"""Self-contained GLB export and read-back proof against the Node geometry arrays."""
import json
from pathlib import Path
import struct

import numpy as np

from .frontend import sha


def write_glb(scene, path):
    """@cc [owner:fontanierh,label:correctness] editor-display-parity
    Preserve topology, native metre axes and piece identity. Float32 positions
    MUST match the editor's BufferGeometry cast. Exports MUST remain unaccepted.
    """
    doc = {'asset': {'version': '2.0', 'generator': 'Atelier pinned editor diagnostic'},
           'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
           'buffers': [], 'bufferViews': [], 'accessors': [],
           'materials': [{'name': 'editor concrete', 'doubleSided': True,
                          'pbrMetallicRoughness': {'metallicFactor': 0, 'roughnessFactor': .88}},
                         {'name': 'editor terrain', 'doubleSided': True,
                          'pbrMetallicRoughness': {'baseColorFactor': [.48, .5, .42, 1],
                                                 'metallicFactor': 0, 'roughnessFactor': 1}}],
           'extras': {'label': 'UNACCEPTED EDITOR DIAGNOSTIC', 'accepted': False,
                      'pieces_sha256': scene.metadata['pieces_sha256'],
                      'park_sha256': scene.metadata['park_sha256'],
                      'terrain': scene.metadata['terrain'], 'rev': scene.metadata.get('rev'),
                      'frame': 'native metres, y up; world altitude = y + 680'}}
    binary = bytearray()

    def accessor(a, kind, component, bounds=False):
        a = np.asarray(a, dtype='<u4' if component == 5125 else '<f4')
        offset = len(binary)
        binary.extend(a.tobytes())
        view = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': a.nbytes})
        record = {'bufferView': view, 'componentType': component, 'count': len(a), 'type': kind}
        if bounds and len(a):
            record.update(min=a.min(axis=0).tolist(), max=a.max(axis=0).tolist())
        doc['accessors'].append(record)
        return len(doc['accessors']) - 1

    def mesh(m, name, extras, colors=None, terrain=False):
        attrs = {'POSITION': accessor(m.V, 'VEC3', 5126, True),
                 'NORMAL': accessor(m.N, 'VEC3', 5126)}
        if colors is not None:
            attrs['COLOR_0'] = accessor(colors, 'VEC3', 5126)
        primitive = {'attributes': attrs, 'indices': accessor(m.F.ravel(), 'SCALAR', 5125),
                     'mode': 4, 'material': int(terrain)}
        i = len(doc['meshes'])
        doc['meshes'].append({'name': name, 'primitives': [primitive], 'extras': extras})
        doc['nodes'].append({'name': name, 'mesh': i})
        doc['scenes'][0]['nodes'].append(i)

    for piece in scene.pieces:
        metadata = {k: v for k, v in piece.metadata.items() if k not in ('arrays', 'stations')}
        metadata['centerline'] = piece.centerline.tolist()
        mesh(piece.mesh, piece.metadata['id'], metadata, piece.colors)
    for ground in scene.terrain:
        mesh(ground, ground.features[0], {'display_only': True, 'type': 'terrain'}, terrain=True)
    doc['buffers'] = [{'byteLength': len(binary)}]
    encoded = json.dumps(doc, separators=(',', ':'), allow_nan=False).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += b'\0' * (-len(binary) % 4)
    contents = (struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary)) +
                struct.pack('<I4s', len(encoded), b'JSON') + encoded +
                struct.pack('<I4s', len(binary), b'BIN\0') + binary)
    Path(path).write_bytes(contents)


def read_glb(path):
    """Decode the exported accessor bytes, not the arrays passed to the writer."""
    data = Path(path).read_bytes()
    magic, version, size = struct.unpack_from('<4sII', data)
    if magic != b'glTF' or version != 2 or size != len(data):
        raise ValueError('invalid GLB header')
    length, kind = struct.unpack_from('<I4s', data, 12)
    if kind != b'JSON':
        raise ValueError('missing GLB JSON')
    doc = json.loads(data[20:20 + length])
    start = 20 + length
    binary_length, kind = struct.unpack_from('<I4s', data, start)
    if kind != b'BIN\0' or start + 8 + binary_length != size:
        raise ValueError('invalid GLB binary chunk')
    binary = data[start + 8:]

    def array(index):
        a = doc['accessors'][index]
        v = doc['bufferViews'][a['bufferView']]
        width = {'SCALAR': 1, 'VEC3': 3}[a['type']]
        dtype = {5125: '<u4', 5126: '<f4'}[a['componentType']]
        return np.frombuffer(binary, dtype, a['count'] * width,
                             v.get('byteOffset', 0) + a.get('byteOffset', 0)).reshape(-1, width)

    meshes = []
    for m in doc['meshes']:
        p = m['primitives'][0]
        arrays = {key: array(value) for key, value in p['attributes'].items()}
        arrays['indices'] = array(p['indices']).reshape(-1, 3)
        meshes.append((m, arrays))
    return doc, meshes


def compare(scene, glb):
    """Every indexed vertex is checked. With identical triangles the maximum
    vertex error bounds the entire corresponding triangle surface, not just a
    sampled subset. This proves serialization parity, not independent geometry
    correctness, topology, collision tolerances or native riding acceptance.
    """
    doc, meshes = read_glb(glb)
    if doc['extras'].get('accepted') is not False or len(meshes) != len(scene.pieces) + len(scene.terrain):
        raise ValueError('wrong diagnostic scene')
    report = {'schema': 'craterpark-editor-parity/1', 'accepted': False,
              'pieces_sha256': scene.metadata['pieces_sha256'], 'park_sha256': scene.metadata['park_sha256'],
              'glb_sha256': sha(Path(glb).read_bytes()), 'rev': scene.metadata.get('rev'),
              'terrain': scene.metadata['terrain'], 'pieces': [], 'by_type': {},
              'proof': 'All Node vertices and indexed triangles compared with decoded GLB. '
                       'Corresponding vertex error bounds every point of every triangle. '
                       'This is serialization parity, not independent geometry or ride certification.'}
    for piece, (m, arrays) in zip(scene.pieces, meshes):
        if m['name'] != piece.metadata['id'] or not np.array_equal(arrays['indices'], piece.mesh.F):
            raise ValueError('piece identity or triangle topology changed')
        delta = arrays['POSITION'].astype('f8') - piece.mesh.V
        center = np.asarray(m['extras']['centerline'], 'f8').reshape(-1, 3)
        center_error = float(np.linalg.norm(center - piece.centerline, axis=1).max(initial=0))
        same_display = all(np.array_equal(arrays[key], source.astype('f4')) for key, source in
                           [('POSITION', piece.mesh.V), ('NORMAL', piece.mesh.N), ('COLOR_0', piece.colors)])
        error = float(np.linalg.norm(delta, axis=1).max(initial=0))
        if not same_display or center_error != 0 or error > .001:
            raise ValueError(f'{m["name"]}: export parity failed')
        row = {'id': m['name'], 'type': piece.metadata['type'], 'vertices': len(piece.mesh.V),
               'triangles': len(piece.mesh.F), 'centerline_max_error_m': center_error,
               'surface_max_error_bound_m': error, 'editor_float32_exact': same_display}
        report['pieces'].append(row)
        t = report['by_type'].setdefault(row['type'], {'pieces': 0, 'vertices': 0, 'triangles': 0,
                    'centerline_max_error_m': 0., 'surface_max_error_bound_m': 0., 'editor_float32_exact': True})
        for key in ('vertices', 'triangles'):
            t[key] += row[key]
        t['pieces'] += 1
        for key in ('centerline_max_error_m', 'surface_max_error_bound_m'):
            t[key] = max(t[key], row[key])
    for ground, (_, arrays) in zip(scene.terrain, meshes[len(scene.pieces):]):
        if not np.array_equal(arrays['POSITION'], ground.V.astype('f4')) or not np.array_equal(arrays['indices'], ground.F):
            raise ValueError('display terrain changed')
    report['display_terrain_float32_exact'] = True
    report['parity_ok'] = True
    return report
