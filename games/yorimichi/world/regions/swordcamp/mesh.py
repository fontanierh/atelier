"""SwordCamp primitive mesh and authored atlas coordinates; no asset construction."""
import math
import bpy
from mathutils import Euler, Matrix, Vector

def px_uv(px, py):
    return (px / 2048.0, 1.0 - py / 2048.0)


def rect_uvs(x0, y0, x1, y1):
    return [px_uv(x0, y1), px_uv(x1, y1), px_uv(x1, y0), px_uv(x0, y0)]


def swatch_uvs(gx, gy, pad=18):
    x0 = 1536 + gx * 128 + pad
    y0 = 1536 + gy * 128 + pad
    return rect_uvs(x0, y0, x0 + 128 - 2 * pad, y0 + 128 - 2 * pad)


UV_BAMBOO = swatch_uvs(0, 0)
UV_CRIMSON = swatch_uvs(1, 0)
UV_INDIGO = swatch_uvs(2, 0)
UV_BRASS = swatch_uvs(3, 0)
UV_STEEL = swatch_uvs(0, 1)
UV_IRON = swatch_uvs(1, 1)
UV_DARKWOOD = swatch_uvs(2, 1)
UV_ROPE = swatch_uvs(3, 1)
UV_LANTERN = swatch_uvs(0, 2)
UV_EMBER = swatch_uvs(1, 2)
UV_RED_SAYA = swatch_uvs(2, 2)
UV_CREAM = swatch_uvs(3, 2)
UV_COBBLE = swatch_uvs(0, 3)
UV_GREEN_BAMBOO = swatch_uvs(1, 3)
UV_BARK = swatch_uvs(2, 3)
UV_SKIN = swatch_uvs(3, 3)

UV_TIMBER_TILE = rect_uvs(1032, 1544, 1272, 1784)
UV_STRAW_TILE = rect_uvs(1288, 1544, 1528, 1784)
UV_STONE_TILE = rect_uvs(1032, 1800, 1272, 2040)
UV_CAST_IRON_TILE = rect_uvs(1288, 1800, 1528, 2040)
UV_TSUKA_WRAP = rect_uvs(1800, 1288, 2040, 1528)
UV_BALE_WEAVE = rect_uvs(1544, 1288, 1784, 1528)
UV_CHEST_FRONT = rect_uvs(1800, 1032, 2040, 1272)


class ProcMesh:
    def __init__(self, name):
        self.name = name
        self.verts = []
        self.faces = []
        self.uvs = []
        self.smooth = []
        self.alphas = []
        self.glows = []
        self.colliders = []
        self.xf = Matrix.Identity(4)
        self._vmap = {}

    def push(self, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1)):
        old = self.xf.copy()
        r = Euler([math.radians(a) for a in rot], 'XYZ').to_matrix().to_4x4()
        s = Matrix.Diagonal((*scale, 1.0))
        self.xf = old @ Matrix.Translation(Vector(loc)) @ r @ s
        return old

    def quad(self, pts, uvs=None, smooth=False, alpha=0.0, glow=None):
        f_uvs = uvs or UV_DARKWOOD[:len(pts)]
        if glow is None:
            glow = 1.0 if (uvs is UV_LANTERN or uvs is UV_EMBER) else 0.0
        face_indices = []
        for k, p in enumerate(pts):
            a_val = float(alpha[k]) if isinstance(alpha, (list, tuple)) else float(alpha)
            wp = tuple(self.xf @ Vector(p))
            if smooth:
                key = (round(wp[0], 4), round(wp[1], 4), round(wp[2], 4), round(a_val, 3), round(glow, 3))
                idx = self._vmap.get(key)
                if idx is None:
                    idx = len(self.verts)
                    self._vmap[key] = idx
                    self.verts.append(wp)
                    self.alphas.append(a_val)
                    self.glows.append(glow)
            else:
                idx = len(self.verts)
                self.verts.append(wp)
                self.alphas.append(a_val)
                self.glows.append(glow)
            face_indices.append(idx)
        if len(set(face_indices)) < 3:
            return
        self.faces.append(tuple(face_indices))
        self.uvs.append(f_uvs)
        self.smooth.append(smooth)

    def box(self, c, s, uvs=None, bevel=0.0, rot=(0, 0, 0)):
        old = self.push(c, rot)
        w, d, h = s
        uv = uvs or UV_DARKWOOD
        if bevel > 0:
            b = min(bevel, w * 0.3, d * 0.3, h * 0.3)
            prof = [
                (-w/2 + b, -d/2), (w/2 - b, -d/2), (w/2, -d/2 + b), (w/2, d/2 - b),
                (w/2 - b, d/2), (-w/2 + b, d/2), (-w/2, d/2 - b), (-w/2, -d/2 + b)
            ]
            rings = []
            for zz, sc in [(-h/2, 0.92), (-h/2 + b, 1.0), (h/2 - b, 1.0), (h/2, 0.92)]:
                rings.append([(px * sc, py * sc, zz) for px, py in prof])
            for a, b_ring in zip(rings[:-1], rings[1:]):
                for k in range(8):
                    k1 = (k + 1) % 8
                    self.quad([a[k], a[k1], b_ring[k1], b_ring[k]], uv, smooth=False)
            self.quad([rings[0][7], rings[0][6], rings[0][5], rings[0][4], rings[0][3], rings[0][2], rings[0][1], rings[0][0]], uv[:1]*8)
            self.quad(rings[-1], uv[:1]*8)
        else:
            p = [(dx*w/2, dy*d/2, dz*h/2) for dx, dy, dz in [
                (-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)
            ]]
            for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:
                self.quad([p[i] for i in f], uv)
        self.xf = old

    def tube(self, p0, p1, r0, r1, uvs=None, segs=12, cap=True, smooth=True):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        if d.length < 1e-6:
            return
        dn = d.normalized()
        up = Vector((0, 0, 1)) if abs(dn.z) < 0.98 else Vector((1, 0, 0))
        x = up.cross(dn).normalized()
        y = dn.cross(x).normalized()
        uv = uvs or UV_BAMBOO
        glow = 1.0 if (uv is UV_LANTERN or uv is UV_EMBER) else 0.0
        ring0, ring1 = [], []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            cs, sn = math.cos(a), math.sin(a)
            ring0.append(p0 + (x * cs + y * sn) * r0)
            ring1.append(p1 + (x * cs + y * sn) * r1)
        for i in range(segs):
            j = (i + 1) % segs
            self.quad([ring0[i], ring0[j], ring1[j], ring1[i]], uv, smooth=smooth, glow=glow)
        if cap:
            if r0 > 1e-4:
                self.quad(list(reversed(ring0)), [uv[0]] * segs, smooth=False, glow=glow)
            if r1 > 1e-4:
                self.quad(ring1, [uv[0]] * segs, smooth=False, glow=glow)

    def torus(self, center, r_major, r_minor, uvs=None, n_maj=18, n_min=8, axis='Z', arc=2*math.pi):
        cx, cy, cz = center
        uv = uvs or UV_ROPE
        rings = []
        steps = n_maj if abs(arc - 2*math.pi) < 1e-3 else n_maj + 1
        for i in range(steps):
            t = (i / n_maj) * arc
            ct, st = math.cos(t), math.sin(t)
            ring = []
            for j in range(n_min):
                p = 2 * math.pi * j / n_min
                cp, sp = math.cos(p), math.sin(p)
                rr = r_major + r_minor * cp
                if axis == 'Z':
                    pt = (cx + rr * ct, cy + rr * st, cz + r_minor * sp)
                elif axis == 'X':
                    pt = (cx + r_minor * sp, cy + rr * ct, cz + rr * st)
                else:
                    pt = (cx + rr * ct, cy + r_minor * sp, cz + rr * st)
                ring.append(pt)
            rings.append(ring)
        for i in range(n_maj):
            i1 = (i + 1) % len(rings)
            for j in range(n_min):
                j1 = (j + 1) % n_min
                self.quad([rings[i][j], rings[i1][j], rings[i1][j1], rings[i][j1]], uv, smooth=True)

    def add_collider(self, c, s):
        self.colliders.append((c, s))

    def to_blender(self, mat):
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.verts, [], self.faces)
        me.update()
        me.materials.append(mat)
        uv_layer = me.uv_layers.new(name='UVMap')
        for fi, poly in enumerate(me.polygons):
            poly.use_smooth = self.smooth[fi]
            f_uvs = self.uvs[fi]
            for k, li in enumerate(poly.loop_indices):
                uv_layer.data[li].uv = f_uvs[k % len(f_uvs)]
        col = me.color_attributes.new(name='Color', type='FLOAT_COLOR', domain='POINT')
        for vi in range(len(self.verts)):
            col.data[vi].color = (self.glows[vi], 1.0, 1.0, self.alphas[vi])
        obj = bpy.data.objects.new(self.name, me)
        bpy.context.collection.objects.link(obj)
        return obj
