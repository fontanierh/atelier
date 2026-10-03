"""The station-side community park, its excavated ground and walk/skate approach.

World metres are X east, Y north, Z up. The entire source scene is turned 180°
and moved as one body. Main deck +48.5 m; source root +38.472 m. The separate
one-metre ground patch stays below upward riding surfaces, including bowl bottoms.
Downward foundations remain buried rather than opening pits beneath solid pads.
"""
from functools import lru_cache
import math
import numpy as np
from communitypark.source import scene

ORIGIN = np.array([1280., 560., 38.472])
YAW = 180.
PATCH = (1200., 500., 1360., 650.)
STEP = 1.
CLEAR = (1210., 485., 1350., 635.)
ENTRY = np.array([1316., 516., 48.5])
SPAWN = np.array([1316., 522., 48.5])
HEADING = 180.
ACCESS = [(1240., 343., 36.), (1240., 400., 41.5), (1280., 470., 47.), tuple(ENTRY)]
WIDTH = 4.


def place(points):
    p = np.asarray(points, float).copy()
    p[..., :2] *= -1
    return p+ORIGIN


def local(points):
    p = np.asarray(points, float)-ORIGIN
    p[..., :2] *= -1
    return p


def inside(x, y, bounds=PATCH):
    return (x >= bounds[0]) & (x <= bounds[2]) & (y >= bounds[1]) & (y <= bounds[3])


def cell_inside(x, y, size=10.):
    # The north mountain's grid is replaced; keep its border nodes shared.
    return x >= PATCH[0] and y >= PATCH[1] and x+size <= PATCH[2] and y+size <= PATCH[3]


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
    mask = (y >= 343) & (y <= 520) & (x > 1220) & (x < 1320)
    if not np.any(mask):
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
    for a, b, c in triangles:
        normal = np.cross(b-a, c-a)
        # Recovered quarter-turn quaternions have float noise: a vertical wall
        # can otherwise appear to have a tiny upward projection.
        if normal[2] <= np.linalg.norm(normal)*1e-4:
            continue
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


def clear(instances):
    """Clear the new destination and approach, and use detailed trees at its edge."""
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
            near = inside(retained[:, 0], retained[:, 1], (1160., 400., 1400., 700.))
            detailed = retained[near].copy()
            detailed[:, 4] *= .8
            moved.setdefault(families[name], []).extend(detailed.tolist())
            retained = retained[~near]
        instances[name] = retained.tolist()
    for name, rows in moved.items():
        instances.setdefault(name, []).extend(rows)


def clearance():
    rectangles = [[list(p) for p in [(CLEAR[0], CLEAR[1]), (CLEAR[2], CLEAR[1]),
                                    (CLEAR[2], CLEAR[3]), (CLEAR[0], CLEAR[3])]]]
    for a, b in zip(ACCESS, ACCESS[1:]):
        tangent = np.array(b[:2])-a[:2]; normal = np.array([-tangent[1], tangent[0]])
        normal *= 6/np.linalg.norm(normal)
        rectangles.append([p.tolist() for p in [np.array(a[:2])+normal, np.array(b[:2])+normal,
                                               np.array(b[:2])-normal, np.array(a[:2])-normal]])
    return rectangles
