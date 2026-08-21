from django.contrib.auth import logout
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, Q
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

from .permissions import IsAdmin, IsNormalUser
from .serializers import AdminAssignedTaskSerializer, AdminAssignmentSerializer, AdminSubmissionSerializer, AdminUserDetailSerializer, AdminUserSerializer, AdminUserUpdateSerializer, LoginSerializer, PasswordResetConfirmSerializer, PasswordResetRequestSerializer, RegisterSerializer, SubmissionReviewSerializer, TaskAssignmentSerializer, TaskSerializer, TaskSubmissionSerializer, TechStackSerializer, UserSerializer
from .models import GoogleIdentity, GoogleLoginCode, Task, TaskAssignment, TaskSubmission, TechStack

User = get_user_model()


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
	flow = Flow.from_client_config(client_config, scopes=['openid', 'email', 'profile'], state=state)
	flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
	return flow


class GoogleLoginView(APIView):
	permission_classes = [AllowAny]

	def get(self, request):
		try:
			flow = google_flow()
		except ImproperlyConfigured:
			return oauth_error_redirect('Google login is not configured.')
		authorization_url, state = flow.authorization_url(access_type='online', include_granted_scopes='true', prompt='select_account')
		request.session['google_oauth_state'] = state
		request.session.set_expiry(settings.GOOGLE_OAUTH_STATE_MAX_AGE)
		return redirect(authorization_url)


class GoogleCallbackView(APIView):
	permission_classes = [AllowAny]

	def get(self, request):
		state = request.GET.get('state')
		if not state or state != request.session.pop('google_oauth_state', None):
			return oauth_error_redirect('Google login could not be verified.')
		if request.GET.get('error'):
			return oauth_error_redirect('Google login was cancelled.')
		try:
			flow = google_flow(state=state)
			flow.fetch_token(code=request.GET.get('code', ''))
			credentials = id_token.verify_oauth2_token(flow.credentials.id_token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
		except Exception:
			return oauth_error_redirect('Google authentication failed.')
		if credentials.get('email_verified') is not True or not credentials.get('sub') or not credentials.get('email'):
			return oauth_error_redirect('Google account email is not verified.')
		try:
			user = self.get_or_create_user(credentials)
		except ValueError as error:
			return oauth_error_redirect(str(error))
		one_time_code = secrets.token_urlsafe(32)
		GoogleLoginCode.objects.create(code_hash=hashlib.sha256(one_time_code.encode()).hexdigest(), user=user)
		return redirect(f"{settings.FRONTEND_URL.rstrip('/')}/oauth/callback?{urlencode({'code': one_time_code})}")

	def get_or_create_user(self, credentials):
		subject = credentials['sub']
		email = credentials['email'].lower()
		identity = GoogleIdentity.objects.select_related('user').filter(subject=subject).first()
		if identity:
			if identity.email != email:
				identity.email = email
				identity.save(update_fields=['email'])
			return identity.user
		user = User.objects.filter(email__iexact=email).first()
		if user is None:
			base_username = ''.join(character for character in email.split('@')[0] if character.isalnum())[:120] or 'googleuser'
			username = base_username
			counter = 1
			while User.objects.filter(username=username).exists():
				counter += 1
				username = f'{base_username}{counter}'
			user = User.objects.create(username=username, email=email)
			user.set_unusable_password()
			user.save(update_fields=['password'])
		GoogleIdentity.objects.get_or_create(user=user, subject=subject, defaults={'email': email})
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


class AdminCheckView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		return Response({'detail': 'Admin authentication confirmed.', 'user': UserSerializer(request.user).data})


class TaskListCreateView(APIView):
	permission_classes = [IsAuthenticated]

	def get_permissions(self):
		return [IsAdmin()] if self.request.method == 'POST' else [IsAuthenticated()]

	def get(self, request):
		return Response(TaskSerializer(Task.objects.all(), many=True, context={'request': request}).data)

	def post(self, request):
		serializer = TaskSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		serializer.save()
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
		submission = TaskSubmission.objects.filter(task_id=task_id, user=request.user).first()
		if submission and submission.status != TaskSubmission.Status.REJECTED:
			return Response({'detail': 'This task already has a pending or approved submission.'}, status=status.HTTP_409_CONFLICT)
		serializer = TaskSubmissionSerializer(submission, data=request.data, partial=False) if submission else TaskSubmissionSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		serializer.save(task_id=task_id, user=request.user, status=TaskSubmission.Status.PENDING, feedback='', reviewed_at=None, reviewed_by=None)
		return Response(serializer.data, status=status.HTTP_200_OK if submission else status.HTTP_201_CREATED)


class MyTasksView(APIView):
	permission_classes = [IsNormalUser]

	def get(self, request):
		assignments = TaskAssignment.objects.filter(user=request.user).select_related('task').order_by('-assigned_date')
		return Response(TaskAssignmentSerializer(assignments, many=True, context={'request': request}).data)


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
			users = users.filter(user_tech_stacks__tech_stack__name__in=tech_stacks).annotate(
				matching_tech_stack_count=Count('user_tech_stacks__tech_stack', distinct=True),
			).filter(matching_tech_stack_count=len(set(tech_stacks)))
		users = users.annotate(assigned_task_count_value=models.Count('task_assignments')).distinct().order_by('username')
		return Response(AdminUserSerializer(users, many=True).data)


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
		assignments = TaskAssignment.objects.select_related('task', 'user').order_by('-assigned_date')
		return Response(AdminAssignmentSerializer(assignments, many=True).data)


class AdminSubmissionsView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request):
		submissions = TaskSubmission.objects.select_related('task', 'user', 'reviewed_by').order_by('-submitted_at')
		return Response(AdminSubmissionSerializer(submissions, many=True).data)


class AdminSubmissionReviewView(APIView):
	permission_classes = [IsAdmin]

	def patch(self, request, submission_id):
		try:
			submission = TaskSubmission.objects.get(pk=submission_id)
		except TaskSubmission.DoesNotExist:
			return Response({'detail': 'Submission not found.'}, status=status.HTTP_404_NOT_FOUND)
		serializer = SubmissionReviewSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		submission.status = serializer.validated_data['status']
		submission.feedback = serializer.validated_data.get('feedback', '')
		submission.reviewed_by = request.user
		submission.reviewed_at = timezone.now()
		submission.save(update_fields=('status', 'feedback', 'reviewed_by', 'reviewed_at'))
		return Response(AdminSubmissionSerializer(submission).data)


class AdminUserTasksView(APIView):
	permission_classes = [IsAdmin]

	def get(self, request, user_id):
		try:
			user = User.objects.get(pk=user_id)
		except User.DoesNotExist:
			return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
		if user.is_staff or user.is_superuser:
			return Response({'detail': 'Admin accounts cannot be managed.'}, status=status.HTTP_403_FORBIDDEN)
		assignments = user.task_assignments.select_related('task').order_by('-assigned_date')
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
