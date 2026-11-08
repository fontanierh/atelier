"""Top-down plan of the generated park for the owner's page (numpy + pillow; native metres, x right, z down).

Height-shaded (the top surface's height, hill-shaded from the north-west), feature outlines (where the top face's
feature changes), riding lines, air arcs (lip to touchdown, bowed by the air's height so they read as flights) and the
validators' failure locations (red rings, numbered as in geometry-report.json).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LINE_COLOURS = [(233, 94, 47), (40, 120, 220), (30, 160, 90), (170, 70, 200), (220, 170, 20), (20, 170, 180)]
MAX_PX = 2400        # the longer side of the image at most, in pixels


def top_raster(T, feature, box, px, budget=4_000_000):
    """The highest face over each pixel centre: (height (h,w) NaN where empty, feature id (h,w) -1 where empty)."""
    x0, z0, x1, z1 = box
    w = int(math.ceil((x1 - x0) / px)); h = int(math.ceil((z1 - z0) / px))
    H = np.full(h * w, -np.inf); Fid = np.full(h * w, -1, 'i8')
    P = T[:, :, [0, 2]]
    e1 = P[:, 1] - P[:, 0]; e2 = P[:, 2] - P[:, 0]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    keep = np.abs(det) > 1e-12                                   # vertical faces have no plan area
    c0 = np.clip(np.floor((P[:, :, 0].min(1) - x0) / px - .5).astype('i8'), 0, w - 1)
    c1 = np.clip(np.ceil((P[:, :, 0].max(1) - x0) / px - .5).astype('i8'), 0, w - 1)
    r0 = np.clip(np.floor((P[:, :, 1].min(1) - z0) / px - .5).astype('i8'), 0, h - 1)
    r1 = np.clip(np.ceil((P[:, :, 1].max(1) - z0) / px - .5).astype('i8'), 0, h - 1)
    inside = keep & (P[:, :, 0].max(1) >= x0) & (P[:, :, 0].min(1) <= x1) & (P[:, :, 1].max(1) >= z0) & (P[:, :, 1].min(1) <= z1)
    f = np.flatnonzero(inside)
    nc = (c1 - c0 + 1)[f]; nr = (r1 - r0 + 1)[f]; cnt = nc * nr
    cum = np.cumsum(cnt)
    if not len(cum):
        return H.reshape(h, w) * np.nan, Fid.reshape(h, w)
    cuts = np.unique(np.r_[0, np.searchsorted(cum, np.arange(budget, cum[-1], budget)), len(f)])
    for a, b in zip(cuts[:-1], cuts[1:]):
        k = cnt[a:b]
        if not k.sum():
            continue
        fi = np.repeat(f[a:b], k)
        loc = np.arange(k.sum()) - np.repeat(np.cumsum(k) - k, k)
        cc = c0[fi] + loc % np.repeat(nc[a:b], k); rr = r0[fi] + loc // np.repeat(nc[a:b], k)
        qx = x0 + (cc + .5) * px - P[fi, 0, 0]; qz = z0 + (rr + .5) * px - P[fi, 0, 1]
        u = (qx * e2[fi, 1] - qz * e2[fi, 0]) / det[fi]; v = (e1[fi, 0] * qz - e1[fi, 1] * qx) / det[fi]
        ok = (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        y = T[fi, 0, 1] + u * (T[fi, 1, 1] - T[fi, 0, 1]) + v * (T[fi, 2, 1] - T[fi, 0, 1])
        idx = (rr * w + cc)[ok]; y = y[ok]; fi = fi[ok]
        o = np.lexsort((y, idx))                                  # per pixel, the highest last
        idx, y, fi = idx[o], y[o], fi[o]
        last = np.r_[idx[1:] != idx[:-1], True]
        idx, y, fi = idx[last], y[last], fi[last]
        better = y > H[idx]
        H[idx[better]] = y[better]; Fid[idx[better]] = feature[fi[better]]
    H[~np.isfinite(H)] = np.nan
    return H.reshape(h, w), Fid.reshape(h, w)


def _palette(t):
    """Height colours: low teal-grey through warm sand to pale concrete (t in [0, 1])."""
    stops = np.array([[0., 70, 96, 110], [.35, 120, 150, 140], [.65, 214, 190, 150], [1., 246, 238, 224]])
    out = np.empty(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, stops[:, 0], stops[:, c + 1])
    return out


def shade(H, px):
    """RGB (h,w,3) uint8: height colours times a north-west hill shade; empty pixels light grey."""
    empty = np.isnan(H)
    lo, hi = (np.nanmin(H), np.nanmax(H)) if (~empty).any() else (0., 1.)
    Hf = np.where(empty, lo, H)
    gz, gx = np.gradient(Hf, px)
    n = np.stack([-gx, np.ones_like(gx), -gz], -1); n /= np.linalg.norm(n, axis=-1, keepdims=True)
    light = np.array([-.5, .75, -.45]); light /= np.linalg.norm(light)
    lam = np.clip(n @ light, 0, 1)
    rgb = _palette((Hf - lo) / max(hi - lo, 1e-9)) * (.45 + .55 * lam)[..., None]
    rgb[empty] = (232, 232, 228)
    return np.clip(rgb, 0, 255).astype('u1'), (float(lo), float(hi))


def render_plan(meshes, out, lanes=(), airs=(), report=None, box=None, px=None, title='Crater Park v2 plan',
                pad=4., line_of=None):
    """Write the plan PNG. meshes: validate.Mesh (render ones are drawn). lanes: validate.Lane. airs: dicts with
    'lip' (x, y, z), 'land' (x, y, z), optional 'apex' (height of the flight's top, native y) and 'label'.
    report: geometry-report.json's dict, whose failure locations are ringed. line_of: {feature id: line index} colours
    the outlines by line. Returns (path, metres per pixel, box)."""
    from .validate import as_mesh
    meshes = [as_mesh(m) for m in meshes]
    ren = [m for m in meshes if m.domain == 'render'] or meshes
    T = np.concatenate([m.T for m in ren]) if ren else np.zeros((0, 3, 3))
    feat = np.concatenate([m.feature for m in ren]) if ren else np.zeros(0, 'i8')
    if not len(T) and box is None:                               # nothing built: say so rather than fail
        img = Image.new('RGB', (720, 120), (250, 250, 247)); d = ImageDraw.Draw(img)
        d.text((10, 10), title, fill=(20, 20, 20)); d.text((10, 50), 'NO GEOMETRY: the park has no drawn faces', fill=(200, 10, 10))
        img.save(out)
        return out, None, None
    if box is None:
        lo = T.reshape(-1, 3).min(0); hi = T.reshape(-1, 3).max(0)
        box = (lo[0] - pad, lo[2] - pad, hi[0] + pad, hi[2] + pad)
    x0, z0, x1, z1 = box
    if px is None:
        px = max((x1 - x0), (z1 - z0)) / MAX_PX
        px = max(px, .05)
    H, Fid = top_raster(T, feat, box, px)
    rgb, (ylo, yhi) = shade(H, px)
    # feature outlines: a pixel whose right or lower neighbour has another top feature
    edge = np.zeros(Fid.shape, bool)
    edge[:, :-1] |= Fid[:, :-1] != Fid[:, 1:]; edge[:-1] |= Fid[:-1] != Fid[1:]
    edge &= ~np.isnan(H)
    col = np.full(Fid.shape + (3,), 40, 'u1')
    if line_of:
        for fid, li in line_of.items():
            col[Fid == fid] = LINE_COLOURS[li % len(LINE_COLOURS)]
    rgb[edge] = (.35 * rgb[edge] + .65 * col[edge]).astype('u1')
    margin = 64
    W = max(rgb.shape[1], 720)
    img = Image.new('RGB', (W, rgb.shape[0] + margin), (250, 250, 247))
    img.paste(Image.fromarray(rgb), (0, margin))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:                                             # pillow < 10.1
        font = ImageFont.load_default()
    to = lambda x, z: ((x - x0) / px, (z - z0) / px + margin)
    for k, lane in enumerate(lanes):
        c = LINE_COLOURS[k % len(LINE_COLOURS)]
        pts = [to(x, z) for x, z in np.asarray(lane.path)]
        if len(pts) > 1:
            d.line(pts, fill=c, width=max(2, int(.6 / px)))
            # an arrow head at the end, along the last segment
            (ax, az), (bx, bz) = pts[-2], pts[-1]
            ang = math.atan2(bz - az, bx - ax); s = max(8, 2. / px)
            d.polygon([(bx, bz), (bx - s * math.cos(ang - .4), bz - s * math.sin(ang - .4)),
                       (bx - s * math.cos(ang + .4), bz - s * math.sin(ang + .4))], fill=c)
            d.text((pts[0][0] + 6, pts[0][1] + 6), lane.name, fill=c, font=font)
    for a in airs:
        lip, land = np.asarray(a['lip'], 'f8'), np.asarray(a['land'], 'f8')
        p0, p1 = np.array(to(lip[0], lip[2])), np.array(to(land[0], land[2]))
        v = p1 - p0; L = np.linalg.norm(v)
        if L < 1:
            continue
        nrm = np.array([-v[1], v[0]]) / L
        rise = float(a.get('apex', max(lip[1], land[1])) - max(lip[1], land[1]))
        bow = min(.25 * L, (abs(rise) + 1.) / px)
        pts = [tuple(p0 + v * t + nrm * bow * 4 * t * (1 - t)) for t in np.linspace(0, 1, 33)]
        for i in range(0, 32, 2):                                 # dashed
            d.line([pts[i], pts[i + 1]], fill=(20, 20, 20), width=3)
        d.ellipse([p0[0] - 4, p0[1] - 4, p0[0] + 4, p0[1] + 4], fill=(20, 20, 20))
        d.ellipse([p1[0] - 5, p1[1] - 5, p1[0] + 5, p1[1] + 5], outline=(20, 20, 20), width=2)
        gap = float(np.linalg.norm((land - lip)[[0, 2]]))
        label = a.get('label') or f'{gap:.0f} m air'
        mid = pts[16]
        d.text((mid[0] + 6, mid[1] - 8), f'{label}  (drop {lip[1] - land[1]:+.1f} m)', fill=(20, 20, 20), font=font)
    n = 0; per_check = {}
    if report:
        for name, chk in report.get('checks', {}).items():
            for f in chk.get('failures', []) or []:
                w = f.get('where')
                if not w or w[0] is None or len(w) < 3:
                    continue
                n += 1; per_check[name] = per_check.get(name, 0) + 1
                x, z = to(w[0], w[2])
                r = 9
                d.ellipse([x - r, z - r, x + r, z + r], outline=(220, 20, 20), width=3)
    # header, two rows: title and failure count; height scale, metre bar and axes
    d.text((10, 6), title, fill=(20, 20, 20), font=font)
    if n:
        d.text((W // 3, 6), f'{n} failure locations ringed: ' + ', '.join(f'{k} {v}' for k, v in per_check.items()),
               fill=(200, 10, 10), font=font)
    sw = 200
    bar = _palette(np.linspace(0, 1, sw))
    for i in range(sw):
        d.line([(10 + i, 34), (10 + i, 48)], fill=tuple(int(c) for c in bar[i]))
    d.text((16 + sw, 34), f'height {ylo:.1f} to {yhi:.1f} m', fill=(20, 20, 20), font=font)
    ten = 10. / px
    while ten > W / 4:
        ten /= 2
    bx = W - ten - 16
    d.line([(bx, 44), (bx + ten, 44)], fill=(20, 20, 20), width=3)
    d.text((bx, 26), f'{ten * px:g} m', fill=(20, 20, 20), font=font)
    d.text((bx - 130, 38), 'x right, z down', fill=(90, 90, 90), font=font)
    img.save(out)
    return out, px, box


def render_park(park, out, report=None, airs=None, **kw):
    """The plan of a dsl.Park: its drawn faces, its RideLines as lanes, its airs (or the park's checks with 'lip' and
    'land' points) and the report's failures."""
    from .validate import park_meshes, park_lanes
    render, _, _ = park_meshes(park)
    if airs is None:
        airs = (report or {}).get('airs') or [c for c in park.checks if isinstance(c, dict) and 'lip' in c and 'land' in c]
    line_of = {}
    for k, line in enumerate(park.lines):
        for i, n in enumerate(park.mesh.features):
            if any(n == f or n.startswith(f + '.') for f in line.features):
                line_of.setdefault(i, k)
    return render_plan(render, out, lanes=park_lanes(park), airs=airs, report=report, line_of=line_of, **kw)


# ---------------------------------------------------------------------------------------------------- 3-D model (glTF)

GLB_COLOURS = {'material_000': '#d9d3c7', 'material_010': '#d9d3c7', 'material_019': '#3d8fd6',
               'coping_steel': '#9aa3ad', 'material_016': '#c08a4e', 'material_024': '#8c7a55'}
GLB_OTHER = '#c4bdb0'           # any other material: a slightly darker concrete (walls, ledges)
GLB_GROUND = '#8c7a55'          # warm earth / autumn grass, every ground-role face
GLB_LINES = {'L1': '#ff7a1a', 'L2': '#2f7bff', 'L3': '#22c55e', 'L4': '#a855f7'}
GLB_AIR = '#ffe14d'
GLB_LIFT = -40.                 # native y minus this: world height (native y + 680, placement.LIFT) minus 640
GLB_MAX_BYTES = 12_000_000


def _linear(hexcol):
    """sRGB '#rrggbb' to linear RGB in [0, 1] (glTF vertex colours are linear)."""
    c = np.array([int(hexcol[i:i + 2], 16) for i in (1, 3, 5)], 'f8') / 255.
    return np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)


def _air_arc(lip, land, apex, n=40):
    """A parabola from lip to land through the apex height (native)."""
    lip, land = np.asarray(lip, 'f8'), np.asarray(land, 'f8')
    t = np.linspace(0, 1, n)
    y0, y1, ya = lip[1], land[1], max(apex, lip[1], land[1])
    # y(t) = y0 + b t + c t^2 with max ya: solve for b (the root giving a top inside [0, 1])
    d = y1 - y0
    disc = max((ya - y0) * (ya - y1), 0.)
    b = 2 * ((ya - y0) + math.sqrt(disc))
    c = d - b
    P = lip[None] + t[:, None] * (land - lip)[None]
    P[:, 1] = y0 + b * t + c * t * t
    return P


def park_glb(park, out, report=None, lift=GLB_LIFT, centre=None, max_bytes=GLB_MAX_BYTES, ground_reach=None):
    """Write the park as a binary glTF 2.0 (one mesh, one vertex-coloured material; a second node with each line's path
    0.5 m over its surface and each air's arc as line strips). Native metres, y up; x and z recentred on the park,
    y = native y - `lift` (world height - 640 m). Base faces are left out. Returns (path, info)."""
    import json as _json
    import struct
    from . import dsl
    from .validate import heights_under
    m = park.mesh
    keep = np.asarray(m.role) != dsl.ROLE[dsl.BASE]
    F = np.asarray(m.F)[keep]; role = np.asarray(m.role)[keep]; mat = np.asarray(m.material)[keep]
    V = np.asarray(m.V, 'f8'); N = np.asarray(m.N, 'f8')
    is_ground = role == dsl.ROLE[dsl.GROUND]
    if ground_reach is not None:                                 # optional: drop ground faces far from every feature
        feat_c = V[F[~is_ground]].mean(1)[:, [0, 2]]
        g_c = V[F[is_ground]].mean(1)[:, [0, 2]]
        cell = ground_reach
        occ = {tuple(k) for k in np.floor(feat_c / cell).astype('i8').tolist()}
        gk = np.floor(g_c / cell).astype('i8')
        near = np.array([any((a + i, b + j) in occ for i in (-1, 0, 1) for j in (-1, 0, 1)) for a, b in gk.tolist()], bool)
        sel = np.ones(len(F), bool); sel[np.flatnonzero(is_ground)[~near]] = False
        F, role, mat, is_ground = F[sel], role[sel], mat[sel], is_ground[sel]
    names = np.asarray(dsl.MATERIALS, object)[mat]
    palette = {}
    cid = np.empty(len(F), 'i8')
    for k, (g, nm) in enumerate(zip(is_ground, names)):
        key = GLB_GROUND if (g or nm == 'material_024') else GLB_COLOURS.get(nm, GLB_OTHER)
        cid[k] = palette.setdefault(key, len(palette))
    cols = np.array([_linear(h) for h in palette], 'f8')
    # a vertex per (vertex, colour): faces of two colours sharing a vertex each get their own
    corner_v = F.ravel(); corner_c = np.repeat(cid, 3)
    key = corner_v * len(palette) + corner_c
    uk, inv = np.unique(key, return_inverse=True)
    vi = uk // len(palette); ci = uk % len(palette)
    if centre is None:
        lo = V[vi].min(0); hi = V[vi].max(0); centre = ((lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2)
    off = np.array([centre[0], lift, centre[1]])
    P = (V[vi] - off).astype('f4')
    Nn = N[vi]; Nn = (Nn / np.maximum(np.linalg.norm(Nn, axis=1, keepdims=True), 1e-12)).astype('f4')
    C = np.c_[np.round(cols[ci] * 255), np.full(len(ci), 255)].astype('u1')
    I = inv.reshape(-1, 3).astype('u4')
    # line strips: each line's path 0.5 m over its riding surface; each air's arc
    strips = []
    T = V[F[~is_ground]]
    for line in park.lines:
        path = np.asarray(line.path, 'f8')
        if len(path) < 2:
            continue
        p, h, _ = heights_under(T, path)
        y = path[:, 1].copy()
        for k in range(len(path)):
            hk = h[p == k]
            if len(hk):
                y[k] = hk.max()
        pts = np.c_[path[:, 0], y + .5, path[:, 2]]
        strips.append((pts, GLB_LINES.get(str(line.name).split('-')[0].split('.')[0][:2], '#ff3d81')))
    for a in (report or {}).get('airs', []) or []:
        strips.append((_air_arc(a['lip'], a['land'], a.get('apex', a['lip'][1])), GLB_AIR))
    # binary layout
    blob = bytearray(); views = []; accessors = []

    def add(arr, target, comp, typ, normalized=False, minmax=False):
        while len(blob) % 4:
            blob.append(0)
        views.append({'buffer': 0, 'byteOffset': len(blob), 'byteLength': arr.nbytes, **({'target': target} if target else {})})
        blob.extend(arr.tobytes())
        acc = {'bufferView': len(views) - 1, 'componentType': comp, 'count': int(len(arr) if arr.ndim > 1 or typ == 'SCALAR' else len(arr)),
               'type': typ}
        if typ == 'SCALAR':
            acc['count'] = int(arr.size)
        if normalized:
            acc['normalized'] = True
        if minmax:
            acc['min'] = arr.min(0).astype(float).tolist(); acc['max'] = arr.max(0).astype(float).tolist()
        accessors.append(acc)
        return len(accessors) - 1
    a_pos = add(P, 34962, 5126, 'VEC3', minmax=True)
    a_nrm = add(Nn, 34962, 5126, 'VEC3')
    a_col = add(C, 34962, 5121, 'VEC4', normalized=True)
    a_idx = add(I.ravel(), 34963, 5125, 'SCALAR')
    prims = [{'attributes': {'POSITION': a_pos, 'NORMAL': a_nrm, 'COLOR_0': a_col}, 'indices': a_idx, 'material': 0, 'mode': 4}]
    line_prims = []
    for pts, hexcol in strips:
        Q = (pts - off).astype('f4')
        Cq = np.tile(np.r_[np.round(_linear(hexcol) * 255), 255].astype('u1'), (len(Q), 1))
        line_prims.append({'attributes': {'POSITION': add(Q, 34962, 5126, 'VEC3', minmax=True),
                                          'COLOR_0': add(Cq, 34962, 5121, 'VEC4', normalized=True)},
                           'material': 1, 'mode': 3})
    while len(blob) % 4:
        blob.append(0)
    meshes = [{'name': 'crater_park', 'primitives': prims}]
    nodes = [{'name': 'crater_park', 'mesh': 0}]
    if line_prims:
        meshes.append({'name': 'lines_and_airs', 'primitives': line_prims}); nodes.append({'name': 'lines_and_airs', 'mesh': 1})
    gltf = {'asset': {'version': '2.0', 'generator': 'craterpark v2 plan_png.park_glb'},
            'scene': 0, 'scenes': [{'nodes': list(range(len(nodes)))}], 'nodes': nodes, 'meshes': meshes,
            'materials': [{'name': 'park', 'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0.,
                                                                    'roughnessFactor': .85}},
                          {'name': 'lines', 'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0.,
                                                                     'roughnessFactor': 1.}, 'emissiveFactor': [1, 1, 1],
                           'extensions': {'KHR_materials_unlit': {}}}],
            'extensionsUsed': ['KHR_materials_unlit'],
            'accessors': accessors, 'bufferViews': views, 'buffers': [{'byteLength': len(blob)}],
            'extras': {'frame': 'native metres, y up: gltf = native - offset_native (y: world height - 640 m)',
                       'offset_native': off.tolist()}}
    js = _json.dumps(gltf, separators=(',', ':')).encode()
    js += b' ' * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(blob)
    if total > max_bytes and ground_reach is None:
        return park_glb(park, out, report, lift, centre, max_bytes, ground_reach=30.)
    with open(out, 'wb') as fh:
        fh.write(struct.pack('<III', 0x46546C67, 2, total))
        fh.write(struct.pack('<II', len(js), 0x4E4F534A)); fh.write(js)
        fh.write(struct.pack('<II', len(blob), 0x004E4942)); fh.write(bytes(blob))
    return out, {'bytes': total, 'vertices': int(len(P)), 'triangles': int(len(I)), 'strips': len(strips),
                 'offset_native': off.tolist(), 'ground_trimmed': ground_reach is not None}


# ---------------------------------------------------------------------------------------------------- viewer JSON

def _srgb(hexcol):
    return [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]


def _surface_y(park, pts, features_only=False):
    """The highest drawn non-base surface over each plan point (x, z) (NaN where none); features_only: not the ground."""
    from . import dsl
    from .validate import heights_under
    m = park.mesh
    keep = np.asarray(m.role) != dsl.ROLE[dsl.BASE]
    if features_only:
        keep &= np.asarray(m.role) != dsl.ROLE[dsl.GROUND]
    T = np.asarray(m.V)[np.asarray(m.F)[keep]]
    Q = np.c_[np.asarray(pts)[:, 0], np.zeros(len(pts)), np.asarray(pts)[:, 1]]
    p, h, _ = heights_under(T, Q)
    y = np.full(len(Q), np.nan)
    np.fmax.at(y, p, h)
    return y


def _nice(fid, line_id):
    """'L1_canyon' -> 'Canyon'; 'L3_valley' -> 'Valley'."""
    t = str(fid)
    if t.startswith(line_id + '_'):
        t = t[len(line_id) + 1:]
    return t.replace('_', ' ').strip().title() or t


def layout_labels(layout, park, lift=GLB_LIFT):
    """Feature labels in native metres (x, y, z): [{text, pos, kind}] from a layout module's LINES (features along each
    path), TOWER and BOWLS, each placed 3-4 m over the built surface at the feature. Features with no geometry under
    them are marked '(planned)'. Heights in the text are world metres (native y + 680) where they name a level."""
    world = lambda y: y + 680.
    out = []
    tower = getattr(layout, 'TOWER', None)
    rollin_name = {v: k for k, v in (tower or {}).get('roll_ins', {}).items()}
    for line in getattr(layout, 'LINES', ()):
        try:
            k = np.asarray(layout.knots(line, 1.))
        except Exception:
            k = None
        yat = (lambda s: float(np.interp(s, k[:, 0], k[:, 1]))) if k is not None and len(k) else (lambda s: float(line.y0))
        feats = list(line.features)
        for i, f in enumerate(feats):
            kind = f.kind.lower(); p = dict(f.params)
            mid = (f.s0 + f.s1) / 2
            (x, z), _ = line.path.at(mid)
            ys = _surface_y(park, [(x, z)])[0]
            built = bool(np.isfinite(_surface_y(park, [(x, z)], features_only=True)[0]))
            y = (ys if np.isfinite(ys) else yat(mid)) + 3.
            name = _nice(f.id, line.id)
            text = label = None
            if kind == 'roll_in':
                drop = yat(f.s0) - yat(f.s1)
                label = 'rollin'
                text = f"{rollin_name.get(line.id, line.id)} roll-in · {line.name} · {drop:.0f} m drop · {p.get('face_deg', '?')}° face"
                (x, z), _ = line.path.at(f.s0 + 2.); y = yat(f.s0) + 4.
            elif kind == 'gap':
                take = next((g for g in reversed(feats[:i]) if g.tag == 'takeoff' or 'takeoff' in g.kind or g.kind == 'kicker'), None)
                lip = (take.params.get('lip_deg') if take else None)
                land = next((g for g in feats[i + 1:] if g.tag == 'landing' or 'landing' in g.kind), None)
                drop = yat(f.s0) - yat(land.s0) if land else None
                label = 'gap'
                slope = land.params.get('slope_deg') if land else None
                text = f"{line.id} {name} · {f.s1 - f.s0:.0f} m gap" + (f" · {lip:.0f}° lip" if lip is not None else '') + \
                    (f" · lands {drop:.1f} m lower" if drop is not None else '') + (f" on {slope:.0f}°" if slope else '')
                y = yat(f.s0) + 5.
                built = bool(take and np.isfinite(_surface_y(park, [line.path.at(f.s0 - .5)[0]], features_only=True)[0]))
            elif kind in ('valley', 'half_pipe', 'halfpipe', 'half_bowl', 'halfbowl', 'channel'):
                label = 'halfbowl'
                bits = [f"{p['floor']:.0f} m floor" if 'floor' in p else None,
                        f"{p['wall_height']:.0f} m walls" if 'wall_height' in p else None,
                        f"R{p['wall_r']:.0f}" if 'wall_r' in p else None,
                        f"{p['grade_deg']:+.0f}° grade" if 'grade_deg' in p else None]
                text = f"{line.id} {name} · " + ', '.join(b for b in bits if b)
            elif kind in ('quarter', 'quarter_pipe', 'quarterpipe', 'qp', 'vert'):
                label = 'quarterpipe'
                text = f"{line.id} {name} QP · {p.get('height', p.get('wall_height', '?'))} m" + \
                    (f" + {p['vert']} m vert" if p.get('vert') else '') + (f" · R{p['r']}" if 'r' in p else '')
            elif kind in ('snake', 'berm', 'bank'):
                berms = p.get('berms') or ()
                for j, (b0, b1) in enumerate(berms):
                    s = f.s0 + (b0 + b1) / 2
                    (bx, bz), _ = line.path.at(s)
                    by = _surface_y(park, [(bx, bz)])[0]
                    bb = bool(np.isfinite(_surface_y(park, [(bx, bz)], features_only=True)[0]))
                    out.append({'text': f"{line.id} berm {j + 1}" + (f" · {p['outer_wall_in_berms']:.0f} m outer wall" if 'outer_wall_in_berms' in p else '')
                                + ('' if bb else ' (planned)'),
                                'pos': [bx, (by if np.isfinite(by) else yat(s)) + 3., bz], 'kind': 'berm', 'planned': not bb})
                label = 'berm'
                bits = [f"{abs(p['turn_deg']):.0f}° turn" if 'turn_deg' in p else None,
                        f"R{p['turn_r']:.0f}" if 'turn_r' in p else None,
                        f"{p['outer_bank_height']:.0f} m bank" if 'outer_bank_height' in p else None,
                        f"at {p['bank_deg']:.0f}°" if 'bank_deg' in p else None,
                        f"{p['wall']} m walls" if 'wall' in p else None,
                        f"{p['grade_deg']:+.0f}° grade" if 'grade_deg' in p else None]
                text = f"{line.id} {name} · " + ' '.join(b for b in bits if b)
            elif kind in ('kicker', 'transfer_takeoff'):
                continue                                              # named on its gap
            if text:
                out.append({'text': text + ('' if built else ' (planned)'), 'pos': [x, y, z], 'kind': label, 'planned': not built})
    if tower:
        cx, cz = tower['centre']
        ys = _surface_y(park, [(cx, cz)], features_only=True)[0]
        built = bool(np.isfinite(ys) and abs(ys - tower['y']) < 2.)
        out.append({'text': f"Tower · deck {world(tower['y']):.0f} m" + ('' if built else ' (planned)'),
                    'pos': [cx, tower['y'] + 6., cz], 'kind': 'tower', 'planned': not built})
    for b in getattr(layout, 'BOWLS', ()):
        cx, cz = b.centre
        ys = _surface_y(park, [(cx, cz)], features_only=True)[0]
        built = bool(np.isfinite(ys) and abs(ys - b.floor_y) < 1.5)
        out.append({'text': f"{b.id.replace('_', ' ').title()} · {b.rim_y - b.floor_y:.1f} m deep · R{b.r:g}"
                            + (f" + {b.vert:g} m vert" if b.vert else '') + ('' if built else ' (planned)'),
                    'pos': [cx, b.rim_y + 4., cz], 'kind': 'bowl', 'planned': not built})
    return out


def viewer_json(park, out, report=None, labels=(), max_bytes=10_000_000):
    """The owner's viewer file: base64 P (float32, recentred like the GLB, y = world height - 640), N (int8 x 127),
    C (uint8 sRGB), I (uint32); `lines` {name: [[x, y, z], ...]}; `labels` [{text, pos, kind}]; `airs` [[[x, y, z], ...]],
    all in that frame. Returns (path, info)."""
    import base64
    import json as _json
    from . import dsl
    m = park.mesh
    keep = np.asarray(m.role) != dsl.ROLE[dsl.BASE]
    F = np.asarray(m.F)[keep]; role = np.asarray(m.role)[keep]; mat = np.asarray(m.material)[keep]
    V = np.asarray(m.V, 'f8'); N = np.asarray(m.N, 'f8')
    names = np.asarray(dsl.MATERIALS, object)[mat]
    is_ground = role == dsl.ROLE[dsl.GROUND]
    palette = {}
    cid = np.array([palette.setdefault(GLB_GROUND if (g or nm == 'material_024') else GLB_COLOURS.get(nm, GLB_OTHER), len(palette))
                    for g, nm in zip(is_ground, names)], 'i8')
    key = F.ravel() * len(palette) + np.repeat(cid, 3)
    uk, inv = np.unique(key, return_inverse=True)
    vi = uk // len(palette); ci = uk % len(palette)
    lo = V[vi].min(0); hi = V[vi].max(0)
    off = np.array([(lo[0] + hi[0]) / 2, GLB_LIFT, (lo[2] + hi[2]) / 2])
    tr = lambda p: (np.asarray(p, 'f8') - off).round(3).tolist()
    Nn = N[vi] / np.maximum(np.linalg.norm(N[vi], axis=1, keepdims=True), 1e-12)
    cols = np.array([_srgb(h) for h in palette], 'u1')
    b64 = lambda a: base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()
    lines = {}
    for line in park.lines:
        path = np.asarray(line.path, 'f8')
        if len(path) < 2:
            continue
        y = _surface_y(park, path[:, [0, 2]])
        y = np.where(np.isfinite(y), y, path[:, 1]) + .5
        lines[str(line.name)] = tr(np.c_[path[:, 0], y, path[:, 2]])
    airs = [tr(_air_arc(a['lip'], a['land'], a.get('apex', a['lip'][1]))) for a in (report or {}).get('airs', []) or []]
    doc = {'frame': 'metres, y up; x, z recentred on the park, y = world height - 640 (native y + 40)',
           'offset_native': off.tolist(),
           'P': b64((V[vi] - off).astype('<f4')),
           'N': b64(np.clip(np.round(Nn * 127), -127, 127).astype('i1')),
           'C': b64(cols[ci]), 'I': b64(inv.reshape(-1, 3).astype('<u4')),
           'counts': {'vertices': int(len(vi)), 'triangles': int(len(F))},
           'lines': lines, 'labels': [dict(l, pos=tr(l['pos'])) for l in labels], 'airs': airs}
    s = _json.dumps(doc, separators=(',', ':'))
    if len(s) > max_bytes:
        raise ValueError(f'viewer json {len(s)} bytes > {max_bytes}')
    Path_ = __import__('pathlib').Path
    p = Path_(out); tmp = p.with_suffix('.tmp'); tmp.write_text(s); tmp.replace(p)
    return out, {'bytes': len(s), 'vertices': int(len(vi)), 'triangles': int(len(F)), 'labels': len(labels),
                 'lines': len(lines), 'airs': len(airs)}
