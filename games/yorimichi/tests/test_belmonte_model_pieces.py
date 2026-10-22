"""Bound actual committed large models and execute the production placement/material assembly."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import numpy as np
import pytest
from types import SimpleNamespace

from atelier.model_files import retain_files, source_records
from atelier.gltf import glb_parts
from atelier import build


GAME = Path(__file__).resolve().parents[1]
REGION = GAME / 'world/regions/belmonte'
SPEC = importlib.util.spec_from_file_location('bounded_belmonte_models', REGION / 'model_pieces.py')
PIECES = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(PIECES)
SOURCE = GAME / 'assets/belmonte'
MANIFEST = json.loads((SOURCE / 'source.json').read_text())
LARGE = [entry for entry in MANIFEST['meshes'] if entry['triangles'] > PIECES.LIMIT]


@pytest.mark.parametrize('entry', LARGE, ids=lambda entry: entry['name'])
def test_every_current_oversized_committed_model_has_bounded_pieces(tmp_path, entry):
    path = tmp_path / Path(entry['path']).name
    shutil.copy2(SOURCE / entry['path'], path)
    prepared = PIECES.prepare(deepcopy(entry), path)
    assert len(prepared) > 1
    assert sum(row['triangles'] for row, _, _ in prepared) == entry['triangles']
    assert max(row['triangles'] for row, _, _ in prepared) <= PIECES.LIMIT
    assert all(row['parent_bounds_m'] == entry['bounds_m'] for row, _, _ in prepared)
    assert len({row['name'] for row, _, _ in prepared}) == len(prepared)
    hull = isinstance(entry.get('collision'), dict)
    assert sum(collides for _, _, collides in prepared) == (1 if hull else len(prepared))
    assert sum(bool(row.get('collision')) for row, _, _ in prepared) == (1 if hull else 0)
    original_doc, _ = glb_parts(path.read_bytes())
    for row, slots, _ in prepared:
        made = tmp_path / Path(row['path']).name
        assert hashlib.sha256(made.read_bytes()).hexdigest() == row['sha256']
        doc, _ = glb_parts(made.read_bytes())
        assert slots == [int(material['name'].split('_')[1]) for material in doc['materials']]
        assert all(material in original_doc['materials'] for material in doc['materials'])


def test_small_models_keep_exact_bytes_names_and_policy(tmp_path):
    entry = next(entry for entry in MANIFEST['meshes'] if entry['triangles'] < 1000)
    path = tmp_path / Path(entry['path']).name
    shutil.copy2(SOURCE / entry['path'], path)
    before = path.read_bytes()
    (same, _, collides), = PIECES.prepare(entry, path)
    assert same is entry and collides and path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_actual_recipe_binds_all_partition_support(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    owner = next(step for step in build.load_recipe('yorimichi').steps(ctx) if step.name == 'world.belmonte')
    assert REGION / 'model_pieces.py' in owner.inputs
    assert all(build.paths.STUDIO / 'atelier' / name in owner.inputs
               for name in ('gltf_partition.py', 'mesh_partition.py', 'gltf.py'))


def test_bad_triangle_declaration_refuses_before_writing_pieces(tmp_path):
    entry = deepcopy(LARGE[0]); path = tmp_path / Path(entry['path']).name
    shutil.copy2(SOURCE / entry['path'], path)
    entry['triangles'] = 1
    with pytest.raises(ValueError, match='triangle declaration'):
        PIECES.prepare(entry, path)
    assert list(tmp_path.iterdir()) == [path]


def test_omitted_child_slots_do_not_merge_distinct_parent_cull_groups():
    # The second child uses only slot1. Two parent instances differ in slot0 and
    # scale; merging their now-identical child bindings would change distance culling.
    bounds = [[0., 0., 0.], [4., 4., 1.]]
    first = dict(name='SM_BM_Test_Piece0', bounds_m=bounds, parent_bounds_m=bounds, parent_material_slots=[0, 1])
    second = dict(first, name='SM_BM_Test_Piece3')
    transforms = [dict(translation_cm=[0., 0., 0.], rotation_xyzw=[0., 0., 0., 1.], scale=[s, s, s])
                  for s in (1., 3.)]
    namespace = dict(
        data={'placements': [dict(asset='parent', materials=slots, transform=transform)
                             for slots, transform in zip((['a', 'b'], ['changed', 'b']), transforms)]},
        by_asset={'parent': [(first, [0], True), (second, [1], False)]},
        materials={key: {'name': 'MI_'+key} for key in ('a', 'b', 'changed')},
        meshes=[first, second], np=np)
    script = REGION / 'build.py'
    main = next(node for node in ast.parse(script.read_text()).body
                if isinstance(node, ast.FunctionDef) and node.name == 'main')
    def assignment(node, name):
        return isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
    start = next(i for i, node in enumerate(main.body) if assignment(node, 'grouped'))
    end = next(i for i, node in enumerate(main.body) if assignment(node, 'material_name'))
    exec(compile(ast.Module(body=main.body[start:end], type_ignores=[]), str(script), 'exec'), namespace)
    children = [group for group in namespace['groups'] if group['asset'].endswith('SM_BM_Test_Piece3.SM_BM_Test_Piece3')]
    assert len(children) == 2
    assert [group['transforms'] for group in children] == [[transforms[0]], [transforms[1]]]
    assert [group['cull_cm'] for group in children] == [50000, 0]
    assert all(group['parent_collision'] and not group['collision'] for group in children)


@pytest.mark.parametrize('hull', [False, True])
def test_actual_region_main_preserves_shared_instances_materials_parent_cull_and_collision(tmp_path, monkeypatch, hull):
    # Use one actual small model, with a lower test budget, through the real assembly body.
    entry = deepcopy(next(entry for entry in MANIFEST['meshes']
                          if 100 < entry['triangles'] < 500 and bool(entry.get('collision')) == hull))
    assets = tmp_path / 'assets'; (assets / 'meshes').mkdir(parents=True)
    shutil.copy2(SOURCE / entry['path'], assets / entry['path'])
    if hull: shutil.copy2(SOURCE / entry['collision']['path'], assets / entry['collision']['path'])
    original_doc, _ = glb_parts((assets / entry['path']).read_bytes())
    slots = [int(material['name'].split('_')[1]) for material in original_doc['materials']]
    palette = ['paint'+str(i) for i in range(max(slots)+1)]
    material_values = {key: {'name': 'MI_'+key} for key in palette}
    transforms = [dict(translation_cm=[x, 20., 30.], rotation_xyzw=[0., 0., 0., 1.], scale=[1., 1., 1.])
                  for x in (10., 40.)]
    data = dict(meshes=[entry], placements=[dict(asset=entry['source_asset'], materials=palette, transform=t)
                                          for t in transforms], signs=[])
    out = tmp_path / 'out'
    source = SimpleNamespace(LIBRARY=assets, manifest=lambda: deepcopy(data),
                             sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
                             terrain=lambda: SimpleNamespace(height=lambda *a: 0.), triangles=lambda *a: [],
                             Surface=lambda *a: None)
    prepare = PIECES.prepare
    monkeypatch.setattr(PIECES, 'prepare', lambda entry, path: prepare(entry, path, triangle_limit=100))
    from test_belmonte_ground_pieces import GROUND, model as ground_model
    def surroundings():
        raw=ground_model(); result=[]
        for name in sorted(GROUND.NORTH):
            path=out/'glb'/(name+'.glb'); path.write_bytes(raw)
            result.append(dict(name=name,path='glb/'+path.name,sha256=hashlib.sha256(raw).hexdigest(),
                               triangles=4,bounds_m=[[0.,0.,0.],[20.,20.,0.]],slots=['Ground']))
        return result,{}
    namespace = dict(OUT=out, source=source, finish_surfaces=lambda data: deepcopy(material_values),
                     terrain=SimpleNamespace(VALLEY_CARVED_TILES=set(), OUTER=[0., 0., 10., 10.]),
                     model_pieces=PIECES, ground_pieces=GROUND, surroundings=surroundings,
                     planting=SimpleNamespace(replacements=lambda *a: ({}, {}), woodland=lambda *a: {}),
                     clear_railway=lambda *a: {}, map_zones=lambda *a: [], tv_spots=lambda *a: [],
                     L=SimpleNamespace(ORIGIN=[0., 0., 0.], BOUNDS=[0., 0., 10., 10.], RAILWAY={}, native_origin=lambda: [0., 0., 0.]),
                     shutil=shutil, json=json, np=np, Path=Path, source_records=source_records, retain_files=retain_files)
    script = REGION / 'build.py'
    body = [node for node in ast.parse(script.read_text()).body
            if isinstance(node, ast.FunctionDef) and node.name == 'main']
    exec(compile(ast.Module(body=body, type_ignores=[]), str(script), 'exec'), namespace)
    namespace['main']()
    runtime = json.loads((out / 'runtime.json').read_text())
    report = json.loads((out / 'build-report.json').read_text())
    assert len(report['meshes']) > 1
    groups = [group for group in runtime['groups'] if group['asset'].rsplit('.',1)[-1].startswith(entry['name']+'_Piece')]
    models = [row for row in report['meshes'] if row['name'].startswith(entry['name']+'_Piece')]
    assert len(groups) == len(models)
    assert len(json.loads((out/'ground/membership.json').read_text())['surfaces']) == 2
    assert all(group['transforms'] == transforms for group in groups)
    assert sum(group['collision'] for group in groups) == (1 if hull else len(groups))
    for group, model in zip(groups, models):
        doc, _ = glb_parts((out / model['path']).read_bytes())
        expected = [f'/Game/Belmonte/Materials/MI_paint{int(material["name"].split("_")[1])}.MI_paint{int(material["name"].split("_")[1])}'
                    for material in doc['materials']]
        assert group['materials'] == expected
        # The original parent span determines culling, irrespective of smaller child bounds.
        span = max(np.subtract(entry['bounds_m'][1], entry['bounds_m'][0]))
        assert group['cull_cm'] == (50000 if span < 8 else 0)
    assert not (out / 'glb' / Path(entry['path']).name).exists()
    if hull:
        assert (out / 'glb' / Path(entry['collision']['path']).name).read_bytes() == (assets / entry['collision']['path']).read_bytes()
