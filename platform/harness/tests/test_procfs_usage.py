"""The Linux /proc sampler that backs the memory guard off macOS.

A synthetic procfs tree is injected, so these assertions run on any host and cover the
fields the guard reads: resident size, pinned start identity, CPU ticks and children.
"""
import os

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
