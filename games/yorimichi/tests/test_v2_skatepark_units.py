"""Actual Sunset Pier declarations, generated members and native finish refusals; no native jobs."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir
from atelier.build_v2.recipe_dependencies import extract
from atelier.build_v2.recipe_job import pack_root
from atelier.export_manifest import publish_receipt

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]
import v2_skatepark_units as units  # noqa: E402
import skatepark_members_v2 as members  # noqa: E402
import skatepark_finish_v2 as body  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


@pytest.fixture(scope='module')
def rows():
    build = load('games/yorimichi/build.py', 'skatepark_actual_build')
    ctx = NS(game='yorimichi', out=ROOT / 'build/yorimichi', uproject=None)
    steps = [s for s in build.world_steps(ctx) + build.unreal_steps(ctx) if 'skatepark' in s.name]
    names = {s.name for s in steps}; products = {p.name for s in steps for p in s.products}
    for step in steps:
        step.reads = [r for r in step.reads if r in products]; step.needs = [n for n in step.needs if n in names]
        step.after = [n for n in step.after if n in names]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def geometry(rows):
    return load('games/yorimichi/v2_geometry_templates.py', 'skatepark_actual_templates').geometry_templates(rows, checkout=ROOT)


def natives():
    paths = [units.VILLAGE, *('/Game/Japan/Assets/' + name for name in json.loads((ROOT / units.LOGICAL).read_bytes()).get('trees', {}))]
    return {path: {'unit': 'actual.native.' + str(i), 'item': 'asset', 'package': path} for i, path in enumerate(paths)}


def test_actual_family_and_produced_material_items(rows, geometry):
    before = deepcopy(geometry)
    result = units.attach_followers(geometry, rows=rows, checkout=ROOT, natives=natives())
    assert geometry == before
    assert len(result['templates']) == 4
    assert len(result['groups']) == 4
    assert result['source_join'] == {'owner': 'world.skatepark', 'retained': True,
                                    'products': ['skatepark.meshes', 'skatepark.runtime', 'skatepark.queries']}
    original = [t for t in result['geometry']['templates'] if t['producer'].startswith(('world.skatepark.geometry.', 'world.skatepark_board.geometry.'))]
    assert len(original) == 10
    for template in original:
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['outputs'][0]['destination'] == 'store'
        assert finish['inputs'][0]['source'] == {'kind': 'item', 'unit': '$previous', 'item': 'raw'}
        assert finish['inputs'][2]['source']['kind'] == 'group_member'
        assert len(finish['outputs'][0]['files']) == 6
        assert units.ORIGINAL in finish['code']
        assert finish['params']['args']['board'] == ('skatepark_board.geometry.' in template['producer'])
        assert finish['params']['args'].get('material') == ('native0' if finish['params']['args']['board'] else None)
    gate = next(u for u in result['units'] if u['id'] == 'unreal.skatepark.complete')
    assert gate['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.skatepark', 'item': 'product0'}
    assert gate['inputs'][1]['source'] == {'kind': 'item', 'unit': 'world.skatepark', 'item': 'product1'}
    for unit in result['units']:
        if unit.get('output_groups'): assert unit['outputs'][0]['id'] != unit['output_groups'][0]['id']
        assert all(o['kind'] == 'tree' for o in unit['params']['recipe']['outputs'])


@pytest.mark.parametrize('damage', ['material', 'tree', 'closure', 'source', 'partial', 'format', 'attached'])
def test_changed_native_or_source_ownership_refuses(rows, geometry, damage):
    rows, geometry, refs = deepcopy(rows), deepcopy(geometry), natives()
    if damage == 'material': refs.pop(units.VILLAGE)
    if damage == 'tree': refs.pop(next(p for p in refs if p != units.VILLAGE))
    if damage == 'closure': refs[units.VILLAGE]['dependencies'] = ['/Game/Missing']
    if damage == 'source': next(r for r in rows if r['id'] == 'world.skatepark')['products'][0]['paths'].pop()
    if damage == 'partial': geometry['templates'].pop()
    if damage == 'format': geometry['templates'][0]['params']['format'] = 'glb'
    if damage == 'attached': geometry['templates'][0]['followers'] = [{}]
    with pytest.raises(ValueError): units.attach_followers(geometry, rows=rows, checkout=ROOT, natives=refs)


def textures(tmp_path, mutation=None):
    root = tmp_path / 'textures'; root.mkdir(); specs = {}
    for key in sorted(members.SURFACES):
        roles = ('albedo',) if key == 'mural' else members.ROLES
        specs[key] = {'repeat_m': 1., 'metallic': float(key == 'steel'), 'maps': {}, 'sha256': {}}
        for role in roles:
            name = key + '-' + role + '.png'; raw = (key + role).encode(); (root / name).write_bytes(raw)
            specs[key]['maps'][role] = name; specs[key]['sha256'][role] = hashlib.sha256(raw).hexdigest()
    if mutation: mutation(root, specs)
    (root / 'textures.json').write_text(json.dumps(specs))
    archive = tmp_path / 'textures.tree.tar'; pack_root(root, archive); return archive


def test_actual_material_and_role_projection_preserves_painted_steel_identity(tmp_path):
    archive = textures(tmp_path)
    members.project(archive, tmp_path / 'specs', 'materials')
    painted = members.read_json(tmp_path / 'specs/painted.json'); steel = members.read_json(tmp_path / 'specs/steel.json')
    assert painted['entry'] == {**steel['entry'], 'metallic': 0.}
    for role in members.ROLES:
        target = tmp_path / role; members.project(archive, target, role)
        assert (target / ('painted_' + role + '.png')).read_bytes() == (target / ('steel_' + role + '.png')).read_bytes()
        assert len(list(target.iterdir())) == (7 if role == 'albedo' else 6)


@pytest.mark.parametrize('mutation', [lambda root, specs: (root / 'steel-normal.png').write_bytes(b'changed'),
    lambda root, specs: (root / 'extra.png').write_bytes(b'extra'), lambda root, specs: specs.pop('mural'),
    lambda root, specs: specs['steel'].update(metallic=0.)])
def test_foreign_incomplete_or_changed_produced_texture_members_refuse(tmp_path, mutation):
    archive = textures(tmp_path, mutation)
    with pytest.raises(ValueError): members.project(archive, tmp_path / 'selected', 'materials')


class Props:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, name): return self.values[name]
    def set_editor_property(self, name, value): self.values[name] = value


class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]


class Mesh(Asset):
    def __init__(self, path):
        super().__init__(path)
        self.static_materials = [Props(imported_material_slot_name='Pier_wood')]
        self.triangles, self.lods, self.uvs, self.simple, self.convex = 1, 1, 1, 0, 0
        self.materials = [None]; self.allow_cpu_access = False; self.complex_collision_mesh = 'stale'; self.lod_for_collision = 1
        self.body = Props(collision_trace_flag='default'); self.high = 100.
    def get_num_lods(self): return self.lods
    def get_num_triangles(self, i): return self.triangles
    def get_material(self, i): return self.materials[i]
    def set_material(self, i, value): self.materials[i] = value
    def get_editor_property(self, name): return self.body if name == 'body_setup' else getattr(self, name)
    def set_editor_property(self, name, value): setattr(self, name, value)
    def get_bounding_box(self): return NS(min=NS(x=0., y=-100., z=0.), max=NS(x=self.high, y=0., z=0.))


@pytest.fixture
def native_case(tmp_path, monkeypatch):
    piece = 'SM_SkatePier'; raw_package = '/Game/_Raw/SkatePark/' + piece; dest = '/Game/SkatePark/' + piece
    source, payload = tmp_path / 'source', tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    packet = mesh_ir.encode(dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], faces=[[0, 1, 2]],
        normals=[[0., 0., 1.]] * 3, materials=[0], smooth=[False], uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.]])], colours=[]),
        key=piece, slots=['Pier_wood'], matrix=np.eye(4).tolist(), options={}, collisions=[])
    (payload / (piece + '.npz')).write_bytes(packet); (source / (piece + '.fbx')).write_bytes(b'fbx')
    publish_receipt(source, key=piece, primary=piece + '.fbx', triangles=1, bounds=[[0, 0, 0], [1, 1, 0]],
        metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest(), 'slots': ['Pier_wood'], 'polygons': 1,
                  'collision_hulls': 0, 'uv_channels': ['UVMap']})
    material_path = '/Game/SkatePark/Materials/M_Pier_wood'
    assets = {raw_package: Mesh(raw_package), material_path: Asset(material_path)}
    state = NS(assets=assets, checks=0, saves=0, changed=False, collision_ok=True)
    def duplicate(source, target):
        asset = deepcopy(assets[source]); asset.path = target; assets[target] = asset; return asset
    def save(asset):
        state.saves += 1
        if state.changed: asset.uvs = 2
        return True
    def collision(asset, *args): state.checks += 1; return state.collision_ok
    editor = NS(get_num_uv_channels=lambda m, i: m.uvs, get_simple_collision_count=lambda m: m.simple,
                get_convex_collision_count=lambda m: m.convex)
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Asset, StaticMeshEditorSubsystem='editor', load_module=lambda _: None,
        get_editor_subsystem=lambda _: editor, CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex', CTF_USE_SIMPLE_AS_COMPLEX='simple'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate, save_loaded_asset=save),
        CitySurfaceValidation=NS(validate_collision=collision, validate_simple_boxes=collision))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(job_dir=str(tmp_path), inputs={'raw': 'raw', 'source_export': source, 'payload': payload, 'material': 'material'},
        packages={'raw': [raw_package], 'source_export': [], 'payload': [], 'material': [material_path]},
        outputs=[dest], data_outputs=['data/reports/' + piece + '.json'],
        params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
            'args': {'action': 'mesh', 'parent': piece, 'piece': piece, 'board': False, 'blocks': True,
                'materials': {'derived_items': {'root': 'actual', 'members': [{'piece': 'wood', 'slot': 'material', 'root': 'material'}]}}}})
    return state, context


def test_current_native_park_piece_uses_original_material_collision_and_snapshot(native_case):
    state, context = native_case; reports = body.run(context)
    mesh = state.assets[context.outputs[0]]
    assert mesh.allow_cpu_access is True and mesh.complex_collision_mesh is None and mesh.lod_for_collision == 0
    assert mesh.body.values['collision_trace_flag'] == 'complex' and state.checks == 2 and state.saves == 1
    assert next(iter(reports.values()))['materials'] == ['Pier_wood']
    assert state.assets[context.packages['raw'][0]].allow_cpu_access is False


@pytest.mark.parametrize('damage', ['triangles', 'bounds', 'uv', 'simple', 'collision', 'payload', 'after_save', 'slot'])
def test_current_native_mismatch_refuses(native_case, damage):
    state, context = native_case; raw = state.assets[context.packages['raw'][0]]
    if damage == 'triangles': raw.triangles = 2
    if damage == 'bounds': raw.high = 101.
    if damage == 'uv': raw.uvs = 2
    if damage == 'simple': raw.simple = 1
    if damage == 'collision': state.collision_ok = False
    if damage == 'payload': (context.inputs['payload'] / 'SM_SkatePier.npz').write_bytes(b'changed')
    if damage == 'after_save': state.changed = True
    if damage == 'slot': raw.static_materials[0].values['imported_material_slot_name'] = 'Wrong'
    with pytest.raises(ValueError): body.run(context)


@pytest.mark.parametrize('key,metallic,roles', [('painted', 0., members.ROLES), ('steel', 1., members.ROLES), ('mural', 0., ('albedo',))])
def test_original_per_material_graph_executes_only_declared_texture_roles(tmp_path, monkeypatch, key, metallic, roles):
    import shutil
    class Texture(Asset): pass
    class Material(Asset): pass
    assets, nodes, saves = {}, [], []
    def create(name, folder, cls, factory):
        value = cls(folder + '/' + name); assets[value.path] = value; return value
    def expression(material, cls):
        value = Props(kind=cls); nodes.append(value); return value
    mel = NS(delete_all_material_expressions=lambda _: None, create_material_expression=expression,
        connect_material_expressions=lambda *args: True, connect_material_property=lambda *args: True,
        layout_material_expressions=lambda _: None, recompile_material=lambda _: None)
    class Enum:
        def __getattr__(self, name): return name
    unreal = NS(Texture=Texture, Material=Material, MaterialFactoryNew=lambda: None, CustomInput=Props,
        MaterialEditingLibrary=mel, AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda path: path in assets,
            save_loaded_asset=lambda asset: saves.append(asset.path) or True),
        MaterialSamplerType=Enum(), MaterialProperty=Enum(), CustomMaterialOutputType=Enum(),
        **{name: name for name in ('MaterialExpressionTextureSample', 'MaterialExpressionVertexColor',
            'MaterialExpressionCustom', 'MaterialExpressionConstant', 'MaterialExpressionMultiply')})
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    original = tmp_path / units.ORIGINAL; original.parent.mkdir(parents=True); shutil.copyfile(ROOT / units.ORIGINAL, original)
    selected = tmp_path / 'spec'; selected.mkdir()
    spec = {'key': key, 'entry': {'metallic': metallic, 'maps': {role: 'source-' + role + '.png' for role in roles}}}
    (selected / (key + '.json')).write_text(json.dumps(spec))
    inputs, packages, descriptors = {'spec': selected}, {'spec': []}, {}
    for role in roles:
        slot = 'texture_' + role; package = '/Game/SkatePark/Textures/T_Pier_' + key + '_' + role
        assets[package] = Texture(package); inputs[slot] = 'native'; packages[slot] = [package]
        descriptors[role] = {'derived_items': {'root': role, 'members': [{'piece': key + '_' + role, 'root': slot, 'slot': slot}]}}
    destination = '/Game/SkatePark/Materials/M_Pier_' + key
    context = NS(job_dir=str(tmp_path), inputs=inputs, packages=packages, outputs=[destination], params={
        'args': {'action': 'material', 'piece': key, 'textures': descriptors}})
    asset = body.run(context)
    assert asset.path == destination and saves == [destination]
    assert [n.values['r'] for n in nodes if n.values['kind'] == 'MaterialExpressionConstant'] == [metallic]
    assert sum(n.values['kind'] == 'MaterialExpressionTextureSample' for n in nodes) == len(roles)
    assert any(n.values['kind'] == 'MaterialExpressionVertexColor' for n in nodes) == (key != 'mural')


def test_current_board_uses_supplied_village_and_look_only_collision(native_case):
    state, context = native_case
    piece = 'SM_SkateWheel'; source, payload = context.inputs['source_export'], context.inputs['payload']
    meta, decoded = mesh_ir.decode((payload / 'SM_SkatePier.npz').read_bytes())
    raw = mesh_ir.encode(decoded, key=piece, slots=['SkateParkPalette'], matrix=meta['matrix'], options=meta['options'], collisions=[])
    for folder in (source, payload):
        for path in folder.iterdir(): path.unlink()
    (payload / (piece + '.npz')).write_bytes(raw); (source / (piece + '.fbx')).write_bytes(b'board')
    publish_receipt(source, key=piece, primary=piece + '.fbx', triangles=1, bounds=[[0, 0, 0], [1, 1, 0]],
        metadata={'geometry_sha256': hashlib.sha256(raw).hexdigest(), 'slots': ['SkateParkPalette'], 'polygons': 1,
                  'collision_hulls': 0, 'uv_channels': ['UVMap']})
    old = context.packages['raw'][0]; native = state.assets.pop(old); native.path = '/Game/_Raw/SkatePark/' + piece
    native.static_materials[0].values['imported_material_slot_name'] = 'SkateParkPalette'
    state.assets[native.path] = native; state.assets[units.VILLAGE] = Asset(units.VILLAGE)
    context.packages['raw'] = [native.path]; context.packages['material'] = [units.VILLAGE]
    context.outputs = [units.ROOT + '/Board/' + piece]; context.data_outputs = ['data/reports/' + piece + '.json']
    context.params['destination'] = context.outputs[0]
    context.params['args'] = {'action': 'mesh', 'piece': piece, 'parent': piece, 'board': True, 'blocks': False, 'material': 'material'}
    result = body.run(context); mesh = state.assets[context.outputs[0]]
    assert mesh.get_material(0) is state.assets[units.VILLAGE]
    assert mesh.body.values['collision_trace_flag'] == 'simple' and state.checks == 2
    assert next(iter(result.values()))['board'] is True


@pytest.mark.parametrize('damage', [None, 'missing', 'hash', 'runtime', 'tree'])
def test_native_gate_requires_exact_assembled_runtime_and_actual_report_roster(tmp_path, damage):
    from skatepark.pieces import runtime_park
    logical = ROOT / units.LOGICAL; authored = json.loads(logical.read_bytes())
    membership = {parent: [parent] for parent in units.PARK}
    runtime = runtime_park(authored, membership)
    runtime_file = tmp_path / 'runtime.json'; runtime_file.write_text(json.dumps(runtime))
    identity = {'park_json_sha256': hashlib.sha256(logical.read_bytes()).hexdigest(),
                'runtime_park_sha256': hashlib.sha256(runtime_file.read_bytes()).hexdigest(), 'exports': {}}
    build = {'identity': identity, 'pieces': {'members': membership}, 'meshes': {}, 'material_slots': {}}
    values = {'park': [], 'board': []}
    for family, names in (('park', units.PARK), ('board', units.BOARD)):
        for piece in names:
            entry = next((r for r in runtime['meshes'] if r['name'] == piece), None)
            board = family == 'board'; slots = ['SkateParkPalette'] if board else ['Pier_wood']
            report = {'name': piece, 'triangles': 1, 'blocks': False if board else entry['blocks'], 'board': board,
                      'materials': slots, 'source_sha256': 'a' * 64}
            root = tmp_path / 'reports' / piece; file = root / 'data/reports' / (piece + '.json')
            file.parent.mkdir(parents=True); file.write_text(json.dumps(report))
            values[family].append((NS(products=[NS(paths=[root])]), piece))
            identity['exports'][('board/' if board else 'assets/') + piece + '.fbx'] = 'a' * 64
            build['meshes'][piece] = {'triangles': 1}; build['material_slots'][piece] = slots
    trees = {}
    for name in runtime.get('trees', {}):
        root = tmp_path / 'trees' / name; file = root / ('content/Game/Japan/Assets/' + name + '.uasset')
        file.parent.mkdir(parents=True); file.write_bytes(b'actual Item bytes in unit test'); trees[name] = root
    if damage == 'missing': values['park'].pop()
    if damage == 'hash': identity['exports']['assets/' + units.PARK[0] + '.fbx'] = 'b' * 64
    if damage == 'runtime': runtime['meshes'].pop(); runtime_file.write_text(json.dumps(runtime))
    if damage == 'tree': trees.pop(next(iter(trees)))
    build_file = tmp_path / 'build.json'; build_file.write_text(json.dumps(build))
    build_archive, runtime_archive = tmp_path / 'build.tree.tar', tmp_path / 'runtime.tree.tar'
    pack_root(build_file, build_archive); pack_root(runtime_file, runtime_archive)
    if damage:
        with pytest.raises(ValueError):
            members.complete(build_file, runtime_file, logical, values['park'], values['board'], trees, tmp_path / 'out')
    else:
        members.complete(build_file, runtime_file, logical, values['park'], values['board'], trees, tmp_path / 'out')
        assert len(json.loads((tmp_path / 'out/native.json').read_text())['meshes']) == 10


def test_production_recipe_view_supplies_decoded_texture_root(tmp_path):
    from atelier.build_v2.recipe_job import prepare_view
    import shutil
    archive = textures(tmp_path)
    job = tmp_path / 'job'; staged = job / 'inputs/textures/products/0-0.tree.tar'
    staged.parent.mkdir(parents=True); shutil.copyfile(archive, staged)
    (job / '.recipe-runtime').mkdir()
    view, _, _ = prepare_view({'code': [], 'inputs': [{'path': 'inputs/textures'}], 'params': {'recipe': {
        'paths': {'textures': 'inputs/textures/products/0-0.tree.tar'},
        'outputs': [{'path': 'members', 'file': 'members.tree.tar', 'required': True}]}}}, job)
    assert (view / 'textures').is_dir()
    members.project(view / 'textures', view / 'members', 'materials')
    assert members.read_json(view / 'members/painted.json')['entry']['metallic'] == 0.
