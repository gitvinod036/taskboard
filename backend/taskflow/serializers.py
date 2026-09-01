from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .languages import is_language_allowed_for_problem
from .models import CodeSubmission, CodingProblem, CodingProblemTestCase, Notification, NotificationPreference, SubmissionAnalysis, Task, TaskAssignment, TaskEvaluation, TaskSubmission, TechStack, UserTechStack
from .services import points_earned_for_submission

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
	role = serializers.SerializerMethodField()
	tech_stack = serializers.SerializerMethodField()

	class Meta:
		model = User
		fields = ('id', 'username', 'email', 'role', 'tech_stack')
		read_only_fields = fields

	def get_role(self, user):
		return 'ADMIN' if user.is_staff or user.is_superuser else 'USER'

	def get_tech_stack(self, user):
		return list(user.user_tech_stacks.select_related('tech_stack').values_list('tech_stack__name', flat=True))


class RegisterSerializer(serializers.ModelSerializer):
	password = serializers.CharField(write_only=True, min_length=8)
	password_confirm = serializers.CharField(write_only=True)
	tech_stack = serializers.ListField(child=serializers.CharField(), required=False, default=list, write_only=True)

	class Meta:
		model = User
		fields = ('username', 'email', 'password', 'password_confirm', 'tech_stack')

	def validate(self, attrs):
		tech_stack_names = attrs.get('tech_stack', [])
		known_names = set(TechStack.objects.filter(name__in=tech_stack_names).values_list('name', flat=True))
		if set(tech_stack_names) != known_names:
			raise serializers.ValidationError({'tech_stack': 'One or more tech stacks are invalid.'})
		if attrs['password'] != attrs.pop('password_confirm'):
			raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
		validate_password(attrs['password'])
		return attrs

	def create(self, validated_data):
		tech_stack_names = validated_data.pop('tech_stack', [])
		user = User.objects.create_user(**validated_data, is_staff=False, is_superuser=False)
		UserTechStack.objects.bulk_create([
			UserTechStack(user=user, tech_stack=tech_stack)
			for tech_stack in TechStack.objects.filter(name__in=tech_stack_names)
		])
		return user


class LoginSerializer(serializers.Serializer):
	username = serializers.CharField()
	password = serializers.CharField(write_only=True)

	def validate(self, attrs):
		user = authenticate(username=attrs['username'], password=attrs['password'])
		if user is None:
			raise serializers.ValidationError('Invalid username or password.')
		if not user.is_active:
			raise serializers.ValidationError('This account is inactive.')
		attrs['user'] = user
		return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
	email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
	uid = serializers.CharField()
	token = serializers.CharField()
	new_password = serializers.CharField(write_only=True)
	new_password_confirm = serializers.CharField(write_only=True)

	def validate(self, attrs):
		if attrs['new_password'] != attrs['new_password_confirm']:
			raise serializers.ValidationError({'new_password_confirm': 'Passwords do not match.'})
		try:
			user_id = force_str(urlsafe_base64_decode(attrs['uid']))
			user = User.objects.get(pk=user_id)
		except (TypeError, ValueError, OverflowError, User.DoesNotExist):
			raise serializers.ValidationError({'token': 'This password reset link is invalid or expired.'})
		if not PasswordResetTokenGenerator().check_token(user, attrs['token']):
			raise serializers.ValidationError({'token': 'This password reset link is invalid or expired.'})
		validate_password(attrs['new_password'], user=user)
		attrs['user'] = user
		return attrs


class TaskSerializer(serializers.ModelSerializer):
	is_assigned = serializers.SerializerMethodField()
	points = serializers.ReadOnlyField()
	tech_stack = serializers.SlugRelatedField(
		many=True,
		read_only=True,
		slug_field='name',
	)

	class Meta:
		model = Task
		fields = ('id', 'title', 'description', 'difficulty', 'points', 'due_date', 'is_assigned', 'tech_stack')
		read_only_fields = ('is_assigned', 'tech_stack', 'points')

	def get_is_assigned(self, task):
		# Uses the `is_assigned_for_user` annotation added by list endpoints
		# (see TaskListCreateView) so serialization performs no extra queries.
		# Falls back to a per-instance lookup for callers without the
		# annotation (e.g., single-task detail or nested assignment output).
		annotated = getattr(task, 'is_assigned_for_user', None)
		if annotated is not None:
			return bool(annotated)
		request = self.context.get('request')
		return bool(request and request.user.is_authenticated and task.assignments.filter(user=request.user).exists())

	def validate_title(self, value):
		if not value.strip():
			raise serializers.ValidationError('Title cannot be blank.')
		return value.strip()

	def validate_description(self, value):
		if not value.strip():
			raise serializers.ValidationError('Description cannot be blank.')
		return value.strip()


class TaskAssignmentSerializer(serializers.ModelSerializer):
	task = TaskSerializer(read_only=True)
	submission = serializers.SerializerMethodField()

	class Meta:
		model = TaskAssignment
		fields = ('id', 'task', 'assigned_date', 'submission')

	def get_submission(self, assignment):
		# Uses the `user_submissions` prefetch added by MyTasksView so
		# serialization performs no per-assignment submission queries.
		# Falls back to a per-instance lookup for callers without the
		# prefetch (e.g., the single-object assignment response).
		prefetched = getattr(assignment.task, 'user_submissions', None)
		if prefetched is not None:
			submission = prefetched[0] if prefetched else None
		else:
			submission = assignment.task.submissions.filter(user=assignment.user).first()
		return TaskSubmissionSerializer(submission).data if submission else None


class TaskSubmissionSerializer(serializers.ModelSerializer):
	class Meta:
		model = TaskSubmission
		fields = ('id', 'git_url', 'linkedin_url', 'note', 'status', 'feedback', 'earned_points', 'submitted_at', 'reviewed_at')
		read_only_fields = ('id', 'status', 'feedback', 'earned_points', 'submitted_at', 'reviewed_at')

	def validate_git_url(self, value):
		if not any(host in value.lower() for host in ('github.com', 'gitlab.com', 'bitbucket.org')):
			raise serializers.ValidationError('Enter a GitHub, GitLab, or Bitbucket repository URL.')
		return value

	def validate_linkedin_url(self, value):
		if 'linkedin.com' not in value.lower():
			raise serializers.ValidationError('Enter a LinkedIn profile URL.')
		return value


class TaskEvaluationSerializer(serializers.ModelSerializer):
	"""Read-only projection of a normal-task AI evaluation.

	total_score is the backend-recalculated rubric sum (max 10); best_score is
	the user's effective score for the task (MAX across their completed
	evaluations), attached by the view. Nothing here is client-writable.
	"""

	best_score = serializers.IntegerField(read_only=True)

	class Meta:
		model = TaskEvaluation
		fields = ('id', 'status', 'scores', 'total_score', 'best_score', 'summary', 'strengths', 'issues', 'suggestions', 'error_message', 'created_at', 'updated_at')
		read_only_fields = fields


class AdminSubmissionSerializer(serializers.ModelSerializer):
	task_title = serializers.CharField(source='task.title', read_only=True)
	username = serializers.CharField(source='user.username', read_only=True)

	class Meta:
		model = TaskSubmission
		fields = ('id', 'task', 'task_title', 'user', 'username', 'git_url', 'linkedin_url', 'note', 'status', 'feedback', 'submitted_at', 'reviewed_at')
		read_only_fields = ('id', 'task', 'user', 'task_title', 'username', 'git_url', 'linkedin_url', 'note', 'submitted_at', 'reviewed_at')


class SubmissionReviewSerializer(serializers.Serializer):
	status = serializers.ChoiceField(choices=(TaskSubmission.Status.APPROVED, TaskSubmission.Status.REJECTED))
	feedback = serializers.CharField(required=False, allow_blank=True)


class TaskSummarySerializer(serializers.ModelSerializer):
	tech_stack = serializers.SlugRelatedField(many=True, read_only=True, slug_field='name')

	class Meta:
		model = Task
		fields = ('id', 'title', 'description', 'due_date', 'tech_stack')


class AdminUserSerializer(serializers.ModelSerializer):
	name = serializers.CharField(source='username', read_only=True)
	assigned_task_count = serializers.SerializerMethodField()
	tech_stack = serializers.SerializerMethodField()

	class Meta:
		model = User
		fields = ('id', 'name', 'email', 'assigned_task_count', 'tech_stack')
		read_only_fields = fields

	def get_assigned_task_count(self, user):
		if hasattr(user, 'assigned_task_count_value'):
			return user.assigned_task_count_value
		return user.task_assignments.count()

	def get_tech_stack(self, user):
		# Uses the `prefetched_user_stacks` Prefetch added by the admin list
		# endpoints so serialization performs no per-user queries. Falls back
		# to a per-instance lookup for callers without the prefetch.
		stacks = getattr(user, 'prefetched_user_stacks', None)
		if stacks is None:
			stacks = user.user_tech_stacks.select_related('tech_stack')
		return [user_tech_stack.tech_stack.name for user_tech_stack in stacks]


class TechStackSerializer(serializers.ModelSerializer):
	class Meta:
		model = TechStack
		fields = ('id', 'name')


class AdminUserUpdateSerializer(serializers.Serializer):
	tech_stack = serializers.ListField(child=serializers.CharField(), required=True)

	def validate_tech_stack(self, value):
		known_names = set(TechStack.objects.filter(name__in=value).values_list('name', flat=True))
		if set(value) != known_names:
			raise serializers.ValidationError('One or more tech stacks are invalid.')
		return list(dict.fromkeys(value))

	def update(self, user, validated_data):
		stacks = TechStack.objects.filter(name__in=validated_data['tech_stack'])
		UserTechStack.objects.filter(user=user).exclude(tech_stack__in=stacks).delete()
		UserTechStack.objects.bulk_create(
			[UserTechStack(user=user, tech_stack=stack) for stack in stacks],
			ignore_conflicts=True,
		)
		return user


class AdminAssignedTaskSerializer(serializers.ModelSerializer):
	task = TaskSummarySerializer(read_only=True)

	class Meta:
		model = TaskAssignment
		fields = ('id', 'task', 'assigned_date')


class AdminUserDetailSerializer(AdminUserSerializer):
	assigned_tasks = serializers.SerializerMethodField()

	class Meta(AdminUserSerializer.Meta):
		fields = ('id', 'name', 'email', 'assigned_task_count', 'tech_stack', 'assigned_tasks')

	def get_assigned_tasks(self, user):
		# AdminAssignedTaskSerializer -> TaskSummarySerializer reads task.tech_stack;
		# prefetch it so SlugRelatedField does not query once per assignment (N+1).
		return AdminAssignedTaskSerializer(
			user.task_assignments.select_related('task').prefetch_related('task__tech_stack').order_by('-assigned_date'),
			many=True,
		).data


class AdminAssignmentSerializer(serializers.ModelSerializer):
	task = TaskSummarySerializer(read_only=True)
	user = AdminUserSerializer(read_only=True)

	class Meta:
		model = TaskAssignment
		fields = ('id', 'task', 'user', 'assigned_date')


class CodingProblemTestCaseSerializer(serializers.ModelSerializer):
	class Meta:
		model = CodingProblemTestCase
		# 'is_hidden' and 'order' are writable for admins but the user-facing
		# serializer never exposes hidden cases.
		fields = ('id', 'input', 'expected_output', 'is_hidden', 'order')


class CodingProblemAdminSerializer(serializers.ModelSerializer):
	"""Full serializer for admin CRUD; test cases are written inline.

	Hidden test cases are returned in the admin payload (admins must be
	able to review them) but user endpoints use a separate safe serializer.

	Drafts may be saved incomplete (empty/partial title, description, etc.),
	so the required text fields are optional + blank at this layer. Full
	completeness is enforced ONLY on the PUBLISH transition by
	_validate_publish below — publishing never accepts empty text fields.
	"""
	test_cases = CodingProblemTestCaseSerializer(many=True, required=False)
	created_by = serializers.StringRelatedField(read_only=True)

	class Meta:
		model = CodingProblem
		fields = (
			'id', 'title', 'description', 'difficulty', 'points', 'input_format',
			'output_format', 'constraints', 'examples', 'explanation',
			'starter_code', 'allowed_languages', 'test_cases', 'status',
			'created_by', 'created_at', 'updated_at', 'published_at',
		)
		read_only_fields = ('id', 'created_by', 'created_at', 'updated_at', 'published_at')
		extra_kwargs = {
			# These are stored in NOT-NULL text columns, so an empty string is a
			# valid DB value. Making them optional + blank lets an admin persist
			# a completely empty (or partially filled) DRAFT; _validate_publish
			# still rejects any of these being blank on the PUBLISHED transition.
			'title': {'required': False, 'allow_blank': True},
			'description': {'required': False, 'allow_blank': True},
			'difficulty': {'required': False, 'allow_blank': True},
			'input_format': {'required': False, 'allow_blank': True},
			'output_format': {'required': False, 'allow_blank': True},
			'constraints': {'required': False, 'allow_blank': True},
		}

	def create(self, validated_data):
		test_cases_data = validated_data.pop('test_cases', [])
		problem = CodingProblem.objects.create(**validated_data)
		self._save_test_cases(problem, test_cases_data)
		return problem

	def update(self, instance, validated_data):
		test_cases_data = validated_data.pop('test_cases', None)
		for attr, value in validated_data.items():
			setattr(instance, attr, value)
		# Publish transition: stamp the first time status becomes PUBLISHED.
		if instance.status == CodingProblem.Status.PUBLISHED and instance.published_at is None:
			instance.published_at = __import__('django.utils.timezone', fromlist=['now']).now()
		instance.save()
		if test_cases_data is not None:
			instance.test_cases.all().delete()
			self._save_test_cases(instance, test_cases_data)
		return instance

	def _save_test_cases(self, problem, test_cases_data):
		objs = [
			CodingProblemTestCase(
				problem=problem,
				input=case['input'],
				expected_output=case['expected_output'],
				is_hidden=case.get('is_hidden', False),
				order=case.get('order', idx),
			)
			for idx, case in enumerate(test_cases_data)
		]
		CodingProblemTestCase.objects.bulk_create(objs)

	PUBLISH_REQUIRED_FIELDS = ('title', 'description', 'difficulty', 'input_format', 'output_format', 'constraints')

	def validate(self, attrs):
		test_cases = attrs.get('test_cases', [])
		if not isinstance(test_cases, list):
			raise serializers.ValidationError({'test_cases': 'Must be a list.'})
		orders = [tc.get('order') for tc in test_cases if tc.get('order') is not None]
		if len(set(orders)) != len(orders):
			raise serializers.ValidationError({'test_cases': 'Duplicate order values are not allowed.'})
		self._validate_publish(attrs)
		return attrs

	def _validate_publish(self, attrs):
		"""A problem may be marked PUBLISHED only when fully complete.

		Runs only when the incoming (or resulting) status is PUBLISHED, so
		plain saves / drafts are never blocked. Guarantees that a problem can
		never be published without the essential fields and without at least
		one public and one hidden test case.
		"""
		new_status = attrs.get('status')
		target_status = new_status if new_status is not None else (self.instance.status if self.instance else None)
		if target_status != CodingProblem.Status.PUBLISHED:
			return

		for field in self.PUBLISH_REQUIRED_FIELDS:
			value = attrs.get(field, getattr(self.instance, field, None) if self.instance else None)
			if not str(value or '').strip():
				raise serializers.ValidationError({field: 'This field is required before publishing.'})

		if 'test_cases' in attrs:
			public = [tc for tc in attrs['test_cases'] if not tc.get('is_hidden')]
			hidden = [tc for tc in attrs['test_cases'] if tc.get('is_hidden')]
		else:
			public = list(self.instance.test_cases.filter(is_hidden=False)) if self.instance else []
			hidden = list(self.instance.test_cases.filter(is_hidden=True)) if self.instance else []
		if len(public) < 1:
			raise serializers.ValidationError({'test_cases': 'At least one public test case is required before publishing.'})
		if len(hidden) < 1:
			raise serializers.ValidationError({'test_cases': 'At least one hidden test case is required before publishing.'})


class CodingProblemUserSerializer(serializers.ModelSerializer):
	"""Public serializer: never exposes hidden test cases."""
	test_cases = serializers.SerializerMethodField()
	created_by = serializers.StringRelatedField(read_only=True)

	class Meta:
		model = CodingProblem
		fields = (
			'id', 'title', 'description', 'difficulty', 'points', 'input_format',
			'output_format', 'constraints', 'examples', 'explanation',
			'starter_code', 'allowed_languages', 'test_cases', 'status',
			'created_by', 'created_at', 'updated_at', 'published_at',
		)

	def get_test_cases(self, problem):
		# Only public cases (and without the is_hidden/order internals) leak
		# to normal users.
		public = problem.test_cases.filter(is_hidden=False).order_by('order')
		return [{'id': tc.id, 'input': tc.input, 'expected_output': tc.expected_output} for tc in public]


class CodeSubmissionCreateSerializer(serializers.ModelSerializer):
	"""Input validation for creating a submission.

	The view supplies the user and the (published) problem via context;
	neither is client-writable. Execution status/metrics are NEVER writable
	from here — a new submission always starts as PENDING.
	"""

	class Meta:
		model = CodeSubmission
		fields = ('language', 'source_code')

	# DRF's CharField strips surrounding whitespace by default, which would
	# silently corrupt submitted source code. Keep it byte-for-byte.
	source_code = serializers.CharField(trim_whitespace=False, style={'base_template': 'textarea.html'})

	def validate_language(self, value):
		language = (value or '').strip()
		if not language:
			raise serializers.ValidationError('A programming language is required.')
		problem = self.context.get('problem')
		if problem is not None and not is_language_allowed_for_problem(problem, language):
			raise serializers.ValidationError(
				f"'{language}' is not supported for this problem. Allowed: {', '.join(problem.allowed_languages or [])}."
			)
		return language

	def validate_source_code(self, value):
		source = value or ''
		if not source.strip():
			raise serializers.ValidationError('Source code cannot be empty.')
		return source


class CodeSubmissionUserSerializer(serializers.ModelSerializer):
	"""Read serializer for the owning user's own submissions.

	Hidden test-case data is never part of this payload. `test_summary`
	reports pass/fail per executed test, with details only for PUBLIC tests.
	"""
	status_label = serializers.SerializerMethodField()
	problem_title = serializers.CharField(source='problem.title', read_only=True)
	test_summary = serializers.SerializerMethodField()
	earned_points = serializers.SerializerMethodField()

	class Meta:
		model = CodeSubmission
		fields = (
			'id', 'problem', 'problem_title', 'language', 'source_code',
			'status', 'status_label', 'verdict', 'mode', 'test_summary',
			'execution_time', 'memory_used',
			'passed_tests', 'total_tests', 'score', 'feedback',
			'created_at', 'updated_at', 'completed_at', 'earned_points',
		)
		read_only_fields = fields

	def get_earned_points(self, submission):
		return points_earned_for_submission(submission)

	def get_status_label(self, submission):
		return submission.get_status_display()

	def get_test_summary(self, submission):
		"""Per-test outcomes attached by the execution service (if any)."""
		outcomes = getattr(submission, '_public_test_outcomes', None)
		if not outcomes:
			return []
		return [
			{
				'index': outcome.index,
				'passed': outcome.passed,
				# Details exist for public cases only.
				'expected_output': outcome.expected_output,
				'actual_output': outcome.actual_output,
			}
			for outcome in outcomes
		]


class AdminCodeSubmissionSerializer(CodeSubmissionUserSerializer):
	"""Admin inspection serializer: adds user context.

	Still never exposes hidden test-case input/expected data — this
	serializes CodeSubmission rows only.
	"""
	user = UserSerializer(read_only=True)

	class Meta(CodeSubmissionUserSerializer.Meta):
		fields = ('user',) + CodeSubmissionUserSerializer.Meta.fields


class SubmissionAnalysisSerializer(serializers.ModelSerializer):
	"""Read serializer for the AI analysis stored against a submission.

	Purely qualitative coaching output — never a pass/fail verdict. The
	judge result shown alongside it comes from CodeSubmission itself.
	"""

	class Meta:
		model = SubmissionAnalysis
		fields = (
			'summary', 'correctness', 'bugs', 'code_quality',
			'time_complexity', 'space_complexity', 'edge_cases',
			'suggestions', 'created_at', 'updated_at',
		)
		read_only_fields = fields


class NotificationPreferenceSerializer(serializers.ModelSerializer):
	"""Reads/updates the current user's notification preferences."""

	class Meta:
		model = NotificationPreference
		fields = ('task_assignments', 'submission_reviews', 'task_deadlines', 'admin_announcements', 'updated_at')
		read_only_fields = ('updated_at',)


class NotificationSerializer(serializers.ModelSerializer):
	"""Read-only notification payload for the recipient.

	recipient/event_key are never exposed or writable: notifications are
	created exclusively by server-side workflow events.
	"""

	class Meta:
		model = Notification
		fields = ('id', 'title', 'message', 'url', 'is_read', 'created_at')
		read_only_fields = fields
