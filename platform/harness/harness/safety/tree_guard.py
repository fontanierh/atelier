"""An independent aggregate footprint guard for one owned compound job on macOS.

Start this monitor before launching any heavy children, then wait for its `running` receipt.
It adds the physical footprint of the pinned owner and its owned descendants, retaining
ownership when an intermediate exits. Shared engine services and their children are excluded,
except exact invocation-owned private roots registered through a pre-exec gate.
Individual game guards and the outer render lock remain required.
"""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import select
import signal
import stat
import sys
import time

SHARED = frozenset({'zenserver', 'UnrealTraceServer'})


def adopt_reporters(launch_nonce):
    """macOS CrashReporter reconciliation; other kernels have no reporters to adopt."""
    if launch_nonce is None or sys.platform != 'darwin':
        return None
    from .mac_crash_reporters import Reporters
    return Reporters(launch_nonce)


class ExitWatches:
    """@cc [owner:fontanierh,label:safety] aggregate-kernel-exit-evidence
    The aggregate monitor MUST bind each discovered descendant's kernel NOTE_EXIT watch only while
    its exact start matches before and after registration, beside the positive parent edge it was
    discovered through. Only a fired watch MAY be published as an exit; missing processes, failed or
    raced registration and PID reuse MUST stay unknown. Fired events are drained before any new
    registration, so a reused PID never inherits an earlier identity's watch or exit.
    """
    WINDOW = 64  # Bounded within MAX_FRAME; older exits are counted as omitted, never published as proof.

    def __init__(self, started):
        self.started = started
        self.queue = select.kqueue() if sys.platform == 'darwin' else None
        self.watched, self.fired, self.total = {}, deque(maxlen=self.WINDOW), 0

    def drain(self):
        while self.queue is not None:
            events = self.queue.control(None, 64, 0)
            for event in events:
                entry = self.watched.pop(event.ident, None)
                if (entry is not None and event.fflags & select.KQ_NOTE_EXIT
                        and not event.flags & select.KQ_EV_ERROR):
                    self.fired.append(entry)  # The immutable identity and edge bound with the watch.
                    self.total += 1
            if len(events) < 64:
                return

    def bind(self, pin, parent):
        if self.queue is None or parent is None:
            return
        if pin[0] in self.watched and self.watched[pin[0]][0] != pin:
            self.drain()
            self.watched.pop(pin[0], None)  # An unretrieved earlier identity stays unknown.
        if pin[0] in self.watched:
            return
        try:
            if self.started(pin[0]) != pin[1]:
                return
            self.queue.control([select.kevent(pin[0], filter=select.KQ_FILTER_PROC,
                                              flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
                                              fflags=select.KQ_NOTE_EXIT)], 0, 0)
        except OSError:
            return
        if self.started(pin[0]) != pin[1]:
            try:
                self.queue.control([select.kevent(pin[0], filter=select.KQ_FILTER_PROC,
                                                  flags=select.KQ_EV_DELETE)], 0, 0)
            except OSError:
                pass
            return
        self.watched[pin[0]] = (pin, parent)

    def evidence(self):
        """The newest fired exits as [pid, start, parent pid, parent start], and how many older ones are omitted."""
        self.drain()
        return [[*pin, *parent] for pin, parent in self.fired], self.total - len(self.fired)

    def close(self):
        if self.queue is not None:
            self.queue.close()
            self.queue = None


class OwnedTree:
    def __init__(self, api, pid, started, reporters=None, exits=None):
        self.api = api
        self.root = (pid, started)
        self.parents = {self.root: None}
        self.depth = {self.root: 0}
        self.shared = set()
        self.reporters = reporters
        self.exits = exits
        from .owned_service import Registrations
        self.services = Registrations(api, self.root)

    def register_service(self, key):
        self.discover()
        self.services.register(key, self.excluded())

    def shared_service(self, key):
        return self.api.name(key[0]) in SHARED and not self.services.includes(key)

    def same(self, key):
        return self.api.started(key[0]) == key[1]

    def excluded(self):
        for key in self.parents:
            if self.same(key) and self.shared_service(key):
                self.shared.add(key)
        result = set(self.shared)
        for key in self.parents:
            ancestor, visited = key, set()
            while ancestor is not None and ancestor not in visited:
                if ancestor in self.shared:
                    result.add(key)
                    break
                visited.add(ancestor)
                ancestor = self.parents.get(ancestor)
        return result

    def discover(self):
        if self.exits is not None:
            self.exits.drain()
        excluded = self.excluded()
        pending = [key for key in self.parents if key not in excluded and self.same(key)]
        seen = set()
        while pending:
            parent = pending.pop()
            if parent in seen:
                continue
            seen.add(parent)
            if self.shared_service(parent):
                self.shared.add(parent)
                continue
            for child in self.api.owned_children(*parent):
                if child not in self.parents:
                    self.parents[child] = parent
                    self.depth[child] = self.depth[parent] + 1
                    if self.exits is not None:
                        self.exits.bind(child, parent)
                if child not in excluded:
                    pending.append(child)
        if self.reporters is not None and self.reporters.observe(self, seen):
            self.reporters.reconcile(self)

    def sample(self):
        self.discover()
        from .owned_service import unsupported
        if unsupported(self.shared, self.parents, self.services):
            raise RuntimeError('unsupported unregistered shared service below private service')
        excluded = self.excluded()
        samples = []
        for key in self.parents:
            if key in excluded:
                continue
            try:
                value = self.api.usage(key[0])
            except ProcessLookupError:
                continue
            if value.started == key[1] and not value.exited:
                sample = dict(pid=key[0], started=key[1], footprint_bytes=value.footprint,
                              name=self.api.name(key[0]), depth=self.depth[key])
                if self.exits is not None:
                    parent = self.parents[key]
                    sample['parent'] = list(parent) if parent is not None else None
                samples.append(sample)
        return samples

    def stop_owned(self, send=os.kill, exclude_pid=None):
        if self.reporters is not None:
            self.reporters.reconcile(self)
        # Recheck service names and pinned identities immediately before each signal. An
        # already-recorded shell may have exec'd a shared service since the last sample.
        for key in sorted(self.parents, key=self.depth.get, reverse=True):
            # Retain historical ancestry, but do not rescan it for every departed compiler.
            if key[0] == exclude_pid or not self.same(key):
                continue
            if key in self.excluded() or not self.same(key):
                continue
            if self.reporters is not None and not self.reporters.signal_allowed(key):
                continue
            try:
                send(key[0], signal.SIGKILL)
            except ProcessLookupError:
                pass


def write_report(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def drain_owned(tree, timeout=2., exclude_pid=None):
    """Observe the retained pinned tree exit, including children found during cleanup."""
    deadline = time.monotonic() + timeout
    empty_samples = 0
    while True:
        try:
            # Remember native identities before stopping their ancestors. Reconcile
            # again after exit, including reporters spawned during the first stop.
            observed = True
            try:
                tree.sample()
            except (OSError, RuntimeError):
                observed = False  # Still try to stop previously pinned processes.
            if exclude_pid is None:
                tree.stop_owned()
            else:
                tree.stop_owned(exclude_pid=exclude_pid)
            remaining = [row for row in tree.sample() if row['pid'] != exclude_pid]
            empty = observed and not remaining and (tree.reporters is None or tree.reporters.empty())
            empty_samples = empty_samples + 1 if empty else 0
            if empty_samples >= 2:
                return True
        except (OSError, RuntimeError):
            # Telemetry loss cannot certify emptiness. Retry the existing pinned
            # cleanup within the same bound; never infer ownership from a failed read.
            empty_samples = 0
        if time.monotonic() >= deadline:
            return False
        time.sleep(.02)



def controller_live(pin):
    from atelier.harness.safety import process_tree
    try:
        sample = process_tree.usage(pin[0])
        return sample.started == pin[1] and not sample.exited
    except ProcessLookupError:
        return False  # Losing controller observation stops only this guard's owned workload.

def custody_descriptors(values):
    """Validate checkout-lock custody descriptors before any worker is released.

    Each must be a distinct int of at least 3 naming an open regular file. The descriptors keep
    their open file description (BSD flock exclusion); nothing here unlocks them.
    Returns (descriptor, (device, inode)) pairs.
    """
    seen, found = set(), []
    for fd in values:
        if type(fd) is not int or fd < 3 or fd in seen:
            raise ValueError(f'invalid custody descriptor {fd!r}')
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f'custody descriptor {fd} is not a regular lock file')
        seen.add(fd)
        found.append((fd, (info.st_dev, info.st_ino)))
    return found


CUSTODY_PAUSE_SECONDS = (.25, 5.)  # first and longest pause between custody observations
CUSTODY_REFRESH_SECONDS = 15.  # an unchanged hold rewrites its receipt at most this often


def _quietly(action, fallback=None):
    """Run a diagnostic or bookkeeping step; on a custody path nothing may unwind the holder."""
    try:
        return action()
    except BaseException:
        return fallback


def _text(value):
    """A bounded description that never raises, whatever repr or str do."""
    def describe():
        text = repr(value) if isinstance(value, BaseException) else str(value)
        return str.__str__(text)[:500]
    return _quietly(describe) or _quietly(lambda: '<unprintable ' + type(value).__name__ + '>') or '<unprintable>'


def _log(message):
    _quietly(lambda: print(message, file=sys.stderr, flush=True))


def _write_quietly(report, value):
    """Publish the receipt if possible. A failed report, serialisation or log never releases custody."""
    try:
        write_report(report, value)
        return True
    except BaseException as error:
        _log('custody receipt not written: ' + _text(error))
        return False


def _custody_pause(seconds):
    time.sleep(seconds)


def _close_custody(custody):
    for fd, _ in custody:
        _quietly(lambda: os.close(fd))


def _monitor_identity():
    from atelier.harness.safety import process_tree
    return [os.getpid(), process_tree.started(os.getpid())]


def _identity(value):
    """A usable [pid, start] pair: two positive ints, never bools; otherwise None."""
    if (isinstance(value, list) and len(value) == 2
            and all(type(part) is int and part > 0 for part in value)):
        return list(value)
    return None


def pin_monitor():
    """@cc [owner:fontanierh,label:safety] tree-monitor-custody-identity
    A custody monitor MUST pin its own positive integer [pid, start] once, before its first
    readiness receipt, and MUST publish exactly that identity as top-level `monitor` in every
    receipt it writes (running, terminal, stop, exception fallback and the late-custody
    continuation), with `custody.monitor` agreeing wherever present. If it cannot pin a usable
    identity it MUST write no readiness receipt and keep the fail-closed custody hold. Monitors
    without custody MUST NOT publish the field. See tests/test_tree_guard_custody.py.

    Returns this custodian's own identity, to pin once before its first readiness receipt.
    """
    monitor = _identity(_monitor_identity())
    if monitor is None or monitor[0] != os.getpid():
        raise RuntimeError('cannot pin the custody monitor identity')
    return monitor


def _observation(remaining, quiet, drained):
    """What a refresh must publish promptly when it changes; footprints alone do not count."""
    pins = _quietly(lambda: sorted((p['pid'], p['started']) for p in remaining), None)
    return 'observed', _text(remaining if pins is None else pins), _text(quiet), _text(drained)


def keep_custody(tree, report, value, custody, code):
    """Close custody only after verified pinned cleanup; otherwise hold it in a continuation.

    The terminal outcome in `value` (state, termination_reason, cleanup_complete) is already
    final. Late cleanup is recorded separately as `late_cleanup_complete` and never changes it.
    Every report, log, repr and serialisation step here is best-effort: none can end the hold.
    """
    files = _quietly(lambda: [list(identity) for _, identity in custody], [])
    if _quietly(lambda: value.get('cleanup_complete') is True, False):
        _quietly(lambda: value.__setitem__('custody', dict(held=False, released='cleanup_complete', lock_files=files)))
        _write_quietly(report, value)
        _close_custody(custody)
        return code
    first, longest = CUSTODY_PAUSE_SECONDS
    # The identity pinned before readiness, so custody.monitor always agrees with it.
    monitor = (_quietly(lambda: _identity(value.get('monitor')))
               or _quietly(_monitor_identity) or [os.getpid(), None])
    reason = _text(_quietly(lambda: value.get('termination_reason') or value.get('state'), 'unknown'))
    record = dict(held=True, reason='owned cleanup unverified after ' + reason, lock_files=files,
                  monitor=monitor, since=time.time(), last_observation=None, last_error=None, remaining=None,
                  refreshed=time.time(), pause_seconds=first)
    _quietly(lambda: value.__setitem__('custody', record))
    published = time.monotonic() if _write_quietly(report, value) else None
    _log('custody held by monitor ' + _text(monitor) + ' for ' + _text(report) + ': ' + record['reason'])
    pause, previous = first, None
    while True:
        try:
            verified = False
            try:
                drained = drain_owned(tree)
                remaining = tree.sample()
                reporters = getattr(tree, 'reporters', None)
                quiet = reporters is None or reporters.empty()
                verified = bool(drained and not remaining and quiet)
                record.update(last_observation=time.time(), remaining=remaining, late_reporters_empty=quiet,
                              last_error=None)
                observation = _observation(remaining, quiet, drained)
            except BaseException as error:  # Retry; never unwind while custody is held.
                record['last_error'] = _text(error)
                observation = 'error', record['last_error']
            if verified:
                break
            if observation != previous:
                pause = first  # a change is published at once and watched closely again
            if observation != previous or published is None or time.monotonic() - published >= CUSTODY_REFRESH_SECONDS:
                record.update(refreshed=time.time(), pause_seconds=pause)
                published = time.monotonic() if _write_quietly(report, value) else None
            previous = observation
            _quietly(lambda: _custody_pause(pause))
            pause = min(pause * 2, longest)
        except BaseException:
            _quietly(lambda: _custody_pause(longest))  # even bookkeeping failure keeps holding
    _quietly(lambda: record.update(held=False, released='late_cleanup_complete', released_at=time.time()))
    _quietly(lambda: value.__setitem__('late_cleanup_complete', True))
    _write_quietly(report, value)
    _close_custody(custody)
    return code


def run_child(pid, started, report, duration=None, limit_gib=10., controller=None, launch_nonce=None,
              custody=(), service_control=None):
    """@cc [owner:fontanierh,label:safety] owned-child-aggregate-limit
    Every sampled owned process MUST contribute to the simultaneous footprint limit except shared
    engine services and their descendants, except explicitly gated invocation-owned service roots.
    Failure or launcher exit MUST stop the retained pinned
    tree, and successful terminal receipts MUST require observed tree exit. Cleanup that cannot
    complete within its bound MUST fail; PID reuse MUST NOT transfer ownership. A bound controller
    disappearing MUST stop the owned tree and publish controller_exited with post-drain cleanup,
    never successful completion. Independent guards MUST outlive the controller process group.
    That bounded terminal outcome is the job's result. An opt-in custody monitor MUST publish it
    unchanged, then MAY continue without a time bound, keeping its checkout custody descriptors
    until pinned cleanup, including late reporters, is verified on two empty samples. Timeouts,
    telemetry, receipt, log, repr or serialisation failures, TERM/HUP and controller loss MUST NOT
    release custody; the hold backs off to a bounded pause, refreshes its receipt on a throttle and
    publishes any change at once. Late cleanup MUST NOT change the recorded state, termination
    reason or exit status. SIGKILL or an OS crash of the monitor itself is outside this guarantee.
    """
    from atelier.harness.safety import process_tree
    adopted = adopt_reporters(launch_nonce)
    tree = OwnedTree(process_tree, pid, started, adopted)
    tree.exits = ExitWatches(process_tree.started)
    report = Path(report)
    began, peak = time.monotonic(), 0
    limit = int(limit_gib * 1024**3)
    terminated = []
    monitor = None
    if custody:
        # Installed before the first readiness receipt: TERM/HUP drain the owned tree and never
        # end a custodian. Default monitors keep their ordinary signal behaviour.
        def request_drain(number, frame):
            terminated.append(number)
        for number in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(number, request_drain)
    try:
        if adopted is not None:
            adopted.bind_root(pid, started)
        if not tree.same(tree.root):
            raise RuntimeError('The launcher is no longer the pinned owner')
        if custody:
            monitor = pin_monitor()  # before any readiness receipt; a failure is never ready
        service_invocation, registrations = None, set()
        if service_control is not None:
            from .owned_service import receive, token
            setup = receive(service_control)
            if set(setup) != {'invocation', 'owner'} or setup['owner'] != [pid, started]:
                raise RuntimeError('private service monitor invocation mismatch')
            service_invocation = token(setup['invocation'])
        while True:
            registration = None
            if service_control is not None:
                from .owned_service import pending, receive, identity, validate_request, MAX_SERVICES
                if pending(service_control):
                    registration = receive(service_control)
                    key = validate_request(registration, service_invocation)
                    if registration['token'] in registrations or len(registrations) >= MAX_SERVICES:
                        raise RuntimeError('duplicate or excessive private service registration')
                    registrations.add(registration['token'])
                    tree.register_service(key)
            samples = tree.sample()
            total = sum(p['footprint_bytes'] for p in samples)
            peak = max(peak, total)
            elapsed = time.monotonic() - began
            state = 'running'
            if total > limit:
                state = 'memory_limit'
            elif duration is not None and elapsed >= duration:
                state = 'test_duration'
            elif terminated:
                state = 'terminated'
            elif controller is not None and not controller_live(controller):
                state = 'controller_exited'
            elif not any((p['pid'], p['started']) == tree.root for p in samples):
                state = 'child_exited'
            value = dict(owner=pid, owner_started=started, time=time.time(), observed_monotonic=time.monotonic(),
                         elapsed_seconds=elapsed,
                         footprint_bytes=total, peak_bytes=peak, limit_bytes=limit,
                         state=state, processes=samples)
            if monitor is not None:
                value['monitor'] = list(monitor)
            if service_control is not None:
                value['owned_services'] = tree.services.evidence()
            if controller is not None:
                value['controller'] = list(controller)
            value['exits'], value['exits_omitted'] = tree.exits.evidence()
            if state != 'running':
                value['cleanup_complete'] = drain_owned(tree)
                # drain_owned may have ended helpers from the pre-cleanup sample. Publish
                # the observed post-drain tree, including any newly discovered survivor.
                remaining = tree.sample()
                remaining_total = sum(p['footprint_bytes'] for p in remaining)
                if state == 'child_exited':
                    value.update(processes=remaining, footprint_bytes=remaining_total)
                else:
                    # Keep the established offending sample for failure diagnostics.
                    value.update(cleanup_processes=remaining, cleanup_footprint_bytes=remaining_total)
                value['cleanup_complete'] = value['cleanup_complete'] and not remaining
                if adopted is not None:
                    value['cleanup_complete'] = value['cleanup_complete'] and adopted.empty()
                    value['late_reporters'] = adopted.evidence()
                value['peak_bytes'] = max(value['peak_bytes'], remaining_total)
                if not value['cleanup_complete']:
                    value['termination_reason'], value['state'] = state, 'cleanup_incomplete'
                    state = 'cleanup_incomplete'
                value['exits'], value['exits_omitted'] = tree.exits.evidence()  # with helpers the drain ended
                value['observed_monotonic'] = time.monotonic()
                value['time'] = time.time()
            write_report(report, value)
            if registration is not None:
                from .owned_service import send
                key = identity(registration['identity'])
                if state != 'running' or not any((p['pid'], p['started']) == key for p in samples):
                    raise RuntimeError('registered private service lost its live aggregate sample')
                tree.services.validate(key)
                send(service_control, dict(**registration, ready=True))
            if state != 'running':
                code = 0 if state == 'child_exited' else 1
                return keep_custody(tree, report, value, custody, code) if custody else code
            time.sleep(.25)
    except BaseException as error:
        lost_controller = False
        if service_control is not None and controller is not None:
            try:
                lost_controller = not controller_live(controller)
            except (OSError, RuntimeError):
                pass
        if not custody:
            cleaned = drain_owned(tree)
            if service_control is not None:
                # Control/registration errors must leave failure evidence rather
                # than a stale running receipt. Never infer an empty tree after
                # failed observation or erase an unsupported helper identity.
                from .owned_service import unsupported
                failed = dict(owner=pid, owner_started=started,
                              state='controller_exited' if lost_controller else 'private_service_error',
                              error_type=type(error).__name__, cleanup_complete=False,
                              owned_services=tree.services.evidence(),
                              unsupported_services=[list(key) for key in unsupported(
                                  tree.shared, tree.parents, tree.services)],
                              time=time.time(), observed_monotonic=time.monotonic(),
                              footprint_bytes=0, peak_bytes=peak, limit_bytes=limit, processes=[])
                def record_failure():
                    remaining = tree.sample()
                    failed.update(processes=remaining,
                                  footprint_bytes=sum(p['footprint_bytes'] for p in remaining),
                                  cleanup_complete=cleaned and not remaining)
                _quietly(record_failure)
                _quietly(lambda: write_report(report, failed))
            raise
        failed = dict(state='cleanup_incomplete',
                      termination_reason='controller_exited' if lost_controller else 'monitor_error',
                      cleanup_complete=False)
        if monitor is not None:
            failed['monitor'] = list(monitor)  # the pinned identity, on the fallback receipt too

        def describe():
            failed.update(owner=pid, owner_started=started, time=time.time(), observed_monotonic=time.monotonic(),
                          elapsed_seconds=time.monotonic() - began, footprint_bytes=0, peak_bytes=peak,
                          limit_bytes=limit, error=_text(error), processes=[])
            if controller is not None:
                failed['controller'] = list(controller)
            if service_control is not None:
                from .owned_service import unsupported
                failed['owned_services'] = tree.services.evidence()
                failed['unsupported_services'] = [list(key) for key in unsupported(
                    tree.shared, tree.parents, tree.services)]
        _quietly(describe)
        return keep_custody(tree, report, failed, custody, 1)


def run(pid, started, report, duration, stop_file, limit_gib=10., launch_nonce=None):
    from atelier.harness.safety import process_tree
    adopted = adopt_reporters(launch_nonce)
    tree = OwnedTree(process_tree, pid, started, adopted)
    report = Path(report)
    report.parent.mkdir(parents=True, exist_ok=True)
    began, peak = time.monotonic(), 0
    limit = int(limit_gib * 1024**3)
    try:
        if adopted is not None:
            adopted.bind_root(pid, started)
        if not tree.same(tree.root):
            raise RuntimeError('The compound job is no longer the pinned owner')
        while True:
            samples = tree.sample()
            total = sum(p['footprint_bytes'] for p in samples)
            peak = max(peak, total)
            elapsed = time.monotonic() - began
            state = 'running'
            if total > limit:
                state = 'memory_limit'
            elif elapsed > duration:
                state = 'test_duration'
            elif not tree.same(tree.root):
                state = 'owner_exited'
            elif Path(stop_file).exists():
                # The harness asks to stop only after all owned games and helpers have
                # exited. Keep protecting the job if a game tree remains alive.
                if adopted is not None:
                    adopted.reconcile(tree)
                    samples = tree.sample()
                    total = sum(p['footprint_bytes'] for p in samples)
                    peak = max(peak, total)
                state = 'complete' if all(p['pid'] in {pid, os.getpid()} for p in samples) else 'children_remain'
                if adopted is not None and not adopted.empty():
                    state = 'cleanup_incomplete'
            value = dict(owner=pid, owner_started=started, time=time.time(), elapsed_seconds=elapsed,
                         footprint_bytes=total, peak_bytes=peak, limit_bytes=limit,
                         state=state, processes=samples)
            if adopted is not None:
                value['late_reporters'] = adopted.evidence()
            if state == 'complete':
                write_report(report, value)
                return 0
            if state != 'running':
                value['cleanup_complete'] = drain_owned(tree, exclude_pid=os.getpid())
                remaining = [row for row in tree.sample() if row['pid'] != os.getpid()]
                value.update(cleanup_processes=remaining,
                             cleanup_footprint_bytes=sum(row['footprint_bytes'] for row in remaining))
                value['cleanup_complete'] = value['cleanup_complete'] and not remaining
                if adopted is not None:
                    value['cleanup_complete'] = value['cleanup_complete'] and adopted.empty()
                    value['late_reporters'] = adopted.evidence()
                if not value['cleanup_complete']:
                    value.update(state='cleanup_incomplete', termination_reason=state)
                write_report(report, value)
                return 1
            write_report(report, value)
            time.sleep(.25)
    except BaseException:
        # Losing telemetry must stop the owned job, even if Unreal or the harness stalls.
        drain_owned(tree, exclude_pid=os.getpid())
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid', type=int, required=True)
    parser.add_argument('--expected-start', type=int, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--stop-file', type=Path)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--controller-pid', type=int)
    parser.add_argument('--controller-start', type=int)
    parser.add_argument('--child', action='store_true', help='guard an owned launcher until it exits')
    parser.add_argument('--launch-context-fd', type=int, help='private inherited launch ownership context')
    parser.add_argument('--limit-gib', type=float, default=10.)
    parser.add_argument('--custody-fd', type=int, action='append', default=[],
                        help='checkout-lock descriptor this child monitor holds until verified cleanup')
    parser.add_argument('--service-control-fd', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    custody = ()
    if args.custody_fd:
        if not args.child:
            parser.error('custody descriptors are only valid with --child')
        try:
            custody = custody_descriptors(args.custody_fd)
        except (OSError, ValueError) as error:
            parser.error(f'invalid custody descriptor: {error}')
        for fd, _ in custody:
            os.set_inheritable(fd, False)
    nonce = None
    if args.launch_context_fd is not None:
        if args.launch_context_fd < 3:
            parser.error('private context requires a separate inherited descriptor')
        from .launch_ownership import read_private_pipe
        nonce = read_private_pipe(args.launch_context_fd)
    if (args.controller_pid is None) != (args.controller_start is None):
        parser.error('controller PID and start must be provided together')
    if args.controller_pid is not None and (not args.child or args.controller_pid <= 0 or args.controller_start <= 0):
        parser.error('a positive controller identity is only valid with --child')
    if args.child:
        if args.stop_file is not None:
            parser.error('--child does not use --stop-file')
        service_control = None
        if args.service_control_fd is not None:
            import socket
            if args.service_control_fd < 3:
                parser.error('private service control requires a separate inherited socket')
            service_control = socket.socket(fileno=args.service_control_fd)
            service_control.settimeout(.25)
            os.set_inheritable(args.service_control_fd, False)
        return run_child(args.pid, args.expected_start, args.report, args.duration, args.limit_gib,
                         None if args.controller_pid is None else (args.controller_pid, args.controller_start), nonce,
                         custody=custody, service_control=service_control)
    if args.service_control_fd is not None:
        parser.error('private services require the normal child aggregate lifecycle')
    if args.stop_file is None or args.duration is None or args.limit_gib != 10.:
        parser.error('compound guards require --stop-file and --duration, with the fixed 10 GiB ceiling')
    # There is deliberately no CLI switch to raise this compound job's 10 GiB ceiling.
    return run(args.pid, args.expected_start, args.report, args.duration, args.stop_file, launch_nonce=nonce)


if __name__ == '__main__':
    raise SystemExit(main())
