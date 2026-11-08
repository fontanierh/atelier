"""Crater Park's drawn faces made clean (pure numpy, native frame: metres, y up; docs/CRATERPARK.md "Clean geometry").

- overlap_pairs: faces lying on each other (parallel, a few millimetres apart), found through a plane index;
  subtract cuts the higher-ranked face's outline out of the lower one, exactly, in its plane (no recede);
- inner_walls: a face lying wholly on one of its group turned the other way, the wall two foundation prisms share;
- fix_tjunctions: a vertex inside another face's edge splits that face, so seams within and between meshes conform;
- reachable: the open space connected to the outside, on a voxel grid, for the ray visibility test.
"""
import numpy as np

EPS = .01           # metres: plane distance under which two parallel faces lie on each other
ANGLE = 2.          # degrees between their normals at most
TINY = 1e-8         # square metres: a clipped part this small is dropped

def unit_normals(t):
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-300)



def lying_pairs(T, test, eps, cosmin, antiparallel=None, cell=2., batch=250_000, W=None):
    """(sample, face) pairs: sample points of faces (W barycentric stencil) within eps of a face's plane, normals
    within the angle (|cos| >= cosmin; antiparallel True: opposite only, False: same only, None: either), inside it;
    `test(sample_face, face)` filters candidates. Faces are indexed by plane: the dominant axis of the normal (sign
    folded), its two other components over it in bins of the angle, the plane's offset in bins of eps, and `cell`
    squares of the plane seen along that axis. A sample looks in the 27 neighbouring plane bins of its own cell."""
    T = T.astype('f8'); N = unit_normals(T)
    bad = ~(np.abs(N).max(1) > .5)                          # a degenerate face has no plane: it lies on nothing
    if bad.any():
        N[bad] = (0., 1., 0.)
    if W is None:
        W = np.array([[1/3, 1/3, 1/3], [.8, .1, .1], [.1, .8, .1], [.1, .1, .8], [.45, .45, .1], [.1, .45, .45], [.45, .1, .45]])
    S = np.einsum('sk,fkd->fsd', W, T).reshape(-1, 3); SO = np.repeat(np.arange(len(T)), len(W))
    ax = np.abs(N).argmax(1)
    sgn = np.sign(N[np.arange(len(N)), ax]); sgn[sgn == 0] = 1
    Nc = N * sgn[:, None]                                   # folded: dominant component positive
    o1 = (ax + 1) % 3; o2 = (ax + 2) % 3
    r = np.arange(len(N))
    qa = np.tan(np.arccos(cosmin)) + 1e-9
    q1 = np.floor(Nc[r, o1] / Nc[r, ax] / qa).astype('i8'); q2 = np.floor(Nc[r, o2] / Nc[r, ax] / qa).astype('i8')
    d = (Nc * T[:, 0]).sum(1)
    qd = np.floor(d / eps).astype('i8')
    # faces' 2-D cells over their box seen along the axis
    P1 = T[r[:, None], np.arange(3)[None], o1[:, None]]; P2 = T[r[:, None], np.arange(3)[None], o2[:, None]]
    c1lo = np.floor(P1.min(1) / cell).astype('i8'); c1hi = np.floor(P1.max(1) / cell).astype('i8')
    c2lo = np.floor(P2.min(1) / cell).astype('i8'); c2hi = np.floor(P2.max(1) / cell).astype('i8')
    n1 = c1hi - c1lo + 1; n2 = c2hi - c2lo + 1; count = np.where(bad, 0, n1 * n2)
    B = 1 << 20

    def pack(a, b1, b2, bd, x, y):
        return ((((((a * 128 + (b1 + 64)) * 128 + (b2 + 64)) * (1 << 22) + (bd + (1 << 21))) * 4096 + (x + 2048)) * 4096) + (y + 2048))

    own = np.repeat(r, count)
    local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
    cx = np.repeat(c1lo, count) + local % np.repeat(n1, count); cy = np.repeat(c2lo, count) + local // np.repeat(n1, count)
    keys = pack(ax[own], q1[own], q2[own], qd[own], cx, cy)
    del local, cx, cy
    o = np.argsort(keys); keys, own = keys[o], own[o]
    out = []
    # each sample: its face's axis and normal bins, its own offset bin along its face's folded normal, its cell
    sa = ax[SO]; sn = Nc[SO]
    sd = np.floor((sn * S).sum(1) / eps).astype('i8')
    s1 = np.floor(S[np.arange(len(S)), o1[SO]] / cell).astype('i8'); s2 = np.floor(S[np.arange(len(S)), o2[SO]] / cell).astype('i8')
    for d1 in (-1, 0, 1):
        for d2 in (-1, 0, 1):
            for dd in (-1, 0, 1):
                k = pack(sa, q1[SO] + d1, q2[SO] + d2, sd + dd, s1, s2)
                first = np.searchsorted(keys, k, 'left'); reps = np.searchsorted(keys, k, 'right') - first
                if not reps.any():
                    continue
                cum = np.cumsum(reps)
                cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(batch, cum[-1], batch)), len(S)])
                for a, b in zip(cuts[:-1], cuts[1:]):
                    rr = reps[a:b]
                    if not rr.any():
                        continue
                    si = a + np.repeat(np.arange(b - a), rr)
                    fj = own[np.repeat(first[a:b], rr) + np.arange(rr.sum()) - np.repeat(np.cumsum(rr) - rr, rr)]
                    ok = test(SO[si], fj)
                    si, fj = si[ok], fj[ok]
                    q = S[si]; v = T[fj]; m = N[fj]
                    dots = (N[SO[si]] * m).sum(1)
                    ok = (np.abs(dots) >= cosmin) if antiparallel is None else ((dots <= -cosmin) if antiparallel else (dots >= cosmin))
                    ok &= np.abs(((q - v[:, 0]) * m).sum(1)) < eps
                    for i in range(3):
                        e = v[:, (i + 1) % 3] - v[:, i]
                        ok &= (np.cross(e, q - v[:, i]) * m).sum(1) / np.maximum(np.linalg.norm(e, axis=1), 1e-12) > -1e-6
                    if ok.any():
                        out.append(np.stack([si[ok], fj[ok]], 1))
    if not out:
        return np.zeros((0, 2), 'i8'), SO, len(W)
    return np.unique(np.concatenate(out), axis=0), SO, len(W)


def overlap_pairs(T, rank, eps=EPS, angle=ANGLE):
    """Pairs (i, j): face i lies (partly) on face j, rank[j] < rank[i] (memory-bounded; see lying_pairs)."""
    pr, SO, nw = lying_pairs(T, lambda fi, fj: rank[fj] < rank[fi], eps, np.cos(np.radians(angle)))
    if not len(pr):
        return pr
    return np.unique(np.stack([SO[pr[:, 0]], pr[:, 1]], 1), axis=0)



def inner_walls(T, group, eps=1e-3):
    """Faces lying wholly (all seven samples) on a face of the same group turned the other way: a shared prism wall."""
    pr, SO, nw = lying_pairs(T, lambda fi, fj: (group[fj] == group[fi]) & (fj != fi), eps, .9999, antiparallel=True)
    hit = np.zeros(len(T) * nw, bool); hit[pr[:, 0]] = True
    return hit.reshape(-1, nw).all(1)



def _clip_half(poly, p0, p1, keep_left):
    """Convex polygon (k,2) clipped to the half-plane left (or right) of the line p0->p1."""
    if len(poly) == 0:
        return poly
    e = p1 - p0
    s = e[0] * (poly[:, 1] - p0[1]) - e[1] * (poly[:, 0] - p0[0])
    if not keep_left:
        s = -s
    out = []
    k = len(poly)
    for i in range(k):
        a, b = poly[i], poly[(i + 1) % k]; sa, sb = s[i], s[(i + 1) % k]
        if sa >= 0:
            out.append(a)
        if (sa >= 0) != (sb >= 0):
            t = sa / (sa - sb); out.append(a + t * (b - a))
    return np.array(out).reshape(-1, 2)



def _area(poly):
    if len(poly) < 3:
        return 0.
    x, y = poly[:, 0], poly[:, 1]
    return .5 * (x * np.roll(y, -1) - np.roll(x, -1) * y).sum()



def subtract(tri, others):
    """The parts of triangle `tri` (3,3) outside every triangle in `others` (k,3,3) projected onto its plane: a list
    of triangles (m,3,3) on tri's plane (fans of convex pieces); the triangle itself if nothing overlaps."""
    n = unit_normals(tri[None])[0]
    u = tri[1] - tri[0]; u /= np.linalg.norm(u); v = np.cross(n, u); o = tri[0]
    to2 = lambda X: np.stack([(X - o) @ u, (X - o) @ v], -1)
    pieces = [to2(tri)]
    if _area(pieces[0]) < 0:
        pieces = [pieces[0][::-1]]
    for A in others:
        a = to2(A)
        if _area(a) < 0:
            a = a[::-1]
        new = []
        for P in pieces:
            rest = P
            for i in range(3):                      # P minus A: outside edge i, inside edges before it
                p0, p1 = a[i], a[(i + 1) % 3]
                out = _clip_half(rest, p0, p1, keep_left=False)
                if abs(_area(out)) > TINY:
                    new.append(out)
                rest = _clip_half(rest, p0, p1, keep_left=True)
                if abs(_area(rest)) <= TINY:
                    break
        pieces = new
        if not pieces:
            break
    tris = []
    for P in pieces:
        for i in range(1, len(P) - 1):
            t2 = np.array([P[0], P[i], P[i + 1]])
            if abs(_area(t2)) > TINY:
                tris.append(o + t2[:, :1] * u + t2[:, 1:] * v)
    out = np.array(tris).reshape(-1, 3, 3)
    # keep the original winding
    if len(out):
        flip = (unit_normals(out) @ n) < 0
        out[flip] = out[flip][:, [0, 2, 1]]
    return out



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
        e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]); fid = np.tile(np.arange(len(F)), 3)
        a, b = P[e[:, 0]], P[e[:, 1]]
        pts = P if others is None else np.concatenate([P, others])
        cand, which, t = _edge_hits(a, b, pts, tol)
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
        ue = np.sort(e, 1); _, ui, uc = np.unique(ue, axis=0, return_inverse=True, return_counts=True)
        op = uc[ui.ravel()][cand] == 1
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



def mark(occ, T, lo, h, budget=1_000_000, step=None, cheapest=True):
    """Set the voxels of occ (origin lo, size h) that the faces T (n,3,3) pass through: each face sampled on its own
    skewed grid, at most h/4 apart along each of its two edges from corner 0 (a long thin face costs its length, not
    its length squared), in chunks of about `budget` points. Each face starts at its cheapest corner (cheapest=False:
    corner 0): a sliver's two long edges from one corner would cost their product (any corner covers the face as
    closely). The default step, h/6, misses fewer grazed voxels than h/4 from corner 0 did, at a fifth of its cost."""
    step = h / 6 if step is None else step
    L = np.linalg.norm(np.roll(T, -1, 1) - T, axis=2)                    # L[:, i]: the edge from corner i to i + 1
    k = np.clip(np.ceil(L / step), 1, 8000).astype('i8')
    costs = np.stack([(k[:, i] + 1) * (k[:, (i + 2) % 3] + 2) // 2 + k[:, i] + 1 for i in range(3)], 1)
    c0 = costs.argmin(1) if cheapest else np.zeros(len(T), 'i8'); rows = np.arange(len(T))
    T = T[rows[:, None], (c0[:, None] + np.arange(3)) % 3]
    e1 = (T[:, 1] - T[:, 0]).astype('f8'); e2 = (T[:, 2] - T[:, 0]).astype('f8')
    k1, k2 = k[rows, c0], k[rows, (c0 + 2) % 3]
    cost = costs[rows, c0]
    cut = np.searchsorted(np.cumsum(cost), np.arange(budget, cost.sum() + budget, budget))
    s = 0
    for e in np.unique(np.r_[cut, len(T)]).tolist():
        e = max(e, s + 1)
        if s >= len(T):
            break
        idx = np.arange(s, min(e, len(T))); s = e
        a, b = k1[idx], k2[idx]
        row = np.repeat(np.arange(len(idx)), a + 1)
        i = np.arange(len(row)) - np.repeat(np.cumsum(a + 1) - (a + 1), a + 1)
        u = i / a[row]
        cnt = np.floor(b[row] * (1 - u) + 1e-9).astype('i8') + 1
        pt = np.repeat(row, cnt)
        j = np.arange(len(pt)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        g = idx[pt]
        p = T[g, 0] + np.repeat(u, cnt)[:, None] * e1[g] + (j / b[pt])[:, None] * e2[g]
        c = np.floor((p - lo) / h).astype(np.int32)
        c = c[((c >= 0) & (c < occ.shape)).all(1)]
        occ[c[:, 0], c[:, 1], c[:, 2]] = True


def reachable(triangles, voxel=.5, log=print):
    """The open space reachable from outside: (grid (a,b,c) bool, origin (3,), voxel). Every face marks the voxels its
    sample points (voxel/4 apart, mark) fall in; the free voxels 6-connected to the grid's border are swept run by run along
    x, y and z in turn until nothing changes. A voxel a face misses only adds reachable space (more faces kept)."""
    T = triangles; h = voxel
    lo = T.reshape(-1, 3).min(0) - 2 * h; hi = T.reshape(-1, 3).max(0) + 2 * h
    shape = tuple(np.ceil((hi - lo) / h).astype(int) + 1)
    occ = np.zeros(shape, bool)
    mark(occ, T, lo, h)
    free = np.logical_not(occ, out=occ); del occ                         # in place: two grids at most
    reach = np.zeros(shape, bool)
    reach[0] = reach[-1] = True; reach[:, 0] = reach[:, -1] = True; reach[:, :, 0] = reach[:, :, -1] = True
    reach &= free
    before = -1
    for sweep in range(200):
        for axis in (0, 1, 2):
            f = np.moveaxis(free, axis, -1); r = np.moveaxis(reach, axis, -1)   # views: each slice updated in place
            for i in range(f.shape[0]):
                fs, rs = f[i], r[i]
                start = fs & ~np.concatenate([np.zeros(fs.shape[:-1] + (1,), bool), fs[..., :-1]], -1)
                rid = np.where(fs, np.cumsum(start.ravel(), dtype='i4').reshape(fs.shape), 0)
                hit = np.zeros(rid.max() + 1, bool); hit[rid[rs & fs]] = True; hit[0] = False
                r[i] = hit[rid]
        now = int(reach.sum())
        log(f'reachable open space: sweep {sweep + 1}, {now} voxels')
        if now == before:
            break
        before = now
    return reach, lo, h


def covered(T, S, eps=.05, cosmin=.98):
    """Mask of the faces T (n,3,3) lying wholly (all seven samples) within eps of a face of S (m,3,3) facing the same
    way, inside it: a foundation's top under a riding surface (build.py `covered`, through the plane index)."""
    n = len(T)
    pr, SO, nw = lying_pairs(np.concatenate([T, S]), lambda fi, fj: (fi < n) & (fj >= n), eps, cosmin, antiparallel=False)
    hit = np.zeros(n * nw, bool); hit[pr[:, 0][pr[:, 0] < n * nw]] = True
    return hit.reshape(-1, nw).all(1)



def _clip_lin(poly, c, d):
    """The part of the convex polygon (k,3) where c.p + d >= 0 (Sutherland-Hodgman with a linear function)."""
    if not len(poly):
        return poly
    g = poly @ c + d
    out = []
    k = len(poly)
    for i in range(k):
        p, q = poly[i], poly[(i + 1) % k]; gp, gq = g[i], g[(i + 1) % k]
        if gp >= 0:
            out.append(p)
        if (gp >= 0) != (gq >= 0):
            out.append(p + gp / (gp - gq) * (q - p))
    return np.array(out).reshape(-1, 3)


def cut_under(tri, skin, lift=.002):
    """The parts of the face `tri` (3,3) not over the surface `skin` (m,3,3, upward faces): over each skin face's
    footprint (x, z), the part of tri above its plane less `lift` is cut away, exactly (every condition is linear in
    the point). Returns triangles (n,3,3) on tri's plane (tri itself, (1,3,3), when nothing is cut)."""
    lo, hi = tri.min(0), tri.max(0)
    near = skin[(skin[:, :, 0].max(1) >= lo[0]) & (skin[:, :, 0].min(1) <= hi[0]) &
                (skin[:, :, 2].max(1) >= lo[2]) & (skin[:, :, 2].min(1) <= hi[2]) & (skin[:, :, 1].min(1) <= hi[1] + lift)]
    pieces = [tri.astype('f8')]
    cut = False
    for s in near.astype('f8'):
        conds = []
        orient = np.sign((s[1, 0] - s[0, 0]) * (s[2, 2] - s[0, 2]) - (s[1, 2] - s[0, 2]) * (s[2, 0] - s[0, 0]))
        if orient == 0:
            continue
        for i in range(3):
            A, B = s[i], s[(i + 1) % 3]
            # orient * cross((B-A).xz, (p-A).xz) >= 0, linear in p
            c = orient * np.array([-(B[2] - A[2]), 0., B[0] - A[0]])
            conds.append((c, -c @ A))
        n = np.cross(s[1] - s[0], s[2] - s[0])                            # skin plane: n.p = n.s0, n_y > 0
        c = n / n[1]                                                       # p.y - plane_y(p.xz) = c.p - c.s0
        conds.append((c, -(c @ s[0]) + lift))                              # above (plane - lift)
        new = []
        for q in pieces:
            inside = q
            for cc, dd in conds:
                inside = _clip_lin(inside, cc, dd)
            if len(inside) < 3 or abs(_poly_area3(inside)) < TINY:
                new.append(q); continue
            cut = True
            rest = q
            for cc, dd in conds:                                           # q minus the convex region, as pieces
                out = _clip_lin(rest, -cc, -dd)
                if len(out) >= 3 and abs(_poly_area3(out)) > TINY:
                    new.append(out)
                rest = _clip_lin(rest, cc, dd)
                if len(rest) < 3:
                    break
        pieces = new
    if not cut:
        return tri[None].astype('f8')
    out = [np.stack([q[0], q[i], q[i + 1]]) for q in pieces for i in range(1, len(q) - 1)]
    return np.array(out).reshape(-1, 3, 3)


def _poly_area3(q):
    return float(np.linalg.norm(sum(np.cross(q[i] - q[0], q[i + 1] - q[0]) for i in range(1, len(q) - 1)))) / 2 if len(q) >= 3 else 0.
