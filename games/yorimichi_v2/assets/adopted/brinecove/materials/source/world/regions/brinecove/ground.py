"""Brinecove's game ground: the layout's terrain inside region.INNER, eased across the collar into the far hills
and closed onto FarHills' own hole vertices, so the two meshes share every vertex on their seam.

Local metres throughout (region.py); plain Python, the Blender export only turns the Builder into meshes.
"""
import math

import numpy as np

from brinecove import layout as L
from brinecove import rocks
from brinecove.geom import _surface_scale as surface_scale
from brinecove.procedural.cell_material import cell_material
from brinecove.procedural.ground_face import ground_face
from brinecove import region as R
from brinecove.geom import Builder
from brinecove.boundary import weld
from brinecove.ground_sampling import STEP, _axis, jag_point


def _loop(points_by_side):
    """One counter-clockwise loop from per-side point lists, each tagged with a perimeter parameter in [0, 4):
    south (x rising) 0..1, east (y rising) 1..2, north (x falling) 2..3, west (y falling) 3..4."""
    ox0, oy0, ox1, oy1 = R.OUTER
    loop = []
    for side, (pts, along, lo, hi, rising, base) in points_by_side.items():
        for p in pts:
            t = (p[along] - lo) / (hi - lo)
            t = t if rising else 1.0 - t
            if t >= 1.0 - 1e-9:
                continue  # the next side owns the corner
            loop.append((base + max(0.0, t), p))
    loop.sort(key=lambda item: item[0])
    return loop


def zip_loops(b, inner, outer, material=None):
    """Triangulate the band between two closed loops that share the same perimeter parameterisation."""
    def at(loop, k):
        return loop[k % len(loop)]

    def param(loop, k):
        t, _ = at(loop, k)
        return t + 4.0 * (k // len(loop))

    i = j = 0
    while i < len(inner) or j < len(outer):
        a, c = at(inner, i)[1], at(outer, j)[1]
        advance_inner = j >= len(outer) or (i < len(inner) and param(inner, i + 1) <= param(outer, j + 1))
        if advance_inner:
            n = at(inner, i + 1)[1]
            tri = (a, n, c)
            i += 1
        else:
            n = at(outer, j + 1)[1]
            tri = (a, n, c)
            j += 1
        material_face(b, tri, material)


def material_face(b, tri, material=None):
    if material is None:
        zavg = sum(p[2] for p in tri) / 3
        material = 'seabed' if zavg < -0.5 else 'sand' if zavg < 2.0 else 'jungle_dark'
    k = 1.0 / max(0.05, surface_scale(material))
    # Keep every triangle facing up: the loops run counter-clockwise, the outer one outside the inner.
    (ax, ay, _), (bx, by, _), (cx, cy, _) = tri
    if (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) < 0:
        tri = (tri[0], tri[2], tri[1])
    b.face(tri, material, [(p[0] * k, p[1] * k) for p in tri])


def build(rim, rim_world):
    """The ground Builder (local metres). rim and rim_world come from region.rim_from_mesh."""
    b = Builder('BC_Ground')
    ox0, oy0, ox1, oy1 = R.OUTER
    xs = _axis(ox0, ox1, STEP)
    ys = _axis(oy0, oy1, STEP)
    z = [[R.ground(L.ground, rim, x, y) for y in ys] for x in xs]
    nx, ny = len(xs) - 1, len(ys) - 1

    def point(i, j):
        p = (xs[i], ys[j], z[i][j])
        return jag_point(p) if R.collar_weight(xs[i], ys[j]) <= 0.0 else p

    pts = [[point(i, j) for j in range(ny + 1)] for i in range(nx + 1)]
    # Interior cells: every cell but the outermost ring, which the zipper below replaces.
    for i in range(1, nx - 1):
        for j in range(1, ny - 1):
            a, bb, c, d = pts[i][j], pts[i + 1][j], pts[i + 1][j + 1], pts[i][j + 1]
            gx, gy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
            dzx = (bb[2] + c[2] - a[2] - d[2]) / (2 * (xs[i + 1] - xs[i]))
            dzy = (c[2] + d[2] - a[2] - bb[2]) / (2 * (ys[j + 1] - ys[j]))
            grid_slope = math.hypot(dzx, dzy)
            inside = R.collar_weight(gx, gy) <= 0.0
            sl = L.slope(gx, gy) if inside else grid_slope
            if inside:
                mat = cell_material(a, bb, c, d, gx, gy, sl, i, j)
            else:
                zavg = (a[2] + bb[2] + c[2] + d[2]) / 4
                mat = ('seabed' if zavg < -0.5 else 'sand' if zavg < 2.0 and sl < 0.45 else
                       rocks.terrain_material(gx, gy, zavg, sl, i, j))
            ground_face(b, a, bb, c, d, mat, gx, gy, sl)
    # The ring one step in from the edge, and FarHills' own hole vertices on the edge.
    inner = _loop({
        'south': ([pts[i][1] for i in range(1, nx)], 0, xs[1], xs[nx - 1], True, 0.0),
        'east': ([pts[nx - 1][j] for j in range(1, ny)], 1, ys[1], ys[ny - 1], True, 1.0),
        'north': ([pts[i][ny - 1] for i in range(1, nx)], 0, xs[1], xs[nx - 1], False, 2.0),
        'west': ([pts[1][j] for j in range(1, ny)], 1, ys[1], ys[ny - 1], False, 3.0),
    })
    local = {side: [R.to_local(*p) for p in rim_world[side]] for side in ('south', 'east', 'north', 'west')}
    outer = _loop({
        'south': (local['south'], 0, ox0, ox1, True, 0.0),
        'east': (local['east'], 1, oy0, oy1, True, 1.0),
        'north': (local['north'], 0, ox0, ox1, False, 2.0),
        'west': (local['west'], 1, oy0, oy1, False, 3.0),
    })
    zip_loops(b, inner, outer)
    return b, dict(grid=[nx, ny], step=STEP, rim_vertices=len(outer), ring_vertices=len(inner))
