"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.procedural.geometry_policy import APRON_LIFT
from brinecove.procedural.geometry_policy import STAIR_APRON
from brinecove.procedural.geometry_policy import STAIR_FOOT_Y
from brinecove.procedural.geometry_policy import TERRACE_CHEEKS
from brinecove.procedural.geometry_policy import TERRACE_STAIRS
from brinecove.procedural.lower_street_slabs import lower_street_slabs


def stair_apron(x):
    """The level foot apron in front of the stair at x: (x0, x1, y0, y1, top). Its top clears every street slab
    under it, so the street's slab-by-slab heights never reach the first riser."""
    width = dict(TERRACE_STAIRS)[x]; cheek = TERRACE_CHEEKS[x]
    x0, x1, y0, y1 = x - width / 2 - cheek, x + width / 2 + cheek, STAIR_FOOT_Y - STAIR_APRON, STAIR_FOOT_Y
    under = [top for a, b, c, d, top in lower_street_slabs() if a < x1 and b > x0 and c < y1 and d > y0]
    return x0, x1, y0, y1, max(under + [L.ground(x, STAIR_FOOT_Y) + 0.16]) + APRON_LIFT
