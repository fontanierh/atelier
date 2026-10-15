import json
import os
import socket
import subprocess
import sys

import pytest

from atelier import capacity_probe as probe
from atelier.capacity_probe_child import command, pinned, process_start, receive, send
from atelier.capacity_service import ShadowService

pytestmark = pytest.mark.skipif(sys.platform != 'darwin' and not sys.platform.startswith('linux'),
                                reason='OS process-start identity unavailable')


def state(database, epoch=1):
    return ShadowService(database).apply(dict(id=f'inspect-{epoch}', action='status', epoch=epoch),
                                         now=int(probe.time.monotonic()))['requests'][0]


def fixed_worker():
    parent, child_end = socket.socketpair()
    try:
        child = subprocess.Popen(command('worker', child_end.fileno()), pass_fds=(child_end.fileno(),),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    finally:
        child_end.close()
    return parent, child


def test_real_closed_roster_registers_runs_and_releases(tmp_path):
    result = probe.run(tmp_path / 'probe.sqlite')
    assert result['passed'] and result['release'] == 'released'
    assert result['gate_opened'] and result['useful_byte']
    assert result['worker_waited'] and result['launcher_waited']
    assert result['admission'] is False and result['native_eligible'] is False
    assert result['synthetic_resources'] and result['synthetic_guard_ready']
    record = state(tmp_path / 'probe.sqlite')
    assert record['state'] == 'released' and len(record['identities']) == 1


@pytest.mark.parametrize('fault', ['eof', 'epoch', 'epoch-bool', 'nonce', 'identity'])
def test_fixed_worker_cannot_emit_useful_byte_for_invalid_gate(fault):
    channel, child = fixed_worker()
    bound = dict(epoch=1, nonce='a' * 64)
    try:
        send(channel, bound)
        ready = receive(channel)
        assert ready['worker'] == [child.pid, process_start(child.pid)]
        assert child.poll() is None  # Readiness is emitted before useful work.
        if fault == 'eof':
            channel.shutdown(socket.SHUT_WR)
        else:
            gate = dict(kind='go', worker=ready['worker'], **bound)
            if fault == 'epoch':
                gate['epoch'] = 2
            elif fault == 'epoch-bool':
                gate['epoch'] = True
            elif fault == 'nonce':
                gate['nonce'] = 'b' * 64
            else:
                gate['worker'] = [child.pid, ready['worker'][1] + 1]
            send(channel, gate)
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode != 0 and stdout == stderr == b''
    finally:
        channel.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_epoch_restart_before_gate_fences_release_and_no_useful_byte(tmp_path, monkeypatch):
    original = probe.Probe.open_gate

    def restart_first(self):
        self.call('restart')
        original(self)

    monkeypatch.setattr(probe.Probe, 'open_gate', restart_first)
    result = probe.run(tmp_path / 'probe.sqlite')
    assert not result['passed'] and not result['gate_opened'] and not result['useful_byte']
    assert result['worker_waited'] and result['launcher_waited']
    assert result['release'] == 'fenced'
    record = state(tmp_path / 'probe.sqlite', epoch=2)
    assert record['state'] == 'uncertain' and record['locks'] == ['closed-probe']


def test_missing_worker_wait_receipt_retains_charge_after_launcher_wait(tmp_path, monkeypatch):
    def discard(self, receipt):
        raise ValueError('Simulated lost worker receipt')

    monkeypatch.setattr(probe.Probe, 'accept_wait', discard)
    result = probe.run(tmp_path / 'probe.sqlite')
    assert not result['passed'] and not result['worker_waited'] and result['launcher_waited']
    assert result['useful_byte'] is None
    assert result['release'] == 'wait'
    record = state(tmp_path / 'probe.sqlite')
    assert record['state'] == 'uncertain' and record['resources']['memory_mib'] == 1


def test_refused_readiness_keeps_gate_closed_but_exact_waits_allow_release(tmp_path, monkeypatch):
    original = probe.Probe.call

    def refuse(self, action, **fields):
        if action == 'running':
            return dict(result='wait')
        return original(self, action, **fields)

    monkeypatch.setattr(probe.Probe, 'call', refuse)
    result = probe.run(tmp_path / 'probe.sqlite')
    assert not result['passed'] and not result['gate_opened'] and not result['useful_byte']
    assert result['worker_waited'] and result['launcher_waited'] and result['release'] == 'released'


def test_pinned_observation_never_infers_exit_from_pid_disappearance(tmp_path, monkeypatch):
    instance = probe.Probe(tmp_path / 'probe.sqlite')
    instance.ready = dict(launcher=[10, 1], worker=[20, 1])
    instance.child = type('Owned', (), {'poll': lambda self: None})()
    monkeypatch.setattr(probe, 'process_start', lambda pid: (_ for _ in ()).throw(ProcessLookupError()))
    assert set(instance.observe(1).processes.values()) == {'unknown'}
    instance.launcher_waited = True
    assert instance.observe(1).processes == {'10:1': 'dead', '20:1': 'unknown'}


def test_receipt_identity_is_exact_and_real_start_is_stable(tmp_path):
    assert pinned() == [os.getpid(), process_start(os.getpid())]
    instance = probe.Probe(tmp_path / 'probe.sqlite')
    instance.ready = dict(launcher=[10, 1], worker=[20, 1])
    receipt = dict(kind='waited', launcher=[10, 1], worker=[20, 2], returncode=0, useful_byte=True, **instance.bound)
    with pytest.raises(ValueError, match='binding mismatch'):
        instance.accept_wait(receipt)
    assert not instance.worker_waited


def test_worker_gate_deadline_exits_without_useful_byte():
    channel, child = fixed_worker()
    try:
        send(channel, dict(epoch=1, nonce='a' * 64))
        receive(channel)
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode != 0 and stdout == stderr == b''
    finally:
        channel.close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=5)


def test_existing_database_is_never_reused(tmp_path, monkeypatch):
    path = tmp_path / 'unrelated'
    path.write_bytes(b'keep')
    monkeypatch.setattr(probe.subprocess, 'Popen', lambda *a, **k: pytest.fail('must refuse before launch'))
    assert not probe.run(path)['passed']
    assert path.read_bytes() == b'keep'


def test_unavailable_os_identity_refuses_before_launch_or_database_creation(tmp_path, monkeypatch):
    def unavailable(pid):
        raise ValueError('Identity API unavailable')
    monkeypatch.setattr(probe, 'process_start', unavailable)
    monkeypatch.setattr(probe.subprocess, 'Popen', lambda *a, **k: pytest.fail('must refuse before launch'))
    result = probe.run(tmp_path / 'fresh.sqlite')
    assert not result['passed'] and not (tmp_path / 'fresh.sqlite').exists()


def test_cli_reports_shadow_only(tmp_path, capsys):
    assert probe.main(tmp_path / 'probe.sqlite') == 0
    result = json.loads(capsys.readouterr().out)
    assert result['admission'] is False and result['native_eligible'] is False


def test_cli_routes_only_explicit_probe_path(tmp_path, monkeypatch):
    from atelier.cli import main
    calls = []
    monkeypatch.setattr(probe, 'main', lambda path: calls.append(path) or 7)
    assert main(['capacity', 'probe', str(tmp_path / 'fresh.sqlite')]) == 7
    assert calls == [str(tmp_path / 'fresh.sqlite')]
    with pytest.raises(SystemExit, match='only supported by capacity shadow'):
        main(['capacity', 'probe', str(tmp_path / 'fresh.sqlite'), '--state', 'other'])


@pytest.mark.parametrize('field,value', [('epoch', True), ('nonce', 'b' * 64),
                                        ('returncode', True), ('extra', 1)])
def test_malformed_wait_receipt_never_establishes_exit(tmp_path, field, value):
    instance = probe.Probe(tmp_path / 'probe.sqlite')
    instance.ready = dict(launcher=[10, 1], worker=[20, 1])
    receipt = dict(kind='waited', launcher=[10, 1], worker=[20, 1], returncode=0, useful_byte=True, **instance.bound)
    receipt[field] = value
    with pytest.raises(ValueError):
        instance.accept_wait(receipt)
    assert not instance.worker_waited and instance.useful_byte is None
