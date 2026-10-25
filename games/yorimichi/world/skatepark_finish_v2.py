"""One Sunset Pier material or selected park/board mesh per native job."""
import ast
import hashlib
import json
from pathlib import Path

from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.export_manifest import validate as validate_export
from island_finish_v2 import _identity, _pairs, _selected
from mega_finish_v2 import _path
from megapark_v2 import _data, _derived, _fresh, _load, _owned
from skatepark_members_v2 import read_json, pieces_module

ROOT = '/Game/SkatePark'
ORIGINAL = 'games/yorimichi/unreal/Scripts/import_skatepark.py'
VILLAGE = '/Game/Japan/Materials/M_Village'
BOARD = ('SM_SkateDeck', 'SM_SkateTruck', 'SM_SkateWheel')


def material(context, unreal, args):
    key = args['piece']
    selected = _data(context, 'spec', directory=True)
    if {p.name for p in selected.iterdir()} != {key + '.json'}:
        raise ValueError('Sunset Pier material requires exactly its selected spec')
    spec = read_json(selected / (key + '.json'))
    if set(spec) != {'key', 'entry'} or spec['key'] != key:
        raise ValueError('Foreign Sunset Pier selected material')
    package = ROOT + '/Materials/M_Pier_' + key
    _owned(context, package); _fresh(unreal, package)
    textures = {}
    for role, descriptor in args['textures'].items():
        for row in _derived(descriptor):
            if row['piece'] == key + '_' + role:
                texture = _load(unreal, context, row['slot'], unreal.Texture)
                _identity(texture, ROOT + '/Textures/T_Pier_' + key + '_' + role)
                textures[role] = texture
    if set(textures) != set(spec['entry']['maps']):
        raise ValueError('Sunset Pier material is missing an explicit produced texture')
    def texture(file, name, role):
        if file != spec['entry']['maps'][role] or name != 'T_Pier_' + key + '_' + role:
            raise ValueError('Original material requested an undeclared Sunset Pier texture')
        return textures[role]
    source = Path(context.job_dir) / ORIGINAL
    if source.is_symlink() or not source.is_file(): raise ValueError('Original Sunset Pier material source is not staged')
    functions = [n for n in ast.parse(source.read_bytes()).body if isinstance(n, ast.FunctionDef) and n.name == 'materials']
    if len(functions) != 1: raise ValueError('Original Sunset Pier materials function changed')
    loops = [n for n in functions[0].body if isinstance(n, ast.For)]
    if len(loops) != 1 or ast.unparse(loops[0].target) != '(key, entry)' or ast.unparse(loops[0].iter) != 'specs.items()':
        raise ValueError('Original Sunset Pier per-material loop changed')
    function = ast.parse('def author(key, entry):\n    result = {}\n    return result["Pier_" + key]\n').body[0]
    function.body[1:1] = loops[0].body
    scope = {'unreal': unreal, 'E': unreal.EditorAssetLibrary, 'AT': unreal.AssetToolsHelpers.get_asset_tools(),
             'MEL': unreal.MaterialEditingLibrary, 'texture': texture}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), ORIGINAL, 'exec'), scope)
    asset = scope['author'](key, spec['entry'])
    if not isinstance(asset, unreal.Material): raise ValueError('Sunset Pier material was not authored')
    _identity(asset, package)
    return asset


def source_facts(context, args):
    piece = args['piece']
    root = _path(context, 'source_export', directory=True)
    receipt = validate_export(root, key=piece)
    if receipt['primary'] != piece + '.fbx' or {p.name for p in root.iterdir()} != {'export.json', piece + '.fbx'}:
        raise ValueError('Sunset Pier export differs from its selected owner')
    payload = _path(context, 'payload', directory=True)
    if {p.name for p in payload.iterdir()} != {piece + '.npz'}:
        raise ValueError('Sunset Pier requires its exact selected MeshIR member')
    path = payload / (piece + '.npz')
    if path.is_symlink() or not path.is_file(): raise ValueError('Missing Sunset Pier MeshIR source')
    raw = path.read_bytes(); meta, decoded, facts = decode_mesh_payload(raw, expected_asset=piece, output_format='fbx')
    expected = {'geometry_sha256': hashlib.sha256(raw).hexdigest(), 'slots': facts['slots'], 'polygons': facts['polygons'],
                'collision_hulls': facts['collision_hulls'], 'uv_channels': facts['uv_channels']}
    if (receipt['metadata'] != expected or receipt['triangles'] != facts['triangles']
            or receipt['bounds'] != [facts['min'], facts['max']] or facts['uv_channels'] != ['UVMap']
            or facts['collision_hulls'] or not 0 < facts['triangles'] <= 32768):
        raise ValueError('Sunset Pier receipt differs from its exact original MeshIR geometry')
    used = {meta['slots'][int(index)] for index in decoded['materials']}
    return {**facts, 'export_sha256': receipt['sha256']}, used


def mesh(context, unreal, args):
    """@cc [owner:fontanierh,label:correctness] sunset-pier-current-native-piece
    Every piece MUST finish a fresh raw duplicate with exact selected source
    triangles, axes, bounds, UV and original material bindings. Park meshes retain
    CPU riding snapshots. Blocking meshes require actual cooked complex validation;
    board and floor paint require simple-as-complex with zero physics shapes.
    Validate before and after saving, including original deck/truck pivot contracts.
    """
    piece, parent, board, blocks = (args[k] for k in ('piece', 'parent', 'board', 'blocks'))
    if type(board) is not bool or type(blocks) is not bool or (board and (piece != parent or parent not in BOARD or blocks)):
        raise ValueError('Unknown Sunset Pier board/collision identity')
    if not board:
        source_policy = pieces_module()
        PARENTS, owned_name = source_policy.PARENTS, source_policy.owned_name
        if parent not in PARENTS or not owned_name(piece) or not (piece == parent or piece.startswith(parent + '_Piece')):
            raise ValueError('Unknown Sunset Pier selected park member')
    destination = ROOT + ('/Board/' if board else '/') + piece
    source = _selected(context, 'raw')
    if context.params['destination'] != destination or source != '/Game/_Raw/SkatePark/' + piece:
        raise ValueError('Sunset Pier raw/finish identity differs')
    _owned(context, destination); _fresh(unreal, destination)
    facts, used = source_facts(context, args)
    materials = {}
    if board:
        material = _load(unreal, context, args['material'], unreal.MaterialInterface)
        _identity(material, VILLAGE)
    else:
        for row in _derived(args['materials']):
            asset = _load(unreal, context, row['slot'], unreal.MaterialInterface)
            _identity(asset, ROOT + '/Materials/M_Pier_' + row['piece'])
            materials['Pier_' + row['piece']] = asset
    lib = unreal.EditorAssetLibrary
    raw = _load(unreal, context, 'raw', unreal.StaticMesh)
    asset = lib.duplicate_asset(source, destination)
    if not isinstance(asset, unreal.StaticMesh) or asset is raw: raise ValueError('Sunset Pier raw duplicate failed')
    _identity(asset, destination)
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    slots = [str(slot.get_editor_property('imported_material_slot_name')) for slot in asset.static_materials]
    if len(slots) != len(set(slots)) or set(slots) != used or (board and len(slots) != 1):
        raise ValueError('Sunset Pier current original material slot roster differs')
    for index, key in enumerate(slots):
        if not board and key not in materials: raise ValueError('Unknown Sunset Pier surface')
        asset.set_material(index, material if board else materials[key])
    if not board: asset.set_editor_property('allow_cpu_access', True)
    asset.set_editor_property('complex_collision_mesh', None); asset.set_editor_property('lod_for_collision', 0)
    body = asset.get_editor_property('body_setup')
    if body is None: raise ValueError('Sunset Pier mesh has no native BodySetup')
    trace = (unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE if blocks
             else unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
    body.set_editor_property('collision_trace_flag', trace)
    validation = getattr(unreal, 'CitySurfaceValidation', None)
    if not all(callable(getattr(validation, name, None)) for name in ('validate_collision', 'validate_simple_boxes')):
        raise ValueError('Produced Sunset Pier collision validator is unavailable')
    low = [facts['min'][0] * 100, -facts['max'][1] * 100, facts['min'][2] * 100]
    high = [facts['max'][0] * 100, -facts['min'][1] * 100, facts['max'][2] * 100]
    def check():
        box = asset.get_bounding_box()
        lo = [round(getattr(box.min, axis), 2) for axis in 'xyz']; hi = [round(getattr(box.max, axis), 2) for axis in 'xyz']
        if (asset.get_num_lods() != 1 or asset.get_num_triangles(0) != facts['triangles']
                or editor.get_num_uv_channels(asset, 0) != 1 or editor.get_simple_collision_count(asset)
                or editor.get_convex_collision_count(asset) or asset.get_editor_property('lod_for_collision') != 0
                or asset.get_editor_property('complex_collision_mesh') is not None
                or body.get_editor_property('collision_trace_flag') != trace
                or (not board and asset.get_editor_property('allow_cpu_access') is not True)
                or max(abs(a - b) for a, b in zip(lo + hi, low + high)) >= .5
                or any(asset.get_material(i) != (material if board else materials[key]) for i, key in enumerate(slots))):
            raise ValueError('Sunset Pier native geometry/axis/UV/material/collision invariant failed')
        if not (validation.validate_collision(asset, facts['triangles'], False) if blocks else validation.validate_simple_boxes(asset, 0)):
            raise ValueError('Sunset Pier actual cooked collision invariant failed')
        if piece == 'SM_SkateDeck' and (abs(hi[2] - 4.5) >= .05 or abs(hi[1] - 10.25) >= .05):
            raise ValueError('Sunset Pier deck pivot contract differs')
        if piece == 'SM_SkateTruck' and (abs(hi[2]) >= .05 or lo[0] >= -3.5):
            raise ValueError('Sunset Pier truck/kingpin pivot contract differs')
        return lo, hi
    check()
    if not lib.save_loaded_asset(asset): raise ValueError('Sunset Pier native save failed')
    lo, hi = check()
    report = 'data/reports/' + piece + '.json'
    if list(context.data_outputs) != [report]: raise ValueError('Sunset Pier native report must have its exact declared owner')
    return {report: {'name': piece, 'triangles': facts['triangles'], 'bounds_min_cm': lo, 'bounds_max_cm': hi,
                     'blocks': blocks, 'board': board, 'materials': slots, 'source_sha256': facts['export_sha256']}}


def run(context):
    import unreal
    args = context.params.get('args', {})
    if args.get('action') == 'material': return material(context, unreal, args)
    if (args.get('action') != 'mesh' or context.params.get('op') != 'finish'
            or context.params.get('kind') != 'static_mesh' or context.params.get('source') != 'raw'):
        raise ValueError('Unsupported Sunset Pier native operation')
    return mesh(context, unreal, args)
