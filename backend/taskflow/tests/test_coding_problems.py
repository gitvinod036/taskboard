from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import CodeSubmission, CodingProblem, CodingProblemTestCase

User = get_user_model()

VALID_AI = {
    "title": "Two Sum",
    "description": "Given an array of integers and a target, find two numbers whose sum equals the target.",
    "difficulty": "EASY",
    "input_format": "The first line contains N and X. The second line contains N integers.",
    "output_format": "Output the two 0-based indices separated by a space.",
    "constraints": "1 <= N <= 10^4; -10^9 <= nums[i] <= 10^9",
    "examples": [
        {"input": "4 9\n2 7 11 15", "output": "0 1", "explanation": "nums[0] + nums[1] == 9."}
    ],
    "explanation": "Hash the seen values to answer in O(N).",
    "starter_code": {
        "python": "def two_sum(nums, target):\n    pass",
        "javascript": "function twoSum(nums, target) {}",
        "java": "class Solution { public int[] twoSum(int[] nums, int target) {} }",
        "cpp": "vector<int> twoSum(vector<int>& nums, int target) {}",
    },
    "allowed_languages": ["python", "javascript", "java", "cpp"],
    "public_test_cases": [
        {"input": "4 9\n2 7 11 15", "expected_output": "0 1"},
    ],
    "hidden_test_cases": [
        {"input": "3 6\n3 3 3", "expected_output": "0 1"},
        {"input": "2 1\n0 1", "expected_output": "0 1"},
    ],
}


class FakeAI:
    """Stand-in for the real AIClient so tests never touch the network."""

    configured = True

    def __init__(self, payload=VALID_AI):
        self.payload = payload

    def generate_problem(self, title, idea):
        return self.payload


def problem_payload(**overrides):
    data = {
        "title": "Two Sum",
        "description": "Sum two numbers from an array.",
        "difficulty": "EASY",
        "input_format": "N X then N integers.",
        "output_format": "Two indices.",
        "constraints": "1 <= N <= 100",
        "examples": [],
        "explanation": "Straightforward.",
        "starter_code": {"python": "pass", "javascript": "", "java": "", "cpp": ""},
        "allowed_languages": ["python", "javascript", "java", "cpp"],
        "test_cases": [
            {"input": "2 3\n1 2", "expected_output": "0 1", "is_hidden": False, "order": 1},
            {"input": "2 9\n4 5", "expected_output": "0 1", "is_hidden": True, "order": 1001},
        ],
        "status": "DRAFT",
    }
    data.update(overrides)
    return data


class CodingProblemTestBase(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
        self.user = User.objects.create_user(username='user', password='StrongPassword!42', email='user@example.com')

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_draft(self, **overrides):
        return CodingProblem.objects.create(
            title=overrides.get('title', 'Two Sum'),
            description=overrides.get('description', 'A test problem.'),
            difficulty=overrides.get('difficulty', 'EASY'),
            input_format=overrides.get('input_format', 'N'),
            output_format=overrides.get('output_format', 'answer'),
            constraints=overrides.get('constraints', '1 <= N <= 100'),
            explanation='',
            starter_code={'python': 'pass'},
            allowed_languages=['python'],
            status=CodingProblem.Status.DRAFT,
            created_by=self.admin,
        )

    def add_test_cases(self, problem, public=1, hidden=1):
        objects = []
        for index in range(public):
            objects.append(CodingProblemTestCase(
                problem=problem, input=f'p {index}',
                expected_output=f'result {index}', is_hidden=False, order=index + 1))
        for index in range(hidden):
            objects.append(CodingProblemTestCase(
                problem=problem, input=f'private {index}',
                expected_output=f'result {index}', is_hidden=True, order=1001 + index))
        if objects:
            CodingProblemTestCase.objects.bulk_create(objects)
class GenerateCodingProblemTests(CodingProblemTestBase):

    def generate(self, title='Two Sum', idea='Two numbers sum to target'):
        return self.client.post('/api/admin/coding/problems/generate/', {'title': title, 'idea': idea})

    def test_admin_can_generate_a_coding_problem(self):
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 201)
        data = response.data
        self.assertEqual(data['title'], 'Two Sum')
        self.assertEqual(data['difficulty'], 'EASY')
        self.assertEqual(data['status'], CodingProblem.Status.DRAFT)
        self.assertIsNone(data['published_at'])
        # The generated problem must persist as a DRAFT with both case kinds.
        problem = CodingProblem.objects.get(pk=data['id'])
        self.assertEqual(problem.status, CodingProblem.Status.DRAFT)
        self.assertEqual(problem.test_cases.filter(is_hidden=False).count(), 1)
        self.assertEqual(problem.test_cases.filter(is_hidden=True).count(), 2)

    def test_ai_response_is_validated_before_persisting(self):
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 201)
        for field in ('title', 'description', 'difficulty', 'input_format', 'output_format',
                      'constraints', 'explanation', 'starter_code', 'allowed_languages'):
            self.assertIn(field, response.data)
        self.assertEqual(response.data['status'], CodingProblem.Status.DRAFT)

    def test_invalid_ai_response_is_rejected(self):
        invalid = {**VALID_AI, 'difficulty': 'EXTREME'}
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI(payload=invalid)):
            response = self.generate()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(CodingProblem.objects.count(), 0)

    def test_malformed_ai_response_is_rejected(self):
        invalid = {k: v for k, v in VALID_AI.items() if k != 'title'}
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI(payload=invalid)):
            response = self.generate()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(CodingProblem.objects.count(), 0)

    def test_ai_cannot_automatically_publish(self):
        self.authenticate(self.admin)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], CodingProblem.Status.DRAFT)

    def test_non_admin_cannot_generate(self):
        self.authenticate(self.user)
        with patch('taskflow.services.AIClient', return_value=FakeAI()):
            response = self.generate()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(CodingProblem.objects.exists())

    def test_unauthenticated_cannot_generate(self):
        response = self.generate()
        self.assertEqual(response.status_code, 401)

    def test_title_and_idea_are_required(self):
        self.authenticate(self.admin)
        response = self.client.post('/api/admin/coding/problems/generate/', {'title': '', 'idea': ''})
        self.assertEqual(response.status_code, 400)

    def test_unconfigured_ai_returns_503(self):
        self.authenticate(self.admin)
        fake = FakeAI()
        fake.configured = False
        with patch('taskflow.services.AIClient', return_value=fake):
            response = self.generate()
        self.assertEqual(response.status_code, 503)
class AdminManageCodingProblemTests(CodingProblemTestBase):

    def test_admin_can_save_a_draft(self):
        self.authenticate(self.admin)
        response = self.client.post('/api/admin/coding/problems/', problem_payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], CodingProblem.Status.DRAFT)
        self.assertEqual(CodingProblem.objects.filter(status=CodingProblem.Status.DRAFT).count(), 1)

    def test_admin_can_edit_a_draft(self):
        problem = self.create_draft()
        self.add_test_cases(problem)
        self.authenticate(self.admin)
        response = self.client.patch(
            f'/api/admin/coding/problems/{problem.id}/',
            {'description': 'Updated description.'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['description'], 'Updated description.')
        self.assertEqual(response.data['status'], CodingProblem.Status.DRAFT)

    def test_admin_can_publish_a_draft(self):
        problem = self.create_draft()
        self.add_test_cases(problem)
        self.authenticate(self.admin)
        response = self.client.patch(
            f'/api/admin/coding/problems/{problem.id}/',
            {'status': CodingProblem.Status.PUBLISHED},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], CodingProblem.Status.PUBLISHED)
        self.assertIsNotNone(response.data['published_at'])
        problem.refresh_from_db()
        self.assertEqual(problem.status, CodingProblem.Status.PUBLISHED)
        self.assertIsNotNone(problem.published_at)

    def test_publish_requires_both_public_and_hidden_test_cases(self):
        problem = self.create_draft()
        self.add_test_cases(problem, public=0, hidden=2)  # only hidden cases
        self.authenticate(self.admin)
        response = self.client.patch(
            f'/api/admin/coding/problems/{problem.id}/',
            {'status': CodingProblem.Status.PUBLISHED},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        problem.refresh_from_db()
        self.assertEqual(problem.status, CodingProblem.Status.DRAFT)

    def test_publish_requires_required_fields(self):
        problem = self.create_draft(description='')
        self.add_test_cases(problem)
        self.authenticate(self.admin)
        response = self.client.patch(
            f'/api/admin/coding/problems/{problem.id}/',
            {'status': CodingProblem.Status.PUBLISHED},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        problem.refresh_from_db()
        self.assertEqual(problem.status, CodingProblem.Status.DRAFT)

    def test_admin_can_delete_a_problem(self):
        problem = self.create_draft()
        self.add_test_cases(problem)
        self.authenticate(self.admin)
        response = self.client.delete(f'/api/admin/coding/problems/{problem.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(CodingProblem.objects.filter(pk=problem.id).exists())

    def test_non_admin_cannot_create(self):
        self.authenticate(self.user)
        response = self.client.post('/api/admin/coding/problems/', problem_payload(), format='json')
        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_edit(self):
        problem = self.create_draft()
        self.add_test_cases(problem)
        self.authenticate(self.user)
        response = self.client.patch(
            f'/api/admin/coding/problems/{problem.id}/',
            {'description': 'hacked'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_delete(self):
        problem = self.create_draft()
        self.authenticate(self.user)
        response = self.client.delete(f'/api/admin/coding/problems/{problem.id}/')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(CodingProblem.objects.filter(pk=problem.id).exists())


class UserCodingProblemVisibilityTests(CodingProblemTestBase):

    def setUp(self):
        super().setUp()
        self.published = self.create_draft()
        self.published.status = CodingProblem.Status.PUBLISHED
        self.published.published_at = '2026-01-01T00:00:00Z'
        self.published.save()
        self.add_test_cases(self.published)
        self.draft = self.create_draft(title='Hidden Draft')
        self.add_test_cases(self.draft)

    def test_users_see_only_published_problems(self):
        self.authenticate(self.user)
        response = self.client.get('/api/coding/problems/')
        self.assertEqual(response.status_code, 200)
        ids = [item['id'] for item in response.data['results']]
        self.assertIn(self.published.id, ids)
        self.assertNotIn(self.draft.id, ids)

    def test_draft_problem_detail_is_not_visible(self):
        self.authenticate(self.user)
        response = self.client.get(f'/api/coding/problems/{self.draft.id}/')
        self.assertEqual(response.status_code, 404)

    def test_published_problem_detail_is_visible(self):
        self.authenticate(self.user)
        response = self.client.get(f'/api/coding/problems/{self.published.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], self.published.title)

    def test_admins_see_all_problems(self):
        self.authenticate(self.admin)
        response = self.client.get('/api/admin/coding/problems/')
        self.assertEqual(response.status_code, 200)
        ids = [item['id'] for item in response.data['results']]
        self.assertIn(self.published.id, ids)
        self.assertIn(self.draft.id, ids)

    def test_hidden_test_cases_never_exposed_to_users(self):
        self.authenticate(self.user)
        response = self.client.get(f'/api/coding/problems/{self.published.id}/')
        self.assertEqual(response.status_code, 200)
        cases = response.data['test_cases']
        self.assertGreaterEqual(len(cases), 1)
        for case in cases:
            self.assertNotIn('is_hidden', case)
            self.assertEqual(case['input'], 'p 0')  # only the public case payload

    def test_user_list_never_exposes_hidden_cases_internals(self):
        self.authenticate(self.user)
        response = self.client.get('/api/coding/problems/')
        listed = next(item for item in response.data['results'] if item['id'] == self.published.id)
        for case in listed['test_cases']:
            self.assertNotIn('is_hidden', case)
            self.assertNotEqual(case['input'], 'private 0')