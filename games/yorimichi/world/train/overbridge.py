"""The stone overbridge carrying the road from Belmonte's south-east gate over the railway's final cutting (plain
Python): its mesh LODs as track.Mesh and the piece track.json places. Built only for a line ending at the station's
site (station_site.for_line).

The structure is regular (station_site.OVERBRIDGE, Bridge) and the ground is made to fit it (earthworks.carve): a
straight deck square to the road, its road surface one plane climbing with the road, parapets along its edges and
arched faces between the retaining walls; abutments under its ends; the retaining walls straight along both sides of
the cutting with straight copings, the ground behind them flush with the copings, and a return wall square to the line
closing each end. LOD2 is the collision: deck, parapets, abutments and walls. Budget: track.BUDGETS['SM_ST_Overbridge'].
"""
import math

import numpy as np

from train import earthworks as E
from train import station_site as S
from train import track as T

PARAPET = .5               # the parapets' thickness, on the deck's edges
PARAPET_HEIGHT = 1.05      # over the road
GRAVEL = .05               # the road's gravel over the deck's stone
DECK_DEPTH = 1.35          # the deck's road surface over its soffit
ARCH_RISE = 1.6            # the arched faces' rise under the soffit
COPING = (.3, .1)          # the copings: under and over the ground behind the walls
COPING_LIP = .2            # their overhang beyond the walls' faces
RETURN_STEP = (1., 2., 4.)  # metres between the return walls' points across, per LOD


def crossing_chainage(line, xy=None):
    """The chainage of the road's crossing on a track.Line (nearest point within the last 500 m, to 1 cm)."""
    xy = np.asarray(xy if xy is not None else S.OVERBRIDGE['xy'], float)
    s = np.arange(max(0., line.length - 500.), line.length, .5)
    for step in (.5, .01):
        p = line.frame(s)[0]
        s0 = float(s[np.argmin(np.hypot(p[:, 0] - xy[0], p[:, 1] - xy[1]))])
        s = np.arange(s0 - step, s0 + step + 1e-9, .01)
    return s0


def bridge(line):
    """The overbridge's frame (station_site.Bridge) on a track.Line, with the crossing's rail point and chainage."""
    s = crossing_chainage(line)
    p, t, _ = line.frame(s)
    return S.Bridge(p[:2], t[:2], lambda a: line.frame(s + np.asarray(a, float))[0][..., 2]), p, s


def valley_ground(x, y):
    """The ground as the game shows it in Belmonte's valley: the committed tiles, carved by the station's tool."""
    from belmonte import layout as BM, source
    return source.terrain().height(np.asarray(x, float) - BM.ORIGIN[0], np.asarray(y, float) - BM.ORIGIN[1]) + \
        BM.ORIGIN[2]


def _quad(m, pts, outward, mat):
    """A quad facing `outward` (a direction): its vertex order is flipped if needed."""
    pts = [tuple(map(float, q)) for q in pts]
    a, b, c = (np.asarray(q) for q in pts[:3])
    if np.cross(b - a, c - a) @ np.asarray(outward, float) < 0:
        pts = pts[::-1]
    return m.add(pts, [(0, 1, 2, 3)], mat)


def _loft(m, rings, mat):
    """A closed solid through cross-sections of four (x, y, z) points each (in the same order), its faces outward:
    the sides between consecutive sections and a cap at each end."""
    rings = [[np.asarray(q, float) for q in r] for r in rings]
    for r0, r1 in zip(rings[:-1], rings[1:]):
        centre = np.mean(r0 + r1, axis=0)
        for j in range(4):
            pts = [r0[j], r0[(j + 1) % 4], r1[(j + 1) % 4], r1[j]]
            _quad(m, pts, np.mean(pts, axis=0) - centre, mat)
    for r, other in ((rings[0], rings[1]), (rings[-1], rings[-2])):
        _quad(m, r, np.mean(r, axis=0) - np.mean(other, axis=0), mat)


def overbridge(line, lod):
    """The stone bridge carrying the road from the south-east gate over the cutting (S.OVERBRIDGE), relative to the
    crossing's rail point; returns (mesh, origin, chainage). See the module's docstring."""
    k, p, s = bridge(line)
    m = T.Mesh()
    lo, hi = k.ends()
    half = S.DECK_HALF

    def road(d, w, z):
        """The point d along the road, w across it, at the absolute height z."""
        q = k.road_xy(d, w) - p[:2]
        return (float(q[0]), float(q[1]), float(z - p[2]))

    def track(a, u, z):
        """The point a along the line, u across it, at the absolute height z."""
        q = k.world(a, u) - p[:2]
        return (float(q[0]), float(q[1]), float(z - p[2]))

    def d_at(u, w):
        """d along the road where it is u from the line, w across it."""
        return float((u - (k.road_xy(0., w) - k.origin) @ k.n) / k.rn)

    def deck_box(d0, d1, w0, w1, below, above, mat):
        """A box on the deck's plane from d0 to d1 and w0 to w1, from plane + below to plane + above."""
        ring = [(d0, w0), (d1, w0), (d1, w1), (d0, w1)]
        _loft(m, [[road(d, w, k.plane(d) + below) for d, w in ring],
                  [road(d, w, k.plane(d) + above) for d, w in ring]], mat)

    deck_box(lo, hi, -half, half, -DECK_DEPTH, -GRAVEL, 'MI_B_ashlar')
    deck_box(lo, hi, -half + PARAPET, half - PARAPET, -GRAVEL, 0., 'MI_B_gravel')
    for w0 in (-half, half - PARAPET):
        deck_box(lo, hi, w0, w0 + PARAPET, -GRAVEL, PARAPET_HEIGHT, 'MI_B_stone')
    # abutments under the deck's ends: from the walls' inner faces to the ends, the formation to the soffit
    for sign in (-1., 1.):
        ring = []
        for w in (-half, half):
            inner = d_at(sign * k.wall_half, w)
            ring.append((inner, w))
            ring.append((hi if inner > k.dc else lo, w))
        ring = [ring[0], ring[1], ring[3], ring[2]]
        base = float(k.rail(0.)) + S.FORMATION
        _loft(m, [[road(d, w, base) for d, w in ring], [road(d, w, k.plane(d) - DECK_DEPTH) for d, w in ring]],
              'MI_B_ashlar')
    if lod < 2:     # the arched faces under both edges, springing from the walls' inner faces
        segs = (10, 5)[lod]
        for w0, w1 in ((-half, -half + PARAPET), (half - PARAPET, half)):
            wm = (w0 + w1) / 2
            da, db = sorted((d_at(-k.wall_half, wm), d_at(k.wall_half, wm)))
            for j in range(segs):
                ds = [da + (db - da) * (1 - math.cos(x * math.pi / segs)) / 2 for x in (j, j + 1)]
                arc = [math.sin(x * math.pi / segs) * ARCH_RISE for x in (j, j + 1)]
                soffit = [float(k.plane(d)) - DECK_DEPTH for d in ds]
                ring = [(ds[0], soffit[0] - arc[0]), (ds[1], soffit[1] - arc[1]), (ds[1], soffit[1]),
                        (ds[0], soffit[0])]
                _loft(m, [[road(d, w0, z) for d, z in ring], [road(d, w1, z) for d, z in ring]], 'MI_B_ashlar')
    # the retaining walls, straight along the cutting with straight copings, and a return wall closing each end
    for sign in (-1., 1.):
        a0, a1 = k.wall(sign)
        inner, outer = k.wall_half, k.outer

        def section(a):
            top, base = float(k.coping(sign, a)), float(k.rail(a)) + S.FORMATION
            wall = [track(a, sign * u, z) for u, z in ((inner, base), (outer, base), (outer, top - COPING[0]),
                                                       (inner, top - COPING[0]))]
            lip = (inner - COPING_LIP, outer + COPING_LIP)
            cap = [track(a, sign * u, z) for u, z in ((lip[0], top - COPING[0]), (lip[1], top - COPING[0]),
                                                      (lip[1], top + COPING[1]), (lip[0], top + COPING[1]))]
            return wall, cap
        (w0, c0), (w1, c1) = section(a0), section(a1)
        _loft(m, [w0, w1], 'MI_B_ashlar')
        _loft(m, [c0, c1], 'MI_B_stone')
        for a, inward in ((a0, 1.), (a1, -1.)):
            # its coping carries on the wall's (level across, with the wall's slope along the line)
            reach = E.return_reach(k, sign, a)
            floor = float(k.rail(a)) - E.FORMATION_DROP
            back = a + inward * S.WALL_THICK
            top = {x: float(k.coping(sign, x)) for x in (a, back)}
            us = np.linspace(inner, reach, max(2, int(math.ceil((reach - inner) / RETURN_STEP[lod])) + 1))
            rings = []
            for u in us:            # the face's foot just under the cutting's face in front of it
                foot = floor + float(E._rise(u - inner, *E.BRIDGE_SLOPES)) - .3
                rings.append([track(a, sign * u, foot), track(back, sign * u, foot),
                              track(back, sign * u, top[back] - COPING[0]), track(a, sign * u, top[a] - COPING[0])])
            _loft(m, rings, 'MI_B_ashlar')
            lip, far = a - inward * COPING_LIP, back + inward * COPING_LIP
            ring = [(lip, inner - COPING_LIP), (far, inner - COPING_LIP), (far, reach + COPING_LIP),
                    (lip, reach + COPING_LIP)]
            _loft(m, [[track(a_, sign * u, float(k.coping(sign, a_)) - COPING[0]) for a_, u in ring],
                      [track(a_, sign * u, float(k.coping(sign, a_)) + COPING[1]) for a_, u in ring]], 'MI_B_stone')
    return m, p, s


def layout(line):
    """({'SM_ST_Overbridge': [LODs]}, its piece for track.json) on a line ending at the station's site, else
    ({}, None)."""
    end, before = line.frame(line.length)[0], line.frame(line.length - 10.)[0]
    if S.for_line([before[:2], end[:2]], [before[2], end[2]]) is None:
        return {}, None
    lods, at, chainage = zip(*[overbridge(line, k) for k in range(3)])
    piece = dict(name='SM_ST_Overbridge', origin=[round(float(c), 3) for c in at[0]], collision='LOD2',
                 chainage=round(float(chainage[0]), 2))
    return {'SM_ST_Overbridge': list(lods)}, piece
