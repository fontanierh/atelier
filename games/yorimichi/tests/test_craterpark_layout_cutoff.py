"""Riding edits leave island placement current; landform and stale source never do."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from atelier import build, build_products

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import craterpark_layout as layout  # noqa: E402
from craterpark.v2 import dsl, v4_config, v4_placement  # noqa: E402


@pytest.fixture
def selected(tmp_path, monkeypatch):
    design = tmp_path / 'design.json'
    artifact = tmp_path / 'geometry.npz'
    doc = {'frame': {'lift': 680.}, 'ground': {},
           'site': {'buildable': [[0, 0], [20, 0], [20, 20], [0, 20]]}, 'rev': 1}
    monkeypatch.setenv(v4_config.EDITOR_SWITCH, 'off')
    monkeypatch.setenv(v4_config.SWITCH, str(design))
    monkeypatch.setattr(v4_placement, 'geometry_path', lambda: artifact)
    mesh = dsl.Mesh(np.array([[0., 0., 0.], [0., 0., 1.], [1., 0., 0.], [1., 2., 0.]]),
                    np.array([[0, 1, 2], [1, 2, 3]]),
                    role=np.array([dsl.ROLE[dsl.GROUND], dsl.ROLE[dsl.RIDING]]))
    index = {'render': [{}], 'accepted': True,
             'validation': {'ran': True, 'ok': True, 'supports': {'ran': True, 'ok': True}},
             'lines': [{'spawn': {'location_cm': [1000., -1000., 12500.], 'yaw_deg': 0.}}]}
    extra = {}

    def write(*, current=True):
        design.write_text(json.dumps(doc))
        if current:
            index['v4'] = v4_config.provenance()
        np.savez(artifact, index=np.asarray(json.dumps(index)), **mesh.to_arrays('r0_'), **extra)

    write()
    return SimpleNamespace(doc=doc, mesh=mesh, index=index, extra=extra, write=write, artifact=artifact)


def test_current_riding_and_material_changes_leave_layout_identity(selected):
    before = layout.snapshot()
    selected.doc['rev'] += 1
    selected.mesh.V[3, 1] += 5.
    selected.mesh.material[:] = 1
    selected.write()
    assert layout.snapshot() == before


@pytest.mark.parametrize('change', ['ground', 'site', 'depth', 'spawn', 'yaw'])
def test_consumed_placement_changes_invalidate_layout_identity(selected, change):
    before = layout.snapshot()
    if change == 'ground':
        selected.mesh.V[0, 1] += 1.
    elif change == 'site':
        selected.doc['site']['buildable'][0][0] -= 2.
    elif change == 'depth':
        selected.doc['ground'] = {'dig': {'kind': 'depth', 'DEPTH': 50.}}
    elif change == 'spawn':
        selected.index['lines'][0]['spawn']['location_cm'][0] += 1.
    else:
        selected.index['lines'][0]['spawn']['yaw_deg'] += 5.
    selected.write()
    assert layout.snapshot() != before


@pytest.mark.parametrize('field', ['heights', 'weights', 'metadata'])
def test_terrain_grid_changes_invalidate_layout_identity(selected, field):
    selected.index['ground_grid'] = {'x0': 0., 'z0': 0., 'G': 2., 'nx': 3, 'nz': 3}
    selected.extra.update(ground_height=np.zeros((3, 3)), ground_weight=np.ones((3, 3)))
    selected.write()
    before = layout.snapshot()
    if field == 'metadata':
        selected.index['ground_grid']['G'] = 3.
    else:
        selected.extra['ground_height' if field == 'heights' else 'ground_weight'][0, 0] += .1
    selected.write()
    assert layout.snapshot() != before


@pytest.mark.parametrize('failure', ['stale', 'missing', 'unaccepted', 'supports', 'frame', 'spawn'])
def test_invalid_selected_inputs_cannot_keep_a_prior_layout_identity(selected, failure):
    layout.snapshot()
    if failure == 'stale':
        selected.doc['rev'] += 1
        selected.write(current=False)
    elif failure == 'missing':
        selected.artifact.unlink()
    else:
        if failure == 'unaccepted':
            selected.index['accepted'] = False
        elif failure == 'supports':
            selected.index['validation']['supports']['ok'] = False
        elif failure == 'frame':
            selected.doc['frame']['lift'] = 700.
        else:
            selected.index['lines'] = []
        selected.write()
    with pytest.raises((OSError, ValueError)):
        layout.snapshot()


def test_inputs_changing_during_projection_fail(selected, monkeypatch):
    original = v4_placement.drop_in
    def changing():
        result = original()
        selected.doc['rev'] += 1
        selected.write()
        return result
    monkeypatch.setattr(v4_placement, 'drop_in', changing)
    with pytest.raises(ValueError, match='changed during observation'):
        layout.snapshot()


def test_recipe_routes_placement_consumers_through_validated_cutoff(selected, tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    steps = recipe.steps(ctx)
    build_products.Graph(steps)                     # no source/layout/geometry dependency cycle
    cutoff = next(s for s in steps if s.name == 'world.craterpark_layout')
    assert cutoff.cutoff and cutoff.heavy and cutoff.needs == ['world.craterpark_geometry']
    assert v4_config.design_path() in cutoff.inputs
    for name in ('world.layout', 'world.hidamari.layout_data', 'world.island.geometry.FarHills',
                 'world.map', 'world.belmonte.north.raw.SM_BM_NorthApron'):
        step = next(s for s in steps if s.name == name)
        assert 'world.craterpark_layout' in step.needs, name
        # Direct geometry queries retain their source dependency as well as
        # the validated placement identity; assemblies only consume Products.
        if name in ('world.layout', 'world.map'):
            assert v4_config.design_path() not in step.inputs, name
    geometry = next(s for s in steps if s.name == 'world.craterpark_geometry')
    assert v4_config.design_path() in geometry.inputs
    assert 'world.craterpark_layout' not in geometry.needs


def test_editor_park_uses_current_terrain_grid_envelope(selected, monkeypatch):
    design = v4_config.design_path()
    data = design.parent / 'data'
    data.mkdir()
    meta = {'inner': {'x0': -10., 'z0': -20., 'G': 2., 'nx': 3, 'nz': 4,
                      'layers': {'floor': 'floor.bin'}}, 'outer': {'file': 'outer.bin'}}
    (data / 'terrain.json').write_text(json.dumps(meta))
    for name in ('floor.bin', 'outer.bin'):
        (data / name).write_bytes(b'terrain fixture')
    selected.doc['schema'] = v4_config.EDITOR_SCHEMA
    monkeypatch.setenv(v4_config.EDITOR_SWITCH, str(design))
    selected.write()
    before = layout.snapshot()
    selected.doc['rev'] += 1
    selected.mesh.V[3, 1] += 2.
    selected.write()
    assert layout.snapshot() == before
    meta['inner']['nx'] += 1
    (data / 'terrain.json').write_text(json.dumps(meta))
    selected.write()
    assert layout.snapshot() != before


def test_real_cutoff_keeps_island_consumer_current_and_never_masks_stale_geometry(selected, monkeypatch, tmp_path):
    import yori
    root = tmp_path / 'project'
    (root / 'games' / 'standin').mkdir(parents=True)
    monkeypatch.setattr(build.paths, 'GAMES', root / 'games')
    monkeypatch.setenv('ATELIER_BUILD_ROOT', str(root / 'build'))
    out = root / 'build' / 'standin'
    monkeypatch.setattr(yori, 'OUT', out)
    output = out / 'craterpark' / 'layout-identity.json'
    runs = []
    steps = [build.Step('layout', [build.Call('validated layout', lambda ctx, log: layout.main())],
                        inputs=[v4_config.design_path(), selected.artifact], outputs=[output], cutoff=True),
             build.Step('island', [build.Call('export island', lambda ctx, log: runs.append('island'))], needs=['layout'])]
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))
    assert build.build('standin', [], echo=lambda line: None) == 0
    assert runs == ['island']
    selected.doc['rev'] += 1
    selected.mesh.V[3, 1] += 2.
    selected.write()
    assert build.build('standin', [], echo=lambda line: None) == 0
    assert runs == ['island']
    selected.mesh.V[0, 1] += 1.
    selected.write()
    assert build.build('standin', [], echo=lambda line: None) == 0
    assert runs == ['island', 'island']
    selected.doc['rev'] += 1
    selected.write(current=False)
    assert build.build('standin', [], echo=lambda line: None) != 0
    assert runs == ['island', 'island']
