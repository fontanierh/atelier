"""The island and house concepts go through atelier.ai.ledger: the record before the paid call, an earlier record
(also in the older format) is never sent again, and --again sets the earlier record aside."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def load(name, monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location(f'{name}_ledger_test', TOOLS / f'{name}.py')
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    import atelier.env
    monkeypatch.setattr(atelier.env, 'require', lambda *names: None)
    monkeypatch.setattr(tool, 'OUT', tmp_path / 'concepts')
    monkeypatch.setattr(tool, 'ORIGINALS', tmp_path / 'originals')
    monkeypatch.setattr(tool, 'compact', lambda png, dest, kind: (dest.write_bytes(png), {'file': dest.name})[1])
    still = tmp_path / 'still.png'; still.write_bytes(b'still')
    refs = 'REFS' if name == 'island_concepts' else 'STILLS'
    monkeypatch.setattr(tool, refs, {k: (still, text) for k, (_, text) in getattr(tool, refs).items()})
    calls = []

    def sunburst(prompt, size, images):
        record = tool.OUT / f'{view_of(tool, prompt)}.provenance.json'
        assert json.loads(record.read_text())['status'] == 'submitted'
        calls.append(record.name)
        return b'png', {'total_tokens': 3}
    monkeypatch.setattr(tool, 'sunburst', sunburst)
    tool.OUT.mkdir(parents=True)
    return tool, calls


def view_of(tool, prompt):
    if hasattr(tool, 'prompt_of'):
        return next(v for v in tool.VIEWS if tool.prompt_of(v) == prompt)
    return next(slug for slug, _, p in tool.concepts() if p == prompt)


def main(tool, monkeypatch, *args):
    monkeypatch.setattr(sys, 'argv', ['tool', *args])
    tool.main()


OLD = {'stage': 'concept', 'status': 'failed', 'error': 'Sunburst HTTP 500'}   # the format before the ledger


def test_an_island_view_is_recorded_before_the_call_and_once(monkeypatch, tmp_path):
    tool, calls = load('island_concepts', monkeypatch, tmp_path)
    (tool.OUT / 'boat.provenance.json').write_text(json.dumps(OLD))
    main(tool, monkeypatch, '--only', 'far,boat')
    assert calls == ['far.provenance.json']
    prov = json.loads((tool.OUT / 'far.provenance.json').read_text())
    assert prov['status'] == 'done' and prov['outputs'] == {'far.png': tool.sha(b'png')}
    assert prov['compact_copy'] == {'file': 'far.jpg'} and prov['usage'] == {'total_tokens': 3}
    assert set(prov) >= {'stage', 'concept', 'requested_model', 'quality', 'size', 'endpoint', 'execution',
                         'prompt_file', 'prompt_sha256', 'reference_files', 'started_at', 'finished_at',
                         'elapsed_seconds'}
    assert (tool.ORIGINALS / 'far.png').read_bytes() == b'png'
    assert json.loads((tool.OUT / 'boat.provenance.json').read_text()) == OLD
    secs, error = tool.run('far')
    assert 'already recorded' in error and len(calls) == 1


def test_a_failed_island_view_stops_and_stays_recorded_without_its_message(monkeypatch, tmp_path):
    tool, _ = load('island_concepts', monkeypatch, tmp_path)

    def sunburst(*args):
        raise RuntimeError('Sunburst HTTP 500: see https://signed.example/url')
    monkeypatch.setattr(tool, 'sunburst', sunburst)
    with pytest.raises(SystemExit, match='not retried'):
        main(tool, monkeypatch)
    prov = json.loads((tool.OUT / 'far.provenance.json').read_text())
    assert prov['status'] == 'submission_uncertain' and prov['error_type'] == 'RuntimeError'
    assert 'signed' not in json.dumps(prov) and not (tool.OUT / 'boat.provenance.json').exists()


def test_a_house_concept_is_called_again_only_with_again_which_sets_the_record_aside(monkeypatch, tmp_path, capsys):
    tool, calls = load('house_concepts', monkeypatch, tmp_path)
    (tool.OUT / 'variants.jpg').write_bytes(b'jpg')
    (tool.OUT / 'street.provenance.json').write_text(json.dumps(OLD))
    tool.ORIGINALS.mkdir(); (tool.ORIGINALS / 'street.png').write_bytes(b'earlier')
    main(tool, monkeypatch)
    assert calls == ['uphill.provenance.json'] and 'pass --again to repeat: street' in capsys.readouterr().out
    assert json.loads((tool.OUT / 'street.provenance.json').read_text()) == OLD
    main(tool, monkeypatch, '--again', 'street')
    assert calls == ['uphill.provenance.json', 'street.provenance.json']
    assert json.loads((tool.OUT / 'street.provenance.rejected-1.json').read_text()) == OLD
    assert (tool.ORIGINALS / 'street.rejected-1.png').read_bytes() == b'earlier'
    prov = json.loads((tool.OUT / 'street.provenance.json').read_text())
    assert prov['status'] == 'done' and prov['concept'] == 'street' and prov['outputs'] == {'street.png': tool.sha(b'png')}
    main(tool, monkeypatch, '--again', 'street')   # the JPEG is there now: nothing is called
    assert len(calls) == 2
