"""A continuous northern landscape around the current valley, in island metres."""
from functools import lru_cache

import numpy as np
from belmonte import layout as L, source
from hidamari import layout as H
from hippodrome.build import Mesh

OUTER = (L.BOUNDS[0] - L.APRON, L.SOUTH_JOIN, L.BOUNDS[2] + L.APRON, L.BOUNDS[3] + L.APRON)
COUNTRY = (-3200., L.SOUTH_JOIN, 3200., 6500.)


def grid_height(xs, ys, heights, x, y):
    """Intersect the same a-c diagonal used by the exported grid quads."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    i = np.clip(np.searchsorted(xs, x, side='right') - 1, 0, len(xs) - 2)
    j = np.clip(np.searchsorted(ys, y, side='right') - 1, 0, len(ys) - 2)
    u, v = (x - xs[i]) / (xs[i + 1] - xs[i]), (y - ys[j]) / (ys[j + 1] - ys[j])
    a, b, c, d = heights[j, i], heights[j, i + 1], heights[j + 1, i + 1], heights[j + 1, i]
    return np.where(u >= v, a + u * (b - a) + v * (c - b), a + u * (c - d) + v * (d - a))


def old_height(x, y):
    grid = H.backdrop_grid()
    axis = np.linspace(-3200., 3200., len(grid))
    return grid_height(axis, axis, grid, x, y)


@lru_cache(maxsize=1)
def country_grid():
    xs = np.unique(np.r_[np.linspace(-3200., 3200., 96), OUTER[0], OUTER[2]])
    ys = np.unique(np.r_[L.SOUTH_JOIN, np.linspace(-3200., 3200., 96)[-3:],
                         np.arange(3200., 6500., 50.), OUTER[3], 6500.])
    x, y = np.meshgrid(xs, ys)
    edge = old_height(x, np.minimum(y, 3200.))
    # The authored valley keeps its relief. Its surroundings use the island's
    # own deterministic rolling hills and taper to sea beyond the visible zone.
    inland = H.mountains.smooth((x + 3000.) / 750.) * H.mountains.smooth((3000. - x) / 750.)
    land = (225. + 26. * H.mountains.noise(x, y, 550., 27)) * inland
    land *= H.mountains.smooth((6500. - y) / 1000.)
    blend = H.mountains.smooth((y - 3200.) / 500.)
    z = edge * (1. - blend) + land * blend
    return xs, ys, z


def country_height(x, y):
    return grid_height(*country_grid(), x, y)


def collar_contains(x, y):
    return (x >= OUTER[0]) & (x <= OUTER[2]) & (y >= OUTER[1]) & (y <= OUTER[3])


def old_backdrop(grid, x, y):
    """Hide only coarse ground replaced by the fine collar, preserving the rest."""
    result = grid.copy()
    on = collar_contains(x, y) & (y > L.SOUTH_JOIN)
    result[on] = np.minimum(result[on], -50.)
    return result


def collar():
    """Four stitched strips: every imported rim vertex and outer grid knot retained."""
    mesh = Mesh()
    points = source.terrain().faces.reshape(-1, 3) + L.ORIGIN
    xs, ys, _ = country_grid()
    inner, outer = L.BOUNDS, OUTER
    # Orient each strip counter-clockwise round the hole; its outward rows then
    # give upward triangles. All corner rows are identical on adjacent strips.
    edges = [(0, 1, inner[1], outer[1], inner[0], inner[2], outer[0], outer[2]),
             (1, 0, inner[2], outer[2], inner[1], inner[3], outer[1], outer[3]),
             (0, 1, inner[3], outer[3], inner[2], inner[0], outer[2], outer[0]),
             (1, 0, inner[0], outer[0], inner[3], inner[1], outer[3], outer[1])]
    total = 0
    for along, across, edge, rim, lo, hi, olo, ohi in edges:
        boundary = points[np.isclose(points[:, across], edge, atol=.002), along]
        knots = xs if along == 0 else ys
        if across == 1 and edge == inner[1]:
            knots = np.r_[knots, np.arange(H.mountains.BOUNDS[0], H.mountains.BOUNDS[2] + 10., 10.)]
        u = np.unique(np.clip(np.r_[(boundary - lo) / (hi - lo),
                                   (knots - olo) / (ohi - olo), np.linspace(0., 1., int(abs(hi - lo) / 10.) + 2)], 0., 1.))
        ix, iy = (lo + u * (hi - lo), np.full_like(u, edge)) if along == 0 else (np.full_like(u, edge), lo + u * (hi - lo))
        ox, oy = (olo + u * (ohi - olo), np.full_like(u, rim)) if along == 0 else (np.full_like(u, rim), olo + u * (ohi - olo))
        iz = source.terrain().height(ix - L.ORIGIN[0], iy - L.ORIGIN[1]) + L.ORIGIN[2]
        oz = H.north_height(ox, oy) if across == 1 and edge == inner[1] else country_height(ox, oy)
        assert np.isfinite(iz).all() and np.isfinite(oz).all(), 'Open Belmonte collar edge'
        previous = None
        for t in np.linspace(0., 1., 40):
            smooth = t * t * (3. - 2. * t)
            row = np.stack([ix * (1. - t) + ox * t, iy * (1. - t) + oy * t,
                            iz * (1. - smooth) + oz * smooth], 1) - L.ORIGIN
            if previous is not None:
                for a, b, c, d in zip(previous[:-1], previous[1:], row[1:], row[:-1]):
                    mesh.quad(a, d, c, b)
            previous = row
        total += len(u)
    return mesh, {'boundary_samples': total, 'bounds_m': OUTER, 'source_gap_m': 0., 'island_gap_m': 0.}


def country():
    mesh = Mesh()
    xs, ys, z = country_grid()
    for j, (ay, by) in enumerate(zip(ys[:-1], ys[1:])):
        for i, (ax, bx) in enumerate(zip(xs[:-1], xs[1:])):
            if OUTER[0] <= ax and bx <= OUTER[2] and ay >= OUTER[1] and by <= OUTER[3]:
                continue
            mesh.quad(np.array([ax, ay, z[j, i]]) - L.ORIGIN,
                      np.array([bx, ay, z[j, i + 1]]) - L.ORIGIN,
                      np.array([bx, by, z[j + 1, i + 1]]) - L.ORIGIN,
                      np.array([ax, by, z[j + 1, i]]) - L.ORIGIN)
    return mesh
