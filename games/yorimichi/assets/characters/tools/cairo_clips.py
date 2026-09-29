"""Clip definitions for the Cairo animation library.

Each clip is a pose function of time on the `cairo_rig.Rig` helper. Units are
armature units (the character stands about 0.72 tall; the accepted sprint
travels 3.443 units/s). Timings follow the Seedance references listed in the
library README; the reference revisions are recorded in the manifest.
All clips are in place: the controller owns translation and yaw.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import math
from mathutils import Quaternion, Vector
from cairo_rig import (X, Y, Z, TAU, q_axis, smooth, smoother, ramp, lerp, clamp, hermite, Timeline)

FPS = 60


class Clip:
    def __init__(self, name, duration, pose, loop=False, kind='one-shot', markers=(), notes='', travel=None,
                 standing_garments=False, action_name=None, reference=None, entry='Idle', exit='Idle', yaw=None):
        self.name = name
        self.frames = round(duration * FPS) + 1
        self.duration = (self.frames - 1) / FPS
        self.pose = pose
        self.loop = loop
        self.kind = kind
        self.markers = list(markers)
        self.notes = notes
        self.travel = travel
        self.standing_garments = standing_garments
        self.action_name = action_name or f'{name} · library'
        self.reference = reference
        self.entry, self.exit, self.yaw = entry, exit, yaw
        self.poses = None


# --- shared body vocabulary --------------------------------------------------
NEUTRAL_FEET = {}
RELAX = {'curl': .12, 'thumb': .08}
FIST = {'curl': .92, 'thumb': .30, 'opposition': .90, 'spread': -.12}
OPEN = {'curl': .02, 'thumb': .02, 'spread': .45}


def neutral_feet(rig):
    if not NEUTRAL_FEET:
        saved = dict(rig.M)
        rig.begin(); rig.fill()
        for side in ['Left', 'Right']:
            low = rig.sole_low(side)
            NEUTRAL_FEET[side] = Vector((low.x, low.y, 0))
        rig.M = saved
    return NEUTRAL_FEET


SOLE_REFERENCE = {}


def ankle_for(rig, side, sole, pitch=0, yaw=0, toe=0):
    """Ankle position for a sole placed at `sole` (z relative to the floor).

    x/y place the flat-foot sole reference (the neutral lowest point, rotated
    by the yaw) so the foot never jumps when the lowest point switches between
    heel and toe; z uses the actual lowest sole point for this orientation."""
    foot = side + 'Foot'
    saved = dict(rig.M)
    if side not in SOLE_REFERENCE:
        rig.M[foot] = rig.neutral[foot].to_matrix().to_4x4()
        rig.M[side + 'ToeBase'] = rig.M[foot] @ rig.rest[foot].inverted() @ rig.rest[side + 'ToeBase']
        SOLE_REFERENCE[side] = rig.sole_low(side)
    rotation = (q_axis(Z, yaw) @ q_axis(Y, pitch) @ rig.neutral[foot]).to_matrix().to_4x4()
    rig.M[foot] = rotation
    rig.M[side + 'ToeBase'] = rotation @ rig.rest[foot].inverted() @ rig.rest[side + 'ToeBase']
    rig.bend(side + 'ToeBase', Y, -toe)
    low = rig.sole_low(side)
    rig.M = saved
    reference = q_axis(Z, yaw) @ SOLE_REFERENCE[side]
    return Vector((sole.x - reference.x, sole.y - reference.y, rig.floor + sole.z - low.z))


def contact_weight(lift):
    """How much a foot constrains the pelvis: full on the floor, fading out by 3 cm of lift."""
    return 1 - smooth(lift / .03)


def settle_hips(rig, hips_target, ankles, extension=.985, weights=None):
    """Lower the pelvis so that each planted leg stays within reach.

    `weights` (0..1 per side) blend the constraint in as a foot approaches the
    floor, so a heel strike beyond reach never snaps the pelvis."""
    z = hips_target.z
    for side, ankle in ankles.items():
        w = 1.0 if weights is None else weights.get(side, 1.0)
        if w <= 0:
            continue
        upper, lower = side + 'UpLeg', side + 'Leg'
        reach = (rig.length[upper] + rig.length[lower]) * extension
        offset = rig.neutral_head[upper] - rig.neutral_head['Hips']
        hip_xy = Vector((hips_target.x + offset.x, hips_target.y + offset.y, 0))
        d = min((Vector((ankle.x, ankle.y, 0)) - hip_xy).length, reach * .93)
        if True:
            limit = ankle.z + math.sqrt(reach * reach - d * d) - offset.z
            z = min(z, lerp(hips_target.z, limit, w) if limit < hips_target.z else z)
    return Vector((hips_target.x, hips_target.y, z))


SIDES = ['Left', 'Right']


def body_params():
    """Default parameter set for the generic standing/airborne pose."""
    p = {'hx': 0, 'hy': 0, 'hz': -.006, 'hp': 0, 'hyaw': 0, 'hr': 0,
         'sp': 0, 'syaw': 0, 'sr': 0, 'hdp': 0, 'hdyaw': 0, 'hdr': 0, 'air': 0, 'spin': 0}
    for s in ['l', 'r']:
        p.update({f'{s}fx': 0, f'{s}fy': 0, f'{s}fz': 0, f'{s}fp': 0, f'{s}fyaw': 0, f'{s}toe': 0,
                  f'{s}swing': 0, f'{s}spread': 6.0, f'{s}twist': 0, f'{s}elbow': 6, f'{s}wp': 0, f'{s}wy': 0, f'{s}ft': 0,
                  f'{s}curl': .12, f'{s}thumb': .08, f'{s}opp': 0, f'{s}fspread': 0, f'{s}pole': 0, f'{s}hinge': 0})
    return p


def apply_params(rig, p, feet_relative_to_hips=False, centre_offset=Vector((0, 0, .05))):
    """Pose the body from a flat parameter dict (see body_params).

    Grounded: feet are sole positions on the floor (z = lift) and the pelvis
    settles to keep planted legs in reach. Airborne (`air`): the pelvis is
    explicit and feet are ankle offsets from the pelvis. `spin` rotates the
    whole body forward about the pelvis-plus-centre_offset point."""
    feet0 = neutral_feet(rig)
    hips_offset = Vector((p['hx'], p['hy'], p['hz']))
    ankles, planted = {}, {}
    for s, side in zip(['l', 'r'], SIDES):
        if p['air']:
            ankles[side] = rig.neutral_head['Hips'] + hips_offset + Vector((p[f'{s}fx'], feet0[side].y + p[f'{s}fy'], p[f'{s}fz']))
            planted[side] = False
        else:
            p[f'{s}fz'] = max(0.0, p[f'{s}fz'])
            sole = Vector((feet0[side].x + p[f'{s}fx'], feet0[side].y + p[f'{s}fy'], p[f'{s}fz']))
            ankles[side] = ankle_for(rig, side, sole, p[f'{s}fp'], p[f'{s}fyaw'], p[f'{s}toe'])
            planted[side] = p[f'{s}fz'] < 1e-4
    target = rig.neutral_head['Hips'] + hips_offset
    if p['air']:
        position = target
    else:
        position = settle_hips(rig, target, ankles, weights={side: contact_weight(p[f'{s}fz']) for s, side in zip(['l', 'r'], SIDES)})
    spin = q_axis(Y, p['spin']) if p['spin'] else None
    centre = rig.neutral_head['Hips'] + hips_offset + centre_offset
    rig.hips(position - rig.neutral_head['Hips'], p['hp'], p['hyaw'], p['hr'], centre=centre, spin=spin)
    rig.spine(p['sp'], p['syaw'], p['sr'], head_pitch=p['hdp'], head_yaw=p['hdyaw'], head_roll=p['hdr'])
    if spin is not None:
        # The head follows the somersault instead of staying level.
        rig.set_rot('Head', spin @ q_axis(Z, p['hdyaw']) @ q_axis(Y, p['hdp']) @ rig.neutral['Head'])
        rig.rotate('Neck', Quaternion())
    for s, side in zip(['l', 'r'], SIDES):
        ankle = ankles[side]
        if spin is not None:
            ankle = centre + spin @ (ankle - centre)
        pole = (spin @ Vector((1, 0, 0))) if spin is not None else Vector((1, .35 * (1 if side == 'Left' else -1) * p[f'{s}pole'], 0))
        pitch = p[f'{s}fp'] + (p['spin'] if spin is not None else 0)
        rig.leg(side, ankle, pitch, p[f'{s}fyaw'], p[f'{s}toe'], pole=pole)
        rig.arm(side, swing=p[f'{s}swing'], spread=p[f'{s}spread'], twist=p[f'{s}twist'], elbow=p[f'{s}elbow'],
                wrist_pitch=p[f'{s}wp'], wrist_yaw=p[f'{s}wy'], forearm_twist=p[f'{s}ft'], hinge=p[f'{s}hinge'])
        rig.hand(side, curl=p[f'{s}curl'], thumb=p[f'{s}thumb'], opposition=p[f'{s}opp'], spread=p[f'{s}fspread'])
    return {'left_planted': planted['Left'], 'right_planted': planted['Right'], 'hips': position}


def both(**kw):
    """Expand mirrored parameters: swing=10 → lswing=10, rswing=10."""
    out = {}
    for k, v in kw.items():
        out['l' + k] = v
        out['r' + k] = v
    return out


def timeline_clip(keys, ease='flow', **extra):
    tl = Timeline(keys, body_params(), ease=ease)

    def pose(rig, t):
        return apply_params(rig, tl.at(t), **extra)
    return pose


# --- Idle: quiet breathing and weight shift, 4.0 s loop ----------------------
def idle_pose(rig, t):
    T = 4.0
    u = t / T
    breath = math.sin(TAU * 2 * u - math.pi / 2)            # two breaths per loop
    shift = math.sin(TAU * u)                                 # one weight shift per loop
    look = .5 * (1 - math.cos(TAU * u))
    p = body_params()
    p.update({'hy': .007 * shift, 'hz': -.008 - .0015 * breath, 'hp': .6 * breath, 'hyaw': -1.5 * shift, 'hr': 1.2 * shift,
              'sp': -1.4 * breath, 'syaw': 1.5 * shift, 'sr': -.8 * shift,
              'hdp': -.8 * breath + .6, 'hdyaw': 5 * math.sin(TAU * u) * look, 'hdr': .8 * shift})
    p.update(both(swing=1.2 * breath - .5, spread=7.5 + .8 * breath, elbow=7 + 1.5 * breath, curl=.12 + .03 * breath, thumb=.08))
    return apply_params(rig, p)


# --- Gait cycles --------------------------------------------------------------
def quintic(t, a, b, va=0.0, vb=0.0):
    d = b - a
    return a + va * t + (10 * d - 6 * va - 4 * vb) * t ** 3 + (-15 * d + 8 * va + 7 * vb) * t ** 4 + (6 * d - 3 * va - 3 * vb) * t ** 5


def gait_foot(u, cfg):
    """Sole trajectory for one foot at cycle phase u: (x relative to body, lift, pitch, planted)."""
    stance, stride = cfg['stance'], cfg['speed'] * cfg['period']
    span = stride * stance
    centre = cfg.get('centre', 0.0)
    if u < stance:
        s = u / stance
        pitch = cfg['heel'] * (1 - smoother(s / .22)) + cfg['toe'] * smoother((s - .62) / .38)
        return centre + span / 2 - span * s, 0.0, pitch, True
    s = (u - stance) / (1 - stance)
    tangent = -stride * (1 - stance)      # matched velocity at takeoff and touchdown
    x = quintic(s, centre - span / 2, centre + span / 2, tangent * cfg.get('takeoff', .35), tangent * cfg.get('landing', .35))
    apex = cfg.get('apex', .42)
    lift = cfg['lift'] * (smoother(s / apex) if s < apex else 1 - smoother((s - apex) / (1 - apex)))
    fold = cfg.get('fold', cfg['toe'] + 10)
    pitch = cfg['toe'] + (fold - cfg['toe']) * smoother(s / .30) + (cfg['heel'] - fold) * smoother((s - .30) / .62)
    return x, lift, pitch, False


# Weight and arm phasing follow Williams' walk chart (ANIMATION_PRINCIPLES.md §2):
# bob_low is the fraction of a step after the contact at which the pelvis is
# lowest (the "down"; it is highest half a step later, the "up"), and arm_peak
# the fraction of a step after the contact at which the arm swing is widest.
# The pre-book values were bob_low 0 (lowest at the contact) and arm_peak .5
# (widest at the passing position).
WALK = {'period': 1.0, 'speed': .62, 'stance': .62, 'lift': .030, 'heel': -14, 'toe': 26, 'fold': 34, 'apex': .45,
        'takeoff': .30, 'landing': .30, 'bob_low': .25, 'arm_peak': .25}
CROUCH_WALK = {'period': 1.1, 'speed': .42, 'stance': .70, 'lift': .022, 'heel': -6, 'toe': 14, 'fold': 18, 'apex': .5,
               'takeoff': .3, 'landing': .3, 'bob_low': .25, 'arm_peak': .25}


def gait_phases(a, cfg):
    """Pelvis bob and arm swing shape for cycle angle a (one cycle = two steps).

    Returns (bob, swing) in -1..1: bob is -1 at the down and +1 at the up;
    swing is +1 when the left leg's opposite arm is fully forward."""
    bob = -math.cos(2 * a - TAU * cfg.get('bob_low', .25))
    swing = math.sin(a + math.pi / 2 - math.pi * cfg.get('arm_peak', .25))
    return bob, swing


def walk_pose(rig, t, cfg=WALK):
    T = cfg['period']
    phase = (t / T) % 1
    feet0 = neutral_feet(rig)
    ankles, planted, pitches, lifts = {}, {}, {}, {}
    for side, offset in [('Left', 0.0), ('Right', 0.5)]:
        u = (phase + offset) % 1
        x, lift, pitch, on = gait_foot(u, cfg)
        sole = Vector((feet0[side].x + x, feet0[side].y * .92, lift))
        ankles[side] = ankle_for(rig, side, sole, pitch)
        planted[side], pitches[side] = on, pitch
        lifts[side] = lift
    a = TAU * phase
    bob_shape, swing_shape = gait_phases(a, cfg)
    bob = .012 * bob_shape
    sway = .008 * math.sin(a)
    target = rig.neutral_head['Hips'] + Vector((0, sway, -.036 + bob))
    position = settle_hips(rig, target, ankles, weights={s: contact_weight(lifts[s]) for s in ankles})
    yaw = 5 * math.sin(a)
    rig.hips(position - rig.neutral_head['Hips'], pitch=3, yaw=yaw, roll=1.5 * math.sin(a))
    rig.spine(pitch=1.5 - .6 * bob_shape, yaw=-7 * math.sin(a), roll=-1.5 * math.sin(a), head_pitch=.6 - .8 * bob_shape)
    for side in SIDES:
        rig.leg(side, ankles[side], pitches[side], pole=Vector((1, 0, 0)))
    swing = 27 * swing_shape
    rig.arm('Left', swing=-swing, spread=7, elbow=20 + 12 * max(0, -swing_shape))
    rig.arm('Right', swing=swing, spread=7, elbow=20 + 12 * max(0, swing_shape))
    for side in SIDES:
        rig.hand(side, curl=.14, thumb=.10)
    return {'left_planted': planted['Left'], 'right_planted': planted['Right']}


CROUCH_HIPS = -.205


def crouch_base(rig, breath=0.0, sway=0.0, yaw=0.0):
    p = body_params()
    p.update({'hz': CROUCH_HIPS - .003 * breath, 'hy': .004 * sway, 'hp': 26 + 1.0 * breath, 'hyaw': yaw,
              'sp': 12 - 1.2 * breath, 'hdp': -8 - .8 * breath, 'hdyaw': -yaw * .5,
              'lfy': .034, 'rfy': -.034, 'lfx': .02, 'rfx': .02, 'lfyaw': 12, 'rfyaw': -12})
    p.update(both(pole=1.0, swing=22 + 1.5 * breath, spread=8, elbow=62, wp=-10, curl=.30, thumb=.15, ft=0))
    return p


def crouch_idle_pose(rig, t):
    T = 3.0
    u = t / T
    breath = math.sin(TAU * u - math.pi / 2)
    sway = math.sin(TAU * u)
    p = crouch_base(rig, breath, sway, yaw=1.5 * sway)
    p['hdyaw'] += 4 * math.sin(TAU * u)
    p['lswing'] += 2 * sway; p['rswing'] -= 2 * sway
    return apply_params(rig, p)


def crouch_walk_pose(rig, t, cfg=CROUCH_WALK):
    T = cfg['period']
    phase = (t / T) % 1
    a = TAU * phase
    feet0 = neutral_feet(rig)
    ankles, planted, pitches, lifts = {}, {}, {}, {}
    for side, offset, sign in [('Left', 0.0, 1), ('Right', 0.5, -1)]:
        u = (phase + offset) % 1
        x, lift, pitch, on = gait_foot(u, cfg)
        sole = Vector((feet0[side].x + x + .01, feet0[side].y + sign * .022, lift))
        ankles[side] = ankle_for(rig, side, sole, pitch, sign * 8)
        planted[side], pitches[side], lifts[side] = on, pitch, lift
    bob_shape, swing_shape = gait_phases(a, cfg)
    target = rig.neutral_head['Hips'] + Vector((0, .004 * math.sin(a), CROUCH_HIPS + .02 + .004 * bob_shape))
    position = settle_hips(rig, target, ankles, weights={s: contact_weight(lifts[s]) for s in ankles})
    rig.hips(position - rig.neutral_head['Hips'], pitch=28, yaw=4 * math.sin(a), roll=1.0 * math.sin(a))
    rig.spine(pitch=10, yaw=-4 * math.sin(a), head_pitch=-8)
    for side, sign in [('Left', 1), ('Right', -1)]:
        rig.leg(side, ankles[side], pitches[side], sign * 8, pole=Vector((1, sign * .3, 0)))
    swing = 7 * swing_shape
    rig.arm('Left', swing=24 - swing, spread=8, elbow=64, wrist_pitch=-10)
    rig.arm('Right', swing=24 + swing, spread=8, elbow=64, wrist_pitch=-10)
    for side in SIDES:
        rig.hand(side, curl=.30, thumb=.15)
    return {'left_planted': planted['Left'], 'right_planted': planted['Right']}


# --- Jump family --------------------------------------------------------------
LAUNCH = dict(hz=.012, hp=8, sp=4, hdp=-4, lfp=28, rfp=28, lfz=.0, rfz=.0, **both(swing=70, spread=10, elbow=18, curl=.25))
APEX = dict(air=1, hz=0, hp=6, sp=4, hdp=-3, lfx=.07, rfx=.065, lfz=-.29, rfz=-.30, lfp=18, rfp=16,
            **both(swing=92, spread=24, elbow=38, curl=.2))
FALL = dict(air=1, hz=0, hp=4, sp=3, hdp=6, lfx=.03, rfx=.03, lfz=-.36, rfz=-.36, lfp=14, rfp=14,
            **both(swing=25, spread=40, elbow=32, curl=.2))

JUMP_START_KEYS = [
    (0.000, {}),
    (0.060, dict(hz=-.070, hp=14, sp=8, hdp=-8, **both(swing=-5, spread=6, elbow=22, curl=.3), lfx=.0, rfx=.0)),
    (0.100, dict(hz=-.030, hp=10, sp=6, hdp=-6, lfp=10, rfp=10, **both(swing=36, spread=8, elbow=22, curl=.25))),
    (0.1333, LAUNCH),
]

JUMP_RISE_KEYS = [
    (0.000, dict(LAUNCH, air=1, lfx=-.02, rfx=-.02, lfz=-.405, rfz=-.405)),
    (0.160, dict(air=1, hz=0, hp=6, sp=4, hdp=-5, lfx=-.01, rfx=-.01, lfz=-.39, rfz=-.39, lfp=32, rfp=32, **both(swing=150, spread=14, elbow=12, curl=.25))),
    (0.330, dict(air=1, hz=0, hp=6, sp=4, hdp=-4, lfx=.04, rfx=.04, lfz=-.33, rfz=-.335, lfp=22, rfp=22, **both(swing=125, spread=20, elbow=25, curl=.22))),
    (0.550, APEX),
]


def fall_pose(rig, t):
    T = 1.1
    u = t / T
    w = math.sin(TAU * u)
    p = body_params(); p.update(FALL)
    p.update({'hp': 4 + 1.5 * w, 'sr': 1.5 * math.sin(TAU * u + 1), 'hdp': 6 - 1.5 * w,
              'lfz': -.36 + .012 * w, 'rfz': -.36 - .012 * w, 'lfx': .03 + .01 * w, 'rfx': .03 - .01 * w})
    p.update({'lswing': 25 + 5 * w, 'rswing': 25 - 5 * w, 'lspread': 48 + 6 * math.sin(TAU * u + .8), 'rspread': 48 + 6 * math.sin(TAU * u + .8),
              'lelbow': 32 + 4 * w, 'relbow': 32 - 4 * w})
    return apply_params(rig, p)


LAND_KEYS = [
    (0.000, dict(hz=-.020, hp=8, sp=5, hdp=2, lfy=.012, rfy=-.012, lfp=6, rfp=6, **both(swing=22, spread=40, elbow=35, curl=.2))),
    (0.120, dict(hz=-.105, hp=20, sp=10, hdp=-6, lfy=.012, rfy=-.012, **both(swing=30, spread=18, elbow=55, curl=.25))),
    (0.260, dict(hz=-.040, hp=8, sp=4, hdp=-2, lfy=.008, rfy=-.008, **both(swing=8, spread=6, elbow=25, curl=.15))),
    (0.4333, dict(hz=-.008, lfy=0, rfy=0, **both(swing=0, spread=6, elbow=6, curl=.12))),
]

HARD_LAND_KEYS = [
    (0.000, dict(hz=-.030, hp=14, sp=8, hdp=0, lfy=.030, rfy=-.030, lfx=.02, rfx=-.02, lfp=8, rfp=8, **both(swing=25, spread=40, elbow=35, curl=.25))),
    (0.130, dict(hz=-.165, hp=42, sp=18, hdp=-14, lfy=.030, rfy=-.030, lfx=.02, rfx=-.02, lfyaw=8, rfyaw=-8, lswing=55, lspread=25, lelbow=40, rswing=70, rspread=6, relbow=8, rcurl=.15, lcurl=.3, lpole=1, rpole=1)),
    (0.300, dict(hz=-.160, hp=40, sp=16, hdp=-16, lfy=.030, rfy=-.030, lfx=.02, rfx=-.02, lfyaw=8, rfyaw=-8, lswing=50, lspread=22, lelbow=45, rswing=66, rspread=6, relbow=10, lpole=1, rpole=1)),
    (0.500, dict(hz=-.070, hp=16, sp=6, hdp=-6, lfy=.016, rfy=-.016, lfx=.01, rfx=-.01, lfyaw=3, rfyaw=-3, **both(swing=14, spread=8, elbow=25, curl=.15, pole=.4))),
    (0.700, dict(hz=-.008, lfy=0, rfy=0, lfx=0, rfx=0, lfyaw=0, rfyaw=0, **both(swing=0, spread=6, elbow=6, curl=.12, pole=0))),
]


def double_jump_pose(rig, t):
    """Tuck, one forward somersault about the body centre, open upright."""
    D = .75
    boost = smoother(t / .10)
    tuck_in = smoother((t - .06) / .14)
    tuck_out = 1 - smoother((t - .44) / .20)
    tuck = min(tuck_in, tuck_out)
    # Continuous rotation: eased start, linear middle, eased finish; 360° by 0.60 s.
    r0, r1 = .08, .60
    s = clamp((t - r0) / (r1 - r0))
    spin = 360 * (s * s * (3 - 2 * s) * .35 + s * .65) if s < 1 else 360.0
    spin = min(360.0, spin)
    p = body_params()
    p.update(APEX)
    # Legs: from apex dangle to a tight tuck (knees to chest), then to the fall pose.
    tucked = dict(lfx=.16, rfx=.16, lfz=-.13, rfz=-.135, lfp=55, rfp=55)
    open_pose = dict(FALL)
    for k in ['lfx', 'rfx', 'lfz', 'rfz', 'lfp', 'rfp']:
        p[k] = lerp(lerp(APEX[k], open_pose[k], smoother((t - .46) / .2)), tucked[k], tuck)
    swing = lerp(lerp(92, 130, boost), 118, tuck)      # hands reach the shins in the tuck
    swing = lerp(swing, open_pose['lswing'], smoother((t - .46) / .27) * (1 - tuck))
    elbow = lerp(lerp(38, 12, boost), 105, tuck)
    elbow = lerp(elbow, FALL['lelbow'], smoother((t - .46) / .27) * (1 - tuck))
    spread = lerp(24, 14, tuck)
    p.update(both(swing=swing, elbow=elbow, spread=spread, curl=lerp(.2, .8, tuck), thumb=lerp(.08, .35, tuck), pole=0))
    p.update({'air': 1, 'spin': spin, 'hp': lerp(6, 28, tuck), 'sp': lerp(4, 22, tuck), 'hdp': lerp(-3, 18, tuck)})
    if t > .48:
        blend = smoother((t - .48) / .16)
        p['hp'] = lerp(p['hp'], FALL['hp'], blend); p['sp'] = lerp(p['sp'], FALL['sp'], blend); p['hdp'] = lerp(p['hdp'], FALL['hdp'], blend)
    p['hz'] = .0
    return apply_params(rig, p, centre_offset=Vector((0, 0, .07)))


# --- Dashes -------------------------------------------------------------------
DASH_PROFILE = [(0, 0), (.12, .4), (.20, 2.2), (.44, 2.2), (.58, 1.2), (.74, .3), (.90, 0)]   # units/s vs seconds


def dash_speed(t):
    return hermite(DASH_PROFILE, t)[0]


def dash_distance(t, step=1 / 600):
    d, x = 0.0, 0.0
    while x < t:
        d += dash_speed(x) * step
        x += step
    return d


def dash_ground_pose(rig, t):
    """Reference-shaped burst: crouched load, low long-stride drive with a strong
    lean and pumping fists, braking crouch with the hands forward, settle."""
    p = body_params()
    load = smoother(t / .13) * (1 - smoother((t - .13) / .10))
    drive = smoother((t - .12) / .14) * (1 - smoother((t - .42) / .16))
    brake = smoother((t - .44) / .18) * (1 - smoother((t - .72) / .18))
    settle = smoother((t - .74) / .16)
    lean = 28 * load + 50 * drive + 8 * brake
    p.update({'hz': -.13 * load - .15 * drive - .13 * brake - .008 * settle,
              'hp': lean * .55, 'sp': lean * .45, 'hdp': -lean * .62, 'hyaw': -6 * drive, 'syaw': 6 * drive})

    def d(a, b):
        return dash_distance(b) - dash_distance(a)
    x_left = x_right = z_left = z_right = p_left = p_right = 0.0
    if t < .15:                                        # load: rear foot slides back, heel lifts
        x_right = -.06 * load; p_right = 12 * load; x_left = .03 * load
    elif t < .26:                                      # first drive: right pushes, left reaches far forward
        s = (t - .15) / .11
        x_right = -.06 - d(.15, t); p_right = 12 + 32 * smoother(s)
        x_left = lerp(.03, .26, smoother(s)); z_left = .07 * math.sin(math.pi * s); p_left = lerp(24, -8, s)
    elif t < .48:                                      # second drive: left pushes, right recovers forward
        s = (t - .26) / .22
        x_left = .26 - d(.26, t); p_left = lerp(-8, 34, smoother(s))
        x_right = lerp(-.06 - d(.15, .26), .22, smoother(s)); z_right = .06 * math.sin(math.pi * s); p_right = lerp(44, -6, s)
    elif t < .74:                                      # brake: right foot plants ahead and slides, left comes under
        s = (t - .48) / .26
        x_right = .22 - d(.48, t); p_right = lerp(-6, 4, smoother(s))
        x_left = lerp(.26 - d(.26, .48), -.03, smoother(s * 1.5)); z_left = .035 * math.sin(math.pi * min(1, s * 1.5)); p_left = lerp(34, 0, min(1, s * 1.5))
    else:                                              # settle
        s = smoother((t - .74) / .16)
        x_right = (.22 - d(.48, .74)) * (1 - s) - d(.74, t) * (1 - s); x_left = -.03 * (1 - s); p_right = 4 * (1 - s)
    p.update({'lfx': x_left, 'rfx': x_right, 'lfz': z_left, 'rfz': z_right, 'lfp': p_left, 'rfp': p_right, 'lpole': .3, 'rpole': .3})
    # Arms: swing back on the load, pump opposite the legs through both drives, then reach forward for the brake.
    pump = math.sin(math.pi * clamp((t - .15) / .32))      # +1 at the first drive peak, back to 0 by the second
    alt = math.sin(math.pi * clamp((t - .30) / .24))        # second drive peak
    l_swing = -40 * load + (-60 * pump + 70 * alt) * drive + 52 * brake
    r_swing = -40 * load + (80 * pump - 45 * alt) * drive + 52 * brake
    p.update({'lswing': l_swing, 'rswing': r_swing, 'lelbow': 6 + 40 * load + 85 * drive + 72 * brake, 'relbow': 6 + 40 * load + 85 * drive + 72 * brake,
              'lspread': 8, 'rspread': 8, 'lwp': -10 * brake, 'rwp': -10 * brake})
    grip = max(load, drive, brake)
    p.update(both(curl=lerp(.12, .9, grip), thumb=lerp(.08, .3, grip), opp=.9 * grip))
    return apply_params(rig, p)


def dash_air_pose(rig, t):
    """Snap into a horizontal streamlined pose, hold, and tilt back to the fall pose."""
    D = .50
    p = body_params(); p.update(FALL)
    into = smoother(t / .13)
    out = smoother((t - .34) / .16)
    hold = into * (1 - out)
    wobble = math.sin(TAU * (t - .09) / .5)
    p['air'] = 1
    p['spin'] = 72 * hold + 4 * wobble * hold
    p.update({'hp': lerp(4, 8, hold), 'sp': lerp(3, 6, hold), 'hdp': lerp(6, -62, hold),
              'lfx': lerp(.03, -.02, hold), 'rfx': lerp(.03, -.02, hold), 'lfz': lerp(-.36, -.395, hold), 'rfz': lerp(-.36, -.395, hold),
              'lfp': lerp(14, 40, hold), 'rfp': lerp(14, 40, hold), 'lfy': .004 * hold, 'rfy': -.004 * hold})
    p.update(both(swing=lerp(25, 168, hold), spread=lerp(40, 10, hold), elbow=lerp(32, 6, hold), twist=lerp(0, 10, hold),
                  curl=lerp(.2, .06, hold), fspread=.2 * hold))
    return apply_params(rig, p, centre_offset=Vector((0, 0, .06)))


# --- Grounded actions --------------------------------------------------------
DODGE_KEYS = [
    (0.000, {}),
    (0.110, dict(hz=-.055, hp=10, hr=6, sp=6, sr=6, hdr=-4, hdyaw=10, **both(swing=40, spread=10, elbow=95, curl=.5, wp=-10))),
    (0.200, dict(hz=.030, hy=.040, hp=8, hr=14, sp=4, sr=8, hdr=-8, hdyaw=12, lfz=.055, rfz=.070, lfy=-.02, rfy=-.02, lfp=20, rfp=24, **both(swing=45, spread=14, elbow=100, curl=.55, wp=-10))),
    (0.320, dict(hz=-.110, hy=.050, hp=16, hr=6, sp=10, sr=2, hdr=-2, hdyaw=8, lfz=0, rfz=0, lfy=.075, rfy=-.055, lfx=.02, rfx=-.01, lfp=0, rfp=0, lfyaw=10, rfyaw=-6, **both(swing=38, spread=16, elbow=92, curl=.5, wp=-8, pole=.8))),
    (0.480, dict(hz=-.060, hy=.030, hp=8, hr=2, sp=4, sr=0, hdr=0, hdyaw=3, lfy=.05, rfy=-.04, lfx=.01, rfx=0, lfyaw=6, rfyaw=-3, **both(swing=18, spread=8, elbow=45, curl=.3, wp=-4, pole=.5))),
    (0.7333, dict(hz=-.008, hy=0, lfy=0, rfy=0, lfx=0, rfx=0, lfyaw=0, rfyaw=0, **both(swing=0, spread=6, elbow=6, curl=.12, wp=0, pole=0))),
]


def interact_pose(rig, t):
    """Half step, bend, reach the right hand to the floor ahead, lift and look, return."""
    D = 1.35
    p = body_params()
    step = smoother(t / .22) * (1 - smoother((t - 1.08) / .25))
    bend = smoother((t - .12) / .40) * (1 - smoother((t - .62) / .38))
    hold = smoother((t - 1.0) / .12) * (1 - smoother((t - 1.15) / .2))
    p.update({'lfx': .10 * step, 'lfy': .012 * step, 'rfy': -.012 * step, 'rfx': -.02 * step,
              'hz': -.006 - .170 * bend, 'hx': .05 * bend, 'hp': 55 * bend, 'sp': 30 * bend, 'hdp': -16 * bend + 10 * hold,
              'hyaw': -4 * bend, 'syaw': -6 * bend, 'hdyaw': -5 * bend - 8 * hold, 'lpole': .3, 'rpole': .3})
    p.update({'lswing': 22 * bend + 8 * hold, 'lspread': 4 + 4 * bend, 'lelbow': 6 + 30 * bend + 10 * hold, 'lcurl': .12 + .15 * bend})
    info = apply_params(rig, p)
    grasp = smoother((t - .50) / .12)
    release = 1 - smoother((t - 1.24) / .11)
    curl = .12 + .70 * grasp * release
    rig.hand('Right', curl=curl, thumb=.1 + .3 * grasp * release, opposition=.8 * grasp * release)
    # Right arm: reach down toward a spot ahead of the toes, then lift the hand to the chest.
    reach_target = Vector((neutral_feet(rig)['Right'].x + .27, -.03, rig.floor + .028))
    chest_target = rig.head('Spine2') + Vector((.14, -.06, .02))
    hang = rig.head('RightArm') + Vector((.03, -.06, -.235))
    lift = smoother((t - .66) / .34) * (1 - smoother((t - 1.04) / .31))
    early = smoother((t - .03) / .22) * (1 - smoother((t - 1.0) / .3))
    target = hang.lerp(reach_target, bend) + Vector((.07, -.06, .0)) * math.sin(math.pi * bend) + Vector((.05, -.07, .02)) * early * (1 - bend)
    target = target.lerp(chest_target, lift)
    rig.reach('Right', target, pole=Vector((-.4, -.6, -.5)).lerp(Vector((-.3, -.9, -.3)), lift))
    rig.rotate('RightHand', Quaternion(rig.direction('RightForeArm'), math.radians(-60 * lift)))
    return info


def wave_pose(rig, t):
    D = 2.4
    p = body_params()
    up = smoother(t / .45) * (1 - smoother((t - 1.95) / .45))
    waving = smoother((t - .40) / .15) * (1 - smoother((t - 1.85) / .15))
    osc = math.sin(TAU * 2.2 * (t - .45)) * waving
    p.update({'hy': -.006 * up, 'hr': -1.5 * up, 'sr': -3 * up, 'hdr': 5 * up, 'hdyaw': 4 * up, 'syaw': 4 * up,
              'rswing': 12 * up, 'rspread': 100 * up, 'relbow': 58 * up, 'rtwist': 10 * up, 'rft': -90 * up, 'rhinge': 90 * up, 'rwy': 22 * osc, 'rwp': -6 * up,
              'rcurl': lerp(.12, .02, up), 'rthumb': lerp(.08, .02, up), 'rfspread': .45 * up,
              'lswing': 2 * up, 'lspread': 3 + 2 * up, 'lelbow': 8 + 4 * up})
    p['rspread'] += 10 * osc
    return apply_params(rig, p)


# --- Sitting ------------------------------------------------------------------
SEAT_HEIGHT = .160    # documented seat/contact height above the floor (armature units)
SEATED = dict(hz=-.180, hx=-.055, hp=6, sp=-4, hdp=-2, lfx=.20, rfx=.20, lfy=.014, rfy=-.014, lpole=.2, rpole=.2,
              **both(swing=58, spread=6, elbow=62, wp=-20, curl=.22, thumb=.12))


def seated_hips(rig):
    """Pelvis height so the seat contact sits at SEAT_HEIGHT (hip joint ~0.08 above the seat)."""
    return rig.floor + SEAT_HEIGHT + .080 - rig.neutral_head['Hips'].z


SIT_DOWN_KEYS = [
    (0.000, {}),
    (0.220, dict(hz=-.030, hx=.01, hp=18, sp=8, hdp=-6, lfx=.09, rfx=.09, lfy=.012, rfy=-.012, **both(swing=20, spread=4, elbow=18, curl=.15))),
    (0.600, dict(hz=-.120, hx=-.03, hp=26, sp=8, hdp=-8, lfx=.17, rfx=.17, lfy=.014, rfy=-.014, lpole=.2, rpole=.2, **both(swing=40, spread=5, elbow=36, curl=.2))),
    (0.950, dict(SEATED, hp=12, sp=-2)),
    (1.200, SEATED),
]

STAND_UP_KEYS = [
    (0.000, SEATED),
    (0.350, dict(SEATED, hz=-.165, hx=.03, hp=44, sp=14, hdp=-14, **both(swing=50, spread=6, elbow=32, curl=.2))),
    (0.700, dict(hz=-.065, hx=.02, hp=16, sp=6, hdp=-4, lfx=.13, rfx=.13, lfy=.012, rfy=-.012, **both(swing=14, spread=4, elbow=16, curl=.15))),
    (0.950, dict(hz=-.014, hx=0, hp=3, sp=1, hdp=0, lfx=.03, rfx=.03, lfy=.004, rfy=-.004, **both(swing=3, spread=2, elbow=8, curl=.13))),
    (1.100, dict(hz=-.008, lfx=0, rfx=0, lfy=0, rfy=0, **both(swing=0, spread=6, elbow=6, curl=.12))),
]


def sit_idle_pose(rig, t):
    T = 3.0
    u = t / T
    breath = math.sin(TAU * u - math.pi / 2)
    p = body_params(); p.update(SEATED)
    p.update({'hz': SEATED['hz'] - .001 * breath, 'sp': -4 - 1.6 * breath, 'hdp': -2 - 1.2 * breath, 'hdyaw': 4 * math.sin(TAU * u) * (.5 - .5 * math.cos(TAU * u))})
    p.update(both(swing=58 + 1.2 * breath, elbow=62 + 1.5 * breath, wp=-20, curl=.22 + .04 * breath, thumb=.12))
    return apply_params(rig, p)


# --- Climb -------------------------------------------------------------------
LADDER = {'plane_x': .19, 'rung_spacing': .15, 'hand_y': .085, 'foot_y': .05, 'foot_x': .13, 'speed': .25, 'period': 1.2}


def climb_pose(rig, t):
    """Alternating reach: the ladder moves down at the climb speed (in place)."""
    L = LADDER
    T = L['period']
    phase = (t / T) % 1
    v = L['speed']
    feet0 = neutral_feet(rig)
    hips_target = rig.neutral_head['Hips'] + Vector((-.045, 0, -.085 + .006 * math.cos(2 * TAU * phase)))
    rig.hips(hips_target - rig.neutral_head['Hips'], pitch=-6, yaw=3 * math.sin(TAU * phase))
    rig.spine(pitch=-4, yaw=-3 * math.sin(TAU * phase), head_pitch=-26)
    # Feet: each stands on a rung for 60% of the cycle, then lifts two rungs up.
    for side, offset, sign in [('Left', 0.0, 1), ('Right', 0.5, -1)]:
        u = (phase + offset) % 1
        stance = .60
        top = .17                                   # rung height (above floor) where the foot lands
        if u < stance:
            z = top - v * u * T; x = L['foot_x']; on = True
        else:
            s = (u - stance) / (1 - stance)
            z = lerp(top - v * stance * T, top, smoother(s)); x = L['foot_x'] - .05 * math.sin(math.pi * s); on = False
        pitch = -8
        ankle = ankle_for(rig, side, Vector((x, sign * L['foot_y'], z)), pitch)
        rig.leg(side, ankle, pitch, 0, 0, pole=Vector((1, sign * .2, 0)))
    # Hands: grip for 60% then reach up to the next-but-one rung.
    for side, offset, sign in [('Left', 0.5, 1), ('Right', 0.0, -1)]:
        u = (phase + offset) % 1
        stance = .60
        top = rig.neutral_head['Hips'].z + .32
        if u < stance:
            z = top - v * u * T; x = L['plane_x'] - .02
        else:
            s = (u - stance) / (1 - stance)
            z = lerp(top - v * stance * T, top, smoother(s)); x = L['plane_x'] - .02 - .04 * math.sin(math.pi * s)
        rig.reach(side, Vector((x, sign * L['hand_y'], z)), pole=Vector((-.6, sign * .7, -.3)))
        rig.rotate(side + 'Hand', Quaternion(rig.direction(side + 'ForeArm'), math.radians(sign * 40)))
        grip = 1 if u < stance else 1 - math.sin(math.pi * (u - stance) / (1 - stance)) * .5
        rig.hand(side, curl=.75 * grip + .1, thumb=.5 * grip, opposition=.7 * grip)
    return {'left_planted': False, 'right_planted': False, 'fixture': 'ladder'}


# --- Glide --------------------------------------------------------------------
def glide_pose(rig, t):
    T = 2.4
    u = t / T
    w1, w2 = math.sin(TAU * u), math.sin(TAU * u + 1.3)
    p = body_params(); p.update(FALL)
    p.update({'air': 1, 'spin': 52 + 3 * w1, 'hp': 6 + 2 * w2, 'sp': 4, 'sr': 2.5 * w2, 'hr': 2 * w1, 'hdp': -46 - 2 * w1, 'hdyaw': 3 * w2,
              'lfx': -.03 + .01 * w2, 'rfx': -.03 - .01 * w2, 'lfz': -.385, 'rfz': -.385, 'lfp': 34, 'rfp': 34, 'lfy': .0, 'rfy': .0,
              'lspread': 82 + 4 * w1, 'rspread': 82 - 4 * w1, 'lswing': 12 + 3 * w2, 'rswing': 12 - 3 * w2, 'ltwist': 10, 'rtwist': 10,
              'lelbow': 12, 'relbow': 12, 'lcurl': .04, 'rcurl': .04, 'lfspread': .3, 'rfspread': .3})
    return apply_params(rig, p, centre_offset=Vector((0, 0, .06)))


# --- Turns --------------------------------------------------------------------
def turn_pose(direction):
    sign = 1 if direction == 'Left' else -1

    def pose(rig, t):
        D = .70
        feet0 = neutral_feet(rig)
        body_yaw = 90 * sign * smoother((t - .04) / .58)
        head_yaw = 90 * sign * smoother(t / .34)
        # Inside foot steps first, outside foot follows; each foot lands rotated by its own yaw.
        first, second = (direction, 'Right' if direction == 'Left' else 'Left')
        steps = {first: (.05, .32), second: (.36, .62)}
        ankles, pitches, yaws, planted = {}, {}, {}, {}
        for side in SIDES:
            start, end = steps[side]
            s = smoother((t - start) / (end - start))
            yaw = 90 * sign * s
            base = feet0[side]
            rotated = q_axis(Z, yaw) @ Vector((base.x, base.y, 0))
            lift = .028 * math.sin(math.pi * clamp((t - start) / (end - start)))
            pitch = 8 * math.sin(math.pi * clamp((t - start) / (end - start)))
            ankles[side] = ankle_for(rig, side, Vector((rotated.x, rotated.y, lift)), pitch, yaw)
            pitches[side], yaws[side], planted[side] = pitch, yaw, lift < 1e-4
        hips0 = rig.neutral_head['Hips']
        centre = q_axis(Z, body_yaw) @ Vector((hips0.x, hips0.y, 0))
        target = Vector((centre.x, centre.y, hips0.z - .014 - .012 * math.sin(math.pi * clamp(t / .7))))
        position = settle_hips(rig, target, {sd: a for sd, a in ankles.items() if planted[sd]})
        rig.hips(position - hips0, pitch=2, yaw=body_yaw, roll=-3 * sign * math.sin(math.pi * clamp(t / .7)))
        rig.spine(yaw=(head_yaw - body_yaw) * .35, head_yaw=head_yaw, head_pitch=0)
        for side in SIDES:
            rig.leg(side, ankles[side], pitches[side], yaws[side], pole=q_axis(Z, yaws[side]) @ Vector((1, 0, 0)))
        swing = 10 * math.sin(math.pi * clamp(t / .7))
        rig.arm('Left', swing=sign * swing, spread=8, elbow=10, yaw=body_yaw)
        rig.arm('Right', swing=-sign * swing, spread=8, elbow=10, yaw=body_yaw)
        for side in SIDES:
            rig.hand(side, curl=.12, thumb=.08)
        return {'left_planted': planted['Left'], 'right_planted': planted['Right'], 'body_yaw': body_yaw}
    return pose


# --- Registry -----------------------------------------------------------------
CLIPS = {
    'Idle': Clip('Idle', 4.0, idle_pose, loop=True, kind='loop', reference='anim-ref-idle-r01',
                 markers=[{'time': 0, 'label': 'loop start'}, {'time': 2.0, 'label': 'weight on right'}],
                 notes='Quiet breathing (two per loop) with one slow weight shift and look; feet never leave their planted positions.'),
    'Walk': Clip('Walk', WALK['period'], walk_pose, loop=True, kind='loop', travel=WALK['speed'], reference='anim-ref-walk-r01',
                 markers=[{'time': 0, 'label': 'left heel strike'}, {'time': WALK['period'] / 2, 'label': 'right heel strike'}],
                 notes='Relaxed heel-to-toe walk; in place, matched travel speed recorded for the moving-floor review.'),
    'CrouchIdle': Clip('CrouchIdle', 3.0, crouch_idle_pose, loop=True, kind='loop', reference='anim-ref-crouch-r01',
                       notes='Deep stable crouch, feet apart and turned out, hands ready in front; breathing and small sway.', entry='CrouchWalk/Idle', exit='CrouchWalk/Idle'),
    'CrouchWalk': Clip('CrouchWalk', CROUCH_WALK['period'], crouch_walk_pose, loop=True, kind='loop', travel=CROUCH_WALK['speed'], reference='anim-ref-crouch-r01',
                       markers=[{'time': 0, 'label': 'left heel strike'}, {'time': CROUCH_WALK['period'] / 2, 'label': 'right heel strike'}],
                       notes='Low creeping gait at crouch height with short steps; arms held ready.', entry='CrouchIdle', exit='CrouchIdle'),
    'JumpStart': Clip('JumpStart', .1333, timeline_clip(JUMP_START_KEYS), kind='one-shot', reference='anim-ref-jump-r01',
                      markers=[{'time': .06, 'label': 'deepest load'}, {'time': .1333, 'label': 'launch'}],
                      notes='Shallow loading then extension onto the toes; no foot repositioning so moving starts blend cleanly.', exit='JumpRise'),
    'JumpRise': Clip('JumpRise', .55, timeline_clip(JUMP_RISE_KEYS), kind='air', reference='anim-ref-jump-r01',
                     markers=[{'time': 0, 'label': 'launch pose'}, {'time': .55, 'label': 'apex pose'}],
                     notes='Ascent: full extension, arms up, then knees drift forward into the apex pose shared with DoubleJump/Fall.', entry='JumpStart', exit='Fall/DoubleJump/DashAir'),
    'DoubleJump': Clip('DoubleJump', .75, double_jump_pose, kind='one-shot', reference='anim-ref-flip-r01',
                       markers=[{'time': .08, 'label': 'rotation starts'}, {'time': .60, 'label': 'rotation complete (360°)'}, {'time': .633, 'label': 'upright'}],
                       notes='Compact tuck and one forward somersault about the body centre (pelvis + 0.07 up); opens upright before the end into the fall pose.', entry='JumpRise/Fall', exit='Fall'),
    'Fall': Clip('Fall', 1.1, fall_pose, loop=True, kind='loop', reference='anim-ref-jump-r01',
                 notes='Airborne descent hold with gentle arm balance; safe entry from apex, ledge walk-off, air dash or double jump.', entry='JumpRise/DoubleJump/DashAir', exit='Land/HardLand'),
    'Land': Clip('Land', .4333, timeline_clip(LAND_KEYS), kind='one-shot', reference='anim-ref-jump-r01',
                 markers=[{'time': 0, 'label': 'contact'}, {'time': .12, 'label': 'deepest absorption'}],
                 notes='Soft landing: contact on frame 1, absorb, recover to idle; can be cut early for moving exits.', entry='Fall', exit='Idle/Walk/Sprint'),
    'HardLand': Clip('HardLand', .70, timeline_clip(HARD_LAND_KEYS), kind='one-shot', reference='anim-ref-jump-r01',
                     markers=[{'time': 0, 'label': 'contact'}, {'time': .13, 'label': 'deepest crouch'}, {'time': .30, 'label': 'hold ends'}],
                     notes='Heavy landing: deep squat with the torso folded and the right hand dropping toward the floor, slower recovery.', entry='Fall', exit='Idle'),
    'DashGround': Clip('DashGround', .90, dash_ground_pose, kind='one-shot', reference='anim-ref-dash-r01', travel='profile',
                       markers=[{'time': .13, 'label': 'deepest load'}, {'time': .15, 'label': 'drive starts'}, {'time': .48, 'label': 'brake plant'}, {'time': .74, 'label': 'settling'}, {'time': .90, 'label': 'idle'}],
                       notes='Reference-shaped burst: crouched load, two low driving strides with a 50° lean and pumping fists, braking crouch with the hands forward, settle. Proposed displacement profile in the manifest.', exit='Idle/Walk/Sprint/Fall'),
    'DashAir': Clip('DashAir', .50, dash_air_pose, kind='air', reference='anim-ref-airdash-r01', travel='profile',
                    markers=[{'time': .09, 'label': 'streamlined'}, {'time': .34, 'label': 'release'}, {'time': .50, 'label': 'fall pose'}],
                    notes='Airborne burst: tilts about the body centre into a horizontal streamlined pose with arms swept back, holds, then returns to the fall pose.', entry='JumpRise/Fall/DoubleJump', exit='Fall/Land'),
    'Dodge': Clip('Dodge', .7333, timeline_clip(DODGE_KEYS), kind='one-shot', reference='anim-ref-dodge-r01',
                  markers=[{'time': .09, 'label': 'load'}, {'time': .20, 'label': 'airborne hop'}, {'time': .32, 'label': 'low landing'}],
                  notes='Grounded evade: guard arms, quick hop to the left, low wide landing and recovery; distinct from the forward dash.'),
    'Interact': Clip('Interact', 1.35, interact_pose, kind='one-shot', reference='anim-ref-interact-r01',
                     markers=[{'time': .55, 'label': 'hand at floor'}, {'time': 1.0, 'label': 'hand at chest'}],
                     notes='Half step, bend and reach the right hand to a floor spot ahead, grasp, lift to the chest and look, then return.'),
    'Wave': Clip('Wave', 2.4, wave_pose, kind='one-shot', reference='anim-ref-wave-r01',
                 markers=[{'time': .45, 'label': 'arm up'}, {'time': 1.95, 'label': 'lowering'}],
                 notes='Right arm raised beside the head, three side-to-side waves with spread fingers, then lowered.'),
    'SitDown': Clip('SitDown', 1.2, timeline_clip(SIT_DOWN_KEYS), kind='transition', reference='anim-ref-sit-r01',
                    markers=[{'time': .95, 'label': 'seat contact'}],
                    notes=f'Controlled descent to a seat {SEAT_HEIGHT} units above the floor (about knee height), feet moving forward.', exit='SitIdle'),
    'SitIdle': Clip('SitIdle', 3.0, sit_idle_pose, loop=True, kind='loop', reference='anim-ref-sit-r01',
                    notes='Seated breathing and a small look; hands on the thighs.', entry='SitDown', exit='StandUp'),
    'StandUp': Clip('StandUp', 1.1, timeline_clip(STAND_UP_KEYS), kind='transition', reference='anim-ref-sit-r01',
                    markers=[{'time': .35, 'label': 'weight over feet'}, {'time': .70, 'label': 'seat released'}],
                    notes='Lean over the feet, push up through the legs, settle to idle.', entry='SitIdle'),
    'Climb': Clip('Climb', LADDER['period'], climb_pose, loop=True, kind='loop', reference='anim-ref-climb-r01', travel=LADDER['speed'],
                  notes=f"Ladder climb, in place: vertical ladder plane {LADDER['plane_x']} ahead, rungs {LADDER['rung_spacing']} apart, climb speed {LADDER['speed']} units/s.",
                  entry='ladder attach', exit='ladder detach'),
    'Glide': Clip('Glide', 2.4, glide_pose, loop=True, kind='loop', reference='anim-ref-glide-r01',
                  notes='Airborne balance hold: body inclined about 52° with arms spread wide; slow balancing oscillation. No glider asset.', entry='Fall', exit='Fall'),
    'TurnLeft': Clip('TurnLeft', .70, turn_pose('Left'), kind='one-shot', reference='anim-ref-turn-r01', yaw=90,
                     markers=[{'time': .05, 'label': 'left foot steps'}, {'time': .36, 'label': 'right foot steps'}, {'time': .62, 'label': 'both planted'}],
                     notes='90° left turn in place: the clip owns the visual yaw; apply +90° controller yaw when it ends and the pose equals idle rotated about the origin.'),
    'TurnRight': Clip('TurnRight', .70, turn_pose('Right'), kind='one-shot', reference='anim-ref-turn-r01', yaw=-90,
                      markers=[{'time': .05, 'label': 'right foot steps'}, {'time': .36, 'label': 'left foot steps'}, {'time': .62, 'label': 'both planted'}],
                      notes='Mirror of TurnLeft, inspected independently.'),
}

ROLES = [
    ('Idle', 'Idle'), ('Walk', 'Walk'), ('Run', 'shared:Sprint · dressed'), ('Sprint', 'existing:Sprint · dressed'),
    ('CrouchIdle', 'CrouchIdle'), ('CrouchWalk', 'CrouchWalk'), ('JumpStart', 'JumpStart'), ('JumpRise', 'JumpRise'),
    ('DoubleJump', 'DoubleJump'), ('Fall', 'Fall'), ('Land', 'Land'), ('HardLand', 'HardLand'), ('Dodge', 'Dodge'),
    ('Interact', 'Interact'), ('Wave', 'Wave'), ('SitDown', 'SitDown'), ('SitIdle', 'SitIdle'), ('StandUp', 'StandUp'),
    ('Climb', 'Climb'), ('Glide', 'Glide'), ('TurnLeft', 'TurnLeft'), ('TurnRight', 'TurnRight'),
    ('DashGround', 'DashGround'), ('DashAir', 'DashAir'),
]
