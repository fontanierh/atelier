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
signalled. The ceiling is `limit_gib`, 10 GiB by default.

An Unreal can leave SDK helpers running after it exits: a Turnkey `dotnet AutomationTool ... -command=VerifySdk`
outlived its game and held UnrealBuildTool's mutex, so the next game waited in `SDKSetup` until it was ended. The
monitor records the game's descendants while it runs, and once the game has gone `reap` (or the end of `attach`) ends
the recorded ones named in `HELPERS` that are still the same processes, still orphaned or under another of them. Nothing
is matched by name across the machine, and shared services the game starts (Zen, Trace) are not in `HELPERS`.
"""
import json, os, signal, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path

from .memory_guard import children, helpers_path, owned_children, usage

GUARD = Path(__file__).with_name('memory_guard.py')
HELPERS = ('dotnet', 'mono', 'bash', 'sh')   # UAT/Turnkey and UnrealBuildTool, and the scripts that start them
_owned = {}                                  # game pid -> (helper record, game start), from attach to reap_helpers


def _alive(pid, started):
    try:
        current = usage(pid)
    except ProcessLookupError:
        return False
    return current.started == started and not current.exited


def reap_helpers(pid, grace=3.):
    """End the SDK helpers the owned Unreal `pid` left behind, once it has exited. Returns what was ended."""
    if pid not in _owned:
        return []
    record_path, started = _owned[pid]
    if _alive(pid, started):
        return []
    del _owned[pid]
    try:
        record = json.loads(record_path.read_text())
    except (OSError, ValueError):
        return []
    if (record.get('game'), record.get('game_started')) != (pid, started):
        return []
    helpers = record['helpers']
    orphans = set(children(1))

    def ours(helper):
        if helper['name'] not in HELPERS or not _alive(helper['pid'], helper['started']):
            return False
        mine = (helper['pid'], helper['started'])
        return helper['pid'] in orphans or any(mine in owned_children(h['pid'], h['started']) for h in helpers
                                               if h is not helper)
    targets = sorted((h for h in helpers if ours(h)), key=lambda h: -h['depth'])
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, 1.)):
        for helper in targets:
            if _alive(helper['pid'], helper['started']):
                try:
                    os.kill(helper['pid'], sig)
                except ProcessLookupError:   # it exited since the check
                    pass
        deadline = time.monotonic()+wait
        while any(_alive(h['pid'], h['started']) for h in targets) and time.monotonic() < deadline:
            time.sleep(.05)
    ended = [dict(pid=h['pid'], name=h['name'], depth=h['depth']) for h in targets]
    if ended:
        record['reaped'] = ended
        record_path.write_text(json.dumps(record, indent=2)+'\n')
        print(f'ended {len(ended)} helper(s) left by Unreal {pid}: '
              + ', '.join(f'{h["pid"]} ({h["name"]})' for h in ended), flush=True)
    return ended


def _reap_helpers(pid):
    try:
        reap_helpers(pid)
    except Exception as error:   # cleanup must not hide the run's own outcome
        print(f'could not end the helpers left by Unreal {pid}: {error!r}', file=sys.stderr, flush=True)


def reap(child, grace=10.):
    """Never leave an owned Unreal behind: ask it to stop, then insist; then end the SDK helpers it left."""
    try:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    finally:
        _reap_helpers(child.pid)


@contextmanager
def attach(pid, report, duration, limit_gib=10., expected_start=None):
    """`duration=None` means no time limit: the ceiling still applies, nothing kills on the clock. `expected_start`
    carries an identity validated earlier: a different process now holding the pid gets no monitor (None)."""
    try:
        started = usage(pid).started
    except ProcessLookupError:
        yield None
        return
    if expected_start is not None and started != expected_start:
        yield None
        return
    _owned[pid] = (helpers_path(report), started)
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
        _reap_helpers(pid)   # a game still running is left to the harness's reap
