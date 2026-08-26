"""
Domain services including AI generation.
"""
import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CodingProblem, CodingProblemTestCase


# Schema the AI must satisfy. Kept explicit so malformed LLM output can
# never silently corrupt the database.
AI_PROBLEM_SCHEMA_FIELDS = [
    "title", "description", "difficulty", "input_format",
    "output_format", "constraints", "examples", "explanation",
    "starter_code", "allowed_languages", "public_test_cases",
    "hidden_test_cases",
]
VALID_DIFFICULTIES = ("EASY", "MEDIUM", "HARD")


class AIClient:
    """Clean interface over the configured AI provider.

    No hardcoded keys: reads AI_API_KEY / AI_MODEL from Django settings
    (env-driven). Returns only the validated JSON structure; the view
    never trusts the raw LLM output directly.
    """

    def __init__(self):
        self.api_key = getattr(settings, "AI_API_KEY", "")
        self.model = getattr(settings, "AI_MODEL", "gemini-2.5-flash")
        self.base_url = getattr(
            settings,
            "AI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/models",
        )

    @property
    def configured(self):
        return bool(self.api_key)

    def _post(self, prompt):
        """Perform an HTTP call to the AI provider via requests.

        Returns parsed JSON or raises; isolated from the model layer so a
        bad response is never persisted.
        """
        import requests  # local import keeps the dependency optional
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, json=payload, timeout=30, headers=headers)
            resp.raise_for_status()
        except Exception:
            raise RuntimeError("AI provider request failed")
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
        return self._post(prompt)


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
    if not client.configured:
        raise RuntimeError("AI provider is not configured (set AI_API_KEY)")
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
