"""Build the sword combat clip set on the current game body (game-r13 = game-r12 + combat clips).

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_sword_combat_build.py

Sources: `game-r12/WarmOriginal-Game-r12.blend` (complete library, current body) and the accepted
Mixamo combo `sword-r01/stage1-bokken/mixamo-r02/WarmOriginal-Mixamo-Slash.blend` (action
`Mixamo · Great Sword Combo Slash · head clearance`, 212 frames at 60 fps, plus the bone-parented
bokken with the extended lower grip). No video landmarks and no rejected `rebuild-*` data are used.

Every combat clip is cut from captured phases of that combo. The only authored motion is: short
recoveries back to the guard pose (quaternion blends with the support hand re-solved per frame),
breathing on the two static holds, the draw/sheath blends from the library idle, and the parry
recoil. Hip travel and turning of captured phases move to the `Root` bone (Unreal root motion);
authored links are in place. The finger wrap uses the rig's own curl drivers, fitted to the
accepted hold-r14 wrap angles, so the library's driver-based fingers keep working unchanged.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import hashlib, json, math, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0, str(Path(__file__).parent))
from warm_mixamo_test import PREFIX as P, fit_support_hand
from warm_outfit_correctives import set_clip

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
PARENT = ASSET / 'game-r12'
COMBO = ASSET / 'sword-r01/stage1-bokken/mixamo-r02/WarmOriginal-Mixamo-Slash.blend'
COMBO_ACTION = 'Mixamo · Great Sword Combo Slash · head clearance'
REV = 'game-r13'
OUT = ASSET / REV
FPS = 60
GUARD_FRAME = 5                                  # combo frame whose stance defines the guard
HANDS = ['Left', 'Right']
HAND_PROPS = ['thumb_curl', 'index_curl', 'middle_curl', 'ring_curl', 'pinky_curl', 'thumb_opposition', 'finger_spread']
RELAX = {'thumb_curl': .06, 'index_curl': .06, 'middle_curl': .06, 'ring_curl': .06, 'pinky_curl': .06, 'thumb_opposition': 0., 'finger_spread': 0.}
OPEN = {'thumb_curl': .02, 'index_curl': .02, 'middle_curl': .02, 'ring_curl': .02, 'pinky_curl': .02, 'thumb_opposition': 0., 'finger_spread': .35}


def smooth(t):
    t = max(0., min(1., t)); return t * t * (3 - 2 * t)


def smoother(t):
    t = max(0., min(1., t)); return t * t * t * (10 + t * (-15 + 6 * t))


def gaussian(values, sigma):
    values = np.asarray(values, dtype=float)
    if sigma <= 0: return values
    r = int(math.ceil(3 * sigma)); k = np.exp(-.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    padded = np.concatenate([np.repeat(values[:1], r, 0), values, np.repeat(values[-1:], r, 0)], 0)
    if values.ndim == 1: return np.convolve(padded, k, 'valid')
    return np.stack([np.convolve(padded[:, i], k, 'valid') for i in range(values.shape[1])], 1)


def unwrap(deg):
    out = [deg[0]]
    for d in deg[1:]:
        while d - out[-1] > 180: d -= 360
        while d - out[-1] < -180: d += 360
        out.append(d)
    return out


class Builder:
    def __init__(self):
        record = json.loads((PARENT / 'source-manifest.json').read_text())
        source = ROOT / record['native']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['native_sha256'], 'game-r12 changed'
        self.record = record; self.source = source
        bpy.ops.wm.open_mainfile(filepath=str(source))
        self.scene = bpy.context.scene; self.scene.render.fps = FPS
        self.arm = next(o for o in self.scene.objects if o.type == 'ARMATURE')
        self.library = {a.name: self.signature(a) for a in bpy.data.actions}
        self.library_slot = next(sl for sl in bpy.data.actions['Idle · library'].slots if sl.identifier.startswith('OB')).name_display
        self.load_combo()
        self.R0 = self.arm.data.bones['Root'].matrix_local.copy(); self.R0i = self.R0.inverted()
        self.Hrest = self.arm.data.bones[P + 'Hips'].matrix_local.copy()
        self.O = self.R0.translation.copy(); self.O.z = 0
        self.body_bones = [pb.name for pb in self.arm.pose.bones if pb.name not in ('Root', P + 'Hips') and not self.is_finger(pb.name)]
        self.head = bpy.data.objects['Body · head']
        self.fit_fingers()
        self.sample_combo()

    @staticmethod
    def is_finger(name):
        return name[-1].isdigit() and 'Hand' in name

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

    def load_combo(self):
        """Append the accepted action and the bone-parented sword; verify identical rest skeletons."""
        with bpy.data.libraries.load(str(COMBO)) as (src, dst):
            dst.actions = [COMBO_ACTION]; dst.objects = ['Bokken-stage1-r01']
        self.combo = bpy.data.actions[COMBO_ACTION]
        sword = bpy.data.objects['Bokken-stage1-r01']; self.scene.collection.objects.link(sword)
        source_basis = sword.matrix_basis.copy()
        sword.parent = self.arm; sword.parent_type = 'BONE'; sword.parent_bone = P + 'RightHand'
        sword.matrix_parent_inverse = Matrix.Identity(4); sword.matrix_basis = source_basis
        sword.hide_render = False; sword.hide_viewport = False; sword.hide_set(False)
        sword['combat_socket'] = 'bone-parented to mixamorig:RightHand; matrix_basis compensates the tail offset (see hold_socket)'
        self.sword = sword
        # The combo blend was saved from the same skeleton; require identical bind matrices before reuse.
        with bpy.data.libraries.load(str(COMBO)) as (src, dst):
            dst.armatures = [a for a in src.armatures]
        other = next(a for a in bpy.data.armatures if a.users == 0 and a != self.arm.data)
        assert {b.name for b in other.bones} == {b.name for b in self.arm.data.bones}
        err = max(abs(v - w) for b in other.bones for v, w in zip([x for r in b.matrix_local for x in r], [x for r in self.arm.data.bones[b.name].matrix_local for x in r]))
        assert err < 1e-5, err
        bpy.data.armatures.remove(other)
        self.rest_error = err

    # ---------------------------------------------------------------- fingers
    def fit_fingers(self):
        """Fit the curl/opposition/spread props of each hand to the accepted hold's finger wrap."""
        quats = {}
        for layer in self.combo.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        if 'rotation_quaternion' in fc.data_path and self.is_finger(fc.data_path.split('"')[1]):
                            quats.setdefault(fc.data_path.split('"')[1], [0, 0, 0, 0])[fc.array_index] = fc.evaluate(1)
        drivers = {}
        for d in self.arm.animation_data.drivers:
            bone = d.data_path.split('"')[1]
            if not self.is_finger(bone) or 'rotation_euler' not in d.data_path: continue
            expr = d.driver.expression; var = d.driver.variables[0]; prop = var.targets[0].data_path.split('"')[3]
            # expressions are  max(0,min(1,v))*k   or   s*v*k  : recover the linear factor numerically
            def f(v, expr=expr, name=var.name):
                return eval(expr, {'max': max, 'min': min}, {name: v})
            drivers[(bone, d.array_index)] = (prop, f(1.) - f(0.), f(0.))
        self.grip_props = {}
        for side in HANDS:
            rows, targets, props = [], [], HAND_PROPS
            for (bone, axis), (prop, k, c) in drivers.items():
                if not bone.startswith(P + side): continue
                q = quats.get(bone)
                if q is None: continue
                euler = Quaternion(q).to_euler('XYZ')
                rows.append([k if p == prop else 0. for p in props]); targets.append(euler[axis] - c)
            A = np.array(rows); b = np.array(targets)
            x, *_ = np.linalg.lstsq(A, b, rcond=None)
            fitted = {p: float(min(1., max(0., v))) if 'curl' in p or 'opposition' in p else float(max(-.5, min(.5, v))) for p, v in zip(props, x)}
            residual = float(np.degrees(np.sqrt(np.mean((A @ np.array([fitted[p] for p in props]) - b) ** 2))))
            self.grip_props[side] = fitted; self.grip_props[side + '_residual_degrees'] = residual
        self.finger_bones = [b for b in quats]

    def set_hand(self, side, values):
        hand = self.arm.pose.bones[P + side + 'Hand']
        for k, v in values.items(): hand[k] = v

    def blend_props(self, a, b, u):
        return {k: a[k] + (b[k] - a[k]) * u for k in HAND_PROPS}

    # ---------------------------------------------------------------- pose descriptors
    def read_pose(self):
        bases = {n: self.arm.pose.bones[n].matrix_basis.copy() for n in self.body_bones}
        return {'bases': bases, 'H': self.arm.pose.bones[P + 'Hips'].matrix.copy()}

    def yaw_of(self, H):
        f = H.to_3x3() @ Vector((1, 0, 0)); return math.degrees(math.atan2(f.y, f.x))

    def rebase(self, pose, yaw, xy):
        """Express the hips relative to a root at translation xy turned by yaw about the root origin."""
        M = Matrix.Translation((xy[0], xy[1], 0)) @ Matrix.Translation(self.O) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Translation(-self.O)
        return {'bases': {n: m.copy() for n, m in pose['bases'].items()}, 'Hrel': M.inverted() @ pose['H']}

    def sample_combo(self):
        """Sample every combo frame; strip smoothed facing/travel into per-frame root values."""
        set_clip(self.arm, self.combo)
        for pb in self.arm.pose.bones: pb.matrix_basis = Matrix.Identity(4)
        self.frames = {}
        raw_yaw, raw_xy = [], []
        for f in range(1, 213):
            self.scene.frame_set(f); pose = self.read_pose(); self.frames[f] = pose
            raw_yaw.append(self.yaw_of(pose['H'])); raw_xy.append([pose['H'].translation.x - self.O.x, pose['H'].translation.y - self.O.y])
        raw_yaw = unwrap(raw_yaw); self.guard_yaw = raw_yaw[GUARD_FRAME - 1]
        self.root_yaw = gaussian(np.array(raw_yaw) - self.guard_yaw, 2.5)
        self.root_xy = gaussian(np.array(raw_xy), 2.5)
        self.raw_yaw = raw_yaw
        for f in range(1, 213):
            self.frames[f] = self.rebase(self.frames[f], float(self.root_yaw[f - 1]), self.root_xy[f - 1])
        self.guard = self.frames[GUARD_FRAME]
        self.apply(self.guard, support=0.); self.floor_ref = self.foot_low()
        # The library idle pose (frame 1) is the unarmed reference for draw/sheath.
        idle = bpy.data.actions['Idle · library']; set_clip(self.arm, idle); self.scene.frame_set(1)
        # Keep the idle's own facing (root identity) so the draw starts exactly where the unarmed idle stands.
        pose = self.read_pose(); self.idle = self.rebase(pose, 0., [pose['H'].translation.x - self.O.x, pose['H'].translation.y - self.O.y])
        self.idle_hand = {side: {p: float(self.arm.pose.bones[P + side + 'Hand'][p]) for p in HAND_PROPS} for side in HANDS}
        self.idle_yaw = self.yaw_of(pose['H']) - self.guard_yaw
        self.arm.animation_data.action = None

    def at(self, f):
        """Combo pose at a (possibly fractional) frame, rebased."""
        lo = int(math.floor(f)); hi = min(212, lo + 1); u = f - lo
        if u < 1e-6 or lo == hi: return self.frames[lo]
        return self.blend(self.frames[lo], self.frames[hi], u)

    def blend(self, a, b, u):
        bases = {}
        for n in self.body_bones:
            qa = a['bases'][n].to_quaternion(); qb = b['bases'][n].to_quaternion()
            if qa.dot(qb) < 0: qb = -qb
            bases[n] = qa.slerp(qb, u).to_matrix().to_4x4()
        qa = a['Hrel'].to_quaternion(); qb = b['Hrel'].to_quaternion()
        if qa.dot(qb) < 0: qb = -qb
        H = qa.slerp(qb, u).to_matrix().to_4x4(); H.translation = a['Hrel'].translation.lerp(b['Hrel'].translation, u)
        return {'bases': bases, 'Hrel': H}

    def breathe(self, pose, t, period, depth=1.0):
        """Subtle chest/pelvis breathing on a static pose; loops exactly over `period` seconds."""
        w = 2 * math.pi * t / period; s = math.sin(w); c = .5 * (1 - math.cos(w))
        out = {'bases': {n: m.copy() for n, m in pose['bases'].items()}, 'Hrel': pose['Hrel'].copy()}
        for n, deg, axis in [(P + 'Spine1', 1.1, 'X'), (P + 'Spine2', .9, 'X'), (P + 'Neck', -.7, 'X'), (P + 'LeftShoulder', .6, 'Z'), (P + 'RightShoulder', -.6, 'Z'), (P + 'RightArm', .7, 'Z'), (P + 'LeftArm', -.5, 'Z')]:
            out['bases'][n] = out['bases'][n] @ Matrix.Rotation(math.radians(deg * s * depth), 4, axis)
        out['Hrel'] = Matrix.Translation((0, 0, -.003 * c * depth)) @ out['Hrel']
        return out

    # ---------------------------------------------------------------- apply / key
    def foot_low(self):
        pts = []
        for side in HANDS:
            f = self.arm.pose.bones[P + side + 'Foot']; t = self.arm.pose.bones[P + side + 'ToeBase']
            pts += [f.head.z, f.tail.z, t.head.z, t.tail.z]
        return min(pts)

    def apply(self, pose, yaw=0., xy=(0., 0.), support=1., hands=None, floor=False):
        arm = self.arm
        M = Matrix.Translation((xy[0], xy[1], 0)) @ Matrix.Translation(self.O) @ Matrix.Rotation(math.radians(yaw), 4, 'Z') @ Matrix.Translation(-self.O)
        root = arm.pose.bones['Root']; hips = arm.pose.bones[P + 'Hips']
        root.matrix_basis = self.R0i @ M @ self.R0
        root_matrix = self.R0 @ root.matrix_basis
        hips.matrix_basis = (root_matrix @ self.R0i @ self.Hrest).inverted() @ (M @ pose['Hrel'])
        for n, m in pose['bases'].items(): arm.pose.bones[n].matrix_basis = m
        for side in HANDS: self.set_hand(side, (hands or {}).get(side, self.grip_props[side]))
        bpy.context.view_layer.update()
        if floor:
            # Authored blends may push a planted foot under the guard's contact height: lift the pelvis, never sink it.
            dip = self.floor_ref - self.foot_low()
            if dip > 5e-4:
                hips.matrix_basis = (root_matrix @ self.R0i @ self.Hrest).inverted() @ (Matrix.Translation((0, 0, dip)) @ M @ pose['Hrel'])
                bpy.context.view_layer.update()
        error = 0.
        if support > 0:
            before = {n: arm.pose.bones[P + 'Left' + part].rotation_quaternion.copy() for n, part in [(0, 'Arm'), (1, 'ForeArm'), (2, 'Hand')]}
            error = fit_support_hand(arm, self.sword)
            if support < 1:
                for i, part in enumerate(['Arm', 'ForeArm', 'Hand']):
                    pb = arm.pose.bones[P + 'Left' + part]; q = pb.rotation_quaternion
                    if q.dot(before[i]) < 0: q = -q
                    pb.rotation_quaternion = before[i].slerp(q, support)
                bpy.context.view_layer.update()
        return error

    def key(self, frame, last):
        for pb in self.arm.pose.bones:
            if self.is_finger(pb.name): continue
            q = pb.rotation_quaternion.copy()
            if pb.name in last and q.dot(last[pb.name]) < 0: q.negate(); pb.rotation_quaternion = q
            last[pb.name] = q.copy()
            pb.keyframe_insert('rotation_quaternion', frame=frame, group=pb.name)
            if pb.name in ('Root', P + 'Hips'): pb.keyframe_insert('location', frame=frame, group=pb.name)
        for side in HANDS:
            hand = self.arm.pose.bones[P + side + 'Hand']
            for prop in HAND_PROPS: hand.keyframe_insert(f'["{prop}"]', frame=frame, group=hand.name + ' · grip')

    def new_action(self, name, loop):
        action = bpy.data.actions.new(name); action.use_fake_user = True
        # Share the library's slot name so every tool that assigns clips by name keeps auto-selecting a slot.
        slot = action.slots.new(id_type='OBJECT', name=self.library_slot)
        self.arm.animation_data.action = action; self.arm.animation_data.action_slot = slot
        return action

    def finish(self, action, loop):
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        for k in fc.keyframe_points: k.interpolation = 'LINEAR'
                        if loop: fc.modifiers.new('CYCLES')

    # ---------------------------------------------------------------- clip assembly
    def captured(self, f0, f1, step=1.0):
        """Captured frames f0..f1 (inclusive, fractional step) with root motion relative to f0."""
        frames = []; y0 = float(np.interp(f0, range(1, 213), self.root_yaw)); xy0 = [float(np.interp(f0, range(1, 213), self.root_xy[:, i])) for i in range(2)]
        c, s = math.cos(math.radians(-y0)), math.sin(math.radians(-y0))
        f = f0
        while f <= f1 + 1e-6:
            yaw = float(np.interp(f, range(1, 213), self.root_yaw)) - y0
            dx, dy = [float(np.interp(f, range(1, 213), self.root_xy[:, i])) - xy0[i] for i in range(2)]
            frames.append({'pose': self.at(f), 'yaw': yaw, 'xy': (c * dx - s * dy, s * dx + c * dy), 'source': f})
            f += step
        return frames

    def link(self, a, b, n, ease=smoother, yaw=None, xy=None, lead=None):
        """n authored frames blending pose a -> pose b (exclusive of a, inclusive of b).
        `lead` = (bone prefix list, factor): those bones reach the target earlier so the weapon arm stays within the support hand's reach."""
        out = []
        for i in range(n):
            u = (i + 1) / n; pose = self.blend(a, b, ease(u))
            if lead:
                early = self.blend(a, b, ease(min(1., u * lead[1])))
                for bone in pose['bases']:
                    if any(bone.startswith(P + k) for k in lead[0]): pose['bases'][bone] = early['bases'][bone]
            out.append({'pose': pose, 'yaw': yaw or 0., 'xy': xy or (0., 0.), 'source': None})
        return out

    def tail(self, frames, n):
        """Recovery from the last frame to the guard, root frozen where the capture ended."""
        last = frames[-1]
        return self.link(last['pose'], self.guard, n, yaw=last['yaw'], xy=last['xy'])

    def write(self, name, frames, loop=False, support=None, hands=None, meta=None):
        action = self.new_action(name, loop); last = {}; errors = []
        for i, fr in enumerate(frames):
            self.scene.frame_set(i + 1)
            w = support(i, len(frames)) if callable(support) else (1. if support is None else support)
            h = hands(i, len(frames)) if callable(hands) else hands
            errors.append(self.apply(fr['pose'], fr['yaw'], fr['xy'], support=w, hands=h, floor=fr['source'] is None))
            self.key(i + 1, last)
        self.finish(action, loop)
        info = {'clip': name, 'frames': len(frames), 'duration_seconds': (len(frames) - 1) / FPS, 'loop': loop,
                'support_hand_error_max_m': max(errors), 'support_hand_frames_over_8mm': [i + 1 for i, e in enumerate(errors) if e > .008], 'end_yaw_degrees': frames[-1]['yaw'], 'end_travel': list(frames[-1]['xy']),
                'root_motion': any(abs(f['yaw']) > 1e-6 or abs(f['xy'][0]) + abs(f['xy'][1]) > 1e-6 for f in frames),
                'source_frames': [f['source'] for f in frames if f['source'] is not None][:1] + [f['source'] for f in frames if f['source'] is not None][-1:]}
        info.update(meta or {})
        print('CLIP', name, info['frames'], f"support max {max(errors) * 1000:.1f} mm", flush=True)
        return info

    def build(self):
        g = self.guard; clips = {}
        sec = lambda f: round((f - 1) / FPS, 4)
        hold_both = {'Left': self.grip_props['Left'], 'Right': self.grip_props['Right']}
        # Guard idle: breathing loop on the captured stance (3 s, frame 181 == frame 1).
        idle = [{'pose': self.breathe(g, i / FPS, 3.0), 'yaw': 0., 'xy': (0., 0.), 'source': GUARD_FRAME} for i in range(181)]
        clips['SwordIdle'] = self.write('SwordIdle · library', idle, loop=True, meta={'kind': 'loop', 'source': f'combo frame {GUARD_FRAME} stance + breathing'})
        # Draw / sheath: library idle <-> guard, 27 frames. The support hand joins the grip over the last 40 %.
        draw = self.link(self.idle, g, 27, ease=smooth)
        hands_draw = lambda i, n: {'Left': self.blend_props(self.idle_hand['Left'], self.grip_props['Left'], smooth((i / (n - 1) - .55) / .45)),
                                   'Right': self.blend_props(self.idle_hand['Right'], self.grip_props['Right'], smooth(i / (n - 1) / .35))}
        clips['SwordDraw'] = self.write('SwordDraw · library', draw, support=lambda i, n: smooth((i / (n - 1) - .6) / .4), hands=hands_draw,
                                        meta={'kind': 'one-shot', 'source': 'authored blend: Idle · library frame 1 -> guard', 'sword_visible_from_frame': 1})
        sheath = self.link(g, self.idle, 27, ease=smooth)
        clips['SwordSheath'] = self.write('SwordSheath · library', sheath, support=lambda i, n: 1 - smooth(i / (n - 1) / .4), hands=lambda i, n: hands_draw(n - 1 - i, n),
                                          meta={'kind': 'one-shot', 'source': 'authored blend: guard -> Idle · library frame 1', 'sword_hidden_from_frame': 27})
        # Attack chain: three captured strikes, each with a 16-18 frame recovery to the guard.
        for name, f0, f1, tail, active, link in [('SwordAttack1', 29, 65, 16, (45, 57), (57, 65)), ('SwordAttack2', 81, 115, 16, (97, 111), (109, 115)), ('SwordAttack3', 127, 165, 18, (145, 161), (161, 165))]:
            frames = self.captured(f0, f1); frames += self.tail(frames, tail)
            clips[name] = self.write(name + ' · library', frames, meta={'kind': 'one-shot', 'source': f'combo frames {f0}-{f1} + {tail}-frame recovery',
                'active_window_seconds': [sec(active[0] - f0 + 1), sec(active[1] - f0 + 1)], 'link_window_seconds': [sec(link[0] - f0 + 1), (len(frames) - 1) / FPS],
                'cancel_after_seconds': sec(link[0] - f0 + 1), 'capture_frames': [f0, f1]})
        # Charged attack: authored raise into the captured back-lean wind-up (frame 137), breathing hold, captured release.
        coil = self.frames[137]
        up = self.link(g, coil, 18, lead=(['RightShoulder', 'RightArm', 'RightForeArm', 'RightHand', 'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand'], 1.35))
        clips['SwordChargeUp'] = self.write('SwordChargeUp · library', up, meta={'kind': 'one-shot', 'source': 'authored blend: guard -> combo frame 137'})
        hold = [{'pose': self.breathe(coil, i / FPS, 2.0, .8), 'yaw': 0., 'xy': (0., 0.), 'source': 137} for i in range(121)]
        clips['SwordChargeHold'] = self.write('SwordChargeHold · library', hold, loop=True, meta={'kind': 'loop', 'source': 'combo frame 137 wind-up + breathing'})
        release = self.captured(137, 165); release += self.tail(release, 18)
        clips['SwordChargeRelease'] = self.write('SwordChargeRelease · library', release, meta={'kind': 'one-shot', 'source': 'combo frames 137-165 + 18-frame recovery',
            'active_window_seconds': [sec(145 - 137 + 1), sec(161 - 137 + 1)], 'cancel_after_seconds': sec(161 - 137 + 1), 'capture_frames': [137, 165]})
        # Parry: 3-frame link into the captured rise (163-177, in place), settle, captured lowering (191-199 at 1.4x), back to guard.
        raise_ = self.link(g, self.frames[163], 3)
        cover = [{'pose': self.at(f), 'yaw': 0., 'xy': (0., 0.), 'source': f} for f in range(164, 178)]
        settle = self.link(self.frames[177], self.frames[191], 6)
        lower = [{'pose': self.at(f), 'yaw': 0., 'xy': (0., 0.), 'source': f} for f in np.arange(192.4, 199.01, 1.4)]
        parry = raise_ + cover + settle + lower; parry += self.link(parry[-1]['pose'], g, 8)
        clips['SwordParry'] = self.write('SwordParry · library', parry, meta={'kind': 'one-shot', 'source': 'authored 3-frame link, combo 163-177 rise (in place), 6-frame settle, 191-199 lowering at 1.4x, 8-frame return',
            'active_window_seconds': [sec(6), sec(21)], 'cancel_after_seconds': sec(24)})
        # Parry success: recoil from the cover pose, then the game chains into SwordAttack1.
        base = self.frames[175]; recoil = {'bases': {n: m.copy() for n, m in base['bases'].items()}, 'Hrel': base['Hrel'].copy()}
        for n, deg, axis in [(P + 'Spine', -5, 'X'), (P + 'Spine1', -4, 'X'), (P + 'RightArm', 9, 'X'), (P + 'LeftArm', 9, 'X'), (P + 'Neck', 4, 'X')]:
            recoil['bases'][n] = recoil['bases'][n] @ Matrix.Rotation(math.radians(deg), 4, axis)
        recoil['Hrel'] = Matrix.Translation((-.012, 0, -.004)) @ recoil['Hrel']
        hit = self.link(base, recoil, 4, ease=smooth) + [{'pose': recoil, 'yaw': 0., 'xy': (0., 0.), 'source': None}] * 3 + self.link(recoil, base, 6)
        clips['SwordParryHit'] = self.write('SwordParryHit · library', hit, meta={'kind': 'one-shot', 'source': 'authored recoil on combo frame 175', 'counter_from_seconds': sec(9)})
        # Untouched accepted combo on the current body, with root motion, for reference/comparison.
        combo = self.captured(1, 212)
        clips['SwordCombo'] = self.write('SwordCombo · reference', combo, meta={'kind': 'reference', 'source': 'accepted mixamo-r02 combo, complete', 'capture_frames': [1, 212]})
        self.clips = clips

    def save(self):
        OUT.mkdir(exist_ok=True); (OUT / '.gitignore').write_text('diagnostics/\n*.blend1\n'); (OUT / 'diagnostics').mkdir(exist_ok=True)
        # the untouched library keeps its exact curves; the combo action itself is not kept (its clips are)
        bpy.data.actions.remove(self.combo)
        for name, sig in self.library.items(): assert self.signature(bpy.data.actions[name]) == sig, name
        set_clip(self.arm, bpy.data.actions['Idle · library']); self.scene.frame_set(1)
        self.scene.frame_start = 1; self.scene.frame_end = 241
        native = OUT / f'WarmOriginal-Game-{REV[5:]}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(native))
        record = self.record
        record['roles'] = [r for r in record['roles'] if not r['role'].startswith('Sword')]
        for role, info in self.clips.items():
            row = {'role': role, 'clip': info['clip'], 'mapping': role, 'fps': FPS, 'frames': info['frames'], 'duration_seconds': info['duration_seconds'],
                   'loop': info['loop'], 'kind': info['kind'], 'reference_revision': 'sword-r01/stage1-bokken/mixamo-r02', 'travel': None, 'tested_play_rate': 1.0,
                   'root_motion': 'root bone carries captured travel and turning' if info['root_motion'] else 'in place; controller owns translation',
                   'yaw_ownership': 'clip root' if info['root_motion'] else 'controller', 'weapon': 'bokken in the right hand, two-handed unless noted',
                   'entry_pose': 'SwordIdle', 'exit_pose': 'SwordIdle', 'notes': info['source'], 'validation_record': 'combat-validation.json', 'sword': True}
            for k in ['active_window_seconds', 'link_window_seconds', 'cancel_after_seconds', 'counter_from_seconds', 'capture_frames', 'end_yaw_degrees', 'end_travel',
                      'support_hand_error_max_m', 'sword_visible_from_frame', 'sword_hidden_from_frame']:
                if k in info: row[k] = info[k]
            record['roles'].append(row)
        record.update(native=str(native.relative_to(ROOT)), native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                      parent_source=str(self.source.relative_to(ROOT)), parent_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
                      revision=REV, changed_actions=[i['clip'] for i in self.clips.values()], other_parent_actions_preserved=True,
                      combat_source={'blend': str(COMBO.relative_to(ROOT)), 'sha256': hashlib.sha256(COMBO.read_bytes()).hexdigest(), 'action': COMBO_ACTION, 'rest_matrix_max_error': self.rest_error},
                      sword={'object': 'Bokken-stage1-r01', 'parent_bone': P + 'RightHand', 'matrix_basis': [list(r) for r in self.sword.matrix_basis], 'hold_socket': json.loads(self.sword['hold_socket']),
                             'blade_local_z': [.0995, .36], 'grip_props': self.grip_props})
        (OUT / 'source-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
        (OUT / 'combat-build.json').write_text(json.dumps({'clips': self.clips, 'grip_props': self.grip_props, 'guard_yaw_degrees': self.guard_yaw, 'idle_yaw_degrees': self.idle_yaw,
                                                            'root_yaw_degrees': [float(v) for v in self.root_yaw], 'root_xy': self.root_xy.tolist()}, indent=1) + '\n')
        print('REVISION_READY', REV, native, flush=True)


if __name__ == '__main__':
    b = Builder(); b.build(); b.save()
