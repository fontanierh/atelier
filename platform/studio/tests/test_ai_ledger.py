import json
import pytest
from atelier.ai.ledger import run_once


def test_paid_submission_is_recorded_before_call_and_not_repeated(tmp_path):
    path = tmp_path / 'job.json'
    calls = []
    def operation():
        assert json.loads(path.read_text())['status'] == 'submitted'
        calls.append(1)
        return {'usage': {'images': 1}}
    run_once(path, {'model': 'test'}, operation)
    with pytest.raises(FileExistsError):
        run_once(path, {'model': 'test'}, operation)
    assert calls == [1]
    assert json.loads(path.read_text())['status'] == 'done'


def test_uncertain_submission_stays_blocked_and_does_not_record_error_secrets(tmp_path):
    path = tmp_path / 'job.json'
    def operation():
        raise RuntimeError('sensitive provider message')
    with pytest.raises(RuntimeError):
        run_once(path, {}, operation)
    record = json.loads(path.read_text())
    assert record['status'] == 'submission_uncertain'
    assert 'sensitive' not in path.read_text()
    with pytest.raises(FileExistsError):
        run_once(path, {}, lambda: {})


def test_try_once_reports_instead_of_raising(tmp_path):
    from atelier.ai.ledger import try_once
    path = tmp_path / 'job.json'
    record, why = try_once(path, {'model': 'test'}, lambda: {'output': 'a.png'})
    assert why is None and record['status'] == 'done' and record['output'] == 'a.png'
    record, why = try_once(path, {}, lambda: {})
    assert record is None and 'already recorded in job.json' in why
    def fail():
        raise RuntimeError('HTTP 500 at https://signed.example/x?sig=1')
    record, why = try_once(tmp_path / 'failed.json', {}, fail)
    assert record is None and why == 'RuntimeError: HTTP 500 at <URL omitted>'
    assert json.loads((tmp_path / 'failed.json').read_text())['status'] == 'submission_uncertain'
