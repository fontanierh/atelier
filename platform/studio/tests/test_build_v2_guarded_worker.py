"""The build-v2 guarded bridge reports guard facts honestly and passes descriptors narrowly.

The bridge runs in a subprocess with a fake `run` standing in for `guarded.run` (no admission is
requested). The worker is the disposable protocol fixture with one descendant.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from atelier.build_v2.guarded_worker import classify, cleanup, monitor_identity, tree_sample

ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / 'platform/build-v2/tests/fixtures/disposable_worker.py'
darwin = pytest.mark.skipif(sys.platform != 'darwin', reason='process identities use macOS libproc')

MONITOR = [999991, 4242]  # the fake guard's custody monitor identity (see FAKE_GUARD)

FAKE_GUARD = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
from atelier.harness.capacity_protocol import process_start

MONITOR = [999991, 4242]  # stands in for the custody monitor's own pinned identity

def run(command, folder, timeout=0., purpose=None, env=None, limit_gib=10., kind='job', on_slot=None,
        on_poll=None, pass_fds=(), queue_seconds=None, custody_fds=(), invocation_id=None, script_memory_gib=None, job_gpu_gib=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    scenario = os.environ['FAKE_GUARD']
    (folder / 'fake-call.json').write_text(json.dumps(dict(
        pass_fds=list(pass_fds), custody=[list(os.fstat(fd)[1:3][::-1]) for fd in custody_fds],
        kind=kind, limit_gib=limit_gib, timeout=timeout, queue_seconds=queue_seconds, script_memory_gib=script_memory_gib, job_gpu_gib=job_gpu_gib)))
    if scenario == 'gpu_probe':
        raise SystemExit(1)  # No process/admission: inspect only the actual bridge call.
    if scenario == 'queue':
        while True:
            time.sleep(.02)  # stands in for waiting on the broker; TERM unwinds it
    on_slot('capacity', 'fake admission')
    with (folder / 'stdout.log').open('w') as log:
        child = subprocess.Popen(command, env=env, pass_fds=pass_fds, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT)
    start = process_start(child.pid)
    state = 'memory_limit' if scenario == 'memory' else 'running'
    (folder / 'memory-health.json').write_text(json.dumps(dict(pid=child.pid, process_start=start, state=state,
                                                               time=time.time())))
    tree = dict(owner=child.pid, owner_started=start, state='child_exited', cleanup_complete=True,
                processes=[], footprint_bytes=0,
                late_reporters=dict(adopted=[], unresolved=[], unresolved_pids=[], scan_failed=False))
    files = [list(os.fstat(fd)[1:3][::-1]) for fd in custody_fds]
    if files:
        tree['custody'] = dict(held=False, released='cleanup_complete', lock_files=files)
    if scenario == 'unconfirmed':
        tree.update(state='cleanup_incomplete', termination_reason='child_exited', cleanup_complete=False)
    try:
        if files:
            # A custody monitor's readiness receipt names its controller (this bridge) and itself.
            running = dict(owner=child.pid, owner_started=start, state='running', time=time.time(),
                           controller=[os.getpid(), process_start(os.getpid())], monitor=list(MONITOR),
                           processes=[dict(pid=child.pid, started=start, name='python', depth=0, footprint_bytes=1)])
            if scenario == 'monitor_foreign':
                running['controller'] = [1, 1]
            (folder / 'memory-health-tree.json').write_text(json.dumps(running))
            on_poll(child.pid)
            if scenario in ('monitor_changed', 'monitor_missing'):
                running['time'] = time.time() + .001
                if scenario == 'monitor_changed':
                    running['monitor'] = [MONITOR[0], MONITOR[1] + 1]
                else:
                    del running['monitor']
                (folder / 'memory-health-tree.json').write_text(json.dumps(running))
                on_poll(child.pid)
            tree['monitor'] = list(MONITOR)
        if scenario == 'sampling':
            running = dict(owner=child.pid, owner_started=start, state='running', time=time.time(),
                           processes=[dict(pid=child.pid, started=start, name='python', depth=0, footprint_bytes=1)])
            (folder / 'memory-health-tree.json').write_text(json.dumps(running))
            on_poll(child.pid)
            on_poll(child.pid)  # the same receipt again: no second sample
            running.update(time=time.time() + .001, processes=running['processes'] + [dict(pid=1, started=7)])
            (folder / 'memory-health-tree.json').write_text(json.dumps(running))
        on_poll(child.pid)
        if scenario == 'memory':
            child.kill()
            child.wait()
            # A stop keeps the offending sample and publishes the post-drain one separately.
            tree.update(state='memory_limit', processes=[dict(pid=child.pid)], footprint_bytes=123,
                        cleanup_processes=[], cleanup_footprint_bytes=0)
            raise SystemExit('process memory guard stopped the child')
        code = child.wait()
        if scenario == 'capacity':
            raise RuntimeError('Capacity exit remains uncertain; reservation and named locks retained')
        return code
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
            tree.update(state='terminated', cleanup_processes=[], cleanup_footprint_bytes=0)
        tree['time'] = time.time()
        (folder / 'memory-health-tree.json').write_text(json.dumps(tree))
        (folder / 'execution-timings.json').write_text(json.dumps(dict(schema=1, invocation_id=invocation_id)))
'''


class Bridge:
    def __init__(self, tmp_path, scenario, custody=(), memory=1, program=None):
        self.skip_samples = bool(custody)  # a custody readiness receipt is also a sample
        (tmp_path / 'fakeguard.py').write_text(FAKE_GUARD)
        self.report = tmp_path / 'attempt-1'
        self.report.mkdir()
        request_r, self.request_w = os.pipe()
        self.response_r, response_w = os.pipe()
        events_r, events_w = os.pipe()
        liveness_r, self.liveness_w = os.pipe()
        spec_r, spec_w = os.pipe()
        self.fd_report = tmp_path / 'worker-fds.json'
        spec = dict(program=program or sys.executable, args=[str(WORKER), 'normal'],
                    env=dict(PATH=os.environ['PATH'], WORKER_FD_REPORT=str(self.fd_report)))
        os.write(spec_w, json.dumps(spec).encode())
        os.close(spec_w)
        inherited = [request_r, response_w, events_w, liveness_r, spec_r, *custody]
        argv = ['--report', str(self.report), '--purpose', 'bridge test', '--memory-gib', str(memory), '--timeout', '30',
                '--events-fd', str(events_w), '--liveness-fd', str(liveness_r), '--spec-fd', str(spec_r),
                '--request-fd', str(request_r), '--response-fd', str(response_w)]
        for fd in custody:
            argv += ['--custody-fd', str(fd)]
        code = ('import sys; sys.path.insert(0, sys.argv[1]); import fakeguard; '
                'from atelier.build_v2 import guarded_worker; sys.exit(guarded_worker.main(sys.argv[2:], run=fakeguard.run))')
        self.process = subprocess.Popen([sys.executable, '-c', code, str(tmp_path), *argv], pass_fds=inherited,
                                        env={**os.environ, 'FAKE_GUARD': scenario})
        for fd in (request_r, response_w, events_w, liveness_r, spec_r):
            os.close(fd)
        self.events = os.fdopen(events_r, 'r')

    def next(self):
        while True:
            line = self.events.readline()
            assert line, 'the bridge closed its events before finishing'
            event = json.loads(line)
            if not (self.skip_samples and event['event'] == 'tree_sample'):
                return event

    def hello_then_close(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('v2protocol', ROOT / 'platform/studio/atelier/build_v2/protocol.py')
        protocol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(protocol)
        with os.fdopen(self.response_r, 'rb', buffering=0) as stream:
            payload = protocol.read_payload(stream)
        assert protocol.decode_payload(protocol.RESPONSE, payload)['type'] == 'hello'
        os.close(self.request_w)

    def finish(self):
        return self.process.wait(timeout=30)


@darwin
def test_normal_attempt_reports_pinned_identity_and_confirmed_cleanup(tmp_path):
    import fcntl
    lock = os.open(tmp_path / 'checkout.lock', os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    custody = fcntl.fcntl(lock, fcntl.F_DUPFD_CLOEXEC, 3)
    bridge = Bridge(tmp_path, 'normal', custody=[custody])
    os.close(custody)
    assert bridge.next() == {'event': 'queued'}
    assert bridge.next() == {'event': 'admitted'}
    started = bridge.next()
    assert started['event'] == 'child_started' and started['pid'] > 0 and started['started'] and started['boot']
    monitor = bridge.next()
    assert monitor == dict(event='monitor', pid=MONITOR[0], started=str(MONITOR[1]), boot=started['boot'],
                           invocation=monitor['invocation']), 'the custody monitor, once, with its correlation'
    assert len(monitor['invocation']) == 32
    bridge.hello_then_close()
    exited = bridge.next()
    assert exited == dict(event='child_exited', pid=started['pid'], started=started['started'], boot=started['boot'],
                          returncode=0, stopped_by=None)
    assert bridge.next() == dict(event='finished', cleanup='confirmed', reason=None)
    assert bridge.finish() == 0
    record = json.loads((bridge.report / 'cleanup.json').read_text())
    assert record == dict(schema=1, invocation=monitor['invocation'], boot=started['boot'],
                          child=[started['pid'], int(started['started'])], monitor=MONITOR, confirmed=True,
                          reason=None)
    call = json.loads((bridge.report / 'fake-call.json').read_text())
    info = os.fstat(lock)
    assert call['kind'] == 'job' and call['limit_gib'] == 1 and len(call['pass_fds']) == 2
    assert call['custody'] == [[info.st_dev, info.st_ino]], 'custody goes to the monitor, not pass_fds'
    worker = json.loads(bridge.fd_report.read_text())
    assert sorted(map(int, worker['open'])) == sorted([worker['request_fd'], worker['response_fd']])
    assert [info.st_dev, info.st_ino] not in worker['open'].values()
    os.close(lock)


@darwin
def test_queued_cancel_and_controller_loss_spawn_nothing_and_confirm_the_withdrawal(tmp_path):
    for how in ('signal', 'liveness'):
        folder = tmp_path / how
        folder.mkdir()
        bridge = Bridge(folder, 'queue')
        assert bridge.next() == {'event': 'queued'}
        if how == 'signal':
            bridge.process.send_signal(signal.SIGTERM)
        else:
            os.close(bridge.liveness_w)
        assert bridge.next() == dict(event='finished', cleanup='confirmed', reason=None)
        assert bridge.finish() == 1
        assert not (bridge.report / 'stdout.log').exists()


@darwin
@pytest.mark.parametrize('scenario,stopped_by,confirmed', [
    ('memory', 'guard', True), ('unconfirmed', None, False), ('capacity', None, False)])
def test_guard_stops_and_uncertain_cleanup_are_reported_as_such(tmp_path, scenario, stopped_by, confirmed):
    bridge = Bridge(tmp_path, scenario)
    assert bridge.next()['event'] == 'queued'
    assert bridge.next()['event'] == 'admitted'
    assert bridge.next()['event'] == 'child_started'
    if scenario != 'memory':
        bridge.hello_then_close()
    exited = bridge.next()
    assert exited['event'] == 'child_exited' and exited['stopped_by'] == stopped_by
    finished = bridge.next()
    assert finished['cleanup'] == ('confirmed' if confirmed else 'unconfirmed')
    assert confirmed or finished['reason']
    assert bridge.finish() == 1


def test_classification_is_conservative():
    assert classify(None, {'state': 'memory_limit'}, None, False) == 'guard'
    assert classify(SystemExit('child exceeded 30 s'), {'state': 'running'}, None, False) == 'deadline'
    assert classify(SystemExit(143), None, None, False) == 'cancel'
    assert classify(None, None, None, True) == 'cancel'
    assert classify(None, {'state': 'running'}, {'state': 'child_exited'}, False) is None


INVOCATION = 'a' * 32
FILES = [[1, 11], [1, 12]]


def receipts(**tree):
    """A consistent confirmed set: pinned child (7, 70), fresh receipts, an empty drained tree."""
    base = dict(owner=7, owner_started=70, time=100., state='child_exited', cleanup_complete=True,
                processes=[], footprint_bytes=0,
                late_reporters=dict(adopted=[], unresolved=[], unresolved_pids=[], scan_failed=False))
    base.update(tree)
    return dict(error=None, child=(7, 70), process=dict(pid=7, process_start=70, time=100., state='running'),
                tree=base, admitted=True, since=50., now=200., invocation=INVOCATION,
                timings=dict(schema=1, invocation_id=INVOCATION), custody=None)


def judge(error, child, process, tree, **rest):
    return cleanup(error, child, process, tree, **rest)


STOPPED = dict(state='memory_limit', processes=[{'pid': 8}], footprint_bytes=123, cleanup_processes=[],
               cleanup_footprint_bytes=0)
CUSTODY = dict(held=False, released='cleanup_complete', lock_files=[[1, 12], [1, 11]])


@pytest.mark.parametrize('evidence', [
    receipts(),
    receipts(time=201.),  # within the clock skew
    receipts(**STOPPED),
    {**receipts(**STOPPED), 'error': SystemExit('child exceeded 30 s')},
    {**receipts(custody=CUSTODY, monitor=[9, 90]), 'custody': FILES},
    {**receipts(custody=CUSTODY, monitor=[9, 90]), 'custody': FILES, 'monitor': [9, 90]},
    dict(error=SystemExit(143), child=None, process=None, tree=None, admitted=False, since=50., now=200.,
         invocation=INVOCATION, timings=None, custody=None),
    # The real guard publishes its diagnostic timings even for a run cancelled in the queue.
    dict(error=SystemExit(143), child=None, process=None, tree=None, admitted=False, since=50., now=200.,
         invocation=INVOCATION, timings=dict(schema=1, invocation_id=INVOCATION), custody=None),
], ids=['exited', 'skew', 'stopped', 'deadline', 'custody', 'custody-monitor', 'queued-cancel',
        'queued-cancel-timings'])
def test_cleanup_confirms_only_consistent_affirmative_evidence(evidence):
    assert judge(**evidence) == (True, None)


def mutate(path, value, **tree):
    evidence = receipts(**tree)
    evidence[path] = value
    return evidence


@pytest.mark.parametrize('evidence', [
    # front-man's repro: a running, nonempty tree that claims cleanup_complete
    receipts(state='running', processes=[{'pid': 8}], footprint_bytes=123),
    receipts(processes=[{'pid': 8}]),
    receipts(footprint_bytes=123),
    receipts(footprint_bytes=False),
    receipts(processes=None),
    receipts(cleanup_processes=[], cleanup_footprint_bytes=0),
    receipts(**{**STOPPED, 'cleanup_processes': [{'pid': 9}]}),
    receipts(**{**STOPPED, 'cleanup_footprint_bytes': 4096}),
    receipts(state='memory_limit', processes=[], footprint_bytes=0),
    receipts(state='cleanup_incomplete', termination_reason='child_exited'),
    receipts(termination_reason='child_exited'),
    receipts(error='RuntimeError()'),
    receipts(cleanup_complete=1),
    receipts(state=None),
    receipts(late_reporters=dict(adopted=[], unresolved=[{'pid': 9}], unresolved_pids=[], scan_failed=False)),
    receipts(late_reporters=dict(adopted=[], unresolved=[], unresolved_pids=[9], scan_failed=False)),
    receipts(late_reporters=dict(adopted=[], unresolved=[], unresolved_pids=[], scan_failed=True)),
    receipts(late_reporters=None),
    receipts(owner=8),
    receipts(owner_started=71),
    mutate('process', dict(pid=7, process_start=71, time=100.)),
    mutate('process', None),
    mutate('tree', None),
    mutate('tree', []),
    receipts(time=10.),
    receipts(time='100'),
    receipts(time=float('nan')),
    receipts(time=float('inf')),
    receipts(time=203.),  # beyond the clock skew past the bridge's now
    mutate('process', dict(pid=7, process_start=70, time=float('inf'))),
    mutate('process', dict(pid=7, process_start=70, time=1e12)),
    mutate('process', dict(pid=7, process_start=70, time=10.)),
    mutate('process', dict(pid=7, process_start=70)),
    mutate('timings', None),
    mutate('timings', dict(schema=1, invocation_id='b' * 32)),
    mutate('admitted', False),
    mutate('error', RuntimeError('Capacity exit remains uncertain; reservation and named locks retained')),
    mutate('custody', FILES),
    mutate('custody', FILES, custody=dict(held=True, reason='unverified', lock_files=FILES)),
    mutate('custody', FILES, custody=dict(held=False, released='late_cleanup_complete', lock_files=FILES)),
    mutate('custody', FILES, custody=dict(held=False, released='cleanup_complete', lock_files=[[1, 11]])),
    mutate('custody', FILES, custody=dict(held=False, released='cleanup_complete', lock_files=[[1, 'x'], 3])),
    mutate('custody', FILES, custody=dict(held=False, released='cleanup_complete')),
    mutate('custody', FILES, custody='released'),
    receipts(custody=CUSTODY),
    receipts(monitor=[9, 90]),  # a monitor identity for a run without custody
    mutate('custody', FILES, custody=CUSTODY),  # custody without a monitor identity
    mutate('custody', FILES, custody=CUSTODY, monitor=[9, 0]),
    mutate('custody', FILES, custody=CUSTODY, monitor=[True, 90]),
    {**receipts(custody=CUSTODY, monitor=[9, 90]), 'custody': FILES, 'monitor': [9, 91]},  # another monitor
    {**receipts(custody=CUSTODY, monitor=[9, 90]), 'custody': FILES, 'monitor': [9, 90], 'monitor_fault': True},
])
def test_cleanup_rejects_malformed_contradictory_stale_or_missing_evidence(evidence):
    confirmed, reason = judge(**evidence)
    assert confirmed is False and reason


@pytest.mark.parametrize('change', [
    dict(admitted=True),
    dict(error=None),
    dict(process=dict(pid=7, process_start=70, time=100.)),
    dict(tree=dict(owner=7, owner_started=70, time=100., state='child_exited', cleanup_complete=True,
                   processes=[], footprint_bytes=0)),
    dict(timings=dict(schema=1, invocation_id='b' * 32)),
    dict(timings=[]),
])
def test_no_child_is_confirmed_only_for_an_unwind_before_admission_without_receipts(change):
    evidence = dict(error=SystemExit(143), child=None, process=None, tree=None, admitted=False, since=50., now=200.,
                    invocation=INVOCATION, timings=None, custody=None)
    evidence.update(change)
    assert judge(**evidence)[0] is False


@darwin
def test_running_tree_receipts_become_samples_of_the_pinned_child_once_each(tmp_path):
    bridge = Bridge(tmp_path, 'sampling')
    assert bridge.next() == {'event': 'queued'}
    assert bridge.next() == {'event': 'admitted'}
    started = bridge.next()
    assert started['event'] == 'child_started'
    first = bridge.next()
    assert first['event'] == 'tree_sample' and set(first) == {'event', 'time', 'processes'}
    assert first['processes'] == [[started['pid'], started['started']]]
    second = bridge.next()
    assert second['event'] == 'tree_sample' and second['time'] > first['time']
    assert second['processes'] == [[started['pid'], started['started']], [1, '7']], 'reported, not judged'
    bridge.hello_then_close()
    assert bridge.next()['event'] == 'child_exited'
    assert bridge.next()['event'] == 'finished'
    bridge.finish()


SINCE, NOW, CHILD = 1000., 2000., (42, 77)


def running(**change):
    value = dict(owner=42, owner_started=77, state='running', time=1500.,
                 processes=[dict(pid=42, started=77, name='python', depth=0, footprint_bytes=1)])
    value.update(change)
    return value


def test_a_fresh_running_receipt_of_the_pinned_child_is_a_sample():
    assert tree_sample(running(), CHILD, SINCE, NOW, None) == dict(time=1500., processes=[[42, '77']])
    two = running(processes=running()['processes'] + [dict(pid=9, started=3)])
    assert tree_sample(two, CHILD, SINCE, NOW, 1400.)['processes'] == [[42, '77'], [9, '3']]


@pytest.mark.parametrize('tree, last', [
    (None, None),  # absent
    ('not a receipt', None),  # malformed
    (running(time=999.), None),  # stale: before this invocation
    (running(time=NOW + 60), None),  # from the future
    (running(time=float('nan')), None),  # malformed time
    (running(time=True), None),  # malformed time
    (running(), 1500.),  # not newer than the last sample
    (running(owner=43), None),  # another identity
    (running(owner_started=78), None),  # a reused pid
    (running(owner_started='77'), None),  # malformed identity
    (running(state='child_exited'), None),  # not a running sample
    (running(processes='42'), None),  # malformed list
    (running(processes=[dict(pid=42)]), None),  # a process without its start time
    (running(processes=[dict(pid='42', started=77)]), None),  # malformed pid
])
def test_absent_stale_future_malformed_or_foreign_receipts_are_never_samples(tree, last):
    assert tree_sample(tree, CHILD, SINCE, NOW, last) is None
    assert tree_sample(running(), None, SINCE, NOW, None) is None, 'no pinned child yet'


@darwin
@pytest.mark.parametrize('scenario', ['monitor_changed', 'monitor_missing'])
def test_a_published_monitor_that_changes_or_goes_missing_is_a_fault_and_never_confirmed(tmp_path, scenario):
    import fcntl
    lock = os.open(tmp_path / 'checkout.lock', os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    custody = fcntl.fcntl(lock, fcntl.F_DUPFD_CLOEXEC, 3)
    bridge = Bridge(tmp_path, scenario, custody=[custody])
    os.close(custody)
    assert [bridge.next()['event'] for _ in range(4)] == ['queued', 'admitted', 'child_started', 'monitor']
    assert bridge.next() == dict(event='fault', reason='the published custody monitor identity changed or went missing')
    bridge.hello_then_close()
    assert bridge.next()['event'] == 'child_exited'
    finished = bridge.next()
    assert finished['event'] == 'finished' and finished['cleanup'] == 'unconfirmed' and 'monitor' in finished['reason']
    bridge.finish()
    record = json.loads((bridge.report / 'cleanup.json').read_text())
    assert record['confirmed'] is False and record['monitor'] == MONITOR
    os.close(lock)


@darwin
def test_a_receipt_from_another_controller_never_publishes_a_monitor(tmp_path):
    import fcntl
    lock = os.open(tmp_path / 'checkout.lock', os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    custody = fcntl.fcntl(lock, fcntl.F_DUPFD_CLOEXEC, 3)
    bridge = Bridge(tmp_path, 'monitor_foreign', custody=[custody])
    os.close(custody)
    assert [bridge.next()['event'] for _ in range(3)] == ['queued', 'admitted', 'child_started']
    bridge.hello_then_close()
    assert bridge.next()['event'] == 'child_exited', 'no monitor event'
    assert bridge.next()['event'] == 'finished'
    bridge.finish()
    assert json.loads((bridge.report / 'cleanup.json').read_text())['monitor'] is None
    os.close(lock)


def test_runs_without_custody_publish_no_monitor_and_write_no_cleanup_record(tmp_path):
    if sys.platform != 'darwin':
        pytest.skip('process identities use macOS libproc')
    bridge = Bridge(tmp_path, 'normal')
    events = [bridge.next()['event'] for _ in range(3)]
    bridge.hello_then_close()
    events += [bridge.next()['event'], bridge.next()['event']]
    bridge.finish()
    assert events == ['queued', 'admitted', 'child_started', 'child_exited', 'finished']
    assert not (bridge.report / 'cleanup.json').exists()


CONTROLLER = (5, 50)


def readiness(**change):
    value = dict(running(), controller=list(CONTROLLER), monitor=[9, 90])
    value.update(change)
    return value


def test_a_fresh_readiness_receipt_of_the_pinned_child_and_this_bridge_names_the_monitor():
    assert monitor_identity(readiness(), CHILD, CONTROLLER, SINCE, NOW) == [9, 90]


@pytest.mark.parametrize('tree', [
    None, 'not a receipt',
    readiness(state='child_exited'),  # not a readiness receipt
    readiness(time=999.), readiness(time=NOW + 60), readiness(time=float('nan')),  # not fresh
    readiness(owner=43), readiness(owner_started=78),  # another child
    readiness(controller=[5, 51]), readiness(controller=None),  # another controller
    readiness(monitor=None), readiness(monitor=[9]), readiness(monitor=[9, 0]), readiness(monitor=[0, 90]),
    readiness(monitor=[True, 90]), readiness(monitor=[9, '90']), readiness(monitor=(9, 90)),
    readiness(monitor=[42, 90]),  # the child itself
    readiness(monitor=[5, 90]),  # the controller itself
])
def test_no_usable_monitor_identity_is_ever_inferred(tree):
    assert monitor_identity(tree, CHILD, CONTROLLER, SINCE, NOW) is None
    assert monitor_identity(readiness(), None, CONTROLLER, SINCE, NOW) is None, 'no pinned child yet'


@darwin
def test_explicit_large_script_reservation_matches_the_actual_guard_ceiling(tmp_path):
    bridge = Bridge(tmp_path, 'normal', memory=16)
    assert bridge.next()['event'] == 'queued'
    assert bridge.next()['event'] == 'admitted'
    assert bridge.next()['event'] == 'child_started'
    bridge.hello_then_close()
    assert bridge.next()['event'] == 'child_exited'
    assert bridge.next()['cleanup'] == 'confirmed'
    assert bridge.finish() == 0
    assert json.loads((bridge.report / 'fake-call.json').read_text())['script_memory_gib'] == 16


@darwin
@pytest.mark.parametrize('program,gpu', [('/Applications/Blender.app/Contents/MacOS/Blender', 10),
                                        ('/Applications/Blender.app/Contents/MacOS/blender', 10),
                                        ('/usr/bin/python3', None), ('/tmp/Blender-wrapper', None)])
def test_literal_blender_job_reserves_full_guard_gpu_without_changing_launch_kind(tmp_path, program, gpu):
    bridge = Bridge(tmp_path, 'gpu_probe', memory=10, program=program)
    assert bridge.next()['event'] == 'queued'
    assert bridge.next()['event'] == 'finished'
    assert bridge.finish() == 1
    call = json.loads((bridge.report / 'fake-call.json').read_text())
    assert call['kind'] == 'job'
    assert call['limit_gib'] == 10
    assert call['job_gpu_gib'] == gpu
    assert call['script_memory_gib'] is None
