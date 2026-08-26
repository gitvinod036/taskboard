"""Regression tests for multi-tech-stack AND filtering (Step 8).

``?tech_stack=A,B,C`` must keep returning only records that contain EVERY
requested stack (AND semantics), while the underlying SQL stays a single join
plus a COUNT/HAVING instead of one extra JOIN per selected stack.
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TechStack, UserTechStack

User = get_user_model()

TASK_THROUGH = 'taskflow_task_tech_stack'
USER_THROUGH = 'taskflow_usertechstack'


class MultiStackFilterBase(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = User.objects.create_user(username='member', password='StrongPassword!42')
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42')

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def _stack(self, name):
		stack, _ = TechStack.objects.get_or_create(name=name)
		return stack


class TaskListMultiStackFilterTests(MultiStackFilterBase):
	"""GET /api/tasks/?tech_stack= keeps AND semantics."""

	def setUp(self):
		super().setUp()
		self.authenticate(self.user)
		stacks = {
			name: self._stack(name)
			for name in ('Python', 'Django', 'React', 'Node')
		}
		self.combos = {
			'All three': ['Python', 'Django', 'React'],
			'Py + Dj': ['Python', 'Django'],
			'Py + Re': ['Python', 'React'],
			'Dj + Re': ['Django', 'React'],
			'Py only': ['Python'],
			'No stacks': [],
			'With Node': ['Node'],
		}
		self.tasks = {}
		for title, names in self.combos.items():
			task = Task.objects.create(title=title, description='d')
			task.tech_stack.set([stacks[n] for n in names])
			self.tasks[title] = task

	def _ids_for(self, stacks):
		response = self.client.get('/api/tasks/', {'tech_stack': ','.join(stacks)})
		self.assertEqual(response.status_code, 200)
		return sorted(item['id'] for item in response.data['results'])

	def _titles_for(self, stacks):
		lookup = {task.id: title for title, task in self.tasks.items()}
		return sorted(lookup[task_id] for task_id in self._ids_for(stacks))

	def test_single_stack(self):
		self.assertEqual(
			self._titles_for(['Python']),
			['All three', 'Py + Dj', 'Py + Re', 'Py only'],
		)

	def test_two_stacks_require_both(self):
		self.assertEqual(self._titles_for(['Python', 'Django']), ['All three', 'Py + Dj'])
		self.assertEqual(self._titles_for(['Django', 'React']), ['All three', 'Dj + Re'])

	def test_three_stacks_require_all_three(self):
		self.assertEqual(self._titles_for(['Python', 'Django', 'React']), ['All three'])

	def test_partial_match_is_excluded(self):
		titles = self._titles_for(['Python', 'Django'])
		self.assertNotIn('Py only', titles)
		self.assertNotIn('No stacks', titles)
		self.assertNotIn('With Node', titles)

	def test_task_with_many_matching_stacks_appears_once(self):
		ids = self._ids_for(['Python', 'Django'])
		self.assertEqual(len(ids), len(set(ids)))
		self.assertEqual(ids.count(self.tasks['All three'].id), 1)

	def test_duplicate_stack_names_in_param_behave_like_unique(self):
		self.assertEqual(self._titles_for(['Python', 'Python']), self._titles_for(['Python']))

	def test_unknown_stack_returns_empty(self):
		self.assertEqual(self._ids_for(['Rust']), [])

	def test_no_filter_returns_everything(self):
		self.assertEqual(len(self._ids_for([])), len(self.combos))

	def test_filtered_pagination_shape_is_correct(self):
		for index in range(30):
			task = Task.objects.create(title=f'Bulk {index}', description='d')
			task.tech_stack.set([self._stack('Python'), self._stack('Django')])
		response = self.client.get('/api/tasks/', {'tech_stack': 'Python,Django', 'page_size': 10})
		self.assertEqual(response.status_code, 200)
		self.assertIn('count', response.data)
		self.assertIn('next', response.data)
		self.assertIn('previous', response.data)
		self.assertIn('results', response.data)
		self.assertEqual(response.data['count'], 32)  # 30 bulk + All three + Py + Dj
		self.assertEqual(len(response.data['results']), 10)
		self.assertIsNotNone(response.data['next'])
		self.assertIsNone(response.data['previous'])
		page2 = self.client.get('/api/tasks/', {'tech_stack': 'Python,Django', 'page_size': 10, 'page': 2})
		self.assertEqual(len(page2.data['results']), 10)
		first_ids = {item['id'] for item in response.data['results']}
		second_ids = {item['id'] for item in page2.data['results']}
		self.assertFalse(first_ids & second_ids)

	def test_join_count_does_not_grow_with_selected_stacks(self):
		def through_refs(stacks):
			with CaptureQueriesContext(connection) as captured:
				response = self.client.get('/api/tasks/', {'tech_stack': ','.join(stacks)})
			self.assertEqual(response.status_code, 200)
			return max(sql.count(TASK_THROUGH) for sql in (q['sql'] for q in captured.captured_queries))

		one = through_refs(['Python'])
		two = through_refs(['Python', 'Django'])
		three = through_refs(['Python', 'Django', 'React'])
		self.assertEqual(one, two)
		self.assertEqual(two, three)

class MyTasksMultiStackFilterTests(MultiStackFilterBase):
	"""GET /api/my/tasks/?tech_stack= keeps AND semantics on the user's own assignments."""

	def setUp(self):
		super().setUp()
		self.authenticate(self.user)
		self.other = User.objects.create_user(username='other', password='StrongPassword!42')
		stacks = {name: self._stack(name) for name in ('Python', 'Django', 'React')}
		specs = {
			'Own all three': (['Python', 'Django', 'React'], self.user),
			'Own two': (['Python', 'Django'], self.user),
			'Own one': (['Python'], self.user),
			'Other all three': (['Python', 'Django', 'React'], self.other),
			'Other one': (['Django'], self.other),
		}
		self.tasks = {}
		for title, (names, owner) in specs.items():
			task = Task.objects.create(title=title, description='d')
			task.tech_stack.set([stacks[n] for n in names])
			TaskAssignment.objects.create(task=task, user=owner)
			self.tasks[title] = task

	def _titles_for(self, stacks):
		response = self.client.get('/api/my/tasks/', {'tech_stack': ','.join(stacks)})
		self.assertEqual(response.status_code, 200)
		return sorted(item['task']['title'] for item in response.data['results'])

	def test_my_tasks_two_stacks_require_both_and_stay_private(self):
		titles = self._titles_for(['Python', 'Django'])
		self.assertEqual(titles, ['Own all three', 'Own two'])
		self.assertNotIn('Other all three', titles)

	def test_my_tasks_three_stacks(self):
		self.assertEqual(self._titles_for(['Python', 'Django', 'React']), ['Own all three'])

	def test_my_tasks_single_stack(self):
		self.assertEqual(
			self._titles_for(['Python']),
			['Own all three', 'Own one', 'Own two'],
		)

	def test_my_tasks_join_count_constant_across_stack_counts(self):
		def through_refs(stacks):
			with CaptureQueriesContext(connection) as captured:
				response = self.client.get('/api/my/tasks/', {'tech_stack': ','.join(stacks)})
			self.assertEqual(response.status_code, 200)
			return max(sql.count(TASK_THROUGH) for sql in (q['sql'] for q in captured.captured_queries))

		self.assertEqual(through_refs(['Python']), through_refs(['Python', 'Django', 'React']))


class AdminUsersMultiStackFilterTests(MultiStackFilterBase):
	"""GET /api/admin/users/ keeps AND filtering plus search and count accuracy."""

	def setUp(self):
		super().setUp()
		self.authenticate(self.admin)
		stacks = {name: self._stack(name) for name in ('React', 'Python', 'Django')}
		self.both = User.objects.create_user(username='aaa_both', password='StrongPassword!42')
		self.react_only = User.objects.create_user(username='bbb_react', password='StrongPassword!42')
		UserTechStack.objects.create(user=self.both, tech_stack=stacks['React'])
		UserTechStack.objects.create(user=self.both, tech_stack=stacks['Python'])
		UserTechStack.objects.create(user=self.both, tech_stack=stacks['Django'])
		UserTechStack.objects.create(user=self.react_only, tech_stack=stacks['React'])
		# Assignments so the assigned_task_count annotation is non-trivial.
		for index in range(3):
			task = Task.objects.create(title=f'T{index}', description='d')
			TaskAssignment.objects.create(task=task, user=self.both)

	def _names_for(self, query):
		response = self.client.get('/api/admin/users/', query)
		self.assertEqual(response.status_code, 200)
		return [item['name'] for item in response.data['results']]

	def test_multi_stack_and_semantics(self):
		self.assertEqual(sorted(self._names_for({'tech_stack': 'React,Python'})), ['aaa_both'])
		self.assertCountEqual(self._names_for({'tech_stack': 'React'}), ['aaa_both', 'bbb_react'])
		self.assertEqual(self._names_for({'tech_stack': 'Rust'}), [])

	def test_three_stack_filter(self):
		self.assertEqual(self._names_for({'tech_stack': 'React,Python,Django'}), ['aaa_both'])

	def test_search_combined_with_stack_filter(self):
		self.assertEqual(self._names_for({'search': 'react', 'tech_stack': 'React'}), ['bbb_react'])
		self.assertEqual(self._names_for({'search': 'both', 'tech_stack': 'React,Python'}), ['aaa_both'])
		self.assertEqual(self._names_for({'search': 'nomatchxyz'}), [])

	def test_assigned_counts_stay_exact_under_multi_stack_filter(self):
		response = self.client.get('/api/admin/users/', {'tech_stack': 'React,Python'})
		counts = {item['name']: item['assigned_task_count'] for item in response.data['results']}
		self.assertEqual(counts['aaa_both'], 3)

	def test_users_join_count_constant_across_stack_counts(self):
		def through_refs(stacks):
			with CaptureQueriesContext(connection) as captured:
				response = self.client.get('/api/admin/users/', {'tech_stack': ','.join(stacks)})
			self.assertEqual(response.status_code, 200)
			return max(sql.count(USER_THROUGH) for sql in (q['sql'] for q in captured.captured_queries))

		self.assertEqual(through_refs(['React']), through_refs(['React', 'Python', 'Django']))


class AdminAssignmentsMultiStackFilterTests(MultiStackFilterBase):
	"""GET /api/admin/assignments/?tech_stack= keeps AND semantics and nested counts."""

	def setUp(self):
		super().setUp()
		self.authenticate(self.admin)
		stacks = {name: self._stack(name) for name in ('React', 'Python', 'Django')}
		self.full_stack_task = Task.objects.create(title='Full stack task', description='d')
		self.full_stack_task.tech_stack.set([stacks[n] for n in ('React', 'Python')])
		self.partial_task = Task.objects.create(title='Partial task', description='d')
		self.partial_task.tech_stack.set([stacks['React']])
		self.members = [
			User.objects.create_user(username=f'm{i}', password='StrongPassword!42')
			for i in range(2)
		]
		for index, member in enumerate(self.members):
			TaskAssignment.objects.create(task=self.full_stack_task, user=member)
			if index == 0:
				TaskAssignment.objects.create(task=self.partial_task, user=member)

	def _rows_for(self, stacks):
		response = self.client.get('/api/admin/assignments/', {'tech_stack': ','.join(stacks)})
		self.assertEqual(response.status_code, 200)
		return response.data

	def test_assignments_multi_stack_and_semantics(self):
		data = self._rows_for(['React', 'Python'])
		titles = sorted(item['task']['title'] for item in data['results'])
		self.assertEqual(titles, ['Full stack task', 'Full stack task'])  # both members
		data_one = self._rows_for(['React'])
		self.assertEqual(len(data_one['results']), 3)

	def test_assignments_nested_count_not_inflated_by_filter(self):
		data = self._rows_for(['React', 'Python'])
		nested = {item['user']['id']: item['user']['assigned_task_count'] for item in data['results']}
		self.assertEqual(nested[self.members[0].id], 2)
		self.assertEqual(nested[self.members[1].id], 1)

	def test_assignments_pagination_shape_under_filter(self):
		data = self._rows_for(['React'])
		self.assertIn('count', data)
		self.assertIn('next', data)
		self.assertIn('previous', data)
		self.assertIn('results', data)
		self.assertEqual(data['count'], 3)

	def test_assignments_join_count_constant_across_stack_counts(self):
		def through_refs(stacks):
			with CaptureQueriesContext(connection) as captured:
				response = self.client.get('/api/admin/assignments/', {'tech_stack': ','.join(stacks)})
			self.assertEqual(response.status_code, 200)
			return max(sql.count(TASK_THROUGH) for sql in (q['sql'] for q in captured.captured_queries))

		self.assertEqual(through_refs(['React']), through_refs(['React', 'Python']))
