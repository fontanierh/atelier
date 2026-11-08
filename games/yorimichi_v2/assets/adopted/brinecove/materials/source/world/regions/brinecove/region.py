"""Where Brinecove sits in Yorimichi and how its ground meets the far hills.

Layout coordinates are local metres with the cove's centre line at x = 0 and the quay at y = 60. World metres follow
docs/WORLD_MAP.md (x east, y north, z up): world = local + ORIGIN, with no rotation. The cove opens south onto open
sea west of Momiji Coast.

The region owns the ground inside OUTER_WORLD, a rectangle on the FarHills 96-knot axis, so FarHills hides exactly
the cells inside it (farhills_surface.owns_fine_ground). Inside INNER the ground is the layout's; between INNER and
OUTER a collar eases it into the far hills and ends on FarHills' own hole-boundary vertices.
Pure Python: farhills_surface, the map and the tests import it without Blender.
"""
import math

ORIGIN = (-1500.0, -120.0, 0.0)
_KNOT = 6400.0 / 95.0  # FarHills axis step: np.linspace(-3200, 3200, 96)


def _knot(k):
    return -3200.0 + _KNOT * k


# The FarHills hole, world metres (x0, y0, x1, y1): knots 10..37 east-west, 32..56 south-north.
OUTER_WORLD = (_knot(10), _knot(32), _knot(37), _knot(56))
# The layout's own ground, local metres (x0, y0, x1, y1).
INNER = (-900.0, -780.0, 700.0, 600.0)
OUTER = (OUTER_WORLD[0] - ORIGIN[0], OUTER_WORLD[1] - ORIGIN[1], OUTER_WORLD[2] - ORIGIN[0], OUTER_WORLD[3] - ORIGIN[1])
# Teleport stop on the quay, world metres.
QUAY_STOP = (-1500.0, -45.0)


def to_world(x, y, z=0.0):
    return x + ORIGIN[0], y + ORIGIN[1], z + ORIGIN[2]


def to_local(x, y, z=0.0):
    return x - ORIGIN[0], y - ORIGIN[1], z - ORIGIN[2]


def owns(x, y):
    """True where Brinecove supplies the ground (world metres, strictly inside OUTER_WORLD)."""
    x0, y0, x1, y1 = OUTER_WORLD
    return x0 < x < x1 and y0 < y < y1


def collar_weight(x, y):
    """0 inside INNER, 1 on OUTER's edge (local metres): how much of the far hills a collar point takes."""
    ix0, iy0, ix1, iy1 = INNER
    ox0, oy0, ox1, oy1 = OUTER
    s = max(0.0, (ix0 - x) / (ix0 - ox0), (x - ix1) / (ox1 - ix1), (iy0 - y) / (iy0 - oy0), (y - iy1) / (oy1 - iy1))
    s = min(1.0, s)
    return s * s * (3.0 - 2.0 * s)


class Rim:
    """FarHills' hole boundary, local metres: per side, the boundary vertices sorted along the side.

    Built from the FarHills final product (rim_from_mesh), so the collar ends on exactly the vertices the far hills
    already have. height(x, y) projects a collar point onto the nearest sides and blends their profiles.
    """

    def __init__(self, sides):
        # sides: {'south'|'north': [(x, z)...] sorted by x, 'west'|'east': [(y, z)...] sorted by y}
        self.sides = {k: sorted(v) for k, v in sides.items()}

    def profile(self, side, t):
        pts = self.sides[side]
        if t <= pts[0][0]:
            return pts[0][1]
        if t >= pts[-1][0]:
            return pts[-1][1]
        lo, hi = 0, len(pts) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if pts[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        (t0, z0), (t1, z1) = pts[lo], pts[hi]
        return z0 + (z1 - z0) * (t - t0) / max(1e-9, t1 - t0)

    def height(self, x, y):
        ix0, iy0, ix1, iy1 = INNER
        ox0, oy0, ox1, oy1 = OUTER
        reach = {'west': (ix0 - x) / (ix0 - ox0), 'east': (x - ix1) / (ox1 - ix1),
                 'south': (iy0 - y) / (iy0 - oy0), 'north': (y - iy1) / (oy1 - iy1)}
        total, weight = 0.0, 0.0
        for side, s in reach.items():
            w = max(1e-6, s) ** 4
            z = self.profile(side, y if side in ('west', 'east') else x)
            total += w * z
            weight += w
        return total / weight


def rim_from_mesh(vertices, triangles, tolerance=0.05):
    """The FarHills hole boundary (Rim) from its final mesh: world-metre vertices and triangle indices.

    A boundary edge belongs to exactly one triangle; the ones on OUTER_WORLD's sides form the hole's rim.
    """
    x0, y0, x1, y1 = OUTER_WORLD
    count = {}
    for a, b, c in triangles:
        for e in ((a, b), (b, c), (c, a)):
            key = (min(e), max(e))
            count[key] = count.get(key, 0) + 1
    on = {}
    for (a, b), n in count.items():
        if n != 1:
            continue
        for side, axis, value in (('west', 0, x0), ('east', 0, x1), ('south', 1, y0), ('north', 1, y1)):
            pa, pb = vertices[a], vertices[b]
            if abs(pa[axis] - value) < tolerance and abs(pb[axis] - value) < tolerance:
                lo, hi = (y0, y1) if axis == 0 else (x0, x1)
                along = 1 - axis
                if lo - tolerance <= pa[along] <= hi + tolerance and lo - tolerance <= pb[along] <= hi + tolerance:
                    on.setdefault(side, set()).update((a, b))
    sides = {}
    for side, ids in on.items():
        along = 1 if side in ('west', 'east') else 0
        offset = ORIGIN[along]
        sides[side] = [(float(vertices[i][along]) - offset, float(vertices[i][2])) for i in ids]
        sides[side + '_world'] = [tuple(float(c) for c in vertices[i]) for i in ids]
    missing = {'west', 'east', 'south', 'north'} - set(on)
    if missing:
        raise ValueError(f'FarHills has no hole edge along {sorted(missing)}: is owns_fine_ground hiding Brinecove?')
    return Rim({k: v for k, v in sides.items() if not k.endswith('_world')}), \
        {k[:-6]: sorted(v, key=lambda p: p[1] if k.startswith(('west', 'east')) else p[0])
         for k, v in sides.items() if k.endswith('_world')}


def ground(height_fn, rim, x, y):
    """Game ground (local metres): the layout inside INNER, eased into the rim across the collar."""
    w = collar_weight(x, y)
    if w <= 0.0:
        return height_fn(x, y)
    if w >= 1.0:
        return rim.height(x, y)
    return height_fn(x, y) * (1.0 - w) + rim.height(x, y) * w


def area_m2():
    x0, y0, x1, y1 = OUTER_WORLD
    return (x1 - x0) * (y1 - y0)


def distance_to_outer(x, y):
    """Metres from a local point inside OUTER to its nearest edge."""
    ox0, oy0, ox1, oy1 = OUTER
    return min(x - ox0, ox1 - x, y - oy0, oy1 - y)


assert math.isclose(OUTER_WORLD[0], -2526.3157894736842) and math.isclose(OUTER_WORLD[3], 572.6315789473683)
