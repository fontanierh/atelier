"""Hakuba's prop source GLBs, in plain NumPy: `glb` writes a `full` node coloured per vertex in linear RGB, or drawn
with textured materials, and an optional `collision` node; `prop` writes one prop with its origin at its footprint's
centre; `read` returns another GLB's triangles; `rename_images` repoints a GLB's images. `convert.py` in Blender,
`crater_park.py` and `transport.py` without it all write the same shape."""
import base64
import json
import struct

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


def prop(position, normal, colour, triangles, output, textured=None):
    """Write one prop: corners' map-frame `position`, `normal` and linear `colour` (RGB or RGBA) and `triangles` of
    corner indices, painted per vertex (alpha 0, no motion), or with `textured`, (uv, face material, materials) as
    `glb` takes them, drawn as a textured surface times that colour, materials that draw alike joined. Its origin
    moves to the centre of its footprint, 1 cm above its lowest point, as `convert.py` places it; returns that origin
    in the source frame and the model's size."""
    position = np.asarray(position, np.float64)
    colour = np.asarray(colour, np.float32)
    if colour.shape[1] == 3:
        colour = np.hstack([colour, np.full((len(colour), 1), 1.0 if textured else 0.0, np.float32)])
    triangles = np.asarray(triangles, np.int64).reshape(-1, 3)
    used = position[np.unique(triangles)]
    low, high = used.min(axis=0), used.max(axis=0)
    origin = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2] + 0.01])
    node = ['full', SURFACE if textured else {'vertex_paint': PAINT}, position - origin,
            np.asarray(normal, np.float32), colour, triangles]
    materials = None
    if textured:
        uv, face_material, materials = textured
        # Materials that draw alike (the same texture, colour and sides) become one, drawn as one part.
        keys = [(m['texture'], tuple(m['colour']), m['two_sided']) for m in materials]
        kinds = list(dict.fromkeys(keys))
        alike = np.array([kinds.index(key) for key in keys])
        materials = [materials[keys.index(key)] for key in kinds]
        node += [np.asarray(uv, np.float32), alike[np.asarray(face_material)]]
    glb([tuple(node)], output, materials)
    return origin.tolist(), float(max(high - low))


def _matrix(node):
    if 'matrix' in node:
        return np.array(node['matrix'], float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0.0, 0.0, 0.0, 1.0])
    r = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    m = np.eye(4)
    m[:3, :3] = r * np.array(node.get('scale', [1.0, 1.0, 1.0]))
    m[:3, 3] = node.get('translation', [0.0, 0.0, 0.0])
    return m


def read(path):
    """A GLB's document, its images' bytes by index, and every mesh node's triangles in the map frame (x east, y north,
    z up): (corner positions (n, 3, 3), corner normals (n, 3, 3), corner UVs (n, 3, 2), the material index per
    triangle), with each node's transform applied."""
    data = open(path, 'rb').read()
    length = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + length])
    binary = data[20 + length + 8:]

    def accessor(index):
        acc = doc['accessors'][index]
        view = doc['bufferViews'][acc['bufferView']]
        kind = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[acc['componentType']]
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[acc['type']]
        start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
        out = np.frombuffer(binary, kind, acc['count'] * width, start).reshape(-1, width).astype(np.float64)
        if acc.get('normalized'):
            out /= {5123: 65535.0, 5121: 255.0}[acc['componentType']]
        return out

    images = {}
    for k, image in enumerate(doc.get('images', [])):
        if 'bufferView' in image:
            view = doc['bufferViews'][image['bufferView']]
            start = view.get('byteOffset', 0)
            images[k] = binary[start:start + view['byteLength']]
        elif image.get('uri', '').startswith('data:'):
            images[k] = base64.b64decode(image['uri'].split(',', 1)[1])
    up = np.array([[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float)  # glTF Y-up to map Z-up
    parts = []

    def visit(index, parent):
        node = doc['nodes'][index]
        m = parent @ _matrix(node)
        if 'mesh' in node:
            normal_m = np.linalg.inv(m[:3, :3]).T
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode', 4) != 4:
                    continue
                attrs = primitive['attributes']
                p = accessor(attrs['POSITION'])
                n = accessor(attrs['NORMAL']) if 'NORMAL' in attrs else np.zeros_like(p)
                uv = accessor(attrs['TEXCOORD_0']) if 'TEXCOORD_0' in attrs else np.zeros((len(p), 2))
                if 'indices' in primitive:
                    idx = accessor(primitive['indices']).astype(np.int64).ravel()
                else:
                    idx = np.arange(len(p))
                p = (up @ np.c_[p @ m[:3, :3].T + m[:3, 3], np.ones(len(p))].T).T[:, :3]
                n = n @ normal_m.T
                n = (up[:3, :3] @ n.T).T
                n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
                tri = idx.reshape(-1, 3)
                parts.append((p[tri], n[tri], uv[tri], np.full(len(tri), primitive.get('material', -1))))
        for child in node.get('children', []):
            visit(child, m)

    scene = doc.get('scenes', [{}])[doc.get('scene', 0)]
    for root in scene.get('nodes', range(len(doc['nodes']))):
        visit(root, np.eye(4))
    return doc, images, parts


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
