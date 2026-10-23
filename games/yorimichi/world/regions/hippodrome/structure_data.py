"""Selected committed structure, transformed without writing an export."""
from hippodrome.mesh_data import _read, _encoded, PROPS, np

def structure(slug, spec):
    """A Tripo model scaled to its size (front axis, across, height) with its base at z = 0; glTF axes kept."""
    gltf, binary = _read(PROPS / slug / f'{slug}.glb')
    primitive = gltf['meshes'][0]['primitives'][0]
    view = lambda accessor: gltf['bufferViews'][gltf['accessors'][accessor]['bufferView']]
    count = lambda accessor: gltf['accessors'][accessor]['count']

    def array(accessor):
        v = view(accessor)
        start = v.get('byteOffset', 0) + gltf['accessors'][accessor].get('byteOffset', 0)
        return np.frombuffer(bytes(binary[start:start + count(accessor) * 12]), np.float32).reshape(-1, 3).copy()

    pos, nrm = array(primitive['attributes']['POSITION']), array(primitive['attributes']['NORMAL'])
    lo, hi = pos.min(0), pos.max(0)
    depth, across, height = spec['size']
    scale = np.array([depth / (hi[0] - lo[0]), height / (hi[1] - lo[1]), across / (hi[2] - lo[2])], np.float32)
    pos = (pos - np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2], np.float32)) * scale
    nrm = nrm / scale
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    for accessor, values in ((primitive['attributes']['POSITION'], pos), (primitive['attributes']['NORMAL'], nrm)):
        v = view(accessor)
        start = v.get('byteOffset', 0) + gltf['accessors'][accessor].get('byteOffset', 0)
        binary[start:start + values.nbytes] = values.astype(np.float32).tobytes()
    acc = gltf['accessors'][primitive['attributes']['POSITION']]
    acc['min'] = [float(v) for v in pos.min(0)]; acc['max'] = [float(v) for v in pos.max(0)]
    name = 'SM_HD_' + ''.join(part.title() for part in slug.split('_'))
    gltf['meshes'][0]['name'] = gltf['nodes'][0]['name'] = name
    gltf['materials'][0]['name'] = 'HD_' + ''.join(part.title() for part in slug.split('_'))
    return _encoded(gltf, binary), name, {'triangles': sum(count(p['indices']) // 3 for m in gltf['meshes'] for p in m['primitives']),
                  'min': [float(pos[:, 0].min()), float(-pos[:, 2].max()), float(pos[:, 1].min())],
                  'max': [float(pos[:, 0].max()), float(-pos[:, 2].min()), float(pos[:, 1].max())],
                  'material': gltf['materials'][0]['name']}
