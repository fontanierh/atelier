"""Aggregate accounting must keep ownership across exit/exec without touching shared services."""
from types import SimpleNamespace

from atelier.harness.safety.tree_guard import OwnedTree


class Processes:
    def __init__(self):
        self.rows = {}

    def add(self, pid, parent, name, footprint, started=None):
        self.rows[pid] = SimpleNamespace(parent=parent, name=name, footprint=footprint,
                                         started=started or pid * 100, exited=0)

    def started(self, pid):
        return self.rows[pid].started if pid in self.rows else None

    def name(self, pid):
        return self.rows[pid].name if pid in self.rows else ''

    def owned_children(self, pid, started):
        return [(p, v.started) for p, v in self.rows.items() if v.parent == pid] if self.started(pid) == started else []

    def usage(self, pid):
        if pid not in self.rows:
            raise ProcessLookupError(pid)
        return self.rows[pid]


def test_counts_both_game_trees_from_first_discovery_and_keeps_orphan_ownership():
    api = Processes()
    api.add(1, 0, 'python', 10)
    api.add(2, 1, 'UnrealEditor', 200)
    api.add(3, 1, 'UnrealEditor', 300)
    api.add(4, 2, 'dotnet', 40)
    tree = OwnedTree(api, 1, 100)
    assert sum(p['footprint_bytes'] for p in tree.sample()) == 550
    del api.rows[2]
    api.rows[4].parent = 0
    api.add(5, 4, 'sh', 50)
    assert sum(p['footprint_bytes'] for p in tree.sample()) == 400
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent.index(5) < sent.index(4) < sent.index(1)
    assert set(sent) == {1, 3, 4, 5}


def test_reused_pid_and_its_new_children_are_never_counted_or_signalled():
    api = Processes()
    api.add(1, 0, 'python', 10)
    api.add(2, 1, 'UnrealEditor', 200)
    tree = OwnedTree(api, 1, 100)
    tree.sample()
    api.add(2, 0, 'UnrealEditor', 900, started=999)
    api.add(3, 2, 'dotnet', 300)
    assert sum(p['footprint_bytes'] for p in tree.sample()) == 10
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]


def test_shell_execing_shared_service_excludes_its_already_recorded_descendants():
    api = Processes()
    api.add(1, 0, 'python', 10)
    api.add(2, 1, 'sh', 200)
    api.add(3, 2, 'helper', 300)
    tree = OwnedTree(api, 1, 100)
    assert sum(p['footprint_bytes'] for p in tree.sample()) == 510
    api.rows[2].name = 'zenserver'
    assert sum(p['footprint_bytes'] for p in tree.sample()) == 10
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid))
    assert sent == [1]


def test_monitor_can_finish_cleanup_before_exiting_itself():
    api = Processes()
    api.add(1, 0, 'python', 10)
    api.add(2, 1, 'python', 20)  # independent aggregate monitor
    api.add(3, 1, 'UnrealEditor', 300)
    tree = OwnedTree(api, 1, 100)
    tree.sample()
    sent = []
    tree.stop_owned(lambda pid, sig: sent.append(pid), exclude_pid=2)
    assert sent == [3, 1]


def test_cleanup_skips_departed_history_before_scanning_shared_ancestry():
    class CountedProcesses(Processes):
        calls = 0

        def started(self, pid):
            self.calls += 1
            return super().started(pid)

    api = CountedProcesses()
    api.add(1, 0, 'launcher', 10)
    api.add(2, 1, 'helper', 20)
    api.add(3, 2, 'helper', 30)
    departed = range(100, 1100)
    for pid in departed:
        api.add(pid, 1, 'compiler', 40)
    tree = OwnedTree(api, 1, 100)
    tree.sample()
    history = dict(tree.parents)
    for pid in (1, *departed):
        del api.rows[pid]
    api.rows[2].parent = 0  # Retained ownership survives the launcher's exit.
    api.calls = 0
    sent = []

    def exited(pid, signal):
        sent.append(pid)
        del api.rows[pid]

    tree.stop_owned(exited)
    assert sent == [3, 2]
    assert api.calls < 5 * len(history), 'departed compiler history must not cause quadratic OS queries'
    assert tree.parents == history, 'cleanup must retain pinned ancestry, including departed parents'
    assert tree.sample() == []


def test_cleanup_rechecks_identity_after_shared_ancestry_scan(monkeypatch):
    api = Processes()
    api.add(1, 0, 'launcher', 10)
    api.add(2, 1, 'helper', 20)
    tree = OwnedTree(api, 1, 100)
    tree.sample()
    name = api.name

    def reused_during_scan(pid):
        result = name(pid)
        if pid == 2:
            api.add(2, 0, 'foreign', 900, started=999)
        return result

    monkeypatch.setattr(api, 'name', reused_during_scan)
    sent = []
    tree.stop_owned(lambda pid, signal: sent.append(pid))
    assert api.rows[2].started == 999
    assert sent == [1], 'a pin that matched the fast filter can be reused before signalling'


def test_cleanup_refreshes_shared_ancestry_between_live_candidates():
    api = Processes()
    api.add(1, 0, 'launcher', 10)
    api.add(2, 1, 'sh', 20)
    api.add(3, 2, 'helper', 30)
    api.add(4, 2, 'helper', 40)
    tree = OwnedTree(api, 1, 100)
    tree.sample()
    sent = []

    def exited(pid, signal):
        sent.append(pid)
        del api.rows[pid]
        if pid == 3:
            api.rows[2].name = 'zenserver'
            api.add(5, 2, 'shared-helper', 50)

    tree.stop_owned(exited)
    assert sent == [3, 1]
    assert set(api.rows) == {2, 4, 5}, 'a new shared service and its children must survive cleanup'


def test_terminal_receipt_reports_the_post_cleanup_sample(tmp_path, monkeypatch):
    import json
    from atelier.harness.safety import tree_guard
    before = [dict(pid=2, started=20, footprint_bytes=77, name='helper', depth=1)]
    samples = iter((before, []))
    tree = SimpleNamespace(root=(1, 10), same=lambda pin: True, sample=lambda: next(samples))
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate: candidate is tree)
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(1, 10, path) == 0
    value = json.loads(path.read_text())
    assert value['state'] == 'child_exited' and value['cleanup_complete'] is True
    assert value['processes'] == [] and value['footprint_bytes'] == 0
    assert value['peak_bytes'] == 77


def test_new_survivor_after_cleanup_cannot_publish_success(tmp_path, monkeypatch):
    import json
    from atelier.harness.safety import tree_guard
    before = [dict(pid=2, started=20, footprint_bytes=77, name='helper', depth=1)]
    after = [dict(pid=3, started=30, footprint_bytes=88, name='helper', depth=2)]
    samples = iter((before, after))
    tree = SimpleNamespace(root=(1, 10), same=lambda pin: True, sample=lambda: next(samples))
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate: True)
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(1, 10, path) == 1
    value = json.loads(path.read_text())
    assert value['state'] == 'cleanup_incomplete' and value['cleanup_complete'] is False
    assert value['processes'] == after and value['footprint_bytes'] == 88
    assert value['peak_bytes'] == 88 and value['termination_reason'] == 'child_exited'


def test_stop_receipts_preserve_the_offending_pre_cleanup_sample(tmp_path, monkeypatch):
    import json
    from atelier.harness.safety import tree_guard
    for state, options in [('memory_limit', dict(limit_gib=1e-8)), ('test_duration', dict(duration=0))]:
        before = [dict(pid=2, started=20, footprint_bytes=77, name='helper', depth=1)]
        samples = iter((before, []))
        tree = SimpleNamespace(root=(1, 10), same=lambda pin: True, sample=lambda: next(samples))
        monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
        monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate: True)
        path = tmp_path / (state + '.json')
        assert tree_guard.run_child(1, 10, path, **options) == 1
        value = json.loads(path.read_text())
        assert value['state'] == state and value['cleanup_complete'] is True
        assert value['processes'] == before and value['footprint_bytes'] == 77 and value['peak_bytes'] == 77
        assert value['cleanup_processes'] == [] and value['cleanup_footprint_bytes'] == 0



def test_zombie_controller_is_treated_as_lost(monkeypatch):
    from atelier.harness.safety import tree_guard,process_tree
    monkeypatch.setattr(process_tree,'usage',lambda pid:SimpleNamespace(started=100,exited=1))
    assert not tree_guard.controller_live((1,100))
    monkeypatch.setattr(process_tree,'usage',lambda pid:SimpleNamespace(started=101,exited=0))
    assert not tree_guard.controller_live((1,100))
