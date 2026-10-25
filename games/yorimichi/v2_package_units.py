"""Mac package composition over freshly verified cooked packages, then the original download assembly."""
import importlib.util
from pathlib import Path
import re

PROJECT = 'games/yorimichi/unreal/Yorimichi.uproject'
TARGET = 'Yorimichi'
PACKAGE = 'build/yorimichi/package'
ARCHIVE = PACKAGE + '/archive'
SCRIPT = 'platform/studio/atelier/build_v2/native_tool_worker.py'
FINALISE = 'platform/studio/atelier/build_v2/zen_package_finalise.py'
ARCHIVER = 'games/yorimichi/tools/package_archive.py'
LAUNCHER = 'games/yorimichi/tools/desktop_preview.py'
STAGE = 'unreal.package.mac'
DOWNLOAD = 'unreal.package.download'
DOWNLOAD_FILE = 'build/yorimichi/package-download.mac.zip'
ORIGINAL = ('unreal.cook', 'unreal.package')


def _load(root, path, name):
    spec = importlib.util.spec_from_file_location(name, root / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _item(name, reference, why):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': reference['unit'], 'item': reference['item']},
            'whole': why}


def _ref(value, what, keys=('unit', 'item')):
    if not isinstance(value, dict) or any(not isinstance(value.get(key), str) or not value[key] for key in keys):
        raise ValueError(f'package requires the actual produced {what} Item reference')
    return value


def _closure(root, *paths):
    from atelier.source_imports import ImportScanner
    scanner, code = ImportScanner(), set()
    for path in paths:
        code.update(found.relative_to(root).as_posix() for found in scanner.local_imports(
            root / path, (root / 'platform/studio', root / 'platform/harness')))
    return code


def author_units(cooked, *, editor, game, plugins, global_data, checkout, complete=False):
    """@cc [owner:fontanierh,label:correctness] package-from-verified-cooked-set
    Packaging MUST compose only the exact freshly verified CookedPackage Items it
    is given, with the actual produced game MacZIP, editor/plugin module ROOTs and
    semantic global data as declared inputs; none MAY come from recipe paths, Git,
    old cook receipts or scans. Download assembly MUST run the original archive
    script over the produced archive Item. The original cook/package targets are
    replaced only when the caller states the cooked set is complete.
    """
    root = Path(checkout).resolve()
    if not isinstance(cooked, dict) or not cooked:
        raise ValueError('package requires the verified CookedPackage roster')
    for package, reference in cooked.items():
        _ref(reference, 'CookedPackage')
        if (not isinstance(package, str) or not re.fullmatch(r'/Game/[A-Za-z0-9_/-]+', package)
                or reference.get('package') != package or set(reference) != {'unit', 'item', 'package'}):
            raise ValueError('cooked package reference identity differs: ' + str(package))
    _ref(game, 'game binary', ('unit', 'item', 'file'))
    if not game['file'].endswith('.mac.zip'):
        raise ValueError('game binary Item must be one complete Mac binary archive')
    _ref(global_data, 'global data', ('unit', 'item', 'file'))
    if global_data['file'] != 'global-data.tree.tar':
        raise ValueError('global data Item must be the semantic global-data ROOT')
    if type(complete) is not bool:
        raise ValueError('complete states whether the cooked roster covers the whole game')
    base = _load(root, 'games/yorimichi/v2_global_cook_units.py', 'package_global_cook_policy')
    declared = base.author_unit(checkout=root, editor=editor, plugins=plugins)['units'][0]
    inputs = list(declared['inputs'])
    paths = dict(declared['params']['recipe']['paths'])
    code = set(declared['code']) | _closure(root, FINALISE)
    inputs.append(_item('game', game, 'UAT stages the complete produced Mac game binaries from one archive.'))
    for index, resource in enumerate(game.get('resources', ())):
        if (not isinstance(resource, dict) or set(resource) != {'unit', 'item', 'file', 'path'}
                or resource['unit'] != game['unit'] or not isinstance(resource['file'], str)
                or not resource['file'].endswith('.tree.tar')):
            raise ValueError('game redistribution requires exact produced resource Items')
        destination = resource['path']
        if (not isinstance(destination, str) or not destination.startswith('games/yorimichi/unreal/Samples/')
                or any(part in ('', '.', '..') for part in destination.split('/')) or destination in paths
                or not isinstance(resource['file'], str) or resource['file'].startswith('/')
                or any(part in ('', '.', '..') for part in resource['file'].split('/'))):
            raise ValueError('game redistribution resource path escapes or aliases')
        slot = 'game_resource_' + str(index)
        inputs.append(_item(slot, resource, 'UAT consumes the produced redistributed game resource.'))
        paths[destination] = 'inputs/' + slot + '/' + resource['file']
    inputs.append(_item('global', global_data, 'Native finalisation composes from the complete semantic global ROOT.'))
    for index, (package, reference) in enumerate(sorted(cooked.items())):
        inputs.append(_item('cooked_' + str(index), reference, 'Sealed native package ' + package + '.'))
    names = [row['name'] for row in inputs]
    if len(set(names)) != len(names):
        raise ValueError('duplicate package input slot')
    recipe = {'version': 1, 'commands': [], 'paths': paths, 'verify': None,
              'outputs': [{'path': ARCHIVE, 'kind': 'tree', 'file': 'archive.mac.zip', 'encoding': 'mac-zip', 'required': True}]}
    stage = {'id': STAGE, 'op': {'kind': 'unreal.package', 'version': '1'}, 'script': SCRIPT, 'code': sorted(code),
             'inputs': inputs,
             'params': {'project': PROJECT, 'target': TARGET, 'archive': ARCHIVE, 'native_global': 'global', 'recipe': recipe},
             'outputs': [{'id': 'archive', 'logical_path': '/Package/Mac/Archive', 'class': 'Data', 'destination': 'store',
                          'files': [{'path': 'archive.mac.zip', 'required': True}]}]}
    archive_inputs = [_item('archive', {'unit': STAGE, 'item': 'archive'},
                            'Download assembly reads the complete archived .app produced by UAT.')]
    download = {'id': DOWNLOAD, 'op': {'kind': 'package.archive', 'version': '1'}, 'script': SCRIPT,
                'code': sorted(_closure(root, SCRIPT, ARCHIVER, LAUNCHER)), 'inputs': archive_inputs,
                'params': {'recipe': {'version': 1, 'paths': {}, 'verify': None,
                    'commands': [{'kind': 'python', 'script': ARCHIVER, 'args': ['--out', {'path': PACKAGE}], 'env': {}}],
                    'outputs': [{'path': PACKAGE, 'kind': 'tree', 'file': 'package-download.mac.zip', 'encoding': 'mac-zip',
                                 'required': True}]}},
                'outputs': [{'id': 'download', 'logical_path': '/Package/Mac/Download', 'class': 'Data', 'destination': 'checkout',
                             'files': [{'path': 'package-download.mac.zip', 'install_path': DOWNLOAD_FILE, 'required': True}]}]}
    units = [stage, download]
    return {'units': units,
            'staged_inputs': {unit['id']: {row['name']: 'inputs/' + row['name'] for row in unit['inputs']} for unit in units},
            'content_slots': {row['name']: False for unit in units for row in unit['inputs']},
            'aliases': {original: (STAGE, DOWNLOAD) for original in ORIGINAL} if complete else {},
            'archive': {'unit': STAGE, 'item': 'archive'}, 'download': {'unit': DOWNLOAD, 'item': 'download'}}
