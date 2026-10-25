"""Actual world prop D2 followers, projected palettes, selected export/MeshIR proofs and native finish refusals."""
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


units = load('games/yorimichi/v2_props_units.py', 'props_units_test')
body = load(units.FINISH, 'props_finish_test')
PARENT_MATERIAL = '/Game/Japan/Materials/M_Japan'


@pytest.fixture(scope='module')
def geometry():
    factory = load('games/yorimichi/props_atomic_build.py', 'props_actual_factory_test')
    rows = extract(factory.steps(NS(out=ROOT / 'build/yorimichi')), checkout=ROOT, build_root=ROOT / 'build')
    return load('games/yorimichi/v2_geometry_templates.py', 'props_actual_templates_test').geometry_templates(rows, checkout=ROOT)


def natives():
    packages = {package for palette in units.bindings(ROOT).values() for package in palette.values()}
    refs = {p: {'unit': 'unreal.materials.' + p.rsplit('/', 1)[-1], 'item': 'asset', 'package': p,
                'dependencies': [PARENT_MATERIAL]} for p in packages}
    refs[PARENT_MATERIAL] = {'unit': 'unreal.materials.M_Japan', 'item': 'asset', 'package': PARENT_MATERIAL}
    return refs


def test_projected_palettes_bind_original_setup_project_materials():
    palette = units.bindings(ROOT)
    assert sorted(palette) == sorted(body.PROPS)
    assert palette['Pole'] == {k: '/Game/Japan/Materials/MI_' + k for k in ('Concrete', 'Metal', 'Paint', 'Wood')}
    assert palette['Torii'] == {'Tile': '/Game/Japan/Materials/MI_Tile', 'Vermilion': '/Game/Japan/Materials/MI_Vermilion'}
    assert palette['SkyDome'] == {'Sky': '/Game/Japan/Materials/MI_Sky'}
    assert units.COMPLEX == body.COMPLEX


def test_actual_fourteen_prop_templates_bind_own_sources_palettes_and_original_policies(geometry):
    before = deepcopy(geometry); result = units.attach_followers(geometry, natives(), checkout=ROOT)
    assert geometry == before
    templates = {t['unit_prefix'].removeprefix('world.props.export.'): t for t in result['templates']
                 if t['unit_prefix'].startswith('world.props.export.')}
    assert sorted(templates) == sorted(body.PROPS)
    palette = units.bindings(ROOT)
    for parent, template in templates.items():
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['params']['fbx'] == units.FBX and raw['params']['fbx']['convert_scene_unit'] is False
        assert raw['params']['destination'] == '/Game/_Raw/Props/$piece' and raw['outputs'][0]['destination'] == 'store'
        assert finish['outputs'][0]['logical_path'] == '/Game/Japan/Assets/$piece' and finish['outputs'][0]['destination'] == 'checkout'
        assert finish['inputs'][2]['source'] == {'kind': 'group_member', 'unit': 'world.props.geometry.' + parent,
                                                 'group': 'geometry', 'piece': '$piece'}
        args = finish['params']['args']
        assert args['collision'] == ('complex_as_simple' if parent in units.COMPLEX else 'original')
        assert {k: args['native_inputs'][s] for k, s in args['materials'].items()} == palette[parent]
        assert set(args['native_inputs'].values()) == {*palette[parent].values(), PARENT_MATERIAL}
        assert [i['name'] for i in finish['inputs'][3:]] == sorted(args['native_inputs'], key=lambda s: int(s[6:]))
        assert all((ROOT / p).is_file() for p in finish['code'])
        assert {'games/yorimichi/city_tile_products.py', 'games/yorimichi/world/island_finish_v2.py'} <= set(finish['code'])
        assert result['module_requirements'][template['unit_prefix']][0]['name'] == 'Yorimichi'


@pytest.mark.parametrize('damage', ['missing', 'wrong', 'transitive', 'alias', 'partial', 'format', 'foreign', 'attached'])
def test_missing_roles_or_changed_original_family_refuse(geometry, damage):
    geometry = deepcopy(geometry); refs = natives()
    props = [t for t in geometry['templates'] if t['unit_prefix'].startswith('world.props.export.')]
    if damage == 'missing': del refs['/Game/Japan/Materials/MI_Sky']
    elif damage == 'wrong': refs['/Game/Japan/Materials/MI_Sky']['package'] = '/Game/Other'
    elif damage == 'transitive': del refs[PARENT_MATERIAL]
    elif damage == 'alias': refs['/Game/Japan/Materials/MI_Tile']['unit'] = refs['/Game/Japan/Materials/MI_Vermilion']['unit']
    elif damage == 'partial': geometry['templates'].remove(props[0])
    elif damage == 'format': props[0]['params']['format'] = 'glb'
    elif damage == 'foreign': props[0]['producer'] = 'other'
    else: props[0]['followers'] = [{}]
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
    def get_material(self, i): return self.materials[i]
    def set_material(self, i, value): self.materials[i] = value
    def get_editor_property(self, key): return self.body
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz', self.low))), max=NS(**dict(zip('xyz', self.high))))


def case(tmp_path, monkeypatch, *, parent='Torii', hull=False, slots=('Vermilion', 'Tile')):
    source = tmp_path / 'source'; payload = tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    piece = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [1., 1., 0.]], faces=[[0, 1, 2], [1, 3, 2]],
                 normals=[[0., 0., 1.]] * 6, materials=[0, len(slots) - 1], smooth=[False] * 2,
                 uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.], [1., 0.], [1., 1.], [0., 1.]])], colours=[])
    hulls = []
    if hull:
        tetra = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]], faces=[[0, 1, 2], [0, 3, 1], [1, 3, 2], [0, 2, 3]],
                     normals=[[0., 0., 1.]] * 12, materials=[0] * 4, smooth=[False] * 4, uvs=[], colours=[])
        hulls = [mesh_collision.encode(tetra, slots=['Hull'], matrix=np.eye(4).tolist())]
    packet = mesh_ir.encode(piece, key=parent, slots=list(slots), matrix=np.eye(4).tolist(), options={}, collisions=hulls)
    (payload / (parent + '.npz')).write_bytes(packet)
    _meta, _decoded, facts = decode_mesh_payload(packet, expected_asset=parent)
    (source / (parent + '.fbx')).write_bytes(b'producer-verified FBX')
    publish_receipt(source, key=parent, primary=parent + '.fbx', triangles=facts['triangles'], bounds=[facts['min'], facts['max']],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'slots': facts['slots'], 'polygons': facts['polygons'],
                  'collision_hulls': len(hulls), 'uv_channels': facts['uv_channels']})
    raw_path = '/Game/_Raw/Props/' + parent; dest = '/Game/Japan/Assets/' + parent
    raw = Mesh(raw_path); raw.triangles = facts['triangles']; raw.uvs = 1; raw.materials = [None] * len(slots)
    raw.hulls = [[[p[0] * 100, -p[1] * 100, p[2] * 100] for p in h['vertices']] for h in hulls]
    # FBX import may reorder slots; binding is by name, as setup_project.assign does.
    raw.static_materials = [Props(imported_material_slot_name=name) for name in reversed(slots)]
    raw.body = Props(collision_trace_flag='raw_default'); raw.low, raw.high = body.native_bounds(facts)
    palette = units.bindings(ROOT)[parent]
    native = {'native' + str(i): package for i, package in enumerate(palette.values())}
    materials = {key: 'native' + str(i) for i, key in enumerate(palette)}
    assets = {raw_path: raw, **{package: Material(package) for package in native.values()}}
    content = tmp_path / 'Content'; content.mkdir()
    state = NS(raw=raw, assets=assets, saves=[], cooked=[], save_ok=True, cook_ok=True)
    def duplicate(path, target):
        result = deepcopy(assets[path]); result.path = target; assets[target] = result; return result
    def save(mesh, dirty):
        assert dirty is True
        path = content / (mesh.path.removeprefix('/Game/') + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'primary')
        state.saves.append(mesh.path); return state.save_ok
    def complex_check(mesh, triangles, authored):
        state.cooked.append(('complex', triangles, authored)); return state.cook_ok
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: NS(get_num_uv_channels=lambda mesh, lod: mesh.uvs),
        CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex_as_simple'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda path: path in assets, duplicate_asset=duplicate, save_loaded_asset=save),
        CitySurfaceValidation=NS(collision_vertices=lambda mesh: json.dumps(mesh.hulls), validate_collision=complex_check))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(job_dir=str(tmp_path), content_dir=str(content),
        inputs={'raw': 'native-raw', 'source_export': str(source), 'payload': str(payload), **{s: 'native' for s in native}},
        packages={'raw': [raw_path], 'source_export': [], 'payload': [], **{s: [p] for s, p in native.items()}},
        outputs=[dest], params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
            'package_sources': {'raw': raw_path}, 'settings': [],
            'args': {'parent': parent, 'collision': 'complex_as_simple' if parent in body.COMPLEX else 'original',
                     'payload': 'payload', 'source_export': 'source_export', 'materials': materials, 'native_inputs': native}})
    return state, context


@pytest.mark.parametrize('parent,slots,hull', [('Torii', ('Vermilion', 'Tile'), False), ('Torii', ('Vermilion', 'Tile'), True),
                                               ('Pole', ('Concrete', 'Paint'), False), ('SkyDome', ('Sky',), False),
                                               ('BirdBody', ('Feather', 'FeatherDark', 'Vermilion'), False)])
def test_original_material_and_collision_policy(tmp_path, monkeypatch, parent, slots, hull):
    state, context = case(tmp_path, monkeypatch, parent=parent, slots=slots, hull=hull)
    mesh = body.run(context)
    assert mesh.path == context.outputs[0] and state.saves == [mesh.path]
    names = [m.values['imported_material_slot_name'] for m in mesh.static_materials]
    assert [m.path for m in mesh.materials] == ['/Game/Japan/Materials/MI_' + n for n in names]
    complex_ = parent in body.COMPLEX
    assert mesh.body.values['collision_trace_flag'] == ('complex_as_simple' if complex_ else 'raw_default')
    assert state.cooked == ([('complex', mesh.triangles, False)] * 2 if complex_ else [])
    assert state.raw.materials == [None] * len(slots)


@pytest.mark.parametrize('damage', ['slot', 'foreign_slot', 'triangles', 'bounds', 'uv', 'hulls', 'cook', 'save', 'receipt',
                                    'payload', 'membership', 'policy', 'fresh', 'material', 'binding'])
def test_invalid_sources_or_native_state_never_complete(tmp_path, monkeypatch, damage):
    state, context = case(tmp_path, monkeypatch, hull=damage == 'hulls',
                          slots=('Vermilion', 'Metal') if damage == 'foreign_slot' else ('Vermilion', 'Tile'))
    raw = state.raw; args = context.params['args']
    if damage == 'slot': raw.static_materials = [Props(imported_material_slot_name='Vermilion')] * 2
    elif damage == 'triangles': raw.triangles -= 1
    elif damage == 'bounds': raw.high = (raw.high[0] + 1, *raw.high[1:])
    elif damage == 'uv': raw.uvs = 2
    elif damage == 'hulls': raw.hulls = []
    elif damage == 'cook': state.cook_ok = False
    elif damage == 'save': state.save_ok = False
    elif damage == 'receipt': (Path(context.inputs['source_export']) / 'export.json').write_text('{}')
    elif damage == 'payload': (Path(context.inputs['payload']) / 'Torii.npz').write_bytes(b'other')
    elif damage == 'membership': context.inputs['extra'] = 'x'; context.packages['extra'] = []
    elif damage == 'policy': args['collision'] = 'original'
    elif damage == 'fresh': state.assets[context.outputs[0]] = Mesh(context.outputs[0])
    elif damage == 'material': state.assets[args['native_inputs']['native0']] = Asset(args['native_inputs']['native0'])
    elif damage == 'binding': args['materials'] = dict(zip(args['materials'], reversed(list(args['materials'].values()))))
    with pytest.raises(ValueError):
        body.run(context)
