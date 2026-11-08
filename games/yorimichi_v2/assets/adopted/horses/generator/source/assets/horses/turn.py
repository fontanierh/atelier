"""Bake pivot footwork, jumping and running tail clearance while preserving the committed GLB's original data."""
import copy
import math
import struct

import bpy
from mathutils import Matrix, Quaternion, Vector

from atelier.gltf import glb_pack, glb_parts

PIVOT_CLIPS = ('TurnLeft', 'TurnRight')
JUMP_CLIP = 'Jump'
CLIPS = (*PIVOT_CLIPS, JUMP_CLIP)
DEGREES_PER_CYCLE = 36.
# Touchdowns match HorseComponent's four walk beats. Fore and hind legs step separately.
LEGS = (('Arm_1_L', 'Arm_2_L', 'Wrist_L', .10), ('Leg_1_R', 'Leg_2_R', 'Ankle_R', .35),
        ('Arm_1_R', 'Arm_2_R', 'Wrist_R', .60), ('Leg_1_L', 'Leg_2_L', 'Ankle_L', .85))
# Dock (Tail_1..3) arches out behind the croup; plume (Tail_4..7) drapes behind the kicking hind hooves.
TAIL_LIFT = {
    'Walk': (22., 18., 6., -10., -10., -8., -4.),
    'Trot': (28., 24., 8., -12., -12., -8., -4.),
    'Canter': (42., 36., 10., -10., -10., -8., -4.),
    'Gallop': (16., 14., 6., -6., -8., -6., -4.),
    'Sprint': (42., 38., 8., -6., -8., -6., -4.),
    'TurnLeft': (22., 18., 6., -10., -10., -8., -4.),
    'TurnRight': (22., 18., 6., -10., -10., -8., -4.),
    'Jump': (22., 18., 6., -6., -8., -6., -4.),
}


def foot_target(rest, centre, phase, direction, scale):
    """A planted hoof counter-rotates the actor; its short lifted swing resets the next foothold."""
    stance = .72
    if phase < stance:
        travel, lift = phase / stance, 0.
    else:
        t = (phase - stance) / (1. - stance)
        travel = 1. - t * t * (3. - 2. * t)
        lift = .10 * scale * math.sin(math.pi * t) ** 2
    angle = direction * math.radians(DEGREES_PER_CYCLE * stance) * (.5 - travel)
    yaw = Quaternion((0., 0., 1.), angle)
    at = centre + yaw @ (rest - centre)
    at.z = rest.z + lift
    return at, yaw


def jump_target(rest_delta, root, phase, is_fore, is_left, scale):
    """Fold the forelegs under the chest over the obstacle, push off and fold the hind legs, then reach to land."""
    lead = (.025 if is_left else -.025) * scale
    if is_fore:
        tuck = math.sin(math.pi * min(1., phase / .68)) ** 2
        reach = math.sin(math.pi * max(0., (phase - .52) / .48)) ** 2
        at = root + Vector((
            rest_delta.x,
            rest_delta.y + (.10 * tuck - .24 * reach) * scale + lead,
            rest_delta.z + (.24 * tuck + .06 * reach) * scale,
        ))
        pitch = math.radians(65. * tuck - 24. * reach)
    else:
        push = math.sin(math.pi * min(1., phase / .28)) ** 2
        fold = math.sin(math.pi * max(0., min(1., (phase - .16) / .70))) ** 2
        land = math.sin(math.pi * max(0., (phase - .68) / .32)) ** 2
        at = root + Vector((
            rest_delta.x,
            rest_delta.y + (.14 * push + .22 * fold - .10 * land) * scale + lead,
            rest_delta.z + (.04 * push + .28 * fold + .04 * land) * scale,
        ))
        pitch = math.radians(18. * push + 55. * fold - 12. * land)
    return at, Quaternion((1., 0., 0.), pitch)


def _quat_mul(q1, q2):
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def _quat_z(deg):
    rad = .5 * math.radians(deg)
    return (0., 0., math.sin(rad), math.cos(rad))


def solve_leg(arm, upper_name, lower_name, end_name, target, rotation):
    """Two rigid links to the ankle/wrist, with the hoof's orientation independent of knee flexion."""
    upper, lower, end = (arm.pose.bones[n] for n in (upper_name, lower_name, end_name))
    a, b, c = (p.head.copy() for p in (upper, lower, end))
    upper_rotation, lower_rotation = upper.matrix.to_quaternion(), lower.matrix.to_quaternion()
    l1, l2 = (b - a).length, (c - b).length
    axis = (target - a).normalized()
    distance = min(max((target - a).length, abs(l1 - l2) + 1e-5), (l1 + l2) * .9999)
    along = (l1 * l1 - l2 * l2 + distance * distance) / (2. * distance)
    bend = (b - a) - axis * (b - a).dot(axis)
    if bend.length < 1e-6:
        bend = axis.cross(Vector((1., 0., 0.)))
    knee = a + axis * along + bend.normalized() * math.sqrt(max(0., l1 * l1 - along * along))
    ankle = a + axis * distance
    q1 = (b - a).rotation_difference(knee - a) @ upper_rotation
    q2 = (c - b).rotation_difference(ankle - knee) @ lower_rotation
    upper.matrix = Matrix.LocRotScale(a, q1, None)
    bpy.context.view_layer.update()
    lower.matrix = Matrix.LocRotScale(knee, q2, None)
    bpy.context.view_layer.update()
    end.matrix = Matrix.LocRotScale(ankle, rotation, None)
    bpy.context.view_layer.update()
    return (end.head - target).length


def bake_glb(source, arm, scene, play, fps=60):
    """@cc [owner:fontanierh,label:correctness] pivot-source-preservation
    Generated horse clips and running tail clearance MUST leave original meshes, skins, nodes and binary data intact,
    and MUST keep every clip's rider-contact bone transforms unchanged so existing rider clips stay synchronized.
    """
    doc, binary = glb_parts(source)
    doc = copy.deepcopy(doc)
    data = bytearray(binary)
    parents = {child: i for i, n in enumerate(doc['nodes']) for child in n.get('children', [])}
    rest_world = {}

    def rest(i):
        if i not in rest_world:
            n = doc['nodes'][i]
            q = n.get('rotation', [0., 0., 0., 1.])
            local = Matrix.LocRotScale(Vector(n.get('translation', [0., 0., 0.])),
                                       Quaternion((q[3], *q[:3])), Vector(n.get('scale', [1., 1., 1.])))
            rest_world[i] = rest(parents[i]) @ local if i in parents else local
        return rest_world[i]

    for i in range(len(doc['nodes'])):
        rest(i)
    # Blender world (+Z up) -> glTF world (+Y up). Bone axes can differ after glTF import,
    # so transfer world deltas from the imported bind pose, rather than copying local quaternions.
    convert = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))
    bones = {i: arm.pose.bones.get(n.get('name', '')) for i, n in enumerate(doc['nodes'])}
    bones = {i: b for i, b in bones.items() if b is not None}
    bind_inverse = {i: (arm.matrix_world @ arm.data.bones[b.name].matrix_local).inverted() for i, b in bones.items()}

    def accessor(values, width):
        while len(data) % 4:
            data.append(0)
        packed = struct.pack('<' + 'f' * sum(len(v) for v in values), *(x for v in values for x in v))
        view = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': len(data), 'byteLength': len(packed)})
        data.extend(packed)
        a = {'bufferView': view, 'componentType': 5126, 'count': len(values),
             'type': {1: 'SCALAR', 3: 'VEC3', 4: 'VEC4'}[width]}
        if width == 1:
            a.update(min=[values[0][0]], max=[values[-1][0]])
        index = len(doc['accessors'])
        doc['accessors'].append(a)
        return index

    play(arm, 'Idle')
    scene.frame_set(0)
    bpy.context.view_layer.update()
    feet = {end: arm.matrix_world @ arm.pose.bones[end].head for _, _, end, _ in LEGS}
    idle_deltas = {end: feet[end] - (arm.matrix_world @ arm.pose.bones[upper].head) for upper, _, end, _ in LEGS}
    rotations = {end: (arm.matrix_world @ arm.pose.bones[end].matrix).to_quaternion() for end in feet}
    # The walking toe roll belongs to forward propulsion. Keep each complete hoof
    # in its idle shape so a planted wrist/ankle also plants the actual hoof.
    toes = {b.name: b.matrix_basis.copy() for b in arm.pose.bones if b.name.startswith('Toe_')}
    assert len(toes) == 2 * len(LEGS), 'Pivot clips require both toe bones on all four hooves'
    # The imported armature has its own rotated basis. Author trajectories in Blender
    # world (+Z up), around the actor/mesh origin, then solve in armature space.
    centre = Vector((0., 0., 0.))
    scale = (arm.matrix_world @ arm.pose.bones['Saddle_Root'].head).z / 1.5993
    arm_inverse = arm.matrix_world.inverted()
    arm_rotation_inverse = arm.matrix_world.to_quaternion().inverted()
    walk = play(arm, 'Walk')
    end_frame = round(walk.frame_range[1])
    duration = end_frame / fps
    walk_poses = []
    roots = {end: [] for _, _, end, _ in LEGS}
    lengths = {}
    for frame in range(end_frame):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        walk_poses.append({b.name: b.matrix_basis.copy() for b in arm.pose.bones})
        for upper, lower, end, _ in LEGS:
            a, b, c = (arm.matrix_world @ arm.pose.bones[n].head for n in (upper, lower, end))
            roots[end].append(a)
            lengths[end] = (b - a).length + (c - b).length
    # Keep each hoof on its original ground plane while placing its pivot stance
    # within reach of every frame's moving hip/shoulder. Only the horizontal
    # foothold changes; neither bones nor the saddle are stretched or lowered.
    for _, _, end, offset in LEGS:
        circles = []
        for direction in (1., -1.):
            for frame, root in enumerate(roots[end]):
                target, yaw = foot_target(feet[end], centre, (frame / end_frame - offset) % 1., direction, scale)
                horizontal = yaw.inverted() @ Vector((root.x, root.y, 0.))
                radius2 = (lengths[end] * .997) ** 2 - (root.z - target.z) ** 2
                assert radius2 > 0., f'{end}: no reachable grounded pivot stance'
                circles.append((horizontal, math.sqrt(radius2)))
        at = Vector((feet[end].x, feet[end].y, 0.))
        for _ in range(40):
            for c, radius in circles:
                delta = at - c
                if delta.length > radius:
                    at = c + delta.normalized() * radius
        assert (at - Vector((feet[end].x, feet[end].y, 0.))).length < .15 * scale
        feet[end].x, feet[end].y = at.x, at.y
    times = accessor([(f / fps,) for f in range(end_frame + 1)], 1)
    worst = 0.
    for clip, direction in zip(PIVOT_CLIPS, (1., -1.)):
        tracks = {i: {'translation': [], 'rotation': [], 'scale': []} for i in bones}
        for frame in range(end_frame + 1):
            # Evaluate frame zero at the seam: the generated cycle closes exactly.
            scene.frame_set(frame % end_frame)
            # IK writes unkeyed location channels too. Restore the complete original pose,
            # so no result from the previous frame/direction can accumulate into this one.
            for name, basis in walk_poses[frame % end_frame].items():
                arm.pose.bones[name].matrix_basis = basis
            for name, basis in toes.items():
                arm.pose.bones[name].matrix_basis = basis
            bpy.context.view_layer.update()
            for upper, lower, end, offset in LEGS:
                at, yaw = foot_target(feet[end], centre, (frame / end_frame - offset) % 1., direction, scale)
                worst = max(worst, solve_leg(arm, upper, lower, end, arm_inverse @ at,
                                            arm_rotation_inverse @ yaw @ rotations[end]))
            world = {i: convert @ arm.matrix_world @ b.matrix @ bind_inverse[i] @ convert.inverted() @ rest_world[i]
                     for i, b in bones.items()}
            for i in bones:
                parent = parents.get(i)
                local = world.get(parent, rest_world.get(parent, Matrix.Identity(4))).inverted() @ world[i]
                loc, rot, size = local.decompose()
                q = [rot.x, rot.y, rot.z, rot.w]
                prev = tracks[i]['rotation']
                if prev and sum(a * b for a, b in zip(prev[-1], q)) < 0:
                    q = [-v for v in q]
                tracks[i]['translation'].append(tuple(loc))
                tracks[i]['rotation'].append(q)
                tracks[i]['scale'].append(tuple(size))
        animation = {'name': clip, 'samplers': [], 'channels': []}
        for i, paths in tracks.items():
            for path, values in paths.items():
                sampler = len(animation['samplers'])
                animation['samplers'].append({'input': times, 'output': accessor(values, len(values[0])), 'interpolation': 'LINEAR'})
                animation['channels'].append({'sampler': sampler, 'target': {'node': i, 'path': path}})
        doc['animations'].append(animation)

    gallop = play(arm, 'Gallop')
    gallop_end = round(gallop.frame_range[1])
    gallop_poses = []
    for frame in range(gallop_end):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        gallop_poses.append({b.name: b.matrix_basis.copy() for b in arm.pose.bones})
    jump_times = times if gallop_end == end_frame else accessor([(f / fps,) for f in range(gallop_end + 1)], 1)
    jump_tracks = {i: {'translation': [], 'rotation': [], 'scale': []} for i in bones}
    for frame in range(gallop_end + 1):
        scene.frame_set(frame % gallop_end)
        for name, basis in gallop_poses[frame % gallop_end].items():
            arm.pose.bones[name].matrix_basis = basis
        for name, basis in toes.items():
            arm.pose.bones[name].matrix_basis = basis
        bpy.context.view_layer.update()
        phase = frame / gallop_end
        for upper, lower, end, _ in LEGS:
            root = arm.matrix_world @ arm.pose.bones[upper].head
            at, pitch_q = jump_target(idle_deltas[end], root, phase, end.startswith('Wrist'), end.endswith('L'), scale)
            worst = max(worst, solve_leg(arm, upper, lower, end, arm_inverse @ at,
                                         arm_rotation_inverse @ pitch_q @ rotations[end]))
        world = {i: convert @ arm.matrix_world @ b.matrix @ bind_inverse[i] @ convert.inverted() @ rest_world[i]
                 for i, b in bones.items()}
        for i in bones:
            parent = parents.get(i)
            local = world.get(parent, rest_world.get(parent, Matrix.Identity(4))).inverted() @ world[i]
            loc, rot, size = local.decompose()
            q = [rot.x, rot.y, rot.z, rot.w]
            prev = jump_tracks[i]['rotation']
            if prev and sum(a * b for a, b in zip(prev[-1], q)) < 0:
                q = [-v for v in q]
            jump_tracks[i]['translation'].append(tuple(loc))
            jump_tracks[i]['rotation'].append(q)
            jump_tracks[i]['scale'].append(tuple(size))
    jump_anim = {'name': JUMP_CLIP, 'samplers': [], 'channels': []}
    for i, paths in jump_tracks.items():
        for path, values in paths.items():
            sampler = len(jump_anim['samplers'])
            jump_anim['samplers'].append({'input': jump_times, 'output': accessor(values, len(values[0])), 'interpolation': 'LINEAR'})
            jump_anim['channels'].append({'sampler': sampler, 'target': {'node': i, 'path': path}})
    doc['animations'].append(jump_anim)

    tail_nodes = {n.get('name'): i for i, n in enumerate(doc['nodes']) if n.get('name', '').startswith('Tail_')}
    for animation in doc['animations']:
        lifts = TAIL_LIFT.get(animation.get('name'))
        if not lifts:
            continue
        for rank, deg in enumerate(lifts, 1):
            node_idx = tail_nodes.get(f'Tail_{rank}')
            channel = next((c for c in animation['channels']
                            if c['target'].get('node') == node_idx and c['target'].get('path') == 'rotation'), None)
            if channel is None:
                continue
            sampler = animation['samplers'][channel['sampler']]
            acc_doc = doc['accessors'][sampler['output']]
            view_doc = doc['bufferViews'][acc_doc['bufferView']]
            start = view_doc.get('byteOffset', 0) + acc_doc.get('byteOffset', 0)
            count = acc_doc['count']
            raw = struct.unpack_from('<' + 'f' * (4 * count), data, start)
            lift_q = _quat_z(deg)
            lifted = []
            for k in range(count):
                qx, qy, qz, qw = raw[4 * k:4 * k + 4]
                if rank >= 3:
                    qz *= .35
                norm = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw) or 1.
                q = list(_quat_mul(lift_q, (qx / norm, qy / norm, qz / norm, qw / norm)))
                if lifted and sum(a * b for a, b in zip(lifted[-1], q)) < 0:
                    q = [-v for v in q]
                lifted.append(tuple(q))
            sampler['output'] = accessor(lifted, 4)

    doc['buffers'][0]['byteLength'] = len(data)
    proof = {'duration': duration, 'max_ankle_error_cm': round(worst * 100., 4)}
    assert worst < .005, f'Pivot hoof targets outside the leg reach: {proof}'
    return glb_pack(doc, bytes(data)), proof
