"""Armed locomotion: the usual walk and sprint with the sword swinging in the right hand (game-r16 = game-r15 + 2 clips).

    blender -b --threads 4 --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_sword_locomotion.py -- [--parent game-r15] [--revision game-r16]

While the sword was out, the game laid the guard's right arm over every locomotion clip, so the sword arm stayed frozen
while the body ran. `SwordWalk · armed` and `SwordSprint · armed` are copies of `Walk · library` and `Sprint · dressed`
where only the right arm and the grip change. The game plays their right arm in step with the body (BS_SwordLocomotion,
same speeds and lengths; the run is the sprint at 0.8x, as for the unarmed run).

Per frame, from the source clip:
- **Upper arm.** The clip's own swing, same timing. The sprint's swing is scaled to `amplitude` of itself about its cycle
  mean: a full sprint pump with a sword in the fist would carry the blade over the head.
- **Width.** Seen from behind, the sprint's elbow and wrist stay at the unarmed arm's distance from the body (+1.5 cm):
  a two-bone solve moves the wrist in and turns the elbow in about the shoulder-wrist line (user feedback: the arm
  hung too wide and should look like the free arm from the back).
- **Elbow.** The walk keeps the clip's elbow. The sprint's elbow is set so the forearm points down and forward along the
  swing (`forearm` pitch band, back to front): a forearm that points forward can only hold the blade upright.
- **Wrist.** The hand holds the grip with the palm toward the body (hammer grip, tip on the index side). With a straight
  wrist the blade stands at right angles to the forearm; its pitch and outward yaw are clamped into a band (tip forward,
  a little down at the back of the swing, up at the front, angled out from the legs) and the wrist bends only by the
  clamp. The forearm roll carries the palm's turn so the wrist does not twist.
- **Fingers.** The sword clips' grip props.

The result is smoothed along the cycle and checked: blade clearance to the clothes and head, tip height, wrist bend,
forearm roll change and loop closure (`locomotion-build.json`).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, json, math, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
sys.path.insert(0, str(Path(__file__).parent))
from cairo_outfit_correctives import set_clip

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
P = 'mixamorig:'
FPS = 60
HAND_PROPS = ['thumb_curl', 'index_curl', 'middle_curl', 'ring_curl', 'pinky_curl', 'thumb_opposition', 'finger_spread']
ARM = [P + 'RightArm', P + 'RightForeArm', P + 'RightHand']
FORWARD, RIGHT, UP = Vector((1, 0, 0)), Vector((0, -1, 0)), Vector((0, 0, 1))   # locomotion clips face +X in place
BLADE = (.0995, .36)                  # sword-local z of the blade (guard end, tip)
UNIT_CM = 148.                        # armature units -> game cm
CLIPS = {
    # role: source action, upper-arm amplitude and outward lift (degrees), forearm pitch band (back, front) or None, palm turn
    # (degrees; turns the straight-wrist blade outward), blade pitch band, blade yaw band (+ = outward). `width` (cm) keeps
    # the elbow and wrist that far outside the source arm's own distance from the body (seen from behind the sword arm
    # must look like the free arm; user feedback 28 Sep), None leaves them where the solve puts them.
    'SwordWalk': dict(source='Walk · library', role='Walk', amplitude=1.0, abduct=0., forearm=None, width=None, palm_yaw=8., pitch=(-14., 36.), yaw=(4., 24.)),
    'SwordStand': dict(source='Idle · library', role='Idle', amplitude=1.0, abduct=0., forearm=None, width=None, palm_yaw=8., pitch=(-15., 20.), yaw=(4., 24.)),
    'SwordSprint': dict(source='Sprint · dressed', role='Sprint', amplitude=.7, abduct=0., forearm=(-86., -40.), width=1.5, palm_yaw=8., pitch=(-8., 42.), yaw=(4., 24.)),
}
CLEARANCE = .03                       # armature units (4.4 cm): blade to clothes/head, else the blade turns further out
YAW_LIMIT = 40.
import os
ROLL_MODE = os.environ.get('ROLL_MODE', 'own')    # 'roll': the carry hold moving to the side (the first version)
FLOOR = -.0013                        # armature-space floor height
CARRY_BLADE = (48., 6.)                # the one-handed carry: blade pitch and outward yaw (degrees)


def smooth01(t):
    t = max(0., min(1., t)); return t * t * (3 - 2 * t)


def pitch_yaw(d):
    return math.degrees(math.asin(max(-1., min(1., d.dot(UP))))), math.degrees(math.atan2(d.dot(RIGHT), d.dot(FORWARD)))


def direction(pitch, yaw):
    p, y = math.radians(pitch), math.radians(yaw)
    return (FORWARD * (math.cos(p) * math.cos(y)) + RIGHT * (math.cos(p) * math.sin(y)) + UP * math.sin(p)).normalized()


def gaussian_open(values, sigma):
    """Gaussian smoothing of an open sequence (edges held)."""
    r = int(math.ceil(3 * sigma)); k = np.exp(-.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    padded = np.concatenate([np.repeat(values[:1], r, 0), values, np.repeat(values[-1:], r, 0)], 0)
    return np.stack([np.convolve(padded[:, i], k, 'valid') for i in range(values.shape[1])], 1)


def cyclic_smooth(quats, sigma):
    """Gaussian smoothing of a closed loop of quaternions (first == last sample)."""
    n = len(quats) - 1; q = np.array([list(x) for x in quats[:-1]])
    for i in range(1, n):
        if np.dot(q[i], q[i - 1]) < 0: q[i] = -q[i]
    r = int(math.ceil(3 * sigma)); k = np.exp(-.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    out = []
    for i in range(n):
        acc = np.zeros(4)
        for j, w in zip(range(i - r, i + r + 1), k):
            v = q[j % n]; acc += w * (v if np.dot(v, q[i]) >= 0 else -v)
        out.append(Quaternion(acc / np.linalg.norm(acc)))
    return out + [out[0].copy()]


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
        self.sword = bpy.data.objects['Bokken-stage1-r01']
        for a in [a for a in bpy.data.actions if a.name.endswith(' · armed')]: bpy.data.actions.remove(a)
        self.library = {a.name: self.signature(a) for a in bpy.data.actions}
        self.grip = json.loads((self.parent_dir / 'combat-build.json').read_text())['grip_props']['Right']
        pb = self.arm.pose.bones; set_clip(self.arm, bpy.data.actions['SwordIdle · library']); self.scene.frame_set(1)
        # the sword's fixed transform relative to the hand's pose matrix (bone-parented, tail offset in matrix_world)
        self.socket = pb[P + 'RightHand'].matrix.inverted() @ self.arm.matrix_world.inverted() @ self.sword.matrix_world
        self.blade_in_hand = (self.socket.to_3x3() @ Vector((0, 0, 1))).normalized()
        rest = {n: self.arm.data.bones[n].matrix_local.to_3x3() for n in [P + 'RightShoulder', *ARM]}
        self.rest_rel = {ARM[i]: (rest[([P + 'RightShoulder'] + ARM)[i]].inverted() @ rest[ARM[i]]) for i in range(3)}
        self.bodies = [bpy.data.objects[n] for n in ('Body · outfit (Tripo skate r01)', 'Body · head')]
        self.report = {'blade_in_hand_frame': list(self.blade_in_hand)}

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

    # ---------------------------------------------------------------- pose helpers (armature space, rotation only)
    def world(self, name):
        return self.arm.pose.bones[name].matrix.to_3x3().normalized()

    def set_world(self, name, R):
        """Set a bone's armature-space rotation through its basis (the location basis is left alone)."""
        pb = self.arm.pose.bones[name]
        parent = pb.parent.matrix.to_3x3().normalized()
        basis = (parent @ self.rest_rel[name]).inverted() @ R
        q = basis.to_quaternion(); prev = pb.rotation_quaternion
        if q.dot(prev) < 0: q.negate()
        pb.rotation_quaternion = q
        bpy.context.view_layer.update()

    def blade(self):
        M = self.arm.matrix_world.inverted() @ self.sword.matrix_world
        return M @ Vector((0, 0, BLADE[0])), M @ Vector((0, 0, BLADE[1]))

    def body_tree(self):
        dg = bpy.context.evaluated_depsgraph_get(); verts, polys = [], []
        inv = self.arm.matrix_world.inverted()
        for ob in self.bodies:
            ev = ob.evaluated_get(dg); me = ev.to_mesh(); M = inv @ ev.matrix_world; base = len(verts)
            verts += [M @ v.co for v in me.vertices]; polys += [tuple(base + i for i in p.vertices) for p in me.polygons]
            ev.to_mesh_clear()
        return BVHTree.FromPolygons(verts, polys)

    def clearance(self, tree):
        b0, b1 = self.blade()
        return min(tree.find_nearest(b0.lerp(b1, t / 12))[3] for t in range(2, 13))

    # ---------------------------------------------------------------- one clip
    def build_clip(self, role, cfg):
        src = bpy.data.actions[cfg['source']]; f0, f1 = map(int, src.frame_range)
        frames = list(range(f0, f1 + 1)); pb = self.arm.pose.bones
        # Sample the source, then work with no action assigned so nothing re-evaluates over the solved arm.
        set_clip(self.arm, src); poses = []
        for f in frames:
            self.scene.frame_set(f)
            poses.append({b.name: (b.location.copy(), b.rotation_quaternion.copy()) for b in pb if b.rotation_mode == 'QUATERNION'})
        self.arm.animation_data.action = None
        for k, v in self.grip.items(): pb[ARM[2]][k] = v

        def pose(i, upper=None):
            for name, (loc, q) in poses[i].items(): pb[name].location = loc; pb[name].rotation_quaternion = q
            if upper is not None:
                pb[ARM[0]].rotation_quaternion = upper; bpy.context.view_layer.update()
                if cfg['abduct']: self.set_world(ARM[0], Matrix.Rotation(math.radians(-cfg['abduct']), 3, FORWARD) @ self.world(ARM[0]))
            bpy.context.view_layer.update()
        # the upper arm's own swing, scaled about its cycle mean (walk: unchanged)
        q_ua = [p[ARM[0]][1] for p in poses]
        mean = np.zeros(4)
        for q in q_ua: mean += np.array(q) if q.dot(q_ua[0]) >= 0 else -np.array(q)
        mean = Quaternion(mean / np.linalg.norm(mean))
        scaled = [mean.slerp(q if q.dot(mean) >= 0 else -q, cfg['amplitude']) for q in q_ua]
        fwd, width = [], []
        side = lambda p: (p - pb[P + 'Hips'].head).dot(RIGHT)
        for i in range(len(frames)):
            pose(i); width.append((side(pb[ARM[1]].head), side(pb[ARM[2]].head)))
            pose(i, scaled[i]); fwd.append((pb[ARM[1]].head - pb[ARM[0]].head).normalized().dot(FORWARD))
        lo, hi = min(fwd), max(fwd)
        solved, rows = {n: [] for n in ARM}, []
        for i, f in enumerate(frames):
            pose(i, scaled[i])
            s = smooth01((fwd[i] - lo) / max(hi - lo, 1e-6))              # 0 = back of the swing, 1 = front
            upper = (pb[ARM[1]].head - pb[ARM[0]].head).normalized()
            fore_R = self.world(ARM[1]); fore = (fore_R @ Vector((0, 1, 0))).normalized()
            if cfg['forearm']:
                target = cfg['forearm'][0] + (cfg['forearm'][1] - cfg['forearm'][0]) * s
                axis = upper.cross(fore).normalized()
                best = min((abs(math.degrees(math.asin(max(-1., min(1., (Matrix.Rotation(math.radians(t), 3, axis) @ upper).z)))) - target), t)
                           for t in np.arange(8., 150., .5))[1]
                new_fore = (Matrix.Rotation(math.radians(best), 3, axis) @ upper).normalized()
                fore_R = fore.rotation_difference(new_fore).to_matrix() @ fore_R; fore = new_fore
            if cfg['width'] is not None:
                # From behind, hold the elbow and wrist at the source arm's distance from the body: two-bone solve to the
                # wrist moved sideways, the elbow bending toward the solved elbow moved the same way.
                S, E = pb[ARM[0]].head.copy(), pb[ARM[1]].head.copy(); L1 = (E - S).length
                W = E + fore * (pb[ARM[2]].head - E).length
                L2 = (pb[ARM[2]].head - E).length
                margin = cfg['width'] / UNIT_CM
                Wt = W - RIGHT * (side(W) - width[i][1] - margin); Ep = E - RIGHT * (side(E) - width[i][0] - margin)
                d = min((Wt - S).length, (L1 + L2) * .999); axis = (Wt - S).normalized(); Wt = S + axis * d
                a = (L1 * L1 - L2 * L2 + d * d) / (2 * d); h = math.sqrt(max(0., L1 * L1 - a * a))
                pole = (Ep - S) - axis * (Ep - S).dot(axis); pole.normalize()
                # turn the elbow about the shoulder-wrist line, nearest the pole, until it is no wider than the target
                target = width[i][0] + margin
                circle = [S + axis * a + (Matrix.Rotation(math.radians(t), 3, axis) @ pole) * h for t in np.arange(-60., 60.5, 1.)]
                En = min(zip(circle, np.arange(-60., 60.5, 1.)), key=lambda c: max(0., side(c[0]) - target) * 100 + abs(c[1]) * .002)[0]
                upper_R = self.world(ARM[0]); cur = (En - S).normalized()
                self.set_world(ARM[0], (upper_R @ Vector((0, 1, 0))).rotation_difference(cur).to_matrix() @ upper_R)
                carried = self.world(ARM[1]); new_fore = (Wt - pb[ARM[1]].head).normalized()
                fore_R = (carried @ Vector((0, 1, 0))).rotation_difference(new_fore).to_matrix() @ carried; fore = new_fore
            # neutral hand: straight wrist, palm toward the body's centre line
            inward = Matrix.Rotation(math.radians(-cfg['palm_yaw']), 3, UP) @ -RIGHT
            palm = (inward - fore * inward.dot(fore)).normalized()
            neutral = Matrix((palm, fore, palm.cross(fore))).transposed()
            b_neutral = (neutral @ self.blade_in_hand).normalized()
            p, y = pitch_yaw(b_neutral)
            pc = max(cfg['pitch'][0], min(cfg['pitch'][1], p)); yc = max(cfg['yaw'][0], min(cfg['yaw'][1], y))
            # forearm roll: the neutral hand's turn goes to the forearm, the wrist only bends
            roll_R = neutral @ self.rest_rel[ARM[2]].inverted()
            roll_R = (roll_R @ Vector((0, 1, 0))).rotation_difference(fore).to_matrix() @ roll_R
            self.set_world(ARM[1], roll_R)
            tree = self.body_tree()
            for extra in range(0, 60):
                yt = min(YAW_LIMIT, yc + extra); bt = direction(pc, yt)
                self.set_world(ARM[2], b_neutral.rotation_difference(bt).to_matrix() @ neutral)
                if self.clearance(tree) >= CLEARANCE or yt >= YAW_LIMIT: break
            for n in ARM: solved[n].append(pb[n].rotation_quaternion.copy())
            twist = math.degrees((fore_R.inverted() @ self.world(ARM[1])).to_quaternion().angle)
            rows.append(dict(frame=f, s=round(s, 3), forearm_pitch=round(math.degrees(math.asin(fore.z)), 1), neutral=[round(p, 1), round(y, 1)], blade=[round(pc, 1), round(yt, 1)],
                             wrist_bend=round(math.degrees(b_neutral.angle(bt)), 1), forearm_turn=round(twist, 1)))
        for n in ARM:
            solved[n][-1] = solved[n][0].copy()
            solved[n] = cyclic_smooth(solved[n], 1.0)
        return self.write(role, cfg, src, frames, solved, rows)

    def write(self, role, cfg, src, frames, solved, rows):
        action = src.copy(); action.name = role + ' · armed'; action.use_fake_user = True
        drop = [f'pose.bones["{n}"].rotation_quaternion' for n in ARM] + [f'pose.bones["{ARM[2]}"]["{k}"]' for k in HAND_PROPS]
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in [fc for fc in bag.fcurves if fc.data_path in drop]: bag.fcurves.remove(fc)
        set_clip(self.arm, action); pb = self.arm.pose.bones
        for i, f in enumerate(frames):
            for n in ARM:
                pb[n].rotation_quaternion = solved[n][i]; pb[n].keyframe_insert('rotation_quaternion', frame=f, group=n)
        hand = pb[ARM[2]]
        for k in HAND_PROPS:
            hand[k] = self.grip[k]
            for f in (frames[0], frames[-1]): hand.keyframe_insert(f'["{k}"]', frame=f, group=ARM[2] + ' · grip')
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        if fc.data_path in drop:
                            for k in fc.keyframe_points: k.interpolation = 'LINEAR'
                            if not fc.modifiers: fc.modifiers.new('CYCLES')
        return self.check(role, cfg, action, frames, rows)

    def check(self, role, cfg, action, frames, rows):
        set_clip(self.arm, action); pb = self.arm.pose.bones
        out = []
        for f, row in zip(frames, rows):
            self.scene.frame_set(f)
            b0, b1 = self.blade(); d = (b1 - b0).normalized(); p, y = pitch_yaw(d)
            tree = self.body_tree(); c = self.clearance(tree)
            row.update(final=[round(p, 1), round(y, 1)], clearance_cm=round(c * UNIT_CM, 1), tip_height_cm=round(b1.z * UNIT_CM, 1),
                       wrist_height_cm=round(pb[ARM[2]].head.z * UNIT_CM, 1),
                       wrist_out_cm=round((pb[ARM[2]].head - pb[P + 'Hips'].head).dot(RIGHT) * UNIT_CM, 1),
                       elbow_out_cm=round((pb[ARM[1]].head - pb[P + 'Hips'].head).dot(RIGHT) * UNIT_CM, 1))
            out.append(row)
        self.scene.frame_set(frames[0]); a = [pb[n].matrix.copy() for n in ARM]
        self.scene.frame_set(frames[-1]); b = [pb[n].matrix.copy() for n in ARM]
        closure = max((x.to_3x3().to_quaternion().rotation_difference(y.to_3x3().to_quaternion()).angle for x, y in zip(a, b)), default=0)
        info = dict(clip=action.name, source=cfg['source'], frames=len(frames), duration_seconds=(len(frames) - 1) / FPS,
                    settings={k: v for k, v in cfg.items() if k != 'source'},
                    min_clearance_cm=min(r['clearance_cm'] for r in out), min_tip_height_cm=min(r['tip_height_cm'] for r in out),
                    max_wrist_bend_degrees=max(r['wrist_bend'] for r in out), max_forearm_turn_degrees=max(r['forearm_turn'] for r in out),
                    blade_pitch_range=[min(r['final'][0] for r in out), max(r['final'][0] for r in out)],
                    blade_yaw_range=[min(r['final'][1] for r in out), max(r['final'][1] for r in out)],
                    wrist_out_cm=[min(r['wrist_out_cm'] for r in out), max(r['wrist_out_cm'] for r in out)],
                    elbow_out_cm=[min(r['elbow_out_cm'] for r in out), max(r['elbow_out_cm'] for r in out)],
                    loop_closure_degrees=round(math.degrees(closure), 3), per_frame=out)
        print('CLIP', role, {k: v for k, v in info.items() if k not in ('per_frame', 'settings')}, flush=True)
        return info

    # ---------------------------------------------------------------- the carry held through jumps, falls, dashes and crouching
    AIR = ['JumpStart · library', 'JumpRise · library', 'DoubleJump · library', 'Fall · library', 'Land · library', 'HardLand · library',
           'DashAir · library', 'DashGround · library', 'CrouchIdle · library', 'CrouchWalk · library']

    def build_carry(self):
        """One-handed hold for every non-locomotion clip: the guard's right hand (where it holds the sword in front of the
        belly, blade forward), placed relative to the chest of the forward-facing idle. The guard's own arm on a
        forward-facing body put the sword upright at the right shoulder (the guard stance turns the torso)."""
        pb = self.arm.pose.bones; chest = P + 'Spine2'
        set_clip(self.arm, bpy.data.actions['SwordIdle · library']); self.scene.frame_set(1)
        C, E, W = pb[chest].head.copy(), pb[ARM[1]].head.copy(), pb[ARM[2]].head.copy(); H = self.world(ARM[2])
        guard_bend = math.degrees(pb[ARM[2]].rotation_quaternion.angle)
        src = bpy.data.actions['Idle · library']; set_clip(self.arm, src); self.scene.frame_set(1)
        pose = {b.name: (b.location.copy(), b.rotation_quaternion.copy()) for b in pb if b.rotation_mode == 'QUATERNION'}
        self.arm.animation_data.action = None
        for name, (loc, q) in pose.items(): pb[name].location = loc; pb[name].rotation_quaternion = q
        for k, v in self.grip.items(): pb[ARM[2]][k] = v
        bpy.context.view_layer.update()
        c = pb[chest].head.copy(); Wt = c + (W - C)
        # the blade straight ahead of the centre line, palm toward the body (the guard's own hand angle points it 26 deg out)
        bt = direction(*CARRY_BLADE)
        hold = self.ik_hold(Wt, c + (E - C), bt, (-RIGHT - bt * (-RIGHT).dot(bt)).normalized()); self.hold = hold
        # the roll: hand out at the right side of the lower ribs, palm up, blade pointing out along the axis the body turns about
        self.roll_hold = self.ik_hold(c + (FORWARD * .05 + RIGHT * .15 - UP * .10), c + (RIGHT * .16 - UP * .02 - FORWARD * .06), RIGHT, UP)
        for n, q in hold.items(): pb[n].rotation_quaternion = q
        bpy.context.view_layer.update()
        b0, b1 = self.blade(); d = (b1 - b0).normalized()
        info = dict(clip='SwordCarry · armed', source='Idle · library', frames=int(src.frame_range[1] - src.frame_range[0] + 1),
                    duration_seconds=(src.frame_range[1] - src.frame_range[0]) / FPS, blade=[round(v, 1) for v in pitch_yaw(d)],
                    wrist_bend_degrees=round(math.degrees(pb[ARM[2]].rotation_quaternion.angle), 1), guard_wrist_bend_degrees=round(guard_bend, 1),
                    wrist_error_cm=round((pb[ARM[2]].head - Wt).length * UNIT_CM, 2),
                    wrist_out_cm=round((pb[ARM[2]].head - pb[P + 'Hips'].head).dot(RIGHT) * UNIT_CM, 1))
        # clearance over every clip that shows this hold
        worst = {}
        for name in self.AIR:
            a = bpy.data.actions[name]; set_clip(self.arm, a); f0, f1 = map(int, a.frame_range); low = (1e9, 0)
            for f in range(f0, f1 + 1, 2):
                self.scene.frame_set(f)
                for n, q in hold.items(): pb[n].rotation_quaternion = q
                bpy.context.view_layer.update()
                low = min(low, (self.clearance(self.body_tree()), f))
            worst[name] = [round(low[0] * UNIT_CM, 1), low[1]]
        info['clearance_cm_by_clip'] = worst
        action = src.copy(); action.name = info['clip']; action.use_fake_user = True
        drop = [f'pose.bones["{n}"].rotation_quaternion' for n in ARM] + [f'pose.bones["{ARM[2]}"]["{k}"]' for k in HAND_PROPS]
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in [fc for fc in bag.fcurves if fc.data_path in drop]: bag.fcurves.remove(fc)
        set_clip(self.arm, action)
        f0, f1 = map(int, src.frame_range)
        for f in (f0, f1):
            for n in ARM: pb[n].rotation_quaternion = hold[n]; pb[n].keyframe_insert('rotation_quaternion', frame=f, group=n)
            for k in HAND_PROPS: pb[ARM[2]][k] = self.grip[k]; pb[ARM[2]].keyframe_insert(f'["{k}"]', frame=f, group=ARM[2] + ' · grip')
        print('CLIP SwordCarry', {k: v for k, v in info.items()}, flush=True)
        return info

    # ---------------------------------------------------------------- armed versions of the tumbling clips
    # role: (source, arm) — 'own' keeps the clip's own right arm (the jump's arm movement, fist closed on the grip);
    # 'roll' holds the carry and moves the hand to the side through the dive.
    VARIANTS = {'SwordJumpStart': ('JumpStart · library', 'own'), 'SwordJumpRise': ('JumpRise · library', 'own'),
                'SwordDoubleJump': ('DoubleJump · library', 'own'), 'SwordFall': ('Fall · library', 'own'),
                'SwordLand': ('Land · library', 'own'), 'SwordHardLand': ('HardLand · library', 'own'),
                'SwordDashAir': ('DashAir · library', 'own'), 'SwordDashGround': ('DashGround · library', 'own'),
                'SwordCrouchIdle': ('CrouchIdle · library', 'own'), 'SwordCrouchWalk': ('CrouchWalk · library', 'own'),
                'SwordSitDown': ('SitDown · library', 'own'), 'SwordSitIdle': ('SitIdle · library', 'own'), 'SwordStandUp': ('StandUp · library', 'own'),
                'SwordRoll': ('Roll · library', ROLL_MODE)}
    VARIANT_CLEARANCE = .025             # 3.7 cm from the clothes, head and floor

    def clear_score(self, tree):
        b0, b1 = self.blade(); pts = [b0.lerp(b1, t / 12) for t in range(2, 13)]
        return min(min(tree.find_nearest(p)[3] for p in pts), min(p.z for p in pts) - FLOOR)

    def build_variant(self, role, source, mode):
        """The clip with the sword in the right hand: its own arm movement ('own', fist closed on the grip) or the carry
        hold moving to the side through a roll ('roll'). Where the blade would meet the body or the floor, the forearm
        turns the fist (up to 120 deg) and the wrist tips the blade (up to 30 deg): the smallest consistent turn that
        clears it along the clip."""
        pb = self.arm.pose.bones; src = bpy.data.actions[source]; f0, f1 = map(int, src.frame_range); frames = list(range(f0, f1 + 1))
        loop = any(r['clip'] == source and r.get('loop') for r in self.record['roles'])
        set_clip(self.arm, src); poses = []
        for f in frames:
            self.scene.frame_set(f); poses.append({b.name: (b.location.copy(), b.rotation_quaternion.copy()) for b in pb if b.rotation_mode == 'QUATERNION'})
        self.arm.animation_data.action = None
        for k, v in self.grip.items(): pb[ARM[2]][k] = v

        # the roll moves the hand to the roll hold while the torso tips past 35 deg (and back as it rises)
        tilt = []
        for i in range(len(frames)):
            for name, (loc, q) in poses[i].items(): pb[name].location = loc; pb[name].rotation_quaternion = q
            bpy.context.view_layer.update()
            tilt.append(math.degrees((self.world(P + 'Spine2') @ Vector((0, 1, 0))).angle(UP)))
        if mode == 'roll':
            raw = np.array([smooth01((t - 35.) / 30.) for t in tilt]); win = 6
            w = gaussian_open(np.array([[max(raw[max(0, i - win):i + win + 1])] for i in range(len(raw))]), 2.5)[:, 0]
        else: w = np.zeros(len(frames))

        def pose(i, turn=(0., 0.)):
            for name, (loc, q) in poses[i].items(): pb[name].location = loc; pb[name].rotation_quaternion = q
            if mode != 'own':
                for n, q in self.hold.items():
                    r = self.roll_hold[n]; pb[n].rotation_quaternion = q.slerp(r if r.dot(q) >= 0 else -r, float(w[i]))
            bpy.context.view_layer.update()
            if turn != (0., 0.):
                fore = (pb[ARM[2]].head - pb[ARM[1]].head).normalized(); H0 = self.world(ARM[2]); F0 = self.world(ARM[1])
                Rf = Matrix.Rotation(math.radians(turn[0]), 3, fore); palm = Rf @ (H0 @ Vector((1, 0, 0)))
                self.set_world(ARM[1], Rf @ F0)
                self.set_world(ARM[2], Matrix.Rotation(math.radians(turn[1]), 3, palm) @ Rf @ H0)
        # One path through the clip over a grid of (forearm turn, wrist tip): each frame pays for blade contact, for turning
        # at all and for changing the turn since the previous frame (dynamic programming), so the correction stays
        # consistent through a tuck. Candidate blades are the frame's blade rotated about the wrist, without reposing.
        # the roll plants the sword hand on the floor: it gets the full forearm turn and a deeper wrist tip
        turn, tip = (180, 45) if role == 'SwordRoll' else (120, 30)
        grid = [(a, b) for a in range(-turn, turn + 1, 10) for b in range(-tip, tip + 1, 5 if tip > 30 else 10)]
        unary = []
        for i in range(len(frames)):
            pose(i); tree = self.body_tree()
            Wp = pb[ARM[2]].head.copy(); fore = (Wp - pb[ARM[1]].head).normalized(); palm0 = self.world(ARM[2]) @ Vector((1, 0, 0))
            b0, b1 = self.blade(); pts = [b0.lerp(b1, t / 12) - Wp for t in range(2, 13)]
            row = []
            for a, b in grid:
                Rf = Matrix.Rotation(math.radians(a), 3, fore); R = Matrix.Rotation(math.radians(b), 3, Rf @ palm0) @ Rf
                q = [Wp + R @ v for v in pts]
                c = min(min(tree.find_nearest(x)[3] for x in q), min(x.z for x in q) - FLOOR)
                row.append(.02 * (abs(a) + 1.5 * abs(b)) + 1e5 * max(0., self.VARIANT_CLEARANCE - c))
            unary.append(np.array(row))
        G = np.array(grid, float); move = .3 * (np.abs(G[:, None, 0] - G[None, :, 0]) + 1.5 * np.abs(G[:, None, 1] - G[None, :, 1]))
        cost = unary[0].copy(); back = []
        for i in range(1, len(frames)):
            total = cost[:, None] + move; k = total.argmin(0); back.append(k); cost = total[k, np.arange(len(grid))] + unary[i]
        path = [int(cost.argmin())]
        for k in reversed(back): path.append(int(k[path[-1]]))
        path.reverse(); choice = [grid[k] for k in path]
        # hold each turn two frames either side, so the smoothing eases in and out around the contact, not across it
        mag = [abs(c[0]) + 1.5 * abs(c[1]) for c in choice]
        choice = [choice[max(range(max(0, i - 2), min(len(choice), i + 3)), key=lambda j: mag[j])] for i in range(len(choice))]
        turns = gaussian_open(np.array(choice, float), .8)
        solved = {n: [] for n in ARM}; rows = []
        for i, f in enumerate(frames):
            pose(i, tuple(turns[i])); tree = self.body_tree()
            for n in ARM: solved[n].append(pb[n].rotation_quaternion.copy())
            b0, b1 = self.blade()
            rows.append(dict(frame=f, roll_hold=round(float(w[i]), 2), turn=[round(float(t), 1) for t in turns[i]], raw=list(choice[i]), clearance_cm=round(self.clear_score(tree) * UNIT_CM, 1),
                             hand_clear_cm=round(tree.find_nearest(pb[ARM[2]].head)[3] * UNIT_CM, 1), tip_floor_cm=round((b1.z - FLOOR) * UNIT_CM, 1)))
        action = src.copy(); action.name = role + ' · armed'; action.use_fake_user = True
        drop = [f'pose.bones["{n}"].rotation_quaternion' for n in ARM] + [f'pose.bones["{ARM[2]}"]["{k}"]' for k in HAND_PROPS]
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in [fc for fc in bag.fcurves if fc.data_path in drop]: bag.fcurves.remove(fc)
        set_clip(self.arm, action)
        for i, f in enumerate(frames):
            for n in ARM:
                q = solved[n][i]
                if i and q.dot(solved[n][i - 1]) < 0: q.negate()
                pb[n].rotation_quaternion = q; pb[n].keyframe_insert('rotation_quaternion', frame=f, group=n)
        for k in HAND_PROPS:
            for f in (f0, f1): pb[ARM[2]][k] = self.grip[k]; pb[ARM[2]].keyframe_insert(f'["{k}"]', frame=f, group=ARM[2] + ' · grip')
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for fc in bag.fcurves:
                        if fc.data_path in drop:
                            for k in fc.keyframe_points: k.interpolation = 'LINEAR'
                            if loop and not fc.modifiers: fc.modifiers.new('CYCLES')
        self.scene.frame_set(f0); a0 = [pb[n].matrix.to_quaternion() for n in ARM]
        self.scene.frame_set(f1); a1 = [pb[n].matrix.to_quaternion() for n in ARM]
        info = dict(clip=action.name, source=source, arm=mode, loop=loop,
                    loop_closure_degrees=round(max(math.degrees(x.rotation_difference(y).angle) for x, y in zip(a0, a1)), 2) if loop else None, frames=len(frames), duration_seconds=(len(frames) - 1) / FPS,
                    min_clearance_cm=min(r['clearance_cm'] for r in rows), max_turn=[max(abs(r['turn'][0]) for r in rows), max(abs(r['turn'][1]) for r in rows)],
                    per_frame=rows)
        print('CLIP', role, {k: v for k, v in info.items() if k != 'per_frame'}, flush=True)
        return info

    def ik_hold(self, Wt, Ep, blade, palm):
        """Arm rotations (local) reaching wrist target Wt, elbow toward Ep, the blade along `blade` with the palm facing `palm`."""
        pb = self.arm.pose.bones; S = pb[ARM[0]].head.copy()
        En = self.two_bone(S, Wt, Ep); upper_R = self.world(ARM[0])
        self.set_world(ARM[0], (upper_R @ Vector((0, 1, 0))).rotation_difference((En - S).normalized()).to_matrix() @ upper_R)
        fore_R = self.world(ARM[1]); fore = (Wt - pb[ARM[1]].head).normalized()
        self.set_world(ARM[1], (fore_R @ Vector((0, 1, 0))).rotation_difference(fore).to_matrix() @ fore_R)
        palm = (palm - blade * palm.dot(blade)).normalized(); bl = self.blade_in_hand; xl = (Vector((1, 0, 0)) - bl * bl.x).normalized()
        H = Matrix((palm, blade.cross(palm), blade)).transposed() @ Matrix((xl, bl.cross(xl), bl))
        # the forearm's roll follows the hand so the wrist bends without twisting
        roll_R = H @ self.rest_rel[ARM[2]].inverted(); roll_R = (roll_R @ Vector((0, 1, 0))).rotation_difference(fore).to_matrix() @ roll_R
        self.set_world(ARM[1], roll_R); self.set_world(ARM[2], H)
        return {n: pb[n].rotation_quaternion.copy() for n in ARM}

    def two_bone(self, S, Wt, Ep):
        """Elbow position for a shoulder-elbow-wrist chain reaching Wt, bending toward Ep."""
        pb = self.arm.pose.bones
        L1 = (pb[ARM[1]].head - pb[ARM[0]].head).length; L2 = (pb[ARM[2]].head - pb[ARM[1]].head).length
        d = min((Wt - S).length, (L1 + L2) * .999); axis = (Wt - S).normalized()
        a = (L1 * L1 - L2 * L2 + d * d) / (2 * d); h = math.sqrt(max(0., L1 * L1 - a * a))
        pole = (Ep - S) - axis * (Ep - S).dot(axis); pole.normalize()
        return S + axis * a + pole * h

    # ---------------------------------------------------------------- revision
    def save(self, clips):
        out = ASSET / self.rev; out.mkdir(exist_ok=True)
        (out / '.gitignore').write_text('diagnostics/\n*.blend1\n')
        for name, sig in self.library.items(): assert self.signature(bpy.data.actions[name]) == sig, name
        set_clip(self.arm, bpy.data.actions['Idle · library']); self.scene.frame_set(1)
        native = out / f'WarmOriginal-Game-{self.rev[5:]}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(native))
        record = self.record; roles = {r['role']: r for r in record['roles']}
        armed = {'SwordStand': 'Idle', 'SwordCarry': 'Idle', **{role: role[5:] for role in self.VARIANTS}}
        record['roles'] = [r for r in record['roles'] if r['role'] not in ('SwordWalk', 'SwordRun', 'SwordSprint', *armed)]
        for role in ('SwordWalk', 'SwordSprint', 'SwordRun'):
            base_role = {'SwordWalk': 'Walk', 'SwordSprint': 'Sprint', 'SwordRun': 'Run'}[role]
            info = clips['SwordSprint' if role == 'SwordRun' else role]; base = roles[base_role]
            row = {k: v for k, v in base.items() if k not in ('original_curve_signature',)}
            row.update(role=role, clip=info['clip'], sword=True, locomotion=True, weapon='bokken in the right hand',
                       mapping=f'shared: {info["clip"]} at 0.8x, as Run' if role == 'SwordRun' else f'armed copy of {base["clip"]}',
                       notes=f'{base["clip"]} with the right arm swinging the sword; played as the right-arm layer while armed')
            record['roles'].append(row)
        notes = {role: f'{role[5:]} with its own right-arm movement and the sword in the fist; the blade turns clear of the body and floor'
                 for role, (_, mode) in self.VARIANTS.items() if mode == 'own'}
        notes.update(SwordStand='Idle with the sword in the right hand (arm unchanged, fist closed on the grip); the armed standing pose',
                     SwordCarry='one-handed hold in front of the belly, blade forward; the right-arm layer over crouching and any clip without an armed copy',
                     SwordRoll='Roll with the sword kept: the hand moves to the right side (blade out along the roll axis) through the dive')
        for role, base_role in armed.items():
            info = clips[role]; base = roles[base_role]
            row = {k: v for k, v in base.items() if k not in ('original_curve_signature',)}
            row.update(role=role, clip=info['clip'], sword=True, weapon='bokken in the right hand', mapping=f'armed copy of {base["clip"]}', notes=notes[role])
            record['roles'].append(row)
        record.update(native=str(native.relative_to(ROOT)), native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                      parent_source=str(self.source.relative_to(ROOT)), parent_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
                      revision=self.rev, changed_actions=[i['clip'] for i in clips.values()], other_parent_actions_preserved=True)
        (out / 'source-manifest.json').write_text(json.dumps(record, indent=2) + '\n')
        build = json.loads((self.parent_dir / 'combat-build.json').read_text())
        (out / 'combat-build.json').write_text(json.dumps(build, indent=1) + '\n')
        self.report['clips'] = clips
        (out / 'locomotion-build.json').write_text(json.dumps(self.report, indent=1) + '\n')
        print('REVISION_READY', self.rev, native, flush=True)


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser(); ap.add_argument('--parent', default='game-r15'); ap.add_argument('--revision', default='game-r16')
    ap.add_argument('--dry', action='store_true', help='solve and report without saving a revision')
    a = ap.parse_args(argv)
    b = Builder(a.parent, a.revision)
    clips = {role: b.build_clip(role, cfg) for role, cfg in CLIPS.items()}
    clips['SwordCarry'] = b.build_carry()
    for role, (source, mode) in b.VARIANTS.items(): clips[role] = b.build_variant(role, source, mode)
    if not a.dry: b.save(clips)

