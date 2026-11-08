"""Supports for the owner's editor park: stone viaducts, after the approved Sunburst design
(assets/craterpark/concepts/editor/support-design-viaduct.jpg).

Every ramp rides on one arcade as wide as the ramp: solid piers of dark basalt masonry, battered wider toward their
foot, linked by round arches whose crowns sit a constant ring below the ramp, so the stone always meets the wood in one
clean line. A few piers per piece (SPAN_MIN to SPAN_MAX apart, wider for the high pieces), never a forest of posts; a
run too low for an arch rests on a solid wall. Where another piece passes underneath, the arcade lifts clear of it and
no pier stands there.

The arcade is lofted along the piece's own stations, its top just under the piece's underside (the pieces' own
vertices) and its foot sunk into the cut ground the volcano follows, so nothing floats. Bowls (in their own pits) and
decks get none. The Vert drop line stands on a timber stage instead (`stage`, after
concepts/editor/vertdrop-kiyomizu-overview.jpg).
"""
import math

import numpy as np

from . import dsl

STONE = 'material_029'        # basalt ashlar masonry, a world-aligned Sunburst painting (tools/craterpark_textures.py)

DS = 1.               # metres between loft sections along a piece
INSET = .4            # the arcade is this much narrower than the piece on each side
SINK = 2.             # the arcade goes this far into the ground (the volcano samples the cut ground every 5 m)
EMBED = -.25          # its top stops just under the ramp (the pieces are single sheets, no thickness)
MIN_BODY = 1.         # metres of stone at least, or no arcade at that section
SPAN_MIN, SPAN_MAX = 12., 30.   # clear arch openings, scaled with the piece's clearance
PIER_MIN, PIER_MAX = 4., 7.     # pier thickness along the piece
BATTER = .05          # each pier side leans out this much per metre down to its foot
BATTER_MAX = 6.       # metres: at most
RING_MIN, RING_MAX = 1.6, 3.5   # stone kept above an arch's crown
MIN_RISE = 2.        # an opening lower than this is left solid
OVER = 4.5            # metres kept clear above another piece running underneath: a rider and an ollie
TIER = 26.           # an opening taller than this gets a lower tier of arches (as an aqueduct's)
TALL_BLOCK = 25.     # a stretch too short for a span but this tall gets one arch through it
# the concept's relief (support-design-viaduct.jpg): piers standing proud of the faces, arch rings, a cornice under the
# ramp, plinths and boulders at the feet
ROCK = 'material_027'         # the volcano's restyled rock, for the boulders round the feet
PROUD = .35           # the top of a pier stands this far out of the arcade's faces
SETBACK = .3          # each ledge up a pier steps in this much (so its lower stages stand further out)
CORNER = .8           # rounded pier corners (radius, m)
PLINTH = .8           # a pier's plinth rises this far above the highest ground under it...
PLINTH_OUT = .5       # ...and steps out this much round it
CORNICE = 1.1         # the cornice band under the ramp: its height...
OVERHANG = .45        # ...and how far it stands out of the faces (just under the ramp's edge)
RING_DEPTH = 1.1      # the arch rings (archivolts): their depth round the opening...
RING_PROUD = .2       # ...and how far they stand out of the faces
WALL_ROW = 3.0        # the arcade's faces are cut in courses this high...
WALL_BUMP = .12       # ...each standing up to this much in or out
COURSE = (1.5, 2.6)   # pier courses: heights between these
VOUSSOIR = 1.         # arch stones: about this long round the arch
# the start tower: a solid deck standing high above the ground becomes a Japanese castle keep: a curved stone base
# (ishigaki) under a white-plastered turret (yagura) with a tiled skirt roof, a balcony with a vermilion railing round
# the deck, a torii over the drop-in and a shrine balcony off the back of the deck
VERMILION = 'material_038'    # lacquered vermilion: torii, posts and railing
TILE = 'material_039'         # dark blue-grey roof tiles, the torii's black lintel
PLASTER = 'material_040'      # white lime plaster
TIMBER = 'material_041'       # dark stained timber: the turret's boards and frame, the deck's edge
TOWER_MIN = 6.        # a solid deck this far above the ground becomes a tower
ISHIGAKI_FLARE = .2   # the stone base spreads out this share of its height at its foot (at most ISHIGAKI_MAX)...
ISHIGAKI_MAX = 15.
ISHIGAKI_CURVE = 2.2  # ...along this concave curve: near upright under the turret, sweeping out toward the foot
YAGURA = 6.5          # the plastered turret under the deck: this tall...
YAGURA_OUT = .8       # ...standing this far out of the deck's outline, its lower BOARDS share in dark boards
BOARDS = .38
SKIRT = 2.8           # the tiled skirt roof round the turret's foot: its reach...
SKIRT_DROP = 1.5      # ...its drop...
SORI = .7             # ...and every eave's upturn at the corners
RIM = 1.7             # the balcony round the deck, outside its planks
RAIL = 1.1            # the railing's height
TORII = 10.           # the torii over the drop-in: its height
TORII_LIFT = 2.       # ...and this much more over a roll-in
TORII_BACK = 6.       # its pillars stand on the deck this far back from the drop-in's edge, clear of the ramp's walls
TORII_CLEAR = 3.5     # ...this far from any wall or coping above the deck,
RUNWAY_CLEAR = 4.     # ...and this far from the run-in (RUNWAY m back from its first station) of a line starting there
RUNWAY = 12.
# the shrine balcony off the back of the deck (concept C, tower-top-shrine-balcony.jpg; its models are shrine.py's)
SHRINE_DEPTH = 17.    # its depth out from the tower's rim...
SHRINE_STEP = .45     # ...its floor this far above the rim's boards, behind the deck's railing...
SHRINE_SLAB = .9      # ...boards over a timber frame this deep
SHRINE_CLEAR = 3.5    # kept this far (plan) from any other piece's surface from SHRINE_BELOW under its floor to over its
SHRINE_BELOW = 4.     # roofs, RUNWAY_CLEAR from every run-in and over no other piece at all...
SHRINE_WIDE, SHRINE_DEEP = 12., 15.   # ...at least this wide and deep, or no shrine
SHRINE_POST = 1.1     # its posts' half thickness (the tower's are TOWER_POST)
SHRINE_FRONT = 4.     # the pavilion stands this far back from the balcony's front edge...
SHRINE_TORII = 1.3    # ...the torii this far back, just behind the deck's railing, framing the pavilion
SHRINE_BANNERS = 3.   # metres between the nobori along the back
TOWER_TIMBER = True   # the tower stands on an open timber frame as the Vert drop's concept, not on the stone keep
TOWER_POST = 1.5      # its posts' half thickness...
TOWER_BAY = 8.        # ...about this far apart round the deck's outline...
TOWER_NUKI = 20.      # ...tied by nuki this far apart in height


class Ground:
    """Bilinear lookup in the cut-ground grid (native y at native x, z)."""

    def __init__(self, heights, grid):
        self.H, self.g = np.asarray(heights, 'f8').reshape(grid['nz'], grid['nx']), grid

    def __call__(self, x, z):
        g = self.g
        fi = np.clip((np.asarray(x) - g['x0']) / g['G'] - .5, 0, g['nx'] - 1.001)
        fj = np.clip((np.asarray(z) - g['z0']) / g['G'] - .5, 0, g['nz'] - 1.001)
        i, j = np.floor(fi).astype(int), np.floor(fj).astype(int)
        a, c = fi - i, fj - j
        H = self.H
        return ((1 - a) * (1 - c) * H[j, i] + a * (1 - c) * H[j, i + 1]
                + (1 - a) * c * H[j + 1, i] + a * c * H[j + 1, i + 1])


class Plan:
    """Every kept piece's triangles hashed on a plan grid: the piece surfaces right above or below any point."""

    def __init__(self, pieces, cell=4.):
        tris, owner = [], []
        for k, p in enumerate(pieces):
            T = np.asarray(p.mesh.V, 'f8')[np.asarray(p.mesh.F)]
            tris.append(T)
            owner.append(np.full(len(T), k))
        self.T, self.owner, self.cell = np.concatenate(tris), np.concatenate(owner), cell
        lo = np.floor(self.T[:, :, [0, 2]].min(1) / cell).astype(int)
        hi = np.floor(self.T[:, :, [0, 2]].max(1) / cell).astype(int)
        cells = {}
        for t, (i0, j0), (i1, j1) in zip(range(len(self.T)), lo, hi):
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    cells.setdefault((i, j), []).append(t)
        self.cells = {key: np.array(v) for key, v in cells.items()}

    def heights(self, x, z):
        """(piece, y) of every piece surface straight above or below the point."""
        t = self.cells.get((math.floor(x / self.cell), math.floor(z / self.cell)))
        if t is None:
            return np.zeros(0, int), np.zeros(0)
        T = self.T[t]
        a, b, c = T[:, 0], T[:, 1], T[:, 2]
        e1, e2 = (b - a)[:, [0, 2]], (c - a)[:, [0, 2]]
        q = np.array([x, z]) - a[:, [0, 2]]
        det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        ok = np.abs(det) > 1e-9                         # vertical faces have no plan area
        det = np.where(ok, det, 1.)
        u = (q[:, 0] * e2[:, 1] - q[:, 1] * e2[:, 0]) / det
        v = (e1[:, 0] * q[:, 1] - e1[:, 1] * q[:, 0]) / det
        hit = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
        y = a[:, 1] + u * (b[:, 1] - a[:, 1]) + v * (c[:, 1] - a[:, 1])
        return self.owner[t][hit], y[hit]

    def span(self, x, z, piece):
        """(underside of `piece` above the point, highest surface of any other piece below that underside) or None."""
        who, y = self.heights(x, z)
        own = y[who == piece]
        if not len(own):
            return None
        under = own.min()
        other = y[(who != piece) & (y < under)]
        return under, (other.max() if len(other) else -np.inf)


def _orient(V, F, N):
    """Faces counter-clockwise seen from their normal's side."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    flip = (np.cross(b - a, c - a) * (N[F[:, 0]] + N[F[:, 1]] + N[F[:, 2]])).sum(1) < 0
    F = F.copy()
    F[flip] = F[flip][:, [0, 2, 1]]
    return F


class Builder:
    def __init__(self):
        self.parts = {}
        self.models = []          # the shrine's textured models: (slug, base point, facing), shrine.place's arguments
        self.shrine = None

    def add(self, material, VFN):
        V, F, N = VFN
        self.parts.setdefault(material, []).append(VFN)

    def meshes(self, feature):
        out = []
        for material, items in self.parts.items():
            V, F, N, base = [], [], [], 0
            for v, f, n in items:
                V.append(v), F.append(f + base), N.append(n)
                base += len(v)
            V, F, N = np.concatenate(V), np.concatenate(F), np.concatenate(N)
            F = _orient(V, F, N)
            ax = np.abs(N).argmax(1)
            UV = np.where(ax[:, None] == 1, V[:, [0, 2]], np.where(ax[:, None] == 0, V[:, [2, 1]], V[:, [0, 1]])) / 4.
            out.append(dsl.Mesh.part(V, F, N=N, UV=UV, role=dsl.SIDE, material=material, feature=feature))
        return out


def _outer_half(s):
    """Half the piece's full width at a station: floor, wall reach and coping deck on each side."""
    reach = []
    for w in (s['wl'], s['wr']):
        h, R = w['h'], max(w['R'], 1e-3)
        reach.append(R if h >= R else R * math.sin(math.acos(max(-1., 1 - h / R))))
    return s['w'] / 2 + max(reach) + s.get('deck', 0)


def _rand(*key):
    """Deterministic uniform [0, 1) from a position: the same park always gets the same stones."""
    h = 2166136261
    for k in key:
        h = ((h ^ (int(round(k * 100)) & 0xffffffff)) * 16777619) & 0xffffffff
    return ((h * 2654435761) & 0xffffffff) / 2 ** 32


def _rings(b, material, rings, normals=None):
    """Loft through closed cross-sections (each (k, 3)), with end caps: flat faces outward, or the given per-ring
    vertex normals (each (k, 3)) on the sides for a smooth (rounded) surface."""
    V, F, N = [], [], []
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        mid = np.concatenate([A, B]).mean(0)
        k = len(A)
        for e in range(k):
            q = np.array([A[e], A[(e + 1) % k], B[(e + 1) % k], B[e]])
            n = np.cross(q[1] - q[0], q[2] - q[0]) + np.cross(q[2] - q[0], q[3] - q[0])
            size = np.linalg.norm(n)
            if size < 1e-6:
                continue
            n = n / size
            if n @ (q.mean(0) - mid) < 0:
                n = -n
            o = len(V)
            V.extend(q)
            if normals is not None:
                N.extend([normals[i][e], normals[i][(e + 1) % k], normals[i + 1][(e + 1) % k], normals[i + 1][e]])
            else:
                N.extend([n] * 4)
            F.extend([(o, o + 1, o + 2), (o, o + 2, o + 3)])
    for R, other in ((rings[0], rings[1]), (rings[-1], rings[-2])):
        out = R.mean(0) - other.mean(0)
        size = np.linalg.norm(out)
        if size < 1e-9:
            continue
        o = len(V)
        V.extend([R.mean(0)] + list(R))
        N.extend([out / size] * (len(R) + 1))
        F.extend([(o, o + 1 + e, o + 1 + (e + 1) % len(R)) for e in range(len(R))])
    if F:
        b.add(material, (np.array(V, 'f8'), np.array(F, 'i8'), np.array(N, 'f8')))


def _rounded(c, fwd, acr, a, w, y, r=CORNER, seg=3):
    """A rounded rectangle at height y, `a` long (half, along fwd) and `w` wide (half, along acr): points and their
    outward horizontal normals."""
    r = min(r, a * .9, w * .9)
    pts, nrm = [], []
    for su, sv, a0 in ((1, 1, 0.), (-1, 1, .5 * np.pi), (-1, -1, np.pi), (1, -1, 1.5 * np.pi)):
        for k in range(seg + 1):
            ang = a0 + .5 * np.pi * k / seg
            du, dv = math.cos(ang), math.sin(ang)
            u, v = su * (a - r) + r * du, sv * (w - r) + r * dv
            pts.append((c[0] + u * fwd[0] + v * acr[0], y, c[1] + u * fwd[1] + v * acr[1]))
            nrm.append((du * fwd[0] + dv * acr[0], 0., du * fwd[1] + dv * acr[1]))
    return np.array(pts), np.array(nrm)


def _lean(s, y):
    """The arcade's half width at height y in section s: its faces lean out BATTER per metre below the ramp."""
    return s.half + min(BATTER * max(s.top - y, 0.), BATTER_MAX)


_ICO = None


def _boulder(b, plan, ground, x, z, r, seed):
    """A half-buried, faceted boulder of radius r at (x, z); none where a piece lies within reach above the ground."""
    global _ICO
    g = float(ground(x, z))
    who, y = plan.heights(x, z)
    if len(y) and (y < g + 2.5 * r + 1.).any():
        return 0
    if _ICO is None:
        t = (1 + 5 ** .5) / 2
        P = np.array([(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
                      (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)], 'f8')
        F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
             (8, 6, 7), (9, 8, 1)]
        P = list(P / np.linalg.norm(P[0]))
        mids, F2 = {}, []
        for a, bb, c in F:                                   # one subdivision: 80 faces
            m = []
            for i, j in ((a, bb), (bb, c), (c, a)):
                key = (min(i, j), max(i, j))
                if key not in mids:
                    q = P[i] + P[j]
                    P.append(q / np.linalg.norm(q))
                    mids[key] = len(P) - 1
                m.append(mids[key])
            F2 += [(a, m[0], m[2]), (bb, m[1], m[0]), (c, m[2], m[1]), (m[0], m[1], m[2])]
        _ICO = np.array(P), np.array(F2)
    P, F = _ICO
    bump = np.array([1 + .32 * (_rand(seed, i, 7.) - .5) for i in range(len(P))])
    yaw = _rand(seed, 3.) * 2 * np.pi
    S = P * bump[:, None] * [r * (1 + .3 * _rand(seed, 5.)), r * .62, r]
    S = S @ np.array([[math.cos(yaw), 0, -math.sin(yaw)], [0, 1, 0], [math.sin(yaw), 0, math.cos(yaw)]])
    S += [x, g - .3 * r, z]
    T = S[F]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    b.add(ROCK, (T.reshape(-1, 3), np.arange(len(F) * 3).reshape(-1, 3), np.repeat(n, 3, axis=0)))
    return 1


def _samples(stations):
    """The piece resampled every DS metres: d, x, z, heading (radians) and the arcade's half width; None if too short."""
    d = np.array([s['d'] for s in stations], 'f8')
    if len(d) < 2 or d[-1] - d[0] < 3 * DS:
        return None
    t = np.arange(d[0], d[-1] + 1e-6, DS)
    if t[-1] < d[-1] - 1e-6:
        t = np.append(t, d[-1])
    h = np.interp(t, d, np.unwrap(np.radians([s['h'] for s in stations])))
    half = np.interp(t, d, [_outer_half(s) - INSET for s in stations])
    return t, np.interp(t, d, [s['x'] for s in stations]), np.interp(t, d, [s['z'] for s in stations]), h, half


class Section:
    """What the arcade meets at one sample: the underside on each side, the ground, and any piece running below."""

    def __init__(self, plan, ground, piece, x, z, h, half):
        self.c, self.across, self.half = np.array([x, z]), np.array([-math.sin(h), math.cos(h)]), half
        under, self.over = {}, -np.inf
        for v in (-1., -.5, 0., .5, 1.):
            got = plan.span(*(self.c + v * half * self.across), piece)
            if got is None:
                self.ok = False
                return
            under[v], self.over = got[0], max(self.over, got[1])
        self.top_l = min(under[-1.], under[-.5], under[0.]) + EMBED
        self.top_r = min(under[0.], under[.5], under[1.]) + EMBED
        self.top = min(self.top_l, self.top_r)
        g = [float(ground(*(self.c + v * half * self.across))) for v in (-1., -.5, 0., .5, 1.)]
        self.g_lo, self.g_hi = min(g), max(g)
        self.blocked = self.over > self.g_lo - SINK           # another piece runs between the ground and this one
        self.lo = self.over + OVER if self.blocked else self.g_lo - SINK
        self.ok = self.top - self.lo >= MIN_BODY and self.top - self.g_hi > .5

    def foot(self, ground):
        """A pier's foot level: its lowest level, sunk under the ground at its battered corners too."""
        if self.blocked:
            return self.lo
        wide = self.half + min(BATTER * max(self.top - self.lo, 0.), BATTER_MAX)
        return min(self.lo, min(float(ground(*(self.c + v * wide * self.across))) for v in (-1., 1.)) - SINK)


def _piers(ts, blocked, clear):
    """Sample index ranges [(i0, i1)] of the piers along one stretch of arcade, about one span apart; a pier that
    would stand on another piece moves aside, or is left out."""
    n = len(ts)
    span = float(np.clip(.8 * clear, SPAN_MIN, SPAN_MAX))
    pier = float(np.clip(3. + .06 * clear, PIER_MIN, PIER_MAX))
    length = ts[-1] - ts[0]
    if length <= 2 * pier + .6 * SPAN_MIN:
        if clear > TALL_BLOCK and length >= 16.:              # a tall block: one arch through it
            w = max(2, int(round(.3 * length / DS)))
            return [(0, w), (n - 1 - w, n - 1)]
        return [(0, n - 1)]                                   # too short for an arch: one solid block
    gaps = max(1, int(round((length - pier) / (span + pier))))
    step = (length - pier) / gaps
    w = max(1, int(round(pier / DS)))
    out = []
    for k in range(gaps + 1):
        centre = ts[0] + pier / 2 + k * step
        i = int(np.argmin(np.abs(ts - centre)))
        for shift in sorted(range(-int(step / 3 / DS), int(step / 3 / DS) + 1), key=abs):
            i0 = min(max(i + shift - w // 2, 0), n - 1 - w)
            if not blocked[i0:i0 + w + 1].any():
                out.append((i0, i0 + w))
                break
    merged = []
    for a, b in out:
        if merged and a - merged[-1][1] < 3:                  # no room for an arch between them
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def _arch(secs, ts, f0, f1, top0=None, top1=None):
    """The intrados over the opening between samples f0 and f1 (pier faces), per sample f0..f1, or None if too low.
    The arch rakes with the ramp: its crown stays a ring's depth under the line between the two pier tops (top0 and
    top1 for a lower tier, whose band is level with them)."""
    a, b = secs[f0], secs[f1]
    top0 = a.top if top0 is None else top0
    top1 = b.top if top1 is None else top1
    half = (ts[f1] - ts[f0]) / 2
    ring = float(np.clip(.12 * 2 * half, RING_MIN, RING_MAX))
    rise = min(half, top0 - ring - a.g_hi, top1 - ring - b.g_hi)
    if rise < MIN_RISE:
        return None
    radius = (half * half + rise * rise) / (2 * rise)
    mid = (ts[f0] + ts[f1]) / 2
    out = []
    for k in range(f0, f1 + 1):
        line = top0 + (top1 - top0) * (ts[k] - ts[f0]) / (2 * half)
        arc = math.sqrt(max(radius * radius - (ts[k] - mid) ** 2, 0.)) - (radius - rise)
        y = min(line - ring - rise + arc, min(secs[k].top, line) - RING_MIN)
        out.append(max(y, secs[k].lo))
    return out


def _tiers(secs, ts, f0, f1, arc):
    """Lower tiers under a tall opening: each a level band halfway down its lower side with its own arch, while room
    remains.
    [(band top per sample f0..f1, intrados per sample)]."""
    out = []
    while min(arc[0] - secs[f0].g_hi, arc[-1] - secs[f1].g_hi) > TIER:
        # level, as an aqueduct's tiers are: halfway up the lower side, so under a raking ramp the bays step down
        # one by one instead of a slab raking across the arches above
        t = min(secs[f0].g_hi + .5 * (arc[0] - secs[f0].g_hi), secs[f1].g_hi + .5 * (arc[-1] - secs[f1].g_hi))
        lower = _arch(secs, ts, f0, f1, t, t)
        if lower is None:
            break
        out.append(([t] * (f1 - f0 + 1), lower))
        arc = lower
    return out


def _loft(b, rows):
    """Loft the arcade through its sections [(Section, bottom[, top left, top right])], with flat-shaded closed faces.
    Its sides lean out BATTER per metre below the ramp, so piers, arches and tiers share one battered face, and are cut
    in courses WALL_ROW high, each a little in or out (WALL_BUMP), so the stone never reads machine-flat."""
    n = int(np.clip(math.ceil(max(max(top or (s.top,)) - bot for s, bot, *top in rows) / WALL_ROW), 1, 40))
    corners = []
    for s, bot, *top in rows:
        (x, z), u = s.c, s.across
        top_l, top_r = top or (s.top_l, s.top_r)

        def side(sign, top_y):
            pts = []
            for r in range(n + 1):
                y = bot + (top_y - bot) * r / n
                bump = 0. if r in (0, n) else WALL_BUMP * (2 * _rand(x, z, r, sign) - 1)
                w = _lean(s, y) + bump
                pts.append((x + sign * w * u[0], y, z + sign * w * u[1]))
            return pts
        right, left = side(1., top_r), side(-1., top_l)
        corners.append(np.array([left[0]] + right + left[::-1][:-1]))
    V, F, N = [], [], []
    k = len(corners[0])

    def quad(q, outward):
        nn = np.cross(q[1] - q[0], q[2] - q[0]) + np.cross(q[2] - q[0], q[3] - q[0])
        size = np.linalg.norm(nn)
        if size < 1e-6:
            return
        nn = nn / size
        if nn @ outward < 0:
            nn = -nn
        o = len(V)
        V.extend(q), N.extend([nn] * 4), F.extend([(o, o + 1, o + 2), (o, o + 2, o + 3)])

    for i in range(len(rows) - 1):
        A, B = corners[i], corners[i + 1]
        fwd = np.array([*(rows[i + 1][0].c - rows[i][0].c)])[[0, 0, 1]] * [1, 0, 1]
        if np.linalg.norm(fwd) < 1e-9:                       # a pier face: both sections at one sample
            s = rows[i][0]
            fwd = np.array([-s.across[1], 0., s.across[0]]) * (1 if rows[i + 1][1] > rows[i][1] else -1)
            for e in range(k):
                quad(np.array([A[e], A[(e + 1) % k], B[(e + 1) % k], B[e]]), fwd)
            continue
        mid = np.concatenate([A, B]).mean(0)
        for e in range(k):
            q = np.array([A[e], A[(e + 1) % k], B[(e + 1) % k], B[e]])
            quad(q, q.mean(0) - mid)
    for C, sign, j in ((corners[0], -1, 0), (corners[-1], 1, -1)):   # end caps: fans
        s = rows[j][0]
        out = sign * np.array([-s.across[1], 0., s.across[0]])
        c = C.mean(0)
        for e in range(k):
            tri = np.array([c, C[e], C[(e + 1) % k]])
            nn = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            if np.linalg.norm(nn) < 1e-9:
                continue
            o = len(V)
            V.extend([tri[0], tri[1], tri[2], tri[2]]), N.extend([out] * 4), F.append((o, o + 1, o + 2))
    if F:
        b.add(STONE, (np.array(V, 'f8'), np.array(F, 'i8'), np.array(N, 'f8')))


def _at(S, ts, t):
    """The arcade's frame at distance t along a stretch: centre (x, z), across (unit), the section nearest."""
    i = int(np.clip(np.searchsorted(ts, t) - 1, 0, len(ts) - 2))
    f = float(np.clip((t - ts[i]) / max(ts[i + 1] - ts[i], 1e-9), 0., 1.))
    c = S[i].c * (1 - f) + S[i + 1].c * f
    u = S[i].across * (1 - f) + S[i + 1].across * f
    return c, u / np.linalg.norm(u), S[i if f < .5 else i + 1]


def _box(b, material, c, fwd, acr, a, w, y0, y1, yaw=0.):
    """A stone block: `a` long (half, along fwd turned by yaw), `w` wide (half), from y0 to y1, flat faces."""
    ca, sa = math.cos(yaw), math.sin(yaw)
    f = ca * fwd + sa * acr
    u = -sa * fwd + ca * acr
    ring = lambda y: np.array([(c[0] + p * a * f[0] + q * w * u[0], y, c[1] + p * a * f[1] + q * w * u[1])
                               for p, q in ((1, 1), (-1, 1), (-1, -1), (1, -1))])
    _rings(b, material, [ring(y0), ring(y1)])


def _course(b, centre, fwd, acr, along, wide, y0, y1, key, plinth=False, top=None):
    """One rough course of stone, `along` (half, along fwd) by `wide` (half, along acr), from y0 to y1: a little
    shifted, turned and rounded at random, with a corner stone standing out of it about every other course. `top`
    (along, wide) tapers it to another size at y1, a course of a curved wall (the keep's ishigaki): those stay true to
    their neighbours, so the curve reads as one sweep of stone, not a stack of slabs."""
    j = 0. if plinth or top is not None else .22
    cc = centre + (2 * _rand(key, 1.) - 1) * j * fwd + (2 * _rand(key, 2.) - 1) * j * .6 * acr
    yaw = 0. if plinth or top is not None else (2 * _rand(key, 3.) - 1) * .025
    rad = CORNER * (.85 if top is not None else .5 + .7 * _rand(key, 4.))
    f = math.cos(yaw) * fwd + math.sin(yaw) * acr
    u = -math.sin(yaw) * fwd + math.cos(yaw) * acr
    rings, normals = [], []
    for y, (al, wi) in ((y0, (along, wide)), (y1, top or (along, wide))):
        pts, nrm = _rounded(cc, f, u, al, wi, y, rad, seg=2)
        rings.append(pts)
        normals.append(nrm)
    _rings(b, STONE, rings, normals)
    if top is not None:
        return
    if not plinth and _rand(key, 5.) < .55:              # a corner stone standing out of the course
        su, sv = (1 if _rand(key, 6.) < .5 else -1), (1 if _rand(key, 7.) < .5 else -1)
        qa, qw = .5 + .35 * _rand(key, 8.), .4 + .25 * _rand(key, 9.)
        pop = .1 + .15 * _rand(key, 10.)
        qc = cc + su * (along - qa + pop) * f + sv * (wide - qw + pop) * u
        _box(b, STONE, qc, f, u, qa, qw, y0 + .04, y1 - .04)


def _pier(b, plan, ground, S, ts, a, c):
    """A pier over samples a..c, laid in rough courses as the concept's: each course a little shifted, turned and
    stepped, stepping in at a ledge or two on the way up to the capstones, corner stones standing out, on a plinth,
    with rubble round its foot. Returns the boulders placed."""
    mid = (ts[a] + ts[c]) / 2
    centre, acr, s = _at(S, ts, mid)
    fwd = np.array([acr[1], -acr[0]])
    half_len = max((ts[c] - ts[a]) / 2, 1.5)
    top = min(min(S[j].top_l, S[j].top_r) for j in range(a, c + 1)) - CORNICE + .1
    corners = [centre + u * fwd + v * acr for u in (-half_len, half_len) for v in (-s.half, s.half)]
    g_hi = max(float(ground(*q)) for q in corners)
    foot = min(float(ground(*q)) for q in corners) - SINK - 1.
    base = g_hi + PLINTH
    if top - base < 1.5:
        return 0
    height = top - base
    stages = 1 + (height > 14.) + (height > 32.)
    out = PROUD + (stages - 1) * SETBACK

    def course(y0, y1, extra, key, plinth=False):
        along = half_len + .5 * BATTER * max(top - y0, 0.) + extra
        _course(b, centre, fwd, acr, along, _lean(s, y0) + extra, y0, y1, key, plinth)

    course(foot, base, out + PLINTH_OUT, mid, plinth=True)
    y, k = base, 0
    while y < top - .3:
        h = COURSE[0] + (COURSE[1] - COURSE[0]) * _rand(mid, k, 11.)
        y1 = min(y + h, top) if top - (y + h) > .8 else top
        stage = min(int((y - base) / height * stages), stages - 1)
        course(y - .02, y1, out - stage * SETBACK, mid * 13 + k)
        y, k = y1, k + 1
    placed = 0
    n = 4 + min(8, int(height / 6))
    for k in range(n):
        ang = 2 * np.pi * (k + _rand(mid, k, 1.)) / n
        reach = np.array([(half_len + out + PLINTH_OUT) * math.cos(ang), (s.half + out + PLINTH_OUT) * math.sin(ang)])
        reach *= 1.0 + .45 * _rand(mid, k, 2.)
        q = centre + reach[0] * fwd + reach[1] * acr
        r = min(.6 + 1.1 * _rand(mid, k, 3.) + .025 * height, 3.2)
        placed += _boulder(b, plan, ground, q[0], q[1], r, mid * 7 + k)
    return placed


def _archivolt(b, S, ts, f0, f1, arc):
    """The arch's stones: wedge blocks about VOUSSOIR long round the intrados, of uneven depth, each standing a little
    out of the faces."""
    t = np.asarray(ts[f0:f1 + 1], 'f8')
    y = np.asarray(arc, 'f8')
    if len(t) < 4:
        return
    seg = np.hypot(np.diff(t), np.diff(y))
    run = np.r_[0., np.cumsum(seg)]
    count = max(3, int(round(run[-1] / VOUSSOIR)))
    edges = np.linspace(0., run[-1], count + 1)

    def point(d):
        i = int(np.clip(np.searchsorted(run, d) - 1, 0, len(seg) - 1))
        f = (d - run[i]) / max(seg[i], 1e-9)
        tt, yy = t[i] + f * (t[i + 1] - t[i]), y[i] + f * (y[i + 1] - y[i])
        dt, dy = (t[i + 1] - t[i]) / max(seg[i], 1e-9), (y[i + 1] - y[i]) / max(seg[i], 1e-9)
        return tt, yy, -dy, dt                               # the point and the outward normal (away from the opening)

    for k in range(count):
        depth = RING_DEPTH * (.8 + .5 * _rand(t[0], k, 1.))
        proud = RING_PROUD * (.5 + _rand(t[0], k, 2.))
        rings = []
        for d in (edges[k] + .03, edges[k + 1] - .03):
            tt, yy, nt, ny = point(d)
            c_in, u_in, s = _at(S, ts, tt)
            c_out, u_out, _ = _at(S, ts, tt + depth * nt)
            y_out = yy + depth * ny
            w_in, w_out = _lean(s, yy) + proud, _lean(s, y_out) + proud
            rings.append(np.array([(c_in[0] - w_in * u_in[0], yy, c_in[1] - w_in * u_in[1]),
                                   (c_in[0] + w_in * u_in[0], yy, c_in[1] + w_in * u_in[1]),
                                   (c_out[0] + w_out * u_out[0], y_out, c_out[1] + w_out * u_out[1]),
                                   (c_out[0] - w_out * u_out[0], y_out, c_out[1] - w_out * u_out[1])]))
        _rings(b, STONE, rings)


def _cornice(b, S):
    """The capstones along the top of a stretch: a ragged row of blocks one or two metres long, each standing its own
    distance out of the faces and hanging its own depth below the ramp."""
    j = 0
    while j < len(S) - 1:
        e = min(len(S) - 1, j + 1 + int(_rand(S[j].c[0], S[j].c[1], 1.) * 2))
        over = OVERHANG * (.6 + .7 * _rand(S[j].c[0], S[j].c[1], 2.))
        depth = CORNICE * (.75 + .5 * _rand(S[j].c[0], S[j].c[1], 3.))
        rings = []
        for i in range(j, e + 1):
            s = S[i]
            (x, z), u = s.c, s.across
            yb = s.top - depth
            wall, out = _lean(s, yb) - .05, s.half + over
            prof = [(-wall, yb), (-out, yb + .4 * depth), (-out, s.top_l), (out, s.top_r), (out, yb + .4 * depth),
                    (wall, yb)]
            rings.append(np.array([(x + v * u[0], yy, z + v * u[1]) for v, yy in prof]))
        if len(rings) >= 2:
            _rings(b, STONE, rings)
        j = e


def arcade(b, plan, ground, piece, stations):
    """The viaduct under one piece: (piers, arches, metres of arcade, boulders)."""
    got = _samples(stations)
    if got is None:
        return 0, 0, 0., 0
    t, x, z, h, half = got
    secs = [Section(plan, ground, piece, *a) for a in zip(x, z, h, half)]
    piers = arches = rocks = 0
    metres = 0.
    k, n = 0, len(secs)
    while k < n:                                              # stretches of consecutive good sections
        if not secs[k].ok:
            k += 1
            continue
        e = k
        while e + 1 < n and secs[e + 1].ok:
            e += 1
        if e - k >= 2:
            S, ts = secs[k:e + 1], t[k:e + 1]
            clear = float(np.median([s.top - s.g_hi for s in S]))
            rows, P = [], _piers(ts, np.array([s.blocked for s in S]), clear)
            if not P:                                         # every pier would stand on another piece: leave it open
                k = e + 1
                continue
            first, last = P[0][0], P[-1][1]
            # a stretch's ends beyond its first and last piers spring from the stretch end
            spans = ([(0, first)] if first > 1 else []) + [(P[j][1], P[j + 1][0]) for j in range(len(P) - 1)] \
                + ([(last, len(S) - 1)] if last < len(S) - 2 else [])
            bots = {}
            for f0, f1 in spans:
                arc = _arch(S, ts, f0, f1)
                if arc is not None:
                    bots[(f0, f1)] = arc
                    arches += 1
                    _archivolt(b, S, ts, f0, f1, arc)
                    for band, lower in _tiers(S, ts, f0, f1, arc):
                        _loft(b, [(S[j], lower[j - f0], band[j - f0], band[j - f0])
                                  for j in range(f0, f1 + 1)])
                        _archivolt(b, S, ts, f0, f1, lower)
                        arches += 1
            solid = np.ones(len(S), bool)
            for f0, f1 in bots:
                solid[f0 + 1:f1] = False
            i = 0
            while i < len(S):
                if solid[i]:
                    rows.append((S[i], S[i].foot(ground)))
                    i += 1
                    continue
                f0 = i - 1
                f1 = next(f for a, f in bots if a == f0)
                arc = bots[(f0, f1)]
                for j in range(f0, f1 + 1):
                    rows.append((S[j], arc[j - f0]))
                i = f1
            _loft(b, rows)
            _cornice(b, S)
            if bots:
                for a, c in P:
                    if c - a >= 1 and not any(S[j].blocked for j in range(a, c + 1)):
                        rocks += _pier(b, plan, ground, S, ts, a, c)
                        piers += 1
            # boulders along the foot of the solid walls
            for j in range(0, len(S), 6):
                if solid[j] and not S[j].blocked and S[j].top - S[j].g_hi > 1.:
                    for side in (-1., 1.):
                        if _rand(ts[j], side, 4.) < .55:
                            q = S[j].c + side * (_lean(S[j], S[j].g_lo) + .3 + _rand(ts[j], side, 5.)) * S[j].across
                            rocks += _boulder(b, plan, ground, q[0], q[1], .7 + .8 * _rand(ts[j], side, 6.),
                                              ts[j] * 3 + side)
            metres += ts[-1] - ts[0]
        k = e + 1
    return piers, arches, metres, rocks


def _rect(V):
    """The top face of a box deck: centre (x, z), long and short axes, half extents along them, and its top y."""
    top = V[:, 1].max()
    P = np.unique(np.round(V[V[:, 1] > top - .05][:, [0, 2]], 3), axis=0)
    c = P.mean(0)
    w, vecs = np.linalg.eigh(np.cov((P - c).T))
    fwd = vecs[:, 1] / np.linalg.norm(vecs[:, 1])
    acr = np.array([-fwd[1], fwd[0]])
    return c, fwd, acr, np.abs((P - c) @ fwd).max(), np.abs((P - c) @ acr).max(), top


def _cylinder(b, material, x, z, y0, y1, r, seg=10):
    ring = lambda y: np.array([(x + r * math.cos(a), y, z + r * math.sin(a))
                               for a in np.linspace(0, 2 * np.pi, seg, endpoint=False)])
    _rings(b, material, [ring(y0), ring(y1)])


def _perimeter(n_side=6):
    """Points round a unit rectangle (u, v in [-1, 1]), the same order for every ring of a roof."""
    out = []
    for k in range(4 * n_side):
        side, f = divmod(k, n_side)
        t = -1 + 2 * f / n_side
        out.append([(1, t), (-t, 1), (-1, -t), (t, -1)][side])
    return np.array(out, 'f8')


def _roof(b, c, fwd, acr, levels):
    """A tiled roof lofted through rectangular rings (half along, half across, y, upturn): each eave rises SORI-like
    toward its corners by `upturn`, so the roof sweeps up at its four corners."""
    P = _perimeter()
    rings = []
    for A, W, y, up in levels:
        m = np.minimum(np.abs(P[:, 0]), np.abs(P[:, 1])) ** 4
        u, v = P[:, 0] * (A + .4 * up * m), P[:, 1] * (W + .4 * up * m)
        rings.append(np.stack([c[0] + u * fwd[0] + v * acr[0], y + up * m, c[1] + u * fwd[1] + v * acr[1]], 1))
    _rings(b, TILE, rings)


def _beam(b, material, c, t, n, half, y0, y1, depth, lift=0.):
    """A beam along t (half long), y0..y1 high, `depth` thick along n; `lift` curves its ends up (a torii's lintel)."""
    rings = []
    for s in np.linspace(-1, 1, 15 if lift else 2):
        dy = lift * s ** 4
        p = c + s * half * t
        rings.append(np.array([(p[0] + q * depth * n[0], y + dy, p[1] + q * depth * n[1])
                               for q, y in ((-1, y0), (1, y0), (1, y1), (-1, y1))]))
    _rings(b, material, rings)


def tower(b, plan, ground, piece, open_sides, k=-1, gates=None, halves=None, runways=()):
    """The start tower under a high solid deck, a Japanese castle keep: a curved ishigaki of stone courses sweeping
    out toward its foot; a white-plastered turret with dark boards and timber frame on top of it, a tiled skirt roof
    round its foot; a balcony with a vermilion railing round the deck on the sides no ramp leaves from; a torii over
    the drop-in where it fits, and the shrine balcony (_shrine) off the back of the deck, so the deck stays open.
    Returns the boulders placed, or None if the deck is not high enough for one."""
    V = np.asarray(piece.mesh.V, 'f8')
    c, fwd, acr, a, w, top = _rect(V)
    corners = [c + u * fwd + v * acr for u in (-a, 0, a) for v in (-w, 0, w)]
    g = [float(ground(*q)) for q in corners]
    g_hi, foot = max(g), min(g) - SINK - 1.
    floor = top - .12                                         # the balcony's boards, just under the deck's planks
    yagura_top = floor - .5
    yagura_foot = yagura_top - YAGURA
    stone_top = yagura_foot - .3
    if top - g_hi < TOWER_MIN or stone_top - g_hi < 2.:
        return None
    key0 = c[0] * 7 + c[1]
    ya, yw = a + YAGURA_OUT, w + YAGURA_OUT
    height = stone_top - foot
    flare = min(ISHIGAKI_FLARE * height, ISHIGAKI_MAX)
    spread = lambda y: .4 + flare * (max(stone_top - y, 0.) / height) ** ISHIGAKI_CURVE

    if TOWER_TIMBER:
        # as the Vert drop's concept: the deck stands on an open timber frame (the stage's), not a stone keep
        _tower_frame(b, plan, ground, k, c, fwd, acr, a, w, yagura_top)
    else:
        # the ishigaki: courses of stone tapering with the curve, true to each other so it sweeps up as one face, with no
        # corner stones standing out of it (upright blocks on a sloping face step like stairs)
        y, k = foot, 0
        while y < stone_top - .3:
            h = COURSE[0] + (COURSE[1] - COURSE[0]) * _rand(key0, k, 11.)
            y1 = min(y + h, stone_top) if stone_top - (y + h) > .8 else stone_top
            s0, s1 = spread(y), spread(y1)
            _course(b, c, fwd, acr, ya + s0, yw + s0, y - .02, y1, key0 * 13 + k, top=(ya + s1, yw + s1))
            y, k = y1, k + 1
        # the skirt roof round the turret's foot, over the top of the stone
        _roof(b, c, fwd, acr, [(ya + .05, yw + .05, yagura_foot + .9, 0.), (ya + .55 * SKIRT, yw + .55 * SKIRT,
                               yagura_foot - .45 * SKIRT_DROP, .3 * SORI), (ya + SKIRT, yw + SKIRT, yagura_foot - SKIRT_DROP,
                                                                            SORI)])
        # the turret: dark boards below, white plaster above, a dark timber frame and barred windows on the plaster
        split = yagura_foot + BOARDS * YAGURA
        _rings(b, TIMBER, [_rounded(c, fwd, acr, ya, yw, yagura_foot, .05, seg=1)[0],
                           _rounded(c, fwd, acr, ya, yw, split, .05, seg=1)[0]])
        _rings(b, PLASTER, [_rounded(c, fwd, acr, ya - .05, yw - .05, split, .05, seg=1)[0],
                            _rounded(c, fwd, acr, ya - .05, yw - .05, yagura_top, .05, seg=1)[0]])
        for n, t, half_face, other in ((fwd, acr, yw, ya), (-fwd, acr, yw, ya), (acr, fwd, ya, yw), (-acr, fwd, ya, yw)):
            count = max(2, int(round(2 * half_face / 3.2)))
            for j in range(count + 1):
                u = -half_face + 2 * half_face * j / count
                _box(b, TIMBER, c + other * n + u * t, n, t, .1, .18, split, yagura_top)
            _beam(b, TIMBER, c + (other + .02) * n, t, n, half_face, split - .12, split + .15, .1)
            _beam(b, TIMBER, c + (other + .02) * n, t, n, half_face, yagura_top - .35, yagura_top, .1)
            for j in range(count):
                u = -half_face + 2 * half_face * (j + .5) / count
                wy = split + .55 * (yagura_top - split)
                _box(b, TIMBER, c + (other + .03) * n + u * t, n, t, .08, .6, wy - .45, wy + .45)
    # brackets under the balcony, then its boards
    for n, t, half_face, other in ((fwd, acr, w + RIM, a), (-fwd, acr, w + RIM, a), (acr, fwd, a + RIM, w),
                                   (-acr, fwd, a + RIM, w)):
        for j in range(int(2 * half_face // 2.6) + 1):
            u = -half_face + .4 + j * 2.6
            if u > half_face - .4:
                break
            _box(b, TIMBER, c + (other + YAGURA_OUT + .5 * (RIM - YAGURA_OUT)) * n + u * t, n, t,
                 .5 * (RIM - YAGURA_OUT) + .1, .15, yagura_top - .9, yagura_top)
    _rings(b, TIMBER, [_rounded(c, fwd, acr, a + RIM, w + RIM, yagura_top - .02, .1, seg=1)[0],
                       _rounded(c, fwd, acr, a + RIM, w + RIM, floor, .1, seg=1)[0]])
    _rings(b, TIMBER, [_rounded(c, fwd, acr, a, w, floor - .05, .05, seg=1)[0],
                       _rounded(c, fwd, acr, a, w, top - .02, .05, seg=1)[0]])
    sides = ((0, fwd, acr, w, a), (1, -fwd, acr, w, a), (2, acr, fwd, a, w), (3, -acr, fwd, a, w))
    # the vermilion railing round the balcony, except where a ramp leaves
    for side, n, t, half_face, other in sides:
        if side in open_sides:
            continue
        edge, span = other + RIM - .2, half_face + RIM - .2
        lo, hi = -span, span
        for g in open_sides:                                  # stop short of a drop-in beside this side
            _, gn, _, _, g_other = sides[g]
            if gn @ t > .5:
                hi = g_other - .4
            elif gn @ t < -.5:
                lo = -(g_other - .4)
        count = max(2, int(round((hi - lo) / 2.)))
        for j in range(count + 1):
            u = lo + (hi - lo) * j / count
            corner = j in (0, count)
            _box(b, VERMILION, c + edge * n + u * t, n, t, .11, .11, floor, floor + RAIL + (.3 if corner else 0.))
            if corner:
                _cylinder(b, TILE, *(c + edge * n + u * t), floor + RAIL + .3, floor + RAIL + .55, .16, seg=8)
        for yy in (floor + .45, floor + RAIL - .1):
            _beam(b, VERMILION, c + edge * n + (lo + hi) / 2 * t, t, n, (hi - lo) / 2, yy, yy + .12, .07)
    # the torii over the drop-in: two vermilion pillars on black feet, the tie beam through them, the lintel and its
    # black, upturned cap
    gate = next(iter(sorted(open_sides if gates is None else gates)), None)
    if gate is not None:
        _, n, t, half_face, other = sides[gate]
        gate_h = TORII + TORII_LIFT
        # its pillars on the deck's own planks (or a deck flush with it), RUNWAY_CLEAR from every run-in onto a line
        # that starts here and TORII_CLEAR from any wall or coping standing above the deck: as wide and as near the
        # drop-in as that allows, else no torii
        def clear(q):
            for a, e in runways:
                d = e - a
                u = np.clip(np.dot(q - a, d) / max(np.dot(d, d), 1e-9), 0., 1.)
                if np.linalg.norm(q - (a + u * d)) < RUNWAY_CLEAR:
                    return False
            return not _beside(plan, q, TORII_CLEAR, floor + .3, floor + 3., k)
        fit = next(((b, w) for b in np.arange(min(TORII_BACK, .45 * other), .9 * other, 1.)
                    for w in np.arange(half_face - 1.2, 3.9, -.5)
                    if clear(c + (other - b) * n + w * t) and clear(c + (other - b) * n - w * t)), None)
    if gate is not None and fit is not None:
        span = fit[1]
        base = c + (other - fit[0]) * n
        for sgn in (-1, 1):
            x, z = base + sgn * span * t
            _cylinder(b, TILE, x, z, floor - .02, floor + .7, .62)
            _cylinder(b, VERMILION, x, z, floor + .7, floor + gate_h - .6, .45)
        _beam(b, VERMILION, base, t, n, span + 1.2, floor + gate_h - 2.6, floor + gate_h - 2.05, .3)
        _box(b, VERMILION, base, n, t, .28, .3, floor + gate_h - 2.1, floor + gate_h - 1.05)
        _beam(b, VERMILION, base, t, n, span + 1.3, floor + gate_h - 1.05, floor + gate_h - .55, .38)
        _beam(b, TILE, base, t, n, span + 1.8, floor + gate_h - .55, floor + gate_h + .05, .48, lift=.7)
    # the shrine balcony off the back of the deck (concept C): never off a ledge or another ramp's start
    back = {0: 1, 1: 0, 2: 3, 3: 2}.get(gate, 1)
    if back in open_sides:
        back = next((sd for sd in (back, 1, 0, 3, 2) if sd not in open_sides), None)
    if back is None and not TOWER_TIMBER:
        return None
    if back is not None:
        _, n, t, half_face, other = sides[back]
        _shrine(b, plan, ground, k, c, n, t, half_face, other, floor, runways)
    placed = 0
    if TOWER_TIMBER:
        return placed
    reach_a, reach_w = ya + spread(g_hi) + .5, yw + spread(g_hi) + .5
    count = 10 + int((top - g_hi) / 8)
    for k in range(count):
        ang = 2 * np.pi * (k + _rand(key0, k, 1.)) / count
        q = c + (reach_a * math.cos(ang) * fwd + reach_w * math.sin(ang) * acr) * (1.05 + .3 * _rand(key0, k, 2.))
        r = min(.8 + 1.4 * _rand(key0, k, 3.) + .02 * (top - g_hi), 3.6)
        placed += _boulder(b, plan, ground, q[0], q[1], r, key0 * 3 + k)
    return placed


def _tower_frame(b, plan, ground, k, c, fwd, acr, a, w, y_top):
    """The start tower's timber frame (the Vert drop concept's): posts round the deck's own outline on rough stone
    plinths, through nuki every TOWER_NUKI with iron plates and end blocks on the outer faces, and a ring beam under the
    balcony. A post is left out where any other piece lies below the deck there."""
    hp, cap = TOWER_POST, TOWER_POST * STAGE_EDGE
    ua = np.linspace(-(a - 1.6 * hp), a - 1.6 * hp, max(2, round(2 * a / TOWER_BAY)) + 1)
    vw = np.linspace(-(w - 1.6 * hp), w - 1.6 * hp, max(2, round(2 * w / TOWER_BAY)) + 1)
    ring = ([(u, vw[0]) for u in ua] + [(ua[-1], v) for v in vw[1:]] + [(u, vw[-1]) for u in ua[-2::-1]]
            + [(ua[0], v) for v in vw[-2:0:-1]])
    posts = []
    for u, v in ring:
        p = c + u * fwd + v * acr
        gs = [float(ground(*(p + su * hp * fwd + sv * hp * acr))) for su in (-1, 1) for sv in (-1, 1)]
        who, y = plan.heights(*p)
        if ((who != k) & (y > min(gs) - SINK - 1.) & (y < y_top - .5)).any() or y_top - max(gs) < STAGE_MIN + 3. \
                or _beside(plan, p, hp * PLINTH_WIDE * 1.8 + STAGE_CLEAR, min(gs) - SINK - 1., y_top - 2., k):
            posts.append(None)
            continue
        posts.append(dict(p=p, base=min(gs) - SINK, ground=max(gs), foot=min(y_top - 2., max(gs) + PLINTH_RISE[1])))
    for q in posts:
        if q:
            _plinth(b, q['p'], fwd, acr, hp * PLINTH_WIDE, q['base'], min(q['ground'], q['foot'] - .3), q['foot'])
            _post(b, q['p'], hp, q['foot'] - .2, y_top - cap * .5)
            _box(b, KEYAKI, q['p'], fwd, acr, hp * CAPITAL[0], hp * CAPITAL[0], y_top - cap - hp * CAPITAL[1],
                 y_top - cap * .5)
    ea, eh, el = END_BLOCK
    for A, B in zip(posts, posts[1:] + posts[:1]):
        if not (A and B):
            continue
        d = B['p'] - A['p']
        L = float(np.linalg.norm(d))
        u = d / L
        n = np.array([-u[1], u[0]])
        out = n if float(n @ ((A['p'] + B['p']) / 2 - c)) >= 0 else -n
        level = math.ceil((max(A['foot'], B['foot']) + .5 * TOWER_NUKI) / TOWER_NUKI) * TOWER_NUKI
        while level <= y_top - cap - .4 * TOWER_NUKI:
            # the tenons stick out past the posts, except toward another piece nearby (a ramp leaving the tower)
            near = lambda P: _beside(plan, P, hp * 2 + STAGE_CLEAR, level - 4., level + 4., k)
            ends = [(A['p'], -1.), (B['p'], 1.)]
            if near((A['p'] + B['p']) / 2):
                level += TOWER_NUKI
                continue
            tips = [P + sgn * (hp if near(P + sgn * hp * STAGE_TENON * u) else hp * STAGE_TENON) * u for P, sgn in ends]
            _timber(b, [(tips[0][0], level, tips[0][1]), (tips[1][0], level, tips[1][1])], n, hp * .6, hp * .75)
            for P in (A['p'], B['p']):
                _box(b, IRON, P + out * (hp + .06), u, out, hp * PLATE, .06, level - hp * PLATE, level + hp * PLATE)
            for (P, sgn), T in zip(ends, tips):
                if float(np.linalg.norm(T - P)) > hp * 1.5:
                    _box(b, KEYAKI, T + sgn * hp * el * u, u, n, hp * el, hp * ea, level - hp * eh, level + hp * eh)
            level += TOWER_NUKI
        _timber(b, [(A['p'][0], y_top - cap * .5, A['p'][1]), (B['p'][0], y_top - cap * .5, B['p'][1])], n, hp * .85,
                cap * .5)


def _surface_points(plan, k, centre, reach, y0, y1, step=.3):
    """Plan points (x, z) every `step` or closer over the faces of every piece but k within `reach` of centre that lie
    between y0 and y1 (a face reaching into the band counts whole)."""
    T = plan.T[(plan.owner != k)]
    keep = (np.linalg.norm(T[:, :, [0, 2]].mean(1) - centre, axis=1) < reach) & (T[:, :, 1].max(1) > y0) & \
        (T[:, :, 1].min(1) < y1)
    out = []
    for tri in T[keep]:
        P = tri[:, [0, 2]]
        m = max(1, int(math.ceil(max(np.linalg.norm(P[i] - P[(i + 1) % 3]) for i in range(3)) / step)))
        i, j = np.meshgrid(np.arange(m + 1), np.arange(m + 1))
        ok = (i + j) <= m
        a, bb = i[ok] / m, j[ok] / m
        out.append(P[0] + a[:, None] * (P[1] - P[0]) + bb[:, None] * (P[2] - P[0]))
    return np.concatenate(out) if out else np.zeros((0, 2))


def _rail_run(b, P, Q, y, ends=(True, True)):
    """A vermilion railing from P to Q (plan points) on a floor at y: posts about 2 m apart, two rails, the end posts
    (where `ends`) taller with black caps, as the tower's balcony railing."""
    d = Q - P
    L = float(np.linalg.norm(d))
    if L < .5:
        return
    d = d / L
    nrm = np.array([-d[1], d[0]])
    count = max(2, int(round(L / 2.)))
    for j in range(count + 1):
        p = P + d * L * j / count
        end = (j == 0 and ends[0]) or (j == count and ends[1])
        _box(b, VERMILION, p, d, nrm, .11, .11, y, y + RAIL + (.3 if end else 0.))
        if end:
            _cylinder(b, TILE, *p, y + RAIL + .3, y + RAIL + .55, .16, seg=8)
    for yy in (y + .45, y + RAIL - .1):
        _beam(b, VERMILION, (P + Q) / 2, d, nrm, L / 2, yy, yy + .12, .07)


def _shrine(b, plan, ground, k, c, n, t, half_face, other, floor, runways):
    """The shrine balcony off the deck's back side (n out of it, t along it), after concept C: a timber floor a step
    above the tower's rim, behind the deck's railing, as wide as the deck and its rim where it stays SHRINE_CLEAR from
    every other piece near its height, RUNWAY_CLEAR from every run-in and over no piece at all; a vermilion railing
    round its three outer sides; standing on its own row of keyaki posts on stone plinths down to the ground, tied by
    nuki to each other and back into the tower's frame. On it (shrine.py, b.models): the bell pavilion, the torii in
    front of it on its axis as the gateway from the deck (its posts on the balcony, off the deck and its rim), a stone
    lantern either side of the path between them and a row of nobori along the back. Sets b.shrine (its plan rectangle
    in the deck's frame, floor height and model count) and returns it, or None (no room: no shrine)."""
    from . import shrine
    u0, u1 = other + RIM, other + RIM + SHRINE_DEPTH
    v0, v1 = -(half_face + RIM), half_face + RIM
    y = floor + SHRINE_STEP
    height = y + max(shrine.footprint(s)[2] for s in shrine.MODELS) + 1.
    at = lambda u, v: c + u * n + v * t
    # what it must keep clear of, in the deck's frame (u along n, v along t): other pieces' surfaces from SHRINE_BELOW
    # under its floor to over its roofs (SHRINE_CLEAR), the run-ins (RUNWAY_CLEAR)
    near = _surface_points(plan, k, at((u0 + u1) / 2, 0.), SHRINE_DEPTH + half_face + 30., y - SHRINE_BELOW, height)
    run = [a + f * (e - a) for a, e in runways for f in np.linspace(0., 1., 1 + int(np.linalg.norm(e - a) / .25))]
    pts = np.array([*near, *run]).reshape(-1, 2) - c
    pts = np.stack([pts @ n, pts @ t], 1)
    need = np.r_[np.full(len(near), SHRINE_CLEAR), np.full(len(run), RUNWAY_CLEAR)]

    def gap(u0, u1, v0, v1):              # each point's plan distance from the balcony
        du = np.maximum(np.maximum(u0 - pts[:, 0], pts[:, 0] - u1), 0.)
        dv = np.maximum(np.maximum(v0 - pts[:, 1], pts[:, 1] - v1), 0.)
        return np.hypot(du, dv)

    def under(u0, u1, v0, v1):            # another piece below (or through) the balcony anywhere
        for u in np.linspace(u0, u1, int(math.ceil(u1 - u0)) + 1):
            for v in np.linspace(v0, v1, int(math.ceil(v1 - v0)) + 1):
                who, ys = plan.heights(*at(u, v))
                if ((who != k) & (ys < height)).any():
                    return (u, v)
        return None

    while v1 - v0 >= SHRINE_WIDE and u1 - u0 >= SHRINE_DEEP:
        d = gap(u0, u1, v0, v1)
        bad = np.flatnonzero(d < need)
        hit = under(u0, u1, v0, v1) if not len(bad) else None
        if not len(bad) and hit is None:
            break
        su, sv = pts[bad[np.argmin(d[bad] - need[bad])]] if len(bad) else hit
        if su > u1 or (hit is not None and su > u0 + SHRINE_DEEP):
            u1 -= .5                                          # beyond its back: a shallower balcony
        elif sv < (v0 + v1) / 2:
            v0 += .5                                          # beside (or in front of) one end: narrower there
        else:
            v1 -= .5
    else:
        b.shrine = None
        return None
    clear = gap(u0, u1, v0, v1)
    # the floor: boards over a dark timber frame, the railing round its outer sides
    um, vm, hu, hv = (u0 + u1) / 2, (v0 + v1) / 2, (u1 - u0) / 2, (v1 - v0) / 2
    _box(b, KEYAKI, at(um, vm), n, t, hu, hv, y - .15, y)
    _box(b, TIMBER, at(um, vm), n, t, hu - .1, hv - .1, y - SHRINE_SLAB, y - .15)
    _rail_run(b, at(u0 + .2, v0 + .2), at(u1 - .2, v0 + .2), y, (False, True))
    _rail_run(b, at(u1 - .2, v0 + .2), at(u1 - .2, v1 - .2), y, (False, False))
    _rail_run(b, at(u1 - .2, v1 - .2), at(u0 + .2, v1 - .2), y, (True, False))
    # its posts: a row under the outer edge, on stone plinths, capped by a beam under the floor; joists from each back
    # into the tower's top; nuki between them and back to the tower's posts every TOWER_NUKI
    hp = SHRINE_POST
    cap_top = y - SHRINE_SLAB
    tower_u = other - 1.6 * TOWER_POST                           # the tower's posts on this side (_tower_frame)
    posts = []
    for v in np.linspace(v0 + 1.3 * hp, v1 - 1.3 * hp, max(2, int(round((v1 - v0) / 7.)) + 1)):
        p = at(u1 - 1.3 * hp, v)
        g = _column(plan, ground, p, hp, cap_top)
        if g is not None:
            posts.append((p, v, g, min(cap_top - 2., g[1] + PLINTH_RISE[1])))
    for p, v, (g_lo, g_hi), foot in posts:
        _plinth(b, p, n, t, hp * PLINTH_WIDE, g_lo - SINK, min(g_hi, foot - .3), foot)
        _post(b, p, hp, foot - .2, cap_top - hp)
        _box(b, KEYAKI, p, n, t, hp * CAPITAL[0], hp * CAPITAL[0], cap_top - hp - hp * CAPITAL[1], cap_top - hp)
        q = at(tower_u, v)                                      # its joist back into the tower's top
        _timber(b, [(q[0], cap_top - hp * .6, q[1]), (p[0], cap_top - hp * .6, p[1])], t, hp * .55, hp * .6)
    if len(posts) >= 2:
        A, B = posts[0][0], posts[-1][0]
        _timber(b, [(A[0], cap_top - hp * .6, A[1]), (B[0], cap_top - hp * .6, B[1])], n, hp * .7, hp * .6)
        level = math.ceil((max(q[3] for q in posts) + .5 * TOWER_NUKI) / TOWER_NUKI) * TOWER_NUKI
        while level <= cap_top - .4 * TOWER_NUKI:
            _timber(b, [(A[0] - hp * 1.5 * t[0], level, A[1] - hp * 1.5 * t[1]),
                        (B[0] + hp * 1.5 * t[0], level, B[1] + hp * 1.5 * t[1])], n, hp * .6, hp * .75)
            for p, v, _, _ in posts:
                if abs(v) <= half_face - 1.6 * TOWER_POST + TOWER_POST:
                    q = at(tower_u, v)
                    _timber(b, [(q[0], level, q[1]), (p[0], level, p[1])], t, hp * .6, hp * .75)
            level += TOWER_NUKI
    # the shrine on it (shrine.py): models placed on the floor, their fronts toward the deck
    face = -n
    _, tw, _ = shrine.footprint('torii')
    pd, pw, _ = shrine.footprint('bell_pavilion')
    bd, bw, _ = shrine.footprint('nobori')
    # the torii is the gateway from the deck: on the pavilion's axis, just behind the railing, so a rider on the deck
    # sees the bell through it
    v_pav = min(max(vm, v0 + max(pw, tw) + .5), v1 - max(pw, tw) - .5)
    u_pav = u0 + SHRINE_FRONT + pd
    models = [('torii', at(u0 + SHRINE_TORII, v_pav), face), ('bell_pavilion', at(u_pav, v_pav), face)]
    for sgn in (-1, 1):                                    # the lanterns line the path from the torii to the bell
        models.append(('stone_lantern', at(u0 + (SHRINE_TORII + SHRINE_FRONT) / 2, v_pav + sgn * .65 * pw), face))
    count = max(2, int(round((v1 - v0 - 2.) / SHRINE_BANNERS)))
    for v in np.linspace(v0 + .6 + bw, v1 - .6 - bw, count):
        models.append(('nobori', at(u1 - .5 - bd, v), face))
    b.models = [(slug, (p[0], y, p[1]), f) for slug, p, f in models]
    # what it keeps clear of, as built: the nearest other piece's surface near its height and the nearest run-in
    # (plan metres from the balcony's outline, which every model stands inside), and the gap to the deck's edge
    nearest = lambda m: round(float(clear[m].min()), 2) if m.any() else None
    b.shrine = {'rect_uv': [round(float(x), 2) for x in (u0, u1, v0, v1)], 'floor_y': round(float(y), 3),
                'top_y': round(float(height - 1.), 2), 'models': len(b.models), 'posts': len(posts),
                'clear_m': nearest(need == SHRINE_CLEAR), 'runin_m': nearest(need == RUNWAY_CLEAR),
                'deck_gap_m': round(float(u0 - other), 2)}
    return b.shrine


# The Vert drop's timber stage (kakezukuri), after the approved Sunburst concept
# (assets/craterpark/concepts/editor/vertdrop-kiyomizu-overview.jpg): instead of an arcade, each of the line's ramps
# stands on its own grid of massive posts on stone plinths, tied by horizontal nuki that pass through the posts at
# even levels and stick out past the outer ones, with a cap beam following the ramp's underside. Nothing spans from one
# piece to the next, so the air between the vert kicker and the reverse catch (and under the mega air) stays open.
STAGE_LINES = {'L2'}          # the lines that stand on timber stages instead of stone arcades
STAGE_TYPES = {'rollin'}      # ...and the roll-ins, which leave the timber tower (the concept's ramp down from it)
KEYAKI = 'material_045'       # weathered keyaki, warm mid-brown: the stage's posts and beams
IRON = TILE                   # the black iron plates over the outer joints
STAGE_TALL = 120.             # members grow with the stage's height, up to this many metres of clearance
STAGE_BAY = (10., 22.)        # post spacing along the piece (low to tall stages)...
STAGE_SPAN = (16., 30.)       # ...and across it: posts in a few long rows, not a forest
STAGE_POST = (.9, 2.4)        # post half thickness: massive, as the concept's frames (about a twelfth of their height)
STAGE_NUKI = (5., 26.)        # height between tie-beam levels: three to five levels on any frame, as the concept's
STAGE_MIN = 2.                # a post shorter than this is left out: the ramp sits on (or in) the ground there
STAGE_CLEAR = 3.              # metres kept between a post (or its plinth) and any other piece beside it
STAGE_CAP = 1.6               # the cap beam's height under the ramp, in post half thicknesses...
STAGE_EDGE = 2.4              # ...deeper along the outer frames, the heavy edge beam under the ramp's sides
STAGE_TENON = 2.6             # a nuki runs this many post half thicknesses past the posts it ties
PLATE = .8                    # an iron plate's half size, in post half thicknesses
STAGE_TRUSS = (3., 9.)        # a truss's depth under the ramp, where another piece runs underneath
STAGE_REACH = 80.             # metres beyond the edge searched for clear ground to stand a truss's outrigger post
STAGE_BACK_RUN, STAGE_BACK_STEEP = 15., 60.   # a piece this steep (deg) within this far of its start is a catch wall
PLINTH_RISE = (2.5, 9.)       # the stone plinth stands this far above the highest ground under it...
PLINTH_WIDE = 2.2             # ...is this many post half thicknesses wide at its top...
PLINTH_COURSES = 3            # ...in this many rough courses, each stepping out this much of its width below
PLINTH_STEP = .12
CAPITAL = (1.3, 1.1)          # a block capping each post under the beams: half width and height, in post halves
TWIN = 2.3                    # a frame's corner posts are doubled, the second this many post halves inward
END_BLOCK = (.75, .9, .35)    # the square block on a nuki's outer end: half width, half height, length (post halves)


def _lerp(pair, f):
    return pair[0] + (pair[1] - pair[0]) * f


def _post(b, c, half, y0, y1):
    """A squared keyaki post with chamfered corners."""
    ch = .22 * half
    ring = lambda y: np.array([(c[0] + p, y, c[1] + q) for p, q in
                               ((half, half - ch), (half - ch, half), (ch - half, half), (-half, half - ch),
                                (-half, ch - half), (ch - half, -half), (half - ch, -half), (half, ch - half))])
    _rings(b, KEYAKI, [ring(y0), ring(y1)])


def _plinth(b, c, fwd, acr, half, y0, yg, y1):
    """A rough stone plinth (the volcano's grey rock) from y0 (sunk) to y1, its courses above the ground yg each stepping
    in from the one below."""
    levels = [y0] + [yg + (y1 - yg) * k / PLINTH_COURSES for k in range(1, PLINTH_COURSES + 1)]
    for k in range(PLINTH_COURSES):
        w = half * (1 + PLINTH_STEP * (PLINTH_COURSES - 1 - k))
        r = [_rand(c[0], c[1], k, i) - .5 for i in range(3)]       # rough-laid: each course a little off square
        q = c + .06 * half * (r[0] * fwd + r[1] * acr)
        _box(b, ROCK, q, fwd, acr, w * (1 + .05 * r[2]), w * (1 - .05 * r[2]), levels[k], levels[k + 1], yaw=.04 * r[1])


def _timber(b, pts, n, depth, height):
    """A beam through centre points (each (x, y, z)), `depth` thick (half) along the plan direction n, `height` tall
    (half): sections are vertical, so it follows a sloped or curved line."""
    _rings(b, KEYAKI, [np.array([(p[0] + q * depth * n[0], p[1] + r * height, p[2] + q * depth * n[1])
                                 for q, r in ((-1, -1), (1, -1), (1, 1), (-1, 1))]) for p in pts])


def _beside(plan, p, r, y0, y1, piece=-1):
    """Whether any piece other than `piece` has a surface between y0 and y1 within r (plan) of p."""
    for ang in np.linspace(0, 2 * np.pi, 24, endpoint=False):
        for f in (.35, .7, 1.):
            who, y = plan.heights(*(p + f * r * np.array([math.cos(ang), math.sin(ang)])))
            if ((who != piece) & (y > y0) & (y < y1)).any():
                return True
    return False


def _column(plan, ground, p, w, top):
    """(lowest, highest) ground round a post standing at p up to `top` without meeting any piece, nor standing within
    STAGE_CLEAR of one beside it, else None."""
    r, g = w * PLINTH_WIDE * (1 + PLINTH_STEP * (PLINTH_COURSES - 1)), []
    for q in (p, p + (r, r), p + (-r, r), p + (-r, -r), p + (r, -r)):
        gg = float(ground(*q))
        _, y = plan.heights(*q)
        if ((y > gg - SINK - 1.) & (y < top + 1.)).any():
            return None
        g.append(gg)
    if _beside(plan, p, r * 1.42 + STAGE_CLEAR, min(g) - SINK - 1., top + 1.):
        return None
    return (min(g), max(g)) if top - max(g) >= STAGE_MIN else None


def _truss_room(plan, piece, chain, half):
    """How far a truss along a chain of nodes (each with its plan point p and ramp top) may hang under the tops and stay
    OVER clear of every other piece's surface below them, its members `half` wide each side of the chain's line (m)."""
    room = np.inf
    for A, B in zip(chain, chain[1:]):
        d = B['p'] - A['p']
        L = float(np.linalg.norm(d))
        n = np.array([-d[1], d[0]]) / max(L, 1e-6)
        for s in np.linspace(0., 1., max(2, int(L / 1.) + 1)):
            p, top = A['p'] + s * d, A['top'] + s * (B['top'] - A['top'])
            for q in (-half, 0., half):
                who, y = plan.heights(*(p + q * n))
                y = y[(who != piece) & (y < top)]
                if len(y):
                    room = min(room, top - float(y.max()) - OVER)
    return room


def stage(b, plan, ground, piece, stations):
    """The timber stage under one piece: (posts, beams, metres). Where another piece runs underneath, a timber truss
    under the ramp carries it across to the nearest posts beside it: a post of the grid, or an outrigger standing on
    clear ground outside the pieces below. The truss keeps OVER over the pieces below it, made shallower where they
    come close; where even the shallowest truss would not, that stretch of the stage is left out."""
    got = _samples(stations)
    if got is None:
        return 0, 0, 0.
    t, x, z, h, half = got
    clear = []
    for i in range(0, len(t), 4):
        sp = plan.span(x[i], z[i], piece)
        if sp is not None:
            clear.append(sp[0] - float(ground(x[i], z[i])))
    if not clear:
        return 0, 0, 0.
    catch = max(abs(st['a']) for st in stations if st['d'] - stations[0]['d'] < STAGE_BACK_RUN) > STAGE_BACK_STEEP
    if catch:                                                  # its back frame stands up to the lip
        clear.append(stations[0]['y'] - float(ground(stations[0]['x'], stations[0]['z'])))
    f = float(np.clip(max(clear) / STAGE_TALL, 0., 1.))     # members sized for the stage's tallest frame
    bay, w, nuki, depth = _lerp(STAGE_BAY, f), _lerp(STAGE_POST, f), _lerp(STAGE_NUKI, f), _lerp(STAGE_TRUSS, f)
    rise, cap = _lerp(PLINTH_RISE, f), w * STAGE_CAP
    end = w * max(STAGE_TENON + 2 * END_BLOCK[2], PLINTH_WIDE * (1 + PLINTH_STEP * (PLINTH_COURSES - 1))) + .3   # all within the piece
    if t[-1] - t[0] < 2 * end + 1.:
        return 0, 0, 0.
    rows = np.linspace(t[0] + end, t[-1] - end, max(1, round((t[-1] - t[0] - 2 * end) / bay)) + 1)
    cols = max(1, math.ceil((2 * float(half.min()) - 2 * end) / _lerp(STAGE_SPAN, f)))

    def standing(p, top, g_lo, g_hi):
        return dict(p=p, top=top, base=g_lo - SINK, ground=g_hi, foot=min(top - 1., g_hi + rise), fwd=fwd, acr=acr)

    # the post grid: grid[i][j] a standing post, a node hung from a truss ('hung') or None, and the outriggers
    grid, outs = [], []
    for s in rows:
        hh = float(np.interp(s, t, h))
        c = np.array([np.interp(s, t, x), np.interp(s, t, z)])
        fwd, acr = np.array([math.cos(hh), math.sin(hh)]), np.array([-math.sin(hh), math.cos(hh)])
        reach = float(np.interp(s, t, half)) - end
        row = []
        for v in np.linspace(-reach, reach, cols + 1):
            p = c + v * acr
            corners = [p + a * w * fwd + q * w * acr for a, q in ((0, 0), (1, 1), (-1, 1), (-1, -1), (1, -1))]
            spans = [plan.span(*q, piece) for q in corners]
            if any(sp is None for sp in spans):
                row.append(None)                      # off the piece
                continue
            g = [float(ground(*q)) for q in corners]
            top = min(sp[0] for sp in spans) + EMBED
            if max(sp[1] for sp in spans) > min(g) - SINK:
                row.append(dict(p=p, top=top, base=top - depth, foot=top - depth, hung=True))
            elif top - max(g) >= STAGE_MIN and not _beside(plan, p, w * PLINTH_WIDE * 1.8 + STAGE_CLEAR,
                                                            min(g) - SINK - 1., top - 1., piece):
                row.append(standing(p, top, min(g), max(g)))
            else:
                row.append(None)                      # the ramp sits on (or in) the ground here
        # every run of hung nodes needs a post at each end, else it is left out
        out = {}
        j = 0
        while j < len(row):
            if not (row[j] and row[j].get('hung')):
                j += 1
                continue
            e = j
            while e + 1 < len(row) and row[e + 1] and row[e + 1].get('hung'):
                e += 1
            ends, found = [], {}
            for side, k, edge in ((-1, j - 1, row[j]), (1, e + 1, row[e])):
                if 0 <= k < len(row):
                    ends.append(row[k] if row[k] and not row[k].get('hung') else None)
                    continue
                post = None
                for v in np.arange(reach + 3 * w + 1., reach + STAGE_REACH, 2.):
                    p = c + side * v * acr
                    g = _column(plan, ground, p, w, edge['top'])
                    if g is not None:
                        post = found[side] = standing(p, edge['top'], *g)
                        break
                ends.append(post)
            # the truss hangs no deeper than the pieces below it leave room for (OVER over their surfaces), and at least
            # under the deepest beam it carries; with less room the run is left out, never through the piece below
            # (a run missing an end keeps an outrigger found for its other end, as before; one without the room keeps none)
            fit = None
            if ends[0] is not None and ends[1] is not None:
                chain = [ends[0]] + row[j:e + 1] + [ends[1]]
                fit = min(depth, _truss_room(plan, piece, chain, w * .75) - w * .7)
                if fit < w * (STAGE_EDGE + .7):
                    fit = None
            else:
                out.update(found)
            if fit is None:
                for k in range(j, e + 1):
                    row[k] = None
            else:
                out.update(found)
                row[j:e + 1] = [dict(n, truss=(ends[0], ends[1]), depth=fit, base=n['top'] - fit, foot=n['top'] - fit)
                                for n in row[j:e + 1]]
            j = e + 1
        grid.append(row)
        outs.append(out)
    # a catch wall (the piece drops away steeply from its start) gets a row of posts behind its top, up to its lip;
    # never behind a piece's end, where the rider flies off
    if catch:
        h0 = math.radians(stations[0]['h'])
        fwd, acr = np.array([math.cos(h0), math.sin(h0)]), np.array([-math.sin(h0), math.cos(h0)])
        c = np.array([stations[0]['x'], stations[0]['z']]) - (end + w * PLINTH_WIDE * (1 + PLINTH_STEP * (PLINTH_COURSES - 1))) * fwd
        top, reach, back = stations[0]['y'] + EMBED, float(half[0]) - end, []
        for v in np.linspace(-reach, reach, cols + 1):
            g = _column(plan, ground, c + v * acr, w, top)
            back.append(None if g is None else standing(c + v * acr, top, *g))
        if any(back):
            grid.insert(0, back)
            outs.insert(0, {})
            rows = np.concatenate([[rows[0] - bay], rows])
    # as the concept, the frames stand along the ramp's edges and across its two ends, not under the whole ramp: the
    # posts between them are left out (except where a truss lands), and a girder crosses under the ramp from edge to edge
    keep = {id(e) for row in grid for q in row if q and q.get('hung') for e in q['truss']}
    for row in grid[1:-1]:
        for j in range(1, len(row) - 1):
            if row[j] and not row[j].get('hung') and id(row[j]) not in keep:
                row[j] = None
    posts = beams = 0
    standing_posts = [q for row in grid for q in row if q and not q.get('hung')] + [q for o in outs for q in o.values()]
    corners = {id(grid[i][j]): 1 if i == 0 else -1 for i in (0, len(grid) - 1) for j in (0, len(grid[i]) - 1)
               if grid[i][j] and not grid[i][j].get('hung')}
    for q in standing_posts:
        here = [q['p']]
        if id(q) in corners:                          # the corner posts are doubled, as the concept's
            p2 = q['p'] + corners[id(q)] * TWIN * w * q['fwd']
            if _column(plan, ground, p2, w, q['top']) is not None:
                here.append(p2)
        for p in here:
            _plinth(b, p, q['fwd'], q['acr'], w * PLINTH_WIDE, q['base'], min(q['ground'], q['foot'] - .3), q['foot'])
            _post(b, p, w, q['foot'] - .2, q['top'] - cap * .5)
            ca, ch = CAPITAL
            _box(b, KEYAKI, p, q['fwd'], q['acr'], w * ca, w * ca, q['top'] - cap - w * ch, q['top'] - cap * .5)
            posts += 1

    every = [q['p'] for row in grid for q in row if q] + [q['p'] for o in outs for q in o.values()]
    middle = np.mean(every, 0) if every else np.zeros(2)

    def tie(A, B, outer, ties=True):
        """Nuki between two neighbouring posts at every level both stand through, with iron plates over the joints on
        an outer frame's face, and the cap beam over them (the deep edge beam on an outer frame)."""
        nonlocal beams
        d = B['p'] - A['p']
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            return
        u = d / L
        n = np.array([-u[1], u[0]])
        out = n if float(n @ ((A['p'] + B['p']) / 2 - middle)) >= 0 else -n
        top = w * STAGE_EDGE if outer else cap
        lo, hi = max(A['foot'], B['foot']) + .5 * nuki, min(A['top'], B['top']) - top - .6 * nuki
        level, ext = math.ceil(lo / nuki) * nuki, w * STAGE_TENON
        while ties and level <= hi:
            a, e = A['p'] - ext * u, B['p'] + ext * u
            _timber(b, [(a[0], level, a[1]), (e[0], level, e[1])], n, w * .6, w * .75)
            beams += 1
            if outer:
                for P in (A['p'], B['p']):
                    _box(b, IRON, P + out * (w + .06), u, out, w * PLATE, .06, level - w * PLATE, level + w * PLATE)
                ea, eh, el = END_BLOCK
                for P, sgn in ((a, -1.), (e, 1.)):
                    _box(b, KEYAKI, P + sgn * w * el * u, u, n, w * el, w * ea, level - w * eh, level + w * eh)
            level += nuki
        # the cap beam hugs the ramp's underside between the two posts (level between them off the piece): its top is
        # shaped to the underside across its width too, so under a steep ramp it bears all across instead of stopping
        # short of the ramp's upper side
        rings = []
        for s in np.linspace(0., 1., max(2, int(L / 1.5) + 1)):
            p = A['p'] + s * d
            sps = [plan.span(*(p + q * w * .85 * n), piece) for q in (-1., 0., 1.)]
            if all(sp is not None for sp in sps):
                tops = [sp[0] + EMBED for sp in sps]
            else:
                ys = [sp[0] for sp in sps if sp is not None]
                tops = [min(ys) + EMBED if ys else A['top'] + s * (B['top'] - A['top'])] * 3
            at = lambda q, y: (p[0] + q * w * .85 * n[0], y, p[1] + q * w * .85 * n[1])
            low = min(tops) - top
            rings.append(np.array([at(-1., low), at(1., low), at(1., tops[2]), at(0., tops[1]), at(-1., tops[0])]))
        _rings(b, KEYAKI, rings)
        beams += 1

    def truss(chain, depth):
        """A truss's bottom chord, verticals and diagonals under the cap beams along a chain of nodes, `depth` under
        the ramp (its room over the pieces below, _truss_room)."""
        nonlocal beams
        for a, (A, B) in enumerate(zip(chain, chain[1:])):
            d = B['p'] - A['p']
            n = np.array([-d[1], d[0]]) / max(float(np.linalg.norm(d)), 1e-6)
            _timber(b, [(A['p'][0], A['top'] - depth, A['p'][1]), (B['p'][0], B['top'] - depth, B['p'][1])], n,
                    w * .7, w * .7)
            lo, hi = (A, B) if a % 2 == 0 else (B, A)
            _timber(b, [(lo['p'][0], lo['top'] - depth, lo['p'][1]), (hi['p'][0], hi['top'] - cap, hi['p'][1])], n,
                    w * .5, w * .55)
            beams += 2
        for q in chain[1:-1]:
            _post(b, q['p'], w * .75, q['top'] - depth - w * .7, q['top'] - cap * .5)
            beams += 1

    for i, row in enumerate(grid):
        left, right = outs[i].get(-1), outs[i].get(1)
        ordered = ([left] if left else []) + row + ([right] if right else [])
        for A, B in zip(ordered, ordered[1:]):
            if A is not None and B is not None:
                tie(A, B, i in (0, len(grid) - 1))
        if 0 < i < len(grid) - 1 and row[0] and row[-1] and not any(row[1:-1]):
            tie(row[0], row[-1], False, ties=False)
        j = 0
        while j < len(row):
            q = row[j]
            if q and q.get('hung'):
                e = j
                while e + 1 < len(row) and row[e + 1] and row[e + 1].get('hung'):
                    e += 1
                truss([q['truss'][0]] + row[j:e + 1] + [q['truss'][1]], q['depth'])
                j = e + 1
            else:
                j += 1
        if i + 1 < len(grid):
            for j, q in enumerate(row):
                if q is not None and grid[i + 1][j] is not None:
                    tie(q, grid[i + 1][j], j in (0, len(row) - 1))
            for side in (-1, 1):
                if side in outs[i] and side in outs[i + 1]:
                    tie(outs[i][side], outs[i + 1][side], True)
    return posts, beams, (float(rows[-1] - rows[0]) if posts else 0.)


def open_sides(piece, pieces, k, halves=None, types=None):
    """The sides of a deck (0 +fwd, 1 -fwd, 2 +acr, 3 -acr) a ramp leaves from at its top (or arrives at): where the
    ramp's first or last station stands on the deck's edge. No railing there, and the torii over the first. `halves`, if
    given, gets each such side's widest ramp half width (floor, walls and coping)."""
    c, fwd, acr, a, w, top = _rect(np.asarray(piece.mesh.V, 'f8'))
    out = set()
    for j, other in enumerate(pieces):
        stations = other.metadata.get('stations') or []
        if j == k or not stations or (types and other.metadata['type'] not in types):
            continue
        for st in (stations[0], stations[-1]):
            d = np.array([st['x'], st['z']]) - c
            u, v = d @ fwd, d @ acr
            if abs(st['y'] - top) > 1.5 or abs(u) > a + 2. or abs(v) > w + 2.:
                continue
            side = int(np.argmax([u / a, -u / a, v / w, -v / w]))
            out.add(side)
            if halves is not None:
                halves[side] = max(halves.get(side, 0.), _outer_half(st))
    return out


def ledge_sides(piece, plan, k):
    """The sides of a deck another piece adjoins at its own height (a takeoff ledge, a ramp's top), probed just outside
    each edge: no railing nor shrine there."""
    c, fwd, acr, a, w, top = _rect(np.asarray(piece.mesh.V, 'f8'))
    out = set()
    for side, (n, t, half_face, other) in enumerate(((fwd, acr, w, a), (-fwd, acr, w, a), (acr, fwd, a, w),
                                                     (-acr, fwd, a, w))):
        for u in np.linspace(-half_face + .5, half_face - .5, 9):
            who, y = plan.heights(*(c + (other + 1.) * n + u * t))
            if ((who != k) & (np.abs(y - top) < 1.5)).any():
                out.add(side)
                break
    return out


def _runways(piece, pieces, k):
    """The run-ins across a deck: for every other piece whose first station stands on it (a roll-in's mouth, an edge
    the rider runs off), the plan segment RUNWAY m back from that station along its heading."""
    V = np.asarray(piece.mesh.V, 'f8')
    top, lo, hi = V[:, 1].max(), V[:, [0, 2]].min(0) - 3., V[:, [0, 2]].max(0) + 3.
    out = []
    for j, other in enumerate(pieces):
        st = other.metadata.get('stations') or []
        if j == k or not st:
            continue
        s0 = st[0]
        p = np.array([s0['x'], s0['z']], 'f8')
        if abs(s0['y'] - top) < 2. and (p >= lo).all() and (p <= hi).all():
            h = np.radians(float(s0['h']))
            out.append((p - RUNWAY * np.array([np.cos(h), np.sin(h)]), p))
    return out


def build(pieces, heights, grid):
    """The supports for the kept editor pieces (bridge Pieces), as dsl Mesh parts, and a summary."""
    ground = Ground(heights, grid)
    plan = Plan(pieces)
    out, summary = [], {'piers': 0, 'arches': 0, 'posts': 0, 'beams': 0, 'metres': 0., 'boulders': 0, 'towers': [], 'pieces': {},
                    'shrines': {}}
    for k, piece in enumerate(pieces):
        meta = piece.metadata
        if meta['type'] == 'deck' and (meta.get('params') or {}).get('solid'):
            b = Builder()
            halves = {}
            drops = open_sides(piece, pieces, k, halves, types={'rollin'})     # the torii stands over a roll-in only
            gates = open_sides(piece, pieces, k)
            runways = _runways(piece, pieces, k)
            rocks = tower(b, plan, ground, piece, gates | drops | ledge_sides(piece, plan, k), k, gates=drops, runways=runways,
                          halves=halves)
            if rocks is not None:
                out += b.meshes(f"{meta['id']}_tower")
                if b.models:
                    from . import shrine
                    out += [shrine.part(shrine.place(*m), f"{meta['id']}_shrine") for m in b.models]
                    summary['shrines'][meta['id']] = b.shrine
                summary['boulders'] += rocks
                summary['towers'].append(meta['id'])
                summary['pieces'][meta['id']] = 'tower'
            continue
        if meta['type'] in ('bowl', 'deck', 'rail') or not meta.get('stations'):
            continue
        b = Builder()
        if meta.get('line') in STAGE_LINES or meta['type'] in STAGE_TYPES:
            posts, beams, metres = stage(b, plan, ground, k, meta['stations'])
            if posts:
                out += b.meshes(f"{meta['id']}_supports")
                summary['posts'] += posts
                summary['beams'] += beams
                summary['metres'] += round(metres, 1)
                summary['pieces'][meta['id']] = 'stage'
            continue
        piers, arches, metres, rocks = arcade(b, plan, ground, k, meta['stations'])
        if not metres:
            continue
        out += b.meshes(f"{meta['id']}_supports")
        summary['piers'] += piers
        summary['arches'] += arches
        summary['boulders'] += rocks
        summary['metres'] += round(metres, 1)
        summary['pieces'][meta['id']] = 'viaduct'
    summary['metres'] = round(summary['metres'], 1)
    return out, summary
