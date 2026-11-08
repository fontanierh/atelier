#!/usr/bin/env python3
"""Clean, orient and scale the Tripo galleon hull into the proposal's ship frame.

    blender -b --factory-startup --threads 3 --python games/yorimichi/world/regions/brinecove/galleon_hull.py

Input: the retained Tripo P2 FBX (build/yorimichi/brinecove-review/tripo/galleon/model-r2). Output:
assets/brinecove/models/galleon-hull.glb plus provenance. The frame matches modules.ship: +Y is the bow, the stern is at
y = -32 and the stem at y = 29, x = 0 is the centreline and the keel sits at z = 0; the provenance records the waist
deck height and mast stations that modules.ship rigs onto. The front reference view showed
the stern castle's towers beside the bow, and Tripo reconstructed them as flat window wings outboard of the bow;
every vertex in the forward half outside the midship beam is removed. Masts, yards, sails and rigging stay
procedural.
"""
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
import bmesh
from mathutils import Matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from brinecove.paths import MODELS, REPO, REVIEW  # noqa: E402

JOB = REVIEW / 'tripo/galleon/model-r2'
SOURCE = JOB / 'raw/output_model_url.fbx'
TARGET = MODELS / 'galleon-hull.glb'
STERN, STEM = -32.0, 29.0
# Tripo keeps the toy-like proportions of the reference views: scaled to length the hull is 34 m wide with its waist
# deck 19 m above the keel. Narrow and lower it towards a galleon's 3:1 length to beam; side-on, where the gunports
# and galleries are read, only the height factor applies.
BEAM_K, HEIGHT_K = 0.55, 0.78
# Mast stumps on the processed hull, measured along the centreline; the procedural masts stand on them.
MASTS = (-14.5, -2.0, 11.5)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(SOURCE))
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    for o in bpy.data.objects:
        o.select_set(o in meshes)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.object
    obj.parent = None
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    mesh = obj.data
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    # Length runs along the longer horizontal axis; rotate it onto Y.
    if max(xs) - min(xs) > max(ys) - min(ys):
        mesh.transform(Matrix.Rotation(math.radians(90), 4, 'Z'))
    ys = [v.co.y for v in mesh.vertices]
    y0, y1 = min(ys), max(ys)
    length = y1 - y0

    def top(lo, hi):
        return max((v.co.z for v in mesh.vertices if lo <= v.co.y <= hi), default=-1e9)

    # The stern castle is the tall end; turn it to -Y.
    if top(y1 - 0.2 * length, y1) > top(y0, y0 + 0.2 * length):
        mesh.transform(Matrix.Rotation(math.radians(180), 4, 'Z'))
    xs = [v.co.x for v in mesh.vertices]
    ys = [v.co.y for v in mesh.vertices]
    zs = [v.co.z for v in mesh.vertices]
    cx = (min(xs) + max(xs)) / 2
    y0, y1 = min(ys), max(ys)
    mid = (y0 + y1) / 2
    length = y1 - y0
    beam = max(abs(v.co.x - cx) for v in mesh.vertices if abs(v.co.y - mid) < 0.08 * length)
    # Remove the reconstructed bow wings.
    bm = bmesh.new()
    bm.from_mesh(mesh)
    wings = [v for v in bm.verts if v.co.y > mid - 0.05 * length and abs(v.co.x - cx) > beam * 1.04]
    removed = len(wings)
    bmesh.ops.delete(bm, geom=wings, context='VERTS')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(mesh)
    bm.free()
    # Scale to the ship frame: stern at -32, the bow end at the stem, keel on z = 0.
    k = (STEM - STERN) / length
    zs = [v.co.z for v in mesh.vertices]
    mesh.transform(Matrix.Translation((-cx, -y0, -min(zs))))
    mesh.transform(Matrix.Scale(k, 4))
    mesh.transform(Matrix.Translation((0.0, STERN, 0.0)))
    mesh.transform(Matrix.Diagonal((BEAM_K, 1.0, HEIGHT_K, 1.0)))
    mesh.update()
    if mesh.has_custom_normals:
        bpy.ops.mesh.customdata_custom_splitnormals_clear()  # stale after the non-uniform scale
    for poly in mesh.polygons:
        poly.use_smooth = True
    co = [v.co for v in mesh.vertices]
    dims = [round(max(c[i] for c in co) - min(c[i] for c in co), 2) for i in range(3)]
    top_z = max(c.z for c in co)
    # Waist deck: the area-weighted median height of upward faces near the centreline amidships.
    deck = sorted((p.center.z, p.area) for p in mesh.polygons
                  if p.normal.z > 0.95 and abs(p.center.x) < 3.0 and abs(p.center.y + 1.5) < 10.0)
    half, acc = sum(a for _, a in deck) / 2, 0.0
    for deck_z, a in deck:
        acc += a
        if acc >= half:
            break
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(TARGET), export_format='GLB', use_selection=False, export_apply=True,
                              export_yup=True, export_animations=False, export_lights=False, export_cameras=False,
                              export_image_format='JPEG', export_image_quality=86)
    job = json.loads((JOB / 'job.json').read_text())
    record = dict(
        slug='galleon-hull', stage='brinecove-tripo-processed', generated=datetime.now(timezone.utc).isoformat(),
        source=str(SOURCE.relative_to(REPO)), source_sha256=sha(SOURCE),
        references='build/yorimichi/brinecove-review/tripo/galleon/views-r1 (front, left, back, right; approval.json)',
        generation=dict(provider='Tripo', endpoint=job.get('endpoint'), settings=job.get('settings'),
                        task_id=job.get('task_id'), credits_consumed=job.get('credits_consumed')),
        processing=dict(script='games/yorimichi/world/regions/brinecove/galleon_hull.py',
                        removed_bow_wing_vertices=removed, midship_half_beam_source_units=round(beam, 4),
                        scale=round(k, 6), beam_factor=BEAM_K, height_factor=HEIGHT_K,
                        frame='+Y bow, stern y=-32, stem y=29, keel z=0', dimensions_m=dims,
                        deck_z=round(deck_z, 2), top_z=round(top_z, 2), masts=list(MASTS),
                        vertices=len(mesh.vertices), triangles=sum(len(p.vertices) - 2 for p in mesh.polygons)),
        output_sha256=sha(TARGET))
    TARGET.with_suffix('.provenance.json').write_text(json.dumps(record, indent=2) + '\n')
    print('GALLEON HULL', json.dumps(record['processing']), flush=True)


if __name__ == '__main__':
    main()
    sys.exit(0)
