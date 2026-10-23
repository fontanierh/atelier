"""Capture completed logical geometry into independently consumed bounded export inputs.

No FBX/GLB is written here. Normal recipe discovery creates one export task for
one payload; unchanged payload bytes remain current after another part changes.
"""
import json
import re
from pathlib import Path

import numpy as np

from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory, sha
from atelier.mesh_cells import cell_face_groups
from atelier import mesh_ir,mesh_collision
from atelier.model_files import member
import region_plan_files
from mesh_pieces import capture, subset

CELL_METRES = 128.


def compact_materials(piece, slots):
    """Keep face material identity while excluding unused parent slots from leaf bytes."""
    used = sorted({int(index) for index in piece['materials']})
    if not used or used[0] < 0 or used[-1] >= len(slots):
        raise ValueError('Piece material index escaped the original table')
    remap = {old: new for new, old in enumerate(used)}
    result = dict(piece, materials=np.asarray([remap[int(index)] for index in piece['materials']], dtype=np.int32))
    return result, [slots[index] for index in used], used


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


def plan(obj, root, *, collisions=(), options=None, cell_metres=CELL_METRES, face_groups=None, material_specs=None,
         partition=None, collision_owner=None):
    """@cc [owner:fontanierh,label:correctness;performance] planned-independent-mesh-pieces
    Capture complete original corner channels before partitioning. Every source face MUST have
    exactly one piece owner and every piece MUST fit the atomic export budget. Whole authored
    UCX MUST belong to exactly one explicitly authored piece. Whole units MUST
    remain whole and refuse oversize geometry; declared spatial owners MUST stay
    spatial even below the total budget. Spatial UCX owners MUST declare an existing
    member key; missing owners MUST refuse rather than transfer hulls or invent geometry.
    The assembly MUST retain the parent's collision
    policy independently of each child's owned hull count, so render-only children cannot
    introduce additional simple blocking surfaces when the parent used authored UCX.
    Per-piece payloads MUST exclude unrelated piece identities and whole-parent receipts so
    unchanged logical geometry remains independently cacheable. Unused parent material slots
    MUST stay outside a leaf payload; face material names/order MUST survive local remapping.
    The complete original table remains in logical metadata. No mesh export occurs here.
    """
    if obj.type != 'MESH' or obj.modifiers or getattr(obj.data, 'shape_keys', None) is not None:
        raise ValueError('Logical planning requires a completed static mesh without modifiers or shape keys')
    if face_groups is None:
        if partition not in ('whole', 'spatial'):
            raise ValueError('Declare whole or spatial logical authoring policy')
    elif partition not in (None, 'explicit'):
        raise ValueError('Explicit face groups cannot use an automatic partition policy')
    else:
        partition = 'explicit'
    if collision_owner is not None: name(collision_owner)
    collisions = tuple(collisions)
    parent = name(obj.name)
    root = real_directory(root)
    source = capture(obj.data)
    if material_specs is not None and (type(material_specs) is not list or len(material_specs) != len(source['slots'])):
        raise ValueError('Explicit material descriptors differ from the original slot table')
    matrix = np.asarray(obj.matrix_world, dtype=np.float64)
    world = source['positions'] @ matrix[:3, :3].T + matrix[:3, 3]
    faces = [source['vertex_indices'][s:s + n].tolist() for s, n in zip(source['starts'], source['counts'])]
    triangles = int(sum(source['counts'] - 2))
    if not faces or not source['slots'] or any(slot is None for slot in source['slots']):
        raise ValueError('Logical mesh requires geometry and a complete material table')
    if partition == 'whole':
        groups = [(parent, tuple(range(len(faces))))]
    elif partition == 'spatial':
        spatial = cell_face_groups(world, faces, cell_metres, triangle_limit=TRIANGLE_LIMIT)
        groups = [(f'{parent}_cell_{x}_{y}' + ('_Piece' + suffix if suffix else ''), members)
                  for x, y, suffix, members in spatial]
    else:
        groups = [(key, tuple(members)) for key, members in face_groups]
    validate_face_groups(groups, source['counts'])
    if collisions:
        if collision_owner is None:
            if len(groups) != 1 or partition == 'spatial':
                raise ValueError('Spatial or multi-piece UCX requires an explicit collision-owner key')
            collision_owner = groups[0][0]
        if collision_owner not in {key for key, _ in groups}:
            raise ValueError('Declared collision-owner render member is absent')
        # Existing readers put the complete authored UCX owner first. This order is
        # determined by the declaration, never by sorted/new cell membership.
        groups.sort(key=lambda row: row[0] != collision_owner)
    else:
        collision_owner = None
    keys = [name(key) for key, _ in groups]
    region_plan_files.begin(root, parent, [key + '.npz' for key in keys])
    owned = np.zeros(len(faces), dtype=np.int32)
    rows = []
    for key, members in groups:
        piece = subset(source, members)
        np.add.at(owned, list(members), 1)
        piece, slots, material_indices = compact_materials(piece, [m.name for m in source['slots']])
        payload = mesh_ir.encode(piece, key=key, slots=slots,
                                 matrix=matrix.tolist(), options=options or {},
                                 material_specs=None if material_specs is None else [material_specs[i] for i in material_indices],
                                 collisions=collisions if key == collision_owner else ())
        relative = key + '.npz'
        mesh_ir.write(root / relative, payload)
        used = world[piece['used']]
        rows.append(dict(name=key, payload=relative, sha256=sha(root / relative),
                         triangles=piece['triangles'], polygons=len(members),
                         source_faces=list(members), slots=slots, source_material_indices=material_indices,
                         min=used.min(0).tolist(), max=used.max(0).tolist(),
                         collision_hulls=len(collisions) if key == collision_owner else 0))
    if not np.all(owned == 1) or sum(r['triangles'] for r in rows) != triangles:
        raise ValueError('Logical geometry is not completely and exclusively partitioned')
    value = dict(schema=1, parent=parent, complete=True, triangle_limit=TRIANGLE_LIMIT,
                 partition=partition, collision_owner=collision_owner,
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
    if not mesh_set:
        partition = value.get('partition')
        collision_owner = value.get('collision_owner')
        if (partition not in ('whole', 'spatial', 'explicit') or 'collision_owner' not in value
                or (hulls > 0 and (not isinstance(collision_owner, str) or value['pieces'][0]['name'] != collision_owner))
                or (hulls == 0 and collision_owner is not None)):
            raise ValueError('Missing or inconsistent authored partition/collision ownership')
        if partition == 'whole' and [row['name'] for row in value['pieces']] != [value['parent']]:
            raise ValueError('Whole logical owner cannot silently partition')
        if partition == 'spatial' and any(not re.fullmatch(re.escape(value['parent']) +
                r'_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?', row['name']) for row in value['pieces']):
            raise ValueError('Spatial logical owner cannot collapse to a whole parent')
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
        slots = row.get('slots', value['slots'])
        if not mesh_set and 'slots' in row:
            indices = row.get('source_material_indices')
            if (not isinstance(indices, list) or not indices or any(type(i) is not int or not 0 <= i < len(value['slots']) for i in indices)
                    or indices != sorted(set(indices)) or slots != [value['slots'][i] for i in indices]
                    or set(piece['materials']) != set(range(len(slots)))):
                raise ValueError('Piece material ownership differs from its original face table')
        if (meta['asset'] != key or piece['triangles'] != row['triangles']
                or row.get('polygons') != len(piece['faces'])
                or meta['slots'] != (row.get('slots') if mesh_set else slots) or meta['matrix'] != value['matrix']
                or len(meta['collisions']) != (hulls if (mesh_set and index == 0) or (not mesh_set and key == collision_owner) else 0)
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
