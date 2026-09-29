"""Render review captures of every authored fox-hunter clip: 12 frames from three-quarter, side and front cameras.

blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/fox_hunter_captures.py -- --rev animation-r01
Then tile with:  python games/yorimichi/assets/characters/tools/fox_hunter_captures.py tile --rev animation-r01   (Pillow, system python)
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import json, sys
from pathlib import Path

# ROOT (the archive) comes from _archive
ASSET = ROOT / 'output/imagegen/yorimichi-fox-hunter-2026-09-13'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
rev = argv[argv.index('--rev') + 1] if '--rev' in argv else 'animation-r01'
only = argv[argv.index('--only') + 1].split(',') if '--only' in argv else []
OUT = ASSET / rev / 'captures'
N = 12

if argv and argv[0] == 'tile':
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 15)
    m = json.loads((ASSET / rev / 'manifest.json').read_text())
    for name in m['clips']:
        for cam in ('threeq', 'side', 'front'):
            files = sorted((OUT / 'frames').glob(f'{name}-{cam}-*.png'))
            if not files: continue
            ims = [Image.open(f).convert('RGB') for f in files]
            w, h = ims[0].size; cols = 6; rows = (len(ims) + cols - 1) // cols
            sheet = Image.new('RGB', (w * cols, (h + 22) * rows), (238, 234, 226)); d = ImageDraw.Draw(sheet)
            fps = m['fps']; n = m['clips'][name]['frames']
            for i, im in enumerate(ims):
                x, y = (i % cols) * w, (i // cols) * (h + 22); sheet.paste(im, (x, y))
                f = int(round(n * i / (N - 1)))
                d.text((x + 6, y + h + 3), f'{name} · {cam} · frame {f} · {f / fps:.2f}s', fill=(40, 40, 48), font=font)
            sheet.save(OUT / f'{name}-{cam}.jpg', quality=90)
    print('tiled')
    sys.exit(0)

import bpy
from mathutils import Vector
bpy.ops.wm.open_mainfile(filepath=str(ASSET / rev / f'FoxHunter-Anim-{rev.split("-")[-1]}.blend'))
sc = bpy.context.scene
arm = next(o for o in sc.objects if o.type == 'ARMATURE')
body = next(o for o in sc.objects if o.type == 'MESH' and o.vertex_groups)
m = json.loads((ASSET / rev / 'manifest.json').read_text())
H = m['model_height_units']
cam = sc.camera; cam.data.type = 'PERSP'; cam.data.lens = 45
sc.render.resolution_x = sc.render.resolution_y = 640
sc.render.engine = 'BLENDER_EEVEE'; sc.render.image_settings.file_format = 'PNG'
# a floor and a forward marker so direction is unambiguous in every capture
FLOOR = m.get('floor_z', 0.0)  # the rest soles sit here; r01 captures had the plane 0.03 above them
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, FLOOR)); floor = bpy.context.active_object
fm = bpy.data.materials.new('Floor'); fm.use_nodes = True; fm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.52, 0.53, 0.56, 1); floor.data.materials.append(fm)
bpy.ops.mesh.primitive_cone_add(radius1=0.06, depth=0.18, location=(H * 0.9, 0, FLOOR + 0.09), rotation=(0, 1.5708, 0)); marker = bpy.context.active_object
mm = bpy.data.materials.new('Marker'); mm.use_nodes = True; mm.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.85, 0.35, 0.2, 1); marker.data.materials.append(mm)
(OUT / 'frames').mkdir(parents=True, exist_ok=True)
for tr in arm.animation_data.nla_tracks: tr.mute = True
for name, info in m['clips'].items():
    if only and name not in only: continue
    for tr in arm.animation_data.nla_tracks: tr.mute = (tr.name != name)
    n = info['frames']
    for i in range(N):
        f = int(round(n * i / (N - 1))); sc.frame_set(f)
        rp = arm.matrix_world @ arm.pose.bones['Root'].head
        for camname, off in (('threeq', Vector((H * 2.3, -H * 2.0, H * 1.0))), ('side', Vector((0.0, -H * 3.2, H * 0.55))), ('front', Vector((H * 3.2, 0.0, H * 0.55)))):
            target = Vector((rp.x, rp.y, H * 0.48)); cam.location = target + off
            cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
            sc.render.filepath = str(OUT / 'frames' / f'{name}-{camname}-{i:02d}.png'); bpy.ops.render.render(write_still=True)
print('CAPTURES OK', len(m['clips']))
