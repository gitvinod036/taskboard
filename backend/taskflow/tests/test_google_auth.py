from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import GoogleIdentity, GoogleLoginCode

User = get_user_model()


class GoogleAuthTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.google_profile = {
            'sub': 'google-sub-123',
            'email': 'google@example.com',
            'email_verified': True,
            'given_name': 'Google',
            'family_name': 'User',
        }

    @override_settings(GOOGLE_CLIENT_ID='client-id', GOOGLE_CLIENT_SECRET='client-secret')
    @patch('taskflow.views.google_flow')
    def test_google_login_initiation_redirects_and_stores_state(self, flow_factory):
        flow = flow_factory.return_value
        # The view persists the PKCE verifier in the session, which must be a
        # JSON-serializable string (real flows always use a str).
        flow.code_verifier = 'pkce-verifier-123'
        flow.authorization_url.return_value = ('https://accounts.google.com/auth', 'state-123')
        response = self.client.get('/api/auth/google/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('accounts.google.com', response['Location'])
        self.assertEqual(self.client.session['google_oauth_state'], 'state-123')
        self.assertEqual(self.client.session['google_oauth_code_verifier'], 'pkce-verifier-123')

    def test_invalid_state_redirects_without_authentication(self):
        response = self.client.get('/api/auth/google/callback/?state=wrong&code=code')
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.exists())

    @override_settings(GOOGLE_CLIENT_ID='client-id', GOOGLE_CLIENT_SECRET='client-secret')
    @patch('taskflow.views.id_token.verify_oauth2_token')
    @patch('taskflow.views.google_flow')
    def test_verified_google_identity_creates_user_and_one_time_exchange(self, flow_factory, verify_token):
        session = self.client.session
        session['google_oauth_state'] = 'state-123'
        session.save()
        verify_token.return_value = self.google_profile
        response = self.client.get('/api/auth/google/callback/?state=state-123&code=auth-code')
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email='google@example.com')
        self.assertTrue(user.has_usable_password() is False)
        self.assertTrue(GoogleIdentity.objects.filter(subject='google-sub-123', user=user).exists())
        raw_code = parse_qs(urlparse(response['Location']).query)['code'][0]
        exchange = self.client.post('/api/auth/google/exchange/', {'code': raw_code}, format='json')
        self.assertEqual(exchange.status_code, 200)
        self.assertIn('token', exchange.data)

    @override_settings(GOOGLE_CLIENT_ID='client-id', GOOGLE_CLIENT_SECRET='client-secret')
    @patch('taskflow.views.id_token.verify_oauth2_token')
    @patch('taskflow.views.google_flow')
    def test_existing_verified_email_is_linked_without_duplicate_user(self, flow_factory, verify_token):
        user = User.objects.create_user(username='existing', email='google@example.com')
        session = self.client.session
        session['google_oauth_state'] = 'state-123'
        session.save()
        verify_token.return_value = self.google_profile
        response = self.client.get('/api/auth/google/callback/?state=state-123&code=auth-code')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.filter(email='google@example.com').count(), 1)
        self.assertTrue(GoogleIdentity.objects.filter(subject='google-sub-123', user=user).exists())

    def test_exchange_creates_existing_django_token_and_rejects_reuse(self):
        user = User.objects.create_user(username='existing')
        raw_code = 'one-time-code'
        import hashlib
        code = GoogleLoginCode.objects.create(code_hash=hashlib.sha256(raw_code.encode()).hexdigest(), user=user)
        response = self.client.post('/api/auth/google/exchange/', {'code': raw_code}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Token.objects.filter(user=user).exists())
        self.assertEqual(self.client.post('/api/auth/google/exchange/', {'code': raw_code}, format='json').status_code, 400)
        code.refresh_from_db()
        self.assertIsNotNone(code.used_at)

    @override_settings(
        GOOGLE_CLIENT_ID='',
        GOOGLE_CLIENT_SECRET='',
        FRONTEND_URL='http://localhost:5173',
    )
    def test_unconfigured_google_login_redirects_to_frontend_login(self):
        """Regression: with missing credentials the flow must bounce to the
        configured FRONTEND_URL /login page (correct dev port), carrying an
        oauth_error message — never to a dead origin."""
        with override_settings(FRONTEND_URL='http://localhost:5173'):
            response = self.client.get('/api/auth/google/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response['Location']).scheme + '://' + urlparse(response['Location']).netloc,
            'http://localhost:5173',
        )
        self.assertEqual(urlparse(response['Location']).path, '/login')
        self.assertIn('oauth_error', parse_qs(urlparse(response['Location']).query))

    def test_oauth_callback_redirects_to_configured_frontend_origin(self):
        """The one-time-code handoff must land on FRONTEND_URL/oauth/callback."""
        with override_settings(FRONTEND_URL='http://localhost:5173'):
            response = self.client.get('/api/auth/google/callback/?state=wrong&code=code')
        location = urlparse(response['Location'])
        self.assertEqual(f'{location.scheme}://{location.netloc}/oauth/callback'.rstrip('/'),
                         'http://localhost:5173/oauth/callback')