"""Utility poles along Hidamari's streets and the wires between them.

The poles are the coastal road's (build_assets.py pole: a concrete pole, two crossarms across the street, insulators).
One stands about every POLE_STEP metres on one sidewalk of every street, just off the carriageway (layout.road_width),
clear of the junctions, the covered arcade, the clock square, the station square and anything already standing there
(lamps, planters, benches, street props, trees). Every third has a lamp arm on the east-west streets' dark side. The
wires are one mesh, HD_Wires: three sagging lines from the top crossarm per span, from each pole to the next one along
the same street, none across a junction.
"""
import math

POLE_STEP = 30.
SIDE_Y = -1          # the east-west streets' poles stand on the south sidewalk, across from the lamps (cy + 7.8)
SIDE_X = 1           # the north-south streets' on the east one
JUNCTION = 11.       # metres from a crossing street's centre line kept free of poles
KEEP_OUT = [(589, 727, 61, 89),        # the covered arcade (x0, x1, y0, y1)
            (655, 810, 118, 222),      # the clock square
            (1150, 1225, 270, 315)]    # the station square
CLEAR = 1.6          # metres to any lamp, planter, bench, bollard, street prop or tree trunk
ANCHORS = [(0., -1.05, 10.53), (0., 0., 10.53), (0., 1.05, 10.53)]   # the top crossarm's insulators (pole frame)
SAG = .035           # of the span
SEGMENTS = 8
RADIUS = .022


def _kept_out(x, y):
    return any(x0 < x < x1 and y0 < y < y1 for x0, x1, y0, y1 in KEEP_OUT)


def place(put, inst, road_x, road_y, road_width, height):
    """Add the poles through put() and return [(street, [(x, y, z, yaw), ...]), ...], each street's poles in order."""
    taken = [(p[0], p[1]) for name, rows in inst.items()
             if name.startswith(('HD_Lamp', 'HD_Planter', 'HD_Bench', 'HD_Bollard', 'HD_P_', 'Tree', 'HD_ArcadeTree',
                                 'HD_PlazaTree'))
             for p in rows if 380 < p[0] < 1280 and -110 < p[1] < 360]

    def free(x, y):
        return not _kept_out(x, y) and not any(abs(x-a) < CLEAR and abs(y-b) < CLEAR and math.hypot(x-a, y-b) < CLEAR
                                               for a, b in taken)
    streets = []
    for cy in road_y:
        offset = SIDE_Y*(road_width(y=cy)[1]+.5); row = []
        for k, x in enumerate(_stations(400., 1250., road_x, road_width, along='x')):
            y = cy+offset
            if free(x, y):
                lamp = len(row) % 3 == 1
                put('Pole_Lamp' if lamp else 'Pole', x, y, yaw=0 if SIDE_Y < 0 else 180)
                row.append((x, y, float(height(x, y)), 0 if SIDE_Y < 0 else 180)); taken.append((x, y))
        streets.append((f'y{cy}', row))
    for cx in road_x:
        offset = SIDE_X*(road_width(x=cx)[1]+.5); row = []
        top = 162. if cx == 730 else 350.
        for y in _stations(-90., top, road_y, road_width, along='y'):
            x = cx+offset
            if free(x, y):
                put('Pole', x, y, yaw=90)
                row.append((x, y, float(height(x, y)), 90)); taken.append((x, y))
        streets.append((f'x{cx}', row))
    return streets


def _stations(a, b, crossing, road_width, along):
    """Positions every POLE_STEP along a street from a to b, restarting after each crossing street's junction."""
    cuts = sorted(c for c in crossing if a < c < b)
    out = []; start = a+JUNCTION
    for c in cuts+[b]:
        half = (road_width(x=c)[0] if along == 'x' else road_width(y=c)[0])
        end = c-JUNCTION-half+8 if c != b else b-4
        n = max(0, math.floor((end-start)/POLE_STEP))
        if end > start:
            step = (end-start)/max(n, 1)
            out += [start+i*step for i in range(n+1)]
        start = c+JUNCTION+half-8
    return out


def wires(m, streets, key):
    """Three sagging wires per span between consecutive poles on a street (none longer than 45 m)."""
    count = 0
    for _, row in streets:
        for (x0, y0, z0, yaw0), (x1, y1, z1, yaw1) in zip(row, row[1:]):
            if math.hypot(x1-x0, y1-y0) > 45: continue
            for ax, ay, az in ANCHORS:
                p0 = _anchor(x0, y0, z0, yaw0, ax, ay, az); p1 = _anchor(x1, y1, z1, yaw1, ax, ay, az)
                _wire(m, p0, p1, key); count += 1
    return count


def _anchor(x, y, z, yaw, ax, ay, az):
    a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
    return (x+ax*c-ay*s, y+ax*s+ay*c, z+az)


def _wire(m, p0, p1, key):
    dx, dy, dz = (p1[i]-p0[i] for i in range(3)); span = math.sqrt(dx*dx+dy*dy+dz*dz)
    hx, hy = -dy/math.hypot(dx, dy), dx/math.hypot(dx, dy)          # horizontal side vector
    rings = []
    for k in range(SEGMENTS+1):
        t = k/SEGMENTS
        px, py, pz = p0[0]+dx*t, p0[1]+dy*t, p0[2]+dz*t-SAG*span*4*t*(1-t)
        rings.append([(px+hx*RADIUS, py+hy*RADIUS, pz), (px, py, pz+RADIUS), (px-hx*RADIUS, py-hy*RADIUS, pz),
                      (px, py, pz-RADIUS)])
    for r0, r1 in zip(rings, rings[1:]):
        for q in range(4):
            m.poly([r0[q], r0[(q+1) % 4], r1[(q+1) % 4], r1[q]], key)
