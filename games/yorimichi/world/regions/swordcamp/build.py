#!/usr/bin/env python3
"""Build the Sunburst-textured procedural Kasa Ronin equipment and Roadside Mini-Camp meshes in Blender.

Exports:
- build/yorimichi/swordcamp/fbx/SM_*.fbx (with UCX collision boxes for camp props)
- build/yorimichi/swordcamp/site/*.glb (for the Three.js viewer)
- build/yorimichi/swordcamp/site/render_*.png (studio comparison renders)
"""
import json
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(HERE.parents[1]))
import yori  # noqa: E402

OUT = yori.OUT / 'swordcamp'
ATLAS_PATH = OUT / 'swordcamp_atlas.jpg'
FBX_DIR = OUT / 'fbx'
SITE_ASSETS = OUT / 'site'


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


def build_kasa(m: ProcMesh, origin=(0, 0, 0)):
    """Scout's woven bamboo Sandogasa with domed crown, inner hachimaki headband, and cheek-to-chin cord."""
    old = m.push(origin)
    n_rad = 32
    n_rings = 12
    R_outer = 0.36
    H_cone = 0.230
    rings_top, rings_bot, rings_uv = [], [], []
    for jr in range(n_rings + 1):
        f = jr / n_rings
        r = 0.02 + (R_outer - 0.02) * f
        z = H_cone * (1.0 - (f ** 1.55))
        rt, rb, ruv = [], [], []
        for i in range(n_rad):
            a = 2 * math.pi * i / n_rad
            cs, sn = math.cos(a), math.sin(a)
            rt.append((r * cs, r * sn, z))
            rb.append((r * cs, r * sn, z - 0.008))
            px = 512.0 + (f * 462.0) * cs
            py = 512.0 + (f * 462.0) * sn
            ruv.append(px_uv(px, py))
        rings_top.append(rt)
        rings_bot.append(rb)
        rings_uv.append(ruv)
    for jr in range(n_rings):
        for i in range(n_rad):
            i1 = (i + 1) % n_rad
            uv_q = [rings_uv[jr][i], rings_uv[jr][i1], rings_uv[jr+1][i1], rings_uv[jr+1][i]]
            m.quad([rings_top[jr][i], rings_top[jr][i1], rings_top[jr+1][i1], rings_top[jr+1][i]], uv_q, smooth=True)
            m.quad([rings_bot[jr][i1], rings_bot[jr][i], rings_bot[jr+1][i], rings_bot[jr+1][i1]], uv_q, smooth=True)
    m.tube((0.015, 0, -0.022), (0.015, 0, 0.035), 0.162, 0.158, UV_INDIGO, segs=24, cap=False)
    m.torus((0, 0, -0.002), R_outer, 0.015, UV_INDIGO, n_maj=32, n_min=8)
    for i in range(20):
        a = 2 * math.pi * i / 20
        cs, sn = math.cos(a), math.sin(a)
        rx, ry = R_outer * cs, R_outer * sn
        m.box((rx, ry, -0.002), (0.034, 0.014, 0.030), UV_BAMBOO, bevel=0.003, rot=(0, 0, math.degrees(a)))
    m.tube((0, 0, H_cone - 0.012), (0, 0, H_cone + 0.018), 0.056, 0.040, UV_INDIGO, segs=16, cap=True)
    m.tube((0, 0, H_cone + 0.018), (0, 0, H_cone + 0.030), 0.036, 0.018, UV_BRASS, segs=16, cap=True)
    cord_pts = []
    for k in range(15):
        u = (k / 14.0) * 2.0 - 1.0
        cy = u * 0.145
        cx = 0.04 + 0.065 * (1.0 - u ** 2)
        cz = -0.210 + 0.205 * (u ** 2)
        cord_pts.append((cx, cy, cz))
    for p0, p1 in zip(cord_pts[:-1], cord_pts[1:]):
        m.tube(p0, p1, 0.0075, 0.0075, UV_CRIMSON, segs=8, cap=False)
    m.torus((0.105, 0, -0.212), 0.014, 0.007, UV_CRIMSON, n_maj=12, n_min=6, axis='X')
    m.xf = old


def build_jingasa(m: ProcMesh, origin=(0, 0, 0)):
    """Guard's dark lacquered iron war-hat (Jingasa) with brass ribs, front crescent crest, and rear shikoro neck lames."""
    old = m.push(origin)
    n_rad = 32
    n_rings = 10
    R_outer = 0.33
    H_dome = 0.225
    rings_top, rings_bot, rings_uv = [], [], []
    for jr in range(n_rings + 1):
        f = jr / n_rings
        r = 0.02 + (R_outer - 0.02) * f
        z = H_dome * (1.0 - (f ** 1.55)) - 0.022 * (f ** 2)
        rt, rb, ruv = [], [], []
        for i in range(n_rad):
            a = 2 * math.pi * i / n_rad
            cs, sn = math.cos(a), math.sin(a)
            rt.append((r * cs, r * sn, z))
            rb.append((r * cs, r * sn, z - 0.009))
            px = 1536.0 + (f * 450.0) * cs
            py = 512.0 + (f * 450.0) * sn
            ruv.append(px_uv(px, py))
        rings_top.append(rt)
        rings_bot.append(rb)
        rings_uv.append(ruv)
    for jr in range(n_rings):
        for i in range(n_rad):
            i1 = (i + 1) % n_rad
            uv_q = [rings_uv[jr][i], rings_uv[jr][i1], rings_uv[jr+1][i1], rings_uv[jr+1][i]]
            m.quad([rings_top[jr][i], rings_top[jr][i1], rings_top[jr+1][i1], rings_top[jr+1][i]], uv_q, smooth=True)
            m.quad([rings_bot[jr][i1], rings_bot[jr][i], rings_bot[jr+1][i], rings_bot[jr+1][i1]], UV_IRON, smooth=True)
    m.tube((0.012, 0, -0.020), (0.012, 0, 0.030), 0.164, 0.160, UV_IRON, segs=24, cap=False)
    m.torus((0, 0, -0.022), R_outer, 0.011, UV_BRASS, n_maj=32, n_min=8)
    for i in range(8):
        a = 2 * math.pi * i / 8
        cs, sn = math.cos(a), math.sin(a)
        pts_rib = []
        for k in range(7):
            fk = 0.12 + 0.85 * (k / 6.0)
            rk = 0.02 + (R_outer - 0.02) * fk
            zk = H_dome * (1.0 - (fk ** 1.55)) - 0.022 * (fk ** 2) + 0.005
            pts_rib.append((rk * cs, rk * sn, zk))
        for p0, p1 in zip(pts_rib[:-1], pts_rib[1:]):
            m.tube(p0, p1, 0.006, 0.005, UV_BRASS if i == 0 else UV_IRON, segs=6, cap=False)
    m.tube((0, 0, H_dome - 0.01), (0, 0, H_dome + 0.024), 0.048, 0.022, UV_BRASS, segs=16, cap=True)
    for side in (-1, 1):
        for k in range(6):
            t0, t1 = k / 6.0, (k + 1) / 6.0
            p0 = (0.22 - 0.02 * t0, side * (0.010 + 0.105 * t0), 0.055 + 0.095 * (t0 ** 1.35))
            p1 = (0.22 - 0.02 * t1, side * (0.010 + 0.105 * t1), 0.055 + 0.095 * (t1 ** 1.35))
            m.tube(p0, p1, 0.015 * (1.0 - 0.65 * t0), 0.015 * (1.0 - 0.65 * t1), UV_BRASS, segs=8, cap=True)
    for tier in range(3):
        zt0 = -0.018 - tier * 0.040
        zt1 = zt0 - 0.036
        rt0 = 0.195 + tier * 0.016
        rt1 = rt0 + 0.018
        n_arc = 14
        for ia in range(n_arc):
            u0, u1 = ia / n_arc, (ia + 1) / n_arc
            a0 = math.radians(48.0 + u0 * 264.0)
            a1 = math.radians(48.0 + u1 * 264.0)
            p00 = (rt0 * math.cos(a0), rt0 * math.sin(a0), zt0)
            p01 = (rt0 * math.cos(a1), rt0 * math.sin(a1), zt0)
            p11 = (rt1 * math.cos(a1), rt1 * math.sin(a1), zt1)
            p10 = (rt1 * math.cos(a0), rt1 * math.sin(a0), zt1)
            uv_q = rect_uvs(1036 + u0 * 980, 100 + tier * 260, 1036 + u1 * 980, 340 + tier * 260)
            m.quad([p00, p01, p11, p10], uv_q, smooth=True)
    m.xf = old


def build_kabuto(m: ProcMesh, origin=(0, 0, 0)):
    """Captain's ornate horned Samurai Kabuto helmet with smooth continuous forged golden Kuwagata horns."""
    old = m.push(origin)
    n_rad = 32
    n_rings = 10
    R_bowl = 0.225
    H_bowl = 0.230
    rings_top, rings_bot, rings_uv = [], [], []
    for jr in range(n_rings + 1):
        f = jr / n_rings
        r = 0.02 + (R_bowl - 0.02) * f
        z = H_bowl * (1.0 - (f ** 2.1))
        rt, rb, ruv = [], [], []
        for i in range(n_rad):
            a = 2 * math.pi * i / n_rad
            cs, sn = math.cos(a), math.sin(a)
            rx = r * cs * 1.06 - 0.012
            ry = r * sn * 0.96
            rt.append((rx, ry, z))
            rb.append((rx * 0.96, ry * 0.96, z - 0.008))
            px = 1288 + (0.5 + 0.45 * cs * f) * 240
            py = 1800 + (0.5 + 0.45 * sn * f) * 240
            ruv.append(px_uv(px, py))
        rings_top.append(rt)
        rings_bot.append(rb)
        rings_uv.append(ruv)
    for jr in range(n_rings):
        for i in range(n_rad):
            i1 = (i + 1) % n_rad
            uv_q = [rings_uv[jr][i], rings_uv[jr][i1], rings_uv[jr+1][i1], rings_uv[jr+1][i]]
            m.quad([rings_top[jr][i], rings_top[jr][i1], rings_top[jr+1][i1], rings_top[jr+1][i]], uv_q, smooth=True)
            m.quad([rings_bot[jr][i1], rings_bot[jr][i], rings_bot[jr+1][i], rings_bot[jr+1][i1]], UV_IRON, smooth=True)
    m.tube((0.005, 0, -0.020), (0.005, 0, 0.025), 0.168, 0.165, UV_IRON, segs=24, cap=False)
    m.torus((-0.012, 0, H_bowl), 0.036, 0.010, UV_BRASS, n_maj=18, n_min=6)
    m.torus((-0.012, 0, 0.004), R_bowl, 0.012, UV_BRASS, n_maj=32, n_min=8)
    n_vis = 12
    for iv in range(n_vis):
        u0, u1 = iv / n_vis, (iv + 1) / n_vis
        a0 = math.radians(-62.0 + u0 * 124.0)
        a1 = math.radians(-62.0 + u1 * 124.0)
        r_in, r_out = R_bowl * 0.98, R_bowl + 0.068 * math.cos((u0 - 0.5) * math.pi * 0.9)
        r_out1 = R_bowl + 0.068 * math.cos((u1 - 0.5) * math.pi * 0.9)
        p00 = (r_in * math.cos(a0), r_in * math.sin(a0), 0.018)
        p01 = (r_in * math.cos(a1), r_in * math.sin(a1), 0.018)
        p11 = (r_out1 * math.cos(a1), r_out1 * math.sin(a1), -0.008)
        p10 = (r_out * math.cos(a0), r_out * math.sin(a0), -0.008)
        m.quad([p00, p01, p11, p10], UV_CRIMSON, smooth=True)
    m.box((R_bowl + 0.015, 0, 0.055), (0.022, 0.088, 0.052), UV_BRASS, bevel=0.005)
    m.tube((R_bowl + 0.018, 0, 0.095), (R_bowl + 0.032, 0, 0.095), 0.046, 0.044, UV_CRIMSON, segs=18)
    m.torus((R_bowl + 0.025, 0, 0.095), 0.046, 0.007, UV_BRASS, n_maj=18, n_min=6, axis='X')
    for side in (-1, 1):
        n_h = 14
        ring_list = []
        for k in range(n_h + 1):
            t = k / n_h
            cy = side * (0.028 + 0.215 * (t ** 0.92))
            cz = 0.052 + 0.255 * (t ** 1.18)
            cx = R_bowl + 0.022 - 0.040 * (t ** 1.4)
            w = 0.034 * (1.0 + 0.35 * math.sin(t * math.pi * 0.85)) * (1.0 - 0.78 * (t ** 2.2))
            th = 0.006 * (1.0 - 0.5 * t)
            ty, tz = -side * 0.65, 0.76
            ring_list.append([
                (cx + th, cy - ty * w, cz - tz * w),
                (cx + th, cy + ty * w, cz + tz * w),
                (cx - th, cy + ty * w, cz + tz * w),
                (cx - th, cy - ty * w, cz - tz * w),
            ])
        for k in range(n_h):
            r0, r1 = ring_list[k], ring_list[k+1]
            for j in range(4):
                j1 = (j + 1) % 4
                m.quad([r0[j], r0[j1], r1[j1], r1[j]], UV_BRASS, smooth=True)
        m.quad(ring_list[-1], UV_BRASS, smooth=False)
    for tier in range(4):
        zt0 = 0.002 - tier * 0.040
        zt1 = zt0 - 0.036
        rt0 = 0.205 + tier * 0.018
        rt1 = rt0 + 0.020
        n_arc = 16
        for ia in range(n_arc):
            u0, u1 = ia / n_arc, (ia + 1) / n_arc
            a0 = math.radians(65.0 + u0 * 230.0)
            a1 = math.radians(65.0 + u1 * 230.0)
            p00 = (rt0 * math.cos(a0) - 0.012, rt0 * math.sin(a0), zt0)
            p01 = (rt0 * math.cos(a1) - 0.012, rt0 * math.sin(a1), zt0)
            p11 = (rt1 * math.cos(a1) - 0.012, rt1 * math.sin(a1), zt1)
            p10 = (rt1 * math.cos(a0) - 0.012, rt1 * math.sin(a0), zt1)
            uv_q = rect_uvs(1036 + u0 * 980, 40 + tier * 230, 1036 + u1 * 980, 260 + tier * 230)
            m.quad([p00, p01, p11, p10], uv_q, smooth=True)
    m.xf = old


def build_menpo(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    rows, cols = 10, 14
    grid, grid_uv = [], []
    for r in range(rows + 1):
        v = r / rows
        z = -0.075 + v * 0.14
        row_pts, row_uvs = [], []
        for c in range(cols + 1):
            u = (c / cols) * 2.0 - 1.0
            w = 0.095 * (0.62 + 0.38 * math.sin(v * math.pi * 0.75))
            y = u * w
            base_x = 0.065 * math.cos(u * math.pi * 0.46) * (0.82 + 0.18 * math.sin(v * math.pi))
            nose_bump = 0.032 * math.exp(-((u / 0.18) ** 2)) * max(0.0, math.sin((v - 0.35) / 0.65 * math.pi)) if v > 0.35 else 0.0
            cheek_ridge = 0.010 * math.exp(-(((abs(u) - 0.52) / 0.20) ** 2)) * math.exp(-(((v - 0.48) / 0.22) ** 2))
            chin_cup = 0.012 * math.exp(-((u / 0.35) ** 2)) * math.exp(-(((v - 0.14) / 0.14) ** 2))
            eye_dip = -0.024 * (v - 0.75) / 0.25 * math.exp(-(((abs(u) - 0.46) / 0.25) ** 2)) if v > 0.75 else 0.0
            x = base_x + nose_bump + cheek_ridge + chin_cup
            row_pts.append((x, y, z + eye_dip))
            px = 1536 + (c / cols) * 256.0
            py = 1280 - (r / rows) * 256.0
            row_uvs.append(px_uv(px, py))
        grid.append(row_pts)
        grid_uv.append(row_uvs)
    for r in range(rows):
        for c in range(cols):
            if r == 3 and 5 <= c <= 8:
                continue
            p00, p01 = grid[r][c], grid[r][c+1]
            p11, p10 = grid[r+1][c+1], grid[r+1][c]
            uv_q = [grid_uv[r][c], grid_uv[r][c+1], grid_uv[r+1][c+1], grid_uv[r+1][c]]
            m.quad([p00, p01, p11, p10], uv_q, smooth=True)
            b00 = (p00[0] - 0.008, p00[1] * 0.96, p00[2])
            b01 = (p01[0] - 0.008, p01[1] * 0.96, p01[2])
            b11 = (p11[0] - 0.008, p11[1] * 0.96, p11[2])
            b10 = (p10[0] - 0.008, p10[1] * 0.96, p10[2])
            m.quad([b01, b00, b10, b11], UV_IRON, smooth=True)
    for side in (-1, 1):
        m.torus((0.015, side * 0.092, 0.032), 0.014, 0.006, UV_CRIMSON, n_maj=10, n_min=6, axis='Y')
        m.torus((0.012, side * 0.082, -0.025), 0.012, 0.005, UV_CRIMSON, n_maj=10, n_min=6, axis='Y')
    m.xf = old


def build_do(m: ProcMesh, origin=(0, 0, 0)):
    """Lacquered Samurai Do torso cuirass with clear arm channels and front/back kusazuri waist tassets."""
    old = m.push(origin)
    n_tiers = 5
    n_seg = 28
    for tier in range(n_tiers):
        v0, v1 = tier / n_tiers, (tier + 1) / n_tiers
        z0 = -0.145 + v0 * 0.220
        z1 = -0.145 + v1 * 0.220 + 0.005
        scale_xy0 = 0.98 + 0.05 * math.sin(v0 * math.pi * 0.85)
        scale_xy1 = 0.98 + 0.05 * math.sin(v1 * math.pi * 0.85)
        for i in range(n_seg):
            u0, u1 = i / n_seg, (i + 1) / n_seg
            a0, a1 = 2 * math.pi * u0, 2 * math.pi * u1
            am = 0.5 * (a0 + a1)
            if tier >= 3 and (abs(math.sin(am)) > 0.76):
                continue
            def ring_pt(ang, sc_xy, zz):
                cs, sn = math.cos(ang), math.sin(ang)
                corner = 0.022 * (cs * cs) * (sn * sn) * 4.0
                rx = ((0.166 if cs >= 0 else 0.168) + corner) * sc_xy
                ry = (0.192 + corner) * sc_xy
                return (rx * cs, ry * sn, zz)
            p00 = ring_pt(a0, scale_xy0, z0)
            p01 = ring_pt(a1, scale_xy0, z0)
            p11 = ring_pt(a1, scale_xy1, z1)
            p10 = ring_pt(a0, scale_xy1, z1)
            uv_q = rect_uvs(1036 + u0 * 980, 40 + v0 * 920, 1036 + u1 * 980, 40 + v1 * 920)
            m.quad([p00, p01, p11, p10], uv_q, smooth=True)
            b00 = (p00[0]*0.95, p00[1]*0.95, z0)
            b01 = (p01[0]*0.95, p01[1]*0.95, z0)
            b11 = (p11[0]*0.95, p11[1]*0.95, z1)
            b10 = (p10[0]*0.95, p10[1]*0.95, z1)
            m.quad([b01, b00, b10, b11], UV_IRON, smooth=True)
    m.torus((0, 0, -0.142), 0.182, 0.022, UV_CRIMSON, n_maj=28, n_min=8)
    m.tube((0.164, 0, 0.015), (0.176, 0, 0.015), 0.044, 0.042, UV_BRASS, segs=16)
    for side in (-1, 1):
        sy = side * 0.115
        for k in range(6):
            t0, t1 = k / 6.0, (k + 1) / 6.0
            a0, a1 = math.radians(-55 + t0 * 110), math.radians(-55 + t1 * 110)
            p0 = (0.142 * math.sin(a0), sy, 0.070 + 0.068 * math.cos(a0))
            p1 = (0.142 * math.sin(a1), sy, 0.070 + 0.068 * math.cos(a1))
            m.box(((p0[0]+p1[0])*0.5, sy, (p0[2]+p1[2])*0.5), (0.042, 0.040, 0.018), UV_CRIMSON, bevel=0.004)
    for base_ang in (-42, 0, 42, 138, 180, 222):
        for kt in range(3):
            zv0, zv1 = -0.152 - kt * 0.036, -0.152 - (kt + 1) * 0.036
            fl0, fl1 = 1.05 + kt * 0.06, 1.05 + (kt + 1) * 0.06
            for ks in range(4):
                u0, u1 = ks / 4.0, (ks + 1) / 4.0
                a0 = math.radians(base_ang - 19.0 + u0 * 38.0)
                a1 = math.radians(base_ang - 19.0 + u1 * 38.0)
                def k_pt(ang, fl, zz):
                    cs, sn = math.cos(ang), math.sin(ang)
                    corner = 0.024 * (cs * cs) * (sn * sn) * 4.0
                    return ((0.172 + corner) * fl * cs, (0.192 + corner) * fl * sn, zz)
                p00 = k_pt(a0, fl0, zv0)
                p01 = k_pt(a1, fl0, zv0)
                p11 = k_pt(a1, fl1, zv1)
                p10 = k_pt(a0, fl1, zv1)
                uv_q = rect_uvs(1036 + u0 * 980, 120 + kt * 280, 1036 + u1 * 980, 380 + kt * 280)
                m.quad([p00, p01, p11, p10], uv_q, smooth=True)
    m.xf = old


def build_sode(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    w = 0.24
    h_total = 0.28
    n_lames = 4
    segs_w = 10
    for lame in range(n_lames):
        v0, v1 = lame / n_lames, (lame + 1) / n_lames
        z0 = h_total * (0.5 - v1)
        z1 = h_total * (0.5 - v0) + 0.006
        flare0, flare1 = 1.0 + 0.10 * v0, 1.0 + 0.10 * v1
        for i in range(segs_w):
            u0, u1 = i / segs_w, (i + 1) / segs_w
            a0, a1 = (u0 - 0.5) * 0.72, (u1 - 0.5) * 0.72
            R_curve = 0.30
            x00, y00 = R_curve * (1.0 - math.cos(a0)) + lame * 0.004, w * flare0 * math.sin(a0)
            x01, y01 = R_curve * (1.0 - math.cos(a1)) + lame * 0.004, w * flare0 * math.sin(a1)
            x10, y10 = R_curve * (1.0 - math.cos(a0)) + lame * 0.004, w * flare1 * math.sin(a0)
            x11, y11 = R_curve * (1.0 - math.cos(a1)) + lame * 0.004, w * flare1 * math.sin(a1)
            uv_q = rect_uvs(1036 + u0 * 1000, 12 + v0 * 1000, 1036 + u1 * 1000, 12 + v1 * 1000)
            p00, p01, p11, p10 = (x00, y00, z1), (x01, y01, z1), (x11, y11, z0), (x10, y10, z0)
            m.quad([p10, p11, p01, p00], uv_q, smooth=True)
            th = -0.012
            b00, b01, b11, b10 = (x00+th, y00, z1), (x01+th, y01, z1), (x11+th, y11, z0), (x10+th, y10, z0)
            m.quad([b00, b01, b11, b10], UV_IRON, smooth=True)
            if i == 0:
                m.quad([b10, p10, p00, b00], UV_IRON)
            if i == segs_w - 1:
                m.quad([p11, b11, b01, p01], UV_IRON)
    m.box((0.006, 0, h_total * 0.5 + 0.008), (0.024, w * 0.88, 0.022), UV_IRON, bevel=0.004)
    for sy in (-1, 1):
        m.tube((0.014, sy * 0.078, h_total * 0.42), (0.022, sy * 0.078, h_total * 0.42), 0.011, 0.008, UV_BRASS, segs=10)
        m.torus((0.0, sy * 0.062, h_total * 0.5 + 0.018), 0.015, 0.006, UV_CRIMSON, n_maj=10, n_min=6, axis='X')
    m.xf = old


def build_sashimono(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    m.tube((0, 0, 0.0), (0, 0, 1.18), 0.018, 0.016, UV_BAMBOO, segs=12)
    m.tube((0, 0, -0.01), (0, 0, 0.03), 0.020, 0.020, UV_IRON, segs=12)
    m.tube((0, 0, 1.14), (0, 0, 1.19), 0.018, 0.018, UV_IRON, segs=12)
    for z_node in (0.18, 0.42, 0.66, 0.90, 1.08):
        m.torus((0, 0, z_node), 0.0175, 0.0035, UV_BAMBOO, n_maj=12, n_min=6)
    m.tube((0.05, 0, 1.08), (-0.37, 0, 1.08), 0.013, 0.012, UV_BAMBOO, segs=10)
    m.tube((-0.37, 0, 1.08), (-0.385, 0, 1.08), 0.014, 0.014, UV_IRON, segs=10)
    m.box((0, 0, 1.08), (0.044, 0.044, 0.044), UV_CREAM, bevel=0.006)
    for x_loop in (-0.09, -0.20, -0.31):
        m.box((x_loop, 0, 1.06), (0.026, 0.030, 0.052), UV_CREAM, bevel=0.004)
    for z_loop in (0.20, 0.38, 0.56, 0.74, 0.92):
        m.box((-0.022, 0, z_loop), (0.052, 0.030, 0.028), UV_CREAM, bevel=0.004)
        m.tube((0, 0, z_loop - 0.018), (0, 0, z_loop + 0.018), 0.0195, 0.0195, UV_IRON, segs=10)
    def banner_v_tex(v):
        if v < 0.25:
            return (v / 0.25) * 0.18
        if v <= 0.75:
            return 0.18 + ((v - 0.25) / 0.50) * 0.64
        return 0.82 + ((v - 0.75) / 0.25) * 0.18
    nx, nz = 6, 12
    x_min, x_max = -0.365, -0.045
    z_min, z_max = 0.25, 1.035
    for iz in range(nz):
        v0, v1 = iz / nz, (iz + 1) / nz
        vt0, vt1 = banner_v_tex(v0), banner_v_tex(v1)
        zz0, zz1 = z_max - v0 * (z_max - z_min), z_max - v1 * (z_max - z_min)
        for ix in range(nx):
            u0, u1 = ix / nx, (ix + 1) / nx
            xx0, xx1 = x_min + u0 * (x_max - x_min), x_min + u1 * (x_max - x_min)
            if iz >= nz - 2 and ix == nx // 2 - 1:
                continue
            wy0 = 0.008 * math.sin(u0 * math.pi) * math.sin(v0 * math.pi * 1.5)
            wy1 = 0.008 * math.sin(u1 * math.pi) * math.sin(v1 * math.pi * 1.5)
            uv_q = rect_uvs(u0 * 1024, 1024 + vt0 * 1024, u1 * 1024, 1024 + vt1 * 1024)
            p00, p01, p11, p10 = (xx0, wy0 - 0.003, zz0), (xx1, wy1 - 0.003, zz0), (xx1, wy1 - 0.003, zz1), (xx0, wy0 - 0.003, zz1)
            m.quad([p10, p11, p01, p00], uv_q, smooth=True, alpha=[(1.0 - u0) * 0.6, (1.0 - u1) * 0.6, (1.0 - u1) * 0.6, (1.0 - u0) * 0.6])
            q00, q01, q11, q10 = (xx0, wy0 + 0.003, zz0), (xx1, wy1 + 0.003, zz0), (xx1, wy1 + 0.003, zz1), (xx0, wy0 + 0.003, zz1)
            m.quad([q00, q01, q11, q10], uv_q, smooth=True, alpha=[(1.0 - u0) * 0.6, (1.0 - u1) * 0.6, (1.0 - u1) * 0.6, (1.0 - u0) * 0.6])
    m.xf = old


def build_sword(m: ProcMesh, origin=(0, 0, 0), blade_len=0.72, hilt_len=0.24, curve=0.032, sheathed=False, red_saya=False):
    old = m.push(origin)
    m.tube((0, 0, -hilt_len), (0, 0, -hilt_len + 0.018), 0.016, 0.017, UV_BRASS, segs=10)
    n_h = 8
    for i in range(n_h):
        t0, t1 = i / n_h, (i + 1) / n_h
        z0 = -hilt_len + 0.018 + t0 * (hilt_len - 0.034)
        z1 = -hilt_len + 0.018 + t1 * (hilt_len - 0.034)
        x0 = -curve * 0.18 * (1.0 - t0) ** 2
        x1 = -curve * 0.18 * (1.0 - t1) ** 2
        m.box(((x0 + x1) * 0.5, 0, (z0 + z1) * 0.5), (0.034, 0.022, (z1 - z0) + 0.002), UV_TSUKA_WRAP, bevel=0.004)
    m.tube((0, 0, -0.016), (0, 0, 0.0), 0.017, 0.018, UV_BRASS, segs=10)
    m.tube((0, 0, -0.004), (0, 0, 0.005), 0.044, 0.044, UV_BRASS, segs=18)
    m.torus((0, 0, 0.0005), 0.042, 0.005, UV_BRASS, n_maj=18, n_min=6)
    m.box((0, 0, 0.016), (0.030, 0.015, 0.026), UV_BRASS, bevel=0.002)
    if sheathed:
        saya_uv = UV_RED_SAYA if red_saya else UV_INDIGO
        n_b = 14
        for i in range(n_b):
            t0, t1 = i / n_b, (i + 1) / n_b
            z0, z1 = 0.026 + t0 * blade_len, 0.026 + t1 * blade_len
            x0, x1 = -curve * (t0 ** 2), -curve * (t1 ** 2)
            m.box(((x0 + x1) * 0.5, 0, (z0 + z1) * 0.5), (0.034, 0.018, (z1 - z0) + 0.003), saya_uv, bevel=0.004)
        m.box((-curve, 0, 0.026 + blade_len + 0.012), (0.033, 0.018, 0.024), UV_BRASS, bevel=0.004)
        for k in range(4):
            zk = 0.11 + k * 0.016
            xk = -curve * ((zk / blade_len) ** 2)
            m.torus((xk, 0, zk), 0.018, 0.0055, UV_CRIMSON, n_maj=12, n_min=6)
    else:
        n_b = 16
        rings = []
        for i in range(n_b + 1):
            t = i / n_b
            z = 0.028 + t * blade_len
            cx = -curve * (t ** 2)
            taper = 1.0 - 0.65 * max(0.0, (t - 0.85) / 0.15) ** 1.6
            w_b, th_b = 0.028 * taper, 0.007 * taper
            rings.append([
                (cx - w_b * 0.5, 0.0, z),
                (cx - w_b * 0.05, -th_b, z),
                (cx + w_b * 0.55, 0.0, z),
                (cx - w_b * 0.05,  th_b, z),
            ])
        for i in range(n_b):
            r0, r1 = rings[i], rings[i+1]
            for k in range(4):
                k1 = (k + 1) % 4
                m.quad([r0[k], r0[k1], r1[k1], r1[k]], UV_STEEL, smooth=True)
        tip = (-curve * 1.03 + 0.008, 0.0, 0.028 + blade_len + 0.024)
        r_last = rings[-1]
        for k in range(4):
            k1 = (k + 1) % 4
            m.quad([r_last[k], r_last[k1], tip], UV_STEEL[:3], smooth=True)
    m.xf = old


def build_jinmaku(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    span, post_h = 3.2, 2.15
    for side in (-1, 1):
        px = side * (span * 0.5)
        m.box((px, 0, 0.14), (0.48, 0.48, 0.28), UV_STONE_TILE, bevel=0.05)
        m.box((px, 0, 0.29), (0.36, 0.36, 0.08), UV_COBBLE, bevel=0.02)
        m.box((px, 0, 0.28 + post_h * 0.5), (0.22, 0.22, post_h), UV_TIMBER_TILE, bevel=0.025)
        for rz in (0.44, 0.49, 0.54, 0.59, 2.10, 2.15, 2.20):
            m.torus((px, 0, rz), 0.135, 0.026, UV_ROPE, n_maj=14, n_min=6)
    m.tube((-span * 0.5 - 0.22, 0, 2.15), (span * 0.5 + 0.22, 0, 2.15), 0.052, 0.052, UV_TIMBER_TILE, segs=12)
    for i in range(7):
        lx = -span * 0.42 + (i / 6.0) * (span * 0.84)
        m.box((lx, 0, 2.09), (0.09, 0.12, 0.16), UV_CREAM, bevel=0.015)
    nx, nz = 20, 10
    x0_c, x1_c = -span * 0.44, span * 0.44
    z0_c, z1_c = 0.42, 2.02
    for iz in range(nz):
        v0, v1 = iz / nz, (iz + 1) / nz
        zz0, zz1 = z1_c - v0 * (z1_c - z0_c), z1_c - v1 * (z1_c - z0_c)
        for ix in range(nx):
            u0, u1 = ix / nx, (ix + 1) / nx
            xx0, xx1 = x0_c + u0 * (x1_c - x0_c), x0_c + u1 * (x1_c - x0_c)
            y0 = 0.028 * math.sin(u0 * math.pi * 6.0) * (0.3 + 0.7 * v0)
            y1 = 0.028 * math.sin(u1 * math.pi * 6.0) * (0.3 + 0.7 * v1)
            uv_q = rect_uvs(1024 + u0 * 512, 1024 + v0 * 512, 1024 + u1 * 512, 1024 + v1 * 512)
            m.quad([(xx0, y0 - 0.008, zz1), (xx1, y1 - 0.008, zz1), (xx1, y1 - 0.008, zz0), (xx0, y0 - 0.008, zz0)],
                   uv_q, smooth=True, alpha=[v1 * 0.5, v1 * 0.5, v0 * 0.5, v0 * 0.5])
            m.quad([(xx0, y0 + 0.008, zz0), (xx1, y1 + 0.008, zz0), (xx1, y1 + 0.008, zz1), (xx0, y0 + 0.008, zz1)],
                   uv_q, smooth=True, alpha=[v0 * 0.5, v0 * 0.5, v1 * 0.5, v1 * 0.5])
    lx = span * 0.5 + 0.26
    m.box((span * 0.5 + 0.16, 0, 2.15), (0.32, 0.09, 0.09), UV_TIMBER_TILE, bevel=0.01)
    m.tube((lx, 0, 2.12), (lx, 0, 1.94), 0.012, 0.012, UV_IRON, segs=8)
    m.tube((lx, 0, 1.90), (lx, 0, 1.95), 0.11, 0.09, UV_IRON, segs=16)
    m.tube((lx, 0, 1.38), (lx, 0, 1.43), 0.09, 0.11, UV_IRON, segs=16)
    for k in range(8):
        t0, t1 = k / 8.0, (k + 1) / 8.0
        z_a, z_b = 1.43 + t0 * 0.47, 1.43 + t1 * 0.47
        r_a, r_b = 0.11 + 0.075 * math.sin(t0 * math.pi), 0.11 + 0.075 * math.sin(t1 * math.pi)
        m.tube((lx, 0, z_a), (lx, 0, z_b), r_a, r_b, UV_LANTERN, segs=18, cap=False)
        if 0 < k < 8:
            m.torus((lx, 0, z_a), r_a + 0.003, 0.004, UV_DARKWOOD, n_maj=18, n_min=6)
    m.add_collider((0, 0, 1.15), (span + 0.5, 0.45, 2.3))
    m.xf = old


def build_firepit(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    rng = random.Random(108)
    n_stones = 14
    for i in range(n_stones):
        a = 2 * math.pi * i / n_stones
        r = 0.78 + rng.uniform(-0.04, 0.04)
        sx, sy, sz = 0.34 + rng.uniform(-0.04, 0.05), 0.28 + rng.uniform(-0.03, 0.04), 0.24 + rng.uniform(-0.03, 0.05)
        m.box((r * math.cos(a), r * math.sin(a), sz * 0.45), (sx, sy, sz), UV_COBBLE if i % 2 == 0 else UV_STONE_TILE,
              bevel=0.06, rot=(rng.uniform(-6, 6), rng.uniform(-6, 6), math.degrees(a) + rng.uniform(-12, 12)))
    m.tube((0, 0, 0.0), (0, 0, 0.14), 0.62, 0.28, UV_EMBER, segs=16)
    m.tube((0, 0, 0.14), (0, 0, 0.24), 0.28, 0.08, UV_LANTERN, segs=12)
    for i in range(6):
        a = 2 * math.pi * i / 6 + 0.25
        p0 = (0.48 * math.cos(a), 0.48 * math.sin(a), 0.08)
        p1 = (0.10 * math.cos(a + 0.4), 0.10 * math.sin(a + 0.4), 0.28)
        m.tube(p0, p1, 0.058, 0.048, UV_BARK if i % 2 == 0 else UV_EMBER, segs=8)
    apex = Vector((0, 0, 1.62))
    for i in range(3):
        a = 2 * math.pi * i / 3 + 0.52
        base = Vector((0.82 * math.cos(a), 0.82 * math.sin(a), 0.04))
        top = apex + Vector((-0.09 * math.cos(a), -0.09 * math.sin(a), 0.18))
        m.tube(base, top, 0.042, 0.032, UV_GREEN_BAMBOO, segs=10)
        for f in (0.2, 0.4, 0.6, 0.8):
            pt = base.lerp(top, f)
            m.torus(tuple(pt), 0.040, 0.006, UV_BAMBOO, n_maj=10, n_min=6)
    for k in range(6):
        m.torus((0, 0, 1.50 + k * 0.032), 0.085 - k * 0.003, 0.022, UV_ROPE, n_maj=14, n_min=6)
    for k in range(5):
        m.torus((0, 0, 1.44 - k * 0.055), 0.026, 0.008, UV_IRON, n_maj=10, n_min=6, axis='X' if k % 2 == 0 else 'Y')
    kz = 0.72
    prof = [(0.0, 0.11), (0.04, 0.21), (0.13, 0.24), (0.22, 0.19), (0.26, 0.12), (0.28, 0.13)]
    for (z0, r0), (z1, r1) in zip(prof[:-1], prof[1:]):
        m.tube((0, 0, kz + z0), (0, 0, kz + z1), r0, r1, UV_CAST_IRON_TILE, segs=18, cap=False)
    m.tube((0, 0, kz + 0.28), (0, 0, kz + 0.31), 0.11, 0.02, UV_IRON, segs=14)
    m.tube((0, 0, kz + 0.31), (0, 0, kz + 0.34), 0.028, 0.022, UV_IRON, segs=10)
    m.tube((0.18, 0, kz + 0.15), (0.29, 0, kz + 0.25), 0.036, 0.022, UV_IRON, segs=10)
    m.torus((0, 0, kz + 0.28), 0.16, 0.014, UV_IRON, n_maj=14, n_min=6, axis='Y', arc=math.pi)
    m.add_collider((0, 0, 0.55), (1.75, 1.75, 1.1))
    m.xf = old


def build_weapon_rack_clean(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    rx = -0.42
    for side in (-1, 1):
        sy = side * 0.46
        m.box((rx, sy, 0.06), (0.36, 0.14, 0.12), UV_TIMBER_TILE, bevel=0.015)
        m.box((rx, sy, 0.56), (0.09, 0.10, 0.96), UV_TIMBER_TILE, bevel=0.012)
        for tz in (0.58, 0.88):
            m.box((rx + 0.06, sy, tz), (0.14, 0.08, 0.05), UV_DARKWOOD, bevel=0.008, rot=(0, -15, 0))
    m.box((rx, 0, 0.20), (0.06, 0.98, 0.09), UV_TIMBER_TILE, bevel=0.01)
    m.box((rx, 0, 0.44), (0.05, 0.98, 0.06), UV_TIMBER_TILE, bevel=0.008)
    for tz, red in [(0.93, False), (0.63, True)]:
        s_old = m.push((rx + 0.07, -0.26, tz), rot=(-90, 0, 0))
        build_sword(m, origin=(0, 0, 0), blade_len=0.76, hilt_len=0.25, curve=0.034, sheathed=True, red_saya=red)
        m.xf = s_old
    mx = 0.52
    m.box((mx, 0, 0.08), (0.68, 0.22, 0.16), UV_TIMBER_TILE, bevel=0.02)
    m.box((mx, 0, 0.08), (0.22, 0.68, 0.16), UV_TIMBER_TILE, bevel=0.02)
    m.box((mx, 0, 0.78), (0.19, 0.19, 1.48), UV_TIMBER_TILE, bevel=0.02)
    for tier in range(5):
        tz0 = 0.48 + tier * 0.165
        m.tube((mx, 0, tz0), (mx, 0, tz0 + 0.158), 0.138, 0.136, UV_STRAW_TILE, segs=16)
        m.torus((mx, 0, tz0 + 0.158), 0.135, 0.012, UV_ROPE, n_maj=16, n_min=6)
    for rz in (0.50, 0.54, 0.58, 1.24, 1.28, 1.32):
        m.torus((mx, 0, rz), 0.144, 0.018, UV_CRIMSON, n_maj=16, n_min=6)
    m.add_collider((0, 0, 0.75), (1.55, 1.15, 1.5))
    m.xf = old


def build_bales_and_chest(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)

    def add_tawara(bx, by, bz, yaw_deg):
        t_old = m.push((bx, by, bz), rot=(0, 90, yaw_deg))
        segs_z = 8
        for i in range(segs_z):
            f0, f1 = i / segs_z, (i + 1) / segs_z
            z0, z1 = -0.36 + f0 * 0.72, -0.36 + f1 * 0.72
            r0 = 0.21 + 0.045 * math.sin(f0 * math.pi)
            r1 = 0.21 + 0.045 * math.sin(f1 * math.pi)
            m.tube((0, 0, z0), (0, 0, z1), r0, r1, UV_STRAW_TILE, segs=16, cap=(i == 0 or i == segs_z - 1))
        for rz in (-0.25, -0.09, 0.09, 0.25):
            rr = 0.21 + 0.045 * math.sin(((rz + 0.36) / 0.72) * math.pi)
            m.torus((0, 0, rz), rr + 0.006, 0.018, UV_ROPE, n_maj=16, n_min=6)
        for i_sp in range(6):
            ang = 2 * math.pi * i_sp / 6
            cs, sn = math.cos(ang), math.sin(ang)
            m.tube((0.23 * cs, 0.23 * sn, -0.33), (0.23 * cs, 0.23 * sn, 0.33), 0.011, 0.011, UV_ROPE, segs=6)
        for end_s in (-1, 1):
            m.torus((0, 0, end_s * 0.36), 0.062, 0.024, UV_ROPE, n_maj=12, n_min=6)
            for i_r in range(6):
                ang = 2 * math.pi * i_r / 6
                m.tube((0.05 * math.cos(ang), 0.05 * math.sin(ang), end_s * 0.36),
                       (0.20 * math.cos(ang), 0.20 * math.sin(ang), end_s * 0.35), 0.012, 0.012, UV_ROPE, segs=6)
        m.xf = t_old

    add_tawara(-0.48, -0.10, 0.25, 14.0)
    add_tawara(-0.45,  0.04, 0.68, -8.0)
    cx, cy, cz = 0.44, 0.0, 0.34
    cw, cd, ch = 0.86, 0.58, 0.64
    m.box((cx, cy, cz), (cw, cd, ch), UV_TIMBER_TILE, bevel=0.02)
    m.box((cx, cy, cz + ch * 0.5 + 0.045), (cw + 0.04, cd + 0.04, 0.09), UV_TIMBER_TILE, bevel=0.015)
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz_off in (-ch * 0.5 + 0.06, ch * 0.5 + 0.03):
                m.box((cx + sx * (cw * 0.5 - 0.05), cy + sy * (cd * 0.5 - 0.05), cz + sz_off),
                      (0.14, 0.14, 0.12), UV_IRON, bevel=0.008)
    m.box((cx, cy - cd * 0.5 - 0.012, cz + 0.16), (0.11, 0.03, 0.22), UV_IRON, bevel=0.006)
    m.torus((cx, cy - cd * 0.5 - 0.024, cz + 0.10), 0.024, 0.008, UV_IRON, n_maj=10, n_min=6, axis='Y')
    for sx in (-1, 1):
        m.torus((cx + sx * (cw * 0.5 + 0.015), cy, cz + 0.05), 0.055, 0.012, UV_IRON, n_maj=10, n_min=6, axis='X')
    m.add_collider((0, 0, 0.45), (1.85, 0.95, 0.92))
    m.xf = old


def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def make_material():
    m = bpy.data.materials.new('M_SwordCamp')
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = 0.88
    bsdf.inputs['Specular IOR Level'].default_value = 0.08
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(str(ATLAS_PATH))
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.nodes.active = tex
    return m


def export_fbx_and_glb(proc: ProcMesh, mat, fbx_name=None, glb_name=None):
    clear_scene()
    m = make_material()
    obj = proc.to_blender(m)
    objs = [obj]
    if fbx_name:
        for idx, (cc, cs) in enumerate(proc.colliders):
            bpy.ops.mesh.primitive_cube_add(size=1.0, location=cc)
            ucx = bpy.context.object
            ucx.name = f'UCX_{fbx_name}_{idx:02d}'
            ucx.scale = cs
            bpy.ops.object.transform_apply(scale=True)
            objs.append(ucx)
        bpy.ops.object.select_all(action='DESELECT')
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = obj
        FBX_DIR.mkdir(parents=True, exist_ok=True)
        from atelier.blender.fbx import export_fbx as export_scene_fbx
        export_scene_fbx(
            filepath=str(FBX_DIR / f'{fbx_name}.fbx'),
            use_selection=True,
            apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_ALL',
            axis_forward='-Y',
            axis_up='Z',
            object_types={'MESH'},
            mesh_smooth_type='FACE',
            bake_anim=False,
            use_custom_props=False,
            path_mode='STRIP',
        )
    if glb_name:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        SITE_ASSETS.mkdir(parents=True, exist_ok=True)
        bpy.ops.export_scene.gltf(
            filepath=str(SITE_ASSETS / f'{glb_name}.glb'),
            use_selection=True,
            export_format='GLB',
            export_apply=True,
        )
    return len(obj.data.polygons)


def render_showcase(proc: ProcMesh, out_png: Path, cam_loc, cam_target, ortho_scale=None, res=(1536, 1024)):
    clear_scene()
    m = make_material()
    proc.to_blender(m)
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_WORKBENCH'
    sc.display.shading.light = 'STUDIO'
    sc.display.shading.color_type = 'TEXTURE'
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = 'BOTH'
    sc.display.shading.show_shadows = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    world = bpy.data.worlds.new('StudioWorld')
    world.color = (0.76, 0.76, 0.77)
    sc.world = world
    cam_data = bpy.data.cameras.new('Cam')
    if ortho_scale:
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = ortho_scale
    else:
        cam_data.lens = 42
    cam = bpy.data.objects.new('Cam', cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.location = Vector(cam_loc)
    cam.rotation_euler = (Vector(cam_target) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = str(out_png)
    bpy.ops.render.render(write_still=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    FBX_DIR.mkdir(parents=True, exist_ok=True)
    assert ATLAS_PATH.is_file(), f'Missing {ATLAS_PATH}; run world.swordcamp_atlas first'
    showcase = '--showcase' in sys.argv
    manifest = {}
    assets = [
        ('SM_RoninKasa', lambda m: build_kasa(m)),
        ('SM_GuardJingasa', lambda m: build_jingasa(m)),
        ('SM_CaptainKabuto', lambda m: build_kabuto(m)),
        ('SM_RoninMenpo', lambda m: build_menpo(m)),
        ('SM_RoninDo', lambda m: build_do(m)),
        ('SM_RoninSode', lambda m: build_sode(m)),
        ('SM_RoninSashimono', lambda m: build_sashimono(m)),
        ('SM_RoninKatana', lambda m: build_sword(m, blade_len=0.72, hilt_len=0.24, curve=0.030, sheathed=False)),
        ('SM_RoninNodachi', lambda m: build_sword(m, blade_len=1.06, hilt_len=0.34, curve=0.046, sheathed=False)),
        ('SM_RoninWakizashi', lambda m: build_sword(m, blade_len=0.46, hilt_len=0.16, curve=0.018, sheathed=True, red_saya=False)),
        ('SM_CampJinmaku', lambda m: build_jinmaku(m)),
        ('SM_CampFirePit', lambda m: build_firepit(m)),
        ('SM_CampWeaponRack', lambda m: build_weapon_rack_clean(m)),
        ('SM_CampBales', lambda m: build_bales_and_chest(m)),
    ]
    for name, fn in assets:
        pm = ProcMesh(name)
        fn(pm)
        polys = export_fbx_and_glb(pm, None, fbx_name=name, glb_name=name.lower() if showcase else None)
        manifest[name] = {'polygons': polys, 'colliders': len(pm.colliders)}
        print(f'[swordcamp] Built {name}: {polys} polygons, {len(pm.colliders)} colliders', flush=True)

    if showcase:
        SITE_ASSETS.mkdir(parents=True, exist_ok=True)
        kit_ronin = ProcMesh('RoninArmorKit')
        build_kasa(kit_ronin, origin=(-0.72, 0.0, 0.45))
        build_jingasa(kit_ronin, origin=(0.0, 0.0, 0.45))
        build_kabuto(kit_ronin, origin=(0.68, 0.0, 0.45))
        old = kit_ronin.push((-0.72, -0.05, -0.02), rot=(0, 0, -90), scale=(1.28, 1.28, 1.28))
        build_menpo(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((0.0, 0.0, -0.05), rot=(0, 0, -90))
        build_do(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((-0.38, 0.0, -0.04), rot=(0, -8, -72))
        build_sode(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((0.38, 0.0, -0.04), rot=(0, 8, -108))
        build_sode(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((0.82, 0.0, -0.32), rot=(0, 0, 0))
        build_sashimono(kit_ronin)
        kit_ronin.xf = old
        old = kit_ronin.push((-0.68, 0.0, -0.34), rot=(0, 90, 0))
        build_sword(kit_ronin, blade_len=0.72, hilt_len=0.24, curve=0.030, sheathed=False)
        kit_ronin.xf = old
        old = kit_ronin.push((-0.74, 0.0, -0.50), rot=(0, 90, 0))
        build_sword(kit_ronin, blade_len=1.06, hilt_len=0.34, curve=0.046, sheathed=False)
        kit_ronin.xf = old
        export_fbx_and_glb(kit_ronin, None, glb_name='ronin_kit_scene')
        render_showcase(kit_ronin, SITE_ASSETS / 'render_ronin_kit.png', cam_loc=(0.0, -2.9, 0.15), cam_target=(0.0, 0.0, 0.10), ortho_scale=2.45)

        kit_camp = ProcMesh('CampPropsKit')
        old = kit_camp.push((-1.45, 0.55, 0.35), rot=(0, 0, 18), scale=(0.68, 0.68, 0.68))
        build_jinmaku(kit_camp)
        kit_camp.xf = old
        old = kit_camp.push((1.35, 0.45, 0.35), scale=(0.85, 0.85, 0.85))
        build_firepit(kit_camp)
        kit_camp.xf = old
        old = kit_camp.push((-1.35, -0.65, -0.95), rot=(0, 0, -68), scale=(0.88, 0.88, 0.88))
        build_weapon_rack_clean(kit_camp)
        kit_camp.xf = old
        old = kit_camp.push((1.25, -0.65, -0.88), rot=(0, 0, -14), scale=(0.95, 0.95, 0.95))
        build_bales_and_chest(kit_camp)
        kit_camp.xf = old
        export_fbx_and_glb(kit_camp, None, glb_name='camp_kit_scene')
        render_showcase(kit_camp, SITE_ASSETS / 'render_camp_kit.png', cam_loc=(0.0, -6.2, 2.45), cam_target=(0.0, 0.0, 0.10), ortho_scale=5.75)

    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('SWORDCAMP PROCEDURAL BUILD COMPLETE', flush=True)


if __name__ == '__main__':
    main()
