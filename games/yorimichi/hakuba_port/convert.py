"""Blender script: turn Yorimichi export meshes into Hakuba source props.

Run as `blender -b --threads 3 -P convert.py -- JOBS.json`. Each job names one source mesh (FBX or GLB) and one
output GLB. The output holds a node `full`, the visible mesh, and, when the source has `UCX_` hulls or the job names a
`collision_source`, a node `collision` holding them. Each corner's colour, in linear RGB, is the product of what its
material slot's rule names: a flat `rgb`, the source's vertex colour (`vertex`) and a `gain`. A slot whose rule names a
`texture` asset draws it on the mesh's own UVs, over the rule's `tile` (the UV span one repeat of the image covers, 1
by default), times that colour, and then the whole `full` node is a textured surface; on a mesh without UVs it shows
the texture's mean colour (`mean_rgb`) instead. Otherwise the colour alone is painted per vertex, with alpha 0 (no
motion). A slot whose rule says `drop` loses its faces. Corners that store the same position, normal, colour and
texture position share one vertex. A job's `turn`, a 3 by 3 rotation row by row, turns the visible mesh and its
hulls about the source origin first. A job's `keep`, a rectangle [west, south, east, north] in the source frame, keeps
only the visible faces whose centre lies in it, west and south edges included; with none there, the job writes no
GLB and reports itself `EMPTY`. A job's `ground_owned` slots lose their faces facing up (`UP`), a walking surface the
world's ground draws instead. A job's `meet`, segments in the source frame, is an edge its vertices within a couple of
centimetres of it move onto, first (`seam.py`).
"""
import json
import os
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from painted import PAINT, SURFACE, glb  # noqa: E402
from seam import meet  # noqa: E402


def slot_rules(job, names):
    """Each slot's colour rule, by slot index: a slot's own rule, its name before any `.001`, or the default."""
    return [job['slots'].get(n) or job['slots'].get(n.split('.')[0]) or job.get('default') or {} for n in names]


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def import_source(path, reset=True):
    if reset:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    before = set(bpy.data.objects)
    if path.lower().endswith('.fbx'):
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        bpy.ops.import_scene.gltf(filepath=path)
    return [o for o in bpy.data.objects if o.type == 'MESH' and o not in before]


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


# A ground-owned slot's face is a walking surface when its normal rises at least this steeply.
UP = 0.5


def ground_owned(o, slots):
    """Remove the faces of `slots` facing up, as `pier_path.py` takes them for the ground."""
    names = [m.name.split('.')[0] if m else '' for m in o.data.materials]
    turn = o.matrix_world.to_3x3().inverted().transposed()
    mesh = bmesh.new()
    mesh.from_mesh(o.data)
    up = [f for f in mesh.faces if names[f.material_index] in slots and (turn @ f.normal).normalized().z > UP]
    bmesh.ops.delete(mesh, geom=up, context='FACES')
    mesh.to_mesh(o.data)
    mesh.free()


def keep(o, rectangle):
    """Keep only `o`'s faces whose centre lies in `rectangle`, [west, south, east, north] in the source frame, its west
    and south edges included."""
    west, south, east, north = rectangle
    mesh = bmesh.new()
    mesh.from_mesh(o.data)
    centres = [o.matrix_world @ f.calc_center_median() for f in mesh.faces]
    outside = [f for f, c in zip(mesh.faces, centres) if not (west <= c.x < east and south <= c.y < north)]
    bmesh.ops.delete(mesh, geom=outside, context='FACES')
    mesh.to_mesh(o.data)
    mesh.free()


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
    source's vertex colour (`vertex`, decoded from sRGB once more with `decode`), a flat `rgb` and a `gain`, and the
    texture's mean (`mean_rgb`) where the mesh has no UVs to draw it on. Returns each slot's texture, or None."""
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
    material = np.zeros(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get('material_index', material)
    total = np.empty(len(mesh.polygons), dtype=np.int32)
    mesh.polygons.foreach_get('loop_total', total)
    loop_material = np.repeat(material, total)
    colours = np.zeros((n, 4), dtype=np.float32)
    textures = []
    for k, rule in enumerate(rules):
        texture = rule.get('texture') if mesh.uv_layers else None
        textures.append(texture)
        sel = loop_material == k
        if not sel.any():
            continue
        c = np.ones((int(sel.sum()), 3), dtype=np.float32)
        if rule.get('vertex') and existing is not None:
            c *= linear(existing[sel]) if rule.get('decode') else existing[sel]
        if rule.get('texture') and not texture:
            c *= np.asarray(rule['mean_rgb'], dtype=np.float32)
        if not any(key in rule for key in ('vertex', 'texture', 'rgb')):
            c *= 0.5
        c *= np.asarray(rule.get('rgb', [1.0, 1.0, 1.0]), dtype=np.float32) * rule.get('gain', 1.0)
        # Hakuba paints vertex colour in [0, 1], and a gain can push past it; a colour multiplying a texture may
        # brighten it, as a material lightening its image (a pale decal folded in by its mean) does.
        colours[sel, :3] = c if texture else np.clip(c, 0.0, 1.0)
    for attr in list(mesh.color_attributes):
        mesh.color_attributes.remove(attr)
    attr = mesh.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='CORNER')
    attr.data.foreach_set('color', colours.ravel())
    return textures


def arrays(o, coloured):
    """A mesh's corners as flat float arrays in the map frame, and its triangles, without zero-area ones; with
    `coloured`, also its corners' texture positions (rows running down the image, as glTF's) and each triangle's
    material slot."""
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
    triangles = np.empty(len(mesh.loop_triangles) * 3, dtype=np.int64)
    mesh.loop_triangles.foreach_get('loops', triangles)
    triangles = triangles.reshape(-1, 3)
    slot = np.empty(len(mesh.loop_triangles), dtype=np.int32)
    mesh.loop_triangles.foreach_get('material_index', slot)
    a, b, c = (position[triangles[:, k]] for k in range(3))
    area = np.linalg.norm(np.cross(b - a, c - a), axis=1) > 1e-10
    triangles, slot = triangles[area], slot[area]
    if not coloured:
        return position, normal.reshape(-1, 3), None, triangles
    colour = np.empty(n * 4, dtype=np.float32)
    mesh.color_attributes['Color'].data.foreach_get('color', colour)
    uv = np.zeros((n, 2), dtype=np.float32)
    if mesh.uv_layers:
        flat = np.empty(n * 2, dtype=np.float32)
        mesh.uv_layers[0].data.foreach_get('uv', flat)
        uv = flat.reshape(-1, 2)
        uv[:, 1] = 1.0 - uv[:, 1]
    return position, normal.reshape(-1, 3), colour.reshape(-1, 4), triangles, uv, slot


def convert(job):
    """Convert one job. The model's origin moves to the centre of its footprint, 1 cm above its lowest point, so its
    lowest point lies below its origin and it streams with the tile it stands in. The result reports where the new
    origin is in the source frame."""
    objects = import_source(job['source'])
    hulls = [o for o in objects if o.name.startswith('UCX_')]
    visible = [o for o in objects if not o.name.startswith('UCX_')]
    if job.get('collision_source'):
        hulls += import_source(job['collision_source'], reset=False)
    if job.get('turn'):
        turn = Matrix(job['turn']).to_4x4()
        for o in visible + hulls:
            o.matrix_world = turn @ o.matrix_world
    if not visible:
        raise RuntimeError(f"{job['source']}: no visible mesh")
    full = join(visible, 'full')
    if job.get('meet'):
        print('MEET', job['output'], *meet(full, np.array(job['meet'], float)), flush=True)
    if job.get('ground_owned'):
        ground_owned(full, set(job['ground_owned']))
    if job.get('keep'):
        keep(full, job['keep'])
        if not full.data.polygons:
            return None
    drop(full, job)
    textures = paint(full, job)
    position, normal, colour, triangles, uv, slot = arrays(full, True)
    # Each corner's texture position over its slot's tile.
    names = [m.name if m else '' for m in full.data.materials] or ['']
    tile = np.array([rule.get('tile', 1.0) for rule in slot_rules(job, names)], dtype=np.float32)
    corner_slot = np.zeros(len(uv), dtype=np.int64)
    corner_slot[triangles.ravel()] = np.repeat(slot, 3)
    uv = uv / tile[corner_slot][:, None]
    used = np.unique(slot)
    materials = None
    if any(textures[k] for k in used):
        # A textured surface: one material per texture its slots draw (or none), each named after its first slot,
        # times the corner colour, which keeps each slot's own colour; slots drawing the same texture share one
        # material, so the prop is drawn in as few parts as it has textures.
        first = {}
        for k in used:
            first.setdefault(textures[k], k)
        kinds = list(first)
        materials = [{'name': names[first[t]], 'colour': [1.0, 1.0, 1.0], 'texture': t, 'two_sided': False}
                     for t in kinds]
        of_slot = np.array([kinds.index(textures[k]) for k in used])
        colour[:, 3] = 1.0
        parts = [('full', SURFACE, position, normal, colour, triangles, uv, of_slot[np.searchsorted(used, slot)])]
    else:
        parts = [('full', {'vertex_paint': PAINT}, position, normal, colour, triangles)]
    if hulls and job.get('collision', True):
        collision = join(hulls, 'collision')
        parts.append(('collision', None, *arrays(collision, False)))
    if len(parts[0][5]) == 0:
        raise RuntimeError(f"{job['source']}: no triangles with area")
    position = parts[0][2][np.unique(parts[0][5])]
    low, high = position.min(axis=0), position.max(axis=0)
    origin = np.array([(low[0] + high[0]) / 2, (low[1] + high[1]) / 2, low[2] + 0.01])
    parts = [(n, e, p - origin, *rest) for n, e, p, *rest in parts]
    glb(parts, job['output'], materials)
    return {'output': job['output'], 'triangles': int(len(parts[0][5])), 'collision': len(parts) == 2,
            'origin': origin.tolist(), 'size': float(max(high - low)),
            'textures': sorted({m['texture'] for m in materials or [] if m['texture']})}


def main():
    jobs = json.load(open(sys.argv[sys.argv.index('--') + 1]))
    for job in jobs:
        try:
            result = convert(job)
            if result is None:
                print('EMPTY', json.dumps({'output': job['output']}), flush=True)
            else:
                print('CONVERTED', json.dumps(result), flush=True)
        except Exception as error:  # report every failure, then keep converting the others
            print('FAILED', json.dumps({'output': job['output'], 'error': str(error)}), flush=True)


main()
