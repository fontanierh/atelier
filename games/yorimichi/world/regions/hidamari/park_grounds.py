"""The sunlit park around the pond (x 926-1114, y 238-327): what turns a lawn with a pond into a strolling garden.

Gravel paths come in from the four streets to the pond's stone perimeter walk, and a meandering loop crosses the
western lawn; clipped shrub beds edge the paths and the entrances; the lone swing in the east corner gets a sand
playground with a slide, a climbing frame, a seesaw, a sandpit, benches and a drinking fountain. The pond, its walk,
bridge and tea terrace (build.park, pond_garden, garden_bridge) and the park's riding route along y=284 stay as they
are. Builder: HD_ParkGrounds (world space, following the ground).
"""
import math, random

# Path centre lines (2.6 m of gravel), from the street paving to the perimeter walk (ellipse 51 x 37 about 1030, 284).
PATHS = [[(1030., 238.3), (1030., 247.6)], [(1030., 320.4), (1030., 326.8)],
         [(925.7, 284.), (979.4, 284.)], [(1080.6, 284.), (1114.3, 284.)],
         [(925.7, 252.), (944., 257.), (956., 270.), (959.5, 284.)],
         [(959.5, 284.), (956., 299.), (944., 311.), (925.7, 317.)],
         [(1076.5, 268.), (1091.5, 263.)]]
WIDTH = 2.6
SAND = (1092., 1111., 251.5, 269.)           # x0, x1, y0, y1 around the swing (HD_Playground at 1100, 260)
# Shrub beds: (x, y, rx, ry) ellipses of soil with clipped bushes.
BEDS = [(1025.2, 242.5, 2.4, 3.2), (1034.8, 242.5, 2.4, 3.2), (1025.2, 324., 2.4, 2.2), (1034.8, 324., 2.4, 2.2),
        (933., 279.5, 4., 1.6), (933., 288.5, 4., 1.6), (944.5, 268., 3., 4.5), (944.5, 300., 3., 4.5),
        (966., 279.4, 3., 1.4), (966., 288.6, 3., 1.4), (1105., 279.5, 5., 1.6), (1095., 288.5, 4., 1.5), (1088.5, 252., 2.2, 3.5)]
BENCHES = [(1091.2, 256., 90), (1091.2, 266., 90), (1112., 260.5, -90), (941., 286.5, 0), (952., 282.1, 180)]
LAMPS = [(1038.5, 245.), (1038.5, 323.), (927.8, 281.6), (1112.2, 281.6), (961.2, 274.5), (960.2, 296.)]
PALETTE = {'pk_path_gravel': (.33, .30, .25), 'pk_path_edge_stone': (.27, .26, .23), 'pk_bed_soil': (.13, .085, .05),
           'pk_sand_dirt': (.55, .47, .33), 'pk_edge_timber': (.24, .16, .09), 'pk_concrete': (.36, .35, .33),
           'pk_slide_red': (.55, .10, .05), 'pk_frame_yellow': (.70, .52, .07), 'pk_gym_blue': (.08, .22, .45),
           'pk_seesaw_green': (.12, .34, .14), 'pk_bench_wood': (.36, .22, .11), 'pk_metal': (.18, .19, .20)}


def palette():
    from village import build as v
    v.PALETTE.update(PALETTE)


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


def _ellipse(m, x, y, rx, ry, z_at, key, lift, n=16):
    c = (x, y, float(z_at(x, y))+lift)
    pts = [(x+rx*math.cos(i*math.tau/n), y+ry*math.sin(i*math.tau/n)) for i in range(n)]
    for a, b in zip(pts, pts[1:]+pts[:1]):
        m.poly([c, (a[0], a[1], float(z_at(*a))+lift), (b[0], b[1], float(z_at(*b))+lift)], key)


def _bench(m, x, y, z, yaw):
    with m.at((x, y, z), yaw):
        for dx in (-.7, .7):
            m.box((dx, 0, .22), (.08, .42, .44), 'pk_metal')
        for k in range(3): m.box((0, -.15+k*.15, .46), (1.7, .12, .04), 'pk_bench_wood')
        for k in range(2): m.box((0, .24, .62+k*.16), (1.7, .04, .11), 'pk_bench_wood')
        m.collider((0, 0, .4), (1.8, .5, .8))


def grounds(m, height):
    """HD_ParkGrounds, in world space."""
    from hidamari.temple_precinct import _ribbon
    palette()
    for line in PATHS:
        for a, b in zip(line, line[1:]):
            _ribbon(m, a, b, WIDTH, height, 'pk_path_gravel', .035, 1.5)
            _ribbon(m, a, b, WIDTH+.5, height, 'pk_path_edge_stone', .02, 1.5)
        for p in line[1:-1]: _ellipse(m, p[0], p[1], WIDTH/2+.2, WIDTH/2+.2, height, 'pk_path_gravel', .036, 10)
    for bx, by, rx, ry in BEDS:
        _ellipse(m, bx, by, rx, ry, height, 'pk_bed_soil', .045)
        _ellipse(m, bx, by, rx+.25, ry+.25, height, 'pk_path_edge_stone', .03)
    # the sand playground: sand inside a timber kerb
    x0, x1, y0, y1 = SAND; step = 1.
    xs = [x0+i*step for i in range(int((x1-x0)/step)+1)]; ys = [y0+j*step for j in range(int((y1-y0)/step)+1)]
    if xs[-1] < x1: xs.append(x1)
    if ys[-1] < y1: ys.append(y1)
    for a, b in zip(xs, xs[1:]):
        for c, d in zip(ys, ys[1:]):
            m.poly([(px, py, float(height(px, py))+.04) for px, py in ((a, c), (b, c), (b, d), (a, d))], 'pk_sand_dirt')
    for (ax, ay), (bx, by) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        n = max(1, int(math.hypot(bx-ax, by-ay)/2))
        for k in range(n):
            p = (ax+(bx-ax)*k/n, ay+(by-ay)*k/n); q = (ax+(bx-ax)*(k+1)/n, ay+(by-ay)*(k+1)/n)
            m.beam((p[0], p[1], float(height(*p))+.12), (q[0], q[1], float(height(*q))+.12), .2, .2, 'pk_edge_timber')
    g = lambda x, y: float(height(x, y))
    # slide: ladder up to a platform, chute down to the south
    sx, sy = 1095.5, 262.; z = g(sx, sy)
    for dx in (-.4, .4):
        for dy in (-.4, .4): m.box((sx+dx, sy+dy, z+1.05), (.08, .08, 2.1), 'pk_frame_yellow')
    m.box((sx, sy, z+1.5), (.9, .9, .08), 'pk_frame_yellow')
    for dx in (-.4, .4): m.beam((sx+dx, sy+.4, z+1.5), (sx+dx, sy+.4, z+2.15), .05, .05, 'pk_frame_yellow')
    for k in range(5): m.box((sx, sy+.45, z+.3+k*.3), (.7, .05, .05), 'pk_frame_yellow')
    m.beam((sx, sy-.45, z+1.5), (sx, sy-3.6, z+.35), .6, .06, 'pk_slide_red')
    for dx in (-.32, .32): m.beam((sx+dx, sy-.45, z+1.62), (sx+dx, sy-3.6, z+.47), .05, .2, 'pk_slide_red')
    m.collider((sx, sy, z+1.05), (1., 1., 2.1)); m.collider((sx, sy-2., z+.9), (.7, 3., 1.))
    # climbing frame: a 3 x 3 x 2 m lattice of blue pipes
    cx, cy = 1106., 255.5; z = g(cx, cy)
    for i in range(4):
        for j in range(4):
            m.box((cx-1.5+i, cy-1.5+j, z+1.), (.06, .06, 2.), 'pk_gym_blue')
    for k in range(1, 3):
        for i in range(4):
            m.beam((cx-1.5+i, cy-1.5, z+k), (cx-1.5+i, cy+1.5, z+k), .05, .05, 'pk_gym_blue')
            m.beam((cx-1.5, cy-1.5+i, z+k), (cx+1.5, cy-1.5+i, z+k), .05, .05, 'pk_gym_blue')
    m.collider((cx, cy, z+1.), (3.1, 3.1, 2.))
    # seesaw
    qx, qy = 1106., 265.; z = g(qx, qy)
    m.box((qx, qy, z+.3), (.3, .5, .6), 'pk_frame_yellow')
    m.beam((qx-1.9, qy, z+.28), (qx+1.9, qy, z+.72), .3, .06, 'pk_seesaw_green')
    for dx, h in ((-1.6, .5), (1.6, .9)): m.beam((qx+dx, qy-.2, z+h), (qx+dx, qy+.2, z+h), .04, .04, 'pk_metal')
    m.collider((qx, qy, z+.4), (3.8, .4, .8))
    # sandpit: a low concrete ring
    px, py = 1100., 266.; z = g(px, py)
    for (a, b), (w, d) in (((0, -1.5), (3.2, .2)), ((0, 1.5), (3.2, .2)), ((-1.5, 0), (.2, 2.8)), ((1.5, 0), (.2, 2.8))):
        m.box((px+a, py+b, z+.15), (w, d, .3), 'pk_concrete')
    # drinking fountain
    fx, fy = 1092.9, 270.4; z = g(fx, fy)
    m.box((fx, fy, z+.4), (.35, .35, .8), 'pk_concrete'); m.box((fx, fy, z+.84), (.5, .5, .08), 'pk_concrete')
    m.box((fx, fy, z+.92), (.06, .06, .1), 'pk_metal'); m.collider((fx, fy, z+.45), (.5, .5, .9))
    for x, y, yaw in BENCHES: _bench(m, x, y, g(x, y), yaw)
    return m
