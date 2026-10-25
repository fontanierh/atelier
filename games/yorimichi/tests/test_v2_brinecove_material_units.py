"""Individual original Brinecove shader declarations, without Unreal execution."""
import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[3]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


units = load('games/yorimichi/v2_brinecove_material_units.py', 'brinecove_material_units_test')
body = load('games/yorimichi/world/brinecove_material_v2.py', 'brinecove_material_body_test')


def test_static_original_descriptor_semantics_and_complete_individual_owners():
    rows, files = units.static_materials(ROOT)
    assert rows['waterfall']['kind'] == 'masked' and rows['waterfall']['pan'] == .9
    assert rows['foam']['motion'] == {'Drift': .03, 'Wash': .22}
    assert rows['mist']['kind'] == 'translucent' and rows['mist']['motion'] == {'Opacity': .42}
    assert rows['lantern']['kind'] == 'emissive'
    assert rows['rock_dark']['colour'] == [.72] * 3 and rows['rock_dark']['rock_only'] is True
    assert set(rows['terrain']['layers']) == {'Sand', 'Meadow', 'Forest', 'Rock'}
    result = units.author_units(checkout=ROOT, hero_materials={})
    assert result['missing_roles'] == []
    owned = [item['logical_path'] for unit in result['units'] for item in unit['outputs']]
    assert len(set(owned)) == len(owned)
    assert all(units.ROOT + '/Materials/' + row['name'] in result['packages'] for row in rows.values())
    assert all(unit['outputs'][0]['destination'] in ('store', 'checkout') for unit in result['units'])
    normal = next(unit for unit in result['units'] if unit['id'].endswith('.finish.T_BC_terrain_rock_n'))
    assert normal['params']['properties']['srgb'] is False
    albedo = next(unit for unit in result['units'] if unit['id'].endswith('.finish.T_BC_terrain_rock'))
    assert albedo['params']['properties']['srgb'] is True
    assert all((ROOT / path).is_file() for unit in result['units'] for path in unit['code'])
    assert all(path.is_relative_to(ROOT / 'games/yorimichi/assets/brinecove/textures') for path in files.values())


def hero(texture=None):
    return {'name': 'MI_BC_hero_cannon_0', 'colour': [.21, .34, .55], 'texture': texture,
            'kind': 'opaque', 'pan': 0., 'roughness': .8, 'metal': False}


def test_hero_uses_actual_supplied_descriptor_or_explicit_missing_roles():
    absent = units.author_units(checkout=ROOT)
    assert 'hero_material_descriptors' in absent['missing_roles']
    given = units.author_units(checkout=ROOT, hero_materials={'hero_cannon_0': hero()})
    unit = next(unit for unit in given['units'] if unit['id'].endswith('MI_BC_hero_cannon_0'))
    assert unit['params']['args']['descriptor']['colour'] == [.21, .34, .55]
    missing = units.author_units(checkout=ROOT, hero_materials={'hero_cannon_0': hero('T_BC_hero_cannon_0.png')})
    assert 'texture:T_BC_hero_cannon_0.png' in missing['missing_roles']
    assert units.ROOT + '/Materials/MI_BC_hero_cannon_0' not in missing['packages']
    supplied = {'T_BC_hero_cannon_0.png': {'unit': 'actual.hero.texture', 'item': 'texture',
        'package': '/Game/Brinecove/Textures/T_BC_hero_cannon_0'}}
    bound = units.author_units(checkout=ROOT, hero_materials={'hero_cannon_0': hero('T_BC_hero_cannon_0.png')}, textures=supplied)
    unit = next(unit for unit in bound['units'] if unit['id'].endswith('MI_BC_hero_cannon_0'))
    assert any(row['source']['unit'] == 'actual.hero.texture' for row in unit['inputs'])


def test_named_parent_ast_only_never_imports_old_unguarded_main(monkeypatch):
    monkeypatch.setitem(sys.modules, 'atmosphere', NS())
    unreal = NS(EditorAssetLibrary=NS(), MaterialEditingLibrary=NS(), AssetToolsHelpers=NS(get_asset_tools=lambda: NS()))
    result = body.factories(unreal)
    assert result['parent'].__code__.co_filename.endswith('import_brinecove.py')
    assert 'main' not in result and 'yori' not in result and 'surfaces' not in result
    assert 'TERRAIN_WEIGHTS' in result and result['MOTION'] == ('Drift', 'Wash', 'Layer')


@pytest.mark.parametrize('damage', ['colour', 'roughness', 'motion', 'kind'])
def test_nonfinite_or_unknown_hero_semantics_refuse_before_native(damage):
    value = hero()
    if damage == 'colour': value['colour'][0] = math.inf
    elif damage == 'roughness': value['roughness'] = math.nan
    elif damage == 'motion': value['motion'] = {'Unknown': .2}
    else: value['kind'] = 'fallback'
    with pytest.raises(ValueError): units.author_units(checkout=ROOT, hero_materials={'hero_cannon_0': value})


def test_instance_runtime_exact_original_scalars_motion_colour_and_parent(monkeypatch):
    path = '/Game/Brinecove/Materials/MI_BC_hero_cannon_0'
    parent = '/Game/Brinecove/Materials/M_Brinecove'
    class Asset:
        def __init__(self, path): self.path = path
        def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
    result, loaded = Asset(path), Asset(parent)
    calls = {}
    MEL = NS(clear_all_material_instance_parameters=lambda m: calls.update(clear=True),
        set_material_instance_parent=lambda m, p: calls.update(parent=p.path),
        set_material_instance_vector_parameter_value=lambda m, k, v: calls.update({k: v}),
        set_material_instance_scalar_parameter_value=lambda m, k, v: calls.update({k: v}),
        update_material_instance=lambda m: calls.update(updated=True))
    unreal = NS(EditorAssetLibrary=NS(does_asset_exist=lambda p: False, load_asset=lambda p: loaded,
        save_loaded_asset=lambda m, dirty: m is result), MaterialEditingLibrary=MEL,
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=lambda *args: result)),
        MaterialInstanceConstant=object(), MaterialInstanceConstantFactoryNew=lambda: object(), LinearColor=lambda *v: v)
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(params={'args': {'asset': 'MI_BC_hero_cannon_0', 'package': path, 'factory': 'instance',
        'inputs': {'parent': parent}, 'descriptor': hero()}, 'settings': []},
        outputs=[path], inputs={'parent': 'actual-parent-item'}, packages={'parent': [parent]})
    assert body.run(context) is result
    assert calls['parent'] == parent and calls['Colour'] == (.21, .34, .55, 1.)
    assert {k: calls[k] for k in ('UseTex', 'Pan', 'Roughness', 'Metallic', 'Glow')} == {
        'UseTex': 0., 'Pan': 0., 'Roughness': .8, 'Metallic': 0., 'Glow': .045}
