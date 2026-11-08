"""Error-bounded, attribute-aware remeshing (Blender's constrained Delaunay), ported from the clean-geometry branch,
and `simplify(mesh)` for a v2 dsl.Mesh.

A mesh is split into patches, each a height field over its own plane. Every edge where two patches meet, and every
open edge, belongs to a chain between junctions; each chain is simplified once (Douglas-Peucker on position and
attributes), so both patches along it get the very same vertices: the result is conforming by construction, no
T-junction, no crack. Each patch is then re-triangulated from its simplified boundary (constrained Delaunay in its
plane) and greedy insertion of its own vertices: in every triangle the input vertex furthest from it (height along
the patch's normal over tol_h, or an attribute over its own tolerance) is inserted, until every input vertex lies
within the tolerances, and also (new in v2) every point where a coarse edge crosses a fine one: both surfaces are
linear between those and the fine vertices, so the bound then holds everywhere on the fine faces, not only at their
corners (a bowl, curved both ways, was 3.7 mm at tol_h 2.5 mm checked at vertices only). Output vertices are a subset
of the input ones, so per-vertex attributes carry over exactly.

Fails closed: a patch that cannot be certified keeps its fine faces (and its neighbours are redone against its full
chains): a CDT that makes a vertex (crossing constraints), a vertex left uncovered, the round limit, a covered area off
the fine one's by more than tol_b x boundary length, a boundary simplified to fewer than 3 points, and (new in v2) a
patch whose faces do not all project onto its plane with one orientation (a fold: the snake lesson). Also new in v2:
Blender's CDT merging two input vertices within its epsilon, and any patch whose triangles are not a manifold sheet
bounded by exactly its chain edges (_closes); a last guard returns the input if the result has more open or
non-manifold edges than it. `diag['reasons']` counts why patches kept their faces.

Proven on generated ramps with Blender's CDT: 7 ramps 191,268 -> 854 triangles, max riding deviation 1.74 mm at
tol_h 3 mm, 0 failed patches, 3.0 s, 1.84 GiB peak (cleanpark remesh benchmark). Needs Blender for `cdt`.
"""
import numpy as np

MIN_COS = .05       # a patch's faces must face its plane this much (one orientation, none edge-on)

try:
    from mathutils.geometry import delaunay_2d_cdt
except ImportError:                                     # outside Blender: the remesh needs Blender's Delaunay
    delaunay_2d_cdt = None


def weld(P, tol=1e-5):
    key = np.round(P / tol).astype('i8')
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    return first, inv.ravel()


def face_normals(P, F):
    t = P[F]
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = np.linalg.norm(n, axis=1)
    return n / np.maximum(a, 1e-300)[:, None], a / 2


def edges_of(F):
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    face = np.tile(np.arange(len(F)), 3)
    key = np.sort(e, 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return key, face, inv.ravel(), cnt


def frame(n):
    n = n / np.linalg.norm(n)
    side = np.array([1., 0, 0]) if abs(n[0]) < .9 else np.array([0, 0, 1.])
    u = np.cross(n, side); u /= np.linalg.norm(u); v = np.cross(n, u)
    return u, v, n


def dp_chain(idx, P, A, tol_g, tol_a, closed=False):
    """Douglas-Peucker over the vertex chain `idx` (positions P, attributes A (V,k) with tolerances tol_a (k,)): the
    kept indices, ends always kept. A vertex may go when it lies within tol_g of the segment kept round it, and each
    attribute interpolated along it there within its tolerance."""
    idx = np.asarray(idx)
    if closed:
        # split a loop at its first vertex and the vertex furthest from it
        far = int(np.argmax(np.linalg.norm(P[idx] - P[idx[0]], axis=1)))
        a = dp_chain(np.r_[idx[:far + 1]], P, A, tol_g, tol_a)
        b = dp_chain(np.r_[idx[far:], idx[:1]], P, A, tol_g, tol_a)
        return np.r_[a, b[1:-1]]
    keep = np.zeros(len(idx), bool); keep[0] = keep[-1] = True
    stack = [(0, len(idx) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        p0, p1 = P[idx[i]], P[idx[j]]
        mid = P[idx[i + 1:j]]
        d = p1 - p0; L2 = max(d @ d, 1e-300)
        u = np.clip(((mid - p0) @ d) / L2, 0, 1)
        dist = np.linalg.norm(p0 + u[:, None] * d - mid, axis=1) / tol_g
        if A is not None and A.shape[1]:
            ai = A[idx[i]] + u[:, None] * (A[idx[j]] - A[idx[i]])
            dist = np.maximum(dist, (np.abs(ai - A[idx[i + 1:j]]) / tol_a).max(1))
        k = int(np.argmax(dist))
        if dist[k] > 1:
            m = i + 1 + k; keep[m] = True
            stack += [(i, m), (m, j)]
    return idx[keep]


class Locator:
    """Point location in 2-D triangles (m,3,2) through a uniform grid of their bounding boxes."""

    def __init__(self, T2, cell=None):
        self.T = T2
        lo, hi = T2.min(1), T2.max(1)
        if cell is None:
            cell = max(float(np.sqrt(np.median(np.prod(hi - lo, 1)))) if len(T2) else 1., 1e-3)
        self.cell = cell
        self.o = lo.min(0) if len(T2) else np.zeros(2)
        a = np.floor((lo - self.o) / cell).astype('i8'); b = np.floor((hi - self.o) / cell).astype('i8')
        size = b - a + 1; count = size.prod(1)
        owner = np.repeat(np.arange(len(T2)), count)
        local = np.arange(count.sum()) - np.repeat(np.cumsum(count) - count, count)
        c = a[owner] + np.stack([local % size[owner, 0], local // size[owner, 0]], -1)
        keys = (c[:, 0] << 32) + c[:, 1]
        o = np.argsort(keys, kind='stable'); self.keys, self.owner = keys[o], owner[o]

    def locate(self, Q, eps=1e-9):
        """Index of a triangle containing each point (k,2) and its barycentrics, -1 where none."""
        c = np.floor((Q - self.o) / self.cell).astype('i8')
        k = (c[:, 0] << 32) + c[:, 1]
        first = np.searchsorted(self.keys, k, 'left'); reps = np.searchsorted(self.keys, k, 'right') - first
        out = np.full(len(Q), -1); bary = np.zeros((len(Q), 3))
        best = np.full(len(Q), -np.inf)
        CH = 4_000_000
        cum = np.cumsum(reps)
        cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(CH, cum[-1] if len(cum) else 0, CH)), len(Q)])
        for s, e in zip(cuts[:-1], cuts[1:]):
            r = reps[s:e]
            which = s + np.repeat(np.arange(e - s), r)
            cand = self.owner[np.repeat(first[s:e], r) + np.arange(r.sum()) - np.repeat(np.cumsum(r) - r, r)]
            t = self.T[cand]; q = Q[which]
            v0 = t[:, 1] - t[:, 0]; v1 = t[:, 2] - t[:, 0]; v2 = q - t[:, 0]
            den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
            ok = np.abs(den) > 1e-300; den = np.where(ok, den, 1)
            b1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
            b2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
            b0 = 1 - b1 - b2
            m = np.minimum(np.minimum(b0, b1), b2)
            good = ok & (m > -eps)
            # keep the most inside candidate per point
            sc = np.where(good, m, -np.inf)
            order = np.lexsort((sc, which))
            last = np.r_[which[order][1:] != which[order][:-1], True]
            sel = order[last]
            upd = sc[sel] > best[which[sel]]
            w = which[sel][upd]
            best[w] = sc[sel][upd]; out[w] = cand[sel][upd]
            bary[w] = np.stack([b0, b1, b2], 1)[sel][upd]
        return out, bary


def cdt(Q2, edges):
    """Constrained Delaunay triangulation of points (k,2) with constraint edges (e,2) -> triangles (m,3) into Q2."""
    if delaunay_2d_cdt is None:
        raise RuntimeError('remesh needs Blender (mathutils.geometry.delaunay_2d_cdt)')
    vo, eo, fo, ov, oe, of = delaunay_2d_cdt([tuple(p) for p in Q2.tolist()], [tuple(e) for e in edges.tolist()], [], 0, 1e-9, True)
    # map output vertices to input ones (constraints never cross, so every output vertex is an input vertex)
    m = np.full(len(vo), -1)
    for i, o in enumerate(ov):
        if len(o) > 1:
            raise CDTError('input vertices merged within epsilon')          # one would vanish: a hole beside it
        if len(o):
            m[i] = o[0]
    F = np.array(fo, dtype='i8').reshape(-1, 3) if len(fo) else np.zeros((0, 3), 'i8')
    if (m < 0).any():
        raise CDTError('constraint edges crossed: a new vertex was made')     # fail closed: the patch keeps its faces
    return m[F]


class CDTError(RuntimeError):
    pass


def _parity(q, P2, edges, chunk=4096):
    """Even-odd inside test of the points q (m,2) against the closed loops of `edges` (pairs into P2): a constrained
    triangulation's triangles lie wholly inside or outside its constraints, so a centroid's parity is exact."""
    e = np.asarray(edges, 'i8').reshape(-1, 2); a, b = P2[e[:, 0]], P2[e[:, 1]]
    odd = np.zeros(len(q), bool)
    for s in range(0, len(e), chunk):
        ax, ay, bx, by = a[s:s + chunk, 0], a[s:s + chunk, 1], b[s:s + chunk, 0], b[s:s + chunk, 1]
        straddle = (ay[None] > q[:, 1:2]) != (by[None] > q[:, 1:2])
        x = ax[None] + (q[:, 1:2] - ay[None]) * (bx - ax)[None] / np.where(by == ay, 1., by - ay)[None]
        odd ^= (straddle & (x > q[:, 0:1])).sum(1) % 2 == 1
    return odd


def _dist_to_boundary(Q, P2, T):
    """Distance from points Q (m,2) to the boundary edges (edges of one face) of the triangles T (n,3) into P2."""
    key, face, inv, cnt = edges_of(T)
    b = np.unique(key, axis=0)[cnt == 1]
    out = np.full(len(Q), np.inf)
    for s in range(0, len(b), 2048):
        a, c = P2[b[s:s + 2048, 0]], P2[b[s:s + 2048, 1]]; d = c - a; L2 = np.maximum((d * d).sum(1), 1e-300)
        t = np.clip((((Q[:, None] - a[None]) * d[None]).sum(2)) / L2[None], 0, 1)
        out = np.minimum(out, np.linalg.norm(a[None] + t[..., None] * d[None] - Q[:, None], axis=2).min(1))
    return out


def _crossing_errors(P2, H, A, tol_h, tol_a, Tg, loc, E):
    """@cc [owner:fontanierh,label:correctness] complete-overlay-edge-errors
    Return the maximum normalised height/attribute error over each fine edge's
    intersection with the coarse surface. Every intersecting coarse triangle
    MUST be examined; a traversal limit or failed point lookup MUST NOT certify
    an unexamined remainder. Exterior boundary motion is certified separately
    by remesh_patch's vertex and _patch's area/boundary/topology checks.

    Clip the edge against each candidate triangle in barycentric coordinates.
    The difference is linear on that interval, so its endpoints suffice. The
    locator's complete bounding-box cell index supplies candidates, including
    when either endpoint is outside, or the edge goes through a coarse vertex.
    """
    E = np.asarray(E, 'i8').reshape(-1, 2)
    err = np.zeros(len(E))
    if not len(E) or not len(Tg):
        return err
    pa, pb = P2[E[:, 0]], P2[E[:, 1]]
    lower = np.floor((np.minimum(pa, pb) - loc.o) / loc.cell).astype('i8')
    upper = np.floor((np.maximum(pa, pb) - loc.o) / loc.cell).astype('i8')
    sizes = upper - lower + 1
    counts = sizes.prod(1)

    def evaluate(edge, triangle):
        if not len(edge):
            return
        q = P2[Tg[triangle]]
        u, v = q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]
        den = u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]
        if (np.abs(den) <= 1e-300).any():
            raise CDTError('degenerate triangle in overlay certification')

        def bary(points):
            w = points - q[:, 0]
            b1 = (w[:, 0] * v[:, 1] - w[:, 1] * v[:, 0]) / den
            b2 = (u[:, 0] * w[:, 1] - u[:, 1] * w[:, 0]) / den
            return np.stack([1. - b1 - b2, b1, b2], 1)

        first, last = bary(pa[edge]), bary(pb[edge])
        delta = last - first
        ratio = -first / np.where(delta != 0., delta, 1.)
        enter = np.maximum(0., np.where(delta > 0., ratio, -np.inf).max(1))
        leave = np.minimum(1., np.where(delta < 0., ratio, np.inf).min(1))
        parallel_outside = ((delta == 0.) & (first < -1e-10)).any(1)
        hit = (enter <= leave + 1e-10) & ~parallel_outside
        if not hit.any():
            return
        edge, triangle = edge[hit], triangle[hit]
        first, delta = first[hit], delta[hit]
        for t in (np.clip(enter[hit], 0., 1.), np.clip(leave[hit], 0., 1.)):
            bc = first + t[:, None] * delta
            coarse = (H[Tg[triangle]] * bc).sum(1)
            fine = H[E[edge, 0]] + t * (H[E[edge, 1]] - H[E[edge, 0]])
            value = np.abs(coarse - fine) / tol_h
            if A is not None and A.shape[1]:
                ca = (A[Tg[triangle]] * bc[..., None]).sum(1)
                fa = A[E[edge, 0]] + t[:, None] * (A[E[edge, 1]] - A[E[edge, 0]])
                value = np.maximum(value, (np.abs(ca - fa) / tol_a).max(1))
            np.maximum.at(err, edge, value)

    # Bound temporary cell and pair arrays, even for an unusually long edge.
    # Large cell rectangles use a complete triangle scan in bounded chunks.
    cell_budget = 65536
    start = 0
    while start < len(E):
        if counts[start] > cell_budget:
            for begin in range(0, len(Tg), 4096):
                tri = np.arange(begin, min(begin + 4096, len(Tg)))
                evaluate(np.full(len(tri), start, 'i8'), tri)
            start += 1
            continue
        stop = start
        total = 0
        while stop < len(E) and total + counts[stop] <= cell_budget and stop - start < 1024:
            total += int(counts[stop]); stop += 1
        n = counts[start:stop]
        owner = np.repeat(np.arange(start, stop), n)
        local = np.arange(total) - np.repeat(np.cumsum(n) - n, n)
        cells = lower[owner] + np.stack([local % sizes[owner, 0], local // sizes[owner, 0]], 1)
        keys = (cells[:, 0] << 32) + cells[:, 1]
        lo = np.searchsorted(loc.keys, keys, 'left')
        reps = np.searchsorted(loc.keys, keys, 'right') - lo
        # One cell can name many triangles; slice the virtual candidate list.
        cumulative = np.r_[0, np.cumsum(reps)]
        for begin in range(0, int(cumulative[-1]), 262144):
            index = np.arange(begin, min(begin + 262144, int(cumulative[-1])))
            cell = np.searchsorted(cumulative, index, 'right') - 1
            triangle = loc.owner[lo[cell] + index - cumulative[cell]]
            pairs = np.unique(np.stack([owner[cell], triangle], 1), axis=0)
            evaluate(pairs[:, 0], pairs[:, 1])
        start = stop
    return err


def remesh_patch(P2, H, A, tol_h, tol_a, bverts, bedges, interior, inside, max_rounds=60, tol_out=0., fine_edges=None):
    """One patch: P2 (V,2) plane coordinates, H (V,) height along its normal, A (V,k) attributes; the simplified
    boundary's vertices `bverts` and constraint edges `bedges` (pairs of vertex ids), the candidate vertices
    `interior` (every original vertex of the patch, boundary ones included, as checks), `inside(points (m,2))` a mask of
    points in the patch's domain (None: the parity of the constraint loops, exact). Returns triangles (m,3) of vertex ids, or None when it cannot certify them (fail
    closed): a check vertex left outside the triangles by more than tol_out (the boundary's own tolerance) is inserted,
    and one still outside, or still off the surface, after max_rounds fails the patch. With `fine_edges` (pairs of
    vertex ids: the fine faces' edges) the bound also holds inside the fine faces (_crossing_errors): a fine edge
    crossed off tolerance inserts its endpoints, and one whose endpoints are both chosen already fails the patch."""
    chosen = np.unique(np.asarray(bverts))
    check = np.asarray(interior)
    if len(chosen) < 3:                       # a boundary simplified to a segment: nothing to triangulate (fail closed)
        return None
    for rnd in range(max_rounds):
        local = {v: i for i, v in enumerate(chosen.tolist())}
        le = np.array([[local[a], local[b]] for a, b in bedges], 'i8').reshape(-1, 2)
        T = cdt(P2[chosen], le)
        if len(T):
            c = P2[chosen][T].mean(1)
            T = T[_parity(c, P2, bedges) if inside is None else inside(c)]
        Tg = chosen[T]
        if not len(Tg):
            return None
        loc = Locator(P2[Tg])
        tri, bary = loc.locate(P2[check], eps=1e-7)
        ok = tri >= 0
        err = np.zeros(len(check))
        out = np.flatnonzero(~ok)
        if len(out):
            far = out[_dist_to_boundary(P2[check[out]], P2, Tg) > tol_out + 1e-7]
            if len(far):                                  # a hole or a lost strip: insert, never certify by omission
                if np.isin(check[far], chosen).any() or rnd == max_rounds - 1:
                    return None                           # chosen and still uncovered: the patch keeps its faces
                chosen = np.unique(np.r_[chosen, check[far]])
                continue
        h = (H[Tg[tri[ok]]] * bary[ok]).sum(1)
        err[ok] = np.abs(h - H[check[ok]]) / tol_h
        if A is not None and A.shape[1]:
            a = (A[Tg[tri[ok]]] * bary[ok][..., None]).sum(1)
            err[ok] = np.maximum(err[ok], (np.abs(a - A[check[ok]]) / tol_a).max(1))
        bad = ok & (err > 1)
        if not bad.any():
            if fine_edges is None:
                return Tg
            fe = np.asarray(fine_edges, 'i8').reshape(-1, 2)
            xe = _crossing_errors(P2, H, A, tol_h, tol_a, Tg, loc, fe)
            worse = fe[xe > 1]
            if not len(worse):
                return Tg
            new = np.setdiff1d(worse.ravel(), chosen)
            if not len(new) or rnd == max_rounds - 1:
                return None                                   # crossed between two chosen vertices: keep the faces
            chosen = np.unique(np.r_[chosen, new])
            continue
        # the worst point of each triangle
        bi = np.flatnonzero(bad)
        order = np.lexsort((-err[bi], tri[bi]))
        firsts = order[np.r_[True, tri[bi][order][1:] != tri[bi][order][:-1]]]
        new = check[bi[firsts]]
        chosen = np.unique(np.r_[chosen, new])
    return None


def chains_of(F, label, fixed_vertex=None):
    """The chains of a mesh's patch boundaries: edges with one face, faces of two labels, or more than two faces.
    Returns (chains [(vertex ids, closed)], per chain the set of labels along it)."""
    key, face, inv, cnt = edges_of(F)
    ue = np.unique(key, axis=0)                              # unique edges, sorted as inv refers
    # labels on each unique edge
    lab = label[face]
    lo = np.full(len(ue), np.iinfo('i8').max); hi = np.full(len(ue), np.iinfo('i8').min)
    np.minimum.at(lo, inv, lab); np.maximum.at(hi, inv, lab)
    is_chain = (cnt != 2) | (lo != hi)
    ce = ue[is_chain]
    # vertex degree in the chain graph
    deg = np.bincount(ce.ravel(), minlength=F.max() + 1)
    # labels incident to each chain vertex: a vertex where 3+ labels meet is a junction too
    nv = F.max() + 1
    junction = (deg != 2) & (deg > 0)
    # count distinct labels per vertex (vectorised)
    pv = np.stack([F.ravel(), np.repeat(label, 3)], 1)
    pv = np.unique(pv, axis=0)
    nlab = np.bincount(pv[:, 0], minlength=nv)
    junction |= (deg > 0) & (nlab >= 3)
    if fixed_vertex is not None:
        junction |= (deg > 0) & np.asarray(fixed_vertex)[:nv]
    # adjacency of the chain graph
    adj = {}
    for a, b in ce.tolist():
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    used = set()
    chains = []
    ek = lambda a, b: (a, b) if a < b else (b, a)
    starts = [v for v in adj if junction[v]]
    for s in starts:
        for nb in adj[s]:
            if ek(s, nb) in used:
                continue
            path = [s, nb]; used.add(ek(s, nb))
            cur, prev = nb, s
            while not junction[cur]:
                nxt = [x for x in adj[cur] if ek(cur, x) not in used]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]; used.add(ek(prev, cur)); path.append(cur)
            chains.append((np.array(path), False))
    # loops without junctions
    for a, b in ce.tolist():
        if ek(a, b) in used:
            continue
        path = [a, b]; used.add(ek(a, b)); cur = b
        while True:
            nxt = [x for x in adj[cur] if ek(cur, x) not in used]
            if not nxt:
                break
            used.add(ek(cur, nxt[0])); cur = nxt[0]
            if cur == a:
                break
            path.append(cur)
        chains.append((np.array(path), True))
    return chains


def planar_patches(P, F, angle=.5, offset=1e-3, extra_cut=None):
    """Labels of the faces' planar patches: faces joined across an edge when their normals agree within `angle`
    degrees and each lies within `offset` of the other's plane, never across an edge in `extra_cut` (a set of sorted
    vertex pairs: UV seams, material changes)."""
    n, area = face_normals(P, F)
    key, face, inv, cnt = edges_of(F)
    order = np.argsort(inv, kind='stable')
    inv_s, face_s = inv[order], face[order]
    starts = np.flatnonzero(np.r_[True, inv_s[1:] != inv_s[:-1]])
    pair = (np.diff(np.r_[starts, len(inv_s)]) == 2)
    a = face_s[starts[pair]]; b = face_s[starts[pair] + 1]
    ok = (n[a] * n[b]).sum(1) > np.cos(np.radians(angle))
    ca, cb = P[F[a]].mean(1), P[F[b]].mean(1)
    ok &= (np.abs(((cb - P[F[a][:, 0]]) * n[a]).sum(1)) < offset) & (np.abs(((ca - P[F[b][:, 0]]) * n[b]).sum(1)) < offset)
    if extra_cut is not None and len(extra_cut):
        ek = np.unique(key, axis=0)[inv_s[starts[pair]]]
        cut = np.array([(int(x), int(y)) in extra_cut for x, y in ek])
        ok &= ~cut
    a, b = a[ok], b[ok]
    label = union_find(len(F), a, b)
    return np.unique(label, return_inverse=True)[1].ravel()


def union_find(n, a, b):
    """Component label (its smallest member) of each of n items joined by the pairs (a, b): root hooking with full
    path compression (Shiloach-Vishkin style), a few rounds."""
    label = np.arange(n)
    while True:
        la, lb = label[a], label[b]
        diff = la != lb
        if not diff.any():
            return label
        la, lb = la[diff], lb[diff]
        lo, hi = np.minimum(la, lb), np.maximum(la, lb)
        np.minimum.at(label, hi, lo)
        while True:
            nxt = label[label]
            if np.array_equal(nxt, label):
                break
            label = nxt


def _area2(t2):
    return .5 * ((t2[:, 1, 0] - t2[:, 0, 0]) * (t2[:, 2, 1] - t2[:, 0, 1]) - (t2[:, 1, 1] - t2[:, 0, 1]) * (t2[:, 2, 0] - t2[:, 0, 0]))


def _boundary_length(P2, F):
    key, face, inv, cnt = edges_of(F)
    ue = np.unique(key, axis=0)
    b = ue[cnt == 1]
    return float(np.linalg.norm(P2[b[:, 0]] - P2[b[:, 1]], axis=1).sum())


def _patch(P, F, A, fl, chains, n, area, l, normal_of, tol_h, tol_a, tol_b, patch_A=None, why=None):
    """One patch's remeshed faces (global vertex ids), or None when it cannot be certified (`why`, a dict: the
    count of each reason)."""
    def fail(reason):
        if why is not None:
            why[reason] = why.get(reason, 0) + 1
        return None

    Fl = F[fl]
    vs = np.unique(np.concatenate([Fl.ravel()] + list(chains)))
    loc_of = {int(v): i for i, v in enumerate(vs.tolist())}
    nrm = normal_of(l) if normal_of is not None else (n[fl] * area[fl, None]).sum(0)
    u, v, w = frame(nrm)
    Pl = P[vs]
    P2 = np.stack([Pl @ u, Pl @ v], 1); H = Pl @ w
    Al = patch_A(l, vs) if patch_A is not None else (A[vs] if A is not None else None)
    if Al is None and patch_A is not None:
        return fail('seam')                             # the patch's attributes are not single-valued (a seam inside)
    s_n = (n[fl] @ w)[area[fl] > 1e-12]                 # degenerate faces have no orientation
    if not ((s_n > MIN_COS).all() or (s_n < -MIN_COS).all()):
        return fail('projection')                       # not one-to-one onto its plane (a fold, or too steep a face)
    bverts, bedges = [], []
    for k in chains:
        kk = [loc_of[int(x)] for x in k]
        bverts += kk; bedges += list(zip(kk[:-1], kk[1:]))
    Flocal = np.array([[loc_of[int(x)] for x in tri] for tri in Fl.tolist()], 'i8')
    try:
        fe = np.unique(np.sort(np.concatenate([Flocal[:, [0, 1]], Flocal[:, [1, 2]], Flocal[:, [2, 0]]]), 1), axis=0)
        T = remesh_patch(P2, H, Al, tol_h, tol_a, np.unique(bverts), bedges, np.unique(Flocal), None, tol_out=tol_b,
                         fine_edges=fe)
    except CDTError as e:
        return fail('cdt: ' + str(e))
    if T is None or not len(T):
        return fail('uncertified')
    # the domain: the remeshed patch covers the fine one's area, up to its boundary moving tol_b
    a0 = np.abs(_area2(P2[Flocal])).sum(); a1 = np.abs(_area2(P2[T])).sum()
    if abs(a1 - a0) > tol_b * _boundary_length(P2, Flocal) + 1e-9:
        return fail('area')
    t2 = P2[T]
    s = (t2[:, 1, 0] - t2[:, 0, 0]) * (t2[:, 2, 1] - t2[:, 0, 1]) - (t2[:, 1, 1] - t2[:, 0, 1]) * (t2[:, 2, 0] - t2[:, 0, 0])
    T = np.where((s < 0)[:, None], T[:, [0, 2, 1]], T)
    if (n[fl] @ w).mean() < 0:
        T = T[:, [0, 2, 1]]
    if not _closes(T, bedges):
        return fail('topology')
    return vs[T]


def _closes(T, bedges):
    """True when the triangles T (local ids) are a manifold disc-like sheet bounded by exactly the constraint edges:
    no degenerate or repeated triangle, every constraint edge used once, every other edge twice with opposite
    directions. Shared chains then make neighbouring patches meet edge for edge (no gap, no overlap)."""
    T = np.asarray(T, 'i8')
    if ((T[:, 0] == T[:, 1]) | (T[:, 1] == T[:, 2]) | (T[:, 2] == T[:, 0])).any():
        return False
    d = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    if len(np.unique(d, axis=0)) != len(d):                  # a directed edge twice: overlap or flipped neighbour
        return False
    u, c = np.unique(np.sort(d, 1), axis=0, return_counts=True)
    if (c > 2).any():
        return False
    b = np.unique(np.sort(np.asarray(bedges, 'i8').reshape(-1, 2), 1), axis=0)
    once = u[c == 1]
    return len(once) == len(b) and np.array_equal(once, b)


def remesh_mesh(P, F, A, tol_h, tol_a, label, normal_of=None, tol_b=None, fixed=None, fixed_vertex=None, diag=None,
                patch_A=None, return_labels=False):
    """Remesh every patch (faces with one `label`) of the welded mesh (P, F) as a height field over its plane, sharing
    simplified chains between patches. A patch of one face, or one in `fixed` (labels), keeps its faces; chains along it
    keep every vertex, as do vertices in `fixed_vertex` (seams shared with other meshes). `normal_of(label)` gives a
    patch's projection normal (default: its area-weighted mean normal). Returns faces. A patch the remesher cannot
    certify (remesh_patch None, crossing constraints, or a covered area off the fine one's by more than tol_b times its
    boundary length) keeps its fine faces, counted in `diag` (a dict) when given. `patch_A(label, vertex ids)`: a
    patch's own attributes (v2: a vertex split at a seam has one value per side), or None to keep the patch as it is;
    `A` is then used for the chains only. With return_labels, (faces, each face's label)."""
    tol_b = tol_h if tol_b is None else tol_b
    n, area = face_normals(P, F)
    nl = int(label.max()) + 1
    count = np.bincount(label, minlength=nl)
    fixed_l = count <= 1
    if fixed is not None and len(fixed):
        fixed_l[np.fromiter(fixed, 'i8')] = True
    chains = chains_of(F, label, fixed_vertex)
    key, face, inv, cnt = edges_of(F)
    ue = np.unique(key, axis=0)
    # labels along each unique edge
    el = np.stack([inv, label[face]], 1); el = np.unique(el, axis=0)
    starts = np.searchsorted(el[:, 0], np.arange(len(ue)))
    ends = np.searchsorted(el[:, 0], np.arange(len(ue)), 'right')
    edge_index = {}
    for i, (x, y) in enumerate(ue.tolist()):
        edge_index[(x, y)] = i
    # each chain's labels, and its simplified form (used while none of its patches is fixed)
    chain_labs, chain_simple = [], []
    for idx, closed in chains:
        x, y = int(idx[0]), int(idx[1])
        ei = edge_index[(min(x, y), max(x, y))]
        chain_labs.append(el[starts[ei]:ends[ei], 1].tolist())
        k = dp_chain(idx, P, A, tol_b, tol_a, closed)
        chain_simple.append(np.r_[k, k[:1]] if closed else k)
    chain_full = [np.r_[idx, idx[:1]] if closed else idx for idx, closed in chains]
    of_patch = [[] for _ in range(nl)]
    for c, labs in enumerate(chain_labs):
        for l in labs:
            of_patch[l].append(c)
    order = np.argsort(label, kind='stable')
    bounds = np.r_[0, np.cumsum(count)]
    done = {}                                   # label -> (its chains' forms, triangles or None)
    # A patch that fails keeps its faces and becomes fixed: its chains go back to every vertex, and the patches
    # beside it are remeshed against those (a simplified chain beside a full one would leave a gap), until none fails.
    while True:
        simple = [not any(fixed_l[l] for l in labs) for labs in chain_labs]
        out, failed, labs_out = [], [], []
        for l in range(nl):
            fl = order[bounds[l]:bounds[l + 1]]
            if fixed_l[l] or not of_patch[l]:
                out.append(F[fl]); labs_out.append(np.full(len(fl), l)); continue
            sig = tuple(simple[c] for c in of_patch[l])
            if l in done and done[l][0] == sig:
                res = done[l][1]
            else:
                res = _patch(P, F, A, fl, [chain_simple[c] if simple[c] else chain_full[c] for c in of_patch[l]],
                             n, area, l, normal_of, tol_h, tol_a, tol_b, patch_A,
                             None if diag is None else diag.setdefault('reasons', {}))
                done[l] = (sig, res)
            if res is None:
                failed.append(l); out.append(F[fl]); labs_out.append(np.full(len(fl), l))
            else:
                out.append(res); labs_out.append(np.full(len(res), l))
        if not failed:
            break
        fixed_l[np.array(failed)] = True
        if diag is not None:
            diag['failed_patches'] = diag.get('failed_patches', 0) + len(failed)
            diag['failed_faces'] = diag.get('failed_faces', 0) + int(count[failed].sum())
    faces = np.concatenate(out) if out else np.zeros((0, 3), 'i8')
    if return_labels:
        return faces, (np.concatenate(labs_out) if labs_out else np.zeros(0, 'i8'))
    return faces


# ---------------------------------------------------------------- v2: a dsl.Mesh
DIRECTIONS = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]
                      + [[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], 'f8')
DIRECTIONS /= np.linalg.norm(DIRECTIONS, axis=1, keepdims=True)
"""Projection directions: a patch's faces are binned by the nearest (at most about 55 degrees off), so each patch is a
height field over its direction's plane."""
TOL_H, TOL_B, TOL_UV, TOL_AO = .003, .0015, .002, .02   # metres, metres, tiles, occlusion (the clean branch's)
WELD = 1e-6


def patches(mesh):
    """Each face's patch label: faces joined across an edge they share by vertex ids (never across a crease or a UV
    seam, where vertices are split), with one material, role, feature and tag, and one projection direction."""
    F = mesh.F
    n, area = face_normals(mesh.V, F)
    bins = np.argmax(n @ DIRECTIONS.T, 1)
    attr = np.stack([mesh.material, mesh.role, mesh.feature, getattr(mesh, 'tag', np.zeros(len(F), 'i4')), bins], 1)
    key, face, inv, cnt = edges_of(F)
    o = np.argsort(inv, kind='stable'); inv_s, face_s = inv[o], face[o]
    pair = np.flatnonzero((inv_s[1:] == inv_s[:-1]) & (np.bincount(inv)[inv_s[1:]] == 2))
    a, b = face_s[pair], face_s[pair + 1]
    same = (attr[a] == attr[b]).all(1) & (area[a] > 1e-12) & (area[b] > 1e-12)
    lab = union_find(len(F), a[same], b[same])
    return np.unique(lab, return_inverse=True)[1].ravel()


def simplify(mesh, tol_h=TOL_H, tol_b=TOL_B, tol_uv=TOL_UV, tol_ao=TOL_AO, keep=None, diag=None, keep_open=False):
    """The mesh remeshed patch by patch (patches()) within tol_h of its surface along each patch's direction, its
    boundaries within tol_b, its UVs within tol_uv and AO within tol_ao everywhere on the input's faces; a new dsl.Mesh whose
    vertices are a subset of the input's (positions, normals, UVs, AO carried over exactly) and whose faces keep their
    patch's material, role, feature and tag. Creases and UV seams (split vertices) keep every vertex along them.
    `keep` (m,) bool: faces left as they are (their patches fixed). A patch the remesher cannot certify, or one that
    holds both sides of a seam (a seam ending inside it), keeps its faces; counted in `diag`. `keep_open`: every vertex
    on an open edge stays (a piece cut from a larger mesh, simplified on its own, still meets its neighbours exactly)."""
    from . import dsl
    V, F = mesh.V, mesh.F
    if not len(F):
        return mesh
    key = np.round(V / WELD).astype('i8')
    _, first, w_of = np.unique(key, axis=0, return_index=True, return_inverse=True); w_of = w_of.ravel()
    P = V[first]; Fw = w_of[F]
    twins = np.bincount(w_of, minlength=len(P)) > 1                        # split vertices: creases and UV seams
    if keep_open:
        e = np.sort(np.concatenate([Fw[:, [0, 1]], Fw[:, [1, 2]], Fw[:, [2, 0]]]), 1)
        u, c = np.unique(e, axis=0, return_counts=True)
        twins[u[c == 1].ravel()] = True
    X = np.c_[mesh.AO, mesh.UV]
    tolA = np.array([tol_ao, tol_uv, tol_uv])
    lab = patches(mesh)
    order = np.argsort(lab, kind='stable'); bounds = np.r_[0, np.cumsum(np.bincount(lab))]
    split_of = {}

    def patch_A(l, vs):
        if l not in split_of:
            fl = order[bounds[l]:bounds[l + 1]]
            pairs = np.unique(np.stack([Fw[fl].ravel(), F[fl].ravel()], 1), axis=0)
            if len(np.unique(pairs[:, 0])) != len(pairs):
                split_of[l] = None                                         # a seam inside the patch
            else:
                m = np.full(len(P), -1, 'i8'); m[pairs[:, 0]] = pairs[:, 1]; split_of[l] = m
        m = split_of[l]
        if m is None:
            if diag is not None:
                diag['seam_patches'] = diag.get('seam_patches', 0) + 1
            return None
        return X[m[vs]]

    fixed = set(np.unique(lab[keep]).tolist()) if keep is not None else set()
    T, tl = remesh_mesh(P, Fw, X[first], tol_h, tolA, lab, normal_of=lambda l: _direction(mesh, lab, order, bounds, l),
                        tol_b=tol_b, fixed=fixed, fixed_vertex=twins, diag=diag, patch_A=patch_A, return_labels=True)
    # back to split vertices. A kept patch's faces come out as its input faces, in order: those corners as they were.
    # A remeshed patch holds no seam (patch_A gave its attributes), so its welded ids map to split ids one to one.
    out = np.empty_like(T)
    for l in np.unique(tl).tolist():
        rows = np.flatnonzero(tl == l)
        fl = order[bounds[l]:bounds[l + 1]]
        if len(rows) == len(fl) and np.array_equal(T[rows], Fw[fl]):
            out[rows] = F[fl]
            continue
        m = np.full(len(P), -1, 'i8'); m[Fw[fl].ravel()] = F[fl].ravel()
        out[rows] = m[T[rows]]
    assert (out >= 0).all()
    if any(a > b for a, b in zip(_edge_defects(w_of[out]), _edge_defects(Fw))):   # last guard: never less watertight
        if diag is not None:
            diag['reverted'] = True
        return mesh
    face_of = order[bounds[tl]]                                            # a face of each output face's patch
    used = np.unique(out); remap = np.full(len(V), -1, 'i8'); remap[used] = np.arange(len(used))
    return dsl.Mesh(V[used], remap[out], mesh.N[used], mesh.UV[used], mesh.AO[used], mesh.material[face_of],
                    mesh.role[face_of], mesh.feature[face_of], mesh.features, tag=mesh.tag[face_of])


def _edge_defects(F):
    """(open edges, edges on more than two faces) of welded faces F."""
    e = np.sort(np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), 1)
    _, c = np.unique(e, axis=0, return_counts=True)
    return int((c == 1).sum()), int((c > 2).sum())


def _direction(mesh, lab, order, bounds, l):
    """A patch's projection direction: its faces' bin (they share one)."""
    f = order[bounds[l]]
    n, _ = face_normals(mesh.V, mesh.F[f:f + 1])
    return DIRECTIONS[np.argmax(n @ DIRECTIONS.T, 1)[0]]
