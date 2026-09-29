"""Render the naked Cairo body (the Tripo base body under the outfit) in its bind pose as front/back/left/
right orthographic views, the inputs for the full-body outfit swap.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_body_swap_references.py [-- --mannequin DIR]

With --mannequin the head and the hands are left out (the body regions under the clothes, one flat grey material,
neck and wrist openings capped) and the renders go to DIR/references/naked-*.png: references for a generation that
must come back without head and hands, so nothing has to be cut afterwards.

Writes 1024x1024 Cycles renders of the base body alone (`naked-<view>.png`) and of the r07 dressed character for
context (`dressed-<view>.png`) plus envelope.json with the body bounds and camera. No generative step; the r07
source is opened read-only and not saved.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import os
import bpy, json, sys
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).parent))
from atelier.blender import renderdev
# ROOT (the archive) comes from _archive
BASE = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
import argparse
_ap = argparse.ArgumentParser(); _ap.add_argument('--mannequin', default='')
_args = _ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
MANNEQUIN = bool(_args.mannequin)
OUT = BASE / (_args.mannequin + '/references' if MANNEQUIN else 'body-swap-r01/references')
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(BASE / os.environ.get('BODY_SWAP_SOURCE', 'outfit-r07/WarmOriginal-Outfit-r07.blend')))   # the base character: r07 for the outfit work, game-r10 for the game build
s = bpy.context.scene
arm = next(o for o in s.objects if o.type == 'ARMATURE')
arm.animation_data.action = None
arm.data.pose_position = 'REST'
for o in s.objects:
    if o.type == 'MESH' and o.data.shape_keys:
        o.data.shape_keys.animation_data_clear()
        for k in o.data.shape_keys.key_blocks:
            k.value = 0
bpy.context.view_layer.update()
body = next(o for o in s.objects if o.get('base_body'))
if MANNEQUIN:
    import bmesh
    grey = bpy.data.materials.new('Mannequin grey'); grey.use_nodes = True
    grey.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.45, .44, .43, 1); grey.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value = .9
    from cairo_body_key import mannequin   # the same mannequin the body key's depth test rebuilds
    mann = bpy.data.objects.new('Mannequin (no head, no hands)', bpy.data.meshes.new('mannequin'))
    s.collection.objects.link(mann)
    bm = mannequin(list(s.objects))
    bm.to_mesh(mann.data); bm.free()
    mann.data.materials.append(grey)
    for pl in mann.data.polygons:
        pl.material_index = 0
    body = mann
pts = [body.matrix_world @ v.co for v in body.data.vertices]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
center = (lo + hi) / 2
s.render.engine = 'CYCLES'; renderdev.enable_metal(); s.cycles.samples = 32; s.render.resolution_x = s.render.resolution_y = 1024
s.render.film_transparent = False
world = s.world; world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg: bg.inputs[0].default_value = (.82, .82, .82, 1); bg.inputs[1].default_value = 1.0
c = s.camera; c.data.type = 'ORTHO'
scale = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z) * 1.15
views = {'front': (1, 0, 0), 'back': (-1, 0, 0), 'left': (0, 1, 0), 'right': (0, -1, 0)}
def shoot(name, direction):
    c.data.ortho_scale = scale
    c.location = center + Vector(direction) * 4
    c.rotation_euler = (center - c.location).to_track_quat('-Z', 'Y').to_euler()
    s.render.filepath = str(OUT / name); bpy.ops.render.render(write_still=True)
for o in s.objects:
    if o.type == 'MESH': o.hide_render = o is not body
body.hide_render = False
for view, d in views.items(): shoot(f'naked-{view}.png', d)
if MANNEQUIN:
    json.dump({'source': 'outfit-r07/WarmOriginal-Outfit-r07.blend', 'pose': 'bind (REST)', 'mannequin': True, 'center': list(center), 'ortho_scale': scale}, open(OUT / 'envelope.json', 'w'), indent=2)
    print('MANNEQUIN', len(body.data.vertices), list(lo), list(hi)); sys.exit(0)
for o in s.objects:
    if o.type == 'MESH': o.hide_render = o.name.startswith('Review floor') or bool(o.get('base_body'))
for view, d in views.items(): shoot(f'dressed-{view}.png', d)
json.dump({'source': 'outfit-r07/WarmOriginal-Outfit-r07.blend', 'pose': 'bind (REST), all morphs 0', 'body_object': body.name,
           'body_bounds': [list(lo), list(hi)], 'center': list(center), 'ortho_scale': scale,
           'views': {k: list(v) for k, v in views.items()},
           'note': 'character faces +X, left +Y, up +Z; camera directions are world axes; left/right are the character\'s own'},
          open(OUT / 'envelope.json', 'w'), indent=2)
print('BODY', body.name, list(lo), list(hi), scale, 'materials', [m.name for m in body.data.materials])
