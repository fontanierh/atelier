"""Read the committed scene and sample its actual terrain triangles."""
import hashlib
import json
from functools import lru_cache

import numpy as np
import yori
from atelier.gltf import glb_parts

LIBRARY = yori.ASSETS / 'belmonte'
MANIFEST = LIBRARY / 'source.json'
FRAME = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])


@lru_cache(maxsize=1)
def manifest():
    return json.loads(MANIFEST.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triangles(path):
    """The acquisition bakes object transforms; glTF nodes are identity."""
    doc, binary = glb_parts(path.read_bytes())

    def read(index):
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        dtype = np.dtype({5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[accessor['componentType']])
        width = {'SCALAR': 1, 'VEC3': 3}[accessor['type']]
        return np.ndarray((accessor['count'], width), dtype=dtype, buffer=binary,
                          offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                          strides=(view.get('byteStride', width * dtype.itemsize), dtype.itemsize))

    result = []
    for node in doc['nodes']:
        assert not any(key in node for key in ('matrix', 'translation', 'rotation', 'scale')), (path, node)
        if 'mesh' not in node:
            continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            assert primitive.get('mode', 4) == 4
            vertices = read(primitive['attributes']['POSITION']).astype(float) @ FRAME.T
            faces = read(primitive['indices']).reshape(-1, 3)
            result.append(vertices[faces])
    return np.concatenate(result)


class Surface:
    """Upward triangle intersections, indexed in 32 m cells for map and planting."""
    CELL = 32.

    def __init__(self, faces):
        faces = np.asarray(faces, float)
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        normal = np.cross(b - a, c - a)
        self.faces = faces[np.abs(normal[:, 2]) > 1e-8]
        self.bins = {}
        lo = np.floor(self.faces[:, :, :2].min(1) / self.CELL).astype(int)
        hi = np.floor(self.faces[:, :, :2].max(1) / self.CELL).astype(int)
        for index, (low, high) in enumerate(zip(lo, hi)):
            for x in range(low[0], high[0] + 1):
                for y in range(low[1], high[1] + 1):
                    self.bins.setdefault((x, y), []).append(index)

    def height(self, x, y):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        query = np.stack([x.ravel(), y.ravel()], 1)
        cells = np.floor(query / self.CELL).astype(int)
        result = np.full(len(query), np.nan)
        keys, inverse = np.unique(cells, axis=0, return_inverse=True)
        for group, key in enumerate(keys):
            indices = self.bins.get(tuple(key))
            if not indices:
                continue
            selected = np.flatnonzero(inverse == group)
            a, b, c = np.moveaxis(self.faces[indices], 1, 0)
            e, f = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2]
            p = query[selected, None, :] - a[None, :, :2]
            determinant = e[:, 0] * f[:, 1] - e[:, 1] * f[:, 0]
            u = (p[:, :, 0] * f[:, 1] - p[:, :, 1] * f[:, 0]) / determinant
            v = (e[:, 0] * p[:, :, 1] - e[:, 1] * p[:, :, 0]) / determinant
            covered = (u >= -1e-7) & (v >= -1e-7) & (u + v <= 1 + 1e-7)
            z = a[:, 2] + u * (b[:, 2] - a[:, 2]) + v * (c[:, 2] - a[:, 2])
            best = np.max(np.where(covered, z, -np.inf), axis=1)
            result[selected] = np.where(np.isfinite(best), best, np.nan)
        return result.reshape(x.shape)


@lru_cache(maxsize=1)
def terrain():
    entries = [entry for entry in manifest()['meshes'] if entry['name'].startswith('SM_BM_BT_Terrain_')]
    assert len(entries) == 56, 'Current Belmonte terrain coverage changed; review the source census'
    return Surface(np.concatenate([triangles(LIBRARY / entry['path']) for entry in entries]))
