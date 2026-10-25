"""Native bodies for Scripts/import_ferry.py, one declared Ferry package per job.

``args.action`` selects
- ``parent``, ``wake_material``, ``wake_mesh``: M_Ferry, M_FerryWake and FY_Wake, by the original functions
  themselves (material_parent, wake_material, wake_mesh), compiled from the staged import_ferry.py without its
  top level;
- ``instance``: one palette MaterialInstanceConstant by the original materials() from the declared manifest
  values (an FY_ instance's ship and terminal manifest values must agree, as the original writes both);
- ``mesh``: one ship or terminal mesh finished from its raw import: slots bound by name, the original
  simple-as-complex UCX policy, then ferry_native.reusable against the current assembly state that
  ferry_native.configure/configure_terminals build (without their retirement inventory).
"""
import ast
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys

NAME = re.compile(r'F[YT]_[A-Za-z0-9_]+\Z')
MATERIALS = '/Game/Ferry/Materials/'
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
FUNCTIONS = ('material_parent', 'wake_material', 'wake_mesh', 'materials')


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared Ferry input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1:
        raise ValueError('Ferry native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls):
    package = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(package)
    if not isinstance(asset, cls) or _path(asset) != package:
        raise ValueError('Declared Ferry input did not load as expected: ' + package)
    return asset


def _json(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('Ferry source must be a declared Data Item: ' + str(slot))
    path = Path(context.inputs[slot])
    if (not path.is_absolute() or path.is_symlink() or not path.is_file() or path.resolve() != path or path.name != name
            or not path.is_relative_to(Path(context.job_dir).resolve())):
        raise ValueError('Ferry source must be its exact job-local producer file: ' + name)
    return json.loads(path.read_bytes())


def _fresh(unreal, package):
    if unreal.EditorAssetLibrary.does_asset_exist(package):
        raise ValueError('Ferry destination must be fresh: ' + package)


def _staged(context, relative):
    path = Path(context.job_dir) / SCRIPTS / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original Ferry script is not staged keyed code: ' + relative)
    return path


def original(context, unreal):
    """The original import_ferry.py functions, bound to the editor globals they use; its top level never runs."""
    tree = ast.parse(_staged(context, 'import_ferry.py').read_bytes())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    if sorted(n.name for n in nodes) != sorted(FUNCTIONS):
        raise ValueError('import_ferry.py no longer defines its native functions')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('StaticMeshEditor subsystem is unavailable after loading its module')
    scope = {'unreal': unreal, 'E': unreal.EditorAssetLibrary, 'M': unreal.MaterialEditingLibrary,
             'TOOLS': unreal.AssetToolsHelpers.get_asset_tools(), 'EDITOR': editor}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'import_ferry.py', 'exec'), scope)
    return scope


def native(context):
    """Scripts/ferry_native.py with its staged helpers importable."""
    paths = [str(Path(context.job_dir) / SCRIPTS), str(Path(context.job_dir) / 'games/yorimichi/world')]
    sys.path[:0] = paths
    try:
        spec = importlib.util.spec_from_file_location('atelier_ferry_native', _staged(context, 'ferry_native.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    finally:
        for path in paths:
            sys.path.remove(path)
    return module


def _owned(context, package):
    if list(context.outputs) != [package]:
        raise ValueError('Ferry job owns exactly its declared package: ' + package)


def parent(context, unreal, args):
    _owned(context, MATERIALS + 'M_Ferry'); _fresh(unreal, MATERIALS + 'M_Ferry')
    return original(context, unreal)['material_parent']()


def wake_material(context, unreal, args):
    _owned(context, MATERIALS + 'M_FerryWake'); _fresh(unreal, MATERIALS + 'M_FerryWake')
    return original(context, unreal)['wake_material']()


def wake_mesh(context, unreal, args):
    destination = '/Game/Ferry/Ship/FY_Wake'
    _owned(context, destination); _fresh(unreal, destination)
    material = _load(unreal, context, args['material'], unreal.MaterialInterface)
    if _path(material) != MATERIALS + 'M_FerryWake':
        raise ValueError('FY_Wake binds only M_FerryWake')
    scope = original(context, unreal)
    mesh = scope['wake_mesh'](material)
    if (_path(mesh) != destination or mesh.get_material(0) != material
            or scope['EDITOR'].get_simple_collision_count(mesh) or scope['EDITOR'].get_convex_collision_count(mesh)):
        raise ValueError('FY_Wake lost its material or kept collision')
    return mesh


def instance(context, unreal, args):
    name = args['name']
    if not NAME.fullmatch(str(name)):
        raise ValueError('Unknown Ferry palette entry')
    _owned(context, MATERIALS + name); _fresh(unreal, MATERIALS + name)
    values = [_json(context, slot, 'manifest.json')['materials'].get(name) for slot in args['manifests']]
    expected = 2 if name.startswith('FY_') else 1
    if len(values) != expected or values[0] is None or any(v != values[0] for v in values):
        raise ValueError(f'{name}: ship and terminal palette values differ or are absent')
    base = _load(unreal, context, args['parent'], unreal.Material)
    if _path(base) != MATERIALS + 'M_Ferry':
        raise ValueError('Ferry instances parent M_Ferry')
    rgb, roughness, metallic = values[0]
    result = original(context, unreal)['materials'](base, {name: (rgb, roughness, metallic)})[name]
    if _path(result) != MATERIALS + name or result.get_editor_property('parent') != base:
        raise ValueError(f'{name}: instance did not bind M_Ferry')
    return result


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def state(context, args):
    """ferry_native.configure / configure_terminals over the declared Items, without the retirement inventory."""
    folder, name = args['folder'], args['name']
    manifest = _json(context, args['manifest'], 'manifest.json')
    atomic = _json(context, args['atomic'], 'atomic-manifest.json')
    if set(atomic['parents']) != set(args['parents']):
        raise ValueError('Incomplete native ferry logical roster')
    entries = {row['asset']: row for row in atomic['exports']}
    if folder == 'Ship':
        names = {*manifest['meshes'], 'FY_Collision'}
        hulls = []
        if name == 'FY_Collision':
            proxies = _json(context, args['collision_data'], 'ship-collision-data.json')
            if (proxies.get('schema') != 1 or proxies.get('asset') != 'FY_Collision'
                    or len(proxies['proxies']) != manifest['collision']['convex_hulls']):
                raise ValueError('Native ferry authored proxy closure is incomplete')
            for proxy in proxies['proxies']:
                vertices = [[_f32(x), _f32(y), _f32(z)] for heights in ('z0', 'z1') for (x, y), z in zip(proxy['poly'], proxy[heights])]
                hulls.append(dict(vertices=vertices, matrix=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]))
        elif 'collision_data' in args:
            raise ValueError('Only FY_Collision consumes the authored proxies')
        destination = '/Game/Ferry/Ship'
    else:
        names = {key for owner in manifest['terminals'].values() for key in owner['meshes']} | {'FT_HD_Collision', 'FT_BC_Collision'}
        hulls = {}
        for key, row in entries.items():
            if key.endswith('_Collision'):
                hulls[key] = row['metadata']['authored_hulls']
            else:
                if not any(key in children for children in atomic['parents'].values()):
                    raise ValueError('Foreign native terminal child')
                hulls[key] = next(owner['meshes'][key]['authored_hulls'] for owner in manifest['terminals'].values()
                                  if key in owner['meshes'])
            if len(hulls[key]) != row['metadata']['collision_hulls']:
                raise ValueError('Native terminal authored hull closure differs')
        destination = '/Game/Ferry/Terminals'
    if set(entries) != names or name not in entries:
        raise ValueError('Native ferry membership differs from its complete file assembly')
    return dict(entries=entries, hulls=hulls, destination=destination)


def mesh(context, unreal, args):
    params = context.params
    name, folder = args['name'], args['folder']
    destination, source = f'/Game/Ferry/{folder}/{name}', f'/Game/_Raw/Ferry/{folder}/{name}'
    if (not NAME.fullmatch(str(name)) or folder not in ('Ship', 'Terminals') or params.get('destination') != destination
            or params.get('source') != 'raw' or _selected(context, 'raw') != source):
        raise ValueError('Ferry mesh finish must own exactly its original package')
    _owned(context, destination)
    current = state(context, args)
    library = unreal.EditorAssetLibrary
    raw = _load(unreal, context, 'raw', unreal.StaticMesh)
    mats = {key: _load(unreal, context, slot, unreal.MaterialInterface) for key, slot in args['materials'].items()}
    if any(_path(m) != MATERIALS + key for key, m in mats.items()):
        raise ValueError('Ferry mesh materials must be the declared palette instances')
    checks = native(context)
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    _fresh(unreal, destination)
    asset = library.duplicate_asset(source, destination)
    if not isinstance(asset, unreal.StaticMesh) or asset is raw or _path(asset) != destination:
        raise ValueError('Ferry raw duplicate failed: ' + destination)
    for index, slot in enumerate(asset.static_materials):
        key = str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
        if key in mats:
            if asset.get_material(index) != mats[key]:
                asset.set_material(index, mats[key])
        elif not name.endswith('_Collision'):
            raise ValueError(f'{name}: undeclared material {key}')
    body = asset.get_editor_property('body_setup')
    if name.endswith(('_Collision', '_Brow')):
        if body.get_editor_property('collision_trace_flag') != unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX:
            body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        if editor.get_convex_collision_count(asset) <= 0:
            raise ValueError(f'{name}: missing authored convex collision')
    if not checks.reusable(asset, name, current, mats):
        raise ValueError('Current ferry native source/material/hull validation failed: ' + name)
    if not library.save_loaded_asset(asset, True):
        raise ValueError('Current ferry native save failed: ' + name)
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('Ferry native save did not leave its actual regular primary package')
    if not checks.reusable(asset, name, current, mats):
        raise ValueError('Saved ferry native source/material/hull validation failed: ' + name)
    return asset


ACTIONS = {'parent': parent, 'wake_material': wake_material, 'wake_mesh': wake_mesh, 'instance': instance, 'mesh': mesh}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-ferry-bodies
    Each job MUST author or finish exactly its declared Ferry package from declared
    inputs with import_ferry.py's own material/wake functions and mesh policy:
    agreeing palette values, a fresh duplicate of its raw import, slots bound by
    name, simple-as-complex UCX and ferry_native's current-source validation
    before and after save. It MUST NOT run the original top level, its service
    gate, retirement or reports.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported Ferry action')
    if args['action'] == 'mesh':
        if params.get('op') != 'finish' or params.get('kind') != 'static_mesh':
            raise ValueError('Ferry meshes are finished by unreal.finish(static_mesh)')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected Ferry author parameters')
    return ACTIONS[args['action']](context, unreal, args)
