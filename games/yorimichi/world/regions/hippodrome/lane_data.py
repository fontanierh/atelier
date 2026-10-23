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
        mesh.quad((lx - w - ox, ys[k] - oy, za), (lx + w - ox, ys[k] - oy, za), (lx + w - ox, ys[k + 1] - oy, zb),
                  (lx - w - ox, ys[k + 1] - oy, zb), uv=[(0, ys[k] / UV_METRES), (L.LANE_WIDTH / UV_METRES, ys[k] / UV_METRES),
                                                       (L.LANE_WIDTH / UV_METRES, ys[k + 1] / UV_METRES), (0, ys[k + 1] / UV_METRES)])
    return mesh
