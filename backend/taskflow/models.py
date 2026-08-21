from django.db import models
from django.conf import settings


class Task(models.Model):
	title = models.CharField(max_length=200)
	description = models.TextField()
	due_date = models.DateField(blank=True, null=True)
	tech_stack = models.ManyToManyField('TechStack', blank=True, related_name='tasks')

	class Meta:
		ordering = ('due_date', 'id')

	def __str__(self):
		return self.title


class TechStack(models.Model):
	name = models.CharField(max_length=100, unique=True)

	class Meta:
		ordering = ('name',)

	def __str__(self):
		return self.name


class UserTechStack(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='user_tech_stacks')
	tech_stack = models.ForeignKey(TechStack, on_delete=models.CASCADE, related_name='user_tech_stacks')

	class Meta:
		constraints = [models.UniqueConstraint(fields=('user', 'tech_stack'), name='unique_user_tech_stack')]
		indexes = [models.Index(fields=('user',)), models.Index(fields=('tech_stack',))]


class GoogleIdentity(models.Model):
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='google_identities')
	subject = models.CharField(max_length=255, unique=True)
	email = models.EmailField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=('user', 'email'), name='unique_user_google_email')]


class GoogleLoginCode(models.Model):
	code_hash = models.CharField(max_length=64, unique=True)
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	created_at = models.DateTimeField(auto_now_add=True)
	used_at = models.DateTimeField(null=True, blank=True)


class TaskAssignment(models.Model):
	task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='assignments')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_assignments')
	assigned_date = models.DateTimeField(auto_now_add=True)

	class Meta:
		constraints = [models.UniqueConstraint(fields=('task', 'user'), name='unique_task_user_assignment')]
		indexes = [models.Index(fields=('task',)), models.Index(fields=('user',))]


class TaskSubmission(models.Model):
	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Pending Review'
		APPROVED = 'APPROVED', 'Approved'
		REJECTED = 'REJECTED', 'Rejected'

	task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='submissions')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='task_submissions')
	git_url = models.URLField(max_length=500)
	linkedin_url = models.URLField(max_length=500)
	note = models.TextField(blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	feedback = models.TextField(blank=True)
	submitted_at = models.DateTimeField(auto_now_add=True)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_task_submissions')

	class Meta:
		constraints = [models.UniqueConstraint(fields=('task', 'user'), name='unique_task_submission_user')]
		indexes = [models.Index(fields=('status',)), models.Index(fields=('user',)), models.Index(fields=('task',))]
