"""Run one heavy child (Unreal, a Blender render) under the machine's render lock and the independent memory guard.

    python -m atelier.safety.guarded --report DIR [--timeout SECONDS] [--purpose TEXT] [--no-lock]
                                     [--small GIB] [--kind job|game|compile] -- COMMAND ...

Two protections, because they do different jobs:

* `render_lock` gives this process a render slot, so a second harness in another checkout is refused instead of
  launching alongside. A per-process memory ceiling cannot stop two Unreals from exhausting shared memory between them.
  The big slot is the machine's only one unless two are switched on (see `render_lock`); `small_gib` (`--small`), the
  job's expected peak, lets a small job use the second, small slot beside a big one.
* `memory_guard` runs as a sibling watching this exact child, pinned to its pid and start time, at `limit_gib`
  (10 GiB by default, up to 14 for `atelier play --memory-gib`), or 4 GiB in the small slot.

Ownership is registered the instant the child exists, so every later failure still reaps it: the monitor failing to
start, an exception, Ctrl-C, or the deadline. `timeout=0` means no deadline (interactive play); the ceiling is never
lifted either way.

A launcher whose heavy work runs in descendants (UAT's BuildCookRun starts the cook as UnrealEditor-Cmd, and
compilers) passes `watch`: every descendant is recorded by pid and start time as it appears, and those whose executable
name is in `watch` get their own memory guard (`memory-health-<name>-<pid>.json`) under the same ceiling and the same
outer slot turn. When the run ends, for any reason, recorded descendants still running as the same processes are stopped,
deepest first, before the child itself. Shared engine services a cook starts (Zen, Unreal Trace Server) and anything
under them are never signalled, nor is anything outside the recorded tree. `progress` prints a line that often while the child is quiet.

Compile-kind launchers additionally wait behind a private exec gate until a sibling aggregate guard is ready.
It samples the simultaneous physical footprint of the wrapper and its owned descendants every quarter second,
excluding shared services, under the same ceiling and admission. `memory-health-tree.json` is this aggregate
receipt, separate from per-process reports. Lost telemetry or a missing successful terminal receipt fails the run.
"""
import argparse, json, os, signal, subprocess, sys, time, uuid
from contextlib import ExitStack
from pathlib import Path

from .guard import attach as attach_memory_guard, attach_tree, reap, wait_ready
from . import process_tree
from .render_lock import KINDS, SMALL_LIMIT_GIB, render_lock
from .process import spawn


# Engine services a cook may start and other work then shares: recorded, never guarded or signalled.
SHARED_SERVICES = frozenset({'zenserver', 'UnrealTraceServer'})
FITTING_STARTUP_SECONDS = 2.
CHILD_EXIT_SECONDS = 2.


class Descendants:
    """The child's process tree as it grows. Records are keyed by (pid, start) and reached only through pinned parents;
    names are read again on every poll, so a child first seen as `sh` that execs the cook still gets its guard."""
    def __init__(self, root, root_start, folder, watch, duration, limit_gib, stack):
        self.root, self.folder, self.watch, self.duration, self.limit_gib, self.stack = (
            (root, root_start), folder, set(watch), duration, limit_gib, stack)
        self.depth, self.parent, self.guarded, self.shared = {}, {}, {}, set()

    def same(self, key):
        return process_tree.started(key[0]) == key[1]

    def poll(self, attach_guards=True):
        # Walk from the root and from every recorded process still alive: an intermediate that lost the root's
        # ancestry (its parent exited) can still start the cook.
        queue = [(*self.root, 0)] + [(*key, depth) for key, depth in self.depth.items()
                                     if key not in self.shared and self.same(key)]
        seen = set()
        while queue:
            parent, parent_start, depth = queue.pop()
            if (parent, parent_start) in seen:
                continue
            seen.add((parent, parent_start))
            for child, child_start in process_tree.owned_children(parent, parent_start):
                key = (child, child_start)
                self.depth.setdefault(key, depth+1)
                self.parent.setdefault(key, (parent, parent_start))
                if process_tree.name(child) in SHARED_SERVICES:
                    self.shared.add(key)
                if key not in self.shared:
                    queue.append((child, child_start, depth+1))
        if not attach_guards:
            return
        for key in self.depth:
            if key in self.guarded or key in self.shared or not self.same(key):
                continue
            label = process_tree.name(key[0])
            if label in SHARED_SERVICES:   # a child that exec'd a shared service after it was recorded
                self.shared.add(key)
                continue
            if label not in self.watch:
                continue
            report = self.folder/f'memory-health-{label}-{key[0]}.json'
            monitor = self.stack.enter_context(attach_memory_guard(
                key[0], report, duration=self.duration, limit_gib=self.limit_gib, expected_start=key[1]))
            if monitor is None:
                if self.same(key):
                    raise SystemExit(f'could not guard {label} {key[0]}')
                continue
            self.guarded[key] = (label, monitor)
            print(f'guarding {label} pid {key[0]}, report {report}', flush=True)

    def check(self):
        """A watched process must never outlive its guard."""
        for key, (label, monitor) in self.guarded.items():
            if monitor.poll() is not None and self.same(key):
                raise SystemExit(f'memory guard for {label} {key[0]} exited before it')

    def shared_now(self):
        """Recorded processes at or under a shared service, judged on current names: a recorded `sh` may have exec'd
        zenserver since the last poll, and everything under it is then the service's too."""
        for key in self.depth:
            if key not in self.shared and self.same(key) and process_tree.name(key[0]) in SHARED_SERVICES:
                self.shared.add(key)

        def under(key):
            seen = set()
            while key in self.parent and key not in seen:
                if key in self.shared:
                    return True
                seen.add(key)
                key = self.parent[key]
            return key in self.shared
        return {key for key in self.depth if under(key)}

    def unwind(self, grace=10.):
        """Stop recorded descendants that are still the same processes, deepest first, never a shared service or
        anything under one."""
        # Discover children born since the last host poll before stopping their parents. No new
        # monitors are attached during cleanup; the independent aggregate guard remains attached.
        try:
            self.poll(attach_guards=False)
        finally:
            self._unwind_recorded(grace)

    def _unwind_recorded(self, grace):
        excluded = self.shared_now()
        live = sorted((key for key in self.depth if key not in excluded), key=self.depth.get, reverse=True)
        for key in live:
            self.signal(key, signal.SIGTERM)
        deadline = time.monotonic()+grace
        while time.monotonic() < deadline and any(self.same(key) for key in live):
            time.sleep(.2)
        for key in live:
            self.signal(key, signal.SIGKILL)

    def signal(self, key, number):
        """Signal one recorded process only if its pinned identity still holds at this instant and it has not become a
        shared service."""
        if self.same(key) and process_tree.name(key[0]) not in SHARED_SERVICES:
            try:
                os.kill(key[0], number)
            except ProcessLookupError:
                pass


def last_line(path):
    try:
        with open(path, 'rb') as handle:
            handle.seek(max(0, os.path.getsize(path)-4096))
            lines = [line for line in handle.read().decode(errors='ignore').splitlines() if line.strip()]
        return lines[-1].strip()[:160] if lines else ''
    except OSError:
        return ''


def check_root_guard(child, monitor, report, final=False):
    """Reconcile a clean monitor exit with the owned child's status, without leaving a live child unguarded."""
    if monitor is None:
        return
    status = monitor.poll()
    if status not in (None, 0):
        suffix = ' before the final callback' if final else ''
        raise SystemExit(f'memory guard failed{suffix}')
    if status == 0 and child.poll() is None:
        # proc_pid_rusage can observe exit before waitpid does. Only a clean monitor exit
        # gets this bounded reconciliation; a surviving child still fails and is reaped.
        try:
            child.wait(timeout=CHILD_EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            raise SystemExit('memory guard exited before the child') from None
    if final or status == 0:
        try:
            record = json.loads(report.read_text())
        except FileNotFoundError:
            return  # A short-lived child may exit before the first sample.
        except (OSError, ValueError):
            raise SystemExit('memory guard report is unreadable') from None
        if not isinstance(record, dict):
            raise SystemExit('memory guard report is invalid')
        # Build report directories are reused. An old process's receipt says nothing
        # about a new child that exited before its first sample.
        if record.get('pid') == child.pid and record.get('state') in ('memory_limit', 'test_duration'):
            raise SystemExit(f'memory guard stopped the child: {record["state"]}')


def run(command, folder, timeout=0., purpose=None, lock=True, env=None, limit_gib=10., small_gib=None, kind='job',
        on_slot=None, watch=(), progress=0., track_tree=False, fitting_gib=None, pass_fds=(), aggregate_tree=False,
        on_poll=None, admission=None, performance=False, invocation_id=None, worker_binding=None):
    """@cc [owner:fontanierh,label:correctness] diagnostic-execution-timings
    Timing diagnostics MUST NOT certify outputs or guess command execution duration. Publication
    MUST require clearing the prior report; failure to clear MUST suppress publication without
    changing the guarded result. Reports MUST carry their invocation identity.

    Run one guarded child. The optional invocation_id is a UUID hex string. Admission time ends at GO acknowledgement
    (or spawn for an ungated child). Child lifetime includes gated startup. Execution duration
    stays unknown without an independently pinned gate-consumption event.
    """
    entered = time.monotonic()
    identifier = uuid.uuid4().hex if invocation_id is None else invocation_id
    if type(identifier) is not str or uuid.UUID(identifier).hex != identifier:
        raise ValueError('invocation_id must be a UUID hex string')
    report = Path(folder) / 'execution-timings.json'
    publish_timings = True
    try:
        report.unlink(missing_ok=True)
    except OSError:
        publish_timings = False  # A diagnostic path must not block an otherwise valid launch.
    events = {}
    try:
        return _run(command, folder, timeout, purpose, lock, env, limit_gib, small_gib, kind,
                    on_slot, watch, progress, track_tree, fitting_gib, pass_fds, aggregate_tree,
                    on_poll, admission, performance, worker_binding=worker_binding, _timings=events)
    finally:
        if publish_timings and events.get('ready'):
            def duration(start, end):
                return max(0., end - start) if start is not None and end is not None else None
            value = dict(schema=1, invocation_id=identifier,
                         admission_seconds=duration(entered, events.get('go')),
                         child_lifetime_seconds=duration(events.get('spawned'), events.get('exited')),
                         execution_seconds=None)
            temporary = report.with_name(report.name + '.' + identifier + '.tmp')
            try:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, 'w') as stream:
                    json.dump(value, stream, allow_nan=False)
                    stream.write('\n')
                temporary.replace(report)
            except OSError:
                pass  # Diagnostic failure cannot certify or change the guarded job's result.
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass


def _run(command, folder, timeout=0., purpose=None, lock=True, env=None, limit_gib=10., small_gib=None, kind='job',
        on_slot=None, watch=(), progress=0., track_tree=False, fitting_gib=None, pass_fds=(), aggregate_tree=False,
        on_poll=None, admission=None, performance=False, *, worker_binding=None, _timings):
    """@cc [owner:fontanierh,label:safety] compile-tree-monitor-lifecycle
    Aggregate mode MUST release the command only after a matching monitor readiness receipt, and MUST
    require a successful matching terminal receipt proving observed tree exit before returning success.
    Every exit path MUST perform owned descendant cleanup and launcher reap before detaching its monitors,
    retaining one normal admission. Cleanup that cannot observe tree exit within its bound MUST fail.
    Poll callbacks MUST follow root, watched-child and aggregate health checks. The final callback MUST
    require successful launcher exit and any aggregate terminal receipt before acknowledging results.
    A clean process-monitor exit MAY precede child reaping by at most two seconds; a surviving child,
    failed monitor or matching memory/duration stop receipt MUST fail, including without a callback.
    Capacity-managed work MUST hold either the exclusive migration bridge or all three sealed
    shared compatibility mutexes and await the broker's own exec gate after both guards are ready.
    Shared admission MUST verify the durable boot-bound compatibility barrier. Broker failure MUST fail the run, without falling back to
    slots. Capacity cleanup MUST follow owned-child cleanup/reap and precede guard detachment.
    Requested performance exclusion MUST reach the configured broker or already belong to an explicit session.
    An opted-in legacy worker binding MUST publish only after both guards are ready and actual GO,
    and MUST transfer only the existing held lock context without another admission lock or monitor.

    Run `command` to completion and return its exit status. `small_gib` and `kind` go to `render_lock`;
    `on_slot(slot, why)` hears which slot the child runs in. `track_tree` records descendants for cleanup
    when a compound worker attaches its own actual-child guards immediately at launch. `aggregate_tree`
    additionally gates execution on an independent aggregate footprint guard for the owned launcher tree.
    Compile-kind work always uses this aggregate protection, including UAT and tool bootstrap wrappers.
    `on_poll(pid)` observes the owned child between waits and once after successful exit. Exceptions
    unwind through the existing guard/child cleanup; the callback never replaces either protection.
    `admission` is an explicit capacity-client session. During migration it adds the broker gate and
    exclusive legacy bridge, retaining existing guards, resource policies and foreign-process checks.
    `performance` asks a configured broker to drain other grants before this run and exclude new ones.
    An explicit admission session must already carry that flag when performance exclusion is requested.
    """
    if worker_binding is not None:
        from .worker_binding import WorkerBinding, require_legacy
        if (type(worker_binding) is not WorkerBinding or not lock or not aggregate_tree or kind != 'job'
                or admission is not None or small_gib is not None or fitting_gib is not None):
            raise ValueError('Worker binding requires the normal legacy aggregate job lifecycle')
        require_legacy()
    if type(performance) is not bool:
        raise ValueError('performance request must be a boolean')
    if performance and admission is not None and getattr(admission, 'request', {}).get('performance') is not True:
        raise ValueError('explicit capacity admission must request performance exclusion')
    if admission is None:
        from ..capacity_runtime import configured_session
        admission = configured_session(kind=kind, limit_gib=limit_gib, timeout=timeout, folder=folder,
                                       purpose=purpose or (Path(command[0]).name if command else kind),
                                       performance=performance, command=command)
    if admission is not None and (not lock or fitting_gib is not None):
        raise ValueError('capacity admission requires the legacy bridge or sealed shared mutexes, without a fitting-lane request')
    if admission is not None and getattr(admission, 'mode', None) == 'capacity':
        from ..capacity_runtime import validate_session_profile
        validate_session_profile(admission, kind=kind, command=command, limit_gib=limit_gib)
    aggregate_tree = aggregate_tree or kind == 'compile' or admission is not None
    if fitting_gib is not None:
        if (not lock or kind != 'job' or not command or Path(command[0]).name.lower() != 'blender'
                or not any(arg in ('-b', '--background') for arg in command[1:]) or watch or track_tree or aggregate_tree):
            raise ValueError('the fitting slot requires one background Blender child under its normal lock and guard')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    _timings['ready'] = True
    horizon = timeout if timeout > 0 else None
    with ExitStack() as stack:
        child, root_start, tree = None, None, None
        capacity_closed = False

        def retained():
            if tree is None:
                return ()
            excluded = tree.shared_now()
            return tuple(key for key in tree.depth if key not in excluded)

        def close_capacity():
            nonlocal capacity_closed
            if not capacity_closed:
                capacity_closed = True
                admission.close(child=child, child_start=root_start, descendants=retained())

        if admission is not None:
            # Also cancel a queued offer when acquiring the bridge fails. The later callback
            # moves successful-spawn cleanup before monitor detachment; this fallback is a no-op.
            stack.callback(close_capacity)
            admission.offer()
        slot = None
        if lock:
            def taken(name, why):
                nonlocal slot
                slot = name
                if on_slot is not None:
                    on_slot(name, why)
            options = dict(small_gib=small_gib, kind=kind, on_slot=taken, fitting_gib=fitting_gib)
            if worker_binding is not None:
                options['worker_binding'] = worker_binding
            if admission is not None:
                options.update(small_gib=None)
                if getattr(admission, 'mode', None) == 'capacity':
                    options['capacity'] = admission
                else:
                    options['exclusive_bridge'] = True
            stack.enter_context(render_lock(purpose or Path(command[0]).name, **options))
        if slot in ('small', 'fitting'):
            limit_gib = min(limit_gib, SMALL_LIMIT_GIB)
        log = stack.enter_context((folder/'stdout.log').open('w'))
        # Register monitors first, so later child/tree cleanup runs before either monitor detaches,
        # including when monitor startup fails. The private pipe holds this same PID before exec.
        monitors = stack.enter_context(ExitStack())
        if admission is not None:
            stack.callback(close_capacity)
        descriptors = tuple(pass_fds)
        gate = None
        if aggregate_tree:
            if admission is not None:
                read_fd = admission.gate()
            else:
                read_fd, write_fd = os.pipe()
                gate = stack.enter_context(os.fdopen(write_fd, 'wb', buffering=0))
            gate_read = stack.enter_context(os.fdopen(read_fd, 'rb', buffering=0))
            descriptors += (read_fd,)
            command = [sys.executable, str(Path(__file__).with_name('exec_gate.py')), str(read_fd), *command]
        inherited = {'pass_fds': descriptors, 'stdin': subprocess.DEVNULL} if descriptors else {}
        child = spawn(command, kind=kind, stdout=log, stderr=subprocess.STDOUT, env=env, **inherited)
        _timings['spawned'] = time.monotonic()
        if not aggregate_tree:
            _timings['go'] = _timings['spawned']
        def observed_exit():
            if 'exited' not in _timings and child.poll() is not None:
                _timings['exited'] = time.monotonic()
        stack.callback(observed_exit)
        if aggregate_tree:
            gate_read.close()
        fitting_ready_by = time.monotonic()+FITTING_STARTUP_SECONDS
        fitting_started = False
        stack.callback(reap, child, grace=0. if aggregate_tree else 10.)
        where = f', {slot} render slot, {limit_gib:g} GiB limit' if slot in ('small', 'fitting') else ''
        print(f'pid {child.pid}, guard report {folder/"memory-health.json"}{where}', flush=True)
        root_start = process_tree.started(child.pid) if watch or track_tree or aggregate_tree else None
        if watch or track_tree or aggregate_tree:
            if type(root_start) is not int or root_start <= 0:
                raise RuntimeError('could not pin the owned launcher before attaching its tree guards')
            tree = Descendants(child.pid, root_start, folder, watch, horizon, limit_gib, monitors)
            # Runs before the child is reaped; after a success it only reaps leftovers such as shader workers.
            # A lost aggregate monitor cannot leave descendants allocating during a graceful
            # shutdown window. Ordinary single-process/watched runs retain their existing grace.
            stack.callback(tree.unwind, grace=0. if aggregate_tree else 10.)
        monitor = monitors.enter_context(attach_memory_guard(child.pid, folder/'memory-health.json',
                                                             duration=horizon, limit_gib=limit_gib))
        aggregate = None
        if aggregate_tree:
            if monitor is None:
                raise RuntimeError('the gated launcher has no process memory guard')
            aggregate = monitors.enter_context(attach_tree(child.pid, folder/'memory-health-tree.json',
                                                           duration=horizon, limit_gib=limit_gib,
                                                           expected_start=root_start))
            aggregate.ready()
            if monitor.poll() is not None:
                raise RuntimeError('process memory guard exited before releasing the launcher')
            if admission is not None or worker_binding is not None:
                limit_bytes = int(limit_gib * 1024**3)
                wait_ready(monitor, child.pid, root_start, folder/'memory-health.json', limit_bytes)
            if admission is not None:
                admission.start(child_pid=child.pid, child_start=root_start,
                                process_guard=dict(pid=monitor.pid, start=process_tree.started(monitor.pid),
                                                   report=str((folder/'memory-health.json').resolve())),
                                tree_guard=dict(pid=aggregate.process.pid,
                                                start=process_tree.started(aggregate.process.pid),
                                                report=str((folder/'memory-health-tree.json').resolve())),
                                limit_bytes=limit_bytes)
            else:
                gate.write(b'1')
                gate.close()
            _timings['go'] = time.monotonic()
            if worker_binding is not None:
                worker_binding.publish((child.pid, root_start),
                    dict(process_guard=dict(pid=monitor.pid, start=process_tree.started(monitor.pid),
                                            report=str((folder/'memory-health.json').resolve())),
                         tree_guard=dict(pid=aggregate.process.pid, start=process_tree.started(aggregate.process.pid),
                                         report=str((folder/'memory-health-tree.json').resolve()))), limit_bytes)
        started = time.monotonic()
        deadline = started+horizon if horizon else None
        spoken = started
        while child.poll() is None:
            if fitting_gib is not None:
                executable = process_tree.name(child.pid).lower()
                # It can finish between poll and proc_name; a completed child is not a foreign executable.
                if child.poll() is not None:
                    break
                if executable == 'blender':
                    fitting_started = True
                elif not fitting_started and executable in ('taskpolicy', 'nice', ''):
                    if time.monotonic() >= fitting_ready_by:
                        raise SystemExit('the fitting launcher did not reach Blender within its startup deadline')
                else:
                    raise SystemExit(f'the fitting child is not Blender: {executable!r}')
            if tree is not None:
                tree.poll()
                tree.check()
            if progress and time.monotonic()-spoken >= progress:
                spoken = time.monotonic()
                watched = ', '.join(f'{label} {key[0]}' for key, (label, _) in tree.guarded.items() if tree.same(key)) if tree else ''
                print(f'{(spoken-started)/60:.0f} min{f" [{watched}]" if watched else ""}: {last_line(folder/"stdout.log")}', flush=True)
            check_root_guard(child, monitor, folder/'memory-health.json')
            if aggregate is not None and child.poll() is None:
                try:
                    aggregate.check()
                except RuntimeError:
                    # The launcher may have exited between the loop condition and its monitor's
                    # final receipt. The mandatory finish check below judges that terminal result.
                    if child.poll() is None:
                        raise
            if deadline is not None and time.monotonic() > deadline:
                raise SystemExit(f'child exceeded {timeout} s')
            if admission is not None and child.poll() is None:
                admission.check(descendants=retained())
            if on_poll is not None and child.poll() is None:
                on_poll(child.pid)
            try:
                child.wait(timeout=.01 if fitting_gib is not None and not fitting_started else 1)
            except subprocess.TimeoutExpired:
                pass
        observed_exit()
        if aggregate is not None:
            aggregate.finish()
        check_root_guard(child, monitor, folder/'memory-health.json', final=True)
        if on_poll is not None and child.returncode == 0:
            if tree is not None:
                tree.check()
            on_poll(child.pid)
        return child.returncode or 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, help='directory for memory-health.json and stdout.log')
    parser.add_argument('--timeout', type=float, default=0, help='seconds before the child is stopped, 0 for none')
    parser.add_argument('--purpose', default=None, help='recorded in the lock file for a clearer refusal')
    parser.add_argument('--no-lock', action='store_true', help='skip the render lock (the memory guard stays)')
    parser.add_argument('--small', type=float, default=None, metavar='GIB',
                        help='expected peak in GiB: the job may use the small render slot (at most 3 GiB, 4 GiB limit)')
    parser.add_argument('--fitting', type=float, default=None, metavar='GIB',
                        help='reserved background Blender fitting slot only (at most 3 GiB, 4 GiB limit)')
    parser.add_argument('--kind', choices=KINDS, default='job', help='recorded in the lock file; games and compiles '
                        'always use the big slot, and a compile waits for a small job to finish')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == '--' else args.command
    if not command:
        raise SystemExit('nothing to run')
    return run(command, args.report, args.timeout, args.purpose, lock=not args.no_lock, small_gib=args.small,
               kind=args.kind, fitting_gib=args.fitting)


if __name__ == '__main__':
    sys.exit(main())
