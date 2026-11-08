"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.procedural.cell_material import cell_material
from brinecove.procedural.ground_face import ground_face
from brinecove.procedural.terrain_dressing import terrain_dressing


def terrain(hills=True):
    from brinecove.ground import jag_point
    b = Builder('01_terrain')
    nx, ny = 600, 480
    dx = (L.VIEW_X_MAX - L.VIEW_X_MIN) / nx
    dy = (L.VIEW_Y_MAX - L.VIEW_Y_MIN) / ny
    zs = [[L.ground(L.VIEW_X_MIN + i * dx, L.VIEW_Y_MIN + j * dy) for j in range(ny + 1)] for i in range(nx + 1)]
    for i in range(nx):
        for j in range(ny):
            x0 = L.VIEW_X_MIN + i * dx; x1 = x0 + dx
            y0 = L.VIEW_Y_MIN + j * dy; y1 = y0 + dy
            a = (x0, y0, zs[i][j]); bb = (x1, y0, zs[i + 1][j])
            c = (x1, y1, zs[i + 1][j + 1]); d = (x0, y1, zs[i][j + 1])
            # Break the sampled heightfield on steep faces (see ground.jag_point).
            a, bb, c, d = (jag_point(a), jag_point(bb), jag_point(c), jag_point(d))
            gx = (x0 + x1) / 2; gy = (y0 + y1) / 2
            sl = L.slope(gx, gy)
            ground_face(b, a, bb, c, d, cell_material(a, bb, c, d, gx, gy, sl, i, j), gx, gy, sl)
    terrain_dressing(b, hills)
    return b
