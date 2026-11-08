"""Crater Park v2 geometry validators (pure numpy; native frame: metres, x, y up, z).

Every owner complaint about r4 has a check that fails the build if it comes back (plan/pipeline.md section 8).
Each check returns a dict {'ok', numbers..., 'failures': [{'where': [x, y, z], ...}]}: the worst locations, in native
metres, so a dev-mode note can be matched against them. `validate()` runs them all and writes `geometry-report.json`.

- overlaps        V3   coplanar or near-coplanar overlapping faces within and between meshes (flicker)
- topology        V2/V4 open, non-manifold and mis-wound edges, T-junctions, degenerate faces; closed solids watertight
- protrusions     -    anything standing above a lane's riding surface inside its corridor ("popping out of the ground")
- thin_walls      V5   back-to-back faces closer than 0.30 m (fins, slabs, double-sided sheets); exact face-pair test
- plan_width      V5   exact minimum plan width of raised regions (inward normal rays, evaluated at breakpoints)
- budgets         V14  render and collision triangle counts, per mesh, per 200 m cube

Input meshes are `Mesh` (or anything `as_mesh` adapts: a dict or object with V/F or positions/triangles).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

WELD = 1e-5          # metres: the grid on which corners are one vertex (park-assist's harness default)
T_TOL = 1e-4         # metres: a vertex this close to the inside of an open edge is a T-junction
EPS = .005           # metres: two parallel faces this close overlap (flicker)
ANGLE = .5           # degrees between their normals at most
MIN_AREA = 1e-6      # square metres of projected overlap at least, for a pair to count
THIN = .30           # metres: the thinnest a wall, slab or raised region may be
THIN_AREA = 1e-3     # square metres of facing overlap at least, for a thin pair to count
THIN_ANGLE = 30.     # degrees from antiparallel at most, for two faces to be a wall's two sides
TOL_UP = .02         # metres above a riding surface: anything higher in a lane corridor protrudes
HEADROOM = 3.        # metres over a riding surface checked for protrusions (r4's span HEADROOM)
SAMPLE = .1          # metres between the sample points of a face tested for protrusion
FAILURES = 50        # worst locations kept per check
BUDGETS = {'render': 350_000, 'collision': 250_000, 'render_mesh': 30_000, 'render_meshes': 80,
           'collision_cube': 100_000, 'coping': 25_000}
CUBE = 200.          # metres: the in-game skating snapshot's cube
CUBE_STRIDE = 50.    # metres between the sliding cubes' corners
EXEMPT_THIN = ('coping', 'rail')   # roles designed thinner than THIN (render-only tubes, grind rails)


# ---------------------------------------------------------------------------------------------------- input

@dataclass
class Mesh:
    """One mesh of the park. V (n,3) native metres, F (m,3) int. Per face: feature (int, -1 none). role: riding |
    side | ground | solid | coping | rail | dressing. closed: a solid, which must be watertight."""
    name: str
    V: np.ndarray
    F: np.ndarray
    domain: str = 'render'
    role: str = 'riding'
    feature: np.ndarray | None = None
    closed: bool = False
    material: str | None = None
    uv: np.ndarray | None = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        self.V = np.asarray(self.V, 'f8').reshape(-1, 3)
        self.F = np.asarray(self.F, 'i8').reshape(-1, 3)
        if self.feature is None:
            self.feature = np.full(len(self.F), -1, 'i8')
        else:
            self.feature = np.broadcast_to(np.asarray(self.feature, 'i8'), (len(self.F),)).copy()

    @property
    def T(self):
        return self.V[self.F]


def as_mesh(m, **kw):
    """A Mesh from a Mesh, a dict or an object with V/F, positions/triangles or vertices/faces (agent A's type)."""
    if isinstance(m, Mesh):
        return m
    get = (lambda k: m.get(k)) if isinstance(m, dict) else (lambda k: getattr(m, k, None))
    pick = lambda *ks: next((get(k) for k in ks if get(k) is not None), None)
    V = pick('V', 'positions', 'vertices', 'verts'); F = pick('F', 'triangles', 'faces', 'tris')
    args = dict(name=pick('name') or 'mesh', V=V, F=F, domain=pick('domain') or 'render', role=pick('role') or 'riding',
                feature=pick('feature', 'features', 'face_feature'), closed=bool(pick('closed') or False),
                material=pick('material'), uv=pick('uv', 'corner_uv'))
    args.update(kw)
    return Mesh(**args)


def soup_to_mesh(T, name, weld=WELD, **kw):
    """A welded Mesh from a triangle soup (k,3,3): corners on one `weld` grid point are one vertex."""
    T = np.asarray(T, 'f8').reshape(-1, 3, 3)
    q = np.round(T.reshape(-1, 3) / weld).astype('i8')
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    return Mesh(name, T.reshape(-1, 3)[first], inv.reshape(-1, 3), **kw)


def load_unreal_bin(path, name=None, **kw):
    """An imported-geometry .bin (float64 (n,3,3) Unreal cm, x z y) as a welded native Mesh."""
    T = np.fromfile(path, 'f8').reshape(-1, 3, 3)[:, :, [0, 2, 1]] / 100.
    return soup_to_mesh(T, name or Path(path).stem, **kw)


def crop(mesh, box, pad=0.):
    """The faces of a mesh whose plan centroid lies in box (x0, z0, x1, z1) (+pad)."""
    c = mesh.T.mean(1)
    k = (c[:, 0] >= box[0] - pad) & (c[:, 0] <= box[2] + pad) & (c[:, 2] >= box[1] - pad) & (c[:, 2] <= box[3] + pad)
    return Mesh(mesh.name, mesh.V, mesh.F[k], mesh.domain, mesh.role, mesh.feature[k], mesh.closed, mesh.material,
                None if mesh.uv is None else mesh.uv[k], dict(mesh.extra))


# ---------------------------------------------------------------------------------------------------- helpers

def unit_normals(T):
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    a = np.linalg.norm(n, axis=1)
    return n / np.maximum(a, 1e-300)[:, None], a / 2


def _pt(p):
    return [round(float(v), 3) for v in p]


def _worst(rows, key, n=FAILURES):
    rows = sorted(rows, key=key)
    return rows[:n]


def cell_pairs(lo, hi, cell, budget=2_000_000):
    """Yield (i, j) arrays, i < j, of boxes [lo, hi] (k,3) sharing a grid cell, each pair once (in the cell holding the
    low corner of the two boxes' intersection), in batches of about `budget` pairs (memory bounded by pairs)."""
    c0 = np.floor(lo / cell).astype('i8'); c1 = np.floor(hi / cell).astype('i8')
    span = c1 - c0 + 1
    cnt = span.prod(1)
    if not len(cnt) or cnt.sum() == 0:
        return
    if cnt.sum() > 200_000_000:
        raise MemoryError(f'{int(cnt.sum())} cell entries: use a larger cell')
    own = np.repeat(np.arange(len(lo)), cnt)
    loc = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    sx, sy = span[own, 0], span[own, 1]
    cx = c0[own, 0] + loc % sx; cy = c0[own, 1] + (loc // sx) % sy; cz = c0[own, 2] + loc // (sx * sy)
    del loc
    key = ((cx + (1 << 20)) << 42) | ((cy + (1 << 20)) << 21) | (cz + (1 << 20))
    o = np.lexsort((own, key)); key, own = key[o], own[o]
    cxyz = np.stack([cx[o], cy[o], cz[o]], 1)
    del cx, cy, cz
    # each entry pairs with the later entries of its run (same cell)
    start = np.r_[0, np.flatnonzero(key[1:] != key[:-1]) + 1]
    run_end = np.repeat(np.r_[start[1:], len(key)], np.diff(np.r_[start, len(key)]))
    partners = run_end - np.arange(len(key)) - 1
    cum = np.cumsum(partners)
    if not cum[-1]:
        return
    cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(budget, cum[-1], budget)), len(key)])
    for a, b in zip(cuts[:-1], cuts[1:]):
        p = partners[a:b]
        if not p.sum():
            continue
        e = np.repeat(np.arange(a, b), p)
        f = e + 1 + (np.arange(p.sum()) - np.repeat(np.cumsum(p) - p, p))
        i, j = own[e], own[f]
        # once: in the cell of the low corner of the boxes' intersection
        home = np.floor(np.maximum(lo[i], lo[j]) / cell).astype('i8')
        ok = (home == cxyz[e]).all(1) & (i != j)
        i, j = i[ok], j[ok]
        yield np.minimum(i, j), np.maximum(i, j)


def _clip(P, n, A, B):
    """Clip convex polygons P (m,K,2) with n corners to the left of lines A->B (m,2): Sutherland-Hodgman, vectorised."""
    m, K, _ = P.shape
    idx = np.arange(K)
    valid = idx[None] < n[:, None]
    nxt = np.where(idx[None] + 1 < n[:, None], idx[None] + 1, 0)
    Q = P[np.arange(m)[:, None], nxt]
    d = B - A
    side = lambda X: d[:, None, 0] * (X[..., 1] - A[:, None, 1]) - d[:, None, 1] * (X[..., 0] - A[:, None, 0])
    s0, s1 = side(P), side(Q)
    keep = valid & (s0 >= 0)
    cross = valid & ((s0 >= 0) != (s1 >= 0))
    t = s0 / np.where(s0 - s1 == 0, 1, s0 - s1)
    X = P + t[..., None] * (Q - P)
    cand = np.stack([P, X], 2).reshape(m, 2 * K, 2)
    mask = np.stack([keep, cross], 2).reshape(m, 2 * K)
    o = np.argsort(~mask, axis=1, kind='stable')
    out = cand[np.arange(m)[:, None], o][:, :K]
    nn = np.minimum(mask.sum(1), K)
    return out, nn


def _area2(P, n):
    K = P.shape[1]
    idx = np.arange(K)
    nxt = np.where(idx[None] + 1 < n[:, None], idx[None] + 1, 0)
    Q = P[np.arange(len(P))[:, None], nxt]
    s = (P[..., 0] * Q[..., 1] - Q[..., 0] * P[..., 1]) * (idx[None] < n[:, None])
    return s.sum(1) / 2


def _cross2(a, b):
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def tri_overlap(A2, B2, K=8):
    """Exact intersection polygons of 2-D triangles A2, B2 (m,3,2) (any winding): (polygons (m,K,2), counts, areas)."""
    m = len(A2)
    ccw = lambda T: np.where((_cross2(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]) < 0)[:, None, None], T[:, ::-1], T)
    A2, B2 = ccw(A2), ccw(B2)
    P = np.zeros((m, K, 2)); P[:, :3] = A2; n = np.full(m, 3)
    for k in range(3):
        P, n = _clip(P, n, B2[:, k], B2[:, (k + 1) % 3])
    return P, n, np.abs(_area2(P, n))


def _sat_separated(A2, B2, tol):
    """True where 2-D triangles are separated (or only touch within tol) along one of their six edge normals."""
    sep = np.zeros(len(A2), bool)
    for T in (A2, B2):
        for k in range(3):
            e = T[:, (k + 1) % 3] - T[:, k]
            ax = np.stack([-e[:, 1], e[:, 0]], 1)
            ax /= np.maximum(np.linalg.norm(ax, axis=1, keepdims=True), 1e-300)
            pa = (A2 * ax[:, None]).sum(2); pb = (B2 * ax[:, None]).sum(2)
            sep |= (pa.max(1) <= pb.min(1) + tol) | (pb.max(1) <= pa.min(1) + tol)
    return sep


def _project(T, ax):
    o1 = (ax + 1) % 3; o2 = (ax + 2) % 3
    r = np.arange(len(T))[:, None]
    return np.stack([T[r, np.arange(3)[None], o1[:, None]], T[r, np.arange(3)[None], o2[:, None]]], 2)


def _plane_height(N, d, ax, P2):
    """The dominant-axis coordinate of plane N.x = d at 2-D points P2 (m,K,2) (other two axes in cyclic order)."""
    r = np.arange(len(N))
    o1 = (ax + 1) % 3; o2 = (ax + 2) % 3
    return (d[:, None] - N[r, o1][:, None] * P2[..., 0] - N[r, o2][:, None] * P2[..., 1]) / N[r, ax][:, None]


def _lift(ax, P2, h):
    """3-D points from 2-D coordinates on the two other axes and a height on the dominant one."""
    out = np.zeros(P2.shape[:-1] + (3,))
    r = np.arange(len(ax))[:, None]
    K = P2.shape[1]
    out[r, np.arange(K)[None], ax[:, None]] = h
    out[r, np.arange(K)[None], ((ax + 1) % 3)[:, None]] = P2[..., 0]
    out[r, np.arange(K)[None], ((ax + 2) % 3)[:, None]] = P2[..., 1]
    return out


class _Stack:
    """The meshes of one check stacked into one face array, with each face's mesh index."""

    def __init__(self, meshes):
        self.meshes = list(meshes)
        Ts = [m.T for m in self.meshes]
        self.T = np.concatenate(Ts) if Ts else np.zeros((0, 3, 3))
        self.mesh = np.repeat(np.arange(len(self.meshes)), [len(t) for t in Ts]).astype('i8')
        self.local = np.concatenate([np.arange(len(t)) for t in Ts]) if Ts else np.zeros(0, 'i8')
        self.N, self.A = unit_normals(self.T)

    def name(self, i):
        return self.meshes[self.mesh[i]].name


# ---------------------------------------------------------------------------------------------------- V3 overlaps

def overlaps(meshes, eps=EPS, angle=ANGLE, min_area=MIN_AREA, cell=2., budget=2_000_000, limit=FAILURES):
    """V3, flicker: pairs of faces (within one mesh or between two) whose normals are parallel or antiparallel within
    `angle`, whose projected intersection has area > min_area, and whose planes are within `eps` of each other over that
    whole intersection (exact: the gap is linear over the convex intersection, so its maximum is at a corner)."""
    S = _Stack(meshes)
    T, N = S.T, S.N
    good = S.A > 1e-12
    cosmin = math.cos(math.radians(angle))
    lo = T.min(1) - eps; hi = T.max(1) + eps
    lo[~good] = np.inf; hi[~good] = -np.inf          # degenerate faces have no plane: never paired
    ok_lo = np.where(good[:, None], lo, 0.); ok_hi = np.where(good[:, None], hi, -1.)
    ax_all = np.abs(N).argmax(1)
    d_all = (N * T[:, 0]).sum(1)
    found = []; pairs_tested = 0
    for i, j in cell_pairs(ok_lo[good], ok_hi[good], cell, budget):
        gi = np.flatnonzero(good); i, j = gi[i], gi[j]
        pairs_tested += len(i)
        dot = (N[i] * N[j]).sum(1)
        k = np.abs(dot) >= cosmin
        i, j = i[k], j[k]
        # every corner of each within reach of the other's plane (a cheap bound before the exact test)
        reach = eps + np.linalg.norm(T[j] - T[j].mean(1, keepdims=True), axis=2).max(1) * 2 * math.sin(math.radians(angle))
        dj = np.abs(((T[j] - T[i][:, :1]) * N[i][:, None]).sum(2)).min(1)
        k = dj <= reach
        i, j = i[k], j[k]
        if not len(i):
            continue
        ax = ax_all[i]
        A2, B2 = _project(T[i], ax), _project(T[j], ax)
        k = ~_sat_separated(A2, B2, 1e-5)
        i, j, ax, A2, B2 = i[k], j[k], ax[k], A2[k], B2[k]
        if not len(i):
            continue
        P, n, area = tri_overlap(A2, B2)
        area = area / np.abs(N[i, ax])
        hi_ = _plane_height(N[i], d_all[i], ax, P); hj = _plane_height(N[j], d_all[j], ax, P)
        valid = np.arange(P.shape[1])[None] < n[:, None]
        gap = np.where(valid, np.abs(hi_ - hj), 0).max(1) * np.abs(N[i, ax])
        k = (area > min_area) & (gap <= eps)
        if k.any():
            cen = (np.where(valid[..., None], P, 0).sum(1) / np.maximum(n, 1)[:, None])[k]
            hc = _plane_height(N[i][k], d_all[i][k], ax[k], cen[:, None])[:, 0]
            where = _lift(ax[k], cen[:, None], hc[:, None])[:, 0]
            found.append(np.c_[i[k], j[k], area[k], gap[k], np.degrees(np.arccos(np.clip(np.abs((N[i[k]] * N[j[k]]).sum(1)), 0, 1))), where])
    rows = np.concatenate(found) if found else np.zeros((0, 8))
    within = int((S.mesh[rows[:, 0].astype('i8')] == S.mesh[rows[:, 1].astype('i8')]).sum()) if len(rows) else 0
    by_pair = {}
    for r in rows:
        a, b = S.name(int(r[0])), S.name(int(r[1]))
        key = f'{a} | {b}' if a <= b else f'{b} | {a}'
        e = by_pair.setdefault(key, [0, 0.]); e[0] += 1; e[1] += r[2]
    order = np.argsort(-rows[:, 2]) if len(rows) else []
    fails = [{'where': _pt(r[5:8]), 'meshes': [S.name(int(r[0])), S.name(int(r[1]))],
              'faces': [int(S.local[int(r[0])]), int(S.local[int(r[1])])], 'area_m2': round(float(r[2]), 6),
              'gap_mm': round(float(r[3]) * 1000, 3), 'angle_deg': round(float(r[4]), 4)} for r in rows[order][:limit]]
    return {'ok': len(rows) == 0, 'pairs': int(len(rows)), 'within_mesh_pairs': within,
            'between_mesh_pairs': int(len(rows) - within), 'area_m2': round(float(rows[:, 2].sum()), 4),
            'candidate_pairs': int(pairs_tested), 'eps_m': eps, 'angle_deg': angle,
            'mesh_pairs': {k: {'pairs': v[0], 'area_m2': round(v[1], 4)} for k, v in
                           sorted(by_pair.items(), key=lambda kv: -kv[1][1])[:limit]},
            'failures': fails}


# ---------------------------------------------------------------------------------------------------- V2/V4 topology

def _edges(F):
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    fid = np.tile(np.arange(len(F)), 3)
    u = np.sort(e, 1)
    _, inv, cnt = np.unique(u, axis=0, return_inverse=True, return_counts=True)
    inv = inv.ravel()
    return e, fid, inv, cnt


def edge_report(P, F, weld=WELD):
    """Welded edge census of one surface: (open edge ids, nonmanifold, mis-wound, degenerate faces, e, inv)."""
    q = np.round(P / weld).astype('i8')
    _, first, vid = np.unique(q, axis=0, return_index=True, return_inverse=True)
    vid = vid.ravel()
    W = vid[F]
    T = P[F]
    area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / 2
    collapsed = (W[:, 0] == W[:, 1]) | (W[:, 1] == W[:, 2]) | (W[:, 2] == W[:, 0])
    deg = collapsed | (area <= 1e-12)
    Wk = W[~collapsed]
    e, fid, inv, cnt = _edges(Wk)
    c = cnt[inv]
    opened = np.flatnonzero(c == 1)
    nonman = np.unique(inv[c > 2])
    # two faces on one edge must run it in opposite directions
    two = c == 2
    fwd = e[:, 0] < e[:, 1]
    s = np.zeros(len(cnt), 'i8'); np.add.at(s, inv[two], np.where(fwd[two], 1, -1))
    wound = np.flatnonzero((cnt == 2) & (s != 0))
    return dict(W=Wk, P=P[first], e=e, inv=inv, cnt=cnt, open=opened, nonmanifold=nonman, miswound=wound,
                degenerate=np.flatnonzero(deg), faces=np.flatnonzero(~collapsed))


def signed_volume(T):
    return float(np.einsum('ij,ij->i', T[:, 0], np.cross(T[:, 1], T[:, 2])).sum() / 6)


def topology(meshes, allow_open=None, weld=WELD, t_tol=T_TOL, limit=FAILURES):
    """V2/V4. The conforming surface (all non-closed meshes of one domain, welded together) has no open edge (except
    where `allow_open(a, b) -> bool mask` allows, e.g. the site's outer bottom), no non-manifold or mis-wound edge, no
    T-junction (a vertex inside an open edge) and no degenerate face. Every closed solid is watertight, consistently
    wound and has positive volume."""
    from .. import clean
    out = {'ok': True, 'surface': {}, 'solids': {}, 'failures': []}
    fails = []
    surf = [m for m in meshes if not m.closed]
    if surf:
        P = np.concatenate([m.V for m in surf]); off = np.cumsum([0] + [len(m.V) for m in surf])
        F = np.concatenate([m.F + o for m, o in zip(surf, off[:-1])])
        owner = np.repeat(np.arange(len(surf)), [len(m.F) for m in surf])
        r = edge_report(P, F, weld)
        Pw, e, inv = r['P'], r['e'], r['inv']
        oe = e[r['open']]
        allowed = np.zeros(len(oe), bool)
        if allow_open is not None and len(oe):
            allowed = np.asarray(allow_open(Pw[oe[:, 0]], Pw[oe[:, 1]]), bool)
        bad_open = oe[~allowed]
        # T-junctions: a welded vertex inside an open edge
        cand, which, t = clean._edge_hits(Pw[oe[:, 0]], Pw[oe[:, 1]], Pw, t_tol) if len(oe) else ([], [], [])
        cand = np.asarray(cand, 'i8'); which = np.asarray(which, 'i8')
        if len(cand):
            k = (which != oe[cand, 0]) & (which != oe[cand, 1])
            cand, which = cand[k], which[k]
        fowner = owner[r['faces']]
        efo = np.tile(fowner, 3)
        name = lambda i: surf[int(i)].name
        for k in range(min(len(cand), limit)):
            fails.append({'kind': 't_junction', 'where': _pt(Pw[which[k]]), 'mesh': name(efo[r['open'][cand[k]]])})
        ol = np.linalg.norm(Pw[bad_open[:, 0]] - Pw[bad_open[:, 1]], axis=1) if len(bad_open) else np.zeros(0)
        for k in np.argsort(-ol)[:limit]:
            fails.append({'kind': 'open_edge', 'where': _pt((Pw[bad_open[k, 0]] + Pw[bad_open[k, 1]]) / 2),
                          'length_m': round(float(ol[k]), 4), 'mesh': name(efo[r['open'][~allowed][k]])})
        for kind, ids in (('nonmanifold_edge', r['nonmanifold']), ('miswound_edge', r['miswound'])):
            for u in ids[:limit]:
                k = np.flatnonzero(inv == u)[0]
                fails.append({'kind': kind, 'where': _pt((Pw[e[k, 0]] + Pw[e[k, 1]]) / 2), 'mesh': name(efo[k])})
        for f in r['degenerate'][:limit]:
            fails.append({'kind': 'degenerate_face', 'where': _pt(P[F[f]].mean(0)), 'mesh': name(owner[f])})
        nt = len(np.unique(which)) if len(which) else 0
        out['surface'] = {'faces': int(len(F)), 'vertices_welded': int(len(Pw)), 'open_edges': int(len(bad_open)),
                          'open_edges_allowed': int(allowed.sum()), 'open_edge_length_m': round(float(ol.sum()), 3),
                          'nonmanifold_edges': int(len(r['nonmanifold'])), 'miswound_edges': int(len(r['miswound'])),
                          'degenerate_faces': int(len(r['degenerate'])), 't_junction_incidences': int(len(cand)),
                          't_junction_vertices': int(nt)}
        s = out['surface']
        if s['open_edges'] or s['nonmanifold_edges'] or s['miswound_edges'] or s['degenerate_faces'] or s['t_junction_incidences']:
            out['ok'] = False
    for m in meshes:
        if not m.closed:
            continue
        r = edge_report(m.V, m.F, weld)
        vol = signed_volume(m.T)
        rec = {'open_edges': int(len(r['open'])), 'nonmanifold_edges': int(len(r['nonmanifold'])),
               'miswound_edges': int(len(r['miswound'])), 'degenerate_faces': int(len(r['degenerate'])),
               'volume_m3': round(vol, 6)}
        rec['ok'] = not (rec['open_edges'] or rec['nonmanifold_edges'] or rec['miswound_edges'] or rec['degenerate_faces']) and vol > 0
        out['solids'][m.name] = rec
        if not rec['ok']:
            out['ok'] = False
            fails.append({'kind': 'solid_not_closed' if vol > 0 else 'solid_inside_out', 'where': _pt(m.V.mean(0)),
                          'mesh': m.name, **{k: v for k, v in rec.items() if k != 'ok'}})
    out['failures'] = fails[:limit * 4]
    return out


# ---------------------------------------------------------------------------------------------------- protrusions

@dataclass
class Lane:
    """A riding corridor: a plan path [(x, z)], half its width, and the features whose faces are its own (their riding
    faces are the surface; their other faces, coping or ledges on the line, are never protrusions)."""
    name: str
    path: np.ndarray
    half_width: float
    features: tuple = ()
    surface: tuple = ()        # mesh names whose up-facing faces are the riding surface (when features are not set)

    def __post_init__(self):
        self.path = np.asarray(self.path, 'f8').reshape(-1, 2)


def _seg_dist2(Q, path):
    """Squared plan distance from points Q (k,2) to a polyline (n,2), batched by point-segment pairs."""
    a, b = path[:-1], path[1:]
    out = np.full(len(Q), np.inf)
    step = max(1, 4_000_000 // max(len(a), 1))
    for s in range(0, len(Q), step):
        q = Q[s:s + step, None]
        d = b - a
        t = np.clip(((q - a) * d).sum(2) / np.maximum((d * d).sum(1), 1e-300), 0, 1)
        out[s:s + step] = ((a + t[..., None] * d - q) ** 2).sum(2).min(1)
    return out


def _lattice(T, h):
    """Barycentric sample points of triangles (k,3,3), spacing at most about h; with each point's face index."""
    L = np.linalg.norm(T - T[:, [1, 2, 0]], axis=2).max(1)
    n = np.clip(np.ceil(L / h).astype('i8'), 1, 200)
    pts, own = [], []
    for k in np.unique(n):
        f = np.flatnonzero(n == k)
        i, j = np.meshgrid(np.arange(k + 1), np.arange(k + 1), indexing='ij')
        m = i + j <= k
        w = np.stack([k - i[m] - j[m], i[m], j[m]], 1) / k
        pts.append(np.einsum('sk,fkd->fsd', w, T[f]).reshape(-1, 3)); own.append(np.repeat(f, len(w)))
    return (np.concatenate(pts), np.concatenate(own)) if pts else (np.zeros((0, 3)), np.zeros(0, 'i8'))


def heights_under(T, Q, cell=1., budget=2_000_000):
    """For plan points Q (k,3), every height of faces T (m,3,3) over each point: (point index, height, face)."""
    lo = T[:, :, [0, 2]].min(1); hi = T[:, :, [0, 2]].max(1)
    c0 = np.floor(lo / cell).astype('i8'); c1 = np.floor(hi / cell).astype('i8'); span = c1 - c0 + 1
    cnt = span.prod(1)
    own = np.repeat(np.arange(len(T)), cnt)
    loc = np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    key = ((c0[own, 0] + loc % span[own, 0] + (1 << 30)) << 32) | (c0[own, 1] + loc // span[own, 0] + (1 << 30))
    o = np.argsort(key); key, own = key[o], own[o]
    qc = np.floor(Q[:, [0, 2]] / cell).astype('i8')
    qk = ((qc[:, 0] + (1 << 30)) << 32) | (qc[:, 1] + (1 << 30))
    first = np.searchsorted(key, qk, 'left'); reps = np.searchsorted(key, qk, 'right') - first
    cum = np.cumsum(reps)
    res_p, res_h, res_f = [], [], []
    if not len(cum) or not cum[-1]:
        return np.zeros(0, 'i8'), np.zeros(0), np.zeros(0, 'i8')
    cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(budget, cum[-1], budget)), len(Q)])
    for a, b in zip(cuts[:-1], cuts[1:]):
        r = reps[a:b]
        if not r.sum():
            continue
        p = a + np.repeat(np.arange(b - a), r)
        f = own[np.repeat(first[a:b], r) + np.arange(r.sum()) - np.repeat(np.cumsum(r) - r, r)]
        t = T[f]; q = Q[p]
        x0, z0 = t[:, 0, 0], t[:, 0, 2]
        e1 = t[:, 1] - t[:, 0]; e2 = t[:, 2] - t[:, 0]
        det = e1[:, 0] * e2[:, 2] - e1[:, 2] * e2[:, 0]
        ok = np.abs(det) > 1e-12
        dx, dz = q[:, 0] - x0, q[:, 2] - z0
        u = (dx * e2[:, 2] - dz * e2[:, 0]) / np.where(ok, det, 1)
        v = (e1[:, 0] * dz - e1[:, 2] * dx) / np.where(ok, det, 1)
        ok &= (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        res_p.append(p[ok]); res_h.append((t[:, 0, 1] + u * e1[:, 1] + v * e2[:, 1])[ok]); res_f.append(f[ok])
    return np.concatenate(res_p), np.concatenate(res_h), np.concatenate(res_f)


def protrusions(meshes, lanes, tol=TOL_UP, headroom=HEADROOM, sample=SAMPLE, up=.2, limit=FAILURES):
    """The owner's "objects popping out of the ground": inside each lane's corridor, any face that is not the lane's own
    (another feature, dressing, an old slab) and stands between tol and headroom metres above the lane's riding surface.
    Faces are sampled on a barycentric lattice (spacing `sample`) plus their corners."""
    S = _Stack(meshes)
    feat = np.concatenate([m.feature for m in S.meshes]) if S.meshes else np.zeros(0, 'i8')
    names = np.array([m.name for m in S.meshes])
    out = {'ok': True, 'lanes': {}, 'failures': []}
    for lane in lanes:
        own = np.isin(feat, np.asarray(lane.features, 'i8')) if len(lane.features) else np.zeros(len(feat), bool)
        if len(lane.surface):
            own |= np.isin(names[S.mesh], list(lane.surface))
        ride = own & (S.N[:, 1] > up) & (S.A > 1e-12)
        if not ride.any():
            out['lanes'][lane.name] = {'ok': False, 'error': 'no riding surface'}; out['ok'] = False
            continue
        lo = lane.path.min(0) - lane.half_width; hi = lane.path.max(0) + lane.half_width
        Tp = S.T[:, :, [0, 2]]
        cand = ~own & (Tp[:, :, 0].max(1) >= lo[0]) & (Tp[:, :, 0].min(1) <= hi[0]) & \
            (Tp[:, :, 1].max(1) >= lo[1]) & (Tp[:, :, 1].min(1) <= hi[1]) & (S.A > 1e-12)
        ci = np.flatnonzero(cand)
        if len(ci):
            c = S.T[ci].mean(1)[:, [0, 2]]; rad = np.linalg.norm(S.T[ci][:, :, [0, 2]] - c[:, None], axis=2).max(1)
            ci = ci[np.sqrt(_seg_dist2(c, lane.path)) <= lane.half_width + rad]
        Q, qf = _lattice(S.T[ci], sample)
        qf = ci[qf] if len(ci) else qf
        inside = _seg_dist2(Q[:, [0, 2]], lane.path) <= lane.half_width ** 2
        Q, qf = Q[inside], qf[inside]
        ri = np.flatnonzero(ride)
        p, h, rf = heights_under(S.T[ri], Q)
        d = Q[p, 1] - h
        hit = (d > tol) & (d <= headroom)
        # each protruding face once: its highest point over the surface
        pf = qf[p[hit]]; dh = d[hit]; pw = Q[p[hit]]
        faces = {}
        for f, dd, w in zip(pf, dh, pw):
            if f not in faces or dd > faces[f][0]:
                faces[f] = (dd, w)
        covered = np.zeros(len(Q), bool); covered[p] = True
        rows = sorted(((dd, int(f), w) for f, (dd, w) in faces.items()), key=lambda r: -r[0])
        per_mesh = {}
        for dd, f, w in rows:
            e = per_mesh.setdefault(S.name(f), [0, 0.]); e[0] += 1; e[1] = max(e[1], dd)
        rec = {'ok': not rows, 'protruding_faces': len(rows), 'max_height_m': round(float(rows[0][0]), 4) if rows else 0.,
               'samples': int(len(Q)), 'samples_over_surface': int(covered.sum()),
               'meshes': {k: {'faces': v[0], 'max_height_m': round(v[1], 4)} for k, v in
                          sorted(per_mesh.items(), key=lambda kv: -kv[1][0])}}
        out['lanes'][lane.name] = rec
        if rows:
            out['ok'] = False
            out['failures'] += [{'lane': lane.name, 'where': _pt(w), 'height_m': round(float(dd), 4),
                                 'mesh': S.name(f), 'face': int(S.local[f]), 'feature': int(feat[f])} for dd, f, w in rows[:limit]]
    out['failures'] = sorted(out['failures'], key=lambda r: -r['height_m'])[:limit]
    return out


# ---------------------------------------------------------------------------------------------------- V5 thickness

def thin_walls(meshes, thin=THIN, min_area=THIN_AREA, angle=THIN_ANGLE, exempt=EXEMPT_THIN, cell=1.,
               budget=2_000_000, limit=FAILURES):
    """V5 on meshes: pairs of faces back to back (normals within `angle` of antiparallel, each behind the other) whose
    facing overlap (projected along the first's dominant axis, area > min_area) is thinner than `thin` anywhere. The
    distance between the planes is linear over the convex overlap, so its minimum at a corner is exact. Catches fins,
    slabs, double-sided sheets (thickness 0) and riding shells a few centimetres off a foundation. Roles in `exempt`
    (coping tubes, rails) are designed thinner; a closed solid sunk into another mesh is a contact, not a wall."""
    use = [m for m in meshes if m.role not in exempt]
    S = _Stack(use)
    T, N = S.T, S.N
    good = S.A > 1e-12
    gi = np.flatnonzero(good)
    cosmin = math.cos(math.radians(angle))
    d_all = (N * T[:, 0]).sum(1); ax_all = np.abs(N).argmax(1)
    closed = np.array([m.closed for m in S.meshes] + [False])
    found = []
    pad = thin / 2
    for i, j in cell_pairs(T[gi].min(1) - pad, T[gi].max(1) + pad, cell, budget):
        i, j = gi[i], gi[j]
        k = (N[i] * N[j]).sum(1) <= -cosmin
        # a closed solid sunk into another mesh (a ledge into its deck) is a contact, not a wall's two sides
        k &= ~((S.mesh[i] != S.mesh[j]) & (closed[S.mesh[i]] | closed[S.mesh[j]]))
        i, j = i[k], j[k]
        if not len(i):
            continue
        # j behind i and i behind j (back to back), at most thin apart: a bound on the corners first
        sj = ((T[j] - T[i][:, :1]) * N[i][:, None]).sum(2); si = ((T[i] - T[j][:, :1]) * N[j][:, None]).sum(2)
        k = (sj.min(1) < 1e-9) & (si.min(1) < 1e-9) & (sj.max(1) > -thin - 1e-9) & (si.max(1) > -thin - 1e-9)
        i, j = i[k], j[k]
        if not len(i):
            continue
        ax = ax_all[i]
        A2, B2 = _project(T[i], ax), _project(T[j], ax)
        k = ~_sat_separated(A2, B2, 1e-5)
        i, j, ax, A2, B2 = i[k], j[k], ax[k], A2[k], B2[k]
        if not len(i):
            continue
        P, n, area = tri_overlap(A2, B2)
        area = area / np.abs(N[i, ax])
        hi_ = _plane_height(N[i], d_all[i], ax, P); hj = _plane_height(N[j], d_all[j], ax, P)
        valid = np.arange(P.shape[1])[None] < n[:, None]
        # signed separation of j's plane from i's along i's normal, at the overlap's corners: behind is negative
        sep = (hj - hi_) * N[i, ax][:, None]
        depth = np.where(valid, -sep, np.inf)
        thick = depth.min(1)
        k = (area > min_area) & (thick > -1e-6) & (thick < thin)
        if k.any():
            at = depth[k].argmin(1)
            p2 = P[k][np.arange(k.sum()), at]
            where = _lift(ax[k], p2[:, None], hi_[k][np.arange(k.sum()), at][:, None])[:, 0]
            found.append(np.c_[i[k], j[k], area[k], np.maximum(thick[k], 0), where])
    rows = np.concatenate(found) if found else np.zeros((0, 7))
    per_mesh = {}
    for r in rows:
        e = per_mesh.setdefault(S.name(int(r[0])), [0, 0., np.inf]); e[0] += 1; e[1] += r[2]; e[2] = min(e[2], r[3])
    order = np.lexsort((-rows[:, 2], rows[:, 3])) if len(rows) else []
    fails = [{'where': _pt(r[4:7]), 'thickness_m': round(float(r[3]), 4), 'area_m2': round(float(r[2]), 5),
              'meshes': [S.name(int(r[0])), S.name(int(r[1]))]} for r in rows[order][:limit]]
    return {'ok': not len(rows), 'thin_pairs': int(len(rows)), 'thin_area_m2': round(float(rows[:, 2].sum()), 3),
            'min_thickness_m': round(float(rows[:, 3].min()), 4) if len(rows) else None, 'limit_m': thin,
            'meshes': {k: {'pairs': v[0], 'area_m2': round(v[1], 3), 'min_thickness_m': round(v[2], 4)}
                       for k, v in sorted(per_mesh.items(), key=lambda kv: -kv[1][1])[:limit]},
            'failures': fails}


def plan_width(loops, thin=THIN, corner_deg=45., facing_deg=60., limit=FAILURES):
    """V5, exact, on a raised region's plan outline: loops [(k,2) (x, z)], the outer one counter-clockwise seen from
    above (+y) with holes the other way (interior on the left walking +x->+z... any consistent: the outer loop's
    signed area decides). The width at a boundary point is the distance along its inward normal to the first boundary
    hit; along one edge, against one other edge, it is linear, so its minimum lies where the hit interval ends (the
    edge's ends or the other edge's ends projected): every such breakpoint is evaluated, so the minimum is exact.
    Hits on an adjacent edge are ignored at corners of at least corner_deg (they measure the corner, not a neck);
    sharper corners are failures in their own right. Only edges facing each other (normals within facing_deg of
    antiparallel) form a neck: a grazing hit near a corner, or along an S-curve, is not one."""
    loops = [np.asarray(l, 'f8').reshape(-1, 2) for l in loops]
    loops = [l[:-1] if len(l) > 2 and np.allclose(l[0], l[-1]) else l for l in loops]
    sa = lambda l: float((l[:, 0] * np.roll(l[:, 1], -1) - np.roll(l[:, 0], -1) * l[:, 1]).sum() / 2)
    outer = int(np.argmax([abs(sa(l)) for l in loops]))
    sgn = 1. if sa(loops[outer]) > 0 else -1.
    A, B, nxt, prv = [], [], [], []
    off = 0
    for k, l in enumerate(loops):
        # holes run opposite to the outer loop
        if k != outer and np.sign(sa(l)) == sgn:
            l = l[::-1]
        n = len(l)
        A.append(l); B.append(np.roll(l, -1, 0))
        nxt.append(off + (np.arange(n) + 1) % n); prv.append(off + (np.arange(n) - 1) % n); off += n
    A = np.concatenate(A); B = np.concatenate(B); nxt = np.concatenate(nxt); prv = np.concatenate(prv)
    D = B - A; Ln = np.linalg.norm(D, axis=1)
    # inward normal: interior on the left of a counter-clockwise outer loop (in (x, z) coordinates)
    Nn = sgn * np.stack([-D[:, 1], D[:, 0]], 1) / np.maximum(Ln, 1e-300)[:, None]
    # interior angle at each edge's start corner
    din, dout = D[prv], D
    turn = np.arctan2(din[:, 0] * dout[:, 1] - din[:, 1] * dout[:, 0], (din * dout).sum(1)) * sgn
    interior = 180. - np.degrees(turn)
    fails = [{'kind': 'sharp_corner', 'where': [round(float(A[k, 0]), 3), None, round(float(A[k, 1]), 3)],
              'angle_deg': round(float(interior[k]), 2)} for k in np.flatnonzero(interior < corner_deg)]
    m = len(A)
    i, j = np.meshgrid(np.arange(m), np.arange(m), indexing='ij'); i, j = i.ravel(), j.ravel()
    k = i != j
    lo = np.minimum(A, B); hi = np.maximum(A, B)
    k &= ((lo[j] <= hi[i] + thin) & (hi[j] >= lo[i] - thin)).all(1)
    adj_ok = interior >= corner_deg
    k &= ~((j == nxt[i]) & adj_ok[nxt[i]]) & ~((j == prv[i]) & adj_ok[i])
    # a neck's two sides face each other (within facing_deg of antiparallel); a grazing hit measures a corner
    k &= (Nn[i] * Nn[j]).sum(1) <= -math.cos(math.radians(facing_deg))
    i, j = i[k], j[k]
    best = []
    for s in range(0, len(i), 500_000):
        ii, jj = i[s:s + 500_000], j[s:s + 500_000]
        a, d, n = A[ii], D[ii], Nn[ii]; c, e = A[jj], D[jj]
        # p(s) = a + s d (s in [0,1]); ray p + t n hits c + u e: solve [n, -e] [t, u] = c - a - s d
        det = n[:, 0] * (-e[:, 1]) - n[:, 1] * (-e[:, 0])
        ok = np.abs(det) > 1e-12
        det = np.where(ok, det, 1)
        rhs0 = c - a
        # t(s) = t0 + s t1, u(s) = u0 + s u1
        solve = lambda r: ((r[:, 0] * (-e[:, 1]) - r[:, 1] * (-e[:, 0])) / det, (n[:, 0] * r[:, 1] - n[:, 1] * r[:, 0]) / det)
        t0, u0 = solve(rhs0); t1, u1 = solve(-d)
        # breakpoints in s: 0, 1, u = 0, u = 1
        with np.errstate(divide='ignore', invalid='ignore'):
            sc = np.stack([np.zeros_like(t0), np.ones_like(t0), -u0 / u1, (1 - u0) / u1], 1)
        sc = np.where(np.isfinite(sc), sc, -1)
        uu = u0[:, None] + sc * u1[:, None]; tt = t0[:, None] + sc * t1[:, None]
        v = ok[:, None] & (sc >= -1e-12) & (sc <= 1 + 1e-12) & (uu >= -1e-9) & (uu <= 1 + 1e-9) & (tt > 1e-9)
        tt = np.where(v, tt, np.inf)
        w = tt.min(1); at = tt.argmin(1)
        hit = w < thin
        if hit.any():
            p = a[hit] + sc[hit, at[hit]][:, None] * d[hit]
            best.append(np.c_[w[hit], p, ii[hit], jj[hit]])
    rows = np.concatenate(best) if best else np.zeros((0, 5))
    # the narrowest per edge
    rows = rows[np.argsort(rows[:, 0])]
    _, u = np.unique(rows[:, 3], return_index=True)
    rows = rows[np.sort(u)]
    fails += [{'kind': 'thin', 'where': [round(float(r[1]), 3), None, round(float(r[2]), 3)],
               'width_m': round(float(r[0]), 4)} for r in rows[:limit]]
    return {'ok': not fails, 'min_width_m': round(float(rows[0, 0]), 4) if len(rows) else None,
            'thin_edges': int(len(rows)), 'sharp_corners': int((interior < corner_deg).sum()), 'limit_m': thin,
            'failures': fails[:limit]}


# ---------------------------------------------------------------------------------------------------- V14 budgets

def budgets(meshes, limits=None, cube=CUBE, stride=CUBE_STRIDE, tiles=None):
    """V14: render and collision triangle totals, the largest render mesh, the render mesh count, coping triangles and
    the most collision triangles inside any `cube` (sliding by `stride`), with that cube's corner. tiles: the exported
    render meshes [(name, triangles, centre)] when they differ from `meshes` (split's 64 m material tiles)."""
    L = dict(BUDGETS, **(limits or {}))
    ren = [m for m in meshes if m.domain == 'render']; col = [m for m in meshes if m.domain == 'collision']
    nr = sum(len(m.F) for m in ren); nc = sum(len(m.F) for m in col)
    big = max(ren, key=lambda m: len(m.F)) if ren else None
    if tiles is not None:
        tiles = list(tiles)
        big_t = max(tiles, key=lambda t: t[1]) if tiles else None
    cop = sum(len(m.F) for m in ren if m.role == 'coping')
    worst, corner = 0, None
    if col:
        C = np.concatenate([m.T.mean(1) for m in col])
        q = np.floor(C / stride).astype('i8'); q0 = q.min(0); q -= q0
        k = int(round(cube / stride))
        G = np.zeros(tuple(q.max(0) + k + 1), 'i8'); np.add.at(G, (q[:, 0] + k, q[:, 1] + k, q[:, 2] + k), 1)
        I = G.cumsum(0).cumsum(1).cumsum(2)
        # the triangles of every k x k x k block of stride cells (inclusion-exclusion on the prefix sums)
        s = (I[k:, k:, k:] - I[:-k, k:, k:] - I[k:, :-k, k:] - I[k:, k:, :-k] + I[:-k, :-k, k:] + I[:-k, k:, :-k]
             + I[k:, :-k, :-k] - I[:-k, :-k, :-k])
        at = np.unravel_index(int(s.argmax()), s.shape)
        worst = int(s.max())
        # block ending at prefix index at+k covers cells at+1 .. at+k of G, i.e. q cells at+1-k .. at
        corner = [float((a + 1 - k + q0[d]) * stride) for d, a in enumerate(at)]
    n_meshes = len(ren) if tiles is None else len(tiles)
    if tiles is None:
        largest = (big.name, int(len(big.F)), _pt(big.V[np.unique(big.F)].mean(0))) if big else None
    else:
        largest = (big_t[0], int(big_t[1]), _pt(big_t[2])) if big_t else None
    rec = {'render_triangles': nr, 'collision_triangles': nc, 'render_meshes': n_meshes,
           'largest_render_mesh': {'name': largest[0], 'triangles': largest[1]} if largest else None,
           'coping_triangles': cop, 'collision_cube_max': worst, 'collision_cube_corner': corner, 'limits': L}
    fails = []
    for k, v, lim in (('render', nr, L['render']), ('collision', nc, L['collision']),
                      ('render_meshes', n_meshes, L['render_meshes']), ('coping', cop, L['coping']),
                      ('collision_cube', worst, L['collision_cube']),
                      ('render_mesh', largest[1] if largest else 0, L['render_mesh'])):
        if v > lim:
            f = {'kind': k, 'value': int(v), 'limit': lim, 'where': None}
            if k == 'collision_cube':
                f['where'] = [c + cube / 2 for c in corner]
            if k == 'render_mesh':
                f['mesh'] = largest[0]; f['where'] = largest[2]
            fails.append(f)
    rec['ok'] = not fails; rec['failures'] = fails
    return rec


# ---------------------------------------------------------------------------------------------------- site edge

def site_boundary(outline, tol=1e-3, below=None):
    """An allow_open rule for topology: an open edge is allowed only when both its ends and its midpoint lie within
    `tol` (plan metres) of the site's outer `outline` [(x, z)] (closed loop), and, with `below`, at or under that
    native y (the skirt's bottom). Any other open edge (a crack, a knife edge, a free wall top) still fails."""
    o = np.asarray(outline, 'f8'); o = o[:, [0, 2]] if o.shape[1] == 3 else o
    loop = np.r_[o, o[:1]]

    def ok(a, b):
        m = np.ones(len(a), bool)
        for p in (a, b, (a + b) / 2):
            m &= _seg_dist2(p[:, [0, 2]], loop) <= tol * tol
            if below is not None:
                m &= p[:, 1] <= below + tol
        return m
    return ok


# ---------------------------------------------------------------------------------------------------- V7 facets

DIHEDRAL = 2.        # degrees between neighbouring riding faces at most, off a designed crease (I6)


def facets(meshes, limit_deg=DIHEDRAL, weld=None, up=.2, limit=FAILURES):
    """V7, no visible faceting: between two riding faces sharing an edge, the angle between their normals is at most
    limit_deg. A designed crease (lip, coping, foot) has its vertices split (dsl.Mesh), so it is not a shared edge;
    with `weld` (metres) corners are merged first (for meshes without that convention: r4's soups)."""
    S = _Stack(meshes)
    ride = (S.N[:, 1] > up) & (S.A > 1e-12)
    if not ride.any():
        return {'ok': True, 'edges': 0, 'max_deg': 0., 'failures': []}
    V = np.concatenate([m.V for m in S.meshes]); off = np.cumsum([0] + [len(m.V) for m in S.meshes])
    F = np.concatenate([m.F + o for m, o in zip(S.meshes, off[:-1])])
    if weld:
        _, vid = np.unique(np.round(V / weld).astype('i8'), axis=0, return_inverse=True); F = vid.ravel()[F]
    fi = np.flatnonzero(ride)
    e, fid, inv, cnt = _edges(F[fi])
    two = np.flatnonzero(cnt == 2)
    o = np.argsort(inv, kind='stable'); si = inv[o]
    first = np.searchsorted(si, two)
    a, b = fi[fid[o[first]]], fi[fid[o[first + 1]]]
    ang = np.degrees(np.arccos(np.clip((S.N[a] * S.N[b]).sum(1), -1, 1)))
    bad = ang > limit_deg + .01                                  # the tessellation's own step is the limit
    eu = e[o[first]]
    mid = (V[eu[:, 0]] + V[eu[:, 1]]) / 2
    order = np.argsort(-ang)
    fails = [{'where': _pt(mid[k]), 'dihedral_deg': round(float(ang[k]), 3), 'mesh': S.name(a[k])}
             for k in order[:limit] if bad[k]]
    return {'ok': not bad.any(), 'edges': int(len(two)), 'faceted_edges': int(bad.sum()),
            'max_deg': round(float(ang.max()), 3) if len(ang) else 0., 'p99_deg': round(float(np.percentile(ang, 99)), 3) if len(ang) else 0.,
            'limit_deg': limit_deg, 'failures': fails}


# ---------------------------------------------------------------------------------------------------- V8 UVs

WORLD_UV = ('material_017', 'material_023', 'material_024', 'coping_steel')   # triplanar / round-the-tube: exempt
ANISO = 1.5          # the tangent map's singular values within this ratio (a streak is 77x in r4)
SCALE = 2.           # each singular value within this factor of its material's (area-weighted) median


def uv_stretch(meshes, aniso=ANISO, scale=SCALE, exempt=WORLD_UV, limit=FAILURES):
    """V8: each face's tangent map from UV to world (3x2: metres per texture tile along u and v); both singular values
    s1 >= s2 are measured. A streak (planar UVs on a wall: s2 tiny, s1 huge) fails the anisotropy s1/s2 <= aniso; a
    wrong scale fails |log(s / material median)| <= log(scale). Meshes need per-corner `uv` (m,3,2); materials in
    `exempt` (world triplanar) are skipped."""
    rows, per = [], {}
    for m in meshes:
        if m.uv is None or (m.material in exempt):
            continue
        T = m.T; U = np.asarray(m.uv, 'f8')
        dP = np.stack([T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]], 2)                    # (k,3,2)
        dU = np.stack([U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]], 2)                    # (k,2,2)
        det = dU[:, 0, 0] * dU[:, 1, 1] - dU[:, 0, 1] * dU[:, 1, 0]
        area = np.linalg.norm(np.cross(dP[:, :, 0], dP[:, :, 1]), axis=1) / 2
        ok = area > 1e-10
        inv = np.zeros_like(dU)
        safe = np.where(np.abs(det) > 1e-14, det, np.inf)
        inv[:, 0, 0] = dU[:, 1, 1] / safe; inv[:, 1, 1] = dU[:, 0, 0] / safe
        inv[:, 0, 1] = -dU[:, 0, 1] / safe; inv[:, 1, 0] = -dU[:, 1, 0] / safe
        J = np.einsum('kij,kjl->kil', dP, inv)
        sv = np.linalg.svd(J, compute_uv=False)
        s1 = np.where(np.abs(det) > 1e-14, sv[:, 0], np.inf); s2 = np.where(np.abs(det) > 1e-14, sv[:, 1], 0.)
        key = m.material or m.name
        per.setdefault(key, []).append((s1[ok], s2[ok], area[ok], T[ok].mean(1), m.name))
    for key, parts in per.items():
        s1 = np.concatenate([p[0] for p in parts]); s2 = np.concatenate([p[1] for p in parts])
        A = np.concatenate([p[2] for p in parts]); C = np.concatenate([p[3] for p in parts])
        names = np.concatenate([[p[4]] * len(p[0]) for p in parts])
        g = np.sqrt(np.where(np.isfinite(s1), s1, 0) * s2)
        fin = np.isfinite(s1) & (s2 > 0)
        o = np.argsort(g[fin]); cw = np.cumsum(A[fin][o])
        ref = float(g[fin][o][np.searchsorted(cw, cw[-1] / 2)]) if fin.any() else 1.
        an = np.where(fin, s1 / np.maximum(s2, 1e-300), np.inf)
        bad = (an > aniso) | ~fin | (np.abs(np.log(np.maximum(s1, 1e-300) / ref)) > np.log(scale)) | \
            (np.abs(np.log(np.maximum(s2, 1e-300) / ref)) > np.log(scale))
        for k in np.flatnonzero(bad):
            rows.append({'where': _pt(C[k]), 'material': key, 'mesh': str(names[k]),
                         'anisotropy': None if not np.isfinite(an[k]) else round(float(an[k]), 2),
                         'metres_per_tile': [None if not np.isfinite(s1[k]) else round(float(s1[k]), 3), round(float(s2[k]), 3)],
                         'material_metres': round(ref, 3), 'area_m2': round(float(A[k]), 4)})
        per[key] = {'faces': int(len(s1)), 'material_metres': round(ref, 3), 'bad_faces': int(bad.sum()),
                    'bad_area_m2': round(float(A[bad].sum()), 3),
                    'anisotropy_p99': round(float(np.percentile(np.where(np.isfinite(an), an, 1e9), 99)), 3) if len(an) else 1.}
    rows.sort(key=lambda r: -r['area_m2'])
    return {'ok': not rows, 'bad_faces': len(rows), 'materials': per, 'limits': {'anisotropy': aniso, 'scale': scale},
            'failures': rows[:limit]}


# ---------------------------------------------------------------------------------------------------- V6 outlines

TURN = 1.            # degrees: a turn smaller than this is straight (float noise)
FEATURE_EDGE = 30.   # degrees of dihedral from which an edge is a feature line (a wall top, a lip)


def feature_lines(meshes, weld=1e-4, crease=FEATURE_EDGE):
    """The outline polylines of the meshes: open edges, edges between different meshes (features, roles) and edges
    sharper than `crease`, chained between junctions. Returns [(k,3) points]."""
    S = _Stack(meshes)
    if not len(S.T):
        return []
    P = S.T.reshape(-1, 3)
    vid = np.unique(np.round(P / weld).astype('i8'), axis=0, return_inverse=True)[1].ravel()
    pos = np.zeros((vid.max() + 1, 3)); pos[vid] = P
    W = vid.reshape(-1, 3)
    good = S.A > 1e-12
    fi = np.flatnonzero(good)
    e, fid, inv, cnt = _edges(W[fi])
    o = np.argsort(inv, kind='stable'); si = inv[o]
    start = np.searchsorted(si, np.arange(len(cnt)))
    f0 = fi[fid[o[start]]]
    f1 = fi[fid[o[np.minimum(start + 1, len(o) - 1)]]]
    ang = np.degrees(np.arccos(np.clip((S.N[f0] * S.N[f1]).sum(1), -1, 1)))
    line = (cnt == 1) | (cnt > 2) | ((cnt == 2) & ((S.mesh[f0] != S.mesh[f1]) | (ang > crease)))
    E = np.sort(e[o[start]][line], 1)
    if not len(E):
        return []
    E = np.unique(E, axis=0)
    deg = np.bincount(E.ravel(), minlength=len(pos))
    adj = {}
    for a, b in E.tolist():
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    used = set(); chains = []

    def walk(a, b):
        ch = [a, b]; used.add((min(a, b), max(a, b)))
        while deg[b] == 2:
            n = [x for x in adj[b] if (min(b, x), max(b, x)) not in used]
            if not n:
                break
            a, b = b, n[0]; ch.append(b); used.add((min(a, b), max(a, b)))
        return ch
    for v in np.flatnonzero((deg != 2) & (deg > 0)):
        for w in adj[v]:
            if (min(v, w), max(v, w)) not in used:
                chains.append(walk(v, w))
    for a, b in E.tolist():                                       # closed loops
        if (a, b) not in used:
            chains.append(walk(a, b))
    return [pos[c] for c in chains]


def _turns(Q):
    """Signed turning angles (degrees) at the inner points of a 2-D polyline, dropping zero-length segments."""
    if len(Q) < 3:
        return np.zeros(0), np.zeros(0, 'i8')
    d = np.diff(Q, axis=0); L = np.linalg.norm(d, axis=1)
    keep = L > 1e-4
    idx = np.flatnonzero(keep)
    d = d[keep]
    if len(d) < 2:
        return np.zeros(0), np.zeros(0, 'i8')
    ang = np.degrees(np.arctan2(d[:-1, 0] * d[1:, 1] - d[:-1, 1] * d[1:, 0], (d[:-1] * d[1:]).sum(1)))
    return ang, idx[1:]                                            # turn at the start point of each later segment


def zigzag(polylines, turn=TURN, limit=FAILURES):
    """V6, no serration: on every outline, in plan (x, z) and in elevation (plan arc length, y), three consecutive
    turns larger than `turn` degrees alternating in sign (+-+ or -+-) are a zigzag: a grid staircase or a saw-tooth.
    An S-curve turns one way and then the other once, so it never alternates twice in a row."""
    rows = []; n_lines = 0; n_bad_lines = 0
    for P in polylines:
        P = np.asarray(P, 'f8')
        if len(P) < 4:
            continue
        n_lines += 1
        s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P[:, [0, 2]], axis=0), axis=1))]
        bad_here = 0
        for view, Q in (('plan', P[:, [0, 2]]), ('elevation', np.c_[s, P[:, 1]])):
            ang, at = _turns(Q)
            if len(ang) < 3:
                continue
            sg = np.sign(ang) * (np.abs(ang) > turn)
            alt = (sg[:-2] != 0) & (sg[1:-1] == -sg[:-2]) & (sg[2:] == sg[:-2])
            for k in np.flatnonzero(alt):
                bad_here += 1
                rows.append({'where': _pt(P[at[k + 1]]), 'view': view,
                             'turns_deg': [round(float(x), 2) for x in ang[k:k + 3]],
                             'step_m': round(float(np.linalg.norm(P[at[k + 1]] - P[at[k]])), 3)})
        n_bad_lines += bad_here > 0
    rows.sort(key=lambda r: -max(abs(t) for t in r['turns_deg']))
    return {'ok': not rows, 'outlines': n_lines, 'serrated_outlines': n_bad_lines, 'zigzag_points': len(rows),
            'turn_deg': turn, 'failures': rows[:limit]}


def outlines(meshes, **kw):
    """V6 on the meshes' own outlines (feature_lines), drawn faces only."""
    return zigzag(feature_lines(meshes), **kw)


# ---------------------------------------------------------------------------------------------------- V9 slivers

QUALITY = .01
MAX_EDGE = {'riding': 4., 'side': 4., 'ground': 8.}


def slivers(meshes, quality=QUALITY, max_edge=None, limit=FAILURES):
    """V9: triangle quality 4 sqrt(3) area / sum of squared edges >= quality (1 equilateral, 0 collapsed), and edges
    no longer than the role's maximum (riding 4 m, ground 8 m)."""
    me = dict(MAX_EDGE, **(max_edge or {}))
    rows = []; n = 0
    for m in meshes:
        T = m.T
        if not len(T):
            continue
        n += len(T)
        e2 = ((T - T[:, [1, 2, 0]]) ** 2).sum(2)
        A = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / 2
        q = 4 * np.sqrt(3) * A / np.maximum(e2.sum(1), 1e-300)
        L = np.sqrt(e2.max(1))
        lim = me.get(m.role, np.inf)
        for k in np.flatnonzero((q < quality) | (L > lim)):
            rows.append({'where': _pt(T[k].mean(0)), 'mesh': m.name, 'quality': round(float(q[k]), 5),
                         'longest_edge_m': round(float(L[k]), 3)})
    rows.sort(key=lambda r: r['quality'])
    return {'ok': not rows, 'faces': n, 'bad_faces': len(rows), 'quality_min': quality, 'max_edge_m': me,
            'failures': rows[:limit]}


# ---------------------------------------------------------------------------------------------------- V10 ownership

def ownership(meshes, feature_names, lines=(), scenery=(), limit=FAILURES):
    """V10, no useless blocks: every drawn face has a feature (index into feature_names, not -1 or 'unnamed'), and
    every feature is on a designed line (its name, or a sub-feature 'name.part') or declared scenery."""
    owned = [*lines, *scenery]
    on = lambda f: any(f == o or f.startswith(o + '.') for o in owned)
    rows = []; n_orphan = 0; counts = {}
    for m in meshes:
        f = np.asarray(m.feature, 'i8')
        bad = (f < 0) | (f >= len(feature_names))
        names = np.where(bad, '', np.asarray(list(feature_names) + [''], object)[np.clip(f, 0, len(feature_names))])
        bad |= names == 'unnamed'
        n_orphan += int(bad.sum())
        if bad.any():
            rows.append({'kind': 'faces_without_feature', 'mesh': m.name, 'faces': int(bad.sum()),
                         'where': _pt(m.T[bad].mean(1).mean(0))})
        for nm in set(names[~bad].tolist()):
            sel = names == nm
            counts.setdefault(nm, [0, []]); counts[nm][0] += int(sel.sum()); counts[nm][1].append(m.T[sel].mean(1).mean(0))
    stray = {k: v for k, v in counts.items() if not on(k)}
    for k, v in stray.items():
        rows.append({'kind': 'feature_on_no_line', 'feature': k, 'faces': v[0], 'where': _pt(np.mean(v[1], 0))})
    return {'ok': not rows, 'faces_without_feature': n_orphan, 'features': len(counts),
            'features_on_no_line': sorted(stray), 'failures': rows[:limit]}


# ---------------------------------------------------------------------------------------------------- V13 terrain

@dataclass
class Ground:
    """A terrain height field on a regular grid: H (nx+1, nz+1) at x0 + i*step, z0 + j*step; each cell split into two
    triangles by the diagonal (i, j)-(i+1, j+1), so the ground is piecewise linear (as a landscape is)."""
    x0: float
    z0: float
    step: float
    H: np.ndarray

    def at(self, x, z):
        u = (np.asarray(x, 'f8') - self.x0) / self.step; v = (np.asarray(z, 'f8') - self.z0) / self.step
        i = np.clip(np.floor(u).astype('i8'), 0, self.H.shape[0] - 2); j = np.clip(np.floor(v).astype('i8'), 0, self.H.shape[1] - 2)
        fu = u - i; fv = v - j
        h00 = self.H[i, j]; h10 = self.H[i + 1, j]; h01 = self.H[i, j + 1]; h11 = self.H[i + 1, j + 1]
        low = fu >= fv                                              # the triangle (i,j) (i+1,j) (i+1,j+1)
        return np.where(low, h00 + fu * (h10 - h00) + fv * (h11 - h10), h00 + fv * (h01 - h00) + fu * (h11 - h01))


def terrain(meshes, ground, clearance=.3, limit=FAILURES, budget=2_000_000):
    """V13, exact: every face stays `clearance` above a piecewise-linear ground. The gap between a face (linear) and
    the ground (linear on each grid triangle) is linear on each piece of their overlay, so its minimum lies at an
    overlay vertex: the face's corners, ground nodes inside the face, or a face edge crossing a grid line or diagonal.
    All three are evaluated, so a ground bump between corners, or under an edge, is found."""
    S = _Stack(meshes)
    T = S.T
    if not len(T):
        return {'ok': True, 'min_clearance_m': None, 'failures': []}
    g = ground; st = g.step
    pts, own = [T.reshape(-1, 3)], [np.repeat(np.arange(len(T)), 3)]
    # face edges crossing grid lines x = const, z = const and diagonals (x - x0) - (z - z0) = const
    a = T.reshape(-1, 3); b = T[:, [1, 2, 0]].reshape(-1, 3); ef = np.repeat(np.arange(len(T)), 3)
    for coord in ((lambda p: (p[:, 0] - g.x0) / st), (lambda p: (p[:, 2] - g.z0) / st),
                  (lambda p: ((p[:, 0] - g.x0) - (p[:, 2] - g.z0)) / st)):
        ca, cb = coord(a), coord(b)
        lo = np.ceil(np.minimum(ca, cb)); hi = np.floor(np.maximum(ca, cb))
        k = np.maximum(hi - lo + 1, 0).astype('i8'); k[ca == cb] = 0
        if not k.sum():
            continue
        e = np.repeat(np.arange(len(a)), k)
        c = np.repeat(lo, k) + (np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k))
        t = (c - ca[e]) / (cb[e] - ca[e])
        pts.append(a[e] + t[:, None] * (b[e] - a[e])); own.append(ef[e])
    # ground nodes inside each face's plan footprint, at the face's plane height
    i0 = np.floor((T[:, :, 0].min(1) - g.x0) / st).astype('i8'); i1 = np.ceil((T[:, :, 0].max(1) - g.x0) / st).astype('i8')
    j0 = np.floor((T[:, :, 2].min(1) - g.z0) / st).astype('i8'); j1 = np.ceil((T[:, :, 2].max(1) - g.z0) / st).astype('i8')
    ni = i1 - i0 + 1; nj = j1 - j0 + 1; cnt = ni * nj
    cum = np.cumsum(cnt)
    cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(budget, cum[-1], budget)), len(T)])
    for s0, s1 in zip(cuts[:-1], cuts[1:]):
        k = cnt[s0:s1]
        f = np.repeat(np.arange(s0, s1), k)
        loc = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
        x = g.x0 + (i0[f] + loc % ni[f]) * st; z = g.z0 + (j0[f] + loc // ni[f]) * st
        t = T[f]; e1 = t[:, 1] - t[:, 0]; e2 = t[:, 2] - t[:, 0]
        det = e1[:, 0] * e2[:, 2] - e1[:, 2] * e2[:, 0]
        ok = np.abs(det) > 1e-12
        dx, dz = x - t[:, 0, 0], z - t[:, 0, 2]
        u = (dx * e2[:, 2] - dz * e2[:, 0]) / np.where(ok, det, 1); v = (e1[:, 0] * dz - e1[:, 2] * dx) / np.where(ok, det, 1)
        ok &= (u >= 0) & (v >= 0) & (u + v <= 1)
        y = t[:, 0, 1] + u * e1[:, 1] + v * e2[:, 1]
        pts.append(np.c_[x, y, z][ok]); own.append(f[ok])
    Q = np.concatenate(pts); qf = np.concatenate(own)
    inside = (Q[:, 0] >= g.x0) & (Q[:, 0] <= g.x0 + st * (g.H.shape[0] - 1)) & (Q[:, 2] >= g.z0) & (Q[:, 2] <= g.z0 + st * (g.H.shape[1] - 1))
    Q, qf = Q[inside], qf[inside]
    c = Q[:, 1] - g.at(Q[:, 0], Q[:, 2])
    bad = c < clearance
    per = {}
    for k in np.flatnonzero(bad):
        f = qf[k]
        if f not in per or c[k] < per[f][0]:
            per[f] = (c[k], Q[k])
    rows = sorted(((v[0], f, v[1]) for f, v in per.items()), key=lambda r: r[0])
    return {'ok': not rows, 'min_clearance_m': round(float(c.min()), 4) if len(c) else None, 'clearance_m': clearance,
            'faces_too_low': len(rows), 'points_tested': int(len(Q)),
            'failures': [{'where': _pt(w), 'clearance_m': round(float(cc), 4), 'mesh': S.name(f)} for cc, f, w in rows[:limit]]}


# ---------------------------------------------------------------------------------------------------- buried faces

def buried(meshes, solid, exempt=('coping', 'rail'), offset=.002, limit=FAILURES):
    """No buried or internal faces: a drawn face whose front (its centroid moved `offset` along its normal) lies inside
    the closed `solid` meshes (vertical-ray parity) faces into material and is never seen: a foundation wall behind a
    riding face, a duplicate inside a block. Roles in `exempt` (coping tubes sunk into a deck: the documented
    render-only exception) are skipped."""
    S = _Stack([m for m in meshes if m.role not in exempt])
    Z = _Stack(solid)
    if not len(S.T) or not len(Z.T):
        return {'ok': True, 'buried_faces': 0, 'failures': []}
    good = S.A > 1e-10
    Q = S.T.mean(1) + offset * S.N + np.array([1.234567e-5, 0, 2.345678e-5])   # off every edge and vertex
    p, h, _ = heights_under(Z.T, Q)
    above = h > Q[p, 1]
    n = np.bincount(p[above], minlength=len(Q))
    inside = (n % 2 == 1) & good
    per = {}
    for k in np.flatnonzero(inside):
        e = per.setdefault(S.name(k), [0, 0.]); e[0] += 1; e[1] += float(S.A[k])
    order = np.argsort(-S.A * inside)
    rows = [{'where': _pt(S.T[k].mean(0)), 'mesh': S.name(k), 'area_m2': round(float(S.A[k]), 4)}
            for k in order[:limit] if inside[k]]
    return {'ok': not inside.any(), 'buried_faces': int(inside.sum()), 'buried_area_m2': round(float(S.A[inside].sum()), 3),
            'meshes': {k: {'faces': v[0], 'area_m2': round(v[1], 3)} for k, v in sorted(per.items(), key=lambda kv: -kv[1][1])[:limit]},
            'failures': rows}


# ---------------------------------------------------------------------------------------------------- airs

G = 9.81
LIP_MAX = 30.        # degrees: a launch lip steeper than this verts the rider (note 2); 15-25 is the design range
LIP_TOL = 1.         # degrees between the built and the designed lip angle
MISMATCH = 20.       # degrees between the flight and the landing surface at touchdown at most
SPEEDS = np.arange(4., 30.01, .5)


def air(meshes, lip, direction, lip_degrees=None, speeds=SPEEDS, band=None, g=G, lip_max=LIP_MAX, lip_tol=LIP_TOL,
        mismatch=MISMATCH, up=.2, horizon=8.):
    """Lip-angle and landing-match sanity for one air (ballistic, no drag; the rider sim V15 has the final say).
    The lip angle is measured on the built surface 5-45 cm before `lip` along the plan `direction`, extrapolated to it. Each speed is
    flown from the lip; the first surface it comes down on is its touchdown. A speed lands when the touchdown face is a
    'landing' face (when the meshes tag any; else one sloping down along the flight) and the flight meets it within
    `mismatch` degrees. Fails: a lip steeper than lip_max (it verts), a lip off its design, no landable speed, or a
    design speed `band` (lo, hi) not wholly landable."""
    S = _Stack(meshes)
    tags = np.concatenate([np.asarray(m.extra.get('tag', [''] * len(m.F)), object) for m in S.meshes]) if S.meshes else np.zeros(0, object)
    tagged = (tags == 'landing').any()
    ride = np.flatnonzero((S.N[:, 1] > up) & (S.A > 1e-12))
    T = S.T[ride]
    lip = np.asarray(lip, 'f8'); d = np.asarray(direction, 'f8')[[0, -1]] if len(direction) == 3 else np.asarray(direction, 'f8')
    d = d / np.linalg.norm(d)
    back = (.05, .25, .45)
    probe = np.array([[lip[0] - d[0] * s, lip[1], lip[2] - d[1] * s] for s in back])
    p, h, _ = heights_under(T, probe)
    hh = []
    for k in range(len(back)):
        c = h[p == k]
        hh.append(c[np.argmin(np.abs(c - lip[1]))] if len(c) else np.nan)
    # slopes 15 and 35 cm before the lip, extrapolated to it (a transition still curves up to its lip)
    a1 = np.degrees(np.arctan2(hh[0] - hh[1], .2)); a2 = np.degrees(np.arctan2(hh[1] - hh[2], .2))
    built = float(a1 + (a1 - a2) * .75) if np.isfinite(a2) else float(a1)
    theta = np.radians(built if np.isfinite(built) else (lip_degrees or 0.))
    rec = {'lip': _pt(lip), 'lip_built_deg': round(built, 2) if np.isfinite(built) else None,
           'lip_design_deg': lip_degrees, 'speeds': {}}
    fails = []
    if not np.isfinite(built):
        fails.append({'kind': 'no_lip_surface', 'where': _pt(lip)})
    elif built > lip_max + .05:                                 # a 30 degree design lip measures 30.000x
        fails.append({'kind': 'lip_verts', 'where': _pt(lip), 'lip_deg': round(built, 2), 'limit_deg': lip_max})
    if lip_degrees is not None and np.isfinite(built) and abs(built - lip_degrees) > lip_tol:
        fails.append({'kind': 'lip_off_design', 'where': _pt(lip), 'built_deg': round(built, 2), 'design_deg': lip_degrees})
    landed = []
    for v0 in speeds:
        vx, vy = v0 * math.cos(theta), v0 * math.sin(theta)
        tmax = (vy + math.sqrt(vy * vy + 2 * g * horizon * 4)) / g + 1.
        t = np.arange(0, tmax, .05 / max(vx, .5))[1:]
        X = np.c_[lip[0] + d[0] * vx * t, lip[1] + .02 + vy * t - g * t * t / 2, lip[2] + d[1] * vx * t]
        p, h, f = heights_under(T, X)
        prev = np.r_[lip[1] + .02, X[:-1, 1]]
        hit = (h >= X[p, 1]) & (h <= prev[p] + .05) & (vx * t[p] > .3)
        if not hit.any():
            rec['speeds'][float(v0)] = {'lands': False, 'why': 'no touchdown'}; continue
        k = np.argmin(np.where(hit, p, 1 << 40)); i, face = p[k], ride[f[k]]
        vel = np.array([d[0] * vx, vy - g * t[i], d[1] * vx])
        n = S.N[face]
        ang = float(np.degrees(np.arcsin(min(1., abs(vel @ n) / np.linalg.norm(vel)))))
        down = n[0] * d[0] + n[2] * d[1] > 0
        ok_face = (tags[face] == 'landing') if tagged else down
        ok = bool(ok_face and ang <= mismatch)
        rec['speeds'][float(v0)] = {'lands': ok, 'touchdown': _pt(X[i]), 'mismatch_deg': round(ang, 1),
                                    'on': str(tags[face]) or S.name(face), 'distance_m': round(float(vx * t[i]), 2),
                                    'apex_y': round(float(lip[1] + vy * vy / (2 * g)), 2)}
        if ok:
            landed.append(float(v0))
    rec['landable_speeds'] = [min(landed), max(landed)] if landed else None
    if not landed:
        worst = min((s for s in rec['speeds'].values() if 'touchdown' in s), key=lambda s: s['mismatch_deg'], default=None)
        fails.append({'kind': 'no_landing', 'where': worst['touchdown'] if worst else _pt(lip),
                      'best_mismatch_deg': worst['mismatch_deg'] if worst else None})
    if band is not None and landed:
        need = [float(v) for v in speeds if band[0] <= v <= band[1]]
        miss = [v for v in need if v not in landed]
        if miss:
            fails.append({'kind': 'band_not_landable', 'where': _pt(lip), 'band': list(band), 'missed_speeds': miss})
    if landed:
        mid = landed[len(landed) // 2]
        rec['land'] = rec['speeds'][mid]['touchdown']; rec['apex'] = rec['speeds'][mid]['apex_y']
    rec['ok'] = not fails; rec['failures'] = fails
    return rec


def airs(meshes, specs, **kw):
    """`air` for each spec: dicts with 'lip', and 'direction' or 'landing_start' (plan direction from the lip), with
    optional 'lip_degrees', 'band' (lo, hi) m/s and 'feature' (the name in the report)."""
    out = {'ok': True, 'airs': {}, 'failures': []}
    for k, sp in enumerate(specs):
        lip = np.asarray(sp['lip'], 'f8')
        dirn = sp.get('direction')
        if dirn is None:
            ls = np.asarray(sp['landing_start'], 'f8'); dirn = (ls - lip)[[0, 2]]
        r = air(meshes, lip, dirn, sp.get('lip_degrees'), band=sp.get('band'), **kw)
        name = sp.get('feature') or f'air_{k}'
        out['airs'][name] = r
        if not r['ok']:
            out['ok'] = False
            out['failures'] += [dict(f, air=name) for f in r['failures']]
    return out


# ---------------------------------------------------------------------------------------------------- entry point

def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def _plan_widths(regions):
    w = {k: plan_width(v) for k, v in dict(regions).items()}
    return {'ok': all(r['ok'] for r in w.values()), 'regions': w,
            'failures': [dict(f, region=k) for k, r in w.items() for f in r['failures']][:FAILURES]}


def validate(meshes, lanes=(), regions=(), allow_open=None, out=None, checks=None, limits=None, log=print):
    """Run every check on the park's meshes. lanes: Lane corridors (protrusions). regions: raised plan regions
    {name: [loops]} for the exact width test. Returns (report, ok); writes the report as JSON to `out` if given."""
    import time
    meshes = [as_mesh(m) for m in meshes]
    ren = [m for m in meshes if m.domain == 'render']; col = [m for m in meshes if m.domain == 'collision']
    run = {
        'overlaps': lambda: overlaps(ren),
        'overlaps_collision': lambda: overlaps(col),
        'topology': lambda: topology([m for m in ren if m.role not in ('coping', 'rail', 'dressing')], allow_open),
        'topology_collision': lambda: topology(col, allow_open),
        'thin_walls': lambda: thin_walls(ren),
        'plan_width': lambda: _plan_widths(regions),
        'protrusions': lambda: protrusions(meshes, lanes),
        'budgets': lambda: budgets(meshes, limits),
    }
    report = {'schema': 1, 'frame': 'native metres, x, y up, z', 'checks': {}}
    for name, fn in run.items():
        if checks is not None and name not in checks:
            continue
        if name.endswith('_collision') and not col or name in ('overlaps', 'topology', 'thin_walls') and not ren:
            continue
        t = time.time()
        r = fn(); r['seconds'] = round(time.time() - t, 2)
        report['checks'][name] = r
        if log:
            log(f'validate {name}: {"ok" if r["ok"] else "FAIL"} ({r["seconds"]} s)')
    ok = all(r['ok'] for r in report['checks'].values())
    report['ok'] = ok
    report['failed'] = [k for k, r in report['checks'].items() if not r['ok']]
    report = _jsonable(report)
    if out is not None:
        p = Path(out); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(report, indent=1)); tmp.replace(p)
    return report, ok


# ---------------------------------------------------------------------------------------------------- dsl.Park

LANE_HALF_WIDTH = 1.5   # metres either side of a designed line's centre path: the rider's corridor


def park_meshes(park):
    """A dsl.Park's one mesh as validator meshes, one per (feature, role, material), named 'feature/role/material'
    (per-corner UVs and per-face tags kept). Render: the roles in dsl.RENDER_ROLE; collision: dsl.COLLISION_ROLE; base
    faces (buried bottoms, never drawn) only close the surface. Returns (render, collision, surface): surface is all
    but the coping and rail tubes (each tube is a closed solid of its own)."""
    from . import dsl
    m = park.mesh
    feat = np.asarray(m.feature, 'i8'); role = np.asarray(m.role, 'i8'); mat = np.asarray(m.material, 'i8')
    key = np.stack([feat, role, mat], 1)
    render, collision, surface = [], [], []
    for f_id, r_id, m_id in np.unique(key, axis=0).tolist():
        mask = (feat == f_id) & (role == r_id) & (mat == m_id)
        r_name = dsl.ROLES[r_id]; material = dsl.MATERIALS[m_id]
        name = f'{m.features[f_id]}/{r_name}/{material}'
        F = m.F[mask]
        kw = dict(role=r_name, feature=np.full(len(F), f_id), material=material, uv=m.UV[F],
                  extra={'tag': np.asarray(dsl.TAGS, object)[m.tag[mask]]})
        if r_name in dsl.RENDER_ROLE:
            render.append(Mesh(name, m.V, F, 'render', **kw))
        if r_name in dsl.COLLISION_ROLE:
            collision.append(Mesh(name, m.V, F, 'collision', **kw))
        surface.append(Mesh(name, m.V, F, 'surface', closed=r_name in (dsl.COPING, dsl.RAIL), **kw))
    return render, collision, surface


def park_lanes(park, half_width=LANE_HALF_WIDTH):
    """Lane corridors from the park's designed RideLines: their plan centre paths, their own features by index."""
    names = list(park.mesh.features)
    own = lambda line: tuple(i for i, n in enumerate(names) if any(n == f or n.startswith(f + '.') for f in line.features))
    return [Lane(line.name, np.asarray(line.path)[:, [0, 2]], half_width, features=own(line)) for line in park.lines]


def _tube_components(mesh, weld=WELD):
    """Each connected component of a tube mesh (coping, rail) as its own closed Mesh."""
    if not len(mesh.F):
        return []
    q = np.round(mesh.V / weld).astype('i8')
    _, vid = np.unique(q, axis=0, return_inverse=True); vid = vid.ravel()
    W = vid[mesh.F]
    parent = np.arange(vid.max() + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in np.r_[W[:, [0, 1]], W[:, [1, 2]]]:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    comp = np.array([find(x) for x in W[:, 0]])
    out = []
    for k, c in enumerate(np.unique(comp)):
        sel = comp == c
        out.append(Mesh(f'{mesh.name}#{k}', mesh.V, mesh.F[sel], mesh.domain, mesh.role, mesh.feature[sel], True))
    return out


def validate_park(park, out=None, lanes=None, regions=(), allow_open=None, limits=None, ground=None, skip=(),
                  log=print):
    """The build's entry point (generate.run_validators): every check on a dsl.Park. Returns (report, ok) and writes
    the report as JSON to `out`. Lanes default to the park's RideLines; the surface (riding, side, ground and base
    faces) must be closed except where allow_open allows; coping and rail tubes must each be closed solids."""
    import time
    render, collision, surface = park_meshes(park)
    lanes = park_lanes(park) if lanes is None else lanes
    tubes = [c for m in surface if m.closed for c in _tube_components(m)]
    try:
        from . import split
        tiles = [(name, len(t.F), t.triangles().reshape(-1, 3).mean(0)) for name, _, t in split.render_meshes(park.mesh)]
    except Exception as e:                                       # the split's own failure is reported by its step
        tiles = None
        if log:
            log(f'validate budgets: render tiles unavailable ({e})')
    surf = [m for m in surface if not m.closed]
    drawn = [m for m in render]
    line_features = [f for line in park.lines for f in line.features]
    scenery = [c.get('feature') for c in park.checks if isinstance(c, dict) and c.get('kind') == 'scenery']
    # the site: a feature with ground faces (the landform every line stands on) is on no line by design
    from . import dsl
    gr = np.asarray(park.mesh.role) == dsl.ROLE[dsl.GROUND]
    scenery += [park.mesh.features[i] for i in np.unique(np.asarray(park.mesh.feature)[gr])]
    air_specs = [c for c in park.checks if isinstance(c, dict) and c.get('kind') == 'air' and 'lip' in c]
    riding = [m for m in collision if m.role == 'riding']
    run = {
        'overlaps': lambda: overlaps(drawn),
        'overlaps_collision': lambda: overlaps(collision),
        'topology': lambda: topology(surf + tubes, allow_open),
        'buried': lambda: buried(drawn, surf),
        'thin_walls': lambda: thin_walls(drawn),
        'plan_width': lambda: _plan_widths(regions),
        'outlines': lambda: outlines(drawn),
        'facets': lambda: facets(riding),
        'uv_stretch': lambda: uv_stretch(drawn),
        'slivers': lambda: slivers(drawn),
        'ownership': lambda: ownership(drawn, park.mesh.features, line_features, scenery),
        'protrusions': lambda: protrusions(drawn, lanes),
        'airs': lambda: airs(collision, air_specs),
        'terrain': lambda: terrain(drawn, ground) if ground is not None else {'ok': True, 'skipped': 'no ground given',
                                                                              'failures': []},
        'budgets': lambda: budgets(render + collision, limits, tiles=tiles),
    }
    report = {'schema': 1, 'frame': 'native metres, x, y up, z', 'features': list(park.mesh.features),
              'lanes': [{'name': l.name, 'half_width_m': l.half_width, 'path': np.round(l.path, 3).tolist()} for l in lanes],
              'checks': {}}
    for name, fn in run.items():
        if name in skip:
            continue
        t = time.time()
        r = fn(); r['seconds'] = round(time.time() - t, 2)
        report['checks'][name] = r
        if log:
            log(f'validate {name}: {"ok" if r["ok"] else "FAIL"} ({r["seconds"]} s)')
    report['airs'] = [{'feature': k, 'lip': v['lip'], 'land': v['land'], 'apex': v['apex']}
                      for k, v in report['checks'].get('airs', {}).get('airs', {}).items() if 'land' in v]
    ok = all(r['ok'] for r in report['checks'].values())
    report['ok'] = ok
    report['failed'] = [k for k, r in report['checks'].items() if not r['ok']]
    report = _jsonable(report)
    if out is not None:
        p = Path(out); p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(report, indent=1)); tmp.replace(p)
    return report, ok
