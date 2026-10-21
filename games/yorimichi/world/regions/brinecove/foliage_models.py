"""Pure local foliage model geometry; never imports terrain or placement code."""
import math
import random

from brinecove.geom import Builder
from brinecove.foliage_atlas import LEAF_CELLS, PALM_CELLS, cell_uvs

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
        b.sphere(p, radius * rng.uniform(0.1, 0.16), ('blossom', 'blossom_pale', 'blossom')[rng.randrange(3)],
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

BUILDERS = {function.__name__: function for function in
            (broadleaf, palm, shrub, flowering, cover_fern, cover_grass, cover_broadleaf)}


def build(spec):
    """@cc [owner:fontanierh,label:performance] independent-local-model-geometry
    A plant model MUST depend only on its own parameters and shared geometry/UV/atlas code.
    Terrain, instance placements and material colours MUST NOT enter model generation.
    Seeded generation MUST preserve the same local geometry for unchanged definitions.
    """
    if set(spec) != {"builder", "parameters"} or spec["builder"] not in BUILDERS:
        raise ValueError("Invalid foliage model definition")
    return BUILDERS[spec["builder"]](**spec["parameters"])
