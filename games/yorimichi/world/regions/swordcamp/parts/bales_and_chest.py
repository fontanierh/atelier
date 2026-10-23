"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_IRON, UV_ROPE, UV_STRAW_TILE, UV_TIMBER_TILE

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
