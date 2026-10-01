"""The forest round the Mega Park: the island's detailed autumn trees where the skater gets close (docs/MEGAPARK.md).

Pure NumPy. The north forest is opaque low-poly crowns (HD_NorthTree*), made to be seen from afar. Round the park they
become the island's detailed leaf-card trees: all of them within NEAR metres of the riding footprint, which takes in
the hills the park is seen from, fewer and fewer out to FAR. New detailed trees fill in thickest at the park's edge,
thinning to the forest's own density by FILL_END, with a few glades. Unreal treats the detailed trees inside
near_box() as near ones, with shadows, collision and the camera fade (JapanWorld.cpp, city.json near_trees).
"""
import math

import numpy as np

from megapark import placement

NEAR, FAR = 220., 320.          # metres from the riding footprint
CLEAR = 5.                      # kept free round the footprint, where the park's own plants stand
TAPER, FILL_END = 25., 70.      # the fill thins from TAPER to FILL_END
# Low-poly crown -> detailed species. The detailed meshes are smaller, so their scale grows to keep the forest's height.
DETAILED = {
    'HD_NorthTreeGold': (('Tree_Ginkgo', .55), ('Tree_Maple_B', .25), ('Tree_Broad_B', .2)),
    'HD_NorthTreeRust': (('Tree_Maple_A', .5), ('Tree_Maple_B', .25), ('Tree_Broad_A', .15), ('Tree_Broad_C', .1)),
    'HD_NorthTreePine': (('Tree_Pine_B', .45), ('Tree_Cedar_B', .35), ('Tree_Pine_A', .2)),
}
CROWN = 10.                     # metres, a low-poly crown's top at scale 1 (hidamari/mountains.py forest_tree)
HEIGHT = {'Tree_Maple_A': 6.5, 'Tree_Maple_B': 5.2, 'Tree_Ginkgo': 9.0, 'Tree_Broad_A': 8.5, 'Tree_Broad_B': 7.0,
          'Tree_Broad_C': 10., 'Tree_Pine_A': 13., 'Tree_Pine_B': 11., 'Tree_Cedar_B': 13.}
SCALE = (.85, 1.6)
FILL = dict(spacing=5.4, gap=4.0, scale=(1.0, 1.5),
            mix=(('Tree_Maple_A', .27), ('Tree_Maple_B', .18), ('Tree_Ginkgo', .22), ('Tree_Broad_A', .08),
                 ('Tree_Broad_C', .05), ('Tree_Cedar_B', .1), ('Tree_Pine_B', .1)))
SEED = 1300


def distance(x, y):
    """Metres from the park's riding footprint, 0 on it."""
    fx0, fy0, cell, _, _, mask = placement.footprint()
    q = np.pad(mask, 1)
    inner = q[:-2, 1:-1] & q[2:, 1:-1] & q[1:-1, :-2] & q[1:-1, 2:]
    j, i = np.nonzero(mask & ~inner)
    edge = np.stack([fx0 + (i + .5) * cell, fy0 + (j + .5) * cell], 1)
    x, y = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(y, 'f8'))
    p = np.stack([x.ravel(), y.ravel()], 1)
    d = np.empty(len(p))
    for k in range(0, len(p), 2048):
        d[k:k + 2048] = np.hypot(*(p[k:k + 2048, None] - edge[None]).transpose(2, 0, 1)).min(1)
    d = np.maximum(d - cell / 2, 0.)
    d[placement.contains(p[:, 0], p[:, 1])] = 0.
    return d.reshape(x.shape)


def near_box():
    """[x0, y0, x1, y1] in island metres: the footprint's bounds grown by FAR, where trees are near ones."""
    fx0, fy0, cell, _, _, mask = placement.footprint()
    j, i = np.nonzero(mask)
    return [round(float(fx0 + i.min() * cell - FAR), 1), round(float(fy0 + j.min() * cell - FAR), 1),
            round(float(fx0 + (i.max() + 1) * cell + FAR), 1), round(float(fy0 + (j.max() + 1) * cell + FAR), 1)]


def _smooth(t):
    t = np.clip(t, 0., 1.)
    return t * t * (3 - 2 * t)


def grow(instances, height, trail_distance):
    """Turn the low-poly crowns round the park into detailed trees and fill the near band. `instances` maps names to
    [[x, y, z, yaw, scale], ...] in island metres; `height(x, y)` is the ground and `trail_distance(x, y)` the
    distance to the north trail. Returns {name: count} of the trees added or turned."""
    rng = np.random.default_rng(SEED)
    x0, y0, x1, y1 = near_box()
    done = {}
    for low, kinds in DETAILED.items():
        if low not in instances:
            continue
        a = np.asarray(instances[low], 'f8').reshape(-1, 5)
        box = (a[:, 0] > x0) & (a[:, 0] < x1) & (a[:, 1] > y0) & (a[:, 1] < y1)
        turn = np.zeros(len(a), bool)
        if box.any():
            d = distance(a[box, 0], a[box, 1])
            turn[box] = rng.random(box.sum()) < 1 - _smooth((d - NEAR) / (FAR - NEAR))
        instances[low] = a[~turn].tolist()
        moved = a[turn]
        pick = rng.choice(len(kinds), size=len(moved), p=[w for _, w in kinds])
        for k, (name, _) in enumerate(kinds):
            rows = moved[pick == k].copy()
            rows[:, 4] = np.clip(rows[:, 4] * CROWN / HEIGHT[name], *SCALE)
            instances.setdefault(name, []).extend(np.round(rows, 3).tolist())
            done[name] = done.get(name, 0) + len(rows)
    # Fill round the park on a jittered grid, clear of every tree already there, with glades where the patch is low.
    have = np.array([q[:2] for name, rows in instances.items() if name.startswith(('Tree', 'HD_NorthTree'))
                     for q in rows if x0 - 8 < q[0] < x1 + 8 and y0 - 8 < q[1] < y1 + 8], 'f8').reshape(-1, 2)
    s = FILL['spacing']
    fx0, fy0, fx1, fy1 = x0 + FAR - FILL_END, y0 + FAR - FILL_END, x1 - FAR + FILL_END, y1 - FAR + FILL_END
    gx, gy = np.meshgrid(np.arange(fx0, fx1, s), np.arange(fy0, fy1, s))
    p = np.stack([gx.ravel(), gy.ravel()], 1) + rng.uniform(-.45, .45, (gx.size, 2)) * s
    d = distance(p[:, 0], p[:, 1])
    patch = np.sin(p[:, 0] * .021 + np.sin(p[:, 1] * .017) * 1.7) + .6 * np.cos(p[:, 1] * .026 - p[:, 0] * .009)
    # Densest at the park's edge, thinning to the forest's own density by FILL_END, so no ring shows from afar.
    density = (.62 + .3 * np.tanh(patch)) * (1 - _smooth((d - TAPER) / (FILL_END - TAPER)))
    keep = (d > CLEAR) & (rng.random(len(p)) < density) & (trail_distance(p[:, 0], p[:, 1]) > 7)
    p = p[keep]
    z = np.asarray(height(p[:, 0], p[:, 1]), 'f8')
    p, z = p[z > 2], z[z > 2]
    names, weights = zip(*FILL['mix'])
    cell = {}
    for q in have:
        cell.setdefault((math.floor(q[0] / 8), math.floor(q[1] / 8)), []).append(q)
    for q, ground in zip(p, z):
        bx, by = math.floor(q[0] / 8), math.floor(q[1] / 8)
        if any(math.hypot(*(q - o)) < FILL['gap'] for dx in (-1, 0, 1) for dy in (-1, 0, 1) for o in cell.get((bx + dx, by + dy), ())):
            continue
        name = names[rng.choice(len(names), p=weights)]
        instances.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]), 3), round(float(ground) - .3, 3),
                                               round(float(rng.uniform(0, 360)), 1), round(float(rng.uniform(*FILL['scale'])), 3)])
        cell.setdefault((bx, by), []).append(q)
        done[name] = done.get(name, 0) + 1
    return done
