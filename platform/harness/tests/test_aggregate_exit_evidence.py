"""The aggregate monitor's own kernel exit watches: producer binding, receipt parsing and broker consumption."""
import json
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from atelier.harness import capacity_client as client
from atelier.harness import capacity_protocol as wire
from atelier.harness.safety import tree_guard

from test_capacity_broker import broker_factory, complete, gated_child, session, short_path  # noqa: F401

darwin = pytest.mark.skipif(sys.platform != 'darwin', reason='the aggregate monitor binds kqueue exit watches on macOS')
ME = (os.getpid(), wire.process_start(os.getpid()))


def held():
    process = subprocess.Popen([sys.executable, '-c', 'import sys; sys.stdin.buffer.read(1)'], stdin=subprocess.PIPE)
    return process, (process.pid, wire.process_start(process.pid))


def end(process):
    process.communicate(input=b'x', timeout=3)


def settle(watches, expected, deadline=3.):
    stop = time.monotonic() + deadline
    while time.monotonic() < stop:
        found, omitted = watches.evidence()
        if len(found) + omitted >= expected:
            return found, omitted
        time.sleep(.01)
    return watches.evidence()


@darwin
def test_a_watch_bound_while_live_keeps_its_exit_and_edge_after_reap():
    watches = tree_guard.ExitWatches(wire.process_start)
    process, pin = held()
    watches.bind(pin, ME)
    end(process)  # reaped: the PID may now be reused, the fired identity stays exact
    assert settle(watches, 1) == ([[*pin, *ME]], 0)


@darwin
def test_missing_raced_or_reused_identities_stay_unknown():
    watches = tree_guard.ExitWatches(wire.process_start)
    gone, gone_pin = held()
    end(gone)
    watches.bind(gone_pin, ME)  # already reaped: never registered
    live, live_pin = held()
    watches.bind((live_pin[0], live_pin[1] + 1), ME)  # another start for this PID: never registered
    raced = tree_guard.ExitWatches(lambda pid, starts=iter([live_pin[1], None]): next(starts))
    raced.bind(live_pin, ME)  # identity changed across registration: deleted, never published
    watches.bind(live_pin, None)  # the root has no discovered edge; the broker watches it directly
    end(live)
    time.sleep(.2)
    assert watches.evidence() == ([], 0) and raced.evidence() == ([], 0)
    assert not watches.watched and not raced.watched


@darwin
def test_a_burst_beyond_the_window_counts_older_exits_as_omitted():
    watches = tree_guard.ExitWatches(wire.process_start)
    count = tree_guard.ExitWatches.WINDOW + 6
    processes = [held() for _ in range(count)]
    for _, pin in processes:
        watches.bind(pin, ME)
    for process, _ in processes:
        end(process)
    found, omitted = settle(watches, count)
    assert len(found) == tree_guard.ExitWatches.WINDOW and omitted == 6
    assert {tuple(item[:2]) for item in found} <= {pin for _, pin in processes}


def test_owned_tree_binds_each_new_child_with_its_discovery_edge():
    bound = []
    watches = SimpleNamespace(drain=lambda: bound.append('drain'), bind=lambda pin, parent: bound.append((pin, parent)))
    children = {(1, 10): [(2, 20)], (2, 20): [(3, 30)]}
    api = SimpleNamespace(started=lambda pid: pid * 10, owned_children=lambda pid, start: children.get((pid, start), []),
                          name=lambda pid: 'tool', usage=lambda pid: SimpleNamespace(started=pid * 10, exited=0, footprint=1))
    tree = tree_guard.OwnedTree(api, 1, 10, exits=watches)
    samples = tree.sample()
    tree.sample()
    assert [b for b in bound if b != 'drain'] == [((2, 20), (1, 10)), ((3, 30), (2, 20))]
    assert bound[0] == 'drain'
    assert {(s['pid'], tuple(s['parent']) if s['parent'] else None) for s in samples} == {
        (1, None), (2, (1, 10)), (3, (2, 20))}


def test_receipt_evidence_parses_exactly_or_refuses():
    record = {'processes': [{'pid': 2, 'started': 20, 'parent': [1, 10]}, {'pid': 1, 'started': 10, 'parent': None}],
              'exits': [[3, 30, 2, 20]]}
    assert wire.guard_evidence(record) == ((((2, 20), (1, 10)),), (((3, 30), (2, 20)),))
    assert wire.guard_evidence({'processes': [{'pid': 2, 'started': 20}]}) == ((), ())  # old receipts: no evidence
    for exits in ([[3, 30, 2]], [{'pid': 3}], 'x', [[3, 30, 2, 20]] * (wire.MAX_ROSTER + 1), [[3, -1, 2, 20]]):
        with pytest.raises(wire.CapacityError):
            wire.guard_evidence({'processes': [], 'exits': exits})


def reaped():
    process, pin = held()
    end(process)
    return pin


@pytest.mark.parametrize('evidence', ['live', 'terminal', 'none', 'other-parent', 'unretained', 'unverified-parent'])
def test_reaped_helper_releases_only_with_the_aggregate_monitors_exact_exit(broker_factory, short_path, evidence):
    helper = reaped()  # discovered by the monitor, gone before the broker's own watch or parent read
    facts = [wire.GuardFacts((), 0)]
    broker = broker_factory(guards=lambda *args: facts[0])
    admission = session(broker)
    admission.offer()
    child = gated_child(admission, hold=True)
    root = (child.pid, wire.process_start(child.pid))
    receipt = short_path / 'tree.json'
    admission.start(child_pid=child.pid, child_start=root[1], process_guard={},
                    tree_guard={'pid': ME[0], 'start': ME[1], 'report': str(receipt)}, limit_bytes=128 * 1024**2)
    facts[0] = wire.GuardFacts((helper,), 0)
    admission.check()
    exit_entry = {'live': (helper, root), 'terminal': (helper, root), 'none': None,
                  'other-parent': (helper, ME), 'unretained': (reaped(), root),
                  'unverified-parent': (helper, (root[0], root[1] + 1))}[evidence]
    if evidence == 'live':
        facts[0] = wire.GuardFacts((), 0, (), (exit_entry,))
        admission.check()
    receipt.write_text(json.dumps({'owner': root[0], 'owner_started': root[1], 'limit_bytes': 128 * 1024**2,
                                   'state': 'child_exited', 'processes': [],
                                   'exits': [[*exit_entry[0], *exit_entry[1]]] if evidence != 'live' and exit_entry else []}))
    if evidence in ('live', 'terminal'):
        assert complete(admission, child, root[1])['released'] is True
        record = client.status(broker.socket_path)
        assert record['charged_count'] == 0
    else:
        with pytest.raises(wire.CapacityError, match='uncertain'):
            complete(admission, child, root[1])
        status = client.reconcile(broker.socket_path)
        assert status['charged_count'] == 1 and status['records'][0]['ancestry_unknown']
