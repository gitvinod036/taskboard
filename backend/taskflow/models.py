from django.db import models
from django.conf import settings


# Authoritative difficulty → points mapping for coding problems. Kept in one
# backend location so every view/component derives the same value. Points are
# computed from difficulty — there is no manually-assigned points field.
DIFFICULTY_POINTS = {
    'EASY': 10,
    'MEDIUM': 20,
    'HARD': 30,
}


class CodingProblem(models.Model):
	"""A coding problem that can be reviewed, drafted, and published.

	The AI-generation pipeline writes into DRAFT; only an explicit admin
	Publish action (PATCH status -> PUBLISHED) makes a problem visible to
	normal users. Hidden test cases are never returned by user endpoints.
	"""

	class Status(models.TextChoices):
		DRAFT = 'DRAFT', 'Draft'
		PUBLISHED = 'PUBLISHED', 'Published'

	title = models.CharField(max_length=200)
	description = models.TextField()
	difficulty = models.CharField(max_length=20, choices=[('EASY', 'Easy'), ('MEDIUM', 'Medium'), ('HARD', 'Hard')])
	input_format = models.TextField()
	output_format = models.TextField()
	constraints = models.TextField()
	explanation = models.TextField(blank=True)
	starter_code = models.JSONField(default=dict, blank=True)
	allowed_languages = models.JSONField(default=list, blank=True)
	examples = models.JSONField(default=list, blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
	created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_coding_problems')
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	published_at = models.DateTimeField(null=True, blank=True)

	class Meta:
		ordering = ('-created_at', 'id')
		indexes = [models.Index(fields=('status',))]

	def __str__(self):
		return self.title

	@property
	def points(self):
		"""Reward value derived from difficulty (EASY 10, MEDIUM 20, HARD 30)."""
		return DIFFICULTY_POINTS.get(self.difficulty, 0)


class CodingProblemTestCase(models.Model):
	"""A public or hidden test case for a coding problem."""
	problem = models.ForeignKey(CodingProblem, on_delete=models.CASCADE, related_name='test_cases')
	input = models.TextField()
	expected_output = models.TextField()
	is_hidden = models.BooleanField(default=False)
	order = models.PositiveIntegerField()
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('order', 'id')
		constraints = [models.UniqueConstraint(fields=('problem', 'order'), name='unique_problem_testcase_order')]

	def __str__(self):
		return f"# {self.order} ({'hidden' if self.is_hidden else 'public'})"


class CodeSubmission(models.Model):
	"""A user's source-code submission for a coding problem.

	PHASE 3: submissions are executed inside an isolated Docker sandbox by
	taskflow.execution. Nothing here runs user code on the Django host, and
	clients can never write status/verdict/metrics directly — those are set
	only by the execution service from observed results.
	"""

	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Queued for execution'
		RUNNING = 'RUNNING', 'Running'
		ACCEPTED = 'ACCEPTED', 'Accepted'
		WRONG_ANSWER = 'WRONG_ANSWER', 'Wrong Answer'
		COMPILATION_ERROR = 'COMPILATION_ERROR', 'Compilation Error'
		RUNTIME_ERROR = 'RUNTIME_ERROR', 'Runtime Error'
		TIME_LIMIT_EXCEEDED = 'TIME_LIMIT_EXCEEDED', 'Time Limit Exceeded'
		MEMORY_LIMIT_EXCEEDED = 'MEMORY_LIMIT_EXCEEDED', 'Memory Limit Exceeded'
		SYSTEM_ERROR = 'SYSTEM_ERROR', 'System Error'

	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='code_submissions')
	problem = models.ForeignKey(CodingProblem, on_delete=models.CASCADE, related_name='submissions')
	language = models.CharField(max_length=30)
	source_code = models.TextField()
	status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)

	# RUN = "Run Code" against public tests only; SUBMIT = full judging
	# (public + hidden). Set by the server, never by the client.
	class Mode(models.TextChoices):
		RUN = 'RUN', 'Run (public tests)'
		SUBMIT = 'SUBMIT', 'Submit (public + hidden tests)'

	mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SUBMIT)
	verdict = models.CharField(max_length=30, choices=Status.choices, null=True, blank=True)
	completed_at = models.DateTimeField(null=True, blank=True)

	# Populated by the Phase 3 execution service. Kept nullable so a queued
	# submission never carries invented values.
	execution_time = models.FloatField(null=True, blank=True)
	memory_used = models.FloatField(null=True, blank=True)
	passed_tests = models.PositiveIntegerField(null=True, blank=True)
	total_tests = models.PositiveIntegerField(null=True, blank=True)
	score = models.FloatField(null=True, blank=True)
	feedback = models.TextField(blank=True)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ('-created_at', '-id')
		indexes = [
			models.Index(fields=('user', 'problem')),
			models.Index(fields=('status',)),
			models.Index(fields=('problem',)),
		]

	def __str__(self):
		return f'#{self.pk} {self.user} -> {self.problem_id} [{self.language}] {self.status}'


class SubmissionAnalysis(models.Model):
	"""AI-generated qualitative feedback for a completed coding submission.

	The judge (taskflow.execution) remains the only source of truth for
	pass/fail and metrics; this stores Gemini's additional coaching only.
	One row per submission: regeneration updates the existing row in place
	instead of creating duplicates. Never displayed as a verdict.
	"""

	submission = models.OneToOneField(CodeSubmission, on_delete=models.CASCADE, related_name='ai_analysis')
	summary = models.TextField()
	correctness = models.TextField()
	bugs = models.JSONField(default=list, blank=True)
	code_quality = models.TextField()
	time_complexity = models.CharField(max_length=200, blank=True)
	space_complexity = models.CharField(max_length=200, blank=True)
	edge_cases = models.JSONField(default=list, blank=True)
	suggestions = models.JSONField(default=list, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	def __str__(self):
		return f'AI analysis for submission #{self.submission_id}'



class Task(models.Model):
	# Difficulty drives a derived reward via the single authoritative
	# DIFFICULTY_POINTS mapping (shared with CodingProblem). EASY is the safe
	# default so pre-existing tasks created without difficulty stay valid.
	class Difficulty(models.TextChoices):
		EASY = 'EASY', 'Easy'
		MEDIUM = 'MEDIUM', 'Medium'
		HARD = 'HARD', 'Hard'

	title = models.CharField(max_length=200)
	description = models.TextField()
	difficulty = models.CharField(
		max_length=20, choices=Difficulty.choices, default=Difficulty.EASY,
		help_text='Primary difficulty level of the task.',
	)
	due_date = models.DateField(blank=True, null=True)
	tech_stack = models.ManyToManyField('TechStack', blank=True, related_name='tasks')

	class Meta:
		ordering = ('due_date', 'id')

	def __str__(self):
		return self.title

	@property
	def points(self):
		"""Reward value derived from difficulty (EASY 10, MEDIUM 20, HARD 30)."""
		return DIFFICULTY_POINTS.get(self.difficulty, 0)


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
	# Server-set reward granted exactly once when the submission is APPROVED.
	# Never writable by the client: derived from Task.points / DIFFICULTY_POINTS
	# at award time. Legacy fallback contribution — once a submission has a
	# completed AI evaluation, the leaderboard uses the evaluation score.
	earned_points = models.PositiveIntegerField(default=0)
	submitted_at = models.DateTimeField(auto_now_add=True)
	reviewed_at = models.DateTimeField(null=True, blank=True)
	reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_task_submissions')

	class Meta:
		# NOTE: no unique (task, user) constraint — users may RESUBMIT improved
		# versions of a rejected task, so a (user, task) pair can own multiple
		# historical attempts. The newest attempt is the authoritative one.
		indexes = [models.Index(fields=('status',)), models.Index(fields=('user',)), models.Index(fields=('task',)), models.Index(fields=('user', 'task'))]


class TaskEvaluation(models.Model):
	"""AI evaluation of an APPROVED normal-task submission, on a fixed 10-point rubric.

	The judge/reviewer remains the source of truth for acceptance: only
	APPROVED submissions may be evaluated, and a rejected submission can
	never receive a score. The backend recalculates total_score from the
	individual rubric categories — an AI-supplied total is never trusted —
	and nothing here writes leaderboard points directly; the leaderboard
	derives contributions from these rows at read time. Regeneration
	updates the existing row in place (one row per submission).
	"""

	class Status(models.TextChoices):
		PENDING = 'PENDING', 'Pending evaluation'
		COMPLETED = 'COMPLETED', 'Evaluation complete'
		FAILED = 'FAILED', 'Evaluation failed (retry allowed)'

	submission = models.OneToOneField(TaskSubmission, on_delete=models.CASCADE, related_name='ai_evaluation')
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	# Rubric category scores; total_score is always the server-computed sum.
	scores = models.JSONField(default=dict, blank=True)
	total_score = models.PositiveSmallIntegerField(default=0)
	summary = models.TextField(blank=True)
	strengths = models.JSONField(default=list, blank=True)
	issues = models.JSONField(default=list, blank=True)
	suggestions = models.JSONField(default=list, blank=True)
	error_message = models.CharField(max_length=200, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		indexes = [models.Index(fields=('status',))]

	def __str__(self):
		return f'AI evaluation for submission #{self.submission_id} [{self.status}] {self.total_score}/10'


class NotificationPreference(models.Model):
	"""Per-user notification preferences.

	Created lazily with all-True defaults on first read/update so existing
	users keep working without a data migration.
	"""

	user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_preference')
	task_assignments = models.BooleanField(default=True, help_text='Notify when a task is assigned to me.')
	submission_reviews = models.BooleanField(default=True, help_text='Notify when my submission is reviewed.')
	task_deadlines = models.BooleanField(default=True, help_text='Notify about task deadlines and overdue tasks.')
	admin_announcements = models.BooleanField(default=True, help_text='Receive general/admin announcements.')
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name_plural = 'notification preferences'

	def __str__(self):
		return f'Notification preferences for {self.user}'


class Notification(models.Model):
	"""An in-app notification for one recipient.

	Created ONLY by server-side workflow events (task published, submission
	received, review outcome, AI evaluation) — never from client input.
	Idempotent per event: (recipient, event_key) is unique, so replaying the
	same backend event (repeated API call, retry, re-review) can never create
	duplicate rows.
	"""

	recipient = models.ForeignKey(
		settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications',
	)
	title = models.CharField(max_length=200)
	message = models.TextField()
	# Frontend path the notification opens (e.g. /my-tasks, /admin/submissions).
	url = models.CharField(max_length=300, blank=True)
	# Deterministic per-event key, e.g. 'task-published-12-user-3'.
	event_key = models.CharField(max_length=150)
	is_read = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ('-created_at', '-id')
		constraints = [
			models.UniqueConstraint(fields=('recipient', 'event_key'), name='unique_recipient_notification_event'),
		]
		indexes = [models.Index(fields=('recipient', 'is_read'))]

	def __str__(self):
		return f'Notification for {self.recipient}: {self.title}'
