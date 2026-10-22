"""Closed solids for Crater Park v2, on the shared `dsl.Mesh`: the checks every primitive passes (watertight on the
welded topology, consistent winding, outward volume, no folds, wall thickness) and the builders the primitives close
their riding sheets with (quad grids, planar caps, swept tubes with parallel-transport frames, prisms).

Native metres, y up, plan (x, z); fronts counter-clockwise (an upward face has cross(b - a, c - a).y > 0). A crease is
two vertices at one position, so watertightness is checked on `Mesh.welded()`. Faces that only close a solid (its
bottom under the ground, a wall hidden where a deck continues at the same height) have role `base` and are never
exported; what is left is open exactly along the primitive's seams, which the network stitches.

UV modes (divided by dsl.UV_METRES, so in tiles):
- `wall`: u the plan arc length along the grid's rows, v the height: an exact isometry on a vertical wall;
- `arc`: u each column's own arc length along the rows, v each row's arc length across;
- `world`: (x, z), for flats.
"""
import itertools

import numpy as np

from . import dsl

WELD = 1e-7          # metres: positions this close are one vertex of the topology
RING_SPACING = 2.5   # metres between a tube's rings at most


# ---------------------------------------------------------------------------------------------------------- checks

def edge_report(F):
    """Undirected edges used once (open) or more than twice (non-manifold), directed edges used twice (a flipped face)."""
    if not len(F):
        return {'open': 0, 'nonmanifold': 0, 'flipped': 0}
    d = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]).astype('i8')
    u0 = np.minimum(d[:, 0], d[:, 1])
    u1 = np.maximum(d[:, 0], d[:, 1])
    _, cu = np.unique((u0 << 32) | u1, return_counts=True)
    _, cd = np.unique((d[:, 0] << 32) | d[:, 1], return_counts=True)
    return {'open': int((cu == 1).sum()), 'nonmanifold': int((cu > 2).sum()), 'flipped': int((cd > 1).sum())}


def volume(V, F):
    t = V[F]
    return float(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)


def check_closed(mesh, min_area=1e-9, name=None):
    """Raise unless the mesh (all roles, base included) is a closed, consistently wound, outward solid with no
    degenerate face. Returns its volume."""
    name = name or mesh.features[0]
    a = mesh.areas()
    if (a < min_area).any():
        raise ValueError(f'{name}: {int((a < min_area).sum())} degenerate faces')
    P, F = mesh.welded(WELD)
    r = edge_report(F)
    if r['open'] or r['nonmanifold'] or r['flipped']:
        raise ValueError(f'{name}: not watertight {r}')
    v = volume(P, F)
    if v <= 0:
        raise ValueError(f'{name}: inward volume {v}')
    return v


def check_open(mesh, name=None, min_area=1e-9):
    """Raise unless the mesh is consistently wound and manifold, open only along simple closed loops; return those
    loops as (k, 3) positions (a feature on the ground: its foot loops, which the ground fills)."""
    name = name or mesh.features[0]
    a = mesh.areas()
    if (a < min_area).any():
        raise ValueError(f'{name}: {int((a < min_area).sum())} degenerate faces')
    P, F = mesh.welded(WELD)
    r = edge_report(F)
    if r['nonmanifold'] or r['flipped']:
        raise ValueError(f'{name}: not manifold {r}')
    d = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]).astype('i8')
    u0 = np.minimum(d[:, 0], d[:, 1])
    u1 = np.maximum(d[:, 0], d[:, 1])
    _, inv, cu = np.unique((u0 << 32) | u1, return_inverse=True, return_counts=True)
    open_ = d[cu[inv.ravel()] == 1]
    nxt = {}
    for u, v in open_:
        if int(u) in nxt:
            raise ValueError(f'{name}: its open boundary branches at {P[u].round(3).tolist()}')
        nxt[int(u)] = int(v)
    loops, seen = [], set()
    for u0 in nxt:
        if u0 in seen:
            continue
        loop, u = [], u0
        while u not in seen:
            seen.add(u); loop.append(u)
            if u not in nxt:
                raise ValueError(f'{name}: its open boundary does not close at {P[u].round(3).tolist()}')
            u = nxt[u]
        if u != u0:
            raise ValueError(f'{name}: its open boundary is not a simple loop')
        loops.append(P[loop[::-1]])                      # the ground's side: counter-clockwise seen from above
    return loops


def check_folds(mesh, name=None, flat=.05):
    """Raise on any face folded over: its geometric normal against its corners' analytic normals, and (the ribbon
    regression, park-assist #13382) any mixed projected orientation among faces that are not near vertical, whatever
    sign the majority has. Run before any winding is normalised."""
    name = name or mesh.features[0]
    t = mesh.triangles()
    g = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    a = mesh.N[mesh.F].mean(1)
    big = np.linalg.norm(g, axis=1) > 1e-9
    against = big & ((g * a).sum(1) <= 0)
    gy = g[:, 1] / np.maximum(np.linalg.norm(g, axis=1), 1e-300)
    steep = np.abs(a[:, 1]) < flat * np.linalg.norm(a, axis=1)
    mixed = big & ~steep & (np.sign(gy) != np.sign(a[:, 1]))
    if against.any() or mixed.any():
        k = int(np.flatnonzero(against | mixed)[0])
        raise ValueError(f'{name}: {int(against.sum())} faces fold over and {int(mixed.sum())} have mixed projected '
                         f'orientation (first at {t[k].mean(0).round(2).tolist()}): the path bends tighter than the '
                         f'section reaches')


def segments_cross(P):
    """Whether the closed plan polygon P (n, 2) crosses itself (two non-adjacent edges intersect)."""
    a, b = P, np.roll(P, -1, 0)
    n = len(P)

    def orient(p, q, r):
        return (q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) - (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0])
    for i0 in range(0, n, 256):
        A, B = a[i0:i0 + 256, None], b[i0:i0 + 256, None]
        o1 = orient(A, B, a[None]); o2 = orient(A, B, b[None])
        o3 = orient(a[None], b[None], A); o4 = orient(a[None], b[None], B)
        hit = (o1 * o2 < 0) & (o3 * o4 < 0)
        i = np.arange(i0, min(i0 + 256, n))[:, None]; j = np.arange(n)[None]
        adj = (np.abs(i - j) <= 1) | (np.abs(i - j) == n - 1)
        if (hit & ~adj).any():
            return True
    return False


def thickness(mesh, role='side', reach=50., facing=-.5):
    """The least distance from the centre of each face of `role` inward (against its normal) to an opposing face of
    the solid (normals at more than 120 degrees: a slab's other side, not a slope it meets at a corner): a wall's
    thickness (`reach` when there is none)."""
    sel = np.flatnonzero(mesh.role == dsl.ROLE[role])
    if not len(sel):
        return np.inf
    t = mesh.triangles(); n = mesh.face_normals()
    best = np.inf
    for chunk in np.array_split(sel, max(1, len(sel) * len(t) // 2_000_000 + 1)):
        opp = ((n[chunk] @ n.T) <= facing).any(0)
        if not opp.any():
            continue
        sub_idx = np.flatnonzero(opp)
        dist = ray_hits(t[chunk].mean(1) - 1e-6 * n[chunk], -n[chunk], t[sub_idx])
        dist[(n[chunk] @ n[sub_idx].T) > facing] = np.inf
        same = chunk[:, None] == sub_idx[None, :]
        dist[same] = np.inf
        best = min(best, float(dist.min()))
    return min(best, reach)


def ray_hits(o, d, tri, eps=1e-12):
    """(k, m) distances along the rays (o, d) to the triangles (m, 3, 3), inf where missed (Moller-Trumbore)."""
    e1 = tri[:, 1] - tri[:, 0]; e2 = tri[:, 2] - tri[:, 0]
    p = np.cross(d[:, None], e2[None])
    det = np.einsum('kmj,mj->km', p, e1)
    ok = np.abs(det) > eps
    inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
    s = o[:, None] - tri[None, :, 0]
    u = np.einsum('kmj,kmj->km', s, p) * inv
    q = np.cross(s, e1[None])
    v = np.einsum('kj,kmj->km', d, q) * inv
    w = np.einsum('mj,kmj->km', e2, q) * inv
    hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9) & (w > 1e-7)
    return np.where(hit, w, np.inf)


# ---------------------------------------------------------------------------------------------------- triangulation

def _plane_2d(P):
    """2D coordinates of a planar loop P (n, 3) and its Newell normal."""
    n = np.zeros(3)
    Q = np.roll(P, -1, 0)
    n[0] = ((P[:, 1] - Q[:, 1]) * (P[:, 2] + Q[:, 2])).sum()
    n[1] = ((P[:, 2] - Q[:, 2]) * (P[:, 0] + Q[:, 0])).sum()
    n[2] = ((P[:, 0] - Q[:, 0]) * (P[:, 1] + Q[:, 1])).sum()
    n /= max(np.linalg.norm(n), 1e-300)
    ref = np.array([0., 1., 0.]) if abs(n[1]) < .9 else np.array([1., 0., 0.])
    e1 = np.cross(ref, n); e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1)
    return np.stack([P @ e1, P @ e2], 1), n


def ear_clip(P2):
    """Triangles (index triples into P2) of the simple polygon P2 (n, 2), wound as its vertex order. The best-shaped
    ear goes first; a vertex on a would-be diagonal blocks it, so no face is degenerate. No new vertices."""
    P2 = np.asarray(P2, 'f8')
    x = P2[:, 0] - P2[:, 0].mean(); y = P2[:, 1] - P2[:, 1].mean()
    area = .5 * (x * np.roll(y, -1) - np.roll(x, -1) * y).sum()
    Q = np.stack([x, y], 1)
    scale = max(np.ptp(Q, 0).max(), 1e-12)
    eps = 1e-12 * scale * scale
    rem = np.arange(len(P2)) if area > 0 else np.arange(len(P2))[::-1]
    out = []
    while len(rem) > 3:
        a, b, c = Q[np.roll(rem, 1)], Q[rem], Q[np.roll(rem, -1)]
        cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        cand = np.flatnonzero(cross > eps)
        if not len(cand):
            raise ValueError('ear_clip: no ear (the polygon is not simple)')
        A, B, C = a[cand], b[cand], c[cand]
        pts = Q[rem]

        def side(p, q, pts=pts):
            return ((q[:, None, 0] - p[:, None, 0]) * (pts[None, :, 1] - p[:, None, 1])
                    - (q[:, None, 1] - p[:, None, 1]) * (pts[None, :, 0] - p[:, None, 0]))
        inside = (side(A, B) >= -eps) & (side(B, C) >= -eps) & (side(C, A) >= -eps)
        r = len(rem); k = np.arange(len(cand))
        for off in (-1, 0, 1):
            inside[k, (cand + off) % r] = False
        for corner in (A, B, C):                                  # a pinch vertex at an ear corner does not block it
            inside &= ~(np.abs(pts[None] - corner[:, None]).max(-1) <= 1e-12 * scale)
        ok = ~inside.any(1)
        if not ok.any():
            raise ValueError('ear_clip: no free ear (the polygon is not simple)')
        l2 = ((B - A) ** 2).sum(1) + ((C - B) ** 2).sum(1) + ((A - C) ** 2).sum(1)
        q = np.where(ok, cross[cand] / np.maximum(l2, 1e-300), -1)
        i = cand[int(np.argmax(q))]
        out.append((rem[(i - 1) % r], rem[i], rem[(i + 1) % r]))
        rem = np.delete(rem, i)
    out.append(tuple(rem))
    tris = np.array(out, 'i8')
    return tris if area > 0 else tris[:, [0, 2, 1]]


# ----------------------------------------------------------------------------------------------------------- builders

def _uv(P, mode):
    """Per-vertex UVs (a, b, 2) of a grid P (a, b, 3), in tiles."""
    if mode == 'world':
        uv = P[..., [0, 2]]
    elif mode == 'wall':
        plan = np.concatenate([np.zeros((1, P.shape[1])),
                               np.cumsum(np.linalg.norm(np.diff(P[..., [0, 2]], axis=0), axis=-1), 0)])
        uv = np.stack([plan, P[..., 1]], -1)
    else:
        along = np.concatenate([np.zeros((1, P.shape[1])), np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=-1), 0)])
        across = np.concatenate([np.zeros((P.shape[0], 1)), np.cumsum(np.linalg.norm(np.diff(P, axis=1), axis=-1), 1)], 1)
        uv = np.stack([along, across], -1)
    return uv / dsl.UV_METRES


def orient(F, V, outward):
    """Faces F wound so their summed normal points along `outward` ((3,) or a per-face (m, 3) direction)."""
    if not len(F):
        return F
    t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    out = np.broadcast_to(np.asarray(outward, 'f8'), n.shape)
    return F if (n * out).sum() >= 0 else F[:, ::-1].copy()


def grid(P, *, outward, feature, material=dsl.CONCRETE, role=dsl.SIDE, tag='', uv='wall', closed_rows=False,
         normals=None):
    """A Mesh from a quad grid P (a, b, 3): faces between rows i, i+1 and columns j, j+1, split on the shorter 3D
    diagonal, wound toward `outward`; `closed_rows` joins the last row to the first. Collapsed faces (a row or column
    of one point, e.g. a wall of zero height) are dropped."""
    P = np.asarray(P, 'f8')
    a, b = P.shape[:2]
    if closed_rows:
        P = np.concatenate([P, P[:1]]); a += 1
    idx = np.arange(a * b).reshape(a, b)
    V = P.reshape(-1, 3)
    i = idx[:-1, :-1].ravel(); j = idx[1:, :-1].ravel(); k = idx[1:, 1:].ravel(); m = idx[:-1, 1:].ravel()
    short = np.linalg.norm(V[i] - V[k], axis=1) <= np.linalg.norm(V[j] - V[m], axis=1)
    F = np.concatenate([np.where(short[:, None], np.stack([i, j, k], 1), np.stack([i, j, m], 1)),
                        np.where(short[:, None], np.stack([i, k, m], 1), np.stack([j, k, m], 1))])
    t = V[F]
    F = F[np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-12]
    out = np.asarray(outward, 'f8')
    if out.ndim > 1:                                             # per row (a, 3) or per vertex (a, b, 3)
        out = np.broadcast_to(out[:, None] if out.ndim == 2 else out, (len(out), b, 3))
        if closed_rows:
            out = np.concatenate([out, out[:1]])
        out = out.reshape(-1, 3)[F].mean(1)
    F = orient(F, V, out)
    UV = _uv(P, uv).reshape(-1, 2)
    return dsl.Mesh.part(V, F, material=material, role=role, feature=feature, UV=UV, tag=tag, N=normals)


def _inside(Q, P2):
    """Even-odd: which points Q (m, 2) lie inside the polygon P2 (n, 2)."""
    a, b = P2, np.roll(P2, -1, 0)
    inside = np.zeros(len(Q), bool)
    for i0 in range(0, len(P2), 512):
        A, B = a[i0:i0 + 512], b[i0:i0 + 512]
        cond = (A[None, :, 1] > Q[:, None, 1]) != (B[None, :, 1] > Q[:, None, 1])
        x = A[None, :, 0] + (Q[:, None, 1] - A[None, :, 1]) * (B[None, :, 0] - A[None, :, 0]) / np.where(
            B[None, :, 1] != A[None, :, 1], B[None, :, 1] - A[None, :, 1], 1.)
        inside ^= (cond & (Q[:, None, 0] < x)).sum(1) % 2 == 1
    return inside


def _seg_distance(Q, P2):
    a, b = P2, np.roll(P2, -1, 0)
    best = np.full(len(Q), np.inf)
    for i0 in range(0, len(P2), 512):
        A, B = a[i0:i0 + 512], b[i0:i0 + 512]
        d = B - A
        u = np.clip(((Q[:, None] - A[None]) * d[None]).sum(-1) / np.maximum((d * d).sum(1), 1e-300)[None], 0, 1)
        best = np.minimum(best, np.linalg.norm(Q[:, None] - (A[None] + u[..., None] * d[None]), axis=-1).min(1))
    return best


STEINER_MAX = 2.0     # metres: interior points of a planar cap at most this far apart
STEINER_MIN = .25


def fill(P2, spacing=None):
    """Faces (index triples) filling the simple polygon P2 (n, 2) without moving or adding boundary vertices: a
    constrained Delaunay triangulation (cdt.py) over the boundary plus interior points on a grid (as fine as the
    boundary's spacing and the polygon's size ask, STEINER_MIN..STEINER_MAX), kept clear of the boundary, so a dense
    curved edge never fans to one far corner. A failed triangulation is retried at nearby spacings, then ear-clipped.
    Returns (faces, interior points (k, 2)); faces wound as P2's order."""
    from .cdt import CDTError, triangulate
    P2 = np.asarray(P2, 'f8')
    seg = np.linalg.norm(np.roll(P2, -1, 0) - P2, axis=1)
    x = P2[:, 0] - P2[:, 0].mean(); y = P2[:, 1] - P2[:, 1].mean()
    area = .5 * (x * np.roll(y, -1) - np.roll(x, -1) * y).sum()
    h0 = spacing or float(np.clip(max(2 * np.median(seg), np.sqrt(abs(area)) / 12), STEINER_MIN, STEINER_MAX))
    lo, hi = P2.min(0), P2.max(0)
    for h in (h0, h0 * 1.13, h0 * .89, h0 * 1.27):
        gx = np.arange(lo[0] + h / 2, hi[0], h); gy = np.arange(lo[1] + h / 2, hi[1], h)
        G = np.stack(np.meshgrid(gx, gy), -1).reshape(-1, 2) if len(gx) and len(gy) else np.zeros((0, 2))
        if len(G):
            G = G[_inside(G, P2)]
        if len(G):
            G = G[_seg_distance(G, P2) > .6 * h]
        pts = np.concatenate([P2, G])
        try:
            F = triangulate(pts, [np.arange(len(P2))])
        except CDTError:
            continue
        if len(F) != len(P2) - 2 + 2 * len(G):               # not a full triangulation of the polygon: retry
            continue
        t = pts[F]
        cw = ((t[:, 1, 0] - t[:, 0, 0]) * (t[:, 2, 1] - t[:, 0, 1])
              - (t[:, 1, 1] - t[:, 0, 1]) * (t[:, 2, 0] - t[:, 0, 0])) < 0
        F = np.where(cw[:, None], F[:, [0, 2, 1]], F)        # counter-clockwise in P2's plane
        return (F if area > 0 else F[:, [0, 2, 1]]), G
    return ear_clip(P2), np.zeros((0, 2))


def polygon(loop, *, outward, feature, material=dsl.CONCRETE, role=dsl.SIDE, tag='', uv=None, steiner=True):
    """A planar cap over the 3D loop (n, 3) facing `outward`: a constrained Delaunay fill with interior points (fill),
    or ear-clipped (steiner=False: no new vertices at all). UVs: world (x, z) when the cap is near level, else
    (horizontal distance in its plane, y)."""
    L = np.asarray(loop, 'f8')
    P2, n = _plane_2d(L)
    if steiner:
        F, G = fill(P2)
        if len(G):                                           # interior points back into 3D on the loop's plane
            e1 = np.cross(np.array([0., 1., 0.]) if abs(n[1]) < .9 else np.array([1., 0., 0.]), n)
            e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1)
            d = L[0] @ n
            L = np.concatenate([L, G[:, :1] * e1 + G[:, 1:] * e2 + d * n])
    else:
        F = ear_clip(P2)
    F = orient(F, L, outward)
    if uv is None:
        uv = 'world' if abs(n[1]) > .7 else 'vertical'
    if uv == 'world':
        UV = L[:, [0, 2]]
    else:
        h = np.array([n[2], 0., -n[0]]); h /= max(np.linalg.norm(h), 1e-300)
        UV = np.stack([L @ h, L[:, 1]], 1)
    nn = n if (n @ np.asarray(outward, 'f8').reshape(-1, 3).mean(0)) >= 0 else -n
    N = np.broadcast_to(nn, L.shape)
    return dsl.Mesh.part(L, F, material=material, role=role, feature=feature, UV=UV / dsl.UV_METRES, tag=tag, N=N)


def transport_frames(P, closed=False):
    """Unit tangents and rotation-minimising normals along the polyline P (k, 3) (double reflection); a closed loop's
    leftover twist is spread evenly along it, so the frame meets itself."""
    k = len(P)
    if closed:
        s = np.roll(P, -1, 0) - P; s /= np.linalg.norm(s, axis=1, keepdims=True)
        T = np.roll(s, 1, 0) + s
    else:
        s = np.diff(P, axis=0); s /= np.linalg.norm(s, axis=1, keepdims=True)
        T = np.concatenate([s[:1], s[:-1] + s[1:], s[-1:]])
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    r = np.array([0., 1., 0.]) - T[0] * T[0, 1]
    if np.linalg.norm(r) < 1e-6:
        r = np.cross(T[0], [1., 0., 0.])
    r /= np.linalg.norm(r)
    N = np.zeros((k, 3)); N[0] = r
    for i in range(k if closed else k - 1):
        j = (i + 1) % k
        v1 = P[j] - P[i]; c1 = v1 @ v1
        rL = r - 2 / c1 * (v1 @ r) * v1; tL = T[i] - 2 / c1 * (v1 @ T[i]) * v1
        v2 = T[j] - tL; c2 = v2 @ v2
        r = rL - 2 / c2 * (v2 @ rL) * v2 if c2 > 1e-300 else rL
        if j:
            N[j] = r
    if closed:
        B0 = np.cross(T[0], N[0])
        twist = np.arctan2(r @ B0, r @ N[0])
        s = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
        ang = -twist * s / (s[-1] + np.linalg.norm(P[0] - P[-1]))
        B = np.cross(T, N)
        N = np.cos(ang)[:, None] * N + np.sin(ang)[:, None] * B
    N -= T * (N * T).sum(1, keepdims=True)
    return T, N / np.linalg.norm(N, axis=1, keepdims=True)


def tube(axis, radius, *, feature, sides=12, closed=False, role=dsl.COPING, material=dsl.STEEL, tag=''):
    """A closed tube of `radius` round the polyline `axis` (k, 3): one ring of `sides` per axis point (so a straight
    run is two rings), parallel-transport frames, rings mitred at corners so both legs keep the radius; an open tube
    ends in flat discs. Smooth normals round the tube; u along it, v round it."""
    P = np.asarray(axis, 'f8')
    if closed and np.linalg.norm(P[0] - P[-1]) < 1e-9:
        P = P[:-1]
    # rings at most RING_SPACING apart, so a long straight run's faces stay well shaped (C's V9)
    Q = np.concatenate([P, P[:1]]) if closed else P
    out = [Q[:1]]
    for a, b in itertools.pairwise(Q):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / RING_SPACING)))
        out.append(a + (b - a) * (np.arange(1, n + 1) / n)[:, None])
    P = np.concatenate(out)
    if closed:
        P = P[:-1]
    k = len(P)
    T, N = transport_frames(P, closed)
    B = np.cross(T, N)
    ang = 2 * np.pi * np.arange(sides + 1) / sides                # the seam's ring twice, for its UVs
    radial = np.cos(ang)[None, :, None] * N[:, None] + np.sin(ang)[None, :, None] * B[:, None]
    ring = P[:, None] + radius * radial
    seg = (np.roll(P, -1, 0) - P) if closed else np.concatenate([np.diff(P, axis=0)[:1], np.diff(P, axis=0)])
    prev = (np.roll(seg, 1, 0) if closed else seg)
    prev = prev / np.linalg.norm(prev, axis=1, keepdims=True)
    cos_half = np.clip((prev * T).sum(1), .2, 1.)
    bend = prev - T * (prev * T).sum(1, keepdims=True)
    nb = np.linalg.norm(bend, axis=1, keepdims=True)
    bend = np.where(nb > 1e-9, bend / np.maximum(nb, 1e-300), 0.)
    comp = ((ring - P[:, None]) * bend[:, None]).sum(-1, keepdims=True)
    ring = ring + (1 / cos_half - 1)[:, None, None] * comp * bend[:, None]
    G = np.concatenate([ring, ring[:1]]) if closed else ring
    R = np.concatenate([radial, radial[:1]]) if closed else radial
    along = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(G[:, 0] - radius * R[:, 0], axis=0), axis=1))])
    UV = np.stack(np.broadcast_arrays(along[:, None], (ang * radius)[None, :]), -1) / dsl.UV_METRES
    a, b = G.shape[:2]
    idx = np.arange(a * b).reshape(a, b)
    i = idx[:-1, :-1].ravel(); j = idx[1:, :-1].ravel(); kk = idx[1:, 1:].ravel(); m = idx[:-1, 1:].ravel()
    F = np.concatenate([np.stack([i, j, kk], 1), np.stack([i, kk, m], 1)])
    V = G.reshape(-1, 3)
    out = (R.reshape(-1, 3)[F]).mean(1)
    t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    if (n * out).sum() < 0:
        F = F[:, ::-1].copy()
    parts = [dsl.Mesh.part(V, F, material=material, role=role, feature=feature, UV=UV.reshape(-1, 2),
                           N=R.reshape(-1, 3), tag=tag)]
    if not closed:
        for end, sign in ((0, -1.), (k - 1, 1.)):
            loop = ring[end, :-1]
            parts.append(polygon(loop, outward=sign * T[end], feature=feature, material=material, role=role, tag=tag))
    return dsl.Mesh.concat(parts)


def prism(loop, y0, y1, *, feature, material=dsl.LEDGE, top_role=dsl.RIDING, side_role=dsl.SIDE, tag=''):
    """A vertical prism over the plan loop (k, 2) from y0 to y1 (a post, a pad): top `top_role`, sides `side_role`,
    bottom `base` (it sits on a support surface the network cuts round its footprint)."""
    L = np.asarray(loop, 'f8')
    area = .5 * (L[:, 0] * np.roll(L[:, 1], -1) - np.roll(L[:, 0], -1) * L[:, 1]).sum()
    if area < 0:
        L = L[::-1]
    k = len(L)
    bot = np.stack([L[:, 0], np.full(k, y0), L[:, 1]], 1); top = bot + [0., y1 - y0, 0.]
    G = np.stack([bot, top], 1)
    parts = []
    for i in range(k):                                           # one wall face pair per edge: sharp prism corners
        q = np.stack([G[i], G[(i + 1) % k]])
        d = q[1, 0] - q[0, 0]
        parts.append(grid(q, outward=np.array([d[2], 0., -d[0]]), feature=feature, material=material, role=side_role,
                          tag=tag))
    parts.append(polygon(top, outward=[0., 1., 0.], feature=feature, material=material, role=top_role, tag=tag))
    parts.append(polygon(bot, outward=[0., -1., 0.], feature=feature, material=material, role=dsl.BASE))
    return dsl.Mesh.concat(parts)
