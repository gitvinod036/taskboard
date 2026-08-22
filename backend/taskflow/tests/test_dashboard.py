from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TaskSubmission, TechStack

User = get_user_model()


class AdminDashboardTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.today = timezone.localdate()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		self.user1 = User.objects.create_user(username='user1', password='StrongPassword!42', email='one@example.com')
		self.user2 = User.objects.create_user(username='user2', password='StrongPassword!42', email='two@example.com')
		self.inactive = User.objects.create_user(username='user3', password='StrongPassword!42', email='three@example.com', is_active=False)
		self.django = TechStack.objects.get(name='Django')
		self.react = TechStack.objects.get(name='React')
		self.overdue_task = Task.objects.create(title='Overdue task', description='A', due_date=self.today - timedelta(days=3))
		self.future_task = Task.objects.create(title='Future task', description='B', due_date=self.today + timedelta(days=3))
		self.undated_task = Task.objects.create(title='Undated task', description='C')
		self.unassigned_task = Task.objects.create(title='Unassigned task', description='D')
		self.overdue_task.tech_stack.add(self.django)
		self.future_task.tech_stack.add(self.django, self.react)

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def submit(self, user, task, status, reviewed_at=None):
		return TaskSubmission.objects.create(
			user=user,
			task=task,
			git_url='https://github.com/example/repo',
			linkedin_url='https://www.linkedin.com/in/example',
			status=status,
			reviewed_at=reviewed_at,
			reviewed_by=self.admin if reviewed_at else None,
		)

	def dashboard(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/dashboard/')
		self.assertEqual(response.status_code, 200)
		return response.data

	def test_admin_can_access_dashboard(self):
		data = self.dashboard()
		self.assertEqual(
			set(data),
			{'generated_at', 'summary', 'status_distribution', 'technology_distribution', 'completion_trend', 'top_users', 'overdue_tasks'},
		)

	def test_normal_user_is_forbidden_and_anonymous_is_unauthorized(self):
		self.authenticate(self.user1)
		self.assertEqual(self.client.get('/api/admin/dashboard/').status_code, 403)
		self.client.credentials()
		self.assertEqual(self.client.get('/api/admin/dashboard/').status_code, 401)

	def test_summary_counts_match_the_database(self):
		TaskAssignment.objects.create(user=self.user1, task=self.overdue_task)
		TaskAssignment.objects.create(user=self.user1, task=self.future_task)
		TaskAssignment.objects.create(user=self.user2, task=self.undated_task)
		self.submit(self.user1, self.future_task, TaskSubmission.Status.APPROVED, reviewed_at=timezone.now())
		self.submit(self.user2, self.undated_task, TaskSubmission.Status.PENDING)

		summary = self.dashboard()['summary']
		self.assertEqual(summary['total_tasks'], 4)
		self.assertEqual(summary['completed'], 1)
		self.assertEqual(summary['pending_review'], 1)
		self.assertEqual(summary['in_progress'], 2)
		self.assertEqual(summary['overdue'], 1)
		self.assertEqual(summary['total_users'], 3)
		self.assertEqual(summary['active_users'], 2)

	def test_pending_submissions_are_counted_and_never_treated_as_completed(self):
		TaskAssignment.objects.create(user=self.user1, task=self.undated_task)
		TaskAssignment.objects.create(user=self.user2, task=self.undated_task)
		self.submit(self.user1, self.undated_task, TaskSubmission.Status.PENDING)
		self.submit(self.user2, self.undated_task, TaskSubmission.Status.PENDING)

		data = self.dashboard()
		self.assertEqual(data['summary']['pending_review'], 2)
		self.assertEqual(data['summary']['completed'], 0)
		self.assertEqual(data['summary']['in_progress'], 2)
		self.assertEqual(data['status_distribution']['assignments']['pending_review'], 2)
		self.assertEqual(data['status_distribution']['assignments']['without_submission'], 0)

	def test_approved_submissions_drive_completion_counts_and_trend(self):
		TaskAssignment.objects.create(user=self.user1, task=self.undated_task)
		TaskAssignment.objects.create(user=self.user2, task=self.undated_task)
		self.submit(self.user1, self.undated_task, TaskSubmission.Status.APPROVED, reviewed_at=timezone.now())
		self.submit(self.user2, self.undated_task, TaskSubmission.Status.APPROVED, reviewed_at=timezone.now() - timedelta(days=60))

		data = self.dashboard()
		self.assertEqual(data['summary']['completed'], 2)
		self.assertEqual(data['summary']['in_progress'], 0)
		trend = data['completion_trend']
		self.assertEqual(len(trend), 30)
		self.assertEqual(trend[-1]['date'], self.today)
		self.assertEqual(trend[-1]['completed'], 1)
		self.assertEqual(sum(point['completed'] for point in trend), 1)

	def test_in_progress_ignores_approved_work_and_counts_rejected_work(self):
		TaskAssignment.objects.create(user=self.user1, task=self.undated_task)
		TaskAssignment.objects.create(user=self.user1, task=self.future_task)
		TaskAssignment.objects.create(user=self.user2, task=self.future_task)
		self.submit(self.user1, self.undated_task, TaskSubmission.Status.REJECTED, reviewed_at=timezone.now())
		self.submit(self.user1, self.future_task, TaskSubmission.Status.APPROVED, reviewed_at=timezone.now())

		data = self.dashboard()
		self.assertEqual(data['summary']['in_progress'], 2)
		self.assertEqual(data['status_distribution']['assignments']['total'], 3)
		self.assertEqual(data['status_distribution']['assignments']['rejected'], 1)
		self.assertEqual(data['status_distribution']['assignments']['without_submission'], 1)
		self.assertEqual(data['status_distribution']['tasks'], {'total': 4, 'assigned': 2, 'unassigned': 2})

	def test_overdue_only_counts_past_due_dates_without_an_approved_submission(self):
		TaskAssignment.objects.create(user=self.user1, task=self.overdue_task)
		TaskAssignment.objects.create(user=self.user2, task=self.overdue_task)
		TaskAssignment.objects.create(user=self.user1, task=self.future_task)
		TaskAssignment.objects.create(user=self.user1, task=self.undated_task)
		self.submit(self.user2, self.overdue_task, TaskSubmission.Status.APPROVED, reviewed_at=timezone.now())

		data = self.dashboard()
		self.assertEqual(data['summary']['overdue'], 1)
		self.assertEqual(data['overdue_tasks'], [{
			'task_id': self.overdue_task.id,
			'title': 'Overdue task',
			'due_date': self.overdue_task.due_date,
			'user': {'id': self.user1.id, 'name': 'user1'},
			'submission_status': None,
		}])

	def test_technology_distribution_counts_tasks_per_stack(self):
		distribution = self.dashboard()['technology_distribution']
		self.assertEqual(len(distribution), TechStack.objects.count())
		self.assertEqual(
			[(row['name'], row['task_count']) for row in distribution[:2]],
			[('Django', 2), ('React', 1)],
		)
		self.assertTrue(all(row['task_count'] == 0 for row in distribution[2:]))

	def test_top_users_are_ranked_without_exposing_sensitive_data(self):
		TaskAssignment.objects.create(user=self.user1, task=self.overdue_task)
		TaskAssignment.objects.create(user=self.user1, task=self.future_task)
		TaskAssignment.objects.create(user=self.user2, task=self.undated_task)
		self.submit(self.user2, self.undated_task, TaskSubmission.Status.APPROVED, reviewed_at=timezone.now())

		data = self.dashboard()
		top_users = data['top_users']
		self.assertEqual(top_users[0], {'id': self.user2.id, 'name': 'user2', 'assigned_count': 1, 'completed_count': 1})
		self.assertEqual(top_users[1], {'id': self.user1.id, 'name': 'user1', 'assigned_count': 2, 'completed_count': 0})
		self.assertNotIn(self.admin.id, [row['id'] for row in top_users])
		for row in top_users:
			self.assertEqual(set(row), {'id', 'name', 'assigned_count', 'completed_count'})
		payload = str(data)
		for secret in ('password', 'one@example.com', 'is_staff', 'token'):
			self.assertNotIn(secret, payload)
