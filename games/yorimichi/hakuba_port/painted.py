"""Writes Hakuba's prop source GLBs: a `full` node coloured per vertex in linear RGB, or drawn with textured
materials, and an optional `collision` node. Plain NumPy, so both `convert.py` in Blender and `crater_park.py` without
it write the same shape."""
import json

import numpy as np

# The `full` node's extras: how Hakuba's painted props light their vertex colour.
PAINT = {
    'fill': 0.06, 'glow': 0.8, 'glow_min': [0.8, 0.35, 0.0], 'glow_max': [1.0, 0.72, 0.3],
    'haze_start_m': 30.0, 'haze_length_m': 9000.0, 'haze_colour': [0.0932, 0.2301, 0.5328],
}
# The `full` node's extras for a textured prop: Hakuba's textured surface response, with the painted props' haze.
SURFACE = {'surface_paint': {key: PAINT[key] for key in ('haze_start_m', 'haze_length_m', 'haze_colour')}}


def glb(nodes, path, materials=None):
    """Write `nodes`, each (name, extras, position, normal, colour, triangles), as a GLB in glTF's Y-up frame.

    With `materials`, each {'name', 'colour' (linear RGB), 'texture' (a Hakuba texture asset's name, or None),
    'two_sided'}, a node may add (uv, face material): its corners' texture positions and each triangle's index into
    `materials`, and draws one primitive per material; `colour` then multiplies the material's texture and colour."""
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

    for name, extras, position, normal, colour, triangles, *textured in nodes:
        uv, face_material = textured or (None, None)
        # Drop triangles whose stored 32-bit corners enclose no area.
        stored = position.astype(np.float32).astype(np.float64)
        a, b, c = (stored[triangles[:, k]] for k in range(3))
        area = (np.cross(b - a, c - a) ** 2).sum(axis=1) > 0.0
        triangles = triangles[area]
        if face_material is None:
            parts = [(0 if colour is not None else None, triangles)]
        else:
            face_material = face_material[area]
            parts = [(int(m), triangles[face_material == m]) for m in np.unique(face_material)]
        primitives = []
        for material, part in parts:
            # Corners that store the same position, normal, colour and texture position become one vertex. Painted
            # props draw no texture, so their UVs are zero and never split a vertex.
            corners = part.ravel()
            p, nm = position[corners], normal[corners]
            columns = [np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1),
                       np.stack([nm[:, 0], nm[:, 2], -nm[:, 1]], axis=1)]
            if colour is not None:
                columns.append(colour[corners])
            if uv is not None:
                columns.append(uv[corners])
            key = np.ascontiguousarray(np.hstack(columns).astype(np.float32))
            _, first, remap = np.unique(key.view(np.uint32), axis=0, return_index=True, return_inverse=True)
            vertices = key[first]
            texcoord = vertices[:, -2:] if uv is not None else np.zeros((len(vertices), 2), dtype=np.float32)
            attrs = {'POSITION': add(vertices[:, 0:3], 'VEC3', 34962, True),
                     'NORMAL': add(vertices[:, 3:6], 'VEC3', 34962), 'TEXCOORD_0': add(texcoord, 'VEC2', 34962)}
            index_type = np.uint16 if len(vertices) < 65536 else np.uint32
            primitive = {'attributes': attrs, 'indices': add(remap.ravel().astype(index_type), 'SCALAR', 34963)}
            if colour is not None:
                attrs['COLOR_0'] = add(vertices[:, 6:10], 'VEC4', 34962)
            if material is not None:
                primitive['material'] = material
            primitives.append(primitive)
        meshes.append({'primitives': primitives})
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
    if materials is not None:
        textures = sorted({m['texture'] for m in materials if m['texture']})
        doc['materials'] = []
        for m in materials:
            pbr = {'metallicFactor': 0.0, 'roughnessFactor': 1.0, 'baseColorFactor': [*map(float, m['colour']), 1.0]}
            if m['texture']:
                pbr['baseColorTexture'] = {'index': textures.index(m['texture'])}
            doc['materials'].append({'name': m['name'], 'pbrMetallicRoughness': pbr, 'doubleSided': m['two_sided'],
                                     'extensions': {'KHR_materials_specular': {'specularFactor': 0}}})
        if textures:
            doc['images'] = [{'uri': f'../../textures/{t}/{t}.ktx2'} for t in textures]
            doc['textures'] = [{'source': k, 'sampler': 0} for k in range(len(textures))]
            # Repeating, smoothed between mipmap levels.
            doc['samplers'] = [{'wrapS': 10497, 'wrapT': 10497, 'magFilter': 9729, 'minFilter': 9987}]
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    with open(path, 'wb') as f:
        f.write(b'glTF' + (2).to_bytes(4, 'little') + (28 + len(text) + len(blob)).to_bytes(4, 'little'))
        f.write(len(text).to_bytes(4, 'little') + b'JSON' + text)
        f.write(len(blob).to_bytes(4, 'little') + b'BIN\0' + bytes(blob))


def rename_images(path, names):
    """Point the GLB at `path`'s images named by `names` ({old uri: new uri}) at their new URIs, in place."""
    data = open(path, 'rb').read()
    length = int.from_bytes(data[12:16], 'little')
    doc = json.loads(data[20:20 + length])
    for image in doc.get('images', []):
        image['uri'] = names.get(image['uri'], image['uri'])
    text = json.dumps(doc, separators=(',', ':')).encode()
    text += b' ' * (-len(text) % 4)
    rest = data[20 + length:]
    with open(path, 'wb') as f:
        f.write(b'glTF' + (2).to_bytes(4, 'little') + (20 + len(text) + len(rest)).to_bytes(4, 'little'))
        f.write(len(text).to_bytes(4, 'little') + b'JSON' + text + rest)
