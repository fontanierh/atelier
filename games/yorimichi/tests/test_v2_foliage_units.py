"""C3 foliage declarations consume fixed original LOD exports and assembled manifests only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import foliage_build  # noqa: E402
import v2_foliage_units as foliage  # noqa: E402
from v2_texture_units import PLUGIN  # noqa: E402


@pytest.fixture(scope='module')
def rows():
    steps = foliage_build.world_steps(SimpleNamespace(out=ROOT / 'build/yorimichi'))
    return [row for row in extract(steps, checkout=ROOT, build_root=ROOT / 'build')
            if row['id'].startswith('world.foliage.') and row['id'] != 'world.foliage_lods']


def natives():
    roster = foliage.roster(ROOT)
    packages = {'/Game/Japan/Materials/MI_' + key for entry in roster.values() for key in entry['materials']}
    packages |= {foliage.PARENT, foliage.WHITE}
    return {package: {'unit': 'native.' + package.rpartition('/')[2], 'item': 'material'} for package in packages}


def build(rows):
    return foliage.foliage_units(rows, checkout=ROOT, natives=natives())


def test_roster_is_every_fixed_mesh_lod_and_crown_of_all_owners():
    roster = foliage.roster(ROOT)
    assert list(roster) == list(foliage_build.catalog.FOLIAGE) and len(roster) == 18
    for owner, entry in roster.items():
        spec = json.loads((GAME / 'assets/foliage' / (owner + '.json')).read_text())
        count = len(spec['screen_sizes']) + (spec.get('far_crown') is not None)
        assert [key for key, _ in entry['chain']] == [owner] + [f'{owner}_LOD{level}' for level in range(1, count)]
        assert [level for _, level in entry['chain']] == list(range(count))
        assert entry['materials'] == spec['materials'] and entry['crown'] == (spec.get('far_crown') is not None)
    assert len(roster['Tree_Broad_A']['chain']) == 6 and len(roster['Grass_A']['chain']) == 3


def test_each_key_becomes_one_store_only_raw_import_of_its_export_item(rows):
    result = build(rows)
    raws = [unit for unit in result['units'] if unit['op']['kind'] == 'unreal.raw_import']
    assert len(raws) == 10 * 6 + 8 * 3
    for unit in raws:
        package = unit['params']['destination']; ref = result['packages'][package]; key = ref['key']
        assert package == f'/Game/_Raw/Foliage/{ref["owner"]}/{key}'
        assert unit['params'] == {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': package,
                                  'fbx': foliage.FBX, 'settings': ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false'],
                                  'input_roots': {'source': {'archive_member': 'products/0-0.tree.tar', 'name': key}}}
        assert unit['inputs'] == [{'role': 'content', 'name': 'source', 'source': {
            'kind': 'item', 'unit': 'world.foliage.export.' + key, 'item': 'product0'}}]
        output, = unit['outputs']
        assert output['class'] == 'RawStaticMesh' and output['destination'] == 'store'
        assert all('install_path' not in file for file in output['files'])
    assert not any(ref.get('key', '').endswith('_Seed') for ref in result['packages'].values())


def test_one_owner_uses_only_its_real_rows_and_keeps_the_full_build_declarations(rows):
    owner = 'Tree_Broad_A'
    entry = foliage.roster(ROOT)[owner]
    wanted = {'world.foliage.' + owner, *('world.foliage.export.' + key for key, _ in entry['chain'])}
    selected = [row for row in rows if row['id'] in wanted]
    required = {foliage.PARENT, foliage.WHITE, *('/Game/Japan/Materials/MI_' + key for key in entry['materials'])}
    supplied = {key: value for key, value in natives().items() if key in required}
    result = foliage.foliage_units(selected, checkout=ROOT, natives=supplied, owners=(owner,))
    full = build(rows)
    expected_ids = {'unreal.foliage.finish.' + owner, 'unreal.foliage.crown.' + owner,
                    *('unreal.foliage.raw.' + key for key, _ in entry['chain'])}
    assert {unit['id'] for unit in result['units']} == expected_ids
    assert result['units'] == [unit for unit in full['units'] if unit['id'] in expected_ids]
    assert all(ref['owner'] == owner for ref in result['packages'].values())


@pytest.mark.parametrize('owners', [(), ('missing',), ('Tree_Broad_A', 'Tree_Broad_A'), 'Tree_Broad_A'])
def test_invalid_owner_selection_refuses(rows, owners):
    with pytest.raises(foliage.Unsupported, match='owner selection'):
        foliage.foliage_units(rows, checkout=ROOT, natives=natives(), owners=owners)


def test_tree_finish_owns_base_and_lods_and_consumes_raw_manifest_palette_and_crown(rows):
    result = build(rows)
    by_id = {unit['id']: unit for unit in result['units']}
    finish = by_id['unreal.foliage.finish.Tree_Broad_A']
    assert finish['op'] == {'kind': 'unreal.finish', 'version': '1'} and finish['script'] == foliage.FINISH
    assert {foliage.FINISH, foliage.HELPERS} <= set(finish['code'])
    assert [(o['id'], o['logical_path'], o['class'], o['destination']) for o in finish['outputs']] == [
        ('static_mesh', '/Game/Japan/Assets/Tree_Broad_A', 'StaticMesh', 'checkout')] + [
        (f'lod{i}', f'/Game/Japan/FoliageLODs/Tree_Broad_A/Tree_Broad_A_LOD{i}', 'StaticMesh', 'checkout') for i in range(1, 6)]
    assert finish['outputs'][0]['files'][0] == {'path': 'content/Game/Japan/Assets/Tree_Broad_A.uasset', 'required': True,
        'install_path': 'games/yorimichi/unreal/Content/Japan/Assets/Tree_Broad_A.uasset'}
    sources = {item['name']: item['source'] for item in finish['inputs']}
    assert sources['manifest'] == {'kind': 'item', 'unit': 'world.foliage.Tree_Broad_A', 'item': 'product0'}
    assert [sources[f'lod{i}'] for i in range(6)] == [{'kind': 'item', 'unit': 'unreal.foliage.raw.' + key,
        'item': 'raw_static_mesh'} for key in ['Tree_Broad_A'] + [f'Tree_Broad_A_LOD{i}' for i in range(1, 6)]]
    assert sources['crown'] == {'kind': 'item', 'unit': 'unreal.foliage.crown.Tree_Broad_A', 'item': 'material'}
    args = finish['params']['args']
    assert finish['params']['source'] == 'lod0' and args['levels'] == [f'lod{i}' for i in range(6)]
    assert set(args['materials']) == set(foliage.roster(ROOT)['Tree_Broad_A']['materials'])
    assert finish['params']['input_roots'] == {'manifest': {'archive_member': 'products/0-0.tree.tar', 'name': 'Tree_Broad_A'}}
    crown = by_id['unreal.foliage.crown.Tree_Broad_A']
    assert crown['op'] == {'kind': 'unreal.author', 'version': '1'} and crown['params']['args']['action'] == 'crown'
    assert [(o['logical_path'], o['class']) for o in crown['outputs']] == [
        ('/Game/Japan/FoliageLODs/Tree_Broad_A/MI_Tree_Broad_A_Crown', 'MaterialInstance')]
    assert {item['name']: item['source']['unit'] for item in crown['inputs'][1:]} == {
        'parent': 'native.M_Painted', 'white': 'native.T_white'}
    grass = by_id['unreal.foliage.finish.Grass_A']
    assert grass['params']['args']['crown'] is None and 'unreal.foliage.crown.Grass_A' not in by_id
    assert len(result['units']) == 84 + 18 + 10


# The controller registry's admitted params (unreal_controller.rs register): any other key refuses.
AUTHOR = {'args', 'settings', 'input_roots'}
NATIVE = {'op', 'kind', 'source', 'destination', 'properties', 'args', 'fbx', 'package_sources', 'partners',
          'input_roots', 'skeleton', 'physics_asset', 'materials', 'lod_build_settings', 'settings'}


def test_every_declaration_uses_only_registered_params(rows):
    for unit in build(rows)['units']:
        params = unit['params']
        if unit['op']['kind'] == 'unreal.author':
            assert set(params) <= AUTHOR and 'args' in params and params['settings'] == []
        else:
            assert set(params) <= NATIVE and {'op', 'kind', 'source', 'destination'} <= set(params)
            assert params['op'] == unit['op']['kind'].removeprefix('unreal.') and params['kind'] == 'static_mesh'
        assert all(isinstance(params[key], list) for key in ('settings', 'materials') if key in params)


def test_fbx_options_equal_the_original_mesh_import():
    source = (GAME / 'unreal/Scripts/mesh_import.py').read_text()
    for key, value in foliage.FBX.items():
        assert f'{key}={value!r}' in source
    assert 'Interchange.FeatureFlags.Import.FBX 0' in (GAME / 'unreal/Scripts/import_foliage.py').read_text()


def test_shared_material_and_crown_dependencies_are_staged_transitively(rows):
    supplied = natives()
    bark = '/Game/Japan/Materials/MI_Bark'
    assert bark in supplied
    supplied[bark]['dependencies'] = ['/Game/Japan/Materials/M_Painted', '/Game/Japan/Textures/T_bark']
    supplied['/Game/Japan/Textures/T_bark'] = {'unit': 'native.T_bark', 'item': 'texture'}
    supplied[foliage.PARENT]['dependencies'] = ['/Game/Japan/Materials/MPC_Wind']
    supplied['/Game/Japan/Materials/MPC_Wind'] = {'unit': 'native.MPC_Wind', 'item': 'collection', 'package': '/Game/Japan/Materials/MPC_Wind'}
    by_id = {unit['id']: unit for unit in foliage.foliage_units(rows, checkout=ROOT, natives=supplied)['units']}
    owner = next(unit['id'].removeprefix('unreal.foliage.finish.') for unit in by_id.values()
                 if unit['id'].startswith('unreal.foliage.finish.Tree') and 'material_Bark' in unit['params']['args']['materials'].values())
    names = {item['name']: item['source']['unit'] for item in by_id['unreal.foliage.finish.' + owner]['inputs']}
    assert {names['native_Japan_Materials_M_Painted'], names['native_Japan_Textures_T_bark'],
            names['native_Japan_Textures_T_white'], names['native_Japan_Materials_MPC_Wind']} == {
        'native.M_Painted', 'native.T_bark', 'native.T_white', 'native.MPC_Wind'}
    crown = {item['name'] for item in by_id['unreal.foliage.crown.' + owner]['inputs']}
    assert crown == {'manifest', 'parent', 'white', 'native_Japan_Materials_MPC_Wind'}
    del supplied['/Game/Japan/Materials/MPC_Wind']
    with pytest.raises(foliage.Unsupported, match='MPC_Wind'):
        foliage.foliage_units(rows, checkout=ROOT, natives=supplied)


def test_missing_shared_native_item_refuses(rows):
    supplied = natives(); del supplied[foliage.WHITE]
    with pytest.raises(foliage.Unsupported, match='T_white'):
        foliage.foliage_units(rows, checkout=ROOT, natives=supplied)


@pytest.mark.parametrize('change', ['missing', 'product', 'optional', 'script', 'format', 'commands', 'manifest', 'duplicate'])
def test_wrong_source_shape_refuses(rows, change):
    selected = deepcopy(rows)
    index = next(i for i, row in enumerate(selected) if row['id'] == 'world.foliage.export.Grass_A_LOD1')
    row = selected[index]
    if change == 'missing': del selected[index]
    elif change == 'product': row['products'][0]['paths'] = ['build/yorimichi/exports/other']
    elif change == 'optional': row['products'][0]['optional_paths'] = ['x.fbx']
    elif change == 'script': row['commands'][0]['script'] = {'path': 'other.py'}
    elif change == 'format': row['commands'][0]['args'][-1] = '.glb'
    elif change == 'commands': row['commands'].append(deepcopy(row['commands'][0]))
    elif change == 'manifest':
        next(r for r in selected if r['id'] == 'world.foliage.Grass_A')['products'][0]['id'] = 'other'
    elif change == 'duplicate': selected.append(deepcopy(row))
    with pytest.raises(foliage.Unsupported):
        foliage.foliage_units(selected, checkout=ROOT, natives=natives())


def test_construction_never_scans_generated_content_or_mutates_rows(rows, monkeypatch):
    before = deepcopy(rows)
    original = Path.rglob
    def scan(path, pattern):
        assert path == ROOT / PLUGIN / 'Source'
        return original(path, pattern)
    def forbidden(*_args, **_kwargs):
        raise AssertionError('generated folder scan')
    monkeypatch.setattr(Path, 'rglob', scan)
    monkeypatch.setattr(Path, 'glob', forbidden)
    monkeypatch.setattr(Path, 'iterdir', forbidden)
    assert len(build(rows)['units']) == 112
    assert rows == before
