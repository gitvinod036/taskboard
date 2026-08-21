from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import override_settings
from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = 'StrongPassword!42'

    def test_registration_creates_normal_user_with_hashed_password(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'new-user',
            'email': 'new@example.com',
            'password': self.password,
            'password_confirm': self.password,
            'role': 'ADMIN',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='new-user')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.password, self.password)
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(response.data['user']['role'], 'USER')

    def test_login_and_logout_manage_token(self):
        user = User.objects.create_user(username='member', password=self.password)

        login_response = self.client.post('/api/auth/login/', {
            'username': user.username,
            'password': self.password,
        }, format='json')
        self.assertEqual(login_response.status_code, 200)
        token = login_response.data['token']
        self.assertTrue(Token.objects.filter(key=token, user=user).exists())

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 204)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_admin_can_authenticate_and_user_cannot_access_admin_endpoint(self):
        admin = User.objects.create_superuser(username='admin', password=self.password)
        member = User.objects.create_user(username='member', password=self.password)

        login_response = self.client.post('/api/auth/login/', {
            'username': admin.username,
            'password': self.password,
        }, format='json')
        self.assertEqual(login_response.status_code, 200)
        admin_token = Token.objects.get(user=admin)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {admin_token.key}')
        admin_response = self.client.get('/api/auth/admin-check/')
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(admin_response.data['user']['role'], 'ADMIN')

        member_token = Token.objects.create(user=member)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {member_token.key}')
        self.assertEqual(self.client.get('/api/auth/admin-check/').status_code, 403)

    def test_unauthenticated_requests_are_rejected(self):
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
        self.assertEqual(self.client.get('/api/auth/admin-check/').status_code, 401)

    def test_invalid_credentials_are_rejected_without_sensitive_data(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'missing-user',
            'password': self.password,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('password', response.data)
        self.assertNotIn('token', response.data)

    def test_user_role_is_read_only_and_not_changeable(self):
        user = User.objects.create_user(username='member', password=self.password)
        self.authenticate_user(user)
        response = self.client.patch('/api/auth/me/', {'role': 'ADMIN'}, format='json')
        self.assertEqual(response.status_code, 405)
        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def authenticate_user(self, user):
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_admin_login_returns_admin_role(self):
        admin = User.objects.create_superuser(
            username='Admin',
            email='admin@example.com',
            password='LocalAdminPassword!42',
        )
        authenticated = authenticate(username='Admin', password='LocalAdminPassword!42')
        self.assertIsNotNone(authenticated)
        self.assertTrue(authenticated.is_staff)
        self.assertTrue(authenticated.is_superuser)

        response = self.client.post('/api/auth/login/', {
            'username': 'Admin',
            'password': 'LocalAdminPassword!42',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['role'], 'ADMIN')


class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.password = 'StrongPassword!42'
        self.user = User.objects.create_user(username='member', email='member@example.com', password=self.password)
        self.admin = User.objects.create_superuser(username='admin', email='admin@example.com', password=self.password)

    def reset_payload(self, user, password='NewStrongPassword!42'):
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = PasswordResetTokenGenerator().make_token(user)
        return {'uid': uid, 'token': token, 'new_password': password, 'new_password_confirm': password}

    def test_existing_and_unknown_email_responses_are_identical(self):
        existing = self.client.post('/api/auth/password-reset/', {'email': self.user.email}, format='json')
        unknown = self.client.post('/api/auth/password-reset/', {'email': 'missing@example.com'}, format='json')
        self.assertEqual(existing.status_code, 200)
        self.assertEqual(existing.data, unknown.data)
        self.assertNotIn('member', str(unknown.data))
        self.assertNotIn('USER', str(unknown.data))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FRONTEND_URL='http://localhost:5174')
    def test_reset_email_contains_frontend_reset_url(self):
        response = self.client.post('/api/auth/password-reset/', {'email': self.user.email}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('http://localhost:5174/reset-password/', mail.outbox[0].body)

    def test_admin_and_normal_user_can_reset_password(self):
        for user in (self.user, self.admin):
            response = self.client.post('/api/auth/password-reset-confirm/', self.reset_payload(user), format='json')
            self.assertEqual(response.status_code, 200)
            user.refresh_from_db()
            self.assertTrue(user.check_password('NewStrongPassword!42'))

    def test_invalid_uid_token_mismatch_and_weak_password_are_rejected(self):
        payload = self.reset_payload(self.user)
        invalid_uid = {**payload, 'uid': 'invalid'}
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', invalid_uid, format='json').status_code, 400)
        invalid_token = {**payload, 'token': 'invalid-token'}
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', invalid_token, format='json').status_code, 400)
        mismatch = {**payload, 'new_password_confirm': 'DifferentPassword!42'}
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', mismatch, format='json').status_code, 400)
        weak = {**payload, 'new_password': '123', 'new_password_confirm': '123'}
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', weak, format='json').status_code, 400)

    def test_successful_reset_invalidates_old_password_and_token(self):
        payload = self.reset_payload(self.user)
        response = self.client.post('/api/auth/password-reset-confirm/', payload, format='json')
        self.assertEqual(response.status_code, 200)
        login_old = self.client.post('/api/auth/login/', {'username': self.user.username, 'password': self.password}, format='json')
        login_new = self.client.post('/api/auth/login/', {'username': self.user.username, 'password': 'NewStrongPassword!42'}, format='json')
        self.assertEqual(login_old.status_code, 400)
        self.assertEqual(login_new.status_code, 200)
        self.assertEqual(self.client.post('/api/auth/password-reset-confirm/', payload, format='json').status_code, 400)