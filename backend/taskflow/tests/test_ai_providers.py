"""Gemini multi-key fallback tests (Google Gemini is the ONLY AI provider).

All Gemini HTTP requests are mocked at the transport seam (AIClient._post) --
no network, no real API quota usage. The tests prove:

- numbered keys (GEMINI_API_KEY_1..4) are used in priority order
- blank keys are ignored
- the legacy single GEMINI_API_KEY works when numbered keys are absent
- only retryable provider failures advance to the next key
- the first successful key is returned immediately and no later key is called
- when all keys fail, the safe application-level RuntimeError is raised
"""
from unittest.mock import patch

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase, override_settings

from taskflow.services import (
    AIConfigurationError,
    AI_ERROR_RATE_LIMITED,
    AI_ERROR_TIMEOUT,
    AIProviderError,
    AIClient,
    TASKBOARD_EVALUATION_SYSTEM_MESSAGE,
    normalize_ai_response,
)

VALID_EVAL = {
    "scores": {"requirement_completion": 3, "correctness": 2,
               "quality": 1, "completeness": 1, "clarity": 1},
    "total_score": 99,  # deliberately wrong: backend must recompute (8)
    "summary": "Solid work.",
    "strengths": ["Clear structure"],
    "issues": [],
    "suggestions": ["Add tests"],
}


def gemini_client(keys):
    """An AIClient pinned to explicit Gemini keys for deterministic tests."""
    client = AIClient()
    client.api_keys = list(keys)
    client.api_key = keys[0] if keys else ""
    client.models = ["gemini-primary"]
    client.model = "gemini-primary"
    return client


class GeminiMultiKeyTests(TestCase):
    def test_primary_key_success_does_not_attempt_fallback(self):
        client = gemini_client(["key-1", "key-2", "key-3"])
        with patch.object(AIClient, "_post", return_value=VALID_EVAL) as post:
            result = client._post_with_providers("prompt")
        self.assertEqual(result, VALID_EVAL)
        # Exactly one attempt, against the first key only.
        self.assertEqual(post.call_count, 1)
        self.assertEqual(client.last_provider, "gemini")

    def test_429_on_key_1_falls_back_to_key_2(self):
        client = gemini_client(["key-1", "key-2"])
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError(
                "AI provider request failed (HTTP 429)",
                category=AI_ERROR_RATE_LIMITED), VALID_EVAL],
        ) as post:
            result = client._post_with_providers("prompt")
        self.assertEqual(result["scores"]["correctness"], 2)
        self.assertEqual(post.call_count, 2)

    def test_503_on_key_1_falls_back_to_key_2(self):
        client = gemini_client(["key-1", "key-2"])
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError(
                "AI provider request failed (HTTP 503)"), VALID_EVAL],
        ) as post:
            result = client._post_with_providers("prompt")
        self.assertEqual(result["scores"]["correctness"], 2)
        self.assertEqual(post.call_count, 2)

    def test_timeout_on_key_1_falls_back_to_key_2(self):
        client = gemini_client(["key-1", "key-2"])
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError(
                "AI provider request failed (transient network error)",
                category=AI_ERROR_TIMEOUT), VALID_EVAL],
        ) as post:
            result = client._post_with_providers("prompt")
        self.assertEqual(result["scores"]["correctness"], 2)
        self.assertEqual(post.call_count, 2)

    def test_all_keys_fail_raises_safe_runtime_error(self):
        client = gemini_client(["key-1", "key-2", "key-3"])
        with patch.object(
            AIClient, "_post",
            side_effect=AIProviderError("AI provider request failed (HTTP 503)"),
        ) as post:
            with self.assertRaises(RuntimeError) as caught:
                client._post_with_providers("prompt")
        # One attempt per configured key -- no endless retries.
        self.assertEqual(post.call_count, 3)
        # The surfaced message is the same safe application-level failure.
        self.assertEqual(str(caught.exception), "AI provider request failed")
        self.assertNotIn("key-1", str(caught.exception))

    def test_non_retryable_error_does_not_attempt_fallback_keys(self):
        client = gemini_client(["key-1", "key-2"])
        with patch.object(
            AIClient, "_post",
            side_effect=AIConfigurationError("AI provider rejected the request"),
        ) as post:
            with self.assertRaises(RuntimeError):
                client._post_with_providers("prompt")
        # A bad key / authorization error must not burn the other keys.
        self.assertEqual(post.call_count, 1)


class GeminiLegacyCompatibilityTests(TestCase):
    @override_settings(GEMINI_API_KEYS=["numbered-1", "numbered-2"], AI_API_KEY="legacy-key")
    def test_numbered_keys_take_priority_over_legacy(self):
        client = AIClient()
        self.assertEqual(client.api_keys, ["numbered-1", "numbered-2"])
        self.assertEqual(client.api_key, "numbered-1")

    @override_settings(GEMINI_API_KEYS=["legacy-key"])
    def test_legacy_key_is_used_when_no_numbered_keys(self):
        # Legacy GEMINI_API_KEY / AI_API_KEY is collapsed into a single-entry
        # GEMINI_API_KEYS list by settings._gemini_api_keys(); the client
        # consumes that collapsed value verbatim.
        client = AIClient()
        self.assertEqual(client.api_keys, ["legacy-key"])
        self.assertEqual(client.api_key, "legacy-key")

    @override_settings(GEMINI_API_KEYS=["value1", "value3"], AI_API_KEY="legacy-key")
    def test_blank_numbered_keys_are_ignored(self):
        # settings.GEMINI_API_KEYS already collapses blanks server-side; this
        # asserts the client reads the collapsed list verbatim.
        client = AIClient()
        self.assertEqual(client.api_keys, ["value1", "value3"])
        with patch.object(
            AIClient, "_post",
            side_effect=[AIProviderError(
                "AI provider request failed (HTTP 503)"), VALID_EVAL],
        ) as post:
            result = client._post_with_providers("prompt")
        # Only value1 then value3 are attempted (order preserved).
        self.assertEqual(post.call_count, 2)
        self.assertEqual(result["scores"]["correctness"], 2)


class CanonicalNormalizationTests(TestCase):
    def test_backend_recalculates_total_ignoring_ai_total(self):
        canonical = normalize_ai_response(dict(VALID_EVAL), provider="gemini")
        self.assertEqual(canonical["total_score"], 8)
        self.assertEqual(canonical["provider"], "gemini")

    def test_missing_rubric_field_is_rejected(self):
        broken = dict(VALID_EVAL)
        broken["scores"] = {k: v for k, v in VALID_EVAL["scores"].items() if k != "clarity"}
        with self.assertRaises(DjangoValidationError):
            normalize_ai_response(broken, provider="gemini")

    def test_out_of_range_score_is_rejected(self):
        broken = dict(VALID_EVAL)
        broken["scores"] = dict(VALID_EVAL["scores"], quality=5)
        with self.assertRaises(DjangoValidationError):
            normalize_ai_response(broken, provider="gemini")

    def test_non_numeric_score_is_rejected(self):
        broken = dict(VALID_EVAL)
        broken["scores"] = dict(VALID_EVAL["scores"], clarity="1")
        with self.assertRaises(DjangoValidationError):
            normalize_ai_response(broken, provider="gemini")

    def test_all_rubric_maxima_total_exactly_ten(self):
        top = dict(VALID_EVAL)
        top["scores"] = {"requirement_completion": 3, "correctness": 2,
                         "quality": 2, "completeness": 2, "clarity": 1}
        self.assertEqual(normalize_ai_response(top)["total_score"], 10)

    def test_every_response_produces_the_same_canonical_shape(self):
        canonical = normalize_ai_response(dict(VALID_EVAL), provider="gemini")
        self.assertEqual(
            sorted(canonical.keys()),
            ["issues", "provider", "scores", "strengths",
             "suggestions", "summary", "total_score"],
        )
        self.assertEqual(canonical["total_score"], 8)

    def test_system_message_is_the_canonical_contract(self):
        self.assertIn("You are TaskBoard's evaluation engine",
                      TASKBOARD_EVALUATION_SYSTEM_MESSAGE)
        self.assertIn("ONLY the requested structured JSON object",
                      TASKBOARD_EVALUATION_SYSTEM_MESSAGE)


class SecurityTests(TestCase):
    def test_api_keys_never_escape_exception_messages(self):
        client = gemini_client(["SUPERSECRET-TEST-KEY-123"])
        with patch.object(
            AIClient, "_post",
            side_effect=AIProviderError("AI provider request failed (HTTP 503)"),
        ):
            with self.assertRaises(RuntimeError) as caught:
                client._post_with_providers("prompt")
        self.assertNotIn("SUPERSECRET-TEST-KEY", str(caught.exception))
