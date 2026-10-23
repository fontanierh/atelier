"""The Linux /proc sampler that backs the memory guard off macOS.

A synthetic procfs tree is injected, so these assertions run on any host and cover the
fields the guard reads: resident size, pinned start identity, CPU ticks and children.
"""
import os
import subprocess
import sys
import threading
import time

import pytest

from atelier.harness.safety import memory_guard as guard

PAGE = os.sysconf('SC_PAGE_SIZE')
NEWLINE = chr(10)


def fake(root, pid, *, state='S', rss_pages=3, start=4242, utime=7, stime=9, comm='python3'):
    folder = root / str(pid)
    (folder / 'task' / str(pid)).mkdir(parents=True)
    tokens = ['S'] + ['0'] * 23
    tokens[0], tokens[11], tokens[12], tokens[19] = state, str(utime), str(stime), str(start)
    (folder / 'stat').write_bytes(f'{pid} (python3 3.12) '.encode() + ' '.join(tokens).encode() + NEWLINE.encode())
    (folder / 'statm').write_text(f'100 {rss_pages} 10 0 0 0 0' + NEWLINE)
    (folder / 'status').write_text('Name:' + NEWLINE + f'VmRSS: {rss_pages * PAGE // 1024} kB' + NEWLINE + 'VmLck: 4 kB' + NEWLINE)
    (folder / 'io').write_text('rchar: 1' + NEWLINE + 'read_bytes: 11' + NEWLINE + 'write_bytes: 13' + NEWLINE)
    (folder / 'comm').write_text(comm + NEWLINE)
    return folder


@pytest.fixture
def procfs(tmp_path, monkeypatch):
    monkeypatch.setattr(guard, 'PROCFS', tmp_path)
    monkeypatch.setattr(guard, 'DARWIN', False)
    return tmp_path


def test_usage_reports_resident_size_and_a_pinned_start(procfs):
    fake(procfs, 77, rss_pages=5, start=999, utime=3, stime=4)
    value = guard.usage(77)
    assert value.resident == value.footprint == 5 * PAGE
    assert (value.started, value.user, value.system) == (999, 3, 4)
    assert value.wired == 4 * 1024
    assert (value.read_bytes, value.written_bytes) == (11, 13)
    assert not value.exited


def test_a_zombie_or_missing_process_is_not_sampled(procfs):
    fake(procfs, 77, state='Z')
    with pytest.raises(ProcessLookupError):
        guard.usage(77)
    with pytest.raises(ProcessLookupError):
        guard.usage(1234)


def test_children_and_name_come_from_proc(procfs):
    folder = fake(procfs, 77, comm='UnrealEditor-Cmd')
    assert guard.name(77) == 'UnrealEditor-Cmd'
    (folder / 'task' / '77' / 'children').write_text('12 13' + NEWLINE)
    assert guard.children(77) == [12, 13]


def test_a_process_with_no_children_or_comm_yields_empty_values(procfs):
    fake(procfs, 77)
    (procfs / '77' / 'comm').unlink()
    assert guard.children(77) == [] and guard.name(77) == ''


def test_a_child_of_any_worker_thread_is_listed(procfs):
    """Each task records only its own children, so a worker thread's child must still appear."""
    folder = fake(procfs, 77)
    (folder / 'task' / '77' / 'children').write_text('12' + NEWLINE)
    worker = folder / 'task' / '78'
    worker.mkdir()
    (worker / 'children').write_text('13 14' + NEWLINE)
    assert guard.children(77) == [12, 13, 14]


def test_a_refused_or_failed_read_is_not_process_absence(procfs):
    """Only a missing entry means gone. A refused read or malformed telemetry is a failure, so a
    dead-looking sample can never certify an empty owned tree."""
    folder = fake(procfs, 77)
    (folder / 'stat').unlink()
    (folder / 'stat').mkdir()
    with pytest.raises(OSError) as refused:
        guard.usage(77)
    assert not isinstance(refused.value, ProcessLookupError)
    (folder / 'task' / '77' / 'children').mkdir()
    with pytest.raises(OSError) as refused:
        guard.children(77)
    assert not isinstance(refused.value, ProcessLookupError)
    (folder / 'task').rename(folder / 'tasks-gone')
    with pytest.raises(ProcessLookupError):
        guard.children(77)


def test_malformed_procfs_values_fail_instead_of_reporting_absence(procfs):
    folder = fake(procfs, 77)
    (folder / 'stat').write_bytes(b'77 (python3) S 0 1' + NEWLINE.encode())
    with pytest.raises(RuntimeError, match='stat'):
        guard.usage(77)
    fake(procfs, 78, rss_pages=3)
    (procfs / '78' / 'statm').write_text('not numbers' + NEWLINE)
    with pytest.raises(RuntimeError, match='statm'):
        guard.usage(78)



@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='reads the real /proc')
def test_a_child_spawned_by_a_worker_thread_is_discovered():
    """The kernel records a child under the thread that created it, so a parent's own task entry
    is not enough; the live tree must still contain a worker thread's child."""
    spawned, holding = [], threading.Event()
    def spawn():
        spawned.append(subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']))
        holding.wait(30)  # Stay alive: a thread that exits reparents its child to the leader.
    worker = threading.Thread(target=spawn)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not spawned:
            time.sleep(0.02)
        assert spawned, 'the worker thread did not start its child'
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and spawned[0].pid not in guard.children(os.getpid()):
            time.sleep(0.02)
        assert spawned[0].pid in guard.children(os.getpid())
    finally:
        holding.set()
        worker.join(timeout=5)
        if spawned:
            spawned[0].kill()
            spawned[0].wait()



def test_refused_optional_counters_are_not_a_failed_sample(procfs):
    """/proc/<pid>/io needs ptrace access and may be refused for a live process, so its absence
    from the sample must not fail the guard or read as the process being gone."""
    folder = fake(procfs, 77, rss_pages=4)
    (folder / 'io').unlink()
    (folder / 'io').mkdir()
    (folder / 'status').unlink()
    (folder / 'status').mkdir()
    value = guard.usage(77)
    assert value.resident == 4 * PAGE
    assert (value.read_bytes, value.written_bytes, value.wired) == (0, 0, 0)

