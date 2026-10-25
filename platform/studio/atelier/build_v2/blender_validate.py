"""D2 in-job semantic checks, reusing the existing bounded MeshIR decoder.

The consumer fully decodes its selected input; producer checks finish before Completed. B2
independently checks frozen complete inventories, roles, bounds and hash bindings, without a
second geometry parser or semantic-run claim. No process, descriptor runner or store token lives
here. NumPy/Blender are platform; the actual body/helper code is an explicit key ingredient.
Native FBX geometry comparison remains separate T1b acceptance.
"""
import json
import math

import numpy as np

from atelier import mesh_ir
from atelier.export_manifest import TRIANGLE_LIMIT, name

MAX_RECEIPT_BYTES = 1024 * 1024
FBX_HEADER = b'Kaydara FBX Binary  \x00\x1a\x00'


PLAN_FIELDS = frozenset(('schema', 'parent', 'complete', 'triangle_limit', 'partition',
                         'source_triangles', 'source_polygons', 'source_collision_hulls',
                         'collision_owner', 'slots', 'matrix', 'pieces'))
MEMBER_FIELDS = frozenset(('name', 'payload', 'sha256', 'triangles', 'polygons', 'source_faces',
                           'min', 'max', 'collision_hulls', 'slots', 'source_material_indices'))
OPTION_BOOLEANS = frozenset(('apply_unit_scale', 'use_space_transform', 'bake_space_transform',
                            'use_mesh_modifiers', 'use_mesh_modifiers_render', 'use_subsurf',
                            'use_mesh_edges', 'use_tspace', 'use_triangles', 'use_custom_props'))
OPTION_ENUMS = dict(apply_scale_options={'FBX_SCALE_NONE', 'FBX_SCALE_UNITS', 'FBX_SCALE_CUSTOM', 'FBX_SCALE_ALL'},
                    axis_forward={'X', 'Y', 'Z', '-X', '-Y', '-Z'}, axis_up={'X', 'Y', 'Z', '-X', '-Y', '-Z'},
                    mesh_smooth_type={'OFF', 'FACE', 'EDGE'}, colors_type={'NONE', 'SRGB', 'LINEAR'},
                    path_mode={'RELATIVE', 'STRIP'}, batch_mode={'OFF'})


def validate_mesh_options(options, *, output_format='fbx', finite_materials=False):
    """Admit only this route's typed finite settings before producer completion/native work."""
    if not hasattr(options, 'items'):
        raise ValueError('Export options must be an explicit object')
    result = dict(options)
    if output_format == 'glb':
        if (set(result) - {'export_apply', 'export_image_format'}
                or type(result.get('export_apply', False)) is not bool
                or result.get('export_image_format', 'AUTO' if finite_materials else 'NONE')
                    != ('AUTO' if finite_materials else 'NONE')):
            raise ValueError('Unsupported declared atomic GLB export option')
        return result
    if output_format != 'fbx' or finite_materials:
        raise ValueError('Unsupported mesh export format')
    for key, value in result.items():
        if key in OPTION_BOOLEANS:
            valid = type(value) is bool
        elif key in OPTION_ENUMS:
            valid = type(value) is str and value in OPTION_ENUMS[key]
        elif key == 'global_scale':
            valid = type(value) in (int, float) and 0.001 <= value <= 1000 and math.isfinite(value)
        elif key == 'triangle_limit':
            valid = type(value) is int and 1 <= value <= TRIANGLE_LIMIT
        elif key == 'scene_world_color':
            valid = (isinstance(value, (list, tuple)) and len(value) == 3
                     and all(type(v) in (int, float) and 0 <= v <= 1 and math.isfinite(v) for v in value))
        elif key in ('use_batch_own_dir', 'embed_textures'):
            valid = value is False
        else:
            valid = False
        if not valid:
            raise ValueError('Unsupported, mistyped or nonfinite export option: ' + str(key))
        if key == 'scene_world_color':
            # JobContext makes JSON arrays immutable tuples; the shared exporter expects a list.
            result[key] = list(value)
    if 'axis_forward' in result and 'axis_up' in result and result['axis_forward'][-1] == result['axis_up'][-1]:
        raise ValueError('Export forward/up axes must be independent')
    return result


def mesh_facts(payload, *, expected_asset=None, output_format='fbx'):
    """Decode the existing MeshIR, including its collision/material/channel validation.

    Only compact semantic facts leave this function. No arrays, original bytes, source locators,
    planner key, roster or siblings become selected-child metadata.
    """
    return decode_mesh_payload(payload, expected_asset=expected_asset, output_format=output_format)[2]


def decode_mesh_payload(payload, *, expected_asset=None, output_format='fbx'):
    """Return the fully checked existing decoder result and its compact facts, once."""
    meta, piece = mesh_ir.decode(payload)
    if output_format is None:
        # Producer proof admits the existing finite encodings; it does not choose a child's exporter.
        output_format = ('glb' if meta['schema'] == 3 or
                         set(meta['options']) & {'export_apply', 'export_image_format'} else 'fbx')
    if meta['schema'] != 2 and output_format != 'glb':
        raise ValueError('This FBX slice refuses material-graph payloads; their GLB route is pending')
    validate_mesh_options(meta['options'], output_format=output_format, finite_materials=meta['schema'] == 3)
    if expected_asset is not None and meta['asset'] != name(expected_asset):
        raise ValueError('Selected payload belongs to another piece')
    positions = piece['positions'] @ np.asarray(meta['matrix'])[:3, :3].T + np.asarray(meta['matrix'])[:3, 3]
    facts = dict(asset=meta['asset'], triangles=piece['triangles'], polygons=len(piece['faces']),
                slots=meta['slots'], matrix=meta['matrix'], options=meta['options'],
                collision_hulls=len(meta['collisions']), selection=meta['selection'],
                uv_channels=[row[0] for row in piece['uvs']],
                used_material_indices=sorted(set(piece['materials'].tolist())),
                colour_channels=[list(row[:3]) for row in piece['colours']],
                min=positions.min(0).tolist(), max=positions.max(0).tolist())
    return meta, piece, facts


def validate_member_row(facts, row, manifest):
    """Cross-check the decoded member against B2's already checked complete plan roster."""
    if not isinstance(row, dict) or not isinstance(manifest, dict):
        raise ValueError('Expected the authoritative plan row and manifest')
    for field, expected in [('asset', row.get('name')), ('triangles', row.get('triangles')),
                            ('polygons', row.get('polygons')), ('matrix', manifest.get('matrix')),
                            ('min', row.get('min')), ('max', row.get('max')),
                            ('collision_hulls', row.get('collision_hulls'))]:
        if facts.get(field) != expected:
            raise ValueError('Decoded piece differs from its plan: ' + field)
    if facts['slots'] != row.get('slots', manifest.get('slots')):
        raise ValueError('Decoded piece material table differs from its plan')
    indices = row.get('source_material_indices')
    if indices is not None:
        slots = manifest.get('slots')
        if (not isinstance(indices, list) or not isinstance(slots, list)
                or any(type(i) is not int or not 0 <= i < len(slots) for i in indices)
                or indices != sorted(set(indices))
                or [slots[i] for i in indices] != facts['slots']):
            raise ValueError('Piece material mapping differs from the parent inventory')
    owner = manifest.get('collision_owner')
    expected_hulls = manifest.get('source_collision_hulls') if row.get('name') == owner else 0
    if facts['collision_hulls'] != expected_hulls:
        raise ValueError('Whole collision does not belong exclusively to its declared owner')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate receipt field')
        result[key] = value
    return result


def _finite_bounds(value):
    return (isinstance(value, list) and len(value) == 2
            and all(isinstance(row, list) and len(row) == 3 for row in value)
            and all(type(v) in (int, float) and math.isfinite(v) for row in value for v in row)
            and all(a <= b for a, b in zip(*value)))



def selected_policy(value):
    """Retain the exact JSON object from the keyed selected projection, including frozen values."""
    if not hasattr(value, 'items'):
        raise ValueError('Selected semantic metadata must be an explicit object')
    return json.loads(json.dumps(dict(value), default=dict, sort_keys=True, allow_nan=False))


def validate_export_receipt(receipt_bytes, primary_bytes, *, asset,
                            primary_digest, payload_digest, facts, primary_name=None, native_policy=None):
    """Validate in-job receipt binding and binary framing, not native FBX geometry fidelity.

    The producer supplies the just-written bytes and their computed digests. The caller checks
    the exact two-file inventory. B2 later compares these bindings to independently frozen hashes.
    T1b compares real FBX geometry; this receipt/framing check is not that proof.
    """
    asset = name(asset)
    primary_name = primary_name or asset + '.fbx'
    if type(primary_name) is not str or not primary_name.endswith(('.fbx', '.glb')):
        raise ValueError('Invalid declared mesh primary')
    name(primary_name[:-4])
    if (type(primary_digest) is not str or len(primary_digest) != 64
            or any(c not in '0123456789abcdef' for c in primary_digest)
            or type(payload_digest) is not str or len(payload_digest) != 64
            or any(c not in '0123456789abcdef' for c in payload_digest)):
        raise ValueError('Expected SHA-256 content digests')
    if not isinstance(receipt_bytes, bytes) or not 0 < len(receipt_bytes) <= MAX_RECEIPT_BYTES:
        raise ValueError('Invalid receipt byte bound')
    receipt = json.loads(receipt_bytes, object_pairs_hook=_pairs,
                         parse_constant=lambda _value: (_ for _ in ()).throw(ValueError('Nonfinite receipt')))
    if (not isinstance(receipt, dict)
            or set(receipt) != {'schema', 'asset', 'primary', 'triangles', 'bounds', 'sha256', 'metadata'}
            or type(receipt['schema']) is not int or receipt['schema'] != 1
            or receipt['asset'] != asset or receipt['primary'] != primary_name
            or type(receipt['triangles']) is not int or not 0 < receipt['triangles'] <= TRIANGLE_LIMIT
            or not _finite_bounds(receipt['bounds']) or receipt['sha256'] != primary_digest):
        raise ValueError('Invalid or foreign FBX receipt')
    metadata = receipt['metadata']
    expected = dict(geometry_sha256=payload_digest, slots=facts['slots'], polygons=facts['polygons'],
                    collision_hulls=facts['collision_hulls'], uv_channels=facts['uv_channels'])
    if native_policy is not None:
        expected['native_policy'] = selected_policy(native_policy)
    if (json.dumps(metadata, sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False)
            or facts['asset'] != asset
            or receipt['triangles'] != facts['triangles']
            or receipt['bounds'] != [facts['min'], facts['max']]):
        raise ValueError('Export receipt differs from its selected geometry payload')
    # Bounded framing check only; do not claim this substitutes for native importer comparisons.
    if primary_name.endswith('.glb'):
        from atelier.gltf import glb_parts
        glb_parts(primary_bytes)
    elif not isinstance(primary_bytes, bytes) or len(primary_bytes) <= len(FBX_HEADER) + 4 or not primary_bytes.startswith(FBX_HEADER):
        raise ValueError('Expected an emitted binary FBX primary')
    return receipt
