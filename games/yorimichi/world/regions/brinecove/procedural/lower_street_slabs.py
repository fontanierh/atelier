"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.procedural.covered import covered
from brinecove.procedural.geometry_policy import LOWER_BANDS
from brinecove.procedural.geometry_policy import LOWER_ROADS
from brinecove.procedural.geometry_policy import MARKET_FLOOR
from brinecove.procedural.geometry_policy import _STREET_SLABS
from brinecove.procedural.paving_grid import paving_grid


def lower_street_slabs():
    """Every terrain-following slab lower_town() lays, as (x0, x1, y0, y1, top): the same grid and skip as paving()."""
    if not _STREET_SLABS:
        rects = [(x - w / 2, x + w / 2, y - d / 2, y + d / 2, None) for x, y, w, d in LOWER_ROADS]
        rects += [(-372.0, 372.0, y0, y1, MARKET_FLOOR) for y0, y1 in LOWER_BANDS]
        for x0, x1, y0, y1, skip in rects:
            nx, ny, sx, sy = paving_grid(x0, x1, y0, y1)
            for i in range(nx):
                cx = x0 + (i + 0.5) * sx
                for j in range(ny):
                    cy = y0 + (j + 0.5) * sy
                    if not covered(skip, cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2):
                        _STREET_SLABS.append((cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, L.ground(cx, cy) + 0.16))
    return _STREET_SLABS
