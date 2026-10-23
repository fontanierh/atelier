"""Selected exact Hippodrome constructor."""
from hippodrome.mesh_data import Mesh, np, math, UV_METRES
from hippodrome import layout as L
from hippodrome.query_context import ground

def construct(z0):
    """The lane from the street up to the platform: a straight ramp, with its own skirts down to the ground."""
    mesh, sides = Mesh(), Mesh()
    (lx, ya), (_, yb) = L.LANE
    ox, oy = L.ORIGIN
    w = L.LANE_WIDTH / 2
    n = int(yb - ya)
    zs = np.linspace(L.LANE_START_Z, z0 + .02, n + 1)
    ys = np.linspace(ya, yb, n + 1)
    for k in range(n):
        za, zb = zs[k] - z0, zs[k + 1] - z0
        for side in (-1, 1):
            x = lx + side * w
            ga, gb = ground(x + side * 1.5, ys[k]) - z0 - .4, ground(x + side * 1.5, ys[k + 1]) - z0 - .4
            a, b = (x - ox, ys[k] - oy, za), (x - ox, ys[k + 1] - oy, zb)
            c, d = (x + side * 1.5 - ox, ys[k + 1] - oy, min(gb, zb - .3)), (x + side * 1.5 - ox, ys[k] - oy, min(ga, za - .3))
            sides.quad(*((a, d, c, b) if side > 0 else (a, b, c, d)))
    return sides
