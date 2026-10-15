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

from atelier.capacity import Resources
from atelier.capacity_broker import CapacityBroker
from atelier.capacity_client import AdmissionSession, CapacityError, status
from atelier.safety import guarded


@pytest.fixture
def broker(tmp_path, monkeypatch):
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


def test_ordinary_unchanged_launcher_still_works_without_machine_activation(tmp_path, broker, monkeypatch):
    from atelier import capacity_runtime
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


@pytest.mark.parametrize('pressure', ['missing', 'stale', 'memory', 'disk'])
def test_pressure_refusal_never_releases_useful_work(tmp_path, broker, pressure):
    observation = dict(observed_monotonic=time.monotonic(), available_memory_mib=4096, available_temp_mib=8192)
    if pressure == 'stale':
        observation['observed_monotonic'] -= 10
    if pressure in ('memory', 'disk'):
        observation['available_memory_mib' if pressure == 'memory' else 'available_temp_mib'] = 0
    broker.observe = lambda: None if pressure == 'missing' else observation
    request = dict(id='pressure', resources=asdict(Resources(256, 1000, 16, 1)), locks=[], seconds=10)
    marker = tmp_path / 'executed'
    with pytest.raises(CapacityError):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'], tmp_path / 'guard',
                    admission=AdmissionSession(broker.socket_path, request), limit_gib=.25, timeout=10)
    assert not marker.exists()
    assert status(broker.socket_path)['charged_count'] == 0


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
    with pytest.raises(CapacityError):
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
