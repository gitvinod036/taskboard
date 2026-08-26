"""Docker-backed sandbox for running untrusted user code.

SECURITY CONTRACT
=================
* User code NEVER touches the Django host. It is written into an isolated
  temporary workspace directory and executed inside a locked-down container.
* The user's source code is never placed on the container command line or in
  any environment variable, so it cannot be interpreted by a shell. Only
  platform-owned argv tokens (compilers/interpreters plus file names we
  chose) ever reach the command line.
* Containers run with: no network, capped CPU/memory/PIDs, read-only root
  filesystem, all Linux capabilities dropped, no privilege escalation, and a
  non-root uid/gid.
* Workspaces are created under the system temp dir with restrictive
  permissions and always deleted in a ``finally`` block. Containers use
  ``--rm`` so they are reaped automatically even on failure.
"""

import os
import shutil
import subprocess
import tempfile
import time

from django.conf import settings


class SandboxUnavailable(RuntimeError):
    """Raised when the configured container runtime cannot be used."""


class SandboxResult:
    """Outcome of a single sandboxed invocation."""

    __slots__ = ('exit_code', 'stdout', 'stderr', 'timed_out',
                 'duration_seconds', 'peak_memory_mb', 'killed')

    def __init__(self, exit_code=None, stdout='', stderr='', timed_out=False,
                 duration_seconds=0.0, peak_memory_mb=None, killed=False):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.duration_seconds = duration_seconds
        self.peak_memory_mb = peak_memory_mb
        self.killed = killed

    @property
    def oom_killed(self):
        # 137 == SIGKILL (128+9): how the kernel OOM killer terminates a
        # process that blew past its cgroup memory limit.
        return self.exit_code == 137 or self.killed

    def truncated_stderr(self, limit=2000):
        text = (self.stderr or '').strip()
        if len(text) > limit:
            return text[:limit] + '\n... [truncated]'
        return text


def sandbox_settings():
    """Effective sandbox configuration (settings override the defaults)."""
    from taskflow.languages import SANDBOX_DEFAULTS

    config = dict(SANDBOX_DEFAULTS)
    config.update(getattr(settings, 'CODE_SANDBOX', {}) or {})
    return config


def docker_binary():
    return shutil.which('docker')


def docker_available():
    """True when a usable container runtime is present on this host."""
    binary = docker_binary()
    if not binary:
        return False
    try:
        probe = subprocess.run(
            [binary, 'info', '--format', '{{.ServerVersion}}'],
            capture_output=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


class DockerSandbox:
    """Runs single commands inside an ephemeral, resource-capped container."""

    METRICS_FILENAME = '.metrics'

    def __init__(self):
        config = sandbox_settings()
        self.image = config['image']
        self.workspace_mount = config['workspace_mount']
        self.memory_mb = int(config['memory_mb'])
        self.cpu_cores = str(config['cpu_cores'])
        self.pids_limit = int(config['pids_limit'])
        self.container_user = config['container_user']
        self.binary = docker_binary()

    def security_flags(self):
        """Hardening flags applied to every container.

        A method (not a constant) so tests can assert the guarantees.
        """
        return [
            '--rm',                                    # auto-remove container
            '--network', 'none',                       # no network access
            '-i',                                      # keep STDIN open for tests
            '--memory', f'{self.memory_mb}m',           # RAM ceiling
            '--memory-swap', f'{self.memory_mb}m',      # swap disabled (== RAM)
            '--cpus', self.cpu_cores,                   # CPU quota
            '--pids-limit', str(self.pids_limit),       # fork-bomb cap
            '--read-only',                              # immutable root filesystem
            '--cap-drop', 'ALL',                        # no kernel capabilities
            '--security-opt', 'no-new-privileges',      # cannot gain privileges
            '--user', self.container_user,               # non-root uid/gid
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=16m',
            '--ulimit', 'fsize=67108864',
            '--ulimit', 'nproc=64',
        ]

    def _workspace_host_path(self, workspace_path):
        """Absolute host path for the bind mount."""
        if not os.path.isabs(workspace_path):
            raise SandboxUnavailable('Workspace path must be absolute.')
        resolved = os.path.realpath(workspace_path)
        temp_root = os.path.realpath(tempfile.gettempdir())
        if resolved != temp_root and not resolved.startswith(temp_root + os.sep):
            raise SandboxUnavailable('Refusing to mount a non-temporary path.')
        return resolved

    def build_command(self, argv, workspace_path):
        """Assemble the full ``docker run`` argv for an in-container command."""
        if not self.binary:
            raise SandboxUnavailable('Docker is not available on this host.')
        host_path = self._workspace_host_path(workspace_path)
        return [self.binary, 'run'] + self.security_flags() + [
            '-v', f'{host_path}:{self.workspace_mount}',
            '-w', self.workspace_mount,
            self.image,
        ] + list(argv)

    def run(self, argv, *, workspace_path, stdin_data='', timeout_seconds=5,
            collect_metrics=True):
        """Execute ``argv`` inside the sandbox and return a SandboxResult."""
        command = self.build_command(argv, workspace_path)
        effective_timeout = float(timeout_seconds) + 15  # grace for spin-up
        started = time.monotonic()
        try:
            completed = subprocess.run(
                command,
                input=(stdin_data or '').encode('utf-8', errors='replace'),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=effective_timeout,
                # Deliberately minimal env: nothing from the host leaks in and
                # no user data travels through the CLI.
                env=_cli_environment(),
            )
        except subprocess.TimeoutExpired:
            _kill_stale_containers()
            return SandboxResult(
                exit_code=None, timed_out=True, killed=True,
                duration_seconds=float(timeout_seconds),
                peak_memory_mb=self._read_peak_memory(workspace_path) if collect_metrics else None,
            )
        except OSError as exc:
            raise SandboxUnavailable(f'Failed to start the sandbox: {exc}') from exc

        result = SandboxResult(
            exit_code=completed.returncode,
            stdout=completed.stdout.decode('utf-8', errors='replace'),
            stderr=completed.stderr.decode('utf-8', errors='replace'),
            duration_seconds=round(time.monotonic() - started, 3),
        )
        if collect_metrics:
            result.peak_memory_mb = self._read_peak_memory(workspace_path)
        return result

    def compile(self, argv, *, workspace_path, timeout_seconds=20):
        """Compile step: same isolation, no stdin, no metrics collection."""
        return self.run(
            argv, workspace_path=workspace_path, stdin_data='',
            timeout_seconds=timeout_seconds, collect_metrics=False)

    def _read_peak_memory(self, workspace_path):
        """Peak RSS (MB) written by GNU ``time`` inside the container."""
        metrics_path = os.path.join(workspace_path, self.METRICS_FILENAME)
        try:
            with open(metrics_path, 'r', encoding='utf-8', errors='ignore') as handle:
                raw = handle.read().strip()
        except OSError:
            return None
        finally:
            try:
                os.remove(metrics_path)
            except OSError:
                pass
        for line in reversed(raw.splitlines()):
            if line.strip().isdigit():
                return round(int(line) / 1024.0, 2)  # KB -> MB
        return None


def _cli_environment():
    """Environment for the docker CLI only — deliberately minimal."""
    env = {'PATH': os.environ.get('PATH', '')}
    for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG'):
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


def _kill_stale_containers():
    """Best-effort reap of judge containers left by a hung run."""
    binary = docker_binary()
    if not binary:
        return
    image = sandbox_settings()['image']
    try:
        listing = subprocess.run(
            [binary, 'ps', '-q', '--filter', f'ancestor={image}'],
            capture_output=True, timeout=10, env=_cli_environment())
        for container_id in listing.stdout.decode().split()[:20]:
            subprocess.run([binary, 'rm', '-f', container_id.strip()],
                           capture_output=True, timeout=10, env=_cli_environment())
    except (OSError, subprocess.SubprocessError):
        pass