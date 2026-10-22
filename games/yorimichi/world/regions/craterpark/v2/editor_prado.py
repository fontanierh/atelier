"""The Prado bowl as a boost zone (owner, 2026-10-16: "the prado bowl to be entirely boost walls", in high quality).

Its painting (editor_decal: one 1024x1536 image laid over the whole 95 m by 180 m bowl from above) gave about 12 cm a
texel on the floor and three to four times that down the walls: soft up close. A boosted decal bowl drops it for
graphics cut into the mesh, as sharp as the geometry at any distance (editor_boost's approach):

- its walls (every riding face that is not floor) take the sunburst, editor_boost.BIG_RAYS rays round its floor's centre,
  up to a gold coping;
- its floor keeps the Prado's design, redrawn: the gold sun and ring at the sunburst's centre (editor_boost.paint), the
  PRADO letters, and wave bands following the foot of every wall and spine, teal then navy with a thin orange line, on
  poured concrete.

The sun goes on the most open level floor, and the letters in a LETTERS box (metres) on the open level floor beside it
(plan). The box sits on the floor's 4 m concrete tiles (editor_generate.tile_uv), so its texture (tools/
craterpark_textures.py letters: the same concrete tiled under navy letters, about 4 mm a texel) carries the floor's grain
straight across its edges.

The bands are cut along iso-lines of each floor vertex's plan distance to the walls' foot. The floor's 3 m cells are
split finer within reach of the bands first (FINE), so the cut lines follow the walls' curves closely.
"""
import numpy as np

from . import editor_boost

TEAL = 'material_054'      # deep teal lacquer over the bowl's concrete (tools/craterpark_textures.py BOOST_PAINTS)
NAVY = 'material_055'      # navy lacquer
ORANGE = 'material_056'    # warm orange lacquer
MAGENTA = 'material_057'   # the sunburst's lacquers over concrete, not the ramps' boards (editor_boost's)
YELLOW = 'material_058'
SUN = 'material_059'
LETTERS = 'material_060'   # the PRADO letters on the concrete (one 8192x2048 texture over the LETTERS box)
PAINTS = (TEAL, NAVY, ORANGE, MAGENTA, YELLOW, SUN, LETTERS)
BOX = (32., 8.)            # metres: the letters' box, along and across its reading line, on the 4 m tiles
TILE = 4.
CLEAR = 4.5                # metres the box and the sun keep from the walls' foot (past the bands)
GRID = 1.                  # metres between the plan's samples of the floor
READ = (1, 1)              # the shipped design's box (plan: 'along', 'side'), for which the letters' texture lays its
                           # concrete as the floor's (tools/craterpark_textures.py letters; the tests check plan's)
LEVEL = .05                # metres: the most the floor under the sun or the box may rise or fall
# metres from the walls' foot: (inner edge, material) of each band, outermost first; the concrete floor beyond the last
BANDS = ((0., TEAL), (1.6, NAVY), (3.2, ORANGE), (3.6, None))
FINE = 1.             # metres: the floor's faces within the bands' reach are split until no edge is longer
FLAT = editor_boost.FLAT


def _foot(V, F, floor):
    """Plan points along the walls' foot: the edges a floor face shares with a face that is not floor, sampled
    every 0.25 m."""
    edges = {}
    for f, tri in enumerate(F):
        for i in range(3):
            key = (min(tri[i], tri[(i + 1) % 3]), max(tri[i], tri[(i + 1) % 3]))
            edges.setdefault(key, []).append(floor[f])
    pts = []
    for (a, b), who in edges.items():
        if any(who) and not all(who):
            p, q = V[a, [0, 2]], V[b, [0, 2]]
            n = max(1, int(np.ceil(np.linalg.norm(q - p) / .25)))
            pts.extend(p + (q - p) * t for t in np.linspace(0., 1., n + 1))
    return np.array(pts) if pts else np.zeros((0, 2))


def _distance(P, foot, cell=2., reach=6.):
    """Each plan point's distance to the nearest foot point, exact within `reach` (np.inf beyond): the foot points are
    bucketed in `cell` m squares and each point searches the squares within reach (the repo has no scipy)."""
    out = np.full(len(P), np.inf)
    if not len(foot) or not len(P):
        return out
    key = lambda Q: np.floor(Q / cell).astype(np.int64)
    fk = key(foot)
    buckets = {}
    for i, (a, b) in enumerate(fk):
        buckets.setdefault((a, b), []).append(i)
    n = int(np.ceil(reach / cell))
    pk = key(P)
    order = np.lexsort((pk[:, 1], pk[:, 0]))
    cells, start = np.unique(pk[order], axis=0, return_index=True)
    for (a, b), s0, s1 in zip(cells, start, np.r_[start[1:], len(order)]):
        near = [j for da in range(-n, n + 1) for db in range(-n, n + 1) for j in buckets.get((a + da, b + db), ())]
        if not near:
            continue
        idx = order[s0:s1]
        d = ((P[idx, None, :] - foot[None, near, :]) ** 2).sum(-1).min(1)
        out[idx] = np.sqrt(d)
    return out


def _refine(V, N, F, mask, parent):
    """Split the faces in `mask` with an edge longer than FINE at their edges' midpoints (shared, so neighbours stay
    joined), again until none is; the T-junctions left against the faces not split are split later
    (tjunction.fix_tjunctions)."""
    V, N = np.asarray(V, 'f8'), np.asarray(N, 'f8')
    for _ in range(6):
        e = np.linalg.norm(V[F] - V[np.roll(F, -1, 1)], axis=2).max(1)
        split = mask & (e > FINE)
        if not split.any():
            break
        n0 = len(V)
        new_V, new_N = [], []
        mid, out, owner = {}, [], []

        def m(a, b):
            key = (min(a, b), max(a, b))
            if key not in mid:
                new_V.append((V[a] + V[b]) / 2); new_N.append((N[a] + N[b]) / 2); mid[key] = n0 + len(new_V) - 1
            return mid[key]
        for f in np.flatnonzero(split):
            a, b, c = int(F[f, 0]), int(F[f, 1]), int(F[f, 2])
            ab, bc, ca = m(a, b), m(b, c), m(c, a)
            out += [[a, ab, ca], [ab, b, bc], [ca, bc, c], [ab, bc, ca]]
            owner += [parent[f]] * 4
        if new_V:
            V = np.concatenate([V, np.array(new_V, 'f8')])
            N = np.concatenate([N, np.array(new_N, 'f8')])
        F = np.concatenate([F[~split], np.array(out, 'i8')])
        parent = np.concatenate([parent[~split], np.array(owner, 'i8')])
        mask = np.r_[mask[~split], np.ones(len(out), bool)]
    return V, N, F, parent


def _level(V, F, flat):
    """The level floor sampled on a GRID m plan grid: (P (n, 2) plan points, y (n,)), each point inside a flat face."""
    T = V[F[flat]]
    P, Y = [], []
    lo, hi = np.floor(T[:, :, [0, 2]].min(1) / GRID), np.ceil(T[:, :, [0, 2]].max(1) / GRID)
    for t, a, b in zip(T, lo, hi):
        gx, gz = np.meshgrid(np.arange(a[0], b[0] + 1) * GRID, np.arange(a[1], b[1] + 1) * GRID)
        q = np.c_[gx.ravel(), gz.ravel()]
        (x0, z0), (x1, z1), (x2, z2) = t[:, [0, 2]]
        det = (z1 - z2) * (x0 - x2) + (x2 - x1) * (z0 - z2)
        if abs(det) < 1e-12:
            continue
        l0 = ((z1 - z2) * (q[:, 0] - x2) + (x2 - x1) * (q[:, 1] - z2)) / det
        l1 = ((z2 - z0) * (q[:, 0] - x2) + (x0 - x2) * (q[:, 1] - z2)) / det
        l2 = 1 - l0 - l1
        inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
        P.append(q[inside]); Y.append(l0[inside] * t[0, 1] + l1[inside] * t[1, 1] + l2[inside] * t[2, 1])
    P, Y = np.concatenate(P), np.concatenate(Y)
    _, keep = np.unique(np.round(P / GRID).astype(np.int64), axis=0, return_index=True)
    return P[keep], Y[keep]


def _far(P, foot):
    """Each plan point's distance to the nearest foot point (exact, chunked)."""
    out = np.empty(len(P))
    for a in range(0, len(P), 512):
        out[a:a + 512] = np.sqrt(((P[a:a + 512, None] - foot[None]) ** 2).sum(-1).min(1))
    return out


def _window(G, offsets, how):
    """`how` (np.minimum or np.maximum) of the grid G over each cell's `offsets` (cells, (dj, di)); +-inf off it."""
    fill = np.inf if how is np.minimum else -np.inf
    k = max(max(abs(dj), abs(di)) for dj, di in offsets)
    pad = np.pad(G, k, constant_values=fill)
    return how.reduce([pad[k + dj:k + dj + G.shape[0], k + di:k + di + G.shape[1]] for dj, di in offsets])


def plan(V, N, F, cls, ride=0):
    """Where the boosted Prado's sun and letters go: (centre (x, z), box). Both sit on level floor (within LEVEL m),
    at least CLEAR from the walls' foot: the sun's centre where its disc is farthest from the foot; the box {'x0', 'z0',
    'along': 0 (x) or 1 (z), 'side'} is the BOX on TILE m tiles, CLEAR from the sun too, as far from both as can be.
    Its 'side' (+1 or -1, across the line) is where the letters are read from (box_uv): the side with more floor."""
    flat = (N[F][:, :, 1] > FLAT).all(1) & (cls == ride)
    foot = _foot(V, F, flat)
    P, Y = _level(V, F, flat)
    lo = np.floor(P.min(0) / TILE) * TILE
    ij = np.round((P - lo) / GRID).astype(int)
    shape = tuple(ij.max(0)[::-1] + 1)

    def grid(vals, fill):
        G = np.full(shape, fill)
        G[ij[:, 1], ij[:, 0]] = vals
        return G
    hi_y, lo_y, d = grid(Y, -np.inf), grid(Y, np.inf), grid(_far(P, foot), -np.inf)
    r = int(np.ceil((editor_boost.SUN_RADIUS + .5) / GRID))
    disc = [(dj, di) for dj in range(-r, r + 1) for di in range(-r, r + 1) if dj * dj + di * di <= r * r]
    level = _window(hi_y, disc, np.maximum) - _window(lo_y, disc, np.minimum) <= LEVEL
    room = np.where(level, d - editor_boost.SUN_RADIUS, -np.inf)
    j, i = np.unravel_index(room.argmax(), shape)
    centre = lo + np.array([i, j]) * GRID
    sun = np.hypot(*np.meshgrid((np.arange(shape[1]) - i) * GRID, (np.arange(shape[0]) - j) * GRID)) \
        - editor_boost.SUN_RADIUS
    clear = np.minimum(d, sun)
    best = None
    for along in (0, 1):
        n = (np.array(BOX if along == 0 else BOX[::-1]) / GRID).astype(int)
        rows = [(dj, 0) for dj in range(n[1] + 1)]
        cols = [(0, di) for di in range(n[0] + 1)]
        c = _window(_window(np.where(np.isfinite(hi_y), clear, -np.inf), rows, np.minimum), cols, np.minimum)
        box_hi = _window(_window(hi_y, rows, np.maximum), cols, np.maximum)
        box_lo = _window(_window(lo_y, rows, np.minimum), cols, np.minimum)
        flat_box = box_hi - box_lo <= LEVEL
        step = int(TILE / GRID)
        c = np.where(flat_box, c, -np.inf)[::step, ::step]       # origins on the tiles
        jb, ib = np.unravel_index(c.argmax(), c.shape)
        if c[jb, ib] >= CLEAR and (best is None or c[jb, ib] > best[0]):
            best = (c[jb, ib], {'x0': float(lo[0] + ib * TILE), 'z0': float(lo[1] + jb * TILE), 'along': along})
    if best is None:
        return centre, None
    box = best[1]
    size = np.array(BOX if box['along'] == 0 else BOX[::-1])
    mid = np.array([box['x0'], box['z0']]) + size / 2
    across = 1 - box['along']
    box['side'] = 1 if (P[:, across] > mid[across]).sum() > (P[:, across] < mid[across]).sum() else -1
    return centre, box


def box_uv(V, box):
    """The letters' UVs over their box: u left to right along the reading line (0 to 1), v down the letters to their
    baseline (1: rows run down the image, as editor_generate.tile_uv's, the export flipping them to Blender's), the edge
    on the reader's side (box['side'] along the axis across the line). Plan (x, z) with y up is right-handed: facing +z
    the reader's right is -x; facing +x it is +z."""
    size = np.array(BOX if box['along'] == 0 else BOX[::-1])
    t = (V[:, [0, 2]] - [box['x0'], box['z0']]) / size
    a, c = box['along'], 1 - box['along']
    v = 1 - t[:, c] if box['side'] < 0 else t[:, c]
    u = t[:, a] if (box['side'] < 0) == (a == 1) else 1 - t[:, a]
    return np.c_[u, v]


def floor(V, N, F, cls, paint, sun, ride=0, box=None):
    """The boosted Prado's floor redrawn (editor_boost.paint's output in, the same out): its floor faces outside the
    sun lose the rays and take the wave bands on concrete, and the letters in `box` (plan). Returns (V, N, F, cls,
    paint)."""
    from .tjunction import fix_tjunctions
    flat = (N[F][:, :, 1] > FLAT).all(1) & (cls == ride)
    foot = _foot(V, F, flat)
    if not len(foot):
        return V, N, F, cls, paint
    reach = BANDS[-1][0] + FINE
    near = flat & (_distance(V[F].mean(1)[:, [0, 2]], foot) < reach + 2 * FINE)
    parent = np.arange(len(F))
    V, N, F, parent = _refine(V, N, F, near, parent)
    for edge, _ in BANDS[1:]:
        field = np.minimum(_distance(V[:, [0, 2]], foot), 1e3) - edge
        V, F, N, parent = editor_boost._cut(V, F, N, parent, field, lambda a, b: field[a] / (field[a] - field[b]),
                                            faces=flat[parent])
    if box is not None:
        size = np.array(BOX if box['along'] == 0 else BOX[::-1])
        lo = np.array([box['x0'], box['z0']])
        for axis, at in ((0, lo[0]), (0, lo[0] + size[0]), (1, lo[1]), (1, lo[1] + size[1])):
            field = V[:, 2 * axis] - at
            P = V[F].mean(1)[:, [0, 2]]
            near = flat[parent] & (P > lo - TILE).all(1) & (P < lo + size + TILE).all(1)
            V, F, N, parent = editor_boost._cut(V, F, N, parent, field, lambda a, b: field[a] / (field[a] - field[b]),
                                                faces=near)
    cls = cls[parent]
    # keep each class's faces conforming (the refinement and cuts leave T-junctions against untouched faces)
    out, keep = [], []
    for c in np.unique(cls):
        V, Fc, _, N = fix_tjunctions(V, F[cls == c], attrs=N)
        out.append(Fc); keep.append(np.full(len(Fc), c))
    F, cls = np.concatenate(out), np.concatenate(keep)
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return V, N, F, cls, paints(V, N, F, cls, sun, foot, ride, box)


def paints(V, N, F, cls, sun, foot, ride=0, box=None):
    """Each face's paint from where it lies: on the floor the sun, its ring, the letters, the bands or None
    (concrete); on the walls the sunburst's rays; None off the riding faces."""
    import math
    c = V[F].mean(1)
    flat = (N[F][:, :, 1] > FLAT).all(1)
    P = c[:, [0, 2]] - sun['centre']
    r = np.linalg.norm(P, axis=1)
    k = np.floor(((np.arctan2(P[:, 1], P[:, 0]) - sun['start']) % (2 * math.pi)) / sun['width']).astype(int)
    rays = np.where(k % 2 == 0, MAGENTA, YELLOW)
    d = _distance(c[:, [0, 2]], foot)
    band = np.full(len(F), None, object)
    for (lo, mat), (hi, _) in zip(BANDS, BANDS[1:]):
        band[(d >= lo) & (d < hi)] = mat
    if box is not None:
        size = np.array(BOX if box['along'] == 0 else BOX[::-1])
        q = c[:, [0, 2]] - [box['x0'], box['z0']]
        band[(q > 0).all(1) & (q < size).all(1)] = LETTERS
    on_floor = np.where(r < sun['radius'] - editor_boost.RING, SUN,
                        np.where(r < sun['radius'], editor_boost.GOLD, band))
    return np.where(cls == ride, np.where(flat, on_floor, rays), None)
