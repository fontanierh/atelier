"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_BRASS, UV_CRIMSON, UV_IRON, rect_uvs

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
