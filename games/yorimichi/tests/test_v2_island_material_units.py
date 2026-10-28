"""Island package ownership and dependency declarations are complete and narrow."""
import importlib.util
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME.parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


units = load(GAME / 'v2_island_material_units.py', 'island_material_units_test')
policy = load(GAME / 'island_native_policy.py', 'island_policy_test')
shared = load(GAME / 'v2_material_units.py', 'shared_material_units_test')
catalog = load(GAME / 'world/asset_catalog.py', 'island_catalog_test')


def packages():
    textures = {Path(name).stem: {'unit': Path(name).stem, 'item': 'texture',
                'package': '/Game/Japan/Textures/' + Path(name).stem} for name in catalog.TEXTURES}
    result = shared.author_units(textures)['packages']
    result.update({row['package']: row for row in textures.values()})
    result[units.TEXTURE] = {'unit': 'coast.texture.finish', 'item': 'texture', 'package': units.TEXTURE}
    result['north_snow'] = {'unit': 'world.hidamari.north_masks', 'item': 'product0', 'file': 'products/0-1.tree.tar'}
    return result


def test_exact_island_policy_has_individual_owners_and_finished_texture_dependency():
    result = units.author_units(packages(), checkout=ROOT)
    assert len(result['units']) == 7
    assert set(result['packages']) == set(policy.MATERIAL_PACKAGES)
    assert result['packages'][units.TEXTURE]['unit'] == 'coast.texture.finish'
    for unit in result['units']:
        assert len(unit['outputs']) == 1
        item = unit['outputs'][0]
        assert item['class'] in ('Material', 'MaterialInstance')
        assert item['destination'] == 'checkout'
        assert unit['op'] == {'kind': 'unreal.author', 'version': '1'}
        assert item['files'][0]['required'] and item['files'][0]['path'].endswith('.uasset')
        assert {row['path'].removeprefix('content/Game/' + item['logical_path'].removeprefix('/Game/'))
                for row in item['files'][1:]} == set(policy.SIDECARS)
        assert all(row['install_path'].startswith('games/yorimichi/unreal/Content/') for row in item['files'])
    assert set(result['staged_inputs']) == {unit['id'] for unit in result['units']}
    assert all(value is False for value in result['content_slots'].values())


def test_snow_metadata_is_explicit_only_for_forest_and_native_parent_closure_is_complete():
    by_name = {row['params']['args']['asset']: row for row in units.author_units(packages(), checkout=ROOT)['units']}
    def names(name):
        return {row['name'] for row in by_name[name]['inputs']}
    assert names('M_ForestGround') == {'T_ground', 'T_ground_detail', 'north_snow'}
    assert names('MI_FarForest') == names('MI_Coast') == {'M_ForestGround', 'T_ground', 'T_ground_detail'}
    assert names('M_CoastRock') == {'T_CoastRock'}
    assert names('MI_CoastRock') == {'M_CoastRock', 'T_CoastRock'}
    assert names('MI_Sand') == {'M_Painted', 'T_white', 'MPC_SeeThrough'}
    assert names('M_Sea') == set()
    snow = next(row for row in by_name['M_ForestGround']['inputs'] if row['name'] == 'north_snow')
    assert snow['source'] == {'kind': 'item', 'unit': 'world.hidamari.north_masks', 'item': 'product0'}
    assert by_name['M_ForestGround']['params']['args']['north_snow'] == {'file': 'products/0-1.tree.tar'}
    assert all(row['role'] == 'content' for unit in by_name.values() for row in unit['inputs'])


@pytest.mark.parametrize('missing', ['north_snow', units.TEXTURE, '/Game/Japan/Textures/T_ground_detail'])
def test_missing_actual_upstream_owner_refuses(missing):
    mapping = packages()
    del mapping[missing]
    with pytest.raises(ValueError):
        units.author_units(mapping, checkout=ROOT)


def test_all_original_atomic_piece_material_bindings_have_current_owners():
    products = load(GAME / 'island_atomic_products.py', 'island_atomic_material_bindings_test')
    upstream = packages()
    result = units.author_units(upstream, checkout=ROOT)
    owned = set(upstream) | set(result['packages'])
    for parent, slots in products.MATERIALS.items():
        assert set(products.material_paths(parent, list(slots)).values()) <= owned
