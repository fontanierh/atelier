"""Render a production-prepared character seated on the kart, posed with the driving stance's targets.

    blender -b --threads 3 --python-exit-code 1 --python preview.py -- cairo /abs/out

The kart's three meshes come from build/yorimichi/kart/assets (world.kart). The character is opened through
characters/pipeline/rig.py prepare(), the same outfit, scale, floor, facing and bone contract the game imports,
then moved so its pelvis sits on the seat and posed with two-bone IK on the legs and arms. Diagnostic render
only; nothing here is part of the game's build graph.
"""
import sys as _sys; from pathlib import Path as _Path; _ASSET = _Path(__file__).resolve().parents[2]; _sys.path.insert(0, str(_ASSET.parent / 'world')); _sys.path.insert(0, str(_ASSET / 'characters' / 'pipeline')); import yori  # noqa: E402
import rig  # noqa: E402
import export as character_export
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import cockpit
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from atelier.blender import renderdev

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
CHARACTER = ARGS[0] if ARGS else 'cairo'
OUT = Path(ARGS[1]) if len(ARGS) > 1 else Path('/tmp/kart-preview')
OUT.mkdir(parents=True, exist_ok=True)

KART = yori.OUT / 'kart/assets'
BONES = {
    'pelvis': 'mixamorig:Hips', 'spine': 'mixamorig:Spine',
    'thigh_L': 'mixamorig:LeftUpLeg', 'shin_L': 'mixamorig:LeftLeg', 'foot_L': 'mixamorig:LeftFoot',
    'thigh_R': 'mixamorig:RightUpLeg', 'shin_R': 'mixamorig:RightLeg', 'foot_R': 'mixamorig:RightFoot',
    'upperarm_L': 'mixamorig:LeftArm', 'forearm_L': 'mixamorig:LeftForeArm', 'hand_L': 'mixamorig:LeftHand',
    'upperarm_R': 'mixamorig:RightArm', 'forearm_R': 'mixamorig:RightForeArm', 'hand_R': 'mixamorig:RightHand',
    'fingers_L': ('mixamorig:LeftHandIndex', 'mixamorig:LeftHandMiddle', 'mixamorig:LeftHandRing',
                  'mixamorig:LeftHandPinky', 'mixamorig:LeftHandThumb'),
    'fingers_R': ('mixamorig:RightHandIndex', 'mixamorig:RightHandMiddle', 'mixamorig:RightHandRing',
                  'mixamorig:RightHandPinky', 'mixamorig:RightHandThumb'),
}


def bone(arm, name):
    for candidate in (name, BONES.get(name), f'mixamorig:{name}'):
        if candidate and candidate in arm.pose.bones:
            return arm.pose.bones[candidate]
    return None


def leg_length(arm, root):
    thigh = arm.data.bones.get('thigh_L') or arm.data.bones.get(BONES['thigh_L'])
    shin = arm.data.bones.get('shin_L') or arm.data.bones.get(BONES['shin_L'])
    if not (thigh and shin):
        raise ValueError("Kart fitting requires both thigh_L and shin_L bones")
    return ((thigh.tail_local - thigh.head_local).length + (shin.tail_local - shin.head_local).length) * root.scale.x

LAYOUT = cockpit.load()
SCALE = 1.0
WHEEL_HUB = Vector(LAYOUT['steering'])
RIM = LAYOUT['steering_radius']
KNEE = [Vector(LAYOUT['knee']), Vector((LAYOUT['knee'][0], -LAYOUT['knee'][1], LAYOUT['knee'][2]))]
ELBOW = [Vector(LAYOUT['elbow']), Vector((LAYOUT['elbow'][0], -LAYOUT['elbow'][1], LAYOUT['elbow'][2]))]


def fresh(scene):
    for ob in [o for o in scene.objects if o.type in ('LIGHT', 'CAMERA')]:
        bpy.data.objects.remove(ob, do_unlink=True)
    scene.render.engine = 'CYCLES'
    renderdev.enable_metal()
    scene.cycles.samples = 32
    scene.render.resolution_x = scene.render.resolution_y = 960
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new('KartWorld')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (.55, .60, .66, 1)
    scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = .7
    return scene


def kart_material():
    mat = bpy.data.materials.new('KartVertexColour')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    colour = nodes.new('ShaderNodeVertexColor')
    colour.layer_name = 'Color'
    mat.node_tree.links.new(colour.outputs['Color'], nodes['Principled BSDF'].inputs['Base Color'])
    nodes['Principled BSDF'].inputs['Roughness'].default_value = .82
    return mat


def import_kart():
    mat = kart_material()
    pieces = {}
    for name, at, spin_y in (('SM_Kart_Body', (0, 0, 0), 0.0), ('SM_Kart_Seat', (0, 0, 0), 0.0), ('SM_Kart_Wheel', None, 0.0),
                             ('SM_Kart_SteeringWheel', WHEEL_HUB, -22.0)):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(filepath=str(KART / f'{name}.fbx'))
        added = [o for o in bpy.data.objects if o not in before]
        keep = []
        for ob in list(added):
            if ob.name.startswith('UCX'):
                bpy.data.objects.remove(ob, do_unlink=True)
            else:
                keep.append(ob)
        imported = [o for o in keep if o.type == 'MESH']
        for ob in imported:
            # Match M_Kart's explicit sRGB-to-linear decode instead of previewing a brighter linear palette.
            for layer in ob.data.color_attributes:
                for color in layer.data:
                    color.color_srgb = color.color[:]
            ob.data.materials.clear(); ob.data.materials.append(mat)
        pieces[name] = imported
    # Runtime builds the telescopic column separately so each saved fit can change height/tilt.
    base, hub = Vector(LAYOUT['steering_column_base']), Vector(LAYOUT['steering'])
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=.019, depth=(hub-base).length, location=(base+hub)*.5)
    column = bpy.context.object; column.name = 'PreviewColumn'
    column.rotation_euler = (hub-base).to_track_quat('Z', 'Y').to_euler()
    color = column.data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    for item in color.data: item.color_srgb = (.57, .55, .48, 1)
    column.data.materials.append(mat)
    placed = [column]
    for ob in pieces['SM_Kart_Body'] + pieces['SM_Kart_Seat']:
        placed.append(ob)
    wheels = pieces['SM_Kart_Wheel']
    for index, at in enumerate(LAYOUT['wheel_positions']):
        size = 1.0 if index < 2 else 1.08
        ob = wheels[0].copy(); ob.data = wheels[0].data.copy()
        bpy.context.scene.collection.objects.link(ob)
        ob.location = at
        ob.scale = (size, size, size)
        placed.append(ob)
    for source in pieces['SM_Kart_Seat']:
        source.location = LAYOUT['seat']
    for source in pieces['SM_Kart_SteeringWheel']:
        source.location = WHEEL_HUB
        source.rotation_euler = (0, math.radians(LAYOUT['steering_tilt_degrees']), 0)
        placed.append(source)
    for ob in placed:
        ob.location *= SCALE
        ob.scale *= SCALE
    for ob in wheels:
        ob.hide_render = True
    return placed


def character_objects(arm):
    root = arm
    while root.parent:
        root = root.parent
    family = {root}
    changed = True
    while changed:
        changed = False
        for ob in bpy.context.scene.objects:
            if ob.parent in family and ob not in family:
                family.add(ob); changed = True
    return [o for o in family if o.type in ('MESH', 'ARMATURE')]


def evaluated_tree(objects, exclude_arms=False):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    verts, faces = [], []
    for obj in objects:
        ev = obj.evaluated_get(depsgraph)
        mesh = ev.to_mesh()
        offset = len(verts)
        verts.extend(ev.matrix_world @ v.co for v in mesh.vertices)
        allowed = set(range(len(mesh.vertices)))
        if exclude_arms:
            # Hands intentionally touch the rim. Torso, hips and clothed legs must clear it.
            arms = {g.index for g in obj.vertex_groups if any(n in g.name.lower() for n in
                    ('hand', 'finger', 'thumb', 'forearm', 'upperarm', 'leftarm', 'rightarm'))}
            allowed = {v.index for v in mesh.vertices if sum(g.weight for g in v.groups if g.group in arms) < .2}
        faces.extend(tuple(offset + i for i in p.vertices) for p in mesh.polygons if all(i in allowed for i in p.vertices))
        ev.to_mesh_clear()
    return (BVHTree.FromPolygons(verts, faces), verts) if faces else (None, verts)


def clearance_report(arm):
    body = [o for o in character_objects(arm) if o.type == 'MESH' and not o.hide_render]
    kart = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o.name.startswith('SM_Kart_')]
    wheel = [o for o in kart if o.name.startswith('SM_Kart_SteeringWheel')]
    shell = [o for o in kart if o.name.startswith(('SM_Kart_Body', 'PreviewColumn'))]
    bt, bverts = evaluated_tree(body, exclude_arms=True)
    wt, _ = evaluated_tree(wheel)
    st, _ = evaluated_tree(shell)
    if bt is None or wt is None:
        return
    wheel_hits = bt.overlap(wt)
    shell_hits = bt.overlap(st) if st else []
    nearest = min((wt.find_nearest(v)[3] for v in bverts if v.length > 0), default=0.0)
    for ob in body:
        part, _ = evaluated_tree([ob], exclude_arms=True)
        if part and st:
            print('SHELL PART', ob.name, len(part.overlap(st)), flush=True)
    print('CLEARANCE torso_legs_wheel_overlap' , len(wheel_hits), 'shell_overlap', len(shell_hits),
          'nearest_wheel', round(nearest, 3), flush=True)
    import json
    report = {'character': CHARACTER, 'kart_scale': SCALE, 'torso_legs_wheel_overlap': len(wheel_hits),
              'shell_overlap': len(shell_hits), 'nearest_wheel_vertex_m': nearest}
    (OUT / f'{CHARACTER}-fit.json').write_text(json.dumps(report, indent=2) + '\n')


def grip_report(arm):
    """Measure evaluated skin against the same torus the generated steering rim uses."""
    import json
    hub = Vector(LAYOUT['steering']) * SCALE
    forward = Vector(cockpit.grip(0)[1])
    radius, tube = LAYOUT['steering_radius'] * SCALE, LAYOUT['steering_tube_radius'] * SCALE
    depsgraph = bpy.context.evaluated_depsgraph_get()
    hands = {}
    for suffix in ('L', 'R'):
        distances = {name: [] for chain in finger_chains(arm, suffix) for name in chain}
        distances[f'hand_{suffix}'] = []
        for ob in character_objects(arm):
            if ob.type != 'MESH' or ob.hide_render:
                continue
            groups = {g.index: g.name for g in ob.vertex_groups if g.name in distances}
            if not groups:
                continue
            evaluated = ob.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh()
            for v in mesh.vertices:
                offset = evaluated.matrix_world @ v.co - hub
                axial = offset.dot(forward)
                radial = (offset - forward * axial).length
                sdf = math.hypot(radial - radius, axial) - tube
                for weight in v.groups:
                    if weight.group in groups and weight.weight > .25:
                        distances[groups[weight.group]].append(sdf)
            evaluated.to_mesh_clear()
        measurements = {name: {'vertices': len(ds), 'penetration_mm': round(max(0, -min(ds)) * 1000, 2),
                               'nearest_mm': round(min(abs(d) for d in ds) * 1000, 2)}
                        for name, ds in distances.items() if ds}
        firsts = [arm.pose.bones[c[0]] for c in finger_chains(arm, suffix)[:4]]
        hand, fore = bone(arm, f'hand_{suffix}'), bone(arm, f'forearm_{suffix}')
        knuckles = sum((pb.head for pb in firsts), Vector()) / 4
        bend = math.degrees((knuckles - hand.head).angle(hand.head - fore.head))
        hands[suffix] = {'wrist_bend_degrees': round(bend, 2), 'skin': measurements}
        print('GRIP SKIN', CHARACTER, suffix, json.dumps(hands[suffix]), flush=True)
    (OUT / f'{CHARACTER}-hands.json').write_text(json.dumps(hands, indent=2) + '\n')


def finger_chains(arm, side):
    """The three bones of each finger: production contract names or the raw Mixamo fallback."""
    contract = [[f'finger_{i}_{side}', f'finger_tip_{i}_{side}', f'finger_end_{i}_{side}'] for i in range(4)]
    contract.append([f'thumb_{side}', f'thumb_tip_{side}', f'thumb_end_{side}'])
    if all(arm.pose.bones.get(name) for chain in contract for name in chain):
        return contract
    return [[f'{prefix}{part}' for part in (1, 2, 3)] for prefix in BONES[f'fingers_{side}']]


def pose(arm):
    arm.data.pose_position = 'POSE'
    for ob in character_objects(arm):
        if ob.animation_data:
            ob.animation_data_clear()   # a stored idle action would overwrite the stance at render time
        for modifier in ob.modifiers:
            if modifier.type == 'CLOTH':
                modifier.show_viewport = modifier.show_render = False   # the game mesh is skinned, not simulated
    root = arm
    while root.parent:
        root = root.parent
    pedal = [Vector(LAYOUT['foot']) * SCALE, Vector((LAYOUT['foot'][0], -LAYOUT['foot'][1], LAYOUT['foot'][2])) * SCALE]
    if 'diag' in ARGS:
        print('FIT scale', round(SCALE, 3), 'leg', round(leg_length(arm, root), 3), flush=True)
    seat = Vector(LAYOUT['pelvis']) * SCALE
    pelvis = bone(arm, 'pelvis')
    if pelvis:
        root.location += seat - (arm.matrix_world @ pelvis.head)
        bpy.context.view_layer.update()

    rest_hip = {}
    for suffix in ('L', 'R'):
        thigh, pelvis_bone = bone(arm, f'thigh_{suffix}'), bone(arm, 'pelvis')
        shin = bone(arm, f'shin_{suffix}')
        if thigh and shin and pelvis_bone:
            a = (shin.head - thigh.head).normalized()
            b = (pelvis_bone.tail - pelvis_bone.head).normalized()
            rest_hip[suffix] = math.degrees(a.angle(b))

    def aim_bone(pb, head, want):
        """Turn a bone's +Y length axis toward want, preserving its roll and head position."""
        current = (pb.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
        turn = current.rotation_difference(want.normalized())
        placed = turn.to_matrix().to_4x4() @ pb.matrix
        placed.translation = head
        pb.matrix = placed
        bpy.context.view_layer.update()

    def solve_two_bone(upper, lower, target, pole, extension=0.0):
        """The runtime's non-stretch two-bone solve: bend toward the pole, keep both lengths."""
        hip = upper.head.copy()
        knee = lower.head.copy()
        ankle = lower.tail.copy()
        l1 = (knee - hip).length
        l2 = (ankle - knee).length + extension
        delta = target - hip
        distance = delta.length
        if distance < 1e-5:
            return hip
        direction = delta / distance
        d = min(max(distance, abs(l1 - l2) + 1e-4), l1 + l2 - 1e-4)
        side = pole - hip
        side = side - direction * side.dot(direction)
        if side.length < 1e-5:
            side = direction.cross(Vector((0, 0, 1)))
        side.normalize()
        along = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
        height = math.sqrt(max(l1 * l1 - along * along, 0.0))
        solved_knee = hip + direction * along + side * height
        solved_ankle = hip + direction * d
        aim_bone(upper, hip, solved_knee - hip)
        aim_bone(lower, lower.head.copy(), solved_ankle - lower.head)
        return solved_ankle

    def wrist_twist(fore, hand):
        rest_local = fore.bone.matrix_local.inverted() @ hand.bone.matrix_local
        pose_local = fore.matrix.inverted() @ hand.matrix
        y_axis = Vector((0, 1, 0))
        rest_x = rest_local.to_3x3() @ Vector((1, 0, 0))
        pose_x = pose_local.to_3x3() @ Vector((1, 0, 0))
        rest_x = (rest_x - y_axis * rest_x.dot(y_axis)).normalized()
        pose_x = (pose_x - y_axis * pose_x.dot(y_axis)).normalized()
        return math.degrees(math.atan2(y_axis.dot(rest_x.cross(pose_x)), rest_x.dot(pose_x)))
        if 'diag' in ARGS:
            print('PELVIS after', tuple(round(v, 3) for v in (arm.matrix_world @ pelvis.head)), 'seat', tuple(seat),
                  'root', root.name, 'parent', root.parent.name if root.parent else None,
                  'loc', tuple(round(v, 3) for v in root.location), 'scale', tuple(round(v, 4) for v in root.scale))
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    if 'diag' in ARGS:
        for name in ('hand_L', 'hand_R'):
            pb = bone(arm, name)
            if pb:
                at = arm.matrix_world @ pb.head
                print('REST', name, tuple(round(v, 3) for v in at))
    bpy.ops.object.mode_set(mode='POSE')
    for posed in arm.pose.bones:
        posed.rotation_mode = 'XYZ'
        posed.matrix_basis = Matrix.Identity(4)   # pose from the rest skeleton, not a stored idle
    bpy.context.view_layer.update()
    pelvis = bone(arm, 'pelvis')
    if pelvis:
        root.location += seat - (arm.matrix_world @ pelvis.head)
        bpy.context.view_layer.update()
    # The stance reclines the whole upper body around the pelvis. Rotating only the spine's local
    # X can yaw an imported rig whose bone axes differ.
    pelvis = bone(arm, 'pelvis')
    spine = bone(arm, 'spine')
    if pelvis and spine:
        bpy.context.view_layer.update()
        pivot = pelvis.head.copy()
        R = Matrix.Rotation(math.radians(-LAYOUT['recline_degrees']), 4, 'Y')
        spine.matrix = (Matrix.Translation(pivot) @ R @ Matrix.Translation(-pivot)) @ spine.matrix
        bpy.context.view_layer.update()
    neck = bone(arm, 'neck') or arm.pose.bones.get('mixamorig:Neck')
    if neck:
        pivot = neck.head.copy()
        R = Matrix.Rotation(math.radians(LAYOUT['recline_degrees'] * .6), 4, 'Y')   # 60% counter-rotation over the 18 degree seat
        neck.matrix = (Matrix.Translation(pivot) @ R @ Matrix.Translation(-pivot)) @ neck.matrix
        bpy.context.view_layer.update()

    mw = arm.matrix_world.copy()
    mw_inv = mw.inverted()
    # Feet: solve the hips/knee/ankle chain toward the pedal, then plant the toe down the pedal
    # instead of inheriting each source rig's resting ankle roll.
    plant = (mw.to_3x3().inverted() @ Vector(LAYOUT['foot_forward'])).normalized()
    for side, suffix in ((0, 'L'), (1, 'R')):
        thigh = bone(arm, f'thigh_{suffix}')
        shin = bone(arm, f'shin_{suffix}')
        foot = bone(arm, f'foot_{suffix}')
        if thigh and shin:
            solve_two_bone(thigh, shin, mw_inv @ pedal[side], mw_inv @ (KNEE[side] * SCALE))
        if foot:
            toe = bone(arm, f'toe_{suffix}')
            if toe:
                old = (toe.head - foot.head).normalized()
                rotation = old.rotation_difference(plant)
                matrix = rotation.to_matrix().to_4x4() @ foot.matrix
                matrix.translation = foot.head.copy()
                foot.matrix = matrix
                bpy.context.view_layer.update()

    # Seed pose for the manual grip editor, in Blender's +Y-left mesh frame. This is
    # provisional: the authored wheel-local profiles, not these guessed curls, drive the final runtime hands.
    # The knuckles, not the hand bone's imported axis, define forward and span; the wrist follows
    # from the rotated knuckle offset.
    inverse = mw.to_3x3().inverted()
    grips = {}
    for side, suffix in ((0, 'L'), (1, 'R')):
        steering = next((float(a.split('=', 1)[1]) for a in ARGS if a.startswith('steer=')), 0.0)
        contact, fwd, up, axis = cockpit.grip(side, steering)
        rim, forward, radial, tangent = Vector(contact) * SCALE, Vector(fwd), Vector(up), Vector(axis)
        hand = bone(arm, f'hand_{suffix}')
        chains = finger_chains(arm, suffix)
        firsts = [arm.pose.bones.get(chain[0]) for chain in chains[:4]]
        if not hand or any(pb is None for pb in firsts):
            continue
        bpy.context.view_layer.update()
        old = mw @ hand.matrix
        knuckles = sum((mw @ pb.head for pb in firsts), Vector()) / 4.0
        old_fwd = (knuckles - old.translation).normalized()
        old_span = ((mw @ firsts[3].head) - (mw @ firsts[0].head)).normalized()   # pinky toward index
        desired = rim + forward * .012 + radial * .028
        upper, fore = bone(arm, f'upperarm_{suffix}'), bone(arm, f'forearm_{suffix}')
        hand_length = (knuckles - old.translation).length
        end = solve_two_bone(upper, fore, mw_inv @ desired, mw_inv @ (ELBOW[side] * SCALE),
                             extension=hand_length / mw.to_scale().x)
        desired = mw @ end
        hand_forward = (mw.to_3x3() @ (end - fore.head)).normalized()
        hand_forward = (hand_forward - tangent * hand_forward.dot(tangent)).normalized()
        first = old_fwd.rotation_difference(hand_forward)
        span = first @ old_span
        span = (span - hand_forward * span.dot(hand_forward)).normalized()
        # Index is above pinky on either grip; thumb stays above the rim.
        want = (-tangent + hand_forward * tangent.dot(hand_forward)).normalized()
        align = span.rotation_difference(want) @ first
        hand_rot = align @ old.to_quaternion()
        wrist = desired - align @ (knuckles - old.translation)
        solve_two_bone(upper, fore, mw_inv @ wrist, mw_inv @ (ELBOW[side] * SCALE))
        if 'diag' in ARGS:
            print('GRIP', suffix, 'hand', tuple(round(v, 3) for v in old.translation),
                  'knuckles', tuple(round(v, 3) for v in knuckles),
                  'desired', tuple(round(v, 3) for v in desired),
                  'wrist', tuple(round(v, 3) for v in wrist),
                  'offset', round((knuckles - old.translation).length, 3),
                  'span', tuple(round(v, 2) for v in old_span),
                  'want', tuple(round(v, 2) for v in want))
        grips[side] = (suffix, hand, hand_rot, wrist, rim, forward, radial)

    bpy.context.view_layer.update()
    # Curl around the rim like the grip node: each phalanx's own bone axis is aimed at the wrap
    # directions, so rigs with mirrored hands curl the same way.
    def aim(pb, want):
        head = pb.matrix.translation.copy()
        current = ((pb.children[0].head - pb.head) if pb.children else (pb.tail - pb.head)).normalized()
        turn = current.rotation_difference(want.normalized())
        placed = turn.to_matrix().to_4x4() @ pb.matrix
        placed.translation = head
        pb.matrix = placed
        bpy.context.view_layer.update()

    for side, (suffix, hand, hand_rot, wrist, rim, forward_w, radial_w) in grips.items():
        local_rot = mw.to_quaternion().inverted() @ hand_rot
        hand.matrix = Matrix.Translation(mw_inv @ wrist) @ local_rot.to_matrix().to_4x4()
        bpy.context.view_layer.update()
        fore = bone(arm, f'forearm_{suffix}')
        if fore:
            twist = wrist_twist(fore, hand)
            if abs(twist) > 5.0:
                axis = (fore.matrix.to_3x3() @ Vector((0, 1, 0))).normalized()
                pivot = fore.head.copy()
                M = Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(twist * .6), 4, axis) @ Matrix.Translation(-pivot)
                fore.matrix = M @ fore.matrix
                bpy.context.view_layer.update()
                hand.matrix = Matrix.Translation(mw_inv @ wrist) @ local_rot.to_matrix().to_4x4()
                bpy.context.view_layer.update()
        hub = Vector(LAYOUT['steering']) * SCALE
        for digit, chain in enumerate(finger_chains(arm, suffix)):
            base = mw @ arm.pose.bones[chain[0]].head
            flat = base - hub - forward_w * (base - hub).dot(forward_w)
            radial = flat.normalized()
            center = hub + radial * LAYOUT['steering_radius'] * SCALE
            # Skeleton segments are tangent to an inflated rim; their skin closes onto the rubber.
            pad = .0055 * SCALE
            radius = LAYOUT['steering_tube_radius'] * SCALE + pad * (1.3 if digit == 4 else 1.0)
            for name in chain:
                pb = arm.pose.bones.get(name)
                if not pb:
                    continue
                head = mw @ pb.head
                offset = head - center
                x, y = offset.dot(radial), offset.dot(forward_w)
                dx, dy = cockpit.wrap_direction((x, y), radius, opposed=digit == 4)
                aim(pb, inverse @ (radial * dx + forward_w * dy).normalized())

    # Nox's sparse seat targets are driven by hip flexion. The game uses bilinear interpolation
    # between the -25/0/35/70/105 degree targets; apply the same weights for this diagnostic body.
    body = next((o for o in character_objects(arm) if o.type == 'MESH' and o.data.shape_keys and
                 any(k.name.startswith('NoxSeat_') for k in o.data.shape_keys.key_blocks)), None)
    if body and rest_hip:
        flex = {}
        for suffix in ('L', 'R'):
            thigh, shin, pelvis_bone = bone(arm, f'thigh_{suffix}'), bone(arm, f'shin_{suffix}'), bone(arm, 'pelvis')
            if thigh and shin and pelvis_bone:
                a = (shin.head - thigh.head).normalized()
                b = (pelvis_bone.tail - pelvis_bone.head).normalized()
                flex[suffix] = min(105.0, max(-25.0, rest_hip[suffix] - math.degrees(a.angle(b))))
        grid = (-25, 0, 35, 70, 105)
        def ramp(value):
            if value <= grid[0]:
                return [(grid[0], 1.0)]
            if value >= grid[-1]:
                return [(grid[-1], 1.0)]
            for i in range(len(grid) - 1):
                if grid[i] <= value <= grid[i + 1]:
                    t = (value - grid[i]) / (grid[i + 1] - grid[i])
                    return [(grid[i], 1.0 - t), (grid[i + 1], t)]
            return [(0, 1.0)]
        name = lambda v: ('m' + str(-v)) if v < 0 else str(v)
        keys = body.data.shape_keys.key_blocks
        for key in keys:
            if key.name.startswith('NoxSeat_'):
                key.value = 0.0
        for left, wl in ramp(flex.get('L', 0.0)):
            for right, wr in ramp(flex.get('R', 0.0)):
                key = keys.get(f'NoxSeat_L{name(left)}_R{name(right)}')
                if key:
                    key.value = wl * wr
        bpy.context.view_layer.update()
        if 'diag' in ARGS:
            print('NOX SEAT flex', {k: round(v, 1) for k, v in flex.items()})
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.view_layer.update()
    for label, bone_name, goal_obj in (('footL', 'foot_L', 'foot_L'), ('footR', 'foot_R', 'foot_R'),
                                       ('handL', 'hand_L', 'hand_L'), ('handR', 'hand_R', 'hand_R')):
        pb = bone(arm, bone_name)
        target = bpy.data.objects.get(goal_obj)
        if pb and target:
            at = arm.matrix_world @ pb.tail
            print('POSE', label, 'bone', tuple(round(v, 3) for v in at),
                  'target', tuple(round(v, 3) for v in target.location),
                  'miss', round((at - target.location).length, 3))
    for suffix in ('L', 'R'):
        fore = bone(arm, f'forearm_{suffix}')
        target = bpy.data.objects.get(f'hand_{suffix}')
        if fore and target:
            at = arm.matrix_world @ fore.tail
            print('WRIST', suffix, tuple(round(v, 3) for v in at), 'target',
                  tuple(round(v, 3) for v in target.location), 'miss', round((at - target.location).length, 3))
    if 'diag' in ARGS:
        head = bone(arm, 'head') or arm.pose.bones.get('mixamorig:Head')
        if head:
            axes = head.matrix.to_3x3()
            print('HEAD AXES', 'x', tuple(round(v, 2) for v in axes.col[0]),
                  'y', tuple(round(v, 2) for v in axes.col[1]),
                  'z', tuple(round(v, 2) for v in axes.col[2]))
        for suffix in ('L', 'R'):
            for chain in finger_chains(arm, suffix)[:4]:
                first = arm.pose.bones.get(chain[0])
                last = arm.pose.bones.get(chain[-1])
                if first and last:
                    a = arm.matrix_world @ first.head
                    b = arm.matrix_world @ first.tail
                    c = arm.matrix_world @ last.tail
                    print('FINGER', suffix, chain[0],
                          'base', tuple(round(v, 3) for v in a),
                          'firstdir', tuple(round(v, 2) for v in (b - a).normalized()),
                          'tip', tuple(round(v, 3) for v in c))
        for suffix in ('L', 'R'):
            knee = bone(arm, f'shin_{suffix}')
            foot = bone(arm, f'foot_{suffix}')
            if knee and foot:
                sole = (arm.matrix_world.to_3x3() @ (foot.tail - foot.head)).normalized()
                thigh = bone(arm, f'thigh_{suffix}')
                bend = 0.0
                flex = 0.0
                if thigh:
                    a = (knee.head - thigh.head).normalized()
                    b = (foot.head - knee.head).normalized()
                    bend = math.degrees(a.angle(b))
                    spine = bone(arm, 'spine')
                    if spine:
                        flex = 180.0 - math.degrees(a.angle((spine.tail - spine.head).normalized()))
                print('LEG', suffix, 'hip', tuple(round(v, 3) for v in (arm.matrix_world @ (thigh.head if thigh else knee.head))),
                      'knee', tuple(round(v, 3) for v in (arm.matrix_world @ knee.head)),
                      'ankle', tuple(round(v, 3) for v in (arm.matrix_world @ foot.head)),
                      'flex', round(flex, 1), 'bend', round(bend, 1), 'sole', tuple(round(v, 2) for v in sole))
        for side, (suffix, hand, hand_rot, wrist, rim, forward_w, radial_w) in grips.items():
            fore = bone(arm, f'forearm_{suffix}')
            if not (hand and fore):
                continue
            chains = finger_chains(arm, suffix)
            firsts = [arm.pose.bones.get(chain[0]) for chain in chains[:4]]
            knuckles = sum((arm.matrix_world @ pb.head for pb in firsts), Vector()) / 4.0
            hand_head = arm.matrix_world @ hand.head
            twist = wrist_twist(fore, hand)
            print('HAND', suffix, 'forearm_tail', tuple(round(v, 3) for v in (arm.matrix_world @ fore.tail)),
                  'hand_head', tuple(round(v, 3) for v in hand_head),
                  'continuity', round(((arm.matrix_world @ fore.tail) - hand_head).length, 4),
                  'twist', round(twist, 1),
                  'knuckles', tuple(round(v, 3) for v in knuckles),
                  'rim', tuple(round(v, 3) for v in rim),
                  'knuckle_rim', round((knuckles - rim).length, 3))
        clearance_report(arm)
        grip_report(arm)


def light(scene):
    sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
    scene.collection.objects.link(sun)
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(35))
    fill = bpy.data.objects.new('Fill', bpy.data.lights.new('Fill', 'AREA'))
    scene.collection.objects.link(fill)
    fill.data.energy = 300
    fill.data.size = 4
    fill.location = (-2.5, -2.5, 3)
    fill.rotation_euler = (math.radians(55), 0, math.radians(-135))


def camera(scene, at, look):
    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    scene.collection.objects.link(cam)
    cam.location = at
    direction = Vector(look) - cam.location
    cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = 55
    scene.camera = cam
    return cam


def render(scene, path, at, look):
    remove = [o for o in scene.objects if o.type == 'CAMERA']
    for o in remove:
        bpy.data.objects.remove(o, do_unlink=True)
    cam = camera(scene, Vector(at), Vector(look))
    if 'grip-' in str(path):
        cam.data.lens = 85
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print('RENDERED', path)


def main():
    character = rig.load(CHARACTER)
    prepared = character.prepare()
    character_export.rest(prepared)
    hooks = character_export.hooks(character)
    if hooks:
        hooks.body(prepared, {})
    scene = fresh(prepared.scene)
    arm = prepared.arm
    root = arm
    while root.parent:
        root = root.parent
    global SCALE
    SCALE = cockpit.fit(leg_length(arm, root))
    import_kart()
    # prepare() keeps glTF meshes unparented so their world transforms survive the import; re-parent them
    # without moving them, so seating the armature carries the whole body.
    for ob in prepared.meshes:
        if ob.parent is None:
            world = ob.matrix_world.copy()
            ob.parent = arm
            ob.matrix_world = world
    for ob in character_objects(arm):
        if any(word in ob.name for word in ('Bokken', 'Sword', 'sword')):
            ob.hide_render = True
    print('CHARACTER', CHARACTER, 'ARMATURE', arm.name, 'BONES', len(arm.data.bones))
    if 'diag' in ARGS:
        print('BONE NAMES', ', '.join(b.name for b in arm.data.bones))
    for ob in character_objects(arm):
        print('  OBJECT', ob.name, ob.type, 'hide', ob.hide_render, 'dims', tuple(round(v, 3) for v in ob.dimensions))
        if ob.type == 'MESH' and 'diag' in ARGS:
            print('    MODIFIERS', [(m.type, getattr(m, 'object', None).name if getattr(m, 'object', None) else None) for m in ob.modifiers],
                  'groups', len(ob.vertex_groups), 'render', [(m.show_render, m.show_viewport) for m in ob.modifiers],
                  'parent', ob.parent.name if ob.parent else None, ob.parent_type)
    pose(arm)
    if 'diag' in ARGS and 'render' not in ARGS:
        print('DIAGNOSTIC ONLY')
        return
    light(scene)
    views = (
        ('front', (2.6, -2.4, 1.55), (-0.15, 0, 0.5)),
        ('rear', (-2.5, 2.2, 1.55), (-0.12, 0, 0.5)),
        ('left', (0.4, 3.2, 1.2), (-0.1, 0, 0.5)),
        ('right', (0.4, -3.2, 1.2), (-0.1, 0, 0.5)),
        ('seat', (1.5, -1.8, 2.55), (-0.1, 0, 0.34)),
        ('grip-L', (0.95, 0.82, 1.02), (0.06, 0.15, 0.54)),
        ('grip-R', (0.95, -0.82, 1.02), (0.06, -0.15, 0.54)),
    )
    for label, at, look in views:
        if 'grips' in ARGS and not label.startswith('grip-'):
            continue
        if 'quick' in ARGS and label not in ('front', 'right', 'seat', 'grip-L', 'grip-R'):
            continue
        if label.startswith('grip-'):
            side = 0 if label.endswith('L') else 1
            contact = Vector(cockpit.grip(side)[0]) * SCALE
            sign = 1 if side == 0 else -1
            look = contact
            at = contact + Vector((.34, sign * .30, .22)) * SCALE
        render(scene, OUT / f'{CHARACTER}-kart-{label}.png', at, look)
    print('KART PREVIEW COMPLETE', CHARACTER)


if __name__ == '__main__':
    if CHARACTER == 'all':
        directory = OUT
        for CHARACTER in ('cairo', 'modori', 'nox', 'paul'):
            OUT = directory / CHARACTER
            OUT.mkdir(parents=True, exist_ok=True)
            print('BEGIN CHARACTER', CHARACTER, flush=True)
            main()
    else:
        main()
