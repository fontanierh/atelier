"""Native bodies for Scripts/import_wanderer.py, one declared Wanderer V2 asset bundle per job.

``args.action`` selects
- ``material``: M_Wanderer, the flat vertex-colour graph (sRGB to linear, rough, no specular, 0.30 emissive fill);
- ``mesh``: SK_Wanderer with its compact Skeleton and PhysicsAsset, finished from its raw import: the one palette
  slot bound to M_Wanderer and the bone hierarchy checked against model_manifest.json;
- ``clip``: A_<Clip> from its raw 60 Hz import: duration, root motion off and the shared compression;
- ``blendspace``: BS_Locomotion or BS_Crouching over the finished clips at their manifest speeds;
- ``definition``: the public /Game/Wanderer/DA_Wanderer selection asset.
Every manifest value comes from the declared characters.wanderer Item, its bytes checked against build.json.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
DEST = '/Game/Wanderer/V2'
DEFINITION = '/Game/Wanderer/DA_Wanderer'
COMPRESSION = '/Game/Japan/Animation/CharacterCompression'
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
LINEAR = 'return lerp(C/12.92,pow((C+0.055)/1.055,2.4),step(0.04045,C));'
# import_wanderer.blendspace: the upright idle pelvis settles longer after braking.
INTERPOLATION = {'BS_Locomotion': .14, 'BS_Crouching': .09}


def _package(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical declared /Game package')
    return value


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared Wanderer input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Wanderer native input must be exactly one declared package: ' + slot)
    return _package(packages[0])


def _load(unreal, context, slot, cls=None):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if asset is None or _path(asset) != package or (cls is not None and not isinstance(asset, cls)):
        raise ValueError('Declared Wanderer input did not load as expected: ' + package)
    return asset


def _fresh(unreal, package):
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('Wanderer destination must be fresh: ' + package)


def _file(root, relative):
    path = root.joinpath(*relative.split('/'))
    if path.is_symlink() or not path.is_file() or path.resolve() != path:
        raise ValueError('Wanderer export member is absent or linked: ' + relative)
    return path


def export(context, slot, *members):
    """The declared characters.wanderer Item: its manifests, and each named member checked against build.json."""
    if not isinstance(slot, str) or context.inputs.get(slot) is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('Wanderer export must be a declared Data Item')
    root = Path(context.inputs[slot])
    if (not root.is_absolute() or root.is_symlink() or not root.is_dir() or root.resolve() != root
            or not root.is_relative_to(Path(context.job_dir).resolve())):
        raise ValueError('Wanderer export must be a job-local declared directory')
    build = json.loads(_file(root, 'build.json').read_bytes())
    artifacts = build.get('artifacts') if isinstance(build, dict) else None
    if not isinstance(artifacts, dict):
        raise ValueError('Wanderer build.json has no artifact digests')
    for relative in ('model_manifest.json', 'animation_manifest.json', *members):
        if artifacts.get(relative) != hashlib.sha256(_file(root, relative).read_bytes()).hexdigest():
            raise ValueError('Wanderer export member differs from build.json: ' + relative)
    model = json.loads(_file(root, 'model_manifest.json').read_bytes())
    clips = json.loads(_file(root, 'animation_manifest.json').read_bytes())
    if set(artifacts) != {'Wanderer.blend', 'model_manifest.json', 'animation_manifest.json', 'animation_targets.json',
                          'fbx/Wanderer.fbx', *('fbx/' + name + '.fbx' for name in clips)}:
        raise ValueError('Wanderer build.json differs from its animation manifest')
    return model, clips


def _module(context, relative):
    path = Path(context.job_dir) / SCRIPTS / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original helper is not staged keyed code: ' + relative)
    spec = importlib.util.spec_from_file_location('atelier_' + relative.removesuffix('.py'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _save(unreal, asset):
    if not unreal.EditorAssetLibrary.save_loaded_asset(asset, False):
        raise ValueError('Wanderer save failed: ' + _path(asset))


def material(context, unreal, args):
    destination = DEST + '/M_Wanderer'
    if list(context.outputs) != [destination] or context.inputs:
        raise ValueError('M_Wanderer job owns exactly its package and reads nothing')
    _fresh(unreal, destination)
    M = unreal.MaterialEditingLibrary
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_Wanderer', DEST, unreal.Material, unreal.MaterialFactoryNew())
    if not isinstance(mat, unreal.Material) or _path(mat) != destination:
        raise ValueError('M_Wanderer not created')
    M.delete_all_material_expressions(mat)
    mat.set_editor_property('used_with_skeletal_mesh', True)
    mat.set_editor_property('two_sided', True)
    vc = M.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -500, 0)
    linear = M.create_material_expression(mat, unreal.MaterialExpressionCustom, -300, 0)
    linear.set_editor_property('code', LINEAR)
    linear.set_editor_property('output_type', unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    ci = unreal.CustomInput()
    ci.set_editor_property('input_name', 'C')
    linear.set_editor_property('inputs', [ci])
    if not (M.connect_material_expressions(vc, '', linear, 'C')
            and M.connect_material_property(linear, '', unreal.MaterialProperty.MP_BASE_COLOR)):
        raise ValueError('M_Wanderer base colour not connected')
    for prop, value, y in [(unreal.MaterialProperty.MP_ROUGHNESS, 1., 100), (unreal.MaterialProperty.MP_SPECULAR, 0., 180)]:
        constant = M.create_material_expression(mat, unreal.MaterialExpressionConstant, -200, y)
        constant.set_editor_property('r', value)
        if not M.connect_material_property(constant, '', prop):
            raise ValueError('M_Wanderer constant not connected')
    fill = M.create_material_expression(mat, unreal.MaterialExpressionMultiply, -100, 280)
    fill.set_editor_property('const_b', .30)
    if not (M.connect_material_expressions(linear, '', fill, 'A')
            and M.connect_material_property(fill, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)):
        raise ValueError('M_Wanderer emissive fill not connected')
    M.recompile_material(mat)
    _save(unreal, mat)
    if not mat.get_editor_property('two_sided') or not mat.get_editor_property('used_with_skeletal_mesh'):
        raise ValueError('M_Wanderer flags did not persist')
    return mat


def skeleton_tree(editor, mesh):
    """import_wanderer's walk: every bone once, from root down."""
    parents, pending = {'root': None}, ['root']
    while pending:
        bone = pending.pop()
        children = [str(b) for b in editor.get_bone_children(mesh, bone)]
        if set(children) & set(parents):
            raise ValueError('Wanderer skeleton cycle')
        parents.update({child: bone for child in children})
        pending.extend(children)
    return parents


def mesh(context, unreal, args):
    params = context.params
    destination = _package(params['destination'])
    partners = params.get('partners')
    if (destination != DEST + '/SK_Wanderer' or partners != {'skeleton': destination + '_Skeleton',
                                                             'physics_asset': destination + '_PhysicsAsset'}
            or set(context.outputs) != {destination, *partners.values()}):
        raise ValueError('The Wanderer skeletal finish owns exactly SK_Wanderer, its Skeleton and PhysicsAsset')
    model, _clips = export(context, args['wanderer'], 'fbx/Wanderer.fbx')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.SkeletalMesh)
    palette = _load(unreal, context, args['material'], unreal.MaterialInterface)
    if _path(palette) != DEST + '/M_Wanderer':
        raise ValueError('SK_Wanderer binds only M_Wanderer')
    for package in context.outputs:
        _fresh(unreal, package)
    raw_physics = raw.get_editor_property('physics_asset')
    if raw_physics is None:
        raise ValueError('The raw Wanderer import made no physics asset')
    asset = library.duplicate_asset(_path(raw), destination)
    skeleton = library.duplicate_asset(_path(raw.get_editor_property('skeleton')), partners['skeleton'])
    physics = library.duplicate_asset(_path(raw_physics), partners['physics_asset'])
    if (not isinstance(asset, unreal.SkeletalMesh) or not isinstance(skeleton, unreal.Skeleton)
            or not isinstance(physics, unreal.PhysicsAsset)):
        raise ValueError('Wanderer skeletal bundle duplicate failed')
    if not unreal.AtelierBuildWorkerLibrary.bind_skeletal_partners(asset, skeleton, physics):
        raise ValueError('Wanderer skeletal partner binding failed')
    slots = list(asset.get_editor_property('materials'))
    if len(slots) != 1 or len(model['materials']) != 1:
        raise ValueError('The reference character should have one palette material')
    slots[0].set_editor_property('material_interface', palette)
    asset.set_editor_property('materials', slots)
    for value in (skeleton, physics, asset):
        _save(unreal, value)
    editor = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
    parents = skeleton_tree(editor, asset)
    if set(parents) != set(model['bones']) or any(parents[bone] != parent for bone, parent in model['bones'].items() if parent):
        raise ValueError('Wanderer imported bone hierarchy differs from model_manifest.json')
    if (asset.get_editor_property('skeleton') != skeleton or asset.get_editor_property('physics_asset') != physics
            or [s.get_editor_property('material_interface') for s in asset.get_editor_property('materials')] != [palette]):
        raise ValueError('SK_Wanderer bindings did not persist')
    return asset


def clip(context, unreal, args):
    params = context.params
    name = args['name']
    destination = _package(params['destination'])
    if destination != f'{DEST}/A_{name}' or list(context.outputs) != [destination]:
        raise ValueError('Clip job owns exactly its declared A_ package')
    _model, clips = export(context, args['wanderer'], f'fbx/{name}.fbx')
    if name not in clips:
        raise ValueError(f'{name}: clip is not in animation_manifest.json')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, params['source'], unreal.AnimSequence)
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    settings = _load(unreal, context, args['compression'])
    if _path(settings) != COMPRESSION or _path(skeleton) != DEST + '/SK_Wanderer_Skeleton':
        raise ValueError('Clip consumes the compact Wanderer Skeleton and shared CharacterCompression')
    _fresh(unreal, destination)
    sequence = library.duplicate_asset(_path(raw), destination)
    if not isinstance(sequence, unreal.AnimSequence) or sequence.get_editor_property('skeleton') != skeleton:
        raise ValueError('Clip is not on the compact Wanderer Skeleton: ' + destination)
    if abs(sequence.get_editor_property('sequence_length') - clips[name]['duration']) >= .02:
        raise ValueError(f'{name}: Clip duration mismatch')
    sequence.set_editor_property('enable_root_motion', False)
    compression = _module(context, 'animation_compression.py')
    compression._settings = settings
    compression.apply_to(sequence)
    _save(unreal, sequence)
    if sequence.get_editor_property('enable_root_motion') or sequence.get_editor_property('bone_compression_settings') != settings:
        raise ValueError('Clip finishing did not persist: ' + destination)
    return sequence


def blendspace(context, unreal, args):
    name = args['name']
    destination = f'{DEST}/{name}'
    if name not in INTERPOLATION or list(context.outputs) != [destination]:
        raise ValueError('Blend space job owns exactly BS_Locomotion or BS_Crouching')
    _model, settings = export(context, args['wanderer'])
    skeleton = _load(unreal, context, args['skeleton'], unreal.Skeleton)
    names = list(args['clips'])
    if any(n not in settings for n in names):
        raise ValueError(f'{name}: sample clips are not in animation_manifest.json')
    clips = [_load(unreal, context, args['clips'][n], unreal.AnimSequence) for n in names]
    if any(_path(c) != f'{DEST}/A_{n}' or c.get_editor_property('skeleton') != skeleton for c, n in zip(clips, names)):
        raise ValueError(f'{name}: sample clips are not the finished Wanderer clips')
    speeds = [settings[n].get('speed', 0) * 100 for n in names]
    _fresh(unreal, destination)
    factory = unreal.BlendSpaceFactory1D()
    factory.set_editor_property('target_skeleton', skeleton)
    blend = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DEST, unreal.BlendSpace1D, factory)
    if not isinstance(blend, unreal.BlendSpace1D) or _path(blend) != destination:
        raise ValueError('Blend space not created: ' + destination)
    params = list(blend.get_editor_property('blend_parameters'))
    for prop, value in dict(display_name='Speed (cm/s)', min=0., max=max(speeds)).items():
        params[0].set_editor_property(prop, value)
    blend.set_editor_property('blend_parameters', params)
    blend.set_editor_property('scale_animation', True)
    smoothing = list(blend.get_editor_property('interpolation_param'))
    smoothing[0].set_editor_property('interpolation_time', INTERPOLATION[name])
    blend.set_editor_property('interpolation_param', smoothing)
    if not unreal.WandererContentLibrary.configure_blend_space(blend, clips, speeds):
        raise ValueError(f'{name}: blend space samples were not configured')
    _save(unreal, blend)
    return blend


def definition(context, unreal, args):
    if list(context.outputs) != [DEFINITION]:
        raise ValueError('The selection job owns exactly /Game/Wanderer/DA_Wanderer')
    _model, settings = export(context, args['wanderer'])
    if set(args['clips']) != set(settings):
        raise ValueError('DA_Wanderer clips differ from animation_manifest.json')
    body = _load(unreal, context, args['mesh'], unreal.SkeletalMesh)
    clips = {n: _load(unreal, context, slot, unreal.AnimSequence) for n, slot in args['clips'].items()}
    moving = _load(unreal, context, args['locomotion'], unreal.BlendSpace1D)
    crouching = _load(unreal, context, args['crouching'], unreal.BlendSpace1D)
    if (_path(body) != DEST + '/SK_Wanderer' or _path(moving) != DEST + '/BS_Locomotion'
            or _path(crouching) != DEST + '/BS_Crouching' or any(_path(c) != f'{DEST}/A_{n}' for n, c in clips.items())):
        raise ValueError('DA_Wanderer consumes only the finished Wanderer V2 assets')
    _fresh(unreal, DEFINITION)
    factory = unreal.DataAssetFactory()
    factory.set_editor_property('data_asset_class', unreal.WandererDefinition)
    asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset('DA_Wanderer', '/Game/Wanderer', unreal.WandererDefinition, factory)
    if asset is None or _path(asset) != DEFINITION:
        raise ValueError('DA_Wanderer not created')
    for prop, value in dict(mesh=body, locomotion=moving, crouching=crouching, actions=clips,
                            camera_height=float(args['camera_height']),
                            walk_speed=settings['Walk']['speed'] * 100, jog_speed=settings['Jog']['speed'] * 100,
                            run_speed=settings['Run']['speed'] * 100,
                            crouch_speed=settings['CrouchWalk']['speed'] * 100).items():
        asset.set_editor_property(prop, value)
    _save(unreal, asset)
    if ({str(k) for k in asset.get_editor_property('actions')} != set(settings)
            or asset.get_editor_property('mesh') != body or asset.get_editor_property('locomotion') != moving):
        raise ValueError('DA_Wanderer lost its bindings')
    return asset


ACTIONS = {'material': material, 'mesh': mesh, 'clip': clip, 'blendspace': blendspace, 'definition': definition}
FINISHES = {'mesh': 'skeletal_mesh', 'clip': 'animation'}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-wanderer-v2-bodies
    Each job MUST author or finish exactly its declared Wanderer V2 package bundle
    from declared inputs with import_wanderer.py's settings and checks: fresh
    duplicates of raw imports, M_Wanderer's original graph, the compact Skeleton
    checked against the manifest, the shared compression and the public
    DA_Wanderer. It MUST NOT import sources, run the original or pipeline.verify,
    or write reports or packages outside its declaration.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported Wanderer action')
    kind = FINISHES.get(args['action'])
    if kind:
        if params.get('op') != 'finish' or params.get('kind') != kind:
            raise ValueError(f'{args["action"]} is finished by unreal.finish({kind})')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected Wanderer author parameters')
    return ACTIONS[args['action']](context, unreal, args)
