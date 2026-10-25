"""Actual houses D2 followers, selected export/MeshIR proofs and native finish refusals."""
from copy import deepcopy
import hashlib
import importlib.util
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


units = load('games/yorimichi/v2_houses_units.py', 'houses_units_test')
body = load(units.FINISH, 'houses_finish_test')
VILLAGE, GROUND = units.MATERIALS['Village'], units.MATERIALS['Ground']
PARENTS = ['HouseLot_1', 'HouseLot_2', 'HouseLot_3', 'HouseLot_4', 'HouseLot_5', 'House_A', 'House_B', 'House_C']


@pytest.fixture(scope='module')
def geometry():
    factory = load('games/yorimichi/houses_build.py', 'houses_actual_factory_test')
    rows = extract(factory.steps(NS(out=ROOT / 'build/yorimichi')), checkout=ROOT, build_root=ROOT / 'build')
    return load('games/yorimichi/v2_geometry_templates.py', 'houses_actual_templates_test').geometry_templates(rows, checkout=ROOT)


def natives():
    return {VILLAGE: {'unit': 'village.material.actual', 'item': 'asset', 'package': VILLAGE},
            GROUND: {'unit': 'island.material.MI_Ground', 'item': 'asset', 'package': GROUND,
                     'dependencies': ['/Game/Japan/Materials/M_Ground']},
            '/Game/Japan/Materials/M_Ground': {'unit': 'island.material.M_Ground', 'item': 'asset',
                                               'package': '/Game/Japan/Materials/M_Ground'}}


def test_actual_eight_parent_templates_bind_own_sources_and_supplied_material_closure(geometry):
    before = deepcopy(geometry); result = units.attach_followers(geometry, natives(), checkout=ROOT)
    assert geometry == before
    templates = {t['unit_prefix'].removeprefix('world.houses.export.'): t for t in result['templates']}
    assert sorted(templates) == PARENTS and sorted(result['module_requirements']) == sorted('world.houses.export.' + p for p in PARENTS)
    for parent, template in templates.items():
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['op'] == {'kind': 'unreal.raw_import', 'version': '1'} and raw['params']['fbx'] == units.FBX
        assert raw['outputs'][0]['class'] == 'RawStaticMesh' and raw['outputs'][0]['destination'] == 'store'
        assert raw['params']['destination'] == '/Game/_Raw/Houses/$piece'
        assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': '$export', 'item': 'asset'}
        assert finish['script'] == units.FINISH and finish['outputs'][0]['logical_path'] == '/Game/Japan/Assets/$piece'
        assert finish['outputs'][0]['destination'] == 'checkout'
        assert finish['outputs'][0]['files'][0]['install_path'] == 'games/yorimichi/unreal/Content/Japan/Assets/$piece.uasset'
        assert [i['source'] for i in finish['inputs'][:3]] == [
            {'kind': 'item', 'unit': '$previous', 'item': 'raw'}, {'kind': 'item', 'unit': '$export', 'item': 'asset'},
            {'kind': 'group_member', 'unit': 'world.houses.geometry.' + parent, 'group': 'geometry', 'piece': '$piece'}]
        args = finish['params']['args']
        assert args['lot'] is parent.startswith('HouseLot_') and args['materials'] == {'Village': 'native0', 'Ground': 'native1'}
        assert args['native_inputs'] == {'native0': VILLAGE, 'native1': GROUND, 'native2': '/Game/Japan/Materials/M_Ground'}
        assert all((ROOT / p).is_file() for p in finish['code']) and units.FINISH in finish['code']
        assert 'games/yorimichi/world/island_finish_v2.py' in finish['code']
        assert result['module_requirements'][template['unit_prefix']][0]['name'] == 'Yorimichi'


def test_extending_houses_keeps_other_families_module_requirements(geometry):
    geometry = deepcopy(geometry); geometry['module_requirements'] = {'world.village.export.X': ['kept']}
    result = units.attach_followers(geometry, natives(), checkout=ROOT)
    assert result['module_requirements']['world.village.export.X'] == ['kept']


@pytest.mark.parametrize('damage', ['missing_village', 'missing_ground', 'transitive', 'wrong', 'partial', 'format', 'foreign', 'attached'])
def test_missing_roles_or_changed_original_family_refuse(geometry, damage):
    geometry = deepcopy(geometry); refs = natives()
    houses = [t for t in geometry['templates'] if t['unit_prefix'].startswith('world.houses.export.')]
    if damage == 'missing_village': del refs[VILLAGE]
    elif damage == 'missing_ground': del refs[GROUND]
    elif damage == 'transitive': del refs['/Game/Japan/Materials/M_Ground']
    elif damage == 'wrong': refs[GROUND]['package'] = '/Game/Other'
    elif damage == 'partial': geometry['templates'].remove(houses[0])
    elif damage == 'format': houses[0]['params']['format'] = 'glb'
    elif damage == 'foreign': houses[0]['producer'] = 'other'
    else: houses[0]['followers'] = [{}]
    with pytest.raises(ValueError):
        units.attach_followers(geometry, refs, checkout=ROOT)


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
    def get_material(self, i): return self.materials.get(i)
    def set_material(self, i, value): self.materials[i] = value
    def get_editor_property(self, key): return self.body
    def get_bounding_box(self): return NS(max=NS(z=self.max_z))


def case(tmp_path, monkeypatch, *, lot=False, degenerate=False):
    parent = 'HouseLot_2' if lot else 'House_B'
    slots = ['Village', 'Ground'] if lot else ['Village']
    source = tmp_path / 'source'; payload = tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    piece = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 2.], [1., 1., 0.]], faces=[[0, 1, 2], [1, 3, 2]],
                 normals=[[0., 0., 1.]] * 6, materials=[0, len(slots) - 1], smooth=[False, False],
                 uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.], [1., 0.], [1., 1.], [0., 1.]])], colours=[])
    if degenerate:
        piece['positions'][3] = list(piece['positions'][1])
    tetra = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], faces=[[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]],
                 normals=[[0., 0., 1.]] * 12, materials=[0] * 4, smooth=[False] * 4, uvs=[], colours=[])
    hulls = [] if lot else [mesh_collision.encode(tetra, slots=['Hull'], matrix=np.eye(4).tolist())]
    packet = mesh_ir.encode(piece, key=parent, slots=slots, matrix=np.eye(4).tolist(), options={}, collisions=hulls)
    (payload / (parent + '.npz')).write_bytes(packet)
    _meta, _decoded, facts = decode_mesh_payload(packet, expected_asset=parent)
    (source / (parent + '.fbx')).write_bytes(b'producer-verified FBX')
    publish_receipt(source, key=parent, primary=parent + '.fbx', triangles=facts['triangles'], bounds=[facts['min'], facts['max']],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'slots': facts['slots'], 'polygons': facts['polygons'],
                  'collision_hulls': len(hulls), 'uv_channels': facts['uv_channels']})
    raw_path = '/Game/_Raw/Houses/' + parent; dest = '/Game/Japan/Assets/' + parent
    raw = Mesh(raw_path); raw.triangles = facts['triangles']; raw.uvs = 1; raw.max_z = facts['max'][2] * 100
    raw.materials = {}; raw.static_materials = [Props(imported_material_slot_name=s) for s in slots]
    raw.body = Props(collision_trace_flag='old', agg_geom=Props(convex_elems=[object()] * len(hulls)))
    materials = {VILLAGE: Material(VILLAGE), GROUND: Material(GROUND), '/Game/Japan/Materials/M_Ground': Material('/Game/Japan/Materials/M_Ground')}
    assets = {raw_path: raw, **materials}; content = tmp_path / 'Content'; content.mkdir()
    state = NS(raw=raw, assets=assets, saves=[], cooked=[], save_ok=True, cook_ok=True)
    def duplicate(path, target):
        result = deepcopy(assets[path]); result.path = target; assets[target] = result; return result
    def save(mesh, dirty):
        assert dirty is True
        path = content / (mesh.path.removeprefix('/Game/') + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'primary')
        state.saves.append(mesh.path); return state.save_ok
    def cooked(mesh, triangles, simple):
        state.cooked.append((triangles, simple)); return state.cook_ok
    editor = NS(get_num_uv_channels=lambda mesh, lod: mesh.uvs)
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: editor, CollisionTraceFlag=NS(CTF_USE_SIMPLE_AND_COMPLEX='simple', CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda path: path in assets, duplicate_asset=duplicate, save_loaded_asset=save),
        CitySurfaceValidation=NS(validate_collision=cooked))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    native = {'native0': VILLAGE, 'native1': GROUND, 'native2': '/Game/Japan/Materials/M_Ground'}
    context = NS(job_dir=str(tmp_path), content_dir=str(content),
        inputs={'raw': 'native-raw', 'source_export': str(source), 'payload': str(payload), **dict.fromkeys(native, 'native')},
        packages={'raw': [raw_path], 'source_export': [], 'payload': [], **{k: [v] for k, v in native.items()}},
        outputs=[dest], params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
            'package_sources': {'raw': raw_path}, 'settings': [],
            'args': {'parent': parent, 'lot': lot, 'payload': 'payload', 'source_export': 'source_export',
                     'materials': {'Village': 'native0', 'Ground': 'native1'}, 'native_inputs': native}})
    return state, context


@pytest.mark.parametrize('lot', [False, True])
def test_original_slot_binding_and_collision_policy(tmp_path, monkeypatch, lot):
    state, context = case(tmp_path, monkeypatch, lot=lot)
    mesh = body.run(context)
    assert mesh.path == context.outputs[0] and state.saves == [mesh.path]
    assert mesh.body.values['collision_trace_flag'] == ('complex' if lot else 'simple')
    expected = [state.assets[VILLAGE], state.assets[GROUND]] if lot else [state.assets[VILLAGE]]
    assert [mesh.materials[i] for i in range(len(expected))] == expected
    assert state.cooked == [(mesh.triangles, not lot)] * 2 and state.raw.materials == {}


@pytest.mark.parametrize('damage', ['slots', 'scale', 'hulls', 'triangles', 'uv', 'cook', 'save', 'receipt', 'payload',
                                    'membership', 'material', 'fresh', 'lot'])
def test_invalid_sources_or_native_state_never_complete(tmp_path, monkeypatch, damage):
    state, context = case(tmp_path, monkeypatch)
    raw = state.raw
    if damage == 'slots': raw.static_materials = [Props(imported_material_slot_name='Ground')]
    elif damage == 'scale': raw.max_z += 1
    elif damage == 'hulls': raw.body.values['agg_geom'] = Props(convex_elems=[])
    elif damage == 'triangles': raw.triangles += 1
    elif damage == 'uv': raw.uvs = 2
    elif damage == 'cook': state.cook_ok = False
    elif damage == 'save': state.save_ok = False
    elif damage == 'receipt': (Path(context.inputs['source_export']) / 'export.json').write_text('{}')
    elif damage == 'payload': (Path(context.inputs['payload']) / 'House_B.npz').write_bytes(b'other')
    elif damage == 'membership': context.inputs['extra'] = 'x'; context.packages['extra'] = []
    elif damage == 'material': context.params['args']['materials'] = {'Village': 'native1', 'Ground': 'native0'}
    elif damage == 'fresh': state.assets[context.outputs[0]] = Mesh(context.outputs[0])
    else: context.params['args']['lot'] = True
    with pytest.raises(ValueError):
        body.run(context)


def test_lot_cannot_certify_arbitrary_missing_native_triangles(tmp_path, monkeypatch):
    state, context = case(tmp_path, monkeypatch, lot=True)
    state.raw.triangles = 1
    with pytest.raises(ValueError, match='geometry'):
        body.run(context)
    assert not state.saves


def test_lot_uses_exact_existing_fbx_degenerate_projection(tmp_path, monkeypatch):
    state, context = case(tmp_path, monkeypatch, lot=True, degenerate=True)
    state.raw.triangles = 1
    mesh = body.run(context)
    assert mesh.triangles == 1 and state.saves == [mesh.path]
