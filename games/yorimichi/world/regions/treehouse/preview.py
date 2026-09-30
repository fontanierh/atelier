"""Quick Workbench views of the built tree house on its terrain, before any Unreal run.

    blender -b --python-exit-code 1 --python games/yorimichi/world/regions/treehouse/preview.py -- [OUT_DIR]

Opens build/yorimichi/treehouse/Treehouse.blend, adds the hillside from the heightmap and renders a few fixed views
(vertex colours, flat studio light) to build/yorimichi/review/treehouse/preview/.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import math, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from village.layout import sample

OUT = yori.OUT/'treehouse'
VIEWS = {
    'top': ((-134, 177, 150), (-134, 176.99, 60), 50),
    'south': ((-128, 108, 100), (-134, 170, 70), 55),
    'east': ((-75, 160, 95), (-135, 168, 68), 55),
    'entry': ((-124, 212, 80), (-136, 196, 76.5), 60),
    'porch': ((-135.4, 196.6, 78.6), (-135, 160, 74), 75),
    'lookout': ((-133, 128, 86), (-148, 140, 78), 60),
}


def terrain(h):
    xs = np.arange(-182, -88, .75); ys = np.arange(122, 222, .75); gx, gy = np.meshgrid(xs, ys)
    z = sample(h, gx, gy); nx = len(xs)
    verts = np.column_stack([gx.ravel(), gy.ravel(), z.ravel()]).tolist()
    faces = [(j*nx+i, j*nx+i+1, (j+1)*nx+i+1, (j+1)*nx+i) for j in range(len(ys)-1) for i in range(nx-1)]
    me = bpy.data.meshes.new('Ground'); me.from_pydata(verts, [], faces); me.update()
    col = me.color_attributes.new('Color', 'FLOAT_COLOR', 'POINT')
    for i in range(len(verts)): col.data[i].color = (.10, .16, .05, 1)
    ob = bpy.data.objects.new('Ground', me); bpy.context.collection.objects.link(ob)


def main():
    out = Path(sys.argv[sys.argv.index('--')+1]) if '--' in sys.argv and len(sys.argv) > sys.argv.index('--')+1 else yori.REVIEW/'treehouse'/'preview'
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'Treehouse.blend'))
    terrain(np.load(yori.OUT/'heightmap.npy'))
    sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.color_type = 'VERTEX'; sc.display.shading.light = 'STUDIO'
    sc.display.shading.show_shadows = True; sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.clip_end = 1000
    for name, (pos, target, fov) in VIEWS.items():
        cam.location = pos; d = Vector(target)-Vector(pos)
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler(); cam.data.angle = math.radians(fov)
        sc.render.filepath = str(out/f'{name}.png'); bpy.ops.render.render(write_still=True)
    print('PREVIEW DONE', out, flush=True)


if __name__ == '__main__':
    main()
