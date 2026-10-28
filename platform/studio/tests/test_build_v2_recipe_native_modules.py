"""Produced editor/plugin contexts bind explicit content edges, never ambient binaries."""
import json
from copy import deepcopy

import pytest

from atelier.build_v2.recipe_native_modules import attach


def fixture(tmp_path):
    project = tmp_path / 'games/game/unreal/Game.uproject'
    project.parent.mkdir(parents=True)
    project.write_text(json.dumps({'Modules': [{'Name': 'Game', 'Type': 'Runtime'}],
        'AdditionalPluginDirectories': ['../../../platform/engine/Plugins'],
        'Plugins': [{'Name': 'Tools', 'Enabled': True}]}))
    plugin = tmp_path / 'platform/engine/Plugins/Tools/Tools.uplugin'
    plugin.parent.mkdir(parents=True)
    plugin.write_text('{"Modules":[{"Name":"Tools","Type":"Editor"}]}')
    rows = [{'id': 'editor', 'commands': [{'kind': 'UnrealCompile'}],
             'products': [{'id': 'editor.Tools'}]}]
    units = [{'id': 'editor', 'params': {'project': project.relative_to(tmp_path).as_posix()},
              'outputs': [{'id': 'output0', 'files': [{'path': 'outputs/0.tree.tar'}]}]},
             {'id': 'pawn', 'inputs': [], 'params': {}}]
    return rows, units, {'pawn': {}}, {}, {'pawn': [{'name': 'Game'}]}


def test_game_module_context_uses_actual_compiled_items_and_descriptor(tmp_path):
    rows, units, staged, slots, required = fixture(tmp_path)
    attach(units, rows, required, checkout=tmp_path, staged=staged, slots=slots)
    unit = units[1]
    assert unit['inputs'] == [
        {'role': 'content', 'name': 'compiled_editor', 'source': {'kind': 'item', 'unit': 'editor', 'item': 'output0'}},
        {'role': 'content', 'name': 'compiled_plugin_0', 'source': {'kind': 'item', 'unit': 'editor', 'item': 'output0'}},
        {'role': 'content', 'name': 'compiled_descriptor_0', 'source': {'kind': 'file', 'path': 'platform/engine/Plugins/Tools/Tools.uplugin'}}]
    context = unit['params']['native_modules']
    assert context['editor'] == {'slot': 'compiled_editor', 'archive': 'outputs/0.tree.tar',
        'modules': [{'name': 'Game', 'kind': 'Runtime', 'loading_phase': 'Default'}], 'subset': True}
    assert context['plugins'][0]['archive'] == 'outputs/0.tree.tar'
    assert context['plugins'][0]['subset'] is True
    assert not (tmp_path / 'games/game/unreal/Binaries').exists()
    assert set(staged['pawn']) == set(slots)


@pytest.mark.parametrize('broken', ['producer', 'module', 'archive', 'plugin', 'collision'])
def test_missing_or_ambiguous_module_roles_refuse(tmp_path, broken):
    rows, units, staged, slots, required = fixture(tmp_path)
    if broken == 'producer': rows.clear()
    if broken == 'module': required['pawn'] = [{'name': 'Unknown'}]
    if broken == 'archive': units[0]['outputs'][0]['files'][0]['path'] = 'foreign.tree.tar'
    if broken == 'plugin':
        plugin = tmp_path / 'platform/engine/Plugins/Tools/Tools.uplugin'
        local = tmp_path / 'games/game/unreal/Plugins/Tools/Tools.uplugin'
        local.parent.mkdir(parents=True); plugin.rename(local)
        rows[0]['products'].clear()
    if broken == 'collision': staged['pawn']['compiled_editor'] = 'owned'
    with pytest.raises(ValueError):
        attach(units, rows, required, checkout=tmp_path, staged=staged, slots=slots)


def test_shared_modules_need_no_nonexistent_plugin_product(tmp_path):
    rows, units, staged, slots, required = fixture(tmp_path)
    rows[0]['products'].clear()
    attach(units, rows, required, checkout=tmp_path, staged=staged, slots=slots)
    plugin = units[1]['params']['native_modules']['plugins'][0]
    assert plugin['archive'] == 'outputs/0.tree.tar' and plugin['subset']


def test_project_local_plugin_keeps_its_separate_compiled_product(tmp_path):
    rows, units, staged, slots, required = fixture(tmp_path)
    plugin = tmp_path / 'platform/engine/Plugins/Tools/Tools.uplugin'
    local = tmp_path / 'games/game/unreal/Plugins/Tools/Tools.uplugin'
    local.parent.mkdir(parents=True); plugin.rename(local)
    attach(units, rows, required, checkout=tmp_path, staged=staged, slots=slots)
    context = units[1]['params']['native_modules']['plugins'][0]
    assert context['archive'] == 'products/0-0.tree.tar' and not context['subset']


def test_finished_template_binds_actual_compiled_module_items_before_expansion(tmp_path):
    from atelier.build_v2.recipe_native_modules import attach_followers
    rows, units, staged, slots, required = fixture(tmp_path)
    finish = {'unit': {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
                       'inputs': [], 'params': {}}, 'staged_inputs': {}}
    templates = [{'unit_prefix': 'world.example.export.Parent', 'followers': [finish]}]
    attach_followers(templates, units, rows, {'world.example.export.Parent': required['pawn']},
                     checkout=tmp_path, slots=slots)
    assert finish['unit']['params']['native_modules']['editor']['archive'] == 'outputs/0.tree.tar'
    assert finish['unit']['inputs'][0]['source'] == {'kind': 'item', 'unit': 'editor', 'item': 'output0'}
    assert set(finish['staged_inputs']) == set(slots)
    assert all('$' not in row['source'].get('unit', '') for row in finish['unit']['inputs'])


@pytest.mark.parametrize('broken', ['absent', 'no_finish', 'two_finishes'])
def test_template_module_request_cannot_silently_omit_a_finish(tmp_path, broken):
    from atelier.build_v2.recipe_native_modules import attach_followers
    rows, units, staged, slots, required = fixture(tmp_path)
    finish = {'unit': {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'},
                       'inputs': [], 'params': {}}, 'staged_inputs': {}}
    templates = [{'unit_prefix': 'world.example.export.Parent', 'followers': [finish]}]
    if broken == 'absent': templates.clear()
    elif broken == 'no_finish': templates[0]['followers'].clear()
    else: templates[0]['followers'].append(deepcopy(finish))
    with pytest.raises(ValueError, match='absent|authored or finish|duplicate stage'):
        attach_followers(templates, units, rows, {'world.example.export.Parent': required['pawn']},
                         checkout=tmp_path, slots=slots)


def test_each_distinct_city_finish_and_material_author_binds_compiled_modules(tmp_path):
    from atelier.build_v2.recipe_native_modules import attach_followers
    rows, units, staged, slots, required = fixture(tmp_path)
    followers = [{'unit': {'id': name, 'op': {'kind': kind, 'version': '1'}, 'inputs': [], 'params': {}},
                  'staged_inputs': {}} for name, kind in [('$export.raw', 'unreal.raw_import'),
                    ('$export.finish', 'unreal.finish'), ('$export.tree', 'unreal.finish'),
                    ('$export.material', 'unreal.author')]]
    attach_followers([{'unit_prefix': 'world.example.export.Parent', 'followers': followers}],
        units, rows, {'world.example.export.Parent': required['pawn']}, checkout=tmp_path, slots=slots)
    assert 'native_modules' not in followers[0]['unit']['params']
    for follower in followers[1:]:
        assert follower['unit']['params']['native_modules']['editor']['archive'] == 'outputs/0.tree.tar'
        assert follower['unit']['inputs'][0]['source'] == {'kind': 'item', 'unit': 'editor', 'item': 'output0'}
