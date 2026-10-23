"""Selected exact Hippodrome constructor."""
from hippodrome.mesh_data import Mesh, np, math, UV_METRES
from hippodrome import layout as L
from hippodrome.query_context import ground

def construct(z0):
    x0, y0, x1, y1 = L.PLATFORM
    ox, oy = L.ORIGIN
    top, skirt = Mesh(), Mesh()
    xs, ys = np.linspace(x0, x1, int((x1 - x0) // 8) + 1), np.linspace(y0, y1, int((y1 - y0) // 8) + 1)
    for a, b in zip(xs[:-1], xs[1:]):
        for c, d in zip(ys[:-1], ys[1:]):
            top.quad((a - ox, c - oy, 0), (b - ox, c - oy, 0), (b - ox, d - oy, 0), (a - ox, d - oy, 0), normal=(0, 0, 1))
    return top
