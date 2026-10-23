"""One independently consumed logical asset constructor."""
from swordcamp.mesh import ProcMesh, UV_BRASS, UV_CRIMSON, UV_INDIGO, UV_RED_SAYA, UV_STEEL, UV_TSUKA_WRAP

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
