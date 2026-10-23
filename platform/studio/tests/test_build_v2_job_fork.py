"""C5c: a sandboxed build-v2 Python job cannot fork, so a resident loop's job leaves no process.

Per-unit quiescence in a resident session rests on two things: this no-fork sandbox (an
assumption that depends on the sandbox profile) and the guard's tree sample after each terminal
reply. This test pins the first one against the production loop's real profile.
"""
import subprocess
import sys

import pytest

from atelier.build_v2 import python_worker
from test_build_v2_python_worker import WORKER, Loop, stage

pytestmark = [pytest.mark.macos_only]

FORK = '''
import os, time
def run(context):
    pid = os.fork()
    if pid == 0:
        try:
            context.output('forked.txt').write_text('child')
        finally:
            time.sleep(30)
            os._exit(0)
    os.waitpid(pid, 0)
    context.output('piece.txt').write_text('parent')
'''

SPAWN = '''
import subprocess, sys
def run(context):
    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    context.output('piece.txt').write_text('parent')
'''


def children(pid):
    found = subprocess.run(['pgrep', '-P', str(pid)], capture_output=True, text=True).stdout.split()
    return [int(child) for child in found]


@pytest.mark.parametrize('name, script', [('fork', FORK), ('spawn', SPAWN)])
def test_a_sandboxed_job_that_forks_fails_and_leaves_no_process(tmp_path, name, script):
    loop = Loop(WORKER)
    try:
        job = stage(tmp_path / name, script=script)
        response = loop.run(job)
        assert response['type'] == 'failed', response
        assert response['failure']['kind'] == 'dependency', response
        assert not (tmp_path / name / 'output' / 'forked.txt').exists()
        assert not (tmp_path / name / 'output' / 'piece.txt').exists()
        assert children(loop.process.pid) == [], 'the job child is reaped and nothing outlives it'
        loop.close()
    finally:
        if loop.process.poll() is None:
            loop.process.kill()
            loop.process.wait()


NATIVE_FORK = (
    'import ctypes, os\n'
    'libc = ctypes.CDLL(None, use_errno=True)\n'
    'pid = libc.fork()\n'
    'os._exit(0 if pid == 0 else (5 if pid > 0 else (7 if ctypes.get_errno() == 1 else 9)))\n'
)


def test_the_kernel_profile_itself_denies_fork_and_spawn_even_past_the_python_guard(tmp_path):
    """The no-fork assumption must not rest on the Python-level guard alone."""
    job = stage(tmp_path / 'job')['job_dir']
    profile = python_worker.sandbox_profile(job)

    def status(code):
        command = [python_worker.SANDBOX_EXEC, '-p', profile, sys.executable, *python_worker.CHILD_FLAGS, '-c', code]
        return subprocess.run(command, cwd=job, env=dict(python_worker.JOB_ENVIRONMENT), capture_output=True,
                              timeout=20).returncode

    assert status('import os; os.fork()') == 1  # PermissionError
    assert status('import os, sys; os.posix_spawn(sys.executable, [sys.executable, "-c", "pass"], {})') == 1
    assert status(NATIVE_FORK) == 7, 'a native fork() returns -1 with EPERM: no child exists'
