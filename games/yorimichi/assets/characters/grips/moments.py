"""The grip poser's scenes, from a character's hands sampled in the game: each grip, its handle, its prop and every moment.

    uv run python games/yorimichi/assets/characters/grips/moments.py --character modori --samples SAMPLES.jsonl

SAMPLES.jsonl (or .jsonl.gz) holds sample.py's rows: the game's world-space joints and skin of both hands while they
hold the sword (the two-handed guard) or the glider, and the held prop's vertices (or the glider's handle axes). For each
grip (a prop and a hand) it writes, to build/yorimichi/grips/<character>/moments.json:

- the handle as the finger wrap sees it (FingerWrapNode.h): its usable span from A to B, its oval's radii at either end
  and at its waist, in a frame with A at the origin, the span along +x and the oval's major axis along +y;
- the prop's mesh placed in that frame (LinkSword.glb fitted to the game's vertices; LinkGlider.glb by its handles);
- each moment's hand: the hand bone's place in that frame, from the palm (the wrist, the index and the little finger's
  base joints; how the game held it, which the poser keeps while the fingers move), and the other hand's;
- the game's own finger pose at a typical moment, fitted to its joints and skin: the poser's starting pose, and its ghost.

Frames are glTF's (Y up, metres): a game point (x, y, z) in centimetres is (x, z, y) / 100 (export.py). Checks (how
closely the fitted hand's skin lies on the game's) go in the file's `checks`.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import itertools
import json
import struct
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402

DIGITS = [[f'finger_{f}_{{s}}', f'finger_tip_{f}_{{s}}', f'finger_end_{f}_{{s}}'] for f in range(4)] + \
         [['thumb_{s}', 'thumb_tip_{s}', 'thumb_end_{s}']]
# FingerWrapNode's handles (BotwMoveSetDetail.h): the glider's tubes in its own frame (cm, the game's axes) and their
# oval; the sword's grip in lengths of its handle (its origin to the pommel's end).
GLIDER_HANDLES = {'R': ((-24.8, -14.2, 1.2), (-30.5, 2.8, 1.1)), 'L': ((25.4, -14.2, 1.6), (30.1, 2.9, 1.0))}
GLIDER_RADII = (3.30, 2.80)
SWORD_SPAN = (.709, -.231)
SWORD_RADII = ((.125, .090), (.126, .076), (.113, .070))
SWORD_WAIST = .523
BEYOND = .02   # the wood past the usable span, then capped (m)
BOTW = yori.OUT / 'botw' / 'glb'


def from_game(p):
    """Game centimetres (Z up) to glTF metres (Y up)."""
    p = np.asarray(p, float)
    return np.stack([p[..., 0], p[..., 2], p[..., 1]], -1) / 100.


class Glb:
    def __init__(self, path):
        data = path.read_bytes()
        size = struct.unpack('<I', data[12:16])[0]
        self.json = json.loads(data[20:20 + size])
        start = 20 + size
        self.bin = data[start + 8:start + 8 + struct.unpack('<I', data[start:start + 4])[0]]

    def accessor(self, index):
        a = self.json['accessors'][index]
        view = self.json['bufferViews'][a['bufferView']]
        kind = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}[a['componentType']]
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        offset = view.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = view.get('byteStride', 0) or width * np.dtype(kind).itemsize
        rows = np.lib.stride_tricks.as_strided(np.frombuffer(self.bin, np.uint8, offset=offset),
                                               (a['count'], width * np.dtype(kind).itemsize), (stride, 1))
        return np.ascontiguousarray(rows).view(kind).reshape(a['count'], width).astype(float)

    def worlds(self):
        """Every node's world matrix (column vectors), by index."""
        nodes, out = self.json['nodes'], {}

        def local(n):
            M = np.eye(4)
            x, y, z, w = n.get('rotation', [0, 0, 0, 1])
            M[:3, :3] = rotation([x, y, z, w]) * np.asarray(n.get('scale', [1, 1, 1]))
            M[:3, 3] = n.get('translation', [0, 0, 0])
            return M

        def walk(i, parent):
            out[i] = parent @ local(nodes[i])
            for c in nodes[i].get('children', []):
                walk(c, out[i])
        children = {c for n in nodes for c in n.get('children', [])}
        for root in (i for i in range(len(nodes)) if i not in children):
            walk(root, np.eye(4))
        return out


def rotation(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def quaternion(R):
    """A rotation matrix's quaternion (x, y, z, w), w >= 0."""
    t = np.trace(R)
    if t > 0:
        s = np.sqrt(t + 1.) * 2
        q = [(R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s, .25 * s]
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = np.sqrt(1. + R[i, i] - R[j, j] - R[k, k]) * 2
        q = [0., 0., 0., (R[k, j] - R[j, k]) / s]
        q[i], q[j], q[k] = .25 * s, (R[j, i] + R[i, j]) / s, (R[k, i] + R[i, k]) / s
    q = np.array(q)
    return q * (1 if q[3] >= 0 else -1) / np.linalg.norm(q)


def similarity(X, Y):
    """Scale, rotation and translation taking points X onto Y (Umeyama), least squares."""
    mx, my = X.mean(0), Y.mean(0)
    U, S, Vt = np.linalg.svd((Y - my).T @ (X - mx) / len(X))
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    s = np.trace(np.diag(S) @ D) / ((X - mx) ** 2).sum(1).mean()
    return s, R, my - s * R @ mx


def fit_mesh(X, Y, iterations=40):
    """A mesh's vertices X placed onto a sampled copy Y (the game's own vertices, a different split): principal axes in
    each of their four sign choices, then iterative closest points; the placement with the least two-way error."""
    def axes(P):
        c = P.mean(0)
        return c, np.linalg.svd(P - c)[2]
    cx, vx = axes(X)
    cy, vy = axes(Y)
    best = None
    for a, b in itertools.product((1, -1), repeat=2):
        Vy = vy * np.array([[a], [b], [1]])
        Vy[2] = np.cross(Vy[0], Vy[1])
        Vx = vx.copy()
        Vx[2] = np.cross(Vx[0], Vx[1])
        R = Vy.T @ Vx
        s = np.sqrt(((Y - cy) ** 2).sum(1).mean() / ((X - cx) ** 2).sum(1).mean())
        t = cy - s * R @ cx
        for _ in range(iterations):
            near = (((s * X @ R.T + t)[:, None] - Y[None]) ** 2).sum(-1).argmin(1)
            s, R, t = similarity(X, Y[near])
        d = np.sqrt((((s * X @ R.T + t)[:, None] - Y[None]) ** 2).sum(-1))
        error = d.min(1).mean() + d.min(0).mean()
        if best is None or error < best[0]:
            best = (error, s, R, t)
    return best[1:]


def frame(A, B, major):
    """The handle's frame: A, the span along x, the oval's major axis along y (world from handle, 4x4)."""
    u = (B - A) / np.linalg.norm(B - A)
    x = major - u * (major @ u)
    x /= np.linalg.norm(x)
    M = np.eye(4)
    M[:3, :3] = np.stack([u, x, np.cross(u, x)], 1)
    M[:3, 3] = A
    return M


def palm(joints, side):
    """The palm's frame (y from the wrist to the knuckles, z from the index's base to the little finger's) and length:
    import_botw_moveset.py's Rig.hand, columns x, y, z."""
    wrist = joints[f'hand_{side}']
    reach = (joints[f'finger_0_{side}'] + joints[f'finger_3_{side}']) / 2 - wrist
    across = joints[f'finger_3_{side}'] - joints[f'finger_0_{side}']
    y = reach / np.linalg.norm(reach)
    z = across - y * (across @ y)
    z /= np.linalg.norm(z)
    return np.stack([np.cross(y, z), y, z], 1), np.linalg.norm(reach)


class Body:
    """The character's rest skeleton and skin (export.py's body.glb), and its pose as world matrices by bone name."""

    def __init__(self, path):
        glb = Glb(path)
        nodes = glb.json['nodes']
        self.names = [n.get('name', '') for n in nodes]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.parent = {c: i for i, n in enumerate(nodes) for c in n.get('children', [])}
        self.rest = glb.worlds()
        self.local = {i: np.linalg.inv(self.rest[self.parent[i]]) @ self.rest[i] if i in self.parent else self.rest[i]
                      for i in self.rest}
        skin = glb.json['skins'][0]
        self.joints = skin['joints']
        mesh = next(m for m in glb.json['meshes'] if m['name'].endswith('Body'))
        prim = mesh['primitives'][0]['attributes']
        bind = glb.accessor(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
        position = glb.accessor(prim['POSITION'])
        weights = glb.accessor(prim['WEIGHTS_0'])
        bones = glb.accessor(prim['JOINTS_0']).astype(int)
        self.weights = np.zeros((len(position), len(self.joints)))
        np.put_along_axis(self.weights, bones, weights, 1)
        self.weights /= self.weights.sum(1, keepdims=True)
        # each joint's skinning matrix applied to the bind-pose vertices, so a pose is a weighted sum
        self.bound = np.einsum('jab,vb->jva', bind, np.c_[position, np.ones(len(position))])

    def world(self, name, pose):
        return pose[self.index[name]]

    def posed(self, locals_):
        """World matrices from local ones (bone index -> 4x4), parents first."""
        out = {}

        def at(i):
            if i not in out:
                out[i] = (at(self.parent[i]) if i in self.parent else np.eye(4)) @ locals_[i]
            return out[i]
        for i in locals_:
            at(i)
        return out

    def skin(self, pose, bones):
        """The posed vertices with at least a third of their weight on `bones` (LiveLibrary.SkinnedVertices' rule)."""
        columns = [self.joints.index(self.index[b]) for b in bones]
        keep = self.weights[:, columns].sum(1) >= 1 / 3
        M = np.stack([pose[j] for j in self.joints])
        return np.einsum('jab,jvb,vj->va', M, self.bound[:, keep], self.weights[keep])[:, :3]


def distal(points, near, mid, reach):
    """The direction of a digit's last segment, from its last joint (`near`) to the middle of the skin past it: the
    points nearer that joint than the one before (`mid`), within `reach`."""
    d_near = np.linalg.norm(points - near, axis=1)
    pick = points[(d_near < np.linalg.norm(points - mid, axis=1)) & (d_near < reach)]
    v = pick.mean(0) - near
    return v / np.linalg.norm(v)


def pose_hand(body, side, joints, skin, to_handle):
    """The rest skeleton's hand and digits turned onto the game's: the hand bone by the palm's frame, then each digit's
    segments in turn swung (the smallest turn) to point at its next joint, its last segment at its skin's middle.
    Returns the bone locals (by index) and the hand bone's world matrix, in the handle's frame."""
    rest = {n: body.rest[body.index[n]][:3, 3] for n in body.names if n}
    joints = {n: (to_handle @ np.r_[p, 1])[:3] for n, p in joints.items()}
    skin = {k: (np.c_[v, np.ones(len(v))] @ to_handle.T)[:, :3] for k, v in skin.items()}
    F0, length0 = palm(rest, side)
    F1, length1 = palm(joints, side)
    hand = body.index[f'hand_{side}']
    H = np.eye(4)
    H[:3, :3] = F1 @ F0.T @ body.rest[hand][:3, :3]
    H[:3, 3] = joints[f'hand_{side}']
    locals_ = dict(body.local)
    # the whole rest skeleton carried with the hand, so the wrist's skin (partly the forearm's) keeps its rest shape
    root = hand
    while root in body.parent:
        root = body.parent[root]
    locals_[root] = H @ np.linalg.inv(body.rest[hand]) @ body.local[root]
    for k, digit in enumerate(DIGITS):
        names = [n.format(s=side) for n in digit]
        points = skin['thumb' if k == 4 else str(k)]
        rest_points = body.skin(body.rest, names)
        for j, name in enumerate(names):
            pose = body.posed(locals_)
            i = body.index[name]
            if j < 2:
                child = rest[names[j + 1]] - rest[name]
                want = joints[names[j + 1]] - joints[name]
            else:
                reach = 1.6 * np.linalg.norm(rest[names[2]] - rest[names[1]])
                child = distal(rest_points, rest[names[2]], rest[names[1]], reach)
                want = distal(points, joints[names[2]], joints[names[1]], reach)
            # the rest pose's direction carried by the posed parent, swung onto the wanted one
            W = pose[body.parent[i]] @ body.local[i]
            have = W[:3, :3] @ np.linalg.inv(body.rest[i][:3, :3]) @ child
            S = swing(have / np.linalg.norm(have), want / np.linalg.norm(want))
            W[:3, :3] = S @ W[:3, :3]
            locals_[i] = np.linalg.inv(pose[body.parent[i]]) @ W
            locals_[i][:3, 3] = body.local[i][:3, 3]
    return locals_, H, length1 / length0


def swing(a, b):
    v = np.cross(a, b)
    s, c = np.linalg.norm(v), a @ b
    if s < 1e-9:
        return np.eye(3)
    k = v / s
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    angle = np.arctan2(s, c)
    return np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * K @ K


def placement(M):
    return {'position': [round(float(v), 6) for v in M[:3, 3]],
            'quaternion': [round(float(v), 7) for v in quaternion(M[:3, :3] / np.linalg.norm(M[:3, 0]))],
            'scale': round(float(np.linalg.norm(M[:3, 0])), 6)}


def sword_handle(glb_path):
    """The sword's grip in its own mesh frame (BotwMoveSet.cpp: the blade along the bounds' longest axis from the
    origin to the far end; the handle from the origin to the near end; the oval's major axis the bounds' middle size)."""
    glb = Glb(glb_path)
    X = glb.accessor(glb.json['meshes'][0]['primitives'][0]['attributes']['POSITION'])
    lo, hi = X.min(0), X.max(0)
    size = hi - lo
    axis, thin = int(np.argmax(size)), int(np.argmin(size))
    far = hi[axis] if abs(hi[axis]) >= abs(lo[axis]) else lo[axis]
    near = lo[axis] if far == hi[axis] else hi[axis]
    hilt = np.zeros(3)
    hilt[axis] = near if near * far < 0 else 0.
    major = np.zeros(3)
    major[3 - axis - thin] = 1.
    return np.unique(X.round(6), axis=0), hilt, major


def main(args):
    data = args.samples.read_bytes()
    if args.samples.suffix == '.gz':   # the committed copy (grips/modori/samples/) is gzipped; its hash is the samples'
        data = gzip.decompress(data)
    rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
    held = [r for r in rows if r.get('handle') in ('sword', 'glider') and all(h['weight'] > .99 for h in r['grip']['hands'])]
    body = Body(yori.OUT / 'grips' / args.character / 'body.glb')
    sword_vertices, hilt, major = sword_handle(BOTW / 'LinkSword.glb')
    length = float(np.linalg.norm(hilt))
    grips, checks = [], {}
    for prop in ('sword', 'glider'):
        samples = [r for r in held if r['handle'] == prop]
        if not samples:
            continue
        for side in 'RL':
            moments = []
            for r in samples:
                if prop == 'sword':
                    s, R, t = fit_mesh(sword_vertices, from_game(r['handle_verts']))
                    A = s * R @ (hilt * SWORD_SPAN[0]) + t
                    B = s * R @ (hilt * SWORD_SPAN[1]) + t
                    world = frame(A, B, R @ major)
                    radii = [[v * length * s for v in rr] for rr in SWORD_RADII]
                    handle = {'r0': radii[0], 'r1': radii[1], 'rm': radii[2], 'mid_at': SWORD_WAIST}
                else:
                    local = from_game([p for e in 'RL' for p in GLIDER_HANDLES[e]])
                    s, R, t = similarity(local, from_game([p for e in 'RL' for p in r['handle_axes'][e]]))
                    A, B = (from_game(p) for p in r['handle_axes'][side])
                    world = frame(A, B, R @ np.array([0., 1., 0.]))   # the glider's up (the game's Z)
                    radius = [v / 100. * s for v in GLIDER_RADII]
                    handle = {'r0': radius, 'r1': radius, 'rm': None, 'mid_at': -1}
                handle['length'] = float(np.linalg.norm(B - A))
                to_handle = np.linalg.inv(world)
                prop_matrix = np.eye(4)
                prop_matrix[:3, :3], prop_matrix[:3, 3] = s * R, t
                hands = {}
                for e in 'RL':
                    joints = {n: from_game(p) for n, p in r['joints_' + e].items()}
                    F, _ = palm({n: (to_handle @ np.r_[p, 1])[:3] for n, p in joints.items()}, e)
                    hand = np.eye(4)
                    hand[:3, :3] = F @ palm({n: body.rest[body.index[n]][:3, 3] for n in body.names if n}, e)[0].T \
                        @ body.rest[body.index[f'hand_{e}']][:3, :3]
                    hand[:3, 3] = (to_handle @ np.r_[joints[f'hand_{e}'], 1])[:3]
                    hands[e] = hand
                moments.append({'row': r, 'world': world, 'handle': handle, 'prop': to_handle @ prop_matrix, 'hands': hands})
            # moments that hold the hand the same way (within .5 mm and .2 degrees) are one
            distinct = []
            for m in moments:
                if not any(np.abs(m['hands'][side][:3, 3] - d['hands'][side][:3, 3]).max() < 5e-4 and
                           np.degrees(np.arccos(np.clip((np.trace(m['hands'][side][:3, :3].T @ d['hands'][side][:3, :3]) - 1) / 2, -1, 1))) < .2
                           for d in distinct):
                    distinct.append(m)
            # the typical moment: the one whose hand is nearest the others' mean place
            centre = np.mean([m['hands'][side][:3, 3] for m in distinct], 0)
            typical = min(range(len(distinct)), key=lambda k: np.linalg.norm(distinct[k]['hands'][side][:3, 3] - centre))
            m = distinct[typical]
            r = m['row']
            joints = {n: from_game(p) for n, p in r['joints_' + side].items()}
            skin = {k: from_game(v) for k, v in r['fingers_' + side].items()}
            skin['thumb'] = from_game(r['thumb_' + side])
            to_handle = np.linalg.inv(m['world'])
            locals_, hand, scale = pose_hand(body, side, joints, skin, to_handle)
            pose = body.posed(locals_)
            bones = [f'hand_{side}'] + [n.format(s=side) for d in DIGITS for n in d]
            fitted = body.skin(pose, bones)
            game = (np.c_[from_game(r['hand_' + side]), np.ones(len(r['hand_' + side]))] @ to_handle.T)[:, :3]
            d = np.sqrt(((fitted[:, None] - game[None]) ** 2).sum(-1))
            joint_miss = max(np.linalg.norm((pose[body.index[n]][:3, 3]) - (to_handle @ np.r_[joints[n], 1])[:3])
                             for n in bones if n in joints)
            gid = f'{prop}_{side}'
            checks[gid] = {'moments': len(moments), 'distinct': len(distinct), 'palm_scale': round(float(scale), 4),
                           'skin_to_game_mm': round(float(d.min(1).mean() * 1000), 2),
                           'game_to_skin_mm': round(float(d.min(0).mean() * 1000), 2),
                           'worst_joint_mm': round(float(joint_miss * 1000), 2)}
            grips.append({
                'id': gid, 'prop': prop, 'side': side,
                'label': f"{'Sword' if prop == 'sword' else 'Glider'}, {'right' if side == 'R' else 'left'} hand",
                'handle': {**{k: v for k, v in m['handle'].items()}, 'beyond': BEYOND},
                'prop_mesh': {'file': 'LinkSword.glb' if prop == 'sword' else 'LinkGlider.glb', **placement(m['prop'])},
                'moments': [{'t': d['row']['t'], 'hand': placement(d['hands'][side]),
                             'other': placement(d['hands']['L' if side == 'R' else 'R'])} for d in distinct],
                'typical': typical,
                'start': {'bones': {body.names[i]: [round(float(v), 7) for v in quaternion(locals_[i][:3, :3])]
                                    for i in (body.index[n] for n in bones[1:])},
                          'report': r['grip']['hands'][0 if side == 'R' else 1],
                          'ghost_joints': {n: [round(float(v), 5) for v in (to_handle @ np.r_[p, 1])[:3]] for n, p in joints.items()},
                          'ghost_skin': [[round(float(v), 5) for v in p] for p in game]},
            })
            print(gid, json.dumps(checks[gid]), flush=True)
    out = yori.OUT / 'grips' / args.character
    record = {'character': args.character, 'frame': 'glTF: Y up, metres; the handle frame has A at the origin, the span along +x, the oval major axis along +y',
              'samples': {'file': args.samples.name.removesuffix('.gz'), 'sha256': hashlib.sha256(data).hexdigest(), 'rows': len(rows), 'held': len(held)},
              'grips': grips, 'checks': checks}
    (out / 'moments.json').write_text(json.dumps(record) + '\n')
    print('GRIP MOMENTS COMPLETE', json.dumps(checks), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--character', default='modori')
    parser.add_argument('--samples', type=Path, required=True)
    main(parser.parse_args())
