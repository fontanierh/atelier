"""Carve Belmonte's committed valley terrain for the railway's last stretch and its station (one-off source edit).

    uv run python games/yorimichi/tools/belmonte_station_terrain.py [--dry-run]

The valley's terrain tiles (assets/belmonte/meshes/SM_BM_BT_Terrain_*.glb) are committed sources that no build step
carves (regions/belmonte/build.py carves only the apron and the country around them). Since route v4 (Paul,
2026-10-17) the line ends in the valley: it runs in a cutting under the road from the south-east gate, and the station
stands in it. This tool edits those tiles once, in place, to the earthworks' design (train/earthworks.py, including
the station's ground from train/station_site.py): every touched triangle is subdivided to STEP metres and carved,
normals recomputed, and the four terrain layers repainted where the ground moved (Rock on cut faces, Dirt on the
formation, the forecourt and the access road, Green on new slopes). It also paints a dirt path from the Salon des
paris' terrace to the road below it (SALON_PATH). Along the overbridge's walls the triangles are refined again to
FINE, so the ground steps within the walls' thickness (earthworks.bridge_ground), and so along the forecourt's edges,
where the ground steps within station_site.FORECOURT_HOLD of the paving. Retained triangles
next to carved ones share their new edge nodes (earthworks.refine's conform_neighbors), so the carving leaves no
cracks.
Only the line's final cutting (from earthworks.VALLEY_LEAD before it) and the station's ground are carved: the
embankments further down the valley stay on their bank meshes (track.py bank_ranges), over the uncarved ground.

It reads the committed line (assets/vehicles/belmonte-train/line.json) and the station's site (train/station_site.py)
and records their digest in each carved tile's source.json entry (`railway_carved`): a tile already carved for that
line is left alone. Before its first carve a tile's natural version is kept in assets/belmonte/natural/: a tile carved
for another line is carved again from it, and the route study plans on it (belmonte/source.py terrain(natural=True)),
so the committed line stays its own result. The tool updates source.json and the asset library contract
(assets/source-library.json). Run it after changing the line or the station's site, then rebuild world.belmonte and
the steps after it. It refuses a line that does not end at the station's site (station_site.for_line): the riverside
terminus carves nothing in the valley.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
import argparse
import hashlib
import json
import struct

import numpy as np

from belmonte import layout as BM
from belmonte import source
from train import corridor as C
from train import earthworks as E
from train import station_site as SS

STEP = 2.0                  # metres: the carved triangles' size (the tiles are about 5 m)
FINE = .75                  # ... and along the overbridge's walls and the forecourt's edges, where the ground steps
# Paul, 2026-10-18: a dirt path from the road up to the Salon des paris' terrace, down the middle of its cypress
# avenue (two rows 13 m apart). It follows the ground; only its triangles are subdivided (to PATH_STEP) and painted.
SALON_PATH = dict(points=((623.1, 4733.), (647.8, 4771.)), half=2.0, soft=1.0)
PATH_STEP = 1.5
LAYERS = ('Dry', 'Green', 'Dirt', 'Rock')     # COLOR_0's channels (MI_B_terrain_town's layers)
NATURAL = yori.ASSETS / 'belmonte' / 'natural'
LIBRARY = yori.ASSETS / 'source-library.json'


def read(path):
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


def encode(colour):
    """COLOR_0 as the library stores it ('native-byte-rgb-linear-alpha'): the first three layers on bytes (multiples
    of 257), the fourth the rest of 65535."""
    w = np.clip(colour, 0, None)
    w = w / np.maximum(w.sum(1, keepdims=True), 1e-6)
    rgb = np.rint(w[:, :3] * 255).astype(np.int64)
    over = np.maximum(rgb.sum(1) - 255, 0)        # rounding up all three can pass 255
    for i in np.flatnonzero(over):
        rgb[i, np.argmax(rgb[i])] -= over[i]
    rgb *= 257
    return np.column_stack([rgb, 65535 - rgb.sum(1)]).astype('<u2')


def write(path, doc, position, normal, uv, colour, faces):
    """The tile with new buffers, keeping its nodes, material and extras."""
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
        COLOR_0=add(encode(colour), 5123, 'VEC4', 34962, normalized=True))
    big = len(position) > 65535
    prim['indices'] = add(faces.ravel().astype('<u4' if big else '<u2'), 5125 if big else 5123, 'SCALAR', 34963)
    doc['bufferViews'], doc['accessors'] = views, accessors
    binary = b''.join(blobs)
    doc['buffers'] = [dict(byteLength=len(binary))]
    path.write_bytes(source.glb_pack(doc, binary))


def repaint(colour, x, y, z, z0, ln):
    """The four layer weights where the ground moved: Rock on cut faces, Dirt on the formation and the station's
    ground, Green on new slopes."""
    rock, cess, fill = E.weights(x, y, z, z0, ln)
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


def _path_excess(x, y):
    pts = np.asarray(SALON_PATH['points'], float)
    return SS.polyline_excess(x, y, pts, SALON_PATH['half'])[0]


def salon_path(v, f, attrs):
    """The Salon's path: its triangles split to PATH_STEP and painted Dirt (soft edge). (v, f, attrs, changed)"""
    tri = v[f]
    probes = np.concatenate([tri, tri.mean(1, keepdims=True)], 1).reshape(-1, 3)
    sel = (_path_excess(probes[:, 0], probes[:, 1]) < SALON_PATH['soft'] + 1.).reshape(-1, 4).any(1)
    span = np.linalg.norm(tri - tri.mean(1, keepdims=True), axis=2).max(1)
    sel |= _path_excess(tri.mean(1)[:, 0], tri.mean(1)[:, 1]) < span
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
    w = 1 - E._smooth(_path_excess(v[:, 0], v[:, 1]) / SALON_PATH['soft'])
    out['colour'] = out['colour'] * (1 - w[:, None]) + np.array([0., 0., 1., 0.]) * w[:, None]
    return v, f, out, True


def bisect_near(v, f, attrs, near):
    """Bisect the triangles whose centroid is `near` until their edges are at most FINE, each at its longest edge with
    its neighbour across it (conforming: no crack). Attributes are interpolated. (v, f, attrs)"""
    v = np.asarray(v, float)
    f = np.asarray(f, np.int64)
    attrs = {k: np.asarray(x, float) for k, x in attrs.items()}
    for _ in range(40):
        tri = v[f]
        length = np.linalg.norm(tri - np.roll(tri, -1, 1), axis=2)          # edge j: corner j to j + 1
        longest = length.argmax(1)
        want = (length.max(1) > FINE) & near(tri.mean(1))
        if not want.any():
            break
        # every edge to split: the longest of each wanted triangle, closed over neighbours (each triangle with a
        # split edge also splits its longest)
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
            mid[e] = first_free = len(v) + len(new_v)
            new_v.append((v[e[0]] + v[e[1]]) / 2)
            for k in attrs:
                new_attr[k].append((attrs[k][e[0]] + attrs[k][e[1]]) / 2)
        faces = []
        for i in range(len(f)):
            j = longest[i]
            c = [f[i, (j + q) % 3] for q in range(3)]         # c0-c1 the longest edge, c2 opposite
            e = [key(i, (j + q) % 3) for q in range(3)]
            if e[0] not in split:
                faces.append(c)
                continue
            m = mid[e[0]]
            for half, side in (((c[0], m, c[2]), e[2]), ((m, c[1], c[2]), e[1])):
                if side in split:               # bisect this half again at its other split edge
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


def along_walls(v, f, attrs, ln, bridge, hidden):
    """Refine the carved triangles near the overbridge's walls (earthworks.bridge_walls) to FINE (bisect_near), then
    carve the vertices there again (the ground near the walls does not depend on the height it is carved from) and
    recompute their normals."""
    near = lambda p: E.bridge_walls(p[:, 0], p[:, 1], bridge) & ~np.asarray(hidden(p[:, 0], p[:, 1]), bool)  # noqa
    first = len(v)
    v, f, attrs = bisect_near(v, f, attrs, near)
    redo = near(v)
    z0 = v[:, 2].copy()
    v[redo, 2] = E.carve(v[redo, 0], v[redo, 1], v[redo, 2], ln)
    moved = redo | (np.arange(len(v)) >= first)
    if 'normals' in attrs:
        attrs['normals'] = E._normals(v, f, attrs['normals'], moved | (np.abs(v[:, 2] - z0) > 1e-3))
    return v, f, attrs


def along_forecourt(v, f, attrs, ln):
    """Refine the carved triangles along the forecourt's front and side edges to FINE (bisect_near), so the ground
    steps within station_site.FORECOURT_HOLD of the paving rather than across it, and carve their new vertices from
    the natural ground. New vertices on the tile's border stay on its edges (the next tile keeps those straight).
    (v, f, attrs, refined)"""
    site = ln.station()
    a0, a1, u0, u1 = SS.FORECOURT

    def near(p):
        a, u = site.local(p[:, 0], p[:, 1])
        out = SS.rect_excess(a, u, (a0 - 50., a1, u0, u1))
        depth = np.minimum(np.minimum(a1 - a, u - u0), u1 - u)
        return (a >= a0 - 1.) & (out <= SS.FORECOURT_HOLD + 2.) & (depth <= 1.5)
    if not near(v[f].mean(1)).any():
        return v, f, attrs, False
    first = len(v)
    v, f, attrs = bisect_near(v, f, attrs, near)
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), 1)
    uniq, count = np.unique(edges, axis=0, return_counts=True)
    border = np.zeros(len(v), bool)
    border[uniq[count == 1].ravel()] = True
    redo = (np.arange(len(v)) >= first) & ~border
    v[redo, 2] = E.carve(v[redo, 0], v[redo, 1], attrs['natural'][redo, 0], ln)
    if 'normals' in attrs:
        attrs['normals'] = E._normals(v, f, attrs['normals'], np.arange(len(v)) >= first)
    return v, f, attrs, len(v) > first


def carved_zone(ln, rows):
    """hidden(x, y) for earthworks.refine: everything but the final cutting and the station's ground."""
    start = E.valley_carve_start(ln, rows)
    site = ln.station()

    def hidden(x, y):
        x, y = np.asarray(x, float), np.asarray(y, float)
        s, _, _ = ln.project(x.ravel(), y.ravel())
        keep = np.nan_to_num(s, nan=-1.).reshape(x.shape) >= start
        keep |= SS.inside(site, x, y, margin=E.STATION_REACH)
        return ~keep
    return hidden, start


def library(manifest):
    """Record the carved tiles and their natural copies in the asset library contract."""
    contract = json.loads(LIBRARY.read_text())
    for entry in manifest['meshes']:
        if entry.get('railway_carved'):
            for path in (yori.ASSETS / 'belmonte' / entry['path'], NATURAL / f"{entry['name']}.glb"):
                raw = path.read_bytes()
                contract['files'][path.relative_to(yori.ASSETS).as_posix()] = dict(
                    bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    LIBRARY.write_text(json.dumps(contract, indent=2) + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true', help='carve again tiles already carved for this line')
    args = ap.parse_args(argv)
    ln = E.line()
    if ln is None:
        sys.exit('no committed line (assets/vehicles/belmonte-train/line.json)')
    if ln.station() is None:
        sys.exit('the committed line does not end at the Belmonte station site (train/station_site.py)')
    digest = hashlib.sha256(C.LINE.read_bytes() + Path(SS.__file__).read_bytes() +
                            json.dumps(SALON_PATH).encode()).hexdigest()[:16]
    manifest_path = yori.ASSETS / 'belmonte' / 'source.json'
    manifest = json.loads(manifest_path.read_text())
    origin = np.asarray(BM.ORIGIN, float)
    hidden, start = carved_zone(ln, json.loads(C.LINE.read_text())['samples'])
    print(f'carving from chainage {start:.0f} to the end ({ln.length:.0f}) and the station', flush=True)
    changed = 0
    for entry in manifest['meshes']:
        if not entry['name'].startswith('SM_BM_BT_Terrain_'):
            continue
        path = yori.ASSETS / 'belmonte' / entry['path']
        carved = entry.get('railway_carved')
        if carved == digest and not args.force:
            continue
        natural = NATURAL / f"{entry['name']}.glb"
        doc, t = read(natural if natural.is_file() else path)
        world = t['position'] @ source.FRAME.T + origin
        normals = t['normal'] @ source.FRAME.T
        attrs = dict(normals=normals, uv=t['uv'], colour=t['colour'], natural=world[:, 2:3])
        v, f, a, report = E.refine(world, t['faces'], STEP, attrs, ln, hidden=hidden, conform_neighbors=True)
        bridge = ln.bridge()
        if bridge is not None and report.get('refined'):    # finer along the overbridge's walls, where the ground steps
            v, f, a = along_walls(v, f, a, ln, bridge, hidden)
            report.update(triangles_out=int(len(f)))
        if report.get('refined'):           # finer along the forecourt's edges, where the ground steps
            v, f, a, _ = along_forecourt(v, f, a, ln)
            report.update(triangles_out=int(len(f)))
        moved = report.get('moved', 0)
        if report.get('refined') and moved:
            a['colour'] = repaint(a['colour'], v[:, 0], v[:, 1], v[:, 2], a['natural'][:, 0], ln)
        else:
            v, f, a, moved = world, t['faces'], attrs, 0
        v, f, a, paved = salon_path(v, f, a)
        if paved:
            report['triangles_out'] = len(f)
            report.setdefault('triangles_in', len(t['faces']))
        if not moved and not paved:
            if carved:              # carved for a line that no longer reaches it: back to its natural ground
                print(f"{entry['name']}: restored", flush=True)
                changed += 1
                if not args.dry_run:
                    path.write_bytes(natural.read_bytes())
                    entry.update(sha256=source.sha(path), triangles=int(len(t['faces'])))
                    local = t['position'] @ source.FRAME.T
                    entry['bounds_m'] = [[float(c) for c in local.min(0)], [float(c) for c in local.max(0)]]
                    del entry['railway_carved']
            continue
        z0 = a['natural'][:, 0]
        colour = a['colour']
        print(f"{entry['name']}: {report['triangles_in']} -> {report['triangles_out']} triangles, "
              f"{moved} vertices moved, "
              f"cut {float(np.max(z0 - v[:, 2])):.1f} m, fill {float(np.max(v[:, 2] - z0)):.1f} m"
              f"{', Salon path' if paved else ''}", flush=True)
        changed += 1
        if args.dry_run:
            continue
        if not natural.is_file():
            NATURAL.mkdir(exist_ok=True)
            natural.write_bytes(path.read_bytes())
        write(path, doc, (v - origin) @ source.FRAME, a['normals'] @ source.FRAME, a['uv'], colour, f)
        entry['sha256'] = source.sha(path)
        entry['triangles'] = int(len(f))
        lo, hi = (v - origin).min(0), (v - origin).max(0)
        entry['bounds_m'] = [[float(c) for c in lo], [float(c) for c in hi]]
        entry['railway_carved'] = digest
    if changed and not args.dry_run:
        manifest_path.write_text(json.dumps(manifest, separators=(',', ':')) + '\n')
        library(manifest)
    print(f'BELMONTE STATION TERRAIN carved={changed} line={digest}{" (dry run)" if args.dry_run else ""}')


if __name__ == '__main__':
    main()
