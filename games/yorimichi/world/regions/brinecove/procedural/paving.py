"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.procedural.covered import covered
from brinecove.procedural.geometry_policy import FLAT_PAVING
from brinecove.procedural.paving_grid import paving_grid
from brinecove.procedural.paving_material import paving_material


def paving(b, x0, x1, y0, y1, z=None, tile=6.5, thick=0.22, kerbs=(True, True), seed=0, skip=None):
    """Tile a street rectangle in abutting slabs; z=None follows the ground per slab. Kerbs line the y edges.
    skip is a floor (x0, x1, y0, y1) laid by another module: only slabs and kerbs wholly under it are left out, so
    the street still meets that floor's edge instead of leaving bare ground beside it."""
    if z is not None and skip is None:
        FLAT_PAVING.append((min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), z - thick))
    nx, ny, sx, sy = paving_grid(x0, x1, y0, y1, tile)
    for i in range(nx):
        cx = x0 + (i + 0.5) * sx
        for j in range(ny):
            cy = y0 + (j + 0.5) * sy
            if covered(skip, cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2):
                continue
            top = L.ground(cx, cy) + 0.16 if z is None else z
            b.box((cx, cy, top - thick / 2), (sx, sy, thick), paving_material(cx, cy, seed))
        for edge, on in zip((y0 + 0.25, y1 - 0.25), kerbs):
            if on and not covered(skip, cx - sx / 2, cx + sx / 2, edge - 0.85, edge + 0.85):
                top = L.ground(cx, edge) + 0.16 if z is None else z
                b.box((cx, edge, top + 0.06), (sx, 0.5, 0.36), 'stone_light')
                # A dark gutter of upright setts just inside the kerb.
                gy = edge + (0.6 if edge < (y0 + y1) / 2 else -0.6)
                b.box((cx, gy, top), (sx, 0.7, 0.06), 'cobble_dark')
