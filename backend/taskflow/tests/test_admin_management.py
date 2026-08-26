import re

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
		user_data = next(item for item in list_response.data['results'] if item['id'] == self.user1.id)
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
		# Never assume a literal id is unused: kept test databases carry ids
		# forward across runs, so derive one that cannot exist.
		missing_user_id = User.objects.order_by('-id').values_list('id', flat=True).first() + 1_000_000
		self.assertEqual(self.client.get(f'/api/admin/users/{missing_user_id}/').status_code, 404)
		self.assertEqual(self.client.get(f'/api/admin/users/{missing_user_id}/tasks/').status_code, 404)
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
		self.assertCountEqual([item['name'] for item in response.data['results']], ['user1', 'user2'])
		response = self.client.get('/api/admin/users/?tech_stack=React,Python')
		self.assertEqual(response.status_code, 200)
		self.assertEqual([item['name'] for item in response.data['results']], ['user1'])
		self.assertEqual(self.client.get('/api/admin/users/?tech_stack=Rust').data['results'], [])

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


class AdminQueryEfficiencyTests(TestCase):
	"""Regression guards for the admin serializer N+1 fixes."""

	def setUp(self):
		self.client = APIClient()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		# Five members with varying assignments and tech stacks make any
		# per-user query pattern visible.
		self.members = [
			User.objects.create_user(username=f'member{index}', password='StrongPassword!42', email=f'm{index}@example.com')
			for index in range(5)
		]
		self.tasks = [Task.objects.create(title=f'Task {index}', description='D') for index in range(6)]
		for index, member in enumerate(self.members):
			for task_index in range(index):  # member0:0, member1:1, ... member4:4
				TaskAssignment.objects.create(user=member, task=self.tasks[task_index])
		for name in ('React', 'Python', 'Django'):
			TechStack.objects.get_or_create(name=name)
		UserTechStack.objects.create(user=self.members[0], tech_stack=TechStack.objects.get(name='React'))
		UserTechStack.objects.create(user=self.members[1], tech_stack=TechStack.objects.get(name='React'))
		UserTechStack.objects.create(user=self.members[1], tech_stack=TechStack.objects.get(name='Python'))
		# members[2..4] have no stacks at all.

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def test_admin_users_returns_correct_counts_and_stacks_without_n_plus_one(self):
		from django.db import connection
		from django.test.utils import CaptureQueriesContext

		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/admin/users/')
		self.assertEqual(response.status_code, 200)
		data = {item['id']: item for item in response.data['results']}
		self.assertEqual(data[self.members[0].id]['assigned_task_count'], 0)
		self.assertEqual(data[self.members[3].id]['assigned_task_count'], 3)
		self.assertCountEqual(data[self.members[1].id]['tech_stack'], ['React', 'Python'])
		self.assertEqual(data[self.members[2].id]['tech_stack'], [])

		sql_statements = [query['sql'] for query in captured.captured_queries]
		# Exactly ONE prefetch query fetches all users' stacks; more means a
		# per-user tech-stack N+1 has regressed.
		stack_queries = [sql for sql in sql_statements if 'taskflow_usertechstack' in sql]
		self.assertEqual(len(stack_queries), 1)
		# At most two COUNT-containing queries are legitimate: the annotated
		# users-list query itself plus the paginator's COUNT. Any third means
		# a per-user COUNT N+1 has regressed.
		count_queries = [sql for sql in sql_statements if 'COUNT' in sql.upper()]
		self.assertLessEqual(len(count_queries), 2)

	def test_admin_users_tech_stack_filtering_and_search_still_work(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/users/?tech_stack=React')
		self.assertEqual(response.status_code, 200)
		self.assertCountEqual([item['name'] for item in response.data['results']], ['member0', 'member1'])
		for item in response.data['results']:  # counts stay correct under filtering
			expected = int(item['name'].replace('member', ''))
			self.assertEqual(item['assigned_task_count'], expected)

		response = self.client.get('/api/admin/users/?search=member3')
		self.assertEqual([item['name'] for item in response.data['results']], ['member3'])
		self.assertEqual(response.data['results'][0]['assigned_task_count'], 3)

	def test_admin_assignments_nested_user_data_without_n_plus_one(self):
		from django.db import connection
		from django.test.utils import CaptureQueriesContext

		# Two stacks on one task: the optional m2m filter join would multiply
		# rows and inflate a non-distinct COUNT annotation.
		self.tasks[0].tech_stack.set([
			TechStack.objects.get(name='React'),
			TechStack.objects.get(name='Python'),
		])

		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/admin/assignments/')
		self.assertEqual(response.status_code, 200)
		nested_by_user = {}
		for item in response.data['results']:
			nested_by_user.setdefault(item['user']['id'], item['user'])
		self.assertEqual(nested_by_user[self.members[3].id]['assigned_task_count'], 3)
		self.assertCountEqual(nested_by_user[self.members[1].id]['tech_stack'], ['React', 'Python'])

		sql_statements = [query['sql'] for query in captured.captured_queries]
		# One prefetch query for all nested users' tech stacks — never one per user.
		stack_queries = [sql for sql in sql_statements if 'taskflow_usertechstack' in sql]
		self.assertEqual(len(stack_queries), 1)
		# No standalone per-user "SELECT COUNT(*) FROM taskflow_taskassignment
		# WHERE user_id = X" queries; counts come from the annotation inside
		# the list query (the paginator's grouped COUNT wrapper is fine).
		standalone_counts = [
			sql for sql in sql_statements
			if re.search(r'SELECT COUNT\(\*\)\s+FROM "taskflow_taskassignment"\s+WHERE', sql)
		]
		self.assertEqual(standalone_counts, [])

		# Filtered variant keeps nested counts correct despite the extra join.
		# Only members holding assignments on matching tasks appear (member0
		# holds none), and their counts must not be inflated by the join.
		response = self.client.get('/api/admin/assignments/?tech_stack=React,Python')
		self.assertEqual(response.status_code, 200)
		nested_counts = {item['user']['id']: item['user']['assigned_task_count'] for item in response.data['results']}
		self.assertEqual(len(nested_counts), 4)  # members 1..4
		for member_index in range(1, 5):
			member_id = self.members[member_index].id
			self.assertIn(member_id, nested_counts)
			self.assertEqual(nested_counts[member_id], member_index)