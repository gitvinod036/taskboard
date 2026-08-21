from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TechStack

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
		self.assertGreater(len(response.data), 0)
		for task in response.data:
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

	def test_tech_stacks_endpoint_requires_authentication(self):
		"""GET /api/tasks/tech-stacks/ must reject unauthenticated requests."""
		self.assertEqual(self.client.get('/api/tasks/tech-stacks/').status_code, 401)