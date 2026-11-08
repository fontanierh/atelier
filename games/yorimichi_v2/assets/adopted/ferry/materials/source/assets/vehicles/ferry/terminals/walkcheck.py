"""The terminal walk audit, independent of Blender: it marches a route and asks a ray caster about the geometry.

terminals/build.py drives it with a BVH of the kit, the ship at its berth and the exported world around the route;
tests/test_ferry_site.py drives it with TriangleCaster on small fixtures. One implementation either way.

A player is a capsule of radius RADIUS. Every 0.1 m along the route it needs: a floor within reach, a step to the
next floor of at most STEP_MAX, HEADROOM_MIN of headroom, WIDTH_MIN of clear width, at least RADIUS clear on each side
of the route line (at knee and chest height), and nothing across the way between samples at knee, waist or head
height, on the route line or RADIUS to either side of it.
"""
import math

import numpy as np

STEP_MAX, HEADROOM_MIN, WIDTH_MIN = 0.25, 2.1, 0.9     # metres
RADIUS = 0.22                                         # the player capsule
SAMPLE = 0.1


class TriangleCaster:
    """Nearest ray hit against a triangle soup (Moller-Trumbore), as BVHTree.ray_cast answers it: hit point or None."""

    def __init__(self, tris):
        self.a = np.asarray(tris, float)[:, 0]
        self.e1 = np.asarray(tris, float)[:, 1] - self.a
        self.e2 = np.asarray(tris, float)[:, 2] - self.a

    def __call__(self, o, d, dist):
        o, d = np.asarray(o, float), np.asarray(d, float)
        p = np.cross(d, self.e2); det = (self.e1 * p).sum(1)
        ok = np.abs(det) > 1e-12; inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - self.a; u = (s * p).sum(1) * inv
        q = np.cross(s, self.e1); v = (q * d).sum(1) * inv; t = (q * self.e2).sum(1) * inv
        hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t >= 0) & (t <= dist)
        if not hit.any():
            return None
        return tuple(o + d * t[hit].min())


def audit(route, cast):
    """route: [(x, y, z or None)], the first z the walking level; cast(origin, direction, distance) -> point or None."""
    pts = route; z = pts[0][2]; rows = []
    worst = {'max_step': 0.0, 'min_headroom': 99.0, 'min_width': 99.0, 'min_side_clearance': 99.0, 'no_floor': 0, 'blocked': 0}
    dn, up = (0.0, 0.0, -1.0), (0.0, 0.0, 1.0)
    for (ax, ay, _), (bx, by, _) in zip(pts, pts[1:]):
        L = math.hypot(bx - ax, by - ay); n = max(1, int(L / SAMPLE)); d = ((bx - ax) / L, (by - ay) / L, 0.0)
        side = (-d[1], d[0], 0.0)
        for k in range(n + 1):
            px, py = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
            hit = cast((px, py, z + 0.5), dn, 1.2)
            if hit is None:
                worst['no_floor'] += 1; rows.append({'at': [round(px, 2), round(py, 2)], 'issue': 'no floor'}); continue
            nz = hit[2]
            at = [round(px, 2), round(py, 2), round(nz, 3)]
            if k:                     # the capsule's path from the last sample: on the route line and at its sides
                bx_, by_ = px - d[0] * L / n, py - d[1] * L / n
                for off in (0.0, RADIUS, -RADIUS):
                    for hgt in (0.35, 0.95, 1.6):
                        o = (bx_ + side[0] * off, by_ + side[1] * off, z + hgt)
                        if cast(o, d, L / n) is not None:
                            worst['blocked'] += 1; rows.append({'at': at, 'issue': f'blocked at {hgt} m, {off:+.2f} m off the line'})
                            break
                    else:
                        continue
                    break
            step = nz - z; z = nz
            if abs(step) > worst['max_step']:
                worst['max_step'] = abs(step); worst['max_step_at'] = at
            h = cast((px, py, z + 0.05), up, 4.0)
            head = (h[2] - z) if h is not None else 4.0
            if head < worst['min_headroom']:
                worst['min_headroom'] = head; worst['min_headroom_at'] = at
            for hgt in (0.35, 1.2):
                o = (px, py, z + hgt); w = 0.0
                for s in (1, -1):
                    h = cast(o, (side[0] * s, side[1] * s, 0.0), 3.0)
                    gap = math.dist(h, o) if h is not None else 3.0
                    w += gap
                    if gap < worst['min_side_clearance']:
                        worst['min_side_clearance'] = gap; worst['min_side_clearance_at'] = at + [hgt]
                if w < worst['min_width']:
                    worst['min_width'] = w; worst['min_width_at'] = at + [hgt]
    worst = {k: round(v, 3) if isinstance(v, float) else v for k, v in worst.items()}
    worst['route'] = [[round(c, 3) if c is not None else None for c in p] for p in pts]
    worst['pass'] = (worst['max_step'] <= STEP_MAX and worst['min_headroom'] >= HEADROOM_MIN and worst['min_width'] >= WIDTH_MIN
                     and worst['min_side_clearance'] >= RADIUS and not worst['no_floor'] and not worst['blocked'])
    worst['end_z'] = round(z, 3)
    worst['issues'] = rows[:20]
    return worst
