"""A decal bowl's riding faces and deck (editor_generate.DECALS: the Prado bowl), laid so nothing smears at its rim.

The bowl's painting (tools/craterpark_textures.py DECALS) is painted on its plan, from straight above. Laid from above
(editor_generate.decal_uv) on every face, its steep walls took one texel row for metres of wall (0 texels per metre
down a vert): the painted tile band along the rim smeared into orange streaks four to six metres tall, and the deck's
outer edge took the painting's black surround. So:

- the deck is poured concrete (dsl.CONCRETE, world-projected tiles), under the brick coping's back edge;
- the top BAND metres of wall under the main lip are a real tile band (TILE: the glazed terracotta tiles, laid along
  the lip and down the wall in square tiles), sliced out of the wall along that exact line;
- below it the painting goes on, laid down the wall: a wall vertex takes the plan point that is as far in from the lip
  as its place between the tile band (the painting's own tile band's inner edge, PAINTED_BAND in) and the wall's foot
  (the floor's own plan point), measured along the wall. The fall line is stretched evenly (about 3 to 4 times on
  this bowl's walls, never the old hundreds), and the floor keeps its plan exactly, so the graphics' layout is the
  painting's.
A spine's walls (any lip but the longest) take the same lay-down from SPINE_LINE in, with no tile band.

The editor floor's 3 m cells end on points along the walls' foot edges that the walls do not have (pieces.js
heightFloor): those T-junctions are split first (tjunction.fix_tjunctions), so the floor and walls share every vertex.
"""
import heapq

import numpy as np

from . import dsl, editor_coping, tjunction

BAND = .9             # metres of wall under the main lip in the tile band (the brick coping's face hides its top .3 m)
TILE = 'material_007'   # glazed terracotta tiles with a bullnose row (r4's tile_edge, tools/craterpark_textures.py)
TILE_SPAN = 1.8       # metres the tile texture spans along the lip (six 0.3 m tiles)
TILE_HEIGHT = .9      # metres it spans down the wall (its 2:1 frame)
TILE_FROM = .3        # metres under the lip where its top row starts, under the brick coping's face
PAINTED_BAND = 3.6    # plan metres in from the lip where the painting's own tile band ends (its 90th percentile)
# the least plan metres of painting per metre down a wall (at most 6:1): a wall too short for the painting from
# PAINTED_BAND to its foot at that rate (rev 107's 4.8 m walls: 0.8 m of plan over 6.4 m of wall) starts nearer the lip
LAID_MIN = 1 / 6
SPINE_LINE = .5       # plan metres from a spine's lip that the painting draws as the spine
SMOOTH = 3.           # metres of lip over which the directions wall points are pushed along are averaged
FIN = .3              # an up-facing floor face standing steeper than this (|n.y|) is a fin (_flip_fins)
FLAT = .98            # a vertex whose normal is this close to up is floor (or the last, near-flat row of a wall)
DECK_TILE = 4.        # metres per concrete tile on the deck (editor_generate.tile_uv)
WELD = 1e-3


def _graph(V, F):
    """Welded ids per vertex and the undirected edges between them."""
    _, ids = np.unique(np.round(V / WELD).astype('i8'), axis=0, return_inverse=True)
    ids = ids.ravel()
    E = ids[np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])]
    E = np.unique(np.sort(E[E[:, 0] != E[:, 1]], 1), axis=0)
    return ids, E


def _dijkstra(n, E, w, sources):
    """Shortest path lengths over the edges E (k, 2) of weights w from the source nodes (inf where unreached)."""
    adj = [[] for _ in range(n)]
    for (a, b), x in zip(E.tolist(), w.tolist()):
        adj[a].append((b, x))
        adj[b].append((a, x))
    d = np.full(n, np.inf)
    heap = [(0., int(s)) for s in np.unique(sources)]
    for _, s in heap:
        d[s] = 0.
    heapq.heapify(heap)
    while heap:
        ds, a = heapq.heappop(heap)
        if ds > d[a]:
            continue
        for b, x in adj[a]:
            if ds + x < d[b]:
                d[b] = ds + x
                heapq.heappush(heap, (ds + x, b))
    return d


def _smooth(P, D, closed, sigma=SMOOTH):
    """The lip's `into` directions D (k, 2) averaged along it (a Gaussian of `sigma` metres of arc length), so pushing
    wall points along them fans out evenly round a corner instead of at the corner's own column."""
    seg = np.linalg.norm(np.diff(np.vstack([P, P[:1]]) if closed else P, axis=0), axis=1)
    run = np.r_[0., np.cumsum(seg)]
    total = run[-1]
    x = run[:len(P)]
    d = x[:, None] - x[None]
    if closed:
        d = (d + total / 2) % total - total / 2
    ds = (seg + np.roll(seg, 1)) / 2 if closed else np.r_[seg[0] / 2, (seg[1:] + seg[:-1]) / 2, seg[-1] / 2]
    w = np.exp(-.5 * (d / sigma) ** 2) * ds[None, :len(P)]      # each point weighs the arc it stands for
    out = w @ D
    return out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-9)


def _project(Q, lip, into, closed):
    """For plan points Q (n, 2): plan distance to the lip polyline, the lip's `into` there (unit, plan, smoothed along
    the lip) and the arc length along the lip there."""
    P = np.asarray(lip, 'f8')[:, [0, 2]]
    D = _smooth(P, np.asarray(into, 'f8')[:, [0, 2]], closed)
    if closed:
        P, D = np.vstack([P, P[:1]]), np.vstack([D, D[:1]])
    A, B = P[:-1], P[1:]
    run = np.r_[0., np.cumsum(np.linalg.norm(B - A, axis=1))]
    best = np.full(len(Q), np.inf)
    out_d, out_u = np.zeros((len(Q), 2)), np.zeros(len(Q))
    for a in range(0, len(Q), 2048):
        q = Q[a:a + 2048]
        ab = B - A
        t = np.clip(((q[:, None] - A[None]) * ab[None]).sum(2) / np.maximum((ab * ab).sum(1), 1e-12)[None], 0, 1)
        X = A[None] + t[..., None] * ab[None]
        dist = np.linalg.norm(q[:, None] - X, axis=2)
        k = dist.argmin(1)
        r = np.arange(len(q))
        tk = t[r, k]
        best[a:a + 2048] = dist[r, k]
        d = (1 - tk)[:, None] * D[k] + tk[:, None] * D[k + 1]
        out_d[a:a + 2048] = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        out_u[a:a + 2048] = run[k] + tk * (run[k + 1] - run[k])
    return best, out_d, out_u, run[-1]


def _slice(V, F, X, field, level):
    """Split the faces (V, F) along field == level: a vertex on each crossed edge (shared by both faces on it, the
    per-vertex attributes X and the field interpolated), each side fanned in its winding. Returns (V, F, X, field)."""
    V, X, field = list(V), list(X), list(field)
    made, out = {}, []
    side = np.sign(np.asarray(field) - level)
    side[np.abs(np.asarray(field) - level) < 1e-9] = 0

    def cut(a, b):
        key = (min(a, b), max(a, b))
        if key not in made:
            t = (level - field[a]) / (field[b] - field[a])
            V.append(V[a] + t * (V[b] - V[a]))
            X.append(X[a] + t * (X[b] - X[a]))
            field.append(level)
            made[key] = len(V) - 1
        return made[key]

    for tri in F.tolist():
        s = side[tri]
        if not ((s > 0).any() and (s < 0).any()):
            out.append(tri)
            continue
        for keep in (1, -1):              # the polygon on each side, walked in the face's winding
            poly = []
            for i in range(3):
                a, b = tri[i], tri[(i + 1) % 3]
                if side[a] == keep or side[a] == 0:
                    poly.append(a)
                if side[a] * side[b] < 0:
                    poly.append(cut(a, b))
            out += [[poly[0], poly[j], poly[j + 1]] for j in range(1, len(poly) - 1)]
    return np.array(V), np.array(out, 'i8'), np.array(X), np.array(field)


def _flip_fins(V, F, N):
    """Flip the floor's fins away: a face whose corners all face up but that stands on edge (the editor's floor grid
    clipped a line 2 mm from a wall foot: three points in a row in plan, 5 cm apart in height) is flipped with the face
    across its longest plan edge, so the floor bends over that step instead of standing a sliver up on it (which takes
    no texels from above)."""
    F = F.copy()
    key = np.round(V / WELD).astype('i8')
    for _ in range(4):
        t = V[F]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        up = (N[F][:, :, 1] > FLAT).all(1)
        fins = np.flatnonzero(up & (np.abs(n[:, 1]) < FIN * np.linalg.norm(n, axis=1)))
        if not len(fins):
            break
        edges = {}
        for f, tri in enumerate(F.tolist()):
            for i in range(3):
                edges[(tuple(key[tri[i]]), tuple(key[tri[(i + 1) % 3]]))] = (f, i)
        done = set()
        for f in fins:
            if f in done:
                continue
            tri = F[f]
            plan = [np.linalg.norm(V[tri[(i + 1) % 3]][[0, 2]] - V[tri[i]][[0, 2]]) for i in range(3)]
            i = int(np.argmax(plan))
            c, a, b = tri[i], tri[(i + 1) % 3], tri[(i + 2) % 3]           # the long edge c -> a, b its apex
            hit = edges.get((tuple(key[a]), tuple(key[c])))
            if hit is None or hit[0] in done:
                continue
            g, j = hit
            d = F[g][(j + 2) % 3]
            new = np.array([[b, c, d], [b, d, a]])
            q = V[new]
            m = np.cross(q[:, 1] - q[:, 0], q[:, 2] - q[:, 0])[:, 1]
            if (np.sign(m) == np.sign(n[g, 1])).all() and (np.abs(m) > 1e-6).all():
                F[f], F[g] = new
                done |= {f, g}
    return F


def ride_layout(piece, ride, frame):
    """The riding faces of a decal bowl, laid out: (V, N, F, material per face (TILE or None for the painting), UV per
    face corner (m, 3, 2), report). `ride` masks the piece's riding faces, `frame` is editor_generate.decal_frame."""
    from .editor_generate import decal_uv, orient
    V0, N0 = np.asarray(piece.mesh.V, 'f8'), np.asarray(piece.mesh.N, 'f8')
    F = orient(V0, np.asarray(piece.mesh.F), N0)[ride]
    t = V0[F]
    F = F[np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-9]   # a crease's zero rows
    used = np.unique(F)
    remap = np.full(len(V0), -1, 'i8')
    remap[used] = np.arange(len(used))
    V, N, F = V0[used], N0[used], remap[F]
    F = _flip_fins(V, F, N)
    V, F, added, N = tjunction.fix_tjunctions(V, F, attrs=N)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    lips = sorted(editor_coping._join(editor_coping.lip_frames(piece)),
                  key=lambda l: -np.linalg.norm(np.diff(l[0], axis=0), axis=1).sum())
    if not lips:
        raise ValueError(f"{piece.metadata['id']}: a decal bowl needs a lip")
    ids, E = _graph(V, F)
    n = ids.max() + 1
    P = np.zeros((n, 3))
    P[ids] = V
    w3 = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
    wp = np.linalg.norm(P[E[:, 0]][:, [0, 2]] - P[E[:, 1]][:, [0, 2]], axis=1)
    # s: metres down the surface from each lip; a vertex belongs to its nearest lip
    S, node = [], {tuple(k): i for i, k in enumerate(np.round(P / WELD).astype('i8').tolist())}
    for q, _, _, _ in lips:          # a lip's points are the piece's own vertices, welded alike (editor_coping.WELD)
        S.append(_dijkstra(n, E, w3, [node[k] for k in map(tuple, np.round(q / WELD).astype('i8').tolist()) if k in node]))
    S = np.array(S)
    which = S.argmin(0)
    s = S[which, np.arange(n)]
    # t, tp: metres (surface, plan) down to the floor: vertices facing up, away from any lip
    Nn = np.zeros((n, 3))
    Nn[ids] = N
    floor = (Nn[:, 1] > FLAT) & (s > 2 * BAND)
    tt = _dijkstra(n, E, w3, np.flatnonzero(floor))
    tp = _dijkstra(n, E, wp, np.flatnonzero(floor))
    # the plan point each vertex takes from the painting, before the band is sliced out (the slice's new vertices
    # interpolate it, so each sliced face keeps its share of the unsliced face's map)
    s, tt, tp = s[ids], tt[ids], tp[ids]
    which = which[ids]
    Q = V[:, [0, 2]].copy()
    for k, (q, d, _, closed) in enumerate(lips):
        m = which == k
        if not m.any():
            continue
        o, into, _, _ = _project(V[m][:, [0, 2]], q, d, closed)
        top, band = (PAINTED_BAND, BAND) if k == 0 else (SPINE_LINE, 0.)
        wall = np.isfinite(tt[m]) & (tt[m] > 1e-6)
        foot, length = o + tp[m], np.maximum(s[m] + tt[m] - band, 1e-6)    # the foot's plan offset, the laid length
        top = np.minimum(top, foot - LAID_MIN * length)        # a short wall starts its lay nearer the lip
        c = np.clip((foot - top) / length, LAID_MIN, 1.)
        lay = np.where(wall, np.maximum(o, top + (s[m] - band) * c), o)
        Q[m] += (lay - o)[:, None] * into
    decal = decal_uv(np.c_[Q[:, 0], np.zeros(len(Q)), Q[:, 1]], frame)
    # slice the tile band out of the main lip's wall (s there; the other lips' walls and the floor stay whole)
    field = np.where((which == 0) & np.isfinite(s), s, 1e9)
    V, F, attrs, field = _slice(V, F, np.c_[N, decal, which], field, BAND)
    N = attrs[:, :3] / np.maximum(np.linalg.norm(attrs[:, :3], axis=1, keepdims=True), 1e-12)
    decal, which = attrs[:, 3:5], np.round(attrs[:, 5]).astype(int)
    tile = (field[F] <= BAND + 1e-6).all(1) & (which[F] == 0).all(1)
    UV = decal[F]
    q, d, _, closed = lips[0]
    m = which == 0
    U = np.zeros(len(V))
    _, _, U[m], loop = _project(V[m][:, [0, 2]], q, d, closed)
    loop = loop if closed else 0.
    # the tile band: along the lip (a whole number of textures round a closed loop) and down the wall
    scale = (np.round(loop / TILE_SPAN) / loop) if loop >= TILE_SPAN else 1. / TILE_SPAN
    tu = U * scale
    tv = (field - TILE_FROM) / TILE_HEIGHT
    T = np.stack([tu, tv], 1)[F[tile]]
    if loop:
        wrap = np.ptp(T[:, :, 0], axis=1) > .5 * loop * scale      # a face across where the loop meets itself
        T[wrap, :, 0] += np.where(T[wrap, :, 0] < .5 * loop * scale, loop * scale, 0.)
    UV[tile] = T
    material = np.where(tile, TILE, None)
    report = {'tjunctions_split': int(added), 'lips': len(lips), 'tile_faces': int(tile.sum()),
              'painted_faces': int((~tile).sum())}
    return V, N, F, material, UV, report


def stretch(V, F, UV, size):
    """Per face (smallest, largest) texels per metre of the face corners' UVs (m, 3, 2) on a texture of `size` (w, h)
    pixels: the singular values of the map from the face's own plane to the texture."""
    A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    e1, e2 = B - A, C - A
    l1 = np.linalg.norm(e1, axis=1)
    x = e1 / np.maximum(l1, 1e-12)[:, None]
    y = np.cross(np.cross(e1, e2), e1)
    y /= np.maximum(np.linalg.norm(y, axis=1, keepdims=True), 1e-12)
    Pm = np.stack([np.stack([l1, np.zeros_like(l1)], 1), np.stack([(e2 * x).sum(1), (e2 * y).sum(1)], 1)], 2)
    size = np.asarray(size, 'f8')
    Um = np.stack([(UV[:, 1] - UV[:, 0]) * size, (UV[:, 2] - UV[:, 0]) * size], 2)
    ok = np.abs(np.linalg.det(Pm)) > 1e-12
    J = np.zeros((len(F), 2, 2))
    J[ok] = Um[ok] @ np.linalg.inv(Pm[ok])
    sv = np.linalg.svd(J, compute_uv=False)
    return sv[:, 1], sv[:, 0]


def parts(piece, decal, ride, deck, frame, feature):
    """The decal bowl's riding parts: (list of dsl.Mesh, report): the painting, the tile band, the concrete deck."""
    V, N, F, material, UV, report = ride_layout(piece, ride, frame)
    out = []
    for mat in (decal, TILE):
        m = material == (TILE if mat == TILE else None)
        if not m.any():
            continue
        # one vertex per (vertex, UV) corner: a texture seam keeps a vertex per side
        corners = F[m].ravel()
        key = np.c_[corners, np.round(UV[m].reshape(-1, 2) * 1e6).astype('i8')]
        _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        out.append(dsl.Mesh.part(V[corners[first]], inv.reshape(-1, 3), N=N[corners[first]],
                                 UV=UV[m].reshape(-1, 2)[first], role=dsl.RIDING, material=mat, feature=feature))
    V0, N0, F0 = np.asarray(piece.mesh.V, 'f8'), np.asarray(piece.mesh.N, 'f8'), np.asarray(piece.mesh.F)
    Fd = F0[deck]
    t = V0[Fd]
    Fd = Fd[np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-9]
    if len(Fd):
        from .editor_generate import orient, tile_uv
        used = np.unique(Fd)
        remap = np.full(len(V0), -1, 'i8')
        remap[used] = np.arange(len(used))
        Vd, Nd = V0[used], N0[used]
        out.append(dsl.Mesh.part(Vd, orient(Vd, remap[Fd], Nd), N=Nd, UV=tile_uv(Vd, Nd, DECK_TILE),
                                 role=dsl.RIDING, material=dsl.CONCRETE, feature=feature))
    return out, report
