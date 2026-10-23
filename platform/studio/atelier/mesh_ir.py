"""Deterministic static-mesh inputs for independently cached single-mesh exporters.

The representation contains consumed geometry, not authoring-file pointers or a
whole region's source identity. Unchanged pieces therefore keep identical inputs.
"""
import io
import json
from pathlib import Path
import stat
import tempfile
import zipfile

import numpy as np

from .export_manifest import TRIANGLE_LIMIT, name, real_directory

FIELDS = {'positions': ('f', 3), 'normals': ('f', 3), 'counts': ('i', None),
          'indices': ('i', None), 'materials': ('i', None), 'smooth': ('b', None)}
MAX_BYTES = 128 * 1024 * 1024


def encode(piece, *, key, slots, matrix, options, collisions=()):
    """Create one complete piece payload; parent history and other pieces are not inputs."""
    arrays = dict(positions=np.asarray(piece['positions'], dtype='<f4'),
                  normals=np.asarray(piece['normals'], dtype='<f4'),
                  counts=np.asarray([len(f) for f in piece['faces']], dtype='<i4'),
                  indices=np.asarray([i for f in piece['faces'] for i in f], dtype='<i4'),
                  materials=np.asarray(piece['materials'], dtype='<i4'),
                  smooth=np.asarray(piece['smooth'], dtype=np.bool_))
    uv, colour = [], []
    for index, (label, values) in enumerate(piece['uvs']):
        field = f'uv{index}'; arrays[field] = np.asarray(values, dtype='<f4')
        uv.append([label, field])
    for index, (label, domain, kind, values) in enumerate(piece['colours']):
        field = f'colour{index}'; arrays[field] = np.asarray(values, dtype='<f4')
        colour.append([label, domain, kind, field])
    selection = piece.get('selection', dict(uv_active=uv[0][0] if uv else None,
                         uv_render=uv[0][0] if uv else None, colour_active=colour[0][0] if colour else None,
                         colour_render=colour[0][0] if colour else None))
    metadata = dict(schema=2, asset=name(key), slots=slots, matrix=matrix, options=options, selection=selection,
                    uvs=uv, colours=colour, collisions=list(collisions))
    arrays['metadata'] = np.frombuffer(json.dumps(metadata, sort_keys=True, separators=(',', ':'),
                                                allow_nan=False).encode(), dtype=np.uint8)
    stream = io.BytesIO()
    np.savez_compressed(stream, **arrays)
    result = stream.getvalue()
    decode(result)
    return result


def decode(payload,*,_collision_payload=False):
    """@cc [owner:fontanierh,label:correctness] complete-atomic-mesh-input
    Static mesh payloads MUST be bounded, pickle-free and complete. Preserve ordered faces,
    winding, float32 corner normals, all UV/colour values and types, complete material slots,
    smoothing, active/render channel roles, transform and explicitly owned collision. Reject unknown/missing channels,
    malformed indexing and nonfinite values before an exporter creates Blender data.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise ValueError('Atomic mesh input exceeds its size bound')
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as container:
            expanded=sum(info.file_size for info in container.infolist())
            if expanded > MAX_BYTES:
                raise ValueError('Expanded atomic mesh input exceeds its size bound')
        with np.load(io.BytesIO(payload), allow_pickle=False) as saved:
            if len(saved.files) != len(set(saved.files)):
                raise ValueError('Duplicate atomic mesh fields')
            arrays = {key: saved[key] for key in saved.files}
    except (OSError, TypeError, KeyError, zipfile.BadZipFile) as error:
        raise ValueError('Invalid atomic mesh array container') from error
    encoded = arrays.pop('metadata', None)
    if encoded is None or encoded.dtype != np.uint8 or encoded.ndim != 1:
        raise ValueError('Atomic mesh metadata is missing')
    meta = json.loads(encoded.tobytes())
    if set(meta) != {'schema', 'asset', 'slots', 'matrix', 'options', 'uvs', 'colours', 'collisions', 'selection'} or meta['schema'] != 2:
        raise ValueError('Unsupported atomic mesh metadata')
    name(meta['asset'])
    slots, matrix = meta['slots'], np.asarray(meta['matrix'])
    if (not isinstance(slots, list) or not slots or len(slots) > 1024
            or any(not isinstance(slot, str) or not slot for slot in slots)
            or matrix.shape != (4, 4) or matrix.dtype.kind not in 'fi' or not np.isfinite(matrix).all()
            or not np.array_equal(matrix[3], [0, 0, 0, 1]) or np.linalg.det(matrix[:3, :3]) == 0
            or type(meta['options']) is not dict or type(meta['collisions']) is not list):
        raise ValueError('Invalid atomic mesh materials, transform or settings')
    for collision in meta['collisions']:
        from . import mesh_collision
        if type(collision) is not dict or set(collision) not in (mesh_collision.CORE,mesh_collision.RICH,mesh_collision.TRANSFORMED):
            raise ValueError('Invalid atomic collision fields')
        if _collision_payload:raise ValueError('Nested collision payloads are forbidden')
        vertices = np.asarray(collision['vertices'])
        transform = np.asarray(collision['matrix'])
        faces_ = collision['faces']
        if (vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 4
                or vertices.dtype.kind not in 'fi' or not np.isfinite(vertices).all()
                or transform.shape != (4, 4) or transform.dtype.kind not in 'fi'
                or not np.isfinite(transform).all() or not np.array_equal(transform[3], [0, 0, 0, 1])
                or np.linalg.det(transform[:3, :3]) == 0 or type(faces_) is not list or not faces_
                or any(type(face) is not list or len(face) < 3
                       or any(type(i) is not int or not 0 <= i < len(vertices) for i in face)
                       for face in faces_)):
            raise ValueError('Invalid atomic collision geometry')
        if 'corner_payload' in collision:
            packet,size=mesh_collision.unpack(collision);expanded+=size
            if expanded>MAX_BYTES:raise ValueError('Complete collision channels exceed the mesh input bound')
            mesh_collision.decode(collision,packet=packet)
    for field, (kind, width) in FIELDS.items():
        value = arrays.get(field)
        required = np.dtype('<f4' if kind == 'f' else '<i4' if kind == 'i' else '?')
        if (value is None or value.dtype != required
                or (value.ndim != 1 if width is None else value.ndim != 2 or value.shape[1] != width)
                or not np.isfinite(value).all()):
            raise ValueError('Invalid atomic mesh channel: ' + field)
    positions, normals = arrays['positions'], arrays['normals']
    counts, indices = arrays['counts'], arrays['indices']
    faces = len(counts); corners = len(indices)
    triangles = int(np.sum(counts.astype(np.int64) - 2))
    if (not len(positions) or np.any(counts < 3) or int(np.sum(counts.astype(np.int64))) != corners
            or len(normals) != corners or len(arrays['materials']) != faces or len(arrays['smooth']) != faces
            or not 0 < triangles <= TRIANGLE_LIMIT or np.any(indices < 0) or np.any(indices >= len(positions))
            or np.any(arrays['materials'] < 0) or np.any(arrays['materials'] >= len(slots))):
        raise ValueError('Atomic mesh topology or triangle budget is invalid')
    expected = set(FIELDS)
    labels = set()
    for label, field in meta['uvs']:
        if (not isinstance(label, str) or not label or label in labels or field in expected
                or field not in arrays or arrays[field].shape != (corners, 2)
                or arrays[field].dtype != np.dtype('<f4') or not np.isfinite(arrays[field]).all()):
            raise ValueError('Invalid atomic UV channel')
        expected.add(field); labels.add(label)
    for label, domain, kind, field in meta['colours']:
        size = len(positions) if domain == 'POINT' else corners
        if (not isinstance(label, str) or not label or label in labels
                or domain not in ('POINT', 'CORNER') or kind not in ('FLOAT_COLOR', 'BYTE_COLOR')
                or field in expected or field not in arrays or arrays[field].shape != (size, 4)
                or arrays[field].dtype != np.dtype('<f4') or not np.isfinite(arrays[field]).all()):
            raise ValueError('Invalid atomic colour channel')
        expected.add(field); labels.add(label)
    selection = meta['selection']
    if (type(selection) is not dict or set(selection) != {'uv_active', 'uv_render', 'colour_active', 'colour_render'}
            or any(selection[role] is not None and selection[role] not in [entry[0] for entry in meta['uvs']]
                   for role in ('uv_active', 'uv_render'))
            or any(selection[role] is not None and selection[role] not in [entry[0] for entry in meta['colours']]
                   for role in ('colour_active', 'colour_render'))):
        raise ValueError('Invalid atomic active/render channel selection')
    if set(arrays) != expected:
        raise ValueError('Atomic mesh input contains undeclared fields')
    boundaries = np.cumsum(counts, dtype=np.int64)[:-1]
    piece = dict(selection=selection, positions=positions, normals=normals,
                 faces=[a.tolist() for a in np.split(indices, boundaries)],
                 materials=arrays['materials'], smooth=arrays['smooth'], slots=slots,
                 uvs=[(label, arrays[field]) for label, field in meta['uvs']],
                 colours=[(label, domain, kind, arrays[field]) for label, domain, kind, field in meta['colours']],
                 triangles=triangles)
    return meta, piece


def write(path, payload):
    """Validate before publication; preserve identical existing bytes and refuse links."""
    decode(payload)
    path = Path(path)
    real_directory(path.parent, create=True)
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        mode = None
    if mode is not None:
        if not stat.S_ISREG(mode):
            raise ValueError('Atomic mesh destination must be a regular file')
        if path.read_bytes() == payload:
            return False
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.mesh-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload); stream.flush()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return True
