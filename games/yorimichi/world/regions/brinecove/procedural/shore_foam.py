"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.procedural.final_ground import final_ground
import math


def shore_foam(b, step=3.0, width=3.4, level=0.05):
    """Animated foam hugging the real waterline: marching squares on the final ground at sea level, each crossing
    becoming a thin strip laid seaward (v 0 at the shore, 1 offshore), so foam only touches actual shore."""
    import brinecove.region as R
    x0, y0, x1, y1 = R.OUTER
    nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
    z = [[final_ground(x0 + i * step, y0 + j * step) - level for j in range(ny + 1)] for i in range(nx + 1)]
    count = 0
    for i in range(nx):
        for j in range(ny):
            c = ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))
            v = [z[a][bb] for a, bb in c]
            if min(v) > 0 or max(v) < 0 or max(v) - min(v) > 18.0:
                continue
            cx, cy = x0 + (i + 0.5) * step, y0 + (j + 0.5) * step
            if L.in_gorge(cx, cy, 4.0) or L.on_pier(cx, cy, 4.0) or L.town_floor(cx, cy, 2.0):
                continue
            cross = []
            for k in range(4):
                (ia, ja), (ib, jb) = c[k], c[(k + 1) % 4]
                za, zb = z[ia][ja], z[ib][jb]
                if (za > 0) != (zb > 0):
                    t = za / (za - zb)
                    cross.append((x0 + (ia + (ib - ia) * t) * step, y0 + (ja + (jb - ja) * t) * step))
            if len(cross) != 2:
                continue
            (ax, ay), (bx, by) = cross
            # Seaward is down the ground's gradient; steep cliff feet get a thinner collar.
            gx = (v[1] + v[2] - v[0] - v[3]) / (2 * step)
            gy = (v[2] + v[3] - v[0] - v[1]) / (2 * step)
            g = math.hypot(gx, gy)
            if g < 1e-4:
                continue
            sx, sy = -gx / g, -gy / g
            w = width / (1.0 + 0.6 * min(g, 3.0))
            pts = [(ax, ay, 0.07), (bx, by, 0.07), (bx + sx * w, by + sy * w, 0.06), (ax + sx * w, ay + sy * w, 0.06)]
            # Keep the strip's winding facing up.
            if (bx - ax) * (sy * w) - (by - ay) * (sx * w) < 0:
                pts = [pts[1], pts[0], pts[3], pts[2]]
            uv = [((p[0] + p[1]) / 4.0, 0.0 if k < 2 else 1.0) for k, p in enumerate(pts)]
            b.face(pts, 'foam', uv)
            count += 1
    return count
