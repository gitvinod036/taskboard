from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import CodeSubmission, CodingProblem, CodingProblemTestCase, SubmissionAnalysis

User = get_user_model()

VALID_ANALYSIS = {
    "summary": "A solid two-pointer approach.",
    "correctness": "The approach is generally correct.",
    "bugs": ["Index out of range when the list is empty."],
    "code_quality": "Readable and well-named.",
    "time_complexity": "O(n log n) time",
    "space_complexity": "O(1) space",
    "edge_cases": ["Empty list"],
    "suggestions": ["Add early returns."],
}


class FakeAI:
    """Stand-in for the real AIClient so analysis tests never touch the network."""

    configured = True
    any_provider_configured = True

    def __init__(self, payload=None, error=None, configured=None):
        self.payload = payload or dict(VALID_ANALYSIS)
        self.error = error
        if configured is not None:
            self.configured = configured
            # The service gate reads the provider-aware flag.
            self.any_provider_configured = configured

    def analyze_submission(self, context_text):
        if self.error:
            raise self.error
        return self.payload


class SubmissionAnalysisTestBase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
        self.user = User.objects.create_user(username='user', password='StrongPassword!42', email='user@example.com')
        self.other = User.objects.create_user(username='other', password='StrongPassword!42', email='other@example.com')

        self.problem = CodingProblem.objects.create(
            title='Two Sum',
            description='Sum two numbers from an array.',
            difficulty='EASY',
            input_format='N X then N integers.',
            output_format='Two indices.',
            constraints='1 <= N <= 100',
            explanation='',
            starter_code={'python': 'pass'},
            allowed_languages=['python'],
            status=CodingProblem.Status.PUBLISHED,
            created_by=self.admin,
            published_at='2026-01-01T00:00:00Z',
        )
        CodingProblemTestCase.objects.create(
            problem=self.problem, input='2 3\n1 2',
            expected_output='0 1', is_hidden=False, order=1)
        CodingProblemTestCase.objects.create(
            problem=self.problem, input='SECRET-HIDDEN',
            expected_output='SECRET-OUT', is_hidden=True, order=1001)

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def make_submission(self, user=None):
        return CodeSubmission.objects.create(
            user=user or self.user,
            problem=self.problem,
            language='python',
            source_code='def solve(nums):\n    return [0, 1]\n',
            status=CodeSubmission.Status.ACCEPTED,
            passed_tests=2,
            total_tests=2,
            execution_time=0.02,
            memory_used=8.0,
        )

    def analyze(self, submission):
        return self.client.post(f'/api/coding/submissions/{submission.id}/analyze/')


class AnalyzeOwnSubmissionTests(SubmissionAnalysisTestBase):

    def test_authenticated_user_can_analyze_own_submission(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.analyze(submission)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['submission']['id'], submission.id)
        self.assertEqual(response.data['analysis']['summary'], VALID_ANALYSIS['summary'])
        self.assertEqual(response.data['judge_result']['status'], CodeSubmission.Status.ACCEPTED)
        self.assertTrue(SubmissionAnalysis.objects.filter(submission=submission).exists())

    def test_unauthenticated_request_is_rejected(self):
        submission = self.make_submission(user=self.user)
        response = self.analyze(submission)
        self.assertEqual(response.status_code, 401)

    def test_user_cannot_analyze_another_users_submission(self):
        submission = self.make_submission(user=self.other)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.analyze(submission)
        # Non-owner: existence is never confirmed → 404.
        self.assertEqual(response.status_code, 404)

    def test_analysis_never_creates_duplicate_for_nonexistent_owner(self):
        submission = self.make_submission(user=self.other)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            self.analyze(submission)
            self.analyze(submission)
        self.assertEqual(SubmissionAnalysis.objects.count(), 0)


class AnalyzeGeminiFailuresTests(SubmissionAnalysisTestBase):

    def test_missing_gemini_api_key_returns_503(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        fake = FakeAI(configured=False)
        with patch('taskflow.services.AIClient', return_value=fake):
            response = self.analyze(submission)
        self.assertEqual(response.status_code, 503)
        # The safe contract never exposes provider names or internals to clients.
        self.assertEqual(response.data['detail'], 'AI service is temporarily unavailable. Please try again shortly.')
        self.assertFalse(SubmissionAnalysis.objects.filter(submission=submission).exists())

    def test_malformed_gemini_response_returns_422(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        malformed = {k: v for k, v in VALID_ANALYSIS.items() if k != 'summary'}
        with patch('taskflow.services.AIClient', return_value=FakeAI(payload=malformed)):
            response = self.analyze(submission)
        self.assertEqual(response.status_code, 422)
        self.assertFalse(SubmissionAnalysis.objects.filter(submission=submission).exists())

    def test_gemini_failure_returns_controlled_503(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI(error=RuntimeError('boom'))):
            response = self.analyze(submission)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('boom', response.data['detail'])
        self.assertNotIn('Traceback', response.data['detail'])
        self.assertFalse(SubmissionAnalysis.objects.filter(submission=submission).exists())


class AnalyzePersistenceTests(SubmissionAnalysisTestBase):

    def test_analysis_is_persisted_and_regenerated_in_place(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            first = self.analyze(submission)
        self.assertEqual(first.status_code, 200)
        row = SubmissionAnalysis.objects.get(submission=submission)
        self.assertEqual(SubmissionAnalysis.objects.filter(submission=submission).count(), 1)
        original_id = row.id
        original_summary = row.summary

        modified = {**VALID_ANALYSIS, 'summary': 'Updated summary.'}
        with patch('taskflow.services.AIClient', return_value=FakeAI(payload=modified)):
            second = self.analyze(submission)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['analysis']['summary'], modified['summary'])
        # Regeneration updates the SAME row rather than creating a duplicate.
        self.assertEqual(SubmissionAnalysis.objects.filter(submission=submission).count(), 1)
        refreshed = SubmissionAnalysis.objects.get(submission=submission)
        self.assertEqual(refreshed.id, original_id)
        self.assertNotEqual(refreshed.summary, original_summary)

    def test_analysis_never_touches_judge_fields_or_creates_tasks(self):
        submission = self.make_submission(user=self.user)
        before_status = submission.status
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            self.analyze(submission)
        submission.refresh_from_db()
        self.assertEqual(submission.status, before_status)
        from taskflow.models import Task as _Task
        self.assertEqual(_Task.objects.count(), 0)
        self.assertEqual(CodeSubmission.objects.count(), 1)


class AnalyzeAdminTests(SubmissionAnalysisTestBase):

    def test_admin_can_analyze_own_submission_via_user_endpoint(self):
        submission = self.make_submission(user=self.admin)
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.analyze(submission)
        self.assertEqual(response.status_code, 200)

    def test_normal_user_cannot_use_admin_analyze_endpoint(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.client.post(f'/api/admin/coding/submissions/{submission.id}/analyze/')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_analyze_any_submission_via_admin_endpoint(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.client.post(f'/api/admin/coding/submissions/{submission.id}/analyze/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['submission']['id'], submission.id)

    def test_hidden_test_data_never_exposed_in_analyze_payload(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            self.analyze(submission)
            body = self.analyze(submission).content.decode()
        self.assertNotIn('SECRET-HIDDEN', body)
        self.assertNotIn('SECRET-OUT', body)