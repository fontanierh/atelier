"""A constrained Delaunay triangulation in plan, pure Python + numpy (the repo has no scipy).

triangulate(points (n, 2), loops [index arrays], interior=None) -> faces (m, 3), counter-clockwise in (x, z) seen from
+y... precisely: counter-clockwise in the (x, z) plane's own orientation, i.e. cross2(b - a, c - a) > 0 with
cross2(u, v) = u.x v.z - u.z v.x. (A face with that plan winding has a DOWNWARD 3D normal by the right-hand rule in
(x, y, z); callers flip it for upward ground.)

Every loop edge (loop[i], loop[i + 1], closed) is an edge of the result. Triangles are kept where the even-odd count
of loops around them is odd: the first loop is the outline, the others holes (or islands inside holes).

Incremental Lawson insertion in spatial (Z-order) order with walking point location, then constraint recovery by
flips (Sloan 1993), a Delaunay re-legalisation of the free edges, and an even-odd flood fill.
"""
import numpy as np


def _orient2d(ax, ay, bx, by, cx, cy):
    """Signed area, with an exact fallback when cancellation makes its sign uncertain.

    A point almost on an edge must not lie to the right of both directed copies of
    that edge: the point-location walk would bounce between its adjacent faces.
    The bound includes the coordinate subtractions and the determinant products.
    """
    left = (bx - ax) * (cy - ay)
    right = (by - ay) * (cx - ax)
    det = left - right
    if abs(det) > 3.3306690738754716e-16 * (abs(left) + abs(right)):
        return det
    from fractions import Fraction
    ax, ay, bx, by, cx, cy = map(Fraction, (ax, ay, bx, by, cx, cy))
    return float((bx - ax) * (cy - ay) - (by - ay) * (cx - ax))


class CDTError(RuntimeError):
    """`vertices`: the input point indices involved (two crossing segments a-b and x-y), when known."""
    def __init__(self, message, vertices=()):
        super().__init__(message)
        self.vertices = tuple(int(v) for v in vertices)


def _zorder(p):
    q = ((p - p.min(0)) / max(np.ptp(p, 0).max(), 1e-12) * 65535).astype('u8')
    code = np.zeros(len(p), 'u8')
    for bit in range(16):
        code |= ((q[:, 0] >> np.uint64(bit)) & np.uint64(1)) << np.uint64(2 * bit)
        code |= ((q[:, 1] >> np.uint64(bit)) & np.uint64(1)) << np.uint64(2 * bit + 1)
    return np.argsort(code, kind='stable')


class _T:
    def __init__(self, P):
        self.X = [float(x) for x in P[:, 0]]; self.Y = [float(y) for y in P[:, 1]]
        self.tv = []; self.tn = []; self.vt = [-1] * len(self.X)
        self.fixed = set()

    def orient(self, a, b, c):
        X, Y = self.X, self.Y
        return _orient2d(X[a], Y[a], X[b], Y[b], X[c], Y[c])

    def incircle(self, a, b, c, d):
        X, Y = self.X, self.Y
        adx, ady = X[a] - X[d], Y[a] - Y[d]
        bdx, bdy = X[b] - X[d], Y[b] - Y[d]
        cdx, cdy = X[c] - X[d], Y[c] - Y[d]
        ad, bd, cd = adx * adx + ady * ady, bdx * bdx + bdy * bdy, cdx * cdx + cdy * cdy
        return (adx * (bdy * cd - bd * cdy) - ady * (bdx * cd - bd * cdx) + ad * (bdx * cdy - bdy * cdx))

    def new(self, v, n):
        self.tv.append(v); self.tn.append(n)
        t = len(self.tv) - 1
        for x in v:
            self.vt[x] = t
        return t

    def fix(self, u, old, new):
        if u >= 0:
            n = self.tn[u]
            n[n.index(old)] = new

    def locate(self, p, t):
        steps = 0
        k = 0
        while True:
            steps += 1
            if steps > 4 * len(self.tv) + 100:
                raise CDTError('point location did not converge')
            v = self.tv[t]
            moved = False
            for r in range(3):
                i = (k + r) % 3
                a, b = v[(i + 1) % 3], v[(i + 2) % 3]
                o = self.orient(a, b, p)
                if o < 0:
                    u = self.tn[t][i]
                    if u < 0:
                        raise CDTError('point outside the triangulation')
                    t = u; moved = True; k = (k + 1) % 3
                    break
            if not moved:
                return t

    def insert(self, p, start, eps):
        t = self.locate(p, start)
        v = self.tv[t]
        X, Y = self.X, self.Y
        for x in v:
            if abs(X[x] - X[p]) <= eps and abs(Y[x] - Y[p]) <= eps:
                return t, x                     # a duplicate: merged onto the existing vertex
        # on an edge? (relative to the edge length)
        on = -1
        for i in range(3):
            a, b = v[(i + 1) % 3], v[(i + 2) % 3]
            L = ((X[b] - X[a]) ** 2 + (Y[b] - Y[a]) ** 2) ** .5
            if abs(self.orient(a, b, p)) <= eps * max(L, 1e-12):
                on = i
        stack = []
        if on < 0:
            a, b, c = v; na, nb, nc = self.tn[t]
            self.tv[t] = [a, b, p]; self.tn[t] = [-2, -2, nc]
            t2 = self.new([b, c, p], [-2, -2, na]); t3 = self.new([c, a, p], [-2, -2, nb])
            self.tn[t][0], self.tn[t][1] = t2, t3
            self.tn[t2][0], self.tn[t2][1] = t3, t
            self.tn[t3][0], self.tn[t3][1] = t, t2
            self.fix(na, t, t2); self.fix(nb, t, t3)
            for x in (a, b, p):
                self.vt[x] = t
            stack = [(t, 2), (t2, 2), (t3, 2)]
        else:
            k = on
            a, b, c = v[k], v[(k + 1) % 3], v[(k + 2) % 3]
            Nb, Nc = self.tn[t][(k + 1) % 3], self.tn[t][(k + 2) % 3]
            u = self.tn[t][k]
            if u < 0:
                raise CDTError('a point on the hull')
            j = self.tn[u].index(t); d = self.tv[u][j]
            Mc, Mb = self.tn[u][(j + 1) % 3], self.tn[u][(j + 2) % 3]
            self.tv[t] = [a, b, p]; self.tv[u] = [d, c, p]
            t2 = self.new([a, p, c], [-2, Nb, t]); u2 = self.new([d, p, b], [t, Mc, u])
            self.tn[t] = [u2, t2, Nc]; self.tn[u] = [t2, u2, Mb]
            self.tn[t2][0] = u; self.tn[u2][0] = t
            self.fix(Nb, t, t2); self.fix(Mc, u, u2)
            for x, tt in ((a, t), (b, t), (p, t), (d, u), (c, u)):
                self.vt[x] = tt
            stack = [(t, 2), (t2, 1), (u, 2), (u2, 1)]
            if (min(b, c), max(b, c)) in self.fixed:
                raise CDTError('a point on a constrained edge')
        self.legalize(stack)
        return t, p

    def flip(self, t, i):
        """Flip the edge opposite vertex i of t. Returns (t, u) as [p, x, q], [p, q, y]."""
        p = self.tv[t][i]; x = self.tv[t][(i + 1) % 3]; y = self.tv[t][(i + 2) % 3]
        A, B = self.tn[t][(i + 1) % 3], self.tn[t][(i + 2) % 3]
        u = self.tn[t][i]; j = self.tn[u].index(t); q = self.tv[u][j]
        C, D = self.tn[u][(j + 1) % 3], self.tn[u][(j + 2) % 3]
        self.tv[t] = [p, x, q]; self.tn[t] = [C, u, B]
        self.tv[u] = [p, q, y]; self.tn[u] = [D, A, t]
        self.fix(A, t, u); self.fix(C, u, t)
        self.vt[p] = t; self.vt[x] = t; self.vt[q] = t; self.vt[y] = u
        return t, u

    def legalize(self, stack):
        while stack:
            t, i = stack.pop()
            u = self.tn[t][i]
            if u < 0:
                continue
            p = self.tv[t][i]; x = self.tv[t][(i + 1) % 3]; y = self.tv[t][(i + 2) % 3]
            if (min(x, y), max(x, y)) in self.fixed:
                continue
            j = self.tn[u].index(t); q = self.tv[u][j]
            if self.incircle(p, x, y, q) > 0:
                t, u = self.flip(t, i)
                stack.append((t, 0)); stack.append((u, 0))

    def around(self, a):
        """Triangles round vertex a (a never on the hull: the super triangle surrounds everything)."""
        t0 = self.vt[a]
        if a not in self.tv[t0]:
            raise CDTError('vertex map out of date')
        out, t = [], t0
        while True:
            out.append(t)
            k = self.tv[t].index(a)
            t = self.tn[t][(k + 1) % 3]
            if t < 0 or t == t0 or len(out) > 10000:
                break
        return out

    def find_edge(self, a, b):
        for t in self.around(a):
            v = self.tv[t]
            if b in v:
                k = v.index(a); m = v.index(b)
                return t, 3 - k - m
        return None

    def crossing(self, a, b, x, y):
        """Do segment ab and segment xy cross properly?"""
        o1, o2 = self.orient(a, b, x), self.orient(a, b, y)
        o3, o4 = self.orient(x, y, a), self.orient(x, y, b)
        return o1 * o2 < 0 and o3 * o4 < 0

    def recover(self, a, b):
        if a == b:
            return
        if self.find_edge(a, b) is not None:
            self.fixed.add((min(a, b), max(a, b))); return
        # the edges crossing ab: start in the triangle round a that ab leaves through
        edges = []
        t = None
        for s in self.around(a):
            v = self.tv[s]; k = v.index(a); x, y = v[(k + 1) % 3], v[(k + 2) % 3]
            if self.orient(a, x, b) > 0 and self.orient(a, y, b) < 0:
                t = s; break
            if self.orient(a, x, b) == 0 and self._between(a, x, b) or self.orient(a, y, b) == 0 and self._between(a, y, b):
                raise CDTError('a vertex lies on a constrained segment')
        if t is None:
            raise CDTError('constrained segment start not found')
        while True:
            v = self.tv[t]
            # the edge of t that ab crosses, not touching the entry
            for i in range(3):
                x, y = v[(i + 1) % 3], v[(i + 2) % 3]
                if a in (x, y) or b in (x, y):
                    continue
                if self.crossing(a, b, x, y) and (min(x, y), max(x, y)) not in {e for e in edges}:
                    break
            else:
                raise CDTError('lost the constrained segment')
            if (min(x, y), max(x, y)) in self.fixed:
                raise CDTError('two constrained segments cross', (a, b, x, y))
            edges.append((min(x, y), max(x, y)))
            u = self.tn[t][i]; q = self.tv[u][self.tn[u].index(t)]
            if q == b:
                break
            if self.orient(a, b, q) == 0:
                raise CDTError('a vertex lies on a constrained segment')
            t = u
        queue = list(edges); guard = 0
        while queue:
            guard += 1
            if guard > 100 * len(edges) + 1000:
                raise CDTError('constraint recovery did not converge')
            x, y = queue.pop(0)
            f = self.find_edge(x, y)
            if f is None:
                continue
            t, i = f
            u = self.tn[t][i]; p = self.tv[t][i]; q = self.tv[u][self.tn[u].index(t)]
            # convex quad p-x-q-y: p and q on opposite sides of xy, x and y on opposite sides of pq
            if self.orient(p, q, x) * self.orient(p, q, y) >= 0:
                queue.append((x, y)); continue
            t, u = self.flip(t, i)
            if (p, q) in ((a, b), (b, a)):
                continue
            if self.crossing(a, b, p, q):
                queue.append((min(p, q), max(p, q)))
        if self.find_edge(a, b) is None:
            raise CDTError('constrained segment not recovered')
        self.fixed.add((min(a, b), max(a, b)))

    def _between(self, a, x, b):
        X, Y = self.X, self.Y
        return min(X[a], X[b]) <= X[x] <= max(X[a], X[b]) and min(Y[a], Y[b]) <= Y[x] <= max(Y[a], Y[b])


def triangulate(points, loops, eps=1e-9, segments=()):
    """Faces (m, 3) of the constrained Delaunay triangulation of `points` (n, 2) with the closed `loops` (index
    arrays) as constraints, keeping the even-odd inside (loops[0] the outline, the rest holes). Coincident points
    (within eps of the extent) merge onto the first; the faces use the first's index. `segments`: extra polylines
    (index arrays) whose edges are kept too, without changing which triangles are inside."""
    P = np.asarray(points, 'f8')
    if len(P) < 3:
        return np.zeros((0, 3), 'i8')
    centre = (P.min(0) + P.max(0)) / 2; scale = max(np.ptp(P, 0).max(), 1e-12)
    Q = (P - centre) / scale
    big = 50.
    S = np.vstack([Q, [[-big, -big], [big, -big], [0., big]]])
    T = _T(S)
    n = len(P); s0, s1, s2 = n, n + 1, n + 2
    T.new([s0, s1, s2], [-1, -1, -1])
    alias = np.arange(n)
    last = 0
    tol = eps
    for p in _zorder(Q):
        last, got = T.insert(int(p), last, tol)
        alias[p] = got
    def recover(a, b):
        try:
            T.recover(a, b)
        except CDTError as e:
            v = [i for i in e.vertices if i < n] or [a, b]
            where = ', '.join(f'{i} ({P[i][0]:.2f}, {P[i][1]:.2f})' for i in v)
            raise CDTError(f'{e} at vertices {where}', v) from None
    for loop in loops:
        idx = alias[np.asarray(loop, 'i8')]
        for i in range(len(idx)):
            recover(int(idx[i]), int(idx[(i + 1) % len(idx)]))
    region = set(T.fixed)
    # extra constrained polylines (open, or closed by repeating the first index): edges kept, region unchanged
    for chain in segments:
        idx = alias[np.asarray(chain, 'i8')]
        for a, b in zip(idx[:-1], idx[1:]):
            recover(int(a), int(b))
    # Delaunay again on the free edges
    stack = [(t, i) for t in range(len(T.tv)) for i in range(3)]
    T.legalize(stack)
    # even-odd depth: flood from the super triangle's corner triangles across edges, +1 across a constraint
    depth = [-1] * len(T.tv)
    start = [t for t in range(len(T.tv)) if s0 in T.tv[t] or s1 in T.tv[t] or s2 in T.tv[t]]
    from collections import deque
    queue = deque()
    for t in start:
        depth[t] = 0; queue.append(t)
    # a BFS by levels: free edges first (0-1 BFS)
    while queue:
        t = queue.popleft()
        v = T.tv[t]
        for i in range(3):
            u = T.tn[t][i]
            if u < 0:
                continue
            x, y = v[(i + 1) % 3], v[(i + 2) % 3]
            w = depth[t] + (1 if (min(x, y), max(x, y)) in region else 0)
            if depth[u] < 0 or w < depth[u]:
                depth[u] = w
                if w == depth[t]:
                    queue.appendleft(u)
                else:
                    queue.append(u)
    tv = np.asarray(T.tv, 'i8'); d = np.asarray(depth)
    keep = (d % 2 == 1) & (tv < n).all(1)
    return tv[keep]
