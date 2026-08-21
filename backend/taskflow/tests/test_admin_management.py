from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TechStack, UserTechStack

User = get_user_model()


class AdminManagementTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		self.user1 = User.objects.create_user(username='user1', password='StrongPassword!42', email='one@example.com')
		self.user2 = User.objects.create_user(username='user2', password='StrongPassword!42', email='two@example.com')
		self.user3 = User.objects.create_user(username='user3', password='StrongPassword!42', email='three@example.com')
		self.task_a = Task.objects.create(title='Task A', description='A')
		self.task_b = Task.objects.create(title='Task B', description='B')

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def assign(self, user, task):
		TaskAssignment.objects.create(user=user, task=task)

	def test_admin_can_list_users_and_view_user_assignments(self):
		self.assign(self.user1, self.task_a)
		self.authenticate(self.admin)
		list_response = self.client.get('/api/admin/users/')
		self.assertEqual(list_response.status_code, 200)
		user_data = next(item for item in list_response.data if item['id'] == self.user1.id)
		self.assertEqual(user_data['name'], 'user1')
		self.assertEqual(user_data['assigned_task_count'], 1)
		self.assertNotIn('password', user_data)

		detail_response = self.client.get(f'/api/admin/users/{self.user1.id}/')
		self.assertEqual(detail_response.status_code, 200)
		self.assertEqual(detail_response.data['assigned_tasks'][0]['task']['title'], 'Task A')
		self.assertNotIn('password', detail_response.data)
		self.assertNotIn('token', detail_response.data)

	def test_admin_can_list_all_assignments_and_specific_user_tasks(self):
		self.assign(self.user1, self.task_a)
		self.assign(self.user2, self.task_a)
		self.authenticate(self.admin)
		self.assertEqual(self.client.get('/api/admin/assignments/').status_code, 200)
		response = self.client.get(f'/api/admin/users/{self.user2.id}/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]['task']['title'], 'Task A')

	def test_admin_unassigns_only_selected_user_task(self):
		self.assign(self.user1, self.task_a)
		self.assign(self.user2, self.task_a)
		self.assign(self.user3, self.task_a)
		self.assign(self.user2, self.task_b)
		self.authenticate(self.admin)
		response = self.client.delete(f'/api/admin/users/{self.user2.id}/tasks/{self.task_a.id}/')
		self.assertEqual(response.status_code, 204)
		self.assertFalse(TaskAssignment.objects.filter(user=self.user2, task=self.task_a).exists())
		self.assertTrue(TaskAssignment.objects.filter(user=self.user1, task=self.task_a).exists())
		self.assertTrue(TaskAssignment.objects.filter(user=self.user3, task=self.task_a).exists())
		self.assertTrue(TaskAssignment.objects.filter(user=self.user2, task=self.task_b).exists())

	def test_delete_user_removes_only_assignments_and_preserves_tasks_and_others(self):
		self.assign(self.user1, self.task_a)
		self.assign(self.user2, self.task_a)
		self.assign(self.user2, self.task_b)
		self.assign(self.user3, self.task_a)
		self.authenticate(self.admin)
		response = self.client.delete(f'/api/admin/users/{self.user2.id}/')
		self.assertEqual(response.status_code, 204)
		self.assertFalse(User.objects.filter(pk=self.user2.id).exists())
		self.assertTrue(Task.objects.filter(pk=self.task_a.id).exists())
		self.assertTrue(Task.objects.filter(pk=self.task_b.id).exists())
		self.assertTrue(TaskAssignment.objects.filter(user=self.user1, task=self.task_a).exists())
		self.assertTrue(TaskAssignment.objects.filter(user=self.user3, task=self.task_a).exists())
		self.assertFalse(TaskAssignment.objects.filter(user_id=self.user2.id).exists())

	def test_admin_cannot_delete_or_manage_admin(self):
		self.authenticate(self.admin)
		self.assertEqual(self.client.delete(f'/api/admin/users/{self.admin.id}/').status_code, 403)
		self.assertEqual(self.client.get(f'/api/admin/users/{self.admin.id}/').status_code, 403)

	def test_normal_user_cannot_access_admin_apis(self):
		self.authenticate(self.user1)
		self.assertEqual(self.client.get('/api/admin/users/').status_code, 403)
		self.assertEqual(self.client.get('/api/admin/assignments/').status_code, 403)
		self.assertEqual(self.client.get(f'/api/admin/users/{self.user2.id}/tasks/').status_code, 403)

	def test_unauthenticated_and_missing_resources_are_rejected(self):
		self.assertEqual(self.client.get('/api/admin/users/').status_code, 401)
		self.authenticate(self.admin)
		self.assertEqual(self.client.get('/api/admin/users/999/').status_code, 404)
		self.assertEqual(self.client.get('/api/admin/users/999/tasks/').status_code, 404)
		self.assertEqual(self.client.delete(f'/api/admin/users/{self.user1.id}/tasks/999/').status_code, 404)

	def test_admin_can_update_and_retrieve_user_tech_stack(self):
		TechStack.objects.get_or_create(name='React')
		TechStack.objects.get_or_create(name='Python')
		self.authenticate(self.admin)
		response = self.client.patch(f'/api/admin/users/{self.user1.id}/', {'tech_stack': ['React', 'Python']}, format='json')
		self.assertEqual(response.status_code, 200)
		self.assertCountEqual(response.data['tech_stack'], ['React', 'Python'])
		self.assertEqual(UserTechStack.objects.filter(user=self.user1).count(), 2)

		response = self.client.get(f'/api/admin/users/{self.user1.id}/')
		self.assertCountEqual(response.data['tech_stack'], ['React', 'Python'])

	def test_admin_can_filter_users_by_one_or_multiple_tech_stacks(self):
		for name in ('React', 'Python', 'Django'):
			TechStack.objects.get_or_create(name=name)
		UserTechStack.objects.create(user=self.user1, tech_stack=TechStack.objects.get(name='React'))
		UserTechStack.objects.create(user=self.user1, tech_stack=TechStack.objects.get(name='Python'))
		UserTechStack.objects.create(user=self.user2, tech_stack=TechStack.objects.get(name='React'))
		UserTechStack.objects.create(user=self.user3, tech_stack=TechStack.objects.get(name='Django'))
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/users/?tech_stack=React')
		self.assertEqual(response.status_code, 200)
		self.assertCountEqual([item['name'] for item in response.data], ['user1', 'user2'])
		response = self.client.get('/api/admin/users/?tech_stack=React,Python')
		self.assertEqual(response.status_code, 200)
		self.assertEqual([item['name'] for item in response.data], ['user1'])
		self.assertEqual(self.client.get('/api/admin/users/?tech_stack=Rust').data, [])

	def test_normal_user_cannot_filter_or_update_user_tech_stack(self):
		self.authenticate(self.user1)
		self.assertEqual(self.client.get('/api/admin/users/?tech_stack=React').status_code, 403)
		self.assertEqual(self.client.patch(f'/api/admin/users/{self.user2.id}/', {'tech_stack': ['React']}, format='json').status_code, 403)

	def test_admin_assignment_responses_do_not_expose_credentials(self):
		self.assign(self.user1, self.task_a)
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/assignments/')
		self.assertEqual(response.status_code, 200)
		self.assertNotIn('password', str(response.data))
		self.assertNotIn('token', str(response.data))