"""One independently consumed logical asset constructor."""
import math
from swordcamp.mesh import ProcMesh, UV_CRIMSON, UV_IRON, px_uv

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
