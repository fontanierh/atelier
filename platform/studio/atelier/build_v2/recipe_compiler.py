"""Lower recipe data into independently keyed v2 units; never execute a recipe action."""
from copy import deepcopy
from pathlib import PurePosixPath

from .controller_recipe import ControllerTarget


JOB_SCRIPT = 'platform/studio/atelier/build_v2/recipe_job.py'
NATIVE_SCRIPT = 'platform/studio/atelier/build_v2/native_tool_worker.py'


class Unsupported(ValueError):
    """A declaration needs an execution capability the compiler cannot silently omit."""


def _path(value):
    if (not isinstance(value, str) or not value or '\\' in value
            or PurePosixPath(value).is_absolute() or str(PurePosixPath(value)) != value
            or any(part in ('.', '..') for part in value.split('/'))):
        raise Unsupported(f'noncanonical recipe path: {value!r}')
    return value


def _binding(value):
    if value is None:
        return None
    if value.get('bound') is not None:
        raise Unsupported('bound callback needs an explicit receiver declaration')
    return {name: deepcopy(value[source]) for name, source in (
        ('source', 'source'), ('qualname', 'qualname'), ('line', 'line'),
        ('captures', 'closure'), ('defaults', 'defaults'), ('kwdefaults', 'kwdefaults'))}


def _command(value):
    kind = value['kind']
    if kind == 'call':
        return {'kind': 'call', 'call': _binding(value['fn'])}
    if kind in ('UnrealCompile', 'UnrealGame'):
        return {**deepcopy(value), 'kind': 'native_tool', 'tool_kind': kind}
    if kind == 'PackageArchive':
        return {'kind': 'python', 'script': _path(value['script']['path']),
                'args': deepcopy(value.get('args', [])), 'env': [], 'threads': 1}
    if kind not in ('python', 'blender'):
        raise Unsupported(f'{kind} requires its native typed execution adapter')
    script = value['script']
    if not isinstance(script, dict) or set(script) != {'path'}:
        raise Unsupported('command script must name a project source file')
    result = {'kind': kind, 'script': _path(script['path']),
              'args': deepcopy(value.get('args', [])),
              'env': deepcopy(value.get('env', [])),
              'threads': value.get('threads', 1)}
    if type(result['threads']) is not int or result['threads'] < 1:
        raise Unsupported('Blender execution requires a positive worker count')
    result['threads'] = min(result['threads'], 3)
    return result


def _under(path, root):
    return path == root or path.startswith(root + '/')


def _without_joins(rows, targets):
    """A declaration-only join is an edge list, not an executable/cacheable body."""
    joins = {row['id']: row for row in rows if not any(
        row[field] for field in ('commands', 'products', 'outputs', 'inputs', 'verify'))
        and not row.get('deferred') and not row.get('references')}

    def expand(name, seen=frozenset()):
        if name not in joins:
            return [name]
        if name in seen:
            raise Unsupported(f'cyclic declaration join {name}')
        join = joins[name]
        return [child for parent in (*join['needs'], *join['after'],
                                     *(read['producer'] for read in join['reads']))
                for child in expand(parent, seen | {name})]

    lowered = []
    for row in rows:
        if row['id'] in joins:
            continue
        row = dict(row)
        for field in ('needs', 'after'):
            row[field] = list(dict.fromkeys(child for parent in row[field] for child in expand(parent)))
        lowered.append(row)
    return lowered, tuple(dict.fromkeys(child for name in targets for child in expand(name)))


def compile_rows(rows, *, project, targets, install_roots=(), checkout=None, geometry=None):
    """@cc [owner:fontanierh,label:correctness] recipe-units-use-real-engine
    Each action MUST become its own unit with complete code, consumed source and
    upstream product identities. No old action fingerprint, stamp, source location
    or scheduler may be substituted for an engine identity. Unknown execution kinds,
    ambiguous ownership and missing producers MUST refuse rather than lose effects.
    Internal directory products use complete deterministic archives, never a sampled
    existing directory listing. Rust validates, keys, executes and publishes units.
    """
    from atelier import paths as project_paths
    from .recipe_inputs import lower_inputs, Unsupported as InputUnsupported
    checkout = project_paths.REPO if checkout is None else checkout
    geometry = geometry or {'groups': {}, 'templates': []}
    rows = deepcopy(list(rows))
    for row in rows:
        kinds = [command['kind'] for command in row['commands']]
        if 'UnrealCompile' in kinds or 'UnrealGame' in kinds:
            if not row['outputs'] and not row['products']:
                root = f'games/{project}/unreal/Binaries/Mac'
                row['outputs'] = [root]
                row['native_output_encoding'] = {root: 'mac-zip'} if 'UnrealGame' in kinds else {}
                if 'UnrealCompile' in kinds:
                    for descriptor in sorted((checkout / 'platform/engine/Plugins').rglob('*.uplugin')):
                        root = (descriptor.parent / 'Binaries/Mac').relative_to(checkout).as_posix()
                        row['products'].append({'id': row['id'] + '.' + descriptor.stem,
                                                'paths': [], 'optional_paths': [root]})
    rows, targets = _without_joins(tuple(rows), targets)
    by_name = {row['id']: row for row in rows}
    if len(by_name) != len(rows):
        raise Unsupported('duplicate recipe unit')
    if not targets or set(targets) - by_name.keys():
        raise Unsupported('selection contains an undeclared recipe unit')
    products = {}
    roots = []
    for row in rows:
        for index, product in enumerate(row['products']):
            name = product['id']
            if name in products:
                raise Unsupported(f'duplicate product: {name}')
            item = f'product{index}'
            paths = [_path(path) for path in (*product['paths'], *product['optional_paths'])]
            products[name] = (row['id'], item, paths)
            roots.extend((path, row['id'], item) for path in paths)
        for index, path in enumerate(row['outputs']):
            path = _path(path)
            if not any(_under(path, root) and owner == row['id'] for root, owner, _ in roots):
                roots.append((path, row['id'], f'output{index}'))
    units, staged, slots, errors = [], {}, {}, []
    for row in rows:
        name = row['id']
        try:
            commands = [_command(command) for command in row['commands']]
            if not commands:
                raise Unsupported('unit has no executable action')
            native = next((command for command in commands if command['kind'] == 'native_tool'), None)
            archive = any(command['kind'] == 'PackageArchive' for command in row['commands'])
            runtime = 'blender' if any(c['kind'] == 'blender' for c in commands) else 'python'
            input_row = dict(row)
            input_row.setdefault('references', [])
            input_row.setdefault('deferred', [])
            lowered = lower_inputs(input_row, rows=by_name, roots=roots, products=products, checkout=checkout)
            inputs, stage, paths = lowered['inputs'], lowered['staged'], lowered['paths']
            slots.update(lowered['slots'])
            code = sorted(set(lowered['code']) | {JOB_SCRIPT})
            outputs, emitted, covered = [], [], set()
            for index, product in enumerate(row['products']):
                files = []
                for root_index, path in enumerate((*product['paths'], *product['optional_paths'])):
                    path = _path(path)
                    filename = f'products/{index}-{root_index}.tree.tar'
                    files.append({'path': filename})
                    emitted.append({'path': path, 'kind': 'tree', 'file': filename,
                                    'required': root_index < len(product['paths'])})
                    covered.add(path)
                outputs.append({'id': f'product{index}',
                    'logical_path': f'/Game/_Build/{name}/product{index}', 'class': 'Data',
                    'destination': 'store', 'files': files})
            for index, path in enumerate(row['outputs']):
                path = _path(path)
                if any(_under(path, root) for root in covered):
                    continue
                encoding = row.get('native_output_encoding', {}).get(path)
                filename = f'outputs/{index}.' + ('mac.zip' if encoding == 'mac-zip' else 'tree.tar')
                emitted.append({'path': path, 'kind': 'tree', 'file': filename, 'required': True})
                if encoding:
                    emitted[-1]['encoding'] = encoding
                outputs.append({'id': f'output{index}', 'logical_path': f'/Game/_Build/{name}/output{index}',
                                'class': 'Data', 'destination': 'store', 'files': [{'path': filename}]})
            if not outputs:
                raise Unsupported('control action needs an explicit completed-result output')
            unit = {'id': name, 'op': {'kind': f'recipe.{runtime}', 'version': '1'},
                'script': JOB_SCRIPT, 'code': code, 'inputs': inputs,
                'params': {'recipe': {'version': 1, 'commands': commands, 'paths': paths,
                                     'outputs': emitted, 'verify': _binding(row['verify']),
                                     'deferred': lowered['deferred']}},
                'outputs': outputs}
            if native or archive:
                unit['script'] = NATIVE_SCRIPT
                unit['code'] = sorted(set(unit['code']) | {NATIVE_SCRIPT,
                    'platform/studio/atelier/build_v2/unreal_tool_ops.py'})
                unit['op']['kind'] = ('unreal.compile' if native['tool_kind'] == 'UnrealCompile'
                                     else 'unreal.game') if native else 'package.archive'
                if native:
                    project_files = list((checkout / 'games' / project / 'unreal').glob('*.uproject'))
                    if len(project_files) != 1:
                        raise Unsupported('native tool needs exactly one project descriptor')
                    unit['params'].update(project=project_files[0].relative_to(checkout).as_posix(),
                        target=native['target'], configuration=native.get('config', 'Development'))
                    unit['params']['recipe']['commands'] = []
            if name in geometry['groups']:
                from atelier.source_imports import ImportScanner
                group = geometry['groups'][name]
                contract = deepcopy(group['contract'])
                unit['output_groups'] = [contract]
                unit['params'].update(geometry_root='output/geometry', parent=contract['parent'],
                    plan_limits={key: contract[key] for key in ('max_pieces', 'max_manifest_bytes',
                                                              'max_member_bytes', 'max_total_bytes')})
                unit['params']['recipe']['geometry'] = {'source': group['source'],
                    'encoding': contract['encoding'], 'parent': contract['parent']}
                decoder = 'platform/studio/atelier/build_v2/blender_ops.py'
                closure = ImportScanner().local_imports(checkout / decoder,
                    (checkout / 'platform/studio',))
                unit['code'] = sorted(set(unit['code']) | {
                    path.relative_to(checkout).as_posix() for path in closure})
                if contract['encoding'] == 'encoded_glb':
                    encoded = 'platform/studio/atelier/encoded_glb.py'
                    unit['code'] = sorted(set(unit['code']) | {path.relative_to(checkout).as_posix()
                        for path in ImportScanner().local_imports(checkout / encoded,
                            (checkout / 'platform/studio',))})
            tools = []
            node_entries = [path for path in code if path.endswith('/bridge.cjs')]
            node_entries += [source['path'] for source in row['inputs']
                             if source['path'].endswith('/bridge.cjs')]
            for entry in dict.fromkeys(node_entries):
                frontend = entry.rsplit('/', 1)[0] + '/'
                tools.append({'kind': 'node.frontend', 'entry': entry,
                              'sources': [frontend + filename for filename in
                                          ('bridge.cjs', 'pieces.cjs', 'terrain.cjs')]})
            media_scripts = {f'games/{project}/assets/audio/footsteps/slice.py',
                             f'games/{project}/assets/audio/combat/slice.py'}
            imported = sorted(source['path'] for source in row['inputs']
                              if source['path'].startswith('build/v2-source-inputs/atelier-cache/'))
            if imported:
                for command in commands:
                    if command['kind'] in ('python', 'blender'):
                        command['env'] = [pair for pair in command['env'] if pair[0] != 'ATELIER_CACHE']
                        command['env'].append(['ATELIER_CACHE', {'path': 'build/v2-source-inputs/atelier-cache'}])
            if any(command.get('script') in media_scripts for command in commands):
                tools.append({'kind': 'media.audio', 'inputs': imported,
                              'writes': [f'build/{project}/audio/.tmp']})
            if tools:
                unit['params']['recipe']['tools'] = tools
            units.append(unit)
            staged[name] = stage
        except (Unsupported, InputUnsupported) as error:
            errors.append(f'{name}: {error}')
    if errors:
        raise Unsupported('\n'.join(errors))
    declaration = {'schema_version': 2, 'cache_version': 'v2-1', 'units': units}
    # Rust checks the complete global declaration before selecting these roots.
    return ControllerTarget(targets[0], project, declaration, staged, slots,
                            tuple(install_roots) or (f'build/{project}',),
                            tuple(geometry['templates']))


def recipe_steps(game, *, checkout, build_root):
    """Read the authored constructor graph without creating a runtime build Context."""
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    from atelier.build_cook import CookMode

    checkout, build_root = Path(checkout), Path(build_root)
    directory = checkout / 'games' / game
    projects = list((directory / 'unreal').glob('*.uproject'))
    if len(projects) != 1:
        raise Unsupported('recipe must name one project descriptor')
    context = SimpleNamespace(game=game, game_dir=directory, out=build_root / game,
        logs=build_root / game / 'logs', stamps=build_root / game / 'stamps',
        uproject=projects[0], unreal_root=None, cook_mode=CookMode.DEFAULT,
        cook_reason=None, cook_memory_gib=None, recover_cook=None, record_cook_recovery=False)
    source = directory / 'build.py'
    spec = importlib.util.spec_from_file_location(f'atelier_v2_declarations_{game}', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.steps(context)


def compile_source_prerequisites(game, *, checkout, build_root):
    """Select the real source work required by the usual package target.

    This selector is production prerequisite work, not full package completion.
    It neither creates a synthetic successful join nor adopts previous stamps.
    """
    from dataclasses import replace
    from atelier.build_products import Graph
    from .recipe_dependencies import extract
    from .recipe_external_inputs import import_external_inputs
    from atelier import paths
    import importlib.util
    from pathlib import Path
    steps = recipe_steps(game, checkout=checkout, build_root=build_root)
    selected = Graph(steps).select(('unreal.package',))
    rows = extract(selected, checkout=checkout, build_root=build_root)
    blocked = {row['id'] for row in rows if row['id'].startswith('unreal.')}
    while True:
        extra = {row['id'] for row in rows if any(parent in blocked for parent in
            (*row['needs'], *row['after'], *(read['producer'] for read in row['reads']),
             *(read['producer'] for read in row.get('references', []))))}
        if extra <= blocked:
            break
        blocked |= extra
    rows = [row for row in rows if row['id'] not in blocked]
    if any(any(command['kind'].startswith('Unreal') or command['kind'] == 'PackageArchive'
               for command in row['commands']) for row in rows):
        raise Unsupported('source prerequisite selector contains a native command')
    rows, _receipt = import_external_inputs(rows, checkout=checkout, source_cache=paths.cache_dir(create=False))
    path = Path(checkout) / 'games' / game / 'v2_geometry_templates.py'
    spec = importlib.util.spec_from_file_location('atelier_source_templates_' + game, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    geometry = module.geometry_templates(rows, checkout=checkout)
    rows = module.apply_derived(rows, geometry['derived'])
    ids = tuple(row['id'] for row in rows)
    _, actual_targets = _without_joins(rows, ids)
    marker = compile_rows(rows, project=game, targets=actual_targets, checkout=checkout,
        install_roots=(f'build/{game}',), geometry=geometry)
    return replace(marker, unit='world.source-prerequisites', selection_targets=actual_targets)


def compile_materials(game, *, checkout, build_root):
    """Compile the real shared library with individual raw, finish and graph owners."""
    from dataclasses import replace
    import importlib.util
    from pathlib import Path
    from atelier.build_products import Graph
    from .recipe_dependencies import extract
    source_steps = Graph(recipe_steps(game, checkout=checkout, build_root=build_root)).select(('world.textures',))
    rows = extract(source_steps, checkout=checkout, build_root=build_root)
    _, targets = _without_joins(rows, ('world.textures',))
    source = compile_rows(rows, project=game, targets=targets, checkout=checkout,
                          install_roots=(f'build/{game}', f'games/{game}/unreal/Content'))
    filename = Path(checkout) / 'games' / game / 'v2_native_units.py'
    spec = importlib.util.spec_from_file_location('atelier_native_units_' + game, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    native = module.shared_materials(rows, checkout=checkout)
    return replace(source, unit='unreal.materials',
        declaration={**source.declaration, 'units': [*source.declaration['units'], *native['units']]},
        staged_inputs={**source.staged_inputs, **native['staged_inputs']},
        content_slots={**source.content_slots, **native['content_slots']},
        selection_targets=native['targets'])


def compile_game(game, *, checkout, build_root, targets=('unreal.package',)):
    """Compose authored declarations; all execution remains in the v2 engine."""
    from atelier.build_products import Graph
    from .recipe_dependencies import extract

    steps = recipe_steps(game, checkout=checkout, build_root=build_root)
    selected = Graph(steps).select(targets)
    rows = extract(selected, checkout=checkout, build_root=build_root)
    from .recipe_external_inputs import import_external_inputs
    from atelier import paths
    rows, _external_receipt = import_external_inputs(rows, checkout=checkout,
        source_cache=paths.cache_dir(create=False))
    import importlib.util
    from pathlib import Path
    template_source = Path(checkout) / 'games' / game / 'v2_geometry_templates.py'
    geometry = None
    if template_source.is_file():
        spec = importlib.util.spec_from_file_location('atelier_geometry_templates_' + game, template_source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        geometry = module.geometry_templates(rows, checkout=checkout)
        rows = module.apply_derived(rows, geometry['derived'])
    return compile_rows(rows, project=game, targets=targets, checkout=checkout, geometry=geometry,
                        install_roots=(f'build/{game}', f'games/{game}/unreal/Content',
                                       f'games/{game}/unreal/Binaries'))
