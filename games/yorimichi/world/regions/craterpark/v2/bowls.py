"""Crater Park v2: the bowl complex (plan/layout.md section 4; owner: agent F).

The Crater Bowl, the Blue Pool and the Peanut are ONE bowl: one lip loop round all three and the floor-level channels
that join them (Crater <-> Pool, Pool <-> Peanut, Peanut <-> Crater), with a deck island in the middle. A rider carves
the whole complex as one loop and never meets a dead end. The structure comes from the physics (layout.md section 2):
- the floor is one smooth surface: level in each bowl, and a C2 ramp (smootherstep) up each channel from the Crater's
  floor to the shallow bowls'. The climb is what bleeds speed toward the shallow bowls' ~10 m/s wall limit, and the
  way back down feeds the Crater;
- the wall is a variable profile swept round the lip: transition R plus vert, from the local wall height
  (layout.BOWLS: Crater R9 + 1 m vert, Pool R2.5 + 0.4, Peanut R3 + 0.3), so a channel's walls ease from one bowl's
  wall into the other's;
- lines join at ports (`ports`): where a line's built surface ends, the bowl wall morphs into that line's own
  section (a level floor strip at floor height, or a roll-in whose crest R is at least 1.1 v^2 / g so nobody is
  launched by accident), and the lip comes down to meet it;
- a flat deck at the rim height surrounds the lip (the island deck in the middle), with steel coping on every lip
  where the wall is a wall; the island's coping is one closed tube.

The plan outline is the zero set of a smooth union of signed distance fields (the Crater's rounded convex polygon,
r4's pool lip fitted from mesh-0098-000, the Peanut's two lobes and a waist, and the channels as tapered capsules),
traced on a 0.25 m raster and smoothed. The Pool is r4's lip loop (16 Fourier harmonics, 0.59 m at most from the
original) turned so its shallow arm opens into the Crater channel.

Frame: native metres, y up, plan (x, z) (dsl.py). Every surface is a quad grid or a constrained Delaunay fill in plan,
so the welded surface is closed (closed mode: a skirt and a base under the deck's outer edge) or open exactly along
its outer edge (on_ground: `Built.foot`, which A's ground meets).
"""
import math
from dataclasses import dataclass, field

import numpy as np

from . import coping as coping_mod
from . import dsl, solids
from .cdt import CDTError, triangulate
from .primitives import Built

G = 9.81
GRID = .25            # metres: the plan raster the outline is traced on
DS = .1               # metres: the dense lip polyline's spacing
K_BLEND = 5.0         # metres: smooth-union radius (rounded hips where a channel meets a bowl)
ROUND = 14.0          # metres: the Crater polygon's corner rounding
ELL = 2.0             # metres: a profile column's length weight against its turn (hybrid column parameter)
TURN = 1.6            # degrees: the most a column or row may turn (validate.DIHEDRAL is 2)
ROW_MAX = 2.0         # metres between rows at most (quad diagonals stay under 4 m)
DECK = 3.0            # metres of flat deck outside the lip (layout.BOWLS deck)
MORPH = 12.0          # metres along the lip over which a wall morphs into a port's section
PORT_PAD = 1.0        # metres of the port's own section past each side of the line
PORT_FLAT = 3.0       # metres: a floor port's level strip into the bowl
CREST_K = 1.1         # a roll-in crest's radius is at least CREST_K v^2 / g (layout.md 2: R >= v^2/g never launches)
ENTRY_SPEED = 25.0    # m/s: the Crater's allowed entry (layout.md 2), used for a roll-in's crest
FLOOR_STEP = (.6, 2.0)   # metres between floor fill points: on channel ramps, in the level bowls
DECK_STEP = 2.0
MATERIAL = {'crater_bowl': dsl.CONCRETE, 'blue_pool': 'material_019', 'peanut': dsl.CONCRETE,
            'bowl_channels': dsl.CONCRETE, 'bowl_deck': dsl.DECK}
TILE = 'material_007'     # the pool's tile band (r4's tile_edge) on its vert
FORBIDDEN = ('material_004',)

# r4's Blue Pool lip loop (mesh-0098-000, native metres about r4's pool centre (1296.3, 910.7)): the boundary edges at
# the coping height (y > -22.6), arc-length resampled and low-passed to 16 Fourier harmonics (at most 0.59 m from the
# original loop; tightest outward bulge R 2.86 m), then 96 points. Counter-clockwise; the shallow arm points along +x.
POOL_R4 = np.array([
    (-20.66, -5.69), (-20.30, -7.00), (-19.65, -8.20), (-18.79, -9.25), (-17.75, -10.12), (-16.54, -10.74),
    (-15.22, -11.06), (-13.86, -11.08), (-12.53, -10.81), (-11.28, -10.27), (-10.15, -9.52), (-9.10, -8.65),
    (-8.07, -7.76), (-6.98, -6.95), (-5.79, -6.28), (-4.51, -5.82), (-3.17, -5.59), (-1.81, -5.60), (-0.46, -5.80),
    (0.84, -6.17), (2.09, -6.71), (3.26, -7.42), (4.33, -8.26), (5.35, -9.16), (6.42, -10.00), (7.60, -10.67),
    (8.89, -11.09), (10.25, -11.19), (11.58, -10.92), (12.79, -10.31), (13.84, -9.45), (14.71, -8.40), (15.36, -7.21),
    (15.69, -5.89), (15.62, -4.54), (15.26, -3.23), (14.78, -1.95), (14.45, -0.63), (14.89, 0.61), (16.02, 1.35),
    (17.28, 1.87), (18.56, 2.33), (19.83, 2.83), (21.08, 3.37), (22.31, 3.95), (23.52, 4.57), (24.67, 5.30),
    (25.67, 6.22), (26.37, 7.38), (26.66, 8.71), (26.56, 10.06), (26.11, 11.34), (25.35, 12.47), (24.29, 13.32),
    (23.03, 13.81), (21.67, 13.91), (20.33, 13.70), (19.04, 13.26), (17.81, 12.68), (16.60, 12.05), (15.39, 11.42),
    (14.17, 10.83), (12.93, 10.27), (11.67, 9.75), (10.38, 9.32), (9.04, 9.07), (7.68, 9.01), (6.32, 9.02),
    (4.96, 8.92), (3.65, 8.55), (2.45, 7.92), (1.31, 7.17), (0.15, 6.46), (-1.15, 6.07), (-2.45, 6.38), (-3.48, 7.27),
    (-4.34, 8.33), (-5.27, 9.32), (-6.44, 10.00), (-7.78, 10.19), (-9.11, 9.91), (-10.26, 9.20), (-10.98, 8.06),
    (-11.22, 6.72), (-11.20, 5.36), (-11.24, 4.00), (-11.75, 2.76), (-12.86, 2.00), (-14.17, 1.64), (-15.51, 1.38),
    (-16.82, 1.00), (-17.98, 0.31), (-18.93, -0.66), (-19.69, -1.80), (-20.28, -3.02), (-20.63, -4.33),
])
POOL_ARM_DEG = 32.0       # the arm's heading in POOL_R4's frame (base (16, 2) to tip (26.7, 8.7))

# Where the shallow bowls sit, and the channels (F's plan; layout.BOWLS gives sizes, heights and walls). The Pool and
# the Peanut sit south of the Crater so that each channel is long enough for a smooth 7 m climb (about 40 m of ramp at
# most 20 degrees, crest and foot radius at least 35 m), and the Pool turns its arm north into the Crater channel.
SITE = {
    'blue_pool': {'centre': (1392.0, 838.0), 'arm_deg': 90.0},
    'peanut': {'centre': (1322.0, 852.0), 'axis': 5.0},
    'channels': (
        # (from bowl, to bowl, from point, to point, width at from, width at to): lip-to-lip widths
        ('crater_bowl', 'blue_pool', (1395.0, 915.0), (1393.0, 858.0), 24.0, 9.0),
        ('blue_pool', 'peanut', (1374.0, 838.0), (1336.0, 851.0), 9.0, 10.0),
        ('peanut', 'crater_bowl', (1318.0, 858.0), (1336.0, 912.0), 10.0, 24.0),
    ),
}


# ---------------------------------------------------------------------------------------------------- small helpers

def smootherstep(x):
    x = np.clip(x, 0., 1.)
    return x * x * x * (x * (6 * x - 15) + 10)


def _rot(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])


def _area(P):
    return .5 * float((P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]).sum())


def _seg_dist(Q, A, B):
    """Distance from points Q (n, 2) to segments A->B (m, 2): (n, m)."""
    d = B - A
    u = np.clip(((Q[:, None] - A[None]) * d[None]).sum(-1) / np.maximum((d * d).sum(1), 1e-300)[None], 0, 1)
    return np.linalg.norm(Q[:, None] - (A[None] + u[..., None] * d[None]), axis=-1)


def sdf_polygon(Q, P):
    """Signed distance (negative inside) from points Q (n, 2) to the closed polygon P (k, 2)."""
    A, B = P, np.roll(P, -1, 0)
    out = np.empty(len(Q))
    for i0 in range(0, len(Q), 4096):
        q = Q[i0:i0 + 4096]
        d = _seg_dist(q, A, B).min(1)
        out[i0:i0 + 4096] = np.where(solids._inside(q, P), -d, d)
    return out


def smin(a, b, k):
    """Polynomial smooth minimum: rounds a union's concave corners with radius about k."""
    h = np.maximum(k - np.abs(a - b), 0.) / k
    return np.minimum(a, b) - h * h * k / 4


def clip_halfplane(P, n, c):
    """The convex polygon P (k, 2) clipped to {p : p . n <= c}."""
    out = []
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        da, db = a @ n - c, b @ n - c
        if da <= 0:
            out.append(a)
        if da * db < 0:
            out.append(a + (b - a) * (da / (da - db)))
    return np.asarray(out)


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def convex_hull(P):
    P = np.unique(np.asarray(P, 'f8'), axis=0)
    P = P[np.lexsort((P[:, 1], P[:, 0]))]

    def half(pts):
        h = []
        for p in pts:
            while len(h) >= 2 and _cross2(h[-1] - h[-2], p - h[-2]) <= 1e-12:
                h.pop()
            h.append(p)
        return h
    lo, hi = half(P), half(P[::-1])
    return np.asarray(lo[:-1] + hi[:-1])


# ---------------------------------------------------------------------------------------------------- ports

@dataclass
class Port:
    """Where a line's built surface ends against the bowl: the lip there is the straight `row` (k, 3) across the line,
    the line arrives heading `heading` (unit plan vector into the bowl) at height y with slope `slope_deg` (negative:
    falling into the bowl) and about `speed` m/s; `kind` is 'floor' (level, at the floor), 'rim' (at the rim) or
    'mid'."""
    line: str
    kind: str
    point: np.ndarray
    heading: np.ndarray
    y: float
    slope_deg: float
    width: float
    speed: float
    row: np.ndarray = None

    def as_dict(self):
        return {'line': self.line, 'kind': self.kind, 'point': [float(self.point[0]), self.y, float(self.point[1])],
                'heading_deg': math.degrees(math.atan2(self.heading[1], self.heading[0])),
                'slope_deg': self.slope_deg, 'width': self.width, 'speed': self.speed,
                'row': None if self.row is None else np.round(self.row, 6).tolist()}


def port_row(point, heading, y, width):
    """The port's lip vertices, sampled across the line as B's ramp samples a straight path (linspace, at most
    max_edge / sqrt 2 apart), ordered from the line's left edge to its right (along the lip, counter-clockwise)."""
    n = max(1, int(math.ceil(width / (dsl.RIDING_TESS.max_edge / math.sqrt(2)) - 1e-9)))
    w = np.linspace(width / 2, -width / 2, n + 1)
    left = np.array([-heading[1], heading[0]])
    p = np.asarray(point, 'f8')[None] + w[:, None] * left[None]
    return np.stack([p[:, 0], np.full(len(w), float(y)), p[:, 1]], 1)


def ports(data=None, rows=None):
    """Every line's port at its actual built end, not its unbuilt profile tail.
    rows: {line id: (k, 3)} supplies the built line's exact seam row.
    """
    data = data or _layout()
    crater = _bowl(data, 'crater_bowl')
    out = []
    for line in data.LINES:
        k = np.asarray(data.knots(line, .25), 'f8')
        s = float(data.build_stop(line)) if hasattr(data, 'build_stop') else float(k[-1, 0])
        if any(f.kind == 'gap' and f.s0 + 1e-6 < s < f.s1 - 1e-6 for f in line.features):
            raise ValueError(f'bowls: {line.id} ends inside an open gap')
        y = float(np.interp(s, k[:, 0], k[:, 1]))
        a = float(np.interp(s, k[:, 0], k[:, 2]))
        p, tg = line.path.at(s)
        width = max(f.width for f in line.features if f.s0 <= s + 1e-6) if line.features else 16.
        last = [f for f in line.features if f.s0 <= s + 1e-6]
        width = last[-1].width if last else width
        if y > crater.rim_y + .3 or y < crater.floor_y - .3:
            kind = 'skip'                  # not between the floor and the rim: the line does not end at this bowl
        elif abs(y - crater.floor_y) < .3:
            kind = 'floor'
        elif abs(y - crater.rim_y) < .3:
            kind = 'rim'
        else:
            kind = 'mid'
        drop = max(line.y0 - y, 0.)
        speed = min(ENTRY_SPEED, .92 * math.sqrt(2 * G * drop))
        port = Port(line.id, kind, np.asarray(p, 'f8'), np.asarray(tg, 'f8') / np.linalg.norm(tg), float(y),
                    float(a), float(width), float(speed))
        port.row = np.asarray(rows[line.id], 'f8') if rows and line.id in rows else port_row(p, port.heading, y, width)
        out.append(port)
    return out


# ---------------------------------------------------------------------------------------------------- sections

class Section:
    """A wall's cross-section from the floor edge (d = reach, y = floor) to the lip (d = 0): parts ('arc', R, to_deg)
    and ('line', L) from a level start, turning up. Evaluated at a hybrid column parameter (turn + length / ELL), so a
    tight transition and a long ramp both get columns at most TURN degrees apart for a shared column count."""

    def __init__(self, floor, parts):
        self.floor = float(floor)
        xy_parts = [np.zeros((1, 2), 'f8')]
        ang_parts = [np.zeros(1, 'f8')]
        q_parts = [np.zeros(1, 'f8')]
        last_xy = np.zeros(2, 'f8')
        last_q = 0.
        a = 0.
        for p in parts:
            if p[0] == 'arc':
                R, to = p[1], math.radians(p[2])
                if abs(to - a) < 1e-12 or R <= 0:
                    continue
                n = max(8, int(math.ceil(abs(math.degrees(to - a)) / .25)))
                th = np.linspace(a, to, n + 1)[1:]
                sg = 1. if to > a else -1.
                c = last_xy + sg * R * np.array([-math.sin(a), math.cos(a)])
                seg_xy = c + sg * R * np.c_[np.sin(th), -np.cos(th)]
                dq = abs(th[1] - th[0] if len(th) > 1 else to - a) * (1 + R / ELL)
                seg_q = last_q + dq * np.arange(1, len(th) + 1, dtype='f8')
                xy_parts.append(seg_xy); ang_parts.append(th); q_parts.append(seg_q)
                last_xy = seg_xy[-1]; last_q = float(seg_q[-1])
                a = to
            else:
                L = p[1]
                if L <= 1e-9:
                    continue
                n = max(2, int(math.ceil(L / .05)))
                d = np.array([math.cos(a), math.sin(a)])
                idx = np.arange(1, n + 1, dtype='f8')
                seg_xy = last_xy + (idx * (L / n))[:, None] * d
                seg_q = last_q + idx * (L / n / ELL)
                xy_parts.append(seg_xy); ang_parts.append(np.full(n, a, 'f8')); q_parts.append(seg_q)
                last_xy = seg_xy[-1]; last_q = float(seg_q[-1])
        self.xy = np.concatenate(xy_parts); self.ang = np.concatenate(ang_parts); self.q = np.concatenate(q_parts)
        self.reach = float(self.xy[-1, 0]); self.height = float(self.xy[-1, 1])
        self.top_deg = math.degrees(a)
        self.arcs = [p[1] for p in parts if p[0] == 'arc' and p[1] > 0]

    def columns_needed(self):
        """Columns for at most TURN degrees per column on every arc."""
        if not self.arcs:
            return 2
        per = min(math.radians(TURN) * (1 + R / ELL) for R in self.arcs)
        return int(math.ceil(self.q[-1] / per))

    def at(self, u):
        """(d, y) at column parameters u in [0, 1]: d inward from the lip, y absolute."""
        qq = np.asarray(u) * self.q[-1]
        x = np.interp(qq, self.q, self.xy[:, 0]); y = np.interp(qq, self.q, self.xy[:, 1])
        return np.stack([self.reach - x, self.floor + y], -1)


def wall_section(floor, H, R, vert):
    """A bowl wall H high: a transition of radius R to vertical, then vert (or, lower than R, a transition cut at H)."""
    if H >= R:
        return Section(floor, [('arc', R, 90.), ('line', H - R)])
    if H <= 1e-6:
        return Section(floor, [('line', .5)])
    return Section(floor, [('arc', R, math.degrees(math.acos(1 - H / R)))])


def rollin_section(floor, H, top_deg, crest, foot=20., slope=25.):
    """A roll-in from a line arriving at `top_deg` (degrees, rising outward) down H to the floor: a crest of radius
    `crest`, a straight at `slope`, a foot of radius `foot`."""
    for sl in np.arange(slope, 4., -1.):
        rise = foot * (1 - math.cos(math.radians(sl))) + crest * (math.cos(math.radians(top_deg))
                                                                  - math.cos(math.radians(sl)))
        if rise <= H + 1e-9 and sl > top_deg:
            L = (H - rise) / math.sin(math.radians(sl))
            return Section(floor, [('arc', foot, sl), ('line', L), ('arc', crest, top_deg)])
    # too shallow for any straight: a single arc to the top angle
    R = H / max(1 - math.cos(math.radians(max(top_deg, 1.))), 1e-6)
    return Section(floor, [('arc', R, max(top_deg, 1.))])


def flat_section(floor, top_y, reach=PORT_FLAT):
    """@cc [owner:fontanierh,label:correctness] signed-floor-port-section
    A floor port above or below its floor MUST have a finite circular section
    ending exactly at the requested horizontal reach and height. A lower port
    MUST NOT produce an unbounded radius by clamping the sign of its angle.
    """
    h = top_y - floor
    if abs(h) < 1e-8:
        return Section(floor, [('line', reach)])
    radius = (reach * reach + h * h) / (2. * abs(h))
    angle = math.degrees(2. * math.atan2(h, reach))
    return Section(floor, [('arc', radius, angle)])


# ---------------------------------------------------------------------------------------------------- the plan

@dataclass
class Plan:
    rim: float
    floors: dict                  # bowl id -> floor y
    walls: list                   # [(H, R, vert)] anchors, sorted by H
    shapes: dict                  # bowl id -> callable sdf(Q)
    channels: list                # [dict]
    ports: list                   # [Port]
    crater_poly: np.ndarray = None
    pool_poly: np.ndarray = None
    notes: list = field(default_factory=list)

    def sdf(self, Q):
        d = None
        for f in self.shapes.values():
            v = f(Q)
            d = v if d is None else smin(d, v, K_BLEND)
        for c in self.channels:
            d = smin(d, c['sdf'](Q), K_BLEND)
        return d

    def bowl_of(self, Q):
        """Which bowl each plan point belongs to ('bowl_channels' inside a channel's ramp band)."""
        names = list(self.shapes)
        D = np.stack([self.shapes[n](Q) for n in names], 1)
        out = np.asarray(names, object)[np.argmin(D, 1)]
        for c in self.channels:
            u, lat = c['proj'](Q)
            m = (u > c['u0']) & (u < c['u1']) & (lat < c['band'](u))
            out[m] = 'bowl_channels'
        return out

    def floor(self, Q):
        """The floor height at plan points Q (n, 2): each bowl's level floor, C2 ramps up the channels."""
        Q = np.atleast_2d(np.asarray(Q, 'f8'))
        names = list(self.shapes)
        D = np.stack([self.shapes[n](Q) for n in names], 1)
        y = np.asarray([self.floors[n] for n in names])[np.argmin(D, 1)]
        for c in self.channels:
            u, lat = c['proj'](Q)
            m = (u >= 0) & (u <= 1) & (lat < c['band'](u))
            if m.any():
                s = smootherstep((u[m] - c['u0']) / (c['u1'] - c['u0']))
                y[m] = c['ya'] + (c['yb'] - c['ya']) * s
        return y

    def wall(self, H):
        """(R, vert) for a wall H high: interpolated between the bowls' own walls."""
        Hs = np.array([w[0] for w in self.walls]); Rs = np.array([w[1] for w in self.walls])
        Vs = np.array([w[2] for w in self.walls])
        R = float(np.interp(H, Hs, Rs)); v = float(np.interp(H, Hs, Vs))
        if H < Hs[0]:
            R = Rs[0] * H / Hs[0]; v = Vs[0] * H / Hs[0]
        return min(R, max(H - v, 1e-3)), max(min(v, H - R), 0.)


def _layout():
    from . import layout
    return layout


def _bowl(data, name):
    return next(b for b in data.BOWLS if b.id == name)


def _crater_polygon(bowl, ports_):
    """The Crater's convex plan polygon: its size round its centre on its axis, extended to reach every port that
    lies outside, and cut by every port's entry plane, so each port is a straight edge."""
    c = np.asarray(bowl.centre, 'f8'); ax = math.radians(bowl.axis)
    u = np.array([math.cos(ax), math.sin(ax)]); v = np.array([-u[1], u[0]])
    L, W = bowl.size[0] / 2, bowl.size[1] / 2
    rect = np.array([c - L * u - W * v, c + L * u - W * v, c + L * u + W * v, c - L * u + W * v])
    pts = list(rect)
    cuts = []
    for p in ports_:
        half = p.width / 2 + PORT_PAD + MORPH + ROUND
        left = np.array([-p.heading[1], p.heading[0]])
        a, b = p.point + half * left, p.point - half * left
        if sdf_polygon(p.point[None], rect)[0] > 0:
            pts += [a, b]                   # outside: the bowl grows to reach it (its edge is the hull's)
        cuts.append((p.heading, p.point))    # outside ports also need an exact seam plane
    P = convex_hull(np.asarray(pts))
    if _area(P) < 0:
        P = P[::-1]
    for h, q in cuts:                      # the bowl lies ahead of the port: (x - q) . h >= 0
        P = clip_halfplane(P, -h, float(-h @ q))
    return P


def _rounded_sdf(P, r):
    """The signed distance to the convex polygon P with its corners rounded by r (its edges stay straight)."""
    Q = np.array([[-1e6, -1e6], [1e6, -1e6], [1e6, 1e6], [-1e6, 1e6]])
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        t = (b - a) / np.linalg.norm(b - a); n = np.array([t[1], -t[0]])      # outward for counter-clockwise
        Q = clip_halfplane(Q, n, float(n @ a) - r)
    return lambda X: sdf_polygon(X, Q) - r


def plan(data=None, port_rows=None, only=None):
    """The complex's plan. only=('crater_bowl',): the Crater Bowl alone (no Pool, Peanut or channels)."""
    data = data or _layout()
    crater, pool, peanut = (_bowl(data, n) for n in ('crater_bowl', 'blue_pool', 'peanut'))
    rim = crater.rim_y
    if any(abs(b.rim_y - rim) > 1e-9 for b in (pool, peanut)):
        raise ValueError('bowls: the complex has one deck; every bowl rim must be at the same height')
    every = ports(data, port_rows)
    ps = [p for p in every if p.kind != 'skip']
    floors = {'crater_bowl': crater.floor_y, 'blue_pool': pool.floor_y, 'peanut': peanut.floor_y}
    walls = sorted({(round(b.rim_y - b.floor_y, 6), b.r, b.vert) for b in (crater, pool, peanut)})
    P = _crater_polygon(crater, ps)
    shapes = {'crater_bowl': _rounded_sdf(P, ROUND)}
    if only is not None and set(only) == {'crater_bowl'}:
        pl = Plan(rim, floors, [w for w in walls if abs(w[0] - (crater.rim_y - crater.floor_y)) < 1e-6], shapes, [],
                  ps, P, P)
        pl.notes += [f'port {p.line} skipped: its line ends at y {p.y:.2f}, outside the rim-floor range' for p in every
                     if p.kind == 'skip']
        return pl
    # the Pool: r4's loop, turned so its arm points along arm_deg, at its centre
    sp = SITE['blue_pool']
    pp = (POOL_R4 @ _rot(sp['arm_deg'] - POOL_ARM_DEG).T) + np.asarray(sp['centre'])
    shapes['blue_pool'] = lambda X, pp=pp: sdf_polygon(X, pp)
    # the Peanut: two lobes of its width, its length apart, smooth-joined at a waist (the hip)
    sn = SITE['peanut']
    a = math.radians(sn['axis']); ua = np.array([math.cos(a), math.sin(a)])
    r = peanut.size[1] / 2; off = peanut.size[0] / 2 - r
    c1, c2 = np.asarray(sn['centre']) - off * ua, np.asarray(sn['centre']) + off * ua
    shapes['peanut'] = lambda X, c1=c1, c2=c2, r=r: smin(np.linalg.norm(X - c1, axis=1) - r,
                                                        np.linalg.norm(X - c2, axis=1) - r, 1.6 * r)
    channels = []
    for fa, fb, A, B, wa, wb in SITE['channels']:
        A, B = np.asarray(A, 'f8'), np.asarray(B, 'f8')
        d = B - A; Ln = float(np.linalg.norm(d)); t = d / Ln; nrm = np.array([-t[1], t[0]])

        def proj(X, A=A, t=t, nrm=nrm, Ln=Ln):
            rel = X - A
            return rel @ t / Ln, np.abs(rel @ nrm)

        def width(u, wa=wa, wb=wb):
            return wa + (wb - wa) * np.clip(u, 0, 1)

        def sdf_c(X, proj=proj, width=width, A=A, B=B, Ln=Ln):
            u, lat = proj(X)
            uc = np.clip(u, 0, 1)
            along = np.where(u < 0, -u * Ln, np.where(u > 1, (u - 1) * Ln, 0.))
            return np.hypot(np.maximum(lat - width(uc) / 2, 0.), along) + np.minimum(lat - width(uc) / 2, 0.) * (along == 0)
        # the ramp runs where the channel is clear of both bowls' shapes (plus the blend), level beyond
        uu = np.linspace(0, 1, 401); line = A[None] + uu[:, None] * d[None]
        out_a = shapes[fa](line) > K_BLEND + 1.; out_b = shapes[fb](line) > K_BLEND + 1.
        free = out_a & out_b
        if not free.any():
            raise ValueError(f'bowls: the channel {fa} -> {fb} has no room for a ramp')
        u0, u1 = float(uu[free][0]), float(uu[free][-1])
        channels.append({'from': fa, 'to': fb, 'A': A, 'B': B, 'length': Ln, 'proj': proj, 'width': width,
                         'sdf': sdf_c, 'u0': u0, 'u1': u1, 'ya': floors[fa], 'yb': floors[fb],
                         'band': lambda u, width=width: width(np.clip(u, 0, 1)) / 2 + 2.})
    pl = Plan(rim, floors, walls, shapes, channels, ps, P, pp)
    pl.notes += [f'port {p.line} skipped: its line ends at y {p.y:.2f}, outside the rim-floor range' for p in every
                 if p.kind == 'skip']
    return pl


# ---------------------------------------------------------------------------------------------------- contours

def _trace(F, x0, z0, h):
    """Closed zero-level loops of the raster F (rows z, columns x; negative inside), by marching squares: (k, 2)
    plan polylines, counter-clockwise round the inside."""
    ny, nx = F.shape
    inside = F < 0
    # crossing points on horizontal edges (i, j)-(i, j+1) and vertical edges (i, j)-(i+1, j)
    def hpt(i, j):
        a, b = F[i, j], F[i, j + 1]
        return np.array([x0 + h * (j + a / (a - b)), z0 + h * i])

    def vpt(i, j):
        a, b = F[i, j], F[i + 1, j]
        return np.array([x0 + h * j, z0 + h * (i + a / (a - b))])
    case = (inside[:-1, :-1].astype(int) | (inside[:-1, 1:] << 1) | (inside[1:, 1:] << 2) | (inside[1:, :-1] << 3))
    nxt = {}
    # edges of cell (i, j): 0 bottom h(i, j), 1 right v(i, j+1), 2 top h(i+1, j), 3 left v(i, j)
    def key(i, j, e):
        return (('h', i, j), ('v', i, j + 1), ('h', i + 1, j), ('v', i, j))[e]
    # segments directed so the inside is on the left: (from edge, to edge) per case
    table = {1: [(3, 0)], 2: [(0, 1)], 3: [(3, 1)], 4: [(1, 2)], 6: [(0, 2)], 7: [(3, 2)], 8: [(2, 3)],
             9: [(2, 0)], 11: [(2, 1)], 12: [(1, 3)], 13: [(1, 0)], 14: [(0, 3)]}
    for i, j in zip(*np.nonzero((case > 0) & (case < 15)), strict=True):
        c = int(case[i, j])
        if c in (5, 10):
            centre = F[i:i + 2, j:j + 2].mean() < 0
            segs = {5: [(3, 2), (1, 0)] if centre else [(3, 0), (1, 2)],
                    10: [(0, 3), (2, 1)] if centre else [(0, 1), (2, 3)]}[c]
        else:
            segs = table[c]
        for a, b in segs:
            nxt[key(i, j, a)] = key(i, j, b)
    loops, seen = [], set()
    for k0 in list(nxt):
        if k0 in seen:
            continue
        loop, k = [], k0
        while k not in seen:
            seen.add(k)
            loop.append(hpt(k[1], k[2]) if k[0] == 'h' else vpt(k[1], k[2]))
            k = nxt[k]
        loops.append(np.asarray(loop))
    return loops


class Loop:
    """A closed lip polyline, densely resampled (DS) and smoothed, with the bowl on its left: point, unit tangent,
    inward normal (into the bowl) and the turning per metre at any arc length t."""

    def __init__(self, P, smooth=3, normal_span=.3):
        self.normal_span = float(normal_span)
        P = np.asarray(P, 'f8')
        P = _resample(P, DS)
        for _ in range(smooth):                       # Taubin smoothing: no shrinking
            for lam in (.5, -.53):
                P = P + lam * ((np.roll(P, 1, 0) + np.roll(P, -1, 0)) / 2 - P)
        self.P = _resample(P, DS)
        self._index()

    def _index(self):
        P = self.P
        seg = np.linalg.norm(np.roll(P, -1, 0) - P, axis=1)
        self.s = np.concatenate([[0.], np.cumsum(seg)]); self.length = float(self.s[-1])
        k = max(1, int(round(self.normal_span / DS)))
        T = np.roll(P, -k, 0) - np.roll(P, k, 0)
        self.T = T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
        self.N = np.stack([-self.T[:, 1], self.T[:, 0]], 1)
        ang = np.unwrap(np.arctan2(self.T[:, 1], self.T[:, 0]))
        self.turn = np.concatenate([ang, [ang[0] + 2 * np.pi * round((ang[-1] - ang[0]) / (2 * np.pi))]])

    def snap(self, a, b):
        """Make the stretch near the straight segment a-b (plan) exactly straight."""
        d = b - a; L = np.linalg.norm(d); t = d / L; n = np.array([-t[1], t[0]])
        rel = self.P - a
        u = rel @ t; lat = rel @ n
        m = (u > -.5) & (u < L + .5) & (np.abs(lat) < 1.)
        self.P[m] = a + np.clip(u[m], 0, L)[:, None] * t
        self.P = _resample(self.P, DS)
        self._index()

    def _interp(self, t, A):
        t = np.mod(np.asarray(t, 'f8'), self.length)
        A2 = np.concatenate([A, A[:1]])
        return np.stack([np.interp(t, self.s, A2[:, k]) for k in range(A.shape[1])], -1)

    def point(self, t):
        return self._interp(t, self.P)

    def tangent(self, t):
        T = self._interp(t, self.T)
        return T / np.linalg.norm(T, axis=-1, keepdims=True)

    def inward(self, t):
        T = self.tangent(t)
        return np.stack([-T[..., 1], T[..., 0]], -1)

    def locate(self, q):
        """The arc length of the loop point nearest to plan point q."""
        i = int(np.argmin(np.linalg.norm(self.P - np.asarray(q)[None], axis=1)))
        return float(self.s[i])

    def turning(self, t):
        return np.interp(np.mod(t, self.length), self.s, self.turn)


def _resample(P, ds):
    Q = np.concatenate([P, P[:1]])
    s = np.concatenate([[0.], np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))])
    n = max(8, int(round(s[-1] / ds)))
    u = np.linspace(0, s[-1], n + 1)[:-1]
    return np.stack([np.interp(u, s, Q[:, 0]), np.interp(u, s, Q[:, 1])], 1)


def outline(pl, h=GRID, margin=DECK + 8.):
    """The lip loops of the plan: the outer one (counter-clockwise) and the islands' (clockwise), each a Loop with
    the bowl on its left."""
    lo = np.full(2, np.inf); hi = np.full(2, -np.inf)
    for P in (pl.crater_poly, pl.pool_poly):
        lo = np.minimum(lo, P.min(0)); hi = np.maximum(hi, P.max(0))
    for c in pl.channels:
        lo = np.minimum(lo, np.minimum(c['A'], c['B'])); hi = np.maximum(hi, np.maximum(c['A'], c['B']))
    lo -= margin + 20; hi += margin + 20
    xs = np.arange(lo[0], hi[0] + h, h); zs = np.arange(lo[1], hi[1] + h, h)
    X, Z = np.meshgrid(xs, zs)
    Q = np.stack([X.ravel(), Z.ravel()], 1)
    F = pl.sdf(Q).reshape(X.shape)
    loops = _trace(F, xs[0], zs[0], h)
    loops = [L for L in loops if len(L) > 16]
    loops.sort(key=lambda L: -abs(_area(L)))
    return loops, (xs, zs, F)


# ---------------------------------------------------------------------------------------------------- the ring

@dataclass
class Ring:
    loop: Loop
    t: np.ndarray                 # row arc lengths
    P: np.ndarray                 # (rows, cols, 3)
    Nrm: np.ndarray               # (rows, cols, 3) air-side unit normals
    w: np.ndarray                 # (rows,) port weight (0: a plain wall with coping)
    bowl: np.ndarray              # (rows,) bowl id of the row
    vert: np.ndarray              # (rows,) vert height of the plain wall
    locked: np.ndarray            # (rows,) rows on a port's own row (never moved or split)
    closed: bool = True


def _zones(loop, ps, rim):
    """Per port on this loop: (t centre, half width of the port's own section, its Section maker, port)."""
    out = []
    for p in ps:
        tc = loop.locate(p.point)
        if np.linalg.norm(loop.point(tc) - p.point) > 1.:
            raise ValueError(f'bowls: {p.line} entry does not meet the bowl boundary')
        out.append((tc, p.width / 2 + PORT_PAD, p))
    return out


def _port_weight(loop, zones, t):
    w = np.zeros(len(t)); which = np.full(len(t), -1)
    for k, (tc, half, _) in enumerate(zones):
        d = np.abs((t - tc + loop.length / 2) % loop.length - loop.length / 2)
        wk = 1 - smootherstep((d - half) / MORPH)
        better = wk > w
        w = np.where(better, wk, w); which = np.where(better, k, which)
    return w, which


def _row_section(pl, loop, t, zones, w, k):
    """The Section for one row: the plain wall at the local floor, morphed toward its port's section by w."""
    L = loop.point(t); n = loop.inward(t)
    y = pl.floor(L[None])[0]
    reach = 0.
    for _ in range(6):                                # the floor edge sits a transition's reach inside the lip
        H = pl.rim - y
        R, v = pl.wall(H)
        reach = R if H >= R else math.sqrt(max(H * (2 * R - H), 0.))
        y = pl.floor((L + reach * n)[None])[0]
    H = pl.rim - y
    R, v = pl.wall(H)
    wall = wall_section(y, H, R, v)
    port = None
    if k >= 0 and w > 0:
        p = zones[k][2]
        if p.kind == 'floor':
            port = flat_section(y, p.y)
        else:
            crest = max(20., CREST_K * p.speed ** 2 / G)
            port = rollin_section(y, p.y - y, max(-p.slope_deg, 0.), crest)
    return wall, port, v


def _ring_rows(pl, loop, zones, t, N, _cache=None):
    w, which = _port_weight(loop, zones, t)
    u = np.linspace(0., 1., N)
    rows, verts, secs = [], [], []
    for ti, wi, ki in zip(t, w, which, strict=True):
        t_key = float(ti)
        if _cache is not None and t_key in _cache:
            dy, v, sec = _cache[t_key]
        else:
            wall, port, v = _row_section(pl, loop, ti, zones, wi, ki)
            dy = wall.at(u)
            if port is not None:
                dy = (1 - wi) * dy + wi * port.at(u)
            sec = (wall, port)
            if _cache is not None:
                _cache[t_key] = (dy, v, sec)
        rows.append(dy); verts.append(v); secs.append(sec)
    D = np.asarray(rows)                                  # (rows, N, 2): inward distance, height
    L = loop.point(t); n = loop.inward(t)
    P = np.stack([L[:, None, 0] + D[..., 0] * n[:, None, 0], D[..., 1], L[:, None, 1] + D[..., 0] * n[:, None, 1]], -1)
    return P, w, np.asarray(verts), secs


def _normals(P):
    """Air-side unit normals of a ring grid (rows along the lip counter-clockwise round the bowl, columns floor to
    lip): cross(d/drow, d/dcolumn) points up from the floor and into the bowl from the walls."""
    dr = np.gradient(P, axis=0); dc = np.gradient(P, axis=1)
    n = np.cross(dr, dc)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)


def _quad_normals(P):
    a = P[1:, 1:] - P[:-1, :-1]; b = P[:-1, 1:] - P[1:, :-1]
    n = np.cross(b, a)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-12)


def _angle(a, b):
    return np.degrees(np.arccos(np.clip((a * b).sum(-1), -1, 1)))


def ring(pl, loop, zones, N, max_rounds=12):
    """The wall grid round one lip loop: rows at most ROW_MAX apart and TURN degrees of plan turn, split until no
    two neighbouring rows' faces differ by more than TURN degrees (port rows are kept exactly)."""
    L = loop.length
    n = max(8, int(math.ceil(L / ROW_MAX)))
    t = np.linspace(0, L, n, endpoint=False)
    ts = loop.s[:-1]
    dth = np.abs(np.diff(np.concatenate([loop.turn[:-1], [loop.turn[-1]]])))
    cum = np.concatenate([[0.], np.cumsum(dth)])[:len(ts)]
    step = math.radians(TURN) * .9
    if cum[-1] > step:
        t = np.union1d(t, np.interp(np.arange(step, cum[-1], step), cum, ts))
    lock = []
    for tc, half, p in zones:
        for q in p.row:
            lock.append(loop.locate(q[[0, 2]]))
        if p.row is not None:
            lock_lo, lock_hi = min(lock[-len(p.row):]), max(lock[-len(p.row):])
            t = t[~((t > lock_lo - .05) & (t < lock_hi + .05))]
    t = np.unique(np.concatenate([t, lock]))
    t = t[np.r_[True, np.diff(t) > .02]]
    lockset = np.asarray(sorted(lock))
    row_cache = {}
    for _ in range(max_rounds):
        P, w, verts, _ = _ring_rows(pl, loop, zones, t, N, _cache=row_cache)
        _put_ports(P, t, loop, zones)
        qn = _quad_normals(np.concatenate([P, P[:1]]))
        ang = _angle(qn[1:], qn[:-1]).max(1)                     # across row i+1 (between quads i and i+1)
        ang = np.concatenate([[_angle(qn[0], qn[-1]).max()], ang])   # row 0, across the closing seam
        bad = np.flatnonzero(ang > TURN)
        if not len(bad):
            break
        tn = np.concatenate([t, [t[0] + L]])
        add = []
        for i in bad:                                     # split both quads that meet at row i
            for a, b in ((i - 1, i), (i, i + 1)):
                ta, tb = tn[a % len(t)] + (L if a < 0 else 0) - (L if a < 0 else 0), tn[b] if b < len(tn) else tn[-1]
                ta = tn[a] if a >= 0 else tn[-2] - L
                mid = (ta + tb) / 2
                if np.any((lockset > min(ta, tb) + 1e-6) & (lockset < max(ta, tb) - 1e-6)) or tb - ta < .02:
                    continue
                if len(lockset) and np.any(np.abs(lockset - ta) < 1e-6) and np.any(np.abs(lockset - tb) < 1e-6):
                    continue
                add.append(mid % L)
        if not add:
            break
        t = np.unique(np.concatenate([t, add]))
    else:
        P, w, verts, secs = _ring_rows(pl, loop, zones, t, N, _cache=row_cache)
        _put_ports(P, t, loop, zones)
    is_lock = np.isin(np.round(t, 9), np.round(lockset, 9))
    bowl = pl.bowl_of(loop.point(t))
    return Ring(loop, t, P, _normals(np.concatenate([P[-1:], P, P[:1]]))[1:-1], w, bowl, verts, is_lock)


def _put_ports(P, t, loop, zones):
    """Port rows take the port's exact lip vertices (the line's end row) and its exact section direction."""
    for tc, half, p in zones:
        for q in p.row:
            i = int(np.argmin(np.abs(t - loop.locate(q[[0, 2]]))))
            L = loop.point(t[i])
            d = P[i, :, [0, 2]].T - L[None]
            dist = np.linalg.norm(d, axis=1)
            P[i, :, 0] = q[0] + dist * p.heading[0]
            P[i, :, 2] = q[2] + dist * p.heading[1]
            P[i, -1] = q


# ---------------------------------------------------------------------------------------------------- meshes

def _grid_faces(P, closed_rows=True):
    """Two triangles per quad of the grid P (a, b, 3), split on the shorter diagonal: (faces into P.reshape(-1, 3),
    row index of each face)."""
    a, b = P.shape[:2]
    idx = np.arange(a * b).reshape(a, b)
    if closed_rows:
        idx = np.concatenate([idx, idx[:1]])
    V = P.reshape(-1, 3)
    i = idx[:-1, :-1].ravel(); j = idx[1:, :-1].ravel(); k = idx[1:, 1:].ravel(); m = idx[:-1, 1:].ravel()
    row = np.repeat(np.arange(idx.shape[0] - 1), b - 1)
    short = np.linalg.norm(V[i] - V[k], axis=1) <= np.linalg.norm(V[j] - V[m], axis=1)
    F = np.concatenate([np.where(short[:, None], np.stack([i, j, k], 1), np.stack([i, j, m], 1)),
                        np.where(short[:, None], np.stack([i, k, m], 1), np.stack([j, k, m], 1))])
    return F, np.concatenate([row, row])


def ring_mesh(rg, pl, features):
    """The ring as a dsl.Mesh: riding faces, material by bowl (the Pool's tile band on its vert), feature by bowl."""
    P, Nr = rg.P, rg.Nrm
    F, row = _grid_faces(P)
    V = P.reshape(-1, 3); N = Nr.reshape(-1, 3)
    t = V[F]; fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    area = np.linalg.norm(fn, axis=1) / 2
    if (fn * N[F].mean(1)).sum() < 0:
        F = F[:, ::-1].copy(); fn = -fn
    keep = area > 1e-9
    F, row = F[keep], row[keep]
    names = rg.bowl[row]
    mat = np.array([dsl.MATERIAL[MATERIAL[n]] for n in names])
    tile = (names == 'blue_pool') & (rg.w[row] == 0) & (V[F][:, :, 1].min(1) >= pl.rim - rg.vert[row] - 1e-6) \
        & (rg.vert[row] > 0)
    mat[tile] = dsl.MATERIAL[TILE]
    feat = np.array([features.index(n) for n in names])
    UV = _ring_uv(P).reshape(-1, 2)
    return dsl.Mesh(V, F, N, UV, None, mat, dsl.ROLE[dsl.RIDING], feat, tuple(features), {}, 0)


def _ring_uv(P):
    """u: each column's own arc length along the rows; v: each row's arc length across (tiles)."""
    Q = np.concatenate([P, P[:1]])
    along = np.concatenate([np.zeros((1, P.shape[1])), np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=-1), 0)])[:-1]
    across = np.concatenate([np.zeros((P.shape[0], 1)), np.cumsum(np.linalg.norm(np.diff(P, axis=1), axis=-1), 1)], 1)
    return np.stack([along, across], -1) / dsl.UV_METRES


def fill_plan(loops3, step, height=None, step_fn=None, _tries=4):
    """A constrained Delaunay fill (cdt.py) of the plan region bounded by loops3 [(k, 3)] (the first the outline,
    the rest holes), keeping every boundary vertex exactly; interior points on a grid `step` apart (or step_fn(x, z)
    for a graded fill), kept 0.6 step clear of the boundary; their heights from height(Q) (else the mean boundary y).
    Returns (V (n, 3), F (m, 3)) wound upward."""
    B = [np.asarray(L, 'f8') for L in loops3]
    P2 = np.concatenate([L[:, [0, 2]] for L in B])
    lo, hi = P2.min(0), P2.max(0)
    fine = step if step_fn is None else min(step, FLOOR_STEP[0])
    gx = np.arange(lo[0] + fine / 2, hi[0], fine); gz = np.arange(lo[1] + fine / 2, hi[1], fine)
    Gp = np.stack(np.meshgrid(gx, gz), -1).reshape(-1, 2) if len(gx) and len(gz) else np.zeros((0, 2))
    if len(Gp) and step_fn is not None:                  # thin the fine grid where the local step is coarser
        s = step_fn(Gp)
        k = np.maximum(1, np.round(s / fine)).astype(int)
        ix = np.round((Gp[:, 0] - gx[0]) / fine).astype(int); iz = np.round((Gp[:, 1] - gz[0]) / fine).astype(int)
        Gp = Gp[(ix % k == 0) & (iz % k == 0)]
    if len(Gp):
        ins = solids._inside(Gp, B[0][:, [0, 2]])
        for H in B[1:]:
            ins &= ~solids._inside(Gp, H[:, [0, 2]])
        Gp = Gp[ins]
    if len(Gp):
        clear = np.full(len(Gp), np.inf)
        for L in B:
            clear = np.minimum(clear, solids._seg_distance(Gp, L[:, [0, 2]]))
        local = step if step_fn is None else step_fn(Gp)
        Gp = Gp[clear > .6 * local]
    pts = np.concatenate([P2, Gp])
    loops, o = [], 0
    for L in B:
        loops.append(np.arange(o, o + len(L))); o += len(L)
    try:
        F = triangulate(pts, loops)
    except CDTError:
        if _tries <= 0:
            raise
        return fill_plan(loops3, step * 1.07, height, step_fn, _tries - 1)
    if len(F) != len(P2) - 2 * len(B) + 2 + 2 * len(Gp) + (2 * (len(B) - 1) if len(B) > 1 else 0) - 2 * (len(B) - 1):
        pass                                              # (holes: Euler count checked by the watertight test)
    yb = np.concatenate([L[:, 1] for L in B])
    yi = height(Gp) if (height is not None and len(Gp)) else np.full(len(Gp), yb.mean())
    V = np.concatenate([np.concatenate(B), np.stack([Gp[:, 0], yi, Gp[:, 1]], 1)]) if len(Gp) else np.concatenate(B)
    t = V[F]
    up = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])[:, 1]
    F = np.where((up < 0)[:, None], F[:, [0, 2, 1]], F)
    return V, F


def _part(V, F, *, material, role, feature, features, tag=''):
    t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    N = np.zeros_like(V)
    for i in range(3):
        np.add.at(N, F[:, i], n)
    N = N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    UV = V[:, [0, 2]] / dsl.UV_METRES
    m = len(F)
    return dsl.Mesh(V, F, N, UV, None, np.full(m, dsl.MATERIAL[material]), np.full(m, dsl.ROLE[role]),
                    np.full(m, features.index(feature)), tuple(features), {}, np.full(m, dsl.TAG[tag]))


def _seg_points(a, b, step):
    n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
    return a + (b - a) * (np.arange(1, n) / n)[:, None]


# ---------------------------------------------------------------------------------------------------- the complex

FEATURES = ('crater_bowl', 'blue_pool', 'peanut', 'bowl_channels', 'bowl_deck')


def complex(data=None, *, on_ground=False, ports=None, only=None):    # noqa: A001 (the task's name)
    """The bowl complex as a primitives.Built: one closed solid (on_ground=False: a skirt and a base close it) or
    the open surface with its `foot` loop for A's ground. `ports`: {line id: (k, 3) end row} from the built lines."""
    data = data or _layout()
    pl = plan(data, ports, only)
    return compile_plan(pl, on_ground=on_ground)


def compile_plan(pl, *, on_ground=False, inserts=()):
    """Mesh a connected bowl plan, including its inner spines and exact entry rows.

    Both the original complex and the Prado-inspired finish use this builder, so
    a spine changes the floor boundary rather than overlapping a second ramp.
    """
    loops, _ = outline(pl)
    if len(loops) < 1:
        raise ValueError('bowls: no outline')
    loop_options = dict(smooth=getattr(pl, 'outline_smooth', 3),
                        normal_span=getattr(pl, 'outline_normal_span', .3))
    outer = Loop(loops[0] if _area(loops[0]) > 0 else loops[0][::-1], **loop_options)
    for p in pl.ports:                                   # each port's straight lip
        a, b = p.row[0, [0, 2]], p.row[-1, [0, 2]]
        ext = (b - a) / np.linalg.norm(b - a) * PORT_PAD
        outer.snap(a - ext, b + ext)
    inner = [Loop(L if _area(L) < 0 else L[::-1], **loop_options) for L in loops[1:]]
    # columns: enough for every section's tightest arc
    secs = [wall_section(0, *w) for w in pl.walls]
    for p in pl.ports:
        H = p.y - pl.floors['crater_bowl']
        secs.append(flat_section(0, H) if p.kind == 'floor' else
                    rollin_section(0, H, max(-p.slope_deg, 0.), max(20., CREST_K * p.speed ** 2 / G)))
    N = max(s.columns_needed() for s in secs) + 1
    zones = _zones(outer, pl.ports, pl.rim)
    rings = [ring(pl, outer, zones, N)] + [ring(pl, L, [], N) for L in inner]
    features = list(FEATURES)
    parts = [ring_mesh(rg, pl, features) for rg in rings]
    # the floor: the region between the rings' floor edges, cut into bowls and channels at each channel's ramp ends
    floor_loops = [rg.P[:, 0] for rg in rings]
    for insert in inserts:
        # An internal feature owns its floor footprint. Fill around its exact
        # foot loop, never underneath it: no buried or coincident riding faces.
        for foot in insert.foot:
            inside = solids._inside(np.asarray(foot)[:, [0, 2]], floor_loops[0][:, [0, 2]])
            if not inside.all():
                bad = np.asarray(foot)[~inside]
                raise ValueError(f'{insert.mesh.features[0]}: floor footprint leaves the receiving bowl floor; '
                                 f'outside bounds {bad.min(0).tolist()} to {bad.max(0).tolist()}')
            floor_loops.append(foot)
    fV, fF = fill_plan(floor_loops, FLOOR_STEP[1], height=pl.floor,
                       step_fn=lambda Q: np.where(pl.bowl_of(Q) == 'bowl_channels', FLOOR_STEP[0], FLOOR_STEP[1]))
    names = pl.bowl_of(fV[fF].mean(1)[:, [0, 2]])
    for name in set(names):
        sel = names == name
        parts.append(_part(fV, fF[sel], material=MATERIAL[name], role=dsl.RIDING, feature=name, features=features))
    # the deck: between the outer lip and its outline (offset by DECK, hugging the lip wherever a port lowers it),
    # and the islands
    O, runs = _deck_outline(pl, rings[0])
    deck_pieces = _deck_pieces(O, runs, rings[0])
    for outline_, holes in deck_pieces:
        V, F = fill_plan([outline_] + holes, DECK_STEP)
        parts.append(_part(V, F, material=MATERIAL['bowl_deck'], role=dsl.RIDING, feature='bowl_deck',
                           features=features))
    for rg in rings[1:]:
        lip = rg.P[::-1, -1]                              # counter-clockwise round the island
        V, F = fill_plan([lip], DECK_STEP)
        parts.append(_part(V, F, material=MATERIAL['bowl_deck'], role=dsl.RIDING, feature='bowl_deck',
                           features=features))
    foot = []
    if on_ground:
        foot.append(O)
    else:
        base_y = min(pl.floors.values()) - 1.5
        bot = O.copy(); bot[:, 1] = base_y
        # A full-depth skirt quad has a 10+ m edge in a deep bowl. Keep the
        # closing surface within the same 4 m edge limit as other side walls.
        steps = max(1, int(math.ceil(float((O[:, 1] - base_y).max()) / 2.5)))
        u = np.linspace(0., 1., steps + 1)
        G2 = O[:, None] * (1 - u[None, :, None]) + bot[:, None] * u[None, :, None]
        # A floor-port closing edge has the receiver's two vertical endpoints.
        # Collapse intermediate skirt samples there; otherwise removing the
        # covered face leaves T-junctions against the receiver's end wall.
        for p in pl.ports:
            n = np.array([-p.heading[1], p.heading[0]])
            lateral = (O[:, [0, 2]] - p.point) @ n
            bounds = (p.row[:, [0, 2]] - p.point) @ n
            at_port = (np.abs((O[:, [0, 2]] - p.point) @ p.heading) < 1e-7)
            at_port &= (lateral >= bounds.min() - 1e-7) & (lateral <= bounds.max() + 1e-7)
            at_port &= np.abs(O[:, 1] - p.y) < 1e-7
            if p.kind == 'floor':
                receiving_bottom = p.y - 1.5
                if receiving_bottom < base_y - 1e-7:
                    raise ValueError(f'bowls: {p.line} receiver bottom is below the bowl base')
                if abs(receiving_bottom - base_y) < 1e-7:
                    G2[at_port, 1:] = bot[at_port, None]
                else:
                    if steps < 2:
                        raise ValueError('bowls: elevated floor port needs at least two skirt intervals')
                    G2[at_port, 1:, 1] = np.linspace(receiving_bottom, base_y, steps)
        F, _ = _grid_faces(G2)
        V = G2.reshape(-1, 3)
        t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        F = F[np.linalg.norm(n, axis=1) > 1e-9]
        t = V[F]; n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        cen = O[:, [0, 2]].mean(0)
        out = t.mean(1)[:, [0, 2]] - cen
        if (n[:, [0, 2]] * out).sum() < 0:
            F = F[:, ::-1]
        skirt = _part(V, F, material=dsl.CONCRETE, role=dsl.SIDE, feature='bowl_deck', features=features)
        for p in pl.ports:
            n = np.array([-p.heading[1], p.heading[0]])
            lateral = (t[:, :, [0, 2]] - p.point) @ n
            bounds = (p.row[:, [0, 2]] - p.point) @ n
            covered = (np.abs((t[:, :, [0, 2]] - p.point) @ p.heading) < 1e-7).all(1)
            covered &= (lateral.min(1) >= bounds.min() - 1e-7) & (lateral.max(1) <= bounds.max() + 1e-7)
            if p.kind == 'floor':
                covered &= t[:, :, 1].max(1) <= p.y + 1e-7
                covered &= t[:, :, 1].min(1) >= p.y - 1.5 - 1e-7
                skirt.role[covered] = dsl.ROLE[dsl.BASE]
        parts.append(skirt)
        b = solids.polygon(bot, outward=np.array([0., -1., 0.]), feature='bowl_deck', role=dsl.BASE)
        parts.append(_part(b.V, b.F, material=dsl.CONCRETE, role=dsl.BASE, feature='bowl_deck', features=features))
    # coping: every plain-wall stretch of each lip (the islands' are closed loops)
    rails = []
    for rg in rings:
        plain = rg.w <= 1e-9
        for i0, i1, closed in _runs(plain):
            idx = np.arange(i0, i1 + 1) % len(rg.t) if not closed else np.arange(len(rg.t))
            lip = rg.P[idx, -1]
            into = np.zeros_like(lip); into[:, [0, 2]] = rg.loop.inward(rg.t[idx])
            if len(idx) < 3:
                continue
            tube, rail = coping_mod.coping(lip, into, closed=closed, feature=rg.bowl[idx[0]])
            tube.features = (rg.bowl[idx[0]],)
            m = len(tube.F)
            parts.append(dsl.Mesh(tube.V, tube.F, tube.N, tube.UV, None, tube.material, tube.role,
                                  np.full(m, features.index(rg.bowl[idx[0]])), tuple(features), {}, tube.tag))
            rails.append(rail)
    mesh = dsl.Mesh.concat(parts)
    if inserts:
        mesh = dsl.Mesh.concat([mesh] + [b.mesh for b in inserts])
        rails += [rail for b in inserts for rail in b.rails]
    checks = [{'feature': 'bowl_complex', 'kind': 'bowls', 'ports': [p.as_dict() for p in pl.ports],
               'rows': [len(rg.t) for rg in rings], 'columns': N,
               'floors': pl.floors, 'rim': pl.rim, 'notes': pl.notes}]
    return Built(mesh, rails, checks, foot)


def _runs(mask):
    """Runs of True in a cyclic mask: [(i0, i1, closed)]."""
    n = len(mask)
    if mask.all():
        return [(0, n - 1, True)]
    if not mask.any():
        return []
    start = int(np.flatnonzero(~mask)[0])
    out, i, cur = [], 0, None
    for k in range(1, n + 1):
        j = (start + k) % n
        if mask[j] and cur is None:
            cur = start + k
        if (not mask[j] or k == n) and cur is not None:
            out.append((cur % n, (start + k - 1) % n if mask[j] is False or not mask[j] else (start + k) % n, False))
            cur = None
    fixed = []
    for i0, i1, c in out:
        fixed.append((i0, i1 if i1 >= i0 else i1 + n, c))
    return fixed


def _deck_outline(pl, rg):
    """The deck's outer edge O (k, 3) at the rim: the lip offset outward by DECK, except along each port's run (the
    rows whose wall a port morphs), where O is the lip itself. Returns (O, runs as (i0, i1) row index ranges, and
    their positions in O)."""
    n = len(rg.t)
    lip = rg.P[:, -1]
    out_n = -np.concatenate([rg.loop.inward(rg.t)], 0)
    level = rg.w <= 1e-9
    runs = [(i0, i1) for i0, i1, _ in _runs(~level)]
    # extend each run by one level row either side: the deck meets the lip only where it is level
    runs = [(i0 - 1, i1 + 1) for i0, i1 in runs]
    in_run = np.zeros(n, bool)
    for i0, i1 in runs:
        in_run[np.arange(i0, i1 + 1) % n] = True
    off = lip.copy(); off[:, [0, 2]] += DECK * out_n; off[:, 1] = pl.rim
    # thin the offset to at most DECK_STEP apart, and fix folds of the offset at sharp inward turns by a max-distance
    pts, owner = [], []
    for i in range(n):
        if in_run[i] and not any((i - i0) % n == 0 or (i - i1) % n == 0 for i0, i1 in runs):
            pts.append(lip[i]); owner.append(('lip', i))
        elif in_run[i]:
            pts.append(lip[i]); owner.append(('lip', i))
        else:
            pts.append(off[i]); owner.append(('off', i))
    # legs: between an offset point and a run's end lip point, add points along the leg
    O, own = [], []
    m = len(pts)
    for k in range(m):
        a, b = pts[k], pts[(k + 1) % m]
        O.append(a); own.append(owner[k])
        if owner[k][0] != owner[(k + 1) % m][0]:
            for q in _seg_points(a, b, 1.):
                O.append(q); own.append(('leg', -1))
    O = np.asarray(O)
    # decimate the offset stretches to about 1 m (the lip rows can be dense)
    keep = np.ones(len(O), bool); last = None
    for k in range(len(O)):
        if own[k][0] == 'off':
            if last is not None and np.linalg.norm(O[k] - O[last]) < 1. and (k + 1 < len(O) and own[k + 1][0] == 'off'):
                keep[k] = False
                continue
            last = k
        else:
            last = None
    O = O[keep]; own = [o for o, k in zip(own, keep, strict=True) if k]
    O = _unfold(O, [o[0] == 'off' for o in own])
    run_pos = []
    for i0, i1 in runs:
        ks = [k for k, o in enumerate(own) if o[0] == 'lip' and (o[1] - i0) % n <= (i1 - i0) % n]
        run_pos.append((i0 % n, i1 % n, ks[0], ks[-1]))
    return O, run_pos


def _unfold(O, movable):
    """Remove self-intersections of the offset polyline (where the lip turns inward tighter than DECK) by dropping
    the looped points."""
    O = np.asarray(O)
    for _ in range(50):
        P = O[:, [0, 2]]
        if not solids.segments_cross(P):
            return O
        n = len(P)
        a, b = P, np.roll(P, -1, 0)
        drop = None
        for i in range(n):
            for j in range(i + 2, min(n, i + 200)):
                if (i == 0 and j == n - 1):
                    continue
                p, r = a[i], b[i] - a[i]; q, s = a[j], b[j] - a[j]
                den = r[0] * s[1] - r[1] * s[0]
                if abs(den) < 1e-12:
                    continue
                tt = ((q - p)[0] * s[1] - (q - p)[1] * s[0]) / den
                uu = ((q - p)[0] * r[1] - (q - p)[1] * r[0]) / den
                if 0 < tt < 1 and 0 < uu < 1:
                    drop = (i, j); break
            if drop:
                break
        if not drop:
            return O
        i, j = drop
        if not all(movable[k] for k in range(i + 1, j + 1)):
            raise ValueError('bowls: the deck outline folds against a port')
        x = a[i] + tt * (b[i] - a[i])
        newpt = np.array([x[0], O[i, 1], x[1]])
        O = np.concatenate([O[:i + 1], [newpt], O[j + 1:]])
        movable = list(movable[:i + 1]) + [True] + list(movable[j + 1:])
    return O


def _deck_pieces(O, runs, rg):
    """The deck between O and the outer lip: one piece per stretch between port runs (or the whole ring when
    there are none), each (outline (k, 3) counter-clockwise, holes)."""
    lip = rg.P[:, -1]
    n = len(lip)
    if not runs:
        return [(O, [lip[::-1]])]
    pieces = []
    m = len(O)
    runs = sorted(runs, key=lambda r: r[2])
    for k in range(len(runs)):
        i0a, i1a, ka0, ka1 = runs[k]
        i0b, i1b, kb0, kb1 = runs[(k + 1) % len(runs)]
        # along O from the end of run a to the start of run b (counter-clockwise), then back along the lip
        oseg = [O[(ka1 + j) % m] for j in range((kb0 - ka1) % m + 1)]
        back = [lip[(i0b - j) % n] for j in range(1, (i0b - i1a) % n)]
        pieces.append((np.asarray(oseg + back), []))
    return pieces


build = complex     # the same entry point under the name layout.park() may call
