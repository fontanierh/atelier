"""Steel coping and grind rails along every lip of the owner's editor park, except the kicker launch ramps.

A lip is where a piece's riding surface meets the flat coping deck behind its wall. The editor colours those two
surfaces differently (pieces.js mesh: rideC and deckC), so the lips are exactly the edges a riding face shares with a
deck face, for runs, roll-ins, jumps and bowls alike. Each lip becomes the pipeline's own coping (coping.coping: a
render-only steel tube) and its dsl.Rail, which the game grinds (export.py cp_lip_###).

A bowl in `brick` (the decal bowls: Prado) gets the concept's glazed terracotta brick coping instead of steel: a
bullnose band over its lip, the same grind line on top. A boost zone's lips (`gold`: editor_boost) are polished gold
over the same tube, up to where the piece ends, so a rail running on into a plain piece turns steel there.

Left out: a jump's kicker (its stations up to the lip), and the launch end of a run the owner capped
(params.vert_assist_max, the same KICK_REACH as the assist zones). Lips that continue from one piece into the next are
joined into one rail, so a grind runs on across the joint.
"""
import numpy as np

from . import coping as coping_mod
from . import dsl

FIXED = ([0.6, 0.58, 0.54], [0.45, 0.43, 0.4])    # pieces.js COL.side, COL.bottom: never a lip
WELD = 1e-3          # metres: vertices this close are one point
JOIN = .05           # metres: lips whose ends are this close continue into each other
MIN_LENGTH = 2.      # metres: shorter lips are left out
KICK_REACH = 30.     # metres of a capped run's end that count as its launch ramp (editor_generate.KICK_REACH)
GOLD = 'material_053'    # polished gold coping on a boost zone (editor_boost.GOLD)
BRICK = 'material_033'   # glazed terracotta brick coping (a Sunburst painting, tools/craterpark_textures.py)
BRICK_LENGTH = 2.4       # metres the brick texture spans along the lip (six bricks)
# the brick band's profile (out of the bowl, up) about the lip: from 1 cm inside the wall face (no light leak under it)
# down the wall face, over a rounded nose, back over the deck; its top is the grind line
BRICK_PROFILE = ((.01, -.3), (-.06, -.3), (-.06, -.03), (-.045, .03), (-.01, .065), (.04, .08), (.36, .08), (.36, -.02))
BRICK_TOP = .08
MEET, MEET_DIP = .02, .01   # metres a narrow deck's bands run past its middle, and how far their tops dip there
EXCLUDE_PAD = 1.     # metres past a launch ramp's end that stay bare


def _classes(piece):
    """Face masks (ride, deck): the most common non-side colour is the riding surface, the others the deck."""
    col = np.round(np.asarray(piece.colors, 'f8')[piece.mesh.F[:, 0]], 3)
    fixed = np.zeros(len(col), bool)
    for c in FIXED:
        fixed |= np.abs(col - c).max(1) < .01
    keys, inverse, counts = np.unique(col[~fixed], axis=0, return_inverse=True, return_counts=True)
    if not len(keys):
        return np.zeros(len(col), bool), np.zeros(len(col), bool)
    ride = np.zeros(len(col), bool)
    ride[np.flatnonzero(~fixed)[inverse.ravel() == counts.argmax()]] = True
    return ride, ~fixed & ~ride


def _excluded(piece, cap):
    """Indices of the stations that belong to a launch ramp: a jump's kicker, a capped run's last KICK_REACH m."""
    meta, st = piece.metadata, piece.metadata.get('stations') or []
    if not st:
        return set()
    if meta['type'] == 'kicker':
        return set(range(len(st)))
    if meta['type'] == 'jump' and meta.get('info', {}).get('lip'):
        return set(range(meta['info']['lip']['i'] + 1))
    if cap is not None and meta['type'] in ('run', 'rollin'):
        return {i for i, s in enumerate(st) if s['d'] >= st[-1]['d'] - KICK_REACH - EXCLUDE_PAD}
    return set()


def _chains(edges):
    """Polylines (lists of point ids) through undirected edges; split where more than two edges meet."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    used, out = set(), []
    starts = [v for v, n in adj.items() if len(n) != 2] + list(adj)
    for s in starts:
        for n in adj[s]:
            if (min(s, n), max(s, n)) in used:
                continue
            line, prev, cur = [s], s, n
            used.add((min(s, n), max(s, n)))
            while True:
                line.append(cur)
                if len(adj[cur]) != 2 or cur == s:
                    break
                nxt = adj[cur][0] if adj[cur][1] == prev else adj[cur][1]
                key = (min(cur, nxt), max(cur, nxt))
                if key in used:
                    break
                used.add(key)
                prev, cur = cur, nxt
            out.append(line)
    return out


def piece_lips(piece, cap=None):
    """The lips of one piece: [(points (k, 3), into (k, 3) horizontal unit toward the riding side)]."""
    return [(q, n) for q, n, _ in lip_frames(piece, cap)]


def lip_frames(piece, cap=None):
    """The lips of one piece with the riding wall's slope under them: [(points (k, 3), into (k, 3), run (k,))], `run`
    the metres the wall face moves into the riding side per metre of drop just under the lip (0 on a vert wall).

    `into` is square to the lip in plan, its side chosen by every face on the lip edge (the riding faces' centroids lie
    on the riding side, the deck's on the other), weighted by how far off the lip they lie: a vert wall's top row has
    its centroid on the lip line itself, and a single face's side read there flipped from one lip point to the next."""
    V, F = np.asarray(piece.mesh.V, 'f8'), np.asarray(piece.mesh.F)
    ride, deck = _classes(piece)
    if not ride.any() or not deck.any():
        return []
    keys, ids = np.unique(np.round(V / WELD).astype('i8'), axis=0, return_inverse=True)
    ids = ids.ravel()
    P = np.zeros((len(keys), 3))
    np.add.at(P, ids, V)
    P /= np.bincount(ids, minlength=len(keys))[:, None]
    W = ids[F]
    T = V[F]
    cross = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    real = np.linalg.norm(cross, axis=1) > 1e-9          # zero-area rows (a crease's two coincident rings) say nothing
    normal = cross / np.maximum(np.linalg.norm(cross, axis=1, keepdims=True), 1e-12)

    def edge_map(mask):
        out = {}
        for f, tri in zip(np.flatnonzero(mask), W[mask]):
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                if a != b:
                    out.setdefault((min(a, b), max(a, b)), []).append(f)
        return out

    ride_edges, deck_edges = edge_map(ride), edge_map(deck)
    lip_edges = [e for e in ride_edges if e in deck_edges]
    if not lip_edges:
        return []
    centroid = T.mean(1)
    into = np.zeros_like(P)
    run, runs = np.zeros(len(P)), np.zeros(len(P))
    for e in lip_edges:
        mid = (P[e[0]] + P[e[1]]) / 2
        t = P[e[1]] - P[e[0]]
        t[1] = 0.
        t /= np.linalg.norm(t) or 1.
        perp = np.array([-t[2], 0., t[0]])                 # square to the lip, horizontal
        vote = sum(((centroid[f] - mid) @ perp) for f in ride_edges[e] if real[f]) \
            - sum(((centroid[f] - mid) @ perp) for f in deck_edges[e] if real[f])
        d = perp * (1. if vote >= 0 else -1.)
        into[list(e)] += d
        # the wall's slope under the lip: the largest riding face on the edge, its normal turned to the riding side
        faces = [f for f in ride_edges[e] if real[f]]
        if faces:
            f = max(faces, key=lambda f: np.linalg.norm(cross[f]))
            n = normal[f] * (1. if normal[f] @ d >= 0 else -1.)
            r = abs(n[1]) / max(n @ d, .2)               # cot of the wall angle, at most 5 (a wall under about 11 deg)
            run[list(e)] += r
            runs[list(e)] += 1
    run = run / np.maximum(runs, 1)
    skip = _excluded(piece, cap)
    st = piece.metadata.get('stations') or []
    if skip and st:
        sx = np.array([[s['x'], s['z']] for s in st])
        bad = np.array([i in skip for i in range(len(st))])
    out = []
    for chain in _chains(lip_edges):
        pts = P[chain]
        keep = np.ones(len(chain), bool)
        if skip and st:
            near = np.argmin(((pts[:, None, [0, 2]] - sx[None]) ** 2).sum(2), 1)
            keep = ~bad[near]
        for seg in np.split(np.arange(len(chain)), np.flatnonzero(np.diff(keep.astype(int)) != 0) + 1):
            if not keep[seg[0]] or len(seg) < 2:
                continue
            q = pts[seg]
            n = into[np.array(chain)[seg]]
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            out.append((q, n, run[np.array(chain)[seg]]))
    return out


def _join(lips):
    """Join lips whose ends meet (within JOIN) into longer ones; closed loops are marked. A lip is a tuple of per-point
    arrays (points first); each comes back as that tuple plus `closed`."""
    lips = [tuple(a.copy() for a in lip) for lip in lips]
    merged = True
    while merged:
        merged = False
        for i in range(len(lips)):
            for j in range(len(lips)):
                if i == j or lips[i] is None or lips[j] is None:
                    continue
                for fa, fb in ((False, False), (False, True), (True, False), (True, True)):
                    A = tuple(a[::-1] for a in lips[i]) if fa else lips[i]
                    B = tuple(b[::-1] for b in lips[j]) if fb else lips[j]
                    if np.linalg.norm(A[0][-1] - B[0][0]) < JOIN:
                        lips[i], lips[j] = tuple(np.concatenate([a, b[1:]]) for a, b in zip(A, B)), None
                        merged = True
                        break
                if merged:
                    break
            if merged:
                break
        lips = [x for x in lips if x is not None] if merged else lips
    out = []
    for lip in lips:
        p = lip[0]
        length = np.linalg.norm(np.diff(p, axis=0), axis=1).sum()
        if length < MIN_LENGTH:
            continue
        closed = len(p) > 3 and np.linalg.norm(p[0] - p[-1]) < JOIN and length > 10
        out.append(tuple(a[:-1] if closed else a for a in lip) + (closed,))
    return out


def _brick_profile(reach):
    """BRICK_PROFILE with its deck side ending `reach` metres out. On a narrow deck (a spine's top) the band has no back
    face and runs MEET past the middle, its top dipping MEET_DIP there: the bands from the two sides cross along the
    middle instead of lying coplanar over each other (flicker) or leaving a slit between them."""
    prof = [list(q) for q in BRICK_PROFILE]
    if reach >= prof[-1][0]:
        return np.array(prof)
    prof = prof[:-1]
    prof[-1] = [max(reach + MEET, prof[-2][0] + .01), BRICK_TOP - MEET_DIP]
    return np.array(prof)


def brick_coping(lip, into, closed, feature, run=None, reach=BRICK_PROFILE[-1][0]):
    """(mesh, rail): the brick band along the lip points (k, 3), `into` the horizontal unit toward the bowl. `run` (k,)
    is the wall's slope under the lip (lip_frames): the face hanging down the wall leans in with it, so it never sinks
    into a sloping wall (a grazing crossing flickers). Normals face out of the band (hard at its square corners) and
    every face winds with them; on a closed loop the bricks are stretched a little so a whole number of textures
    goes round (no half brick where the loop meets itself)."""
    P, D = np.asarray(lip, 'f8'), np.asarray(into, 'f8')
    run = np.zeros(len(P)) if run is None else np.clip(np.asarray(run, 'f8'), 0., 1.)
    if closed:
        P, D, run = np.vstack([P, P[:1]]), np.vstack([D, D[:1]]), np.r_[run, run[:1]]
    length = np.r_[0., np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    along = length / BRICK_LENGTH
    if closed and along[-1] >= 1:
        along *= np.round(along[-1]) / along[-1]
    base = _brick_profile(reach)
    span = np.r_[0., np.cumsum(np.linalg.norm(np.diff(base, axis=0), axis=1))]
    span /= span[-1]
    # per lip point: the profile (out of the bowl, up), its hanging face leaning in by `run` per metre of drop
    prof = np.repeat(base[None], len(P), 0)
    hang = base[:, 0] < .05                                             # the points on the wall side
    prof[:, hang, 0] -= run[:, None] * np.maximum(-base[None, hang, 1], 0.)
    seg = np.diff(prof, axis=1)
    seg /= np.linalg.norm(seg, axis=2, keepdims=True)
    sn = np.stack([-seg[..., 1], seg[..., 0]], -1)                      # each segment's outward normal (out, up)
    # columns: one per profile point, two at a square corner (each side keeps its own normal)
    cols, left, right = [], [], []                                      # (point, normal source) per column
    m = len(base)
    for j in range(m):
        a, b = (j - 1 if j else None), (j if j < m - 1 else None)
        corner = a is not None and b is not None and float(sn[0, a] @ sn[0, b]) < np.cos(np.radians(40))
        if corner:
            left.append(len(cols)); cols.append((j, a))
            right.append(len(cols)); cols.append((j, b))
        else:
            left.append(len(cols)); right.append(len(cols)); cols.append((j, 'mean' if a is not None and b is not None else (a if b is None else b)))
    up = np.array([0., 1., 0.])
    out = -D                                                                 # away from the bowl, over the deck
    V, N, UV = [], [], []
    for j, src in cols:
        V.append(P + out * prof[:, j, 0:1] + up * prof[:, j, 1:2])
        n2 = sn[:, j - 1] + sn[:, j] if src == 'mean' else sn[:, src]
        n2 = n2 / np.linalg.norm(n2, axis=1, keepdims=True)
        N.append(out * n2[:, 0:1] + up * n2[:, 1:2])
        UV.append(np.stack([along, np.full(len(P), span[j])], 1))
    c = len(cols)
    V, N, UV = np.stack(V, 1).reshape(-1, 3), np.stack(N, 1).reshape(-1, 3), np.stack(UV, 1).reshape(-1, 2)
    k = len(P)
    F = []
    for j in range(m - 1):
        a0, b0 = right[j], left[j + 1]
        i = np.arange(k - 1) * c
        F += [np.stack([i + a0, i + b0, i + c + b0], 1), np.stack([i + a0, i + c + b0, i + c + a0], 1)]
    F = np.concatenate(F)
    t = V[F]
    fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    flip = (fn * N[F].sum(1)).sum(1) < 0
    F[flip] = F[flip][:, ::-1]
    mesh = dsl.Mesh.part(V, F, N=N, UV=UV, role=dsl.COPING, material=BRICK, feature=feature, tag='coping')
    top = P + up * BRICK_TOP
    if closed:
        top = top[:-1]
    return mesh, dsl.Rail(coping_mod.resample(top, closed=closed), closed, feature)


def deck_reach(lip, into):
    """Metres the brick band may reach over the deck behind a lip: half the deck's width where the deck is a narrow top
    between two lips of the same loop (a spine), else the profile's own."""
    P, D = np.asarray(lip, 'f8')[:, [0, 2]], np.asarray(into, 'f8')[:, [0, 2]]
    widths = []
    for p, d in zip(P, D):
        q = P - p
        dist = np.linalg.norm(q, axis=1)
        behind = (q @ -d) > .95 * dist                   # straight across the deck, not along the lip
        if behind.any():
            widths.append(dist[behind].min())
    full = BRICK_PROFILE[-1][0]
    return float(min(full, min(widths) / 2)) if widths else full


def gild(mesh, lip, gold):
    """The coping tube `mesh` (coping.coping along the lip points (k, 3)) turned GOLD on the faces whose nearest lip
    point is a gold one (`gold`, (k,) bool)."""
    if not gold.any():
        return mesh
    c = mesh.V[mesh.F].mean(1)
    near = np.zeros(len(c), 'i8')
    for a in range(0, len(c), 2048):
        near[a:a + 2048] = (((c[a:a + 2048, None] - lip[None]) ** 2).sum(2)).argmin(1)
    mesh.material = np.where(gold[near], dsl.MATERIAL[GOLD], mesh.material).astype(mesh.material.dtype)
    return mesh


def build(pieces, caps, brick=(), gold=()):
    """(coping meshes, rails, summary) for the kept bridge pieces. `caps` maps piece id -> vert_assist_max (or None);
    the bowls in `brick` get brick coping, the pieces in `gold` (the boost zones) gold steel coping."""
    lips, bricks = [], []
    for piece in pieces:
        if piece.metadata['type'] in ('deck', 'rail'):
            continue
        if piece.metadata['id'] in brick:
            bricks.extend(lip_frames(piece, caps.get(piece.metadata['id'])))
        else:
            flag = float(piece.metadata['id'] in gold)
            lips.extend((q, n, np.full(len(q), flag)) for q, n in piece_lips(piece, caps.get(piece.metadata['id'])))
    meshes, rails = [], []
    for k, (p, n, g, closed) in enumerate(_join(lips)):
        mesh, rail = coping_mod.coping(p, n, closed=closed, feature=f'editor_coping_{k:03d}')
        meshes.append(gild(mesh, p, g > .5))
        rails.append(rail)
    for k, (p, n, run, closed) in enumerate(_join(bricks)):
        mesh, rail = brick_coping(p, n, closed, f'editor_brick_{k:03d}', run, deck_reach(p, n))
        meshes.append(mesh)
        rails.append(rail)
    length = sum(np.linalg.norm(np.diff(r.points, axis=0), axis=1).sum() for r in rails)
    return meshes, rails, {'rails': len(rails), 'metres': round(float(length), 1)}
