"""Instanced Brinecove foliage: a small library of leaf-card trees, palms and shrubs, scattered thousands of times.

The concept paintings close the headlands and the ridge behind the town with one continuous, rounded canopy. Baking
that many cards into the vegetation mesh would cost tens of millions of triangles, so each species is built once as a
prototype and placed as linked instances (EXT_mesh_gpu_instancing in the viewer). Card normals point away from the
crown centre, as on Hidamari's trees, so a crown shades as one soft mass with lit tops and darker undersides.

Plain Python: the scatter and the triangle budget can be checked without Blender.
"""
import math
import random
from foliage_roles import SurfaceKey

from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.kit import LEAF_CELLS, PALM_CELLS, cell_uvs

TAU = math.pi * 2

# Canopy mixes, as (material, weight) for the outer shell. Interiors are always leaf_deep.
PALETTES = {
    'green': (('leaf_mid', 5), ('leaf_light', 3), ('leaf_sun', 2), ('leaf_warm', 0.5)),
    'olive': (('leaf_mid', 3), ('leaf_sun', 3), ('leaf_warm', 2), ('leaf_gold', 0.8)),
    'autumn': (('leaf_rust', 4), ('leaf_gold', 2), ('leaf_warm', 2), ('leaf_mid', 1.5)),
    'gold': (('leaf_gold', 4), ('leaf_sun', 3), ('leaf_warm', 1.5), ('leaf_mid', 1)),
}


def _pick(rng, palette):
    total = sum(w for _, w in palette)
    r = rng.uniform(0, total)
    for mat, w in palette:
        r -= w
        if r <= 0:
            return mat
    return palette[-1][0]


def _canopy(b, centre, radii, count, size, rng, palette, normal_from, lift):
    """Leaf cards in an ellipsoid, denser on the shell; normals from the whole crown's centre."""
    cx, cy, cz = centre
    rx, ry, rz = radii
    for _ in range(count):
        while True:
            p = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1))
            length = math.sqrt(p[0] * p[0] + p[1] * p[1] + p[2] * p[2])
            if length <= 1.0:
                break
        if length < 0.6 and rng.random() < 0.55:
            k = rng.uniform(0.65, 1.0) / max(length, 1e-3)
            p = (p[0] * k, p[1] * k, p[2] * k)
            length = 1.0
        pos = (cx + p[0] * rx, cy + p[1] * ry, cz + p[2] * rz)
        facing = (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.6, 1))
        if length < 0.5:
            mat = 'leaf_deep'
        elif p[2] < -0.45 and rng.random() < 0.6:
            mat = 'leaf_deep' if rng.random() < 0.5 else 'leaf_mid'
        else:
            mat = _pick(rng, palette)
        w = size * rng.uniform(0.8, 1.2)
        b.card(pos, facing, w, w * rng.uniform(0.85, 1.05), mat, cell_uvs(rng.randrange(len(LEAF_CELLS))),
               normal_from=normal_from, lift=lift)


def broadleaf(seed, height, spread, palette, cards=900, card=1.5, form='round'):
    """A tropical hardwood: short trunk, a few leaders, and a broad crown of overlapping lobes."""
    rng = random.Random(seed)
    b = Builder(f'tree_{seed}')
    pal = PALETTES[palette]
    lean = (rng.uniform(-0.06, 0.06) * height, rng.uniform(-0.06, 0.06) * height)
    fork_z = height * (0.34 if form == 'round' else 0.48)
    fork = (lean[0] * 0.4, lean[1] * 0.4, fork_z)
    trunk_r = 0.035 * height + 0.12
    b.cylinder((0, 0, -0.6), (fork[0] * 0.5, fork[1] * 0.5, fork_z * 0.55), trunk_r, 'wood_dark', 8,
               radius_b=trunk_r * 0.82, caps=False)
    b.cylinder((fork[0] * 0.5, fork[1] * 0.5, fork_z * 0.55), fork, trunk_r * 0.82, 'wood_dark', 7,
               radius_b=trunk_r * 0.62, caps=False)
    # Buttress roots for the big trees.
    if height > 11:
        for i in range(4):
            a = rng.uniform(0, TAU)
            b.beam((0, 0, 0.9), (math.cos(a) * trunk_r * 3.2, math.sin(a) * trunk_r * 3.2, -0.2),
                   trunk_r * 0.5, 'wood_dark', depth=trunk_r * 0.25)
    lobes = []
    crown_z = height * (0.70 if form == 'round' else 0.74)
    depth = height * (0.17 if form == 'round' else 0.13)
    lobes.append(((lean[0], lean[1], height - depth * 0.9), (spread * 0.30, spread * 0.30, depth)))
    ring = 6 if form == 'round' else 5
    for i in range(ring):
        a = i * TAU / ring + rng.uniform(-0.3, 0.3)
        reach = spread * rng.uniform(0.26, 0.33)
        c = (lean[0] + math.cos(a) * reach, lean[1] + math.sin(a) * reach,
             crown_z + rng.uniform(-0.08, 0.06) * height)
        r = spread * rng.uniform(0.2, 0.26)
        lobes.append((c, (r, r, depth * rng.uniform(0.85, 1.1))))
    if form == 'tiered':
        # Emergent rainforest trees carry a second, smaller tier below the crown.
        for i in range(3):
            a = i * TAU / 3 + 0.5
            c = (lean[0] * 0.7 + math.cos(a) * spread * 0.22, lean[1] * 0.7 + math.sin(a) * spread * 0.22,
                 height * 0.5)
            lobes.append((c, (spread * 0.16, spread * 0.16, depth * 0.6)))
    for c, _ in lobes:
        end = (fork[0] + (c[0] - fork[0]) * 0.75, fork[1] + (c[1] - fork[1]) * 0.75,
               fork[2] + (c[2] - fork[2]) * 0.75)
        b.cylinder(fork, end, trunk_r * 0.42, 'wood_dark', 6, radius_b=trunk_r * 0.14, caps=False)
    normal_from = (lean[0], lean[1], height * 0.55)
    volumes = [r[0] * r[1] * r[2] for _, r in lobes]
    total = sum(volumes)
    for (c, r), v in zip(lobes, volumes):
        _canopy(b, c, r, max(12, round(cards * v / total)), card, rng, pal, normal_from, 0.35 * spread)
    return b


def palm(seed, height, fronds=15):
    """A coconut palm: a curved ringed trunk and drooping frond strips with real width and a fold."""
    rng = random.Random(seed)
    b = Builder(f'palm_{seed}')
    lean_dir = rng.uniform(0, TAU)
    lean = height * rng.uniform(0.06, 0.2)
    segs = 9
    pts = []
    for i in range(segs + 1):
        t = i / segs
        bend = lean * t ** 1.8
        pts.append((math.cos(lean_dir) * bend, math.sin(lean_dir) * bend, height * t - 0.4 * (1 - t)))
    for i in range(segs):
        r0 = 0.30 - 0.11 * (i / segs)
        r1 = 0.30 - 0.11 * ((i + 1) / segs)
        b.cylinder(pts[i], pts[i + 1], r0 * height / 10, 'palm_trunk', 7, radius_b=r1 * height / 10, caps=False)
        # The leaf-scar rings that make a palm read at distance.
        b.cylinder(pts[i + 1], (pts[i + 1][0], pts[i + 1][1], pts[i + 1][2] + 0.12), r1 * height / 10 * 1.12,
                   'wood_dark', 7, caps=False)
    top = pts[-1]
    for i in range(fronds):
        ang = i * TAU / fronds + rng.uniform(-0.15, 0.15)
        rise = rng.uniform(0.25, 0.75) if i % 3 else rng.uniform(0.9, 1.3)
        length = height * rng.uniform(0.42, 0.55)
        width = length * 0.36
        cell = PALM_CELLS[i % len(PALM_CELLS)]
        u0, v0, u1, v1 = LEAF_CELLS[cell]
        _frond(b, top, ang, rise, length, width, (u0, v0, u1, v1), rng)
    for i in range(5):
        a = rng.uniform(0, TAU)
        b.sphere((top[0] + math.cos(a) * 0.35, top[1] + math.sin(a) * 0.35, top[2] - 0.35), 0.24 * height / 10,
                 'palm_trunk' if i % 2 else 'wood_dark', subdiv=0)
    return b


def _frond(b, top, ang, rise, length, width, cell, rng, steps=6):
    """A frond strip: an arching rachis that droops toward its tip, folded down the middle like a shallow V."""
    u0, v0, u1, v1 = cell
    um = (u0 + u1) / 2
    ca, sa = math.cos(ang), math.sin(ang)
    side = (-sa, ca, 0.0)
    droop = rng.uniform(0.9, 1.4)
    prev = None
    for k in range(steps + 1):
        t = k / steps
        reach = length * t
        z = top[2] + length * (rise * t - droop * t * t) * 0.62
        centre = (top[0] + ca * reach, top[1] + sa * reach, z)
        half = width * 0.5 * (0.35 + 0.65 * math.sin(math.pi * min(1.0, 0.15 + t * 0.95)))
        fold = half * 0.38
        left = (centre[0] + side[0] * half, centre[1] + side[1] * half, centre[2] - fold)
        right = (centre[0] - side[0] * half, centre[1] - side[1] * half, centre[2] - fold)
        v = v0 + (v1 - v0) * t
        row = (left, centre, right, v)
        if prev is not None:
            pl, pc, pr, pv = prev
            up = (0.0, 0.0, 1.0)
            nl = (side[0] * 0.45, side[1] * 0.45, 0.9)
            nr = (-side[0] * 0.45, -side[1] * 0.45, 0.9)
            b.face((pl, pc, centre, left), 'palm_frond', ((u0, pv), (um, pv), (um, v), (u0, v)), (nl, up, up, nl))
            b.face((pc, pr, right, centre), 'palm_frond', ((um, pv), (u1, pv), (u1, v), (um, v)), (up, nr, nr, up))
        prev = row


def shrub(seed, radius, palette, cards=140):
    rng = random.Random(seed)
    b = Builder(f'shrub_{seed}')
    pal = PALETTES[palette]
    lobes = [((0, 0, radius * 0.65), (radius, radius, radius * 0.7))]
    for i in range(3):
        a = i * TAU / 3 + rng.uniform(-0.4, 0.4)
        lobes.append(((math.cos(a) * radius * 0.6, math.sin(a) * radius * 0.6, radius * 0.5),
                      (radius * 0.6, radius * 0.6, radius * 0.5)))
    for c, r in lobes:
        _canopy(b, c, r, cards // len(lobes), max(0.6, radius * 0.55), rng, pal, (0, 0, radius * 0.2), radius * 0.4)
    return b


def flowering(seed, radius):
    """Bougainvillea and hibiscus mounds that carry the pink of the paintings on walls and terraces."""
    rng = random.Random(seed)
    b = shrub(seed, radius, 'green', 110)
    b.name = f'bloom_{seed}'
    for _ in range(26):
        a = rng.uniform(0, TAU)
        e = rng.uniform(0.1, 1.2)
        r = radius * rng.uniform(0.8, 1.05)
        p = (math.cos(a) * r * math.cos(e), math.sin(a) * r * math.cos(e), radius * 0.6 + r * 0.7 * math.sin(e))
        b.sphere(p, radius * rng.uniform(0.1, 0.16), SurfaceKey(('blossom','blossom_pale','blossom')[rng.randrange(3)],'flower'),
                 subdiv=0)
    return b


def _blade(b, base, ang, length, width, rise, bend, mat, segments=4, up=0.75):
    """One tapered, bending strip (a fern frond or a grass blade), both sides, normals leaning up so the clump
    shades as one soft mass instead of dark undersides."""
    ca, sa = math.cos(ang), math.sin(ang)
    px, py = -sa, ca
    rows = []
    for k in range(segments + 1):
        t = k / segments
        d = length * t
        z = base[2] + rise * t - bend * t * t
        # The tip keeps a sliver of width: a zero-width tip makes degenerate triangles that Unreal drops on import.
        w = width * max(0.08, (1.0 - t) ** 0.7) * (0.6 + 0.4 * math.sin(math.pi * min(1.0, t * 1.4)))
        cx, cy = base[0] + ca * d, base[1] + sa * d
        rows.append(((cx - px * w, cy - py * w, z), (cx + px * w, cy + py * w, z)))
    n = (ca * (1 - up), sa * (1 - up), up)
    m = math.sqrt(sum(c * c for c in n))
    n = tuple(c / m for c in n)
    for (a0, a1), (b0, b1) in zip(rows, rows[1:]):
        b.face((a0, a1, b1, b0), mat, ((0, 0), (1, 0), (1, 1), (0, 1)), (n,) * 4)
        b.face((a1, a0, b0, b1), mat, ((0, 0), (1, 0), (1, 1), (0, 1)), (n,) * 4)


def cover_fern(seed):
    """A fern clump: arching fronds from one crown, about knee high."""
    rng = random.Random(seed)
    b = Builder(f'cover_fern_{seed}')
    for i in range(rng.randint(7, 10)):
        ang = TAU * i / 8 + rng.uniform(-0.3, 0.3)
        mat = 'cover_fern_light' if rng.random() < 0.35 else 'cover_fern'
        _blade(b, (0.0, 0.0, 0.0), ang, rng.uniform(0.8, 1.3), rng.uniform(0.16, 0.24), rng.uniform(0.7, 1.0),
               rng.uniform(0.45, 0.75), mat, segments=5, up=0.7)
    return b


def cover_grass(seed):
    """A tuft of grass blades, some dry tips among the green."""
    rng = random.Random(seed)
    b = Builder(f'cover_grass_{seed}')
    for _ in range(rng.randint(12, 16)):
        ang = rng.uniform(0, TAU)
        r = rng.uniform(0.0, 0.18)
        mat = 'cover_grass_dry' if rng.random() < 0.25 else 'cover_grass'
        _blade(b, (math.cos(ang) * r, math.sin(ang) * r, 0.0), ang, rng.uniform(0.15, 0.35),
               rng.uniform(0.035, 0.05), rng.uniform(0.35, 0.6), rng.uniform(0.0, 0.15), mat, segments=3, up=0.6)
    return b


def cover_broadleaf(seed):
    """Low broad-leaf ground plants: a rosette of pointed leaves on short stalks."""
    rng = random.Random(seed)
    b = Builder(f'cover_leaf_{seed}')
    for i in range(rng.randint(5, 7)):
        ang = TAU * i / 6 + rng.uniform(-0.3, 0.3)
        mat = 'cover_leaf_light' if i % 3 == 0 else 'cover_leaf'
        _blade(b, (0.0, 0.0, 0.05), ang, rng.uniform(0.45, 0.65), rng.uniform(0.16, 0.22), rng.uniform(0.25, 0.4),
               rng.uniform(0.15, 0.3), mat, segments=3, up=0.8)
    return b


def prototypes():
    """Species library. Keys name each prototype; values are geometry builders."""
    protos = {}
    for i, (h, s, pal) in enumerate([(13, 15, 'green'), (11, 13, 'green'), (15, 17, 'green'), (12, 14, 'olive'),
                                     (14, 15, 'olive'), (11, 12, 'autumn'), (13, 14, 'gold'), (10, 12, 'green')]):
        protos[f'broad_{i}'] = broadleaf(4100 + i, h, s, pal, cards=int(360 + s * 12), card=1.3 + s * 0.06)
    for i, (h, s, pal) in enumerate([(21, 16, 'green'), (19, 14, 'olive'), (23, 17, 'green')]):
        protos[f'emergent_{i}'] = broadleaf(4200 + i, h, s, pal, cards=int(460 + s * 14), card=1.4 + s * 0.06,
                                            form='tiered')
    for i, (h, s, pal) in enumerate([(6.5, 6.5, 'green'), (5.5, 5.0, 'olive'), (7.0, 7.5, 'autumn')]):
        protos[f'small_{i}'] = broadleaf(4300 + i, h, s, pal, cards=260, card=1.0)
    for i, h in enumerate((9.0, 11.5, 13.5, 15.5, 10.5, 12.5)):
        protos[f'palm_{i}'] = palm(4400 + i, h, fronds=14 + i % 3)
    for i, (r, pal) in enumerate([(1.6, 'green'), (2.4, 'green'), (2.0, 'olive'), (3.2, 'green'), (1.8, 'autumn')]):
        protos[f'shrub_{i}'] = shrub(4500 + i, r, pal, cards=int(60 + r * 55))
    for i, r in enumerate((1.2, 1.7)):
        protos[f'bloom_{i}'] = flowering(4600 + i, r)
    # Groundcover: real standing plants instead of a printed leaf carpet (playtest note 1).
    for i in range(3):
        protos[f'cover_fern_{i}'] = cover_fern(4700 + i)
        protos[f'cover_grass_{i}'] = cover_grass(4710 + i)
        protos[f'cover_leaf_{i}'] = cover_broadleaf(4720 + i)
    return protos


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


def triangles(builder):
    return sum(len(f) - 2 for f in builder.faces)


if __name__ == '__main__':
    import time
    started = time.time()
    protos = prototypes()
    built = time.time()
    places = scatter() + bloom_spots(random.Random(5))
    done = time.time()
    tris = {k: triangles(v) for k, v in protos.items()}
    counts = {}
    for p in places:
        counts[p[0]] = counts.get(p[0], 0) + 1
    print('prototypes', len(protos), 'unique tris', sum(tris.values()), f'{built - started:.1f}s')
    print('placements', len(places), 'rendered tris', sum(tris[k] * n for k, n in counts.items()),
          f'{done - built:.1f}s')
    for k in sorted(counts):
        print(f'  {k:12s} {counts[k]:6d} x {tris[k]:5d}')
