"""City placement parameters and data functions, independent from mesh construction."""
import math
import random


PATHS = [[(1030., 238.3), (1030., 247.6)], [(1030., 320.4), (1030., 326.8)],
         [(925.7, 284.), (979.4, 284.)], [(1080.6, 284.), (1114.3, 284.)],
         [(925.7, 252.), (944., 257.), (956., 270.), (959.5, 284.)],
         [(959.5, 284.), (956., 299.), (944., 311.), (925.7, 317.)],
         [(1076.5, 268.), (1091.5, 263.)]]


WIDTH = 2.6


SAND = (1092., 1111., 251.5, 269.)


BEDS = [(1025.2, 242.5, 2.4, 3.2), (1034.8, 242.5, 2.4, 3.2), (1025.2, 324., 2.4, 2.2), (1034.8, 324., 2.4, 2.2),
        (933., 279.5, 4., 1.6), (933., 288.5, 4., 1.6), (944.5, 268., 3., 4.5), (944.5, 300., 3., 4.5),
        (966., 279.4, 3., 1.4), (966., 288.6, 3., 1.4), (1105., 279.5, 5., 1.6), (1095., 288.5, 4., 1.5), (1088.5, 252., 2.2, 3.5)]


LAMPS = [(1038.5, 245.), (1038.5, 323.), (927.8, 281.6), (1112.2, 281.6), (961.2, 274.5), (960.2, 296.)]


def _near_path(x, y, margin):
    for line in PATHS:
        for a, b in zip(line, line[1:]):
            dx, dy = b[0]-a[0], b[1]-a[1]; t = max(0., min(1., ((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy)))
            if math.hypot(x-a[0]-t*dx, y-a[1]-t*dy) < WIDTH/2+margin: return True
    return False


def place(put, inst, height):
    """Clear trees and small furniture off the paths, beds and sand; plant the beds; light the paths."""
    x0, x1, y0, y1 = SAND
    for name, items in inst.items():
        if not (name.startswith(('Tree', 'Bush', 'Grass')) or name in ('HD_Planter', 'HD_Bench', 'HD_Lamp')): continue
        inst[name] = [p for p in items if not (926 < p[0] < 1114 and 238 < p[1] < 327 and
                      (_near_path(p[0], p[1], 1.2 if name.startswith('Tree') else .3) or
                       (x0-1.5 < p[0] < x1+1.5 and y0-1.5 < p[1] < y1+1.5 and name != 'HD_Lamp') or
                       any(((p[0]-bx)/(rx+1.))**2+((p[1]-by)/(ry+1.))**2 < 1 for bx, by, rx, ry in BEDS)))]
    r = random.Random(1311)
    for bx, by, rx, ry in BEDS:
        n = max(3, int(rx*ry*.9))
        for i in range(n):
            a = r.uniform(0, math.tau); d = math.sqrt(r.random())*.8
            px, py = bx+math.cos(a)*rx*d, by+math.sin(a)*ry*d
            name = r.choices(['Bush_HD_Mound', 'Bush_HD_Ball', 'Bush_HD_Azalea', 'Bush_HD_Amber'], [.4, .25, .2, .15])[0]
            put(name, px, py, yaw=r.uniform(0, 360), scale=r.uniform(.7, 1.0))
    for x, y in LAMPS: put('HD_Lamp', x, y)
