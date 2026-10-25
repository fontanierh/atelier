"""Native bodies for unreal.adventure (Scripts/import_adventure.py), one declared /Game/Adventure package per job.

``args.action`` selects
- ``master``: M_AdventureCharacter(Masked) by the original master(name, masked), run alone;
- ``instance``: MI_<piece>, the original restyle() result for one glTF material: the adventure master for its
  alpha mode, its own base colour and emissive textures, emissive factor and (masked) alpha cutoff;
- ``mesh``: SK_<title> and SKEL_<title> from a raw glTF skeletal import, its slots bound by imported slot name to
  the owner's derived instances;
- ``clip``: A_<title>_<clip> from a raw glTF animation on the finished skeleton: the original length check against
  its member's frames at the export rate, root motion off and the shared compression;
- ``record``: Data/adventure/reference.json, import_character's record and import_equipment's, from loaded assets.
The original top level (its directory delete, registry scans and renames) never runs.
"""
import ast
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
DEST = '/Game/Adventure'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_adventure.py'
COMPRESSION_SCRIPT = 'games/yorimichi/unreal/Scripts/animation_compression.py'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
MASTERS = {False: 'M_AdventureCharacter', True: 'M_AdventureCharacterMasked'}
RECORD = 'data/reference.json'
MESH_YAW = -90.   # import_adventure.MESH_YAW


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared Reference input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Reference native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls=None):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or _path(asset) != package or (cls is not None and not isinstance(asset, cls)):
        raise ValueError('Declared Reference input did not load as expected: ' + package)
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared Reference data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Reference data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.name != name or path.is_symlink() or not path.is_file():
        raise ValueError(f'Reference data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Reference derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    if not isinstance(value, dict):
        raise ValueError('Reference roster must be a slot map')
    return dict(value)


def _start(unreal, context, packages):
    if set(context.outputs) != set(packages):
        raise ValueError('Reference job owns exactly its declared packages')
    for package in packages:
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            raise ValueError('Reference destination must be fresh: ' + package)


def piece(owner, name):
    """reference_members_v2._piece: the member name of an owner's glTF material or image."""
    return re.sub(r'[^A-Za-z0-9_]+', '_', f'{owner}_{name}').strip('_')


def original(context, unreal, names):
    path = Path(context.job_dir) / ORIGINAL
    if path.is_symlink() or not path.is_file():
        raise ValueError('The original adventure importer is not staged keyed code')
    nodes = [n for n in ast.parse(path.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name in names]
    if sorted(n.name for n in nodes) != sorted(names):
        raise ValueError('import_adventure.py no longer defines ' + ', '.join(names))
    scope = {'U': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
             'M': unreal.MaterialEditingLibrary, 'DEST': DEST}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), ORIGINAL, 'exec'), scope)
    return scope


def master(context, unreal, args):
    masked = bool(args['masked'])
    package = f'{DEST}/{MASTERS[masked]}'
    _start(unreal, context, [package])
    material = original(context, unreal, ('master',))['master'](MASTERS[masked], masked)
    if _path(material) != package:
        raise ValueError('Adventure master not authored at its package')
    return material


def instance(context, unreal, args):
    meta = _data(context, args['meta'], 'meta.json')
    if meta['name'] != args['name']:
        raise ValueError('Reference material member differs from its piece')
    folder = args['folder']
    package = f'{folder}/MI_{meta["name"]}'
    _start(unreal, context, [package])
    parent = _load(unreal, context, args['masters'][str(meta['masked']).lower()], unreal.Material)
    if _path(parent) != f'{DEST}/{MASTERS[meta["masked"]]}':
        raise ValueError('Reference material parent differs from its alpha mode')
    images = _roster(args['images'])
    E, M = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_' + meta['name'], folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi is None or _path(mi) != package:
        raise ValueError('Reference material instance not created: ' + package)
    # import_adventure.restyle, after Interchange: the master, then its kept albedo, emissive and cutoff.
    M.set_material_instance_parent(mi, parent)
    for key, parameter in (('base', 'BaseColorTexture'), ('emissive', 'EmissiveTexture')):
        if meta[key] is not None:
            if meta[key] not in images:
                raise ValueError(f'{meta["name"]}: its {key} image is not a declared texture')
            M.set_material_instance_texture_parameter_value(mi, parameter, _load(unreal, context, images[meta[key]]))
    M.set_material_instance_vector_parameter_value(mi, 'EmissiveFactor', unreal.LinearColor(*meta['emissive_factor'], 1.))
    if meta['masked']:
        M.set_material_instance_scalar_parameter_value(mi, 'AlphaCutoff', meta['alpha_cutoff'] or .5)
    M.update_material_instance(mi)
    if not E.save_loaded_asset(mi, False):
        raise ValueError('Reference material instance save failed: ' + package)
    return mi


def mesh(context, unreal, args):
    params = context.params
    destination, skeleton_package = params['destination'], params['partners']['skeleton']
    _start(unreal, context, [destination, skeleton_package])
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    materials = _roster(args['materials'])
    asset = library.duplicate_asset(_path(raw), destination)
    skeleton = library.duplicate_asset(_path(raw.get_editor_property('skeleton')), skeleton_package)
    if not isinstance(asset, unreal.SkeletalMesh) or not isinstance(skeleton, unreal.Skeleton):
        raise ValueError('Reference skeletal duplicate failed: ' + destination)
    if not unreal.AtelierBuildWorkerLibrary.bind_skeletal_partners(asset, skeleton, None):
        raise ValueError('Reference skeletal partner binding failed')
    slots = list(asset.materials)
    for slot in slots:
        if args['owner'] == 'Reference' and not any(name.startswith('Reference_') for name in materials):
            # The committed neutral marker rig has no glTF material. Preserve only
            # its absent/Engine default slot; never substitute an unknown game material.
            current = slot.get_editor_property('material_interface')
            if current is not None and not _path(current).startswith('/Engine/'):
                raise ValueError('Unmaterialed Reference marker has an unknown game material')
            continue
        key = piece(args['owner'], str(slot.get_editor_property('imported_material_slot_name')))
        bound = _load(unreal, context, materials[key]) if key in materials else None
        if bound is None or _path(bound) != f'{args["material_folder"]}/MI_{key}':
            raise ValueError(f'{destination}: no declared instance for slot {key}')
        slot.set_editor_property('material_interface', bound)
    asset.set_editor_property('materials', slots)
    # The skeleton first, so the mesh's saved package names its final path (import_adventure.import_character).
    if not library.save_loaded_asset(skeleton, False) or not library.save_loaded_asset(asset, False):
        raise ValueError('Reference skeletal save failed: ' + destination)
    return asset


def prop(context, unreal, args):
    """SM_<title> from a raw geometry-only glTF import, its slots bound by slot name to the owner's instances."""
    params = context.params
    destination = params['destination']
    _start(unreal, context, [destination])
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.StaticMesh)
    materials = _roster(args['materials'])
    asset = library.duplicate_asset(_path(raw), destination)
    if not isinstance(asset, unreal.StaticMesh):
        raise ValueError('Reference prop duplicate failed: ' + destination)
    for index, slot in enumerate(asset.get_editor_property('static_materials')):
        key = piece(args['owner'], str(slot.get_editor_property('material_slot_name')))
        bound = _load(unreal, context, materials[key]) if key in materials else None
        if bound is None or _path(bound) != f'{args["material_folder"]}/MI_{key}':
            raise ValueError(f'{destination}: no declared instance for slot {key}')
        asset.set_material(index, bound)
    if not library.save_loaded_asset(asset, False):
        raise ValueError('Reference prop save failed: ' + destination)
    return asset


def clip(context, unreal, args):
    params = context.params
    destination = params['destination']
    _start(unreal, context, [destination])
    meta = _data(context, args['meta'], 'meta.json') if 'meta' in args else None
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'])
    settings = _load(unreal, context, args['compression'])
    if _path(settings) != COMPRESSION:
        raise ValueError('Clip compression input is not the shared CharacterCompression')
    sequence = library.duplicate_asset(_path(raw), destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Reference clip is not on the declared skeleton: ' + destination)
    length = sequence.get_editor_property('sequence_length')
    # A Reference clip is checked against its member (import_character); the glider's one clip is not (import_equipment).
    if meta is not None and abs(length - meta['frames'] / meta['fps']) >= .002:
        raise ValueError(f'{destination}: length {length} differs from {meta["frames"]} frames at {meta["fps"]} fps')
    sequence.set_editor_property('enable_root_motion', False)
    if args.get('compress', True):
        path = Path(context.job_dir) / COMPRESSION_SCRIPT
        spec = importlib.util.spec_from_file_location('atelier_reference_compression', path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        module._settings = settings
        module.apply_to(sequence)
    if not library.save_loaded_asset(sequence, False):
        raise ValueError('Reference clip save failed: ' + destination)
    return sequence


def record(context, unreal, args):
    """import_character's record for Reference (with import_equipment's), from the declared finished assets."""
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (RECORD,):
        raise ValueError('The reference record job owns only its JsonData output')
    config = _data(context, args['export'], 'export.json')
    character = config['characters'][0]
    mesh_asset = _load(unreal, context, args['mesh'], unreal.SkeletalMesh)
    skeleton = _load(unreal, context, args['skeleton'])
    clips = {}
    finished = {_path(_load(unreal, context, slot)): slot for slot in _roster(args['clips']).values()}
    for entry in character['clips']:
        path = f'{DEST}/Reference/A_Reference_{entry["name"]}'
        if path not in finished:
            raise ValueError('Reference record lacks a declared clip: ' + entry['name'])
        sequence = _load(unreal, context, finished[path], unreal.AnimSequence)
        length = sequence.get_editor_property('sequence_length')
        clips[entry['name']] = {'path': sequence.get_path_name(), 'length': round(length, 4), 'loop': entry['loop'],
                                'travel_cm': [round(v * 100. * character['scale'], 2) for v in entry['travel']]}
    looks = {}
    for name, slot in sorted(_roster(args['materials']).items()):
        mi = _load(unreal, context, slot)
        masked = mi.get_editor_property('parent').get_name() == MASTERS[True]
        owner = next(o for o in args['owners'] if name.startswith(o + '_'))
        looks.setdefault(owner, []).append('masked' if masked else 'opaque')
    bounds = mesh_asset.get_bounds()
    result = {
        'name': 'Reference', 'label': character['label'], 'kind': character['kind'], 'mesh': mesh_asset.get_path_name(),
        'skeleton': skeleton.get_path_name(), 'mesh_yaw': MESH_YAW, 'scale': character['scale'],
        'height_cm': round(character['height'] * 100., 1),
        'radius_cm': round(min(bounds.box_extent.x, bounds.box_extent.y) * .5 * character['scale'], 1),
        'speeds_cm': {gait: round(speed * 100., 1) for gait, speed in character['speeds'].items()},
        'clips': clips, 'roles': character['roles'],
        'materials': [str(slot.material_slot_name) for slot in mesh_asset.materials], 'looks': looks.get('Reference', []),
        'seconds': 0.0}
    moves = character['moves']
    equipment = {}
    for slot_name, item in moves['equipment'].items():
        entry = {key: item[key] for key in ('hand', 'back', 'carry') if key in item}
        piece_mesh = _load(unreal, context, args['equipment'][slot_name]['mesh'])
        entry['mesh'] = piece_mesh.get_path_name()
        if 'clip' in item:
            entry['clip'] = _load(unreal, context, args['equipment'][slot_name]['clip']).get_path_name()
        entry['looks'] = looks.get(f'Reference{slot_name.capitalize()}', [])
        equipment[slot_name] = entry
    result['moves'] = {'actions': moves['actions'], 'params': moves['params'], 'equipment': equipment}
    return {RECORD: {'characters': [result]}}


ACTIONS = {'master': master, 'instance': instance, 'mesh': mesh, 'prop': prop, 'clip': clip, 'record': record}
FINISHES = {'mesh': 'skeletal_mesh', 'prop': 'static_mesh', 'clip': 'animation'}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-reference-bodies
    Each job MUST author or finish exactly its declared /Game/Adventure package (or
    the reference.json record) from declared inputs: the original master() alone,
    restyle()'s instance parameters from its own material member, fresh duplicates
    of raw glTF imports with the original clip length check and shared compression.
    It MUST NOT run the original top level, delete directories or scan the registry.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported Reference action')
    kind = FINISHES.get(args['action'])
    if kind:
        if params.get('op') != 'finish' or params.get('kind') != kind:
            raise ValueError(f'{args["action"]} is finished by unreal.finish({kind})')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected Reference author parameters')
    return ACTIONS[args['action']](context, unreal, args)
