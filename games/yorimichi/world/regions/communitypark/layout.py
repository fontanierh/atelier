"""The station-side community park, its excavated ground and walk/skate approach.

World metres are X east, Y north, Z up. The entire source scene is turned 180°
and moved as one body. Main deck +48.5 m; source root +38.472 m. The separate
one-metre ground patch stays below upward riding surfaces, including bowl bottoms.
Downward foundations remain buried rather than opening pits beneath solid pads.
"""
from functools import lru_cache
import math
import numpy as np
from communitypark.source import available, scene

ORIGIN = np.array([1280., 560., 38.472])
YAW = 180.
PATCH = (1200., 500., 1360., 650.)
STEP = 1.
CLEAR = (1210., 485., 1350., 635.)
ENTRY = np.array([1316., 516., 48.5])
SPAWN = np.array([1316., 522., 48.5])
HEADING = 180.
MAIN_DECK = 48.49965   # the main deck's top, island metres
# The x=1240 street's asphalt (6.5 cm above its 36 m datum) runs on to y=350 beneath the path.
# Start flush with it on the street's last uncarved 2 m vertex row: starting a row later left
# its tilted asphalt quad 2 cm proud of the ribbon, a lip at the join.
ACCESS = [(1240., 342., 36.065), (1240., 400., 41.5), (1280., 470., 47.), tuple(ENTRY)]
WIDTH = 4.
# Backdrop crowns in this box become detailed, near trees (clear(), near_boxes()).
NEAR_TREES = (1160., 400., 1400., 700.)


def place(points):
    p = np.asarray(points, float).copy()
    p[..., :2] *= -1
    return p+ORIGIN


def local(points):
    p = np.asarray(points, float)-ORIGIN
    p[..., :2] *= -1
    return p


def upward(triangles):
    """Which triangles face up. Recovered quarter-turn quaternions have float noise: a vertical wall
    can otherwise appear to have a tiny upward projection."""
    normal = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    return normal[:, 2] > np.linalg.norm(normal, axis=1)*1e-4


def inside(x, y, bounds=PATCH):
    return (x >= bounds[0]) & (x <= bounds[2]) & (y >= bounds[1]) & (y <= bounds[3])


def cell_inside(x, y, size=10.):
    # The north mountain's grid is replaced; keep its border nodes shared.
    return available() and x >= PATCH[0] and y >= PATCH[1] and x+size <= PATCH[2] and y+size <= PATCH[3]


@lru_cache(maxsize=1)
def access():
    from village.layout import spline
    xy, arc = spline([p[:2] for p in ACCESS], .5)
    controls = np.array(ACCESS)
    indices = [int(np.argmin(np.linalg.norm(xy-p[:2], axis=1))) for p in controls]
    z = np.interp(arc, arc[indices], controls[:, 2])
    return np.column_stack((xy, z))


def access_nearest(x, y):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    distance = np.full(x.shape, np.inf); height = np.zeros_like(x)
    # Sampling every 2 m keeps terrain queries inexpensive; the mesh uses 0.5 m.
    p = access(); p = np.vstack((p[::4], p[-1]))
    for a, b in zip(p, p[1:]):
        dx, dy = b[:2]-a[:2]; length = dx*dx+dy*dy
        if length < 1e-12:
            continue
        t = np.clip(((x-a[0])*dx+(y-a[1])*dy)/length, 0, 1)
        d = np.hypot(x-a[0]-t*dx, y-a[1]-t*dy)
        near = d < distance
        height = np.where(near, a[2]+t*(b[2]-a[2]), height)
        distance = np.minimum(distance, d)
    return distance, height


def carve_access(x, y, z):
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    mask = (y > ACCESS[0][1]) & (y <= 520) & (x > 1220) & (x < 1320)
    if not available() or not np.any(mask):
        return z
    d, h = access_nearest(x[mask], y[mask])
    t = np.clip((7-d)/4, 0, 1); w = t*t*(3-2*t)
    # The path's thin riding ribbon sits above this supporting ground.
    result = z.copy()
    result[mask] = z[mask]*(1-w)+(h-.12)*w
    return result


@lru_cache(maxsize=1)
def cover():
    """Lowest upward source surface on the 1 m patch, expanded two cells.

    Triangle rasterization sees the bowl bottoms as well as the decks. Taking the
    lowest neighbouring corner protects both halves of each ground grid cell.
    """
    xs = np.arange(PATCH[0], PATCH[2]+STEP, STEP)
    ys = np.arange(PATCH[1], PATCH[3]+STEP, STEP)
    bottom = np.full((len(ys), len(xs)), np.inf)
    triangles = place(scene().triangles())
    for a, b, c in triangles[upward(triangles)]:
        # Thin floor spacers can lie entirely between grid nodes. Rasterize
        # their edges too; an interior-only raster would leave grass over them.
        for start, end in ((a, b), (b, c), (c, a)):
            count = max(1, math.ceil(np.linalg.norm((end-start)[:2])/STEP))
            points = start+np.linspace(0, 1, count+1)[:, None]*(end-start)
            ix = np.rint((points[:, 0]-PATCH[0])/STEP).astype(int)
            iy = np.rint((points[:, 1]-PATCH[1])/STEP).astype(int)
            np.minimum.at(bottom, (iy, ix), points[:, 2])
        den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den) < 1e-10:
            continue
        p = np.array([a, b, c]); lo = p[:, :2].min(0); hi = p[:, :2].max(0)
        i0 = max(0, int(math.ceil((lo[0]-PATCH[0])/STEP-1e-8)))
        j0 = max(0, int(math.ceil((lo[1]-PATCH[1])/STEP-1e-8)))
        i1 = min(len(xs)-1, int(math.floor((hi[0]-PATCH[0])/STEP+1e-8)))
        j1 = min(len(ys)-1, int(math.floor((hi[1]-PATCH[1])/STEP+1e-8)))
        if i1 < i0 or j1 < j0:
            continue
        x, y = np.meshgrid(xs[i0:i1+1], ys[j0:j1+1])
        u = ((b[1]-c[1])*(x-c[0])+(c[0]-b[0])*(y-c[1]))/den
        v = ((c[1]-a[1])*(x-c[0])+(a[0]-c[0])*(y-c[1]))/den
        w = 1-u-v
        valid = (u >= -1e-8) & (v >= -1e-8) & (w >= -1e-8)
        z = np.where(valid, u*a[2]+v*b[2]+w*c[2], np.inf)
        bottom[j0:j1+1, i0:i1+1] = np.minimum(bottom[j0:j1+1, i0:i1+1], z)
    padded = np.pad(bottom, 2, constant_values=np.inf)
    conservative = np.minimum.reduce([padded[j:j+len(ys), i:i+len(xs)] for j in range(5) for i in range(5)])
    return xs, ys, conservative


@lru_cache(maxsize=2)
def grid(base_sampler):
    xs, ys, bottom = cover(); x, y = np.meshgrid(xs, ys)
    z = carve_access(x, y, base_sampler(x, y))
    z = np.minimum(z, bottom-.25)
    return x, y, z


def ground(x, y, base_sampler):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    field = grid(base_sampler)[2]
    fx = np.clip((x-PATCH[0])/STEP, 0, field.shape[1]-1.000001)
    fy = np.clip((y-PATCH[1])/STEP, 0, field.shape[0]-1.000001)
    i, j = fx.astype(int), fy.astype(int); u, v = fx-i, fy-j
    a, b, c, d = field[j, i], field[j, i+1], field[j+1, i], field[j+1, i+1]
    return np.where(u >= v, a*(1-u)+b*(u-v)+d*v, a*(1-v)+d*u+c*(v-u))


def surface(x, y, base_sampler):
    """base_sampler's terrain with the park's fine patch in place."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    z = np.array(base_sampler(x, y), float)
    mask = inside(x, y) & available()
    if mask.any(): z[mask] = ground(x[mask], y[mask], base_sampler)
    return z


def near_boxes():
    return [list(NEAR_TREES)] if available() else []


def clear(instances):
    """Clear the new destination and approach, and use detailed trees at its edge."""
    if not available(): return
    families = {'HD_NorthTreeGold': 'Tree_Ginkgo', 'HD_NorthTreeRust': 'Tree_Maple_A',
                'HD_NorthTreeGreen': 'Tree_Maple_B', 'HD_NorthTreePine': 'Tree_Pine_B',
                'HD_NorthTreeBackdropGold': 'Tree_Ginkgo', 'HD_NorthTreeBackdropRust': 'Tree_Maple_A',
                'HD_NorthTreeBackdropGreen': 'Tree_Maple_B', 'HD_NorthTreeBackdropPine': 'Tree_Pine_B'}
    moved = {}
    for name, rows in list(instances.items()):
        if not rows or not name.startswith(('Tree', 'HD_NorthTree', 'Bush', 'Grass', 'Rock', 'Litter')):
            continue
        a = np.asarray(rows, float); x, y = a[:, 0], a[:, 1]
        distance = np.full(x.shape, np.inf)
        approach = (x >= 1220) & (x <= 1320) & (y >= 330) & (y <= 530)
        distance[approach], _ = access_nearest(x[approach], y[approach])
        remove = inside(x, y, CLEAR) | (distance < (6. if 'Tree' in name else 2.7))
        retained = a[~remove]
        if name in families and len(retained):
            near = inside(retained[:, 0], retained[:, 1], NEAR_TREES)
            detailed = retained[near].copy()
            detailed[:, 4] *= .8
            moved.setdefault(families[name], []).extend(detailed.tolist())
            retained = retained[~near]
        instances[name] = retained.tolist()
    for name, rows in moved.items():
        instances.setdefault(name, []).extend(rows)


def screen_vegetation(base_sampler):
    """A secluded clearing: overlapping mature crowns, young trees and a closed woodland floor.

    The tree-house canopy meshes have articulated branches and 1,100–1,250
    individual leaf cards, rather than the island's small roadside crowns.
    Three lower layers fill the bare trunks without entering the riding area
    or the four-metre approach. The park owns this scatter independently of
    the city clearance, using the existing foliage asset/material families.
    """
    vertices = place(scene().triangles()).reshape(-1, 3)
    lo, hi = vertices[:, :2].min(0), vertices[:, :2].max(0)
    rng = np.random.default_rng(202604)
    plants = {}

    def points(spacing, inner, outer, path_gap, density=1.):
        x, y = np.meshgrid(np.arange(lo[0]-outer, hi[0]+outer, spacing),
                           np.arange(lo[1]-outer, hi[1]+outer, spacing))
        # Staggered, jittered rows avoid a visible plantation grid.
        x[::2] += spacing/2
        xy = np.column_stack((x.ravel(), y.ravel()))+rng.uniform(-.22, .22, (x.size, 2))*spacing
        edge = np.maximum(np.maximum(lo-xy, xy-hi), 0).max(1)
        distance, _ = access_nearest(xy[:, 0], xy[:, 1])
        keep = (edge >= inner) & (edge <= outer) & (distance >= path_gap)
        keep &= rng.random(len(xy)) < density
        return xy[keep], edge[keep]

    def add(xy, names, scales, sink):
        z = np.asarray(base_sampler(xy[:, 0], xy[:, 1])).copy()
        patch = inside(xy[:, 0], xy[:, 1])
        z[patch] = ground(xy[patch, 0], xy[patch, 1], base_sampler)
        positions = local(np.column_stack((xy, z-sink)))
        for p, name, scale in zip(positions, names, scales):
            plants.setdefault(str(name), []).append([*p.tolist(), float(rng.uniform(0, 360)), float(scale)])

    # A sixty-metre belt closes the canopy, with coherent red/gold/green groves.
    xy, edge = points(4.5, 6.5, 60., 9.5)
    clump = np.sin(xy[:, 0]*.035+np.sin(xy[:, 1]*.04)*1.8)+.6*np.cos(xy[:, 1]*.027)
    families = [(('Tree_Cedar_A', 'Tree_Canopy_Maple'), (.8, .2)),
                (('Tree_Canopy_Maple', 'Tree_Canopy_Crimson', 'Tree_Canopy_Amber'), (.5, .35, .15)),
                (('Tree_Canopy_Ginkgo', 'Tree_Canopy_Amber'), (.6, .4))]
    kinds = np.digitize(clump, [-.35, .65])
    mixed = rng.random(len(xy)) < .12
    kinds[mixed] = rng.integers(0, len(families), mixed.sum())
    names = np.empty(len(xy), object)
    for k, (members, weights) in enumerate(families):
        pick = kinds == k; names[pick] = rng.choice(members, pick.sum(), p=weights)
    scales = rng.uniform(1.05, 1.3, len(xy))
    scales[edge > 20] = rng.uniform(1.3, 1.7, int((edge > 20).sum()))
    add(xy, names, scales, .12)

    # Young trees close the middle storey beneath the high mature crowns.
    young, _ = points(5.2, 4.5, 54., 6.8, .9)
    distance = np.linalg.norm(young[:, None]-xy[None], axis=2).min(1)
    young = young[distance > 1.4]
    names = rng.choice(['Tree_Maple_A', 'Tree_Maple_B', 'Tree_Ginkgo', 'Tree_Cedar_B'],
                       len(young), p=[.35, .25, .2, .2])
    add(young, names, rng.uniform(.9, 1.4, len(young)), .12)

    # Dense overlapping shrubs screen the sightlines between otherwise bare trunks.
    shrubs, _ = points(2.4, 2.7, 57., 4.8, .85)
    names = rng.choice(['Bush_Green_A', 'Bush_Green_B', 'Bush_Ochre_A', 'Bush_Ochre_B'],
                       len(shrubs), p=[.4, .3, .2, .1])
    add(shrubs, names, rng.uniform(1.25, 1.8, len(shrubs)), .15)
    floor, _ = points(2., 1.5, 56., 3.2, .75)
    names = rng.choice(['Grass_A', 'Grass_B', 'Litter'], len(floor), p=[.45, .4, .15])
    scales = rng.uniform(.85, 1.3, len(floor))
    for name in ('Grass_A', 'Grass_B', 'Litter'):
        pick = names == name
        add(floor[pick], names[pick], scales[pick], -.025 if name == 'Litter' else .08)
    return plants


def clearance():
    rectangles = [[list(p) for p in [(CLEAR[0], CLEAR[1]), (CLEAR[2], CLEAR[1]),
                                    (CLEAR[2], CLEAR[3]), (CLEAR[0], CLEAR[3])]]]
    for a, b in zip(ACCESS, ACCESS[1:]):
        tangent = np.array(b[:2])-a[:2]; normal = np.array([-tangent[1], tangent[0]])
        normal *= 6/np.linalg.norm(normal)
        rectangles.append([p.tolist() for p in [np.array(a[:2])+normal, np.array(b[:2])+normal,
                                               np.array(b[:2])-normal, np.array(a[:2])-normal]])
    return rectangles
