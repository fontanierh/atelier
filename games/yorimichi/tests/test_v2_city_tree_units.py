"""unreal.city_tree_lods followers on the actual lower-level templates and the city tree parents, and the bodies."""
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
import v2_city_tree_units as trees  # noqa: E402
import v2_geometry_templates as geometry_templates  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402

spec = importlib.util.spec_from_file_location('city_tree_body', GAME / 'world/city_tree_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
TREES, SIZES = trees.policy(ROOT)
ARCADE = '/Game/Japan/Materials/M_Arcade'
NATIVES = {ARCADE: {'unit': 'unreal.material.M_Arcade', 'item': 'asset', 'package': ARCADE,
                    'dependencies': ['/Game/Japan/Textures/T_white']},
           '/Game/Japan/Textures/T_white': {'unit': 'unreal.texture.white', 'item': 'texture', 'package': '/Game/Japan/Textures/T_white'}}


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('city_tree_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['city_tree_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [*recipe._load_helper_module('city_tree_build', GAME / 'hidamari_tree_build.py').steps(context),
             *(s for s in recipe.steps(context) if s.name == 'unreal.city_tree_lods')]
    names, products = {s.name for s in steps}, {p.name for s in steps for p in s.products}
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = []
        step.reads = [r for r in step.reads if r in products]
    rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    geometry = geometry_templates.geometry_templates(rows, checkout=ROOT)
    # The three city tree parents as v2_city_units leaves them: their FBX child with the city raw and finish.
    model = next(t for t in geometry['templates'] if t['unit_prefix'].startswith('world.city_tree_lods.export.'))
    for parent in TREES:
        template = deepcopy(model)
        template.update(producer=f'world.hidamari.geometry.{parent}', unit_prefix=f'world.hidamari.export.{parent}')
        template['followers'] = [{'unit': {'id': '$export.raw', 'outputs': [{'id': 'raw'}]}, 'staged_inputs': {}},
                                 {'unit': {'id': '$export.finish', 'outputs': [
                                     {'id': 'asset', 'logical_path': trees.SURFACES + '/$piece'}]}, 'staged_inputs': {}}]
        geometry['templates'].append(template)
    return rows, geometry


@pytest.fixture(scope='module')
def declared(actual):
    return trees.attach_followers(actual[1], rows=actual[0], checkout=ROOT, natives=NATIVES)


def test_lower_levels_and_bases_follow_their_own_children(declared):
    templates = {t['unit_prefix']: t for t in declared['geometry']['templates']}
    lod = templates['world.city_tree_lods.export.HD_PlazaTreeGold_LOD2']
    raw, finish = (f['unit'] for f in lod['followers'])
    assert raw['params']['fbx'] == trees.FBX and raw['outputs'][0]['destination'] == 'store'
    assert finish['params']['destination'] == trees.DEST + '/lods/$piece'
    assert {i['name'] for i in finish['inputs']} == {'raw', 'export', 'native_Japan_Materials_M_Arcade', 'native_Japan_Textures_T_white'}
    parent = templates['world.hidamari.export.HD_ArcadeTree']
    assert [f['unit']['id'] for f in parent['followers']] == ['$export.raw', '$export.finish', '$export.tree']
    base = parent['followers'][2]['unit']
    assert base['params']['destination'] == trees.DEST + '/$piece_v4'
    assert {i['name']: i['source'] for i in base['inputs']}['original'] == {'kind': 'item', 'unit': '$previous', 'item': 'asset'}
    lod1 = base['params']['args']['lods']['1']['derived_items']['templates'][0]
    assert lod1['piece'] == {'value': '$piece', 'replace_prefix': {'from': 'HD_ArcadeTree', 'to': 'HD_ArcadeTree_LOD1'}}
    assert lod1['unit_prefix'] == 'world.city_tree_lods.export.HD_ArcadeTree_LOD1' and lod1['follower'] == 1
    assert base['params']['args']['screen_sizes'] == SIZES
    record = declared['units'][0]
    assert len(record['params']['args']['trees']['derived_items']['templates']) == 3
    assert declared['aliases'] == {'unreal.city_tree_lods': (trees.RECORD_UNIT,)}
    assert declared['packages'][trees.REPORT]['unit'] == trees.RECORD_UNIT


@pytest.mark.parametrize('damage', ['row', 'city', 'native', 'lod'])
def test_declaration_drift_refuses(actual, damage):
    rows, geometry, natives = deepcopy(actual[0]), deepcopy(actual[1]), deepcopy(NATIVES)
    if damage == 'row':
        next(r for r in rows if r['id'] == 'unreal.city_tree_lods')['products'].pop()
    elif damage == 'city':
        next(t for t in geometry['templates'] if t['unit_prefix'] == 'world.hidamari.export.HD_PlazaTreeOrange')['followers'].pop()
    elif damage == 'native':
        natives.pop('/Game/Japan/Textures/T_white')
    else:
        geometry['templates'] = [t for t in geometry['templates'] if not t['unit_prefix'].endswith('PlazaTreeGold_LOD1')]
    with pytest.raises(Unsupported):
        trees.attach_followers(geometry, rows=rows, checkout=ROOT, natives=natives)


# ---- bodies ---------------------------------------------------------------------------------------------------------

class V(NS):
    pass


class Mesh:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
    def get_num_lods(self): return self.props.get('lods', 1)
    def set_num_source_models(self, n): self.props['lods'] = n
    def get_num_triangles(self, level): return self.props['triangles'][level]
    def get_num_sections(self, level): return 1
    def get_material(self, index): return self.props.get('material')
    def set_material(self, index, value): self.props['material'] = value
    def get_bounds(self): return self.props['bounds']
    def get_bounding_box(self): return self.props['box']
    @property
    def static_materials(self): return [object()]
class Material(Mesh): pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves = {}, []
    def duplicate(source, target):
        assets[target] = type(assets[source])(target, **deepcopy({k: v for k, v in assets[source].props.items() if k != 'material'}),
                                              material=assets[source].props.get('material')); return assets[target]
    precision = {}
    def settings(mesh, level):
        return NS(get_editor_property=lambda k: precision.get((mesh.path, level), True),
                  set_editor_property=lambda k, v: precision.__setitem__((mesh.path, level), v))
    def set_lod(target, level, source, index, keep):
        target.props['lods'] = max(target.get_num_lods(), level + 1)
        target.props['triangles'] = [*target.props['triangles'][:level], source.props['triangles'][0]]; return level
    meshes = NS(get_lod_build_settings=settings, set_lod_build_settings=lambda m, l, s: None,
                get_simple_collision_count=lambda m: 0, get_convex_collision_count=lambda m: 0, remove_collisions=lambda m: True,
                set_lod_from_static_mesh=set_lod, set_lod_screen_sizes=lambda m, s: m.props.update(sizes=list(s)) or True,
                get_lod_screen_sizes=lambda m: m.props['sizes'], get_lod_material_slot=lambda m, l, s: 0)
    unreal = NS(StaticMesh=Mesh, load_module=lambda n: None, get_editor_subsystem=lambda cls: meshes, StaticMeshEditorSubsystem=object,
                CitySurfaceValidation=NS(collision_vertices=lambda m: json.dumps([[[0, 0, 0]]]),
                                         validate_collision=lambda m, t, h: t == m.props['triangles'][0]),
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    (tmp_path / trees.EMPTY).parent.mkdir(parents=True)
    (tmp_path / trees.EMPTY).write_text('def finish_empty_collision(mesh, tile, editor):\n    mesh.props["emptied"] = tile["name"]\n')
    assets[ARCADE] = Material(ARCADE)
    return NS(assets=assets, saves=saves, root=tmp_path)


def stage(editor, name, value, file):
    path = editor.root / name; path.mkdir(exist_ok=True)
    (path / file).write_text(json.dumps(value))
    return str(path)


def receipt(name, triangles, bounds=([0, 0, 0], [1, 2, 3])):
    return {'schema': 1, 'asset': name, 'primary': name + '.fbx', 'triangles': triangles, 'bounds': list(bounds)}


def lod_context(editor, piece, level, triangles):
    raw = '/Game/_Raw/CityTrees/' + piece
    editor.assets[raw] = Mesh(raw, triangles=[triangles], box=V(min=V(x=0, y=-200, z=0), max=V(x=100, y=0, z=300)),
                              bounds=V(sphere_radius=180., origin=V(x=0, y=0, z=0), box_extent=V(x=1, y=1, z=1)))
    destination = f'{trees.DEST}/lods/{piece}'
    return NS(job_dir=str(editor.root), outputs=[destination],
              inputs={'raw': 'x', 'export': stage(editor, 'export_' + piece, receipt(piece, triangles), 'export.json'), 'material': 'x'},
              packages={'raw': [raw], 'export': [], 'material': [ARCADE]},
              params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': destination,
                      'args': {'action': 'lod', 'parent': 'HD_ArcadeTree', 'level': level, 'piece': piece,
                               'export': 'export', 'material': 'material'}})


def test_lower_level_is_the_original_source_check(editor):
    source = body.run(lod_context(editor, 'HD_ArcadeTree_LOD1_cell_0_1', 1, 400))
    assert source.props['material'] is editor.assets[ARCADE] and source.props['emptied'] == 'HD_ArcadeTree_LOD1_cell_0_1'
    context = lod_context(editor, 'HD_ArcadeTree_LOD2_cell_0_1', 2, 90)
    editor.assets['/Game/_Raw/CityTrees/HD_ArcadeTree_LOD2_cell_0_1'].props['box'] = V(min=V(x=0, y=-200, z=0), max=V(x=100, y=0, z=301))
    with pytest.raises(ValueError, match='bounds'):
        body.run(context)


def base_context(editor, piece, siblings):
    original = f'{trees.SURFACES}/{piece}'
    editor.assets[original] = Mesh(original, triangles=[1200], allow_cpu_access=True, material=editor.assets[ARCADE],
                                   bounds=V(sphere_radius=200., origin=V(x=0, y=0, z=0), box_extent=V(x=1, y=1, z=1)))
    for level, name in siblings.items():
        editor.assets[f'{trees.DEST}/lods/{name}'] = Mesh(f'{trees.DEST}/lods/{name}', triangles=[400 // level],
                                                          bounds=V(sphere_radius=190.))
    destination = f'{trees.DEST}/{piece}_v4'
    inputs = {'original': 'x', 'export': stage(editor, 'export', receipt(piece, 1200), 'export.json'),
              'parent': stage(editor, 'parent', {'parent': 'HD_ArcadeTree', 'source_collision_hulls': 0,
                                                 'source_material_slots': ['Palette']}, 'plan.json'), 'material': 'x'}
    packages = {'original': [original], 'export': [], 'parent': [], 'material': [ARCADE]}
    lods = {}
    for level, name in siblings.items():
        inputs[f'l{level}'] = 'x'; packages[f'l{level}'] = [f'{trees.DEST}/lods/{name}']
        lods[str(level)] = {'derived_items': {'root': 'r', 'members': [{'piece': name, 'slot': f'l{level}', 'root': 'r'}]}}
    return NS(job_dir=str(editor.root), outputs=[destination], inputs=inputs, packages=packages,
              params={'op': 'finish', 'kind': 'static_mesh', 'source': 'original', 'destination': destination,
                      'args': {'action': 'base', 'parent': 'HD_ArcadeTree', 'piece': piece, 'export': 'export', 'facts': 'parent',
                               'material': 'material', 'screen_sizes': SIZES, 'lods': lods}})


def test_base_duplicates_its_original_with_its_own_two_siblings(editor):
    piece = 'HD_ArcadeTree_cell_0_1'
    target = body.run(base_context(editor, piece, {1: 'HD_ArcadeTree_LOD1_cell_0_1', 2: 'HD_ArcadeTree_LOD2_cell_0_1'}))
    assert target.path == f'{trees.DEST}/{piece}_v4' and target.props['triangles'] == [1200, 400, 200]
    assert target.props['sizes'] == SIZES and target.props['lod_for_collision'] == 0
    assert editor.saves == [target.path] and editor.assets[f'{trees.SURFACES}/{piece}'].get_num_lods() == 1
    with pytest.raises(ValueError, match='sibling'):
        body.run(base_context(editor, 'HD_ArcadeTree_cell_1_1', {1: 'HD_ArcadeTree_LOD1_cell_0_1', 2: 'HD_ArcadeTree_LOD2_cell_1_1'}))


def test_record_is_the_original_report(editor):
    for name in ('HD_ArcadeTree_cell_0_1', 'HD_PlazaTreeGold_cell_2_0'):
        editor.assets[f'{trees.DEST}/{name}_v4'] = Mesh(f'{trees.DEST}/{name}_v4', triangles=[900, 300, 90])
    members = [{'piece': n, 'slot': f's{i}', 'root': 'r'} for i, n in enumerate(('HD_ArcadeTree_cell_0_1', 'HD_PlazaTreeGold_cell_2_0'))]
    context = NS(job_dir=str(editor.root), outputs=[], data_outputs=(body.RECORD,), inputs={'s0': 'x', 's1': 'x'},
                 packages={'s0': [f'{trees.DEST}/HD_ArcadeTree_cell_0_1_v4'], 's1': [f'{trees.DEST}/HD_PlazaTreeGold_cell_2_0_v4']},
                 params={'args': {'action': 'record', 'screen_sizes': SIZES, 'trees': {'derived_items': {'root': 'r', 'members': members}}},
                         'settings': []})
    value = body.run(context)[body.RECORD]
    assert value['complete'] is True and value['pieces']['HD_PlazaTreeGold_cell_2_0']['triangles'] == [900, 300, 90]
    assert value['pieces']['HD_ArcadeTree_cell_0_1']['original'] == f'{trees.SURFACES}/HD_ArcadeTree_cell_0_1.HD_ArcadeTree_cell_0_1'
