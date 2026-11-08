"""E1: a profile swept along a plan path (plan/pipeline.md 4, 5.1-5.3).

transverse:   S(t, s) = C(t) + o(s) N(t) + (h(t) + py(s)) Y,  o(s) = offset + side * px(s)
              rows are path stations t, columns profile stations s (quarter pipes, bowl walls, banks along an edge).
longitudinal: S(s, w) = C(t(s)) + w N(t(s)) + (h(t(s)) + py(s)) Y,  t(s) = start + px(s)
              rows are profile stations s along the path, columns lateral offsets w (roll-ins, kickers, landings).

Stations come from the profile's arc length (never a plan grid) and from the path's curvature, each at the smallest
spacing allowed by the Tess (chord, angle, max edge). Creases in the profile (('corner', deg)) duplicate the station:
two vertices per position, each with its own side's analytic normal. Quads use the shorter 3D diagonal, chosen once
per strip. UVs: transverse u = length along the path at `offset`, v = profile arc length; longitudinal u = w,
v = s; both divided by uv_metres.
"""
import math

import numpy as np

from . import dsl
from .curves import adaptive, merge_params


def _ys(t, h):
    return h(t), h.slope(t)


def grid_mesh(P, Nrm, UV, row_skip, col_skip, face_attrs, feature, seams_prefix=''):
    """A Mesh from a (na, nb) grid of positions P (na, nb, 3), normals and UVs. row_skip[i] / col_skip[j]: the gap
    between row i and i + 1 (column j and j + 1) has zero width (a crease duplicate) and gets no faces.
    face_attrs(i0, i1, j0, j1) -> (material id, role name, tag name) for the quad block, called per strip (column j)."""
    na, nb = P.shape[:2]
    idx = np.arange(na * nb).reshape(na, nb)
    rows = np.flatnonzero(~np.asarray(row_skip, bool)[:na - 1])
    faces, mats, roles, tags = [], [], [], []
    for j in range(nb - 1):
        if col_skip[j]:
            continue
        a, b, c, d = idx[rows, j], idx[rows + 1, j], idx[rows + 1, j + 1], idx[rows, j + 1]
        V = P.reshape(-1, 3)
        diag_ac = np.linalg.norm(V[a] - V[c], axis=1).sum(); diag_bd = np.linalg.norm(V[b] - V[d], axis=1).sum()
        if diag_ac <= diag_bd:
            f = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
        else:
            f = np.concatenate([np.stack([a, b, d], 1), np.stack([b, c, d], 1)])
        material, role, tag = face_attrs(j)
        faces.append(f); mats.append(np.full(len(f), dsl.MATERIAL[material]))
        roles.append(np.full(len(f), dsl.ROLE[role])); tags.append(np.full(len(f), dsl.TAG[tag]))
    F = np.concatenate(faces) if faces else np.zeros((0, 3), 'i8')
    V = P.reshape(-1, 3); N = Nrm.reshape(-1, 3)
    # orientation: the faces' fronts follow the analytic normals (one decision for the whole grid)
    if len(F):
        t = V[F]; fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        if (fn * N[F].mean(1)).sum() < 0:
            F = F[:, ::-1].copy()
    # drop zero-area faces (a profile running exactly along the path's degenerate end): never exported
    if len(F):
        t = V[F]; area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1)
        keep = area > 1e-10
    else:
        keep = np.zeros(0, bool)
    seams = {seams_prefix + 'start': idx[0], seams_prefix + 'end': idx[-1],
             seams_prefix + 'left': idx[:, 0], seams_prefix + 'right': idx[:, -1]}
    mesh = dsl.Mesh(V, F[keep], N, UV.reshape(-1, 2), None,
                    np.concatenate(mats)[keep] if mats else None, np.concatenate(roles)[keep] if roles else None,
                    0, (feature,), seams, np.concatenate(tags)[keep] if tags else None)
    return mesh


def _stations(profile, s):
    """Profile stations with creases doubled: (s, right flags, skip-after flags)."""
    s = np.asarray(s, 'f8')
    out, right = [], []
    creases = profile.creases
    for x in s:
        if 0 < x < profile.length and any(abs(x - c) < 1e-9 for c in creases):
            out += [x, x]; right += [False, True]
        else:
            out.append(x); right.append(True)
    out = np.asarray(out); right = np.asarray(right)
    skip = np.zeros(len(out), bool); skip[:-1] = np.abs(np.diff(out)) < 1e-12
    return out, right, skip


def _eval_profile(profile, s, right):
    x, y, ang = np.zeros(len(s)), np.zeros(len(s)), np.zeros(len(s))
    for flag in (True, False):
        m = right == flag
        if m.any():
            xx, yy, aa, _, _ = profile._eval(s[m], flag)
            x[m], y[m], ang[m] = xx, yy, aa
    return x, y, ang


def _attrs(profile, s, right):
    def face_attrs(j):
        mid = (s[j] + s[j + 1]) / 2
        a = profile.attrs[int(profile.part_of(mid)[0])]
        return a['material'], a['role'], a.get('tag', '')
    return face_attrs


def sweep(path, profile, *, mode='transverse', side=1, offset=0., height=0., start=0., across=None,
          t=None, s=None, tess=dsl.RIDING_TESS, feature='unnamed', uv_metres=dsl.UV_METRES):
    """Sweep `profile` along `path` (a curves.Curve). Returns a dsl.Mesh with analytic normals, arc-length UVs, per-face
    material/role/tag from the profile's part attributes, and seams 'start', 'end' (first and last row), 'left', 'right'
    (first and last column), prefixed by '<feature>.'.

    transverse: `side` +1 puts the profile on the path's left (+N), -1 on its right; `offset` shifts it laterally;
    `height` (float, dsl.Height or callable of t) is added to the profile's y. `t`: path stations to use exactly (from a
    network.Network), else adaptive. `s`: extra profile stations.
    longitudinal: the profile's x runs along the path from `start`; `across` the lateral offsets (sorted array), or a
    width as a float (centred, subdivided to max_edge and the plan curvature); `t` extra path stations (mapped to s)."""
    h = dsl.as_height(height)
    prefix = feature + '.'
    if mode == 'transverse':
        ss = profile.samples(tess, () if s is None else s)
        st, right, skip_col = _stations(profile, ss)
        px, py, pa = _eval_profile(profile, st, right)
        o = offset + side * px
        if t is None:
            t = path.samples(tess, offsets=np.unique(o), height=None if isinstance(height, (int, float)) else h)
        t = np.asarray(t, 'f8')
        C = path.point(t); T = path.tangent(t); Nn = path.normal(t); k = path.curvature(t)
        hy, hs = _ys(t, h)
        T3 = np.stack([T[:, 0], np.zeros(len(t)), T[:, 1]], 1); N3 = np.stack([Nn[:, 0], np.zeros(len(t)), Nn[:, 1]], 1)
        Y = np.array([0., 1., 0.])
        P = (np.stack([C[:, 0], np.zeros(len(t)), C[:, 1]], 1)[:, None, :] + o[None, :, None] * N3[:, None, :]
             + (hy[:, None] + py[None, :])[..., None] * Y)
        dT = T3[:, None, :] * (1 - k[:, None] * o[None, :])[..., None] + hs[:, None, None] * Y
        dS = side * np.cos(pa)[None, :, None] * N3[:, None, :] + np.sin(pa)[None, :, None] * Y
        Nrm = side * np.cross(dS, dT)
        Nrm /= np.maximum(np.linalg.norm(Nrm, axis=-1, keepdims=True), 1e-12)
        # u along the path at `offset`
        ds = np.diff(t) * np.abs(1 - (k[1:] + k[:-1]) / 2 * offset)
        u = np.concatenate([[0.], np.cumsum(ds)])
        UV = np.stack(np.broadcast_arrays(u[:, None], st[None, :]), -1) / uv_metres
        mesh = grid_mesh(P, Nrm, UV, np.zeros(len(t), bool), skip_col, _attrs(profile, st, right), feature, prefix)
        return mesh
    if mode != 'longitudinal':
        raise ValueError(mode)
    # One adaptive station set accounts for pitch, plan turn and their twist.
    # Merging independent grids for all three oversamples their Cartesian product
    # with the transverse shoulders and creates very close, skinny rows.
    dense = np.linspace(0, profile.length, 2048); dx = profile.point(dense)[:, 0] - profile.start[0]
    if np.any(np.diff(dx) < -1e-9):
        raise ValueError(f'{feature}: a longitudinal profile must not run backwards')
    w = np.asarray(across, 'f8') if across is not None and np.ndim(across) else None
    width = float(across) if w is None and across is not None else 0.
    wmax = np.abs(w).max() if w is not None else width / 2
    # a slope on a plan curve: its normal also turns with the heading (rate k sin a cos a per metre of profile) and
    # across the width (the same rate per metre of offset), so both stations share the angle budget with the profile
    # (a combined turn of at most tess.angle between neighbouring faces, diagonals included)
    tdense = start + dx
    kd = np.abs(path.curvature(tdense)); ad = profile.angle(dense)
    twist = kd * np.abs(np.sin(ad) * np.cos(ad))
    budget = np.radians(tess.angle) / math.sqrt(2)
    def density(q):
        x, a = profile.point(q)[:, 0], profile.angle(q)
        k = np.abs(path.curvature(start + x - profile.start[0]))
        kp = np.abs(profile.curvature(q))
        cos = np.abs(np.cos(a))
        radius = np.maximum(1 / np.maximum(k, 1e-12) - wmax, 1e-6)
        plan_rate = k * cos / tess.step_angle(radius)
        edge_rate = cos * (1 + k * wmax) / (tess.max_edge / math.sqrt(2))
        twist_rate = np.sqrt(kp ** 2 + (k * np.abs(np.sin(a) * np.cos(a))) ** 2) / budget
        return np.maximum.reduce([tess.density(kp), plan_rate, edge_rate, twist_rate])

    # Invert only semantic path cuts and caller-supplied stations, to full
    # precision: linear inversion on a fixed 2048-point table moves a cut off
    # its exact profile and can leave a visible seam at a joined module.
    t_need = np.r_[path.breaks(), [] if t is None else t]
    t_need = np.unique(t_need[(t_need > start + 1e-9) & (t_need < start + dx[-1] - 1e-9)])
    lo, hi = np.zeros(len(t_need)), np.full(len(t_need), profile.length)
    for _ in range(48):
        mid = (lo + hi) / 2
        before = start + profile.point(mid)[:, 0] - profile.start[0] < t_need
        lo, hi = np.where(before, mid, lo), np.where(before, hi, mid)
    keep = np.r_[profile.knots, list(profile.tags.values()), [] if s is None else s, (lo + hi) / 2]
    keep = np.unique(keep[(keep >= 0.) & (keep <= profile.length)])
    cuts = np.unique(np.r_[0., profile.length, keep])
    # Splitting at the path cuts also keeps an abrupt curvature change from
    # being missed by the density integration, even if a profile part is long.
    spans = [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b - a > 1e-12]
    ss = merge_params(adaptive(spans, density), keep)
    st, right, skip_row = _stations(profile, ss)
    px, py, pa = _eval_profile(profile, st, right)
    tt = start + px - profile.start[0]
    if w is None:
        kmax = np.abs(path.curvature(tt)).max() if len(tt) else 0.
        cols = max(width * tess.density(0., 1 + kmax * wmax), width * twist.max() / budget)
        n = max(1, int(np.ceil(cols)))
        w = np.linspace(-width / 2, width / 2, n + 1)
    C = path.point(tt); T = path.tangent(tt); Nn = path.normal(tt); k = path.curvature(tt)
    hy, hs = _ys(tt, h)
    T3 = np.stack([T[:, 0], np.zeros(len(tt)), T[:, 1]], 1); N3 = np.stack([Nn[:, 0], np.zeros(len(tt)), Nn[:, 1]], 1)
    Y = np.array([0., 1., 0.])
    P = (np.stack([C[:, 0], np.zeros(len(tt)), C[:, 1]], 1)[:, None, :] + w[None, :, None] * N3[:, None, :]
         + (hy + py)[:, None, None] * Y)
    cx, sy = np.cos(pa), np.sin(pa)
    dS = (cx[:, None, None] * T3[:, None, :] * (1 - k[:, None] * w[None, :])[..., None]
          + (sy + hs * cx)[:, None, None] * Y)
    dW = np.broadcast_to(N3[:, None, :], dS.shape)
    Nrm = np.cross(dW, dS)
    Nrm /= np.maximum(np.linalg.norm(Nrm, axis=-1, keepdims=True), 1e-12)
    UV = np.stack(np.broadcast_arrays(w[None, :], st[:, None]), -1) / uv_metres
    # attributes vary by row here: build per row strip by transposing the grid (rows <-> columns)
    Pt, Nt, UVt = P.transpose(1, 0, 2), Nrm.transpose(1, 0, 2), UV.transpose(1, 0, 2)
    mesh = grid_mesh(Pt, Nt, UVt, np.zeros(len(w), bool), skip_row, _attrs(profile, st, right), feature, prefix)
    # grid_mesh named seams for the transposed grid: rows were offsets; rename to the sweep's meaning
    sm = mesh.seams
    mesh.seams = {prefix + 'start': sm[prefix + 'left'], prefix + 'end': sm[prefix + 'right'],
                  prefix + 'left': sm[prefix + 'start'], prefix + 'right': sm[prefix + 'end']}
    return mesh
