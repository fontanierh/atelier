"""Capture completed logical geometry into independently consumed bounded export inputs.

No FBX/GLB is written here. Normal recipe discovery creates one export task for
one payload; unchanged payload bytes remain current after another part changes.
"""
import json
from pathlib import Path

import numpy as np

from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory, sha
from atelier.mesh_cells import cell_face_groups
from atelier import mesh_ir
from atelier.model_files import member
import region_plan_files
from mesh_pieces import capture, subset

CELL_METRES = 128.


def capture_colliders(boxes):
    """Capture the original authored whole boxes once, without assigning them to each child."""
    import bpy
    collisions = []
    for centre, size, rotation in boxes:
        bpy.ops.mesh.primitive_cube_add(size=1, location=centre, rotation=rotation)
        hull = bpy.context.object
        hull.scale = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        collisions.append(dict(vertices=[list(v.co) for v in hull.data.vertices],
                               faces=[list(f.vertices) for f in hull.data.polygons],
                               matrix=[list(row) for row in hull.matrix_world]))
        bpy.data.objects.remove(hull, do_unlink=True)
    return collisions


def plan(obj, root, *, collisions=(), options=None, cell_metres=CELL_METRES):
    """@cc [owner:fontanierh,label:correctness;performance] planned-independent-mesh-pieces
    Capture complete original corner channels before partitioning. Every source face MUST have
    exactly one piece owner and every piece MUST fit the atomic export budget. Whole authored
    UCX MUST belong to exactly one piece. The assembly MUST retain the parent's collision
    policy independently of each child's owned hull count, so render-only children cannot
    introduce additional simple blocking surfaces when the parent used authored UCX.
    Per-piece payloads MUST exclude unrelated piece identities and whole-parent receipts so
    unchanged logical geometry remains independently cacheable. No mesh export occurs here.
    """
    if obj.type != 'MESH' or obj.modifiers or getattr(obj.data, 'shape_keys', None) is not None:
        raise ValueError('Logical planning requires a completed static mesh without modifiers or shape keys')
    parent = name(obj.name)
    root = real_directory(root)
    source = capture(obj.data)
    matrix = np.asarray(obj.matrix_world, dtype=np.float64)
    world = source['positions'] @ matrix[:3, :3].T + matrix[:3, 3]
    faces = [source['vertex_indices'][s:s + n].tolist() for s, n in zip(source['starts'], source['counts'])]
    triangles = int(sum(source['counts'] - 2))
    if not faces or not source['slots'] or any(slot is None for slot in source['slots']):
        raise ValueError('Logical mesh requires geometry and a complete material table')
    if triangles <= TRIANGLE_LIMIT:
        groups = [(None, None, '', tuple(range(len(faces))))]
    else:
        groups = cell_face_groups(world, faces, cell_metres, triangle_limit=TRIANGLE_LIMIT)
    keys = [parent if x is None else f'{parent}_cell_{x}_{y}' + ('_Piece' + suffix if suffix else '')
            for x, y, suffix, _ in groups]
    region_plan_files.begin(root, parent, [key + '.npz' for key in keys])
    owned = np.zeros(len(faces), dtype=np.int32)
    rows = []
    for x, y, suffix, members in groups:
        key = parent if x is None else f'{parent}_cell_{x}_{y}' + ('_Piece' + suffix if suffix else '')
        piece = subset(source, members)
        np.add.at(owned, list(members), 1)
        payload = mesh_ir.encode(piece, key=key, slots=[m.name for m in source['slots']],
                                 matrix=matrix.tolist(), options=options or {},
                                 collisions=collisions if not rows else ())
        relative = key + '.npz'
        mesh_ir.write(root / relative, payload)
        used = world[piece['used']]
        rows.append(dict(name=key, payload=relative, sha256=sha(root / relative),
                         triangles=piece['triangles'], polygons=len(members),
                         min=used.min(0).tolist(), max=used.max(0).tolist(),
                         collision_hulls=len(collisions) if not rows else 0))
    if not np.all(owned == 1) or sum(r['triangles'] for r in rows) != triangles:
        raise ValueError('Logical geometry is not completely and exclusively partitioned')
    value = dict(schema=1, parent=parent, complete=True, triangle_limit=TRIANGLE_LIMIT,
                 source_triangles=triangles, source_polygons=len(faces), source_collision_hulls=len(collisions),
                 slots=[m.name for m in source['slots']], matrix=matrix.tolist(), pieces=rows)
    # Validate the complete current set before retiring any superseded inputs.
    validate(root, value)
    region_plan_files.finish(root, value)
    return value


def validate(root, value=None):
    """Validate a complete planner inventory before discovering any executable child tasks."""
    root = real_directory(root)
    published = value is None
    if published:
        actual = region_plan_files.files(root)
        value = json.loads((root / 'plan.json').read_text())
        if actual != {'plan.json', *(row['payload'] for row in value['pieces'])}:
            raise ValueError('Incomplete or foreign logical plan membership')
    if (value.get('schema') != 1 or value.get('complete') is not True
            or value.get('triangle_limit') != TRIANGLE_LIMIT or not value.get('pieces')):
        raise ValueError('Missing or incomplete logical export plan')
    name(value['parent'])
    hulls = value.get('source_collision_hulls')
    polygons = value.get('source_polygons')
    if type(hulls) is not int or hulls < 0 or type(polygons) is not int or polygons <= 0:
        raise ValueError('Missing logical parent collision or polygon ownership')
    mesh_set = value.get('kind') == 'mesh_set'
    if value.get('kind') not in (None, 'mesh_set') or (mesh_set and hulls != 0):
        raise ValueError('Unsupported logical geometry ownership kind')
    seen, total, total_polygons = set(), 0, 0
    all_slots = set()
    for index, row in enumerate(value['pieces']):
        key = name(row['name'])
        if (key.casefold() in seen or member(row['payload']) != key + '.npz'
                or type(row['triangles']) is not int or not 0 < row['triangles'] <= TRIANGLE_LIMIT
                or (mesh_set and not (key == value['parent'] or key.startswith(value['parent'] + '_')))):
            raise ValueError('Duplicate or noncanonical planned export')
        seen.add(key.casefold())
        path = root / row['payload']
        if path.is_symlink() or not path.is_file() or sha(path) != row['sha256']:
            raise ValueError('Planned geometry input is missing or changed')
        meta, piece = mesh_ir.decode(path.read_bytes())
        if (meta['asset'] != key or piece['triangles'] != row['triangles']
                or row.get('polygons') != len(piece['faces'])
                or meta['slots'] != (row.get('slots') if mesh_set else value['slots']) or meta['matrix'] != value['matrix']
                or len(meta['collisions']) != (hulls if index == 0 else 0)
                or row.get('collision_hulls') != len(meta['collisions'])):
            raise ValueError('Planned geometry identity or logical ownership differs')
        matrix = np.asarray(meta['matrix'])
        world = piece['positions'] @ matrix[:3, :3].T + matrix[:3, 3]
        if (not np.array_equal(world.min(0), row.get('min'))
                or not np.array_equal(world.max(0), row.get('max'))):
            raise ValueError('Planned geometry bounds differ from the current payload')
        all_slots.update(meta['slots'])
        total += piece['triangles']
        total_polygons += len(piece['faces'])
    if mesh_set and (not isinstance(value.get('metadata'), dict)
                     or set(value['metadata']) != {r['name'] for r in value['pieces']}
                     or any(not isinstance(v, dict) for v in value['metadata'].values())):
        raise ValueError('Finished mesh-set semantic inventory is incomplete')
    if mesh_set and sorted(all_slots) != value['slots']:
        raise ValueError('Finished mesh-set material inventory is incomplete')
    if total != value['source_triangles'] or total_polygons != polygons:
        raise ValueError('Planned geometry triangle conservation failed')
    return value


def present(root):
    try:
        validate(Path(root))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
