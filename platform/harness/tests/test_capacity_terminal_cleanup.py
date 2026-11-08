"""Exclusive monitored-tree cleanup can resolve historical discovery gaps without invented exits."""
from dataclasses import asdict
import json
import hashlib
import sqlite3
import threading
import time

import pytest

from atelier.harness import capacity_protocol as wire
from atelier.harness import capacity_client
from atelier.harness.capacity import Resources
from atelier.harness.capacity_broker import CapacityBroker, SCHEMA


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
    broker._queue_status = broker._advisory_budget = None
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


@pytest.mark.parametrize('bad', [None, 'controller', 'missing-late', 'unresolved', 'scan-failed',
    'nonempty', 'missing-root-exit', 'live-tail', 'stopped', 'wrong-owner', 'wrong-limit', 'stale'])
def test_shared_editor_releases_only_its_bound_normal_empty_tree(terminal, bad):
    broker, record, path, receipt = terminal
    broker.mode = 'capacity'
    record['request'].update(shared_editor=True, phase='job')
    receipt.update(controller=record['principal'], late_reporters=dict(
        adopted=[], unresolved=[], unresolved_pids=[], scan_failed=False))
    if bad == 'controller': receipt['controller'] = [1, 2]
    elif bad == 'missing-late': del receipt['late_reporters']
    elif bad == 'unresolved': receipt['late_reporters']['unresolved_pids'] = [200]
    elif bad == 'scan-failed': receipt['late_reporters']['scan_failed'] = True
    elif bad == 'nonempty': receipt.update(processes=[{'pid': 1}], footprint_bytes=1)
    elif bad == 'missing-root-exit': record['exited'] = record['exited'][1:]
    elif bad == 'live-tail': broker.alive = lambda pin: pin == tuple(record['roster'][-1])
    elif bad == 'stopped': receipt['state'] = 'controller_exited'
    elif bad == 'wrong-owner': receipt['owner_started'] += 1
    elif bad == 'wrong-limit': receipt['limit_bytes'] += 1
    elif bad == 'stale': receipt['time'] = 1
    path.write_text(json.dumps(receipt))
    assert broker._settle_exited(record) is (bad is None)
    if bad is None:
        assert record['release_witness']['kind'] == 'shared-editor-exit'
        assert len(record['exited']) == 32 and record['ancestry_unknown']
        assert broker._check_completion(record)['terminal']
    else:
        assert record['state'] == 'uncertain'


def stopped_receipt(record, receipt, reason):
    footprint = record['limit_bytes'] + 1 if reason == 'memory_limit' else 77
    return receipt | dict(state=reason, footprint_bytes=footprint, peak_bytes=footprint,
                          processes=[dict(pid=100, started=1000, footprint_bytes=footprint)],
                          cleanup_processes=[], cleanup_footprint_bytes=0)


@pytest.mark.parametrize('reason', ['memory_limit', 'test_duration'])
def test_guard_stop_releases_capacity_without_successful_completion(terminal, reason):
    broker, record, path, receipt = terminal
    broker.mode = 'capacity'
    record['request']['performance'] = True
    path.write_text(json.dumps(stopped_receipt(record, receipt, reason)))
    assert broker._tree_end_observation(record, pending=True) is None
    assert broker._settle_exited(record)
    assert record['release_witness']['kind'] == 'guarded-tree-stop'
    assert record['state'] == 'released' and len(record['exited']) == 32
    assert broker._check_completion(record) is None  # Resource release is not native success.


@pytest.mark.parametrize('reason', ['memory_limit', 'test_duration'])
@pytest.mark.parametrize('bad', ['cleanup', 'missing-cleanup', 'cleanup-bytes', 'bool-bytes', 'sum',
                                 'negative', 'duplicate', 'peak', 'state', 'root', 'birth', 'limit',
                                 'time', 'missing-root-exit', 'live-retained', 'not-exclusive'])
def test_guard_stop_never_loosens_exit_and_cleanup_proof(terminal, reason, bad):
    broker, record, path, receipt = terminal
    broker.mode = 'capacity'
    record['request']['performance'] = True
    stopped = stopped_receipt(record, receipt, reason)
    if bad == 'cleanup':
        stopped['cleanup_processes'] = [dict(pid=100, started=1000)]
    elif bad == 'missing-cleanup':
        del stopped['cleanup_processes']
    elif bad == 'cleanup-bytes':
        stopped['cleanup_footprint_bytes'] = 1
    elif bad == 'bool-bytes':
        stopped['cleanup_footprint_bytes'] = False
    elif bad == 'sum':
        stopped['footprint_bytes'] += 1
    elif bad == 'negative':
        stopped['processes'][0]['footprint_bytes'] = -1
    elif bad == 'duplicate':
        stopped['processes'] *= 2
    elif bad == 'peak':
        stopped['peak_bytes'] = 0
    elif bad == 'state':
        stopped['state'] = 'cleanup_incomplete'
    elif bad in ('root', 'birth', 'limit'):
        stopped[{'root': 'owner', 'birth': 'owner_started', 'limit': 'limit_bytes'}[bad]] += 1
    elif bad == 'time':
        stopped['time'] = 1
    elif bad == 'missing-root-exit':
        record['exited'] = record['exited'][1:]
    elif bad == 'live-retained':
        broker.alive = lambda pin: pin == tuple(record['roster'][-1])
    elif bad == 'not-exclusive':
        record['request']['performance'] = False
    path.write_text(json.dumps(stopped))
    assert not broker._settle_exited(record)
    assert record['state'] == 'uncertain'


def test_pre_cleanup_tail_requires_actual_retained_positive_exit(terminal):
    broker, record, path, receipt = terminal
    tail = record['roster'][2]
    sample = dict(pid=tail[0], started=tail[1], footprint_bytes=77, name='any-helper', depth=5)
    path.write_text(json.dumps(receipt | dict(processes=[sample], footprint_bytes=77)))
    original_exits = list(record['exited'])
    assert broker._settle_exited(record)
    assert record['release_witness']['kind'] == 'guarded-tree-exit'
    assert record['exited'] == original_exits and record['ancestry_unknown'] is True


@pytest.mark.parametrize('bad', ['unretained', 'unwitnessed', 'reused', 'duplicate', 'root',
                                'live', 'negative', 'bool', 'sum', 'missing', 'over-limit'])
def test_pre_cleanup_tail_never_uses_absence_or_names_as_exit_proof(terminal, bad):
    broker, record, path, receipt = terminal
    tail = record['roster'][2]
    sample = dict(pid=tail[0], started=tail[1], footprint_bytes=77, name='ibtoold', depth=5)
    if bad == 'unretained':
        record['roster'].remove(tail)
    elif bad == 'unwitnessed':
        record['exited'].remove(tail)
    elif bad == 'reused':
        sample['started'] += 1
    elif bad == 'root':
        sample.update(pid=record['child'][0], started=record['child'][1])
    elif bad == 'live':
        broker.alive = lambda pin: pin == tuple(tail)
    elif bad == 'negative':
        sample['footprint_bytes'] = -1
    elif bad == 'bool':
        sample['footprint_bytes'] = True
    elif bad == 'missing':
        del sample['started']
    elif bad == 'over-limit':
        sample['footprint_bytes'] = record['limit_bytes'] + 1
    samples = [sample, sample] if bad == 'duplicate' else [sample]
    total = sample['footprint_bytes'] if bad == 'over-limit' else 78 if bad == 'sum' else 77
    value = receipt | dict(processes=samples, footprint_bytes=total)
    path.write_text(json.dumps(value))
    assert not broker._settle_exited(record)
    assert record['state'] == 'uncertain'


@pytest.mark.parametrize('mode', ['capacity', 'sealed-maintenance'])
def test_old_terminal_sample_still_requires_exclusive_admission(terminal, mode):
    broker, record, path, receipt = terminal
    tail = record['roster'][2]
    path.write_text(json.dumps(receipt | dict(processes=[dict(pid=tail[0], started=tail[1], footprint_bytes=77)],
                                             footprint_bytes=77)))
    broker.mode = mode
    assert not broker._settle_exited(record)
    record['request']['performance'] = True
    assert broker._settle_exited(record)


@pytest.mark.parametrize('mode', ['capacity', 'sealed-maintenance'])
@pytest.mark.parametrize('performance,allowed', [(False, False), (True, True)])
def test_full_mode_requires_performance_exclusion(terminal, performance, allowed, mode):
    broker, record, _, _ = terminal
    broker.mode = mode
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
    broker.directory = bound_path.parent
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
    def dispose():
        assert not broker.connection.in_transaction
        durable = json.loads(broker.connection.execute('SELECT value FROM state').fetchone()[0])
        assert durable['records']['job']['state'] == 'released'
        assert durable['records']['job']['release_witness']['kind'] == 'guarded-tree-exit'
        disposed.append('fixture')
    class Handle:
        def poll(self):
            return False
        def close(self):
            dispose()
    broker._watches[('fixture', (100, 1000))] = Handle()
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


@pytest.mark.parametrize('damage', [None, 'missing-candidate', 'compatibility', 'lease', 'stale-wall',
    'stale-monotonic', 'future-monotonic', 'wrong-owner', 'wrong-birth', 'memory-stop', 'nonempty',
    'footprint', 'incomplete', 'ceiling', 'stop-reason', 'missing-report', 'symlink-report'])
def test_finish_hint_requires_fresh_clean_bound_report_and_never_releases(terminal, damage):
    broker, record, path, receipt = terminal
    broker.compatible = True; broker.lease_seconds = 30; broker._clock = time.monotonic
    record['heartbeat'] = time.monotonic(); record['guard_completion_candidate'] = True
    record['exited'].remove(record['child'])  # The hint MUST NOT stand in for affirmative root exit.
    receipt.update(time=time.time(), observed_monotonic=time.monotonic())
    changes = {'stale-wall': {'time': time.time()-10}, 'stale-monotonic': {'observed_monotonic': time.monotonic()-10},
        'future-monotonic': {'observed_monotonic': time.monotonic()+10}, 'wrong-owner': {'owner': 101},
        'wrong-birth': {'owner_started': 1001}, 'memory-stop': {'state': 'memory_limit'},
        'nonempty': {'processes': [{'pid': 100}]}, 'footprint': {'footprint_bytes': 1},
        'incomplete': {'cleanup_complete': False}, 'ceiling': {'limit_bytes': 2},
        'stop-reason': {'termination_reason': 'memory_limit'}}
    receipt.update(changes.get(damage, {})); path.write_text(json.dumps(receipt))
    if damage == 'missing-candidate': record.pop('guard_completion_candidate')
    if damage == 'compatibility': broker.compatible = False
    if damage == 'lease': record['heartbeat'] -= 60
    if damage == 'missing-report': path.unlink()
    if damage == 'symlink-report':
        other = path.with_suffix('.saved'); path.rename(other); path.symlink_to(other)
    result = broker._check_completion(record)
    assert (result is not None) is (damage is None)
    if result is not None:
        assert result == dict(state='uncertain', admission=False, finish_required=True, child=record['child'])
    assert record['state'] == 'uncertain' and record['child'] not in record['exited']
    assert not broker._settle_exited(record)


def test_released_check_requires_an_existing_positive_release_witness(terminal):
    broker, record, _, _ = terminal
    assert broker._settle_exited(record)
    result = broker._check_completion(record)
    assert result == dict(state='released', admission=False, terminal=True, child=record['child'])
    record['release_witness'] = {'kind': 'os-boot-change'}
    assert broker._check_completion(record) is None


@pytest.mark.parametrize('arrives', ['aggregate', 'root', 'neither'])
def test_monitor_publication_lag_gets_one_bounded_charged_reconciliation(terminal, monkeypatch, arrives):
    broker, record, path, receipt = terminal
    broker.compatible = True; broker.lease_seconds = 30; broker._clock = time.monotonic
    record['heartbeat'] = time.monotonic(); record['guard_completion_candidate'] = True
    record['exited'].remove(record['child'])
    receipt.update(time=time.time(), observed_monotonic=time.monotonic(), state='running', cleanup_complete=False)
    path.write_text(json.dumps(receipt))
    original = broker._tree_end_observation
    calls = []
    def observation(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(True)
        if len(calls) == 1 and arrives == 'aggregate':
            # Publish only AFTER the initial read found the running report.
            final = receipt | dict(state='child_exited', cleanup_complete=True)
            path.write_text(json.dumps(final))
        return result
    monkeypatch.setattr(broker, '_tree_end_observation', observation)
    def root_exited(_):
        if arrives == 'root':
            record['exited'].append(record['child'])
            return True
        return False
    monkeypatch.setattr(broker, '_root_exited', root_exited)
    before = time.monotonic()
    result = broker._check_completion(record, reconcile=True)
    assert time.monotonic() - before < 1
    assert record['completion_reconciled'] is True
    if arrives == 'aggregate':
        assert result['finish_required'] is True and result['admission'] is False
        assert record['state'] == 'uncertain' and record['child'] not in record['exited']
    elif arrives == 'root':
        assert result is None and record['state'] == 'draining'
        assert record['child'] in record['exited']
    else:
        assert result is None and record['state'] == 'uncertain'
        before = time.monotonic()
        assert broker._check_completion(record, reconcile=True) is None
        assert time.monotonic() - before < .1  # Never renew the reconciliation window.
    assert record['state'] != 'released'  # Nothing here clears capacity or certifies outputs.
