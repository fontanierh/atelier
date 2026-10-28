"""Finish one declared Lake child from its actual bounded MeshIR and FBX export Item."""
import hashlib
from pathlib import Path

from atelier.build_v2.blender_validate import decode_mesh_payload
from island_finish_v2 import _identity, _selected, _source
from lake_native import DEST, OWNERS, owned

WATER = '/Game/Japan/Materials/M_ForestLakeWater'
VILLAGE = '/Game/Japan/Materials/M_Village'


def source_facts(context):
    args = context.params['args']; parent = args['parent']
    receipt, _, bounds = _source(context, args['source_export'])
    key = receipt['asset']
    if parent not in OWNERS or not owned(key) or not (key == parent or key.startswith(parent + '_cell_')):
        raise ValueError('Lake selected source belongs to another logical parent')
    if receipt['primary'] != key + '.fbx' or receipt['metadata']['slots'] != ['LakePalette']:
        raise ValueError('Lake requires its original single FBX draw slot')
    value = context.inputs.get(args['payload'])
    if value is None or context.packages.get(args['payload']) not in ([], ()):
        raise ValueError('Lake requires its actual selected Data payload Item')
    payload = Path(value)
    if (not payload.is_absolute() or not payload.is_relative_to(Path(context.job_dir)) or payload.resolve() != payload
            or payload.is_symlink() or not payload.is_dir()):
        raise ValueError('Lake source payload must be a regular job-local Item')
    members = list(payload.iterdir())
    if (len(members) != 1 or members[0].name != key + '.npz' or members[0].is_symlink()
            or not members[0].is_file() or not 0 < members[0].stat().st_size <= 128 * 1024 * 1024):
        raise ValueError('Lake payload Item must contain exactly its bounded selected MeshIR')
    raw = members[0].read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    metadata, _, facts = decode_mesh_payload(raw, expected_asset=key, output_format='fbx')
    if (metadata['collisions'] or facts['slots'] != ['LakePalette'] or facts['uv_channels'] != ['UVMap']
            or facts['triangles'] != receipt['triangles'] or [facts['min'], facts['max']] != receipt['bounds']
            or receipt['metadata'] != {'geometry_sha256': digest, 'slots': facts['slots'], 'polygons': facts['polygons'],
                                      'collision_hulls': 0, 'uv_channels': facts['uv_channels']}):
        raise ValueError('Lake export and selected payload geometry/UV/zero-hull ownership differ')
    return key, receipt['triangles'], bounds


def run(context):
    """@cc [owner:fontanierh,label:correctness] current-lake-piece-finish
    Finish MUST mutate only a fresh duplicate of its exact raw Item. Its selected
    payload/export MUST prove original parent membership, triangles, bounds,
    LakePalette and one UV channel with zero authored hulls. Bind original water
    only on Lake_Water, M_Village otherwise. Require half UV precision, complex-
    as-simple cooked LOD0 collision and an actual dirty-only primary save, with
    native invariants checked before and after save. No scan/main/cache/retirement.
    """
    import unreal
    p = context.params
    if (set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'settings'}
            or p.get('op') != 'finish' or p.get('kind') != 'static_mesh' or p.get('source') != 'raw'
            or not isinstance(p.get('args'), dict) or set(p['args']) != {'parent', 'source_export', 'payload', 'material', 'native_inputs'}):
        raise ValueError('Unsupported Lake finish parameters')
    args = p['args']; native = args['native_inputs']
    material_path = WATER if args['parent'] == 'Lake_Water' else VILLAGE
    if (not isinstance(native, dict) or args['material'] not in native or native[args['material']] != material_path
            or set(context.inputs) != {'raw', args['source_export'], args['payload'], *native}
            or set(context.packages) != set(context.inputs) or context.packages.get(args['source_export']) not in ([], ())):
        raise ValueError('Lake native/source role membership differs')
    key, triangles, bounds = source_facts(context)
    destination = DEST + '/' + key; source = _selected(context, 'raw')
    if source != '/Game/_Raw/Lake/' + key or p['destination'] != destination or list(context.outputs) != [destination]:
        raise ValueError('Lake owns exactly its selected original mesh package')
    E = unreal.EditorAssetLibrary; raw = E.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh): raise ValueError('Lake raw input must be a StaticMesh')
    _identity(raw, source); loaded = {}
    for slot, package in native.items():
        if _selected(context, slot) != package: raise ValueError('Lake native dependency differs')
        asset = E.load_asset(package)
        if asset is None: raise ValueError('Lake native dependency failed to load')
        _identity(asset, package); loaded[slot] = asset
    material = loaded[args['material']]
    if not isinstance(material, unreal.MaterialInterface): raise ValueError('Lake declared material is not a MaterialInterface')
    validator = getattr(getattr(unreal, 'CitySurfaceValidation', None), 'validate_collision', None)
    if not callable(validator): raise ValueError('Required produced Lake collision validator is unavailable')
    unreal.load_module('StaticMeshEditor'); editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None: raise ValueError('Native StaticMeshEditor unavailable')
    if E.does_asset_exist(destination): raise ValueError('Lake destination must be fresh')
    mesh = E.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw: raise ValueError('Lake raw duplicate failed')
    _identity(mesh, destination)
    mesh.set_num_source_models(1)
    if len(mesh.static_materials) != 1 or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'LakePalette':
        raise ValueError('Lake original palette slot differs')
    if mesh.get_material(0) != material: mesh.set_material(0, material)
    settings = editor.get_lod_build_settings(mesh, 0)
    if settings.get_editor_property('use_full_precision_u_vs'):
        settings.set_editor_property('use_full_precision_u_vs', False); editor.set_lod_build_settings(mesh, 0, settings)
    body = mesh.get_editor_property('body_setup')
    if body is None: raise ValueError('Lake mesh has no BodySetup')
    trace = unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    body.set_editor_property('collision_trace_flag', trace)
    if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
        if not editor.remove_collisions(mesh): raise ValueError('Lake unexpected collision shapes could not be removed')
    def validate():
        box = mesh.get_bounding_box()
        if (mesh.get_num_triangles(0) != triangles or mesh.get_num_lods() != 1 or editor.get_num_uv_channels(mesh, 0) != 1
                or editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs')
                or len(mesh.static_materials) != 1 or mesh.get_material(0) != material
                or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'LakePalette'
                or body.get_editor_property('collision_trace_flag') != trace
                or editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh)
                or any(not abs(getattr(box.min, axis)-lo) <= .1 or not abs(getattr(box.max, axis)-hi) <= .1
                       for axis, lo, hi in zip(('x', 'y', 'z'), *bounds))):
            raise ValueError('Lake current geometry/material/UV/zero-hull/bounds invariant failed')
        if not validator(mesh, triangles, False): raise ValueError('Lake original cooked LOD0 collision validation failed')
    validate()
    if not E.save_loaded_asset(mesh, True): raise ValueError('Lake native save failed')
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(p.is_symlink() for p in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('Lake native save did not leave its actual regular primary package')
    validate()
    return mesh
