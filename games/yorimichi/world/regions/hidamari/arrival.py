"""The arrival road's last stretch into Hidamari (x 300-400): terraced rice paddies on the hillside, a roadside
shrine, a bus stop, and a town gate where the road meets the first street.

West of the first north-south street (x 410) the old ground was the east-west streets' sidewalk paving carried on up
the hill (build.land_use); it is grass now. On the hillside either side of the road the paddies step down the slope:
each a level plate a little above the highest ground under it, held on its low sides by a dry-stone wall of rounded
stones (ishigaki) or, where low, a grass bank, a grass bund along its rim; half still standing golden with ripe rice
in rows, others harvested stubble, a few flooded or fallow, rice drying on hasa racks. Builder: HD_Arrival (world
space, following the ground).
"""
import math, random
from functools import lru_cache

from hidamari.arrival_placement import (
    AREA, BUS_STOP, ROAD_CLEAR, SHRINE, STEP_MAX, _fits, _road, _world, cells, place, road_distance,
)

CELL = (4., 6.)                        # a paddy, along x and y: narrow, the hillside is steep
SKIRT = .3                             # how far a shoulder's edge skirt reaches below the ground it meets
SPACING = .25                          # metres between the road ribbon's cross-sections
BLEND = 12.                            # metres over which the ribbon leaves the island road's surface for the hillside
FLUSH = .03                            # a shoulder's outer edge above the ground drawn under it
ROAD_LIFT = .06                        # build_terrain.py: the island road strip above its centre line
GATE_X = 399.; GATE_Y = 140.; GATE_HALF = 8.8
PALETTE = {'ar_paddy_earth': (.22, .15, .065), 'ar_stubble_row': (.40, .29, .10), 'ar_paddy_water': (.11, .16, .20),
           'ar_paddy_fallow_lawn': (.17, .22, .08), 'ar_bund_lawn': (.15, .19, .07), 'ar_terrace_drystone': (.25, .235, .20),
           'ar_bank_lawn': (.16, .20, .07), 'ar_hasa_timber': (.25, .17, .09), 'ar_straw_bundle': (.56, .44, .20),
           'ar_hokora_timber': (.30, .17, .08), 'ar_hokora_roof': (.08, .09, .10), 'ar_red_cloth': (.60, .07, .04),
           'ar_shrine_stone': (.32, .31, .28), 'ar_gate_timber': (.22, .12, .06), 'ar_gate_roof': (.07, .08, .09),
           'ar_gate_stone': (.30, .29, .26), 'ar_gate_sign': (.70, .64, .50), 'ar_lantern_glow': (1., .55, .25),
           'ar_island_road': (.085, .085, .09), 'ar_road_gravel': (.17, .155, .13), 'ar_verge_lawn': (.126, .141, .028),
           'ar_rice_canopy': (.42, .32, .09), 'ar_rice_canopy_shade': (.29, .22, .07), 'ar_rice_side': (.22, .19, .07)}


def palette():
    from village import mesh as v
    v.PALETTE.update(PALETTE)


@lru_cache(maxsize=1)
def _island():
    import numpy as np, yori
    world = _world()
    return np.load(yori.OUT/'heightmap.npy'), world['n'], world['size']


def _drawn(a, b, c, d, tx, ty):
    """A terrain quad (corners a, b, c, d anticlockwise from its low x, low y corner) at (tx, ty), as Unreal draws it:
    both terrains are imported as quads, and the importer splits each along its a-c diagonal."""
    return a+(b-a)*tx+(c-b)*ty if tx >= ty else a+(c-d)*tx+(d-a)*ty


def island_height(x, y):
    """The island terrain mesh (build_terrain.py) at (x, y), on the triangle Unreal draws there."""
    H, n, size = _island(); step = size/(n-1)
    fx, fy = (x+size/2)/step, (y+size/2)/step
    i, j = min(max(int(math.floor(fx)), 0), n-2), min(max(int(math.floor(fy)), 0), n-2)
    return _drawn(float(H[j, i]), float(H[j, i+1]), float(H[j+1, i+1]), float(H[j+1, i]), fx-i, fy-j)


@lru_cache(maxsize=1)
def _hidamari_axes():
    from hidamari import layout
    return tuple(map(tuple, layout.terrain_axes()))


def hidamari_height(height, x, y):
    """HD_Terrain (build.surface) at (x, y): height sampled on its grid lines, drawn as the importer splits each quad,
    not the smooth model between them (on the hillside the two differ by a decimetre)."""
    import bisect
    xs, ys = _hidamari_axes()
    i = min(max(bisect.bisect_right(xs, x)-1, 0), len(xs)-2); j = min(max(bisect.bisect_right(ys, y)-1, 0), len(ys)-2)
    x0, x1, y0, y1 = xs[i], xs[i+1], ys[j], ys[j+1]
    g = lambda u, v: float(height(u, v))
    return _drawn(g(x0, y0), g(x1, y0), g(x1, y1), g(x0, y1), (x-x0)/(x1-x0), (y-y0)/(y1-y0))


def ground(height):
    """The ground the road ribbon lies on, as drawn. The island road ends just west of x 300, the island terrain's east
    edge, so the ribbon's first metres sit on the island terrain mesh, the rest on HD_Terrain; the two meet at x 300."""
    edge = _island()[2]/2
    return lambda x, y: island_height(x, y) if x < edge else hidamari_height(height, x, y)


def _bank(level, drop):
    """(key, lean) of a paddy's bank dropping drop below its rim: a grass slope where low, a steep dry-stone wall of
    rounded stones (ishigaki) where it holds up a terrace."""
    return ('ar_terrace_drystone', .12*drop) if drop > .7 else ('ar_bank_lawn', .55*drop)


def _facing(m, pts, out, key):
    """A polygon wound to face along out (horizontal)."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts[:3]
    u, v = (bx-ax, by-ay, bz-az), (cx-ax, cy-ay, cz-az)
    nx, ny = u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2]
    m.poly(pts if nx*out[0]+ny*out[1] >= 0 else pts[::-1], key)


def _banks(m, rim, level, height):
    """The banks from the rim (corners anticlockwise) at level down to the ground on every side, each foot stepped
    out by its lean (one per side, from its tallest drop), the corners closed between neighbouring sides."""
    g = lambda p: float(height(*p))
    sides = []
    for p, q in zip(rim, rim[1:]+rim[:1]):
        L = math.hypot(q[0]-p[0], q[1]-p[1]); out = ((q[1]-p[1])/L, -(q[0]-p[0])/L); n = max(1, int(L))
        pts = [(p[0]+(q[0]-p[0])*k/n, p[1]+(q[1]-p[1])*k/n) for k in range(n+1)]
        key, lean = _bank(level, level-min(g(t) for t in pts))
        sides.append((pts, out, key, lean))
        foot = [(t[0]+out[0]*lean, t[1]+out[1]*lean) for t in pts]
        for k in range(n):
            if level-min(g(pts[k]), g(pts[k+1])) < .12: continue
            _facing(m, [(*foot[k], g(foot[k])-.15), (*foot[k+1], g(foot[k+1])-.15), (*pts[k+1], level), (*pts[k], level)], out, key)
    for (_, o1, k1, l1), (pts, o2, k2, l2) in zip(sides[-1:]+sides[:-1], sides):
        P = pts[0]
        if level-g(P) < .12: continue
        f1 = (P[0]+o1[0]*l1, P[1]+o1[1]*l1); f2 = (P[0]+o2[0]*l2, P[1]+o2[1]*l2); fd = (f1[0]+o2[0]*l2, f1[1]+o2[1]*l2)
        out = (o1[0]+o2[0], o1[1]+o2[1]); key = k1 if l1 >= l2 else k2
        for t1, t2 in ((f1, fd), (fd, f2)):
            _facing(m, [(*P, level), (*t1, g(t1)-.15), (*t2, g(t2)-.15)], out, key)


def _paddy(m, cell, height, r):
    a, b, c, d, z, kind, rack = cell
    top = {'ripe': 'ar_paddy_earth', 'stubble': 'ar_paddy_earth', 'water': 'ar_paddy_water', 'fallow': 'ar_paddy_fallow_lawn'}[kind]
    m.poly([(a, c, z), (b, c, z), (b, d, z), (a, d, z)], top)
    if kind == 'ripe':_crop(m, a+.35, b-.35, c+.35, d-.35, z)
    if kind == 'stubble':
        y = c+.6
        while y < d-.5:
            m.poly([(a+.4, y, z+.025), (b-.4, y, z+.025), (b-.4, y+.14, z+.025), (a+.4, y+.14, z+.025)], 'ar_stubble_row'); y += .55
    # the banks on all four sides, then a grass bund along the rim
    _banks(m, [(a, c), (b, c), (b, d), (a, d)], z, height)
    for p, q in (((a, c), (b, c)), ((b, c), (b, d)), ((b, d), (a, d)), ((a, d), (a, c))):
        m.beam((p[0], p[1], z+.09), (q[0], q[1], z+.09), .45, .18, 'ar_bund_lawn')
    if rack:                                                         # along the paddy's long side (y)
        cx, cy = (a+b)/2, (c+d)/2; L = min(5., d-c-1.2)
        for k in range(4):
            py = cy-L/2+k*L/3; m.box((cx, py, z+1.), (.1, .1, 2.), 'ar_hasa_timber')
        for h in (1.25, 1.8):m.beam((cx, cy-L/2, z+h), (cx, cy+L/2, z+h), .07, .07, 'ar_hasa_timber')
        for h in (1.25, 1.8):
            n = int(L/.32)
            for k in range(n):
                py = cy-L/2+.16+k*.32
                for s in (-1, 1):m.box((cx+s*.14, py, z+h-.36), (.14, .26, .7), 'ar_straw_bundle')


def _crop(m, a, b, c, d, z):
    """Standing ripe rice inside a paddy's bund: rows along y about 0.8 m up, each a low ridge of bowed heads (lit
    crest, shaded furrow), gently uneven, its stalks down the sides."""
    top = lambda x, y: z+.78+.05*math.sin(x*2.1+y*1.3)+.035*math.sin(x*.7-y*2.9)
    rows = max(1, round((b-a)/.3)); xs = [a+(b-a)*k/rows for k in range(rows+1)]
    ys = [c+(d-c)*k/max(1, round(d-c)) for k in range(max(1, round(d-c))+1)]
    for x0, x1 in zip(xs, xs[1:]):
        xm = (x0+x1)/2
        for y0, y1 in zip(ys, ys[1:]):
            for xa, xb, key in ((x0, xm, 'ar_rice_canopy'), (xm, x1, 'ar_rice_canopy_shade')):
                ha = .07 if xa == xm else 0.; hb = .07 if xb == xm else 0.
                m.poly([(xa, y0, top(xa, y0)+ha), (xb, y0, top(xb, y0)+hb), (xb, y1, top(xb, y1)+hb), (xa, y1, top(xa, y1)+ha)], key)
    for edge in ([(x, c) for x in xs], [(b, y) for y in ys], [(x, d) for x in xs[::-1]], [(a, y) for y in ys[::-1]]):
        for p, q in zip(edge, edge[1:]):
            m.poly([(*p, z), (*q, z), (*q, top(*q)), (*p, top(*p))], 'ar_rice_side')


def _shrine(m, height):
    x, y = SHRINE; z = max(float(height(x+dx, y+dy)) for dx in (-1, 1) for dy in (-1, 1))
    with m.at((x, y, z), 45):                                        # local -Y towards the road, south-east
        m.box((0, 0, -.3), (2.0, 1.7, 1.0), 'ar_shrine_stone'); m.collider((0, 0, .2), (2.0, 1.7, 2.))
        m.box((0, 0, .45), (1.0, .8, .5), 'ar_shrine_stone')
        m.box((0, 0, 1.05), (.8, .65, .7), 'ar_hokora_timber')
        m.box((0, -.33, 1.0), (.5, .02, .5), 'ar_red_cloth')
        for s in (-1, 1):
            m.poly([(-.62, 0, 1.68), (.62, 0, 1.68), (.62, s*.55, 1.38), (-.62, s*.55, 1.38)][::s], 'ar_hokora_roof')
        m.box((0, 0, 1.7), (1.3, .08, .06), 'ar_hokora_roof')


def _gate(m, height):
    """The town gate over the road at x 399: posts on stone bases, a tie beam, a small tiled roof and a blank board."""
    z = float(height(GATE_X, GATE_Y))
    for s in (-1, 1):
        y = GATE_Y+s*GATE_HALF
        m.box((GATE_X, y, z+.3), (.9, .9, .6), 'ar_gate_stone'); m.collider((GATE_X, y, z+2.8), (.5, .5, 5.6))
        m.box((GATE_X, y, z+3.0), (.38, .38, 5.4), 'ar_gate_timber')
        m.box((GATE_X, y+.6*s, z+.9), (.16, .9, .16), 'ar_gate_timber')
        m.beam((GATE_X, y, z+4.0), (GATE_X, y-s*1.4, z+5.1), .16, .16, 'ar_gate_timber')
        m.box((GATE_X+.5, y-s*1.6, z+4.35), (.32, .32, .5), 'ar_lantern_glow')
        m.box((GATE_X-.5, y-s*1.6, z+4.35), (.32, .32, .5), 'ar_lantern_glow')
    m.box((GATE_X, GATE_Y, z+5.25), (.42, 2*GATE_HALF+1.6, .45), 'ar_gate_timber')
    m.box((GATE_X, GATE_Y, z+4.45), (.3, 2*GATE_HALF, .25), 'ar_gate_timber')
    for s in (-1, 1):
        m.poly([(GATE_X, GATE_Y-GATE_HALF-1.2, z+6.25), (GATE_X, GATE_Y+GATE_HALF+1.2, z+6.25),
                (GATE_X+s*1.0, GATE_Y+GATE_HALF+1.2, z+5.6), (GATE_X+s*1.0, GATE_Y-GATE_HALF-1.2, z+5.6)][::s], 'ar_gate_roof')
    m.box((GATE_X, GATE_Y, z+6.28), (.25, 2*GATE_HALF+2.4, .14), 'ar_gate_roof')
    for s in (-1, 1):m.box((GATE_X+s*.23, GATE_Y, z+4.85), (.04, 4.2, .62), 'ar_gate_sign')


def _smooth(u):
    u = min(max(u, 0.), 1.); return u*u*(3-2*u)


@lru_cache(maxsize=1)
def _island_end():
    """(x, y, z, grade, left normal) of the island road's last point: its strip lies flat at z+ROAD_LIFT across."""
    road = _world()['road']; k = max(range(len(road)), key=lambda i: road[i][0]); p, q = road[k-1], road[k]
    L = math.hypot(q[0]-p[0], q[1]-p[1])
    return q[0], q[1], q[2], (q[2]-p[2])/L, (-(q[1]-p[1])/L, (q[0]-p[0])/L)


@lru_cache(maxsize=1)
def _samples():
    """(points, left normals, distances) every SPACING metres along the road from the island road's end to the gate,
    its bends rounded; the first normal is the island road's own, so the two strips share their joining edge."""
    road = _road()
    for _ in range(4):                                               # round the bends (Chaikin), the ends kept
        road = [road[0]]+[(p[0]*w+q[0]*(1-w), p[1]*w+q[1]*(1-w)) for p, q in zip(road, road[1:]) for w in (.75, .25)]+[road[-1]]
    pts = []
    for a, b in zip(road, road[1:]):
        L = math.hypot(b[0]-a[0], b[1]-a[1]); n = max(1, round(L/SPACING))
        pts += [(a[0]+(b[0]-a[0])*k/n, a[1]+(b[1]-a[1])*k/n) for k in range(n)]
    pts = [p for p in pts+[road[-1]] if p[0] <= GATE_X]
    def side(k):                                                     # the left normal, from the neighbouring samples
        if k == 0: return _island_end()[4]
        p, q = pts[max(0, k-1)], pts[min(len(pts)-1, k+1)]
        dx, dy = q[0]-p[0], q[1]-p[1]; L = math.hypot(dx, dy); return (-dy/L, dx/L)
    t = [0.]
    for p, q in zip(pts, pts[1:]): t.append(t[-1]+math.hypot(q[0]-p[0], q[1]-p[1]))
    return pts, [side(k) for k in range(len(pts))], t


ASPHALT = (-2.6, -1.3, 0., 1.3, 2.6)                   # cross-section offsets (left positive): the island road's width
SHOULDER = (2.6, 2.8, 3., 3.2, 3.4)                     # a gravel shoulder, from the asphalt's edge out to the ground:
#                                                         fine enough across to follow the island terrain's creases


def _shoulder(side):
    """A shoulder's section offsets, from just outside the asphalt's edge out to the ground, on side -1 or 1."""
    return (side*(SHOULDER[0]+1e-3),)+tuple(side*s for s in SHOULDER[1:])


def _sections(height):
    """[(point, normal, {offset: z})] down the ribbon. The asphalt starts as the island road's own flat strip (its end
    height plus its grade) and eases over BLEND metres onto the hillside, 0.12 m above the ground drawn under it;
    each shoulder falls (or climbs) from just under the asphalt's edge, never under the ground, to FLUSH above it."""
    pts, normals, dist = _samples(); g = ground(height); ex, ey, ez, grade, _ = _island_end()
    out = []
    for c, n, t in zip(pts, normals, dist):
        w = _smooth(t/BLEND); flat = ez+ROAD_LIFT+grade*t; at = lambda s: g(c[0]+n[0]*s, c[1]+n[1]*s); z = {}
        for s in ASPHALT:
            z[s] = max((1-w)*flat+w*(at(s)+.12), at(s)+.02)
        for side in (-1, 1):
            inner = side*SHOULDER[0]; edge, *between, outer = _shoulder(side)
            z[outer] = at(outer)+FLUSH
            z[edge] = min(z[inner], max(z[inner]-.02, at(inner)+.02))
            for s in between:
                u = (s-edge)/(outer-edge); z[s] = max((1-u)*z[edge]+u*z[outer], at(s)+FLUSH)
        out.append((c, n, z))
    return out


def road_uv(s, t):
    """The island road's own UV (build_terrain.py) carried on t metres past its end, s metres left of the centre line:
    u from its right edge (0) to its left (1), v an eighth per road point, so its markings run on in phase."""
    road = _world()['road']; k = max(range(len(road)), key=lambda i: road[i][0])
    step = math.hypot(road[k][0]-road[k-1][0], road[k][1]-road[k-1][1])
    return (s-ASPHALT[0])/(ASPHALT[-1]-ASPHALT[0]), (k+t/step)/8


def _ribbon(m, height):
    """The road itself, draped on the hillside from the island road's end to the gate: the island road's asphalt and
    markings (MI_Road, on its UVs) and gravel shoulders (the terrain's grid is too coarse to draw a narrow diagonal
    road)."""
    sections = _sections(height); dist = _samples()[2]
    if not hasattr(m, 'uvs'): m.uvs = {}                # surfaces.export: the faces that carry their own UVs
    point = lambda c, n, s, z: (c[0]+n[0]*s, c[1]+n[1]*s, z)
    def strip(offsets, key, uv=None):
        for (c, n, zc), (d, o, zd), t0, t1 in zip(sections, sections[1:], dist, dist[1:]):
            for lo, hi in zip(offsets, offsets[1:]):
                faces = len(m.faces)
                m.poly([point(c, n, hi, zc[hi]), point(c, n, lo, zc[lo]), point(d, o, lo, zd[lo]), point(d, o, hi, zd[hi])], key)
                if uv and len(m.faces) > faces and len(m.faces[-1]) == 4:
                    m.uvs[faces] = [uv(hi, t0), uv(lo, t0), uv(lo, t1), uv(hi, t1)]
    strip(ASPHALT, 'ar_island_road', road_uv)
    def lawn(points):   # a verge face in the grass under it: the island ground's colour, fading to HD_Terrain's lawn
        faces = len(m.faces); m.poly(points, 'ar_verge_lawn')
        if len(m.faces) > faces and hasattr(m, 'colors'):
            from hidamari import layout
            from village import mesh as v
            k = len(m.faces[-1]); hd = v.PALETTE['hd_grass']
            for i, (x, _, _) in enumerate(m.vertices[-k:]):
                w = float(layout.island_fade(x)); m.colors[len(m.colors)-k+i] = (*(a*(1-w)+b*w for a, b in zip(layout.ISLAND_LAWN, hd)), 0)
    # Each shoulder is gravel out to a width that grows from nothing at the island road's end (which runs straight
    # onto the grass) to the whole shoulder over BLEND metres; the rest of it is lawn. Its column at a section is cut
    # where that width ends, on the section's line between its two points, so a face that narrows to nothing is
    # dropped (Mesh.poly) rather than drawn.
    def cut(c, n, z, lo, hi, s):
        u = min(max((s-lo)/(hi-lo), 0.), 1.); return point(c, n, lo+(hi-lo)*u, z[lo]+(z[hi]-z[lo])*u)
    for side in (-1, 1):
        offsets = _shoulder(side)
        for (c, n, zc), (d, o, zd), t0, t1 in zip(sections, sections[1:], dist, dist[1:]):
            b0, b1 = (side*(SHOULDER[0]+(SHOULDER[-1]-SHOULDER[0])*_smooth(t/BLEND)) for t in (t0, t1))
            for lo, hi in zip(offsets, offsets[1:]):
                p0, p1 = cut(c, n, zc, lo, hi, b0), cut(d, o, zd, lo, hi, b1)
                ring = [point(c, n, lo, zc[lo]), p0, p1, point(d, o, lo, zd[lo])]
                verge = [p0, point(c, n, hi, zc[hi]), point(d, o, hi, zd[hi]), p1]
                if side > 0: ring, verge = ring[::-1], verge[::-1]
                m.poly(ring, 'ar_road_gravel'); lawn(verge)
    # A short skirt under each shoulder's outer edge and across its start, in the shoulder's surface there: the
    # shoulder ends FLUSH above the drawn ground, and the skirt closes what little light could show under it.
    g = ground(height)
    def skirt(p, q, gravel):
        quad = [p, q, (q[0], q[1], g(q[0], q[1])-SKIRT), (p[0], p[1], g(p[0], p[1])-SKIRT)]
        for face in (quad, quad[::-1]): m.poly(face, 'ar_road_gravel') if gravel else lawn(face)
    for side in (-1, 1):
        offsets = _shoulder(side); outer = offsets[-1]
        for (c, n, zc), (d, o, zd), t0 in zip(sections, sections[1:], dist):
            skirt(point(c, n, outer, zc[outer]), point(d, o, outer, zd[outer]), t0 >= BLEND)
        c, n, zc = sections[0]
        for a, b in zip(offsets, offsets[1:]): skirt(point(c, n, a, zc[a]), point(c, n, b, zc[b]), False)


def arrival(m, height):
    """HD_Arrival, in world space."""
    palette(); r = random.Random(4402)
    _ribbon(m, height)
    for cell in cells(): _paddy(m, cell, height, r)
    _shrine(m, height)
    _gate(m, height)
    return m
