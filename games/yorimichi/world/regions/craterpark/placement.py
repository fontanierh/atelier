"""Where Crater Park sits on the volcano's caldera floor (docs/CRATERPARK.md, "Placement").

Pure NumPy (no Blender, no Unreal): the terrain, the forest, the map and the park build all read the park from here.

The park is moved as one rigid body. Native points (x, y up, z) become Blender-frame metres b = (x, -z, y), are
turned by HEADING about the park block's centre and moved to the caldera's centre, and raised by LIFT. The park
stands on its own block of hillside (the `mountain` mesh): the caldera ground rises to meet the block's top edge and
buries its sides.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np

SOURCE = Path(__file__).resolve().parents[3] / 'assets' / 'craterpark'

CENTRE = (850.0, 2400.0)    # Blender metres: the caldera's centre (hidamari/mountains.py VOLCANO)
HEADING = 185.0             # degrees, counter-clockwise from above: the block's high west side faces the tallest crest
LIFT = 518.0                # metres added to the native height: the block's low east edge meets the 485 m caldera floor
GROUND = 'mountain'         # the closed block of hillside the park stands on


@lru_cache(maxsize=1)
def scene():
    return json.loads((SOURCE / 'scene.json').read_text())


def meshes(role=None, helper=False):
    """The scene's mesh entries, by role; helpers (auxiliary duplicates of the riding surfaces) are left out."""
    return [m for m in scene()['meshes'] if (role is None or m['role'] == role) and m['helper'] == helper]


def arrays(entry):
    with np.load(SOURCE / entry['npz'], allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def frame():
    """(centre_x, centre_y) of the block in the source's Blender frame."""
    lo, hi = np.asarray(scene()['bounds'], 'f8')
    return float((lo[0] + hi[0]) / 2), float(-(lo[2] + hi[2]) / 2)


def place(points):
    """Source Blender-frame points (..., 3) -> island Blender metres."""
    p = np.asarray(points, 'f8'); cx, cy = frame()
    a = math.radians(HEADING); c, s = math.cos(a), math.sin(a)
    x = p[..., 0] - cx; y = p[..., 1] - cy
    return np.stack([CENTRE[0] + x * c - y * s, CENTRE[1] + x * s + y * c, p[..., 2] + LIFT], -1)


def native_to_island(points):
    """Native (x, y up, z) metres -> island Blender metres."""
    p = np.asarray(points, 'f8')
    return place(np.stack([p[..., 0], -p[..., 2], p[..., 1]], -1))


def unreal_transform():
    """The park actor's Unreal transform (location cm, yaw deg) for children authored at ue(native) = 100*(x, z, y).

    As megapark/placement.py: ue(native) is 100 x the source Blender point with y negated, so the island point is
    U' = R(-HEADING)(U - C) + T, an actor at T - R(-HEADING) C with yaw -HEADING."""
    cx, cy = frame()
    yaw = -HEADING; a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
    C = np.array([100 * cx, -100 * cy, 0.]); T = np.array([100 * CENTRE[0], -100 * CENTRE[1], 100 * LIFT])
    RC = np.array([C[0] * c - C[1] * s, C[0] * s + C[1] * c, C[2]])
    return {'location_cm': (T - RC).tolist(), 'yaw_deg': yaw}


def to_unreal(native):
    """Native (x, y up, z) metres -> island Unreal cm, through the park actor's transform."""
    u = 100 * np.asarray(native, 'f8')[..., [0, 2, 1]]
    t = unreal_transform(); a = math.radians(t['yaw_deg']); c, s = math.cos(a), math.sin(a)
    return np.stack([u[..., 0] * c - u[..., 1] * s, u[..., 0] * s + u[..., 1] * c, u[..., 2]], -1) + t['location_cm']


def drop_in():
    """The park's marked ramp drop-in: (ground point, camera point) in island Blender metres."""
    marker = json.loads((SOURCE / 'drop-in.json').read_text())
    return native_to_island(marker['groundPosition']), native_to_island(marker['cameraPosition'])


@lru_cache(maxsize=1)
def ground_triangles():
    """The block's triangles, placed in the island, float64 (n, 3, 3)."""
    out = []
    for entry in meshes(GROUND):
        a = arrays(entry)
        p = a['positions'].astype('f8')[a['triangles']]
        out.append(place(np.stack([p[..., 0], -p[..., 2], p[..., 1]], -1)))
    return np.concatenate(out)


@lru_cache(maxsize=2)
def footprint(cell=5.0):
    """The block's top on a Blender-frame grid: (x0, y0, cell, top, mask). top is its highest point in each cell (NaN
    outside); mask is the covered cells."""
    from megapark.placement import surface_samples
    pts = surface_samples(ground_triangles(), cell / 2)
    x0, y0 = np.floor(pts[:, :2].min(0) / cell) * cell - cell
    nx, ny = (np.ceil((pts[:, :2].max(0) - (x0, y0)) / cell) + 2).astype(int)
    top = np.full((ny, nx), -np.inf)
    np.maximum.at(top, (((pts[:, 1] - y0) / cell).astype(int), ((pts[:, 0] - x0) / cell).astype(int)), pts[:, 2])
    mask = np.isfinite(top)
    return float(x0), float(y0), cell, np.where(mask, top, np.nan), mask


# The caldera meets the block: under it the ground drops below the block's top, out of sight inside the block; round it,
# the natural floor is offset to the block's edge and eases back over a skirt that widens with the height it makes up.
SKIRT_MIN, SKIRT_PER_METRE, SKIRT_MAX = 30.0, 2.5, 120.0
SINK = 2.0      # metres the ground stays below the block's lowest top within REACH
REACH = 15.0    # one and a half terrain cells (hidamari/mountains.py STEP), so no terrain triangle pokes through
EDGE = .3       # metres the ground stays below the block's top edge, out of the way of its own faces


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


@lru_cache(maxsize=4)
def _stamp(natural):
    """Fields on a grid round the block for `natural(x, y)`: (x0, y0, cell, inside, distance, offset, ground)."""
    fx0, fy0, cell, top, mask = footprint()
    pad = int(SKIRT_MAX / cell) + 2
    inside = np.pad(mask, pad)
    top = np.pad(top, pad, constant_values=np.nan)
    x0, y0 = fx0 - pad * cell, fy0 - pad * cell
    ny, nx = inside.shape
    X, Y = np.meshgrid(x0 + cell * (np.arange(nx) + .5), y0 + cell * (np.arange(ny) + .5))
    q = np.pad(inside, 1)
    rim = inside & ~(q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:])
    rx, ry, rz = X[rim], Y[rim], top[rim] - EDGE
    offset_rim = rz - np.asarray(natural(rx, ry), 'f8')
    distance = np.empty(X.size); offset = np.empty(X.size)
    px, py = X.ravel(), Y.ravel()
    for a in range(0, X.size, 4096):
        d = np.hypot(px[a:a + 4096, None] - rx, py[a:a + 4096, None] - ry)
        near = d.min(1)
        w = np.exp(-((d - near[:, None]) / 12.0) ** 2)
        distance[a:a + 4096] = near
        offset[a:a + 4096] = (w * offset_rim).sum(1) / w.sum(1)
    r = int(round(REACH / cell))
    f = np.pad(np.where(inside, top, np.inf), r, constant_values=np.inf)
    lowest = np.full(X.shape, np.inf)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            lowest = np.minimum(lowest, f[r + dy:r + dy + ny, r + dx:r + dx + nx])
    return x0, y0, cell, inside, distance.reshape(X.shape), offset.reshape(X.shape), lowest - SINK


def _sample(field, x0, y0, cell, x, y):
    ny, nx = field.shape
    fx = np.clip((x - x0) / cell - .5, 0, nx - 1.001); fy = np.clip((y - y0) / cell - .5, 0, ny - 1.001)
    i = fx.astype(int); j = fy.astype(int); u = fx - i; v = fy - j
    return (field[j, i] * (1 - u) + field[j, i + 1] * u) * (1 - v) + (field[j + 1, i] * (1 - u) + field[j + 1, i + 1] * u) * v


def terrain(x, y, natural_height, natural):
    """Ground height with the park in it. `natural_height` is natural(x, y), the ground without the park."""
    x, y, z = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'), np.asarray(natural_height, 'f8'))
    x0, y0, cell, inside, distance, offset, ground = _stamp(natural)
    ny, nx = inside.shape
    i = np.floor((x - x0) / cell).astype(int); j = np.floor((y - y0) / cell).astype(int)
    near = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    if not near.any():
        return z
    ic, jc = np.clip(i, 0, nx - 1), np.clip(j, 0, ny - 1)
    under = near & inside[jc, ic]
    d = _sample(distance, x0, y0, cell, x, y); off = _sample(offset, x0, y0, cell, x, y)
    width = np.clip(SKIRT_MIN + SKIRT_PER_METRE * np.abs(off), SKIRT_MIN, SKIRT_MAX)
    blended = z + off * _smooth(1 - d / width) * near
    return np.where(under, ground[jc, ic], blended)


def contains(x, y, margin=0.0):
    """True where (x, y) is on the park's block (grown by `margin` metres)."""
    fx0, fy0, cell, _, mask = footprint()
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    grow = int(math.ceil(margin / cell))
    m = np.pad(mask, grow)
    for _ in range(grow):
        q = np.pad(m, 1); m = m | q[:-2, 1:-1] | q[2:, 1:-1] | q[1:-1, :-2] | q[1:-1, 2:]
    i = np.floor((x - fx0) / cell).astype(int) + grow; j = np.floor((y - fy0) / cell).astype(int) + grow
    ok = (i >= 0) & (i < m.shape[1]) & (j >= 0) & (j < m.shape[0])
    return ok & m[np.clip(j, 0, m.shape[0] - 1), np.clip(i, 0, m.shape[1] - 1)]


def summary():
    t = ground_triangles().reshape(-1, 3)
    ground, _ = drop_in()
    return {'centre': CENTRE, 'heading': HEADING, 'lift': LIFT, 'meshes': len(meshes()), 'helpers': len(meshes(helper=True)),
            'bounds_min': t.min(0).round(2).tolist(), 'bounds_max': t.max(0).round(2).tolist(),
            'drop_in': ground.round(2).tolist(), 'unreal': unreal_transform()}


if __name__ == '__main__':
    print(json.dumps(summary(), indent=1))
