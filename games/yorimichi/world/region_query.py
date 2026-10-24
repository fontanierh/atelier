"""Explicit triangulated query surfaces, independent of exported mesh files."""
import io
import json
from pathlib import Path
import stat
import tempfile
import zipfile

import numpy as np

from atelier.atomic_files import managed_temporary_parent
from atelier.export_manifest import name, real_directory

MAX_BYTES = 256 * 1024 * 1024


def capture(obj, *, role='render'):
    """Read the completed Blender mesh's actual tessellation, never a polygon fan."""
    if obj.type != 'MESH' or obj.modifiers or getattr(obj.data, 'shape_keys', None) is not None:
        raise ValueError('Query capture requires completed static geometry')
    from mesh_pieces import values
    obj.data.calc_loop_triangles()
    triangles = np.empty(len(obj.data.loop_triangles) * 3, dtype='<i4')
    obj.data.loop_triangles.foreach_get('vertices', triangles)
    return dict(name=name(obj.name), role=role, positions=values(obj.data.vertices, 'co', 3),
                triangles=triangles.reshape(-1, 3), matrix=np.asarray(obj.matrix_world, dtype='<f8'))


def capture_group(objects, *, owner):
    """Compose only query arrays from completed pieces sharing their authored frame.

    This does not join Blender geometry or create a mesh export. The rendered
    objects and their independent export identities remain separate.
    """
    objects = tuple(objects)
    if not objects or len({id(obj) for obj in objects}) != len(objects):
        raise ValueError('Query group requires complete unique source pieces')
    positions, indices, offset, frame = [], [], 0, None
    for obj in objects:
        surface = capture(obj)
        if frame is not None and not np.array_equal(surface['matrix'], frame):
            raise ValueError('Query group pieces must share their explicit authored frame')
        frame = surface['matrix']
        positions.append(surface['positions'])
        indices.append(surface['triangles'].astype('<i8') + offset)
        offset += len(surface['positions'])
    return dict(name=name(owner), role='render', matrix=frame,
                positions=np.concatenate(positions), triangles=np.concatenate(indices))


def capture_colliders(owner, collisions):
    """Use the same authored whole hulls, each once, with Blender tessellation."""
    import bpy
    from mathutils import Matrix
    result = []
    for index, collision in enumerate(collisions):
        key = f'UCX_{name(owner)}_{index:04d}'
        mesh = bpy.data.meshes.new(key)
        obj = bpy.data.objects.new(key, mesh)
        try:
            mesh.from_pydata(collision['vertices'], [], collision['faces'])
            mesh.update()
            obj.matrix_world = Matrix(collision['matrix'])
            result.append(capture(obj, role='collision'))
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.meshes.remove(mesh)
    return result


def encode(surfaces, *, owner, stage):
    arrays, rows = {}, []
    for index, surface in enumerate(surfaces):
        prefix = f's{index}_'
        rows.append(dict(name=surface['name'], role=surface['role'], prefix=prefix))
        arrays[prefix + 'positions'] = np.asarray(surface['positions'], dtype='<f4')
        arrays[prefix + 'triangles'] = np.asarray(surface['triangles'])
        arrays[prefix + 'matrix'] = np.asarray(surface['matrix'], dtype='<f8')
    arrays['metadata'] = np.frombuffer(json.dumps(dict(schema=1, owner=owner, stage=stage,
        surfaces=rows), sort_keys=True, separators=(',', ':'), allow_nan=False).encode(), dtype=np.uint8)
    stream = io.BytesIO()
    np.savez_compressed(stream, **arrays)
    payload = stream.getvalue()
    decode(payload, owner=owner, stage=stage)
    return payload


def decode(payload, *, owner, stage):
    """@cc [owner:fontanierh,label:correctness] explicit-stage-query-geometry
    A query product MUST bind its logical owner, raw/final stage, original transform,
    actual ordered render tessellation and separately owned whole collision surfaces.
    Consumers MUST request the intended stage explicitly. No export path, sibling
    manifest or source revision enters unchanged geometry bytes. Malformed, linked,
    oversized or incomplete data MUST refuse rather than fall back to mesh exports.
    """
    try:
        return _decode(payload, owner=owner, stage=stage)
    except (zipfile.BadZipFile, OSError, EOFError, KeyError, TypeError) as error:
        raise ValueError('Malformed query geometry container') from error


def _decode(payload, *, owner, stage):
    name(owner)
    if stage not in ('raw', 'final') or not isinstance(payload, bytes) or len(payload) > MAX_BYTES:
        raise ValueError('Invalid query product stage or size')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_BYTES:
            raise ValueError('Expanded query product exceeds its size bound')
    with np.load(io.BytesIO(payload), allow_pickle=False) as data:
        if len(data.files) != len(set(data.files)):
            raise ValueError('Duplicate query product fields')
        encoded = data['metadata']
        if encoded.dtype != np.uint8 or encoded.ndim != 1:
            raise ValueError('Missing query product metadata')
        metadata = json.loads(encoded.tobytes())
        if (set(metadata) != {'schema', 'owner', 'stage', 'surfaces'} or type(metadata['schema']) is not int or metadata['schema'] != 1
                or metadata['owner'] != owner or metadata['stage'] != stage
                or not isinstance(metadata['surfaces'], list) or not metadata['surfaces']):
            raise ValueError('Query product identity or surface inventory differs')
        result, seen, fields = [], set(), {'metadata'}
        for index, row in enumerate(metadata['surfaces']):
            if (set(row) != {'name', 'role', 'prefix'} or row['prefix'] != f's{index}_'
                    or name(row['name']).casefold() in seen or row['role'] not in ('render', 'collision')
                    or (row['role'] == 'render' and row['name'] != owner)
                    or (row['role'] == 'collision' and not row['name'].startswith('UCX_' + owner + '_'))):
                raise ValueError('Invalid query surface identity')
            seen.add(row['name'].casefold())
            keys = [row['prefix'] + field for field in ('positions', 'triangles', 'matrix')]
            positions, triangles, matrix = (data[key] for key in keys)
            if (positions.dtype != np.dtype('<f4') or positions.ndim != 2 or positions.shape[1] != 3
                    or not len(positions) or not np.isfinite(positions).all()
                    or triangles.dtype.kind not in 'iu' or triangles.ndim != 2 or triangles.shape[1] != 3
                    or not len(triangles) or triangles.min() < 0 or triangles.max() >= len(positions)
                    or matrix.dtype != np.dtype('<f8') or matrix.shape != (4, 4)
                    or not np.isfinite(matrix).all() or not np.array_equal(matrix[3], [0, 0, 0, 1])
                    or np.linalg.det(matrix[:3, :3]) == 0):
                raise ValueError('Invalid query geometry or transform')
            fields.update(keys)
            result.append(dict(name=row['name'], role=row['role'], positions=positions,
                               triangles=triangles, matrix=matrix))
        if set(data.files) != fields or sum(row['role'] == 'render' for row in result) != 1:
            raise ValueError('Incomplete or foreign query geometry fields')
    return result


def save(path, surfaces, *, owner, stage):
    """@cc [owner:fontanierh,label:correctness;safety] scoped-region-query-temporaries
    Query bytes, unchanged-file identity and default sibling replacement MUST stay
    unchanged. Managed calls MUST use their existing held temporary scope on the
    destination filesystem, without enlarging the exact product ownership.
    """
    payload = encode(surfaces, owner=owner, stage=stage)
    path = Path(path); real_directory(path.parent)
    if path.exists() or path.is_symlink():
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Query destination must be a regular unlinked file')
        if path.read_bytes() == payload:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=managed_temporary_parent(path), prefix='.query-', delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(payload); stream.flush(); temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    return True


def load(path, *, owner, stage):
    path = Path(path); real_directory(path.parent)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Query input must be a bounded regular unlinked file')
    return decode(path.read_bytes(), owner=owner, stage=stage)


def triangles(surfaces, *, placement=None, roles=('render', 'collision')):
    """Apply each authored frame followed by the logical instance frame, exactly once."""
    placement = np.eye(4) if placement is None else np.asarray(placement, dtype='<f8')
    if (placement.shape != (4, 4) or not np.isfinite(placement).all()
            or not np.array_equal(placement[3], [0, 0, 0, 1]) or np.linalg.det(placement[:3, :3]) == 0
            or not roles or any(role not in ('render', 'collision') for role in roles)):
        raise ValueError('Invalid query placement or role selection')
    result = []
    for surface in surfaces:
        if surface['role'] in roles:
            matrix = placement @ surface['matrix']
            vertices = surface['positions'] @ matrix[:3, :3].T + matrix[:3, 3]
            result.append(vertices[surface['triangles']])
    return np.concatenate(result) if result else np.empty((0, 3, 3), dtype='<f8')
