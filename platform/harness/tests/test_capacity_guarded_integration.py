"""The real broker gates a lightweight Python child under the actual memory monitors."""
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time

import pytest

from atelier.harness.capacity import Resources
from atelier.harness.capacity_broker import CapacityBroker
from atelier.harness.capacity_client import AdmissionSession, CapacityError, status
from atelier.harness.safety import guarded


@pytest.fixture
def broker(tmp_path, monkeypatch):
    from atelier.harness import capacity_compat
    from atelier.harness import capacity_runtime
    # This private legacy-bridge fixture must never read the host's installed cutover/client.
    monkeypatch.setattr(capacity_compat, 'DEFAULT_RECORD', tmp_path / 'fixture-cutover.json')
    monkeypatch.setattr(capacity_runtime, 'DEFAULT_CONFIG', tmp_path / 'fixture-client.json')
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    monkeypatch.setenv('ATELIER_RENDER_LOCK', str(tmp_path / 'render.lock'))
    monkeypatch.setenv('ATELIER_RENDER_LOCK_SCAN', '0')
    # pytest's default Darwin temp hierarchy exceeds sockaddr_un.sun_path.
    with tempfile.TemporaryDirectory(prefix='ac-', dir='/tmp') as private:
        instance = CapacityBroker(Path(private) / 'broker', total=Resources(2048, 4000, 4096, 2, 2048),
                                  reserve=Resources(64, 1000, 64), disk_pool=tmp_path,
                                  observe=lambda: dict(observed_monotonic=time.monotonic(),
                                                       available_memory_mib=4096, available_temp_mib=8192))
        errors = []

        def serve():
            try:
                instance.serve_forever()
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield instance
        finally:
            instance._stop.set()
            thread.join(timeout=3)
            instance.close()
            assert not thread.is_alive(), 'owned broker did not stop'
            assert errors == []


def test_real_broker_exec_and_release_with_actual_guard_receipts(tmp_path, broker):
    request = dict(id='real-launch', resources=asdict(Resources(256, 1000, 16, 1)),
                   locks=['checkout:test'], seconds=10)
    session = AdmissionSession(broker.socket_path, request)
    folder = tmp_path / 'guard'
    assert guarded.run([sys.executable, '-c', 'print("capacity executed")'], folder,
                       admission=session, limit_gib=.25, timeout=10) == 0
    assert 'capacity executed' in (folder / 'stdout.log').read_text()
    aggregate = json.loads((folder / 'memory-health-tree.json').read_text())
    assert aggregate['state'] == 'child_exited'
    report = status(broker.socket_path)
    own = next(record for record in report['records'] if record['id'] == 'real-launch')
    assert own['state'] == 'released' and own['charged'] is False


@pytest.mark.parametrize('monitor_edges', [False, True])
def test_failed_heartbeat_drains_real_monitors_before_terminal_close(tmp_path, broker, monkeypatch, monitor_edges):
    # Deliberately lose the broker's own live ancestry reads. Without the aggregate monitor's
    # edges only the existing exclusive terminal-tree policy can settle the guarded cleanup;
    # with them, the monitor's positive discovery edges resolve the same helper's ancestry.
    broker.parent = lambda pin: None
    if not monitor_edges:
        from atelier.harness import capacity_protocol
        monkeypatch.setattr(capacity_protocol, 'guard_evidence', lambda record: ((), ()))
    request = dict(id='failed-heartbeat', resources=asdict(Resources(512, 1000, 16, 1)),
                   locks=['checkout:test'], seconds=10)
    session = AdmissionSession(broker.socket_path, request)
    check = session.check
    def fail_after_helper_registration(*, descendants):
        response = check(descendants=descendants)
        if any(pin != session.child for pin in descendants):
            raise CapacityError('deliberate heartbeat transport failure after registration')
        return response
    session.check = fail_after_helper_registration
    code = ('import subprocess,sys,time; '
            'subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
            'time.sleep(30)')
    folder = tmp_path/'guard'
    with pytest.raises(CapacityError, match='deliberate heartbeat'):
        guarded.run([sys.executable, '-c', code], folder, admission=session, limit_gib=.5, timeout=10)
    terminal = json.loads((folder/'memory-health-tree.json').read_text())
    assert terminal['state'] == 'child_exited' and terminal['cleanup_complete'] is True
    assert terminal['processes'] == [] and terminal['footprint_bytes'] == 0
    report = status(broker.socket_path)
    own = next(record for record in report['records'] if record['id'] == 'failed-heartbeat')
    assert own['ancestry_unknown'] is (not monitor_edges) and own['state'] == 'released' and not own['charged']
    assert report['charged_count'] == 0


def test_ordinary_unchanged_launcher_still_works_without_machine_activation(tmp_path, broker, monkeypatch):
    from atelier.harness import capacity_runtime
    monkeypatch.setattr(capacity_runtime, 'DEFAULT_CONFIG', tmp_path / 'not-enabled.json')
    monkeypatch.delenv('ATELIER_CAPACITY_CLIENT', raising=False)
    assert guarded.run([sys.executable, '-c', 'print("legacy executed")'], tmp_path / 'legacy', timeout=10) == 0
    assert status(broker.socket_path)['records'] == []


def test_machine_profile_selects_real_broker_automatically(tmp_path, broker, monkeypatch):
    profile = dict(resources=asdict(Resources(256, 1000, 16, 1)), locks=['configured-fixture'])
    config = broker.directory / 'client.json'
    config.write_text(json.dumps(dict(schema=1, socket=str(broker.socket_path),
                                     profiles={kind: profile for kind in ('job', 'game', 'compile')})))
    config.chmod(0o600)
    monkeypatch.setenv('ATELIER_CAPACITY_CLIENT', str(config))
    assert guarded.run([sys.executable, '-c', 'print("configured capacity")'], tmp_path / 'configured',
                       purpose='profile integration', limit_gib=.25, timeout=10) == 0
    report = status(broker.socket_path)
    assert report['charged_count'] == 0
    assert any(record['state'] == 'released' for record in report['records'])


@pytest.mark.parametrize('pressure', ['missing', 'stale', 'memory'])
def test_pressure_wait_never_spawns_or_releases_useful_work(tmp_path, broker, pressure, monkeypatch):
    from atelier.harness import capacity_client
    wait = capacity_client.wait_for_offer
    monkeypatch.setattr(capacity_client, 'wait_for_offer',
                        lambda admission, **kwargs: wait(admission, seconds=.05))
    observation = dict(observed_monotonic=time.monotonic(), available_memory_mib=4096, available_temp_mib=8192)
    if pressure == 'stale':
        observation['observed_monotonic'] -= 10
    if pressure == 'memory':
        observation['available_memory_mib'] = 0
    broker.observe = lambda: None if pressure == 'missing' else observation
    request = dict(id='pressure', resources=asdict(Resources(256, 1000, 16, 1)), locks=[], seconds=10)
    marker = tmp_path / 'executed'
    with pytest.raises(CapacityError, match='queue wait deadline reached'):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'], tmp_path / 'guard',
                    admission=AdmissionSession(broker.socket_path, request), limit_gib=.25, timeout=10)
    assert not marker.exists()
    assert not (tmp_path / 'guard' / 'memory-health-tree.json').exists()
    assert not broker._gates
    assert status(broker.socket_path)['charged_count'] == 0


@pytest.mark.parametrize('disk', [0, None])
def test_disk_availability_does_not_block_an_ordinary_guarded_child(tmp_path, broker, disk):
    observation = dict(observed_monotonic=time.monotonic(), available_memory_mib=4096)
    if disk is not None:
        observation['available_temp_mib'] = disk
    broker.observe = lambda: observation
    request = dict(id='disk', resources=asdict(Resources(256, 1000, 999999)), locks=[], seconds=10)
    marker = tmp_path / 'executed'
    assert guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'], tmp_path / 'guard',
                       admission=AdmissionSession(broker.socket_path, request), limit_gib=.25, timeout=10) == 0
    assert marker.read_text() == 'ran'
    report = status(broker.socket_path)
    assert report['charged_count'] == 0
    assert all(report[key]['temp_mib'] == 0 for key in ('total', 'reserve', 'charged_resources'))


@pytest.mark.parametrize('invalid', ['process-pin', 'guard-limit', 'stale-process', 'stale-tree', 'malformed'])
def test_invalid_guard_binding_cannot_release_exec_gate(tmp_path, broker, invalid):
    class InvalidBinding(AdmissionSession):
        def start(self, **binding):
            if invalid == 'process-pin':
                binding['process_guard']['start'] += 1
            elif invalid == 'guard-limit':
                binding['limit_bytes'] += 1
            else:
                kind = 'tree_guard' if invalid == 'stale-tree' else 'process_guard'
                original = Path(binding[kind]['report'])
                report = json.loads(original.read_text())
                if invalid != 'malformed':
                    report['observed_monotonic' if kind == 'tree_guard' else 'time'] -= 10
                replacement = tmp_path / 'invalid-report.json'
                replacement.write_text('{' if invalid == 'malformed' else json.dumps(report))
                binding[kind]['report'] = str(replacement)
            return super().start(**binding)
    request = dict(id='bad-binding', resources=asdict(Resources(256, 1000, 16, 1)), locks=[], seconds=10)
    marker = tmp_path / 'executed'
    with pytest.raises(CapacityError, match='guard identity|Guard ceiling|guard receipt|Invalid capacity message'):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'], tmp_path / 'guard',
                    admission=InvalidBinding(broker.socket_path, request), limit_gib=.25, timeout=10)
    assert not marker.exists()
    assert status(broker.socket_path)['charged_count'] == 0


def test_trickled_rpc_response_cannot_extend_absolute_deadline():
    errors = []
    with tempfile.TemporaryDirectory(prefix='act-', dir='/tmp') as directory:
        path = Path(directory) / 'broker.sock'
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            path.chmod(0o600)
            listener.listen(1)
            listener.settimeout(1)

            def trickle():
                try:
                    with listener.accept()[0] as channel:
                        channel.settimeout(1)
                        channel.recv(65536)
                        for byte in b'{"ok":true,"namespace":"atelier.capacity-broker.v1","padding":"' + b'a' * 500 + b'"}\n':
                            channel.sendall(bytes([byte]))
                            time.sleep(.01)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except BaseException as error:
                    errors.append(error)
            thread = threading.Thread(target=trickle, daemon=True)
            thread.start()
            began = time.monotonic()
            try:
                with pytest.raises(CapacityError):
                    status(path, timeout=.15)
                assert time.monotonic() - began < .75
            finally:
                thread.join(timeout=2)
            assert not thread.is_alive() and errors == []


class _Dead:
    def __init__(self, pin):
        self.pin = pin
    def poll(self):
        return False
    def close(self):
        pass


@pytest.mark.skipif(sys.platform != 'darwin', reason='the aggregate monitor binds kqueue exit watches on macOS')
@pytest.mark.parametrize('evidence', ['published', 'wrong-start'])
def test_reaped_helper_exit_from_the_real_monitor_reaches_the_broker(tmp_path, broker, monkeypatch, evidence):
    # The broker loses the race for every helper: no parent read and a watch that never fires.
    from atelier.harness import capacity_protocol
    from atelier.harness.capacity_protocol import ExitWatch
    created = []
    def watch(pin):
        created.append(pin)
        return ExitWatch(pin) if len(created) == 1 else _Dead(pin)  # only the root's own watch is real
    broker.watch_factory, broker.parent = watch, (lambda pin: None)
    if evidence == 'wrong-start':
        real = capacity_protocol.guard_evidence
        def shifted(record):
            edges, exits = real(record)
            return edges, tuple(((pin[0], pin[1] + 1), parent) for pin, parent in exits)
        monkeypatch.setattr(capacity_protocol, 'guard_evidence', shifted)
    request = dict(id='reaped-helper', resources=asdict(Resources(512, 1000, 16, 1)), locks=['checkout:test'], seconds=20)
    session = AdmissionSession(broker.socket_path, request)
    code = ('import subprocess,sys,time; '
            'subprocess.run([sys.executable,"-c","import time; time.sleep(2)"]); time.sleep(3)')
    folder = tmp_path / 'guard'
    try:
        guarded.run([sys.executable, '-c', code], folder, admission=session, limit_gib=.5, timeout=20)
    except CapacityError:
        assert evidence == 'wrong-start'
    with broker._lock:
        record = broker._load()['records']['reaped-helper']
        broker.connection.rollback()
    root = tuple(record['child'])
    helpers = [tuple(pin) for pin in record['roster'] if tuple(pin) != root]
    assert helpers, 'the helper never reached the broker roster'
    exited = {tuple(pin) for pin in record.get('exited', [])}
    if evidence == 'published':
        assert set(helpers) <= exited and not record['ancestry_unknown']
        assert record['state'] == 'released' and record['release_witness']['kind'] == 'retained-kernel-exits'
    else:
        assert not set(helpers) & exited
        assert record.get('release_witness', {}).get('kind') != 'retained-kernel-exits'
