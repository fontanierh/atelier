"""Step 1 of the body swap: import the Tripo full-body model, align it to the r07 base body, measure the
proportions against the skeleton and render overlays for review.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_body_swap_fit.py

Alignment: uniform scale and translation only (floor to floor, head top to head top, centred), so the
proportion comparison is honest. Writes body-swap-r01/fit/ with align.json, overlay renders and an aligned blend.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import json, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).parent))
from atelier.blender import renderdev
# ROOT (the archive) comes from _archive
BASE = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
import os
SWAP_DIR = os.environ.get('BODY_SWAP_DIR', 'body-swap-r01')
SWAP_STEM = os.environ.get('BODY_SWAP_STEM', 'WarmOriginal-BodySwap-r01')
HEADLESS = bool(os.environ.get('BODY_SWAP_HEADLESS'))
SWAP = BASE / SWAP_DIR
OUT = SWAP / 'fit'; OUT.mkdir(exist_ok=True)
RAW = next(p for p in (SWAP / 'raw/output_model_url.glb', SWAP / 'raw/output_model_url.fbx') if p.exists())
bpy.ops.wm.open_mainfile(filepath=str(BASE / os.environ.get('BODY_SWAP_SOURCE', 'outfit-r07/WarmOriginal-Outfit-r07.blend')))   # the base character: r07 for the outfit work, game-r10 for the game build
s = bpy.context.scene
arm = next(o for o in s.objects if o.type == 'ARMATURE')
arm.animation_data.action = None; arm.data.pose_position = 'REST'
for o in s.objects:
    if o.type == 'MESH' and o.data.shape_keys:
        o.data.shape_keys.animation_data_clear()
        for k in o.data.shape_keys.key_blocks:
            k.value = 0
bpy.context.view_layer.update()
body = next(o for o in s.objects if o.get('base_body'))
old = set(bpy.data.objects)
if RAW.suffix == '.glb':
    bpy.ops.import_scene.gltf(filepath=str(RAW))
else:
    bpy.ops.import_scene.fbx(filepath=str(RAW))
new_objs = [o for o in bpy.data.objects if o not in old and o.type == 'MESH']
for o in new_objs:
    bpy.ops.object.select_all(action='DESELECT'); o.select_set(True); bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bpy.ops.object.select_all(action='DESELECT')
for o in new_objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = new_objs[0]
if len(new_objs) > 1:
    bpy.ops.object.join()
gen = bpy.context.object; gen.name = 'Tripo clothed body (raw, aligned)'
for o in list(bpy.data.objects):
    if o not in old and o is not gen:
        bpy.data.objects.remove(o, do_unlink=True)
# Tripo/glTF import: Y up converted by the importer; the character should face +X like the base body. Check the
# facing by comparing the extent along X vs Y of the arm span (T-pose arms lie along Y for our character).
P = np.array([v.co[:] for v in gen.data.vertices])
ext = P.max(0) - P.min(0)
facing_note = 'arms along Y (faces +X or -X)' if ext[1] > ext[0] else 'arms along X: rotated 90 deg about Z'
if ext[0] > ext[1]:
    P = P @ np.array([[0, 1, 0], [-1, 0, 0], [0, 0, 1]]).T
# front/back: the face (eyes) is on +X for the base body; use the nose/face protrusion: the head slice's X extent
B = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
def head_dir(pts):
    if HEADLESS:   # no head: the toes point forward, so use the feet slice
        lo = pts[:, 2].min(); sl = pts[pts[:, 2] < lo + .05]
    else:
        top = pts[:, 2].max(); sl = pts[(pts[:, 2] > top - .16) & (pts[:, 2] < top - .06)]
    return float(np.sign((sl[:, 0].max() - sl[:, 0].mean()) - (sl[:, 0].mean() - sl[:, 0].min())))
if head_dir(P) != head_dir(B):
    P[:, 0] *= -1; P[:, 1] *= -1
    facing_note += ' + turned 180'
if HEADLESS:
    # no head to measure: scale by the arm span (the sleeves end at the mannequin's wrist stumps, |y| .34), floor to
    # floor, and centre on the legs (z below -.2), which the trousers wrap symmetrically
    mann = B[(B[:, 2] < .175) & (np.abs(B[:, 1]) < .345)]
    scale = (mann[:, 1].max() - mann[:, 1].min()) / (P[:, 1].max() - P[:, 1].min())
    P = P * scale
    P[:, 2] += B[:, 2].min() - P[:, 2].min()
    _lb = B[B[:, 2] < -.2]; _lp = P[P[:, 2] < -.2]
    P[:, 0] += _lb[:, 0].mean() - _lp[:, 0].mean(); P[:, 1] += _lb[:, 1].mean() - _lp[:, 1].mean()
    # front/back: centre the tee on the chest depth (the collar must sit around the neck, not behind it): compare
    # the outfit's front and back extents with the base chest at z .04-.12, |y| < .06
    _cb = B[(B[:, 2] > .04) & (B[:, 2] < .12) & (np.abs(B[:, 1]) < .06)]
    _cp = P[(P[:, 2] > .04) & (P[:, 2] < .12) & (np.abs(P[:, 1]) < .06)]
    _front = _cp[:, 0].max() - _cb[:, 0].max(); _back = _cb[:, 0].min() - _cp[:, 0].min()
    P[:, 0] += (_back - _front) / 2
    measures_extra = {'chest_recentre_x_mm': round(1000 * float((_back - _front) / 2), 1), 'chest_front_clearance_mm': round(1000 * float((_front + _back) / 2), 1)}
    # the generated arms sit a few cm forward and below the base arms while the torso matches, so each sleeve is
    # slid locally onto its forearm axis (measured over |y| .25-.33), blended in from the shoulder
    for sign, side in ((1, 'Left'), (-1, 'Right')):
        selb = (np.sign(B[:, 1]) == sign) & (np.abs(B[:, 1]) > .25) & (np.abs(B[:, 1]) < .33) & (B[:, 2] > .05)
        selp = (np.sign(P[:, 1]) == sign) & (np.abs(P[:, 1]) > .25) & (np.abs(P[:, 1]) < .33) & (P[:, 2] > .05)
        dx = float(B[selb][:, 0].mean() - P[selp][:, 0].mean()); dz = float(B[selb][:, 2].mean() - P[selp][:, 2].mean())
        w = np.clip((np.abs(P[:, 1]) - .10) / .10, 0, 1); w = w * w * (3 - 2 * w) * (np.sign(P[:, 1]) == sign)
        P[:, 0] += w * dx; P[:, 2] += w * dz
        measures_extra[f'{side}_sleeve_slide_mm'] = [round(1000 * dx, 1), round(1000 * dz, 1)]
else:
    # uniform scale floor-to-head-top, then centre in X/Y on the base body
    scale = (B[:, 2].max() - B[:, 2].min()) / (P[:, 2].max() - P[:, 2].min())
    P = P * scale
    P[:, 2] += B[:, 2].min() - P[:, 2].min()
    # centre on the head (identical in both meshes; a whole-body mean is biased forward by the baggy trousers)
    _hb = B[B[:, 2] > B[:, 2].max() - .22]; _hp = P[P[:, 2] > P[:, 2].max() - .22]
    P[:, 0] += _hb[:, 0].mean() - _hp[:, 0].mean(); P[:, 1] += _hb[:, 1].mean() - _hp[:, 1].mean()
gen.data.vertices.foreach_set('co', P.astype(np.float32).ravel()); gen.data.update()
gen.matrix_world.identity()
# proportion landmarks: compare skeleton joints to the generated silhouette
def bone(n):
    b = arm.data.bones['mixamorig:' + n]; return arm.matrix_world @ b.head_local
def span_at(pts, z, band=.01):
    sl = pts[np.abs(pts[:, 2] - z) < band]
    return (float(sl[:, 1].min()), float(sl[:, 1].max())) if len(sl) else (None, None)
lm = {}
for name in ('Hips', 'Spine2', 'Neck', 'Head', 'LeftArm', 'LeftForeArm', 'LeftHand', 'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase'):
    lm[name] = list(bone(name))
z_arm = lm['LeftArm'][2]
measures = {
    **(measures_extra if HEADLESS else {}),
    'base_arm_span_y': span_at(B, z_arm, .015), 'gen_arm_span_y': span_at(P, z_arm, .015),
    'base_hip_width_y': span_at(B, lm['Hips'][2]), 'gen_hip_width_y': span_at(P, lm['Hips'][2]),
    'base_height': float(B[:, 2].max() - B[:, 2].min()), 'gen_height_after_scale': float(P[:, 2].max() - P[:, 2].min()), 'headless': HEADLESS,
    'scale_applied': float(scale), 'facing': facing_note,
    'gen_vertices': len(P), 'gen_faces': len(gen.data.polygons), 'materials': [m.name for m in gen.data.materials],
}
# where does the generated mesh end in the arm direction (wrist / fingertip) vs the skeleton hand
for side, sign in (('Left', 1), ('Right', -1)):
    arm_pts = P[(np.abs(P[:, 2] - z_arm) < .03)]
    tip = float(sign * (arm_pts[:, 1] * sign).max()) if len(arm_pts) else None
    base_pts = B[(np.abs(B[:, 2] - z_arm) < .03)]
    btip = float(sign * (base_pts[:, 1] * sign).max()) if len(base_pts) else None
    measures[f'{side}_fingertip_y'] = {'base': btip, 'gen': tip, 'hand_bone_y': lm['LeftHand'][1] * sign}
# clearance of the generated shell over the base body (signed along the base normal): negative means the base
# body pokes out of the outfit there
from mathutils.bvhtree import BVHTree
gen.data.calc_loop_triangles()
gbvh = BVHTree.FromPolygons([Vector(q) for q in P], [tuple(t.vertices) for t in gen.data.loop_triangles], all_triangles=True)
body_nrm = np.array([(body.matrix_world.to_3x3() @ v.normal)[:] for v in body.data.vertices])
clear = []
for q, nrm in zip(B, body_nrm):
    if q[2] > .14 or abs(q[1]) > .33:      # head and hands are replaced by the originals
        continue
    hit = gbvh.ray_cast(Vector(q), Vector(nrm), .08)
    clear.append(hit[3] if hit[0] is not None else None)
hits = [c for c in clear if c is not None]
measures['torso_clearance_mm'] = {'covered': len(hits), 'uncovered': len(clear) - len(hits), 'min': round(1000 * min(hits), 1), 'p05': round(1000 * float(np.percentile(hits, 5)), 1), 'median': round(1000 * float(np.median(hits)), 1)}
json.dump({'raw': str(RAW.relative_to(ROOT)), 'landmarks_world': lm, 'measures': measures}, open(OUT / 'align.json', 'w'), indent=2)
print('ALIGN', json.dumps(measures))
# overlay renders: generated body alone, base body alone, both (base in wireframe-ish via transparency)
s.render.engine = 'CYCLES'; renderdev.enable_metal(); s.cycles.samples = 24; s.render.resolution_x = s.render.resolution_y = 1024
c = s.camera; c.data.type = 'ORTHO'
lo, hi = B.min(0), B.max(0); center = Vector(((lo + hi) / 2).tolist()); scale_v = float(max(hi - lo) * 1.15)
def shoot(name, direction, show):
    for o in s.objects:
        if o.type == 'MESH':
            o.hide_render = o not in show
    c.data.ortho_scale = scale_v; c.location = center + Vector(direction) * 4
    c.rotation_euler = (center - c.location).to_track_quat('-Z', 'Y').to_euler()
    s.render.filepath = str(OUT / name); bpy.ops.render.render(write_still=True)
views = {'front': (1, 0, 0), 'back': (-1, 0, 0), 'left': (0, 1, 0), 'right': (0, -1, 0), 'three-quarter': (1, -.7, .3)}
for v, d in views.items():
    shoot(f'gen-{v}.png', d, {gen})
    shoot(f'both-{v}.png', d, {gen, body})
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'WarmOriginal-BodySwap-aligned.blend'))
print('FIT_DONE')
