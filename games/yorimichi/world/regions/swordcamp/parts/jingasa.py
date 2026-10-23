"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_BRASS, UV_IRON, px_uv, rect_uvs

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
