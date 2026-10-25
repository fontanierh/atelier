"""Actual gondola rows, exact producer roots, per-package Gondola units and fake-editor native bodies."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_gondola_units.py', 'gondola_units_test')
body = load(units.SCRIPT, 'gondola_body_test')
PARAMS = load(units.KIT + '/params.py', 'gondola_params_test')


@pytest.fixture(scope='module')
def rows():
    factory = load('games/yorimichi/build.py', 'gondola_build_test')
    return extract(factory.gondola_steps(NS(out=ROOT / 'build/yorimichi')), checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def result(rows):
    return units.gondola_units(rows, checkout=ROOT)


def test_roster_is_the_actual_importer_closure(rows):
    roster = units.roster(rows, ROOT)
    assert roster['Kit'] == PARAMS.asset_names() and len(roster['Kit']) == 33
    assert roster['Materials'] == list(PARAMS.MATERIALS) and len(roster['Textures']) == 12
    assert sorted(roster['lods']) == ['GD_L1_Rope_LOD0', 'GD_L2_Rope_LOD0', 'GD_L3_Rope_LOD0']
    assert not any(n.endswith(('_LOD1', '_LOD2')) for n in roster['World'])
    assert roster['textured']['GD_Timber'] == ['GD_wood_grain_color', 'GD_wood_grain_rough']


def test_units_bind_exact_roots_and_original_policies(rows, result):
    by_id = {u['id']: u for u in result['units']}
    roster = units.roster(rows, ROOT)
    assert len(by_id) == 2 * 12 + 26 + 2 * (33 + len(roster['World']))
    kit = next(r for r in rows if r['id'] == 'world.gondola_kit')
    assets = [p['paths'] for p in kit['products'] if p['id'] == 'gondola.kit'][0].index('build/yorimichi/gondola/assets')
    cabin = by_id['unreal.gondola.mesh.raw.GD_Cabin_Collision']
    assert cabin['params']['source_member'] == 'GD_Cabin_Collision.fbx' and 'fbx' not in cabin['params']
    assert cabin['params']['input_roots'] == {'source': {'archive_member': f'products/0-{assets}.tree.tar', 'name': 'assets'}}
    site = next(r for r in rows if r['id'] == 'world.gondola_site')
    index = site['outputs'].index('build/yorimichi/gondola/world/assets/GD_L1_Rope_LOD1.fbx')
    rope = by_id['unreal.gondola.mesh.GD_L1_Rope_LOD0']
    assert rope['params']['args']['lods'] == {'1': 'lod1', '2': 'lod2'}
    assert rope['params']['input_roots']['lod1'] == {'archive_member': f'outputs/{index}.tree.tar', 'name': 'GD_L1_Rope_LOD1.fbx'}
    assert {i['name']: i['source'] for i in rope['inputs']}['lod1'] == {'kind': 'item', 'unit': 'world.gondola_site', 'item': f'output{index}'}
    world = by_id['unreal.gondola.mesh.raw.GD_hidamari_Access']
    assert 'source_member' not in world['params'] and world['inputs'][0]['source']['unit'] == 'world.gondola_site'
    rough = by_id['unreal.gondola.texture.GD_wood_grain_rough']['params']['properties']
    assert rough == {'srgb': False} and by_id['unreal.gondola.texture.GD_wood_grain_color']['params']['properties'] == {}
    timber = by_id['unreal.gondola.material.GD_Timber']
    assert timber['params']['input_roots']['manifest']['name'] == 'manifest.json'
    assert {i['source']['unit'] for i in timber['inputs']} == {'world.gondola_kit', 'unreal.gondola.texture.GD_wood_grain_color',
                                                               'unreal.gondola.texture.GD_wood_grain_rough'}
    assert len(by_id['unreal.gondola.material.GD_Glass']['inputs']) == 1
    for unit in by_id.values():
        produced = {i['source']['unit'] for i in unit['inputs']} - {r['id'] for r in rows}
        assert produced <= set(by_id) and unit['id'] not in produced
        assert set(result['staged_inputs'][unit['id']]) == {i['name'] for i in unit['inputs']}
        assert set(unit['params'].get('input_roots', {})) <= {i['name'] for i in unit['inputs']}
    finish = by_id['unreal.gondola.mesh.GD_Cabin']
    assert len(finish['params']['args']['materials']) == 26 and len(finish['inputs']) == 1 + 26 + 12
    assert all((ROOT / p).is_file() for p in finish['code']) and 'games/yorimichi/unreal/Scripts/mesh_materials.py' in finish['code']
    assert result['packages']['/Game/Gondola/Kit/GD_Cabin']['unit'] == 'unreal.gondola.mesh.GD_Cabin'


@pytest.mark.parametrize('damage', ['missing', 'command', 'extra_output', 'kit_root', 'texture_root', 'site_output'])
def test_changed_original_rows_refuse(rows, damage):
    rows = deepcopy(rows); by_id = {r['id']: r for r in rows}
    if damage == 'missing': rows.remove(by_id['world.gondola_kit.textures'])
    elif damage == 'command': by_id['unreal.gondola']['commands'][0]['script'] = {'path': 'other.py'}
    elif damage == 'extra_output': by_id['unreal.gondola']['outputs'].append('games/yorimichi/unreal/Content/Gondola/Kit/GD_Extra.uasset')
    elif damage == 'kit_root': by_id['world.gondola_kit']['products'][0]['paths'] = by_id['world.gondola_kit']['products'][0]['paths'][:2]
    elif damage == 'texture_root': by_id['world.gondola_kit.textures']['products'][0]['paths'].pop()
    else: by_id['world.gondola_site']['outputs'].pop()
    with pytest.raises(units.Unsupported):
        units.gondola_units(rows, checkout=ROOT)


# ---- native bodies --------------------------------------------------------------------------------------------------

class Props:
    def __init__(self, **values): self.values = dict(values)
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value
    def copy(self): return Props(**self.values)
class Asset(Props):
    def __init__(self, path, **values): super().__init__(**values); self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Material(Asset): pass
class Texture(Asset): pass
class Mesh(Asset):
    def get_num_lods(self): return self.lods
    def set_material(self, index, value): self.static_materials[index].values['material_interface'] = value


def editor(tmp_path, monkeypatch, assets):
    state = NS(saves=[], connected=[], nodes=[], lods=[])
    content = tmp_path / 'Content'; content.mkdir()
    def create(name, folder, cls, factory):
        asset = Material(folder + '/' + name); assets[asset.path] = asset; return asset
    def duplicate(path, target):
        source = assets[path]
        result = Mesh(target, **{k: v for k, v in source.values.items() if k != 'body_setup'})
        result.static_materials = [s.copy() for s in source.static_materials]; result.lods = source.lods
        result.hulls = source.hulls; result.values['body_setup'] = source.values['body_setup'].copy()
        assets[target] = result; return result
    def save(asset, dirty):
        primary = content / (asset.path.removeprefix('/Game/') + '.uasset'); primary.parent.mkdir(parents=True, exist_ok=True)
        primary.write_bytes(b'p'); state.saves.append(asset.path); return True
    def import_lod(mesh, level, path):
        state.lods.append((level, Path(path).name)); mesh.lods += 1; return level
    graph = NS(delete_all_material_expressions=lambda m: None,
               connect_material_property=lambda node, out, prop: state.connected.append((node.values, out, prop)) or True)
    unreal = NS(Material=Material, MaterialInterface=Material, Texture=Texture, StaticMesh=Mesh, MaterialFactoryNew=lambda: None,
        MaterialExpressionTextureSample='sample', MaterialExpressionConstant3Vector='vector', MaterialExpressionConstant='constant',
        MaterialSamplerType=NS(SAMPLERTYPE_LINEAR_COLOR='linear'), LinearColor=lambda *v: v,
        MaterialProperty=NS(MP_BASE_COLOR='base', MP_ROUGHNESS='rough', MP_METALLIC='metal', MP_OPACITY='opacity',
                            MP_EMISSIVE_COLOR='emissive'),
        BlendMode=NS(BLEND_TRANSLUCENT='translucent', BLEND_OPAQUE='opaque'), MaterialEditingLibrary=graph,
        CollisionTraceFlag=NS(CTF_USE_SIMPLE_AS_COMPLEX='simple_as_complex', CTF_USE_COMPLEX_AS_SIMPLE='complex_as_simple'),
        StaticMeshEditorSubsystem=object(), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: NS(get_convex_collision_count=lambda mesh: mesh.hulls, import_lod=import_lod),
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate,
                              save_loaded_asset=save))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    scripts = tmp_path / body.SCRIPTS; scripts.mkdir(parents=True)
    (scripts / 'material_assets.py').write_text(
        "import sys\nstate = None\ndef node(m, cls, x, y, **props):\n    return sys.modules['unreal'].Props(cls=cls, **props)\n"
        "def save_material(m):\n    sys.modules['unreal'].EditorAssetLibrary.save_loaded_asset(m, True)\n")
    (scripts / 'mesh_materials.py').write_text((ROOT / body.SCRIPTS / 'mesh_materials.py').read_text())
    unreal.Props = Props
    return state, content


def material_case(tmp_path, monkeypatch, name):
    manifest = tmp_path / 'item-0/manifest.json'; manifest.parent.mkdir()
    manifest.write_text(json.dumps({'materials': {k: [list(v[0]), v[1], v[2]] for k, v in PARAMS.MATERIALS.items()},
                                    'textured_materials': PARAMS.TEXTURED}))
    texture = PARAMS.TEXTURED.get(name)
    assets = {}
    inputs, packages, args = {'manifest': str(manifest)}, {'manifest': []}, {'action': 'material', 'name': name, 'manifest': 'manifest'}
    if texture:
        for kind in ('color', 'rough'):
            path = f'/Game/Gondola/Textures/GD_{texture}_{kind}'
            assets[path] = Texture(path, srgb=kind == 'color')
            inputs[kind], packages[kind], args[kind] = 'n', [path], kind
    state, _ = editor(tmp_path, monkeypatch, assets)
    ctx = NS(job_dir=str(tmp_path), inputs=inputs, packages=packages, outputs=['/Game/Gondola/Materials/' + name],
             params={'args': args, 'settings': []})
    return state, assets, ctx


@pytest.mark.parametrize('name', ['GD_Glass', 'GD_LampGlow', 'GD_Timber', 'GD_Steel'])
def test_material_keeps_original_graph(tmp_path, monkeypatch, name):
    state, assets, ctx = material_case(tmp_path, monkeypatch, name)
    mat = body.run(ctx)
    props = [prop for _node, _out, prop in state.connected]
    assert mat.values['blend_mode'] == ('translucent' if name == 'GD_Glass' else 'opaque')
    assert ('opacity' in props) == (name == 'GD_Glass') and ('emissive' in props) == (name == 'GD_LampGlow')
    assert mat.values.get('two_sided', False) == (name == 'GD_Glass')
    base = state.connected[0][0]
    if name == 'GD_Timber':
        assert base['texture'] is assets['/Game/Gondola/Textures/GD_wood_grain_color'] and state.connected[1][1] == 'R'
    else:
        assert base['constant'] == (*(body._linear(v) for v in PARAMS.MATERIALS[name][0]), 1.)
    assert state.saves == [mat.path]


def test_material_refuses_srgb_rough_or_missing_texture(tmp_path, monkeypatch):
    state, assets, ctx = material_case(tmp_path, monkeypatch, 'GD_Timber')
    assets['/Game/Gondola/Textures/GD_wood_grain_rough'].values['srgb'] = True
    with pytest.raises(ValueError):
        body.run(ctx)
    del assets['/Game/Gondola/Materials/GD_Timber']
    del ctx.params['args']['color']
    with pytest.raises(ValueError):
        body.run(ctx)


def mesh_case(tmp_path, monkeypatch, name, folder, slots=('GD_Steel',), hulls=0):
    raw = f'/Game/_Raw/Gondola/{folder}/{name}'
    assets = {raw: Mesh(raw, generate_mesh_distance_field=True, body_setup=Props(collision_trace_flag='default'))}
    assets[raw].static_materials = [Props(imported_material_slot_name=s, material_slot_name=s, material_interface=None) for s in slots]
    assets[raw].lods, assets[raw].hulls = 1, hulls
    inputs, packages, materials = {'raw': 'r'}, {'raw': [raw]}, {}
    for key in PARAMS.MATERIALS:
        path = '/Game/Gondola/Materials/' + key; assets[path] = Material(path)
        inputs['m_' + key], packages['m_' + key], materials[key] = 'n', [path], 'm_' + key
    lods = {}
    if name.endswith('_Rope_LOD0'):
        for level in (1, 2):
            path = tmp_path / f'item-{level}' / f'{name[:-1]}{level}.fbx'; path.parent.mkdir(); path.write_bytes(b'fbx')
            inputs[f'lod{level}'], packages[f'lod{level}'], lods[str(level)] = str(path), [], f'lod{level}'
    state, content = editor(tmp_path, monkeypatch, assets)
    dest = f'/Game/Gondola/{folder}/{name}'
    ctx = NS(job_dir=str(tmp_path), content_dir=str(content), inputs=inputs, packages=packages, outputs=[dest],
             params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest, 'package_sources': {'raw': raw},
                     'args': {'action': 'mesh', 'name': name, 'folder': folder, 'materials': materials, 'lods': lods}, 'settings': []})
    return state, assets, ctx


@pytest.mark.parametrize('name,folder,slots,hulls,trace', [
    ('GD_Cabin', 'Kit', ('GD_Steel', 'GD_Glass.001'), 0, 'default'),
    ('GD_Cabin_Collision', 'Kit', ('Hull',), 3, 'simple_as_complex'),
    ('GD_hidamari_Access', 'World', ('GD_Concrete',), 0, 'complex_as_simple'),
    ('GD_L1_Rope_LOD0', 'World', ('GD_Rope',), 0, 'default')])
def test_mesh_keeps_original_collision_slot_and_lod_policy(tmp_path, monkeypatch, name, folder, slots, hulls, trace):
    state, assets, ctx = mesh_case(tmp_path, monkeypatch, name, folder, slots, hulls)
    mesh = body.run(ctx)
    assert mesh.values['generate_mesh_distance_field'] is False and mesh.values['body_setup'].values['collision_trace_flag'] == trace
    expected = [assets['/Game/Gondola/Materials/' + (s.split('.')[0] if s.split('.')[0] in PARAMS.MATERIALS else 'GD_DarkIron')]
                for s in slots]
    assert [s.values['material_interface'] for s in mesh.static_materials] == expected
    assert state.lods == ([(1, 'GD_L1_Rope_LOD1.fbx'), (2, 'GD_L1_Rope_LOD2.fbx')] if 'Rope' in name else [])
    assert state.saves == [mesh.path] and assets[ctx.params['package_sources']['raw']].values['generate_mesh_distance_field'] is True


@pytest.mark.parametrize('damage', ['unknown_slot', 'no_hulls', 'fresh', 'lod_missing', 'palette', 'folder'])
def test_mesh_refuses_changed_state(tmp_path, monkeypatch, damage):
    name = 'GD_Cabin_Collision' if damage == 'no_hulls' else 'GD_L1_Rope_LOD0' if damage == 'lod_missing' else 'GD_Cabin'
    folder = 'World' if damage == 'lod_missing' else 'Kit'
    state, assets, ctx = mesh_case(tmp_path, monkeypatch, name, folder, ('Mystery',) if damage == 'unknown_slot' else ('GD_Steel',), 0)
    if damage == 'fresh': assets[ctx.outputs[0]] = Mesh(ctx.outputs[0])
    elif damage == 'lod_missing': del ctx.params['args']['lods']['2']
    elif damage == 'palette': ctx.packages['m_GD_Steel'] = ['/Game/Gondola/Materials/GD_Rope']
    elif damage == 'folder': ctx.params['args']['folder'] = 'World'
    with pytest.raises(ValueError):
        body.run(ctx)
