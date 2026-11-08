"""Where the Mega Park sits in the island, and which of the bundled source it keeps.

Pure NumPy (no Blender, no Unreal): the terrain, the forest, the map and the park build all read the park from here.

The park is moved as one rigid body. Native points (x, y up, z) become Blender-frame metres b = (x, -z, y), are
turned by YAW about the park centre and moved to CENTRE; the lowest kept collision point lands at BASE. The riding
collision and the grind paths are therefore the original ones, only placed.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).resolve().parents[3] / 'assets' / 'megapark'

# Western foothills, about a kilometre north of the forest lake (docs/MEGAPARK.md, "Placement").
CENTRE = (-150.0, 1300.0)   # Blender metres, x east, y north
YAW = -60.0                 # degrees, counter-clockwise from above: the roll-in faces uphill, toward the volcano
BASE = 49.3                 # metres above sea level for the lowest kept collision point
# The seam (docs/MEGAPARK.md, "Seam"): where the park meets the air station's footbridge, the gate's rock ended in a
# drop to the pit that the left-out hills had covered. The park keeps that piece of them: the earth hillside between
# the rock and the old road, the wall that held it above the road, and the riding collision on them.
SEAM = {'0xC888FCF815E09C53': (15, 35, 36)}     # asset -> render parts
SEAM_SECTION = '715219D1D6FFC624_0'             # the collision section they belong to
SEAM_TOLERANCE = .25        # metres: a collision triangle is the seam's when its corners and middle lie this close to it
# Where the hillside stops in the air, a skirt of its own earth (or the wall's concrete) hangs SKIRT_DROP metres under
# the edge, past the ground everywhere it meets. An edge is joined, and gets none, when it lies within JOINED metres of
# the park or of another seam triangle, or when its face drops from it steeper than STEEP (a wall's top).
SKIRT_DROP = 45.0
JOINED = .05
STEEP = 2.0                 # metres down per metre out


def is_park_model(model):
    """The authored park: resources whose parts use the park's own _MP materials (32 of the 50)."""
    return any('_MP' in part['name'] for part in model['meshes'])


@lru_cache(maxsize=1)
def source():
    return json.loads((SOURCE / 'map.json').read_text())


def _union(boxes):
    lo = np.min([b['minimum'] for b in boxes], axis=0); hi = np.max([b['maximum'] for b in boxes], axis=0)
    return lo, hi


@lru_cache(maxsize=1)
def kept():
    """(render models, collision sections) of the park itself. Campus, roads and outer hills are left out.

    A collision section is kept when it lies within the bounds of the park models of its own stream tile, so a tile
    shared with a campus piece keeps only the park's sections."""
    src = source()
    models = [m for m in src['models'] if is_park_model(m)]
    by_tile = {}
    for m in models:
        by_tile.setdefault(m['stream_file'].replace('cPres', ''), []).append(m['bounds'])
    collision = []
    for c in src['collision']:
        boxes = by_tile.get(c['stream_file'].replace('cSim', ''))
        if not boxes:
            continue
        lo, hi = _union(boxes)
        if np.all(np.asarray(c['bounds']['minimum']) >= lo - 1) and np.all(np.asarray(c['bounds']['maximum']) <= hi + 1):
            collision.append(c)
    return models, collision


@lru_cache(maxsize=1)
def collision_triangles():
    """All kept collision triangles in the source's Blender frame (unplaced), float64, shape (n, 3, 3)."""
    _, sections = kept()
    tris = [np.load(SOURCE / c['npz'])['triangles'].astype('f8') for c in sections]
    t = np.concatenate(tris)
    return np.stack([t[..., 0], -t[..., 2], t[..., 1]], -1)


@lru_cache(maxsize=1)
def seam_render():
    """The seam's render triangles, native (x, y up, z) metres, float64 (n, 3, 3)."""
    out = []
    for m in source()['models']:
        if m['asset_id'] in SEAM:
            with np.load(SOURCE / m['npz']) as a:
                out += [a[f'vertices_{i}'][a[f'faces_{i}']].astype('f8') for i in SEAM[m['asset_id']]]
    return np.concatenate(out)


def _distance_to_triangles(points, triangles):
    """Metres from each point (n, 3) to the nearest of the triangles (m, 3, 3)."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac = b - a, c - a
    normal = np.cross(ab, ac); nn = (normal * normal).sum(-1)
    out = np.empty(len(points))
    for s in range(0, len(points), 256):
        q = points[s:s + 256, None, :]
        ap = q - a
        # Barycentric coordinates of the projection, clamped to the triangle.
        v = (np.cross(ap, ac) * normal).sum(-1) / nn; w = (np.cross(ab, ap) * normal).sum(-1) / nn
        v = np.clip(v, 0, 1); w = np.clip(w, 0, 1); over = np.maximum(v + w, 1); v /= over; w /= over
        nearest = a + v[..., None] * ab + w[..., None] * ac
        best = np.linalg.norm(q - nearest, axis=-1).min(1)
        # Clamping can miss the nearest edge point; the edges themselves bound it from above.
        for p0, p1 in ((a, b), (b, c), (c, a)):
            d = p1 - p0; t = np.clip(((q - p0) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-12), 0, 1)
            best = np.minimum(best, np.linalg.norm(q - (p0 + t[..., None] * d), axis=-1).min(1))
        out[s:s + 256] = best
    return out


@lru_cache(maxsize=1)
def seam_mask():
    """Which triangles of SEAM_SECTION carry the seam: those whose corners and middle lie on its render surface."""
    section = next(c for c in source()['collision'] if c['id'] == SEAM_SECTION)
    t = np.load(SOURCE / section['npz'])['triangles'].astype('f8')
    render = seam_render()
    lo = render.reshape(-1, 3).min(0) - SEAM_TOLERANCE; hi = render.reshape(-1, 3).max(0) + SEAM_TOLERANCE
    mask = np.all(t.min(1) >= lo, 1) & np.all(t.max(1) <= hi, 1)
    near = t[mask]
    points = np.concatenate([near, near.mean(1, keepdims=True)], 1)
    mask[mask] = (_distance_to_triangles(points.reshape(-1, 3), render).reshape(-1, 4) < SEAM_TOLERANCE).all(1)
    return mask


@lru_cache(maxsize=1)
def seam_triangles():
    """The seam's collision triangles in the source's Blender frame (unplaced), float64 (n, 3, 3)."""
    section = next(c for c in source()['collision'] if c['id'] == SEAM_SECTION)
    t = np.load(SOURCE / section['npz'])['triangles'].astype('f8')[seam_mask()]
    return np.stack([t[..., 0], -t[..., 2], t[..., 1]], -1)


def seam_parts():
    """[(asset, part, vertices, faces)] of the seam, native metres, without zero-area faces (as the park build)."""
    out = []
    for m in source()['models']:
        if m['asset_id'] not in SEAM:
            continue
        with np.load(SOURCE / m['npz']) as a:
            for i in SEAM[m['asset_id']]:
                v = a[f'vertices_{i}'].astype('f8'); f = a[f'faces_{i}']; t = v[f]
                f = f[np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-12]
                out.append((m['asset_id'], i, v, f))
    return out


@lru_cache(maxsize=1)
def seam_skirt():
    """The seam's open edges and the skirt under them: [(asset, part, a, b, outward)] with a, b vertex indices of that
    part and outward the skirt's plan normal (native x, z). The skirt's quad is a, b, b', a' (a' = a - SKIRT_DROP up),
    wound so its front faces outward like the seam's own faces."""
    parts = seam_parts()
    tris = np.concatenate([v[f] for _, _, v, f in parts])
    lo = tris.reshape(-1, 3).min(0) - 1; hi = tris.reshape(-1, 3).max(0) + 1
    park = []
    for m in kept()[0]:
        with np.load(SOURCE / m['npz']) as a:
            for p in m['meshes']:
                i = p['index']; v = a[f'vertices_{i}']
                if len(v):
                    t = v[a[f'faces_{i}']].astype('f8')
                    park.append(t[np.all(t.max(1) >= lo, 1) & np.all(t.min(1) <= hi, 1)])
    park = np.concatenate(park)
    key = lambda p: tuple(np.round(p / .01).astype(np.int64))
    uses = {}
    for _, _, v, f in parts:
        for face in f:
            for k in range(3):
                e = frozenset((key(v[face[k]]), key(v[face[(k + 1) % 3]])))
                uses[e] = uses.get(e, 0) + 1
    out = []
    first = 0
    for asset, part, v, f in parts:
        for n, face in enumerate(f):
            for k in range(3):
                a, b, o = face[k], face[(k + 1) % 3], face[(k + 2) % 3]
                if uses[frozenset((key(v[a]), key(v[b])))] > 1 or np.hypot(*(v[b] - v[a])[[0, 2]]) < JOINED:
                    continue            # shared, or upright: a skirt under it would have no width
                points = np.stack([v[a], (v[a] + v[b]) / 2, v[b]])
                others = np.delete(tris, first + n, 0)
                if (_distance_to_triangles(points, park) < JOINED).all() or \
                        (_distance_to_triangles(points, others) < JOINED).all():
                    continue
                d = v[b] - v[a]
                e = v[a] + d * np.dot(v[o] - v[a], d) / np.dot(d, d)
                drop = e[1] - v[o][1]; run = np.hypot(*(v[o] - e)[[0, 2]])
                if drop > STEEP * run:
                    continue
                normal = np.cross(v[b] - v[a], v[o] - v[a]); normal /= np.linalg.norm(normal)
                # Out of the face in plan; for a near-vertical face (a wall's foot), the way the face looks.
                out_xz = (e - v[o])[[0, 2]] if abs(normal[1]) > .3 else normal[[0, 2]]
                out_xz = out_xz / np.linalg.norm(out_xz)
                below = v[b] - (0, SKIRT_DROP, 0)
                front = np.cross(v[b] - v[a], below - v[a])[[0, 2]]
                out.append((asset, part, *((a, b) if np.dot(front, out_xz) > 0 else (b, a)), tuple(out_xz.round(6))))
        first += len(f)
    return out


def skirt_triangles():
    """The skirt's triangles, native metres (n, 3, 3): two per open edge."""
    verts = {(asset, part): v for asset, part, v, _ in seam_parts()}
    out = []
    for asset, part, a, b, _ in seam_skirt():
        v = verts[(asset, part)]; drop = np.array([0, SKIRT_DROP, 0])
        out += [[v[a], v[b], v[b] - drop], [v[a], v[b] - drop, v[a] - drop]]
    return np.array(out, 'f8').reshape(-1, 3, 3)


@lru_cache(maxsize=1)
def frame():
    """(centre_x, centre_y, lowest_z) of the kept collision in the source's Blender frame. The seam is left out of it, so
    the park keeps its place."""
    t = collision_triangles()
    lo = t.reshape(-1, 3).min(0); hi = t.reshape(-1, 3).max(0)
    return float((lo[0] + hi[0]) / 2), float((lo[1] + hi[1]) / 2), float(lo[2])


def place(points):
    """Source Blender-frame points (..., 3) -> island Blender metres."""
    p = np.asarray(points, 'f8'); cx, cy, low = frame()
    a = math.radians(YAW); c, s = math.cos(a), math.sin(a)
    x = p[..., 0] - cx; y = p[..., 1] - cy
    return np.stack([CENTRE[0] + x * c - y * s, CENTRE[1] + x * s + y * c, p[..., 2] - low + BASE], -1)


def native_to_island(points):
    """Native (x, y up, z) metres -> island Blender metres."""
    p = np.asarray(points, 'f8')
    return place(np.stack([p[..., 0], -p[..., 2], p[..., 1]], -1))


def unreal_transform():
    """The park actor's Unreal transform (location cm, yaw deg) for children authored at ue(native) = 100*(x, z, y).

    ue(native) is 100 x the source Blender point with y negated. The island point is U' = R(-YAW)(U - C) + T in
    Unreal space, which is an actor at T - R(-YAW) C with yaw -YAW."""
    cx, cy, low = frame()
    yaw = -YAW; a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
    C = np.array([100 * cx, -100 * cy, 100 * low]); T = np.array([100 * CENTRE[0], -100 * CENTRE[1], 100 * BASE])
    RC = np.array([C[0] * c - C[1] * s, C[0] * s + C[1] * c, C[2]])
    return {'location_cm': (T - RC).tolist(), 'yaw_deg': yaw}


def surface_samples(triangles, spacing):
    """Points covering every triangle no farther than about `spacing` apart (barycentric grids)."""
    t = np.asarray(triangles, 'f8')
    if not len(t):
        return np.zeros((0, 3))
    edge = np.linalg.norm(t - np.roll(t, 1, 1), axis=-1).max(1)
    steps = np.maximum(np.ceil(edge / spacing).astype(int), 1)
    out = []
    for n in np.unique(steps):
        tri = t[steps == n]
        i, j = np.array([(i, j) for i in range(n + 1) for j in range(n + 1 - i)]).T / n
        w = np.stack([1 - i - j, i, j], -1)                      # (k, 3)
        out.append(np.einsum('kv,tvc->tkc', w, tri).reshape(-1, 3))
    return np.concatenate(out)


@lru_cache(maxsize=2)
def _raster(cell):
    """(x0, y0, park floor, seam floor, top): the placed collision's lowest height in each grid cell, the park's and the
    seam's apart (inf where they have none), and the highest of either (-inf where neither has any)."""
    park = surface_samples(place(collision_triangles()), cell / 2)
    seam = surface_samples(place(seam_triangles()), cell / 2)
    pts = np.concatenate([park, seam])
    x0, y0 = np.floor(pts[:, :2].min(0) / cell) * cell - cell
    nx, ny = (np.ceil((pts[:, :2].max(0) - (x0, y0)) / cell) + 2).astype(int)

    def cells(p):
        return ((p[:, 1] - y0) / cell).astype(int), ((p[:, 0] - x0) / cell).astype(int)
    top = np.full((ny, nx), -np.inf); np.maximum.at(top, cells(pts), pts[:, 2])
    floors = []
    for p in (park, seam):
        floor = np.full((ny, nx), np.inf); np.minimum.at(floor, cells(p), p[:, 2]); floors.append(floor)
    return float(x0), float(y0), floors[0], floors[1], top


@lru_cache(maxsize=1)
def footprint(cell=5.0):
    """Placed collision, the seam's included, rasterised on a Blender-frame grid: (x0, y0, cell, floor, top, mask).

    floor/top are the lowest/highest collision height in each cell (NaN outside); mask is the covered cells, with
    single-cell gaps closed."""
    x0, y0, park, seam, top = _raster(cell)
    floor = np.minimum(park, seam)
    return x0, y0, cell, np.where(np.isfinite(floor), floor, np.nan), np.where(np.isfinite(top), top, np.nan), \
        _closed(np.isfinite(top))


def _closed(mask):
    """mask with its single-cell gaps closed."""
    grown = mask.copy()
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        grown |= np.roll(mask, (dy, dx), (0, 1))
    shrunk = grown.copy()
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        shrunk &= np.roll(grown, (dy, dx), (0, 1))
    return mask | shrunk


# The island terrain meets the park: under the park it drops just below the park's own ground; around it, the natural
# relief is offset to the park's edge height and eases back over a skirt that widens with the height it has to make up.
# The seam is one sheet of hillside, so away from the park the ground under it follows it closely, up to its edges.
SKIRT_MIN, SKIRT_PER_METRE, SKIRT_MAX = 35.0, 3.0, 220.0
UNDER = 1.0         # metres the terrain stays below the lowest park surface around it
REACH = 20.0        # metres round a terrain point whose lowest park surface it stays under
SEAM_REACH = 10.0   # the same under the seam, one terrain cell (hidamari/mountains.py STEP)


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


@lru_cache(maxsize=4)
def _stamp(natural):
    """Fields on a 5 m grid around the park for `natural(x, y)`: (x0, y0, cell, inside, distance, offset, ground)."""
    fx0, fy0, cell, _, _, mask = footprint()
    _, _, park, seam, _ = _raster(cell)
    pad = int(SKIRT_MAX / cell) + 2
    inside = np.pad(mask, pad)
    # The skirt round the park eases from the park's own rim: the seam's edges either hang their own skirt over lower
    # ground or sink into higher ground, so the terrain past them stays as it was.
    own = np.pad(_closed(np.isfinite(park)), pad)
    floor = np.pad(np.where(np.isfinite(park), park, np.nan), pad, constant_values=np.nan)
    x0, y0 = fx0 - pad * cell, fy0 - pad * cell
    ny, nx = inside.shape
    X, Y = np.meshgrid(x0 + cell * (np.arange(nx) + .5), y0 + cell * (np.arange(ny) + .5))
    q = np.pad(own, 1)
    rim = own & ~(q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:]) & np.isfinite(floor)
    rx, ry, rz = X[rim], Y[rim], floor[rim]
    offset_rim = rz - np.asarray(natural(rx, ry), 'f8')
    distance = np.empty(X.size); offset = np.empty(X.size)
    px, py = X.ravel(), Y.ravel()
    for a in range(0, X.size, 4096):
        d = np.hypot(px[a:a + 4096, None] - rx, py[a:a + 4096, None] - ry)
        near = d.min(1)
        w = np.exp(-((d - near[:, None]) / 15.0) ** 2)
        distance[a:a + 4096] = near
        offset[a:a + 4096] = (w * offset_rim).sum(1) / w.sum(1)
    distance = distance.reshape(X.shape); offset = offset.reshape(X.shape)
    # Lowest park surface within REACH: a 10 m terrain triangle below it stays below every surface it spans. Where the
    # seam alone stands, the lowest surface of either within SEAM_REACH, so the ground follows the hillside up to its
    # edges.

    def lowest(field, reach):
        r = int(round(reach / cell))
        f = np.pad(field, pad + r, constant_values=np.inf)
        out = np.full(X.shape, np.inf)
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                out = np.minimum(out, f[r + dy:r + dy + ny, r + dx:r + dx + nx])
        return out
    seam_only = np.pad(np.isfinite(seam) & ~np.isfinite(park), pad)
    near = np.minimum(lowest(park, SEAM_REACH), lowest(seam, SEAM_REACH))
    ground = np.where(seam_only, near, np.minimum(lowest(park, REACH), near))
    return x0, y0, cell, inside, distance, offset, ground - UNDER


def _sample(field, x0, y0, cell, x, y):
    ny, nx = field.shape
    fx = np.clip((x - x0) / cell - .5, 0, nx - 1.001); fy = np.clip((y - y0) / cell - .5, 0, ny - 1.001)
    i = fx.astype(int); j = fy.astype(int); u = fx - i; v = fy - j
    return (field[j, i] * (1 - u) + field[j, i + 1] * u) * (1 - v) + (field[j + 1, i] * (1 - u) + field[j + 1, i + 1] * u) * v


def terrain(x, y, natural_height, natural):
    """Island terrain height with the park in it. `natural_height` is natural(x, y), the terrain without the park."""
    x, y, z = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'), np.asarray(natural_height, 'f8'))
    x0, y0, cell, inside, distance, offset, ground = _stamp(natural)
    ny, nx = inside.shape
    i = np.floor((x - x0) / cell).astype(int); j = np.floor((y - y0) / cell).astype(int)
    near = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    ic, jc = np.clip(i, 0, nx - 1), np.clip(j, 0, ny - 1)
    under = near & inside[jc, ic]
    d = _sample(distance, x0, y0, cell, x, y); off = _sample(offset, x0, y0, cell, x, y)
    width = np.clip(SKIRT_MIN + SKIRT_PER_METRE * np.abs(off), SKIRT_MIN, SKIRT_MAX)
    blended = z + off * _smooth(1 - d / width) * near
    return np.where(under, ground[jc, ic], blended)


def contains(x, y, margin=0.0):
    """True where (x, y) is on the park (its collision footprint, grown by `margin` metres)."""
    fx0, fy0, cell, _, _, mask = footprint()
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    grow = int(math.ceil(margin / cell))
    m = np.pad(mask, grow)
    for _ in range(grow):
        q = np.pad(m, 1); m = m | q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]
    i = np.floor((x - fx0) / cell).astype(int) + grow; j = np.floor((y - fy0) / cell).astype(int) + grow
    ok = (i >= 0) & (i < m.shape[1]) & (j >= 0) & (j < m.shape[0])
    return ok & m[np.clip(j, 0, m.shape[0] - 1), np.clip(i, 0, m.shape[1] - 1)]


def to_unreal(native):
    """Native (x, y up, z) metres -> island Unreal cm, through the park actor's transform (a check on unreal_transform)."""
    u = 100 * np.asarray(native, 'f8')[..., [0, 2, 1]]
    t = unreal_transform(); a = math.radians(t['yaw_deg']); c, s = math.cos(a), math.sin(a)
    return np.stack([u[..., 0] * c - u[..., 1] * s, u[..., 0] * s + u[..., 1] * c, u[..., 2]], -1) + t['location_cm']


def summary():
    models, collision = kept()
    t = place(collision_triangles())
    return {'centre': CENTRE, 'yaw': YAW, 'base': BASE, 'models': len(models), 'collision_sections': len(collision),
            'collision_triangles': int(len(t)), 'seam_triangles': int(len(seam_triangles())), 'bounds_min': t.reshape(-1, 3).min(0).round(2).tolist(),
            'bounds_max': t.reshape(-1, 3).max(0).round(2).tolist(), 'unreal': unreal_transform()}


if __name__ == '__main__':
    print(json.dumps(summary(), indent=1))
