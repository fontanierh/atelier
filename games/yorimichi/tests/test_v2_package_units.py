"""Package declarations bind the verified cooked roster and produced binaries, never recipe-mapped or scanned bytes."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('package_units_test', ROOT / 'games/yorimichi/v2_package_units.py')
units = importlib.util.module_from_spec(spec); spec.loader.exec_module(units)
DESCRIPTOR = 'games/yorimichi/unreal/Plugins/HorseRacing/HorseRacing.uplugin'


def refs(**change):
    value = {'cooked': {'/Game/Maps/Japan': {'unit': 'cook.verify.japan', 'item': 'package', 'package': '/Game/Maps/Japan'},
                        '/Game/Nox/SK_Nox': {'unit': 'cook.verify.nox', 'item': 'package', 'package': '/Game/Nox/SK_Nox'}},
             'editor': {'unit': 'unreal.compile', 'item': 'editor', 'file': 'editor.tree.tar'},
             'game': {'unit': 'unreal.game', 'item': 'game', 'file': 'game.mac.zip'},
             'plugins': {'HorseRacing': {'unit': 'unreal.plugin.HorseRacing', 'item': 'modules', 'file': 'plugin.tree.tar',
                                         'descriptor_path': DESCRIPTOR}},
             'global_data': {'unit': 'unreal.cook.global', 'item': 'global', 'file': 'global-data.tree.tar'}}
    value.update(change)
    cooked = value.pop('cooked')
    return units.author_units(cooked, checkout=ROOT, **value)


def test_stage_composes_exact_cooked_items_with_produced_binaries_outside_recipe_paths():
    result = refs()
    stage, download = result['units']
    assert stage['op'] == {'kind': 'unreal.package', 'version': '1'} and stage['script'] == units.SCRIPT
    params = stage['params']
    assert {k: params[k] for k in ('project', 'target', 'archive', 'native_global')} == {
        'project': units.PROJECT, 'target': 'Yorimichi', 'archive': 'build/yorimichi/package/archive', 'native_global': 'global'}
    by_name = {row['name']: row['source'] for row in stage['inputs']}
    assert by_name['game'] == {'kind': 'item', 'unit': 'unreal.game', 'item': 'game'}
    assert by_name['global'] == {'kind': 'item', 'unit': 'unreal.cook.global', 'item': 'global'}
    assert [by_name[f'cooked_{i}']['unit'] for i in range(2)] == ['cook.verify.japan', 'cook.verify.nox']
    paths = params['recipe']['paths']
    assert not any(value.startswith(('inputs/game', 'inputs/global', 'inputs/cooked_')) for value in paths.values())
    assert paths['games/yorimichi/unreal/Binaries/Mac'] == 'inputs/editor/editor.tree.tar'
    assert paths['games/yorimichi/unreal/Plugins/HorseRacing/Binaries/Mac'] == 'inputs/plugin_0/plugin.tree.tar'
    assert params['recipe']['outputs'] == [{'path': 'build/yorimichi/package/archive', 'kind': 'tree', 'file': 'archive.mac.zip',
                                            'encoding': 'mac-zip', 'required': True}]
    assert [(o['class'], o['destination'], o['files']) for o in stage['outputs']] == [
        ('Data', 'store', [{'path': 'archive.mac.zip', 'required': True}])]
    assert units.FINALISE in stage['code'] and units.SCRIPT in stage['code']
    assert not any(key in params for key in ('cooked_files', 'source_key', 'namespace', 'receipt', 'revision'))
    assert result['staged_inputs'][units.STAGE]['cooked_1'] == 'inputs/cooked_1'


def test_download_runs_original_archive_script_over_the_produced_archive_item():
    stage, download = refs()['units']
    assert download['op'] == {'kind': 'package.archive', 'version': '1'} and 'project' not in download['params']
    assert download['inputs'] == [{'role': 'content', 'name': 'archive',
                                   'source': {'kind': 'item', 'unit': units.STAGE, 'item': 'archive'},
                                   'whole': download['inputs'][0]['whole']}]
    recipe = download['params']['recipe']
    assert recipe['paths'] == {} and recipe['verify'] is None
    command, = recipe['commands']
    assert command == {'kind': 'python', 'script': units.ARCHIVER, 'args': ['--out', {'path': 'build/yorimichi/package'}],
                       'env': {}}
    assert '--cook-receipt' not in command['args']
    assert {units.ARCHIVER, units.LAUNCHER, 'platform/studio/atelier/provenance.py'} <= set(download['code'])
    assert recipe['outputs'] == [{'path': 'build/yorimichi/package', 'kind': 'tree', 'file': 'package-download.mac.zip',
                                  'encoding': 'mac-zip', 'required': True}]
    output, = download['outputs']
    assert (output['class'], output['destination']) == ('Data', 'checkout')
    assert output['files'] == [{'path': 'package-download.mac.zip', 'install_path': 'build/yorimichi/package-download.mac.zip',
                                'required': True}]


def test_original_targets_are_replaced_only_for_a_stated_complete_roster():
    assert refs()['aliases'] == {}
    assert refs(complete=True)['aliases'] == {'unreal.cook': (units.STAGE, units.DOWNLOAD),
                                              'unreal.package': (units.STAGE, units.DOWNLOAD)}


@pytest.mark.parametrize('change', [
    {'cooked': {}},
    {'cooked': {'/Game/A': {'unit': 'u', 'item': 'package', 'package': '/Game/B'}}},
    {'cooked': {'/Game/A': {'unit': 'u', 'item': 'package', 'package': '/Game/A', 'namespace': 'x'}}},
    {'cooked': {'Game/A': {'unit': 'u', 'item': 'package', 'package': 'Game/A'}}},
    {'game': {'unit': 'unreal.game', 'item': 'game', 'file': 'game.tree.tar'}},
    {'game': {'unit': 'unreal.game', 'item': 'game'}},
    {'global_data': {'unit': 'g', 'item': 'global', 'file': 'global-cook.tree.tar'}},
    {'editor': {'unit': 'unreal.compile', 'item': 'editor', 'file': 'editor.mac.zip'}},
    {'plugins': {}},
    {'complete': 1},
])
def test_reshaped_or_partial_references_refuse(change):
    with pytest.raises(ValueError):
        refs(**change)
