"""Railway alignment for the Belmonte steam train: Hidamari's town station to Belmonte's eastern edge.

    python games/yorimichi/world/train/route.py [--out DIR] [--optimise]

Plain Python and NumPy, no Blender or Unreal. It changes no terrain: it reads the ground the way the world map does
(world/map/build_map.py) and writes a study to build/yorimichi/belmonte-train/route/ (route.json, profile.png,
plan.png). Coordinates are Blender metres (x east, y north, z up); bearings are degrees counter-clockwise from east;
chainage s runs from Hidamari's buffer stop to Belmonte's.

The study, in order:
- Horizontal alignment: straights through tangent points (PIS) joined by clothoid-circle-clothoid curves, with the
  stations' reserves straight at both ends. Each curve takes the largest radius its two tangents leave room for. One
  tangent point carries a Swiss-style spiral: a full extra turn underground on a tight fixed radius, so the climb
  hides in a hill and the line in the open reads as one flowing curve (no horseshoe or hairpin).
- Ground: the island's collision surface (hidamari.layout.north_height), Belmonte's own terrain triangles inside its
  bounds and the generated northern apron and country beyond the south join, as build_map.py composes them.
- Vertical profile: dynamic programming over rail heights every STEP metres against an earthwork cost (formation
  FORMATION wide, side slopes 1:SLOPE) with view-weighted costs for tunnels and viaducts, the grade limit, level
  platforms and the passing loop; then a moving average whose length is the vertical curve (it keeps the grade limit).
- Structures: cutting, deep cutting, tunnel, embankment and viaduct, short pieces merged.
- Operation: two trains on one schedule half a cycle apart, standing DWELL at each terminus and crossing at the
  passing loop, where the first one there stands on the loop track until the other has cleared it; the loop is
  placed where that gives the shortest headway. The run model posts each curve's limit (sqrt(a R), rounded down to 10 km/h) over the whole
  curve and the train's length, brakes before it, climbs as the engine's power allows and holds steep descents on the
  brakes; it runs each direction separately and stops at both platforms. The train reverses
  at each terminus (locomotive pushing on the way back), so neither station needs a turning loop.
- Views: rays at eye height every 1 degree from every VIEW_STEP metres of line against a GRID metre ground raster;
  route.json keeps the brief's 10-degree rays per viewpoint, the coverage uses all of them. Empty spaces are ground
  cells seen within EMPTY_RANGE of the line that hold no built content (city, Belmonte and world instances): bare, or
  planted only. Beyond about x 2600 the far-hills grid is clamped, so views and spaces there are indicative only.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

# --- stations and constraints ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Station:
    """A terminus: platform centre, the bearing a train runs along it towards Belmonte, the platform length and the
    reserve (length along the track, width across) that stays straight and level."""
    name: str
    centre: tuple
    bearing: float
    platform: float
    reserve: tuple

    @property
    def axis(self):
        a = math.radians(self.bearing)
        return np.array([math.cos(a), math.sin(a)])


# The town station's existing south-side platform, extended east for the full consist. The buffer stays east of
# the x=1120 lane; the old engine shed gives way to the approach. Share the rail datum with the station builder.
from hidamari import station_yard
HIDAMARI = Station('Hidamari', station_yard.SERVICE_CENTRE, 0., 160., (160., 56.))
# Paul, 2026-10-17: the station moves next to the town, on the flat ground (206-214 m) north of the road from the
# south-east gate to the Dunes Basses estate, its facade facing north-west towards the town (train/station_site.py).
# The line keeps the riverside approach of the former terminus (1375, 4375, bearing 170) through its coastal curve,
# so the shoreline's railway headlands stay as they are (shorelines._rail_headlands), then turns right onto the
# station's axis and passes under that road in a cutting about 230 m before the buffer stop: the road keeps its line
# and level on a stone overbridge (track.py). Trains arrive running north-west.
BELMONTE = Station('Belmonte', (900., 4625.), 140., 160., (200., 60.))

STEP = 10.                  # sampling along the line
MIN_RADIUS = 450.          # in the open; a spiral loop keeps its own radius
PREFERRED_RADIUS = 900.
SPIRAL = 80.                # clothoid length at each end of a curve
MIN_STRAIGHT = 20.          # between two curves
VOLCANO_CLEARANCE = 1550.
MAX_GRADE = .035
PREFERRED_GRADE = .030
VERTICAL_CURVE = 150.       # margin around the level and loop zones (and, before the grade-state profile, the smoothing)
DZ = .05                    # rail height resolution of the dynamic programme
VERTICAL_RADIUS = STEP * STEP / DZ   # 2000 m: the profile's grade changes by at most DZ per STEP per STEP
PLATFORM_OFFSET = 6.        # rail may stand this far off the ground along a reserve (H2 rises 9.5 m along its 200 m)

# Classification (rail top against the ground; the tunnel crown stands TUNNEL_BORE above the rail).
CUT_DEPTH = 12.             # deeper cuttings are reported as deep cuttings: preferred to tunnels for the view
TUNNEL_BORE = 7.
TUNNEL_COVER = 18.          # tunnels where the cover would reach this: portals at 25 m deep (was 25: 32 m deep cuttings)
EMBANKMENT_HEIGHT = 10.
MIN_TUNNEL = 60.
SPIRAL_COVER = 15.          # rail at least this far below the ground over the spiral (bore plus 8 m)
COVER_COST = 2000.          # per metre of missing cover over the spiral, per metre of line
MIN_VIADUCT = 40.
FORMATION = 8.
SLOPE = 1.5
# View-weighted costs, cubic metres of earthwork per metre of line: a tunnel hides the landscape, a viaduct shows it.
MAX_BEND = 100.             # degrees: the largest single curve in the open
TUNNEL_BUDGET = 1400.       # the town station is 11 m below H2; its lower approach needs about 390 m more tunnel
TUNNEL_COST = 10000.        # four times a 32 m deep cutting: tunnels only where nothing in the open fits
VIADUCT_COST = 300.
VIADUCT_RISE = 15.          # per metre of height above EMBANKMENT_HEIGHT

# Operation.
TRAIN_LENGTH = 131.
MAX_SPEED = 100 / 3.6       # Paul, 2026-10-14 playtest: faster on straights and gentle curves (was 80)
RUN_COST = 500.             # m3 of earthwork worth one second of running time, for the optimiser
LATERAL_ACCELERATION = .85  # with cant (was .65 without): v = sqrt(a R), posted in POSTED_STEP steps rounded down
POSTED_STEP = 10 / 3.6
ACCELERATION = .4           # at most; less when the engine's power runs out
BRAKING = 1.2               # Paul: still stopped far too slowly at .8 (was .5); a firm stop for a game
TUNNEL_SPEED = 160 / 3.6    # game pacing: only while the complete consist is under one continuous tunnel
TUNNEL_ACCELERATION = 1.2
# A steam train for a game: locomotive 70 t, tender 40 t and five vehicles of about 36 t (consist.py has no masses).
MASS = (70. + 40. + 5 * 36.) * 1e3
POWER = 1.5e6               # watts at the rail
DAVIS = (15., .36, .045)    # rolling resistance per tonne, N: A + B v + C v^2 (v in m/s)
GRAVITY = 9.81
STOP_CLEARANCE = 10.        # the head stops this far from the end of the line, the whole train on the reserve
DWELL = 90.                 # Paul, 2026-10-14: every train stands 1 min 30 s at each terminus
CROSSING_MARGIN = 10.       # s between the crossing train clearing the loop and the waiting one leaving
ASKED_INTERVAL = 600.       # the 10 min first asked for; the optimiser still aims at it
LOOP_LENGTH = 200.          # the second track's straight or gentle length
TURNOUT = 30.
LOOP_TOTAL = LOOP_LENGTH + 2 * TURNOUT
LOOP_RADIUS = 500.
LOOP_GRADE = .01
TRACK_SPACING = 4.
LOOP_SEARCH = 240.          # seconds of timetable offset searched first when placing the loop (optimiser)
LOOP = (4810., 5070.)       # the approved loop's same location, re-chained after the town-station approach
LOOP_TRIES = 12             # loop windows given their own profile when placing the loop
HEADWAY_COST = 20000.       # m3 of earthwork worth one second of headway when choosing the loop
OFFSET_COST = 2000.         # m3 of earthwork worth one second of timetable offset when choosing the loop

# Views.
EYE = 3.2
VIEW_STEP = 50.
VIEW_RANGE = 2000.
RAY_STEP = 20.
BIG_VIEW = 1000.
EMPTY_RANGE = 1500.
GRID = 20.                  # ground raster for views and the plan
CELL = 50.                  # empty-space cells
RASTER_BOUNDS = (-1280., -1780., 4600., 6800.)    # the line's box plus VIEW_RANGE, fixed so the cache survives tuning

# Tangent points between the two stations, tuned by `optimise` (python route.py --optimise prints new values). The
# line leaves the town station east, enters the far hills' southern slope and climbs one turn of spiral tunnel, runs
# north over the plateau east of the volcano and comes down through Belmonte's country. An entry (x, y, turns, radius)
# is the spiral (see spiral_loops); with 0 turns, a plain curve kept on that radius (fixed_radii). FIRST and LAST are
# distances along the stations' axes from their centres.
FIRST = 400.
# The last entry is the former terminus's approach curve, kept in place and on its radius (see BELMONTE).
PIS = [(2300., 710.), (2170., 1580.), (2440., 2080., -1, 300.), (2490., 2345.), (2465., 3440.), (2075., 3880.),
       (1759.075, 4307.277, 0, 625.622)]
LAST = 327.447              # where the former terminus's straight meets the station's axis
# Alternatives costed in route.json: the first study's short line round the volcano's eastern flank (v1, tunnel-heavy)
# and the second study's line in the open (v2: horseshoe out of H2, coastal viaduct and a hairpin on the far hills).
ALTERNATIVES = {
    'v1: short line through the eastern flank': dict(
        first=790., pis=[(2290., 1770.), (2495., 2455.), (2360., 2860.), (2020., 3567.5)], last=450., min_radius=250.,
        grade=.035),
    'v2: in the open with horseshoe and hairpin': dict(
        first=1210., pis=[(2150., 110.), (3925., 140.), (3540., 895.), (2335., 600.), (2340., 1890.), (2420., 2300.),
                          (2485., 3395.), (2115., 3840.)], last=390., min_radius=250., grade=.035)}
DESIGN_GRADE = .040         # the spiral's single turn needs 4.0%; the 3.5% option is costed in route.json
OPTION_GRADE = .035


def full_speed_radius():
    """The smallest radius the train takes at MAX_SPEED (908 m at 100 km/h and 0.85 m/s2)."""
    return MAX_SPEED ** 2 / LATERAL_ACCELERATION


def curve_limit(radius):
    """Posted speed on a curve of this radius, m/s: sqrt(a R) rounded down to POSTED_STEP, at most MAX_SPEED."""
    v = math.sqrt(LATERAL_ACCELERATION * radius)
    return min(MAX_SPEED, math.floor(v / POSTED_STEP + 1e-9) * POSTED_STEP)


def volcano():
    from hidamari import mountains
    return np.array(mountains.VOLCANO, float)


def ends():
    """Buffer stops: the far ends of the two reserves."""
    start = np.array(HIDAMARI.centre) - HIDAMARI.axis * HIDAMARI.reserve[0] / 2
    end = np.array(BELMONTE.centre) + BELMONTE.axis * BELMONTE.reserve[0] / 2
    return start, end


def tangent_points(first=None, pis=None, last=None):
    """Buffer stop, the point FIRST along H2's axis, the inner points (x, y) of `pis`, the point LAST back along
    Belmonte's axis and its buffer stop."""
    first, pis, last = (FIRST if first is None else first), (PIS if pis is None else pis), (LAST if last is None else last)
    start, end = ends()
    return [start, np.array(HIDAMARI.centre) + HIDAMARI.axis * first, *(np.asarray(p[:2], float) for p in pis),
            np.array(BELMONTE.centre) - BELMONTE.axis * last, end]


def spiral_loops(pis=None):
    """{inner tangent point index: (turns, radius)} for the entries of `pis` written (x, y, turns, radius) with turns
    other than 0: a curve there turns `turns` full circles more than its deflection (negative: clockwise), on a fixed
    radius."""
    pis = PIS if pis is None else pis
    return {i + 2: (p[2], p[3]) for i, p in enumerate(pis) if len(p) > 2 and p[2]}   # keys index tangent_points()


def fixed_radii(pis=None):
    """{inner tangent point index: radius} for the entries of `pis` written (x, y, 0, radius): a plain curve kept on
    that radius (not a spiral loop), where the line must follow an existing one exactly."""
    pis = PIS if pis is None else pis
    return {i + 2: p[3] for i, p in enumerate(pis) if len(p) > 2 and not p[2]}


# --- horizontal alignment -------------------------------------------------------------------------------------------


def _spiral_shift(radius, length):
    """Shift p and tangent extension k of a clothoid of this length ending on this radius."""
    t = length / (2 * radius)
    x = length * (1 - t ** 2 / 10 + t ** 4 / 216)
    y = length * (t / 3 - t ** 3 / 42 + t ** 5 / 1320)
    return y - radius * (1 - math.cos(t)), x - radius * math.sin(t)


def _curve(deflection, radius):
    """(spiral length, tangent length) of a symmetric clothoid-circle-clothoid curve."""
    spiral = min(SPIRAL, radius * abs(deflection))       # pure clothoids when the deflection is too small for an arc
    p, k = _spiral_shift(radius, spiral)
    return spiral, (radius + p) * math.tan(abs(deflection) / 2) + k      # negative past half a turn: a loop


def curves(points, loops=None, radii=None):
    """Per inner tangent point: (deflection, radius, spiral, tangent length). Every radius starts at PREFERRED_RADIUS
    and shrinks until the tangents fit their legs, the station reserves staying straight. None if a radius would go
    below MIN_RADIUS. A spiral loop (`loops`, see spiral_loops) keeps its radius and adds its full turns to the
    deflection: its tangents are those of the plain deflection, so the line leaves it on the same outgoing tangent.
    A fixed radius (`radii`, see fixed_radii) is kept as it is."""
    loops, radii = loops or {}, radii or {}
    points = [np.asarray(p, float) for p in points]
    legs = [b - a for a, b in zip(points, points[1:])]
    lengths = [float(np.hypot(*leg)) for leg in legs]
    deflection = []
    for a, b in zip(legs, legs[1:]):
        deflection.append(math.atan2(a[0] * b[1] - a[1] * b[0], a @ b))
    radius = [PREFERRED_RADIUS] * len(deflection)
    for i, (turns, loop_radius) in loops.items():
        deflection[i - 1] += 2 * math.pi * turns
        radius[i - 1] = loop_radius
    for i, r in radii.items():
        radius[i - 1] = r
    fixed = {i - 1 for i in (*loops, *radii)}
    room = list(lengths)
    room[0] -= HIDAMARI.reserve[0]
    room[-1] -= BELMONTE.reserve[0]
    for _ in range(5000):
        tangent = [_curve(d, r)[1] if abs(d) > 1e-6 else 0. for d, r in zip(deflection, radius)]
        worst = None
        for i, available in enumerate(room):
            used = (tangent[i - 1] if i > 0 else 0.) + (tangent[i] if i < len(tangent) else 0.)
            need = MIN_STRAIGHT if 0 < i < len(room) - 1 else 0.
            if used + need > available + 1e-6:
                worst = (i, used + need - available)
                break
        if worst is None:
            return [(d, r, *_curve(d, r)) for d, r in zip(deflection, radius)]
        i, _excess = worst
        options = [j for j in (i - 1, i) if 0 <= j < len(radius) and radius[j] > MIN_RADIUS and j not in fixed]
        if not options:
            return None
        j = max(options, key=lambda n: tangent[n])
        radius[j] = max(MIN_RADIUS, radius[j] * .98)
    return None


def _element(xy, heading, length, k0, k1, step=.25):
    """Points of a clothoid element (curvature k0 to k1, linear in chainage) by midpoint integration."""
    n = max(1, int(math.ceil(length / step)))
    s = np.linspace(0., length, n + 1)
    k = k0 + (k1 - k0) * s / max(length, 1e-9)
    h = heading + k0 * s + (k1 - k0) * s ** 2 / (2 * max(length, 1e-9))
    mid = (h[1:] + h[:-1]) / 2
    ds = np.diff(s)
    x = xy[0] + np.r_[0., np.cumsum(ds * np.cos(mid))]
    y = xy[1] + np.r_[0., np.cumsum(ds * np.sin(mid))]
    return s, x, y, h, k


@dataclass
class Alignment:
    """The line every STEP metres: chainage, position, heading (radians) and signed curvature (1/m, left positive),
    with the curves' (deflection, radius, spiral, tangent) and the closure error at Belmonte's buffer stop."""
    s: np.ndarray
    x: np.ndarray
    y: np.ndarray
    heading: np.ndarray
    curvature: np.ndarray
    points: list
    curves: list
    closure: float
    spirals: list = ()

    def spiral_mask(self, s=None):
        """True where chainage s (default: the samples) lies on a spiral loop, entry and exit clothoids included."""
        s = self.s if s is None else np.asarray(s, float)
        mask = np.zeros(s.shape, bool)
        for spiral in self.spirals:
            mask |= (s >= spiral['start']) & (s <= spiral['end'])
        return mask

    @property
    def length(self):
        return float(self.s[-1])

    def at(self, s):
        s = np.asarray(s, float)
        return (np.interp(s, self.s, self.x), np.interp(s, self.s, self.y),
                np.interp(s, self.s, np.unwrap(self.heading)), np.interp(s, self.s, self.curvature))


def alignment(points=None, step=STEP, loops=None, radii=None):
    """Build the alignment through the tangent points (default: FIRST, PIS, LAST with PIS's spiral loops and fixed
    radii), None when the curves cannot fit."""
    if points is None:
        points, loops, radii = tangent_points(), spiral_loops(), fixed_radii()
    points = [np.asarray(p, float) for p in points]
    loops = loops or {}
    plan = curves(points, loops, radii)
    if plan is None:
        return None
    parts = []
    xy = points[0]
    heading = math.atan2(*(points[1] - points[0])[::-1])
    spirals = []
    for i, (deflection, radius, spiral, tangent) in enumerate(plan):
        vertex = points[i + 1]
        straight = float(np.hypot(*(vertex - xy))) - tangent
        parts.append(_element(xy, heading, straight, 0., 0.))
        if i + 1 in loops:
            begin = sum(part[0][-1] for part in parts)
            spirals.append({'start': begin, 'end': begin + abs(deflection) * radius + spiral,
                            'turns': loops[i + 1][0], 'radius': radius, 'tangent_point': vertex.tolist()})
        sign = 1. if deflection > 0 else -1.
        k = sign / radius
        arc = abs(deflection) * radius - spiral
        for length, k0, k1 in ((spiral, 0., k), (max(arc, 0.), k, k), (spiral, k, 0.)):
            if length > 1e-6:
                part = _element((parts[-1][1][-1], parts[-1][2][-1]), parts[-1][3][-1], length, k0, k1)
                parts.append(part)
        xy = np.array([parts[-1][1][-1], parts[-1][2][-1]])
        heading = parts[-1][3][-1]
    end = points[-1]
    parts.append(_element(xy, heading, float(np.hypot(*(end - xy))), 0., 0.))
    s, x, y, h, k = [], [], [], [], []
    offset = 0.
    for ps, px, py, ph, pk in parts:
        s.append(ps[:-1] + offset); x.append(px[:-1]); y.append(py[:-1]); h.append(ph[:-1]); k.append(pk[:-1])
        offset += ps[-1]
    last = parts[-1]
    s.append([offset]); x.append([last[1][-1]]); y.append([last[2][-1]]); h.append([last[3][-1]]); k.append([0.])
    s, x, y, h, k = map(np.concatenate, (s, x, y, h, k))
    closure = float(np.hypot(x[-1] - end[0], y[-1] - end[1]))
    # Resample on STEP, ending exactly on the buffer stop (the last interval is shorter).
    grid = np.r_[np.arange(0., s[-1], step), s[-1]]
    k_grid = np.interp(grid, s, k)
    return Alignment(grid, np.interp(grid, s, x), np.interp(grid, s, y), np.interp(grid, s, h), k_grid,
                     points, plan, closure, spirals)


def backdrop(x, y):
    """True on the far-hills backdrop (hidamari.layout.far_height): outside the city, the volcano's island surface
    and Belmonte's country. Placeholder scenery: a line there needs that ground built or extended."""
    from hidamari import mountains
    x, y = np.asarray(x, float), np.asarray(y, float)
    city = (x >= 300) & (x <= 1420) & (y >= -300) & (y <= 500)
    return ~city & ~mountains.contains(x, y) & (y <= 3200.)      # beyond y 3200 far_height is Belmonte's country


def volcano_distance(x, y):
    v = volcano()
    return np.hypot(np.asarray(x) - v[0], np.asarray(y) - v[1])


# --- ground ---------------------------------------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _belmonte_surfaces():
    from belmonte import source
    # The natural ground: belmonte/build.py writes the apron and country before the railway's earthworks carve the
    # built meshes; the committed valley tiles in assets/belmonte/meshes/ remain natural.
    paths = [yori.OUT / f'belmonte/natural/{name}.glb' for name in ('SM_BM_NorthCountry', 'SM_BM_NorthApron')]
    for p in paths:
        if not p.is_file():
            raise FileNotFoundError(f'missing Belmonte natural ground {p}; run world.belmonte first')
    north = [source.Surface(source.triangles(p)) for p in paths]
    return source.terrain(natural=True), north


@lru_cache(maxsize=1)
def _square():
    path, world = yori.OUT / 'heightmap.npy', yori.OUT / 'world.json'
    if not (path.exists() and world.exists()):
        return None
    return np.load(path).astype(np.float32), float(json.loads(world.read_text())['size'])


def _bilinear(grid, fx, fy):
    n1, n0 = grid.shape[1] - 1, grid.shape[0] - 1
    fx = np.clip(fx, 0, n1 - 1e-3); fy = np.clip(fy, 0, n0 - 1e-3)
    i = fx.astype(int); j = fy.astype(int); u = fx - i; v = fy - j
    return (grid[j, i] * (1 - u) + grid[j, i + 1] * u) * (1 - v) + (grid[j + 1, i] * (1 - u) + grid[j + 1, i + 1] * u) * v


def ground(x, y):
    """Ground height as the world map composes it: the island surface, the 600 m square's heightmap, Belmonte's own
    terrain inside its bounds and the northern apron and country meshes beyond the south join."""
    from belmonte import layout as BM
    from hidamari import layout as CITY
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    z = np.array(CITY.north_height(x, y, carved=False), float)
    square = _square()
    if square is not None:
        grid, size = square
        on = (np.abs(x) <= size / 2) & (np.abs(y) <= size / 2)
        if on.any():
            n = grid.shape[1] - 1
            z[on] = _bilinear(grid, (x[on] + size / 2) / size * n, (y[on] + size / 2) / size * n)
    terrain, north = _belmonte_surfaces()
    inside = BM.contains(x, y)
    if inside.any():
        z[inside] = terrain.height(x[inside] - BM.ORIGIN[0], y[inside] - BM.ORIGIN[1]) + BM.ORIGIN[2]
    beyond = (y > BM.SOUTH_JOIN) & ~inside
    for mesh in north:
        if not beyond.any():
            break
        height = mesh.height(x[beyond] - BM.ORIGIN[0], y[beyond] - BM.ORIGIN[1]) + BM.ORIGIN[2]
        hit = np.isfinite(height)
        index = np.flatnonzero(beyond)[hit]
        z.flat[index] = height[hit]
        beyond.flat[index] = False
    return z


class Raster:
    """Ground heights on a GRID metre raster, cached in the output folder."""

    def __init__(self, bounds, step=GRID, cache=None):
        self.bounds, self.step = tuple(float(b) for b in bounds), float(step)
        x0, y0, x1, y1 = self.bounds
        self.xs = np.arange(x0, x1 + step / 2, step)
        self.ys = np.arange(y0, y1 + step / 2, step)
        digest = self._source_digest() if cache is not None else ''
        if cache is not None and cache.exists():
            data = np.load(cache)
            if (tuple(data['bounds']) == self.bounds and float(data['step']) == self.step
                    and 'source_sha256' in data.files and str(data['source_sha256']) == digest):
                self.z = data['z']
                return
        gx, gy = np.meshgrid(self.xs, self.ys)
        self.z = np.empty(gx.shape, np.float32)
        for row in range(0, gx.shape[0], 40):
            self.z[row:row + 40] = ground(gx[row:row + 40], gy[row:row + 40])
            print(f'  ground raster rows {min(row + 40, gx.shape[0])}/{gx.shape[0]}', flush=True)
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(cache, z=self.z, bounds=np.array(self.bounds), step=self.step, source_sha256=digest)

    @staticmethod
    def _source_digest():
        """@cc [owner:fontanierh,label:correctness] route-coast-cache
        Cached ground MUST be invalidated when the shoreline profile, water bounds
        or committed railway geometry used for coastal headlands changes, and
        when the committed Belmonte valley tiles the study samples change.
        """
        h = hashlib.sha256()
        regions = _Path(__file__).resolve().parents[1] / 'regions'
        files = [
            _Path(__file__).resolve(),
            regions.parent / 'shorelines.py',
            regions.parent / 'coast_water.py',
            yori.ASSETS / 'vehicles' / 'belmonte-train' / 'line.json',
            regions / 'hidamari' / 'layout.py',
            regions / 'hidamari' / 'mountains.py',
            regions / 'belmonte' / 'layout.py',
            regions / 'belmonte' / 'source.py',
            regions / 'belmonte' / 'terrain.py',
            yori.ASSETS / 'belmonte' / 'source.json',
            yori.OUT / 'world.json',
            yori.OUT / 'heightmap.npy',
            yori.OUT / 'farhills.npy',
            yori.OUT / 'belmonte' / 'natural' / 'SM_BM_NorthApron.glb',
            yori.OUT / 'belmonte' / 'natural' / 'SM_BM_NorthCountry.glb',
            yori.OUT / 'belmonte' / 'glb' / 'SM_BM_NorthApron.glb',
            yori.OUT / 'belmonte' / 'glb' / 'SM_BM_NorthCountry.glb',
        ]
        for p in files:
            h.update(str(p.name).encode() + (p.read_bytes() if p.is_file() else b'missing'))
        return h.hexdigest()

    def __call__(self, x, y):
        return _bilinear(self.z, (np.asarray(x) - self.bounds[0]) / self.step, (np.asarray(y) - self.bounds[1]) / self.step)


# --- vertical profile -----------------------------------------------------------------------------------------------


def section_area(h, formation=FORMATION):
    """Cross-section of an embankment (h > 0) or cutting (h < 0) h metres deep, slopes 1:SLOPE."""
    d = np.abs(h)
    return d * (formation + SLOPE * d)


def cost(h, formation=FORMATION):
    """View-weighted cost per metre of line at rail-minus-ground h: earthwork volume for cuttings and embankments,
    TUNNEL_COST and VIADUCT_COST beyond them."""
    h = np.asarray(h, float)
    tunnel = -h >= TUNNEL_COVER + TUNNEL_BORE
    viaduct = h > EMBANKMENT_HEIGHT
    result = section_area(h, formation)
    result = np.where(viaduct, VIADUCT_COST + VIADUCT_RISE * (h - EMBANKMENT_HEIGHT), result)
    return np.where(tunnel, TUNNEL_COST, result)


def zones(s, length, loop=None):
    """Per chainage: 'level' (station reserves plus half a vertical curve) and 'loop' (the passing loop plus half a
    vertical curve) masks, and the hard limits of rail-minus-ground."""
    margin = VERTICAL_CURVE / 2
    level = (s <= HIDAMARI.reserve[0] + margin) | (s >= length - BELMONTE.reserve[0] - margin)
    platform = (s <= HIDAMARI.reserve[0]) | (s >= length - BELMONTE.reserve[0])
    on_loop = np.zeros_like(level)
    track = np.zeros_like(level)
    if loop is not None:
        on_loop = (s >= loop[0] - margin) & (s <= loop[1] + margin)
        track = (s >= loop[0] - STEP) & (s <= loop[1] + STEP)
    return level, platform, on_loop, track


def vertical(s, zg, grade=MAX_GRADE, loop=None, spiral=None):
    """Rail heights every STEP metres minimising the view-weighted cost, by dynamic programming over DZ levels and
    grades: the grade changes by at most DZ per STEP per STEP (a vertical curve radius of VERTICAL_RADIUS) and stays
    within `grade`, LOOP_GRADE along the loop's tracks and level along the platforms. The ground's undulations are
    followed wherever the grade allows, and no smoothing afterwards undoes it. Returns (rail z, total cost) or
    (None, inf) if no profile meets the limits."""
    s, zg = np.asarray(s, float), np.asarray(zg, float)
    length = float(s[-1])
    _, platform, _, track = zones(s, length, loop)
    datum = station_yard.floor_z() + station_yard.RAIL
    z0 = datum + math.floor((float(zg.min()) - 60. - datum) / DZ) * DZ
    levels = z0 + DZ * np.arange(int((zg.max() + 80. - z0) / DZ))
    m = len(levels)
    ds = np.diff(s, prepend=s[0])
    big = 1e18
    top = int(math.floor(grade * STEP / DZ + 1e-9))         # grade states: k levels per STEP, |k| <= top
    flat = int(math.floor(LOOP_GRADE * STEP / DZ + 1e-9))
    ks = np.arange(-top, top + 1)

    def row(i):
        h = levels - zg[i]
        if spiral is not None and spiral[i]:        # the spiral is a tunnel wherever it runs: keep SPIRAL_COVER over it
            return (TUNNEL_COST + COVER_COST * np.maximum(h + SPIRAL_COVER, 0.)) * max(ds[i], 1.)
        c = cost(h, FORMATION + (TRACK_SPACING if track[i] else 0.)) * max(ds[i], 1.)
        if platform[i]:
            c = np.where(np.abs(h) <= PLATFORM_OFFSET, c, big)
        if s[i] <= HIDAMARI.reserve[0]:
            # A fixed station cannot follow the optimizer up or down by PLATFORM_OFFSET metres.
            c = np.where(np.abs(levels - datum) < DZ / 2, c, big)
        if track[i]:
            c = np.where((h > -(TUNNEL_COVER + TUNNEL_BORE)) & (h <= EMBANKMENT_HEIGHT), c, big)
        return c

    acc = np.full((m, len(ks)), big)
    acc[:, top] = row(0)                                     # level at the buffer stop
    back = np.zeros((len(s), m, len(ks)), np.int8)
    for i in range(1, len(s)):
        allowed = 0 if (platform[i] and platform[i - 1]) else flat if (track[i] or track[i - 1]) else top
        scale = ds[i] / STEP
        padded = np.pad(acc, ((0, 0), (1, 1)), constant_values=big)
        choice = np.stack([padded[:, :-2], padded[:, 1:-1], padded[:, 2:]])   # from grade k-1, k, k+1
        arg = np.argmin(choice, 0)
        best = np.take_along_axis(choice, arg[None], 0)[0]
        new = np.full((m, len(ks)), big)
        r = row(i)
        for c, k in enumerate(ks):
            if abs(k) > allowed:
                continue
            d = int(round(k * scale))
            col = np.full(m, big)
            if d > 0:
                col[d:] = best[:-d, c]
            elif d < 0:
                col[:d] = best[-d:, c]
            else:
                col = best[:, c].copy()
            new[:, c] = col + r
        acc = np.minimum(new, big)
        back[i] = (arg - 1).astype(np.int8)        # per level before the step: the grade column offset it came from
    acc[:, np.abs(ks) > 0] = big                             # level at the far buffer stop too
    j, c = np.unravel_index(int(np.argmin(acc)), acc.shape)
    total = float(acc[j, c])
    if total >= big:
        return None, math.inf
    index = np.empty(len(s), int)
    for i in range(len(s) - 1, -1, -1):
        index[i] = j
        if i == 0:
            break
        j -= int(round(ks[c] * ds[i] / STEP))       # the level before this step, then the grade it came from
        c += int(back[i, j, c])
    return levels[index], total


def smooth(z, s):
    """Moving average over VERTICAL_CURVE on the STEP grid: grade changes become parabolic vertical curves and the
    grade limit holds (the average of slopes within it). The shorter last interval is resampled."""
    regular = np.arange(0., s[-1] + 1e-6, STEP)
    zr = np.interp(regular, s, z)
    n = int(round(VERTICAL_CURVE / STEP)) | 1
    padded = np.pad(zr, n // 2, mode='edge')
    out = np.convolve(padded, np.ones(n) / n, mode='valid')
    return np.interp(s, regular, out)


# --- classification and structures ----------------------------------------------------------------------------------

KINDS = ('cutting', 'deep cutting', 'tunnel', 'embankment', 'viaduct')


def classify(h, spiral=None):
    """Class per sample from rail minus ground; the spiral loop is tunnel throughout."""
    h = np.asarray(h, float)
    kind = np.where(h >= 0, 'embankment', 'cutting').astype(object)
    kind[(h < -CUT_DEPTH)] = 'deep cutting'
    kind[-h >= TUNNEL_COVER + TUNNEL_BORE] = 'tunnel'
    kind[h > EMBANKMENT_HEIGHT] = 'viaduct'
    if spiral is not None:
        kind[np.asarray(spiral, bool)] = 'tunnel'
    kind = merge(kind)
    if spiral is not None:
        kind[np.asarray(spiral, bool)] = 'tunnel'
    return kind


def _runs(kind):
    runs, start = [], 0
    for i in range(1, len(kind) + 1):
        if i == len(kind) or kind[i] != kind[start]:
            runs.append([kind[start], start, i])
            start = i
    return runs


def merge(kind):
    """Tunnels shorter than MIN_TUNNEL become deep cuttings and viaducts shorter than MIN_VIADUCT embankments; a short
    gap between two tunnels (or two viaducts) joins them."""
    kind = np.array(kind, dtype=object)
    for structure, minimum, fallback, gap_kinds in (('tunnel', MIN_TUNNEL, 'deep cutting', ('deep cutting', 'cutting')),
                                                    ('viaduct', MIN_VIADUCT, 'embankment', ('embankment',))):
        runs = _runs(kind)
        for a, b, c in zip(runs, runs[1:], runs[2:]):
            if a[0] == c[0] == structure and b[0] in gap_kinds and (b[2] - b[1]) * STEP < minimum:
                kind[b[1]:b[2]] = structure
        for name, i0, i1 in _runs(kind):
            if name == structure and (i1 - i0) * STEP < minimum:
                kind[i0:i1] = fallback
    return kind


def structures(line, rail, zg, kind):
    result = []
    for name, i0, i1 in _runs(kind):
        h = rail[i0:i1] - zg[i0:i1]
        s0 = float(line.s[i0] - (STEP / 2 if i0 else 0.))
        s1 = float(line.s[i1 - 1] + (STEP / 2 if i1 < len(line.s) else 0.))
        spiral = bool(line.spiral_mask()[i0:i1].any()) and name == 'tunnel'
        result.append({'kind': name, 'name': 'spiral tunnel' if spiral else name,
                       'start': round(s0, 1), 'end': round(s1, 1), 'length': round(s1 - s0, 1),
                       'extreme': round(float(h.max() if h.mean() > 0 else -h.min()), 1),
                       'start_xy': [round(float(line.x[i0]), 1), round(float(line.y[i0]), 1)],
                       'end_xy': [round(float(line.x[i1 - 1]), 1), round(float(line.y[i1 - 1]), 1)]})
    return result


def earthworks(line, rail, zg, kind, loop=None):
    """Cut and fill volumes (m3) of cuttings and embankments; the loop's stretch is TRACK_SPACING wider."""
    h = rail - zg
    ds = np.gradient(line.s)
    width = np.full(len(h), FORMATION)
    if loop is not None:
        width[(line.s >= loop[0]) & (line.s <= loop[1])] += TRACK_SPACING
    area = section_area(h, width) * ds
    cut = np.isin(kind, ('cutting', 'deep cutting'))
    fill = kind == 'embankment'
    return float(area[cut].sum()), float(area[fill].sum())


# --- operation ------------------------------------------------------------------------------------------------------


def posted_limits(line, step=1.):
    """Posted curve limits as (start, end, m/s, radius), each over its whole curve with the transitions, from the
    alignment's curvature; the spiral is one long limit. MAX_SPEED elsewhere."""
    s = np.arange(0., line.length + step / 2, step)
    k = np.abs(np.interp(s, line.s, line.curvature))
    curved = k > 1e-7
    result = []
    for name, i0, i1 in _runs(curved):
        if not name:
            continue
        radius = 1 / float(k[i0:i1].max())
        limit = curve_limit(radius)
        if limit < MAX_SPEED - 1e-9:
            result.append((float(s[i0]), float(s[i1 - 1]), limit, radius))
    return result


def resistance(v):
    """Davis rolling resistance of the whole train at speed v, newtons."""
    return (DAVIS[0] + DAVIS[1] * v + DAVIS[2] * v * v) * MASS / 1e3


def balancing_speed(grade):
    """The speed the engine's power holds on a steady climb (m/s), at most MAX_SPEED."""
    v = MAX_SPEED
    for _ in range(60):
        v = min(MAX_SPEED, POWER / max(resistance(v) + MASS * GRAVITY * grade, 1.))
    return v


def tunnel_covered(line, tunnel, head, direction):
    """@cc [owner:fontanierh,label:correctness] train-hidden-speed-containment
    A boosted head position MUST put the complete consist inside one continuous tunnel.
    Separate tunnels MUST NOT bridge an exposed gap. Coverage is conservative at sampled
    portal boundaries; a half-cell beyond the first/last tunnel sample is never boosted.
    """
    head = np.asarray(head, float)
    covered = np.zeros(head.shape, bool)
    if tunnel is None:
        return covered
    tunnel = np.asarray(tunnel, bool)
    if tunnel.shape != line.s.shape:
        raise ValueError('Tunnel mask must have one value per line sample')
    rear = head - direction * TRAIN_LENGTH
    low, high = np.minimum(head, rear), np.maximum(head, rear)
    for inside, start, end in _runs(tunnel):
        if inside:
            covered |= (low >= line.s[start]) & (high <= line.s[end - 1])
    return covered


def run(line, rail=None, direction=1, step=1., stop=None, tunnel=None):
    """Run between the platform centres, H2 to Belmonte (direction 1) or back (-1): head chainage, time and speed
    arrays. The train brakes at BRAKING to reach a posted limit where the curve starts and keeps it until its rear
    has left the curve; it accelerates at most at ACCELERATION and as the engine's POWER allows against the grade
    and DAVIS resistance; descents are limited only by the posted limits and MAX_SPEED. It starts with its head
    TRAIN_LENGTH + STOP_CLEARANCE from the end it leaves (the train reversed there) and stops with its head
    STOP_CLEARANCE from the far end, so the whole train stands on the station reserve.
    With `stop` (a chainage) it also comes to a stand there. With a tunnel mask on line.s,
    a fully covered consist may use TUNNEL_SPEED and TUNNEL_ACCELERATION; braking still
    restores the posted limit before any part leaves the tunnel."""
    first, last = STOP_CLEARANCE + TRAIN_LENGTH, line.length - STOP_CLEARANCE
    if direction < 0:
        first, last = line.length - first, STOP_CLEARANCE
    d = np.arange(0., abs(last - first) + step / 2, step)
    c = first + direction * d
    limit = np.full(len(d), MAX_SPEED)
    for a, b, v, _ in posted_limits(line):
        lo, hi = (a, b + TRAIN_LENGTH) if direction > 0 else (a - TRAIN_LENGTH, b)
        limit[(c >= lo) & (c <= hi)] = np.minimum(limit[(c >= lo) & (c <= hi)], v)
    hidden = tunnel_covered(line, tunnel, c, direction)
    limit[hidden] = TUNNEL_SPEED
    if rail is None:
        grade = np.zeros(len(d))
    else:
        grade = direction * np.interp(c, line.s, np.gradient(np.asarray(rail, float), line.s))
    vb = limit.copy()
    vb[-1] = 0.
    halt = None if stop is None else int(np.argmin(np.abs(c - stop)))
    if halt is not None:
        vb[halt] = 0.
    for i in range(len(d) - 2, -1, -1):
        vb[i] = min(vb[i], math.sqrt(vb[i + 1] ** 2 + 2 * BRAKING * step))
    v = np.zeros(len(d))
    for i in range(len(d) - 1):
        u = v[i]
        force = POWER / max(u, 1.) - resistance(u) - MASS * GRAVITY * grade[i]
        acc = TUNNEL_ACCELERATION if hidden[i] else min(ACCELERATION, force / MASS)
        v[i + 1] = min(vb[i + 1], math.sqrt(max(u * u + 2 * acc * step, 1.)))
    if halt is not None:
        v[halt] = 0.
    v[-1] = 0.
    mean = (v[1:] + v[:-1]) / 2
    t = np.r_[0., np.cumsum(step / np.maximum(mean, .5))]
    return c, t, v


def crossing(up, down, at):
    """Seconds the Hidamari train must leave after the Belmonte one for them to pass chainage `at` together."""
    t_up = float(np.interp(at, up[0], up[1]))
    t_down = float(np.interp(at, down[0][::-1], down[1][::-1]))
    return t_down - t_up


def _at(r, chainage):
    """Time a run's head reaches `chainage`."""
    c, t = r[0], r[1]
    return float(np.interp(chainage, c, t) if c[-1] > c[0] else np.interp(chainage, c[::-1], t[::-1]))


def service(line, rail, loop, up=None, down=None, tunnel=None):
    """The two-train timetable with DWELL at both ends and the crossing at `loop`. Both trains run one schedule half
    a cycle apart. At each crossing the train of one direction (the same every time) arrives first, stops with its
    head TURNOUT + 10 m short of the far turnout and stands until the other's rear has cleared that turnout plus
    CROSSING_MARGIN; the other runs through, entering the loop only once the first has stopped. Both choices of who
    waits are solved in closed form and the shorter cycle wins; each station sees a departure every half cycle."""
    up = up or run(line, rail, 1, tunnel=tunnel)
    down = down or run(line, rail, -1, tunnel=tunnel)
    a, b = loop
    U, D = float(up[1][-1]), float(down[1][-1])
    best = None
    for waiting in (1, -1):
        if waiting > 0:         # the up train waits near the Belmonte-side turnout
            halt = b - TURNOUT - 10.
            stopping = run(line, rail, 1, stop=halt, tunnel=tunnel)
            arrive, U0 = _at(stopping, halt), float(stopping[1][-1])
            enter, clear = _at(down, b), _at(down, b - TRAIN_LENGTH)
            # the down train leaves Belmonte (U0 + wait - D) / 2 after the up one leaves H2: it reaches the loop
            # after the up train has stopped, and the up train leaves after it has cleared the far turnout
            wait = max(0., 2 * (arrive - enter) - U0 + D, 2 * (clear + CROSSING_MARGIN - arrive) + U0 - D)
            up_time, down_time = U0 + wait, D
        else:                   # the down train waits near the Hidamari-side turnout
            halt = a + TURNOUT + 10.
            stopping = run(line, rail, -1, stop=halt, tunnel=tunnel)
            arrive, D0 = _at(stopping, halt), float(stopping[1][-1])
            enter, clear = _at(up, a), _at(up, a + TRAIN_LENGTH)
            wait = max(0., U - D0 + 2 * (arrive - enter), 2 * (clear + CROSSING_MARGIN - arrive) - U + D0)
            up_time, down_time = U, D0 + wait
        cycle = up_time + down_time + 2 * DWELL
        if best is None or cycle < best[0] - 1e-6:
            best = (cycle, waiting, wait, arrive, up_time, down_time)
    cycle, waiting, wait, arrive, up_time, down_time = best
    half = cycle / 2
    phase = (up_time - down_time) / 2       # the first down departure from Belmonte, after the up one from H2
    if waiting > 0:
        up_loop, down_loop = (arrive, arrive + wait), (_at(down, b), _at(down, a))
    else:
        up_loop, down_loop = (_at(up, a), _at(up, b)), (arrive, arrive + wait)

    def leg(direction, depart, at_loop, total):
        return {'direction': direction, 'depart_s': round(depart, 1), 'loop_arrive_s': round(depart + at_loop[0], 1),
                'loop_leave_s': round(depart + at_loop[1], 1), 'arrive_s': round(depart + total, 1)}

    up_leg = ('Hidamari -> Belmonte', up_loop, up_time)
    down_leg = ('Belmonte -> Hidamari', down_loop, down_time)
    schedule = [{'train': 'A', 'legs': [leg(up_leg[0], 0., *up_leg[1:]), leg(down_leg[0], phase + half, *down_leg[1:])]},
                {'train': 'B', 'legs': [leg(down_leg[0], phase, *down_leg[1:]), leg(up_leg[0], half, *up_leg[1:])]}]
    return {'trains': 2, 'dwell_s': DWELL, 'cycle_s': round(cycle, 1), 'headway_s': round(half, 1),
            'headway_min': round(half / 60, 2), 'waiting_direction': 'up' if waiting > 0 else 'down',
            'loop_wait_s': round(wait, 1), 'crossing_margin_s': CROSSING_MARGIN,
            'run_up_s': round(up_time, 1), 'run_down_s': round(down_time, 1),
            'asked_for_headway_s': ASKED_INTERVAL, 'asked_for_works': half <= ASKED_INTERVAL,
            # the speed profiles' chainage is the leading end's (the head stops STOP_CLEARANCE from the line's end)
            'profile_reference': 'head', 'train_length_m': TRAIN_LENGTH,
            'times_note': 'seconds from train A leaving Hidamari; the pattern repeats every cycle_s and each station '
                          'sees a departure every headway_s; a waiting train\'s run time includes its stop and wait',
            'schedule': schedule}


def loop_candidates(line, lo, hi):
    """Loop windows [start, end] of LOOP_TOTAL inside (lo, hi) whose curvature stays within 1 / LOOP_RADIUS."""
    margin = VERTICAL_CURVE / 2
    k = np.abs(line.curvature)
    out = []
    for centre in np.arange(lo, hi, STEP):
        a, b = centre - LOOP_TOTAL / 2, centre + LOOP_TOTAL / 2
        if a < HIDAMARI.reserve[0] + VERTICAL_CURVE + margin or b > line.length - BELMONTE.reserve[0] - VERTICAL_CURVE - margin:
            continue
        on = (line.s >= a - STEP) & (line.s <= b + STEP)
        if k[on].max() <= 1 / LOOP_RADIUS + 1e-9:
            out.append((float(a), float(b)))
    return out


def loop_track(line, loop, side):
    """The loop's second track, TRACK_SPACING to one side (+1 left, -1 right) with turnouts easing in over TURNOUT."""
    s = np.arange(loop[0], loop[1] + 1e-6, 5.)
    x, y, h, _ = line.at(s)
    t = np.clip(np.minimum(s - loop[0], loop[1] - s) / TURNOUT, 0, 1)
    offset = side * TRACK_SPACING * (1 - np.cos(math.pi * t)) / 2
    return np.stack([s, x - np.sin(h) * offset, y + np.cos(h) * offset], 1)


# --- views and empty spaces -----------------------------------------------------------------------------------------


def views(line, rail, kind, raster, trees=None):
    """Rays every degree from every VIEW_STEP metres at rail + EYE against the raster. Per viewpoint: visible ground
    area within VIEW_RANGE, farthest visible ground, the ten-degree rays' reach, flags; plus the visible cells."""
    s = np.arange(0., line.length + 1e-6, VIEW_STEP)
    x, y, _, _ = line.at(s)
    eye = np.interp(s, line.s, rail) + EYE
    tunnel = np.array([kind[min(int(round(a / STEP)), len(kind) - 1)] == 'tunnel' for a in s])
    azimuth = np.radians(np.arange(0, 360, 1.))
    radius = np.arange(RAY_STEP, VIEW_RANGE + 1e-6, RAY_STEP)
    ca, sa = np.cos(azimuth), np.sin(azimuth)
    v = volcano()
    points, rows = [], []
    for i in range(len(s)):
        px = x[i] + ca[:, None] * radius[None, :]
        py = y[i] + sa[:, None] * radius[None, :]
        z = raster(px, py)
        slope = (z - eye[i]) / radius[None, :]
        before = np.maximum.accumulate(np.concatenate([np.full((len(azimuth), 1), -np.inf), slope[:, :-1]], 1), axis=1)
        visible = (slope >= before) & ~tunnel[i]
        area = float((visible * radius[None, :]).sum() * RAY_STEP * (2 * math.pi / len(azimuth)))
        reach = np.where(visible.any(1), np.where(visible, radius[None, :], 0).max(1), 0.)
        rays = reach[::10]
        far = rays >= BIG_VIEW
        bearing = math.degrees(math.atan2(v[1] - y[i], v[0] - x[i])) % 360
        towards = [(int(a) % 360) for a in np.arange(0, 360, 10)[far]]
        volcano_view = any(abs((a - bearing + 180) % 360 - 180) <= 20 for a in towards)
        near_trees = 0
        if trees is not None and len(trees):
            near_trees = int((np.hypot(trees[:, 0] - x[i], trees[:, 1] - y[i]) < 40).sum())
        flags = []
        if far.sum() >= 3:
            flags.append('big view')
        if volcano_view:
            flags.append('volcano')
        if tunnel[i]:
            flags.append('closed: tunnel')
        elif rays.max() < 300:
            flags.append('closed: terrain')
        elif near_trees >= 25 and far.sum() < 3:
            flags.append('closed: forest')
        rows.append({'s': float(s[i]), 'xy': [round(float(x[i]), 1), round(float(y[i]), 1)], 'eye_z': round(float(eye[i]), 1),
                     'visible_area_ha': round(area / 1e4, 1), 'farthest': float(reach.max()),
                     'rays_10deg': [float(r) for r in rays], 'flags': flags})
        near = visible & (radius[None, :] <= EMPTY_RANGE)
        points.append(np.stack([px[near], py[near], np.full(int(near.sum()), s[i])], 1))
    return rows, np.concatenate(points)


def stretches(rows, test):
    out, start = [], None
    for i, row in enumerate(rows + [None]):
        hit = row is not None and test(row)
        if hit and start is None:
            start = i
        if not hit and start is not None:
            out.append([rows[start]['s'], rows[i - 1]['s']])
            start = None
    return out


PLANTS = ('Tree', 'Bush', 'Grass', 'Flower', 'Shrub', 'Fern', 'Reed', 'Plant')


def content_points():
    """Placed content as (built, plants, trees, boxes): Hidamari city instances (its backdrop forest included) and
    buildings, the 600 m square's instances, Belmonte's runtime placements, and the footprints of Belmonte's baked
    meshes (boxes, counted as built)."""
    built, plants, trees, boxes = [], [], [], []

    def add(name, xy, plant=None):
        plant = name.startswith(PLANTS) if plant is None else plant
        (plants if plant else built).append(xy)
        if plant and name.startswith('Tree'):
            trees.append(xy)

    city = yori.OUT / 'hidamari/city.json'
    if city.exists():
        data = json.loads(city.read_text())
        for name, items in data['instances'].items():
            add(name, np.asarray(items, float).reshape(-1, 5)[:, :2])
        built.append(np.asarray([b['position'][:2] for b in data['buildings']], float).reshape(-1, 2))
    world = yori.OUT / 'world.json'
    if world.exists():
        for name, items in json.loads(world.read_text()).get('instances', {}).items():
            if items:
                add(name, np.asarray(items, float).reshape(len(items), -1)[:, :2])
    runtime = yori.OUT / 'belmonte/runtime.json'
    if runtime.exists():
        from belmonte import layout as BM, source
        data = json.loads(runtime.read_text())
        meshes = {entry['name']: entry for entry in source.manifest()['meshes']}
        for group in data['groups']:
            name = group['asset'].split('.')[-1]
            xy = []
            for transform in group['transforms']:
                tx, ty, _ = transform['translation_cm']
                if tx == 0 and ty == 0 and name in meshes:
                    (x0, y0, _), (x1, y1, _) = meshes[name]['bounds_m']
                    if max(x1 - x0, y1 - y0) <= 400 and 'Terrain' not in name and 'Water' not in name:
                        boxes.append((x0 + BM.ORIGIN[0], y0 + BM.ORIGIN[1], x1 + BM.ORIGIN[0], y1 + BM.ORIGIN[1]))
                    continue
                xy.append((tx / 100 + BM.ORIGIN[0], -ty / 100 + BM.ORIGIN[1]))
            if xy:
                add(name.replace('Tree_Tuscan', 'Tree'), np.asarray(xy), bool(group['plant']))
    flat = lambda parts: np.concatenate(parts) if parts else np.zeros((0, 2))   # noqa: E731
    return flat(built), flat(plants), flat(trees), boxes


def _count(points, x0, y0, nx, ny):
    count = np.zeros((ny, nx), int)
    i = ((points[:, 0] - x0) // CELL).astype(int)
    j = ((points[:, 1] - y0) // CELL).astype(int)
    on = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    np.add.at(count, (j[on], i[on]), 1)
    return count


def _groups(mask):
    label = np.zeros(mask.shape, int)
    groups = []
    for j, i in zip(*np.nonzero(mask)):
        if label[j, i]:
            continue
        stack, cells = [(j, i)], []
        label[j, i] = len(groups) + 1
        while stack:
            a, b = stack.pop()
            cells.append((a, b))
            for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                c, d = a + da, b + db
                if 0 <= c < mask.shape[0] and 0 <= d < mask.shape[1] and mask[c, d] and not label[c, d]:
                    label[c, d] = len(groups) + 1
                    stack.append((c, d))
        groups.append(cells)
    return groups


def empty_spaces(line, seen, raster, built, plants, boxes, minimum_cells=8):
    """Connected groups of CELL metre cells seen from the line within EMPTY_RANGE, on land and more than 40 m from the
    track, that hold no built content: 'bare' (at most one plant) or 'woodland' (planting only). Candidate sites for
    future scenery, largest first."""
    x0, y0 = raster.bounds[0], raster.bounds[1]
    nx = int((raster.bounds[2] - x0) // CELL) + 1
    ny = int((raster.bounds[3] - y0) // CELL) + 1
    seen_cells = np.zeros((ny, nx), bool)
    first = np.full((ny, nx), np.inf)
    last = np.full((ny, nx), -np.inf)
    ci = ((seen[:, 0] - x0) // CELL).astype(int)
    cj = ((seen[:, 1] - y0) // CELL).astype(int)
    ok = (ci >= 0) & (ci < nx) & (cj >= 0) & (cj < ny)
    ci, cj, cs = ci[ok], cj[ok], seen[ok, 2]
    seen_cells[cj, ci] = True
    np.minimum.at(first, (cj, ci), cs)
    np.maximum.at(last, (cj, ci), cs)
    structure = _count(built, x0, y0, nx, ny)
    for bx0, by0, bx1, by1 in boxes:
        i0, i1 = int((bx0 - x0) // CELL), int((bx1 - x0) // CELL)
        j0, j1 = int((by0 - y0) // CELL), int((by1 - y0) // CELL)
        structure[max(j0, 0):max(j1 + 1, 0), max(i0, 0):max(i1 + 1, 0)] += 1
    planting = _count(plants, x0, y0, nx, ny)
    cx = x0 + (np.arange(nx) + .5) * CELL
    cy = y0 + (np.arange(ny) + .5) * CELL
    gx, gy = np.meshgrid(cx, cy)
    land = raster(gx, gy) > .5
    distance = np.full(gx.shape, np.inf)
    for px, py in zip(line.x[::2], line.y[::2]):
        distance = np.minimum(distance, np.hypot(gx - px, gy - py))
    free = seen_cells & land & (structure == 0) & (distance > 40) & (distance <= EMPTY_RANGE)
    result = []
    for kind, mask in (('bare', free & (planting <= 1)), ('woodland', free & (planting > 1))):
        for cells in _groups(mask):
            if len(cells) < minimum_cells:
                continue
            js, iis = np.array(cells).T
            centres = np.stack([cx[iis], cy[js]], 1)
            result.append({'kind': kind, 'area_ha': round(len(cells) * CELL * CELL / 1e4, 1),
                           'centroid': [round(float(v), 1) for v in centres.mean(0)],
                           'bbox': [float(centres[:, 0].min() - CELL / 2), float(centres[:, 1].min() - CELL / 2),
                                    float(centres[:, 0].max() + CELL / 2), float(centres[:, 1].max() + CELL / 2)],
                           'distance_from_line': [round(float(distance[js, iis].min())), round(float(distance[js, iis].max()))],
                           'plants_per_ha': round(float(planting[js, iis].mean()) * 1e4 / CELL ** 2, 1),
                           'seen_from': [float(first[js, iis].min()), float(last[js, iis].max())],
                           'cells': centres.round(1).tolist()})
    result.sort(key=lambda item: (item['kind'] != 'bare', -item['area_ha']))
    for n, item in enumerate(result):
        item['id'] = n + 1
    return result


# --- clearances -----------------------------------------------------------------------------------------------------


def hidamari_clearance(line):
    """Nearest Hidamari building footprint (city.json, rectangles) to the track centre line, metres."""
    path = yori.OUT / 'hidamari/city.json'
    if not path.exists():
        return None
    best = (math.inf, None)
    pts = np.c_[line.x, line.y]
    for b in json.loads(path.read_text())['buildings']:
        x, y = b['position'][:2]
        a = math.radians(b.get('yaw', 0.))
        d = pts - (x, y)
        u = np.abs(d[:, 0] * math.cos(a) + d[:, 1] * math.sin(a)) - b.get('width', 10.) / 2
        v = np.abs(-d[:, 0] * math.sin(a) + d[:, 1] * math.cos(a)) - b.get('depth', 10.) / 2
        dist = float(np.hypot(np.maximum(u, 0), np.maximum(v, 0)).min())
        if dist < best[0]:
            best = (dist, b['asset'])
    return {'distance': round(best[0], 1), 'asset': best[1]}


def belmonte_clearance(line):
    """Nearest Belmonte building (town blocks, estates, farms; placed meshes) to the centre line, and the water the
    line bridges."""
    from belmonte import layout as BM, planting, source
    data = source.manifest()
    models = {entry['source_asset']: entry for entry in data['meshes']}
    near = (line.y > BM.BOUNDS[1] - 200)
    pts = np.c_[line.x[near], line.y[near]]
    best, water = (math.inf, None), set()
    for placement in data['placements']:
        model = models[placement['asset']]
        name = model['name']
        building = name.startswith(('SM_BM_BT_blk_', 'SM_BM_BH_', 'SM_BM_BVV_Farm_', 'SM_BM_BVV_Village'))
        building |= name.startswith('SM_BM_BE_') and name.endswith(('Stables', 'Villa', 'Accent'))
        wet = name.startswith('SM_BM_BC_Water_')
        if not (building or wet):
            continue
        faces = source.triangles(source.LIBRARY / model['path'])
        t = placement['transform']
        native = faces.reshape(-1, 3) * np.array([100., -100., 100.]) * t['scale']
        native = planting.rotate(t['rotation_xyzw'], native) + t['translation_cm']
        world = native / np.array([100., -100., 100.]) + BM.ORIGIN
        lo, hi = world[:, :2].min(0), world[:, :2].max(0)
        u = np.maximum(np.maximum(lo[0] - pts[:, 0], pts[:, 0] - hi[0]), 0)
        v = np.maximum(np.maximum(lo[1] - pts[:, 1], pts[:, 1] - hi[1]), 0)
        dist = float(np.hypot(u, v).min()) if len(pts) else math.inf
        if wet and dist == 0:
            water.add(name)
        if building and dist < best[0]:
            best = (dist, name)
    return {'distance': round(best[0], 1), 'asset': best[1], 'bridges': sorted(water)}


# --- the study ------------------------------------------------------------------------------------------------------


def profile(line, sampler=ground, grade=MAX_GRADE, loop=None):
    zg = np.asarray(sampler(line.x, line.y), float)
    rail, total = vertical(line.s, zg, grade, loop, line.spiral_mask())
    return zg, rail, total


def place_loop(line, zg, grade, tries=None, every=3):
    """The passing loop. Every `every`th candidate window is timed on the profile without a loop; the LOOP_TRIES
    quickest with a feasible profile get it and the one with the shortest headway wins, its earthworks (HEADWAY_COST m3 per
    second) breaking near-ties. With `tries` (the optimiser) the first feasible window in time order wins,
    trying only windows where the profile without a loop already runs in cutting or on embankment and the `tries`
    nearest others. Returns (loop, rail, cost, meeting s); cost is the profile's own."""
    spiral = line.spiral_mask()
    plain, _ = vertical(line.s, zg, grade, spiral=spiral)
    h = None if plain is None else plain - zg
    up, down = run(line, plain, 1), run(line, plain, -1)
    meet = float(up[0][np.argmin(np.abs(np.array([crossing(up, down, c) for c in up[0][::20]])))
                       * 20])

    def suitable(window):
        on = (line.s >= window[0] - STEP) & (line.s <= window[1] + STEP)
        return h is None or bool(((h[on] > -(TUNNEL_COVER + TUNNEL_BORE)) & (h[on] <= EMBANKMENT_HEIGHT)).all())

    def offset(window):
        return abs(crossing(up, down, (window[0] + window[1]) / 2))

    candidates = sorted(loop_candidates(line, 0., line.length), key=offset)
    if tries is not None:
        unsuitable = 0
        for window in candidates:
            if not suitable(window):
                unsuitable += 1
                if unsuitable > tries:
                    continue
            rail, total = vertical(line.s, zg, grade, window, spiral)
            if rail is not None:
                return window, rail, total, meet
        return None, None, math.inf, meet
    windows = sorted(loop_candidates(line, 0., line.length))[::every]
    if plain is None:
        return None, None, math.inf, meet
    quick = sorted((service(line, plain, window, up, down)['headway_s'], window) for window in windows)
    best = (math.inf, None, None, math.inf)
    tried = 0
    for _, window in quick:        # the quickest windows on the profile without a loop, then on their own
        if tried >= LOOP_TRIES:
            break
        rail, total = vertical(line.s, zg, grade, window, spiral)
        if rail is None:
            continue
        tried += 1
        score = service(line, rail, window)['headway_s'] * HEADWAY_COST + total
        if score < best[0]:
            best = (score, window, rail, total)
    return best[1], best[2], best[3], meet


class InfeasibleRoute(ValueError):
    """A studied alternative cannot meet the alignment or profile constraints."""


def study(points=None, sampler=ground, grade=None):
    """Everything route.json holds except the views: alignment, ground, profile, loop, structures, operation. The
    grade limit is DESIGN_GRADE unless `grade` is given."""
    line = alignment(points)
    if line is None:
        raise InfeasibleRoute('curves do not fit the station reserves and tangent points')
    zg = np.asarray(sampler(line.x, line.y), float)
    plain = {g: vertical(line.s, zg, g, spiral=line.spiral_mask())[1] for g in (PREFERRED_GRADE, MAX_GRADE)}
    if grade is None:
        grade = DESIGN_GRADE
    rail = None
    if points is None and LOOP is not None:      # the approved line keeps its approved loop
        _, _, total, meet = place_loop(line, zg, grade, tries=0)
        loop = LOOP
        rail, total = vertical(line.s, zg, grade, loop, line.spiral_mask())
    if points is not None or LOOP is None or rail is None:     # other lines, or a grade the approved loop cannot take
        loop, rail, total, meet = place_loop(line, zg, grade)
    if rail is None and grade < MAX_GRADE:
        grade = MAX_GRADE
        loop, rail, total, meet = place_loop(line, zg, grade)
    if rail is None:
        raise InfeasibleRoute(f'no profile meets the fixed station height and {grade * 100:g}% grade limit')
    kind = classify(rail - zg, line.spiral_mask())
    tunnel = kind == 'tunnel'
    up, down = run(line, rail, 1, tunnel=tunnel), run(line, rail, -1, tunnel=tunnel)
    centre = (loop[0] + loop[1]) / 2 if loop else math.nan
    loop_time = float(np.interp(centre, up[0], up[1])) if loop else math.nan
    return dict(line=line, zg=zg, rail=rail, cost=total, grade_limit=grade, plain_costs=plain, loop=loop, meet=meet,
                kind=kind, run=up, run_down=down, one_way=float(up[1][-1]), one_way_down=float(down[1][-1]),
                loop_time=loop_time, loop_offset=crossing(up, down, centre) if loop else math.nan,
                service=service(line, rail, loop, up, down, tunnel=tunnel) if loop else None)


def summary(r):
    line, rail, zg, kind = r['line'], r['rail'], r['zg'], r['kind']
    cut, fill = earthworks(line, rail, zg, kind, r['loop'])
    grade = np.diff(rail) / np.diff(line.s)
    lengths = {k: float(np.gradient(line.s)[kind == k].sum()) for k in KINDS}
    radius = 1 / np.abs(line.curvature).max()
    dg = float(np.abs(np.diff(grade)).max())
    rv = STEP / dg if dg > 0 else math.inf
    one_way, one_way_down = r['one_way'], r['one_way_down']
    offset = r['loop_offset']
    on_backdrop = backdrop(line.x, line.y)
    ds = np.gradient(line.s)
    slow = [{'start': round(a, 1), 'end': round(b, 1), 'radius': round(radius), 'limit_kmh': round(v * 3.6)}
            for a, b, v, radius in posted_limits(line)]
    return {'length_m': round(line.length, 1), 'straight_run_time_s_at_50kmh': round(line.length / (50 / 3.6), 1),
            'max_speed_kmh': round(MAX_SPEED * 3.6), 'straight_run_time_s_at_max_speed': round(line.length / MAX_SPEED, 1),
            'curve_speed_limits': slow,
            'backdrop_length_m': round(float(ds[on_backdrop].sum()), 1),
            'backdrop_east_of_2600_m': round(float(ds[on_backdrop & (line.x > 2600)].sum()), 1),
            'backdrop_stretches': [[round(float(line.s[i0]), 1), round(float(line.s[i1 - 1]), 1)]
                                   for name, i0, i1 in _runs(on_backdrop) if name],
            'one_way_run_time_s': round(one_way, 1), 'one_way_run_time_min': round(one_way / 60, 2),
            'one_way_run_time_down_s': round(one_way_down, 1), 'one_way_run_time_down_min': round(one_way_down / 60, 2),
            'service': r['service'],
            'balancing_speed_kmh': {f'{g * 100:.1f}%': round(balancing_speed(g) * 3.6) for g in (.02, .03, .035, .04)},
            'min_radius_m': round(float(radius), 1), 'max_grade_pct': round(float(np.abs(grade).max()) * 100, 2),
            'grade_limit_pct': r['grade_limit'] * 100, 'min_vertical_curve_radius_m': round(rv),
            'min_volcano_distance_m': round(float(volcano_distance(line.x, line.y).min()), 1),
            'cut_m3': round(cut, -2), 'fill_m3': round(fill, -2),
            'lengths_m': {k: round(v, 1) for k, v in lengths.items()},
            'tunnel_share_pct': round(100 * lengths['tunnel'] / line.length, 1),
            'counts': {k: sum(1 for name, _, _ in _runs(kind) if name == k) for k in KINDS},
            'rail_z_ends': [round(float(rail[0]), 2), round(float(rail[-1]), 2)],
            'meeting_chainage': round(r['meet'], 1),
            'loop': None if r['loop'] is None else {
                'start': r['loop'][0], 'end': r['loop'][1], 'centre_time_s': round(r['loop_time'], 1),
                'half_run_s': round(one_way / 2, 1),
                'hidamari_departure_offset_s': round(offset, 1),
                'note': ('meets at the loop with simultaneous departures' if abs(offset) < 5 else
                         f"the {'Hidamari' if offset > 0 else 'Belmonte'} train leaves {abs(offset):.0f} s after "
                         f"the other (a dwell at that station) so they meet at the loop")},
            'closure_m': round(line.closure, 4),
            'tunnel_besides_spiral_m': round(float(ds[(kind == 'tunnel') & ~line.spiral_mask()].sum()), 1),
            'spirals': [spiral_report(line, rail, zg, spiral) for spiral in line.spirals]}


def spiral_report(line, rail, zg, spiral):
    """The spiral loop's figures: chainage, length, turns, radius, speed limit, height gained, cover, entry and exit
    (the loop's clothoid ends) and the circle's centre."""
    on = (line.s >= spiral['start']) & (line.s <= spiral['end'])
    x, y, _, _ = line.at([spiral['start'], spiral['end']])
    ring = on & (np.abs(np.abs(line.curvature) - 1 / spiral['radius']) < 1e-6)
    return {'start': round(float(spiral['start']), 1), 'end': round(float(spiral['end']), 1),
            'length': round(float(spiral['end'] - spiral['start']), 1), 'turns': spiral['turns'],
            'radius': spiral['radius'], 'limit_kmh': round(curve_limit(spiral['radius']) * 3.6),
            'rail_z': [round(float(np.interp(spiral['start'], line.s, rail)), 1),
                       round(float(np.interp(spiral['end'], line.s, rail)), 1)],
            'height_gained': round(float(np.interp(spiral['end'], line.s, rail) - np.interp(spiral['start'], line.s, rail)), 1),
            'min_cover': round(float((zg[on] - rail[on]).min() - TUNNEL_BORE), 1),
            'entry_xy': [round(float(x[0]), 1), round(float(y[0]), 1)],
            'exit_xy': [round(float(x[1]), 1), round(float(y[1]), 1)],
            'centre': [round(float(line.x[ring].mean()), 1), round(float(line.y[ring].mean()), 1)] if ring.any() else None}


def brief(report):
    """The figures the alternatives are compared on."""
    lengths = report['lengths_m']
    loop = report['loop'] or {}
    return {'length_m': report['length_m'], 'run_min': report['one_way_run_time_min'],
            'run_down_min': report['one_way_run_time_down_min'],
            'headway_s': (report['service'] or {}).get('headway_s'),
            'grade_limit_pct': round(report['grade_limit_pct'], 1), 'tunnel_m': lengths['tunnel'],
            'tunnel_pct': report['tunnel_share_pct'], 'viaduct_m': lengths['viaduct'],
            'deep_cutting_m': lengths['deep cutting'], 'cut_m3': report['cut_m3'], 'fill_m3': report['fill_m3'],
            'loop_offset_s': loop.get('hidamari_departure_offset_s'), 'backdrop_m': report['backdrop_length_m']}


def optimise(sampler, iterations=6, grade=MAX_GRADE):
    """Pattern search over FIRST, the inner tangent points and LAST against the profile cost, the volcano clearance and
    the loop. Prints the result; paste it into FIRST, PIS and LAST. A fixed-radius tangent point (fixed_radii) stays
    where it is: the line follows an existing curve there."""
    v = [FIRST, *np.ravel([p[:2] for p in PIS]), LAST]
    pinned = set(fixed_radii())

    def score(values):
        pis = [(*(PIS[i][:2] if i + 2 in pinned else xy), *PIS[i][2:])
               for i, xy in enumerate(np.reshape(values[1:-1], (-1, 2)))]
        line = alignment(tangent_points(values[0], pis, values[-1]), loops=spiral_loops(pis), radii=fixed_radii(pis))
        if line is None:
            return math.inf
        clearance = float(volcano_distance(line.x, line.y).min())
        penalty = max(0., VOLCANO_CLEARANCE + 10 - clearance) * 1e6
        zg = sampler(line.x, line.y)
        loop, rail, total, meet = place_loop(line, zg, grade, tries=8)
        if rail is None:            # too short for the climb and the loop: reward length until a profile fits
            return 1e12 - line.length * 1e6 + penalty
        up, down = run(line, rail, 1), run(line, rail, -1)
        offset = abs(crossing(up, down, (loop[0] + loop[1]) / 2))
        both = up[1][-1] + down[1][-1]
        loops = spiral_loops(pis)
        open_curves = [c for i, c in enumerate(line.curves) if i + 1 not in loops]
        radius = sum(max(0., full_speed_radius() - c[1]) for c in open_curves) * 2000.   # local speed limits are allowed
        bend = sum(max(0., abs(math.degrees(c[0])) - MAX_BEND) for c in open_curves) * 1e5    # no horseshoes
        kind = classify(rail - zg, line.spiral_mask())
        other = float(((kind == 'tunnel') & ~line.spiral_mask()).sum() * STEP)
        budget = max(0., other - TUNNEL_BUDGET) * 5e4
        slow = max(0., both - 2 * (ASKED_INTERVAL - DWELL)) * 1e5 + RUN_COST * both / 2
        return total + penalty + OFFSET_COST * offset + radius + bend + budget + slow

    best = score(v)
    step = 80.
    for _ in range(iterations):
        improved = True
        while improved:
            improved = False
            for i in range(len(v)):
                if 0 < i < len(v) - 1 and (i - 1) // 2 + 2 in pinned:
                    continue
                for d in (step, -step):
                    trial = list(v)
                    trial[i] += d
                    value = score(trial)
                    if value < best:
                        best, v, improved = value, trial, True
                        print(f'  cost {best:,.0f}  {np.round(v).tolist()}', flush=True)
        step /= 2
    print('FIRST =', round(float(v[0]), 1))
    xy = np.reshape(v[1:-1], (-1, 2))
    print('PIS =', [(round(float(a), 1), round(float(b), 1), *PIS[i][2:]) for i, (a, b) in enumerate(xy)])
    print('LAST =', round(float(v[-1]), 1))
    return v


# --- drawing --------------------------------------------------------------------------------------------------------

COLOURS = {'cutting': (196, 140, 64), 'deep cutting': (150, 86, 30), 'tunnel': (60, 60, 70),
           'embankment': (70, 140, 70), 'viaduct': (40, 90, 200)}


def draw_profile(path, r):
    from PIL import Image, ImageDraw
    line, rail, zg, kind = r['line'], r['rail'], r['zg'], r['kind']
    w, h, m = 2000, 700, 60
    zlo, zhi = min(zg.min(), rail.min()) - 10, max(zg.max(), rail.max()) + 10
    X = lambda s: m + (w - 2 * m) * s / line.length                       # noqa: E731
    Y = lambda z: h - m - (h - 2 * m) * (z - zlo) / (zhi - zlo)           # noqa: E731
    img = Image.new('RGB', (w, h), (250, 248, 242))
    d = ImageDraw.Draw(img)
    for z in range(int(zlo // 50 * 50), int(zhi) + 1, 50):
        d.line([(m, Y(z)), (w - m, Y(z))], fill=(225, 222, 214))
        d.text((8, Y(z) - 6), f'{z} m', fill=(90, 90, 90))
    for s in range(0, int(line.length) + 1, 500):
        d.line([(X(s), h - m), (X(s), h - m + 6)], fill=(90, 90, 90))
        d.text((X(s) - 12, h - m + 10), f'{s / 1000:.1f} km', fill=(90, 90, 90))
    if r['loop']:
        d.rectangle([X(r['loop'][0]), m, X(r['loop'][1]), h - m], fill=(255, 236, 200))
        d.text((X(r['loop'][0]), m - 16), 'passing loop', fill=(160, 100, 20))
    for spiral in line.spirals:
        d.rectangle([X(spiral['start']), m, X(spiral['end']), h - m], fill=(228, 226, 240))
        d.text((X(spiral['start']), m - 16), f"spiral tunnel, R {spiral['radius']:.0f} m", fill=(60, 60, 110))
    ground_pts = [(X(s), Y(z)) for s, z in zip(line.s, zg)]
    d.polygon(ground_pts + [(X(line.length), h - m), (X(0), h - m)], fill=(214, 204, 180))
    d.line(ground_pts, fill=(120, 100, 70), width=2)
    for name, i0, i1 in _runs(kind):
        pts = [(X(s), Y(z)) for s, z in zip(line.s[i0:i1 + 1], rail[i0:i1 + 1])]
        if len(pts) > 1:
            d.line(pts, fill=COLOURS[name], width=4)
    for i, name in enumerate(KINDS):
        d.rectangle([m + i * 160, 14, m + i * 160 + 20, 28], fill=COLOURS[name])
        d.text((m + i * 160 + 26, 15), name, fill=(40, 40, 40))
    d.text((w - 520, 15), f"Hidamari H2 -> Belmonte  {line.length:,.0f} m, grade limit {r['grade_limit'] * 100:.1f}%",
           fill=(40, 40, 40))
    img.save(path)


def draw_plan(path, r, raster, view_rows, spaces):
    from PIL import Image, ImageDraw
    from belmonte import layout as BM
    line, kind = r['line'], r['kind']
    x0, y0 = line.x.min() - 1700, line.y.min() - 500
    x1, y1 = line.x.max() + 1000, line.y.max() + 900
    px = .3
    W, H = int((x1 - x0) * px), int((y1 - y0) * px)
    P = lambda x, y: ((x - x0) * px, (y1 - y) * px)                       # noqa: E731
    xs = x0 + (np.arange(W) + .5) / px
    ys = y1 - (np.arange(H) + .5) / px
    gx, gy = np.meshgrid(xs, ys)
    z = raster(gx, gy)
    gyy, gxx = np.gradient(z, 1 / px)
    a, e = math.radians(315), math.radians(42)
    shade = np.clip((-gxx * math.cos(e) * math.sin(a) + gyy * math.cos(e) * math.cos(a) + math.sin(e))
                    / np.sqrt(gxx ** 2 + gyy ** 2 + 1), 0, 1)
    t = np.clip(z / 600, 0, 1)[..., None]
    land = (1 - t) * np.array([200, 205, 160]) + t * np.array([235, 230, 225])
    base = np.where((z < 0)[..., None], np.array([150, 185, 205]), land)
    rgb = (base * (.45 + .55 * shade[..., None])).clip(0, 255).astype(np.uint8)
    img = Image.fromarray(rgb, 'RGB')
    over = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    half = CELL / 2
    for space in spaces:
        tint = (255, 90, 190, 110) if space['kind'] == 'bare' else (150, 60, 220, 70)
        for cx, cy in space['cells']:
            d.rectangle([P(cx - half, cy + half), P(cx + half, cy - half)], fill=tint)
    img = Image.alpha_composite(img.convert('RGBA'), over)
    d = ImageDraw.Draw(img)
    for space in spaces[:25]:
        d.text(P(*space['centroid']), str(space['id']), fill=(150, 0, 90))
    v = volcano()
    rad = VOLCANO_CLEARANCE
    d.ellipse([P(v[0] - rad, v[1] + rad), P(v[0] + rad, v[1] - rad)], outline=(200, 40, 40), width=3)
    d.text(P(v[0] - 120, v[1]), 'volcano 1550 m', fill=(200, 40, 40))
    d.rectangle([P(300, 430), P(1320, -260)], outline=(80, 80, 80), width=2)
    d.text(P(310, 420), 'Hidamari', fill=(30, 30, 30))
    d.text(P(line.x.min(), line.y.min() - 150), f"{line.length:,.0f} m, {r['one_way'] / 60:.1f} min at up to "
           f"{MAX_SPEED * 3.6:.0f} km/h", fill=(0, 0, 0))
    d.rectangle([P(BM.BOUNDS[0], BM.BOUNDS[3]), P(BM.BOUNDS[2], BM.BOUNDS[1])], outline=(80, 80, 80), width=2)
    d.text(P(BM.BOUNDS[0] + 10, BM.BOUNDS[3] - 10), 'Belmonte', fill=(30, 30, 30))
    from belmonte import layout as BL
    d.line([P(*p) for p in BL.RAILWAY], fill=(120, 120, 120), width=1)
    for row in view_rows:
        cx, cy = row['xy']
        if 'big view' in row['flags']:
            d.ellipse([P(cx - 25, cy + 25), P(cx + 25, cy - 25)], outline=(255, 200, 0), width=2)
        if any(f.startswith('closed') for f in row['flags']):
            d.ellipse([P(cx - 12, cy + 12), P(cx + 12, cy - 12)], fill=(90, 90, 90))
    for name, i0, i1 in _runs(backdrop(line.x, line.y)):
        if name:
            d.line([P(x, y) for x, y in zip(line.x[i0:i1 + 1], line.y[i0:i1 + 1])], fill=(255, 255, 255), width=13)
    for name, i0, i1 in _runs(kind):
        pts = [P(x, y) for x, y in zip(line.x[i0:i1 + 1], line.y[i0:i1 + 1])]
        if len(pts) > 1:
            d.line(pts, fill=COLOURS[name], width=5)
    for spiral in line.spirals:
        info = spiral_report(line, r['rail'], r['zg'], spiral)
        if info['centre']:
            cx, cy = info['centre']
            rad = spiral['radius'] + 25
            d.ellipse([P(cx - rad, cy + rad), P(cx + rad, cy - rad)], outline=(60, 60, 110), width=2)
            d.text(P(cx + rad + 10, cy), f"spiral tunnel: {abs(spiral['turns'])} turn, R {spiral['radius']:.0f} m, "
                   f"+{info['height_gained']:.0f} m", fill=(30, 30, 90))
    if r.get('loop_track') is not None:
        d.line([P(x, y) for _, x, y in r['loop_track']], fill=(255, 140, 0), width=3)
    for station in (HIDAMARI, BELMONTE):
        c, u = np.array(station.centre), station.axis
        n = np.array([-u[1], u[0]])
        L, Wd = station.reserve
        corners = [c + u * L / 2 + n * Wd / 2, c - u * L / 2 + n * Wd / 2, c - u * L / 2 - n * Wd / 2, c + u * L / 2 - n * Wd / 2]
        d.polygon([P(*p) for p in corners], outline=(0, 0, 0), fill=(255, 255, 255))
        d.text(P(c[0] + 60, c[1] + 40), station.name, fill=(0, 0, 0))
    for i, name in enumerate(KINDS):
        d.rectangle([10, 10 + i * 18, 30, 24 + i * 18], fill=COLOURS[name])
        d.text((36, 11 + i * 18), name, fill=(0, 0, 0))
    d.text((10, 10 + 5 * 18), 'orange: passing loop; yellow rings: big views; grey dots: closed; '
           'pink: bare and violet: woodland-only ground seen; white halo: on far-hills backdrop (to be built)',
           fill=(0, 0, 0))
    img.convert('RGB').save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(yori.OUT / 'belmonte-train' / 'route'))
    ap.add_argument('--optimise', action='store_true')
    args = ap.parse_args()
    out = _Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print('ground raster', RASTER_BOUNDS, flush=True)
    raster = Raster(RASTER_BOUNDS, GRID, out / 'ground-20m.npz')
    if args.optimise:
        optimise(raster)
        return
    print('profile', flush=True)
    r = study()
    line, rail, zg, kind = r['line'], r['rail'], r['zg'], r['kind']
    side = 1. if r['loop'] and float(np.interp(sum(r['loop']) / 2, line.s, line.curvature)) <= 0 else -1.
    r['loop_track'] = loop_track(line, r['loop'], side) if r['loop'] else None
    if r['loop_track'] is not None:
        # keep the second track on the side away from the volcano
        lt = r['loop_track']
        if volcano_distance(lt[:, 1], lt[:, 2]).min() < volcano_distance(*line.at(lt[:, 0])[:2]).min():
            r['loop_track'] = loop_track(line, r['loop'], -side)
    print('views', flush=True)
    built, plants, trees, boxes = content_points()
    rows, seen = views(line, rail, kind, raster, trees)
    spaces = empty_spaces(line, seen, raster, built, plants, boxes)
    s_run, t_run, v_run = r['run']
    report = summary(r)
    report['structures'] = structures(line, rail, zg, kind)
    report['hidamari_clearance'] = hidamari_clearance(line)
    report['belmonte_clearance'] = belmonte_clearance(line)
    report['alternatives_costed'] = {f'profile without loop at {g * 100:.1f}%': (round(c) if math.isfinite(c) else 'infeasible')
                                     for g, c in r['plain_costs'].items()}
    print('alternatives', flush=True)
    options, infeasible = [('recommended', r)], []

    def alternative(name, points=None, grade=None):
        try:
            options.append((name, study(points, grade=grade)))
        except InfeasibleRoute as error:
            infeasible.append(dict(name=name, feasible=False, reason=str(error)))

    alternative(f'same line at {OPTION_GRADE * 100:.1f}%', grade=OPTION_GRADE)
    global MIN_RADIUS
    for name, values in ALTERNATIVES.items():
        kept, MIN_RADIUS = MIN_RADIUS, values['min_radius']
        try:
            points = tangent_points(values['first'], values['pis'], values['last'])
            alternative(name, points, values['grade'])
        finally:
            MIN_RADIUS = kept
    report['alternatives'] = [dict(name=name, **brief(summary(option))) for name, option in options] + infeasible
    grade = np.r_[np.diff(rail) / np.diff(line.s), 0.]
    data = {'version': 1, 'frame': 'Blender metres, x east, y north, z up; bearings counter-clockwise from east',
            'stations': {st.name: {'centre': list(st.centre), 'bearing': st.bearing, 'platform': st.platform,
                                   'reserve': list(st.reserve),
                                   **({'side': 'r', 'top_above_rail_m': .25 - station_yard.RAIL}
                                      if st == HIDAMARI else {})} for st in (HIDAMARI, BELMONTE)},
            'tangent_points': [[round(float(a), 2), round(float(b), 2)] for a, b in line.points],
            'curves': [{'deflection_deg': round(math.degrees(c[0]), 2), 'radius': round(c[1], 1), 'spiral': round(c[2], 1)}
                       for c in line.curves],
            'summary': report,
            'samples': [{'s': round(float(s), 2), 'x': round(float(x), 2), 'y': round(float(y), 2),
                         'rail_z': round(float(z), 3), 'ground_z': round(float(g), 3), 'class': str(k),
                         'curvature': round(float(c), 6), 'grade': round(float(gr), 5), 'spiral': bool(sp)}
                        for s, x, y, z, g, k, c, gr, sp in zip(line.s, line.x, line.y, rail, zg, kind, line.curvature, grade,
                                                               line.spiral_mask())],
            'passing_loop': None if r['loop'] is None else {
                'start': r['loop'][0], 'end': r['loop'][1], 'turnout': TURNOUT, 'spacing': TRACK_SPACING,
                'second_track': [[round(float(a), 1), round(float(b), 2), round(float(c), 2)] for a, b, c in r['loop_track']]},
            'speed_profile': [[round(float(s), 1), round(float(t), 1), round(float(v) * 3.6, 1)]
                              for s, t, v in zip(s_run[::10], t_run[::10], v_run[::10])],
            'speed_profile_down': [[round(float(s), 1), round(float(t), 1), round(float(v) * 3.6, 1)]
                                   for s, t, v in zip(*(part[::10] for part in r['run_down']))],
            'speed_profiles_note': '[head chainage m, seconds since departure, km/h]; speed_profile runs Hidamari to '
                                   'Belmonte, speed_profile_down Belmonte to Hidamari',
            'posted_limits': [{'start': round(a, 1), 'end': round(b, 1), 'kmh': round(v * 3.6),
                               'radius': round(radius), 'what': 'spiral tunnel' if line.spiral_mask([(a + b) / 2])[0]
                               else 'curve'} for a, b, v, radius in posted_limits(line)],
            'views': {'eye_height': EYE, 'rays': '10-degree rays (reach per ray); coverage uses 1-degree rays',
                      'points': rows,
                      'big_view_stretches': stretches(rows, lambda row: 'big view' in row['flags']),
                      'closed_stretches': stretches(rows, lambda row: any(f.startswith('closed') for f in row['flags']))},
            'empty_spaces': {'cell': CELL, 'range': EMPTY_RANGE, 'sites': spaces}}
    (out / 'route.json').write_text(json.dumps(data, indent=1))
    from train import corridor                  # the cut, fill and portal footprints for the terrain builders
    corridor.write_terrain_mask(data, out / 'terrain_mask.json')
    draw_profile(out / 'profile.png', r)
    draw_plan(out / 'plan.png', r, raster, rows, spaces)
    print(json.dumps(report, indent=1))
    print('wrote', out)


if __name__ == '__main__':
    main()
