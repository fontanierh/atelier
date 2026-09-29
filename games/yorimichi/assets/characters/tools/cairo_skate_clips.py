"""Skateboarding rider clips for Cairo: game-r17 = game-r16 + the Skate* clips, regular and goofy.

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_skate_clips.py -- \
        [--parent game-r16] [--revision game-r17] [--only SkateStance,SkateOllie] [--scratch DIR] [--no-goofy] [--no-clipcheck]

The contract is games/yorimichi/docs/SKATE.md, "Rider clips". In every clip the board sits at its rest place under the rider and
the Root bone stays put; the game moves the board (pop, manual tilt, flips) and maps the limbs in contact through it.

Frames and units
- Rider frame (cm): origin at the Root bone's head on the ground (the standing sole level), +X the way the rig faces
  (the board's toe edge), +Y the rig's left, +Z up. Armature units x 148 = cm (measured: the exporter's
  1.48 / (top - floor) times the armature object scale gives 147.9999).
- Stance frame: `t` toward the toe edge (= +X), `a` along the board toward the nose, z up. Regular: +a = +Y (left foot
  forward); goofy mirrors it: +a = -Y, right foot forward. Every pose below is written once in the stance frame and
  solved on the real rig for each stance (the rig is not exactly symmetric, so goofy is re-solved, not copied).
- Deck-local (SKATE.md): x = a, y = t, z from the deck top centre (9.05 cm above the ground).

The solve per frame (armature space, `cairo_rig.Rig` FK table, no action assigned):
pelvis position and turn, spine and head (world angles), each foot placed by its centre or its ball on a deck spot (or
on the ground) with its heading, pitched and aligned to the deck surface (kicks and concave); the leg is a two-bone
solve with a knee pole; the shoe's deformed vertices (dual-quaternion skinning over Leg/Foot/ToeBase, as Blender's
armature modifier does for the outfit) are then pushed to touch the surface without going through it, and the leg is
solved again. Arms are FK (the library's arm helper, palms toward the body) or an IK grab of a deck edge: the palm
against the edge at the base of the fingers, thumb over the grip, fingers wrapping under, the forearm taking the
hand's roll so the wrist only bends.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, json, math, sys, time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, str(Path(__file__).parent))
from cairo_outfit_correctives import set_clip
from cairo_rig import Rig, BODY, HAND_PROPS, bn, q_axis, smooth, smoother, lerp, clamp, hermite, X, Y, Z

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
FPS = 60
UNIT = 148.0
OUTFIT = 'Body · outfit (Tripo skate r01)'
OB_SLOT = 'Cairo · Tripo body rig'
SUFFIX = ' · skate'
CLEAR = .12                            # cm the solver keeps between the shoe and the deck/ground


# ============================================================================ board (SKATE.md, deck-local cm)
class Board:
    LENGTH, WIDTH, KICK, KICK_RISE, CONCAVE, THICK = 80., 20.5, 13., 4.5, .9, 1.2
    TOP = 9.05
    KINGPIN, AXLE_Z, WHEEL_Y, WHEEL_R, WHEEL_W = 18., -6.35, 9.3, 2.65, 3.2
    HALF = WIDTH / 2
    END = LENGTH / 2 - WIDTH / 2          # where the rounded ends begin

    @classmethod
    def kick(cls, a):
        u = np.clip((np.abs(a) - (cls.LENGTH / 2 - cls.KICK)) / cls.KICK, 0, 1)
        return cls.KICK_RISE * u * u

    @classmethod
    def top(cls, a, t):
        """Deck top height above the ground (rest place): centre 9.05, concave rails +0.9, kicks +4.5 at the tips."""
        return cls.TOP + cls.CONCAVE * np.minimum(1, (np.asarray(t) / cls.HALF) ** 2) + cls.kick(a)

    @classmethod
    def inside(cls, a, t):
        a, t = np.abs(np.asarray(a, float)), np.abs(np.asarray(t, float))
        return (t <= cls.HALF) & ((a <= cls.END) | ((a - cls.END) ** 2 + t * t <= cls.HALF * cls.HALF))

    @classmethod
    def edge(cls, a):
        """Half-width of the outline at `a` (rounded ends)."""
        a = abs(a)
        if a <= cls.END: return cls.HALF
        return math.sqrt(max(0., cls.HALF ** 2 - (a - cls.END) ** 2))


def board_matrix(pitch=0., pivot=0., roll=0., lift=0.):
    """Board transform in the stance frame (cm): pitch nose-up (deg) about the ground line under the axle at a = pivot,
    roll (deg) about the long axis through the deck's mid-thickness, then lift. Acts on (t, a, z) column vectors."""
    Pv = Matrix.Translation((0, pivot, 0))
    pitch_m = Matrix.Rotation(math.radians(pitch), 4, 'X')       # +a (nose) rises for nose-up: rotation about +t
    axis_z = Board.TOP - Board.THICK / 2
    roll_m = Matrix.Translation((0, 0, axis_z)) @ Matrix.Rotation(math.radians(roll), 4, 'Y') @ Matrix.Translation((0, 0, -axis_z))
    return Matrix.Translation((0, 0, lift)) @ Pv @ pitch_m @ Pv.inverted() @ roll_m


# ============================================================================ stance and frames
class Stance:
    def __init__(self, goofy=False):
        self.goofy = goofy
        self.s = -1 if goofy else 1
        self.front, self.back = ('Right', 'Left') if goofy else ('Left', 'Right')
        self.side = {'F': self.front, 'B': self.back}
        self.name = 'goofy' if goofy else 'regular'


def quat_mul(a, b):
    aw, ax, ay, az = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    bw, bx, by, bz = b[..., 0], b[..., 1], b[..., 2], b[..., 3]
    return np.stack([aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw], -1)


class Shoe:
    """The outfit's shoe vertices for one side, deformed with dual-quaternion skinning over Leg/Foot/ToeBase exactly as
    the outfit's armature modifier (preserve volume) does, from an FK matrix table."""
    BONES = ('Leg', 'Foot', 'ToeBase')

    def __init__(self, side, outfit, arm, rig):
        self.side = side
        index = {outfit.vertex_groups[bn(side + b)].index: i for i, b in enumerate(self.BONES)}
        to_arm = arm.matrix_world.inverted() @ outfit.matrix_world
        rows, weights = [], []
        for v in outfit.data.vertices:
            w = np.zeros(3); total = 0.
            for g in v.groups:
                total += g.weight
                if g.group in index: w[index[g.group]] += g.weight
            if w[1] + w[2] < .05 or total <= 0: continue
            rows.append((to_arm @ v.co)[:]); weights.append(w / total)
        self.rest = np.array(rows); self.w = np.array(weights)
        self.rest_inv = [rig.rest[side + b].inverted() for b in self.BONES]
        self.rig = rig

    def points(self, M=None):
        M = M or self.rig.M
        qs, ds = [], []
        for b, inv in zip(self.BONES, self.rest_inv):
            D = M[self.side + b] @ inv
            q = D.to_quaternion(); t = D.translation
            qs.append([q.w, q.x, q.y, q.z])
            ds.append(0.5 * quat_mul(np.array([0., t.x, t.y, t.z]), np.array([q.w, q.x, q.y, q.z])))
        q, d = np.array(qs), np.array(ds)
        for i in (0, 2):
            if np.dot(q[i], q[1]) < 0: q[i], d[i] = -q[i], -d[i]
        Q = self.w @ q; Dd = self.w @ d
        n = np.linalg.norm(Q, axis=1, keepdims=True); Q = Q / n; Dd = Dd / n
        conj = Q * np.array([1., -1., -1., -1.])
        v = np.concatenate([np.zeros((len(self.rest), 1)), self.rest], 1)
        rotated = quat_mul(quat_mul(Q, v), conj)[:, 1:]
        trans = 2 * quat_mul(Dd, conj)[:, 1:]
        return rotated + trans


class Skater:
    """Poses the rig from stance-frame parameters (see BASE) and measures contacts."""

    def __init__(self, rig, outfit, arm):
        self.rig = rig
        self.origin = rig.rest['Root'].translation.copy(); self.origin.z = rig.floor
        self.shoe = {side: Shoe(side, outfit, arm, rig) for side in ('Left', 'Right')}
        rig.begin(); rig.fill()
        self.foot_ref, self.psi0, self.foot_len = {}, {}, {}
        for side in ('Left', 'Right'):
            pts = self.shoe[side].points()
            low = pts[pts[:, 2] < pts[:, 2].min() + .6 / UNIT]
            c = low[:, :2].mean(0); d = low[:, :2] - c
            _, V = np.linalg.eigh(d.T @ d); ax = V[:, 1] * (1 if V[0, 1] > 0 else -1)
            along = d @ ax; lat = d @ np.array([-ax[1], ax[0]])
            s0, s1 = along.min(), along.max(); mid_lat = .5 * (lat.min() + lat.max())
            base = Vector((*c, pts[:, 2].min()))
            axv, latv = Vector((ax[0], ax[1], 0)), Vector((-ax[1], ax[0], 0))
            centre = base + axv * (.5 * (s0 + s1)) + latv * mid_lat
            ball = base + axv * (s0 + .68 * (s1 - s0)) + latv * mid_lat
            Minv = rig.M[side + 'Foot'].inverted()
            # the ball lies on the toe part of the shoe (the rig's toe joint is at mid-shoe): it follows the toe bend
            self.foot_ref[side] = {'centre': Minv @ centre, 'ball': Minv @ ball, 'ball_toe': rig.M[side + 'ToeBase'].inverted() @ ball}
            self.psi0[side] = math.degrees(math.atan2(ax[1], ax[0]))
            self.foot_len[side] = (s1 - s0) * UNIT
        self.info = {}

    def ref_point(self, side, M, w):
        """Armature-space foot reference: the footprint centre (w = 0) to the ball of the foot (w = 1)."""
        r = self.foot_ref[side]
        return (M[side + 'Foot'] @ r['centre']).lerp(M[side + 'ToeBase'] @ r['ball_toe'], w)

    # ------------------------------------------------------------------ frames
    def arm_pt(self, t, a, z, st):
        """Stance-frame cm -> armature space."""
        return self.origin + Vector((t, st.s * a, z)) / UNIT

    def stance_pt(self, p, st):
        d = (Vector(p) - self.origin) * UNIT
        return Vector((d.x, st.s * d.y, d.z))

    def surface(self, pts_arm, st, g):
        """Height (armature units) of the support under each armature-space point: the deck top inside the outline,
        otherwise the ground; blended toward the ground by g (0 deck, 1 ground)."""
        cm = (pts_arm - np.array(self.origin[:])) * UNIT
        t, a = cm[:, 0], st.s * cm[:, 1]
        deck = np.where(Board.inside(a, t), Board.top(a, t), 0.)
        if g is not None: deck = deck * (1 - g)
        return deck / UNIT + self.origin.z

    # ------------------------------------------------------------------ pose
    def solve(self, P, st):
        """Pose one frame. A grabbing hand that cannot reach its edge lowers the pelvis a little (at most 8 cm) and the
        frame is solved again: the arms are short for this board."""
        drop = 0.
        for attempt in range(6):
            info = self._solve(dict(P, pz=P['pz'] - drop) if drop else P, st)
            excess = info.pop('reach_excess_cm', 0.)
            room = self.knee_room(st)
            if excess <= .02 or drop >= 8. or room <= .05: break
            drop = min(8., drop + min(excess * 1.5, room))
        info['reach_drop_cm'] = round(drop, 2)
        return info

    KNEE_MAX = 150.                           # deepest knee fold allowed (degrees of flexion): a full squat

    def knee_room(self, st):
        """How far (cm) the pelvis can still drop before a knee on the board folds past KNEE_MAX."""
        rig, room = self.rig, 99.
        for side in ('Left', 'Right'):
            a, b = rig.length[side + 'UpLeg'] * UNIT, rig.length[side + 'Leg'] * UNIT
            dmin = math.sqrt(a * a + b * b - 2 * a * b * math.cos(math.radians(180 - self.KNEE_MAX)))
            v = (rig.head(side + 'UpLeg') - rig.head(side + 'Foot')) * UNIT
            h2 = v.x * v.x + v.y * v.y
            if dmin * dmin <= h2: continue
            room = min(room, v.z - math.sqrt(dmin * dmin - h2))
        return room

    def _solve(self, P, st):
        rig = self.rig; s = st.s
        rig.begin()
        feet = {role: self.foot_frame(role, P, st) for role in ('F', 'B')}
        drop = 0.
        for _ in range(2):
            pelvis = self.arm_pt(P['px'], P['pa'], P['pz'] - drop, st)
            rig.hips(pelvis - rig.neutral_head['Hips'], pitch=P['pp'], yaw=s * P['py'], roll=s * P['pr'])
            need = 0.
            for role, f in feet.items():
                side = st.side[role]
                hip = rig.head(side + 'UpLeg'); reach = (rig.length[side + 'UpLeg'] + rig.length[side + 'Leg']) * .975
                A = f['ankle_guess']; dxy = math.hypot(A.x - hip.x, A.y - hip.y)
                if dxy < reach:
                    zmax = A.z + math.sqrt(reach * reach - dxy * dxy)
                    need = max(need, hip.z - zmax)
            if need <= 1e-6: break
            drop += need * UNIT + .05
        self.info = {'settle_cm': round(drop, 2)}
        rig.spine(P['sp'], s * P['sy'], s * P['sr'], head_pitch=P['hp'], head_yaw=s * P['hy'], head_roll=s * P['hr'])
        for role in ('F', 'B'):
            self.place_foot(role, feet[role], P, st)
        for role in ('F', 'B'):
            self.place_arm(role, P, st)
        for role in ('F', 'B'):
            side = st.side[role]
            rig.hand(side, curl=P[role + 'cu'], thumb=P[role + 'th'], opposition=P[role + 'op'], spread=P[role + 'fs'], index=P.get(role + 'ix'))
        return self.info

    def foot_frame(self, role, P, st):
        """Foot rotation, reference point and a first ankle guess for one foot."""
        rig = self.rig; side = st.side[role]; s = st.s
        yaw = s * P[role + 'h']
        q = q_axis(Z, yaw - self.psi0[side])
        lateral = q_axis(Z, yaw) @ Y
        q = Quaternion(lateral, math.radians(P[role + 'p'])) @ q
        roll = P.get(role + 'r', 0.)
        if roll: q = Quaternion(q_axis(Z, yaw) @ X, math.radians(s * roll)) @ q
        g, lift = clamp(P[role + 'g']), max(0., P[role + 'l'])          # Catmull-Rom can overshoot below the support
        target = self.arm_pt(P[role + 't'], P[role + 'a'], 0., st)
        R0 = (q @ rig.neutral[side + 'Foot']).to_matrix()
        # align to the deck surface under the footprint (kicks, concave), fading out toward the ground
        if g < 1:
            fp = self.footprint(side, R0, target)
            cm = (fp - np.array(self.origin[:])) * UNIT
            t_, a_ = cm[:, 0], st.s * cm[:, 1]
            ok = Board.inside(a_, t_)
            if ok.sum() >= 6:
                A = np.c_[cm[ok, 0], cm[ok, 1], np.ones(ok.sum())]
                coef, *_ = np.linalg.lstsq(A, Board.top(a_[ok], t_[ok]), rcond=None)
                n = Vector((-coef[0], -coef[1], 1)).normalized()
                n = n.lerp(Z, g).normalized()
                q = Z.rotation_difference(n) @ q
        R = q @ rig.neutral[side + 'Foot']
        ref = self.foot_ref[side]['centre'].lerp(self.foot_ref[side]['ball'], P[role + 'ref'])
        off = R.to_matrix() @ ref
        guess = target - off
        surf = float(self.surface(np.array([target[:]]), st, g)[0])
        guess.z = surf + lift / UNIT - off.z + .002
        pole = q_axis(Z, s * (P[role + 'h'] + P[role + 'kh'])) @ X
        pole = (pole + Vector((0, 0, P.get(role + 'ku', 0.)))).normalized()
        return {'R': R, 'ref': ref, 'w': P[role + 'ref'], 'target': target, 'ankle_guess': guess, 'pole': pole, 'g': g, 'lift': lift}

    def footprint(self, side, R, target):
        """Low sole points (rigid approximation) for a foot rotated by R with its centre at target (xy)."""
        rig = self.rig
        saved = {k: rig.M.get(k) for k in (side + 'Foot', side + 'ToeBase')}
        m = R.to_4x4(); rig.M[side + 'Foot'] = m
        rig.M[side + 'ToeBase'] = m @ rig.rest[side + 'Foot'].inverted() @ rig.rest[side + 'ToeBase']
        pts = self.shoe[side].points({**rig.M, side + 'Leg': rig.M.get(side + 'Leg', m @ rig.rest[side + 'Foot'].inverted() @ rig.rest[side + 'Leg'])})
        for k, v in saved.items():
            if v is None: rig.M.pop(k, None)
            else: rig.M[k] = v
        low = pts[pts[:, 2] < pts[:, 2].min() + 1.0 / UNIT]
        c = R @ self.foot_ref[side]['centre']
        return low - np.array([c.x, c.y, 0.]) + np.array([target.x, target.y, 0.])

    def place_foot(self, role, f, P, st):
        """Leg solve so the foot's reference point sits on its spot and the deformed shoe touches the support without
        going through it. The heel is skinned partly to the shin, so the lowest shoe point moves with the ankle angle:
        the height is found with secant steps (a full step oscillates when the heel swings faster than the ankle)."""
        rig = self.rig; side = st.side[role]
        A = f['ankle_guess'].copy()
        toe = P[role + 'toe']; want = (f['lift'] + CLEAR) / UNIT
        prev = None
        for it in range(16):
            for n in ('Leg', 'Foot', 'ToeBase'): rig.M.pop(side + n, None)      # two_bone reads the child's cached head
            rig.two_bone(side + 'UpLeg', side + 'Leg', A, f['pole'], extension=.995)
            rig.set_rot(side + 'Foot', f['R'])
            rig.M[side + 'ToeBase'] = rig.inherited(side + 'ToeBase')
            if toe: rig.bend(side + 'ToeBase', Y, -toe)
            pts = self.shoe[side].points()
            gap = float((pts[:, 2] - self.surface(pts, st, None)).min())
            achieved = self.ref_point(side, rig.M, f['w'])
            ex, ey, ez = f['target'].x - achieved.x, f['target'].y - achieved.y, want - gap
            if max(abs(ex), abs(ey), abs(ez)) < .0003 / UNIT: break
            slope = 1.
            if prev is not None and abs(A.z - prev[0]) > 1e-9:
                slope = min(4., max(.3, (gap - prev[1]) / (A.z - prev[0])))
            prev = (A.z, gap)
            A = A + Vector((ex, ey, ez / slope))
        self.info[role + '_gap_cm'] = round(gap * UNIT, 3)
        self.info[role + '_spot_err_cm'] = round(math.hypot(ex, ey) * UNIT, 3)

    def place_arm(self, role, P, st):
        rig = self.rig; side = st.side[role]; s = st.s
        chest_yaw = s * (P['py'] + P['sy'])
        dep, pro = P.get(role + 'cl', 0.), P.get(role + 'cp', 0.)
        if dep or pro:
            # the clavicle drops and comes forward when the hand reaches down (scapula depression and protraction)
            sgn = 1 if side == 'Left' else -1; carried = rig.parent_delta(side + 'Shoulder')
            q = Quaternion(carried @ X, math.radians(-sgn * dep)) @ Quaternion(carried @ Z, math.radians(-sgn * pro))
            rig.rotate(side + 'Shoulder', q)
        rig.arm(side, swing=P[role + 'sw'], spread=P[role + 'spr'], twist=P[role + 'tw'], elbow=P[role + 'el'],
                wrist_pitch=P[role + 'wp'], wrist_yaw=P[role + 'wy'], forearm_twist=P[role + 'ft'], yaw=chest_yaw, hinge=P[role + 'hi'])
        w = P.get(role + 'grab', 0.)
        spec = P.get(role + 'grip')
        if w <= 1e-4 or not spec: return
        fk_wrist = rig.head(side + 'Hand'); fk_hand = rig.rot(side + 'Hand'); fk_elbow = rig.head(side + 'ForeArm')
        G, Rg = self.grip_frame(side, spec, st)
        wrist = G - Rg.to_matrix() @ self.grip_local(side)
        shoulder = rig.head(side + 'Arm')
        reach = (rig.length[side + 'Arm'] + rig.length[side + 'ForeArm']) * .998
        self.info['reach_excess_cm'] = max(self.info.get('reach_excess_cm', 0.), ((wrist - shoulder).length - reach) * UNIT * smooth(w))
        bulge = Vector(spec.get('arc', (0, 0, 0)))
        arc = Vector((bulge.x, st.s * bulge.y, bulge.z)) / UNIT * math.sin(math.pi * clamp(w))
        target = fk_wrist.lerp(wrist, smooth(w)) + arc
        pole_ik = Vector(spec['pole']); pole_ik = Vector((pole_ik.x, st.s * pole_ik.y, pole_ik.z)).normalized()
        mid = (shoulder + target) / 2
        pole_fk = (fk_elbow - mid)
        pole = pole_fk.normalized().lerp(pole_ik, smooth(w)).normalized()
        for n in ('ForeArm', 'Hand'): rig.M.pop(side + n, None)
        rig.two_bone(side + 'Arm', side + 'ForeArm', target, pole, extension=.998)
        H = fk_hand.slerp(Rg if Rg.dot(fk_hand) >= 0 else -Rg, smooth(w))
        self.roll_forearm(side, H)
        rig.set_rot(side + 'Hand', H)
        achieved = rig.M[side + 'Hand'] @ self.grip_local(side)
        self.info[role + '_grip_err_cm'] = round((achieved - G).length * UNIT, 2) if w > .99 else None

    def grip_local(self, side):
        """Where the deck edge sits in the hand: against the palm at the base of the fingers (hand bone frame)."""
        pb = self.rig.obj.pose.bones
        mid = self.rig.rest[side + 'Hand'].inverted() @ self.rig.obj.data.bones[bn(side + 'HandMiddle1')].head_local
        sign = 1 if side == 'Right' else -1                      # palm normal: +X right, -X left
        return Vector((sign * .008, mid.y * .70, mid.z * .5))

    def grip_frame(self, side, spec, st):
        """Contact point and hand rotation for a grab. spec: edge 'toe'|'heel'|'nose'|'tail', a (or t for nose/tail)."""
        edge = spec['edge']
        if edge in ('toe', 'heel'):
            sgn = 1 if edge == 'toe' else -1
            a = spec['a']; tt = sgn * Board.edge(a)
            z = float(Board.top(a, tt)) - Board.THICK * .35
            G = self.arm_pt(tt + sgn * 1.0, a, z, st)
            inward = Vector((-sgn, 0, 0))
        else:
            sgn = 1 if edge == 'nose' else -1
            tt = spec.get('t', 0.)
            a = sgn * (Board.END + math.sqrt(max(0., Board.HALF ** 2 - tt ** 2)))
            z = float(Board.top(a - sgn * 1.5, tt)) - Board.THICK * .5 + 1.0
            G = self.arm_pt(tt, a + sgn * .7, z, st)
            inward = Vector((0, -sgn * st.s, 0))
        tilt = math.radians(spec.get('tilt', 50.))      # fingers point down and in, under the deck; the thumb goes over the grip
        fingers = (Vector((0, 0, -1)) * math.cos(tilt) + inward * math.sin(tilt)).normalized()
        palm = (inward - fingers * inward.dot(fingers)).normalized()
        twist = spec.get('twist', 0.)
        if twist: palm = Quaternion(fingers, math.radians(twist)) @ palm
        xl = palm if side == 'Right' else -palm
        zl = xl.cross(fingers)
        R = Matrix((xl, fingers, zl)).transposed().to_quaternion()
        return G, R

    def roll_forearm(self, side, H):
        """Turn the forearm about its own axis so the hand's rotation relative to it has no twist (the wrist only bends)."""
        rig = self.rig; fa = side + 'ForeArm'
        rest_rel = (rig.rest[fa].inverted() @ rig.rest[side + 'Hand']).to_quaternion()
        F0 = rig.rot(fa); axis = rig.direction(fa); head = rig.head(fa)

        def twist(angle):
            F = Quaternion(axis, angle) @ F0
            local = (F @ rest_rel).inverted() @ H
            return abs(2 * math.atan2(local.y, local.w)) if local.w >= 0 else abs(2 * math.atan2(-local.y, -local.w))
        best = min((twist(math.radians(d)), d) for d in range(-180, 181, 5))[1]
        lo, hi = math.radians(best - 5), math.radians(best + 5)
        for _ in range(30):
            m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if twist(m1) < twist(m2): hi = m2
            else: lo = m1
        rig.set_rot(fa, Quaternion(axis, (lo + hi) / 2) @ F0, head)


# ============================================================================ pose vocabulary (stance frame, regular)
# Pelvis px/pa/pz (cm: toward the toe edge, toward the nose, height of the Hips head above the ground), pp/py/pr pitch
# (forward +), yaw (toward the nose +), roll (nose-side hip up +). Spine sp/sy/sr and head hp/hy/hr (world; head yaw
# toward the nose +, pitch looking down +). Feet F (front) and B (back): a/t spot (cm), h heading (deg from the toe
# edge direction toward the nose: 90 points at the nose), l lift above the support (cm), p pitch (toes down +), toe
# (toes bent up +), g support (0 deck, 1 ground), ref (0 foot centre, 1 ball of the foot on the spot), kh knee heading
# relative to the foot. Arms (library FK helper): sw swing forward, spr spread out, tw twist, el elbow, wp/wy wrist,
# ft forearm twist, hi hinge; grab (0..1) blends to the IK grab given by `grip`. Hands: cu curl, th thumb, op, fs.
STANCE_H = {'F': 35., 'B': 10.}          # 55 and 80 degrees from the board axis
BASE = dict(px=-2.5, pa=-2.5, pz=62.0, pp=8., py=10., pr=0., sp=12., sy=8., sr=0., hp=8., hy=62., hr=0.,
            Fa=16., Ft=1., Fh=STANCE_H['F'], Fl=0., Fp=0., Ftoe=0., Fg=0., Fref=0., Fkh=4., Fr=0.,
            Ba=-21., Bt=1., Bh=STANCE_H['B'], Bl=0., Bp=0., Btoe=0., Bg=0., Bref=0., Bkh=-24., Br=0.,
            Fsw=6., Fspr=15., Ftw=0., Fel=20., Fwp=0., Fwy=0., Fft=0., Fhi=0., Fgrab=0.,
            Bsw=2., Bspr=15., Btw=0., Bel=18., Bwp=0., Bwy=0., Bft=0., Bhi=0., Bgrab=0.,
            Fcu=.28, Fth=.14, Fop=.1, Ffs=0., Bcu=.28, Bth=.14, Bop=.1, Bfs=0.)


def P_(**kw):
    p = dict(BASE); p.update(kw); return p


def both(**kw):
    out = {}
    for k, v in kw.items(): out['F' + k] = v; out['B' + k] = v
    return out


def keyed(keys, t, ease='flow', base=None):
    """Interpolate parameter dicts keyed at times (missing names hold)."""
    from cairo_rig import Timeline
    tl = Timeline([(k, {n: v for n, v in d.items() if not isinstance(v, (dict, str))}) for k, d in keys], base or BASE, ease=ease)
    return tl.at(t)


def wave(u, k=1, phase=0.):
    return math.sin(math.tau * (k * u + phase))


class SkateClip:
    def __init__(self, role, duration, fn, loop=False, hold=False, notes='', board=None, grips=None):
        self.role, self.fn, self.loop, self.hold, self.notes = role, fn, loop, hold, notes
        self.frames = round(duration * FPS) + 1
        self.duration = (self.frames - 1) / FPS
        self.board = board or (lambda t: dict(pitch=0., pivot=0., roll=0., lift=0.))
        self.grips = grips or {}

    def params(self, t):
        P = self.fn(t)
        for role, spec in self.grips.items(): P[role + 'grip'] = spec
        return P


# ---------------------------------------------------------------- riding stance
def stance_pose(t, T=2.0, fakie=False):
    u = t / T
    b = wave(u, 1, -.25)                      # one slow breath per loop
    sway = wave(u, 1)
    p = P_(pz=BASE['pz'] - .5 - .5 * b, px=BASE['px'] + .4 * sway, pa=BASE['pa'] + .6 * sway, pr=.8 * sway,
           sp=BASE['sp'] - 1.0 * b, sr=-.8 * sway, hp=BASE['hp'] - .8 * b, hy=BASE['hy'] + 3 * wave(u, 1, .1))
    p.update(Fsw=BASE['Fsw'] + 1.5 * b, Bsw=BASE['Bsw'] + 1.5 * b, Fspr=BASE['Fspr'] + .8 * b, Bspr=BASE['Bspr'] + .8 * b,
             Fel=BASE['Fel'] + 2 * b, Bel=BASE['Bel'] + 2 * b)
    if fakie:
        p.update(hy=-66 + 3 * wave(u, 1, .1), sy=-8., py=2., hp=9 - .8 * b)
    return p


# ---------------------------------------------------------------- ollie family
CROUCH = P_(px=-4., pa=-7., pz=49., pp=24., py=8., sp=16., sy=4., hp=26., hy=48.,
            Fa=8., Fh=25., Fkh=-6., Ba=-31., Bt=1., Bh=10., Bref=1., Bkh=-4.,
            **both(sw=24., spr=18., el=36., cu=.32, th=.16))
NOLLIE_CROUCH = P_(px=-4., pa=4., pz=49., pp=24., py=12., sp=16., sy=6., hp=26., hy=58.,
                   Fa=31., Ft=1., Fh=30., Fref=1., Fkh=-6., Ba=-8., Bh=12., Bkh=-4.,
                   **both(sw=24., spr=18., el=36., cu=.32, th=.16))
AIR = P_(px=-3., pa=-3., pz=BASE['pz'] - 18., pp=20., py=10., sp=14., sy=6., hp=22., hy=52.,
         Fa=16., Fh=32., Fkh=-4., Ba=-21., Bh=12., Bkh=0.,
         Fsw=22., Fspr=52., Fel=26., Bsw=16., Bspr=56., Bel=24., Fwp=-6., Bwp=-6., Fcu=.22, Bcu=.22, Fth=.1, Bth=.1)


def crouch_pose(t):
    return keyed([(0., BASE), (.2, CROUCH)], t, ease='smooth')


def nollie_crouch_pose(t):
    return keyed([(0., BASE), (.2, NOLLIE_CROUCH)], t, ease='smooth')


def ollie_pose(t):
    pop = dict(CROUCH, pz=61., px=-2., pp=10., sp=8., hp=16., hy=50., Fa=10., Fkh=-6., Bp=24., Btoe=26.,
               **both(sw=40., spr=34., el=30.))
    rise = dict(pop, pz=55., pp=14., sp=10., Fa=18., Bp=10., Btoe=10., Bref=.6, Ba=-28., **both(sw=34., spr=44., el=28.))
    drag = dict(AIR, pz=50., Fa=24., Fh=28., Ba=-24., Bref=.2, Bp=0., Btoe=0.)
    return keyed([(0., CROUCH), (.05, pop), (.12, rise), (.20, drag), (.45, AIR)], t)


def nollie_pose(t):
    pop = dict(NOLLIE_CROUCH, pz=61., px=-2., pp=10., sp=8., hp=16., Ba=-10., Fp=24., Ftoe=26.,
               **both(sw=40., spr=34., el=30.))
    rise = dict(pop, pz=55., pp=14., sp=10., Ba=-16., Fp=10., Ftoe=10., Fref=.6, Fa=26., **both(sw=34., spr=44., el=28.))
    drag = dict(AIR, pz=50., Ba=-26., Bh=14., Fa=20., Fref=.2, Fp=0., Ftoe=0.)
    return keyed([(0., NOLLIE_CROUCH), (.05, pop), (.12, rise), (.20, drag), (.45, AIR)], t)


def air_pose(t, T=1.0):
    u = t / T
    w, w2 = wave(u), wave(u, 1, .3)
    p = dict(AIR)
    p.update(pz=AIR['pz'] + .6 * w2, pr=1.2 * w, sr=-1.5 * w, hp=AIR['hp'] - 1 * w2,
             Fspr=AIR['Fspr'] + 5 * w, Bspr=AIR['Bspr'] - 5 * w, Fsw=AIR['Fsw'] + 3 * w2, Bsw=AIR['Bsw'] - 3 * w2,
             Fel=AIR['Fel'] + 3 * w2, Bel=AIR['Bel'] - 3 * w2)
    return p


def flip_pose(t):
    up = AIR['pz']
    kick = dict(AIR, pz=up + 3., Fa=27., Fl=11., Ft=-5., Fh=40., Fp=-8., Bl=9., Bp=6., **both(spr=58., sw=26.))
    top = dict(AIR, pz=up + 5., Fa=21., Fl=15., Ft=-1., Bl=15., Bp=4., hp=34., **both(spr=54., sw=24.))
    catch = dict(AIR, pz=up + 1., Fl=0., Bl=0.)
    return keyed([(0., AIR), (.03, dict(AIR, Fl=.2, Bl=.2)), (.08, kick), (.20, top), (.32, dict(AIR, pz=up + 2., Fl=3., Bl=3.)), (.38, catch), (.45, AIR)], t)


def land_pose(t):
    absorb = dict(BASE, pz=BASE['pz'] - 21., px=-4., pp=22., sp=18., hp=18., hy=56., Fkh=4., Bkh=-20.,
                  **both(sw=16., spr=40., el=30., cu=.26))
    return keyed([(0., AIR), (.12, absorb), (.26, dict(BASE, pz=BASE['pz'] - 4., **both(spr=18., el=22.))), (.35, BASE)], t)


# ---------------------------------------------------------------- push
BALL = .18 * 25.7                     # ball of the foot ahead of the foot centre (cm; shoe footprint 25.7 cm)


def ball_spot(a, t, h):
    r = math.radians(h)
    return a + BALL * math.sin(r), t + BALL * math.cos(r)


PUSH = dict(plant=.30, release=.62, stroke=44., plant_a=18., plant_t=26.)


def push_pose(t):
    fa, ft = ball_spot(BASE['Fa'], BASE['Ft'], BASE['Fh'])
    fb = dict(Fref=1., Fa=fa, Ft=ft)                    # the front foot pivots on its ball
    k0 = dict(BASE, **fb)
    turn = dict(k0, py=44., sy=12., hy=80., hp=10., pz=61., pa=2., px=0., Fh=62., Bl=2.5, Bh=18., Ba=-19., Bkh=4.,
                Fsw=-4., Bsw=10., **{'Bp': 4.})
    swing = dict(turn, py=62., sy=14., hy=86., pz=55., pa=7., px=2., Fh=76., Fkh=14., Bg=0., Bl=11., Ba=6., Bt=24., Bh=66.,
                 Bref=1., Bkh=-18., Bp=6., Fsw=-8., Bsw=4.)
    plant = dict(swing, pz=53., pa=8., px=3., pp=12., sp=12., Bg=1., Bl=0., Ba=PUSH['plant_a'], Bt=PUSH['plant_t'], Bh=82., Bp=9., Bkh=0.,
                 Fsw=-6., Bsw=-4., Fel=24., Bel=24.)
    mid = dict(plant, pz=51., pa=6., px=3.5, pr=3., pp=16., sp=14., Ba=PUSH['plant_a'] - PUSH['stroke'] / 2, Bp=15., Btoe=8., Fsw=-10., Bsw=14.)
    release = dict(plant, pz=48.5, pa=3.5, px=4., pr=6., pp=20., sp=16., Ba=PUSH['plant_a'] - PUSH['stroke'], Bp=38., Btoe=34., Fsw=-14., Bsw=26., Bel=28.)
    lift = dict(release, pz=52., pa=5., pr=2., Bg=1., Bl=9., Ba=-22., Bt=20., Bp=18., Btoe=6., Bh=60., Bkh=-14., Fsw=-6., Bsw=-4., Bspr=26., py=56.)
    back = dict(k0, py=26., sy=10., hy=70., pz=60., pa=0., Fh=46., Bg=0., Bl=6., Ba=-21., Bt=1., Bh=14., Bref=0., Bp=0., Btoe=0.,
                Bkh=0., Fsw=0., Bsw=6.)
    down = dict(k0, py=16., hy=66., pz=63.5, Fh=38., Bl=0.)
    keys = [(0., k0), (.10, turn), (.21, swing), (PUSH['plant'], plant), (.46, mid), (PUSH['release'], release),
            (.72, lift), (.84, back), (.90, down), (1.0, k0)]
    p = keyed(keys, t)
    if PUSH['plant'] <= t <= PUSH['release']:        # the planted foot stays still on the ground: it slides back at the board's speed
        u = (t - PUSH['plant']) / (PUSH['release'] - PUSH['plant'])
        p.update(Bg=1., Bl=0., Ba=PUSH['plant_a'] - PUSH['stroke'] * u, Bt=PUSH['plant_t'], Bref=1.)
    return p


# ---------------------------------------------------------------- brake
def brake_pose(t):
    fa, ft = ball_spot(BASE['Fa'], BASE['Ft'], BASE['Fh'])
    k0 = dict(BASE, Fref=1., Fa=fa, Ft=ft)
    turn = dict(k0, py=36., sy=10., hy=76., pz=59., pa=0., px=0., Fh=56., Bl=4., Ba=-22., Bt=5., Bh=30., Bkh=0., Fsw=-2., Bsw=8.)
    reach = dict(turn, py=50., sy=12., hy=82., pz=52., pa=2., px=2., Fh=66., Bg=1., Bl=3., Ba=-25., Bt=27., Bh=80., Bp=-3., Bkh=-10.,
                 Fsw=12., Bsw=-6., Fspr=20., Bspr=22., Fel=26., Bel=24.)
    drag = dict(reach, pz=50.5, pa=2.5, Bl=0., Bp=-2., pp=4., sp=6., Fsw=16., Bsw=-4.)
    return keyed([(0., k0), (.12, turn), (.26, reach), (.34, drag), (.40, drag)], t)


# ---------------------------------------------------------------- manuals
MANUAL = P_(pa=-20., px=-3., pz=57., pp=4., py=14., sp=10., sy=8., hp=12., hy=64., Ba=-24., Bh=10., Fa=15., Fh=32., Fkh=0., Bkh=-20.,
            Fsw=16., Fspr=62., Fel=22., Bsw=4., Bspr=68., Bel=20., Fwp=-8., Bwp=-8., Fcu=.2, Bcu=.2)
NOSE_MANUAL = P_(pa=13., px=-2., pz=55., pp=18., py=12., sp=12., sy=8., hp=24., hy=70., Fa=21., Fh=30., Ba=-15., Bh=12., Fkh=4., Bkh=-16.,
                 Fsw=20., Fspr=62., Fel=22., Bsw=8., Bspr=66., Bel=20., Fwp=-8., Bwp=-8., Fcu=.2, Bcu=.2)


def balance(base, t, T=1.0, amp=1.0):
    u = t / T; w, w2 = wave(u), wave(u, 2, .15)
    p = dict(base)
    p.update(pa=base['pa'] + 1.2 * amp * w, pr=base['pr'] + 1.6 * amp * w, sr=base['sr'] - 2.4 * amp * w, px=base['px'] + .5 * amp * w2,
             hy=base['hy'] + 2 * amp * w2, Fspr=base['Fspr'] + 7 * amp * w, Bspr=base['Bspr'] - 7 * amp * w,
             Fsw=base['Fsw'] + 4 * amp * w2, Bsw=base['Bsw'] - 3 * amp * w2, Fel=base['Fel'] + 3 * amp * w, Bel=base['Bel'] - 3 * amp * w)
    return p


# ---------------------------------------------------------------- grinds and slides
GRIND = P_(pa=-1., px=-3., pz=54., pp=16., py=10., sp=12., sy=6., hp=20., hy=66., Fa=18., Fh=30., Ba=-19., Bh=10.,
           Fsw=12., Fspr=70., Fel=18., Bsw=6., Bspr=72., Bel=16., Fwp=-6., Bwp=-6., Fcu=.2, Bcu=.2)
GRIND_TAIL = dict(GRIND, pa=-13., pz=53., pp=10., sp=8., hy=62., Fkh=2., Bkh=-24.)
GRIND_NOSE = dict(GRIND, pa=9., pz=52., pp=22., sp=16., hp=26., hy=70., Fkh=6., Bkh=-14.)
SLIDE = P_(pa=-2.5, px=-2., pz=50., pp=14., py=0., sp=10., sy=-2., hp=16., hy=14., Fh=30., Bh=8., Fkh=6., Bkh=-26.,
           Fsw=26., Fspr=78., Fel=16., Bsw=14., Bspr=80., Bel=14., Fwp=-6., Bwp=-6., Fcu=.18, Bcu=.18, Ffs=.25, Bfs=.25)


# ---------------------------------------------------------------- grabs (from SkateAir; reach by 0.18 s, hold)
GRAB_BODY = dict(AIR, pz=BASE['pz'] - 24., pp=28., sp=24., hp=34., hy=46., Fkh=18., Bkh=-45.)


def grab_pose(hands, body, t):
    reach = dict(body)
    for role in hands: reach.update({role + 'grab': 1., role + 'cu': .72, role + 'th': .5, role + 'op': .75, role + 'fs': 0., role + 'ix': .66,
                                     role + 'cl': body.get(role + 'cl', 20.), role + 'cp': body.get(role + 'cp', 20.)})
    hold = dict(reach)
    for k in ('pz', 'pp', 'sp'): hold[k] = reach[k] + {'pz': -.8, 'pp': 1.5, 'sp': 1.5}[k]
    p = keyed([(0., AIR), (.18, reach), (.36, hold), (.5, reach)], t)
    for role in hands: p[role + 'grab'] = smooth(t / .18)
    return p


GRABS = {
    # body numbers from a reach search on this rig (the arms are short: the pelvis folds low over the board and the
    # clavicle drops and comes forward), refined by a local search against the mesh clipping check (arm through the
    # baggy trousers), with the knees kept within 70 degrees of the feet, the torso roll within 28 degrees and the knee fold under 150
    'SkateGrabIndy': (('B',), dict(GRAB_BODY, pz=36.5, pp=29.5, sp=11., px=-1., pa=-1.5, py=23.5, sy=20., sr=22., hy=40., Fkh=41.5, Bkh=-68.,
                                   Fcp=17., Bcl=11.5, Bcp=15.5, Fsw=34., Fspr=66., Fel=22.),
                      {'B': dict(edge='toe', a=1.2, pole=(.01, .09, .24), arc=(3.8, -5.9, 3.9))}),
    'SkateGrabMelon': (('F',), dict(GRAB_BODY, pz=34., pp=11.5, sp=4.5, px=-1., pa=-1., py=12.5, sy=40., sr=-20., hy=62., hp=28., Fkh=-10., Bkh=-33.,
                                    Fcl=23., Bsw=40., Bspr=78., Bel=20.),
                       {'F': dict(edge='heel', a=11., pole=(-.25, .52, .05), arc=(-6.6, 0., 6.5), tilt=35.)}),
    'SkateGrabNose': (('F',), dict(GRAB_BODY, pz=37., pp=32.5, sp=9.5, px=-1.5, pa=8., py=19., sy=1.5, sr=-9.5, hy=74., hp=32., Fkh=-5., Bkh=-31.,
                                   Fcl=23., Bsw=26., Bspr=72., Bel=22.),
                      {'F': dict(edge='nose', t=0., pole=(-.01, .25, 1.1), tilt=20., arc=(1., 1.8, -2.9))}),
    'SkateGrabTail': (('B',), dict(GRAB_BODY, pz=42., pp=40., sp=0., px=-1., pa=-5.5, py=-12., sy=-22.5, sr=20., hy=-10., hp=36., Fkh=25.5, Bkh=-23.,
                                   Fcl=2.5, Fcp=26., Bcl=22.5, Bcp=26.5, Fsw=30., Fspr=70., Fel=22.),
                      {'B': dict(edge='tail', t=0., pole=(.41, -1.39, .77), tilt=20., arc=(-3.1, 2.5, -5.8))}),
    'SkateGrabMethod': (('F',), dict(GRAB_BODY, pz=35., pp=3., sp=12., px=-3., pa=-9., py=-5., sy=20., sr=-28., hy=40., hp=6., Fkh=-43., Bkh=-62.,
                                     Fcl=23., Fcp=16., Bsw=-20., Bspr=96., Bel=30.),
                        {'F': dict(edge='heel', a=7.3, pole=(.29, 1.06, .04), arc=(-7.6, 1.6, 2.5), tilt=35.)}),
    'SkateGrabStalefish': (('B',), dict(GRAB_BODY, pz=32.5, pp=-19., sp=26.5, px=2.5, pa=5.5, py=-.5, sy=-29.5, sr=28., hy=40., Fkh=57., Bkh=-43.,
                                        Bcl=27.5, Bcp=9., Fsw=34., Fspr=70., Fel=22.),
                           {'B': dict(edge='heel', a=-2.9, pole=(-.96, -.58, -.83), arc=(-12.6, -10.7, -1.), tilt=35.)}),
    'SkateGrabDouble': (('F', 'B'), dict(GRAB_BODY, pz=29.5, pp=37., sp=20., px=.5, pa=-2., py=33.5, sy=29., sr=-26., hy=56., Fkh=5.5, Bkh=-64.5,
                                         Fcl=21.5, Fcp=30., Bcl=17., Bcp=23.),
                        {'B': dict(edge='toe', a=4.6, pole=(.82, .24, 1.29), arc=(8.9, -6.1, -2.6)),
                         'F': dict(edge='heel', a=16.9, pole=(-.65, .04, .2), arc=(5.3, 5.1, 1.5), tilt=35.)}),
}


# ---------------------------------------------------------------- powerslide and carves
POWERSLIDE = P_(px=-9., pa=-2.5, pz=50., pp=-2., py=-4., sp=10., sy=-4., hp=6., hy=10., Fh=26., Bh=6., Fkh=6., Bkh=-20.,
                Fsw=56., Fspr=18., Fel=24., Bsw=50., Bspr=18., Bel=24., Fcu=.3, Bcu=.3)
CARVE_TOE = P_(px=7., pz=56., pp=20., sp=16., hy=56., hp=12., pr=0., Fkh=-4., Bkh=-14., Fsw=34., Fspr=34., Fel=26., Bsw=-16., Bspr=28., Bel=20.)
CARVE_HEEL = P_(px=-10., pz=55., pp=-2., sp=6., hy=62., hp=8., Fsw=40., Fspr=22., Fel=26., Bsw=34., Bspr=20., Bel=24.)


def settle_into(pose, T):
    return lambda t: keyed([(0., BASE), (T, pose)], t)


def eased(rows, t):
    """Piecewise smoothstep through (time, value) rows: no overshoot between keys."""
    if t <= rows[0][0]: return rows[0][1]
    for (t0, v0), (t1, v1) in zip(rows, rows[1:]):
        if t <= t1: return lerp(v0, v1, smooth((t - t0) / (t1 - t0)))
    return rows[-1][1]


def rear_pitch(schedule):
    """Board nose-up pitch about the rear wheels from (time, degrees) rows (the review preview of the game's pop)."""
    return lambda t: dict(pitch=eased(schedule, t), pivot=-Board.KINGPIN, roll=0., lift=0.)


def front_pitch(schedule):
    return lambda t: dict(pitch=-eased(schedule, t), pivot=Board.KINGPIN, roll=0., lift=0.)


OLLIE_PITCH = [(0., 0.), (.05, 30.), (.12, 20.), (.24, 0.), (.45, 0.)]


def flip_board(t):
    u = clamp((t - .08) / (.36 - .08))
    return dict(pitch=0., pivot=0., roll=360. * smooth(u), lift=6. * math.sin(math.pi * u))


CLIPS = {c.role: c for c in [
    SkateClip('SkateStance', 2.0, stance_pose, loop=True, notes='riding stance, soft knees, weight centred, head to the nose, slow breathing sway'),
    SkateClip('SkateStanceFakie', 2.0, lambda t: stance_pose(t, fakie=True), loop=True, notes='riding stance looking back over the back shoulder toward the tail'),
    SkateClip('SkatePush', 1.0, push_pose, loop=True, notes='front foot swivels on its ball to point along the board, body turns forward, back foot plants beside the front truck, strokes back 44 cm, returns to the tail'),
    SkateClip('SkateCrouch', .2, crouch_pose, hold=True, notes='ollie load: deep crouch, back foot ball on the tail, front foot behind the front bolts'),
    SkateClip('SkateNollieCrouch', .2, nollie_crouch_pose, hold=True, notes='nollie load: front foot ball on the nose, back foot behind the back bolts'),
    SkateClip('SkateOllie', .45, ollie_pose, board=rear_pitch(OLLIE_PITCH), notes='pop, front foot drags up the grip, knees up; ends in SkateAir'),
    SkateClip('SkateNollie', .45, nollie_pose, board=front_pitch(OLLIE_PITCH), notes='nollie pop from the nose; ends in SkateAir'),
    SkateClip('SkateAir', 1.0, air_pose, loop=True, notes='air tuck, knees up, feet on the deck, arms out'),
    SkateClip('SkateFlip', .45, flip_pose, board=flip_board, notes='flick: both feet leave the deck, 15 cm up at 0.2 s, catch at 0.38 s'),
    SkateClip('SkateLand', .35, land_pose, notes='touchdown from SkateAir: absorb, rise to the stance'),
    SkateClip('SkateBrake', .4, brake_pose, hold=True, notes='foot brake: back foot leaves the tail and drags its sole flat on the ground beside the tail, weight on the front leg'),
    SkateClip('SkateManual', 1.0, lambda t: balance(MANUAL, t), loop=True, board=lambda t: dict(pitch=11., pivot=-Board.KINGPIN, roll=0., lift=0.),
              notes='manual: hips over the back foot, arms out, balancing (the game tilts the board nose-up 11 deg)'),
    SkateClip('SkateNoseManual', 1.0, lambda t: balance(NOSE_MANUAL, t), loop=True, board=lambda t: dict(pitch=-11., pivot=Board.KINGPIN, roll=0., lift=0.),
              notes='nose manual: hips over the front foot, arms out, balancing (the game tilts the board nose-down 11 deg)'),
    SkateClip('SkateGrind', 1.0, lambda t: balance(GRIND, t), loop=True, notes='50-50: crouched over the trucks, arms wide, looking down the line'),
    SkateClip('SkateGrindTail', 1.0, lambda t: balance(GRIND_TAIL, t), loop=True, notes='5-0 / smith / feeble: weight over the back truck'),
    SkateClip('SkateGrindNose', 1.0, lambda t: balance(GRIND_NOSE, t), loop=True, notes='nosegrind / crooked: weight over the front truck'),
    SkateClip('SkateSlide', 1.0, lambda t: balance(SLIDE, t, amp=1.2), loop=True, notes='boardslide family: lower, arms wide, square to +X and looking along the rail'),
    *[SkateClip(role, .5, (lambda h, b: (lambda t: grab_pose(h, b, t)))(hands, body), grips=grips,
                notes={'SkateGrabIndy': 'indy: back hand grabs the toe edge between the feet',
                       'SkateGrabMelon': 'melon: front hand reaches behind the front leg to the heel edge',
                       'SkateGrabNose': 'nose grab: front hand to the nose', 'SkateGrabTail': 'tail grab: back hand to the tail',
                       'SkateGrabMethod': 'method: front hand on the heel edge, knees bent back, chest up',
                       'SkateGrabStalefish': 'stalefish: back hand behind the back leg to the heel edge',
                       'SkateGrabDouble': 'double: indy with the back hand and melon with the front hand'}[role])
      for role, (hands, body, grips) in GRABS.items()],
    SkateClip('SkatePowerslide', .6, settle_into(POWERSLIDE, .6), hold=True, notes='powerslide: square to the travel (+X), weight back toward the heel edge, knees bent, arms forward'),
    SkateClip('SkateCarveToe', .5, settle_into(CARVE_TOE, .5), hold=True, notes='toe-side carve: knees and hips toward the toe edge'),
    SkateClip('SkateCarveHeel', .5, settle_into(CARVE_HEEL, .5), hold=True, notes='heel-side carve: sitting back toward the heel edge'),
]}


# ============================================================================ mesh clipping check
REGIONS = {'Llower': ('LeftForeArm', 'LeftHand'), 'Rlower': ('RightForeArm', 'RightHand'), 'Lupper': ('LeftArm',), 'Rupper': ('RightArm',),
           'Lleg': ('LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase'), 'Rleg': ('RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase')}
PAIRS = [('Llower', ('torso', 'Lleg', 'Rleg', 'Rlower', 'Rupper')), ('Rlower', ('torso', 'Lleg', 'Rleg', 'Llower', 'Lupper')),
         ('Lupper', ('Lleg', 'Rleg')), ('Rupper', ('Lleg', 'Rleg')), ('Lleg', ('Rleg',))]


def region_of(name):
    n = name.replace('mixamorig:', '')
    for side, S in (('Left', 'L'), ('Right', 'R')):
        if n.startswith(side):
            rest = n[len(side):]
            if rest.startswith('Hand') or rest == 'ForeArm': return S + 'lower'
            if rest == 'Arm': return S + 'upper'
            if rest in ('UpLeg', 'Leg', 'Foot', 'ToeBase'): return S + 'leg'
    return 'torso'


class ClipCheck:
    """Edges of one body region passing through faces of another, on the deformed visible meshes (outfit, hands and
    forearms, head, neck piece). Counts are compared with the standing pose, where the Tripo outfit already has a few."""

    def __init__(self, objects, unit=UNIT / .9995):
        self.objects = objects; self.unit = unit        # world metres -> cm (the armature object is scaled 0.9995)
        self.labels, self.faces, self.edges, offset = [], [], [], 0
        for ob in objects:
            names = {g.index: g.name for g in ob.vertex_groups}
            for v in ob.data.vertices:
                best = max(v.groups, key=lambda g: g.weight, default=None)
                self.labels.append(region_of(names[best.group]) if best else 'torso')
            self.faces += [tuple(offset + i for i in p.vertices) for p in ob.data.polygons]
            self.edges += [(offset + e.vertices[0], offset + e.vertices[1]) for e in ob.data.edges]
            offset += len(ob.data.vertices)
        lab = self.labels
        face_region = []
        for f in self.faces:
            rs = {lab[i] for i in f}
            face_region.append(rs.pop() if len(rs) == 1 else None)
        self.src, self.tgt = {}, {}
        for src, targets in PAIRS:
            self.src[src] = [e for e in self.edges if lab[e[0]] == src and lab[e[1]] == src]
            for tg in targets:
                self.tgt[tg] = [f for f, r in zip(self.faces, face_region) if r == tg]

    def coords(self):
        dg = bpy.context.evaluated_depsgraph_get(); out = []
        for ob in self.objects:
            ev = ob.evaluated_get(dg); M = ev.matrix_world
            out += [M @ v.co for v in ev.data.vertices]
        return out

    def frame(self):
        co = self.coords(); res = {}
        trees = {tg: BVHTree.FromPolygons(co, faces, all_triangles=False) for tg, faces in self.tgt.items() if faces}
        for src, targets in PAIRS:
            for tg in targets:
                tree = trees.get(tg); n = 0; depth = 0.
                if tree:
                    ends = set()
                    for e0, e1 in self.src[src]:
                        d = co[e1] - co[e0]; L = d.length
                        if L > 1e-7 and tree.ray_cast(co[e0], d / L, L)[0] is not None: n += 1; ends.update((e0, e1))
                    for i in ends:        # how far the pierced part sits behind the target surface (cloth over cloth: a few mm)
                        loc, nrm, _, dist = tree.find_nearest(co[i])
                        if loc is not None and (co[i] - loc).dot(nrm) < 0: depth = max(depth, dist)
                res[f'{src}>{tg}'] = n
                res[f'{src}>{tg} depth_cm'] = round(depth * self.unit, 2)
        return res


# ============================================================================ build
class Builder:
    def __init__(self, parent, revision):
        self.parent_dir, self.rev = ASSET / parent, revision
        record = json.loads((self.parent_dir / 'source-manifest.json').read_text())
        source = ROOT / record['native']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['native_sha256'], f'{parent} changed'
        self.record, self.source = record, source
        bpy.ops.wm.open_mainfile(filepath=str(source))
        self.scene = bpy.context.scene; self.scene.render.fps = FPS
        self.arm = next(o for o in self.scene.objects if o.type == 'ARMATURE')
        for a in [a for a in bpy.data.actions if a.name.endswith(SUFFIX)]: bpy.data.actions.remove(a)
        self.library = {a.name: self.signature(a) for a in bpy.data.actions}
        self.outfit = bpy.data.objects[OUTFIT]
        set_clip(self.arm, bpy.data.actions['Standing · outfit review']); self.scene.frame_set(1)
        dg = bpy.context.evaluated_depsgraph_get()
        visible = [o for o in self.scene.objects if o.type == 'MESH' and (o.get('outfit_slot') or (o.get('body_region') and not o.get('hidden_by_slot')))]
        pts = []
        for o in visible:
            ev = o.evaluated_get(dg); used = {i for f in ev.data.polygons for i in f.vertices}
            pts += [(ev.matrix_world @ ev.data.vertices[i].co).z for i in used]
        floor, top = min(pts), max(pts)
        self.unit = self.arm.matrix_world.to_scale().x * 1.48 / (top - floor) * 100
        self.export_scale, self.export_floor = 1.48 / (top - floor), floor
        assert abs(self.unit - UNIT) < .05, ('armature unit to cm changed', self.unit)
        ev = self.outfit.evaluated_get(dg)
        floor_world = min((ev.matrix_world @ v.co).z for v in ev.data.vertices)
        self.rig = Rig(self.arm, self.scene, self.outfit, floor_world)
        self.skater = Skater(self.rig, self.outfit, self.arm)
        self.visible = visible
        self.report = {'unit_cm_per_armature_unit': round(self.unit, 4), 'floor_armature_z': self.rig.floor,
                       'root_head_armature': list(self.skater.origin),
                       'foot_psi0_deg': self.skater.psi0, 'footprint_length_cm': self.skater.foot_len}
        self.last = {}

    @staticmethod
    def signature(action):
        h = hashlib.sha256()
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        h.update(f'{fc.data_path}[{fc.array_index}]'.encode())
                        for k in fc.keyframe_points: h.update(np.array([*k.co, *k.handle_left, *k.handle_right], np.float32).tobytes())
        return h.hexdigest()

    # ------------------------------------------------------------ author one clip
    def author(self, clip, st):
        name = clip.role + ('Goofy' if st.goofy else '')
        action = bpy.data.actions.new(name + SUFFIX); action.use_fake_user = True
        slot = action.slots.new(id_type='OBJECT', name=OB_SLOT)
        self.arm.animation_data.action = action; self.arm.animation_data.action_slot = slot
        rig, last, frames = self.rig, {}, []
        for f in range(1, clip.frames + 1):
            t = (f - 1) / FPS
            if clip.loop and f == clip.frames: t = 0.
            P = clip.params(t)
            info = self.skater.solve(P, st)
            rig.apply(); rig.key(f, last)
            frames.append({'t': round((f - 1) / FPS, 4), 'P': {k: v for k, v in P.items() if not isinstance(v, dict)},
                           'grip': {r: P.get(r + 'grip') for r in 'FB' if P.get(r + 'grip')}, 'solve': dict(info)})
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for k in fc.keyframe_points: k.interpolation = 'LINEAR'
                        if clip.loop: fc.modifiers.new('CYCLES')
        self.arm.animation_data.action = None
        return name, action, frames

    # ------------------------------------------------------------ measure the keyed clip
    def measure(self, clip, st, name, action, frames, clipcheck=None, clip_step=3):
        set_clip(self.arm, action); pb = self.arm.pose.bones; sk = self.skater
        rows, contact = [], {'foot_F': [], 'foot_B': [], 'hand_F': [], 'hand_B': [], 'ground_F': [], 'ground_B': []}
        clips = []
        for i, fr in enumerate(frames):
            f = i + 1; self.scene.frame_set(f)
            M = {n: pb[bn(n)].matrix.copy() for n in BODY}
            P = fr['P']; row = {'t': fr['t']}
            for role in 'FB':
                side = st.side[role]
                pts = sk.shoe[side].points(M)
                surf = sk.surface(pts, st, None)
                d = pts[:, 2] - surf
                cm = (pts - np.array(sk.origin[:])) * UNIT
                over = Board.inside(st.s * cm[:, 1], cm[:, 0])
                gap = float(d.min()) * UNIT
                deck_gap = float(d[over].min()) * UNIT if over.any() else None
                ground_gap = float(d[~over].min()) * UNIT if (~over).any() else None
                spot = sk.ref_point(side, M, P[role + 'ref'])
                spot_cm = sk.stance_pt(spot, st)
                on_deck = deck_gap is not None and deck_gap <= .5 and P[role + 'g'] < .5
                on_ground = ground_gap is not None and ground_gap <= .5 and P[role + 'g'] > .5
                hip, knee, ank = M[side + 'UpLeg'].translation, M[side + 'Leg'].translation, M[side + 'Foot'].translation
                flex = math.degrees((knee - hip).angle(ank - knee))
                pole_side = (knee - (hip + ank) / 2).dot(q_axis(Z, st.s * (P[role + 'h'] + P[role + 'kh'])) @ X) * UNIT
                row[role] = dict(gap=round(gap, 3), deck_gap=None if deck_gap is None else round(deck_gap, 3),
                                 ground_gap=None if ground_gap is None else round(ground_gap, 3),
                                 spot=[round(spot_cm.x, 2), round(spot_cm.y, 2), round(spot_cm.z, 2)],
                                 spot_err=round(math.hypot(spot_cm.x - P[role + 't'], spot_cm.y - P[role + 'a']), 3),
                                 on_deck=bool(on_deck), on_ground=bool(on_ground), knee_flex=round(flex, 1), knee_forward_cm=round(pole_side, 2))
                contact['foot_' + role].append(on_deck); contact['ground_' + role].append(on_ground)
                w = P.get(role + 'grab', 0.); holding = w >= .98 and role in fr['grip']
                contact['hand_' + role].append(bool(holding))
                if holding:
                    G, _ = sk.grip_frame(side, fr['grip'][role], st)
                    row[role]['grip_err'] = round((M[side + 'Hand'] @ sk.grip_local(side) - G).length * UNIT, 2)
            row['hips'] = [round(v, 2) for v in sk.stance_pt(M['Hips'].translation, st)]
            row['settle_cm'] = fr['solve'].get('settle_cm', 0.)
            row['reach_drop_cm'] = fr['solve'].get('reach_drop_cm', 0.)
            rows.append(row)
            if clipcheck and (i % clip_step == 0 or i == len(frames) - 1):
                clips.append((f, clipcheck.frame()))
                row['clipping'] = {k: v for k, v in clips[-1][1].items() if v}
        # loop closure
        closure = None
        if clip.loop:
            self.scene.frame_set(1); a = {n: pb[bn(n)].matrix.copy() for n in BODY}
            self.scene.frame_set(clip.frames); b = {n: pb[bn(n)].matrix.copy() for n in BODY}
            closure = dict(rotation_deg=round(max(math.degrees(a[n].to_quaternion().rotation_difference(b[n].to_quaternion()).angle) for n in BODY), 4),
                           position_cm=round(max((a[n].translation - b[n].translation).length for n in BODY) * UNIT, 4))
        # steps between frames (pops)
        intervals = {k: self.intervals(v, clip) for k, v in contact.items()}
        on = [(r, role) for r in rows for role in 'FB' if r[role]['on_deck']]
        summary = dict(
            frames=len(rows), duration=clip.duration, loop=clip.loop,
            max_spot_err_cm=round(max((r[role]['spot_err'] for r, role in on), default=0.), 3),
            max_deck_penetration_cm=round(max((max(0., -r[role]['deck_gap']) for r in rows for role in 'FB' if r[role]['deck_gap'] is not None), default=0.), 3),
            max_ground_penetration_cm=round(max((max(0., -r[role]['ground_gap']) for r in rows for role in 'FB' if r[role]['ground_gap'] is not None), default=0.), 3),
            max_contact_gap_cm=round(max((r[role]['deck_gap'] for r, role in on), default=0.), 3),
            knee_flex_range=[min(r[role]['knee_flex'] for r in rows for role in 'FB'), max(r[role]['knee_flex'] for r in rows for role in 'FB')],
            min_knee_forward_cm=min(r[role]['knee_forward_cm'] for r in rows for role in 'FB'),
            max_settle_cm=max(r['settle_cm'] for r in rows), max_reach_drop_cm=max(r['reach_drop_cm'] for r in rows),
            max_grip_err_cm=max((r[role].get('grip_err', 0.) for r in rows for role in 'FB'), default=0.),
            loop_closure=closure, intervals=intervals)
        if clips:
            keys = clips[0][1].keys()
            summary['clipping'] = {k: dict(max=max(c[k] for _, c in clips), frame=max(clips, key=lambda x: x[1][k])[0]) for k in keys}
        self.arm.animation_data.action = None
        return summary, rows

    @staticmethod
    def intervals(flags, clip):
        out, start = [], None
        for i, f in enumerate(flags + [False]):
            if f and start is None: start = i
            if not f and start is not None:
                out.append([round(start / FPS, 4), round((i - 1) / FPS, 4)]); start = None
        return out

    # ------------------------------------------------------------ save
    def save_scratch(self, folder, results):
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        set_clip(self.arm, bpy.data.actions['Idle · library']); self.scene.frame_set(1)
        for name, sig in self.library.items(): assert self.signature(bpy.data.actions[name]) == sig, name
        bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'skate-scratch.blend'), copy=True)
        (folder / 'skate-scratch.json').write_text(json.dumps({'report': self.report, 'clips': results}, indent=1) + '\n')
        print('SCRATCH_READY', folder, flush=True)

    def save(self, results, per_frame):
        out = ASSET / self.rev; out.mkdir(exist_ok=True)
        (out / '.gitignore').write_text('diagnostics/\n*.blend1\n')
        for name, sig in self.library.items(): assert self.signature(bpy.data.actions[name]) == sig, name
        set_clip(self.arm, bpy.data.actions['Idle · library']); self.scene.frame_set(1)
        native = out / f'WarmOriginal-Game-{self.rev[5:]}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(native))
        record = self.record
        record['roles'] = [r for r in record['roles'] if not r['role'].startswith('Skate')]
        for name, res in results.items():
            clip = CLIPS[res['role']]
            record['roles'].append(dict(
                role=name, clip=name + SUFFIX, mapping='skate rider clip (SKATE.md)', fps=FPS, frames=clip.frames,
                duration_seconds=clip.duration, loop=clip.loop, kind='loop' if clip.loop else ('hold' if clip.hold else 'one-shot'),
                hold_last_frame=clip.hold, skate=True, stance=res['stance'], travel=None, tested_play_rate=1.0,
                root_motion='in place; the board actor owns translation and rotation', yaw_ownership='board',
                notes=clip.notes, contacts=limb_contacts(res), validation_record='skate-build.json'))
        record.update(native=str(native.relative_to(ROOT)), native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                      parent_source=str(self.source.relative_to(ROOT)), parent_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
                      revision=self.rev, changed_actions=[n + SUFFIX for n in results], other_parent_actions_preserved=True,
                      note=f'{self.rev}: {self.parent_dir.name} plus the skateboarding rider clips (cairo_skate_clips.py). '
                           'Meshes, weights, rig, sword and every other clip unchanged.')
        (out / 'source-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
        for f in ('combat-build.json', 'locomotion-build.json'):
            if (self.parent_dir / f).exists(): (out / f).write_text((self.parent_dir / f).read_text())
        (out / 'diagnostics').mkdir(exist_ok=True)
        (out / 'diagnostics' / 'skate-per-frame.json').write_text(json.dumps(per_frame) + '\n')
        print('REVISION_READY', self.rev, native, flush=True)
        return out


def run(args):
    started = time.time()
    b = Builder(args.parent, args.revision)
    roles = [r for r in CLIPS if not args.only or r in args.only.split(',')]
    stances = [Stance(False)] + ([] if args.no_goofy else [Stance(True)])
    authored = []
    for st in stances:
        for role in roles:
            name, action, frames = b.author(CLIPS[role], st)
            authored.append((role, st, name, action, frames))
            print('AUTHORED', name, f'{time.time() - started:.0f}s', flush=True)
    check = None
    if not args.no_clipcheck:
        check = ClipCheck(b.visible)
        set_clip(b.arm, bpy.data.actions['Standing · outfit review']); b.scene.frame_set(1)
        b.report['clipping_baseline_standing'] = check.frame()
    results, per_frame = {}, {}
    for role, st, name, action, frames in authored:
        summary, rows = b.measure(CLIPS[role], st, name, action, frames, check, args.clip_step)
        summary.update(role=role, stance=st.name)
        results[name] = summary; per_frame[name] = rows
        print('MEASURED', name, json.dumps({k: v for k, v in summary.items() if k not in ('intervals',)}), flush=True)
    if args.scratch:
        b.save_scratch(args.scratch, {'summary': results, 'per_frame': per_frame})
    else:
        out = b.save(results, per_frame)
        write_build(out, b, results, per_frame)
        write_readme(out, b, results, per_frame)
    print('DONE', f'{time.time() - started:.0f}s', flush=True)


def limb_contacts(res):
    """Per limb (foot_L, foot_R, hand_L, hand_R) the [t0, t1] seconds on the board; front/back mapped by the stance."""
    m = {'regular': {'F': 'L', 'B': 'R'}, 'goofy': {'F': 'R', 'B': 'L'}}[res['stance']]; iv = res['intervals']
    out = {f'foot_{m[r]}': iv['foot_' + r] for r in 'FB'}
    out.update({f'hand_{m[r]}': iv['hand_' + r] for r in 'FB'})
    ground = {f'foot_{m[r]}': iv['ground_' + r] for r in 'FB' if iv['ground_' + r]}
    if ground: out['on_ground'] = ground
    return out


README_HEAD = """# {rev}: skateboarding rider clips (regular and goofy)

28 September 2026. `WarmOriginal-Game-{num}.blend` is `{parent}` plus {count} actions named `<Role> · skate`, built by
`japan/tools/warm_skate_clips.py` for the native skate system (contract: `games/yorimichi/docs/SKATE.md`, "Rider clips"). Every
{parent} action is unchanged (curve signatures asserted before saving). Not reviewed by the user yet.

- **Frame.** The rig faces +X, left +Y, up +Z; the Root bone stays put and the rider frame's origin is its head on the
  ground (the standing sole level). The board lies across the rider at its rest place in every clip: nose toward +Y for
  regular (toward -Y for the `Goofy` copies), toe edge toward +X, deck top 9.05 cm. Armature units x 148 = cm (measured).
  In the exported mesh's component space the Root head is at {root} cm and the deck top centre at {deck} cm (UE axes):
  the mesh attaches to the board frame so the Root head sits on the board's ground point.
- **Feet.** Each foot is placed by the centre (or the ball) of its shoe footprint on a deck spot with its angle to the
  board, aligned to the deck surface (concave, kicks); the deformed shoe (its heel is skinned partly to the shin) is then
  pushed to touch the grip without going through it. Riding stance: front foot centre (+16, +1), 55 deg from the board
  axis; back foot (-21, +1), 80 deg (deck-local cm).
- **Contacts.** `skate-build.json` lists, per clip and limb (foot_L, foot_R, hand_L, hand_R), the [t0, t1] seconds on
  the board (sole within 0.5 cm of the deck; hands holding), the push plant/release and planted position, the measured
  stance spots and every check below. The manifest roles carry the same contacts.
- **Goofy.** Each clip is solved again on the real rig with the stance mirrored (right foot forward, nose toward -Y),
  not copied: the Tripo rig is not symmetric.
- **Review.** Sheets (behind the board = the game camera, toe side, above) in `../skate-r01/review/`, pose references
  (GPT Image 2.5 Sunburst) in `../skate-r01/references/`. For SkateOllie/SkateNollie/SkateManual/SkateNoseManual and the
  flip the sheets move the board as the game will and move the feet with it (two-bone legs), as the game's IK will.

| Clip | Length | Kind | Feet on the board (regular) | Hands | Notes |
| --- | --- | --- | --- | --- | --- |
"""

README_TAIL = """
## Checks (all {count} actions)

- Sole on its deck spot: worst {spot:.2f} cm; sole below the deck surface: worst {deck:.2f} cm; below the ground: {ground:.2f} cm.
- Knees: flexion {k0:.0f}-{k1:.0f} deg, always bending toward the knee pole (at least {kf:.1f} cm in front of the hip-ankle line):
  no hyperextension.
- Loops close exactly (first frame = last frame).
- Grab hands on their edge: worst {grip:.2f} cm. The arms are short for a board at its rest place, so a grabbing hand
  that cannot reach lowers the pelvis up to 8 cm and the clavicle drops and comes forward.
- Mesh clipping (edges of one body part through faces of another, on the deformed outfit, hands and head, every 2nd
  frame). In the grabs the sleeves lie against the baggy trousers: {clipnote}

## Deviations from SKATE.md

{deviations}

## Rebuild and export

```sh
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_skate_clips.py -- --parent {parent} --revision {rev}
blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_skate_review.py -- --blend output/imagegen/yorimichi-yellow-boy-2026-09-12/{rev}/WarmOriginal-Game-{num}.blend
blender -b --python games/yorimichi/assets/characters/cairo/export_unreal.py -- --revision {rev} --clips <every Skate* role> --clips-only --report export-skate.json
```

## Known weaknesses

{weak}
"""

DEVIATIONS = """- SkatePush: the pushing foot plants its ball at (+18, +26) deck-local (26 cm toward the toe side, beside the front
  truck: nearer and the shoe's heel, skinned to the shin, swings over the deck edge) and slides back 44 cm to (-26, +26):
  plant 0.30 s, release 0.62 s as specified. The front foot pivots on its ball from 55 to 14 deg off the board axis.
- SkateLand: the absorb bottoms out 21 cm below the stance at 0.12 s (the air tuck is already 18 cm down, so 15-20 cm would
  not be an absorb).
- Grabs: while holding, the pelvis sits {grab_lo:.0f}-{grab_hi:.0f} cm below the stance (SkateAir: 18) because the hands (38-40 cm arms) must reach
  the deck edge with the board at its rest place; knees splay to let the arm pass. Method and stalefish cannot bring the
  board up behind with a board fixed under the feet: the method is the melon grab with the chest up and the back arm high.
- Foot spots per clip (deck-local x): manual back foot -24, front +15; nose manual front +21, back -15; grinds over the
  trucks +18 / -19; brake foot on the ground at (-25, +27); everything else uses the stance spots, the ollie load spots or
  the nollie load spots of the contract.
- Board profile assumed for the checks and the proxy: concave z += 0.9 (y / 10.25)^2, kicks z += 4.5 u^2 over the last
  13 cm, rounded ends. The board mesh should match it or the sole checks shift by up to a few millimetres."""

WEAK = """- The shoe heels are skinned about half to the shin, so they lift or sink with the ankle angle; in deep crouches the
  heel of the shoe rises off the grip (the forefoot carries the contact).
- Deep grabs open the trousers' crotch (dark inside visible from the toe side, not from the game camera) and press the
  sleeves against the trousers.
- The push stroke keeps the support knee bent about 100 deg: the deck is 9 cm high and the legs are 60 cm.
- Reviewed by numbers and renders only; not yet seen in the game with the real board transform and IK."""


def write_readme(out, b, results, per_frame):
    rows = []
    for name, res in results.items():
        if res['stance'] != 'regular': continue
        clip = CLIPS[name]; iv = limb_contacts(res)
        feet = '; '.join(f"{k[-1]} {', '.join(f'{a:.2f}-{z:.2f}' for a, z in v)}" for k, v in iv.items() if k.startswith('foot') and v) or '-'
        if 'on_ground' in iv: feet += '; ground ' + '; '.join(f"{k[-1]} {', '.join(f'{a:.2f}-{z:.2f}' for a, z in v)}" for k, v in iv['on_ground'].items())
        hands = '; '.join(f"{k[-1]} {', '.join(f'{a:.2f}-{z:.2f}' for a, z in v)}" for k, v in iv.items() if k.startswith('hand') and v) or '-'
        kind = 'loop' if clip.loop else ('hold last frame' if clip.hold else 'one-shot')
        rows.append(f'| {name} | {clip.duration:.2f} s | {kind} | {feet} | {hands} | {clip.notes} |')
    R = list(results.values())
    grabs = [r for r in R if r['role'].startswith('SkateGrab')]
    worst = max(((k, v['max']) for r in grabs for k, v in r.get('clipping', {}).items() if k.endswith('depth_cm')), key=lambda x: x[1], default=('none', 0))
    others = sorted({n for n, r in results.items() if not r['role'].startswith('SkateGrab') and any(v['max'] for k, v in r.get('clipping', {}).items())})
    other_depth = max((v['max'] for n in others for k, v in results[n]['clipping'].items() if k.endswith('depth_cm')), default=0.)
    clipnote = (f"the deepest measured overlap is {worst[1]:.1f} cm ({worst[0].replace(' depth_cm', '')}). Outside the grabs: "
                + (f"{', '.join(others)} (the swinging leg brushes the other trouser leg, at most {other_depth:.1f} cm)." if others else 'none.'))
    held = [BASE['pz'] - r['hips'][2] for n, rows in per_frame.items() if results[n]['role'].startswith('SkateGrab') for r in rows if r['t'] >= .18]
    deviations = DEVIATIONS.format(grab_lo=min(held), grab_hi=max(held))
    text = README_HEAD.format(rev=b.rev, num=b.rev[5:], parent=b.parent_dir.name, count=len(results),
                              root=component_cm(b, b.skater.origin), deck=component_cm(b, b.skater.origin + Vector((0, 0, Board.TOP / UNIT))))
    text += '\n'.join(rows) + '\n'
    text += README_TAIL.format(count=len(results), spot=max(r['max_spot_err_cm'] for r in R), deck=max(r['max_deck_penetration_cm'] for r in R),
                               ground=max(r['max_ground_penetration_cm'] for r in R), k0=min(r['knee_flex_range'][0] for r in R),
                               k1=max(r['knee_flex_range'][1] for r in R), kf=min(r['min_knee_forward_cm'] for r in R),
                               grip=max(r['max_grip_err_cm'] for r in R), clipnote=clipnote, deviations=deviations, parent=b.parent_dir.name,
                               rev=b.rev, num=b.rev[5:], weak=WEAK)
    (out / 'README.md').write_text(text)
    print('README', out / 'README.md', flush=True)


def component_cm(b, p_arm):
    """Armature-space point -> the exported mesh's component space in cm (UE axes: X forward, Y right, Z up), with the
    exporter's transform (scale 1.48 / standing height, floor moved to the 0.65 cm sole height)."""
    W = b.arm.matrix_world @ Vector(p_arm)
    return [round(W.x * b.export_scale * 100, 3), round(-W.y * b.export_scale * 100, 3), round((W.z - b.export_floor) * b.export_scale * 100 + .65, 3)]


def write_build(out, b, results, per_frame):
    sk = b.skater
    limbs = {'regular': {'F': 'L', 'B': 'R'}, 'goofy': {'F': 'R', 'B': 'L'}}
    deck_top = sk.origin + Vector((0, 0, Board.TOP / UNIT))
    clips, push = {}, {}
    for name, res in results.items():
        m = limbs[res['stance']]; iv = res['intervals']; clip = CLIPS[res['role']]
        contacts = limb_contacts(res)
        rows = per_frame[name]
        spots = {f'foot_{m[r]}': {'first_frame': [rows[0][r]['spot'][1], rows[0][r]['spot'][0]],
                                  'last_frame': [rows[-1][r]['spot'][1], rows[-1][r]['spot'][0]]} for r in 'FB'}
        moves = [[round(t, 3), round(clip.board(t)['pitch'], 2), round(clip.board(t)['roll'], 1)] for t in np.arange(0, clip.duration + 1e-6, .05)]
        clips[name] = dict(role=res['role'], stance=res['stance'], length_s=clip.duration, frames=clip.frames, loop=clip.loop,
                           hold_last_frame=clip.hold, contacts=contacts, deck_spots_deck_local_cm=spots,
                           review_board_motion=(moves if any(abs(x[1]) + abs(x[2]) > 0 for x in moves) else None),
                           validation={k: v for k, v in res.items() if k not in ('intervals', 'role', 'stance')})
        if res['role'] == 'SkatePush':
            g = [i for i, r in enumerate(rows) if r['B']['on_ground']]
            first, last = rows[g[0]], rows[g[-1]]
            s_ = 1 if res['stance'] == 'regular' else -1
            def rider(row):   # stance-frame (t, a) -> rider frame (x, y) cm
                return [row['B']['spot'][0], round(s_ * row['B']['spot'][1], 2), row['B']['spot'][2]]
            push[name] = dict(foot=f"foot_{m['B']}", plant_s=first['t'], release_s=last['t'], ground_intervals=iv['ground_B'] if 'ground_B' in iv else None,
                              planted_ball_rider_cm={'plant': rider(first), 'release': rider(last)},
                              stroke_cm=round(abs(first['B']['spot'][1] - last['B']['spot'][1]), 2),
                              note='rider frame (Blender axes, cm): the ball of the pushing foot, which touches the ground from plant to release and slides back at the board speed')
    stance_spots = {}
    for name in ('SkateStance', 'SkateStanceGoofy'):
        if name in per_frame:
            m = limbs[results[name]['stance']]; r0 = per_frame[name][0]
            stance_spots[name] = {f'foot_{m[r]}': {'centre_deck_local_cm': [r0[r]['spot'][1], r0[r]['spot'][0]], 'sole_gap_cm': r0[r]['deck_gap']} for r in 'FB'}
    build = {
        'contract': 'games/yorimichi/docs/SKATE.md (Rider clips)', 'revision': b.rev, 'parent': b.parent_dir.name, 'fps': FPS,
        'tool': 'japan/tools/warm_skate_clips.py', 'review': 'output/imagegen/yorimichi-yellow-boy-2026-09-12/skate-r01/review/',
        'frames': {
            'rider_frame': 'cm, Blender axes: origin at the Root bone head on the ground (the standing sole level), +X the way the rig faces '
                           '(the board toe edge), +Y the rig left, +Z up. Regular: deck-local (x, y, z) = rider (y, x, z + 9.05), nose toward +Y. '
                           'Goofy (suffix Goofy) mirrors it: nose toward -Y, right foot forward, deck-local (x, y, z) = rider (-y, x, z + 9.05).',
            'unit': f'armature units x {b.unit:.4f} = cm',
            'root_head_in_mesh_component_cm': component_cm(b, sk.origin),
            'deck_top_centre_in_mesh_component_cm': component_cm(b, deck_top),
            'component_space_note': 'the exported FBX component space (UE axes: X forward, Y right, Z up; the standing sole sits at Z = 0.65 cm, '
                                    'the definition SoleHeight). The rider-frame origin (the Root bone) is not at the component origin: '
                                    'attach the mesh to the board frame so root_head_in_mesh_component_cm lands on the board ground point '
                                    '(deck top centre 9.05 cm above it).'},
        'board_profile_used': {'deck_top_cm': Board.TOP, 'concave': 'z += 0.9 * (y / 10.25)^2 across the width (rails 0.9 cm above the centre line)',
                               'kicks': 'z += 4.5 * u^2, u = (|x| - 27) / 13 over the last 13 cm', 'outline': 'rounded ends of radius 10.25 cm',
                               'wheelbase': 36., 'thickness': Board.THICK},
        'foot_reference': {'centre': 'middle of the shoe footprint (heel to toe, across the sole)', 'ball': '68 % of the footprint from the heel',
                           'footprint_length_cm': {k: round(v, 2) for k, v in sk.foot_len.items()},
                           'solver_clearance_cm': CLEAR, 'on_board_threshold_cm': .5,
                           'note': 'feet stand at the listed spots with the deformed shoe (the heel is skinned partly to the shin) touching the grip without going through it'},
        'stance_deck_spots': stance_spots,
        'push': push,
        'clips': clips,
        'report': b.report,
    }
    (out / 'skate-build.json').write_text(json.dumps(build, indent=1) + '\n')
    print('BUILD_JSON', out / 'skate-build.json', flush=True)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--parent', default='game-r16'); ap.add_argument('--revision', default='game-r17')
    ap.add_argument('--only'); ap.add_argument('--scratch', help='save a scratch blend + json here instead of the revision')
    ap.add_argument('--no-goofy', action='store_true'); ap.add_argument('--no-clipcheck', action='store_true')
    ap.add_argument('--clip-step', type=int, default=2)
    run(ap.parse_args(argv))
