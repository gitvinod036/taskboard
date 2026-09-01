"""
Domain services including AI generation.
"""
import json
import logging
from collections import defaultdict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction

from .models import (
    CodingProblem, CodingProblemTestCase, SubmissionAnalysis,
    DIFFICULTY_POINTS, CodeSubmission, Notification, TaskEvaluation, TaskSubmission,
)

logger = logging.getLogger(__name__)


# Schema the AI must satisfy. Kept explicit so malformed LLM output can
# never silently corrupt the database.
AI_PROBLEM_SCHEMA_FIELDS = [
    "title", "description", "difficulty", "input_format",
    "output_format", "constraints", "examples", "explanation",
    "starter_code", "allowed_languages", "public_test_cases",
    "hidden_test_cases",
]
VALID_DIFFICULTIES = ("EASY", "MEDIUM", "HARD")

# Task-draft AI feature (first Gemini integration). A draft generator only:
# nothing here touches the Task model — the admin reviews the returned data
# and creates the task through the existing task-creation flow.
TASK_DRAFT_SCHEMA_FIELDS = [
    "title", "description", "technology", "difficulty",
    "requirements", "expected_outcome",
]
MAX_TASK_DRAFT_PROMPT_LENGTH = 2000
VALID_DIFFICULTIES = ("EASY", "MEDIUM", "HARD")


# --- AI provider failure classification (model fallback system) ---
# Provider/model failures that are safe to retry with the NEXT configured
# model. Includes rate limiting, quota exhaustion, transient 5xx, unknown or
# unavailable models, request timeout and connection failures.
AI_RETRYABLE_STATUS_CODES = frozenset({404, 408, 425, 429, 500, 502, 503, 504})


class AIProviderError(RuntimeError):
    """Retryable AI provider/model failure (e.g. 429, 5xx, timeout).

    Signals that the next configured fallback model/provider may be attempted.
    Messages are always application-safe: they never contain the API key,
    the request URL or any raw provider response body.

    `category` is one of the AI_ERROR_* categories below and is used for safe
    server-side logging only — it never reaches the frontend.
    """

    def __init__(self, message, category="UNKNOWN_PROVIDER_ERROR"):
        super().__init__(message)
        self.category = category


# Normalized provider-failure categories (internal only; never exposed).
AI_ERROR_RATE_LIMITED = "RATE_LIMITED"
AI_ERROR_TIMEOUT = "TIMEOUT"
AI_ERROR_TEMPORARY = "TEMPORARY_PROVIDER_ERROR"
AI_ERROR_INVALID_RESPONSE = "INVALID_RESPONSE"
AI_ERROR_AUTHENTICATION = "AUTHENTICATION_ERROR"
AI_ERROR_UNKNOWN = "UNKNOWN_PROVIDER_ERROR"
# Categories that justify moving on to the next provider.
AI_RETRYABLE_CATEGORIES = frozenset({
    AI_ERROR_RATE_LIMITED, AI_ERROR_TIMEOUT, AI_ERROR_TEMPORARY,
})


class AIConfigurationError(RuntimeError):
    """Non-retryable AI failure (e.g. invalid API key, rejected request).

    Falling back to another model cannot help, so it propagates immediately
    without trying the remaining models. Application bugs and validation
    errors never reach this class — they raise their own exceptions.
    """


class AIClient:
    """Clean interface over the configured AI provider.

    No hardcoded keys: reads AI_API_KEY / AI_MODEL / AI_MODELS from Django
    settings (env-driven). Returns only the validated JSON structure; the
    view never trusts the raw LLM output directly.

    Model fallback: every AI operation is attempted against each entry of
    AI_MODELS strictly in order, sequentially, with no retries per model.
    The first successful response is returned immediately. Only retryable
    provider failures (AIProviderError) move on to the next model; all
    models failing raises the same safe RuntimeError the views already
    translate into a 503. There is no startup health check and no
    pre-pinging of models — fallback happens only inside a real request.
    """

    def __init__(self):
        # Ordered Gemini API keys (server-side only): numbered GEMINI_API_KEY_1..4
        # take priority (blank values ignored); otherwise the legacy single
        # GEMINI_API_KEY / AI_API_KEY is used. Gemini is the ONLY provider.
        self.api_keys = list(getattr(settings, "GEMINI_API_KEYS", None) or [])
        self.api_key = self.api_keys[0] if self.api_keys else ""
        # gemini-2.5-flash is unavailable to new Google AI keys; 3.6-flash is current.
        self.models = list(getattr(settings, "AI_MODELS", None) or []) or [
            getattr(settings, "AI_MODEL", "gemini-3.6-flash")
        ]
        # Primary model (kept for backwards compatibility with the previous
        # single-model interface).
        self.model = self.models[0]
        self.base_url = getattr(
            settings,
            "AI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/models",
        )

    @property
    def configured(self):
        return bool(self.api_key)

    def _post(self, prompt, model=None):
        """Perform a single HTTP attempt against one AI model via requests.

        Returns parsed JSON, or raises AIProviderError (retryable: another
        model may succeed) or AIConfigurationError (non-retryable). Isolated
        from the model layer so a bad response is never persisted. Raised
        messages never include the API key, URL, prompt or provider body —
        requests' HTTPError text embeds the key in the URL, so exception
        strings from requests must never be surfaced or logged.
        """
        import requests  # local import keeps the dependency optional
        model = model or self.models[0]
        url = f"{self.base_url}/{model}:generateContent?key={self.api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
        timeout = getattr(settings, "AI_REQUEST_TIMEOUT", 30)
        try:
            resp = requests.post(url, json=payload, timeout=timeout, headers=headers)
        except requests.exceptions.RequestException:
            # Timeout, connection failure, DNS error... transient by nature.
            raise AIProviderError("AI provider request failed (transient network error)")
        if resp.status_code >= 400:
            if resp.status_code in AI_RETRYABLE_STATUS_CODES:
                # Rate limit / quota / 5xx / unknown or unavailable model.
                raise AIProviderError(
                    f"AI provider request failed (HTTP {resp.status_code})"
                )
            # 400 (e.g. invalid API key) / 401 / 403: another model cannot
            # fix these, so do not burn the fallback chain on them.
            raise AIConfigurationError("AI provider rejected the request")
        try:
            raw_json = resp.json()
            text = (
                raw_json.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            # Strip any surrounding markdown fences the model may have added.
            text = text.strip()
            if text.startswith("```json"):
                text = text[len("```json"):]
            if text.endswith("```"):
                text = text[:-3]
            return json.loads(text.strip())
        except (ValueError, KeyError, IndexError, TypeError):
            # 2xx response that cannot be parsed into usable JSON — treated
            # as a provider failure so the next model may be tried.
            raise AIProviderError("AI provider returned an unparsable response")

    def _post_with_fallback(self, prompt):
        """Run _post against each configured model in order until one succeeds.

        Sequential (never parallel), one attempt per model, no re-tries of a
        model that just failed. Stops immediately on the first success. A
        non-retryable AIConfigurationError propagates without fallback.
        When every model fails, raises the same safe RuntimeError the
        application already maps to a controlled 503 response.
        """
        models = self.models
        last_error = None
        for index, model in enumerate(models):
            try:
                return self._post(prompt, model)
            except AIProviderError as exc:
                last_error = exc
                if index < len(models) - 1:
                    # Safe, secret-free context: model name + app-level reason.
                    logger.warning(
                        "AI model attempt failed (model=%s): %s; trying fallback AI model",
                        model, exc,
                    )
                else:
                    logger.warning(
                        "AI model attempt failed (model=%s): %s; no fallback models remain",
                        model, exc,
                    )
        raise RuntimeError("AI provider request failed") from last_error

    # Gemini key-fallback layer: Google Gemini is the single AI provider.
    last_provider = "gemini"

    @property
    def any_provider_configured(self):
        """True when at least one Gemini API key is configured."""
        return bool(self.api_keys)

    def _post_with_providers(self, prompt, system=""):
        """Run the prompt across the configured Gemini API keys in priority order.

        Google Gemini is the single AI provider. Keys are attempted strictly in
        order (GEMINI_API_KEY_1..4, or the legacy single key); the first success
        is returned immediately. Each key attempt keeps the existing per-model
        fallback chain. Only retryable provider failures (429 / rate limit /
        quota / 5xx / model unavailable / timeout / connection error) advance to
        the next key; safe metadata is logged. Non-retryable AIConfigurationError
        propagates immediately. No startup health checks: fallback happens only
        inside a real AI request.
        """
        last_error = None
        key_count = len(self.api_keys)
        for index in range(key_count):
            key_position = index + 1
            try:
                # Use THIS key for the current attempt (the model-level fallback
                # chain runs inside _post_with_fallback against this key).
                self.api_key = self.api_keys[index]
                result = self._post_with_fallback(prompt)
                return result
            except AIConfigurationError:
                logger.warning("Gemini API key attempt failed and is non-retryable (key=%s)", key_position)
                raise
            except (AIProviderError, RuntimeError) as exc:
                last_error = exc
                category = getattr(exc, "category", AI_ERROR_UNKNOWN)
                if key_position < key_count:
                    logger.warning("Gemini API key attempt failed; trying next configured key (key=%s category=%s)", key_position, category)
                else:
                    logger.warning("Gemini API key attempt failed; no configured fallback keys remain (key=%s category=%s)", key_position, category)
        raise RuntimeError("AI provider request failed") from last_error


    def generate_problem(self, title, idea):
        """Return a freshly generated problem dict (unvalidated by caller)."""
        prompt = f"""
Generate a complete competitive-coding problem suitable for review by a senior engineer. Return ONLY valid JSON (no prose, no markdown fences) matching this exact schema:

{{
  "title": string,
  "description": string,
  "difficulty": "EASY" | "MEDIUM" | "HARD",
  "input_format": string,
  "output_format": string,
  "constraints": string,
  "examples": [ {{"input": string, "output": string, "explanation": string}} ],
  "explanation": string,
  "starter_code": {{ "python": string, "javascript": string, "java": string, "cpp": string }},
  "allowed_languages": ["python","javascript","java","cpp"],
  "public_test_cases": [ {{"input": string, "expected_output": string}} ],
  "hidden_test_cases": [ {{"input": string, "expected_output": string}} ]
}}

Problem idea:
title: {title}
idea: {idea}

Constraints you MUST follow:
- difficulty must be one of EASY, MEDIUM, HARD
- starter_code and allowed_languages must cover exactly: python, javascript, java, cpp
- you must return at least 1 public_test_case and at least 1 hidden_test_case
- every value must be a string (never null) unless it is part of the examples/test_cases arrays
"""
        return self._post_with_providers(prompt)


    def generate_task_draft(self, prompt):
        """Return a raw task-draft dict (unvalidated; caller must validate)."""
        task_prompt = f"""
You are assisting an administrator of a task-management application. Generate a single task draft. Return ONLY valid JSON (no prose, no markdown fences) matching this exact schema:

{{
  "title": string,
  "description": string,
  "technology": string,
  "difficulty": "EASY" | "MEDIUM" | "HARD",
  "requirements": [string],
  "expected_outcome": string
}}

Constraints you MUST follow:
- title: concise, under 200 characters
- description: 2-5 sentences describing the task
- technology: the primary technology or framework involved
- difficulty must be exactly one of EASY, MEDIUM, HARD
- requirements: 3-6 short actionable strings
- expected_outcome: one or two sentences describing what completion looks like
- never include executable code that should be run automatically

Task request:
{prompt}
"""
        return self._post_with_providers(task_prompt)

    def analyze_submission(self, context_text):
        """Return a raw submission-analysis dict (unvalidated; caller must validate)."""
        analysis_prompt = f"""
You are a code-review assistant for a learning platform. Analyze the submission described below and return ONLY valid JSON (no prose, no markdown fences) matching this exact schema:

{{
  "summary": string,
  "correctness": string,
  "bugs": [string],
  "code_quality": string,
  "time_complexity": string,
  "space_complexity": string,
  "edge_cases": [string],
  "suggestions": [string]
}}

Constraints you MUST follow:
- summary: 2-4 sentences written for the student
- correctness: qualitative assessment of the approach; you are NOT the judge. Never claim the code passed or failed overall — the platform's judge result is provided separately in the context and you must refer to it only as "the judge result".
- bugs: concrete likely bugs or failure points (empty list if none)
- code_quality: readability, naming, structure
- time_complexity / space_complexity: e.g. "O(n log n) time", short strings
- edge_cases: edge cases the solution may miss (empty list if none)
- suggestions: 2-5 concrete, actionable improvements

Submission context:
{context_text}
"""
        return self._post_with_providers(analysis_prompt)

    def evaluate_task(self, context_text):
        """Return a raw normal-task evaluation dict (unvalidated; caller validates).

        Uses the SAME free-tier Gemini model chain / fallback orchestration as
        every other AI operation in this application. The fixed 10-point
        rubric is embedded in the prompt so the model can never choose its
        own scoring criteria; the caller still re-derives the total.
        """
        evaluation_prompt = f"""
You are a strict task-work evaluator for a learning platform. Evaluate the task submission described below against the FIXED rubric and return ONLY valid JSON (no prose, no markdown fences) matching this exact schema:

{{
  "summary": string,
  "scores": {{
    "requirement_completion": integer 0-3,
    "correctness": integer 0-2,
    "quality": integer 0-2,
    "completeness": integer 0-2,
    "clarity": integer 0-1
  }},
  "strengths": [string],
  "issues": [string],
  "suggestions": [string]
}}

Hard rules:
- The rubric above is fixed. Never invent other categories or limits.
- Score only evidence present in the submission; never assume unshown work.
- Do not reward missing requirements; do not penalize standard boilerplate.
- Do not consider the user's identity, other users, or any ranking.
- Every score value must be an integer within its stated range.

Submission context:
{context_text}
"""
        return self._post_with_providers(
            evaluation_prompt, system=TASKBOARD_EVALUATION_SYSTEM_MESSAGE)


# Gemini AI system: Google Gemini is the single AI provider.
# Every AI feature funnels through AIClient, which falls back across the
# configured Gemini API keys. Every response is normalized into one

# Canonical TaskBoard evaluation persona. The identical logical system message
# is used for every provider so the evaluation contract never depends on which
# free provider answered.
TASKBOARD_EVALUATION_SYSTEM_MESSAGE = (
    "You are TaskBoard's evaluation engine.\n\n"
    "You evaluate completed TaskBoard submissions using ONLY the information provided.\n"
    "You must follow the TaskBoard evaluation rubric exactly.\n"
    "You must not invent requirements.\n"
    "You must not award points outside the specified ranges.\n"
    "You must not modify the score after returning it.\n"
    "You must return ONLY the requested structured JSON object.\n"
    "The backend will independently calculate and validate the final score."
)

# Low temperature: evaluation must be deterministic, not creative.
AI_EVALUATION_TEMPERATURE = 0.2


def _extract_json(text):
    """Extract a JSON object from a provider's textual response.

    Handles markdown fences and surrounding prose. Returns the parsed object
    or raises AIProviderError(INVALID_RESPONSE) — never silently guesses.
    """
    import json
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        raise AIProviderError(
            "AI provider returned an unparsable response",
            category=AI_ERROR_INVALID_RESPONSE,
        )
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise AIProviderError(
            "AI provider returned an unparsable response",
            category=AI_ERROR_INVALID_RESPONSE,
        )
    try:
        parsed = json.loads(cleaned[start:end + 1])
    except (ValueError, TypeError):
        raise AIProviderError(
            "AI provider returned an unparsable response",
            category=AI_ERROR_INVALID_RESPONSE,
        )
    if not isinstance(parsed, dict):
        raise AIProviderError(
            "AI provider returned an unparsable response",
            category=AI_ERROR_INVALID_RESPONSE,
        )
    return parsed


# Submission-analysis AI feature. Qualitative feedback only: the judge
# (taskflow.execution) remains the single source of truth for pass/fail,
# metrics and errors. Hidden test data is never part of the prompt.
ANALYSIS_SCHEMA_FIELDS = [
    "summary", "correctness", "bugs", "code_quality",
    "time_complexity", "space_complexity", "edge_cases", "suggestions",
]
ANALYSIS_LIST_FIELDS = ("bugs", "edge_cases", "suggestions")


def validate_submission_analysis(data):
    """Validate raw AI analysis output; raises ValidationError on ANY problem."""
    if not isinstance(data, dict):
        raise ValidationError("AI response was not a JSON object")
    missing = [f for f in ANALYSIS_SCHEMA_FIELDS if f not in data]
    if missing:
        raise ValidationError({"detail": f"Missing fields: {', '.join(missing)}"})
    for field in ("summary", "correctness", "code_quality"):
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise ValidationError({field: "must be a non-empty string"})
        data[field] = value.strip()
    for field in ("time_complexity", "space_complexity"):
        value = data[field]
        data[field] = value.strip() if isinstance(value, str) else ""
    for field in ANALYSIS_LIST_FIELDS:
        items = data[field]
        if not isinstance(items, list):
            raise ValidationError({field: "must be a list of strings"})
        cleaned = []
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise ValidationError({field: "each item must be a non-empty string"})
            cleaned.append(item.strip())
        data[field] = cleaned
    return data


def generate_submission_analysis(context_text):
    """Generate + validate an analysis for a completed submission.

    Returns the normalized analysis dict. Deliberately does NOT touch any
    judge field on the submission — the caller persists it separately.
    """
    client = AIClient()
    if not client.any_provider_configured:
        raise RuntimeError("AI service is not configured.")
    data = client.analyze_submission(context_text)
    return validate_submission_analysis(data)


def build_submission_analysis_context(submission):
    """Assemble a safe, judge-derived context string for the AI prompt.

    Hidden test-case inputs / expected answers are NEVER included: only
    judge facts (status, verdict, metrics, feedback) plus public problem
    metadata and the submitted code are supplied, so Gemini cannot learn
    hidden test data from this feature.
    """
    problem = submission.problem
    lines = [
        f"PROBLEM TITLE: {problem.title}",
        f"PROBLEM STATEMENT: {problem.description}",
        f"DIFFICULTY: {problem.get_difficulty_display()}",
        f"SUBMITTED LANGUAGE: {submission.language}",
        "--- START SUBMITTED CODE ---",
        submission.source_code,
        "--- END SUBMITTED CODE ---",
        "--- JUDGE RESULT (source of truth for pass/fail) ---",
        f"STATUS: {submission.status}",
    ]
    if submission.verdict:
        lines.append(f"VERDICT: {submission.verdict}")
    if submission.passed_tests is not None and submission.total_tests is not None:
        lines.append(f"TESTS PASSED: {submission.passed_tests}/{submission.total_tests}")
    if submission.execution_time is not None:
        lines.append(f"EXECUTION TIME: {submission.execution_time}s")
    if submission.memory_used is not None:
        lines.append(f"MEMORY USED: {submission.memory_used} MB")
    if submission.feedback:
        lines.append(f"JUDGE FEEDBACK/ERROR: {submission.feedback}")
    return "\n".join(lines)


def save_submission_analysis(submission, data):
    """Upsert the validated analysis (one row per submission); never duplicate."""
    analysis, _ = SubmissionAnalysis.objects.update_or_create(
        submission=submission,
        defaults={
            "summary": data["summary"],
            "correctness": data["correctness"],
            "bugs": data["bugs"],
            "code_quality": data["code_quality"],
            "time_complexity": data["time_complexity"],
            "space_complexity": data["space_complexity"],
            "edge_cases": data["edge_cases"],
            "suggestions": data["suggestions"],
        },
    )
    return analysis


def validate_task_draft(data):
    """Validate raw AI task-draft output; raises ValidationError on ANY problem."""
    if not isinstance(data, dict):
        raise ValidationError("AI response was not a JSON object")
    missing = [f for f in TASK_DRAFT_SCHEMA_FIELDS if f not in data]
    if missing:
        raise ValidationError({"detail": f"Missing fields: {', '.join(missing)}"})
    for field in ("title", "description", "technology", "expected_outcome"):
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise ValidationError({field: "must be a non-empty string"})
        data[field] = value.strip()
    if data["difficulty"] not in VALID_DIFFICULTIES:
        raise ValidationError({"difficulty": f"difficulty must be one of {VALID_DIFFICULTIES}"})
    requirements = data["requirements"]
    if not isinstance(requirements, list):
        raise ValidationError({"requirements": "must be a list of strings"})
    cleaned = []
    for item in requirements:
        if not isinstance(item, str) or not item.strip():
            raise ValidationError({"requirements": "each requirement must be a non-empty string"})
        cleaned.append(item.strip())
    if not cleaned:
        raise ValidationError({"requirements": "must contain at least one requirement"})
    data["requirements"] = cleaned
    return data


def generate_task_draft(prompt):
    """Generate + validate a task draft. Returns normalized dict.

    Deliberately does NOT create or persist any Task — the caller reviews
    the returned draft and uses the existing task-creation flow.
    """
    client = AIClient()
    if not client.any_provider_configured:
        raise RuntimeError("AI service is not configured.")
    data = client.generate_task_draft(prompt)
    return validate_task_draft(data)


def validate_generated_problem(data):
    """Validate raw AI output; raises ValidationError on ANY problem."""
    if not isinstance(data, dict):
        raise ValidationError("AI response was not a JSON object")
    missing = [f for f in AI_PROBLEM_SCHEMA_FIELDS if f not in data]
    if missing:
        raise ValidationError({"detail": f"Missing fields: {', '.join(missing)}"})
    if data["difficulty"] not in VALID_DIFFICULTIES:
        raise ValidationError({"difficulty": f"difficulty must be one of {VALID_DIFFICULTIES}"})
    if not isinstance(data["starter_code"], dict) or not data["starter_code"]:
        raise ValidationError({"starter_code": "must be a non-empty object"})
    if not isinstance(data["allowed_languages"], list) or not data["allowed_languages"]:
        raise ValidationError({"allowed_languages": "must be a non-empty list"})
    if not isinstance(data["public_test_cases"], list) or len(data["public_test_cases"]) < 1:
        raise ValidationError({"public_test_cases": "must contain at least one case"})
    if not isinstance(data["hidden_test_cases"], list) or len(data["hidden_test_cases"]) < 1:
        raise ValidationError({"hidden_test_cases": "must contain at least one case"})
    for label in ("public_test_cases", "hidden_test_cases"):
        for case in data[label]:
            if "input" not in case or "expected_output" not in case:
                raise ValidationError({label: "each case needs 'input' and 'expected_output'"})


def create_coding_problem_from_ai(title, idea, author):
    """Generate + validate + persist as DRAFT. Returns the CodingProblem."""
    client = AIClient()
    if not client.any_provider_configured:
        raise RuntimeError("AI service is not configured.")
    data = client.generate_problem(title, idea)
    validate_generated_problem(data)
    with transaction.atomic():
        problem = CodingProblem.objects.create(
            title=data["title"],
            description=data["description"],
            difficulty=data["difficulty"],
            input_format=data["input_format"],
            output_format=data["output_format"],
            constraints=data["constraints"],
            explanation=data.get("explanation", ""),
            starter_code=data["starter_code"],
            allowed_languages=data["allowed_languages"],
            examples=data.get("examples", []),
            status=CodingProblem.Status.DRAFT,
            created_by=author,
        )
        # Public test cases use order values < 1000, hidden ones >= 1000 so the
        # ordering constraint stays simple and the two sets never interleave.
        objects = []
        for index, case in enumerate(data.get("public_test_cases", []), start=1):
            objects.append(CodingProblemTestCase(
                problem=problem, input=case["input"],
                expected_output=case["expected_output"], is_hidden=False, order=index))
        for index, case in enumerate(data.get("hidden_test_cases", []), start=1):
            objects.append(CodingProblemTestCase(
                problem=problem, input=case["input"],
                expected_output=case["expected_output"], is_hidden=True, order=1000 + index))
        CodingProblemTestCase.objects.bulk_create(objects)
    return problem


def points_earned_for_submission(submission):
    """Points this submission earns (0 unless it is the user's first ACCEPTED
    SUBMIT for this problem).

    The existing judge result is the trusted source: only an ACCEPTED SUBMIT
    rewards points, and duplicate accepted submissions earn 0. Fully derived
    from submission records — nothing is stored or writable by clients.
    """
    if (
        submission.status != CodeSubmission.Status.ACCEPTED
        or submission.mode != CodeSubmission.Mode.SUBMIT
    ):
        return 0
    # Points go to the FIRST accepted SUBMIT for this (user, problem). id is
    # assigned in creation order, so the earliest accepted row is deterministic.
    first_accepted = (
        CodeSubmission.objects
        .filter(
            user=submission.user,
            problem=submission.problem,
            status=CodeSubmission.Status.ACCEPTED,
            mode=CodeSubmission.Mode.SUBMIT,
        )
        .order_by('id')
        .first()
    )
    if first_accepted is None or first_accepted.pk != submission.pk:
        return 0
    return submission.problem.points


def normal_task_points_earned(submission):
    """Points a Normal Task submission earns toward the leaderboard.

    Only an APPROVED submission grants the task's derived reward (the stored
    `earned_points` value set once, server-side, at approval time). Return 0
    for pending/rejected or never-awarded rows.
    """
    if submission.status != TaskSubmission.Status.APPROVED:
        return 0
    return submission.earned_points or submission.task.points


def award_normal_task_points(submission):
    """Atomically grant Normal Task points for an APPROVED submission.

    Idempotent and concurrency-safe: writes earned_points only when it is
    still 0, using a conditional UPDATE so repeated or simultaneous approvals
    can never double-award. Callers must prefetch `task` (e.g.
    select_related('task')) so accessing task.points costs no extra query.
    Returns the points granted (0 if already awarded or no points due).
    """
    if submission.status != TaskSubmission.Status.APPROVED:
        return 0
    # The review view fetches submissions with select_related('task'),
    # so submission.task is already loaded.
    points = submission.task.points
    if points <= 0:
        return 0
    # Idempotent atomic award: the earned_points=0 guard in the WHERE
    # clause ensures only the first concurrent approver's UPDATE matches.
    updated = TaskSubmission.objects.filter(pk=submission.pk, earned_points=0).update(earned_points=points)
    return points if updated else 0


# ── Normal Task AI evaluation (fixed 10-point rubric) ────────────────────────
# The reviewer/judge remains the source of truth for acceptance: only APPROVED
# submissions may be evaluated. The AI returns rubric category scores only —
# the backend always recomputes the total — and nothing here writes
# leaderboard points directly; the leaderboard derives contributions from
# TaskEvaluation rows at read time.

TASK_EVALUATION_RUBRIC = {
    # category: (min, max) — total across all categories is exactly 10.
    'requirement_completion': (0, 3),
    'correctness': (0, 2),
    'quality': (0, 2),
    'completeness': (0, 2),
    'clarity': (0, 1),
}
TASK_EVALUATION_MAX_SCORE = sum(limits[1] for limits in TASK_EVALUATION_RUBRIC.values())  # == 10


def build_task_evaluation_context(submission):
    """Assemble a safe prompt context for evaluating a normal-task submission.

    Only public task metadata and the user's own submission content are
    included. No API keys, auth tokens, or unrelated user data ever reach
    the AI.
    """
    task = submission.task
    lines = [
        f"TASK TITLE: {task.title}",
        f"TASK DESCRIPTION: {task.description}",
        f"TASK DIFFICULTY: {task.get_difficulty_display()}",
        "--- START SUBMITTED WORK ---",
        f"Repository URL: {submission.git_url}",
        f"LinkedIn URL: {submission.linkedin_url}",
        f"Submission note: {submission.note or '(none provided)'}",
        "--- END SUBMITTED WORK ---",
        "--- REVIEWER RESULT (source of truth for acceptance) ---",
        f"STATUS: {submission.status}",
    ]
    if submission.feedback:
        lines.append(f"REVIEWER FEEDBACK: {submission.feedback}")
    return "\n".join(lines)


def validate_task_evaluation(data):
    """Validate raw AI evaluation output against the fixed rubric.

    Raises ValidationError on ANY problem (shape, missing category,
    out-of-range or non-integer score). The AI-supplied total_score is
    deliberately IGNORED — the total is always recomputed here, so a lying
    or malformed total can never reach the database or the leaderboard.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError
    if not isinstance(data, dict):
        raise DjangoValidationError("AI response was not a JSON object")
    scores = data.get("scores")
    if not isinstance(scores, dict):
        raise DjangoValidationError({"scores": "must be a JSON object"})
    if set(scores) != set(TASK_EVALUATION_RUBRIC):
        raise DjangoValidationError({"scores": f"must contain exactly: {', '.join(TASK_EVALUATION_RUBRIC)}"})
    validated = {}
    for category, (low, high) in TASK_EVALUATION_RUBRIC.items():
        value = scores[category]
        if isinstance(value, bool) or not isinstance(value, int):
            raise DjangoValidationError({f"scores.{category}": "must be an integer"})
        if value < low or value > high:
            raise DjangoValidationError({f"scores.{category}": f"must be between {low} and {high}"})
        validated[category] = value
    # Server-authoritative total: recomputed, never taken from the AI.
    validated["total_score"] = sum(validated.values())

    def _string_list(field):
        value = data.get(field, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise DjangoValidationError({field: "must be a list of strings"})
        return [item.strip() for item in value if item.strip()]

    summary = data.get("summary")
    if not isinstance(summary, str):
        raise DjangoValidationError({"summary": "must be a string"})
    return {
        "scores": {k: validated[k] for k in TASK_EVALUATION_RUBRIC},
        "total_score": validated["total_score"],
        "summary": summary.strip(),
        "strengths": _string_list("strengths"),
        "issues": _string_list("issues"),
        "suggestions": _string_list("suggestions"),
    }


def normalize_ai_response(raw_response, provider=""):
    """Normalize ANY provider's raw output into the canonical TaskBoard form.

    Single funnel for Google Gemini evaluation responses:
      1. extract JSON if the provider returned a text payload (fences/prose),
      2. validate the rubric strictly (ranges, types, no missing categories),
      3. recompute total_score server-side — an AI-supplied total is IGNORED,
      4. normalize the strengths/issues/suggestions string lists.
    Raises ValidationError on any invalid value; nothing is clamped silently.
    The `provider` key is internal metadata for diagnostics only and is not
    part of the frontend/database contract (save_task_evaluation ignores it).
    """
    try:
        extracted = _extract_json(raw_response)
    except AIProviderError as exc:
        raise ValidationError({"detail": str(exc)})
    canonical = validate_task_evaluation(extracted)
    canonical["provider"] = provider or "unknown"
    return canonical


def generate_task_evaluation(submission):
    """Generate + validate an evaluation for an APPROVED submission.

    Raises RuntimeError (safe provider failure) or ValidationError (invalid
    AI output). Deliberately does NOT touch the submission's review fields —
    the reviewer/judge owns those.
    """
    client = AIClient()
    if not client.any_provider_configured:
        raise RuntimeError(
            "AI provider is not configured (set GEMINI_API_KEY)")
    if submission.status != TaskSubmission.Status.APPROVED:
        # A rejected/pending submission can never be evaluated or scored.
        raise ValidationError("Only approved submissions can be evaluated")
    data = client.evaluate_task(build_task_evaluation_context(submission))
    return normalize_ai_response(data, provider=client.last_provider or "")


def save_task_evaluation(submission, data):
    """Upsert the validated evaluation (one row per submission); never duplicate.

    Defensive: the persisted total_score is ALWAYS recomputed from the
    rubric category scores, never taken from `data['total_score']`, so even a
    bypassed-validation or lying AI-supplied total can never reach the DB.
    """
    scores = data["scores"]
    total_score = sum(scores.values())
    evaluation, _ = TaskEvaluation.objects.update_or_create(
        submission=submission,
        defaults={
            "status": TaskEvaluation.Status.COMPLETED,
            "scores": scores,
            "total_score": total_score,
            "summary": data["summary"],
            "strengths": data["strengths"],
            "issues": data["issues"],
            "suggestions": data["suggestions"],
            "error_message": "",
        },
    )
    return evaluation


def record_task_evaluation_failure(submission, message="AI evaluation is temporarily unavailable. Try again shortly."):
    """Mark the evaluation FAILED with NO score; the user may retry.

    A failed evaluation must never award points or mark the task solved.
    """
    evaluation, _ = TaskEvaluation.objects.update_or_create(
        submission=submission,
        defaults={
            "status": TaskEvaluation.Status.FAILED,
            "scores": {},
            "total_score": 0,
            "error_message": message,
        },
    )
    return evaluation


def best_task_evaluation_score(user_id, task_id):
    """Best COMPLETED evaluation score for a (user, task) pair, or None.

    The user's effective task score is the MAXIMUM completed evaluation,
    never a sum, so repeated submissions cannot farm points and a worse
    attempt never reduces the best score.
    """
    return (
        TaskEvaluation.objects
        .filter(
            status=TaskEvaluation.Status.COMPLETED,
            submission__user_id=user_id,
            submission__task_id=task_id,
            submission__status=TaskSubmission.Status.APPROVED,
        )
        .aggregate(best=models.Max('total_score'))['best']
    )


# ---------------------------------------------------------------------------
# In-app notifications (server-side workflow events only).
# ---------------------------------------------------------------------------

def _wants_notification(user, preference_field):
    """Honour the recipient's existing NotificationPreference (default True)."""
    pref = getattr(user, 'notification_preference', None)
    if pref is None:
        return True
    return bool(getattr(pref, preference_field, True))


def notify(recipient, *, title, message, url='', event_key, preference_field=None):
    """Create one notification idempotently.

    (recipient, event_key) is unique, so replaying the same event (duplicate
    API call, retry, concurrent request) inserts at most one row. When
    `preference_field` is given, the recipient's stored preference can opt
    them out; the default is to notify.
    """
    if recipient is None or not getattr(recipient, 'is_active', False):
        return None
    if preference_field and not _wants_notification(recipient, preference_field):
        return None
    notification, _ = Notification.objects.get_or_create(
        recipient=recipient,
        event_key=event_key,
        defaults={'title': title[:200], 'message': message, 'url': url[:300]},
    )
    return notification


def notify_task_published(task, *, creator=None):
    """A) Admin published a task -> notify every active normal user except staff."""
    User = get_user_model()
    recipients = User.objects.filter(is_active=True).exclude(is_staff=True).exclude(is_superuser=True)
    if creator is not None:
        recipients = recipients.exclude(pk=creator.pk)
    for recipient in recipients:
        notify(
            recipient,
            title='New Task Available',
            message=f'Admin posted {task.title}. You can now view and submit this task.',
            url='/my-tasks',
            event_key=f'task-published-{task.pk}-user-{recipient.pk}',
            preference_field='task_assignments',
        )


def notify_submission_received(submission, *, is_resubmission=False):
    """B)/F) User (re)submitted a task -> notify the staff reviewers."""
    User = get_user_model()
    recipients = User.objects.filter(is_active=True, is_staff=True)
    task_title = submission.task.title
    username = submission.user.get_username()
    for recipient in recipients:
        notify(
            recipient,
            title='Improved Submission' if is_resubmission else 'New Task Submission',
            message=(
                f'{username} resubmitted {task_title} with an improved solution.'
                if is_resubmission else
                f'{username} submitted {task_title} for review.'
            ),
            url='/admin/submissions',
            event_key=f'submission-received-{submission.pk}-user-{recipient.pk}',
        )


def notify_submission_reviewed(submission):
    """C)/D) Admin approved or rejected a submission -> notify the submitter.

    The event key includes the OUTCOME, so a later review of the same
    submission (rejected then approved, or vice versa) still notifies, while
    replaying the SAME outcome stays idempotent.
    """
    approved = submission.status == TaskSubmission.Status.APPROVED
    notify(
        submission.user,
        title='Task Approved' if approved else 'Task Rejected',
        message=(
            f'Your submission for {submission.task.title} was accepted and is being evaluated.'
            if approved else
            f'Your submission for {submission.task.title} needs changes.'
        ),
        url='/my-tasks',
        event_key=f'submission-reviewed-{submission.pk}-{"approved" if approved else "rejected"}',
        preference_field='submission_reviews',
    )


def notify_evaluation_completed(submission, evaluation):
    """E) AI evaluation finished successfully -> notify the submitter with the
    server-calculated score. Never called for failed evaluations."""
    notify(
        submission.user,
        title='Task Evaluated',
        message=f'Your submission for {submission.task.title} scored {evaluation.total_score}/10.',
        url='/my-tasks',
        event_key=f'task-evaluated-{evaluation.pk}',
        preference_field='submission_reviews',
    )


def leaderboard():
    """Deterministic combined leaderboard: Coding + Normal Task points.

    For each member (normal user):
      - coding_points      = sum of DIFFICULTY_POINTS for distinct problems
                             with an ACCEPTED SUBMIT (unchanged coding rules).
      - problems_solved    = distinct coding problems solved (unchanged).
      - normal_task_points = sum of awarded Normal Task points from APPROVED
                             TaskSubmission rows (one-time, server-set).
      - total_points       = coding_points + normal_task_points.
    Ranking: higher total_points → higher rank; tie → more problems solved;
    tie → username (stable, deterministic). `points` remains the coding-only
    value for backwards compatibility with existing consumers.
    """
    # Coding: distinct ACCEPTED SUBMITS per (user, problem).
    solved_rows = (
        CodeSubmission.objects
        .filter(
            status=CodeSubmission.Status.ACCEPTED,
            mode=CodeSubmission.Mode.SUBMIT,
        )
        .exclude(problem__status=CodingProblem.Status.DRAFT)
        .values('user_id', 'problem_id', 'problem__difficulty')
        .distinct()
    )
    user_points = defaultdict(int)
    user_solved = defaultdict(int)
    for row in solved_rows:
        user_solved[row['user_id']] += 1
        user_points[row['user_id']] += DIFFICULTY_POINTS.get(row['problem__difficulty'], 0)

    # Normal Task (legacy fallback): awarded earned_points on APPROVED rows.
    approved_tasks = (
        TaskSubmission.objects
        .filter(status=TaskSubmission.Status.APPROVED)
        .exclude(earned_points=0)
        .values('user_id')
        .annotate(total=models.Sum('earned_points'))
    )
    normal_points = {row['user_id']: row['total'] or 0 for row in approved_tasks}

    # Normal Task (best-score rule): for each (user, task) take the MAX
    # completed evaluation score, then sum per user. Rejected submissions are
    # excluded (they can never be evaluated); a failed evaluation contributes
    # nothing. Users with evaluations use ONLY this sum so a legacy award is
    # never double-counted alongside it.
    evaluated_users = set(
        TaskEvaluation.objects.filter(status=TaskEvaluation.Status.COMPLETED)
        .values_list('submission__user_id', flat=True)
    )
    if evaluated_users:
        best_rows = (
            TaskEvaluation.objects
            .filter(status=TaskEvaluation.Status.COMPLETED)
            .filter(submission__status=TaskSubmission.Status.APPROVED)
            .values('submission__user_id', 'submission__task_id')
            .annotate(best=models.Max('total_score'))
        )
        eval_points = defaultdict(int)
        for row in best_rows:
            eval_points[row['submission__user_id']] += row['best'] or 0
        for user_id in evaluated_users:
            normal_points[user_id] = eval_points.get(user_id, 0)

    user_ids = set(user_points) | set(user_solved) | set(normal_points)
    User = get_user_model()
    users = {u.id: u for u in User.objects.filter(id__in=user_ids)}

    entries = []
    for user_id in user_ids:
        user = users.get(user_id)
        if user is None:
            continue
        coding = user_points[user_id]
        normal = normal_points.get(user_id, 0)
        entries.append({
            'rank': 0,
            'user_id': user_id,
            'username': user.username,
            'name': user.get_full_name() or user.username,
            'problems_solved': user_solved[user_id],
            'coding_points': coding,
            'normal_task_points': normal,
            'total_points': coding + normal,
            # Backwards-compatible alias: previously the only 'points' field.
            'points': coding,
        })
    entries.sort(
        key=lambda entry: (
            -entry['total_points'], -entry['problems_solved'], entry['username']
        )
    )
    for index, entry in enumerate(entries, start=1):
        entry['rank'] = index
    return entries


# Backwards-compatible alias for callers/tests that reference the old name.
def coding_leaderboard():
    return leaderboard()
