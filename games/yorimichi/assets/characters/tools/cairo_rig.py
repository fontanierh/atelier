"""Pose authoring helpers for the Cairo 53-bone rig (23 Tripo body bones).

Everything is computed in armature space with an explicit forward-kinematics
matrix table, so a frame is posed with a single depsgraph update. Rotations are
expressed as deltas from the accepted standing pose ("neutral"), in world axes:
the character faces +X, anatomical left is +Y and up is +Z. Bone names, parents,
rest transforms, bind matrices, finger drivers and meshes are never modified.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import math
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

BODY = ['Root', 'Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head',
        'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
        'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand',
        'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
        'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase']
HAND_PROPS = ['thumb_curl', 'index_curl', 'middle_curl', 'ring_curl', 'pinky_curl', 'thumb_opposition', 'finger_spread']
GARMENT_KEYS = {'sweatshirt': ['Left · cloth compression', 'Right · cloth compression', 'Left · torso arm clearance',
                               'Right · torso arm clearance', 'Left · cuff relief front', 'Left · cuff relief top',
                               'Left · cuff relief bottom', 'Right · cuff relief front', 'Right · cuff relief top',
                               'Right · cuff relief bottom'],
                'shorts': ['Left · cloth compression', 'Right · cloth compression']}
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
TAU = math.tau


def bn(name):
    return name if name == 'Root' else 'mixamorig:' + name


def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def smooth(t):
    t = clamp(t)
    return t * t * (3 - 2 * t)


def smoother(t):
    t = clamp(t)
    return t * t * t * (10 + t * (-15 + 6 * t))


def ramp(a, b, v):
    """Smoothstep between thresholds a and b (a may exceed b)."""
    return smooth((v - a) / (b - a))


def lerp(a, b, t):
    return a + (b - a) * t


def q_axis(axis, degrees):
    return Quaternion(axis, math.radians(degrees))


def hermite(points, t, cyclic=False):
    """Catmull-Rom style interpolation through (time, value...) rows.

    Outside the range the first/last rows are held. With cyclic=True the rows
    must start at 0 and end at the period with an identical value.
    """
    if t <= points[0][0]:
        return list(points[0][1:])
    if t >= points[-1][0]:
        return list(points[-1][1:])
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if a[0] <= t <= b[0]:
            if cyclic:
                previous = points[i - 1] if i else (points[-2][0] - points[-1][0], *points[-2][1:])
                following = points[i + 2] if i + 2 < len(points) else (points[-1][0] + points[1][0], *points[1][1:])
            else:
                previous = points[i - 1] if i else a
                following = points[i + 2] if i + 2 < len(points) else b
            u = (t - a[0]) / (b[0] - a[0])
            h = b[0] - a[0]
            out = []
            for c in range(1, len(a)):
                m0 = (b[c] - previous[c]) / (b[0] - previous[0]) if b[0] != previous[0] else 0
                m1 = (following[c] - a[c]) / (following[0] - a[0]) if following[0] != a[0] else 0
                out.append((2*u**3 - 3*u*u + 1) * a[c] + (u**3 - 2*u*u + u) * h * m0
                           + (-2*u**3 + 3*u*u) * b[c] + (u**3 - u*u) * h * m1)
            return out
    return list(points[-1][1:])


class Timeline:
    """Named scalar tracks keyed at times; smooth Catmull-Rom between keys.

    keys: list of (time, {name: value, ...}). Missing names hold their
    previous value. ease='smooth' zeroes the tangents at every key (a hold),
    which suits anticipation poses; the default keeps flowing tangents.
    """
    def __init__(self, keys, defaults, ease='flow'):
        self.defaults = dict(defaults)
        names = set(self.defaults)
        for _, values in keys:
            names |= set(values)
        self.tracks = {}
        for name in names:
            rows, current = [], self.defaults.get(name, 0.0)
            for time, values in keys:
                current = values.get(name, current)
                rows.append((time, current))
            self.tracks[name] = rows
        self.ease = ease

    def at(self, t):
        out = {}
        for name, rows in self.tracks.items():
            if self.ease == 'smooth':
                value = rows[0][1]
                for (t0, v0), (t1, v1) in zip(rows, rows[1:]):
                    if t >= t0:
                        value = lerp(v0, v1, smooth((t - t0) / (t1 - t0)) if t1 > t0 else 1)
                out[name] = value
            else:
                out[name] = hermite(rows, t)[0]
        return out


class Rig:
    def __init__(self, arm, scene, shoes, floor_world_z):
        self.obj, self.scene, self.shoes = arm, scene, shoes
        self.W = arm.matrix_world.copy()
        self.scale = self.W.to_scale().x
        self.rest = {n: arm.data.bones[bn(n)].matrix_local.copy() for n in BODY}
        self.parent = {n: (arm.data.bones[bn(n)].parent.name.replace('mixamorig:', '') if arm.data.bones[bn(n)].parent else None) for n in BODY}
        self.length = {n: arm.data.bones[bn(n)].length for n in BODY}
        # The accepted standing review pose is the neutral base for every clip.
        self.neutral = {n: arm.pose.bones[bn(n)].matrix.to_quaternion() for n in BODY}
        self.neutral_matrix = {n: arm.pose.bones[bn(n)].matrix.copy() for n in BODY}
        self.neutral_head = {n: arm.pose.bones[bn(n)].head.copy() for n in BODY}
        self.neutral_dir = {n: (arm.pose.bones[bn(n)].tail - arm.pose.bones[bn(n)].head).normalized() for n in BODY}
        self.hand_neutral = {side: {p: float(arm.pose.bones[bn(side + 'Hand')][p]) for p in HAND_PROPS} for side in ['Left', 'Right']}
        self.floor = (floor_world_z - self.W.translation.z) / self.scale
        self.sole = self._sole_samples()
        self.M = {}

    # --- geometry captured from the real shoe soles -------------------------
    def _sole_samples(self):
        """Shoe vertices weighted only to Foot/ToeBase, as an exact two-bone blend.

        Returns per side: local coordinates in the Foot frame, in the ToeBase
        frame, and the two weights, so posed positions reproduce the skinning."""
        out = {}
        to_armature = self.W.inverted() @ self.shoes.matrix_world
        for side in ['Left', 'Right']:
            foot_group = self.shoes.vertex_groups.get(bn(side + 'Foot'))
            toe_group = self.shoes.vertex_groups.get(bn(side + 'ToeBase'))
            if foot_group is None:
                continue
            fi, ti = foot_group.index, toe_group.index if toe_group else -1
            foot_local, toe_local, wf, wt = [], [], [], []
            inv_foot, inv_toe = self.rest[side + 'Foot'].inverted(), self.rest[side + 'ToeBase'].inverted()
            for v in self.shoes.data.vertices:
                weights = {g.group: g.weight for g in v.groups if g.weight > 1e-4}
                f, t = weights.get(fi, 0.0), weights.get(ti, 0.0)
                if f + t < .99:
                    continue
                rest_point = to_armature @ v.co
                foot_local.append((inv_foot @ rest_point)[:]); toe_local.append((inv_toe @ rest_point)[:]); wf.append(f); wt.append(t)
            out[side] = {'foot': np.array(foot_local), 'toe': np.array(toe_local), 'wf': np.array(wf)[:, None], 'wt': np.array(wt)[:, None]}
        return out

    def sole_points(self, side):
        d = self.sole[side]
        mf = np.array(self.matrix(side + 'Foot')); mt = np.array(self.matrix(side + 'ToeBase'))
        pf = d['foot'] @ mf[:3, :3].T + mf[:3, 3]
        pt = d['toe'] @ mt[:3, :3].T + mt[:3, 3]
        return pf * d['wf'] + pt * d['wt']

    def sole_low(self, side):
        pts = self.sole_points(side)
        i = int(pts[:, 2].argmin())
        return Vector(pts[i])

    # --- forward kinematics table ------------------------------------------
    def begin(self):
        self.M = {'Root': self.rest['Root'].copy()}

    def matrix(self, n):
        return self.M[n] if n in self.M else self.inherited(n)

    def inherited(self, n):
        p = self.parent[n]
        return self.matrix(p) @ self.rest[p].inverted() @ self.rest[n]

    def head(self, n):
        return self.matrix(n).translation.copy()

    def rot(self, n):
        return self.matrix(n).to_quaternion()

    def direction(self, n):
        return self.rot(n) @ Y

    def parent_delta(self, n):
        p = self.parent[n]
        if p is None:
            return Quaternion()
        return self.rot(p) @ self.neutral[p].inverted()

    def set_rot(self, n, q, head=None):
        m = q.normalized().to_matrix().to_4x4()
        m.translation = head if head is not None else self.inherited(n).translation
        self.M[n] = m

    def base(self, n):
        return self.parent_delta(n) @ self.neutral[n]

    def rotate(self, n, q=None, head=None):
        """World-axis delta on top of the parent-carried neutral orientation."""
        self.set_rot(n, (q or Quaternion()) @ self.base(n), head)

    def bend(self, n, axis, degrees, head=None):
        """Rotate about a neutral-frame world axis transported by the parent."""
        world_axis = self.parent_delta(n) @ axis
        self.rotate(n, Quaternion(world_axis, math.radians(degrees)), head)

    def orient(self, n, direction, head=None):
        """Minimal rotation of the carried neutral orientation onto a direction."""
        base = self.base(n)
        current = base @ Y
        self.set_rot(n, current.rotation_difference(direction.normalized()) @ base, head)

    def fill(self):
        for n in BODY:
            if n not in self.M:
                self.M[n] = self.inherited(n)

    def two_bone(self, upper, lower, target, pole, extension=.995):
        """Analytic two-bone reach; returns the achieved end position."""
        origin = self.head(upper)
        first, second = self.length[upper], self.length[lower]
        delta = target - origin
        distance = min((first + second) * extension, max(abs(first - second) + 1e-5, delta.length))
        axis = delta.normalized() if delta.length > 1e-9 else Z
        bend = pole - axis * pole.dot(axis)
        if bend.length < 1e-6:
            bend = Vector((0, 0, 1)) - axis * axis.z
        bend.normalize()
        along = (first * first - second * second + distance * distance) / (2 * distance)
        joint = origin + axis * along + bend * math.sqrt(max(0, first * first - along * along))
        self.orient(upper, joint - origin)
        self.orient(lower, target - self.head(lower))
        return self.head(lower) + self.direction(lower) * second

    # --- higher level body helpers -------------------------------------------
    def hips(self, offset=Vector((0, 0, 0)), pitch=0, yaw=0, roll=0, centre=None, spin=None):
        """Place the pelvis. Rotation is world-axis: pitch about +Y (forward lean
        positive), yaw about +Z (left positive), roll about +X (left tilt positive).
        `spin` rotates the whole body about `centre` (visual somersault)."""
        q = q_axis(Z, yaw) @ q_axis(X, roll) @ q_axis(Y, pitch)
        position = self.neutral_head['Hips'] + offset
        if spin is not None:
            position = centre + spin @ (position - centre)
            q = spin @ q
        self.rotate('Hips', q, head=position)

    def spine(self, pitch=0, yaw=0, roll=0, head_pitch=0, head_yaw=0, head_roll=0, neck_share=.35,
              weights=(.30, .35, .35)):
        """Distribute torso rotation over Spine/Spine1/Spine2 and counter the head.

        Pitch/yaw/roll are world-axis totals for the chest relative to the pelvis;
        the head keeps its own explicit angles relative to the world (level by
        default), which reads as a character looking where they go.
        """
        for name, w in zip(['Spine', 'Spine1', 'Spine2'], weights):
            self.rotate(name, q_axis(Z, yaw * w) @ q_axis(X, roll * w) @ q_axis(Y, pitch * w))
        chest = self.rot('Spine2') @ self.neutral['Spine2'].inverted()
        want = q_axis(Z, head_yaw) @ q_axis(X, head_roll) @ q_axis(Y, head_pitch)
        # Neck takes a share of the correction, the head the remainder.
        correction = want @ chest.inverted()
        neck = Quaternion().slerp(correction, neck_share)
        self.rotate('Neck', neck)
        self.set_rot('Head', want @ self.neutral['Head'])

    def leg(self, side, ankle, pitch=0, yaw=0, toe=0, pole=None, extension=.995):
        """Reach the ankle position; foot pitch is absolute (toes down positive)."""
        pole = pole or Vector((1, 0, 0))
        self.two_bone(side + 'UpLeg', side + 'Leg', ankle, pole, extension)
        foot = side + 'Foot'
        q = q_axis(Z, yaw) @ q_axis(Y, pitch)
        self.set_rot(foot, q @ self.neutral[foot])
        self.bend(side + 'ToeBase', Y, -toe)

    def plant(self, side, x, y, pitch=0, yaw=0, toe=0, pole=None, lift=0.0, extension=.995):
        """Put the lowest sole point at (x, y, floor + lift) with the given foot angles.

        The foot is rigid, so the ankle is offset by the sole's own extent for
        that orientation. Returns the achieved sole low point."""
        pole = pole or Vector((1, 0, 0))
        foot = side + 'Foot'
        q = q_axis(Z, yaw) @ q_axis(Y, pitch)
        rotation = (q @ self.neutral[foot]).to_matrix()
        self.M[foot] = rotation.to_4x4()
        self.M[side + 'ToeBase'] = self.M[foot] @ self.rest[foot].inverted() @ self.rest[side + 'ToeBase']
        self.bend(side + 'ToeBase', Y, -toe)
        low = self.sole_low(side)  # relative to an ankle at the origin
        ankle = Vector((x - low.x, y - low.y, self.floor + lift - low.z))
        self.leg(side, ankle, pitch, yaw, toe, pole, extension)
        return self.sole_low(side)

    PALM_TWIST = 90  # forearm pronation: the standing pose has palms forward; hang them against the thighs

    def arm(self, side, swing=0, spread=0, twist=0, elbow=0, wrist_pitch=0, wrist_yaw=0, forearm_twist=0, yaw=0, hinge=0):
        """FK arm from the hanging neutral. swing: forward raise about the lateral
        axis (forward positive); spread: away from the body (positive outward);
        twist about the upper arm on top of the palms-inward default (positive
        turns the palm forward); elbow: flexion about the lateral hinge (positive
        folds forward/up); wrist_pitch folds the palm toward the inner forearm;
        wrist_yaw is sideways deviation. `yaw` turns the swing/spread axes with
        the body so a turned character swings in its own plane."""
        sign = 1 if side == 'Left' else -1
        frame = q_axis(Z, yaw)
        placement = frame @ q_axis(Y, -swing) @ q_axis(X, sign * spread) @ frame.inverted()
        roll = q_axis(Z, sign * twist)
        shoulder_delta = self.parent_delta(side + 'Arm')
        self.rotate(side + 'Arm', placement @ roll)
        # Elbow hinge: the lateral axis carried by the placement only (not the roll),
        # so a palms-in arm still folds forward.
        # `hinge` turns the elbow axis about the upper arm (-90 folds a sideways-raised forearm upward).
        hinge_axis = (placement @ q_axis(Z, sign * hinge) @ shoulder_delta) @ Y
        q_elbow = Quaternion(hinge_axis, math.radians(-elbow))
        forearm_dir = (q_elbow @ self.base(side + 'ForeArm')) @ Y
        q_twist = Quaternion(forearm_dir, math.radians(sign * (self.PALM_TWIST + forearm_twist)))
        self.rotate(side + 'ForeArm', q_twist @ q_elbow)
        carried = self.parent_delta(side + 'Hand')
        q_hand = Quaternion(carried @ X, math.radians(sign * wrist_yaw)) @ Quaternion(carried @ Y, math.radians(-wrist_pitch))
        self.rotate(side + 'Hand', q_hand)

    def reach(self, side, wrist, pole=None, extension=.99):
        pole = pole or Vector((-1, 0, -.4))
        return self.two_bone(side + 'Arm', side + 'ForeArm', wrist, pole, extension)

    def hand(self, side, curl=None, thumb=None, opposition=None, spread=None, index=None):
        pb = self.obj.pose.bones[bn(side + 'Hand')]
        base = self.hand_neutral[side]
        values = dict(base)
        if curl is not None:
            for f in ['index_curl', 'middle_curl', 'ring_curl', 'pinky_curl']:
                values[f] = curl
        if index is not None:
            values['index_curl'] = index
        if thumb is not None:
            values['thumb_curl'] = thumb
        if opposition is not None:
            values['thumb_opposition'] = opposition
        if spread is not None:
            values['finger_spread'] = spread
        for p, v in values.items():
            pb[p] = float(v)

    # --- writing the pose into Blender ---------------------------------------
    def apply(self):
        self.fill()
        for n in BODY:
            pb = self.obj.pose.bones[bn(n)]
            p = self.parent[n]
            local = (self.M[p] @ self.rest[p].inverted() @ self.rest[n]).inverted() @ self.M[n] if p else self.rest[n].inverted() @ self.M[n]
            pb.rotation_mode = 'QUATERNION'
            pb.matrix_basis = local

    def key(self, frame, last):
        for n in BODY:
            pb = self.obj.pose.bones[bn(n)]
            q = pb.rotation_quaternion.copy()
            if n in last and q.dot(last[n]) < 0:
                q.negate()
                pb.rotation_quaternion = q
            last[n] = q.copy()
            pb.keyframe_insert('rotation_quaternion', frame=frame, group=pb.name)
            if n in ('Hips', 'Root'):
                pb.keyframe_insert('location', frame=frame, group=pb.name)
        for side in ['Left', 'Right']:
            hand = self.obj.pose.bones[bn(side + 'Hand')]
            for prop in HAND_PROPS:
                hand.keyframe_insert(f'["{prop}"]', frame=frame, group=hand.name + ' · grip')

    def lowest_sole(self):
        return min(self.sole_low(side).z for side in ['Left', 'Right'])

    def to_world(self, v):
        return self.W @ Vector(v)


def garment_values(rig, standing=False):
    """Per-frame garment key values derived from the posed skeleton, using the
    same fields the accepted sprint used, evaluated for this pose."""
    out = {'sweatshirt': {}, 'shorts': {}}
    for side in ['Left', 'Right']:
        arm_dir = rig.direction(side + 'Arm')
        thigh_dir = rig.direction(side + 'UpLeg')
        out['sweatshirt'][side + ' · cloth compression'] = 0 if standing else ramp(.030, .145, abs(arm_dir.x))
        out['shorts'][side + ' · cloth compression'] = 0 if standing else ramp(.025, .14, thigh_dir.x)
        upper_rest = rig.rest[side + 'Arm']
        bend = (upper_rest @ rig.M[side + 'Arm'].inverted()).to_3x3() @ (rig.direction(side + 'ForeArm') * rig.length[side + 'ForeArm'])
        length = max(math.hypot(bend.x, bend.z), 1e-10)
        for label, value in [('front', max(0, bend.x / length)), ('top', max(0, bend.z / length)), ('bottom', max(0, -bend.z / length))]:
            out['sweatshirt'][f'{side} · cuff relief {label}'] = 0 if standing else value
        out['sweatshirt'][side + ' · torso arm clearance'] = 0
    return out


def forearm_torso_proximity(rig, side):
    """Closest approach (armature units) between the forearm/hand segment and
    the torso axis through the chest, used to skip the exact probe cheaply."""
    a = rig.head(side + 'ForeArm')
    b = rig.head(side + 'Hand') + rig.direction(side + 'Hand') * rig.length[side + 'Hand'] * .6
    axis_point = rig.head('Spine1')
    axis_dir = (rig.head('Spine2') - rig.head('Spine')).normalized()
    best = 1e9
    for t in np.linspace(0, 1, 9):
        p = a.lerp(b, float(t))
        rel = p - axis_point
        radial = rel - axis_dir * rel.dot(axis_dir)
        best = min(best, radial.length)
    return best
