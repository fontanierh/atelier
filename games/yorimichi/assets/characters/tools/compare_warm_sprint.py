"""Render eight actual Blender poses beside the same source-video timestamps.

Run with Python + Pillow; invokes Blender and ffmpeg. Does not save over the rig.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import json
import subprocess
from PIL import Image, ImageDraw, ImageFont

# ROOT (the archive) comes from _archive
ASSET=ROOT/'output/imagegen/yorimichi-yellow-boy-2026-09-12'
OUT=ASSET/'sprint-animation-r01'
work=OUT/'animation-frames'
code=f'''
import bpy
from mathutils import Vector
from pathlib import Path
out=Path({str(work)!r})
s=bpy.context.scene;c=s.camera
target=Vector((.13,0,-.044));c.location=target+Vector((0,-1,.015)).normalized()*4
c.rotation_euler=(target-c.location).to_track_quat('-Z','Y').to_euler()
s.render.resolution_x=800;s.render.resolution_y=600
for index,frame in enumerate(range(1,41,5)):
    s.frame_set(frame);s.render.filepath=str(out/f'compare-{{index:02d}}.png')
    bpy.ops.render.render(write_still=True)
'''
subprocess.run(['blender','-b',str(OUT/'WarmOriginal-Sprint-r01.blend'),
                '--python-exit-code','1','--python-expr',code],check=True)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(ASSET/'sprint-reference-r04/reference.mp4'),
                '-vf','select=not(mod(n\\,2))','-fps_mode','vfr','-frames:v','8',
                str(work/'source-%02d.png')],check=True)
font=ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc',18)
sheet=Image.new('RGB',(800,8*340),'#f5f1e8');draw=ImageDraw.Draw(sheet)
for index in range(8):
    y=index*340
    for column,name in enumerate([f'source-{index+1:02d}.png',f'compare-{index:02d}.png']):
        im=Image.open(work/name).convert('RGB');im.thumbnail((400,300),Image.Resampling.LANCZOS)
        sheet.paste(im,(column*400,y+34))
    time=index*2/24
    draw.text((10,y+7),f'Seedance · {time:.3f}s · frame {index*2+1}',font=font,fill='#302c25')
    draw.text((410,y+7),f'Blender · {time:.3f}s · frame {index*5+1}',font=font,fill='#302c25')
sheet.save(OUT/'comparison.jpg',quality=94)
(OUT/'comparison.json').write_text(json.dumps({'source':'../sprint-reference-r04/reference.mp4',
    'model':'WarmOriginal-Sprint-r01.blend','samples':[{'time_seconds':i*2/24,
    'source_frame_zero_based':i*2,'blender_frame':i*5+1} for i in range(8)],
    'method':'Actual video frames and native renders at equal times; no image warping or model proportion changes.'},indent=2)+'\n')
print('Saved eight timestamp-matched comparisons.')
