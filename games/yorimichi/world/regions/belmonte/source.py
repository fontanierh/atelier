"""Read the committed scene and sample its actual terrain triangles."""
import hashlib
import json
from functools import lru_cache

import numpy as np
import yori
from atelier.gltf import glb_pack, glb_parts

LIBRARY = yori.ASSETS / 'belmonte'
MANIFEST = LIBRARY / 'source.json'
FRAME = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])
TERRAIN_LAYERS = {'Dry': (.24,.265,.095), 'Green': (.105,.205,.055),
                  'Dirt': (.36,.26,.125), 'Rock': (.25,.265,.24)}


@lru_cache(maxsize=1)
def manifest():
    return json.loads(MANIFEST.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def srgb(value):
    value = np.asarray(value)
    return np.where(value <= .0031308, value * 12.92, 1.055 * value ** (1 / 2.4) - .055)


def native_colours(path):
    """Encode source RGB once for Interchange's direct linear-to-byte packing.

    The FBX source palette was byte colour, and Blender exports linear glTF RGB.
    Interchange packs those values directly into FColor instead of re-encoding
    them. Keep original byte precision and the linear alpha mask by preparing
    COLOR_0 explicitly. Geometry and all other buffer views remain unchanged.
    """
    doc, binary = glb_parts(path.read_bytes())
    extras = doc.setdefault('extras', {})
    if extras.get('atelier_vertex_colours') == 'native-byte-rgb-linear-alpha':
        return False
    binary = bytearray(binary)
    converted = set()
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            if 'COLOR_0' not in attributes:
                continue
            index = attributes['COLOR_0']
            if index in converted:
                continue
            accessor = doc['accessors'][index]
            view = doc['bufferViews'][accessor['bufferView']]
            assert accessor['componentType'] == 5123 and accessor['normalized'], (path, accessor)
            width = {'VEC3': 3, 'VEC4': 4}[accessor['type']]
            colours = np.ndarray((accessor['count'], width), dtype='<u2', buffer=binary,
                                 offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                                 strides=(view.get('byteStride', width*2), 2))
            rgb = colours[:, :3].astype(float) / 65535.
            colours[:, :3] = np.rint(srgb(rgb) * 255).astype('uint16') * 257
            converted.add(index)
    extras['atelier_vertex_colours'] = 'native-byte-rgb-linear-alpha'
    doc['buffers'][0]['byteLength'] = len(binary)
    path.write_bytes(glb_pack(doc, bytes(binary)))
    return True


def triangles(path, palettes=None):
    """The acquisition bakes object transforms; glTF nodes are identity."""
    doc, binary = glb_parts(path.read_bytes())

    def read(index):
        accessor = doc['accessors'][index]
        view = doc['bufferViews'][accessor['bufferView']]
        dtype = np.dtype({5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[accessor['componentType']])
        width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
        return np.ndarray((accessor['count'], width), dtype=dtype, buffer=binary,
                          offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                          strides=(view.get('byteStride', width * dtype.itemsize), dtype.itemsize))

    result, colours = [], []
    for node in doc['nodes']:
        assert not any(key in node for key in ('matrix', 'translation', 'rotation', 'scale')), (path, node)
        if 'mesh' not in node:
            continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            assert primitive.get('mode', 4) == 4
            vertices = read(primitive['attributes']['POSITION']).astype(float) @ FRAME.T
            faces = read(primitive['indices']).reshape(-1, 3)
            result.append(vertices[faces])
            if palettes is not None:
                assert doc.get('extras', {}).get('atelier_vertex_colours') == 'native-byte-rgb-linear-alpha', path
                index = primitive['attributes']['COLOR_0']
                weights = read(index).astype(float)
                component = doc['accessors'][index]['componentType']
                if component != 5126:
                    weights /= 255. if component == 5121 else 65535.
                # The committed COLOR_0 already holds the native byte palette.
                if weights.shape[1] == 3:
                    weights = np.c_[weights, np.ones(len(weights))]
                slot = int(doc['materials'][primitive['material']]['name'].split('_')[1])
                palette, tint = palettes[slot]
                colour = weights @ palette / np.maximum(weights.sum(1, keepdims=True), .001) * tint
                colours.append(colour[faces])
    return (np.concatenate(result), np.concatenate(colours)) if palettes is not None else np.concatenate(result)


class Surface:
    """Upward triangle intersections, indexed in 32 m cells for map and planting."""
    CELL = 32.

    def __init__(self, faces, values=None):
        faces = np.asarray(faces, float)
        a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
        normal = np.cross(b - a, c - a)
        keep = np.abs(normal[:, 2]) > 1e-8
        self.faces = faces[keep]
        self.values = None if values is None else np.asarray(values, float)[keep]
        self.bins = {}
        lo = np.floor(self.faces[:, :, :2].min(1) / self.CELL).astype(int)
        hi = np.floor(self.faces[:, :, :2].max(1) / self.CELL).astype(int)
        for index, (low, high) in enumerate(zip(lo, hi)):
            for x in range(low[0], high[0] + 1):
                for y in range(low[1], high[1] + 1):
                    self.bins.setdefault((x, y), []).append(index)

    def height(self, x, y):
        return self.sample(x, y)

    def colour(self, x, y):
        assert self.values is not None
        return self.sample(x, y, self.values)

    def sample(self, x, y, values=None):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        query = np.stack([x.ravel(), y.ravel()], 1)
        cells = np.floor(query / self.CELL).astype(int)
        result = np.full((len(query), 3) if values is not None else len(query), np.nan)
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
            if values is None:
                result[selected] = np.where(np.isfinite(best), best, np.nan)
            else:
                chosen = np.argmax(np.where(covered, z, -np.inf), axis=1)
                rows = np.arange(len(selected))
                barycentric = np.stack([1-u[rows, chosen]-v[rows, chosen], u[rows, chosen], v[rows, chosen]], 1)
                colour = (values[np.asarray(indices)[chosen]] * barycentric[:, :, None]).sum(1)
                result[selected] = np.where(np.isfinite(best)[:, None], colour, np.nan)
        return result.reshape(x.shape + ((3,) if values is not None else ()))


@lru_cache(maxsize=1)
def terrain():
    entries = [entry for entry in manifest()['meshes'] if entry['name'].startswith('SM_BM_BT_Terrain_')]
    assert len(entries) == 56, 'Current Belmonte terrain coverage changed; review the source census'
    return Surface(np.concatenate([triangles(LIBRARY / entry['path']) for entry in entries]))


@lru_cache(maxsize=1)
def terrain_colours():
    """Sample the rendered four-layer base colours; neutral texture grain stays in the shader."""
    data = manifest()
    placed = {entry['asset']: entry['materials'] for entry in data['placements']}
    faces, colours = [], []
    for entry in data['meshes']:
        if not entry['name'].startswith('SM_BM_BT_Terrain_'):
            continue
        palettes = []
        for path in placed[entry['source_asset']]:
            material = data['materials'][path]
            vectors = material['vectors']
            layers = np.array(list(TERRAIN_LAYERS.values()))
            tint = np.array(vectors.get('Tint', [1., 1., 1.])[:3]) * vectors.get('StableColor', [1., 1., 1.])[:3]
            palettes.append((layers, tint * material['scalars'].get('Brightness', 1.)))
        f, c = triangles(LIBRARY / entry['path'], palettes)
        faces.append(f); colours.append(c)
    return Surface(np.concatenate(faces), np.concatenate(colours))
