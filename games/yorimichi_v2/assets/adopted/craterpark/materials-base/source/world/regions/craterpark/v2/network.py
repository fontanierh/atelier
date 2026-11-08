"""The shared boundary-curve network (plan/pipeline.md 3.3, review point 3): every seam is sampled once.

Usage:
    net = Network()
    net.add('qp_path', path)                         # a curve shared by several regions
    net.propose('qp_path', qp_t, priority=1)         # each region proposes its stations
    net.propose('qp_path', [12.5], semantic=True)    # a real corner / crossing: always kept, never moved
    net.merge()                                      # sorted union; non-semantic samples closer than tol merge
    t = net.samples('qp_path')                       # every region meshes with exactly these stations

Merging keeps every semantic sample and the order of all samples. A non-semantic sample within `tol` of a kept one
is dropped (the higher priority wins between two non-semantic ones; then the earlier proposal). Curve ends are
semantic.
"""
import numpy as np


class Network:
    def __init__(self, tol=.02):
        self.tol = tol
        self.curves, self.proposals, self.final = {}, {}, {}

    def add(self, key, curve):
        if key in self.curves:
            raise KeyError(f'curve {key!r} already in the network')
        self.curves[key] = curve
        self.proposals[key] = [(np.asarray([0., curve.length]), 1 << 30, True)]
        b = curve.breaks()
        self.proposals[key].append((np.asarray(b, 'f8'), 1 << 30, True))
        return key

    def propose(self, key, t, priority=0, semantic=False):
        if key in self.final:
            raise RuntimeError(f'curve {key!r} already merged')
        self.proposals[key].append((np.asarray(t, 'f8').ravel(), priority, semantic))

    def merge(self, tol=None):
        tol = self.tol if tol is None else tol
        for key, props in self.proposals.items():
            t = np.concatenate([p[0] for p in props])
            pr = np.concatenate([np.full(len(p[0]), p[1]) for p in props])
            sem = np.concatenate([np.full(len(p[0]), p[2]) for p in props])
            order = np.arange(len(t))
            # semantic first, then priority (high first), then proposal order
            rank = np.lexsort((order, -pr, ~sem))
            kept = []
            kept_sem = np.zeros(0)
            for i in rank:
                x = t[i]
                if sem[i]:
                    if not len(kept) or np.min(np.abs(np.asarray(kept) - x)) > 1e-9:
                        kept.append(x)
                    continue
                if np.min(np.abs(np.asarray(kept) - x)) > tol if kept else True:
                    kept.append(x)
            del kept_sem
            self.final[key] = np.sort(np.asarray(kept))
        return self.final

    def samples(self, key):
        return self.final[key]


def fill(loop, normal):
    """Triangles (k, 3) filling the simple planar polygon through the 3D points `loop` (n, 3) (vertex order along the
    boundary, not repeated), facing `normal` (3,): ear clipping on the projection, no new vertices."""
    loop = np.asarray(loop, 'f8'); n = np.asarray(normal, 'f8'); n = n / np.linalg.norm(n)
    a = np.cross(n, [1., 0., 0.] if abs(n[0]) < .9 else [0., 1., 0.]); a /= np.linalg.norm(a); b = np.cross(n, a)
    p = np.stack([loop @ a, loop @ b], 1)
    idx = list(range(len(p)))
    area = .5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
    if area < 0:
        idx.reverse()
    tris = []

    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])
    guard = 0
    while len(idx) > 3 and guard < 10 * len(p) ** 2:
        guard += 1
        m = len(idx); best = None
        for k in range(m):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
            if cross(p[i0], p[i1], p[i2]) <= 1e-14:
                continue
            ok = True
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                q = p[j]
                if (cross(p[i0], p[i1], q) >= -1e-12 and cross(p[i1], p[i2], q) >= -1e-12
                        and cross(p[i2], p[i0], q) >= -1e-12):
                    ok = False; break
            if ok:
                # prefer the fattest ear (fewer slivers)
                e = [np.linalg.norm(p[x] - p[y]) for x, y in ((i0, i1), (i1, i2), (i2, i0))]
                q = cross(p[i0], p[i1], p[i2]) / max(max(e) ** 2, 1e-18)
                if best is None or q > best[0]:
                    best = (q, k)
        if best is None:
            # collinear remainder: drop a flat vertex
            k = next(k for k in range(m) if abs(cross(p[idx[k - 1]], p[idx[k]], p[idx[(k + 1) % m]])) <= 1e-14)
            idx.pop(k); continue
        k = best[1]
        tris.append((idx[k - 1], idx[k], idx[(k + 1) % m])); idx.pop(k)
    if len(idx) == 3 and abs(cross(p[idx[0]], p[idx[1]], p[idx[2]])) > 1e-14:
        tris.append(tuple(idx))
    return np.asarray(tris, 'i8').reshape(-1, 3)


def strip(top, bottom):
    """Triangles joining two ordered vertex-index chains `top` and `bottom` (zipper: the shorter step advances), as
    index triples into the caller's vertex array; winding top[i] -> bottom[j] -> ... is left to the caller to flip.
    `top_pos`, `bottom_pos` are not needed when both chains have the same length (a quad strip)."""
    top, bottom = list(top), list(bottom)
    if len(top) == len(bottom):
        out = []
        for i in range(len(top) - 1):
            out += [(top[i], bottom[i], bottom[i + 1]), (top[i], bottom[i + 1], top[i + 1])]
        return np.asarray(out, 'i8').reshape(-1, 3)
    raise NotImplementedError('zipper between chains of different lengths: use zipper(positions, top, bottom)')


def zipper(V, top, bottom):
    """Triangles stitching two ordered chains of vertex indices (into V (n, 3)) running the same way: at each step the
    shorter new diagonal advances. No new vertices, so the seam conforms on both sides."""
    V = np.asarray(V, 'f8'); i = j = 0; out = []
    while i < len(top) - 1 or j < len(bottom) - 1:
        if i == len(top) - 1:
            adv_top = False
        elif j == len(bottom) - 1:
            adv_top = True
        else:
            adv_top = np.linalg.norm(V[top[i + 1]] - V[bottom[j]]) < np.linalg.norm(V[top[i]] - V[bottom[j + 1]])
        if adv_top:
            out.append((top[i], bottom[j], top[i + 1])); i += 1
        else:
            out.append((top[i], bottom[j], bottom[j + 1])); j += 1
    return np.asarray(out, 'i8').reshape(-1, 3)


def wall_strip(top, bottom, *, outward=None, feature='unnamed', material='material_023', role='side',
               uv_metres=9.):
    """A wall joining two regions whose heights differ along a shared curve (invariant I3): `top` (k, 3) and `bottom`
    (k, 3) are the two regions' own seam vertices at the same plan points (same network samples), so the wall shares
    every vertex position with both. `outward` (3,) picks the facing (default: the side the strip's normals already
    face). Vertex normals are the averaged face normals made horizontal (a ruled wall). u = length along the top (the clean-branch solidify rule), v = height."""
    from . import dsl
    top = np.asarray(top, 'f8'); bottom = np.asarray(bottom, 'f8'); k = len(top)
    V = np.concatenate([top, bottom])
    F = strip(np.arange(k), np.arange(k, 2 * k))
    t = V[F]; fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    if outward is not None and (fn @ np.asarray(outward, 'f8')).sum() < 0:
        F = F[:, ::-1].copy(); fn = -fn
    # no faces where the two seams meet (the wall's height runs out to zero)
    keep = np.linalg.norm(fn, axis=1) > 1e-10
    u = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(top[:, [0, 2]], axis=0), axis=1))])
    UV = np.concatenate([np.stack([u, top[:, 1]], 1), np.stack([u, bottom[:, 1]], 1)]) / uv_metres
    mesh = dsl.Mesh.part(V, F[keep], material=material, role=role, feature=feature, UV=UV)
    mesh.N[:] = dsl.vertex_normals(V, F[keep]) * [1, 0, 1]
    n = np.linalg.norm(mesh.N, axis=1, keepdims=True)
    mesh.N = np.where(n > 1e-12, mesh.N / np.maximum(n, 1e-12), dsl.vertex_normals(V, F[keep]))
    return mesh
