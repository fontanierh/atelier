"""Pure per-package island shader declarations, over completed shared owners."""
from pathlib import Path

SCRIPT = 'games/yorimichi/world/island_materials_v2.py'
PREFIX = '/Game/Japan/Materials/'
TEXTURE = '/Game/Japan/Textures/T_CoastRock'
SIDECARS = ('.uexp', '.ubulk', '.uptnl', '.m.ubulk', '.upayload')


def material_specs():
    return [
        {'asset': 'M_ForestGround', 'factory': 'forest', 'dependencies': [
            '/Game/Japan/Textures/T_ground', '/Game/Japan/Textures/T_ground_detail']},
        {'asset': 'MI_FarForest', 'factory': 'instance', 'parent': 'M_ForestGround', 'dependencies': [PREFIX + 'M_ForestGround']},
        {'asset': 'MI_Coast', 'factory': 'coast', 'parent': 'M_ForestGround', 'dependencies': [PREFIX + 'M_ForestGround']},
        {'asset': 'M_CoastRock', 'factory': 'rock', 'dependencies': [TEXTURE]},
        {'asset': 'MI_CoastRock', 'factory': 'instance', 'parent': 'M_CoastRock', 'dependencies': [PREFIX + 'M_CoastRock']},
        {'asset': 'MI_Sand', 'factory': 'sand', 'dependencies': [PREFIX + 'M_Painted',
            '/Game/Japan/Textures/T_white', '/Game/SeeThrough/MPC_SeeThrough']},
        {'asset': 'M_Sea', 'factory': 'sea', 'dependencies': []},
    ]


def author_units(packages, *, checkout):
    """@cc [owner:fontanierh,label:correctness] individual-island-material-owners
    Each island material MUST have one native owner with the original exact graph.
    A finished coast texture and generated snow metadata MUST be actual content
    inputs, never ambient source paths or hash-pinned reuse. Parent package closure
    MUST be explicit; an instance MUST NOT recreate or dirty its readonly parent.
    No old receiving/main/cache action or native job MAY execute during declaration.
    """
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    references = {}
    for key, reference in packages.items():
        if key == 'north_snow':
            continue
        package = reference.get('package', key if key.startswith('/Game/') else None)
        if package is None:
            raise ValueError('island material input lacks its canonical package')
        if not reference.get('unit') or not reference.get('item'):
            raise ValueError('island material input lacks its completed owner')
        normalized = {**reference, 'package': package}
        if package in references:
            if references[package] != normalized:
                raise ValueError('ambiguous island material input owner')
            continue
        references[package] = normalized
    snow = packages.get('north_snow')
    if not isinstance(snow, dict) or not snow.get('unit') or not snow.get('item') or not snow.get('file'):
        raise ValueError('island forest requires the actual declared north_snow JSON item')
    source = root / SCRIPT
    code = sorted(path.relative_to(root).as_posix() for path in ImportScanner().local_imports(source,
        (root / 'games/yorimichi/world', root / 'games/yorimichi/unreal/Scripts', root / 'games/yorimichi',
         root / 'platform/studio')))
    specs = material_specs()
    by_package = {PREFIX + spec['asset']: spec for spec in specs}
    references.update({package: {'unit': 'unreal.island.material.' + spec['asset'], 'item': 'asset', 'package': package}
                       for package, spec in by_package.items()})
    def dependencies(package):
        found = set()
        def visit(current):
            for dependency in by_package[current]['dependencies']:
                if dependency in found:
                    continue
                if dependency not in references:
                    raise ValueError('missing completed island material input: ' + dependency)
                found.add(dependency)
                if dependency in by_package:
                    visit(dependency)
        visit(package)
        return sorted(found)
    units, staged, slots = [], {}, {}
    for package, spec in by_package.items():
        unit_id = references[package]['unit']
        native = {path.rsplit('/', 1)[-1]: path for path in dependencies(package)}
        inputs = [{'role': 'content', 'name': name, 'source': {'kind': 'item',
            'unit': references[path]['unit'], 'item': references[path]['item']}} for name, path in native.items()]
        args = {key: value for key, value in spec.items() if key != 'dependencies'}
        args.update(package=package, inputs=native)
        if spec['factory'] == 'forest':
            inputs.append({'role': 'content', 'name': 'north_snow', 'source': {'kind': 'item',
                           'unit': snow['unit'], 'item': snow['item']}})
            args['north_snow'] = {key: snow[key] for key in ('file', 'member') if key in snow}
        relative = package.removeprefix('/Game/')
        files = [{'path': 'content/Game/' + relative + suffix,
                  'install_path': 'games/yorimichi/unreal/Content/' + relative + suffix,
                  'required': suffix == '.uasset'} for suffix in ('.uasset', *SIDECARS)]
        units.append({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
            'code': list(code), 'inputs': inputs, 'params': {'args': args, 'settings': []},
            'outputs': [{'id': 'asset', 'logical_path': package, 'class': 'MaterialInstance' if spec['asset'].startswith('MI_')
                         else 'Material', 'destination': 'checkout', 'files': files}]})
        staged[unit_id] = {row['name']: 'inputs/' + row['name'] for row in inputs}
        slots.update({row['name']: False for row in inputs})
    if TEXTURE not in references:
        raise ValueError('island rock requires its independently finished coast texture')
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots,
            'packages': {package: references[package] for package in (*by_package, TEXTURE)}}
