"""Crater Park v2 against the caldera's dressing, and its own planting (docs/CRATERPARK.md, "Dressing"). Pure numpy.

The island's dressing (hidamari/layout.py, city.json) never stands on the r4 block: every instance on it or near it is
dropped (`craterpark.contains(margin=3)`: the block's 5 m cell mask grown by one cell), and the caldera's own groves,
boulders, scree and shrubs keep 7-16 m off it. In the r5 build the nearest instance is 5.5 m from the mask, and 17 m
or more from the tower and the lines' edges. `check` holds v2 to that rule. Every drawn face lies on the mask. Every
riding, side, coping and rail face lies at least RING metres inside the grown mask, the area no dressing instance may
enter. So nothing pokes through a ramp or floats over one, whatever the hidamari dressing does inside its own rules.
hidamari/layout.py is not edited: no world.hidamari rerun, and so no unreal.world rerun.

`plant` dresses the park's own ground, as layout.md 5 asks (planted ground between the lines): clumps of autumn and
ochre bushes on its upward ground faces, set on those faces, CLEAR m plus their reach from every riding, side, coping
and rail face and out of every air's flight corridor. They go into park.json `trees` (park-local Unreal cm, [x, y, z, yaw, scale]), which
ASuperUltraMegaPark::Spawn already plants as collision-free instances, like the Mega Park's. Only the craterpark steps
rerun when they change.
"""
import math

import numpy as np

from . import dsl

SPACING = 1.          # m between samples of a face when testing the footprint
CLEAR = 10.           # m: a bush's reach stays this far (in plan) from any riding, side, coping or rail face
CORRIDOR = 12.        # m: no bush within this of an air's flight line (lip to landing, extended this far each way)
CLUMPS_PER_HA = 50.   # clumps of 3-6 bushes per hectare of open slope, in groves: about 1,100 bushes on the preview park
CLUMP_RADIUS = 3.5    # m
CELL = 1.             # m: the plan grid that marks the park's built faces
FREE_MARGIN = 3.      # hidamari/layout.py drops every city instance within contains(margin=3) of the block
RING = 4.             # m: riding, side, coping and rail faces stay this far inside that dressing-free ground
BUSHES = (('Bush_HD_Autumn', .45, (.8, 1.5), 1.1), ('Bush_Ochre_A', .33, (1.1, 2.), .9), ('Bush_Ochre_B', .22, (1.1, 2.), .9))
"""(mesh, share, scale range, reach m per unit scale): the r4 hillside's mix (hidamari/layout.py)."""


class DressingError(ValueError):
    pass


def samples(triangles, spacing):
    """Points covering every triangle no farther than about `spacing` apart (megapark.placement.surface_samples)."""
    t = np.asarray(triangles, 'f8')
    if not len(t):
        return np.zeros((0, 3))
    edge = np.linalg.norm(t - np.roll(t, 1, 1), axis=-1).max(1)
    steps = np.maximum(np.ceil(edge / spacing).astype(int), 1)
    out = []
    for n in np.unique(steps):
        tri = t[steps == n]
        i, j = np.array([(i, j) for i in range(n + 1) for j in range(n + 1 - i)]).T / n
        w = np.stack([1 - i - j, i, j], -1)
        out.append(np.einsum('kv,tvc->tkc', w, tri).reshape(-1, 3))
    return np.concatenate(out)


def drawn(mesh):
    """(m, 3, 3) every face but the buried base, native metres."""
    return mesh.triangles()[mesh.role != dsl.ROLE[dsl.BASE]]


def check(mesh, placement, spacing=SPACING, ring=None):
    """Every drawn face lies in the selected placement envelope, and every riding, side, coping and rail face
    `ring` m (RING) inside the mask grown by one cell, where the island admits no dressing: {'ok', 'samples',
    'outside', 'near_edge', 'examples' (island x, y)}. Raises DressingError on either."""
    ring = RING if ring is None else ring

    def island(triangles):
        pts = samples(triangles, spacing)
        return placement.native_to_island(pts)[:, :2] if len(pts) else np.zeros((0, 2))
    every = island(drawn(mesh))
    built = np.isin(mesh.role, [dsl.ROLE[r] for r in (dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL)])
    riding = island(mesh.triangles()[built])
    outside = every[~placement.contains(every[:, 0], every[:, 1])] if len(every) else every
    deep = np.ones(len(riding), bool)
    for k in range(16):
        a = 2 * math.pi * k / 16
        q = riding + ring * np.array([math.cos(a), math.sin(a)])
        if len(q):
            deep &= placement.contains(q[:, 0], q[:, 1], margin=FREE_MARGIN)
    edge = riding[~deep]
    report = {'ok': not len(outside) and not len(edge), 'samples': int(len(every)), 'outside': int(len(outside)),
              'near_edge': int(len(edge)), 'examples': np.round(np.concatenate([outside, edge])[:5], 2).tolist()}
    if len(outside):
        raise DressingError(f'{len(outside)} of {len(every)} face samples lie outside the selected park envelope, where the caldera is '
                            f'dressed (island x, y e.g. {report["examples"]}); keep the park on placement.contains')
    if len(edge):
        raise DressingError(f'{len(edge)} riding, side, coping or rail samples lie within {ring:g} m of where the caldera '
                            f'may be dressed, at the selected envelope edge (island x, y e.g. {report["examples"]})')
    return report


def _noise(x, y, scale, seed):
    """Smooth value noise in [0, 1) (hidamari/mountains.py's kind), so bushes clump instead of spreading evenly."""
    q = np.stack([x, y], -1) / scale + seed * .618
    i = np.floor(q); f = q - i; f = f * f * (3 - 2 * f)

    def h(o):
        k = i + o
        return np.modf(np.abs(np.sin(k[..., 0] * 127.1 + k[..., 1] * 311.7 + seed) * 43758.5453))[0]
    a, b, c, d = h(np.array([0, 0])), h(np.array([1, 0])), h(np.array([0, 1])), h(np.array([1, 1]))
    return (a * (1 - f[..., 0]) + b * f[..., 0]) * (1 - f[..., 1]) + (c * (1 - f[..., 0]) + d * f[..., 0]) * f[..., 1]


def _segment_distance(p, a, b):
    """Plan distance from points p (k, 2) to the segment a-b."""
    ab = b - a; L2 = float(ab @ ab)
    u = np.clip(((p - a) @ ab) / L2, 0., 1.) if L2 > 0 else np.zeros(len(p))
    return np.linalg.norm(p - (a + u[:, None] * ab), axis=1)


def corridors(mesh, airs=()):
    """Every air's flight corridor in plan (native x, z): [(a (2,), b (2,))] from the lip to the landing start, from
    the air checks ('lip', 'landing_start'), else from the mesh's tags (each takeoff feature to the nearest landing
    feature ahead of it)."""
    out = []
    for c in airs or ():
        if c.get('kind', 'air') == 'air' and 'lip' in c and 'landing_start' in c:
            out.append((np.asarray(c['lip'], 'f8')[[0, 2]], np.asarray(c['landing_start'], 'f8')[[0, 2]]))
    if out:
        return out
    t = mesh.triangles().mean(1)[:, [0, 2]]
    def centres(tag):
        m = mesh.tag == dsl.TAG[tag]
        return {int(f): t[m & (mesh.feature == f)].mean(0) for f in np.unique(mesh.feature[m])}
    take, land = centres('takeoff'), centres('landing')
    for f, a in take.items():
        if land:
            b = min(land.values(), key=lambda q: float(np.linalg.norm(q - a)))
            out.append((a, b))
    return out


def plant(mesh, airs=(), seed=771, spacing=1.5, clumps=CLUMPS_PER_HA):
    """park.json `trees` for the park's own ground: {mesh name: [[x, y, z cm, yaw, scale], ...]} in park-local Unreal
    cm (ue(native) = 100 (x, z, y)). Clumps of 3-6 bushes (about `clumps` per hectare of open slope, gathered into
    groves by smooth noise), each bush on an upward ground face (normal 0.55-0.97 up), 0.15 m into it, CLEAR m plus its
    reach in plan from every riding, side, coping and rail face, and CORRIDOR m off every air's flight line (`airs`:
    the park's air checks; else the mesh's takeoff and landing tags)."""
    rng = np.random.default_rng(seed)
    t = mesh.triangles()
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    length = np.linalg.norm(n, axis=1)
    up = np.where(length > 0, n[:, 1] / np.maximum(length, 1e-12), 0.)
    ground = (mesh.role == dsl.ROLE[dsl.GROUND]) & (up > .55) & (up < .97)
    built = np.isin(mesh.role, [dsl.ROLE[r] for r in (dsl.RIDING, dsl.SIDE, dsl.COPING, dsl.RAIL)])
    seats = samples(t[ground], spacing)
    if not len(seats):
        return {}
    _, first = np.unique(np.round(seats / (spacing / 2)), axis=0, return_index=True)   # shared corners once
    seats = seats[np.sort(first)]
    # the built faces on a CELL grid, as a summed-area table: a square window count is O(1) per query
    marks = samples(t[built], CELL / 2)
    lo = np.floor(seats[:, [0, 2]].min(0) / CELL) - 40; hi = np.floor(seats[:, [0, 2]].max(0) / CELL) + 41
    shape = (hi - lo + 1).astype(int)
    grid = np.zeros(shape, 'i4')
    if len(marks):
        ij = np.floor(marks[:, [0, 2]] / CELL) - lo
        ok = ((ij >= 0) & (ij < shape)).all(1)
        grid[tuple(ij[ok].astype(int).T)] = 1
    table = np.zeros((shape[0] + 1, shape[1] + 1), 'i8'); table[1:, 1:] = grid.cumsum(0).cumsum(1)

    def clear(x, z, r):
        i, j = int(np.floor(x / CELL) - lo[0]), int(np.floor(z / CELL) - lo[1])
        i0, j0, i1, j1 = max(i - r, 0), max(j - r, 0), min(i + r + 1, shape[0]), min(j + r + 1, shape[1])
        return table[i1, j1] - table[i0, j1] - table[i1, j0] + table[i0, j0] == 0
    lanes = corridors(mesh, airs)
    open_ = np.ones(len(seats), bool)
    for a, b in lanes:
        d = b - a; d = d / max(np.linalg.norm(d), 1e-9)
        open_ &= _segment_distance(seats[:, [0, 2]], a - d * CORRIDOR, b + d * CORRIDOR) > CORRIDOR
    grove = np.clip(((_noise(seats[:, 0], seats[:, 2], 40., 763) + .4 * _noise(seats[:, 0], seats[:, 2], 12., 764)) / 1.4
                     - .45) / .2, 0., 1.)
    area = spacing * spacing / 2                      # m2 of slope per seat, about (barycentric grids)
    centre = open_ & (rng.random(len(seats)) < clumps / 1e4 * area * grove / max(float(grove.mean()), 1e-3))
    names = [b[0] for b in BUSHES]; shares = np.array([b[1] for b in BUSHES]); shares /= shares.sum()
    # seats bucketed by 4 m cells, to gather a clump's members
    bucket = {}
    for k, key in enumerate(map(tuple, np.floor(seats[:, [0, 2]] / 4.).astype(int).tolist())):
        bucket.setdefault(key, []).append(k)
    out, placed = {}, []
    for c in np.flatnonzero(centre):
        cx, _, cz = seats[c]
        i, j = int(np.floor(cx / 4.)), int(np.floor(cz / 4.))
        near = [k for di in (-1, 0, 1) for dj in (-1, 0, 1) for k in bucket.get((i + di, j + dj), ())
                if open_[k] and math.hypot(seats[k, 0] - cx, seats[k, 2] - cz) < CLUMP_RADIUS]
        species = int(rng.choice(len(BUSHES), p=shares))   # a clump is mostly one kind
        for k in rng.permutation(near)[:int(rng.integers(3, 7))]:
            x, y, z = seats[k]
            kind = species if rng.random() < .75 else int(rng.choice(len(BUSHES), p=shares))
            name, _, (s0, s1), reach = BUSHES[kind]
            scale = float(rng.uniform(s0, s1))
            if not clear(x, z, int(math.ceil((CLEAR + reach * scale) / CELL))):
                continue
            if any(abs(x - px) < 1.4 and abs(z - pz) < 1.4 for px, pz in placed[-12:]):
                continue
            placed.append((x, z))
            out.setdefault(names[kind], []).append([round(100 * x, 1), round(100 * z, 1), round(100 * (y - .15), 1),
                                                    round(float(rng.uniform(0, 360)), 1), round(scale, 3)])
    return out


def clearance(instances, placement, near=60.):
    """The island's dressing near the block (city.json `instances`): {mesh: nearest distance in m from the block's
    footprint mask} for every instance within `near` m, for the record (all are 10 m or more)."""
    x0, y0, cell, _, mask = placement.footprint()
    cy, cx = np.nonzero(mask)
    centres = np.stack([x0 + (cx + .5) * cell, y0 + (cy + .5) * cell], -1)
    result = {}
    lo, hi = centres.min(0) - near, centres.max(0) + near
    for name, items in instances.items():
        a = np.asarray(items, 'f8').reshape(-1, 5)[:, :2]
        a = a[((a >= lo) & (a <= hi)).all(1)]
        if not len(a):
            continue
        d = np.full(len(a), np.inf)
        for s in range(0, len(centres), 2048):
            c = centres[s:s + 2048]
            # distance to a cell's square, not its centre
            dx = np.maximum(np.abs(a[:, None, 0] - c[None, :, 0]) - cell / 2, 0)
            dy = np.maximum(np.abs(a[:, None, 1] - c[None, :, 1]) - cell / 2, 0)
            d = np.minimum(d, np.hypot(dx, dy).min(1))
        if (d < near).any():
            result[name] = round(float(d.min()), 2)
    return result
