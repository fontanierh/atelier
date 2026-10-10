"""SK_SkateRider's source: a GLB of the simulation rig in its reference pose with a plain box body and board.

The mesh only exists so Unreal has a skeleton with the simulation bone names and hierarchy; every bone of every clip is
keyed, so the clips never fall back to this pose. Each limb is a box from its parent joint to its own, rigidly skinned
to the parent; the board is a deck on SKATEBOARD_ROOT, a block per truck and per wheel. The *_REPARENTED bones are
targets (where the hands and toes go on the board) and carry no geometry.

glTF is right-handed, Y up, metres; Interchange maps a glTF vector to Unreal (x, z, y) * 100. The file is written in a
glTF frame rotated so that this lands exactly on the Skate adapter's convention (simulation (x, y, z) -> (z, -x, y) * 100):
glTF g = (n.z, n.y, -n.x), a proper rotation, so rotations conjugate without a reflection.
Standard library only: it runs inside Unreal's Python.
"""
from __future__ import annotations

import json
import math
import struct

BODY = (0.80, 0.55, 0.42, 1.0)
BOARD = (0.20, 0.22, 0.26, 1.0)


# ---------------------------------------------------------------- small maths (column vectors)
def quat_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
            [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
            [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]]


def affine(translation, rotation, scale):
    r = quat_matrix(rotation)
    return [[r[i][j] * scale[j] for j in range(3)] + [translation[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def apply(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) + m[i][3] for i in range(3)]


def invert_rigid(m):
    """Inverse of a rotation (+ uniform scale 1) and translation."""
    r = [[m[j][i] for j in range(3)] for i in range(3)]
    t = [-sum(r[i][k] * m[k][3] for k in range(3)) for i in range(3)]
    return [r[i] + [t[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]]


def to_gltf(v):
    return (v[2], v[1], -v[0])


def quat_to_gltf(q):
    return (q[2], q[1], -q[0], q[3])


def scale_to_gltf(s):
    return (s[2], s[1], s[0])


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def unit(v):
    n = math.sqrt(sum(c * c for c in v)) or 1.0
    return [c / n for c in v]


# ---------------------------------------------------------------- geometry
class Mesh:
    def __init__(self):
        self.positions, self.normals, self.joints, self.indices = [], [], [], {}

    def quad(self, material, corners, joint):
        normal = unit(cross(sub(corners[1], corners[0]), sub(corners[2], corners[0])))
        base = len(self.positions)
        for c in corners:
            self.positions.append(c)
            self.normals.append(normal)
            self.joints.append(joint)
        self.indices.setdefault(material, []).extend([base, base + 1, base + 2, base, base + 2, base + 3])

    def box(self, material, centre, axes, half, joint):
        """A box with the given centre, three orthonormal axes and half extents, in glTF space."""
        def corner(sx, sy, sz):
            return [centre[i] + sx * half[0] * axes[0][i] + sy * half[1] * axes[1][i] + sz * half[2] * axes[2][i]
                    for i in range(3)]
        faces = [((1, -1, -1), (1, 1, -1), (1, 1, 1), (1, -1, 1)), ((-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, -1, -1)),
                 ((-1, 1, -1), (-1, 1, 1), (1, 1, 1), (1, 1, -1)), ((-1, -1, 1), (-1, -1, -1), (1, -1, -1), (1, -1, 1)),
                 ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)), ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1))]
        for face in faces:
            self.quad(material, [corner(*c) for c in face], joint)

    def limb(self, material, a, b, width, joint):
        d = sub(b, a)
        length = math.sqrt(sum(c * c for c in d))
        if length < 1e-4:
            return
        axis = unit(d)
        other = [0.0, 1.0, 0.0] if abs(axis[1]) < 0.9 else [1.0, 0.0, 0.0]
        side = unit(cross(axis, other))
        up = cross(side, axis)
        centre = [(a[i] + b[i]) / 2 for i in range(3)]
        self.box(material, centre, (axis, side, up), (length / 2, width, width), joint)


def bind_globals(bones, locals_gltf):
    """Global bind matrices in glTF space (the reference pose's trajectory is the identity, so composing through it
    matches the simulation hierarchy, which never composes children of the trajectory with it)."""
    out = []
    for i, bone in enumerate(bones):
        local = affine(*locals_gltf[i])
        out.append(local if bone.parent < 0 else mul(out[bone.parent], local))
    return out


def build(rig, pose, split_sample):
    """(nodes TRS in glTF space, global bind matrices, Mesh) for the rig in `pose`."""
    bones = rig.bones
    locals_gltf = []
    for words in pose.samples:
        scale, rotation, translation = split_sample(words)
        n = math.sqrt(sum(v * v for v in rotation))
        rotation = tuple(v / n for v in rotation)
        locals_gltf.append((to_gltf(translation), quat_to_gltf(rotation), scale_to_gltf(scale)))
    globals_ = bind_globals(bones, locals_gltf)
    position = [[g[0][3], g[1][3], g[2][3]] for g in globals_]
    names = [b.name for b in bones]
    index = {n: i for i, n in enumerate(names)}
    mesh = Mesh()
    board = {'SKATEBOARD_ROOT', 'TRUCK_FRONT', 'TRUCK_BACK', 'LEFT_WHEELFRONT', 'RIGHT_WHEELFRONT', 'LEFT_WHEELBACK',
             'RIGHT_WHEELBACK'}
    for i, bone in enumerate(bones):
        if bone.parent <= 0 or bone.name.endswith('_REPARENTED') or bone.name in board:
            continue
        width = 0.035 if bones[bone.parent].name.startswith(('SPINE', 'NECK', 'HIPS')) else 0.028
        mesh.limb('body', position[bone.parent], position[i], width, bone.parent)

    def local_box(material, bone, offset, half):
        g = globals_[index[bone]]
        axes = [unit([g[r][c] for r in range(3)]) for c in range(3)]
        centre = apply(g, offset)
        mesh.box(material, centre, axes, half, index[bone])

    def tip(bone, length, width):
        """A block continuing the parent->bone direction past the joint (head, hands, toes)."""
        i = index[bone]
        a, b = position[bones[i].parent], position[i]
        direction = unit(sub(b, a))
        mesh.limb('body', b, [b[k] + direction[k] * length for k in range(3)], width, i)

    tip('HEAD', 0.20, 0.09)
    for side in ('LEFT', 'RIGHT'):
        tip(side + 'HAND', 0.12, 0.035)
        tip(side + 'TOEBASE', 0.08, 0.035)
    local_box('body', 'HIPS', (0.0, 0.0, 0.0), (0.06, 0.08, 0.12))
    # The deck lies in SKATEBOARD_ROOT's frame: the simulation x left, y up, z forward -> glTF (z, y, -x).
    local_box('board', 'SKATEBOARD_ROOT', (0.0, 0.0, 0.0), (0.40, 0.007, 0.105))
    for truck in ('TRUCK_FRONT', 'TRUCK_BACK'):
        local_box('board', truck, (0.0, 0.0, 0.0), (0.03, 0.03, 0.03))
    for wheel in ('LEFT_WHEELFRONT', 'RIGHT_WHEELFRONT', 'LEFT_WHEELBACK', 'RIGHT_WHEELBACK'):
        local_box('board', wheel, (0.0, 0.0, 0.0), (0.027, 0.027, 0.02))
    return locals_gltf, globals_, mesh


def write_glb(path, rig, pose, split_sample):
    locals_gltf, globals_, mesh = build(rig, pose, split_sample)
    bones = rig.bones
    blob = bytearray()
    views, accessors = [], []

    def add(data, target=None):
        while len(blob) % 4:
            blob.append(0)
        view = dict(buffer=0, byteOffset=len(blob), byteLength=len(data))
        if target:
            view['target'] = target
        blob.extend(data)
        views.append(view)
        return len(views) - 1

    def accessor(view, component, count, kind, **extra):
        accessors.append(dict(bufferView=view, componentType=component, count=count, type=kind, **extra))
        return len(accessors) - 1

    n = len(mesh.positions)
    flat = [c for p in mesh.positions for c in p]
    position = accessor(add(struct.pack(f'<{len(flat)}f', *flat), 34962), 5126, n, 'VEC3',
                        min=[min(p[i] for p in mesh.positions) for i in range(3)],
                        max=[max(p[i] for p in mesh.positions) for i in range(3)])
    flat = [c for p in mesh.normals for c in p]
    normal = accessor(add(struct.pack(f'<{len(flat)}f', *flat), 34962), 5126, n, 'VEC3')
    flat = [c for j in mesh.joints for c in (j, 0, 0, 0)]
    joints = accessor(add(struct.pack(f'<{len(flat)}B', *flat), 34962), 5121, n, 'VEC4')
    flat = [c for _ in mesh.joints for c in (1.0, 0.0, 0.0, 0.0)]
    weights = accessor(add(struct.pack(f'<{len(flat)}f', *flat), 34962), 5126, n, 'VEC4')
    primitives, materials = [], []
    for name, colour in (('body', BODY), ('board', BOARD)):
        indices = mesh.indices.get(name, [])
        if not indices:
            continue
        view = add(struct.pack(f'<{len(indices)}I', *indices), 34963)
        materials.append(dict(name=f'M_SkateRider_{name.title()}',
                              pbrMetallicRoughness=dict(baseColorFactor=list(colour), metallicFactor=0.0, roughnessFactor=0.8)))
        primitives.append(dict(attributes=dict(POSITION=position, NORMAL=normal, JOINTS_0=joints, WEIGHTS_0=weights),
                               indices=accessor(view, 5125, len(indices), 'SCALAR'), material=len(materials) - 1))
    inverse = []
    for g in globals_:
        m = invert_rigid(g)
        inverse.extend(m[r][c] for c in range(4) for r in range(4))     # column-major
    ibm = accessor(add(struct.pack(f'<{len(inverse)}f', *inverse)), 5126, len(bones), 'MAT4')
    nodes = []
    for i, bone in enumerate(bones):
        t, r, s = locals_gltf[i]
        node = dict(name=bone.name, translation=list(t), rotation=list(r), scale=list(s))
        children = [j for j, b in enumerate(bones) if b.parent == i]
        if children:
            node['children'] = children
        nodes.append(node)
    nodes.append(dict(name='SK_SkateRider', mesh=0, skin=0))
    document = dict(
        asset=dict(version='2.0', generator='atelier skate_ride rider_mesh.py'),
        scene=0, scenes=[dict(nodes=[0, len(nodes) - 1])], nodes=nodes,
        meshes=[dict(name='SK_SkateRider', primitives=primitives)], materials=materials,
        skins=[dict(name='SKEL_SkateRider', joints=list(range(len(bones))), inverseBindMatrices=ibm, skeleton=0)],
        accessors=accessors, bufferViews=views, buffers=[dict(byteLength=len(blob))])
    text = json.dumps(document, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    while len(blob) % 4:
        blob.append(0)
    out = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(blob))
    out += struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(blob), 0x004E4942) + bytes(blob)
    path.write_bytes(out)
    return dict(vertices=n, triangles=sum(len(v) for v in mesh.indices.values()) // 3, bones=len(bones))
