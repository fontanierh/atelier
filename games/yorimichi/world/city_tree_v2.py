"""Native bodies for unreal.city_tree_lods (Scripts/import_city_tree_atomic.py), one declared package per job.

``args.action`` selects
- ``lod`` (unreal.finish): CityTrees/v4/lods/<P>_LOD<n><sfx>, a fresh duplicate of its raw import on the parent's
  original material with the original source checks against its own export receipt: one slot, its triangles, its
  native bounds within 0.2 cm, full-precision UVs and no collision;
- ``base`` (unreal.finish): CityTrees/v4/<P><sfx>_v4, a fresh duplicate of its declared city-finished original
  with its two finished lower levels and the original's checks: one LOD, triangles, single section and CPU access
  on the original; each level's bounds ratio, three LODs with full-precision UVs and the original material, the
  original's collision, bounds and the policy screen sizes;
- ``record``: city_tree_lods/v4/import-report.json from the finished trees.
The original top level, namespace inventory, protected-file scan and retirement never run.
"""
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
SURFACES = '/Game/Experiments/CitySurfaces/v1_128m'
DEST = '/Game/Experiments/CityTrees/v4'
EMPTY = 'games/yorimichi/unreal/Scripts/import_city_surface_tiles.py'
RECORD = 'data/import-report.json'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared city tree input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('City tree native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, package=None):
    path = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None or _path(asset) != path or (package is not None and path != package):
        raise ValueError('Declared city tree input did not load as expected: ' + path)
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared city tree data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('City tree data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'City tree data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    if not isinstance(value, dict) or set(value) != {'derived_items'} or not isinstance(value['derived_items'], dict):
        raise ValueError('City tree roster must be a derived token')
    rows = value['derived_items'].get('members')
    if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
        raise ValueError('City tree derived roster is unresolved')
    return {r['piece']: r['slot'] for r in rows}


def _fresh(unreal, context, destination):
    if list(context.outputs) != [destination] or unreal.EditorAssetLibrary.does_asset_exist(destination):
        raise ValueError('City tree job owns exactly its fresh declared package: ' + destination)


def _module(context, relative, name):
    path = Path(context.job_dir) / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('City tree keyed code is not staged: ' + relative)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _receipt(context, slot, name):
    receipt = _data(context, slot, 'export.json')
    bounds = receipt.get('bounds')
    if (receipt.get('asset') != name or receipt.get('primary') != name + '.fbx' or type(receipt.get('triangles')) is not int
            or not isinstance(bounds, list) or len(bounds) != 2 or any(not isinstance(v, list) or len(v) != 3 for v in bounds)):
        raise ValueError('City tree export receipt is not its own child: ' + name)
    return receipt


def _native_bounds(bounds):
    """city_tile_products.native_bounds: Blender metres (+Y forward) to Unreal centimetres (+Y right)."""
    (x0, y0, z0), (x1, y1, z1) = bounds
    return (x0 * 100, -y1 * 100, z0 * 100), (x1 * 100, -y0 * 100, z1 * 100)


def lod(context, unreal, args):
    params = context.params
    parent, level, piece = args['parent'], args['level'], args['piece']
    if level not in (1, 2) or not str(piece).startswith(f'{parent}_LOD{level}'):
        raise ValueError('City tree lower level is not its parent level: ' + str(piece))
    destination = f'{DEST}/lods/{piece}'
    if params.get('destination') != destination:
        raise ValueError('City tree lower level owns exactly ' + destination)
    _fresh(unreal, context, destination)
    receipt = _receipt(context, args['export'], piece)
    material = _load(unreal, context, args['material'])
    library = unreal.EditorAssetLibrary
    raw_path = _selected(context, 'raw')
    if raw_path != '/Game/_Raw/CityTrees/' + piece or not isinstance(library.load_asset(raw_path), unreal.StaticMesh):
        raise ValueError('City tree raw input is not its raw StaticMesh: ' + piece)
    unreal.load_module('StaticMeshEditor')
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    source = library.duplicate_asset(raw_path, destination)
    if not isinstance(source, unreal.StaticMesh) or _path(source) != destination:
        raise ValueError('City tree raw duplicate failed: ' + destination)
    if source.get_material(0) != material:
        source.set_material(0, material)
    settings = meshes.get_lod_build_settings(source, 0)
    if not settings.get_editor_property('use_full_precision_u_vs'):
        settings.set_editor_property('use_full_precision_u_vs', True)
        meshes.set_lod_build_settings(source, 0, settings)
    _module(context, EMPTY, 'atelier_city_tree_empty').finish_empty_collision(
        source, {'name': piece, 'collision_hulls': 0}, meshes)
    minimum, maximum = _native_bounds(receipt['bounds'])

    def validate():
        if len(source.static_materials) != 1 or source.get_num_triangles(0) != receipt['triangles']:
            raise ValueError(f'{piece}: lower level slots/triangles differ')
        box = source.get_bounding_box()
        if not all(abs(getattr(box.min, axis) - minimum[i]) < .2 and abs(getattr(box.max, axis) - maximum[i]) < .2
                   for i, axis in enumerate('xyz')):
            raise ValueError(f'{piece}: current source bounds')
        if (source.get_material(0) != material
                or not meshes.get_lod_build_settings(source, 0).get_editor_property('use_full_precision_u_vs')
                or meshes.get_simple_collision_count(source) or meshes.get_convex_collision_count(source)):
            raise ValueError(f'{piece}: lower level material/UV/collision policy failed')
    validate()
    if not library.save_loaded_asset(source, False):
        raise ValueError('City tree lower level save failed: ' + destination)
    validate()
    return source


def base(context, unreal, args):
    params = context.params
    parent, piece = args['parent'], args['piece']
    if not str(piece).startswith(parent):
        raise ValueError('City tree piece is not its parent: ' + str(piece))
    destination = f'{DEST}/{piece}_v4'
    if params.get('destination') != destination or params.get('source') != 'original':
        raise ValueError('City tree base owns exactly ' + destination)
    _fresh(unreal, context, destination)
    receipt = _receipt(context, args['export'], piece)
    facts = _data(context, args['facts'], 'plan.json')
    if facts.get('parent') != parent:
        raise ValueError('City tree parent facts are not its parent')
    library = unreal.EditorAssetLibrary
    original = _load(unreal, context, 'original', f'{SURFACES}/{piece}')
    triangles = receipt['triangles']
    if (original.get_num_lods() != 1 or original.get_num_triangles(0) != triangles or original.get_num_sections(0) != 1
            or not original.get_editor_property('allow_cpu_access')):
        raise ValueError(f'{piece}: city-finished original differs')
    material = _load(unreal, context, args['material'])
    if original.get_material(0) != material:
        raise ValueError(f'{piece}: original material differs from the parent policy')
    lods = {}
    for level in (1, 2):
        expected = f'{parent}_LOD{level}{piece[len(parent):]}'
        members = _roster(args['lods'][str(level)])
        if list(members) != [expected]:
            raise ValueError(f'{piece}: lower level {level} is not its own sibling')
        lods[level] = _load(unreal, context, members[expected], f'{DEST}/lods/{expected}')
    unreal.load_module('StaticMeshEditor')
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    target = library.duplicate_asset(_path(original), destination)
    if not isinstance(target, unreal.StaticMesh) or _path(target) != destination:
        raise ValueError('City tree base duplicate failed: ' + destination)
    if target.get_num_lods() > 1:
        target.set_num_source_models(1)
    radius = original.get_bounds().sphere_radius
    for level, source in lods.items():
        ratio = source.get_bounds().sphere_radius / radius
        if not .85 < ratio < 1.05:
            raise ValueError(f'{piece}: lower LOD units/bounds {ratio}')
        if meshes.set_lod_from_static_mesh(target, level, source, 0, True) != level:
            raise ValueError(f'{piece}: LOD {level} assembly failed')
    target.set_editor_property('lod_for_collision', 0)
    if not target.get_editor_property('allow_cpu_access'):
        target.set_editor_property('allow_cpu_access', True)
    if not meshes.set_lod_screen_sizes(target, args['screen_sizes']):
        raise ValueError(f'{piece}: screen sizes refused')
    hulls = json.loads(unreal.CitySurfaceValidation.collision_vertices(original))

    def validate():
        if target.get_num_lods() != 3 or target.get_num_triangles(0) != triangles:
            raise ValueError(f'{piece}: tree LOD chain differs')
        if not all(meshes.get_lod_build_settings(target, level).get_editor_property('use_full_precision_u_vs') for level in range(3)):
            raise ValueError(f'{piece}: tree UV precision differs')
        if not all(target.get_num_sections(level) == 1
                   and target.get_material(meshes.get_lod_material_slot(target, level, 0)) == material for level in range(3)):
            raise ValueError(f'{piece}: tree LOD material differs')
        if (json.loads(unreal.CitySurfaceValidation.collision_vertices(target)) != hulls
                or not unreal.CitySurfaceValidation.validate_collision(target, triangles, bool(facts['source_collision_hulls']))):
            raise ValueError(f'{piece}: authored hulls')
        for field in ('origin', 'box_extent'):
            for axis in 'xyz':
                if abs(getattr(getattr(target.get_bounds(), field), axis) - getattr(getattr(original.get_bounds(), field), axis)) >= 1.:
                    raise ValueError(f'{piece}: bounds {field} {axis}')
        actual = list(meshes.get_lod_screen_sizes(target))
        if len(actual) != 3 or not all(abs(a - b) < 1e-5 for a, b in zip(actual, args['screen_sizes'])):
            raise ValueError(f'{piece}: screen sizes differ')
    validate()
    if not library.save_loaded_asset(target, False):
        raise ValueError('City tree base save failed: ' + destination)
    validate()
    return target


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (RECORD,):
        raise ValueError('The city tree record job owns only its report')
    pieces = {}
    for name, slot in sorted(_roster(args['trees']).items()):
        target = _load(unreal, context, slot, f'{DEST}/{name}_v4')
        pieces[name] = {'asset': target.get_path_name(), 'original': f'{SURFACES}/{name}.{name}',
                        'triangles': [target.get_num_triangles(level) for level in range(3)],
                        'screen_sizes': list(args['screen_sizes'])}
    if not pieces:
        raise ValueError('City tree record has no finished trees')
    packages = sorted([f'{DEST}/{name}_v4' for name in pieces])
    return {RECORD: {'complete': True, 'pieces': pieces, 'packages': packages}}


ACTIONS = {'lod': lod, 'base': base, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-city-tree-lod-bodies
    Each job MUST own exactly its declared package: a lower level as a fresh
    duplicate of its raw import with the original receipt checks, or a tree base
    as a fresh duplicate of its declared city-finished original with exactly its own
    two finished lower levels and the original's LOD, material, collision, bounds
    and screen-size checks before and after its save. Inputs stay read-only; the
    original top level, inventory and retirement never run.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported city tree action')
    if args['action'] in ('lod', 'base'):
        if params.get('op') != 'finish' or params.get('kind') != 'static_mesh':
            raise ValueError('A city tree mesh is finished by unreal.finish(static_mesh)')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected city tree author parameters')
    return ACTIONS[args['action']](context, unreal, args)
