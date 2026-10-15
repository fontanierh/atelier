"""Steel coping and grind rails along every lip of the owner's editor park, except the kicker launch ramps.

A lip is where a piece's riding surface meets the flat coping deck behind its wall. The editor colours those two
surfaces differently (pieces.js mesh: rideC and deckC), so the lips are exactly the edges a riding face shares with a
deck face, for runs, roll-ins, jumps and bowls alike. Each lip becomes the pipeline's own coping (coping.coping: a
render-only steel tube) and its dsl.Rail, which the game grinds (export.py cp_lip_###).

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

    def edge_map(mask):
        out = {}
        for f, tri in zip(np.flatnonzero(mask), W[mask]):
            for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
                if a != b:
                    out.setdefault((min(a, b), max(a, b)), f)
        return out

    ride_edges, deck_edges = edge_map(ride), edge_map(deck)
    lip_edges = [e for e in ride_edges if e in deck_edges]
    if not lip_edges:
        return []
    # the horizontal direction from each lip edge into its riding face
    centroid = V[F].mean(1)
    into = np.zeros_like(P)
    for e in lip_edges:
        mid = (P[e[0]] + P[e[1]]) / 2
        d = centroid[ride_edges[e]] - mid
        t = P[e[1]] - P[e[0]]
        t[1] = d[1] = 0.
        t /= np.linalg.norm(t) or 1.
        d -= (d @ t) * t        # square to the lip
        into[list(e)] += d / (np.linalg.norm(d) or 1.)
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
        for run in np.split(np.arange(len(chain)), np.flatnonzero(np.diff(keep.astype(int)) != 0) + 1):
            if not keep[run[0]] or len(run) < 2:
                continue
            q = pts[run]
            n = into[np.array(chain)[run]]
            n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
            out.append((q, n))
    return out


def _join(lips):
    """Join lips whose ends meet (within JOIN) into longer ones; closed loops are marked."""
    lips = [(p.copy(), n.copy()) for p, n in lips]
    merged = True
    while merged:
        merged = False
        for i in range(len(lips)):
            for j in range(len(lips)):
                if i == j or lips[i] is None or lips[j] is None:
                    continue
                (pa, na), (pb, nb) = lips[i], lips[j]
                for fa, fb in ((False, False), (False, True), (True, False), (True, True)):
                    A, An = (pa[::-1], na[::-1]) if fa else (pa, na)
                    B, Bn = (pb[::-1], nb[::-1]) if fb else (pb, nb)
                    if np.linalg.norm(A[-1] - B[0]) < JOIN:
                        lips[i], lips[j] = (np.concatenate([A, B[1:]]), np.concatenate([An, Bn[1:]])), None
                        merged = True
                        break
                if merged:
                    break
            if merged:
                break
        lips = [x for x in lips if x is not None] if merged else lips
    out = []
    for p, n in lips:
        length = np.linalg.norm(np.diff(p, axis=0), axis=1).sum()
        if length < MIN_LENGTH:
            continue
        closed = len(p) > 3 and np.linalg.norm(p[0] - p[-1]) < JOIN and length > 10
        out.append((p[:-1] if closed else p, n[:-1] if closed else n, closed))
    return out


def build(pieces, caps):
    """(coping meshes, rails, summary) for the kept bridge pieces. `caps` maps piece id -> vert_assist_max (or None)."""
    lips = []
    for piece in pieces:
        if piece.metadata['type'] in ('deck', 'rail'):
            continue
        lips += piece_lips(piece, caps.get(piece.metadata['id']))
    meshes, rails = [], []
    for k, (p, n, closed) in enumerate(_join(lips)):
        mesh, rail = coping_mod.coping(p, n, closed=closed, feature=f'editor_coping_{k:03d}')
        meshes.append(mesh)
        rails.append(rail)
    length = sum(np.linalg.norm(np.diff(r.points, axis=0), axis=1).sum() for r in rails)
    return meshes, rails, {'rails': len(rails), 'metres': round(float(length), 1)}
