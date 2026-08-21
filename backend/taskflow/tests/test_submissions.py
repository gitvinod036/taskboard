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
		self.assertEqual(my_tasks.data[0]['submission']['status'], 'PENDING')

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
		submission_id = listing.data[0]['id']
		review = self.client.patch(f'/api/admin/submissions/{submission_id}/', {'status': 'APPROVED', 'feedback': 'Approved.'}, format='json')
		self.assertEqual(review.status_code, 200)
		self.assertEqual(review.data['status'], 'APPROVED')

	def test_normal_user_cannot_review_or_list_submissions(self):
		self.authenticate(self.user)
		self.assertEqual(self.client.get('/api/admin/submissions/').status_code, 403)
		self.assertEqual(self.client.patch('/api/admin/submissions/1/', {'status': 'APPROVED'}, format='json').status_code, 403)