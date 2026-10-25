"""Bind compiled project/module Items to explicitly authored native unit contexts."""
from copy import deepcopy
import json
from pathlib import Path


def attach(units, rows, requirements, *, checkout, staged, slots):
    """@cc [owner:fontanierh,label:correctness] authored-native-module-item-edges
    Every requested game module context MUST consume actual compiled editor and
    plugin product Items, plus each selected plugin descriptor. Never read generated
    binaries, infer a build success or use an ambient checkout binary locator.
    Complete declared project modules are loaded from the produced editor inventory;
    selected project plugins include their declared plugin dependency closure.
    """
    if not requirements:
        return
    root = Path(checkout)
    candidates = [row for row in rows if any(command['kind'] == 'UnrealCompile' for command in row['commands'])]
    if len(candidates) != 1:
        raise ValueError('native authored modules require one declared editor compile producer')
    compile_row = candidates[0]
    compile_unit = next((unit for unit in units if unit['id'] == compile_row['id']), None)
    if compile_unit is None:
        raise ValueError('native module editor producer was not compiled into a v2 unit')
    project = root / compile_unit['params']['project']
    descriptor = json.loads(project.read_bytes())
    modules = [{'name': module['Name'], 'kind': module['Type'], 'loading_phase': module.get('LoadingPhase', 'Default')}
               for module in descriptor.get('Modules', [])]
    if not modules:
        raise ValueError('native project descriptor has no authored modules')
    folders = [project.parent / 'Plugins', *(project.parent / value for value in descriptor.get('AdditionalPluginDirectories', []))]
    available = {}
    for folder in folders:
        for path in sorted(folder.rglob('*.uplugin')) if folder.is_dir() else ():
            available[path.stem] = path
    enabled = {row['Name'] for row in descriptor.get('Plugins', []) if row.get('Enabled', True)}
    pending = list(enabled)
    while pending:
        name = pending.pop()
        if name in available:
            value = json.loads(available[name].read_bytes())
            for dependency in value.get('Plugins', []):
                if dependency.get('Enabled', True) and dependency['Name'] not in enabled:
                    enabled.add(dependency['Name']); pending.append(dependency['Name'])
    products = {product['id']: index for index, product in enumerate(compile_row['products'])}
    editor_roots = [output for output in compile_unit['outputs'] if output['id'].startswith('output')]
    if len(editor_roots) != 1 or editor_roots[0]['files'] != [{'path': 'outputs/0.tree.tar'}]:
        raise ValueError('editor compile does not expose the exact complete editor binary tree')
    by_id = {unit['id']: unit for unit in units}
    for unit_id, requested in requirements.items():
        if not {row['name'] for row in requested} <= {row['name'] for row in modules}:
            raise ValueError('native body requested an undeclared game module')
        unit = by_id[unit_id]
        stage = staged[unit_id]
        def incoming(slot, source):
            if slot in stage or any(row['name'] == slot for row in unit['inputs']):
                raise ValueError('native module input collides with a declared body slot')
            unit['inputs'].append({'role': 'content', 'name': slot, 'source': source})
            stage[slot] = 'inputs/' + slot
            slots[slot] = False
        incoming('compiled_editor', {'kind': 'item', 'unit': compile_row['id'], 'item': editor_roots[0]['id']})
        context = {'editor': {'slot': 'compiled_editor', 'archive': 'outputs/0.tree.tar', 'modules': deepcopy(modules)}, 'plugins': []}
        for index, name in enumerate(sorted(enabled & available.keys())):
            product = compile_row['id'] + '.' + name
            if product not in products:
                raise ValueError('selected native plugin has no compiled product: ' + name)
            item = 'product' + str(products[product])
            archive = f'products/{products[product]}-0.tree.tar'
            binary_slot, descriptor_slot = 'compiled_plugin_' + str(index), 'compiled_descriptor_' + str(index)
            incoming(binary_slot, {'kind': 'item', 'unit': compile_row['id'], 'item': item})
            path = available[name].resolve().relative_to(root).as_posix()
            incoming(descriptor_slot, {'kind': 'file', 'path': path})
            context['plugins'].append({'name': name, 'slot': binary_slot, 'archive': archive, 'descriptor_slot': descriptor_slot})
        unit['params']['native_modules'] = context
