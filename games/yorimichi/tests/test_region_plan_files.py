"""Planner retries repair only recorded owner payloads and never adopt foreign files."""
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'world'))
    return importlib.import_module('region_plan_files')


def value(*names):
    return dict(schema=1, parent='Whole', complete=True,
                pieces=[dict(payload=name) for name in names])


def test_interrupted_owned_write_can_resume_and_retire_only_previous_owned_payloads(tmp_path, owner):
    root = tmp_path / 'plan'
    owner.begin(root, 'Whole', ['Whole.npz'])
    (root / 'Whole.npz').write_bytes(b'partial')
    # No completion manifest was published, so this must never pass a current check.
    assert not (root / 'plan.json').exists()
    owner.begin(root, 'Whole', ['Whole_cell_0_0.npz'])
    (root / 'Whole_cell_0_0.npz').write_bytes(b'complete')
    owner.finish(root, value('Whole_cell_0_0.npz'))
    assert owner.files(root) == {'Whole_cell_0_0.npz', 'plan.json'}
    assert (root / 'Whole_cell_0_0.npz').read_bytes() == b'complete'
    assert json.loads((root / 'plan.json').read_text()) == value('Whole_cell_0_0.npz')


@pytest.mark.parametrize('kind', ['regular', 'directory', 'link', 'broken_link', 'unrecorded_payload'])
def test_foreign_member_refuses_before_any_journal_or_payload_write(tmp_path, owner, kind):
    root = tmp_path / 'plan'; root.mkdir()
    outside = tmp_path / 'outside'; outside.write_bytes(b'untouched')
    target = root / ('Whole.npz' if kind == 'unrecorded_payload' else 'foreign')
    if kind in ('regular', 'unrecorded_payload'): target.write_bytes(b'foreign')
    elif kind == 'directory': target.mkdir()
    else: target.symlink_to(outside if kind == 'link' else tmp_path / 'missing')
    with pytest.raises(ValueError): owner.begin(root, 'Whole', ['Whole.npz'])
    assert not (root / owner.JOURNAL).exists()
    assert outside.read_bytes() == b'untouched'
    assert target.exists() or target.is_symlink()


def test_foreign_file_added_during_generation_refuses_before_manifest_or_retirement(tmp_path, owner):
    owner.begin(tmp_path, 'Whole', ['Whole.npz'])
    (tmp_path / 'Whole.npz').write_bytes(b'current')
    (tmp_path / 'foreign').write_bytes(b'foreign')
    with pytest.raises(ValueError): owner.finish(tmp_path, value('Whole.npz'))
    assert (tmp_path / 'foreign').read_bytes() == b'foreign'
    assert not (tmp_path / 'plan.json').exists()


@pytest.mark.parametrize('names', [['Other.npz'], ['../Whole.npz'], ['Whole.npz', 'Whole.npz'], []])
def test_invalid_parent_ownership_is_never_recorded(tmp_path, owner, names):
    with pytest.raises(ValueError): owner.begin(tmp_path, 'Whole', names)
    assert list(tmp_path.iterdir()) == []
