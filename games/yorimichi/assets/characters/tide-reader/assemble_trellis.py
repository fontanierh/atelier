"""Assemble Kiyo's processed TRELLIS head and body with the authored hat.

Run in headless Blender through atelier.safety.guarded. Geometry textures and UVs
come from the processed head and body GLBs; the hat, staff, board and satchel are
extracted from the preserved procedural source. The body is uniformly fitted,
the head is uniformly scaled and placed on the neck plug, and every part shares
one 30-bone armature (23 humanoid core joints plus Kiyo accessory joints).
"""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

CORE = [
    'root', 'pelvis', 'spine', 'spine_mid', 'chest', 'neck', 'head',
    'clavicle_L', 'upperarm_L', 'forearm_L', 'hand_L',
    'clavicle_R', 'upperarm_R', 'forearm_R', 'hand_R',
    'thigh_L', 'shin_L', 'foot_L', 'toe_L',
    'thigh_R', 'shin_R', 'foot_R', 'toe_R',
]
EXTRAS = ['hat', 'hair_bun', 'cape_L', 'cape_R', 'staff', 'tide_board', 'satchel']
FLOOR = 0.0065
BODY_TOP = 1.115
HEAD_BOTTOM = 1.08
HEAD_HEIGHT = 0.325
HEAD_TOP = HEAD_BOTTOM + HEAD_HEIGHT
PROFILE_CLEARANCE = 0.020
HAT_CONTACT_OVERLAP = 0.004
HAT_CONTACT_RADIUS = 0.015


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--head', type=Path, required=True)
    parser.add_argument('--body', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
    for path in (args.head, args.body, args.baseline):
        if not path.is_file():
            parser.error(f'missing input {path}')
    args.output.mkdir(parents=True, exist_ok=True)
    return args


def mesh_bounds(obj):
    coords = np.array([v.co[:] for v in obj.data.vertices], dtype=np.float64)
    return coords, coords.min(axis=0), coords.max(axis=0)


def transform_mesh(obj, scale, offset):
    for vertex in obj.data.vertices:
        vertex.co = (vertex.co * scale) + Vector(offset)
    obj.data.update()
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, 0)
    obj.scale = (1, 1, 1)


def import_mesh(path, name):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path.resolve()))
    added = [obj for obj in bpy.context.scene.objects if obj not in before and obj.type == 'MESH']
    if len(added) != 1:
        raise ValueError(f'{path.name}: expected one mesh, found {len(added)}')
    obj = added[0]
    obj.name = obj.data.name = name
    return obj


def extract_group(source, group_name):
    group = source.vertex_groups.get(group_name)
    if group is None:
        raise ValueError(f'baseline has no {group_name} group')
    selected = set()
    for vertex in source.data.vertices:
        for assignment in vertex.groups:
            if assignment.group == group.index and assignment.weight > 0.01:
                selected.add(vertex.index)
                break
    if not selected:
        raise ValueError(f'baseline group {group_name} is empty')
    faces = [poly for poly in source.data.polygons if all(index in selected for index in poly.vertices)]
    used = sorted({index for poly in faces for index in poly.vertices})
    mapping = {old: new for new, old in enumerate(used)}
    mesh = bpy.data.meshes.new(f'{group_name}_source')
    mesh.from_pydata([source.data.vertices[index].co[:] for index in used], [], [tuple(mapping[index] for index in poly.vertices) for poly in faces])
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(f'Kiyo_{group_name}', mesh)
    bpy.context.collection.objects.link(obj)
    source_color = source.data.color_attributes.active_color
    if source_color is not None:
        target_color = mesh.color_attributes.new(name=source_color.name, type=source_color.data_type, domain='CORNER')
        for new_poly, old_poly in zip(mesh.polygons, faces):
            for new_loop, old_loop in zip(new_poly.loop_indices, old_poly.loop_indices):
                target_color.data[new_loop].color = source_color.data[old_loop].color
        mesh.color_attributes.active_color = target_color
    if source.data.materials:
        mesh.materials.append(source.data.materials[0])
    for poly in mesh.polygons:
        poly.use_smooth = False
    return obj


def create_armature(landmarks):
    data = bpy.data.armatures.new('Kiyo_Trellis_Skeleton')
    arm = bpy.data.objects.new('Kiyo_Trellis_Rig', data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bones = data.edit_bones

    def bone(name, head, tail, parent=None, deform=True):
        item = bones.new(name)
        item.head = head
        item.tail = tail
        item.use_deform = deform
        if parent:
            item.parent = bones[parent]
        return item

    hip = landmarks['hip_z']
    arm_z = landmarks['arm_z']
    arm_y = landmarks['arm_y']
    max_x = landmarks['max_x']
    shoulder_x = min(0.14, max_x * 0.22)
    bone('root', (0, 0, 0), (0, 0, .08), deform=False)
    bone('pelvis', (0, 0, hip), (0, 0, .65), 'root')
    bone('spine', (0, 0, .65), (0, 0, .73), 'pelvis')
    bone('spine_mid', (0, 0, .73), (0, 0, .81), 'spine')
    bone('chest', (0, 0, .81), (0, 0, arm_z), 'spine_mid')
    neck_x, neck_y = landmarks['neck_xy']
    crown_x, crown_y = landmarks['crown_xy']
    hat_z = landmarks['hat_z']
    bone('neck', (0, 0, arm_z), (neck_x, neck_y, HEAD_BOTTOM), 'chest')
    bone('head', (neck_x, neck_y, HEAD_BOTTOM), (neck_x, neck_y, HEAD_TOP), 'neck')
    for side, sign in (('L', 1), ('R', -1)):
        bone('clavicle_' + side, (0, 0, arm_z - .015),
             (sign * shoulder_x, arm_y, arm_z), 'chest')
        bone('upperarm_' + side, (sign * shoulder_x, arm_y, arm_z),
             (sign * max_x * .48, arm_y, arm_z), 'clavicle_' + side)
        bone('forearm_' + side, (sign * max_x * .48, arm_y, arm_z),
             (sign * max_x * .74, arm_y, arm_z), 'upperarm_' + side)
        bone('hand_' + side, (sign * max_x * .74, arm_y, arm_z),
             (sign * max_x, arm_y, arm_z), 'forearm_' + side)
        bone('thigh_' + side, (sign * .11, 0, hip),
             (sign * .12, 0, .30), 'pelvis')
        bone('shin_' + side, (sign * .12, 0, .30),
             (sign * .13, 0, .085), 'thigh_' + side)
        bone('foot_' + side, (sign * .13, 0, .085),
             (sign * .13, -.105, .045), 'shin_' + side)
        bone('toe_' + side, (sign * .13, -.105, .045),
             (sign * .13, -.175, .040), 'foot_' + side)
    bone('hat', (crown_x, crown_y, hat_z), (crown_x, crown_y, hat_z + .147), 'head', deform=False)
    bone('hair_bun', (crown_x, crown_y + .02, HEAD_TOP - .20),
         (crown_x, crown_y + .09, HEAD_TOP - .27), 'head', deform=False)
    for side, sign in (('L', 1), ('R', -1)):
        bone('cape_' + side, (sign * .085, 0, arm_z - .05),
             (sign * .25, -.015, arm_z - .16), 'chest', deform=False)
    bone('staff', (landmarks['staff_head']), (landmarks['staff_tail']), 'hand_R', deform=False)
    bone('tide_board', (landmarks['board_head']), (landmarks['board_tail']), 'pelvis', deform=False)
    bone('satchel', (landmarks['satchel_head']), (landmarks['satchel_tail']), 'pelvis', deform=False)

    bpy.ops.object.mode_set(mode='OBJECT')
    for pose in arm.pose.bones:
        pose.rotation_mode = 'QUATERNION'
    arm.data.display_type = 'OCTAHEDRAL'
    arm.show_in_front = True
    return arm


def rigid_part(obj, arm, bone):
    group = obj.vertex_groups.get(bone) or obj.vertex_groups.new(name=bone)
    group.add(list(range(len(obj.data.vertices))), 1.0, 'REPLACE')
    obj.parent = arm
    modifier = obj.modifiers.new('Kiyo armature', 'ARMATURE')
    modifier.object = arm
    modifier.use_deform_preserve_volume = False


def prune_body_weights(body, arm):
    groups = {group.index: group for group in body.vertex_groups}
    for vertex in body.data.vertices:
        values = sorted(((assignment.group, assignment.weight) for assignment in vertex.groups),
                        key=lambda item: item[1], reverse=True)
        kept = [(index, weight) for index, weight in values[:4] if weight > 1e-7]
        if not kept:
            raise ValueError(f'unweighted body vertex {vertex.index}')
        total = sum(weight for _, weight in kept)
        for index, weight in values:
            group = groups[index]
            if (index, weight) in kept:
                group.add([vertex.index], weight / total, 'REPLACE')
            else:
                group.remove([vertex.index])


def custom_body_weights(body, arm):
    core = [bone for bone in arm.data.bones if bone.name in CORE and bone.name != 'root']
    coords = np.array([v.co[:] for v in body.data.vertices], dtype=np.float64)
    segments = [(np.array(bone.head_local[:]), np.array(bone.tail_local[:]), bone.name) for bone in core]
    distances = np.empty((len(coords), len(segments)), dtype=np.float64)
    for index, (head, tail, name) in enumerate(segments):
        direction = tail - head
        length2 = float(direction @ direction)
        t = np.clip(((coords - head) @ direction) / max(length2, 1e-12), 0, 1)
        nearest = head + t[:, None] * direction
        distance = np.linalg.norm(coords - nearest, axis=1)
        if name.endswith('_L'):
            distance = np.where(coords[:, 0] < -0.01, distance * 2.5, distance)
        elif name.endswith('_R'):
            distance = np.where(coords[:, 0] > 0.01, distance * 2.5, distance)
        distances[:, index] = distance
    scores = 1.0 / np.power(np.maximum(distances, 1e-5), 4)
    choices = np.argsort(scores, axis=1)[:, -4:]
    for vertex_index in range(len(coords)):
        selected = choices[vertex_index]
        values = scores[vertex_index, selected]
        values /= values.sum()
        for segment_index, weight in zip(selected, values):
            name = segments[int(segment_index)][2]
            group = body.vertex_groups.get(name) or body.vertex_groups.new(name=name)
            group.add([vertex_index], float(weight), 'REPLACE')
    body.parent = arm
    modifier = body.modifiers.new('Kiyo armature', 'ARMATURE')
    modifier.object = arm
    modifier.use_deform_preserve_volume = False


def auto_body_weights(body, arm):
    for bone in arm.data.bones:
        bone.use_deform = bone.name in CORE and bone.name != 'root'
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        unweighted = sum(
            1 for vertex in body.data.vertices
            if not any(assignment.weight > 1e-7 for assignment in vertex.groups)
        )
        if unweighted:
            raise RuntimeError(f'bone heat left {unweighted} vertices unweighted')
        method = 'Blender bone-heat automatic weights on T-pose core'
    except RuntimeError:
        method = 'custom nearest-segment weights (bone heat failed)'
        body.parent = None
        for modifier in list(body.modifiers):
            if modifier.type == 'ARMATURE':
                body.modifiers.remove(modifier)
        for group in list(body.vertex_groups):
            body.vertex_groups.remove(group)
        custom_body_weights(body, arm)
    for bone in arm.data.bones:
        bone.use_deform = bone.name in CORE or bone.name in EXTRAS
    prune_body_weights(body, arm)
    return method


def flatten_palette_emission():
    """Keep the authored palette's colour without a constant glTF glow.

    The procedural material links its vertex colour into both Base Color and
    Emission Color. glTF cannot carry the vertex-colour emission link and would
    otherwise export a flat 0.16 emissive factor that washes out the indigo hat
    and the wooden accessories. Base Color already carries the same palette.
    """
    material = bpy.data.materials.get('M_Kiyo_Palette')
    if not material or not material.use_nodes:
        return
    for node in material.node_tree.nodes:
        if node.type != 'BSDF_PRINCIPLED':
            continue
        emission = node.inputs.get('Emission Color') or node.inputs.get('Emission')
        if emission is not None:
            for link in list(emission.links):
                material.node_tree.links.remove(link)
            emission.default_value = (0, 0, 0, 1)
        strength = node.inputs.get('Emission Strength')
        if strength is not None:
            strength.default_value = 0


def scene_bounds(meshes):
    points = []
    for obj in meshes:
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    lo = Vector(tuple(min(point[i] for point in points) for i in range(3)))
    hi = Vector(tuple(max(point[i] for point in points) for i in range(3)))
    return lo, hi


def main():
    args = parse_args()
    started = time.monotonic()
    bpy.ops.wm.open_mainfile(filepath=str(args.baseline.resolve()))
    source = bpy.data.objects.get('Kiyo_Body')
    if source is None or source.type != 'MESH':
        raise ValueError('baseline Kiyo_Body mesh missing')
    accessories = {name: extract_group(source, name) for name in ('hat', 'staff', 'tide_board', 'satchel')}
    for obj in list(bpy.context.scene.objects):
        if obj not in accessories.values():
            bpy.data.objects.remove(obj, do_unlink=True)

    body = import_mesh(args.body, 'Kiyo_Trellis_Body')
    head = import_mesh(args.head, 'Kiyo_Trellis_Head')
    coords, body_lo, body_hi = mesh_bounds(body)
    scale = (BODY_TOP - FLOOR) / float(body_hi[2] - body_lo[2])
    center_x = float((body_lo[0] + body_hi[0]) / 2)
    center_y = float((body_lo[1] + body_hi[1]) / 2)
    transform_mesh(body, scale, (-center_x * scale, -center_y * scale, FLOOR - body_lo[2] * scale))
    _, body_lo, body_hi = mesh_bounds(body)
    coords = np.array([v.co[:] for v in body.data.vertices], dtype=np.float64)
    max_x = float(np.abs(coords[:, 0]).max())
    arms = coords[np.abs(coords[:, 0]) > max_x * .8]
    arm_z = float(np.median(arms[:, 2]))
    arm_y = float(np.median(arms[:, 1]))
    top = coords[coords[:, 2] > body_hi[2] - .008]
    neck_xy = top[:, :2].mean(axis=0)

    hcoords, head_lo, head_hi = mesh_bounds(head)
    head_scale = HEAD_HEIGHT / float(head_hi[2] - head_lo[2])
    bottom = hcoords[hcoords[:, 2] < head_lo[2] + (head_hi[2] - head_lo[2]) * .025]
    head_center_x = float((head_lo[0] + head_hi[0]) / 2)
    head_bottom_y = float(bottom[:, 1].mean())
    transform_mesh(head, head_scale,
                   (-head_center_x * head_scale,
                    float(neck_xy[1]) - head_bottom_y * head_scale,
                    HEAD_BOTTOM - head_lo[2] * head_scale))
    _, head_lo, head_hi = mesh_bounds(head)

    def translate_clamp(obj, dx, dy, dz=0):
        for vertex in obj.data.vertices:
            vertex.co.x += dx
            vertex.co.y += dy
            vertex.co.z += dz
        obj.data.update()

    # The first pass aligns the head's under-cap centroid to the body's neck
    # plug.  The crown and jaw then still sit behind the generated chest in
    # profile, so measure the actual chest front and the face front and move
    # the head forward by the missing clearance.  The forward sign comes from
    # the head's own chin relative to its under-cap, not from a camera axis.
    body_coords, _, body_hi = mesh_bounds(body)
    hcoords, head_lo, head_hi = mesh_bounds(head)
    head_height = float(head_hi[2] - head_lo[2])
    cap = hcoords[hcoords[:, 2] <= head_lo[2] + head_height * .015]
    head_socket_before = cap[:, :2].mean(axis=0)
    chest_band = body_coords[(body_coords[:, 2] > body_hi[2] - .14)
                             & (body_coords[:, 2] < body_hi[2] - .02)
                             & (np.abs(body_coords[:, 0]) < .15)]
    chest_front = float(chest_band[:, 1].min())
    face_band = hcoords[(hcoords[:, 2] > HEAD_BOTTOM + .02)
                        & (hcoords[:, 2] < min(HEAD_BOTTOM + .27, head_hi[2]))
                        & (np.abs(hcoords[:, 0]) < .10)]
    head_face_front = float(face_band[:, 1].min())
    forward = -1.0 if head_face_front < float(head_socket_before[1]) else 1.0
    profile_requested = (chest_front + forward * PROFILE_CLEARANCE) - head_face_front
    profile_shift = max(-.05, min(.05, profile_requested))
    cap_margin = .01
    lower = float(neck_xy[1]) - float(cap[:, 1].max()) + cap_margin
    upper = float(neck_xy[1]) - float(cap[:, 1].min()) - cap_margin
    profile_shift = max(lower, min(upper, profile_shift))
    profile_shift_clamped = abs(profile_shift - profile_requested) > 1e-9
    translate_clamp(head, 0, profile_shift, 0)
    hcoords, head_lo, head_hi = mesh_bounds(head)
    head_socket_after = np.array([head_socket_before[0], head_socket_before[1] + profile_shift])
    head_face_after = head_face_front + profile_shift
    profile_clearance = forward * (head_face_after - chest_front)

    hat = accessories['hat']
    crown_cut = float(head_hi[2] - head_height * .02)
    crown = hcoords[hcoords[:, 2] >= crown_cut]
    crown_xy = (float(crown[:, 0].mean()), float(crown[:, 1].mean()))
    hat_coords, hat_lo, hat_hi = mesh_bounds(hat)
    hat_cx = float((hat_lo[0] + hat_hi[0]) / 2)
    hat_cy = float((hat_lo[1] + hat_hi[1]) / 2)
    translate_clamp(hat, crown_xy[0] - hat_cx, crown_xy[1] - hat_cy, 0)
    hat_coords, _, _ = mesh_bounds(hat)
    radial = np.hypot(hat_coords[:, 0] - crown_xy[0], hat_coords[:, 1] - crown_xy[1])
    inner_candidates = hat_coords[radial < .12]
    inner_z = float(inner_candidates[:, 2].min())
    inner_ring = inner_candidates[np.abs(inner_candidates[:, 2] - inner_z) < .002]
    contacts = []
    for x, y, _ in inner_ring:
        distance2 = (hcoords[:, 0] - x) ** 2 + (hcoords[:, 1] - y) ** 2
        near = hcoords[distance2 < HAT_CONTACT_RADIUS ** 2]
        if len(near):
            contacts.append(float(near[:, 2].max()))
    if contacts:
        contact_z = max(contacts)
        hat_dz_requested = (contact_z - HAT_CONTACT_OVERLAP) - inner_z
        hat_dz = max(-.06, min(.02, hat_dz_requested))
        hat_dz_clamped = abs(hat_dz - hat_dz_requested) > 1e-9
        contact_measured = True
        actual_contact_overlap = contact_z - (inner_z + hat_dz)
        translate_clamp(hat, 0, 0, hat_dz)
    else:
        contact_z = None
        hat_dz = 0.0
        hat_dz_clamped = False
        contact_measured = False
        actual_contact_overlap = None
    hat_coords, hat_lo, hat_hi = mesh_bounds(hat)
    staff = accessories['staff']
    _, staff_lo, staff_hi = mesh_bounds(staff)
    translate_clamp(staff,
                    -max_x - float((staff_lo[0] + staff_hi[0]) / 2),
                    arm_y - float((staff_lo[1] + staff_hi[1]) / 2),
                    0)
    board = accessories['tide_board']
    satchel = accessories['satchel']
    _, board_lo, board_hi = mesh_bounds(board)
    _, satchel_lo, satchel_hi = mesh_bounds(satchel)
    _, staff_lo, staff_hi = mesh_bounds(staff)
    _, hat_lo, hat_hi = mesh_bounds(hat)
    landmarks = dict(
        hip_z=.54, arm_z=arm_z, arm_y=arm_y, max_x=max_x,
        neck_xy=(float(neck_xy[0]), float(neck_xy[1])),
        crown_xy=crown_xy, hat_z=float(HEAD_TOP + hat_dz),
        staff_head=(float((staff_lo[0] + staff_hi[0]) / 2), float((staff_lo[1] + staff_hi[1]) / 2), float(staff_lo[2])),
        staff_tail=(float((staff_lo[0] + staff_hi[0]) / 2), float((staff_lo[1] + staff_hi[1]) / 2), float(staff_hi[2])),
        board_head=(float((board_lo[0] + board_hi[0]) / 2), float((board_lo[1] + board_hi[1]) / 2), float(board_hi[2])),
        board_tail=(float((board_lo[0] + board_hi[0]) / 2), float((board_lo[1] + board_hi[1]) / 2), float(board_lo[2])),
        satchel_head=(float((satchel_lo[0] + satchel_hi[0]) / 2), float((satchel_lo[1] + satchel_hi[1]) / 2), float(satchel_hi[2])),
        satchel_tail=(float((satchel_lo[0] + satchel_hi[0]) / 2), float((satchel_lo[1] + satchel_hi[1]) / 2), float(satchel_lo[2])),
    )
    arm = create_armature(landmarks)
    body_method = auto_body_weights(body, arm)
    rigid_part(head, arm, 'head')
    rigid_part(hat, arm, 'hat')
    rigid_part(staff, arm, 'staff')
    rigid_part(board, arm, 'tide_board')
    rigid_part(satchel, arm, 'satchel')
    for bone in arm.data.bones:
        bone.use_deform = bone.name in CORE or bone.name in EXTRAS

    meshes = [body, head, hat, staff, board, satchel]
    total_triangles = sum(sum(max(0, len(poly.vertices) - 2) for poly in obj.data.polygons) for obj in meshes)
    unweighted = 0
    max_influences = 0
    for obj in meshes:
        for vertex in obj.data.vertices:
            count = sum(1 for assignment in vertex.groups if assignment.weight > 1e-6)
            if count == 0:
                unweighted += 1
            max_influences = max(max_influences, count)
    if unweighted:
        raise ValueError(f'{unweighted} unweighted vertices after assembly')
    if max_influences > 4:
        raise ValueError(f'{max_influences} influences on a vertex')
    lo, hi = scene_bounds(meshes)
    if abs(lo.z - FLOOR) > .002:
        raise ValueError(f'feet are off the shared floor: {lo.z:.5f}')
    if not 1.50 <= hi.z <= 1.60:
        raise ValueError(f'assembled height {hi.z:.4f} is outside the design')
    if set(bone.name for bone in arm.data.bones) != set(CORE + EXTRAS):
        raise ValueError('armature contract differs from the 23 core plus seven accessory bones')

    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    flatten_palette_emission()
    blend = args.output / 'Kiyo-TRELLIS.blend'
    model = args.output / 'Kiyo-TRELLIS.glb'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    bpy.ops.export_scene.gltf(
        filepath=str(model), export_format='GLB', use_selection=True,
        export_yup=True, export_apply=False, export_animations=False,
        export_texcoords=True, export_normals=True, export_materials='EXPORT')
    report = dict(
        method='Processed TRELLIS head and body, uniform fit, measured neck/profile placement, one shared armature',
        input_head_sha256=digest(args.head), input_body_sha256=digest(args.body),
        baseline_sha256=digest(args.baseline), output_blend_sha256=digest(blend), output_glb_sha256=digest(model),
        body_uniform_scale=scale, head_uniform_scale=head_scale,
        body_top_m=BODY_TOP, head_bottom_m=HEAD_BOTTOM, head_top_m=HEAD_TOP,
        arm_axis_m=arm_z, head_neck_overlap_m=BODY_TOP - HEAD_BOTTOM,
        bounds_min=list(lo), bounds_max=list(hi), height_m=hi.z - lo.z,
        head_fit=dict(
            body_neck_plug_xy=[float(neck_xy[0]), float(neck_xy[1])],
            head_under_cap_xy_before=[float(head_socket_before[0]), float(head_socket_before[1])],
            head_under_cap_xy_after=[float(head_socket_after[0]), float(head_socket_after[1])],
            body_chest_front_y=chest_front,
            head_face_front_y_before=head_face_front,
            head_face_front_y_after=head_face_after,
            forward_axis='-Y' if forward < 0 else '+Y',
            profile_shift_requested_m=profile_requested,
            profile_shift_m=profile_shift,
            profile_shift_clamped=profile_shift_clamped,
            profile_clearance_target_m=PROFILE_CLEARANCE,
            profile_clearance_m=profile_clearance,
            rig_pivot_xy=[float(neck_xy[0]), float(neck_xy[1])],
            cap_y_range=[float(cap[:, 1].min()), float(cap[:, 1].max())],
        ),
        hat_fit=dict(
            crown_xy=[float(crown_xy[0]), float(crown_xy[1])],
            inner_brim_z_before=inner_z,
            contact_z=contact_z,
            contact_measured=contact_measured,
            vertical_shift_m=hat_dz,
            vertical_shift_clamped=hat_dz_clamped,
            contact_overlap_target_m=HAT_CONTACT_OVERLAP,
            contact_overlap_m=actual_contact_overlap,
            hat_bbox_after=[list(hat_lo), list(hat_hi)],
        ),
        triangles=total_triangles, meshes={obj.name: len(obj.data.vertices) for obj in meshes},
        materials=sorted({material.name for obj in meshes for material in obj.data.materials if material}),
        bones=len(arm.data.bones), core_bones=len(CORE), accessory_bones=EXTRAS,
        body_weighting=body_method, unweighted_vertices=unweighted, max_influences=max_influences,
        exact_head_geometry='processed head triangles retained; uniform scale plus rigid neck/profile translations, no rotation or sculpting',
        exact_body_geometry='processed body triangles retained; only uniform scale and rigid translation',
        palette_emission='vertex-colour emission link flattened to black for glTF; Base Color retains the palette',
        limitations='Automatic body weights, a T-pose accessory fit and a measured hat contact require animation inspection; no manual sculpting.',
        seconds=time.monotonic() - started,
    )
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
