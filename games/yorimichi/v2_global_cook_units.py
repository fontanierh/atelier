"""Stock Mac global cook source, using actual produced editor/plugin bytes."""
import importlib.util
from pathlib import Path, PurePosixPath
import re

PROJECT = 'games/yorimichi/unreal/Yorimichi.uproject'
SEED = '/Engine/EngineResources/DefaultTexture'
UNIT = 'unreal.cook.global.mac-default-texture-v1'
RECORD = 'records/global-seed.cb'
SEMANTIC_GLOBALS = 'build/yorimichi/global-cook/mac/semantic'
COOK_ROOT = 'games/yorimichi/unreal/Saved/Cooked/Mac'
PROJECT_PLUGINS = 'games/yorimichi/unreal/Plugins/'


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or '\x00' in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in ('', '.', '..') for part in value.split('/'))):
        raise ValueError('global cook requires canonical relative source paths')
    return value


def _produced(reference):
    if (not isinstance(reference, dict) or any(not isinstance(reference.get(key), str) or not reference[key]
                                              for key in ('unit', 'item', 'file'))):
        raise ValueError('global cook requires actual produced module Item references')
    file = _relative(reference['file'])
    if not file.endswith('.tree.tar'):
        raise ValueError('compiled Mac modules must use their complete ROOT archive')
    return file


def author_unit(*, checkout, editor, plugins, data=()):
    """@cc [owner:fontanierh,label:correctness] stock-global-cook-source
    Global cook MUST execute the existing stock source-cook route over the fixed
    engine seed and explicitly produced complete editor/plugin module ROOTs. Project,
    Config and plugin descriptors MUST be actual source File inputs. Supplied runtime
    data MUST be actual produced Items mapped only to their declared Content/Data paths. SDK/engine
    locators MUST stay platform context. Raw CB bytes and full cooked metadata MUST
    remain distinct outputs; declarations MUST NOT mint namespaces, native receipts,
    source keys or global shader/Metal validation claims, nor read ambient Binaries.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    spec = importlib.util.spec_from_file_location('global_cook_declaration_policy', root / 'games/yorimichi/v2_cook_units.py')
    cook = importlib.util.module_from_spec(spec); spec.loader.exec_module(cook)
    scanner = ImportScanner()
    code = {cook.SCRIPT, *(cook.WORKER_ROOT + path for path in cook.WORKER_FILES)}
    for helper in (cook.SCRIPT, 'platform/studio/atelier/build_v2/protocol.py',
                   'platform/studio/atelier/build_v2/recipe_job.py',
                   'platform/studio/atelier/build_v2/unreal_tool_ops.py',
                   'platform/studio/atelier/build_zen.py', 'platform/studio/atelier/build_cook.py'):
        code.update(path.relative_to(root).as_posix() for path in scanner.local_imports(
            root / helper, (root / 'platform/studio', root / 'platform/harness')))
    inputs, paths = [], {}
    def source(name, path):
        _relative(path)
        actual = root / path
        if not actual.is_file() or actual.is_symlink() or actual.resolve() != actual:
            raise ValueError('global cook source is missing or aliased: ' + path)
        inputs.append({'role': 'content', 'name': name, 'source': {'kind': 'file', 'path': path}})
        paths[path] = 'inputs/' + name
    def compiled(name, reference, destination):
        file = _produced(reference)
        _relative(destination)
        if destination in paths:
            raise ValueError('duplicate global cook module destination')
        inputs.append({'role': 'content', 'name': name, 'source': {
            'kind': 'item', 'unit': reference['unit'], 'item': reference['item']},
            'whole': 'Stock source cook loads the complete produced Mac module tree and receipt/module map.'})
        paths[destination] = 'inputs/' + name + '/' + file
    source('project', PROJECT)
    config = root / 'games/yorimichi/unreal/Config'
    if config.is_symlink() or not config.is_dir() or config.resolve() != config:
        raise ValueError('global cook needs the original regular source Config directory')
    for index, path in enumerate(sorted(config.rglob('*'))):
        if path.is_symlink():
            raise ValueError('global cook source Config contains a link')
        if path.is_file():
            source('config_' + str(index), path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise ValueError('global cook source Config contains a special member')
    compiled('editor', editor, 'games/yorimichi/unreal/Binaries/Mac')
    if not isinstance(plugins, dict) or not plugins:
        raise ValueError('global cook requires the actual produced project plugin roster')
    descriptors = set()
    for index, (name, reference) in enumerate(sorted(plugins.items())):
        if not isinstance(name, str) or not re.fullmatch('[A-Za-z0-9_]+', name) or not isinstance(reference, dict):
            raise ValueError('invalid global cook plugin reference')
        descriptor = _relative(reference.get('descriptor_path'))
        if PurePosixPath(descriptor).name != name + '.uplugin' or descriptor.casefold() in descriptors:
            raise ValueError('global cook plugin descriptor identity differs or aliases')
        descriptors.add(descriptor.casefold())
        source('plugin_descriptor_' + str(index), descriptor)
        if 'binaries_in_editor' in reference:
            # Shared AdditionalPluginDirectories modules live in the project Binaries/Mac
            # editor root already mapped above; only their descriptor is a separate input.
            if (reference['binaries_in_editor'] is not True or descriptor.startswith(PROJECT_PLUGINS)
                    or {key: reference.get(key) for key in ('unit', 'item', 'file')}
                    != {key: editor.get(key) for key in ('unit', 'item', 'file')}):
                raise ValueError('shared plugin binaries must be the exact editor module root')
            continue
        compiled('plugin_' + str(index), reference, str(PurePosixPath(descriptor).parent / 'Binaries/Mac'))
    for index, reference in enumerate(data):
        if (not isinstance(reference, dict) or set(reference) != {'unit', 'item', 'file', 'path'}
                or any(not isinstance(reference.get(key), str) or not reference[key] for key in reference)):
            raise ValueError('global cook runtime data requires exact produced Item and path references')
        destination, file = _relative(reference['path']), _relative(reference['file'])
        base = 'games/yorimichi/unreal/Content/Data'
        if (destination != base and not destination.startswith(base + '/')) or destination in paths:
            raise ValueError('global cook runtime data escapes or aliases Content/Data')
        if any(destination.startswith(path + '/') or path.startswith(destination + '/') for path in paths):
            raise ValueError('global cook runtime data destinations overlap')
        slot = 'data_' + str(index)
        inputs.append({'role': 'content', 'name': slot, 'source': {
            'kind': 'item', 'unit': reference['unit'], 'item': reference['item']},
            'whole': 'The stock cooker and package stage consume this complete produced runtime data file or ROOT.'})
        paths[destination] = 'inputs/' + slot + '/' + file
    recipe = {'version': 1, 'commands': [], 'paths': paths, 'verify': None,
              'outputs': [{'path': RECORD, 'kind': 'file', 'file': RECORD, 'required': True},
                          {'path': COOK_ROOT, 'kind': 'tree', 'file': 'global-cook.tree.tar', 'required': True},
                          {'path': SEMANTIC_GLOBALS, 'kind': 'tree', 'file': 'global-data.tree.tar', 'required': True}]}
    unit = {'id': UNIT, 'op': {'kind': 'unreal.cook.produce', 'version': '1'}, 'script': cook.SCRIPT,
            'code': sorted(code), 'inputs': inputs,
            'params': {'project': PROJECT, 'packages': [SEED], 'record_outputs': {SEED: RECORD},
                       'cook_root': COOK_ROOT, 'global_data': SEMANTIC_GLOBALS, 'recipe': recipe},
            'outputs': [{'id': 'seed', 'logical_path': SEED, 'class': 'NativeCookRecord',
                         'destination': 'store', 'files': [{'path': RECORD, 'required': True}]},
                        {'id': 'metadata', 'logical_path': '/Cook/Transport/Mac', 'class': 'Data',
                         'destination': 'store', 'files': [{'path': 'global-cook.tree.tar', 'required': True}]},
                        {'id': 'global', 'logical_path': '/Cook/Global/Mac', 'class': 'Data',
                         'destination': 'store', 'files': [{'path': 'global-data.tree.tar', 'required': True}]}]}
    return {'units': [unit], 'staged_inputs': {UNIT: {row['name']: 'inputs/' + row['name'] for row in inputs}},
            'content_slots': {row['name']: False for row in inputs},
            'global': {'unit': UNIT, 'item': 'global'}, 'record': {'unit': UNIT, 'item': 'seed'}}
