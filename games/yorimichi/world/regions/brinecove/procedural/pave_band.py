"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.kit import bush
from brinecove.procedural.geometry_policy import MARKET_FLOOR
from brinecove.procedural.paving import paving
from brinecove.procedural.random_state import RNG


def pave_band(b, y0, y1, skip_market=True):
    """Pave a street band in terrain-following slabs with kerbs, leaving the market open."""
    paving(b, -372.0, 372.0, y0, y1, seed=int(y0),
           skip=MARKET_FLOOR if skip_market else None)
    # Planters and laundry break up the paved bands and tie them to the walls.
    for px in range(-350, 351, 44):
        if skip_market and -112 < px < 112 and y0 < 228.0:
            continue
        pz = L.ground(px, y0 + 2.2)
        b.box((px, y0 + 2.2, pz + 0.38), (3.8, 1.1, 0.75), 'stone_light')
        bush(b, px, y0 + 2.2, pz + 0.75, 0.0, 0.85, RNG)
    for lx in range(-330, 331, 92):
        if skip_market and -118 < lx < 118 and y0 < 228.0:
            continue
        ly = y0 + 4.0
        lz = L.ground(lx, ly)
        b.beam((lx, ly, lz), (lx, ly, lz + 5.4), 0.12, 'wood_dark')
        b.beam((lx + 24, ly + 5.0, lz), (lx + 24, ly + 5.0, lz + 5.4), 0.12, 'wood_dark')
        b.rope((lx, ly, lz + 5.0), (lx + 24, ly + 5.0, lz + 5.0), 0.5, 0.03)
        for k in range(3):
            qx = lx + 4 + k * 6.4
            b.panel((qx, ly + k * 1.25, lz + 4.95), (qx + 4.6, ly + k * 1.25, lz + 4.95),
                    (qx + 4.6, ly + k * 1.25, lz + 2.8), (qx, ly + k * 1.25, lz + 2.8),
                    ('canvas', 'canvas_red', 'canvas_teal')[k], thick=0.04)
