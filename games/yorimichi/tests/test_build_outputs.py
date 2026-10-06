"""Fresh layout reuse must include the backdrop terrain read by northern regions."""
from dataclasses import replace
import json
from types import SimpleNamespace

from atelier import build


def test_missing_backdrop_grid_invalidates_a_matching_layout_stamp(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs',
                          stamps=tmp_path/'stamps', uproject=None)
    layout = next(s for s in build.load_recipe('yorimichi').steps(ctx) if s.name == 'world.layout')
    backdrop = tmp_path/'farhills.npy'
    assert backdrop in layout.outputs
    trees = build.Step('world.treehouse_trees', [])
    trees_fingerprint = build.fingerprint(trees, {})
    current = build.fingerprint(layout, {trees.name: trees_fingerprint})
    ctx.stamps.mkdir()
    (ctx.stamps/'world.treehouse_trees.json').write_text(json.dumps({'fingerprint': trees_fingerprint}))
    (ctx.stamps/'world.layout.json').write_text(json.dumps({'fingerprint': current}))
    for output in layout.outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'fixture')
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda context: [trees, layout]))
    messages = []
    assert build.build('yorimichi', ['world.layout'], dry=True, echo=messages.append) == 0
    assert any('world.layout' in line and 'up to date' in line for line in messages)

    backdrop.unlink()
    messages.clear()
    assert build.build('yorimichi', ['world.layout'], dry=True, echo=messages.append) == 0
    assert any('world.layout' in line and 'would run' in line for line in messages)
    assert json.loads((ctx.stamps/'world.layout.json').read_text())['fingerprint'] == current


def test_declaring_backdrop_output_keeps_completed_layout_fingerprint(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    layout = next(s for s in build.load_recipe('yorimichi').steps(ctx) if s.name == 'world.layout')
    previous = replace(layout, outputs=[o for o in layout.outputs if o != tmp_path/'farhills.npy'])
    assert build.fingerprint(layout, {}) == build.fingerprint(previous, {})
