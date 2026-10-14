import copy
import json

import pytest

from atelier import contract_review
from atelier.ai import ledger


REQUEST = {'id': '42', 'pull_number': 7, 'base_sha': 'a' * 40, 'head_sha': 'b' * 40}
REVIEW = {'summary': 'Checked the changed behavior and applicable contracts.', 'comments': []}


def test_clean_review_is_bound_to_both_commits():
    assert contract_review.validate(REQUEST, {**REQUEST, 'head_ref': 'feature'}, REVIEW)['completed']
    for key in ('base_sha', 'head_sha'):
        with pytest.raises(ValueError, match='commits'):
            contract_review.validate(REQUEST, {**REQUEST, key: 'c' * 40}, REVIEW)


@pytest.mark.parametrize('review', [None, {}, {'summary': '', 'comments': []},
                                    {'summary': 'ok', 'comments': None},
                                    {'summary': 'ok', 'comments': [{}]}])
def test_missing_or_malformed_review_fails_closed(review):
    with pytest.raises(ValueError): contract_review.validate(REQUEST, REQUEST, review)


def test_violation_is_reported_without_blocking_a_completed_review():
    review = copy.deepcopy(REVIEW)
    review['comments'] = [{'kind': 'violation', 'path': 'example.py', 'line': 1, 'side': 'RIGHT',
                           'body': 'This operation bypasses the required guard.', 'recipients': []}]
    assert contract_review.validate(REQUEST, REQUEST, review) == {'completed': True, 'violations': 1, 'comments': 1}
    review['comments'][0]['kind'] = 'contract-change'
    assert contract_review.validate(REQUEST, REQUEST, review)['violations'] == 0


def test_ci_receipt_precedes_submission_and_prevents_retry(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    monkeypatch.setenv('REVIEW_REQUEST', json.dumps(REQUEST))
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    assert contract_review.main(['begin', str(path)]) == 0
    record = json.loads(path.read_text())
    assert record['status'] == 'submitted'
    assert (record['model'], record['reasoning']) == ('gpt-6.1-sol', 'medium')
    with pytest.raises(FileExistsError): contract_review.main(['begin', str(path)])
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    with pytest.raises(SystemExit, match='never blindly rerun'):
        contract_review.main(['begin', str(tmp_path / 'different.json')])


def test_failed_or_interrupted_review_is_uncertain(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    ledger.begin(path, REQUEST)
    monkeypatch.setenv('REVIEW_REQUEST', json.dumps(REQUEST))
    monkeypatch.setenv('GITHUB_OUTPUT', str(tmp_path / 'outputs'))
    monkeypatch.delenv('ACTUAL_REQUEST', raising=False)
    monkeypatch.delenv('REVIEW_RESULT', raising=False)
    monkeypatch.setenv('REVIEW_OUTCOME', 'failure')
    assert contract_review.main(['finish', str(path)]) == 0
    assert json.loads(path.read_text())['status'] == 'submission_uncertain'
    assert (tmp_path / 'outputs').read_text() == 'completed=false\nviolations=0\n'
    with pytest.raises(FileExistsError): ledger.begin(path, REQUEST)


def test_split_phase_receipt_cannot_be_completed_twice(tmp_path):
    path = tmp_path / 'receipt.json'
    ledger.begin(path, REQUEST)
    ledger.finish(path, status='done')
    with pytest.raises(ValueError, match='Only a submitted'):
        ledger.finish(path, status='done')


def test_finalization_failure_preserves_the_original_operation_error(tmp_path, monkeypatch):
    path = tmp_path / 'receipt.json'
    def finalize(*args, **kwargs): raise OSError('disk unavailable')
    def operation(): raise TimeoutError('provider timeout')
    monkeypatch.setattr(ledger, 'finish', finalize)
    with pytest.raises(TimeoutError) as failure: ledger.run_once(path, {}, operation)
    assert 'OSError' in failure.value.__notes__[0]
    assert json.loads(path.read_text())['status'] == 'submitted'
