"""Selected house geometry; no regional export orchestration."""
from mathutils import Vector
import bpy
import math
import numpy as np
from houses.layout import to_world
import random
from village.mesh import Mesh as KitMesh, PALETTE as KIT

PAL = dict(KIT)

PAL.update({
    'plaster': (.66, .59, .43), 'plaster_shade': (.52, .45, .31),
    'timber': (.075, .034, .012), 'timber_light': (.17, .080, .026), 'board': (.042, .021, .010), 'skirt': (.030, .018, .010),
    'tile': (.028, .037, .052), 'tile_roll': (.046, .058, .076), 'tile_edge': (.014, .020, .030),
    'thatch': (.21, .14, .060), 'thatch_dark': (.13, .082, .038), 'thatch_light': (.27, .18, .080), 'thatch_cut': (.33, .22, .10),
    'shoji': (.74, .67, .50), 'glass': (.022, .034, .042), 'soffit': (.040, .020, .009),
    'stone': (.20, .19, .15), 'stone_light': (.31, .29, .22), 'stone_dark': (.10, .095, .075),
    'gravel': (.44, .41, .33), 'moss': (.050, .088, .020), 'hedge': (.036, .090, .018), 'hedge_light': (.060, .135, .026),
    'log': (.20, .12, .045), 'log_end': (.38, .26, .12),
})

DOOR_STEP = {'A': -5.5, 'B': -4.35, 'C': -5.0}

R = random.Random(41)

def variant(key, amount=.06):
    f = R.uniform(1 - amount, 1 + amount)
    return tuple(min(1., c * f) for c in PAL[key])


def smooth(t):
    t = min(1., max(0., t)); return t * t * (3 - 2 * t)


def newell(pts):
    n = Vector((0, 0, 0))
    for a, b in zip(pts, pts[1:] + pts[:1]):
        n.x += (a.y - b.y) * (a.z + b.z); n.y += (a.z - b.z) * (a.x + b.x); n.z += (a.x - b.x) * (a.y + b.y)
    return n


class Mesh(KitMesh):
    """The village kit's mesh with the house palette, a second material slot (1: the terrain's Ground) and faces
    wound by an outward hint (`out`, in the current local frame)."""

    def __init__(self, name, lot=None):
        super().__init__(name); self.slots = []; self.lot = lot

    def poly(self, points, color, slot=0, out=None):
        if isinstance(color, str): color = PAL[color]
        if out is not None and newell([Vector(q) for q in points]).dot(Vector(out)) < 0:
            points = list(points)[::-1]
        k = len(self.faces); super().poly(points, color)
        if len(self.faces) > k: self.slots.append(slot)

    def bar(self, c, s, color):
        """A box without its back and bottom: a member standing proud of a wall that lies behind it (+y)."""
        x, y, z = c; w, d, h = s
        p = [(x + dx * w / 2, y + dy * d / 2, z + dz * h / 2) for dx, dy, dz in
             [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]]
        for f in [(4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (3, 0, 4, 7)]: self.poly([p[i] for i in f], color)

    def log(self, a, b, r, color, end, n=6):
        """A log from a to b (along x), its cut end showing at b."""
        ring = [(r * math.cos(t), r * math.sin(t)) for t in np.linspace(0, math.tau, n + 1)[:-1]]
        A = [(a[0], a[1] + u, a[2] + v) for u, v in ring]; B = [(b[0], b[1] + u, b[2] + v) for u, v in ring]
        for k in range(n):
            u = (ring[k][0] + ring[(k + 1) % n][0]) / 2; v = (ring[k][1] + ring[(k + 1) % n][1]) / 2
            self.poly([A[k], B[k], B[(k + 1) % n], A[(k + 1) % n]], color, out=(0, u, v))
        self.poly(B, end, out=(1, 0, 0))

    def object(self, mats, shade=None):
        data = bpy.data.meshes.new(self.name); data.from_pydata(self.vertices, [], self.faces); data.update()
        used = sorted(set(self.slots)); index = {s: i for i, s in enumerate(used)}
        for s in used: data.materials.append(mats[s])
        uv = data.uv_layers.new(name='UVMap')
        for f, s in zip(data.polygons, self.slots):
            f.material_index = index[s]
            if s == 1:      # the terrain's UVs
                for li in f.loop_indices:
                    co = data.vertices[data.loops[li].vertex_index].co
                    wx, wy = to_world(self.lot, co.x, co.y)
                    uv.data[li].uv = (float(wx) / 6., float(wy) / 6.)
            else:           # dominant-plane UVs: no texture reads them, they give valid tangents
                drop = max(range(3), key=lambda i: abs(f.normal[i])); axes = [i for i in range(3) if i != drop]
                for li in f.loop_indices:
                    co = data.vertices[data.loops[li].vertex_index].co
                    uv.data[li].uv = (co[axes[0]], co[axes[1]])
        col = data.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        for i, c in enumerate(self.colors):
            k = shade(self.vertices[i][2]) if shade else 1.
            col.data[i].color = (c[0] * k, c[1] * k, c[2] * k, c[3])
        obj = bpy.data.objects.new(self.name, data); bpy.context.collection.objects.link(obj)
        return obj


def house_shade(z):
    """Ground-contact darkening on the houses."""
    return .72 + .28 * smooth((z + .1) / 1.4)


