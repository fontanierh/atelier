"""Staging preserves source bytes except the explicit production piece projection."""
from dataclasses import replace
import io
import json
import os
from types import SimpleNamespace

from atelier import build


def test_staging_copies_required_sources_and_preserves_unrelated_data(tmp_path, monkeypatch):
    recipe = build.load_recipe('yorimichi')
    data = recipe.runtime_data
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path / 'build')
    destination = tmp_path / 'Content' / 'Data'
    course_bytes = data.RACING_COURSES.read_bytes()
    scene_bytes = (data.ASSETS / 'belmonte/source.json').read_bytes()
    monkeypatch.setattr(data, 'REGIONS', tmp_path / 'regions')
    monkeypatch.setattr(data, 'ASSETS', tmp_path / 'assets')
    monkeypatch.setattr(data, 'RACING_COURSES', tmp_path / 'courses.json')
    scene = data.ASSETS / 'belmonte/source.json'
    scene.parent.mkdir(parents=True)
    scene.write_bytes(scene_bytes)
    model_path = data.courses.surface_inputs()[0]
    model_copy = scene.parent / model_path.relative_to(data.courses.SCENE.parent)
    model_copy.parent.mkdir(parents=True, exist_ok=True)
    model_copy.write_bytes(model_path.read_bytes())
    monkeypatch.setattr(data.paths, 'content_data', lambda game: destination)
    expected = {}
    for rel in data.staged(ctx.out):
        source = data.staged_source(ctx.out, rel)
        source.parent.mkdir(parents=True, exist_ok=True)
        expected[rel] = course_bytes if rel == 'racing/belmonte_courses.json' else rel.encode()
        source.write_bytes(expected[rel])
        os.utime(source, ns=(1_000_000_000, 2_000_000_000))
    city = dict(instances=dict(HD_Streets=[[0,0,0,0,1]]), roads=[])
    (ctx.out/'hidamari/city.json').write_text(json.dumps(city))
    tile_name = 'HD_Streets_cell_0_0'
    tile = dict(name=tile_name, triangles=1, sha256='a'*64, min=[0,0,0], max=[1,1,1])
    partition = dict(complete=True,tag='v1_128m',triangle_limit=32768,
                     sources=dict(HD_Terrain={},HD_Square={},HD_Streets=dict(
                         source_slots=['HDS_road'],source_collision_boxes=0,source_triangles=1,
                         source_min=[0,0,0],source_max=[1,1,1],tiles=[tile])))
    expected['city_surface_tiles/v1_128m/manifest.json'] = json.dumps(partition).encode()
    partition_path = ctx.out/'city_surface_tiles/v1_128m/manifest.json'
    partition_path.write_bytes(expected['city_surface_tiles/v1_128m/manifest.json'])
    os.utime(partition_path, ns=(1_000_000_000,2_000_000_000))
    expected['hidamari/city.json'] = (json.dumps(dict(instances={tile_name:[[0,0,0,0,1]]},roads=[]),indent=2)+'\n').encode()
    # The committed skatepark source wins over any similarly named generated file.
    (ctx.out / 'skatepark').mkdir(exist_ok=True)
    (ctx.out / 'skatepark/park.json').write_bytes(b'wrong generated park')
    retained = destination / 'SkateRide/clips.json'
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'keep source data')

    log = io.StringIO()
    recipe.stage_data(ctx, log)

    for rel, content in expected.items():
        target = destination / rel
        assert target.read_bytes() == content
        if rel != 'hidamari/city.json':
            assert target.stat().st_mtime_ns == 2_000_000_000
    assert retained.read_bytes() == b'keep source data'
    assert log.getvalue().splitlines() == [f'staged {rel}' for rel in data.staged(ctx.out)]


def test_staging_implementation_is_a_narrow_fingerprint_input(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    steps = recipe.steps(ctx)
    stage = next(step for step in steps if step.name == 'data.stage')
    implementation = recipe.GAME / 'runtime_data.py'
    assert implementation in stage.inputs
    assert stage.commands[0].fn is recipe.runtime_data.stage_data
    assert all(implementation not in step.inputs for step in steps if step.name != 'data.stage')

    source = tmp_path / 'runtime_data.py'
    source.write_bytes(implementation.read_bytes())
    contract = replace(stage, inputs=[source])
    done = {name: name for name in stage.needs}
    previous = build.fingerprint(contract, done)
    source.write_text(source.read_text() + '\n# a staging implementation change\n')
    assert build.fingerprint(contract, done) != previous
