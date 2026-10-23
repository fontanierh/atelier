"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_COBBLE, UV_CREAM, UV_DARKWOOD, UV_IRON, UV_LANTERN, UV_ROPE, UV_STONE_TILE, UV_TIMBER_TILE, rect_uvs

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
