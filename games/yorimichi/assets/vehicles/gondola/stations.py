"""Gondola station shells: Hidamari valley station (gondola_valley_station.jpg), Crater Park rim station
(gondola_rim_station.jpg) and the crater-floor station (gondola_crater_floor_station.jpg).

Station frame: the platform top is z = 0 and the bullwheel centre is the origin; the haul ropes leave along +x at
y = +-gauge/2 and the rope axis is at the cabin's grip height above the platform. Every station shares one core:
- a U-shaped platform round a pit (pit_depth deep) that the cabins swing through: straight channels along both ropes
  and a round end behind the bullwheel, sized from the cabin's swept plan with a 0.14 m margin;
- a berth on each side at x = berth_x, where the cabin's door (facing outward) meets a gate in the pit railing;
- the horizontal bullwheel at rope height on a drive column, with its gearbox above the hub, and the station's
  stretch of haul rope (round the wheel and out of the station mouth).
Each station dresses the core with its own buildings, roof, materials and access. build.py checks a cabin swept
round the whole loop against every station.
"""
import math
from contextlib import ExitStack, contextmanager

from mathutils import Matrix, Vector

import checks
import rope as RP
import solid
from cabin import GRIP, pose as cabin_pose
from solid import (BASALT, BOLT, CONCRETE, DECK, IRON, LAMP, PAINT, PANEL, PAVING, PLANK, PLASTER, POT, ROPE,
                   SHINGLE, SIGN, SOIL, STEEL, STONE, TILE, TIMBER, TIMBER_DARK, WINDOW, Mesh, circle, proxy, proxy_box,
                   proxy_strip, rect)

CABIN_T = 0.075
ROPE_DROP = 0.15       # the rope inside the station runs this far below the grip line
ATTACH_ZONE = 1.8      # from the mouth inwards: grips close on / open off the rope here


# ------------------------------------------------------------------ polygon helpers
def scan(poly, x):
    """Inside intervals of a simple polygon along the vertical line at x."""
    ys = []
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        if (x0 <= x < x1) or (x1 <= x < x0):
            ys.append(y0 + (y1 - y0) * (x - x0) / (x1 - x0))
    ys.sort()
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]


def offset_path(pts, d):
    """Offset an open polyline to its left by d (mitred)."""
    out = []; n = len(pts)
    for i in range(n):
        a = Vector(pts[max(i - 1, 0)]); b = Vector(pts[i]); c = Vector(pts[min(i + 1, n - 1)])
        t1 = (b - a).normalized() if i > 0 else (c - b).normalized()
        t2 = (c - b).normalized() if i < n - 1 else t1
        n1 = Vector((-t1.y, t1.x)); n2 = Vector((-t2.y, t2.x)); m = (n1 + n2)
        m = m / max(0.3, m.length) if m.length > 1e-9 else n1
        k = 1.0 / max(0.3, m.dot(n1))
        out.append(tuple(b + m.normalized() * d * k))
    return out


def path_len(pts):
    return sum((Vector(b) - Vector(a)).length for a, b in zip(pts[:-1], pts[1:]))


def point_at(pts, s):
    for a, b in zip(pts[:-1], pts[1:]):
        L = (Vector(b) - Vector(a)).length
        if s <= L + 1e-9:
            return tuple(Vector(a).lerp(Vector(b), s / L if L else 0)), (Vector(b) - Vector(a)).normalized()
        s -= L
    return tuple(pts[-1]), (Vector(pts[-1]) - Vector(pts[-2])).normalized()


def sub_path(pts, s0, s1):
    out = [point_at(pts, s0)[0]]; acc = 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        L = (Vector(b) - Vector(a)).length
        if s0 < acc + L - 1e-9 and acc + L < s1 - 1e-9:
            out.append(tuple(b))
        acc += L
    out.append(point_at(pts, s1)[0])
    return out


# ------------------------------------------------------------------ shared builders
def railing(m, st, pts, style, h=1.0, spacing=1.6, gaps=(), on=('platform',), label='rail post', z0=0.0, proxy_name='railing', embed=0.0):
    """Posts and rails along an open polyline (station plan), leaving gaps (s intervals along the path). z0 is the
    walking surface under the posts: a constant or a function f(x, y) (ramps and stairs)."""
    zf = z0 if callable(z0) else (lambda x, y, c=z0: c)
    total = path_len(pts); runs = []; s = 0.0
    for g0, g1 in sorted(gaps):
        if g0 > s:
            runs.append((s, g0))
        s = max(s, g1)
    if s < total:
        runs.append((s, total))
    post = 0.13 if style == 'timber' else 0.06
    for r0, r1 in runs:
        if r1 - r0 < 0.3:
            continue
        n = max(1, math.ceil((r1 - r0) / spacing)); posts = []
        for k in range(n + 1):
            p, t = point_at(pts, r0 + (r1 - r0) * k / n); posts.append((p, t, zf(p[0], p[1])))
        for p, t, z in posts:
            yaw = math.degrees(math.atan2(t.y, t.x))
            if style == 'timber':
                with m.at((p[0], p[1], z), yaw), m.grained((0, 0, 1)):
                    m.box((0, 0, (h + 0.08) / 2), (post, post, h + 0.08), TIMBER, bevel=0.012)
            else:
                m.lathe((p[0], p[1], z), [(0, 0.035), (h, 0.03), (h + 0.03, 0)], IRON, n=8)
            st.seat(label, p[0], p[1], z, embed=embed, on=on)
        for (a, ta, za), (b, tb, zb) in zip(posts[:-1], posts[1:]):
            for zr, w in (((h - 0.03, 0.09), (h * 0.5, 0.06)) if style == 'timber' else ((h - 0.02, 0.04), (h * 0.55, 0.03))):
                A = Vector((a[0], a[1], za + zr)); B = Vector((b[0], b[1], zb + zr)); dv = (B - A).normalized()
                if style == 'timber':
                    m.beam(A + dv * 0.04, B - dv * 0.04, w * 1.1, w, TIMBER, up=(0, 0, 1))
                else:
                    m.tube([A + dv * 0.02, B - dv * 0.02], w / 2, IRON, n=6)
        for (a, _, za), (b, _, zb) in zip(posts[:-1], posts[1:]):
            st.proxies.append(proxy_strip(proxy_name, a, b, 0.14, min(za, zb), max(za, zb) + h + 0.05))


def knee(m, base, direction, up, length, sect, mat=TIMBER, seg=5):
    """A curved knee brace: a quarter-ellipse bar from a post (base, going up) out along direction under a beam."""
    D = Vector(direction).normalized(); U = Vector(up).normalized(); path = []
    for k in range(seg + 1):
        a = (math.pi / 2) * k / seg
        path.append(tuple(Vector(base) + D * length * (1 - math.cos(a)) + U * length * math.sin(a)))
    m.tube(path, 1.0, mat, n=4, phase=math.pi / 4, sx=sect[0] * 1.414 / 2, sy=sect[1] * 1.414 / 2)


def slab_roof(m, x0, x1, half, z_eave, z_ridge, t, mat, rolls=None, ridge_mat=None, fascia=TIMBER, yc=0.0, tails=None, oni=False):
    """Gable roof of two sloped slabs (closed), ridge along x at yc, a ridge cap and barge boards, with optional
    dressing on top: 'tile' (kawara: rounded rolls down the slope over horizontal tile courses, round eave-tile ends)
    or 'courses' (shingle or plank courses). tails = spacing of exposed rafter tails under the eaves; oni = ridge-end
    onigawara blocks. Returns the slope's top-surface height function z(y)."""
    run = half; rise = z_ridge - z_eave; L = math.hypot(run, rise); nz = run / L; ny = rise / L

    def top(y):
        return z_ridge - rise * abs(y - yc) / run
    for s in (-1, 1):
        # quad cross-section: ridge top, eave top, eave bottom, ridge bottom (bottom offset along the slope normal)
        tr = (yc, z_ridge); te = (yc + s * half, z_eave)
        br = (yc, z_ridge - t / nz); be = (yc + s * half + s * t * ny, z_eave - t * nz)
        sec = [tr, te, be, br] if s > 0 else [tr, br, be, te]
        rings = [[(x, y, z) for y, z in sec] for x in (x0, x1)]
        m.loft(rings, mat)
    rm = ridge_mat or mat
    m.box(((x0 + x1) / 2, yc, z_ridge + 0.05), (x1 - x0 + 0.1, 0.36, 0.22), rm, bevel=0.04)
    if rolls == 'tile':
        m.lathe((x0 - 0.02, yc, z_ridge + 0.2), [(0, 0.1), (x1 - x0 + 0.04, 0.1)], rm, n=8, axis=(1, 0, 0))
    if oni:
        for x, d in ((x0 - 0.08, -1), (x1 + 0.08, 1)):
            m.box((x, yc, z_ridge + 0.2), (0.14, 0.46, 0.5), rm, bevel=0.05)
            m.box((x + d * 0.02, yc, z_ridge + 0.5), (0.12, 0.3, 0.14), rm, bevel=0.04)
    for x in (x0 - 0.04, x1 + 0.04):
        for s in (-1, 1):
            a = Vector((x, yc, z_ridge + 0.02)); b = Vector((x, yc + s * (half + 0.05), z_eave - 0.02))
            m.beam(a, b, 0.08 if s > 0 else 0.09, t + 0.12, fascia, up=(0, -s * rise, run))     # unequal widths: no shared faces at the ridge
    if rolls in ('tile', 'courses'):
        step = 0.3 if rolls == 'tile' else 0.42
        n = int(L / step)
        for k in range(1, n):
            f = k / n
            for s in (-1, 1):
                y = yc + s * half * f; z = top(y); nn = Vector((0, s * ny, nz))
                c = Vector(((x0 + x1) / 2, y, z)) + nn * 0.012
                with m.frame(c, Vector((1, 0, 0)), Vector((0, s * nz, -ny)) * -1, nn):
                    m.box((0, 0, 0), (x1 - x0 - 0.06, 0.05, 0.03), mat)
    if rolls == 'tile':
        n = int((x1 - x0) / 0.3)
        for k in range(n):
            x = x0 + (k + 0.5) * (x1 - x0) / n
            for s in (-1, 1):
                a = Vector((x, yc + s * 0.18, top(yc + s * 0.18))); b = Vector((x, yc + s * (half - 0.02), top(yc + s * (half - 0.02))))
                nn = Vector((0, s * ny, nz)); a += nn * 0.04; b += nn * 0.04
                m.tube([a, b], 0.07, mat, n=6, phase=0.3)
                d = (b - a).normalized()
                m.lathe(tuple(b - d * 0.01), [(0, 0.085), (0.035, 0.085)], rm, n=8, axis=tuple(d))
    if tails:
        d = 0.14; w = 0.1
        n = max(2, int((x1 - x0 - 0.5) / tails))
        for k in range(n + 1):
            x = x0 + 0.25 + (x1 - x0 - 0.5) * k / n
            for s in (-1, 1):
                nn = Vector((0, s * ny, nz))
                ya, yb = half - 1.0, half + 0.16
                za = top(yc + s * ya) - t / nz; zb = z_ridge - rise * yb / run - t / nz
                pa = Vector((x, yc + s * ya, za)) - nn * (d / 2 - 0.01); pb = Vector((x, yc + s * yb, zb)) - nn * (d / 2 - 0.01)
                m.beam(pa, pb, w, d, fascia, up=tuple(nn))
    return top


def irimoya_roof(m, X0, X1, yc, half, ze, zr, t, g, mat, rm, gable_mat, fascia=TIMBER_DARK, tails=0.6, no_tails=()):
    """Hip-and-gable (irimoya) tiled roof, one closed solid: front and back slopes from the eaves (X0..X1, yc +- half)
    to a ridge g shorter at each end, hipped end slopes rising g inward from the end eaves, and a small vertical gable
    (in gable_mat) above each hip under the ridge end. Dressing: kawara courses on all slopes and rolls on the long
    slopes, a ridge cap with onigawara over the gables, barge boards on the gables and rafter tails under the long
    eaves' flat soffit, except on the front (-y) eave over the x ranges in no_tails, where a porch roof meets it."""
    Y0, Y1 = yc - half, yc + half; rise = zr - ze
    zg = ze + rise * g / half                       # the gables' base: where the hips meet them
    w = half * (zr - zg) / rise                      # the gables' half width
    V = [(X0, Y0, ze), (X1, Y0, ze), (X1, Y1, ze), (X0, Y1, ze),
         (X1 - g, yc - w, zg), (X1 - g, yc + w, zg), (X0 + g, yc - w, zg), (X0 + g, yc + w, zg),
         (X1 - g, yc, zr), (X0 + g, yc, zr),
         (X0, Y0, ze - t), (X1, Y0, ze - t), (X1, Y1, ze - t), (X0, Y1, ze - t)]
    F = [(0, 1, 4, 8, 9, 6), (2, 3, 7, 9, 8, 5), (1, 2, 5, 4), (3, 0, 6, 7), (4, 5, 8), (7, 6, 9),
         (10, 11, 1, 0), (11, 12, 2, 1), (12, 13, 3, 2), (13, 10, 0, 3), (10, 13, 12, 11)]
    m.part(V, F, [mat, mat, mat, mat, gable_mat, gable_mat, fascia, fascia, fascia, fascia, fascia])
    L = math.hypot(half, rise); ny, nz = rise / L, half / L
    m.box(((X0 + X1) / 2, yc, zr + 0.05), (X1 - X0 - 2 * g + 0.1, 0.36, 0.22), rm, bevel=0.04)
    m.lathe((X0 + g - 0.02, yc, zr + 0.2), [(0, 0.1), (X1 - X0 - 2 * g + 0.04, 0.1)], rm, n=8, axis=(1, 0, 0))
    for x, d in ((X0 + g - 0.1, -1), (X1 - g + 0.1, 1)):
        m.box((x, yc, zr + 0.2), (0.14, 0.46, 0.5), rm, bevel=0.05)
        m.box((x + d * 0.02, yc, zr + 0.5), (0.12, 0.3, 0.14), rm, bevel=0.04)
        for s in (-1, 1):                            # barge boards on the small gable
            a = Vector((x - d * 0.04, yc, zr + 0.02)); b = Vector((x - d * 0.04, yc + s * (w + 0.06), zg - 0.03))
            m.beam(a, b, 0.08 if s > 0 else 0.09, 0.22, fascia, up=(0, -s * rise, half))
    # Courses on the long slopes and the hips, rolls down the long slopes inside the hip lines.
    n = int(L / 0.3)
    for k in range(1, n):
        f = k / n; z = ze + rise * f
        xi = g * min(1.0, (z - ze) / max(1e-6, zg - ze))          # the hip line's inset at this height
        for s in (-1, 1):
            y = yc + s * half * (1 - f); nn = Vector((0, s * ny, nz)); c = Vector(((X0 + X1) / 2, y, z)) + nn * 0.012
            with m.frame(c, Vector((1, 0, 0)), Vector((0, s * nz, -ny)) * -1, nn):
                m.box((0, 0, 0), (X1 - X0 - 2 * xi - 0.06, 0.05, 0.03), mat)
        if z < zg - 0.05:
            yw = half - (half - w) * (z - ze) / (zg - ze)          # the end slope's width at this height
            for X, s in ((X0, -1), (X1, 1)):
                hn = Vector((s * (zg - ze), 0, g)).normalized(); x = X - s * g * (z - ze) / (zg - ze)
                c = Vector((x, yc, z)) + hn * 0.012
                with m.frame(c, Vector((0, 1, 0)), hn.cross(Vector((0, 1, 0))), hn):
                    m.box((0, 0, 0), (2 * yw - 0.1, 0.05, 0.03), mat)
    nr = int((X1 - X0 - 2 * g) / 0.3)
    for k in range(nr):
        x = X0 + g + (k + 0.5) * (X1 - X0 - 2 * g) / nr
        for s in (-1, 1):
            a = Vector((x, yc + s * 0.18, zr - rise * 0.18 / half)); b = Vector((x, yc + s * (half - 0.02), ze + rise * 0.02 / half))
            nn = Vector((0, s * ny, nz)); a += nn * 0.04; b += nn * 0.04
            m.tube([a, b], 0.07, mat, n=6, phase=0.3)
            dd = (b - a).normalized()
            m.lathe(tuple(b - dd * 0.01), [(0, 0.085), (0.035, 0.085)], rm, n=8, axis=tuple(dd))
    if tails:
        nt = max(2, int((X1 - X0 - 0.5) / tails))
        for k in range(nt + 1):
            x = X0 + 0.25 + (X1 - X0 - 0.5) * k / nt
            porch = any(a - 0.06 <= x <= b + 0.06 for a, b in no_tails)
            for s in ((1,) if porch else (-1, 1)):
                ya, yb = half - 1.0, half - 0.05          # level under the flat soffit, tops let 10 mm into it
                m.beam((x, yc + s * ya, ze - t - 0.06), (x, yc + s * yb, ze - t - 0.06), 0.1, 0.14, fascia, up=(0, 0, 1))


def bench(m, st, x, y, yaw, length=1.8, on=('platform',), z0=0.0):
    with m.at((x, y, z0), yaw):
        for k in range(3):
            m.box((0, -0.16 + k * 0.15, 0.44), (length, 0.13, 0.05), TIMBER, bevel=0.008)
        for k in range(2):
            m.box((0, 0.22, 0.6 + k * 0.17), (length, 0.035, 0.12), TIMBER, bevel=0.006)
        for sx in (-1, 1):
            m.box((sx * (length / 2 - 0.2), 0.0, 0.2075), (0.06, 0.46, 0.415), IRON)
            m.box((sx * (length / 2 - 0.2), 0.21, 0.615), (0.05, 0.03, 0.41), IRON)
    c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    for sx in (-1, 1):
        for sy in (-1, 1):
            u, v = sx * (length / 2 - 0.2), sy * 0.2
            st.seat('bench leg', x + c * u - s_ * v, y + s_ * u + c * v, z0, on=on)
    st.proxies.append(proxy_box('bench', x, y, length, 0.6, z0, z0 + 0.82, yaw))


def lantern(m, c, h=0.42):
    x, y, z = c
    m.box((x, y, z + 0.02), (0.22, 0.22, 0.04), IRON)
    m.box((x, y, z + 0.04 + h / 2), (0.16, 0.16, h), LAMP)
    m.lathe((x, y, z + 0.04 + h), [(0, 0.17), (0.06, 0.12), (0.12, 0.0)], IRON, n=4, phase=math.pi / 4)


def stone_course(m, pts, z0, z1, depth, seed, mat=BASALT, size=0.45):
    """Rounded stones proud of a wall face along an open polyline (outward = right of the path)."""
    import random
    rnd = random.Random(seed); total = path_len(pts); rows = max(1, int((z1 - z0) / (size * 0.75)))
    for r in range(rows):
        zc = z0 + (r + 0.5) * (z1 - z0) / rows; s = (r % 2) * size * 0.5
        while s < total - size * 0.3:
            p, t = point_at(pts, s); nrm = Vector((t.y, -t.x, 0))
            k = 0.75 + 0.5 * rnd.random()                     # stones of mixed size and colour, not a uniform course
            c = Vector((p[0], p[1], zc + (rnd.random() - 0.5) * 0.12 * size)) + nrm * (depth * 0.25)
            sz = (size * k * (0.42 + 0.14 * rnd.random()), size * (0.36 + 0.1 * rnd.random()), (z1 - z0) / rows * (0.40 + 0.14 * rnd.random()))
            yaw = math.degrees(math.atan2(t.y, t.x)) + rnd.uniform(-12, 12)
            with m.at(tuple(c), yaw):
                m.rock((0, 0, 0), (sz[0], depth * 0.32, sz[2]), STONE if rnd.random() < 0.55 else mat, seed=rnd.randrange(1 << 30), n=7, m=4)
            s += size * k * (0.85 + 0.2 * rnd.random())


def stone_pier(m, x, y, w=0.9, top=1.20, z0=-0.04, courses=4, seed=0):
    """Dressed stone pier: squared blocks in staggered courses round a core, under a bevelled cap stone (tag the
    caller's choice). Blocks on the x faces run the full width; those on the y faces stop 5 mm short of them, and
    every block has its own height, so no two faces are coplanar."""
    import random
    rnd = random.Random(seed); c = w - 0.1; cap_t = 0.12; zc = top - cap_t
    m.box((x, y, (z0 + zc + 0.04) / 2), (c, c, zc + 0.04 - z0), STONE)
    m.box((x, y, top - cap_t / 2), (w + 0.05, w + 0.05, cap_t), STONE, bevel=0.03)
    h = (zc - 0.01 - (z0 + 0.015)) / courses
    for r in range(courses):
        za = z0 + 0.015 + r * h
        for axis in (0, 1):
            for sgn in (-1, 1):
                split = 0.45 + 0.1 * rnd.random() if (r + axis) % 2 else 1.0
                span = w if axis == 0 else c - 0.07
                edges = [-span / 2, -span / 2 + span * split, span / 2] if split < 1.0 else [-span / 2, span / 2]
                for a, b in zip(edges[:-1], edges[1:]):
                    a2, b2 = a + 0.006, b - 0.006
                    zb = za + 0.004 + 0.006 * rnd.random(); zt = za + h - 0.008 - 0.006 * rnd.random()
                    n0, n1 = c / 2 - 0.03, w / 2 - 0.004 * rnd.random()
                    if axis == 0:
                        cx, cy, sx, sy = x + sgn * (n0 + n1) / 2, y + (a2 + b2) / 2, n1 - n0, b2 - a2
                    else:
                        cx, cy, sx, sy = x + (a2 + b2) / 2, y + sgn * (n0 + n1) / 2, b2 - a2, n1 - n0
                    m.box((cx, cy, (zb + zt) / 2), (sx, sy, zt - zb), STONE if rnd.random() < 0.6 else BASALT, bevel=0.018)


# ------------------------------------------------------------------ station
class Station:
    MOUTH_WIDEN = 0.05      # the channel through a mouth wall: this much wider each side than the pit (m)

    def __init__(self, key, p, d):
        self.key = key; self.p = p; self.d = d
        self.R = p['gauge'] / 2; self.HL, self.HW = p['cabin_length'] / 2, p['cabin_width'] / 2
        self.Zr = d['rope_height_above_platform']; self.pit = p['pit_depth']; self.xb = p['berth_x']
        self.YP = self.R + self.HW + 0.10
        self.RP = math.hypot(self.R + self.HW, self.HL) + 0.14
        self.xt = math.sqrt(self.RP ** 2 - self.YP ** 2)
        self.XM, self.XB, self.YO = 7.6, -7.6, 7.6
        self.seats = []; self.proxies = []; self.levels = []; self.stairs = []; self.access = []; self.surfaces = []; self.points = {}
        self.base = -0.6                  # platform slab bottom
        self.deck = False                 # timber decking boards over the slab
        self.slabs = []                   # (name, polygon) walkable, for the walk layout
        self.slab_z = {}                  # slab name -> its walking height, a value or z(x, y) (absent: z = 0)

    def seat(self, label, x, y, z, embed=0.0, probe=0.15, on=('platform',)):
        self.seats.append((label, round(x, 4), round(y, 4), round(z, 4), embed, probe, tuple(on)))

    @contextmanager
    def shifted(self, dx, *meshes):
        """Build inside a frame moved dx along x: the meshes, and the seats and proxies recorded meanwhile."""
        n_s, n_p = len(self.seats), len(self.proxies)
        with ExitStack() as es:
            for m in meshes:
                es.enter_context(m.at((dx, 0, 0)))
            yield
        self.seats[n_s:] = [(lb, round(x + dx, 4), *rest) for lb, x, *rest in self.seats[n_s:]]
        for pr in self.proxies[n_p:]:
            pr['poly'] = [[round(x + dx, 4), y] for x, y in pr['poly']]

    # ---------------------------------------------------------------- core plan
    def arc(self, a0, a1, n=28):
        return [(self.RP * math.cos(a0 + (a1 - a0) * k / n), self.RP * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]

    def angles(self):
        a = math.atan2(self.YP, self.xt)
        return a, 2 * math.pi - a

    def pit_poly(self):
        a1, a2 = self.angles()
        return [(self.xt, -self.YP), (self.XM, -self.YP), (self.XM, self.YP)] + self.arc(a1, a2)[:-1]

    def pit_edge(self):
        """The pit's edge as an open path from the -y mouth round the back to the +y mouth (pit on the right)."""
        a1, a2 = self.angles()
        return [(self.XM, -self.YP)] + self.arc(a2, a1) + [(self.XM, self.YP)]

    def platform_poly(self, extra_bottom=(), extra_left=(), extra_top=()):
        a1, a2 = self.angles(); YO, XM, XB = self.YO, self.XM, self.XB
        bottom = sorted([(x, -YO) for x in extra_bottom], key=lambda q: -q[0])
        top = sorted([(x, YO) for x in extra_top], key=lambda q: q[0])
        left = sorted([(XB, y) for y in extra_left], key=lambda q: q[1])
        poly = [(XM, -YO), (XM, -self.YP)] + self.arc(a2, a1) + [(XM, self.YP), (XM, YO)] + top[::-1] + [(XB, YO)] + left[::-1] + [(XB, -YO)] + bottom[::-1]
        return poly

    def platform_proxies(self, top=0.0):
        """Convex pieces of the U platform (walk level), from the same arc samples."""
        a1, a2 = self.angles(); P = []; YO = self.YO
        P.append(proxy('platform', rect(self.XB, -YO, -self.RP, YO), self.base, top))
        for s in (-1, 1):
            P.append(proxy('platform', rect(self.xt, self.YP, self.XM, YO) if s > 0 else rect(self.xt, -YO, self.XM, -self.YP), self.base, top))
        up = self.arc(a1, math.pi, 14); lo = self.arc(math.pi, a2, 14)
        for pts, s in ((up, 1), (lo, -1)):
            for (xa, ya), (xb_, yb) in zip(pts[:-1], pts[1:]):
                P.append(proxy('platform', [(xa, ya), (xb_, yb), (xb_, s * YO), (xa, s * YO)], self.base, top))
        return P

    def core(self, plat, mach, fit, slab_mat=PAVING, rail_style='metal', top_mat=None):
        base, pit = self.base, self.pit
        ptop = 0.0
        poly = self.platform_poly(*self.joins())
        with plat.tagged('platform'):
            plat.prism(poly, base, ptop, slab_mat, top=top_mat or slab_mat)
        with plat.tagged('pit'):
            plat.prism(self.pit_poly(), base, -pit, CONCRETE)
        self.slabs.append(('platform', poly))
        # Steel edge along the pit, proud of the platform by 6 mm.
        edge = self.pit_edge(); inner = offset_path(edge, 0.1)
        with fit.tagged('platform edge'):           # part of the boarding interface (gap gated in walk.py)
            fit.band(edge, inner, ptop, 0.006, PAINT)
        # Railing along the pit, open at both berths.
        rail_line = offset_path(edge, 0.26); total = path_len(rail_line)
        g = []
        for s in (-1, 1):
            # arc length along the rail line of x = berth +- 0.8 on each straight
            for xa, xb_ in ((self.xb - 0.8, self.xb + 0.8),):
                if s < 0:
                    g.append((self.XM - xb_, self.XM - xa))
                else:
                    g.append((total - (self.XM - xa), total - (self.XM - xb_)))
        railing(fit, self, rail_line, rail_style, gaps=g, label='pit railing post', z0=0.0)
        self.gates = [{'side': s, 'x': [self.xb - 0.8, self.xb + 0.8], 'y_edge': s * self.YP} for s in (-1, 1)]
        self.machinery(mach)

    def joins(self):
        return (), (), ()

    def machinery(self, m):
        """Drive column, bullwheel and gearbox, the station's stretch of haul rope (rope.station_loop: it drops
        rope_drop below the grip line inside the mouth, away from the opened grips), the running rail the detached
        grips roll on, and the overhead frame that carries the rail from the inside of the loop."""
        Zr, R, pit, rr = self.Zr, self.R, self.pit, self.p['rope_radius']
        Zs = Zr - ROPE_DROP; self.Zs = Zs
        with m.tagged('column'):
            m.prism(solid.rounded_rect(1.5, 1.5, 0.25, 3), -pit + 0.15, Zs - 0.45, STEEL, bevel=0.03)
        self.seat('drive column', 0.5, 0.5, -pit + 0.15, embed=0.01, on=('plinth',))
        with m.tagged('plinth'):
            m.box((0, 0, -pit + 0.08), (1.9, 1.9, 0.16), CONCRETE, bevel=0.02)
        self.seat('drive plinth', 0.85, 0.85, -pit, on=('pit',))
        for k in range(4):
            a = math.pi / 4 + k * math.pi / 2
            m.box((0.8 * math.cos(a), 0.8 * math.sin(a), -pit + 0.17), (0.07, 0.07, 0.02), BOLT)
        m.lathe((0, 0, Zs - 0.45), [(0, 0.5), (0.7, 0.5)], IRON, n=16)
        rim_o, rim_i = R - rr, R - 0.2
        with m.tagged('bullwheel groove'):     # the rope's intentional contact (gated as one seated part)
            m.ring_prism(circle(rim_o, 48), circle(rim_i, 48), Zs - 0.30, Zs, IRON)
        with m.tagged('bullwheel flange'):     # the lower flange: unrelated hardware (rope clearance)
            m.ring_prism(circle(R + 0.03, 48), circle(R - 0.15, 48), Zs - 0.32, Zs - 0.26, STEEL)
        m.ring_prism(circle(1.75, 32), circle(1.6, 32), Zs - 0.22, Zs - 0.08, IRON)
        for k in range(8):
            a = 2 * math.pi * (k + 0.5) / 8
            m.beam((0.42 * math.cos(a), 0.42 * math.sin(a), Zs - 0.15), ((rim_i + 0.05) * math.cos(a), (rim_i + 0.05) * math.sin(a), Zs - 0.15), 0.12, 0.18, STEEL)
        m.box((0, 0, Zs + 0.25 + 0.35), (1.4, 1.0, 0.7), STEEL, bevel=0.04)
        m.box((0.85, 0, Zs + 0.25 + 0.3), (0.5, 0.6, 0.5), IRON, bevel=0.03)
        m.lathe((0, 0, Zs + 0.21), [(0, 0.3), (0.1, 0.3)], IRON, n=12)
        # Haul rope: the single rope path of the station (also used for the grip checks at the mouth).
        self.rope = RP.station_loop(R, Zr, Zs, self.XM, rr)
        with m.tagged('rope'):
            m.tube(self.rope.resampled(0.15), rr, ROPE, n=8)
        self.rail_and_frame(m)

    def rail_and_frame(self, m):
        """Running rail under the grips' wheels (cabin.GRIP), round the loop at the grip line, and its frame."""
        Zr, R, pit = self.Zr, self.R, self.pit; g = GRIP
        rc = -g['wheel_y']; half = g['wheel_width'] / 2 + 0.01
        r_in, r_out = R + rc - half, R + rc + half
        top, bot = Zr + g['wheel_z'] - g['wheel_radius'], Zr + g['rail_bottom_z']
        self.rail = {'centre_offset': round(rc, 3), 'width': round(2 * half, 3), 'top_z': round(top, 4), 'bottom_z': round(bot, 4)}

        def line(r, n=36):
            pts = [(self.XM + 0.3, -r), (0.0, -r)]
            pts += [(r * math.cos(-math.pi / 2 - math.pi * k / n), r * math.sin(-math.pi / 2 - math.pi * k / n)) for k in range(1, n)]
            return pts + [(0.0, r), (self.XM + 0.3, r)]
        with m.tagged('rail'):
            m.band(line(r_out), line(r_in), bot, top, STEEL)
        # Hangers from the overhead frame: connector under the wheel path, a drop plate outside it, an arm over it.
        za0, za1 = Zr + 0.57, Zr + 0.73
        hangs = [(x, s) for x in (1.4, 3.6, 5.8, 7.6) for s in (-1, 1)]
        for x, s in hangs:
            with m.at((x, 0, 0), 0 if s < 0 else 180):
                self.hanger_bracket(m, R, r_out, bot, za0, za1)
        for x in (1.4, 3.6, 5.8, 7.6):
            m.box((x, 0, (za0 + za1) / 2), (0.16, 2 * (r_out + 0.11), za1 - za0), IRON)
        for ang in (135, 180, 225):
            with m.at((0, 0, 0), ang + 90):
                self.hanger_bracket(m, R, r_out, bot, za0, za1)
                m.box((0, -(0.6 + r_out + 0.11) / 2, (za0 + za1) / 2), (0.16, r_out + 0.11 - 0.6, za1 - za0), IRON)
        # Spine along the line centre from the gearbox to the mouth, on two posts standing in the pit.
        m.box(((self.XM + 0.1) / 2, 0, Zr + 0.65), (self.XM + 0.1, 0.24, 0.2), STEEL, bevel=0.01)
        for x in (2.5, 4.7):
            with m.tagged('frame post'):
                m.box((x, 0, (-pit + 0.01 + Zr + 0.56) / 2), (0.3, 0.3, Zr + 0.56 + pit - 0.01), STEEL, bevel=0.01)
            m.box((x, 0, -pit + 0.015), (0.5, 0.5, 0.03), IRON)
            self.seat('rail frame post', x + 0.1, 0.1, -pit, on=('pit',))
        self.proxies.append(proxy('rail frame', rect(-0.8, -(r_out + 0.12), self.XM + 0.3, r_out + 0.12), Zr + 0.5, Zr + 0.8))

    def hanger_bracket(self, m, R, r_out, bot, za0, za1):
        """In a frame whose -y axis points outward across the rail (rail outer face at y = -r_out)."""
        m.box((0, -(r_out + 0.03), bot + 0.045), (0.12, 0.07, 0.07), IRON)                      # connector
        m.box((0, -(r_out + 0.075), (bot - 0.02 + za1 - 0.03) / 2), (0.14, 0.03, za1 - 0.01 - bot), IRON)  # drop plate
        for z in (bot + 0.035, za0 + 0.05):
            m.box((0, -(r_out + 0.093), z), (0.04, 0.012, 0.04), BOLT)

    # ---------------------------------------------------------------- deck boards over a slab
    def boards(self, m, poly, width=0.19, gap=0.012, margin=0.03, along='y', mat=DECK, tag='platform'):
        """Decking boards over the substrate (top -0.03 to 0): strips across x, each cut to the polygon on both of
        its edges so it never overhangs."""
        xs = [p[0] for p in poly]; x = min(xs) + margin
        with m.tagged(tag):
            while x + width < max(xs) - margin:
                a = scan(poly, x + 1e-4); b = scan(poly, x + width - 1e-4)
                for (y0, y1) in a:
                    for (u0, u1) in b:
                        lo, hi = max(y0, u0) + margin, min(y1, u1) - margin
                        if hi - lo > 0.2:
                            m.box((x + width / 2, (lo + hi) / 2, -0.015), (width, hi - lo, 0.03), mat)
                x += width + gap

    # ---------------------------------------------------------------- swept cabin placements and berths
    def grip_line(self):
        """The grips' path through the station (the rail line, not the dropped rope), as a RopePath."""
        return RP.station_loop(self.R, self.Zr, self.Zr, self.XM, self.p['rope_radius'])

    def placements(self, step=0.2):
        """Cabin frames round the loop from the grip line (rope.grip_frame), door side outward; each has a flag for
        the attach zone (grip on the rope, which is then excluded from the clearance check)."""
        path = self.grip_line(); out = []; n = int(path.length / step)
        for k in range(n + 1):
            s_ = path.length * k / n; q = path.rope_point(s_)
            if q[0] < 0:
                ln = math.hypot(q[0], q[1]); outward = (q[0] / ln, q[1] / ln, 0)
            else:
                outward = (0, 1 if q[1] > 0 else -1, 0)
            attach = q[0] > self.XM - ATTACH_ZONE
            out.append((f's {s_:.1f} ({q[0]:.1f}, {q[1]:.1f})', cabin_pose(path.grip_frame(s_, outward)), attach))
        return out

    def line_frames(self):
        """Grip frames on the haul rope past the mouth (clamped): for the jaw-groove check."""
        path = self.rope; out = []
        for side in (-1, 1):
            for x in (self.XM + 0.15, self.XM + 0.25, self.XM + 0.35):     # the housing (+-0.2 m) stays on the modelled rope
                s_ = self.rope_s(x, side)
                out.append((f'mouth x {x:.1f} side {side}', Matrix(path.grip_frame(s_, (0, side, 0))), s_))
        return out

    def rope_s(self, x, side):
        """Arc length on the station rope at x on a straight (side -1 is the start of the path)."""
        path = self.rope; x0 = self.XM + 0.6
        if side < 0:
            return x0 - x
        return path.length - (x0 - x)

    def berth(self, side):
        """Cabin transform in the berth on side -1 (y < 0) or +1."""
        M = Matrix.Translation((self.xb, side * self.R, self.Zr))
        return M if side < 0 else M @ Matrix.Rotation(math.pi, 4, 'Z')

    def attachment(self):
        R = self.R
        return {'frame': 'platform top z = 0, bullwheel centre at the origin, line leaves along +x',
                'rope_height': round(self.Zr, 3), 'rope_height_in_station': round(self.Zs, 3),
                'bullwheel': {'centre': [0, 0, round(self.Zs, 3)], 'rope_radius': R}, 'running_rail': self.rail,
                'rope_exits': [[round(self.XM + 0.6, 3), s * R, round(self.Zr, 3)] for s in (-1, 1)],
                'station_mouth_x': self.XM,
                'berths': [{'side': s, 'cabin_grip': [self.xb, s * R, round(self.Zr, 3)], 'cabin_yaw_deg': 0 if s < 0 else 180,
                            'door_outward': [0, s, 0], 'door_centre': [self.xb, round(s * (R + self.HW), 3), round(self.p['berth_floor_step'], 3)],
                            'platform_edge': {'y': round(s * self.YP, 3), 'x': [round(self.xb - 0.8, 3), round(self.xb + 0.8, 3)], 'z': 0.0},
                            'gap_door_to_edge_m': round(self.YP - R - self.HW, 3), 'door_clear_width': self.p['door_clear_width']} for s in (-1, 1)],
                'pit': {'depth': self.pit, 'straight_half_width': round(self.YP, 3), 'turn_radius': round(self.RP, 3)},
                'platform_extent': {'x': [self.XB, self.XM], 'y': [-self.YO, self.YO]}, 'access': self.access}

    def walk_layout(self, cabin):
        """Walk layout: the platform level with both berths occupied by a cabin, doors open."""
        lay = cabin.layout(); region = [list(map(list, poly)) for _, poly in self.slabs]
        cab_px = cabin.proxies(); P = list(self.proxies) + self.platform_proxies()
        for s in (-1, 1):
            M = self.berth(s)
            for pr in cab_px:
                if pr['name'] == 'cabin floor':
                    continue
                P.append(solid.proxy_transform(pr, M))
            interior = [tuple((M @ Vector((x, y, 0))).xy) for x, y in lay['interior']]
            region.append([list(p) for p in interior])
            x0, x1 = self.xb - cabin.dw / 2, self.xb + cabin.dw / 2
            y0, y1 = sorted((s * (self.R + self.HW - CABIN_T - 0.01), s * (self.YP + 0.02)))
            region.append([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        return region, P


# ------------------------------------------------------------------ timber framing shared by the dressings
def roof_under(z_ridge, z_eave, half, t, y):
    """Underside height of a slab_roof slope at horizontal distance y from the ridge."""
    rise = z_ridge - z_eave; nz = half / math.hypot(half, rise)
    return z_ridge - rise * y / half - t / nz


def eave_for(z_ridge, half, t, y, z_bottom):
    """The eave height that puts a slab_roof's underside at z_bottom, y from the ridge (bisection on the rise)."""
    lo, hi = 0.01, 30.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if roof_under(z_ridge, z_ridge - mid, half, t, y) > z_bottom:
            lo = mid
        else:
            hi = mid
    return z_ridge - (lo + hi) / 2


def canopy(m, st, xs, yp, post, z_foot, z_tie, x_ext, roof, label, on=('platform',), yc=0.0, foot_embed=0.0, roof_kw=None,
           infill=(), knee_sect=0.14, knee_len=0.8):
    """Timber frame of posts on two lines (y = yc +- yp), tie beams, plates, king posts, rafters, struts and knee
    braces under a slab_roof. roof = (x0, x1, half, z_ridge, t, material, rolls). Returns the roof's z_eave."""
    x0, x1, half, z_ridge, t, rmat, rolls = roof
    z_eave = eave_for(z_ridge, half, t, yp + 0.0, z_tie + 0.32)

    def under(y):
        return roof_under(z_ridge, z_eave, half, t, abs(y))
    rise = z_ridge - z_eave; L = math.hypot(half, rise); ny, nz = rise / L, half / L
    for x in xs:
        for s in (-1, 1):
            y = yc + s * yp
            with m.grained((0, 0, 1)):
                m.box((x, y, (z_foot + z_tie + 0.05) / 2), (post, post, z_tie + 0.05 - z_foot), TIMBER, bevel=0.015)
            st.seat(label, x, y, z_foot, embed=foot_embed, on=on)
            st.proxies.append(proxy_box(label, x, y, post + 0.04, post + 0.04, z_foot, z_tie))
            # knee braces: post to tie beam (across) and post to plate (along), inward only at the ends
            Lk = knee_len
            knee(m, (x, y - s * post / 2, z_tie - 0.30 - Lk), (0, -s, 0), (0, 0, 1), Lk, (knee_sect, knee_sect))
            for d in (-1, 1):
                if (d < 0 and x == min(xs)) or (d > 0 and x == max(xs)):
                    continue
                knee(m, (x + d * post / 2, y, z_tie - 0.01 - Lk), (d, 0, 0), (0, 0, 1), Lk, (knee_sect, knee_sect))
        m.beam((x, yc - yp - 0.35, z_tie - 0.15), (x, yc + yp + 0.35, z_tie - 0.15), 0.24, 0.30, TIMBER, up=(0, 0, 1))
        m.box((x, yc, (z_tie + under(0) + 0.05) / 2), (0.22, 0.22, under(0) + 0.05 - z_tie), TIMBER)
        for s in (-1, 1):
            nrm = Vector((0, s * ny, nz)); d = 0.22
            a = Vector((x, yc + s * (yp + 0.1), under(yp + 0.1))) - nrm * (d / 2 - 0.02)
            b = Vector((x, yc + s * 0.08, under(0.08))) - nrm * (d / 2 - 0.02)
            m.beam(a, b, 0.16 if s < 0 else 0.17, d, TIMBER, up=tuple(nrm))     # unequal: no shared faces at the apex
            ys = half * 0.42
            m.beam((x, yc + s * 0.06, z_tie + 0.25), (x, yc + s * ys, under(ys) - 0.1), 0.12, 0.12, TIMBER)
    for s in (-1, 1):
        m.beam((x_ext[0], yc + s * yp, z_tie + 0.17), (x_ext[1], yc + s * yp, z_tie + 0.17), 0.26, 0.36, TIMBER, up=(0, 0, 1))
    with m.grained((0, 1, 0)):
        slab_roof(m, x0, x1, half, z_eave, z_ridge, t, rmat, rolls=rolls, yc=yc, **(roof_kw or {}))
    # Plaster infill in the gable of the trusses named in infill (the members stay proud of it).
    for x in infill:
        z_b = under(yp) - 0.02
        m.box((x, yc, (z_tie - 0.02 + z_b + 0.01) / 2), (0.1, 2 * yp, z_b + 0.03 - z_tie), PLASTER)
        gable(m, x - 0.045, x + 0.045, yc, yp, z_b, (z_ridge, z_eave, half, t), PLASTER)
    return z_eave


def cross_gable(m, st, xs, yp, post, z_foot, z_tie, xc, half, y_ext, z_ridge, t, rmat, rolls, label, on=('platform',),
                foot_embed=0.0, roof_kw=None, knee_sect=0.18, knee_len=1.0, infill=(), mat=TIMBER):
    """A tall gable whose ridge runs across the rope (along y), its gable ends facing +-y: posts on the lines
    y = +-yp at xs, an exposed truss on each post line (tie beam, king post, rafters, struts), eave plates along y on
    the end posts, purlins and a ridge beam along y, knee braces, and a slab_roof turned through 90 degrees. infill
    names the truss lines (-1, +1) that get a plaster gable. Returns the roof's z_eave."""
    x_eave = max(abs(xs[0] - xc), abs(xs[-1] - xc))
    z_eave = eave_for(z_ridge, half, t, x_eave, z_tie + 0.32)

    def under(x):
        return roof_under(z_ridge, z_eave, half, t, abs(x - xc))
    rise = z_ridge - z_eave; L = math.hypot(half, rise); nx, nz = rise / L, half / L; Lk = knee_len
    for s in (-1, 1):
        y = s * yp
        for x in xs:
            with m.grained((0, 0, 1)):
                m.box((x, y, (z_foot + z_tie + 0.05) / 2), (post, post, z_tie + 0.05 - z_foot), mat, bevel=0.015)
            st.seat(label, x, y, z_foot, embed=foot_embed, on=on)
            st.proxies.append(proxy_box(label, x, y, post + 0.04, post + 0.04, z_foot, z_tie))
            for d in (-1, 1):            # into the tie beam, inward only at the ends
                if (d < 0 and x == min(xs)) or (d > 0 and x == max(xs)):
                    continue
                knee(m, (x + d * post / 2, y, z_tie - 0.30 - Lk), (d, 0, 0), (0, 0, 1), Lk, (knee_sect, knee_sect), mat)
            if x in (min(xs), max(xs)):  # into the eave plate, inward
                knee(m, (x, y - s * post / 2, z_tie - 0.01 - Lk), (0, -s, 0), (0, 0, 1), Lk, (knee_sect, knee_sect), mat)
        m.beam((xs[0] - 0.35, y, z_tie - 0.15), (xs[-1] + 0.35, y, z_tie - 0.15), 0.24, 0.30, mat, up=(0, 0, 1))
        m.box((xc, y, (z_tie + under(xc) + 0.05) / 2), (0.22, 0.22, under(xc) + 0.05 - z_tie), mat)
        for sd in (-1, 1):
            nrm = Vector((sd * nx, 0, nz)); dd = 0.22
            a = Vector((xc + sd * (x_eave + 0.1), y, under(xc + sd * (x_eave + 0.1)))) - nrm * (dd / 2 - 0.02)
            b = Vector((xc + sd * 0.08, y, under(xc + sd * 0.08))) - nrm * (dd / 2 - 0.02)
            m.beam(a, b, 0.16 if sd < 0 else 0.17, dd, mat, up=tuple(nrm))     # unequal: no shared faces at the apex
            xs_ = x_eave * 0.45
            m.beam((xc + sd * 0.06, y, z_tie + 0.25), (xc + sd * xs_, y, under(xc + sd * xs_) - 0.1), 0.12, 0.12, mat)
    for x in (min(xs), max(xs)):
        m.beam((x, -yp - 0.35, z_tie + 0.17), (x, yp + 0.35, z_tie + 0.17), 0.26, 0.36, mat, up=(0, 0, 1))
    for f in (0.0, 0.3, 0.62, 0.92):
        for sd in ((1,) if f == 0.0 else (-1, 1)):
            x = xc + sd * x_eave * f; nrm = Vector((sd * nx, 0, nz)) if f else Vector((0, 0, 1))
            c = Vector((x, 0, under(x))) - nrm * 0.09
            m.beam(c + Vector((0, -(y_ext - 0.25), 0)), c + Vector((0, y_ext - 0.25, 0)), 0.17 if f else 0.24, 0.2, mat, up=tuple(nrm))
    with m.frame((xc, 0, 0), (0, 1, 0), (-1, 0, 0), (0, 0, 1)), m.grained((0, 1, 0)):
        slab_roof(m, -y_ext, y_ext, half, z_eave, z_ridge, t, rmat, rolls=rolls, **({'fascia': mat} | (roof_kw or {})))
    # Gable trusses named in infill (-1, +1): a collar beam a little over half way up with queen posts under it,
    # plaster only in the triangle above the collar; below it the truss stays open (the bullwheel shows through).
    for s in infill:
        y = s * yp; z_c = z_tie + 0.55 * (under(xc) - z_tie)
        hw_c = (z_ridge - t / nz - z_c) * half / rise
        m.beam((xc - hw_c, y, z_c), (xc + hw_c, y, z_c), 0.14, 0.2, mat, up=(0, 0, 1))
        for sq in (-1, 1):
            m.box((xc + sq * hw_c * 0.55, y, (z_tie + z_c) / 2), (0.14, 0.13, z_c - z_tie), mat)
        with m.frame((xc, 0, 0), (0, 1, 0), (-1, 0, 0), (0, 0, 1)):
            gable(m, y - 0.045, y + 0.045, 0.0, hw_c, z_c, (z_ridge, z_eave, half, t), PLASTER)
    return z_eave


def gable(m, x0, x1, yc, half_w, z_base, roof, mat):
    """Triangular gable infill between x0 and x1 under a slab_roof (z_ridge, z_eave, half, t)."""
    z_ridge, z_eave, half, t = roof
    apex = roof_under(z_ridge, z_eave, half, t, 0.0) + (z_base - roof_under(z_ridge, z_eave, half, t, half_w)) + 0.02
    with m.frame((x0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)):
        m.prism([(yc - half_w, z_base), (yc + half_w, z_base), (yc, apex)], 0.0, x1 - x0, mat)


def retaining_wall(m, st, path, z0, z1, thick, seed, rock_z=None, mat=STONE, rock_size=0.75, dressed=False):
    """Stone wall outside an open plan path (outward = right of the path), with rounded stones proud of its face, or
    (dressed) squared blocks in coursed rows."""
    outer = offset_path(path, -thick)
    m.band(outer, offset_path(path, 0.05), z0, z1, mat)
    if rock_z and dressed:
        ashlar(m, outer, rock_z[0], rock_z[1], seed, size=rock_size)
    elif rock_z:
        stone_course(m, outer, rock_z[0], rock_z[1], 0.5, seed, size=rock_size)


def ashlar(m, pts, z0, z1, seed, size=0.6, course=0.3):
    """Dressed stone blocks in staggered courses on the face right of an open polyline. Blocks stop 0.12 m short of
    each corner, so blocks of neighbouring faces never overlap."""
    import random
    rnd = random.Random(seed); rows = max(1, round((z1 - z0) / course)); h = (z1 - z0) / rows
    for p, q in zip(pts[:-1], pts[1:]):
        P, Q = Vector(p), Vector(q); L = (Q - P).length
        if L < 0.5:
            continue
        t = (Q - P) / L; nrm = Vector((t.y, -t.x)); yaw = math.degrees(math.atan2(t.y, t.x))
        for r in range(rows):
            zb, zt = z0 + r * h + 0.008, z0 + (r + 1) * h - 0.008
            s_ = 0.12 + (r % 2) * size * 0.45 * rnd.random()
            while s_ < L - 0.32:
                e = min(s_ + size * (0.65 + 0.6 * rnd.random()), L - 0.12)
                c = P + t * ((s_ + e) / 2 + 0.0) + nrm * 0.015
                with m.at((c.x, c.y, (zb + zt) / 2), yaw):
                    m.box((0, 0, 0), (e - s_ - 0.016, 0.07, zt - zb), STONE if rnd.random() < 0.55 else BASALT, bevel=0.016)
                s_ = e


def stair_profile(y0, z_top, risers, rise, tread, landing, z_bottom, direction=1):
    """Side profile (y, z) of a solid stair going down from z_top at y0 in +y (direction 1) or -y."""
    pts = [(0.0, z_bottom), (risers * tread - tread + landing, z_bottom), (risers * tread - tread + landing, z_top - risers * rise)]
    for k in range(risers - 1, 0, -1):
        pts += [(k * tread, z_top - (k + 1) * rise), (k * tread, z_top - k * rise)]
    pts += [(0.0, z_top - rise)]
    return [(y0 + direction * u, z) for u, z in pts]


# ------------------------------------------------------------------ the three stations
class Valley(Station):
    """Hidamari valley station: a plastered, timber-framed station house with a tiled roof and an entry porch on
    the plaza, and a tall tiled canopy on timber trusses over the bullwheel and the platform."""
    NAME = 'Valley'
    HOUSE_DX = -4.0                 # the house plan below is drawn at x -14.6..-2.6 and moved by this
    DOOR_X = -5.6                   # the entrance and its porch, towards the house's east end (house plan x)
    GABLE_XS = (-10.8, -5.8, -0.7, 4.4)  # cross-gable post lines: over the bullwheel end, the line leaving from under it

    def __init__(self, key, p, d):
        super().__init__(key, p, d)
        self.XB = -11.4             # deck behind the bullwheel, under the cross-gable

    def make(self):
        plat, mach, fit, bldg = (Mesh(f'GD_StationValley_{k}') for k in ('Platform', 'Machinery', 'Fittings', 'Building'))
        XB, XM, YO = self.XB, self.XM, self.YO
        self.core(plat, mach, fit, PAVING, 'metal')
        plaza = rect(-20.4, -20.0, 9.6, -YO)
        with plat.tagged('platform'):
            plat.prism(plaza, self.base, 0.0, PAVING)
        self.proxies.append(proxy('plaza', plaza, self.base, 0.0))      # the plaza floor (the road-side access)
        self.slabs.append(('plaza', plaza))
        self.levels.append({'name': 'platform and plaza', 'z': 0.0})
        self.access.append({'name': 'plaza front (road side)', 'edge': [[-11.7, -20.0], [-7.5, -20.0]], 'z': 0.0, 'point': [-9.6, -19.4]})
        self.points['platform back'] = [-6.0, 0.0]
        # Outer railings: the +y side, the back and the mouth corners (the -y side opens onto the plaza).
        railing(fit, self, [(XB + 0.15, -YO + 0.3), (XB + 0.15, YO - 0.15), (XM - 0.15, YO - 0.15), (XM - 0.15, self.YP + 0.5)], 'metal')
        railing(fit, self, [(XM - 0.15, -YO + 0.3), (XM - 0.15, -self.YP - 0.5)], 'metal')
        # Canopy over the loop.
        for x in self.GABLE_XS:
            for s in (-1, 1):
                with fit.tagged('post base'):
                    fit.box((x, s * 6.9, 0.12), (0.5, 0.5, 0.24), STONE, bevel=0.03)
                self.seat('canopy post base', x, s * 6.9, 0.0)
        # The tall cross-gable over the ropeway end: ridge across the rope, gable facing the plaza, open trusses.
        cross_gable(bldg, self, self.GABLE_XS, 6.9, 0.3, 0.23, 4.95, -3.2, 8.3, 8.2, 10.0, 0.14, TILE, 'tile',
                    'canopy post', on=('post base',), foot_embed=0.012, roof_kw={'oni': True, 'tails': 0.6}, infill=(-1,),
                    mat=TIMBER_DARK)
        # The station house stands beside the cross-gable, as painted: its east end meets the gable's west posts.
        with self.shifted(self.HOUSE_DX, bldg, fit):
            self.house(bldg, fit)
        # Plaza furniture.
        bench(fit, self, -17.0, -17.2, 0)
        bench(fit, self, -14.0, -17.2, 0)
        self.notice_board(fit, -19.2, -17.6)
        for x0, x1 in ((-19.8, -11.9), (-7.3, -2.4)):
            self.planter(fit, x0, -19.4, x1, -18.4)
        # Stone kerbs along the road edge and the west side of the forecourt (gap at the entrance).
        for a, b in (((-20.4, -20.0), (-11.7, -20.0)), ((-7.5, -20.0), (9.6, -20.0)), ((-20.4, -19.75), (-20.4, -8.0))):
            if a[1] == b[1]:
                fit.box(((a[0] + b[0]) / 2, a[1] + 0.125, 0.07), (b[0] - a[0], 0.25, 0.14), STONE, bevel=0.02)
                self.seat('kerb', (a[0] + b[0]) / 2, a[1] + 0.125, 0.0)
            else:
                fit.box((a[0] + 0.125, (a[1] + b[1]) / 2, 0.07), (0.25, b[1] - a[1], 0.14), STONE, bevel=0.02)
                self.seat('kerb', a[0] + 0.125, (a[1] + b[1]) / 2, 0.0)
        for x in (self.DOOR_X - 1.9 + self.HOUSE_DX, self.DOOR_X + 1.95 + self.HOUSE_DX):
            fit.lathe((x, -16.15, 0.0), [(0, 0.2), (0.08, 0.27), (0.5, 0.3), (0.55, 0.32)], POT, n=10)
            fit.lathe((x, -16.15, 0.5), [(0, 0.27), (0.03, 0.27)], SOIL, n=10)
            self.seat('flower pot', x, -16.15, 0.0)
            self.proxies.append(proxy_box('flower pot', x, -16.15, 0.6, 0.6, 0.0, 0.55))
        return {m.name: m for m in (plat, mach, fit, bldg)}

    def house(self, m, fit):
        x0, x1, y0, y1 = -14.6, -2.6, -15.6, -9.6; yc = (y0 + y1) / 2; cx = (x0 + x1) / 2
        m.box((cx, yc, 0.15), (x1 - x0 + 0.2, y1 - y0 + 0.2, 0.3), STONE, bevel=0.02)
        self.seat('station house plinth', cx, yc, 0.0)
        m.prism(rect(x0 + 0.1, y0 + 0.1, x1 - 0.1, y1 - 0.1), 0.29, 3.40, PLASTER)
        with m.grained((1, 0, 0)):
            m.ring_prism(rect(x0 + 0.08, y0 + 0.08, x1 - 0.08, y1 - 0.08), rect(x0 + 0.12, y0 + 0.12, x1 - 0.12, y1 - 0.12), 0.3, 1.0, PANEL)
        for x in (x0 + 0.1, x1 - 0.1):
            for y in (y0 + 0.1, y1 - 0.1):
                with m.grained((0, 0, 1)):
                    m.box((x, y, 1.83), (0.26, 0.26, 3.10), TIMBER_DARK)
        # Frame members proud of the plaster: posts every ~2 m, sill, head and top beams.
        for face, (a, b), fixed, nrm in (('front', (x0 + 0.1, x1 - 0.1), y0 + 0.1, (0, -1)), ('back', (x0 + 0.1, x1 - 0.1), y1 - 0.1, (0, 1)),
                                         ('west', (y0 + 0.1, y1 - 0.1), x0 + 0.1, (-1, 0)), ('east', (y0 + 0.1, y1 - 0.1), x1 - 0.1, (1, 0))):
            n = max(2, round((b - a) / 1.0))
            for k in range(1, n):
                u = a + (b - a) * k / n
                c = (u, fixed, 0) if face in ('front', 'back') else (fixed, u, 0)
                if face == 'front' and -7.0 < u < -4.2:
                    continue
                with m.wall(c, nrm), m.grained((0, 1, 0)):
                    m.box((0, 1.845, 0.0), (0.16, 3.07, 0.08), TIMBER_DARK)
            for z, h in ((1.0, 0.12), (2.55, 0.14), (3.2, 0.16)):
                runs = [(a + 0.12, b - 0.12)]
                if face == 'front' and z < 2.0:
                    runs = [(a + 0.12, -7.0), (-4.2, b - 0.12)]
                for ra, rb in runs:
                    mid = (ra + rb) / 2
                    c = (mid, fixed, 0) if face in ('front', 'back') else (fixed, mid, 0)
                    with m.wall(c, nrm):
                        m.box((0, z, 0.0), (rb - ra, h, 0.1), TIMBER_DARK)
        # Front: a long window band, the lattice doors under the porch, a smaller window to the right.
        for wa, wb in ((-14.2, -7.3), (-3.9, -3.0)):
            with m.wall(((wa + wb) / 2, y0 + 0.1, 0), (0, -1)):
                m.box((0, 1.78, 0.0), (wb - wa, 1.4, 0.03), WINDOW)
                n = max(2, round((wb - wa) / 0.9))
                for k in range(1, n):
                    m.box((-(wb - wa) / 2 + (wb - wa) * k / n, 1.78, 0.0), (0.07, 1.44, 0.07), TIMBER_DARK)
        with m.wall((self.DOOR_X, y0 + 0.1, 0), (0, -1)):
            for s in (-1, 1):
                m.box((s * 0.4, 1.365, 0.0), (0.78, 2.11, 0.06), TIMBER)
                for k in range(6):
                    m.box((s * 0.4 - 0.3 + 0.12 * k, 1.5, 0.0), (0.03, 1.6, 0.09), TIMBER_DARK)
            m.box((0, 2.47, 0.0), (1.8, 0.1, 0.09), TIMBER_DARK)
        m.box((self.DOOR_X, y0 - 0.3, 0.075), (2.4, 0.4, 0.15), STONE)
        self.seat('door step', self.DOOR_X, y0 - 0.3, 0.0)
        # Wall lantern beside the door.
        m.box((self.DOOR_X + 1.45, y0 + 0.04, 2.0), (0.08, 0.16, 0.08), IRON)
        m.box((self.DOOR_X + 1.45, y0 - 0.12, 2.0), (0.18, 0.18, 0.26), LAMP)
        m.box((self.DOOR_X + 1.45, y0 - 0.12, 2.16), (0.24, 0.24, 0.06), IRON)
        # Main roof: tiles over the whole house, gables in plaster.
        # Main roof: irimoya (hip-and-gable) in kawara, as painted: the ridge stops short of the ends, hips run down
        # to the end eaves and a small plaster gable with onigawara sits under each ridge end.
        irimoya_roof(m, x0 - 0.5, x1 + 0.5, yc, 3.6, 3.50, 5.6, 0.14, 2.2, TILE, TILE, PLASTER, fascia=TIMBER_DARK,
                     no_tails=((self.DOOR_X - 2.1, self.DOOR_X + 2.1),))
        # Porch: two posts, a beam and a small gable roof turned across the main one.
        for x in (self.DOOR_X - 1.3, self.DOOR_X + 1.3):
            with m.grained((0, 0, 1)):
                m.box((x, y0 - 1.0, 1.35), (0.2, 0.2, 2.7), TIMBER_DARK)
            self.seat('porch post', x, y0 - 1.0, 0.0)
            self.proxies.append(proxy_box('porch post', x, y0 - 1.0, 0.24, 0.24, 0.0, 2.8))
        m.beam((self.DOOR_X - 1.6, y0 - 1.0, 2.68), (self.DOOR_X + 1.6, y0 - 1.0, 2.68), 0.22, 0.24, TIMBER_DARK, up=(0, 0, 1))
        m.beam((self.DOOR_X - 1.3, y0 - 1.0, 2.68), (self.DOOR_X - 1.3, y0 + 0.12, 2.68), 0.16, 0.2, TIMBER_DARK, up=(0, 0, 1))
        m.beam((self.DOOR_X + 1.3, y0 - 1.0, 2.68), (self.DOOR_X + 1.3, y0 + 0.12, 2.68), 0.16, 0.2, TIMBER_DARK, up=(0, 0, 1))
        with m.at((self.DOOR_X, 0, 0), 90), m.grained((0, 1, 0)):
            ze = eave_for(3.75, 1.9, 0.1, 1.3, 2.78)
            slab_roof(m, y0 - 1.5, y0 + 0.4, 1.9, ze, 3.75, 0.1, TILE, rolls='tile', oni=True, fascia=TIMBER_DARK)
        self.proxies.append(proxy('station house', rect(x0, y0, x1, y1), 0.0, 5.0))

    def notice_board(self, m, x, y):
        for s in (-1, 1):
            with m.grained((0, 0, 1)):
                m.box((x + s * 0.7, y, 1.0), (0.12, 0.12, 2.0), TIMBER_DARK)
            self.seat('notice board post', x + s * 0.7, y, 0.0)
        m.box((x, y, 1.45), (1.3, 0.06, 0.95), SIGN)
        m.box((x, y, 2.02), (1.6, 0.3, 0.06), TIMBER_DARK)
        self.proxies.append(proxy_box('notice board', x, y, 1.6, 0.3, 0.0, 2.05))

    def planter(self, m, x0, y0, x1, y1):
        m.ring_prism(rect(x0, y0, x1, y1), rect(x0 + 0.25, y0 + 0.25, x1 - 0.25, y1 - 0.25), 0.0, 0.5, STONE)
        m.prism(rect(x0 + 0.24, y0 + 0.24, x1 - 0.24, y1 - 0.24), 0.01, 0.42, SOIL)
        self.seat('planter wall', x0 + 0.12, (y0 + y1) / 2, 0.0)
        self.proxies.append(proxy('planter', rect(x0, y0, x1, y1), 0.0, 0.5))


class Rim(Station):
    """Crater Park rim station: a decked platform on a stone retaining wall at the crater edge, a shingled timber
    pavilion on stone piers behind the bullwheel, a flat-roofed wheel shelter on heavy posts, a viewing bulge on the
    crater side and a boardwalk down to the rim path."""
    NAME = 'Rim'
    BULGE = [(-6.5, -7.6), (-5.5, -9.6), (-3.0, -10.6), (3.0, -10.6), (5.5, -9.6), (6.5, -7.6)]
    WALK = (-15.4, -13.0, None, 15.0)        # boardwalk start edge x0, x1 at the deck; (unused); grade 1:15

    def __init__(self, key, p, d):
        super().__init__(key, p, d)
        self.XB = -17.8; self.base = -0.6

    def platform_poly(self, *_):
        a1, a2 = self.angles(); YO, XM, XB = self.YO, self.XM, self.XB
        return [(XM, -YO), (XM, -self.YP)] + self.arc(a2, a1) + [(XM, self.YP), (XM, YO), (XB, YO), (XB, -YO)] + self.BULGE

    def platform_proxies(self, top=0.0):
        return super().platform_proxies(top) + [proxy('platform', self.BULGE, self.base, top)]

    def make(self):
        plat, mach, fit, bldg = (Mesh(f'GD_StationRim_{k}') for k in ('Platform', 'Machinery', 'Fittings', 'Building'))
        XB, XM, YO, YP = self.XB, self.XM, self.YO, self.YP
        self.core(plat, mach, fit, TIMBER_DARK, 'timber', top_mat=DECK)
        self.slabs.append(('viewing bulge', self.BULGE))
        self.levels.append({'name': 'deck', 'z': 0.0})
        # Retaining wall round the deck (open path from the mouth's +y corner round to its -y corner), and the
        # mouth: low wall beside the pit, sunk under the pit channel so the cabins pass over it.
        path = [(XM + 0.2, YO), (XB, YO), (XB, -YO)] + self.BULGE + [(XM + 0.2, -YO)]
        retaining_wall(plat, self, path, -3.6, -0.04, 0.45, 7, rock_z=(-2.2, -0.15))
        # The channel through the mouth wall is MOUTH_WIDEN wider each side than the pit, so the cabin body keeps
        # checks.STATION_LOOP_MARGIN from its stone faces (the pit's own edge is the boarding gap).
        w = self.MOUTH_WIDEN
        for s in (-1, 1):
            plat.box((XM + 0.225, s * (YO + YP + w + 0.47) / 2, -1.84), (0.45, YO - YP - w + 0.47, 3.62), STONE)
        plat.box((XM + 0.225, 0.0, -1.925), (0.43, 2 * (YP + w) + 0.02, 3.25), STONE)
        # Railings: deck edge (gap for the boardwalk), viewing bulge.
        inner = offset_path(path, 0.15)
        a = [(XM - 0.15, YP + 0.5), (XM - 0.15, YO - 0.15)] + inner[1:3]
        railing(fit, self, a + [(self.WALK[0] - 0.1, -YO + 0.15)], 'timber')
        railing(fit, self, [(self.WALK[1] + 0.1, -YO + 0.15)] + inner[3:-1] + [(XM - 0.15, -YO + 0.15), (XM - 0.15, -YP - 0.5)], 'timber')
        self.boardwalk(plat, fit)
        self.pavilion(bldg, fit)
        self.shelter(bldg, fit)
        bench(fit, self, -15.6, -2.2, 90)
        bench(fit, self, -15.6, 2.2, 90)
        bench(fit, self, 0.0, -9.4, 0)
        return {m.name: m for m in (plat, mach, fit, bldg)}

    def boardwalk_line(self):
        """Centreline of the curved boardwalk: out of the deck edge, a bend of radius 7 m towards -x, a short straight."""
        x0, x1, _, _ = self.WALK; xc = (x0 + x1) / 2; YO = self.YO; y_b = -YO - 2.4; R7 = 7.0
        pts = [(xc, -YO)] + [(xc, -YO - 0.6 * k) for k in range(1, 5)]
        c = (xc - R7, y_b)
        pts += [(c[0] + R7 * math.cos(-math.radians(5 * k)), c[1] + R7 * math.sin(-math.radians(5 * k))) for k in range(1, 14)]
        a = -math.radians(65); d = (math.sin(a), -math.cos(a))
        last = pts[-1]
        pts += [(last[0] + d[0] * 0.65 * k, last[1] + d[1] * 0.65 * k) for k in range(1, 4)]
        return pts

    def boardwalk(self, plat, fit):
        x0, x1, _, grade = self.WALK; YO = self.YO; half = (x1 - x0) / 2
        line = self.boardwalk_line(); S = [0.0]
        for p, q in zip(line[:-1], line[1:]):
            S.append(S[-1] + math.dist(p, q))

        def s_on(x, y):
            best = (1e9, 0.0)
            for (p, q), s0 in zip(zip(line[:-1], line[1:]), S):
                dx, dy = q[0] - p[0], q[1] - p[1]; L2 = dx * dx + dy * dy
                t = max(0.0, min(1.0, ((x - p[0]) * dx + (y - p[1]) * dy) / L2))
                dd = (x - p[0] - t * dx) ** 2 + (y - p[1] - t * dy) ** 2
                if dd < best[0]:
                    best = (dd, s0 + t * math.sqrt(L2))
            return best[1]

        def top(x, y):
            return -s_on(x, y) / grade
        left, right = offset_path(line, half), offset_path(line, -half)
        with plat.tagged('boardwalk'):
            for i in range(len(line) - 1):
                quad = [right[i], right[i + 1], left[i + 1], left[i]]
                plat.prism(quad, lambda x, y: top(x, y) - 0.25, top, TIMBER_DARK, top=DECK)
                self.proxies.append(proxy('boardwalk', quad, lambda x, y: top(x, y) - 0.25, top))   # sloped floor hull
        outline = right + left[::-1]
        self.slabs.append(('boardwalk', outline)); self.slab_z['boardwalk'] = top
        end = line[-1]; d = Vector(line[-1]) - Vector(line[-2]); d.normalize()
        self.levels.append({'name': 'boardwalk', 'z': 'ramp', 'grade': round(1 / grade, 4), 'length_m': round(S[-1], 2),
                            'from': [line[0][0], line[0][1], 0.0], 'to': [round(end[0], 3), round(end[1], 3), round(-S[-1] / grade, 3)]})
        self.access.append({'name': 'boardwalk to the rim path', 'edge': [list(map(lambda v: round(v, 3), right[-1])), list(map(lambda v: round(v, 3), left[-1]))],
                            'z': round(-S[-1] / grade, 3), 'point': [round(end[0] - d.x * 0.5, 3), round(end[1] - d.y * 0.5, 3)]})
        self.surfaces.append({'name': 'boardwalk', 'poly': outline, 'path': line, 'grade': 1.0 / grade})
        self.points['pavilion'] = [-14.6, 0.0]; self.points['viewing bulge'] = [0.0, -8.4]
        for i in range(3, len(line) - 1, 4):
            t = Vector(line[i + 1]) - Vector(line[i - 1]); yaw = math.degrees(math.atan2(t.y, t.x))
            for off in (half - 0.3, -(half - 0.3)):
                p = offset_path(line, off)[i]; zt = top(*p)
                with plat.at((p[0], p[1], 0.0), yaw), plat.grained((0, 0, 1)):
                    plat.box((0, 0, (zt - 0.24 - 3.4) / 2), (0.2, 0.2, zt - 0.24 + 3.4), TIMBER)
            pa, pb = offset_path(line, half - 0.1)[i], offset_path(line, -(half - 0.1))[i]
            zb = top(*line[i]) - 0.35
            plat.beam((pa[0], pa[1], zb), (pb[0], pb[1], zb), 0.16, 0.2, TIMBER, up=(0, 0, 1))
        for off in (half - 0.15, -(half - 0.15)):
            pts = offset_path(line, off)
            pts = [(pts[0][0], pts[0][1] - 0.1)] + pts[1:-1] + [tuple(Vector(pts[-1]) - d * 0.15)]
            railing(fit, self, pts, 'timber', on=('boardwalk',), z0=lambda xx, yy: top(xx, yy), spacing=1.8)

    def pavilion(self, m, fit):
        xs = (-17.0, -12.8, -8.6); yp = 4.6
        for i, x in enumerate(xs):
            for s in (-1, 1):
                with m.tagged('pier'):
                    stone_pier(m, x, s * yp, seed=11 + 2 * i + (s > 0))
                self.seat('pavilion pier', x, s * yp, -0.04, embed=0.04)
                self.proxies.append(proxy_box('pavilion pier', x, s * yp, 0.95, 0.95, 0.0, 1.2))
        canopy(m, self, xs, yp, 0.42, 1.18, 4.42, (-17.5, -8.1), (-18.6, -7.4, 7.6, 8.5, 0.16, SHINGLE, 'courses'),
               'pavilion post', on=('pier',), foot_embed=0.025, roof_kw={'tails': 0.55}, knee_sect=0.19, knee_len=1.15,
               infill=(-17.0,))
        # Plaster back wall and part of the +y side, timber-framed.
        for (a, b, c, axis) in ((-4.2, 4.2, -17.0, 'x'), (-16.6, -13.2, yp, 'y')):
            if axis == 'x':
                m.box((c, 0.0, 2.07), (0.2, b - a, 4.14), PLASTER)
                self.seat('pavilion back wall', c, 0.0, 0.0)
                self.proxies.append(proxy_box('pavilion wall', c, 0.0, 0.24, b - a, 0.0, 4.1))
                for z in (0.45, 2.3):
                    m.box((c + 0.11, 0.0, z), (0.06, b - a - 0.02, 0.14), TIMBER)
            else:
                m.box(((a + b) / 2, c, 2.215), (b - a, 0.2, 4.43), PLASTER)
                self.seat('pavilion side wall', (a + b) / 2, c, 0.0)
                self.proxies.append(proxy_box('pavilion wall', (a + b) / 2, c, b - a, 0.24, 0.0, 4.1))
                for z in (0.45, 2.3):
                    m.box(((a + b) / 2, c - 0.11, z), (b - a - 0.02, 0.06, 0.14), TIMBER)
        self.proxies.append(proxy('pavilion roof', rect(-18.6, -7.6, -7.4, 7.6), 4.1, 8.5))

    def shelter(self, m, fit):
        """The bullwheel's own raised roof, as painted: a low, flat roof with a deep layered fascia on heavy posts
        that flare into Y brackets, standing on stone piers. The roof beams sit just above the rail frame, so the
        wheel shows directly under the roof from the deck."""
        xs = (-5.6, 1.8); yp = 6.4; z_b = 4.68; post = 0.44
        for i, x in enumerate(xs):
            for s in (-1, 1):
                with m.tagged('pier'):
                    stone_pier(m, x, s * yp, seed=31 + 2 * i + (s > 0))
                self.seat('shelter pier', x, s * yp, -0.04, embed=0.04)
                self.proxies.append(proxy_box('shelter pier', x, s * yp, 0.95, 0.95, 0.0, 1.2))
                with m.grained((0, 0, 1)):
                    m.box((x, s * yp, (1.18 + z_b + 0.02) / 2), (post, post, z_b + 0.02 - 1.18), TIMBER, bevel=0.02)
                self.seat('shelter post', x, s * yp, 1.18, embed=0.025, on=('pier',))
                self.proxies.append(proxy_box('shelter post', x, s * yp, post + 0.04, post + 0.04, 1.18, z_b))
                # Y brackets: big curved braces both ways along the line and both ways across it.
                for d in (-1, 1):
                    knee(m, (x + d * post / 2, s * yp, z_b + 0.02 - 1.35), (d, 0, 0), (0, 0, 1), 1.35, (0.23, 0.23))
                    knee(m, (x, s * yp + d * post / 2, z_b + 0.32 - 1.35), (0, d, 0), (0, 0, 1), 1.35, (0.22, 0.22))
        # Beams: along the line on the post tops, across it at each post line and between.
        for s in (-1, 1):
            m.beam((xs[0] - 1.7, s * yp, z_b + 0.2), (xs[1] + 1.7, s * yp, z_b + 0.2), 0.32, 0.4, TIMBER, up=(0, 0, 1))
        for x in (xs[0], (xs[0] + xs[1]) / 2, xs[1]):
            m.beam((x, -yp - 1.6, z_b + 0.43), (x, yp + 1.6, z_b + 0.43), 0.28, 0.26, TIMBER, up=(0, 0, 1))
        # Roof: a deep fascia slab and a thinner inset cap with a very low hip, bevelled edges.
        x0, x1, y0, y1 = xs[0] - 2.4, xs[1] + 2.4, -yp - 2.1, yp + 2.1
        with m.grained((1, 0, 0)):
            m.box(((x0 + x1) / 2, 0.0, z_b + 0.72), (x1 - x0, y1 - y0, 0.34), PLANK, bevel=0.05)
            m.box(((x0 + x1) / 2, 0.0, z_b + 0.98), (x1 - x0 - 0.6, y1 - y0 - 0.6, 0.2), SHINGLE, bevel=0.06)
        m.ring_prism(rect(x0 - 0.05, y0 - 0.05, x1 + 0.05, y1 + 0.05), rect(x0 + 0.08, y0 + 0.08, x1 - 0.08, y1 - 0.08),
                     z_b + 0.58, z_b + 0.84, TIMBER_DARK)
        self.proxies.append(proxy('shelter roof', rect(x0, y0, x1, y1), z_b - 0.05, z_b + 1.1))


class Crater(Station):
    """Crater-floor station: a raised timber deck on a stone base at the crater floor, a board-clad mechanism house
    over the bullwheel and the back of the loop, a timber canopy over the berths and a stone stair down to the floor."""
    NAME = 'Crater'
    STAIR = (0.0, 2.6)          # stair x range on the +y edge
    RISERS, RISE, TREAD, LANDING = 6, 0.2, 0.3, 1.5

    def __init__(self, key, p, d):
        super().__init__(key, p, d)
        self.XB, self.YO = -9.6, 8.0; self.base = -1.6
        self.grade = -self.RISERS * self.RISE

    def stair_z(self, x, y):
        k = math.ceil((y - self.YO) / self.TREAD - 1e-9)
        return max(self.grade, -self.RISE * k) if y > self.YO else 0.0

    def make(self):
        plat, mach, fit, bldg = (Mesh(f'GD_StationCrater_{k}') for k in ('Platform', 'Machinery', 'Fittings', 'Building'))
        XB, XM, YO, YP = self.XB, self.XM, self.YO, self.YP; sx0, sx1 = self.STAIR
        self.core(plat, mach, fit, TIMBER_DARK, 'timber', top_mat=DECK)
        self.levels.append({'name': 'deck', 'z': 0.0})
        self.levels.append({'name': 'crater floor landing', 'z': self.grade})
        # Stone base: the +y wall is split by the stair.
        retaining_wall(plat, self, [(XM + 0.2, YO), (sx1 + 0.2, YO)], -1.9, -0.04, 0.45, 11, rock_z=(-1.86, -0.1), rock_size=0.6, dressed=True)
        retaining_wall(plat, self, [(sx0 - 0.2, YO), (XB, YO), (XB, -YO), (XM + 0.2, -YO)], -1.9, -0.04, 0.45, 13, rock_z=(-1.86, -0.1), rock_size=0.6, dressed=True)
        # The channel through the mouth wall is MOUTH_WIDEN wider each side than the pit, so the cabin body keeps
        # checks.STATION_LOOP_MARGIN from its stone faces (the pit's own edge is the boarding gap).
        w = self.MOUTH_WIDEN
        for s in (-1, 1):
            plat.box((XM + 0.225, s * (YO + YP + w + 0.47) / 2, -0.99), (0.45, YO - YP - w + 0.47, 1.92), STONE)
        plat.box((XM + 0.225, 0.0, -1.075), (0.43, 2 * (YP + w) + 0.02, 1.55), STONE)
        # Stair: one solid stone flight with cheek walls, landing at the crater floor.
        prof = stair_profile(YO, 0.0, self.RISERS, self.RISE, self.TREAD, self.LANDING, -1.9)
        with plat.frame((sx0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0)), plat.tagged('stair'):
            plat.prism(prof, 0.0, sx1 - sx0, STONE)
        y_end = YO + (self.RISERS - 1) * self.TREAD + self.LANDING
        y_c0 = YO - 0.08

        def cheek(x, y):
            return 0.25 + (y - y_c0) * (self.grade) / (y_end - y_c0)
        for xa, xb in ((sx0 - 0.45, sx0), (sx1, sx1 + 0.45)):
            with plat.tagged('cheek'):
                plat.prism(rect(xa, y_c0, xb, y_end), -1.95, cheek, STONE)
            self.proxies.append(proxy('stair cheek', rect(xa, y_c0, xb, y_end), -1.9, cheek))
            xm = (xa + xb) / 2
            railing(fit, self, [(xm, YO + 0.1), (xm, y_end - 0.15)], 'timber', on=('cheek',), z0=cheek, spacing=1.6, embed=0.01)
        self.stairs.append({'x': [sx0, sx1], 'y': [YO, YO + (self.RISERS - 1) * self.TREAD], 'direction': '+y', 'risers': self.RISERS,
                            'riser_m': self.RISE, 'tread_m': self.TREAD, 'top_z': 0.0, 'bottom_z': self.grade, 'width_m': sx1 - sx0})
        self.slabs.append(('landing', rect(sx0, YO + (self.RISERS - 1) * self.TREAD, sx1, y_end))); self.slab_z['landing'] = self.grade
        self.access.append({'name': 'crater floor (stair landing)', 'edge': [[sx0, y_end], [sx1, y_end]], 'z': self.grade, 'point': [(sx0 + sx1) / 2, y_end - 0.5]})
        ys = YO + (self.RISERS - 1) * self.TREAD
        self.surfaces.append({'name': 'stair', 'poly': rect(sx0, YO, sx1, ys), 'stair': {'y0': YO, 'tread': self.TREAD, 'rise': self.RISE, 'top_z': 0.0, 'bottom_z': self.grade}})
        self.surfaces.append({'name': 'landing', 'poly': rect(sx0, ys, sx1, y_end), 'z': self.grade})
        self.points['behind the bullwheel (house)'] = [-6.2, 0.0]
        for k in range(1, self.RISERS):
            self.proxies.append(proxy('stair step', rect(sx0, YO + (k - 1) * self.TREAD, sx1, YO + k * self.TREAD), -1.9, -self.RISE * k))
        self.proxies.append(proxy('stair landing', rect(sx0, YO + (self.RISERS - 1) * self.TREAD, sx1, y_end), -1.9, self.grade))
        # Railings: deck edges in front of the house, gap at the stair; stair handrails.
        railing(fit, self, [(XM - 0.15, YP + 0.5), (XM - 0.15, YO - 0.15), (sx1 + 0.1, YO - 0.15)], 'timber')
        railing(fit, self, [(sx0 - 0.1, YO - 0.15), (-1.45, YO - 0.15)], 'timber')
        railing(fit, self, [(-1.45, -YO + 0.15), (XM - 0.15, -YO + 0.15), (XM - 0.15, -YP - 0.5)], 'timber')
        self.canopy_and_house(bldg)
        bench(fit, self, 1.3, -7.2, 0)
        return {m.name: m for m in (plat, mach, fit, bldg)}

    def canopy_and_house(self, m):
        YO = self.YO
        canopy(m, self, (-1.2, 3.0, 7.2), 6.9, 0.40, 0.0, 4.95, (-1.75, 7.7), (-1.7, 8.2, 8.8, 7.4, 0.16, SHINGLE, 'courses'), 'canopy post',
               roof_kw={'tails': 0.55}, knee_sect=0.2, knee_len=1.1)
        # Mechanism house: board walls on three sides, a header and gable over the open +x side.
        xh0, xh1 = self.XB, -1.6; zt = 5.2; z_hd = 4.75       # wall top; header bottom over the open +x end (clears the rail frame)
        with m.grained((0, 0, 1)):
            m.box((xh0 + 0.1, 0.0, zt / 2), (0.2, 2 * YO, zt), PANEL)
            for s in (-1, 1):
                m.box(((xh0 + 0.2 + xh1) / 2, s * (YO - 0.1), zt / 2), (xh1 - xh0 - 0.2, 0.2, zt), PANEL)
                self.seat('house side wall', (xh0 + xh1) / 2, s * (YO - 0.1), 0.0)
            m.box((xh1 - 0.1, 0.0, (z_hd + zt) / 2), (0.2, 2 * YO - 0.4, zt - z_hd), PANEL)
        self.seat('house back wall', xh0 + 0.1, 0.0, 0.0)
        # Timber girts and sill across the board walls, proud of them (the concept's horizontal framing).
        for z in (0.10, 2.4, 4.6):
            hgt = 0.30 if z < 0.5 else 0.16
            m.box((xh0 - 0.03, 0.0, z), (0.07, 2 * YO - 0.36, hgt), TIMBER_DARK if z < 0.5 else TIMBER)
            for s in (-1, 1):
                m.box(((xh0 + xh1) / 2 + 0.05, s * (YO + 0.03), z), (xh1 - xh0 - 0.46, 0.07, hgt), TIMBER_DARK if z < 0.5 else TIMBER)
        for x in (xh0 + 0.1, xh1 - 0.1):
            for s in (-1, 1):
                m.box((x, s * (YO - 0.1), (zt - 0.02 - 0.03) / 2), (0.3, 0.3, zt - 0.02 + 0.03), TIMBER)
                self.seat('house corner post', x, s * (YO - 0.1), -0.03, embed=0.03)
        z_ridge, half, t = 6.9, 8.6, 0.16
        z_eave = eave_for(z_ridge, half, t, YO - 0.2, zt - 0.04)
        with m.grained((0, 1, 0)):
            slab_roof(m, xh0 - 0.4, xh1 + 0.22, half, z_eave, z_ridge, t, SHINGLE, rolls='courses', tails=0.6)
        for gx in (xh0 + 0.01, xh1 - 0.19):
            gable(m, gx, gx + 0.18, 0.0, YO - 0.01, zt, (z_ridge, z_eave, half, t), PANEL)
        self.proxies.append(proxy_box('house wall', xh0 + 0.1, 0.0, 0.24, 2 * YO, 0.0, zt))
        for s in (-1, 1):
            self.proxies.append(proxy_box('house wall', (xh0 + xh1) / 2, s * (YO - 0.1), xh1 - xh0, 0.24, 0.0, zt))
        self.proxies.append(proxy('house roof', rect(xh0 - 0.4, -YO - 0.6, xh1 + 0.2, YO + 0.6), z_hd, z_ridge))


STATIONS = {'valley': Valley, 'rim': Rim, 'crater': Crater}


def build(key, p, d, cab, ctx):
    """Build, audit, check and export one station. ctx carries build.py's helpers (shared audit and export)."""
    import json
    st = STATIONS[key](key, p, d); meshes = st.make(); name = f'Station{st.NAME}'
    rows, cop = ctx['audit'](meshes)
    seats = solid.seats(list(meshes.values()), st.seats)
    movers = ctx['movers'](cab); static = list(meshes.values())
    places = st.placements()
    # The running wheels roll on the rail by design: check them against everything but the rail, and the rest of
    # the cabin against everything including the rail. In the attach zone the grip closes on the rope.
    line_p = [(lbl, M) for lbl, M, attach in places if not attach]; mouth_p = [(lbl, M) for lbl, M, attach in places if attach]
    hits = solid.clearance(static, movers, line_p, exclude_tags=('rail',))
    hits += solid.clearance(static, movers, line_p, mover_exclude=('wheel',))
    hits += solid.clearance(static, movers, mouth_p, exclude_tags=('rope', 'rail'))
    hits += solid.clearance(static, movers, mouth_p, exclude_tags=('rope',), mover_exclude=('wheel', 'jaw'))
    opened = cab['cabin'].open_doors(cab['meshes'])
    door_hits = solid.clearance(static, opened, [(f'berth {s:+d}', st.berth(s)) for s in (-1, 1)])
    groove = ctx['groove'](cab, st.rope, st.line_frames())
    # The haul rope (dropped 0.15 m in the station, round the bullwheel) to the cabin at every loop position.
    rope_clear = ctx['rope_check'](cab, st.rope, [(lbl, M, None) for lbl, M, _ in places])
    rope_jaws = ctx['jaw_contact'](cab, st.rope, [(lbl, M, None) for lbl, M, attach in places if attach], seated=False)
    mouth_jaws = ctx['jaw_contact'](cab, st.rope, st.line_frames())         # outside the mouth: each jaw half seated
    rope_station = ctx['static_rope'](static, st.rope, ('bullwheel groove',), 'rope in the bullwheel groove', key)
    # Margin round the loop: the cabin body grown by a margin on every side (ctx['envelope'], the prism the towers
    # gate with) must touch no station structure at any loop position. The platform edge and the pit are the boarding
    # interface (gap and sill gated in walk.py); the running gear works against the rope, the rail and the bullwheel
    # groove, and touches nothing else (the contact check above). The minimum is bracketed to 5 mm by bisection.
    loop = [(lbl, M) for lbl, M, _ in places]; skip = ('platform', 'platform edge', 'pit', 'rope', 'rail', 'bullwheel groove')
    def hits_at(mg):
        return solid.clearance(static, [ctx['envelope'](mg)], loop, exclude_tags=skip)
    gate_hits = hits_at(checks.STATION_LOOP_MARGIN)
    lo, hi = 0.0, 0.6
    if hits_at(0.0):
        hi = 0.0
    elif not hits_at(hi):
        lo = hi
    while hi - lo > 0.005:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if hits_at(mid) else (mid, hi)
    margin = {'min_distance_m': round(lo, 3), 'bracket_m': [round(lo, 3), round(hi, 3)], 'required_m': checks.STATION_LOOP_MARGIN,
              'measured_as': 'the cabin body bounding prism grown by the margin on every side, against the station triangles',
              'excluded': 'platform, its steel edge and the pit (the boarding interface), rope, rail, bullwheel groove',
              'hits_at_required': gate_hits[:6], 'ok': not gate_hits}
    tris = sum(m.tris() for m in meshes.values())
    extra = []
    if hits:
        extra.append(f'cabin touches the station on the loop at {hits[:4]}')
    if door_hits:
        extra.append(f'open doors touch the station at the berth: {door_hits}')
    if not groove['ok']:
        extra.append(f'jaw groove off the rope at the mouth: {groove["failures"]}')
    if not rope_clear['ok']:
        extra.append(f'rope within {rope_clear["required_m"]} m of the cabin on the loop: {rope_clear["where"]}')
    if not margin['ok']:
        extra.append(f'cabin body within {checks.STATION_LOOP_MARGIN} m of the station on the loop: {margin}')
    if not mouth_jaws['ok']:
        extra.append(f'rope not seated in the jaws outside the mouth: {mouth_jaws["failures"]}')
    if not rope_jaws['ok']:
        extra.append(f'rope not seated in the jaws in the attach zone: {rope_jaws["min_distance_from_rope_axis_m"]} at {rope_jaws["where"]}')
    for part in ('intentional', 'clearance'):
        if not rope_station[part]['ok']:
            extra.append(f'rope {part} in the station: {rope_station[part]["min_distance_from_rope_axis_m"]} at {rope_station[part]["where"]}')
    extra += checks.budget_failures('station', tris)
    proxies = st.proxies + st.platform_proxies()
    extra += checks.proxy_failures(proxies)
    extra += checks.floor_support_failures([(n, p, st.slab_z.get(n, 0.0)) for n, p in st.slabs], proxies)
    hulls = ctx['export'](name, meshes, proxies)
    region, walk_proxies = st.walk_layout(cab['cabin'])
    layout = {'station': key, 'levels': st.levels, 'regions': region, 'stairs': st.stairs, 'access': st.access,
              'gates': st.gates, 'berths': st.attachment()['berths'], 'obstacles': walk_proxies,
              'walk_surfaces': [{'name': n, 'poly': [list(q) for q in poly]} for n, poly in st.slabs], 'surfaces': st.surfaces, 'points': st.points,
              'ramp': st.levels[-1] if any(lv.get('z') == 'ramp' for lv in st.levels) else None}
    (ctx['out'] / f'layout_{key}.json').write_text(json.dumps(layout) + '\n')
    entry = {'meshes': rows, 'triangles': tris, 'bounds': ctx['bounds'](meshes), **st.attachment(),
             'collision': {'file': f'assets/GD_{name}_Collision.fbx', 'convex_hulls': hulls},
             'cabin_loop': {'positions': len(places), 'contacts': hits, 'attach_zone_from_mouth_m': ATTACH_ZONE,
                            'doors_open_at_berths_contacts': door_hits, 'jaw_groove_on_rope_at_mouth': groove,
                            'rope_clearance': rope_clear, 'rope_in_jaws_attach_zone': rope_jaws, 'rope_in_jaws_at_mouth': mouth_jaws,
                            'body_margin': margin},
             'rope_and_station': rope_station,
             'stairs': st.stairs, 'coplanar_overlaps': cop,
             'seating': {'checked': len(seats), 'failures': [r for r in seats if r['status'] != 'ok']}}
    return entry, ctx['failures'](rows, cop, seats, extra)
