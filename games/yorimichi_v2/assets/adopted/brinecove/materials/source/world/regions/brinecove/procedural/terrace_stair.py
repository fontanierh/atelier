"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import landmarks as LM
from brinecove.procedural.geometry_policy import NOSING_LIFT
from brinecove.procedural.geometry_policy import STAIR_FOOT_Y
from brinecove.procedural.geometry_policy import STAIR_LANDING
from brinecove.procedural.stair_apron import stair_apron
from brinecove.procedural.terrace_stair_plan import terrace_stair_plan


def terrace_stair(b, x, width, cheek):
    """Solid masonry treads from the quay up to the terrace with landings between flights, a pale nosing on each
    tread, and a coped parapet on each side that climbs with the flights."""
    z0, steps = terrace_stair_plan(x)
    base = z0 - 0.6
    hw = width / 2
    # The foot apron: one level slab over the street's slabs, its top the stair's foot.
    ax0, ax1, ay0, ay1, _ = stair_apron(x)
    b.box(((ax0 + ax1) / 2, (ay0 + ay1) / 2, z0 - 0.15), (ax1 - ax0, ay1 - ay0, 0.3), 'stone_light')
    for y0, y1, top in steps:
        b.box((x, (y0 + y1) / 2, (top + base) / 2), (width, y1 - y0, top - base), 'stone_light')
        # The nosing stands 2 cm proud of the riser and 1 cm in from each side, so none of its faces is coplanar
        # with the tread's (coplanar faces z-fought into streaks along every step edge).
        b.box((x, y0 + 0.05, top + NOSING_LIFT - 0.04), (width - 0.02, 0.14, 0.08), 'stone')
    # Parapets: one sloped block per flight over its nosing line, a flat one per landing, each coped.
    runs, cur = [], []
    for y0, y1, top in steps:
        if y1 - y0 > STAIR_LANDING - 1e-6:
            if cur:
                runs.append(('flight', cur))
            runs.append(('landing', [(y0, y1, top)]))
            cur = []
        else:
            cur.append((y0, y1, top))
    if cur:
        runs.append(('flight', cur))
    for side in (-1, 1):
        xa, xb = sorted((x + side * hw, x + side * (hw + cheek)))
        for _, run in runs:
            ya, yb = run[0][0], run[-1][1]
            ta, tb = run[0][2] + 0.95, run[-1][2] + 0.95
            LM._block(b, [(xa, ya, base), (xb, ya, base), (xb, yb, base), (xa, yb, base)],
                      [(xa, ya, ta), (xb, ya, ta), (xb, yb, tb), (xa, yb, tb)], 'stone')
            LM._block(b, [(xa - 0.05, ya, ta), (xb + 0.05, ya, ta), (xb + 0.05, yb, tb), (xa - 0.05, yb, tb)],
                      [(xa - 0.05, ya, ta + 0.15), (xb + 0.05, ya, ta + 0.15), (xb + 0.05, yb, tb + 0.15),
                       (xa - 0.05, yb, tb + 0.15)], 'stone_light')
        # A newel at the foot.
        b.box(((xa + xb) / 2, STAIR_FOOT_Y + 0.4, (base + steps[0][2] + 1.3) / 2), (xb - xa + 0.2, 0.8,
              steps[0][2] + 1.3 - base), 'stone_light')
