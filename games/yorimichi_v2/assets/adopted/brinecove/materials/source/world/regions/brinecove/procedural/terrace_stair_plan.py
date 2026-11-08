"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.procedural.geometry_policy import NOSING_LIFT
from brinecove.procedural.geometry_policy import STAIR_FLIGHT
from brinecove.procedural.geometry_policy import STAIR_FOOT_Y
from brinecove.procedural.geometry_policy import STAIR_LANDING
from brinecove.procedural.geometry_policy import STAIR_RISE_MAX
from brinecove.procedural.geometry_policy import STAIR_TOP_Y
from brinecove.procedural.stair_apron import stair_apron
import functools
import math


@functools.lru_cache(maxsize=None)
def terrace_stair_plan(x):
    """@cc [owner:fontanierh,label:correctness] terrace-stair-climbable
    The quay-to-terrace stair at x, bottom to top: (foot z, [(y0, y1, top z)]) of abutting treads and landings.
    The foot z is the top of the stair's level apron (stair_apron), which clears every emitted street slab under it.
    Every riser as built, nosing included, MUST be at most STAIR_RISE_MAX, well under the pawn's 0.45 m step: the
    first from the apron, every one between treads and the last onto the terrace paving. Treads and landings MUST
    abut in y with no gap, and the last riser MUST land flush on the terrace paving at STAIR_TOP_Y.
    """
    # Playtest note 410-1/2: the r10 stair climbed 25.5 m in 24 one-metre risers on floating 0.8 m slabs, so the pawn
    # could not climb it, daylight showed under every nosing and the terrace paving walled off its top four treads.
    # The street slabs at the foot follow the ground slab by slab (up to 6 cm apart), so the stair starts from an
    # apron above them rather than from the ground under its first riser.
    z0 = stair_apron(x)[4]
    z1 = L.UPPER_Z + 0.22                           # the terrace paving top
    n = math.ceil((z1 - z0) / (STAIR_RISE_MAX - NOSING_LIFT))
    flights = math.ceil(n / STAIR_FLIGHT)
    rise = (z1 - z0) / n
    tread = (STAIR_TOP_Y - STAIR_FOOT_Y - (flights - 1) * STAIR_LANDING) / (n - flights)
    sizes = [n // flights + (1 if i < n % flights else 0) for i in range(flights)]
    steps, y, k = [], STAIR_FOOT_Y, 0
    for f, m in enumerate(sizes):
        for _ in range(m - 1):
            k += 1
            steps.append((y, y + tread, z0 + rise * k))
            y += tread
        k += 1
        if f < flights - 1:
            steps.append((y, y + STAIR_LANDING, z0 + rise * k))
            y += STAIR_LANDING
    return z0, steps
