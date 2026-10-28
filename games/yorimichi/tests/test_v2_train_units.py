"""Exercise actual train recipe declarations, emitted native ABI and source/native bodies."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract
from atelier.gltf import glb_pack

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_train_units as train
from v2_texture_units import Unsupported
spec = importlib.util.spec_from_file_location('train_body_tests', GAME / 'world/train_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('train_recipe_tests', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules[spec.name] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    names = {'unreal.belmonte_train', 'world.belmonte_train', 'world.belmonte_train_service', 'world.belmonte_train_furniture_lods'}
    steps = [s for s in recipe.steps(context) if s.name in names]
    assert {s.name for s in steps} == names
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = []; step.reads = []; step.references = []
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


def test_cold_constructor_binds_actual_items_and_has_no_guessed_children(actual):
    value = train.train_units(actual, checkout=ROOT)
    assert set(value) == {'units', 'staged_inputs', 'content_slots', 'packages', 'aliases', 'module_requirements', 'templates', 'groups'}
    units = {u['id']: u for u in value['units']}
    source = units['train.members.vehicles']
    assert source['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.belmonte_train', 'item': 'product0'}
    assert any(i['source'] == {'kind': 'item', 'unit': 'world.belmonte_train_furniture_lods', 'item': 'output0'} for i in source['inputs'])
    assert set(value['aliases']['unreal.belmonte_train']) <= set(units)
    assert units['train.record.selected']['inputs'][0]['source'] == {'kind': 'group_member', 'unit': 'train.members.record', 'group': 'members', 'piece': 'Record'}
    assert len(value['templates']) == 6
    for key in ('unreal.belmonte_train.service', 'unreal.belmonte_train.record'):
        assert len(units[key]['outputs']) == 1
        assert len(units[key]['outputs'][0]['files']) == 1
    assert list(value['module_requirements']) == ['unreal.belmonte_train.vehicles']
    tokens = units['unreal.belmonte_train.record']['params']['args']['meshes']['derived_items']['templates']
    assert {t['producer'].removeprefix('train.members.'): t['follower'] for t in tokens} == {
        'vehicles': 3, 'doors': 1, 'furniture1': 1, 'furniture2': 2}
    for template in value['templates']:
        assert template['producer'] in value['groups']
        for follower in template['followers']:
            unit = follower['unit']
            assert set(follower['staged_inputs']) == {i['name'] for i in unit['inputs']}
            assert all((ROOT / p).is_file() for p in unit['code'])
    materials = next(t for t in value['templates'] if t['unit_prefix'].endswith('.materials'))
    assert [[o['class'] for o in f['unit']['outputs']] for f in materials['followers']] == [['Material'], ['MaterialInstance']]
    assert materials['followers'][1]['unit']['inputs'][1]['source'] == {'kind': 'item', 'unit': '$previous', 'item': 'parent'}
    assert all(len(f['unit']['outputs']) == 1 for f in materials['followers'])
    for kind, folder, count in [('vehicles', '', 3), ('doors', '/Doors', 1), ('furniture1', '/Furniture', 1), ('furniture2', '/Furniture', 2)]:
        template = next(t for t in value['templates'] if t['unit_prefix'].endswith('.' + kind))
        assert len(template['followers']) == count + 1
        finish = template['followers'][-1]['unit']
        assert finish['outputs'][0]['logical_path'] == train.DEST + folder + '/$piece'
        assert finish['params']['args']['levels'] == ['level' + str(i) for i in range(count)]
        assert all(o['destination'] == 'store' for f in template['followers'][:-1] for o in f['unit']['outputs'])


@pytest.mark.parametrize('damage', ['marker', 'service', 'bake', 'product'])
def test_recipe_drift_refuses(actual, damage):
    rows = deepcopy(actual); by_id = {r['id']: r for r in rows}
    if damage == 'marker': by_id['unreal.belmonte_train']['commands'][0]['marker'] = 'OTHER'
    elif damage == 'service': by_id['world.belmonte_train_service']['outputs'].pop()
    elif damage == 'bake': by_id['world.belmonte_train_furniture_lods']['outputs'][0] = 'other'
    else: by_id['world.belmonte_train']['products'][0]['optional_paths'] = ['other']
    with pytest.raises(Unsupported): train.train_units(rows, checkout=ROOT)


def library(tmp_path, monkeypatch):
    root = tmp_path / 'train'; root.mkdir()
    image = b'not decoded by projection: exact embedded image bytes'
    doc = {'asset': {'version': '2.0'}, 'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(image)}],
           'buffers': [{'byteLength': len(image)}], 'images': [{'bufferView': 0, 'mimeType': 'image/png'}],
           'textures': [{'source': 0, 'sampler': 0}], 'samplers': [{'wrapS': 33071, 'wrapT': 33648}],
           'materials': [{'name': 'Paint', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'roughnessFactor': .7}}]}
    raw = glb_pack(doc, image)
    def write(path, value):
        p = root / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value if isinstance(value, bytes) else json.dumps(value).encode())
    vehicle = {'id': 'restaurant', 'name': 'SM_BT_Restaurant', 'levels': [f'restaurant/LOD{i}.glb' for i in range(3)],
               'collision': [[0, 0, 0, 1, 2, 3]], 'switchable': [],
               'doors': [{'leaves': [{'glb': 'service/glb/door.glb', 'mesh': '/Game/BelmonteTrain/Doors/SM_Door.SM_Door'}]}]}
    furniture = {'mesh': '/Game/BelmonteTrain/Furniture/SM_BTF_Bench.SM_BTF_Bench',
                 'levels': [{'glb': 'lod/bench_LOD0.glb', 'screen_size': 1.}], 'cull_cm': 1400, 'shadow': False, 'two_sided': True}
    service = {'consist': {'vehicles': [vehicle]}, 'furniture': {'bench': furniture}, 'render': {'screen_sizes': [1., .2, .04]}}
    for path in vehicle['levels'] + ['service/glb/door.glb', 'furniture/lod/bench_LOD0.glb']: write(path, raw)
    write('service/service.json', service); write('manifest.json', {'coaches': {'restaurant': {'triangles': {'LOD0': 10}}}})
    calls = []
    monkeypatch.setattr(body, 'module', lambda *a: NS(preflight_service=lambda *a: calls.append('preflight')))
    return root, service, calls


def test_projection_preflights_and_preserves_lods_door_slots_and_sparse_pbr(tmp_path, monkeypatch):
    root, service, calls = library(tmp_path, monkeypatch)
    values = body.members(root, 'bake')
    assert calls == ['preflight']
    vehicle = values['meshes']['SM_BT_Restaurant']; door = values['meshes']['SM_Door']
    assert vehicle['materials'] == door['materials'] == {'Paint': 'SM_BT_Restaurant_Paint'}
    assert len(vehicle['levels']) == 3 and len(door['levels']) == 1
    assert values['materials']['SM_BTF_Bench_Paint']['ism'] is True
    assert values['materials']['SM_BTF_Bench_Paint']['two_sided'] is True
    assert len(values['images']) == 2 and set(values['materials']['SM_BT_Restaurant_Paint']['images']) == {'BaseColor'}
    assert values['record']['Record']['service'] == service
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / 'SM_Door.json').write_text(body.encode(door))
    output = tmp_path / 'member'; body.select(selected, output, 'SM_Door')
    assert (output / 'level0/source.glb').is_file() and not (output / 'level1').exists()
    assert json.loads((output / 'meta.json').read_text())['count'] == 1


def test_preflight_failure_exposes_no_members(tmp_path, monkeypatch):
    root, _, _ = library(tmp_path, monkeypatch)
    def fail(*a): raise ValueError('stale furniture bake')
    monkeypatch.setattr(body, 'module', lambda *a: NS(preflight_service=fail))
    with pytest.raises(ValueError, match='stale furniture'): body.project(root, 'bake', tmp_path / 'output', 'images')
    assert not (tmp_path / 'output').exists()


def test_selected_bytes_and_material_extensions_fail_closed(tmp_path):
    selected = tmp_path / 'selected'; selected.mkdir()
    value = {'name': 'Image', 'mime': 'image/png', 'bytes': 'YQ==', 'sha256': 'wrong'}
    (selected / 'Image.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Corrupt'): body.select(selected, tmp_path / 'output', 'Image')
    with pytest.raises(ValueError, match='extension'): body.pbr({'extensions': {'KHR_materials_transmission': {}}})
    assert body.pbr({'alphaMode': 'MASK', 'doubleSided': True}) == 'MI_Default_Mask_DS'

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, props
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
    def get_base_material(self): return self.props['parent']
    def get_num_lods(self): return self.props.get('lods', 1)
    def get_num_triangles(self, i): return 10 // (i + 1)
    def set_material(self, i, value): self.props.setdefault('bound', {})[i] = value
    def get_bounding_box(self): return NS(min=NS(x=0,y=0,z=0), max=NS(x=1,y=2,z=3))


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves, scalars, vectors, textures, switches, boxes = {}, [], {}, {}, {}, {}, []
    def duplicate(source, target):
        assets[target] = Asset(target, **deepcopy(assets[source.split('.')[0]].props)); return assets[target]
    def switch(instance, key, value): switches[key] = value; return False  # Actual SDK implementation returns false.
    def lod(asset, level, source, source_level, remap): asset.props['lods'] = level + 1; return level
    edit = NS(set_lod_from_static_mesh=lod, set_lod_screen_sizes=lambda a,s: a.props.update(sizes=s) or True,
              remove_collisions=lambda a: a.props.update(cleared=True), get_lod_screen_sizes=lambda a: a.props.get('sizes', [1.]))
    mel = NS(recompile_material=lambda a: None, set_material_instance_parent=lambda a,p: a.props.update(parent=p),
             set_material_instance_static_switch_parameter_value=switch,
             get_material_instance_static_switch_parameter_value=lambda a,k: switches[k],
             set_material_instance_scalar_parameter_value=lambda a,k,v: scalars.update({k:v}),
             set_material_instance_vector_parameter_value=lambda a,k,v: vectors.update({k:v}),
             set_material_instance_texture_parameter_value=lambda a,k,v: textures.update({k:v}), update_material_instance=lambda a: None)
    unreal = NS(EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.')[0]), duplicate_asset=duplicate,
                 save_loaded_asset=lambda a,d=False: saves.append(a.path) or True), MaterialEditingLibrary=mel,
                get_editor_subsystem=lambda cls: edit, StaticMeshEditorSubsystem=object,
                BelmonteTrainImportLibrary=NS(set_simple_boxes=lambda a,b: boxes.extend(b) or len(b)),
                CollisionTraceFlag=NS(CTF_USE_SIMPLE_AS_COMPLEX='simple'),
                TextureCompressionSettings=NS(TC_NORMALMAP='normal', TC_DEFAULT='default'),
                TextureFilter=NS(TF_DEFAULT='default', TF_NEAREST='nearest', TF_BILINEAR='bilinear', TF_TRILINEAR='trilinear'),
                TextureAddress=NS(TA_WRAP='wrap', TA_CLAMP='clamp', TA_MIRROR='mirror'),
                LinearColor=lambda *v: list(v), log_warning=lambda s: None)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    def original(ctx, u, names): return {'box': lambda b: list(b)}
    monkeypatch.setattr(body, 'original', original)
    return NS(root=tmp_path, assets=assets, saves=saves, scalars=scalars, vectors=vectors, textures=textures,
              switches=switches, boxes=boxes, unreal=unreal)


def stage(editor, meta):
    path = editor.root / 'meta'; path.mkdir(exist_ok=True); (path / 'meta.json').write_text(body.encode(meta)); return str(path)


def derived(mapping):
    return {'derived_items': {'members': [{'piece': k, 'slot': v} for k,v in mapping.items()]}}


@pytest.mark.parametrize('clearcoat', [False, True])
def test_pbr_owner_preserves_sdk_parent_factors_sampler_and_owned_ism_copy(editor, clearcoat):
    key = 'Bench_Paint'; original_parent = Asset('/InterchangeAssets/gltf/M_Default', used_with_instanced_static_meshes=False)
    parent_name = 'MI_ClearCoat_Opaque' if clearcoat else 'MI_Default_Opaque'
    default = Asset('/InterchangeAssets/gltf/MaterialInstances/' + parent_name, parent=original_parent,
                    base_property_overrides=Asset('overrides'))
    editor.assets[original_parent.path] = original_parent; editor.assets[default.path] = default
    image = Asset('/Game/BelmonteTrain/Textures/T_Bench_Paint_BaseColor'); editor.assets[image.path] = image
    reference = {'index': 0, 'extensions': {'KHR_texture_transform': {'offset': [.2,.3], 'scale': [2,3], 'rotation': -.5, 'texCoord': 1}}}
    meta = {'name': key, 'parent': parent_name, 'ism': True, 'two_sided': True,
            'record': {'pbrMetallicRoughness': {'baseColorFactor': [.1,.2,.3,1], 'metallicFactor': .2, 'roughnessFactor': .7},
                       'emissiveFactor': [.2,.3,.4], 'extensions': {'KHR_materials_emissive_strength': {'emissiveStrength': 5}}},
            'images': {'BaseColor': {'piece': 'Bench_Paint_BaseColor', 'reference': reference, 'sampler': {'wrapS': 33071, 'wrapT': 33648}}}}
    if clearcoat: meta['record']['extensions']['KHR_materials_clearcoat'] = {'clearcoatFactor': .6, 'clearcoatRoughnessFactor': .2}
    package, parent = body.ROOT + '/Materials/MI_' + key, body.ROOT + '/Materials/M_' + key
    selected = stage(editor, meta)
    parent_args = {'action': 'material_parent', 'name': key, 'meta': 'meta'}
    parent_ctx = NS(job_dir=str(editor.root), inputs={'meta': selected}, packages={'meta': []},
                    outputs=[parent], params={'args': parent_args})
    body.run(parent_ctx)
    parent_props = deepcopy(editor.assets[parent].props)
    args = {'action': 'material', 'name': key, 'meta': 'meta', 'parent': 'parent', 'images': derived({'Bench_Paint_BaseColor': 'image'})}
    ctx = NS(job_dir=str(editor.root), inputs={'meta': selected, 'image':'x', 'parent': 'x'},
             packages={'meta':[], 'image':[image.path], 'parent': [parent]}, outputs=[package], params={'args':args})
    asset = body.run(ctx)
    assert asset.path == package and editor.saves == [parent, package]
    assert original_parent.props['used_with_instanced_static_meshes'] is False
    assert editor.assets[parent].props['used_with_instanced_static_meshes'] is True
    assert editor.assets[parent].props == parent_props
    assert asset.props['base_property_overrides'].props == {'override_two_sided': True, 'two_sided': True}
    assert editor.scalars['RoughnessFactor'] == .7 and editor.scalars['EmissiveStrength'] == 5
    assert editor.vectors['BaseColorTexture_TilingMethod'] == [1.,2.,0.,0.]
    assert editor.vectors['BaseColorTexture_OffsetScale'] == [.2,.3,2,3]
    assert editor.scalars['BaseColorTexture_TexCoord'] == 1
    assert editor.switches['bHasBaseColorTexture'] is True and editor.switches['bHasNormalTexture'] is False
    assert editor.textures['BaseColorTexture'] is image
    if clearcoat:
        assert editor.scalars['ClearCoatFactor'] == .6 and editor.scalars['ClearCoatRoughnessFactor'] == .2
        assert editor.switches['bHasClearCoatTexture'] is False


@pytest.mark.parametrize('kind,count', [('vehicle',3), ('door',1), ('furniture',2)])
def test_mesh_finish_uses_actual_lod_count_materials_boxes_and_door_collision(editor, kind, count):
    key = 'SM_Test'; folder = '/Furniture/' if kind == 'furniture' else '/Doors/' if kind == 'door' else '/'
    package = body.ROOT + folder + key
    slot = Asset('slot', imported_material_slot_name='Paint')
    raw = Asset('/Game/_Raw/Mesh', static_materials=[slot], body_setup=Asset('body'), lods=1)
    material = Asset(body.ROOT + '/Materials/MI_Test'); editor.assets[raw.path]=raw; editor.assets[material.path]=material
    meta = {'name':key, 'kind':kind, 'count':count, 'screen_sizes':[1.,.2,.04], 'materials':{'Paint':'Paint'},
            'spec': {'collision':[[0,0,0,1,2,3]]}, 'expected':{'triangles':{'LOD0':10}}}
    args = {'action':'mesh', 'name':key, 'meta':'meta', 'levels':['raw','raw','raw'], 'materials':derived({'Paint':'material'})}
    ctx = NS(job_dir=str(editor.root), inputs={'meta':stage(editor,meta),'raw':'x','material':'x'},
             packages={'meta':[],'raw':[raw.path],'material':[material.path]}, outputs=[package], params={'args':args})
    asset = body.run(ctx)
    assert asset.get_num_lods() == count and asset.props['cleared'] is True and asset.props['bound'][0] is material
    assert editor.saves == [package] and 'bound' not in raw.props
    if kind == 'vehicle': assert editor.boxes == [[0,0,0,1,2,3]] and asset.props['lod_for_collision'] == 0
    if kind == 'door': assert asset.props['body_setup'].props['collision_trace_flag'] == 'simple'
    editor.unreal.EditorAssetLibrary.save_loaded_asset=lambda *a: False
    with pytest.raises(RuntimeError, match='save failed'): body.run(ctx)


def test_texture_finish_keeps_normal_maps_linear_and_does_not_change_raw(editor):
    raw = Asset('/Game/_Raw/Texture', srgb=True); editor.assets[raw.path]=raw
    meta = {'name':'Normal', 'role':'Normal', 'sampler':{'minFilter':9985, 'wrapS':33071, 'wrapT':33648}}; destination = body.ROOT + '/Textures/T_Normal'
    ctx = NS(job_dir=str(editor.root), inputs={'meta':stage(editor,meta),'raw':'x'}, packages={'meta':[],'raw':[raw.path]},
             outputs=[destination], params={'args':{'action':'texture','meta':'meta'}, 'source':'raw','destination':destination})
    asset = body.run(ctx)
    assert asset.props['srgb'] is False and asset.props['compression_settings'] == 'normal' and raw.props['srgb'] is True

    assert asset.props['flip_green_channel'] is True and asset.props['filter'] == 'bilinear'
    assert asset.props['address_x'] == 'clamp' and asset.props['address_y'] == 'mirror'


def test_projection_uses_real_bake_preflight_and_refuses_stale_service(tmp_path):
    import shutil
    from test_belmonte_train_service import S, write_fixture
    root = tmp_path / 'belmonte-train'; write_fixture(root)
    service = S.build(root)
    raw = root / 'furniture/lod/canteen-mug_LOD0.glb'
    for vehicle in service['consist']['vehicles']:
        for relative in vehicle['levels']:
            path = root / relative; path.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(raw, path)
    path = root / 'service/service.json'; path.parent.mkdir(exist_ok=True); path.write_text(json.dumps(service))
    (root / 'manifest.json').write_text(json.dumps({'coaches': {}}))
    result = body.members(root, ROOT / train.BAKE)
    assert len(result['meshes']) == len(service['consist']['vehicles']) + len(service['furniture'])
    service['sources']['furniture_bake'] = '0' * 64; path.write_text(json.dumps(service))
    with pytest.raises(ValueError, match='stale'):
        body.project(root, ROOT / train.BAKE, tmp_path / 'refused', 'materials')
    assert not (tmp_path / 'refused').exists()


@pytest.mark.parametrize('field', ['service', 'report'])
def test_data_author_abi_owns_one_json_and_preserves_report_sources(editor, field):
    asset = Asset(body.ROOT + '/SM_Test', lods=3, sizes=[1.,.2,.04]); editor.assets[asset.path]=asset
    vehicle = {'name':'SM_Test', 'collision':[[0,0,0,1,2,3]], 'switchable':[], 'doors':[]}
    service = {'consist':{'vehicles':[vehicle]}, 'furniture':{}}
    meta = {'service':service, 'sources':{'SM_Test':{'LOD0.glb':'abc'}}}
    args = {'action':'record', 'field':field, 'meta':'meta', 'meshes':derived({'SM_Test':'mesh'})}
    output = body.ROSTER if field == 'service' else body.REPORT
    ctx = NS(job_dir=str(editor.root), inputs={'meta':stage(editor,meta),'mesh':'x'},
             packages={'meta':[],'mesh':[asset.path]}, outputs=[], data_outputs=[output], params={'args':args})
    result = body.run(ctx)
    assert list(result) == [output]
    if field == 'service': assert result[output] == service
    else:
        assert result[output]['vehicles']['SM_Test']['sources'] == {'LOD0.glb':'abc'}
        assert result[output]['vehicles']['SM_Test']['triangles'] == [10,5,3]
    ctx.data_outputs = [body.ROSTER, body.REPORT]
    with pytest.raises(ValueError, match='exactly its one'): body.run(ctx)


def test_door_preserves_unmatched_original_leaf_material(tmp_path, monkeypatch):
    from atelier.gltf import glb_parts
    root, _, _ = library(tmp_path, monkeypatch)
    path = root / 'service/glb/door.glb'; gltf, binary = glb_parts(path.read_bytes())
    gltf['materials'][0]['name'] = 'LeafOnly'; path.write_bytes(glb_pack(gltf, binary))
    values = body.members(root, 'bake')
    assert values['meshes']['SM_Door']['materials'] == {'LeafOnly': 'SM_Door_LeafOnly'}
    assert values['materials']['SM_Door_LeafOnly']['ism'] is False
