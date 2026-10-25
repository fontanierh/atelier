"""Finish exactly one current Village mesh with its original manifest and whole UCX hull geometry."""
import hashlib
import json
from pathlib import Path

import numpy as np
from atelier.build_v2.blender_validate import decode_mesh_payload
from atelier.conventions import to_unreal
from atelier.export_manifest import validate as validate_export
from city_tile_products import collision_matches, native_bounds
from island_finish_v2 import _identity, _pairs, _selected
from village_atomic_products import ASSETS, DESTINATION, MATERIAL, ground_native_count, owned


def _path(context, slot, *, directory):
    value = context.inputs.get(slot)
    if value is None or context.packages.get(slot) not in ([], ()):
        raise ValueError('Village source role must be a declared Data Item: ' + str(slot))
    path = Path(value)
    if (not path.is_absolute() or not path.is_relative_to(Path(context.job_dir)) or path.resolve() != path
            or path.is_symlink() or (not path.is_dir() if directory else not path.is_file())):
        raise ValueError('Village source must be an independent regular job-local Item')
    return path


def _json(path, limit):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Missing or oversized Village source JSON')
    return json.loads(path.read_bytes(), object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite Village source JSON')))


def source_facts(context):
    args = context.params['args']; parent = args['parent']
    if parent not in ASSETS:
        raise ValueError('Unknown Village logical parent')
    root = _path(context, args['source_export'], directory=True)
    receipt = _json(root / 'export.json', 1024 * 1024)
    if (not isinstance(receipt, dict) or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or not owned(receipt['asset'], parent) or receipt['primary'] != receipt['asset'] + '.fbx'
            or {p.name for p in root.iterdir()} != {'export.json', receipt['primary']}
            or validate_export(root, key=receipt['asset']) != receipt):
        raise ValueError('Village export Item differs from its exact selected source')
    key = receipt['asset']
    payload = _path(context, args['payload'], directory=True)
    members = list(payload.iterdir())
    if (len(members) != 1 or members[0].name != key + '.npz' or members[0].is_symlink()
            or not members[0].is_file() or not 0 < members[0].stat().st_size <= 128 * 1024 * 1024):
        raise ValueError('Village requires exactly its selected bounded MeshIR payload')
    raw = members[0].read_bytes(); digest = hashlib.sha256(raw).hexdigest()
    metadata, piece, facts = decode_mesh_payload(raw, expected_asset=key, output_format='fbx')
    if (facts['slots'] != ['VillagePalette'] or facts['uv_channels'] != ['UVMap']
            or receipt['triangles'] != facts['triangles'] or receipt['bounds'] != [facts['min'], facts['max']]
            or receipt['metadata'] != {'geometry_sha256': digest, 'slots': facts['slots'], 'polygons': facts['polygons'],
                'collision_hulls': facts['collision_hulls'], 'uv_channels': facts['uv_channels']}):
        raise ValueError('Village source receipt differs from selected complete geometry/attributes')
    manifest = _json(_path(context, args['manifest'], directory=False), 64 * 1024 * 1024)
    if (not isinstance(manifest, dict) or set(manifest) != {'schema', 'complete', 'parents'} or manifest['schema'] != 1
            or manifest['complete'] is not True or not isinstance(manifest['parents'], dict) or set(manifest['parents']) != set(ASSETS)):
        raise ValueError('Village manifest must contain the complete original twelve parents')
    group = manifest['parents'][parent]
    if (not isinstance(group, dict) or group.get('slots') != ['VillagePalette'] or group.get('collision') != (
            'complex_as_simple' if parent == 'Village_Ground' else 'simple_and_complex')
            or type(group.get('source_collision_hulls')) is not int or group['source_collision_hulls'] < 0
            or not isinstance(group.get('source_collision_vertices'), list)
            or len(group['source_collision_vertices']) != group['source_collision_hulls']
            or not isinstance(group.get('pieces'), list) or not group['pieces']):
        raise ValueError('Village manifest lost its original collision/material policy')
    rows, seen = [], set()
    for index, row in enumerate(group['pieces']):
        if (not isinstance(row, dict) or not owned(row.get('name', ''), parent) or row['name'].casefold() in seen
                or type(row.get('triangles')) is not int or not 0 < row['triangles'] <= 32768
                or type(row.get('native_triangles')) is not int or not 0 < row['native_triangles'] <= row['triangles']
                or row.get('collision_hulls') != (group['source_collision_hulls'] if index == 0 else 0)
                or row.get('uv_channels') != ['UVMap']):
            raise ValueError('Village manifest source membership is incomplete or foreign')
        native_bounds(row); seen.add(row['name'].casefold())
        if row['name'] == key: rows.append(row)
    if (len(rows) != 1 or sum(r['triangles'] for r in group['pieces']) != group.get('source_triangles')
            or sum(r['collision_hulls'] for r in group['pieces']) != group['source_collision_hulls']):
        raise ValueError('Village source geometry or collision union is incomplete')
    row = rows[0]
    projection = (ground_native_count(metadata, piece) if parent == 'Village_Ground'
                  else {'native_triangles': facts['triangles'], 'native_removed_polygons': []})
    if (any(row.get(k) != v for k, v in projection.items()) or row.get('geometry_sha256') != digest
            or row.get('sha256') != receipt['sha256'] or row['triangles'] != facts['triangles']
            or [row['min'], row['max']] != receipt['bounds'] or row['collision_hulls'] != len(metadata['collisions'])):
        raise ValueError('Village selected manifest member differs from actual export/payload/projection')
    if row['collision_hulls']:
        hulls = []
        for hull in metadata['collisions']:
            transform = np.asarray(hull['matrix'])
            vertices = np.asarray(hull['vertices']) @ transform[:3, :3].T + transform[:3, 3]
            hulls.append([[float(v) for v in to_unreal(point)] for point in vertices])
        if hulls != group['source_collision_vertices']:
            raise ValueError('Village manifest whole hull geometry differs from its selected source owner')
    return key, group, row


def run(context):
    """@cc [owner:fontanierh,label:correctness;performance] current-village-native-piece
    Only a fresh duplicate of the declared raw Item MAY be mutated. Current source
    payload/export/manifest MUST prove exact native triangles, bounds, VillagePalette,
    one half-precision UV channel and complete whole authored UCX hull geometry.
    Ground MUST use complex-as-simple; all other parents MUST retain simple-and-
    complex even on zero-hull leaves. Original produced-module validation and a
    real dirty-only primary save MUST succeed before and after save. No source
    import, receiving cache, sibling mutation, native scan or retirement MAY run.
    """
    import unreal
    p = context.params
    if (set(p) - {'op', 'kind', 'source', 'destination', 'package_sources', 'args', 'input_roots', 'settings'}
            or p.get('op') != 'finish' or p.get('kind') != 'static_mesh' or not isinstance(p.get('args'), dict)
            or set(p['args']) != {'parent', 'payload', 'source_export', 'manifest', 'material', 'native_inputs'}):
        raise ValueError('Unsupported Village finish parameters')
    args = p['args']; native = args['native_inputs']
    if (not isinstance(native, dict) or args['material'] not in native or native[args['material']] != MATERIAL
            or set(context.inputs) != {'raw', args['source_export'], args['payload'], args['manifest'], *native}
            or set(context.packages) != set(context.inputs)):
        raise ValueError('Village finish input membership differs from its declared sources/native closure')
    key, group, row = source_facts(context)
    destination = DESTINATION + '/' + key
    source = _selected(context, p['source'])
    if (p['source'] != 'raw' or p['destination'] != destination or list(context.outputs) != [destination]
            or source != '/Game/_Raw/Village/' + key):
        raise ValueError('Village finish must own exactly its selected original package')
    library = unreal.EditorAssetLibrary
    raw = library.load_asset(source)
    if not isinstance(raw, unreal.StaticMesh): raise ValueError('Village raw Item is not a StaticMesh')
    _identity(raw, source)
    loaded = {}
    for slot, package in native.items():
        if _selected(context, slot) != package: raise ValueError('Village native dependency differs')
        asset = library.load_asset(package)
        if asset is None: raise ValueError('Village declared material dependency did not load')
        _identity(asset, package); loaded[slot] = asset
    material = loaded[args['material']]
    if not isinstance(material, unreal.MaterialInterface): raise ValueError('Village material must be its supplied MaterialInterface')
    validation = getattr(unreal, 'CitySurfaceValidation', None)
    if not callable(getattr(validation, 'validate_collision', None)) or not callable(getattr(validation, 'collision_vertices', None)):
        raise ValueError('Required produced Village collision validation module is unavailable')
    unreal.load_module('StaticMeshEditor')
    editor = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    if editor is None: raise ValueError('Native StaticMeshEditor unavailable')
    if library.does_asset_exist(destination): raise ValueError('Village destination must be fresh')
    mesh = library.duplicate_asset(source, destination)
    if not isinstance(mesh, unreal.StaticMesh) or mesh is raw: raise ValueError('Village raw duplicate failed')
    _identity(mesh, destination)
    if len(mesh.static_materials) != 1 or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'VillagePalette':
        raise ValueError('Village original draw material slot differs')
    if mesh.get_material(0) != material: mesh.set_material(0, material)
    body = mesh.get_editor_property('body_setup')
    if body is None: raise ValueError('Village mesh has no BodySetup')
    simple = group['collision'] == 'simple_and_complex'
    trace = unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AND_COMPLEX if simple else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE
    if body.get_editor_property('collision_trace_flag') != trace: body.set_editor_property('collision_trace_flag', trace)
    if row['collision_hulls'] == 0:
        if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
            if not editor.remove_collisions(mesh): raise ValueError('Village stale shape removal failed')
        if editor.get_simple_collision_count(mesh) or editor.get_convex_collision_count(mesh):
            raise ValueError('Village render-only leaf retained collision shapes')
    settings = editor.get_lod_build_settings(mesh, 0)
    if settings.get_editor_property('use_full_precision_u_vs'):
        settings.set_editor_property('use_full_precision_u_vs', False); editor.set_lod_build_settings(mesh, 0, settings)
    low, high = native_bounds(row)
    def validate():
        box = mesh.get_bounding_box()
        if (mesh.get_num_triangles(0) != row['native_triangles'] or mesh.get_num_lods() != 1
                or len(mesh.static_materials) != 1 or mesh.get_material(0) != material
                or str(mesh.static_materials[0].get_editor_property('imported_material_slot_name')) != 'VillagePalette'
                or body.get_editor_property('collision_trace_flag') != trace
                or editor.get_num_uv_channels(mesh, 0) != 1
                or editor.get_lod_build_settings(mesh, 0).get_editor_property('use_full_precision_u_vs')
                or not collision_matches(mesh, group, row, read_vertices=validation.collision_vertices)
                or any(not abs(getattr(box.min, axis)-a) < .2 or not abs(getattr(box.max, axis)-b) < .2
                       for axis, a, b in zip(('x', 'y', 'z'), low, high))):
            raise ValueError('Village current geometry/material/UV/hull invariant failed')
        if not validation.validate_collision(mesh, row['native_triangles'], simple):
            raise ValueError('Village original cooked LOD0 collision validation failed')
    validate()
    if not library.save_loaded_asset(mesh, True): raise ValueError('Village dirty-only native save failed')
    primary = Path(context.content_dir) / (destination.removeprefix('/Game/') + '.uasset')
    if any(part.is_symlink() for part in (primary, *primary.parents)) or not primary.is_file():
        raise ValueError('Village native save did not leave its actual regular primary package')
    validate()
    return mesh
