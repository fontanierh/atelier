"""Launch owned work with application resource policies on macOS.

taskpolicy execs the command in the same process: Popen's PID, pipes, exit status
and the existing memory guard/cleanup still refer to the actual owned child.
Jobs and games use normal application policies and keep at least nice 10.
No service, extra writer, render admission or worker count is added.
Explicit PRIO_DARWIN_BG and QoS clamps are separate policies, not cleared here.
"""
import os
import subprocess
import sys


def policy_command(command, *, kind='job'):
    """Return an argv with normal application policies on macOS, unchanged elsewhere."""
    if isinstance(command, (str, bytes)):
        raise TypeError('Expected an argv sequence, not a shell command')
    argv = list(command)
    if not argv:
        raise ValueError('Nothing to launch')
    if kind not in ('job', 'compile', 'game'):
        raise ValueError('Unknown process kind: '+str(kind))
    if sys.platform != 'darwin':
        return argv
    prefix = ['/usr/sbin/taskpolicy', '-a']
    # nice increments the inherited value. Do not turn an already-nice-10
    # agent's child into nice 20, or undo a caller's lower priority.
    adjustment = max(0, 10-os.getpriority(os.PRIO_PROCESS, 0))
    if adjustment:
        prefix += ['/usr/bin/nice', '-n', str(adjustment)]
    return prefix+argv


def spawn(command, *, kind='job', **kwargs):
    """A normal Popen child, retaining all the caller's I/O and lifecycle options."""
    if kwargs.get('shell'):
        raise ValueError('Owned work must use argv, not shell=True')
    return subprocess.Popen(policy_command(command, kind=kind), **kwargs)


def spawn_game(command, **kwargs):
    return spawn(command, kind='game', **kwargs)
