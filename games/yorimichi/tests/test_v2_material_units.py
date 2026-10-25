"""The shared-material replacement is a pure, complete per-package declaration."""
import importlib.util
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
ROOT = GAME.parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


units = module(GAME / 'v2_material_units.py', 'yorimichi_material_units_test')
catalog = module(GAME / 'world/asset_catalog.py', 'yorimichi_material_catalog_test')


def textures():
    return {Path(name).stem: {'unit': 'texture.finish.' + Path(name).stem, 'item': 'texture',
            'package': units.TEXTURES + Path(name).stem} for name in catalog.TEXTURES}


def compiled():
    return units.author_units(textures())


def test_materials_and_textures_cover_the_exact_original_shared_package_roster():
    result = compiled()
    actual = {item['logical_path'] for unit in result['units'] for item in unit['outputs']}
    assert len(result['units']) == len(actual) == 40
    assert actual | {entry['package'] for entry in textures().values()} == set(catalog.shared_packages())
    assert set(result['packages']) == actual
    assert {item['class'] for unit in result['units'] for item in unit['outputs']} == {
        'Material', 'MaterialInstance', 'MaterialParameterCollection'}
    for unit in result['units']:
        assert unit['op'] == {'kind': 'unreal.author', 'version': '1'}
        assert len(unit['outputs']) == 1
        item = unit['outputs'][0]
        assert item['destination'] == 'checkout'
        relative = item['logical_path'].removeprefix('/Game/')
        assert item['files'] == [{'path': 'content/Game/' + relative + suffix,
            'install_path': 'games/yorimichi/unreal/Content/' + relative + suffix,
            'required': suffix == '.uasset'} for suffix in ('.uasset', '.uexp', '.m.ubulk', '.ubulk', '.uptnl', '.upayload')]


def test_content_edges_are_narrow_complete_and_precede_their_consumers():
    result = compiled()
    by_name = {unit['params']['args']['asset']: unit for unit in result['units']}
    def inputs(name):
        return {row['name'] for row in by_name[name]['inputs']}
    assert inputs('MPC_Wind') == inputs('MPC_SeeThrough') == inputs('M_Painterly') == set()
    assert inputs('M_CloudShadow') == {'T_cloudmask'}
    assert inputs('MI_Road') == {'M_Painted', 'T_white', 'MPC_SeeThrough', 'T_road'}
    assert inputs('MI_Sky') == {'M_Sky', 'T_sky'}
    assert inputs('MI_Grass') == {'M_Grass', 'T_white', 'MPC_Wind', 'MPC_SeeThrough', 'T_grass'}
    assert 'T_ground_detail' not in result['content_slots']
    ready = {row['unit'] for row in textures().values()}
    for unit in result['units']:
        assert all(row['role'] == 'content' and row['source']['kind'] == 'item'
                   and row['source']['unit'] in ready for row in unit['inputs'])
        assert result['staged_inputs'][unit['id']] == {row['name']: 'inputs/' + row['name'] for row in unit['inputs']}
        ready.add(unit['id'])
    assert all(value is False for value in result['content_slots'].values())


def test_original_instance_values_and_all_see_through_overrides_survive():
    args = {unit['params']['args']['asset']: unit['params']['args'] for unit in compiled()['units']}
    for name, tint in {'LeafGinkgo': [1., .72, .42], 'BarkTuscan': [.65, .55, .4],
                       'Road': [.34, .33, .33], 'RoofTile': [.4, .42, .48], 'Sky': [1.35] * 3,
                       'Moss': [.30, .38, .16]}.items():
        assert args['MI_' + name]['tint'] == tint
    assert {name for name, value in args.items() if value.get('bark_lod')} == {'MI_Bark', 'MI_BarkOlive', 'MI_BarkTuscan'}
    assert {name.removeprefix('MI_') for name, value in args.items() if value.get('mask_instance')} == {
        'Bark', 'RoofTile', 'Tile', 'Plaster', 'Wood', 'Lattice', 'Vermilion', 'Paint', 'Metal', 'Stone', 'Concrete'}
    assert args['MI_Paint']['cut_scale'] == [1., .25, 1., 1.]
    assert args['M_Grass']['overlay'] == {'scale': [1., 1., 2.5, 1.], 'whole_fade': False}
    assert args['M_Painted']['overlay']['blend'] is False
    assert args['M_Foliage']['overlay'] == {'blend': False, 'scale': [1., 1., 2., 1.]}


def test_actual_frozen_code_closure_contains_original_narrow_factories():
    result = units.author_units(textures(), checkout=ROOT)
    code = set(result['units'][0]['code'])
    assert code == set(units.CODE)
    assert 'games/yorimichi/unreal/Scripts/shared_materials.py' in code
    assert 'platform/studio/atelier/build.py' not in code


def test_missing_or_misbound_finished_texture_refuses_declarations():
    mapping = textures()
    del mapping['T_white']
    with pytest.raises(ValueError, match='missing finished'):
        units.author_units(mapping)
    mapping = textures()
    mapping['T_white']['package'] = units.TEXTURES + 'T_road'
    with pytest.raises(ValueError, match='canonical package'):
        units.author_units(mapping)
