"""Cairo's bike clips: the pedalling cycle and the one-shots, authored in bike space on Cairo's own rig.

    blender -b --python games/yorimichi/assets/vehicles/bike/rider.py [-- --clips BikeRide,BikeBell] [--review DIR]
        [--character modori]

--character authors the same clips on another playable character's rig (its folder's export_unreal.prepare), into
build/yorimichi/<character>/bike/: the solve reaches the same grips, pedals and saddle with that body's limbs.

Opens Cairo's source through export_unreal.prepare (sha checked, contract bone names, 1.48 m; the blend is never
saved) and reads the bike's contact points from build/yorimichi/bike/manifest.json. Bike space is the bike model's:
metres, +X forward, +Y left, origin on the ground under the bottom bracket. While riding, Cairo's mesh origin sits
there, so every clip is authored with the rig's origin at the bike's.

A clip is a list of keys. Each key sets some channels and the rest hold. The pelvis, spine and head are posed
directly. Each hand and foot either holds its grip or pedal, which moves with the crank, steering and the bike's
own lift, pitch and lean, or goes to an explicit point; a solved two-bone IK reaches it. Every frame is solved and
keyed as plain bone rotations at 60 fps, then exported like botw.py to build/yorimichi/cairo/bike/fbx/A_<Clip>.fbx.

export.json lists each clip with:
- frames and loop;
- contact windows: when each hand or foot is on its grip or pedal, so the game's rider solve pins it there;
- the bike's motion per frame: crank angle, kickstand (0 down, 1 stowed), lift, pitch, lean, yaw, steer;
- for clips that leave Cairo standing, where his mesh origin ends relative to the bike.

--review DIR renders each clip's key moments, from the drive side and a front three-quarter view, with the bike posed
by its channels. --frames DIR renders the starting frames for the clips' video references.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'characters' / 'cairo'))
import export_unreal as cairo   # noqa: E402  (also puts the world folder, and yori, on the path)
import yori   # noqa: E402

BIKE = yori.OUT / 'bike'
OUT = yori.OUT / 'cairo' / 'bike'   # the character's own folder with --character (main)
FPS = 60
GROUND_SPACE = 'g'   # a target tagged ('g', x, y, z) is on the ground, not carried by the bike's lift, pitch or lean

MANIFEST = json.loads((BIKE / 'manifest.json').read_text())
RIDER, PIVOT = MANIFEST['rider'], MANIFEST['pivots']
SEAT = Vector(RIDER['saddle_top'])
GRIPS = {'L': Vector(RIDER['grips'][0]), 'R': Vector(RIDER['grips'][1])}
BB, CRANK, PEDAL_Y = Vector(PIVOT['BK_Crank']), MANIFEST['crank_length'], MANIFEST['pedal_offset_y'] + .056
HEAD = Vector(PIVOT['BK_Steer'])
TILT = math.radians(MANIFEST['steer_axis_tilt_degrees'])
AXIS = Vector((-math.sin(TILT), 0, math.cos(TILT)))   # steering axis, leaning back
STAND = Vector(PIVOT['BK_Kickstand'])
STAND_FOOT = Vector((-.024, .104, -STAND.z + .034))      # top of the left rubber foot, from the pivot
STOWED = math.radians(MANIFEST['kickstand_stowed_degrees'])
REAR_CONTACT = Vector((PIVOT['BK_WheelRear'][0], 0, 0))
# The grips sweep back: index finger at the inner, front end. Unit vector toward that end, per side.
GRIP_AXIS = {'L': Vector((.101, -.074, .013)).normalized(), 'R': Vector((.101, .074, .013)).normalized()}
SIDE = {'L': 1, 'R': -1}

# ---------------------------------------------------------------------------------------------------- the bike's pose

def bike_matrix(c):
    """The bike's own motion: lift, pitch about the rear contact (nose up positive), lean about the ground line (left
    positive)."""
    pitch = Matrix.Translation(REAR_CONTACT) @ Matrix.Rotation(-math.radians(c['pitch']), 4, 'Y') @ Matrix.Translation(-REAR_CONTACT)
    return Matrix.Translation((0, 0, c['lift'])) @ pitch @ Matrix.Rotation(-math.radians(c['lean_bike']), 4, 'X')


def steer_matrix(c):
    return Matrix.Translation(HEAD) @ Matrix.Rotation(math.radians(c['steer']), 4, AXIS) @ Matrix.Translation(-HEAD)


def pedal_point(c, side):
    """Top of the pedal tread under the ball of the foot (bike space, before the bike's own motion)."""
    a = math.radians(c['crank']) + (0 if side == 'R' else math.pi)
    return BB + Vector((CRANK * math.cos(a), SIDE[side] * PEDAL_Y, CRANK * math.sin(a) + .018))


def grip_point(c, side):
    return steer_matrix(c) @ (GRIPS[side] + GRIP_AXIS[side] * c['grip_slide_' + side])


def stand_point(c):
    return STAND + Matrix.Rotation(STOWED * c['stand'], 3, 'Y') @ STAND_FOOT

# ------------------------------------------------------------------------------------------------------------ clips

def rot(pitch=0., yaw=0., roll=0.):
    """World rotation from degrees: pitch forward about +Y, yaw left about +Z, roll left about -X."""
    return (Matrix.Rotation(math.radians(yaw), 3, 'Z') @ Matrix.Rotation(math.radians(pitch), 3, 'Y')
            @ Matrix.Rotation(-math.radians(roll), 3, 'X'))


DEFAULT = dict(pelvis=(-.185, 0., .685), pelvis_rot=(8., 0., 0.), lean=24., twist=0., side=0., head=(-16., 0., 0.), shrug=0.,
               hand_L='grip', hand_R='grip', frame_L='grip', frame_R='grip', curl_L=.85, curl_R=.85, thumb_R=0., grip_slide_L=0., grip_slide_R=0.,
               foot_L='pedal', foot_R='pedal', pitch_L=None, pitch_R=None,
               crank=0., stand=1., lift=0., pitch=0., lean_bike=0., yaw=0., steer=0.)
BESIDE = dict(pelvis=(-.24, .36, .615), pelvis_rot=(2., -12., 0.), lean=12., twist=-14., head=(-4., -10., 0.),
              hand_L='grip', frame_L='grip', hand_R=(-.19, .045, .668), frame_R='saddle', curl_R=.25,
              foot_L=(-.20, .45, 0.), foot_R=(-.27, .27, 0.), pitch_L=0., pitch_R=0., stand=0.)
ASTRIDE = dict(pelvis=(-.11, 0., .60), pelvis_rot=(6., 0., 0.), lean=20., twist=0., head=(-10., 0., 0.), hand_L='grip', hand_R='grip',
               frame_R='grip', curl_R=.85, foot_L=(-.04, .25, 0.), foot_R=(.01, -.25, 0.), pitch_L=0., pitch_R=0.)
STOP = dict(pelvis=(-.13, .05, .668), pelvis_rot=(4., 4., 0.), lean=16., twist=4., side=2., head=(-10., 6., 0.),
            foot_L=(GROUND_SPACE, -.03, .335, 0.), pitch_L=0., crank=35., lean_bike=12.)

CLIPS = {
    # One crank revolution, the cycle the game plays at the bike's cadence. Frame 0 has the cranks level.
    'BikeRide': dict(duration=1., loop=True, space='bike', linear=('crank',), keys=[(0., dict(crank=0.)), (1., dict(crank=-360.))]),
    'BikeMount': dict(duration=1.65, space='ground', keys=[
        (0., BESIDE),
        (.28, dict(pelvis=(-.22, .33, .602), side=-4., foot_R=(-.21, .27, .10), pitch_R=12.)),
        (.55, dict(pelvis=(-.17, .23, .600), lean=17., twist=-6., foot_R=(.03, .11, .40), pitch_R=20., hand_R=(-.02, -.09, .74), frame_R='relaxed', curl_R=.3)),
        (.80, dict(pelvis=(-.12, .05, .600), side=0., twist=0., foot_R=(.02, -.21, .10), pitch_R=6., hand_R='grip', frame_R='grip', curl_R=.85)),
        (.95, dict(ASTRIDE, head=(-12., 0., 0.))),
        (1.15, dict(foot_R='pedal', pitch_R=6., crank=30.)),
        (1.25, dict(pelvis=(-.15, 0., .66), lean=22.)),
        (1.40, dict(pelvis=(-.185, 0., .685), pelvis_rot=(8., 0., 0.), lean=24., head=(-16., 0., 0.), foot_L='pedal', pitch_L=None, pitch_R=None, crank=-15., stand=1.)),
        (1.65, dict(crank=-60.)),
    ], stand=[(0., 0.), (1.2, 0.), (1.38, 1.)]),
    'BikeDismount': dict(duration=1.45, space='ground', keys=[
        (0., dict(crank=-90., stand=1.)),
        (.22, dict(pelvis=(-.08, -.02, .672), lean=20., foot_L=(-.06, .20, .16), pitch_L=0.)),
        (.48, dict(pelvis=(-.09, .05, .605), foot_L=(-.03, .25, 0.), head=(-12., 6., 0.))),
        (.70, dict(ASTRIDE)),
        (.95, dict(pelvis=(-.16, .20, .600), twist=-6., foot_R=(.03, .06, .40), pitch_R=20., hand_R=(-.04, -.06, .74), frame_R='relaxed', curl_R=.3)),
        (1.18, dict(BESIDE, stand=1.)),
        (1.45, dict()),
    ]),
    'BikeKickstand': dict(duration=1.05, space='ground', keys=[
        (0., dict(BESIDE, stand=1.)),
        (.22, dict(pelvis=(-.30, .37, .608), twist=-24., pelvis_rot=(4., -24., 0.), hand_L=(-.18, .06, .668), frame_L='saddle', curl_L=.25,
                   hand_R=(-.42, .05, .676), frame_R='saddle', foot_L=(-.36, .30, .10), pitch_L=10.)),
        (.36, dict(foot_L='stand', pitch_L=12., pelvis=(-.30, .37, .618))),
        (.60, dict(foot_L='stand', pitch_L=0., pelvis=(-.30, .37, .590), lean=16., lift=.018)),
        (.74, dict(foot_L=(-.33, .40, .06), pitch_L=0., lift=0.)),
        (.88, dict(foot_L=(-.24, .45, 0.), pelvis=(-.27, .37, .612))),
        (1.05, dict()),
    ], stand=[(0., 1.), (.36, 1.), (.60, 0.)]),
    'BikeHop': dict(duration=1.2, space='ground', keys=[
        (0., dict()),
        (.15, dict(pelvis=(-.13, 0., .70), lean=30., head=(-24., 0., 0.))),
        (.30, dict(pelvis=(-.16, 0., .615), lean=40., pelvis_rot=(14., 0., 0.))),
        (.42, dict(pelvis=(-.12, 0., .80), lean=26., pitch=14., lift=.03)),
        (.52, dict(pelvis=(-.10, 0., .92), lean=22., pitch=4., lift=.17)),
        (.62, dict(pelvis=(-.10, 0., .935), pitch=-3., lift=.19)),
        (.74, dict(pelvis=(-.14, 0., .675), lean=30., pitch=0., lift=0.)),
        (.84, dict(pelvis=(-.155, 0., .615), lean=36., pelvis_rot=(12., 0., 0.))),
        (1.02, dict(pelvis=(-.17, 0., .675), lean=27., pelvis_rot=(9., 0., 0.))),
        (1.2, dict(pelvis=(-.185, 0., .685), lean=24., pelvis_rot=(8., 0., 0.), head=(-16., 0., 0.))),
    ], contacts_held=True),
    'BikeSkid': dict(duration=1.25, space='bike', keys=[
        (0., dict(crank=-20.)),
        (.15, dict(crank=0., pelvis=(-.215, 0., .692), lean=12., head=(-22., 0., 0.), pelvis_rot=(2., 0., 0.))),
        (.50, dict(yaw=6., lean_bike=2.)),
        (.62, dict(foot_L=(-.06, .22, .17), pitch_L=0.)),
        (.95, dict(STOP, yaw=28., head=(-14., 12., 0.))),
        (1.25, dict(STOP, yaw=28.)),
    ]),
    'BikeFootDown': dict(duration=2., loop=True, space='bike', keys=[
        (0., dict(STOP)), (1., dict(STOP, lean=17.5, head=(-8., 12., 0.))), (2., dict(STOP))]),
    'BikeBell': dict(duration=.85, space='bike', keys=[
        (0., dict()),
        (.12, dict(grip_slide_R=.030, head=(-10., -10., 0.))),
        (.20, dict(thumb_R=1.)), (.28, dict(thumb_R=0.)), (.38, dict(thumb_R=1.)), (.46, dict(thumb_R=0.)),
        (.62, dict(grip_slide_R=.030, head=(-14., -4., 0.))),
        (.85, dict(grip_slide_R=0., head=(-16., 0., 0.))),
    ]),
    'BikeWave': dict(duration=1.5, space='bike', keys=[
        (0., dict()),
        (.15, dict(hand_L=(.06, .30, .86), frame_L='relaxed', curl_L=.3, side=-2.)),
        (.36, dict(hand_L=(.02, .40, 1.10), frame_L='wave', curl_L=.08, side=-5., head=(-12., 22., 0.), twist=6.)),
        (.50, dict(hand_L=(.08, .40, 1.11))), (.64, dict(hand_L=(-.03, .40, 1.10))), (.78, dict(hand_L=(.08, .40, 1.11))),
        (.92, dict(hand_L=(-.03, .40, 1.10))), (1.04, dict(hand_L=(.04, .40, 1.10))),
        (1.22, dict(hand_L=(.10, .30, .84), frame_L='relaxed', curl_L=.4, side=-1., head=(-15., 6., 0.), twist=0.)),
        (1.38, dict(hand_L='grip', frame_L='grip', curl_L=.85, side=0., head=(-16., 0., 0.))),
        (1.5, dict()),
    ]),
    'BikeCrash': dict(duration=2.2, space='ground', keys=[
        (0., dict(crank=-30.)),
        (.12, dict(pelvis=(-.10, 0., .73), lean=40., head=(-28., 0., 0.), pitch=-8., lift=.01)),
        (.22, dict(hand_L=(.36, .22, .80), hand_R=(.36, -.22, .80), frame_L='reach', frame_R='reach', curl_L=.2, curl_R=.2, pitch=-10., lift=.03)),
        (.30, dict(pelvis=(.30, 0., .95), lean=55., foot_L=(-.04, .14, .46), foot_R=(-.06, -.14, .40), pitch_L=30., pitch_R=30.,
                   hand_L=(.64, .20, .84), hand_R=(.64, -.20, .84), pitch=0., lift=0.)),
        (.45, dict(pelvis=(.62, 0., .80), lean=48., foot_L=(.34, .13, .26), foot_R=(.40, -.13, .20), pitch_L=10., pitch_R=10.)),
        (.58, dict(pelvis=(.85, -.02, .62), lean=35., foot_R=(.86, -.12, 0.), pitch_R=0., foot_L=(.66, .13, .12), hand_L=(.95, .36, .80), hand_R=(1.02, -.34, .70),
                   frame_L='relaxed', frame_R='relaxed', lean_bike=10.)),
        (.72, dict(pelvis=(1.12, .03, .585), lean=28., foot_L=(1.16, .12, 0.), pitch_L=0., hand_L=(1.08, .46, 1.0), hand_R=(1.24, -.42, .92), head=(-12., 0., 6.))),
        (.88, dict(pelvis=(1.38, -.02, .56), lean=26., foot_R=(1.47, -.12, 0.), hand_L=(1.34, .40, .74), hand_R=(1.50, -.36, .86), head=(-8., 0., -4.), lean_bike=40.)),
        # The reference lands him straight into a deep squat, hands braced on his knees, head down.
        (1.05, dict(pelvis=(1.42, .01, .43), lean=34., foot_L=(1.55, .12, 0.), hand_L=(1.63, .15, .34), hand_R=(1.63, -.15, .34),
                    frame_L='saddle', frame_R='saddle', head=(-18., 0., 0.))),
        (1.15, dict(lean_bike=84.)),
        (1.45, dict(pelvis=(1.43, 0., .42), lean=36., hand_L=(1.64, .15, .33), hand_R=(1.64, -.15, .33), head=(-22., 0., 0.))),
        (1.85, dict(pelvis=(1.50, 0., .615), lean=6., hand_L=(1.52, .24, .52), hand_R=(1.52, -.24, .52), frame_L='relaxed', frame_R='relaxed', curl_L=.4, curl_R=.4, head=(0., 0., 0.))),
        (2.2, dict(pelvis=(1.53, 0., .625), lean=2., foot_L=(1.58, .14, 0.), foot_R=(1.53, -.11, 0.))),
    ], stand=[(0., 1.)]),
}

# --------------------------------------------------------------------------------------------- key interpolation

def resolve(keys):
    """Each key's full channel set (unset channels hold from the previous key, the first key starts from DEFAULT)."""
    out, state = [], dict(DEFAULT)
    for t, k in keys:
        state = {**state, **k}; out.append((t, dict(state)))
    return out


def smooth(a, b, s):
    s = s * s * (3 - 2 * s)
    if isinstance(a, (tuple, list)):
        return tuple(x + (y - x) * s for x, y in zip(a, b))
    return a + (b - a) * s


def channels_at(keys, t, extra=None, linear=()):
    """Channels at time t: numbers and points ease between keys (`linear` ones, such as a looping crank, go at a steady
    rate); targets that change mode are blended later."""
    i = max(j for j, (kt, _) in enumerate(keys) if kt <= t + 1e-9)
    t0, a = keys[i]
    if i == len(keys) - 1:
        c = dict(a); c.update({name: track_at(track, t) for name, track in (extra or {}).items()})
        return c, (a, a), 0.
    t1, b = keys[i + 1]; s = (t - t0) / (t1 - t0)
    c = {}
    for name, v in a.items():
        w = b[name]
        if name in linear: c[name] = v + (w - v) * s
        elif isinstance(v, (int, float)) and isinstance(w, (int, float)): c[name] = smooth(v, w, s)
        elif isinstance(v, tuple) and isinstance(w, tuple) and not isinstance(v[0], str) and not isinstance(w[0], str): c[name] = smooth(v, w, s)
        else: c[name] = v if s < 1 else w
    if extra:
        for name, track in extra.items():
            c[name] = track_at(track, t)
    return c, (a, b), s


def track_at(track, t):
    if t <= track[0][0]: return track[0][1]
    for (t0, v0), (t1, v1) in zip(track, track[1:]):
        if t <= t1: return smooth(v0, v1, (t - t0) / (t1 - t0))
    return track[-1][1]

# ------------------------------------------------------------------------------------------------------- the rig solve

class Rig:
    """Forward kinematics on the rest skeleton in armature space; pose matrices are set bone by bone, parent first."""
    def __init__(self, arm):
        self.arm, self.M = arm, arm.matrix_world.copy(); self.Mi = self.M.inverted()
        self.scale = self.M.to_scale().x
        self.rest = {b.name: b.matrix_local.copy() for b in arm.data.bones}
        self.parent = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        self.order = [b.name for b in arm.data.bones]   # parents come before children
        self.rel = {n: (self.rest[p].inverted() @ self.rest[n] if p else self.rest[n]) for n, p in self.parent.items()}
        self.length = lambda a, b: (self.rest[b].translation - self.rest[a].translation).length
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
        axis, sign = self.hinge[bone]
        if axis == 2:
            z = n * sign; x = y.cross(z)
        else:
            x = n * sign; z = x.cross(y)
        return Matrix((x.normalized(), y.normalized(), z.normalized())).transposed()

    def two_bone(self, upper, lower, end, target_arm, pole_arm, end_rot):
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
        self.place(lower, Matrix.Translation(self.head(lower)) @ self.aimed(lower, y2, n).to_4x4())
        self.place(end, Matrix.Translation(self.head(end)) @ end_rot.to_4x4())
        return (d.length - D) * self.scale   # metres short of the target (0 when reached)


def rest_world_rot(rig, bone):
    return rig.rest[bone].to_3x3().normalized()


class Hands:
    """Hand frames: fingers direction f and palm direction p, with the knuckle line k = s (p x f) (s = +1 left)."""
    def __init__(self, rig):
        self.rig = rig; self.rest = {}
        for side in 'LR':
            R = rest_world_rot(rig, 'hand_' + side); f = R.col[1].normalized()
            p = Vector((0, 0, -1)); p = (p - f * p.dot(f)).normalized()
            self.rest[side] = (f, p)
        h = rig.rest['finger_1_L'].translation - rig.rest['hand_L'].translation
        self.palm = h.length * rig.scale   # wrist to the knuckles, metres

    @staticmethod
    def basis(side, f, p):
        k = SIDE[side] * p.cross(f)
        return Matrix((k.normalized(), f.normalized(), p.normalized())).transposed()

    def frame(self, side, name, c, B):
        """World rotation that takes the rest hand to the named hand frame."""
        s = SIDE[side]; B3 = B.to_3x3()
        if name == 'grip':
            # Knuckles along the grip, index toward its inner end; back of the hand up and out, palm round the grip.
            k = (B3 @ steer_matrix(c).to_3x3() @ GRIP_AXIS[side]).normalized()
            back = B3 @ Vector((0, s * .83, .55)); back = (back - k * back.dot(k)).normalized()
            p = -back; f = s * k.cross(p)
        elif name == 'saddle':   # palm down on the saddle, fingers forward
            f, p = B3 @ Vector((1, 0, -.15)), B3 @ Vector((0, 0, -1))
        elif name == 'reach':    # arms thrown forward to break a fall
            f, p = Vector((1, 0, -.6)), Vector((.3, 0, -1))
        elif name == 'wave':     # fingers up, palm forward and a little out
            f, p = Vector((0, 0, 1)), Vector((1, s * .3, 0))
        else:                    # relaxed: fingers down and forward, palm in
            f, p = Vector((.35, 0, -1)), Vector((0, -s, 0))
        f = f.normalized(); p = (p - f * p.dot(f)).normalized()
        f0, p0 = self.rest[side]
        return self.basis(side, f, p) @ self.basis(side, f0, p0).inverted()

    def wrist_for_grip(self, side, centre, D):
        f0, p0 = self.rest[side]
        f, p = D @ f0, D @ p0
        return centre - f * self.palm * .80 - p * .024


def ease(s):
    return s * s * (3 - 2 * s)


def solve(rig, hands, c, a_b, s, space):
    """Pose the rig for one frame's channels. `a_b` are the surrounding keys and `s` the fraction between them: limb
    targets, hand frames and foot pitch blend from one key's kind of target to the next's (a grip to a point, say).
    Returns how far each limb fell short of its target (metres)."""
    B = bike_matrix(c); a, b = a_b; e = ease(s)
    carry = (lambda v: B @ Vector(v)) if space == 'bike' else (lambda v: Vector(v))
    turn = B.to_3x3() if space == 'bike' else Matrix.Identity(3)
    def point(value, side):
        if isinstance(value, str):
            return B @ {'grip': grip_point, 'pedal': pedal_point}[value](c, side) if value != 'stand' else B @ stand_point(c)
        if value[0] == GROUND_SPACE: return Vector(value[1:])
        return carry(value)
    rig.begin()
    rig.local('root')
    R_pelvis = turn @ rot(*c['pelvis_rot']) @ rest_world_rot(rig, 'pelvis')
    rig.place('pelvis', Matrix.Translation(rig.to_arm(carry(c['pelvis']))) @ R_pelvis.to_4x4())
    for bone, share in (('spine', .34), ('spine_mid', .33), ('chest', .33)):
        rig.local(bone, rot((c['lean'] - c['pelvis_rot'][0] * .5) * share, c['twist'] * share, c['side'] * share))
    hp, hy, hr = c['head']
    rig.local('neck', rot(hp * .4, hy * .4, hr * .4)); rig.local('head', rot(hp * .6, hy * .6, hr * .6))
    short = {}
    for side in 'LR':
        sgn = SIDE[side]
        rig.local('clavicle_' + side, rot(0, 0, -sgn * c['shrug']))
        Da, Db = hands.frame(side, a['frame_' + side], c, B), hands.frame(side, b['frame_' + side], c, B)
        D = Da.to_quaternion().slerp(Db.to_quaternion(), e).to_matrix()
        def wrist(v, Dk):
            if v == 'grip': return hands.wrist_for_grip(side, B @ grip_point(c, side), Dk)
            return point(v, side)
        w = wrist(a['hand_' + side], Da).lerp(wrist(b['hand_' + side], Db), e)
        pole = turn @ Vector((-.55, sgn * .75, -.45))
        short['hand_' + side] = rig.two_bone('upperarm_' + side, 'forearm_' + side, 'hand_' + side, rig.to_arm(w), pole,
                                             D @ rest_world_rot(rig, 'hand_' + side))
        # Foot: the sole under the ball on its target, pitched toe down; on a pedal it ankles with the crank.
        def pitch(key):
            if key['pitch_' + side] is not None: return key['pitch_' + side]
            ang = math.radians(c['crank']) + (0 if side == 'R' else math.pi)
            return 9 - 9 * math.sin(ang)
        def carried(key):
            return isinstance(key['foot_' + side], str) or (space == 'bike' and key['foot_' + side][0] != GROUND_SPACE)
        Ra = (turn if carried(a) else Matrix.Identity(3)) @ rot(pitch(a))
        Rb = (turn if carried(b) else Matrix.Identity(3)) @ rot(pitch(b))
        Rf = Ra.to_quaternion().slerp(Rb.to_quaternion(), e).to_matrix()
        sole = point(a['foot_' + side], side).lerp(point(b['foot_' + side], side), e)
        ankle = sole + Rf @ FOOT_OFFSET[side]
        knee = turn @ Vector((1, sgn * .30, .15))
        short['foot_' + side] = rig.two_bone('thigh_' + side, 'shin_' + side, 'foot_' + side, rig.to_arm(ankle), knee,
                                             Rf @ rest_world_rot(rig, 'foot_' + side))
        rig.local('toe_' + side)
        fingers(rig, side, c['curl_' + side], c['thumb_R'] if side == 'R' else 0.)
    return short


FOOT_OFFSET = {}


def fingers(rig, side, curl, flick):
    """Curl the fingers toward the palm (rest palm faces down) and the thumb across; `flick` straightens the thumb."""
    palm = Vector((0, 0, -1))
    for i, gain in ((0, 1.), (1, 1.), (2, 1.05), (3, 1.1)):
        for bone, amount in ((f'finger_{i}_{side}', 62), (f'finger_tip_{i}_{side}', 78), (f'finger_end_{i}_{side}', 52)):
            y = rest_world_rot(rig, bone).col[1].normalized()
            rig.local(bone, Matrix.Rotation(math.radians(amount * curl * gain), 3, y.cross(palm).normalized()))
    for bone, amount in ((f'thumb_{side}', 28), (f'thumb_tip_{side}', 34), (f'thumb_end_{side}', 26)):
        y = rest_world_rot(rig, bone).col[1].normalized()
        rig.local(bone, Matrix.Rotation(math.radians(amount * curl * (1 - flick) - 20 * flick), 3, y.cross(palm).normalized()))
    for bone in [n for n in rig.order if n.endswith('_' + side) and n not in rig.pose and ('finger' in n or 'thumb' in n)]:
        rig.local(bone)

# ------------------------------------------------------------------------------------------------------------ baking

def bake(rig, hands, name, clip):
    keys = resolve(clip['keys']); frames = round(clip['duration'] * FPS) + (0 if clip.get('loop') else 1)
    extra = {k: clip[k] for k in ('stand',) if k in clip}
    poses, bike, worst = [], [], {}
    for f in range(frames):
        t = f / FPS
        c, a_b, s = channels_at(keys, t, extra, clip.get('linear', ()))
        short = solve(rig, hands, c, a_b, s, clip['space'])
        for limb, v in short.items(): worst[limb] = max(worst.get(limb, 0.), v)
        poses.append({n: rig.basis[n].copy() for n in rig.order})
        bike.append([round(c[k], 4) for k in ('crank', 'stand', 'lift', 'pitch', 'lean_bike', 'yaw', 'steer')])
    # Contact windows: a limb is pinned while both surrounding keys hold its grip, pedal or stand.
    contacts = {}
    full = keys
    for limb in ('hand_L', 'hand_R', 'foot_L', 'foot_R'):
        spans = []
        for (t0, a), (t1, b) in zip(full, full[1:] + [(clip['duration'], full[-1][1])]):
            if isinstance(a[limb], str) and a[limb] == (b[limb] if t1 > t0 else a[limb]):
                if spans and abs(spans[-1][1] - t0) < 1e-6: spans[-1][1] = t1
                else: spans.append([t0, t1])
        contacts[limb] = [[round(x, 3) for x in span] for span in spans if span[1] > span[0]]
    last = keys[-1][1]
    end = None
    if clip['space'] == 'ground' and isinstance(last['foot_L'], tuple) and isinstance(last['foot_R'], tuple):
        rest_pelvis = rig.world(rig.rest['pelvis'].translation)
        end = [round(last['pelvis'][0] - rest_pelvis.x, 4), round(last['pelvis'][1] - rest_pelvis.y, 4)]
    return poses, {'frames': frames, 'duration': clip['duration'], 'loop': bool(clip.get('loop')), 'contacts': contacts,
                   'bike_channels': ['crank', 'stand', 'lift', 'pitch', 'lean', 'yaw', 'steer'], 'bike': bike,
                   'end_offset': end, 'reach_error_cm': {k: round(v * 100, 2) for k, v in worst.items()}}


def write_action(rig, name, poses):
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

# ----------------------------------------------------------------------------------------------------- review renders

def load_bike():
    """Append the bike's parts and assemble them with the bike build's own layout (Bike.blend keeps each part at
    its pivot-local origin)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('bike_model', HERE / 'build.py')
    model = importlib.util.module_from_spec(spec); spec.loader.exec_module(model)
    with bpy.data.libraries.load(str(BIKE / 'Bike.blend'), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith('BK_') and n != 'BK_Pedal.L']
    parts = {}
    for ob in dst.objects:
        bpy.context.scene.collection.objects.link(ob); parts[ob.name] = ob
    model.assemble(parts, MANIFEST)
    parts['BK_Pedal.L'] = bpy.data.objects['BK_Pedal.L']
    return parts, {n: ob.matrix_world.copy() for n, ob in parts.items()}


REST_CRANK = -44.   # Bike.blend is assembled with the right crank forward-down at this angle


def pose_bike(parts, base, c):
    """Pose the review copy of the bike from a frame's channels, as the game will."""
    B, S = bike_matrix(c), steer_matrix(c)
    about = lambda at, R: Matrix.Translation(at) @ R @ Matrix.Translation(-at)
    for name, ob in parts.items():
        M = base[name]
        if name in ('BK_Steer', 'BK_WheelFront'): M = S @ M
        elif name == 'BK_Kickstand': M = about(STAND, Matrix.Rotation(STOWED * c['stand'], 4, 'Y')) @ M
        elif name == 'BK_Crank': M = about(BB, Matrix.Rotation(-math.radians(c['crank'] - REST_CRANK), 4, 'Y')) @ M
        elif name.startswith('BK_Pedal'):
            side = 'L' if name.endswith('.L') else 'R'
            a = math.radians(c['crank']) + (math.pi if side == 'L' else 0)
            p = BB + Vector((CRANK * math.cos(a), SIDE[side] * MANIFEST['pedal_offset_y'], CRANK * math.sin(a)))
            M = Matrix.Translation(p) @ M.to_quaternion().to_matrix().to_4x4()
        ob.matrix_world = B @ M


def studio(scene):
    scene.render.engine = 'BLENDER_EEVEE'; scene.view_settings.view_transform = 'Standard'
    scene.eevee.taa_render_samples = 32
    world = bpy.data.worlds.new('Studio'); scene.world = world; world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.80, .80, .78, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .9
    sun = bpy.data.objects.new('Key', bpy.data.lights.new('Key', 'SUN')); scene.collection.objects.link(sun)
    sun.data.energy = 3.4; sun.data.angle = math.radians(30); sun.rotation_euler = (math.radians(48), 0, math.radians(-40))
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


def render_clip(scene, cam, parts, base, rig, hands, name, clip, out, count=7):
    keys = resolve(clip['keys']); extra = {k: clip[k] for k in ('stand',) if k in clip}
    arm = rig.arm
    centre = Vector((.85 if name == 'BikeCrash' else -.05, 0, .62)); wide = name == 'BikeCrash'
    for i in range(count):
        t = clip['duration'] * i / (count - 1) if not clip.get('loop') else clip['duration'] * i / count
        f = min(round(t * FPS), round(clip['duration'] * FPS) - (1 if clip.get('loop') else 0))
        scene.frame_set(f)
        c, a_b, s = channels_at(keys, f / FPS, extra, clip.get('linear', ()))
        pose_bike(parts, base, c)
        for view, eye in (('side', centre + Vector((0, -4.2, .25))), ('q34', centre + Vector((2.3, 2.7, 1.0)))):
            look(cam, eye, centre, lens=(60 if wide else 78) if view == 'side' else (48 if wide else 62))
            scene.render.filepath = str(out / f'{name}_{view}_{i}.png'); bpy.ops.render.render(write_still=True)


def character(name):
    """The character's export module (its prepare, SOURCE and FBX) and its bike output folder."""
    if name == 'cairo':
        return cairo, OUT
    import importlib.util
    folder = HERE.parents[1] / 'characters' / name
    spec = importlib.util.spec_from_file_location(f'{name.replace("-", "_")}_export', folder / 'export_unreal.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.OUT / 'bike'


def main(args):
    global OUT
    module, OUT = character(args.character)
    prepared = module.prepare(module.SOURCE)
    scene, arm = prepared.scene, prepared.arm
    scene.render.fps, scene.render.fps_base = FPS, 1
    for pb in arm.pose.bones: pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    rig = Rig(arm); hands = Hands(rig)
    for side in 'LR':
        ankle, toe = rig.world(rig.rest['foot_' + side].translation), rig.world(rig.rest['toe_' + side].translation)
        FOOT_OFFSET[side] = Vector((ankle.x - toe.x, 0, ankle.z))   # ankle from the sole under the ball, standing
    wanted = set(args.clips.split(',')) if args.clips else set(CLIPS)
    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    report = {'source_sha256': prepared.record['native_sha256'], 'fps': FPS, 'bike_manifest': str(BIKE / 'manifest.json'), 'clips': {}}
    actions = {}
    for name, clip in CLIPS.items():
        if name not in wanted: continue
        poses, info = bake(rig, hands, name, clip)
        action = write_action(rig, 'Bike · ' + name, poses); actions[name] = action
        scene.frame_start, scene.frame_end = 0, info['frames'] - 1
        scene.frame_set(0)
        bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.fbx(filepath=str(OUT / 'fbx' / f'A_{name}.fbx'), object_types={'ARMATURE'}, bake_anim=True, **module.FBX)
        report['clips'][name] = info
        print(args.character.upper(), 'BIKE CLIP', name, info['frames'], json.dumps(info['reach_error_cm']), flush=True)
    (OUT / ('export.json' if wanted == set(CLIPS) else 'export-partial.json')).write_text(json.dumps(report, indent=1) + '\n')
    if args.review or args.frames:
        cam = studio(scene); parts, base = load_bike()
        if args.review:
            out = Path(args.review); out.mkdir(parents=True, exist_ok=True)
            scene.render.resolution_x, scene.render.resolution_y = 640, 480
            for name, action in actions.items():
                arm.animation_data.action = action
                if arm.animation_data.action_slot is None: arm.animation_data.action_slot = action.slots[0]
                render_clip(scene, cam, parts, base, rig, hands, name, CLIPS[name], out)
        if args.frames:
            out = Path(args.frames); out.mkdir(parents=True, exist_ok=True)
            scene.render.resolution_x = scene.render.resolution_y = 768
            for name, frame, eye in (('beside', ('BikeMount', 0), (1.9, 2.5, 1.15)), ('riding', ('BikeRide', 0), (2.3, -2.6, 1.2))):
                action = actions[frame[0]]; arm.animation_data.action = action
                if arm.animation_data.action_slot is None: arm.animation_data.action_slot = action.slots[0]
                scene.frame_set(frame[1])
                c, _, _ = channels_at(resolve(CLIPS[frame[0]]['keys']), frame[1] / FPS, {k: CLIPS[frame[0]][k] for k in ('stand',) if k in CLIPS[frame[0]]})
                pose_bike(parts, base, c)
                look(cam, eye, (-.05, 0, .58), lens=40)
                scene.render.filepath = str(out / f'start_{name}.png'); bpy.ops.render.render(write_still=True)
    print(f'{args.character.upper()} BIKE EXPORT COMPLETE: {len(report["clips"])} clips', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--clips', help='comma-separated clip names (default: all)')
    parser.add_argument('--review', help='render key moments of each clip into this folder')
    parser.add_argument('--frames', help='render the video references\' starting frames into this folder')
    parser.add_argument('--character', default='cairo', help='the playable character folder to author on (cairo, modori)')
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
