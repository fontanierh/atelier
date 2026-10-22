"""Playable character horseback riding clips authored in horse space on each character's own rig.

    blender -b --python games/yorimichi/assets/horses/rider.py [-- --clips HorseIdle,HorseWalk] [--review DIR]
        [--character cairo] [--breed arabian] [--tack 00]

--character authors the same 13 clips on any playable character's rig (pipeline/rig.py prepare: cairo, modori, nox,
paul), into build/yorimichi/<character>/horse/: the solve reaches the saddle seat, stirrup treads, and rein grips
with that character's limbs while reacting to the horse's spine pitch, roll, and head/neck motion at 60 fps.

Reads the reference breed's 60 Hz contact trajectories from build/yorimichi/horses/manifest.json (world.horses, which
must have run). Horse space matches Yorimichi's character export space: metres, +X forward, +Y left, +Z up, origin on
the ground between the hooves.

export.json holds `source_sha256`, `fps` and each clip's frames, duration and loop (which Scripts/import_ride_clips.py
reads) and reach_error_cm per limb (which the fit gate, characters/pipeline/fit.py, bounds). The horse clip each rides and
the solved targets per frame stay in memory for the review renders.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'world')); import yori  # noqa: E402
sys.path.insert(0, str(HERE.parents[0] / 'vehicles'))
from rider_common import SIDE, Hands as HandFrames, Rig as BaseRig, character, ease, look, rest_world_rot, rot, smooth, studio, write_action  # noqa: E402

HORSE_BUILD = yori.OUT / 'horses'
# What export.json keeps of each clip: the clip import's fields and the fit gate's.
EXPORTED = ('frames', 'duration', 'loop', 'reach_error_cm')
OUT = yori.OUT / 'cairo' / 'horse'
FPS = 60
GROUND_SPACE = 'g'


def load_manifest():
    """world.horses' output: the breeds' contacts and the reference breed's sampled clips."""
    manifest_path = HORSE_BUILD / 'manifest.json'
    if not manifest_path.is_file():
        raise SystemExit(f'{manifest_path} is missing: build world.horses first (atelier build yorimichi world.horses)')
    return json.loads(manifest_path.read_text())


# Per-clip rider posture parameters on mounted clips (driven by the horse's 60 Hz trajectory)
MOUNTED_SPECS = {
    'HorseIdle': dict(
        horse_clip='Idle',
        seat_dx=0.015, pelvis_pitch=6.0, lean=10.0, head_pitch=-4.0,
        pitch_follow=0.40, roll_follow=0.50, head_look_follow=0.25, walk_wave=0.25,
    ),
    'HorseIdleLook': dict(
        horse_clip='IdleLook',
        seat_dx=0.015, pelvis_pitch=6.0, lean=10.0, head_pitch=-4.0,
        pitch_follow=0.40, roll_follow=0.50, head_look_follow=0.55, walk_wave=0.25,
    ),
    'HorseIdleGraze': dict(
        horse_clip='IdleGraze',
        seat_dx=0.032, pelvis_pitch=10.0, lean=16.0, head_pitch=-8.0,
        pitch_follow=0.45, roll_follow=0.50, head_look_follow=0.35, graze_lean=18.0, walk_wave=0.25,
    ),
    'HorseIdleShake': dict(
        horse_clip='IdleShake',
        seat_dx=0.030, pelvis_pitch=9.0, lean=16.0, head_pitch=-6.0,
        pitch_follow=0.45, roll_follow=0.60, head_look_follow=0.25, walk_wave=0.30,
    ),
    'HorseIdleFlehmen': dict(
        horse_clip='IdleFlehmen',
        seat_dx=0.020, pelvis_pitch=6.0, lean=12.0, head_pitch=2.0,
        pitch_follow=0.40, roll_follow=0.50, head_look_follow=0.45, walk_wave=0.25,
    ),
    'HorseIdleAffection': dict(
        horse_clip='IdleAffection',
        seat_dx=0.020, pelvis_pitch=7.0, lean=13.0, head_pitch=-5.0,
        pitch_follow=0.40, roll_follow=0.50, head_look_follow=0.50, walk_wave=0.25,
    ),
    'HorseWalk': dict(
        horse_clip='Walk',
        seat_dx=0.020, pelvis_pitch=8.0, lean=13.0, head_pitch=-6.0,
        pitch_follow=0.45, roll_follow=0.50, head_look_follow=0.20, walk_wave=1.00,
    ),
    'HorseTrot': dict(
        horse_clip='Trot',
        seat_dx=0.026, pelvis_pitch=10.0, lean=17.0, head_pitch=-9.0,
        pitch_follow=0.50, roll_follow=0.50, head_look_follow=0.15, walk_wave=0.55,
    ),
    'HorseCanter': dict(
        horse_clip='Canter',
        seat_dx=0.034, pelvis_pitch=12.0, lean=21.0, head_pitch=-12.0,
        pitch_follow=0.50, roll_follow=0.50, head_look_follow=0.15, walk_wave=0.35,
    ),
    'HorseGallop': dict(
        horse_clip='Gallop',
        seat_dx=0.042, pelvis_pitch=14.0, lean=25.0, head_pitch=-15.0,
        pitch_follow=0.55, roll_follow=0.50, head_look_follow=0.12, walk_wave=0.35,
    ),
    'HorseSprint': dict(
        horse_clip='Sprint',
        seat_dx=0.048, pelvis_pitch=16.0, lean=28.0, head_pitch=-18.0,
        pitch_follow=0.55, roll_follow=0.50, head_look_follow=0.10, walk_wave=0.35,
    ),
}


# ------------------------------------------------------------------------------------------------------- the rig solve

class Rig(BaseRig):
    """The shared rest-skeleton solve, with limb bones aimed by their child (limb_offset) and the rider's proportions."""
    def __init__(self, arm):
        super().__init__(arm)
        for side in 'LR':
            for upper, lower, end, bend in (
                (f'upperarm_{side}', f'forearm_{side}', f'hand_{side}', Vector((1, 0, 0))),
                (f'thigh_{side}', f'shin_{side}', f'foot_{side}', Vector((-1, 0, 0))),
            ):
                for bone, child in ((upper, lower), (lower, end)):
                    R = self.rest[bone].to_3x3().normalized()
                    u_child = (self.rest[child].translation - self.rest[bone].translation).normalized()
                    if R.col[1].normalized().dot(u_child) < 0.95:
                        n_rest = u_child.cross(bend).normalized()
                        x_rest = u_child.cross(n_rest).normalized()
                        F_rest = Matrix((x_rest, u_child, n_rest)).transposed()
                        self.limb_offset[bone] = F_rest.inverted() @ R

        self.dir_local = {}
        for side in 'LR':
            chains = [
                (f'thumb_{side}', f'thumb_tip_{side}', f'thumb_end_{side}'),
                *((f'finger_{i}_{side}', f'finger_tip_{i}_{side}', f'finger_end_{i}_{side}') for i in range(4)),
            ]
            for b0, b1, b2 in chains:
                for bone, nxt, prv in ((b0, b1, b0), (b1, b2, b0), (b2, None, b1)):
                    if bone in self.rest:
                        R = self.rest[bone].to_3x3().normalized()
                        u = (
                            (self.rest[nxt].translation - self.rest[bone].translation).normalized()
                            if nxt and nxt in self.rest
                            else (self.rest[bone].translation - self.rest[prv].translation).normalized()
                        )
                        self.dir_local[bone] = (R.inverted() @ u).normalized()

        # Measure character-specific proportions in world metres
        self.rest_pelvis_w = self.world(self.rest['pelvis'].translation)
        hip_L_w = self.world(self.rest['thigh_L'].translation)
        hip_R_w = self.world(self.rest['thigh_R'].translation)
        self.rest_hips_w = 0.5 * (hip_L_w + hip_R_w)
        self.hip_to_pelvis_w = self.rest_pelvis_w - self.rest_hips_w
        self.leg_length = (
            self.length('thigh_L', 'shin_L') + self.length('shin_L', 'foot_L')
        ) * self.scale
        self.arm_length = (
            self.length('upperarm_L', 'forearm_L') + self.length('forearm_L', 'hand_L')
        ) * self.scale
        # Calibrate seat clearance to rider leg length; sole rests directly on the stirrup iron tread
        self.seat_clearance_z = max(0.055, 0.088 * (self.leg_length - 0.50) / 0.22)
        self.stirrup_shorten_z = 0.0


class Hands(HandFrames):
    """Hand frames: fingers direction f and palm direction p, with knuckle/thumb line k = s (p x f)."""
    def __init__(self, rig):
        self.rig = rig
        self.rest = {}
        self.k_rest = {}
        self.knuckle_mid = {}
        for side in 'LR':
            p_hand = rig.rest['hand_' + side].translation
            p_f0 = rig.rest['finger_0_' + side].translation
            p_f3 = rig.rest['finger_3_' + side].translation
            k0 = (p_f0 - p_f3).normalized()
            f_raw = 0.5 * (p_f0 + p_f3) - p_hand
            f0 = (f_raw - k0 * f_raw.dot(k0)).normalized()
            p0 = (SIDE[side] * f0.cross(k0)).normalized()
            self.rest[side] = (f0, p0)
            self.k_rest[side] = k0
            self.knuckle_mid[side] = f_raw * rig.scale
        h = rig.rest['finger_1_L'].translation - rig.rest['hand_L'].translation
        self.palm = h.length * rig.scale
        self.pocket = {}
        rig.begin()
        for b in rig.order:
            rig.local(b)
        for side in 'LR':
            fingers(rig, self, side, 0.88)
            p_hand = rig.rest['hand_' + side].translation
            pts = []
            for i, w in ((0, 0.25), (1, 0.35), (2, 0.25), (3, 0.15)):
                f_b = f'finger_{i}_{side}'
                t_b = f'finger_tip_{i}_{side}'
                e_b = f'finger_end_{i}_{side}'
                if f_b in rig.pose and t_b in rig.pose and e_b in rig.pose:
                    p_kn = rig.pose[f_b].translation
                    p_pip = rig.pose[t_b].translation
                    p_dip = rig.pose[e_b].translation
                    l_end = rig.length(t_b, e_b) * 0.78
                    v_loc = rig.dir_local.get(e_b, Vector((0.0, 1.0, 0.0)))
                    p_tip = p_dip + (rig.pose[e_b].to_3x3().normalized() @ v_loc).normalized() * l_end
                    c_i = 0.22 * p_kn + 0.30 * p_pip + 0.28 * p_dip + 0.20 * p_tip
                    pts.append((w, c_i))
            w_sum = sum(w for w, _ in pts)
            c_arm = sum((c * (w / w_sum) for w, c in pts), Vector((0.0, 0.0, 0.0)))
            self.pocket[side] = (c_arm - p_hand) * rig.scale

    def frame(self, side, name, fr=None):
        """World rotation that takes the rest hand to the named hand frame."""
        s = SIDE[side]
        if name == 'reins':
            # Knuckles (pinky finger_3 -> index finger_0) aligned along the local tangent of the curved leather rein arch
            # between Reins_5_side and Reins_C; back of the hand up and slightly out, palm and fingers wrapping over and
            # underneath the rein strap.
            if fr is not None and 'reins_c' in fr and ('reins_5_' + side) in fr:
                d_sec = Vector(fr['reins_c']) - Vector(fr['reins_5_' + side])
                k = Vector((0.32 * d_sec.x, d_sec.y, d_sec.z)).normalized()
            else:
                k = Vector((-0.26, -s * 0.96, 0.0)).normalized()
            back = Vector((-0.18, s * 0.42, 0.89))
            back = (back - k * back.dot(k)).normalized()
            p = -back
            f = s * k.cross(p)
        elif name == 'pommel':
            f, p = Vector((0.92, -s * 0.25, -0.15)), Vector((0.0, -s * 0.35, -0.94))
        elif name == 'cantle':
            f, p = Vector((-0.35, -s * 0.85, -0.25)), Vector((0.0, 0.0, -1.0))
        elif name == 'pat':
            f, p = Vector((0.75, -s * 0.20, 0.45)), Vector((0.0, -s * 0.92, -0.35))
        else:
            f, p = Vector((0.35, 0.0, -1.0)), Vector((0.0, -s, 0.0))
        return self.turn(side, f, p)

    def wrist_for_grip(self, side, centre, D):
        return Vector(centre) - (D @ self.pocket[side])


def fingers(rig, hands, side, curl, flick=0.):
    """Curl all 4 fingers and thumb around their anatomical rest hinge axes toward the palm/rein pocket with zero axial twist."""
    f0, palm = hands.rest[side]
    k0 = hands.k_rest[side]
    blend_f = max(0.0, min(1.0, curl))
    axis_f = f0.cross(palm).normalized()
    phalanx_degs = (138.0, 0.0, 0.0) if rig.limb_offset else (74.0, 88.0, 58.0)
    gains = ((0, 1.00), (1, 1.00), (2, 1.00), (3, 1.00)) if rig.limb_offset else ((0, 0.96), (1, 1.00), (2, 1.03), (3, 1.06))
    for i, gain in gains:
        for bone, deg in zip((f'finger_{i}_{side}', f'finger_tip_{i}_{side}', f'finger_end_{i}_{side}'), phalanx_degs):
            if bone in rig.rest:
                rig.local(bone, Matrix.Rotation(math.radians(deg * blend_f * gain), 3, axis_f))
    b_t0 = f'thumb_{side}'
    b_t1 = f'thumb_tip_{side}'
    if b_t0 in rig.rest and b_t1 in rig.rest:
        u_t = (rig.rest[b_t1].translation - rig.rest[b_t0].translation).normalized()
    else:
        u_t = (f0 + k0).normalized()
    target_t = (0.58 * f0 + 0.52 * palm - 0.38 * k0).normalized()
    axis_t = u_t.cross(target_t)
    axis_t = axis_t.normalized() if axis_t.length > 1e-5 else axis_f
    blend_t = max(0.0, min(1.0, curl * (1.0 - flick)))
    thumb_degs = (36.0, 8.0, 0.0) if rig.limb_offset else (34.0, 42.0, 32.0)
    for bone, deg in zip((b_t0, b_t1, f'thumb_end_{side}'), thumb_degs):
        if bone in rig.rest:
            rig.local(bone, Matrix.Rotation(math.radians(deg * blend_t), 3, axis_t))
    for bone in [n for n in rig.order if n.endswith('_' + side) and n not in rig.pose and ('finger' in n or 'thumb' in n)]:
        rig.local(bone)


def rein_grip_point(fr, side):
    """Point on the curved leather rein arch between Reins_C and Reins_5_side where the rider's 4 fingers wrap."""
    if 'reins_c' in fr and ('reins_5_' + side) in fr:
        rc = Vector(fr['reins_c'])
        r5 = Vector(fr['reins_5_' + side])
        return Vector((
            rc.x + 0.11 * (r5.x - rc.x),
            rc.y + 0.44 * (r5.y - rc.y),
            rc.z + 0.44 * (r5.z - rc.z) + 0.001,
        ))
    return Vector(fr['grip_' + side])


def stirrup_tread_point(rig, fr, side):
    """Top-center of the étrier (stirrup iron) tread under the ball of the rider's boot."""
    st = Vector(fr['stirrup_' + side])
    return st + Vector((0.0, 0.0, rig.stirrup_shorten_z))


def pommel_point(fr, side):
    s = SIDE[side]
    sr = Vector(fr['saddle_root'])
    return sr + Vector((0.28, s * 0.055, 0.010))


def cantle_point(fr):
    sr = Vector(fr['saddle_root'])
    return sr + Vector((-0.075, 0.05, -0.085))


def _place_torso(rig, hips_w, pelvis_rot, lean, twist, side_lean, shrug=0.0, spine_rots=None, clavicle_rots=None):
    rig.begin()
    rig.local('root')
    R_pelvis_rest = rest_world_rot(rig, 'pelvis')
    R_pelvis = rot(*pelvis_rot) @ R_pelvis_rest
    pelvis_w = hips_w + (R_pelvis @ R_pelvis_rest.inverted()) @ rig.hip_to_pelvis_w
    rig.place('pelvis', Matrix.Translation(rig.to_arm(pelvis_w)) @ R_pelvis.to_4x4())
    lean_rel = lean - pelvis_rot[0] * 0.5
    for bone, share in (('spine', 0.34), ('spine_mid', 0.33), ('chest', 0.33)):
        if spine_rots and bone in spine_rots:
            dp, dy, dr = spine_rots[bone]
            rig.local(bone, rot(lean_rel * share + dp, twist * share + dy, side_lean * share + dr))
        else:
            rig.local(bone, rot(lean_rel * share, twist * share, side_lean * share))
    for side in 'LR':
        if clavicle_rots and side in clavicle_rots:
            cp, cy, cr = clavicle_rots[side]
            rig.local('clavicle_' + side, rot(cp, cy, cr))
        else:
            rig.local('clavicle_' + side, rot(0., 0., -SIDE[side] * shrug))


def transition_hips(rig, hips, state, foot_offset):
    """@cc [owner:fontanierh,label:correctness] fixed-transition-contacts
    Move the torso into the intersection of the four limbs' reach spheres.
    Transition fitting MUST preserve the authored hand and foot targets
    and the rig's bone lengths; the final IK solve MUST still report any unreachable contact to the fit gate.
    """
    constraints = []
    for side in 'LR':
        for upper, lower, end, target in (
            (f'upperarm_{side}', f'forearm_{side}', f'hand_{side}', Vector(state['wrist_' + side])),
            (f'thigh_{side}', f'shin_{side}', f'foot_{side}',
             Vector(state['sole_' + side]) + state['Rf_' + side] @ foot_offset[side]),
        ):
            # With the torso rotations fixed, translating the hips translates each limb root by the same amount.
            centre = target - (rig.world(rig.head(upper)) - hips)
            # Use the riding solve's reach margins so knees and elbows retain a little bend.
            reach = 0.93 if upper.startswith('upperarm') else 0.965
            radius = (rig.length(upper, lower) + rig.length(lower, end)) * rig.scale * reach
            constraints.append((centre, radius))
    fitted = hips.copy()
    for _ in range(64):
        for centre, radius in constraints:
            delta = fitted - centre
            if delta.length > radius:
                fitted = centre + delta.normalized() * radius
    return fitted


def solve_pose(rig, hands, foot_offset, fr, state):
    """Pose the character rig for one frame given resolved rider state and horse contact frame `fr`."""
    hips_w = Vector(state['hips']).copy()
    pelvis_rot = tuple(state['pelvis_rot'])
    lean = float(state['lean'])
    twist = float(state['twist'])
    side_lean = float(state['side'])
    shrug = float(state.get('shrug', 0.))
    spine_rots = state.get('spine_rots')
    clavicle_rots = state.get('clavicle_rots')
    hp, hy, hr = state['head']

    _place_torso(rig, hips_w, pelvis_rot, lean, twist, side_lean, shrug, spine_rots, clavicle_rots)

    if state.get('transition_reach', False):
        hips_w = transition_hips(rig, hips_w, state, foot_offset)
        _place_torso(rig, hips_w, pelvis_rot, lean, twist, side_lean, shrug, spine_rots, clavicle_rots)
        state['hips'] = hips_w

    # Settle the pelvis deeper into the saddle if a short-legged rider's boot reaches past 96.5% of leg length
    # during high horse suspension frames, keeping the sneaker/boot sole 100% inside the étrier (stirrup iron).
    if state.get('auto_reach', True):
        leg_cap = (rig.length('thigh_L', 'shin_L') + rig.length('shin_L', 'foot_L')) * 0.965
        ank_L_arm = rig.to_arm(Vector(state['sole_L']) + state['Rf_L'] @ foot_offset['L'])
        ank_R_arm = rig.to_arm(Vector(state['sole_R']) + state['Rf_R'] @ foot_offset['R'])
        need_leg0 = max((ank_L_arm - rig.head('thigh_L')).length, (ank_R_arm - rig.head('thigh_R')).length)
        if need_leg0 > leg_cap:
            ank_mid_w = 0.5 * (
                (Vector(state['sole_L']) + state['Rf_L'] @ foot_offset['L'])
                + (Vector(state['sole_R']) + state['Rf_R'] @ foot_offset['R'])
            )
            pull_dir = (ank_mid_w - hips_w)
            pull_dir.y = 0.0
            pull_u = pull_dir.normalized() if pull_dir.length > 1e-5 else Vector((0.0, 0.0, -1.0))
            lo_l, hi_l = 0.0, 0.14
            for _ in range(8):
                mid_l = 0.5 * (lo_l + hi_l)
                h_try = hips_w + pull_u * mid_l
                _place_torso(rig, h_try, pelvis_rot, lean, twist, side_lean, shrug, spine_rots, clavicle_rots)
                need_lm = max((ank_L_arm - rig.head('thigh_L')).length, (ank_R_arm - rig.head('thigh_R')).length)
                if need_lm > leg_cap:
                    lo_l = mid_l
                else:
                    hi_l = mid_l
            hips_w = hips_w + pull_u * hi_l
            _place_torso(rig, hips_w, pelvis_rot, lean, twist, side_lean, shrug, spine_rots, clavicle_rots)
            state['hips'] = hips_w

    # Smoothly lean the spine forward (and slide slightly forward in the saddle bowl) if the horse's outstretched
    # neck pulls the reins beyond 93% of arm length, keeping elbows softly flexed and hands 100% locked to the reins.
    if state.get('auto_reach', True):
        arm_cap = (rig.length('upperarm_L', 'forearm_L') + rig.length('forearm_L', 'hand_L')) * 0.93
        wL_arm = rig.to_arm(Vector(state['wrist_L']))
        wR_arm = rig.to_arm(Vector(state['wrist_R']))
        need0 = max((wL_arm - rig.head('upperarm_L')).length, (wR_arm - rig.head('upperarm_R')).length)
        if need0 > arm_cap:
            lo, hi = 0.0, 34.0
            for _ in range(8):
                mid = 0.5 * (lo + hi)
                h_try = hips_w + Vector((0.0010 * mid, 0.0, 0.0))
                p_try = (pelvis_rot[0] + 0.25 * mid, pelvis_rot[1], pelvis_rot[2])
                _place_torso(rig, h_try, p_try, lean + mid, twist, side_lean, shrug, spine_rots, clavicle_rots)
                need_m = max((wL_arm - rig.head('upperarm_L')).length, (wR_arm - rig.head('upperarm_R')).length)
                if need_m > arm_cap:
                    lo = mid
                else:
                    hi = mid
            extra = hi
            hips_w = hips_w + Vector((0.0010 * extra, 0.0, 0.0))
            pelvis_rot = (pelvis_rot[0] + 0.25 * extra, pelvis_rot[1], pelvis_rot[2])
            lean = lean + extra
            hp = hp - 0.55 * extra
            _place_torso(rig, hips_w, pelvis_rot, lean, twist, side_lean, shrug, spine_rots, clavicle_rots)
            state['hips'] = hips_w

    neck_rot = state.get('neck_rot')
    if neck_rot is not None:
        rig.local('neck', rot(*neck_rot))
        rig.local('head', rot(hp - neck_rot[0], hy - neck_rot[1], hr - neck_rot[2]))
    else:
        rig.local('neck', rot(hp * 0.4, hy * 0.4, hr * 0.4))
        rig.local('head', rot(hp * 0.6, hy * 0.6, hr * 0.6))

    R_yaw = Matrix.Rotation(math.radians(pelvis_rot[1]), 3, 'Z')
    elbow_breathe = float(state.get('elbow_breathe', 0.0))
    knee_sway = float(state.get('knee_sway', 0.0))
    short = {}
    for side in 'LR':
        sgn = SIDE[side]
        D = state['D_' + side]
        w = Vector(state['wrist_' + side])
        pole_arm = R_yaw @ Vector((-0.55 + 0.08 * elbow_breathe, sgn * (0.72 + 0.06 * abs(elbow_breathe)), -0.45 - 0.10 * elbow_breathe))
        short['hand_' + side] = rig.two_bone(
            'upperarm_' + side, 'forearm_' + side, 'hand_' + side,
            rig.to_arm(w), pole_arm, D @ rest_world_rot(rig, 'hand_' + side),
            forearm_twist=0.55,
        )

        Rf = state['Rf_' + side]
        sole = Vector(state['sole_' + side])
        ankle = sole + Rf @ foot_offset[side]
        swing_lift = max(0.0, min(1.0, (sole.z - (hips_w.z - 0.45)) / 0.35))
        base_knee = Vector((0.42, sgn * 0.92 + knee_sway, -0.10)).lerp(Vector((0.20, sgn * 0.75, 0.85)), swing_lift)
        knee_pole = R_yaw @ base_knee
        short['foot_' + side] = rig.two_bone(
            'thigh_' + side, 'shin_' + side, 'foot_' + side,
            rig.to_arm(ankle), knee_pole, Rf @ rest_world_rot(rig, 'foot_' + side),
        )
        rig.local('toe_' + side)
        fingers(rig, hands, side, state['curl_' + side])

    for n in rig.order:
        if n not in rig.pose:
            rig.local(n)
    return short


def bake_mounted_clip(rig, hands, foot_offset, name, spec, horse_clip_data):
    """Bake one of the 11 mounted horse clips from its 60 Hz horse trajectory with phase-lagged spinal wave propagation."""
    traj = horse_clip_data['trajectory']
    frames = len(traj)
    duration = horse_clip_data['duration']
    mean_pitch = sum(fr['pitch_deg'] for fr in traj) / frames
    mean_seat_x = sum(fr['seat'][0] for fr in traj) / frames
    mean_seat_y = sum(fr['seat'][1] for fr in traj) / frames
    mean_seat_z = sum(fr['seat'][2] for fr in traj) / frames
    mean_bit_x = sum(fr['bit'][0] for fr in traj) / frames
    mean_bit_z = sum(fr['bit'][2] for fr in traj) / frames
    rest_bit_z = traj[0]['bit'][2]

    raw_signals = []
    for fr in traj:
        seat_v = Vector(fr['seat'])
        stL, stR = Vector(fr['stirrup_L']), Vector(fr['stirrup_R'])
        sp2, hd, bit_v = Vector(fr['spine_2']), Vector(fr['head']), Vector(fr['bit'])
        raw_signals.append(dict(
            dx=seat_v.x - mean_seat_x,
            dy=seat_v.y - mean_seat_y,
            dz=seat_v.z - mean_seat_z,
            dpitch=fr['pitch_deg'] - mean_pitch,
            roll=math.degrees(math.atan2(stL.z - stR.z, max(0.15, stL.y - stR.y))),
            yaw=math.degrees(math.atan2(hd.y - sp2.y, max(0.20, hd.x - sp2.x))),
            dbit_x=bit_v.x - mean_bit_x,
            dbit_z=bit_v.z - mean_bit_z,
        ))
    mean_roll = sum(s['roll'] for s in raw_signals) / frames
    for s in raw_signals:
        s['roll'] -= mean_roll

    period = max(1, frames - 1)
    is_loop = bool(horse_clip_data['loop'])

    def sig(f_idx):
        if is_loop:
            x = f_idx % period
            i0 = int(math.floor(x)) % period
            i1 = (i0 + 1) % period
            u = x - math.floor(x)
        else:
            x = max(0.0, min(float(frames - 1), f_idx))
            i0 = int(math.floor(x))
            i1 = min(frames - 1, i0 + 1)
            u = x - i0
        a, b = raw_signals[i0], raw_signals[i1]
        return {k: a[k] + (b[k] - a[k]) * u for k in a}

    w_wave = float(spec.get('walk_wave', 0.0))

    poses, horse_frames, worst = [], [], {}
    for f, fr in enumerate(traj):
        t = f / FPS
        seat = Vector(fr['seat'])
        stL, stR = Vector(fr['stirrup_L']), Vector(fr['stirrup_R'])
        bit = Vector(fr['bit'])

        s0 = sig(f)
        s_pelv = sig(f - 2.5)
        s_yaw = sig(f - 4.0)
        s_sp1 = sig(f - 4.0)
        s_sp2 = sig(f - 8.0)
        s_sp3 = sig(f - 12.0)
        s_cl = sig(f - 10.0)
        s_nk = sig(f - 13.5)
        s_hd = sig(f - 16.0)
        s_ft = sig(f - 2.0)

        dpitch = s0['dpitch']
        saddle_roll = s0['roll']
        neck_yaw = s0['yaw']

        # Keep the rider's pelvis smoothly seated in the saddle leather while gliding with the 4-beat stride
        lean_extra = -0.35 * dpitch
        graze_drop = max(0.0, rest_bit_z - bit.z)
        lean_graze = spec.get('graze_lean', 0.0) * min(1.0, graze_drop / 0.65)

        hips = seat + Vector((
            spec['seat_dx'] + 0.025 * (lean_graze / 18.0 if lean_graze else 0.0) - w_wave * (0.45 * s0['dx'] + 0.28 * s_pelv['dz']),
            0.25 * (0.5 * (stL.y + stR.y)) + w_wave * 0.45 * s0['dy'],
            rig.seat_clearance_z,
        ))
        # 3D pelvic figure-8 follow-through: 2x/stride anterior-posterior scoop + 1x/stride lateral roll and phase-shifted yaw
        pelvis_rot = (
            spec['pelvis_pitch'] + spec['pitch_follow'] * dpitch + w_wave * (1.55 * dpitch - 175.0 * s_pelv['dz']),
            0.20 * neck_yaw - w_wave * 2.25 * s_yaw['roll'],
            spec['roll_follow'] * saddle_roll + w_wave * 1.35 * saddle_roll,
        )
        lean = spec['lean'] + lean_extra + lean_graze
        twist = 0.25 * neck_yaw
        side_lean = -0.35 * saddle_roll

        # Phase-lagged wave propagation up the lumbar (spine), thoracic (spine_mid), and upper chest (chest) segments
        spine_rots = {
            'spine': (
                w_wave * (55.0 * s_sp1['dz'] - 0.55 * s_sp1['dpitch']),
                w_wave * (0.75 * s_sp1['roll']),
                w_wave * (-0.55 * s_sp1['roll']),
            ),
            'spine_mid': (
                w_wave * (45.0 * s_sp2['dz'] - 0.45 * s_sp2['dpitch']),
                w_wave * (0.95 * s_sp2['roll']),
                w_wave * (-0.50 * s_sp2['roll']),
            ),
            'chest': (
                w_wave * (38.0 * s_sp3['dz'] - 24.0 * sig(f - 5.0)['dbit_z']),
                w_wave * (1.15 * s_sp3['roll']),
                w_wave * (-0.45 * s_sp3['roll']),
            ),
        }
        clavicle_rots = {
            'L': (w_wave * 0.6 * s_cl['dpitch'], 0.0, -w_wave * (42.0 * s_cl['dz'] + 0.65 * s_cl['roll'])),
            'R': (w_wave * 0.6 * s_cl['dpitch'], 0.0, +w_wave * (42.0 * s_cl['dz'] - 0.65 * s_cl['roll'])),
        }

        head_rot = (
            spec['head_pitch'] - 0.40 * s_hd['dpitch'] - 0.55 * lean_graze + w_wave * (-45.0 * s_hd['dz'] + 18.0 * s_hd['dbit_z']),
            spec['head_look_follow'] * s_hd['yaw'] - w_wave * 0.85 * s_hd['roll'],
            -0.25 * s_hd['roll'] - w_wave * 0.35 * s_hd['roll'],
        )
        neck_rot = (
            0.42 * (spec['head_pitch'] - 0.40 * s_nk['dpitch'] - 0.55 * lean_graze) + w_wave * (-22.0 * s_nk['dz']),
            0.42 * (spec['head_look_follow'] * s_nk['yaw']) - w_wave * 0.35 * s_nk['roll'],
            -0.12 * s_nk['roll'] - w_wave * 0.15 * s_nk['roll'],
        )

        # Affection clip: warm nod and slight torso turn toward the horse's neck in the middle of the clip
        if name == 'HorseIdleAffection':
            w_aff = math.sin(math.pi * min(1.0, t / max(0.01, duration))) ** 2
            head_rot = (head_rot[0] - 8.0 * w_aff, head_rot[1] + 6.0 * w_aff, head_rot[2])
            neck_rot = (neck_rot[0] - 3.2 * w_aff, neck_rot[1] + 2.4 * w_aff, neck_rot[2])
            lean += 3.0 * w_aff

        g_L = rein_grip_point(fr, 'L')
        g_R = rein_grip_point(fr, 'R')
        D_L = hands.frame('L', 'reins', fr)
        D_R = hands.frame('R', 'reins', fr)
        w_L = hands.wrist_for_grip('L', g_L, D_L)
        w_R = hands.wrist_for_grip('R', g_R, D_R)

        # Heels-down equestrian ankle flexion (-6 deg toe up, flexing smoothly with the phase-lagged horse stride)
        foot_pitch_L = -6.0 - (14.0 + 72.0 * w_wave) * s_ft['dz'] + w_wave * 1.35 * s_ft['roll']
        foot_pitch_R = -6.0 - (14.0 + 72.0 * w_wave) * s_ft['dz'] - w_wave * 1.35 * s_ft['roll']
        Rf_L = rot(foot_pitch_L, 8.0 - w_wave * 0.8 * s_ft['roll'], 0.0)
        Rf_R = rot(foot_pitch_R, -8.0 - w_wave * 0.8 * s_ft['roll'], 0.0)
        sole_L = stirrup_tread_point(rig, fr, 'L')
        sole_R = stirrup_tread_point(rig, fr, 'R')

        state = dict(
            hips=hips, pelvis_rot=pelvis_rot, lean=lean, twist=twist, side=side_lean,
            spine_rots=spine_rots, clavicle_rots=clavicle_rots,
            head=head_rot, neck_rot=neck_rot,
            elbow_breathe=w_wave * (-1.2 * s0['dbit_z']),
            knee_sway=w_wave * 0.045 * s_ft['roll'],
            D_L=D_L, D_R=D_R, wrist_L=w_L, wrist_R=w_R, curl_L=0.88, curl_R=0.88,
            Rf_L=Rf_L, Rf_R=Rf_R, sole_L=sole_L, sole_R=sole_R, auto_reach=True,
        )
        short = solve_pose(rig, hands, foot_offset, fr, state)
        for limb, v in short.items():
            worst[limb] = max(worst.get(limb, 0.), v)
        poses.append({n: rig.basis[n].copy() for n in rig.order})
        horse_frames.append({
            'seat': [round(x, 4) for x in state['hips']],
            'grip_L': [round(x, 4) for x in g_L],
            'grip_R': [round(x, 4) for x in g_R],
            'stirrup_L': [round(x, 4) for x in sole_L],
            'stirrup_R': [round(x, 4) for x in sole_R],
            'bit': fr['bit'],
        })

    return poses, {
        'frames': frames,
        'duration': duration,
        'loop': is_loop,
        'horse_clip': spec['horse_clip'],
        'horse': horse_frames,
        'reach_error_cm': {k: round(v * 100, 2) for k, v in worst.items()},
    }


def transition_keys(rig, fr0):
    """Keyframes for HorseMount and HorseDismount relative to the horse's Idle frame 0 contacts."""
    seat = Vector(fr0['seat']) + Vector((0.015, 0.0, rig.seat_clearance_z))
    h_ground = rig.rest_hips_w.z
    # The saddle grip and left stirrup are high on the horse even for a small rider. Lift the trailing foot with
    # the body: leaving it near the ground makes those three contacts physically incompatible for short limbs.
    step_height = seat.z - 0.26
    beside = dict(
        hips=(0.00, 0.64, h_ground), pelvis_rot=(4., -70., 0.), lean=6., twist=-4., side=0., head=(4., -10., 0.),
        hand_L=(GROUND_SPACE, 0.14, 0.42, h_ground + 0.30), hand_R=(GROUND_SPACE, -0.08, 0.42, h_ground + 0.28),
        frame_L='pommel', frame_R='cantle', curl_L=0.45, curl_R=0.45,
        foot_L=(GROUND_SPACE, 0.10, 0.56, 0.0), foot_R=(GROUND_SPACE, -0.06, 0.64, 0.0), pitch_L=0., pitch_R=0.,
    )
    step_stirrup = dict(
        hips=(-0.02, 0.42, step_height), pelvis_rot=(16., -48., 0.), lean=35., twist=-4., side=2., head=(4., -8., 0.),
        hand_L='pommel', hand_R='cantle', frame_L='pommel', frame_R='cantle', curl_L=0.75, curl_R=0.65,
        foot_L='stirrup', foot_R=(GROUND_SPACE, -0.14, 0.54, max(0.16, step_height - 0.75 * rig.leg_length)),
        pitch_L=-4., pitch_R=14.,
    )
    spring_up = dict(
        hips=(-0.02, 0.36, seat.z + 0.12), pelvis_rot=(16., -26., 0.), lean=35., twist=-2., side=2., head=(-2., -6., 0.),
        hand_L='pommel', hand_R='cantle', frame_L='pommel', frame_R='cantle', curl_L=0.80, curl_R=0.65,
        foot_L='stirrup', foot_R=(-0.38, 0.38, seat.z + 0.12), pitch_L=-6., pitch_R=20.,
    )
    swing_apex = dict(
        hips=(0.00, 0.16, seat.z + 0.15), pelvis_rot=(16., -14., 0.), lean=35., twist=-2., side=0., head=(-4., -4., 0.),
        hand_L='reins', hand_R='pommel', frame_L='reins', frame_R='pommel', curl_L=0.84, curl_R=0.70,
        foot_L='stirrup', foot_R=(-0.44, 0.00, seat.z + 0.22), pitch_L=-6., pitch_R=22.,
    )
    swing_over = dict(
        hips=(0.01, 0.04, seat.z + 0.08), pelvis_rot=(16., -6., 0.), lean=35., twist=0., side=0., head=(-4., -2., 0.),
        hand_L='reins', hand_R='pommel', frame_L='reins', frame_R='pommel', curl_L=0.88, curl_R=0.72,
        foot_L='stirrup', foot_R=(-0.24, -0.38, seat.z + 0.06), pitch_L=-6., pitch_R=12.,
    )
    seated = dict(
        hips=tuple(seat), pelvis_rot=(6., 0., 0.), lean=10., twist=0., side=0., head=(-4., 0., 0.),
        hand_L='reins', hand_R='reins', frame_L='reins', frame_R='reins', curl_L=0.88, curl_R=0.88,
        foot_L='stirrup', foot_R='stirrup', pitch_L=-6., pitch_R=-6.,
    )
    mount_keys = [
        (0.00, beside),
        (0.34, step_stirrup),
        (0.68, spring_up),
        (0.94, swing_apex),
        (1.18, swing_over),
        (1.44, seated),
        (1.60, seated),
    ]
    dismount_keys = [
        (0.00, seated),
        (0.24, swing_over),
        (0.48, swing_apex),
        (0.72, spring_up),
        (1.00, step_stirrup),
        (1.24, beside),
        (1.40, beside),
    ]
    return {'HorseMount': (1.60, mount_keys), 'HorseDismount': (1.40, dismount_keys)}


def bake_transition_clip(rig, hands, foot_offset, name, duration, keys, horse_clip_data):
    """Bake HorseMount or HorseDismount at 60 fps against the horse's Idle trajectory."""
    traj = horse_clip_data['trajectory']
    frames = round(duration * FPS) + 1
    poses, horse_frames, worst = [], [], {}

    def target_point(val, side, fr):
        if val == 'reins':
            return rein_grip_point(fr, side)
        if val == 'pommel':
            return pommel_point(fr, side)
        if val == 'cantle':
            return cantle_point(fr)
        if val == 'stirrup':
            return stirrup_tread_point(rig, fr, side)
        if isinstance(val, tuple) and val[0] == GROUND_SPACE:
            return Vector(val[1:])
        return Vector(val)

    def hand_wrist(key, side, fr):
        D = hands.frame(side, key['frame_' + side], fr)
        pt = target_point(key['hand_' + side], side, fr)
        if key['hand_' + side] in ('reins', 'pommel', 'cantle'):
            return hands.wrist_for_grip(side, pt, D), D
        return pt, D

    for f in range(frames):
        t = f / FPS
        fr = traj[min(f, len(traj) - 1)]
        idx = max(j for j, (kt, _) in enumerate(keys) if kt <= t + 1e-9)
        t0, a = keys[idx]
        if idx == len(keys) - 1:
            b, s = a, 0.0
        else:
            t1, b = keys[idx + 1]
            s = (t - t0) / max(1e-6, t1 - t0)
        e = ease(s)

        hips = smooth(a['hips'], b['hips'], s)
        pelvis_rot = smooth(a['pelvis_rot'], b['pelvis_rot'], s)
        lean = smooth(a['lean'], b['lean'], s)
        twist = smooth(a['twist'], b['twist'], s)
        side_lean = smooth(a['side'], b['side'], s)
        head_rot = smooth(a['head'], b['head'], s)

        wLa, DLa = hand_wrist(a, 'L', fr)
        wLb, DLb = hand_wrist(b, 'L', fr)
        w_L = wLa.lerp(wLb, e)
        D_L = DLa.to_quaternion().slerp(DLb.to_quaternion(), e).to_matrix()

        wRa, DRa = hand_wrist(a, 'R', fr)
        wRb, DRb = hand_wrist(b, 'R', fr)
        w_R = wRa.lerp(wRb, e)
        D_R = DRa.to_quaternion().slerp(DRb.to_quaternion(), e).to_matrix()

        sole_L = target_point(a['foot_L'], 'L', fr).lerp(target_point(b['foot_L'], 'L', fr), e)
        sole_R = target_point(a['foot_R'], 'R', fr).lerp(target_point(b['foot_R'], 'R', fr), e)
        Rf_L = rot(smooth(a['pitch_L'], b['pitch_L'], s), pelvis_rot[1] + 6.0, 0.0)
        Rf_R = rot(smooth(a['pitch_R'], b['pitch_R'], s), pelvis_rot[1] - 6.0, 0.0)

        state = dict(
            hips=hips, pelvis_rot=pelvis_rot, lean=lean, twist=twist, side=side_lean, head=head_rot,
            D_L=D_L, D_R=D_R, wrist_L=w_L, wrist_R=w_R,
            curl_L=smooth(a['curl_L'], b['curl_L'], s),
            curl_R=smooth(a['curl_R'], b['curl_R'], s),
            Rf_L=Rf_L, Rf_R=Rf_R, sole_L=sole_L, sole_R=sole_R, auto_reach=False, transition_reach=True,
        )
        short = solve_pose(rig, hands, foot_offset, fr, state)
        for limb, v in short.items():
            worst[limb] = max(worst.get(limb, 0.), v)
        poses.append({n: rig.basis[n].copy() for n in rig.order})
        horse_frames.append({
            'seat': [round(x, 4) for x in state['hips']],
            'grip_L': fr['grip_L'],
            'grip_R': fr['grip_R'],
            'stirrup_L': [round(x, 4) for x in sole_L],
            'stirrup_R': [round(x, 4) for x in sole_R],
            'bit': fr['bit'],
        })

    return poses, {
        'frames': frames,
        'duration': duration,
        'loop': False,
        'horse_clip': 'Idle',
        'horse': horse_frames,
        'reach_error_cm': {k: round(v * 100, 2) for k, v in worst.items()},
    }


# ----------------------------------------------------------------------------------------------------- review renders

def load_horse_and_tack(breed_slug='arabian', tack_id='00'):
    """Import the breed's horse.glb and tack (Saddle_<id>.glb, Reins_<id>.glb) into the review scene in Yorimichi space."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(HERE / breed_slug / 'horse.glb'))
    added_horse = set(bpy.data.objects) - before
    horse_arm = [o for o in added_horse if o.type == 'ARMATURE'][0]

    # Rotate horse root by +90 deg around Z so (-Y_b, X_b, Z_b) aligns with Yorimichi (+X fwd, +Y left, +Z up)
    rot_z = Matrix.Rotation(math.pi / 2, 4, 'Z')
    top_horse = horse_arm
    while top_horse.parent is not None:
        top_horse = top_horse.parent
    top_horse.matrix_world = rot_z @ top_horse.matrix_world
    bpy.context.view_layer.update()

    # Reference mesh parent transform on horse_arm
    horse_mesh = [o for o in added_horse if o.type == 'MESH' and o.parent == horse_arm and 'Body' in o.name][0]
    ref_mpi = horse_mesh.matrix_parent_inverse.copy()
    ref_mb = horse_mesh.matrix_basis.copy()

    for part in ('Saddle', 'Reins'):
        t_before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(HERE / breed_slug / 'tack' / f'{part}_{tack_id}.glb'))
        t_added = set(bpy.data.objects) - t_before
        t_meshes = [o for o in t_added if o.type == 'MESH' and not o.name.startswith('Icosphere')]
        for m in t_meshes:
            m.parent = horse_arm
            m.matrix_parent_inverse = ref_mpi.copy()
            m.matrix_basis = ref_mb.copy()
            for mod in m.modifiers:
                if mod.type == 'ARMATURE':
                    mod.object = horse_arm
        for ob in list(t_added):
            if ob not in t_meshes and ob.name in bpy.data.objects:
                bpy.data.objects.remove(ob, do_unlink=True)
    bpy.context.view_layer.update()
    return horse_arm


def pose_horse(horse_arm, horse_clip_name, f60):
    """Set the active 60 fps horse action on `horse_arm` and evaluate the scene at frame `f60`."""
    act = bpy.data.actions.get(horse_clip_name)
    if act is None:
        return
    horse_arm.animation_data_create()
    for tr in horse_arm.animation_data.nla_tracks:
        tr.mute = True
    if horse_arm.animation_data.action != act:
        horse_arm.animation_data.action = act
    if act.slots and horse_arm.animation_data.action_slot != act.slots[0]:
        horse_arm.animation_data.action_slot = act.slots[0]
    bpy.context.scene.frame_set(int(round(f60)))
    bpy.context.view_layer.update()


def sample_breed_clip_from_arm(horse_arm, clip_name, ref_clip_data, breed_contacts):
    """Sample a 60 Hz trajectory directly from `horse_arm` in Yorimichi space for exact multi-breed review renders."""
    n_frames = ref_clip_data['frames']
    seat_offset_z = breed_contacts['seat_offset_z']
    s = breed_contacts['scale_ratio']
    mw = horse_arm.matrix_world.copy()
    rest_st2_inv_L = (mw @ horse_arm.data.bones['Stirrup_2_L'].matrix_local).inverted()
    rest_st2_inv_R = (mw @ horse_arm.data.bones['Stirrup_2_R'].matrix_local).inverted()
    rest_tread_L = Vector(breed_contacts['stirrup_L'])
    rest_tread_R = Vector(breed_contacts['stirrup_R'])
    traj = []
    for f60 in range(n_frames):
        pose_horse(horse_arm, clip_name, f60)
        pts = {
            b: (mw @ horse_arm.pose.bones[b].head).copy()
            for b in (
                'Saddle_Root', 'Spine_1', 'Spine_2', 'Neck_1', 'Head', 'Bit',
                'Stirrup_2_L', 'Stirrup_2_R', 'Reins_5_L', 'Reins_5_R', 'Reins_C',
            )
        }
        pose_st2_L = mw @ horse_arm.pose.bones['Stirrup_2_L'].matrix
        pose_st2_R = mw @ horse_arm.pose.bones['Stirrup_2_R'].matrix
        stirrup_L = (pose_st2_L @ rest_st2_inv_L) @ rest_tread_L
        stirrup_R = (pose_st2_R @ rest_st2_inv_R) @ rest_tread_R
        r5L, r5R, rc = pts['Reins_5_L'], pts['Reins_5_R'], pts['Reins_C']
        grip_L = Vector((
            rc.x + 0.11 * (r5L.x - rc.x),
            rc.y + 0.44 * (r5L.y - rc.y),
            rc.z + 0.44 * (r5L.z - rc.z) + 0.001,
        ))
        grip_R = Vector((
            rc.x + 0.11 * (r5R.x - rc.x),
            rc.y + 0.44 * (r5R.y - rc.y),
            rc.z + 0.44 * (r5R.z - rc.z) + 0.001,
        ))
        seat = pts['Saddle_Root'] + Vector((0.095 * s, 0.0, seat_offset_z))
        sp_vec = (pts['Spine_2'] - pts['Spine_1']).normalized()
        pitch_deg = math.degrees(math.asin(max(-1.0, min(1.0, sp_vec.z))))
        v3 = lambda v: [round(v.x, 4), round(v.y, 4), round(v.z, 4)]
        traj.append({
            'seat': v3(seat),
            'saddle_root': v3(pts['Saddle_Root']),
            'spine_2': v3(pts['Spine_2']),
            'neck_1': v3(pts['Neck_1']),
            'head': v3(pts['Head']),
            'bit': v3(pts['Bit']),
            'stirrup_L': v3(stirrup_L),
            'stirrup_R': v3(stirrup_R),
            'grip_L': v3(grip_L),
            'grip_R': v3(grip_R),
            'reins_5_L': v3(r5L),
            'reins_5_R': v3(r5R),
            'reins_c': v3(rc),
            'pitch_deg': round(pitch_deg, 3),
        })
    out = dict(ref_clip_data)
    out['trajectory'] = traj
    return out


def render_clip_review(scene, cam, horse_arm, rig, name, info, out, char_id, breed_slug, tack_id, count=3):
    frames = info['frames']
    horse_clip = info['horse_clip']
    sample_indices = [round((frames - 1) * i / max(1, count - 1)) for i in range(count)] if count > 1 else [0]
    for idx_i, f in enumerate(sample_indices):
        pose_horse(horse_arm, horse_clip, f)
        fr_h = info['horse'][f]
        seat = Vector(fr_h['seat'])
        centre = Vector((0.35, 0.0, seat.z - 0.05))
        grip_mid = 0.5 * (Vector(fr_h['grip_L']) + Vector(fr_h['grip_R']))
        views = [
            ('side', centre + Vector((0.0, -4.4, 0.25)), centre, 62),
            ('q34', centre + Vector((2.6, 2.8, 0.85)), centre, 54),
        ]
        if idx_i == 0:
            views.append(('hands', grip_mid + Vector((0.46, 0.44, 0.14)), grip_mid + Vector((-0.02, 0.0, -0.015)), 82))
        for vname, eye, tgt, lens in views:
            look(cam, eye, tgt, lens=lens)
            scene.render.filepath = str(out / f'{char_id}_{breed_slug}_tack{tack_id}_{name}_{vname}_{idx_i}.png')
            bpy.ops.render.render(write_still=True)


def render_clip_video(scene, cam, horse_arm, name, info, out, char_id, breed_slug, tack_id):
    """Render a 30 fps MP4 animation preview of `name` (repeating looping gaits 3x for clear motion review)."""
    import shutil
    import subprocess
    frames = info['frames']
    horse_clip = info['horse_clip']
    is_loop = info['loop']
    tmp_dir = out / f'_frames_{char_id}_{breed_slug}_tack{tack_id}_{name}'
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    orig_x, orig_y = scene.render.resolution_x, scene.render.resolution_y
    orig_samples = scene.eevee.taa_render_samples
    scene.render.resolution_x, scene.render.resolution_y = 640, 360
    scene.eevee.taa_render_samples = 16

    seat0 = Vector(info['horse'][-1]['seat']) if name in ('HorseMount', 'HorseDismount') else Vector(info['horse'][0]['seat'])
    if name in ('HorseMount', 'HorseDismount'):
        centre = Vector((0.18, 0.14, seat0.z - 0.18))
        look(cam, centre + Vector((2.85, 3.05, 0.75)), centre, lens=35)
    else:
        centre = Vector((0.30, 0.0, seat0.z + 0.06))
        look(cam, centre + Vector((2.65, 2.85, 0.80)), centre, lens=44)

    step = 2  # 30 fps from 60 fps bake
    frame_indices = list(range(0, frames, step))
    for out_idx, f in enumerate(frame_indices):
        pose_horse(horse_arm, horse_clip, f)
        scene.render.filepath = str(tmp_dir / f'frame_{out_idx:04d}.png')
        bpy.ops.render.render(write_still=True)

    mp4_path = out / f'{char_id}_{breed_slug}_tack{tack_id}_{name}.mp4'
    cmd = ['ffmpeg', '-y']
    if is_loop:
        cmd += ['-stream_loop', '2']
    cmd += [
        '-framerate', '30',
        '-i', str(tmp_dir / 'frame_%04d.png'),
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '20',
        '-pix_fmt', 'yuv420p',
        str(mp4_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    scene.render.resolution_x, scene.render.resolution_y = orig_x, orig_y
    scene.eevee.taa_render_samples = orig_samples
    print(f'RENDERED VIDEO: {mp4_path}', flush=True)


def main(args):
    global OUT
    manifest = load_manifest()
    module, OUT = character(args.character, 'horse')
    prepared = module.prepare(module.SOURCE)
    scene, arm = prepared.scene, prepared.arm
    scene.render.fps, scene.render.fps_base = FPS, 1
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()

    rig = Rig(arm)
    hands = Hands(rig)
    char_meshes = list(prepared.meshes)
    foot_offset = {}
    for side in 'LR':
        ankle = rig.world(rig.rest['foot_' + side].translation)
        toe = rig.world(rig.rest['toe_' + side].translation)
        foot_bname = 'foot_' + side
        toe_bname = 'toe_' + side
        foot_pts = []
        for cm in char_meshes:
            vg_map = {vg.name: vg.index for vg in cm.vertex_groups}
            target_vgs = {vg_map[b] for b in (foot_bname, toe_bname) if b in vg_map}
            if not target_vgs:
                continue
            mw = cm.matrix_world
            for v in cm.data.vertices:
                if sum(g.weight for g in v.groups if g.group in target_vgs) > 0.25:
                    foot_pts.append(mw @ v.co)
        if foot_pts:
            min_fx = min(p.x for p in foot_pts)
            max_fx = max(p.x for p in foot_pts)
            min_fy = min(p.y for p in foot_pts)
            max_fy = max(p.y for p in foot_pts)
            min_fz = min(p.z for p in foot_pts)
            # Ball of the sneaker sole (58% from heel to toe tip) rests directly on the étrier tread bar center
            contact_x = min_fx + 0.58 * (max_fx - min_fx)
            contact_y = 0.5 * (min_fy + max_fy)
            foot_offset[side] = Vector((ankle.x - contact_x, ankle.y - contact_y, ankle.z - min_fz - 0.003))
        else:
            foot_offset[side] = Vector((ankle.x - toe.x, 0.0, ankle.z))

    trans = transition_keys(rig, manifest['clips']['Idle']['trajectory'][0])
    all_clips = list(MOUNTED_SPECS.keys()) + list(trans.keys())
    wanted = set(args.clips.split(',')) if args.clips else set(all_clips)

    (OUT / 'fbx').mkdir(parents=True, exist_ok=True)
    report = {'source_sha256': prepared.record['native_sha256'], 'fps': FPS, 'clips': {}}
    actions, infos = {}, {}
    for name in all_clips:
        if name not in wanted:
            continue
        if name in MOUNTED_SPECS:
            spec = MOUNTED_SPECS[name]
            poses, info = bake_mounted_clip(rig, hands, foot_offset, name, spec, manifest['clips'][spec['horse_clip']])
        else:
            dur, keys = trans[name]
            poses, info = bake_transition_clip(rig, hands, foot_offset, name, dur, keys, manifest['clips']['Idle'])
        action = write_action(rig, 'Horse · ' + name, poses)
        actions[name] = action
        scene.frame_start, scene.frame_end = 0, info['frames'] - 1
        scene.frame_set(0)
        bpy.ops.object.select_all(action='DESELECT')
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        export_scene_fbx(
            filepath=str(OUT / 'fbx' / f'A_{name}.fbx'),
            object_types={'ARMATURE'},
            bake_anim=True,
            **module.FBX,
        )
        infos[name] = info
        report['clips'][name] = {k: info[k] for k in EXPORTED}
        print(args.character.upper(), 'HORSE CLIP', name, info['frames'], json.dumps(info['reach_error_cm']), flush=True)

    out_json = OUT / ('export.json' if wanted == set(all_clips) else 'export-partial.json')
    out_json.write_text(json.dumps(report, indent=1) + '\n')

    if args.review:
        out_dir = Path(args.review)
        out_dir.mkdir(parents=True, exist_ok=True)
        cam = studio(scene, name='HorseStudio', background=(.82, .81, .78), strength=.95, key=(28, 46, -38),
                     fill=(1.2, 45, 55, 135))
        horse_arm = load_horse_and_tack(args.breed, args.tack)
        breed_contacts = manifest['breeds'][args.breed]['contacts']
        review_wanted = set(args.review_clips.split(',')) if args.review_clips else set(actions.keys())
        video_wanted = set(args.review_video.split(',')) if args.review_video else set()
        sampled_breed_clips = {}
        scene.render.resolution_x, scene.render.resolution_y = 800, 600
        for name in all_clips:
            if name not in actions or (name not in review_wanted and name not in video_wanted):
                continue
            if args.breed != manifest['reference_breed']:
                h_clip = MOUNTED_SPECS[name]['horse_clip'] if name in MOUNTED_SPECS else 'Idle'
                if h_clip not in sampled_breed_clips:
                    sampled_breed_clips[h_clip] = sample_breed_clip_from_arm(
                        horse_arm, h_clip, manifest['clips'][h_clip], breed_contacts
                    )
                if name in MOUNTED_SPECS:
                    spec = MOUNTED_SPECS[name]
                    r_poses, r_info = bake_mounted_clip(rig, hands, foot_offset, name, spec, sampled_breed_clips[h_clip])
                else:
                    r_idle = sampled_breed_clips['Idle']
                    r_trans = transition_keys(rig, r_idle['trajectory'][0])
                    dur, keys = r_trans[name]
                    r_poses, r_info = bake_transition_clip(rig, hands, foot_offset, name, dur, keys, r_idle)
                r_action = write_action(rig, f'HorseReview · {name}', r_poses)
            else:
                r_action = actions[name]
                r_info = infos[name]
            arm.animation_data.action = r_action
            if r_action.slots:
                arm.animation_data.action_slot = r_action.slots[0]
            if name in review_wanted:
                render_clip_review(
                    scene, cam, horse_arm, rig, name, r_info,
                    out_dir, args.character, args.breed, args.tack, count=args.review_count,
                )
            if name in video_wanted:
                render_clip_video(
                    scene, cam, horse_arm, name, r_info,
                    out_dir, args.character, args.breed, args.tack,
                )

    print(f'{args.character.upper()} HORSE EXPORT COMPLETE: {len(report["clips"])} clips', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--clips', help='comma-separated clip names (default: all 13)')
    parser.add_argument('--review', help='render review images into this folder')
    parser.add_argument('--review-clips', default='HorseIdle,HorseWalk,HorseTrot,HorseCanter,HorseGallop,HorseMount',
                        help='comma-separated clip names to render in review mode')
    parser.add_argument('--review-video', default='',
                        help='comma-separated clip names to render as 30fps MP4 previews in review mode')
    parser.add_argument('--review-count', type=int, default=1, help='frames to render per clip in review mode')
    parser.add_argument('--character', default='cairo', help='playable character folder (cairo, modori, nox, paul)')
    parser.add_argument('--breed', default='arabian', help='horse breed slug for review renders')
    parser.add_argument('--tack', default='00', help='tack set ID (00..06) for review renders')
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
