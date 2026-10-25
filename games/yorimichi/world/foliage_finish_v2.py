"""Finish one foliage owner from declared raw LOD meshes; no source import, receive loop or cache access.

``op: finish`` (unreal.finish) owns the base /Game/Japan/Assets/<owner> mesh and its /Game/Japan/FoliageLODs/<owner>
LOD meshes, with import_foliage.py's slots, CPU access, collision, LOD screens, triangle,
bounds and lightmap policy. ``args.action: crown`` (unreal.author) authors the far crown's MaterialInstance exactly as
import_foliage_lods.crown_material does. Both read only the assembled manifest.json Item.
"""
import importlib.util
import json
import math
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+\Z')
NAME = re.compile(r'[A-Za-z0-9_]+\Z')
HELPERS = 'games/yorimichi/unreal/Scripts/foliage_material.py'
FIELDS = {'triangles', 'screen_sizes', 'materials', 'bounds', 'collision', 'import_trunk_collision', 'trunk_collision'}


def _package(value):
    if not isinstance(value, str) or not PACKAGE.fullmatch(value):
        raise ValueError('Expected a canonical declared /Game package')
    return value


def _selected(context, slot):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared foliage package input: ' + str(slot))
    packages = context.packages.get(slot)
    if isinstance(packages, str):
        packages = [packages]
    if not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Foliage native input must be exactly one declared package')
    return _package(packages[0])


def _pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('Duplicate foliage manifest field')
        result[key] = value
    return result


def _manifest(context, slot, owner):
    if not isinstance(slot, str) or slot not in context.inputs or context.inputs[slot] is None:
        raise ValueError('Missing declared foliage manifest Item')
    root = Path(context.inputs[slot])
    if (not root.is_absolute() or not root.is_relative_to(Path(context.job_dir)) or root.resolve() != root
            or root.is_symlink() or not root.is_dir() or root.name != owner):
        raise ValueError('Foliage manifest must be its owner\'s job-local assembled Item directory')
    path = root / 'manifest.json'
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 1024 * 1024:
        raise ValueError('Missing bounded foliage manifest')
    data = json.loads(path.read_bytes(), object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite foliage manifest')))
    if not isinstance(data, dict) or set(data) - {'crown'} != FIELDS:
        raise ValueError('Unexpected foliage manifest fields')
    sizes, counts = data['screen_sizes'], data['triangles']
    if (not isinstance(sizes, list) or len(sizes) < 2 or not isinstance(counts, list) or len(counts) != len(sizes)
            or any(type(n) is not int or n <= 0 for n in counts)
            or any(type(s) not in (int, float) or not math.isfinite(s) for s in sizes)
            or type(data['import_trunk_collision']) is not bool or data['collision'] not in ('complex', 'default')
            or (data['import_trunk_collision'] and not data['trunk_collision'])
            or not isinstance(data['materials'], list) or not data['materials']
            or any(not isinstance(key, str) or not NAME.fullmatch(key) for key in data['materials'])):
        raise ValueError('Invalid original foliage manifest policy')
    crown = data.get('crown')
    if crown is not None and (not isinstance(crown, dict) or crown.get('slot') != owner + '_Crown'
                              or not isinstance(crown.get('colour'), list) or len(crown['colour']) != 3
                              or any(type(c) not in (int, float) or not math.isfinite(c) for c in crown['colour'])):
        raise ValueError('Invalid far crown manifest record')
    return data


def _helpers(context):
    path = Path(context.job_dir) / HELPERS
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original foliage material helpers are not staged keyed code')
    spec = importlib.util.spec_from_file_location('atelier_foliage_material', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _identity(asset, package):
    if asset is None or asset.get_path_name().split('.', 1)[0] != package:
        raise ValueError('Native foliage asset resolves outside its declared package: ' + package)


def _verify_bounds(mesh, authored):
    """import_foliage.verify_bounds: authored metres against Unreal centimetres."""
    bounds = mesh.get_bounding_box()
    extents = [getattr(bounds.max, axis) - getattr(bounds.min, axis) for axis in ('x', 'y', 'z')]
    expected = [(b - a) * 100 for a, b in zip(*authored)]
    if not all(abs(a - b) < .1 for a, b in zip(extents, expected)):
        raise ValueError('Foliage native bounds differ from the authored source')


def _size(mesh):
    bounds = mesh.get_bounding_box()
    return sum((getattr(bounds.max, a) - getattr(bounds.min, a)) ** 2 for a in ('x', 'y', 'z')) ** .5


def crown(context):
    """@cc [owner:fontanierh,label:correctness] c3-foliage-crown-author
    The far crown MUST be a fresh MaterialInstanceConstant at its sole declared
    package, parented to the declared M_Painted with the manifest colour as Tint,
    the declared T_white as Tex and dithered LOD blending, as crown_material did.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if (set(params) - {'args', 'settings', 'input_roots'} or not isinstance(args, dict)
            or set(args) != {'action', 'owner', 'manifest', 'parent', 'white'} or args['action'] != 'crown'
            or not NAME.fullmatch(str(args['owner']))):
        raise ValueError('Unexpected foliage crown parameters')
    owner = args['owner']
    data = _manifest(context, args['manifest'], owner)
    if data.get('crown') is None:
        raise ValueError('Foliage manifest has no far crown')
    folder = '/Game/Japan/FoliageLODs/' + owner
    name = 'MI_' + data['crown']['slot']
    destination = folder + '/' + name
    if list(context.outputs) != [destination]:
        raise ValueError('Foliage crown owns exactly its declared material package')
    helpers = _helpers(context)
    library = unreal.EditorAssetLibrary
    parent_package, white_package = _selected(context, args['parent']), _selected(context, args['white'])
    if parent_package != '/Game/Japan/Materials/M_Painted' or white_package != '/Game/Japan/Textures/T_white':
        raise ValueError('Foliage crown inputs differ from the original M_Painted/T_white')
    parent, white = library.load_asset(parent_package), library.load_asset(white_package)
    _identity(parent, parent_package); _identity(white, white_package)
    if library.does_asset_exist(destination):
        raise ValueError('Foliage crown destination must be fresh')
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    _identity(material, destination)
    colour = unreal.LinearColor(*data['crown']['colour'], 1.)
    edit = unreal.MaterialEditingLibrary
    edit.set_material_instance_parent(material, parent)
    edit.set_material_instance_vector_parameter_value(material, 'Tint', colour)
    edit.set_material_instance_texture_parameter_value(material, 'Tex', white)
    if not helpers.supports_lod_blend(material):
        helpers.enable_bark_lod_blend(material)
    edit.update_material_instance(material)
    def validate():
        if (material.get_editor_property('parent') != parent
                or edit.get_material_instance_vector_parameter_value(material, 'Tint') != colour
                or edit.get_material_instance_texture_parameter_value(material, 'Tex') != white
                or not helpers.supports_lod_blend(material)):
            raise ValueError('Foliage crown material contract failed')
    validate()
    if not library.save_loaded_asset(material, False):
        raise ValueError('Foliage crown save failed: ' + destination)
    validate()
    return material


def finish(context):
    """@cc [owner:fontanierh,label:correctness] c3-foliage-current-finish
    Every level MUST be a fresh duplicate of its own declared raw LOD at its stable
    original package; raw inputs and shared materials are never mutated. The base
    binds the shared MI_<slot> palette, clears CPU access, applies the authored
    collision policy, assembles the saved LOD meshes with the manifest screen sizes,
    then requires the original triangles, bounds, LOD palettes, HISM blending,
    collision counts/complexity and lightmap settings before and after saving.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if (set(params) - {'op', 'kind', 'source', 'destination', 'args', 'input_roots'}
            or not {'op', 'kind', 'source', 'destination', 'args'} <= set(params)
            or params['op'] != 'finish' or params['kind'] != 'static_mesh' or not isinstance(args, dict)
            or set(args) != {'owner', 'manifest', 'levels', 'materials', 'crown'}
            or not NAME.fullmatch(str(args['owner']))):
        raise ValueError('Unexpected foliage finish parameters')
    owner = args['owner']
    data = _manifest(context, args['manifest'], owner)
    sizes, levels, crown_record = data['screen_sizes'], args['levels'], data.get('crown')
    folder = '/Game/Japan/FoliageLODs/' + owner
    base = '/Game/Japan/Assets/' + owner
    packages = [base] + [f'{folder}/{owner}_LOD{level}' for level in range(1, len(sizes))]
    if (_package(params['destination']) != base or not isinstance(levels, list) or len(levels) != len(sizes)
            or params['source'] != levels[0] or sorted(context.outputs) != sorted(packages)):
        raise ValueError('Foliage finish must own exactly its base and authored LOD packages')
    if (crown_record is None) != (args['crown'] is None):
        raise ValueError('Foliage crown input differs from the manifest far crown')
    mapping = args['materials']
    if not isinstance(mapping, dict) or set(mapping) != set(data['materials']):
        raise ValueError('Foliage material bindings differ from the original palette')
    helpers = _helpers(context)
    unreal.load_module('StaticMeshEditor')
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if meshes is None:
        raise ValueError('Required native StaticMeshEditor subsystem is unavailable')
    library = unreal.EditorAssetLibrary
    materials = {}
    for key, slot in mapping.items():
        package = _selected(context, slot)
        if package != '/Game/Japan/Materials/MI_' + key:
            raise ValueError('Foliage material input is not its shared original MI_' + key)
        material = library.load_asset(package)
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError('Declared foliage material did not load as MaterialInterface')
        _identity(material, package)
        materials[key] = material
    crown_path = None
    if crown_record is not None:
        crown_path = _selected(context, args['crown'])
        if crown_path != folder + '/MI_' + crown_record['slot']:
            raise ValueError('Foliage crown input is not this owner\'s far crown material')
        material = library.load_asset(crown_path)
        if not isinstance(material, unreal.MaterialInterface):
            raise ValueError('Declared foliage crown did not load as MaterialInterface')
        _identity(material, crown_path)
        materials[crown_record['slot']] = material
    raws = []
    for slot, package in zip(levels, packages):
        source = _selected(context, slot)
        if source in packages:
            raise ValueError('Foliage raw input and finished destination must differ')
        raw = library.load_asset(source)
        if not isinstance(raw, unreal.StaticMesh):
            raise ValueError('Foliage raw input is not a native StaticMesh')
        _identity(raw, source)
        if library.does_asset_exist(package):
            raise ValueError('Foliage finish destination must be fresh: ' + package)
        raws.append(source)
    def duplicate(source, package):
        mesh = library.duplicate_asset(source, package)
        if not isinstance(mesh, unreal.StaticMesh):
            raise ValueError('Foliage raw duplicate failed: ' + package)
        _identity(mesh, package)
        if mesh.get_num_lods() != 1:
            raise ValueError('Foliage raw LOD is not a single-level mesh')
        return mesh
    def bind(mesh, allowed):
        palette = []
        for index, value in enumerate(mesh.get_editor_property('static_materials')):
            key = str(value.get_editor_property('imported_material_slot_name')).split('.')[0]
            if key not in allowed:
                raise ValueError('Foliage native slot is outside the original palette: ' + key)
            if mesh.get_material(index) != materials[key]:
                mesh.set_material(index, materials[key])
            if mesh.get_material(index) != materials[key]:
                raise ValueError('Foliage material binding did not persist: ' + key)
            palette.append(key)
        return palette
    mesh = duplicate(raws[0], base)
    _verify_bounds(mesh, data['bounds'])
    if sorted(bind(mesh, set(data['materials']))) != sorted(data['materials']):
        raise ValueError('Foliage base material slots differ from the original palette')
    mesh.set_editor_property('allow_cpu_access', False)
    import_trunk = data['import_trunk_collision']
    if not import_trunk and not meshes.remove_collisions(mesh):
        raise ValueError('Could not clear disabled trunk collision: ' + owner)
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('Foliage mesh has no native BodySetup')
    flag = {'complex': unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE,
            'default': unreal.CollisionTraceFlag.CTF_USE_DEFAULT}[data['collision']]
    body.set_editor_property('collision_trace_flag', flag)
    vertices, size = meshes.get_number_verts(mesh, 0), _size(mesh)
    allowed = set(data['materials']) | ({crown_record['slot']} if crown_record else set())
    lods = []
    for level in range(1, len(sizes)):
        lod = duplicate(raws[level], packages[level])
        ratio = _size(lod) / size if size > 0 else 0
        if not .8 <= ratio <= 1.15:
            raise ValueError('Foliage LOD bounds differ: ' + packages[level])
        bind(lod, allowed)
        if not library.save_loaded_asset(lod, False):
            raise ValueError('Foliage LOD save failed: ' + packages[level])
        if meshes.set_lod_from_static_mesh(mesh, level, lod, 0, True) != level:
            raise ValueError('Foliage LOD assembly failed: ' + packages[level])
        lods.append(lod)
    if not meshes.set_lod_screen_sizes(mesh, sizes):
        raise ValueError('Foliage LOD screen sizes were refused')
    if meshes.get_number_verts(mesh, 0) != vertices:
        raise ValueError('Foliage LOD0 changed during LOD assembly')
    for key, value in (('light_map_resolution', 4), ('light_map_coordinate_index', 0)):
        mesh.set_editor_property(key, value)
    def validate():
        if mesh.get_num_lods() != len(sizes):
            raise ValueError('Foliage native LOD chain is incomplete')
        actual = list(meshes.get_lod_screen_sizes(mesh))
        if len(actual) != len(sizes) or not all(abs(a - b) < 1e-5 for a, b in zip(actual, sizes)):
            raise ValueError('Foliage native LOD distances differ')
        slots = [value.get_editor_property('material_interface') for value in mesh.get_editor_property('static_materials')]
        if not all(material and helpers.supports_lod_blend(material) for material in slots):
            raise ValueError('A foliage material disables HISM blending')
        palettes = [sorted({mesh.get_material(meshes.get_lod_material_slot(mesh, level, section)).get_path_name()
                            for section in range(mesh.get_num_sections(level))}) for level in range(len(sizes))]
        authored = palettes[:-1] if crown_record else palettes
        if crown_record and palettes[-1] != [crown_path + '.MI_' + crown_record['slot']]:
            raise ValueError('Foliage far crown material contract failed')
        if any(palette != authored[0] for palette in authored):
            raise ValueError('Foliage LOD changes the source palette')
        if [mesh.get_num_triangles(level) for level in range(len(sizes))] != data['triangles']:
            raise ValueError('Foliage native triangles differ from the authored source')
        _verify_bounds(mesh, data['bounds'])
        if (meshes.get_simple_collision_count(mesh) != 0
                or meshes.get_convex_collision_count(mesh) != int(import_trunk)
                or meshes.get_collision_complexity(mesh) != flag
                or mesh.get_editor_property('allow_cpu_access')
                or mesh.get_editor_property('light_map_resolution') != 4
                or mesh.get_editor_property('light_map_coordinate_index') != 0):
            raise ValueError('Foliage native collision/runtime policy failed')
        for lod in lods:
            if any(lod.get_material(index) is None for index in range(len(lod.get_editor_property('static_materials')))):
                raise ValueError('Foliage LOD lost a material binding')
    validate()
    if not library.save_loaded_asset(mesh, False):
        raise ValueError('Foliage package save failed: ' + base)
    validate()
    return mesh


def run(context):
    params = context.params
    if params.get('op') == 'finish':
        return finish(context)
    if 'op' not in params and isinstance(params.get('args'), dict) and params['args'].get('action') == 'crown':
        return crown(context)
    raise ValueError('Unsupported foliage finish body operation')
