"""Finish one current Southwest render child without receiving, inventory, cache or retirement."""
import ast
import hashlib
from pathlib import Path

from atelier import native_packages
from atelier.build_v2.blender_validate import decode_mesh_payload
from island_finish_v2 import _identity, _selected, _source
from southwest_atomic_products import DESTINATION, PARENTS, owned

MATERIAL = '/Game/Japan/Materials/M_Village'
EMPTY_COLLISION = 'games/yorimichi/unreal/Scripts/import_city_surface_tiles.py'
IDENTITY = [[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]


def source_facts(context):
    args = context.params['args']; parent = args['parent']
    receipt, _, bounds = _source(context, args['source_export'])
    key = receipt['asset']
    if parent not in PARENTS or not owned(key, parent): raise ValueError('Southwest source belongs to another logical parent')
    if receipt['primary'] != key + '.fbx' or receipt['metadata']['slots'] != ['Southwest_Palette']:
        raise ValueError('Southwest requires its original single FBX draw slot')
    value = context.inputs.get(args['payload'])
    if value is None or context.packages.get(args['payload']) not in ([], ()):
        raise ValueError('Southwest requires its actual selected Data payload Item')
    root = Path(value)
    if (not root.is_absolute() or not root.is_relative_to(Path(context.job_dir)) or root.resolve() != root
            or root.is_symlink() or not root.is_dir()):
        raise ValueError('Southwest source payload must be a regular job-local Item')
    members = list(root.iterdir())
    if (len(members) != 1 or members[0].name != key + '.npz' or members[0].is_symlink()
            or not members[0].is_file() or not 0 < members[0].stat().st_size <= 128 * 1024 * 1024):
        raise ValueError('Southwest payload must contain exactly its selected bounded MeshIR')
    raw = members[0].read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    metadata, _, facts = decode_mesh_payload(raw, expected_asset=key, output_format='fbx')
    if (metadata['matrix'] != IDENTITY or metadata['collisions'] or facts['slots'] != ['Southwest_Palette']
            or facts['uv_channels'] != ['UVMap'] or facts['triangles'] != receipt['triangles']
            or [facts['min'], facts['max']] != receipt['bounds']
            or receipt['metadata'] != {'geometry_sha256': digest, 'slots': facts['slots'], 'polygons': facts['polygons'],
                                      'collision_hulls': 0, 'uv_channels': facts['uv_channels']}):
        raise ValueError('Southwest source frame/geometry/UV/zero-hull ownership differ from export')
    return key, receipt['triangles'], bounds


def empty_collision(context):
    """Use only the original named cleanup definition; never import its receiving module."""
    path = Path(context.job_dir) / EMPTY_COLLISION
    if path.resolve() != path or not path.is_file(): raise ValueError('Missing staged keyed Southwest collision cleanup')
    nodes = [n for n in ast.parse(path.read_bytes(), str(path)).body
             if isinstance(n, ast.FunctionDef) and n.name == 'finish_empty_collision']
    if len(nodes) != 1 or nodes[0].decorator_list: raise ValueError('Original empty-collision cleanup definition differs')
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['finish_empty_collision']


def run(context):
    """@cc [owner:fontanierh,label:correctness] southwest-selected-current-native-piece
    Only the fresh selected raw duplicate MAY be mutated. The source payload and
    export MUST prove the original identity frame, Southwest_Palette, exact counts,
    finite bounds, one UV and zero authored hulls. Original empty-collision cleanup,
    half precision and complex-as-simple cooked LOD0 checks MUST survive. Validate
    native state before and after the original checked native save. No old importer
    top level/main, generated scan, source fallback, cache or retirement MAY run.
    """
    import unreal
    p = context.params
    if (set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'settings'}
            or p.get('op') != 'finish' or p.get('kind') != 'static_mesh' or p.get('source') != 'raw'
            or not isinstance(p.get('args'), dict) or set(p['args']) != {'parent', 'source_export', 'payload', 'material', 'native_inputs'}):
        raise ValueError('Unsupported Southwest finish parameters')
    args = p['args']; native = args['native_inputs']
    if (not isinstance(native, dict) or args['material'] not in native or native[args['material']] != MATERIAL
            or set(context.inputs) != {'raw', args['source_export'], args['payload'], *native}
            or set(context.packages) != set(context.inputs) or context.packages.get(args['source_export']) not in ([], ())):
        raise ValueError('Southwest native/source input membership differs')
    key, triangles, bounds = source_facts(context)
    destination = DESTINATION + '/' + key; source = _selected(context, 'raw')
    if source != '/Game/_Raw/Southwest/' + key or p['destination'] != destination or list(context.outputs) != [destination]:
        raise ValueError('Southwest owns exactly its selected original mesh package')
    cleanup = empty_collision(context)
    E = unreal.EditorAssetLibrary; raw = E.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh): raise ValueError('Southwest raw input must be a StaticMesh')
    _identity(raw, source); loaded = {}
    for slot, package in native.items():
        if _selected(context, slot) != package: raise ValueError('Southwest native dependency differs')
        asset = E.load_asset(package)
        if asset is None: raise ValueError('Southwest native dependency failed to load')
        _identity(asset, package); loaded[slot] = asset
    material = loaded[args['material']]
    if not isinstance(material, unreal.MaterialInterface): raise ValueError('Southwest material must be its supplied MaterialInterface')
    validator = getattr(getattr(unreal, 'CitySurfaceValidation', None), 'validate_collision', None)
    if not callable(validator): raise ValueError('Required produced Southwest collision validator unavailable')
    unreal.load_module('StaticMeshEditor'); editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None: raise ValueError('Native StaticMeshEditor unavailable')
    if E.does_asset_exist(destination): raise ValueError('Southwest destination must be fresh')
    mesh = E.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw: raise ValueError('Southwest raw duplicate failed')
    _identity(mesh, destination)
    if len(mesh.static_materials) != 1 or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'Southwest_Palette':
        raise ValueError('Southwest original source material slot differs')
    if mesh.get_material(0) != material: mesh.set_material(0, material)
    if mesh.get_num_lods() > 1: mesh.set_num_source_models(1)
    settings = editor.get_lod_build_settings(mesh, 0)
    if settings.get_editor_property('use_full_precision_u_vs'):
        settings.set_editor_property('use_full_precision_u_vs', False); editor.set_lod_build_settings(mesh, 0, settings)
    body = mesh.get_editor_property('body_setup')
    if body is None: raise ValueError('Southwest mesh has no BodySetup')
    trace = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    if body.get_editor_property('collision_trace_flag') != trace: body.set_editor_property('collision_trace_flag', trace)
    cleanup(mesh, {'name': key, 'collision_hulls': 0}, editor)
    def validate():
        box = mesh.get_bounding_box()
        if (mesh.get_num_triangles(0) != triangles or mesh.get_num_lods() != 1 or editor.get_num_uv_channels(mesh, 0) != 1
                or editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs')
                or len(mesh.static_materials) != 1 or mesh.get_material(0) != material
                or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'Southwest_Palette'
                or body.get_editor_property('collision_trace_flag') != trace
                or editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh)
                or any(not abs(getattr(box.min, axis)-lo) < .2 or not abs(getattr(box.max, axis)-hi) < .2
                       for axis, lo, hi in zip(('x', 'y', 'z'), *bounds))):
            raise ValueError('Southwest current geometry/material/UV/zero-hull/bounds invariant failed')
        if not validator(mesh, triangles, False): raise ValueError('Southwest original cooked LOD0 validation failed')
    validate()
    native_packages.save(mesh, E, context.content_dir)
    validate()
    return mesh
