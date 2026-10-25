"""Replace each playable character_pawn.py target by a Blueprint author unit and a JSON registration row.

The values come from the committed character.toml through assets/characters/pipeline/definition.py, computed
exactly as Scripts/character_pawn.py computes them; that script's top level (an import-time monolith) never runs.
``world/pawn_v2.py`` authors BP_<Name> (unreal.author, class Blueprint) from the character's merged move set
NativeItem and its adventure.json data Item. ``world/character_registration_v2.py`` writes
Content/Data/<id>/character.json only after the Blueprint Item exists. Callers pass the producers as
``natives``: {definition package: {unit, item, dependencies?}, adventure.json checkout path: {unit, item, root?}},
where ``root`` is an optional explicit ROOT binding {archive_member, name}; a missing one refuses.
"""
import importlib.util
import json
from pathlib import Path
import sys

from v2_texture_units import SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/pawn_v2.py'
REGISTRATION = GAME + '/world/character_registration_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/character_pawn.py'
PIPELINE = GAME + '/assets/characters/pipeline'
CONTENT = GAME + '/unreal/Content'
SOLE = 0.65   # character_pawn.SOLE: the export puts the soles this far under the floor (pipeline/rig.py)
PARENT_MODULE = 'Yorimichi'   # AMoverCharacter: Source/Yorimichi/MoverCharacter.h


def _definition(checkout):
    path = Path(checkout) / PIPELINE / 'definition.py'
    spec = importlib.util.spec_from_file_location('v2_pawn_definition', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault('v2_pawn_definition', module)
    spec.loader.exec_module(module)
    return module


def object_path(package):
    return f"{package}.{package.rsplit('/', 1)[1]}"


def values(character):
    """character_pawn.py's DEFAULTS, COMPONENTS and registration record for one loaded character."""
    if not (character.playable and character.plays):
        raise Unsupported(f'{character.id}: a pawn is for a playable mover')
    game = character.game
    definition = object_path(character.adventure['definition'])
    cloth = game['cloth_teleport'] or [0.0, 0.0]
    defaults = {
        'character_id': character.id,
        'display_name': character.toml['display_name'],
        'definition_path': definition,
        'bike_rig': game['bike_rig'],
        'skate_clothing_clearance': float(game['skate_clothing_clearance']),
        'skate_collision_hull_directions': int(game['skate_hull_directions']),
        'leg_scaled_sailboat': bool(game['leg_scaled_sailboat']),
        'cloth_teleport_distance': float(cloth[0]),
        'cloth_teleport_rotation': float(cloth[1]),
        'hair_spring_morphs': [str(m) for m in game['hair_spring_morphs']],
        'seat_corrective_prefix': game['seat_correctives'],
    }
    if len(defaults['hair_spring_morphs']) not in (0, 2):
        raise Unsupported(f'{character.id}: hair_spring_morphs is [forward, sideways]')
    half = float(game['half_height'])
    components = {
        'capsule_component': {'capsule_radius': float(game['capsule_radius']), 'capsule_half_height': half},
        'character_movement': {'crouched_half_height': float(game['crouched_half_height'])},
        'mesh': {'relative_location': {'unreal_type': 'Vector', 'args': [0.0, 0.0, -(half + SOLE)]}},
    }
    blueprint = f'{character.unreal_path}/BP_{character.name}'
    if character.pawn != object_path(blueprint) + '_C':
        raise Unsupported(f'{character.id}: tools name another pawn class {character.pawn}')
    record = {
        'name': character.toml['display_name'],
        'id': character.id,
        'class': character.pawn,
        'definition': definition,
        'build_step': f"unreal.{character.id.replace('-', '_')}_pawn",
        'default': bool(game['default']),
        'aliases': list(game['aliases']),
    }
    return blueprint, defaults, components, record


def _check(row, character, blueprint):
    commands = row['commands']
    data = f'{CONTENT}/Data/{character.id}/character.json'
    if (len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('env') != [['CHARACTER', character.id]] or commands[0].get('args')
            or row['products'] or row['outputs'] != [CONTENT + blueprint.removeprefix('/Game') + '.uasset', data]):
        raise Unsupported(f'{row["id"]}: pawn row differs from the original character_pawn.py target')


def _native(natives, key, fields):
    ref = natives.get(key)
    if (not isinstance(ref, dict) or not {'unit', 'item'} <= set(ref) <= fields
            or not all(isinstance(ref[k], str) and ref[k] for k in ('unit', 'item'))):
        raise Unsupported(f'missing exact native Item for {key}')
    return ref


def _closure(natives, roots):
    seen, order, stack = set(roots), [], list(reversed(roots))
    while stack:
        package = stack.pop()
        for dependency in _native(natives, package, {'unit', 'item', 'package', 'dependencies'}).get('dependencies', []):
            if not isinstance(dependency, str) or not dependency.startswith('/Game/'):
                raise Unsupported(f'invalid native dependency of {package}')
            if dependency not in seen:
                seen.add(dependency); order.append(dependency); stack.append(dependency)
    return order


def _module(checkout):
    project = json.loads((Path(checkout) / GAME / 'unreal/Yorimichi.uproject').read_text())
    for module in project['Modules']:
        if module['Name'] == PARENT_MODULE:
            return {'name': module['Name'], 'kind': module['Type'], 'loading_phase': module['LoadingPhase']}
    raise Unsupported('project descriptor has no AMoverCharacter module')


def author_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] authored-c3-playable-pawns
    Each original character_pawn.py target MUST become exactly one Blueprint author
    unit owning only BP_<Name> and one registration row writing only its character.json,
    which consumes the produced Blueprint Item. Values MUST come from the committed
    definition exactly as the original computes them; the move set and move record MUST
    be explicit producer Items with complete native dependencies. Generated content is
    never scanned and the original top-level script never runs.
    """
    from atelier.build import Python, Step
    from atelier.build_v2.recipe_dependencies import extract
    checkout = Path(checkout)
    definition = _definition(checkout)
    pawns = {row['id']: row for row in rows if row['id'].endswith('_pawn') and row['id'].startswith('unreal.')
             and any(command.get('script') == {'path': ORIGINAL} for command in row['commands'])}
    if not pawns:
        raise Unsupported('no original character_pawn.py targets')
    code = sorted({*_code(checkout), SCRIPT})
    module = _module(checkout)
    units, staged, slots, packages, aliases, steps, requirements = [], {}, {}, {}, {}, [], {}
    for character in definition.movers():
        if not character.playable:
            continue
        key = character.id.replace('-', '_')
        row = pawns.pop(f'unreal.{key}_pawn', None)
        if row is None:
            raise Unsupported(f'missing original pawn target for {character.id}')
        blueprint, defaults, components, record = values(character)
        _check(row, character, blueprint)
        move_set = character.adventure['definition']
        adventure_path = f'{CONTENT}/Data/{character.id}/adventure.json'
        adventure = _native(natives, adventure_path, {'unit', 'item', 'root'})
        inputs = [{'role': 'content', 'name': 'definition',
                   'source': {'kind': 'item', **{k: _native(natives, move_set, {'unit', 'item', 'package', 'dependencies'})[k]
                                                 for k in ('unit', 'item')}}},
                  {'role': 'content', 'name': 'adventure',
                   'source': {'kind': 'item', 'unit': adventure['unit'], 'item': adventure['item']}}]
        for package in _closure(natives, [move_set]):
            ref = natives[package]
            inputs.append({'role': 'content', 'name': 'native_' + package.removeprefix('/Game/').replace('/', '_'),
                           'source': {'kind': 'item', 'unit': ref['unit'], 'item': ref['item']}})
        params = {'args': {'character': character.id, 'blueprint': blueprint, 'pawn': character.pawn,
                           'definition': defaults['definition_path'], 'defaults': defaults, 'components': components,
                           'inputs': {'definition': 'definition', 'adventure': 'adventure'}},
                  'settings': []}
        if 'root' in adventure:
            root = adventure['root']
            if not isinstance(root, dict) or set(root) != {'archive_member', 'name'}:
                raise Unsupported(f'{adventure_path}: invalid ROOT binding')
            params['input_roots'] = {'adventure': dict(root)}
        unit_id = f'unreal.{key}_pawn.blueprint'
        relative = blueprint.removeprefix('/Game/')
        units.append({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
                      'code': code, 'inputs': inputs, 'params': params,
                      'outputs': [{'id': 'blueprint', 'logical_path': blueprint, 'class': 'Blueprint',
                                   'destination': 'checkout',
                                   'files': [{'path': 'content/Game/' + relative + suffix,
                                              'install_path': CONTENT + '/' + relative + suffix,
                                              'required': suffix == '.uasset'} for suffix in SIDECARS]}]})
        staged[unit_id] = {item['name']: 'inputs/' + item['name'] for item in inputs}
        slots.update({item['name']: False for item in inputs})
        packages[blueprint] = {'unit': unit_id, 'item': 'blueprint', 'package': blueprint}
        requirements[unit_id] = [dict(module)]
        uasset = checkout / CONTENT / (relative + '.uasset')
        output = checkout / CONTENT / 'Data' / character.id / 'character.json'
        registration = f'unreal.{key}_pawn.registration'
        steps.append(Step(registration,
            [Python(checkout / REGISTRATION, ('--record', json.dumps(record), '--blueprint', uasset, '--output', output))],
            inputs=[checkout / REGISTRATION, character.folder / 'character.toml', uasset], needs=[unit_id], outputs=[output],
            about=f'Content/Data/{character.id}/character.json: registers {blueprint} once it exists'))
        aliases[row['id']] = (unit_id, registration)
    if pawns:
        raise Unsupported('pawn targets without a playable definition: ' + ', '.join(sorted(pawns)))
    return {'units': units, 'staged_inputs': staged, 'content_slots': slots, 'packages': packages,
            'aliases': aliases, 'rows': extract(steps, checkout=checkout, build_root=checkout / 'build'),
            'module_requirements': requirements}
