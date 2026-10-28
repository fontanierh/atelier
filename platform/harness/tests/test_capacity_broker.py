"""Real private sockets, SQLite and ordinary Python children; no native workloads or admission activation."""
from dataclasses import asdict
import os
import json
from pathlib import Path
import select
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import tempfile

import pytest

from atelier.harness import capacity_broker as server
from atelier.harness import capacity_client as client
from atelier.harness import capacity_protocol as wire
from atelier.harness.capacity import Resources


# These recovery cases need the retained-identity exit witness to survive a broker restart and a
# helper's own shutdown; that path does not observe the exit on Linux CI yet, so they run in the
# macOS job rather than being asserted against a platform where they fail.
macos_only = pytest.mark.macos_only


@pytest.fixture
def short_path():
    with tempfile.TemporaryDirectory(prefix='acb-', dir='/tmp') as folder:
        yield Path(folder)


def stop(instance):
    instance._stop.set()
    instance.test_thread.join(timeout=3)
    instance.close()
    assert not instance.test_thread.is_alive() and not instance.test_errors, instance.test_errors


@pytest.fixture
def broker_factory(short_path):
    instances = []
    def create(**options):
        arguments = dict(state_directory=short_path / 'capacity',
                         total=Resources(memory_mib=4096, cpu_millis=4000, temp_mib=4096, io_slots=4, gpu_mib=4096),
                         disk_pool=short_path, observe=lambda: {'observed_monotonic': time.monotonic(),
                         'available_memory_mib': 4096, 'available_temp_mib': 4096},
                         guards=lambda *args: wire.GuardFacts((), 0))
        instance = server.CapacityBroker(**(arguments | options))
        instance.test_errors = []
        def run():
            try:
                instance.serve_forever()
            except BaseException as error:
                instance.test_errors.append(error)
        instance.test_thread = threading.Thread(target=run, daemon=True)
        instance.test_thread.start()
        instances.append(instance)
        return instance
    yield create
    for instance in instances:
        stop(instance)


@pytest.fixture
def broker(broker_factory):
    return broker_factory()


@pytest.mark.parametrize('action', ['status', 'private unknown action'])
def test_operation_error_logs_only_safe_phase_metadata(broker, monkeypatch, capsys, action):
    def fail(message, principal):
        raise OSError(5, 'private transport details')
    monkeypatch.setattr(broker, 'handle', fail)
    with pytest.raises(wire.CapacityError, match='broker refused'):
        client._rpc(broker.socket_path, {'action': action, 'nonce': 'private request details'}, 2.)
    output = capsys.readouterr().err
    report = json.loads(output.split('capacity operation refused: ')[1].splitlines()[0])
    assert report['action'] == ('status' if action == 'status' else 'invalid')
    assert report['phase'] == 'handle' and report['error_type'] == 'OSError' and report['errno'] == 5
    assert report['elapsed_seconds'] >= 0 and report['observed_at'] > 0
    assert 'private' not in output and 'nonce' not in output


def test_slow_success_logs_elapsed_operation_without_changing_result(broker, monkeypatch, capsys):
    marker = 'capacity slow operation: '
    original = broker.handle
    def slow(message, principal):
        time.sleep(.26)
        return original(message, principal)
    monkeypatch.setattr(broker, 'handle', slow)
    assert client.status(broker.socket_path)['charged_count'] == 0
    output = ''
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        output += capsys.readouterr().err
        if marker in output and '\n' in output.split(marker, 1)[1]:
            break
        time.sleep(0.01)
    else:
        pytest.fail(f'timed out waiting for {marker!r} line in broker stderr; got {output!r}')
    report = json.loads(output.split(marker, 1)[1].splitlines()[0])
    assert report['action'] == 'status' and report['phase'] == 'send'
    assert report['elapsed_seconds'] >= .25 and report['observed_at'] > 0
    assert report['handle_seconds'] >= .25
    assert report['receive_seconds'] >= 0 and report['send_seconds'] >= 0


def session(broker, name='leaf', **changes):
    request = {'id': name, 'owner': 'fixture', 'checkout': str(broker.directory.parent),
               'resources': asdict(Resources(memory_mib=128, cpu_millis=1000)), 'locks': ['fixture'], 'seconds': 1}
    request.update(changes)
    return client.AdmissionSession(broker.socket_path, request, timeout=2.)


def test_retry_required_records_remain_durable_but_are_not_active_waiters(broker):
    dormant, ready = session(broker, 'dormant'), session(broker, 'ready')
    dormant.offer()
    assert dormant.close()['released'] is True
    ready.offer()
    report = client.status(broker.socket_path)
    assert report['waiting_count'] == 1 and report['charged_count'] == 0
    rows = {row['id']: row for row in report['records']}
    assert rows['dormant']['state'] == 'waiting' and rows['ready']['state'] == 'queued'
    assert 'retry required' in rows['dormant']['wait_reason']
    before = rows['dormant']['first_ready']
    ready.close()
    assert client.status(broker.socket_path)['waiting_count'] == 0
    # Retrying preserves the original ready age and re-enters the live queue normally.
    dormant = session(broker, 'dormant')
    assert dormant.offer()['first_ready'] == before
    assert client.status(broker.socket_path)['waiting_count'] == 1
    dormant.close()


def test_normal_wait_keeps_ready_age_and_nonce_without_capacity_or_gate(broker, monkeypatch):
    first, waiting = session(broker, 'short'), session(broker, 'waiting', seconds=600)
    first.offer()
    observed = []
    def next_boundary(seconds):
        report = client.status(broker.socket_path)
        row = next(row for row in report['records'] if row['id'] == 'waiting')
        assert report['charged_count'] == 0 and report['waiting_count'] == 2
        assert row['state'] == 'queued' and not broker._gates
        observed.append((row['first_ready'], waiting.nonce))
        first.close()
    monkeypatch.setattr(client.time, 'sleep', next_boundary)
    try:
        result = client.wait_for_offer(waiting, seconds=5)
        assert len(observed) == 1
        assert result['first_ready'] == observed[0][0] and waiting.nonce == observed[0][1]
        assert result['selected'] is True and client.status(broker.socket_path)['charged_count'] == 0
        assert not broker._gates
    finally:
        first.close()
        waiting.close()


def test_memory_pressure_does_not_query_disk_availability(short_path, monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, 'disk_usage', lambda *_: pytest.fail('disk used for admission'))
    observation = wire.pressure(short_path / 'missing-disk-path')
    assert observation['available_memory_mib'] > 0
    assert 'available_temp_mib' not in observation


def gated_child(admission, *, hold=False):
    fd = admission.gate()
    try:
        return subprocess.Popen([sys.executable, '-c',
            "import os,sys; gate=os.read(int(sys.argv[1]),1); os.close(int(sys.argv[1])); "
            "sys.stdout.buffer.write(b'useful' if gate==b'1' else b''); sys.stdout.buffer.flush(); "
            + ("sys.stdin.buffer.read(1)" if hold else "pass"), str(fd)],
            pass_fds=(fd,), stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    finally:
        os.close(fd)


def start(admission, child):
    pin = wire.process_start(child.pid)
    admission.start(child_pid=child.pid, child_start=pin, process_guard={}, tree_guard={}, limit_bytes=128 * 1024**2)
    return pin


@macos_only
def test_real_socket_gate_commit_and_pinned_wait_release(broker):
    admission = session(broker)
    assert admission.offer()['selected'] is True
    assert client.status(broker.socket_path)['charged_count'] == 0
    child = gated_child(admission)
    try:
        assert not select.select([child.stdout], [], [], .05)[0]
        pin = start(admission, child)
        assert child.communicate(timeout=3)[0] == b'useful'
        assert client.status(broker.socket_path)['charged_count'] == 1
        # Positive root exit may race the guard's last check; draining is still charged.
        assert admission.check()['state'] == 'draining'
        assert admission.close(child=child, child_start=pin)['released'] is True
        assert client.status(broker.socket_path)['charged_count'] == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def lose_response_once(monkeypatch, action):
    original = client._rpc
    calls = []
    def rpc(path, message, timeout, **kwargs):
        result = original(path, message, timeout, **kwargs)
        if message.get('action') == action:
            calls.append((dict(message), result[0]))
            if len(calls) == 1:
                raise client.CapacityTransportError('response lost after broker commit')
        return result
    monkeypatch.setattr(client, '_rpc', rpc)
    return calls


def test_lost_offer_response_preserves_queue_age_without_charge_or_gate(broker, monkeypatch):
    admission = session(broker)
    calls = lose_response_once(monkeypatch, 'offer')
    response = admission.offer()
    assert len(calls) == 2 and calls[0][0] == calls[1][0]
    assert response['first_ready'] == calls[0][1]['first_ready']
    assert response['epoch'] == calls[0][1]['epoch']
    assert client.status(broker.socket_path)['charged_count'] == 0 and not broker._gates
    admission.close()


def test_lost_check_and_close_responses_keep_one_grant_and_affirmative_release(broker, monkeypatch):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    try:
        # Retransmit the root identity as an unacknowledged batch. The server already retains it.
        admission._acknowledged.clear()
        checks = lose_response_once(monkeypatch, 'check')
        assert admission.check(descendants=[(child.pid, pin)])['admission'] is True
        assert len(checks) == 2 and checks[0][0] == checks[1][0]
        assert checks[0][0]['descendants'] == [[child.pid, pin]]
        assert client.status(broker.socket_path)['charged_count'] == 1
        assert admission._acknowledged == {(child.pid, pin)}
        assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
        closes = lose_response_once(monkeypatch, 'close')
        assert admission.close(child=child, child_start=pin)['released'] is True
        assert len(closes) == 2 and closes[0][0] == closes[1][0]
        assert closes[0][1]['released'] is True
        assert closes[0][0]['witness']['child'] == [child.pid, pin]
        assert client.status(broker.socket_path)['charged_count'] == 0 and not broker._gates
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


def test_singleton_does_not_replace_live_socket_or_advance_epoch(broker):
    before = client.status(broker.socket_path)
    inode = broker.socket_path.stat().st_ino
    with pytest.raises(wire.CapacityError, match='already owns'):
        server.CapacityBroker(broker.directory, total=broker.total, disk_pool=broker.disk_pool)
    assert client.status(broker.socket_path)['epoch'] == before['epoch']
    assert broker.socket_path.stat().st_ino == inode


def test_pregrant_unknown_start_can_cancel_without_exit_witness(broker):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission)
    admission.close(child=child, child_start=None)
    assert child.communicate(timeout=3)[0] == b''
    assert client.status(broker.socket_path)['charged_count'] == 0


def expire(broker, admission):
    with broker._lock:
        state = broker._load()
        state['records'][admission.request['id']]['heartbeat'] = time.monotonic() - broker.lease_seconds - 1
        broker._save(state)


def complete(admission, child, pin):
    assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
    return admission.close(child=child, child_start=pin)


def test_simultaneous_full_vector_claims_are_atomic(broker):
    admissions = [session(broker, name, resources=asdict(broker.total), locks=['exclusive']) for name in ('a', 'b')]
    admissions[0].offer()
    with pytest.raises(wire.CapacityError, match='queued'):
        admissions[1].offer()
    children = [gated_child(item, hold=True) for item in admissions]
    pins = [wire.process_start(child.pid) for child in children]
    barrier, outcomes = threading.Barrier(2), []
    def claim(index):
        barrier.wait(timeout=2)
        try:
            admissions[index].start(child_pid=children[index].pid, child_start=pins[index],
                                    process_guard={}, tree_guard={}, limit_bytes=128 * 1024**2)
            outcomes.append((index, True))
        except wire.CapacityError:
            outcomes.append((index, False))
    threads = [threading.Thread(target=claim, args=(index,)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert sorted(success for _, success in outcomes) == [False, True]
    observed = client.status(broker.socket_path)
    assert observed['charged_count'] == 1 and observed['charged_resources'] == asdict(broker.total.admission())
    for index, success in outcomes:
        if success:
            complete(admissions[index], children[index], pins[index])
        else:
            assert children[index].communicate(input=b'x', timeout=3)[0] == b''
            admissions[index].close(child=children[index], child_start=pins[index])
    assert client.status(broker.socket_path)['charged_count'] == 0


def test_refused_atomic_replacement_preserves_vector_and_locks(broker):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    before = client.status(broker.socket_path)['records'][0]
    with pytest.raises(wire.CapacityError, match='replacement refused'):
        admission.replace(Resources(memory_mib=8192, cpu_millis=4001), ['different'])
    after = client.status(broker.socket_path)['records'][0]
    assert (after['resources'], after['locks']) == (before['resources'], before['locks'])
    with pytest.raises(wire.CapacityError, match='queue while holding'):
        session(broker, 'illegal-queue').offer()
    complete(admission, child, pin)


def test_commit_failure_never_releases_gate(broker, monkeypatch):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission)
    save = broker._save
    def fail_grant(state):
        if any(record['state'] == 'running' for record in state['records'].values()):
            raise sqlite3.OperationalError('injected commit failure')
        return save(state)
    monkeypatch.setattr(broker, '_save', fail_grant)
    with pytest.raises(wire.CapacityError):
        start(admission, child)
    assert child.communicate(timeout=3)[0] == b''
    assert client.status(broker.socket_path)['charged_count'] == 0
    admission.close(child=child, child_start=admission.child[1])


def test_queued_expiry_and_rebind_close_gates_preserve_original_age(broker):
    first = session(broker)
    original = first.offer()
    child = gated_child(first)
    expire(broker, first)
    client.status(broker.socket_path)
    assert child.communicate(timeout=3)[0] == b''
    second = session(broker)
    assert second.offer()['first_ready'] == original['first_ready']
    old_nonce = second.nonce
    child = gated_child(second)
    third = session(broker)
    assert third.offer()['first_ready'] == original['first_ready']
    assert third.nonce != old_nonce
    assert child.communicate(timeout=3)[0] == b''
    with pytest.raises(wire.CapacityError, match='identity mismatch'):
        second.gate()
    third.close()


def test_same_boot_restart_before_go_closes_gate_and_fences_session(broker_factory):
    before = broker_factory()
    admission = session(before)
    offer = admission.offer()
    child = gated_child(admission)
    stop(before)
    assert child.communicate(timeout=3)[0] == b''
    after = broker_factory()
    assert client.status(after.socket_path)['epoch'] > offer['epoch']
    with pytest.raises(wire.CapacityError, match='fenced'):
        admission.gate()
    retry = session(after)
    assert retry.offer()['first_ready'] == offer['first_ready']
    retry.close()


def test_restart_while_queued_refuses_reoffer_without_resources_or_gate(broker_factory, monkeypatch):
    before = broker_factory()
    first, waiting = session(before, 'first'), session(before, 'waiting', seconds=600)
    first.offer()
    with pytest.raises(client.CapacityQueued):
        waiting.offer()
    pin = waiting.nonce, waiting.epoch, waiting.boot
    stop(before)
    after = broker_factory()
    monkeypatch.setattr(client.time, 'sleep', lambda _: pytest.fail('fenced wait retried'))
    with pytest.raises(client.CapacityError, match='fenced'):
        client.wait_for_offer(waiting)
    assert (waiting.nonce, waiting.epoch, waiting.boot) == pin
    assert client.status(after.socket_path)['charged_count'] == 0 and not after._gates


@macos_only
@pytest.mark.parametrize('parent_receipt', [True, False])
def test_same_boot_restart_retains_then_accepts_positive_exit(broker_factory, parent_receipt):
    before = broker_factory()
    admission = session(before)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    stop(before)
    after = broker_factory()
    current = client.status(after.socket_path)
    assert current['recovering'] and current['charged_count'] == 1
    with pytest.raises(wire.CapacityError, match='fenced'):
        admission.check()
    assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
    if parent_receipt:
        assert admission.close(child=child, child_start=pin)['released']
    else:
        # No controller exit RPC: only the rearmed, positively bound kernel watch can drain it.
        assert client.reconcile(after.socket_path)['charged_count'] == 0
    assert client.status(after.socket_path)['charged_count'] == 0


def test_boot_change_releases_capacity_without_certifying_outputs(broker_factory):
    before = broker_factory(boot=lambda: 'boot-a')
    admission = session(before)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    stop(before)
    # Inject an authoritative new boot observation; this test does not reboot the host.
    after = broker_factory(boot=lambda: 'boot-b')
    assert client.status(after.socket_path)['charged_count'] == 0
    with after._lock:
        state = after._load()
        assert state['records']['leaf']['release_witness'] == {'kind': 'os-boot-change', 'from': 'boot-a', 'to': 'boot-b'}
        after.connection.rollback()
    assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
    with pytest.raises(wire.CapacityError, match='fenced'):
        admission.close(child=child, child_start=pin)


def test_expired_heartbeat_never_reclaims_and_recovery_blocks_selection(broker):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    expire(broker, admission)
    status = client.status(broker.socket_path)
    assert status['charged_count'] == 1 and status['recovering']
    with broker._lock:
        state = broker._load()
        assert broker._selection(state) is None
        broker.connection.rollback()
    with pytest.raises(wire.CapacityError, match='uncertain'):
        admission.check()
    assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
    assert admission.close(child=child, child_start=pin)['released']


def test_unknown_ancestry_retains_even_after_all_observed_pins_exit(broker):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    sibling = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read(1)'], stdin=subprocess.PIPE)
    sibling_pin = (sibling.pid, wire.process_start(sibling.pid))
    try:
        admission.check(descendants=[sibling_pin])
        sibling.communicate(input=b'x', timeout=3)
        assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
        with pytest.raises(wire.CapacityError, match='uncertain'):
            admission.close(child=child, child_start=pin, descendants=[sibling_pin])
        status = client.reconcile(broker.socket_path)
        assert status['recovering'] and status['charged_count'] == 1
        assert status['records'][0]['ancestry_unknown']
    finally:
        if sibling.poll() is None:
            sibling.kill()
        sibling.wait()


def test_released_logical_id_accepts_new_definition_and_fresh_age(broker):
    first = session(broker, purpose='first', phase='job')
    original = first.offer()
    child = gated_child(first)
    pin = start(first, child)
    complete(first, child, pin)
    second = session(broker, seconds=77, resources=asdict(Resources(memory_mib=256, cpu_millis=500)), purpose='next')
    offered = second.offer()
    assert offered['first_ready'] >= original['first_ready'] and second.nonce != first.nonce
    status = client.status(broker.socket_path)['records'][0]
    assert status['resources']['memory_mib'] == 256 and status['purpose'] == 'next'
    second.close()


def test_two_short_bypasses_protect_original_long_request(broker):
    long = session(broker, 'long', seconds=600)
    original = long.offer()
    for index in range(2):
        short = session(broker, f'short-{index}')
        short.offer()
        child = gated_child(short)
        pin = start(short, child)
        complete(short, child, pin)
    third = session(broker, 'short-2')
    with pytest.raises(wire.CapacityError, match='queued'):
        third.offer()
    assert long.offer()['first_ready'] == original['first_ready']
    child = gated_child(long)
    pin = start(long, child)
    complete(long, child, pin)
    third.close()


def test_positive_root_exit_resolves_guard_terminal_race(broker_factory):
    class Watch:
        exited = False
        def __init__(self, pin):
            self.pin = pin
        def poll(self):
            return self.exited
        def close(self):
            pass
    fail = [False]
    def guards(*args):
        if fail[0]:
            Watch.exited = True
            raise wire.CapacityError('guard became terminal after first exit poll')
        return wire.GuardFacts((), 0)
    broker = broker_factory(watch=Watch, guards=guards)
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    with broker._lock:
        fail[0] = True
    assert admission.check()['state'] == 'draining'
    assert client.status(broker.socket_path)['charged_count'] == 1
    complete(admission, child, pin)


@pytest.mark.parametrize('malformed', [None, {}, {'pid': 1}])
def test_nested_malformed_guard_roster_is_a_health_refusal(short_path, malformed):
    import json
    owner, child, monitor = (10, 10), (20, 20), (30, 30)
    process, tree = short_path / 'process.json', short_path / 'tree.json'
    limit = 128 * 1024**2
    process.write_text(json.dumps({'time': time.time(), 'state': 'running', 'limit_bytes': limit,
                                   'pid': child[0], 'process_start': child[1]}))
    tree.write_text(json.dumps({'observed_monotonic': time.monotonic(), 'state': 'running',
                                'limit_bytes': limit, 'owner': child[0], 'owner_started': child[1],
                                'processes': [malformed], 'footprint_bytes': 0}))
    guards = {name: {'pid': monitor[0], 'start': monitor[1], 'report': str(report)}
              for name, report in [('process_guard', process), ('tree_guard', tree)]}
    with pytest.raises(wire.CapacityError, match='Invalid retained guard process'):
        wire.validate_guards(guards, child, owner, limit, 128, started=lambda pid: pid,
                             child_of=lambda *args: True, alive=lambda pin: True)


def test_fresh_guard_report_does_not_make_exited_monitor_live(short_path):
    # Pinned start identity remains observable for an unreaped zombie; positive liveness is separate.
    guards = {name: {'pid': 30, 'start': 30, 'report': str(short_path / 'unused')}
              for name in ('process_guard', 'tree_guard')}
    with pytest.raises(wire.CapacityError, match='not live'):
        wire.validate_guards(guards, (20, 20), (10, 10), 128 * 1024**2, 128,
                             started=lambda pid: pid, child_of=lambda *args: True, alive=lambda pin: False)


def test_already_dead_root_after_lost_watch_is_unknown_on_same_boot(broker_factory):
    before = broker_factory()
    admission = session(before)
    admission.offer()
    child = gated_child(admission, hold=True)
    start(admission, child)
    stop(before)  # Exit events from this point cannot reach the lost watch or durable DB.
    assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
    after = broker_factory()
    observed = client.reconcile(after.socket_path)
    assert observed['recovering'] and observed['charged_count'] == 1
    assert observed['records'][0]['witnessed'] == 0


def test_exit_watch_post_arm_pid_reuse_discards_kernel_handle():
    child = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read(1)'], stdin=subprocess.PIPE)
    pin = (child.pid, wire.process_start(child.pid))
    starts = iter([pin[1], pin[1] + 1])
    watch = wire.ExitWatch(pin, started=lambda pid: next(starts))
    try:
        assert watch.handle is None
        child.communicate(input=b'x', timeout=3)
        assert watch.poll() is False
    finally:
        watch.close()
        if child.poll() is None:
            child.kill()
        child.wait()


def test_departed_helpers_reclaim_kernel_descriptors_without_losing_exit_proof(monkeypatch):
    from types import SimpleNamespace
    import errno
    handles, watches = set(), []
    class Queue:
        def __init__(self):
            if len(handles) >= 16:
                raise OSError(errno.EMFILE, 'injected finite descriptor budget')
            handles.add(self)
        def control(self, events, count, timeout):
            if events:
                self.pid = events[0].ident
                return []
            return [SimpleNamespace(ident=self.pid, fflags=select.KQ_NOTE_EXIT, flags=0)]
        def close(self):
            handles.remove(self)
    monkeypatch.setattr(wire.sys, 'platform', 'darwin')
    monkeypatch.setattr(wire.select, 'kqueue', Queue, raising=False)
    monkeypatch.setattr(wire.select, 'kevent', lambda pid, **kwargs: SimpleNamespace(ident=pid), raising=False)
    for name, value in dict(KQ_FILTER_PROC=1, KQ_EV_ADD=2, KQ_EV_ONESHOT=4, KQ_NOTE_EXIT=8, KQ_EV_ERROR=16).items():
        monkeypatch.setattr(wire.select, name, value, raising=False)
    for pid in range(100, 700):
        watch = wire.ExitWatch((pid, 1), started=lambda _: 1)
        watches.append(watch)
        assert watch.poll() is True
        assert watch.handle is None
        assert not handles
    assert all(watch.poll() is True for watch in watches)


@macos_only
@pytest.mark.parametrize('committed', [False, True])
def test_killed_broker_fences_gate_and_retains_committed_vector(broker_factory, short_path, committed):
    # Abrupt process death exercises OS-owned pipe closure and durable SQLite state, not close().
    code = '''import sys,time
from pathlib import Path
from atelier.harness.capacity import Resources
from atelier.harness.capacity_broker import CapacityBroker
from atelier.harness.capacity_protocol import GuardFacts
broker=CapacityBroker(Path(sys.argv[1]),total=Resources(memory_mib=4096,cpu_millis=4000,temp_mib=4096,io_slots=4,gpu_mib=4096),disk_pool=Path(sys.argv[2]),guards=lambda *a:GuardFacts((),0),observe=lambda:{'observed_monotonic':time.monotonic(),'available_memory_mib':4096,'available_temp_mib':4096})
broker.serve_forever()
'''
    daemon = subprocess.Popen([sys.executable, '-c', code, str(short_path / 'capacity'), str(short_path)])
    child = None
    try:
        endpoint = short_path / 'capacity' / 'broker.sock'
        deadline = time.monotonic() + 3
        while True:
            try:
                client.status(endpoint, timeout=.1)
                break
            except (OSError, wire.CapacityError):
                assert daemon.poll() is None and time.monotonic() < deadline
                time.sleep(.01)
        admission = client.AdmissionSession(endpoint, {'id': 'crash', 'resources': asdict(Resources(memory_mib=128)), 'locks': ['crash']})
        admission.offer()
        child = gated_child(admission, hold=committed)
        if committed:
            start(admission, child)
        daemon.kill()
        daemon.wait(timeout=3)
        after = broker_factory()
        observed = client.status(after.socket_path)
        assert observed['charged_count'] == int(committed)
        if committed:
            assert observed['recovering']
            assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
            assert client.reconcile(after.socket_path)['charged_count'] == 0
        else:
            assert child.communicate(timeout=3)[0] == b''
    finally:
        if daemon.poll() is None:
            daemon.kill()
        daemon.wait(timeout=3)
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)


@pytest.mark.parametrize('loss_on', [1, 3])
@pytest.mark.parametrize('live_tail', [False, True])
def test_terminal_monitor_hint_stays_charged_until_positive_exit_then_reports_completion(broker_factory, tmp_path, loss_on, live_tail):
    import json
    from dataclasses import asdict
    class Watch:
        exited = False
        def __init__(self, pin): self.pin = pin
        def poll(self): return self.exited
        def close(self): pass
    armed, calls = [False], [0]
    def guards(*args):
        if armed[0]:
            calls[0] += 1
            if calls[0] >= loss_on:
                raise wire.CapacityError('Capacity guard identity is not live and owned')
        return wire.GuardFacts((), 0)
    broker = broker_factory(watch=Watch, guards=guards)
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = wire.process_start(child.pid)
    receipt = tmp_path / 'terminal.json'
    limit = 128 * 1024**2
    binding = dict(pid=os.getpid(), start=wire.process_start(os.getpid()), report=str(receipt))
    admission.start(child_pid=child.pid, child_start=pin, process_guard={}, tree_guard=binding, limit_bytes=limit)
    try:
        receipt.write_text(json.dumps(dict(owner=child.pid, owner_started=pin, time=time.time(),
            observed_monotonic=time.monotonic(), state='child_exited', cleanup_complete=True,
            processes=[], footprint_bytes=0, limit_bytes=limit)))
        armed[0] = True
        if live_tail:
            helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with pytest.raises(wire.CapacityError, match='no longer healthy'):
                    admission.check(descendants=[(helper.pid, wire.process_start(helper.pid))])
                held = client.status(broker.socket_path)
                assert held['charged_count'] == 1
                assert next(row for row in held['records'] if row['id'] == admission.request['id'])['retained'] == 2
            finally:
                helper.terminate(); helper.wait(timeout=3)
        before = set(admission._acknowledged)
        hint = admission.check()
        assert hint['finish_required'] is True and hint['admission'] is False and hint['state'] == 'uncertain'
        assert admission._acknowledged == before
        assert child.poll() is None  # A hint cannot claim the actual root has exited.
        report = client.status(broker.socket_path)
        assert report['charged_count'] == 1 and report['recovering'] is True
        assert child.communicate(input=b'x', timeout=3)[0] == b'useful'
        Watch.exited = True
        completion = admission.check()
        assert completion['terminal'] is True and completion['admission'] is False
        assert completion['state'] == 'released' and completion['child'] == [child.pid, pin]
        assert client.status(broker.socket_path)['charged_count'] == 0
        helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        try:
            with pytest.raises(wire.CapacityError, match='unretained process identities'):
                admission.check(descendants=[(helper.pid, wire.process_start(helper.pid))])
        finally:
            helper.terminate(); helper.wait(timeout=3)
        with pytest.raises(wire.CapacityError, match='live grant'):
            admission.replace(Resources(memory_mib=128), ['fixture'])
        assert admission.close(child=child, child_start=pin)['released'] is True
    finally:
        if child.poll() is None: child.kill()
        child.wait()


def test_lost_selection_denies_go_and_retains_ready_age(broker, capsys):
    long = session(broker, 'long', seconds=600)
    before = long.offer()['first_ready']
    child = gated_child(long)
    short = session(broker, 'short')
    short.offer()
    try:
        with pytest.raises(client.CapacityOfferLost) as denial:
            start(long, child)
        assert denial.value.session is long and denial.value.cleanup is None
        assert child.communicate(timeout=3)[0] == b''  # The broker closed the gate without GO.
        assert not broker._gates and client.status(broker.socket_path)['charged_count'] == 0
        assert long.close(child=child, child_start=long.child[1]) == {
            'ok': True, 'namespace': wire.NAMESPACE, 'boot_id': broker.boot, 'mode': 'legacy-bridge',
            'state': 'waiting', 'released': True}
        short.close()
        retry = session(broker, 'long', seconds=600)
        retry.requeue_after(long)
        assert retry.offer()['first_ready'] == before
        retry.close()
        assert '"reason": "selection-changed"' in capsys.readouterr().err
    finally:
        short.close()
        if child.poll() is None:
            child.kill()
        child.wait()


def test_requeue_restart_is_refused_before_mutating_queue(broker, monkeypatch):
    original = session(broker, 'requeue', seconds=600)
    original.offer()
    original.close()
    retry = session(broker, 'requeue', seconds=600)
    retry.requeue_after(original)
    with broker._lock:
        state = broker._load()
        state['epoch'] += 1
        broker._save(state)
    with pytest.raises(client.CapacityError, match='requeue was fenced'):
        retry.offer()
    assert retry.nonce is None
    report = client.status(broker.socket_path)
    assert report['waiting_count'] == report['charged_count'] == 0
    assert report['records'][0]['state'] == 'waiting'


def test_missing_gate_is_a_plain_refusal_with_its_own_reason(broker, capsys):
    admission = session(broker, 'missing-gate', seconds=600)
    admission.offer()
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        with pytest.raises(client.CapacityError) as error:
            start(admission, child)
        assert type(error.value) is client.CapacityError
        assert '"reason": "gate-unavailable"' in capsys.readouterr().err
        assert client.status(broker.socket_path)['charged_count'] == 0
    finally:
        child.kill(); child.wait()
        admission.close(child=child, child_start=admission.child[1])


@pytest.mark.parametrize('mode', ['interrupted', 'completed', 'unwitnessed'])
def test_administrative_interruption_is_atomic_fenced_and_not_normal_reconcile(broker, monkeypatch, tmp_path, mode):
    completed, unwitnessed = mode == 'completed', mode == 'unwitnessed'
    from atelier.harness import capacity_abandon as abandon
    guards = {}
    for kind in ('process_guard', 'tree_guard'):
        p = tmp_path / (kind + '.json')
        p.write_text('{"state":"running"}')
        guards[kind] = dict(pid=80 + len(guards), start=800 + len(guards), report=str(p))
    record = dict(request=dict(id='stopped-compile', owner='worker', phase='compile', performance=True,
                              resources=asdict(Resources(memory_mib=128,cpu_millis=1000)), locks=['fixture'], seconds=1),
                  sequence=1, first_ready=time.time()-10, bypasses=0, nonce='one-use', state='uncertain',
                  child=[70,700], principal=[71,710], guards=guards, roster=[[70,700],[72,720]],
                  exited=[[70,700]], ancestry_unknown=True, epoch=1, limit_bytes=128*1024**2, heartbeat=time.monotonic()-60)
    if completed:
        broker.mode='capacity'
        monkeypatch.setattr(broker,'_compatibility_proof',lambda:{'activation_id':broker.activation_id})
        record['request'].update(phase='job',performance=False)
        Path(guards['tree_guard']['report']).write_text(json.dumps(dict(owner=70,owner_started=700,
            controller=[71,710],state='child_exited',cleanup_complete=True,processes=[],footprint_bytes=0,
            peak_bytes=100,limit_bytes=record['limit_bytes'],time=time.time())))
    with broker._lock:
        state=broker._load();state['records']['stopped-compile']=record;broker._save(state)
    assert client.reconcile(broker.socket_path)['charged_count']==1
    evidence=dict(id='stopped-compile',nonce='one-use',epoch=1,boot_id=broker.boot,
                  administrator='maintenance',operator_reference='operator instruction 123',services=[])
    action=(client.abandon_unwitnessed if unwitnessed else
            client.abandon_completed if completed else client.abandon_interrupted)
    if unwitnessed:
        with broker._lock:
            state=broker._load();state['records']['stopped-compile']['exited']=[];broker._save(state)
        evidence['acknowledge_missing_root_exit']=True
    if completed or unwitnessed:
        import hashlib
        evidence.update(guards=guards,report_sha256={k:hashlib.sha256(Path(g['report']).read_bytes()).hexdigest()
                                                   for k,g in guards.items()})
    # Legacy mode is never eligible; then emulate healthy verified full mode for this private broker.
    if not completed:
        with pytest.raises(wire.CapacityError):action(broker.socket_path,evidence)
    broker.mode='capacity'
    monkeypatch.setattr(broker,'_compatibility_proof',lambda:{'activation_id':broker.activation_id})
    monkeypatch.setattr(abandon,'absent',lambda pin:True)
    rows={90:dict(pid=90,started=10,parent=1,executable='/apps/agent')}
    monkeypatch.setattr(abandon,'census',lambda **kwargs:rows)
    wrong={**evidence,'epoch':2}
    with pytest.raises(wire.CapacityError):action(broker.socket_path,wrong)
    assert client.status(broker.socket_path)['charged_count']==1
    if unwitnessed:
        # Administrative evidence cannot enter normal reconciliation or bypass another charge.
        with pytest.raises(wire.CapacityError):
            client._rpc(broker.socket_path, {'action':'reconcile','unwitnessed_compile':evidence}, 2.)
        import copy
        with broker._lock:
            state=broker._load();other=copy.deepcopy(state['records']['stopped-compile'])
            other['request']['id']='other';other['nonce']='other'
            state['records']['other']=other;broker._save(state)
        with pytest.raises(wire.CapacityError,match='Another charged job'):
            action(broker.socket_path,evidence)
        assert client.status(broker.socket_path)['charged_count']==2
        with broker._lock:
            state=broker._load();del state['records']['other'];broker._save(state)
    result=action(broker.socket_path,evidence)
    assert result['released'] is True and result['witness']['output_certified'] is False
    assert client.status(broker.socket_path)['charged_count']==0
    with pytest.raises(wire.CapacityError):action(broker.socket_path,evidence)
    with broker._lock:
        state=broker._load();saved=state['records']['stopped-compile'];broker.connection.rollback()
    assert saved['release_witness']['kind']==('administrative-unwitnessed-compile' if unwitnessed else
        'administrative-completed-job' if completed else 'administrative-interruption')
    assert saved['release_witness']['root_exit_observed'] is (not unwitnessed)
    assert saved['exited']==([] if unwitnessed else [[70,700]]) and saved['ancestry_unknown']
    assert json.loads(Path(guards['process_guard']['report']).read_text())['state']=='running'
    assert json.loads(Path(guards['tree_guard']['report']).read_text())['state']==('child_exited' if completed else 'running')


def test_slow_status_reader_cannot_block_a_running_jobs_check(broker, monkeypatch):
    admission = session(broker, 'responsive-check')
    admission.offer()
    child = gated_child(admission, hold=True)
    pin = start(admission, child)
    entered = threading.Event()
    original_handle, original_accept = broker.handle, socket.socket.accept
    def accept(listener):
        channel, address = original_accept(listener)
        channel.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        return channel, address
    def handle(message, principal):
        if message.get('test_slow_reader'):
            entered.set()
            return {'namespace': wire.NAMESPACE, 'padding': 'x' * 60000}, None
        return original_handle(message, principal)
    monkeypatch.setattr(socket.socket, 'accept', accept)
    monkeypatch.setattr(broker, 'handle', handle)
    slow = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    slow.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    try:
        slow.connect(str(broker.socket_path))
        wire.send(slow, {'namespace': wire.NAMESPACE, 'action': 'status', 'test_slow_reader': True})
        assert entered.wait(1)
        admission.timeout = .5
        assert admission.check()['state'] == 'running'
    finally:
        slow.close()
        admission.timeout = 2.
        if child.poll() is None:
            child.communicate(input=b'1', timeout=3)
        admission.close(child=child, child_start=pin)


def test_unchanged_owned_observation_does_not_commit_state(broker, monkeypatch):
    epoch = client.status(broker.socket_path)['epoch']
    with broker._lock:
        broker.mode = 'capacity'
        monkeypatch.setattr(broker, '_compatibility_proof', lambda: {'activation_id': broker.activation_id})
    saved = []
    original = broker._save
    monkeypatch.setattr(broker, '_save', lambda state: (saved.append(True), original(state))[-1])
    try:
        result, fd = client._rpc(broker.socket_path, {'action': 'owned', 'epoch': epoch,
            'boot_id': broker.boot, 'activation_id': broker.activation_id, 'candidates': []}, 2.)
        assert result['owned'] == [] and fd is None and not saved
    finally:
        with broker._lock:
            broker.mode = 'legacy-bridge'


def test_handle_eagain_is_refused_not_replayed_as_socket_readiness(broker, monkeypatch):
    monkeypatch.setattr(broker, 'handle', lambda *args: (_ for _ in ()).throw(BlockingIOError(35, 'private')))
    with pytest.raises(wire.CapacityError, match='broker refused'):
        client.status(broker.socket_path)


def test_partial_reply_transfers_descriptor_only_once(broker, monkeypatch):
    read_fd, write_fd = os.pipe()
    original_handle, original_sendmsg = broker.handle, socket.socket.sendmsg
    transfers = []
    def handle(message, principal):
        if message.get('test_fd'):
            return {'namespace': wire.NAMESPACE, 'padding': 'x' * 60000}, read_fd
        return original_handle(message, principal)
    def sendmsg(channel, buffers, ancillary=(), *args):
        if ancillary:
            count = original_sendmsg(channel, [buffers[0][:17]], ancillary, *args)
            if count:
                transfers.append(count)
            return count
        return original_sendmsg(channel, buffers, ancillary, *args)
    monkeypatch.setattr(broker, 'handle', handle)
    monkeypatch.setattr(socket.socket, 'sendmsg', sendmsg)
    received = None
    try:
        result, received = client._rpc(broker.socket_path, {'action': 'status', 'test_fd': True}, 2., descriptor=True)
        assert len(result['padding']) == 60000 and transfers == [17]
        os.write(write_fd, b'proof')
        assert os.read(received, 5) == b'proof'
    finally:
        if received is not None:
            os.close(received)
        os.close(write_fd)


@pytest.mark.parametrize('ending', ['expiry', 'disconnect', 'shutdown'])
def test_unsent_descriptor_is_closed_on_every_connection_end(broker, monkeypatch, ending):
    read_fd, write_fd = os.pipe()
    waiting, closed = threading.Event(), threading.Event()
    original_handle, original_sendmsg, original_close = broker.handle, socket.socket.sendmsg, os.close
    def handle(message, principal):
        if message.get('test_fd'):
            return {'namespace': wire.NAMESPACE}, read_fd
        return original_handle(message, principal)
    def sendmsg(channel, buffers, ancillary=(), *args):
        if ancillary:
            waiting.set()
            raise BlockingIOError()
        return original_sendmsg(channel, buffers, ancillary, *args)
    def close(fd):
        result = original_close(fd)
        if fd == read_fd:
            closed.set()
        return result
    monkeypatch.setattr(broker, 'handle', handle)
    monkeypatch.setattr(socket.socket, 'sendmsg', sendmsg)
    monkeypatch.setattr(os, 'close', close)
    broker.rpc_timeout = .2
    caller = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        caller.connect(str(broker.socket_path))
        wire.send(caller, {'namespace': wire.NAMESPACE, 'action': 'status', 'test_fd': True})
        assert waiting.wait(1)
        if ending == 'disconnect':
            caller.close()
        elif ending == 'shutdown':
            stop(broker)
        assert closed.wait(1)
    finally:
        caller.close()
        os.close(write_fd)


def test_diagnostic_type_error_cannot_change_operation_result(broker, monkeypatch):
    original = broker.handle
    def slow(message, principal):
        time.sleep(.26)
        return original(message, principal)
    monkeypatch.setattr(broker, 'handle', slow)
    monkeypatch.setattr(server, 'print', lambda *args, **kwargs: (_ for _ in ()).throw(TypeError()), raising=False)
    assert client.status(broker.socket_path)['charged_count'] == 0


def test_stable_pressure_waits_before_gate_and_preserves_identity(broker, monkeypatch):
    available = [127]
    monkeypatch.setattr(broker, 'observe', lambda: dict(observed_monotonic=time.monotonic(),
                                                     available_memory_mib=available[0]))
    admission = session(broker)
    for _ in range(4):
        with pytest.raises(client.CapacityQueued):
            admission.offer()
        row = client.status(broker.socket_path)['records'][0]
        identity = (row['first_ready'], row['sequence'], admission.nonce)
        if _ == 0:
            original = identity
        assert identity == original and row['state'] == 'queued'
        assert client.status(broker.socket_path)['charged_count'] == 0 and not broker._gates
    available[0] = 128
    assert admission.offer()['selected']
    child = gated_child(admission)
    pin = start(admission, child)
    assert child.communicate(timeout=3)[0] == b'useful'
    assert admission.close(child=child, child_start=pin)['released']


def test_final_pressure_drop_closes_gate_without_execution_and_requeues(broker, monkeypatch):
    admission = session(broker)
    before = admission.offer()['first_ready']
    child = gated_child(admission)
    original = broker._pressure
    def deficit(state, record):
        raise server.PressureWait('complete reservation unavailable')
    monkeypatch.setattr(broker, '_pressure', deficit)
    try:
        with pytest.raises(client.CapacityOfferLost) as error:
            start(admission, child)
        assert error.value.reason == 'pressure-wait'
        assert child.communicate(timeout=3)[0] == b''
        assert not broker._gates and client.status(broker.socket_path)['charged_count'] == 0
        assert admission.close(child=child, child_start=admission.child[1])['released']
        retry = session(broker)
        retry.requeue_after(admission)
        monkeypatch.setattr(broker, '_pressure', original)
        assert retry.offer()['first_ready'] == before
        retry.close()
    finally:
        if child.poll() is None:child.kill()
        child.wait()


@pytest.mark.parametrize('performance', [False, True])
def test_pressure_skips_compatible_small_work_until_old_head_is_protected(broker, monkeypatch, performance):
    monkeypatch.setattr(broker, 'observe', lambda: dict(observed_monotonic=time.monotonic(),available_memory_mib=128))
    large = session(broker, 'old-large', resources=asdict(Resources(memory_mib=256,cpu_millis=1000)),performance=performance)
    with pytest.raises(client.CapacityQueued):large.offer()
    small = session(broker, 'small')
    assert small.offer()['selected']
    for protection in ('age','bypasses'):
        with broker._lock:
            state = broker._load();row=state['records']['old-large']
            row['first_ready'] = time.time() - (901 if protection=='age' else 1)
            row['bypasses'] = 0 if protection=='age' else 2
            broker._save(state)
        with pytest.raises(client.CapacityQueued):small.offer()
        assert client.status(broker.socket_path)['charged_count']==0 and not broker._gates
    large.close();small.close()


@pytest.mark.parametrize('state,measured,expected', [('running',32,96),('running',128,0),('draining',32,128)])
def test_pressure_budget_charges_full_unmeasured_or_remaining_peer_growth(broker,monkeypatch,state,measured,expected):
    monkeypatch.setattr(broker,'guards',lambda *args:wire.GuardFacts((),measured*1024**2))
    peer=dict(state=state,request=dict(resources=asdict(Resources(memory_mib=128))),
              guards={},child=[1,1],principal=[2,2],limit_bytes=128*1024**2)
    candidate=dict(state='queued',request=dict(resources=asdict(Resources(memory_mib=128))))
    monkeypatch.setattr(broker,'observe',lambda:dict(observed_monotonic=time.monotonic(),available_memory_mib=128+expected-1))
    with pytest.raises(server.PressureWait):broker._pressure({'records':{'peer':peer}},candidate)
    memory,growth=broker._pressure_budget({'records':{'peer':peer}})
    assert growth==expected and memory==128+expected-1


@pytest.mark.parametrize('observation', [None,{'observed_monotonic':0,'available_memory_mib':0}])
def test_unavailable_advisory_observation_waits_but_final_start_fails_closed(broker,monkeypatch,observation):
    admission = session(broker)
    admission.offer()
    child = gated_child(admission)
    monkeypatch.setattr(broker, 'observe', lambda: observation)
    try:
        with pytest.raises(client.CapacityQueued):
            admission.offer()
        with pytest.raises(wire.CapacityError, match='observation unavailable') as error:
            start(admission, child)
        assert type(error.value) is wire.CapacityError
        assert child.communicate(timeout=3)[0] == b''
        admission.close(child=child, child_start=admission.child[1])
    finally:
        if child.poll() is None:child.kill()
        child.wait()


@pytest.mark.parametrize('cancel', [False, True])
def test_pressure_queue_deadline_and_cancellation_hold_no_child_or_charge(broker, monkeypatch, cancel):
    monkeypatch.setattr(broker, 'observe', lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=0))
    admission = session(broker)
    original_sleep = client.time.sleep
    def interrupt(seconds):
        raise KeyboardInterrupt
    if cancel:
        monkeypatch.setattr(client.time, 'sleep', interrupt)
    try:
        with pytest.raises(KeyboardInterrupt if cancel else client.CapacityError, match=None if cancel else 'deadline reached'):
            client.wait_for_offer(admission, seconds=5 if cancel else .02)
        row = client.status(broker.socket_path)['records'][0]
        assert row['state'] == 'queued' and client.status(broker.socket_path)['charged_count'] == 0
        assert not broker._gates
        original_ready = row['first_ready']
    finally:
        monkeypatch.setattr(client.time, 'sleep', original_sleep)
        assert admission.close()['released']
    retry = session(broker)
    with pytest.raises(client.CapacityQueued):retry.offer()
    assert client.status(broker.socket_path)['records'][0]['first_ready'] == original_ready
    retry.close()


def test_advisory_peer_guard_failure_does_not_change_holder_health(broker, monkeypatch):
    peer = dict(state='running',request=dict(resources=asdict(Resources(memory_mib=128))),
                guards={},child=[1,1],principal=[2,2],limit_bytes=128*1024**2)
    state = {'records': {'peer': peer}}
    def unavailable(*args):
        raise wire.CapacityError('guard evidence missing')
    monkeypatch.setattr(broker, 'guards', unavailable)
    monkeypatch.setattr(broker, '_root_exited', lambda record: False)
    assert broker._pressure_budget(state, advisory=True) is None
    assert peer['state'] == 'running'
    with pytest.raises(wire.CapacityError, match='enforcement is unavailable'):
        broker._pressure_budget(state)
    assert peer['state'] == 'uncertain'


def test_two_actual_pressure_bypasses_protect_even_an_older_short_job(broker, monkeypatch):
    monkeypatch.setattr(broker, 'observe', lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=128))
    large = session(broker, 'old-short', resources=asdict(Resources(memory_mib=256, cpu_millis=1000)))
    with pytest.raises(client.CapacityQueued):large.offer()
    for number in range(2):
        small = session(broker, 'small-' + str(number))
        assert small.offer()['selected']
        child = gated_child(small)
        pin = start(small, child)
        assert child.communicate(timeout=3)[0] == b'useful'
        assert small.close(child=child, child_start=pin)['released']
        row = next(r for r in client.status(broker.socket_path)['records'] if r['id']=='old-short')
        assert row['bypasses'] == number + 1
    third = session(broker, 'small-third')
    with pytest.raises(client.CapacityQueued):third.offer()
    assert not broker._gates and client.status(broker.socket_path)['charged_count']==0
    large.close()
    assert third.offer()['selected']
    third.close()


@pytest.mark.parametrize('protection', ['age', 'bypasses'])
def test_protected_checkout_sibling_does_not_block_unrelated_compatible_work(broker, protection):
    def row(name, sequence, state, locks):
        return dict(request=dict(id=name, resources=asdict(Resources(memory_mib=128,cpu_millis=1000)),
                                 locks=locks, seconds=1, performance=False),
                    state=state,sequence=sequence,first_ready=time.time(),bypasses=0,
                    guards={},child=[1,1],principal=[2,2],limit_bytes=128*1024**2)
    holder = row('holder',1,'running',['checkout:shared'])
    sibling = row('sibling',2,'queued',['checkout:shared'])
    other = row('unrelated',3,'queued',['checkout:other'])
    sibling['bypasses'] = 2 if protection=='bypasses' else 0
    sibling['first_ready'] -= 901 if protection=='age' else 0
    original = (sibling['first_ready'],sibling['bypasses'])
    state = {'records': {r['request']['id']:r for r in (holder,sibling,other)}}
    assert broker._selection(state,pressure=True) is other
    assert (sibling['first_ready'],sibling['bypasses']) == original
    holder['state'] = 'released'
    assert broker._selection(state,pressure=True) is sibling


def test_queue_status_explains_a_sole_pressure_deficit_without_resampling(broker_factory, monkeypatch):
    broker = broker_factory(total=Resources(memory_mib=32768, cpu_millis=4000),
                            reserve=Resources(memory_mib=4096),
                            observe=lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=17510))
    admission = session(broker, resources=asdict(Resources(memory_mib=14336, cpu_millis=1000)))
    with pytest.raises(client.CapacityQueued, match='deficit 922 MiB') as caught:
        admission.offer()
    monkeypatch.setattr(broker, 'observe', lambda: pytest.fail('status must not sample memory'))
    monkeypatch.setattr(broker, 'guards', lambda *args: pytest.fail('status display must not validate guards'))
    report = client.status(broker.socket_path)
    row = report['records'][0]
    assert '17510 MiB available, 18432 MiB required' in row['wait_reason']
    assert '14336 request + 4096 host reserve + 0 remaining peer growth' in row['wait_reason']
    assert 'sample age' in row['wait_reason'] and 'selected' not in row['wait_reason']
    assert report['observed_at'] <= row['pressure_expires_at'] <= report['observed_at'] + 2
    assert row['wait_reason'].split('; sample age')[0] in str(caught.value)
    assert row['state'] == 'queued' and report['charged_count'] == 0 and not broker._gates
    admission.close()


@pytest.mark.parametrize('change', ['stale', 'epoch', 'request', 'nonce', 'sequence', 'bypasses',
                                   'reserve', 'total', 'holder'])
def test_queue_status_never_reuses_stale_or_changed_context(broker, monkeypatch, change):
    admission = session(broker)
    admission.offer()
    with broker._lock:
        state = broker._load()
        broker.connection.rollback()
        if change == 'stale':broker._queue_status['budget']['observed'] -= 3
        elif change == 'epoch':state['epoch'] += 1
        elif change == 'request':state['records']['leaf']['request']['resources']['memory_mib'] += 1
        elif change in ('nonce', 'sequence', 'bypasses'):
            row = state['records']['leaf']
            row[change] = 'new nonce' if change == 'nonce' else row[change] + 1
        elif change == 'reserve':monkeypatch.setattr(broker, 'reserve', Resources(memory_mib=1))
        elif change == 'total':monkeypatch.setattr(broker, 'total', Resources(memory_mib=4095, cpu_millis=4000))
        elif change == 'holder':
            import copy
            peer = copy.deepcopy(state['records']['leaf'])
            peer['request']['id'] = 'peer';peer['state'] = 'draining';peer['request']['locks'] = []
            state['records']['peer'] = peer
        report = broker._status(state)
        row = next(row for row in report['records'] if row['id'] == 'leaf')
        assert 'required' not in row['wait_reason'] and 'eligible' not in row['wait_reason']
        assert row['pressure_expires_at'] is None
        assert 'fresh pressure' in row['wait_reason'] or change == 'holder'
    admission.close()


def test_queue_status_dormant_history_does_not_invalidate_fresh_budget(broker):
    admission = session(broker)
    admission.offer()
    with broker._lock:
        import copy
        state = broker._load()
        broker.connection.rollback()
        old = copy.deepcopy(state['records']['leaf']);old['state'] = 'waiting';old['request']['id'] = 'old'
        state['records']['old'] = old
        row = next(row for row in broker._status(state)['records'] if row['id'] == 'leaf')
        assert 'advisory offer eligible' in row['wait_reason'] and 'guarded start still required' in row['wait_reason']
    admission.close()


def test_queue_status_reports_actual_pressure_backfill_and_protected_priority(broker, monkeypatch):
    monkeypatch.setattr(broker, 'observe', lambda: dict(observed_monotonic=time.monotonic(), available_memory_mib=128))
    large = session(broker, 'large', resources=asdict(Resources(memory_mib=256, cpu_millis=1000)))
    with pytest.raises(client.CapacityQueued):large.offer()
    small = session(broker, 'small')
    small.offer()
    rows = {r['id']: r for r in client.status(broker.socket_path)['records']}
    assert 'waiting for memory' in rows['large']['wait_reason']
    assert 'advisory offer eligible' in rows['small']['wait_reason']
    with broker._lock:
        state = broker._load();state['records']['large']['bypasses'] = 2;broker._save(state)
    with pytest.raises(client.CapacityQueued, match='waiting behind queue priority'):small.offer()
    rows = {r['id']: r for r in client.status(broker.socket_path)['records']}
    assert 'waiting for memory' in rows['large']['wait_reason']
    assert 'waiting behind queue priority' in rows['small']['wait_reason']
    large.close();small.close()
