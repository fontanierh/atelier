"""Global stock-cook declarations exercise existing view and output codecs only."""
import importlib.util
from pathlib import Path
import shutil

import pytest
from atelier.build_v2 import recipe_job

ROOT = Path(__file__).resolve().parents[3]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


cook = load('games/yorimichi/v2_global_cook_units.py', 'global_cook_units_test')


def refs():
    return {'editor': {'unit': 'unreal.compile', 'item': 'editor', 'file': 'editor.tree.tar'},
            'plugins': {'HorseRacing': {'unit': 'unreal.plugin.HorseRacing', 'item': 'modules',
                'file': 'plugin.tree.tar', 'descriptor_path': 'games/yorimichi/unreal/Plugins/HorseRacing/HorseRacing.uplugin'}}}


def test_global_source_binds_actual_modules_sources_and_fixed_engine_seed():
    result = cook.author_unit(checkout=ROOT, **refs())
    unit, = result['units']
    assert unit['op'] == {'kind': 'unreal.cook.produce', 'version': '1'}
    assert unit['params']['packages'] == ['/Engine/EngineResources/DefaultTexture']
    assert unit['params']['record_outputs'] == {cook.SEED: cook.RECORD}
    assert result['global'] == {'unit': unit['id'], 'item': 'global'}
    assert result['record'] == {'unit': unit['id'], 'item': 'seed'}
    recipe = unit['params']['recipe']
    assert recipe['commands'] == [] and recipe['verify'] is None
    assert [(r['kind'], r['required']) for r in recipe['outputs']] == [('file', True), ('tree', True), ('tree', True)]
    assert recipe['paths']['games/yorimichi/unreal/Binaries/Mac'] == 'inputs/editor/editor.tree.tar'
    assert recipe['paths']['games/yorimichi/unreal/Plugins/HorseRacing/Binaries/Mac'] == 'inputs/plugin_0/plugin.tree.tar'
    sources = {i['source']['path'] for i in unit['inputs'] if i['source']['kind'] == 'file'}
    assert cook.PROJECT in sources
    assert 'games/yorimichi/unreal/Plugins/HorseRacing/HorseRacing.uplugin' in sources
    assert {p.relative_to(ROOT).as_posix() for p in (ROOT / 'games/yorimichi/unreal/Config').rglob('*') if p.is_file()} <= sources
    compiled = [i for i in unit['inputs'] if i['source']['kind'] == 'item']
    assert len(compiled) == 2 and all(i['whole'] for i in compiled)
    assert not any('Binaries' in p for p in sources)
    assert len([p for p in unit['code'] if p.startswith('platform/build-v2/unreal/AtelierBuildWorker/')]) == 8
    assert not any(key in unit['params'] for key in ('source_key', 'namespace', 'receipt'))


def test_existing_prepare_and_export_preserve_complete_produced_modules_and_global_tree(tmp_path):
    unit = cook.author_unit(checkout=ROOT, **refs())['units'][0]
    worker = load('platform/studio/atelier/build_v2/native_tool_worker.py', 'global_native_tool_test')
    job = tmp_path / 'job'; job.mkdir()
    for name in unit['code']:
        destination = job / name; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)
    for incoming in unit['inputs']:
        slot, source = incoming['name'], incoming['source']
        target = job / 'inputs' / slot
        if source['kind'] == 'file':
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / source['path'], target)
        else:
            target.mkdir(parents=True)
            modules = tmp_path / slot; modules.mkdir()
            (modules / 'libUnrealEditor-ActualOwner.dylib').write_bytes(slot.encode())
            (modules / 'UnrealEditor.modules').write_bytes(b'complete module-map transport')
            archive = refs()['editor']['file'] if slot == 'editor' else refs()['plugins']['HorseRacing']['file']
            recipe_job.pack_root(modules, target / archive)
    (job / recipe_job.RUNTIME).mkdir()
    protocol_job = {**unit, 'inputs': [{'path': 'inputs/' + row['name']} for row in unit['inputs']]}
    view, protected, writes = recipe_job.prepare_view(protocol_job, job)
    assert (view / cook.PROJECT).read_bytes() == (ROOT / cook.PROJECT).read_bytes()
    for path, slot in (('games/yorimichi/unreal/Binaries/Mac', 'editor'),
                       ('games/yorimichi/unreal/Plugins/HorseRacing/Binaries/Mac', 'plugin_0')):
        assert (view / path / 'libUnrealEditor-ActualOwner.dylib').read_bytes() == slot.encode()
        assert (view / path / 'UnrealEditor.modules').is_file()
    (view / cook.RECORD).write_bytes(b'raw-CB-transport')
    cooked = view / cook.COOK_ROOT; cooked.mkdir()
    (cooked / 'ue.projectstore').write_bytes(b'owned-marker-transport')
    (cooked / 'CookedSettings.txt').write_bytes(b'complete-private-transport')
    semantic = view / cook.SEMANTIC_GLOBALS; semantic.mkdir(parents=True)
    for name in ('ShaderAssetInfo-Global-SF_METAL_SM5.assetinfo.json',
                 'ShaderArchive-Global-SF_METAL_SM5.ushaderbytecode', 'ShaderTypeInfo-Global-SF_METAL_SM5.stinfo'):
        (semantic / name).write_bytes(name.encode())
    output = job / 'output'; output.mkdir()
    def no_native(*args, **kwargs): raise AssertionError('transport test cannot launch native cook')
    worker.export_outputs(unit['params']['recipe'], view, output, no_native, raw_roots=(cook.RECORD,))
    assert (output / cook.RECORD).read_bytes() == b'raw-CB-transport'
    restored = tmp_path / 'restored'; recipe_job.unpack_root(output / 'global-cook.tree.tar', restored)
    assert {p.name for p in restored.iterdir()} == {'ue.projectstore', 'CookedSettings.txt'}
    semantic_copy = tmp_path / 'semantic-copy'; recipe_job.unpack_root(output / 'global-data.tree.tar', semantic_copy)
    assert len(list(semantic_copy.iterdir())) == 3
    assert not (semantic_copy / 'ue.projectstore').exists()
    assert str(cooked) in writes and str(view / cook.RECORD) in writes and protected


@pytest.mark.parametrize('invalid', ['editor', 'archive', 'plugin', 'descriptor'])
def test_missing_or_ambiguous_produced_references_refuse(invalid):
    values = refs()
    if invalid == 'editor': del values['editor']['unit']
    elif invalid == 'archive': values['editor']['file'] = '../ambient.tree.tar'
    elif invalid == 'plugin': values['plugins'] = {}
    else: values['plugins']['HorseRacing']['descriptor_path'] = 'platform/engine/Plugins/AtelierCore/AtelierCore.uplugin'
    with pytest.raises(ValueError): cook.author_unit(checkout=ROOT, **values)


SHARED = 'platform/engine/Plugins/AtelierCore/AtelierCore.uplugin'


def shared_refs(**change):
    value = refs()
    value['plugins']['AtelierCore'] = {**value['editor'], 'descriptor_path': SHARED, 'binaries_in_editor': True, **change}
    return value


def test_shared_plugin_binaries_reuse_the_editor_root_and_keep_their_descriptor():
    unit = cook.author_unit(checkout=ROOT, **shared_refs())['units'][0]
    paths = unit['params']['recipe']['paths']
    assert paths['games/yorimichi/unreal/Binaries/Mac'] == 'inputs/editor/editor.tree.tar'
    assert 'platform/engine/Plugins/AtelierCore/Binaries/Mac' not in paths
    assert paths['games/yorimichi/unreal/Plugins/HorseRacing/Binaries/Mac'] == 'inputs/plugin_1/plugin.tree.tar'
    assert SHARED in {i['source']['path'] for i in unit['inputs'] if i['source']['kind'] == 'file'}
    compiled = [i for i in unit['inputs'] if i['source']['kind'] == 'item']
    assert [i['name'] for i in compiled] == ['editor', 'plugin_1']


@pytest.mark.parametrize('change', [{'unit': 'other'}, {'item': 'modules'}, {'file': 'plugin.tree.tar'},
                                    {'binaries_in_editor': False}, {'binaries_in_editor': 1},
                                    {'descriptor_path': 'games/yorimichi/unreal/Plugins/AtelierCore/AtelierCore.uplugin'}])
def test_shared_plugin_reference_must_be_the_exact_editor_root(change):
    with pytest.raises(ValueError):
        cook.author_unit(checkout=ROOT, **shared_refs(**change))
