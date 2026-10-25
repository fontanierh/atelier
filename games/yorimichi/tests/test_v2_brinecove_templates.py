"""Original coastal declarations, finite member projection and native roster joins."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2 import file_groups, recipe_job
from atelier.build_v2.recipe_dependencies import extract
from atelier import encoded_glb
from atelier.gltf import glb_parts, glb_pack
from test_encoded_region_plan import model

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]
import v2_brinecove_templates as family
import brinecove_members_v2 as body
import brinecove_material_v2 as shader


def load(path):
    spec = importlib.util.spec_from_file_location('brinecove_actual_recipe', ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


@pytest.fixture(scope='module')
def rows():
    factory = load('games/yorimichi/build.py')
    steps = factory.brinecove_steps(ROOT / 'build/yorimichi')
    selected = [s for s in steps if s.name in ('world.brinecove', 'unreal.brinecove')]
    for step in selected:
        step.reads = []; step.needs = []; step.after = []
    return extract(selected, checkout=ROOT, build_root=ROOT / 'build')


def test_actual_original_product_has_complete_family_and_no_invented_ids(rows):
    geometry = {'templates': [], 'groups': {}}
    packet = family.attach_followers(geometry, rows=rows, checkout=ROOT, natives={})
    assert geometry == {'templates': [], 'groups': {}}
    assert packet['missing_roles'] == []
    assert len(packet['templates']) == 3 and len(packet['geometry']['templates']) == 3
    assert set(packet['geometry']['groups']) == set(packet['groups'])
    assert packet['aliases']['unreal.brinecove'] == ('unreal.brinecove.complete',)
    assert len(packet['packages']) == 4  # Only the statically known shader parents.
    assert packet['runtime_data']['root']['archive_member'] == 'products/0-2.tree.tar'
    assert packet['source_join']['retained'] is True
    assert all((ROOT / p).is_file() for u in packet['units'] for p in u['code'])
    material, texture, mesh = packet['templates']
    author = material['followers'][0]['unit']
    finish = mesh['followers'][1]['unit']
    assert author['params']['args']['textures'] == packet['texture_items']
    assert finish['params']['args']['materials'] == packet['material_items']
    assert finish['params']['partners'] == packet['texture_items']
    assert len(finish['inputs']) == 7  # raw/export/payload and four parent closure Items
    assert all(t['derive_payload'] is False for t in packet['templates'])
    assert all(t['unit_prefix'] in packet['module_requirements'] for t in packet['templates'])
    bad = deepcopy(rows)
    next(r for r in bad if r['id'] == 'world.brinecove')['products'][0]['paths'].pop()
    with pytest.raises(ValueError, match='complete original'): family.attach_followers(geometry, rows=bad, checkout=ROOT)


def case(tmp_path):
    glb = tmp_path / 'glb'; glb.mkdir()
    textures = tmp_path / 'textures'; textures.mkdir()
    doc, binary = glb_parts(model()); doc['materials'][0]['name'] = 'BC_hero_test_0'
    raw = glb_pack(doc, binary); facts = encoded_glb.geometry(raw)
    name = 'SM_BC_Hero_Test'
    (glb / (name + '.glb')).write_bytes(raw)
    image = 'T_BC_hero_test_0.jpg'; (textures / image).write_bytes(b'original-jpeg-pixels')
    descriptor = {'name': 'MI_BC_hero_test_0', 'colour': [.21, .34, .55], 'texture': image,
                  'kind': 'opaque', 'pan': 0., 'roughness': .8, 'metal': False}
    report = {'materials': {'hero_test_0': descriptor}, 'meshes': [{'name': name, 'path': 'glb/' + name + '.glb',
        'sha256': hashlib.sha256(raw).hexdigest(), 'triangles': facts['triangles'], 'bounds_m': facts['bounds'],
        'slots': ['hero_test_0'], 'collision': True}]}
    runtime = {'groups': [{'asset': body.ROOT + '/Meshes/' + name + '.' + name,
        'materials': [body.ROOT + '/Materials/MI_BC_hero_test_0.MI_BC_hero_test_0'], 'collision': True}]}
    r = tmp_path / 'report.json'; r.write_text(json.dumps(report))
    rt = tmp_path / 'runtime.json'; rt.write_text(json.dumps(runtime))
    return r, rt, textures, glb, report


def test_exact_descriptor_pixels_mesh_policy_and_selected_recipe_body(tmp_path):
    r, rt, textures, glb, report = case(tmp_path)
    for kind in family.KINDS:
        out = tmp_path / ('projected-' + kind)
        body.project(r, rt, textures, glb, out, kind)
        group = file_groups.write_file_set(out, tmp_path / ('group-' + kind), parent='Coastal_' + kind,
            selectors=['*.mesh'] if kind == 'meshes' else ['*.png', '*.jpg'] if kind == 'textures' else ['*.json'])
        assert len(group['pieces']) == 1
        piece = group['pieces'][0]['name']
        target = tmp_path / ('selected-' + kind)
        body.select(out, target, piece, kind)
        if kind == 'materials':
            assert json.loads((target / (piece + '.json')).read_text())['descriptor'] == report['materials']['hero_test_0']
        elif kind == 'textures':
            assert (target / 'T_BC_hero_test_0.jpg').read_bytes() == b'original-jpeg-pixels'
            assert json.loads((target / 'export.json').read_text())['primary'].endswith('.jpg')
        else:
            identity, raw = encoded_glb.decode((out / (piece + '.mesh')).read_bytes())
            assert raw == (glb / (piece + '.glb')).read_bytes()
            assert identity['metadata']['native_policy'] == {'collision': True, 'lods': False, 'material_kinds': {'BC_hero_test_0': 'opaque'}}
            import brinecove_finish_v2
            ctx = NS(job_dir=tmp_path, inputs={'source': target, 'payload': out},
                params={'args': {'source_export': 'source', 'payload': 'payload'}})
            assert brinecove_finish_v2.source_facts(ctx)['triangles'] == report['meshes'][0]['triangles']
    view = tmp_path / 'view'; path = view / family.BODY; path.parent.mkdir(parents=True); path.write_bytes((ROOT / family.BODY).read_bytes())
    selected = view / 'selected'; selected.mkdir(); src = tmp_path / 'projected-materials/MI_BC_hero_test_0.json'
    (selected / src.name).write_bytes(src.read_bytes())
    binding = family._call(ROOT, 'select', (ROOT / 'selected', ROOT / 'member', 'MI_BC_hero_test_0', 'materials'))['call']
    recipe_job.bind(binding, view)()
    assert (view / 'member' / src.name).read_bytes() == src.read_bytes()


@pytest.mark.parametrize('damage', ['descriptor', 'missing_texture', 'extra_texture', 'changed_mesh', 'runtime', 'duplicate', 'policy'])
def test_corrupt_or_incomplete_original_library_refuses_before_output(tmp_path, damage):
    r, rt, textures, glb, report = case(tmp_path)
    if damage == 'descriptor': report['materials']['hero_test_0']['colour'] = [float('inf')] * 3
    elif damage == 'missing_texture': (textures / 'T_BC_hero_test_0.jpg').unlink()
    elif damage == 'extra_texture': (textures / 'foreign.png').write_bytes(b'x')
    elif damage == 'changed_mesh': (glb / 'SM_BC_Hero_Test.glb').write_bytes(b'changed')
    elif damage == 'runtime': rt.write_text(json.dumps({'groups': []}))
    elif damage == 'duplicate': report['meshes'].append(deepcopy(report['meshes'][0]))
    else: report['meshes'][0]['collision'] = 1
    r.write_text(json.dumps(report)); out = tmp_path / 'output'
    with pytest.raises(ValueError): body.project(r, rt, textures, glb, out, 'meshes')
    assert not out.exists()


def test_final_gate_requires_exact_original_native_roster(tmp_path):
    r, rt, textures, glb, report = case(tmp_path)
    def native(piece, prefix):
        root = tmp_path / piece; path = root / ('content/Game/Brinecove/' + prefix + '/' + piece + '.uasset')
        path.parent.mkdir(parents=True); path.write_bytes(b'fixture-native')
        return NS(products=[NS(paths=(root,))]), piece
    meshes = [native('SM_BC_Hero_Test', 'Meshes')]
    materials = [native('MI_BC_hero_test_0', 'Materials')]
    images = [native('T_BC_hero_test_0', 'Textures')]
    with pytest.raises(ValueError, match='Incomplete'): body.complete(r, rt, textures, (), materials, images, (), tmp_path / 'missing')
    report_root = tmp_path / 'native-reports'; report_path = report_root / 'data/reports/SM_BC_Hero_Test.json'
    report_path.parent.mkdir(parents=True)
    low, high = report['meshes'][0]['bounds_m']
    report_path.write_text(json.dumps({'name': 'SM_BC_Hero_Test', 'triangles': report['meshes'][0]['triangles'],
        'bounds_cm': [low[0]*100, -high[1]*100, low[2]*100, high[0]*100, -low[1]*100, high[2]*100],
        'collision': True, 'lods': False, 'slots': ['BC_hero_test_0'], 'uv_channels': 1}))
    reports = [(NS(products=[NS(paths=(report_root,))]), 'SM_BC_Hero_Test')]
    body.complete(r, rt, textures, meshes, materials, images, reports, tmp_path / 'complete')
    assert json.loads((tmp_path / 'complete/runtime.json').read_text()) == json.loads(rt.read_text())


def test_selected_instance_binds_real_native_texture_and_parent_items(tmp_path, monkeypatch):
    r, rt, textures, glb, report = case(tmp_path)
    spec_root = tmp_path / 'spec'; spec_root.mkdir()
    piece = 'MI_BC_hero_test_0'
    (spec_root / (piece + '.json')).write_text(json.dumps({'key': 'hero_test_0', 'descriptor': report['materials']['hero_test_0']}))
    token = {'derived_items': {'root': 'derived/textures', 'members': [
        {'piece': 'T_BC_hero_test_0', 'root': 'native/image', 'slot': 'image'}]}}
    context = NS(job_dir=tmp_path, inputs={'spec': spec_root, 'parent': 'parent-item', 'image': 'image-item'},
        packages={'spec': [], 'parent': ['/Game/Brinecove/Materials/M_Brinecove'], 'image': ['/Game/Brinecove/Textures/T_BC_hero_test_0']},
        params={'settings': [], 'args': {'factory': 'selected_instance', 'piece': piece,
            'parents': {'M_Brinecove': 'parent'}, 'textures': token}})
    monkeypatch.setattr(shader, 'run', lambda normalized: normalized)
    result = shader.selected_instance(context)
    assert result.params['args']['descriptor'] == report['materials']['hero_test_0']
    assert result.params['args']['inputs'] == {'parent': '/Game/Brinecove/Materials/M_Brinecove',
        'image': '/Game/Brinecove/Textures/T_BC_hero_test_0'}
    assert result.inputs == {'parent': 'parent-item', 'image': 'image-item'}
    context.inputs.pop('image')
    with pytest.raises(ValueError, match='Missing actual'): shader.selected_instance(context)


@pytest.mark.parametrize('piece,srgb', [('T_BC_hero_test_0', True), ('T_BC_terrain_rock_n', False)])
def test_selected_texture_finish_preserves_original_settings(tmp_path, monkeypatch, piece, srgb):
    import atelier.build_v2.unreal_ops as ops
    monkeypatch.setitem(sys.modules, 'unreal', NS())
    monkeypatch.setattr(ops, 'finish', lambda context, unreal: context)
    context = NS(params={'op': 'finish', 'kind': 'texture', 'source': 'raw',
        'destination': '/Game/Brinecove/Textures/' + piece, 'args': {'texture_piece': piece}})
    result = shader.texture_finish(context)
    assert result.params['properties'] == {'srgb': srgb, 'max_texture_size': 1024,
        'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}}
    assert 'args' not in result.params and 'args' in context.params
