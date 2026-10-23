"""Selected house geometry; no regional export orchestration."""
import math
import numpy as np
from houses.layout import BACK, HALF_W, HOUSES, front_y, to_world
from houses.geometry_mesh import DOOR_STEP, Mesh, R, variant

KERB, STEP_RISE, STEP_RUN = .45, .16, .36

class Ground:
    """The final heightmap (world.json's grid)."""

    def __init__(self, world, h):
        self.h = h; self.n = world['n']; self.size = world['size']; self.step = self.size / (self.n - 1)

    def low(self, x, y):
        """The lowest corner of the cell under (x, y): the terrain never shows below it."""
        fx = (x + self.size / 2) / self.step; fy = (y + self.size / 2) / self.step
        i = int(np.clip(math.floor(fx), 0, self.n - 2)); j = int(np.clip(math.floor(fy), 0, self.n - 2))
        return float(self.h[j:j + 2, i:i + 2].min())


def lot_mesh(lot, ground):
    m = Mesh(lot['name'], lot)
    spec = HOUSES[lot['variant']]; level = lot['level']
    F = np.array(lot['front'])                      # x, y, verge - level along the hedge line
    g0, g1 = lot['gate']; gx = (g0 + g1) / 2
    def yf(x): return float(front_y(lot, x))
    def low(lx, ly):
        wx, wy = to_world(lot, lx, ly); return ground.low(float(wx), float(wy)) - level

    # the lot top, from behind the kerb to the back edge (the terrain's ground)
    xs = sorted(set([float(v) for v in F[:, 0]] + [g0, g1]))
    for x0, x1 in zip(xs[:-1], xs[1:]):
        m.poly([(x0, yf(x0) + KERB, 0), (x1, yf(x1) + KERB, 0), (x1, BACK, 0), (x0, BACK, 0)], 'soil', slot=1, out=(0, 0, 1))
    # a gravel yard across the front, the moss garden bed with its edging stones, gravel drip lines under the eaves
    gcx, gcy = lot['garden']['centre']; grx, gry = lot['garden']['radii']; gs = 1 if gcx > 0 else -1
    hx0, hx1, hy0, hy1 = spec['walls']; rx0, rx1, ry0, ry1 = spec['roof']; yard_back = spec['ground'][2] + .1
    yard_x = np.linspace(*sorted([gcx - gs * (grx + .35), -gs * (HALF_W - .7)]), 9)
    for x0, x1 in zip(yard_x[:-1], yard_x[1:]):
        x0, x1 = float(x0), float(x1)
        m.poly([(x0, yf(x0) + KERB + .35, .015), (x1, yf(x1) + KERB + .35, .015), (x1, yard_back, .015), (x0, yard_back, .015)],
               variant('gravel', .025), out=(0, 0, 1))
    ring = [(gcx + grx * math.cos(a), gcy + gry * math.sin(a), .02) for a in np.linspace(0, math.tau, 17)[:-1]]
    m.poly(ring, 'moss', out=(0, 0, 1))
    for x, y, _ in ring[::2]:
        with m.at((x, y, 0), math.degrees(math.atan2(y - gcy, x - gcx)) + 90):
            m.box((0, 0, .04), (.55, .26, .16), variant('stone_light', .1), .04)
    for x0, x1, y0, y1 in ((rx0 + .2, rx1 - .2, hy1 + .05, min(ry1 - .15, BACK - .2)), (rx0 + .2, hx0 - .05, hy0, hy1 + .05),
                           (hx1 + .05, rx1 - .2, hy0, hy1 + .05)):
        if x1 - x0 > .2 and y1 - y0 > .2:
            m.poly([(x0, y0, .018), (x1, y0, .018), (x1, y1, .018), (x0, y1, .018)], variant('gravel', .04), out=(0, 0, 1))
    # stepping stones from the gate to the entrance step
    y, k = yf(gx) + KERB + .5, 0
    while y < DOOR_STEP[lot['variant']] - .45:
        with m.at((gx + (.14 if k % 2 else -.14), y, 0), R.uniform(-20, 20)):
            r = R.uniform(.40, .48)
            top = [(r * math.cos(a) * R.uniform(.85, 1.1), r * .8 * math.sin(a) * R.uniform(.85, 1.1)) for a in np.linspace(0, math.tau, 8)[:-1]]
            m.poly([(a, b, .07) for a, b in top], variant('stone', .1), out=(0, 0, 1))
            for (xa, ya), (xb, yb) in zip(top, top[1:] + top[:1]):
                m.poly([(xa, ya, .07), (xb, yb, .07), (xb, yb, -.05), (xa, ya, -.05)], 'stone_dark', out=(xa + xb, ya + yb, 0))
        y += .9; k += 1

    def pillow(q, out, bulge=.07, gap=.03, key='stone', amount=.16):
        """A rounded stone on a wall face: the quad q (corners in order) drawn in by `gap`, its middle pushed out."""
        Q = [np.array(p, float) for p in q]; c = sum(Q) / 4; o = np.array(out, float) / np.linalg.norm(out)
        Q = [p + (c - p) * min(.4, gap / max(np.linalg.norm(c - p), 1e-6)) + o * .015 for p in Q]
        top = c + o * bulge; col = variant(key, amount)
        for i in range(4): m.poly([Q[i], Q[(i + 1) % 4], top], col, out=o)

    # the stone kerb (rounded stones on a dark bed) and the clipped hedge on it, either side of the gate
    tops = {}
    for run in ([x for x in xs if x <= g0 + 1e-6], [x for x in xs if x >= g1 - 1e-6]):
        if len(run) < 2: continue
        dz = [float(np.interp(x, F[:, 0], F[:, 2])) for x in run]
        top = max(0, max(dz)) + .30
        for x in run: tops[x] = top
        for (xa, da), (xb, db) in zip(zip(run[:-1], dz[:-1]), zip(run[1:], dz[1:])):
            ya, yb = yf(xa), yf(xb)
            segs = max(1, int(round(math.hypot(xb - xa, yb - ya) / .55)))
            for s in range(segs):
                t0, t1 = s / segs, (s + 1) / segs
                x0, x1 = xa + (xb - xa) * t0, xa + (xb - xa) * t1; y0, y1 = ya + (yb - ya) * t0, ya + (yb - ya) * t1
                zb0, zb1 = min(da + (db - da) * t0, 0) - .3, min(da + (db - da) * t1, 0) - .3
                m.poly([(x0, y0, zb0), (x1, y1, zb1), (x1, y1, top), (x0, y0, top)], 'stone_dark', out=(0, -1, 0))
                course = (top + max(zb0, zb1)) / 2 + R.uniform(-.07, .07)
                split = R.uniform(.35, .65)
                xm, ym = x0 + (x1 - x0) * split, y0 + (y1 - y0) * split
                pillow([(x0, y0, max(zb0, -.1 + min(da, 0))), (x1, y1, max(zb1, -.1 + min(db, 0))), (x1, y1, course), (x0, y0, course)], (0, -1, 0))
                pillow([(x0, y0, course), (xm, ym, course), (xm, ym, top), (x0, y0, top)], (0, -1, 0))
                pillow([(xm, ym, course), (x1, y1, course), (x1, y1, top), (xm, ym, top)], (0, -1, 0))
                m.poly([(x0, y0, top), (x1, y1, top), (x1, y1 + KERB, top), (x0, y0 + KERB, top)], variant('stone_light', .08), out=(0, 0, 1))
                m.poly([(x0, y0 + KERB, top), (x1, y1 + KERB, top), (x1, y1 + KERB, -.05), (x0, y0 + KERB, -.05)], 'stone', out=(0, 1, 0))
        for x, cap in ((run[0], -1), (run[-1], 1)):
            if abs(x) > HALF_W - .01: continue           # a lot corner: the side wall closes it
            y0 = yf(x); base = min(0, float(np.interp(x, F[:, 0], F[:, 2]))) - .3
            m.poly([(x, y0, base), (x, y0 + KERB, base), (x, y0 + KERB, top), (x, y0, top)], 'stone', out=(cap, 0, 0))
        # hedge: a clipped, rounded profile swept along the kerb, its crown a little uneven
        shape = [(0, 0), (-.05, .30), (-.03, .50), (.05, .62), (.20, .67), (.36, .67), (.50, .62), (.58, .50), (.60, .30), (.55, 0)]
        rings = []
        for i, x in enumerate(run):
            end = i in (0, len(run) - 1)
            bump = 0 if end else R.uniform(-.035, .035); swell = 0 if end else R.uniform(-.025, .025)
            rings.append([(x, yf(x) + a - .05 + (swell * (1 if a < .25 else -1) if 0 < z < .6 else 0), top + z + (bump if z > .55 else 0))
                          for a, z in shape])
        for ra, rb in zip(rings[:-1], rings[1:]):
            for k in range(len(shape) - 1):
                (a0, z0), (a1, z1) = shape[k], shape[k + 1]
                up = (a1 - a0) / math.hypot(a1 - a0, z1 - z0)
                m.poly([ra[k], rb[k], rb[k + 1], ra[k + 1]], variant('hedge_light' if up > .6 else 'hedge', .06), out=(0, -(z1 - z0), (a1 - a0)))
        m.poly(rings[0], 'hedge', out=(-1, 0, 0)); m.poly(rings[-1], 'hedge', out=(1, 0, 0))
    # the gate: two square posts with caps, a threshold stone in the kerb and steps down to the verge
    dzg = lot['gate_verge']; yg = yf(gx)
    for x in (g0 - .12, g1 + .12):
        m.box((x, yf(x) + KERB / 2, .75), (.2, .2, 1.8), 'timber', .02)
        m.box((x, yf(x) + KERB / 2, 1.68), (.26, .26, .07), 'tile_edge', .02)
    m.box((gx, yg + KERB / 2, -.1), (g1 - g0 + .1, KERB + .1, .2), variant('stone_light', .05), .03)
    n = int(math.ceil(-dzg / STEP_RISE)) if dzg < -.02 else 0
    for k in range(1, n):
        zt = dzg * k / n
        m.box((gx, yg - STEP_RUN * (k - .5), (zt + dzg - .15) / 2), (g1 - g0 + .1, STEP_RUN + .02, zt - dzg + .15),
              variant('stone_light', .06), .04)

    # battered dry-stone walls down the sides and the back, to the ground of the final heightmap
    for (xa, ya), (xb, yb) in (((-HALF_W, yf(-HALF_W)), (-HALF_W, BACK)), ((-HALF_W, BACK), (HALF_W, BACK)),
                               ((HALF_W, BACK), (HALF_W, yf(HALF_W)))):
        length = math.hypot(xb - xa, yb - ya); dx, dy = (xb - xa) / length, (yb - ya) / length
        nx, ny = -dy, dx
        if nx * (xa + xb) + ny * (ya + yb) < 0: nx, ny = -nx, -ny          # outward
        cols = max(2, int(round(length / .85)))
        for c in range(cols):
            p0 = np.array([xa + (xb - xa) * c / cols, ya + (yb - ya) * c / cols])
            p1 = np.array([xa + (xb - xa) * (c + 1) / cols, ya + (yb - ya) * (c + 1) / cols])
            bottom = min(low(*(p0 + (nx * .5, ny * .5))), low(*(p1 + (nx * .5, ny * .5))), -.12) - .3
            courses = max(1, int(round(-bottom / .42)))
            def at(p, z, out=0.):     # a point on the face at height z (0: the lot level), leaning back as it rises
                k = -z * .16 + out
                return (float(p[0] + nx * k), float(p[1] + ny * k), z)
            m.poly([at(p0, bottom), at(p1, bottom), at(p1, 0), at(p0, 0)], 'stone_dark', out=(nx, ny, .1))
            for r_ in range(courses):
                z0 = bottom * (1 - r_ / courses); z1 = bottom * (1 - (r_ + 1) / courses)
                for f0, f1 in (((0, .55), (.55, 1.0)) if (c + r_) % 3 else ((0, 1.0),)):
                    a0 = p0 + (p1 - p0) * f0; a1 = p0 + (p1 - p0) * f1
                    pillow([at(a0, z0), at(a1, z0), at(a1, z1), at(a0, z1)], (nx, ny, 0), .08, .035)
            m.poly([at(p0, .03, .02), at(p1, .03, .02), at(p1, .03, -.3), at(p0, .03, -.3)], variant('stone_light', .08), out=(0, 0, 1))
            m.poly([at(p0, -.08, .03), at(p1, -.08, .03), at(p1, .03, .03), at(p0, .03, .03)], variant('stone_light', .08), out=(nx, ny, 0))
    for x in (-HALF_W, HALF_W):                    # the front corners: close the wall ends behind the kerb
        y0 = yf(x); s = 1 if x > 0 else -1
        bottom = min(low(x + s * .5, y0 + .5), -.12) - .3
        m.poly([(x, y0, bottom), (x, y0 + KERB, bottom), (x, y0 + KERB, tops.get(x, .3)), (x, y0, tops.get(x, .3))], 'stone', out=(s, 0, 0))
    return m
