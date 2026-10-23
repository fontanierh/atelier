"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_BAMBOO, UV_BRASS, UV_CRIMSON, UV_INDIGO, px_uv

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
