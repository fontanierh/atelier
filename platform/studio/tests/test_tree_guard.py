"""Aggregate accounting must keep ownership across exit/exec without touching shared services."""
from types import SimpleNamespace

from atelier.safety.tree_guard import OwnedTree


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
