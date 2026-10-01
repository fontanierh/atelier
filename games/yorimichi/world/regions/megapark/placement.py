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
def frame():
    """(centre_x, centre_y, lowest_z) of the kept collision in the source's Blender frame."""
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
    edge = np.linalg.norm(t - np.roll(t, 1, 1), axis=-1).max(1)
    steps = np.maximum(np.ceil(edge / spacing).astype(int), 1)
    out = []
    for n in np.unique(steps):
        tri = t[steps == n]
        i, j = np.array([(i, j) for i in range(n + 1) for j in range(n + 1 - i)]).T / n
        w = np.stack([1 - i - j, i, j], -1)                      # (k, 3)
        out.append(np.einsum('kv,tvc->tkc', w, tri).reshape(-1, 3))
    return np.concatenate(out)


@lru_cache(maxsize=1)
def footprint(cell=5.0):
    """Placed collision rasterised on a Blender-frame grid: (x0, y0, cell, floor, top, mask).

    floor/top are the lowest/highest collision height in each cell (NaN outside); mask is the covered cells, with
    single-cell gaps closed."""
    pts = surface_samples(place(collision_triangles()), cell / 2)
    x0, y0 = np.floor(pts[:, :2].min(0) / cell) * cell - cell
    nx, ny = (np.ceil((pts[:, :2].max(0) - (x0, y0)) / cell) + 2).astype(int)
    ix = ((pts[:, 0] - x0) / cell).astype(int); iy = ((pts[:, 1] - y0) / cell).astype(int)
    top = np.full((ny, nx), -np.inf); floor = np.full((ny, nx), np.inf)
    np.maximum.at(top, (iy, ix), pts[:, 2]); np.minimum.at(floor, (iy, ix), pts[:, 2])
    mask = np.isfinite(top)
    grown = mask.copy()
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        grown |= np.roll(mask, (dy, dx), (0, 1))
    shrunk = grown.copy()
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        shrunk &= np.roll(grown, (dy, dx), (0, 1))
    mask |= shrunk
    return float(x0), float(y0), cell, np.where(np.isfinite(floor), floor, np.nan), np.where(np.isfinite(top), top, np.nan), mask


# The island terrain meets the park: under the park it drops just below the park's own ground; around it, the natural
# relief is offset to the park's edge height and eases back over a skirt that widens with the height it has to make up.
SKIRT_MIN, SKIRT_PER_METRE, SKIRT_MAX = 35.0, 3.0, 220.0
UNDER = 1.0         # metres the terrain stays below the lowest park surface around it


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


@lru_cache(maxsize=4)
def _stamp(natural):
    """Fields on a 5 m grid around the park for `natural(x, y)`: (x0, y0, cell, inside, distance, offset, ground)."""
    fx0, fy0, cell, floor, _, mask = footprint()
    pad = int(SKIRT_MAX / cell) + 2
    inside = np.pad(mask, pad)
    floor = np.pad(floor, pad, constant_values=np.nan)
    x0, y0 = fx0 - pad * cell, fy0 - pad * cell
    ny, nx = inside.shape
    X, Y = np.meshgrid(x0 + cell * (np.arange(nx) + .5), y0 + cell * (np.arange(ny) + .5))
    q = np.pad(inside, 1)
    rim = inside & ~(q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:]) & np.isfinite(floor)
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
    # Lowest park surface within 20 m: a 10 m terrain triangle below it stays below every surface it spans.
    r = 4
    f = np.pad(np.where(np.isfinite(floor), floor, np.inf), r, constant_values=np.inf)
    ground = np.full(X.shape, np.inf)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ground = np.minimum(ground, f[r + dy:r + dy + ny, r + dx:r + dx + nx])
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
            'collision_triangles': int(len(t)), 'bounds_min': t.reshape(-1, 3).min(0).round(2).tolist(),
            'bounds_max': t.reshape(-1, 3).max(0).round(2).tolist(), 'unreal': unreal_transform()}


if __name__ == '__main__':
    print(json.dumps(summary(), indent=1))
