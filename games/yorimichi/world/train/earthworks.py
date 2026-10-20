"""The railway's earthworks (plain Python): the ground every terrain builder gives way to along the Belmonte line.

One designed surface, from the line's geometry alone (corridor.py's line.json: chainage, plan, rail height and class
every 10 m, the passing loop). Every terrain that the line crosses is carved to it by one guarded call in its
builder, so the Hidamari foothills, the far hills, Belmonte's apron and country all meet the line the same way:

- cuttings: the ground lowered to the formation (FORMATION_DROP under the rail top) across the formation, then soil
  slopes up to the natural ground at 1:1.2-1:2 (RATIO, varying slowly along the line and side to side). Above
  SOIL_DEPTH the face turns to rock and stands steeper (ROCK_RATIO), so deep cuttings read as rock cuts rather than
  100 m wide scars;
- embankments: the ground raised to the formation, grass slopes down at the same soil ratios;
- crest and toe rounded (ROUND), the faces' edges wandering with low-frequency noise (FACE_NOISE);
- tunnels: the cutting runs up to the portal face and stands back steeply above it (BACK_RATIO); over the tunnel the
  ground keeps at least HOOD over the rail within HOOD_HALF, so no thin hill shows the lining. A hole is left in the
  terrain across the mouth (HOLE): the portal mesh (track.py) closes it;
- viaducts and the line's ends: untouched under the deck; the fill or cut ends in a cone (END_RATIO);
- the Belmonte station (station_site.py): the ground under its sheds and stair hall at the formation, standing
  straight against their walls; under the vestibule just under street level, flush with the forecourt and the access
  road at street level along the facade, with ordinary soil slopes beyond; under the road's overbridge the cutting
  stands between retaining walls, so the road keeps its ground either side. Only for a line ending at the site.

Terrains are carved by `refine` (triangle soups: subdivides the triangles that the earthworks touch to `step` metres,
carves them and drops the portal holes) or `carve` (heights on a grid). Both return the terrain unchanged when
RAILWAY_EARTHWORKS=0 is set in the environment or the line has not been built.

`paint` gives the carved ground its colours (rock faces, grass slopes, the cess's ballast dust) for terrains with
vertex colours. Frame: route.json's (metres, x east, y north, z up).
"""
import json
import math
from functools import lru_cache

import numpy as np

from train import corridor as C
from train import station_site as SS

FORMATION_DROP = .85        # terrain at the formation under the rail top: ballast toe (.70) and a .15 m tuck
FLOOR_HALF = 3.0            # flat formation either side of the centre (the ballast's skirt, 2.6, stays buried)
ROUND = 2.0                 # metres over which the toe and the crest round off
RATIO = (1.2, 2.0)          # soil slopes, horizontal per vertical: varying along the line
RATIO_WAVE = 260.           # metres: how slowly the ratio varies
SOIL_DEPTH = 4.0            # a cutting's face turns to rock above this height over the formation
ROCK_RATIO = (.45, .8)      # rock faces, horizontal per vertical
FACE_NOISE = (1.6, 22., .5, 7.)   # lateral wander of the faces: metres at a 22 m wavelength, metres at 7 m
BACK_RATIO = .35            # the face over a portal
HOOD = 8.6                  # ground over the rail at a portal (the face wall stands 9 m) and over every tunnel
HOOD_HALF = 7.              # ... within this half width, falling 1:1 beyond
HOLE = (6.4, -1.2, 2.2)     # the hole at a portal: half width, from (outside, metres along) to (inside)
END_RATIO = 1.5             # cones where a fill or cut ends at a viaduct or the line's end
REACH = 120.                # nothing is carved further than this from the centre line
SEAM_FADE = 20.             # a terrain sharing a seam with ground that is not carved (Belmonte's valley) eases its
                            # carving to nothing over this many metres from the seam, so the seam stays closed
CUT = ('cutting', 'deep cutting', 'embankment')


def _smooth(t):
    t = np.clip(t, 0., 1.)
    return t * t * (3. - 2. * t)


def _noise(x, y, scale, seed):
    """Deterministic value noise in -1..1 (the foothills' own, hidamari/mountains.py)."""
    x, y = np.asarray(x) / scale, np.asarray(y) / scale
    ix, iy = np.floor(x), np.floor(y)
    u, v = _smooth(x - ix), _smooth(y - iy)

    def h(a, b):
        q = np.sin(a * 127.1 + b * 311.7 + seed * 73.9) * 43758.5453
        return (q - np.floor(q)) * 2 - 1
    return (h(ix, iy) * (1 - u) + h(ix + 1, iy) * u) * (1 - v) + (h(ix, iy + 1) * (1 - u) + h(ix + 1, iy + 1) * u) * v


def _wave(s, seed):
    """A slow 0..1 wave along the line."""
    s = np.asarray(s, float) / RATIO_WAVE
    return .5 + .32 * np.sin(s * 1.7 + seed) + .18 * np.sin(s * 4.3 + 2.1 * seed)


def smin(a, b, r):
    h = np.clip(.5 + .5 * (b - a) / r, 0., 1.)
    return b + (a - b) * h - r * h * (1. - h)


def smax(a, b, r):
    return -smin(-a, -b, r)


class Line:
    """The line's centre as segments, with what the earthworks need at each chainage."""

    def __init__(self, data):
        rows = data['samples']
        self.s = np.array([r['s'] for r in rows], float)
        self.xy = np.array([[r['x'], r['y']] for r in rows], float)
        self.rail = np.array([r['rail_z'] for r in rows], float)
        kind = [r['class'] for r in rows]
        self.length = float(self.s[-1])
        # Structures run between sample midpoints (route.py's summary), unless line.json gives them.
        given = data.get('structures')
        if given:
            self.tunnels = [(t['start'], t['end']) for t in given if t['kind'] == 'tunnel']
            self.viaducts = [(t['start'], t['end']) for t in given if t['kind'] == 'viaduct']
        else:
            self.tunnels, self.viaducts = self._runs(kind, 'tunnel'), self._runs(kind, 'viaduct')
        loop = data.get('passing_loop') or {}
        self.loop = None
        if loop.get('second_track'):
            t = np.asarray(loop['second_track'], float)
            x, y = np.interp(t[:, 0], self.s, self.xy[:, 0]), np.interp(t[:, 0], self.s, self.xy[:, 1])
            tx, ty = self.tangent(t[:, 0])
            offset = (t[:, 1] - x) * -ty + (t[:, 2] - y) * tx       # to the left of the main line
            self.loop = (t[:, 0], offset)

    def _runs(self, kind, name):
        runs, start = [], None
        for i, k in enumerate(kind + ['']):
            if k == name and start is None:
                start = 0. if i == 0 else (self.s[i - 1] + self.s[i]) / 2
            if k != name and start is not None:
                runs.append((start, self.length if i == len(kind) else (self.s[i - 1] + self.s[i]) / 2))
                start = None
        return runs

    def tangent(self, s):
        s = np.asarray(s, float)
        dx = np.gradient(self.xy[:, 0], self.s)
        dy = np.gradient(self.xy[:, 1], self.s)
        tx, ty = np.interp(s, self.s, dx), np.interp(s, self.s, dy)
        n = np.hypot(tx, ty)
        return tx / n, ty / n

    def project(self, x, y):
        """(s, u, d): chainage of the nearest centre point (clamped to the line), metres to its left, and the
        distance beyond the line's ends (0 along it), for points x, y; NaN beyond REACH."""
        x, y = np.asarray(x, float).ravel(), np.asarray(y, float).ravel()
        best = np.full(len(x), np.inf)
        s_out, u_out, d_out = np.full(len(x), np.nan), np.full(len(x), np.nan), np.zeros(len(x))
        a, b = self.xy[:-1], self.xy[1:]
        lo, hi = np.minimum(a, b) - REACH, np.maximum(a, b) + REACH
        last = len(a) - 1
        for k in range(len(a)):
            near = np.flatnonzero((x >= lo[k, 0]) & (x <= hi[k, 0]) & (y >= lo[k, 1]) & (y <= hi[k, 1]))
            if not len(near):
                continue
            px, py = x[near], y[near]
            dx, dy = b[k] - a[k]
            length2 = max(dx * dx + dy * dy, 1e-9)
            raw = ((px - a[k, 0]) * dx + (py - a[k, 1]) * dy) / length2
            t = np.clip(raw, 0. if k > 0 else -np.inf, 1. if k < last else np.inf)
            qx, qy = a[k, 0] + t * dx, a[k, 1] + t * dy
            dist = np.hypot(px - qx, py - qy)
            better = (dist < best[near]) & (dist <= REACH)
            if not better.any():
                continue
            idx = near[better]
            best[idx] = dist[better]
            seg = math.sqrt(length2)
            s_out[idx] = self.s[k] + t[better] * (self.s[k + 1] - self.s[k])
            u_out[idx] = ((px - qx) * -dy + (py - qy) * dx)[better] / seg
            beyond = np.where(t[better] < 0, -t[better], np.where(t[better] > 1, t[better] - 1, 0.)) * seg
            d_out[idx] = beyond
            # Beyond an end the point lies along the line, not across it: keep only its offset to the side.
        return s_out, u_out, d_out

    def inside(self, s, runs):
        """For chainages s: metres into the nearest of `runs` (negative outside it) and that run's nearer end."""
        depth = np.full(np.shape(s), -np.inf)
        end = np.full(np.shape(s), np.nan)
        for a, b in runs:
            into = np.minimum(s - a, b - s)
            nearer = np.where(s - a < b - s, a, b)
            better = into > depth
            depth = np.where(better, into, depth)
            end = np.where(better, nearer, end)
        return depth, end

    @lru_cache(maxsize=1)
    def station(self):
        """The Belmonte station's site at the line's end (station_site.Site)."""
        return SS.for_line(self.xy[-2:], self.rail[-2:])

    @lru_cache(maxsize=1)
    def overbridge(self):
        """The chainage where the road from the south-east gate crosses the line, or None if it does not."""
        if self.station() is None:
            return None
        s, u, beyond = self.project(*np.asarray(SS.OVERBRIDGE['xy'], float)[:, None])
        if not np.isfinite(s[0]) or abs(u[0]) > 5. or beyond[0] > 0:
            return None
        return float(s[0])

    @lru_cache(maxsize=1)
    def bridge(self):
        """The overbridge's frame (station_site.Bridge) at the crossing, or None."""
        s = self.overbridge()
        if s is None:
            return None
        origin = (np.interp(s, self.s, self.xy[:, 0]), np.interp(s, self.s, self.xy[:, 1]))
        return SS.Bridge(origin, self.tangent(s), lambda a: np.interp(s + np.asarray(a, float), self.s, self.rail))

    def floor_half(self, s, u):
        """The formation's flat half width at s on the side of u: wider on the loop's side."""
        half = np.full(np.shape(s), FLOOR_HALF)
        if self.loop is not None:
            off = np.interp(s, self.loop[0], self.loop[1], left=0., right=0.)
            half = half + np.where(np.sign(u) == np.sign(off), np.abs(off), 0.)
        return half


@lru_cache(maxsize=1)
def line():
    """The committed Belmonte railway line, or None if missing."""
    try:
        return Line(json.loads(C.LINE.read_text()))
    except (OSError, ValueError, KeyError):
        return None


def _excess(u, half):
    """Metres beyond the flat formation, rounded over ROUND at the toe (0 on the formation)."""
    e = np.maximum(np.abs(u) - half, 0.)
    return np.where(e < ROUND, e * e / (2 * ROUND), e - ROUND / 2)


def _rise(e, ratio, rock_ratio):
    """Height of a cutting's face e metres out from the formation: soil up to SOIL_DEPTH, rock above."""
    soil = e / ratio
    rock = SOIL_DEPTH + (e - SOIL_DEPTH * ratio) / rock_ratio
    return np.where(soil < SOIL_DEPTH, soil, rock)


def design(x, y, ln=None):
    """(upper, lower, info) at points x, y: the carved ground keeps between the lower and the upper bound (both NaN
    where the earthworks do not reach). info holds s, u, the formation height and the rock-face weight."""
    ln = ln or line()
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    shape = x.shape
    s, u, beyond = ln.project(x, y)
    upper, lower = np.full(s.shape, np.nan), np.full(s.shape, np.nan)
    info = dict(s=s, u=u, formation=np.full(s.shape, np.nan), hood=np.full(s.shape, -np.inf))
    ok = np.isfinite(s)
    if not ok.any():
        return upper.reshape(shape), lower.reshape(shape), info
    sx, ux, bx = s[ok], u[ok], beyond[ok]
    px, py = x.ravel()[ok], y.ravel()[ok]
    tun, tun_end = ln.inside(sx, ln.tunnels)
    via, via_end = ln.inside(sx, ln.viaducts)
    # In a tunnel the cutting's floor stays at its portal's height; in a viaduct at the abutment's.
    at = np.where(tun > 0, tun_end, np.where(via > 0, via_end, sx))
    rail = np.interp(at, ln.s, ln.rail)
    floor = rail - FORMATION_DROP
    side = np.sign(ux) + (ux == 0)
    ratio = RATIO[0] + (RATIO[1] - RATIO[0]) * _wave(sx, 1.3 + side)
    rock = ROCK_RATIO[0] + (ROCK_RATIO[1] - ROCK_RATIO[0]) * _wave(sx, 4.1 + side)
    a1, w1, a2, w2 = FACE_NOISE
    wander = a1 * _noise(px, py, w1, 11) + a2 * _noise(px, py, w2, 12)
    e = _excess(ux, ln.floor_half(sx, ux))
    e = np.maximum(e + wander * _smooth(e / 3.), 0.)
    ends = np.maximum(np.maximum(via, 0.), bx)          # metres into a viaduct or beyond the line's ends
    up = floor + _rise(e, ratio, rock) + ends / END_RATIO
    lo = floor - e / ratio - ends / END_RATIO
    # Into a tunnel: the face stands back steeply over the portal; no fill.
    into = np.maximum(tun, 0.)
    up = np.where(tun > 0, floor + _rise(e, ratio, rock) + into / BACK_RATIO, up)
    lo = np.where(tun > 0, -np.inf, lo)
    # Over every tunnel (and only there) the ground keeps HOOD over the rail near the line.
    hood = np.where(tun > 0, np.interp(sx, ln.s, ln.rail) + HOOD - np.maximum(np.abs(ux) - HOOD_HALF, 0.), -np.inf)
    upper[ok], lower[ok] = up, lo
    info['formation'][ok] = floor
    # The station's ground: wherever it asks for less (cut) or more (fill) than the line's own earthworks.
    if ln.station() is not None:
        st_up, st_lo, st_floor = SS.station(x.ravel(), y.ravel(), ln)
        reach = np.isfinite(st_up) | np.isfinite(st_lo)
        upper = np.where(reach, np.fmin(np.where(np.isnan(upper), np.inf, upper), st_up), upper)
        lower = np.where(reach, np.fmax(np.where(np.isnan(lower), -np.inf, lower), st_lo), lower)
        upper = np.where(np.isposinf(upper), np.nan, upper)
        lower = np.where(reach & np.isnan(lower), -np.inf, lower)
        info['formation'] = np.where(reach & ~np.isnan(st_floor), st_floor, info['formation'])
    info['hood'][ok] = hood
    info['tunnel'] = np.full(s.shape, -np.inf)
    info['tunnel'][ok] = tun
    info['rock_height'] = np.full(s.shape, np.nan)
    info['rock_height'][ok] = floor + SOIL_DEPTH
    return upper.reshape(shape), lower.reshape(shape), info


# Belmonte station and overbridge ground helpers live in station_site.py; re-exported for callers.
STATION_REACH = SS.STATION_REACH
VALLEY_LEAD = SS.VALLEY_LEAD
BRIDGE_SLOPES = SS.BRIDGE_SLOPES
valley_carve_start = SS.valley_carve_start
station = SS.station
return_reach = SS.return_reach
bridge_ground = SS.bridge_ground
bridge_walls = SS.bridge_walls


def carve(x, y, z, ln=None):
    """The ground z at x, y carved to the earthworks (unchanged where they do not reach)."""
    ln = ln or line()
    z = np.asarray(z, float)
    if ln is None:
        return z
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), z)
    up, lo, info = design(x, y, ln)
    out = z.astype(float).copy().ravel()
    up, lo = up.ravel(), lo.ravel()
    on = np.isfinite(up)
    if ln.station() is not None:
        on |= np.isfinite(lo)                       # the station may only ask for fill
    g = out[on]
    hi = np.where(np.isfinite(up[on]), up[on], 1e6)
    low = np.where(np.isfinite(lo[on]), lo[on], -1e6)
    r = ROUND
    # The crest and the toe round off over r; the formation itself (where both bounds meet) stays exact.
    f = np.clip(smax(smin(g, hi, r), low, r), low, hi)
    hood = info['hood'][on]
    f = np.where(np.isfinite(hood), np.maximum(f, hood), f)
    out[on] = f
    if ln.bridge() is not None:
        out = SS.bridge_ground(x.ravel(), y.ravel(), out, info['formation'].ravel(), ln.bridge())
    return out.reshape(z.shape)


def in_hole(x, y, z=None, ln=None):
    """True where a terrain triangle at x, y (its centroid) must be left open: across a tunnel's mouth."""
    ln = ln or line()
    x, y = np.asarray(x, float).ravel(), np.asarray(y, float).ravel()
    if ln is None or not ln.tunnels:
        return np.zeros(len(x), bool)
    s, u, _ = ln.project(x, y)
    out = np.zeros(len(x), bool)
    ok = np.isfinite(s)
    half, outside, inside = HOLE
    for a, b in ln.tunnels:
        for portal, sign in ((a, 1.), (b, -1.)):            # sign: into the tunnel
            if portal <= 0. or portal >= ln.length:
                continue
            along = (s - portal) * sign
            hit = ok & (np.abs(u) < half) & (along > outside) & (along < inside)
            if z is not None:
                hit &= np.asarray(z, float).ravel() < np.interp(portal, ln.s, ln.rail) + HOOD + 1.
            out |= hit
    return out


def weights(x, y, z, z0, ln=None):
    """(rock, cess, fill) weights 0..1 of the carved ground z (natural z0) at x, y, for the terrains' colours."""
    ln = ln or line()
    x, y, z, z0 = (np.asarray(v, float).ravel() for v in (x, y, z, z0))
    zero = np.zeros(len(x))
    if ln is None:
        return zero, zero, zero
    _, _, info = design(x, y, ln)
    cut = _smooth((z0 - z) / .6)
    fill = _smooth((z - z0) / .6)
    over = z - np.nan_to_num(info['formation'], nan=-1e9)
    rock = cut * _smooth((over - SOIL_DEPTH + .6) / 1.2) * _smooth((-info['tunnel'] + 1.) / 1.)
    rock = np.maximum(rock, cut * (info['tunnel'] > 0))
    cess = np.maximum(cut, fill) * _smooth((FLOOR_HALF + 1.5 - np.abs(np.nan_to_num(info['u'], nan=1e9))) / 1.5)
    return np.nan_to_num(rock), np.nan_to_num(cess), np.nan_to_num(fill)


ROCK = np.array([.30, .27, .23])      # linear RGB: weathered sandstone
CESS = np.array([.20, .18, .15])      # ballast dust on the formation's shoulders
GRASS = np.array([.10, .14, .045])    # fresh grass on the new slopes


def paint(colours, x, y, z, z0, ln=None):
    """Colours (N, 3+) of the carved ground: rock faces, the cess, grassy new slopes; alpha and beyond unchanged."""
    out = np.array(colours, float, copy=True)
    rock, cess, fill = weights(x, y, z, z0, ln)
    moved = _smooth(np.abs(np.asarray(z, float).ravel() - np.asarray(z0, float).ravel()) / .8)
    grain = .85 + .15 * _noise(np.asarray(x).ravel(), np.asarray(y).ravel(), 3., 21)
    rgb = out[:, :3]
    rgb = rgb * (1 - .5 * moved[:, None]) + GRASS * .5 * moved[:, None]
    rgb = rgb * (1 - rock[:, None]) + ROCK * grain[:, None] * rock[:, None]
    rgb = rgb * (1 - cess[:, None]) + CESS * cess[:, None]
    out[:, :3] = rgb
    return out


# --- refining a terrain's triangles ------------------------------------------------------------------------------


def seam_weight(x, y, box, fade=SEAM_FADE):
    """0 on and inside the box [x0, y0, x1, y1] (ground that is not carved), easing to 1 at `fade` metres out."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    dx = np.maximum(np.maximum(box[0] - x, x - box[2]), 0.)
    dy = np.maximum(np.maximum(box[1] - y, y - box[3]), 0.)
    return _smooth(np.hypot(dx, dy) / fade)


def touched(points, ln=None, margin=.02):
    """True for the points the earthworks move (or nearly: within 12 m of the open line)."""
    ln = ln or line()
    p = np.asarray(points, float).reshape(-1, 3)
    if ln is None:
        return np.zeros(len(p), bool)
    moved = np.abs(carve(p[:, 0], p[:, 1], p[:, 2], ln) - p[:, 2]) > margin
    s, u, _ = ln.project(p[:, 0], p[:, 1])
    return moved | (np.isfinite(s) & (np.abs(np.nan_to_num(u, nan=1e9)) < 12.))


def refine(vertices, faces, step, attributes=None, ln=None, holes=True, hidden=None, weight=None, *, conform_neighbors=False):
    """Subdivide the triangles the earthworks touch to about `step` metres, carve every vertex and leave the portal
    holes open. vertices (N, 3) in route metres; faces (M, 3); attributes {name: (N, k)} are interpolated (normals
    are recomputed where carved). `hidden(x, y)`: where this terrain lies under another one (left as it is);
    `weight(x, y)`: 0..1, how much of the carving applies (seam_weight).
    With conform_neighbors, retained adjacent faces share selected edge nodes before carving.
    Returns (vertices, faces, attributes, report)."""
    ln = ln or line()
    shown = (lambda x, y: ~np.asarray(hidden(x, y), bool)) if hidden else (lambda x, y: np.ones(np.shape(x), bool))

    def carved(p):
        z = p[:, 2].copy()
        on = shown(p[:, 0], p[:, 1])
        c = carve(p[on, 0], p[on, 1], p[on, 2], ln)
        w = 1. if weight is None else weight(p[on, 0], p[on, 1])
        z[on] = p[on, 2] + w * (c - p[on, 2])
        return z
    v = np.asarray(vertices, float).reshape(-1, 3)
    f = np.asarray(faces, np.int64).reshape(-1, 3)
    attributes = {k: np.asarray(a, float).reshape(len(v), -1) for k, a in (attributes or {}).items()}
    if ln is None or not len(f):
        return v, f, attributes, dict(refined=0)
    # Triangles touched by the earthworks: at a corner, the centre or an edge's middle.
    tri = v[f]
    probes = np.concatenate([tri, tri.mean(1, keepdims=True), (tri + np.roll(tri, -1, 1)) / 2], 1)   # (M, 7, 3)
    centre = tri.mean(1)
    span = np.linalg.norm(tri - centre[:, None], axis=2).max(1)
    s, _, _ = ln.project(centre[:, 0], centre[:, 1])
    near = np.isfinite(s)
    near_idx = np.flatnonzero(near)
    hit = np.zeros(len(f), bool)
    if len(near_idx):
        q = probes[near_idx].reshape(-1, 3)
        hit[near_idx] = (touched(q, ln) & shown(q[:, 0], q[:, 1])).reshape(-1, 7).any(1)
    # Wide triangles may hide the line between their probes: take those whose span reaches the centre line too.
    if len(near_idx):
        _, u, _ = ln.project(centre[near_idx, 0], centre[near_idx, 1])
        hit[near_idx] |= (np.abs(u) < span[near_idx] + 6.) & shown(centre[near_idx, 0], centre[near_idx, 1])
    sel = np.flatnonzero(hit)
    keep = np.flatnonzero(~hit)
    report = dict(triangles_in=int(len(f)), refined=int(len(sel)))
    if not len(sel):
        return np.c_[v[:, :2], carved(v)], f, attributes, report
    edges = np.linalg.norm(tri[sel] - np.roll(tri[sel], -1, 1), axis=2).max(1)
    n = int(max(1, math.ceil(float(np.percentile(edges, 95)) / step)))
    # Barycentric template: points (i, j) with i + j <= n and its triangles.
    ij = [(i, j) for i in range(n + 1) for j in range(n + 1 - i)]
    index = {p: k for k, p in enumerate(ij)}
    bary = np.array([(1 - (i + j) / n, i / n, j / n) for i, j in ij])
    tmpl = []
    for i in range(n):
        for j in range(n - i):
            tmpl.append((index[(i, j)], index[(i + 1, j)], index[(i, j + 1)]))
            if i + j < n - 1:
                tmpl.append((index[(i + 1, j)], index[(i + 1, j + 1)], index[(i, j + 1)]))
    tmpl = np.array(tmpl)
    corners = {0: index[(0, 0)], 1: index[(n, 0)], 2: index[(0, n)]}
    # New points per selected triangle; corners keep their own vertex.
    fs = f[sel]
    pts = np.einsum('pk,tkc->tpc', bary, v[fs])                                  # (T, P, 3)
    ids = np.full(pts.shape[:2], -1, np.int64)
    for c, p in corners.items():
        ids[:, p] = fs[:, c]
    fresh = ids < 0
    q = pts[fresh]
    key = np.round(q * 1000.).astype(np.int64)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inverse = inverse.ravel()
    ids[fresh] = len(v) + inverse
    new_v = q[first]
    out_attr = {}
    for name, a in attributes.items():
        interp = np.einsum('pk,tkc->tpc', bary, a[fs])[fresh][first]
        out_attr[name] = np.concatenate([a, interp])
    allv = np.concatenate([v, new_v])
    retained=f[keep]
    if conform_neighbors:
        centres,retained,parents,joined=_conform_neighbors(v,retained,fs,ids,index,n,allv)
        if len(centres):
            allv=np.concatenate([allv,centres])
            for name,a in attributes.items():out_attr[name]=np.concatenate([out_attr[name],a[parents].mean(1)])
        report['conforming_neighbors']=joined
    z0 = allv[:, 2].copy()
    allv[:, 2] = carved(allv)
    new_f = ids[:, tmpl].reshape(-1, 3)
    if holes:
        c = allv[new_f].mean(1)
        open_ = in_hole(c[:, 0], c[:, 1], c[:, 2], ln) & shown(c[:, 0], c[:, 1])
        report['hole_triangles'] = int(open_.sum())
        new_f = new_f[~open_]
    faces_out = np.concatenate([retained, new_f])
    if 'normals' in out_attr:
        moved = np.abs(allv[:, 2] - z0) > 1e-3
        moved[len(v):] = True
        out_attr['normals'] = _normals(allv, faces_out, out_attr['normals'], moved)
    report.update(subdivision=n, triangles_out=int(len(faces_out)), vertices_added=int(len(allv)-len(v)),
                  moved=int((np.abs(allv[:, 2] - z0) > .01).sum()))
    return allv, faces_out, out_attr, report


def _conform_neighbors(v,retained,selected,ids,index,n,allv):
    """@cc [owner:fontanierh,label:correctness] selected-retained-edge-ownership
    Retained neighbors MUST reuse selected template edge nodes before the shared
    carve. No inferred nearby vertex may be welded. Original endpoint ownership
    and conflicting selected chains MUST be checked; selected triangles and
    vertices remain unchanged. The default refine path MUST remain unchanged.
    """
    if n<=1 or not len(retained):return np.empty((0,3)),retained,np.empty((0,3),int),0
    # Adjacent grid cells may duplicate the same original endpoint. Quantized
    # XYZ IDs only find candidates; actual original endpoints are checked below.
    _,canonical=np.unique(np.round(v*1.e7).astype(np.int64),axis=0,return_inverse=True)
    canonical=canonical.ravel();chains={}
    templates=[[index[(i,0)] for i in range(n+1)],
               [index[(n-i,i)] for i in range(n+1)],
               [index[(0,n-i)] for i in range(n+1)]]
    for face,nodes in zip(selected,ids):
        for e,(a,b) in enumerate(zip(face,np.roll(face,-1))):
            ca,cb=int(canonical[a]),int(canonical[b]);key=tuple(sorted((ca,cb)))
            chain=nodes[templates[e]]
            if ca>cb:chain=chain[::-1]
            prior=chains.get(key)
            if prior is not None and np.max(abs(allv[prior]-allv[chain]))>1.e-7:
                raise ValueError('Conflicting selected earthworks edge ownership')
            chains[key]=chain
    output=[];centres=[];parents=[]
    for face in retained:
        polygon=[];changed=False
        for a,b in zip(face,np.roll(face,-1)):
            polygon.append(int(a));ca,cb=int(canonical[a]),int(canonical[b]);chain=chains.get(tuple(sorted((ca,cb))))
            if chain is None:continue
            if ca>cb:chain=chain[::-1]
            if np.max(abs(v[[a,b]]-allv[chain[[0,-1]]]))>1.e-7:
                raise ValueError('Distinct original earthworks endpoints')
            polygon.extend(map(int,chain[1:-1]));changed=True
        if not changed:output.append(face);continue
        centre=len(allv)+len(centres);centres.append(v[face].mean(0));parents.append(face)
        output.extend((centre,a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))
    return np.asarray(centres).reshape(-1,3),np.asarray(output).reshape(-1,3),np.asarray(parents).reshape(-1,3),len(centres)


def _normals(v, f, old, which):
    """Area-weighted vertex normals for the vertices `which`; the others keep theirs."""
    n = np.zeros_like(v)
    face = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for k in range(3):
        np.add.at(n, f[:, k], face)
    length = np.linalg.norm(n, axis=1, keepdims=True)
    n = n / np.maximum(length, 1e-12)
    n[n[:, 2] < 0] *= -1
    out = np.array(old, float, copy=True)
    out[which] = n[which]
    return out


def polygons(vertices, faces, step, ln=None, hidden=None, *, conform_neighbors=False):
    """`refine` for Blender-style polygon lists (quads or triangles, no attributes): (vertices, faces, report).
    Unchanged without a line."""
    ln = ln or line()
    if ln is None:
        return vertices, faces, dict(refined=0)
    tris = []
    for p in faces:
        tris.extend((p[0], p[k], p[k + 1]) for k in range(1, len(p) - 1))
    v, f, _, report = refine(np.asarray(vertices, float), np.asarray(tris), step, ln=ln, hidden=hidden, conform_neighbors=conform_neighbors)
    print('RAILWAY EARTHWORKS', report, flush=True)
    if not report.get('refined'):
        return vertices, faces, report
    return [tuple(map(float, p)) for p in v], [tuple(map(int, t)) for t in f], report


SHEET_STEP = 2.5            # metres: the foothills' 5 m cells split in three where the earthworks touch them


def sheet(data, step=SHEET_STEP, ln=None, hidden=None):
    """A terrain sheet {vertices, faces, colours (RGB + a mask), normals} carved and painted, the mask (the
    foothills' snow) cleared where the ground moved. Unchanged without a line."""
    ln = ln or line()
    if ln is None:
        return data
    z0 = None
    v, f, a, report = refine(data['vertices'], data['faces'], step, dict(colours=data['colours'], normals=data['normals'],
                                                                       natural=np.asarray(data['vertices'])[:, 2:3]), ln,
                          hidden=hidden)
    if not report.get('refined'):
        return data
    z0 = a['natural'][:, 0]
    colours = paint(a['colours'], v[:, 0], v[:, 1], v[:, 2], z0, ln)
    if colours.shape[1] > 3:
        colours[:, 3] *= 1 - _smooth(np.abs(v[:, 2] - z0) / .5)
    print('RAILWAY EARTHWORKS', report, flush=True)
    return dict(data, vertices=v, faces=f.astype(np.int32), colours=colours, normals=a['normals'])


def quads(mesh, origin, step, ln=None, hidden=None, weight=None):
    """`refine` in place for a hippodrome.build.Mesh (lists p, n, t, i; positions relative to `origin`), keeping each
    vertex's natural height in `mesh.natural` for `paint`. Returns the report."""
    ln = ln or line()
    if ln is None or not mesh.i:
        return dict(refined=0)
    origin = np.asarray(origin, float)
    v = np.asarray(mesh.p, float) + origin
    attrs = dict(normals=np.asarray(mesh.n, float), uv=np.asarray(mesh.t, float), natural=v[:, 2:3])
    v, f, a, report = refine(v, np.asarray(mesh.i).reshape(-1, 3), step, attrs, ln, hidden=hidden, weight=weight)
    mesh.p = list(v - origin)
    mesh.n = list(a['normals'])
    mesh.t = [tuple(uv) for uv in a['uv']]
    mesh.i = [int(k) for k in f.ravel()]
    mesh.natural = a['natural'][:, 0]
    print('RAILWAY EARTHWORKS', report, flush=True)
    return report


def stitch(meshes, origin, lines, ln=None, tol=1e-4, *, whole_seam=False):
    """Close the seams between hippodrome.build.Mesh terrains refined at different steps: along each straight seam
    (axis 0: x = value, axis 1: y = value), every seam vertex of one mesh near the line becomes a vertex of the other
    (its seam triangles are fanned), at the exact height the first mesh gives it. Returns the vertices added."""
    ln = ln or line()
    if ln is None and not whole_seam:
        return 0
    origin = np.asarray(origin, float)
    added = 0
    for axis, value in lines:
        across = 1 - axis       # the seam runs along this coordinate
        seams = []
        for mesh in meshes:
            p = np.asarray(mesh.p, float) + origin
            on = np.abs(p[:, axis] - value) < tol
            near = np.flatnonzero(on)
            if not whole_seam:
                s, _, _ = ln.project(p[on, 0], p[on, 1])
                near = near[np.isfinite(s)]
            seams.append({round(float(p[k, across]), 4): float(p[k, 2]) for k in near})
        for m, mesh in enumerate(meshes):
            others = {}
            for k, seam in enumerate(seams):
                if k != m:
                    others.update(seam)
            if not others:
                continue
            keys = np.array(sorted(others))
            heights = np.array([others[k] for k in keys])
            p = np.asarray(mesh.p, float) + origin
            n, t = np.asarray(mesh.n, float), np.asarray(mesh.t, float)
            natural = getattr(mesh, 'natural', None)
            tris = np.asarray(mesh.i).reshape(-1, 3)
            on = np.abs(p[:, axis] - value) < tol
            out, new_p, new_n, new_t, new_nat = [], [], [], [], []
            base = len(p)
            for a, b, c in tris:
                done = False
                for e0, e1, opp in ((a, b, c), (b, c, a), (c, a, b)):
                    if not (on[e0] and on[e1]):
                        continue
                    u0, u1 = p[e0, across], p[e1, across]
                    inside = keys[(keys > min(u0, u1) + tol) & (keys < max(u0, u1) - tol)]
                    if not len(inside):
                        break
                    inside = inside if u1 > u0 else inside[::-1]
                    chain = [e0]
                    for q in inside:
                        f = (q - u0) / (u1 - u0)
                        point = p[e0] + f * (p[e1] - p[e0])
                        point[across] = q
                        point[2] = heights[np.searchsorted(keys, q)]
                        new_p.append(point)
                        new_n.append(n[e0] + f * (n[e1] - n[e0]))
                        new_t.append(t[e0] + f * (t[e1] - t[e0]))
                        if natural is not None:
                            new_nat.append(natural[e0] + f * (natural[e1] - natural[e0]))
                        chain.append(base + len(new_p) - 1)
                    chain.append(e1)
                    out.extend((x0, x1, opp) for x0, x1 in zip(chain[:-1], chain[1:]))
                    done = True
                    break
                if not done:
                    out.append((a, b, c))
            if new_p:
                mesh.p = list(np.concatenate([p, new_p]) - origin)
                mesh.n = list(np.concatenate([n, new_n]))
                mesh.t = [tuple(v) for v in np.concatenate([t, new_t])]
                mesh.i = [int(k) for k in np.asarray(out).ravel()]
                if natural is not None:
                    mesh.natural = np.concatenate([natural, new_nat])
                added += len(new_p)
    return added
