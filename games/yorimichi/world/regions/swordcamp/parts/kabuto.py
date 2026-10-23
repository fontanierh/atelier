"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_BRASS, UV_CRIMSON, UV_IRON, px_uv, rect_uvs

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
