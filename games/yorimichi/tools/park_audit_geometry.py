"""Numpy-only geometry queries for the Crater Park comparison tool (metres, y up)."""
from dataclasses import dataclass
import time
import numpy as np


class Progress:
    def __init__(self):
        self.start = self.last = time.monotonic()

    def __call__(self, message, force=False):
        now = time.monotonic()
        if force or now - self.last >= 20:
            print(f"[{now-self.start:.1f}s] {message}", flush=True)
            self.last = now


progress = Progress()


def normals(triangles):
    cross = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    length = np.linalg.norm(cross, axis=1)
    return cross / np.maximum(length[:, None], 1e-30), length * .5


def closest(points, triangles):
    """Broadcast point/triangle closest points and barycentrics, including degenerate faces."""
    a, b, c = triangles[..., 0, :], triangles[..., 1, :], triangles[..., 2, :]
    ab, ac, ap = b-a, c-a, points-a
    dot = lambda x, y: np.sum(x*y, axis=-1)
    aa, bb, cc = dot(ab, ab), dot(ab, ac), dot(ac, ac)
    d, e = dot(ap, ab), dot(ap, ac)
    det = aa*cc-bb*bb
    safe = np.where(det > 1e-30, det, 1.)
    v, w = (cc*d-bb*e)/safe, (aa*e-bb*d)/safe
    bary = np.stack((1-v-w, v, w), axis=-1)
    q = a + v[..., None]*ab + w[..., None]*ac
    dist = dot(points-q, points-q)
    dist = np.where((det > 1e-30) & (bary.min(axis=-1) >= 0), dist, np.inf)
    for i, j in ((0, 1), (1, 2), (2, 0)):
        u, edge = triangles[..., i, :], triangles[..., j, :] - triangles[..., i, :]
        t = np.clip(dot(points-u, edge)/np.maximum(dot(edge, edge), 1e-30), 0, 1)
        candidate = u + t[..., None]*edge
        ds = dot(points-candidate, points-candidate)
        take = ds < dist
        weights = np.zeros_like(bary)
        weights[..., i], weights[..., j] = 1-t, t
        q = np.where(take[..., None], candidate, q)
        bary = np.where(take[..., None], weights, bary)
        dist = np.minimum(dist, ds)
    return dist, q, bary


@dataclass
class Node:
    lo: np.ndarray
    hi: np.ndarray
    ids: np.ndarray | None = None
    left: object = None
    right: object = None
    axis: int = 0
    split: float = 0.


class BVH:
    """Median AABB hierarchy. Query bounds are conservative; no nearest-neighbour cutoff."""
    def __init__(self, triangles=None, *, lo=None, hi=None, leaf=24):
        self.triangles = triangles
        self.lo = triangles.min(axis=1) if lo is None else lo
        self.hi = triangles.max(axis=1) if hi is None else hi
        centres = (self.lo + self.hi)*.5

        def build(ids):
            progress(f"building spatial index ({len(centres)} primitives)")
            if not len(ids):
                return None
            lower, upper = self.lo[ids].min(axis=0), self.hi[ids].max(axis=0)
            if len(ids) <= leaf:
                return Node(lower, upper, ids)
            axis = int(np.ptp(centres[ids], axis=0).argmax())
            mid = len(ids)//2
            ids = ids[np.argpartition(centres[ids, axis], mid)]
            split = float(centres[ids[mid], axis])
            return Node(lower, upper, left=build(ids[:mid]), right=build(ids[mid:]), axis=axis, split=split)

        self.root = build(np.arange(len(centres)))

    def nearest(self, points, chunk=1024):
        """@cc [owner:fontanierh,label:correctness] no-nearest-distance-cutoff
        Every nonempty target MUST yield the globally nearest triangle distance at each query point,
        to floating-point precision. Empty targets MUST return infinity and face index -1.
        """
        distances, faces, weights = [], [], []
        for start in range(0, len(points), chunk):
            p = points[start:start+chunk]
            best = np.full(len(p), np.inf)
            face = np.full(len(p), -1, dtype=np.int64)
            bary = np.zeros((len(p), 3))

            def visit(node, ids):
                if node is None or not len(ids):
                    return
                delta = np.maximum(np.maximum(node.lo-p[ids], p[ids]-node.hi), 0)
                ids = ids[np.sum(delta*delta, axis=1) <= best[ids] + 1e-24]
                if not len(ids):
                    return
                if node.ids is not None:
                    ds, _, ws = closest(p[ids, None, :], self.triangles[None, node.ids])
                    pick = ds.argmin(axis=1)
                    values = ds[np.arange(len(ids)), pick]
                    update = values < best[ids]
                    use = ids[update]
                    best[use] = values[update]
                    face[use] = node.ids[pick[update]]
                    bary[use] = ws[np.arange(len(ids)), pick][update]
                else:
                    near_left = p[ids, node.axis] < node.split
                    a, b = ids[near_left], ids[~near_left]
                    visit(node.left, a)
                    visit(node.right, b)
                    visit(node.right, a)
                    visit(node.left, b)

            visit(self.root, np.arange(len(p)))
            distances.append(np.sqrt(best)); faces.append(face); weights.append(bary)
            progress(f"nearest surfaces: {min(start+chunk, len(points))}/{len(points)} points")
        if not len(points):
            return np.zeros(0), np.zeros(0, dtype='i8'), np.zeros((0, 3))
        return np.concatenate(distances), np.concatenate(faces), np.concatenate(weights)

    def exposed(self, points, height=1., epsilon=1e-6, chunk=2048):
        """A point is buried if any triangle crosses its open upward segment (eps, height]."""
        result = []
        for start in range(0, len(points), chunk):
            p = points[start:start+chunk]
            blocked = np.zeros(len(p), bool)

            def visit(node, ids):
                if node is None or not len(ids):
                    return
                q = p[ids]
                ok = (~blocked[ids] & (q[:, 0] >= node.lo[0]-epsilon) &
                      (q[:, 0] <= node.hi[0]+epsilon) & (q[:, 2] >= node.lo[2]-epsilon) &
                      (q[:, 2] <= node.hi[2]+epsilon) & (q[:, 1]+height >= node.lo[1]) &
                      (q[:, 1]+epsilon < node.hi[1]))
                ids = ids[ok]
                if not len(ids):
                    return
                if node.ids is None:
                    visit(node.left, ids); visit(node.right, ids)
                    return
                t = self.triangles[node.ids]
                a, u, v = t[:, 0], t[:, 1]-t[:, 0], t[:, 2]-t[:, 0]
                d = p[ids, None, :] - a[None]
                det = u[:, 0]*v[:, 2]-u[:, 2]*v[:, 0]
                safe = np.where(np.abs(det) > 1e-20, det, 1.)
                b = (d[..., 0]*v[:, 2]-d[..., 2]*v[:, 0])/safe
                c = (u[:, 0]*d[..., 2]-u[:, 2]*d[..., 0])/safe
                y = a[:, 1] + b*u[:, 1] + c*v[:, 1]
                hit = ((np.abs(det) > 1e-20) & (b >= -1e-9) & (c >= -1e-9) &
                       (b+c <= 1+1e-9) & (y > p[ids, None, 1]+epsilon) &
                       (y <= p[ids, None, 1]+height))
                blocked[ids] |= np.any(hit, axis=1)

            visit(self.root, np.arange(len(p)))
            result.append(~blocked)
            progress(f"exposure: {min(start+chunk, len(points))}/{len(points)} points")
        return np.concatenate(result) if result else np.zeros(0, bool)


def pairs(first, second=None, epsilon=0.):
    """Yield unique primitive pairs whose expanded AABBs overlap, in bounded batches."""
    same = second is None
    second = first if same else second

    def walk(a, b):
        if a is None or b is None or np.any(a.lo > b.hi+epsilon) or np.any(b.lo > a.hi+epsilon):
            return
        if a is b and same and a.ids is None:
            yield from walk(a.left, a.left)
            yield from walk(a.left, a.right)
            yield from walk(a.right, a.right)
        elif a.ids is not None and b.ids is not None:
            i, j = np.meshgrid(a.ids, b.ids, indexing='ij')
            i, j = i.ravel(), j.ravel()
            keep = np.all(first.lo[i] <= second.hi[j]+epsilon, axis=1)
            keep &= np.all(second.lo[j] <= first.hi[i]+epsilon, axis=1)
            if same and a is b:
                keep &= i < j
            if keep.any():
                yield i[keep], j[keep]
        elif b.ids is not None or (a.ids is None and np.prod(a.hi-a.lo+epsilon) >= np.prod(b.hi-b.lo+epsilon)):
            yield from walk(a.left, b); yield from walk(a.right, b)
        else:
            yield from walk(a, b.left); yield from walk(a, b.right)

    yield from walk(first.root, second.root)


def projected_overlap(a, b, normal, area_epsilon=1e-10):
    """Positive projected overlap: SAT rejects shared edges; clip only surviving pairs."""
    if not len(a):
        return np.zeros(0)
    drop = np.abs(normal).argmax(axis=1)
    axes = np.array([[1, 2], [0, 2], [0, 1]])[drop]
    u = np.take_along_axis(a, axes[:, None, :], axis=2)
    v = np.take_along_axis(b, axes[:, None, :], axis=2)
    live = np.ones(len(a), bool)
    for poly in (u, v):
        for k in range(3):
            edge = poly[:, (k+1)%3] - poly[:, k]
            axis = np.stack((-edge[:, 1], edge[:, 0]), axis=1)
            x, y = np.sum(u*axis[:, None], axis=2), np.sum(v*axis[:, None], axis=2)
            live &= np.minimum(x.max(axis=1), y.max(axis=1)) - np.maximum(x.min(axis=1), y.min(axis=1)) > area_epsilon
    out = np.zeros(len(a))
    cross = lambda x, y: x[0]*y[1]-x[1]*y[0]
    for i in np.flatnonzero(live):
        subject = list(u[i])
        clip = v[i]
        sign = 1 if cross(clip[1]-clip[0], clip[2]-clip[0]) >= 0 else -1
        for k in range(3):
            origin, edge = clip[k], clip[(k+1)%3]-clip[k]
            old, subject = subject, []
            if not old:
                break
            for p, q in zip(old, old[1:]+old[:1]):
                dp, dq = sign*cross(edge, p-origin), sign*cross(edge, q-origin)
                if dp >= 0:
                    subject.append(p)
                if (dp >= 0) != (dq >= 0):
                    subject.append(p + (q-p)*dp/(dp-dq))
        if len(subject) >= 3:
            polygon = np.asarray(subject)
            area = abs(np.sum(polygon[:, 0]*np.roll(polygon[:, 1], -1) -
                              polygon[:, 1]*np.roll(polygon[:, 0], -1)))*.5
            out[i] = area/max(abs(normal[i, drop[i]]), 1e-30)
    return out
