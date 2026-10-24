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
    if type(result['threads']) is not int or not 1 <= result['threads'] <= 3:
        raise Unsupported('Blender execution must use the supported three-worker ceiling')
    return result


def _under(path, root):
    return path == root or path.startswith(root + '/')


def compile_rows(rows, *, project, targets, install_roots=()):
    """@cc [owner:fontanierh,label:correctness] recipe-units-use-real-engine
    Each action MUST become its own unit with complete code, consumed source and
    upstream product identities. No old action fingerprint, stamp, source location
    or scheduler may be substituted for an engine identity. Unknown execution kinds,
    ambiguous ownership and missing producers MUST refuse rather than lose effects.
    Internal directory products use complete deterministic archives, never a sampled
    existing directory listing. Rust validates, keys, executes and publishes units.
    """
    rows = tuple(rows)
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
    units, staged, slots = [], {}, {}
    for row in rows:
        name = row['id']
        try:
            commands = [_command(command) for command in row['commands']]
            if not commands:
                raise Unsupported('unit has no executable action')
            runtime = 'blender' if any(c['kind'] == 'blender' for c in commands) else 'python'
            inputs, stage, paths, incoming = [], {}, {}, set()

            def upstream(owner, item, paths_read):
                if owner == name:
                    raise Unsupported('action reads its own unpublished output')
                pair = (owner, item)
                if pair not in incoming:
                    slot = f'item{len(incoming)}'
                    inputs.append({'role': 'content', 'name': slot,
                                   'source': {'kind': 'item', 'unit': owner, 'item': item}})
                    stage[slot] = f'inputs/{slot}'
                    slots[slot] = False
                    incoming.add(pair)
                else:
                    slot = next(i['name'] for i in inputs if i['source'] == {
                        'kind': 'item', 'unit': owner, 'item': item})
                producer = by_name[owner]
                if item.startswith('product'):
                    product_index = int(item.removeprefix('product'))
                    product = producer['products'][product_index]
                    owned_roots = [*product['paths'], *product['optional_paths']]
                    archive_names = [f'products/{product_index}-{i}.tree.tar'
                                     for i in range(len(owned_roots))]
                else:
                    output_index = int(item.removeprefix('output'))
                    owned_roots = [producer['outputs'][output_index]]
                    archive_names = [f'outputs/{output_index}.tree.tar']
                for path in paths_read:
                    matches = [i for i, root in enumerate(owned_roots) if _under(path, root)]
                    if len(matches) != 1:
                        raise Unsupported(f'input {path} has no exact product-root binding')
                    index = matches[0]
                    paths[_path(owned_roots[index])] = f'{stage[slot]}/{archive_names[index]}'

            for read in row['reads']:
                if read['product'] not in products:
                    raise Unsupported(f'unknown product {read["product"]}')
                owner, item, owned = products[read['product']]
                if owner != read['producer'] or owned != read['paths']:
                    raise Unsupported('product read differs from its owning declaration')
                upstream(owner, item, owned)
            for dependency in (*row['needs'], *row['after']):
                if dependency not in by_name:
                    raise Unsupported(f'unknown prerequisite {dependency}')
                for root, owner, item in roots:
                    if owner == dependency:
                        upstream(owner, item, [root])
            code = sorted(set(map(_path, row['code'])) | {JOB_SCRIPT})
            for source in row['inputs']:
                path = _path(source['path'])
                if path in code:
                    continue
                owners = [(root, owner, item) for root, owner, item in roots if _under(path, root)]
                if owners:
                    longest = max(len(root) for root, _, _ in owners)
                    owners = {entry for entry in owners if len(entry[0]) == longest}
                    if len(owners) != 1:
                        raise Unsupported(f'ambiguous generated input {path}')
                    _, owner, item = owners.pop()
                    upstream(owner, item, [path])
                    continue
                slot = f'file{len(stage)}'
                inputs.append({'role': 'content', 'name': slot,
                    'source': {'kind': 'file', 'path': path, 'optional': bool(source['optional'])},
                    'whole': 'The original producer consumes this complete declared source.'})
                stage[slot] = f'inputs/{slot}'
                slots[slot] = False
                paths[path] = stage[slot]
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
                                     'outputs': emitted, 'verify': _binding(row['verify'])}},
                'outputs': outputs})
            staged[name] = stage
        except Unsupported as error:
            raise Unsupported(f'{name}: {error}') from error
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
    return compile_rows(rows, project=game, targets=targets,
                        install_roots=(f'build/{game}', f'games/{game}/unreal/Content',
                                       f'games/{game}/unreal/Binaries'))
