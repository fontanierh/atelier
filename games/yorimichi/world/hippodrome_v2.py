"""Native bodies for unreal.hippodrome (Scripts/import_hippodrome.py), one declared /Game/Hippodrome owner per job.

``args.action`` selects
- ``texture``: T_Grass or T_Dirt from its raw import with the original megapark texture() settings (sRGB colour,
  default compression, wrapped addressing);
- ``structure`` and ``surface``: M_HD_Structure and M_HD_<Surface> by the original functions, a surface's map the
  declared finished texture in place of the helper's import;
- ``paint``: a structure piece's restyled instance: M_HD_Structure with the piece's own painted map, by the original
  restyle();
- ``mesh``: SM_HD_<child> from its raw GLB import: the original triangle, one-slot, material, complex-as-simple
  collision and y-mirrored bounds checks against the child's own export receipt;
- ``data``: Content/Data/hippodrome/hippodrome.json, the region's venue data;
- ``record``: hippodrome/import-report.json from the finished meshes.
The original top level, its reuse bookkeeping and its directory retire never run.
"""
import ast
import json
from pathlib import Path
import re

PACKAGE = re.compile(r'/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\Z')
ROOT = '/Game/Hippodrome'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_hippodrome.py'
DATA = 'data/hippodrome.json'
REPORT = 'data/import-report.json'


def _path(asset):
    return asset.get_path_name().split('.', 1)[0]


def _selected(context, slot):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared hippodrome input: ' + str(slot))
    packages = context.packages.get(slot)
    packages = [packages] if isinstance(packages, str) else packages
    if not isinstance(packages, (list, tuple)) or len(packages) != 1 or not PACKAGE.fullmatch(str(packages[0])):
        raise ValueError('Hippodrome native input must be exactly one declared package: ' + slot)
    return packages[0]


def _load(unreal, context, slot, cls=None, package=None):
    path = _selected(context, slot)
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if (asset is None or _path(asset) != path or (cls is not None and not isinstance(asset, cls))
            or (package is not None and path != package)):
        raise ValueError('Declared hippodrome input did not load as expected: ' + path)
    return asset


def _file(context, slot, name):
    if not isinstance(slot, str) or context.inputs.get(slot) is None:
        raise ValueError('Missing declared hippodrome data: ' + str(slot))
    root = Path(context.inputs[slot])
    if not root.is_absolute() or root.is_symlink() or not root.resolve().is_relative_to(Path(context.job_dir).resolve()):
        raise ValueError('Hippodrome data must be a job-local declared input')
    path = root / name if root.is_dir() else root
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'Hippodrome data {name} is absent')
    return path


def _roster(value):
    if isinstance(value, dict) and set(value) == {'derived_items'}:
        rows = value['derived_items'].get('members') if isinstance(value['derived_items'], dict) else None
        if not isinstance(rows, list) or any(not isinstance(r, dict) or 'piece' not in r or 'slot' not in r for r in rows):
            raise ValueError('Hippodrome derived roster is unresolved')
        return {r['piece']: r['slot'] for r in rows}
    raise ValueError('Hippodrome roster must be a derived token')


def _start(unreal, context, packages):
    if sorted(context.outputs) != sorted(packages):
        raise ValueError('Hippodrome job owns exactly its declared packages')
    for package in packages:
        if unreal.EditorAssetLibrary.does_asset_exist(package):
            raise ValueError('Hippodrome destination must be fresh: ' + package)


def original(source):
    """The original SURFACES and its surface, structure_material and restyle functions, without its top level."""
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('surface', 'structure_material', 'restyle')}
    surfaces = [n for n in tree.body if isinstance(n, ast.Assign) and [getattr(t, 'id', None) for t in n.targets] == ['SURFACES']]
    if len(functions) != 3 or len(surfaces) != 1:
        raise ValueError('import_hippodrome.py no longer has its surface, structure and restyle functions')
    return ast.literal_eval(surfaces[0].value), ast.Module(body=list(functions.values()), type_ignores=[])


def _scope(context, unreal, **extra):
    source = Path(context.job_dir) / ORIGINAL
    if source.is_symlink() or not source.is_file():
        raise ValueError('import_hippodrome.py is not staged keyed code')
    surfaces, module = original(source.read_text())
    scope = {'unreal': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
             'MEL': unreal.MaterialEditingLibrary, 'ROOT': ROOT, 'SURFACES': surfaces, **extra}
    exec(compile(module, ORIGINAL, 'exec'), scope)
    return scope


def texture(context, unreal, args):
    params = context.params
    destination = params['destination']
    _start(unreal, context, [destination])
    raw = _load(unreal, context, params['source'], unreal.Texture2D)
    tex = unreal.EditorAssetLibrary.duplicate_asset(_path(raw), destination)
    if not isinstance(tex, unreal.Texture2D):
        raise ValueError('Hippodrome texture duplicate failed: ' + destination)
    # import_megapark.texture(..., wrap=True): colour, default compression, wrapped in both axes.
    tex.set_editor_property('srgb', True)
    tex.set_editor_property('compression_settings', unreal.TextureCompressionSettings.TC_DEFAULT)
    tex.set_editor_property('address_x', unreal.TextureAddress.TA_WRAP); tex.set_editor_property('address_y', unreal.TextureAddress.TA_WRAP)
    if not unreal.EditorAssetLibrary.save_loaded_asset(tex, False):
        raise ValueError('Hippodrome texture save failed: ' + destination)
    return tex


def structure(context, unreal, args):
    package = ROOT + '/Materials/M_HD_Structure'
    _start(unreal, context, [package])
    material = _scope(context, unreal)['structure_material']()
    if _path(material) != package:
        raise ValueError('M_HD_Structure not authored at its package')
    return material


def surface(context, unreal, args):
    key = args['key']
    package = f'{ROOT}/Materials/M_{key}'
    _start(unreal, context, [package])
    declared = _load(unreal, context, args['texture'], unreal.Texture2D, f'{ROOT}/Textures/T_{key[3:]}') if 'texture' in args else None

    def finished(path, name, dest=None, wrap=False):
        if declared is None or name != f'T_{key[3:]}' or dest != ROOT + '/Textures' or not wrap:
            raise ValueError('The surface texture call differs from its declared finished texture')
        return declared
    scope = _scope(context, unreal, helper={'texture': finished}, OUT=Path(context.job_dir) / 'unused')
    spec = scope['SURFACES'].get(key)
    if spec is None or isinstance(spec[0], str) != (declared is not None):
        raise ValueError('Hippodrome surface differs from the original SURFACES')
    material = scope['surface'](key, *spec)
    if _path(material) != package:
        raise ValueError('Hippodrome surface not authored at its package')
    return material


def paint(context, unreal, args):
    folder = f'{ROOT}/Meshes/{args["name"]}'
    package = f'{folder}/MI_{args["name"]}'
    _start(unreal, context, [package])
    master = _load(unreal, context, args['master'], unreal.Material, ROOT + '/Materials/M_HD_Structure')
    albedo = _load(unreal, context, args['texture'], unreal.Texture2D, f'{folder}/T_{args["name"]}')
    instance = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        f'MI_{args["name"]}', folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if instance is None or _path(instance) != package:
        raise ValueError('Hippodrome paint instance not created: ' + package)
    # The imported glTF instance carried the painted map as BaseColorTexture; restyle keeps only that map.
    MEL = unreal.MaterialEditingLibrary
    MEL.set_material_instance_texture_parameter_value(instance, 'BaseColorTexture', albedo)
    instance = _scope(context, unreal)['restyle'](instance, master)
    if (instance.get_editor_property('parent') != master
            or MEL.get_material_instance_texture_parameter_value(instance, 'BaseColorTexture') != albedo):
        raise ValueError('Hippodrome paint instance differs from the restyled original')
    return instance


def _receipt(context, slot, piece):
    receipt = json.loads(_file(context, slot, 'export.json').read_bytes())
    metadata = receipt.get('metadata')
    if (receipt.get('asset') != piece or not isinstance(metadata, dict) or type(metadata.get('triangles')) is not int
            or metadata['triangles'] != receipt.get('triangles') or not isinstance(metadata.get('material'), str)
            or any(not isinstance(metadata.get(k), list) or len(metadata[k]) != 3 for k in ('min', 'max'))):
        raise ValueError('Hippodrome child receipt is not its own complete export: ' + str(piece))
    return metadata


def mesh(context, unreal, args):
    params = context.params
    piece, destination = args['piece'], params['destination']
    if destination != f'{ROOT}/{piece}':
        raise ValueError('Hippodrome mesh destination differs from its child')
    _start(unreal, context, [destination])
    expected = _receipt(context, args['export'], piece)
    E = unreal.EditorAssetLibrary
    if 'surfaces' in args:
        surfaces = {key: _load(unreal, context, slot, unreal.Material, f'{ROOT}/Materials/M_{key}') for key, slot in args['surfaces'].items()}
        if expected['material'] not in surfaces:
            raise ValueError(f'{piece}: report material is not an original surface')
        material = surfaces[expected['material']]
    else:
        if expected['material'] in args.get('surface_keys', ()):
            raise ValueError(f'{piece}: a structure child names a surface material')
        master = _load(unreal, context, args['master'], unreal.Material, ROOT + '/Materials/M_HD_Structure')
        paints = _roster(args['paint'])
        if list(paints) != [piece]:
            raise ValueError(f'{piece}: the paint join is not exactly its own instance')
        material = _load(unreal, context, paints[piece], unreal.MaterialInstanceConstant, f'{ROOT}/Meshes/{piece}/MI_{piece}')
        if material.get_editor_property('parent') != master:
            raise ValueError(f'{piece}: paint instance is not on M_HD_Structure')
    raw = _load(unreal, context, params['source'], unreal.StaticMesh)
    asset = E.duplicate_asset(_path(raw), destination)
    if not isinstance(asset, unreal.StaticMesh):
        raise ValueError('Hippodrome mesh duplicate failed: ' + destination)
    if asset.get_num_triangles(0) != expected['triangles']:
        raise ValueError(f'{piece}: {asset.get_num_triangles(0)} triangles, report {expected["triangles"]}')
    if len(list(asset.get_editor_property('static_materials'))) != 1:
        raise ValueError(f'{piece}: one material slot expected')
    asset.set_material(0, material)
    body = asset.get_editor_property('body_setup')
    if not body:
        raise ValueError(f'{piece}: no body setup')
    body.set_editor_property('collision_trace_flag', unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('double_sided_geometry', True)
    if not E.save_loaded_asset(asset, False):
        raise ValueError('Hippodrome mesh save failed: ' + destination)
    box, lo, hi = asset.get_bounding_box(), expected['min'], expected['max']
    actual = [box.min.x, box.min.y, box.min.z, box.max.x, box.max.y, box.max.z]
    wanted = [lo[0] * 100, -hi[1] * 100, lo[2] * 100, hi[0] * 100, -lo[1] * 100, hi[2] * 100]
    if max(abs(a - b) for a, b in zip(actual, wanted)) >= 1.:
        raise ValueError(f'{piece}: unit/axis conversion {actual} {wanted}')
    if asset.get_material(0) != material:
        raise ValueError(f'{piece}: material did not bind')
    return asset


def data(context, unreal, args):
    """shutil.copy2 of the region's hippodrome.json, as the worker's one exact JSON result (equal JSON, its formatting)."""
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (DATA,):
        raise ValueError('The hippodrome data job owns only its venue data')
    return {DATA: json.loads(_file(context, args['region'], 'hippodrome.json').read_bytes())}


def record(context, unreal, args):
    if list(context.outputs) or tuple(getattr(context, 'data_outputs', ())) != (REPORT,):
        raise ValueError('The hippodrome record job owns only its report')
    data = json.loads(_file(context, args['region'], 'hippodrome.json').read_bytes())
    meshes = {}
    for token in args['meshes']:
        meshes.update(_roster(token))
    if sorted(meshes) != sorted(entry['name'] for entry in data['meshes']):
        raise ValueError('Finished hippodrome meshes differ from the venue data')
    result = {}
    for entry in data['meshes']:
        name = entry['name']
        asset = _load(unreal, context, meshes[name], unreal.StaticMesh, f'{ROOT}/{name}')
        box = asset.get_bounding_box()
        result[name] = {'triangles': asset.get_num_triangles(0),
                        'bounds_cm': [[box.min.x, box.min.y, box.min.z], [box.max.x, box.max.y, box.max.z]]}
    return {REPORT: result}


ACTIONS = {'texture': texture, 'structure': structure, 'surface': surface, 'paint': paint, 'mesh': mesh, 'data': data,
           'record': record}
FINISHES = {'texture': 'texture', 'mesh': 'static_mesh'}


def run(context):
    """@cc [owner:fontanierh,label:correctness] c3-hippodrome-native-bodies
    Each job MUST author or finish exactly its declared /Game/Hippodrome owner (or
    the venue data and report) from declared inputs: textures with the original
    settings, materials by the original functions on declared textures, structure
    paints by the original restyle, meshes with the original triangle, slot,
    material, collision and bounds checks against their own export receipt. It
    MUST NOT run the original top level, its reuse bookkeeping or retire scan.
    """
    import unreal
    params = context.params
    args = params.get('args')
    if not isinstance(args, dict) or args.get('action') not in ACTIONS:
        raise ValueError('Unsupported hippodrome action')
    kind = FINISHES.get(args['action'])
    if kind:
        if params.get('op') != 'finish' or params.get('kind') != kind:
            raise ValueError(f'A hippodrome {args["action"]} is finished by unreal.finish({kind})')
    elif set(params) - {'args', 'settings', 'input_roots'}:
        raise ValueError('Unexpected hippodrome author parameters')
    return ACTIONS[args['action']](context, unreal, args)
