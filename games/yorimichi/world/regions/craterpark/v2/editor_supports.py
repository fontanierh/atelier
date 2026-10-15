"""Supports for the owner's editor park, in the style of the approved art-direction concepts
(assets/craterpark/concepts/editor/supports-rock*.jpg and supports-timber*.jpg).

Most of the park rides 20 to 75 m above the crater floor, so it stands on columnar-basalt towers: packed hexagonal
columns rising from the ground to the ramp's underside, their outer columns stepping down, with a skirt of short
columns round the foot. The low runs (under TIMBER_MAX clearance) stand on timber trestle bents on stone footings.

Every support is built from the pieces' own vertices (the underside right above each column) and the cut ground the
volcano follows, so nothing floats. A column that would pass through another piece is left out. Bowls (in their own
pits) and decks (the tower's own structure) get none.
"""
import math

import numpy as np

from . import dsl

BASALT = 'material_028'       # columnar basalt, a world-aligned Sunburst painting (tools/craterpark_textures.py)
TIMBER = 'material_011'       # masonite-brown wood for the trestle posts and braces
FOOTING = 'material_017'      # stone retaining wall for the trestle footings

TIMBER_MAX = 12.      # a piece whose median clearance is under this stands on trestles, else basalt towers
MIN_CLEAR = 1.2       # no support where the underside is this close to the ground
TOWER_EVERY = 45.     # metres between basalt massifs along a piece
BENT_EVERY = 6.       # metres between timber bents
SINK = 2.             # supports go this far into the ground (the volcano samples the cut ground every 5 m)
EMBED = -.25          # column tops stop just under the ramp (the pieces are single sheets, no thickness)
COLUMN = 2.            # basalt column circumradius (m)
PITCH = 3.5            # basalt lattice spacing (m)
TOWER_ALONG = 9.       # depth along the piece of the columns that carry the ramp (m)
FOOT_SLOPE = .32       # the massif widens by this much per metre of height, down to its foot
FOOT_MAX = 22.         # metres: its foot's half width at most
TIERS = 5              # height tiers of the outer columns
POST = .5             # timber post section (m)


def _rand(*key):
    """Deterministic uniform [0, 1) from a position: the same park always gets the same supports."""
    h = hash(tuple(round(k, 2) for k in key)) & 0xffffffff
    return ((h * 2654435761) & 0xffffffff) / 2 ** 32


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
    """Every kept piece's vertices hashed on a 2 m plan grid: the underside above a point, and what lies below it."""

    def __init__(self, pieces, cell=2.):
        self.cell, self.cells = cell, {}
        for k, p in enumerate(pieces):
            V = p.mesh.V
            keys = np.floor(V[:, [0, 2]] / cell).astype(int)
            for key, y, x, z in zip(map(tuple, keys), V[:, 1], V[:, 0], V[:, 2]):
                self.cells.setdefault(key, []).append((k, x, y, z))
        self.cells = {key: np.array(v) for key, v in self.cells.items()}

    def near(self, x, z, r):
        c, out = self.cell, []
        for i in range(math.floor((x - r) / c), math.floor((x + r) / c) + 1):
            for j in range(math.floor((z - r) / c), math.floor((z + r) / c) + 1):
                v = self.cells.get((i, j))
                if v is not None:
                    out.append(v[(v[:, 1] - x) ** 2 + (v[:, 3] - z) ** 2 <= r * r])
        return np.concatenate(out) if out else np.zeros((0, 4))

    def span(self, x, z, r, piece):
        """(underside of `piece` above the point, highest point of any other piece below that underside) or None."""
        v = self.near(x, z, r)
        own = v[v[:, 0] == piece]
        if not len(own):
            return None
        under = own[:, 2].min()
        other = v[(v[:, 0] != piece) & (v[:, 2] < under)]
        return under, (other[:, 2].max() if len(other) else -np.inf)


def _prism(cx, cz, r, y0, y1, sides=6, turn=0.):
    """A vertical prism (no bottom cap: it is buried): vertices, faces, normals (flat-shaded, outward)."""
    a = turn + np.arange(sides) * 2 * np.pi / sides
    ring = np.stack([cx + r * np.cos(a), cz + r * np.sin(a)], 1)
    V, F, N = [], [], []
    for k in range(sides):
        (x0, z0), (x1, z1) = ring[k], ring[(k + 1) % sides]
        n = np.array([z1 - z0, 0., -(x1 - x0)])
        n /= np.linalg.norm(n)
        if n @ np.array([(x0 + x1) / 2 - cx, 0, (z0 + z1) / 2 - cz]) < 0:
            n = -n
        b = len(V)
        V += [(x0, y0, z0), (x1, y0, z1), (x1, y1, z1), (x0, y1, z0)]
        N += [n] * 4
        F += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    b = len(V)
    V += [(cx, y1, cz)] + [(x, y1, z) for x, z in ring]
    N += [(0., 1., 0.)] * (sides + 1)
    F += [(b, b + 1 + k, b + 1 + (k + 1) % sides) for k in range(sides)]
    return np.array(V, 'f8'), np.array(F, 'i8'), np.array(N, 'f8')


def _beam(p, q, w, d):
    """A box beam from p to q (native), w wide (horizontal) and d deep: vertices, faces, normals."""
    p, q = np.asarray(p, 'f8'), np.asarray(q, 'f8')
    t = q - p
    t /= np.linalg.norm(t)
    side = np.cross(t, [0., 1., 0.])
    side = side / np.linalg.norm(side) if np.linalg.norm(side) > 1e-6 else np.array([1., 0., 0.])
    up = np.cross(side, t)
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    ring = [s * w / 2 * side + u * d / 2 * up for s, u in corners]
    V, F, N = [], [], []
    for k in range(4):
        a, b = ring[k], ring[(k + 1) % 4]
        n = (a + b) / 2
        n /= np.linalg.norm(n)
        o = len(V)
        V += [p + a, p + b, q + b, q + a]
        N += [n] * 4
        F += [(o, o + 2, o + 1), (o, o + 3, o + 2)]
    for end, sign in ((p, -1), (q, 1)):
        o = len(V)
        V += [end + c for c in ring]
        N += [sign * t] * 4
        F += [(o, o + 1, o + 2), (o, o + 2, o + 3)] if sign > 0 else [(o, o + 2, o + 1), (o, o + 3, o + 2)]
    return np.array(V), np.array(F, 'i8'), np.array(N)


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


def _every(stations, step):
    """Stations about `step` metres apart along the piece, centred so both ends keep a margin."""
    d = np.array([s['d'] for s in stations])
    if d[-1] < step * .6:
        return [stations[int(np.argmin(np.abs(d - d[-1] / 2)))]]
    n = max(1, int(round(d[-1] / step)))
    targets = (np.arange(n) + .5) * d[-1] / n
    return [stations[int(np.argmin(np.abs(d - t)))] for t in targets]


def tower(b, plan, ground, piece, s):
    """A columnar-basalt massif under station s, after the rock concept: packed columns on a hexagonal lattice whose
    tops follow a stepped spire. Columns under the ramp reach its underside; round them the tops fall away in tiers to
    a wide foot, so the mass tapers from a broad base to the ramp it carries. Returns the number of columns placed."""
    clear = s['y'] - float(ground(s['x'], s['z']))
    if clear < MIN_CLEAR:
        return 0
    h = math.radians(s['h'])
    along, across = np.array([math.cos(h), math.sin(h)]), np.array([-math.sin(h), math.cos(h)])
    half = _outer_half(s) * .8                       # the part of the ramp the columns carry
    carry_along = TOWER_ALONG / 2
    foot = min(FOOT_MAX, half + FOOT_SLOPE * clear)  # the massif's half width at the ground
    foot_along = min(FOOT_MAX, carry_along + FOOT_SLOPE * clear)
    centre = np.array([s['x'], s['z']])
    placed = 0
    n_u, n_v = int(foot_along // (PITCH * .87)) + 1, int(foot // PITCH) + 1
    for r in range(-n_u, n_u + 1):
        u = r * PITCH * .87
        off = PITCH / 2 if r % 2 else 0.
        for c in range(-n_v - 1, n_v + 1):
            v = c * PITCH + off
            x, z = centre + u * along + v * across
            jit = (_rand(x, z, 4) - .5) * PITCH * .25
            x, z = x + jit * across[0], z + jit * across[1]
            # normalised distance out from the carried core (0 inside it, 1 at the foot)
            ou = max(0., abs(u) - carry_along) / max(foot_along - carry_along, 1e-3)
            ov = max(0., abs(v) - half) / max(foot - half, 1e-3)
            out = math.hypot(ou, ov)
            if out > 1.:
                continue
            radius = COLUMN * (.85 + .35 * _rand(z, x))
            g = float(ground(x, z))
            if out == 0.:
                got = plan.span(x, z, radius + .4, piece)      # the whole column top stays under the ramp
                if got is None:
                    continue
                under, below = got
                if below > g - SINK or under - g < MIN_CLEAR:  # another piece runs under here, or no room
                    continue
                top = under + EMBED
            else:
                # tiers: the tops fall with distance out, in steps, each column a little broken
                level = (1 - out) ** 1.6
                level = math.floor(level * TIERS + _rand(x, z, 5) * .7) / TIERS
                top = g + (clear - 1.) * level - _rand(z, x, 6) * 2.
                if top - g < 1.:
                    continue
                near = plan.near(x, z, radius + 1.5)
                if len(near) and (near[:, 2] < top + 2.).any():   # never into or just under any piece
                    continue
            b.add(BASALT, _prism(x, z, radius, g - SINK, top, turn=_rand(x, z, 1) * .5))
            placed += 1
    return placed


def bent(b, plan, ground, piece, s, last):
    """A timber trestle bent under station s: posts on stone footings, a cap beam, X bracing, ties to the last bent."""
    h = math.radians(s['h'])
    across = np.array([-math.sin(h), math.cos(h)])
    half = _outer_half(s) - .6
    posts = [-half, half] if half < 8 else [-half, 0., half]
    tops = []
    for v in posts:
        x, z = np.array([s['x'], s['z']]) + v * across
        got = plan.span(x, z, POST + .4, piece)
        if got is None:
            return last
        under, below = got
        g = float(ground(x, z))
        if below > g - SINK or under - g < MIN_CLEAR:
            return last
        tops.append((x, z, under, g))
    for x, z, under, g in tops:
        b.add(FOOTING, _beam((x, g - 1., z), (x, g + .5, z), 1.2, 1.2))
        b.add(TIMBER, _beam((x, g + .5, z), (x, under + EMBED, z), POST, POST))
    cap = min(t[2] for t in tops) - .25
    (x0, z0, _, g0), (x1, z1, _, g1) = tops[0], tops[-1]
    b.add(TIMBER, _beam((x0, cap, z0), (x1, cap, z1), .45, .5))
    low = max(g0, g1) + 1.
    if cap - low > 2.5:
        levels = max(1, int(round((cap - low) / 8.)))
        for k in range(levels):
            y0 = low + (cap - low) * k / levels
            y1 = low + (cap - low) * (k + 1) / levels
            for (xa, za, _, _), (xb, zb, _, _) in zip(tops, tops[1:]):
                b.add(TIMBER, _beam((xa, y0, za), (xb, y1, zb), .3, .22))
                b.add(TIMBER, _beam((xb, y0, zb), (xa, y1, za), .3, .22))
            if k:
                b.add(TIMBER, _beam((x0, y0, z0), (x1, y0, z1), .3, .3))
    here = [(x, z, (g + 1. + cap) / 2) for x, z, _, g in (tops[0], tops[-1])]
    if last is not None:
        for (xa, za, ya), (xb, zb, yb) in zip(last, here):
            b.add(TIMBER, _beam((xa, ya, za), (xb, yb, zb), .3, .3))
    return here


def build(pieces, heights, grid):
    """The supports for the kept editor pieces (bridge Pieces), as dsl Mesh parts, and a summary."""
    ground = Ground(heights, grid)
    plan = Plan(pieces)
    out, summary = [], {'towers': 0, 'columns': 0, 'bents': 0, 'pieces': {}}
    for k, piece in enumerate(pieces):
        meta = piece.metadata
        if meta['type'] in ('bowl', 'deck') or not meta.get('stations'):
            continue
        st = meta['stations']
        clear = [s['y'] - float(ground(s['x'], s['z'])) for s in st[::4]]
        style = 'timber' if np.median(clear) < TIMBER_MAX else 'basalt'
        b = Builder()
        if style == 'basalt':
            for s in _every(st, TOWER_EVERY):
                n = tower(b, plan, ground, k, s)
                summary['columns'] += n
                summary['towers'] += bool(n)
        else:
            last = None
            for s in _every(st, BENT_EVERY):
                here = bent(b, plan, ground, k, s, last)
                summary['bents'] += here is not last and here is not None
                last = here
        out += b.meshes(f"{meta['id']}_supports")
        summary['pieces'][meta['id']] = style
    return out, summary
