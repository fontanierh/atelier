"""Replace authored planting with existing island flora under a fixed budget.

Positions come from the current scene, never from the old Haras planting scripts.
Dense fields are thinned deterministically; town pots and avenue spacing survive.
"""
import hashlib
import math

import numpy as np
from zeppelin.layout import belmonte_clear
from . import layout as L

BUDGETS = {'tree': 26000, 'bush': 18000, 'grass': 2500}


def species(name):
    if 'Potted' in name or 'Topiary' in name:
        return 'Tree_Tuscan_Olive', 'tree', 7.5
    if 'Cypress' in name:
        return 'Tree_Tuscan_Cypress', 'tree', 15.
    if 'Olive' in name:
        return 'Tree_Tuscan_Olive', 'tree', 7.5
    if 'Pine' in name:
        return 'Tree_Tuscan_Pine', 'tree', 16.
    if any(word in name for word in ('Oak', 'Olive', 'Tree')):
        return 'Tree_Tuscan_Oak', 'tree', 13.
    if any(word in name for word in ('Lawn', 'VegRow', 'GorgeGreen')):
        return 'Grass_A', 'grass', .8
    if any(word in name for word in ('Flower', 'Lavender')):
        return 'Bush_Flower_A', 'bush', 1.2
    return 'Bush_Green_B', 'bush', 1.


def rotate(q, point):
    axis = np.asarray(q[:3], float)
    point = np.asarray(point, float)
    return point + 2 * np.cross(axis, np.cross(axis, point) + q[3] * point)


def replacements(data, ground=None):
    candidates = {'tree': [], 'bush': [], 'grass': []}
    retained, outside = 0, 0
    for entry in data['planting']:
        name = entry['name']
        if 'FarVeg' in name:
            # These meshes are forests in the replaced multi-kilometre backdrop.
            outside += entry['count']
            continue
        mesh, kind, model_height = species(name)
        low, high = np.asarray(entry['bounds_cm'], float)
        size = np.maximum(high - low, 1.)
        for transform in entry['transforms']:
            translation = np.asarray(transform['translation_cm'], float)
            scale = np.asarray(transform['scale'], float)
            x, y = translation[:2] / [100., -100.]
            if not (L.SOURCE_BOUNDS[0] <= x <= L.SOURCE_BOUNDS[2] and L.SOURCE_BOUNDS[1] <= y <= L.SOURCE_BOUNDS[3]):
                outside += 1
                continue
            retained += 1
            # Long vineyard strips and hedges become a row of island shrubs.
            axis = int(np.argmax(size[:2]))
            count = min(12, max(1, int(size[axis] * abs(scale[axis]) / 300))) if kind == 'bush' else 1
            for index in range(count):
                offset = np.zeros(3)
                if count > 1:
                    offset[axis] = low[axis] + (index + .5) / count * size[axis]
                position = translation + rotate(transform['rotation_xyzw'], offset * scale)
                height = size[2] * abs(scale[2]) / 100.
                small = 'Potted' in name or 'Topiary' in name
                fitted = float(np.clip(height / model_height, .20 if small else .6 if kind == 'tree' else .25, 1.5))
                result = {'translation_cm': position.tolist(), 'rotation_xyzw': transform['rotation_xyzw'],
                          'scale': [fitted, fitted, fitted]}
                priority = hashlib.sha256(f'{name}:{position[0]:.2f}:{position[1]:.2f}'.encode()).hexdigest()
                candidates[kind].append((priority, mesh, result))
    embedded = 0
    models = {entry['source_asset']: entry for entry in data['meshes']}
    if ground is not None:
        points = []
        for placement in data['placements']:
            transform = placement['transform']
            for hint in models[placement['asset']]['embedded_plants']:
                x, y, z = hint['base_m']
                native = np.array([x * 100, -y * 100, z * 100]) * transform['scale']
                point = np.asarray(transform['translation_cm']) + rotate(transform['rotation_xyzw'], native)
                points.append(point)
        if points:
            points = np.asarray(points)
            heights = ground(points[:, 0] / 100, -points[:, 1] / 100)
            for point, height in zip(points, heights):
                if not np.isfinite(height):
                    continue
                # Balcony planters and vines keep their measured elevation;
                # only ground planting is seated on the current terrain.
                if abs(point[2] / 100. - height) < 2.:
                    point[2] = height * 100
                transform = {'translation_cm': point.tolist(), 'rotation_xyzw': [0., 0., 0., 1.], 'scale': [.7, .7, .7]}
                priority = hashlib.sha256(f'embedded:{point[0]:.2f}:{point[1]:.2f}'.encode()).hexdigest()
                candidates['bush'].append((priority, 'Bush_Green_B', transform))
                embedded += 1
    selected, report = {}, {'authored_in_region': retained, 'outside_or_backdrop': outside,
                           'embedded_planting_candidates': embedded, 'kinds': {}}
    for kind, rows in candidates.items():
        # Deterministic spatial thinning keeps the authored distribution, including
        # small courtyards; a hard cap prevents an accidental vegetation explosion.
        cells = set()
        # Preserve the actual avenues and olive rows. Only exact duplicate tree
        # roots are collapsed; authored spacing is never replaced by a grid.
        cell_size = {'tree': 10., 'bush': 150., 'grass': 250.}[kind]
        count = 0
        for _, mesh, transform in sorted(rows, key=lambda row: (row[0], row[1])):
            x, y, _ = transform['translation_cm']
            if bool(belmonte_clear(x / 100. + L.ORIGIN[0], -y / 100. + L.ORIGIN[1], kind)):
                continue
            urban = abs(x) < 24000 and abs(y) < 26000
            spacing = min(cell_size, 250.) if urban else cell_size
            key = (math.floor(x / spacing), math.floor(y / spacing), urban)
            if key in cells or count >= BUDGETS[kind]:
                continue
            cells.add(key)
            selected.setdefault(mesh, []).append(transform)
            count += 1
        report['kinds'][kind] = {'candidates': len(rows), 'selected': count, 'budget': BUDGETS[kind]}
    assert selected, 'No island flora replaced the current planting'
    return selected, report


def woodland(surface, limit=17000):
    """Detailed leaf trees in clustered woodland on the connecting collar."""
    from . import terrain_bounds as terrain
    rng = np.random.default_rng(941)
    x, y = np.meshgrid(np.arange(terrain.OUTER[0] + 8., terrain.OUTER[2], 6.),
                       np.arange(terrain.OUTER[1] + 8., terrain.OUTER[3], 6.))
    x, y = x.ravel(), y.ravel()
    x += rng.uniform(-2.5, 2.5, len(x)); y += rng.uniform(-2.5, 2.5, len(y))
    on = ~L.contains(x, y, margin=8.)
    x, y = x[on], y[on]
    z = surface.height(x - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2]
    dx = surface.height(x + 1. - L.ORIGIN[0], y - L.ORIGIN[1]) + L.ORIGIN[2] - z
    dy = surface.height(x - L.ORIGIN[0], y + 1. - L.ORIGIN[1]) + L.ORIGIN[2] - z
    patch = woodland_density(x, y)
    keep = np.isfinite(z) & np.isfinite(dx) & np.isfinite(dy) & (np.hypot(dx, dy) < .7) & (rng.random(len(x)) < patch)
    # Keep the railway open: route v3's corridor (train/corridor.py) where the route is built, else the first
    # sketch of the eastern corridor; these are planting data only.
    from train import corridor
    line = corridor.load()
    if line is not None:
        clear = ~line.blocked(x, y)
    else:
        distance = np.full(len(x), np.inf)
        for a, b in zip(L.RAILWAY, L.RAILWAY[1:]):
            a, b = np.asarray(a), np.asarray(b); d = b - a
            t = np.clip(((x - a[0]) * d[0] + (y - a[1]) * d[1]) / np.dot(d, d), 0., 1.)
            distance = np.minimum(distance, np.hypot(x - a[0] - t * d[0], y - a[1] - t * d[1]))
        clear = distance > 24.
    indices = np.flatnonzero(keep & clear)
    rng.shuffle(indices)
    result = {}
    from forest.ecotone import kinds, tuscan_mask
    from forest.specs import MODEL_BY_KIND
    forest_kind=kinds(x,y,z);tuscan=tuscan_mask(x,y)
    for index in indices[:limit]:
        kind=forest_kind[index]
        name=MODEL_BY_KIND[kind]
        if tuscan[index]:
            name='Tree_Tuscan_Pine' if kind=='Pine' else 'Tree_Tuscan_Olive' if kind=='Gold' else 'Tree_Tuscan_Oak'
        scale = float(rng.uniform(.85, 1.2)); angle = float(rng.uniform(0., math.tau))
        result.setdefault(str(name), []).append({'translation_cm': [(float(x[index]) - L.ORIGIN[0]) * 100.,
                                                                    -(float(y[index]) - L.ORIGIN[1]) * 100.,
                                                                    (float(z[index]) - L.ORIGIN[2] - .1) * 100.],
                                               'rotation_xyzw': [0., 0., math.sin(angle / 2.), math.cos(angle / 2.)],
                                               'scale': [scale, scale, scale]})
    return result


def woodland_density(x, y):
    from hidamari.mountains import noise
    return np.clip(.50 + .45 * noise(x, y, 110., 31), .1, .95)
