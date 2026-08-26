"""Regression tests guarding against tech-stack N+1 queries.

Every endpoint that serializes ``task.tech_stack`` (via TaskSerializer or
TaskSummarySerializer) must prefetch the many-to-many relation so the
SlugRelatedField does not issue one query per task/assignment.

The many-to-many through table is ``taskflow_task_tech_stack``. Without a
prefetch each serialized task triggers its own query against that table; with
a prefetch_related('...tech_stack') the table is hit exactly once regardless
of how many tasks are on the page.
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TechStack

User = get_user_model()

TECH_STACK_THROUGH = 'taskflow_task_tech_stack'


class TechStackQueryCountBase(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42')
		self.user = User.objects.create_user(username='member', password='StrongPassword!42')

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def _stack(self, name):
		stack, _ = TechStack.objects.get_or_create(name=name)
		return stack

	def _through_queries(self, captured):
		"""Queries that touch the task-tech_stack many-to-many through table."""
		return [
			query['sql'] for query in captured.captured_queries
			if TECH_STACK_THROUGH in query['sql']
		]


class TaskListTechStackQueryTests(TechStackQueryCountBase):
	"""GET /api/tasks/ returns TaskSerializer with tech_stack."""

	def test_task_list_prefetches_tech_stack(self):
		stacks = [self._stack(f'Stack {i}') for i in range(3)]
		tasks = [
			Task.objects.create(title=f'Task {i}', description='Bulk')
			for i in range(8)
		]
		# Give every task a share of stacks, some empty.
		for index, task in enumerate(tasks):
			task.tech_stack.set([stacks[index % len(stacks)], stacks[(index + 1) % len(stacks)]])

		self.authenticate(self.user)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/tasks/')
		self.assertEqual(response.status_code, 200)
		results = response.data['results']
		self.assertEqual(len(results), len(tasks))
		# Response correctness: every task exposes its stacks as a list.
		for item in results:
			self.assertIn('tech_stack', item)
			self.assertIsInstance(item['tech_stack'], list)

		# Exactly ONE query may touch the through table (the prefetch).
		# More means the per-task tech-stack N+1 has regressed.
		through_queries = self._through_queries(captured)
		self.assertEqual(len(through_queries), 1)

	def test_task_list_tech_stack_filter_still_works(self):
		"""?tech_stack= retains behavior after adding the prefetch."""
		stack = self._stack('Python')
		task = Task.objects.create(title='Filtered', description='D')
		task.tech_stack.set([stack])
		Task.objects.create(title='Other', description='D')

		self.authenticate(self.user)
		response = self.client.get('/api/tasks/', {'tech_stack': 'Python'})
		self.assertEqual(response.status_code, 200)
		ids = {item['id'] for item in response.data['results']}
		self.assertEqual(ids, {task.id})

class MyTasksTechStackQueryTests(TechStackQueryCountBase):
	"""GET /api/my/tasks/ returns TaskAssignmentSerializer -> TaskSerializer."""

	def test_my_tasks_prefetches_task_tech_stack(self):
		stacks = [self._stack(f'Stack {i}') for i in range(2)]
		tasks = [
			Task.objects.create(title=f'My task {i}', description='Owned')
			for i in range(6)
		]
		for comma, task in enumerate(tasks):
			TaskAssignment.objects.create(task=task, user=self.user)
			task.tech_stack.set([stacks[comma % len(stacks)]])

		self.authenticate(self.user)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/my/tasks/')
		self.assertEqual(response.status_code, 200)
		results = response.data['results']
		self.assertEqual(len(results), len(tasks))
		for item in results:
			self.assertIn('tech_stack', item['task'])
			self.assertIsInstance(item['task']['tech_stack'], list)

		through_queries = self._through_queries(captured)
		self.assertEqual(len(through_queries), 1)


class AdminAssignmentsTechStackQueryTests(TechStackQueryCountBase):
	"""GET /api/admin/assignments/ returns AdminAssignmentSerializer -> TaskSummarySerializer."""

	def test_admin_assignments_prefetches_task_tech_stack(self):
		stacks = [self._stack(f'Stack {i}') for i in range(2)]
		tasks = [
			Task.objects.create(title=f'Assign task {i}', description='D')
			for i in range(6)
		]
		for comma, task in enumerate(tasks):
			TaskAssignment.objects.create(task=task, user=self.user)
			task.tech_stack.set([stacks[comma % len(stacks)]])

		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/admin/assignments/')
		self.assertEqual(response.status_code, 200)
		results = response.data['results']
		self.assertEqual(len(results), len(tasks))
		for item in results:
			self.assertIn('tech_stack', item['task'])
			self.assertIsInstance(item['task']['tech_stack'], list)

		through_queries = self._through_queries(captured)
		self.assertEqual(len(through_queries), 1)


class AdminUserTasksTechStackQueryTests(TechStackQueryCountBase):
	"""Endpoints that render a single user's assigned tasks with tech_stack."""

	def _make_user_with_tasks(self):
		stacks = [self._stack(f'Stack {i}') for i in range(2)]
		user = User.objects.create_user(username='target', password='StrongPassword!42')
		tasks = [
			Task.objects.create(title=f'U task {i}', description='D')
			for i in range(5)
		]
		for comma, task in enumerate(tasks):
			TaskAssignment.objects.create(task=task, user=user)
			task.tech_stack.set([stacks[comma % len(stacks)]])
		return user, tasks

	def test_admin_user_detail_prefetches_assigned_task_tech_stack(self):
		user, tasks = self._make_user_with_tasks()
		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get(f'/api/admin/users/{user.id}/')
		self.assertEqual(response.status_code, 200)
		assigned_tasks = response.data['assigned_tasks']
		self.assertEqual(len(assigned_tasks), len(tasks))
		for item in assigned_tasks:
			self.assertIn('tech_stack', item['task'])
			self.assertIsInstance(item['task']['tech_stack'], list)

		through_queries = self._through_queries(captured)
		self.assertEqual(len(through_queries), 1)

	def test_admin_user_tasks_prefetches_task_tech_stack(self):
		user, tasks = self._make_user_with_tasks()
		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get(f'/api/admin/users/{user.id}/tasks/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), len(tasks))
		for item in response.data:
			self.assertIn('tech_stack', item['task'])
			self.assertIsInstance(item['task']['tech_stack'], list)

		through_queries = self._through_queries(captured)
		self.assertEqual(len(through_queries), 1)
