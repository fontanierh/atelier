"""Read the committed scene and sample its actual terrain triangles."""
import hashlib
import json
from functools import lru_cache
from pathlib import Path
import sys

import numpy as np
from atelier.gltf import glb_pack, glb_parts
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from belmonte.terrain_palette import TERRAIN_LAYERS  # noqa: E402
from belmonte.query_surface import Surface as QuerySurface  # noqa: E402

LIBRARY = Path(__file__).resolve().parents[3] / 'assets/belmonte'
MANIFEST = LIBRARY / 'source.json'
FRAME = np.array([[1., 0., 0.], [0., 0., -1.], [0., 1., 0.]])


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
    return triangles_data(path.read_bytes(),palettes,label=path)


def triangles_data(data,palettes=None,*,label='encoded terrain source'):
    """Read complete query triangles directly from source data, before render exports."""
    doc, binary = glb_parts(data)

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
        assert not any(key in node for key in ('matrix', 'translation', 'rotation', 'scale')), (label, node)
        if 'mesh' not in node:
            continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            assert primitive.get('mode', 4) == 4
            vertices = read(primitive['attributes']['POSITION']).astype(float) @ FRAME.T
            faces = read(primitive['indices']).reshape(-1, 3)
            result.append(vertices[faces])
            if palettes is not None:
                assert doc.get('extras', {}).get('atelier_vertex_colours') == 'native-byte-rgb-linear-alpha', label
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


Surface = QuerySurface


@lru_cache(maxsize=2)
def terrain(natural=False):
    """The 56 terrain tiles. natural=True reads the untouched committed GLBs directly; natural=False evaluates
    the railway/station carving on the 4 valley tiles without mutating assets/belmonte/."""
    from belmonte import terrain as bm_terrain
    entries = [entry for entry in manifest()['meshes'] if entry['name'].startswith('SM_BM_BT_Terrain_')]
    assert len(entries) == 56, 'Current Belmonte terrain coverage changed; review the source census'
    parts = []
    for entry in entries:
        path = LIBRARY / entry['path']
        if not natural and entry['name'] in bm_terrain.VALLEY_CARVED_TILES:
            parts.append(bm_terrain.valley_tile_triangles(path))
        else:
            parts.append(triangles(path))
    return Surface(np.concatenate(parts))


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
