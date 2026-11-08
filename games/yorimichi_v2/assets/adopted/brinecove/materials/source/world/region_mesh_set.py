"""Plan an explicit set of already finished bounded meshes from one logical data producer."""
import json
import numpy as np

from atelier import mesh_ir
from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory, sha
from mesh_pieces import capture, subset
import region_plan_files


def plan(objects, root, *, parent, metadata=None, options=None, diagnostics=None):
    """@cc [owner:fontanierh,label:correctness] complete-finished-regional-mesh-set
    Every object MUST already be a complete static bounded mesh. Preserve its exact
    ordered corner attributes, slots and common world frame in one independent payload.
    An explicit final mesh set MAY have per-piece material tables; it MUST NOT imply
    that these heterogeneous tables are the original slots of one monolithic mesh.
    Runtime policy metadata stays in this owner manifest, outside unrelated mesh keys.
    No FBX/GLB is exported here; refuse incomplete or duplicate objects before writes.
    """
    parent = name(parent)
    objects = tuple(objects)
    keys = [name(obj.name) for obj in objects]
    if not keys or len(set(k.casefold() for k in keys)) != len(keys):
        raise ValueError('Finished mesh set requires explicit unique objects')
    if any(not (key == parent or key.startswith(parent + '_')) for key in keys):
        raise ValueError('Finished mesh lies outside its logical owner')
    metadata = {key: {} for key in keys} if metadata is None else metadata
    diagnostics = {} if diagnostics is None else diagnostics
    if not isinstance(metadata, dict) or set(metadata) != set(keys) or any(not isinstance(v, dict) for v in metadata.values()):
        raise ValueError('Finished mesh-set runtime policy inventory is incomplete')
    if not isinstance(diagnostics, dict):
        raise ValueError('Finished mesh-set diagnostics require an explicit mapping')
    json.dumps(dict(metadata=metadata, diagnostics=diagnostics), allow_nan=False)
    root = real_directory(root)
    rows, sources, frame, all_slots = [], [], None, set()
    for obj in objects:
        if obj.type != 'MESH' or obj.modifiers or getattr(obj.data, 'shape_keys', None) is not None:
            raise ValueError('Finished mesh set requires completed static geometry')
        source = capture(obj.data)
        triangles = int(sum(source['counts'] - 2))
        if not 0 < triangles <= TRIANGLE_LIMIT or not source['slots'] or any(m is None for m in source['slots']):
            raise ValueError('Finished mesh set contains an unbounded or unbound object')
        matrix = np.asarray(obj.matrix_world, dtype=np.float64)
        if frame is None: frame = matrix
        if not np.array_equal(matrix, frame):
            raise ValueError('Finished mesh set requires one explicit placement frame')
        sources.append(source)
        all_slots.update(m.name for m in source['slots'])
    region_plan_files.begin(root, parent, [key + '.npz' for key in keys])
    for key, source in zip(keys, sources):
        data = subset(source, range(len(source['counts'])))
        slots = [m.name for m in source['slots']]
        relative = key + '.npz'
        mesh_ir.write(root / relative, mesh_ir.encode(data, key=key, slots=slots,
                      matrix=frame.tolist(), options=options or {}, collisions=()))
        world = data['positions'] @ frame[:3, :3].T + frame[:3, 3]
        rows.append(dict(name=key, payload=relative, sha256=sha(root / relative),
            triangles=data['triangles'], polygons=len(source['counts']),
            min=world.min(0).tolist(), max=world.max(0).tolist(), collision_hulls=0, slots=slots))
    value = dict(schema=1, kind='mesh_set', parent=parent, complete=True, triangle_limit=TRIANGLE_LIMIT,
        source_triangles=sum(r['triangles'] for r in rows), source_polygons=sum(r['polygons'] for r in rows),
        source_collision_hulls=0, slots=sorted(all_slots), matrix=frame.tolist(), pieces=rows,
        metadata=metadata, diagnostics=diagnostics)
    from region_mesh_parts import validate
    validate(root, value)
    region_plan_files.finish(root, value)
    return value
