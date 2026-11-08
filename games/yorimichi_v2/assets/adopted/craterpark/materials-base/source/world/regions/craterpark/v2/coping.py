"""Steel coping (plan/pipeline.md 5.5): one closed tube per lip, swept along the lip's own samples (the transition's top
row), so it follows the exact outline continuously, never stepped. Parallel-transport frames, 12 sides, a closed
loop meeting itself, flat end discs on an open lip.

Placement: its top stands PROUD over the deck, and its front stands REVEAL past the wall face into the transition.
The tube is partly inside the solid it sits on. This is the documented render-only exception to review point 1: the
coping is drawn and never collides (dsl.COLLISION_ROLE has no 'coping'), and the grind comes from its rail.
"""
import numpy as np

from . import dsl, solids
from .rails import resample

RADIUS = .035       # metres (7 cm across, as r4's COPING_RADIUS)
PROUD = .012        # metres its top stands over the deck (r4's COPING_PROUD)
REVEAL = .012       # metres its front stands past the wall face
SIDES = 12
INSET = .01         # metres an open tube's ends stop short of its lip's ends


def axis(lip, into, radius=RADIUS, proud=PROUD, reveal=REVEAL):
    """The tube's axis under the lip points (k, 3): `into` (k, 3) is the horizontal unit direction from the deck into
    the transition."""
    lip = np.asarray(lip, 'f8'); into = np.asarray(into, 'f8')
    return lip + np.array([0., proud - radius, 0.]) + (reveal - radius) * into


def coping(lip, into, *, closed=False, feature='coping', radius=RADIUS, proud=PROUD, reveal=REVEAL, sides=SIDES):
    """(mesh, rail): the coping tube along the lip points (k, 3) and its grind line, the tube's top every 0.5 m."""
    a = axis(lip, into, radius, proud, reveal)
    if closed and np.linalg.norm(a[0] - a[-1]) < 1e-9:
        a = a[:-1]
    if not closed:                               # end discs clear of the flank faces the lip ends on (no flicker)
        for end, nxt in ((0, 1), (-1, -2)):
            d = a[nxt] - a[end]; L = np.linalg.norm(d)
            a[end] = a[end] + d / L * min(INSET, L / 3)
    mesh = solids.tube(a, radius, feature=feature, sides=sides, closed=closed, tag='coping')
    top = a + np.array([0., radius, 0.])
    return mesh, dsl.Rail(resample(top, closed=closed), closed, feature)
