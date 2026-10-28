"""Blender script: turn Yorimichi export meshes into Hakuba source props.

Run as `blender -b --threads 3 -P convert.py -- JOBS.json`. Each job names one source mesh (FBX or GLB) and one
output GLB. The output holds a node `full`, the visible mesh, coloured per vertex in linear RGB with alpha 0 (no
motion), and, when the source has `UCX_` hulls, a node `collision` holding them. Each material slot's colour comes
from the job: a flat `rgb`, an image's mean colour (`mean`) or the image sampled at each corner's UV (`sample`),
times its `gain`; a slot whose rule says `drop` loses its faces.
"""
import json
import sys

import bmesh
import bpy
import numpy as np

PAINT = {
    'fill': 0.06, 'glow': 0.8, 'glow_min': [0.8, 0.35, 0.0], 'glow_max': [1.0, 0.72, 0.3],
    'haze_start_m': 30.0, 'haze_length_m': 9000.0, 'haze_colour': [0.0932, 0.2301, 0.5328],
}

_images = {}


def image(path):
    """An image's linear RGB pixels as a (height, width, 3) array, cached by path."""
    if path not in _images:
        img = bpy.data.images.load(path, check_existing=True)
        img.colorspace_settings.name = 'sRGB'
        w, h = img.size
        px = np.empty(w * h * 4, dtype=np.float32)
        img.pixels.foreach_get(px)  # Blender converts to linear float pixels
        _images[path] = px.reshape(h, w, 4)[:, :, :3]
    return _images[path]


def slot_rules(job, names):
    """Each slot's colour rule, by slot index: a slot's own rule, its name before any `.001`, or the default."""
    return [job['slots'].get(n) or job['slots'].get(n.split('.')[0]) or job.get('default') or {} for n in names]


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def import_source(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if path.lower().endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o.type == 'MESH']


def join(objects, name):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if len(objects) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    o.name = o.data.name = name
    return o


def drop(o, job):
    """Delete the faces of every slot whose rule says `drop`, such as additive light that has no painted colour."""
    names = [m.name if m else '' for m in o.data.materials] or ['']
    dropped = {k for k, rule in enumerate(slot_rules(job, names)) if rule.get('drop')}
    if not dropped:
        return
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index in dropped], context='FACES')
    bm.to_mesh(o.data)
    bm.free()


def paint(o, job):
    """Write each corner's linear colour into a `Color` attribute: the product of what its slot's rule names, the
    source's vertex colour (`vertex`, decoded from sRGB once more with `decode`), an image's mean (`mean`) or its
    texel at the corner's UV (`sample`), a flat `rgb`, and a `gain`."""
    mesh = o.data
    names = [m.name if m else '' for m in mesh.materials] or ['']
    rules = slot_rules(job, names)
    n = len(mesh.loops)
    source = mesh.color_attributes.get('Color')
    existing = None
    if source is not None and source.domain == 'POINT':
        point = np.empty(len(mesh.vertices) * 4, dtype=np.float32)
        source.data.foreach_get('color', point)
        vi = np.empty(n, dtype=np.int32)
        mesh.loops.foreach_get('vertex_index', vi)
        existing = point.reshape(-1, 4)[vi, :3]
    elif source is not None:
        existing = np.empty(n * 4, dtype=np.float32)
        source.data.foreach_get('color', existing)
        existing = existing.reshape(-1, 4)[:, :3]
    uv = np.zeros((n, 2), dtype=np.float32)
    if mesh.uv_layers:
        flat = np.empty(n * 2, dtype=np.float32)
        mesh.uv_layers[0].data.foreach_get('uv', flat)
        uv = flat.reshape(-1, 2)
    material = np.zeros(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get('material_index', material)
    total = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get('loop_total', total)
    loop_material = np.repeat(material, total)
    colours = np.zeros((n, 4), dtype=np.float32)
    for k, rule in enumerate(rules):
        sel = loop_material == k
        if not sel.any():
            continue
        c = np.ones((int(sel.sum()), 3), dtype=np.float32)
        if rule.get('vertex') and existing is not None:
            c *= linear(existing[sel]) if rule.get('decode') else existing[sel]
        if 'mean' in rule:
            c *= image(rule['mean']).reshape(-1, 3).mean(axis=0)
        if 'sample' in rule:
            px = image(rule['sample'])
            h, w, _ = px.shape
            u, v = np.mod(uv[sel, 0], 1.0), np.mod(uv[sel, 1], 1.0)
            c *= px[(v * (h - 1)).astype(int), (u * (w - 1)).astype(int)]
        if not any(key in rule for key in ('vertex', 'mean', 'sample', 'rgb')):
            c *= 0.5
        c *= np.asarray(rule.get('rgb', [1.0, 1.0, 1.0]), dtype=np.float32) * rule.get('gain', 1.0)
        colours[sel, :3] = c
    for attr in list(mesh.color_attributes):
        mesh.color_attributes.remove(attr)
    attr = mesh.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    attr.data.foreach_set('color', colours.ravel())


def arrays(o, coloured):
    """A mesh's corners as flat float arrays in the map frame, and its triangles, without zero-area ones."""
    mesh = o.data
    mesh.calc_loop_triangles()
    n = len(mesh.loops)
    vi = np.empty(n, dtype=np.int32)
    mesh.loops.foreach_get('vertex_index', vi)
    co = np.empty(len(mesh.vertices) * 3, dtype=np.float64)
    mesh.vertices.foreach_get('co', co)
    position = co.reshape(-1, 3)[vi]
    normal = np.empty(n * 3, dtype=np.float32)
    mesh.corner_normals.foreach_get('vector', normal)
    uv = np.zeros(n * 2, dtype=np.float32)
    if mesh.uv_layers:
        mesh.uv_layers[0].data.foreach_get('uv', uv)
    colour = None
    if coloured:
        colour = np.empty(n * 4, dtype=np.float32)
        mesh.color_attributes['Color'].data.foreach_get('color', colour)
        colour = colour.reshape(-1, 4)
    triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get('loops', triangles)
    triangles = triangles.reshape(-1, 3)
    a, b, c = (position[triangles[:, k]] for k in range(3))
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1)
    triangles = triangles[area > 1e-10]
    return position, normal.reshape(-1, 3), uv.reshape(-1, 2), colour, triangles


def glb(nodes, path):
    """Write `nodes`, each (name, extras, position, normal, uv, colour, triangles), as a GLB in glTF's Y-up frame."""
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
        acc = {'bufferView': len(views) - 1, 'componentType': 5125 if data.dtype == np.uint32 else 5126,
               'count': int(len(data)), 'type': kind}
        if minmax:
            acc['min'] = data.min(axis=0).tolist()
            acc['max'] = data.max(axis=0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    for name, extras, position, normal, uv, colour, triangles in nodes:
        used, remap = np.unique(triangles.ravel(), return_inverse=True)
        p = position[used]
        attrs = {
            'POSITION': add(np.stack([p[:, 0], p[:, 2], -p[:, 1]], axis=1).astype(np.float32), 'VEC3', 34962, True),
        }
        nm = normal[used]
        attrs['NORMAL'] = add(np.stack([nm[:, 0], nm[:, 2], -nm[:, 1]], axis=1).astype(np.float32), 'VEC3', 34962)
        attrs['TEXCOORD_0'] = add(np.stack([uv[used, 0], 1.0 - uv[used, 1]], axis=1).astype(np.float32), 'VEC2', 34962)
        primitive = {'attributes': attrs, 'indices': add(remap.astype(np.uint32), 'SCALAR', 34963)}
        if colour is not None:
            attrs['COLOR_0'] = add(colour[used].astype(np.float32), 'VEC4', 34962)
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


def convert(job):
    """Convert one job. The model's lowest point must lie below its origin, so a model resting on its origin is
    lifted 1 cm; with `recentre`, the origin moves to the centre of its footprint, 1 cm above its lowest point. The
    result reports where the new origin is in the source frame."""
    objects = import_source(job['source'])
    hulls = [o for o in objects if o.name.startswith('UCX_')]
    visible = [o for o in objects if not o.name.startswith('UCX_')]
    if not visible:
        raise RuntimeError(f"{job['source']}: no visible mesh")
    full = join(visible, 'full')
    drop(full, job)
    paint(full, job)
    parts = [('full', {'vertex_paint': PAINT}, *arrays(full, True))]
    if hulls and job.get('collision', True):
        collision = join(hulls, 'collision')
        parts.append(('collision', None, *arrays(collision, False)))
    if len(parts[0][6]) == 0:
        raise RuntimeError(f"{job['source']}: no triangles with area")
    position = parts[0][2][np.unique(parts[0][6])]
    low, high = position.min(axis=0), position.max(axis=0)
    if job.get('recentre'):
        origin = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2] + 0.01])
    else:
        origin = np.array([0.0, 0.0, 0.0 if low[2] < 0.0 else low[2] + 0.01])
    parts = [(n, e, p - origin, *rest) for n, e, p, *rest in parts]
    glb(parts, job['output'])
    return {'output': job['output'], 'triangles': int(len(parts[0][6])), 'collision': len(parts) == 2,
                    'origin': origin.tolist()}


def main():
    jobs = json.load(open(sys.argv[sys.argv.index('--') + 1]))
    for job in jobs:
        try:
            print('CONVERTED', json.dumps(convert(job)), flush=True)
        except Exception as error:  # report every failure, then keep converting the others
            print('FAILED', json.dumps({'output': job['output'], 'error': str(error)}), flush=True)


main()
