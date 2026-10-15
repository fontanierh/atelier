"""The crater floor round the owner's editor park, after the approved Sunburst concept
(assets/craterpark/concepts/editor/crater-floor.jpg): broad fields of snow over cool grey volcanic ground, mats of
yellow-green and olive moss, jagged grey crags and slabs gathered toward the crater's wall, clusters of small conifers,
yellow and orange autumn shrubs, angular rocks, stones and dry grass.

Everything stands on the ground the game draws (Site): the volcano's natural ground blended into the editor's cut
ground by its weight (craterpark/placement.py _follow), sampled as the volcano's 5 m mesh samples it
(hidamari/mountains.py height), inside the crater's crest. Placement is deterministic: jittered grids and value noise
hashed from positions, never a global random state. The snow and moss are sheets cut from noise fields (marching
squares), so they lie in broad connected shapes with soft irregular edges.

The riding stays clear: nothing within CLEAR of a piece's plan (BOWL_CLEAR round a bowl, and further round a tall
viaduct's battered foot), nothing taller than LOW within END_REACH of a piece's end, and nothing at all in the run-out
past an end that meets the ground. No snow lies on anything ridden: the fields are on the volcano's ground only.

The rocks and crags are solid (side faces, with collision); the snow, moss, grass, shrubs and conifers are drawn only
(the coping role: rendered, no collision), so a rider crossing the floor is never tripped by a mat's edge.
"""
import math

import numpy as np

from . import dsl
from .editor_supports import Builder, Ground, _outer_half

ROCK = 'material_027'         # the volcano's restyled rock (as the viaducts' boulders)
SNOW = 'material_034'         # snow, flat
GRASS = 'material_035'        # dry golden grass, two-sided blades
MOSS = 'material_036'         # yellow-green moss and low bushes
SHRUB = 'material_037'        # autumn orange shrubs
OLIVE = 'material_042'        # olive moss mats
CONIFER = 'material_043'      # dark green conifers
GOLD = 'material_044'         # golden-yellow autumn shrubs
SOLID = {ROCK}                # materials with collision; the rest are drawn only (the crags and rocks are ROCK too:
                              # the basalt painting's columns read as flutes on a crag)

CLEAR = 4.            # metres kept clear round every piece's plan...
BOWL_CLEAR = 8.       # ...and round a bowl (its pit and deck)
PIER_OUT = 1.5        # a viaduct pier's plinth and relief stand this far out of the piece's plan...
BATTER = .05          # ...and its faces lean out this much per metre of height (editor_supports.BATTER, BATTER_MAX)
BATTER_MAX = 6.
END_REACH = 15.       # within this of a piece's end, nothing taller than LOW
LOW = 1.5
EXIT_LEN = 40.        # a piece's end within EXIT_GROUND of the ground runs out onto it: this run-out is kept clear,
EXIT_SIDE = 5.        # as wide as the piece and this much more each side
EXIT_GROUND = 3.
CREST_MARGIN = 10.    # metres inside the crater's crest, where the dressing stops
CELL = 1.             # metres per cell of the clearance field
SLOPE_SNOW, SLOPE_PLANT, SLOPE_ROCK = 24., 30., 38.   # degrees: the steepest ground each kind is placed on
SNOW_COVER = .28      # the share of the open floor (clear of the riding) under snow drifts...
MOSS_COVER = .07      # ...and under each of the two moss mats (yellow-green, olive), off the snow
WIND = (.8, .6)       # plan direction the snow drifts in, behind every crag (unit)
BAND = 18.            # metres inside the wall's foot that the band of crags reaches (and WALL_UP up the wall)
WALL_UP = 60.
SLOPE_CRAG = 45.      # degrees: crags stand on the wall's foot too
SNOW_CELL, MOSS_CELL = 3., 2.   # metres between the fields' samples
SITE_STEP = 5.        # the volcano's mesh spacing (hidamari/mountains.py STEP)
BAKE_TILE = 48.       # metres: the dressing's occlusion is baked in plan tiles, each grid this and ao.AO_REACH round it


# ---------------------------------------------------------------- deterministic noise
def _hash(*keys):
    """Uniform [0, 1) from integer keys (arrays broadcast): FNV-1a with a final avalanche, deterministic everywhere."""
    keys = np.broadcast_arrays(*[np.asarray(k, 'i8') for k in keys])
    h = np.full(keys[0].shape, 2166136261, 'u8')
    m = np.uint64(0xffffffff)
    for k in keys:
        h = ((h ^ (k.astype('u8') & m)) * np.uint64(16777619)) & m
    h ^= h >> np.uint64(16)
    h = (h * np.uint64(0x7feb352d)) & m
    h ^= h >> np.uint64(15)
    h = (h * np.uint64(0x846ca68b)) & m
    h ^= h >> np.uint64(16)
    return h.astype('f8') / 2 ** 32


def _noise(x, z, scale, seed):
    """Smooth value noise in [0, 1) at `scale` metres."""
    x, z = np.asarray(x, 'f8') / scale, np.asarray(z, 'f8') / scale
    i, j = np.floor(x), np.floor(z)
    u, v = x - i, z - j
    u, v = u * u * (3 - 2 * u), v * v * (3 - 2 * v)
    i, j = i.astype('i8'), j.astype('i8')
    a, b = _hash(i, j, seed), _hash(i + 1, j, seed)
    c, d = _hash(i, j + 1, seed), _hash(i + 1, j + 1, seed)
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v


def _r(seed, k):
    """One uniform [0, 1) per (item seed, draw)."""
    return float(_hash(int(seed), k, 977))


# ---------------------------------------------------------------- the ground
class Site:
    """The ground the game draws (native y at native x, z) and how far inside the crater's crest a point lies."""

    def __init__(self, ground, inside, bounds, foot=None):
        self.ground, self.inside, self.bounds = ground, inside, bounds   # bounds: (x0, z0, x1, z1) native
        # metres inside the foot of the crater's wall (negative up the wall); none on a bare grid
        self.foot = foot or (lambda x, z: np.full(np.shape(x), np.inf))

    @classmethod
    def flat(cls, heights, grid):
        """The editor's cut ground alone, the whole grid counted as crater floor (tests, previews)."""
        g = grid
        return cls(Ground(heights, grid), lambda x, z: np.full(np.shape(x), np.inf),
                   (g['x0'], g['z0'], g['x0'] + g['nx'] * g['G'], g['z0'] + g['nz'] * g['G']))

    @classmethod
    def volcano(cls, heights, weight, grid):
        """The volcano's own ground round the park, as the game builds it: on its 5 m nodes the natural ground follows
        the editor's cut ground by its weight (placement._follow), and between them it is sampled as the volcano's mesh
        (two triangles a cell, mountains._barycentric). `inside` is metres inside the crest (mountains.rim_radius)."""
        from craterpark import placement
        from hidamari import mountains
        g = grid
        corners = np.array([[x, 0., z] for x in (g['x0'], g['x0'] + g['nx'] * g['G'])
                            for z in (g['z0'], g['z0'] + g['nz'] * g['G'])])
        isl = placement.native_to_island(corners)
        cx, cy = mountains.VOLCANO
        reach = mountains.RIM_RADIUS + 60.
        lo = np.maximum(isl[:, :2].min(0), (cx - reach, cy - reach))
        hi = np.minimum(isl[:, :2].max(0), (cx + reach, cy + reach))
        b0, b1 = mountains.BOUNDS[0], mountains.BOUNDS[1]
        i0, j0 = int((lo[0] - b0) // SITE_STEP) - 1, int((lo[1] - b1) // SITE_STEP) - 1
        i1, j1 = int((hi[0] - b0) // SITE_STEP) + 2, int((hi[1] - b1) // SITE_STEP) + 2
        X, Y = np.meshgrid(b0 + np.arange(i0, i1 + 1) * SITE_STEP, b1 + np.arange(j0, j1 + 1) * SITE_STEP)
        H = np.asarray(heights, 'f8').reshape(g['nz'], g['nx'])
        W = np.asarray(weight, 'f8').reshape(g['nz'], g['nx'])
        Z = placement._follow(X, Y, mountains.natural_height(X, Y), g, H, W) - placement.LIFT
        _, _, r, angle = mountains.polar(X, Y)
        crest = mountains.rim_radius(angle) - r
        foot = mountains.wall_foot(angle) - r

        def lookup(field):
            def at(x, z):
                x, z = np.broadcast_arrays(np.asarray(x, 'f8'), np.asarray(z, 'f8'))
                p = placement.native_to_island(np.stack([x, np.zeros_like(x), z], -1))
                fi = (p[..., 0] - X[0, 0]) / SITE_STEP
                fj = (p[..., 1] - Y[0, 0]) / SITE_STEP
                i = np.clip(np.floor(fi).astype(int), 0, X.shape[1] - 2)
                j = np.clip(np.floor(fj).astype(int), 0, X.shape[0] - 2)
                u, v = np.clip(fi - i, 0, 1), np.clip(fj - j, 0, 1)
                return mountains._barycentric(field[j, i], field[j, i + 1], field[j + 1, i], field[j + 1, i + 1], u, v)
            return at

        # the crater's plan bounds, native
        ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        rr = mountains.rim_radius(ang)
        ring = np.stack([cx + rr * np.cos(ang), cy + rr * np.sin(ang)], -1)
        nx_, nz_ = placement.island_to_native_xz(ring[:, 0], ring[:, 1])
        return cls(lookup(Z), lookup(crest), (nx_.min(), nz_.min(), nx_.max(), nz_.max()), lookup(foot))

    def slope(self, x, z, h=2.5):
        """Degrees, over +-h metres."""
        gx = (self.ground(x + h, z) - self.ground(x - h, z)) / (2 * h)
        gz = (self.ground(x, z + h) - self.ground(x, z - h)) / (2 * h)
        return np.degrees(np.arctan(np.hypot(gx, gz)))


# ---------------------------------------------------------------- what the riding keeps clear
class Clear:
    """The pieces' plan, each point with the clearance it needs, as a weighted distance field on a CELL grid: free(x, z)
    is the plan metres a point keeps beyond every piece's clearance. Also the pieces' ends and their run-outs."""

    def __init__(self, pieces, site, bounds):
        x0, z0, x1, z1 = bounds
        self.x0, self.z0 = x0 - 40., z0 - 40.
        self.nx, self.nz = int((x1 - x0 + 80.) / CELL) + 1, int((z1 - z0 + 80.) / CELL) + 1
        f = np.full((self.nz, self.nx), np.inf)
        reach = 0.
        self.ends, self.runs = [], []
        for p in pieces:
            meta = p.metadata
            P = _samples(np.asarray(p.mesh.V, 'f8'), np.asarray(p.mesh.F))
            kind = meta['type']
            st = meta.get('stations') or []
            if st:                                    # the stations across the piece's width: a jump's open gap too
                d = np.array([s['d'] for s in st], 'f8')
                t = np.arange(d[0], d[-1] + .5, .5) if d[-1] > d[0] else d[:1]
                half = np.interp(t, d, [_outer_half(s) for s in st])
                h = np.interp(t, d, np.unwrap(np.radians([s['h'] for s in st])))
                cx, cy, cz = (np.interp(t, d, [s[k] for s in st]) for k in ('x', 'y', 'z'))
                for v in np.linspace(-1, 1, 9):
                    P = np.concatenate([P, np.stack([cx - v * half * np.sin(h), cy, cz + v * half * np.cos(h)], 1)])
            need = np.full(len(P), BOWL_CLEAR if kind == 'bowl' else CLEAR)
            if kind not in ('bowl', 'deck', 'rail') and meta.get('stations'):
                over = np.maximum(P[:, 1] - site.ground(P[:, 0], P[:, 2]), 0.)
                need = need + np.where(over > 1., PIER_OUT + np.minimum(BATTER * over, BATTER_MAX), 0.)
            i = np.round((P[:, 0] - self.x0) / CELL).astype(int)
            j = np.round((P[:, 2] - self.z0) / CELL).astype(int)
            on = (i >= 0) & (i < self.nx) & (j >= 0) & (j < self.nz)
            np.minimum.at(f, (j[on], i[on]), -need[on])
            reach = max(reach, float(need.max()) if len(need) else 0.)
            if kind in ('bowl', 'deck', 'rail') or len(st) < 2:
                continue
            for s, sign in ((st[0], -1.), (st[-1], 1.)):
                self.ends.append((s['x'], s['z']))
                if s['y'] - float(site.ground(s['x'], s['z'])) < EXIT_GROUND:
                    h = math.radians(s['h'])
                    self.runs.append((s['x'], s['z'], sign * math.cos(h), sign * math.sin(h),
                                      _outer_half(s) + EXIT_SIDE))
        # chamfer propagation (8 neighbours) far enough for the largest clearance and the largest item
        shifts = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx]
        for _ in range(int(math.ceil((reach + 12.) / CELL))):
            p = np.pad(f, 1, constant_values=np.inf)
            f = np.minimum.reduce([f] + [p[1 + dy:1 + dy + self.nz, 1 + dx:1 + dx + self.nx] + math.hypot(dy, dx) * CELL
                                         for dy, dx in shifts])
        self.f = f
        self.E = np.array(self.ends, 'f8').reshape(-1, 2)

    def free(self, x, z):
        i = np.clip(np.round((np.asarray(x) - self.x0) / CELL).astype(int), 0, self.nx - 1)
        j = np.clip(np.round((np.asarray(z) - self.z0) / CELL).astype(int), 0, self.nz - 1)
        return self.f[j, i]

    def near_end(self, x, z):
        """Plan metres to the nearest piece end."""
        if not len(self.E):
            return np.full(np.shape(x), np.inf)
        x, z = np.asarray(x, 'f8'), np.asarray(z, 'f8')
        return np.sqrt(((x[..., None] - self.E[:, 0]) ** 2 + (z[..., None] - self.E[:, 1]) ** 2).min(-1))

    def in_run(self, x, z, r):
        """True where a disc of radius r touches a run-out."""
        x, z = np.asarray(x, 'f8'), np.asarray(z, 'f8')
        hit = np.zeros(x.shape, bool)
        for ox, oz, dx, dz, half in self.runs:
            along = (x - ox) * dx + (z - oz) * dz
            across = np.abs(-(x - ox) * dz + (z - oz) * dx)
            hit |= (along > -r) & (along < EXIT_LEN + r) & (across < half + r)
        return hit


def _samples(V, F, step=.8):
    """Points over every triangle (vertices included), no further apart than about `step` metres."""
    if not len(F):
        return V.reshape(-1, 3)
    T = V[F]
    edge = np.max([np.linalg.norm(T[:, a] - T[:, b], axis=1) for a, b in ((0, 1), (1, 2), (2, 0))], 0)
    n = np.clip(np.ceil(edge / step), 1, 64).astype(int)
    out = [V]
    for k in np.unique(n):
        if k < 2:
            continue
        a, b = np.meshgrid(np.arange(k + 1), np.arange(k + 1))
        keep = a + b <= k
        w = np.stack([a[keep], b[keep]], 1) / k
        t = T[n == k]
        out.append((t[:, None, 0] * (1 - w[:, :1] - w[:, 1:]) + t[:, None, 1] * w[:, :1]
                    + t[:, None, 2] * w[:, 1:]).reshape(-1, 3))
    return np.concatenate(out)


# ---------------------------------------------------------------- the pieces of dressing
_SPHERE = None


def _sphere():
    """A once-subdivided icosahedron (unit radius, 80 faces): the moss mounds and shrub lumps."""
    global _SPHERE
    if _SPHERE is None:
        t = (1 + 5 ** .5) / 2
        P = [np.array(p, 'f8') for p in ((-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
                                         (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1))]
        P = [p / np.linalg.norm(p) for p in P]
        F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
             (8, 6, 7), (9, 8, 1)]
        mids, F2 = {}, []
        for a, b, c in F:
            m = []
            for i, j in ((a, b), (b, c), (c, a)):
                key = (min(i, j), max(i, j))
                if key not in mids:
                    q = P[i] + P[j]
                    P.append(q / np.linalg.norm(q))
                    mids[key] = len(P) - 1
                m.append(mids[key])
            F2 += [(a, m[0], m[2]), (b, m[1], m[0]), (c, m[2], m[1]), (m[0], m[1], m[2])]
        _SPHERE = np.array(P), np.array(F2)
    return _SPHERE


def _add_flat(b, material, T):
    """Triangles (n, 3, 3), each its own flat-shaded face."""
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    b.add(material, (T.reshape(-1, 3), np.arange(len(T) * 3).reshape(-1, 3), np.repeat(n, 3, axis=0)))
    return len(T)


def _lump(b, material, site, x, z, r, h, seed, lift, cap=None):
    """A squashed faceted lump (radius r, height h) with its centre `lift` x h above the ground; `cap` keeps only the
    faces above that height of the unit sphere (a mound). Returns its triangles."""
    P, F = _sphere()
    bump = np.array([1 + .35 * (_r(seed, i) - .5) for i in range(len(P))])
    yaw = _r(seed, 200) * 2 * np.pi
    S = P * bump[:, None] * [r * (1 + .25 * _r(seed, 201)), h / 2, r]
    S = S @ np.array([[math.cos(yaw), 0, -math.sin(yaw)], [0, 1, 0], [math.sin(yaw), 0, math.cos(yaw)]])
    ring = np.linspace(0, 2 * np.pi, 6, endpoint=False)
    g = min(float(site.ground(x, z)), float(site.ground(x + r * np.cos(ring), z + r * np.sin(ring)).min()))
    S += [x, g + lift * h, z]                    # on the lowest ground under it: never floating on a slope
    if cap is not None:
        F = F[(P[F][:, :, 1].mean(1) > cap)]
    return _add_flat(b, material, S[F])


_ICO20 = np.array([(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
                   (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
                   (6, 2, 10), (8, 6, 7), (9, 8, 1)])


def _bush(b, material, site, x, z, r, h, seed):
    """An autumn bush r across (half) and h high: a lumpy icosahedron (20 faces) sitting on the lowest ground under
    it. Returns its triangles."""
    P = _sphere()[0][:12]
    bump = np.array([1 + .45 * (_r(seed, i) - .5) for i in range(12)])
    yaw = _r(seed, 3) * 2 * np.pi
    S = P * bump[:, None] * [r * (1 + .25 * _r(seed, 5)), h / 2, r]
    S = S @ np.array([[math.cos(yaw), 0, -math.sin(yaw)], [0, 1, 0], [math.sin(yaw), 0, math.cos(yaw)]])
    ring = np.linspace(0, 2 * np.pi, 5, endpoint=False)
    g = min(float(site.ground(x, z)), float(site.ground(x + r * np.cos(ring), z + r * np.sin(ring)).min()))
    S += [x, g + .4 * h, z]
    return _add_flat(b, material, S[_ICO20])


def _stone(b, site, x, z, r, seed):
    """A small half-buried faceted stone (an icosahedron, 20 faces).
    Returns its triangles."""
    P = _sphere()[0][:12]
    F = _ICO20
    bump = np.array([1 + .4 * (_r(seed, i) - .5) for i in range(12)])
    yaw = _r(seed, 3) * 2 * np.pi
    S = P * bump[:, None] * [r * (1 + .3 * _r(seed, 5)), r * .62, r]
    S = S @ np.array([[math.cos(yaw), 0, -math.sin(yaw)], [0, 1, 0], [math.sin(yaw), 0, math.cos(yaw)]])
    S += [x, float(site.ground(x, z)) - .3 * r, z]
    return _add_flat(b, ROCK, S[F])


def _cushion(b, material, site, x, z, r, h, seed):
    """A low cushion of moss, r across and h high, faceted: 18 faces. Returns its triangles."""
    n = 6
    a = (np.arange(n) + .5 * (np.array([_r(seed, i) for i in range(n)]) - .5)) * 2 * np.pi / n
    k = np.array([.75 + .45 * _r(seed, 10 + i) for i in range(n)]) * r
    px, pz = x + k * np.cos(a), z + k * np.sin(a)
    foot = np.stack([px, site.ground(px, pz) - .06, pz], 1)
    mx, mz = x + .72 * k * np.cos(a + .2), z + .72 * k * np.sin(a + .2)
    mid = np.stack([mx, site.ground(mx, mz) + h * (.5 + .2 * np.array([_r(seed, 20 + i) for i in range(n)])), mz], 1)
    top = np.array([x, float(site.ground(x, z)) + h, z])
    T = []
    for i in range(n):
        j = (i + 1) % n
        T += [(foot[i], foot[j], mid[j]), (foot[i], mid[j], mid[i]), (mid[i], mid[j], top)]
    T = np.array(T)
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    flip = nrm[:, 1] < 0
    T[flip] = T[flip][:, [0, 2, 1]]
    return _add_flat(b, material, T)


def _block(b, site, x, z, w, d, h, yaw, seed, material=ROCK):
    """An angular rock block (the concepts' broken basalt): a jittered prism w x d (half) and h above the highest
    ground under it, its top tilted and bevelled, its foot sunk under the lowest. Returns its triangles."""
    n = 5 + int(_r(seed, 1) * 3)
    a = (np.arange(n) + .6 * (np.array([_r(seed, 10 + k) for k in range(n)]) - .5)) * 2 * np.pi / n
    k = np.array([.8 + .35 * _r(seed, 20 + i) for i in range(n)])
    u, v = np.cos(a) * w * k, np.sin(a) * d * k
    c, s = math.cos(yaw), math.sin(yaw)
    px, pz = x + u * c - v * s, z + u * s + v * c
    g = site.ground(px, pz)
    tilt = np.array([_r(seed, 30) - .5, _r(seed, 31) - .5]) * .5
    top = g.max() + h + (u * tilt[0] + v * tilt[1]) + .12 * h * np.array([_r(seed, 40 + i) - .5 for i in range(n)])
    bevel = np.clip(.22 * h, .15, .6)
    bottom = np.stack([px, np.full(n, g.min() - .8), pz], 1)
    mid = np.stack([px, top - bevel, pz], 1)
    cx, cz = px.mean(), pz.mean()
    inset = .72 + .1 * _r(seed, 50)
    upper = np.stack([cx + (px - cx) * inset, top, cz + (pz - cz) * inset], 1)
    peak = np.array([cx + (u * c - v * s).mean() * .1, top.max() + .04 * h, cz])
    T = []
    for i in range(n):
        j = (i + 1) % n
        T += [(bottom[i], bottom[j], mid[j]), (bottom[i], mid[j], mid[i]),
              (mid[i], mid[j], upper[j]), (mid[i], upper[j], upper[i]), (upper[i], upper[j], peak)]
    T = np.array(T)
    # every face outward from the block's axis
    centre = np.array([cx, (g.min() + top.max()) / 2, cz])
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    flip = (nrm * (T.mean(1) - centre)).sum(1) < 0
    T[flip] = T[flip][:, [0, 2, 1]]
    return _add_flat(b, material, T)


def _field(b, material, site, xs, zs, f, t, lift, edge, min_area=0.):
    """The ground where the field f (len(zs), len(xs)) on the grid xs, zs reaches t, as one draped sheet (marching
    squares: every cell clipped to f >= t, its edges cut where f crosses t, so the outline is soft and irregular):
    LIFT over the ground where f is EDGE over t, its rim tucked just under the ground; pieces of it smaller than
    MIN_AREA square metres are left out. Returns (triangles, area)."""
    nz, nx = f.shape
    inside = f >= t
    key, V = {}, []

    def vertex(k, x, z, value):
        if k not in key:
            key[k] = len(V)
            V.append((x, z, value))
        return key[k]

    def corner(j, i):
        return vertex(('c', j, i), xs[i], zs[j], f[j, i])

    def cut(j0, i0, j1, i1):
        a, c = f[j0, i0], f[j1, i1]
        u = (t - a) / (c - a)
        return vertex(('e', j0, i0, j1, i1), xs[i0] + u * (xs[i1] - xs[i0]), zs[j0] + u * (zs[j1] - zs[j0]), t)

    F = []
    any_in = inside[:-1, :-1] | inside[:-1, 1:] | inside[1:, :-1] | inside[1:, 1:]
    for j, i in zip(*np.nonzero(any_in)):
        ring = ((j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i))
        poly = []
        for k in range(4):
            (ja, ia), (jb, ib) = ring[k], ring[(k + 1) % 4]
            if inside[ja, ia]:
                poly.append(corner(ja, ia))
            if inside[ja, ia] != inside[jb, ib]:
                poly.append(cut(ja, ia, jb, ib) if (ja, ia) < (jb, ib) else cut(jb, ib, ja, ia))
        F += [(poly[0], poly[k], poly[k + 1]) for k in range(1, len(poly) - 1)]
    if not F:
        return 0, 0.
    V = np.array(V)
    F = np.array(F)
    if min_area > 0:
        parent = np.arange(len(V))

        def root(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for a, c, d in F:
            ra, rc, rd = root(a), root(c), root(d)
            parent[rc] = ra
            parent[rd] = ra
        comp = np.array([root(i) for i in F[:, 0]])
        e1, e2 = V[F[:, 1], :2] - V[F[:, 0], :2], V[F[:, 2], :2] - V[F[:, 0], :2]
        size = np.bincount(comp, np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2, minlength=len(V))
        F = F[size[comp] >= min_area]
        if not len(F):
            return 0, 0.
        used = np.unique(F)
        remap = np.full(len(V), -1)
        remap[used] = np.arange(len(used))
        V, F = V[used], remap[F]
    x, z, value = V[:, 0], V[:, 1], V[:, 2]
    y = site.ground(x, z) + (lift + .03) * _smooth((value - t) / edge) - .03
    P = np.stack([x, y, z], 1)
    # the ground's own normal under each vertex: the sheet shades as the ground it lies on
    h = 1.5
    gx = (site.ground(x + h, z) - site.ground(x - h, z)) / (2 * h)
    gz = (site.ground(x, z + h) - site.ground(x, z - h)) / (2 * h)
    N = np.stack([-gx, np.ones_like(gx), -gz], 1)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    T = P[F]
    area = float(np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1).sum() / 2)
    b.add(material, (P, F, N))
    return len(F), area


def _spire(b, site, x, z, w, d, h, yaw, lean, seed, material=ROCK):
    """A jagged rock spire or slab (the concepts' broken grey crags): an angular prism w x d (half) narrowing to a
    sharp crest h over the highest ground under it, leaning by `lean` (metres of top offset, x and z), its foot sunk
    under the lowest. Flat-shaded, sharp facets. Returns its triangles."""
    n = 4 + int(_r(seed, 1) * 3)
    a = (np.arange(n) + .7 * (np.array([_r(seed, 10 + k) for k in range(n)]) - .5)) * 2 * np.pi / n
    k = np.array([.75 + .45 * _r(seed, 20 + i) for i in range(n)])
    u, v = np.cos(a) * w * k, np.sin(a) * d * k
    c, s = math.cos(yaw), math.sin(yaw)
    px, pz = x + u * c - v * s, z + u * s + v * c
    g = site.ground(px, pz)
    base = g.max()

    def ring(frac, inset, jitter):
        """The section `frac` of the way up: inset toward the axis (and its lean), each corner jittered up and down."""
        cx, cz = x + lean[0] * frac, z + lean[1] * frac
        y = base + frac * h + jitter * h * (np.array([_r(seed, 100 * frac + 30 + i) for i in range(n)]) - .5)
        return np.stack([cx + (px - x) * inset, y, cz + (pz - z) * inset], 1)

    bottom = np.stack([px, np.full(n, g.min() - 1.), pz], 1)
    mid = ring(.5 + .15 * _r(seed, 2), .8 + .1 * _r(seed, 3), .12)
    top = ring(.88, .32 + .2 * _r(seed, 4), .1)
    peak = np.array([x + lean[0] + .25 * w * (_r(seed, 5) - .5), base + h, z + lean[1] + .25 * d * (_r(seed, 6) - .5)])
    T = []
    for i in range(n):
        j = (i + 1) % n
        T += [(bottom[i], bottom[j], mid[j]), (bottom[i], mid[j], mid[i]),
              (mid[i], mid[j], top[j]), (mid[i], top[j], top[i]), (top[i], top[j], peak)]
    T = np.array(T)
    centre = np.array([x + lean[0] / 2, (g.min() + base + h) / 2, z + lean[1] / 2])
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    flip = (nrm * (T.mean(1) - centre)).sum(1) < 0
    T[flip] = T[flip][:, [0, 2, 1]]
    return _add_flat(b, material, T)


def _crag(b, site, x, z, size, tall, seed):
    """A crag of broken grey rock: two to five spires and slabs over `size` metres across, the tallest `tall` high near its
    middle, the slabs upright or leaning out. Returns (spires, triangles)."""
    n = 2 + int(_r(seed, 1) * 4)
    tris = 0
    heading = 2 * np.pi * _r(seed, 2)
    for m in range(n):
        a = heading + 2 * np.pi * m / n + .8 * (_r(seed, 10 + m) - .5)
        d = 0. if m == 0 else .28 * size * (.5 + _r(seed, 20 + m))
        sx, sz = x + d * math.cos(a), z + d * math.sin(a)
        h = tall * (.8 + .2 * _r(seed, 30 + m)) * (1. if m == 0 else .4 + .45 * _r(seed, 40 + m))
        slab = _r(seed, 50 + m) < .45
        w = size * (.2 + .1 * _r(seed, 60 + m))
        dd = w * (.3 + .15 * _r(seed, 70 + m) if slab else .7 + .3 * _r(seed, 70 + m))
        out = .12 * h * _r(seed, 80 + m)
        tris += _spire(b, site, sx, sz, w, dd, h, a + np.pi / 2 if slab else 2 * np.pi * _r(seed, 90 + m),
                       (out * math.cos(a), out * math.sin(a)), int(seed) * 11 + m, ROCK)
    return n, tris


def _splat(field, xs, zs, x, z, reach, value):
    """field (len(zs), len(xs)) raised to value(dx, dz) (arrays of offsets from x, z) within `reach` of x, z."""
    i0, i1 = np.searchsorted(xs, x - reach), np.searchsorted(xs, x + reach)
    j0, j1 = np.searchsorted(zs, z - reach), np.searchsorted(zs, z + reach)
    if i1 <= i0 or j1 <= j0:
        return
    dx, dz = np.meshgrid(xs[i0:i1] - x, zs[j0:j1] - z)
    field[j0:j1, i0:i1] = np.maximum(field[j0:j1, i0:i1], value(dx, dz))


def _conifer(b, site, x, z, h, seed):
    """A small stylised conifer h tall: a short trunk and three stacked cones, dark green. Returns its triangles."""
    n = 7
    g = float(site.ground(x, z)) - .2
    th = (np.arange(n) + _r(seed, 1)) * 2 * np.pi / n
    T = []
    r0 = h * (.3 + .06 * _r(seed, 2))
    trunk = .06 * h
    for t in range(n):                                   # the trunk, up into the lowest cone
        a, c = th[t], th[(t + 1) % n]
        p = [np.array([x + trunk * math.cos(q), y, z + trunk * math.sin(q)]) for q in (a, c) for y in (g, g + .3 * h)]
        T += [(p[0], p[2], p[3]), (p[0], p[3], p[1])]
    for k in range(3):
        r = r0 * (1 - .27 * k)
        y0 = g + h * (.2 + .24 * k)
        apex = np.array([x, g + h * (.55 + .225 * k) if k < 2 else g + h, z])
        ring = [np.array([x + r * math.cos(q), y0 + .04 * h * (_r(seed, 10 * k + t) - .5), z + r * math.sin(q)])
                for t, q in enumerate(th)]
        hub = np.array([x, y0 + .06 * h, z])
        for t in range(n):
            T += [(ring[t], ring[(t + 1) % n], apex), (ring[(t + 1) % n], ring[t], hub)]
    T = np.array(T)
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    centre = np.array([x, g + .5 * h, z])
    flip = (nrm * (T.mean(1) - centre)).sum(1) < 0
    T[flip] = T[flip][:, [0, 2, 1]]
    return _add_flat(b, CONIFER, T)


def _tuft(b, site, x, z, h, seed):
    """A tuft of dry grass: four to six blades leaning out from one root. Returns its triangles."""
    n = 4 + int(_r(seed, 1) * 3)
    g = float(site.ground(x, z)) - .05
    T = []
    for k in range(n):
        a = (k + .7 * _r(seed, 10 + k)) * 2 * np.pi / n
        lean = (.25 + .3 * _r(seed, 20 + k)) * h
        tall = h * (.7 + .3 * _r(seed, 30 + k))
        w = .05 + .04 * _r(seed, 40 + k)
        ca, sa = math.cos(a), math.sin(a)
        root = np.array([x + .04 * ca, g, z + .04 * sa])
        T.append((root + [-w * sa, 0, w * ca], root + [w * sa, 0, -w * ca],
                  np.array([x + lean * ca, g + tall, z + lean * sa])))
    T = np.array(T)
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
    nrm = nrm * .4 + [0, .9, 0]                  # soft, mostly up-facing light, as grass
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    b.add(GRASS, (T.reshape(-1, 3), np.arange(len(T) * 3).reshape(-1, 3), np.repeat(nrm, 3, axis=0)))
    return len(T)


def _jitter(bounds, cell, seed):
    """One candidate per cell of a `cell`-metre grid over bounds, jittered within it: (x, z, key)."""
    x0, z0, x1, z1 = bounds
    i, j = np.meshgrid(np.arange(int((x1 - x0) // cell) + 1), np.arange(int((z1 - z0) // cell) + 1))
    i, j = i.ravel(), j.ravel()
    x = x0 + (i + _hash(i, j, seed, 1)) * cell
    z = z0 + (j + _hash(i, j, seed, 2)) * cell
    return x, z, (i * 7919 + j * 104729 + seed * 15485863) % (2 ** 31)


def _ok(site, clear, x, z, r, slope, tall=0.):
    """Candidates inside the crater, on ground no steeper than `slope`, keeping clear of the riding (r: plan radius,
    tall: metres it stands above the ground)."""
    ok = (site.inside(x, z) > CREST_MARGIN + r) & (site.slope(x, z) <= slope)
    ok &= clear.free(x, z) >= r
    ok &= ~clear.in_run(x, z, r)
    if tall > LOW:
        ok &= clear.near_end(x, z) >= END_REACH + r
    return ok


def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def build(pieces, heights, grid, site=None, bake=True):
    """The crater floor's dressing round the kept editor pieces (bridge Pieces), as dsl Mesh parts, and a summary.
    `site` is the ground to stand on (Site.volcano in the build; the cut ground alone, Site.flat, by default); `bake`
    bakes the parts' own occlusion (bake_tiles).

    As the concept (crater-floor.jpg), read from above: a broken band of big dark basalt crags along the foot of the
    wall and islands of them out on the floor; snow over about SNOW_COVER of the open floor, drifted in the crags' lee
    and along the wall's foot; big mats of saturated olive and gold moss and clumps of gold and orange bushes round
    the crags and the wall; clusters of conifers near the wall; blocks, stones and grass between.
    """
    site = site or Site.flat(heights, grid)
    clear = Clear(pieces, site, site.bounds)
    b = Builder()
    count = {'crags': 0, 'spires': 0, 'rocks': 0, 'stones': 0, 'conifers': 0, 'shrubs': 0, 'tufts': 0, 'cushions': 0,
             'snow_m2': 0, 'moss_m2': 0}
    bounds = site.bounds

    def wall(x, z):
        return _smooth(1 - (site.inside(x, z) - 50.) / 120.)

    def rough(x, z):
        """Where the dressing gathers: 0 on the open ground, 1 in a patch; the wall's foot is rougher."""
        n = .65 * _noise(x, z, 75., 7) + .35 * _noise(x, z, 26., 8)
        return _smooth((n + .25 * wall(x, z) - .42) / .22)

    def one(x, z, r, slope, tall=0.):
        return bool(_ok(site, clear, np.array([x]), np.array([z]), r, slope, tall)[0])

    def open_ground(X, Z, slope):
        """0..1 on a field's samples: inside the crater, on ground no steeper than `slope`, clear of the riding (a
        sample needs CLEAR and 1 m more, so the sheet's cut edge stays out of the clear zone too)."""
        m = _smooth((site.inside(X, Z) - CREST_MARGIN) / 5.) * (site.slope(X, Z) <= slope)
        m = m * _smooth((clear.free(X, Z) - 1.) / 3.)
        return m * ~clear.in_run(X, Z, 2.)

    def grid_of(cell):
        x0, z0, x1, z1 = bounds
        xs, zs = np.arange(x0, x1 + cell, cell), np.arange(z0, z1 + cell, cell)
        X, Z = np.meshgrid(xs, zs)
        return xs, zs, X, Z

    # crags of dark basalt, placed first (the snow drifts behind them, the moss and shrubs gather round them): a
    # broken band along the foot of the wall, 6 to 20 m across, and islands of three to eight out on the floor, the
    # biggest 25 m across and up to 15 m tall
    crags = []

    def crag(cx, cz, size, k):
        tall = float(np.clip(size * (.45 + .3 * _r(k, 7)), 3., 15.))
        if not one(cx, cz, .5 * size + 1., SLOPE_CRAG, tall):
            return
        spires, _ = _crag(b, site, cx, cz, size, tall, int(k))
        crags.append((cx, cz, size, tall, int(k)))
        count['crags'] += 1
        count['spires'] += spires

    x, z, key = _jitter(bounds, 12., 21)
    foot = site.foot(x, z)
    on = (foot < BAND) & (foot > -WALL_UP) & (_hash(key, 22) < .5 + .3 * _noise(x, z, 60., 24))
    for cx, cz, k in zip(x[on], z[on], key[on]):
        crag(cx, cz, 6. + 14. * _hash(k, 23) ** 1.3, k)
    x, z, key = _jitter(bounds, 55., 25)
    on = (site.foot(x, z) > BAND + 12.) & (_hash(key, 26) < .55)
    for cx, cz, k in zip(x[on], z[on], key[on]):
        crag(cx, cz, 12. + 13. * _r(k, 1), k)
        for m in range(2 + int(_r(k, 2) * 6)):
            a, d = 2 * np.pi * _r(k, 10 + m), 6. + 12. * _r(k, 20 + m)
            crag(cx + d * math.cos(a), cz + d * math.sin(a), 5. + 9. * _r(k, 30 + m), int(k) * 7 + m)
    C = np.array([c[:3] for c in crags]) if crags else np.zeros((0, 3))

    def near_crags(xs, zs, value, reach):
        """A (len(zs), len(xs)) field: the most of value(dx, dz, size) over the crags within reach(size)."""
        f = np.zeros((len(zs), len(xs)))
        for cx, cz, size in C:
            _splat(f, xs, zs, cx, cz, reach(size), lambda dx, dz: value(dx, dz, size))
        return f

    def foot_band(X, Z, inner, outer):
        """1 between `inner` and `outer` metres inside the wall's foot, fading over 8 m."""
        f = site.foot(X, Z)
        return _smooth((f - inner) / 8.) * _smooth((outer - f) / 8.)

    # snow: drifts in the lee of the crags and along the wall's foot, on broad fields of their own; small pieces
    # are left out
    xs, zs, X, Z = grid_of(SNOW_CELL)
    room = open_ground(X, Z, SLOPE_SNOW)
    wx, wz = WIND

    def lee(dx, dz, size):
        u, v = dx * wx + dz * wz, -dx * wz + dz * wx           # downwind, across
        reach = 1.8 * size + 6.
        return np.clip(1 - ((u - .35 * reach) / reach) ** 2 - (v / (.45 * size + 3.)) ** 2, 0, 1) * (u > -.3 * size)

    drift = near_crags(xs, zs, lee, lambda size: 2. * size + 8.)
    n = (.4 * _noise(X, Z, 60., 61) + .18 * _noise(X, Z, 22., 62) + .07 * _noise(X, Z, 8., 63)
         + .45 * drift + .15 * foot_band(X, Z, -6., 30.) * (.6 + .4 * _noise(X, Z, 40., 66)))
    valid = room > .99
    t_snow = float(np.quantile(n[valid], 1 - SNOW_COVER)) if valid.any() else 2.
    snow = n * room
    tris, area = _field(b, SNOW, site, xs, zs, snow, t_snow, .22, .08, 60.)
    count['snow_m2'] = round(area)
    floor_m2 = float(valid.sum()) * SNOW_CELL ** 2
    count['snow_share'] = round(area / max(floor_m2, 1.), 3)

    def snow_at(X, Z, xs=xs, zs=zs):
        """How far over the snow's threshold the ground at X, Z is (positive under the snow)."""
        i = np.clip(np.round((X - xs[0]) / SNOW_CELL).astype(int), 0, len(xs) - 1)
        j = np.clip(np.round((Z - zs[0]) / SNOW_CELL).astype(int), 0, len(zs) - 1)
        return snow[j, i] - t_snow

    # moss mats, off the snow: saturated olive and gold, few and big, gathered round the crags and the wall
    xs, zs, X, Z = grid_of(MOSS_CELL)
    room = open_ground(X, Z, SLOPE_PLANT) * _smooth((-.02 - snow_at(X, Z)) / .04)
    valid = room > .99
    ring = near_crags(xs, zs, lambda dx, dz, size: np.clip(1 - (np.hypot(dx, dz) - .5 * size) / (.6 * size + 10.),
                                                           0, 1), lambda size: 1.1 * size + 10.)
    gather = .45 + np.maximum(ring, foot_band(X, Z, -4., 45.))
    mats = []
    for material, seed in ((MOSS, 65), (OLIVE, 67)):
        m = (.65 * _noise(X, Z, 30., seed) + .35 * _noise(X, Z, 10., seed + 1)) * gather
        t = float(np.quantile(m[valid], 1 - MOSS_COVER)) if valid.any() else 2.
        m = m * room
        for other in mats:                       # the two kinds side by side, never one over the other
            m = np.where(other[0] >= other[1] - .02, 0., m)
        mats.append((m, t))
        _, area = _field(b, material, site, xs, zs, m, t, .12, .06, 25.)
        count['moss_m2'] += round(area)
        # cushions of moss over the thickest of the mat, for volume
        j, i = np.nonzero(m > t + .1)
        pick = _hash(j, i, seed + 2) < .06
        for jj, ii in zip(j[pick], i[pick]):
            k = int(jj) * 7919 + int(ii) * 104729 + seed
            cx, cz = xs[ii] + MOSS_CELL * (_r(k, 1) - .5), zs[jj] + MOSS_CELL * (_r(k, 2) - .5)
            _cushion(b, material, site, cx, cz, .9 + 1.1 * _r(k, 3), .3 + .3 * _r(k, 4), k)
            count['cushions'] += 1

    def bushes(cx, cz, n, spread, k):
        """A clump of n autumn bushes, gold and orange, 1.5 to 3 m, within `spread` of cx, cz."""
        for m in range(n):
            a, d = 2 * np.pi * _r(k, 200 + m), spread * _r(k, 220 + m) ** .6
            tx, tz = cx + d * math.cos(a), cz + d * math.sin(a)
            r, h = .75 + .75 * _r(k, 240 + m), 1.5 + 1.5 * _r(k, 260 + m)
            if one(tx, tz, r + .3, SLOPE_PLANT, h) and float(snow_at(np.array(tx), np.array(tz))) < 0:
                _bush(b, GOLD if _r(k, 280 + m) < .6 else SHRUB, site, tx, tz, r, h, int(k) * 13 + m)
                count['shrubs'] += 1

    # autumn shrubs: clumps of five to twenty round the crags and along the wall
    for cx, cz, size, tall, k in crags:
        if _r(k, 300) < .65:
            a = 2 * np.pi * _r(k, 301)
            d = .5 * size + 2. + 3. * _r(k, 302)
            bushes(cx + d * math.cos(a), cz + d * math.sin(a), 5 + int(_r(k, 303) * 16), 3. + .25 * size, k)
    x, z, key = _jitter(bounds, 30., 55)
    on = (np.abs(site.foot(x, z) - 10.) < 22.) & (_hash(key, 56) < .5)
    for cx, cz, k in zip(x[on], z[on], key[on]):
        bushes(cx, cz, 5 + int(_r(k, 1) * 11), 5., int(k))
    x, z, key = _jitter(bounds, 45., 57)                     # and a few out on the open floor
    on = (site.foot(x, z) > 32.) & (_hash(key, 58) < .3)
    for cx, cz, k in zip(x[on], z[on], key[on]):
        bushes(cx, cz, 5 + int(_r(k, 1) * 6), 4., int(k))

    # conifers: clusters near the wall (up its foot and just inside), a few round the crags
    def conifers(cx, cz, n, spread, k):
        for m in range(n):
            a, d = 2 * np.pi * _r(k, 10 + m), (0. if m == 0 else 2.5 + spread * _r(k, 20 + m))
            tx, tz = cx + d * math.cos(a), cz + d * math.sin(a)
            h = 4. + 5. * _r(k, 30 + m) ** 1.2
            if one(tx, tz, .4 * h, SLOPE_ROCK, h):
                _conifer(b, site, tx, tz, h, int(k) * 17 + m)
                count['conifers'] += 1

    x, z, key = _jitter(bounds, 28., 71)
    on = (site.foot(x, z) > -30.) & (site.foot(x, z) < 60.) & (_hash(key, 72) < .4)
    for cx, cz, k in zip(x[on], z[on], key[on]):
        conifers(cx, cz, 3 + int(_r(k, 1) * 7), 7., int(k))
    for cx, cz, size, tall, k in crags:
        if _r(k, 400) < .2:
            a = 2 * np.pi * _r(k, 401)
            d = .5 * size + 3.
            conifers(cx + d * math.cos(a), cz + d * math.sin(a), 2 + int(_r(k, 402) * 3), 4., k * 3 + 1)

    # basalt blocks a metre or two across, in small groups round the crags and here and there
    x, z, key = _jitter(bounds, 18., 11)
    on = _ok(site, clear, x, z, 5., SLOPE_ROCK) & (_hash(key, 13) < .1 + .3 * rough(x, z))
    for cx, cz, k in zip(x[on], z[on], key[on]):
        for m in range(1 + int(_r(k, 1) * 4)):
            a, d = 2 * np.pi * _r(k, 40 + m), (0. if m == 0 else 1.5 + 2.5 * _r(k, 60 + m))
            bx, bz = cx + d * math.cos(a), cz + d * math.sin(a)
            w = .7 + 1.6 * _r(k, 20 + m) ** 1.5
            h = min(w * (.6 + .8 * _r(k, 30 + m)), 3.)
            if one(bx, bz, 1.5 * w, SLOPE_ROCK, h):
                _block(b, site, bx, bz, w, w * (.6 + .4 * _r(k, 50 + m)), h, 2 * np.pi * _r(k, 70 + m),
                       int(k) * 31 + m, ROCK)
                count['rocks'] += 1

    # loose stones between them
    x, z, key = _jitter(bounds, 14., 15)
    on = _ok(site, clear, x, z, 1.1, SLOPE_ROCK) & (_hash(key, 16) < .03 + .1 * rough(x, z))
    for sx, sz_, k in zip(x[on], z[on], key[on]):
        _stone(b, site, sx, sz_, .25 + .45 * _r(k, 1) ** 1.5, int(k))
        count['stones'] += 1

    # dry grass in loose clumps
    x, z, key = _jitter(bounds, 12., 41)
    on = _ok(site, clear, x, z, 4., SLOPE_PLANT) & (_hash(key, 43) < .02 + .22 * rough(x, z) * _noise(x, z, 40., 42))
    for cx, cz, k in zip(x[on], z[on], key[on]):
        for t in range(2 + int(_r(k, 1) * 4)):
            a, d = 2 * np.pi * _r(k, 10 + t), 2.5 * _r(k, 20 + t) ** .7
            _tuft(b, site, cx + d * math.cos(a), cz + d * math.sin(a), .3 + .4 * _r(k, 30 + t), int(k) * 7 + t)
            count['tufts'] += 1

    parts, tris = [], {}
    for mesh in b.meshes('crater_floor') if b.parts else []:
        material = dsl.MATERIALS[int(mesh.material[0])]
        if material not in SOLID:
            mesh.role[:] = dsl.ROLE[dsl.COPING]          # drawn only, no collision
        tris[material] = int(len(mesh.F))
        parts.append(mesh)
    summary = dict(count, triangles=sum(tris.values()), by_material=tris)
    if bake and parts:
        bake_tiles(parts)
    return parts, summary


def bake_tiles(parts):
    """The dressing's own occlusion (ao.bake, in place on each part's AO): the parts' faces in BAKE_TILE plan tiles,
    each baked on a voxel grid of its tile and what stands within ao.AO_REACH round it, so no grid spans the crater.
    (The volcano's ground is not in the park's mesh: only the rocks, snow and plants shade one another.)"""
    from . import ao
    mesh = dsl.Mesh.concat(parts)
    T = mesh.triangles()
    c = T.mean(1)[:, [0, 2]]
    tile = np.floor(c / BAKE_TILE).astype('i8')
    value = np.ones(len(mesh.V))
    for key in np.unique(tile, axis=0):
        mine = (tile == key).all(1)
        lo, hi = key * BAKE_TILE - ao.AO_REACH, (key + 1) * BAKE_TILE + ao.AO_REACH
        near = ((c >= lo) & (c < hi)).all(1)
        F = mesh.F[mine]
        used = np.unique(F)
        remap = np.full(len(mesh.V), -1, 'i8')
        remap[used] = np.arange(len(used))
        V, N = mesh.V[used], mesh.N[used]
        value[used] = ao.bake(V, remap[F], N, ao.nodes(V, N), T[near])
    start = 0
    for part in parts:
        part.AO = value[start:start + len(part.V)].copy()
        start += len(part.V)


def site(heights, weight, grid):
    """The volcano's ground for build() (Site.volcano)."""
    return Site.volcano(heights, weight, grid)
