"""Failure evidence survives reruns without changing cleanup or custody outcomes."""
import json
from types import SimpleNamespace

import pytest

from atelier.harness.safety import tree_guard


@pytest.mark.parametrize('mode', ['child', 'custody', 'legacy'])
@pytest.mark.parametrize('writable', [True, False])
def test_sampling_failure_records_before_cleanup_and_keeps_failure(tmp_path, monkeypatch, mode, writable):
    report = tmp_path / 'tree.json'
    log = tmp_path / 'tree.errors.log'
    if not writable:
        log.mkdir()  # Opening the diagnostic file fails, without relying on Unix permissions.
    error = PermissionError(1, 'Cannot sample process', 123)
    calls = []

    def sample():
        raise error

    def check_log():
        if writable:
            text = log.read_text()
            assert 'Traceback (most recent call last)' in text
            assert 'in sample' in text and 'PermissionError' in text
            assert 'owner=1 owner_started=10' in text

    def drain(*args, **kwargs):
        check_log()
        calls.append('drain')
        return False

    def custody(tree, path, value, descriptors, code):
        check_log()
        assert value['state'] == 'cleanup_incomplete'
        assert value['cleanup_complete'] is False and code == 1
        assert descriptors == ((99, (1, 2)),)
        calls.append('custody')
        return code

    monkeypatch.setattr(tree_guard, 'OwnedTree', lambda *args: SimpleNamespace(
        root=(1, 10), same=lambda key: True, sample=sample, reporters=None))
    monkeypatch.setattr(tree_guard, 'drain_owned', drain)
    monkeypatch.setattr(tree_guard, 'keep_custody', custody)
    monkeypatch.setattr(tree_guard, 'pin_monitor', lambda: (2, 20))
    monkeypatch.setattr(tree_guard.signal, 'signal', lambda *args: None)
    if mode == 'custody':
        assert tree_guard.run_child(1, 10, report, custody=((99, (1, 2)),)) == 1
        assert calls == ['custody']
    else:
        with pytest.raises(PermissionError) as raised:
            if mode == 'child':
                tree_guard.run_child(1, 10, report)
            else:
                tree_guard.run(1, 10, report, 10, tmp_path / 'stop')
        assert raised.value is error
        assert calls == ['drain']
        if mode == 'child':
            assert json.loads(report.read_text())['termination_reason'] == 'monitor_error'


def test_diagnostics_append_across_runs_without_frame_locals(tmp_path):
    report = tmp_path / 'tree.json'
    for pid in (123, 456):
        private_local = 'frame-local-value-not-for-diagnostics'
        try:
            raise PermissionError(1, 'sample denied', pid)
        except PermissionError as error:
            tree_guard.record_error(report, pid, pid * 10, error)
    text = report.with_suffix('.errors.log').read_text()
    assert text.count('Monitor failure at ') == 2
    assert 'owner=123 owner_started=1230' in text
    assert 'owner=456 owner_started=4560' in text
    assert private_local not in text
