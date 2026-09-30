"""Quick Workbench views of the houses on their lots, from the road at eye height, before any Unreal run.

    blender -b --python-exit-code 1 --python games/yorimichi/world/regions/houses/preview.py -- [OUT_DIR] [LOTS]

Opens build/yorimichi/houses/Houses.blend (world.houses), adds the ground round each lot from the heightmap, the road
and its guardrails, and stand-ins for the trees, bushes, rocks, lanterns and poles of world.json (cones for
conifers, blobs for broadleaves, in their autumn colours), then renders each lot from the far side of the road at
the player camera's height and from above the road. LOTS: comma-separated lot numbers (default all). Writes
build/yorimichi/review/houses/preview/lot<k>_road.png and lot<k>_above.png.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from village.layout import sample
from houses.layout import to_world, front_y

GROUND = (.13, .15, .055)
# stand-ins: (shape, height, crown radius, crown colour) at scale 1
PLANTS = {
    'Tree_Pine_A': ('cone', 13.0, 2.6, (.03, .10, .07)), 'Tree_Pine_B': ('cone', 11.0, 2.3, (.03, .10, .07)),
    'Tree_Cedar_A': ('cone', 16.0, 2.4, (.025, .08, .05)), 'Tree_Cedar_B': ('cone', 13.0, 2.1, (.025, .08, .05)),
    'Tree_Maple_A': ('blob', 6.5, 3.0, (.55, .10, .02)), 'Tree_Maple_B': ('blob', 5.2, 2.3, (.60, .16, .02)),
    'Tree_Maple_lo': ('blob', 6.5, 3.0, (.55, .12, .02)), 'Tree_Ginkgo': ('blob', 9.0, 2.4, (.62, .45, .04)),
    'Tree_Ginkgo_lo': ('blob', 9.0, 2.1, (.62, .45, .04)), 'Tree_Broad_A': ('blob', 8.5, 2.3, (.08, .16, .03)),
    'Tree_Broad_B': ('blob', 7.0, 1.9, (.10, .17, .03)), 'Tree_Broad_lo': ('blob', 8.5, 2.5, (.09, .16, .03)),
    'Bush_Green_A': ('bush', 1.4, .8, (.05, .12, .02)), 'Bush_Green_B': ('bush', 1.0, .6, (.05, .12, .02)),
    'Bush_Flower_A': ('bush', 1.2, .7, (.35, .12, .20)), 'Bush_Flower_B': ('bush', .9, .55, (.35, .12, .20)),
    'Bush_Ochre_A': ('bush', 1.5, .8, (.40, .22, .03)), 'Bush_Ochre_B': ('bush', 1.1, .6, (.40, .22, .03)),
    'Rock_A': ('rock', 1.0, .9, (.25, .24, .21)), 'Rock_B': ('rock', .7, .55, (.25, .24, .21)), 'Rock_C': ('rock', 1.3, 1.3, (.25, .24, .21)),
    'Lantern': ('lantern', 1.6, .3, (.35, .34, .30)), 'Pole': ('pole', 11.0, .15, (.45, .45, .43)),
    'Pole_Lamp': ('pole', 11.0, .15, (.45, .45, .43)),
}


class Builder:
    def __init__(self): self.v, self.f, self.c = [], [], []

    def face(self, pts, color):
        i = len(self.v); self.v += [tuple(map(float, p)) for p in pts]; self.f.append(tuple(range(i, i + len(pts)))); self.c += [color] * len(pts)

    def ring_solid(self, x, y, z, rings, color, n=8):
        """A lathe of (height, radius) rings round (x, y, z)."""
        R = [[(x + r * math.cos(k * math.tau / n), y + r * math.sin(k * math.tau / n), z + h) for k in range(n)] for h, r in rings]
        for a, b in zip(R[:-1], R[1:]):
            for k in range(n): self.face([a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]], color)

    def link(self, name):
        me = bpy.data.meshes.new(name); me.from_pydata(self.v, [], self.f); me.update()
        col = me.color_attributes.new('Color', 'FLOAT_COLOR', 'POINT')
        for i, c in enumerate(self.c): col.data[i].color = (*c, 1)
        ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob); return ob


def terrain(h, cx, cy, half=55, step=.75):
    xs = np.arange(cx - half, cx + half, step); ys = np.arange(cy - half, cy + half, step); gx, gy = np.meshgrid(xs, ys)
    z = sample(h, gx, gy); nx = len(xs); b = Builder()
    b.v = np.column_stack([gx.ravel(), gy.ravel(), z.ravel()]).tolist(); b.c = [GROUND] * len(b.v)
    b.f = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(len(ys) - 1) for i in range(nx - 1)]
    return b


def road(world, b):
    P = np.array(world['road'], float); w = world['road_width'] / 2
    T = np.gradient(P[:, :2], axis=0); T /= np.linalg.norm(T, axis=1)[:, None]; N = np.column_stack([-T[:, 1], T[:, 0]])
    for k in range(len(P) - 1):
        a, c = P[k], P[k + 1]; na, nc = N[k], N[k + 1]
        for s0, s1, col in ((-w - .6, -w, (.20, .19, .15)), (-w, w, (.07, .07, .075)), (w, w + .6, (.20, .19, .15))):
            b.face([(a[0] + na[0] * s0, a[1] + na[1] * s0, a[2] + .04), (c[0] + nc[0] * s0, c[1] + nc[1] * s0, c[2] + .04),
                    (c[0] + nc[0] * s1, c[1] + nc[1] * s1, c[2] + .04), (a[0] + na[0] * s1, a[1] + na[1] * s1, a[2] + .04)], col)
        for s in (-w + .25, w - .25):   # edge lines
            b.face([(a[0] + na[0] * (s - .07), a[1] + na[1] * (s - .07), a[2] + .05), (c[0] + nc[0] * (s - .07), c[1] + nc[1] * (s - .07), c[2] + .05),
                    (c[0] + nc[0] * (s + .07), c[1] + nc[1] * (s + .07), c[2] + .05), (a[0] + na[0] * (s + .07), a[1] + na[1] * (s + .07), a[2] + .05)], (.8, .8, .78))
    for run in world.get('rail_runs', []):
        R = np.array(run, float)
        for a, c in zip(R[:-1], R[1:]):
            b.face([(a[0], a[1], a[2] + .58), (c[0], c[1], c[2] + .58), (c[0], c[1], c[2] + .85), (a[0], a[1], a[2] + .85)], (.85, .85, .83))
        for a in R[::2]: b.ring_solid(a[0], a[1], a[2] - .2, [(0, .05), (.8, .05)], (.8, .8, .78), 4)


def plants(world, b, cx, cy, half):
    for name, (shape, H, r, col) in PLANTS.items():
        for x, y, z, yaw, s in world['instances'].get(name, []):
            if abs(x - cx) > half or abs(y - cy) > half: continue
            H_, r_ = H * s, r * s
            if shape == 'cone':
                b.ring_solid(x, y, z, [(0, .25 * s), (H_ * .3, .25 * s)], (.12, .07, .03), 6)
                b.ring_solid(x, y, z, [(H_ * .25, r_), (H_ * .6, r_ * .6), (H_, .05)], col, 8)
            elif shape == 'blob':
                b.ring_solid(x, y, z, [(0, .22 * s), (H_ * .45, .18 * s)], (.12, .07, .03), 6)
                b.ring_solid(x, y, z, [(H_ * .35, .2), (H_ * .45, r_ * .9), (H_ * .7, r_), (H_ * .92, r_ * .6), (H_, .05)], col, 9)
            elif shape == 'bush':
                b.ring_solid(x, y, z, [(0, r_ * .7), (H_ * .5, r_), (H_, .05)], col, 8)
            elif shape == 'rock':
                b.ring_solid(x, y, z, [(-.2, r_ * .6), (H_ * .4, r_ * .6), (H_ * .7, r_ * .35), (H_ * .75, .02)], col, 6)
            elif shape == 'lantern':
                b.ring_solid(x, y, z, [(0, .3 * s), (.25 * s, .3 * s), (.25 * s, .12 * s), (1.0 * s, .12 * s), (1.0 * s, .3 * s),
                                       (1.35 * s, .3 * s), (1.35 * s, .45 * s), (1.6 * s, .02)], col, 6)
            else:
                b.ring_solid(x, y, z, [(0, r), (H, r * .7), (H, .01)], col, 6)
                b.ring_solid(x, y, z, [(10.2, .02), (10.2, 1.2), (10.35, 1.2), (10.35, .02)], (.2, .15, .1), 4)


def camera(sc, cam, pos, target, fov):
    cam.location = pos; d = Vector(target) - Vector(pos)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler(); cam.data.angle = math.radians(fov)


def main():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    out = Path(args[0]) if args else yori.REVIEW / 'houses' / 'preview'
    only = {int(k) for k in args[1].split(',')} if len(args) > 1 else None
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(yori.OUT / 'houses' / 'Houses.blend'))
    world = json.loads((yori.OUT / 'world.json').read_text()); h = np.load(yori.OUT / 'heightmap.npy')
    for ob in bpy.data.objects:     # the lots' Ground faces in the preview's ground colour
        if ob.type == 'MESH' and ob.name.startswith('HouseLot'):
            me = ob.data; col = me.color_attributes['Color']
            gi = [i for i, m in enumerate(me.materials) if m and m.name.startswith('Ground')]
            for f in me.polygons:
                if f.material_index in gi:
                    for vi in f.vertices: col.data[vi].color = (*GROUND, 1)
    sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.color_type = 'VERTEX'; sc.display.shading.light = 'STUDIO'
    sc.display.shading.show_shadows = True; sc.display.shading.shadow_intensity = .45; sc.display.shading.show_cavity = True
    sc.display.shading.background_type = 'VIEWPORT'; sc.display.shading.background_color = (.55, .70, .85)
    sc.display.light_direction = (-.45, -.35, .82)
    sc.view_settings.view_transform = 'Standard'
    sc.render.resolution_x, sc.render.resolution_y = 1280, 800
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam')); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.clip_end = 600
    extra = Builder(); road(world, extra); extra.link('Road')
    P = np.array(world['road'], float)
    for k, lot in enumerate(world['houses']['lots'], 1):
        if only and k not in only: continue
        cx, cy = lot['centre']
        t = terrain(h, cx, cy); plants(world, t, cx, cy, 55); ob = t.link(f'Ground_{k}')
        # the road centre in front of the gate, the camera across the road and a few metres along it
        gx = sum(lot['gate']) / 2
        fx, fy = (float(v) for v in to_world(lot, gx, float(front_y(lot, gx))))
        i = int(np.argmin(np.hypot(P[:, 0] - fx, P[:, 1] - fy))); rc = P[i]
        side = np.array([fx - rc[0], fy - rc[1]]); side /= np.linalg.norm(side)
        along = np.array([-side[1], side[0]])
        eye = np.array(rc[:2]) - side * 3.0 + along * 6.0     # a third-person camera behind the player, across the road
        tx, ty = (float(v) for v in to_world(lot, 0.5, -1.0))
        camera(sc, cam, (eye[0], eye[1], rc[2] + 2.4), (tx, ty, lot['level'] + 1.8), 64)
        sc.render.filepath = str(out / f'lot{k}_road.png'); bpy.ops.render.render(write_still=True)
        high = np.array(rc[:2]) - side * 9.0 - along * 10.0
        camera(sc, cam, (high[0], high[1], rc[2] + 9.0), (cx, cy, lot['level'] + 1.0), 55)
        sc.render.filepath = str(out / f'lot{k}_above.png'); bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(ob, do_unlink=True)
    print('PREVIEW DONE', out, flush=True)


if __name__ == '__main__':
    main()
