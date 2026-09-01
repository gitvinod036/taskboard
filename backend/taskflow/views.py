from django.contrib.auth import logout
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, DateTimeField, Exists, F, OuterRef, Prefetch, Q
from django.db.models.functions import Coalesce, TruncWeek
from django.core.mail import send_mail
from django.utils import timezone
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from datetime import timedelta
import hashlib
import secrets
from urllib.parse import urlencode
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .pagination import StandardResultsPagination
from .permissions import IsAdmin, IsNormalUser
from .serializers import CodingProblemAdminSerializer, CodingProblemUserSerializer, AdminAssignedTaskSerializer, AdminAssignmentSerializer, AdminSubmissionSerializer, AdminUserDetailSerializer, AdminUserSerializer, AdminUserUpdateSerializer, LoginSerializer, NotificationPreferenceSerializer, NotificationSerializer, PasswordResetConfirmSerializer, PasswordResetRequestSerializer, RegisterSerializer, SubmissionAnalysisSerializer, SubmissionReviewSerializer, TaskAssignmentSerializer, TaskEvaluationSerializer, TaskSerializer, TaskSubmissionSerializer, TechStackSerializer, UserSerializer
from .models import GoogleIdentity, GoogleLoginCode, Notification, NotificationPreference, SubmissionAnalysis, Task, TaskAssignment, TaskEvaluation, TaskSubmission, TechStack, UserTechStack

User = get_user_model()


def filter_with_all_tech_stacks(queryset, tech_stacks, filter_lookup, count_lookup):
	"""AND-filter a queryset to records whose tech-stack relation contains ALL names.

	Replaces the previous ``for stack: queryset.filter(rel__name=stack)`` loop,
	which produced one JOIN pair per selected stack. Instead a single JOIN plus a
	filtered COUNT/HAVING requires every requested stack to be present, so the
	query shape stays constant regardless of how many stacks are selected while
	preserving the original AND semantics exactly.
	"""
	stack_names = list(dict.fromkeys(tech_stacks))
	if not stack_names:
		return queryset
	condition = {f'{filter_lookup}__in': stack_names}
	return (
		queryset
		.filter(**condition)
		.annotate(_matching_tech_stack_count=Count(
			count_lookup,
			filter=Q(**condition),
			distinct=True,
		))
		.filter(_matching_tech_stack_count=len(stack_names))
	)



class RegisterView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = RegisterSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()
		token = Token.objects.create(user=user)
		return Response({'token': token.key, 'user': UserSerializer(user).data}, status=status.HTTP_201_CREATED)


class LoginView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = LoginSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.validated_data['user']
		token, _ = Token.objects.get_or_create(user=user)
		return Response({'token': token.key, 'user': UserSerializer(user).data})


def oauth_error_redirect(message):
	return redirect(f"{settings.FRONTEND_URL.rstrip('/')}/login?{urlencode({'oauth_error': message})}")


def google_flow(state=None):
	if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
		raise ImproperlyConfigured('Google OAuth credentials are not configured.')
	client_config = {
		'web': {
			'client_id': settings.GOOGLE_CLIENT_ID,
			'client_secret': settings.GOOGLE_CLIENT_SECRET,
			'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
			'token_uri': 'https://oauth2.googleapis.com/token',
			'redirect_uris': [settings.GOOGLE_REDIRECT_URI],
		}
	}
	# Canonical Google OAuth scopes (openid + email + profile). Short aliases
	# such as 'email'/'profile' must not be used here: Google's token endpoint
	# always returns the full canonical URLs, and oauthlib compares requested
	# vs granted scopes as strict sets during fetch_token(), so aliases make
	# every exchange fail with 'Scope has changed ...'.
	flow = Flow.from_client_config(
		client_config,
		scopes=[
			'openid',
			'https://www.googleapis.com/auth/userinfo.email',
			'https://www.googleapis.com/auth/userinfo.profile',
		],
		state=state,
	)
	flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
	return flow


# class GoogleLoginView(APIView):
# 	permission_classes = [AllowAny]

# 	def get(self, request):
# 		try:
# 			flow = google_flow()
# 		except ImproperlyConfigured:
# 			return oauth_error_redirect('Google login is not configured.')
# 		authorization_url, state = flow.authorization_url(access_type='online', include_granted_scopes='true', prompt='select_account')
# 		request.session['google_oauth_state'] = state
# 		request.session.set_expiry(settings.GOOGLE_OAUTH_STATE_MAX_AGE)
# 		return redirect(authorization_url)

class GoogleLoginView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            flow = google_flow()
        except ImproperlyConfigured:
            return oauth_error_redirect('Google login is not configured.')

        authorization_url, state = flow.authorization_url(
            access_type='online',
            include_granted_scopes='true',
            prompt='select_account'
        )

        request.session['google_oauth_state'] = state
        request.session['google_oauth_code_verifier'] = flow.code_verifier
        request.session.set_expiry(settings.GOOGLE_OAUTH_STATE_MAX_AGE)

        return redirect(authorization_url)


class GoogleCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        state = request.GET.get('state')

        stored_state = request.session.pop('google_oauth_state', None)
        code_verifier = request.session.pop(
            'google_oauth_code_verifier',
            None
        )

        if not state or state != stored_state:
            return oauth_error_redirect(
                'Google login could not be verified.'
            )

        if request.GET.get('error'):
            return oauth_error_redirect(
                'Google login was cancelled.'
            )

        try:
            flow = google_flow(state=state)
            flow.code_verifier = code_verifier

            flow.fetch_token(
                code=request.GET.get('code', '')
            )

            credentials = id_token.verify_oauth2_token(
                flow.credentials.id_token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )

        except Exception as error:
            print("GOOGLE CALLBACK ERROR:", repr(error))
            return oauth_error_redirect(
                'Google authentication failed.'
            )

        if (
            credentials.get('email_verified') is not True
            or not credentials.get('sub')
            or not credentials.get('email')
        ):
            return oauth_error_redirect(
                'Google account email is not verified.'
            )

        try:
            user = self.get_or_create_user(credentials)
        except ValueError as error:
            return oauth_error_redirect(str(error))

        one_time_code = secrets.token_urlsafe(32)

        GoogleLoginCode.objects.create(
            code_hash=hashlib.sha256(
                one_time_code.encode()
            ).hexdigest(),
            user=user
        )

        return redirect(
            f"{settings.FRONTEND_URL.rstrip('/')}/oauth/callback?"
            f"{urlencode({'code': one_time_code})}"
        )

    def get_or_create_user(self, credentials):
        subject = credentials['sub']
        email = credentials['email'].lower()

        identity = GoogleIdentity.objects.select_related(
            'user'
        ).filter(
            subject=subject
        ).first()

        if identity:
            if identity.email != email:
                identity.email = email
                identity.save(update_fields=['email'])

            return identity.user

        user = User.objects.filter(
            email__iexact=email
        ).first()

        if user is None:
            base_username = ''.join(
                character
                for character in email.split('@')[0]
                if character.isalnum()
            )[:120] or 'googleuser'

            username = base_username
            counter = 1

            while User.objects.filter(
                username=username
            ).exists():
                counter += 1
                username = f'{base_username}{counter}'

            user = User.objects.create(
                username=username,
                email=email
            )

            user.set_unusable_password()
            user.save(update_fields=['password'])

        GoogleIdentity.objects.get_or_create(
            user=user,
            subject=subject,
            defaults={'email': email}
        )

        return user


class GoogleTokenExchangeView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		code = request.data.get('code', '')
		code_hash = hashlib.sha256(code.encode()).hexdigest()
		cutoff = timezone.now() - timedelta(seconds=settings.GOOGLE_OAUTH_STATE_MAX_AGE)
		with transaction.atomic():
			login_code = GoogleLoginCode.objects.select_for_update().select_related('user').filter(code_hash=code_hash, used_at__isnull=True, created_at__gte=cutoff).first()
			if not login_code:
				return Response({'detail': 'Google login code is invalid or expired.'}, status=status.HTTP_400_BAD_REQUEST)
			login_code.used_at = timezone.now()
			login_code.save(update_fields=['used_at'])
			token, _ = Token.objects.get_or_create(user=login_code.user)
		return Response({'token': token.key, 'user': UserSerializer(login_code.user).data})


class PasswordResetRequestView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = PasswordResetRequestSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = User.objects.filter(email__iexact=serializer.validated_data['email'], is_active=True).first()
		if user:
			uid = urlsafe_base64_encode(force_bytes(user.pk))
			token = PasswordResetTokenGenerator().make_token(user)
			reset_url = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password/{uid}/{token}/"
			send_mail(
				subject='TaskBoard password reset',
				message=f'Use this link to reset your TaskBoard password:\n\n{reset_url}',
				from_email=settings.DEFAULT_FROM_EMAIL,
				recipient_list=[user.email],
			)
		return Response({'detail': 'If an account exists for this email, password reset instructions have been sent.'})


class PasswordResetConfirmView(APIView):
	permission_classes = [AllowAny]

	def post(self, request):
		serializer = PasswordResetConfirmSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.validated_data['user']
		user.set_password(serializer.validated_data['new_password'])
		user.save(update_fields=['password'])
		return Response({'detail': 'Password has been reset successfully.'})


class LogoutView(APIView):
	permission_classes = [IsAuthenticated]

	def post(self, request):
		Token.objects.filter(user=request.user).delete()
		logout(request)
		return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		return Response(UserSerializer(request.user).data)


class MeTechStackView(APIView):
	permission_classes = [IsAuthenticated]

	def patch(self, request):
		"""Users can update only their own technology stack."""
		serializer = AdminUserUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		serializer.update(request.user, serializer.validated_data)
		return Response(UserSerializer(request.user).data)


class NotificationPreferenceView(APIView):
	permission_classes = [IsAuthenticated]

	def _get_preference(self, request):
		# Lazily create with model defaults so existing users work untouched.
		preference, _ = NotificationPreference.objects.get_or_create(user=request.user)
		return preference

	def get(self, request):
		return Response(NotificationPreferenceSerializer(self._get_preference(request)).data)

	def patch(self, request):
		"""Users can update only their own notification preferences."""
		preference = self._get_preference(request)
		serializer = NotificationPreferenceSerializer(preference, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)


class NotificationListView(APIView):
	"""GET the current user's notifications (newest first) + unread count.

	Recipient is always request.user â€” a user can never read another user's
	notifications, and no client-supplied recipient/filter is trusted.
	"""

	permission_classes = [IsAuthenticated]

	def get(self, request):
		notifications = Notification.objects.filter(recipient=request.user)[:100]
		unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
		return Response({
			'results': NotificationSerializer(notifications, many=True).data,
			'unread_count': unread_count,
		})


class NotificationMarkReadView(APIView):
	"""POST mark one notification read ({id}) or all of them ({all: true})."""

	permission_classes = [IsAuthenticated]

	def post(self, request):
		if request.data.get('all'):
			updated = Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
			return Response({'marked': updated, 'unread_count': 0})
		notification_id = request.data.get('id')
		if notification_id is None:
			return Response({'detail': 'Provide "id" or "all": true.'}, status=status.HTTP_400_BAD_REQUEST)
		# Scoped to request.user: marking another user's notification is a no-op.
		updated = Notification.objects.filter(
			pk=notification_id, recipient=request.user, is_read=False,
		).update(is_read=True)
		unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
		return Response({'marked': updated, 'unread_count': unread_count})


class AdminCheckView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		return Response({'detail': 'Admin authentication confirmed.', 'user': UserSerializer(request.user).data})


class TaskListCreateView(APIView):
	permission_classes = [IsAuthenticated]

	def get_permissions(self):
		return [IsAdmin()] if self.request.method == 'POST' else [IsAuthenticated()]

	def get(self, request):
		tasks = (
			Task.objects
			.annotate(is_assigned_for_user=Exists(
				TaskAssignment.objects.filter(task=OuterRef('pk'), user=request.user),
			))
			# TaskSerializer serializes task.tech_stack; prefetch it so the
			# SlugRelatedField does not issue one query per task (N+1).
			.prefetch_related('tech_stack')
		)
		tech_stacks = [name.strip() for name in request.query_params.get('tech_stack', '').split(',') if name.strip()]
		if tech_stacks:
			tasks = filter_with_all_tech_stacks(
				tasks, tech_stacks, 'tech_stack__name', 'tech_stack',
			).order_by('due_date', 'id')
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(tasks, request)
		return paginator.get_paginated_response(
			TaskSerializer(page, many=True, context={'request': request}).data,
		)

	def post(self, request):
		serializer = TaskSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		task = serializer.save()
		# A) Notify every eligible active user about the new task (idempotent
		# per user; the creating admin is excluded by notify_task_published).
		notify_task_published(task, creator=request.user)
		return Response(serializer.data, status=status.HTTP_201_CREATED)


class TaskDetailView(APIView):
	permission_classes = [IsAuthenticated]

	def get_permissions(self):
		return [IsAdmin()] if self.request.method in ('PATCH', 'DELETE') else [IsAuthenticated()]

	def get_task(self, task_id):
		try:
			return Task.objects.get(pk=task_id)
		except Task.DoesNotExist:
			return None

	def get(self, request, task_id):
		task = self.get_task(task_id)
		if task is None:
			return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(TaskSerializer(task, context={'request': request}).data)

	def patch(self, request, task_id):
		task = self.get_task(task_id)
		if task is None:
			return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
		serializer = TaskSerializer(task, data=request.data, partial=True)
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)

	def delete(self, request, task_id):
		task = self.get_task(task_id)
		if task is None:
			return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
		task.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


class TaskAssignmentView(APIView):
	permission_classes = [IsNormalUser]

	def get_task(self, task_id):
		try:
			return Task.objects.get(pk=task_id)
		except Task.DoesNotExist:
			return None

	def post(self, request, task_id):
		task = self.get_task(task_id)
		if task is None:
			return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
		assignment, created = TaskAssignment.objects.get_or_create(task=task, user=request.user)
		if not created:
			return Response({'detail': 'You have already assigned this task.'}, status=status.HTTP_409_CONFLICT)
		return Response(TaskAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

	def delete(self, request, task_id):
		task = self.get_task(task_id)
		if task is None:
			return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
		deleted, _ = TaskAssignment.objects.filter(task=task, user=request.user).delete()
		if not deleted:
			return Response({'detail': 'You are not assigned to this task.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(status=status.HTTP_204_NO_CONTENT)


class TaskSubmissionView(APIView):
	permission_classes = [IsNormalUser]

	def post(self, request, task_id):
		assignment = TaskAssignment.objects.filter(task_id=task_id, user=request.user).first()
		if assignment is None:
			return Response({'detail': 'You can only submit tasks assigned to you.'}, status=status.HTTP_403_FORBIDDEN)
		existing = TaskSubmission.objects.filter(task_id=task_id, user=request.user).order_by('-id').first()
		if existing and existing.status != TaskSubmission.Status.REJECTED:
			return Response({'detail': 'This task already has a pending or approved submission.'}, status=status.HTTP_409_CONFLICT)
		serializer = TaskSubmissionSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		# Resubmission always creates a NEW attempt row (history preserved).
		# A rejected attempt is never overwritten or deleted; the reviewer's
		# decision on the newest attempt is the authoritative outcome.
		created = existing is None
		serializer.save(task_id=task_id, user=request.user, status=TaskSubmission.Status.PENDING, feedback='', reviewed_at=None, reviewed_by=None, earned_points=0)
		# B)/F) Notify staff reviewers; a resubmission (the user had a
		# previous attempt) uses the "Improved Submission" wording.
		submission = TaskSubmission.objects.filter(task_id=task_id, user=request.user).order_by('-id').first()
		if submission is not None:
			notify_submission_received(submission, is_resubmission=not created)
		return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class MyTasksView(APIView):
	permission_classes = [IsNormalUser]

	def get(self, request):
		assignments = (
			TaskAssignment.objects
			.filter(user=request.user)
			.select_related('task')
			.prefetch_related(Prefetch(
				'task__submissions',
				# Newest attempt first (orders by DB id desc when ids increase
				# with creation_time), so the authoritative attempt is index 0.
				queryset=TaskSubmission.objects.filter(user=request.user).order_by('-id'),
				to_attr='user_submissions',
			))
			# The nested TaskSerializer serializes task.tech_stack; prefetch it
			# so SlugRelatedField does not query once per task (N+1).
			.prefetch_related('task__tech_stack')
			.order_by('-assigned_date', '-id')
		)
		tech_stacks = [name.strip() for name in request.query_params.get('tech_stack', '').split(',') if name.strip()]
		if tech_stacks:
			assignments = filter_with_all_tech_stacks(
				assignments, tech_stacks, 'task__tech_stack__name', 'task__tech_stack',
			).order_by('-assigned_date', '-id')
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(assignments, request)
		return paginator.get_paginated_response(
			TaskAssignmentSerializer(page, many=True, context={'request': request}).data,
		)


class TechStacksView(APIView):
	"""Read-only list of all tech stacks. Available to any authenticated user."""
	permission_classes = [IsAuthenticated]

	def get(self, request):
		return Response(TechStackSerializer(TechStack.objects.all(), many=True).data)


class AdminUsersView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		users = User.objects.filter(is_staff=False, is_superuser=False)
		search = request.query_params.get('search', '').strip()
		tech_stacks = [name.strip() for name in request.query_params.get('tech_stack', '').split(',') if name.strip()]
		if search:
			users = users.filter(Q(username__icontains=search) | Q(email__icontains=search))
		if tech_stacks:
			users = filter_with_all_tech_stacks(users, tech_stacks, 'user_tech_stacks__tech_stack__name', 'user_tech_stacks')
		# distinct=True keeps the count exact even though the filtered
		# user_tech_stacks join repeats a row per matching stack.
		users = users.annotate(assigned_task_count_value=models.Count('task_assignments', distinct=True)).distinct().order_by('username')
		users = users.prefetch_related(Prefetch(
			'user_tech_stacks',
			queryset=UserTechStack.objects.select_related('tech_stack'),
			to_attr='prefetched_user_stacks',
		))
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(users, request)
		return paginator.get_paginated_response(AdminUserSerializer(page, many=True).data)


class AdminTechStacksView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		return Response(TechStackSerializer(TechStack.objects.all(), many=True).data)


class AdminUserDetailView(APIView):
	permission_classes = [IsAdmin]

	def get_user(self, user_id):
		try:
			return User.objects.get(pk=user_id)
		except User.DoesNotExist:
			return None

	def get(self, request, user_id):
		user = self.get_user(user_id)
		if user is None:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		if user.is_staff or user.is_superuser:
			return Response({'detail': 'Admin accounts cannot be managed.'}, status=status.HTTP_403_FORBIDDEN)
		return Response(AdminUserDetailSerializer(user).data)

	def delete(self, request, user_id):
		user = self.get_user(user_id)
		if user is None:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		if user.is_staff or user.is_superuser:
			return Response({'detail': 'Admin accounts cannot be deleted.'}, status=status.HTTP_403_FORBIDDEN)
		user.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)

	def patch(self, request, user_id):
		user = self.get_user(user_id)
		if user is None:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		if user.is_staff or user.is_superuser:
			return Response({'detail': 'Admin accounts cannot be managed.'}, status=status.HTTP_403_FORBIDDEN)
		serializer = AdminUserUpdateSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		serializer.update(user, serializer.validated_data)
		return Response(AdminUserDetailSerializer(user).data)


class AdminAssignmentsView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		assignments = (
			TaskAssignment.objects
			.select_related('task', 'user')
			# Feeds AdminUserSerializer.assigned_task_count for the nested
			# user so serialization performs no per-assignment COUNT query.
			.annotate(assigned_task_count_value=Count('user__task_assignments', distinct=True))
			.prefetch_related(Prefetch(
				'user__user_tech_stacks',
				queryset=UserTechStack.objects.select_related('tech_stack'),
				to_attr='prefetched_user_stacks',
			))
			# TaskSummarySerializer serializes task.tech_stack; prefetch it so
			# SlugRelatedField does not query once per assignment (N+1).
			.prefetch_related('task__tech_stack')
			.order_by('-assigned_date', '-id')
		)
		tech_stacks = [name.strip() for name in request.query_params.get('tech_stack', '').split(',') if name.strip()]
		if tech_stacks:
			assignments = filter_with_all_tech_stacks(
				assignments, tech_stacks, 'task__tech_stack__name', 'task__tech_stack',
			).order_by('-assigned_date', '-id')
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(assignments, request)
		# The count annotation lives on each TaskAssignment row; expose it on
		# the nested User instance so AdminUserSerializer reads it instead of
		# issuing one COUNT query per assignment. Applied to the current page
		# only, after the database-side LIMIT/OFFSET.
		for assignment in page:
			assignment.user.assigned_task_count_value = assignment.assigned_task_count_value
		return paginator.get_paginated_response(AdminAssignmentSerializer(page, many=True).data)


class AdminSubmissionsView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		submissions = TaskSubmission.objects.select_related('task', 'user', 'reviewed_by').order_by('-submitted_at', '-id')
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(submissions, request)
		return paginator.get_paginated_response(AdminSubmissionSerializer(page, many=True).data)


class AdminSubmissionReviewView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request, submission_id):
		"""Return a single submission (admin only).

		Without this handler every GET on /api/admin/submissions/<id>/ was
		answered with 405 Method Not Allowed, so browsers that had already
		passed the OPTIONS preflight never got a usable response.
		"""
		try:
			submission = TaskSubmission.objects.select_related('task', 'user', 'reviewed_by').get(pk=submission_id)
		except TaskSubmission.DoesNotExist:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(AdminSubmissionSerializer(submission).data)

	def patch(self, request, submission_id):
		try:
			# select_related mirrors the serializer's task/user access so a
			# review costs no extra per-relation queries.
			submission = TaskSubmission.objects.select_related(
				'task', 'user', 'user__notification_preference',
			).get(pk=submission_id)
		except TaskSubmission.DoesNotExist:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		serializer = SubmissionReviewSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		submission.status = serializer.validated_data['status']
		submission.feedback = serializer.validated_data.get('feedback', '')
		submission.reviewed_by = request.user
		submission.reviewed_at = timezone.now()
		with transaction.atomic():
			submission.save(update_fields=('status', 'feedback', 'reviewed_by', 'reviewed_at'))
			# Award points exactly once, server-side, on approval (0 for a
			# rejection). award_normal_task_points is idempotent and row-locked,
			# so repeated or concurrent reviews can never double-award.
			if submission.status == TaskSubmission.Status.APPROVED:
				award_normal_task_points(submission)
			# C)/D) Notify the submitting user about the review outcome.
			notify_submission_reviewed(submission)
		return Response(AdminSubmissionSerializer(submission).data)


class TaskSubmissionEvaluationView(APIView):
	"""GET/POST the AI evaluation of a normal-task submission.

	Authorization: the submission's owner (normal user) or any admin.
	POST runs the evaluation through the existing free-Gemini fallback:
	  - Only APPROVED submissions can be evaluated (the reviewer/judge is the
	    source of truth for acceptance); anything else is 409.
	  - The AI's rubric category scores are validated server-side and the
	    total is ALWAYS recomputed by the backend â€” an AI-supplied total is
	    ignored, so no AI response can award more than the fixed 10 points.
	  - A provider failure marks the evaluation FAILED with zero score and
	    returns the safe 503 the frontend already handles; the user may retry.
	    A failed evaluation never awards points or marks the task solved.
	  - Nothing in request.data is ever trusted: score, points, user_id and
	    solved status are all derived server-side.
	"""

	def get_submission(self, request, submission_id):
		qs = TaskSubmission.objects.select_related('task', 'user')
		if request.user.is_staff or request.user.is_superuser:
			return qs.filter(pk=submission_id).first()
		return qs.filter(pk=submission_id, user=request.user).first()

	def get(self, request, submission_id):
		submission = self.get_submission(request, submission_id)
		if submission is None:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		evaluation = TaskEvaluation.objects.filter(submission=submission).first()
		if evaluation is None:
			return Response({'detail': 'No evaluation yet.'}, status=status.HTTP_404_NOT_FOUND)
		evaluation.best_score = best_task_evaluation_score(submission.user_id, submission.task_id)
		return Response(TaskEvaluationSerializer(evaluation).data)

	def post(self, request, submission_id):
		submission = self.get_submission(request, submission_id)
		if submission is None:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		if submission.status != TaskSubmission.Status.APPROVED:
			return Response(
				{'detail': 'Only approved submissions can be evaluated.'},
				status=status.HTTP_409_CONFLICT,
			)
		try:
			data = generate_task_evaluation(submission)
		except DjangoValidationError:
			# Invalid AI output: no score, retry allowed.
			record_task_evaluation_failure(submission, 'The AI returned an invalid evaluation. Try again.')
			return Response(
				{'detail': 'The AI returned an invalid evaluation. You can retry.'},
				status=status.HTTP_502_BAD_GATEWAY,
			)
		except RuntimeError:
			# Safe provider failure (all free models exhausted / not configured).
			record_task_evaluation_failure(submission)
			return Response(
				{'detail': 'AI service is temporarily unavailable. Please try again shortly.'},
				status=status.HTTP_503_SERVICE_UNAVAILABLE,
			)
		evaluation = save_task_evaluation(submission, data)
		evaluation.best_score = best_task_evaluation_score(submission.user_id, submission.task_id)
		# E) Successful evaluation only â€” failed evaluations never notify.
		notify_evaluation_completed(submission, evaluation)
		return Response(TaskEvaluationSerializer(evaluation).data, status=status.HTTP_200_OK)


class AdminUserTasksView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request, user_id):
		try:
			user = User.objects.get(pk=user_id)
		except User.DoesNotExist:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		if user.is_staff or user.is_superuser:
			return Response({'detail': 'Admin accounts cannot be managed.'}, status=status.HTTP_403_FORBIDDEN)
		assignments = user.task_assignments.select_related('task').prefetch_related('task__tech_stack').order_by('-assigned_date')
		return Response(AdminAssignedTaskSerializer(assignments, many=True).data)


class AdminUserTaskDeleteView(APIView):
	permission_classes = [IsAdmin]

	def delete(self, request, user_id, task_id):
		try:
			user = User.objects.get(pk=user_id)
		except User.DoesNotExist:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		if user.is_staff or user.is_superuser:
			return Response({'detail': 'Admin accounts cannot be managed.'}, status=status.HTTP_403_FORBIDDEN)
		try:
			task = Task.objects.get(pk=task_id)
		except Task.DoesNotExist:
			return Response({'detail': 'Task not found.'}, status=status.HTTP_404_NOT_FOUND)
		deleted, _ = TaskAssignment.objects.filter(user=user, task=task).delete()
		if not deleted:
			return Response({'detail': 'Assignment not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(status=status.HTTP_204_NO_CONTENT)


class AdminDashboardView(APIView):
	"""Aggregated workspace metrics for the admin dashboard.

	All figures are computed server-side from real records so the frontend never
	downloads or aggregates large task lists itself.
	"""

	permission_classes = [IsAdmin]

	def get(self, request):
		today = timezone.localdate()
		member_users = Q(is_staff=False, is_superuser=False)

		total_tasks = Task.objects.count()
		completed_count = TaskSubmission.objects.filter(status=TaskSubmission.Status.APPROVED).count()
		pending_review_count = TaskSubmission.objects.filter(status=TaskSubmission.Status.PENDING).count()

		# A task stays "in progress" while its assignment has no pending or
		# approved submission (never submitted, or the last one was rejected).
		settled_submission = TaskSubmission.objects.filter(
			task=OuterRef('task'),
			user=OuterRef('user'),
			status__in=(TaskSubmission.Status.PENDING, TaskSubmission.Status.APPROVED),
		)
		in_progress_count = (
			TaskAssignment.objects
			.annotate(is_settled=Exists(settled_submission))
			.filter(is_settled=False)
			.count()
		)

		approved_submission = TaskSubmission.objects.filter(task=OuterRef('pk'), status=TaskSubmission.Status.APPROVED)
		overdue_tasks = (
			Task.objects
			.filter(due_date__lt=today)
			.annotate(is_completed=Exists(approved_submission))
			.filter(is_completed=False)
			.order_by('due_date', 'id')
		)
		overdue_items = [
			{
				'id': task.id,
				'title': task.title,
				'due_date': task.due_date,
				'days_overdue': (today - task.due_date).days,
			}
			for task in overdue_tasks[:8]
		]

		total_users = User.objects.filter(member_users).count()
		participates = (
			Exists(TaskAssignment.objects.filter(user=OuterRef('pk')))
			| Exists(TaskSubmission.objects.filter(user=OuterRef('pk')))
		)
		active_users = (
			User.objects
			.filter(member_users)
			.annotate(has_participation=participates)
			.filter(has_participation=True)
			.count()
		)

		status_distribution = [
			{'key': 'COMPLETED', 'label': 'Completed', 'count': completed_count},
			{'key': 'IN_PROGRESS', 'label': 'In Progress', 'count': in_progress_count},
			{'key': 'PENDING_REVIEW', 'label': 'Pending Review', 'count': pending_review_count},
		]

		# Weekly completions over the trailing eight weeks. A task counts as
		# completed when it was approved; reviewed_at marks that moment and
		# submitted_at is the fallback for approvals without a stored review.
		trend_start = today - timedelta(days=today.weekday()) - timedelta(weeks=7)
		trend_rows = (
			TaskSubmission.objects
			.filter(status=TaskSubmission.Status.APPROVED)
			.annotate(
				completion_time=Coalesce('reviewed_at', 'submitted_at', output_field=DateTimeField()),
			)
			.filter(completion_time__date__gte=trend_start)
			.annotate(week_start=TruncWeek('completion_time'))
			.values('week_start')
			.annotate(completions=Count('id'))
		)
		completions_by_week = {row['week_start'].date(): row['completions'] for row in trend_rows}
		completion_trend = []
		week_cursor = trend_start
		while week_cursor <= today - timedelta(days=today.weekday()):
			completion_trend.append({
				'week_start': week_cursor.isoformat(),
				'completions': completions_by_week.get(week_cursor, 0),
			})
			week_cursor += timedelta(weeks=1)

		top_users = (
			User.objects
			.filter(member_users)
			.annotate(
				completed_tasks=Count('task_submissions', filter=Q(task_submissions__status=TaskSubmission.Status.APPROVED)),
			)
			.filter(completed_tasks__gt=0)
			.order_by('-completed_tasks', 'id')[:5]
		)

		technology_distribution = [
			{'technology': stack['name'], 'task_count': stack['task_count']}
			for stack in TechStack.objects
			.annotate(task_count=Count('tasks'))
			.order_by('-task_count', 'name')
			.values('name', 'task_count')
		]

		events = []
		for assignment in TaskAssignment.objects.select_related('task', 'user').order_by('-assigned_date')[:10]:
			events.append({'type': 'ASSIGNMENT', 'actor': assignment.user.username, 'task_title': assignment.task.title, 'timestamp': assignment.assigned_date})
		for submission in TaskSubmission.objects.select_related('task', 'user', 'reviewed_by').order_by('-submitted_at')[:10]:
			events.append({'type': 'SUBMISSION', 'actor': submission.user.username, 'task_title': submission.task.title, 'timestamp': submission.submitted_at})
			if submission.reviewed_at and submission.reviewed_by:
				events.append({'type': 'REVIEW', 'actor': submission.reviewed_by.username, 'task_title': submission.task.title, 'timestamp': submission.reviewed_at})
		events.sort(key=lambda event: event['timestamp'], reverse=True)
		recent_activity = [
			{'type': event['type'], 'actor': event['actor'], 'task_title': event['task_title'], 'timestamp': event['timestamp']}
			for event in events[:10]
		]

		return Response({
			'totals': {
				'total_tasks': total_tasks,
				'completed': completed_count,
				'in_progress': in_progress_count,
				'pending_review': pending_review_count,
				'overdue': overdue_tasks.count(),
				'total_users': total_users,
				'active_users': active_users,
			},
			'status_distribution': status_distribution,
			'priority_distribution': {
				'supported': False,
				'message': 'NOT CURRENTLY SUPPORTED BY DATA MODEL',
				'distribution': None,
			},
			'completion_trend': {
				'period_weeks': 8,
				'points': completion_trend,
			},
			'top_users': [
				{
					'id': user.id,
					'username': user.username,
					'name': user.get_full_name() or user.username,
					'completed_tasks': user.completed_tasks,
				}
				for user in top_users
			],
			'overdue_tasks': {
				'total': overdue_tasks.count(),
				'items': overdue_items,
			},
			'technology_distribution': technology_distribution,
					'recent_activity': recent_activity,
		})


from .models import CodingProblem, CodingProblemTestCase
from .services import build_submission_analysis_context, create_coding_problem_from_ai, generate_submission_analysis, generate_task_draft, MAX_TASK_DRAFT_PROMPT_LENGTH, save_submission_analysis, coding_leaderboard, generate_task_evaluation, save_task_evaluation, record_task_evaluation_failure, best_task_evaluation_score, award_normal_task_points, notify_task_published, notify_submission_received, notify_submission_reviewed, notify_evaluation_completed
from django.core.exceptions import ValidationError as DjangoValidationError


def _parse_int_param(value):
	try:
		return int(value)
	except (TypeError, ValueError):
		return None


class CodingProblemGenerateView(APIView):
	permission_classes = [IsAdmin]

	def post(self, request):
		title = (request.data.get('title') or '').strip()
		idea = (request.data.get('idea') or '').strip()
		if not title or not idea:
			return Response({'detail': 'Both title and idea are required.'}, status=status.HTTP_400_BAD_REQUEST)
		try:
			problem = create_coding_problem_from_ai(title, idea, request.user)
		except RuntimeError:
			return Response({'detail': 'AI service is temporarily unavailable. Please try again shortly.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
		except DjangoValidationError as exc:
			detail = exc.detail if hasattr(exc, 'detail') else exc.messages
			return Response({'detail': detail}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
		serializer = CodingProblemAdminSerializer(problem, context={'request': request})
		return Response(serializer.data, status=status.HTTP_201_CREATED)


class TaskDraftAIView(APIView):
	"""AI Task Assistant: generates a task DRAFT for admin review.

	Draft-only by design â€” nothing is persisted; the admin edits the result
	and creates the task through the existing POST /api/tasks/ flow.
	Task creation in this app is admin-only, so generation is too.
	"""

	permission_classes = [IsAdmin]

	def post(self, request):
		prompt = request.data.get('prompt')
		if not isinstance(prompt, str):
			return Response({'detail': 'prompt must be a string.'}, status=status.HTTP_400_BAD_REQUEST)
		prompt = prompt.strip()
		if not prompt:
			return Response({'detail': 'prompt is required.'}, status=status.HTTP_400_BAD_REQUEST)
		if len(prompt) > MAX_TASK_DRAFT_PROMPT_LENGTH:
			return Response({'detail': f'prompt must be at most {MAX_TASK_DRAFT_PROMPT_LENGTH} characters.'}, status=status.HTTP_400_BAD_REQUEST)
		try:
			draft = generate_task_draft(prompt)
		except RuntimeError:
			return Response({'detail': 'AI service is temporarily unavailable. Please try again shortly.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
		except DjangoValidationError as exc:
			detail = exc.detail if hasattr(exc, 'detail') else exc.messages
			return Response({'detail': detail}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
		return Response(draft)


class AdminCodingProblemsView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		problems = CodingProblem.objects.all().order_by('-created_at', '-id')
		search = request.query_params.get('search', '').strip()
		if search:
			problems = problems.filter(title__icontains=search)
		status_val = request.query_params.get('status', '').strip().upper()
		if status_val in CodingProblem.Status.values:
			problems = problems.filter(status=status_val)
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(problems, request)
		return paginator.get_paginated_response(CodingProblemAdminSerializer(page, many=True, context={'request': request}).data)

	def post(self, request):
		serializer = CodingProblemAdminSerializer(data=request.data, context={'request': request})
		serializer.is_valid(raise_exception=True)
		serializer.save(created_by=request.user)
		return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminCodingProblemDetailView(APIView):
	permission_classes = [IsAdmin]

	def get_object(self, problem_id):
		try:
			return CodingProblem.objects.get(pk=problem_id)
		except CodingProblem.DoesNotExist:
			return None

	def get(self, request, problem_id):
		problem = self.get_object(problem_id)
		if problem is None:
			return Response({'detail': 'Problem not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(CodingProblemAdminSerializer(problem, context={'request': request}).data)

	def patch(self, request, problem_id):
		problem = self.get_object(problem_id)
		if problem is None:
			return Response({'detail': 'Problem not found.'}, status=status.HTTP_404_NOT_FOUND)
		serializer = CodingProblemAdminSerializer(problem, data=request.data, partial=True, context={'request': request})
		serializer.is_valid(raise_exception=True)
		serializer.save()
		return Response(serializer.data)

	def delete(self, request, problem_id):
		problem = self.get_object(problem_id)
		if problem is None:
			return Response({'detail': 'Problem not found.'}, status=status.HTTP_404_NOT_FOUND)
		problem.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


class CodingProblemListView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request):
		problems = CodingProblem.objects.filter(status=CodingProblem.Status.PUBLISHED).order_by('-published_at', '-id')
		search = request.query_params.get('search', '').strip()
		if search:
			problems = problems.filter(title__icontains=search)
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(problems, request)
		return paginator.get_paginated_response(CodingProblemUserSerializer(page, many=True, context={'request': request}).data)


class CodingProblemDetailView(APIView):
	permission_classes = [IsAuthenticated]

	def get(self, request, problem_id):
		try:
			problem = CodingProblem.objects.get(pk=problem_id, status=CodingProblem.Status.PUBLISHED)
		except CodingProblem.DoesNotExist:
			return Response({'detail': 'Problem not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(CodingProblemUserSerializer(problem, context={'request': request}).data)


from .models import CodeSubmission
from .serializers import (
	AdminCodeSubmissionSerializer,
	CodeSubmissionCreateSerializer,
	CodeSubmissionUserSerializer,
)
from .execution import SandboxUnavailable, docker_available, execute_submission


def _get_published_problem(problem_id):
	try:
		return CodingProblem.objects.get(pk=problem_id, status=CodingProblem.Status.PUBLISHED)
	except CodingProblem.DoesNotExist:
		return None


def _create_submission(request, problem, mode):
	"""Validate input and persist a PENDING submission (client sets nothing)."""
	serializer = CodeSubmissionCreateSerializer(
		data=request.data, context={'request': request, 'problem': problem})
	serializer.is_valid(raise_exception=True)
	return CodeSubmission.objects.create(
		user=request.user,
		problem=problem,
		language=serializer.validated_data['language'],
		source_code=serializer.validated_data['source_code'],
		mode=mode,
		status=CodeSubmission.Status.PENDING,
	)


class CodingProblemSubmitView(APIView):
	"""Submit a solution for full judging (public + hidden tests).

	PHASE 3: the stored source code is executed inside an isolated Docker
	sandbox. The client cannot influence status/verdict/metrics in any way.
	"""
	permission_classes = [IsAuthenticated]

	def post(self, request, problem_id):
		problem = _get_published_problem(problem_id)
		if problem is None:
			return Response({'detail': 'Problem not found.'}, status=status.HTTP_404_NOT_FOUND)
		if not docker_available():
			return Response(
				{'detail': 'The execution environment is currently unavailable.'},
				status=status.HTTP_503_SERVICE_UNAVAILABLE)

		submission = _create_submission(request, problem, CodeSubmission.Mode.SUBMIT)
		execute_submission(submission, mode=CodeSubmission.Mode.SUBMIT)
		return Response(
			CodeSubmissionUserSerializer(submission).data,
			status=status.HTTP_201_CREATED,
		)


class CodingProblemRunView(APIView):
	"""Run a solution against PUBLIC test cases only.

	Same sandbox isolation as Submit; hidden tests are never touched, so
	their inputs and expected outputs can never leak through this endpoint.
	"""
	permission_classes = [IsAuthenticated]

	def post(self, request, problem_id):
		problem = _get_published_problem(problem_id)
		if problem is None:
			return Response({'detail': 'Problem not found.'}, status=status.HTTP_404_NOT_FOUND)
		if not docker_available():
			return Response(
				{'detail': 'The execution environment is currently unavailable.'},
				status=status.HTTP_503_SERVICE_UNAVAILABLE)

		submission = _create_submission(request, problem, CodeSubmission.Mode.RUN)
		execute_submission(submission, mode=CodeSubmission.Mode.RUN)
		return Response(
			CodeSubmissionUserSerializer(submission).data,
			status=status.HTTP_201_CREATED,
		)


class CodingSubmissionListView(APIView):
	"""List the current user's own submissions (optionally per problem).

	Scoped to request.user server-side; another user's rows are simply not
	addressable through this endpoint.
	"""
	permission_classes = [IsAuthenticated]

	def get(self, request):
		submissions = (
			CodeSubmission.objects
			.filter(user=request.user)
			.select_related('problem')
			.order_by('-created_at', '-id')
		)
		problem_id = _parse_int_param(request.query_params.get('problem'))
		if problem_id is not None:
			submissions = submissions.filter(problem_id=problem_id)
		status_val = (request.query_params.get('status') or '').strip().upper()
		if status_val in CodeSubmission.Status.values:
			submissions = submissions.filter(status=status_val)
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(submissions, request)
		return paginator.get_paginated_response(
			CodeSubmissionUserSerializer(page, many=True, context={'request': request}).data)


class CodingSubmissionDetailView(APIView):
	"""Retrieve one of the current user's own submissions.

	A non-owner (including an admin hitting the user endpoint) gets a 404 so
	the existence of someone else's submission is never confirmed.
	Admins use /api/admin/coding/submissions/<id>/ instead.
	"""
	permission_classes = [IsAuthenticated]

	def get(self, request, submission_id):
		submission = (
			CodeSubmission.objects
			.select_related('problem', 'user')
			.filter(user=request.user, pk=submission_id)
			.first()
		)
		if submission is None:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(CodeSubmissionUserSerializer(submission, context={'request': request}).data)


class CodingLeaderboardView(APIView):
	"""Deterministic leaderboard of coding points for all members.

	Fully derived from judge results (only ACCEPTED SUBMIT submissions count);
	no stored scores, so clients can never inject or alter points.
	"""
	permission_classes = [IsAuthenticated]

	def get(self, request):
		return Response(coding_leaderboard())


class AdminCodingSubmissionsView(APIView):
	"""Admin listing/inspection of coding submissions.

	Read-only by design: admins can review code but cannot fabricate or edit
	execution results through this API â€” those come from Phase 3.
	"""
	permission_classes = [IsAdmin]

	def get(self, request):
		submissions = (
			CodeSubmission.objects
			.select_related('problem', 'user')
			.order_by('-created_at', '-id')
		)
		problem_id = _parse_int_param(request.query_params.get('problem'))
		if problem_id is not None:
			submissions = submissions.filter(problem_id=problem_id)
		user_id = _parse_int_param(request.query_params.get('user'))
		if user_id is not None:
			submissions = submissions.filter(user_id=user_id)
		status_val = (request.query_params.get('status') or '').strip().upper()
		if status_val in CodeSubmission.Status.values:
			submissions = submissions.filter(status=status_val)
		paginator = StandardResultsPagination()
		page = paginator.paginate_queryset(submissions, request)
		return paginator.get_paginated_response(AdminCodeSubmissionSerializer(page, many=True).data)


class AdminCodeSubmissionDetailView(APIView):
	permission_classes = [IsAdmin]

	def get_object(self, submission_id):
		return (
			CodeSubmission.objects
			.select_related('problem', 'user')
			.filter(pk=submission_id)
			.first()
		)

	def get(self, request, submission_id):
		submission = self.get_object(submission_id)
		if submission is None:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		return Response(AdminCodeSubmissionSerializer(submission).data)


def _build_analysis_response(submission, serializer):
	judge_result = {
		'status': submission.status,
		'verdict': submission.verdict,
		'passed_tests': submission.passed_tests,
		'total_tests': submission.total_tests,
		'execution_time': submission.execution_time,
		'memory_used': submission.memory_used,
		'feedback': submission.feedback,
	}
	return {
		'submission': serializer(submission).data,
		'judge_result': judge_result,
		'analysis': None,
	}


class SubmissionAnalysisView(APIView):
	"""Analyze one of the current user's own completed submissions.

	The existing judge remains the sole source of truth for pass/fail;
	this endpoint returns Gemini's qualitative coaching only. A non-owner
	(including an admin using the user endpoint) gets a 404 so the
	existence of another user's submission is never confirmed.
	"""
	permission_classes = [IsAuthenticated]

	def get_submission(self, request, submission_id):
		return (
			CodeSubmission.objects
			.select_related('problem', 'user')
			.filter(user=request.user, pk=submission_id)
			.first()
		)

	def post(self, request, submission_id):
		submission = self.get_submission(request, submission_id)
		if submission is None:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		return self._run(submission, CodeSubmissionUserSerializer, request)

	def _run(self, submission, serializer, request):
		try:
			context_text = build_submission_analysis_context(submission)
			data = generate_submission_analysis(context_text)
			analysis = save_submission_analysis(submission, data)
		except RuntimeError:
			return Response({'detail': 'AI service is temporarily unavailable. Please try again shortly.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
		except DjangoValidationError as exc:
			detail = exc.detail if hasattr(exc, 'detail') else exc.messages
			return Response({'detail': detail}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
		payload = _build_analysis_response(submission, serializer)
		payload['analysis'] = SubmissionAnalysisSerializer(analysis).data
		return Response(payload, status=status.HTTP_200_OK)


class AdminSubmissionAnalysisView(APIView):
	"""Admin-only AI analysis of any submission an admin can inspect.

	Same qualitative-only behaviour as SubmissionAnalysisView, but scoped
	by IsAdmin (admins use this instead of the user endpoint).
	"""
	permission_classes = [IsAdmin]

	def get_object(self, submission_id):
		return (
			CodeSubmission.objects
			.select_related('problem', 'user')
			.filter(pk=submission_id)
			.first()
		)

	def post(self, request, submission_id):
		submission = self.get_object(submission_id)
		if submission is None:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		try:
			context_text = build_submission_analysis_context(submission)
			data = generate_submission_analysis(context_text)
			analysis = save_submission_analysis(submission, data)
		except RuntimeError:
			return Response({'detail': 'AI service is temporarily unavailable. Please try again shortly.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
		except DjangoValidationError as exc:
			detail = exc.detail if hasattr(exc, 'detail') else exc.messages
			return Response({'detail': detail}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
		payload = _build_analysis_response(submission, AdminCodeSubmissionSerializer)
		payload['analysis'] = SubmissionAnalysisSerializer(analysis).data
		return Response(payload, status=status.HTTP_200_OK)



