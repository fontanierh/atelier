"""Real private sockets, SQLite and ordinary Python children; no native workloads or admission activation."""
from dataclasses import asdict
import os
from pathlib import Path
import select
import sqlite3
import subprocess
import sys
import threading
import time
import tempfile

import pytest

from atelier import capacity_broker as server, capacity_client as client, capacity_protocol as wire
from atelier.capacity import Resources


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


def session(broker, name='leaf', **changes):
    request = {'id': name, 'owner': 'fixture', 'checkout': str(broker.directory.parent),
               'resources': asdict(Resources(memory_mib=128, cpu_millis=1000)), 'locks': ['fixture'], 'seconds': 1}
    request.update(changes)
    return client.AdmissionSession(broker.socket_path, request, timeout=2.)


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
    assert observed['charged_count'] == 1 and observed['charged_resources'] == asdict(broker.total)
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


@pytest.mark.parametrize('committed', [False, True])
def test_killed_broker_fences_gate_and_retains_committed_vector(broker_factory, short_path, committed):
    # Abrupt process death exercises OS-owned pipe closure and durable SQLite state, not close().
    code = '''import sys,time
from pathlib import Path
from atelier.capacity import Resources
from atelier.capacity_broker import CapacityBroker
from atelier.capacity_protocol import GuardFacts
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
