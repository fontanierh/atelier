"""Selected railway constructors retain source geometry and publish no sibling data."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
from train import track as T, track_sources as S  # noqa: E402


def line():
    alignment = T.R.alignment()
    chainages = np.linspace(0, alignment.length, 100)
    x, y, _, _ = alignment.at(chainages)
    samples = [dict(s=float(s), x=float(a), y=float(b), rail_z=207.6, ground_z=207.6, **{'class': 'level'})
               for s, a, b in zip(chainages, x, y)]
    cx, cy, heading, _ = alignment.at(200.)
    return T.Line(dict(samples=samples, frame='synthetic explicit query',
        passing_loop=dict(start=100., end=300., second_track=[[200., float(cx - np.sin(heading) * 5), float(cy + np.cos(heading) * 5)]]),
        summary=dict(structures=[], spirals=[])))


def load(label, path):
    spec = importlib.util.spec_from_file_location(label, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_discovery_never_calls_any_track_mesh_constructor():
    ln = line()
    with patch.object(T, 'chunk_mesh', side_effect=AssertionError('geometry during discovery')):
        rows, doc = S.requests(ln)
    assert 'SM_TK_Chunk_00' in rows
    assert len(rows['SM_TK_Chunk_00']) == 3
    assert doc['chunks'][0]['origin'] == T._xyz(ln.frame(0.)[0])


def test_selected_packet_executes_only_its_constructor_and_has_consumed_palette():
    ln = line()
    with patch.object(T, 'chunk_mesh', side_effect=AssertionError('sibling geometry')):
        value = S.selected('SM_TK_Sleeper', 0, ln)
    expected = T.sleeper_mesh()
    assert value['vertices'] == expected.verts
    assert value['faces'] == expected.faces
    assert value['materials'] == expected.mats
    assert set(value['palette']) == {'MI_B_wood'}
    assert 'def chunk_mesh' not in json.dumps(value)
    assert 'route' not in value and 'samples' not in value


def test_deferred_station_and_overbridge_frames_and_every_corner_match_default():
    ln = line()
    expected, doc = T.layout(ln)
    actual, deferred_doc = S.requests(ln)
    assert deferred_doc == doc
    assert list(actual) == list(expected)
    for key, levels in expected.items():
        for original, request in zip(levels, actual[key]):
            selected = request.evaluate()
            assert selected.verts == original.verts, key
            assert selected.faces == original.faces, key
            assert selected.mats == original.mats, key


@pytest.mark.parametrize('asset,level', [('SM_TK_Sleeper', 1), ('SM_TK_Missing', 0), ('../escaped', 0)])
def test_unknown_source_selection_refuses(asset, level):
    with pytest.raises(ValueError): S.selected(asset, level, line())


def test_normal_graph_requires_cold_inventory_then_selected_factory_planners(tmp_path):
    recipe = load('train_track_recipe_test', GAME / 'train_atomic_build.py')
    ctx = SimpleNamespace(out=tmp_path)
    cold = recipe.track_steps(ctx, source_inputs=())
    assert cold[0].replan and cold[0].cache
    assert cold[-1].name == 'world.belmonte_track'
    path = tmp_path / 'belmonte-track/source-data/inventory.json'; path.parent.mkdir(parents=True)
    path.write_text(json.dumps(dict(schema=1, mesh_order=['SM_TK_Sleeper'], meshes=dict(SM_TK_Sleeper=dict(levels=1)))))
    rows = {step.name: step for step in recipe.track_steps(ctx, source_inputs=())}
    source = rows['world.belmonte_track.source.SM_TK_Sleeper_LOD0']
    assert source.cache and source.commands[0].args[:4] == ('--asset', 'SM_TK_Sleeper', '--level', '0')
    planner = rows['world.belmonte_track.geometry.SM_TK_Sleeper_LOD0']
    assert planner.cache and planner.heavy
    assert planner.reads == ['belmonte_track.source.SM_TK_Sleeper_LOD0']
    assert planner.commands[0].factory_startup and planner.commands[0].threads == 3
    assert GAME / 'world/train/track.py' not in planner.inputs
    assert GAME / 'world/train/track_sources.py' not in planner.inputs


def assembly_fixture(tmp_path):
    from atelier.atomic_files import atomic_json
    from atelier.export_manifest import publish_receipt
    root = tmp_path / 'belmonte-track'
    key = 'SM_TK_Sleeper_LOD0'
    atomic_json(root / 'source-data/inventory.json', dict(schema=1, mesh_order=['SM_TK_Sleeper'],
        meshes=dict(SM_TK_Sleeper=dict(levels=1))))
    source_path = root / 'source-data' / (key + '.json')
    atomic_json(source_path, S.packet('SM_TK_Sleeper', 0, T.sleeper_mesh()))
    folder = tmp_path / 'exports/world.belmonte_track.export' / key; folder.mkdir(parents=True)
    (folder / (key + '.glb')).write_bytes(b'geometry fixture')
    receipt = publish_receipt(folder, key=key, primary=key + '.glb', triangles=10, bounds=[[0, 0, 0], [1, 1, 1]],
        metadata=dict(geometry_sha256='a' * 64, material_sha256='b' * 64))
    atomic_json(tmp_path / 'planned_exports/belmonte_track' / key / 'plan.json',
        dict(parent=key, complete=True, source_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
             pieces=[dict(name=key, sha256='a' * 64, material_sha256='b' * 64)]))
    atomic_json(tmp_path / 'atomic_regions/belmonte_track/assets/manifest.json', dict(exports=[receipt]))
    atomic_json(tmp_path / 'atomic_regions/belmonte_track/logical-pieces.json', dict(parents={key: [key]},
        ownership={key: dict(source_triangles=10)}))
    return load('track_assembly_test', GAME / 'train_track_atomic_products.py'), folder


def test_complete_railway_assembly_copies_only_independent_files(tmp_path):
    module, _ = assembly_fixture(tmp_path);module.assemble(tmp_path)
    root = tmp_path / 'belmonte-track/atomic'
    doc = json.loads((root / 'track.json').read_text())
    assert doc['meshes']['SM_TK_Sleeper']['lods'] == ['atomic/meshes/SM_TK_Sleeper_LOD0.glb']
    path = root / 'meshes/SM_TK_Sleeper_LOD0.glb'
    assert path.read_bytes() == b'geometry fixture'
    before = path.stat().st_mtime_ns;module.assemble(tmp_path)
    assert path.stat().st_mtime_ns == before


@pytest.mark.parametrize('defect', ['corrupt', 'missing', 'foreign', 'stale-receipt'])
def test_railway_assembly_refuses_before_writes(tmp_path, defect):
    from atelier.export_manifest import publish_receipt
    module, folder = assembly_fixture(tmp_path);path = folder / 'SM_TK_Sleeper_LOD0.glb'
    if defect == 'corrupt': path.write_bytes(b'corrupt')
    elif defect == 'missing': path.unlink()
    elif defect == 'foreign': (folder / 'foreign.glb').write_bytes(b'foreign')
    else:
        path.write_bytes(b'replaced geometry')
        publish_receipt(folder, key='SM_TK_Sleeper_LOD0', primary=path.name, triangles=10, bounds=[[0, 0, 0], [1, 1, 1]])
    with pytest.raises((ValueError, FileNotFoundError)): module.assemble(tmp_path)
    assert not (tmp_path / 'belmonte-track/atomic').exists()


def test_expanded_normal_graph_selects_each_palette_with_its_own_export(tmp_path):
    from atelier.build import Call, Step
    from atelier.build_products import Graph
    recipe = load('train_track_expanded_graph', GAME / 'train_atomic_build.py')
    key = 'SM_TK_Sleeper_LOD0'
    roster = tmp_path / 'belmonte-track/source-data/inventory.json';roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps(dict(schema=1, mesh_order=['SM_TK_Sleeper'], meshes=dict(SM_TK_Sleeper=dict(levels=1)))))
    root = tmp_path / 'planned_exports/belmonte_track' / key;root.mkdir(parents=True)
    (root / 'plan.json').write_text(json.dumps(dict(schema=1, parent=key, complete=True, triangle_limit=32768,
        source_triangles=10, pieces=[dict(name=key, payload=key + '.npz', triangles=10)])))
    steps = [Step('world.belmonte_train_route', [Call('fixture route', lambda ctx, log: None)]),
             *recipe.track_steps(SimpleNamespace(out=tmp_path), source_inputs=())]
    selected = Graph(steps).select(['world.belmonte_track'])
    export, = [step for step in selected if step.name.startswith('world.belmonte_track.export.')]
    palette = tmp_path / 'belmonte-track/material-data' / key / (key + '.json')
    assert palette in export.inputs
    assert export.commands[0].script == GAME / 'world/train/export_track_piece.py'
    assert export.commands[0].args[-2:] == ('--materials', str(palette))
    assert export.cache and len(export.products) == 1


def test_projected_requests_retain_every_constructor_corner_without_rediscovery():
    ln = line()
    inventory = dict(S.inventory(ln), schema=1)
    original, _ = T.layout(ln)
    for parent, levels in original.items():
        for level, expected in enumerate(levels):
            value = S.descriptor(parent, level, inventory)
            # The selected stage receives no other asset, placement roster or route samples.
            assert set(value) == {'schema', 'asset', 'logical', 'level', 'request', 'code', 'support', 'palette', 'factory'}
            with patch.object(S, 'requests', side_effect=AssertionError('selected constructor rediscovered siblings')):
                actual = S.from_descriptor(value, line_factory=lambda: ln)
            assert actual['vertices'] == expected.verts, value['asset']
            assert actual['faces'] == expected.faces, value['asset']
            assert actual['materials'] == expected.mats, value['asset']


def test_fixed_constructor_projection_reads_no_route_or_sibling_constructor():
    value = S.descriptor('SM_TK_Sleeper', 0, dict(S.inventory(line()), schema=1))
    with patch.object(S, 'requests', side_effect=AssertionError('sibling discovery')):
        actual = S.from_descriptor(value, line_factory=lambda: pytest.fail('fixed primitive read route'))
    assert actual['vertices'] == T.sleeper_mesh().verts
    value['request']['function'] = 'layout'
    with pytest.raises(ValueError, match='constructor'):
        S.from_descriptor(value)


def test_fixed_constructor_normal_inputs_exclude_route_and_whole_inventory(tmp_path):
    recipe = load('train_track_projected_recipe', GAME / 'train_atomic_build.py')
    roster = tmp_path / 'belmonte-track/source-data/inventory.json'
    roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps(dict(schema=1, mesh_order=['SM_TK_Sleeper'],
        meshes=dict(SM_TK_Sleeper=dict(levels=1)))))
    route = tmp_path / 'route.json'
    steps = {step.name: step for step in recipe.track_steps(SimpleNamespace(out=tmp_path), source_inputs=(route,))}
    source = steps['world.belmonte_track.source.SM_TK_Sleeper_LOD0']
    assert route not in source.inputs and roster not in source.inputs
    assert source.reads == ['belmonte_track.request.SM_TK_Sleeper_LOD0']
    assert 'belmonte_track.geometry.SM_TK_Sleeper_LOD0' in steps['world.belmonte_track'].reads
    request = steps['world.belmonte_track.request.SM_TK_Sleeper_LOD0']
    assert request.cache and request.products[0].paths[0].name == 'SM_TK_Sleeper_LOD0.json'


def test_runtime_projection_keeps_every_placement_lod_collision_and_render_policy():
    import copy
    module = load('selected_track_runtime_projection', GAME / 'tools/belmonte_track_data.py')
    meshes, doc = T.layout(line())
    doc['meshes'] = {name: dict(lods=[f'meshes/{name}_LOD{k}.glb' for k in range(len(levels))],
        materials=list(dict.fromkeys(slot for mesh in levels for slot in mesh.mats)))
        for name, levels in meshes.items()}
    current = copy.deepcopy(doc)
    for name, spec in current['meshes'].items():
        spec['lods'] = [f'atomic/meshes/{name}_LOD{k}.glb' for k in range(len(spec['lods']))]
    before, after = module.build(doc), module.build(current)
    for name, spec in before['meshes'].items():
        expected = ['atomic/' + path for path in spec['lods']]
        assert after['meshes'][name]['lods'] == expected
        spec['lods'] = expected
    assert after == before


def test_layout_and_export_driver_edits_do_not_change_selected_source_key(tmp_path, monkeypatch):
    import hashlib
    from atelier import build
    from train import track_projection as projection
    recipe = load('track_local_key_recipe', GAME / 'train_atomic_build.py')
    roster_value = dict(S.inventory(line()), schema=1)
    before = S.descriptor('SM_TK_Sleeper', 0, roster_value)
    roster = tmp_path / 'belmonte-track/source-data/inventory.json'
    roster.parent.mkdir(parents=True); roster.write_text(json.dumps(roster_value))
    source = next(step for step in recipe.track_steps(SimpleNamespace(out=tmp_path))
                  if step.name == 'world.belmonte_track.source.SM_TK_Sleeper_LOD0')
    forbidden = {'track.py', 'track_build.py', 'track_sources.py', 'track_projection.py', 'route.py', 'earthworks.py'}
    assert not forbidden.intersection(path.name for path in source.inputs)
    def key(descriptor):
        consumed = hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()
        return build.fingerprint(source, {'product:belmonte_track.request.SM_TK_Sleeper_LOD0': consumed})
    original_key = key(before)
    track = tmp_path / 'track.py'
    original = projection.MODULES['train.track'].read_text()
    track.write_text(original.replace('def layout(line=None, *, make=None):',
                                     'def layout(line=None, *, make=None):\n    "unrelated discovery implementation edit"'))
    monkeypatch.setitem(projection.MODULES, 'train.track', track)
    read_text = Path.read_text
    def changed_driver(path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        if path.name == 'track_build.py':
            text = text.replace('def main():', 'def main():\n    "unrelated export-driver implementation edit"')
        return text
    monkeypatch.setattr(Path, 'read_text', changed_driver)
    after = S.descriptor('SM_TK_Sleeper', 0, roster_value)
    assert after == before
    assert key(after) == original_key
    assert S.from_descriptor(after)['faces'] == T.sleeper_mesh().faces
    track.write_text(original.replace('def sleeper_mesh():', 'def sleeper_mesh():\n    "changed consumed constructor"'))
    assert key(S.descriptor('SM_TK_Sleeper', 0, roster_value)) != original_key


def test_station_selected_inputs_exclude_route_and_discovery_sources(tmp_path):
    recipe = load('track_station_key_recipe', GAME / 'train_atomic_build.py')
    roster = tmp_path / 'belmonte-track/source-data/inventory.json'
    roster.parent.mkdir(parents=True)
    roster.write_text(json.dumps(dict(schema=1, mesh_order=['SM_ST_Sheds'], meshes=dict(SM_ST_Sheds=dict(levels=3)))))
    source = next(step for step in recipe.track_steps(SimpleNamespace(out=tmp_path))
                  if step.name == 'world.belmonte_track.source.SM_ST_Sheds_LOD0')
    assert not {'track.py', 'station.py', 'station_site.py', 'route.py', 'earthworks.py',
                'track_build.py', 'track_sources.py'}.intersection(path.name for path in source.inputs)


@pytest.mark.parametrize('field', ['vertices', 'uv', 'palette'])
def test_same_count_track_source_cannot_admit_previous_plan_or_export(tmp_path, monkeypatch, field):
    module, _ = assembly_fixture(tmp_path)
    module.assemble(tmp_path)
    root = tmp_path / 'belmonte-track/atomic'
    before = {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    source = tmp_path / 'belmonte-track/source-data/SM_TK_Sleeper_LOD0.json'
    data = json.loads(source.read_text())
    if field == 'vertices': data['vertices'][0][0] += 0.125
    elif field == 'uv':
        original = data['to_object']
        data['to_object'] = original.replace('data.extend((v[a], v[b]))', 'data.extend((v[a] * 0.5, v[b]))')
        assert data['to_object'] != original
    else: data['palette']['MI_B_wood'][0] = 0.25
    source.write_text(json.dumps(data))
    monkeypatch.setattr(module.export_assembly, 'assemble', lambda *a: pytest.fail('publication before source admission'))
    with pytest.raises(ValueError, match='plan differs from current source'): module.assemble(tmp_path)
    assert {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()} == before
    plan = tmp_path / 'planned_exports/belmonte_track/SM_TK_Sleeper_LOD0/plan.json'
    data = json.loads(plan.read_text()); data['source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    # A genuine new planner changes the consumed geometry or material packet.
    data['pieces'][0]['material_sha256' if field == 'palette' else 'sha256'] = 'c' * 64
    plan.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='export differs from current source plan'): module.assemble(tmp_path)
    assert {p.relative_to(root): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()} == before


def test_selected_track_planner_records_actual_source_and_palette_digests(tmp_path, monkeypatch):
    import ast
    from atelier.atomic_files import atomic_json
    from atelier.export_manifest import real_directory, sha
    from atelier.model_files import regular_files, retain_files
    import argparse
    source = tmp_path / 'source.json'; output = tmp_path / 'planned'; materials = tmp_path / 'materials'
    key = 'SM_TK_Test_LOD0'
    value = dict(schema=1, asset=key, triangles=1, palette=dict(MI_B_wood=[1, 0, 0]),
                 material_factory='factory', export_glb='export')
    atomic_json(source, value)
    def plan(obj, root, **kwargs):
        real_directory(root, create=True)
        return dict(parent=key, complete=True, source_triangles=1,
                    pieces=[dict(name=key, slots=['MI_B_wood'], sha256='a' * 64)])
    tree = ast.parse((GAME / 'world/train/plan_track.py').read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    namespace = dict(argparse=argparse, Path=Path, json=json, hashlib=hashlib, __doc__='fixture',
        real_directory=real_directory, sha=sha, atomic_json=atomic_json, regular_files=regular_files,
        retain_files=retain_files, construct=lambda v: v, plan=plan,
        bpy=SimpleNamespace(ops=SimpleNamespace(wm=SimpleNamespace(read_factory_settings=lambda **k: None))))
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-track-planner-main>', 'exec'), namespace)
    namespace['main'](['--source', str(source), '--asset', key, '--output', str(output), '--materials', str(materials)])
    result = json.loads((output / 'plan.json').read_text())
    assert result['source_sha256'] == sha(source)
    assert result['pieces'][0]['material_sha256'] == sha(materials / (key + '.json'))
