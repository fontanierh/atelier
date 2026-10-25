"""Explicit typed skate runtime, bank, motion-index and verification owners."""
import json
from pathlib import Path, PurePosixPath

from v2_texture_units import SIDECARS, Unsupported, _code

SCRIPT = 'games/yorimichi/world/skate_data_v2.py'
SAVE = 'platform/studio/atelier/native_packages.py'
CONFIG = 'games/yorimichi/unreal/Config/DefaultGame.ini'
SCRIPTS = 'games/yorimichi/unreal/Scripts/skate_ride/'
MANIFEST = 'platform/engine/Plugins/Activities/Skate/Data/package-manifest.json'
RUNTIME = '/Game/SkateRuntime/RuntimeData'
MOTION = '/Game/SkateMotion/MotionData'
PREFIX = 'unreal.skate_data.'


def _canonical(value):
    if (not isinstance(value, str) or not value or '\\' in value or PurePosixPath(value).is_absolute()
            or any(p in ('', '.', '..') for p in value.split('/'))):
        raise Unsupported('noncanonical skate source/output path')
    return value


def author_units(rows, *, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] complete-skate-data-owners
    Every motion bank MUST have an individual owner from the committed manifest's
    original 128-clip roster. The source input MUST bind the actual skate.runtime
    package output ROOT. MotionData and verification MUST consume all bank Items;
    the original alias MUST include the installed complete verification report.
    No original script main, Content discovery or native retirement MAY execute.
    """
    result = {'units': [], 'staged_inputs': {}, 'content_slots': {}, 'packages': {},
              'aliases': {}, 'module_requirements': {}}
    selected = [r for r in rows if r['id'] == 'unreal.skate_data']
    if not selected:
        return result
    producers = [r for r in rows if r['id'] == 'skate.runtime']
    if len(selected) != 1 or len(producers) != 1:
        raise Unsupported('skate data requires its unique actual source producer')
    row, producer = selected[0], producers[0]
    commands = row['commands']
    expected = [('import_runtime.py', 'SKATE RUNTIME IMPORT COMPLETE'),
                ('import_motion.py', 'SKATE MOTION IMPORT COMPLETE'), ('verify_data.py', 'SKATE DATA VERIFY COMPLETE')]
    if len(commands) != 3 or row['needs'] != ['skate.runtime']:
        raise Unsupported('skate data requires its original three commands and source dependency')
    for command, (name, marker) in zip(commands, expected):
        if (command.get('kind') != 'UnrealScript' or command.get('script') != {'path': SCRIPTS + name}
                or command.get('marker') != marker or command.get('null_rhi') is not True
                or command.get('env') not in ([], ()) or command.get('args') not in ([], ())
                or command.get('modules') not in ([], ())):
            raise Unsupported('skate data source command differs from its original')
    outputs = row['outputs']
    if (len(outputs) != 3 or outputs[:2] != ['games/yorimichi/unreal/Content/' + p.removeprefix('/Game/') + '.uasset'
                                           for p in (RUNTIME, MOTION)]
            or not _canonical(outputs[2]).endswith('/skate-data/verify.json')):
        raise Unsupported('skate data original package/report outputs differ')
    source_commands = producer['commands']
    if len(source_commands) != 1 or source_commands[0].get('kind') != 'python':
        raise Unsupported('skate runtime must retain its actual package constructor')
    arguments = source_commands[0].get('args')
    if (source_commands[0].get('script') != {'path': 'platform/engine/Plugins/Activities/Skate/Tools/simulation_package.py'}
            or not isinstance(arguments, list) or len(arguments) != 4 or arguments[0] != '--assemble'
            or arguments[2] != '--output' or not isinstance(arguments[1], dict) or set(arguments[1]) != {'path'}
            or not isinstance(arguments[3], dict) or set(arguments[3]) != {'path'}):
        raise Unsupported('skate runtime original package command differs')
    source_path = _canonical(arguments[1]['path'])
    if (producer['products'] or len(producer['outputs']) != 2
            or set(producer['outputs']) != {_canonical(arguments[3]['path']), source_path}
            or PurePosixPath(source_path).name != 'package'):
        raise Unsupported('skate runtime complete package must be its exact ungrouped output ROOT')
    index = producer['outputs'].index(source_path)
    binding = {'archive_member': f'outputs/{index}.tree.tar', 'name': PurePosixPath(source_path).name}
    root = Path(checkout)
    manifest = json.loads((root / MANIFEST).read_text())
    clips = manifest.get('clips')
    if (manifest.get('version') != 1 or type(clips) is not int or clips <= 0
            or clips != sum(name.startswith('animation/clips/') and name.endswith('.skate') for name in manifest['files'])):
        raise Unsupported('committed skate clip roster is incomplete')
    count = (clips + 127) // 128
    project = json.loads((root / 'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m['LoadingPhase']} for m in project['Modules']]
    configured, section = {}, ''
    for line in (root / CONFIG).read_text().splitlines():
        line = line.strip()
        if line.startswith('['): section = line
        if section == '[/Script/AtelierSkate.SkateSettings]' and '=' in line:
            key, value = line.split('=', 1)
            if key in ('MotionData', 'RuntimeData'):
                if key in configured: raise Unsupported('duplicate original skate configured asset')
                configured[key] = value
    if configured != {'MotionData': MOTION + '.MotionData', 'RuntimeData': RUNTIME + '.RuntimeData'}:
        raise Unsupported('original skate verification asset configuration differs')
    code = sorted({*_code(root), SCRIPT, SAVE, CONFIG, *(SCRIPTS + name for name, _ in expected)})
    for path in code:
        if not (root / path).is_file() or (root / path).is_symlink():
            raise Unsupported('skate data keyed source is missing or linked: ' + path)
    def incoming(slot, ref):
        return {'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}}
    source = {'unit': producer['id'], 'item': 'output' + str(index)}
    def add(action, package, dependencies, *, bank=None):
        unit_id = PREFIX + (f'bank.{bank:03d}' if bank is not None else action)
        inputs = [incoming('source', source), *(incoming(slot, ref) for slot, ref in dependencies.items())]
        args = {'action': action, 'bank_count': count, 'clips': clips}
        if bank is not None: args['bank'] = bank
        if action == 'verify':
            args['configured_assets'] = {'motion_data': configured['MotionData'], 'runtime_data': configured['RuntimeData']}
            output = {'id': 'report', 'logical_path': '/Game/_Data/Skate/verify', 'class': 'JsonData', 'destination': 'checkout',
                      'files': [{'path': 'data/verify.json', 'install_path': outputs[2], 'required': True}]}
        else:
            args['package'] = package
            stem = package.removeprefix('/Game/')
            output = {'id': 'asset', 'logical_path': package, 'class': 'DataAsset', 'destination': 'checkout',
                      'files': [{'path': 'content/Game/' + stem + ext,
                                 'install_path': 'games/yorimichi/unreal/Content/' + stem + ext,
                                 'required': ext == '.uasset'} for ext in SIDECARS]}
        unit = {'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
                'code': code, 'inputs': inputs, 'params': {'args': args, 'settings': [], 'input_roots': {'source': binding}},
                'outputs': [output]}
        result['units'].append(unit)
        result['staged_inputs'][unit_id] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        result['content_slots'].update({i['name']: False for i in inputs})
        result['module_requirements'][unit_id] = modules
        ref = {'unit': unit_id, 'item': output['id']}
        if package:
            ref['package'] = package
            if dependencies: ref['dependencies'] = list(dependencies.values())
        result['packages'][package or outputs[2]] = ref
        return ref
    runtime = add('runtime', RUNTIME, {})
    banks = {f'bank{b:03d}': add('bank', f'/Game/SkateMotion/Banks/Bank_{b:03d}', {}, bank=b) for b in range(count)}
    motion = add('motion', MOTION, banks)
    add('verify', None, {'runtime': runtime, 'motion': motion, **banks})
    result['aliases']['unreal.skate_data'] = [u['id'] for u in result['units']]
    return result
