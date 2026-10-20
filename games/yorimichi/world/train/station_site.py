"""The Belmonte station's site (plain Python, numpy only): its footprint, levels, forecourt and access road, in
the frame of the line's Belmonte end. Read by the earthworks (the ground the station stands on) and the corridor (no plants
on it). Nothing here applies to a line that does not end at the site (for_line): the committed riverside terminus keeps
its ground and planting unchanged.

Station frame: origin at the end of the line (route.json's last sample, rail top), `a` metres along the track towards
the buffer stop and beyond (the facade side), `u` metres to the left of a train arriving, z up from the rail top.
The buffer stop stands at a = -track.BUFFER_OFFSET.

The rail reaches Belmonte 8.6 m under the road from the south-east gate (route v4, Paul 2026-10-17), so the station
stands in a shallow cutting: platforms and the concourse at platform level, the headhouse's vestibule, the forecourt and
the access road at street level (STREET over the rail), with a grand staircase between them inside the headhouse.
"""
import math

import numpy as np

# Paul, 2026-10-18: the train will grow 15 % (today 131 m long, 3.60 m wide, 4.30 m tall); the station takes it.
TRAIN_SCALE = 1.15
TRAIN_LENGTH = 131. * TRAIN_SCALE           # 150.7 m; the head stops 10 m short of the buffer (route.STOP_CLEARANCE)
SHED_LENGTH = 175.          # the sheds cover the whole train with 14 m to spare
PLATFORM = 1.0              # platform top over the rail (the train service's arrival spot and boarding steps)
EDGE = round(1.80 * TRAIN_SCALE + .05, 2)   # 2.12: platform edges from a track's centre, clear of the scaled body
STREET = 7.2                # the vestibule, the forecourt and the access road's start over the rail (214.97 m)
FORMATION = -.85            # the ground under the track and the buildings (earthworks.FORMATION_DROP)
SIDING = -29.               # the decorative siding's centre (second shed)
# Rectangles (a0, a1, u0, u1) in the station frame.
SHEDS = (-SHED_LENGTH - 3., 0., -45., 15.5)             # the two train sheds, their outer walls and rear pavilions
HEADHOUSE = (0., 26., -55., 26.)            # the street building: wings, vestibule, gallery and stairs
FORECOURT = (26., 46., -57., 28.)           # the square in front of the facade, at street level
# The ground stays at street level this far beyond the forecourt's edges before its slopes start, so the carved terrain
# (refined along those edges, tools/belmonte_station_terrain.py) steps outside the paving and never rises through it.
FORECOURT_HOLD = 1.5
# The vestibule and the wings' street end: solid to street level in station.py, so the ground under them stands at
# street level (UNDERFLOOR under their floor) and meets the street flush along the whole facade; the stair hall behind
# them (a < VESTIBULE[0]) goes down to the formation.
VESTIBULE = (18., HEADHOUSE[1], HEADHOUSE[2], HEADHOUSE[3])
UNDERFLOOR = .02
AXIS_U = -14.5                              # the building's axis of symmetry (the clock tower)
WALL_SLOPE = .05            # horizontal per vertical: the ground stands against the station's walls
# The access road: from the forecourt's front edge on the axis north to the road from the north gate to the Trois Pres
# estate (its low point), world metres (x, y) after the first point. It leaves the front edge at a slant, so it stays
# at street level for its first ACCESS_FLAT metres (clear of the forecourt and its level ground), then rises evenly to
# ACCESS_END_Z, the road's ground there. 86 m, then about 2.3 %, 7 m wide.
ACCESS = [(797., 4816.)]
ACCESS_END_Z = 216.8
ACCESS_FLAT = 8.
ACCESS_HALF = 4.5           # the 7 m road and its shoulders
ROAD_CLEAR = 3.             # plants keep this far off the footprint and the access road
# The road from the south-east gate to the Dunes Basses estate crosses the cutting 229 m before the buffer stop on a
# straight stone deck (overbridge.py). The structure is regular and the ground is made to fit it (earthworks.carve):
# - the deck's road surface is one plane, level across and climbing `grade` along the road (deck_z at xy), and the road
#   is graded onto that plane for ROAD_FLAT beyond the deck's ends, then eased back to its own ground over ROAD_RAMP;
# - retaining walls stand `wall_half` either side of the track, from a0 to a1 along the line (metres from the
#   crossing, towards the buffer stop), from the road's side to just past the deck's abutments; their copings run
#   straight, COPING_DROP under the deck's plane along the walls (so the road's level carries on along them), and the
#   ground behind a wall is graded flush with its coping. A return wall square to the line closes each end, the
#   cutting opening into its ordinary slopes beyond it.
OVERBRIDGE = dict(xy=(999.0, 4542.0), road_bearing=17.5, deck_z=216.75, grade=.112, wall_half=5.0,
                  walls={-1: (-20., 7.5), 1: (-7.5, 20.)})
WALL_THICK = 1.2            # the retaining and return walls' thickness
DECK_HALF = 4.6             # half the deck's width: 8.2 m of road between the parapets, and them
DECK_REACH = 2.5            # the deck's nearest corner stands this far beyond a wall's outer face
ROAD_HALF = 4.6             # the road graded onto the deck's plane: its half width ...
ROAD_SHOULDER = 3.          # ... easing to the ground beside it over this
ROAD_FLAT = 6.              # metres beyond the deck's ends on the plane
ROAD_RAMP = 50.             # metres over which the road eases back to its own ground (at most 12.5 % on the way)
COPING_DROP = .25           # the ground behind the walls under the deck's plane (their copings stand .1 over it)
ROAD_TUCK = .3              # the road's ground under the deck stays this far under its surface
BRIDGE_FLAT = 1.5           # the ground behind a wall stays flush with its coping this far beyond the return walls ...
BRIDGE_TRANS = 8.           # ... then eases back to the earthworks' own over this many metres across the line
BRIDGE_HOLD = 2.5           # beyond a wall's end the cutting keeps the faces opening from the wall's line this far ...
BRIDGE_FADE = 8.            # ... then eases into its ordinary slopes over this many metres
STATION_REACH = 40.         # the station's slopes reach no further than this beyond its zones
VALLEY_LEAD = 15.           # metres of the line carved in Belmonte's valley tiles before its final cutting starts
SOIL_DEPTH = 4.0            # a cutting's face turns to rock above this height over the formation
SOIL_RATIO = 1.2            # soil slope horizontal per vertical around the station and overbridge
ROCK_ROOF_RATIO = .8        # rock slope horizontal per vertical around the station
BRIDGE_SLOPES = (1.2, .45)  # the cutting's faces beyond the return walls: soil, then rock


def _smooth(t):
    t = np.clip(t, 0., 1.)
    return t * t * (3. - 2. * t)


def _rise(e, ratio, rock_ratio):
    soil = e / ratio
    rock = SOIL_DEPTH + (e - SOIL_DEPTH * ratio) / rock_ratio
    return np.where(soil < SOIL_DEPTH, soil, rock)


class Site:
    """The station frame at the end of a line given as samples (x, y, rail z), and its zones in world metres."""

    def __init__(self, xy, rail):
        xy = np.asarray(xy, float)
        self.origin = xy[-1]
        d = xy[-1] - xy[-2]
        self.t = d / np.hypot(*d)                       # along the track, towards the buffer stop
        self.n = np.array([-self.t[1], self.t[0]])      # left of an arriving train
        self.rail = float(rail[-1])
        self.heading = math.atan2(self.t[1], self.t[0])

    def world(self, a, u):
        a, u = np.asarray(a, float), np.asarray(u, float)
        return self.origin + a[..., None] * self.t + u[..., None] * self.n

    def local(self, x, y):
        d = np.stack([np.asarray(x, float) - self.origin[0], np.asarray(y, float) - self.origin[1]], -1)
        return d @ self.t, d @ self.n

    def access(self):
        """The access road's centre line (world x, y) and its heights at its ends."""
        start = self.world(FORECOURT[1], AXIS_U)
        pts = np.array([start, *ACCESS], float)
        return pts, (self.rail + STREET, ACCESS_END_Z)

    def access_z(self, t):
        """The access road's height at t (0..1 along it): level for ACCESS_FLAT metres, then rising evenly."""
        pts, (z0, z1) = self.access()
        total = float(np.hypot(*np.diff(pts, axis=0).T).sum())
        s = np.asarray(t, float) * total
        return z0 + (z1 - z0) * np.clip((s - ACCESS_FLAT) / (total - ACCESS_FLAT), 0., 1.)

    def zones(self):
        """(rectangle, floor height) of the ground the station stands on: the sheds and the stair hall at the
        formation (their walls retain the street), the vestibule and the forecourt at street level."""
        hall = (HEADHOUSE[0], VESTIBULE[0], HEADHOUSE[2], HEADHOUSE[3])
        return [(SHEDS, self.rail + FORMATION), (hall, self.rail + FORMATION),
                (VESTIBULE, self.rail + STREET - UNDERFLOOR), (FORECOURT, self.rail + STREET)]


def for_line(xy, rail):
    """@cc [owner:fontanierh,label:correctness] station-site-gate
    A line that does not end at Belmonte's station site MUST get None, so its
    earthworks, corridor and carved terrain stay exactly as without the station.
    Otherwise the station's Site at the end of the line given by its last samples.
    """
    xy = np.asarray(xy, float)
    rail = np.asarray(rail, float)
    if xy.ndim != 2 or xy.shape[0] < 2 or xy.shape[1] != 2 or rail.size < 1:
        return None
    if not (np.isfinite(xy[-2:]).all() and np.isfinite(rail[-1])):
        return None
    if np.hypot(*(xy[-1] - xy[-2])) < 1e-6:
        return None
    if np.hypot(*(xy[-1] - np.asarray(OVERBRIDGE['xy']))) > 300.:
        return None
    return Site(xy, rail)


def rect_excess(a, u, rect):
    """Metres outside the rectangle (0 inside)."""
    a0, a1, u0, u1 = rect
    da = np.maximum(np.maximum(a0 - a, a - a1), 0.)
    du = np.maximum(np.maximum(u0 - u, u - u1), 0.)
    return np.hypot(da, du)


def polyline_excess(x, y, pts, half):
    """(metres beyond `half` of the polyline's centre, position along it 0..1) for points x, y."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    best, along = np.full(x.shape, np.inf), np.zeros(x.shape)
    lengths = np.hypot(*np.diff(pts, axis=0).T)
    total, start = lengths.sum(), 0.
    for (ax, ay), (bx, by), length in zip(pts[:-1], pts[1:], lengths):
        dx, dy = bx - ax, by - ay
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / max(length * length, 1e-9), 0., 1.)
        d = np.hypot(x - ax - t * dx, y - ay - t * dy)
        better = d < best
        best = np.where(better, d, best)
        along = np.where(better, (start + t * length) / total, along)
        start += length
    return np.maximum(best - half, 0.), along


def inside(site, x, y, margin=0.):
    """True on the footprint, forecourt and access road (plus `margin`)."""
    return excess(site, x, y) <= margin


def excess(site, x, y):
    """Metres beyond the station's ground (0 on it): the sheds, the headhouse, the forecourt and the access road."""
    a, u = site.local(x, y)
    pts, _ = site.access()
    return np.minimum(np.min([rect_excess(a, u, rect) for rect, _ in site.zones()], axis=0),
                      polyline_excess(x, y, pts, ACCESS_HALF)[0])


class Bridge:
    """The overbridge's frame (OVERBRIDGE) at the rail point `origin` (x, y) where the road crosses the line, `t` the
    line's direction there (towards the buffer stop) and rail(a) the rail's height a metres along it: a along the
    line, u left of it (n); d along the road from OVERBRIDGE['xy'], w left of it."""

    def __init__(self, origin, t, rail):
        self.origin = np.asarray(origin, float)[:2]
        self.t = np.asarray(t, float)[:2] / np.hypot(*np.asarray(t, float)[:2])
        self.n = np.array([-self.t[1], self.t[0]])
        self.rail = rail
        b = math.radians(OVERBRIDGE['road_bearing'])
        self.road = np.array([math.cos(b), math.sin(b)])
        self.side = np.array([-self.road[1], self.road[0]])
        self.xy = np.asarray(OVERBRIDGE['xy'], float)
        self.wall_half = OVERBRIDGE['wall_half']
        self.outer = self.wall_half + WALL_THICK
        self.rn, self.sn = float(self.road @ self.n), float(self.side @ self.n)
        # the deck: centred on the line, square to the road, its nearest corner DECK_REACH beyond the walls
        self.dc = float(-(self.xy - self.origin) @ self.n / self.rn)
        self.half = (self.outer + DECK_REACH + DECK_HALF * abs(self.sn)) / abs(self.rn)

    def local(self, x, y):
        """(a, u) of world points."""
        q = np.stack([np.asarray(x, float) - self.origin[0], np.asarray(y, float) - self.origin[1]], -1)
        return q @ self.t, q @ self.n

    def world(self, a, u):
        a, u = np.asarray(a, float), np.asarray(u, float)
        return self.origin + a[..., None] * self.t + u[..., None] * self.n

    def road_dw(self, x, y):
        """(d, w) of world points."""
        q = np.stack([np.asarray(x, float) - self.xy[0], np.asarray(y, float) - self.xy[1]], -1)
        return q @ self.road, q @ self.side

    def road_xy(self, d, w):
        d, w = np.asarray(d, float), np.asarray(w, float)
        return self.xy + d[..., None] * self.road + w[..., None] * self.side

    def plane(self, d):
        """The deck's road surface (absolute z) at d along the road."""
        return OVERBRIDGE['deck_z'] + OVERBRIDGE['grade'] * np.asarray(d, float)

    def ends(self):
        """d of the deck's two ends."""
        return self.dc - self.half, self.dc + self.half

    def wall(self, sign):
        """(a0, a1) of the retaining wall on the side `sign` of the line."""
        return OVERBRIDGE['walls'][int(sign)][:2]

    def coping(self, sign, a):
        """The ground behind the wall on the side `sign` (absolute z), held at its ends: COPING_DROP under the deck's
        plane along the wall's middle, a straight line."""
        a0, a1 = self.wall(sign)
        a = np.clip(np.asarray(a, float), a0, a1)
        d, _ = self.road_dw(*np.moveaxis(self.world(a, np.full(np.shape(a), sign * (self.wall_half + self.outer) / 2)),
                                         -1, 0))
        return self.plane(d) - COPING_DROP


def valley_carve_start(ln, rows):
    """The chainage from which Belmonte's valley tiles are carved (world/regions/belmonte/terrain.py) on a
    line ending at the station's site: its final cutting, from VALLEY_LEAD before it. None for any other line."""
    if ln is None or ln.station() is None:
        return None
    start = ln.length
    for r in reversed(rows):
        if r['class'] == 'embankment':
            break
        start = r['s']
    return start - VALLEY_LEAD


def station(x, y, ln):
    """(upper, lower, floor) the Belmonte station asks of the ground at points x, y (flat arrays): +inf/-inf/NaN where
    it asks nothing. Sheds and stair hall: the formation, straight walls at their edges; the vestibule: just under
    street level, also with straight walls; forecourt and access road: street level (FORECOURT_HOLD beyond the
    forecourt's edges too) and the access road's run up to its junction, soil slopes beyond."""
    up, lo, floor = np.full(len(x), np.inf), np.full(len(x), -np.inf), np.full(len(x), np.nan)
    site = ln.station()
    if site is None or not len(x):
        return up, lo, floor
    a, u = site.local(x, y)
    for rect, z in site.zones():
        e = rect_excess(a, u, rect)
        near = e < STATION_REACH
        if not near.any():
            continue
        steep = rect is not FORECOURT
        if not steep:           # level ground around the paving before the slopes
            e = np.maximum(e - FORECOURT_HOLD, 0.)
        ratio = WALL_SLOPE if steep else SOIL_RATIO
        up = np.where(near, np.minimum(up, z + (e / ratio if steep else _rise(e, ratio, ROCK_ROOF_RATIO))), up)
        lo = np.where(near, np.maximum(lo, z - e / ratio), lo)
        floor = np.where(e <= 0., z, floor)
    pts, _ = site.access()
    e, t = polyline_excess(x, y, pts, ACCESS_HALF)
    near = e < STATION_REACH
    z = site.access_z(t)
    road_lo = z - e / SOIL_RATIO
    up = np.where(near, np.minimum(up, z + _rise(e, SOIL_RATIO, ROCK_ROOF_RATIO)), up)
    # beyond the level ground around the forecourt (FORECOURT_HOLD) the road's rising floor and its fill slopes win
    beyond = _smooth(rect_excess(a, u, FORECOURT) - FORECOURT_HOLD)
    up = np.where(near, up + beyond * np.maximum(road_lo - up, 0.), up)
    lo = np.where(near, np.maximum(lo, road_lo), lo)
    floor = np.where(e <= 0., z, floor)
    return up, lo, floor


def return_reach(k, sign, a):
    """|u| where the cutting's face beyond the wall's end at a (a0 or a1) reaches the coping: the return wall's
    length out from the line."""
    h = float(k.coping(sign, a) - (k.rail(a) + FORMATION))
    ratio, rock = BRIDGE_SLOPES
    e = h * ratio if h < SOIL_DEPTH else SOIL_DEPTH * ratio + (h - SOIL_DEPTH) * rock
    return k.wall_half + max(e, 0.)


def bridge_ground(x, y, z, floor, k):
    """The ground z (flat arrays) at the overbridge (k: Bridge): between the retaining walls the
    formation; behind them flush with their copings; beyond their ends the cutting's faces opening from the walls'
    line, up to the copings; the road on the deck's plane. Each eases back to z beyond. Where the ground steps at a
    wall it does so within the wall's thickness. Near the walls the result does not depend on z."""
    z = np.asarray(z, float).copy()
    a, u = k.local(x, y)
    au = np.abs(u)
    floor = np.where(np.isfinite(floor), floor, k.rail(a) + FORMATION)
    mid = WALL_THICK / 2
    for sign in (-1., 1.):
        a0, a1 = k.wall(sign)
        top = k.coping(sign, a)
        along = (a >= a0 + mid) & (a <= a1 - mid)
        between = floor + np.maximum(au - k.wall_half - .4, 0.) / WALL_SLOPE
        face = floor + _rise(np.maximum(au - k.wall_half, 0.), *BRIDGE_SLOPES)
        target = np.minimum(top, np.where(along, between, face))
        reach = max(return_reach(k, sign, a0), return_reach(k, sign, a1)) + BRIDGE_FLAT
        out = np.maximum(np.maximum(a0 - a, a - a1) - BRIDGE_HOLD, 0.)
        w = _smooth((BRIDGE_FADE - out) / BRIDGE_FADE)
        w = w * _smooth((reach + BRIDGE_TRANS - au) / BRIDGE_TRANS) * (u * sign >= 0)
        z = w * target + (1 - w) * z
    d, wr = k.road_dw(x, y)
    lo, hi = k.ends()
    beyond = np.maximum(np.maximum(lo - d, d - hi) - ROAD_FLAT, 0.)
    # the road on the plane; its shoulders ease to the ground beside it, and off the walls' copings beside the deck
    shoulder = _smooth((ROAD_HALF + ROAD_SHOULDER - np.abs(wr)) / ROAD_SHOULDER) * \
        _smooth((au - k.outer - .1) / 2.2)
    w = _smooth((ROAD_RAMP - beyond) / ROAD_RAMP) * np.where(np.abs(wr) <= ROAD_HALF, 1., shoulder)
    w = w * _smooth((au - k.wall_half - .4) / .4)     # never into the cutting: it steps within the walls
    tuck = ROAD_TUCK * _smooth(np.minimum(d - lo, hi - d) / 2.)    # under the deck, inside its stone
    return w * (k.plane(d) - tuck) + (1 - w) * z


def bridge_walls(x, y, k, margin=1.):
    """True near the overbridge's walls (within `margin` of their footprints): where the ground steps."""
    a, u = k.local(x, y)
    near = np.zeros(np.shape(a), bool)
    for sign in (-1., 1.):
        a0, a1 = k.wall(sign)
        su = sign * u
        near |= (a >= a0 - margin) & (a <= a1 + margin) & (su >= k.wall_half - margin) & (su <= k.outer + margin)
        for end, inward in ((a0, 1.), (a1, -1.)):
            lo, hi = sorted((end - inward * margin, end + inward * (WALL_THICK + margin)))
            near |= (a >= lo) & (a <= hi) & (su >= k.wall_half - margin) & (su <= return_reach(k, sign, end) + margin)
    return near
