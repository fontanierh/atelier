"""Attach the independent memory guard to a native Unreal child a harness already owns.

`atelier.safety.guarded.run` owns the whole lifecycle. Harnesses that must keep their own launch, deadline,
overlap and artifact checks (the benchmark, reviews, captures) instead wrap their
existing child:

    with attach(process.pid, folder/'memory-health.json', duration=610) as monitor:
        while process.poll() is None:
            if monitor.poll() is not None: raise RuntimeError('Memory monitor exited before the game')
            ...

The monitor is a sibling process, so a stalled render thread cannot defeat it, and exactly one
monitor watches one child. Identity is pinned to the child's start time, so a reused PID is never
signalled. Ceiling stays at the project default of 10 GiB.
"""
import subprocess, sys
from contextlib import contextmanager
from pathlib import Path

from .memory_guard import usage

GUARD = Path(__file__).with_name('memory_guard.py')


def reap(child, grace=10.):
    """Never leave an owned Unreal behind: ask it to stop, then insist."""
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


@contextmanager
def attach(pid, report, duration, limit_gib=10.):
    """`duration=None` means no time limit: the ceiling still applies, nothing kills on the clock."""
    try:
        started = usage(pid).started
    except ProcessLookupError:
        yield None
        return
    command = [sys.executable, str(GUARD), '--pid', str(pid),
               '--expected-start', str(started), '--report', str(report),
               '--limit-gib', str(limit_gib)]
    if duration is not None:
        command += ['--duration', str(duration)]
    monitor = subprocess.Popen(command)
    try:
        yield monitor
    finally:
        if monitor.poll() is None:
            monitor.terminate()
        try:
            monitor.wait(timeout=5)
        except subprocess.TimeoutExpired:
            monitor.kill()
