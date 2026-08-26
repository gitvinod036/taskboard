from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TaskSubmission, TechStack, UserTechStack

User = get_user_model()

DEFAULT_PAGE_SIZE = 25


class PaginationTestBase(TestCase):

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client = APIClient()
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')


class TasksPaginationTests(PaginationTestBase):

	def setUp(self):
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		self.member = User.objects.create_user(username='member', password='StrongPassword!42', email='m@example.com')
		self.tasks = [
			Task.objects.create(title=f'Task {index:03d}', description='D')
			for index in range(DEFAULT_PAGE_SIZE + 5)  # 30 tasks -> 2 pages
		]

	def test_default_page_size_count_and_navigation(self):
		self.authenticate(self.member)
		response = self.client.get('/api/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 30)
		self.assertEqual(len(response.data['results']), DEFAULT_PAGE_SIZE)
		self.assertIsNotNone(response.data['next'])
		self.assertIsNone(response.data['previous'])
		self.assertIn('page=2', response.data['next'])

	def test_page_two_returns_remaining_results(self):
		self.authenticate(self.member)
		response = self.client.get('/api/tasks/', {'page': 2})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 30)
		self.assertEqual(len(response.data['results']), 5)
		self.assertIsNone(response.data['next'])
		self.assertIsNotNone(response.data['previous'])

	def test_is_assigned_annotation_survives_pagination(self):
		TaskAssignment.objects.create(task=self.tasks[0], user=self.member)
		self.authenticate(self.member)
		response = self.client.get('/api/tasks/', {'page_size': 10})
		flagged = [item for item in response.data['results'] if item['is_assigned']]
		self.assertEqual(len(flagged), 1)
		self.assertEqual(flagged[0]['id'], self.tasks[0].id)

	def test_tech_stack_filter_applies_before_pagination(self):
		stack, _ = TechStack.objects.get_or_create(name='Rust')
		for index in range(7):
			self.tasks[index].tech_stack.set([stack])
		self.authenticate(self.member)
		response = self.client.get('/api/tasks/', {'tech_stack': 'Rust'})
		self.assertEqual(response.data['count'], 7)
		self.assertEqual(len(response.data['results']), 7)
		self.assertTrue(all('Rust' in item['tech_stack'] for item in response.data['results']))

	def test_page_size_is_capped(self):
		self.authenticate(self.member)
		response = self.client.get('/api/tasks/', {'page_size': 100000})
		self.assertEqual(response.status_code, 200)
		self.assertLessEqual(len(response.data['results']), 100)


class MyTasksPaginationTests(PaginationTestBase):

	def setUp(self):
		self.member = User.objects.create_user(username='member', password='StrongPassword!42', email='m@example.com')
		self.other = User.objects.create_user(username='other', password='StrongPassword!42', email='o@example.com')
		self.tasks = [Task.objects.create(title=f'My task {index:03d}', description='D') for index in range(27)]
		for index, task in enumerate(self.tasks):
			TaskAssignment.objects.create(task=task, user=self.member)
			if index % 3 == 0:  # other member's own assignments must not leak in
				TaskAssignment.objects.create(task=task, user=self.other)

	def test_only_own_assignments_paginated(self):
		self.authenticate(self.member)
		response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 27)
		self.assertEqual(len(response.data['results']), DEFAULT_PAGE_SIZE)

		page2 = self.client.get('/api/my/tasks/', {'page': 2}).data
		self.assertEqual(page2['count'], 27)
		self.assertEqual(len(page2['results']), 2)

	def test_submission_prefetch_survives_pagination(self):
		# Ordering is newest-first, so attach the submission to the most
		# recently created assignment (first result on page 1).
		TaskSubmission.objects.create(
			task=self.tasks[-1], user=self.member,
			git_url='https://github.com/me/repo', linkedin_url='https://linkedin.com/in/me',
		)
		self.authenticate(self.member)
		response = self.client.get('/api/my/tasks/', {'page_size': 5})
		mine = next(item for item in response.data['results'] if item['task']['id'] == self.tasks[-1].id)
		self.assertIsNotNone(mine['submission'])
		self.assertEqual(mine['submission']['git_url'], 'https://github.com/me/repo')

	def test_other_member_cannot_see_foreign_assignments_via_paging(self):
		self.authenticate(self.other)
		response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.data['count'], 9)  # only their own 9


class AdminUsersPaginationTests(PaginationTestBase):

	def setUp(self):
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		self.members = [
			User.objects.create_user(username=f'member{index:02d}', password='StrongPassword!42', email=f'm{index}@example.com')
			for index in range(DEFAULT_PAGE_SIZE + 3)  # 28 members -> 2 pages
		]
		task = Task.objects.create(title='T', description='D')
		TaskAssignment.objects.create(user=self.members[0], task=task)
		stack, _ = TechStack.objects.get_or_create(name='Go')
		UserTechStack.objects.create(user=self.members[0], tech_stack=stack)

	def test_users_pagination_with_counts_and_stacks(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/users/', {'page_size': 10})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 28)
		self.assertEqual(len(response.data['results']), 10)

		page2 = self.client.get('/api/admin/users/', {'page': 2, 'page_size': 10}).data
		self.assertEqual(len(page2['results']), 10)
		page3 = self.client.get('/api/admin/users/', {'page': 3, 'page_size': 10}).data
		self.assertEqual(len(page3['results']), 8)

		first = response.data['results'][0]
		self.assertIn('assigned_task_count', first)
		self.assertIn('tech_stack', first)

	def test_search_and_filter_apply_before_pagination(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/users/', {'search': 'member00'})
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['results'][0]['assigned_task_count'], 1)

		response = self.client.get('/api/admin/users/', {'tech_stack': 'Go'})
		self.assertEqual(response.data['count'], 1)
		self.assertCountEqual(response.data['results'][0]['tech_stack'], ['Go'])

	def test_normal_user_rejected(self):
		self.authenticate(self.members[0])
		self.assertEqual(self.client.get('/api/admin/users/').status_code, 403)


class AdminAssignmentsPaginationTests(PaginationTestBase):

	def setUp(self):
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		self.member = User.objects.create_user(username='member', password='StrongPassword!42', email='m@example.com')
		self.tasks = [Task.objects.create(title=f'Task {index:03d}', description='D') for index in range(30)]
		for index in range(30):
			TaskAssignment.objects.create(user=self.member, task=self.tasks[index])
		stack, _ = TechStack.objects.get_or_create(name='Svelte')
		self.tasks[0].tech_stack.set([stack])

	def test_assignments_pagination_and_nested_counts(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/assignments/', {'page_size': 12})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 30)
		self.assertEqual(len(response.data['results']), 12)
		self.assertEqual(response.data['results'][0]['user']['assigned_task_count'], 30)

		page3 = self.client.get('/api/admin/assignments/', {'page': 3, 'page_size': 12}).data
		self.assertEqual(len(page3['results']), 6)

	def test_assignment_tech_stack_filter_before_pagination(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/assignments/', {'tech_stack': 'Svelte'})
		self.assertEqual(response.data['count'], 1)
		self.assertEqual(response.data['results'][0]['task']['title'], 'Task 000')
		self.assertEqual(response.data['results'][0]['user']['assigned_task_count'], 30)

	def test_unauthenticated_rejected(self):
		client = APIClient()
		self.assertEqual(client.get('/api/admin/assignments/').status_code, 401)


class AdminSubmissionsPaginationTests(PaginationTestBase):

	def setUp(self):
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
		self.member = User.objects.create_user(username='member', password='StrongPassword!42', email='m@example.com')
		tasks = [Task.objects.create(title=f'Sub task {index:03d}', description='D') for index in range(22)]
		for index, task in enumerate(tasks):
			TaskSubmission.objects.create(
				task=task, user=self.member,
				git_url=f'https://github.com/me/repo{index}',
				linkedin_url='https://linkedin.com/in/me',
			)

	def test_submissions_pagination_ordering_and_navigation(self):
		self.authenticate(self.admin)
		response = self.client.get('/api/admin/submissions/', {'page_size': 8})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['count'], 22)
		self.assertEqual(len(response.data['results']), 8)
		self.assertIn('page=2', response.data['next'])

		timestamps = [item['submitted_at'] for item in response.data['results']]
		self.assertEqual(timestamps, sorted(timestamps, reverse=True))

		page2 = self.client.get('/api/admin/submissions/', {'page': 2, 'page_size': 8})
		self.assertEqual(page2.data['count'], 22)
		self.assertEqual(len(page2.data['results']), 8)
		self.assertIsNotNone(page2.data['previous'])

		page3 = self.client.get('/api/admin/submissions/', {'page': 3, 'page_size': 8})
		self.assertEqual(len(page3.data['results']), 6)
		self.assertIsNone(page3.data['next'])

		all_ids = (
			[item['id'] for item in self.client.get('/api/admin/submissions/', {'page_size': 8}).data['results']]
			+ [item['id'] for item in page2.data['results']]
			+ [item['id'] for item in page3.data['results']]
		)
		self.assertEqual(len(set(all_ids)), 22)  # no duplicates across pages

	def test_normal_user_rejected_on_submissions(self):
		self.authenticate(self.member)
		self.assertEqual(self.client.get('/api/admin/submissions/').status_code, 403)
