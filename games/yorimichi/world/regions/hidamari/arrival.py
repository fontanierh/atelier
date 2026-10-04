"""The arrival road's last stretch into Hidamari (x 300-400): terraced rice paddies on the hillside, a roadside
shrine, a bus stop, and a town gate where the road meets the first street.

West of the first north-south street (x 410) the old ground was the east-west streets' sidewalk paving carried on up
the hill (build.land_use); it is grass now. On the hillside either side of the road the paddies step down the slope:
each a level plate a little above the highest ground under it, held by a stone or earth wall down to the ground on
its low sides, a grass bund along its rim; harvested stubble in rows, a few still flooded or fallow, rice drying on
hasa racks. Builder: HD_Arrival (world space, following the ground).
"""
import math, random
from functools import lru_cache

AREA = (301., 373., 8., 232.)          # x0, x1, y0, y1 of the paddy hillside
CELL = (4., 6.)                        # a paddy, along x and y: narrow, the hillside is steep
ROAD_CLEAR = 11.                       # metres from the arrival road's centre line
STEP_MAX = 2.2                         # the most a paddy's wall may stand above the ground
SHRINE = (356.1, 118.9)                # beside the road's bend, facing it
BUS_STOP = (373.3, 136.7, 45)
GATE_X = 399.; GATE_Y = 140.; GATE_HALF = 8.8
PALETTE = {'ar_paddy_earth': (.36, .27, .12), 'ar_stubble_row': (.48, .37, .16), 'ar_paddy_water': (.10, .13, .14),
           'ar_paddy_fallow_lawn': (.17, .22, .08), 'ar_bund_lawn': (.15, .19, .07), 'ar_terrace_stone': (.27, .26, .22),
           'ar_bank_lawn': (.16, .20, .07), 'ar_hasa_timber': (.25, .17, .09), 'ar_straw_bundle': (.56, .44, .20),
           'ar_hokora_timber': (.30, .17, .08), 'ar_hokora_roof': (.08, .09, .10), 'ar_red_cloth': (.60, .07, .04),
           'ar_shrine_stone': (.32, .31, .28), 'ar_gate_timber': (.22, .12, .06), 'ar_gate_roof': (.07, .08, .09),
           'ar_gate_stone': (.30, .29, .26), 'ar_gate_sign': (.70, .64, .50), 'ar_lantern_glow': (1., .55, .25)}


def palette():
    from village import build as v
    v.PALETTE.update(PALETTE)


@lru_cache(maxsize=1)
def _road():
    import json, yori
    start = max(json.loads((yori.OUT/'world.json').read_text())['road'], key=lambda q: q[0])[:2]
    return [tuple(start), (335., 85.), (390., 140.), (420., 140.)]


def road_distance(x, y):
    best = 1e9
    road = _road()
    for a, b in zip(road, road[1:]):
        dx, dy = b[0]-a[0], b[1]-a[1]; t = max(0., min(1., ((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
        best = min(best, math.hypot(x-a[0]-t*dx, y-a[1]-t*dy))
    return best


def _fits(a, b, c, d):
    """(level, ok) for a paddy over x a-b, y c-d: ok when the ground under it drops less than STEP_MAX and it keeps
    clear of the road and the shrine."""
    from hidamari import layout
    import numpy as np
    xs, ys = np.meshgrid(np.linspace(a, b, 5), np.linspace(c, d, max(3, int(d-c)+1)))
    z = layout.height(xs, ys); hi = float(z.max())
    if hi-float(z.min()) > STEP_MAX-.1: return hi, False
    if min(road_distance(px, py) for px in (a, b, (a+b)/2) for py in (c, d, (c+d)/2)) < ROAD_CLEAR: return hi, False
    return hi, math.hypot((a+b)/2-SHRINE[0], (c+d)/2-SHRINE[1]) > 7.


@lru_cache(maxsize=1)
def cells():
    """[(x0, x1, y0, y1, level, kind, rack)] for each paddy, in fixed order: columns of uneven width across the slope,
    each split along y into paddies as long as the ground allows (so they follow the contours rather than a grid)."""
    out = []; r = random.Random(4401)
    x0, x1, y0, y1 = AREA; a = x0
    while a < x1-2.5:
        b = min(x1, a+r.choice([3.5, 4., 4., 4.5, 5.])); c = y0+r.uniform(0, 2.)
        while c < y1-3.:
            best = None
            for L in (14., 12., 10., 8., 6.5, 5., 4.):
                if c+L > y1: continue
                hi, ok = _fits(a, b, c, c+L)
                if ok: best = (L, hi); break
            if not best: c += 1.5; continue
            L, hi = best; kind = r.choices(['stubble', 'water', 'fallow'], [.78, .13, .09])[0]
            out.append((a+.05, b-.05, c+.05, c+L-.05, hi+.1, kind, kind == 'stubble' and L >= 6.5 and r.random() < .3))
            c += L
        a = b
    return tuple(out)


def place(put, inst, height):
    """Clear scatter off the paddies; the shrine's jizo and lantern, and the bus stop."""
    boxes = [(a-.3, b+.3, c-.3, d+.3) for a, b, c, d, *_ in cells()]
    for name, items in inst.items():
        if not name.startswith(('Tree', 'Bush', 'Grass', 'HD_North')): continue
        inst[name] = [p for p in items if not (AREA[0]-1 < p[0] < AREA[1]+1 and any(a < p[0] < b and c < p[1] < d for a, b, c, d in boxes))]
    x, y = SHRINE; yaw = 45                                         # facing the road, south-east
    for side in (-1, 1):
        a = math.radians(yaw); px, py = x+side*1.4*math.cos(a), y+side*1.4*math.sin(a)
        put('HD_P_jizo', px, py, yaw=yaw)
    put('HD_P_stone_lantern', x+2.6*math.cos(math.radians(yaw)), y+2.6*math.sin(math.radians(yaw)), yaw=yaw)
    put('HD_P_bus_stop', BUS_STOP[0], BUS_STOP[1], yaw=BUS_STOP[2])


def _bank(level, drop):
    """(key, lean) of a paddy's bank dropping drop below its rim: a grass slope, or a steep stone wall where tall."""
    return ('ar_terrace_stone', .15*drop) if drop > 1.9 else ('ar_bank_lawn', .55*drop)


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
    top = {'stubble': 'ar_paddy_earth', 'water': 'ar_paddy_water', 'fallow': 'ar_paddy_fallow_lawn'}[kind]
    m.poly([(a, c, z), (b, c, z), (b, d, z), (a, d, z)], top)
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


def arrival(m, height):
    """HD_Arrival, in world space."""
    palette(); r = random.Random(4402)
    for cell in cells(): _paddy(m, cell, height, r)
    _shrine(m, height)
    _gate(m, height)
    return m
