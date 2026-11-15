"""Descendant discovery for guarded launchers: pinned identities, exec transitions and child guard failures.

Everything is mocked: no process is started and nothing is signalled.
"""
from contextlib import ExitStack, contextmanager
import errno
import signal
from types import SimpleNamespace

import pytest

from atelier.harness.safety import guarded, memory_guard, process_tree


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
    names = {77: 'sh'}  # A process-table transition, independent of how often names are sampled.
    world(monkeypatch, starts={10: 100, 77: 300}, kids={10: [77]}, names=names)
    attached = []
    stack, tree = tracker(monkeypatch, tmp_path, attached)
    with stack:
        tree.poll()
        assert attached == []
        names[77] = 'UnrealEditor-Cmd'
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


@pytest.mark.parametrize('exited', [0, 900])
def test_finished_guard_distinguishes_live_child_from_unreaped_exit(monkeypatch, tmp_path, exited):
    """@cc [owner:fontanierh,label:safety] exited-descendant-monitor-race
    A clean monitor exit MUST still fail for a live child. A sampled exit MUST stop
    counting that identity as live even while the parent has not reaped its zombie.
    """
    samples = {10: SimpleNamespace(started=100, exited=0),
               77: SimpleNamespace(started=300, exited=0)}
    monkeypatch.setattr(process_tree, 'usage', samples.__getitem__)
    monkeypatch.setattr(process_tree, 'children', lambda pid: [77] if pid == 10 else [])
    monkeypatch.setattr(process_tree, 'name', lambda pid: 'UnrealEditor-Cmd' if pid == 77 else 'sh')
    sent, attached = [], []
    monkeypatch.setattr(guarded.os, 'kill', lambda pid, number: sent.append((pid, number)))
    stack, tree = tracker(monkeypatch, tmp_path, attached)
    with stack:
        tree.poll()
        assert len(attached) == 1
        # The monitor uses usage.exited and can finish before UAT reaps this same PID/start.
        samples[77].exited = exited
        attached[0][2].code = 0
        if not exited:
            with pytest.raises(SystemExit, match='exited before it'):
                tree.check()
        else:
            tree.check()
            tree.poll()
            tree.unwind(grace=0)
            assert len(attached) == 1
            assert process_tree.started(77) is None
            assert sent == [], 'an exited child cannot need cleanup signals'


def test_process_identity_sampling_failure_is_not_an_exit(monkeypatch):
    def unreadable(pid):
        raise PermissionError('process telemetry unavailable')
    monkeypatch.setattr(process_tree, 'usage', unreadable)
    with pytest.raises(PermissionError, match='telemetry unavailable'):
        process_tree.started(77)


@pytest.mark.parametrize('error', [errno.ESRCH, errno.EPERM, errno.EIO])
def test_darwin_identity_only_treats_missing_process_as_exited(monkeypatch, error):
    """The native sampler must preserve errno classification before identity checks handle absence."""
    monkeypatch.setattr(memory_guard, 'DARWIN', True)
    monkeypatch.setattr(memory_guard, 'LIB', SimpleNamespace(
        proc_pid_rusage=lambda *args: -1, proc_pidinfo=lambda *args: 0))
    monkeypatch.setattr(memory_guard.ctypes, 'get_errno', lambda: error)
    monkeypatch.setattr(memory_guard.time, 'sleep', lambda delay: None)
    if error == errno.ESRCH:
        assert process_tree.started(77) is None
    else:
        with pytest.raises(OSError) as failure:
            process_tree.started(77)
        assert failure.value.errno == error
        assert not isinstance(failure.value, ProcessLookupError)


def test_darwin_inexit_teardown_waits_for_zombie_or_esrch_and_never_certifies_stuck_inexit(monkeypatch):
    """During cold compiles, exiting clang/ld children expose PROC_FLAG_INEXIT (4) in pbsi_flags and shed
    their Mach task (EPERM) for >20 ms while XNU tears down vm_map before setting SZOMB. Only SZOMB or ESRCH certifies exit."""
    import ctypes
    assert memory_guard.PROC_FLAG_INEXIT == 4
    monkeypatch.setattr(memory_guard, 'DARWIN', True)
    sleeps = []
    monkeypatch.setattr(memory_guard.time, 'sleep', lambda d: sleeps.append(d))

    def make_lib(states):
        seq = list(states)
        last_errno = [errno.EPERM]

        def fake_rusage(pid, flavor, buf):
            last_errno[0] = errno.EPERM
            return -1

        def fake_pidinfo(pid, flavor, arg, buf, size):
            st, fl, rc_err = seq.pop(0) if len(seq) > 1 else seq[0]
            if rc_err is not None:
                last_errno[0] = rc_err
                return 0
            info = memory_guard._BsdShortInfo.from_address(ctypes.cast(buf, ctypes.c_void_p).value)
            info.pid = pid
            info.status = st
            info.flags = fl
            return ctypes.sizeof(memory_guard._BsdShortInfo)

        monkeypatch.setattr(memory_guard.ctypes, 'get_errno', lambda: last_errno[0])
        return SimpleNamespace(proc_pid_rusage=fake_rusage, proc_pidinfo=fake_pidinfo)

    # 1. 12 polls (120 ms) of SRUN + PROC_FLAG_INEXIT followed by SZOMB -> certified exited (None)
    monkeypatch.setattr(memory_guard, 'LIB', make_lib([(2, memory_guard.PROC_FLAG_INEXIT, None)] * 12 + [(memory_guard.SZOMB, memory_guard.PROC_FLAG_INEXIT, None)]))
    sleeps.clear()
    assert process_tree.started(95010) is None
    assert len(sleeps) == 12

    # 2. 8 polls (80 ms) of SRUN + PROC_FLAG_INEXIT followed by ESRCH (reaped) -> certified exited (None)
    monkeypatch.setattr(memory_guard, 'LIB', make_lib([(2, memory_guard.PROC_FLAG_INEXIT, None)] * 8 + [(0, 0, errno.ESRCH)]))
    sleeps.clear()
    assert process_tree.started(95010) is None
    assert len(sleeps) == 8

    # 3. Stuck PROC_FLAG_INEXIT that never reaches SZOMB or ESRCH within 100 attempts -> raises PermissionError fail-closed!
    monkeypatch.setattr(memory_guard, 'LIB', make_lib([(2, memory_guard.PROC_FLAG_INEXIT, None)]))
    sleeps.clear()
    with pytest.raises(PermissionError) as stuck_err:
        process_tree.started(95010)
    assert stuck_err.value.errno == errno.EPERM
    assert len(sleeps) == 99

    # 4. Live process (no PROC_FLAG_INEXIT, e.g. PROC_FLAG_PSUGID = 0x2000) returning EPERM -> stops after 2 retries!
    monkeypatch.setattr(memory_guard, 'LIB', make_lib([(2, 0x2000, None)]))
    sleeps.clear()
    with pytest.raises(PermissionError):
        process_tree.started(95010)
    assert len(sleeps) == 2


@pytest.mark.skipif(not memory_guard.DARWIN, reason='macOS libproc integration check')
def test_real_darwin_bsd_shortinfo_live_zombie_and_reaped():
    """Unmocked check against macOS libproc and SDK header value of PROC_FLAG_INEXIT."""
    import ctypes, os, subprocess, time
    info = memory_guard._BsdShortInfo()
    self_pid = os.getpid()
    cnt = memory_guard.LIB.proc_pidinfo(
        self_pid, memory_guard.PROC_PIDT_SHORTBSDINFO, 0, ctypes.byref(info), ctypes.sizeof(info)
    )
    assert cnt == ctypes.sizeof(info) and info.pid == self_pid
    assert (info.flags & memory_guard.PROC_FLAG_INEXIT) == 0
    assert memory_guard._darwin_bsd_state(self_pid) == 'unknown'

    # Spawn a short-lived child; before wait() reaps it (unreaped zombie: SZOMB or proc_find ESRCH) and after wait(),
    # _darwin_bsd_state must report 'exited' and process_tree.started must return None.
    child = subprocess.Popen(['/usr/bin/true'])
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and memory_guard._darwin_bsd_state(child.pid) != 'exited':
            time.sleep(0.005)
        assert memory_guard._darwin_bsd_state(child.pid) == 'exited'
        assert process_tree.started(child.pid) is None
    finally:
        assert child.wait(timeout=5) == 0
    assert memory_guard._darwin_bsd_state(child.pid) == 'exited'
    assert process_tree.started(child.pid) is None
