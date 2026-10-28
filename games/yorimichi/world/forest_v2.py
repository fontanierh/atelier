"""Native bodies for unreal.forest (Scripts/import_forest.py with import_foliage_lods), one declared owner per job.

``args.action`` selects
- ``master``: M_ForestImpostor by the original forest_impostor_material.parent on the declared T_ForestNormalDefault;
- ``impostor``: MI_<species>_Impostor as forest_impostor_material.instance binds it: the master, the species' own
  colour and normal atlas textures and its TINTS tint;
- ``leaf``: MI_<leaf>, import_forest's leaf instance: M_Foliage with the leaf's own texture as Tex;
- ``crown``: FoliageLODs/MI_<species>_Crown as import_foliage_lods.crown_material authors it;
- ``species``: the species' base /Game/Japan/Assets/<species> and its four FoliageLODs/<species>_LOD<i>
  sources, fresh duplicates of their declared raw imports, with import_forest's material, CPU, collision and height
  policy, apply_lods' bounds and assembly, the original verify_lods and forest_native.validate_current's checks;
- ``record``: forest/import-report.json and forest/native/import.json from the finished bases.
The original top level, its family inventory and retirement never run.
"""
import importlib.util
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
NAME = re.compile(r'Tree_(?:Tuscan|Forest)_[A-Za-z0-9]+\Z')
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
ASSETS, LODS = '/Game/Japan/Assets', '/Game/Japan/FoliageLODs'
MATERIALS, TEXTURES = '/Game/Japan/Materials', '/Game/Japan/Textures'
MASTER, NORMAL = MATERIALS + '/M_ForestImpostor', TEXTURES + '/T_ForestNormalDefault'
FOLIAGE, PAINTED, WHITE = MATERIALS + '/M_Foliage', MATERIALS + '/M_Painted', TEXTURES + '/T_white'
REPORT, NATIVE_REPORT = 'data/import-report.json', 'data/native-import.json'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared forest input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Forest native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls=None, package=None):
    path = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if (asset is None or _path(asset) != path or (cls is not None and not isinstance(asset, cls))
            or (package is not None and path != package)):
        raise ValueError('Declared forest input did not load as expected: ' + path)
    return asset


def _data(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared forest data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Forest data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Forest data {name} is absent')
    return json.loads(path.read_bytes())


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Forest derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    if not isinstance(value, dict):
        raise ValueError('Forest roster must be a slot map')
    return dict(value)


def _start(unreal, context, packages):
    if sorted(context.outputs) != sorted(packages):
        raise ValueError('Forest job owns exactly its declared packages')
    for package in packages:
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            raise ValueError('Forest destination must be fresh: ' + package)


def _module(context, name):
    path = Path(context.job_dir) / (SCRIPTS + name + '.py')
    if path.is_symlink() or not path.is_file():
        raise ValueError('Forest keyed code is not staged: ' + name)
    import sys
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('atelier_forest_' + name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _species(context, args):
    name = args.get('name')
    if not NAME.fullmatch(str(name)):
        raise ValueError('Unknown forest species: ' + str(name))
    data = _data(context, args['entry'], name + '.json')
    if data.get('impostor_slot') != name + '_Impostor' or data.get('crown', {}).get('slot') != name + '_Crown':
        raise ValueError(f'{name}: species entry is not its own')
    return name, data


def master(context, unreal, args):
    _start(unreal, context, [MASTER])
    normal = _load(unreal, context, args['normal'], unreal.Texture2D, NORMAL)
    material = _module(context, 'forest_impostor_material').parent(normal)
    if _path(material) != MASTER:
        raise ValueError('Forest impostor master not authored at its package')
    return material


def impostor(context, unreal, args):
    name, data = _species(context, args)
    package = f'{MATERIALS}/MI_{name}_Impostor'
    _start(unreal, context, [package])
    if data['impostor']['normal_space'] != 'camera-right-up-outward':
        raise ValueError(f'{name}: impostor normal space differs')
    source = _module(context, 'forest_impostor_material')
    master_asset = _load(unreal, context, args['master'], unreal.Material, MASTER)
    textures = {kind: _load(unreal, context, args[kind], unreal.Texture2D, f'{TEXTURES}/T_{name}_{kind}')
                for kind in ('colour', 'normal')}
    E, M = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        f'MI_{name}_Impostor', MATERIALS, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi is None or _path(mi) != package:
        raise ValueError('Forest impostor instance not created: ' + package)
    M.set_material_instance_parent(mi, master_asset)
    M.set_material_instance_texture_parameter_value(mi, 'Tex', textures['colour'])
    M.set_material_instance_texture_parameter_value(mi, 'NormalTex', textures['normal'])
    M.set_material_instance_vector_parameter_value(mi, 'Tint', unreal.LinearColor(*source.TINTS.get(name, (1., 1., 1.)), 1.))
    M.update_material_instance(mi)
    if not E.save_loaded_asset(mi, False):
        raise ValueError('Forest impostor instance save failed: ' + package)
    return mi


def leaf(context, unreal, args):
    slot = args.get('slot')
    package = f'{MATERIALS}/MI_{slot}'
    _start(unreal, context, [package])
    parent = _load(unreal, context, args['parent'], unreal.MaterialInterface, FOLIAGE)
    texture = _load(unreal, context, args['texture'], unreal.Texture2D, f'{TEXTURES}/T_{slot}')
    E, M = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_' + slot, MATERIALS, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi is None or _path(mi) != package:
        raise ValueError('Forest leaf instance not created: ' + package)
    M.set_material_instance_parent(mi, parent)
    M.set_material_instance_texture_parameter_value(mi, 'Tex', texture)
    M.update_material_instance(mi)
    if not E.save_loaded_asset(mi, False):
        raise ValueError('Forest leaf instance save failed: ' + package)
    return mi


def crown(context, unreal, args):
    name, data = _species(context, args)
    record = data['crown']
    package = f'{LODS}/MI_{record["slot"]}'
    _start(unreal, context, [package])
    helpers = _module(context, 'foliage_material')
    parent = _load(unreal, context, args['parent'], unreal.MaterialInterface, PAINTED)
    white = _load(unreal, context, args['white'], unreal.Texture2D, WHITE)
    E, M = unreal.EditorAssetLibrary, unreal.MaterialEditingLibrary
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_' + record['slot'], LODS, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if material is None or _path(material) != package:
        raise ValueError('Forest crown instance not created: ' + package)
    colour = unreal.LinearColor(*record['colour'], 1.)
    M.set_material_instance_parent(material, parent)
    M.set_material_instance_vector_parameter_value(material, 'Tint', colour)
    M.set_material_instance_texture_parameter_value(material, 'Tex', white)
    if not helpers.supports_lod_blend(material):
        helpers.enable_bark_lod_blend(material)
    M.update_material_instance(material)
    if not helpers.supports_lod_blend(material) or not E.save_loaded_asset(material, False):
        raise ValueError('Forest crown material contract failed: ' + package)
    return material


def _size(mesh):
    bounds = mesh.get_bounding_box()
    return sum((getattr(bounds.max, a) - getattr(bounds.min, a)) ** 2 for a in ('x', 'y', 'z')) ** .5


def species(context, unreal, args):
    name, data = _species(context, args)
    base = f'{ASSETS}/{name}'
    sources = [f'{LODS}/{name}_LOD{level}' for level in range(1, 5)]
    _start(unreal, context, [base, *sources])
    raws = _roster(args['levels'])
    keys = [name, *(f'{name}_LOD{level}' for level in range(1, 5))]
    if sorted(raws) != sorted(keys):
        raise ValueError('Forest finish needs exactly its five raw levels')
    library = unreal.EditorAssetLibrary
    lods_module, native = _module(context, 'import_foliage_lods'), _module(context, 'forest_native')
    native.configure({name: data})
    materials = {}
    for key, slot in args['materials'].items():
        package = (f'{LODS}/MI_{key}' if key == data['crown']['slot'] else f'{MATERIALS}/MI_{key}')
        materials[key] = _load(unreal, context, slot, unreal.MaterialInterface, package)
    palette = {data['leaf'], data['impostor_bark'], data['impostor_slot'], data['crown']['slot']}
    if set(materials) != palette:
        raise ValueError(f'{name}: forest material inputs differ from its palette')
    unreal.load_module('StaticMeshEditor')
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)

    def duplicate(key, package):
        raw_path = _selected(context, raws[key])
        if not raw_path.startswith('/Game/_Raw/') or not isinstance(library.load_asset(raw_path), unreal.StaticMesh):
            raise ValueError('Forest raw input is not a raw StaticMesh: ' + key)
        mesh = library.duplicate_asset(raw_path, package)
        if not isinstance(mesh, unreal.StaticMesh) or _path(mesh) != package or mesh.get_num_lods() != 1:
            raise ValueError('Forest raw duplicate failed: ' + package)
        return mesh

    def bind(mesh, allowed):
        for index, slot in enumerate(mesh.get_editor_property('static_materials')):
            key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
            if key not in allowed:
                raise ValueError(f'{_path(mesh)}: slot {key} is outside the original palette')
            if mesh.get_material(index) != materials[key]:
                mesh.set_material(index, materials[key])
            if mesh.get_material(index) != materials[key]:
                raise ValueError('Forest material binding did not persist: ' + key)

    mesh = duplicate(name, base)
    mesh.set_num_source_models(1)
    bind(mesh, {data['leaf'], data['impostor_bark']})
    height = mesh.get_bounding_box().max.z / 100
    if abs(height - data['height']) >= .05:
        raise ValueError(f'{name}: height {height} differs from {data["height"]}')
    mesh.set_editor_property('allow_cpu_access', False)
    mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    if not native.reusable_collision(mesh) or not native.hulls_match(mesh, data['trunk_hulls']):
        raise ValueError(f'{name}: trunk collision differs from its authored hull')
    vertices, size = meshes.get_number_verts(mesh, 0), _size(mesh)
    for level, package in enumerate(sources, 1):
        lod = duplicate(f'{name}_LOD{level}', package)
        ratio = _size(lod) / size if size > 0 else 0
        if not .8 <= ratio <= 1.15:
            raise ValueError(f'{package}: LOD bounds differ')
        bind(lod, palette)
        if not native.reusable_collision(lod) or lod.get_num_triangles(0) != data['triangles'][level]:
            raise ValueError(f'{package}: forest source LOD differs')
        if not library.save_loaded_asset(lod, False):
            raise ValueError('Forest LOD save failed: ' + package)
        if meshes.set_lod_from_static_mesh(mesh, level, lod, 0, True) != level:
            raise ValueError('Forest LOD assembly failed: ' + package)
    if not meshes.set_lod_screen_sizes(mesh, data['screen_sizes']) or meshes.get_number_verts(mesh, 0) != vertices:
        raise ValueError(f'{name}: LOD assembly changed LOD0 or refused its screen sizes')
    for level in range(5):
        settings = meshes.get_lod_build_settings(mesh, level)
        if settings.get_editor_property('use_full_precision_u_vs'):
            settings.set_editor_property('use_full_precision_u_vs', False)
            meshes.set_lod_build_settings(mesh, level, settings)

    def validate():
        lods_module.verify_lods(mesh, data['screen_sizes'], meshes, data['impostor_slot'], data['impostor_bark'],
                                crown=data['crown'], folder=LODS)
        if (mesh.get_num_lods() != 5 or not native.reusable_collision(mesh) or not native.hulls_match(mesh, data['trunk_hulls'])
                or meshes.get_collision_complexity(mesh) != unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX
                or mesh.get_editor_property('allow_cpu_access')):
            raise ValueError(f'{name}: forest base/collision differs')
        for level, count in enumerate(data['triangles']):
            if (mesh.get_num_triangles(level) != count or meshes.get_num_uv_channels(mesh, level) != 1
                    or meshes.get_lod_build_settings(mesh, level).get_editor_property('use_full_precision_u_vs')):
                raise ValueError(f'{name}: forest assembled level geometry differs')
    validate()
    if not library.save_loaded_asset(mesh, False):
        raise ValueError('Forest base save failed: ' + base)
    validate()
    return mesh


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (REPORT, NATIVE_REPORT):
        raise ValueError('The forest record job owns only its two reports')
    lods_module = _module(context, 'import_foliage_lods')
    unreal.load_module('StaticMeshEditor')
    meshes = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    report, native = {}, {}
    for name, slots in args['species'].items():
        data = _data(context, slots['entry'], name + '.json')
        mesh = _load(unreal, context, slots['base'], unreal.StaticMesh, f'{ASSETS}/{name}')
        height = mesh.get_bounding_box().max.z / 100
        report[name] = {'height_m': height, 'triangles': mesh.get_num_triangles(0)}
        native[name] = lods_module.verify_lods(mesh, data['screen_sizes'], meshes, data['impostor_slot'], data['impostor_bark'],
                                               crown=data['crown'], folder=LODS)
    report['_retired'] = []
    return {REPORT: report, NATIVE_REPORT: native}


ACTIONS = {'master': master, 'impostor': impostor, 'leaf': leaf, 'crown': crown, 'species': species, 'record': record}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-forest-native-bodies
    Each job MUST author exactly its declared forest owner from declared inputs:
    the impostor master by the original parent(), instances as the original binds
    them, the crown as crown_material, and each species' base with its four source
    LODs as fresh duplicates of their raw imports with import_forest's policy and the
    original verify_lods and current checks before and after saving. It MUST NOT run
    the original top level, inventory or retirement.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported forest action')
    if set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected forest author parameters')
    return ACTIONS[args['action']](context, unreal, args)
