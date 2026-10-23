"""A continuous northern landscape around the current valley, in island metres."""
import json
from functools import lru_cache

import numpy as np
from belmonte import layout as L, source
from belmonte.ground_names import VALLEY_CARVED_TILES
from hidamari import layout as H
from hippodrome.build import Mesh
import shorelines

OUTER = (L.BOUNDS[0] - L.APRON, L.SOUTH_JOIN, L.BOUNDS[2] + L.APRON, L.BOUNDS[3] + L.APRON)
# The country runs out to sea NORTH_SHIFT metres further north than it first did, keeping its distance from the valley.
SEA = 6500. + L.NORTH_SHIFT
COUNTRY = (-3200., L.SOUTH_JOIN, 3200., SEA)


def grid_height(xs, ys, heights, x, y):
    """Intersect the same a-c diagonal used by the exported grid quads."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    i = np.clip(np.searchsorted(xs, x, side='right') - 1, 0, len(xs) - 2)
    j = np.clip(np.searchsorted(ys, y, side='right') - 1, 0, len(ys) - 2)
    u, v = (x - xs[i]) / (xs[i + 1] - xs[i]), (y - ys[j]) / (ys[j + 1] - ys[j])
    a, b, c, d = heights[j, i], heights[j, i + 1], heights[j + 1, i + 1], heights[j + 1, i]
    return np.where(u >= v, a + u * (b - a) + v * (c - b), a + u * (c - d) + v * (d - a))


def old_height(x, y):
    grid = H.backdrop_grid()
    axis = np.linspace(-3200., 3200., len(grid))
    return grid_height(axis, axis, grid, x, y)


@lru_cache(maxsize=1)
def country_grid():
    xs = np.unique(np.r_[np.linspace(-3200., 3200., 96), OUTER[0], OUTER[2], H.mountains.BOUNDS[0], H.mountains.BOUNDS[2]])
    ys = np.unique(np.r_[L.SOUTH_JOIN, np.linspace(-3200., 3200., 96)[-3:],
                         np.arange(3200., SEA, 50.), OUTER[3], SEA])
    x, y = np.meshgrid(xs, ys)
    edge = old_height(x, np.minimum(y, 3200.))
    # The authored valley keeps its relief. Its surroundings use the island's
    # own deterministic rolling hills and taper to sea beyond the visible zone.
    inland = H.mountains.smooth((x + 3000.) / 750.) * H.mountains.smooth((3000. - x) / 750.)
    land = (225. + 26. * H.mountains.noise(x, y, 550., 27)) * inland
    land *= H.mountains.smooth((SEA - y) / 1000.)
    blend = H.mountains.smooth((y - 3200.) / 500.)
    z = edge * (1. - blend) + land * blend
    return xs, ys, z


def country_profile_height(x, y):
    """Existing triangular country and coast profile before local deformation."""
    out = np.where(np.asarray(y) <= 3200., old_height(x, y), grid_height(*country_grid(), x, y))
    return shorelines.profile_height(x, y, out)


def country_height(x, y, *, carved=False):
    out = shorelines.landforms(x, y, country_profile_height(x, y))
    if carved:
        from train import earthworks
        out = earthworks.carve(x, y, out)
    return out


def collar_contains(x, y):
    return (x >= OUTER[0]) & (x <= OUTER[2]) & (y >= OUTER[1]) & (y <= OUTER[3])


def old_backdrop(grid, x, y):
    """Hide only coarse ground replaced by the fine collar, preserving the rest."""
    result = grid.copy()
    on = collar_contains(x, y) & (y > L.SOUTH_JOIN)
    result[on] = np.minimum(result[on], -50.)
    return result


def collar():
    """Four stitched strips: every imported rim vertex and outer grid knot retained."""
    mesh = Mesh()
    points = source.terrain(natural=True).faces.reshape(-1, 3) + L.ORIGIN
    xs, ys, _ = country_grid()
    inner, outer = L.BOUNDS, OUTER
    # Orient each strip counter-clockwise round the hole; its outward rows then
    # give upward triangles. All corner rows are identical on adjacent strips.
    edges = [(0, 1, inner[1], outer[1], inner[0], inner[2], outer[0], outer[2]),
             (1, 0, inner[2], outer[2], inner[1], inner[3], outer[1], outer[3]),
             (0, 1, inner[3], outer[3], inner[2], inner[0], outer[2], outer[0]),
             (1, 0, inner[0], outer[0], inner[3], inner[1], outer[3], outer[1])]
    total = 0
    for along, across, edge, rim, lo, hi, olo, ohi in edges:
        boundary = points[np.isclose(points[:, across], edge, atol=.002), along]
        knots = xs if along == 0 else ys
        if across == 1 and edge == inner[1]:
            knots = np.r_[knots, np.arange(H.mountains.BOUNDS[0], H.mountains.BOUNDS[2] + H.mountains.STEP, H.mountains.STEP)]
        u = np.unique(np.clip(np.r_[(boundary - lo) / (hi - lo),
                                   (knots - olo) / (ohi - olo), np.linspace(0., 1., int(abs(hi - lo) / 10.) + 2)], 0., 1.))
        ix, iy = (lo + u * (hi - lo), np.full_like(u, edge)) if along == 0 else (np.full_like(u, edge), lo + u * (hi - lo))
        ox, oy = (olo + u * (ohi - olo), np.full_like(u, rim)) if along == 0 else (np.full_like(u, rim), olo + u * (ohi - olo))
        iz = source.terrain(natural=True).height(ix - L.ORIGIN[0], iy - L.ORIGIN[1]) + L.ORIGIN[2]
        oz = H.north_height(ox, oy, carved=False) if across == 1 and edge == inner[1] else country_profile_height(ox, oy)
        assert np.isfinite(iz).all() and np.isfinite(oz).all(), 'Open Belmonte collar edge'
        previous = None
        for t in np.linspace(0., 1., 40):
            smooth = t * t * (3. - 2. * t)
            x, y = ix*(1.-t)+ox*t, iy*(1.-t)+oy*t
            z = shorelines.landforms(x, y, iz*(1.-smooth)+oz*smooth)
            row = np.stack([x, y, z], 1) - L.ORIGIN
            if previous is not None:
                for a, b, c, d in zip(previous[:-1], previous[1:], row[1:], row[:-1]):
                    mesh.quad(a, d, c, b)
            previous = row
        total += len(u)
    return mesh, {'boundary_samples': total, 'bounds_m': OUTER, 'source_gap_m': 0., 'island_gap_m': 0.}


def country():
    mesh = Mesh()
    xs, ys, z = country_grid()
    # North of the far hills the foothills (hidamari/mountains.py) reach on to SOUTH_JOIN; as the far hills do, the
    # country sinks under them so that their eased edges cover it.
    x, y = np.meshgrid(xs, ys)
    under = (x > H.mountains.BOUNDS[0]) & (x < H.mountains.BOUNDS[2]) & (y > H.mountains.BOUNDS[1]) & (y < L.SOUTH_JOIN)
    if under.any():
        z = z.copy()
        z[under] = np.minimum(z[under], H.north_height(x[under], y[under], carved=False) - 25.)
    vertices, faces = shorelines.grid_mesh(xs, ys, z, hidden=lambda x,y:
        y < 3200. or (OUTER[0] < x < OUTER[2] and OUTER[1] < y < OUTER[3]))
    vertices = np.asarray(vertices)-L.ORIGIN
    for face in faces:
        points = vertices[list(face)]
        (mesh.triangle if len(face) == 3 else mesh.quad)(*points)
    return mesh


# --- Belmonte valley railway & station tile carving (generated into build/yorimichi/belmonte/glb/) -------------------

VALLEY_SUBDIV = 3           # 3x3 barycentric split (~1.5 m edges) on non-planar carved triangles
WALL_FINE = .85             # metres along the overbridge walls and deck ends
FORECOURT_FINE = .75        # metres along the station forecourt edges
ACCESS_FINE = 1.6           # metres along the station access road edges
SALON_PATH = dict(points=((623.1, 4733.), (647.8, 4771.)), half=2.0, soft=1.0)
PATH_STEP = 1.5


def _read_glb(path):
    data = path.read_bytes()
    doc, binary = source.glb_parts(data)
    prim = doc['meshes'][0]['primitives'][0]

    def acc(index):
        a = doc['accessors'][index]
        view = doc['bufferViews'][a['bufferView']]
        dtype = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[a['componentType']]
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]
        out = np.frombuffer(binary, dtype, a['count'] * width, view.get('byteOffset', 0) + a.get('byteOffset', 0))
        out = out.reshape(-1, width).astype(float)
        if a.get('normalized'):
            out /= 255. if a['componentType'] == 5121 else 65535.
        return out
    attrs = prim['attributes']
    return doc, dict(position=acc(attrs['POSITION']), normal=acc(attrs['NORMAL']), uv=acc(attrs['TEXCOORD_0']),
                     colour=acc(attrs['COLOR_0']), faces=acc(prim['indices']).astype(np.int64).reshape(-1, 3))


def _encode_colour(colour):
    w = np.clip(colour, 0, None)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-6)
    rgb = np.rint(w[:, :3] * 255).astype(np.int64)
    over = np.maximum(rgb.sum(1) - 255, 0)
    for i in np.flatnonzero(over):
        rgb[i, np.argmax(rgb[i])] -= over[i]
    rgb *= 257
    return np.column_stack([rgb, 65535 - rgb.sum(1)]).astype('<u2')


def encoded_tile(doc, position, normal, uv, colour, faces):
    blobs, views, accessors = [], [], []

    def add(array, component, kind, target, normalized=False, bounds=False):
        raw = np.ascontiguousarray(array).tobytes()
        offset = sum(len(b) for b in blobs)
        blobs.append(raw + b'\0' * (-len(raw) % 4))
        views.append(dict(buffer=0, byteOffset=offset, byteLength=len(raw), target=target))
        acc = dict(bufferView=len(views) - 1, componentType=component, count=int(len(array)), type=kind)
        if normalized:
            acc['normalized'] = True
        if bounds:
            acc['min'] = [float(v) for v in array.min(0)]
            acc['max'] = [float(v) for v in array.max(0)]
        accessors.append(acc)
        return len(accessors) - 1
    prim = doc['meshes'][0]['primitives'][0]
    prim['attributes'] = dict(
        POSITION=add(position.astype('<f4'), 5126, 'VEC3', 34962, bounds=True),
        NORMAL=add(normal.astype('<f4'), 5126, 'VEC3', 34962),
        TEXCOORD_0=add(uv.astype('<f4'), 5126, 'VEC2', 34962),
        COLOR_0=add(_encode_colour(colour), 5123, 'VEC4', 34962, normalized=True))
    big = len(position) > 65535
    prim['indices'] = add(faces.ravel().astype('<u4' if big else '<u2'), 5125 if big else 5123, 'SCALAR', 34963)
    doc['bufferViews'], doc['accessors'] = views, accessors
    binary = b''.join(blobs)
    doc['buffers'] = [dict(byteLength=len(binary))]
    return source.glb_pack(doc, binary)


def _write_glb(path, doc, position, normal, uv, colour, faces):
    path.write_bytes(encoded_tile(doc,position,normal,uv,colour,faces))


def _repaint(colour, x, y, z, z0, ln):
    from train import earthworks as E, station_site as SS
    rock, cess, _ = E.weights(x, y, z, z0, ln)
    moved = E._smooth(np.abs(z - z0) / .8)
    site = ln.station()
    a, u = site.local(x, y)
    paved = np.zeros(len(x))
    for rect, _ in site.zones():
        paved = np.maximum(paved, 1 - E._smooth(SS.rect_excess(a, u, rect) / 1.5))
    pts, _ = site.access()
    paved = np.maximum(paved, 1 - E._smooth(SS.polyline_excess(x, y, pts, SS.ACCESS_HALF - 1.)[0] / 1.5))
    target = np.zeros((len(x), 4))
    target[:, 1] = 1.
    target = target * (1 - rock[:, None]) + np.array([0., 0., 0., 1.]) * rock[:, None]
    dirt = np.maximum(cess, paved)
    target = target * (1 - dirt[:, None]) + np.array([0., 0., 1., 0.]) * dirt[:, None]
    weight = np.maximum(moved, paved)[:, None]
    out = colour * (1 - weight) + target * weight
    return out / np.maximum(out.sum(1, keepdims=True), 1e-6)


def _salon_path(v, f, attrs):
    from train import earthworks as E, station_site as SS
    pts_path = np.asarray(SALON_PATH['points'], float)
    path_excess = lambda x, y: SS.polyline_excess(x, y, pts_path, SALON_PATH['half'])[0]  # noqa: E731
    tri = v[f]
    probes = np.concatenate([tri, tri.mean(1, keepdims=True)], 1).reshape(-1, 3)
    sel = (path_excess(probes[:, 0], probes[:, 1]) < SALON_PATH['soft'] + 1.).reshape(-1, 4).any(1)
    span = np.linalg.norm(tri - tri.mean(1, keepdims=True), axis=2).max(1)
    sel |= path_excess(tri.mean(1)[:, 0], tri.mean(1)[:, 1]) < span
    if not sel.any():
        return v, f, attrs, False
    n = int(np.ceil(np.linalg.norm(tri[sel] - np.roll(tri[sel], -1, 1), axis=2).max() / PATH_STEP))
    ij = [(i, j) for i in range(n + 1) for j in range(n + 1 - i)]
    index = {q: k for k, q in enumerate(ij)}
    bary = np.array([(1 - (i + j) / n, i / n, j / n) for i, j in ij])
    tmpl = np.array([t for i in range(n) for j in range(n - i) for t in
                     [(index[(i, j)], index[(i + 1, j)], index[(i, j + 1)])]
                     + ([(index[(i + 1, j)], index[(i + 1, j + 1)], index[(i, j + 1)])] if i + j < n - 1 else [])])
    fs = f[sel]
    pts = np.einsum('pk,tkc->tpc', bary, v[fs])
    key = np.round(pts.reshape(-1, 3) * 1000.).astype(np.int64)
    corner = {0: index[(0, 0)], 1: index[(n, 0)], 2: index[(0, n)]}
    ids = np.full(pts.shape[:2], -1, np.int64)
    for c, q in corner.items():
        ids[:, q] = fs[:, c]
    fresh = ids < 0
    _, first, inverse = np.unique(key.reshape(pts.shape[:2] + (3,))[fresh], axis=0, return_index=True,
                                  return_inverse=True)
    ids[fresh] = len(v) + inverse.ravel()
    out = {k: np.concatenate([a, np.einsum('pk,tkc->tpc', bary, a[fs])[fresh][first]]) for k, a in attrs.items()}
    v = np.concatenate([v, pts[fresh][first]])
    f = np.concatenate([f[~sel], ids[:, tmpl].reshape(-1, 3)])
    w = 1 - E._smooth(path_excess(v[:, 0], v[:, 1]) / SALON_PATH['soft'])
    out['colour'] = out['colour'] * (1 - w[:, None]) + np.array([0., 0., 1., 0.]) * w[:, None]
    return v, f, out, True


def _bisect_near(v, f, attrs, near, limit):
    v = np.asarray(v, float)
    f = np.asarray(f, np.int64)
    attrs = {k: np.asarray(x, float) for k, x in attrs.items()}
    for _ in range(40):
        tri = v[f]
        length = np.linalg.norm(tri - np.roll(tri, -1, 1), axis=2)
        longest = length.argmax(1)
        want = (length.max(1) > limit) & near(tri.mean(1))
        if not want.any():
            break
        key = lambda i, j: (min(f[i, j], f[i, (j + 1) % 3]), max(f[i, j], f[i, (j + 1) % 3]))  # noqa: E731
        split = {key(i, longest[i]) for i in np.flatnonzero(want)}
        edges = {}
        for i in range(len(f)):
            for j in range(3):
                edges.setdefault(key(i, j), []).append(i)
        todo = [t for e in split for t in edges[e]]
        while todo:
            i = todo.pop()
            e = key(i, longest[i])
            if e not in split:
                split.add(e)
                todo.extend(edges[e])
        mid = {}
        new_v, new_attr = [], {k: [] for k in attrs}
        for e in split:
            mid[e] = len(v) + len(new_v)
            new_v.append((v[e[0]] + v[e[1]]) / 2)
            for k in attrs:
                new_attr[k].append((attrs[k][e[0]] + attrs[k][e[1]]) / 2)
        faces = []
        for i in range(len(f)):
            j = longest[i]
            c = [f[i, (j + q) % 3] for q in range(3)]
            e = [key(i, (j + q) % 3) for q in range(3)]
            if e[0] not in split:
                faces.append(c)
                continue
            m = mid[e[0]]
            for half, side in (((c[0], m, c[2]), e[2]), ((m, c[1], c[2]), e[1])):
                if side in split:
                    s2 = mid[side]
                    if side == e[2]:
                        faces += [(c[0], m, s2), (m, c[2], s2)]
                    else:
                        faces += [(m, c[1], s2), (m, s2, c[2])]
                else:
                    faces.append(half)
        v = np.concatenate([v, np.array(new_v)])
        attrs = {k: np.concatenate([attrs[k], np.array(new_attr[k])]) for k in attrs}
        f = np.array(faces, np.int64)
    return v, f, attrs


def _border_vertices(num_v, f):
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), 1)
    uniq, count = np.unique(edges, axis=0, return_counts=True)
    border = np.zeros(num_v, bool)
    border[uniq[count == 1].ravel()] = True
    return border


def carve_valley_tile(path, ln=None):
    """Carve one Belmonte valley tile GLB in memory without mutating assets/belmonte/. Returns
    (doc, local_position, local_normal, uv, colour, faces, report)."""
    from train import corridor as C, earthworks as E, station_site as SS
    ln = ln or E.line()
    doc, t = _read_glb(path)
    origin = np.asarray(L.ORIGIN, float)
    v = t['position'] @ source.FRAME.T + origin
    f0 = t['faces']
    attrs = dict(normals=t['normal'] @ source.FRAME.T, uv=t['uv'], colour=t['colour'], natural=v[:, 2:3])
    if ln is None or ln.station() is None:
        return doc, t['position'], t['normal'], t['uv'], t['colour'], f0, dict(triangles_in=len(f0), triangles_out=len(f0), moved=0)
    rows = json.loads(C.LINE.read_text())['samples']
    start = SS.valley_carve_start(ln, rows)
    site = ln.station()

    def hidden(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        s, _, _ = ln.project(x.ravel(), y.ravel())
        keep = np.nan_to_num(s, nan=-1.).reshape(x.shape) >= start
        keep |= SS.inside(site, x, y, margin=SS.STATION_REACH)
        return ~keep

    k_bridge = ln.bridge()
    lo_b, hi_b = k_bridge.ends() if k_bridge is not None else (0., 0.)

    def near_bridge(p):
        if k_bridge is None:
            return np.zeros(len(p), bool)
        x, y = p[:, 0], p[:, 1]
        d, wr = k_bridge.road_dw(x, y)
        deck_end = ((np.abs(d - lo_b) <= 1.2) | (np.abs(d - hi_b) <= 1.2)) & (np.abs(wr) <= SS.DECK_HALF)
        return (SS.bridge_walls(x, y, k_bridge, margin=.55) | deck_end) & ~np.asarray(hidden(x, y), bool)

    # Pre-filter planar triangles so flat station floors and forecourts are not flood-subdivided.
    n = VALLEY_SUBDIV
    ij = [(i, j) for i in range(n + 1) for j in range(n + 1 - i)]
    idx = {p: k for k, p in enumerate(ij)}
    c_idx = [idx[(0, 0)], idx[(n, 0)], idx[(0, n)]]
    bary = np.array([(1 - (i + j) / n, i / n, j / n) for i, j in ij])
    tmpl = np.array([q for i in range(n) for j in range(n - i) for q in
                     [(idx[(i, j)], idx[(i + 1, j)], idx[(i, j + 1)])]
                     + ([(idx[(i + 1, j)], idx[(i + 1, j + 1)], idx[(i, j + 1)])] if i + j < n - 1 else [])])
    corners = {0: idx[(0, 0)], 1: idx[(n, 0)], 2: idx[(0, n)]}
    on_v = ~hidden(v[:, 0], v[:, 1])
    v_carved = v.copy()
    if on_v.any():
        v_carved[on_v, 2] = E.carve(v[on_v, 0], v[on_v, 1], v[on_v, 2], ln)
    pts = np.einsum('pk,tkc->tpc', bary, v[f0])
    flat_pts = pts.reshape(-1, 3)
    on_p = ~hidden(flat_pts[:, 0], flat_pts[:, 1])
    z_carved = flat_pts[:, 2].copy()
    if on_p.any():
        z_carved[on_p] = E.carve(flat_pts[on_p, 0], flat_pts[on_p, 1], flat_pts[on_p, 2], ln)
    z_carved = z_carved.reshape(len(f0), len(bary))
    z_lin = np.einsum('pk,tk->tp', bary, v_carved[f0, 2])
    z_err = np.max(np.abs(z_carved - z_lin), axis=1)
    col_p = np.einsum('pk,tkc->tpc', bary, t['colour'][f0]).reshape(-1, 4)
    col_carved = col_p.copy()
    if on_p.any():
        col_carved[on_p] = _repaint(col_p[on_p], flat_pts[on_p, 0], flat_pts[on_p, 1], z_carved.ravel()[on_p], flat_pts[on_p, 2], ln)
    col_carved = col_carved.reshape(len(f0), len(bary), 4)
    col_lin = np.einsum('pk,tkc->tpc', bary, col_carved[:, c_idx, :])
    col_err = np.max(np.abs(col_carved - col_lin), axis=(1, 2))
    centres = v[f0].mean(1)
    hit = ((z_err > .004) | (col_err > .06) | near_bridge(centres)) & ~hidden(centres[:, 0], centres[:, 1])
    sel = np.flatnonzero(hit)
    keep = np.flatnonzero(~hit)
    if len(sel):
        fs = f0[sel]
        pts_sel = pts[sel]
        ids = np.full(pts_sel.shape[:2], -1, np.int64)
        for c, p in corners.items():
            ids[:, p] = fs[:, c]
        fresh = ids < 0
        q = pts_sel[fresh]
        key = np.round(q * 1000.).astype(np.int64)
        _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
        ids[fresh] = len(v) + inverse.ravel()
        new_v = q[first]
        a = {k: np.concatenate([arr, np.einsum('pk,tkc->tpc', bary, arr[fs])[fresh][first]]) for k, arr in attrs.items()}
        allv = np.concatenate([v, new_v])
        retained = f0[keep]
        centres_c, retained, parents, _ = E._conform_neighbors(v, retained, fs, ids, idx, n, allv)
        if len(centres_c):
            allv = np.concatenate([allv, centres_c])
            for k, arr in attrs.items():
                a[k] = np.concatenate([a[k], arr[parents].mean(1)])
        on_all = ~hidden(allv[:, 0], allv[:, 1])
        allv[on_all, 2] = E.carve(allv[on_all, 0], allv[on_all, 1], allv[on_all, 2], ln)
        f = np.concatenate([retained, ids[:, tmpl].reshape(-1, 3)])
        v = allv
        if k_bridge is not None:
            v, f, a = _bisect_near(v, f, a, near_bridge, WALL_FINE)
            redo = near_bridge(v)
            v[redo, 2] = E.carve(v[redo, 0], v[redo, 1], a['natural'][redo, 0], ln)
        a0, a1, u0, u1 = SS.FORECOURT

        def near_forecourt(p):
            pa, pu = site.local(p[:, 0], p[:, 1])
            out = SS.rect_excess(pa, pu, (a0 - 50., a1, u0, u1))
            depth = np.minimum(np.minimum(a1 - pa, pu - u0), u1 - pu)
            return (pa >= a0 - 1.) & (out <= SS.FORECOURT_HOLD + 2.) & (depth <= 1.5)
        if near_forecourt(v[f].mean(1)).any():
            first_fc = len(v)
            v, f, a = _bisect_near(v, f, a, near_forecourt, FORECOURT_FINE)
            redo = (np.arange(len(v)) >= first_fc) & ~_border_vertices(len(v), f)
            v[redo, 2] = E.carve(v[redo, 0], v[redo, 1], a['natural'][redo, 0], ln)
        pts_rd, _ = site.access()
        near_rd = lambda p: SS.polyline_excess(p[:, 0], p[:, 1], pts_rd, SS.ACCESS_HALF)[0] <= 2.5  # noqa: E731
        if near_rd(v[f].mean(1)).any():
            first_rd = len(v)
            v, f, a = _bisect_near(v, f, a, near_rd, ACCESS_FINE)
            redo = (np.arange(len(v)) >= first_rd) & ~_border_vertices(len(v), f)
            v[redo, 2] = E.carve(v[redo, 0], v[redo, 1], a['natural'][redo, 0], ln)
        moved_mask = np.abs(v[:, 2] - a['natural'][:, 0]) > 1e-3
        moved = int((np.abs(v[:, 2] - a['natural'][:, 0]) > .01).sum())
        if moved:
            a['colour'] = _repaint(a['colour'], v[:, 0], v[:, 1], v[:, 2], a['natural'][:, 0], ln)
            a['normals'] = E._normals(v, f, a['normals'], moved_mask)
    else:
        v, f, a = v_carved, f0, dict(attrs)
        moved_mask = np.abs(v[:, 2] - a['natural'][:, 0]) > 1e-3
        moved = int((np.abs(v[:, 2] - a['natural'][:, 0]) > .01).sum())
        if moved:
            a['colour'] = _repaint(a['colour'], v[:, 0], v[:, 1], v[:, 2], a['natural'][:, 0], ln)
            a['normals'] = E._normals(v, f, a['normals'], moved_mask)
    v, f, a, paved = _salon_path(v, f, a)
    local_pos = (v - origin) @ source.FRAME
    local_norm = a['normals'] @ source.FRAME
    report = dict(triangles_in=int(len(f0)), triangles_out=int(len(f)), moved=moved, paved=paved)
    return doc, local_pos, local_norm, a['uv'], a['colour'], f, report


@lru_cache(maxsize=8)
def valley_tile_triangles(path):
    """Local Belmonte-frame triangles (N, 3, 3) of a carved valley tile, evaluated in memory from the natural GLB."""
    _, local_pos, _, _, _, faces, _ = carve_valley_tile(path)
    verts = local_pos.astype(float) @ source.FRAME.T
    return verts[faces]


def write_carved_valley_tile(source_path, dest_path):
    """Write a carved valley tile GLB to dest_path (under build/yorimichi/belmonte/glb/) and return (triangles, bounds_m, report)."""
    doc, local_pos, local_norm, uv, colour, faces, report = carve_valley_tile(source_path)
    _write_glb(dest_path, doc, local_pos, local_norm, uv, colour, faces)
    verts = local_pos.astype(float) @ source.FRAME.T
    lo, hi = verts.min(0), verts.max(0)
    return int(len(faces)), [[float(c) for c in lo], [float(c) for c in hi]], report


def carved_valley_data(source_path):
    """The same final terrain bytes and bounds, before any render mesh export."""
    doc,local_pos,local_norm,uv,colour,faces,report=carve_valley_tile(source_path)
    data=encoded_tile(doc,local_pos,local_norm,uv,colour,faces)
    verts=local_pos.astype(float)@source.FRAME.T
    return data,int(len(faces)),[verts.min(0).tolist(),verts.max(0).tolist()],report
