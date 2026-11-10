"""Mocked Darwin exit-time sampling and aggregate failure receipts; no native processes."""
import ctypes
import errno
import json
from types import SimpleNamespace

import pytest

from atelier.harness.safety import memory_guard, process_tree, tree_guard


def native_samples(monkeypatch, errors, *, state=2, bsd_error=0, size=64, sampled_pid=77):
    errors = iter(errors)
    last, pauses, calls = [0], [], []

    def rusage(pid, flavor, output):
        calls.append(pid)
        last[0] = next(errors)
        if last[0]:
            return -1
        value = ctypes.cast(output, ctypes.POINTER(memory_guard.Usage)).contents
        value.started, value.footprint = 300, 123
        return 0

    def info(pid, flavor, argument, output, length):
        assert flavor == 13 and length == 64
        last[0] = bsd_error
        if bsd_error:
            return 0
        fields = ctypes.cast(output, ctypes.POINTER(ctypes.c_uint32 * 16)).contents
        fields[0], fields[3] = sampled_pid, state
        return size

    monkeypatch.setattr(memory_guard, 'DARWIN', True)
    monkeypatch.setattr(memory_guard, 'LIB', SimpleNamespace(proc_pid_rusage=rusage, proc_pidinfo=info))
    monkeypatch.setattr(memory_guard.ctypes, 'get_errno', lambda: last[0])
    monkeypatch.setattr(memory_guard.time, 'sleep', pauses.append)
    return calls, pauses


def test_permission_race_retries_until_kernel_reports_absence(monkeypatch):
    calls, pauses = native_samples(monkeypatch, [errno.EPERM, errno.ESRCH], bsd_error=errno.EPERM)
    assert process_tree.started(77) is None
    assert calls == [77, 77] and pauses == [.01]


def test_transient_permission_failure_recovers_the_complete_live_sample(monkeypatch):
    calls, pauses = native_samples(monkeypatch, [errno.EPERM, 0])
    value = memory_guard.usage(77)
    assert value.started == 300 and value.footprint == 123 and not value.exited
    assert calls == [77, 77] and pauses == [.01]


@pytest.mark.parametrize('state,bsd_error', [(5, 0), (2, errno.ESRCH)])
def test_positive_bsd_exit_witness_needs_no_retry(monkeypatch, state, bsd_error):
    calls, pauses = native_samples(monkeypatch, [errno.EPERM], state=state, bsd_error=bsd_error)
    assert process_tree.started(77) is None
    assert calls == [77] and pauses == []


@pytest.mark.parametrize('evidence', [
    {}, {'bsd_error': errno.EPERM}, {'bsd_error': errno.EIO},
    {'state': 5, 'size': 16}, {'state': 5, 'sampled_pid': 78},
])
def test_live_or_unknown_bsd_evidence_cannot_certify_exit(monkeypatch, evidence):
    calls, pauses = native_samples(monkeypatch, [errno.EPERM] * 3, **evidence)
    with pytest.raises(PermissionError):
        process_tree.started(77)
    assert calls == [77] * 3 and pauses == [.01, .01]


def test_other_sampling_errors_are_not_retried_or_reclassified(monkeypatch):
    calls, pauses = native_samples(monkeypatch, [errno.EIO], state=5)
    with pytest.raises(OSError) as error:
        memory_guard.usage(77)
    assert error.value.errno == errno.EIO
    assert calls == [77] and pauses == []


def test_exiting_child_race_keeps_parent_guarded_and_retains_pinned_history(monkeypatch):
    native_samples(monkeypatch, [errno.EPERM] + [errno.ESRCH] * 10, bsd_error=errno.EPERM)
    root = SimpleNamespace(started=100, exited=0, footprint=50)
    monkeypatch.setattr(process_tree, 'usage', lambda pid: root if pid == 10 else memory_guard.usage(pid))
    monkeypatch.setattr(process_tree, 'children', lambda pid: [77] if pid == 10 else [])
    monkeypatch.setattr(process_tree, 'name', lambda pid: 'launcher' if pid == 10 else 'helper')
    tree = tree_guard.OwnedTree(process_tree, 10, 100)
    tree.parents[(77, 300)], tree.depth[(77, 300)] = tree.root, 1
    assert [(p['pid'], p['footprint_bytes']) for p in tree.sample()] == [(10, 50)]
    assert (77, 300) in tree.parents, 'exit never discards retained ownership history'
    # A later same-PID process must not inherit the exited child's pin.
    replacement = SimpleNamespace(started=999, exited=0, footprint=900)
    monkeypatch.setattr(process_tree, 'usage', lambda pid: root if pid == 10 else replacement)
    monkeypatch.setattr(process_tree, 'children', lambda pid: [])
    sent = []
    tree.stop_owned(lambda pid, number: sent.append(pid))
    assert sent == [10]


@pytest.mark.parametrize('recoverable', [False, True])
def test_default_aggregate_error_replaces_running_receipt_without_claiming_success(
        tmp_path, monkeypatch, recoverable):
    """Unknown telemetry must retain failure evidence even if the pinned cleanup later succeeds."""
    before = [dict(pid=1, started=10, footprint_bytes=77, name='launcher', depth=0)]
    calls = []

    def sample():
        calls.append(True)
        if len(calls) == 1:
            return before
        if len(calls) == 2 or not recoverable:
            raise PermissionError(errno.EPERM, 'sample denied', 77)
        return []

    tree = SimpleNamespace(root=(1, 10), same=lambda pin: True, reporters=None, sample=sample)
    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: tree)
    cleaned = []
    monkeypatch.setattr(tree_guard, 'drain_owned', lambda candidate: cleaned.append(candidate) or recoverable)
    monkeypatch.setattr(tree_guard.time, 'sleep', lambda delay: None)
    path = tmp_path / 'tree.json'
    with pytest.raises(PermissionError):
        tree_guard.run_child(1, 10, path)
    report = json.loads(path.read_text())
    assert report['state'] == 'cleanup_incomplete'
    assert report['termination_reason'] == 'monitor_error'
    assert report['cleanup_complete'] is recoverable
    assert report['error_type'] == 'PermissionError' and report['peak_bytes'] == 77
    assert report['error_errno'] == errno.EPERM and report['error_pid'] == 77
    assert report['processes'] == before and cleaned == [tree]
    if recoverable:
        assert report['cleanup_processes'] == [] and report['cleanup_footprint_bytes'] == 0
