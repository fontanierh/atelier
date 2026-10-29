"""Writes Hakuba's painted prop source GLBs: a `full` node coloured per vertex in linear RGB, and an optional
`collision` node. Plain NumPy, so both `convert.py` in Blender and `crater_park.py` without it write the same shape."""
import json

import numpy as np

# The `full` node's extras: how Hakuba's painted props light their vertex colour.
PAINT = {
    'fill': 0.06, 'glow': 0.8, 'glow_min': [0.8, 0.35, 0.0], 'glow_max': [1.0, 0.72, 0.3],
    'haze_start_m': 30.0, 'haze_length_m': 9000.0, 'haze_colour': [0.0932, 0.2301, 0.5328],
}


def glb(nodes, path):
    """Write `nodes`, each (name, extras, position, normal, colour, triangles), as a GLB in glTF's Y-up frame."""
    blob = bytearray()
    views, accessors, meshes, gl_nodes = [], [], [], []

    def add(data, kind, target=None, minmax=False):
        data = np.ascontiguousarray(data)
        while len(blob) % 4:
            blob.append(0)
        view = {'buffer': 0, 'byteOffset': len(blob), 'byteLength': data.nbytes}
        if target:
            view['target'] = target
        views.append(view)
        blob.extend(data.tobytes())
        component = {np.dtype(np.uint16): 5123, np.dtype(np.uint32): 5125}.get(data.dtype, 5126)
        acc = {'bufferView': len(views) - 1, 'componentType': component, 'count': int(len(data)), 'type': kind}
        if minmax:
            acc['min'] = data.min(axis=0).tolist()
            acc['max'] = data.max(axis=0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    for name, extras, position, normal, colour, triangles in nodes:
        # Drop triangles whose stored 32-bit corners enclose no area.
        stored = position.astype(np.float32).astype(np.float64)
        a, b, c = (stored[triangles[:, k]] for k in range(3))
        triangles = triangles[(np.cross(b - a, c - a) ** 2).sum(axis=1) > 0.0]
        # Corners that store the same position, normal and colour become one vertex. Painted props draw no texture,
        # so their UVs are zero and never split a vertex.
        corners = triangles.ravel()
        p, nm = position[corners], normal[corners]
        columns = [np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1), np.stack([nm[:, 0], nm[:, 2], -nm[:, 1]], axis=1)]
        if colour is not None:
            columns.append(colour[corners])
        key = np.ascontiguousarray(np.hstack(columns).astype(np.float32))
        _, first, remap = np.unique(key.view(np.uint32), axis=0, return_index=True, return_inverse=True)
        vertices = key[first]
        attrs = {'POSITION': add(vertices[:, 0:3], 'VEC3', 34962, True), 'NORMAL': add(vertices[:, 3:6], 'VEC3', 34962),
                 'TEXCOORD_0': add(np.zeros((len(vertices), 2), dtype=np.float32), 'VEC2', 34962)}
        index_type = np.uint16 if len(vertices) < 65536 else np.uint32
        primitive = {'attributes': attrs, 'indices': add(remap.ravel().astype(index_type), 'SCALAR', 34963)}
        if colour is not None:
            attrs['COLOR_0'] = add(vertices[:, 6:10], 'VEC4', 34962)
            primitive['material'] = 0
        meshes.append({'primitives': [primitive]})
        node = {'mesh': len(meshes) - 1, 'name': name}
        if extras:
            node['extras'] = extras
        gl_nodes.append(node)
    while len(blob) % 4:
        blob.append(0)
    doc = {
        'asset': {'version': '2.0', 'generator': 'hakuba_port'}, 'scene': 0,
        'scenes': [{'nodes': list(range(len(gl_nodes)))}], 'nodes': gl_nodes, 'meshes': meshes,
        'materials': [{'name': 'Painted surface', 'pbrMetallicRoughness': {'metallicFactor': 0.0},
                       'extensions': {'KHR_materials_specular': {'specularFactor': 0}}}],
        'extensionsUsed': ['KHR_materials_specular'],
        'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(blob)}],
    }
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    with open(path, 'wb') as f:
        f.write(b'glTF' + (2).to_bytes(4, 'little') + (28 + len(text) + len(blob)).to_bytes(4, 'little'))
        f.write(len(text).to_bytes(4, 'little') + b'JSON' + text)
        f.write(len(blob).to_bytes(4, 'little') + b'BIN\0' + bytes(blob))
