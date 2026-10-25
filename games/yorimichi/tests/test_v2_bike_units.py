"""Bike followers on the existing vehicle_bike export children, the sole M_Bike owner, the record, and the bodies."""
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
import v2_bike_units as bike  # noqa: E402
import v2_geometry_templates as geometry_templates  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402

spec = importlib.util.spec_from_file_location('bike_finish_v2', GAME / 'world/bike_finish_v2.py')
body = importlib.util.module_from_spec(spec); spec.loader.exec_module(body)
STEERING = ['BK_Steer_BasketFoot', 'BK_Steer_BasketRim', 'BK_Steer_BasketShell', 'BK_Steer_Core']


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('bike_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['bike_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [*recipe._load_helper_module('bike_atomic_recipe', GAME / 'vehicle_atomic_build.py').steps(context, 'bike'),
             *(step for step in recipe.steps(context) if step.name == 'unreal.bike')]
    names = {s.name for s in steps}
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = []
    rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    return rows, geometry_templates.geometry_templates(rows, checkout=ROOT)


def instantiate(follower, piece, export, previous):
    """The controller's $piece/$export/$previous substitution (native_chains.rs)."""
    text = json.dumps(follower['unit']).replace('$piece', piece).replace('$export', export).replace('$previous', previous)
    assert '$' not in text
    return json.loads(text)


def test_roster_is_the_committed_bike_parts():
    parts, steering = bike.roster(ROOT)
    assert len(parts) == 11 and sorted(steering) == STEERING and parts[-4:] == steering


def test_each_export_child_gains_raw_then_finish_on_m_bike(actual):
    rows, geometry = actual
    result = bike.attach_followers(geometry, rows=rows, checkout=ROOT)
    assert all('followers' not in t for t in geometry['templates'])
    templates = {t['unit_prefix']: t for t in result['geometry']['templates'] if t['unit_prefix'].startswith('world.vehicle_bike.export.')}
    assert len(templates) == 11
    frame = templates['world.vehicle_bike.export.BK_WheelFront']
    raw, finish = (instantiate(f, 'BK_WheelFront', 'world.vehicle_bike.export.BK_WheelFront.BK_WheelFront',
                               'unreal.bike.raw.BK_WheelFront') for f in frame['followers'])
    assert raw['params']['fbx'] == bike.FBX and raw['params']['settings'] == bike.SETTINGS
    assert raw['outputs'][0]['destination'] == 'store' and raw['outputs'][0]['logical_path'] == '/Game/_Raw/Bike/BK_WheelFront'
    assert {i['name']: i['source'] for i in finish['inputs']} == {
        'raw': {'kind': 'item', 'unit': 'unreal.bike.raw.BK_WheelFront', 'item': 'raw_static_mesh'},
        'export': {'kind': 'item', 'unit': 'world.vehicle_bike.export.BK_WheelFront.BK_WheelFront', 'item': 'asset'},
        'report': {'kind': 'item', 'unit': 'world.vehicle_bike.geometry.BK_WheelFront', 'item': 'product1'},
        'material': {'kind': 'item', 'unit': bike.MATERIAL_UNIT, 'item': 'asset'}}
    assert finish['params']['input_roots'] == {'report': {'archive_member': 'products/1-0.tree.tar', 'name': 'report.json'}}
    assert 'peers' not in finish['params']['args'] and finish['outputs'][0]['logical_path'] == '/Game/Japan/Assets/BK_WheelFront'
    core = templates['world.vehicle_bike.export.BK_Steer_Core']['followers']
    assert [f['unit']['id'] for f in core] == ['unreal.bike.raw.BK_Steer_Core']
    units = {u['id']: u for u in result['units']}
    assert units[bike.MATERIAL_UNIT]['params']['args']['module'] == bike.SOURCE
    joint = units[bike.STEERING_UNIT]
    assert sorted(o['id'] for o in joint['outputs']) == STEERING
    assert all(result['packages']['/Game/Japan/Assets/' + k] == {'unit': bike.STEERING_UNIT, 'item': k,
               'package': '/Game/Japan/Assets/' + k, 'dependencies': [{'unit': bike.MATERIAL_UNIT, 'item': 'asset',
                                                                      'package': bike.MATERIAL}]} for k in STEERING)
    raws, exports = (joint['params']['args'][k]['derived_items']['templates'] for k in ('raws', 'exports'))
    assert sorted(t['unit_prefix'].rsplit('.', 1)[1] for t in raws) == STEERING
    assert all(t['follower'] == 0 and t['item'] == 'raw_static_mesh' for t in raws)
    assert all('follower' not in t and t['item'] == 'asset' for t in exports)
    record = units[bike.RECORD_UNIT]
    assert len(record['params']['args']['parts']['derived_items']['templates']) == 7
    assert sorted(record['params']['args']['steering']) == STEERING
    assert record['outputs'][0]['destination'] == 'store' and result['packages'][bike.REPORT_OUT]['unit'] == bike.RECORD_UNIT
    assert sorted(result['aliases']['unreal.bike']) == sorted([bike.MATERIAL_UNIT, bike.STEERING_UNIT, bike.RECORD_UNIT,
                                                               *(f'unreal.bike.{k}' for k in bike.roster(ROOT)[0][:7])])
    assert all(prefix in result['geometry']['module_requirements'] for prefix in templates)


def test_supplied_m_bike_replaces_the_author(actual):
    rows, geometry = actual
    supplied = {'unit': 'unreal.supplied', 'item': 'asset', 'package': bike.MATERIAL}
    result = bike.attach_followers(geometry, rows=rows, checkout=ROOT, natives={'M_Bike': supplied})
    assert [u['id'] for u in result['units']] == [bike.STEERING_UNIT, bike.RECORD_UNIT] and bike.MATERIAL not in result['packages']
    assert result['packages']['/Game/Japan/Assets/BK_Frame']['dependencies'] == [supplied]
    with pytest.raises(Unsupported):
        bike.attach_followers(geometry, rows=rows, checkout=ROOT, natives={'M_Village': supplied})


@pytest.mark.parametrize('damage', ['command', 'product', 'report', 'template'])
def test_declaration_drift_refuses(actual, damage):
    rows, geometry = deepcopy(actual[0]), deepcopy(actual[1])
    found = {r['id']: r for r in rows}
    if damage == 'command':
        found['unreal.bike']['commands'][0]['marker'] = 'OTHER'
    elif damage == 'product':
        found['unreal.bike']['products'][0]['paths'].pop()
    elif damage == 'report':
        found['world.vehicle_bike.geometry.BK_Crank']['products'].pop()
    else:
        geometry['templates'] = [t for t in geometry['templates'] if not t['unit_prefix'].endswith('BK_Pedal')]
    with pytest.raises(Unsupported):
        bike.attach_followers(geometry, rows=rows, checkout=ROOT)


# ---- bodies ---------------------------------------------------------------------------------------------------------

class V(NS):
    pass


class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_name(self): return self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Material(Asset): pass
class Mesh(Asset):
    def get_material(self, i): return self.props['material']
    def set_material(self, i, m): self.props['material'] = m
    def get_num_lods(self): return 1
    def get_num_triangles(self, lod): return self.props['triangles']
    def get_bounding_box(self): return self.props['bounds']


REPORT = {'triangles': 120, 'vertices': 80, 'min': [-.1, -.2, 0.], 'max': [.3, .4, .5]}


@pytest.fixture
def editor(tmp_path, monkeypatch):
    assets, saves, groups = {}, [], []
    def duplicate(source, target):
        assets[target] = type(assets[source])(target, **assets[source].props); return assets[target]
    slot = NS(get_editor_property=lambda k: 'BikePalette')
    settings = NS(get_editor_property=lambda k: False)
    component = NS(validate_part=lambda m, t: t == m.props['triangles'],
                   prepare_steering_bounds=lambda parts: groups.append([p.get_name() for p in parts]) or len(parts) == 4,
                   steering_bounds=lambda parts: json.dumps({'origin': [0, 0, 0], 'extent': [1, 1, 1], 'sphere_radius': 2}))
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, BikeMeshComponent=component, StaticMeshEditorSubsystem=object,
                load_module=lambda name: None,
                get_editor_subsystem=lambda cls: NS(get_num_uv_channels=lambda m, l: 1, get_lod_build_settings=lambda m, l: settings),
                EditorAssetLibrary=NS(load_asset=lambda p: assets.get(p.split('.', 1)[0]), does_asset_exist=lambda p: p in assets,
                                      duplicate_asset=duplicate, save_loaded_asset=lambda a, d=True: saves.append(a.path) or True))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    bounds = V(min=V(x=-10., y=-40., z=0.), max=V(x=30., y=20., z=50.))
    raw_props = dict(material=None, allow_cpu_access=False, static_materials=[slot], triangles=120, bounds=bounds)
    for key in ['BK_WheelFront', *STEERING]:
        assets['/Game/_Raw/Bike/' + key] = Mesh('/Game/_Raw/Bike/' + key, **raw_props)
    assets[bike.MATERIAL] = Material(bike.MATERIAL)
    return NS(assets=assets, saves=saves, groups=groups, root=tmp_path)


def stage(editor, name, value, file):
    path = editor.root / name; path.mkdir(exist_ok=True)
    (path / file).write_text(json.dumps(value))
    return str(path)


def receipt(key):
    return {'schema': 1, 'asset': key, 'primary': key + '.fbx', 'triangles': 120, 'bounds': [[0, 0, 0], [1, 1, 1]],
            'metadata': {'slots': ['BikePalette'], 'collision_hulls': 0, 'uv_channels': ['UVMap']}}


def part_context(editor, key, *, report=REPORT):
    inputs = {'raw': 'x', 'export': stage(editor, 'export', receipt(key), 'export.json'),
              'report': stage(editor, 'report', report, 'report.json'), 'material': 'x'}
    packages = {'raw': ['/Game/_Raw/Bike/' + key], 'export': [], 'report': [], 'material': [bike.MATERIAL]}
    args = {'action': 'part', 'part': key, 'piece': key, 'export': 'export', 'report': 'report', 'material': 'material'}
    return NS(job_dir=str(editor.root), outputs=['/Game/Japan/Assets/' + key], inputs=inputs, packages=packages,
              params={'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': '/Game/Japan/Assets/' + key,
                      'args': args, 'settings': []})


def steering_context(editor, *, group=STEERING, report=REPORT):
    inputs, packages = {'material': 'x'}, {'material': [bike.MATERIAL]}
    raws, exports, reports = [], [], {}
    for i, key in enumerate(group):
        raws.append({'piece': key, 'slot': f'r{i}', 'root': 'r'}); exports.append({'piece': key, 'slot': f'e{i}', 'root': 'e'})
        inputs[f'r{i}'] = 'x'; packages[f'r{i}'] = ['/Game/_Raw/Bike/' + key]
        inputs[f'e{i}'] = stage(editor, f'e{i}', receipt(key), 'export.json'); packages[f'e{i}'] = []
        inputs['report_' + key] = stage(editor, 'report_' + key, report, 'report.json'); packages['report_' + key] = []
        reports[key] = 'report_' + key
    return NS(job_dir=str(editor.root), outputs=['/Game/Japan/Assets/' + k for k in STEERING], inputs=inputs, packages=packages,
              params={'args': {'action': 'steering', 'material': 'material', 'reports': reports,
                               'raws': {'derived_items': {'root': 'r', 'members': raws}},
                               'exports': {'derived_items': {'root': 'e', 'members': exports}}}, 'settings': []})


def test_wheel_finish_is_the_original_with_its_own_report(editor):
    mesh = body.run(part_context(editor, 'BK_WheelFront'))
    assert mesh.props['allow_cpu_access'] is True and mesh.props['material'] is editor.assets[bike.MATERIAL]
    assert editor.saves == ['/Game/Japan/Assets/BK_WheelFront'] and not editor.groups


def test_finish_refuses_a_report_that_differs_or_a_steering_part(editor):
    with pytest.raises(ValueError, match='axis/scale'):
        body.run(part_context(editor, 'BK_WheelFront', report={**REPORT, 'max': [.3, .4, .6]}))
    with pytest.raises(ValueError, match='ordinary'):
        body.run(part_context(editor, 'BK_Steer_Core'))
    with pytest.raises(ValueError, match='attributes'):
        body.run(steering_context(editor, report={**REPORT, 'extra': 1}))


def test_steering_owner_finishes_all_four_then_persists_group_bounds(editor):
    group = body.run(steering_context(editor))
    assert [m.path for m in group] == ['/Game/Japan/Assets/' + k for k in STEERING]
    assert editor.groups == [STEERING] and editor.saves == ['/Game/Japan/Assets/' + k for k in STEERING]
    assert not any(p.startswith('/Game/_Raw/') for p in editor.saves)
    with pytest.raises(ValueError, match='four-part'):
        body.run(steering_context(editor, group=STEERING[:3]))


def test_record_is_the_original_report(editor):
    parts = ['BK_WheelFront', *STEERING]
    inputs, packages, members, reports, steering = {}, {}, [], {}, {}
    for i, key in enumerate(parts):
        editor.assets['/Game/Japan/Assets/' + key] = Mesh('/Game/Japan/Assets/' + key, triangles=118,
                                                         bounds=V(min=V(x=0, y=0, z=0), max=V(x=1, y=2, z=3)))
        if key in STEERING:
            steering[key] = f'd{i}'
        else:
            members.append({'piece': key, 'slot': f'd{i}', 'root': f'r/{key}'})
        inputs[f'd{i}'] = 'x'; packages[f'd{i}'] = ['/Game/Japan/Assets/' + key]
        reports[key] = f'report_{key}'
        inputs[f'report_{key}'] = stage(editor, f'report_{key}', REPORT, 'report.json'); packages[f'report_{key}'] = []
    context = NS(job_dir=str(editor.root), outputs=[], data_outputs=(body.RECORD,), inputs=inputs, packages=packages,
                 params={'args': {'action': 'record', 'reports': reports,
                                  'parts': {'derived_items': {'root': 'r', 'members': members}}, 'steering': steering},
                         'settings': []})
    value = body.run(context)[body.RECORD]
    assert value['complete'] is True and value['retired'] == [] and value['steering_bounds']['sphere_radius'] == 2
    assert value['parts']['BK_Steer_Core'] == {'source_triangles': 120, 'triangles': 118, 'min': [0, 0, 0], 'max': [1, 2, 3]}
