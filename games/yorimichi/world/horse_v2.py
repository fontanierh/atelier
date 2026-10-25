"""Native bodies for unreal.horses (Scripts/import_horses.py), one declared /Game/Horses package (or record) per job.

``args.action`` selects
- ``master``: M_HorseCoat, M_HorseHair, M_HorseTack or M_HorseTackMasked by the original make_*_master, run alone
  (the coat master's default mask is the declared finished T_Coat_Solid_Mask);
- ``instance``: MI_<piece>, the original restyle_instance result for one glTF material: its master by role (coat,
  hair with the breed's hair colours, tack or tack_masked by alpha mode), its kept base-colour texture and cutoff;
- ``mesh``: SK_Horse_<Breed> and SKEL_Horse_<Breed> from a raw glTF skeletal import, slots bound by imported slot
  name to the owner's derived instances;
- ``tack``: SK_Horse_<Breed>_<Part>_<sid> from a raw glTF skeletal import on the finished breed skeleton, likewise;
- ``clip``: A_Horse_<Breed>_<clip> from a raw glTF animation on the breed skeleton: root motion off and the shared
  compression, as import_breed does;
- ``record``: Data/horses/roster.json (horse_data.roster, checked by roster_problems) and horses/unreal_import.json
  (the roster with each mesh's instances and the textures they keep), from the loaded finished assets.
The original top level (its directory delete, registry scans and renames) never runs.
"""
import ast
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
DEST = '/Game/Horses'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_horses.py'
HORSE_DATA = 'games/yorimichi/unreal/Scripts/horse_data.py'
COMPRESSION_SCRIPT = 'games/yorimichi/unreal/Scripts/animation_compression.py'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
SOLID_MASK = DEST + '/Coats/Masks/T_Coat_Solid_Mask'
MASTERS = {'coat': ('make_coat_master', 'M_HorseCoat', ()), 'hair': ('make_hair_master', 'M_HorseHair', ()),
           'tack': ('make_tack_master', 'M_HorseTack', (False,)), 'tack_masked': ('make_tack_master', 'M_HorseTackMasked', (True,))}
HELPERS = ('_get_or_create_material', '_default_tex', '_vec_rgb')
ROSTER, REPORT = 'data/roster.json', 'data/unreal_import.json'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared horse input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Horse native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls=None):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or _path(asset) != package or (cls is not None and not isinstance(asset, cls)):
        raise ValueError('Declared horse input did not load as expected: ' + package)
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared horse data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Horse data must be a job-local declared input')
    path = root / name if root.is_dir() else root   # a committed file input is staged under its slot name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Horse data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Horse derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    if not isinstance(value, dict):
        raise ValueError('Horse roster must be a slot map')
    return dict(value)


def _start(unreal, context, packages):
    if set(context.outputs) != set(packages):
        raise ValueError('Horse job owns exactly its declared packages')
    for package in packages:
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            raise ValueError('Horse destination must be fresh: ' + package)


def _module(context, relative, name):
    path = Path(context.job_dir) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Horse keyed code is not staged: ' + relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def piece(owner, name):
    """horse_members_v2.piece: the member name of an owner's glTF material or image."""
    name = re.sub(r'\.(png|jpe?g)\Z', '', f'{owner}_{name}', flags=re.I)
    return re.sub(r'[^A-Za-z0-9_]+', '_', name).strip('_')


def original(context, unreal, names):
    """The named import_horses.py functions (and its module constants), run without its top level."""
    path = Path(context.job_dir) / ORIGINAL
    if path.is_symlink() or not path.is_file():
        raise ValueError('The original horse importer is not staged keyed code')
    body = ast.parse(path.read_bytes()).body
    nodes = [n for n in body if isinstance(n, ast.FunctionDef) and n.name in names]
    if sorted(n.name for n in nodes) != sorted(set(names)):
        raise ValueError('import_horses.py no longer defines ' + ', '.join(names))
    constants = [n for n in body if isinstance(n, ast.Assign) and [getattr(t, 'id', None) for t in n.targets] == ['WHITE_SQUARE']]
    scope = {'U': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
             'M': unreal.MaterialEditingLibrary, 'DEST': DEST}
    exec(compile(ast.Module(body=[*constants, *nodes], type_ignores=[]), ORIGINAL, 'exec'), scope)
    return scope


def master(context, unreal, args):
    function, name, extra = MASTERS[args['key']]
    package = f'{DEST}/{name}'
    _start(unreal, context, [package])
    if args['key'] == 'coat' and _path(_load(unreal, context, args['mask'], unreal.Texture2D)) != SOLID_MASK:
        raise ValueError('The coat master needs the declared T_Coat_Solid_Mask')
    material = original(context, unreal, (function, *HELPERS))[function](name, *extra)
    if _path(material) != package:
        raise ValueError('Horse master not authored at its package')
    return material


def instance(context, unreal, args):
    meta = _data(context, args['meta'], 'meta.json')
    if meta['name'] != args['name'] or meta['role'] not in ('coat', 'hair', 'tack'):
        raise ValueError('Horse material member differs from its piece')
    folder = args['folder']
    package = f'{folder}/MI_{meta["name"]}'
    _start(unreal, context, [package])
    key = meta['role'] if meta['role'] != 'tack' else ('tack_masked' if meta['masked'] else 'tack')
    parent = _load(unreal, context, args['masters'][key], unreal.Material)
    if _path(parent) != f'{DEST}/{MASTERS[key][1]}':
        raise ValueError('Horse material parent differs from its role')
    images = _roster(args['images'])
    if meta['base'] not in images:
        raise ValueError(f'{meta["name"]}: its base-colour image is not a declared texture')
    base = _load(unreal, context, images[meta['base']])
    E, M = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_' + meta['name'], folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi is None or _path(mi) != package:
        raise ValueError('Horse material instance not created: ' + package)
    # import_horses.restyle_instance after Interchange: the master, the hair colours, the cutoff, the kept albedo.
    M.set_material_instance_parent(mi, parent)
    if meta['role'] == 'hair':
        c = args['hair_colour']
        M.set_material_instance_vector_parameter_value(mi, 'PrimaryColor', unreal.LinearColor(c[0], c[1], c[2], 1.))
        M.set_material_instance_vector_parameter_value(mi, 'SecondaryColor', unreal.LinearColor(
            min(1., c[0] * 1.35), min(1., c[1] * 1.35), min(1., c[2] * 1.35), 1.))
    elif key == 'tack_masked':
        M.set_material_instance_scalar_parameter_value(mi, 'AlphaCutoff', meta['alpha_cutoff'] or .5)
    M.set_material_instance_texture_parameter_value(mi, 'BaseColorTexture', base)
    M.update_material_instance(mi)
    if not E.save_loaded_asset(mi, False):
        raise ValueError('Horse material instance save failed: ' + package)
    return mi


def _bind(unreal, context, asset, owner, args):
    materials = _roster(args['materials'])
    slots = list(asset.materials)
    if not slots:
        raise ValueError(f'{owner}: a mesh imported without material slots')
    for slot in slots:
        key = piece(owner, str(slot.get_editor_property('imported_material_slot_name')))
        bound = _load(unreal, context, materials[key]) if key in materials else None
        if bound is None or _path(bound) != f'{args["material_folder"]}/MI_{key}':
            raise ValueError(f'{_path(asset)}: no declared instance for slot {key}')
        slot.set_editor_property('material_interface', bound)
    asset.set_editor_property('materials', slots)


def mesh(context, unreal, args):
    params = context.params
    destination, skeleton_package = params['destination'], params['partners']['skeleton']
    _start(unreal, context, [destination, skeleton_package])
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    asset = library.duplicate_asset(_path(raw), destination)
    skeleton = library.duplicate_asset(_path(raw.get_editor_property('skeleton')), skeleton_package)
    if not isinstance(asset, unreal.SkeletalMesh) or not isinstance(skeleton, unreal.Skeleton):
        raise ValueError('Horse skeletal duplicate failed: ' + destination)
    if not unreal.AtelierBuildWorkerLibrary.bind_skeletal_partners(asset, skeleton, None):
        raise ValueError('Horse skeletal partner binding failed')
    _bind(unreal, context, asset, args['owner'], args)
    if not library.save_loaded_asset(skeleton, False) or not library.save_loaded_asset(asset, False):
        raise ValueError('Horse skeletal save failed: ' + destination)
    return asset


def tack(context, unreal, args):
    params = context.params
    destination = params['destination']
    _start(unreal, context, [destination])
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    if raw.get_editor_property('skeleton') != skeleton:
        raise ValueError(f'{destination}: tack is not on its breed skeleton')
    asset = library.duplicate_asset(_path(raw), destination)
    if not isinstance(asset, unreal.SkeletalMesh) or asset.get_editor_property('skeleton') != skeleton:
        raise ValueError('Horse tack duplicate failed: ' + destination)
    _bind(unreal, context, asset, args['owner'], args)
    if not library.save_loaded_asset(asset, False):
        raise ValueError('Horse tack save failed: ' + destination)
    return asset


def clip(context, unreal, args):
    params = context.params
    destination = params['destination']
    _start(unreal, context, [destination])
    meta = _data(context, args['meta'], 'meta.json')
    if meta['name'] != args['name']:
        raise ValueError('Horse clip member differs from its piece')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    settings = _load(unreal, context, args['compression'])
    if _path(settings) != COMPRESSION:
        raise ValueError('Horse clip compression input is not the shared CharacterCompression')
    sequence = library.duplicate_asset(_path(raw), destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Horse clip is not on its breed skeleton: ' + destination)
    sequence.set_editor_property('enable_root_motion', False)
    module = _module(context, COMPRESSION_SCRIPT, 'atelier_horse_compression')
    module._settings = settings   # the declared shared owner: apply_to only assigns it
    module.apply_to(sequence)
    if not library.save_loaded_asset(sequence, False):
        raise ValueError('Horse clip save failed: ' + destination)
    return sequence


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (ROSTER, REPORT):
        raise ValueError('The horse record job owns only its roster and report')
    data = _module(context, HORSE_DATA, 'horse_record_data')
    library, built = _data(context, args['library'], 'manifest.json'), _data(context, args['built'], 'manifest.json')
    variants = _data(context, args['variants'], 'manifest.json')['variants']
    path = lambda slot: _load(unreal, context, slot).get_path_name()
    masters = {key: path(slot) for key, slot in args['masters'].items()}
    masks = {mask: path(slot) for mask, slot in args['masks'].items()}
    coat_variants = [{**v, 'texture': path(args['coat_variants'][v['id']])} for v in variants]
    breeds, materials = {}, {}
    for slug, entry in args['breeds'].items():
        clips = {}
        for name, slot in _roster(entry['clips']).items():
            sequence = _load(unreal, context, slot, unreal.AnimSequence)
            loop = library['clips'][name]['loop'] if name in library['clips'] else data.GENERATED_CLIPS[name]['loop']
            clips[name] = {'path': sequence.get_path_name(), 'length': round(sequence.get_editor_property('sequence_length'), 4),
                           'loop': loop}
        breeds[slug] = {'mesh': path(entry['mesh']), 'skeleton': path(entry['skeleton']), 'clips': clips,
                        'saddles': {sid: path(slot) for sid, slot in entry['saddles'].items()},
                        'reins': {sid: path(slot) for sid, slot in entry['reins'].items()}}
        for slot in [entry['mesh'], *entry['saddles'].values(), *entry['reins'].values()]:
            mesh = _load(unreal, context, slot, unreal.SkeletalMesh)
            used = {}
            for material in mesh.materials:
                mi = material.get_editor_property('material_interface')
                base = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(mi, 'BaseColorTexture')
                used[mi.get_path_name()] = base.get_path_name()
            materials[mesh.get_path_name()] = used
    roster = data.roster(library, built, masters, masks, coat_variants, breeds)
    problems = data.roster_problems(roster)
    if problems:
        raise ValueError('Horse roster differs from its contract: ' + '; '.join(problems))
    if not all(materials.values()):
        raise ValueError('A horse mesh carries no material instances')
    return {ROSTER: roster, REPORT: {**roster, 'materials': materials}}


ACTIONS = {'master': master, 'instance': instance, 'mesh': mesh, 'tack': tack, 'clip': clip, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-horse-native-bodies
    Each job MUST author exactly its declared /Game/Horses package (or the roster
    and report) from declared inputs only: masters by the original functions,
    instances by restyle_instance's rule from their own member, meshes and tack
    from raw glTF imports on the breed skeleton bound to their derived instances,
    clips with the shared compression. It MUST NOT run the original top level,
    delete /Game/Horses or scan the registry.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported horse action')
    action = args['action']
    if action in ('mesh', 'tack', 'clip'):
        kind = 'animation' if action == 'clip' else 'skeletal_mesh'
        if params.get('op') != 'finish' or params.get('kind') != kind:
            raise ValueError(f'A horse {action} is finished by unreal.finish({kind})')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected horse author parameters')
    return ACTIONS[action](context, unreal, args)
