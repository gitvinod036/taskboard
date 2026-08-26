from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task, TaskAssignment, TaskSubmission

User = get_user_model()


class TaskSubmissionTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42')
		self.user = User.objects.create_user(username='member', password='StrongPassword!42')
		self.other = User.objects.create_user(username='other', password='StrongPassword!42')
		self.task = Task.objects.create(title='Task A', description='Submit this task')
		TaskAssignment.objects.create(task=self.task, user=self.user)

	def authenticate(self, user):
		token, _ = Token.objects.get_or_create(user=user)
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

	def payload(self):
		return {'git_url': 'https://github.com/example/task-a', 'linkedin_url': 'https://www.linkedin.com/in/example', 'note': 'Ready for review'}

	def test_assigned_user_can_submit_and_my_tasks_shows_status(self):
		self.authenticate(self.user)
		response = self.client.post(f'/api/tasks/{self.task.id}/submit/', self.payload(), format='json')
		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data['status'], 'PENDING')
		my_tasks = self.client.get('/api/my/tasks/')
		self.assertEqual(my_tasks.status_code, 200)
		self.assertEqual(my_tasks.data['results'][0]['submission']['status'], 'PENDING')

	def test_unassigned_user_cannot_submit(self):
		self.authenticate(self.other)
		self.assertEqual(self.client.post(f'/api/tasks/{self.task.id}/submit/', self.payload(), format='json').status_code, 403)

	def test_submission_validates_urls(self):
		self.authenticate(self.user)
		response = self.client.post(f'/api/tasks/{self.task.id}/submit/', {'git_url': 'https://example.com', 'linkedin_url': 'https://example.com'}, format='json')
		self.assertEqual(response.status_code, 400)

	def test_admin_can_reject_then_user_can_resubmit(self):
		self.authenticate(self.user)
		self.client.post(f'/api/tasks/{self.task.id}/submit/', self.payload(), format='json')
		submission = TaskSubmission.objects.get(task=self.task, user=self.user)
		self.authenticate(self.admin)
		review = self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'REJECTED', 'feedback': 'Please add more detail.'}, format='json')
		self.assertEqual(review.status_code, 200)
		self.assertEqual(review.data['feedback'], 'Please add more detail.')
		self.authenticate(self.user)
		resubmit = self.client.post(f'/api/tasks/{self.task.id}/submit/', self.payload(), format='json')
		self.assertEqual(resubmit.status_code, 200)
		self.assertEqual(resubmit.data['status'], 'PENDING')

	def test_admin_can_approve_and_list_submissions(self):
		TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		listing = self.client.get('/api/admin/submissions/')
		self.assertEqual(listing.status_code, 200)
		submission_id = listing.data['results'][0]['id']
		review = self.client.patch(f'/api/admin/submissions/{submission_id}/', {'status': 'APPROVED', 'feedback': 'Approved.'}, format='json')
		self.assertEqual(review.status_code, 200)
		self.assertEqual(review.data['status'], 'APPROVED')

	def test_admin_can_approve_without_review(self):
		"""A review comment is optional: approval succeeds with no feedback at all."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		review = self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'APPROVED'}, format='json')
		self.assertEqual(review.status_code, 200)
		self.assertEqual(review.data['status'], 'APPROVED')
		self.assertEqual(review.data['feedback'], '')
		submission.refresh_from_db()
		self.assertEqual(submission.status, 'APPROVED')
		self.assertEqual(submission.feedback, '')
		self.assertEqual(submission.reviewed_by, self.admin)
		self.assertIsNotNone(submission.reviewed_at)

	def test_admin_can_approve_with_blank_review(self):
		"""Whitespace-only or empty-string feedback is accepted like no review."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		for blank in ('', '   '):
			review = self.client.patch(
				f'/api/admin/submissions/{submission.id}/',
				{'status': 'APPROVED', 'feedback': blank},
				format='json',
			)
			self.assertEqual(review.status_code, 200)
			self.assertEqual(review.data['status'], 'APPROVED')
			# CharField trims whitespace, so a whitespace-only comment is stored empty.
			self.assertEqual(review.data['feedback'], '')

	def test_admin_can_reject_without_review(self):
		"""Rejection must not require a comment either."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		review = self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'REJECTED'}, format='json')
		self.assertEqual(review.status_code, 200)
		self.assertEqual(review.data['status'], 'REJECTED')
		self.assertEqual(review.data['feedback'], '')
		submission.refresh_from_db()
		self.assertEqual(submission.status, 'REJECTED')
		self.assertEqual(submission.feedback, '')

	def test_admin_can_reject_with_review(self):
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		review = self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'REJECTED', 'feedback': 'Needs more detail.'}, format='json')
		self.assertEqual(review.status_code, 200)
		self.assertEqual(review.data['status'], 'REJECTED')
		self.assertEqual(review.data['feedback'], 'Needs more detail.')

	def test_unauthenticated_review_is_rejected(self):
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		response = self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'APPROVED'}, format='json')
		self.assertIn(response.status_code, (401, 403))
		submission.refresh_from_db()
		self.assertEqual(submission.status, 'PENDING')

	def test_admin_can_get_single_submission(self):
		"""GET /api/admin/submissions/<id>/ returns 200 with the submission."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		response = self.client.get(f'/api/admin/submissions/{submission.id}/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data['id'], submission.id)
		self.assertEqual(response.data['task_title'], self.task.title)
		self.assertEqual(response.data['username'], self.user.username)
		self.assertEqual(response.data['status'], 'PENDING')
		self.assertEqual(response.data['git_url'], 'https://github.com/example/task-a')

	def test_get_single_submission_matches_list_payload_shape(self):
		"""The detail payload carries exactly the fields the list returns."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		detail = self.client.get(f'/api/admin/submissions/{submission.id}/')
		listing = self.client.get('/api/admin/submissions/')
		self.assertEqual(detail.status_code, 200)
		self.assertEqual(set(detail.data.keys()), set(listing.data['results'][0].keys()))

	def test_normal_user_cannot_get_single_submission(self):
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.user)
		self.assertEqual(self.client.get(f'/api/admin/submissions/{submission.id}/').status_code, 403)

	def test_unauthenticated_get_single_submission_is_rejected(self):
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		response = self.client.get(f'/api/admin/submissions/{submission.id}/')
		self.assertIn(response.status_code, (401, 403))

	def test_missing_submission_detail_returns_404(self):
		self.authenticate(self.admin)
		self.assertEqual(self.client.get('/api/admin/submissions/999999/').status_code, 404)

	def test_patch_missing_submission_returns_404(self):
		"""Reviewing a nonexistent submission must 404, not 500."""
		self.authenticate(self.admin)
		response = self.client.patch('/api/admin/submissions/999999/', {'status': 'APPROVED'}, format='json')
		self.assertEqual(response.status_code, 404)

	def test_patch_rejects_invalid_status(self):
		"""Only APPROVED/REJECTED are reviewable; anything else is a 400."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		response = self.client.patch(
			f'/api/admin/submissions/{submission.id}/',
			{'status': 'MAYBE', 'feedback': 'x'},
			format='json',
		)
		self.assertEqual(response.status_code, 400)
		submission.refresh_from_db()
		self.assertEqual(submission.status, 'PENDING')

	def test_review_patch_does_not_issue_extra_relation_queries(self):
		"""PATCH + serialized response stays at a bounded query count."""
		from django.db import connection
		from django.test.utils import CaptureQueriesContext

		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			review = self.client.patch(
				f'/api/admin/submissions/{submission.id}/',
				{'status': 'APPROVED', 'feedback': 'Nice work.'},
				format='json',
			)
		self.assertEqual(review.status_code, 200)
		# auth(2: token+user) + savepoints(~2) + submission select + update
		# must stay far below one-query-per-relation growth.
		self.assertLessEqual(len(captured.captured_queries), 10)

	def test_submission_list_has_no_per_row_queries(self):
		"""List query count must not grow with the number of submissions."""
		from django.db import connection
		from django.test.utils import CaptureQueriesContext

		for index in range(30):
			task = Task.objects.create(title=f'Bulk {index}', description='d')
			TaskAssignment.objects.create(task=task, user=self.user)
			TaskSubmission.objects.create(task=task, user=self.user, **self.payload())

		self.authenticate(self.admin)
		with CaptureQueriesContext(connection) as captured:
			response = self.client.get('/api/admin/submissions/')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data['results']), 25)  # default page size
		# token+user auth, paginator COUNT and the page query only — never one
		# extra task/user lookup per serialized row.
		self.assertLessEqual(len(captured.captured_queries), 6)

	def test_review_patch_does_not_leak_into_next_page_load(self):
		"""A reviewed row keeps its status after the admin reloads the list."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'REJECTED'}, format='json')
		listing = self.client.get('/api/admin/submissions/')
		row = next(item for item in listing.data['results'] if item['id'] == submission.id)
		self.assertEqual(row['status'], 'REJECTED')


	def test_patch_still_works_after_get_added(self):
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		self.authenticate(self.admin)
		review = self.client.patch(f'/api/admin/submissions/{submission.id}/', {'status': 'APPROVED', 'feedback': 'ok'}, format='json')
		self.assertEqual(review.status_code, 200)
		detail = self.client.get(f'/api/admin/submissions/{submission.id}/')
		self.assertEqual(detail.status_code, 200)
		self.assertEqual(detail.data['status'], 'APPROVED')
		self.assertEqual(detail.data['feedback'], 'ok')

	def test_preflight_options_allows_get_for_allowlisted_origin(self):
		"""CORS preflight succeeds and permits GET + Authorization header.

		This reproduces the reported symptom path: OPTIONS must answer 200 with
		Access-Control-Allow-Origin so the browser proceeds to the real GET.
		"""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		allowed_origin = settings.CORS_ALLOWED_ORIGINS[0]
		preflight = self.client.options(
			f'/api/admin/submissions/{submission.id}/',
			HTTP_ORIGIN=allowed_origin,
			HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
			HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type',
		)
		self.assertEqual(preflight.status_code, 200)
		self.assertEqual(preflight['Access-Control-Allow-Origin'], allowed_origin)
		methods = {method.strip() for method in preflight.get('Access-Control-Allow-Methods', '').split(',')}
		self.assertIn('GET', methods)

	def test_disallowed_origin_gets_no_cors_grant(self):
		"""A non-allowlisted origin receives no Access-Control-Allow-Origin."""
		submission = TaskSubmission.objects.create(task=self.task, user=self.user, **self.payload())
		preflight = self.client.options(
			f'/api/admin/submissions/{submission.id}/',
			HTTP_ORIGIN='https://evil.example.net',
			HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
		)
		self.assertNotIn('Access-Control-Allow-Origin', preflight)

	def test_normal_user_cannot_review_or_list_submissions(self):
		self.authenticate(self.user)
		self.assertEqual(self.client.get('/api/admin/submissions/').status_code, 403)
		self.assertEqual(self.client.patch('/api/admin/submissions/1/', {'status': 'APPROVED'}, format='json').status_code, 403)


class SubmissionReviewCorsTests(TestCase):
	"""CORS must hold on the ACTUAL PATCH response, including error outcomes.

	django-cors-headers answers every preflight with 200 even for origins it
	will not authorise; the browser then blocks the real PATCH with a CORS
	error. These tests pin Access-Control-Allow-Origin onto real PATCH
	responses for every outcome the review flow can produce.
	"""

	def setUp(self):
		self.client = APIClient()
		self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42')
		self.member = User.objects.create_user(username='member', password='StrongPassword!42')
		task = Task.objects.create(title='Task A', description='d')
		TaskAssignment.objects.create(task=task, user=self.member)
		self.submission = TaskSubmission.objects.create(
			task=task,
			user=self.member,
			git_url='https://github.com/example/task-a',
			linkedin_url='https://www.linkedin.com/in/example',
		)
		self.origin = 'http://localhost:5173'
		self.token = Token.objects.create(user=self.admin)

	def _preflight(self):
		return self.client.options(
			f'/api/admin/submissions/{self.submission.id}/',
			HTTP_ORIGIN=self.origin,
			HTTP_ACCESS_CONTROL_REQUEST_METHOD='PATCH',
			HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type',
		)

	def _patch(self, token=None, payload=None, url=None, origin=None):
		if token:
			self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
		response = self.client.patch(
			url or f'/api/admin/submissions/{self.submission.id}/',
			payload or {'status': 'APPROVED'},
			format='json',
			HTTP_ORIGIN=origin or self.origin,
		)
		return response

	def test_preflight_authorizes_patch_with_auth_headers(self):
		preflight = self._preflight()
		self.assertEqual(preflight.status_code, 200)
		self.assertEqual(preflight.get('Access-Control-Allow-Origin'), self.origin)
		self.assertIn('PATCH', preflight.get('Access-Control-Allow-Methods', ''))
		self.assertIn('authorization', preflight.get('Access-Control-Allow-Headers', '').lower())
		self.assertIn('content-type', preflight.get('Access-Control-Allow-Headers', '').lower())

	def test_successful_admin_patch_response_carries_acao(self):
		actual = self._patch(token=self.token.key, payload={'status': 'APPROVED', 'feedback': 'Nice.'})
		self.assertEqual(actual.status_code, 200)
		self.assertEqual(actual.get('Access-Control-Allow-Origin'), self.origin)
		self.assertEqual(actual.data['status'], 'APPROVED')

	def test_patch_error_responses_still_carry_acao(self):
		cases = [
			(None, None, None, {401, 403}),                                            # anonymous
			(Token.objects.create(user=self.member).key, None, None, {403}),           # non-admin
			(self.token.key, {'status': 'NOPE'}, None, {400}),                         # invalid payload
		]
		for token, payload, url, expected in cases:
			response = self._patch(token=token, payload=payload, url=url)
			self.assertIn(response.status_code, expected)
			self.assertEqual(
				response.get('Access-Control-Allow-Origin'),
				self.origin,
				f'PATCH {response.status_code} lost its CORS header',
			)

	def test_missing_submission_patch_response_carries_acao(self):
		missing_id = TaskSubmission.objects.order_by('-id').values_list('id', flat=True).first() + 1_000_000
		response = self._patch(token=self.token.key, url=f'/api/admin/submissions/{missing_id}/')
		self.assertEqual(response.status_code, 404)
		self.assertEqual(response.get('Access-Control-Allow-Origin'), self.origin)

	def test_disallowed_origin_gets_no_acao_on_patch(self):
		response = self._patch(
			token=self.token.key,
			origin='https://arbitrary-attacker-site.example',
		)
		self.assertNotIn('Access-Control-Allow-Origin', response)

	def test_local_dev_origin_on_any_port_can_patch(self):
		"""Vite may bind another free port; PATCH must still be authorised."""
		for origin in ('http://127.0.0.1:5176', 'http://localhost:5180'):
			response = self._patch(token=self.token.key, origin=origin)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.get('Access-Control-Allow-Origin'), origin)