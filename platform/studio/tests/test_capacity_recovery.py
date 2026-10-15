"""Stopped controllers release witnessed exits without a manual recovery command."""
from types import SimpleNamespace
from dataclasses import asdict
import json
import sqlite3
import threading

import pytest

from atelier.capacity_broker import CapacityBroker
from atelier.capacity_broker import SCHEMA
from atelier.capacity import Resources
from atelier import capacity_protocol as wire


def broker_record(*, roster=None, exited=None, ancestry_unknown=False, state='uncertain'):
    root, helper = [101, 1001], [102, 1002]
    record = dict(state=state, roster=[root, helper] if roster is None else roster,
                  exited=[] if exited is None else exited, ancestry_unknown=ancestry_unknown,
                  nonce='fixture', principal=[100, 1000], child=root, heartbeat=0)
    broker = object.__new__(CapacityBroker)
    broker.mode = 'legacy-bridge'
    broker.compatible = True
    broker.lease_seconds = 10
    disposed = []
    broker._dispose = disposed.append
    broker._watches = {}
    return broker, record, disposed


def test_controller_interruption_recovers_from_every_bound_exit_watch():
    broker, record, disposed = broker_record()
    broker._watches = {('fixture', tuple(pin)): SimpleNamespace(poll=lambda: True)
                       for pin in record['roster']}
    assert broker._refresh({'records': {'job': record}}, 20)
    assert record['state'] == 'released'
    assert record['release_witness'] == {'kind': 'retained-kernel-exits'}
    assert disposed == []  # Watches are retained until the transaction commits.
    assert not broker._refresh({'records': {'job': record}}, 21)
    assert disposed == []


@pytest.mark.parametrize('changes', [
    {'roster': []},
    {'exited': [[101, 1001]]},  # Root exited, retained helper is unresolved.
    {'exited': [[101, 9999], [102, 1002]]},  # Reused PID is not the retained identity.
    {'exited': [[101, 1001], [102, 1002]], 'ancestry_unknown': True},
])
def test_uncertain_ownership_is_not_a_completed_job(changes):
    broker, record, disposed = broker_record(**changes)
    assert not broker._refresh({'records': {'job': record}}, 20)
    assert record['state'] == 'uncertain'
    assert disposed == []


def test_expired_controller_with_a_live_child_still_holds_capacity():
    broker, record, disposed = broker_record(state='running')
    assert broker._refresh({'records': {'job': record}}, 20)
    assert record['state'] == 'uncertain'
    assert disposed == []


def test_no_failed_process_lookup_is_needed_to_recover_known_exits():
    broker, record, disposed = broker_record(exited=[[101, 1001], [102, 1002]])
    broker.started = lambda pid: pytest.fail('PID lookup is not exit evidence')
    broker.alive = lambda pin: pytest.fail('PID lookup is not exit evidence')
    assert broker._refresh({'records': {'job': record}}, 20)
    assert record['state'] == 'released'
    assert disposed == []


def test_refused_rpc_preserves_exit_watches_until_recovery_commits():
    broker, record, disposed = broker_record()
    record.update(request=dict(id='job', resources=asdict(Resources(memory_mib=128, cpu_millis=1000)),
                               locks=[], seconds=60, performance=False), sequence=1, first_ready=1, bypasses=0)
    broker._watches = {('fixture', tuple(pin)): SimpleNamespace(poll=lambda: True)
                       for pin in record['roster']}
    def dispose(nonce):
        disposed.append(nonce)
        broker._watches.clear()
    broker._dispose = dispose
    broker._lock = threading.RLock()
    broker._clock = lambda: 20
    broker.boot = 'fixture-boot'
    broker.total = Resources(memory_mib=4096, cpu_millis=4000)
    broker.reserve = Resources()
    broker.connection = sqlite3.connect(':memory:', isolation_level=None)
    broker.connection.execute(SCHEMA)
    state = dict(namespace=wire.NAMESPACE, boot_id=broker.boot, epoch=1, records={'job': record})
    broker.connection.execute('INSERT INTO state VALUES (1,?)', (json.dumps(state),))
    try:
        # The final exit is observed before this malformed RPC is rejected and rolled back.
        with pytest.raises(wire.CapacityError, match='protocol fields'):
            broker.handle(dict(namespace=wire.NAMESPACE, action='status', invalid=True), (100, 1000))
        assert disposed == []
        assert broker._watches
        status, _ = broker.handle(dict(namespace=wire.NAMESPACE, action='status'), (100, 1000))
        assert status['charged_count'] == 0
        assert not status['recovering']
        assert disposed == ['fixture']
        assert not broker._watches
        durable = json.loads(broker.connection.execute('SELECT value FROM state').fetchone()[0])
        assert durable['records']['job']['release_witness'] == {'kind': 'retained-kernel-exits'}
    finally:
        broker.connection.close()
