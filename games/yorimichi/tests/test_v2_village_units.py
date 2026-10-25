"""Actual Village D2 followers, selected MeshIR/manifest proofs and native finish refusals."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_collision, mesh_ir
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_village_units.py', 'village_units_test')
body = load(units.FINISH, 'village_finish_test')


@pytest.fixture(scope='module')
def geometry():
    factory = load('games/yorimichi/village_atomic_build.py', 'village_actual_factory_test')
    rows = extract(factory.steps(NS(out=ROOT / 'build/yorimichi')), checkout=ROOT, build_root=ROOT / 'build')
    return load('games/yorimichi/v2_geometry_templates.py', 'village_actual_templates_test').geometry_templates(rows, checkout=ROOT)


def natives():
    return {units.MATERIAL: {'unit': 'village.material.actual', 'item': 'asset', 'package': units.MATERIAL,
        'dependencies': [{'unit': 'village.texture.actual', 'item': 'texture', 'package': '/Game/Japan/Textures/T_Village'}]}}


def test_actual_twelve_parent_templates_bind_exact_items_complete_material_closure_and_original_outputs(geometry):
    before = deepcopy(geometry); result = units.attach_followers(geometry, natives(), checkout=ROOT)
    assert geometry == before
    assert len(result['templates']) == len(result['module_requirements']) == 12
    for template in result['templates']:
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['op'] == {'kind': 'unreal.raw_import', 'version': '1'}
        assert raw['outputs'][0]['class'] == 'RawStaticMesh' and raw['outputs'][0]['destination'] == 'store'
        assert raw['params']['destination'] == '/Game/_Raw/Village/$piece'
        assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': '$export', 'item': 'asset'}
        assert finish['op'] == {'kind': 'unreal.finish', 'version': '1'} and finish['script'] == units.FINISH
        assert finish['outputs'][0]['logical_path'] == units.DESTINATION + '/$piece'
        assert finish['outputs'][0]['destination'] == 'checkout' and len(finish['outputs'][0]['files']) == 6
        assert finish['inputs'][2]['source'] == {'kind': 'group_member', 'unit': template['producer'], 'group': 'geometry', 'piece': '$piece'}
        assert finish['inputs'][3]['source'] == {'kind': 'item', 'unit': 'world.village', 'item': 'product0'}
        assert finish['params']['input_roots'] == {'manifest': {'archive_member': 'products/0-0.tree.tar', 'name': 'atomic-manifest.json'}}
        assert finish['params']['args']['native_inputs'] == {'native0': units.MATERIAL, 'native1': '/Game/Japan/Textures/T_Village'}
        assert all((ROOT / p).is_file() for p in finish['code'])
        assert 'games/yorimichi/city_tile_products.py' in finish['code']
        assert 'games/yorimichi/village_atomic_products.py' in finish['code']
        assert result['module_requirements'][template['unit_prefix']][0]['name'] == 'Yorimichi'


@pytest.mark.parametrize('damage', ['missing_material', 'wrong_material', 'partial', 'encoding', 'foreign'])
def test_missing_roles_or_changed_original_family_refuse(geometry, damage):
    geometry = deepcopy(geometry); refs = natives()
    if damage == 'missing_material': refs = {}
    elif damage == 'wrong_material': refs[units.MATERIAL]['package'] = '/Game/Other'
    elif damage == 'partial': geometry['templates'].pop()
    elif damage == 'encoding': geometry['templates'][0]['params']['format'] = 'glb'
    else: geometry['templates'][0]['producer'] = 'other'
    with pytest.raises(ValueError): units.attach_followers(geometry, refs, checkout=ROOT)


class Props:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value
class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Material(Asset): pass
class Mesh(Asset):
    def get_num_triangles(self, lod): return self.triangles
    def get_num_lods(self): return self.lods
    def get_material(self, i): return self.material
    def set_material(self, i, value): self.material = value
    def get_editor_property(self, key): return self.body
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz', self.low))), max=NS(**dict(zip('xyz', self.high))))


def case(tmp_path, monkeypatch, *, ground=False, hull=False, degenerate=False):
    parent = 'Village_Ground' if ground else 'Village_Planting'; key = parent
    source = tmp_path / 'source'; payload = tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    piece = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], faces=[[0, 1, 2]],
                 normals=[[0., 0., 1.]] * 3, materials=[0], smooth=[False],
                 uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.]])], colours=[])
    if degenerate:
        piece['positions'] += [[0., 0., 0.], [.25, 0., 0.], [.5, 0., 0.]]
        piece['faces'].append([3, 4, 5]); piece['normals'] *= 2; piece['materials'] *= 2; piece['smooth'] *= 2
        piece['uvs'] = [('UVMap', piece['uvs'][0][1] * 2)]
    hulls = []
    if hull:
        tetra = dict(positions=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]], faces=[[0,1,2],[0,3,1],[1,3,2],[0,2,3]],
                     normals=[[0.,0.,1.]]*12, materials=[0]*4, smooth=[False]*4, uvs=[], colours=[])
        hulls = [mesh_collision.encode(tetra, slots=['Hull'], matrix=np.eye(4).tolist())]
    packet = mesh_ir.encode(piece, key=key, slots=['VillagePalette'], matrix=np.eye(4).tolist(), options={}, collisions=hulls)
    (payload / (key + '.npz')).write_bytes(packet)
    meta, decoded, facts = decode_mesh_payload(packet, expected_asset=key)
    (source / (key + '.fbx')).write_bytes(b'producer-verified FBX')
    receipt = publish_receipt(source, key=key, primary=key + '.fbx', triangles=facts['triangles'], bounds=[facts['min'], facts['max']],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'slots': ['VillagePalette'], 'polygons': facts['polygons'],
                  'collision_hulls': len(hulls), 'uv_channels': ['UVMap']})
    projection = body.ground_native_count(meta, decoded) if ground else {'native_triangles': facts['triangles'], 'native_removed_polygons': []}
    vertices = [[[p[0]*100, -p[1]*100, p[2]*100] for p in h['vertices']] for h in hulls]
    row = dict(name=key, triangles=facts['triangles'], min=facts['min'], max=facts['max'], collision_hulls=len(hulls),
               sha256=receipt['sha256'], geometry_sha256=receipt['metadata']['geometry_sha256'], uv_channels=['UVMap'], **projection)
    group = dict(source_triangles=facts['triangles'], source_collision_hulls=len(hulls), source_collision_vertices=vertices,
                 slots=['VillagePalette'], collision='complex_as_simple' if ground else 'simple_and_complex', pieces=[row])
    manifest = {'schema': 1, 'complete': True, 'parents': {p: group if p == parent else {} for p in body.ASSETS}}
    manifest_path = tmp_path / 'atomic-manifest.json'; manifest_path.write_text(json.dumps(manifest))
    raw_path = '/Game/_Raw/Village/' + key; dest = units.DESTINATION + '/' + key
    raw = Mesh(raw_path); raw.triangles = row['native_triangles']; raw.lods = raw.uvs = 1
    raw.simple, raw.convex = (0, 1) if hull else (1, 1); raw.hulls = vertices
    raw.material = None; raw.static_materials = [Props(imported_material_slot_name='VillagePalette')]
    raw.settings = Props(use_full_precision_u_vs=True); raw.body = Props(collision_trace_flag='old')
    raw.low, raw.high = body.native_bounds(row)
    material = Material(units.MATERIAL); assets = {raw_path: raw, units.MATERIAL: material}
    events = []; content = tmp_path / 'Content'; content.mkdir()
    state = NS(raw=raw, assets=assets, events=events, group=group, row=row, manifest=manifest, manifest_path=manifest_path,
               source=source, payload=payload, receipt=receipt, save_ok=True, cook_ok=True, remove_ok=True, post_save=False, primary=True)
    def duplicate(path, target):
        result = deepcopy(assets[path]); result.path = target; assets[target] = result; events.append('duplicate'); return result
    def remove(mesh):
        events.append('remove')
        if state.remove_ok: mesh.simple=mesh.convex=0; mesh.hulls=[]
        return state.remove_ok
    def save(mesh, dirty):
        assert dirty is True; events.append('save')
        if state.primary:
            path = content / (mesh.path.removeprefix('/Game/') + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'primary')
        if state.post_save: mesh.uvs = 2
        return state.save_ok
    def cooked(mesh, triangles, simple):
        events.append('validate'); assert simple is (not ground) and triangles == row['native_triangles']; return state.cook_ok
    editor = NS(get_lod_build_settings=lambda mesh,lod: mesh.settings, set_lod_build_settings=lambda mesh,lod,value: None,
        get_simple_collision_count=lambda mesh: mesh.simple, get_convex_collision_count=lambda mesh: mesh.convex,
        remove_collisions=remove, get_num_uv_channels=lambda mesh,lod: mesh.uvs)
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: editor, CollisionTraceFlag=NS(CTF_USE_SIMPLE_AND_COMPLEX='simple', CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda path: path in assets, duplicate_asset=duplicate, save_loaded_asset=save),
        CitySurfaceValidation=NS(collision_vertices=lambda mesh: json.dumps(mesh.hulls), validate_collision=cooked))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(job_dir=str(tmp_path), content_dir=str(content), inputs={'raw':'native-raw', 'source_export':str(source), 'payload':str(payload),
        'manifest':str(manifest_path), 'native0':'native-material'}, packages={'raw':[raw_path], 'source_export':[], 'payload':[], 'manifest':[], 'native0':[units.MATERIAL]},
        outputs=[dest], params={'op':'finish','kind':'static_mesh','source':'raw','destination':dest,'package_sources':{'raw':raw_path},
            'args':{'parent':parent,'payload':'payload','source_export':'source_export','manifest':'manifest','material':'native0','native_inputs':{'native0':units.MATERIAL}}})
    return state, context, unreal


@pytest.mark.parametrize('ground,hull,degenerate', [(False,False,False),(False,True,False),(True,False,True)])
def test_original_half_uv_collision_policy_whole_hulls_and_ground_native_count(tmp_path, monkeypatch, ground, hull, degenerate):
    state, context, _ = case(tmp_path, monkeypatch, ground=ground, hull=hull, degenerate=degenerate)
    before = deepcopy(state.raw.__dict__); mesh = body.run(context)
    assert state.raw.settings.values == before['settings'].values and state.raw.material is None
    assert mesh.body.values['collision_trace_flag'] == ('complex' if ground else 'simple')
    assert mesh.settings.values['use_full_precision_u_vs'] is False
    assert mesh.triangles == 1 and state.row['triangles'] == (2 if degenerate else 1)
    assert mesh.hulls == state.group['source_collision_vertices']
    assert state.events == ['duplicate', *([] if hull else ['remove']), 'validate', 'save', 'validate']


@pytest.mark.parametrize('damage', ['triangles','lod','uv','bounds','hull_geometry','slot','cook','save','post_save','primary','missing_validator','source_sha','manifest_projection','extra_payload'])
def test_invalid_current_sources_or_native_state_never_complete(tmp_path, monkeypatch, damage):
    state, context, unreal = case(tmp_path, monkeypatch, hull=True)
    if damage == 'triangles': state.raw.triangles += 1
    elif damage == 'lod': state.raw.lods = 2
    elif damage == 'uv': state.raw.uvs = 2
    elif damage == 'bounds': state.raw.low = [v+1 for v in state.raw.low]
    elif damage == 'hull_geometry': state.raw.hulls[0][0][0] += 10
    elif damage == 'slot': state.raw.static_materials[0].values['imported_material_slot_name'] = 'Other'
    elif damage == 'cook': state.cook_ok = False
    elif damage == 'save': state.save_ok = False
    elif damage == 'post_save': state.post_save = True
    elif damage == 'primary': state.primary = False
    elif damage == 'missing_validator': unreal.CitySurfaceValidation = None
    elif damage == 'source_sha': (state.source / (state.receipt['asset']+'.fbx')).write_bytes(b'changed')
    elif damage == 'manifest_projection':
        state.row['native_removed_polygons'] = [0]; state.manifest_path.write_text(json.dumps(state.manifest))
    else: (state.payload / 'foreign.npz').write_bytes(b'foreign')
    with pytest.raises(ValueError): body.run(context)


def test_actual_manifest_product_root_codec_supplies_exact_file_to_finish(tmp_path, monkeypatch):
    from atelier.build_v2 import recipe_job, unreal_inputs
    state, context, _ = case(tmp_path, monkeypatch)
    archive = tmp_path / 'inputs/manifest/products/0-0.tree.tar'; archive.parent.mkdir(parents=True)
    recipe_job.pack_root(state.manifest_path, archive)
    runtime = tmp_path / '.unreal-runtime'; runtime.mkdir()
    prepared = unreal_inputs.stage_inputs(tmp_path,
        [{'name':'manifest','path':'inputs/manifest','identity':{'state':'digest'}}], Path(context.content_dir),
        runtime_dir=runtime, root_bindings={'manifest':{'archive_member':'products/0-0.tree.tar','name':'atomic-manifest.json'}})
    context.inputs['manifest'] = prepared['inputs']['manifest']
    context.packages['manifest'] = prepared['packages']['manifest']
    assert Path(context.inputs['manifest']).is_file()
    assert body.run(context).get_path_name().split('.')[0] == context.outputs[0]


def test_extending_village_keeps_other_families_module_requirements(geometry):
    incoming = deepcopy(geometry)
    incoming['module_requirements'] = {'other.export.Parent': [{'name':'Other','kind':'Runtime','loading_phase':'Default'}]}
    result = units.attach_followers(incoming, natives(), checkout=ROOT)
    assert result['module_requirements']['other.export.Parent'] == incoming['module_requirements']['other.export.Parent']
