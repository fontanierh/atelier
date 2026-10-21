"""Spatially partition an identity-node static GLB without changing corner attribute bytes."""
from copy import deepcopy
import math
import struct

from .gltf import glb_pack, glb_parts
from .mesh_partition import face_groups


COMPONENTS = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2), 5123: ('H', 2),
              5125: ('I', 4), 5126: ('f', 4)}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def _natural(value):
    if type(value) is not int or value < 0:
        raise ValueError('Invalid static GLB integer')
    return value


def split(data, bounds, *, triangle_limit=32768, frame=(1, -3, 2)):
    """@cc [owner:fontanierh,label:correctness] exact-bounded-static-glb-pieces
    Every source triangle MUST occur exactly once, preserving winding, material identity and
    every attribute's encoded corner bytes. Each piece MUST fit the triangle budget. Fixed
    caller bounds determine subdivision; the signed axis frame affects grouping/bounds only.
    Unsupported transforms, skins, animation, morphs, sparse or compressed geometry MUST
    refuse. Small supported models MUST retain their exact original file bytes. This pure
    operation does not change instance, collision, shadow or cull policy; callers must preserve
    those policies and bind all generated members in their normal source/native inventories.
    """
    if (not isinstance(frame, (tuple, list)) or len(frame) != 3
            or any(type(axis) is not int for axis in frame) or {abs(axis) for axis in frame} != {1, 2, 3}):
        raise ValueError('Invalid signed static GLB axis frame')
    doc, binary = glb_parts(data)
    if (len(doc.get('buffers', [])) != 1 or 'uri' in doc['buffers'][0]
            or doc.get('extensions') or doc['buffers'][0].get('extensions')
            or _natural(doc['buffers'][0]['byteLength']) > len(binary)
            or doc.get('skins') or doc.get('animations') or len(doc.get('nodes', [])) != 1
            or len(doc.get('meshes', [])) != 1):
        raise ValueError('Expected one embedded, unanimated identity-node static mesh')
    node = doc['nodes'][0]
    if set(node) - {'mesh', 'name', 'extras'} or node.get('mesh') != 0:
        raise ValueError('Static mesh node must have identity transform and no children')
    if doc.get('scene', 0) != 0 or doc.get('scenes') != [{'nodes': [0]}]:
        # Scene names/extras are harmless; retain them when the active membership is exact.
        scenes = doc.get('scenes', [])
        if len(scenes) != 1 or scenes[0].get('nodes') != [0] or doc.get('scene', 0) != 0:
            raise ValueError('Static GLB scene membership is not exclusive')
    mesh = doc['meshes'][0]
    if set(mesh) - {'name', 'primitives', 'extras'} or not mesh.get('primitives'):
        raise ValueError('Unsupported static mesh semantics')
    decoded = {}

    def view_bytes(index):
        view = doc['bufferViews'][_natural(index)]
        offset, size = _natural(view.get('byteOffset', 0)), _natural(view['byteLength'])
        if view.get('extensions') or view.get('buffer', 0) != 0 or offset+size > doc['buffers'][0]['byteLength']:
            raise ValueError('Escaping static GLB buffer view')
        return view, binary[offset:offset+size]

    def accessor(index):
        index = _natural(index)
        if index not in decoded:
            source = doc['accessors'][index]
            if set(source) - {'bufferView', 'byteOffset', 'componentType', 'normalized', 'count',
                              'type', 'max', 'min', 'name', 'extras'}:
                raise ValueError('Unsupported static GLB accessor')
            component, width = source['componentType'], WIDTHS[source['type']]
            code, size = COMPONENTS[component]
            count, offset = _natural(source['count']), _natural(source.get('byteOffset', 0))
            view, payload = view_bytes(source['bufferView'])
            stride = _natural(view.get('byteStride', width*size))
            if (not count or stride < width*size or offset % size
                    or view.get('byteOffset', 0) % size
                    or offset+(count-1)*stride+width*size > len(payload)):
                raise ValueError('Invalid static GLB accessor extent')
            rows = [payload[offset+i*stride:offset+i*stride+width*size] for i in range(count)]
            values = [struct.unpack('<'+code*width, row) for row in rows]
            if component == 5126 and any(not math.isfinite(v) for row in values for v in row):
                raise ValueError('Nonfinite static GLB attribute')
            decoded[index] = source, rows, values
        return decoded[index]

    vertices, faces, ownership, primitives = [], [], [], []
    for primitive_index, primitive in enumerate(mesh['primitives']):
        if set(primitive) - {'attributes', 'indices', 'material', 'mode', 'extras'} or primitive.get('mode', 4) != 4:
            raise ValueError('Expected uncompressed static triangles without morph targets')
        position, _, values = accessor(primitive['attributes']['POSITION'])
        if position['componentType'] != 5126 or position['type'] != 'VEC3' or position.get('normalized'):
            raise ValueError('Expected float32 static positions')
        attributes = {key: accessor(value) for key, value in primitive['attributes'].items()}
        if any(len(rows) != len(values) for _, rows, _ in attributes.values()):
            raise ValueError('Static attribute vertex counts disagree')
        indices, _, raw_indices = accessor(primitive['indices'])
        if (indices['type'] != 'SCALAR' or indices['componentType'] not in (5121, 5123, 5125)
                or indices.get('normalized') or len(raw_indices) % 3):
            raise ValueError('Invalid static triangle indices')
        local_faces = [tuple(value[0] for value in raw_indices[i:i+3]) for i in range(0, len(raw_indices), 3)]
        if any(index >= len(values) for face in local_faces for index in face):
            raise ValueError('Escaping static triangle vertex')
        material = _natural(primitive['material'])
        if material >= len(doc['materials']):
            raise ValueError('Escaping static triangle material')
        offset = len(vertices)
        vertices.extend(tuple(row[abs(axis)-1]*(1 if axis > 0 else -1) for axis in frame) for row in values)
        faces.extend(tuple(offset+index for index in face) for face in local_faces)
        ownership.extend((primitive_index, i) for i in range(len(local_faces)))
        primitives.append((primitive, attributes, indices, local_faces))
    groups = face_groups(vertices, faces, bounds, triangle_limit=triangle_limit)
    if len(groups) == 1 and groups[0][0] == '':
        return [{'suffix': '', 'data': data, 'triangles': len(faces),
                 'materials': tuple(range(len(doc['materials']))), 'bounds': _bounds(vertices)}]
    result = []
    for suffix, selected in groups:
        output, blob = deepcopy(doc), bytearray()
        output['accessors'], output['bufferViews'] = [], []

        def add_view(payload, target=None):
            blob.extend(b'\0'*(-len(blob) % 4))
            view = {'buffer': 0, 'byteOffset': len(blob), 'byteLength': len(payload)}
            if target is not None: view['target'] = target
            index = len(output['bufferViews'])
            output['bufferViews'].append(view)
            blob.extend(payload)
            return index

        # Images may share a source buffer view. Keep image/texture references and bytes;
        # unused geometry buffer views and attribute rows do not enter the pieces.
        image_views = {}
        for image in output.get('images', []):
            if 'bufferView' in image:
                index = image['bufferView']
                if index not in image_views:
                    image_views[index] = add_view(view_bytes(index)[1])
                image['bufferView'] = image_views[index]

        def add_accessor(source, payload, values, target):
            item = {key: value for key, value in source.items()
                    if key not in ('bufferView', 'byteOffset', 'count', 'min', 'max')}
            item.update(bufferView=add_view(payload, target), count=len(values))
            if 'min' in source or 'max' in source:
                item['min'] = [min(row[i] for row in values) for i in range(len(values[0]))]
                item['max'] = [max(row[i] for row in values) for i in range(len(values[0]))]
            index = len(output['accessors'])
            output['accessors'].append(item)
            return index

        chosen = {}
        for face in selected:
            primitive_index, local_face = ownership[face]
            chosen.setdefault(primitive_index, []).append(local_face)
        materials = sorted({primitives[index][0]['material'] for index in chosen})
        output['materials'] = [deepcopy(doc['materials'][index]) for index in materials]
        made = []
        for primitive_index, local in chosen.items():
            primitive, attributes, indices, local_faces = primitives[primitive_index]
            used = sorted({index for face in local for index in local_faces[face]})
            remap = {value: index for index, value in enumerate(used)}
            current = {key: deepcopy(value) for key, value in primitive.items()
                       if key not in ('attributes', 'indices', 'material')}
            current['attributes'] = {
                key: add_accessor(source, b''.join(rows[index] for index in used),
                                  [values[index] for index in used], 34962)
                for key, (source, rows, values) in attributes.items()}
            mapped = [remap[index] for face in local for index in local_faces[face]]
            code = COMPONENTS[indices['componentType']][0]
            current['indices'] = add_accessor(indices, struct.pack('<'+code*len(mapped), *mapped),
                                               [(value,) for value in mapped], 34963)
            current['material'] = materials.index(primitive['material'])
            made.append(current)
        output['meshes'][0]['primitives'] = made
        for item in (output['nodes'][0], output['meshes'][0]):
            if 'name' in item: item['name'] += '_Piece'+suffix
        output['buffers'] = [dict(deepcopy(doc['buffers'][0]), byteLength=len(blob))]
        points = [vertices[index] for face in selected for index in faces[face]]
        result.append({'suffix': suffix, 'data': glb_pack(output, bytes(blob)), 'triangles': len(selected),
                       'materials': tuple(materials), 'bounds': _bounds(points)})
    return result


def _bounds(vertices):
    return tuple(tuple(function(row[axis] for row in vertices) for axis in range(3)) for function in (min, max))
