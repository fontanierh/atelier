"""Selected exact Hippodrome constructor."""
from hippodrome.mesh_data import Mesh, np, math, UV_METRES
from hippodrome import layout as L
from hippodrome.query_context import ground

def rails():
    """White rails each side of the track: posts every RAIL_POST_STEP and two bars, broken at the walk-in gaps."""
    mesh = Mesh()
    ox, oy = L.ORIGIN
    for offset in (-(L.WIDTH / 2 + .3), L.WIDTH / 2 + .3):
        steps = int(L.LAP / L.RAIL_POST_STEP)
        for k in range(steps):
            s0, s1 = k * L.LAP / steps, (k + 1) * L.LAP / steps
            x0, y0, h0 = L.centre(s0, offset)
            x1, y1, _ = L.centre(s1, offset)
            gap = lambda x, y: abs(y - oy) > L.RADIUS - 1 and y < oy and any(abs(x - gx) < w / 2 for gx, w in L.RAIL_GAPS)
            if gap(x0, y0) or gap(x1, y1):
                continue
            mesh.box((x0 - ox, y0 - oy, L.RAIL_HEIGHT / 2), (.06, .06, L.RAIL_HEIGHT / 2), h0)
            length = math.hypot(x1 - x0, y1 - y0)
            yaw = math.atan2(y1 - y0, x1 - x0)
            mid = ((x0 + x1) / 2 - ox, (y0 + y1) / 2 - oy)
            for z, thick in ((L.RAIL_HEIGHT - .05, .07), (L.RAIL_HEIGHT * .55, .04)):
                mesh.box((mid[0], mid[1], z), (length / 2 + .03, .05, thick), yaw)
    return mesh
