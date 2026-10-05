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

AREA = (301., 373., 8., 232.)          # x0, x1, y0, y1 of the paddy hillside
CELL = (4., 6.)                        # a paddy, along x and y: narrow, the hillside is steep
ROAD_CLEAR = 11.                       # metres from the arrival road's centre line
STEP_MAX = 2.2                         # the most a paddy's wall may stand above the ground
SHRINE = (356.1, 118.9)                # beside the road's bend, facing it
BUS_STOP = (373.3, 136.7, 45)
GATE_X = 399.; GATE_Y = 140.; GATE_HALF = 8.8
PALETTE = {'ar_paddy_earth': (.22, .15, .065), 'ar_stubble_row': (.40, .29, .10), 'ar_paddy_water': (.11, .16, .20),
           'ar_paddy_fallow_lawn': (.17, .22, .08), 'ar_bund_lawn': (.15, .19, .07), 'ar_terrace_drystone': (.25, .235, .20),
           'ar_bank_lawn': (.16, .20, .07), 'ar_hasa_timber': (.25, .17, .09), 'ar_straw_bundle': (.56, .44, .20),
           'ar_hokora_timber': (.30, .17, .08), 'ar_hokora_roof': (.08, .09, .10), 'ar_red_cloth': (.60, .07, .04),
           'ar_shrine_stone': (.32, .31, .28), 'ar_gate_timber': (.22, .12, .06), 'ar_gate_roof': (.07, .08, .09),
           'ar_gate_stone': (.30, .29, .26), 'ar_gate_sign': (.70, .64, .50), 'ar_lantern_glow': (1., .55, .25),
           'ar_road_asphalt': (.085, .085, .09), 'ar_road_gravel': (.17, .155, .13), 'ar_road_line': (.62, .60, .55),
           'ar_rice_canopy': (.50, .34, .055), 'ar_rice_canopy_shade': (.36, .25, .05), 'ar_rice_side': (.27, .22, .065)}


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
            L, hi = best; kind = r.choices(['ripe', 'stubble', 'water', 'fallow'], [.5, .28, .14, .08])[0]
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


@lru_cache(maxsize=1)
def _samples():
    """(points, left normals) every metre along the road from the island road's end to the gate, its bends rounded."""
    road = _road()
    for _ in range(4):                                               # round the bends (Chaikin), the ends kept
        road = [road[0]]+[(p[0]*w+q[0]*(1-w), p[1]*w+q[1]*(1-w)) for p, q in zip(road, road[1:]) for w in (.75, .25)]+[road[-1]]
    pts = []
    for a, b in zip(road, road[1:]):
        L = math.hypot(b[0]-a[0], b[1]-a[1]); n = max(1, int(L))
        pts += [(a[0]+(b[0]-a[0])*k/n, a[1]+(b[1]-a[1])*k/n) for k in range(n)]
    pts = [p for p in pts+[road[-1]] if p[0] <= GATE_X]
    def side(k):                                                     # the left normal, from the neighbouring samples
        p, q = pts[max(0, k-1)], pts[min(len(pts)-1, k+1)]
        dx, dy = q[0]-p[0], q[1]-p[1]; L = math.hypot(dx, dy); return (-dy/L, dx/L)
    return pts, [side(k) for k in range(len(pts))]


def _ribbon(m, height):
    """The road itself, draped on the hillside from the island road's end to the gate: asphalt with white edge
    lines and gravel shoulders (the terrain's grid is too coarse to draw a narrow diagonal road)."""
    pts, normals = _samples()
    bands = [(-3.4, -2.6, 'ar_road_gravel', .10), (-2.6, 2.6, 'ar_road_asphalt', .12), (2.6, 3.4, 'ar_road_gravel', .10),
             (-2.45, -2.33, 'ar_road_line', .13), (2.33, 2.45, 'ar_road_line', .13)]
    for k in range(len(pts)-1):
        (p, n), (q, o) = (pts[k], normals[k]), (pts[k+1], normals[k+1])
        for lo, hi, key, lift in bands:
            corner = lambda c, v, w: (c[0]+v[0]*w, c[1]+v[1]*w, float(height(c[0]+v[0]*w, c[1]+v[1]*w))+lift)
            m.poly([corner(p, n, hi), corner(p, n, lo), corner(q, o, lo), corner(q, o, hi)], key)


def arrival(m, height):
    """HD_Arrival, in world space."""
    palette(); r = random.Random(4402)
    _ribbon(m, height)
    for cell in cells(): _paddy(m, cell, height, r)
    _shrine(m, height)
    _gate(m, height)
    return m
