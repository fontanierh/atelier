"""Retarget Link's Breath of the Wild clips onto Cairo, for Cairo's move set (assets/characters/botw/README.md).

    blender -b --python games/yorimichi/assets/characters/cairo/botw.py [-- --clips Nml_Wait,Nml_Move_Run]
    blender -b --python games/yorimichi/assets/characters/cairo/botw.py -- --character sword-trainer
    blender -b --python games/yorimichi/assets/characters/cairo/botw.py -- --dump-own   # Cairo's own clips, for the next

The same retarget gives any character on the humanoid contract the merged move set: `--character sword-trainer` reads
Kaede's source (sword-trainer/export_unreal.prepare) and writes build/yorimichi/sword-trainer/botw/. A character other
than Cairo also takes Cairo's own clips in the merged set (OWN_CLIPS: his double jump, his two-handed guard, parry and
recoil), from build/yorimichi/cairo/botw/own.npz, which `--dump-own` writes from Cairo's source: the same retarget with
Cairo in Link's place (bone for bone, at 60 fps, his clips' rate).

Reads Link's baked clips (build/yorimichi/botw/glb/Link.glb and export.json, from botw/export.py) and Cairo's source
(export_unreal.prepare), and writes build/yorimichi/cairo/botw/: fbx/A_<Clip>.fbx for each of Link's clips, on Cairo's
skeleton at 30 fps, and export.json: the clips, Cairo's body scale against Link's, and per clip how far the solved
ankles and hips sit from where they were asked to be.

Both rest poses are T-poses. Each Cairo bone takes its Link bone's turn from rest, carried into Cairo's frame: a limb or
finger is first swung to point where Link's points, a hand keeps its palm frame and a foot its sole frame, and the
spine, neck and head keep Cairo's own rest posture (spine_mid takes half of the turn from spine to chest). The hips
move as Link's do, scaled by the ratio of the two hip heights (`body`, about 0.64). The legs are then solved so each
ankle goes where Link's does: near the ground, Link's ankle travel at that same scale from Cairo's own stance, so
planted feet stay planted and the stride matches the move set's scaled speeds; high off the ground (a jump's tuck,
swimming, gliding, climbing), where Cairo's own leg reaches bent as Link's is.
"""
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'botw'))
import export_unreal as cairo   # noqa: E402  (also puts the world folder, and yori, on the path)
import bake   # noqa: E402
import yori   # noqa: E402

LINK = yori.OUT / 'botw'
OUT = yori.OUT / 'cairo' / 'botw'
OWN = OUT / 'own.npz'   # Cairo's own clips in the merged set, sampled for other characters (--dump-own)
FPS = bake.FPS
# Cairo's clips the merged set plays on him (import_cairo_botw.py: DoubleJump and OWN), by role, at their 60 fps.
OWN_CLIPS = ('DoubleJump', 'SwordIdle', 'SwordParry', 'SwordParryHit')
OWN_FPS = 60
GLTF_TO_BLENDER = np.array([[1., 0, 0], [0, 0, -1], [0, 1, 0]])   # glTF is Y up, Blender Z up
# The bones that keep Cairo's own rest posture (no swing onto Link's directions).
POSTURE = ('pelvis', 'spine', 'spine_mid', 'chest', 'neck', 'head')
# The bone after each limb or finger bone, which gives its direction; an end bone takes its parent's swing.
NEXT = {'clavicle': 'upperarm', 'upperarm': 'forearm', 'forearm': 'hand', 'thigh': 'shin', 'shin': 'foot',
        'thumb': 'thumb_tip', 'thumb_tip': 'thumb_end',
        **{f'finger_{i}': f'finger_tip_{i}' for i in range(4)}, **{f'finger_tip_{i}': f'finger_end_{i}' for i in range(4)}}
# Ankles further than this from their rest height (metres, Link's) follow the leg's shape rather than the ground:
# a tuck, or a whole body lowered to swim or hang on a wall.
GROUND = (.25, .5)


# --- Link's clips -------------------------------------------------------------------------------------------------

class Glb:
    """Link's baked GLB: its nodes' rest transforms and each clip's per-frame local rotations and translations."""

    def __init__(self, path):
        self.gltf, self.binary = bake.read_glb(path)
        self.nodes = self.gltf['nodes']
        self.index = {node.get('name'): i for i, node in enumerate(self.nodes)}
        self.parent = {child: i for i, node in enumerate(self.nodes) for child in node.get('children', [])}
        self.clips = {anim['name']: anim for anim in self.gltf['animations']}

    def read(self, accessor):
        a = self.gltf['accessors'][accessor]
        view = self.gltf['bufferViews'][a['bufferView']]
        width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[a['type']]
        start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        return np.frombuffer(bytes(self.binary[start:start + a['count'] * width * 4]), '<f4').reshape(a['count'], width).astype(np.float64)

    def chain(self, names):
        """The nodes of `names` and all their ancestors, parents first."""
        wanted = set()
        for name in names:
            i = self.index[name]
            while True:
                wanted.add(i)
                if i not in self.parent:
                    break
                i = self.parent[i]
        order, seen = [], set()
        def visit(i):
            if i in seen:
                return
            if i in self.parent:
                visit(self.parent[i])
            seen.add(i); order.append(i)
        for i in sorted(wanted):
            visit(i)
        return order

    def rest(self, order):
        """World matrices (glTF space) of `order`'s nodes at rest."""
        world = {}
        for i in order:
            n = self.nodes[i]
            local = bake.compose(np.array(n.get('translation', [0., 0, 0]))[None], np.array(n.get('rotation', [0., 0, 0, 1]))[None],
                                 np.array(n.get('scale', [1., 1, 1]))[None])[0]
            world[i] = (world[self.parent[i]] if i in self.parent else np.eye(4)) @ local
        return world

    def sample(self, clip, order, frames):
        """World matrices (frames, 4, 4) of `order`'s nodes over the clip's frames 0..frames."""
        anim = self.clips[clip]
        times = np.arange(frames + 1) / FPS
        tracks = {}
        for channel in anim['channels']:
            sampler = anim['samplers'][channel['sampler']]
            keys, values = self.read(sampler['input'])[:, 0], self.read(sampler['output'])
            tracks[(channel['target']['node'], channel['target']['path'])] = (keys, values)
        def at(node, path, default):
            if (node, path) not in tracks:
                return np.repeat(np.array(default, np.float64)[None], len(times), 0)
            keys, values = tracks[(node, path)]
            if len(keys) == len(times) and np.allclose(keys, times, atol=1e-4):
                out = values.copy()
            else:   # LINEAR between keys (a rotation's lerp is renormalised)
                out = np.stack([np.interp(times, keys, values[:, k]) for k in range(values.shape[1])], 1)
            if path == 'rotation':
                out /= np.linalg.norm(out, axis=1, keepdims=True)
            return out
        world = {}
        for i in order:
            n = self.nodes[i]
            local = bake.compose(at(i, 'translation', n.get('translation', [0., 0, 0])), at(i, 'rotation', n.get('rotation', [0., 0, 0, 1])),
                                 np.repeat(np.array(n.get('scale', [1., 1, 1]))[None], len(times), 0))
            world[i] = (world[self.parent[i]] if i in self.parent else np.eye(4)[None]) @ local
        return world


class Own:
    """Cairo's own clips as a source with Glb's interface: his bones' world matrices at rest and per frame, stored in
    glTF's axes (the retarget turns every source into Blender's), named by the contract."""

    def __init__(self, path):
        data = np.load(path)
        self.names = [str(n) for n in data['names']]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.rest_world = data['rest']
        self.clips = {str(c): data['clip_' + str(c)] for c in data['clips']}

    def chain(self, names):
        return [self.index[n] for n in names]

    def rest(self, order):
        return {i: self.rest_world[i] for i in order}

    def sample(self, clip, order, frames):
        world = self.clips[clip]
        return {i: world[:frames + 1, i] for i in order}


def dump_own():
    """Sample Cairo's own clips (OWN_CLIPS) as world matrices of his contract bones, in glTF's axes, into OWN."""
    prepared = cairo.prepare(cairo.SOURCE)
    scene, arm = prepared.scene, prepared.arm
    roles = {r['role']: r['clip'] for r in prepared.record['roles']}
    names = [b.name for b in arm.data.bones]
    to_gltf = np.eye(4); to_gltf[:3, :3] = GLTF_TO_BLENDER.T
    A = np.array(arm.matrix_world)
    arm.animation_data_create()
    arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    bpy.context.view_layer.update()
    rest = np.stack([to_gltf @ A @ np.array(arm.data.bones[n].matrix_local) for n in names])
    out = {'names': np.array(names), 'rest': rest, 'clips': np.array(OWN_CLIPS)}
    for role in OWN_CLIPS:
        action = bpy.data.actions[roles[role]]
        cairo.set_clip(arm, action)
        start, end = map(int, action.frame_range)
        frames = []
        for f in range(start, end + 1):
            scene.frame_set(f)
            frames.append(np.stack([to_gltf @ A @ np.array(arm.pose.bones[n].matrix) for n in names]))
        out['clip_' + role] = np.stack(frames)
        print('CAIRO OWN CLIP', role, len(frames), 'frames', flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OWN, **out)
    print('CAIRO OWN DUMP COMPLETE', OWN, flush=True)


# --- Rotation helpers ---------------------------------------------------------------------------------------------

def unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def frame(y, z):
    """Right-handed rotation whose Y axis is y and whose Z axis is z made perpendicular to it (columns x, y, z)."""
    y = unit(y)
    z = unit(z - y * np.sum(z * y, -1, keepdims=True))
    return np.stack([np.cross(y, z), y, z], -1)


def swing(a, b):
    """The shortest rotation taking direction a onto direction b (both (..., 3))."""
    a, b = unit(a), unit(b)
    axis = np.cross(a, b)
    s, c = np.linalg.norm(axis, axis=-1), np.sum(a * b, -1)
    k = np.where(s[..., None] > 1e-9, axis / np.maximum(s, 1e-12)[..., None], 0.)
    K = np.zeros(k.shape[:-1] + (3, 3))
    K[..., 0, 1], K[..., 0, 2], K[..., 1, 0] = -k[..., 2], k[..., 1], k[..., 2]
    K[..., 1, 2], K[..., 2, 0], K[..., 2, 1] = -k[..., 0], -k[..., 1], k[..., 0]
    return np.eye(3) + s[..., None, None] * K + (1 - c)[..., None, None] * (K @ K)


def quats(m):
    """Quaternions (w, x, y, z) of rotation matrices (..., 3, 3), each frame's sign continuous with the last."""
    q = bake.quat_from_matrices(m.reshape(-1, 3, 3))   # x, y, z, w
    q = np.concatenate([q[:, 3:], q[:, :3]], 1)
    for i in range(1, len(q)):
        if np.dot(q[i], q[i - 1]) < 0:
            q[i] = -q[i]
    return q


def slerp_half(a, b):
    """The rotation halfway from a to b (both (frames, 3, 3))."""
    qa, qb = quats(a), quats(b)
    qb = np.where(np.sum(qa * qb, 1, keepdims=True) < 0, -qb, qb)
    q = unit(qa + qb)
    w, x, y, z = q.T
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], 1)


def smoothstep(a, b, v):
    t = np.clip((v - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


# --- The retarget -------------------------------------------------------------------------------------------------

class Retarget:
    def __init__(self, glb, arm, bone_map):
        self.glb, self.arm = glb, arm
        self.map = {bone: source for bone, source in bone_map.items() if source}
        self.order = glb.chain(self.map.values())
        A = np.array(arm.matrix_world)
        self.arm_scale = float(np.linalg.norm(A[:3, 0]))
        bones = arm.data.bones
        depth = lambda b: 0 if b.parent is None else 1 + depth(b.parent)
        self.bones = [b.name for b in sorted(bones, key=depth)]   # parents first
        self.parent = {b.name: b.parent.name if b.parent else None for b in bones}
        # Cairo at rest, in Blender's world (metres): each bone's rotation and head.
        self.rest_rot = {b.name: np.array(b.matrix_local.to_3x3().normalized()) for b in bones}
        self.rest_pos = {b.name: (A @ np.append(np.array(b.head_local), 1.))[:3] for b in bones}
        # Link at rest, turned into Blender's axes.
        world = glb.rest(self.order)
        self.src_rest_rot = {name: GLTF_TO_BLENDER @ world[glb.index[name]][:3, :3] for name in self.map.values()}
        self.src_rest_pos = {name: GLTF_TO_BLENDER @ world[glb.index[name]][:3, 3] for name in self.map.values()}
        s, t = self.src_rest_pos, self.rest_pos
        # C turns Link's facing into Cairo's: both bodies' (forward, left, up) frames, with the world's up.
        def body(left):
            left = left * np.array([1., 1, 0])
            up = np.array([0., 0, 1])
            return np.stack([unit(np.cross(left, up)), unit(left), up], 1)
        self.C = body(t['upperarm_L'] - t['upperarm_R']) @ body(s[self.map['upperarm_L']] - s[self.map['upperarm_R']]).T
        floor = 0.
        self.body = (t['pelvis'][2] - floor) / (s[self.map['pelvis']][2] - floor)
        # Each bone's rest calibration X: Cairo's bone turns by C S_t S_r^-1 X T_r.
        C, Ci = self.C, self.C.T
        self.X = {}
        hand = lambda rig, side, names: frame(rig[names['finger_0']] * .5 + rig[names['finger_3']] * .5 - rig[names['hand']],
                                              rig[names['finger_3']] - rig[names['finger_0']])
        foot = lambda rig, names, up: frame(rig[names['toe']] - rig[names['foot']], up)
        for side in 'LR':
            own = {k: f'{k}_{side}' for k in ('hand', 'finger_0', 'finger_3', 'foot', 'toe')}
            link = {k: self.map[v] for k, v in own.items()}
            self.X[f'hand_{side}'] = hand(s, side, link) @ hand(t, side, own).T
            feet = foot(s, link, np.array([0., 0, 1])) @ foot(t, own, np.array([0., 0, 1])).T
            self.X[f'foot_{side}'] = self.X[f'toe_{side}'] = feet
        for bone in self.map:
            if bone in self.X or bone in POSTURE:
                continue
            base, side = bone[:-2], bone[-2:]
            nxt = NEXT.get(base)
            if nxt is None:   # an end bone: its parent's swing
                continue
            child = nxt + side
            Q = swing(t[child] - t[bone], C @ (s[self.map[child]] - s[self.map[bone]]))
            self.X[bone] = Ci @ Q
        for bone in self.map:
            if bone not in self.X and bone not in POSTURE:
                self.X[bone] = self.X[self.parent[bone]]
        for bone in POSTURE:
            self.X[bone] = Ci
        self.leg = {side: (np.linalg.norm(t[f'shin_{side}'] - t[f'thigh_{side}']), np.linalg.norm(t[f'foot_{side}'] - t[f'shin_{side}']))
                    for side in 'LR'}

    def clip(self, name, frames):
        """Cairo's pose over the clip: (rotations, pelvis location, checks); rotations[bone] is (frames+1, 4) w,x,y,z
        of the bone's pose (Blender's basis), the location is the pelvis's (armature units, its rest frame)."""
        world = self.glb.sample(name, self.order, frames)
        n = frames + 1
        src_rot = {s: GLTF_TO_BLENDER @ world[self.glb.index[s]][:, :3, :3] for s in self.map.values()}
        src_pos = {s: world[self.glb.index[s]][:, :3, 3] @ GLTF_TO_BLENDER.T for s in self.map.values()}
        C = self.C
        rot = {}
        for bone, source in self.map.items():
            rot[bone] = C @ src_rot[source] @ self.src_rest_rot[source].T @ self.X[bone] @ self.rest_rot[bone]
        # spine_mid: half the turn from spine to chest, applied to its own rest
        turn = lambda bone: rot[bone] @ self.rest_rot[bone].T
        rot['spine_mid'] = slerp_half(turn('spine'), turn('chest')) @ self.rest_rot['spine_mid']
        rot['root'] = np.repeat(self.rest_rot['root'][None], n, 0)
        # Forward kinematics (heads in metres), the hips first.
        pos = {'root': np.repeat(self.rest_pos['root'][None], n, 0)}
        pelvis = self.map['pelvis']
        pos['pelvis'] = self.rest_pos['pelvis'] + (src_pos[pelvis] - self.src_rest_pos[pelvis]) @ C.T * self.body
        def place(bone):
            p = self.parent[bone]
            offset = self.rest_rot[p].T @ (self.rest_pos[bone] - self.rest_pos[p])
            pos[bone] = pos[p] + rot[p] @ offset
        for bone in self.bones:
            if bone not in pos:
                place(bone)
        checks = {}
        for side in 'LR':
            thigh, shin, foot = f'thigh_{side}', f'shin_{side}', f'foot_{side}'
            link_ankle = self.map[foot]
            rise = src_pos[link_ankle][:, 2] - self.src_rest_pos[link_ankle][2]
            ground = self.rest_pos[foot] + (src_pos[link_ankle] - self.src_rest_pos[link_ankle]) @ C.T * self.body
            w = (1 - smoothstep(*GROUND, np.abs(rise)))[:, None]
            goal = w * ground + (1 - w) * pos[foot]
            hip, knee0 = pos[thigh], pos[shin]
            l1, l2 = self.leg[side]
            reach = goal - hip
            d = np.clip(np.linalg.norm(reach, axis=1), abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4)
            axis = unit(reach)
            bend = knee0 - hip
            pole = bend - axis * np.sum(bend * axis, 1, keepdims=True)
            pole = unit(np.where(np.linalg.norm(pole, axis=1, keepdims=True) > 1e-6, pole, rot['pelvis'][:, :, 0]))
            along = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
            knee = hip + axis * along[:, None] + pole * np.sqrt(np.maximum(0, l1 * l1 - along * along))[:, None]
            ankle = hip + axis * d[:, None]
            turn_thigh = swing(knee0 - hip, knee - hip)
            rot[thigh] = turn_thigh @ rot[thigh]
            shin_now = np.einsum('fij,fj->fi', turn_thigh, pos[foot] - knee0)
            rot[shin] = swing(shin_now, ankle - knee) @ turn_thigh @ rot[shin]
            pos[shin], pos[foot] = knee, ankle
            pos[f'toe_{side}'] = ankle + rot[foot] @ (self.rest_rot[foot].T @ (self.rest_pos[f'toe_{side}'] - self.rest_pos[foot]))
            checks[f'ankle_{side}_cm'] = round(float(np.max(np.linalg.norm(ankle - goal, axis=1))) * 100, 2)
            checks[f'ground_{side}'] = round(float(np.mean(w)), 3)
        # Pose (basis) rotations: (parent rest^-1 bone rest)^-1 (parent pose^-1 bone pose).
        basis = {}
        for bone in self.bones:
            p = self.parent[bone]
            prest = self.rest_rot[p] if p else np.eye(3)
            ppose = rot[p] if p else np.eye(3)[None]
            local_rest = prest.T @ self.rest_rot[bone]
            basis[bone] = quats(local_rest.T @ np.swapaxes(ppose, -1, -2) @ rot[bone])
        location = (pos['pelvis'] - self.rest_pos['pelvis']) @ self.rest_rot['pelvis'] / self.arm_scale
        checks['lowest_toe_cm'] = round(float(min(pos[f'toe_{s}'][:, 2].min() for s in 'LR')) * 100, 2)
        return basis, location, checks


def write_action(arm, name, basis, location):
    action = bpy.data.actions.new(name)
    arm.animation_data_create()
    arm.animation_data.action = action
    frames = np.arange(len(location), dtype=np.float64)
    def curve(path, index, values):
        fc = action.fcurve_ensure_for_datablock(arm, path, index=index)
        fc.keyframe_points.add(len(values))
        fc.keyframe_points.foreach_set('co', np.stack([frames, values], 1).ravel())
        fc.keyframe_points.foreach_set('interpolation', [1] * len(values))   # LINEAR
        fc.update()
    for bone, q in basis.items():
        pb = arm.pose.bones[bone]
        pb.rotation_mode = 'QUATERNION'
        for k in range(4):
            curve(f'pose.bones["{bone}"].rotation_quaternion', k, q[:, k])
    for k in range(3):
        curve('pose.bones["pelvis"].location', k, location[:, k])
    if arm.animation_data.action_slot is None:
        arm.animation_data.action_slot = action.slots[0]
    return action


def character(name):
    """The character's export module (its `prepare`, `SOURCE` and FBX settings) and its output folder."""
    if name == 'cairo':
        return cairo, OUT
    import importlib.util
    folder = HERE.parent / name
    spec = importlib.util.spec_from_file_location(f'{name.replace("-", "_")}_export', folder / 'export_unreal.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.OUT / 'botw'


def export_clip(scene, arm, out, name, frames, retarget, module, fps):
    basis, location, checks = retarget.clip(name, frames)
    action = write_action(arm, 'Botw · ' + name, basis, location)
    scene.render.fps, scene.render.fps_base = fps, 1
    scene.frame_start, scene.frame_end = 0, frames
    scene.frame_set(0)
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.export_scene.fbx(filepath=str(out / 'fbx' / f'A_{name}.fbx'), object_types={'ARMATURE'}, bake_anim=True, **module.FBX)
    bpy.data.actions.remove(action)
    print('BOTW CLIP', name, json.dumps(checks), flush=True)
    return checks


def main(args):
    if args.dump_own:
        return dump_own()
    module, out = character(args.character)
    export = json.loads((LINK / 'export.json').read_text())
    link = next(c for c in export['characters'] if c['name'] == 'Link')
    glb = Glb(link['glb'])
    prepared = module.prepare(module.SOURCE)
    scene, arm = prepared.scene, prepared.arm
    scene.render.fps, scene.render.fps_base = FPS, 1
    for pb in arm.pose.bones:
        pb.matrix_basis.identity()
    # Link's contract map, with the hips from Waist (the legs' parent) and spine_mid made from spine and chest.
    bone_map = {**link['skate'], 'root': '', 'spine_mid': '', 'pelvis': 'Waist'}
    missing = sorted(b.name for b in arm.data.bones if b.name not in bone_map)
    assert not missing, (f'{args.character} bones without a Link bone', missing)
    retarget = Retarget(glb, arm, bone_map)
    wanted = set(args.clips.split(',')) if args.clips else None
    (out / 'fbx').mkdir(parents=True, exist_ok=True)
    clips = {}
    for clip in link['clips']:
        name = clip['name']
        if wanted and name not in wanted:
            continue
        checks = export_clip(scene, arm, out, name, clip['frames'], retarget, module, FPS)
        clips[name] = {'frames': clip['frames'], 'duration': round(clip['frames'] / FPS, 4), 'loop': clip['loop'], 'fps': FPS, **checks}
    own = {}
    if args.character != 'cairo' and not wanted:
        # Cairo's own clips in the merged set, Cairo in Link's place: bone for bone, the hips at the two hip heights' ratio.
        assert OWN.exists(), f'{OWN} is missing: run botw.py -- --dump-own first'
        source = Own(OWN)
        own_retarget = Retarget(source, arm, {**{b.name: b.name for b in arm.data.bones}, 'root': '', 'spine_mid': ''})
        for name, world in source.clips.items():
            frames = len(world) - 1
            checks = export_clip(scene, arm, out, name, frames, own_retarget, module, OWN_FPS)
            own[name] = {'frames': frames, 'duration': round(frames / OWN_FPS, 4), 'fps': OWN_FPS, **checks}
        own_body = round(float(own_retarget.body), 4)
    report = {'character': args.character, 'source': prepared.native.name, 'source_sha256': prepared.record['native_sha256'], 'link': link['glb'],
              'fps': FPS, 'body': round(float(retarget.body), 4), 'link_scale': link['scale'],
              'alignment': np.round(retarget.C, 4).tolist(), 'clips': clips}
    if own:
        report.update(own=own, own_body=own_body, own_source=str(OWN))
    (out / ('export.json' if not wanted else 'export-partial.json')).write_text(json.dumps(report, indent=1) + '\n')
    print(f'BOTW EXPORT COMPLETE ({args.character}): {len(clips)} clips, {len(own)} of Cairo\'s, body {retarget.body:.3f}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--clips', help='comma-separated Link clips (default: all)')
    parser.add_argument('--character', default='cairo', help='the character folder to retarget onto (cairo, sword-trainer)')
    parser.add_argument('--dump-own', action='store_true', help="sample Cairo's own merged-set clips for other characters")
    main(parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []))
