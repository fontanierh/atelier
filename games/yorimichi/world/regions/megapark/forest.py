"""The forest round the Mega Park: the island's detailed autumn trees where the skater gets close (docs/MEGAPARK.md).

Pure NumPy. The north forest is opaque low-poly crowns (HD_NorthTree*), made to be seen from afar. Round the park they
become the island's detailed leaf-card trees: all of them within NEAR metres of the riding footprint, which takes in
the hills the park is seen from, fewer and fewer out to FAR. New detailed trees fill the band to a closed canopy in
clumps of one family, with a few small glades, and bushes and grass grow between the trunks at the park's edge. Unreal treats the detailed trees inside
near_box() as near ones, with shadows, collision and the camera fade (JapanWorld.cpp, city.json near_trees).
"""
import math

import numpy as np

from hidamari import mountains
from megapark import placement

NEAR, FAR = 220., 320.          # metres from the riding footprint
CLEAR = 5.                      # kept free round the footprint, where the park's own plants stand
# Low-poly crown -> detailed species. The detailed meshes are smaller, so their scale grows to keep the forest's height.
DETAILED = {
    'HD_NorthTreeGold': (('Tree_Ginkgo', .7), ('Tree_Maple_B', .3)),
    'HD_NorthTreeRust': (('Tree_Maple_A', .6), ('Tree_Maple_B', .3), ('Tree_Broad_C', .1)),
    'HD_NorthTreePine': (('Tree_Pine_B', .45), ('Tree_Cedar_B', .35), ('Tree_Pine_A', .2)),
}
CROWN = 10.                     # metres, a low-poly crown's top at scale 1 (hidamari/mountains.py forest_tree)
HEIGHT = {'Tree_Maple_A': 6.5, 'Tree_Maple_B': 5.2, 'Tree_Ginkgo': 9.0, 'Tree_Broad_A': 8.5, 'Tree_Broad_B': 7.0,
          'Tree_Broad_C': 10., 'Tree_Pine_A': 13., 'Tree_Pine_B': 11., 'Tree_Cedar_A': 16., 'Tree_Cedar_B': 13.}
SCALE = (.85, 1.6)
# The fill makes a closed canopy like the paintovers (assets/megapark/concepts/improve-*): crowns touching, in clumps of
# one family, two in five of them dark conifers standing above red maples and yellow ginkgos. The pale-leaved broadleaves
# stay out: they read as washed-out green against the autumn colours.
FILL = dict(spacing=4.7, gap=3.6)
FAMILIES = (                    # (members with weights, scale range); a clump picks one family
    ((('Tree_Pine_B', .35), ('Tree_Cedar_B', .3), ('Tree_Pine_A', .2), ('Tree_Cedar_A', .15)), (.95, 1.55)),
    ((('Tree_Maple_A', .65), ('Tree_Maple_B', .35)), (1.25, 1.85)),
    ((('Tree_Ginkgo', .8), ('Tree_Maple_B', .2)), (1.15, 1.7)),
)
CLUMPS = (-.2, .6)              # clump noise thresholds between the families: about 43, 32 and 25 per cent
MIX = .25                       # share of trees from another family than their clump's
# Beyond the detailed band the island's opaque crowns close the canopy out to OUTER metres, over the north forest's
# thinned slopes and the far hills west of it that the park looks out on, up to the forest line. OUTER takes in the
# plateau on top of the steep face west of the park, the park's skyline from the upper deck. The crowns keep the fill's
# clumps (conifers, maples, ginkgos -> Pine, Rust, Gold) and the island's own crowns in the band take them too, so the
# hills read as patches of one colour rather than confetti. Pines are slimmer than the broadleaf crowns, so they grow
# closer together and taller, standing above the maples and ginkgos as in the paintovers.
OUTER = 1250.
CANOPY = dict(spacing=4.4, gap=4.8, pine_gap=3.4, pine=.8, broadleaf=.5)   # pine, broadleaf: the grid points they take
CROWNS = ('Pine', 'Rust', 'Gold')
CROWN_CLUMPS = (-.5, .45)       # the clump noise's thresholds for the crowns: about 29, 39 and 32 per cent, warmer than
                                # the fill, since the dense, tall pines fill more of a distant view than their share
CROWN_MIX = .15                 # share of crowns from another kind than their clump's
PINE = 1.25                     # a pine crown's scale over a broadleaf one's
# West of the north forest the far hills carry the island's painted-card far forest (gen_world.py), big cards of every
# kind at random with pale broadleaves and cool conifers among them, taller than the crowns. Where the crowns grow they
# replace it, so it no longer stands over the plateau's canopy as a pale skyline.
FAR_FOREST = ('Tree_Maple_lo', 'Tree_Broad_lo', 'Tree_Ginkgo_lo', 'Tree_Cedar_B', 'Tree_Pine_B')
FOREST_LINE = 215.              # metres, wavering by 25 (hidamari/layout.py stops the north forest at 210 +- 30)
FLOOR = 650.                    # metres: the forest floor's colour fades into the island's ground by here
# Undergrowth where the forest meets the park: bushes, and grass tufts closest in.
UNDER = dict(bush=(55., 2.2, .5), grass=(30., 1.6, .55))   # (reach from the footprint, spacing, density)
BUSHES = (('Bush_Green_A', .3), ('Bush_Green_B', .2), ('Bush_Ochre_A', .25), ('Bush_Ochre_B', .15), ('Bush_Flower_A', .1))
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
    """Turn the low-poly crowns round the park into detailed trees, fill the near band and close the canopy beyond it.
    `instances` maps names to [[x, y, z, yaw, scale], ...] in island metres; `height(x, y)` is the rendered ground,
    the far hills' included, and `trail_distance(x, y)` the distance to the north trail. Returns {name: count} of the
    trees added or turned."""
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
    # Fill the band on a jittered grid, clear of every tree already there, in clumps, with a few small glades.
    have = np.array([q[:2] for name, rows in instances.items() if name.startswith(('Tree', 'HD_NorthTree'))
                     for q in rows if x0 - 8 < q[0] < x1 + 8 and y0 - 8 < q[1] < y1 + 8], 'f8').reshape(-1, 2)
    p = _grid(rng, (x0, y0, x1, y1), FILL['spacing'])
    d = distance(p[:, 0], p[:, 1])
    glade = np.sin(p[:, 0] * .043 + np.sin(p[:, 1] * .037) * 2.1) * np.sin(p[:, 1] * .041 + np.sin(p[:, 0] * .029) * 1.7)
    density = .97 * _smooth((glade + .78) / .2) * (1 - _smooth((d - NEAR) / (FAR - NEAR)))
    keep = (d > CLEAR) & (rng.random(len(p)) < density) & (trail_distance(p[:, 0], p[:, 1]) > 7)
    p = p[keep]
    z = np.asarray(height(p[:, 0], p[:, 1]), 'f8')
    p, z = p[z > 2], z[z > 2]
    clump = np.where(rng.random(len(p)) < MIX, rng.integers(0, len(FAMILIES), len(p)), _clump(p[:, 0], p[:, 1]))
    cell = _bins(have, 8)
    for q, ground, family in zip(p, z, clump):
        if _near(cell, q, FILL['gap'], 8):
            continue
        kinds, scale = FAMILIES[family]
        name = kinds[rng.choice(len(kinds), p=[w for _, w in kinds])][0]
        instances.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]), 3), round(float(ground) - .3, 3),
                                               round(float(rng.uniform(0, 360)), 1), round(float(rng.uniform(*scale)), 3)])
        cell.setdefault((math.floor(q[0] / 8), math.floor(q[1] / 8)), []).append(q)
        done[name] = done.get(name, 0) + 1
    _close(instances, height, trail_distance, np.random.default_rng(SEED + 1), done)
    # Undergrowth at the park's edge, between the trunks.
    trunks = _bins(np.array([q[:2] for name, rows in instances.items() if name.startswith('Tree') for q in rows
                             if x0 < q[0] < x1 and y0 < q[1] < y1], 'f8').reshape(-1, 2), 4)
    for kind, (reach, spacing, dense) in UNDER.items():
        box = (x0 + FAR - reach, y0 + FAR - reach, x1 - FAR + reach, y1 - FAR + reach)
        p = _grid(rng, box, spacing)
        d = distance(p[:, 0], p[:, 1])
        patch = .5 + .5 * np.sin(p[:, 0] * .09 + np.sin(p[:, 1] * .07) * 2.) * np.sin(p[:, 1] * .08 + np.sin(p[:, 0] * .05))
        keep = (d > 1.) & (rng.random(len(p)) < dense * (.4 + patch) * (1 - _smooth((d - reach * .6) / (reach * .4))))
        keep &= trail_distance(p[:, 0], p[:, 1]) > 4
        p = p[keep]
        z = np.asarray(height(p[:, 0], p[:, 1]), 'f8')
        p, z = p[z > 2], z[z > 2]
        for q, ground in zip(p, z):
            if _near(trunks, q, 1.1, 4):
                continue
            name = (BUSHES[rng.choice(len(BUSHES), p=[w for _, w in BUSHES])][0] if kind == 'bush'
                    else ('Grass_A', 'Grass_B')[rng.integers(2)])
            size = rng.uniform(.8, 1.5) if kind == 'bush' else rng.uniform(.7, 1.1)
            instances.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]), 3),
                                                   round(float(ground) - (.15 if kind == 'bush' else .08), 3),
                                                   round(float(rng.uniform(0, 360)), 1), round(float(size), 3)])
            done[name] = done.get(name, 0) + 1
    return done


def _clump(x, y, edges=CLUMPS):
    """The clump of each point: 0 conifers, 1 maples, 2 ginkgos (FAMILIES), or with CROWN_CLUMPS Pine, Rust, Gold."""
    return np.digitize(np.sin(x * .031 + np.sin(y * .027) * 1.9) + .7 * np.cos(y * .035 - x * .012), edges)


def _box(reach, south=650.):
    """[x0, y0, x1, y1]: the footprint's bounds grown by `reach`, not south of `south`."""
    fx0, fy0, cell, _, _, mask = placement.footprint()
    j, i = np.nonzero(mask)
    return (fx0 + i.min() * cell - reach, max(fy0 + j.min() * cell - reach, south),
            fx0 + (i.max() + 1) * cell + reach, fy0 + (j.max() + 1) * cell + reach)


def _outer(d):
    """0..1: how much of the canopy the crowns close at `d` metres from the footprint, fading out by OUTER."""
    return 1 - _smooth((d - OUTER + 250) / 250)


def clear_far_forest(world):
    """Drop the far forest's painted cards where the crowns replace them: west of the north forest, inside OUTER.
    `world` is gen_world.py's world.json; the tree house has already planned its canopy on the full forest."""
    rng = np.random.default_rng(SEED + 2)
    x0, y0, x1, y1 = _box(OUTER)
    for name in FAR_FOREST:
        if name not in world['instances']:
            continue
        a = np.asarray(world['instances'][name], 'f8').reshape(-1, 5)
        box = (a[:, 0] > x0) & (a[:, 0] < min(x1, mountains.BOUNDS[0])) & (a[:, 1] > y0) & (a[:, 1] < y1)
        drop = np.zeros(len(a), bool)
        if box.any():
            drop[box] = rng.random(box.sum()) < _outer(distance(a[box, 0], a[box, 1]))
        world['instances'][name] = [q for q, gone in zip(world['instances'][name], drop) if not gone]


def _close(instances, height, trail_distance, rng, done):
    """Opaque crowns in the gaps of the forest from the detailed band out to OUTER, in the fill's clumps: the north
    forest's own kinds inside its bounds, the backdrop kinds on the far hills west of it. The north forest's crowns in
    the band take the clump of where they stand, less and less towards OUTER."""
    box = _box(OUTER)
    fade = lambda d: _smooth((d - NEAR - 30) / 60) * _outer(d)
    kinds = {'HD_NorthTree' + k: [] for k in CROWNS}
    for name in kinds:
        a = np.asarray(instances.get(name, []), 'f8').reshape(-1, 5)
        inside = (a[:, 0] > box[0]) & (a[:, 0] < box[2]) & (a[:, 1] > box[1]) & (a[:, 1] < box[3])
        turn = np.zeros(len(a), bool)
        if inside.any():
            turn[inside] = rng.random(inside.sum()) < (1 - CROWN_MIX) * fade(distance(a[inside, 0], a[inside, 1]))
        kinds[name].append(a[~turn])
        clump = _clump(a[turn, 0], a[turn, 1], CROWN_CLUMPS)
        for k, kind in enumerate(CROWNS):
            kinds['HD_NorthTree' + kind].append(a[turn][clump == k])
    for name, parts in kinds.items():
        instances[name] = np.concatenate(parts).tolist()
    p = _grid(rng, box, CANOPY['spacing'])
    kind = np.where(rng.random(len(p)) < CROWN_MIX, rng.integers(0, len(CROWNS), len(p)),
                    _clump(p[:, 0], p[:, 1], CROWN_CLUMPS))
    d = distance(p[:, 0], p[:, 1])
    share = np.where(kind == CROWNS.index('Pine'), CANOPY['pine'], CANOPY['broadleaf'])
    keep = (rng.random(len(p)) < .97 * share * fade(d)) & (trail_distance(p[:, 0], p[:, 1]) > 15)
    p, kind = p[keep], kind[keep]
    z = np.asarray(height(p[:, 0], p[:, 1]), 'f8')
    line = FOREST_LINE + 25 * np.sin(p[:, 0] * .008) + 10 * np.sin(p[:, 1] * .021)
    grows = (z > 4) & (z < line)
    p, z, kind = p[grows], z[grows], kind[grows]
    have = _bins(np.array([q[:2] for name, rows in instances.items() if name.startswith(('Tree', 'HD_NorthTree'))
                           for q in rows if box[0] - 8 < q[0] < box[2] + 8 and box[1] - 8 < q[1] < box[3] + 8],
                          'f8').reshape(-1, 2), 8)
    west = p[:, 0] < mountains.BOUNDS[0]
    for q, ground, k, far in zip(p, z, kind, west):
        pine = CROWNS[k] == 'Pine'
        if _near(have, q, CANOPY['pine_gap' if pine else 'gap'], 8):
            continue
        name = ('HD_NorthTreeBackdrop' if far else 'HD_NorthTree') + CROWNS[k]
        scale = (rng.uniform(1.35, 1.85) if far else rng.uniform(1., 1.45)) * (PINE if pine else 1.)
        instances.setdefault(name, []).append([round(float(q[0]), 3), round(float(q[1]), 3),
                                               round(float(ground) - (.2 * scale if far else .3), 3),
                                               round(float(rng.uniform(0, 360)), 1), round(float(scale), 3)])
        have.setdefault((math.floor(q[0] / 8), math.floor(q[1] / 8)), []).append(q)
        done[name] = done.get(name, 0) + 1


def _grid(rng, box, spacing):
    x0, y0, x1, y1 = box
    gx, gy = np.meshgrid(np.arange(x0, x1, spacing), np.arange(y0, y1, spacing))
    return np.stack([gx.ravel(), gy.ravel()], 1) + rng.uniform(-.45, .45, (gx.size, 2)) * spacing


def _bins(points, size):
    cell = {}
    for q in points:
        cell.setdefault((math.floor(q[0] / size), math.floor(q[1] / size)), []).append(q)
    return cell


def _near(cell, q, gap, size):
    bx, by = math.floor(q[0] / size), math.floor(q[1] / size)
    return any(math.hypot(q[0] - o[0], q[1] - o[1]) < gap for dx in (-1, 0, 1) for dy in (-1, 0, 1)
               for o in cell.get((bx + dx, by + dy), ()))


def floor(x, y):
    """0..1: how much of the forest floor's colour the ground round the park takes (hidamari/mountains.py mesh): all of
    it under the detailed band, less and less out to FLOOR metres, where the island's own ground takes over."""
    x, y = np.asarray(x, 'f8'), np.asarray(y, 'f8')
    fx0, fy0, cell, _, _, mask = placement.footprint()
    j, i = np.nonzero(mask)
    x0, y0 = fx0 + i.min() * cell - FLOOR, fy0 + j.min() * cell - FLOOR
    x1, y1 = fx0 + (i.max() + 1) * cell + FLOOR, fy0 + (j.max() + 1) * cell + FLOOR
    out = np.zeros(np.broadcast(x, y).shape)
    box = (x > x0) & (x < x1) & (y > y0) & (y < y1)
    if box.any():
        out[box] = 1 - _smooth((distance(x[box], y[box]) - NEAR) / (FLOOR - NEAR))
    return out
