"""Actual ferry rows, committed palettes, per-package Ferry units and fake-editor native bodies."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_ferry_units.py', 'ferry_units_test')
body = load(units.SCRIPT, 'ferry_body_test')


@pytest.fixture(scope='module')
def rows():
    """The actual ferry rows; reads/needs on producers outside the ferry family are dropped only for extraction."""
    factory = load('games/yorimichi/build.py', 'ferry_build_test')
    steps = factory.ferry_steps(NS(out=ROOT / 'build/yorimichi'))
    names, produced = {s.name for s in steps}, {p.name for s in steps for p in s.products}
    for step in steps:
        step.reads = [r for r in step.reads if r in produced]; step.needs = [n for n in step.needs if n in names]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def result(rows):
    return units.ferry_units(rows, checkout=ROOT)


def test_palettes_and_roster_are_committed_and_declared(rows):
    ship, terminal = units.palettes(ROOT)
    assert len(ship) == 20 and len(terminal) == 21 and ship[0] == 'FY_WhitePaint' and 'FT_LanternGlow' in terminal
    roster = units.roster(rows)
    assert roster['Ship'][-1] == 'FY_Collision' and len(roster['Ship']) == 9 and len(roster['Terminals']) == 13


def test_units_bind_exact_roots_and_original_policies(rows, result):
    by_id = {u['id']: u for u in result['units']}
    assert len(by_id) == 3 + 41 + 2 * 22
    ship = next(r for r in rows if r['id'] == 'world.ferry_ship')
    assets = ship['products'][0]['paths'].index('build/yorimichi/ferry/atomic-assets')
    raw = by_id['unreal.ferry.mesh.raw.FY_Hull']
    assert raw['params']['source_member'] == 'FY_Hull.fbx' and 'fbx' not in raw['params']
    assert raw['params']['input_roots'] == {'source': {'archive_member': f'products/0-{assets}.tree.tar', 'name': 'atomic-assets'}}
    hull = by_id['unreal.ferry.mesh.FY_Hull']['params']['args']
    assert set(hull['materials']) == set(result['palettes']['ship']) and 'collision_data' not in hull
    assert hull['parents'] == ['FY_Hull', 'FY_Superstructure', 'FY_Funnel', 'FY_Lifeboats', 'FY_Rails', 'FY_Masts',
                               'FY_Fittings', 'FY_BoardingGate']
    collision = by_id['unreal.ferry.mesh.FY_Collision']
    audit = next(r for r in rows if r['id'] == 'world.ferry_ship.audit')
    index = [p['id'] for p in audit['products']].index('ferry_ship.collision_data')
    assert collision['params']['input_roots']['collision_data']['archive_member'] == f'products/{index}-0.tree.tar'
    brow = by_id['unreal.ferry.mesh.FT_HD_Brow']['params']['args']
    assert len(brow['materials']) == 41 and brow['folder'] == 'Terminals'
    fy = by_id['unreal.ferry.instance.FY_Brass']
    assert fy['params']['args']['manifests'] == ['ship_manifest', 'terminal_manifest']
    assert by_id['unreal.ferry.instance.FT_Brass']['params']['args']['manifests'] == ['terminal_manifest']
    wake = by_id['unreal.ferry.mesh.FY_Wake']
    assert wake['outputs'][0]['logical_path'] == '/Game/Ferry/Ship/FY_Wake' and wake['inputs'][0]['source']['unit'] == 'unreal.ferry.material.M_FerryWake'
    for unit in by_id.values():
        produced = {i['source']['unit'] for i in unit['inputs']} - {r['id'] for r in rows}
        assert produced <= set(by_id) and unit['id'] not in produced
        assert set(result['staged_inputs'][unit['id']]) == {i['name'] for i in unit['inputs']}
        assert set(unit['params'].get('input_roots', {})) <= {i['name'] for i in unit['inputs']}
    code = by_id['unreal.ferry.mesh.FY_Hull']['code']
    assert {units.ORIGINAL, units.NATIVE, 'games/yorimichi/unreal/Scripts/forest_native.py'} <= set(code)
    assert all((ROOT / p).is_file() for p in code)


@pytest.mark.parametrize('damage', ['importer', 'script', 'foreign', 'wake', 'terminal_root', 'data_root'])
def test_changed_original_rows_refuse(rows, damage):
    rows = deepcopy(rows); by_id = {r['id']: r for r in rows}
    if damage == 'importer': rows.remove(by_id['unreal.ferry'])
    elif damage == 'script': by_id['unreal.ferry']['commands'][0]['script'] = {'path': 'other.py'}
    elif damage == 'foreign': by_id['unreal.ferry']['outputs'].append('games/yorimichi/unreal/Content/Ferry/Other/X.uasset')
    elif damage == 'wake': by_id['unreal.ferry']['outputs'].append('games/yorimichi/unreal/Content/Ferry/Ship/FY_Wake.uasset')
    elif damage == 'terminal_root': by_id['world.ferry_terminals']['products'][0]['paths'].pop()
    else: by_id['world.ferry_ship.audit']['products'] = [p for p in by_id['world.ferry_ship.audit']['products']
                                                        if p['id'] != 'ferry_ship.collision_data']
    with pytest.raises(units.Unsupported):
        units.ferry_units(rows, checkout=ROOT)


# ---- native bodies --------------------------------------------------------------------------------------------------

class Props:
    def __init__(self, **values): self.values = dict(values)
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value
class Asset(Props):
    def __init__(self, path, **values): super().__init__(**values); self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Material(Asset): pass
class Instance(Material): pass
class Mesh(Asset):
    def get_num_lods(self): return 1
    def get_num_triangles(self, lod): return self.triangles
    def get_material(self, index): return self.materials[index]
    def set_material(self, index, value): self.materials[index] = value
class Anything:
    """Editor classes and enums the original functions only pass through."""
    def __getattr__(self, name): return name


def editor(tmp_path, monkeypatch, assets):
    state = NS(saves=[], params={})
    content = tmp_path / 'Content'; content.mkdir(exist_ok=True)
    def create(name, folder, cls, factory):
        asset = (Instance if cls is Instance else Material)(folder + '/' + name); assets[asset.path] = asset; return asset
    def duplicate(path, target):
        if path == '/Engine/BasicShapes/Plane':
            result = Mesh(target, body_setup=Props(collision_trace_flag='CTF_USE_DEFAULT')); result.materials = [None]
            result.simple, result.hulls, result.triangles = 1, [], 2
        else:
            source = assets[path]
            result = Mesh(target, body_setup=Props(**source.values['body_setup'].values))
            result.static_materials, result.materials = source.static_materials, list(source.materials)
            result.simple, result.hulls, result.triangles = source.simple, source.hulls, source.triangles
        assets[target] = result; return result
    def save(asset, dirty):
        primary = content / (asset.path.removeprefix('/Game/') + '.uasset'); primary.parent.mkdir(parents=True, exist_ok=True)
        primary.write_bytes(b'p'); state.saves.append(asset.path); return True
    graph = NS(delete_all_material_expressions=lambda m: None, create_material_expression=lambda *a: Props(),
               connect_material_property=lambda *a: True, connect_material_expressions=lambda *a: True,
               recompile_material=lambda m: None, update_material_instance=lambda m: None,
               set_material_instance_parent=lambda m, p: m.set_editor_property('parent', p),
               set_material_instance_vector_parameter_value=lambda m, k, v: state.params.setdefault(m.path, {}).update({k: v}),
               set_material_instance_scalar_parameter_value=lambda m, k, v: state.params.setdefault(m.path, {}).update({k: v}))
    def remove(mesh):
        mesh.simple = 0; return True
    fake = Anything()
    unreal = NS(Material=Material, MaterialInstanceConstant=Instance, MaterialInterface=Material, StaticMesh=Mesh,
        MaterialFactoryNew=lambda: None, MaterialInstanceConstantFactoryNew=lambda: None, CustomInput=Props,
        LinearColor=lambda *v: v, MaterialEditingLibrary=graph, MaterialExpressionVectorParameter='v',
        MaterialExpressionScalarParameter='s', MaterialProperty=fake, BlendMode=fake, MaterialShadingModel=fake,
        CustomMaterialOutputType=fake, MaterialExpressionTextureCoordinate='uv', MaterialExpressionTime='t',
        MaterialExpressionWorldPosition='p', MaterialExpressionSceneDepth='sd', MaterialExpressionPixelDepth='pd',
        MaterialExpressionSubtract='sub', MaterialExpressionCustom='custom',
        CollisionTraceFlag=NS(CTF_USE_DEFAULT='CTF_USE_DEFAULT', CTF_USE_SIMPLE_AS_COMPLEX='CTF_USE_SIMPLE_AS_COMPLEX'),
        StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: NS(get_simple_collision_count=lambda m: m.simple,
                                            get_convex_collision_count=lambda m: len(m.hulls), remove_collisions=remove),
        CitySurfaceValidation=NS(collision_vertices=lambda m: json.dumps(m.hulls)),
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate,
                              save_loaded_asset=save))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    scripts = tmp_path / body.SCRIPTS; scripts.mkdir(parents=True, exist_ok=True)
    for name in ('import_ferry.py', 'ferry_native.py', 'forest_native.py'):
        shutil.copy(ROOT / body.SCRIPTS / name, scripts / name)
    return state, content


def author_context(tmp_path, args, outputs, inputs=None):
    inputs = inputs or {}
    return NS(job_dir=str(tmp_path.resolve()), inputs={k: v[0] for k, v in inputs.items()},
              packages={k: v[1] for k, v in inputs.items()}, outputs=outputs, params={'args': args, 'settings': []})


def test_original_parent_wake_material_and_wake_mesh(tmp_path, monkeypatch):
    assets = {}; state, _ = editor(tmp_path, monkeypatch, assets)
    parent = body.run(author_context(tmp_path, {'action': 'parent'}, ['/Game/Ferry/Materials/M_Ferry']))
    wake = body.run(author_context(tmp_path, {'action': 'wake_material'}, ['/Game/Ferry/Materials/M_FerryWake']))
    assert wake.values['two_sided'] is True and parent.path == '/Game/Ferry/Materials/M_Ferry'
    mesh = body.run(author_context(tmp_path, {'action': 'wake_mesh', 'material': 'wake'}, ['/Game/Ferry/Ship/FY_Wake'],
                                   {'wake': ('n', [wake.path])}))
    assert mesh.materials == [wake] and mesh.simple == 0 and state.saves[-1] == mesh.path


def write(tmp_path, index, name, value):
    path = tmp_path / f'item-{index}' / name; path.parent.mkdir(parents=True); path.write_text(json.dumps(value)); return str(path)


@pytest.mark.parametrize('name,agree', [('FY_Brass', True), ('FY_Brass', False), ('FT_Moss', True)])
def test_instances_agree_across_original_passes(tmp_path, monkeypatch, name, agree):
    assets = {'/Game/Ferry/Materials/M_Ferry': Material('/Game/Ferry/Materials/M_Ferry')}
    state, _ = editor(tmp_path, monkeypatch, assets)
    value = [[206, 164, 78], .35, .55]
    inputs = {'parent': ('n', ['/Game/Ferry/Materials/M_Ferry']),
              'terminal_manifest': (write(tmp_path, 1, 'manifest.json', {'materials': {name: value}}), [])}
    manifests = ['terminal_manifest']
    if name.startswith('FY_'):
        inputs['ship_manifest'] = (write(tmp_path, 0, 'manifest.json', {'materials': {name: value if agree else [[0, 0, 0], .35, .55]}}), [])
        manifests.insert(0, 'ship_manifest')
    ctx = author_context(tmp_path, {'action': 'instance', 'name': name, 'parent': 'parent', 'manifests': manifests},
                         ['/Game/Ferry/Materials/' + name], inputs)
    if not agree:
        with pytest.raises(ValueError):
            body.run(ctx)
        return
    mi = body.run(ctx)
    assert mi.values['parent'] is assets['/Game/Ferry/Materials/M_Ferry']
    assert state.params[mi.path]['Roughness'] == .35 and state.params[mi.path]['Tint'][0] == pytest.approx(((206 / 255 + .055) / 1.055) ** 2.4)


def mesh_case(tmp_path, monkeypatch, name='FY_Collision', folder='Ship', slots=('FY_DarkIron',)):
    hull = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
    proxies = {'schema': 1, 'asset': 'FY_Collision', 'proxies': [{'poly': [[0, 0], [1, 0], [0, 1]], 'z0': [0, 0, 0], 'z1': [1, 1, 1]}]}
    raw_hulls = [[[x * 100, -y * 100, z * 100] for heights in ('z0', 'z1') for (x, y), z in zip(p['poly'], p[heights])]
                 for p in proxies['proxies']] if name == 'FY_Collision' else []
    raw_path = f'/Game/_Raw/Ferry/{folder}/{name}'
    raw = Mesh(raw_path, body_setup=Props(collision_trace_flag='CTF_USE_DEFAULT'))
    raw.static_materials = [Props(imported_material_slot_name=s) for s in slots]
    raw.materials, raw.simple, raw.hulls, raw.triangles = [None] * len(slots), 0, raw_hulls, 12
    parents = ['FY_Hull'] if folder == 'Ship' else ['FT_HD_Brow']
    exports = [{'asset': n, 'triangles': 12, 'metadata': {'slots': list(slots), 'collision_hulls': len(raw_hulls) if n == name else 0,
                                                          'authored_hulls': []}}
               for n in ('FY_Hull', 'FY_Collision')]
    manifest = {'meshes': {'FY_Hull': {}}, 'collision': {'convex_hulls': 1}}
    assets = {raw_path: raw}
    palette = {key: Instance('/Game/Ferry/Materials/' + key) for key in ('FY_DarkIron', 'FY_Brass')}
    assets.update({m.path: m for m in palette.values()})
    state, content = editor(tmp_path, monkeypatch, assets)
    inputs = {'raw': ('r', [raw_path]), 'manifest': (write(tmp_path, 0, 'manifest.json', manifest), []),
              'atomic': (write(tmp_path, 1, 'atomic-manifest.json', {'parents': {p: [p] for p in parents}, 'exports': exports}), []),
              **{'m_' + k: ('n', [m.path]) for k, m in palette.items()}}
    args = {'action': 'mesh', 'name': name, 'folder': folder, 'parents': parents, 'materials': {k: 'm_' + k for k in palette},
            'manifest': 'manifest', 'atomic': 'atomic'}
    if name == 'FY_Collision':
        inputs['collision_data'] = (write(tmp_path, 2, 'ship-collision-data.json', proxies), [])
        args['collision_data'] = 'collision_data'
    dest = f'/Game/Ferry/{folder}/{name}'
    ctx = NS(job_dir=str(tmp_path.resolve()), content_dir=str(content), inputs={k: v[0] for k, v in inputs.items()},
             packages={k: v[1] for k, v in inputs.items()}, outputs=[dest],
             params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
                     'package_sources': {'raw': raw_path}, 'args': args, 'settings': []})
    return state, assets, ctx, palette


@pytest.mark.parametrize('name', ['FY_Collision', 'FY_Hull'])
def test_mesh_finish_keeps_original_policy_and_native_validation(tmp_path, monkeypatch, name):
    state, assets, ctx, palette = mesh_case(tmp_path, monkeypatch, name)
    mesh = body.run(ctx)
    assert mesh.materials == [palette['FY_DarkIron']] and state.saves == [mesh.path]
    assert mesh.values['body_setup'].values['collision_trace_flag'] == (
        'CTF_USE_SIMPLE_AS_COMPLEX' if name == 'FY_Collision' else 'CTF_USE_DEFAULT')


@pytest.mark.parametrize('damage', ['triangles', 'hulls', 'slot', 'roster', 'membership', 'proxies', 'fresh'])
def test_mesh_finish_refuses_changed_sources(tmp_path, monkeypatch, damage):
    state, assets, ctx, palette = mesh_case(tmp_path, monkeypatch, slots=('Mystery',) if damage == 'slot' else ('FY_DarkIron',),
                                            name='FY_Hull' if damage == 'slot' else 'FY_Collision')
    raw = assets[ctx.params['package_sources']['raw']]
    if damage == 'triangles': raw.triangles = 11
    elif damage == 'hulls': raw.hulls = []
    elif damage == 'roster': ctx.params['args']['parents'] = ['FY_Other']
    elif damage == 'membership':
        Path(ctx.inputs['manifest']).write_text(json.dumps({'meshes': {'FY_Hull': {}, 'FY_Extra': {}}, 'collision': {'convex_hulls': 1}}))
    elif damage == 'proxies':
        Path(ctx.inputs['collision_data']).write_text(json.dumps({'schema': 1, 'asset': 'FY_Collision', 'proxies': []}))
    elif damage == 'fresh': assets[ctx.outputs[0]] = Mesh(ctx.outputs[0])
    with pytest.raises(ValueError):
        body.run(ctx)
