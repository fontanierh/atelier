"""Selected exact Hippodrome constructor."""
from hippodrome.mesh_data import Mesh, np, math, UV_METRES
from hippodrome import layout as L
from hippodrome.query_context import ground

def track():
    """The dirt ribbon, 3 cm over the grass, every metre of the lap; u runs across, v along."""
    mesh = Mesh()
    steps = int(L.LAP)
    half = L.WIDTH / 2
    ox, oy = L.ORIGIN
    for k in range(steps):
        s0, s1 = k * L.LAP / steps, (k + 1) * L.LAP / steps
        (ix0, iy0, _), (ex0, ey0, _) = L.centre(s0, -half), L.centre(s0, half)
        (ix1, iy1, _), (ex1, ey1, _) = L.centre(s1, -half), L.centre(s1, half)
        v0, v1 = s0 / UV_METRES, s1 / UV_METRES
        mesh.quad((ex0 - ox, ey0 - oy, .03), (ex1 - ox, ey1 - oy, .03), (ix1 - ox, iy1 - oy, .03), (ix0 - ox, iy0 - oy, .03),
                  uv=[(0, v0), (0, v1), (L.WIDTH / UV_METRES, v1), (L.WIDTH / UV_METRES, v0)], normal=(0, 0, 1))
    return mesh
