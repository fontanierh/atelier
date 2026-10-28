"""Dependency lowering must preserve producer authority before any runtime exists."""
from copy import deepcopy

import pytest

from atelier.build_v2.recipe_compiler import Unsupported, compile_rows


def row(name, *, inputs=(), products=(), reads=(), outputs=()):
    return {'id': name, 'commands': [{'kind': 'python', 'script': {'path': 'ops/main.py'},
                                    'args': [], 'env': []}],
            'code': ['ops/main.py'], 'inputs': list(inputs), 'reads': list(reads),
            'needs': [], 'after': [], 'products': list(products), 'outputs': list(outputs),
            'verify': None, 'replan': False}


def test_generated_file_is_a_product_edge_without_reading_existing_output(tmp_path):
    producer = row('producer', products=[{'id': 'terrain', 'paths': ['build/game/terrain'],
                                        'optional_paths': []}])
    consumer = row('consumer', inputs=[{'path': 'build/game/terrain/final.npz', 'optional': False}],
                   outputs=['build/game/height.json'])
    marker = compile_rows([producer, consumer], project='game', targets=['consumer'])
    request = marker.request(tmp_path)
    unit = request['declaration']['units'][1]
    assert len(unit['inputs']) == 1 and unit['inputs'][0]['whole']
    assert unit['inputs'][0]['source'] == {'kind': 'item', 'unit': 'producer', 'item': 'product0'}
    assert unit['params']['recipe']['paths'] == {
        'build/game/terrain': 'inputs/item0/products/0-0.tree.tar'}
    assert not list(tmp_path.iterdir())


def test_named_product_bytes_are_explicit_content_even_without_needs(tmp_path):
    producer = row('producer', products=[{'id': 'terrain', 'paths': ['build/game/terrain'],
                                        'optional_paths': []}])
    consumer = row('consumer', reads=[{'producer': 'producer', 'product': 'terrain',
                                     'paths': ['build/game/terrain']}], outputs=['build/game/result.json'])
    result = compile_rows([producer, consumer], project='game', targets=['consumer']).request(tmp_path)
    assert result['declaration']['units'][1]['inputs'][0]['source']['kind'] == 'item'
    altered = deepcopy(consumer)
    altered['reads'][0]['producer'] = 'foreign'
    with pytest.raises(Unsupported, match='owning declaration'):
        compile_rows([producer, altered], project='game', targets=['consumer'])


def test_authored_recipe_whole_captures_keep_identity_and_selected_scope(tmp_path):
    source = row('source', products=[{'id': 'source', 'paths': ['build/game/source'], 'optional_paths': []}])
    incoming = [
        {'role': 'content', 'name': 'whole', 'source': {'kind': 'item', 'unit': 'source', 'item': 'product0'}},
        {'role': 'content', 'name': 'file', 'source': {'kind': 'file', 'path': 'assets/settings.json'}},
        {'role': 'content', 'name': 'field', 'source': {'kind': 'file', 'path': 'assets/settings.json', 'selector': '/value'}},
        {'role': 'content', 'name': 'authored', 'source': {'kind': 'item', 'unit': 'source', 'item': 'product0'},
         'whole': 'The original verifier consumes complete membership.'},
    ]
    native = {'id': 'captured.recipe', 'op': {'kind': 'recipe.python', 'version': '1'},
        'script': 'ops/captured.py', 'code': ['ops/captured.py'], 'inputs': deepcopy(incoming),
        'params': {}, 'outputs': [{'id': 'data', 'class': 'Data', 'logical_path': '/Internal/Captured',
            'destination': 'store', 'files': [{'path': 'data.tree.tar'}]}]}
    result = compile_rows([source], project='game', targets=['captured.recipe'], native={
        'units': [native], 'staged_inputs': {native['id']: {i['name']: 'inputs/' + i['name'] for i in incoming}},
        'content_slots': {i['name']: False for i in incoming}, 'aliases': {}}).request(tmp_path)
    actual = next(unit for unit in result['declaration']['units'] if unit['id'] == native['id'])['inputs']
    assert actual[0]['whole'] and actual[1]['whole']
    assert 'whole' not in actual[2]
    assert actual[3]['whole'] == incoming[3]['whole']
    assert [i['source'] for i in actual] == [i['source'] for i in incoming]
    assert native['inputs'] == incoming  # Compilation does not mutate the author's declarations.


def test_optional_source_remains_explicit_absence_and_never_disappears_from_key(tmp_path):
    unit = row('source', inputs=[{'path': 'assets/settings.json', 'optional': True}],
               outputs=['build/game/data.json'])
    request = compile_rows([unit], project='game', targets=['source']).request(tmp_path)
    assert request['declaration']['units'][0]['inputs'][0]['source'] == {
        'kind': 'file', 'path': 'assets/settings.json', 'optional': True}


def test_unimplemented_native_command_cannot_be_relabelled_python():
    unit = row('native', outputs=['build/game/native.json'])
    unit['commands'] = [{'kind': 'UnrealScript', 'script': {'path': 'ops/main.py'}}]
    with pytest.raises(Unsupported, match='native typed execution adapter'):
        compile_rows([unit], project='game', targets=['native'])


def test_duplicate_or_escaping_ownership_refuses():
    unit = row('source', outputs=['../foreign'])
    with pytest.raises(Unsupported, match='noncanonical'):
        compile_rows([unit], project='game', targets=['source'])
    unit = row('source', outputs=['build/game/data.json'])
    with pytest.raises(Unsupported, match='duplicate recipe unit'):
        compile_rows([unit, unit], project='game', targets=['source'])


def test_native_replacement_alias_keeps_individual_items_and_direct_file_bytes(tmp_path):
    native = {'id': 'native.mesh', 'op': {'kind': 'unreal.finish', 'version': '1'},
              'script': 'ops/finish.py', 'code': ['ops/finish.py'], 'inputs': [], 'params': {},
              'outputs': [{'id': 'asset', 'logical_path': '/Game/Mesh', 'class': 'StaticMesh',
                           'destination': 'checkout', 'files': [{'path': 'content/Game/Mesh.uasset',
                             'install_path': 'games/game/unreal/Content/Mesh.uasset', 'required': True}]}]}
    old = row('old.import', outputs=['games/game/unreal/Content/Mesh.uasset'])
    old['commands'] = [{'kind': 'UnrealScript', 'script': {'path': 'old/import.py'}}]
    consumer = row('consumer', outputs=['build/game/data.json'])
    consumer['needs'] = ['old.import']
    marker = compile_rows([old, consumer], project='game', targets=['consumer'], native={
        'units': [native], 'staged_inputs': {'native.mesh': {}}, 'content_slots': {},
        'aliases': {'old.import': ['native.mesh']}})
    request = marker.request(tmp_path)
    assert request['declaration']['units'][0] == native
    unit = request['declaration']['units'][1]
    assert unit['inputs'][0]['source'] == {'kind': 'item', 'unit': 'native.mesh', 'item': 'asset'}
    assert unit['params']['recipe']['paths'] == {
        'games/game/unreal/Content/Mesh.uasset': 'inputs/item0/content/Game/Mesh.uasset'}
    assert not list(tmp_path.iterdir())
    alias = compile_rows([old], project='game', targets=['old.import'], native={
        'units': [native], 'staged_inputs': {'native.mesh': {}}, 'content_slots': {},
        'aliases': {'old.import': ['native.mesh']}})
    assert alias.request(tmp_path)['targets'] == ['native.mesh']
def test_declared_frontend_directory_gets_fixed_node_role_after_file_lowering(tmp_path):
    frontend = tmp_path / 'editor'
    frontend.mkdir()
    for filename in ('bridge.cjs', 'pieces.cjs', 'terrain.cjs'):
        (frontend / filename).write_text('// declared frontend source')
    unit = row('frontend', inputs=[{'path': 'editor', 'root': 'checkout', 'optional': False}],
               outputs=['build/game/mesh.json'])
    request = compile_rows([unit], project='game', targets=['frontend'], checkout=tmp_path).request(tmp_path)
    lowered = request['declaration']['units'][0]
    assert lowered['params']['recipe']['tools'] == [{'kind': 'node.frontend', 'entry': 'editor/bridge.cjs',
        'sources': ['editor/bridge.cjs', 'editor/pieces.cjs', 'editor/terrain.cjs']}]
    declared = {item['source']['path'] for item in lowered['inputs']}
    assert set(lowered['params']['recipe']['tools'][0]['sources']) <= declared


def test_game_compile_declares_redistributed_files_beside_mac_binary_archive(tmp_path):
    project = tmp_path / 'games/game/unreal/Game.uproject'
    project.parent.mkdir(parents=True); project.write_text('{}')
    source = row('game')
    source['commands'] = [{'kind':'UnrealGame','target':'Game','config':'Development',
                           'products':['Binaries/Mac/library.dylib','Samples/Tools/helper.sh']}]
    marker = compile_rows([source], project='game', targets=['game'], checkout=tmp_path)
    unit = marker.declaration['units'][0]
    assert unit['op']['kind'] == 'unreal.game'
    assert [r['path'] for r in unit['params']['recipe']['outputs']] == [
        'games/game/unreal/Binaries/Mac','games/game/unreal/Samples/Tools/helper.sh']
    assert unit['outputs'][0]['files'] == [{'path':'outputs/0.mac.zip'}]
    assert unit['outputs'][1]['files'] == [{'path':'outputs/1.tree.tar'}]


def test_compiler_preserves_follower_module_requirements_through_ordinary_rows(tmp_path):
    import json
    project = tmp_path / 'games/game/unreal/Game.uproject'
    project.parent.mkdir(parents=True)
    project.write_text(json.dumps({'Modules': [{'Name': 'Game', 'Type': 'Runtime'}]}))
    editor = row('editor', outputs=['games/game/unreal/Binaries/Mac'])
    editor['commands'] = [{'kind': 'UnrealCompile', 'target': 'GameEditor', 'config': 'Development'}]
    follower = {'unit': {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
                         'inputs': [], 'params': {}}, 'staged_inputs': {}}
    native = {'units': [], 'staged_inputs': {}, 'content_slots': {}, 'aliases': {},
              'follower_module_requirements': {'world.example.export.Parent': [{'name': 'Game'}]}}
    marker = compile_rows([editor], project='game', targets=['editor'], checkout=tmp_path,
                          geometry={'groups': {}, 'templates': [
                              {'unit_prefix': 'world.example.export.Parent', 'payload_slot': 'selected_payload',
                               'followers': [follower]}]}, native=native)
    assert marker.content_slots['selected_payload'] is False
    bound = marker.templates[0]['followers'][0]
    assert bound['unit']['params']['native_modules']['editor']['slot'] == 'compiled_editor'
    assert bound['unit']['inputs'][0]['source'] == {'kind': 'item', 'unit': 'editor', 'item': 'output0'}


def replacement_fixture():
    source = row('source', outputs=['build/game/source'])
    old = row('old.import', outputs=['games/game/unreal/Content/Old.uasset'])
    old['commands'] = [{'kind': 'UnrealScript'}]
    old['needs'] = ['unrelated.import']
    unrelated = row('unrelated.import', outputs=['games/game/unreal/Content/Unrelated.uasset'])
    unrelated['commands'] = [{'kind': 'UnrealScript'}]
    unit = {'id': 'replacement', 'op': {'kind': 'recipe.python', 'version': '1'},
            'script': 'ops/main.py', 'code': ['ops/main.py'],
            'inputs': [{'role': 'content', 'name': 'source', 'source': {'kind': 'item', 'unit': 'source', 'item': 'output0'}}],
            'params': {}, 'outputs': [{'id': 'asset', 'logical_path': '/Build/Replaced', 'class': 'Data',
                'destination': 'store', 'files': [{'path': 'result.json', 'required': True}]}]}
    native = {'units': [unit], 'staged_inputs': {'replacement': {'source': 'inputs/source'}},
              'content_slots': {'source': False}, 'aliases': {'old.import': ['replacement']}}
    return [source, old, unrelated], native


def test_replacement_selector_keeps_actual_v2_edges_instead_of_retired_import_prerequisites():
    rows, native = replacement_fixture()
    marker = compile_rows(rows, project='game', targets=['old.import'], native=native)
    assert {unit['id'] for unit in marker.declaration['units']} == {'source', 'replacement'}
    assert marker.selection_targets == ('replacement',)


def test_required_unsupported_producer_still_refuses_replacement_selection():
    rows, native = replacement_fixture()
    rows[0]['commands'] = [{'kind': 'UnrealScript'}]
    with pytest.raises(Unsupported, match='source: UnrealScript'):
        compile_rows(rows, project='game', targets=['old.import'], native=native)


def test_replacement_closure_selects_fixed_native_and_cook_template_followers():
    from atelier.build_v2.recipe_compiler import _replacement_closure
    def unit(name, *dependencies):
        return {'id': name, 'inputs': [{'source': {'kind': 'item', 'unit': owner, 'item': 'asset'}}
                                      for owner in dependencies], 'params': {}}
    units = [unit('source'), unit('package', 'cook.verify')]
    template = {'producer': 'source', 'group': 'geometry', 'unit_prefix': 'export.car',
                'followers': [{'unit': unit('native.car', '$export')},
                              {'unit': unit('cook.source', 'native.car')},
                              {'unit': unit('cook.verify', 'cook.source')}]}
    selected, templates, missing = _replacement_closure(units, [template], ['package'], {}, {}, [])
    assert not missing
    assert selected == {'source', 'package', 'native.car', 'cook.source', 'cook.verify'}
    assert templates == {('source', 'geometry', 'export.car')}
    foreign = unit('package', 'undeclared')
    assert _replacement_closure([units[0], foreign], [template], ['package'], {}, {}, [])[2] == {'undeclared'}
    other = {**deepcopy(template), 'unit_prefix': 'export.other'}
    with pytest.raises(Unsupported, match='ambiguous templates'):
        _replacement_closure(units, [template, other], ['package'], {}, {}, [])


def test_full_unreplaced_selector_does_not_silently_drop_unsupported_required_work():
    rows, native = replacement_fixture()
    full = row('full', outputs=['build/game/full'])
    full['needs'] = ['unrelated.import']
    rows.append(full)
    with pytest.raises(Unsupported, match='unrelated.import: UnrealScript'):
        compile_rows(rows, project='game', targets=['full'], native=native)
