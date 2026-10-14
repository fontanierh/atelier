"""Concept generation must never pay twice on an ordinary rerun. No provider calls."""
import importlib.util
import json
from pathlib import Path

import pytest

from atelier.ai import images


@pytest.fixture
def tool(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / 'assets/props/make_prop.py'
    spec = importlib.util.spec_from_file_location('prop_concept_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'OUT', tmp_path)
    return module


def test_submission_is_recorded_before_call_and_rerun_is_refused(tool, monkeypatch):
    calls = []
    def generate(*args, **kwargs):
        record = json.loads((tool.OUT / 'lantern/provenance.json').read_text())
        assert record['status'] == 'submitted'
        assert record['requested_model'] == 'gpt-image-2.5-sunburst'
        calls.append(1)
        return [b'image'], {'usage': {}}, 0.1
    monkeypatch.setattr(images, 'sunburst', generate)
    tool.concept('lantern', 'a lantern')
    with pytest.raises(SystemExit, match='already exists'): tool.concept('lantern', 'a lantern')
    assert calls == [1]


def test_uncertain_submission_cannot_pay_again(tool, monkeypatch):
    def fail(*args, **kwargs):
        raise TimeoutError('provider timeout')
    monkeypatch.setattr(images, 'sunburst', fail)
    with pytest.raises(TimeoutError): tool.concept('lantern', 'a lantern')
    record = json.loads((tool.OUT / 'lantern/provenance.json').read_text())
    assert record['status'] == 'submission_uncertain'
    with pytest.raises(FileExistsError): tool.concept('lantern', 'a lantern')
