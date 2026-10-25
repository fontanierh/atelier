"""Per-package stock cook declarations followed by sealed native verification."""
import hashlib
from copy import deepcopy
from pathlib import Path
import re

SCRIPT = 'platform/studio/atelier/build_v2/native_tool_worker.py'
VERIFY = 'platform/studio/atelier/build_v2/zen_verify.py'
PROJECT = 'games/yorimichi/unreal/Yorimichi.uproject'
COOK_ROOT = 'games/yorimichi/unreal/Saved/Cooked/Mac'
WORKER_ROOT = 'platform/build-v2/unreal/AtelierBuildWorker/'
WORKER_FILES = (
    'AtelierBuildWorker.uplugin',
    'Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs',
    'Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp',
    'Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp',
    'Source/AtelierBuildWorker/Private/AtelierZenPackage.cpp',
    'Source/AtelierBuildWorker/Private/AtelierZenFinalise.cpp',
    'Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h',
    'Source/AtelierBuildWorker/Public/AtelierZenFinalise.h',
)
SIDECARS = ('.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')


def _reference(value, package=None):
    if not isinstance(value, dict):
        raise ValueError('cook requires finished native item references')
    package = value.get('package', package)
    if (not isinstance(package, str) or not re.fullmatch(r'/Game/[A-Za-z0-9_/-]+', package)
            or any(not part for part in package[1:].split('/'))
            or any(not isinstance(value.get(key), str) or not value[key] for key in ('unit', 'item'))):
        raise ValueError('cook requires a canonical package and completed item owner')
    return {**value, 'package': package}


def author_units(packages, *, checkout, dependencies=(), source_context=None):
    """@cc [owner:fontanierh,label:correctness] per-package-sealed-cook-declarations
    Each selected finished package MUST feed a distinct source cook and sealed
    verifier. Every supplied transitive native dependency MUST be staged explicitly.
    A supplied source context MUST preserve the actual global cook code, compiled
    modules, source Config and runtime Data inputs with collision-free path bindings.
    Raw native CB bytes MUST remain NativeCookRecord; cook-tree transport metadata
    MUST NOT issue source authority. Only the private engine MAY derive source keys
    and receipts. Declaration MUST NOT inspect generated Content or launch tools.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout).resolve()
    def references(values):
        rows = values.items() if isinstance(values, dict) else ((None, value) for value in values)
        result = {}
        for key, value in rows:
            row = _reference(value, key)
            if row['package'] in result:
                raise ValueError('duplicate finished cook package')
            result[row['package']] = row
        return result
    selected, shared = references(packages), references(dependencies)
    all_refs = dict(shared)
    for package, row in selected.items():
        if package in all_refs and all_refs[package] != row:
            raise ValueError('ambiguous finished cook package')
        all_refs[package] = row
    cpp = [WORKER_ROOT + path for path in WORKER_FILES]
    scanner = ImportScanner()
    code = {SCRIPT, PROJECT, *cpp}
    for helper in (SCRIPT, 'platform/studio/atelier/build_v2/protocol.py',
                   'platform/studio/atelier/build_v2/recipe_job.py',
                   'platform/studio/atelier/build_v2/unreal_tool_ops.py',
                   'platform/studio/atelier/build_zen.py', 'platform/studio/atelier/build_cook.py'):
        code.update(path.relative_to(root).as_posix() for path in scanner.local_imports(
            root / helper, (root / 'platform/studio', root / 'platform/harness')))
    context_inputs, context_paths = [], {}
    if source_context is not None:
        context = deepcopy(source_context)
        recipe = context.get('params', {}).get('recipe', {})
        if (context.get('op') != {'kind': 'unreal.cook.produce', 'version': '1'}
                or context.get('script') != SCRIPT or context.get('params', {}).get('project') != PROJECT
                or recipe.get('version') != 1 or recipe.get('commands') != [] or recipe.get('verify') is not None
                or not isinstance(recipe.get('paths'), dict) or not isinstance(context.get('inputs'), list)):
            raise ValueError('source cook requires the exact authored global source context')
        names = set()
        for incoming in context['inputs']:
            name = incoming.get('name')
            if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)
                    or name in names or incoming.get('role') != 'content'):
                raise ValueError('source context input names must be unique content roles')
            names.add(name)
            incoming['name'] = 'context_' + name
            context_inputs.append(incoming)
        for path, value in recipe['paths'].items():
            if (not isinstance(path, str) or path.startswith('/')
                    or any(p in ('', '.', '..') for p in path.split('/'))
                    or not isinstance(value, str) or not value.startswith('inputs/')
                    or any(p in ('', '.', '..') for p in value.split('/'))):
                raise ValueError('source context requires canonical explicit input paths')
            parts = value.split('/')
            if len(parts) < 2 or parts[1] not in names:
                raise ValueError('source context path has no declared input')
            parts[1] = 'context_' + parts[1]
            context_paths[path] = '/'.join(parts)
        code.update(context['code'])
    units, staged, slots, outputs = [], {}, {}, {}
    for package in sorted(selected):
        required = set(shared) | {package}
        visiting = set()
        def visit(name):
            if name in visiting:
                raise ValueError('cyclic native cook dependency')
            visiting.add(name)
            for dependency in all_refs[name].get('dependencies', ()):
                if dependency not in all_refs:
                    raise ValueError('missing transitive native cook dependency: ' + dependency)
                required.add(dependency)
                visit(dependency)
            visiting.remove(name)
        for name in sorted(required):
            visit(name)
        name = hashlib.sha256(package.encode()).hexdigest()
        producer, verifier = 'unreal.cook.source.' + name, 'unreal.cook.package.' + name
        record = 'records/' + name + '.cb'
        inputs, paths = [], {}
        for index, dependency in enumerate(sorted(required)):
            slot = 'native_' + str(index)
            reference = all_refs[dependency]
            inputs.append({'role': 'content', 'name': slot, 'source': {
                'kind': 'item', 'unit': reference['unit'], 'item': reference['item']},
                'whole': 'The stock cooker consumes the complete finished native package and every declared sidecar.'})
            relative = dependency.removeprefix('/Game/')
            extension = '.umap' if reference.get('class') == 'Map' or '/Maps/' in dependency else '.uasset'
            for suffix in (extension, *SIDECARS):
                paths['games/yorimichi/unreal/Content/' + relative + suffix] = (
                    'inputs/' + slot + '/content/Game/' + relative + suffix)
        for path, value in context_paths.items():
            if any(path == present or path.startswith(present + '/') or present.startswith(path + '/') for present in paths):
                raise ValueError('source context path overlaps a selected native package: ' + path)
            paths[path] = value
        inputs.extend(deepcopy(context_inputs))
        recipe = {'version': 1, 'commands': [], 'paths': paths, 'verify': None,
                  'outputs': [{'path': record, 'kind': 'file', 'file': record, 'required': True},
                              {'path': COOK_ROOT, 'kind': 'tree', 'file': 'cook-root.tree.tar', 'required': True}]}
        units.append({'id': producer, 'op': {'kind': 'unreal.cook.produce', 'version': '1'},
            'script': SCRIPT, 'code': sorted(code), 'inputs': inputs,
            'params': {'project': PROJECT, 'packages': [package], 'record_outputs': {package: record},
                       'cook_root': COOK_ROOT, 'recipe': recipe},
            'outputs': [{'id': 'record', 'logical_path': package, 'class': 'NativeCookRecord',
                         'destination': 'store', 'files': [{'path': record, 'required': True}]},
                        {'id': 'metadata', 'logical_path': package + '/cook-metadata', 'class': 'Data',
                         'destination': 'store', 'files': [{'path': 'cook-root.tree.tar', 'required': True}]}]})
        units.append({'id': verifier, 'op': {'kind': 'unreal.cook.package', 'version': '1'},
            'script': VERIFY, 'code': sorted([VERIFY, *cpp]),
            'inputs': [{'role': 'content', 'name': 'record', 'source': {
                'kind': 'item', 'unit': producer, 'item': 'record'}}],
            'params': {'package': package, 'mode': 'restore', 'settings': []},
            'outputs': [{'id': 'package', 'logical_path': package, 'class': 'CookedPackage',
                         'destination': 'external', 'files': []}]})
        staged[producer] = {row['name']: 'inputs/' + row['name'] for row in inputs}
        staged[verifier] = {'record': 'inputs/record'}
        slots.update({row['name']: False for row in inputs})
        slots['record'] = False
        outputs[package] = {'unit': verifier, 'item': 'package', 'package': package}
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': outputs}
