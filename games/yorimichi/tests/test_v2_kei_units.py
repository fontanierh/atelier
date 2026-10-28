"""Kei followers on the existing vehicle_kei export children, the sole M_Village owner, and the finish body."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_geometry_templates as geometry_templates  # noqa: E402
import v2_kei_units as kei  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402

spec = importlib.util.spec_from_file_location('kei_finish_v2', GAME / 'world/kei_finish_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
CARS = ['SM_Kei_Microvan', 'SM_Kei_Pickup', 'SM_Kei_Retro', 'SM_Kei_Wagon']


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('kei_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['kei_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [*recipe._load_helper_module('kei_atomic_recipe', GAME / 'vehicle_atomic_build.py').steps(context, 'kei'),
             *(step for step in recipe.steps(context) if step.name == 'unreal.kei')]
    rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    return rows, geometry_templates.geometry_templates(rows, checkout=ROOT)


def instantiate(follower, piece, export, previous):
    """The controller's $piece/$export/$previous substitution (native_chains.rs)."""
    text = json.dumps(follower['unit']).replace('$piece', piece).replace('$export', export).replace('$previous', previous)
    assert '$' not in text
    return json.loads(text)


def test_roster_is_the_committed_vehicle_sources_kei_family():
    assert kei.cars(ROOT) == CARS


def test_each_export_child_gains_raw_then_finish_on_village(actual):
    rows, geometry = actual
    result = kei.attach_followers(geometry, rows=rows, checkout=ROOT)
    assert all('followers' not in t for t in geometry['templates'])
    templates = {t['unit_prefix']: t for t in result['geometry']['templates']}
    assert sorted(p.rsplit('.', 1)[1] for p in templates if p.startswith('world.vehicle_kei.export.')) == CARS
    template = templates['world.vehicle_kei.export.SM_Kei_Retro']
    raw, finish = (instantiate(f, 'SM_Kei_Retro', 'world.vehicle_kei.export.SM_Kei_Retro.SM_Kei_Retro',
                               'unreal.kei.raw.SM_Kei_Retro') for f in template['followers'])
    assert raw['inputs'] == [{'role': 'content', 'name': 'source',
                              'source': {'kind': 'item', 'unit': 'world.vehicle_kei.export.SM_Kei_Retro.SM_Kei_Retro', 'item': 'asset'}}]
    assert raw['params']['fbx'] == kei.FBX and raw['params']['settings'] == kei.SETTINGS
    assert raw['outputs'][0]['destination'] == 'store' and raw['outputs'][0]['logical_path'] == '/Game/_Raw/Kei/SM_Kei_Retro'
    assert all('install_path' not in f for f in raw['outputs'][0]['files'])
    assert [i['source'] for i in finish['inputs']] == [
        {'kind': 'item', 'unit': 'unreal.kei.raw.SM_Kei_Retro', 'item': 'raw_static_mesh'},
        {'kind': 'item', 'unit': 'world.vehicle_kei.export.SM_Kei_Retro.SM_Kei_Retro', 'item': 'asset'},
        {'kind': 'item', 'unit': kei.MATERIAL_UNIT, 'item': 'asset'}]
    assert finish['params']['args'] == {'car': 'SM_Kei_Retro', 'piece': 'SM_Kei_Retro', 'export': 'export', 'material': 'material'}
    assert finish['outputs'][0]['logical_path'] == '/Game/Japan/Assets/SM_Kei_Retro'
    assert finish['outputs'][0]['files'][0]['install_path'] == 'games/yorimichi/unreal/Content/Japan/Assets/SM_Kei_Retro.uasset'
    assert kei.FINISH in finish['code']
    village, = result['units']
    assert village['params']['args'] == {'module': kei.VILLAGE, 'function': 'material', 'arguments': [],
                                         'keyword_arguments': {}, 'expected_package': kei.MATERIAL}
    assert {'games/yorimichi/unreal/Scripts/atmosphere.py', 'games/yorimichi/unreal/Scripts/sea_look.py',
            'games/yorimichi/world/yori.py', kei.AUTHOR, kei.VILLAGE} <= set(village['code'])
    assert result['packages']['/Game/Japan/Assets/SM_Kei_Retro']['dependencies'] == [
        {'unit': kei.MATERIAL_UNIT, 'item': 'asset', 'package': kei.MATERIAL}]
    assert result['aliases'] == {'unreal.kei': (kei.MATERIAL_UNIT, *(f'unreal.kei.{car}' for car in CARS))}


def test_supplied_village_owner_is_reused_not_duplicated(actual):
    rows, geometry = actual
    owner = {'unit': 'unreal.village.owner', 'item': 'material', 'package': kei.MATERIAL}
    result = kei.attach_followers(geometry, rows=rows, checkout=ROOT, natives={'M_Village': owner})
    assert result['units'] == [] and kei.MATERIAL not in result['packages']
    finish = result['geometry']['templates'][0]['followers'][1]['unit']
    assert finish['inputs'][2]['source'] == {'kind': 'item', 'unit': 'unreal.village.owner', 'item': 'material'}
    assert result['aliases']['unreal.kei'] == tuple(f'unreal.kei.{car}' for car in CARS)


@pytest.mark.parametrize('change', ['missing', 'attached', 'format', 'row', 'natives', 'owner'])
def test_missing_or_reshaped_roles_refuse(actual, change):
    rows, geometry = deepcopy(actual[0]), deepcopy(actual[1])
    natives = None
    kei_templates = [t for t in geometry['templates'] if t['unit_prefix'].startswith('world.vehicle_kei.')]
    if change == 'missing': geometry['templates'].remove(kei_templates[0])
    elif change == 'attached': kei_templates[0]['followers'] = [{}]
    elif change == 'format': kei_templates[0]['params'] = {'format': 'glb', 'options': {}}
    elif change == 'row': next(r for r in rows if r['id'] == 'unreal.kei')['needs'] = ['world.kei']
    elif change == 'natives': natives = {'M_Other': {}}
    elif change == 'owner': natives = {'M_Village': {'unit': 'u', 'item': 'asset', 'package': '/Game/Other'}}
    with pytest.raises(Unsupported):
        kei.attach_followers(geometry, rows=rows, checkout=ROOT, natives=natives)


# ---- finish body ----------------------------------------------------------------------------------------------------

class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, name): return self.props[name]


class MaterialInterface(Asset): pass


class StaticMesh(Asset):
    def set_material(self, index, material): self.props.setdefault('materials', {})[index] = material
    def get_material(self, index): return self.props['materials'][index]
    def get_bounding_box(self): return NS(max=NS(x=self.props['max_x']))


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves = {}, []
    def duplicate(source, destination):
        copy = StaticMesh(destination, **assets[source].props); assets[destination] = copy; return copy
    unreal = NS(StaticMesh=StaticMesh, MaterialInterface=MaterialInterface,
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    setup = NS(get_editor_property=lambda name: NS(get_editor_property=lambda name: [object(), object()]))
    assets['/Game/_Raw/Kei/SM_Kei_Retro'] = StaticMesh('/Game/_Raw/Kei/SM_Kei_Retro', max_x=169.95, body_setup=setup)
    assets[kei.MATERIAL] = MaterialInterface(kei.MATERIAL)
    export = tmp_path / 'inputs/export'; export.mkdir(parents=True)
    (export / 'SM_Kei_Retro.fbx').write_bytes(b'fbx')
    receipt = {'schema': 1, 'asset': 'SM_Kei_Retro', 'primary': 'SM_Kei_Retro.fbx', 'triangles': 900,
               'bounds': [[-1.7, -0.7, 0.], [1.7, 0.7, 1.5]], 'sha256': 'x',
               'metadata': {'collision_hulls': 2, 'geometry_sha256': 'y', 'slots': [], 'polygons': 1, 'uv_channels': 1}}
    (export / 'export.json').write_text(json.dumps(receipt))
    return NS(assets=assets, saves=saves, export=export, receipt=receipt)


def job(editor, **change):
    args = {'car': 'SM_Kei_Retro', 'piece': 'SM_Kei_Retro', 'export': 'export', 'material': 'material', **change}
    return NS(inputs={'raw': 'x', 'export': str(editor.export), 'material': 'x'},
              packages={'raw': ['/Game/_Raw/Kei/SM_Kei_Retro'], 'export': [], 'material': [kei.MATERIAL]},
              outputs=['/Game/Japan/Assets/SM_Kei_Retro'],
              params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw',
                      'destination': '/Game/Japan/Assets/SM_Kei_Retro', 'args': args})


def test_finish_binds_village_and_keeps_original_checks(editor):
    mesh = body.run(job(editor))
    assert mesh.path == '/Game/Japan/Assets/SM_Kei_Retro' and mesh.get_material(0) is editor.assets[kei.MATERIAL]
    assert editor.saves == ['/Game/Japan/Assets/SM_Kei_Retro']
    assert 'materials' not in editor.assets['/Game/_Raw/Kei/SM_Kei_Retro'].props


@pytest.mark.parametrize('failure', ['piece', 'scale', 'hulls', 'receipt', 'fresh', 'material', 'extra'])
def test_finish_refuses_differences_from_its_export_child(editor, failure):
    context = job(editor)
    if failure == 'piece': context = job(editor, piece='SM_Kei_Retro_2')
    elif failure == 'scale': editor.assets['/Game/_Raw/Kei/SM_Kei_Retro'].props['max_x'] = 1.7
    elif failure == 'hulls': editor.receipt['metadata']['collision_hulls'] = 3
    elif failure == 'receipt': editor.receipt['asset'] = 'SM_Kei_Wagon'
    elif failure == 'fresh': editor.assets['/Game/Japan/Assets/SM_Kei_Retro'] = StaticMesh('/Game/Japan/Assets/SM_Kei_Retro')
    elif failure == 'material': context.packages['material'] = ['/Game/Japan/Materials/M_Other']
    elif failure == 'extra': context.inputs['other'] = 'x'
    (editor.export / 'export.json').write_text(json.dumps(editor.receipt))
    with pytest.raises(ValueError):
        body.run(context)
