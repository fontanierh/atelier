"""Exact Hippodrome geometry data; no export side effects."""
import hashlib, json, math, struct
from pathlib import Path
import numpy as np
import yori
PROPS=yori.ASSETS/"hippodrome"/"props"
UV_METRES=4.

def encoded_glb(name, positions, normals, uvs, indices, material):
    """The original exact mesh encoding, as data before any file export."""
    p = np.asarray(positions, np.float32); n = np.asarray(normals, np.float32); t = np.asarray(uvs, np.float32)
    i = np.asarray(indices, np.uint32).reshape(-1)
    gl = lambda v: np.stack([v[:, 0], v[:, 2], -v[:, 1]], 1).astype(np.float32)
    p, n = gl(p), gl(n)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    chunks, views, accessors = bytearray(), [], []

    def add(array, kind, ctype, target, minmax=False):
        chunks.extend(b'\x00' * (-len(chunks) % 4))
        views.append({'buffer': 0, 'byteOffset': len(chunks), 'byteLength': array.nbytes, 'target': target})
        chunks.extend(array.tobytes())
        acc = {'bufferView': len(views) - 1, 'componentType': ctype, 'count': len(array), 'type': kind}
        if minmax:
            acc['min'] = [float(v) for v in array.min(0)]; acc['max'] = [float(v) for v in array.max(0)]
        accessors.append(acc)
        return len(accessors) - 1

    attributes = {'POSITION': add(p, 'VEC3', 5126, 34962, True), 'NORMAL': add(n, 'VEC3', 5126, 34962),
                  'TEXCOORD_0': add(t, 'VEC2', 5126, 34962)}
    index = add(i, 'SCALAR', 5125, 34963)
    gltf = {'asset': {'version': '2.0', 'generator': 'yorimichi hippodrome'}, 'scene': 0,
            'scenes': [{'nodes': [0]}], 'nodes': [{'name': name, 'mesh': 0}],
            'meshes': [{'name': name, 'primitives': [{'attributes': attributes, 'indices': index, 'material': 0}]}],
            'materials': [{'name': material, 'pbrMetallicRoughness': {'baseColorFactor': [.8, .8, .8, 1.],
                                                                       'metallicFactor': 0., 'roughnessFactor': .9}}],
            'buffers': [{'byteLength': len(chunks)}], 'bufferViews': views, 'accessors': accessors}
    return _encoded(gltf,chunks), {'triangles': len(i) // 3, 'min': [float(v) for v in np.asarray(positions).min(0)],
            'max': [float(v) for v in np.asarray(positions).max(0)], 'material': material}

def _encoded(gltf,binary):
    binary = bytes(binary) + b'\x00' * (-len(binary) % 4)
    gltf['buffers'] = [{'byteLength': len(binary)}]
    text = json.dumps(gltf, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    return (struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(text) + 8 + len(binary)) +
            struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(binary), 0x004E4942) + binary)

def _read(path):
    data = path.read_bytes()
    length = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    return gltf, bytearray(data[20 + length + 8:])

class Mesh:
    def __init__(self):
        self.p, self.n, self.t, self.i = [], [], [], []

    def triangle(self, a, b, c):
        """One upward-oriented triangle without a degenerate second half."""
        a, b, c = (np.asarray(v, float) for v in (a, b, c))
        normal = np.cross(b-a, c-a)
        normal /= max(np.linalg.norm(normal), 1e-9)
        base = len(self.p)
        self.p += [a, b, c]; self.n += [normal]*3
        self.t += [(v[0]/UV_METRES, v[1]/UV_METRES) for v in (a, b, c)]
        self.i += [base, base+1, base+2]

    def quad(self, a, b, c, d, uv=None, normal=None):
        """Quad a-b-c-d counter-clockwise seen from its front."""
        a, b, c, d = (np.asarray(v, float) for v in (a, b, c, d))
        nrm = np.cross(b - a, d - a) if normal is None else np.asarray(normal, float)
        nrm = nrm / max(np.linalg.norm(nrm), 1e-9)
        base = len(self.p)
        self.p += [a, b, c, d]; self.n += [nrm] * 4
        self.t += uv or [(a[0] / UV_METRES, a[1] / UV_METRES), (b[0] / UV_METRES, b[1] / UV_METRES),
                         (c[0] / UV_METRES, c[1] / UV_METRES), (d[0] / UV_METRES, d[1] / UV_METRES)]
        self.i += [base, base + 1, base + 2, base, base + 2, base + 3]

    def box(self, centre, half, yaw=0.):
        """An axis box turned by `yaw` (radians) about z."""
        c, s = math.cos(yaw), math.sin(yaw)
        corner = lambda x, y, z: (centre[0] + x * c - y * s, centre[1] + x * s + y * c, centre[2] + z)
        hx, hy, hz = half
        v = {k: corner(*k) for k in [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]}
        g = lambda sx, sy, sz: v[(sx * hx, sy * hy, sz * hz)]
        self.quad(g(-1, -1, 1), g(1, -1, 1), g(1, 1, 1), g(-1, 1, 1))
        self.quad(g(-1, -1, -1), g(-1, 1, -1), g(1, 1, -1), g(1, -1, -1))
        self.quad(g(-1, -1, -1), g(1, -1, -1), g(1, -1, 1), g(-1, -1, 1))
        self.quad(g(1, 1, -1), g(-1, 1, -1), g(-1, 1, 1), g(1, 1, 1))
        self.quad(g(1, -1, -1), g(1, 1, -1), g(1, 1, 1), g(1, -1, 1))
        self.quad(g(-1, 1, -1), g(-1, -1, -1), g(-1, -1, 1), g(-1, 1, 1))

    def save(self, path, material):
        data, info = encoded_glb(path.stem, self.p, self.n, self.t, self.i, material)
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        return info
