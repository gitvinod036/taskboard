from django.conf import settings
from django.test import TestCase
from rest_framework.test import APIClient


class CorsConfigurationTests(TestCase):
	"""CORS must behave as a strict allowlist, never allow-all."""

	def setUp(self):
		self.client = APIClient()

	def _origin_response(self, origin):
		return self.client.get(
			'/api/tasks/tech-stacks/',
			HTTP_ORIGIN=origin,
		)

	def test_allow_all_is_not_enabled(self):
		self.assertFalse(getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False))

	def test_arbitrary_origin_is_rejected(self):
		response = self._origin_response('https://arbitrary-attacker-site.example')
		self.assertNotIn('Access-Control-Allow-Origin', response)

	def test_allowlisted_origin_is_accepted(self):
		allowed = settings.CORS_ALLOWED_ORIGINS
		if not allowed:
			self.skipTest('No CORS_ALLOWED_ORIGINS configured in this environment.')
		response = self._origin_response(allowed[0])
		self.assertIn('Access-Control-Allow-Origin', response)
		self.assertEqual(response['Access-Control-Allow-Origin'], allowed[0])

	def test_preflight_from_arbitrary_origin_is_rejected(self):
		response = self.client.options(
			'/api/tasks/',
			HTTP_ORIGIN='https://arbitrary-attacker-site.example',
			HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
		)
		self.assertNotIn('Access-Control-Allow-Origin', response)


class CorsActualGetResponseTests(TestCase):
	"""The ACTUAL GET response (not just OPTIONS) must carry ACAO.

	django-cors-headers answers every preflight with 200, even for origins it
	will not authorise; the browser then blocks the real GET with a CORS error.
	These tests pin the header onto real GET responses.
	"""

	def setUp(self):
		self.client = APIClient()

	def _get(self, origin):
		return self.client.get('/api/tasks/tech-stacks/', HTTP_ORIGIN=origin)

	def test_get_response_has_acao_for_localhost_5173(self):
		response = self._get('http://localhost:5173')
		self.assertEqual(response.get('Access-Control-Allow-Origin'), 'http://localhost:5173')

	def test_get_response_has_acao_for_loopback_ip_5173(self):
		response = self._get('http://127.0.0.1:5173')
		self.assertEqual(response.get('Access-Control-Allow-Origin'), 'http://127.0.0.1:5173')

	def test_get_response_has_acao_when_vite_bumps_port(self):
		"""Vite moves to another free port when 5173 is busy — must still work."""
		for origin in ('http://localhost:5175', 'http://127.0.0.1:5176'):
			response = self._get(origin)
			self.assertEqual(
				response.get('Access-Control-Allow-Origin'),
				origin,
				f'Missing ACAO on actual GET for dev origin {origin}',
			)

	def test_preflight_and_actual_get_agree_for_every_local_port(self):
		"""OPTIONS 200 must never be followed by a GET that lacks ACAO."""
		origin = 'http://localhost:5179'
		preflight = self.client.options(
			'/api/tasks/tech-stacks/',
			HTTP_ORIGIN=origin,
			HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
			HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization,content-type',
		)
		actual = self._get(origin)
		self.assertEqual(preflight.status_code, 200)
		# tech-stacks requires auth, so an unauthenticated GET is a 401 — what
		# matters is that CORS headers are present on the actual response.
		self.assertEqual(actual.status_code, 401)
		self.assertEqual(preflight.get('Access-Control-Allow-Origin'), origin)
		self.assertEqual(actual.get('Access-Control-Allow-Origin'), origin)

	def test_non_local_origin_still_requires_exact_allowlisting(self):
		"""The regex only relaxes local hosts; remote origins stay strict."""
		response = self._get('https://arbitrary-attacker-site.example')
		self.assertNotIn('Access-Control-Allow-Origin', response)

	def test_https_local_origin_is_not_granted(self):
		"""Only plain-http local dev origins are relaxed by the regex."""
		response = self._get('https://localhost:5173')
		self.assertNotIn('Access-Control-Allow-Origin', response)
