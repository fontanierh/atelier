"""The island's ground where the Mega Park meets its air station (docs/MEGAPARK.md, "Gate").

Pure NumPy. The north foothills (hidamari/mountains.py) are a 10 m grid of flat facets, and round the park
placement.terrain sinks them under the lowest park surface within 20 m. By the station that left a dark pit under the
footbridge, a trench along the hillside's north edge and thin park edges standing over the air. In GATE a 1 m patch
of ground replaces the foothills (HD_NorthGate, hidamari/build.py; hidamari/layout.py north_height samples it):

- it rises to every open park edge in the box from below (SEAT under it) and buries the seam's skirt where that hangs
  less than BURY metres (LEDGE under its edge), so no edge stands over a gap; a deeper skirt (the gate's west cliff)
  and the park's own walls keep their faces, the ground meeting them between their foot and their top;
- the station's pad and its footpath stay level at the station's height, and a shallow dell (DELL) runs under the
  footbridge;
- farther than FAR metres from the park it keeps the foothills' relief, eased, and on its border it is the foothills'
  own surface, so the two meet without a step.

It is drawn like the island's ground (mesh(): smooth, the ground texture, M_NorthGate in unreal/Scripts/
mountain_material.py) and dressed like it (dress(): grass, fallen leaves, rocks).
"""
from functools import lru_cache

import numpy as np

from megapark import placement

GATE = (-260., 1440., -60., 1600.)  # x0, y0, x1, y1: island metres, on the foothills' 10 m grid
STEP = 1.                           # metres between the patch's nodes
EDGE = 1.6                          # metres: an uncovered node this close to the park's cover is on its edge
SEAT = .08                          # metres the ground stays under an edge it meets
LEDGE = .22                         # metres it stays under a buried skirt's edge, which then shows as a low ledge
UNDER = (.15, 1.)                   # metres under the park's lowest surface: within DEEP of its edge, and deeper in
DEEP = 3.                           # metres
HUG = 2.5                           # metres under the cover from its edge where the ground follows it closely
WALL = .35                          # metres: geometry this far under an edge's top near it is a face going down
BURY = 10.                          # a skirt hanging over less than this much of a drop is buried
FAR = 20.                           # metres from the park where the foothills' own relief takes over
FEATHER = 15.                       # metres over which an edge leaving the patch eases back to the foothills
DELL = dict(centre=(-164.5, 1471.5), radius=(5.5, 7.), depth=2.5)  # under the footbridge (zeppelin/layout.py)
RELIEF = .35                        # metres of gentle relief added where nothing holds the ground


def inside(x, y):
    """Whether (x, y) is on the patch."""
    x0, y0, x1, y1 = GATE
    return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)


def cell_inside(x, y):
    """Whether the foothills' 10 m cell with its south-west corner at (x, y) lies on the patch."""
    x0, y0, x1, y1 = GATE
    return (x >= x0 - 1e-6) & (x + 10. <= x1 + 1e-6) & (y >= y0 - 1e-6) & (y + 10. <= y1 + 1e-6)


def _smooth(t):
    t = np.clip(t, 0., 1.)
    return t * t * (3 - 2 * t)


def _up(t):
    """The triangles of t that are not upright (their surface can be stood on, or hangs over)."""
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return t[np.abs(n[:, 2]) > .2 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)]


@lru_cache(maxsize=1)
def _triangles():
    """(solid, collision, skirt): island-metre triangles (n, 3, 3) round GATE. solid is the park's drawn surfaces
    (no plants) and the seam, collision the riding collision, skirt the seam's skirt."""
    from megapark import plants
    x0, y0, x1, y1 = GATE

    def near(t):
        lo, hi = t[..., :2].min(1), t[..., :2].max(1)
        return t[(hi[:, 0] > x0 - 3) & (lo[:, 0] < x1 + 3) & (hi[:, 1] > y0 - 3) & (lo[:, 1] < y1 + 3)]
    drawn = []
    for model in placement.kept()[0]:
        with np.load(placement.SOURCE / model['npz']) as arrays:
            for part in model['meshes']:
                i = part['index']; v = arrays[f'vertices_{i}']
                if len(v) and not plants.is_foliage(part):
                    drawn.append(near(placement.native_to_island(v[arrays[f'faces_{i}']].astype('f8'))))
    drawn += [near(placement.native_to_island(v[f])) for _, _, v, f in placement.seam_parts()]
    collision = near(placement.place(np.concatenate([placement.collision_triangles(), placement.seam_triangles()])))
    skirt = near(placement.native_to_island(placement.skirt_triangles()))
    return np.concatenate(drawn), collision, skirt


def _lowest_surface(t, xs, ys):
    """The lowest of the triangles t over each node (inf where none is)."""
    nx, ny = len(xs), len(ys)
    out = np.full((ny, nx), np.inf)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    ok = np.abs(den) > 1e-12
    t, a, b, c, den = t[ok], a[ok], b[ok], c[ok], den[ok]
    i0 = np.clip(np.ceil((t[:, :, 0].min(1) - xs[0]) / STEP - 1e-6).astype(int), 0, nx)
    i1 = np.clip(np.floor((t[:, :, 0].max(1) - xs[0]) / STEP + 1e-6).astype(int), -1, nx - 1)
    j0 = np.clip(np.ceil((t[:, :, 1].min(1) - ys[0]) / STEP - 1e-6).astype(int), 0, ny)
    j1 = np.clip(np.floor((t[:, :, 1].max(1) - ys[0]) / STEP + 1e-6).astype(int), -1, ny - 1)
    w = np.maximum(i1 - i0 + 1, 0); count = w * np.maximum(j1 - j0 + 1, 0)
    k = np.repeat(np.arange(len(t)), count)
    off = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    ii = i0[k] + off % np.maximum(w[k], 1); jj = j0[k] + off // np.maximum(w[k], 1)
    px, py = xs[ii], ys[jj]
    l1 = ((b[k, 1] - c[k, 1]) * (px - c[k, 0]) + (c[k, 0] - b[k, 0]) * (py - c[k, 1])) / den[k]
    l2 = ((c[k, 1] - a[k, 1]) * (px - c[k, 0]) + (a[k, 0] - c[k, 0]) * (py - c[k, 1])) / den[k]
    l3 = 1 - l1 - l2
    on = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
    z = l1 * t[k, 0, 2] + l2 * t[k, 1, 2] + l3 * t[k, 2, 2]
    np.minimum.at(out, (jj[on], ii[on]), z[on])
    return out


def _lowest_near(t, xs, ys):
    """The lowest point of the triangles t within about a metre of each node, faces going down included."""
    nx, ny = len(xs), len(ys)
    out = np.full((ny, nx), np.inf)
    if len(t):
        s = placement.surface_samples(t, .3)
        i = np.round((s[:, 0] - xs[0]) / STEP).astype(int); j = np.round((s[:, 1] - ys[0]) / STEP).astype(int)
        ok = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
        np.minimum.at(out, (j[ok], i[ok]), s[ok, 2])
    return _min_filter(out, 1.5)


def _edge_height(t, xs, ys, nodes):
    """Over each node of `nodes`: the height of the triangles t at their nearest point in plan, the lowest of the points
    within 25 cm of the nearest (inf where nothing is within EDGE). By the park's edge, that is the edge's own
    height."""
    out = np.full(nodes.shape, np.inf)
    s = placement.surface_samples(t, .25)
    nx = len(xs) + 6
    ci = np.floor((s[:, 0] - xs[0]) / STEP).astype(int) + 3; cj = np.floor((s[:, 1] - ys[0]) / STEP).astype(int) + 3
    ok = (ci >= 0) & (ci < nx) & (cj >= 0) & (cj < len(ys) + 6)
    key = cj[ok] * nx + ci[ok]; s = s[ok]
    order = np.argsort(key, kind='stable'); key, s = key[order], s[order]
    r = int(np.ceil(EDGE / STEP))
    for j, i in zip(*np.nonzero(nodes)):
        rows = [np.searchsorted(key, [(j + dj + 3) * nx + i - r + 2, (j + dj + 3) * nx + i + r + 4])
                for dj in range(-r - 1, r + 1)]
        p = np.concatenate([s[a:b] for a, b in rows])
        if not len(p):
            continue
        d = np.hypot(p[:, 0] - xs[i], p[:, 1] - ys[j])
        if d.min() <= EDGE:
            out[j, i] = p[d <= d.min() + .25, 2].min()
    return out


def _faces_away(t, X, Y, nodes):
    """Nodes of `nodes` that see the back of the upright faces of t nearest them (within EDGE): a face drawn one-sided
    whose front looks into the park, so from the island it is not drawn at all."""
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    upright = np.abs(n[:, 2]) <= .2 * np.maximum(np.linalg.norm(n, axis=1), 1e-12)
    t, n = t[upright], n[upright][:, :2]
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    out = np.zeros(nodes.shape, bool)
    if not len(t):
        return out
    steps = np.maximum(np.ceil(np.linalg.norm(t - np.roll(t, 1, 1), axis=-1).max(1) / .5).astype(int), 1)
    points, normals = [], []
    for k in np.unique(steps):
        i, j = np.array([(i, j) for i in range(k + 1) for j in range(k + 1 - i)]).T / k
        w = np.stack([1 - i - j, i, j], -1)
        points.append(np.einsum('kv,tvc->tkc', w, t[steps == k, :, :2]).reshape(-1, 2))
        normals.append(np.repeat(n[steps == k], len(w), 0))
    points, normals = np.concatenate(points), np.concatenate(normals)
    for j, i in zip(*np.nonzero(nodes)):
        d = points - (X[j, i], Y[j, i])
        near = (np.abs(d) <= EDGE).all(1)
        if near.any():
            dist = np.hypot(*d[near].T)
            weight = 1 / (dist + .1)
            out[j, i] = float((weight * (normals[near] * -d[near]).sum(1)).sum()) < 0
    return out


def _min_filter(field, radius):
    r = int(np.floor(radius / STEP))
    ny, nx = field.shape
    p = np.pad(field, r, constant_values=np.inf)
    out = field.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if (dx * dx + dy * dy) * STEP * STEP <= radius * radius:
                out = np.minimum(out, p[r + dy:r + dy + ny, r + dx:r + dx + nx])
    return out


def _grow(mask, within):
    """Nodes of `within` connected to `mask` through `within` (4-neighbours)."""
    out = mask & within
    while True:
        q = np.pad(out, 1)
        grown = (q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:] | out) & within
        if (grown == out).all():
            return out
        out = grown


def _distance(X, Y, mask):
    """Metres from each node to the nearest node of mask (inf when mask is empty)."""
    p = np.stack([X[mask], Y[mask]], 1)
    out = np.full(X.size, np.inf)
    if len(p):
        q = np.stack([X.ravel(), Y.ravel()], 1)
        for s in range(0, len(q), 2048):
            d = q[s:s + 2048, None, :] - p[None]
            out[s:s + 2048] = np.sqrt((d * d).sum(-1).min(1))
    return out.reshape(X.shape)


def _gauss(field, sigma):
    """field blurred with a Gaussian of sigma metres (edges clamped)."""
    r = int(np.ceil(3 * sigma / STEP))
    k = np.exp(-.5 * (np.arange(-r, r + 1) * STEP / sigma) ** 2); k /= k.sum()
    p = np.pad(field, ((0, 0), (r, r)), mode='edge')
    out = sum(k[i] * p[:, i:i + field.shape[1]] for i in range(2 * r + 1))
    p = np.pad(out, ((r, r), (0, 0)), mode='edge')
    return sum(k[i] * p[i:i + field.shape[0]] for i in range(2 * r + 1))


@lru_cache(maxsize=2)
def grid(base_sampler):
    """The patch every STEP metres: a dict of node fields (rows y, columns x). z is the ground; the rest tells colours
    and dressing where the park's edges, the station's footpath and the open ground are."""
    from hidamari import mountains
    from zeppelin.layout import PARK_PAD, PARK_WALK, PARK_BRIDGE, STATIONS
    x0, y0, x1, y1 = GATE
    xs = np.arange(x0, x1 + STEP / 2, STEP); ys = np.arange(y0, y1 + STEP / 2, STEP)
    X, Y = np.meshgrid(xs, ys)
    coarse = mountains.height(X, Y, base_sampler)
    solid, collision, skirt = _triangles()
    low = np.minimum(_lowest_surface(_up(solid), xs, ys), _lowest_surface(_up(collision), xs, ys))
    covered = np.isfinite(low)
    border = np.zeros(X.shape, bool); border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    # The island's side: uncovered nodes joined to the border outside the park's footprint (an opening in the park
    # that reaches the border is still the park's).
    outside = _grow(border & ~covered & ~placement.contains(X, Y), ~covered)
    # Uncovered nodes the park closes all round are under it, at the lowest cover beside them.
    hole = ~covered & ~outside
    while (hole & ~np.isfinite(low)).any():
        low = np.where(hole & ~np.isfinite(low), _min_filter(low, 1.5), low)
    covered |= hole
    # The edge's top: the cover's height at its nearest point (the lowest cover within EDGE where that is not found).
    top = _min_filter(np.where(covered, low, np.inf), EDGE)
    near = outside & ~border & np.isfinite(top)
    rim = _edge_height(np.concatenate([_up(solid), _up(collision)]), xs, ys, near)
    top = np.where(np.isfinite(rim), rim, top)
    edge = outside & np.isfinite(top) & ~border
    floor = _lowest_near(solid, xs, ys)
    hang = _lowest_near(skirt, xs, ys)
    # A face going down from the edge is a wall, unless it is one we would see from behind: then it is an open edge.
    wall = edge & (floor < top - WALL)
    wall &= ~_faces_away(solid, X, Y, wall)
    skirted = edge & ~wall & (hang < top - WALL)
    open_edge = edge & ~wall & ~skirted
    buried = skirted & (top - coarse <= BURY)
    from_cover = _distance(X, Y, covered)
    from_open = _distance(X, Y, outside)
    oz = STATIONS[2]['origin'][2]
    px0, py0, px1, py1 = PARK_PAD
    (wx0, wy), (wx1, _) = PARK_WALK
    pad = (X >= px0 - 1) & (X <= px1 + 1) & (Y >= py0 - 1) & (Y <= py1 + 1)
    walk = (X >= wx0 - 3) & (X <= PARK_BRIDGE[0][0] + .9) & (np.abs(Y - wy) <= 2.6)
    level = (pad | walk) & ~covered
    from_border = np.minimum(np.minimum(X - x0, x1 - X), np.minimum(Y - y0, y1 - Y))
    # Far from the park the foothills' relief stays, eased so its 10 m facets do not show on the patch; on the
    # border it is theirs exactly.
    relief = coarse + (_gauss(coarse, 3.) - coarse) * _smooth(from_border / 15.)
    station = _distance(X, Y, level)
    far = ~covered & (from_cover > FAR) & (station > 8.)
    deep = covered & (from_open > DEEP)
    # Pinned nodes keep `fixed`; the rest settle between their neighbours within [lo, hi].
    fixed = np.full(X.shape, np.nan)
    fixed[far] = relief[far]
    fixed[deep] = np.minimum(coarse, low - UNDER[1])[deep]
    # Where an edge runs off the patch it eases back to the foothills' ground, as it meets them past the border.
    exits = border & outside & (_distance(X, Y, edge) < 3.)
    ease = _smooth((_distance(X, Y, exits) - 2.) / (FEATHER - 2.))
    seat = coarse + (np.where(np.isfinite(top), top - np.where(buried, LEDGE, SEAT), coarse) - coarse) * ease
    fixed[open_edge | buried] = seat[open_edge | buried]
    # Under the cover by its edge the ground follows the cover's underside closely, so that from outside, at any
    # height, no gap opens under an edge into the dark under the park.
    hug = covered & (from_open <= HUG)
    cap = np.where(covered, low, np.inf) - UNDER[0]
    fixed[hug] = np.where(np.isfinite(cap), cap, fixed)[hug]
    fixed[level] = oz
    fixed[border] = coarse[border]
    lo = np.full(X.shape, -np.inf); hi = np.full(X.shape, np.inf)
    near_cover = covered & ~deep
    hi[near_cover] = (low - UNDER[0])[near_cover]
    hang_free = skirted & ~buried
    hi[hang_free | wall] = np.maximum(seat, coarse)[hang_free | wall]
    lo[wall] = np.minimum(floor + .3, seat)[wall]
    z = _solve(np.where(np.isfinite(fixed), fixed, np.clip(coarse, lo, hi)), np.isnan(fixed), lo, hi)
    # The dell under the footbridge and a gentle relief where nothing holds the ground.
    held = open_edge | buried | wall | level
    free = np.isnan(fixed) & ~covered
    give = _smooth((_distance(X, Y, held) - 1.) / 5.) * free * _smooth((from_cover - 1.) / 4.)
    (cx, cy), (rx, ry) = DELL['centre'], DELL['radius']
    dell = DELL['depth'] * np.exp(-((X - cx) / rx) ** 2 - ((Y - cy) / ry) ** 2)
    hollow = _smooth((_distance(X, Y, held & ~level) - .5) / 3.) * free
    bump = RELIEF * (mountains.noise(X, Y, 16., 61) * .7 + mountains.noise(X, Y, 7., 62) * .3)
    z = z - dell * hollow + bump * give
    z = np.where(np.isfinite(fixed), z, np.clip(z, lo, hi))
    return dict(xs=xs, ys=ys, z=z, coarse=coarse, covered=covered, outside=outside, low=low, top=top, edge=edge,
                wall=wall, skirted=skirted, buried=buried, open_edge=open_edge, level=level, walk=walk & ~covered,
                pad=pad & ~covered, from_cover=from_cover, fixed=np.isfinite(fixed), floor=floor, hang=hang,
                station=station, from_border=from_border, hang_free=hang_free)


def _solve(z, free, lo, hi, iterations=3000, omega=1.9):
    """Free nodes of z relaxed to the mean of their four neighbours (projected red-black SOR within [lo, hi])."""
    z = z.copy()
    ny, nx = z.shape
    jj, ii = np.mgrid[0:ny, 0:nx]
    colour = [free & ((ii + jj) % 2 == k) for k in (0, 1)]
    for _ in range(iterations):
        for m in colour:
            p = np.pad(z, 1, mode='edge')
            mean = .25 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:])
            z[m] += omega * (mean[m] - z[m])
            z[m] = np.clip(z[m], lo[m], hi[m])
    return z


def height(x, y, base_sampler):
    """The patch's ground at (x, y) on the same triangles as its mesh (x, y on the patch)."""
    g = grid(base_sampler)
    xs, ys, z = g['xs'], g['ys'], g['z']
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    fx = np.clip((x - xs[0]) / STEP, 0, len(xs) - 1.000001); fy = np.clip((y - ys[0]) / STEP, 0, len(ys) - 1.000001)
    i = np.minimum(fx.astype(int), len(xs) - 2); j = np.minimum(fy.astype(int), len(ys) - 2)
    u, v = fx - i, fy - j
    z00, z10, z01, z11 = z[j, i], z[j, i + 1], z[j + 1, i], z[j + 1, i + 1]
    return np.where(u >= v, z00 * (1 - u) + z10 * (u - v) + z11 * v, z00 * (1 - v) + z11 * u + z01 * (v - u))


# The look: linear albedo, as the island paints its own ground (hidamari/mountains.py colours, the village's meadow).
MEADOW = ((.155, .172, .040), (.172, .166, .046))  # the island's meadow (T_ground's mean) and a warmer, drier patch
PATH = (.25, .16, .079)             # the island's footpaths (zeppelin/build.py, hidamari/mountains.py trail_mesh)
EARTH = (.10, .085, .06)            # bare earth at the foot of walls and rock faces
CLEARING = (10., 12.)               # metres round the station and its footpath that are meadow, and the fade beyond
VERGE = (2., 7.)                    # metres of meadow along the park's edges, and their fade into the forest floor
PATH_WIDTH = 1.3                    # metres, half the footpath's width; it widens by .5 at the footbridge's head
TEXTURE = (.55, 1.)                 # how much of the ground texture the forest floor and the meadow show
GROUND = (.163, .183, .036)         # T_ground's mean (linear): M_NorthGate divides the texture by it


@lru_cache(maxsize=2)
def paint(base_sampler):
    """(rgb, amount, meadow, path) per node: the ground's linear colour, how much of the island's ground texture it
    shows (M_NorthGate), how much of it is meadow and how much footpath. On the border it is the foothills' own
    colour, untextured."""
    from hidamari import mountains
    from zeppelin.layout import PARK_WALK, PARK_BRIDGE
    g = grid(base_sampler)
    X, Y = np.meshgrid(g['xs'], g['ys'])
    n1, n2, n3 = (mountains.noise(X, Y, s, k) for s, k in ((11., 71), (4., 72), (23., 73)))
    border = _smooth((g['from_border'] - 3.) / 12.)
    clearing = 1 - _smooth((g['station'] - CLEARING[0] - 5 * n1) / CLEARING[1])
    verge = (1 - _smooth((g['from_cover'] - VERGE[0] - 2 * n3) / VERGE[1])) * .85
    meadow = np.maximum(clearing, verge) * border
    grass = np.array(MEADOW[0]) + (np.array(MEADOW[1]) - MEADOW[0]) * _smooth(.5 + n3)[..., None]
    grass = grass * (1 + .09 * n1 + .05 * n2)[..., None]
    rgb = mountains.colours(X, Y, g['z']) * (1 - meadow[..., None]) + grass * meadow[..., None]
    # The footpath from the station's door to the footbridge, soft-edged.
    (wx0, wy), _ = PARK_WALK
    x0, x1 = wx0 - 6., PARK_BRIDGE[0][0]
    along = np.clip(X, x0, x1)
    d = np.hypot(X - along, Y - wy)
    width = PATH_WIDTH + .22 * n2 + .5 * _smooth((X - x1 + 4.) / 3.)
    path = (1 - _smooth((d - width) / .8 + .5)) * border
    rgb = rgb * (1 - path[..., None]) + np.array(PATH) * (1 + .08 * n2)[..., None] * path[..., None]
    # Bare, darker earth at the foot of the park's walls and rock faces; a little contact shade where the ground
    # meets an edge.
    foot = 1 - _smooth((_distance(X, Y, g['wall'] | g['hang_free']) - .3 - .6 * n2) / 2.2)
    rgb = (rgb * (1 - .55 * foot[..., None]) + np.array(EARTH) * .55 * foot[..., None]) * (1 - .25 * foot[..., None])
    meet = 1 - _smooth((_distance(X, Y, g['open_edge'] | g['buried']) - .2) / 1.5)
    rgb = rgb * (1 - .12 * meet[..., None])
    rgb[g['covered']] = EARTH
    amount = (TEXTURE[0] + (TEXTURE[1] - TEXTURE[0]) * meadow) * (1 - .7 * path) * (1 - .5 * foot) * border
    return rgb, amount, meadow, path


def mesh(base_sampler):
    """The patch as a mesh: {vertices (n, 3), faces (m, 3), colours (n, 4) linear RGB and texture amount, normals
    (n, 3)}, on the triangles height() samples. Its normals see the park's cover as ground at the edge's height, so
    the ground does not shade as if it fell away under the park's edges."""
    g = grid(base_sampler)
    rgb, amount, _, _ = paint(base_sampler)
    xs, ys, z = g['xs'], g['ys'], g['z']
    X, Y = np.meshgrid(xs, ys)
    seen = np.where(g['covered'] & np.isfinite(g['low']), g['low'] - SEAT, z)
    dy, dx = np.gradient(seen, STEP)
    normals = np.stack([-dx, -dy, np.ones_like(z)], -1)
    normals /= np.linalg.norm(normals, axis=-1)[..., None]
    ny, nx = z.shape
    a = (np.arange(ny - 1)[:, None] * nx + np.arange(nx - 1)[None, :]).ravel()
    faces = np.concatenate([np.stack([a, a + 1, a + nx + 1], 1), np.stack([a, a + nx + 1, a + nx], 1)])
    return dict(vertices=np.stack([X, Y, z], -1).reshape(-1, 3), faces=faces,
                colours=np.concatenate([rgb, amount[..., None]], -1).reshape(-1, 4), normals=normals.reshape(-1, 3))


def _at(field, x, y, xs, ys):
    """field bilinear at (x, y)."""
    fx = np.clip((x - xs[0]) / STEP, 0, len(xs) - 1.000001); fy = np.clip((y - ys[0]) / STEP, 0, len(ys) - 1.000001)
    i, j = fx.astype(int), fy.astype(int); u, v = fx - i, fy - j
    f = field.astype('f8')
    return (f[j, i] * (1 - u) + f[j, i + 1] * u) * (1 - v) + (f[j + 1, i] * (1 - u) + f[j + 1, i + 1] * u) * v


# The patch's dressing (dress()), like the concept assets/megapark/concepts/gate-ground: grass tufts on the meadow and
# thick along the park's edges, fallen leaves, ochre and green bushes where the meadow meets the forest and in clumps
# along the park's edges (low between the footbridge and the hillside, which reads from the bridge), and the park's
# stone (ROCKS) at the foot of its walls, among the edge's bushes and here and there in the grass.
ROCKS = {'HD_NorthRockA': (36, (1.8, 1.4, 1.0)), 'HD_NorthRockB': (37, (1.1, .9, .7)),
         'HD_NorthRockC': (38, (2.6, 2., 1.3))}
STONE = (.2, .19, .18)              # the park's rock as it reads in the island's light (its texture is grey-violet)
LICHEN = (.13, .14, .09)
BUSHES = (('Bush_Ochre_A', .3), ('Bush_Ochre_B', .25), ('Bush_Green_A', .2), ('Bush_Green_B', .1),
          ('Bush_Flower_A', .15))
VIEW = (-215., 1446., -150., 1474.)  # between the footbridge and the hillside: low bushes only, few
SEED = 1400


def rock(seed, size):
    """[(points, colour)]: a low-poly boulder shaped like the island's (build_assets.py rock, same seeds) in the park's
    stone, darker underneath, with lichen on some of its upper faces."""
    import math
    import random
    rng = random.Random(seed)
    sx, sy, sz = size
    rings = []
    for j in range(4):
        t = (j + .5) / 4; zz = (t - .15) * sz; rr = math.sin(math.pi * min(1., t * 1.1)) * .5 + .2
        rings.append([(math.cos(a) * sx * rr * rng.uniform(.8, 1.2), math.sin(a) * sy * rr * rng.uniform(.8, 1.2),
                       zz + rng.uniform(-.05, .05) * sz) for a in [2 * math.pi * i / 7 for i in range(7)]])
    shade = random.Random(seed + 100)

    def colour(level):
        c = (np.array(LICHEN if level >= 2 and shade.random() < .35 else STONE) * (.88 + .05 * level)
             * shade.uniform(.93, 1.07))
        return tuple(float(v) for v in c)
    polys = []
    for j in range(3):
        for i in range(7):
            polys.append(([rings[j][i], rings[j][(i + 1) % 7], rings[j + 1][(i + 1) % 7], rings[j + 1][i]], colour(j)))
    top = (0., 0., sz * .9)
    for i in range(7):
        polys.append(([rings[3][i], rings[3][(i + 1) % 7], top], colour(3)))
    return polys


def dress(instances, base_sampler):
    """Replace the undergrowth on the patch with its own (see ROCKS): `instances` maps names to [[x, y, z, yaw,
    scale], ...] in island metres. Returns {name: count} added."""
    from megapark.plants import MESHES
    from zeppelin.layout import PARK_WALK, PARK_BRIDGE
    g = grid(base_sampler)
    _, _, meadow, path = paint(base_sampler)
    xs, ys = g['xs'], g['ys']
    for name in list(instances):
        if not instances[name] or not (name.startswith(('Bush', 'Grass', 'Litter', 'Rock', 'HD_NorthRock'))
                                       or name == 'Tree_Maple_B'):
            continue
        a = np.asarray(instances[name], 'f8').reshape(-1, 5)
        drop = inside(a[:, 0], a[:, 1]) & ((a[:, 4] < .6) if name == 'Tree_Maple_B' else True)
        instances[name] = a[~drop].tolist()
    rng = np.random.default_rng(SEED)
    x0, y0, x1, y1 = GATE
    (wx0, wy), _ = PARK_WALK
    b0, b1 = PARK_BRIDGE[0][0], PARK_BRIDGE[1][0]
    done = {}

    def candidates(spacing):
        gx, gy = np.meshgrid(np.arange(x0 + 1, x1 - 1, spacing), np.arange(y0 + 1, y1 - 1, spacing))
        p = np.stack([gx.ravel(), gy.ravel()], 1) + rng.uniform(-.45, .45, (gx.size, 2)) * spacing
        f = {k: _at(v, p[:, 0], p[:, 1], xs, ys)
             for k, v in (('meadow', meadow), ('path', path), ('cover', g['from_cover']), ('station', g['station']))}
        f['z'] = height(p[:, 0], p[:, 1], base_sampler)
        f['bridge'] = (p[:, 0] > b0 - 1.) & (p[:, 0] < b1 + .5) & (np.abs(p[:, 1] - wy) < 1.6)
        f['patch'] = (.5 + .5 * np.sin(p[:, 0] * .21 + np.sin(p[:, 1] * .17) * 2.)
                      * np.sin(p[:, 1] * .19 + np.sin(p[:, 0] * .13)))
        return p, f

    def put(name, q, z, scale):
        instances.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]), 3), round(float(z), 3),
                                               round(float(rng.uniform(0, 360)), 1), round(float(scale), 3)])
        done[name] = done.get(name, 0) + 1
    # Grass: thick on the meadow, a few under the trees, none on the path, the station's pad or under the bridge's ends.
    p, f = candidates(.85)
    keep = ((rng.random(len(p)) < (.8 * f['meadow'] * (.45 + .55 * f['patch']) + .1) * (1 - f['path']))
            & (f['cover'] > .5) & (f['station'] > 1.) & ~f['bridge'])
    for q, z in zip(p[keep], f['z'][keep]):
        put(('Grass_A', 'Grass_B')[rng.integers(2)], q, z - .08, rng.uniform(.7, 1.2))
    # A grass verge along every edge the ground meets, where the road and the rock end.
    X, Y = np.meshgrid(xs, ys)
    edge = g['open_edge'] | g['buried']
    q = np.stack([X[edge], Y[edge]], 1) + rng.uniform(-.5, .5, (int(edge.sum()), 2))
    cover = _at(g['from_cover'], q[:, 0], q[:, 1], xs, ys)
    ok = ((cover > .35) & (rng.random(len(q)) < .75)
          & ~((q[:, 0] > b0 - 1.) & (q[:, 0] < b1 + .5) & (np.abs(q[:, 1] - wy) < 1.6)))
    for r, z in zip(q[ok], height(q[ok, 0], q[ok, 1], base_sampler)):
        put(('Grass_A', 'Grass_B')[rng.integers(2)], r, z - .08, rng.uniform(.8, 1.3))
    # Fallen leaves everywhere, fewer on the path.
    p, f = candidates(2.)
    keep = (rng.random(len(p)) < .45 * (1 - .6 * f['path'])) & (f['cover'] > .3) & ~f['bridge']
    for q, z in zip(p[keep], f['z'][keep]):
        put('Litter', q, z + .02, rng.uniform(.9, 1.4))
    # Bushes where the meadow gives way to the forest, a few under the trees; few and low between the bridge and the
    # hillside; none on the path, the pad, or within 3.5 m of the footpath's line.
    p, f = candidates(2.6)
    m = f['meadow']
    view = (p[:, 0] > VIEW[0]) & (p[:, 0] < VIEW[2]) & (p[:, 1] > VIEW[1]) & (p[:, 1] < VIEW[3])
    want = (2.4 * m * (1 - m) + .12 * (1 - m)) * (.3 + .7 * f['patch']) * np.where(view, .25, 1.)
    keep = ((rng.random(len(p)) < want) & (f['path'] < .05) & (f['station'] > 3.) & (f['cover'] > 1.2)
            & ~((p[:, 0] > wx0 - 8) & (p[:, 0] < b1 + 2) & (np.abs(p[:, 1] - wy) < 3.5)))
    names, weights = zip(*BUSHES)
    for q, z, low, cover in zip(p[keep], f['z'][keep], view[keep], f['cover'][keep]):
        name = names[rng.choice(len(names), p=np.array(weights) / sum(weights))]
        scale = rng.uniform(.6, .9) if low else rng.uniform(.75, 1.3)
        put(name, q, z - .15, min(scale, (cover - .6) / MESHES[name][1]))

    # Along the park's edges, like the concept's wall foot: clumps of bushes a metre or two out from where the ground
    # meets the road, the rock and the walls (low between the footbridge and the hillside), sized to keep off the
    # road, with grass and rocks among them; none by the footbridge's ends, on the path or the pad.
    def clear(p, f):
        return ((f['path'] < .05) & (f['station'] > 3.)
                & ~((p[:, 0] > b0 - 3.) & (p[:, 0] < b1 + 1.) & (np.abs(p[:, 1] - wy) < 3.2)))
    p, f = candidates(1.7)
    view = (p[:, 0] > VIEW[0]) & (p[:, 0] < VIEW[2]) & (p[:, 1] > VIEW[1]) & (p[:, 1] < VIEW[3])
    keep = clear(p, f) & (f['cover'] > 1.5) & (f['cover'] < 3.3) & (rng.random(len(p)) < .55 * (.3 + .7 * f['patch']))
    for q, z, low, cover in zip(p[keep], f['z'][keep], view[keep], f['cover'][keep]):
        name = names[rng.choice(len(names), p=np.array(weights) / sum(weights))]
        scale = rng.uniform(.5, .75) if low else rng.uniform(.65, 1.05)
        put(name, q, z - .15, min(scale, (cover - .6) / MESHES[name][1]))
    p, f = candidates(.8)
    keep = (clear(p, f) & (f['cover'] > .5) & (f['cover'] < 3.5)
            & (rng.random(len(p)) < .5 * (.4 + .6 * f['patch'])))
    for q, z in zip(p[keep], f['z'][keep]):
        put(('Grass_A', 'Grass_B')[rng.integers(2)], q, z - .08, rng.uniform(.8, 1.3))
    # Rocks at the foot of the park's walls and rock faces, along its edges (sized to keep off the road) and a few in
    # the grass; a third of each rock's height is under the ground.
    taken = []

    def place(q, chance, gap):
        for r in q[rng.permutation(len(q))]:
            if rng.random() < chance and all(np.hypot(*(r - o)) > gap for o in taken):
                taken.append(r)
    foot = g['wall'] | g['hang_free']
    place(np.stack([X[foot], Y[foot]], 1), .35, 2.5)
    walls = len(taken)
    p, f = candidates(1.5)
    place(p[clear(p, f) & (f['cover'] > 1.4) & (f['cover'] < 2.8)], .45, 3.)
    p, f = candidates(11.)
    keep = ((rng.random(len(p)) < .35 * f['meadow']) & (f['path'] < .05) & (f['station'] > 2.) & (f['cover'] > 2.)
            & ~f['bridge'])
    place(p[keep], 1., 3.5)
    taken = np.array(taken).reshape(-1, 2)
    names = sorted(ROCKS)
    cover = _at(g['from_cover'], taken[:, 0], taken[:, 1], xs, ys)
    ix = np.rint((taken[:, 0] - xs[0]) / STEP).astype(int); iy = np.rint((taken[:, 1] - ys[0]) / STEP).astype(int)
    for k, (r, z) in enumerate(zip(taken, height(taken[:, 0], taken[:, 1], base_sampler))):
        name = names[rng.integers(len(names))]
        size = ROCKS[name][1]
        # .6 of a rock's height shows; one against a wall stays .3 m under its top, any other keeps off the cover.
        most = (g['top'][iy[k], ix[k]] - z - .3) / (.6 * size[2]) if k < walls else (cover[k] - .4) / (.7 * size[0])
        scale = min(rng.uniform(.4, .9), most)
        if scale >= .3:
            put(name, r, z - .3 * size[2] * scale, scale)
    return done
