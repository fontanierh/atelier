"""Deterministic coastal instance placement data; never creates or exports mesh geometry."""
import math
import random
from brinecove import layout as L


class Poisson:
    """Grid-hashed dart throwing: one placement per disc, so the canopy closes without stacked trunks."""

    def __init__(self, cell=8.0):
        self.cell = cell
        self.grid = {}

    def fits(self, x, y, r):
        c = self.cell
        gx, gy = int(math.floor(x / c)), int(math.floor(y / c))
        span = int(math.ceil((r + 9.0) / c))
        for i in range(gx - span, gx + span + 1):
            for j in range(gy - span, gy + span + 1):
                for ox, oy, orad in self.grid.get((i, j), ()):
                    if (ox - x) ** 2 + (oy - y) ** 2 < (min(r, orad) * 0.5 + max(r, orad) * 0.5) ** 2:
                        return False
        return True

    def add(self, x, y, r):
        key = (int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))
        self.grid.setdefault(key, []).append((x, y, r))


def _ridge(x, y):
    """The forested ridge behind the town, outside the playable basin but in every harbor view."""
    return L.Y_MAX - 5 < y < 760 and abs(x) < 900 and L.plantable(x, y) and L.ground(x, y) > 6.0 \
        and L.slope(x, y) < 1.7


def scatter(seed=8807):
    """Placements as (prototype, x, y, z, yaw degrees, scale)."""
    from brinecove.landmarks import footprint
    rng = random.Random(seed)
    out = []
    discs = Poisson()
    broad = [f'broad_{i}' for i in range(8)]
    emergent = [f'emergent_{i}' for i in range(3)]
    small = [f'small_{i}' for i in range(3)]
    palms = [f'palm_{i}' for i in range(6)]
    shrubs = [f'shrub_{i}' for i in range(5)]

    def place(proto, x, y, scale, spacing, sink=0.0):
        if footprint(x, y, spacing * 0.5 + 1.0):
            return False  # the fort, its ramp, the shipyard and the hill stair stay clear
        if not discs.fits(x, y, spacing):
            return False
        discs.add(x, y, spacing)
        out.append((proto, x, y, L.ground(x, y) - sink, rng.uniform(0, 360), scale))
        return True

    # Headland and ridge canopy: emergents first, then the closing hardwood layer, then palms in the gaps and
    # along the sunny cliff lip where the paintings show them.
    for _ in range(9000):
        x = rng.choice((-1, 1)) * rng.uniform(425, 815)
        y = rng.uniform(-250, 520)
        if L.headland_plantable(x, y) and L.slope(x, y) < 1.2:
            place(rng.choice(emergent), x, y, rng.uniform(0.9, 1.15), 14.0, 0.6)
    for _ in range(60000):
        x = rng.choice((-1, 1)) * rng.uniform(425, 815)
        y = rng.uniform(-250, 520)
        if not L.headland_plantable(x, y):
            continue
        lip = abs(x) - L.bay_half(y) < 70 and y < L.QUAY_Y + 40
        if lip and rng.random() < 0.38:
            place(rng.choice(palms), x, y, rng.uniform(0.85, 1.25), 3.6)
        else:
            place(rng.choice(broad), x, y, rng.uniform(0.85, 1.2), 8.6, 0.5)
    for _ in range(40000):
        x = rng.uniform(-900, 900)
        y = rng.uniform(L.Y_MAX - 5, 760)
        if _ridge(x, y):
            proto = rng.choice(emergent) if rng.random() < 0.12 else rng.choice(broad)
            place(proto, x, y, rng.uniform(0.95, 1.3), 9.6, 0.5)
    # The town keeps its palms and a few shade trees in yards, terraces and street ends.
    for _ in range(26000):
        x = rng.uniform(-420, 420)
        y = rng.uniform(L.QUAY_Y + 6, L.Y_MAX - 5)
        if not L.plantable(x, y) or L.ground(x, y) < 2.0:
            continue
        r = rng.random()
        if r < 0.30:
            place(rng.choice(palms), x, y, rng.uniform(0.8, 1.2), 4.0)
        elif r < 0.62:
            place(rng.choice(small), x, y, rng.uniform(0.8, 1.2), 5.0, 0.3)
        elif r < 0.80 and y > 250:
            place(rng.choice(broad), x, y, rng.uniform(0.7, 0.95), 7.0, 0.4)
        else:
            place(rng.choice(shrubs), x, y, rng.uniform(0.8, 1.2), 2.2)
    # Understory: shrubs fill what the crowns leave, ferns and bananas live in the generic vegetation mesh.
    for _ in range(30000):
        x = rng.choice((-1, 1)) * rng.uniform(425, 815)
        y = rng.uniform(-250, 520)
        if L.headland_plantable(x, y):
            place(rng.choice(shrubs), x, y, rng.uniform(0.9, 1.5), 2.6)
    return out


COVER_LIMIT = 300000  # bounded instance memory and runtime.json; the 50 m cull keeps the drawn count low


def groundcover(ground=None, seed=8811):
    """Groundcover placements (prototype, x, y, z, yaw, scale): natural clumps of fern, broadleaf and grass on the
    planted slopes, never on sand, cliffs, streets or water.

    Each clump is one family, packed and largest at its heart and thinning to its rim, from a palm-sized tuft to a
    bed several metres across; clumps gather in noise drifts and crowd the feet of rock faces, with bare soil between.
    Single plants on an even disc spacing read as a grid of tufts on brown soil (2026-10-19 capture review).
    ground is the game's final ground (build.py passes the collar-eased one). The count is capped at COVER_LIMIT;
    build.py culls the instances at 50 m and the prototypes carry generated LODs."""
    from brinecove.rocks import fbm, uphill
    from brinecove.landmarks import footprint
    import brinecove.region as R
    ground = ground or L.ground
    rng = random.Random(seed)
    out, discs = [], Poisson(cell=4.0)
    x0, y0, x1, y1 = R.OUTER

    def spot(x, y):
        """The ground height if a plant may grow at (x, y), else None."""
        if not (x0 + 2 <= x <= x1 - 2 and y0 + 2 <= y <= y1 - 2):
            return None
        inside = abs(x) <= 880 and L.Y_MIN - 30 <= y <= L.Y_MAX + 250
        if inside and not L.plantable(x, y):
            return None
        z = ground(x, y)
        if z < 2.6 or L.in_gorge(x, y, 5.0) or footprint(x, y, 0.5) or uphill(x, y, 3.0)[2] > 0.95:
            return None
        return z

    # Clump centres on a jittered grid, so no walkable spot is left bare by the luck of the draw; whole clumps are
    # thinned evenly if the total would pass the cap (random draws until the cap left the note 1 meadow empty).
    clumps = []
    cell = 6.0
    gx = x0 + 2
    while gx < x1 - 2:
        gy = y0 + 2
        while gy < y1 - 2:
            cx, cy = gx + rng.uniform(0, cell), gy + rng.uniform(0, cell)
            gy += cell
            drift = fbm(cx, cy, 22.0, 3, 61)
            if drift < 0.3 or spot(cx, cy) is None:
                continue
            # The foot of a rock face (steep ground just uphill) gathers the biggest, densest beds; walkable flats
            # and open slopes keep nearly every clump (the slopes' scrub is culled further out, build.py).
            ux, uy, grad = uphill(cx, cy, 3.0)
            foot = uphill(cx + ux * 5.0, cy + uy * 5.0, 3.0)[2] > 0.95
            if not foot and rng.random() > (1.0 if grad < 0.4 else 0.9):
                continue
            clumps.append((cx, cy, drift, foot, rng.random(), grad >= 0.4 and not foot))
        gx += cell
    clumps.sort(key=lambda c: c[4])
    for cx, cy, drift, foot, _, slope in clumps:
        if len(out) >= COVER_LIMIT:
            break
        # Open slopes are seen from the beach and the paths below at 20-40 m, where palm-sized tufts read as specks
        # (notes 5 and 6, second review): their clumps are low coastal scrub, ferns and broadleaf about twice the
        # size, spaced to match.
        big = 1.9 if slope else 1.0
        size = rng.uniform(1.4, 4.2) * (1.3 if foot or slope else 1.0) * (0.8 + 0.5 * drift)
        wet = fbm(cx, cy, 60.0, 2, 67)
        family = 'cover_fern' if wet > 0.55 else ('cover_leaf' if wet > 0.42 else 'cover_grass')
        if foot and rng.random() < 0.5 or slope and family == 'cover_grass' and rng.random() < 0.7:
            family = 'cover_fern' if wet > 0.48 else 'cover_leaf'
        # Their hearts are low shrubs, knee to waist high, so the slope reads as coastal scrub, not a leaf print.
        if slope and len(out) < COVER_LIMIT:
            for _ in range(rng.choice((1, 1, 2, 3))):
                a, r = rng.uniform(0, math.tau), rng.uniform(0.0, size * 0.45)
                x, y = cx + r * math.cos(a), cy + r * math.sin(a)
                z = spot(x, y)
                if z is None or not discs.fits(x, y, 1.4):
                    continue
                discs.add(x, y, 1.4)
                out.append((f'shrub_{rng.choice((0, 1, 2, 4))}', x, y, z - 0.25, rng.uniform(0, 360),
                            rng.uniform(0.38, 0.6)))
        for _ in range(int(rng.uniform(8, 24) * (1.4 if foot else 1.6 if slope else 1.0))):
            r = size * math.sqrt(rng.random())
            a = rng.uniform(0, math.tau)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            spacing = (0.45 + 0.35 * r / size) * big
            if not discs.fits(x, y, spacing):
                continue
            z = spot(x, y)
            if z is None:
                continue
            discs.add(x, y, spacing)
            kind = family if rng.random() < 0.85 else rng.choice(('cover_fern', 'cover_leaf', 'cover_grass'))
            out.append((f'{kind}_{rng.randrange(3)}', x, y, z - 0.05, rng.uniform(0, 360),
                        rng.uniform(0.75, 1.1) * (1.35 - 0.55 * r / size) * big))
    return out


def bloom_spots(rng):
    """Flowering mounds along the market edge, the stair and the upper lane."""
    spots = []
    for _ in range(4000):
        x = rng.uniform(-400, 400)
        y = rng.uniform(L.QUAY_Y + 8, 400)
        if L.plantable(x, y) and (L.in_lot(x, y, 6.0) or L.on_street(x, y, 5.0) or L.on_market(x, y, 8.0)):
            spots.append((rng.choice(('bloom_0', 'bloom_1')), x, y, L.ground(x, y), rng.uniform(0, 360),
                          rng.uniform(0.8, 1.3)))
            if len(spots) >= 260:
                break
    return spots
