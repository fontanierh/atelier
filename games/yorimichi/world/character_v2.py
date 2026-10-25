"""Native bodies for one character's body import (Scripts/import_character.py), one declared asset bundle per job.

``args.action`` selects
- ``material``: one body material in the game's character look (import_character.material);
- ``mesh``: SK_<Name> with its Skeleton (and PhysicsAsset, and cloth colliders), finished from its raw import:
  CPU access, slot materials, Chaos cloth, contact morphs, the skeleton check and the saved bindings;
- ``clip``: one own clip A_<Clip> from its raw import: duration, root motion off, the shared compression and the
  recorded morph curves read back;
- ``base``: DA_<Name>Base, the WandererDefinition with the mesh, own clips and measurements.
The values the original reads from build/<output>/export.json come from that declared Data Item.
"""
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
CLOTH_MAX_DISTANCE = 30.    # import_character.CLOTH_MAX_DISTANCE
MORPH_CURVE_ERROR = .002    # import_character.MORPH_CURVE_ERROR
SEE_THROUGH = '/Game/SeeThrough/MPC_SeeThrough'   # see_through.MPC


def _package(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical declared /Game package')
    return value


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared character input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Character native input must be exactly one declared package: ' + slot)
    return _package(packages[0])


def _load(unreal, context, slot, cls=None):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or _path(asset) != package or (cls is not None and not isinstance(asset, cls)):
        raise ValueError('Declared character input did not load as expected: ' + package)
    return asset


def _config(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared character export')
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Character export must be a job-local declared input')
    path = root / 'export.json' if root.is_dir() else root
    if path.name != 'export.json' or path.is_symlink() or not path.is_file():
        raise ValueError('Character export.json is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    """{name: slot}: a keyed slot map, or the provider's resolved derived_items {root, members: [{piece, slot}]}."""
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Character derived roster is unresolved')
        roster = {r['piece']: r['slot'] for r in rows}
        if len(roster) != len(rows):
            raise ValueError('Duplicate character derived member')
        return roster
    if not isinstance(value, dict):
        raise ValueError('Character roster must be a slot map')
    return dict(value)


def _fresh(unreal, package):
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('Character destination must be fresh: ' + package)


def _module(context, relative):
    path = Path(context.job_dir) / SCRIPTS / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original helper is not staged keyed code: ' + relative)
    spec = importlib.util.spec_from_file_location('atelier_' + relative.removesuffix('.py'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def material(context, unreal, args):
    """import_character.material, with its texture a declared finished input."""
    destination = f"{_package(args['dest'])}/{args['name']}"
    if list(context.outputs) != [destination]:
        raise ValueError('Material job owns exactly its declared package')
    config = _config(context, args['export'])
    cfg = config['materials'][args['name']]
    if 'textures' in args:
        # The whole character texture roster is staged; the export names this material's own one.
        roster = _roster(args['textures'])
        stem = Path(cfg['texture']).stem if cfg['texture'] else None
        if stem is not None and stem not in roster:
            raise ValueError('Material texture is not in the declared character textures')
        args = {**args, **({'texture': roster[stem]} if stem else {})}
        args.pop('textures')
    if bool(cfg['texture']) != ('texture' in args):
        raise ValueError('Material texture input differs from the export')
    _fresh(unreal, destination)
    M = unreal.MaterialEditingLibrary
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(args['name'], args['dest'], unreal.Material,
                                                                  unreal.MaterialFactoryNew())
    if mat is None or _path(mat) != destination:
        raise ValueError('Material not created: ' + destination)
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    mat.set_editor_property('two_sided', cfg['two_sided'])
    mat.set_editor_property('used_with_skeletal_mesh', True)
    if args['morphs']:
        mat.set_editor_property('used_with_morph_targets', True)
    cloth = config.get('cloth')
    if cloth and cloth['mesh'] in cfg.get('meshes', ()):
        mat.set_editor_property('used_with_clothing', True)
    if cfg['texture']:
        texture = _load(unreal, context, args['texture'])
        node = M.create_material_expression(mat, unreal.MaterialExpressionTextureSample)
        node.set_editor_property('texture', texture)
        if not M.connect_material_property(node, 'RGB', unreal.MaterialProperty.MP_BASE_COLOR):
            raise ValueError('base colour texture not connected')
    else:
        node = M.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector)
        node.set_editor_property('constant', unreal.LinearColor(*cfg['base_color']))
        if not M.connect_material_property(node, '', unreal.MaterialProperty.MP_BASE_COLOR):
            raise ValueError('base colour not connected')
    fill = M.create_material_expression(mat, unreal.MaterialExpressionMultiply)
    fill.set_editor_property('const_b', .30)
    if not (M.connect_material_expressions(node, 'RGB' if cfg['texture'] else '', fill, 'A')
            and M.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)):
        raise ValueError('emissive fill not connected')
    for field, prop in [('roughness', unreal.MaterialProperty.MP_ROUGHNESS), ('metallic', unreal.MaterialProperty.MP_METALLIC),
                        ('specular', unreal.MaterialProperty.MP_SPECULAR)]:
        constant = M.create_material_expression(mat, unreal.MaterialExpressionConstant)
        constant.set_editor_property('r', cfg[field])
        if not M.connect_material_property(constant, '', prop):
            raise ValueError(field + ' not connected')
    M.recompile_material(mat)
    see_through = args.get('see_through')
    if see_through and args['name'].startswith(tuple(see_through['prefixes'])):
        # import_see_through.main for this material: the shared collection read only, then the original patch.
        if _selected(context, see_through['collection']) != SEE_THROUGH:
            raise ValueError('See-through needs the shared ' + SEE_THROUGH)
        cut = _module(context, 'see_through.py')
        cut.collection()
        if cut.character(mat):
            if not cut.save(mat):
                raise ValueError('See-through material failed to compile: ' + destination)
            return mat
    if not unreal.EditorAssetLibrary.save_loaded_asset(mat, False):
        raise ValueError('Material save failed: ' + destination)
    return mat


def native_morph(names, name, owner):
    """import_character.native_morph: the importer may prefix a mesh identifier."""
    matches = [native for native in names if native == name or native.endswith('_' + name)]
    if len(matches) != 1:
        raise ValueError(f'{owner}: morph target {name} matches {matches}')
    return matches[0]


def skeleton_tree(editor, mesh, owner):
    """import_character.skeleton_tree: {bone: parent} from root down, each bone once."""
    parents, pending = {'root': None}, ['root']
    while pending:
        bone = pending.pop()
        children = [str(b) for b in editor.get_bone_children(mesh, bone)]
        if set(children) & set(parents):
            raise ValueError(f'{owner}: a bone appears twice {children}')
        parents.update({child: bone for child in children})
        pending.extend(children)
    return parents


def mesh(context, unreal, args):
    params = context.params
    destination = _package(params['destination'])
    partners = params.get('partners', {})
    if not isinstance(partners, dict) or set(partners) - {'skeleton', 'physics_asset'} or 'skeleton' not in partners:
        raise ValueError('The skeletal finish owns its skeleton (and physics asset)')
    cloth_package = args.get('cloth_package')
    owned = {destination, *map(_package, partners.values()), *([_package(cloth_package)] if cloth_package else [])}
    if set(context.outputs) != owned:
        raise ValueError('Skeletal finish owns exactly its mesh bundle')
    library, name = unreal.EditorAssetLibrary, args['name']
    config = _config(context, args['export'])
    if bool(config.get('cloth')) != bool(cloth_package):
        raise ValueError('Cloth collider ownership differs from the export')
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    materials = {key: _load(unreal, context, slot) for key, slot in _roster(args['materials']).items()}
    if set(materials) != set(config['materials']):
        raise ValueError('Material inputs differ from the export')
    for package in owned:
        _fresh(unreal, package)
    asset = library.duplicate_asset(_path(raw), destination)
    if not isinstance(asset, unreal.SkeletalMesh):
        raise ValueError('Skeletal duplicate failed: ' + destination)
    skeleton = library.duplicate_asset(_path(raw.get_editor_property('skeleton')), partners['skeleton'])
    if not isinstance(skeleton, unreal.Skeleton):
        raise ValueError('Skeleton duplicate failed')
    asset.set_editor_property('skeleton', skeleton)
    skeleton.set_editor_property('preview_skeletal_mesh', asset)
    raw_physics = raw.get_editor_property('physics_asset')
    if 'physics_asset' in partners:
        if raw_physics is None:
            raise ValueError('The raw import made no physics asset')
        physics = library.duplicate_asset(_path(raw_physics), partners['physics_asset'])
        if not isinstance(physics, unreal.PhysicsAsset):
            raise ValueError('Physics asset duplicate failed')
        asset.set_editor_property('physics_asset', physics)
        physics.set_editor_property('preview_skeletal_mesh', asset)
    elif raw_physics is not None:
        raise ValueError('[unreal] physics_asset = false, but the raw import made a physics asset')
    if args['cpu_access']:
        unreal.SkeletalMeshEditorSubsystem.set_allow_cpu_access(asset, True)
    slots = list(asset.materials)
    for slot in slots:
        key = str(slot.get_editor_property('imported_material_slot_name'))
        if key not in materials:
            raise ValueError(f'unknown material {key}')
        slot.set_editor_property('material_interface', materials[key])
    asset.set_editor_property('materials', slots)
    cloth = config.get('cloth')
    if cloth:
        capsules = cloth['colliders']
        tools = unreal.YorimichiClothLibrary
        colliders = tools.make_capsule_colliders(asset, cloth_package, [c['bone'] for c in capsules],
                                                 [c['from'] for c in capsules], [c['to'] for c in capsules],
                                                 [c['radius_cm'] for c in capsules])
        if not colliders or _path(colliders) != cloth_package:
            raise ValueError('the cloth colliders could not be built')
        library.save_loaded_asset(colliders, False)
        section = next(key for key, cfg in config['materials'].items() if cloth['mesh'] in cfg['meshes'])
        if not tools.add_section_cloth(asset, section, CLOTH_MAX_DISTANCE, colliders, True):
            raise ValueError('the cloth could not be built')
    contacts = [*args['contact_morphs'], *config.get('contact_morphs', [])]
    validate_contact_data = _module(context, 'skin_morph_contacts.py').validate_contact_data if contacts else None
    targets = []
    if contacts:
        names = [str(n) for n in asset.get_all_morph_target_names()]
        targets = [native_morph(names, key, name) for key in contacts]
        data, receipt = unreal.SkinMorphContactLibrary.capture_skin_morph_contacts(asset, targets)
        if data is None:
            raise ValueError(f'{name}: contact morph capture failed {receipt}')
        validate_contact_data(unreal.SkinMorphContactLibrary, asset, targets, f'{name} contact morph data')
    elif args['morphs']:
        unreal.SkinMorphContactLibrary.clear_skin_morph_contacts(asset)
    for value in (skeleton, *([asset.get_editor_property('physics_asset')] if 'physics_asset' in partners else [])):
        if not library.save_loaded_asset(value, False):
            raise ValueError('Partner save failed: ' + _path(value))
    if not library.save_loaded_asset(asset, False):
        raise ValueError('Skeletal mesh save failed: ' + destination)
    if contacts:
        validate_contact_data(unreal.SkinMorphContactLibrary, asset, targets, f'Saved {name} contact morph data')
    editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    if skeleton_tree(editor, asset, name) != config['parents']:
        raise ValueError('imported skeleton mismatch')
    for slot in asset.materials:
        key = str(slot.get_editor_property('imported_material_slot_name'))
        mat = slot.material_interface
        if (not mat or mat.get_path_name() != f"{args['dest']}/{key}.{key}"
                or not mat.get_editor_property('used_with_skeletal_mesh')
                or (args['morphs'] and not mat.get_editor_property('used_with_morph_targets'))
                or mat.get_editor_property('two_sided') != config['materials'][key]['two_sided']):
            raise ValueError(f'unsaved material binding {key}')
    return asset


def clip(context, unreal, args):
    params = context.params
    destination = _package(params['destination'])
    if list(context.outputs) != [destination]:
        raise ValueError('Clip job owns exactly its declared package')
    library = unreal.EditorAssetLibrary
    cfg = _config(context, args['export'])['clips'][args['name']]
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'])
    settings = _load(unreal, context, args['compression'])
    body = _load(unreal, context, args['mesh'], unreal.SkeletalMesh)
    if _path(settings) != COMPRESSION:
        raise ValueError('Clip compression input is not the shared CharacterCompression')
    _fresh(unreal, destination)
    sequence = library.duplicate_asset(_path(raw), destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Clip is not on the declared skeleton: ' + destination)
    if abs(sequence.get_editor_property('sequence_length') - cfg['duration']) >= .001:
        raise ValueError(f'{args["name"]}: duration differs from the export')
    sequence.set_editor_property('enable_root_motion', False)
    compression = _module(context, 'animation_compression.py')
    compression._settings = settings
    compression.apply_to(sequence)
    if not library.save_loaded_asset(sequence, False):
        raise ValueError('Clip save failed: ' + destination)
    if sequence.get_editor_property('enable_root_motion') or sequence.get_editor_property('bone_compression_settings') != settings:
        raise ValueError('Clip finishing did not persist: ' + destination)
    expected = cfg.get('expected_morph_curves')
    if expected:
        P = unreal.AnimPoseExtensions
        options = unreal.AnimPoseEvaluationOptions()
        options.evaluation_type = unreal.AnimDataEvalType.COMPRESSED
        options.optional_skeletal_mesh = body
        morphs = [m.get_name() for m in body.get_editor_property('morph_targets')]
        targets = {key: native_morph(morphs, key, args['name']) for key in expected}
        worst = 0
        for frame in range(cfg['frames']):
            pose = P.get_anim_pose_at_time(sequence, frame / cfg['fps'], options)
            if not P.is_valid(pose):
                raise ValueError('invalid compressed pose')
            for key, values in expected.items():
                worst = max(worst, abs(P.get_curve_weight(pose, targets[key]) - values[frame]))
        if worst > MORPH_CURVE_ERROR:
            raise ValueError(f'{args["name"]}: morph curve error {worst}')
    return sequence


def base(context, unreal, args):
    destination = f"{_package(args['dest'])}/{args['name']}"
    if list(context.outputs) != [destination]:
        raise ValueError('Base definition job owns exactly its declared package')
    config = _config(context, args['export'])
    clips = {key: _load(unreal, context, slot) for key, slot in _roster(args['clips']).items()}
    if set(clips) != set(config['clips']):
        raise ValueError('Base definition clips differ from the export')
    body = _load(unreal, context, args['mesh'], unreal.SkeletalMesh)
    _fresh(unreal, destination)
    factory = unreal.DataAssetFactory()
    factory.set_editor_property('data_asset_class', unreal.WandererDefinition)
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(args['name'], args['dest'], unreal.WandererDefinition, factory)
    if asset is None or _path(asset) != destination:
        raise ValueError('Base definition not created: ' + destination)
    for key, value in dict(mesh=body, actions=clips, use_authored_movement=True,
                           rest_ankle_heights=unreal.Vector2D(config['rest_ankles_cm']['L'], config['rest_ankles_cm']['R']),
                           sole_height=config['sole_cm'], camera_height=args['camera_height']).items():
        asset.set_editor_property(key, value)
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, False):
        raise ValueError('Base definition save failed: ' + destination)
    if ({str(k) for k in asset.get_editor_property('actions')} != set(config['clips'])
            or not asset.get_editor_property('use_authored_movement')):
        raise ValueError('the base definition lost clips')
    return asset


ACTIONS = {'material': material, 'mesh': mesh, 'clip': clip, 'base': base}
FINISHES = {'mesh': 'skeletal_mesh', 'clip': 'animation'}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-character-body-bodies
    Each job MUST author or finish exactly its declared package bundle from declared
    inputs with import_character.py's settings and checks: fresh duplicates of raw
    imports, the declared shared compression, materials bound by slot name, and the
    saved assets read back. It MUST NOT import sources, run the original top level,
    or write reports or packages outside its declaration.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported character body action')
    kind = FINISHES.get(args['action'])
    if kind:
        if params.get('op') != 'finish' or params.get('kind') != kind:
            raise ValueError(f'{args["action"]} is finished by unreal.finish({kind})')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected character author parameters')
    return ACTIONS[args['action']](context, unreal, args)
