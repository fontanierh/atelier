"""Selected exact Hippodrome constructor."""
from hippodrome.mesh_data import Mesh, np, math, UV_METRES
from hippodrome import layout as L
from hippodrome.query_context import ground

def construct(z0):
    x0, y0, x1, y1 = L.PLATFORM
    ox, oy = L.ORIGIN
    top, skirt = Mesh(), Mesh()
    # The skirt: round the rectangle (counter-clockwise), every metre from the platform edge out and down to just
    # below the ground.
    ring = [(x, y0) for x in np.arange(x0, x1, 1.)] + [(x1, y) for y in np.arange(y0, y1, 1.)] + \
           [(x, y1) for x in np.arange(x1, x0, -1.)] + [(x0, y) for y in np.arange(y1, y0, -1.)]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lane_x = L.LANE[0][0]

    def out(x, y):
        dx = (L.SKIRT if x >= x1 - 1e-6 else -L.SKIRT if x <= x0 + 1e-6 else 0.)
        dy = (L.SKIRT if y >= y1 - 1e-6 else -L.SKIRT if y <= y0 + 1e-6 else 0.)
        return x + dx, y + dy

    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        if ay <= y0 + 1e-6 and by <= y0 + 1e-6 and abs((ax + bx) / 2 - lane_x) < L.LANE_WIDTH / 2:
            continue   # the lane comes in here
        (oax, oay), (obx, oby) = out(ax, ay), out(bx, by)
        za, zb = ground(oax, oay) - z0 - .4, ground(obx, oby) - z0 - .4
        skirt.quad((ax - ox, ay - oy, 0), (oax - ox, oay - oy, za), (obx - ox, oby - oy, zb), (bx - ox, by - oy, 0),
                   uv=[(0, 0), (L.SKIRT / UV_METRES, za / UV_METRES), (L.SKIRT / UV_METRES, zb / UV_METRES), (0, 0.25)])
    return skirt
