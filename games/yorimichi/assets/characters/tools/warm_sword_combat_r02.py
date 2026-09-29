"""Combat clips r02: the accepted Mixamo strikes without the spin, faster, ending on the target.

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/warm_sword_combat_r02.py -- [--parent game-r14] [--revision game-r15]

Builds on `warm_sword_combat_build.Builder` (same combo, same guard, fingers, support-hand solve and
recoveries) and changes three things, all measured in `combat-build.json`:

- **Facing.** The combo is a spinning great-sword capture: 130-224 degrees of body turn per strike, a
  full 360 over the combo, so the character ended each strike facing away. The root yaw of each strike
  is compressed to a fraction `k` of the captured turn (enough to put the hips into the cut), and the
  recovery turns the root to the direction the cut landed, so a strike aimed at an enemy ends facing it.
- **Feet.** Turning the body less than the capture would make planted feet pivot and slide. Feet that
  are planted in the capture are pinned in the new world (mean position and heading of each contact),
  the correction is blended through the steps between contacts, and each leg is re-solved with a
  two-bone solve that keeps the captured knee plane.
- **Speed.** Each strike is time-warped by a smooth monotone curve through phase keys: the wind-up runs
  about twice as fast, the cut 1.6-1.8x, recoveries are shorter; draw, sheathe and parry are quicker.

Per strike the manifest also records where the blade meets a target (`contact_yaw_degrees`, positive
to the character's left, and `contact_distance`, armature units from the clip's start position), which
the game uses to aim the strike and step in, replacing hand-measured constants.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0, str(Path(__file__).parent))
import warm_sword_combat_build as W
from warm_sword_combat_build import P, HANDS, HAND_PROPS, FPS, GUARD_FRAME, smooth, smoother, unwrap
from warm_outfit_correctives import set_clip

ROOT = W.ROOT; ASSET = W.ASSET
BLADE_POINT = .0995 + .7 * (.36 - .0995)        # blade local z of the point that meets the target (70 % along the blade)

# Strike timing: (output seconds, combo source frame) phase keys, turn fraction k, recovery frames, active and link source frames.
STRIKES = {
    'SwordAttack1': dict(keys=[(0., 29), (.10, 40), (.14, 45), (.27, 58), (.35, 65)], k=.35, tail=12, active=(45, 57), link=57),
    'SwordAttack2': dict(keys=[(0., 81), (.09, 93), (.13, 98), (.27, 113), (.30, 116)], k=.35, tail=12, active=(97, 111), link=110),
    'SwordAttack3': dict(keys=[(0., 127), (.07, 133), (.12, 143), (.30, 163), (.34, 166)], k=.28, tail=15, active=(145, 161), link=None),
    'SwordChargeRelease': dict(keys=[(0., 137), (.04, 143), (.22, 163), (.26, 166)], k=.30, tail=16, active=(145, 161), link=None),
}
PLANT_SPEED = .30          # armature units per source second: slower than this counts as a planted foot
PLANT_HEIGHT = .018        # and within this of the clip's lowest ankle


def pchip(xs, ys):
    """Monotone cubic interpolant (Fritsch-Carlson) through increasing keys; returns f(x)."""
    xs = np.asarray(xs, float); ys = np.asarray(ys, float); h = np.diff(xs); d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for i in range(1, len(xs) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0], m[-1] = d[0], d[-1]

    def f(x):
        i = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)); t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1]
    return f


def inverse(f, x0, x1, y):
    lo, hi = x0, x1
    for _ in range(60):
        mid = .5 * (lo + hi)
        if f(mid) < y: lo = mid
        else: hi = mid
    return .5 * (lo + hi)


class Builder(W.Builder):
    def __init__(self, parent, revision):
        self.parent_rev, self.rev = parent, revision
        self.parent_dir = ASSET / parent
        record = json.loads((self.parent_dir / 'source-manifest.json').read_text())
        source = ROOT / record['native']
        assert hashlib.sha256(source.read_bytes()).hexdigest() == record['native_sha256'], f'{parent} changed'
        self.record = record; self.source = source
        bpy.ops.wm.open_mainfile(filepath=str(source))
        self.scene = bpy.context.scene; self.scene.render.fps = FPS
        self.arm = next(o for o in self.scene.objects if o.type == 'ARMATURE')
        # The parent already carries a combat set: drop it (clips and sword) so this build replaces it cleanly.
        for action in [a for a in bpy.data.actions if a.name.startswith('Sword')]: bpy.data.actions.remove(action)
        if 'Bokken-stage1-r01' in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects['Bokken-stage1-r01'], do_unlink=True)
        for mesh in [m for m in bpy.data.meshes if m.users == 0]: bpy.data.meshes.remove(mesh)
        self.library = {a.name: self.signature(a) for a in bpy.data.actions}
        self.library_slot = next(sl for sl in bpy.data.actions['Idle · library'].slots if sl.identifier.startswith('OB')).name_display
        self.load_combo()
        assert self.sword.name == 'Bokken-stage1-r01', self.sword.name
        self.R0 = self.arm.data.bones['Root'].matrix_local.copy(); self.R0i = self.R0.inverted()
        self.Hrest = self.arm.data.bones[P + 'Hips'].matrix_local.copy()
        self.O = self.R0.translation.copy(); self.O.z = 0
        self.body_bones = [pb.name for pb in self.arm.pose.bones if pb.name not in ('Root', P + 'Hips') and not self.is_finger(pb.name)]
        self.head = bpy.data.objects['Body · head']
        self.fit_fingers()
        self.sample_combo()
        self.diagnostics = {}

    # ---------------------------------------------------------------- strikes
    def captured_despun(self, name):
        """Warped, de-spun captured frames of one strike (root yaw k x captured turn, forward travel)."""
        spec = STRIKES[name]; keys = spec['keys']
        warp = pchip([t for t, _ in keys], [f for _, f in keys]); T = keys[-1][0]
        f0 = keys[0][1]
        yaw_at = lambda f: float(np.interp(f, range(1, 213), self.root_yaw))
        xy_at = lambda f: np.array([float(np.interp(f, range(1, 213), self.root_xy[:, i])) for i in range(2)])
        y0, xy0 = yaw_at(f0), xy_at(f0)
        c, s = math.cos(math.radians(-y0)), math.sin(math.radians(-y0))
        n = int(round(T * FPS)); frames = []
        for i in range(n + 1):
            f = float(warp(i / FPS))
            d = xy_at(f) - xy0; local = (c * d[0] - s * d[1], s * d[0] + c * d[1])
            frames.append({'pose': self.at(f), 'yaw': spec['k'] * (yaw_at(f) - y0), 'xy': local, 'source': f,
                           'yaw_c': yaw_at(f) - y0, 'xy_c': local})
        return frames, warp, T

    def contact(self, frames, warp, T, active):
        """Where the blade meets a target: the 70 % blade point where, inside the active window, it crosses the
        character's current facing (the root heading at that frame); the fastest such crossing if there are several.
        Armature space: bearing from the clip's start root position, positive to the left; height above the guard's floor."""
        t0, t1 = inverse(warp, 0, T, active[0]), inverse(warp, 0, T, active[1])
        self.arm.animation_data.action = None
        inv = self.arm.matrix_world.inverted(); rows = []
        for i, fr in enumerate(frames):
            self.apply(fr['pose'], fr['yaw'], fr['xy'], support=0.)
            p = inv @ (self.sword.matrix_world @ Vector((0, 0, BLADE_POINT))); rel = p - self.O
            bearing = math.degrees(math.atan2(rel.y, rel.x))
            rows.append({'i': i, 'p': p.copy(), 'bearing': bearing, 'off': (bearing - fr['yaw'] + 180) % 360 - 180,
                         'speed': (p - rows[-1]['p']).length * FPS if rows else 0.})
        window = [r for r in rows if t0 - .5 / FPS <= r['i'] / FPS <= t1 + .5 / FPS]
        crossings = [(a, b) for a, b in zip(window, window[1:]) if a['off'] * b['off'] <= 0 and abs(a['off'] - b['off']) < 90]
        if crossings:
            a, b = max(crossings, key=lambda ab: ab[0]['speed'] + ab[1]['speed'])
            u = a['off'] / (a['off'] - b['off']) if a['off'] != b['off'] else 0.; p = a['p'].lerp(b['p'], u); frame = a['i'] + u
        else:
            r = min(window, key=lambda r: abs(r['off'])); p = r['p']; frame = r['i']
        rel = p - self.O
        return {'contact_yaw_degrees': math.degrees(math.atan2(rel.y, rel.x)), 'contact_distance': math.hypot(rel.x, rel.y),
                'contact_frame': frame + 1, 'contact_height': p.z - self.floor_ref, 'contact_rule': 'crossing' if crossings else 'nearest'}

    def strike(self, name):
        spec = STRIKES[name]
        frames, warp, T = self.captured_despun(name)
        hit = self.contact(frames, warp, T, spec['active'])
        last = frames[-1]; end_yaw = hit['contact_yaw_degrees']
        tail = self.link(last['pose'], self.guard, spec['tail'], xy=last['xy'])
        for j, fr in enumerate(tail):
            fr['yaw'] = last['yaw'] + (end_yaw - last['yaw']) * smoother((j + 1) / len(tail))
        frames += tail
        sec = lambda f: round(inverse(warp, 0, T, f), 4)
        meta = {'kind': 'one-shot', 'source': f"combo frames {spec['keys'][0][1]}-{spec['keys'][-1][1]} time-warped, turn x{spec['k']}, {spec['tail']}-frame recovery to the contact heading",
                'active_window_seconds': [sec(spec['active'][0]), sec(spec['active'][1])], 'capture_frames': [spec['keys'][0][1], spec['keys'][-1][1]],
                'time_warp_keys': spec['keys'], 'turn_fraction': spec['k'], **hit}
        if spec['link']:
            meta['link_window_seconds'] = [sec(spec['link']), (len(frames) - 1) / FPS]; meta['cancel_after_seconds'] = sec(spec['link'])
        else:
            meta['cancel_after_seconds'] = round(T + .5 * spec['tail'] / FPS, 4)
        return frames, meta

    # ---------------------------------------------------------------- planted feet
    def feet_now(self):
        out = {}
        for side in HANDS:
            foot = self.arm.pose.bones[P + side + 'Foot']; M = self.arm.matrix_world @ foot.matrix
            out[side] = (M.translation.copy(), M.to_3x3().normalized())
        return out

    @staticmethod
    def heading(R):
        v = R @ Vector((0, 1, 0)); return math.degrees(math.atan2(v.y, v.x))

    def plan_feet(self, frames):
        """Per frame and foot: (dx, dy, dyaw) corrections that hold captured contacts still in the new world."""
        self.arm.animation_data.action = None
        natural, captured = [], []
        for fr in frames:
            self.apply(fr['pose'], fr['yaw'], fr['xy'], support=0., floor=fr['source'] is None)
            natural.append(self.feet_now())
            if 'yaw_c' in fr:
                self.apply(fr['pose'], fr['yaw_c'], fr['xy_c'], support=0.)
                captured.append(self.feet_now())
            else:
                captured.append(natural[-1])
        plan = {side: [(0., 0., 0.)] * len(frames) for side in HANDS}; report = {}
        for side in HANDS:
            z = [n[side][0].z for n in natural]; zmin = min(z)
            planted = []
            for i in range(len(frames)):
                if i == 0: j = 1
                else: j = i - 1
                a, b = captured[i][side][0], captured[j][side][0]
                fa, fb = frames[i]['source'], frames[j]['source']
                dt = abs(fa - fb) / FPS if fa is not None and fb is not None and fa != fb else 1. / FPS
                speed = math.hypot(a.x - b.x, a.y - b.y) / dt
                planted.append(speed < PLANT_SPEED and z[i] < zmin + PLANT_HEIGHT)
            # close one-frame gaps, drop one- and two-frame contacts
            for i in range(1, len(planted) - 1):
                if not planted[i] and planted[i - 1] and planted[i + 1]: planted[i] = True
            runs, i = [], 0
            while i < len(planted):
                if planted[i]:
                    j = i
                    while j + 1 < len(planted) and planted[j + 1]: j += 1
                    if j - i >= 2: runs.append((i, j))
                    i = j + 1
                else: i += 1
            offsets = {}
            for r, (a, b) in enumerate(runs):
                pts = [natural[i][side][0] for i in range(a, b + 1)]
                heads = unwrap([self.heading(natural[i][side][1]) for i in range(a, b + 1)])
                if r == 0 and a == 0: px, py, ph = pts[0].x, pts[0].y, heads[0]
                elif r == len(runs) - 1 and b == len(frames) - 1: px, py, ph = pts[-1].x, pts[-1].y, heads[-1]
                else: px, py, ph = float(np.mean([p.x for p in pts])), float(np.mean([p.y for p in pts])), float(np.mean(heads))
                for k, i in enumerate(range(a, b + 1)):
                    offsets[i] = (px - pts[k].x, py - pts[k].y, ph - heads[k])
            keyed = sorted(offsets)
            for i in range(len(frames)):
                if i in offsets: plan[side][i] = offsets[i]; continue
                before = [k for k in keyed if k < i]; after = [k for k in keyed if k > i]
                a = (before[-1], offsets[before[-1]]) if before else (0, (0., 0., 0.))
                b = (after[0], offsets[after[0]]) if after else (len(frames) - 1, (0., 0., 0.))
                u = smooth((i - a[0]) / max(1, b[0] - a[0]))
                plan[side][i] = tuple(a[1][c] + (b[1][c] - a[1][c]) * u for c in range(3))
            report[side] = {'contacts': [[a + 1, b + 1] for a, b in runs], 'max_shift': max(math.hypot(o[0], o[1]) for o in plan[side]),
                            'max_turn_degrees': max(abs(o[2]) for o in plan[side])}
        return plan, natural, report

    def solve_leg(self, side, goal, rotation):
        """Two-bone solve of UpLeg/Leg to put the ankle at `goal` (world), keeping the current knee plane; set the foot's world rotation."""
        arm = self.arm; Wm = arm.matrix_world; inv = Wm.inverted()
        upper, lower, foot = [arm.pose.bones[P + side + part] for part in ('UpLeg', 'Leg', 'Foot')]
        hip, knee, ankle = Wm @ upper.head, Wm @ lower.head, Wm @ foot.head
        l1, l2 = (knee - hip).length, (ankle - knee).length
        reach = goal - hip; d = reach.length; axis = reach.normalized()
        bend = knee - hip; pole = (bend - axis * bend.dot(axis)).normalized()
        safe = max(abs(l1 - l2) + 1e-4, min(l1 + l2 - 1e-4, d))
        along = (l1 * l1 - l2 * l2 + safe * safe) / (2 * safe); height = math.sqrt(max(0., l1 * l1 - along * along))
        new_knee = hip + axis * along + pole * height; reached = hip + axis * safe
        for bone, new_dir in [(upper, new_knee - hip), (lower, reached - new_knee)]:
            old = (Wm @ bone.matrix).copy(); now_dir = (Wm @ bone.tail) - (Wm @ bone.head)
            swing = now_dir.normalized().rotation_difference(new_dir.normalized())
            desired = (swing.to_matrix() @ old.to_3x3()).to_4x4(); desired.translation = Wm @ bone.head
            bone.matrix = inv @ desired
            bpy.context.view_layer.update()
        scale = (Wm @ foot.matrix).to_scale()
        desired = rotation.to_4x4() @ Matrix.Diagonal((*scale, 1)); desired.translation = Wm @ foot.head
        foot.matrix = inv @ desired
        bpy.context.view_layer.update()
        return ((Wm @ foot.head) - goal).length

    def write(self, name, frames, loop=False, support=None, hands=None, meta=None, pin=False):
        if not pin: return super().write(name, frames, loop, support, hands, meta)
        plan, natural, feet_report = self.plan_feet(frames)
        action = self.new_action(name, loop); last = {}; errors = []; leg_error = 0.
        for i, fr in enumerate(frames):
            self.scene.frame_set(i + 1)
            w = support(i, len(frames)) if callable(support) else (1. if support is None else support)
            h = hands(i, len(frames)) if callable(hands) else hands
            errors.append(self.apply(fr['pose'], fr['yaw'], fr['xy'], support=w, hands=h, floor=fr['source'] is None))
            for side in HANDS:
                dx, dy, dyaw = plan[side][i]
                if abs(dx) + abs(dy) + abs(dyaw) < 1e-7: continue
                pos, rot = natural[i][side]
                goal = pos + Vector((dx, dy, 0.))
                leg_error = max(leg_error, self.solve_leg(side, goal, Matrix.Rotation(math.radians(dyaw), 3, 'Z') @ rot))
            self.key(i + 1, last)
        self.finish(action, loop)
        info = {'clip': name, 'frames': len(frames), 'duration_seconds': (len(frames) - 1) / FPS, 'loop': loop,
                'support_hand_error_max_m': max(errors), 'support_hand_frames_over_8mm': [i + 1 for i, e in enumerate(errors) if e > .008],
                'end_yaw_degrees': frames[-1]['yaw'], 'end_travel': list(frames[-1]['xy']),
                'root_motion': any(abs(f['yaw']) > 1e-6 or abs(f['xy'][0]) + abs(f['xy'][1]) > 1e-6 for f in frames),
                'source_frames': [f['source'] for f in frames if f['source'] is not None][:1] + [f['source'] for f in frames if f['source'] is not None][-1:],
                'planted_feet': feet_report, 'leg_solve_error_max_m': leg_error}
        info.update(meta or {})
        print('CLIP', name, info['frames'], f"support max {max(errors) * 1000:.1f} mm, leg {leg_error * 1000:.1f} mm, feet {json.dumps(feet_report)}", flush=True)
        return info

    # ---------------------------------------------------------------- the set
    def build(self):
        g = self.guard; clips = {}
        sec = lambda f: round((f - 1) / FPS, 4)
        idle = [{'pose': self.breathe(g, i / FPS, 3.0), 'yaw': 0., 'xy': (0., 0.), 'source': GUARD_FRAME} for i in range(181)]
        clips['SwordIdle'] = self.write('SwordIdle · library', idle, loop=True, meta={'kind': 'loop', 'source': f'combo frame {GUARD_FRAME} stance + breathing'})
        hands_draw = lambda i, n: {'Left': self.blend_props(self.idle_hand['Left'], self.grip_props['Left'], smooth((i / (n - 1) - .55) / .45)),
                                   'Right': self.blend_props(self.idle_hand['Right'], self.grip_props['Right'], smooth(i / (n - 1) / .35))}
        draw = self.link(self.idle, g, 18, ease=smooth)
        clips['SwordDraw'] = self.write('SwordDraw · library', draw, support=lambda i, n: smooth((i / (n - 1) - .6) / .4), hands=hands_draw,
                                        meta={'kind': 'one-shot', 'source': 'authored blend: Idle · library frame 1 -> guard (18 frames)', 'sword_visible_from_frame': 1})
        sheath = self.link(g, self.idle, 20, ease=smooth)
        clips['SwordSheath'] = self.write('SwordSheath · library', sheath, support=lambda i, n: 1 - smooth(i / (n - 1) / .4), hands=lambda i, n: hands_draw(n - 1 - i, n),
                                          meta={'kind': 'one-shot', 'source': 'authored blend: guard -> Idle · library frame 1 (20 frames)', 'sword_hidden_from_frame': 20})
        for name in ['SwordAttack1', 'SwordAttack2', 'SwordAttack3']:
            frames, meta = self.strike(name)
            clips[name] = self.write(name + ' · library', frames, meta=meta, pin=True)
        coil = self.frames[137]
        up = self.link(g, coil, 14, lead=(['RightShoulder', 'RightArm', 'RightForeArm', 'RightHand', 'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand'], 1.35))
        clips['SwordChargeUp'] = self.write('SwordChargeUp · library', up, meta={'kind': 'one-shot', 'source': 'authored blend: guard -> combo frame 137 (14 frames)'})
        hold = [{'pose': self.breathe(coil, i / FPS, 2.0, .8), 'yaw': 0., 'xy': (0., 0.), 'source': 137} for i in range(121)]
        clips['SwordChargeHold'] = self.write('SwordChargeHold · library', hold, loop=True, meta={'kind': 'loop', 'source': 'combo frame 137 wind-up + breathing'})
        frames, meta = self.strike('SwordChargeRelease')
        clips['SwordChargeRelease'] = self.write('SwordChargeRelease · library', frames, meta=meta, pin=True)
        # Parry: 3-frame link into the captured rise (163-177, in place, at 1.4x), a short settle, the lowering at 1.6x, back to guard.
        raise_ = self.link(g, self.frames[163], 3)
        cover = [{'pose': self.at(f), 'yaw': 0., 'xy': (0., 0.), 'source': f} for f in np.arange(164.4, 177.01, 1.4)]
        settle = self.link(self.frames[177], self.frames[191], 5)
        lower = [{'pose': self.at(f), 'yaw': 0., 'xy': (0., 0.), 'source': f} for f in np.arange(192.6, 199.01, 1.6)]
        parry = raise_ + cover + settle + lower; parry += self.link(parry[-1]['pose'], g, 7)
        active_end = len(raise_) + len(cover) + len(settle)
        clips['SwordParry'] = self.write('SwordParry · library', parry, meta={'kind': 'one-shot', 'source': 'authored 3-frame link, combo 163-177 rise at 1.4x (in place), 5-frame settle, 191-199 lowering at 1.6x, 7-frame return',
            'active_window_seconds': [sec(3), sec(active_end + 1)], 'cancel_after_seconds': sec(active_end + 3)})
        base = self.frames[175]; recoil = {'bases': {n: m.copy() for n, m in base['bases'].items()}, 'Hrel': base['Hrel'].copy()}
        for n, deg, axis in [(P + 'Spine', -5, 'X'), (P + 'Spine1', -4, 'X'), (P + 'RightArm', 9, 'X'), (P + 'LeftArm', 9, 'X'), (P + 'Neck', 4, 'X')]:
            recoil['bases'][n] = recoil['bases'][n] @ Matrix.Rotation(math.radians(deg), 4, axis)
        recoil['Hrel'] = Matrix.Translation((-.012, 0, -.004)) @ recoil['Hrel']
        hit = self.link(base, recoil, 3, ease=smooth) + [{'pose': recoil, 'yaw': 0., 'xy': (0., 0.), 'source': None}] * 2 + self.link(recoil, base, 5)
        clips['SwordParryHit'] = self.write('SwordParryHit · library', hit, meta={'kind': 'one-shot', 'source': 'authored recoil on combo frame 175', 'counter_from_seconds': sec(7)})
        combo = self.captured(1, 212)
        clips['SwordCombo'] = self.write('SwordCombo · reference', combo, meta={'kind': 'reference', 'source': 'accepted mixamo-r02 combo, complete (spinning, not used in play)', 'capture_frames': [1, 212]})
        self.clips = clips

    def save(self):
        W.REV, W.OUT, W.PARENT = self.rev, ASSET / self.rev, self.parent_dir
        super().save()
        build = json.loads((W.OUT / 'combat-build.json').read_text())
        build['style'] = 'r02: de-spun, time-warped, planted feet'; build['strikes'] = STRIKES
        (W.OUT / 'combat-build.json').write_text(json.dumps(build, indent=1) + '\n')
        add_contact_fields(W.OUT / 'source-manifest.json', self.clips)


CONTACT_FIELDS = ['contact_yaw_degrees', 'contact_distance', 'contact_height', 'turn_fraction', 'time_warp_keys']


def add_contact_fields(manifest_path, clips):
    """The base builder copies a fixed list of fields into the manifest roles; add the r02 ones the game reads."""
    record = json.loads(manifest_path.read_text())
    for row in record['roles']:
        info = clips.get(row['role'], {})
        for key in CONTACT_FIELDS:
            if key in info: row[key] = info[key]
    manifest_path.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument('--parent', default='game-r14'); ap.add_argument('--revision', default='game-r15')
    a = ap.parse_args(argv)
    b = Builder(a.parent, a.revision); b.build(); b.save()
