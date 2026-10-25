"""Native bodies for unreal.fox_hunter (Scripts/import_fox_hunter.py), one declared /Game/FoxHunter owner per job.

``args.action`` selects
- ``material``: M_FoxHunter_* by the original material loop body, run alone for its own member with the declared
  finished texture in place of the loop's texture import;
- ``mesh``: SK_FoxHunter with its Skeleton and PhysicsAsset from a raw FBX skeletal import, slots bound by imported
  slot name to the derived materials, and the original bone-set and reference-pose checks;
- ``clip``: A_Fox<clip> from a raw FBX animation on the finished skeleton: its duration check, root motion, the
  reference-pose root lock and the shared compression;
- ``blend``: BS_FoxLocomotion over Idle, Creep and Run by their exported speeds;
- ``definition``: DA_FoxHunter with the mesh, blend space, clips and their FoxHunterClip entries;
- ``record``: fox_hunter/unreal_import.json, the original report, from the finished assets.
The original top level never runs.
"""
import ast
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
DEST = '/Game/FoxHunter'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_fox_hunter.py'
COMPRESSION_SCRIPT = 'games/yorimichi/unreal/Scripts/animation_compression.py'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
LOCOMOTION = ('Idle', 'Creep', 'Run')
PROBES = ('pelvis', 'head', 'hand_R', 'finger_end_1_R', 'foot_R')
RECORD = 'data/unreal_import.json'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared fox input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Fox native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls=None, package=None):
    path = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if (asset is None or _path(asset) != path or (cls is not None and not isinstance(asset, cls))
            or (package is not None and path != package)):
        raise ValueError('Declared fox input did not load as expected: ' + path)
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared fox data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Fox data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Fox data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Fox derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    raise ValueError('Fox roster must be a derived token')


def _start(unreal, context, packages):
    if sorted(context.outputs) != sorted(packages):
        raise ValueError('Fox job owns exactly its declared packages')
    for package in packages:
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            raise ValueError('Fox destination must be fresh: ' + package)


def _code(context, relative):
    path = Path(context.job_dir) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Fox keyed code is not staged: ' + relative)
    return path


def material_body(source):
    """The original loop over CONFIG['materials'], without its texture import: (statements, the asset() helper)."""
    tree = ast.parse(source)
    loops = [n for n in tree.body if isinstance(n, ast.For) and ast.unparse(n.iter) == "CONFIG['materials'].items()"]
    helpers = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'asset']
    if len(loops) != 1 or len(helpers) != 1 or ast.unparse(loops[0].target) != '(name, cfg)':
        raise ValueError('import_fox_hunter.py no longer has its one material loop')
    kept, dropped = [], []
    for statement in loops[0].body:
        names = {n.id for n in ast.walk(statement) if isinstance(n, ast.Name)}
        (dropped if 'task' in names or (isinstance(statement, ast.Assign) and ast.unparse(statement.targets[0]) == 'texture') else kept).append(statement)
    if [ast.unparse(s).split('(')[0] for s in dropped][:1] != ['task = U.AssetImportTask'] or len(dropped) != 4:
        raise ValueError('The original material texture import changed shape')
    return ast.Module(body=[*helpers, *kept], type_ignores=[])


def material(context, unreal, args):
    meta = _data(context, args['meta'], 'meta.json')
    name = meta['name']
    if name != args['name']:
        raise ValueError('Fox material member differs from its piece')
    package = f'{DEST}/{name}'
    _start(unreal, context, [package])
    # The images roster is every exported texture; the export names this material's own one.
    images = _roster(args['images'])
    if meta['texture'] not in images:
        raise ValueError('Fox material texture is not a declared fox image')
    texture = _load(unreal, context, images[meta['texture']], unreal.Texture2D, f'{DEST}/Textures/{meta["texture"]}')
    module = material_body(_code(context, ORIGINAL).read_text())
    scope = {'U': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
             'M': unreal.MaterialEditingLibrary, 'DEST': DEST, 'name': name, 'cfg': meta, 'texture': texture, 'materials': {}}
    exec(compile(module, ORIGINAL, 'exec'), scope)
    mat = scope['materials'].get(name)
    if mat is None or _path(mat) != package:
        raise ValueError('Fox material not authored at its package')
    return mat


def mesh(context, unreal, args):
    params = context.params
    destination, partners = params['destination'], params['partners']
    _start(unreal, context, [destination, partners['skeleton'], partners['physics_asset']])
    facts = _data(context, args['facts'], 'facts.json')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    asset = library.duplicate_asset(_path(raw), destination)
    skeleton = library.duplicate_asset(_path(raw.get_editor_property('skeleton')), partners['skeleton'])
    physics = library.duplicate_asset(_path(raw.get_editor_property('physics_asset')), partners['physics_asset'])
    if not isinstance(asset, unreal.SkeletalMesh) or not isinstance(skeleton, unreal.Skeleton) or not isinstance(physics, unreal.PhysicsAsset):
        raise ValueError('Fox skeletal duplicate failed: ' + destination)
    asset.set_skeleton(skeleton); asset.set_editor_property('physics_asset', physics)
    skeleton.set_editor_property('preview_skeletal_mesh', asset); physics.set_editor_property('preview_skeletal_mesh', asset)
    materials = _roster(args['materials'])
    if sorted(materials) != sorted(facts['materials']):
        raise ValueError('Fox derived materials differ from the export')
    slots = list(asset.materials)
    for slot in slots:
        key = str(slot.get_editor_property('imported_material_slot_name'))
        if key not in materials:
            raise ValueError(f'Unknown material {key}')
        slot.set_editor_property('material_interface', _load(unreal, context, materials[key], package=f'{DEST}/{key}'))
    asset.set_editor_property('materials', slots)
    editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    pending, bones = ['root'], []
    while pending:
        bone = pending.pop()
        if bone in bones:
            raise ValueError('Fox skeleton repeats a bone: ' + bone)
        bones.append(bone)
        pending.extend(str(b) for b in editor.get_bone_children(asset, bone))
    if set(bones) != set(facts['bones']):
        raise ValueError('Imported skeleton mismatch')
    pose = unreal.AnimPoseExtensions.get_reference_pose(skeleton)
    gaps = {b: (unreal.AnimPoseExtensions.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD).translation
                - unreal.Vector(*facts['rest_bones_cm'][b])).length() for b in PROBES}
    if max(gaps.values()) >= .5:
        raise ValueError(f'reference pose does not match the export space: {gaps}')
    for value in (skeleton, physics, asset):
        if not library.save_loaded_asset(value, False):
            raise ValueError('Fox skeletal save failed: ' + destination)
    return asset


def clip(context, unreal, args):
    params = context.params
    destination = params['destination']
    _start(unreal, context, [destination])
    meta = _data(context, args['meta'], 'meta.json')
    if meta['name'] != args['name'] or destination != f'{DEST}/A_Fox{meta["name"]}':
        raise ValueError('Fox clip member differs from its piece')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    settings = _load(unreal, context, args['compression'], package=COMPRESSION)
    sequence = library.duplicate_asset(_path(raw), destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Fox clip is not on the finished skeleton: ' + destination)
    if abs(sequence.get_editor_property('sequence_length') - meta['duration']) >= .001:
        raise ValueError(f'{destination}: length differs from {meta["duration"]}')
    sequence.set_editor_property('enable_root_motion', bool(meta['root_motion']))
    sequence.set_editor_property('root_motion_root_lock', unreal.RootMotionRootLock.REF_POSE)
    spec = importlib.util.spec_from_file_location('atelier_fox_compression', _code(context, COMPRESSION_SCRIPT))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module._settings = settings   # the declared shared owner: apply_to only assigns it
    module.apply_to(sequence)
    if not library.save_loaded_asset(sequence, False):
        raise ValueError('Fox clip save failed: ' + destination)
    return sequence


def _clips(unreal, context, args):
    clips = {}
    for name, slot in _roster(args['clips']).items():
        clips[name] = _load(unreal, context, slot, unreal.AnimSequence, f'{DEST}/A_Fox{name}')
    return clips


def blend(context, unreal, args):
    package = f'{DEST}/BS_FoxLocomotion'
    _start(unreal, context, [package])
    facts = _data(context, args['facts'], 'facts.json')
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    clips = _clips(unreal, context, args)
    speeds = {n: float(facts['speeds'][n]) for n in LOCOMOTION}
    factory = unreal.BlendSpaceFactory1D(); factory.set_editor_property('target_skeleton', skeleton)
    space = unreal.AssetToolsHelpers.get_asset_tools().create_asset('BS_FoxLocomotion', DEST, unreal.BlendSpace1D, factory)
    if space is None or _path(space) != package:
        raise ValueError('Fox blend space not created')
    params = list(space.get_editor_property('blend_parameters'))
    for key, value in dict(display_name='Speed (cm/s)', min=0., max=speeds['Run']).items():
        params[0].set_editor_property(key, value)
    space.set_editor_property('blend_parameters', params)
    space.set_editor_property('scale_animation', True)
    smoothing = list(space.get_editor_property('interpolation_param')); smoothing[0].set_editor_property('interpolation_time', .12)
    space.set_editor_property('interpolation_param', smoothing)
    if not unreal.WandererContentLibrary.configure_blend_space(space, [clips[n] for n in LOCOMOTION], [speeds[n] for n in LOCOMOTION]):
        raise ValueError('Fox blend space samples were refused')
    if not unreal.EditorAssetLibrary.save_loaded_asset(space, False):
        raise ValueError('Fox blend space save failed')
    return space


def definition(context, unreal, args):
    package = f'{DEST}/DA_FoxHunter'
    _start(unreal, context, [package])
    facts = _data(context, args['facts'], 'facts.json')
    mesh_asset = _load(unreal, context, args['mesh'], unreal.SkeletalMesh, f'{DEST}/SK_FoxHunter')
    space = _load(unreal, context, args['blend'], unreal.BlendSpace1D, f'{DEST}/BS_FoxLocomotion')
    clips = _clips(unreal, context, args)
    if sorted(clips) != sorted(facts['clips']):
        raise ValueError('Fox definition clips differ from the export')
    entries = []
    for name, cfg in facts['clips'].items():
        e = unreal.FoxHunterClip()
        e.set_editor_property('role', name); e.set_editor_property('duration', float(cfg['duration']))
        hw = cfg.get('hit_window')
        e.set_editor_property('hit_start', float(hw[0]) if hw else -1.); e.set_editor_property('hit_end', float(hw[1]) if hw else -1.)
        e.set_editor_property('strike_bone', cfg.get('strike_bone', 'None')); e.set_editor_property('strike_tip_bone', cfg.get('strike_tip_bone', 'None'))
        e.set_editor_property('reach_cm', float(cfg.get('reach_cm', 0.)))
        e.set_editor_property('root_motion', bool(cfg['root_motion'])); e.set_editor_property('loop', bool(cfg['loop']))
        e.set_editor_property('holds_last_pose', bool(cfg['holds_last_pose']))
        e.set_editor_property('travel_cm', float(cfg['travel_cm'][0])); e.set_editor_property('yaw_degrees', float(cfg['yaw_degrees']))
        entries.append(e)
    factory = unreal.DataAssetFactory(); factory.set_editor_property('data_asset_class', unreal.FoxHunterDefinition)
    value = unreal.AssetToolsHelpers.get_asset_tools().create_asset('DA_FoxHunter', DEST, unreal.FoxHunterDefinition, factory)
    if value is None or _path(value) != package:
        raise ValueError('Fox definition not created')
    speeds = facts['speeds']
    for key, item in dict(mesh=mesh_asset, locomotion=space, actions=clips, clips=entries, creep_speed=float(speeds['Creep']),
                          run_speed=float(speeds['Run']), capsule_radius=float(facts['capsule']['radius_cm']),
                          capsule_half_height=float(facts['capsule']['half_height_cm']), sole_height=float(facts['sole_cm'])).items():
        value.set_editor_property(key, item)
    if not unreal.EditorAssetLibrary.save_loaded_asset(value, False):
        raise ValueError('Fox definition save failed')
    return value


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (RECORD,):
        raise ValueError('The fox record job owns only its report')
    facts = _data(context, args['facts'], 'facts.json')
    mesh_asset = _load(unreal, context, args['mesh'], unreal.SkeletalMesh, f'{DEST}/SK_FoxHunter')
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    value = _load(unreal, context, args['definition'], package=f'{DEST}/DA_FoxHunter')
    editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    pending, bones = ['root'], []
    while pending:
        bone = pending.pop(); bones.append(bone)
        pending.extend(str(b) for b in editor.get_bone_children(mesh_asset, bone))
    pose = unreal.AnimPoseExtensions.get_reference_pose(skeleton)
    root_scale = unreal.AnimPoseExtensions.get_bone_pose(pose, 'root', unreal.AnimPoseSpaces.WORLD).scale3d.x
    gaps = {b: (unreal.AnimPoseExtensions.get_bone_pose(pose, b, unreal.AnimPoseSpaces.WORLD).translation
                - unreal.Vector(*facts['rest_bones_cm'][b])).length() for b in PROBES}
    clips = {name: {'path': c.get_path_name(), 'duration': c.get_editor_property('sequence_length'),
                    'root_motion': bool(facts['clips'][name]['root_motion'])} for name, c in _clips(unreal, context, args).items()}
    return {RECORD: {'mesh': mesh_asset.get_path_name(), 'bones': bones, 'root_scale': root_scale, 'reference_gaps_cm': gaps,
                     'materials': [str(s.material_slot_name) for s in mesh_asset.materials],
                     'lod_vertices': [editor.get_num_verts(mesh_asset, i) for i in range(editor.get_lod_count(mesh_asset))],
                     'clips': clips, 'speeds': facts['speeds'], 'definition': value.get_path_name(), 'source': facts['source_sha256']}}


ACTIONS = {'material': material, 'mesh': mesh, 'clip': clip, 'blend': blend, 'definition': definition, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-fox-hunter-native-bodies
    Each job MUST author exactly its declared /Game/FoxHunter owner (or the report)
    from declared inputs: materials by the original loop body on their declared
    texture, the mesh bundle with the original bone and reference-pose checks,
    clips with their duration check, root motion, root lock and shared compression,
    the blend space and definition as the original builds them. It MUST NOT run
    the original top level.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported fox action')
    action = args['action']
    if action in ('mesh', 'clip'):
        kind = 'skeletal_mesh' if action == 'mesh' else 'animation'
        if params.get('op') != 'finish' or params.get('kind') != kind:
            raise ValueError(f'A fox {action} is finished by unreal.finish({kind})')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected fox author parameters')
    return ACTIONS[action](context, unreal, args)
