"""Native bodies for one character's merged adventure move set, one declared package (or record) per job.

Scripts/import_adventure_moveset.py is an import-time monolith; these bodies never run its top level. They take
its original function definitions (speed_blend, the Rig/equipment geometry) by name from the keyed source and
execute only those, with the module globals the original computes, rebuilt from declared inputs:
``args.action`` selects
- ``compression``: the shared /Game/Japan/Animation/CharacterCompression (animation_compression.apply_to);
- ``clip``: one A_<Clip> finished from its raw import (root motion off, the shared compression);
- ``blend``: one BS_<Name>Adventure<Title> 1D speed blend;
- ``moveset``: the merged UAdventureMoveSet, a copy of the base with the adventure moves;
- ``record``: the move record (Content/Data/<id>/adventure.json), a JsonData output from native poses.
"""
import ast
import importlib.util
import json
import math
from pathlib import Path
import re
import sys

ORIGINAL = 'games/yorimichi/unreal/Scripts/import_adventure_moveset.py'
COMPRESSION_SCRIPT = 'games/yorimichi/unreal/Scripts/animation_compression.py'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
FUNCTIONS = ('ends', 'speed_blend', 'sub', 'add', 'mul', 'dot', 'cross', 'unit', 'apply', 'apply_t', 'compose',
             'compose_t', 'frame', 'Rig', 'turn', 'align', 'fitted', 'transform', 'record_of', 'glider', 'equipment')
PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
RECORD = 'data/adventure.json'


def _package(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical declared /Game package')
    return value


def _selected(context, slot):
    expected = None
    if isinstance(slot, dict) and set(slot) == {'derived_native'}:
        binding = slot['derived_native']
        rows = binding.get('items', {}).get('derived_items', {}).get('members')
        if (not isinstance(rows, list) or len(rows) != 1
                or not isinstance(rows[0], dict) or not isinstance(rows[0].get('slot'), str)):
            raise ValueError('Move-set native selection must resolve exactly one actual member')
        expected, slot = _package(binding['package']), rows[0]['slot']
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared move-set input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Move-set native input must be exactly one declared package: ' + slot)
    actual = _package(packages[0])
    if expected is not None and actual != expected:
        raise ValueError('Move-set selected native package differs from its declared identity')
    return actual


def _load(unreal, context, slot, cls=None):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or asset.get_path_name().split('.', 1)[0] != package or (cls is not None and not isinstance(asset, cls)):
        raise ValueError('Declared move-set input did not load as expected: ' + package)
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared move-set data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Move-set data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.name != name or path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError(f'Move-set data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    """{name: slot}: a keyed slot map, or the provider's resolved derived_items {root, members: [{piece, slot}]}."""
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Move-set derived roster is unresolved')
        roster = {r['piece']: r['slot'] for r in rows}
        if len(roster) != len(rows):
            raise ValueError('Duplicate move-set derived member')
        return roster
    if not isinstance(value, dict):
        raise ValueError('Move-set roster must be a slot map')
    return dict(value)


def _fresh(unreal, package):
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('Move-set destination must be fresh: ' + package)


def _owns(context, package):
    if list(context.outputs) != [_package(package)]:
        raise ValueError('Move-set job owns exactly its declared package: ' + package)


def original(context, **namespace):
    """The original importer's named function definitions, executed alone with the given module globals."""
    path = Path(context.job_dir) / ORIGINAL
    if path.is_symlink() or not path.is_file():
        raise ValueError('The original move-set importer is not staged keyed code')
    tree = ast.parse(path.read_text(), str(path))
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in FUNCTIONS]
    if sorted(node.name for node in nodes) != sorted(FUNCTIONS):
        raise ValueError('The original move-set importer lacks a required definition')
    namespace.setdefault('math', math)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace


def _compression_module(context):
    path = Path(context.job_dir) / COMPRESSION_SCRIPT
    if path.is_symlink() or not path.is_file():
        raise ValueError('The original compression helper is not staged keyed code')
    spec = importlib.util.spec_from_file_location('atelier_animation_compression', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sources(context, args):
    config = _data(context, args['export'], 'export.json')
    reference = next(c for c in _data(context, args['reference_export'], 'export.json')['characters'] if c['name'] == 'Reference')
    return config, reference


def compression(context, unreal, args):
    """The shared compression settings, made by the original apply_to (its sequence assignment discarded)."""
    _owns(context, COMPRESSION)
    _fresh(unreal, COMPRESSION)
    module = _compression_module(context)
    class Discard:
        def set_editor_property(self, name, value):
            if name != 'bone_compression_settings':
                raise ValueError('Unexpected compression assignment')
    module.apply_to(Discard())
    settings = module._settings
    if settings is None or settings.get_path_name().split('.', 1)[0] != COMPRESSION:
        raise ValueError('Compression settings were not created at ' + COMPRESSION)
    if settings.get_editor_property('error_threshold') != .0001:
        raise ValueError('Compression settings differ from the original threshold')
    return settings


def clip(context, unreal, args):
    """import_adventure_moveset.fbx's finishing, on a duplicate of the declared raw import."""
    params = context.params
    destination = _package(params['destination'])
    _owns(context, destination)
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'])
    settings = _load(unreal, context, args['compression'])
    if settings.get_path_name().split('.', 1)[0] != COMPRESSION:
        raise ValueError('Clip compression input is not the shared CharacterCompression')
    _fresh(unreal, destination)
    sequence = library.duplicate_asset(raw.get_path_name().split('.', 1)[0], destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_path_name().split('.', 1)[0] != destination:
        raise ValueError('Clip duplicate failed: ' + destination)
    if sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Clip is not on the declared skeleton: ' + destination)
    if 'frames' not in args:
        # A derived member: its frames and rate are its own selected member's metadata.
        entry = _data(context, args['meta'], 'meta.json')
        if entry['name'] != args['name'] or entry['kind'] != args['kind'] or entry['fps'] != args['fps']:
            raise ValueError('Clip rate or identity differs from its declared group: ' + args['name'])
        args = {**args, 'frames': entry['frames']}
    length = sequence.get_editor_property('sequence_length')
    if abs(length - args['frames'] / args['fps']) >= .002:
        raise ValueError(f'Clip length {length} differs from {args["frames"]} frames at {args["fps"]} fps')
    sequence.set_editor_property('enable_root_motion', False)
    module = _compression_module(context)
    module._settings = settings   # the declared shared owner: apply_to only assigns it
    module.apply_to(sequence)
    def validate():
        if (sequence.get_editor_property('enable_root_motion')
                or sequence.get_editor_property('bone_compression_settings') != settings):
            raise ValueError('Clip finishing did not persist: ' + destination)
    validate()
    if not library.save_loaded_asset(sequence, False):
        raise ValueError('Clip save failed: ' + destination)
    validate()
    return sequence


def blend(context, unreal, args):
    destination = f"{_package(args['dest'])}/{args['name']}"
    _owns(context, destination)
    _fresh(unreal, destination)
    config, reference = _sources(context, args)
    size = config['body'] / config['reference_scale']
    samples = reference['moves']['blends'][args['kind']]
    clips = _roster(args['clips'])
    if any(sample['clip'] not in clips for sample in samples):
        raise ValueError('A blend sample has no declared finished clip')
    skeleton = _load(unreal, context, args['skeleton'])
    namespace = original(context, U=unreal, E=unreal.EditorAssetLibrary, AT=unreal.AssetToolsHelpers.get_asset_tools(),
                         DEST=args['dest'])
    result = namespace['speed_blend'](args['name'], skeleton, [_load(unreal, context, clips[s['clip']]) for s in samples],
                                      [round(s['speed'] * size, 1) for s in samples], [s['rate'] for s in samples])
    if result.get_path_name().split('.', 1)[0] != destination:
        raise ValueError('Blend created outside its declared package')
    return result


def _clips(unreal, context, args):
    clips = {name: _load(unreal, context, slot) for name, slot in _roster(args['clips']).items()}
    clips.update({'Own' + name: _load(unreal, context, slot) for name, slot in _roster(args['own']).items()})
    return clips


def _own(unreal, context, args, clips, name):
    if args['is_donor']:
        slot = args['donor'].get(name)
        sequence = _load(unreal, context, slot) if slot else None
    else:
        sequence = clips.get('Own' + name)
    if sequence is None:
        raise ValueError(f'no donor clip {name}')
    return sequence


def _timing(unreal, context, args, clips):
    own_timing, actions = {}, {}
    for action, timing in args['donor_spec']['actions'].items():
        timing = dict(timing)
        clip_name = timing.pop('clip')
        actions[action] = sequence = _own(unreal, context, args, clips, clip_name)
        length = round(sequence.get_editor_property('sequence_length'), 4)
        own_timing[action] = {'clip': clip_name, 'length': length, 'loop': False, 'root': 'keep', 'rate': 1., 'start': 0.,
                              'end': length, 'blend': .05, 'active': [], 'guard': [], 'input': -1, 'cancel': -1, 'idle': -1,
                              'bind': -1, 'unbind': -1, **timing}
    return own_timing, actions


def moveset(context, unreal, args):
    """The merged definition exactly as the original sets it, on a fresh copy of the declared base."""
    target = _package(args['target'])
    _owns(context, target)
    library = unreal.EditorAssetLibrary
    config, reference = _sources(context, args)
    roster = next(c for c in _data(context, args['roster'], 'reference.json')['characters'] if c['name'] == 'Reference')
    size = config['body'] / config['reference_scale']
    moves = reference['moves']
    gaits = [round(s['speed'] * size, 1) for s in moves['blends']['locomotion']]
    clips = _clips(unreal, context, args)
    plain = {name: sequence for name, sequence in clips.items() if not name.startswith('Own')}
    actions = {'Idle': plain[reference['roles']['idle']]}
    actions.update({action: plain[entry['clip']] for action, entry in roster['moves']['actions'].items()})
    donor = args['donor_spec']
    actions['DoubleJump'] = _own(unreal, context, args, clips, donor['double_jump'])
    _, timed = _timing(unreal, context, args, clips)
    actions.update(timed)
    base_definition = _load(unreal, context, args['base'])
    if base_definition.get_path_name().split('.', 1)[0] != args['base_package']:
        raise ValueError('Move-set base differs from adventure.toml')
    _fresh(unreal, target)
    definition = library.duplicate_asset(args['base_package'], target)
    if definition is None or definition.get_path_name().split('.', 1)[0] != target:
        raise ValueError(f'{args["base_package"]} could not be copied')
    for key in ('mesh', 'rest_ankle_heights', 'sole_height', 'camera_height', 'skate_bones', 'skate_board_scale'):
        definition.set_editor_property(key, base_definition.get_editor_property(key))
    for name in donor['gestures']:
        if 'Own' + name in clips:
            actions.setdefault(name, clips['Own' + name])
    for action, sequence in (dict(base_definition.get_editor_property('actions')) if args['keep_base_actions'] else {}).items():
        actions.setdefault(str(action), sequence)
    blends = {kind: _load(unreal, context, slot) for kind, slot in args['blends'].items()}
    for key, value in dict(locomotion=blends['locomotion'], crouching=blends['crouching'], armed_locomotion=blends['armed'],
                           armed_crouching=None, actions=actions, use_authored_movement=True, walk_speed=gaits[1],
                           jog_speed=gaits[1], run_speed=gaits[2], sprint_speed=gaits[3],
                           crouch_speed=round(moves['blends']['crouching'][-1]['speed'] * size, 1),
                           ground_dash_profile=[], air_dash_profile=[], roll_profile=[], roll_dive_takeoff=0.,
                           roll_dive_touchdown=0., sword_mesh=None, sword_clips=[]).items():
        definition.set_editor_property(key, value)
    if not library.save_loaded_asset(definition, False):
        raise ValueError('Move-set save failed: ' + target)
    return definition


def record(context, unreal, args):
    """The move record, Reference's scaled to the character, with its equipment fitted from native poses."""
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (RECORD,):
        raise ValueError('The move record job owns only its JsonData output')
    config, reference = _sources(context, args)
    roster = next(c for c in _data(context, args['roster'], 'reference.json')['characters'] if c['name'] == 'Reference')
    body, size = config['body'], config['body'] / config['reference_scale']
    clips = _clips(unreal, context, args)
    own_timing, _ = _timing(unreal, context, args, clips)
    scaled = {}
    for name, entry in roster['moves']['actions'].items():
        entry = dict(entry)
        if 'path' in entry:
            entry['path'] = [[round(x * size, 2), round(y * size, 2), round(z * size, 2), yaw] for x, y, z, yaw in entry['path']]
        if 'speed' in entry:
            entry['speed'] = round(entry['speed'] * size, 1)
        scaled[name] = entry
    scaled.update(own_timing)
    params = dict(roster['moves']['params'])
    params['SwimHang'] = round(params['SwimHang'] * size, 2)
    params['BodyScale'] = body
    params['TwoHandedGuard'] = 1
    meshes = {_selected(context, slot) for slot in args['equipment']}
    wanted = {item['mesh'] for item in roster['moves']['equipment'].values() if item.get('mesh')}
    if not wanted <= meshes:
        raise ValueError('Equipment meshes are not all declared inputs: ' + ', '.join(sorted(wanted - meshes)))
    for slot in args['equipment']:
        _load(unreal, context, slot)
    fit = args['fit']
    namespace = original(context, U=unreal, E=unreal.EditorAssetLibrary, P=unreal.AnimPoseExtensions,
                         AT=unreal.AssetToolsHelpers.get_asset_tools(), ROSTER=roster, BODY=body, SIZE=size, FIT=fit,
                         CARRY=fit.get('carry', {}), PUSH=fit.get('push', {}), TILT=fit.get('tilt', {}),
                         YAW=fit.get('yaw', {}), MOUNT=fit.get('mount', 0.), CROUCH=fit.get('crouch', {}))
    rig, P = namespace['Rig'], unreal.AnimPoseExtensions
    names = {**reference['skate'], 'pelvis': 'Waist'}
    reference_skeleton, skeleton = _load(unreal, context, args['reference_skeleton']), _load(unreal, context, args['skeleton'])
    glide = roster['moves']['actions']['Glide']['clip']
    reference_glide = _load(unreal, context, args['reference_glide'])
    if reference_glide.get_path_name().split('.', 1)[0] != roster['clips'][glide]['path'].split('.', 1)[0]:
        raise ValueError('Reference glide input differs from the roster')
    options = unreal.AnimPoseEvaluationOptions()
    reference_rig, wearer = rig(reference_skeleton, names), rig(skeleton, {})
    gear, checks = namespace['equipment'](reference_rig, wearer, (
        rig(reference_skeleton, names, P.get_anim_pose_at_time(reference_glide, 0., options)),
        rig(skeleton, {}, P.get_anim_pose_at_time(clips[glide], 0., options))))
    body_check = wearer.at('pelvis')[2] / reference_rig.at('pelvis')[2]
    if max(checks['glider']['grip_miss_cm']) >= 6.:
        raise ValueError(f'the glider bar misses the hands: {checks["glider"]}')
    if abs(body_check - body) >= .02:
        raise ValueError(f'the reference poses disagree with the export: {body_check} {body}')
    return {RECORD: {'actions': scaled, 'params': params, 'equipment': gear}}


ACTIONS = {'compression': compression, 'clip': clip, 'blend': blend, 'moveset': moveset, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-adventure-moveset-bodies
    Each job MUST author exactly its declared package (or JsonData record) from declared
    inputs: the original importer's named definitions run alone with globals rebuilt
    from declared data, never its top level. Finished clips MUST be fresh duplicates of
    their raw imports on the declared skeleton with the shared compression owner; the
    merged definition MUST be a fresh copy of the declared base with the original fields.
    """
    import unreal
    args = context.params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported move-set body action')
    if args['action'] == 'clip':
        if context.params.get('op') != 'finish' or context.params.get('kind') != 'animation':
            raise ValueError('A clip is finished by unreal.finish(animation)')
    elif set(context.params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected move-set author parameters')
    return ACTIONS[args['action']](context, unreal, args)
