"""Render clip frames from a library .blend for visual inspection.

blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/capture_warm_clip.py -- \
    --blend animations-r01/WarmOriginal-Animations-r01.blend --clip "Walk · library" \
    --out animations-r01/diagnostics/walk --views side,three --step 3 [--cycles] [--sheet] [--size 640]
Camera directions follow the sprint review: side = -Y, three-quarter = (1,-.7,.08).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import argparse, json, subprocess, sys
import bpy
from mathutils import Vector
# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
sys.path.insert(0, str(Path(__file__).parent)); pass
from warm_outfit_correctives import set_clip
parser = argparse.ArgumentParser()
parser.add_argument('--blend', required=True)
parser.add_argument('--clip', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--views', default='side')
parser.add_argument('--step', type=int, default=2)
parser.add_argument('--frames', default='')
# Blender 5.2's Cycles startup parser treats --cycles as an ambiguous prefix
# of its own switches. Use --path-traced when invoking this through Blender.
parser.add_argument('--cycles', '--path-traced', dest='cycles', action='store_true')
parser.add_argument('--sheet', action='store_true')
parser.add_argument('--reel', action='store_true')
parser.add_argument('--size', type=int, default=560)
parser.add_argument('--samples', type=int, default=24)
parser.add_argument('--scale', type=float, default=1.35)
parser.add_argument('--target', default='0.03,0,-0.06')
parser.add_argument('--equip', default='all')
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
OUT = ASSET / args.out; OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ASSET / args.blend))
scene = bpy.context.scene; arm = next(o for o in scene.objects if o.type == 'ARMATURE')
action = bpy.data.actions[args.clip]
set_clip(arm, action)
for obj in scene.objects:
    if obj.type == 'MESH' and obj.get('outfit_slot') and args.equip != 'all':
        obj.hide_render = obj['outfit_slot'] not in args.equip.split(',')
    if obj.type == 'MESH' and obj.get('body_region') and args.equip != 'all':
        obj.hide_render = bool(obj['hidden_by_slot']) and obj['hidden_by_slot'] in args.equip.split(',')
if args.cycles:
    from atelier.blender import renderdev
    scene.render.engine = 'CYCLES'; scene.cycles.samples = args.samples; renderdev.enable_metal()
else:
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'; scene.display.shading.color_type = 'TEXTURE'
    scene.display.shading.show_shadows = True; scene.display.shading.show_cavity = False
    scene.display_settings.display_device = 'sRGB'; scene.view_settings.view_transform = 'Standard'
scene.render.resolution_x = scene.render.resolution_y = args.size; scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
camera = scene.camera; camera.data.type = 'ORTHO'; camera.data.ortho_scale = args.scale
target = Vector([float(v) for v in args.target.split(',')])
directions = {'side': (0, -1, .03), 'three': (1, -.7, .10), 'front': (1, 0, .05), 'back': (-1, .3, .08), 'other': (0, 1, .03), 'top': (.2, -.2, 1)}
start, end = int(action.frame_range[0]), int(action.frame_range[1])
frames = [int(f) for f in args.frames.split(',')] if args.frames else list(range(start, end + 1, args.step))
records = []
for view in args.views.split(','):
    camera.location = target + Vector(directions[view]).normalized() * 4
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    for index, frame in enumerate(frames):
        scene.frame_set(frame)
        path = OUT / f'{view}-{frame:04d}.png'
        scene.render.filepath = str(path); bpy.ops.render.render(write_still=True)
        records.append({'view': view, 'frame': frame, 'time': (frame - 1) / scene.render.fps, 'file': path.name})
(OUT / 'captures.json').write_text(json.dumps({'blend': args.blend, 'clip': args.clip, 'frames': records}, indent=2) + '\n')
if args.sheet:
    subprocess.run([sys.executable, str(Path(__file__).parent / 'contact_sheet.py'), str(OUT)], check=True)
if args.reel:
    for view in args.views.split(','):
        seq = OUT / f'{view}-reel'; seq.mkdir(exist_ok=True)
        for i, frame in enumerate(frames):
            (seq / f'{i:04d}.png').write_bytes((OUT / f'{view}-{frame:04d}.png').read_bytes())
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-framerate', str(60 / args.step), '-i', str(seq / '%04d.png'), '-c:v', 'libx264', '-crf', '20', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(OUT / f'{view}.mp4')], check=True)
print('CAPTURES_READY', OUT, len(records))
