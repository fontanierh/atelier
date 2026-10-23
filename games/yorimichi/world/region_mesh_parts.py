"""Capture completed logical geometry into independently consumed bounded export inputs.

No FBX/GLB is written here. Normal recipe discovery creates one export task for
one payload; unchanged payload bytes remain current after another part changes.
"""
import json
from pathlib import Path

import numpy as np

from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory, sha
from atelier.mesh_cells import cell_face_groups
from atelier import mesh_ir,mesh_collision
from atelier.model_files import member
import region_plan_files
from mesh_pieces import capture, subset

CELL_METRES = 128.


def capture_collision(hull):
    """Capture an already-finished original hull, including its actual corner channels."""
    if (hull.parent is not None or hull.constraints or hull.modifiers or hull.animation_data is not None
            or tuple(hull.delta_location)!=(0.,0.,0.) or tuple(hull.delta_scale)!=(1.,1.,1.)
            or tuple(hull.delta_rotation_euler)!=(0.,0.,0.) or tuple(hull.delta_rotation_quaternion)!=(1.,0.,0.,0.)):
        raise ValueError('Collision capture requires a complete static unparented transform')
    source=capture(hull.data)
    piece={key:source[key] for key in ('positions','normals','materials','smooth','uvs','colours','selection')}
    piece['faces']=[list(face.vertices) for face in hull.data.polygons]
    return mesh_collision.encode(piece,slots=[material.name for material in source['slots']],
        matrix=[list(row) for row in hull.matrix_world],transform=dict(
            location=list(hull.location),scale=list(hull.scale),rotation_mode=hull.rotation_mode,
            rotation_euler=list(hull.rotation_euler),rotation_quaternion=list(hull.rotation_quaternion),
            rotation_axis_angle=list(hull.rotation_axis_angle)))


def capture_colliders(boxes):
    """Capture the original authored whole boxes once, without assigning them to each child."""
    import bpy
    collisions = []
    for centre, size, rotation in boxes:
        bpy.ops.mesh.primitive_cube_add(size=1, location=centre, rotation=rotation)
        hull = bpy.context.object
        hull.scale = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        data=hull.data
        try:collisions.append(capture_collision(hull))
        finally:
            bpy.data.objects.remove(hull, do_unlink=True)
            if data.users==0:bpy.data.meshes.remove(data)
    return collisions


def plan(obj, root, *, collisions=(), options=None, cell_metres=CELL_METRES, face_groups=None):
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
    if face_groups is None:
        spatial = ([(None, None, '', tuple(range(len(faces))))] if triangles <= TRIANGLE_LIMIT else
                   cell_face_groups(world, faces, cell_metres, triangle_limit=TRIANGLE_LIMIT))
        groups = [(parent if x is None else f'{parent}_cell_{x}_{y}' + ('_Piece' + suffix if suffix else ''), members)
                  for x, y, suffix, members in spatial]
    else:
        groups = [(key, tuple(members)) for key, members in face_groups]
    keys = [name(key) for key, _ in groups]
    validate_face_groups(groups, source['counts'])
    region_plan_files.begin(root, parent, [key + '.npz' for key in keys])
    owned = np.zeros(len(faces), dtype=np.int32)
    rows = []
    for key, members in groups:
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
                         source_faces=list(members),
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


def validate_face_groups(groups, counts):
    """@cc [owner:fontanierh,label:correctness] logical-piece-lod-face-membership
    Every original polygon MUST have exactly one bounded child owner. Explicit
    LOD groups MUST retain base polygon membership and names; simplification MUST
    NOT repartition leaves into different native components. Refuse missing,
    duplicate, out-of-range or unbounded groups before creating output files.
    """
    names, covered = set(), np.zeros(len(counts), dtype=np.int32)
    for key, members in groups:
        key = name(key)
        members = tuple(members)
        if (key.casefold() in names or not members or any(type(i) is not int or not 0 <= i < len(counts) for i in members)
                or not 0 < sum(int(counts[i])-2 for i in members) <= TRIANGLE_LIMIT):
            raise ValueError('Invalid bounded source face group')
        names.add(key.casefold())
        np.add.at(covered, list(members), 1)
    if not len(counts) or not np.all(covered == 1):
        raise ValueError('Source face groups must cover each polygon exactly once')


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
    if any('source_faces' in row for row in value['pieces']):
        groups = [(row['name'], row.get('source_faces', ())) for row in value['pieces']]
        # Polygon counts, not reduced triangle counts, determine conserved membership.
        validate_face_groups(groups, np.full(polygons, 3, dtype=np.int32))
        if any(len(row['source_faces']) != row['polygons'] for row in value['pieces']):
            raise ValueError('Source polygon membership differs from its current piece')
    if total != value['source_triangles'] or total_polygons != polygons:
        raise ValueError('Planned geometry triangle conservation failed')
    return value


def present(root):
    try:
        validate(Path(root))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
