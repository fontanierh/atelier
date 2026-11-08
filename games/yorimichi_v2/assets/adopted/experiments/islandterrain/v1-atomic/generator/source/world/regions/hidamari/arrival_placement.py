"""City placement parameters and data functions, independent from mesh construction."""
from functools import lru_cache
import math
import random


AREA = (301., 373., 8., 232.)


ROAD_CLEAR = 11.


STEP_MAX = 2.2


SHRINE = (356.1, 118.9)


BUS_STOP = (373.3, 136.7, 45)


@lru_cache(maxsize=1)
def _world():
    import json, yori
    return json.loads((yori.OUT/'world.json').read_text())


@lru_cache(maxsize=1)
def _road():
    start = max(_world()['road'], key=lambda q: q[0])[:2]
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
