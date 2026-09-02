from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import CodingProblem, CodingProblemTestCase

User = get_user_model()

LOCAL_ORIGIN = "http://localhost:5174"


class CorsPublishTests(TestCase):
    """The publish PATCH must carry CORS headers on every response class.

    django-cors-headers answers a disallowed-origin preflight with 200 but no
    Access-Control-Allow-Origin, so an "OPTIONS returned 200" in DevTools does
    not prove the origin is allowed — the actual PATCH then fails with a
    browser CORS error. These tests pin the header on preflight, success and
    error responses for the local Vite dev origin.
    """

    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=False)
        self.admin = User.objects.create_user(
            username="corsadmin", password="pass12345", is_staff=True
        )
        if hasattr(self.admin, "role"):
            self.admin.role = User.Role.ADMIN
            self.admin.save()
        self.token = Token.objects.create(user=self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.problem = CodingProblem.objects.create(title="Draft", status=CodingProblem.Status.DRAFT)
        # A fully complete problem that passes strict publish validation.
        self.complete = CodingProblem.objects.create(
            title="Valid problem",
            description="desc",
            difficulty="EASY",
            input_format="in",
            output_format="out",
            constraints="none",
            status=CodingProblem.Status.DRAFT,
        )
        CodingProblemTestCase.objects.create(problem=self.complete, input="1", expected_output="1", is_hidden=False, order=0)
        CodingProblemTestCase.objects.create(problem=self.complete, input="2", expected_output="2", is_hidden=True, order=1)

    def _origin_headers(self):
        return {"HTTP_ORIGIN": LOCAL_ORIGIN}

    def test_preflight_options_allows_local_dev_origin(self):
        response = self.client.options(
            f"/api/admin/coding/problems/{self.problem.id}/",
            HTTP_ORIGIN=LOCAL_ORIGIN,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="PATCH",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization,content-type",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], LOCAL_ORIGIN)
        self.assertIn("PATCH", response["Access-Control-Allow-Methods"])

    def test_publish_patch_response_carries_cors_header(self):
        response = self.client.patch(
            f"/api/admin/coding/problems/{self.complete.id}/",
            data={"status": "PUBLISHED"},
            content_type="application/json",
            **self._origin_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], LOCAL_ORIGIN)

    def test_validation_error_response_carries_cors_header(self):
        response = self.client.patch(
            f"/api/admin/coding/problems/{self.problem.id}/",
            data={"status": "PUBLISHED"},  # invalid: incomplete publish data
            content_type="application/json",
            **self._origin_headers(),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Access-Control-Allow-Origin"], LOCAL_ORIGIN)

    def test_unauthenticated_response_carries_cors_header(self):
        anon = APIClient(enforce_csrf_checks=False)
        response = anon.patch(
            f"/api/admin/coding/problems/{self.problem.id}/",
            data={"title": "x"},
            content_type="application/json",
            **self._origin_headers(),
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Access-Control-Allow-Origin"], LOCAL_ORIGIN)

    def test_other_5173_origin_still_allowed(self):
        response = self.client.options(
            f"/api/admin/coding/problems/{self.problem.id}/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="PATCH",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:5173")

    def test_settings_include_local_dev_origins_even_with_env_override(self):
        # The regression this file guards against: an env-provided
        # CORS_ALLOWED_ORIGINS value replacing the local dev origins.
        self.assertIn(LOCAL_ORIGIN, settings.CORS_ALLOWED_ORIGINS)
        self.assertIn("http://localhost:5173", settings.CORS_ALLOWED_ORIGINS)
