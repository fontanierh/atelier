"""Original Treehouse palette declarations and AST-only material factory/data boundary."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_job import pack_root

ROOT = Path(__file__).resolve().parents[3]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


units = load('games/yorimichi/v2_treehouse_material_units.py', 'treehouse_palette_units')
body = load('games/yorimichi/world/treehouse_materials_v2.py', 'treehouse_palette_body')


def sources():
    return {key: {'unit': 'source.' + key, 'item': 'data', 'file': 'products/0-0.tree.tar',
                  'member': member} for key, member in (
        ('palette', 'textures.json'), ('props', 'props.json'), ('trees', 'trees.json'))}


def supplied():
    return {path: {'unit': 'native.' + path.rsplit('/', 1)[-1], 'item': 'asset', 'package': path}
            for path in ('/Game/SeeThrough/MPC_SeeThrough', '/Game/Japan/Materials/M_Foliage')}


def test_individual_native_owners_preserve_original_palette_props_light_and_canopy():
    result = units.author_units(sources(), supplied(), checkout=ROOT)
    by_id = {unit['id']: unit for unit in result['units']}
    assert len(by_id) == len(result['units'])
    owned = [output['logical_path'] for unit in result['units'] for output in unit['outputs']]
    assert len(set(owned)) == len(owned)
    assert units.MAT + 'M_TreeHouse' in result['packages']
    assert units.MAT + 'MI_TH_trunk' in result['packages']
    assert units.MAT + 'MI_TH_pane' in result['packages']
    assert all(units.MAT + 'MI_TH_P_' + name in result['packages'] for name in ('barrel', 'basket', 'telescope'))
    trunk = by_id['unreal.treehouse.material.MI_TH_trunk']
    assert trunk['params']['args']['data'] == {'slot': 'palette', 'file': 'products/0-0.tree.tar', 'member': 'textures.json'}
    assert '/Game/SeeThrough/MPC_SeeThrough' in trunk['params']['args']['inputs'].values()
    crimson = by_id['unreal.treehouse.texture.finish.T_leaf_crimson']
    assert crimson['params']['properties']['do_scale_mips_for_alpha_coverage'] is True
    bark = by_id['unreal.treehouse.texture.finish.T_TH_bark']
    assert bark['params']['properties']['lod_group'] == {'unreal_enum': 'TextureGroup.TEXTUREGROUP_WORLD'}
    assert bark['params']['properties']['max_texture_size'] == 1024
    raw = by_id['unreal.treehouse.texture.raw.T_TH_bark']
    assert raw['params']['input_roots']['palette'] == {'archive_member': 'products/0-0.tree.tar', 'name': 'palette'}
    assert raw['params']['source_member'] == 'bark.png'
    assert all((ROOT / name).is_file() for unit in result['units'] for name in unit['code'])


def test_palette_completes_geometry_material_roles_without_fake_owners():
    native = load('games/yorimichi/v2_treehouse_native_units.py', 'treehouse_palette_followers')
    result = units.author_units(sources(), supplied(), checkout=ROOT)
    packages = {**supplied(), **result['packages']}
    for slug in native._palette(ROOT):
        assert units.MAT + 'MI_TH_' + slug in packages
    assert units.MAT + 'MI_TH_trunk' in packages


@pytest.mark.parametrize('role', ['palette', 'props', 'trees'])
def test_missing_finished_source_roles_refuse(role):
    values = sources(); del values[role]
    with pytest.raises(ValueError, match='Missing finished Treehouse source'):
        units.author_units(values, supplied(), checkout=ROOT)


def test_original_importer_main_never_executes_when_factories_are_compiled(monkeypatch):
    # Loading the original script would import yori/unreal and run unguarded main.
    # Only definitions/literal constants are compiled; no factory is called here.
    monkeypatch.setitem(sys.modules, 'see_through', NS())
    unreal = NS(EditorAssetLibrary=NS(), MaterialEditingLibrary=NS(),
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS()))
    result = body.factories(unreal)
    assert result['parent'].__code__.co_filename.endswith('import_treehouse.py')
    assert set(result['GLOW']) == {'paper', 'glass', 'noren_cream'}
    assert result['LIGHT'] == {'pane': {'Shape': 1., 'Intensity': .06}}
    assert 'main' not in result and 'trees' not in result and 'yori' not in result


def test_actual_data_root_member_is_digest_checked_and_duplicate_json_refuses(tmp_path):
    origin = tmp_path / 'source'; origin.mkdir()
    (origin / 'textures.json').write_text(json.dumps({'bark': {'gain': 2.}}))
    incoming = tmp_path / 'incoming'; incoming.mkdir()
    archive = incoming / 'palette.tree.tar'; pack_root(origin, archive)
    context = NS(job_dir=str(tmp_path), inputs={'palette': incoming})
    selection = {'slot': 'palette', 'file': archive.name, 'member': 'textures.json'}
    assert body.read_data(context, selection) == {'bark': {'gain': 2.}}
    selection['member'] = 'absent.json'
    with pytest.raises(ValueError): body.read_data(context, selection)
    selection['member'] = 'textures.json'
    (origin / 'textures.json').write_text('{"bark":{"gain":2},"bark":{"gain":3}}')
    other = incoming / 'bad.tree.tar'; pack_root(origin, other)
    selection['file'] = other.name
    with pytest.raises(ValueError, match='Duplicate'): body.read_data(context, selection)


@pytest.mark.parametrize('factory,key,name,glow,room', [
    ('palette', 'paper', 'MI_TH_paper', 3., False),
    ('trunk', 'bark', 'MI_TH_trunk', 0., True),
    ('prop', 'TH_P_barrel', 'MI_TH_P_barrel', .7, False),
])
def test_runtime_uses_actual_metadata_gain_original_glow_and_trunk_roomcut(tmp_path, monkeypatch, factory, key, name, glow, room):
    package = units.MAT + name
    native_parent = units.MAT + 'M_TreeHouse'
    texture = '/Game/Japan/Treehouse/Textures/' + ('T_' + key if factory == 'prop' else 'T_TH_' + key)
    class Asset:
        def __init__(self, path): self.path = path
        def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
    assets = {path: Asset(path) for path in (native_parent, texture)}
    result = Asset(package)
    calls = []
    def instance(actual_name, parent, tex, gain, actual_glow):
        calls.append((actual_name, parent.path, tex.path, gain, actual_glow)); return result
    monkeypatch.setattr(body, 'factories', lambda unreal: {'instance': instance, 'GLOW': {'paper': 3.}})
    monkeypatch.setattr(body, 'read_data', lambda context, selection: {key: {'gain': 1.375, 'glow': .7}})
    unreal = NS(EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: False,
        save_loaded_asset=lambda asset, dirty: asset is result),
        MaterialEditingLibrary=NS(set_material_instance_scalar_parameter_value=lambda obj, k, v: calls.append((k, v)),
                                  update_material_instance=lambda obj: None),
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS()))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    context = NS(params={'args': {'asset': name, 'package': package, 'factory': factory, 'key': key,
        'inputs': {'parent': native_parent, 'texture': texture},
        'data': {'slot': 'metadata', 'file': 'data.tree.tar', 'member': 'data.json'}}, 'settings': []},
        inputs={'parent': 'parent', 'texture': 'texture', 'metadata': 'data'},
        packages={'parent': [native_parent], 'texture': [texture], 'metadata': []}, outputs=[package])
    assert body.run(context) is result
    assert calls[0] == (name, native_parent, texture, 1.375, glow)
    assert (('RoomCut', 0.) in calls) is room


@pytest.mark.parametrize('role,asset,filename', [
    ('palette', 'T_TH_bark', 'bark.png'),
    ('props', 'T_TH_P_barrel', 'TH_P_barrel.png'),
    ('trees', 'T_leaf_crimson', 'T_leaf_crimson.png'),
])
def test_real_root_staging_then_actual_ops_selects_exact_png(tmp_path, role, asset, filename):
    from atelier.build_v2 import unreal_inputs, unreal_ops
    source_refs = sources()
    # A nested metadata location proves selection remains relative to the decoded
    # ROOT, while the ROOT staging name remains a single stable basename.
    source_refs[role]['member'] = 'nested/' + source_refs[role]['member']
    declaration = units.author_units(source_refs, supplied(), checkout=ROOT)
    raw = next(unit for unit in declaration['units'] if unit['id'] == 'unreal.treehouse.texture.raw.' + asset)
    job = tmp_path / 'job'; job.mkdir()
    runtime = job / 'runtime'; runtime.mkdir()
    content = tmp_path / 'Content'; content.mkdir()
    producer = tmp_path / 'producer'; (producer / 'nested').mkdir(parents=True)
    (producer / 'nested' / filename).write_bytes(b'EXACT selected pixels')
    (producer / 'nested/other.png').write_bytes(b'NEIGHBOR pixels')
    (producer / source_refs[role]['member']).write_text('{}')
    incoming = job / 'inputs' / role
    archive = incoming / source_refs[role]['file']; archive.parent.mkdir(parents=True)
    pack_root(producer, archive)
    original = archive.read_bytes()
    staged = unreal_inputs.stage_inputs(job,
        [{'name': role, 'path': 'inputs/' + role, 'identity': {'state': 'digest'}}], content,
        runtime_dir=runtime, root_bindings=raw['params']['input_roots'])
    context = NS(job_dir=str(job), inputs=staged['inputs'], packages=staged['packages'], params=raw['params'])
    selected = Path(unreal_ops._input(context, role))
    assert selected == runtime / 'item-0' / role / 'nested' / filename
    assert selected.is_file() and selected.read_bytes() == b'EXACT selected pixels'
    assert selected != Path(staged['inputs'][role]) and archive.read_bytes() == original
    assert staged['packages'][role] == []  # Data pixels do not issue native package authority.
    context.params = {key: value for key, value in raw['params'].items() if key != 'source_member'}
    with pytest.raises(ValueError): unreal_ops._input(context, role)
    context.params = {**raw['params'], 'source_member': '../outside.png'}
    with pytest.raises(ValueError): unreal_ops._input(context, role)
