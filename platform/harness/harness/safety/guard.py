"""Attach the independent memory guard to a native Unreal child a harness already owns.

`atelier.harness.safety.guarded.run` owns the whole lifecycle. Harnesses that must keep their own launch, deadline,
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
import json, math, os, signal, subprocess, sys, time
from contextlib import contextmanager
from pathlib import Path

from atelier.harness.safety.memory_guard import children, helpers_path, owned_children, usage

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


def wait_ready(monitor, pid, started, report, limit_bytes, timeout=5.):
    """Require a fresh process-guard sample before releasing a capacity-gated child.

    This is evidence of guard health and its configured ceiling, not an exit witness or
    a claim that the process's descendants have all been discovered.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if monitor is None or monitor.poll() is not None:
            raise RuntimeError('process memory guard exited before becoming ready')
        try:
            with Path(report).open('rb') as handle:
                raw = handle.read(1024 * 1024 + 1)
            value = json.loads(raw) if len(raw) <= 1024 * 1024 else None
        except (OSError, ValueError):
            value = None
        if isinstance(value, dict):
            observed = value.get('time')
            fresh = (type(observed) in (int, float) and math.isfinite(observed)
                     and 0 <= time.time() - observed <= 5.)
            if (fresh and value.get('pid') == pid and value.get('process_start') == started
                    and value.get('limit_bytes') == limit_bytes and value.get('state') == 'running'):
                return
        time.sleep(.01)
    raise RuntimeError('process memory guard did not become ready')


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
    monitor = subprocess.Popen(command, start_new_session=True)
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


class TreeMonitor:
    """A sibling aggregate monitor whose receipts belong to this exact launcher."""
    def __init__(self, process, pid, started, report, service_control=None, service_invocation=None):
        self.process, self.pid, self.started, self.report = process, pid, started, Path(report)
        self.service_control = service_control
        self.service_invocation = service_invocation

    def register_service(self, key, token):
        from .owned_service import send, receive
        self.check()
        if self.service_control is None:
            raise RuntimeError('private service registration is disabled')
        request = dict(identity=list(key), token=token, invocation=self.service_invocation)
        send(self.service_control, request)
        if receive(self.service_control) != dict(**request, ready=True):
            raise RuntimeError('aggregate did not acknowledge private service identity')
        self.check()
        record = json.loads(self.report.read_text())
        if list(key) not in record.get('owned_services', []):
            raise RuntimeError('aggregate receipt lacks private service registration')

    def receipt(self, state):
        try:
            with self.report.open('rb') as handle:
                raw = handle.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                return False
            record = json.loads(raw)
        except (OSError, ValueError):
            return False
        if not isinstance(record, dict):
            return False
        observed = record.get('observed_monotonic')
        fresh = (type(observed) in (int, float) and math.isfinite(observed)
                 and 0 <= time.monotonic() - observed <= 5.)
        return (fresh and record.get('owner') == self.pid and record.get('owner_started') == self.started
                and record.get('state') == state
                and (state != 'child_exited' or record.get('cleanup_complete') is True))

    def ready(self, timeout=5.):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('aggregate memory guard exited before becoming ready')
            if self.receipt('running'):
                return
            time.sleep(.01)
        raise RuntimeError('aggregate memory guard did not become ready')

    def check(self):
        if self.process.poll() is not None:
            raise RuntimeError('aggregate memory guard exited before the launcher finished')
        if not self.receipt('running'):
            raise RuntimeError('aggregate memory guard lost its live receipt')

    def finish(self, timeout=5.):
        try:
            status = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError('aggregate memory guard did not finish') from None
        if status != 0 or not self.receipt('child_exited'):
            raise RuntimeError('aggregate memory guard did not certify launcher exit')


@contextmanager
def attach_tree(pid, report, duration, limit_gib=10., expected_start=None, launch_nonce=None, custody_fds=(),
                invocation=None, owned_services=False):
    """@cc [owner:fontanierh,label:safety] tree-monitor-custody-detach
    Checkout custody descriptors MUST be validated before the monitor starts and MUST reach only
    the monitor, as its own inherited duplicates; the caller keeps and closes its descriptors.
    With custody, no path MAY terminate or kill a still-running monitor, whatever its receipt
    says: it MUST be detached and logged with its pinned identity, report and lock-file identity.
    Without custody the existing bounded termination is unchanged. See tests/test_tree_guard_custody.py.

    Attach while the gated launcher waits. Call ready() after entering; reap its tree before leaving.
    Readiness is deliberately outside __enter__, so a readiness failure still leaves the monitor
    attached until the caller's owned-tree cleanup has run.
    """
    from atelier.harness.safety import process_tree
    from atelier.harness.safety.tree_guard import custody_descriptors
    custody = custody_descriptors(tuple(custody_fds))
    started = process_tree.started(pid)
    if started is None or (expected_start is not None and started != expected_start):
        raise RuntimeError('Cannot attach aggregate guard to the pinned launcher')
    report = Path(report)
    report.unlink(missing_ok=True)  # an earlier run is never a readiness receipt
    command = [sys.executable, '-m', 'atelier.harness.safety.tree_guard', '--child', '--pid', str(pid),
               '--expected-start', str(started), '--report', str(report), '--limit-gib', str(limit_gib),
               '--controller-pid', str(os.getpid()), '--controller-start', str(usage(os.getpid()).started)]
    if duration is not None:
        command += ['--duration', str(duration)]
    for fd, _ in custody:
        command += ['--custody-fd', str(fd)]
    kept = tuple(fd for fd, _ in custody)
    service_control = service_peer = None
    if owned_services:
        from .owned_service import channel
        import uuid
        service_control, service_peer = channel()
        service_invocation = uuid.uuid4().hex
        command += ['--service-control-fd', str(service_peer.fileno())]
        kept += (service_peer.fileno(),)
    else:
        service_invocation = None
    try:
        if launch_nonce is None:
            process = subprocess.Popen(command, start_new_session=True, **({'pass_fds': kept} if kept else {}))
        else:
            from .launch_ownership import private_pipe
            with private_pipe(launch_nonce) as descriptor:
                process = subprocess.Popen([*command, '--launch-context-fd', str(descriptor)],
                                           start_new_session=True, pass_fds=(*kept, descriptor))
    except BaseException:
        if service_control is not None:
            service_control.close()
        raise
    finally:
        if service_peer is not None:
            service_peer.close()
    monitor = TreeMonitor(process, pid, started, report, service_control, service_invocation)
    try:
        if service_control is not None:
            from .owned_service import send
            send(service_control, dict(invocation=service_invocation, owner=[pid, started]))
        yield monitor
    finally:
        try:
            if custody:
                # A custodian may hold checkout exclusion while cleanup is uncertain. Never end it.
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        monitor_start = process_tree.started(process.pid)
                    except Exception:
                        monitor_start = None
                    print(f'custody monitor retained: pid {process.pid} start {monitor_start} '
                          f'invocation {invocation} report {report} '
                          f'lock files {[list(identity) for _, identity in custody]}', flush=True)
            else:
                if process.poll() is None:
                    # The launcher has already been reaped by the caller. Let the monitor observe and
                    # drain its retained tree before detaching; its child-mode cleanup has a 2 s bound.
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        finally:
            if service_control is not None:
                service_control.close()
