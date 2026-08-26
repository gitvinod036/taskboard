"""Judging orchestration: compile once, then run each test in the sandbox.

Verdicts are derived strictly from observed sandbox behaviour. The user's
code is only ever fed test input on stdin; expected outputs are compared
afterwards and hidden cases are never echoed back to users.
"""

import os
import shutil
import stat
import tempfile
from dataclasses import dataclass, field

from ..languages import (
    SANDBOX_DEFAULTS,
    compile_command_for,
    run_command_for,
    source_filename,
)
from .sandbox import DockerSandbox, SandboxUnavailable  # noqa: F401


@dataclass
class TestOutcome:
    """Per-test result. Hidden cases stay opaque to end users."""
    index: int            # 1-based position within the executed set
    is_hidden: bool
    passed: bool
    # Populated ONLY for public tests; hidden cases never carry these.
    expected_output: str = ''
    actual_output: str = ''


@dataclass
class JudgeOutcome:
    status: str = None    # CodeSubmission.Status value
    passed_tests: int = 0
    total_tests: int = 0
    score: float = 0.0
    execution_time = None   # seconds (float) or None
    memory_used = None      # MB (float) or None
    feedback: str = ''
    test_outcomes: list = field(default_factory=list)


def normalize_output(text):
    """Compare-friendly normalisation: trim trailing spaces per line and any
    trailing blank lines. Inner content stays exact so formatting mistakes
    still fail honestly."""
    lines = [line.rstrip() for line in (text or '').splitlines()]
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines)


def _workspace_for(language, source_code):
    """Create an isolated temp workspace holding the user's source file."""
    directory = tempfile.mkdtemp(prefix='taskflow-judge-')
    path = os.path.join(directory, source_filename(language))
    with open(path, 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(source_code)
    # Owner-writable (so cleanup works on every OS) but readable by the
    # non-root container user, who cannot write to it.
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    # The container's non-root uid must be able to write compiled artifacts
    # (g++/javac output) into this per-run directory.
    os.chmod(directory, 0o777)
    return directory, path


def _rmtree_force(path):
    """rmtree that clears read-only bits first (needed on Windows)."""
    def _onerror(func, failing_path, _exc_info):
        try:
            os.chmod(failing_path, stat.S_IRWXU)
            func(failing_path)
        except OSError:
            pass
    shutil.rmtree(path, onerror=_onerror)


def _mount_path(source_path, workspace):
    """Source file location as seen from inside the container."""
    mount_root = SANDBOX_DEFAULTS['workspace_mount']
    relative = os.path.relpath(source_path, workspace)
    return f'{mount_root}/{relative.replace(os.sep, "/")}'


def _render(argv_template, *, source_path, source_stem):
    """Substitute placeholders with concrete in-container paths."""
    return [
        token.format(source_path=source_path, source_stem=source_stem)
        if isinstance(token, str) else token
        for token in argv_template
    ]


def _metrics_wrapper(argv):
    """Wrap argv with GNU time so peak RSS can be captured per run."""
    return ['/usr/bin/time', '-f', '%M', '-o', DockerSandbox.METRICS_FILENAME] + list(argv)


def judge(problem, language, source_code, test_cases, mode='SUBMIT',
          sandbox=None):
    """Execute ``test_cases`` against ``source_code``; returns JudgeOutcome.

    ``mode`` is 'RUN' (public tests only) or 'SUBMIT' (public + hidden).
    Raises SandboxUnavailable when no container runtime is usable.
    The temporary workspace is always removed, even on failure.
    """
    from taskflow.models import CodeSubmission

    outcome = JudgeOutcome(status=CodeSubmission.Status.SYSTEM_ERROR)
    outcome.total_tests = len(test_cases)
    if not test_cases:
        outcome.feedback = 'This problem has no executable tests configured.'
        return outcome

    workspace, source_path = _workspace_for(language, source_code)
    try:
        return _judge_in_workspace(
            sandbox or DockerSandbox(), problem, language,
            test_cases, outcome, workspace, source_path)
    finally:
        _rmtree_force(workspace)


def _limits_for(problem):
    from ..execution.sandbox import sandbox_settings

    config = sandbox_settings()
    return {
        'run_timeout': float(
            getattr(problem, 'time_limit_seconds', None)
            or config['run_timeout_seconds']),
        'compile_timeout': float(config['compile_timeout_seconds']),
        'memory_mb': int(config['memory_mb']),
    }


def _judge_in_workspace(sandbox, problem, language, test_cases, outcome,
                        workspace, source_path):
    from taskflow.models import CodeSubmission

    limits = _limits_for(problem)
    stem = os.path.splitext(os.path.basename(source_path))[0]
    mounted = _mount_path(source_path, workspace)

    compile_template = compile_command_for(language)
    if compile_template:
        compiled = sandbox.compile(
            _render(compile_template, source_path=mounted, source_stem=stem),
            workspace_path=workspace,
            timeout_seconds=limits['compile_timeout'],
        )
        if compiled.timed_out:
            outcome.status = CodeSubmission.Status.TIME_LIMIT_EXCEEDED
            outcome.feedback = 'Compilation exceeded the allowed time.'
            return outcome
        if compiled.exit_code != 0:
            outcome.status = CodeSubmission.Status.COMPILATION_ERROR
            outcome.feedback = compiled.truncated_stderr() or 'Compilation failed.'
            return outcome

    slowest = 0.0
    peak_memory = None
    passed_count = 0

    for index, test_case in enumerate(test_cases, start=1):
        argv = _metrics_wrapper(_render(
            run_command_for(language), source_path=mounted, source_stem=stem))
        result = sandbox.run(
            argv, workspace_path=workspace,
            stdin_data=test_case.input or '',
            timeout_seconds=limits['run_timeout'],
        )
        slowest = max(slowest, result.duration_seconds)
        if result.peak_memory_mb is not None:
            peak_memory = max(peak_memory or 0.0, result.peak_memory_mb)

        if result.timed_out:
            status = CodeSubmission.Status.TIME_LIMIT_EXCEEDED
        elif result.oom_killed:
            status = CodeSubmission.Status.MEMORY_LIMIT_EXCEEDED
        elif result.exit_code != 0:
            status = CodeSubmission.Status.RUNTIME_ERROR
        elif normalize_output(result.stdout) == normalize_output(test_case.expected_output):
            status = CodeSubmission.Status.ACCEPTED
        else:
            status = CodeSubmission.Status.WRONG_ANSWER

        passed = status == CodeSubmission.Status.ACCEPTED
        if passed:
            passed_count += 1

        # Hidden cases stay opaque: never record their expected/actual text.
        hidden = bool(test_case.is_hidden)
        outcome.test_outcomes.append(TestOutcome(
            index=index, is_hidden=hidden, passed=passed,
            expected_output='' if hidden else (test_case.expected_output or ''),
            actual_output='' if hidden else result.stdout[:4000],
        ))

        if status != CodeSubmission.Status.ACCEPTED:
            return _finalise_failure(outcome, status, passed_count, index,
                                     slowest, peak_memory, limits, result)

    outcome.status = CodeSubmission.Status.ACCEPTED
    outcome.passed_tests = passed_count
    outcome.execution_time = round(slowest, 3)
    outcome.memory_used = peak_memory
    outcome.score = 100.0
    outcome.feedback = f'All {outcome.total_tests} tests passed.'
    return outcome


def _finalise_failure(outcome, status, passed_count, index, slowest,
                      peak_memory, limits, result):
    from taskflow.models import CodeSubmission

    outcome.status = status
    outcome.passed_tests = passed_count
    outcome.execution_time = round(slowest, 3)
    outcome.memory_used = peak_memory
    outcome.score = round((passed_count / outcome.total_tests) * 100, 2) \
        if outcome.total_tests else 0.0

    if status == CodeSubmission.Status.WRONG_ANSWER:
        public_failures = [o for o in outcome.test_outcomes
                           if not o.is_hidden and not o.passed]
        if public_failures:
            first = public_failures[0]
            outcome.feedback = (
                f'Wrong answer on public test {first.index}.\n'
                f'Expected:\n{first.expected_output}\n'
                f'Received:\n{first.actual_output}')
        else:
            outcome.feedback = 'Output did not match on a hidden test.'
    elif status == CodeSubmission.Status.TIME_LIMIT_EXCEEDED:
        outcome.feedback = f'Exceeded the {limits["run_timeout"]:g}s limit on test {index}.'
    elif status == CodeSubmission.Status.MEMORY_LIMIT_EXCEEDED:
        outcome.feedback = f'Exceeded the {limits["memory_mb"]}MB memory limit on test {index}.'
    else:
        outcome.feedback = (result.truncated_stderr()
                            or f'Non-zero exit ({result.exit_code}) on test {index}.')
    return outcome