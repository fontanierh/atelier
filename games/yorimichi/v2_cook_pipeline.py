"""Join existing finished native owners to per-package stock cook and the Mac package consumer."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path

NATIVE_CLASSES = frozenset(('Texture', 'StaticMesh', 'SkeletalMesh', 'Skeleton', 'PhysicsAsset',
    'Material', 'MaterialInstance', 'MaterialParameterCollection', 'Blueprint', 'Map', 'Sound', 'Animation', 'DataAsset',
    'BlendSpace1D', 'AdventureMoveSet', 'AnimBoneCompressionSettings', 'AnimCurveCompressionSettings', 'MirrorDataTable', 'WandererDefinition', 'SoundAttenuation'))
PATHS = 'platform/studio/atelier/build_v2/recipe_native_paths.py'


def _load(root, name):
    spec = importlib.util.spec_from_file_location('cook_pipeline_' + name, root / 'games/yorimichi' / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _substitute(value, old, new):
    if isinstance(value, str): return value.replace(old, new)
    if isinstance(value, list): return [_substitute(v, old, new) for v in value]
    if isinstance(value, dict): return {_substitute(k, old, new): _substitute(v, old, new) for k, v in value.items()}
    return value


def _output_references(row):
    """Same required ROOT ownership as the normal row compiler; never inspect generated files."""
    covered = []
    for index, product in enumerate(row['products']):
        for position, path in enumerate(product['paths']):
            covered.append(path)
            yield path, {'unit': row['id'], 'item': 'product' + str(index),
                         'file': f'products/{index}-{position}.tree.tar', 'path': path}
        covered.extend(product['optional_paths'])
    for index, path in enumerate(row['outputs']):
        if not any(path == root or path.startswith(root + '/') for root in covered):
            yield path, {'unit': row['id'], 'item': 'output' + str(index),
                         'file': f'outputs/{index}.tree.tar', 'path': path}


def _context(rows, native, root):
    from atelier.build_v2.recipe_compiler import compile_rows
    by_id = {row['id']: row for row in rows}
    needed = set()
    def visit(name):
        if name in needed: return
        needed.add(name)
        row = by_id[name]
        for parent in (*row['needs'], *row['after'], *(r['producer'] for r in row['reads']),
                       *(r['producer'] for r in row.get('references', ()))):
            visit(parent)
    for name in ('unreal.compile', 'unreal.game_binary'): visit(name)
    compiled = compile_rows([row for row in rows if row['id'] in needed], project='yorimichi',
        targets=('unreal.compile', 'unreal.game_binary'), checkout=root, callback_out='build/yorimichi')
    units = {unit['id']: unit for unit in compiled.declaration['units']}
    editor = {'unit': 'unreal.compile', 'item': 'output0', 'file': 'outputs/0.tree.tar'}
    project = root / 'games/yorimichi/unreal/Yorimichi.uproject'
    descriptor = json.loads(project.read_bytes())
    available = {}
    for folder in (project.parent / 'Plugins', *(project.parent / name for name in descriptor.get('AdditionalPluginDirectories', ()))):
        for path in sorted(folder.rglob('*.uplugin')) if folder.is_dir() else ():
            if path.stem in available: raise ValueError('ambiguous source plugin descriptor: ' + path.stem)
            available[path.stem] = path
    wanted = {row['Name'] for row in descriptor.get('Plugins', ()) if row.get('Enabled', True)}
    pending = list(wanted)
    while pending:
        name = pending.pop()
        if name in available:
            for dependency in json.loads(available[name].read_bytes()).get('Plugins', ()):
                if dependency.get('Enabled', True) and dependency['Name'] not in wanted:
                    wanted.add(dependency['Name']); pending.append(dependency['Name'])
    plugins = {}
    for name in sorted(wanted & available.keys()):
        path = Path(os.path.abspath(available[name]))
        if path.resolve() != path or not path.is_relative_to(root):
            raise ValueError('source plugin descriptor is aliased or outside checkout')
        relative = path.relative_to(root).as_posix()
        if path.is_relative_to(project.parent / 'Plugins'):
            destination = (path.parent / 'Binaries/Mac').relative_to(root).as_posix()
            outputs = [row for row in units['unreal.compile']['params']['recipe']['outputs'] if row['path'] == destination]
            if len(outputs) != 1: raise ValueError('missing actual compiled plugin ROOT: ' + name)
            items = [item for item in units['unreal.compile']['outputs'] if any(f['path'] == outputs[0]['file'] for f in item['files'])]
            if len(items) != 1: raise ValueError('compiled plugin ROOT has no exact Item: ' + name)
            plugins[name] = {'unit': 'unreal.compile', 'item': items[0]['id'], 'file': outputs[0]['file'], 'descriptor_path': relative}
        else:
            plugins[name] = {**editor, 'descriptor_path': relative, 'binaries_in_editor': True}
    game_unit = units['unreal.game_binary']
    game = {'unit': game_unit['id'], 'item': 'output0', 'file': 'outputs/0.mac.zip', 'resources': []}
    for index, output in enumerate(game_unit['params']['recipe']['outputs']):
        if output['file'].endswith('.tree.tar'):
            game['resources'].append({'unit': game_unit['id'], 'item': 'output' + str(index),
                                      'file': output['file'], 'path': output['path']})
    return editor, game, plugins, _data_context(rows, native)


def _data_context(rows, native):
    """Bind original, replacement and additional runtime-data rows by their actual output owner."""
    data = {}
    effective = {row['id']: row for row in rows if row['id'] not in native['aliases']}
    effective.update({row['id']: row for row in native.get('rows', ())})
    for row in effective.values():
        for path, reference in _output_references(row):
            if path.startswith('games/yorimichi/unreal/Content/Data/'):
                if path in data: raise ValueError('duplicate runtime Data row output: ' + path)
                data[path] = reference
    for unit in native['units']:
        for item in unit['outputs']:
            for file in item['files']:
                path = file.get('install_path', '')
                if path.startswith('games/yorimichi/unreal/Content/Data/'):
                    if path in data: raise ValueError('duplicate runtime Data output owner: ' + path)
                    data[path] = {'unit': unit['id'], 'item': item['id'], 'file': file['path'], 'path': path}
    for reference in native.get('runtime_data', ()):
        path = reference['path']
        if not path.startswith('games/yorimichi/unreal/Content/Data/') or path in data:
            raise ValueError('duplicate or foreign explicit runtime Data owner: ' + path)
        data[path] = deepcopy(reference)
    return list(data.values())


def attach(native, rows, *, checkout):
    """@cc [owner:fontanierh,label:correctness] full-selected-native-cook-join
    Every selected finished native Item, including every actual expanded follower,
    MUST get its own source-cook and sealed verifier with declared transitive native
    inputs and matching produced editor/plugin/runtime Data context. Package MUST
    consume those verified Items and Global data with the actual produced game.
    Full aliases MUST remain absent while any selected original native family lacks
    a replacement. Dynamic names MUST come from existing validated child templates.
    No generated Content scan, ambient binary or old cook/package receipt is allowed.
    """
    root = Path(checkout).resolve()
    editor, game, plugins, data = _context(rows, native, root)
    global_bundle = _load(root, 'v2_global_cook_units').author_unit(checkout=root,
        editor=editor, plugins=plugins, data=data)
    cook = _load(root, 'v2_cook_units')
    geometry = native['geometry']
    templates = {tuple(t[k] for k in ('producer', 'group', 'unit_prefix')): t for t in geometry['templates']}
    by_id = {unit['id']: unit for unit in native['units']}
    def is_native(item):
        return (item['class'] in NATIVE_CLASSES and item['logical_path'].startswith('/Game/')
                and not item['logical_path'].startswith(('/Game/_Raw/', '/Game/AtelierRaw/')))
    def native_tokens(value):
        found = []
        if isinstance(value, dict):
            if set(value) == {'derived_items'}:
                descriptor = deepcopy(value['derived_items']); kept = []
                for source in descriptor.get('templates', ()):
                    template = templates[tuple(source[k] for k in ('producer', 'group', 'unit_prefix'))]
                    owner = template['followers'][source['follower']]['unit'] if 'follower' in source else None
                    if owner is None: continue
                    items = [item for item in owner['outputs'] if source.get('item', item['id']) == item['id']]
                    if len(items) != 1: raise ValueError('native cook closure requires one exact template Item')
                    if is_native(items[0]): kept.append(source)
                if kept:
                    descriptor['templates'] = kept; found.append({'derived_items': descriptor})
            else:
                for child in value.values(): found.extend(native_tokens(child))
        elif isinstance(value, list):
            for child in value: found.extend(native_tokens(child))
        return found
    def cook_one(owner, item, local=None):
        references, tokens, visited = {}, {}, set()
        owners = {**by_id, **(local or {})}
        def visit(unit):
            if unit['id'] in visited: return
            visited.add(unit['id'])
            for token in native_tokens(unit.get('params', {})):
                tokens[json.dumps(token, sort_keys=True)] = token
            for incoming in unit['inputs']:
                source = incoming['source']
                upstream = owners.get(source.get('unit')) if source['kind'] == 'item' else None
                if upstream:
                    matched = [output for output in upstream['outputs'] if output['id'] == source['item']]
                    if len(matched) != 1: raise ValueError('native cook closure has an unknown Item')
                    if is_native(matched[0]): references[(upstream['id'], matched[0]['id'])] = (upstream, matched[0])
                    if matched[0]['class'].startswith('Raw') or is_native(matched[0]): visit(upstream)
        references[(owner['id'], item['id'])] = (owner, item)
        visit(owner)
        package = item['logical_path']
        sentinel = 'AtelierV2SelectedPiece'
        declared = package.replace('$piece', sentinel)
        bundle = cook.author_units({declared: {'unit': owner['id'], 'item': item['id'], 'package': declared,
                                               'class': item['class']}}, checkout=root, source_context=global_bundle['units'][0])
        producer, verifier = bundle['units']
        producer['code'] = sorted(set(producer['code']) | {PATHS})
        incoming = {(row['source'].get('unit'), row['source'].get('item')): row['name']
                    for row in producer['inputs'] if row['source']['kind'] == 'item'}
        slots = []
        for key in references:
            slot = incoming.get(key)
            if slot is None:
                slot = 'dependency_' + str(len(slots))
                producer['inputs'].append({'role': 'content', 'name': slot, 'source': {'kind': 'item', 'unit': key[0], 'item': key[1]},
                    'whole': 'The stock cooker loads this complete declared transitive finished Native Item.'})
            slots.append(slot)
        producer['params']['recipe']['native_inputs'] = {'slots': slots, 'derived': list(tokens.values())}
        if '$piece' in package:
            bundle = _substitute(bundle, sentinel, '$piece')
            producer, verifier = bundle['units']
            producer['id'], verifier['id'] = '$export.cook.' + item['id'], '$export.cooked.' + item['id']
            verifier['inputs'][0]['source']['unit'] = producer['id']
            bundle['staged_inputs'] = {producer['id']: {row['name']: 'inputs/' + row['name'] for row in producer['inputs']},
                                        verifier['id']: {'record': 'inputs/record'}}
            bundle['packages'][package] = {'unit': verifier['id'], 'item': 'package', 'package': package}
            bundle['packages'].pop(declared, None)
        else:
            bundle['staged_inputs'][producer['id']] = {row['name']: 'inputs/' + row['name'] for row in producer['inputs']}
        bundle['content_slots'].update({row['name']: False for row in producer['inputs']})
        return bundle
    cooked, additions, dynamic = {}, [global_bundle], []
    for owner in list(native['units']):
        for item in owner['outputs']:
            if is_native(item):
                bundle = cook_one(owner, item); additions.append(bundle); cooked.update(bundle['packages'])
    for template in geometry['templates']:
        original = list(template.get('followers', ())); local, previous = {}, '$export'
        for follower in original:
            unit = _substitute(follower['unit'], '$previous', previous)
            local[unit['id']] = unit; previous = unit['id']
        for owner in local.values():
            for item in owner['outputs']:
                if not is_native(item): continue
                bundle = cook_one(owner, item, local)
                index = len(template['followers']) + 1
                template['followers'].extend({'unit': unit, 'staged_inputs': bundle['staged_inputs'][unit['id']]}
                                             for unit in bundle['units'])
                dynamic.append({'derived_items': {'root': 'build/v2-derived/cooked/' + template['unit_prefix'] + '/' + item['id'],
                    'templates': [{key: template[key] for key in ('producer', 'group', 'unit_prefix')}
                                  | {'follower': index, 'item': 'package'}]}})
                native['content_slots'].update(bundle['content_slots'])
    package = _load(root, 'v2_package_units').author_units(cooked, editor=editor, game=game, plugins=plugins,
        global_data={**global_bundle['global'], 'file': 'global-data.tree.tar'}, checkout=root, data=data, complete=False)
    package['units'][0]['params']['recipe']['cooked_members'] = dynamic
    additions.append(package)
    for bundle in additions:
        native['units'].extend(bundle['units']); native['staged_inputs'].update(bundle['staged_inputs'])
        native['content_slots'].update(bundle['content_slots'])
    unknown = [row['id'] for row in rows if row['id'] not in native['aliases']
               and any(command['kind'] == 'UnrealScript' for command in row['commands'])]
    if not unknown and not native.get('missing_roles'):
        native['aliases'].update({name: (_load(root, 'v2_package_units').DOWNLOAD,) for name in ('unreal.cook', 'unreal.package')})
    native['cook_gaps'] = unknown
    return native
