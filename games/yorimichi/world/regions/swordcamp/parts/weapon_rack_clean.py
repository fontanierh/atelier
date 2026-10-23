"""One independently consumed logical asset constructor."""
from swordcamp.mesh import ProcMesh, UV_CRIMSON, UV_DARKWOOD, UV_ROPE, UV_STRAW_TILE, UV_TIMBER_TILE
from swordcamp.parts.sword import build_sword

def build_weapon_rack_clean(m: ProcMesh, origin=(0, 0, 0)):
    old = m.push(origin)
    rx = -0.42
    for side in (-1, 1):
        sy = side * 0.46
        m.box((rx, sy, 0.06), (0.36, 0.14, 0.12), UV_TIMBER_TILE, bevel=0.015)
        m.box((rx, sy, 0.56), (0.09, 0.10, 0.96), UV_TIMBER_TILE, bevel=0.012)
        for tz in (0.58, 0.88):
            m.box((rx + 0.06, sy, tz), (0.14, 0.08, 0.05), UV_DARKWOOD, bevel=0.008, rot=(0, -15, 0))
    m.box((rx, 0, 0.20), (0.06, 0.98, 0.09), UV_TIMBER_TILE, bevel=0.01)
    m.box((rx, 0, 0.44), (0.05, 0.98, 0.06), UV_TIMBER_TILE, bevel=0.008)
    for tz, red in [(0.93, False), (0.63, True)]:
        s_old = m.push((rx + 0.07, -0.26, tz), rot=(-90, 0, 0))
        build_sword(m, origin=(0, 0, 0), blade_len=0.76, hilt_len=0.25, curve=0.034, sheathed=True, red_saya=red)
        m.xf = s_old
    mx = 0.52
    m.box((mx, 0, 0.08), (0.68, 0.22, 0.16), UV_TIMBER_TILE, bevel=0.02)
    m.box((mx, 0, 0.08), (0.22, 0.68, 0.16), UV_TIMBER_TILE, bevel=0.02)
    m.box((mx, 0, 0.78), (0.19, 0.19, 1.48), UV_TIMBER_TILE, bevel=0.02)
    for tier in range(5):
        tz0 = 0.48 + tier * 0.165
        m.tube((mx, 0, tz0), (mx, 0, tz0 + 0.158), 0.138, 0.136, UV_STRAW_TILE, segs=16)
        m.torus((mx, 0, tz0 + 0.158), 0.135, 0.012, UV_ROPE, n_maj=16, n_min=6)
    for rz in (0.50, 0.54, 0.58, 1.24, 1.28, 1.32):
        m.torus((mx, 0, rz), 0.144, 0.018, UV_CRIMSON, n_maj=16, n_min=6)
    m.add_collider((0, 0, 0.75), (1.55, 1.15, 1.5))
    m.xf = old
