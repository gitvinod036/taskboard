"""Secure code-execution service for the coding system.

Public entry points:
    execute_run(...)      - run a solution against PUBLIC tests only
    execute_submission(...) - judge a submission against public + hidden tests
    docker_available()    - whether the container runtime is usable

Every execution happens inside an isolated Docker container. Nothing in this
package interprets or executes user code on the Django host.
"""

from .sandbox import DockerSandbox, SandboxResult, SandboxUnavailable
from .sandbox import docker_available, sandbox_settings
from .judge import JudgeOutcome, TestOutcome, judge, normalize_output

__all__ = [
    'DockerSandbox', 'SandboxResult', 'SandboxUnavailable',
    'docker_available', 'sandbox_settings',
    'JudgeOutcome', 'TestOutcome', 'judge', 'normalize_output',
]


def _apply_outcome(submission, outcome):
    """Persist a JudgeOutcome onto a CodeSubmission (server-side only)."""
    from django.utils import timezone

    submission.status = outcome.status
    submission.verdict = outcome.status
    submission.passed_tests = outcome.passed_tests
    submission.total_tests = outcome.total_tests
    submission.score = outcome.score
    submission.execution_time = outcome.execution_time
    submission.memory_used = outcome.memory_used
    submission.feedback = outcome.feedback[:8000]
    submission.completed_at = timezone.now()
    # Public-only outcomes so serializers can show detail without ever
    # touching hidden cases.
    submission._public_test_outcomes = [
        outcome for outcome in outcome.test_outcomes if not outcome.is_hidden
    ]
    submission.save(update_fields=(
        'status', 'verdict', 'passed_tests', 'total_tests', 'score',
        'execution_time', 'memory_used', 'feedback', 'completed_at',
        'updated_at',
    ))
    return submission


def execute_submission(submission, *, mode='SUBMIT', sandbox=None):
    """Judge ``submission`` and persist the results.

    mode='RUN'    -> public test cases only
    mode='SUBMIT' -> public + hidden test cases
    """
    from taskflow.models import CodeSubmission

    if mode == 'RUN':
        cases = list(submission.problem.test_cases.filter(is_hidden=False).order_by('order'))
    else:
        cases = list(submission.problem.test_cases.order_by('order'))

    submission.status = CodeSubmission.Status.RUNNING
    submission.save(update_fields=('status', 'updated_at'))

    try:
        outcome = judge(
            submission.problem, submission.language,
            submission.source_code, cases, mode=mode, sandbox=sandbox)
    except SandboxUnavailable as exc:
        submission.status = CodeSubmission.Status.SYSTEM_ERROR
        submission.verdict = CodeSubmission.Status.SYSTEM_ERROR
        submission.feedback = f'Execution environment unavailable: {exc}'
        from django.utils import timezone
        submission.completed_at = timezone.now()
        submission.save(update_fields=(
            'status', 'verdict', 'feedback', 'completed_at', 'updated_at'))
        return submission

    return _apply_outcome(submission, outcome)