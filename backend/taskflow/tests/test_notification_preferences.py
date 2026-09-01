from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from ..models import NotificationPreference

User = get_user_model()

PREFERENCES_URL = '/api/auth/me/notification-preferences/'


def make_user(username):
	return User.objects.create_user(
		username=username,
		email=f'{username}@example.com',
		password='testpass123',
	)


class NotificationPreferenceModelTests(TestCase):
	def test_defaults_are_all_enabled(self):
		user = make_user('defaults')
		preference = NotificationPreference.objects.create(user=user)
		self.assertTrue(preference.task_assignments)
		self.assertTrue(preference.submission_reviews)
		self.assertTrue(preference.task_deadlines)
		self.assertTrue(preference.admin_announcements)

	def test_one_to_one_user_relationship(self):
		user = make_user('rel')
		created = NotificationPreference.objects.create(user=user)
		self.assertEqual(user.notification_preference, created)
		with self.assertRaises(Exception):
			NotificationPreference.objects.create(user=user)


class NotificationPreferenceAPITests(TestCase):
	def setUp(self):
		self.user = make_user('member')
		self.token = Token.objects.create(user=self.user)
		self.client = APIClient()

	def authenticate(self):
		self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

	def test_unauthenticated_access_is_rejected(self):
		self.assertEqual(self.client.get(PREFERENCES_URL).status_code, 401)
		self.assertEqual(self.client.patch(PREFERENCES_URL, {}, format='json').status_code, 401)

	def test_retrieve_creates_defaults_for_existing_users(self):
		self.authenticate()
		response = self.client.get(PREFERENCES_URL)
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data['task_assignments'])
		self.assertTrue(response.data['submission_reviews'])
		self.assertTrue(response.data['task_deadlines'])
		self.assertTrue(response.data['admin_announcements'])
		self.assertIsNotNone(response.data['updated_at'])
		self.assertTrue(NotificationPreference.objects.filter(user=self.user).exists())

	def test_update_preferences(self):
		self.authenticate()
		response = self.client.patch(PREFERENCES_URL, {
			'task_assignments': False,
			'admin_announcements': False,
		}, format='json')
		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.data['task_assignments'])
		self.assertFalse(response.data['admin_announcements'])
		# Untouched fields keep their defaults.
		self.assertTrue(response.data['submission_reviews'])
		preference = NotificationPreference.objects.get(user=self.user)
		self.assertFalse(preference.task_assignments)
		self.assertFalse(preference.admin_announcements)

	def test_invalid_payload_is_rejected(self):
		self.authenticate()
		response = self.client.patch(PREFERENCES_URL, {'task_assignments': 'maybe'}, format='json')
		self.assertEqual(response.status_code, 400)

	def test_user_isolation(self):
		other = make_user('other')
		other_preference = NotificationPreference.objects.create(user=other)
		self.authenticate()
		response = self.client.patch(PREFERENCES_URL, {'task_deadlines': False}, format='json')
		self.assertEqual(response.status_code, 200)
		other_preference.refresh_from_db()
		self.assertTrue(other_preference.task_deadlines)  # untouched
		preference = NotificationPreference.objects.get(user=self.user)
		self.assertFalse(preference.task_deadlines)