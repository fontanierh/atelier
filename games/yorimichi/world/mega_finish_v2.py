"""Finish exactly one mini-mega mesh with import_mega.py's material and collision policy.

import_mega.py binds M_Village to slot 0 and sets the collision trace: Mega_Trim is look only (AMegaRamp gives it
no collision, so simple as complex with no shapes), Mega_Ramp and Mega_Trail collide with their render mesh
(complex as simple). The source facts are the piece's own export receipt and selected MeshIR payload: its one
MegaPalette slot, triangles, bounds, UV set and any authored UCX hulls. The finish binds them to the existing
native validators (exact triangles, Blender-to-Unreal bounds, UCX vertices, cooked collision) before and after
its primary save. Unlike Village_Ground, no triangle may be dropped: native triangles equal the source exactly.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.conventions import to_unreal
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches, native_bounds
from island_finish_v2 import _identity, _pairs, _selected

DESTINATION = '/Game/Japan/Assets'
MATERIAL = '/Game/Japan/Materials/M_Village'
POLICY = {'Mega_Ramp': 'complex_as_simple', 'Mega_Trim': 'look_only', 'Mega_Trail': 'complex_as_simple'}


def _path(context, slot, *, directory):
    value = context.inputs.get(slot)
    if value is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('Mega source role must be a declared Data Item: ' + str(slot))
    path = Path(value)
    if (not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve() != path
            or path.is_symlink() or (not path.is_dir() if directory else not path.is_file())):
        raise ValueError('Mega source must be an independent regular job-local Item')
    return path


def source_facts(context):
    args = context.params['args']; parent = args['parent']
    if POLICY.get(parent) != args['collision']:
        raise ValueError('Unknown mega parent or changed collision policy')
    root = _path(context, args['source_export'], directory=True)
    receipt_path = root / 'export.json'
    if receipt_path.is_symlink() or not receipt_path.is_file() or not 0 < receipt_path.stat().st_size <= 1024 * 1024:
        raise ValueError('Mega export Item has no bounded receipt')
    receipt = json.loads(receipt_path.read_bytes(), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite mega receipt')))
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or receipt['asset'] != parent or receipt['primary'] != parent + '.fbx'
            or {p.name for p in root.iterdir()} != {'export.json', receipt['primary']}
            or validate_export(root, key=parent) != receipt):
        raise ValueError('Mega export Item differs from its exact selected source')
    payload = _path(context, args['payload'], directory=True)
    members = list(payload.iterdir())
    if (len(members) != 1 or members[0].name != parent + '.npz' or members[0].is_symlink()
            or not members[0].is_file() or not 0 < members[0].stat().st_size <= 128 * 1024 * 1024):
        raise ValueError('Mega requires exactly the selected bounded MeshIR payload')
    raw = members[0].read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    metadata, _piece, facts = decode_mesh_payload(raw, expected_asset=parent, output_format='fbx')
    if (facts['slots'] != ['MegaPalette'] or facts['uv_channels'] != ['UVMap']
            or receipt['triangles'] != facts['triangles'] or receipt['bounds'] != [facts['min'], facts['max']]
            or receipt['metadata'] != {'geometry_sha256': digest, 'slots': facts['slots'], 'polygons': facts['polygons'],
                'collision_hulls': facts['collision_hulls'], 'uv_channels': facts['uv_channels']}):
        raise ValueError('Mega source receipt differs from its selected geometry, slot or UV set')
    if args['collision'] == 'look_only' and facts['collision_hulls']:
        raise ValueError('Look-only Mega_Trim source authored collision hulls')
    hulls = []
    for hull in metadata['collisions']:
        transform = np.asarray(hull['matrix'])
        vertices = np.asarray(hull['vertices']) @ transform[:3, :3].T + transform[:3, 3]
        hulls.append([[float(v) for v in to_unreal(point)] for point in vertices])
    return facts, hulls


def run(context):
    """@cc [owner:fontanierh,label:correctness] current-mega-native-piece
    Only a fresh duplicate of the declared raw Item MAY be mutated, at the original
    /Game/Japan/Assets/<parent>. Its own export and MeshIR MUST prove the MegaPalette
    slot, exact triangles, bounds, one UV set and authored hulls. Slot 0 binds the
    supplied M_Village. Mega_Trim is look-only simple-as-complex with no shapes; the
    ramp and trail are complex-as-simple. The checks and a real primary save MUST
    hold before and after save. No source import, cache or retirement MAY run.
    """
    import unreal
    p = context.params
    if (set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'settings'}
            or p.get('op') != 'finish' or p.get('kind') != 'static_mesh' or not isinstance(p.get('args'), dict)
            or set(p['args']) != {'parent', 'collision', 'payload', 'source_export', 'material', 'native_inputs'}):
        raise ValueError('Unsupported mega finish parameters')
    args = p['args']; native = args['native_inputs']
    if (not isinstance(native, dict) or native.get(args['material']) != MATERIAL
            or set(context.inputs) != {'raw', args['source_export'], args['payload'], *native}
            or set(context.packages) != set(context.inputs)):
        raise ValueError('Mega finish input membership differs from its declared sources/native closure')
    facts, hulls = source_facts(context)
    parent, look_only = args['parent'], args['collision'] == 'look_only'
    destination = DESTINATION + '/' + parent
    source = _selected(context, p['source'])
    if (p['source'] != 'raw' or p['destination'] != destination or list(context.outputs) != [destination]
            or source != '/Game/_Raw/Mega/' + parent):
        raise ValueError('Mega finish must own exactly its selected original package')
    library = unreal.EditorAssetLibrary
    raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh):
        raise ValueError('Mega raw Item is not a StaticMesh')
    _identity(raw, source)
    loaded = {}
    for slot, package in native.items():
        if _selected(context, slot) != package:
            raise ValueError('Mega native dependency differs')
        asset = library.load_asset(package)
        if asset is None:
            raise ValueError('Mega declared material dependency did not load')
        _identity(asset, package); loaded[slot] = asset
    material = loaded[args['material']]
    if not isinstance(material, unreal.MaterialInterface):
        raise ValueError('Mega material must be its supplied MaterialInterface')
    validation = getattr(unreal, 'CitySurfaceValidation', None)
    if not all(callable(getattr(validation, name, None)) for name in ('validate_collision', 'validate_simple_boxes', 'collision_vertices')):
        raise ValueError('Required produced mega collision validation module is unavailable')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None:
        raise ValueError('Native StaticMeshEditor unavailable')
    if library.does_asset_exist(destination):
        raise ValueError('Mega destination must be fresh')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw:
        raise ValueError('Mega raw duplicate failed')
    _identity(mesh, destination)
    if (len(mesh.static_materials) != 1
            or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'MegaPalette'):
        raise ValueError('Mega original draw material slot differs')
    mesh.set_material(0, material)
    body = mesh.get_editor_property('body_setup')
    if body is None:
        raise ValueError('Mega mesh has no BodySetup')
    trace = (unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX if look_only
             else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    body.set_editor_property('collision_trace_flag', trace)
    low, high = native_bounds({'min': facts['min'], 'max': facts['max']})
    row, tile = {'source_collision_vertices': hulls}, {'collision_hulls': len(hulls)}
    def validate():
        box = mesh.get_bounding_box()
        if (mesh.get_num_triangles(0) != facts['triangles'] or mesh.get_num_lods() != 1
                or mesh.get_material(0) != material or body.get_editor_property('collision_trace_flag') != trace
                or editor.get_num_uv_channels(mesh, 0) != 1
                or not collision_matches(mesh, row, tile, read_vertices=validation.collision_vertices)
                or any(not abs(getattr(box.min, axis) - a) < .2 or not abs(getattr(box.max, axis) - b) < .2
                       for axis, a, b in zip(('x', 'y', 'z'), low, high))):
            raise ValueError(f'{parent}: current geometry/material/UV/collision invariant failed')
        cooked = (validation.validate_simple_boxes(mesh, 0) if look_only
                  else validation.validate_collision(mesh, facts['triangles'], False))
        if not cooked:
            raise ValueError(f'{parent}: original cooked collision validation failed')
    validate()
    if not library.save_loaded_asset(mesh, True):
        raise ValueError('Mega dirty-only native save failed')
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('Mega native save did not leave its actual regular primary package')
    validate()
    return mesh
