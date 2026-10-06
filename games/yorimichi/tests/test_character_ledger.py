"""The character concept tools pay through atelier.ai.ledger: the record before the call, the old fields after, and a
recorded call is never sent again by itself."""
import importlib.util
import json
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / 'assets' / 'characters' / 'tools'


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location(f'{name}_ledger_test', TOOLS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def still(tmp_path):
    path = tmp_path / 'still.png'; path.write_bytes(b'still')
    return path


def fake_edit(record, calls, reply):
    def gpt_edit(prompt, images, n):
        assert json.loads(record.read_text())['status'] == 'submitted'
        calls.append(prompt)
        if isinstance(reply, Exception):
            raise reply
        return reply(n)
    return gpt_edit


@pytest.mark.parametrize('name, reply', [('spirit_concepts', lambda n: ([b'png'] * n, 2.0)),
                                         ('cairo_back_concepts', lambda n: ([b'png'] * n, {'usage': {}}, 2.0))])
def test_a_concept_is_recorded_before_the_call_and_once(name, reply, monkeypatch, tmp_path):
    tool = load(name, monkeypatch)
    ref = still(tmp_path)
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'OUT', tmp_path / 'out')
    if name == 'spirit_concepts':
        monkeypatch.setattr(tool, 'CONCEPTS', {'v': {'prompt': 'a prompt; with a semicolon', 'stills': [ref]}})
    else:
        monkeypatch.setattr(tool, 'STILLS', [ref])
        monkeypatch.setattr(tool, 'BASE', 'a prompt; ')
        monkeypatch.setattr(tool, 'CONCEPTS', {'v': 'with a semicolon'})
    record, calls = tmp_path / 'out' / 'v.provenance.json', []
    monkeypatch.setattr(tool, 'gpt_edit', fake_edit(record, calls, reply))
    slug, outs, secs, err = tool.run('v', 2)
    assert (outs, secs, err) == (['v-1.png', 'v-2.png'], 2.0, None) and calls == ['a prompt; with a semicolon']
    prov = json.loads(record.read_text())
    assert prov['status'] == 'done' and prov['approval'] == 'pending' and set(prov['outputs']) == {'v-1.png', 'v-2.png'}
    assert prov['reference_files'] == {'still.png': tool.sha(ref)} and prov['prompt_file'] == 'v.prompt.txt'
    assert 'already recorded' in tool.run('v', 2)[3] and len(calls) == 1


def test_a_failed_concept_stays_recorded_without_its_message(monkeypatch, tmp_path):
    tool = load('cairo_back_concepts', monkeypatch)
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'OUT', tmp_path / 'out')
    monkeypatch.setattr(tool, 'STILLS', [still(tmp_path)])
    monkeypatch.setattr(tool, 'CONCEPTS', {'v': 'x'})
    record, calls = tmp_path / 'out' / 'v.provenance.json', []
    monkeypatch.setattr(tool, 'gpt_edit', fake_edit(record, calls, TimeoutError('read timed out at https://api.example/x')))
    _, outs, secs, err = tool.run('v', 1)
    assert outs == [] and secs is None and err.startswith('TimeoutError') and 'api.example' not in err
    assert json.loads(record.read_text())['status'] == 'submission_uncertain'
    assert 'already recorded' in tool.run('v', 1)[3] and len(calls) == 1


def test_the_fox_hunter_views_are_recorded_once(monkeypatch, tmp_path):
    tool = load('fox_hunter_pipeline', monkeypatch)
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'ASSET', tmp_path / 'asset')
    monkeypatch.setattr(tool, 'VIEWS', {'back': 'the back. '})
    (tmp_path / 'asset' / 'front-r01').mkdir(parents=True)
    (tmp_path / 'asset' / 'front-r01' / 'C.png').write_bytes(b'front')
    record, calls = tmp_path / 'asset' / 'views-r01' / 'back.provenance.json', []
    monkeypatch.setattr(tool.sc, 'gpt_edit', fake_edit(record, calls, lambda n: ([b'png'], 3.0)))
    tool.stage_views()
    prov = json.loads(record.read_text())
    assert prov['status'] == 'done' and prov['output'] == 'back.png' and prov['output_sha256'] == tool.sc.sha(record.parent / 'back.png')
    assert prov['reference_files'] == {'asset/views-r01/front.png': tool.sc.sha(record.parent / 'front.png')}
    tool.stage_views()
    assert len(calls) == 1


def test_a_body_swap_view_raises_rather_than_paying_twice(monkeypatch, tmp_path):
    tool = load('cairo_body_swap_sunburst', monkeypatch)
    out = tmp_path / 'references'; out.mkdir()
    (out / 'naked-left.png').write_bytes(b'naked')
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, 'OUT', out)
    monkeypatch.setattr(tool, 'CONCEPT', still(tmp_path))
    monkeypatch.setattr(tool, 'COMMON', '{view} view. ', raising=False)
    record, calls = out / 'left.provenance.json', []
    monkeypatch.setattr(tool.wb, 'gpt_edit', fake_edit(record, calls, lambda n: ([b'png'], {'usage': {}}, 4.0)))
    assert tool.run('left') == ('left', 4.0)
    prov = json.loads(record.read_text())
    assert prov['status'] == 'done' and prov['approval'] == 'pending' and prov['output_sha256'] == tool.wb.sha(out / 'left.png')
    assert (out / 'api-private' / 'left.response.json').exists()
    with pytest.raises(FileExistsError):
        tool.run('left')
    assert len(calls) == 1


def test_an_outfit_redo_under_spend_sets_the_old_records_aside_and_pays_once_more(monkeypatch, tmp_path):
    outfit = load('cairo_outfit', monkeypatch)
    from atelier.ai import ledger
    d = tmp_path / 'body-swap-test'
    (d / 'references').mkdir(parents=True); (d / 'key').mkdir()
    for v in outfit.VIEWS:
        (d / f'references/naked-{v}.png').write_bytes(b'naked')
    (d / 'references/envelope.json').write_text('{}')
    spec = tmp_path / 'test.toml'; spec.write_text('name = "test"\n')
    monkeypatch.setattr(outfit, 'ROOT', tmp_path)
    monkeypatch.setattr(outfit, 'CHAR', tmp_path)
    monkeypatch.setattr(outfit.env, 'load', lambda *a: None)
    paid = []

    def sunburst_tool(cmd, log, environ):   # like cairo_body_swap_sunburst.py: one ledger record per image, never repaid
        folder, name = ('key', 'key-{}') if '--key' in cmd else ('references', '{}')
        for v in ['concept'] if '--make-concept' in cmd else outfit.VIEWS:
            out = d / 'concept.png' if v == 'concept' else d / folder / f'{name.format(v)}.png'
            ledger.run_once(out.with_suffix('.provenance.json'), {}, lambda: out.write_bytes(b'png') and {})
            paid.append(out.name)
        return 0
    monkeypatch.setattr(outfit, 'run', sunburst_tool)
    argv = ['cairo_outfit.py', str(spec), '--dir', d.name, '--spend', '--until', 'key']
    monkeypatch.setattr('sys.argv', argv)
    outfit.main()
    assert len(paid) == 9
    monkeypatch.setattr('sys.argv', argv + ['--redo', 'views'])
    outfit.main()
    assert len(paid) == 17
    assert (d / 'references/front.rejected-1.provenance.json').exists() and (d / 'key/key-front.rejected-1.provenance.json').exists()
    assert json.loads((d / 'references/front.provenance.json').read_text())['status'] == 'done'
    monkeypatch.setattr('sys.argv', argv)
    outfit.main()   # done: nothing runs, nothing is set aside
    assert len(paid) == 17 and not (d / 'references/front.rejected-2.provenance.json').exists()
