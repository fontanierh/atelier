"""Atelier library obstacles the skate pier is built from, placed in park-local metres.

The GLBs are committed in assets/skatepark/modules. Their sizes and grind lines are measured once
into the pin, so the park's layout and rails are the same with or without them: without them, features.py draws
procedural stand-ins on the same lines. A placement is a dict with the part, its centre `at` (x, y, deck height) and
`yaw`, the degrees its local +y (every part's long or uphill axis) is turned anticlockwise from north.
"""
import hashlib
import json
import math
import struct
from functools import lru_cache
import numpy as np
import yori

SPEC = yori.ASSETS / 'skatepark' / 'modules.json'
FOLDER = SPEC.parent / 'modules'
FRAME = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])   # glTF Y-up to park Z-up
TYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTH = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


@lru_cache(maxsize=1)
def spec():
    return json.loads(SPEC.read_text())


def part(name):
    return spec()['parts'][name]


@lru_cache(maxsize=1)
def available():
    """Whether every committed library mesh matches its recorded size and checksum."""
    for name, entry in spec()['parts'].items():
        path = FOLDER / f'{name}.glb'
        if not path.is_file() or path.stat().st_size != entry['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            return False
    return True


def _node_matrix(node):
    if 'matrix' in node:
        return np.asarray(node['matrix'], float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0., 0., 0., 1.])
    r = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                  [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    m = np.eye(4)
    m[:3, :3] = r @ np.diag(node.get('scale', [1., 1., 1.]))
    m[:3, 3] = node.get('translation', [0., 0., 0.])
    return m


@lru_cache(maxsize=None)
def local_triangles(name):
    """A part's triangles in its own Z-up metres, (n, 3, 3), every node's transform applied."""
    data = (FOLDER / f'{name}.glb').read_bytes()
    if hashlib.sha256(data).hexdigest() != part(name)['sha256']:
        raise ValueError(f'Committed skate pier module {name} checksum mismatch')
    size = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20+size])
    buffer = data[len(data)-struct.unpack_from('<I', data, 20+size)[0]:]

    def accessor(index):
        a = gltf['accessors'][index]; view = gltf['bufferViews'][a['bufferView']]
        dtype = np.dtype(TYPES[a['componentType']]); width = WIDTH[a['type']]
        return np.ndarray((a['count'], width), dtype=dtype, buffer=buffer, offset=view.get('byteOffset', 0)+a.get('byteOffset', 0),
                          strides=(view.get('byteStride', width*dtype.itemsize), dtype.itemsize))
    out = []

    def visit(index, parent):
        node = gltf['nodes'][index]; matrix = parent @ _node_matrix(node)
        if 'mesh' in node:
            for p in gltf['meshes'][node['mesh']]['primitives']:
                if p.get('mode', 4) != 4:
                    raise ValueError('Only triangle primitives are accepted')
                positions = accessor(p['attributes']['POSITION']).astype(float) @ matrix[:3, :3].T + matrix[:3, 3]
                faces = accessor(p['indices']).ravel().astype(int).reshape(-1, 3)
                out.append((positions @ FRAME.T)[faces])
        for child in node.get('children', []):
            visit(child, matrix)
    for root in gltf['scenes'][gltf.get('scene', 0)]['nodes']:
        visit(root, np.eye(4))
    tris = np.concatenate(out)
    if len(tris) != part(name)['triangles']:
        raise ValueError(f'Skate pier module {name} has {len(tris)} triangles, the pin {part(name)["triangles"]}')
    return tris


def place(points, item):
    """Local points (..., 3) turned by the placement's yaw and moved to its centre."""
    p = np.asarray(points, float)
    a = math.radians(item['yaw']); c, s = math.cos(a), math.sin(a)
    x, y = p[..., 0]*c - p[..., 1]*s, p[..., 0]*s + p[..., 1]*c
    return np.stack([x + item['at'][0], y + item['at'][1], p[..., 2] + item['at'][2]], axis=-1)


def triangles(item):
    """The placed part's triangles without its bottom faces lying on the floor (no coplanar riding collision)."""
    t = local_triangles(item['part'])
    n = np.cross(t[:, 1]-t[:, 0], t[:, 2]-t[:, 0])
    down = n[:, 2] < -.9*np.linalg.norm(n, axis=1)
    on_floor = np.abs(t[:, :, 2]).max(axis=1) < .005
    return place(t[~(down & on_floor)], item)


def line(item):
    """The placed part's measured grind line (bars, handrails): its top's centre line."""
    return [tuple(round(float(v), 4) for v in p) for p in place(part(item['part'])['line'], item)]


def edges(item):
    """The placed part's two long top edges (ledge lips) with their outward sides."""
    out = []
    a = math.radians(item['yaw']); c, s = math.cos(a), math.sin(a)
    for edge in part(item['part'])['edges']:
        sx, sy, _ = edge['side']
        out.append(([tuple(round(float(v), 4) for v in p) for p in place(edge['points'], item)],
                    (round(sx*c - sy*s, 4), round(sx*s + sy*c, 4))))
    return out


def footprint(item):
    """The placed part's floor rectangle (x0, x1, y0, y1); every yaw is a multiple of 90 degrees."""
    (x0, y0, _), (x1, y1, _) = part(item['part'])['bounds']
    corners = place([(x0, y0, 0.), (x1, y1, 0.)], item)
    return (round(float(corners[:, 0].min()), 4), round(float(corners[:, 0].max()), 4),
            round(float(corners[:, 1].min()), 4), round(float(corners[:, 1].max()), 4))


def height(item):
    return item['at'][2] + part(item['part'])['bounds'][1][2]
