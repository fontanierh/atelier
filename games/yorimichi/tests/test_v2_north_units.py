"""North's own packages as native units: declaration from the actual rows, bodies on a fake editor."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_north_units.py', 'north_units_test')
body = load(units.SCRIPT, 'north_body_test')
NATIVES = {'/Game/Japan/Textures/T_ground_detail': {'unit': 'unreal.texture.finish.ground_detail', 'item': 'texture'},
           '/Game/Japan/Textures/T_ground': {'unit': 'unreal.texture.finish.ground', 'item': 'texture'},
           '/Game/Japan/Materials/MPC_Wind': {'unit': 'unreal.material.MPC_Wind', 'item': 'asset'}}
STEPS = {'unreal.north', 'world.hidamari.north_masks', 'world.craterpark_restyle'}
MASK = {'srgb': False, 'compression_settings': {'unreal_enum': 'TextureCompressionSettings.TC_GRAYSCALE'},
        'mip_gen_settings': {'unreal_enum': 'TextureMipGenSettings.TMGS_SIMPLE_AVERAGE'},
        'address_x': {'unreal_enum': 'TextureAddress.TA_CLAMP'}, 'address_y': {'unreal_enum': 'TextureAddress.TA_CLAMP'},
        'never_stream': True}


@pytest.fixture(scope='module')
def rows():
    """The actual North rows; reads/needs on producers outside them are dropped only for extraction."""
    factory = load('games/yorimichi/build.py', 'north_build_test')
    ctx = NS(game='yorimichi', out=ROOT / 'build/yorimichi', uproject=None)
    steps = [s for s in factory.world_steps(ctx) + factory.unreal_steps(ctx) if s.name in STEPS]
    produced = {p.name for s in steps for p in s.products}
    for step in steps:
        step.reads = [r for r in step.reads if r in produced]; step.needs = [n for n in step.needs if n in STEPS]
        step.after = [n for n in step.after if n in STEPS]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def north(rows):
    return units.north_units(rows, checkout=ROOT, natives=NATIVES)


def by_id(north):
    return {u['id']: u for u in north['units']}


def test_prelude_split_is_the_original_texture_imports():
    specs, graph = body.split((ROOT / units.ORIGINAL).read_bytes())
    assert [(s['name'], s['properties']) for s in specs] == [
        ('T_VolcanicRock', {'srgb': True, 'max_texture_size': 2048}), ('T_NorthSnowMask', MASK),
        ('T_NorthCraterMask', MASK), ('T_NorthCraterFloor', {'srgb': True, 'max_texture_size': 1024})]
    import ast
    text = '\n'.join(ast.unparse(n) for n in graph)
    assert 'task' not in text and 'import_asset_tasks' not in text and "set_editor_property('texture', rock)" in text
    assert "assert hashlib.sha256(floor_png.read_bytes()).hexdigest() == painted['sha256']" in text


@pytest.mark.parametrize('edit', [
    ("rock.set_editor_property('srgb',True)", "rock.set_editor_property('srgb',True);rock=None"),
    ("    x0,y0,_,_=snow_meta['bounds']\n", "    x0,y0,_,_=snow_meta['bounds']\n    floor_texture=rock\n"),
    ("rock.set_editor_property('max_texture_size',2048)", "rock.set_editor_property('max_texture_size',size)"),
    ("task.destination_name='T_NorthCraterFloor'", "task.destination_name='T_Other'")])
def test_prelude_drift_refuses(edit):
    source = (ROOT / units.ORIGINAL).read_text()
    assert edit[0] in source
    with pytest.raises(ValueError):
        body.split(source.replace(edit[0], edit[1], 1))


def test_textures_come_from_actual_source_items(north):
    found = by_id(north)
    assert len(found) == 11
    rock = found['unreal.north.texture.raw.T_VolcanicRock']
    assert rock['inputs'][0]['source'] == {'kind': 'file', 'path': units.ROCK} and 'input_roots' not in rock['params']
    for key, member in (('Snow', 'products/0-0.tree.tar'), ('Crater', 'products/0-2.tree.tar')):
        raw = found[f'unreal.north.texture.raw.T_North{key}Mask']
        assert raw['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.hidamari.north_masks', 'item': 'product0'}
        assert raw['params']['input_roots'] == {'source': {'archive_member': member, 'name': f'north_{key.lower()}.png'}}
        assert found[f'unreal.north.texture.T_North{key}Mask']['params']['properties'] == MASK
    floor = found['unreal.north.texture.raw.T_NorthCraterFloor']
    assert floor['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.craterpark_restyle', 'item': 'output0'}
    assert floor['params']['source_member'] == 'crater_floor.png'
    assert floor['params']['input_roots'] == {'source': {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}}
    for name in ('T_VolcanicRock', 'T_NorthSnowMask', 'T_NorthCraterMask', 'T_NorthCraterFloor'):
        finish = found['unreal.north.texture.' + name]
        assert finish['params']['destination'] == '/Game/Japan/Textures/' + name
        assert finish['inputs'] == [{'role': 'content', 'name': 'raw', 'source': {
            'kind': 'item', 'unit': 'unreal.north.texture.raw.' + name, 'item': 'raw_texture'}}]
        assert found['unreal.north.texture.raw.' + name]['outputs'][0]['destination'] == 'store'


def test_materials_take_finished_textures_and_declared_metadata(north):
    found = by_id(north)
    mountains = found['unreal.north.material.M_NorthMountains']
    sources = {i['name']: i['source'] for i in mountains['inputs']}
    assert sources['native_Japan_Textures_T_NorthSnowMask'] == {'kind': 'item', 'unit': 'unreal.north.texture.T_NorthSnowMask', 'item': 'texture'}
    assert sources['native_Japan_Materials_MPC_Wind'] == {'kind': 'item', 'unit': 'unreal.material.MPC_Wind', 'item': 'asset'}
    assert set(sources) == {'native_Japan_Textures_' + n for n in ('T_VolcanicRock', 'T_NorthSnowMask', 'T_NorthCraterMask',
                            'T_NorthCraterFloor', 'T_ground_detail')} | {'native_Japan_Materials_MPC_Wind', 'snow', 'crater', 'restyle'}
    assert mountains['params']['input_roots'] == {
        'snow': {'archive_member': 'products/0-1.tree.tar', 'name': 'north_snow.json'},
        'crater': {'archive_member': 'products/0-3.tree.tar', 'name': 'north_crater.json'},
        'restyle': {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}}
    for unit in (u for u in north['units'] if u['op']['kind'] == 'unreal.author'):
        assert unit['params']['settings'] == ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false']
        assert unit['outputs'][0]['destination'] == 'checkout' and unit['script'] == units.SCRIPT
        assert {units.ORIGINAL, units.TABLE, 'games/yorimichi/unreal/Scripts/atmosphere.py',
                'games/yorimichi/unreal/Scripts/ground_grain.py', 'games/yorimichi/unreal/Scripts/sea_look.py'} <= set(unit['code'])
    rock = found['unreal.north.material.MI_NorthRockCaps']
    assert rock['outputs'][0]['class'] == 'MaterialInstance'  # Registered native class; SDK remains MaterialInstanceConstant.
    assert {i['name'] for i in rock['inputs']} == {i['name'] for i in mountains['inputs'][:6]} | {'native_Japan_Materials_M_NorthMountains'}
    assert [d['package'] for d in north['packages']['/Game/Japan/Materials/MI_NorthRockCaps']['dependencies']][0] == \
        '/Game/Japan/Materials/M_NorthMountains'
    gate = found['unreal.north.material.M_NorthGate']
    assert [i['source'] for i in gate['inputs']] == [{'kind': 'item', 'unit': 'unreal.texture.finish.ground', 'item': 'texture'}]
    assert set(north['packages']) == {'/Game/Japan/Textures/' + n for n in ('T_VolcanicRock', 'T_NorthSnowMask', 'T_NorthCraterMask',
                                      'T_NorthCraterFloor')} | {'/Game/Japan/Materials/' + n for n in ('M_NorthMountains',
                                      'MI_NorthRockCaps', 'M_NorthGate')}


@pytest.mark.parametrize('damage', ['command', 'masks', 'restyle', 'input', 'native'])
def test_declaration_drift_refuses(rows, damage):
    rows, natives = deepcopy(rows), dict(NATIVES)
    found = {r['id']: r for r in rows}
    if damage == 'command':
        found['unreal.north']['commands'][0]['env'] = [['HIDAMARI_ASSETS', 'HD_*']]
    elif damage == 'masks':
        found['world.hidamari.north_masks']['products'][0]['optional_paths'] = ['x']
    elif damage == 'restyle':
        found['world.craterpark_restyle']['outputs'] = ['build/yorimichi/craterpark/textures/crater_floor.png']
    elif damage == 'input':
        found['unreal.north']['inputs'] = [i for i in found['unreal.north']['inputs'] if not i['path'].endswith('crater_floor.png')]
    else:
        natives.pop('/Game/Japan/Materials/MPC_Wind')
    with pytest.raises(ValueError):
        units.north_units(rows, checkout=ROOT, natives=natives)


# ---- native bodies --------------------------------------------------------------------------------------------------

class Props:
    def __init__(self, **values): self.values = dict(values)
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value
class Asset(Props):
    def __init__(self, path, **values): super().__init__(**values); self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Texture(Asset): pass
class Material(Asset): pass
class Instance(Asset): pass
class Fake(NS):
    def __getattr__(self, name): return name


def editor(tmp_path, monkeypatch, assets):
    state = NS(saves=[], expressions=[], scalars={})
    def create(name, folder, cls, factory):
        asset = cls(folder + '/' + name); assets[asset.path] = asset; return asset
    def expression(m, cls, *xy):
        node = Props(cls=cls); state.expressions.append(node); return node
    def task():
        raise AssertionError('no inline import task may run')
    graph = Fake(delete_all_material_expressions=lambda m: None, create_material_expression=expression,
                 connect_material_expressions=lambda *a: True, connect_material_property=lambda *a: True,
                 recompile_material=lambda m: None, update_material_instance=lambda m: None,
                 set_material_instance_parent=lambda m, p: m.set_editor_property('parent', p),
                 set_material_instance_scalar_parameter_value=lambda m, k, v: state.scalars.setdefault(m.path, {}).update({k: v}),
                 get_material_instance_scalar_parameter_value=lambda m, k: state.scalars[m.path][k])
    unreal = Fake(Texture=Texture, Material=Material, MaterialInstanceConstant=Instance, MaterialInterface=Material,
                  MaterialFactoryNew=lambda: None, MaterialInstanceConstantFactoryNew=lambda: None, CustomInput=Props,
                  AssetImportTask=task, MaterialEditingLibrary=graph, MaterialProperty=Fake(), CustomMaterialOutputType=Fake(),
                  MaterialSamplerType=Fake(), AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                  EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets,
                                        save_loaded_asset=lambda a: state.saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    for name in ('atmosphere', 'sea_look', 'ground_grain'):
        monkeypatch.delitem(sys.modules, name, raising=False)
        target = tmp_path / body.SCRIPTS / (name + '.py'); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / body.SCRIPTS / (name + '.py'), target)
    shutil.copy(ROOT / body.ORIGINAL, tmp_path / body.ORIGINAL)
    (tmp_path / body.TOOLS).mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / units.TABLE, tmp_path / units.TABLE)
    return state


def context(tmp_path, params, inputs, outputs):
    return NS(job_dir=str(tmp_path.resolve()), inputs={k: v[0] for k, v in inputs.items()},
              packages={k: v[1] for k, v in inputs.items()}, outputs=outputs, params=params)


def sources(tmp_path, *, png='crater_floor.png', sha=None):
    meta = {'linear': True, 'size': [1024, 1024], 'bounds': [-100., -200., 100., 200.], 'step_m': 4.,
            'volcano_m': [10., 20.], 'rock_radius_m': [1., 2.], 'rock_prominence_m': [3., 4.], 'south_join_m': 50.}
    inputs = {}
    for slot in ('snow', 'crater'):
        path = tmp_path / ('item-' + slot) / f'north_{slot}.json'; path.parent.mkdir(); path.write_text(json.dumps(meta))
        inputs[slot] = (str(path.resolve()), [])
    restyle = tmp_path / 'item-restyle' / 'textures'; restyle.mkdir(parents=True)
    (restyle / 'crater_floor.png').write_bytes(b'floor')
    (restyle / 'textures.json').write_text(json.dumps({'world_aligned': {'crater_floor': {
        'png': png, 'sha256': sha or hashlib.sha256(b'floor').hexdigest(), 'metres': 16}}}))
    inputs['restyle'] = (str(restyle.resolve()), [])
    return inputs


def mountains_inputs(tmp_path, monkeypatch, **kw):
    assets = {}
    state = editor(tmp_path, monkeypatch, assets)
    inputs, textures = sources(tmp_path, **kw), {}
    for package in (*(f'/Game/Japan/Textures/{n}' for n in ('T_VolcanicRock', 'T_NorthSnowMask', 'T_NorthCraterMask',
                                                             'T_NorthCraterFloor', 'T_ground_detail')),):
        assets[package] = Texture(package); slot = units._slot(package)
        inputs[slot] = ('n', [package]); textures[package.rsplit('/', 1)[1]] = slot
    assets['/Game/Japan/Materials/MPC_Wind'] = Asset('/Game/Japan/Materials/MPC_Wind')
    inputs['wind'] = ('n', ['/Game/Japan/Materials/MPC_Wind'])
    args = {'action': 'mountains', 'textures': {k: v for k, v in textures.items() if k != 'T_ground_detail'},
            'natives': {'detail': textures['T_ground_detail'], 'wind': 'wind'},
            'snow': 'snow', 'crater': 'crater', 'restyle': 'restyle', 'floor': 'crater_floor.png'}
    return assets, state, inputs, args


def test_mountains_is_the_original_graph_over_finished_textures(tmp_path, monkeypatch):
    assets, state, inputs, args = mountains_inputs(tmp_path, monkeypatch)
    material = body.run(context(tmp_path, {'args': args, 'settings': []}, inputs, ['/Game/Japan/Materials/M_NorthMountains']))
    assert material.path == '/Game/Japan/Materials/M_NorthMountains' and state.saves == [material.path]
    assert material.values == {'used_with_instanced_static_meshes': True, 'dithered_lod_transition': True}
    bound = [n.values['texture'].path for n in state.expressions if 'texture' in n.values]
    assert bound == ['/Game/Japan/Textures/' + n for n in ('T_VolcanicRock', 'T_ground_detail', 'T_NorthSnowMask',
                                                          'T_NorthCraterMask', 'T_NorthCraterFloor')]
    code = next(n.values['code'] for n in state.expressions if 'code' in n.values)
    assert 'snowUV=(float2(P.x,-P.y)/100.-float2(-100.0,-200.0))/4.0' in code and 'float3 cp=P/1600.0' in code


@pytest.mark.parametrize('damage', ['png', 'sha', 'meta'])
def test_mountains_gates_refuse(tmp_path, monkeypatch, damage):
    kw = {'png': 'other.png'} if damage == 'png' else {'sha': '0' * 64} if damage == 'sha' else {}
    assets, state, inputs, args = mountains_inputs(tmp_path, monkeypatch, **kw)
    if damage == 'meta':
        Path(inputs['crater'][0]).write_text(json.dumps({'linear': True, 'size': [1024, 1024], 'bounds': [0, 0, 1, 1], 'step_m': 4.}))
    with pytest.raises((ValueError, AssertionError)):
        body.run(context(tmp_path, {'args': args, 'settings': []}, inputs, ['/Game/Japan/Materials/M_NorthMountains']))
    assert state.saves == []


def test_rock_and_gate_are_the_original_functions(tmp_path, monkeypatch):
    assets = {}; state = editor(tmp_path, monkeypatch, assets)
    parent = assets['/Game/Japan/Materials/M_NorthMountains'] = Material('/Game/Japan/Materials/M_NorthMountains')
    ground = assets['/Game/Japan/Textures/T_ground'] = Texture('/Game/Japan/Textures/T_ground')
    inputs = {'parent': ('n', [parent.path]), 'ground': ('n', [ground.path])}
    rock = body.run(context(tmp_path, {'args': {'action': 'rock', 'parent': 'parent', 'closure': []}, 'settings': []},
                            inputs, ['/Game/Japan/Materials/MI_NorthRockCaps']))
    assert rock.values['parent'] is parent and state.scalars[rock.path] == {'Caps': 1.}
    gate = body.run(context(tmp_path, {'args': {'action': 'gate', 'ground': 'ground'}, 'settings': []},
                            inputs, ['/Game/Japan/Materials/M_NorthGate']))
    assert [n.values['texture'] for n in state.expressions if 'texture' in n.values] == [ground]
    assert gate.values == {'used_with_instanced_static_meshes': True}
    with pytest.raises(ValueError):
        body.run(context(tmp_path, {'args': {'action': 'gate', 'ground': 'ground'}, 'settings': []},
                         inputs, ['/Game/Japan/Materials/M_NorthGate']))
