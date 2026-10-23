"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_BRASS, UV_CRIMSON, UV_IRON, rect_uvs

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
