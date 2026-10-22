"""T-junctions: find them (the seam-conformity validator, V2) and, behind a flag only, split them (a safety net).

A T-junction is a vertex lying inside another face's open edge: the renderer rasterises the two sides of that edge
along different lines and a hairline crack flickers through. The v2 generator shares seam samples by construction
(network.py), so on a clean build `find` reports nothing; validate.py calls `check(mesh)` and requires 0.

The contract (proven on the clean-geometry branch, park-assist's T-junction suite 8/8 and acceptance suite 4/4):
- only an OPEN edge (one face's) counts: a crack opens only there; an edge two faces share already conforms;
- a point counts at its NEAREST edge of a face only, and never for a face whose corner it sits on (within tol): inside
  a sliver every point is within tol of every edge;
- `fix_tjunctions` splits one edge per face per round, its points fanned from the opposite corner: it never makes a
  vertex inside a face (a centre vertex on a sliver lies within tol of its own edges and splits them again, without end);
- a split reuses an existing vertex only where its attributes (UV, AO) agree with the receiving edge's, so a UV seam
  keeps a vertex per chart.
Candidate search walks the 0.5 m cells each edge passes through, in chunks of about `budget` pairs: memory stays
bounded however dense the points.
"""
import numpy as np

TOL = 5e-4          # metres: a vertex this close to the inside of an open edge is a T-junction


def _edge_hits(a, b, pts, tol, cell=.5, budget=2_000_000):
    """(edge, point, t) for every point (k,3) within tol of the inside of an edge (a, b) (not at its ends): candidates
    from the cells each edge passes through (sampled every cell/4 at most; the cells of the cube of half that spacing
    plus tol round each sample), never its bounding box, and tested in chunks of about `budget` pairs (memory stays bounded however dense the points)."""
    key = lambda c: ((c[..., 0] + (1 << 20)) << 42) | ((c[..., 1] + (1 << 20)) << 21) | (c[..., 2] + (1 << 20))
    if not len(a) or not len(pts):
        return np.zeros(0, 'i8'), np.zeros(0, 'i8'), np.zeros(0)
    pk = key(np.floor(pts / cell).astype('i8')); po = np.argsort(pk); pk = pk[po]
    L = np.linalg.norm(b - a, axis=1)
    k = np.clip(np.ceil(L / (cell / 4)).astype('i8'), 1, 1 << 20) + 1          # samples per edge
    # every point of an edge lies within half the actual sample spacing of a sample: the cube of that radius plus tol
    # round each sample is narrower than a cell, so its 8 corners name every cell it touches (diagonals included)
    corner = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], 'f8')
    rad = L / np.maximum(k - 1, 1) / 2 + tol
    nudge = corner
    hits = []
    cum = np.cumsum(k * len(nudge)); cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(budget, cum[-1], budget)), len(a)])
    for e0, e1 in zip(cuts[:-1], cuts[1:]):
        if e1 <= e0:
            continue
        kk = k[e0:e1]; own = np.repeat(np.arange(e0, e1), kk)
        f = (np.arange(len(own)) - np.repeat(np.cumsum(kk) - kk, kk)) / np.maximum(np.repeat(kk - 1, kk), 1)
        smp = a[own] + f[:, None] * (b[own] - a[own])
        cells = key(np.floor((smp[:, None, :] + nudge[None] * rad[own][:, None, None]) / cell).astype('i8')).ravel()
        own8 = np.repeat(own, len(nudge)); o = np.lexsort((cells, own8)); own8, cells = own8[o], cells[o]
        first_ = np.r_[True, (own8[1:] != own8[:-1]) | (cells[1:] != cells[:-1])]
        pair = np.stack([own8[first_], cells[first_]], 1)
        first = np.searchsorted(pk, pair[:, 1], 'left'); reps = np.searchsorted(pk, pair[:, 1], 'right') - first
        rc = np.cumsum(reps)
        sub = np.unique(np.r_[0, np.searchsorted(rc, np.arange(budget, rc[-1] if len(rc) else 0, budget)), len(pair)])
        for s0, s1 in zip(sub[:-1], sub[1:]):
            r = reps[s0:s1]
            if not r.sum():
                continue
            e = np.repeat(pair[s0:s1, 0], r)
            p = po[np.repeat(first[s0:s1], r) + np.arange(r.sum()) - np.repeat(np.cumsum(r) - r, r)]
            A = a[e]; d = b[e] - A; L2 = (d * d).sum(1); q = pts[p]
            t = ((q - A) * d).sum(1) / np.maximum(L2, 1e-300)
            dist = np.linalg.norm(A + t[:, None] * d - q, axis=1); Le = np.sqrt(L2)
            ok = (dist < tol) & (t * Le > tol * 10) & ((1 - t) * Le > tol * 10)
            if ok.any():
                hits.append(np.stack([e[ok], p[ok], t[ok]], 1))
    if not hits:
        return np.zeros(0, 'i8'), np.zeros(0, 'i8'), np.zeros(0)
    h = np.concatenate(hits)
    e_, p_ = h[:, 0].astype('i8'), h[:, 1].astype('i8'); o = np.lexsort((p_, e_))
    h = h[o][np.r_[True, (e_[o][1:] != e_[o][:-1]) | (p_[o][1:] != p_[o][:-1])]]   # an edge-point pair once
    return h[:, 0].astype('i8'), h[:, 1].astype('i8'), h[:, 2]


def fix_tjunctions(P, F, others=None, tol=1e-6, rounds=8, attrs=None, atol=1e-3):
    """(P, F) with every triangle split where a vertex (of P, or of `others` (k,3)) lies inside one of its edges (within
    tol, not at its ends), on an open edge (one face's), each point at its nearest edge of a face. New vertices, appended
    to P, lie only at those points' positions. Returns (P, F, added), and with `attrs` (a per-vertex (n,k) array: UVs,
    occlusion) (P, F, added, attrs): a split's vertex takes the attributes interpolated along the edge it splits; an
    existing vertex is reused only where its own agree within atol (a UV seam's other chart gets a vertex of its own)."""
    added = 0
    X = None if attrs is None else np.asarray(attrs, 'f8').reshape(len(P), -1)
    if others is not None and len(others):
        # each other position once, and none of this mesh's own (those split its edges as its vertices already)
        others = np.asarray(others, 'f8')
        k = np.round(np.concatenate([P, others]) / max(tol, 1e-9)).astype('i8')
        _, first, inv = np.unique(k, axis=0, return_index=True, return_inverse=True); inv = inv.ravel()
        mine = np.zeros(len(first), bool); mine[inv[:len(P)]] = True
        keep = first[~mine & (first >= len(P))] - len(P)         # each other position once, none of this mesh's own
        others = others[np.sort(keep)]
    for _ in range(rounds):
        nF = len(F)
        if not nF:
            break
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
        u0 = np.minimum(e[:, 0], e[:, 1]).astype('i8')
        u1 = np.maximum(e[:, 0], e[:, 1]).astype('i8')
        _, ui, uc = np.unique((u0 << 32) | u1, return_inverse=True, return_counts=True)
        is_open = (uc[ui.ravel()] == 1)
        if not is_open.any():
            break
        open_face = is_open[:nF] | is_open[nF:2 * nF] | is_open[2 * nF:]
        sub_edges = np.flatnonzero(np.tile(open_face, 3))
        fid = np.tile(np.arange(nF), 3)
        a, b = P[e[:, 0]], P[e[:, 1]]
        pts = P if others is None else np.concatenate([P, others])
        sub_cand, which, t = _edge_hits(a[sub_edges], b[sub_edges], pts, tol)
        cand = sub_edges[sub_cand]
        # a face's own corner (a sliver's apex), or any point at a corner's position (its UV seam twin), never
        # splits its edges
        own = (np.linalg.norm(P[F[fid[cand]]] - pts[which][:, None], axis=2) <= tol).any(1)
        cand, which, t = cand[~own], which[~own], t[~own]
        if not len(cand):
            break
        # a point near two edges of one face (anywhere in a sliver) splits only its nearest: the edge it lies on
        tc = np.clip(t, 0, 1)[:, None]
        dist = np.linalg.norm(a[cand] + tc * (b[cand] - a[cand]) - pts[which], axis=1)
        o = np.lexsort((dist, which, fid[cand]))
        first = np.r_[True, (fid[cand][o][1:] != fid[cand][o][:-1]) | (which[o][1:] != which[o][:-1])]
        o = o[first]; cand, which, t = cand[o], which[o], t[o]
        # and only an open edge (one face's): a crack opens only there; an edge two faces share already conforms
        op = is_open[cand]
        cand, which, t = cand[op], which[op], t[op]
        if not len(cand):
            break
        # split each affected triangle along one busy edge (its busiest): the edge's points in order of t fanned from
        # the opposite corner. No vertex is ever made inside a face (a centre vertex on a sliver lies within tol of its
        # edges and splits them again, without end); points on a face's other edges split its fan's end triangles next round
        nF = len(F)
        hf, hk = fid[cand], cand // nF
        u = np.unique(np.stack([hf, hk, which], 1), axis=0, return_index=True)[1]   # a point once per edge
        cand, which, t, hf, hk = cand[u], which[u], t[u], hf[u], hk[u]
        cnt = np.zeros((nF, 3), 'i8'); np.add.at(cnt, (hf, hk), 1)
        aff = np.flatnonzero(cnt.any(1)); kb = np.full(nF, -1, 'i8'); kb[aff] = cnt[aff].argmax(1)
        on = hk == kb[hf]; cand, which, t, hf = cand[on], which[on], t[on], hf[on]
        keep = np.ones(nF, bool); keep[aff] = False
        # the vertex each split point becomes: a vertex of P where its attributes are the receiving edge's (a UV seam
        # keeps a vertex per chart at one position: the other chart's is never borrowed), else a new one at its
        # position with the edge's attributes, one per (position, attributes)
        n0 = len(P)
        if X is None:
            make = which >= n0; Xi = None
        else:
            tt = np.clip(t, 0, 1)[:, None]; Xi = (1 - tt) * X[e[cand, 0]] + tt * X[e[cand, 1]]
            make = which >= n0
            mine = np.flatnonzero(~make)
            make[mine] = np.abs(X[which[mine]] - Xi[mine]).max(1) > atol
        if make.any():
            src = which[make]
            key = src[:, None] if Xi is None else np.c_[src, np.round(Xi[make] / atol).astype('i8')]
            _, fi, inv = np.unique(key, axis=0, return_index=True, return_inverse=True); inv = inv.ravel()
            P = np.concatenate([P, pts[src[fi]]]); added += len(fi)
            if X is not None:
                X = np.concatenate([X, Xi[make][fi]])
            which = which.copy(); which[make] = n0 + np.arange(len(fi))[inv]
            used = np.unique(src[src >= n0]) - n0
            if len(used):
                others = np.delete(others, used, 0)                       # a vertex of P now: never added twice
        hw, ht = which, t
        # each face's chain: the edge's start corner, its points by t, its end corner
        cf = np.r_[aff, aff]; ct = np.r_[np.full(len(aff), -1.), np.full(len(aff), 2.)]
        cv = np.r_[F[aff, kb[aff]], F[aff, (kb[aff] + 1) % 3]]
        ef = np.r_[cf, hf]; et = np.r_[ct, ht]; ev = np.r_[cv, hw]
        o = np.lexsort((et, ef)); ef, ev = ef[o], ev[o]
        last = np.r_[ef[1:] != ef[:-1], True]                            # a chain's end corner starts no triangle
        s = np.flatnonzero(~last)
        out = np.stack([F[ef[s], (kb[ef[s]] + 2) % 3], ev[s], ev[s + 1]], 1)   # (apex, p_i, p_i+1): the face's winding
        F = np.concatenate([F[keep], np.array(out, 'i8').reshape(-1, 3)])
        # drop degenerate fan triangles (three points on one edge)
        t3 = P[F]
        area = np.linalg.norm(np.cross(t3[:, 1] - t3[:, 0], t3[:, 2] - t3[:, 0]), axis=1)
        F = F[area > 1e-12]
    return (P, F, added) if X is None else (P, F, added, X)



def find(P, F, tol=TOL):
    """The T-junctions of the mesh (P (n,3), F (m,3)), without changing it: (face, edge k (0: corners 0-1, 1: 1-2,
    2: 2-0), point index, t along the edge, distance) arrays, the filters of `fix_tjunctions` applied (open edges only,
    a point at its nearest edge of a face, never a face's own corner). Weld creases and UV seams first (Mesh.welded):
    there a split vertex is not a T-junction."""
    P = np.asarray(P, 'f8'); F = np.asarray(F, 'i8').reshape(-1, 3)
    empty = (np.zeros(0, 'i8'),) * 3 + (np.zeros(0),) * 2
    nF = len(F)
    if not nF:
        return empty
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    u0 = np.minimum(e[:, 0], e[:, 1]).astype('i8')
    u1 = np.maximum(e[:, 0], e[:, 1]).astype('i8')
    _, ui, uc = np.unique((u0 << 32) | u1, return_inverse=True, return_counts=True)
    is_open = (uc[ui.ravel()] == 1)
    if not is_open.any():
        return empty
    open_face = is_open[:nF] | is_open[nF:2 * nF] | is_open[2 * nF:]
    sub_edges = np.flatnonzero(np.tile(open_face, 3))
    fid = np.tile(np.arange(nF), 3)
    a, b = P[e[:, 0]], P[e[:, 1]]
    sub_cand, which, t = _edge_hits(a[sub_edges], b[sub_edges], P, tol)
    cand = sub_edges[sub_cand]
    if not len(cand):
        return empty
    own = (np.linalg.norm(P[F[fid[cand]]] - P[which][:, None], axis=2) <= tol).any(1)
    cand, which, t = cand[~own], which[~own], t[~own]
    if not len(cand):
        return empty
    tc = np.clip(t, 0, 1)[:, None]
    dist = np.linalg.norm(a[cand] + tc * (b[cand] - a[cand]) - P[which], axis=1)
    o = np.lexsort((dist, which, fid[cand]))
    first = np.r_[True, (fid[cand][o][1:] != fid[cand][o][:-1]) | (which[o][1:] != which[o][:-1])]
    o = o[first]; cand, which, t, dist = cand[o], which[o], t[o], dist[o]
    op = is_open[cand]
    cand, which, t, dist = cand[op], which[op], t[op], dist[op]
    return fid[cand], cand // nF, which, t, dist


def check(mesh, tol=TOL, examples=10):
    """The V2 seam-conformity report of a dsl.Mesh: its positions welded (creases and UV seams are not T-junctions),
    then `find`. {'tjunctions': count, 'faces': faces with one, 'max_distance': metres, 'examples': [{'point': xyz,
    'face': i, 'edge': k, 'feature': name}]}; 0 is required."""
    P, F = mesh.welded()
    f, k, w, t, d = find(P, F, tol)
    out = {'tjunctions': int(len(f)), 'faces': int(len(np.unique(f))), 'max_distance': float(d.max()) if len(d) else 0.}
    names = getattr(mesh, 'features', ())
    feat = getattr(mesh, 'feature', None)
    out['examples'] = [{'point': P[w[i]].round(4).tolist(), 'face': int(f[i]), 'edge': int(k[i]),
                        'feature': names[feat[f[i]]] if feat is not None and len(names) else ''}
                       for i in range(min(examples, len(f)))]
    return out
