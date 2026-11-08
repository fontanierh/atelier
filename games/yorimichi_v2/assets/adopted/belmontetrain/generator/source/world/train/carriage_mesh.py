"""Validate a bounded carriage node hierarchy without changing encoded geometry."""
import json
import math
import struct

import numpy as np

from atelier.export_manifest import TRIANGLE_LIMIT
from atelier.gltf_partition import COMPONENTS, WIDTHS


def geometry(doc, binary):
    """@cc [owner:fontanierh,label:correctness] complete-carriage-node-source
    A carriage packet MUST preserve each original node, instance, transform, extra,
    primitive, attribute encoding and material/embedded image binding. Unsupported
    animation, skinning, sparse/compressed geometry and escaping references MUST fail.
    Count every mesh instance toward the bounded primary's triangle limit.
    """
    json.dumps(doc, allow_nan=False)
    if (len(doc.get('buffers', [])) != 1 or set(doc['buffers'][0]) != {'byteLength'}
            or not 0 < doc['buffers'][0]['byteLength'] <= len(binary)
            or len(binary) - doc['buffers'][0]['byteLength'] > 3
            or doc.get('skins') or doc.get('animations') or doc.get('cameras') or doc.get('extensions')
            or len(doc.get('scenes', [])) != 1 or doc.get('scene', 0) != 0):
        raise ValueError('Unsupported carriage scene/buffer policy')
    def index(rows, value):
        if type(value) is not int or not 0 <= value < len(rows): raise ValueError('Escaping carriage reference')
        return rows[value]
    def view(value):
        row = index(doc.get('bufferViews', []), value)
        start, size = row.get('byteOffset', 0), row['byteLength']
        if (row.get('buffer', 0) != 0 or row.get('extensions') or type(start) is not int or type(size) is not int
                or start < 0 or size <= 0 or start + size > doc['buffers'][0]['byteLength']):
            raise ValueError('Escaping carriage buffer view')
        return row, binary[start:start + size]
    decoded = {}
    def accessor(value):
        if value in decoded: return decoded[value]
        row = index(doc.get('accessors', []), value)
        if (set(row) - {'bufferView', 'byteOffset', 'componentType', 'normalized', 'count', 'type', 'min', 'max', 'name', 'extras'}
                or row['componentType'] not in COMPONENTS or row['type'] not in WIDTHS):
            raise ValueError('Unsupported carriage corner channel')
        code, size = COMPONENTS[row['componentType']]; width = WIDTHS[row['type']]
        descriptor, data = view(row['bufferView']); count = row['count']; offset = row.get('byteOffset', 0)
        stride = descriptor.get('byteStride', size * width)
        if (type(count) is not int or count <= 0 or type(offset) is not int or offset < 0 or type(stride) is not int
                or stride < size * width or offset % size or descriptor.get('byteOffset', 0) % size
                or offset + (count - 1) * stride + size * width > len(data)):
            raise ValueError('Incomplete carriage channel extent')
        values = [struct.unpack_from('<' + code * width, data, offset + i * stride) for i in range(count)]
        if any(not math.isfinite(v) for item in values for v in item): raise ValueError('Nonfinite carriage channel')
        decoded[value] = row, values
        return decoded[value]
    meshes = []
    for mesh in doc.get('meshes', []):
        if set(mesh) - {'name', 'primitives', 'extras'} or not mesh.get('primitives'): raise ValueError('Unsupported carriage mesh')
        points = []; count = 0
        for primitive in mesh['primitives']:
            if set(primitive) - {'attributes', 'indices', 'material', 'mode', 'extras'} or primitive.get('mode', 4) != 4:
                raise ValueError('Unsupported carriage primitive')
            channels = {key: accessor(value) for key, value in primitive['attributes'].items()}
            if not {'POSITION', 'NORMAL'} <= set(channels): raise ValueError('Missing carriage positions/normals')
            position, values = channels['POSITION']
            if position['componentType'] != 5126 or position['type'] != 'VEC3' or position.get('normalized'):
                raise ValueError('Changed carriage position encoding')
            if any(row['count'] != position['count'] for row, _ in channels.values()): raise ValueError('Incomplete carriage corner channels')
            indices, ids = accessor(primitive['indices'])
            if (indices['type'] != 'SCALAR' or indices['componentType'] not in (5121, 5123, 5125)
                    or indices.get('normalized') or len(ids) % 3 or any(not 0 <= v[0] < len(values) for v in ids)):
                raise ValueError('Invalid carriage face indices')
            index(doc.get('materials', []), primitive['material'])
            points.extend(values[v[0]] for v in ids); count += len(ids) // 3
        meshes.append((count, np.asarray(points)))
    for image in doc.get('images', []):
        if 'uri' in image or image.get('mimeType') not in ('image/png', 'image/jpeg'): raise ValueError('Unbound carriage texture')
        view(image['bufferView'])
    for texture in doc.get('textures', []):
        index(doc.get('images', []), texture['source'])
        if 'sampler' in texture: index(doc.get('samplers', []), texture['sampler'])
    def textures(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.endswith('Texture') and isinstance(item, dict): index(doc.get('textures', []), item['index'])
                textures(item)
        elif isinstance(value, list):
            for item in value: textures(item)
    textures(doc.get('materials', []))
    visited = set(); points = []; total = 0
    def traverse(value, parent):
        nonlocal total
        node = index(doc.get('nodes', []), value)
        if value in visited: raise ValueError('Cyclic or repeated carriage node')
        visited.add(value)
        if set(node) - {'name', 'mesh', 'children', 'matrix', 'translation', 'rotation', 'scale', 'extras'}:
            raise ValueError('Unsupported carriage node policy')
        if 'matrix' in node:
            if {'translation', 'rotation', 'scale'} & set(node) or len(node['matrix']) != 16: raise ValueError('Ambiguous carriage transform')
            matrix = np.asarray(node['matrix'], float).reshape(4, 4).T
        else:
            t, q, s = (np.asarray(node.get(key, default), float) for key, default in
                       [('translation', [0, 0, 0]), ('rotation', [0, 0, 0, 1]), ('scale', [1, 1, 1])])
            if t.shape != (3,) or q.shape != (4,) or s.shape != (3,): raise ValueError('Invalid carriage TRS')
            x, y, z, w = q
            rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                                 [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                                 [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
            matrix = np.eye(4); matrix[:3, :3] = rotation @ np.diag(s); matrix[:3, 3] = t
        if not np.isfinite(matrix).all() or not np.array_equal(matrix[3], [0, 0, 0, 1]) or np.linalg.det(matrix[:3, :3]) == 0:
            raise ValueError('Invalid carriage node frame')
        world = parent @ matrix
        if 'mesh' in node:
            count, vertices = index(meshes, node['mesh']); total += count
            points.append(vertices @ world[:3, :3].T + world[:3, 3])
        for child in node.get('children', []): traverse(child, world)
    for root in doc['scenes'][0]['nodes']: traverse(root, np.eye(4))
    if len(visited) != len(doc['nodes']) or not 0 < total <= TRIANGLE_LIMIT: raise ValueError('Incomplete or oversized carriage primary')
    positions = np.concatenate(points)
    return dict(triangles=total, bounds=[positions.min(0).tolist(), positions.max(0).tolist()],
                slots=[material['name'] for material in doc.get('materials', [])])


def glb(doc, binary):
    """The existing runtime/Blender compact GLB encoding, with unchanged document order."""
    geometry(doc, binary)
    text = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    text += b' ' * (-len(text) % 4); binary += b'\0' * (-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28 + len(text) + len(binary)) + struct.pack('<I4s', len(text), b'JSON')
            + text + struct.pack('<I4s', len(binary), b'BIN\0') + binary)
