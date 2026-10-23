"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.procedural._falls_zone import _falls_zone


def falls_cliff(x, y, z):
    """The sea cliff that frames the waterfall, below the ledge shelf: its jagged 4 m ground cells stood out of the
    rock outcrops as flat meadow-green triangles (note 9 second review), so they take the rock layer alone."""
    x0, x1, top = _falls_zone()
    return x0 <= x <= x1 and abs(y - L.GORGE_Y) < 75.0 and z < top
