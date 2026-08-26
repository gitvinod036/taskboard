from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.models import CodeSubmission, CodingProblem, CodingProblemTestCase

User = get_user_model()


def submission_payload(**overrides):
    data = {
        'language': 'python',
        'source_code': 'def two_sum(nums, target):\n    return [0, 1]\n',
    }
    data.update(overrides)
    return data


class CodeSubmissionTestBase(TestCase):
    """Base harness.

    PHASE 3 NOTE: submitting now executes code inside the Docker sandbox.
    These Phase 2 API tests stub the executor at the view boundary so they
    stay deterministic and never touch Docker; real judging behaviour is
    covered separately in test_execution.py.
    """

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
        self.user = User.objects.create_user(username='user', password='StrongPassword!42', email='user@example.com')
        self.other = User.objects.create_user(username='other', password='StrongPassword!42', email='other@example.com')
        self._stub_execution()

    def _stub_execution(self):
        """Keep submissions PENDING without invoking the sandbox."""
        docker_patcher = patch('taskflow.views.docker_available', return_value=True)
        execute_patcher = patch(
            'taskflow.views.execute_submission',
            side_effect=lambda submission, **kwargs: submission)
        docker_patcher.start()
        execute_patcher.start()
        self.addCleanup(docker_patcher.stop)
        self.addCleanup(execute_patcher.stop)
        self.problem = CodingProblem.objects.create(
            title='Two Sum',
            description='Sum two numbers from an array.',
            difficulty='EASY',
            input_format='N X then N integers.',
            output_format='Two indices.',
            constraints='1 <= N <= 100',
            explanation='',
            starter_code={
                'python': 'def two_sum(nums, target):\n    pass\n',
                'javascript': 'function twoSum(nums, target) {}\n',
                'cpp': '// cpp starter\n',
                'java': '// java starter\n',
            },
            allowed_languages=['python', 'javascript', 'cpp', 'java'],
            status=CodingProblem.Status.PUBLISHED,
            created_by=self.admin,
            published_at='2026-01-01T00:00:00Z',
        )
        CodingProblemTestCase.objects.create(
            problem=self.problem, input='2 3\n1 2',
            expected_output='0 1', is_hidden=False, order=1)
        self.hidden_case = CodingProblemTestCase.objects.create(
            problem=self.problem, input='SECRET-HIDDEN-INPUT',
            expected_output='SECRET-HIDDEN-OUTPUT', is_hidden=True, order=1001)

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def make_submission(self, user=None, problem=None, **overrides):
        submission = CodeSubmission.objects.create(
            user=user or self.user,
            problem=problem or self.problem,
            language=overrides.pop('language', 'python'),
            source_code=overrides.pop('source_code', 'print("hi")\n'),
            status=CodeSubmission.Status.PENDING,
        )
        return submission

    def submit(self, problem_id=None, payload=None):
        return self.client.post(
            f'/api/coding/problems/{problem_id if problem_id is not None else self.problem.id}/submissions/',
            payload if payload is not None else submission_payload(),
            format='json',
        )


class CodeSubmissionModelTests(CodeSubmissionTestBase):

    def test_submission_can_be_created(self):
        submission = CodeSubmission.objects.create(
            user=self.user, problem=self.problem,
            language='python', source_code='print(1)\n')
        self.assertIsNotNone(submission.pk)
        self.assertEqual(submission.user, self.user)
        self.assertEqual(submission.problem, self.problem)

    def test_default_status_is_pending(self):
        submission = CodeSubmission.objects.create(
            user=self.user, problem=self.problem,
            language='python', source_code='print(1)\n')
        self.assertEqual(submission.status, CodeSubmission.Status.PENDING)
        self.assertIn('PENDING', CodeSubmission.Status.values)

    def test_status_choices_are_valid(self):
        expected = {
            'PENDING', 'RUNNING', 'ACCEPTED', 'WRONG_ANSWER',
            'COMPILATION_ERROR', 'RUNTIME_ERROR',
            'TIME_LIMIT_EXCEEDED', 'MEMORY_LIMIT_EXCEEDED', 'SYSTEM_ERROR',
        }
        self.assertEqual(set(CodeSubmission.Status.values), expected)

    def test_user_and_problem_relationships_work(self):
        submission = self.make_submission()
        self.assertIn(submission, self.user.code_submissions.all())
        self.assertIn(submission, self.problem.submissions.all())
        self.assertEqual(str(submission).startswith(f'#{submission.pk}'), True)

    def test_execution_fields_default_to_null(self):
        submission = self.make_submission()
        self.assertIsNone(submission.execution_time)
        self.assertIsNone(submission.memory_used)
        self.assertIsNone(submission.passed_tests)
        self.assertIsNone(submission.total_tests)
        self.assertIsNone(submission.score)
        self.assertEqual(submission.feedback, '')
class SubmitCodeAPITests(CodeSubmissionTestBase):

    def test_authenticated_user_can_submit_for_published_problem(self):
        self.authenticate(self.user)
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(CodeSubmission.objects.count(), 1)
        submission = CodeSubmission.objects.get()
        self.assertEqual(submission.user, self.user)
        self.assertEqual(submission.problem, self.problem)
        self.assertEqual(submission.language, 'python')

    def test_submission_response_shape(self):
        self.authenticate(self.user)
        response = self.submit()
        self.assertEqual(response.status_code, 201)
        data = response.data
        for field in ('id', 'problem', 'language', 'status', 'source_code',
                      'execution_time', 'memory_used', 'passed_tests',
                      'total_tests', 'score', 'feedback', 'created_at'):
            self.assertIn(field, data)
        # Execution metrics stay null in Phase 2 — nothing has executed yet.
        for null_field in ('execution_time', 'memory_used', 'passed_tests',
                           'total_tests', 'score'):
            self.assertIsNone(data[null_field])

    def test_unauthenticated_user_cannot_submit(self):
        response = self.submit()
        self.assertEqual(response.status_code, 401)

    def test_user_cannot_submit_to_unpublished_problem(self):
        draft = CodingProblem.objects.create(
            title='Draft Problem', description='D', difficulty='EASY',
            input_format='I', output_format='O', constraints='C',
            starter_code={'python': 'pass'}, allowed_languages=['python'],
            status=CodingProblem.Status.DRAFT, created_by=self.admin)
        self.authenticate(self.user)
        response = self.submit(problem_id=draft.id)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(CodeSubmission.objects.count(), 0)

    def test_user_cannot_submit_to_missing_problem(self):
        self.authenticate(self.user)
        response = self.submit(problem_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_invalid_language_is_rejected(self):
        self.authenticate(self.user)
        response = self.submit(payload=submission_payload(language='cobol'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CodeSubmission.objects.count(), 0)

    def test_language_not_allowed_for_problem_is_rejected(self):
        # The problem allows python/javascript/cpp/java; ruby is a real-ish
        # id but not configured on this problem.
        self.problem.allowed_languages = ['python']
        self.problem.save()
        self.authenticate(self.user)
        response = self.submit(payload=submission_payload(language='javascript'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CodeSubmission.objects.count(), 0)

    def test_empty_source_code_is_rejected(self):
        self.authenticate(self.user)
        response = self.submit(payload=submission_payload(source_code=''))
        self.assertEqual(response.status_code, 400)
        response = self.submit(payload=submission_payload(source_code='   \n\t  '))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CodeSubmission.objects.count(), 0)

    def test_blank_language_is_rejected(self):
        self.authenticate(self.user)
        response = self.submit(payload=submission_payload(language=''))
        self.assertEqual(response.status_code, 400)

    def test_submission_starts_as_pending(self):
        self.authenticate(self.user)
        response = self.submit()
        self.assertEqual(response.data['status'], CodeSubmission.Status.PENDING)
        stored = CodeSubmission.objects.get(pk=response.data['id'])
        self.assertEqual(stored.status, CodeSubmission.Status.PENDING)

    def test_client_cannot_set_status_or_metrics(self):
        self.authenticate(self.user)
        malicious = submission_payload(status='ACCEPTED', score=100.0,
                                       passed_tests=10, total_tests=10,
                                       execution_time=0.01, memory_used=1024.0)
        response = self.submit(payload=malicious)
        self.assertEqual(response.status_code, 201)
        stored = CodeSubmission.objects.get(pk=response.data['id'])
        self.assertEqual(stored.status, CodeSubmission.Status.PENDING)
        self.assertIsNone(stored.score)
        self.assertIsNone(stored.passed_tests)
class SubmissionAccessTests(CodeSubmissionTestBase):

    def test_user_can_list_own_submissions(self):
        self.make_submission(user=self.user)
        self.make_submission(user=self.user, language='cpp')
        self.authenticate(self.user)
        response = self.client.get('/api/coding/submissions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_user_cannot_see_another_users_submissions(self):
        mine = self.make_submission(user=self.user)
        theirs = self.make_submission(user=self.other, source_code='SECRET-CODE\n')
        self.authenticate(self.user)
        response = self.client.get('/api/coding/submissions/')
        ids = [item['id'] for item in response.data['results']]
        self.assertIn(mine.id, ids)
        self.assertNotIn(theirs.id, ids)

    def test_user_can_retrieve_own_submission(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        response = self.client.get(f'/api/coding/submissions/{submission.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], submission.id)
        self.assertEqual(response.data['source_code'], 'print("hi")\n')

    def test_user_cannot_retrieve_another_users_submission(self):
        submission = self.make_submission(user=self.other, source_code='SECRET\n')
        self.authenticate(self.user)
        response = self.client.get(f'/api/coding/submissions/{submission.id}/')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn(b'SECRET', response.content)

    def test_user_cannot_modify_submissions(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.user)
        patch_response = self.client.patch(
            f'/api/coding/submissions/{submission.id}/',
            {'status': 'ACCEPTED'}, format='json')
        put_response = self.client.put(
            f'/api/coding/submissions/{submission.id}/',
            {'status': 'ACCEPTED'}, format='json')
        delete_response = self.client.delete(f'/api/coding/submissions/{submission.id}/')
        self.assertEqual(patch_response.status_code, 405)
        self.assertEqual(put_response.status_code, 405)
        self.assertEqual(delete_response.status_code, 405)
        submission.refresh_from_db()
        self.assertEqual(submission.status, CodeSubmission.Status.PENDING)
    def test_admin_can_inspect_all_submissions(self):
        self.make_submission(user=self.user, source_code='USERCODE\n')
        self.authenticate(self.admin)
        response = self.client.get('/api/admin/coding/submissions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        item = response.data['results'][0]
        self.assertEqual(item['source_code'], 'USERCODE\n')
        self.assertEqual(item['user']['username'], 'user')

    def test_non_admin_cannot_use_admin_submissions_endpoint(self):
        self.make_submission(user=self.user)
        self.authenticate(self.user)
        response = self.client.get('/api/admin/coding/submissions/')
        self.assertEqual(response.status_code, 403)

    def test_admin_can_retrieve_single_submission(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.admin)
        response = self.client.get(f'/api/admin/coding/submissions/{submission.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], submission.id)

    def test_admin_cannot_manually_edit_execution_results(self):
        submission = self.make_submission(user=self.user)
        self.authenticate(self.admin)
        response = self.client.patch(
            f'/api/admin/coding/submissions/{submission.id}/',
            {'status': 'ACCEPTED', 'score': 100}, format='json')
        self.assertEqual(response.status_code, 405)
        submission.refresh_from_db()
        self.assertEqual(submission.status, CodeSubmission.Status.PENDING)


class SubmissionSecurityTests(CodeSubmissionTestBase):

    def test_hidden_test_cases_never_exposed_through_submission_endpoints(self):
        self.make_submission(user=self.user)
        self.authenticate(self.user)
        list_response = self.client.get('/api/coding/submissions/')
        detail_response = self.client.get(
            f"/api/coding/submissions/{CodeSubmission.objects.get().id}/")
        for response in (list_response, detail_response):
            body = response.content.decode()
            self.assertNotIn('SECRET-HIDDEN-INPUT', body)
            self.assertNotIn('SECRET-HIDDEN-OUTPUT', body)

    def test_hidden_test_cases_not_in_admin_payload_either(self):
        self.make_submission(user=self.user)
        self.authenticate(self.admin)
        response = self.client.get('/api/admin/coding/submissions/')
        body = response.content.decode()
        self.assertNotIn('SECRET-HIDDEN-INPUT', body)
        self.assertNotIn('SECRET-HIDDEN-OUTPUT', body)
    def test_no_code_execution_mechanisms_used_by_the_app(self):
        """Phase 2 stores code as data only — assert no executor is wired up."""
        import inspect
        import pathlib

        import taskflow.views
        import taskflow.services
        import taskflow.serializers

        sources = []
        for module in (taskflow.views, taskflow.services, taskflow.serializers):
            path = pathlib.Path(inspect.getfile(module))
            sources.append(path.read_text(encoding='utf-8'))

        banned = (
            'exec(', 'eval(', 'os.system(', 'subprocess.run(',
            'subprocess.Popen(', 'subprocess.call(', 'shell=True',
            'check_output(', 'popen(',
        )
        for source in sources:
            for token in banned:
                self.assertNotIn(token, source)

    def test_submission_stores_source_code_only(self):
        self.authenticate(self.user)
        code = 'def solve():\n    return "anything"\n'
        response = self.submit(payload=submission_payload(source_code=code))
        self.assertEqual(response.status_code, 201)
        stored = CodeSubmission.objects.get(pk=response.data['id'])
        self.assertEqual(stored.source_code, code)
        # Nothing was executed: the row stays queued with no output artifacts.
        self.assertEqual(stored.status, CodeSubmission.Status.PENDING)
        self.assertIsNone(stored.execution_time)
        self.assertIsNone(stored.memory_used)