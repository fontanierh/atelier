"""The aggregate monitor's own kernel exit watches: producer binding, receipt parsing and broker consumption."""
import json
import select
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


class Dead:
    """A broker watch that lost the race: bound too late, so it never fires."""
    def __init__(self, pin):
        self.pin = pin
    def poll(self):
        return False
    def close(self):
        pass


def test_a_verified_pins_retained_parent_refuses_conflicting_or_duplicate_evidence(broker_factory):
    root, helper, other = (200, 2000), (201, 2010), (202, 2020)
    broker = broker_factory(watch=Dead, parent=lambda pin: {helper: root}.get(pin))
    record = {'principal': [100, 1000], 'child': list(root), 'nonce': 'n', 'request': {}}
    broker._watch(record, [root, helper])  # the broker read helper -> root itself while it was live
    assert sorted(map(tuple, record['verified_roster'])) == [root, helper] and not record['ancestry_unknown']
    for exits, edges in [(((helper, other),), ()),                     # another parent for a verified pin
                         (((helper, root), (helper, root)), ()),       # duplicate exit evidence
                         (((helper, root),), ((helper, other),))]:      # the receipt's own edge disagrees
        broker._watch(record, [], edges=edges, exits=exits)
        assert record.get('exited', []) == []
    broker._watch(record, [], exits=((helper, root),))
    assert record['exited'] == [list(helper)]
    legacy = {'principal': [100, 1000], 'child': list(root), 'nonce': 'm', 'request': {},
              'roster': [list(root), list(helper)], 'verified_roster': [list(root), list(helper)]}
    broker._watch(legacy, [], exits=((helper, root),))  # verified before parents were retained: unknown
    assert legacy.get('exited', []) == []


class FakeQueue:
    def __init__(self):
        self.registered, self.events = {}, []
    def control(self, changes, maxevents, timeout):
        for change in changes or ():
            if change.flags & select.KQ_EV_DELETE:
                self.registered.pop(change.ident, None)
            else:
                self.registered[change.ident] = change.fflags
        if changes:
            return []
        events, self.events = self.events[:maxevents], self.events[maxevents:]
        return events
    def fire(self, pid):
        assert self.registered.pop(pid) & select.KQ_NOTE_EXIT
        self.events.append(SimpleNamespace(ident=pid, fflags=select.KQ_NOTE_EXIT, flags=0))
    def close(self):
        pass


@darwin
@pytest.mark.parametrize('old_fired', [False, True])
def test_a_reused_pid_never_inherits_the_earlier_identitys_watch_or_exit(old_fired):
    starts = {5: 50}
    watches = tree_guard.ExitWatches(starts.get)
    watches.queue.close()
    watches.queue = queue = FakeQueue()
    parent = (1, 10)
    watches.bind((5, 50), parent)
    if old_fired:
        queue.fire(5)  # the earlier identity exited; its event is still unretrieved
    else:
        queue.registered.pop(5)  # its registration was lost: it must stay unknown
    starts[5] = 51  # the PID is reused by a new process
    watches.bind((5, 51), parent)
    assert watches.watched[5][0] == (5, 51)
    queue.fire(5)
    found, omitted = watches.evidence()
    assert found == ([[5, 50, *parent]] if old_fired else []) + [[5, 51, *parent]] and omitted == 0


def test_a_full_pretty_printed_roster_with_evidence_reads_within_the_durable_bound(tmp_path):
    child, owner, monitor = (90001, 19783708509809), (90000, 19783708509000), (90002, 19783708509900)
    limit = 12 * 1024**3
    processes = [dict(pid=91000 + i, started=19783708600000 + i, footprint_bytes=9_876_543_210,
                      name='clang-compiler-helper-name-xxxx', depth=3, parent=[child[0], child[1]])
                 for i in range(wire.MAX_ROSTER)]
    exits = [[92000 + i, 19783708700000 + i, *child] for i in range(tree_guard.ExitWatches.WINDOW)]
    tree = tmp_path / 'tree.json'
    tree_guard.write_report(tree, dict(owner=child[0], owner_started=child[1], time=time.time(),
                                       observed_monotonic=time.monotonic(), elapsed_seconds=1., footprint_bytes=1,
                                       peak_bytes=1, limit_bytes=limit, state='running', processes=processes,
                                       exits=exits, exits_omitted=0, controller=list(owner)))
    process = tmp_path / 'process.json'
    process.write_text(json.dumps({'time': time.time(), 'state': 'running', 'limit_bytes': limit,
                                   'pid': child[0], 'process_start': child[1]}))
    size = tree.stat().st_size
    assert wire.MAX_FRAME < size < wire.GUARD_REPORT_LIMIT  # the socket frame bound would have refused it
    guards = {name: {'pid': monitor[0], 'start': monitor[1], 'report': str(report)}
              for name, report in [('process_guard', process), ('tree_guard', tree)]}
    facts = wire.validate_guards(guards, child, owner, limit, 12 * 1024, started=lambda pid: monitor[1],
                                 child_of=lambda *args: True, alive=lambda pin: True)
    assert len(facts.roster) == wire.MAX_ROSTER and len(facts.edges) == wire.MAX_ROSTER
    assert len(facts.exits) == tree_guard.ExitWatches.WINDOW
    with pytest.raises(wire.CapacityError, match='exceeds its limit'):
        wire.decode(tree.read_bytes())  # frames keep MAX_FRAME
