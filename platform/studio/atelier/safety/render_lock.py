"""One Unreal at a time, across every worktree on this machine.

Each harness used to run its own preflight scan, which cannot stop two of them starting together:
both scan, both see nothing, both launch. `render_lock()` takes an exclusive advisory lock on a
single file outside any checkout, so the second caller is refused rather than admitted, and then
scans for render processes that no lock-aware harness owns (the phone stream's game, a hand-started
editor, a Blender render). The lock file carries the holder's pid, start time, checkout and purpose
so a refusal can name who is running; a holder that has exited, or whose pid has been recycled, does
not block anything.

    with render_lock('benchmark spawn'):
        ...launch exactly one Unreal child...

`ATELIER_RENDER_LOCK` moves the lock file and `ATELIER_RENDER_LOCK_SCAN=0` skips the foreign
process scan. Both exist for the CPU tests; a real measurement uses the defaults.
"""
import fcntl, json, os, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path


from .memory_guard import usage

DEFAULT_LOCK = Path.home()/'.cache/atelier/render.lock'
RENDER_NAMES = ('UnrealEditor', 'UnrealEditor-Cmd', 'ShaderCompileWorker', 'blender', 'Blender')


def lock_path():
    return Path(os.environ.get('ATELIER_RENDER_LOCK') or DEFAULT_LOCK)


def render_processes(ignore=()):
    """Live render processes by name, excluding pids in `ignore` and this process."""
    listing = subprocess.run(['ps', '-axo', 'pid=,comm='], capture_output=True, text=True).stdout
    skip = set(ignore) | {os.getpid()}
    found = []
    for line in listing.splitlines():
        fields = line.strip().split(None, 1)
        if len(fields) != 2 or not fields[0].isdigit():
            continue
        pid, command = int(fields[0]), fields[1]
        if pid not in skip and Path(command).name in RENDER_NAMES:
            found.append({'pid': pid, 'command': command})
    return found


def holder(handle):
    """Whoever last wrote the lock file, if that process is still the one it claims to be."""
    try:
        handle.seek(0)
        record = json.loads(handle.read() or '{}')
    except (OSError, ValueError):
        return None
    pid, started = record.get('pid'), record.get('started')
    if not pid:
        return None
    try:
        if started is not None and usage(pid).started != started:
            return None
    except ProcessLookupError:
        return None
    return record


class RenderBusy(RuntimeError):
    """Another render job owns the machine; this one must not start."""


@contextmanager
def render_lock(purpose, wait=0., ignore=(), scan=None):
    """Own the machine's single render slot for the duration of the block."""
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+')
    deadline = time.monotonic()+max(wait, 0.)
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    other = holder(handle)
                    detail = f" held by pid {other['pid']} ({other.get('purpose')})" if other else ''
                    raise RenderBusy(f'another render job is running{detail}; '
                                     f'stop it (or the phone stream) before starting this one')
                time.sleep(.25)
        if scan is None:
            scan = os.environ.get('ATELIER_RENDER_LOCK_SCAN', '1') != '0'
        if scan:
            foreign = render_processes(ignore=ignore)
            if foreign:
                names = ', '.join(f"{p['pid']} {Path(p['command']).name}" for p in foreign)
                raise RenderBusy(f'render processes are already running and no harness owns them: {names}. '
                                 f'Stop them (the phone stream: `atelier stream stop`) first')
        handle.seek(0)
        handle.truncate()
        json.dump(dict(pid=os.getpid(), started=usage(os.getpid()).started, purpose=str(purpose),
                       checkout=str(Path.cwd()), time=time.time()), handle)
        handle.flush()
        yield path
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        handle.close()
