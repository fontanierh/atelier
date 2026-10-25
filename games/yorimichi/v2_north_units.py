"""Replace unreal.north's own packages (Scripts/mountain_material.py) by native units (world/north_v2.py).

import_hidamari.py with HIDAMARI_ASSETS=HD_North* runs mountain_material.material(), which imports T_VolcanicRock,
T_NorthSnowMask, T_NorthCraterMask and T_NorthCraterFloor inline before authoring M_NorthMountains, then
rock_material (MI_NorthRockCaps) and gate_material (M_NorthGate). Here each texture is a raw import + finish with
the prelude's own properties (north_v2.split), from its actual source Item: the committed rock jpg, the
world.hidamari.north_masks product members, and the crater floor member of world.craterpark_restyle's folder.
The materials are the original functions over the finished textures. The HD_North* meshes are the city's.
Shared packages arrive as ``natives = {package: {unit, item}}``.
"""
import importlib.util
from pathlib import Path

from v2_character_units import _modules, _output
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/north_v2.py'
SCRIPTS = GAME + '/unreal/Scripts'
ORIGINAL = SCRIPTS + '/mountain_material.py'
IMPORTER = SCRIPTS + '/import_hidamari.py'
TABLE = GAME + '/tools/craterpark_textures.py'
ROCK = GAME + '/assets/environment/textures/volcanic-rock.jpg'
HIDAMARI = 'build/yorimichi/hidamari'
RESTYLE = 'build/yorimichi/craterpark/textures'
FLOOR = 'crater_floor.png'
MASKS = ('world.hidamari.north_masks', 'hidamari.north_masks')
RAW = '/Game/_Raw/Textures'
NATIVES = {'detail': '/Game/Japan/Textures/T_ground_detail', 'wind': '/Game/Japan/Materials/MPC_Wind',
           'ground': '/Game/Japan/Textures/T_ground'}
SETTINGS = ['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false']


def _body(checkout):
    spec = importlib.util.spec_from_file_location('north_v2_declaration', Path(checkout) / SCRIPT)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def _slot(package):
    return 'native_' + package.removeprefix('/Game/').replace('/', '_')


def _code_closure(checkout):
    from atelier.source_imports import ImportScanner
    root = Path(checkout)
    found = set()
    for source in (SCRIPT, ORIGINAL):
        found |= {p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
            root / source, (root / GAME / 'world', root / SCRIPTS, root / GAME / 'tools', root / 'platform/studio'))}
    return sorted({*_code(root), SCRIPT, ORIGINAL, TABLE, *found})


def _rows(rows, checkout):
    by_id = {row['id']: row for row in rows}
    north = by_id.get('unreal.north')
    commands = north and north['commands']
    if (not north or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': IMPORTER}
            or [list(e) for e in commands[0].get('env', [])] != [['HIDAMARI_ASSETS', 'HD_North*']]):
        raise Unsupported('unreal.north differs from the original import_hidamari.py HD_North* target')
    importer = (Path(checkout) / IMPORTER).read_text()
    for call in ('mountain_material()', 'rock_material(mountain_mat)', 'gate_material()'):
        if call not in importer:
            raise Unsupported('import_hidamari.py no longer calls ' + call)
    declared = {i['path'] for i in north['inputs']}
    masks = by_id.get(MASKS[0])
    products = [i for i, p in enumerate(masks['products'] if masks else []) if p['id'] == MASKS[1]]
    if len(products) != 1 or masks['products'][products[0]]['optional_paths']:
        raise Unsupported('world.hidamari.north_masks must own exactly one complete hidamari.north_masks product')
    index = products[0]
    members = {str(p): f'products/{index}-{j}.tree.tar' for j, p in enumerate(masks['products'][index]['paths'])}
    restyle = by_id.get('world.craterpark_restyle')
    if not restyle or [str(p) for p in restyle['outputs']] != [RESTYLE]:
        raise Unsupported('world.craterpark_restyle no longer publishes exactly its textures folder')
    wanted = {f'{HIDAMARI}/north_{key}{suffix}' for key in ('snow', 'crater') for suffix in ('.png', '.json')}
    if not wanted <= set(members) or not wanted | {f'{RESTYLE}/{FLOOR}', ROCK} <= declared:
        raise Unsupported('unreal.north sources differ from their actual producer members')
    return f'product{index}', members


def north_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] original-north-material-units
    Each North texture MUST be a raw import + finish of its actual source Item
    member with exactly mountain_material's own prelude properties. The
    materials MUST be the original functions over finished textures and
    declared metadata Items, with their complete read-only package closure and
    every shared native package explicit. No original top level, generated
    discovery, fixed hash or graph rewrite is permitted.
    """
    natives = natives or {}
    missing = [p for p in NATIVES.values() if not isinstance(natives.get(p), dict) or not {'unit', 'item'} <= set(natives[p])]
    if missing:
        raise Unsupported('North needs the shared native packages: ' + ', '.join(missing))
    mask_item, members = _rows(rows, checkout)
    specs, _ = _body(checkout).split((Path(checkout) / ORIGINAL).read_bytes())
    sources = {
        f"str(yori.ASSETS / '{ROCK.removeprefix(GAME + '/assets/')}')": ({'kind': 'file', 'path': ROCK}, None, None),
        **{f"str(yori.OUT / 'hidamari/north_{key}.png')": (
            {'kind': 'item', 'unit': MASKS[0], 'item': mask_item},
            {'archive_member': members[f'{HIDAMARI}/north_{key}.png'], 'name': f'north_{key}.png'}, None)
           for key in ('snow', 'crater')},
        'str(floor_png)': ({'kind': 'item', 'unit': 'world.craterpark_restyle', 'item': 'output0'},
                           {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}, FLOOR)}
    absolute = Path(checkout) / ROCK
    if absolute.is_symlink() or not absolute.is_file():
        raise Unsupported('missing committed volcanic rock source')
    ops_code, code = list(_code(checkout)), _code_closure(checkout)
    editor = _modules(checkout, [])[0]
    units, staged, owned, requirements = [], {}, {}, {}

    def add(unit, inputs, roots=None, *, package=None, item_id='asset', closure=()):
        if roots:
            unit['params']['input_roots'] = roots
        unit['inputs'] = inputs
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if package:
            requirements[unit['id']] = editor
            owned[package] = {'unit': unit['id'], 'item': item_id, 'package': package,
                              'dependencies': [dict(owned.get(p) or {**natives[p], 'package': p}) for p in closure]}

    for spec in specs:
        if spec['filename'] not in sources:
            raise Unsupported('mountain_material imports an undeclared texture source: ' + spec['filename'])
        source, root, member = sources[spec['filename']]
        name, package = spec['name'], spec['package']
        raw_id, raw_package = 'unreal.north.texture.raw.' + name, f'{RAW}/{name}'
        params = {'op': 'raw_import', 'kind': 'texture', 'source': 'source', 'destination': raw_package}
        if member:
            params['source_member'] = member
        add({'id': raw_id, 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'params': params, 'outputs': [_output('raw_texture', raw_package, 'RawTexture', store=True)]},
            [{'role': 'content', 'name': 'source', 'source': source}], {'source': root} if root else None)
        add({'id': 'unreal.north.texture.' + name, 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': OPS,
             'code': ops_code, 'params': {'op': 'finish', 'kind': 'texture', 'source': 'raw', 'destination': package,
                                          'package_sources': {'raw': raw_package}, 'properties': dict(spec['properties'])},
             'outputs': [_output('texture', package, 'Texture')]},
            [_item('raw', raw_id, 'raw_texture')], package=package, item_id='texture')
    textures = [spec['package'] for spec in specs]
    mountains = '/Game/Japan/Materials/M_NorthMountains'
    closure = [*textures, NATIVES['detail'], NATIVES['wind']]
    refs = {p: owned.get(p) or natives[p] for p in closure}
    add({'id': 'unreal.north.material.M_NorthMountains', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
         'code': code, 'params': {'args': {
             'action': 'mountains', 'textures': {spec['name']: _slot(spec['package']) for spec in specs},
             'natives': {key: _slot(NATIVES[key]) for key in ('detail', 'wind')},
             'snow': 'snow', 'crater': 'crater', 'restyle': 'restyle', 'floor': FLOOR}, 'settings': list(SETTINGS)},
         'outputs': [_output('asset', mountains, 'Material')]},
        [*(_item(_slot(p), refs[p]['unit'], refs[p]['item']) for p in closure),
         _item('snow', MASKS[0], mask_item), _item('crater', MASKS[0], mask_item),
         _item('restyle', 'world.craterpark_restyle', 'output0')],
        {'snow': {'archive_member': members[f'{HIDAMARI}/north_snow.json'], 'name': 'north_snow.json'},
         'crater': {'archive_member': members[f'{HIDAMARI}/north_crater.json'], 'name': 'north_crater.json'},
         'restyle': {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}},
        package=mountains, closure=closure)
    rock = '/Game/Japan/Materials/MI_NorthRockCaps'
    add({'id': 'unreal.north.material.MI_NorthRockCaps', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
         'code': code, 'params': {'args': {'action': 'rock', 'parent': _slot(mountains),
                                           'closure': [_slot(p) for p in closure]}, 'settings': list(SETTINGS)},
         'outputs': [_output('asset', rock, 'MaterialInstanceConstant')]},
        [_item(_slot(mountains), owned[mountains]['unit'], 'asset'),
         *(_item(_slot(p), refs[p]['unit'], refs[p]['item']) for p in closure)],
        package=rock, closure=[mountains, *closure])
    gate, ground = '/Game/Japan/Materials/M_NorthGate', NATIVES['ground']
    add({'id': 'unreal.north.material.M_NorthGate', 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
         'code': code, 'params': {'args': {'action': 'gate', 'ground': _slot(ground)}, 'settings': list(SETTINGS)},
         'outputs': [_output('asset', gate, 'Material')]},
        [_item(_slot(ground), natives[ground]['unit'], natives[ground]['item'])], package=gate, closure=[ground])
    return {'units': units, 'staged_inputs': staged, 'packages': owned, 'module_requirements': requirements}
