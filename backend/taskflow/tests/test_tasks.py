from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TaskSubmission, TechStack

User = get_user_model()


class TaskCrudTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42')
		self.user = User.objects.create_user(username='member', password='StrongPassword!42')

	def authenticate(self, user):
		token = Token.objects.create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_admin_can_create_edit_delete_and_view_tasks(self):
		self.authenticate(self.admin)
		create_response = self.client.post('/api/tasks/', {
			'title': 'Task A',
			'description': 'First task',
			'due_date': '2026-09-01',
		}, format='json')
		self.assertEqual(create_response.status_code, 201)
		task_id = create_response.data['id']
		self.assertEqual(self.client.get('/api/tasks/').status_code, 200)
		self.assertEqual(self.client.get(f'/api/tasks/{task_id}/').status_code, 200)

		edit_response = self.client.patch(f'/api/tasks/{task_id}/', {'title': 'Updated task'}, format='json')
		self.assertEqual(edit_response.status_code, 200)
		self.assertEqual(edit_response.data['title'], 'Updated task')
		self.assertEqual(self.client.delete(f'/api/tasks/{task_id}/').status_code, 204)
		self.assertFalse(Task.objects.filter(pk=task_id).exists())

	def test_user_can_view_but_cannot_create_edit_or_delete(self):
		task = Task.objects.create(title='Task A', description='Visible task')
		self.authenticate(self.user)
		self.assertEqual(self.client.get('/api/tasks/').status_code, 200)
		self.assertEqual(self.client.get(f'/api/tasks/{task.id}/').status_code, 200)
		self.assertEqual(self.client.post('/api/tasks/', {'title': 'Nope', 'description': 'Nope'}, format='json').status_code, 403)
		self.assertEqual(self.client.patch(f'/api/tasks/{task.id}/', {'title': 'Nope'}, format='json').status_code, 403)
		self.assertEqual(self.client.delete(f'/api/tasks/{task.id}/').status_code, 403)
		self.assertEqual(Task.objects.get(pk=task.id).title, 'Task A')

	def test_unauthenticated_requests_are_rejected(self):
		self.assertEqual(self.client.get('/api/tasks/').status_code, 401)
		self.assertEqual(self.client.post('/api/tasks/', {}, format='json').status_code, 401)

	def test_invalid_data_is_rejected_and_due_date_is_optional(self):
		self.authenticate(self.admin)
		invalid_response = self.client.post('/api/tasks/', {'title': ' ', 'description': ' '}, format='json')
		self.assertEqual(invalid_response.status_code, 400)
		valid_response = self.client.post('/api/tasks/', {'title': 'No due date', 'description': 'Optional date'}, format='json')
		self.assertEqual(valid_response.status_code, 201)
		self.assertIsNone(valid_response.data['due_date'])

	# ── tech_stack field tests ──────────────────────────────────────────────

	def test_task_serializer_includes_tech_stack_field(self):
		"""GET /api/tasks/ must return a tech_stack list on every task."""
		Task.objects.create(title='Plain task', description='No stacks')
		self.authenticate(self.user)
		response = self.client.get('/api/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertGreater(len(response.data['results']), 0)
		for task in response.data['results']:
			self.assertIn('tech_stack', task)
			self.assertIsInstance(task['tech_stack'], list)

	def test_task_tech_stack_returns_assigned_names(self):
		"""Tasks that have TechStack objects linked return their names in the API."""
		python, _ = TechStack.objects.get_or_create(name='Python')
		django, _ = TechStack.objects.get_or_create(name='Django')
		task = Task.objects.create(title='Backend task', description='Python + Django')
		task.tech_stack.set([python, django])

		self.authenticate(self.user)
		response = self.client.get(f'/api/tasks/{task.id}/')
		self.assertEqual(response.status_code, 200)
		self.assertCountEqual(response.data['tech_stack'], ['Python', 'Django'])

	def test_task_tech_stack_is_empty_list_by_default(self):
		"""Newly created tasks have an empty tech_stack list — not null."""
		task = Task.objects.create(title='No stack task', description='Untagged')
		self.authenticate(self.user)
		response = self.client.get(f'/api/tasks/{task.id}/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['tech_stack'], [])

	def test_tech_stacks_endpoint_is_accessible_to_normal_users(self):
		"""GET /api/tasks/tech-stacks/ must be accessible to authenticated normal users."""
		TechStack.objects.get_or_create(name='React')
		TechStack.objects.get_or_create(name='TypeScript')
		self.authenticate(self.user)
		response = self.client.get('/api/tasks/tech-stacks/')
		self.assertEqual(response.status_code, 200)
		names = [item['name'] for item in response.data]
		self.assertIn('React', names)
		self.assertIn('TypeScript', names)

	def test_task_list_does_not_query_assignments_per_task(self):
		"""GET /api/tasks/ must not issue one assignment-existence query per task.

		The is_assigned flag is computed by a single Exists() annotation on the
		list queryset instead of task.assignments.filter(...).exists() during
		serialization (N+1 prevention).
		"""
		tasks = [
			Task.objects.create(title=f'Task {index}', description='Bulk')
			for index in range(8)
		]
		TaskAssignment.objects.create(task=tasks[0], user=self.user)
		self.authenticate(self.user)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/tasks/')
		self.assertEqual(response.status_code, 200)
		results = response.data['results']
		self.assertEqual(len(results), len(tasks))
		assigned_flags = {item['id']: item['is_assigned'] for item in results}
		self.assertTrue(assigned_flags[tasks[0].id])
		self.assertFalse(any(assigned_flags[task.id] for task in tasks[1:]))
		# The ONLY queries allowed to touch taskflow_taskassignment are:
		#   1. the annotated EXISTS() inside the task-list query
		#   2. the paginator's COUNT(*) over the same annotated queryset
		# Any standalone per-task assignment lookup means the per-task N+1
		# has regressed.
		assignment_queries = [
			query['sql'] for query in captured.captured_queries
			if 'taskflow_taskassignment' in query['sql']
		]
		self.assertLessEqual(len(assignment_queries), 2)
		self.assertTrue(any('EXISTS' in sql for sql in assignment_queries))
		self.assertFalse(any(
			sql.strip().upper().startswith('SELECT COUNT') and 'EXISTS' not in sql.upper()
			for sql in assignment_queries
		))

	def test_my_tasks_does_not_query_submissions_per_assignment(self):
		"""GET /api/my/tasks/ must prefetch submissions, not query per assignment.

		The submission is fetched through a single Prefetch() filtered to the
		authenticated user, so exactly ONE captured query may touch
		taskflow_tasksubmission regardless of assignment count.
		"""
		tasks = [
			Task.objects.create(title=f'My task {index}', description='Owned')
			for index in range(6)
		]
		for index, task in enumerate(tasks):
			TaskAssignment.objects.create(task=task, user=self.user)
		# Own submissions on some tasks; none on others.
		TaskSubmission.objects.create(task=tasks[0], user=self.user, git_url='https://github.com/me/repo0', linkedin_url='https://linkedin.com/in/me')
		TaskSubmission.objects.create(task=tasks[2], user=self.user, git_url='https://github.com/me/repo2', linkedin_url='https://linkedin.com/in/me')
		# Another member's submissions on tasks also assigned to self.user —
		# these must NEVER appear in self.user's response.
		other = User.objects.create_user(username='othermember', password='StrongPassword!42')
		TaskAssignment.objects.create(task=tasks[1], user=other)
		TaskSubmission.objects.create(task=tasks[1], user=other, git_url='https://github.com/other/repo1', linkedin_url='https://linkedin.com/in/other')

		self.authenticate(self.user)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		results = response.data['results']
		self.assertEqual(len(results), len(tasks))

		submissions_by_task = {
			item['task']['id']: item['submission'] for item in results
		}
		# Correct own submission returned where it exists.
		self.assertIsNotNone(submissions_by_task[tasks[0].id])
		self.assertEqual(submissions_by_task[tasks[0].id]['git_url'], 'https://github.com/me/repo0')
		self.assertIsNotNone(submissions_by_task[tasks[2].id])
		# No submission of one's own → null.
		self.assertIsNone(submissions_by_task[tasks[3].id])
		# Another user's submission is never leaked.
		self.assertIsNone(submissions_by_task[tasks[1].id])

		# Exactly ONE query may touch taskflow_tasksubmission (the prefetch);
		# more means the per-assignment N+1 has regressed.
		submission_queries = [
			query['sql'] for query in captured.captured_queries
			if 'taskflow_tasksubmission' in query['sql']
		]
		self.assertEqual(len(submission_queries), 1)
		self.assertIn('user_id', submission_queries[0])

	def test_tech_stacks_endpoint_requires_authentication(self):
		"""GET /api/tasks/tech-stacks/ must reject unauthenticated requests."""
		self.assertEqual(self.client.get('/api/tasks/tech-stacks/').status_code, 401)