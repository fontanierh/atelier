"""The tree house paintings go through atelier.ai.ledger: the record before the paid call, the old fields after, and a
recorded call is never sent again by itself."""
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location(f'{name}_ledger_test', TOOLS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name, stills', [('treehouse_concepts', 'STILLS'), ('treehouse_refs', 'CONTEXT')])
def test_a_painting_is_recorded_before_the_call_and_once(name, stills, monkeypatch, tmp_path):
    tool = load(name, monkeypatch)
    still = tmp_path / 'still.png'; still.write_bytes(b'still')
    monkeypatch.setattr(tool, 'OUT', tmp_path)
    monkeypatch.setattr(tool, stills, {'s': (still, 'a still')})
    record = tmp_path / 'v.provenance.json'
    calls = []

    def sunburst(prompt, size, images):
        assert json.loads(record.read_text())['status'] == 'submitted'
        calls.append(prompt)
        return b'png', {'total_tokens': 3}
    monkeypatch.setattr(tool, 'sunburst', sunburst)
    monkeypatch.setattr(tool, 'keep', lambda png, kind, slug, dest: ('d1g', {'file': dest.name}))
    result = tool.run('v', ['s'], 'a prompt; with a semicolon')
    assert result[1] is None and calls == ['a prompt; with a semicolon']
    prov = json.loads(record.read_text())
    assert prov['status'] == 'done' and prov['outputs'] == {'v.png': 'd1g'} and prov['usage'] == {'total_tokens': 3}
    assert prov['compact_copy'] == {'file': 'v.jpg'} and prov['prompt_file'] == 'v.prompt.txt'
    assert set(prov) >= {'stage', 'requested_model', 'quality', 'size', 'endpoint', 'execution', 'prompt_sha256',
                         'reference_files', 'started_at', 'finished_at', 'elapsed_seconds'}
    again = tool.run('v', ['s'], 'a prompt; with a semicolon')
    assert 'already recorded' in again[1] and len(calls) == 1


def test_a_failed_call_stays_recorded_without_its_message(monkeypatch, tmp_path):
    tool = load('treehouse_concepts', monkeypatch)
    still = tmp_path / 'still.png'; still.write_bytes(b'still')
    monkeypatch.setattr(tool, 'OUT', tmp_path)
    monkeypatch.setattr(tool, 'STILLS', {'s': (still, 'a still')})

    def sunburst(*args):
        raise RuntimeError('Sunburst HTTP 500: see https://signed.example/url')
    monkeypatch.setattr(tool, 'sunburst', sunburst)
    slug, error, _ = tool.run('v', ['s'], 'p')
    assert '<URL omitted>' in error
    prov = json.loads((tmp_path / 'v.provenance.json').read_text())
    assert prov['status'] == 'submission_uncertain' and prov['error_type'] == 'RuntimeError'
    assert 'signed' not in json.dumps(prov)
