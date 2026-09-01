from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import Task
from taskflow.services import MAX_TASK_DRAFT_PROMPT_LENGTH

User = get_user_model()

VALID_DRAFT = {
    "title": "Build a REST API client module",
    "description": "Create a small Python module that talks to a REST API and handles pagination.",
    "technology": "Python",
    "difficulty": "MEDIUM",
    "requirements": [
        "Use the requests library for HTTP calls.",
        "Implement cursor-based pagination.",
        "Add unit tests covering error responses.",
    ],
    "expected_outcome": "A reusable module with passing unit tests and documented usage.",
}


class FakeTaskDraftAI:
    """Stand-in for the real AIClient so tests never touch the network."""

    configured = True
    any_provider_configured = True

    def __init__(self, payload=VALID_DRAFT):
        self.payload = payload
        self.prompts_received = []

    def generate_task_draft(self, prompt):
        self.prompts_received.append(prompt)
        return self.payload


class FailingTaskDraftAI(FakeTaskDraftAI):
    """Simulates a Gemini/provider outage inside _post."""

    def generate_task_draft(self, prompt):
        raise RuntimeError("AI provider request failed")


class TaskDraftAITestBase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
        self.user = User.objects.create_user(username='user', password='StrongPassword!42', email='user@example.com')

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def generate(self, prompt="Create an intermediate Python task about REST APIs"):
        return self.client.post('/api/auth/ai/task-draft/', {'prompt': prompt})


class TaskDraftAIPermissionTests(TaskDraftAITestBase):

    def test_admin_can_request_a_task_draft(self):
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeTaskDraftAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 200)

    def test_unauthenticated_request_is_rejected(self):
        response = self.generate()
        self.assertEqual(response.status_code, 401)

    def test_non_admin_user_is_rejected(self):
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeTaskDraftAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 403)


class TaskDraftAIValidationTests(TaskDraftAITestBase):

    def test_missing_prompt_is_rejected(self):
        self.authenticate(self.admin)
        response = self.client.post('/api/auth/ai/task-draft/', {})
        self.assertEqual(response.status_code, 400)

    def test_empty_prompt_is_rejected(self):
        self.authenticate(self.admin)
        response = self.generate("   ")
        self.assertEqual(response.status_code, 400)

    def test_non_string_prompt_is_rejected(self):
        self.authenticate(self.admin)
        # JSON format so the integer survives parsing as a non-string type
        # (multipart would coerce it to "123").
        response = self.client.post('/api/auth/ai/task-draft/', {'prompt': 123}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_oversized_prompt_is_rejected(self):
        self.authenticate(self.admin)
        response = self.generate('x' * (MAX_TASK_DRAFT_PROMPT_LENGTH + 1))
        self.assertEqual(response.status_code, 400)

    def test_prompt_at_max_length_is_allowed(self):
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeTaskDraftAI()) as fake_ai:
            response = self.generate('x' * MAX_TASK_DRAFT_PROMPT_LENGTH)
        self.assertEqual(response.status_code, 200)
        # The exact prompt (trimmed) must reach Gemini unchanged.
        sent_prompt = fake_ai.return_value.prompts_received[0]
        self.assertEqual(sent_prompt, 'x' * MAX_TASK_DRAFT_PROMPT_LENGTH)


class TaskDraftAIResponseTests(TaskDraftAITestBase):

    def test_valid_gemini_response_is_normalized_into_expected_structure(self):
        self.authenticate(self.admin)
        messy = {**VALID_DRAFT, 'title': '  Build a REST API client module  ', 'requirements': [' Keep first. ', 'Then second.']}
        with patch('taskflow.services.AIClient', return_value=FakeTaskDraftAI(payload=messy)):
            response = self.generate()
        self.assertEqual(response.status_code, 200)
        data = response.data
        for field in ('title', 'description', 'technology', 'difficulty', 'requirements', 'expected_outcome'):
            self.assertIn(field, data)
        self.assertEqual(data['title'], 'Build a REST API client module')
        self.assertEqual(data['difficulty'], 'MEDIUM')
        self.assertEqual(len(data['requirements']), len(messy['requirements']))

    def test_invalid_gemini_response_is_handled_safely(self):
        self.authenticate(self.admin)
        broken = {k: v for k, v in VALID_DRAFT.items() if k != 'expected_outcome'}
        with patch('taskflow.services.AIClient', return_value=FakeTaskDraftAI(payload=broken)):
            response = self.generate()
        self.assertEqual(response.status_code, 422)

    def test_gemini_outage_returns_controlled_error(self):
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FailingTaskDraftAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 503)
        rendered = str(response.data).lower()
        self.assertNotIn('api key', rendered)
        self.assertNotIn('traceback', rendered)

    def test_unconfigured_provider_is_rejected_by_service(self):
        from taskflow import services as services_module

        with patch.object(services_module.AIClient, 'any_provider_configured', False), \
                patch.object(services_module.AIClient, 'generate_task_draft') as mock_generate:
            with self.assertRaises(RuntimeError) as caught:
                services_module.generate_task_draft('anything')
        # Controlled error; no provider must ever be called without a key.
        self.assertIn('not configured', str(caught.exception))
        mock_generate.assert_not_called()

    def test_ai_generation_does_not_create_a_task(self):
        self.authenticate(self.admin)
        tasks_before = Task.objects.count()
        with patch('taskflow.services.AIClient', return_value=FakeTaskDraftAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), tasks_before)
