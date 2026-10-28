"""Actual mini-mega D2 followers, selected export/MeshIR proofs and native finish refusals."""
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


units = load('games/yorimichi/v2_mega_units.py', 'mega_units_test')
body = load(units.FINISH, 'mega_finish_test')
MATERIAL = units.MATERIAL


@pytest.fixture(scope='module')
def geometry():
    factory = load('games/yorimichi/mega_build.py', 'mega_actual_factory_test')
    rows = extract(factory.steps(NS(out=ROOT / 'build/yorimichi')), checkout=ROOT, build_root=ROOT / 'build')
    return load('games/yorimichi/v2_geometry_templates.py', 'mega_actual_templates_test').geometry_templates(rows, checkout=ROOT)


def natives():
    return {MATERIAL: {'unit': 'village.material.actual', 'item': 'asset', 'package': MATERIAL}}


def test_actual_three_parent_templates_bind_own_sources_and_original_policies(geometry):
    before = deepcopy(geometry); result = units.attach_followers(geometry, natives(), checkout=ROOT)
    assert geometry == before
    templates = {t['unit_prefix'].removeprefix('world.mega.export.'): t for t in result['templates']}
    assert sorted(templates) == ['Mega_Ramp', 'Mega_Trail', 'Mega_Trim']
    for parent, template in templates.items():
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['params']['fbx'] == units.FBX and raw['params']['destination'] == '/Game/_Raw/Mega/$piece'
        assert raw['outputs'][0]['destination'] == 'store'
        assert finish['outputs'][0]['logical_path'] == '/Game/Japan/Assets/$piece' and finish['outputs'][0]['destination'] == 'checkout'
        assert finish['inputs'][2]['source'] == {'kind': 'group_member', 'unit': 'world.mega.geometry.' + parent,
                                                 'group': 'geometry', 'piece': '$piece'}
        args = finish['params']['args']
        assert args['collision'] == ('look_only' if parent == 'Mega_Trim' else 'complex_as_simple')
        assert args['material'] == 'native0' and args['native_inputs'] == {'native0': MATERIAL}
        assert all((ROOT / p).is_file() for p in finish['code'])
        assert {'games/yorimichi/city_tile_products.py', 'games/yorimichi/world/island_finish_v2.py'} <= set(finish['code'])
        assert result['module_requirements'][template['unit_prefix']][0]['name'] == 'Yorimichi'


@pytest.mark.parametrize('damage', ['missing', 'wrong', 'transitive', 'partial', 'format', 'foreign', 'attached'])
def test_missing_roles_or_changed_original_family_refuse(geometry, damage):
    geometry = deepcopy(geometry); refs = natives()
    mega = [t for t in geometry['templates'] if t['unit_prefix'].startswith('world.mega.export.')]
    if damage == 'missing': refs = {}
    elif damage == 'wrong': refs[MATERIAL]['package'] = '/Game/Other'
    elif damage == 'transitive': refs[MATERIAL]['dependencies'] = ['/Game/Japan/Textures/T_Missing']
    elif damage == 'partial': geometry['templates'].remove(mega[0])
    elif damage == 'format': mega[0]['params']['format'] = 'glb'
    elif damage == 'foreign': mega[0]['producer'] = 'other'
    else: mega[0]['followers'] = [{}]
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
    def get_material(self, i): return self.material
    def set_material(self, i, value): self.material = value
    def get_editor_property(self, key): return self.body
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz', self.low))), max=NS(**dict(zip('xyz', self.high))))


def case(tmp_path, monkeypatch, *, parent='Mega_Ramp', hull=False):
    source = tmp_path / 'source'; payload = tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    piece = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], faces=[[0, 1, 2]],
                 normals=[[0., 0., 1.]] * 3, materials=[0], smooth=[False],
                 uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.]])], colours=[])
    hulls = []
    if hull:
        tetra = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], faces=[[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]],
                     normals=[[0., 0., 1.]] * 12, materials=[0] * 4, smooth=[False] * 4, uvs=[], colours=[])
        hulls = [mesh_collision.encode(tetra, slots=['Hull'], matrix=np.eye(4).tolist())]
    packet = mesh_ir.encode(piece, key=parent, slots=['MegaPalette'], matrix=np.eye(4).tolist(), options={}, collisions=hulls)
    (payload / (parent + '.npz')).write_bytes(packet)
    _meta, _decoded, facts = decode_mesh_payload(packet, expected_asset=parent)
    (source / (parent + '.fbx')).write_bytes(b'producer-verified FBX')
    publish_receipt(source, key=parent, primary=parent + '.fbx', triangles=facts['triangles'], bounds=[facts['min'], facts['max']],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'slots': ['MegaPalette'], 'polygons': facts['polygons'],
                  'collision_hulls': len(hulls), 'uv_channels': ['UVMap']})
    raw_path = '/Game/_Raw/Mega/' + parent; dest = '/Game/Japan/Assets/' + parent
    raw = Mesh(raw_path); raw.triangles = facts['triangles']; raw.uvs = 1; raw.material = None
    raw.hulls = [[[p[0] * 100, -p[1] * 100, p[2] * 100] for p in h['vertices']] for h in hulls]
    raw.static_materials = [Props(imported_material_slot_name='MegaPalette')]
    raw.body = Props(collision_trace_flag='old'); raw.low, raw.high = body.native_bounds(facts)
    assets = {raw_path: raw, MATERIAL: Material(MATERIAL)}; content = tmp_path / 'Content'; content.mkdir()
    state = NS(raw=raw, assets=assets, saves=[], cooked=[], save_ok=True, cook_ok=True)
    def duplicate(path, target):
        result = deepcopy(assets[path]); result.path = target; assets[target] = result; return result
    def save(mesh, dirty):
        assert dirty is True
        path = content / (mesh.path.removeprefix('/Game/') + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'primary')
        state.saves.append(mesh.path); return state.save_ok
    def complex_check(mesh, triangles, authored):
        state.cooked.append(('complex', triangles, authored)); return state.cook_ok
    def boxes(mesh, count):
        state.cooked.append(('boxes', count)); return state.cook_ok
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: NS(get_num_uv_channels=lambda mesh, lod: mesh.uvs),
        CollisionTraceFlag=NS(CTF_USE_SIMPLE_AS_COMPLEX='simple_as_complex', CTF_USE_COMPLEX_AS_SIMPLE='complex_as_simple'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda path: path in assets, duplicate_asset=duplicate, save_loaded_asset=save),
        CitySurfaceValidation=NS(collision_vertices=lambda mesh: json.dumps(mesh.hulls), validate_collision=complex_check,
                                 validate_simple_boxes=boxes))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(job_dir=str(tmp_path), content_dir=str(content),
        inputs={'raw': 'native-raw', 'source_export': str(source), 'payload': str(payload), 'native0': 'native'},
        packages={'raw': [raw_path], 'source_export': [], 'payload': [], 'native0': [MATERIAL]},
        outputs=[dest], params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
            'package_sources': {'raw': raw_path}, 'settings': [],
            'args': {'parent': parent, 'collision': body.POLICY[parent], 'payload': 'payload', 'source_export': 'source_export',
                     'material': 'native0', 'native_inputs': {'native0': MATERIAL}}})
    return state, context


@pytest.mark.parametrize('parent,hull', [('Mega_Ramp', False), ('Mega_Ramp', True), ('Mega_Trail', False), ('Mega_Trim', False)])
def test_original_material_and_collision_policy(tmp_path, monkeypatch, parent, hull):
    state, context = case(tmp_path, monkeypatch, parent=parent, hull=hull)
    mesh = body.run(context)
    assert mesh.path == context.outputs[0] and state.saves == [mesh.path] and mesh.material is state.assets[MATERIAL]
    trim = parent == 'Mega_Trim'
    assert mesh.body.values['collision_trace_flag'] == ('simple_as_complex' if trim else 'complex_as_simple')
    assert state.cooked == [('boxes', 0) if trim else ('complex', mesh.triangles, False)] * 2
    assert state.raw.material is None


@pytest.mark.parametrize('damage', ['slot', 'triangles', 'bounds', 'uv', 'hulls', 'cook', 'save', 'receipt', 'payload',
                                    'membership', 'policy', 'fresh', 'trim_hulls'])
def test_invalid_sources_or_native_state_never_complete(tmp_path, monkeypatch, damage):
    state, context = case(tmp_path, monkeypatch, parent='Mega_Trim' if damage == 'trim_hulls' else 'Mega_Ramp',
                          hull=damage in ('hulls', 'trim_hulls'))
    raw = state.raw
    if damage == 'slot': raw.static_materials = [Props(imported_material_slot_name='VillagePalette')]
    elif damage == 'triangles': raw.triangles -= 1
    elif damage == 'bounds': raw.high = (raw.high[0] + 1, *raw.high[1:])
    elif damage == 'uv': raw.uvs = 2
    elif damage == 'hulls': raw.hulls = []
    elif damage == 'cook': state.cook_ok = False
    elif damage == 'save': state.save_ok = False
    elif damage == 'receipt': (Path(context.inputs['source_export']) / 'export.json').write_text('{}')
    elif damage == 'payload': (Path(context.inputs['payload']) / 'Mega_Ramp.npz').write_bytes(b'other')
    elif damage == 'membership': context.inputs['extra'] = 'x'; context.packages['extra'] = []
    elif damage == 'policy': context.params['args']['collision'] = 'look_only'
    elif damage == 'fresh': state.assets[context.outputs[0]] = Mesh(context.outputs[0])
    with pytest.raises(ValueError):
        body.run(context)
