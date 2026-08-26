"""Phase 3 execution-service tests.

Verdict mapping, sandbox hardening, hidden-test protection and ownership are
all exercised through a FAKE sandbox so these tests are deterministic and
never require a container runtime. Live Docker behaviour is covered by the
opt-in smoke tests at the bottom of this module.
"""

from unittest.mock import patch

import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from taskflow.execution import SandboxResult, judge, normalize_output
from taskflow.execution.sandbox import DockerSandbox, docker_available
from taskflow.models import CodeSubmission, CodingProblem, CodingProblemTestCase

User = get_user_model()

ACCEPT = lambda *_args, **_kwargs: None  # noqa: E731


class FakeTest:
    """Duck-typed stand-in for CodingProblemTestCase."""
    def __init__(self, index, input_text, expected_output, is_hidden):
        self.index = index
        self.input = input_text
        self.expected_output = expected_output
        self.is_hidden = is_hidden


class ScriptedSandbox:
    """Returns a canned SandboxResult per call, in order."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def compile(self, argv, **kwargs):
        self.calls.append(('compile', argv))
        return SandboxResult(exit_code=0)

    def run(self, argv, *, workspace_path, stdin_data='', timeout_seconds=5,
            collect_metrics=True):
        self.calls.append(('run', argv, stdin_data))
        result = self.results.pop(0) if self.results else SandboxResult(exit_code=0)
        # Simulate GNU-time metric capture for realism.
        result.peak_memory_mb = result.peak_memory_mb or 42.5
        return result


class JudgeTestBase(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(username='admin', password='StrongPassword!42', email='admin@example.com')
        self.user = User.objects.create_user(username='user', password='StrongPassword!42', email='user@example.com')
        self.other = User.objects.create_user(username='other', password='StrongPassword!42', email='other@example.com')
        self.problem = CodingProblem.objects.create(
            title='Echo', description='Echo the input.', difficulty='EASY',
            input_format='One line.', output_format='Same line.',
            constraints='n/a', explanation='',
            starter_code={'python': 'print(input())\n'},
            allowed_languages=['python', 'cpp'],
            status=CodingProblem.Status.PUBLISHED,
            created_by=self.admin, published_at='2026-01-01T00:00:00Z')
        self.public_case = CodingProblemTestCase.objects.create(
            problem=self.problem, input='PUBLIC-IN',
            expected_output='PUBLIC-OUT', is_hidden=False, order=1)
        self.hidden_case = CodingProblemTestCase.objects.create(
            problem=self.problem, input='SECRET-HIDDEN-IN',
            expected_output='SECRET-HIDDEN-OUT', is_hidden=True, order=1001)

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def make_submission(self, source_code='print(input())\n', language='python'):
        return CodeSubmission.objects.create(
            user=self.user, problem=self.problem, language=language,
            source_code=source_code, mode=CodeSubmission.Mode.SUBMIT,
            status=CodeSubmission.Status.PENDING)


class VerdictMappingTests(JudgeTestBase):
    """Each verdict must come from observed sandbox behaviour."""

    def judge_with(self, results, mode='SUBMIT'):
        cases = list(self.problem.test_cases.order_by('order'))
        if mode == 'RUN':
            cases = [c for c in cases if not c.is_hidden]
        sandbox = ScriptedSandbox(results)
        outcome = judge(self.problem, 'python', 'print(input())\n',
                        cases, mode=mode, sandbox=sandbox)
        return outcome, sandbox

    def test_accepted_when_all_tests_pass(self):
        outcome, _ = self.judge_with([
            SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n'),
            SandboxResult(exit_code=0, stdout='SECRET-HIDDEN-OUT\n'),
        ])
        from taskflow.models import CodeSubmission as CS
        self.assertEqual(outcome.status, CS.Status.ACCEPTED)
        self.assertEqual(outcome.passed_tests, 2)
        self.assertEqual(outcome.total_tests, 2)
        self.assertEqual(outcome.score, 100.0)
        self.assertIsNotNone(outcome.execution_time)
        self.assertEqual(outcome.memory_used, 42.5)

    def test_wrong_answer_on_public_mismatch(self):
        outcome, _ = self.judge_with([
            SandboxResult(exit_code=0, stdout='NOPE\n'),
        ])
        from taskflow.models import CodeSubmission as CS
        self.assertEqual(outcome.status, CS.Status.WRONG_ANSWER)
        self.assertIn('Expected:', outcome.feedback)
        self.assertEqual(outcome.passed_tests, 0)
        self.assertEqual(outcome.score, 0.0)

    def test_runtime_error_on_non_zero_exit(self):
        outcome, _ = self.judge_with([
            SandboxResult(exit_code=1, stderr='Traceback (most recent call last): ...'),
        ])
        from taskflow.models import CodeSubmission as CS
        self.assertEqual(outcome.status, CS.Status.RUNTIME_ERROR)

    def test_time_limit_exceeded_when_sandbox_times_out(self):
        outcome, _ = self.judge_with([SandboxResult(timed_out=True, killed=True)])
        from taskflow.models import CodeSubmission as CS
        self.assertEqual(outcome.status, CS.Status.TIME_LIMIT_EXCEEDED)

    def test_memory_limit_exceeded_on_oom_kill(self):
        outcome, _ = self.judge_with([SandboxResult(exit_code=137)])
        from taskflow.models import CodeSubmission as CS
        self.assertEqual(outcome.status, CS.Status.MEMORY_LIMIT_EXCEEDED)

    def test_compilation_error_for_cpp(self):
        cases = list(self.problem.test_cases.order_by('order'))
        sandbox = ScriptedSandbox([])
        sandbox.compile = lambda argv, **kwargs: SandboxResult(
            exit_code=1, stderr="error: 'x' was not declared in this scope")
        outcome = judge(self.problem, 'cpp', 'int main() { return x; }',
                        cases, sandbox=sandbox)
        from taskflow.models import CodeSubmission as CS
        self.assertEqual(outcome.status, CS.Status.COMPILATION_ERROR)
        self.assertIn('not declared', outcome.feedback)
        # A compile failure must never run any test.
        self.assertEqual(outcome.total_tests, len(cases))
        self.assertEqual([c for kind, *_ in sandbox.calls if kind == 'run'], [])


class SandboxHardeningTests(JudgeTestBase):
    """The container must be locked down on every single invocation."""

    def setUp(self):
        super().setUp()
        self.sandbox = DockerSandbox()

    def hardened_command(self):
        return self.sandbox.build_command(
            ['python3', '-I', '/sandbox/solution.py'],
            workspace_path=__import__('tempfile').mkdtemp())

    def test_network_is_disabled(self):
        command = self.hardened_command()
        self.assertIn('--network', command)
        self.assertEqual(command[command.index('--network') + 1], 'none')

    def test_runs_as_non_root(self):
        command = self.hardened_command()
        index = command.index('--user')
        self.assertNotEqual(command[index + 1], '0:0')
        self.assertEqual(command[index + 1], '65534:65534')

    def test_memory_cpu_and_process_limits_are_capped(self):
        command = self.hardened_command()
        for flag in ('--memory', '--memory-swap', '--cpus', '--pids-limit'):
            self.assertIn(flag, command)
        memory = command[command.index('--memory') + 1]
        swap = command[command.index('--memory-swap') + 1]
        self.assertTrue(memory.endswith('m'))
        # Swap must not exceed RAM, otherwise the memory cap is meaningless.
        self.assertEqual(swap, memory)
        self.assertLess(int(command[command.index('--pids-limit') + 1]), 500)

    def test_filesystem_and_capabilities_are_restricted(self):
        command = self.hardened_command()
        self.assertIn('--read-only', command)
        self.assertIn('--cap-drop', command)
        self.assertEqual(command[command.index('--cap-drop') + 1], 'ALL')
        self.assertIn('no-new-privileges', command)
        self.assertIn('--security-opt', command)
        self.assertNotIn('--privileged', command)

    def test_auto_cleanup_is_enabled(self):
        self.assertIn('--rm', self.hardened_command())

    def test_user_source_never_appears_in_argv(self):
        """User code travels via the mounted file only — never the CLI."""
        malicious = 'print("pwned") ; __import__("os").system("rm -rf /")'
        from taskflow.execution.judge import _workspace_for
        workspace, source_path = _workspace_for('python', malicious)
        try:
            command = self.sandbox.build_command(
                ['python3', '-I', '/sandbox/solution.py'],
                workspace_path=workspace)
            joined = ' '.join(command)
            self.assertNotIn(malicious, joined)
            self.assertNotIn('system(', joined)
        finally:
            import shutil
            shutil.rmtree(workspace, ignore_errors=True)

    def test_mount_is_confined_to_temp_area(self):
        from taskflow.execution.sandbox import SandboxUnavailable
        with self.assertRaises(SandboxUnavailable):
            self.sandbox.build_command(['true'], workspace_path='relative/path')
        with self.assertRaises(SandboxUnavailable):
            self.sandbox.build_command(['true'], workspace_path='C:\\Windows')


class HiddenTestProtectionTests(JudgeTestBase):

    def test_hidden_details_are_not_recorded_on_outcomes(self):
        # Public passes, hidden fails: the loop must reach the hidden case.
        outcome, _ = VerdictMappingTests.judge_with(self, [
            SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n'),
            SandboxResult(exit_code=0, stdout='WRONG\n'),
        ])
        hidden_outcomes = [o for o in outcome.test_outcomes if o.is_hidden]
        self.assertTrue(hidden_outcomes)
        self.assertFalse(hidden_outcomes[0].passed)
        for item in hidden_outcomes:
            self.assertEqual(item.expected_output, '')
            self.assertEqual(item.actual_output, '')

    def test_run_mode_executes_public_tests_only(self):
        public_only = [self.public_case]
        sandbox = ScriptedSandbox([SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n')])
        judge(self.problem, 'python', 'print(input())\n',
              public_only, mode='RUN', sandbox=sandbox)
        stdin_feed = [call[2] for call in sandbox.calls if call[0] == 'run']
        self.assertEqual(stdin_feed, ['PUBLIC-IN'])
        self.assertNotIn('SECRET-HIDDEN-IN', stdin_feed)
class ExecutionAPITests(JudgeTestBase):
    """End-to-end API behaviour with a scripted sandbox."""

    def setUp(self):
        super().setUp()
        self.scripted = ScriptedSandbox([])
        docker_patcher = patch('taskflow.views.docker_available', return_value=True)
        docker_patcher.start()
        self.addCleanup(docker_patcher.stop)
        # judge() resolves its sandbox lazily via DockerSandbox(); substitute a
        # factory that hands back our scripted instance while keeping the
        # METRICS_FILENAME attribute the judge reads.
        scripted = self.scripted
        factory = type('ScriptedSandboxFactory', (), {
            'METRICS_FILENAME': '.metrics',
            '__new__': lambda cls: scripted,
        })
        judge_patcher = patch(
            'taskflow.execution.judge.DockerSandbox', factory)
        judge_patcher.start()
        self.addCleanup(judge_patcher.stop)

    def test_submit_executes_public_and_hidden_tests(self):
        self.authenticate(self.user)
        self.scripted.results = [
            SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n'),
            SandboxResult(exit_code=0, stdout='SECRET-HIDDEN-OUT\n'),
        ]
        response = self.client.post(
            f'/api/coding/problems/{self.problem.id}/submissions/',
            {'language': 'python', 'source_code': 'print(input())\n'},
            format='json')
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data
        self.assertEqual(data['status'], CodeSubmission.Status.ACCEPTED)
        self.assertEqual(data['verdict'], CodeSubmission.Status.ACCEPTED)
        self.assertEqual(data['mode'], CodeSubmission.Mode.SUBMIT)
        self.assertEqual(data['passed_tests'], 2)
        self.assertIsNotNone(data['completed_at'])
        stored = CodeSubmission.objects.get(pk=data['id'])
        self.assertEqual(stored.total_tests, 2)

    def test_run_executes_public_tests_only(self):
        self.authenticate(self.user)
        self.scripted.results = [SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n')]
        response = self.client.post(
            f'/api/coding/problems/{self.problem.id}/run/',
            {'language': 'python', 'source_code': 'print(input())\n'},
            format='json')
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data
        self.assertEqual(data['mode'], CodeSubmission.Mode.RUN)
        self.assertEqual(data['status'], CodeSubmission.Status.ACCEPTED)
        stdin_feed = [c[2] for c in self.scripted.calls if c[0] == 'run']
        self.assertEqual(stdin_feed, ['PUBLIC-IN'])

    def test_submission_response_never_contains_hidden_data(self):
        self.authenticate(self.user)
        self.scripted.results = [SandboxResult(exit_code=0, stdout='WRONG\n')]
        response = self.client.post(
            f'/api/coding/problems/{self.problem.id}/submissions/',
            {'language': 'python', 'source_code': 'print(input())\n'},
            format='json')
        body = response.content.decode()
        self.assertNotIn('SECRET-HIDDEN-IN', body)
        self.assertNotIn('SECRET-HIDDEN-OUT', body)

    def test_user_cannot_set_verdict_or_metrics(self):
        self.authenticate(self.user)
        self.scripted.results = [SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n')]
        response = self.client.post(
            f'/api/coding/problems/{self.problem.id}/submissions/',
            {'language': 'python', 'source_code': 'print(input())\n',
             'status': 'ACCEPTED', 'score': 100, 'verdict': 'ACCEPTED',
             'passed_tests': 99},
            format='json')
        self.assertEqual(response.status_code, 201)
        stored = CodeSubmission.objects.get(pk=response.data['id'])
        # Values come from the judge, not from the request payload.
        self.assertEqual(stored.passed_tests, 1)
        self.assertEqual(stored.status, stored.verdict)
    def test_invalid_language_never_reaches_the_sandbox(self):
        self.authenticate(self.user)
        before = len(self.scripted.calls)
        response = self.client.post(
            f'/api/coding/problems/{self.problem.id}/submissions/',
            {'language': 'ruby', 'source_code': 'puts 1'},
            format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.scripted.calls), before)

    def test_unauthenticated_run_is_rejected(self):
        client = APIClient()
        response = client.post(
            f'/api/coding/problems/{self.problem.id}/run/',
            {'language': 'python', 'source_code': 'x'},
            format='json')
        self.assertEqual(response.status_code, 401)

    def test_unpublished_problem_cannot_be_run(self):
        self.problem.status = CodingProblem.Status.DRAFT
        self.problem.save()
        self.authenticate(self.user)
        response = self.client.post(
            f'/api/coding/problems/{self.problem.id}/run/',
            {'language': 'python', 'source_code': 'x'},
            format='json')
        self.assertEqual(response.status_code, 404)

    def test_sandbox_unavailable_yields_system_error_not_a_crash(self):
        from taskflow.execution.sandbox import SandboxUnavailable
        self.authenticate(self.user)
        with patch('taskflow.execution.judge.DockerSandbox',
                   side_effect=SandboxUnavailable('no docker')):
            response = self.client.post(
                f'/api/coding/problems/{self.problem.id}/run/',
                {'language': 'python', 'source_code': 'print(1)'},
                format='json')
        self.assertEqual(response.status_code, 201)
        stored = CodeSubmission.objects.get(pk=response.data['id'])
        self.assertEqual(stored.status, CodeSubmission.Status.SYSTEM_ERROR)


class OwnershipOnExecutionTests(JudgeTestBase):

    def test_users_cannot_modify_execution_results(self):
        submission = CodeSubmission.objects.create(
            user=self.other, problem=self.problem, language='python',
            source_code='x', mode=CodeSubmission.Mode.SUBMIT,
            status=CodeSubmission.Status.ACCEPTED, score=100)
        self.authenticate(self.user)
        for method, payload in (
            ('patch', {'status': 'WRONG_ANSWER', 'score': 1}),
            ('put', {'status': 'WRONG_ANSWER'}),
            ('delete', None),
        ):
            sender = getattr(self.client, method)
            if payload:
                response = sender(f'/api/coding/submissions/{submission.id}/',
                                  payload, format='json')
            else:
                response = sender(f'/api/coding/submissions/{submission.id}/')
            self.assertEqual(response.status_code, 405, method)
        submission.refresh_from_db()
        self.assertEqual(submission.status, CodeSubmission.Status.ACCEPTED)
        self.assertEqual(submission.score, 100)

    def test_admin_cannot_fabricate_results_via_api(self):
        submission = CodeSubmission.objects.create(
            user=self.user, problem=self.problem, language='python',
            source_code='x', status=CodeSubmission.Status.ACCEPTED)
        self.authenticate(self.admin)
        response = self.client.patch(
            f'/api/admin/coding/submissions/{submission.id}/',
            {'score': 100, 'status': 'ACCEPTED'}, format='json')
        self.assertEqual(response.status_code, 405)

    def test_admin_sees_source_but_not_hidden_cases(self):
        CodeSubmission.objects.create(
            user=self.user, problem=self.problem, language='python',
            source_code='ADMIN-VIEW-CODE', status=CodeSubmission.Status.PENDING)
        self.authenticate(self.admin)
        response = self.client.get('/api/admin/coding/submissions/')
        body = response.content.decode()
        self.assertIn('ADMIN-VIEW-CODE', body)
        self.assertNotIn('SECRET-HIDDEN-IN', body)
        self.assertNotIn('SECRET-HIDDEN-OUT', body)


class OutputNormalisationTests(JudgeTestBase):

    def test_trailing_whitespace_ignored_but_content_exact(self):
        self.assertEqual(normalize_output('out\n'), normalize_output('out'))
        self.assertEqual(normalize_output('a  \nb\n'), normalize_output('a\nb'))
        self.assertNotEqual(normalize_output('a b'), normalize_output('ab'))
class LiveDockerSmokeTests(JudgeTestBase):
    """Real container execution — skipped when Docker is unavailable."""

    def setUp(self):
        super().setUp()
        if not docker_available():
            self.skipTest('Docker is not available on this host')

    @override_settings(CODE_SANDBOX={'image': 'alpine:3.19'})
    def test_sandbox_reports_command_output(self):
        sandbox = DockerSandbox()
        workspace = tempfile.mkdtemp(prefix='smoke-')
        try:
            result = sandbox.run(['echo', 'HELLO-FROM-SANDBOX'],
                                 workspace_path=workspace, collect_metrics=False)
            self.assertEqual(result.exit_code, 0)
            self.assertIn('HELLO-FROM-SANDBOX', result.stdout)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    @override_settings(CODE_SANDBOX={'image': 'alpine:3.19'})
    def test_timeout_is_enforced(self):
        sandbox = DockerSandbox()
        workspace = tempfile.mkdtemp(prefix='smoke-')
        try:
            result = sandbox.run(['sleep', '30'], workspace_path=workspace,
                                 timeout_seconds=2, collect_metrics=False)
            self.assertTrue(result.timed_out)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    @override_settings(CODE_SANDBOX={'image': 'alpine:3.19'})
    def test_no_network_inside_container(self):
        sandbox = DockerSandbox()
        workspace = tempfile.mkdtemp(prefix='smoke-')
        try:
            result = sandbox.run(
                ['wget', '-q', '-T', '3', 'https://example.com'],
                workspace_path=workspace, timeout_seconds=8, collect_metrics=False)
            self.assertNotEqual(result.exit_code, 0)
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    @override_settings(CODE_SANDBOX={'image': 'alpine:3.19'})
    def test_workspace_is_removed_after_judging(self):
        import glob
        import time
        pattern = os.path.join(tempfile.gettempdir(), 'taskflow-judge-*')
        before = set(glob.glob(pattern))
        sandbox = ScriptedSandbox([SandboxResult(exit_code=0, stdout='PUBLIC-OUT\n')])
        judge(self.problem, 'python', 'print(input())\n',
              [self.public_case], mode='RUN', sandbox=sandbox)
        # On Windows a just-unmounted dir can be released asynchronously, so
        # allow the OS a moment before asserting the workspace is gone.
        for _ in range(10):
            if not (set(glob.glob(pattern)) - before):
                break
            time.sleep(0.5)
        after = set(glob.glob(pattern))
        self.assertFalse(after - before, 'Judge workspaces must be cleaned up')