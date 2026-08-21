from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import Task, TaskAssignment, TaskSubmission, TechStack, UserTechStack

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
	tech_stack = serializers.SlugRelatedField(
		many=True,
		read_only=True,
		slug_field='name',
	)

	class Meta:
		model = Task
		fields = ('id', 'title', 'description', 'due_date', 'is_assigned', 'tech_stack')
		read_only_fields = ('is_assigned', 'tech_stack')

	def get_is_assigned(self, task):
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
		submission = assignment.task.submissions.filter(user=assignment.user).first()
		return TaskSubmissionSerializer(submission).data if submission else None


class TaskSubmissionSerializer(serializers.ModelSerializer):
	class Meta:
		model = TaskSubmission
		fields = ('id', 'git_url', 'linkedin_url', 'note', 'status', 'feedback', 'submitted_at', 'reviewed_at')
		read_only_fields = ('id', 'status', 'feedback', 'submitted_at', 'reviewed_at')

	def validate_git_url(self, value):
		if not any(host in value.lower() for host in ('github.com', 'gitlab.com', 'bitbucket.org')):
			raise serializers.ValidationError('Enter a GitHub, GitLab, or Bitbucket repository URL.')
		return value

	def validate_linkedin_url(self, value):
		if 'linkedin.com' not in value.lower():
			raise serializers.ValidationError('Enter a LinkedIn profile URL.')
		return value


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
	class Meta:
		model = Task
		fields = ('id', 'title', 'description', 'due_date')


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
		return list(user.user_tech_stacks.select_related('tech_stack').values_list('tech_stack__name', flat=True))


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
		return AdminAssignedTaskSerializer(user.task_assignments.select_related('task').order_by('-assigned_date'), many=True).data


class AdminAssignmentSerializer(serializers.ModelSerializer):
	task = TaskSummarySerializer(read_only=True)
	user = AdminUserSerializer(read_only=True)

	class Meta:
		model = TaskAssignment
		fields = ('id', 'task', 'user', 'assigned_date')
