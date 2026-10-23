"""Read complete serialized static GLB triangle corners for bounded export diagnostics."""
from collections import Counter

import numpy as np
from atelier.gltf import glb_parts

TYPES = {5120: '<i1', 5121: '<u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read(path):
    doc, binary = glb_parts(path.read_bytes())
    def array(index):
        entry = doc['accessors'][index]
        if 'sparse' in entry or entry['type'] not in WIDTHS:
            raise ValueError('Unsupported diagnostic GLB accessor')
        view = doc['bufferViews'][entry['bufferView']]
        if view.get('buffer', 0) != 0: raise ValueError('External diagnostic GLB buffer')
        dtype = np.dtype(TYPES[entry['componentType']]); width = WIDTHS[entry['type']]
        offset = view.get('byteOffset', 0) + entry.get('byteOffset', 0)
        stride = view.get('byteStride', dtype.itemsize * width)
        value = np.ndarray((entry['count'], width), dtype=dtype, buffer=binary,
                           offset=offset, strides=(stride, dtype.itemsize)).copy()
        if entry.get('normalized'):
            info = np.iinfo(dtype)
            value = value.astype(np.float64) / info.max
            if dtype.kind == 'i': value = np.maximum(value, -1)
        if not np.isfinite(value).all(): raise ValueError('Nonfinite diagnostic GLB attribute')
        return value
    roots = doc['scenes'][doc.get('scene', 0)]['nodes']
    if len(roots) != 1: raise ValueError('Expected one explicit static mesh node')
    node = doc['nodes'][roots[0]]
    if 'children' in node or 'mesh' not in node: raise ValueError('Unexpected diagnostic mesh hierarchy')
    transform = tuple((key, tuple(node.get(key, default))) for key, default in (
        ('matrix', ()), ('translation', (0, 0, 0)), ('rotation', (0, 0, 0, 1)), ('scale', (1, 1, 1))))
    result = Counter()
    for primitive in doc['meshes'][node['mesh']]['primitives']:
        if primitive.get('mode', 4) != 4 or primitive.get('targets') or primitive.get('extensions'):
            raise ValueError('Unsupported diagnostic primitive')
        values = {key: array(index) for key, index in primitive['attributes'].items()}
        if not {'POSITION', 'NORMAL'} <= values.keys(): raise ValueError('Missing diagnostic geometry channels')
        indices = array(primitive['indices']).reshape(-1)
        if indices.dtype.kind not in 'iu' or len(indices) % 3: raise ValueError('Invalid triangle index array')
        material = doc['materials'][primitive['material']]['name']
        for triangle in indices.reshape(-1, 3):
            corners = tuple(tuple((key, tuple(float(v) for v in value[int(index)]))
                                  for key, value in sorted(values.items())) for index in triangle)
            result[(material, transform, corners)] += 1
    if not result: raise ValueError('Empty diagnostic GLB geometry')
    return result
