from collections import Counter
import json
import struct

import pytest

from atelier.gltf import glb_pack, glb_parts
from atelier.gltf_partition import split


def model():
    vertices = []
    for slot in (0, 1):
        for x, y in ((2., 2.), (8., 2.), (2., 8.), (8., 8.)):
            for dx, dy in ((0., 0.), (.1, 0.), (0., .1)):
                vertices.append(struct.pack('<3f3f2f2f4H4fB3x', x+dx, slot*.05, -y-dy,
                                            0., 1., 0., .2, .3, .7, .8, 1, 65535, 1000, 50000,
                                            1., 0., 0., -1., slot))
    binary = b''.join(vertices)
    views = [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(binary), 'byteStride': 68}]
    accessors = []
    attrs = {}
    for key, offset, component, kind, normalized in (
        ('POSITION', 0, 5126, 'VEC3', False), ('NORMAL', 12, 5126, 'VEC3', False),
        ('TEXCOORD_0', 24, 5126, 'VEC2', False), ('TEXCOORD_1', 32, 5126, 'VEC2', False),
        ('COLOR_0', 40, 5123, 'VEC4', True), ('TANGENT', 48, 5126, 'VEC4', False),
        ('_ROLE', 64, 5121, 'SCALAR', False),
    ):
        item = dict(bufferView=0, byteOffset=offset, componentType=component, type=kind, count=24)
        if normalized: item['normalized'] = True
        if key == 'POSITION': item.update(min=[2., 0., -8.1], max=[8.1, .05, -2.])
        attrs[key] = len(accessors); accessors.append(item)
    primitives = []
    for slot in (0, 1):
        payload = struct.pack('<12H', *range(slot*12, (slot+1)*12))
        views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(payload)))
        binary += payload
        index = len(accessors)
        accessors.append(dict(bufferView=len(views)-1, componentType=5123, type='SCALAR', count=12))
        primitives.append(dict(attributes=attrs, indices=index, material=slot, mode=4))
    image = b'image bytes copied exactly'
    views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(image)))
    binary += image
    doc = dict(asset={'version': '2.0'}, buffers=[{'byteLength': len(binary)}],
               bufferViews=views, accessors=accessors, scenes=[{'nodes': [0]}], scene=0,
               nodes=[{'mesh': 0, 'name': 'Model'}], meshes=[{'name': 'Model', 'primitives': primitives}],
               materials=[{'name': name, 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}}}
                          for name in ('Slot_2', 'Slot_5')],
               images=[{'bufferView': len(views)-1, 'mimeType': 'image/png'}], textures=[{'source': 0}])
    return glb_pack(doc, binary)


def rows(doc, binary, index):
    widths = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
    sizes = {5121: 1, 5123: 2, 5125: 4, 5126: 4}
    item = doc['accessors'][index]; view = doc['bufferViews'][item['bufferView']]
    size = widths[item['type']]*sizes[item['componentType']]
    offset = view.get('byteOffset', 0)+item.get('byteOffset', 0)
    stride = view.get('byteStride', size)
    return [binary[offset+i*stride:offset+i*stride+size] for i in range(item['count'])]


def corners(data):
    doc, binary = glb_parts(data)
    found = []
    for primitive in doc['meshes'][0]['primitives']:
        index = primitive['indices']; code = {5121: 'B', 5123: 'H', 5125: 'I'}[doc['accessors'][index]['componentType']]
        indices = [struct.unpack('<'+code, row)[0] for row in rows(doc, binary, index)]
        attrs = {key: rows(doc, binary, value) for key, value in primitive['attributes'].items()}
        material = json.dumps(doc['materials'][primitive['material']], sort_keys=True)
        for i in range(0, len(indices), 3):
            found.append((material, tuple(tuple((key, attrs[key][vertex]) for key in sorted(attrs))
                                          for vertex in indices[i:i+3])))
    return Counter(found)


def test_bounded_pieces_preserve_every_encoded_corner_and_material_once():
    original = model()
    parts = split(original, (0., 0., 10., 10.), triangle_limit=2)
    assert len(parts) == 4
    assert all(part['triangles'] == 2 for part in parts)
    assert sum((corners(part['data']) for part in parts), Counter()) == corners(original)
    assert parts == split(original, (0., 0., 10., 10.), triangle_limit=2)
    for part in parts:
        doc, binary = glb_parts(part['data'])
        assert part['materials'] == (0, 1)
        assert all(doc['accessors'][p['attributes']['POSITION']]['count'] == 3
                   for p in doc['meshes'][0]['primitives'])
        image = doc['bufferViews'][doc['images'][0]['bufferView']]
        assert binary[image['byteOffset']:image['byteOffset']+image['byteLength']] == b'image bytes copied exactly'
        assert all(lo <= hi for lo, hi in zip(*part['bounds']))


def test_small_supported_model_is_byte_identical():
    original = model()
    part, = split(original, (0., 0., 10., 10.), triangle_limit=8)
    assert part['suffix'] == '' and part['data'] is original


@pytest.mark.parametrize('fault', ['transform', 'skin', 'animation', 'morph', 'sparse', 'compression',
                                  'view-compression', 'nonfinite', 'indices', 'attribute-count', 'wrong-mode'])
def test_unsupported_or_invalid_geometry_refuses(fault):
    doc, binary = glb_parts(model())
    if fault == 'transform': doc['nodes'][0]['translation'] = [1., 0., 0.]
    if fault == 'skin': doc['skins'] = [{'joints': [0]}]
    if fault == 'animation': doc['animations'] = [{}]
    if fault == 'morph': doc['meshes'][0]['primitives'][0]['targets'] = [{}]
    if fault == 'sparse': doc['accessors'][0]['sparse'] = {}
    if fault == 'compression': doc['meshes'][0]['primitives'][0]['extensions'] = {'KHR_draco_mesh_compression': {}}
    if fault == 'view-compression': doc['bufferViews'][0]['extensions'] = {'EXT_meshopt_compression': {}}
    if fault == 'nonfinite': binary = binary[:24]+struct.pack('<f', float('nan'))+binary[28:]
    if fault == 'indices':
        accessor = doc['accessors'][doc['meshes'][0]['primitives'][0]['indices']]
        offset = doc['bufferViews'][accessor['bufferView']]['byteOffset']
        binary = binary[:offset]+struct.pack('<H', 65535)+binary[offset+2:]
    if fault == 'attribute-count': doc['accessors'][1]['count'] -= 1
    if fault == 'wrong-mode': doc['meshes'][0]['primitives'][0]['mode'] = 1
    with pytest.raises(ValueError): split(glb_pack(doc, binary), (0., 0., 10., 10.), triangle_limit=2)


def test_fixed_bounds_and_axis_frame_are_required():
    for frame in ((0, 1, 2), (1, 1, 3), (1, 2), (True, 2, 3)):
        with pytest.raises(ValueError): split(model(), (0., 0., 10., 10.), frame=frame)
    with pytest.raises(ValueError, match='outside'):
        split(model(), (0., 0., 1., 1.), triangle_limit=2)
