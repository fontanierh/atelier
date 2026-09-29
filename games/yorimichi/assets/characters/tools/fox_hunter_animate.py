"""Author the fox hunter's animation set on the frozen rig (tripo-rig-r02). Revision 3, after two fifteen-reviewer
passes (animation-r01/reviews, animation-r02/reviews).

blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_animate.py -- [--rev animation-r03] [--only Idle,Run] [--no-sheets] [--no-export]

Pose language. Everything is written in the character's own frame (+X forward, +Y his left, +Z up), which turns
with the Root bone (yaw and tilt), so a 'Y' rotation is always a pitch about his own left-right axis.
  bone: [(axis, deg), ...]          rotations applied first-listed-first ON TOP of the parent's posed orientation.
  bone: {'aim': (x, y, z), 'twist': d}  turn the bone from wherever its parent leaves it to point along that
                                    direction, then roll about it. arm_rot(side, elev, az, twist) builds this:
                                    elev = degrees below horizontal (90 hanging, 0 level, negative raised),
                                    az = degrees from straight sideways toward forward (90 forward, >90 across the
                                    body, negative backward), twist = roll (90 with a hanging arm = palm to the thigh).
  ForeArm: {'flex': d, 'roll': r}   elbow flexion about the true hinge (arm direction x palm normal), positive
                                    brings the hand toward the palm side; then roll = forearm pronation about its
                                    own axis, positive turns the palm toward the body on both sides. Keep the
                                    upper-arm twist small (hinge lateral, forearm folds forward) and use roll for
                                    the palm, or the forearm folds across the chest.
  Foot: {'world': [(axis, deg), ...]} absolute orientation in the character frame, whatever the leg does.
  hips / root: (x, y, z)            hips offset (character frame) and root travel (world); root_rot yaw degrees
                                    (+ toward his left), root_tilt pitch degrees (+ face down).
  plant: {'Left': target, ...}      solve that leg (thigh aim, knee, flat foot) so the ankle sits on the target:
                                    'hold' = where it was at the previous key; 'ready' = its READY spot;
                                    ('ready', dx, dy) = offset from that; ('world', x, y) = a fixed spot on the
                                    floor; (x, y, z) = character frame. Targets are the ball of the foot. Optional
                                    plant_pitch: {'Left': deg} keeps the ball down with the heel raised.
  support: 'Left'|'Right'           ground the hips on that foot's soles (loops); free: True = airborne, no solve.
Mirrored clips are reflections (sides swapped, y flipped); the solve runs after mirroring on the actual rig.
After keying, a per-frame pass pins the planted foot between keys and lifts the hips wherever a sole would sink,
so the contacts hold through the interpolation too. manifest.json carries numeric checks per clip.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, base64, json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fox_hunter_clip

ap = argparse.ArgumentParser()
ap.add_argument('--rev', default='animation-r03')
ap.add_argument('--only', default='')
ap.add_argument('--no-sheets', action='store_true')
ap.add_argument('--no-export', action='store_true')
ap.add_argument('--texture-size', type=int, default=2048)
ap.add_argument('--dump', default='')
ap.add_argument('--no-bake', action='store_true')
ap.add_argument('--check', action='store_true', help='run the mesh self-intersection check on every clip (slow)')
ap.add_argument('--check-step', type=int, default=2)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-fox-hunter-2026-09-13'
RIG = ASSET / 'tripo-rig-r02/blender/FoxHunter-Rig-r02.blend'
OUT = ASSET / a.rev; OUT.mkdir(parents=True, exist_ok=True)
NAME = 'FoxHunter-Anim-' + a.rev.split('-')[-1]
FPS = 30

bpy.ops.wm.open_mainfile(filepath=str(RIG))
sc = bpy.context.scene; sc.render.fps = FPS
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
body = next(o for o in sc.objects if o.type == 'MESH' and o.vertex_groups)
arm.animation_data.action = None
for tr in list(arm.animation_data.nla_tracks):
    arm.animation_data.nla_tracks.remove(tr)
H = body.dimensions.z
U = H / 0.92
REST = {pb.name: pb.bone.matrix_local.to_3x3() for pb in arm.pose.bones}
ORDER = []
def _walk(b):
    ORDER.append(b.name)
    for c in b.children: _walk(c)
for b in arm.data.bones:
    if b.parent is None: _walk(b)
FINGER = [n for n in ORDER if any(f in n for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'))]
BODY_BONES = [n for n in ORDER if n not in FINGER]
PARENT = {pb.name: (pb.parent.name if pb.parent else None) for pb in arm.pose.bones}
HANDS = {'Left': arm.pose.bones['mixamorig:LeftHand'], 'Right': arm.pose.bones['mixamorig:RightHand']}
PROPS = ['thumb_curl', 'index_curl', 'middle_curl', 'ring_curl', 'pinky_curl', 'thumb_opposition', 'finger_spread']
SOLES = {'Left': ['mixamorig:LeftFoot', 'mixamorig:LeftToeBase'], 'Right': ['mixamorig:RightFoot', 'mixamorig:RightToeBase']}
SOLE_BONES = SOLES['Left'] + SOLES['Right']
MW = arm.matrix_world
def mx(name): return arm.pose.bones[name].bone.matrix_local
LEG_LEN = {s: (mx(f'mixamorig:{s}Leg').translation - mx(f'mixamorig:{s}UpLeg').translation).length for s in ('Left', 'Right')}
SHANK_LEN = {s: (mx(f'mixamorig:{s}Foot').translation - mx(f'mixamorig:{s}Leg').translation).length for s in ('Left', 'Right')}
FOOT_LEN = {s: (mx(f'mixamorig:{s}ToeBase').translation - mx(f'mixamorig:{s}Foot').translation).length for s in ('Left', 'Right')}

# ---------------------------------------------------------------- pose language -----------------------------
def R(axis, deg):
    if isinstance(axis, str):
        return Matrix.Rotation(math.radians(deg), 3, axis)
    return Matrix.Rotation(math.radians(deg), 3, Vector(axis).normalized())

def short(name): return name.replace('mixamorig:', '')

def arm_rot(side, elev=70, az=25, twist=90):
    sgn = 1 if side == 'Left' else -1
    e, z = math.radians(elev), math.radians(az)
    d = (math.cos(e) * math.sin(z), sgn * math.cos(e) * math.cos(z), -math.sin(e))
    return {'aim': d, 'twist': twist * sgn}

def _mirror_rots(rots):
    rr = []
    for axis, deg in rots:
        if isinstance(axis, str): rr.append((axis, deg if axis == 'Y' else -deg))
        else: rr.append(((axis[0], -axis[1], axis[2]), -deg))
    return rr

def _mirror_target(t):
    if isinstance(t, str): return t
    if isinstance(t, tuple) and t and t[0] == 'hold': return t
    if isinstance(t, tuple) and t and t[0] in ('ready', 'world'): return (t[0], t[1], -t[2]) + tuple(t[3:])
    return (t[0], -t[1], t[2])

def mirror_pose(pose):
    out = {}
    for k, v in pose.items():
        if k in ('hips', 'root'): out[k] = (v[0], -v[1], v[2]); continue
        if k == 'root_rot': out[k] = -v; continue
        if k in ('root_tilt', 'free', 'lift', 'nofloor'): out[k] = v; continue
        if k == 'support': out[k] = 'Right' if v == 'Left' else 'Left'; continue
        if k in ('hands', 'plant', 'plant_pitch'):
            out[k] = {('Right' if s == 'Left' else 'Left'): (_mirror_target(d) if k == 'plant' else d) for s, d in v.items()}; continue
        mk = k.replace('Left', 'TMP').replace('Right', 'Left').replace('TMP', 'Right')
        if isinstance(v, dict):
            d = dict(v)
            if 'aim' in d: d['aim'] = (v['aim'][0], -v['aim'][1], v['aim'][2]); d['twist'] = -v.get('twist', 0)
            if 'extra' in d: d['extra'] = _mirror_rots(v['extra'])
            if 'world' in d: d['world'] = _mirror_rots(v['world'])
            out[mk] = d; continue
        out[mk] = _mirror_rots(v)
    return out

def merge(*poses):
    out = {}
    for p in poses:
        for k, v in p.items():
            if k in ('hands', 'plant', 'plant_pitch'):
                out.setdefault(k, {})
                if k == 'hands':
                    for s, d in v.items(): out[k].setdefault(s, {}).update(d)
                else:
                    out[k].update(v)
            else:
                out[k] = v
    return out

def hands(curl=0.35, spread=0.15, thumb=0.25, opp=0.25):
    d = {'index_curl': curl, 'middle_curl': curl, 'ring_curl': curl, 'pinky_curl': curl, 'thumb_curl': thumb, 'thumb_opposition': opp, 'finger_spread': spread}
    return {'hands': {'Left': dict(d), 'Right': dict(d)}}

def arms(elev=70, az=25, twist=0, flex=50, roll=70, left=None, right=None):
    L = dict(elev=elev, az=az, twist=twist, flex=flex, roll=roll); Rr = dict(L)
    if left: L.update(left)
    if right: Rr.update(right)
    return {'LeftArm': arm_rot('Left', L['elev'], L['az'], L['twist']), 'LeftForeArm': {'flex': L['flex'], 'roll': L['roll']},
            'RightArm': arm_rot('Right', Rr['elev'], Rr['az'], Rr['twist']), 'RightForeArm': {'flex': Rr['flex'], 'roll': Rr['roll']}}

def one_arm(side, elev, az, twist=0, flex=50, roll=70):
    return {side + 'Arm': arm_rot(side, elev, az, twist), side + 'ForeArm': {'flex': flex, 'roll': roll}}

def legs(l_thigh=-18, l_knee=32, l_foot=-14, r_thigh=None, r_knee=None, r_foot=None, l_out=0, r_out=0):
    """Thigh pitch (negative = forward), knee flex, foot pitch (negative = toes up), optional thigh yaw out."""
    r_thigh = l_thigh if r_thigh is None else r_thigh; r_knee = l_knee if r_knee is None else r_knee; r_foot = l_foot if r_foot is None else r_foot
    return {'LeftUpLeg': [('Y', l_thigh), ('Z', l_out), ('X', 7)], 'LeftLeg': [('Y', l_knee)], 'LeftFoot': [('Y', l_foot), ('X', -7)],
            'RightUpLeg': [('Y', r_thigh), ('Z', -r_out), ('X', -7)], 'RightLeg': [('Y', r_knee)], 'RightFoot': [('Y', r_foot), ('X', 7)]}

def plant(left=None, right=None, l_pitch=None, r_pitch=None):
    p = {'plant': {}}
    if left is not None: p['plant']['Left'] = left
    if right is not None: p['plant']['Right'] = right
    pp = {}
    if l_pitch is not None: pp['Left'] = l_pitch
    if r_pitch is not None: pp['Right'] = r_pitch
    if pp: p['plant_pitch'] = pp
    return p

BOTH = plant('hold', 'hold')

READY = merge({
    'Spine': [('Y', 14)], 'Spine1': [('Y', 8)], 'Spine2': [('Y', 4)], 'Neck': [('Y', -18)], 'Head': [('Y', -8)],
    'hips': (0, 0, -0.045),
}, legs(-18, 32, -14), arms(elev=66, az=22, twist=0, flex=48, roll=75), hands(0.35, 0.2))

WORLD = {}
LASTQ = {}
B = Matrix.Identity(3)

def apply_raw(pose):
    """Set the rig from a (post-mirror, post-solve) pose."""
    global WORLD, B
    WORLD = {}
    for name in BODY_BONES:
        pb = arm.pose.bones[name]
        pb.rotation_mode = 'QUATERNION'
        pb.location = Vector((0, 0, 0))
        M = REST[name]
        Wp = WORLD.get(PARENT[name], Matrix.Identity(3))
        spec = pose.get(short(name))
        if name == 'Root':
            Rw = R('Y', pose.get('root_tilt', 0)) @ R('Z', pose.get('root_rot', 0))
            B = Rw
        elif isinstance(spec, dict) and 'flex' in spec:
            side = 'Left' if 'Left' in name else 'Right'
            up = 'mixamorig:' + side + 'Arm'
            arm_dir = (WORLD[up] @ REST[up] @ Vector((0, 1, 0))).normalized()
            palm_n = (WORLD[up] @ Vector((1, 0, 0))).normalized()
            hinge = arm_dir.cross(palm_n)
            if hinge.length < 1e-6: hinge = Vector((0, 0, 1))
            Rw = R((hinge.x, hinge.y, hinge.z), spec.get('flex', 0))
            if spec.get('roll'):
                fdir = (Rw @ Wp @ M @ Vector((0, 1, 0))).normalized()
                Rw = R((fdir.x, fdir.y, fdir.z), spec['roll'] * (1 if side == 'Left' else -1)) @ Rw
            for axis, deg in spec.get('extra', []):
                Rw = B @ R(axis, deg) @ B.inverted() @ Rw
        elif isinstance(spec, dict) and 'aim' in spec:
            u = (Wp @ M @ Vector((0, 1, 0))).normalized()
            d = (B @ Vector(spec['aim'])).normalized()
            Rw = u.rotation_difference(d).to_matrix()
            # canonical roll: the bone's palm/knee axis (rest +X) faces forward relative to a lateral hinge, whatever
            # direction the bone points, so twist means the same thing for a hanging, forward or raised limb
            sgn = 1 if 'Left' in name else -1
            lat = B @ Vector((0, sgn, 0)); fwd = B @ Vector((1, 0, 0))
            h = lat - lat.dot(d) * d
            if h.length < 0.3: h = fwd - fwd.dot(d) * d
            h.normalize()
            p_star = d.cross(h) * sgn
            p_cur = Rw @ Wp @ Vector((1, 0, 0)); p_cur = (p_cur - p_cur.dot(d) * d).normalized()
            ang = math.degrees(math.atan2(p_cur.cross(p_star).dot(d), p_cur.dot(p_star)))
            Rw = R((d.x, d.y, d.z), ang + spec.get('twist', 0)) @ Rw
        elif isinstance(spec, dict) and 'world' in spec:
            Rt = Matrix.Identity(3)
            for axis, deg in spec['world']:
                Rt = R(axis, deg) @ Rt
            Rw = B @ Rt @ Wp.inverted()     # rest orientation turned by Rt in the character frame, then by the root
        else:
            Rw = Matrix.Identity(3)
            for axis, deg in (spec or []):
                Rw = R(axis, deg) @ Rw
            Rw = B @ Rw @ B.inverted()
        WORLD[name] = Rw @ Wp
        q = (M.inverted() @ Wp.inverted() @ Rw @ Wp @ M).to_quaternion()
        prev = LASTQ.get(name)
        if prev is not None and q.dot(prev) < 0: q.negate()
        LASTQ[name] = q
        pb.rotation_quaternion = q
    arm.pose.bones['mixamorig:Hips'].location = REST['mixamorig:Hips'].inverted() @ Vector(pose.get('hips', (0, 0, 0)))
    arm.pose.bones['Root'].location = REST['Root'].inverted() @ Vector(pose.get('root', (0, 0, 0)))
    for side, hb in HANDS.items():
        vals = pose.get('hands', {}).get(side, {})
        for p in PROPS: hb[p] = float(vals.get(p, 0.0))
    bpy.context.view_layer.update()

def root_pos():
    return MW @ arm.pose.bones['Root'].head

def to_char(w):
    """World point to the character frame (relative to the Root, turned with it)."""
    return B.inverted() @ (w - root_pos())

def sole_pen(sides=('Left', 'Right')):
    """Most negative sole clearance (each sole bone against its own rest height)."""
    return min((MW @ arm.pose.bones[n].tail).z - SOLE_Z[n] for s in sides for n in SOLES[s])

apply_raw({})
SOLE_Z = {n: (MW @ arm.pose.bones[n].tail).z for n in SOLE_BONES}
FLOOR = min(SOLE_Z.values())
BALL_Z = {s: SOLE_Z[f'mixamorig:{s}Foot'] - root_pos().z for s in ('Left', 'Right')}   # ball on its own floor
ANKLE_READY = {}   # READY ball spots (character frame), kept under the old name
apply_raw(READY)
for s in ('Left', 'Right'):
    c = to_char(MW @ arm.pose.bones[f'mixamorig:{s}Foot'].tail)
    ANKLE_READY[s] = Vector((c.x, c.y, BALL_Z[s]))
TOE_LEN = {s: arm.pose.bones[f'mixamorig:{s}ToeBase'].bone.length for s in ('Left', 'Right')}
LAST_ANKLE = {}  # world ankle positions after the previous key

def char_to_world(c):
    return root_pos() + B @ Vector(c)

def solve_leg(pose, side, target_world, pitch=0.0, iters=3):
    """Aim the thigh, flex the knee and set the foot so the BALL of the foot sits on the world target. pitch > 0
    raises the heel (ball down, toes flat); pitch < 0 is a heel strike (heel down, ball lifted)."""
    sg = 1 if side == 'Left' else -1
    L1, L2 = LEG_LEN[side], SHANK_LEN[side]
    pose[f'{side}Foot'] = {'world': [('Y', pitch), ('X', -7 * sg)]}
    pose[f'{side}ToeBase'] = {'world': [('Y', min(0.0, pitch)), ('X', -7 * sg)]}
    apply_raw(pose)
    ball = Vector(target_world) + Vector((0, 0, 1.2 * FOOT_LEN[side] * math.sin(math.radians(max(0.0, -pitch)))))
    foot_vec = (MW @ arm.pose.bones[f'mixamorig:{side}Foot'].tail) - (MW @ arm.pose.bones[f'mixamorig:{side}Foot'].head)
    goal = to_char(ball - foot_vec)
    aim_at = Vector(goal)
    for _ in range(iters):
        apply_raw(pose)
        foot_vec = (MW @ arm.pose.bones[f'mixamorig:{side}Foot'].tail) - (MW @ arm.pose.bones[f'mixamorig:{side}Foot'].head)
        goal = to_char(ball - foot_vec)
        h = to_char(MW @ arm.pose.bones[f'mixamorig:{side}UpLeg'].head)
        v = aim_at - h; d = max(1e-4, min(v.length, L1 + L2 - 1e-3)); u = v.normalized()
        k = 180 - math.degrees(math.acos(max(-1, min(1, (L1 * L1 + L2 * L2 - d * d) / (2 * L1 * L2)))))
        al = math.degrees(math.acos(max(-1, min(1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)))))
        hinge = u.cross(Vector((1, 0, 0)))
        if hinge.length < 1e-6: hinge = Vector((0, -1, 0))
        hinge.normalize()
        t = R((hinge.x, hinge.y, hinge.z), al) @ u
        pose[f'{side}UpLeg'] = {'aim': (t.x, t.y, t.z), 'twist': 0}
        pose[f'{side}Leg'] = [((-hinge.x, -hinge.y, -hinge.z), k)]
        apply_raw(pose)
        got = to_char(MW @ arm.pose.bones[f'mixamorig:{side}Foot'].head)
        aim_at = aim_at + (goal - got)
    return pose

def resolve_target(pose, side, t):
    """World position for a plant target, evaluated with this key's root placement."""
    apply_raw(pose)
    if t == 'hold': return Vector(LAST_ANKLE.get(side, char_to_world(ANKLE_READY[side])))
    if isinstance(t, tuple) and t and t[0] == 'hold':
        return Vector(LAST_ANKLE.get(side, char_to_world(ANKLE_READY[side]))) + Vector((0, 0, t[1]))
    if t == 'ready': return char_to_world(ANKLE_READY[side])
    if isinstance(t, tuple) and t and t[0] == 'ready':
        return char_to_world(Vector(ANKLE_READY[side]) + Vector((t[1], t[2], t[3] if len(t) > 3 else 0.0)))
    if isinstance(t, tuple) and t and t[0] == 'world':
        return Vector((t[1], t[2], SOLE_Z[f'mixamorig:{side}Foot'] + (t[3] if len(t) > 3 else 0.0)))
    return char_to_world(t)

def solve(pose):
    """Post-mirror solve: plant legs, then ground the hips (unless free)."""
    pose = dict(pose)
    targets = {}
    for side, t in pose.get('plant', {}).items():
        targets[side] = resolve_target(pose, side, t)
    for side, tg in targets.items():
        solve_leg(pose, side, tg, pose.get('plant_pitch', {}).get(side, 0.0))
    if not pose.get('free'):
        apply_raw(pose)
        if pose.get('support'):
            pen = sole_pen((pose['support'],))
        elif targets and len(targets) == 2:
            pen = 0.0
        else:
            pen = sole_pen()
        pen -= pose.get('lift', 0.0)
        if abs(pen) > 1e-5 and not (targets and len(targets) == 2):
            h = pose.get('hips', (0, 0, 0)); pose['hips'] = (h[0], h[1], h[2] - pen)
            if targets:  # keep the planted foot where it was after the hips moved
                for side, tg in targets.items():
                    solve_leg(pose, side, tg, pose.get('plant_pitch', {}).get(side, 0.0), iters=2)
    apply_raw(pose)
    for s in ('Left', 'Right'):
        LAST_ANKLE[s] = (MW @ arm.pose.bones[f'mixamorig:{s}Foot'].tail).copy()
    pose['_targets'] = targets
    return pose

MIRROR = False
KEYLOG = []

def key(frame, pose):
    if MIRROR: pose = mirror_pose(pose)
    pose = solve(pose)
    for name in BODY_BONES:
        pb = arm.pose.bones[name]
        pb.keyframe_insert('rotation_quaternion', frame=frame)
        if name in ('mixamorig:Hips', 'Root'): pb.keyframe_insert('location', frame=frame)
    for hb in HANDS.values():
        for p in PROPS: hb.keyframe_insert(data_path=f'["{p}"]', frame=frame)
    KEYLOG.append((frame, bool(pose.get('free')), pose['_targets'], bool(pose.get('nofloor'))))
    if a.dump:
        print('KEYQ', frame, 'LeftFoot pb', tuple(round(x, 3) for x in arm.pose.bones['mixamorig:LeftFoot'].rotation_quaternion), 'LASTQ', tuple(round(x, 3) for x in LASTQ['mixamorig:LeftFoot']))
        print('KEY', frame, {s_: round(min((MW @ arm.pose.bones[n].tail).z - SOLE_Z[n] for n in SOLES[s_]), 3) for s_ in ('Left', 'Right')},
              {k: (v if not isinstance(v, dict) else {kk: (vv if kk != 'aim' else 'aim') for kk, vv in v.items()}) for k, v in pose.items() if k in ('RightUpLeg', 'RightLeg', 'RightFoot', 'hips', 'plant')})

def T(sec): return int(round(sec * FPS))

def keys_from(poses):
    for sec, pose in poses: key(T(sec), pose)

def all_fcurves(act):
    if hasattr(act, 'fcurves') and len(getattr(act, 'fcurves', [])): return list(act.fcurves)
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags: out.extend(cb.fcurves)
    return out

def linear(act, data_path_end, index, f0, f1):
    for fc in all_fcurves(act):
        if fc.data_path.endswith(data_path_end) and (index is None or fc.array_index == index):
            for kp in fc.keyframe_points:
                if f0 <= kp.co.x <= f1: kp.interpolation = 'LINEAR'

def bake_contacts(act, nframes):
    """Per-frame pass after keying: hold planted feet in place between keys that plant them on the same spot,
    and lift the hips wherever a sole would sink below the floor (grounded stretches only)."""
    keys = sorted(KEYLOG)
    if not keys: return
    free = set(); pinned = {}
    for (f0, fr0, t0, nf0), (f1, fr1, t1, nf1) in zip(keys, keys[1:]):
        for f in range(f0, f1 + 1):
            if nf0 or nf1: free.add(f)   # kneeling / lying: the feet legitimately sit below their standing soles
        for side in t0:
            if side in t1 and (t0[side] - t1[side]).length < 0.01:
                for f in range(f0, f1 + 1): pinned.setdefault(f, {})[side] = t0[side]
    hips = arm.pose.bones['mixamorig:Hips']
    arm.animation_data.action = act
    for _ in range(3):
        for f in range(nframes + 1):
            sc.frame_set(f); bpy.context.view_layer.update()
            Bf = arm.pose.bones['Root'].matrix.to_3x3() @ REST['Root'].inverted()
            rp = MW @ arm.pose.bones['Root'].head
            delta = Vector((0, 0, 0))
            pins = pinned.get(f, {})
            if pins:
                dxy = Vector((0, 0, 0))
                for side, tg in pins.items():
                    cur = MW @ arm.pose.bones[f'mixamorig:{side}Foot'].tail
                    if a.dump and 26 <= f <= 30: print('PIN', _, f, side, 'cur', tuple(round(x, 4) for x in cur), 'tg', tuple(round(x, 4) for x in tg))
                    dxy += Vector((tg.x - cur.x, tg.y - cur.y, 0))
                delta += dxy / len(pins)
            if f not in free:
                bones = [n for side in pins for n in SOLES[side]] if pins else SOLE_BONES
                pen = min((MW @ arm.pose.bones[n].tail).z - SOLE_Z[n] for n in bones)
                if pen < -1e-4: delta.z -= pen
            if delta.length > 1e-5:
                if a.dump: print('BAKE', _, f, 'pins', list(pins), 'delta', tuple(round(x, 4) for x in delta), 'hips', tuple(round(x, 4) for x in hips.location))
                hips.location = hips.location + REST['mixamorig:Hips'].inverted() @ (Bf.inverted() @ delta)
                hips.keyframe_insert('location', frame=f)
    if a.dump:
        for f in (26, 27, 28, 29, 30):
            sc.frame_set(f); bpy.context.view_layer.update()
            print('POSTBAKE', f, tuple(round(x, 4) for x in (MW @ arm.pose.bones['mixamorig:LeftFoot'].tail)), 'hipsloc', tuple(round(x, 4) for x in hips.location))
        arm.animation_data.action = None
        arm.animation_data.action = act
        for f in (26, 27, 28, 29, 30):
            sc.frame_set(f); bpy.context.view_layer.update()
            print('REASSIGNED', f, tuple(round(x, 4) for x in (MW @ arm.pose.bones['mixamorig:LeftFoot'].tail)), 'hipsloc', tuple(round(x, 4) for x in hips.location))
    arm.animation_data.action = None

# ---------------------------------------------------------------- clips -------------------------------------
def clip_idle(length=4.0):
    n = T(length)
    for i in range(n):
        t = i / n
        s = math.sin(4 * math.pi * t + 1.1)                 # weight shift, twice per loop
        h = math.sin(4 * math.pi * t + 0.7); hh = max(-1.0, min(1.0, 1.7 * h))
        hd = math.sin(4 * math.pi * t + 0.2); hds = max(-1.0, min(1.0, 1.5 * hd))
        b = math.sin(6 * math.pi * t + 2.2)                 # breathing, three per loop
        c = math.sin(4 * math.pi * t + 2.6)
        chest = 2 * s + 1.5 * math.sin(4 * math.pi * t - 0.2) + 2.5 * math.sin(4 * math.pi * t) + 3 * s
        p = merge(READY, {
            'Spine': [('Y', 14 + 2 * s), ('Z', 3 * s), ('X', 3 * s)], 'Spine1': [('Y', 8 + 2.5 * b), ('Z', 2 * s + 1.5 * math.sin(4 * math.pi * t - 0.2))],
            'Spine2': [('Y', 4 + 1.5 * b), ('Z', 2.5 * math.sin(4 * math.pi * t))],
            'Neck': [('Y', -18), ('Z', 13 * hh)], 'Head': [('Y', -8 + 3 * hd), ('Z', 8 * hds)],
            'hips': (0, 0.035 * s, -0.055 - 0.014 * abs(s)),
        }, arms(elev=66 + 3 * s, twist=0, flex=48 + 4 * b, roll=75, left={'az': 22 + 2 * hd + chest}, right={'az': 22 + 2 * hd - chest}),
            hands(0.28 + 0.30 * (0.5 + 0.5 * c), 0.2), plant('ready', 'ready'))
        key(i, p)
    return dict(kind='loop', seconds=length, last_frame_exclusive=True)

def gait_run(ph):
    """One frame of the run at phase ph (0..1). Stance: the ankle target sweeps back at the travel speed with
    heel-first contact and toe-off; swing: knee tucked at mid-swing, reaching at the end; flight between."""
    speed = 3.2 * U; period = 0.6
    reach = 0.27 * U
    st = {'Left': (0.28, 0.56), 'Right': (0.78, 1.06)}
    p = {'Spine': [('Y', 38 + 9 * abs(math.sin(2 * math.pi * ph)))], 'Spine1': [('Y', 15), ('Z', -10 * math.sin(2 * math.pi * ph))], 'Spine2': [('Y', 8)],
         'Neck': [('Y', -(38 + 9 * abs(math.sin(2 * math.pi * ph))) * 1.05), ('Z', 4 * math.sin(2 * math.pi * ph))], 'Head': [('Y', -17)],
         'Hips': [('Z', -5 * math.sin(2 * math.pi * ph)), ('X', 4 * math.sin(2 * math.pi * ph))]}
    plants, pitches = {}, {}
    leg_specs = {}
    support = None
    for side, (s0, s1) in st.items():
        u = (ph - s0) % 1.0
        dur = s1 - s0
        if u <= dur:  # stance
            t = u / dur
            x = reach - speed * period * u
            pitch = -14 * (1 - min(1, t * 2.5)) + 34 * max(0.0, (t - 0.65) / 0.35)
            plants[side] = (x, ANKLE_READY[side].y, ANKLE_READY[side].z)
            pitches[side] = pitch
            support = side
        else:  # swing: from toe-off (behind) to reach (ahead)
            w = (u - dur) / (1 - dur)
            e = 0.5 - 0.5 * math.cos(math.pi * w)
            thigh = 38 - (38 + 40) * e
            knee = 30 + 62 * math.sin(math.pi * w) ** 1.2
            foot = -20 + 30 * (1 - w)
            sg = 1 if side == 'Left' else -1
            leg_specs[f'{side}UpLeg'] = [('Y', thigh), ('X', 7 * sg)]
            leg_specs[f'{side}Leg'] = [('Y', knee)]
            leg_specs[f'{side}Foot'] = [('Y', foot), ('X', -7 * sg)]
    p.update(leg_specs)
    # hips height: absorb through the stance, an arc through flight
    if support:
        s0, s1 = st[support]; t = ((ph - s0) % 1.0) / (s1 - s0)
        z = -0.075 - 0.03 * math.sin(math.pi * t)
    else:
        z = -0.075 + 0.055 * math.sin(math.pi * ((ph - 0.56) % 0.5) / 0.22) if ((ph - 0.56) % 0.5) < 0.22 else -0.075
    p['hips'] = (0, 0.0, z)
    p['free'] = support is None
    # arms swing fore-aft with elevation, counter to the legs
    sw = math.sin(2 * math.pi * ph)
    th_l, th_r = -sw * 50, sw * 50
    p.update({'LeftArm': arm_rot('Left', 90 - abs(th_l), 80 if th_l >= 0 else -60, 5), 'LeftForeArm': {'flex': 25 + 40 * max(0.0, th_l) / 50, 'roll': 60},
              'RightArm': arm_rot('Right', 90 - abs(th_r), 80 if th_r >= 0 else -60, 5), 'RightForeArm': {'flex': 25 + 40 * max(0.0, th_r) / 50, 'roll': 60}})
    p = merge(p, hands(0.15, 0.3))
    if plants:
        p['plant'] = plants; p['plant_pitch'] = pitches
    return p

def gait_creep(ph):
    """Stalking walk: 65 percent stance per foot, the stance ankle sweeping back at the travel speed with heel
    strike, flat mid-stance and toe-off; the swing foot low; arms low and forward, swinging fore-aft."""
    speed = 0.32 * U; period = 1.5
    reach = 0.15 * U
    st = {'Left': (0.15, 0.80), 'Right': (0.65, 1.30)}
    sw = math.sin(2 * math.pi * ph)
    # Weight: the pelvis is lowest a quarter step after each heel strike (0.15 / 0.65) and highest a quarter
    # step after the passing position; a sneak with no vertical reads weightless (ANIMATION_PRINCIPLES.md §2).
    bob = -0.012 * math.sin(4 * math.pi * (ph - 0.15))
    p = {'Spine': [('Y', 27 + 2 * abs(sw))], 'Spine1': [('Y', 11), ('Z', -8 * sw)], 'Spine2': [('Y', 5)],
         'Neck': [('Y', -30), ('Z', 3 * sw)], 'Head': [('Y', -12)], 'Hips': [('Z', -4 * sw), ('X', 3 * sw)],
         'hips': (0, -0.012 * math.cos(2 * math.pi * ph), -0.10 + bob)}
    plants, pitches = {}, {}
    for side, (s0, s1) in st.items():
        u = (ph - s0) % 1.0; dur = s1 - s0
        if u <= dur:
            t = u / dur
            x = reach - speed * period * u
            pitch = -12 * (1 - min(1, t / 0.45)) + 32 * max(0.0, (t - 0.72) / 0.28)
            plants[side] = (x, ANKLE_READY[side].y, ANKLE_READY[side].z); pitches[side] = pitch
        else:
            # Swing: the ball follows a low solved arc from toe-off to the reach. The old forward-kinematic
            # swing put the reaching foot up to 8 cm below the floor, and the contact bake answered by lifting
            # the whole body and dropping it 8 cm on the heel strike (r04 Creep, twice per cycle).
            w = (u - dur) / (1 - dur); e = 0.5 - 0.5 * math.cos(math.pi * w)
            x = (reach - speed * period * dur) + (speed * period * dur) * e
            lift = 0.045 * U * math.sin(math.pi * w)
            pitch = 32 * (1 - w) ** 1.5 - 12 * w ** 2
            plants[side] = (x, ANKLE_READY[side].y, ANKLE_READY[side].z + lift); pitches[side] = pitch
    p = merge(p, arms(elev=84, az=55, twist=-10, flex=38, roll=75, left={'elev': 84 - 13 * sw, 'flex': 38 + 10 * max(0.0, sw)},
                      right={'elev': 84 + 13 * sw, 'flex': 38 + 10 * max(0.0, -sw)}), hands(0.2, 0.35))
    p['plant'] = plants; p['plant_pitch'] = pitches
    return p

def clip_cycle(kind, length):
    n = T(length)
    for i in range(n):
        ph = i / n
        key(i, gait_run(ph) if kind == 'run' else gait_creep(ph))
    return dict(kind='loop', seconds=length, last_frame_exclusive=True, travel_speed_units_per_s=(0.32 if kind == 'creep' else 3.2) * U)

def clip_attack():
    """Variant A, right claw: cocked above the right shoulder, one diagonal slash down and across to the left
    hip, held low, then a two-beat recovery. Rear (right) foot stays put; the left foot steps in and back."""
    rear = plant(right='ready')
    windup = merge(READY, {
        'Spine': [('Y', 8), ('Z', -18)], 'Spine1': [('Y', 4), ('Z', -12)], 'Neck': [('Y', -14), ('Z', 18)], 'Head': [('Y', -6), ('Z', 12)],
        **one_arm('Right', -45, 30, 10, 90, 30), **one_arm('Left', 55, 30, 0, 75, 60),
        'hips': (-0.02, 0.0, -0.06),
    }, hands(0.2, 0.5), plant(('ready', 0.13, 0.0, 0.07), 'ready'))
    step = merge(windup, {'hips': (0.03, 0, -0.065)}, plant(('ready', 0.13, 0.0), 'ready'))
    slash = merge(READY, {
        'Spine': [('Y', 22), ('Z', 20)], 'Spine1': [('Y', 10), ('Z', 12)], 'Spine2': [('Y', 4), ('Z', 6)], 'Neck': [('Y', -18), ('Z', -15)], ('Head'): [('Y', -6), ('Z', -10)],
        **one_arm('Right', 35, 100, 0, 15, 40), **one_arm('Left', 70, -35, 0, 40, 60),
        'hips': (0.07, 0.0, -0.062),
    }, hands(0.15, 0.6), plant('hold', 'ready', r_pitch=22))
    follow = merge(slash, {'Spine': [('Y', 26), ('Z', 22)], **one_arm('Right', 55, 115, 0, 35, 60), 'hips': (0.075, 0, -0.068)}, hands(0.3, 0.4))
    settle = merge(READY, {'Spine': [('Y', 20), ('Z', 14)], 'Spine1': [('Y', 9), ('Z', 8)], 'Neck': [('Y', -14)],
                           **one_arm('Right', 60, 60, 0, 60, 70), **one_arm('Left', 62, 30, 0, 50, 70), 'hips': (0.045, 0, -0.068)},
                   hands(0.35, 0.3), plant('hold', 'ready', r_pitch=8))
    drift = merge(settle, {'Spine': [('Y', 18), ('Z', 10)], 'hips': (0.035, 0, -0.07)})
    lift = merge(READY, {'Spine': [('Y', 16), ('Z', 4)], 'hips': (0.0, 0, -0.06)}, plant(('ready', 0, 0, 0.06), 'ready'))
    keys_from([(0.0, merge(READY, BOTH)), (0.35, windup), (0.46, step), (0.62, slash), (0.72, follow), (0.95, settle), (1.2, drift), (1.45, lift), (1.65, merge(READY, plant('ready', 'ready'))), (1.9, merge(READY, plant('ready', 'ready')))])
    return dict(kind='one-shot', seconds=1.9, hit_window_seconds=[0.52, 0.68], strike='RightHand')

def clip_attack_b():
    """Variant B, left claw: low outside the left hip, a rising backhand across the front that finishes above the
    right shoulder; the right foot steps in, the left (rear) foot drives on its ball."""
    rear = plant(left='ready')
    windup = merge(READY, {
        'Spine': [('Y', 22), ('Z', 20)], 'Spine1': [('Y', 8), ('Z', 12)], 'Neck': [('Y', -16), ('Z', -14)],
        **one_arm('Left', 78, 5, 0, 45, 70), **one_arm('Right', 50, 55, 0, 70, 60),
        'hips': (-0.03, 0, -0.07),
    }, legs(-18, 32, -14, -34, 48, -2), hands(0.15, 0.5), rear)
    liftr = merge(windup, {'hips': (0.0, 0, -0.07)}, plant('ready', ('ready', 0.13, 0.0, 0.07)))
    step = merge(windup, {'hips': (0.06, 0, -0.075)}, plant('ready', ('ready', 0.13, 0.0)))
    contact = merge(READY, {
        'Spine': [('Y', 16), ('Z', -12)], 'Spine1': [('Y', 6), ('Z', -8)], 'Neck': [('Y', -12), ('Z', 20)], 'Head': [('Y', -4), ('Z', 10)],
        **one_arm('Left', -12, 95, 0, 12, 30), **one_arm('Right', 50, 60, 0, 80, 50),
        'hips': (0.07, 0, -0.075),
    }, hands(0.1, 0.6), plant('ready', 'hold', l_pitch=26))
    slash = merge(contact, {'Spine': [('Y', 14), ('Z', -26)], 'Spine1': [('Y', 5), ('Z', -16)], 'Neck': [('Y', -12), ('Z', 26)], 'Head': [('Y', -4), ('Z', 14)],
                            **one_arm('Left', -12, 112, 0, 20, 30)})
    follow = merge(slash, {'Spine': [('Y', 8), ('Z', -36)], 'Spine1': [('Y', 4), ('Z', -20)], 'Neck': [('Y', -10), ('Z', 30)],
                           **one_arm('Left', 15, 130, 0, 30, 20), **one_arm('Right', 60, 40, 0, 60, 60)}, hands(0.3, 0.4))
    settle = merge(follow, {'Spine': [('Y', 14), ('Z', -18)], 'Spine1': [('Y', 5), ('Z', -10)], 'Neck': [('Y', -10), ('Z', 24)], 'Head': [('Y', -8), ('Z', 10)],
                            **one_arm('Left', 10, 125, 0, 35, 30), 'hips': (0.06, 0, -0.08)}, plant('ready', 'hold', l_pitch=10))
    drift = merge(settle, {'Spine': [('Y', 14), ('Z', -22)], 'Spine1': [('Y', 5), ('Z', -12)], **one_arm('Left', -5, 120, 0, 30, 40), 'hips': (0.05, 0, -0.085)})
    liftback = merge(READY, {'Spine': [('Y', 20), ('Z', -5)], 'hips': (0.0, 0, -0.06)}, plant('ready', ('ready', 0, 0, 0.06)))
    keys_from([(0.0, merge(READY, BOTH)), (0.33, windup), (0.40, liftr), (0.47, step), (0.53, contact), (0.59, slash), (0.66, follow), (0.82, settle), (1.15, drift), (1.45, liftback), (1.65, merge(READY, plant('ready', 'ready'))), (1.9, merge(READY, plant('ready', 'ready')))])
    return dict(kind='one-shot', seconds=1.9, hit_window_seconds=[0.50, 0.63], strike='LeftHand')

def clip_kick():
    """Front kick with the right leg at chest height on a planted left foot: anticipation, chamber, snap,
    retract, plant, knee absorb, rebound."""
    sup = plant(left='ready')
    anticip = merge(READY, {'Spine': [('Y', 20)], 'Neck': [('Y', -22)], 'hips': (-0.035, 0.02, -0.085)}, plant('ready', 'ready', r_pitch=18))
    load = merge(READY, {'Spine': [('Y', 6), ('X', 7)], 'Spine1': [('Y', 3), ('X', 3)], 'hips': (-0.02, 0.035, -0.075)}, legs(r_thigh=-108, r_knee=120, r_foot=10),
                 arms(elev=55, az=-10, twist=0, flex=40, roll=60, left={'az': 5, 'flex': 60}, right={'az': -35}), sup)
    kick = merge(READY, {'Spine': [('Y', -18), ('X', 7)], 'Spine1': [('Y', -9), ('X', 3)], 'Neck': [('Y', -2)], 'hips': (0.05, 0.03, -0.05)}, legs(r_thigh=-112, r_knee=8, r_foot=25),
                 arms(elev=52, az=-55, twist=0, flex=25, roll=50, left={'elev': 58, 'az': 60, 'flex': 75}), hands(0.5, 0.2), sup)
    through = merge(kick, {'Spine': [('Y', -21), ('X', 7)], 'hips': (0.085, 0.03, -0.05)}, legs(r_thigh=-116, r_knee=2, r_foot=30), sup)
    half_back = merge(kick, {'hips': (0.02, 0.035, -0.06)}, legs(r_thigh=-96, r_knee=55, r_foot=15), sup)
    retract = merge(load, {'hips': (-0.02, 0.03, -0.06)}, legs(r_thigh=-36, r_knee=108, r_foot=0), sup)
    hover = merge(READY, {'Spine': [('Y', 14)], 'hips': (0.0, 0.025, -0.07)}, arms(elev=62, az=20, twist=0, flex=50, roll=75), plant('ready', ('ready', 0, 0, 0.05)))
    plant_k = merge(READY, {'Spine': [('Y', 16)], 'hips': (0.01, 0.02, -0.06)}, plant('ready', 'ready'))
    settle = merge(READY, {'Spine': [('Y', 22)], 'hips': (0, 0.005, -0.09)}, plant('ready', 'ready'))
    rebound = merge(READY, {'Spine': [('Y', 17)], 'hips': (0, 0, -0.04)}, plant('ready', 'ready'))
    # Hard accent: the kick overshoots for one frame after the hit and rebounds at once instead of driving on
    # for four frames (ANIMATION_PRINCIPLES.md §1, hard vs soft accent). The recovery keeps its old spacing.
    keys_from([(0.0, merge(READY, BOTH)), (0.10, anticip), (0.25, load), (0.40, kick), (0.4333, through), (0.50, half_back), (0.60, retract), (0.66, hover), (0.72, plant_k), (0.80, settle), (0.88, rebound), (1.10, merge(READY, BOTH))])
    return dict(kind='one-shot', seconds=1.10, hit_window_seconds=[0.38, 0.48], strike='RightFoot')

def clip_dash(direction):
    fwd = direction > 0
    dist = (1.6 if fwd else 0.9) * U * direction
    final = {s_: ('world', dist + ANKLE_READY[s_].x, ANKLE_READY[s_].y) for s_ in ('Left', 'Right')}
    def fin(side, dx=0.0, dz=0.0): return ('world', final[side][1] + dx, final[side][2], dz)
    if fwd:
        crouch = merge(READY, {'Spine': [('Y', 48)], 'Spine1': [('Y', 14)], 'Neck': [('Y', -30)], 'hips': (-0.06, 0, -0.26)}, arms(elev=70, az=-50, twist=0, flex=30, roll=70), BOTH)
        press = merge(READY, {'Spine': [('Y', 47)], 'Neck': [('Y', -32)], 'hips': (-0.02, 0, -0.20)}, arms(elev=72, az=-30, twist=0, flex=35, roll=70), plant('hold', 'hold', l_pitch=12, r_pitch=12))
        launch = merge(READY, {'Spine': [('Y', 45)], 'Spine1': [('Y', 14)], 'Neck': [('Y', -35)], 'hips': (0.06, 0, -0.06)}, arms(elev=40, az=80, twist=0, flex=20, roll=40), hands(0.1, 0.6), plant('hold', 'hold', l_pitch=40, r_pitch=40))
        air = merge(READY, {'free': True, 'Hips': [('Y', 35)], 'Spine': [('Y', 26)], 'Spine1': [('Y', 10)], 'Neck': [('Y', -45)], 'Head': [('Y', -18)], 'hips': (0, 0, 0.12)},
                    legs(48, 22, 35, 55, 28, 35), arms(elev=-10, az=85, twist=0, flex=8, roll=30), hands(0.05, 0.7))
        fall = merge(air, {'free': True, 'Hips': [('Y', 26)], 'Spine': [('Y', 30)], 'Neck': [('Y', -42)], 'hips': (0, 0, 0.05)}, legs(-24, 34, -10, 8, 50, 8), arms(elev=30, az=85, twist=0, flex=20, roll=40), hands(0.1, 0.6))
        impact = merge(READY, {'Spine': [('Y', 38)], 'Spine1': [('Y', 14)], 'Neck': [('Y', -30)], 'hips': (-0.02, 0, -0.30)}, arms(elev=78, az=35, twist=0, flex=30, roll=70, right={'elev': 82, 'az': 48}),
                       plant(fin('Left'), fin('Right', -0.10), l_pitch=-12, r_pitch=22))
        drag = merge(impact, {'Spine': [('Y', 34)], 'hips': (0.0, 0, -0.28)}, arms(elev=76, az=32, twist=0, flex=36, roll=70, right={'elev': 81, 'az': 46, 'flex': 22}), plant('hold', 'hold', l_pitch=-8, r_pitch=14))
        land = merge(impact, {'Spine': [('Y', 30)], 'hips': (0.02, 0, -0.26)}, arms(elev=75, az=30, twist=0, flex=40, roll=70, right={'elev': 80, 'az': 45, 'flex': 10}), plant('hold', 'hold', l_pitch=0, r_pitch=8))
        rise = merge(READY, {'Spine': [('Y', 26)], 'Spine1': [('Y', 12)], 'hips': (0.02, 0, -0.19)}, arms(elev=72, az=25, twist=0, flex=45, roll=70, right={'elev': 64, 'az': -5}), plant(left='hold', right=fin('Right', 0, 0.06)))
        settle = merge(READY, {'Spine': [('Y', 18)], 'Spine1': [('Y', 9)], 'hips': (0, 0, -0.07)}, plant(fin('Left'), fin('Right')))
        seq = [(0.0, merge(READY, BOTH), 0.0), (0.22, crouch, 0.0), (0.30, crouch, 0.0), (0.36, press, 0.0), (0.42, launch, 0.05), (0.58, air, 0.40), (0.71, fall, 0.74), (0.80, impact, 0.90), (0.92, drag, 0.975), (1.05, land, 1.0), (1.14, merge(land, {'hips': (0.03, 0.02, -0.24)}, plant(left='hold', right=fin('Right', -0.10, 0.06))), 1.0), (1.24, rise, 1.0), (1.44, settle, 1.0), (1.6, merge(READY, plant('ready', 'ready')), 1.0)]
        f0, f1 = T(0.42), T(0.80)
    else:
        crouch = merge(READY, {'Spine': [('Y', 30)], 'Spine1': [('Y', 12)], 'Neck': [('Y', -26)], 'Head': [('Y', -10)], 'hips': (-0.09, 0, -0.20)}, arms(elev=70, az=-50, twist=0, flex=30, roll=70), plant('hold', 'hold', l_pitch=6))
        mid = merge(READY, {'Spine': [('Y', 20)], 'Spine1': [('Y', 8)], 'Neck': [('Y', -16)], 'hips': (-0.06, 0, -0.10)}, arms(elev=72, az=-25, twist=0, flex=35, roll=70), plant('hold', 'hold', l_pitch=6, r_pitch=4))
        launch = merge(READY, {'Spine': [('Y', 8)], 'Spine1': [('Y', 4)], 'Neck': [('Y', -6)], 'hips': (-0.05, 0, -0.02)}, arms(elev=70, az=35, twist=0, flex=40, roll=70), hands(0.15, 0.5), plant('hold', 'hold', l_pitch=32, r_pitch=32))
        air = merge(READY, {'free': True, 'Hips': [('Y', -20)], 'Spine': [('Y', -14)], 'Spine1': [('Y', -6)], 'Neck': [('Y', 6)], 'hips': (0, 0, 0.12)},
                    legs(-30, 40, 15, -38, 30, 20), arms(elev=0, az=70, twist=0, flex=25, roll=40), hands(0.1, 0.6))
        fall = merge(air, {'free': True, 'Spine': [('Y', -8)], 'Neck': [('Y', -4)], 'hips': (0, 0, 0.08)}, legs(-30, 62, -20), arms(elev=12, az=70, twist=0, flex=35, roll=40))
        impact = merge(READY, {'Spine': [('Y', 34)], 'Spine1': [('Y', 12)], 'Neck': [('Y', -26)], 'hips': (-0.02, 0, -0.29)}, arms(elev=45, az=60, twist=0, flex=45, roll=60),
                       plant(fin('Left'), fin('Right'), l_pitch=-10, r_pitch=-8))
        land = merge(impact, {'Spine': [('Y', 26)], 'hips': (0, 0, -0.24)}, arms(elev=68, az=25, twist=0, flex=40, roll=70), plant('hold', 'hold', l_pitch=0, r_pitch=0))
        rise = merge(READY, {'Spine': [('Y', 16)], 'Spine1': [('Y', 10)], 'Neck': [('Y', -14)], 'hips': (0, 0, -0.16)}, arms(elev=76, az=8, twist=0, flex=45, roll=70), plant('hold', 'hold'))
        seq = [(0.0, merge(READY, BOTH), 0.0), (0.2, crouch, 0.0), (0.25, mid, 0.0), (0.30, launch, 0.03), (0.44, air, 0.37), (0.55, fall, 0.63), (0.66, impact, 0.97), (0.80, land, 1.0), (1.0, rise, 1.0), (1.3, merge(READY, plant('ready', 'ready')), 1.0), (1.5, merge(READY, plant('ready', 'ready')), 1.0)]
        f0, f1 = T(0.30), T(0.66)
    for sec, pose, frac in seq:
        key(T(sec), merge(pose, {'root': (dist * frac, 0, 0)}))
    linear(arm.animation_data.action, 'pose.bones["Root"].location', None, f0, f1)
    return dict(kind='one-shot', seconds=seq[-1][0], root_motion=True, travel_units=dist)

def clip_turn():
    """180 to the LEFT: head leads, two short steps, the planted foot pivoting on its ball, root yaw in two
    bursts, arms dragging, settle."""
    drag = arms(elev=68, az=15, twist=0, flex=50, roll=75, left={'az': 8}, right={'az': 40})
    final = {s: ('world', -ANKLE_READY[s].x, -ANKLE_READY[s].y) for s in ('Left', 'Right')}   # the READY stance turned 180
    look = merge(READY, {'Neck': [('Y', -18), ('Z', 35)], 'Head': [('Y', -8), ('Z', 25)], 'Spine1': [('Y', 8), ('Z', 10)]}, BOTH)
    step1 = merge(READY, {'Spine': [('Y', 14), ('Z', 20), ('X', -6)], 'Neck': [('Y', -18), ('Z', 35)], 'Head': [('Y', -8), ('Z', 20)], 'hips': (0, 0.012, -0.065),
                          }, drag, plant(left=final['Left'] + (0.06,), right='hold', r_pitch=10))
    mid = merge(READY, {'Spine': [('Y', 16), ('Z', 18)], 'Neck': [('Y', -18), ('Z', 30)], 'Head': [('Y', -8), ('Z', 15)], 'hips': (0, 0.0, -0.085)}, drag,
                plant(left=final['Left'], right='hold', l_pitch=-4, r_pitch=14))
    shift = merge(READY, {'Spine': [('Y', 15), ('Z', 14)], 'Neck': [('Y', -18), ('Z', 26)], 'Head': [('Y', -8), ('Z', 12)], 'hips': (0, 0.0, -0.08)}, drag, plant(left='hold', right='hold', r_pitch=30))
    step2 = merge(READY, {'Spine': [('Y', 14), ('Z', 10), ('X', -6)], 'Neck': [('Y', -18), ('Z', 20)], 'Head': [('Y', -8), ('Z', 10)], 'hips': (0, -0.012, -0.065),
                          },
                 arms(elev=68, az=20, twist=0, flex=50, roll=75, right={'az': 30}), plant(left='hold', right=final['Right'] + (0.06,), l_pitch=10))
    plant2 = merge(READY, {'hips': (0, 0, -0.085), 'Neck': [('Y', -18), ('Z', 10)], 'Head': [('Y', -8), ('Z', 4)]}, arms(elev=68, az=24, twist=0, flex=50, roll=75, right={'az': 34}), plant(left='hold', right=final['Right']))
    over = merge(READY, {'Neck': [('Y', -18), ('Z', -8)], 'Head': [('Y', -8), ('Z', -4)], 'hips': (0, 0, -0.055)}, BOTH)
    settle = merge(READY, {'Spine': [('Y', 14), ('Z', 4)], 'Neck': [('Y', -16)], 'hips': (0, 0, -0.05)}, arms(elev=70, az=26, twist=0, flex=52, roll=75), BOTH)
    liftL = merge(look, {'hips': (0, 0.01, -0.06)}, plant(left=('hold', 0.06), right='hold', r_pitch=6))
    liftR = merge(shift, plant(left='hold', right=('hold', 0.06)))
    seq = [(0.0, merge(READY, BOTH), 0), (0.2, look, 0), (0.28, liftL, 4), (0.38, step1, 20), (0.5, mid, 78), (0.6, shift, 100), (0.66, liftR, 108), (0.75, step2, 124), (0.87, plant2, 172), (1.0, over, 186), (1.13, settle, 181), (1.3, merge(READY, plant('ready', 'ready')), 180)]
    for sec, pose, ang in seq:
        key(T(sec), merge(pose, {'root_rot': ang}))
    return dict(kind='one-shot', seconds=1.3, root_motion=True, yaw_degrees=180)

def clip_hurt():
    """Hit to the chest: head whips, arms fly back, one stagger step back onto the left foot, doubled over with
    a claw at the chest, knee absorb, two-beat recovery. Travels back on the Root."""
    hit = merge(READY, {'Spine': [('Y', -20), ('Z', 12), ('X', -8)], 'Spine1': [('Y', -12), ('Z', 8)], 'Neck': [('Y', -12), ('Z', -10)], 'Head': [('Y', -8)],
                        'root': (-0.08 * U, 0, 0), 'hips': (0, 0, -0.085)}, legs(-6, 80, -20, -34, 50, -10),
                arms(elev=20, az=-50, twist=0, flex=10, roll=30, left={'elev': 62, 'az': 15, 'flex': 95, 'roll': 50}), hands(0.1, 0.7), plant(right=('ready', 0.06, 0)))
    landing = ('world', -0.28 * U + ANKLE_READY['Left'].x, ANKLE_READY['Left'].y)
    whip = merge(hit, {'Neck': [('Y', -22), ('Z', -12)], 'Head': [('Y', -18)], 'root': (-0.11 * U, 0, 0)}, plant(left=landing + (0.09,), right=('ready', 0.06, 0)))
    passing = merge(READY, {'Spine': [('Y', 10)], 'Neck': [('Y', -14)], 'Head': [('Y', -8)], 'root': (-0.16 * U, 0, 0), 'hips': (0, 0, -0.10)}, legs(r_thigh=-20, r_knee=75, r_foot=-30),
                    arms(elev=45, az=-30, twist=0, flex=40, roll=50, right={'elev': 55, 'az': 30, 'flex': 90}), hands(0.4, 0.3), plant(left=landing + (0.03,), right='hold'))
    stag_legs = legs(26, 12, -27, -26, 58, -10)
    stag_spine = {'Spine': [('Y', 16), ('Z', -12), ('X', 8)], 'Spine1': [('Y', 10), ('Z', -14)], 'Neck': [('Y', -4), ('Z', -12)], 'Head': [('Y', 8)]}
    stag_arms = arms(elev=55, az=-45, twist=0, flex=40, roll=60, right={'elev': 52, 'az': 60, 'flex': 115}, left={'elev': 38, 'az': -55, 'flex': 20})
    plant_l = merge(READY, stag_spine, {'root': (-0.27 * U, 0, 0), 'hips': (0, 0, -0.10)}, stag_legs, stag_arms, hands(0.6, 0.1, 0.5, 0.6), plant(left=landing, right='hold'))
    stagger = merge(plant_l, {'root': (-0.31 * U, 0, 0)}, plant('hold', 'hold'))
    sink = merge(stagger, {'Spine': [('Y', 24), ('Z', -12), ('X', 8)], 'Spine1': [('Y', 12), ('Z', -14)], 'Neck': [('Y', -10), ('Z', -12)], 'root': (-0.29 * U, 0, 0), 'hips': (0, 0, -0.125)})
    catch = merge(stagger, {'Spine': [('Y', 10), ('Z', -8), ('X', 6)], 'root': (-0.28 * U, 0, 0), 'hips': (0, 0, -0.08)})
    rmid = merge(READY, {'Spine': [('Y', 12), ('Z', -8)], 'Spine1': [('Y', 10), ('Z', -10)], 'Neck': [('Y', -10)], 'root': (-0.28 * U, 0, 0), 'hips': (0, 0.01, -0.08)}, legs(-18, 32, -14, -30, 105, 15),
                 arms(elev=60, az=10, twist=0, flex=60, roll=70, right={'elev': 62, 'az': 40, 'flex': 105}), hands(0.5, 0.1), plant(left='hold'))
    rlift = merge(READY, {'Spine': [('Y', 18), ('Z', -6)], 'Spine1': [('Y', 10), ('Z', -8)], 'Neck': [('Y', -18)], 'root': (-0.28 * U, 0, 0), 'hips': (0, 0.01, -0.075)},
                  arms(elev=64, az=20, twist=0, flex=55, roll=70, right={'elev': 66, 'az': 30, 'flex': 95}), hands(0.5, 0.1), plant(left='hold', right=('ready', 0, 0, 0.06)))
    recover = merge(READY, {'Spine': [('Y', 24)], 'Spine1': [('Y', 12)], 'Neck': [('Y', -22)], 'root': (-0.28 * U, 0, 0), 'hips': (0, 0, -0.07)},
                    arms(elev=66, az=22, twist=0, flex=48, roll=75, right={'elev': 72, 'az': 18, 'flex': 85}), hands(0.5, 0.1), plant(left='hold', right='ready'))
    end = merge(READY, {'root': (-0.28 * U, 0, 0)}, plant('ready', 'ready'))
    over = merge(end, {'Neck': [('Y', -22)]})
    # The displaced hit pose lands on the frame after contact (no ease-in); the head whip trails it by two frames.
    keys_from([(0.0, merge(READY, BOTH, {'root': (0, 0, 0)})), (0.0333, hit), (0.10, whip), (0.20, passing), (0.27, plant_l), (0.35, stagger), (0.62, sink), (0.80, catch), (0.84, rmid), (0.90, rlift), (0.98, recover), (1.10, over), (1.2, end)])
    return dict(kind='one-shot', seconds=1.2, root_motion=True, travel_units=-0.28 * U)

def clip_death():
    """Hit, knees buckle, kneel (knees on the floor), fold forward onto the hands, pitch over the knees face down,
    still by three seconds."""
    hit = merge(READY, {'Spine': [('Y', -26)], 'Spine1': [('Y', -10)], 'Neck': [('Y', 30)], 'Head': [('Y', 24)]}, arms(elev=48, az=-10, twist=0, flex=35, roll=50, left={'az': 8}), hands(0.1, 0.6), BOTH)
    buckle = merge(READY, {'Spine': [('Y', 26)], 'Neck': [('Y', 6)], 'hips': (0, 0, -0.16)}, arms(elev=75, az=-15, twist=0, flex=25, roll=70), plant('hold', 'hold', l_pitch=10, r_pitch=10))
    kneel_legs = legs(-40, 130, 34, -40, 130, 28, l_out=6, r_out=6)
    kneel = merge(READY, kneel_legs, {'free': True, 'nofloor': True, 'Spine': [('Y', 10)], 'Neck': [('Y', 10)], 'Head': [('Y', 15)], 'hips': (0, 0, -0.285)}, arms(elev=78, az=-15, twist=0, flex=10, roll=70), hands(0.1, 0.1))
    # knee pivot: measured on the kneel pose so the tilt turns about the knees instead of the floor origin
    apply_raw(kneel)
    kn = sum((to_char(MW @ arm.pose.bones[f'mixamorig:{s}Leg'].head) for s in ('Left', 'Right')), Vector((0, 0, 0))) / 2
    kn.z = 0.0
    def placed(pose):
        """Set the root translation so the mean knee lands where it knelt (knee radius above the floor)."""
        pose = dict(pose); pose['root'] = (0, 0, 0)
        for _ in range(2):
            apply_raw(pose)
            k = sum((MW @ arm.pose.bones[f'mixamorig:{s}Leg'].head for s in ('Left', 'Right')), Vector((0, 0, 0))) / 2 - root_pos()
            r = pose['root']
            pose['root'] = (r[0] + kn.x - k.x, 0, r[2] + 0.035 - k.z)
        return pose
    knee_hit = merge(kneel, {'Spine': [('Y', 16)], 'hips': (0, 0, -0.305)})
    sag = merge(kneel, {'Spine': [('Y', 16)], 'Neck': [('Y', 14)], 'Head': [('Y', 20)], 'hips': (0.01, 0, -0.305)})
    fold = merge(kneel, {'Spine': [('Y', 55)], 'Spine1': [('Y', 25)], 'Neck': [('Y', 20)], 'Head': [('Y', 20)], 'hips': (0.05, 0, -0.29)}, arms(elev=70, az=-60, twist=0, flex=5, roll=70))
    hands_down = placed(merge(kneel, {'Spine': [('Y', 20)], 'Spine1': [('Y', 10)], 'Neck': [('Y', 5)], 'Head': [('Y', 10)], 'hips': (0.02, 0, -0.285), 'root_tilt': 45},
                              legs(-40, 85, 34, -40, 85, 28, l_out=6, r_out=6), arms(elev=35, az=60, twist=0, flex=15, roll=40)))   # knees open with the tilt so the shins stay down
    down = placed(merge({'free': True, 'nofloor': True, 'Spine': [('Y', 4)], 'Spine1': [('Y', 2)], 'Neck': [('Y', -10)], 'Head': [('Y', -2), ('Z', 25)], 'root_tilt': 90, 'hips': (0, 0, -0.03)},
                 legs(-12, 24, 18, -12, 24, 18, l_out=5, r_out=5), arms(elev=28, az=-16, twist=0, flex=12, roll=50, right={'elev': 34}), hands(0.05, 0.4)))
    down_flat = placed(merge(down, legs(0, 0, 18, 0, 0, 18, l_out=5, r_out=5)))
    # Hit pose on the frame after contact, then held (the six-frame hold is what makes the accent read).
    keys_from([(0.0, merge(READY, BOTH)), (0.0333, hit), (0.22, hit), (0.40, buckle), (0.60, knee_hit), (0.73, kneel), (1.0, sag), (1.4, fold), (1.6, hands_down),
               (1.95, placed(merge(down, {'root_tilt': 70}, legs(-30, 48, 30, -30, 48, 30, l_out=5, r_out=5)))), (2.05, down), (2.13, placed(merge(down, {'hips': (0, 0, -0.04)}))), (2.35, down_flat), (3.0, down_flat)])
    linear(arm.animation_data.action, 'pose.bones["Root"].rotation_quaternion', None, T(1.6), T(2.05))
    return dict(kind='one-shot', seconds=3.0, holds_last_pose=True)

def clip_jump():
    crouch = merge(READY, {'Spine': [('Y', 30)], 'Neck': [('Y', -28)], 'hips': (0, 0, -0.2)}, arms(elev=65, az=-45, twist=0, flex=50, roll=70), BOTH)
    push = merge(READY, {'Spine': [('Y', 18)], 'Neck': [('Y', -32)], 'hips': (0, 0, -0.06)}, arms(elev=25, az=55, twist=0, flex=45, roll=50), plant('hold', 'hold', l_pitch=8, r_pitch=8))
    launch = merge(READY, {'Spine': [('Y', 4)], 'Neck': [('Y', -35)], 'Head': [('Y', -15)], 'hips': (0, 0, 0.01)}, legs(10, 5, 35), arms(elev=-25, az=80, twist=0, flex=45, roll=30), hands(0.1, 0.6), plant('hold', 'hold', l_pitch=38, r_pitch=38))
    rising = merge(READY, {'free': True, 'Spine': [('Y', 4)], 'Neck': [('Y', -35)], 'Head': [('Y', -15)], 'hips': (0, 0, 0.20)}, legs(4, 3, 45), arms(elev=-35, az=80, twist=0, flex=50, roll=30), hands(0.1, 0.6))
    apex = merge(READY, {'free': True, 'Spine': [('Y', 6)], 'Spine1': [('Y', 4)], 'hips': (0, 0, 0.42)}, legs(-60, 95, 15, -10, 30, 35), arms(elev=0, az=70, twist=0, flex=40, roll=50), hands(0.05, 0.7))
    fall = merge(apex, {'free': True, 'Neck': [('Y', -6)], 'hips': (0, 0, 0.16)}, legs(-35, 45, 20, -20, 30, 20), arms(elev=45, az=-10, twist=0, flex=55, roll=60))
    land = merge(READY, {'Spine': [('Y', 22)], 'Spine1': [('Y', 10)], 'Neck': [('Y', -12)], 'Head': [('Y', 0)], 'hips': (0, 0, -0.19)}, arms(elev=68, az=-40, twist=0, flex=30, roll=70),
                 plant(('ready', 0.03, 0.02), ('ready', -0.03, -0.02)))
    plant_k = merge(READY, {'Spine': [('Y', 18)], 'Neck': [('Y', -16)], 'hips': (0, 0, -0.14)}, arms(elev=70, az=-15, twist=0, flex=40, roll=70), plant('hold', 'hold'))
    keys_from([(0.0, merge(READY, BOTH)), (0.2, crouch), (0.27, push), (0.33, launch), (0.40, rising), (0.6, apex), (0.82, fall), (0.95, land), (1.12, plant_k), (1.4, merge(READY, plant('ready', 'ready')))])
    return dict(kind='one-shot', seconds=1.4, apex_seconds=0.6)

CLIPS = {
    'Idle': (clip_idle, False), 'Creep': (lambda: clip_cycle('creep', 1.5), False), 'Run': (lambda: clip_cycle('run', 0.6), False),
    'AttackR_A': (clip_attack, False), 'AttackL_A': (clip_attack, True),
    'AttackL_B': (clip_attack_b, False), 'AttackR_B': (clip_attack_b, True),
    'Kick': (clip_kick, False), 'DashForward': (lambda: clip_dash(1), False), 'DashBackward': (lambda: clip_dash(-1), False),
    'TurnLeft': (clip_turn, False), 'TurnRight': (clip_turn, True),
    'Hurt': (clip_hurt, False), 'Death': (clip_death, False), 'Jump': (clip_jump, False),
}

# ---------------------------------------------------------------- build --------------------------------------
only = [s for s in a.only.split(',') if s]
manifest, actions, checks = {}, {}, {}
CHECKER = fox_hunter_clip.Checker(body, arm) if a.check else None

def measure(name, info):
    """Per-clip numbers: per-foot sole clearance, foot skating while grounded, striking limb through the hit
    window, root yaw steps, hand/head heights at the end."""
    act = actions[name]
    arm.animation_data.action = act
    n = info['frames']
    free = set()
    keys = sorted(KEYLOG)
    for (f0, fr0, _, nf0), (f1, fr1, _, nf1) in zip(keys, keys[1:]):
        if nf0 or nf1: free.update(range(f0, f1 + 1))
    per = {'Left': [], 'Right': []}; skate = {'Left': 0.0, 'Right': 0.0}; prev = {}
    reach, yaw_steps, prev_yaw = [], [], None
    for f in range(n + 1):
        sc.frame_set(f); bpy.context.view_layer.update()
        for s in ('Left', 'Right'):
            cl = min((MW @ arm.pose.bones[b].tail).z - SOLE_Z[b] for b in SOLES[s])
            per[s].append(round(cl, 4))
            pos = (MW @ arm.pose.bones[f'mixamorig:{s}Foot'].tail)
            if s in prev and cl < 0.012 and prev[s][1] < 0.012 and f not in free and info['kind'] != 'loop':
                skate[s] = max(skate[s], (pos.xy - prev[s][0].xy).length)
            prev[s] = (pos.copy(), cl)
        if info.get('strike'):
            hb = arm.pose.bones['mixamorig:' + info['strike']]
            hips_x = (MW @ arm.pose.bones['mixamorig:Hips'].head).x
            p = MW @ hb.tail
            reach.append((f, round(p.x - hips_x, 3), round(p.y, 3), round(p.z - FLOOR, 3)))
        yaw = math.degrees(arm.pose.bones['Root'].matrix.to_quaternion().to_euler('XYZ').z)
        if prev_yaw is not None: yaw_steps.append(round((yaw - prev_yaw + 180) % 360 - 180, 1))
        prev_yaw = yaw
    out = dict(left_sole_min=min(per['Left']), right_sole_min=min(per['Right']),
               left_sole_max=max(per['Left']), right_sole_max=max(per['Right']),
               max_skate_step_while_grounded={s: round(v, 4) for s, v in skate.items()},
               max_yaw_step_deg=max((abs(x) for x in yaw_steps), default=0.0))
    if info['kind'] == 'loop':
        out['frames_left_sole_over_6mm'] = sum(1 for v in per['Left'] if v > 0.006)
        out['frames_right_sole_over_6mm'] = sum(1 for v in per['Right'] if v > 0.006)
    if reach and info.get('hit_window_seconds'):
        w0, w1 = info['hit_window_seconds']
        inwin = [r for r in reach if T(w0) <= r[0] <= T(w1)]
        out['strike_path_in_window'] = inwin
        out['strike_min_forward_in_window'] = min(r[1] for r in inwin)
        out['strike_lateral_range_in_window'] = [min(r[2] for r in inwin), max(r[2] for r in inwin)]
        out['strike_height_range_in_window'] = [min(r[3] for r in inwin), max(r[3] for r in inwin)]
    if a.dump == name:
        arm.animation_data.action = act
        for flag in (True, False, True):
            act.use_frame_range = flag
            sc.frame_set(26); bpy.context.view_layer.update()
            print('MEASURE26 use_frame_range', flag, tuple(round(x, 4) for x in (MW @ arm.pose.bones['mixamorig:LeftFoot'].tail)), 'hipsloc', tuple(round(x, 4) for x in arm.pose.bones['mixamorig:Hips'].location), 'rootq', tuple(round(x, 3) for x in arm.pose.bones['Root'].rotation_quaternion))
        for f in range(20, 27):
            sc.frame_set(f); bpy.context.view_layer.update()
            print('SEQ', f, tuple(round(x, 4) for x in (MW @ arm.pose.bones['mixamorig:LeftFoot'].tail)), 'hipsloc', tuple(round(x, 4) for x in arm.pose.bones['mixamorig:Hips'].location), 'rootq', tuple(round(x, 3) for x in arm.pose.bones['Root'].rotation_quaternion), 'LupLeg', tuple(round(x, 3) for x in arm.pose.bones['mixamorig:LeftUpLeg'].rotation_quaternion))
        sc.frame_set(26); bpy.context.view_layer.update()
        print('JUMP 26', tuple(round(x, 4) for x in (MW @ arm.pose.bones['mixamorig:LeftFoot'].tail)), 'LupLeg', tuple(round(x, 3) for x in arm.pose.bones['mixamorig:LeftUpLeg'].rotation_quaternion))
        for f in range(n + 1):
            sc.frame_set(f); bpy.context.view_layer.update()
            row = [f, 'free' if f in free else '    ']
            for s_ in ('Left', 'Right'):
                pos = MW @ arm.pose.bones[f'mixamorig:{s_}Foot'].tail
                fq = arm.pose.bones[f'mixamorig:{s_}Foot'].rotation_quaternion
                fv = (MW @ arm.pose.bones[f'mixamorig:{s_}Foot'].tail) - (MW @ arm.pose.bones[f'mixamorig:{s_}Foot'].head)
                row += [s_[0], round(per[s_][f], 3), round(pos.x, 3), round(pos.y, 3), 'pitch', round(math.degrees(math.atan2(-fv.z, fv.xy.length)), 1), 'q', tuple(round(x, 2) for x in fq)]
            print('DUMP', *row)
    sc.frame_set(n); bpy.context.view_layer.update()
    out['end_hand_z'] = [round((MW @ HANDS[s].tail).z - FLOOR, 3) for s in ('Left', 'Right')]
    out['end_head_z'] = round((MW @ arm.pose.bones['mixamorig:Head'].tail).z - FLOOR, 3)
    if name == 'Death':
        out['end_knee_z'] = [round((MW @ arm.pose.bones[f'mixamorig:{s}Leg'].head).z - FLOOR, 3) for s in ('Left', 'Right')]
    arm.animation_data.action = None
    return out

def build(name):
    global MIRROR, LASTQ, KEYLOG, LAST_ANKLE
    fn, MIRROR = CLIPS[name]
    LASTQ = {}; KEYLOG = []; LAST_ANKLE = {}
    act = bpy.data.actions.new(f'Fox_{name}')
    arm.animation_data.action = act
    info = fn()
    MIRROR = False
    if CLIPS[name][1]:
        info['mirror_of'] = next(k for k, v in CLIPS.items() if v[0] is fn and not v[1])
        if 'yaw_degrees' in info: info['yaw_degrees'] = -info['yaw_degrees']
        if info.get('strike'): info['strike'] = info['strike'].replace('Left', 'TMP').replace('Right', 'Left').replace('TMP', 'Right')
    last = int(round(act.frame_range[1]))
    if info.get('last_frame_exclusive'):
        last = T(info['seconds']) - 1
    if not a.no_bake: bake_contacts(act, last)
    act.use_frame_range = True; act.frame_range = (0, last)
    act.use_fake_user = True
    actions[name] = act
    manifest[name] = dict(info, action=act.name, frames=last, fps=FPS)
    arm.animation_data.action = None
    checks[name] = measure(name, manifest[name])
    if a.check:
        arm.animation_data.action = act
        frames = []
        for f in range(0, last + 1, a.check_step):
            sc.frame_set(f); bpy.context.view_layer.update(); frames.append((f, CHECKER.frame(bpy.context.evaluated_depsgraph_get())))
        arm.animation_data.action = None
        checks[name]['clip'] = fox_hunter_clip.summarize(frames)
        print('CLIP', fox_hunter_clip.line(name, checks[name]['clip']))
    print('clip', name, manifest[name]['kind'], last, 'frames', 'mirror' if CLIPS[name][1] else '', json.dumps({k: v for k, v in checks[name].items() if k != 'strike_path_in_window'}))

for name in CLIPS:
    if only and name not in only: continue
    build(name)

mirror_err = 0.0
for pb in arm.pose.bones:
    if 'Left' in pb.name:
        h1, h2 = pb.bone.head_local, arm.pose.bones[pb.name.replace('Left', 'Right')].bone.head_local
        mirror_err = max(mirror_err, (Vector((h1.x, -h1.y, h1.z)) - h2).length)

# ---------------------------------------------------------------- sheets and exports -------------------------
arm.animation_data.action = None
for name, act in actions.items():
    tr = arm.animation_data.nla_tracks.new(); tr.name = name
    st = tr.strips.new(name, 0, act); st.name = name
    tr.mute = True
sheets = {}
if not a.no_sheets:
    cam = sc.camera; cam.data.type = 'PERSP'; cam.data.lens = 50
    sc.render.resolution_x = sc.render.resolution_y = 512
    sc.render.engine = 'BLENDER_EEVEE'; sc.render.image_settings.file_format = 'PNG'
    tmp = OUT / 'sheet-frames'; tmp.mkdir(exist_ok=True)
    for name, act in actions.items():
        for tr in arm.animation_data.nla_tracks: tr.mute = (tr.name != name)
        n = manifest[name]['frames']; files = []
        for i in range(6):
            f = int(round(n * i / 5)); sc.frame_set(f)
            rp = MW @ arm.pose.bones['Root'].head
            target = Vector((rp.x, rp.y, H * 0.48))
            cam.location = target + Vector((H * 2.4, -H * 2.0, H * 0.9)); cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = str(tmp / f'{name}-{i}.png'); bpy.ops.render.render(write_still=True); files.append((f, tmp / f'{name}-{i}.png'))
        sheets[name] = [(f, str(p.relative_to(OUT))) for f, p in files]
    for tr in arm.animation_data.nla_tracks: tr.mute = True

def write_manifest(exported):
    (OUT / 'manifest.json').write_text(json.dumps(dict(
        rig=str(RIG.relative_to(ROOT)), fps=FPS, model_height_units=round(H, 4), facing='+X', floor_z=round(FLOOR, 4), mirror_rest_error=round(mirror_err, 6),
        house_rules=['hanging arms: palms face the body', 'loops are in place; travel speed recorded', 'dashes, turns and hurt carry Root motion'],
        clips=manifest, checks=checks, sheets=sheets, exported_animations=exported), indent=2) + '\n')

if a.no_export:
    write_manifest([])
    print('ANIM OK (no export)', len(manifest), 'clips; floor', round(FLOOR, 4))
    sys.exit(0)

bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); body.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f'{NAME}.blend'))
for tr in arm.animation_data.nla_tracks: tr.mute = False
bpy.ops.export_scene.gltf(filepath=str(OUT / f'{NAME}.glb'), export_format='GLB', use_selection=True, export_animations=True,
                          export_animation_mode='NLA_TRACKS', export_skins=True, export_force_sampling=True, export_yup=True)
for im in bpy.data.images:
    if im.size[0] > a.texture_size: im.scale(a.texture_size, a.texture_size)
prev = OUT / 'preview'; prev.mkdir(exist_ok=True); gltf = prev / f'{NAME}.gltf'
bpy.ops.export_scene.gltf(filepath=str(gltf), export_format='GLTF_SEPARATE', use_selection=True, export_image_format='JPEG', export_jpeg_quality=85,
                          export_texture_dir='tex', export_animations=True, export_animation_mode='NLA_TRACKS', export_skins=True,
                          export_force_sampling=True, export_yup=True)
doc = json.loads(gltf.read_text()); b = doc['buffers'][0]; blob = (gltf.parent / b['uri']).read_bytes(); (gltf.parent / b['uri']).unlink()
del b['uri']; b['byteLength'] = len(blob); gltf.write_text(json.dumps(doc))
(prev / f'{NAME}.buffer.js').write_text('window.GLTF_BUFFER_B64="' + base64.b64encode(blob).decode() + '";\n')
exported = [x['name'] for x in doc.get('animations', [])]
write_manifest(exported)
print('ANIM OK', len(manifest), 'clips; exported animations:', exported, 'floor', round(FLOOR, 4))
