"""SwordCamp atlas/material owners and per-piece followers over the actual rows, plus native finish refusals."""
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


units = load('games/yorimichi/v2_swordcamp_units.py', 'swordcamp_units_test')
body = load(units.FINISH, 'swordcamp_finish_test')
CATALOGUE = load(units.CATALOGUE, 'swordcamp_catalogue_test').ASSETS


@pytest.fixture(scope='module')
def actual():
    recipe = load('games/yorimichi/build.py', 'swordcamp_recipe_test')
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [s for s in recipe.steps(context) if s.name.startswith('world.swordcamp') or s.name == 'unreal.swordcamp']
    rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    geometry = load('games/yorimichi/v2_geometry_templates.py', 'swordcamp_templates_test').geometry_templates(rows, checkout=ROOT)
    return rows, geometry


def test_atlas_and_both_original_materials_from_actual_product(actual):
    rows, _ = actual
    result = units.author_units(rows, checkout=ROOT)
    raw, finish, camp, ronin = result['units']
    producer = next(r for r in rows if r['id'] == 'world.swordcamp_atlas')
    index = [p['id'] for p in producer['products']].index('swordcamp.atlas')
    assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.swordcamp_atlas', 'item': f'product{index}'}
    assert raw['params']['input_roots'] == {'source': {'archive_member': f'products/{index}-0.tree.tar', 'name': 'swordcamp_atlas.jpg'}}
    assert raw['outputs'][0]['destination'] == 'store'
    assert finish['params']['properties'] == {'srgb': True, 'max_texture_size': 2048,
                                              'lod_group': {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}}
    assert finish['outputs'][0]['logical_path'] == units.ATLAS and finish['outputs'][0]['destination'] == 'checkout'
    for unit, function, package in ((camp, 'build_material', units.MATERIAL),
                                    (ronin, 'build_ronin_body_material', '/Game/SwordCamp/Materials/M_RoninBody')):
        assert unit['script'] == units.AUTHOR and unit['outputs'][0]['class'] == 'Material'
        assert unit['params']['args'] == {'module': units.ORIGINAL, 'function': function, 'arguments': [{'native_input': 'atlas'}],
                                          'keyword_arguments': {}, 'expected_package': package}
        assert unit['inputs'] == [{'role': 'content', 'name': 'atlas', 'source': {'kind': 'item', 'unit': finish['id'], 'item': 'texture'}}]
        assert {'games/yorimichi/unreal/Scripts/atmosphere.py', 'games/yorimichi/unreal/Scripts/mesh_import.py',
                'games/yorimichi/world/yori.py'} <= set(unit['code'])
        assert result['packages'][package]['dependencies'] == [units.ATLAS]


def test_every_catalogue_parent_gains_followers_over_the_supplied_material(actual):
    rows, geometry = actual
    natives = units.author_units(rows, checkout=ROOT)['packages']
    before = deepcopy(geometry); result = units.attach_followers(geometry, natives, checkout=ROOT)
    assert geometry == before
    templates = {t['unit_prefix'].removeprefix('world.swordcamp.export.'): t for t in result['templates']
                 if t['unit_prefix'].startswith('world.swordcamp.export.')}
    assert sorted(templates) == sorted(CATALOGUE)
    for parent, template in templates.items():
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['params']['fbx'] == units.FBX and raw['params']['destination'] == '/Game/_Raw/SwordCamp/$piece'
        assert finish['outputs'][0]['logical_path'] == '/Game/SwordCamp/Assets/$piece'
        assert finish['inputs'][2]['source'] == {'kind': 'group_member', 'unit': 'world.swordcamp.geometry.' + parent,
                                                 'group': 'geometry', 'piece': '$piece'}
        args = finish['params']['args']
        assert args['collision'] == ('simple_and_complex' if parent in units.SOLID_PROPS else 'default')
        assert args['native_inputs'] == {'native0': units.MATERIAL, 'native1': units.ATLAS} and args['material'] == 'native0'
        assert result['module_requirements'][template['unit_prefix']][0]['name'] == 'Yorimichi'
        assert all((ROOT / p).is_file() for p in finish['code'])


@pytest.mark.parametrize('damage', ['missing', 'transitive', 'partial', 'format', 'foreign', 'attached'])
def test_missing_roles_or_changed_family_refuse(actual, damage):
    rows, geometry = deepcopy(actual[0]), deepcopy(actual[1])
    natives = units.author_units(rows, checkout=ROOT)['packages']
    camp = [t for t in geometry['templates'] if t['unit_prefix'].startswith('world.swordcamp.export.')]
    if damage == 'missing': del natives[units.MATERIAL]
    elif damage == 'transitive': del natives[units.ATLAS]
    elif damage == 'partial': geometry['templates'].remove(camp[0])
    elif damage == 'format': camp[0]['params']['format'] = 'glb'
    elif damage == 'foreign': camp[0]['producer'] = 'other'
    else: camp[0]['followers'] = [{}]
    with pytest.raises(ValueError):
        units.attach_followers(geometry, natives, checkout=ROOT)


@pytest.mark.parametrize('damage', ['import', 'atlas'])
def test_changed_rows_refuse(actual, damage):
    rows = deepcopy(actual[0])
    if damage == 'import': next(r for r in rows if r['id'] == 'unreal.swordcamp')['commands'][0]['marker'] = 'DONE'
    else: next(r for r in rows if r['id'] == 'world.swordcamp_atlas')['products'] = []
    with pytest.raises(ValueError):
        units.author_units(rows, checkout=ROOT)


# ---- finish body ----------------------------------------------------------------------------------------------------

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
    def get_num_lods(self): return 1
    def get_material(self, i): return self.material
    def set_material(self, i, value): self.material = value
    def get_editor_property(self, key): return self.body
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz', self.low))), max=NS(**dict(zip('xyz', self.high))))


def case(tmp_path, monkeypatch, *, parent='SM_CampFirePit', hull=True):
    source = tmp_path / 'source'; payload = tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    piece = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], faces=[[0, 1, 2]],
                 normals=[[0., 0., 1.]] * 3, materials=[0], smooth=[False],
                 uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.]])], colours=[])
    hulls = []
    if hull:
        tetra = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], faces=[[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]],
                     normals=[[0., 0., 1.]] * 12, materials=[0] * 4, smooth=[False] * 4, uvs=[], colours=[])
        hulls = [mesh_collision.encode(tetra, slots=['Hull'], matrix=np.eye(4).tolist())]
    packet = mesh_ir.encode(piece, key=parent, slots=['M_SwordCamp'], matrix=np.eye(4).tolist(), options={}, collisions=hulls)
    (payload / (parent + '.npz')).write_bytes(packet)
    _meta, _decoded, facts = decode_mesh_payload(packet, expected_asset=parent)
    (source / (parent + '.fbx')).write_bytes(b'producer-verified FBX')
    publish_receipt(source, key=parent, primary=parent + '.fbx', triangles=facts['triangles'], bounds=[facts['min'], facts['max']],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'slots': ['M_SwordCamp'], 'polygons': facts['polygons'],
                  'collision_hulls': len(hulls), 'uv_channels': ['UVMap']})
    raw_path = '/Game/_Raw/SwordCamp/' + parent; dest = '/Game/SwordCamp/Assets/' + parent
    raw = Mesh(raw_path); raw.triangles = facts['triangles']; raw.uvs = 1; raw.material = None
    raw.hulls = [[[p[0] * 100, -p[1] * 100, p[2] * 100] for p in h['vertices']] for h in hulls]
    raw.static_materials = [Props(imported_material_slot_name='M_SwordCamp')]
    raw.body = Props(collision_trace_flag='old'); raw.low, raw.high = body.native_bounds(facts)
    assets = {raw_path: raw, units.MATERIAL: Material(units.MATERIAL), units.ATLAS: Asset(units.ATLAS)}
    content = tmp_path / 'Content'; content.mkdir()
    state = NS(raw=raw, assets=assets, saves=[], cooked=[], save_ok=True, cook_ok=True)
    def duplicate(path, target):
        result = deepcopy(assets[path]); result.path = target; assets[target] = result; return result
    def save(mesh, dirty):
        assert dirty is True
        path = content / (mesh.path.removeprefix('/Game/') + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'primary')
        state.saves.append(mesh.path); return state.save_ok
    def cooked(mesh, triangles, authored):
        state.cooked.append((triangles, authored)); return state.cook_ok
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: NS(get_num_uv_channels=lambda mesh, lod: mesh.uvs),
        CollisionTraceFlag=NS(CTF_USE_SIMPLE_AND_COMPLEX='simple_and_complex', CTF_USE_DEFAULT='default'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda path: path in assets, duplicate_asset=duplicate, save_loaded_asset=save),
        CitySurfaceValidation=NS(collision_vertices=lambda mesh: json.dumps(mesh.hulls), validate_collision=cooked))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    native = {'native0': units.MATERIAL, 'native1': units.ATLAS}
    context = NS(job_dir=str(tmp_path), content_dir=str(content),
        inputs={'raw': 'native-raw', 'source_export': str(source), 'payload': str(payload), **dict.fromkeys(native, 'native')},
        packages={'raw': [raw_path], 'source_export': [], 'payload': [], **{k: [v] for k, v in native.items()}},
        outputs=[dest], params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
            'package_sources': {'raw': raw_path}, 'settings': [],
            'args': {'parent': parent, 'collision': 'simple_and_complex' if parent in units.SOLID_PROPS else 'default',
                     'payload': 'payload', 'source_export': 'source_export', 'material': 'native0', 'native_inputs': native}})
    return state, context


@pytest.mark.parametrize('parent,hull', [('SM_CampFirePit', True), ('SM_RoninKatana', False), ('SM_RoninKasa', True)])
def test_original_material_and_collision_policy(tmp_path, monkeypatch, parent, hull):
    state, context = case(tmp_path, monkeypatch, parent=parent, hull=hull)
    mesh = body.run(context)
    solid = parent in units.SOLID_PROPS
    assert mesh.path == context.outputs[0] and state.saves == [mesh.path] and mesh.material is state.assets[units.MATERIAL]
    assert mesh.body.values['collision_trace_flag'] == ('simple_and_complex' if solid else 'default')
    assert state.cooked == ([(mesh.triangles, True)] * 2 if solid else [])
    assert state.raw.material is None


@pytest.mark.parametrize('damage', ['slot', 'triangles', 'bounds', 'uv', 'hulls', 'cook', 'save', 'receipt', 'payload',
                                    'membership', 'policy', 'fresh', 'material'])
def test_invalid_sources_or_native_state_never_complete(tmp_path, monkeypatch, damage):
    state, context = case(tmp_path, monkeypatch)
    raw = state.raw
    if damage == 'slot': raw.static_materials = [Props(imported_material_slot_name='M_RoninBody')]
    elif damage == 'triangles': raw.triangles -= 1
    elif damage == 'bounds': raw.high = (raw.high[0] + 1, *raw.high[1:])
    elif damage == 'uv': raw.uvs = 2
    elif damage == 'hulls': raw.hulls = []
    elif damage == 'cook': state.cook_ok = False
    elif damage == 'save': state.save_ok = False
    elif damage == 'receipt': (Path(context.inputs['source_export']) / 'export.json').write_text('{}')
    elif damage == 'payload': (Path(context.inputs['payload']) / 'SM_CampFirePit.npz').write_bytes(b'other')
    elif damage == 'membership': context.inputs['extra'] = 'x'; context.packages['extra'] = []
    elif damage == 'policy': context.params['args']['collision'] = 'default'
    elif damage == 'fresh': state.assets[context.outputs[0]] = Mesh(context.outputs[0])
    else: context.params['args']['native_inputs'] = {'native0': units.ATLAS, 'native1': units.MATERIAL}
    with pytest.raises(ValueError):
        body.run(context)
