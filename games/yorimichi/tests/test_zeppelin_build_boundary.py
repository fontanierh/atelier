"""City exports leave Zeppelin current; its actual terrain, layout and canopy inputs do not."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from atelier import build
from test_mega_ramp_layers import changed_by
from test_volcano_layers import RECIPE


def test_hidamari_export_implementation_does_not_regenerate_zeppelin(tmp_path, monkeypatch):
    changed = changed_by(RECIPE.REGIONS / 'hidamari' / 'build.py', tmp_path, monkeypatch)
    assert 'world.hidamari' in changed
    assert 'world.zeppelin' not in changed


@pytest.mark.parametrize('edited', [
    RECIPE.REGIONS / 'hidamari' / 'layout.py',
    RECIPE.REGIONS / 'hidamari' / 'mountains.py',
    RECIPE.REGIONS / 'treehouse' / 'trees.py',
    RECIPE.ASSETS / 'megapark' / 'map.json',
    RECIPE.ASSETS / 'megapark' / 'geometry' / 'piece.npz',
    RECIPE.ASSETS / 'megapark' / 'collision' / 'piece.npz',
])
def test_consumed_code_and_data_still_regenerate_zeppelin(tmp_path, monkeypatch, edited):
    assert 'world.zeppelin' in changed_by(edited, tmp_path, monkeypatch)


def test_targeted_zeppelin_keeps_selection_order_and_complete_source_closure(tmp_path):
    steps = RECIPE.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None))
    selected = build.order(list(reversed(steps)), ['world.zeppelin'])
    names = [step.name for step in selected]
    assert names.index('world.hidamari') < names.index('world.zeppelin')
    zeppelin = next(step for step in selected if step.name == 'world.zeppelin')
    assert {'world.layout', 'world.treehouse_trees'} <= set(zeppelin.needs)
    assert 'world.hidamari' not in zeppelin.needs and 'world.hidamari' in zeppelin.after
    script = RECIPE.REGIONS / 'zeppelin' / 'build.py'
    assert set(RECIPE.local_imports(script)) <= set(zeppelin.inputs)
    assert {RECIPE.ASSETS / 'megapark' / name for name in ('map.json','geometry','collision')} <= set(zeppelin.inputs)
    catalog = json.loads((RECIPE.ASSETS / 'megapark' / 'map.json').read_text())
    for item in catalog['models'] + catalog['collision']:
        path = RECIPE.ASSETS / 'megapark' / item['npz']
        assert any(path == root or root in path.parents for root in zeppelin.inputs), path


@pytest.mark.parametrize('legacy', [False, True], ids=['independent-exports', 'old-city-export-edge'])
def test_builder_rechecks_actual_dependencies_after_layout_cutoff(tmp_path, monkeypatch, legacy):
    out = tmp_path / 'out'
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out/'logs', stamps=out/'stamps', uproject=None)
    production = next(s for s in RECIPE.steps(ctx) if s.name == 'world.zeppelin')
    sources = {name: tmp_path/(name+'.py') for name in ('trees', 'layout', 'city')}
    for path in sources.values():path.write_text('1')
    world, trees, city, airship = (out/name for name in ('world.json','trees.json','city.json','airship.json'))
    ran = []

    def canopy(ctx, log):
        out.mkdir(exist_ok=True)
        trees.write_text(sources['trees'].read_text())

    def layout(ctx, log):
        world.write_text(sources['layout'].read_text())

    def export_city(ctx, log):
        ran.append('city')
        city.write_text(sources['city'].read_text())

    def export_airship(ctx, log):
        ran.append('zeppelin')
        airship.write_text(world.read_text()+trees.read_text())

    zeppelin = replace(production, commands=[build.Call('export airship', export_airship)],
                       inputs=[], outputs=[airship], heavy=False)
    if legacy:
        zeppelin = replace(zeppelin, needs=['world.layout','world.hidamari'], after=[])
    steps = [
        build.Step('world.treehouse_trees', [build.Call('canopy', canopy)], inputs=[sources['trees']], outputs=[trees]),
        build.Step('world.layout', [build.Call('layout', layout)], inputs=[sources['layout']],
                   needs=['world.treehouse_trees'], outputs=[world], cutoff=True),
        build.Step('world.hidamari', [build.Call('city', export_city)], inputs=[sources['city']],
                   needs=['world.layout','world.treehouse_trees'], outputs=[city]),
        zeppelin,
    ]
    monkeypatch.setattr(build, 'Context', lambda game: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))

    def run():
        ran.clear()
        assert build.build('yorimichi', ['world.zeppelin'], echo=lambda line: None) == 0
        return ran.copy()

    assert run() == ['city','zeppelin']
    assert run() == []
    sources['city'].write_text('2')
    assert run() == (['city','zeppelin'] if legacy else ['city'])
    # Layout output stays byte-identical, but the imported canopy metadata really changed.
    before = world.read_bytes()
    sources['trees'].write_text('2')
    assert run() == ['city','zeppelin']
    assert world.read_bytes() == before and airship.read_text() == '12'
    sources['layout'].write_text('2')
    assert run() == ['city','zeppelin'] and airship.read_text() == '22'
