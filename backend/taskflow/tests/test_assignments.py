from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TechStack

User = get_user_model()


class TaskAssignmentTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.task = Task.objects.create(title='Task A', description='Shared task', due_date='2026-09-01')
		self.user1 = User.objects.create_user(username='user1', password='StrongPassword!42')
		self.user2 = User.objects.create_user(username='user2', password='StrongPassword!42')
		self.user3 = User.objects.create_user(username='user3', password='StrongPassword!42')
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42')

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_user_can_assign_and_unassign_own_task(self):
		self.authenticate(self.user1)
		assign_response = self.client.post(f'/api/tasks/{self.task.id}/assign/', {}, format='json')
		self.assertEqual(assign_response.status_code, 201)
		self.assertEqual(TaskAssignment.objects.filter(task=self.task, user=self.user1).count(), 1)
		self.assertEqual(self.client.delete(f'/api/tasks/{self.task.id}/assign/').status_code, 204)
		self.assertFalse(TaskAssignment.objects.filter(task=self.task, user=self.user1).exists())

	def test_client_cannot_assign_on_behalf_of_another_user(self):
		self.authenticate(self.user1)
		response = self.client.post(f'/api/tasks/{self.task.id}/assign/', {'user_id': self.user2.id}, format='json')
		self.assertEqual(response.status_code, 201)
		self.assertTrue(TaskAssignment.objects.filter(task=self.task, user=self.user1).exists())
		self.assertFalse(TaskAssignment.objects.filter(task=self.task, user=self.user2).exists())

	def test_duplicate_assignment_is_rejected(self):
		self.authenticate(self.user1)
		self.assertEqual(self.client.post(f'/api/tasks/{self.task.id}/assign/', {}).status_code, 201)
		self.assertEqual(self.client.post(f'/api/tasks/{self.task.id}/assign/', {}).status_code, 409)
		self.assertEqual(TaskAssignment.objects.filter(task=self.task, user=self.user1).count(), 1)

	def test_three_users_can_assign_and_one_unassign_does_not_affect_others(self):
		for user in (self.user1, self.user2, self.user3):
			self.authenticate(user)
			self.assertEqual(self.client.post(f'/api/tasks/{self.task.id}/assign/', {}).status_code, 201)
		self.assertEqual(TaskAssignment.objects.filter(task=self.task).count(), 3)

		self.authenticate(self.user1)
		self.assertEqual(self.client.delete(f'/api/tasks/{self.task.id}/assign/').status_code, 204)
		self.assertFalse(TaskAssignment.objects.filter(task=self.task, user=self.user1).exists())
		self.assertTrue(TaskAssignment.objects.filter(task=self.task, user=self.user2).exists())
		self.assertTrue(TaskAssignment.objects.filter(task=self.task, user=self.user3).exists())

	def test_my_tasks_returns_only_current_users_assignments(self):
		TaskAssignment.objects.create(task=self.task, user=self.user2)
		other_task = Task.objects.create(title='Private to user 1', description='Own assignment')
		TaskAssignment.objects.create(task=other_task, user=self.user1)
		self.authenticate(self.user1)
		response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data['results']), 1)
		self.assertEqual(response.data['results'][0]['task']['title'], 'Private to user 1')
		self.assertNotIn('Shared task', str(response.data))

	def test_task_remains_visible_and_reports_current_assignment(self):
		TaskAssignment.objects.create(task=self.task, user=self.user2)
		self.authenticate(self.user1)
		response = self.client.get('/api/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['results'][0]['title'], 'Task A')
		self.assertFalse(response.data['results'][0]['is_assigned'])

		self.client.post(f'/api/tasks/{self.task.id}/assign/', {})
		response = self.client.get('/api/tasks/')
		self.assertTrue(response.data['results'][0]['is_assigned'])

	def test_admin_cannot_use_user_assignment_endpoints(self):
		self.authenticate(self.admin)
		self.assertEqual(self.client.post(f'/api/tasks/{self.task.id}/assign/', {}).status_code, 403)
		self.assertEqual(self.client.get('/api/my/tasks/').status_code, 403)

	def test_unauthenticated_and_missing_task_requests_are_rejected(self):
		self.assertEqual(self.client.post('/api/tasks/999/assign/', {}).status_code, 401)
		self.authenticate(self.user1)
		self.assertEqual(self.client.post('/api/tasks/999/assign/', {}).status_code, 404)
		self.assertEqual(self.client.delete('/api/tasks/999/assign/').status_code, 404)

	def test_database_constraint_prevents_duplicate_records(self):
		TaskAssignment.objects.create(task=self.task, user=self.user1)
		with self.assertRaises(Exception):
			TaskAssignment.objects.create(task=self.task, user=self.user1)


class MyTasksTechStackTests(TestCase):
	"""Verify tech_stack data flows through GET /api/my/tasks/ correctly."""

	def setUp(self):
		self.client = APIClient()
		self.user = User.objects.create_user(username='techuser', password='StrongPassword!42')
		token = Token.objects.create(user=self.user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

		self.python, _ = TechStack.objects.get_or_create(name='Python')
		self.react, _ = TechStack.objects.get_or_create(name='React')

		# Task with two tech stacks
		self.task_py = Task.objects.create(title='Python task', description='Uses Python')
		self.task_py.tech_stack.set([self.python])

		# Task with two tech stacks
		self.task_full = Task.objects.create(title='Full-stack task', description='Uses both')
		self.task_full.tech_stack.set([self.python, self.react])

		# Task with no tech stacks
		self.task_plain = Task.objects.create(title='Plain task', description='Untagged')

		TaskAssignment.objects.create(task=self.task_py, user=self.user)
		TaskAssignment.objects.create(task=self.task_full, user=self.user)
		TaskAssignment.objects.create(task=self.task_plain, user=self.user)

	def _get_my_tasks(self):
		response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		return {item['task']['title']: item['task']['tech_stack'] for item in response.data['results']}

	def test_my_tasks_response_includes_tech_stack_field_on_every_task(self):
		"""Every item in /my/tasks/ must have a tech_stack list on its task."""
		response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		for item in response.data['results']:
			self.assertIn('tech_stack', item['task'])
			self.assertIsInstance(item['task']['tech_stack'], list)

	def test_my_tasks_tech_stack_contains_correct_names(self):
		tasks = self._get_my_tasks()
		self.assertCountEqual(tasks['Python task'], ['Python'])
		self.assertCountEqual(tasks['Full-stack task'], ['Python', 'React'])
		self.assertEqual(tasks['Plain task'], [])

	def test_my_tasks_returns_only_own_assignments_with_tech_stack(self):
		"""A second user's tasks must never appear in the first user's /my/tasks/."""
		other = User.objects.create_user(username='other', password='StrongPassword!42')
		other_task = Task.objects.create(title='Other user task', description='Private')
		other_task.tech_stack.set([self.react])
		TaskAssignment.objects.create(task=other_task, user=other)

		response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		titles = [item['task']['title'] for item in response.data['results']]
		self.assertNotIn('Other user task', titles)
		self.assertEqual(len(titles), 3)  # only the three tasks assigned to self.user

	def test_my_tasks_tech_stack_supports_frontend_and_filter(self):
		"""Simulate the frontend AND-filter: tasks matching ALL selected stacks."""
		tasks = self._get_my_tasks()
		selected = ['Python', 'React']

		# AND filter: task must include every selected stack
		matching = [
			title for title, stacks in tasks.items()
			if all(s in stacks for s in selected)
		]
		self.assertEqual(matching, ['Full-stack task'])

	def test_my_tasks_tech_stack_single_filter(self):
		"""Single-stack filter: returns all tasks that include that stack."""
		tasks = self._get_my_tasks()
		selected = ['Python']
		matching = [
			title for title, stacks in tasks.items()
			if all(s in stacks for s in selected)
		]
		self.assertIn('Python task', matching)
		self.assertIn('Full-stack task', matching)
		self.assertNotIn('Plain task', matching)