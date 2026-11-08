"""Crater Park v2 primitives (plan/pipeline.md section 4): features built on A's `sweep.sweep` riding sheets, closed
into solids with thick walls, flat caps, banks and a buried base (solids.py), each with its seams and rails.

Every primitive returns a `Built` (mesh: dsl.Mesh, rails: [dsl.Rail], checks: [dict]) whose mesh is watertight on its
welded topology (base faces included) and has no folded face; both are checked before it is returned.

Sides of a feature, where its edge meets lower ground (`Side`):
- `wall`: a vertical wall down to the ground: the solid's own side, as thick as the feature is wide;
- `curb`: a thick wall standing `height` over the riding edge with a flat cap `width` (>= 0.30 m) wide;
- `bank`: a slope at `degrees` down to the ground (role side: it collides and can be ridden, but it is not the
  designed line, so it is meshed coarsely and kept out of the riding checks);
- `flush`: the ground or a deck continues at the riding edge (the wall is only a buried closing face);
- `ground` (on_ground only): no side at all: the landform meets the riding edge itself (a roll-in carved into the
  tower's mound).
- `bowl`: a curved transition wall rising from the riding edge (a circular arc of `radius` up to `height`, as a
  snake run's or half-pipe's), so a rider drifting sideways carves up it and comes back, then a flat cap `width` wide,
  then `outer`: 'ground' (on_ground: the landform meets the cap), 'wall' (down to the ground) or 'bank'. The wall
  grows from zero over `fade` metres at each end (a ramp fades it at a 'wall' end: to zero at a kicker's lip, from zero
  at a landing's knuckle; a tower roll-in fades it from its deck), and is full height at a 'flush' end, so the next
  run's walls continue it exactly.
Wherever the riding edge stands less than FLUSH over the ground, its wall is buried (role base).

Profiles are A's `profile.Profile` (('line', L) is L along the slope). `from_additions` converts the r4 RAMPS table's
profiles, whose ('line', L) is a horizontal run, so the ridden dimensions carry over exactly.
"""
import itertools
import math
from dataclasses import dataclass, field, replace

import numpy as np

from . import coping as coping_mod
from . import dsl, solids
from .curves import Arc, Curve, Line
from .profile import Profile
from .rails import edge_rail
from .sweep import _stations, sweep

FLUSH = .05         # metres: a riding edge this close over the ground meets it flush (no visible wall)
FOOT = .01          # metres a wall's foot lies under a flush edge at least (so the wall never has zero height)
BURY = .3           # metres the base lies under the lowest ground or riding point
MIN_WALL = .30      # metres: a wall or cap's least thickness (I5)
TESS = dsl.Tess(.002, 2.0, 2.8)   # riding: as RIDING_TESS, but quads of 2.8 m keep their diagonals under 4 m (V9)
WALL_ROW = 2.2      # metres between a wall's rows down it at most
BOWL_HEIGHT = 3.    # metres: a bowl side's wall over the riding edge at full height
BOWL_RADIUS = 3.5   # metres: its transition's radius
BOWL_CAP = 1.       # metres: its flat cap's width
BOWL_FADE = 15.     # metres over which it grows from zero at a faded end (a cosine ease of its whole section)
BOWL_TURN = 1.2     # degrees its rows turn along a fade between stations at most (with the diagonals, under 2)
BOWL_STEP = 1.5     # degrees across a shoulder; leave room for its longitudinal pitch under the 2 degree facet limit


@dataclass
class Side:
    kind: str = 'wall'          # wall, curb, bank, flush, ground, bowl
    width: float = None         # curb: its cap's width (.4); bowl: its flat cap's width (BOWL_CAP)
    height: float = None        # curb: how far it stands over the riding edge (.3); bowl: its wall (BOWL_HEIGHT)
    degrees: float = 30.        # bank (and a bowl's 'bank' outer): its slope
    material: str = dsl.CONCRETE
    radius: float = BOWL_RADIUS     # bowl: its transition's radius
    fade: tuple = None              # bowl: metres it grows from zero over at (start, end); None: the ramp decides
    outer: str = None               # bowl: past its cap, 'ground', 'wall' or 'bank' (None: ground on the ground)
    fade_power: float = 1.           # a merge uses 3: height vanishes as distance^6, reach as distance^3
    shape: object = None            # optional (edge positions) -> (full heights, radii), before endpoint fades

    def __post_init__(self):
        if self.kind not in ('wall', 'curb', 'bank', 'flush', 'ground', 'bowl'):
            raise ValueError(f'unknown side {self.kind!r}')
        if self.width is None:
            self.width = BOWL_CAP if self.kind == 'bowl' else .4
        if self.height is None:
            self.height = BOWL_HEIGHT if self.kind == 'bowl' else .3
        if self.kind == 'curb' and self.width < MIN_WALL:
            raise ValueError(f'a curb cap must be at least {MIN_WALL} m wide (I5), not {self.width}')
        if self.kind == 'bowl':
            if self.width < MIN_WALL:
                raise ValueError(f'a bowl side\'s cap must be at least {MIN_WALL} m wide (I5), not {self.width}')
            if not (self.height > 0 and self.radius > 0):
                raise ValueError('a bowl side needs a positive height and radius')
            if self.outer not in (None, 'ground', 'wall', 'bank'):
                raise ValueError(f'a bowl side\'s outer is ground, wall or bank, not {self.outer!r}')
            if not math.isfinite(self.fade_power) or self.fade_power < 1.:
                raise ValueError('a bowl fade power must be finite and at least one')


@dataclass
class Built:
    mesh: dsl.Mesh
    rails: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    foot: list = field(default_factory=list)     # on_ground: the loops (k, 3) where the solid meets the ground

    @staticmethod
    def concat(built):
        built = [b for b in built if b is not None]
        return Built(dsl.Mesh.concat([b.mesh for b in built]), [r for b in built for r in b.rails],
                     [c for b in built for c in b.checks], [f for b in built for f in b.foot])


def one_feature(mesh, feature):
    """The mesh with every face under the one feature name (its parts' names merged)."""
    mesh.features = (feature,)
    mesh.feature[:] = 0
    return mesh


def as_side(s):
    return s if isinstance(s, Side) else Side(s)


def _faded(side, ends):
    """A bowl side with no fade given fades at the ramp's 'wall' ends (a kicker's lip, a landing's knuckle)."""
    if side.kind != 'bowl' or side.fade is not None:
        return side
    return replace(side, fade=tuple(BOWL_FADE if as_side(e).kind == 'wall' else 0. for e in ends))


def as_ground(g):
    """A ground height function of plan points (x, z) arrays, from a float or a callable."""
    if callable(g):
        return g
    y = float(g)
    return lambda x, z: np.full(np.shape(x), y)


def from_additions(y, degrees, parts, **attrs):
    """A Profile from an r4 RAMPS profile (y, degrees, parts), whose ('line', L) runs L horizontally."""
    a, out = float(degrees), []
    for p in parts:
        extra = [p[-1]] if isinstance(p[-1], dict) else []
        core = p[:-1] if extra else p
        if core[0] == 'line':
            out.append(('line', core[1] / math.cos(math.radians(a)), *extra))
        else:
            out.append(tuple(core) + tuple(extra))
            if core[0] in ('arc', 'corner'):
                a = float(core[-1])
    return Profile(out, start=(0., y), degrees=degrees, **attrs)


def tagged(parts, tag, which=None):
    """The profile parts with `tag` set on the parts at indices `which` (all if None), keeping other attributes."""
    out = []
    for i, p in enumerate(parts):
        a = dict(p[-1]) if isinstance(p[-1], dict) else {}
        core = p[:-1] if isinstance(p[-1], dict) else p
        if which is None or i in which or (i - len(parts)) in which:
            a.setdefault('tag', tag)
        out.append(tuple(core) + ((a,) if a else ()))
    return out


def _dedupe(ids, V):
    """The vertex ids of a seam with consecutive duplicate positions (crease twins) dropped."""
    ids = np.asarray(ids)
    keep = np.r_[True, np.linalg.norm(np.diff(V[ids], axis=0), axis=1) > 1e-9]
    return ids[keep]


FLANK_ROW = 2.2     # metres between a bank flank's rows down it at most
PINCH = .12         # metres: a flank shorter than this is none (the riding edge meets the ground there)
INSIDE = 2.         # metres a flank stops short of its edge's centre of turn


def _flank_extent(E, D, side, g, gap):
    """Each station's flank length down the slope from the riding edge E (k, 3) to the ground, clipped on the inside
    of a turn to the edge's turn radius less INSIDE (a flank must never fold; it then ends in a short wall)."""
    a = math.radians(side.degrees)
    drop = E[:, 1] - gap - g(E[:, 0], E[:, 2])
    lo = np.zeros(len(E)); hi = np.full(len(E), max(float(drop.max()), 0.) / math.sin(a) + 1.)
    for _ in range(50):                                      # bisection: the slope meets the (sloping) ground
        mid = (lo + hi) / 2
        q = E + (mid * math.cos(a))[:, None] * D
        up = E[:, 1] - mid * math.sin(a) - gap - g(q[:, 0], q[:, 2]) > 0
        lo = np.where(up, mid, lo); hi = np.where(up, hi, mid)
    sig = np.where(drop > 0, (lo + hi) / 2, 0.)
    k = _edge_curvature(E, D)
    reach = np.where(k > 1e-9, np.maximum(1 / np.maximum(k, 1e-9) - INSIDE, 0.) / math.cos(a), np.inf)
    sig = np.minimum(sig, reach)
    sig[sig < PINCH] = 0.
    return sig


def _flank_mesh(E, D, side, g, gap, feature):
    """A bank flank on an open path, as a constrained Delaunay mesh in its own (u along the riding edge, sigma down
    the slope) domain: the edge on top, each station's foot below, rows FLANK_ROW apart at the stations' u, each row
    ending a half row short of the foot, so a flank whose length changes along the ramp never fans or thins. UVs: u
    the arc length along each row, v sigma. Returns (mesh or None, foot (k, 3), end columns {0: [...], -1: [...]})."""
    from .cdt import CDTError, triangulate
    a = math.radians(side.degrees)
    Y = np.array([0., 1., 0.])
    k = len(E)
    sig_f = _flank_extent(E, D, side, g, gap)

    def place(uu, ss):
        Eu = np.stack([np.interp(uu, u, E[:, c]) for c in range(3)], 1)
        Du = np.stack([np.interp(uu, u, D[:, c]) for c in range(3)], 1)
        Du /= np.maximum(np.linalg.norm(Du, axis=1, keepdims=True), 1e-300)
        return Eu + (ss * math.cos(a))[:, None] * Du - (ss * math.sin(a))[:, None] * Y
    u = np.r_[0., np.cumsum(np.linalg.norm(np.diff(E, axis=0), axis=1))]
    foot = place(u, sig_f)
    foot[sig_f == 0] = E[sig_f == 0]
    lim = np.minimum.reduce([sig_f, np.r_[sig_f[1:], sig_f[-1]], np.r_[sig_f[0], sig_f[:-1]]])

    def column(limit):
        n = int(limit // FLANK_ROW)
        lv = FLANK_ROW * np.arange(1, n + 1)
        return lv[lv < limit - FLANK_ROW / 2]
    ends = {0: column(sig_f[0]), -1: column(sig_f[-1])}
    run = np.flatnonzero(sig_f > 0)
    if not len(run):
        return None, foot, {0: [], -1: []}
    parts = []
    for r in np.split(run, np.flatnonzero(np.diff(run) > 1) + 1):
        i0, i1 = int(r[0]), int(r[-1])
        top = [(u[i], 0.) for i in range(i0, i1 + 1)]
        left = [(u[i0 - 1], 0.)] if i0 > 0 else []
        if i1 < k - 1:
            right = [(u[i1 + 1], 0.)]
            hi = i1
        else:
            right = [(u[-1], x) for x in ends[-1]] + [(u[-1], sig_f[-1])]
            hi = k - 2
        lo = i0 if i0 > 0 else 1
        feet = [(u[i], sig_f[i]) for i in range(hi, lo - 1, -1)]
        if i0 == 0:
            feet += [(u[0], sig_f[0])] + [(u[0], x) for x in ends[0][::-1]]
        poly = np.asarray(left + top + right + feet)
        inner = [(u[i], x) for i in range(max(i0, 1), min(i1, k - 2) + 1) for x in column(lim[i])]
        P2 = np.concatenate([poly, np.asarray(inner).reshape(-1, 2)])
        F = None
        for sc in (1., .5, 2., .77, 1.3):           # the CDT's point location can fail; an affine stretch avoids it
            try:
                F = triangulate(P2 * [sc, 1.], [np.arange(len(poly))])
                break
            except CDTError:
                continue
        if F is None:
            P2 = poly; F = solids.ear_clip(poly)
        V = place(P2[:, 0], P2[:, 1])
        # u: the arc length along each row (the iso-sigma curve through the vertex), v: sigma
        rows = place(np.repeat(u[None], len(P2), 0).ravel(), np.repeat(P2[:, 1], k)).reshape(len(P2), k, 3)
        seg = np.r_[np.zeros((len(P2), 1)).T, np.cumsum(np.linalg.norm(np.diff(rows, axis=1), axis=2), 1).T].T
        along = np.array([np.interp(P2[j, 0], u, seg[j]) for j in range(len(P2))])
        t = V[F]
        F = F[np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) > 1e-12]
        uc = P2[F].mean(1)[:, 0]
        F = solids.orient(F, V, np.stack([np.interp(uc, u, D[:, c]) for c in range(3)], 1) + Y)
        t = V[F]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        if (n[:, 1] <= 0).any():
            raise ValueError(f'{feature}: its bank flank folds near {t[np.argmin(n[:, 1])].mean(0).round(2).tolist()}')
        parts.append(dsl.Mesh.part(V, F, material=side.material, role=dsl.SIDE, feature=feature,
                                   UV=np.stack([along, P2[:, 1]], 1) / dsl.UV_METRES))
    col = {e: [place(np.array([u[e]]), np.array([x]))[0] for x in ends[e]] for e in (0, -1)}
    return dsl.Mesh.concat(parts), foot, col


def _drop_rows(top, foot, step=WALL_ROW, fixed=False):
    """Rows down a vertical wall from `top` to `foot` (k, 3), at most `step` apart; past a station's foot (or within
    half a step of it) a row collapses onto the foot. The last row is the foot."""
    h = top[:, 1] - foot[:, 1]
    n = max(1, math.ceil(float(h.max()) / step)) if len(h) else 1
    rows = []
    for k in range(1, n):
        d = k * step if fixed else k * float(h.max()) / n
        y = np.where(d < h - step / 2, top[:, 1] - d, foot[:, 1])
        r = top.copy(); r[:, 1] = y
        rows.append(r)
    return rows + [foot]


def _bowl_top(side, h=None):
    """A bowl side's transition at wall height h (default its full height): (top angle radians, vert metres)."""
    h = side.height if h is None else h
    R = side.radius
    return (math.acos(1. - h / R), 0.) if h <= R else (math.pi / 2, h - R)


def bowl_reach(side=None):
    """Plan metres from the riding edge to a bowl side's outer cap edge at full height (default: Side('bowl'))."""
    side = side or Side('bowl')
    th, _ = _bowl_top(side)
    return side.radius * math.sin(th) + side.width


def _edge_curvature(E, D):
    """Per station: the riding edge E's plan curvature toward D (> 0: D is the inside of the turn), the largest over
    each station's two neighbours either side."""
    if len(E) < 3:
        return np.zeros(len(E))
    s = np.r_[0., np.cumsum(np.linalg.norm(np.diff(E[:, [0, 2]], axis=0), axis=1))]
    T = np.gradient(E[:, [0, 2]], s, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    dT = np.gradient(T, s, axis=0)
    k = (dT * D[:, [0, 2]]).sum(1)
    return np.maximum.reduce([k, np.r_[k[1:], k[-1]], np.r_[k[0], k[:-1]], np.r_[k[2:], k[-2:]], np.r_[k[:2], k[:-2]]])


def _bowl_scale(u, fade):
    """A bowl side's section scale (0..1) at plan metres u along its edge of plan length u[-1]: a cosine ease from 0
    over fade (start, end) metres at each end, else 1."""
    f0, f1 = fade or (0., 0.)
    w = np.ones(len(u))
    if f0 > 0:
        w *= (1. - np.cos(np.pi * np.clip(u / f0, 0., 1.))) / 2
    if f1 > 0:
        w *= (1. - np.cos(np.pi * np.clip((u[-1] - u) / f1, 0., 1.))) / 2
    return w


def _fade_stations(side, length):
    """Extra plan stations (metres along an edge of plan `length`) in a bowl side's fade zones, so the top of its
    transition turns at most BOWL_TURN between stations as its section eases (its other stations stay as swept)."""
    f0, f1 = side.fade or (0., 0.)
    out = []
    for f, sign in ((f0, 1), (f1, -1)):
        if f <= 0:
            continue
        x = np.linspace(0., min(f, length), 2001)
        H = side.height * ((1 - np.cos(np.pi * x / f)) / 2) ** side.fade_power
        th = np.arccos(1 - np.minimum(H, side.radius) / side.radius)
        reach = side.radius * np.sin(th)
        yaw = np.arctan(np.gradient(reach, x))
        pitch = np.arctan(np.gradient(H, x))
        acc = np.r_[0., np.cumsum(np.abs(np.diff(th)) + np.abs(np.diff(yaw)) + np.abs(np.diff(pitch)))]
        n = math.ceil(acc[-1] / math.radians(BOWL_TURN))
        if n > 1:
            q = np.interp(np.linspace(0., acc[-1], n + 1)[1:-1], acc, x)
            out.append(q if sign > 0 else length - q)
    return np.concatenate(out) if out else np.zeros(0)


def _bowl_rows(E, D, side, feature):
    """@cc [owner:fontanierh,label:correctness] nonpinching-shoulder-fade
    Fading MUST lower the wall along its specified fixed-radius transition;
    it MUST NOT shrink that radius toward a sharp conical tip. At zero height
    the transition collapses onto its floor edge and its flat cap remains.
    """
    Y = np.array([0., 1., 0.])
    u = np.r_[0., np.cumsum(np.linalg.norm(np.diff(E[:, [0, 2]], axis=0), axis=1))]
    sc = _bowl_scale(u, side.fade)[:, None]
    th, vert = _bowl_top(side)
    if side.shape is None:
        heights, R = side.height, side.radius
    else:
        heights, R = (np.asarray(v, 'f8').reshape(-1, 1) for v in side.shape(E))
        if (not np.isfinite(heights).all() or not np.isfinite(R).all() or (heights <= 0).any() or (R <= 0).any()
                or (heights > side.height + 1e-7).any() or (R > side.radius + 1e-7).any()):
            raise ValueError(f'{feature}: side shape exceeds its declared positive height/radius envelope')
    H = heights * sc ** side.fade_power
    angles = np.arccos(1 - np.minimum(H, R) / R)
    vertical = np.maximum(H - R, 0.)
    k = _edge_curvature(E, D)
    reach = bowl_reach(side)
    if (k * reach > .9).any():
        i = int(np.argmax(k))
        raise ValueError(f'{feature}: its bowl side folds on the inside of a turn of radius {1 / k[i]:.1f} m near '
                         f'{E[i].round(2).tolist()} (the wall reaches {reach:.1f} m; ease the turn or lower the wall)')
    n_arc = max(2, math.ceil(math.degrees(th) / BOWL_STEP))
    n_vert = math.ceil(vert / WALL_ROW) if vert > 0 else 0
    rows = []
    for j in range(1, n_arc + 1):
        a = angles * j / n_arc
        rows.append(E + R * np.sin(a) * D + R * (1 - np.cos(a)) * Y)
    top = rows[-1]
    for j in range(1, n_vert + 1):
        rows.append(top + vertical * (j / n_vert) * Y)
    cap = rows[-1] + side.width * D
    return [E] + rows, cap


def _side_columns(E, D, side, g, base_y, under=None, on_ground=False, closed=False, feature='side', suspended=False):
    """The cross-section points outward of a riding edge E (k, 3), outward D (k, 3) horizontal unit, for `side`:
    a list of (k, 3) rows from the edge out to the outer top, then the foot and (unless `on_ground`) the base rows;
    plus each segment's (role, outward kind) for the strips between consecutive rows ('skip': meshed in extra
    parts). On the ground, the foot lies exactly on it (or at the edge where the ground is as high), and nothing goes
    below. extra: {'parts', 'ends': a bank flank's own points down each end, 'at': the row they follow}."""
    Y = np.array([0., 1., 0.])
    gap = 0. if on_ground else FOOT
    rows, segs = [E], []
    extra = {'parts': [], 'ends': {0: [], -1: []}, 'at': 0}
    if side.kind == 'bowl':
        arc, cap = _bowl_rows(E, D, side, feature)
        extra['parts'].append(solids.grid(np.stack(arc, 1), outward=-D + Y, feature=feature, material=side.material,
                                          role=dsl.RIDING, uv='arc', closed_rows=closed))
        rows += arc[1:]; segs += [(dsl.RIDING, 'skip')] * (len(arc) - 1)
        rows.append(cap); segs.append((dsl.RIDING, 'up'))
        outer = side.outer or ('ground' if on_ground else 'wall')
        side = Side(outer, degrees=side.degrees, material=side.material)
        E = cap
        extra['at'] = len(rows) - 1
    if side.kind == 'ground':
        if not on_ground:
            raise ValueError("a 'ground' side needs on_ground=True (the landform meets the riding edge)")
        return rows, segs, extra
    if side.kind == 'curb':
        rows.append(E + side.height * Y); segs.append((dsl.SIDE, 'inner'))
        rows.append(E + side.height * Y + side.width * D); segs.append((dsl.RIDING, 'up'))
    elif side.kind == 'bank':
        if closed:
            raise ValueError(f'{feature}: a bank flank on a closed path is not supported; use a wall or curb')
        mesh, foot_f, ends = _flank_mesh(E, D, side, g, gap, feature)
        rows.append(foot_f); segs.append((dsl.RIDING, 'flank'))
        extra['parts'] += [mesh] if mesh is not None else []
        extra['ends'] = ends
    outer = rows[-1]
    gy = np.asarray(base_y) if suspended else g(outer[:, 0], outer[:, 2])
    foot = outer.copy(); foot[:, 1] = np.minimum(gy, outer[:, 1] - gap)
    if under is not None and not on_ground:     # under the section's lowest point, so the end face stays simple
        foot[:, 1] = np.minimum(foot[:, 1], under - FOOT)
    # down to the foot (a bank's flank ends on the ground already; where it collapsed onto a flush edge, the drop
    # keeps the foot under it, so the end face never folds back on itself)
    role = dsl.SIDE if (side.kind != 'flush' or on_ground) else dsl.BASE
    if side.kind != 'bank' or (outer[:, 1] - foot[:, 1] > 1e-9).any():
        for r in _drop_rows(outer, foot, fixed=suspended):
            rows.append(r); segs.append((role, 'out'))
    if not on_ground:
        base = outer.copy(); base[:, 1] = base_y
        rows.append(base); segs.append((dsl.BASE, 'out'))
    return rows, segs, extra


def _ground_bands(chain, g, eps=1e-6):
    """An end face on the ground: the polygons between its top `chain` (from foot to foot) and the ground straight
    under it, one per run where the chain stands over the ground (where it lies on the ground the face pinches)."""
    gy = np.minimum(g(chain[:, 0], chain[:, 2]), chain[:, 1])
    gy[0], gy[-1] = chain[0, 1], chain[-1, 1]                    # the feet are on the ground
    over = chain[:, 1] - gy > eps
    bands, i, n = [], 0, len(chain)
    while i < n - 1:
        if not over[i + 1]:
            i += 1; continue
        j = i + 1
        while j < n - 1 and over[j]:
            j += 1
        top = chain[i:j + 1]
        under = np.stack([chain[i + 1:j, 0], gy[i + 1:j], chain[i + 1:j, 2]], 1)[::-1]
        loop = _strip_dupes(np.concatenate([top, under])) if len(under) else top
        if len(loop) >= 3:
            bands.append(loop)
        i = j
    return bands


def _chord_points(chain, F, B, gap=.05):
    """Points on the straight foot chord F -> B under an end face's top `chain`, where its points stand over the
    chord (in order from F): the face's triangles then never span the whole chord under a low top (C's V9)."""
    d = B - F; L2 = float(d @ d)
    if L2 < 1e-12:
        return np.zeros((0, 3))
    u = np.sort(((chain - F) @ d) / L2)
    u = u[(u > gap / np.sqrt(L2)) & (u < 1 - gap / np.sqrt(L2))]
    keep, last = [], 0.
    for x in u:
        if (x - last) * np.sqrt(L2) > gap:
            keep.append(x); last = x
    keep = [x for x in keep if (1 - x) * np.sqrt(L2) > gap]
    return F + np.asarray(keep)[:, None] * d if keep else np.zeros((0, 3))


def _strip_dupes(L):
    keep = np.r_[True, np.linalg.norm(np.diff(L, axis=0), axis=1) > 1e-9]
    L = L[keep]
    if np.linalg.norm(L[0] - L[-1]) <= 1e-9:
        L = L[:-1]
    return L


def _bury_low(mesh, ground):
    """Wall faces standing less than FLUSH over the ground become buried closing faces (role base)."""
    t = mesh.triangles()
    top = t[:, :, 1].max(1)
    c = t.mean(1)
    low = top - ground(c[:, 0], c[:, 2]) < FLUSH
    mesh.role[low] = dsl.ROLE[dsl.BASE]


def _finish(parts, feature, riding=None, on_ground=False):
    """The parts as one mesh, checked: closed (or, on the ground, open only along simple foot loops) and unfolded.
    Returns (mesh, foot loops [(k, 3)])."""
    mesh = one_feature(dsl.Mesh.concat(parts), feature)
    solids.check_folds(mesh.where(role=dsl.RIDING) if riding is None else riding, name=feature)
    if not on_ground:
        solids.check_closed(mesh, name=feature)
        return mesh, []
    return mesh, solids.check_open(mesh, name=feature)


# ------------------------------------------------------------------------------------------------ longitudinal ramps

CLEAR = .25         # share of the local station spacing a path station keeps clear of a profile station
NEAR = .05          # metres: a path break (a fillet's start) this near a profile station merges into it


class _Clear(Curve):
    """A path whose own adaptive stations keep clear of the profile's (`own`, path parameters): a longitudinal sweep
    merges both lists, and a path station a centimetre from a profile station made a sliver row (C's V9)."""

    def __init__(self, path, own):
        self.path, self.own = path, np.sort(np.asarray(own, 'f8'))
        self.length, self.closed = path.length, getattr(path, 'closed', False)

    def point(self, t):
        return self.path.point(t)

    def tangent(self, t):
        return self.path.tangent(t)

    def normal(self, t):
        return self.path.normal(t)

    def curvature(self, t):
        return self.path.curvature(t)

    def breaks(self):
        return self.path.breaks()

    def samples(self, tess, extra=(), offsets=(0.,), height=None):
        t = self.path.samples(tess, extra, offsets, height)
        if len(self.own) < 2:
            return t
        k = np.clip(np.searchsorted(self.own, t), 1, len(self.own) - 1)
        lo, hi = self.own[k - 1], self.own[k]
        gap = np.minimum(t - lo, hi - t)
        inside = (t > self.own[0]) & (t < self.own[-1])
        keep = ~inside | (gap > CLEAR * (hi - lo)) | (np.isin(t, self.path.breaks()) & (gap > NEAR))
        return t[keep]



def ramp(path, profile, width, *, start=0., left='wall', right='wall', ground=None, ends=('flush', 'flush'),
         feature='ramp', tess=TESS, t=None, on_ground=False, across=None, thickness=None,
         bottom_u=None, end_openings=None):
    """@cc [owner:fontanierh,label:correctness] suspended-ramp-solid
    A ramp along the plan `path` (curves.Curve) from `start` metres along it: the `profile` (its x along the path,
    y absolute) `width` wide, closed into a solid down to the `ground` (float or f(x, z); default 0 under the lowest
    point) with sides `left`/`right` (Side or kind; left is the path's +normal side) and `ends` (start, end) each
    'flush' (the next feature or deck continues there) or 'wall' (a visible end face: a kicker's back at its lip, a
    landing's front). `across` supplies exact lateral floor stations for a shared port, including both floor edges.
    `thickness` makes an elevated solid channel whose underside follows the floor
    that many metres below it; it has no terrain footprint. Roll-ins, decks,
    kickers, landings and run-outs are ramps. Returns a Built.

    `bottom_u` gives exact normalized underside columns for shared ports.
    `end_openings` gives the start/end lateral intervals occupied by adjoining
    modules. The rest of those end walls stays visible and collidable.

    A suspended ramp MUST be closed, with a visible underside following its floor
    at the requested positive thickness; it MUST NOT close down to terrain.
    """
    if thickness is not None:
        if not math.isfinite(thickness) or thickness < MIN_WALL:
            raise ValueError('a suspended ramp needs at least 0.30 m thickness')
        if on_ground:
            raise ValueError('a suspended ramp cannot also be on_ground')
        if any(as_side(s).kind in ('bank', 'ground') or as_side(s).outer in ('bank', 'ground') for s in (left, right)):
            raise ValueError('a suspended ramp needs solid outer walls')
    if bottom_u is not None:
        bottom_u = np.asarray(bottom_u, 'f8')
        if (thickness is None or bottom_u.ndim != 1 or len(bottom_u) < 2 or not np.isfinite(bottom_u).all()
                or np.any(np.diff(bottom_u) <= 0) or not np.allclose(bottom_u[[0, -1]], [0., 1.], atol=1e-12, rtol=0)):
            raise ValueError('suspended underside columns must increase from zero to one')
    if end_openings is not None:
        if thickness is None or len(end_openings) != 2:
            raise ValueError('end openings need a suspended ramp and two end specifications')
        for openings in end_openings:
            if openings is not None and any(not -width / 2 <= a < b <= width / 2 for a, b in openings):
                raise ValueError('end openings must lie inside the flat floor width')
    if across is not None:
        across = np.asarray(across, 'f8')
        if (across.ndim != 1 or len(across) < 2 or not np.isfinite(across).all()
                or np.any(np.diff(across) <= 0) or not np.allclose(across[[0, -1]], [-width / 2, width / 2], atol=1e-8, rtol=0)):
            raise ValueError('ramp: across must increase from -width/2 to width/2')
    left, right = _faded(as_side(left), ends), _faded(as_side(right), ends)
    if left.kind == 'bowl' or right.kind == 'bowl':
        tess = replace(tess, angle=min(tess.angle, 1.))
    own = start + profile.point(profile.samples(tess))[:, 0] - profile.start[0]
    extra = [] if t is None else [np.asarray(t, 'f8')]
    for sd in (left, right):
        if sd.kind == 'bowl' and sd.fade and max(sd.fade) > 0:
            L = float(own.max() - own.min())
            q = start + _fade_stations(sd, L)
            extra.append(q[np.abs(q[:, None] - own[None]).min(1) > .15] if len(q) else q)
    t = np.unique(np.concatenate(extra)) if extra else None
    riding = sweep(_Clear(path, own), profile, mode='longitudinal', start=start, across=width if across is None else across, feature=feature,
                   tess=tess, t=t)
    lo = float(riding.V[:, 1].min())
    g = as_ground(lo if ground is None else ground)
    V = riding.V
    # the edge rows (w = -W/2 is the path's right, -N; +W/2 its left, +N)
    sm = riding.seams
    e_minus = _dedupe(sm[f'{feature}.left'], V); e_plus = _dedupe(sm[f'{feature}.right'], V)
    if len(e_minus) != len(e_plus):
        raise ValueError(f'{feature}: edge rows differ ({len(e_minus)} vs {len(e_plus)})')
    Em, Ep = V[e_minus], V[e_plus]
    D = Ep - Em; D[:, 1] = 0; D /= np.linalg.norm(D, axis=1, keepdims=True)
    start_row = _dedupe(sm[f'{feature}.start'], V); end_row = _dedupe(sm[f'{feature}.end'], V)
    rows = [V[start_row], V[end_row]]
    if np.dot(rows[0][-1] - rows[0][0], D[0]) < 0:
        rows = [r[::-1] for r in rows]
    G = np.stack([Em, Ep], 1)
    parts = [riding] + _close_transverse(G, feature=feature, ground=g, front=right, back=left, ends=ends,
                                         closed=False, end_rows=rows, on_ground=on_ground, thickness=thickness,
                                         bottom_u=bottom_u, end_openings=end_openings)
    mesh, foot = _finish(parts, feature, riding, on_ground)
    x = profile.point([0., profile.length])
    checks = [{'feature': feature, 'kind': 'ramp', 'start_t': start, 'end_t': start + float(x[1, 0] - x[0, 0]),
               'start_y': float(x[0, 1]), 'end_y': float(x[1, 1]), 'end_degrees': profile.end_degrees,
               'width': width}]
    return Built(mesh, [], checks, foot)


def jump_line(path, launch, landing, gap, width, *, start=0., left='wall', right='wall', ground=None,
              feature='jump', tess=TESS, land_width=None, on_ground=False):
    """The joined line: roll-in, deck, kicker (the `launch` profile, ending at its lip), a `gap` (horizontal metres
    from the lip to the landing's start), then landing and run-out (the `landing` profile), along one plan `path`.
    The launch's last arc is tagged takeoff and the landing ramp's faces landing (unless the profiles tag them). The
    kicker's back under its lip and the landing's front are visible walls. Returns a Built whose checks hold the lip
    (point, degrees, height over the ground) and the landing zone."""
    def retag(p, tag, which):
        return Profile(tagged(p.parts, tag, which), start=tuple(p.start), degrees=p.degrees, tags=p.tags)
    arcs = [i for i, part in enumerate(launch.parts) if part[0] == 'arc']
    launch = retag(launch, 'takeoff', [arcs[-1]] if arcs else [len(launch.parts) - 1])
    landing = retag(landing, 'landing', None)
    a = ramp(path, launch, width, start=start, left=left, right=right, ground=ground, ends=('flush', 'wall'),
             feature=f'{feature}.launch', tess=tess, on_ground=on_ground)
    x0 = float(launch.end[0] - launch.start[0])
    b = ramp(path, landing, land_width or width, start=start + x0 + gap, left=left, right=right, ground=ground,
             ends=('wall', 'flush'), feature=f'{feature}.landing', tess=tess, on_ground=on_ground)
    g = as_ground(0. if ground is None else ground)
    lip_t = start + x0
    lip = path.point3([lip_t], launch.end[1])[0]
    land0 = path.point3([lip_t + gap], landing.start[1])[0]
    checks = [{'feature': feature, 'kind': 'air', 'lip': lip.tolist(), 'lip_degrees': launch.end_degrees,
               'lip_height': float(lip[1] - g(lip[:1], lip[2:])[0]), 'gap': gap, 'landing_start': land0.tolist(),
               'landing_t': (lip_t + gap, lip_t + gap + float(landing.end[0] - landing.start[0]))}]
    return Built(dsl.Mesh.concat([a.mesh, b.mesh]), [], a.checks + b.checks + checks, a.foot + b.foot)


# ------------------------------------------------------------------------------------------------ transverse solids

class Rounded(Curve):
    """A plan path through `points` (k, 2) whose corners are exact circular fillets of `radius` (a scalar or one per
    corner): straight legs and arcs, tangent-continuous, so a transverse sweep turns it without a mitre. `closed`
    rounds the closing corner too (a rounded-rectangle ledge, a bowl's outline). Arc ends are breaks."""

    def __init__(self, points, radius, closed=False):
        p = np.asarray(points, 'f8')
        if closed and np.linalg.norm(p[0] - p[-1]) < 1e-9:
            p = p[:-1]
        self.closed = closed
        n = len(p)
        corners = range(n) if closed else range(1, n - 1)
        r = np.broadcast_to(np.asarray(radius, 'f8'), (n,))
        fil = {}
        for i in corners:
            a, b, c = p[i - 1], p[i], p[(i + 1) % n]
            u = (b - a) / np.linalg.norm(b - a); v = (c - b) / np.linalg.norm(c - b)
            turn = math.atan2(u[0] * v[1] - u[1] * v[0], u @ v)
            if abs(turn) < 1e-9:
                continue
            cut = r[i] * math.tan(abs(turn) / 2)
            fil[i] = (b - cut * u, b + cut * v, turn, r[i], u, cut)
        for i in range(n if closed else n - 1):                 # each leg holds the cuts at both its ends
            j = (i + 1) % n
            used = fil.get(i, (0,) * 6)[5] + fil.get(j, (0,) * 6)[5]
            if used > np.linalg.norm(p[j] - p[i]) + 1e-9:
                raise ValueError(f'Rounded: the fillets at points {i} and {j} do not fit the leg between them')
        self.parts = []                          # ('line', a, b) or ('arc', centre, R, start angle, turn)
        start = fil[0][1] if closed and 0 in fil else p[0]
        order = list(range(1, n)) + ([0] if closed else [])
        cur = start
        for i in order:
            if i in fil:
                a, b, turn, R, u, _ = fil[i]
                if np.linalg.norm(a - cur) > 1e-12:
                    self.parts.append(('line', cur, a))
                nrm = np.array([-u[1], u[0]]) * math.copysign(1., turn)
                centre = a + R * nrm
                a0 = math.atan2(*(a - centre)[::-1])
                self.parts.append(('arc', centre, R, a0, turn))
                cur = b
            else:
                if np.linalg.norm(p[i] - cur) > 1e-12:
                    self.parts.append(('line', cur, p[i]))
                cur = p[i]
        if closed and np.linalg.norm(start - cur) > 1e-12:
            self.parts.append(('line', cur, start))
        self.curves = [Line(q[1], q[2]) if q[0] == 'line' else Arc(q[1], q[2], math.degrees(q[3]), math.degrees(q[4]))
                       for q in self.parts]
        self.s = np.concatenate([[0.], np.cumsum([c.length for c in self.curves])])
        self.length = float(self.s[-1])

    def _at(self, t):
        t = np.atleast_1d(np.asarray(t, 'f8'))
        k = np.clip(np.searchsorted(self.s, t, 'right') - 1, 0, len(self.curves) - 1)
        return k, t

    def _map(self, t, fn, width):
        k, t = self._at(t)
        out = np.zeros((len(t), width)) if width else np.zeros(len(t))
        for i in np.unique(k):
            m = k == i
            out[m] = getattr(self.curves[i], fn)(t[m] - self.s[i])
        return out

    def point(self, t):
        return self._map(t, 'point', 2)

    def tangent(self, t):
        return self._map(t, 'tangent', 2)

    def curvature(self, t):
        return self._map(t, 'curvature', 0)

    def breaks(self):
        return self.s.copy()


def _horizontal(v):
    v = np.asarray(v, 'f8').copy(); v[..., 1] = 0
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-300)


def _columns(profile, tess, s=None):
    """The sweep's profile stations (crease twins included), as sweep.sweep makes them."""
    st, _, _ = _stations(profile, profile.samples(tess, () if s is None else s))
    return st


def _grid_of(riding, nb):
    """The transverse sheet's vertex grid (rows: path stations, columns: profile stations)."""
    if len(riding.V) % nb:
        raise ValueError('the sweep grid does not match its profile stations')
    return riding.V.reshape(-1, nb, 3)


def _dedupe_rows(P):
    keep = np.r_[True, np.linalg.norm(np.diff(P, axis=0), axis=-1).max(-1) > 1e-9] if P.ndim == 3 else None
    return P[keep]


def _dedupe_cols(row):
    keep = np.r_[True, np.linalg.norm(np.diff(row, axis=0), axis=1) > 1e-9]
    return row[keep]


def _close_transverse(G, *, feature, ground, front, back, ends, closed, end_rows=None, on_ground=False, thickness=None,
                      bottom_u=None, end_openings=None):
    """Walls, base, caps and end faces closing a riding sheet into a solid. G (k, n, 3): its grid, rows path
    stations, columns from front to back (a ramp passes only its two edge columns and its full `end_rows`).
    front/back: Side kinds ('wall', 'flush', 'curb', 'bank'), or 'cap' (front only: the front column is a level loop
    filled as riding, a bowl's floor or a ledge's top) or 'base' (back only: a level loop on the support filled as a
    buried base, a ledge's footprint). `on_ground`: no base under the feet; the solid stays open exactly along its
    foot loop, which the ground (ground.py) fills. Low faces (under FLUSH over the ground) are buried (role base)."""
    Y = np.array([0., 1., 0.])
    g = as_ground(ground)
    if closed:
        G = G[:-1] if np.linalg.norm(G[0] - G[-1], axis=-1).max() < 1e-9 else G
    Ef, Eb = G[:, 0], G[:, -1]
    D = _horizontal(Eb - Ef)
    lo = min(float(G[..., 1].min()), float(g(G[..., 0].ravel(), G[..., 2].ravel()).min()))
    probe = []
    for E, Dd, kind in ((Ef, -D, front), (Eb, D, back)):
        s = as_side(kind) if kind not in ('cap', 'base') else None
        if s is not None and s.kind == 'bank':
            reach = (E[:, 1] - g(E[:, 0], E[:, 2])).max() / math.tan(math.radians(s.degrees)) + 1.
            q = E + reach * Dd
            probe.append(float(g(q[:, 0], q[:, 2]).min()))
        if s is not None and s.kind == 'curb':
            q = E + s.width * Dd
            probe.append(float(g(q[:, 0], q[:, 2]).min()))
        if s is not None and s.kind == 'bowl':
            out = bowl_reach(s) + (E[:, 1].max() + s.height - g(E[:, 0], E[:, 2]).min()) / math.tan(
                math.radians(s.degrees)) + 1. if s.outer == 'bank' else bowl_reach(s)
            for x in np.linspace(0., out, 4):
                q = E + x * Dd
                probe.append(float(g(q[:, 0], q[:, 2]).min()))
    base_y = min([lo] + probe) - BURY - FOOT
    suspended = thickness is not None
    if suspended:
        base_y = G[..., 1].min(1) - thickness
    parts = []
    cols, ends_of, at_of = {}, {'front': {0: [], -1: []}, 'back': {0: [], -1: []}}, {'front': 0, 'back': 0}
    for name, E, Dd, kind in (('front', Ef, -D, front), ('back', Eb, D, back)):
        if kind == 'cap':
            parts.append(solids.polygon(E, outward=Y, feature=feature, role=dsl.RIDING))
            cols[name] = None
            continue
        if kind == 'base':
            if np.ptp(E[:, 1]) > 1e-9:
                raise ValueError(f'{feature}: a base loop must be level')
            if not on_ground:
                parts.append(solids.polygon(E, outward=-Y, feature=feature, role=dsl.BASE))
            cols[name] = None
            continue
        side = as_side(kind)
        rows, segs, extra = _side_columns(E, Dd, side, g, base_y, under=G[..., 1].min(1), on_ground=on_ground,
                                          closed=closed, feature=feature, suspended=suspended)
        parts += extra['parts']
        ends_of[name] = extra['ends']; at_of[name] = extra['at']
        for (a, b), (role, k) in zip(itertools.pairwise(rows), segs, strict=True):
            if k in ('flank', 'skip'):
                continue
            out = {'inner': -Dd, 'up': np.broadcast_to(Y, Dd.shape), 'bank': Dd + Y, 'out': Dd}[k]
            m = solids.grid(np.stack([a, b], 1), outward=out, feature=feature, material=side.material, role=role,
                            uv='arc' if role == dsl.RIDING else 'wall', closed_rows=closed)
            if role == dsl.SIDE and not on_ground and not suspended:
                _bury_low(m, g)
            parts.append(m)
        cols[name] = rows
    if not on_ground:
        if cols['front'] is not None and cols['back'] is not None:
            fbase, bbase = cols['front'][-1], cols['back'][-1]
            if bottom_u is None:
                bottom_u = np.linspace(0., 1., max(1, math.ceil(np.linalg.norm(bbase - fbase, axis=1).max() / WALL_ROW)) + 1)
            bottom = fbase[:, None] + bottom_u[None, :, None] * (bbase - fbase)[:, None]
            parts.append(solids.grid(bottom if suspended else np.stack([fbase, bbase], 1), outward=-Y, feature=feature,
                                     role=dsl.SIDE if suspended else dsl.BASE, uv='world', closed_rows=closed))
        elif closed and cols['back'] is not None:
            parts.append(solids.polygon(cols['back'][-1], outward=-Y, feature=feature, role=dsl.BASE))
        elif closed and cols['front'] is not None:
            raise ValueError(f'{feature}: a closed sweep needs a cap at its front or a base at its back')
    if not closed:
        if cols['front'] is None or cols['back'] is None:
            raise ValueError(f'{feature}: an open sweep closes with walls at its front and back')
        T0 = _horizontal(G[1, 0] - G[0, 0]); T1 = _horizontal(G[-1, 0] - G[-2, 0])
        tops = end_rows if end_rows is not None else (G[0], G[-1])
        foot = -1 if on_ground else -2
        for i, top, kind, out in ((0, tops[0], ends[0], -T0), (-1, tops[1], ends[1], T1)):
            f = [r[i] for r in cols['front']]; b = [r[i] for r in cols['back']]
            af, ab = at_of['front'] + 1, at_of['back'] + 1     # a flank's own points down the end
            f = f[:af] + list(ends_of['front'][i]) + f[af:]
            b = b[:ab] + list(ends_of['back'][i]) + b[ab:]
            wall = as_side(kind).kind == 'wall'
            if on_ground and not wall:
                continue                 # the next feature or deck continues here: left open (its seam)
            if suspended:
                chord = f[-1] + bottom_u[1:-1, None] * (b[-1] - f[-1])
                loop = _strip_dupes(np.asarray(f[::-1] + list(top) + b[1:] + list(chord[::-1])))
                openings = None if end_openings is None else end_openings[0 if i == 0 else 1]
                if openings is None:
                    parts.append(solids.polygon(loop, outward=out, feature=feature,
                                                role=dsl.SIDE if wall else dsl.BASE))
                else:
                    from . import ports
                    parts += ports.cap(loop, axis=D[i], centre=(Ef[i] + Eb[i]) / 2,
                                       outward=out, openings=openings, feature=feature)
                continue
            upper = [f[foot]] + f[foot - 1::-1] + list(top) + b[1:len(b) + foot + 1]
            upper = _strip_dupes(np.asarray(upper))
            if on_ground:
                for band in _ground_bands(upper, g):
                    parts.append(solids.polygon(band, outward=out, feature=feature, role=dsl.SIDE))
                continue
            chord = _chord_points(upper, f[foot], b[foot])
            m = solids.polygon(np.concatenate([upper, chord[::-1]]), outward=out, feature=feature,
                               role=dsl.SIDE if wall else dsl.BASE)
            if wall and not on_ground:
                _bury_low(m, g)
            parts.append(m)
            if not on_ground:
                lower = np.concatenate([[b[-2], b[-1], f[-1], f[-2]], chord])
                parts.append(solids.polygon(lower, outward=out, feature=feature, role=dsl.BASE))
    return parts


def transverse(path, profile, *, side=1, offset=0., height=0., ground=None, front='flush', back='wall',
               ends=('wall', 'wall'), feature='transverse', tess=TESS, t=None, on_ground=False):
    """A profile swept across the plan `path` (A's transverse sweep: o = offset + side * x), closed into a solid.
    Returns (Built, the sheet's grid (k, n, 3), its profile columns)."""
    closed = bool(getattr(path, 'closed', False))
    o = offset + side * profile.point(profile.samples(tess))[:, 0]
    tt = np.linspace(0, path.length, max(256, int(path.length * 8)))
    k = path.curvature(tt)
    stretch = 1 - k[:, None] * o[None, :]                    # a row's length per metre of path: <= 0 folds
    if stretch.min() < .1:
        i, j = np.unravel_index(int(np.argmin(stretch)), stretch.shape)
        raise ValueError(f'{feature}: the path bends to R {1 / abs(k[i]):.2f} m near '
                         f'{path.point([tt[i]])[0].round(2).tolist()} on the side the section reaches '
                         f'{abs(o[j]):.2f} m: the section would fold (keep R > 1.1 x the reach there)')
    riding = sweep(path, profile, mode='transverse', side=side, offset=offset, height=height, feature=feature,
                   tess=tess, t=t)
    st = _columns(profile, tess)
    G = _grid_of(riding, len(st))
    # the closing works on positions; crease twins are dropped (they weld)
    # UVs: u the length along the path itself (o = 0: the lip, the centreline), the same for every column so nothing
    # shears (A's sweep measures it at `offset`, the profile's start, which stretches the far side most: V8); v the
    # profile's arc length. Each column's length is linear in its offset; the fit at o = 0 is the path's.
    o = offset + side * profile.point(st)[:, 0]
    along = np.concatenate([np.zeros((1, G.shape[1])), np.cumsum(np.linalg.norm(np.diff(G, axis=0), axis=-1), 0)])
    if np.ptp(o) > 1e-9:
        oc = o - o.mean()
        slope = (along * oc).sum(1) / (oc * oc).sum()
        u = along.mean(1) - slope * o.mean()
    else:
        u = along[:, 0]
    riding.UV = (np.stack(np.broadcast_arrays(u[:, None], st[None, :]), -1) / dsl.UV_METRES).reshape(-1, 2)
    keep = np.r_[True, np.abs(np.diff(st)) > 1e-12]
    Gc = G[:, keep]
    lo = float(G[..., 1].min())
    parts = [riding] + _close_transverse(Gc, feature=feature, ground=lo if ground is None else ground, front=front,
                                         back=back, ends=ends, closed=closed, on_ground=on_ground)
    mesh, foot = _finish(parts, feature, riding, on_ground)
    return Built(mesh, foot=foot), G, st


def _lip_row(G, st, profile, name='lip'):
    s = profile.tags[name]
    j = int(np.flatnonzero(np.abs(st - s) < 1e-9)[0])
    return G[:, j]


def _with_coping(built, G, st, profile, *, closed, into_sign, feature, names=('lip',)):
    """Coping tubes along the profile's tagged lip rows; into_sign +1 when the transition lies toward the profile's
    front (lower s) from the lip."""
    meshes, rails = [built.mesh], []
    D = _horizontal(G[:, -1] - G[:, 0])
    for k, name in enumerate(names):
        row = _lip_row(G, st, profile, name)
        sign = into_sign[k] if np.ndim(into_sign) else into_sign
        rows = row[:-1] if closed and np.linalg.norm(row[0] - row[-1]) < 1e-9 else row
        Dd = D[:len(rows)]
        tube, rail = coping_mod.coping(rows, -sign * Dd, closed=closed, feature=f'{feature}.{name}')
        solids.check_closed(tube, name=f'{feature}.{name}')
        meshes.append(tube); rails.append(rail)
    mesh = one_feature(dsl.Mesh.concat(meshes), feature)
    return Built(mesh, built.rails + rails, built.checks, built.foot)


def quarter_pipe(path, *, floor_y, height, radius, deck=1.5, floor=.5, top_degrees=None, side=1, ground=None,
                 back='wall', ends=('wall', 'wall'), coping=True, feature='quarter_pipe', tess=TESS,
                 material=dsl.CONCRETE, deck_material=dsl.DECK, on_ground=False, front='flush'):
    """A quarter pipe whose lip runs along the plan `path`: a flat `floor` strip at `floor_y`, a transition of `radius`
    up to `top_degrees` (default: vertical if `height` > `radius`, else the angle the arc reaches at `height`), a
    straight extension to the lip at floor_y + height, then a flat `deck` (>= 1.2 m) on the path's `side` (+1 its
    left). The floor's front edge meets the park floor flush; the deck's back is a `back` Side; its flanks are
    `ends`. With `coping`, a steel tube along the lip and a rail on it. `front='ground'` leaves an on-ground
    floor seam open for an integral apron instead of making a wall underneath that apron."""
    if deck < 1.2 - 1e-9:
        raise ValueError(f'{feature}: a deck must be at least 1.2 m deep')
    if top_degrees is None:
        top_degrees = 90. if height >= radius else math.degrees(math.acos(1 - height / radius))
    a = math.radians(top_degrees)
    rise = radius * (1 - math.cos(a))
    if rise > height + 1e-9:
        raise ValueError(f'{feature}: the transition rises {rise:.3f} m, over the height {height}')
    ext = (height - rise) / math.sin(a)
    ride = {'material': material}
    parts = [('line', floor, ride), ('arc', radius, top_degrees, ride)]
    if ext > 1e-9:
        parts.append(('line', ext, ride))
    parts += [('corner', 0., {'material': deck_material, 'tag': 'lip'}), ('line', deck, {'material': deck_material})]
    prof = Profile(parts, start=(0., floor_y), tags={'lip': len(parts) - 1})
    x_lip = float(prof.point([prof.tags['lip']])[0, 0])
    built, G, st = transverse(path, prof, side=side, offset=-side * x_lip, ground=ground, front=front, back=back,
                              ends=ends, feature=feature, tess=tess, on_ground=on_ground)
    built.checks.append({'feature': feature, 'kind': 'quarter_pipe', 'lip_y': floor_y + height,
                         'top_degrees': top_degrees, 'radius': radius})
    if coping:
        built = _with_coping(built, G, st, prof, closed=bool(getattr(path, 'closed', False)), into_sign=1,
                             feature=feature)
    return built


def bank(path, *, foot_y, height, degrees, foot_r=3., top_r=3., deck=1.2, floor=0., side=1, ground=None,
         back='wall', ends=('wall', 'wall'), feature='bank', tess=TESS, material=dsl.CONCRETE, on_ground=False):
    """A bank whose foot runs along the plan `path`, rising on its `side` (+1 left): `floor` flat, a foot transition
    (R >= 3 m) up to `degrees`, a straight slope, a crest transition (R >= 3 m) back to level and a `deck` at
    foot_y + height. Along a Rounded path with a convex corner it is a rounded hip."""
    if min(foot_r, top_r) < 3. - 1e-9:
        raise ValueError(f'{feature}: bank transitions need R >= 3 m')
    a = math.radians(degrees)
    run = (height - (foot_r + top_r) * (1 - math.cos(a))) / math.sin(a)
    if run < -1e-9:
        raise ValueError(f'{feature}: transitions of R {foot_r}/{top_r} at {degrees} deg rise over {height} m')
    ride = {'material': material}
    parts = [('line', floor, ride)] if floor > 0 else []
    parts += [('arc', foot_r, degrees, ride)] + ([('line', run, ride)] if run > 1e-9 else [])
    parts += [('arc', top_r, 0., ride), ('line', deck, ride)]
    prof = Profile(parts, start=(0., foot_y), tags={'crest': len(parts) - 1})
    built, _, _ = transverse(path, prof, side=side, ground=ground, front='flush', back=back, ends=ends,
                             feature=feature, tess=tess, on_ground=on_ground)
    built.checks.append({'feature': feature, 'kind': 'bank', 'degrees': degrees, 'top_y': foot_y + height})
    return built


def hip(corner, legs, *, foot_y, height, degrees, ridge_r=None, **kw):
    """A hip: two banks rising away from their feet that meet on a ridge over the `corner` (plan point), the feet
    running back along `legs` = (a, b) (plan points). The foot turns the corner on a fillet of `ridge_r` (default
    the bank's reach, so the ridge is rounded and the surface stays one smooth sweep, never mitred)."""
    a, b = np.asarray(legs[0], 'f8'), np.asarray(legs[1], 'f8'); c = np.asarray(corner, 'f8')
    u = (c - a) / np.linalg.norm(c - a); v = (b - c) / np.linalg.norm(b - c)
    turn = u[0] * v[1] - u[1] * v[0]
    # the bank rises away from the hip's outside: inward of the turn
    side = 1 if turn > 0 else -1
    if ridge_r is None:
        ridge_r = 2. * height / math.tan(math.radians(degrees)) + kw.get('deck', 1.2) + 1.
    return bank(Rounded([a, c, b], ridge_r), foot_y=foot_y, height=height, degrees=degrees, side=side, **kw)


def snake_profile(width, wall, radius, lip):
    """A snake run's cross-section from its left deck edge to its right: `lip` of deck, the coping, an arc of
    `radius` down to the floor `width` wide, and back up. Tags lip_l, lip_r. Starts at (0, wall)."""
    a = math.degrees(math.acos(1 - wall / radius)) if wall < radius else 90.
    ext = (wall - radius * (1 - math.cos(math.radians(a)))) / math.sin(math.radians(a))
    down = [('corner', -a, {'tag': 'lip'})] + ([('line', ext)] if ext > 1e-9 else []) + [('arc', radius, 0.)]
    up = [('arc', radius, a)] + ([('line', ext)] if ext > 1e-9 else []) + [('corner', 0., {'tag': 'lip'})]
    parts = [('line', lip, {'material': dsl.DECK})] + down + [('line', width)] + up + [('line', lip, {'material': dsl.DECK})]
    return Profile(parts, start=(0., wall), tags={'lip_l': 1, 'lip_r': len(parts) - 2})


def snake_run(centre, *, width, wall, radius, lip=.6, floor=0., ground=None, coping=True, ends=('flush', 'flush'),
              feature='snake', tess=TESS, on_ground=False):
    """A snake run along the centreline `centre` (a smooth Curve, e.g. Spline): a floor `width` wide at the height
    `floor` (float, dsl.Height or f(t)) along it, transitions of `radius` rising `wall` either side, a `lip` deck and
    a coping on both lips. The sections come from the analytic normal (no eased polyline, no snap). A centreline
    tighter than 1.5 times the section's reach is refused, and so is any fold or a self-crossing outline."""
    prof = snake_profile(width, wall, radius, lip)
    half = float(prof.end[0]) / 2
    tt = np.linspace(0, centre.length, max(64, int(centre.length * 8)))
    k = np.abs(centre.curvature(tt)).max()
    if k > 0 and 1 / k < 1.5 * half:
        raise ValueError(f'{feature}: the centreline bends to R {1 / k:.2f} m, tighter than 1.5 x the section reach '
                         f'{half:.2f} m: the section would fold')
    built, G, st = transverse(centre, prof, side=1, offset=-half, height=floor, ground=ground, front='wall',
                              back='wall', ends=ends, feature=feature, tess=tess, on_ground=on_ground)
    outline = np.concatenate([G[:, 0], G[-1, 1:], G[::-1][1:, -1], G[0, ::-1][1:-1]])[:, [0, 2]]
    outline = _dedupe_cols(outline)
    if solids.segments_cross(outline):
        raise ValueError(f'{feature}: its outline crosses itself in plan (a fold)')
    built.checks.append({'feature': feature, 'kind': 'snake', 'reach': half, 'least_radius': 1 / k if k else np.inf})
    if coping:
        # lip_l: the transition lies toward the back (higher s); lip_r: toward the front
        built = _with_coping(built, G, st, prof, closed=False, into_sign=(-1, 1), feature=feature,
                             names=('lip_l', 'lip_r'))
    return built


def _ccw(path):
    tt = np.linspace(0, path.length, 512, endpoint=False)
    p = path.point(tt)
    return .5 * (p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]).sum() > 0


def bowl(outline, *, floor_y, depth, radius, deck=1.2, top_degrees=None, ground=None, back='wall', coping=True,
         feature='bowl', tess=TESS, material=dsl.CONCRETE, deck_material=dsl.DECK, on_ground=False):
    """A bowl whose coping follows the closed plan `outline` (Spline(closed=True) or Rounded(closed=True)): a level
    floor at `floor_y`, walls of transition `radius` up to `top_degrees` (default: vertical if `depth` > `radius`),
    a straight extension to the lip at floor_y + depth, and a `deck` around it. The outline may turn inward (a
    kidney); where its inward turn is tighter than the deck, or its outward bulge tighter than the transition's reach,
    the offset rows would fold, and the bowl is refused with the place and the radius."""
    if top_degrees is None:
        top_degrees = 90. if depth >= radius else math.degrees(math.acos(1 - depth / radius))
    a = math.radians(top_degrees)
    rise = radius * (1 - math.cos(a))
    if rise > depth + 1e-9:
        raise ValueError(f'{feature}: the transition rises {rise:.3f} m, over the depth {depth}')
    ext = (depth - rise) / math.sin(a)
    ride = {'material': material}
    parts = [('arc', radius, top_degrees, ride)] + ([('line', ext, ride)] if ext > 1e-9 else [])
    parts += [('corner', 0., {'material': deck_material, 'tag': 'lip'}), ('line', deck, {'material': deck_material})]
    prof = Profile(parts, start=(0., floor_y), tags={'lip': len(parts) - 1})
    reach = float(prof.point([prof.tags['lip']])[0, 0])
    inward = 1 if _ccw(outline) else -1                 # +N points into the bowl for a counter-clockwise outline
    tt = np.linspace(0, outline.length, max(256, int(outline.length * 8)), endpoint=False)
    k = outline.curvature(tt) * inward                  # > 0 where it bulges outward (convex), < 0 where it turns in
    convex, concave = k.max(), -k.min()
    if convex > 0 and 1 / convex <= reach + 1e-6:
        i = int(np.argmax(k))
        raise ValueError(f'{feature}: the outline bulges at R {1 / convex:.2f} m near {outline.point([tt[i]])[0].round(2)}, '
                         f'tighter than the transition reach {reach:.2f} m: the floor would fold')
    if concave > 0 and 1 / concave <= deck + 1e-6:
        i = int(np.argmin(k))
        raise ValueError(f'{feature}: the outline turns inward at R {1 / concave:.2f} m near '
                         f'{outline.point([tt[i]])[0].round(2)}, tighter than the deck {deck:.2f} m: the deck would fold')
    built, G, st = transverse(outline, prof, side=-inward, offset=inward * reach, ground=ground, front='cap',
                              back=back, feature=feature, tess=tess, on_ground=on_ground)
    built.checks.append({'feature': feature, 'kind': 'bowl', 'lip_y': floor_y + depth, 'reach': reach,
                         'least_bulge_radius': 1 / convex if convex > 0 else np.inf,
                         'least_inward_radius': 1 / concave if concave > 0 else np.inf})
    if coping:
        built = _with_coping(built, G, st, prof, closed=True, into_sign=1, feature=feature)
    return built


SOLID_TESS = dsl.Tess(.003, 15., .5)    # ledges and boxes: a 3 cm nose in 15 degree steps, stations 0.5 m apart


def ledge(outline, *, support_y, height, nose=.03, feature='ledge', tess=SOLID_TESS, material=dsl.LEDGE,
          grind=True, on_ground=False):
    """A ledge, box or manual pad over the closed plan footprint `outline` (Rounded(closed=True) or a closed Spline):
    a level ridable top at support_y + height, a rounded `nose` over vertical faces down to the support. The base
    faces close it over the footprint, which the network cuts out of the deck (review point 1: no buried faces under
    an intact deck); the footprint is the seam '<feature>.footprint'. With `grind`, a rail along the top arris."""
    if height < nose + .05:
        raise ValueError(f'{feature}: {height} m is too low for a {nose} m nose')
    top = support_y + height
    ride = {'material': material}
    prof = Profile([('arc', nose, -90., ride), ('line', height - nose, {'material': material, 'role': dsl.SIDE})],
                   start=(0., top))
    inward = 1 if _ccw(outline) else -1
    built, G, _ = transverse(outline, prof, side=-inward, offset=inward * nose, front='cap', back='base',
                              ground=support_y, feature=feature, tess=tess, on_ground=on_ground)
    mesh = built.mesh
    foot = G[:, -1]
    foot = foot[:-1] if np.linalg.norm(foot[0] - foot[-1]) < 1e-9 else foot
    base = np.unique(mesh.F[mesh.role == dsl.ROLE[dsl.BASE]])
    mesh.seams[f'{feature}.footprint'] = base[np.abs(mesh.V[base, 1] - support_y) < 1e-9]
    rails = []
    if grind:
        arris = G[:, 0]
        rails.append(edge_rail(arris, closed=True, feature=feature))
    built.checks.append({'feature': feature, 'kind': 'ledge', 'top_y': top, 'footprint': foot[:, [0, 2]].tolist()})
    return Built(mesh, rails, built.checks, built.foot)


def box(x0, z0, x1, z1, *, support_y, height, corner=.1, nose=.03, feature='box', **kw):
    """A box or manual pad: a rounded rectangle footprint (corner radius `corner`), see ledge."""
    return ledge(Rounded([(x0, z0), (x1, z0), (x1, z1), (x0, z1)], corner, closed=True), support_y=support_y,
                 height=height, nose=nose, feature=feature, **kw)


# ------------------------------------------------------------------------------------------------------------ tower

TOWER_FLANK = 30.   # degrees: the tower mound's earth-banked flanks, at most


def _heading(deg):
    a = math.radians(deg)
    return np.array([math.cos(a), math.sin(a)])


def place_crests(spec, roll_ins, gap=2., walls=None):
    """Crest points for roll-ins on the tower deck rectangle (spec 'centre', 'size'): each roll-in
    {id: (heading degrees, width)} goes on the side whose outward normal is nearest its heading, roll-ins sharing a side
    spread along it `gap` apart, each taking `walls` more each side (default bowl_reach(): its bowl walls at full
    height; 0 for none). Returns {id: (x, z)}; refuses roll-ins that do not fit their side."""
    walls = bowl_reach() if walls is None else float(walls)
    c = np.asarray(spec['centre'], 'f8'); hx, hz = spec['size'][0] / 2, spec['size'][1] / 2
    sides = {0: (np.array([1., 0.]), hx, hz), 90: (np.array([0., 1.]), hz, hx),
             180: (np.array([-1., 0.]), hx, hz), 270: (np.array([0., -1.]), hz, hx)}
    by_side = {}
    for rid, (h, w) in roll_ins.items():
        d = _heading(h)
        best = max(sides, key=lambda k: sides[k][0] @ d)
        by_side.setdefault(best, []).append((rid, w))
    out = {}
    for k, items in by_side.items():
        n, half, along = sides[k]
        t = np.array([-n[1], n[0]])
        total = sum(w + 2 * walls for _, w in items) + gap * (len(items) - 1)
        if total > 2 * along + 1e-9:
            raise ValueError(f'tower: roll-ins {[r for r, _ in items]} need {total:.1f} m on one side of '
                             f'{2 * along:.1f} m: widen the deck or turn one to another side')
        x = -total / 2
        for rid, w in items:
            out[rid] = tuple((c + n * half + t * (x + walls + w / 2)).tolist())
            x += w + 2 * walls + gap
    return out


def tower(spec, exits, ground, *, y=None, side=None, flanks='ground', flank_degrees=TOWER_FLANK, feature='tower',
          tess=TESS):
    """The drop-in tower (C's item: one owner for every plan point of its footprint): a flat deck at `y` (default
    spec['y']: the deck height is a parameter) whose outline runs through each roll-in's crest row, earth-banked
    flanks at `flank_degrees` from its free edges down to the `ground` (float or f(x, z)), and one roll-in per line
    in `exits` (layout.tower_exits(): crest, heading, rollin parts in r4's convention, width, the exit section s, y,
    point; optionally 'path', the line's plan Curve when the roll-in turns), each a ramp ending exactly on its exit
    section, where the line's own build starts. flanks='ground' (default): the deck's free edges and the roll-ins'
    riding edges are the foot loop, and A's landform is the mound (one surface round every roll-in; their own flanks
    would overlap each other on a high deck); flanks='bank': its own `flank_degrees` flanks (a low deck only). Open
    only along its foot loop (Built.foot). Refuses crest rows that cross or lie inside the deck, and a roll-in that misses its exit section."""
    deck_y = float(spec['y'] if y is None else y)
    g = as_ground(ground)
    if flanks not in ('ground', 'bank'):
        raise ValueError(f'{feature}: flanks are ground (the landform is the mound) or bank (its own 30 degree flanks)')
    side = side or Side('bowl', fade=(BOWL_FADE, 0.), outer='ground' if flanks == 'ground' else 'bank',
                        degrees=flank_degrees)
    if flanks == 'bank' and side.kind == 'ground':
        raise ValueError(f"{feature}: flanks='bank' needs roll-in sides of their own (not 'ground')")
    if side.kind == 'bowl' and flanks == 'ground' and side.outer not in (None, 'ground'):
        raise ValueError(f"{feature}: with flanks='ground' the landform meets the roll-ins' bowl caps (outer 'ground')")
    if side.kind == 'bowl' and (side.fade or (0., 0.))[0] <= 0:
        raise ValueError(f'{feature}: a roll-in\'s bowl walls must fade into the deck (fade[0] > 0)')
    parts, checks, rows = [], [], []
    for rid, ex in exits.items():
        h = _heading(ex['heading']); crest = np.asarray(ex['crest'], 'f8')
        path = ex.get('path') or Line(crest, crest + h * (float(ex['s']) + 1.))
        prof = from_additions(deck_y, 0., list(ex['rollin']))
        x_end = float(prof.end[0] - prof.start[0])
        if abs(x_end - float(ex['s'])) > 1e-6 or abs(float(prof.end[1]) - float(ex['y'])) > 1e-6:
            raise ValueError(f'{feature}: roll-in {rid} ends at s {x_end:.3f}, y {prof.end[1]:.3f}, not its exit section '
                             f's {ex["s"]:.3f}, y {ex["y"]:.3f} (the deck height {deck_y} must be the line\'s y0)')
        end = path.point([x_end])[0]
        if np.linalg.norm(end - np.asarray(ex['point'])) > .01:
            raise ValueError(f'{feature}: roll-in {rid} ends at {end.round(3).tolist()}, {np.linalg.norm(end - ex["point"]):.2f} m '
                             f'off its exit section: pass the line\'s plan curve as exits[{rid!r}]["path"]')
        b = ramp(path, prof, float(ex['width']), left=side, right=side, ground=g, ends=('flush', 'flush'),
                 feature=f'{rid}.rollin', tess=tess, on_ground=True)
        sm = b.mesh.seams
        row = b.mesh.V[_dedupe(sm[f'{rid}.rollin.start'], b.mesh.V)]
        N = np.array([-h[1], 0., h[0]])
        if (row[-1] - row[0]) @ N < 0:
            row = row[::-1]
        if side.kind == 'bowl':        # the walls are zero high at the crest: their caps lie on the deck's edge
            u = _horizontal(row[-1] - row[0])
            row = np.concatenate([[row[0] - side.width * u], row, [row[-1] + side.width * u]])
        rows.append((rid, row, h))
        parts.append(b.mesh); checks += b.checks
        checks.append({'feature': f'{rid}.rollin', 'kind': 'exit', 'line': rid, 's': x_end, 'y': float(prof.end[1]),
                       'degrees': prof.end_degrees, 'point': end.tolist(), 'heading': float(ex['heading'])})
    # the deck: the crest rows in order round it, joined by its free edges
    centre = np.mean([r[1][:, [0, 2]].mean(0) for r in rows], 0)
    rows.sort(key=lambda r: math.atan2(*(r[1][:, [0, 2]].mean(0) - centre)[::-1]))
    loop, free = [], []
    for i, (rid, row, h) in enumerate(rows):
        loop += list(row)
        nxt = rows[(i + 1) % len(rows)][1]
        a, b2 = row[-1], nxt[0]
        L = float(np.linalg.norm(b2 - a))
        if L > 1e-6:
            n = max(1, math.ceil(L / tess.max_edge))
            E = a + (b2 - a) * (np.arange(n + 1) / n)[:, None]
            free.append(E)
            loop += list(E[1:-1])
    loop = np.asarray(loop)
    if solids.segments_cross(loop[:, [0, 2]]):
        raise ValueError(f'{feature}: the roll-ins\' crest rows cross or overlap round the deck: '
                         f'{[r[0] for r in rows]}; move their crests apart (place_crests)')
    x = loop[:, 0] - loop[:, 0].mean(); z = loop[:, 2] - loop[:, 2].mean()
    area = .5 * (x * np.roll(z, -1) - np.roll(x, -1) * z).sum()
    if area <= 0:
        raise ValueError(f'{feature}: a crest row faces into the deck (headings must point away from it)')
    parts.append(solids.polygon(loop, outward=[0., 1., 0.], feature=feature, material=spec.get('material', dsl.DECK),
                                role=dsl.RIDING))
    for E in free if flanks == 'bank' else ():
        t = _horizontal(E[-1] - E[0])
        D = np.broadcast_to(np.array([t[2], 0., -t[0]]), E.shape).copy()      # outward: right of a CCW loop
        m, _, _ = _flank_mesh(E, D, side, g, 0., feature)
        if m is not None:
            parts.append(m)
    mesh = dsl.Mesh.concat(parts)
    foot = solids.check_open(mesh, name=feature)
    checks.append({'feature': feature, 'kind': 'tower', 'deck_y': deck_y, 'deck_area_m2': float(area),
                   'roll_ins': [r[0] for r in rows]})
    return Built(mesh, [], checks, foot)


def exit_of(crest, heading, rollin, width, deck_y, path=None):
    """The exits entry (as layout.tower_exits) of a roll-in from `crest` (x, z) heading `heading` degrees with r4-style
    `rollin` parts from the deck at deck_y, along `path` (default straight): its exit section s, y, degrees, point."""
    prof = from_additions(deck_y, 0., list(rollin))
    s = float(prof.end[0] - prof.start[0])
    c = np.asarray(crest, 'f8')
    line = path or Line(c, c + _heading(heading) * (s + 1.))
    p = line.point([s])[0]; d = line.tangent([s])[0]
    out = {'crest': tuple(c.tolist()), 'heading': float(heading), 'rollin': tuple(rollin), 's': s,
           'y': float(prof.end[1]), 'degrees': prof.end_degrees, 'point': tuple(p.tolist()),
           'exit_heading': math.degrees(math.atan2(d[1], d[0])), 'width': float(width)}
    if path is not None:
        out['path'] = path
    return out
