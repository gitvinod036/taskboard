"""Tests for the AI model fallback system (AIClient model chain).

These tests never touch the network: the single-model HTTP layer
(AIClient._post) is patched, and the fallback orchestration
(_post_with_fallback) plus the real views are exercised on top of it.
Only the configured free-tier Gemini models are involved; no other
provider exists anywhere in this code path.
"""
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import CodeSubmission, CodingProblem
from taskflow.services import (
    AIConfigurationError,
    AIProviderError,
    AIClient,
)

User = get_user_model()

PRIMARY = "gemini-3.6-flash"
FALLBACK = "gemini-2.5-flash"
SECRET_KEY_VALUE = "SUPERSECRET-TEST-KEY-123"

VALID_DRAFT = {
    "title": "Build a REST API client module",
    "description": "Create a small Python module that talks to a REST API.",
    "technology": "Python",
    "difficulty": "MEDIUM",
    "requirements": ["Use requests.", "Handle pagination.", "Add unit tests."],
    "expected_outcome": "A reusable module with passing unit tests.",
}

VALID_ANALYSIS = {
    "summary": "A solid two-pointer approach.",
    "correctness": "The approach is generally correct.",
    "bugs": [],
    "code_quality": "Readable and well-named.",
    "time_complexity": "O(n) time",
    "space_complexity": "O(1) space",
    "edge_cases": ["Empty list"],
    "suggestions": ["Add early returns."],
}


def make_client(models=(PRIMARY, FALLBACK)):
    """An AIClient pinned to an explicit model chain for deterministic tests."""
    client = AIClient()
    client.api_key = SECRET_KEY_VALUE
    client.api_keys = [SECRET_KEY_VALUE]
    client.models = list(models)
    client.model = models[0]
    return client


class AIFallbackOrchestrationTests(TestCase):
    """_post_with_fallback: order, stopping conditions, safe failure."""

    def test_primary_success_does_not_attempt_fallback(self):
        client = make_client()
        with patch.object(AIClient, "_post", return_value=VALID_DRAFT) as mock_post:
            result = client._post_with_fallback("prompt")
        self.assertEqual(result, VALID_DRAFT)
        # Exactly one attempt, against the primary model only.
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args.args, ("prompt", PRIMARY))

    def test_primary_503_falls_back_to_next_model(self):
        client = make_client()
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError("AI provider request failed (HTTP 503)"), VALID_DRAFT],
        ) as mock_post:
            result = client._post_with_fallback("prompt")
        self.assertEqual(result, VALID_DRAFT)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(
            [c.args[1] for c in mock_post.call_args_list], [PRIMARY, FALLBACK]
        )

    def test_primary_429_rate_limit_falls_back(self):
        client = make_client()
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError("AI provider request failed (HTTP 429)"), VALID_DRAFT],
        ) as mock_post:
            result = client._post_with_fallback("prompt")
        self.assertEqual(result, VALID_DRAFT)
        self.assertEqual([c.args[1] for c in mock_post.call_args_list], [PRIMARY, FALLBACK])

    def test_transient_network_error_falls_back(self):
        client = make_client()
        with patch.object(
            AIClient, "_post",
            side_effect=[
                AIProviderError("AI provider request failed (transient network error)"),
                VALID_DRAFT,
            ],
        ) as mock_post:
            result = client._post_with_fallback("prompt")
        self.assertEqual(result, VALID_DRAFT)
        self.assertEqual(mock_post.call_count, 2)

    def test_unparsable_model_output_falls_back(self):
        client = make_client()
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError("AI provider returned an unparsable response"), VALID_DRAFT],
        ) as mock_post:
            result = client._post_with_fallback("prompt")
        self.assertEqual(result, VALID_DRAFT)
        self.assertEqual(mock_post.call_count, 2)

    def test_all_models_fail_raises_safe_runtime_error(self):
        client = make_client((PRIMARY, FALLBACK))
        with patch.object(
            AIClient, "_post",
            side_effect=AIProviderError("AI provider request failed (HTTP 503)"),
        ) as mock_post:
            with self.assertRaises(RuntimeError) as caught:
                client._post_with_fallback("prompt")
        # One sequential attempt per configured model — no endless retries.
        self.assertEqual(mock_post.call_count, 2)
        # The surfaced message is the same safe application-level failure.
        self.assertEqual(str(caught.exception), "AI provider request failed")
        self.assertNotIn(SECRET_KEY_VALUE, str(caught.exception))

    def test_non_retryable_error_does_not_fall_back(self):
        client = make_client((PRIMARY, FALLBACK))
        with patch.object(
            AIClient, "_post",
            side_effect=AIConfigurationError("AI provider rejected the request"),
        ) as mock_post:
            with self.assertRaises(RuntimeError):
                client._post_with_fallback("prompt")
        # A rejected request (e.g. bad API key) must not burn the chain.
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(mock_post.call_args.args[1], PRIMARY)

    def test_fallback_logs_helpful_context_without_secrets(self):
        client = make_client()
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError("AI provider request failed (HTTP 503)"), VALID_DRAFT],
        ):
            with self.assertLogs("taskflow.services", level="INFO") as logs:
                client._post_with_fallback("prompt")
        combined = "\n".join(logs.output)
        self.assertIn("AI model attempt failed", combined)
        self.assertIn("fallback", combined)
        self.assertNotIn(SECRET_KEY_VALUE, combined)
        self.assertNotIn(SECRET_KEY_VALUE.lower(), combined.lower())

class AIPostClassificationTests(TestCase):
    """_post maps raw provider outcomes to retryable vs non-retryable errors."""

    @staticmethod
    def _http_payload(text):
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}

    def _run(self, status_code=None, payload=None, exc=None):
        client = make_client()
        if exc is not None:
            with patch("requests.post", side_effect=exc):
                return self._capture(client)
        response = type("R", (), {})()
        response.status_code = status_code
        response.json = lambda: payload
        with patch("requests.post", return_value=response):
            return self._capture(client)

    @staticmethod
    def _capture(client):
        try:
            return client._post("prompt", PRIMARY), None
        except Exception as raised:  # the test asserts the exact type
            return None, raised

    def test_200_with_valid_json_body_returns_dict(self):
        import json as jsonlib
        text = jsonlib.dumps(VALID_DRAFT)
        result, error = self._run(status_code=200, payload=self._http_payload(text))
        self.assertIsNone(error)
        self.assertEqual(result, VALID_DRAFT)

    def test_200_with_markdown_fenced_json_is_stripped_and_parsed(self):
        import json as jsonlib
        text = "```json\n" + jsonlib.dumps(VALID_DRAFT) + "\n```"
        result, error = self._run(status_code=200, payload=self._http_payload(text))
        self.assertIsNone(error)
        self.assertEqual(result, VALID_DRAFT)

    def test_200_with_garbage_body_is_retryable(self):
        _, error = self._run(status_code=200, payload=self._http_payload("not json at all"))
        self.assertIsInstance(error, AIProviderError)

    def test_429_is_retryable(self):
        _, error = self._run(status_code=429, payload={})
        self.assertIsInstance(error, AIProviderError)

    def test_500_502_503_504_are_retryable(self):
        for status in (500, 502, 503, 504):
            _, error = self._run(status_code=status, payload={})
            self.assertIsInstance(error, AIProviderError, f"HTTP {status}")

    def test_404_model_not_found_is_retryable(self):
        _, error = self._run(status_code=404, payload={})
        self.assertIsInstance(error, AIProviderError)

    def test_400_is_not_retryable(self):
        _, error = self._run(status_code=400, payload={})
        self.assertIsInstance(error, AIConfigurationError)
        self.assertNotIsInstance(error, AIProviderError)

    def test_timeout_is_retryable(self):
        _, error = self._run(exc=requests.exceptions.Timeout("timed out"))
        self.assertIsInstance(error, AIProviderError)

    def test_connection_error_is_retryable(self):
        _, error = self._run(exc=requests.exceptions.ConnectionError("conn refused"))
        self.assertIsInstance(error, AIProviderError)

    def test_error_messages_never_contain_the_api_key(self):
        import json as jsonlib
        errors = [
            self._run(status_code=429, payload={})[1],
            self._run(status_code=400, payload={})[1],
            self._run(status_code=200, payload=self._http_payload("garbage"))[1],
            self._run(exc=requests.exceptions.Timeout("timed out"))[1],
        ]
        for error in errors:
            self.assertIsNotNone(error)
            self.assertNotIn(SECRET_KEY_VALUE, str(error))
        # Sanity: a valid body still parses.
        text = jsonlib.dumps(VALID_DRAFT)
        result, error = self._run(status_code=200, payload=self._http_payload(text))
        self.assertIsNone(error)
        self.assertEqual(result, VALID_DRAFT)


class AIModelConfigurationTests(TestCase):
    """AI_MODELS parsing / legacy AI_MODEL backwards compatibility."""

    def test_ai_models_list_is_used_in_order(self):
        with override_settings(AI_MODELS=["model-a", "model-b"]):
            client = AIClient()
        self.assertEqual(client.models, ["model-a", "model-b"])
        self.assertEqual(client.model, "model-a")

    def test_unset_ai_models_falls_back_to_legacy_ai_model(self):
        with override_settings(AI_MODELS=[], AI_MODEL="legacy-model"):
            client = AIClient()
        self.assertEqual(client.models, ["legacy-model"])
        self.assertEqual(client.model, "legacy-model")


@override_settings(
    AI_MODELS=[PRIMARY, FALLBACK],
    GEMINI_API_KEYS=[SECRET_KEY_VALUE, SECRET_KEY_VALUE + "2"],
)
class AIFallbackEndToEndTests(TestCase):
    """The three AI features keep their API contract across model fallback.

    AI_MODELS is pinned to a two-model chain so the fallback leg is
    exercised regardless of the developer's local .env configuration.
    """

    def setUp(self):
        self.api = APIClient()
        self.admin = User.objects.create_superuser(
            username="admin", password="StrongPassword!42", email="admin@example.com")
        self.user = User.objects.create_user(
            username="user", password="StrongPassword!42", email="user@example.com")

    def _auth(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_task_draft_succeeds_via_fallback(self):
        self._auth(self.admin)
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError("AI provider request failed (HTTP 503)"), VALID_DRAFT],
        ):
            response = self.api.post("/api/auth/ai/task-draft/", {"prompt": "REST API task"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], VALID_DRAFT["title"])

    def test_task_draft_returns_safe_503_when_all_models_fail(self):
        self._auth(self.admin)
        # Patch BOTH transports: AIClient._post (Gemini leg) and the global
        # requests.post (Groq/OpenRouter adapters), so every configured
        # provider deterministically fails and no live API quota is consumed.
        with patch.object(
            AIClient, "_post",
            side_effect=AIProviderError("AI provider request failed (HTTP 503)"),
        ), patch("requests.post", side_effect=requests.ConnectionError("mock")):
            response = self.api.post("/api/auth/ai/task-draft/", {"prompt": "REST API task"})
        self.assertEqual(response.status_code, 503)
        rendered = str(response.data).lower()
        self.assertNotIn("gemini", rendered)
        self.assertNotIn("http 503", rendered)
        self.assertNotIn("api key", rendered)
        self.assertNotIn("traceback", rendered)
        self.assertNotIn(SECRET_KEY_VALUE, str(response.data))

    def test_invalid_input_is_rejected_before_any_ai_attempt(self):
        self._auth(self.admin)
        with patch.object(AIClient, "_post") as mock_post:
            response = self.api.post("/api/auth/ai/task-draft/", {"prompt": ""})
        self.assertEqual(response.status_code, 400)
        mock_post.assert_not_called()

    def test_coding_problem_generation_succeeds_via_fallback(self):
        self._auth(self.admin)
        problem = {
            "title": "Two Sum",
            "description": "Sum two numbers.",
            "difficulty": "EASY",
            "input_format": "N X then N integers.",
            "output_format": "Two indices.",
            "constraints": "1 <= N <= 100",
            "examples": [{"input": "2 3\n1 2", "output": "0 1", "explanation": "ok"}],
            "explanation": "Use a map.",
            "starter_code": {"python": "pass", "javascript": "", "java": "", "cpp": ""},
            "allowed_languages": ["python", "javascript", "java", "cpp"],
            "public_test_cases": [{"input": "2 3\n1 2", "expected_output": "0 1"}],
            "hidden_test_cases": [{"input": "1 5\n5", "expected_output": "0"}],
        }
        # _post returns the already-parsed JSON object (dict), not raw text.
        with patch.object(
            AIClient, "_post",
            side_effect=[
                AIProviderError("AI provider request failed (HTTP 429)"),
                problem,
            ],
        ):
            response = self.api.post(
                "/api/admin/coding/problems/generate/",
                {"title": "Two Sum", "idea": "Two numbers sum to target"})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(CodingProblem.objects.filter(title="Two Sum").exists())

    def _make_problem_and_submission(self, with_hidden=True):
        problem = CodingProblem.objects.create(
            title="Two Sum", description="Sum two numbers.", difficulty="EASY",
            input_format="N X then N integers.", output_format="Two indices.",
            constraints="1 <= N <= 100", explanation="",
            starter_code={"python": "pass"}, allowed_languages=["python"],
            status=CodingProblem.Status.PUBLISHED, created_by=self.admin,
            published_at="2026-01-01T00:00:00Z")
        if with_hidden:
            from taskflow.models import CodingProblemTestCase
            CodingProblemTestCase.objects.create(
                problem=problem, input="SECRET-HIDDEN", expected_output="SECRET-OUT",
                is_hidden=True, order=1001)
        submission = CodeSubmission.objects.create(
            user=self.user, problem=problem, language="python",
            source_code="def solve(nums):\n    return [0, 1]\n",
            status=CodeSubmission.Status.ACCEPTED, passed_tests=2, total_tests=2,
            execution_time=0.02, memory_used=8.0)
        return submission

    def test_submission_analysis_succeeds_via_fallback(self):
        self._auth(self.user)
        submission = self._make_problem_and_submission()
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError("AI provider request failed (HTTP 503)"), VALID_ANALYSIS],
        ):
            response = self.api.post(f"/api/coding/submissions/{submission.id}/analyze/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["analysis"]["summary"], VALID_ANALYSIS["summary"])
        # Judge fields untouched by AI; hidden data never leaves the server.
        submission.refresh_from_db()
        self.assertEqual(submission.status, CodeSubmission.Status.ACCEPTED)
        self.assertNotIn("SECRET-HIDDEN", response.content.decode())

    def test_submission_analysis_returns_safe_503_when_all_models_fail(self):
        self._auth(self.user)
        submission = self._make_problem_and_submission(with_hidden=False)
        # Patch BOTH transports (Gemini leg + Groq/OpenRouter adapters) so
        # every configured provider fails deterministically without any
        # live API call. Adapters import requests locally but resolve
        # requests.post as a module attribute at call time, so patching the
        # global requests.post intercepts all providers.
        with patch.object(
            AIClient, "_post",
            side_effect=AIProviderError("AI provider request failed (HTTP 503)"),
        ), patch("requests.post", side_effect=requests.ConnectionError("mock")):
            response = self.api.post(f"/api/coding/submissions/{submission.id}/analyze/")
        self.assertEqual(response.status_code, 503)
        rendered = str(response.data).lower()
        self.assertNotIn("gemini", rendered)
        self.assertNotIn("http 503", rendered)
        self.assertNotIn("api key", rendered)
        self.assertNotIn(SECRET_KEY_VALUE, str(response.data))
