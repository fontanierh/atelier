"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_BAMBOO, UV_CREAM, UV_IRON, rect_uvs

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
