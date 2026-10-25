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
        {'role': 'content', 'name': 'compiled_plugin_0', 'source': {'kind': 'item', 'unit': 'editor', 'item': 'product0'}},
        {'role': 'content', 'name': 'compiled_descriptor_0', 'source': {'kind': 'file', 'path': 'platform/engine/Plugins/Tools/Tools.uplugin'}}]
    context = unit['params']['native_modules']
    assert context['editor'] == {'slot': 'compiled_editor', 'archive': 'outputs/0.tree.tar',
        'modules': [{'name': 'Game', 'kind': 'Runtime', 'loading_phase': 'Default'}]}
    assert context['plugins'][0]['archive'] == 'products/0-0.tree.tar'
    assert not (tmp_path / 'games/game/unreal/Binaries').exists()
    assert set(staged['pawn']) == set(slots)


@pytest.mark.parametrize('broken', ['producer', 'module', 'archive', 'plugin', 'collision'])
def test_missing_or_ambiguous_module_roles_refuse(tmp_path, broken):
    rows, units, staged, slots, required = fixture(tmp_path)
    if broken == 'producer': rows.clear()
    if broken == 'module': required['pawn'] = [{'name': 'Unknown'}]
    if broken == 'archive': units[0]['outputs'][0]['files'][0]['path'] = 'foreign.tree.tar'
    if broken == 'plugin': rows[0]['products'].clear()
    if broken == 'collision': staged['pawn']['compiled_editor'] = 'owned'
    with pytest.raises(ValueError):
        attach(units, rows, required, checkout=tmp_path, staged=staged, slots=slots)
