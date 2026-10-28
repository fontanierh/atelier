"""Static and actual-template native outputs join the same source-cook/verification/package chain."""
from copy import deepcopy
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('v2_cook_pipeline_test', ROOT / 'games/yorimichi/v2_cook_pipeline.py')
pipeline = importlib.util.module_from_spec(spec); spec.loader.exec_module(pipeline)


def output(item, package, cls):
    return {'id': item, 'logical_path': package, 'class': cls, 'destination': 'store',
            'files': [{'path': 'content/Game/' + package.removeprefix('/Game/') + '.uasset', 'required': True}]}


def native():
    material = {'id': 'material', 'op': {'kind': 'unreal.author', 'version': '1'},
        'inputs': [], 'params': {'args': {}, 'settings': []}, 'outputs': [output('asset', '/Game/M', 'Material')]}
    raw = {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'},
        'inputs': [], 'params': {}, 'outputs': [output('raw', '/Game/_Raw/$piece', 'RawStaticMesh'),
                                          output('raw_skeleton', '/Game/_Raw/$piece/Skeleton', 'Skeleton')]}
    finish = {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
        'inputs': [{'role': 'content', 'name': 'raw', 'source': {'kind': 'item', 'unit': '$previous', 'item': 'raw'}},
                   {'role': 'content', 'name': 'material', 'source': {'kind': 'item', 'unit': 'material', 'item': 'asset'}}],
        'params': {}, 'outputs': [output('mesh', '/Game/Meshes/$piece', 'StaticMesh')]}
    template = {'producer': 'geometry', 'group': 'geometry', 'unit_prefix': 'export',
                'followers': [{'unit': raw, 'staged_inputs': {}}, {'unit': finish, 'staged_inputs': {}}]}
    return {'units': [material], 'staged_inputs': {'material': {}}, 'content_slots': {}, 'packages': {},
            'aliases': {}, 'geometry': {'templates': [template], 'groups': {}}}


def context():
    return ({'unit': 'compiler', 'item': 'editor', 'file': 'editor.tree.tar'},
            {'unit': 'game', 'item': 'game', 'file': 'game.mac.zip'},
            {'HorseRacing': {'unit': 'compiler', 'item': 'horse', 'file': 'horse.tree.tar',
                'descriptor_path': 'games/yorimichi/unreal/Plugins/HorseRacing/HorseRacing.uplugin'}}, [])


def test_each_actual_native_follower_gets_its_own_cook_and_external_verified_item(monkeypatch):
    monkeypatch.setattr(pipeline, '_context', lambda *args: context())
    original = native()
    result = pipeline.attach(deepcopy(original), [], checkout=ROOT)
    followers = result['geometry']['templates'][0]['followers']
    assert len(original['geometry']['templates'][0]['followers']) == 2
    source, sealed = [row['unit'] for row in followers[-2:]]
    assert source['op']['kind'] == 'unreal.cook.produce'
    assert source['params']['packages'] == ['/Game/Meshes/$piece']
    assert source['params']['record_outputs'].keys() == {'/Game/Meshes/$piece'}
    assert {'$export.finish', 'material'} <= {row['source'].get('unit') for row in source['inputs']}
    assert source['params']['recipe']['native_inputs']['slots']
    assert pipeline.PATHS in source['code']
    assert sealed['inputs'][0]['source']['unit'] == source['id']
    assert sealed['outputs'][0]['class'] == 'CookedPackage' and sealed['outputs'][0]['destination'] == 'external'
    package = next(unit for unit in result['units'] if unit['op']['kind'] == 'unreal.package')
    dynamic = package['params']['recipe']['cooked_members'][0]['derived_items']['templates'][0]
    assert dynamic == {'producer': 'geometry', 'group': 'geometry', 'unit_prefix': 'export', 'follower': 3, 'item': 'package'}
    assert result['aliases']['unreal.package'] == ('unreal.package.download',)
    assert not any(item['class'].startswith('Raw') for unit in result['units']
                   if unit['op']['kind'] == 'unreal.cook.produce' for item in unit['outputs'])


def test_unknown_selected_family_prevents_a_partial_roster_becoming_the_full_alias(monkeypatch):
    monkeypatch.setattr(pipeline, '_context', lambda *args: context())
    row = {'id': 'unreal.unknown', 'commands': [{'kind': 'UnrealScript'}]}
    result = pipeline.attach(native(), [row], checkout=ROOT)
    assert result['cook_gaps'] == ['unreal.unknown']
    assert 'unreal.package' not in result['aliases'] and 'unreal.cook' not in result['aliases']


def test_replaced_runtime_and_added_registration_rows_survive_the_global_data_join():
    base = 'games/yorimichi/unreal/Content/Data/'
    original = {'id': 'data.stage', 'outputs': [base + 'obsolete.json'], 'products': []}
    runtime = {'id': 'data.stage', 'outputs': [base + 'world.json'], 'products': []}
    registration = {'id': 'character.registration', 'outputs': [base + 'cairo/character.json'], 'products': []}
    value = {'aliases': {'data.stage': ('data.stage',)}, 'rows': [runtime, registration], 'units': [
        {'id': 'horses.record', 'outputs': [{'id': 'roster', 'files': [
            {'path': 'data/roster.json', 'install_path': base + 'horses/roster.json'}]}]}]}
    data = {row['path']: row for row in pipeline._data_context([original], value)}
    assert set(data) == {base + 'world.json', base + 'cairo/character.json', base + 'horses/roster.json'}
    assert data[base + 'world.json']['unit'] == 'data.stage'
    assert data[base + 'world.json']['file'] == 'outputs/0.tree.tar'
    assert data[base + 'cairo/character.json']['unit'] == 'character.registration'
    assert data[base + 'horses/roster.json']['file'] == 'data/roster.json'


def test_explicit_network_identity_root_reaches_global_cook_without_ambient_scan():
    path = 'games/yorimichi/unreal/Content/Data/Network/session.json'
    reference = {'unit': 'data.network', 'item': 'session', 'file': 'session.tree.tar', 'path': path}
    native = {'aliases': {'data.network': ('data.network',)}, 'rows': [], 'units': [], 'runtime_data': [reference]}
    original = {'id': 'data.network', 'outputs': [path], 'products': []}
    assert pipeline._data_context([original], native) == [reference]
