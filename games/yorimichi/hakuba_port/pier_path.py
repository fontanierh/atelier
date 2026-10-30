"""Blender script: the walking surface of Sunset Pier's path in from the coast, for Hakuba's `skatepark` region.

Run as `blender -b --factory-startup --threads 3 -P pier_path.py -- BUILD` with Yorimichi's build folder, after
`world.skatepark.assembled`. The path (`SM_SkatePath`) runs over the ground from the coast road down to the deck, so
the world's ground owns its walking surface: the faces of its concrete slot facing up (`walking`), which the
`skatepark` adapter leaves out of the path's props (`Model.ground_owned`). This writes them, in map metres, to the
region's `path-source.json`, as `layout.rs` reads them: three surfaces, each drawing the pier's concrete map (`uv` as
glTF reads it), tinted as Yorimichi's material draws a face, twice its linear vertex colour, the paving, its dark edge
bands and the joints every 3 m, each triangle in the surface of its corners' mean colour. The path's skirts, edge faces
and railings stay props. First the path's vertices at the coast road's edge meet it (`seam.py`), as `convert.py` moves
the props' own, so the walking surface and its props still share every vertex.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seam import edge, meet  # noqa: E402

HERE = Path(__file__).resolve().parent
PARK = HERE.parents[0] / 'world' / 'regions' / 'skatepark' / 'park.json'
OUT = HERE.parents[1] / 'hakuba' / 'assets' / 'world' / 'src' / 'regions' / 'skatepark' / 'path-source.json'
SOURCE = 'atomic_regions/skatepark/assets/SM_SkatePath.fbx'
# The walking surface: the concrete slot's faces whose normal rises at least this steeply.
SLOT, UP = 'Pier_concrete', 0.5


def walking(normal_z, slot):
    """Whether a face is the path's walking surface, as `convert.py`'s `ground_owned` decides it."""
    return slot == SLOT and normal_z > UP


def linear(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def kind(mean):
    """Which of the path's three colours a triangle's mean vertex colour is: the dark edge band is bluish, the joint a
    dark warm grey, the paving the light one."""
    if mean[2] > mean[0]:
        return 'path-edge'
    return 'path-joint' if mean.sum() < JOINT_BELOW else 'path'


def main():
    global JOINT_BELOW
    build = Path(sys.argv[sys.argv.index('--') + 1])
    origin = np.array(json.loads(PARK.read_text())['origin'], float)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(build / SOURCE))
    (obj,) = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.name.startswith('UCX_')]
    # In the source frame, as `convert.py` joins it.
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    points = np.array([v.co[:] for v in obj.data.vertices]) + origin
    (x0, y0), (x1, y1) = points[:, :2].min(0), points[:, :2].max(0)
    moved, added = meet(obj, edge([x0, y0, x1, y1]) - origin)
    print(f'SUNSET PIER PATH meets the road: {moved} vertices moved, {added} added', flush=True)
    mesh, world = obj.data, obj.matrix_world
    turn = world.to_3x3().inverted().transposed()
    mesh.calc_loop_triangles()
    # The source's vertex colour as `convert.py` reads it, by corner.
    attribute = mesh.color_attributes['Color']
    colours = np.array([tuple(c.color) for c in attribute.data])[:, :3]
    if attribute.domain == 'POINT':
        colours = colours[[loop.vertex_index for loop in mesh.loops]]
    uvs = mesh.uv_layers.active.data
    slots = [s.material.name.split('.')[0] if s.material else '' for s in obj.material_slots]
    rows = []
    for tri in mesh.loop_triangles:
        poly = mesh.polygons[tri.polygon_index]
        normal = (turn @ poly.normal).normalized()
        if not walking(normal.z, slots[poly.material_index]):
            continue
        loops = list(tri.loops)
        xyz = [list(np.array(world @ mesh.vertices[mesh.loops[k].vertex_index].co) + origin) for k in loops]
        rows.append({'xyz': xyz, 'uv': [[uvs[k].uv[0], 1.0 - uvs[k].uv[1]] for k in loops],
                     'normal': [list((turn @ mesh.corner_normals[k].vector).normalized()) for k in loops],
                     'colour': colours[loops]})
    if not rows:
        raise SystemExit('Sunset Pier path: no walking surface')
    sums = np.array([r['colour'].mean(0).sum() for r in rows])
    # The paving's colour sums about twice the joints'; between them lies the cut.
    JOINT_BELOW = 0.75 * np.median(sums)
    surfaces = {}
    for row in rows:
        surfaces.setdefault(kind(row['colour'].mean(0)), []).append(row)
    out = {'surfaces': []}
    for name in ('path', 'path-edge', 'path-joint'):
        group = surfaces.get(name, [])
        if not group:
            continue
        tint = 2.0 * linear(np.concatenate([r['colour'] for r in group])).mean(0)
        out['surfaces'].append({'name': name, 'tint': [round(float(v), 4) for v in tint], 'triangles': [
            {key: [[round(float(v), 4) for v in corner] for corner in r[key]] for key in ('xyz', 'uv', 'normal')}
            for r in group]})
        print(f'SUNSET PIER PATH {name}: {len(group)} triangles, tint {out["surfaces"][-1]["tint"]}', flush=True)
    OUT.write_text(json.dumps(out, separators=(',', ':')) + '\n')
    print('SUNSET PIER PATH COMPLETE', OUT, flush=True)


main()
