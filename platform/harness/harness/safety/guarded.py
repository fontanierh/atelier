"""Run one heavy child (Unreal, a Blender render) under the machine's render lock and the independent memory guard.

    python -m atelier.harness.safety.guarded --report DIR [--timeout SECONDS] [--purpose TEXT] [--no-lock]
                                     [--small GIB] [--kind job|game|compile] -- COMMAND ...

Two protections, because they do different jobs:

* `render_lock` gives this process a render slot, so a second harness in another checkout is refused instead of
  launching alongside. A per-process memory ceiling cannot stop two Unreals from exhausting shared memory between them.
  The big slot is the machine's only one unless two are switched on (see `render_lock`); `small_gib` (`--small`), the
  job's expected peak, lets a small job use the second, small slot beside a big one.
* `memory_guard` runs as a sibling watching this exact child, pinned to its pid and start time, at `limit_gib`
  (10 GiB by default, up to 24 for `atelier play --memory-gib`), or 4 GiB in the small slot.

Ownership is registered the instant the child exists, so every later failure still reaps it: the monitor failing to
start, an exception, Ctrl-C, or the deadline. `timeout=0` means no deadline (interactive play); the ceiling is never
lifted either way.

A launcher whose heavy work runs in descendants (UAT's BuildCookRun starts the cook as UnrealEditor-Cmd, and
compilers) passes `watch`: every descendant is recorded by pid and start time as it appears, and those whose executable
name is in `watch` get their own memory guard (`memory-health-<name>-<pid>.json`) under the same ceiling and the same
outer slot turn. When the run ends, for any reason, recorded descendants still running as the same processes are stopped,
deepest first, before the child itself. Shared engine services and their children are excluded, except exact owned
private roots registered before exec through the explicit owned_services protocol. Nothing outside the recorded
tree is signalled. `progress` prints a line that often while the child is quiet.

Compile-kind launchers additionally wait behind a private exec gate until a sibling aggregate guard is ready.
It samples the simultaneous physical footprint of the wrapper and its owned descendants every quarter second,
excluding shared services, under the same ceiling and admission. `memory-health-tree.json` is this aggregate
receipt, separate from per-process reports. Lost telemetry or a missing successful terminal receipt fails the run.
"""
import argparse, hashlib, json, math, os, shutil, signal, subprocess, sys, time, uuid
from contextlib import ExitStack
from pathlib import Path

from atelier.harness.safety.guard import attach as attach_memory_guard, attach_tree, reap, wait_ready
from atelier.harness.safety import process_tree
from atelier.harness.safety.render_lock import KINDS, SMALL_LIMIT_GIB, render_lock
from atelier.harness.safety.process import spawn


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
        self.service_reports = {}
        from .owned_service import Registrations
        self.services = Registrations(process_tree, self.root)

    def register_service(self, key):
        self.poll(attach_guards=False)
        self.services.register(key, self.shared_now())

    def shared_service(self, key):
        return process_tree.name(key[0]) in SHARED_SERVICES and not self.services.includes(key)

    def same(self, key):
        return process_tree.started(key[0]) == key[1]

    def poll(self, attach_guards=True):
        # Walk from the root and from every recorded process still alive: an intermediate that lost the root's
        # ancestry (its parent exited) can still start the cook.
        excluded = self.shared_now()
        queue = [(*self.root, 0)] + [(*key, depth) for key, depth in self.depth.items()
                                     if key not in excluded and self.same(key)]
        seen = set()
        while queue:
            parent, parent_start, depth = queue.pop()
            if (parent, parent_start) in seen:
                continue
            seen.add((parent, parent_start))
            if self.shared_service((parent, parent_start)):
                self.shared.add((parent, parent_start))
                continue
            for child, child_start in process_tree.owned_children(parent, parent_start):
                key = (child, child_start)
                self.depth.setdefault(key, depth+1)
                self.parent.setdefault(key, (parent, parent_start))
                if self.shared_service(key):
                    self.shared.add(key)
                if key not in self.shared:
                    queue.append((child, child_start, depth+1))
        excluded = self.shared_now(check_coverage=True)
        if not attach_guards:
            return
        for key in self.depth:
            if key in self.guarded or key in excluded or not self.same(key):
                continue
            label = process_tree.name(key[0])
            if self.shared_service(key):   # a child that exec'd a shared service after it was recorded
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
            if key in self.service_reports:
                from .guard import process_guard_record, process_guard_receipt
                record = process_guard_record(self.service_reports[key])
                if (not record or (record.get('pid'), record.get('process_start')) != key
                        or record.get('limit_bytes') != int(self.limit_gib * 1024**3)):
                    raise RuntimeError('private service memory guard lost its live receipt or terminal identity')
                if record.get('state') != 'running':
                    raise RuntimeError('private service memory guard stopped its child: ' + str(record.get('state')))
                if monitor.poll() not in (None, 0):
                    raise RuntimeError('private service memory guard failed')
                if self.same(key) and not process_guard_receipt(
                        key[0], key[1], self.service_reports[key], int(self.limit_gib * 1024**3)):
                    raise RuntimeError('private service memory guard lost its live receipt')

    def finish_services(self, timeout=3.):
        """@cc [owner:fontanierh,label:safety] private-service-terminal-stop-evidence
        Before success or a final callback, every private actual-child monitor MUST settle naturally
        and its identity-bound receipt MUST be checked, even after the child disappeared. Memory or
        duration stops, missing/changed evidence and monitor failure MUST NOT become clean completion.
        """
        deadline = time.monotonic() + timeout
        for key in self.service_reports:
            monitor = self.guarded[key][1]
            try:
                status = monitor.wait(timeout=max(0., deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise RuntimeError('private service memory guard did not settle naturally') from None
            if status != 0:
                raise RuntimeError('private service memory guard failed before completion')
        self.check()

    def shared_now(self, check_coverage=False):
        """Recorded processes at or under a shared service, judged on current names: a recorded `sh` may have exec'd
        zenserver since the last poll, and everything under it is then the service's too."""
        for key in self.depth:
            if key not in self.shared and self.same(key) and self.shared_service(key):
                self.shared.add(key)
        if check_coverage:
            from .owned_service import unsupported
            if unsupported(self.shared, self.parent, self.services):
                raise RuntimeError('unsupported unregistered shared service below private service')

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
        if self.same(key) and key not in self.shared_now() and not self.shared_service(key) and self.same(key):
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


def check_aggregate_guard(child, monitor):
    """@cc [owner:fontanierh,label:safety] aggregate-terminal-wait-reconciliation
    A fresh identity-bound clean aggregate exit receipt MAY precede waitpid completion.
    Only that receipt and a nonfailed monitor permit a bounded wait for the owned child.
    A surviving child or an unexpected monitor death MUST still fail. The normal final
    aggregate finish and actual child return code MUST remain mandatory.
    """
    try:
        monitor.check()
    except RuntimeError:
        if child.poll() is not None:
            return  # The mandatory final finish below still judges the monitor's terminal result.
        if monitor.process.poll() not in (None, 0) or not monitor.receipt('child_exited'):
            raise
        try:
            child.wait(timeout=CHILD_EXIT_SECONDS)
        except subprocess.TimeoutExpired:
            raise RuntimeError('aggregate memory guard certified exit before a surviving launcher') from None


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


def settle_completion_guards(monitor, tree, timeout=3.):
    """Let every receipt writer finish naturally before retaining affirmative completion evidence."""
    deadline = time.monotonic() + timeout
    for process in [monitor, *(guard for _, guard in tree.guarded.values())]:
        try:
            code = process.wait(timeout=max(0., deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise RuntimeError('Completion process guards did not settle naturally') from None
        if code != 0:
            raise RuntimeError('Completion process guard failed; no completion proof')


def completion_watches(tree):
    """A disappeared watched child cannot erase its affirmative guard stop from recovery evidence."""
    records = []
    for (pid, started), (label, monitor) in tree.guarded.items():
        if monitor.poll() != 0:
            raise RuntimeError('Watched process guard failed; no completion proof')
        path = tree.folder / f'memory-health-{label}-{pid}.json'
        try:
            with path.open('rb') as stream:
                raw = stream.read(1024**2 + 1)
            if len(raw) > 1024**2:
                raise ValueError('oversized watched guard report')
            record = json.loads(raw)
        except FileNotFoundError:
            continue  # A short-lived child can exit before its first sample.
        if (record.get('pid'), record.get('process_start')) != (pid, started):
            continue
        if record.get('state') in ('memory_limit', 'test_duration'):
            raise RuntimeError('Watched process guard stopped its child; no completion proof')
        records.append(record)
    return records


def run(command, folder, timeout=0., purpose=None, lock=True, env=None, limit_gib=10., small_gib=None, kind='job',
        on_slot=None, watch=(), progress=0., track_tree=False, fitting_gib=None, pass_fds=(), aggregate_tree=False,
        on_poll=None, admission=None, performance=False, invocation_id=None, worker_binding=None,
        completion_path=None, compile_memory_gib=None, script_memory_gib=None, launch_context=None,
        queue_seconds=None, custody_fds=(), owned_services=False, logical_folder=None, job_gpu_gib=None):
    """@cc [owner:fontanierh,label:correctness] diagnostic-execution-timings
    Timing diagnostics MUST NOT certify outputs or guess command execution duration. Publication
    MUST require clearing the prior report; failure to clear MUST suppress publication without
    changing the guarded result. Reports MUST carry their invocation identity.

    Automatic full-capacity pressure no-GO responses MAY return to the same queue only after
    positive owned cleanup and uncharged close, under the original queue deadline when one was opted into.
    A queued job otherwise waits until admitted (queue_seconds, or ATELIER_CAPACITY_QUEUE_SECONDS, opts in).
    Selection-loss retries remain separately bounded; generic admission errors MUST NOT retry.
    Run one guarded child. The optional invocation_id is a UUID hex string. Admission time ends at GO acknowledgement
    (or spawn for an ungated child). Child lifetime includes gated startup. Execution duration
    stays unknown without an independently pinned gate-consumption event.

    An explicit job_gpu_gib MUST reach automatic full job admission unchanged, including
    internal no-GO requeues. It MUST NOT bypass locks or select explicit/legacy admission;
    only GPU reservation MAY increase, within the actual memory guard ceiling.
    A fixed provider MAY supply logical_folder to retain the existing stable task request
    identity while folder is a fresh report namespace. It MUST bind the original actual
    task/kind/checkout folder string; it MUST NOT supply a caller UUID, priority or ready time.
    The same logical_folder MUST reach every internal no-GO requeue unchanged. None retains
    the existing behavior. Actual reports MUST remain under folder, never logical_folder.
    """
    if job_gpu_gib is not None and (kind != 'job' or not lock or admission is not None
            or type(job_gpu_gib) not in (int, float) or not math.isfinite(job_gpu_gib)
            or not 0 < job_gpu_gib <= limit_gib):
        raise ValueError('Job GPU selection requires automatic guarded job admission within its memory ceiling')
    entered = time.monotonic()
    if logical_folder is not None and (not isinstance(logical_folder, (str, Path)) or not str(logical_folder)
                                       or '\0' in str(logical_folder) or admission is not None):
        raise ValueError('logical_folder requires an original task folder and automatic admission')
    if type(owned_services) is not bool:
        raise ValueError('owned_services must be an explicit bool')
    if owned_services and not lock:
        raise ValueError('private services require ordinary guarded admission')
    if owned_services and (worker_binding is not None or completion_path is not None):
        raise ValueError('private services do not yet support worker binding or compile completion publication')
    if queue_seconds is None and os.environ.get('ATELIER_CAPACITY_QUEUE_SECONDS'):
        queue_seconds = float(os.environ['ATELIER_CAPACITY_QUEUE_SECONDS'])
    if queue_seconds is not None and not (math.isfinite(queue_seconds) and queue_seconds > 0):
        raise ValueError('queue_seconds must be a positive number of seconds')
    identifier = uuid.uuid4().hex if invocation_id is None else invocation_id
    if type(identifier) is not str or uuid.UUID(identifier).hex != identifier:
        raise ValueError('invocation_id must be a UUID hex string')
    from .launch_ownership import LaunchContext, prepare
    if launch_context is None:
        launch_context = prepare(env)
        env = dict(launch_context.environment)
    if not isinstance(launch_context, LaunchContext):
        raise ValueError('Invalid launch ownership context')
    if env is None:
        env = dict(launch_context.environment)
    # Freeze the caller's supplied mapping before claiming the exact context. A
    # concurrent caller mutation must not change the environment after validation.
    env = dict(env)
    launch_nonce = launch_context.claim(env)
    if completion_path is not None:
        completion_path = Path(completion_path)
        if kind != 'compile' or not lock or completion_path.exists() or completion_path.is_symlink():
            raise ValueError('Completion proof requires a new path and the normal aggregate compile lifecycle')
    report = Path(folder) / 'execution-timings.json'
    publish_timings = True
    try:
        report.unlink(missing_ok=True)
    except OSError:
        publish_timings = False  # A diagnostic path must not block an otherwise valid launch.
    events = {}
    try:
        from atelier.harness.safety import tree_observation
        observe_tree = tree_observation.clear(folder)
    except Exception:
        observe_tree = False
    completion = {} if completion_path is not None else None
    try:
        from atelier.harness.capacity_client import CapacityOfferLost, CapacityError
        previous = None
        attempt, selection_losses = 0, 0
        while True:
            try:
                from atelier.harness.safety.cancellation import termination_cleanup
                with termination_cleanup():
                    code = _run(command, folder, timeout, purpose, lock, env, limit_gib, small_gib, kind,
                                on_slot, watch, progress, track_tree, fitting_gib, pass_fds, aggregate_tree,
                                on_poll, admission, performance, worker_binding=worker_binding, _timings=events,
                                _launch_nonce=launch_nonce, custody_fds=custody_fds, _invocation=identifier,
                                **({'owned_services': True} if owned_services else {}),
                                _requeue=previous, _queue_deadline=None if queue_seconds is None else entered + queue_seconds,
                                **({'compile_memory_gib': compile_memory_gib} if compile_memory_gib is not None else {}),
                                **({'script_memory_gib': script_memory_gib} if script_memory_gib is not None else {}),
                                **({'job_gpu_gib': job_gpu_gib} if job_gpu_gib is not None else {}),
                                **({'logical_folder': logical_folder} if logical_folder is not None else {}),
                                **({'_completion': completion} if completion is not None else {}))
                break
            except CapacityOfferLost as error:
                # The typed broker denial is necessary but not sufficient: _run must also
                # have completed its actual child/tree cleanup and affirmative uncharged close.
                if admission is not None or error.cleanup is None:
                    raise
                attempt += 1
                selection_losses += error.reason != 'pressure-wait'
                archive = Path(folder) / ('lost-offer-' + identifier + '-' + str(attempt))
                archive.mkdir()
                for name in ('memory-health.json', 'memory-health-tree.json', 'stdout.log'):
                    shutil.copy2(Path(folder) / name, archive / name)
                (archive / 'no-go.json').write_text(json.dumps(error.cleanup, indent=2) + '\n')
                if selection_losses >= 3 or time.monotonic() >= entered + 1800.:
                    raise CapacityError('Capacity pre-GO requeue bound reached; no resources held') from error
                previous = error.session
                for name in ('spawned', 'exited', 'go'):
                    events.pop(name, None)
                print('Capacity ' + error.reason + ' before GO: owned gate child reaped, tree empty, '
                      'uncharged close confirmed; returning to the same queue', flush=True)
        # _run's ExitStack has now completed child cleanup, capacity close and monitor detach.
        # This affirmative receipt is deliberately independent from diagnostic timings.
        if completion is not None and code == 0:
            if not completion:
                raise RuntimeError('Guarded command lacks positive aggregate completion evidence')
            identity = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
            value = dict(schema=1, kind='guarded-success', invocation_id=identifier, returncode=0,
                         cleanup_and_capacity_close=True, command_sha256=identity(command),
                         environment_sha256=identity(dict(os.environ) if env is None else env), **completion)
            candidate = completion_path.with_name('.' + completion_path.name + '.' + identifier + '.tmp')
            fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream, allow_nan=False); stream.write('\n')
                stream.flush(); os.fsync(stream.fileno())
            os.link(candidate, completion_path)
            candidate.unlink()
            directory = os.open(completion_path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        if code == 0 and observe_tree:
            try:
                tree_observation.publish(folder, identifier, events.get('tree_observation'),
                                         events.get('command_sha256'), events.get('environment_sha256'))
            except Exception:
                pass  # Optional publication cannot turn a completed job into a failure.
        return code
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
        on_poll=None, admission=None, performance=False, *, worker_binding=None, _timings, _completion=None,
        _requeue=None, _queue_deadline=None, compile_memory_gib=None, script_memory_gib=None, _launch_nonce=None,
        custody_fds=(), _invocation=None, owned_services=False, logical_folder=None, job_gpu_gib=None):
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
    Shared admission MUST verify the durable boot-bound compatibility barrier. Broker failures MUST fail
    without falling back to slots. Only an automatic full session's typed, fenced selection-change or pressure-wait
    no-GO denial MAY requeue after its exact child is positively reaped, its aggregate tree is
    affirmatively empty and its close confirms an uncharged waiting state. All process guards MUST
    settle naturally and their final bound receipts MUST exclude memory/duration stops before retry.
    Requeues MUST retain
    request/configuration and broker epoch/boot within the original 1800-second admission
    deadline. Selection changes MUST use at most two retries; pressure waits MAY retry only
    until that same original deadline, and MUST NOT repeat useful execution or certify success.
    Capacity cleanup MUST follow owned-child cleanup/reap and precede guard detachment.
    Requested performance exclusion MUST reach the configured broker or already belong to an explicit session.
    Explicit cook ceilings MUST retain automatic full compile admission and forward the same selected
    ceiling to its reservation, child guards and aggregate guard; other compile requests MUST not resize.
    Optional completion evidence MUST contain the positively waited launcher and matching terminal
    aggregate receipt. Its caller MUST publish it only after successful cleanup and capacity close.
    A typed broker completion observation MUST NOT grant continued execution. The actual bound
    launcher MUST exit within two seconds, both final guards MUST pass, a terminal capacity
    observation MUST be established, and normal affirmative capacity close MUST still succeed.
    Only automatic full sessions MAY select the existing measured-small 4 GiB envelope. Both
    process and aggregate guards MUST use that actual ceiling and the matching reservation.
    Explicit sessions MUST retain and cover the caller's actual requested ceiling.
    An opted-in legacy worker binding MUST publish only after both guards are ready and actual GO,
    and MUST transfer only the existing held lock context without another admission lock or monitor.
    Checkout custody descriptors MUST be validated before admission, require the aggregate monitor,
    and MUST reach only that monitor, never the guarded child; the default is none.

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
        from atelier.harness.safety.worker_binding import WorkerBinding, require_legacy
        if (type(worker_binding) is not WorkerBinding or not lock or not aggregate_tree or kind != 'job'
                or admission is not None or small_gib is not None or fitting_gib is not None):
            raise ValueError('Worker binding requires the normal legacy aggregate job lifecycle')
        require_legacy()
    if type(performance) is not bool:
        raise ValueError('performance request must be a boolean')
    if performance and admission is not None and getattr(admission, 'request', {}).get('performance') is not True:
        raise ValueError('explicit capacity admission must request performance exclusion')
    automatic = admission is None
    custody_fds = tuple(custody_fds)
    if custody_fds:
        # Before any admission session: invalid or child-bound custody never queues.
        from atelier.harness.safety.tree_guard import custody_descriptors
        custody_descriptors(custody_fds)
        if set(custody_fds) & set(pass_fds):
            raise ValueError('checkout custody descriptors never reach the guarded child')
    if job_gpu_gib is not None and (admission is not None or not lock or kind != 'job'):
        raise ValueError('Job GPU selection requires automatic guarded job admission')
    if script_memory_gib is not None and admission is not None:
        raise ValueError('Script ceiling selection requires an automatic full session')
    if compile_memory_gib is not None and admission is not None:
        raise ValueError('Cook ceiling selection requires an automatic full compile session')
    if admission is None:
        from atelier.harness.capacity_runtime import configured_session
        admission = configured_session(kind=kind, limit_gib=limit_gib, timeout=timeout, folder=folder,
                                       purpose=purpose or (Path(command[0]).name if command else kind),
                                       performance=performance, command=command, small_gib=small_gib,
                                       **({'compile_memory_gib': compile_memory_gib} if compile_memory_gib is not None else {}),
                                       **({'script_memory_gib': script_memory_gib} if script_memory_gib is not None else {}),
                                       **({'job_gpu_gib': job_gpu_gib} if job_gpu_gib is not None else {}),
                                       **({'logical_folder': logical_folder} if logical_folder is not None else {}))
        if admission is not None and getattr(admission, 'mode', None) == 'capacity':
            selected = getattr(admission, 'guard_limit_gib', None)
            if selected is not None:
                if type(selected) not in (int, float) or selected not in (limit_gib, min(limit_gib, SMALL_LIMIT_GIB)):
                    raise ValueError('Configured guard ceiling must retain the nominal or established SMALL envelope')
                limit_gib = selected
    if job_gpu_gib is not None and getattr(admission, 'mode', None) != 'capacity':
        raise ValueError('Job GPU selection requires full-capacity admission')
    if script_memory_gib is not None and getattr(admission, 'mode', None) != 'capacity':
        raise ValueError('Script ceiling selection requires full-capacity admission')
    if compile_memory_gib is not None and getattr(admission, 'mode', None) != 'capacity':
        raise ValueError('Cook ceiling selection requires full-capacity admission')
    if _requeue is not None:
        if not automatic or admission is None or admission.mode != 'capacity':
            raise ValueError('Capacity requeue requires an automatic full session')
        admission.requeue_after(_requeue)
    if admission is not None and (not lock or fitting_gib is not None):
        raise ValueError('capacity admission requires the legacy bridge or sealed shared mutexes, without a fitting-lane request')
    if admission is not None and getattr(admission, 'mode', None) in ('capacity', 'sealed-maintenance'):
        from atelier.harness.capacity_runtime import validate_session_profile
        validate_session_profile(admission, kind=kind, command=command, limit_gib=limit_gib)
    aggregate_tree = aggregate_tree or kind == 'compile' or admission is not None or owned_services
    if owned_services and not lock:
        raise ValueError('private services require ordinary guarded admission')
    if custody_fds and not aggregate_tree:
        raise ValueError('checkout custody requires the aggregate tree monitor')
    if fitting_gib is not None:
        if (not lock or kind != 'job' or not command or Path(command[0]).name.lower() != 'blender'
                or not any(arg in ('-b', '--background') for arg in command[1:]) or watch or track_tree or aggregate_tree):
            raise ValueError('the fitting slot requires one background Blender child under its normal lock and guard')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    _timings['ready'] = True
    horizon = timeout if timeout > 0 else None
    with ExitStack() as stack:
        child, root_start, tree, aggregate = None, None, None, None
        capacity_closed = False
        aggregate_settled = False
        lost_offer = None

        def finish_aggregate():
            nonlocal aggregate_settled
            if aggregate is not None and not aggregate_settled:
                # One existing bounded settlement, including when its result is a failure.
                aggregate_settled = True
                aggregate.finish()

        def retained():
            if tree is None:
                return ()
            excluded = tree.shared_now()
            return tuple(key for key in tree.depth if key not in excluded)

        def close_capacity():
            nonlocal capacity_closed
            if not capacity_closed:
                capacity_closed = True
                try:
                    # ExitStack has already unwound/reaped the owned workload here. On an
                    # exception, let the still-attached monitor publish its post-drain receipt
                    # before asking the broker to judge cleanup; never wait over a live root.
                    if child is not None and child.poll() is not None:
                        finish_aggregate()
                finally:
                    response = admission.close(child=child, child_start=root_start, descendants=retained())
                if (lost_offer is not None and automatic and admission.mode == 'capacity'
                        and lost_offer.session is admission and lost_offer.child == (child.pid, root_start)
                        and response.get('released') is True and response.get('state') == 'waiting'
                        and child.wait(timeout=0) is not None and aggregate is not None
                        and aggregate.receipt('child_exited') and monitor.poll() in (None, 0)):
                    # A memory/duration stop also exits its process monitor with status zero.
                    # Wait for all writers before inspecting the final bound stop receipts.
                    settle_completion_guards(monitor, tree)
                    check_root_guard(child, monitor, folder/'memory-health.json', final=True)
                    completion_watches(tree)
                    if not aggregate.receipt('child_exited'):
                        raise RuntimeError('Capacity requeue aggregate terminal became stale')
                    process_receipt = json.loads((folder/'memory-health.json').read_text())
                    if (process_receipt.get('pid'), process_receipt.get('process_start'),
                            process_receipt.get('limit_bytes'), process_receipt.get('state')) != (
                            child.pid, root_start, int(limit_gib * 1024**3), 'running'):
                        raise RuntimeError('Capacity requeue lacks the final bound process guard receipt')
                    observed = process_receipt.get('time')
                    if type(observed) not in (int, float) or not 0 <= time.time() - observed <= 5.:
                        raise RuntimeError('Capacity requeue process guard receipt became stale')
                    terminal = json.loads(aggregate.report.read_text())
                    if (terminal.get('owner'), terminal.get('owner_started'), terminal.get('state'),
                            terminal.get('cleanup_complete'), terminal.get('processes'), terminal.get('footprint_bytes')) == (
                            child.pid, root_start, 'child_exited', True, [], 0):
                        lost_offer.cleanup = dict(schema=1, reason=lost_offer.reason, no_go=True,
                            child=[child.pid, root_start], returncode=child.returncode,
                            epoch=admission.epoch, boot_id=admission.boot, uncharged_close=True,
                            terminal=terminal)

        if admission is not None:
            # Also cancel a queued offer when acquiring the bridge fails. The later callback
            # moves successful-spawn cleanup before monitor detachment; this fallback is a no-op.
            stack.callback(close_capacity)
            from atelier.harness.capacity_client import wait_for_offer
            remaining = None if _queue_deadline is None else _queue_deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                from atelier.harness.capacity_client import CapacityError
                raise CapacityError('Capacity admission deadline reached; no resources held')
            wait_for_offer(admission, seconds=remaining)  # Until admitted unless a deadline was opted into.
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
                if getattr(admission, 'mode', None) in ('capacity', 'sealed-maintenance'):
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
        service_controller = None
        if owned_services:
            from .owned_service import Controller, ENV_FD, ENV_TOKEN
            service_controller = Controller()
            stack.callback(service_controller.close)
            env = dict(os.environ if env is None else env)
            env[ENV_FD] = str(service_controller.driver.fileno())
            env[ENV_TOKEN] = service_controller.invocation
            descriptors += (service_controller.driver.fileno(),)
        gate = None
        try:
            from atelier.harness.safety import tree_observation
            _timings['command_sha256'] = tree_observation.identity(command)
            _timings['environment_sha256'] = tree_observation.identity(dict(os.environ) if env is None else env)
        except Exception:
            pass
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
        if service_controller is not None:
            service_controller.driver.close()
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
        if aggregate_tree:
            if monitor is None:
                raise RuntimeError('the gated launcher has no process memory guard')
            aggregate = monitors.enter_context(attach_tree(child.pid, folder/'memory-health-tree.json',
                                                           duration=horizon, limit_gib=limit_gib,
                                                           expected_start=root_start,
                                                           **({'owned_services': True} if owned_services else {}),
                                                           **({'launch_nonce': _launch_nonce} if _launch_nonce is not None else {}),
                                                           **({'custody_fds': custody_fds, 'invocation': _invocation}
                                                              if custody_fds else {})))
            aggregate.ready()
            if _completion is not None:
                monitor_pins = dict(process=[monitor.pid, process_tree.started(monitor.pid)],
                                    tree=[aggregate.process.pid, process_tree.started(aggregate.process.pid)])
                if any(type(start) is not int or start <= 0 for _, start in monitor_pins.values()):
                    raise RuntimeError('Could not pin completion monitors')
            if monitor.poll() is not None:
                raise RuntimeError('process memory guard exited before releasing the launcher')
            if admission is not None or worker_binding is not None or _completion is not None:
                limit_bytes = int(limit_gib * 1024**3)
                wait_ready(monitor, child.pid, root_start, folder/'memory-health.json', limit_bytes)
            if admission is not None:
                from atelier.harness.capacity_client import CapacityOfferLost
                try:
                    admission.start(child_pid=child.pid, child_start=root_start,
                                    process_guard=dict(pid=monitor.pid, start=process_tree.started(monitor.pid),
                                                       report=str((folder/'memory-health.json').resolve())),
                                    tree_guard=dict(pid=aggregate.process.pid,
                                                    start=process_tree.started(aggregate.process.pid),
                                                    report=str((folder/'memory-health-tree.json').resolve())),
                                    limit_bytes=limit_bytes)
                except CapacityOfferLost as error:
                    lost_offer = error
                    raise
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
        capacity_finishing = False
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
                check_aggregate_guard(child, aggregate)
            if deadline is not None and time.monotonic() > deadline:
                raise SystemExit(f'child exceeded {timeout} s')
            if admission is not None and child.poll() is None:
                response = admission.check(descendants=retained())
                if response.get('terminal') is True or response.get('finish_required') is True:
                    try:
                        child.wait(timeout=2.)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError('capacity completion observation preceded a surviving launcher') from None
                    capacity_finishing = True
                    break
            if on_poll is not None and child.poll() is None:
                on_poll(child.pid)
            if service_controller is not None and child.poll() is None:
                service_controller.poll(tree, aggregate, monitors, horizon, limit_gib)
            try:
                child.wait(timeout=.01 if fitting_gib is not None and not fitting_started else 1)
            except subprocess.TimeoutExpired:
                pass
        observed_exit()
        finish_aggregate()
        if capacity_finishing:
            try:
                status = monitor.wait(timeout=3.)
            except subprocess.TimeoutExpired:
                raise RuntimeError('process memory guard did not finish after capacity completion') from None
            if status != 0:
                raise RuntimeError('process memory guard failed after capacity completion')
        check_root_guard(child, monitor, folder/'memory-health.json', final=True)
        if service_controller is not None:
            tree.finish_services()
        if capacity_finishing:
            response = admission.check(descendants=retained())
            if response.get('terminal') is not True or response.get('admission') is not False:
                raise RuntimeError('capacity terminal completion was not affirmatively established')
        if on_poll is not None and child.returncode == 0:
            if tree is not None:
                tree.check()
            on_poll(child.pid)
        if _completion is not None and child.returncode == 0:
            if aggregate is None or child.wait(timeout=0) != 0 or not aggregate.receipt('child_exited'):
                raise RuntimeError('Completion proof lacks a positively waited guarded tree')
            settle_completion_guards(monitor, tree)
            terminal = json.loads(aggregate.report.read_text())
            if (terminal.get('owner'), terminal.get('owner_started'), terminal.get('state'), terminal.get('cleanup_complete')) != (
                    child.pid, root_start, 'child_exited', True):
                raise RuntimeError('Completion terminal identity changed')
            process_receipt = json.loads((folder / 'memory-health.json').read_text())
            if (process_receipt.get('pid'), process_receipt.get('process_start')) != (child.pid, root_start):
                raise RuntimeError('Completion process guard identity changed')
            if process_receipt.get('state') in ('memory_limit', 'test_duration'):
                raise RuntimeError('Completion process guard stopped the child; no completion proof')
            _completion.update(root=[child.pid, root_start], monitors=monitor_pins, terminal=terminal,
                               process_guard=process_receipt, watched=completion_watches(tree))
        if child.returncode == 0:
            try:
                from atelier.harness.safety import tree_observation
                _timings['tree_observation'] = tree_observation.capture(
                    aggregate, child, root_start, int(limit_gib * 1024**3), admission)
            except Exception:
                pass  # Optional history cannot affect the guarded result or cleanup.
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
    parser.add_argument('--queue-wait', type=float, default=None, metavar='SECONDS',
                        help='give up after waiting this long for capacity (default: wait until admitted)')
    parser.add_argument('--owned-services', action='store_true',
                        help='enable gated invocation-owned private service children in a compound driver')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command and args.command[0] == '--' else args.command
    if not command:
        raise SystemExit('nothing to run')
    return run(command, args.report, args.timeout, args.purpose, lock=not args.no_lock, small_gib=args.small,
               kind=args.kind, fitting_gib=args.fitting, queue_seconds=args.queue_wait,
               owned_services=args.owned_services)


if __name__ == '__main__':
    sys.exit(main())
