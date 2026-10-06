"""Descendant discovery for guarded launchers: pinned identities, exec transitions and child guard failures.

Everything is mocked: no process is started and nothing is signalled.
"""
from contextlib import ExitStack, contextmanager

import pytest

from atelier.safety import guarded, process_tree


class Then(list):
    """Successive answers for one pid (a reused pid, an exec); the last one repeats."""


def world(monkeypatch, starts, kids, names):
    """A fake process table; a `Then` value answers differently on each call."""
    def answer(table, key, default):
        value = table.get(key, default)
        if isinstance(value, Then):
            return value.pop(0) if len(value) > 1 else value[0]
        return value
    monkeypatch.setattr(process_tree, 'started', lambda pid: answer(starts, pid, None))
    monkeypatch.setattr(process_tree, 'children', lambda pid: list(answer(kids, pid, [])))
    monkeypatch.setattr(process_tree, 'name', lambda pid: answer(names, pid, ''))


def test_a_reused_parent_pid_brings_in_no_children(monkeypatch):
    # The parent exits and its pid is reused while its children are listed.
    world(monkeypatch, starts={10: Then([100, 999]), 11: 150}, kids={10: [11]}, names={})
    assert process_tree.owned_children(10, 100) == []


def test_a_reused_child_pid_is_not_recorded(monkeypatch):
    # The child seen in the first listing exits; its pid is another process by the time it is checked again.
    world(monkeypatch, starts={10: 100, 11: Then([150, 777])}, kids={10: [11]}, names={})
    assert process_tree.owned_children(10, 100) == []
    world(monkeypatch, starts={10: 100, 11: 150}, kids={10: [11]}, names={})
    assert process_tree.owned_children(10, 100) == [(11, 150)]


class Monitor:
    def __init__(self):
        self.code = None

    def poll(self):
        return self.code


def tracker(monkeypatch, tmp_path, attached):
    @contextmanager
    def attach(pid, report, duration, limit_gib=10., expected_start=None):
        monitor = Monitor()
        attached.append((pid, expected_start, monitor))
        yield monitor
    monkeypatch.setattr(guarded, 'attach_memory_guard', attach)
    stack = ExitStack()
    return stack, guarded.Descendants(10, 100, tmp_path, ('UnrealEditor-Cmd',), None, 10., stack)


def test_a_child_first_seen_as_sh_is_guarded_once_it_execs_the_cook(monkeypatch, tmp_path):
    # PID 77, start 300: the same identity is recorded as `sh`, then execs UnrealEditor-Cmd (review #1506).
    names = {77: Then(['sh', 'sh', 'UnrealEditor-Cmd'])}   # read once while walking, once when guarding
    world(monkeypatch, starts={10: 100, 77: 300}, kids={10: [77]}, names=names)
    attached = []
    stack, tree = tracker(monkeypatch, tmp_path, attached)
    with stack:
        tree.poll()
        assert attached == []
        tree.poll()
        assert [(pid, start) for pid, start, _ in attached] == [(77, 300)], 'expected start comes from validated discovery'
        tree.poll()
        assert len(attached) == 1, 'one guard per identity'


def test_a_watched_child_that_outlives_its_guard_fails_the_run(monkeypatch, tmp_path):
    world(monkeypatch, starts={10: 100, 77: 300}, kids={10: [77]}, names={77: 'UnrealEditor-Cmd'})
    attached = []
    stack, tree = tracker(monkeypatch, tmp_path, attached)
    with stack:
        tree.poll(); tree.check()
        attached[0][2].code = 1
        with pytest.raises(SystemExit):
            tree.check()
        # A guard that stopped its process at the limit is not an error here: the launcher's own exit reports it.
        world(monkeypatch, starts={10: 100, 77: None}, kids={10: []}, names={})
        tree.check()


def test_a_guard_is_not_attached_to_a_different_process_on_the_same_pid(tmp_path):
    import os
    from atelier.safety.guard import attach
    with attach(os.getpid(), tmp_path/'report.json', duration=1, expected_start=1) as monitor:
        assert monitor is None


def test_unwind_rechecks_identity_before_every_signal(monkeypatch, tmp_path):
    # Recorded as (77, 300); by the time it is signalled the pid belongs to another process.
    world(monkeypatch, starts={10: 100, 77: Then([300, 300, 999])}, kids={10: [77]}, names={77: 'sh'})
    sent = []
    monkeypatch.setattr(guarded.os, 'kill', lambda pid, number: sent.append((pid, number)))
    stack = ExitStack()
    tree = guarded.Descendants(10, 100, tmp_path, ('UnrealEditor-Cmd',), None, 10., stack)
    tree.poll()
    tree.unwind(grace=0)
    assert sent == [], 'a reused pid is never signalled'


def test_shared_engine_services_are_never_signalled(monkeypatch, tmp_path):
    # A cook (77) starts Zen (88); both are recorded, only the cook is stopped.
    world(monkeypatch, starts={10: 100, 77: 300, 88: 400}, kids={10: [77], 77: [88]},
          names={77: 'UnrealEditor-Cmd', 88: 'zenserver'})
    attached, sent = [], []
    stack, tree = tracker(monkeypatch, tmp_path, attached)
    monkeypatch.setattr(guarded.os, 'kill', lambda pid, number: sent.append(pid))
    with stack:
        tree.poll()
        assert (88, 400) in tree.depth and (88, 400) in tree.shared
        assert [pid for pid, _, _ in attached] == [77], 'shared services get no guard'
        tree.unwind(grace=0)
    assert 88 not in sent and 77 in sent


def test_an_orphaned_intermediate_still_brings_in_the_cook_it_starts(monkeypatch, tmp_path):
    # 77 is recorded under the root, then its parent link is lost (reparented); it later starts the cook 99.
    world(monkeypatch, starts={10: 100, 77: 300}, kids={10: [77]}, names={77: 'sh'})
    attached = []
    stack, tree = tracker(monkeypatch, tmp_path, attached)
    with stack:
        tree.poll()
        world(monkeypatch, starts={10: 100, 77: 300, 99: 500}, kids={10: [], 77: [99]}, names={77: 'sh', 99: 'UnrealEditor-Cmd'})
        tree.poll()
        assert (99, 500) in tree.depth and [pid for pid, _, _ in attached] == [99]


def test_a_recorded_shell_that_execs_a_shared_service_keeps_itself_and_its_children(monkeypatch, tmp_path):
    # Root 10 -> sh 11 -> worker 12 are recorded; 11 then execs zenserver with no further poll before cleanup (#1560).
    world(monkeypatch, starts={10: 100, 11: 110, 12: 120}, kids={10: [11], 11: [12]}, names={11: 'sh', 12: 'worker'})
    sent = []
    monkeypatch.setattr(guarded.os, 'kill', lambda pid, number: sent.append(pid))
    tree = guarded.Descendants(10, 100, tmp_path, ('UnrealEditor-Cmd',), None, 10., ExitStack())
    tree.poll()
    assert set(tree.depth) == {(11, 110), (12, 120)} and not tree.shared
    world(monkeypatch, starts={10: 100, 11: 110, 12: 120}, kids={10: [11], 11: [12]}, names={11: 'zenserver', 12: 'worker'})
    tree.unwind(grace=0)
    assert sent == [], 'neither the service nor anything under it is signalled'
