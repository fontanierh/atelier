"""What the bike and horse riders share (vehicles/bike/rider.py, horses/rider.py): the rest-skeleton solve, hand frames,
easing, keyed actions and the review studio. Blender only; each rider authors its own clips on top of these.

The rider's world is Yorimichi's character space: metres, +X forward, +Y left, +Z up.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

SIDE = {'L': 1, 'R': -1}


def rot(pitch=0., yaw=0., roll=0.):
    """World rotation from degrees: pitch forward about +Y, yaw left about +Z, roll left about -X."""
    return (Matrix.Rotation(math.radians(yaw), 3, 'Z') @ Matrix.Rotation(math.radians(pitch), 3, 'Y')
            @ Matrix.Rotation(-math.radians(roll), 3, 'X'))


def ease(s):
    return s * s * (3 - 2 * s)


def smooth(a, b, s):
    s = ease(s)
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * s for x, y in zip(a, b))
    return a + (b - a) * s


class Rig:
    """Forward kinematics on the rest skeleton in armature space; pose matrices are set bone by bone, parent first.
    `limb_offset` (empty here) holds a limb bone's rest frame relative to its aim frame, for rigs whose bones do not
    point at their child; a rider that needs it fills it in."""
    def __init__(self, arm):
        self.arm, self.M = arm, arm.matrix_world.copy(); self.Mi = self.M.inverted()
        self.scale = self.M.to_scale().x
        self.rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        self.order = [b.name for b in arm.data.bones]   # parents come before children
        self.rel = {n: (self.rest[p].inverted() @ self.rest[n] if p else self.rest[n]) for n, p in self.parent.items()}
        self.length = lambda a, b: (self.rest[b].translation - self.rest[a].translation).length
        self.limb_offset = {}
        self.hinge = {}
        for side in 'LR':
            for upper, lower, bend in ((f'upperarm_{side}', f'forearm_{side}', Vector((1, 0, 0))), (f'thigh_{side}', f'shin_{side}', Vector((-1, 0, 0)))):
                for bone in (upper, lower):
                    R = self.rest[bone].to_3x3(); y = R.col[1].normalized()
                    n = y.cross(bend).normalized()
                    best = max(((i, s) for i in (0, 2) for s in (1, -1)), key=lambda c: c[1] * R.col[c[0]].normalized().dot(n))
                    self.hinge[bone] = best

    def begin(self):
        self.pose, self.basis = {}, {}

    def place(self, name, matrix):
        """Set a bone's pose matrix (armature space) and record its basis."""
        p = self.parent[name]
        base = (self.pose[p] @ self.rel[name]) if p else self.rel[name]
        self.pose[name] = matrix; self.basis[name] = base.inverted() @ matrix

    def local(self, name, delta=None):
        """Pose a bone by a world-axis rotation about its own head, relative to its parent."""
        p = self.parent[name]
        base = (self.pose[p] @ self.rel[name]) if p else self.rel[name]
        R = self.rest[name].to_3x3().normalized()
        q = (R.inverted() @ delta @ R) if delta is not None else Matrix.Identity(3)
        self.pose[name] = base @ q.to_4x4(); self.basis[name] = q.to_4x4()

    def head(self, name):
        p = self.parent[name]
        return ((self.pose[p] @ self.rel[name]) if p else self.rel[name]).translation

    def to_arm(self, world):
        return self.Mi @ Vector(world)

    def world(self, arm_point):
        return self.M @ arm_point

    def aimed(self, bone, y, n):
        """Rotation whose Y is `y` and whose hinge axis (found from the rest pose) is `n`."""
        if bone in self.limb_offset:
            y_u = y.normalized()
            z_u = (n - y_u * n.dot(y_u)).normalized()
            x_u = y_u.cross(z_u).normalized()
            return Matrix((x_u, y_u, z_u)).transposed() @ self.limb_offset[bone]
        axis, sign = self.hinge[bone]
        if axis == 2:
            z = n * sign; x = y.cross(z)
        else:
            x = n * sign; z = x.cross(y)
        return Matrix((x.normalized(), y.normalized(), z.normalized())).transposed()

    def two_bone(self, upper, lower, end, target_arm, pole_arm, end_rot, forearm_twist=0.):
        """@cc [owner:fontanierh,label:correctness] unsigned-rider-reach-error
        Reach `target_arm` with the end bone's head; `forearm_twist` (0..1) rolls the lower bone toward the end's
        frame. Return the nonnegative distance in world metres from the target, including targets inside the
        minimum reach of unequal bone lengths, so the fit gate MUST NOT discard an unreachable contact's error.
        """
        S = self.head(upper)
        l1, l2 = self.length(upper, lower), self.length(lower, end)
        d = target_arm - S; D = min(max(d.length, abs(l1 - l2) + 1e-4), (l1 + l2) * .9995); u = d.normalized()
        a = (l1 * l1 - l2 * l2 + D * D) / (2 * D); h = math.sqrt(max(l1 * l1 - a * a, 0.))
        v = pole_arm - u * pole_arm.dot(u); v = v.normalized() if v.length > 1e-6 else u.orthogonal().normalized()
        E = S + u * a + v * h; W = S + u * D
        y1, y2 = (E - S).normalized(), (W - E).normalized()
        n = y1.cross(y2)
        n = n.normalized() if n.length > 1e-5 else u.cross(v).normalized()
        self.place(upper, Matrix.Translation(S) @ self.aimed(upper, y1, n).to_4x4())
        R_lower = self.aimed(lower, y2, n)
        if forearm_twist > 0.:
            R_end_unrolled = (R_lower @ self.rel[end].to_3x3()).normalized()
            z_u = R_end_unrolled.col[2] - y2 * R_end_unrolled.col[2].dot(y2)
            z_e = end_rot.col[2] - y2 * end_rot.col[2].dot(y2)
            if z_u.length > 1e-4 and z_e.length > 1e-4:
                q_tw = z_u.normalized().rotation_difference(z_e.normalized())
                R_lower = Quaternion((1., 0., 0., 0.)).slerp(q_tw, forearm_twist).to_matrix() @ R_lower
        self.place(lower, Matrix.Translation(self.head(lower)) @ R_lower.to_4x4())
        self.place(end, Matrix.Translation(self.head(end)) @ end_rot.to_4x4())
        return abs(d.length - D) * self.scale


def rest_world_rot(rig, bone):
    return rig.rest[bone].to_3x3().normalized()


class Hands:
    """Hand frames: fingers direction f and palm direction p, with the knuckle line k = s (p x f) (s = +1 left). A
    rider sets `rest` ({side: (f, p)} of the rest hand) and names its own frames."""
    @staticmethod
    def basis(side, f, p):
        k = SIDE[side] * p.cross(f)
        return Matrix((k.normalized(), f.normalized(), p.normalized())).transposed()

    def turn(self, side, f, p):
        """World rotation that takes the rest hand to fingers `f` and palm `p`."""
        f = f.normalized(); p = (p - f * p.dot(f)).normalized()
        f0, p0 = self.rest[side]
        return self.basis(side, f, p) @ self.basis(side, f0, p0).inverted()


def write_action(rig, name, poses):
    """A new action on the rig's armature keying each pose's bone rotations (and the pelvis location), one per frame."""
    arm = rig.arm
    action = bpy.data.actions.new(name); arm.animation_data_create(); arm.animation_data.action = action
    frames = list(range(len(poses)))
    def curve(path, index, values):
        fc = action.fcurve_ensure_for_datablock(arm, path, index=index)
        fc.keyframe_points.add(len(values))
        flat = []
        for f, v in zip(frames, values): flat += [f, v]
        fc.keyframe_points.foreach_set('co', flat)
        fc.keyframe_points.foreach_set('interpolation', [1] * len(values))
        fc.update()
    for bone in rig.order:
        pb = arm.pose.bones[bone]; pb.rotation_mode = 'QUATERNION'
        qs = []
        for p in poses:
            q = p[bone].to_quaternion()
            if qs and q.dot(qs[-1]) < 0: q = -q
            qs.append(q)
        for k in range(4): curve(f'pose.bones["{bone}"].rotation_quaternion', k, [q[k] for q in qs])
        if bone == 'pelvis':
            for k in range(3): curve(f'pose.bones["{bone}"].location', k, [p[bone].translation[k] for p in poses])
    if arm.animation_data.action_slot is None:
        arm.animation_data.action_slot = action.slots[0]
    return action


def studio(scene, name='Studio', background=(.80, .80, .78), strength=.9, key=(30, 48, -40), fill=None):
    """Review lighting, a floor and a camera. `key` and `fill` are suns as (angle, elevation, heading) in degrees;
    `fill` also has an energy first: (energy, angle, elevation, heading)."""
    scene.render.engine = 'BLENDER_EEVEE'; scene.view_settings.view_transform = 'Standard'
    scene.eevee.taa_render_samples = 32
    world = bpy.data.worlds.new(name); scene.world = world; world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (*background, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = strength
    sun = bpy.data.objects.new('Key', bpy.data.lights.new('Key', 'SUN')); scene.collection.objects.link(sun)
    sun.data.energy = 3.4; sun.data.angle = math.radians(key[0]); sun.rotation_euler = (math.radians(key[1]), 0, math.radians(key[2]))
    if fill:
        light = bpy.data.objects.new('Fill', bpy.data.lights.new('Fill', 'SUN')); scene.collection.objects.link(light)
        light.data.energy = fill[0]; light.data.angle = math.radians(fill[1])
        light.rotation_euler = (math.radians(fill[2]), 0, math.radians(fill[3]))
    floor = bpy.data.objects.new('Floor', bpy.data.meshes.new('Floor')); scene.collection.objects.link(floor)
    floor.data.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    mat = bpy.data.materials.new('FloorMat'); mat.use_nodes = True
    mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.62, .60, .56, 1)
    floor.data.materials.append(mat)
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); scene.collection.objects.link(cam); scene.camera = cam
    for ob in scene.objects:
        if ob.name.startswith(('Bokken', 'Review')): ob.hide_render = True
    return cam


def look(cam, eye, target, lens=50):
    cam.location = Vector(eye); cam.rotation_euler = (Vector(target) - Vector(eye)).to_track_quat('-Z', 'Y').to_euler(); cam.data.lens = lens


def character(name, folder):
    """The character's rig (characters/pipeline/rig.py: its prepare, SOURCE, OUT and FBX) and its `folder` output."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'characters' / 'pipeline'))
    import rig
    module = rig.load(name)
    return module, module.OUT / folder
