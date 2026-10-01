"""The Mega Park trail: a secluded footpath from the woodland air station over the forested ridge to the park's low
west deck (docs/MEGAPARK.md, "Getting there").

Pure NumPy. The path crosses three grounds, all carved to one bed:
- the island's square heightmap, carved by integrate() (gen_world.py);
- APPROACH, a 2 m patch of ground north of the square (HD_NorthApproach, hidamari/build.py). The far hills' 67 m grid
  was too coarse to walk through a forest on; the patch replaces them there, and the far forest's painted cards with
  a forest of the island's detailed trees (forest());
- the north foothills (hidamari/mountains.py surface_grid).
integrate() works the bed out once, from the uncarved ground along the path smoothed to walking grades, and writes it
to build/yorimichi/megapark/trail.json, which every later step reads.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json
import math
from functools import lru_cache

import numpy as np

from village.layout import nearest, sample, spline, smooth

# From the woodland air station's footpath beside its pad, up through the woodland and a switchback on the far hills'
# shoulder, down its north side into the valley west of the park, and along the valley to the park's low west deck,
# square to its edge for the last 8 m, to the foot of the steps (STEPS).
WAYPOINTS = [(-184, 214.5), (-181, 229), (-177, 246), (-170, 264), (-163, 282), (-154, 302), (-140, 330), (-105, 362),
             (-92, 388), (-112, 410), (-150, 440), (-185, 470), (-203, 505), (-214, 550), (-232, 610), (-258, 680),
             (-288, 760), (-318, 840), (-350, 910), (-378, 990), (-393, 1060), (-396, 1125), (-382, 1185), (-352, 1228),
             (-318, 1250), (-290, 1257), (-272.12, 1258.85), (-265.19, 1262.85)]
# The low west deck stands about 1.2 m over the ground at its straight west edge. Eight timber steps climb from the
# trail's end onto it: DECK is a point on the edge and the deck's height, INTO the way across the edge (the park's YAW
# is -60 degrees), and the steps' treads end at the edge, the top one flush with the deck.
DECK = (-263.11, 1264.05, 51.92)
INTO = (math.cos(math.radians(30)), math.sin(math.radians(30)))
STEPS, TREAD = 8, .3
STEP = 2.                       # metres between the path's samples, and the approach ground's grid
HALF = 1.2                      # the path's half-width
SMOOTH = 20.                    # metres: the bed is the ground along the path under a Gaussian of this sigma
CARVE = (5.3, 3.4)              # 2 m grounds: the bed within 1.9 m of the path, back to the hillside by 5.3
CARVE_COARSE = (11., 7.)        # the foothills' 10 m grid
APPROACH = (-300., 300., -36., 500.)   # x0, y0, x1, y1: on the square's 2 m grid, by far-hill columns -303 and -34
CLEAR = dict(tree=6.5, plant=2.2)      # metres kept clear of the path's centre line in the square
DETAIL = 35.                    # metres: the square's painted cards this near the path become detailed trees
TRUNK = 3.                      # metres from the path's centre line to the approach's nearest trunks
UNDER = (('Grass_A', .3), ('Grass_B', .28), ('Bush_Green_A', .12), ('Bush_Ochre_A', .12), ('Bush_Flower_A', .05),
         ('Rock_B', .06), ('Litter', .07))
SEED = 1400


@lru_cache(maxsize=1)
def path():
    """(xy, s): the path's centre line every STEP metres, and the distance along it."""
    return spline(WAYPOINTS, STEP)


@lru_cache(maxsize=1)
def bed():
    """[[x, y, z], ...]: the path's centre line on its bed (integrate())."""
    return np.asarray(json.loads((yori.OUT / 'megapark' / 'trail.json').read_text())['points'], 'f8')


def _near(x, y, points, reach):
    """(index, distance, bed height) of the points within `reach` of the polyline's bounds."""
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    lo, hi = points[:, :2].min(0) - reach, points[:, :2].max(0) + reach
    index = np.flatnonzero((x >= lo[0]) & (x <= hi[0]) & (y >= lo[1]) & (y <= hi[1]))
    d, z = nearest(x.ravel()[index], y.ravel()[index], points) if len(index) else (np.zeros(0), np.zeros(0))
    return index, d, z


def distance(x, y, reach=400.):
    """Metres from the path's centre line (1e9 beyond `reach` of its bounds)."""
    xy, _ = path()
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    index, d, _ = _near(x, y, np.column_stack([xy, np.zeros(len(xy))]), reach)
    out = np.full(x.size, 1e9)
    out[index] = d
    return out.reshape(x.shape)


def carve(x, y, z, points=None, reach=CARVE[0], fade=CARVE[1]):
    """`z` levelled to the bed (`points`, by default bed()) near the path."""
    points = bed() if points is None else points
    z = np.array(np.broadcast_to(z, np.broadcast(x, y).shape), 'f8')
    index, d, bz = _near(x, y, points, reach)
    w = smooth((reach - d) / fade)
    flat = z.reshape(-1)
    flat[index] = flat[index] * (1 - w) + bz * w
    return z


def in_approach(x, y, margin=0.):
    x0, y0, x1, y1 = APPROACH
    return (x > x0 + margin) & (x < x1 - margin) & (y > y0 + margin) & (y < y1 - margin)


def _approach_raw(x, y, row, backdrop):
    """The approach's ground before the carve: the far hills, blended from the square's north edge (`row`, its height
    at y=300) and given a forest floor's small relief away from the patch's edges."""
    from hidamari import mountains
    x0, y0, x1, y1 = APPROACH
    z = row + (backdrop - row) * smooth((y - y0) / 40)
    inner = smooth((x - x0) / 25) * smooth((x1 - x) / 25) * smooth((y - y0) / 25) * smooth((y1 - y) / 25)
    return z + inner * (mountains.noise(x, y, 23, 51) * 1.1 + mountains.noise(x, y, 61, 52) * 1.6)


def _profile(g, s):
    """The bed: the ground along the path under a Gaussian, tighter towards the ends, which are held."""
    def gauss(sigma):
        k = sigma / STEP
        r = int(3 * k)
        # Odd reflection keeps the ends' heights and slopes.
        pad = np.concatenate([2 * g[0] - g[r:0:-1], g, 2 * g[-1] - g[-2:-r - 2:-1]])
        kernel = np.exp(-.5 * (np.arange(-r, r + 1) / k) ** 2)
        return np.convolve(pad, kernel / kernel.sum(), mode='valid')
    end = np.minimum(s, s[-1] - s)
    z = gauss(SMOOTH / 3) + (gauss(SMOOTH) - gauss(SMOOTH / 3)) * smooth(end / 40)
    return g + (z - g) * smooth(end / 4)


def integrate(world, h):
    """Work out the bed, carve the square's part, and clear the square's and the approach's trees and plants.
    `world` is gen_world.py's world.json, `h` its heightmap (rows y, columns x), changed in place."""
    from hidamari import mountains
    size = world['size']
    far = np.load(yori.OUT / 'farhills.npy')
    axis = np.linspace(-3200, 3200, far.shape[0])

    def backdrop(x, y):
        # hidamari/layout.py backdrop_grid() is the far hills unchanged west of x=180.
        fx = np.clip((np.asarray(x) + 3200) / (axis[1] - axis[0]), 0, len(axis) - 1.001)
        fy = np.clip((np.asarray(y) + 3200) / (axis[1] - axis[0]), 0, len(axis) - 1.001)
        i, j = fx.astype(int), fy.astype(int)
        u, v = fx - i, fy - j
        return (far[j, i] * (1 - u) + far[j, i + 1] * u) * (1 - v) + (far[j + 1, i] * (1 - u) + far[j + 1, i + 1] * u) * v

    xy, s = path()
    x, y = xy[:, 0], xy[:, 1]
    assert (x < 170).all(), 'the far hills under the path must be the unchanged ones'
    row = sample(h, x, np.full_like(y, size / 2))
    # In the foothills, the ground as their 10 m grid will have it (the park's stamp drops steeply at the deck's edge,
    # where the grid and the ground under it part by most of a metre).
    foothills = mountains.on_grid(x, y, lambda gx, gy: mountains.raw_height(
        gx, gy, backdrop(gx, gy), backdrop(gx, np.full_like(gy, APPROACH[3]))))
    g = np.where(y <= size / 2, sample(h, x, y),
                 np.where(y < APPROACH[3], _approach_raw(x, y, row, backdrop(x, y)), foothills))
    points = np.column_stack([xy, _profile(g, s)])
    # The square's part, and its edge row where the approach starts.
    before = h.copy()
    grid = np.linspace(-size / 2, size / 2, len(h))
    X, Y = np.meshgrid(grid, grid)
    part = points[points[:, 1] < size / 2 + 2 * STEP]
    h[:] = carve(X, Y, h, part)
    _cards(world, part)
    removed = {}
    for name, rows in list(world['instances'].items()):
        try:
            a = np.asarray(rows, 'f8')
        except ValueError:
            continue
        if a.ndim != 2 or a.shape[1] < 3:
            continue
        gone = in_approach(a[:, 0], a[:, 1])
        if name.startswith(('Tree', 'Bush', 'Grass', 'Rock', 'Litter')):
            index, d, _ = _near(a[:, 0], a[:, 1], part, CLEAR['tree'])
            gone[index] |= d < (CLEAR['tree'] if name.startswith('Tree') else CLEAR['plant'])
        # What stays on the carved ground stays on it.
        inside = (np.abs(a[:, 0]) < size / 2) & (np.abs(a[:, 1]) < size / 2) & ~gone
        a[inside, 2] += sample(h, a[inside, 0], a[inside, 1]) - sample(before, a[inside, 0], a[inside, 1])
        world['instances'][name] = a[~gone].tolist()
        if gone.any():
            removed[name] = int(gone.sum())
    world['park_trail'] = np.round(points, 3).tolist()
    out = yori.OUT / 'megapark'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'trail.json').write_text(json.dumps({'points': world['park_trail'], 'half_width': HALF, 'approach': APPROACH,
                                                'length': round(float(s[-1]), 1), 'removed': removed}) + '\n')
    bed.cache_clear()
    return removed


def _cards(world, part):
    """The far forest's painted cards near the square's part of the path become the island's detailed trees, as round
    the tree house (treehouse/layout.py DETAILED)."""
    from treehouse.layout import DETAILED as CARDS
    rng = np.random.default_rng(SEED)
    for card, kinds in CARDS.items():
        a = np.asarray(world['instances'].get(card, []), 'f8').reshape(-1, 5)
        index, d, _ = _near(a[:, 0], a[:, 1], part, DETAIL)
        turn = np.zeros(len(a), bool)
        turn[index] = d < DETAIL
        world['instances'][card] = a[~turn].tolist()
        moved = a[turn]
        pick = rng.choice(len(kinds), size=len(moved), p=[w for _, w in kinds])
        for k, (name, _) in enumerate(kinds):
            world['instances'].setdefault(name, []).extend(moved[pick == k].tolist())


@lru_cache(maxsize=1)
def approach_grid():
    """(xs, ys, z): the approach's ground every STEP metres, rows y. Its south row is the square's north edge, its
    north row the foothills' south edge (hidamari/mountains.py)."""
    from hidamari import mountains
    from hidamari.layout import backdrop_height, north_base_height
    x0, y0, x1, y1 = APPROACH
    xs = np.arange(x0, x1 + STEP / 2, STEP)
    ys = np.arange(y0, y1 + STEP / 2, STEP)
    X, Y = np.meshgrid(xs, ys)
    h = np.load(yori.OUT / 'heightmap.npy').astype('f8')
    row = np.broadcast_to(sample(h, xs, np.full_like(xs, y0)), X.shape)
    top = mountains.height(X, np.full_like(Y, y1), north_base_height)
    z = _approach_raw(X, Y, row, backdrop_height(X, Y))
    # Along its sides it stands at least as high as the far hills it meets, so they never show through it.
    side = 1 - smooth(np.minimum(X - x0, x1 - X) / 20)
    z = np.maximum(z, side * _far_hills(X, Y, upper=True) + (1 - side) * z)
    z = carve(X, Y, z + (top - z) * smooth((Y - y1 + 30) / 30))
    z += (top - z) * smooth((Y - y1 + 4) / 4)
    return xs, ys, row + (z - row) * smooth((Y - y0) / 6)


def approach_height(x, y):
    """The approach's ground, on the same triangles as its mesh."""
    xs, ys, z = approach_grid()
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    fx = np.clip((x - xs[0]) / STEP, 0, len(xs) - 1.001)
    fy = np.clip((y - ys[0]) / STEP, 0, len(ys) - 1.001)
    i, j = fx.astype(int), fy.astype(int)
    u, v = fx - i, fy - j
    z00, z10, z01, z11 = z[j, i], z[j, i + 1], z[j + 1, i], z[j + 1, i + 1]
    return np.where(u >= v, z00 * (1 - u) + z10 * (u - v) + z11 * v, z00 * (1 - v) + z11 * u + z01 * (v - u))


def approach_mesh():
    """HD_NorthApproach: the approach's ground under its forest, with skirts down the far hills' sides."""
    from village.build import Mesh
    from hidamari import mountains
    xs, ys, z = approach_grid()
    X, Y = np.meshgrid(xs, ys)
    litter = mountains.noise(X, Y, 40, 41)
    floor = np.stack([.066 + .018 * litter, .062 + .014 * litter, np.full_like(X, .026)], -1)
    # It takes the foothills' colours where it meets them.
    edge = smooth((Y - APPROACH[3] + 30) / 30)[..., None]
    colours = floor * (1 - edge) + mountains.colours(X, np.full_like(Y, APPROACH[3]), z) * edge
    m = Mesh('HD_NorthApproach')
    for j in range(len(ys) - 1):
        for i in range(len(xs) - 1):
            for corners in (((0, 0), (1, 0), (1, 1)), ((0, 0), (1, 1), (0, 1))):
                m.poly([(X[j + b, i + a], Y[j + b, i + a], z[j + b, i + a]) for a, b in corners],
                       tuple(np.mean([colours[j + b, i + a] for a, b in corners], 0)))
    # The far hills meet the square's edge lower than the square does, so the skirts reach below them.
    for i, west in ((0, True), (len(xs) - 1, False)):
        x = np.full_like(ys, xs[i])
        bottom = np.minimum(z[:, i] - 3, _far_hills(x, ys) - 1)
        for j in range(len(ys) - 1):
            skirt = [(xs[i], ys[j], z[j, i]), (xs[i], ys[j + 1], z[j + 1, i]), (xs[i], ys[j + 1], bottom[j + 1]),
                     (xs[i], ys[j], bottom[j])]
            m.poly(skirt if west else skirt[::-1], tuple(colours[j, i]))
    return m


def _far_hills(x, y, upper=False):
    """The far hills' lower (or upper) triangulation as build_terrain.py exports them: lowered under the foothills and
    the approach, or as they were (`upper`)."""
    from hidamari import mountains
    from hidamari.layout import backdrop_grid, north_height
    far = backdrop_grid().copy()
    axis = np.linspace(-3200, 3200, far.shape[0])
    if not upper:
        X, Y = np.meshgrid(axis, axis)
        mask = mountains.contains(X, Y) | in_approach(X, Y)
        far[mask] = np.minimum(far[mask], north_height(X, Y)[mask] - 25)
    fx = np.clip((np.asarray(x) + 3200) / (axis[1] - axis[0]), 0, len(axis) - 1.001)
    fy = np.clip((np.asarray(y) + 3200) / (axis[1] - axis[0]), 0, len(axis) - 1.001)
    i, j = fx.astype(int), fy.astype(int)
    u, v = fx - i, fy - j
    a, b, c, d = far[j, i], far[j, i + 1], far[j + 1, i + 1], far[j + 1, i]
    ac = np.where(u >= v, a * (1 - u) + b * (u - v) + c * v, a * (1 - v) + c * u + d * (v - u))
    bd = np.where(u + v <= 1, a * (1 - u - v) + b * u + d * v, b * (1 - v) + c * (u + v - 1) + d * (1 - u))
    return np.maximum(ac, bd) if upper else np.minimum(ac, bd)


@lru_cache(maxsize=1)
def _square():
    return np.load(yori.OUT / 'heightmap.npy').astype('f8')


def ground(x, y, north_height):
    """The rendered ground along the path: the square's (either triangulation), or `north_height` (hidamari/layout.py,
    the approach's and the foothills')."""
    from village.layout import upper_surface
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    return np.where((np.abs(x) <= 300) & (y <= APPROACH[1]), upper_surface(_square(), x, y), north_height(x, y))


def trail_mesh(north_height):
    """HD_NorthParkTrail: the path, packed earth between soft edges of leaf litter, just over the ground."""
    from village.build import Mesh
    p = bed()
    t = np.gradient(p[:, :2], axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    n = np.stack([-t[:, 1], t[:, 0]], 1)
    across = (-HALF - .4, -HALF + .25, HALF - .25, HALF + .4)
    rows = []
    for o in across:
        x, y = p[:, 0] + n[:, 0] * o, p[:, 1] + n[:, 1] * o
        rows.append(np.column_stack([x, y, ground(x, y, north_height) + .045]))
    earth, litter = (.21, .15, .085), (.13, .10, .05)
    m = Mesh('HD_NorthParkTrail')
    for k in range(len(p) - 1):
        for a, b, colour in ((rows[0], rows[1], litter), (rows[1], rows[2], earth), (rows[2], rows[3], litter)):
            m.poly([tuple(a[k]), tuple(a[k + 1]), tuple(b[k + 1]), tuple(b[k])], colour)
    # The steps onto the deck: timber treads on solid risers down into the ground, between two stringers.
    plank, wood = (.32, .17, .067), (.18, .075, .026)
    fx, fy = p[-1, :2]
    g = float(ground(np.array([fx]), np.array([fy]), north_height)[0])
    rise = (DECK[2] - g) / STEPS
    with m.at((fx, fy, 0.), math.degrees(math.atan2(INTO[1], INTO[0])) - 90):
        for k in range(STEPS):      # local +Y is INTO
            top = g + rise * (k + 1)
            m.box((0, TREAD * (k + .5), (top + g - .4) / 2), (2 * HALF, TREAD + .01, top - g + .4), plank if k % 2 else
                  tuple(c * .93 for c in plank))
        for side in (-1, 1):
            m.beam((side * (HALF + .07), -.1, g - .1), (side * (HALF + .07), STEPS * TREAD, DECK[2] + .08), .14, .22, wood)
    return m


def forest(instances, north_height):
    """The approach's forest: the island's detailed autumn trees in the Mega Park forest's clumps (megapark/forest.py),
    closing over the path, and undergrowth along the path from the square to the park. Returns {name: count}."""
    from megapark import forest as park
    rng = np.random.default_rng(SEED + 1)
    x0, y0, x1, y1 = APPROACH
    p = park._grid(rng, (x0 + 2, y0 + 2, x1 - 2, y1), park.FILL['spacing'])
    glade = np.sin(p[:, 0] * .043 + np.sin(p[:, 1] * .037) * 2.1) * np.sin(p[:, 1] * .041 + np.sin(p[:, 0] * .029) * 1.7)
    d = distance(p[:, 0], p[:, 1])
    keep = (d > TRUNK) & (rng.random(len(p)) < .95 * smooth((glade + .78) / .2)) & in_approach(p[:, 0], p[:, 1], 1.)
    p = p[keep]
    z = north_height(p[:, 0], p[:, 1])
    clump = np.where(rng.random(len(p)) < park.MIX, rng.integers(0, len(park.FAMILIES), len(p)), park._clump(p[:, 0], p[:, 1]))
    done = {}
    have = park._bins(np.zeros((0, 2)), 8)
    for q, base, family in zip(p, z, clump):
        if park._near(have, q, park.FILL['gap'], 8):
            continue
        kinds, scale = park.FAMILIES[family]
        name = kinds[rng.choice(len(kinds), p=[w for _, w in kinds])][0]
        instances.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]), 3), round(float(base) - .3, 3),
                                               round(float(rng.uniform(0, 360)), 1), round(float(rng.uniform(*scale)), 3)])
        have.setdefault((math.floor(q[0] / 8), math.floor(q[1] / 8)), []).append(q)
        done[name] = done.get(name, 0) + 1
    # Undergrowth along the path north of the square, between the trunks.
    xy, _ = path()
    t = np.gradient(xy, axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    k = np.repeat(np.flatnonzero((xy[:, 1] > y0) & (np.arange(len(xy)) % 2 == 0)), 2)
    side = np.tile([-1., 1.], len(k) // 2) * rng.uniform(HALF + .7, 8., len(k))
    q = xy[k] + np.column_stack([-t[k, 1], t[k, 0]]) * side[:, None] + t[k] * rng.uniform(-1.5, 1.5, len(k))[:, None]
    q = q[distance(q[:, 0], q[:, 1], 20.) > HALF + .6]
    z = north_height(q[:, 0], q[:, 1])
    pick = rng.choice(len(UNDER), size=len(q), p=[w for _, w in UNDER])
    for point, base, kind in zip(q, z, pick):
        if park._near(have, point, 1.2, 8):
            continue
        name = UNDER[kind][0]
        size = rng.uniform(.6, 1.0) if name.startswith(('Grass', 'Rock')) else rng.uniform(.7, 1.2)
        instances.setdefault(name, []).append([round(float(point[0]), 3), round(float(point[1]), 3),
                                               round(float(base) - (.08 if name.startswith('Grass') else .15), 3),
                                               round(float(rng.uniform(0, 360)), 1), round(float(size), 3)])
        done[name] = done.get(name, 0) + 1
    return done


def near_boxes():
    """[[x0, y0, x1, y1], ...]: where the trees along the path are near ones in Unreal (city.json near_trees), from
    where the square's own near trees end (450 m out) to the Mega Park forest's box (megapark/forest.py near_box())."""
    return [[APPROACH[0], 440., APPROACH[2], APPROACH[3]], [-330., APPROACH[3] - 5, -150., 740.]]
