"""Ordinary owned Python processes exercise compile guards without heavy process names or admission scans."""
from contextlib import contextmanager
import json
import subprocess
import sys
import time

import pytest

from atelier.safety import guard, guarded, process_tree, tree_guard


class MonitorProcess:
    def __init__(self, status=None):
        self.status = status

    def poll(self):
        return self.status

    def wait(self, timeout=None):
        if self.status is None:
            raise subprocess.TimeoutExpired('monitor', timeout)
        return self.status

    def terminate(self):
        self.status = -15


def receipt(path, **changes):
    value = dict(owner=123, owner_started=456, state='running', observed_monotonic=time.monotonic(),
                 cleanup_complete=True)
    value.update(changes)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize('case', ['missing', 'malformed', 'owner', 'start', 'stale', 'future', 'nan', 'state'])
def test_missing_or_invalid_live_receipts_fail_closed(tmp_path, case):
    path = tmp_path / 'tree.json'
    if case == 'malformed':
        path.write_text('{')
    elif case != 'missing':
        changes = dict(owner=dict(owner=999), start=dict(owner_started=999),
                       stale=dict(observed_monotonic=time.monotonic() - 6),
                       future=dict(observed_monotonic=time.monotonic() + 60),
                       nan=dict(observed_monotonic=float('nan')), state=dict(state='child_exited'))
        receipt(path, **changes[case])
    monitor = guard.TreeMonitor(MonitorProcess(), 123, 456, path)
    with pytest.raises(RuntimeError, match='live receipt'):
        monitor.check()
    with pytest.raises(RuntimeError, match='become ready'):
        monitor.ready(timeout=.02)


@pytest.mark.parametrize('status,state,owner,complete', [(1, 'child_exited', 123, True),
                                                       (0, 'running', 123, True),
                                                       (0, 'child_exited', 999, True),
                                                       (0, 'child_exited', 123, False)])
def test_terminal_status_and_receipt_are_both_required(tmp_path, status, state, owner, complete):
    path = tmp_path / 'tree.json'
    receipt(path, state=state, owner=owner, cleanup_complete=complete)
    with pytest.raises(RuntimeError, match='certify'):
        guard.TreeMonitor(MonitorProcess(status), 123, 456, path).finish()


def test_terminal_wait_has_a_deadline(tmp_path):
    monitor = guard.TreeMonitor(MonitorProcess(), 123, 456, tmp_path / 'missing')
    with pytest.raises(RuntimeError, match='did not finish'):
        monitor.finish(timeout=.01)


def test_attach_discards_previous_receipt_before_starting_monitor(tmp_path, monkeypatch):
    path = tmp_path / 'tree.json'
    receipt(path)
    monkeypatch.setattr(process_tree, 'started', lambda pid: 456)
    process = MonitorProcess()
    monkeypatch.setattr(guard.subprocess, 'Popen', lambda command: process)
    with guard.attach_tree(123, path, duration=None, expected_start=456) as monitor:
        assert not path.exists()
        with pytest.raises(RuntimeError, match='become ready'):
            monitor.ready(timeout=.02)
    assert process.status == -15


@pytest.fixture
def admissions(monkeypatch):
    calls = []

    @contextmanager
    def admitted(purpose, **kwargs):
        calls.append(kwargs)
        kwargs['on_slot']('big', '')
        yield
    monkeypatch.setattr(guarded, 'render_lock', admitted)
    return calls


def assert_gone(pid, started):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            value = process_tree.usage(pid)
        except ProcessLookupError:
            return
        if value.started != started or value.exited:
            return
        time.sleep(.02)
    pytest.fail('owned process remains alive')


def standin(tmp_path, megabytes=0):
    child_file = tmp_path / 'child.json'
    child_code = (f'import os,json,time; from atelier.safety.process_tree import started; '
                  f'block=bytearray({megabytes}*1024*1024); '
                  f'open({str(child_file)!r},"w").write(json.dumps([os.getpid(),started(os.getpid())])); '
                  'time.sleep(30)')
    wrapper = ('import subprocess,sys,time; '
               f'block=bytearray({megabytes}*1024*1024); '
               f'subprocess.Popen([sys.executable,"-c",{child_code!r}]); time.sleep(30)')
    return [sys.executable, '-c', wrapper], child_file


def test_compile_aggregate_crossing_stops_individually_fitting_processes(tmp_path, admissions):
    command, child_file = standin(tmp_path, 64)
    folder = tmp_path / 'guard'
    with pytest.raises(RuntimeError, match='aggregate memory guard'):
        guarded.run(command, folder, kind='compile', timeout=8, limit_gib=96 / 1024)
    record = json.loads((folder / 'memory-health-tree.json').read_text())
    assert record['state'] == 'memory_limit'
    assert record['footprint_bytes'] > record['limit_bytes']
    assert len(record['processes']) >= 2
    assert all(p['footprint_bytes'] < record['limit_bytes'] for p in record['processes'])
    for process in record['processes']:
        assert_gone(process['pid'], process['started'])
    assert child_file.exists()
    assert len(admissions) == 1 and admissions[0]['kind'] == 'compile'


def test_monitor_loss_reaps_recorded_tree_but_preserves_bystander(tmp_path, monkeypatch, admissions):
    command, child_file = standin(tmp_path)
    original = guarded.attach_tree
    captured = []

    @contextmanager
    def attach(*args, **kwargs):
        with original(*args, **kwargs) as monitor:
            captured.append((monitor.pid, monitor.started))
            check = monitor.check

            def lose_monitor():
                if child_file.exists() and monitor.process.poll() is None:
                    monitor.process.kill()
                    monitor.process.wait(timeout=3)
                check()
            monitor.check = lose_monitor
            yield monitor
    monkeypatch.setattr(guarded, 'attach_tree', attach)
    bystander = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        with pytest.raises(RuntimeError, match='exited before'):
            guarded.run(command, tmp_path / 'guard', kind='compile', timeout=8)
        assert_gone(*captured[0])
        assert_gone(*json.loads(child_file.read_text()))
        assert bystander.poll() is None
    finally:
        bystander.terminate()
        bystander.wait(timeout=3)


@pytest.mark.parametrize('failure', ['readiness', 'startup'])
def test_readiness_failure_never_releases_actual_command(tmp_path, monkeypatch, admissions, failure):
    marker = tmp_path / 'executed'
    captured = []

    @contextmanager
    def attach(pid, report, duration, limit_gib=10., expected_start=None):
        captured.append((pid, expected_start))
        if failure == 'startup':
            raise RuntimeError('aggregate monitor startup failed')
        monitor = guard.TreeMonitor(MonitorProcess(), pid, expected_start, report)
        ready = monitor.ready
        monitor.ready = lambda: ready(timeout=.02)
        yield monitor
    monkeypatch.setattr(guarded, 'attach_tree', attach)
    with pytest.raises(RuntimeError, match='become ready|startup failed'):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'],
                    tmp_path / 'guard', kind='compile')
    assert not marker.exists()
    assert_gone(*captured[0])


def test_fast_compile_requires_terminal_receipt_and_preserves_policy_and_fds(tmp_path, admissions):
    import os
    read_fd, write_fd = os.pipe()
    try:
        command = [sys.executable, '-c', f'import os; os.write({write_fd},b"done")']
        folder = tmp_path / 'guard'
        assert guarded.run(command, folder, kind='compile', pass_fds=(write_fd,)) == 0
        assert os.read(read_fd, 4) == b'done'
    finally:
        os.close(read_fd)
        os.close(write_fd)
    record = json.loads((folder / 'memory-health-tree.json').read_text())
    assert record['state'] == 'child_exited'
    assert len(admissions) == 1


def test_child_success_does_not_hide_final_monitor_failure(tmp_path, monkeypatch, admissions):
    original = guarded.attach_tree

    @contextmanager
    def attach(*args, **kwargs):
        with original(*args, **kwargs) as monitor:
            finish = monitor.finish

            def failed_terminal():
                finish()
                monitor.report.write_text('{}')
                finish()
            monitor.finish = failed_terminal
            yield monitor
    monkeypatch.setattr(guarded, 'attach_tree', attach)
    with pytest.raises(RuntimeError, match='certify'):
        guarded.run([sys.executable, '-c', 'pass'], tmp_path / 'guard', kind='compile')


def test_run_child_cleans_up_on_telemetry_failure(tmp_path, monkeypatch):
    stopped = []

    class Tree:
        root = (123, 456)

        def same(self, key):
            return True

        def sample(self):
            raise OSError('telemetry unavailable')

        def stop_owned(self):
            stopped.append(True)
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: Tree())
    with pytest.raises(OSError):
        tree_guard.run_child(123, 456, tmp_path / 'tree.json')
    assert stopped == [True]


def test_child_exit_stops_leftovers_before_writing_terminal_receipt(tmp_path, monkeypatch):
    stopped = []

    class Tree:
        root = (123, 456)
        samples = 0

        def same(self, key):
            return True

        def sample(self):
            self.samples += 1
            if self.samples >= 3:
                return []
            return [dict(pid=124, started=457, footprint_bytes=100, name='python', depth=1)]

        def stop_owned(self):
            stopped.append(True)
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: Tree())
    write = tree_guard.write_report

    def terminal(path, value):
        assert stopped == [True, True]
        write(path, value)
    monkeypatch.setattr(tree_guard, 'write_report', terminal)
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(123, 456, path) == 0
    record = json.loads(path.read_text())
    assert record['state'] == 'child_exited' and record['cleanup_complete'] is True


def test_child_exit_with_undrained_member_is_not_success(tmp_path, monkeypatch):
    class Tree:
        root = (123, 456)

        def same(self, key):
            return True

        def sample(self):
            return [dict(pid=124, started=457, footprint_bytes=100, name='python', depth=1)]

        def stop_owned(self):
            pass
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: Tree())
    drain = tree_guard.drain_owned
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda tree: drain(tree, timeout=0.))
    path = tmp_path / 'tree.json'
    assert tree_guard.run_child(123, 456, path) == 1
    record = json.loads(path.read_text())
    assert record['state'] == 'cleanup_incomplete'
    assert record['cleanup_complete'] is False and record['termination_reason'] == 'child_exited'


def test_dead_root_monitor_never_releases_actual_command(tmp_path, monkeypatch, admissions):
    marker = tmp_path / 'executed'
    captured = []

    @contextmanager
    def attach(pid, report, **kwargs):
        captured.append((pid, process_tree.started(pid)))
        yield MonitorProcess(1)
    monkeypatch.setattr(guarded, 'attach_memory_guard', attach)
    with pytest.raises(RuntimeError, match='before releasing'):
        guarded.run([sys.executable, '-c', f'open({str(marker)!r},"w").write("ran")'],
                    tmp_path / 'guard', kind='compile')
    assert not marker.exists()
    assert_gone(*captured[0])


@pytest.mark.parametrize('terminal_failure', [False, True])
def test_poll_callbacks_follow_aggregate_health_and_terminal_receipt(tmp_path, monkeypatch, admissions,
                                                                  terminal_failure):
    original = guarded.attach_tree
    events = []

    @contextmanager
    def attach(*args, **kwargs):
        with original(*args, **kwargs) as monitor:
            check, finish = monitor.check, monitor.finish

            def checked():
                check()
                events.append('health')

            def finished():
                finish()
                events.append('terminal')
                if terminal_failure:
                    raise RuntimeError('terminal receipt refused')
            monitor.check, monitor.finish = checked, finished
            yield monitor
    monkeypatch.setattr(guarded, 'attach_tree', attach)

    def run():
        return guarded.run([sys.executable, '-c', 'pass'], tmp_path / 'guard', kind='compile',
                           on_poll=lambda pid: events.append('ack'))
    if terminal_failure:
        with pytest.raises(RuntimeError, match='terminal receipt refused'):
            run()
        assert events[-1] == 'terminal', 'a failed terminal check must not acknowledge results'
    else:
        assert run() == 0
        assert events[-2:] == ['terminal', 'ack']
    for index, event in enumerate(events[:events.index('terminal')]):
        if event == 'ack':
            assert index > 0 and events[index - 1] == 'health'
