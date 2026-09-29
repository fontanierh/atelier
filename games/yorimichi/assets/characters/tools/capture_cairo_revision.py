"""Render consistent front/rear/profile captures of a native game revision."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
# ROOT (the archive) comes from _archive
sys.path[:0] = [str(TOOLS)]
from cairo_outfit_correctives import set_clip
from atelier.blender import renderdev

parser = argparse.ArgumentParser()
parser.add_argument('--revision', required=True)
parser.add_argument('--clip', default='Idle · library')
parser.add_argument('--frames', default='1')
parser.add_argument('--views', default='front,rear,rear-quarter,side')
args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
out = ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12'/args.revision
record = json.loads((out/'source-manifest.json').read_text())
bpy.ops.wm.open_mainfile(filepath=str(ROOT/record['native']))
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
scene.render.engine = 'CYCLES'; scene.cycles.samples = 16; renderdev.enable_metal()
scene.render.resolution_x = 720; scene.render.resolution_y = 800; scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
set_clip(arm, bpy.data.actions['Standing · outfit review']); scene.frame_set(1)
pts = []
for o in scene.objects:
    if o.type != 'MESH' or not (o.get('outfit_slot') or (o.get('body_region') and not o.get('hidden_by_slot'))): continue
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    pts.extend(ev.matrix_world@v.co for v in ev.data.vertices)
target = Vector((.02, 0, (max(p.z for p in pts)+min(p.z for p in pts))/2))
scene.camera.data.type = 'ORTHO'
scene.camera.data.ortho_scale = (max(p.z for p in pts)-min(p.z for p in pts))*1.15
directions = {'front': (1,0,.08), 'rear': (-1,0,.08), 'rear-quarter': (-1,-.55,.2), 'side': (0,-1,.1)}
set_clip(arm, bpy.data.actions[args.clip])
for frame in map(int, args.frames.split(',')):
    scene.frame_set(frame)
    for view in args.views.split(','):
        direction = Vector(directions[view]).normalized()
        scene.camera.location = target+direction*4
        scene.camera.rotation_euler = (target-scene.camera.location).to_track_quat('-Z','Y').to_euler()
        scene.render.filepath = str(out/'diagnostics'/f'{args.clip.split(" · ")[0].lower()}-{view}-{frame:03}.png')
        bpy.ops.render.render(write_still=True)
        print('CAPTURE', args.clip, view, frame, flush=True)
