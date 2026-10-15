"""Exclusive monitored-tree cleanup can resolve historical discovery gaps without invented exits."""
from dataclasses import asdict
import json
import hashlib
import sqlite3
import threading
import time

import pytest

from atelier import capacity_protocol as wire
from atelier import capacity_client
from atelier.capacity import Resources
from atelier.capacity_broker import CapacityBroker, SCHEMA


@pytest.fixture
def terminal(tmp_path):
    path = tmp_path / 'tree.json'
    receipt = dict(owner=100, owner_started=1000, time=time.time() - 1, state='child_exited',
                   limit_bytes=1024**2, cleanup_complete=True, processes=[], footprint_bytes=0)
    path.write_text(json.dumps(receipt))
    roster = [[pid, pid * 10] for pid in range(100, 148)]
    record = dict(state='uncertain', nonce='fixture', child=roster[0], principal=[99, 990],
                  roster=roster, verified_roster=roster[:32], exited=roster[:32], ancestry_unknown=True,
                  first_ready=time.time() - 10, heartbeat=0, sequence=1, bypasses=0, limit_bytes=1024**2,
                  guards={'tree_guard': dict(pid=300, start=3000, report=str(path))},
                  request=dict(id='job', owner='builder', purpose='Compile', resources=asdict(Resources(memory_mib=1)),
                               locks=[], performance=False, seconds=60))
    broker = object.__new__(CapacityBroker)
    broker.mode = 'legacy-bridge'
    broker.alive = lambda pin: False
    return broker, record, path, receipt


def test_historical_48_32_gap_gets_explicit_scoped_witness(terminal):
    broker, record, _, _ = terminal
    assert broker._settle_exited(record)
    assert record['state'] == 'released'
    assert record['release_witness']['kind'] == 'guarded-tree-exit'
    assert record['release_witness']['coverage'] == 'monitored-owned-tree'
    assert len(record['exited']) == 32  # No invented per-process evidence.
    assert record['ancestry_unknown'] is True


@pytest.mark.parametrize('change', [
    {'state': 'running'}, {'state': 'memory_limit'}, {'state': 'test_duration'},
    {'state': 'cleanup_incomplete'}, {'cleanup_complete': False}, {'processes': [{'pid': 100}]},
    {'footprint_bytes': 1}, {'footprint_bytes': False}, {'owner': 101}, {'owner_started': 1001},
    {'limit_bytes': 2}, {'termination_reason': 'memory_limit'}, {'time': 1}, {'time': float('inf')},
    {'time': time.time() + 3600},
])
def test_invalid_terminal_evidence_preserves_uncertainty(terminal, change):
    broker, record, path, receipt = terminal
    path.write_text(json.dumps(receipt | change))
    assert not broker._settle_exited(record)
    assert record['state'] == 'uncertain'


def test_root_absence_is_not_affirmative_exit_evidence(terminal):
    broker, record, _, _ = terminal
    record['exited'] = record['exited'][1:]
    assert not broker._settle_exited(record)


def test_any_live_retained_identity_blocks_terminal_release(terminal):
    broker, record, _, _ = terminal
    broker.alive = lambda pin: pin == tuple(record['roster'][-1])
    assert not broker._settle_exited(record)


@pytest.mark.parametrize('performance,allowed', [(False, False), (True, True)])
def test_full_mode_requires_performance_exclusion(terminal, performance, allowed):
    broker, record, _, _ = terminal
    broker.mode = 'capacity'
    record['request']['performance'] = performance
    assert broker._settle_exited(record) is allowed


@pytest.mark.parametrize('bad', ['missing', 'symlink', 'writable', 'oversized'])
def test_bound_report_must_remain_safe_to_read(terminal, tmp_path, bad):
    broker, record, path, _ = terminal
    if bad == 'missing':
        path.unlink()
    elif bad == 'symlink':
        target = tmp_path / 'target.json'
        path.rename(target)
        path.symlink_to(target)
    elif bad == 'writable':
        path.chmod(0o666)
    else:
        path.write_bytes(b'x' * (wire.MAX_FRAME + 1))
    assert not broker._settle_exited(record)


def test_preserved_original_can_recover_an_overwritten_bound_report(terminal, tmp_path):
    broker, record, bound_path, receipt = terminal
    archive = tmp_path / 'preserved.json'
    raw = json.dumps(receipt).encode()
    archive.write_bytes(raw)
    bound_path.write_text(json.dumps(receipt | {'owner': 999, 'owner_started': 9990}))
    state = {'records': {'job': record}}
    assert not broker._settle_exited(record)
    assert broker._preserved_terminal(state, dict(request_id='job', path=str(archive)))
    witness = record['release_witness']
    assert witness['provenance'] == 'operator-preserved'
    assert witness['evidence_sha256'] == hashlib.sha256(raw).hexdigest()
    assert witness['bound_report_sha256'] == hashlib.sha256(str(bound_path).encode()).hexdigest()
    assert witness['bound_monitor'] == [300, 3000]
    assert len(record['exited']) == 32
    assert json.loads(bound_path.read_text())['owner'] == 999
    assert not broker._preserved_terminal(state, dict(request_id='job', path=str(archive)))


@pytest.mark.parametrize('bad', ['root', 'birth', 'limit', 'time', 'cleanup', 'processes', 'missing-root',
                                 'overlap', 'live', 'symlink', 'mode', 'oversized', 'relative', 'unknown-id'])
def test_preserved_receipt_cannot_bypass_terminal_policy(terminal, tmp_path, bad):
    broker, record, _, receipt = terminal
    archive = tmp_path / 'preserved.json'
    changes = {'root': {'owner': 101}, 'birth': {'owner_started': 1001}, 'limit': {'limit_bytes': 2},
               'time': {'time': 1}, 'cleanup': {'cleanup_complete': False}, 'processes': {'processes': [{'pid': 100}]}}
    archive.write_text(json.dumps(receipt | changes.get(bad, {})))
    if bad == 'missing-root':
        record['exited'] = record['exited'][1:]
    elif bad == 'overlap':
        broker.mode = 'capacity'
    elif bad == 'live':
        broker.alive = lambda pin: True
    elif bad == 'symlink':
        link = tmp_path / 'link.json'
        link.symlink_to(archive)
        archive = link
    elif bad == 'mode':
        archive.chmod(0o666)
    elif bad == 'oversized':
        archive.write_bytes(b'x' * (wire.MAX_FRAME + 1))
    with pytest.raises((wire.CapacityError, OSError)):
        broker._preserved_terminal({'records': {'job': record}}, dict(
            request_id='unknown' if bad == 'unknown-id' else 'job',
            path='relative.json' if bad == 'relative' else str(archive)))
    assert record['state'] == 'uncertain'


def test_client_requires_both_preserved_evidence_arguments(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(capacity_client, '_rpc', lambda path, message, timeout: (sent.append(message), None))
    for arguments in [dict(request_id='job'), dict(preserved_terminal=tmp_path / 'receipt.json')]:
        with pytest.raises(wire.CapacityError, match='both request ID'):
            capacity_client.reconcile('/unused', **arguments)
    capacity_client.reconcile('/unused', request_id='job', preserved_terminal=tmp_path / 'receipt.json')
    assert sent == [dict(action='reconcile', preserved_terminal=dict(request_id='job', path=str(tmp_path / 'receipt.json'))) ]


@pytest.mark.parametrize('arguments', [
    ['reconcile', '/unused', '--request-id', 'job'],
    ['reconcile', '/unused', '--preserved-terminal', '/archive'],
    ['status', '/unused', '--request-id', 'job', '--preserved-terminal', '/archive'],
])
def test_cli_preserved_evidence_options_require_reconcile_and_pair(arguments):
    from atelier import cli
    with pytest.raises(SystemExit, match='must be used together'):
        cli.main(['capacity', *arguments])


def test_cli_passes_explicit_preservation_attestation(monkeypatch, capsys):
    from atelier import cli
    received = []
    def reconcile(path, **kwargs):
        received.append((path, kwargs))
        return {'charged_count': 0}
    monkeypatch.setattr(capacity_client, 'reconcile', reconcile)
    assert cli.main(['capacity', 'reconcile', '/socket', '--request-id', 'job', '--preserved-terminal', '/archive']) == 0
    assert received == [('/socket', dict(request_id='job', preserved_terminal='/archive'))]
    assert 'charged_count' in capsys.readouterr().out


@pytest.mark.parametrize('action', ['reconcile', 'close', 'preserved'])
def test_recovery_commits_before_disposal_and_reconcile_is_idempotent(terminal, action):
    broker, record, bound_path, receipt = terminal
    broker.compatible, broker.lease_seconds, broker.boot = True, 10, 'fixture'
    broker._watches, broker._gates, broker._lock = {}, {}, threading.RLock()
    broker._clock = lambda: 20
    broker.total, broker.reserve = Resources(memory_mib=10), Resources()
    record['epoch'] = 1
    archive = bound_path.with_name('preserved.json')
    if action == 'preserved':
        archive.write_text(json.dumps(receipt))
        bound_path.write_text(json.dumps(receipt | {'owner': 999}))
    if action == 'close':
        record['exited'] = record['exited'][1:]
        broker.started = lambda pid: pid * 10
        broker.alive = lambda pin: pin == (99, 990)
    broker.connection = sqlite3.connect(':memory:', isolation_level=None)
    broker.connection.execute(SCHEMA)
    state = dict(namespace=wire.NAMESPACE, epoch=1, boot_id=broker.boot, records={'job': record})
    broker.connection.execute('INSERT INTO state VALUES (1,?)', (json.dumps(state),))
    disposed = []
    def dispose(nonce):
        assert not broker.connection.in_transaction
        durable = json.loads(broker.connection.execute('SELECT value FROM state').fetchone()[0])
        assert durable['records']['job']['state'] == 'released'
        assert durable['records']['job']['release_witness']['kind'] == 'guarded-tree-exit'
        disposed.append(nonce)
    broker._dispose = dispose
    try:
        for _ in range(1 if action == 'close' else 2):
            message = dict(namespace=wire.NAMESPACE, action='reconcile' if action == 'preserved' else action)
            if action == 'preserved':
                message['preserved_terminal'] = dict(request_id='job', path=str(archive))
            if action == 'close':
                message.update(id='job', nonce='fixture', epoch=1, boot_id=broker.boot,
                               witness=dict(kind='direct-parent-wait', parent=[99, 990], child=[100, 1000], returncode=0))
            result, _ = broker.handle(message, (99, 990))
            if action == 'close':
                assert result['released'] is True and result['coverage'] == 'monitored-owned-tree'
            else:
                assert result['charged_count'] == 0 and not result['recovering']
        assert disposed == ['fixture']
    finally:
        broker.connection.close()
