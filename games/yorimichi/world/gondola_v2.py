"""Native bodies for Scripts/import_gondola.py, one declared ropeway package per job.

``args.action`` selects
- ``material``: one GD_<name> material (import_gondola.material) from the kit manifest's values: a linear
  constant or the declared timber colour/rough textures, metallic, translucent two-sided GD_Glass at 0.18
  opacity and emissive GD_LampGlow;
- ``mesh``: one kit or world static mesh finished from its raw import: no distance field, the original collision
  trace (authored convex hulls simple-as-complex, world non-rope meshes complex-as-simple), every slot bound by
  name (collision slots fall back to GD_DarkIron) and a rope's declared LOD1/LOD2 imported natively.
"""
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
NAME = re.compile(r'GD_[A-Za-z0-9_]+\Z')
MATERIALS = '/Game/Gondola/Materials/'
TEXTURES = '/Game/Gondola/Textures/'
SCRIPTS = 'games/yorimichi/unreal/Scripts/'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared Gondola input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Gondola native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if not isinstance(asset, cls) or _path(asset) != package:
        raise ValueError('Declared Gondola input did not load as expected: ' + package)
    return asset


def _file(context, slot, name):
    """One declared Data Item restored as its single producer file."""
    if not isinstance(slot, str) or context.inputs.get(slot) is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('Gondola source must be a declared Data Item: ' + str(slot))
    path = Path(context.inputs[slot])
    if (not path.is_absolute() or path.is_symlink() or not path.is_file() or path.resolve() != path or path.name != name
            or not path.is_relative_to(Path(context.job_dir).resolve())):
        raise ValueError('Gondola source must be its exact job-local producer file: ' + name)
    return path


def _module(context, relative):
    path = Path(context.job_dir) / SCRIPTS / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original helper is not staged keyed code: ' + relative)
    spec = importlib.util.spec_from_file_location('atelier_gondola_' + relative.removesuffix('.py'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fresh(unreal, package):
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('Gondola destination must be fresh: ' + package)


def _linear(value):
    value /= 255.
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def material(context, unreal, args):
    name = args['name']
    destination = MATERIALS + name
    if not NAME.fullmatch(str(name)) or list(context.outputs) != [destination]:
        raise ValueError('Gondola material job owns exactly its declared package')
    manifest = json.loads(_file(context, args['manifest'], 'manifest.json').read_bytes())
    rgb, roughness, metallic = manifest['materials'][name]
    texture = manifest['textured_materials'].get(name)
    if bool(texture) != ('color' in args) or set(args) - {'action', 'name', 'manifest', 'color', 'rough'}:
        raise ValueError(f'{name}: declared texture inputs differ from the kit manifest')
    helpers = _module(context, 'material_assets.py')
    M = unreal.MaterialEditingLibrary
    _fresh(unreal, destination)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, MATERIALS.rstrip('/'), unreal.Material,
                                                                  unreal.MaterialFactoryNew())
    if not isinstance(mat, unreal.Material) or _path(mat) != destination:
        raise ValueError('Gondola material not created: ' + destination)
    M.delete_all_material_expressions(mat)
    if texture:
        color = _load(unreal, context, args['color'], unreal.Texture)
        rough = _load(unreal, context, args['rough'], unreal.Texture)
        if (_path(color) != f'{TEXTURES}GD_{texture}_color' or _path(rough) != f'{TEXTURES}GD_{texture}_rough'
                or rough.get_editor_property('srgb')):
            raise ValueError(f'{name}: timber textures differ from the kit manifest')
        c = helpers.node(mat, unreal.MaterialExpressionTextureSample, -300, 0, texture=color)
        r = helpers.node(mat, unreal.MaterialExpressionTextureSample, -300, 160, texture=rough,
                         sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    else:
        c = helpers.node(mat, unreal.MaterialExpressionConstant3Vector, -300, 0,
                         constant=unreal.LinearColor(*(_linear(v) for v in rgb), 1.))
        r = helpers.node(mat, unreal.MaterialExpressionConstant, -300, 160, r=roughness)
    connected = [M.connect_material_property(c, '', unreal.MaterialProperty.MP_BASE_COLOR),
                 M.connect_material_property(r, 'R' if texture else '', unreal.MaterialProperty.MP_ROUGHNESS)]
    metal = helpers.node(mat, unreal.MaterialExpressionConstant, -300, 300, r=metallic)
    connected.append(M.connect_material_property(metal, '', unreal.MaterialProperty.MP_METALLIC))
    if name == 'GD_Glass':
        mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_TRANSLUCENT)
        mat.set_editor_property('two_sided', True)
        opacity = helpers.node(mat, unreal.MaterialExpressionConstant, -300, 450, r=.18)
        connected.append(M.connect_material_property(opacity, '', unreal.MaterialProperty.MP_OPACITY))
    else:
        mat.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
    if name == 'GD_LampGlow':
        connected.append(M.connect_material_property(c, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR))
    if not all(connected):
        raise ValueError(f'{name}: material graph not connected')
    helpers.save_material(mat)
    return mat


def mesh(context, unreal, args):
    params = context.params
    name, folder = args['name'], args['folder']
    destination = f'/Game/Gondola/{folder}/{name}'
    source = f'/Game/_Raw/Gondola/{folder}/{name}'
    collision = name.endswith('_Collision')
    rope = name.endswith('_Rope_LOD0')
    if (not NAME.fullmatch(str(name)) or folder not in ('Kit', 'World') or params.get('destination') != destination
            or list(context.outputs) != [destination] or params.get('source') != 'raw'
            or _selected(context, 'raw') != source or set(args['lods']) != ({'1', '2'} if rope and folder == 'World' else set())):
        raise ValueError('Gondola mesh finish must own exactly its original package and detail levels')
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, 'raw', unreal.StaticMesh)
    mats = {key: _load(unreal, context, slot, unreal.MaterialInterface) for key, slot in args['materials'].items()}
    if any(_path(m) != MATERIALS + key for key, m in mats.items()) or 'GD_DarkIron' not in mats:
        raise ValueError('Gondola mesh materials must be the declared GD palette')
    lods = {int(level): _file(context, slot, f'{name[:-1]}{level}.fbx') for level, slot in args['lods'].items()}
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('StaticMeshEditor subsystem is unavailable after loading its module')
    _fresh(unreal, destination)
    asset = library.duplicate_asset(source, destination)
    if not isinstance(asset, unreal.StaticMesh) or asset is raw or _path(asset) != destination:
        raise ValueError('Gondola raw duplicate failed: ' + destination)
    asset.set_editor_property('generate_mesh_distance_field', False)
    body = asset.get_editor_property('body_setup')
    if body is None:
        raise ValueError(name + ': mesh has no BodySetup')
    if collision:
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        if editor.get_convex_collision_count(asset) <= 0:
            raise ValueError(name + ': missing authored convex collision')
    elif folder == 'World' and '_Rope_' not in name:
        body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    trace = body.get_editor_property('collision_trace_flag')
    slots = []
    for slot in asset.static_materials:
        key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        if key not in mats and not collision:
            raise ValueError(name + ': unknown material ' + key)
        slots.append(mats.get(key, mats['GD_DarkIron']))
    if slots:
        _module(context, 'mesh_materials.py').assign_materials(asset, slots)
    for level, path in sorted(lods.items()):
        if editor.import_lod(asset, level, str(path)) != level:
            raise ValueError(name + ': failed rope LOD import')
    if rope and asset.get_num_lods() != 3:
        raise ValueError(name + ': incomplete rope detail levels')
    hulls = editor.get_convex_collision_count(asset)
    if not library.save_loaded_asset(asset, False):
        raise ValueError('Gondola mesh save failed: ' + destination)
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('Gondola native save did not leave its actual regular primary package')
    if ([s.get_editor_property('material_interface') for s in asset.static_materials] != slots
            or body.get_editor_property('collision_trace_flag') != trace or asset.get_editor_property('generate_mesh_distance_field')
            or editor.get_convex_collision_count(asset) != hulls or (collision and hulls <= 0)):
        raise ValueError(name + ': finished bindings did not persist')
    return asset


ACTIONS = {'material': material, 'mesh': mesh}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-gondola-bodies
    Each job MUST author or finish exactly its declared ropeway package from
    declared inputs with import_gondola.py's settings and checks: the manifest's
    material values and textures, a fresh duplicate of its raw import, the
    original collision trace and convex-hull gate, slots bound by name and the
    rope's declared detail levels. It MUST NOT import sources other than declared
    rope LODs, run the original or its service validation, or write reports.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported Gondola action')
    if args['action'] == 'mesh':
        if (params.get('op') != 'finish' or params.get('kind') != 'static_mesh'
                or set(args) != {'action', 'name', 'folder', 'materials', 'lods'}):
            raise ValueError('Gondola meshes are finished by unreal.finish(static_mesh)')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected Gondola author parameters')
    return ACTIONS[args['action']](context, unreal, args)
