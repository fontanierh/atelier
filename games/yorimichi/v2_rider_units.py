"""Replace each Scripts/import_ride_clips.py target (unreal.<k>_bike, unreal.<k>_horse) by native units (world/rider_v2.py).

Per ride, from characters.<k>_<ride>'s complete export Product, one projector (world/rider_members_v2.py) writes each
exported clip as a FileSet member, its export entry with its FBX bytes; each selected child unpacks only its own
member, and its followers import it on the character's skeleton at the committed rider FPS and finish it as
A_<Clip> in /Game/<Rig><Ride> with the shared compression and the original length check. One record unit writes the
ride's unreal_import.json. The horse's clip roster is committed (its declared FBX outputs) and must match exactly.
``natives = {compression: {unit, item, package}, <id>: {skeleton: {unit, item, package}}}``.
"""
import ast
from pathlib import Path, PurePosixPath

from atelier.build import Call, Step
from atelier.build_v2.recipe_compiler import _binding
from atelier.build_v2.recipe_dependencies import extract
from atelier.source_imports import ImportScanner
from v2_character_units import _definition, _modules, _output
from v2_geometry_templates import LIMITS
from v2_texture_units import OPS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/rider_v2.py'
BODY = GAME + '/world/rider_members_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_ride_clips.py'
COMPRESSION_SCRIPT = GAME + '/unreal/Scripts/animation_compression.py'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
RIDERS = {'bike': GAME + '/assets/vehicles/bike/rider.py', 'horse': GAME + '/assets/horses/rider.py'}
RECIPE = 'platform/studio/atelier/build_v2/recipe_job.py'
EMITTER = 'platform/studio/atelier/build_v2/file_groups.py'
OUT = 'build/yorimichi'
RECIPE_OP = {'kind': 'recipe.python', 'version': '1'}
# import_ride_clips.fbx's FbxAnimSequenceImportData (custom_sample_rate is the export's, the committed rider FPS).
FBX = {'animation_length': {'unreal_enum': 'FBXAnimationLengthImportType.FBXALIT_EXPORTED_TIME'},
       'use_default_sample_rate': False, 'import_bone_tracks': True, 'delete_existing_morph_target_curves': True,
       'do_not_import_curve_with_zero': False, 'convert_scene': True}


def _body(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location('rider_members_declaration', root / BODY)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _call(root, name, defaults):
    function = getattr(_body(root), name); function.__defaults__ = tuple(defaults)
    row = extract([Step('members', [Call(name, function)])], checkout=root, build_root=root / 'build',
                  import_roots=(root / 'platform/studio', root / GAME / 'world'))[0]
    return {'kind': 'call', 'call': _binding(row['commands'][0]['fn'])}


def _item(name, unit, item_id):
    return {'role': 'content', 'name': name, 'source': {'kind': 'item', 'unit': unit, 'item': item_id}}


def _ref(value, label, package=None):
    if (not isinstance(value, dict) or not {'unit', 'item', 'package'} <= set(value)
            or (package is not None and value['package'] != package)):
        raise Unsupported('missing exact native Item for ' + label)
    return value


def fps(root, ride):
    """The rider's committed FPS (its export.json 'fps')."""
    found = [n.value.value for n in ast.parse((root / RIDERS[ride]).read_bytes()).body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'FPS' for t in n.targets) and isinstance(n.value, ast.Constant)]
    if len(found) != 1 or type(found[0]) is not int or found[0] <= 0:
        raise Unsupported(f'{RIDERS[ride]} no longer defines a literal FPS')
    return found[0]


def token(k, ride):
    return {'derived_items': {'root': f'build/v2-derived/ride/{k}/{ride}', 'templates': [
        {'producer': f'characters.{k}_{ride}.members.clips', 'group': 'members', 'unit_prefix': f'unreal.ride.{k}.{ride}',
         'follower': 1, 'item': 'animation'}]}}


def rider_units(rows, *, checkout, natives):
    """@cc [owner:fontanierh,label:correctness] cold-ride-clip-native-members
    Each import_ride_clips.py target MUST become, from its actual complete ride
    export Product, FileSet clip members with one selected child each and its
    raw/finish followers consuming only that member, the character's declared
    skeleton and the shared compression, plus one report unit. A committed
    roster MUST match exactly. No fake future IDs, whole-export clip consumer,
    generated scan or original top level.
    """
    root = Path(checkout).resolve()
    by_id = {row['id']: row for row in rows}
    targets = {row['id']: row for row in rows if any(c.get('script') == {'path': ORIGINAL} for c in row['commands'])}
    compression = _ref((natives or {}).get('compression'), 'the shared CharacterCompression', COMPRESSION)
    recipe_code = set()
    for source in (BODY, RECIPE, EMITTER):
        recipe_code.update(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
            root / source, (root / 'platform/studio', root / GAME / 'world')))
    recipe_code = sorted(recipe_code | {BODY})
    code = sorted({*_code(root), SCRIPT, COMPRESSION_SCRIPT, *(p.relative_to(root).as_posix() for p in ImportScanner().local_imports(
        root / COMPRESSION_SCRIPT, (root / GAME / 'unreal/Scripts', root / 'platform/studio')))})
    ops_code, editor = list(_code(root)), _modules(root, [])[0]
    units, staged, packages, aliases, requirements, templates, groups, tokens = [], {}, {}, {}, {}, [], {}, {}

    def add(unit, inputs, roots=None):
        unit['inputs'] = inputs
        if roots:
            unit['params']['input_roots'] = roots
        units.append(unit)
        staged[unit['id']] = {i['name']: 'inputs/' + i['name'] for i in inputs}
        if unit['op']['kind'] != 'recipe.python':
            requirements[unit['id']] = editor

    characters = {c.id: c for c in _definition(root).movers()}
    if not targets:
        raise Unsupported('no import_ride_clips.py targets')
    for target_id, target in sorted(targets.items()):
        env = dict(map(tuple, target['commands'][0].get('env', ())))
        ride, character = env.get('RIDE'), characters.get(env.get('RIDE_CHARACTER'))
        if (len(target['commands']) != 1 or target['commands'][0].get('kind') != 'UnrealScript' or ride not in RIDERS
                or character is None or set(env) != {'RIDE', 'RIDE_CHARACTER'}
                or target_id != f"unreal.{character.id.replace('-', '_')}_{ride}"):
            raise Unsupported(f'{target_id}: row differs from the original import_ride_clips.py target')
        k = character.id.replace('-', '_')
        producer = by_id.get(f'characters.{k}_{ride}')
        if not producer or producer['commands'][0].get('script') != {'path': RIDERS[ride]}:
            raise Unsupported(f'characters.{k}_{ride} differs from the original {RIDERS[ride]}')
        base_out = f'{OUT}/{character.output}/{ride}'
        found = [i for i, p in enumerate(producer['products']) if p['id'] == f'characters.{k}_{ride}.export']
        if (len(found) != 1 or [str(p) for p in producer['products'][found[0]]['paths']] != [f'{base_out}/export.json', f'{base_out}/fbx']
                or producer['products'][found[0]]['optional_paths']):
            raise Unsupported(f'characters.{k}_{ride} must own its complete export Product (export.json, fbx)')
        index = found[0]
        export_item, archives = f'product{index}', {'export.json': f'products/{index}-0.tree.tar', 'fbx': f'products/{index}-1.tree.tar'}
        # The horse's roster is committed: its producer declares each clip FBX.
        roster = sorted(PurePosixPath(o).stem[2:] for o in producer['outputs'] if o.startswith(f'{base_out}/fbx/A_')) or None
        dest = f"/Game/{character.game['bike_rig']}{ride.capitalize()}"
        if roster and sorted(PurePosixPath(o).stem[2:] for o in target['outputs'] if o.endswith('.uasset')) != roster:
            raise Unsupported(f'{target_id}: declared clip packages differ from the committed roster')
        rate = fps(root, ride)
        skeleton = _ref(((natives or {}).get(character.id) or {}).get('skeleton'), f'{character.id} skeleton')
        folder, parent, producer_id = f'generated/ride/{k}/{ride}', f'{character.name}_{ride}', f'characters.{k}_{ride}.members.clips'
        contract = {'id': 'members', 'root': 'files', 'root_param': 'file_root', 'manifest': 'plan.json',
                    'adapter_version': 'd2.file-set/1', 'parent': parent, 'encoding': 'file_set', 'class': 'Data',
                    'logical_namespace': f'/Internal/Ride/{k}/{ride}', **LIMITS}
        whole = _item('export', producer['id'], export_item)
        whole['whole'] = 'The complete ride export validates its rate, roster and every clip FBX before selecting members.'
        add({'id': producer_id, 'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code,
             'params': {'file_root': 'output/files', 'recipe': {'version': 1, 'verify': None,
                 'paths': {f'{base_out}/export.json': 'inputs/export/' + archives['export.json'],
                           f'{base_out}/fbx': 'inputs/export/' + archives['fbx']},
                 'commands': [_call(root, 'project', (root / base_out / 'export.json', root / base_out / 'fbx', root / folder,
                                                      rate, roster))],
                 'outputs': [{'path': folder, 'file': 'members.tree.tar', 'required': True}],
                 'file_group': {'source': folder, 'parent': parent, 'extensions': ['.json']}}},
             'outputs': [{'id': 'members', 'logical_path': f'/Internal/Ride/{k}/{ride}', 'class': 'Data', 'destination': 'store',
                          'files': [{'path': 'members.tree.tar', 'required': True}]}],
             'output_groups': [contract]}, [whole])
        groups[producer_id] = {'contract': contract, 'source': folder}
        raw_package = f'/Game/_Raw/Ride/{k}/{ride}/A_$piece'
        followers = [
            {'id': '$export.raw', 'op': {'kind': 'unreal.raw_import', 'version': '1'}, 'script': OPS, 'code': ops_code,
             'inputs': [_item('source', '$export', 'asset'), _item('skeleton', skeleton['unit'], skeleton['item'])],
             'params': {'op': 'raw_import', 'kind': 'animation', 'source': 'source', 'destination': raw_package,
                        'skeleton': 'skeleton', 'fbx': {**FBX, 'custom_sample_rate': rate},
                        'input_roots': {'source': {'archive_member': 'member.tree.tar', 'name': 'member'}}},
             'outputs': [_output('raw_animation', raw_package, 'RawAnimation', store=True)]},
            {'id': '$export.finish', 'op': {'kind': 'unreal.finish', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'inputs': [_item('raw', '$previous', 'raw_animation'), _item('skeleton', skeleton['unit'], skeleton['item']),
                        _item('compression', compression['unit'], compression['item']), _item('meta', '$export', 'asset')],
             'params': {'op': 'finish', 'kind': 'animation', 'source': 'raw', 'destination': f'{dest}/A_$piece',
                        'input_roots': {'meta': {'archive_member': 'meta.tree.tar', 'name': 'meta'}},
                        'args': {'action': 'clip', 'name': '$piece', 'fps': rate, 'meta': 'meta', 'skeleton': 'skeleton',
                                 'compression': 'compression'}},
             'outputs': [_output('animation', f'{dest}/A_$piece', 'Animation')]}]
        templates.append({'producer': producer_id, 'group': 'members', 'unit_prefix': f'unreal.ride.{k}.{ride}',
            'op': dict(RECIPE_OP), 'script': RECIPE, 'code': recipe_code, 'derive_payload': False, 'payload_slot': 'payload',
            'staged_path': 'inputs/payload', 'output_class': 'Data', 'logical_namespace': f'/Internal/Ride/{k}/{ride}/Selected',
            'files': [{'path': 'member.tree.tar', 'required': True}, {'path': 'meta.tree.tar', 'required': True}],
            'params': {'recipe': {'version': 1, 'paths': {'selected': 'inputs/payload'}, 'verify': None,
                'commands': [_call(root, 'select', (root / 'selected', root / 'member', root / 'meta', '$piece'))],
                'outputs': [{'path': 'member', 'file': 'member.tree.tar', 'required': True},
                            {'path': 'meta', 'file': 'meta.tree.tar', 'required': True}]}},
            'followers': [{'unit': unit, 'staged_inputs': {i['name']: 'inputs/' + i['name'] for i in unit['inputs']}}
                          for unit in followers]})
        clips = token(k, ride)
        record_id = f'unreal.ride.{k}.{ride}.record'
        add({'id': record_id, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
             'params': {'args': {'action': 'record', 'export': 'export', 'clips': clips}, 'settings': []},
             'outputs': [{'id': 'record', 'logical_path': f'/Internal/Ride/{k}/{ride}/Report', 'class': 'JsonData',
                          'destination': 'store', 'files': [{'path': 'data/unreal_import.json', 'required': True}]}]},
            [_item('export', producer['id'], export_item)], {'export': {'archive_member': archives['export.json'], 'name': 'export.json'}})
        tokens[target_id] = {'clips': clips, 'folder': dest, **({'roster': roster} if roster else {})}
        packages[f'{base_out}/unreal_import.json'] = {'unit': record_id, 'item': 'record'}
        aliases[target_id] = (producer_id, record_id)
    return {'units': units, 'staged_inputs': staged, 'content_slots': {i['name']: False for u in units for i in u['inputs']},
            'packages': packages, 'aliases': aliases, 'module_requirements': requirements, 'templates': templates,
            'groups': groups, 'tokens': tokens}
