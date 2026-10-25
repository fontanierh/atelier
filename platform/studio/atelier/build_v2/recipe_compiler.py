"""Lower recipe data into independently keyed v2 units; never execute a recipe action."""
from copy import deepcopy
from pathlib import PurePosixPath

from .controller_recipe import ControllerTarget


JOB_SCRIPT = 'platform/studio/atelier/build_v2/recipe_job.py'


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


def compile_rows(rows, *, project, targets, install_roots=(), checkout=None):
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
                filename = f'outputs/{index}.tree.tar'
                emitted.append({'path': path, 'kind': 'tree', 'file': filename, 'required': True})
                outputs.append({'id': f'output{index}', 'logical_path': f'/Game/_Build/{name}/output{index}',
                                'class': 'Data', 'destination': 'store', 'files': [{'path': filename}]})
            if not outputs:
                raise Unsupported('control action needs an explicit completed-result output')
            units.append({'id': name, 'op': {'kind': f'recipe.{runtime}', 'version': '1'},
                'script': JOB_SCRIPT, 'code': code, 'inputs': inputs,
                'params': {'recipe': {'version': 1, 'commands': commands, 'paths': paths,
                                     'outputs': emitted, 'verify': _binding(row['verify']),
                                     'deferred': lowered['deferred']}},
                'outputs': outputs})
            staged[name] = stage
        except (Unsupported, InputUnsupported) as error:
            errors.append(f'{name}: {error}')
    if errors:
        raise Unsupported('\n'.join(errors))
    declaration = {'schema_version': 2, 'cache_version': 'v2-1', 'units': units}
    # Rust checks the complete global declaration before selecting these roots.
    return ControllerTarget(targets[0], project, declaration, staged, slots,
                            tuple(install_roots) or (f'build/{project}',))


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


def compile_game(game, *, checkout, build_root, targets=('unreal.package',)):
    """Compose authored declarations; all execution remains in the v2 engine."""
    from atelier.build_products import Graph
    from .recipe_dependencies import extract

    steps = recipe_steps(game, checkout=checkout, build_root=build_root)
    selected = Graph(steps).select(targets)
    rows = extract(selected, checkout=checkout, build_root=build_root)
    return compile_rows(rows, project=game, targets=targets, checkout=checkout,
                        install_roots=(f'build/{game}', f'games/{game}/unreal/Content',
                                       f'games/{game}/unreal/Binaries'))
