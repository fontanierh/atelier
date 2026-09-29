"""Captures of the assembled body swap: rest pose, several library clips, and neck/wrist seam close-ups.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/cairo_body_swap_capture.py
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import json, sys
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).parent))
from atelier.blender import renderdev
from cairo_outfit_correctives import set_clip
# ROOT (the archive) comes from _archive
import os
SWAP_DIR = os.environ.get('BODY_SWAP_DIR', 'body-swap-r01')
SWAP_STEM = os.environ.get('BODY_SWAP_STEM', 'WarmOriginal-BodySwap-r01')
HEADLESS = bool(os.environ.get('BODY_SWAP_HEADLESS'))
SWAP = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12' / SWAP_DIR
OUT = SWAP / 'captures'; OUT.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(SWAP / f'assembled/{SWAP_STEM}.blend'))
s = bpy.context.scene; arm = next(o for o in s.objects if o.type == 'ARMATURE')
s.render.engine = 'CYCLES'; renderdev.enable_metal(); s.cycles.samples = 24
s.render.resolution_x = 900; s.render.resolution_y = 1000
for o in s.objects:
    if o.name.startswith('Review floor'):
        o.hide_render = True
cam = s.camera; cam.data.type = 'ORTHO'
def bone(n):
    return arm.matrix_world @ arm.pose.bones['mixamorig:' + n].head
records = []
def shot(name, direction, target, scale):
    d = Vector(direction).normalized(); t = Vector(target)
    cam.location = t + d * 3; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler(); cam.data.ortho_scale = scale
    s.render.filepath = str(OUT / f'{name}.png'); bpy.ops.render.render(write_still=True); records.append(name)
POSES = [('standing', 'Standing · outfit review', 1), ('idle', 'Idle · library', 120), ('sprint17', 'Sprint · dressed', 17),
         ('sprint27', 'Sprint · dressed', 27), ('crouch', 'CrouchIdle · library', 46), ('sit', 'SitIdle · library', 90),
         ('wave', 'Wave · library', 80), ('doublejump', 'DoubleJump · library', 14), ('dash', 'DashGround · library', 20)]
for tag, clip, frame in POSES:
    set_clip(arm, bpy.data.actions[clip]); s.frame_set(frame); bpy.context.view_layer.update()
    hips = bone('Hips')
    for vn, d in (('front-left', (1, .7, .15)), ('back-right', (-1, -.7, .15)), ('front', (1, 0, .05)), ('back', (-1, 0, .05))):
        shot(f'{tag}--{vn}', d, (hips.x, hips.y, hips.z + .02), 1.2)
    if tag in ('standing', 'sprint17', 'crouch', 'wave'):
        shot(f'{tag}--neck', (1, -.6, .4), bone('Neck') + Vector((0, 0, .02)), .3)
        shot(f'{tag}--neck-back', (-1, .6, .4), bone('Neck') + Vector((0, 0, .02)), .3)
        for side, sg in (('left', 1), ('right', -1)):
            shot(f'{tag}--wrist-{side}', (1, sg * .5, .5), bone(f'{side.capitalize()}Hand'), .22)
(OUT / 'index.json').write_text(json.dumps(records, indent=1) + '\n')
print('CAPTURES', len(records))
