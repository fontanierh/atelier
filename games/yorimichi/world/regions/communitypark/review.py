"""EEVEE placement captures from the generated blend, before Unreal import.

Run through atelier.safety.guarded, after world.communitypark. These are source
and terrain previews; the game review in tools/review_communitypark.py is separate.
"""
import math
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori
import bpy
import numpy as np
from mathutils import Vector
from communitypark import layout as L
from communitypark.build import mesh
from hidamari.layout import north_height
from hidamari.mountains import colours

OUT = yori.OUT/'communitypark/blender-review'
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(yori.OUT/'communitypark/CommunityPark.blend'))
for obj in bpy.data.objects:
    obj.location = L.ORIGIN; obj.rotation_euler.z = math.radians(L.YAW)
    if obj.name == 'SM_CP_Seed': obj.hide_render = True

xs = np.arange(1140., 1441., 2.); ys = np.arange(330., 711., 2.)
x, y = np.meshgrid(xs, ys); z = north_height(x, y)
vertices = np.stack((x, y, z), axis=-1).reshape(-1, 3); faces = []; width = len(xs)
for j in range(len(ys)-1):
    for i in range(len(xs)-1):
        if L.cell_inside(xs[i], ys[j], 2.): continue
        a = j*width+i; faces.extend([(a, a+1, a+width+1), (a, a+width+1, a+width)])
mesh('ReviewSurroundingGround', vertices, faces, bpy.data.materials['CP_Ground'], colors=colours(x, y, z).reshape(-1, 3))

sc = bpy.context.scene; sc.render.engine = 'BLENDER_EEVEE'
sc.render.resolution_x = 1500; sc.render.resolution_y = 1000; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'; sc.view_settings.view_transform = 'AgX'
sc.world = bpy.data.worlds.new('ReviewSky'); sc.world.use_nodes = True
bg = sc.world.node_tree.nodes.get('Background'); bg.inputs['Color'].default_value = (.42, .55, .72, 1); bg.inputs['Strength'].default_value = .55
sun = bpy.data.lights.new('ReviewSun', 'SUN'); sun.energy = 4; sun.angle = math.radians(3); sun.color = (1., .93, .82)
obj = bpy.data.objects.new('ReviewSun', sun); sc.collection.objects.link(obj); obj.rotation_euler = (math.radians(30), math.radians(-25), math.radians(-40))
for name, location, target, lens in [('overview', (1420, 380, 145), (1280, 560, 48), 35),
                                    ('entrance', (1316, 496, 51), (1302, 555, 50), 25),
                                    ('bowls', (1242, 572, 65), (1280, 563, 46), 28)]:
    camera = bpy.data.cameras.new(name); camera.lens = lens; camera.clip_end = 3000
    obj = bpy.data.objects.new(name, camera); sc.collection.objects.link(obj); obj.location = location
    obj.rotation_euler = (Vector(target)-Vector(location)).to_track_quat('-Z', 'Y').to_euler(); sc.camera = obj
    sc.render.filepath = str(OUT/f'{name}.png'); bpy.ops.render.render(write_still=True)
    print('COMMUNITY PARK PREVIEW', sc.render.filepath, flush=True)
