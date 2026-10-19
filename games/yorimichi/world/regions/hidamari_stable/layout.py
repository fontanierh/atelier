"""Hidamari stable (陽だまり厩舎): the plan of Henry's racing stable on the slope above Hidamari's north edge.

Blender metres (x east, y north, z up). Everything below is in the stable's frame: origin at SITE on the graded
ground (PAD_Z), axes parallel to the island's (YAW = 0).
Unreal = (100 x, -100 y, 100 z) after adding SITE.

The compound is one flat pad, COMPOUND wide, on the slope north of the city, graded into Hidamari's own terrain
(`grade`, called by hidamari/layout.py height): cut on its north side, filled on its south side, both meeting the
natural ground in gentle 1-in-GRADE_SLOPE slopes, so the hillside keeps its soft shape and Hidamari's grass. The visitor arrives by the ROAD, a dirt lane that leaves the end of
Hidamari's north-running street at x = 920 and climbs with the ground to the pad's west edge, then passes
through the roofed GATE that carries the stable's name plate, across the sand YARD (water trough, hitching rail,
lanterns) and into the BARN's west door. The barn is a long timber umaya with a central aisle: the tack room and the
jockeys' office first, then five stalls on each side, then the east door towards the PADDOCK.

Standard library and numpy only: build.py (Blender) and the tests import it.
"""
import math

NAME = '陽だまり厩舎'
SITE = (955., 447.)            # world (x, y) of the frame's origin: chosen by Paul on the slope above the city's north edge
YAW = 0.                       # degrees; the frame is axis-aligned with the island
COMPOUND = (-40., -35., 40., 35.)   # pad rectangle (x0, y0, x1, y1)
PAD_Z = 45.6                   # the pad's level (island metres): cut and fill balance on the slope (47.0 to 42.6 m)
GRADE_SLOPE = 4.               # the graded ground's run per metre of cut or fill (about 14 degrees)
GRADE_CREST = 3.               # metres over which the slopes round off from the flat pad
GRADE_ROUND = 1.5              # metres over which they round into the natural ground (crest and toe)
GRADE_REACH = 22.              # the farthest the grading reaches from the pad (3 m of fill plus the rounding)


def grade_offset(d):
    """How far the graded slopes may rise or fall from the pad's level, `d` metres out from the pad's edge (scalar or
    numpy): a parabola over the crest, then a straight 1-in-GRADE_SLOPE slope."""
    import numpy as np
    d = np.maximum(d, 0.)
    return np.where(d < GRADE_CREST, d * d / (2 * GRADE_CREST * GRADE_SLOPE), (d - GRADE_CREST / 2) / GRADE_SLOPE)


def _smin(a, b, r):
    import numpy as np
    h = np.clip(.5 + .5 * (b - a) / r, 0., 1.)
    return b + (a - b) * h - r * h * (1 - h)


def grade(x, y, z):
    """The island ground z at x, y (island metres, numpy) reshaped round the stable, as Hidamari's terrain carries it
    (hidamari/layout.py height): flat at PAD_Z over the pad, then cut and fill slopes of 1 in GRADE_SLOPE that round
    into the natural ground. Unchanged beyond GRADE_REACH, so the city's streets and the north's terrain never see it."""
    import numpy as np
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    x0, y0, x1, y1 = (SITE[0] + COMPOUND[0], SITE[1] + COMPOUND[1], SITE[0] + COMPOUND[2], SITE[1] + COMPOUND[3])
    out = z.copy()
    near = (x > x0 - GRADE_REACH) & (x < x1 + GRADE_REACH) & (y > y0 - GRADE_REACH) & (y < y1 + GRADE_REACH)
    if not near.any():
        return out
    px, py, g = x[near], y[near], z[near]
    d = np.hypot(np.maximum(np.maximum(x0 - px, px - x1), 0.), np.maximum(np.maximum(y0 - py, py - y1), 0.))
    hi, lo = PAD_Z + grade_offset(d), PAD_Z - grade_offset(d)
    f = -_smin(-_smin(g, hi, GRADE_ROUND), -lo, GRADE_ROUND)            # the cut's crest and the fill's toe, rounded
    fade = np.clip((GRADE_REACH - d) / GRADE_ROUND, 0., 1.)           # back to the natural ground at the reach, seamless
    out[near] = g + (np.clip(f, lo, hi) - g) * fade
    return out


# ------------------------------------------------------------------ barn
WALL = .25                     # outer wall thickness
PART = .15                     # stall fronts and partitions
STALL_W, STALL_D = 3.6, 3.6    # clear stall box (along the aisle, across it)
STALLS_PER_SIDE = 5
ROOM_W = 4.0                   # clear length of the west bay (tack room north, office south)
AISLE = 3.5                    # clear aisle between the stall fronts
BARN_LENGTH = 2 * WALL + ROOM_W + STALLS_PER_SIDE * (PART + STALL_W)
BARN_WIDTH = 2 * WALL + 2 * STALL_D + 2 * PART + AISLE
BARN_CENTRE = (6., 12.)        # the aisle runs along y = BARN_CENTRE[1]
BARN_X0 = BARN_CENTRE[0] - BARN_LENGTH / 2
BARN_X1 = BARN_CENTRE[0] + BARN_LENGTH / 2
BARN_Y0 = BARN_CENTRE[1] - BARN_WIDTH / 2
BARN_Y1 = BARN_CENTRE[1] + BARN_WIDTH / 2
FLOOR_Z = .10                  # the barn floor over the pad (a low stone sill round it)
EAVE_Z = 3.9                   # top of the walls
ROOF_PITCH = 26.               # degrees
EAVE_OVERHANG = 1.1
RIDGE_Z = EAVE_Z + (BARN_WIDTH / 2) * math.tan(math.radians(ROOF_PITCH))
VENT = dict(width=2.6, height=1.1, inset=2.2)   # the raised ridge vent (koshi-yane): width, wall height, end inset
BOARD_Z = 1.5                  # dark charred boards below, cream plaster above on the outer walls
AISLE_DOOR = (3.2, 3.3)        # clear width, height of the two aisle doors (west to the yard, east to the paddock)
STALL_DOOR = (1.4, 2.45)       # clear width, height of a stall's sliding door
STALL_FRONT_Z = 2.6            # stall fronts and partitions: solid boards to 1.3 m, bars above up to this height
ROOM_DOOR = (1.0, 2.15)
DOOR_LEAF = .07                # sliding leaf thickness; it hangs on the aisle face
DOOR_GAP = DOOR_LEAF / 2 + .02 # leaf centre plane off the aisle face of its wall
PLAQUE = (.42, .28)            # name plate (width, height): stats plaques show here later
PLAQUE_Z = 1.75                # plate centre over the floor

AISLE_Y0 = BARN_CENTRE[1] - AISLE / 2
AISLE_Y1 = BARN_CENTRE[1] + AISLE / 2


def bay_x(k):
    """(x0, x1) of the clear interior of bay k: 0 is the room bay, 1..STALLS_PER_SIDE the stalls, west to east."""
    x = BARN_X0 + WALL
    if k == 0:
        return x, x + ROOM_W
    x += ROOM_W + (k - 1) * (PART + STALL_W) + PART
    return x, x + STALL_W


def stalls():
    """The ten stalls, west to east, north side first: id, side (+1 north, -1 south), clear box, the sliding door on
    the aisle (closed leaf's bottom centre, slide direction and travel), the name plate and the horse's spot."""
    out = []
    for side, label in ((1, 'N'), (-1, 'S')):
        front = BARN_CENTRE[1] + side * AISLE / 2           # the stall front's aisle face
        back = front + side * (PART + STALL_D)               # the outer wall's inner face
        for k in range(1, STALLS_PER_SIDE + 1):
            x0, x1 = bay_x(k)
            cx = (x0 + x1) / 2
            door_x = x0 + .25 + STALL_DOOR[0] / 2            # door near the stall's west end, plate east of it
            slide = -1.                                      # the leaf opens westwards over the neighbour's solid front
            plaque_x = door_x + STALL_DOOR[0] / 2 + .30 + PLAQUE[0] / 2
            box_y0, box_y1 = sorted((front + side * PART, back))
            out.append(dict(
                id=f'{label}{k}', side=side, index=len(out),
                box=(x0, box_y0, x1, box_y1, FLOOR_Z),
                door=dict(pivot=(door_x, front - side * DOOR_GAP, FLOOR_Z), slide=(slide, 0., 0.),
                          travel=STALL_DOOR[0] + .05, width=STALL_DOOR[0], height=STALL_DOOR[1]),
                plaque=dict(centre=(plaque_x, front - side * .03, FLOOR_Z + PLAQUE_Z), normal=(0., -side, 0.),
                            size=PLAQUE),
                horse=dict(at=(cx, (box_y0 + box_y1) / 2, FLOOR_Z), yaw=-90. * side),   # head towards the door
            ))
    return out


def rooms():
    """The west bay: tack room (north) and jockeys' office (south), each with its door on the aisle."""
    x0, x1 = bay_x(0)
    out = {}
    for name, side in (('tack', 1), ('office', -1)):
        front = BARN_CENTRE[1] + side * AISLE / 2
        y0, y1 = sorted((front + side * PART, BARN_CENTRE[1] + side * (BARN_WIDTH / 2 - WALL)))
        out[name] = dict(box=(x0, y0, x1, y1, FLOOR_Z),
                         door=dict(pivot=(x0 + 1.7, front - side * DOOR_GAP, FLOOR_Z), slide=(-1., 0., 0.),
                                   travel=ROOM_DOOR[0] + .05, width=ROOM_DOOR[0], height=ROOM_DOOR[1]))
    return out


def notice_board():
    """The transfers board: a cork board on the office's east wall (the partition with stall S1), facing west."""
    x0, y0, x1, y1, z = rooms()['office']['box']
    return dict(centre=(x1 - .04, (y0 + y1) / 2, z + 1.55), normal=(-1., 0., 0.), size=(1.6, 1.0))


# ------------------------------------------------------------------ grounds
YARD = (-35.8, -1.4, BARN_X0 - .2, 27.4)     # sand yard between the gate and the barn's west door, inside its fence
GATE = dict(at=(-36., BARN_CENTRE[1]), opening=4.2, height=3.4, post=.32)    # the entrance gate faces west
SIGN = dict(centre=(GATE['at'][0] - .30, GATE['at'][1], 2.82), normal=(-1., 0., 0.), size=(2.6, .72), text=.46)
# The yard's low fence: the gate's bamboo fences run along the west side to YARD_FENCE's y0 and y1, a low timber fence
# closes the north and south sides up to x_north and x_south. The gap left south-east is the way to the paddock.
YARD_FENCE = dict(y0=-1.5, y1=27.5, x_north=-6.5, x_south=-9., height=.95)


def fence_run(s):
    """The bamboo fence's length on side s (+1 north, -1 south) of the gate."""
    edge = GATE['at'][1] + s * (GATE['opening'] / 2 + GATE['post'])
    return abs((YARD_FENCE['y1'] if s > 0 else YARD_FENCE['y0']) - edge)


TROUGH = dict(at=(-13., 22.2), size=(2.4, .8, .72))         # stone trough with a bamboo spout, along x
HITCH = dict(at=(-20., 2.6), length=4.8, height=1.15)       # hitching rail along x
LANTERNS = [(-33.6, 9.0), (-33.6, 15.0), (-8.2, 8.4), (-8.2, 15.6)]
TREES = [(-32.5, 25.5, 'maple', 1.1), (-30., -4.5, 'pine', 1.2), (-3., 24.5, 'maple', .9), (31., 20., 'maple', 1.25),
         (-31.5, 2.2, 'maple', .8)]

# Yard dressing (the yard was too big and empty): an open hay shed (naya) with a tiled gable, a two-wheeled handcart
# (niguruma), barrels, planted tubs, a tea bench under a red parasol (nodate-gasa), shrubs, a garden bed and fire buckets.
HAY_SHED = dict(at=(-23.5, 24.4), size=(7.2, 4.0), eave=2.55)       # open to the south (the yard), ridge along x
CART = dict(at=(-17.2, 17.2), yaw=200., size=(1.1, 2.3))            # bed width, length; shafts point along yaw
BARRELS = [(-29.0, 23.4), (-29.0, 22.5), (-28.2, 22.9)]
TUBS = [(-6.9, 9.3), (-6.9, 14.7), (-15.7, 22.2), (-10.3, 21.6), (-26.4, 7.2)]
BENCH = dict(at=(-24.0, 7.6), length=1.9, parasol=1.3)              # along x, facing north
FIRE_BUCKETS = (-7.4, 6.6)
GARDEN = (-35.2, -1.0, -27.5, 5.5)                                   # grass bed with shrubs and rocks, south-west
SHRUBS = [(-34.4, 25.8, .9), (-34.4, 19.0, .7), (-34.4, 4.6, .8), (-28.8, 4.4, .6), (-33.5, 0.2, .7), (-8.0, 26.4, .9),
          (-12.5, 26.6, .7), (-18.6, 26.6, .6), (-28.4, 26.6, .7), (-20.0, -.6, .7), (-13.0, -.6, .8)]
ROCKS = [(-31.0, 4.4, .55), (-29.6, .6, .4), (-33.6, 2.4, .35)]
PADDOCK = (-2., -31., 34., 1.)               # fenced, south of the barn
PADDOCK_GATE = dict(x=3.5, width=3.6)        # gap in the paddock's north fence
FENCE_POST_STEP = 2.5
FENCE_HEIGHT = 1.35

# The road from the city to the gate. Hidamari's street along x = 920 (city.json roads[9], 6 m of asphalt) runs north
# from the main street (y = 335) and stops at y = 350; the road carries on from there. Island metres.
STREET_END = (920., 350.)
STREET_HALF = 3.
MAIN_STREET_Y = 335.
ROAD_WIDTH = 5.                # dirt lane: a horse and a cart pass each other
ROAD_CORNER = 9.               # fillet radius at the bends
ROAD_CONTROL = ((920., 350.), (920., 366.), (890., 390.), (890., 459.), (917., 459.))   # round the graded slope; the last leg is the gate's axis
ROAD_BLEND = 14.               # metres over which the lane eases from the ground onto the pad's height


def _fillet(points, radius, step):
    """The polyline through `points` with each bend rounded by a quadratic curve, sampled about every `step` metres."""
    out = [points[0]]
    for k in range(1, len(points) - 1):
        a, b, c = points[k - 1], points[k], points[k + 1]
        la, lc = math.dist(a, b), math.dist(b, c)
        d = min(radius, .45 * la, .45 * lc)
        p = (b[0] + (a[0] - b[0]) * d / la, b[1] + (a[1] - b[1]) * d / la)
        q = (b[0] + (c[0] - b[0]) * d / lc, b[1] + (c[1] - b[1]) * d / lc)
        _line(out, p, step)
        n = max(2, int(math.ceil(2 * d / step)))
        for i in range(1, n + 1):
            t = i / n
            out.append(((1 - t) ** 2 * p[0] + 2 * t * (1 - t) * b[0] + t * t * q[0],
                        (1 - t) ** 2 * p[1] + 2 * t * (1 - t) * b[1] + t * t * q[1]))
    _line(out, points[-1], step)
    return out


def _line(out, end, step):
    a = out[-1]
    n = max(1, int(math.ceil(math.dist(a, end) / step)))
    out.extend((a[0] + (end[0] - a[0]) * i / n, a[1] + (end[1] - a[1]) * i / n) for i in range(1, n + 1))


def road_points(step=2.):
    """The road's centre line in the stable's frame, from the street's end to just inside the pad's west edge."""
    return [(x - SITE[0], y - SITE[1]) for x, y in _fillet(ROAD_CONTROL, ROAD_CORNER, step)]


def road_outline(margin=0.):
    """One polygon (island metres) round the road, `margin` metres wider than it on each side."""
    pts = [(x + SITE[0], y + SITE[1]) for x, y in road_points(4.)]
    for end, nxt in ((0, 1), (-1, -2)):               # reach `margin` past both ends too
        (ax, ay), (bx, by) = pts[end], pts[nxt]; d = math.hypot(ax - bx, ay - by)
        pts[end] = (ax + (ax - bx) / d * margin, ay + (ay - by) / d * margin)
    half = ROAD_WIDTH / 2 + margin
    left, right = [], []
    for k, (x, y) in enumerate(pts):
        a, b = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy)
        nx, ny = -dy / n, dx / n
        left.append([x + nx * half, y + ny * half]); right.append([x - nx * half, y - ny * half])
    return left + right[::-1]


def spots():
    """Where people and horses stand (NPC and AI anchors), in the stable's frame."""
    office = rooms()['office']['box']; tack = rooms()['tack']['box']
    hx, hy = HITCH['at']
    return {
        'npc': [
            dict(id='stable_master', at=(GATE['at'][0] + 3.5, GATE['at'][1] - 3.2, 0.), yaw=180.),
            dict(id='jockey_office_desk', at=((office[0] + office[2]) / 2 - .3, office[1] + 1.0, FLOOR_Z), yaw=90.),
            dict(id='jockey_office_board', at=(office[2] - 1.1, (office[1] + office[3]) / 2, FLOOR_Z), yaw=0.),
            dict(id='groom_tack', at=((tack[0] + tack[2]) / 2, (tack[1] + tack[3]) / 2, FLOOR_Z), yaw=90.),
            dict(id='groom_hitch', at=(hx + 1.2, hy + 1.6, 0.), yaw=-90.),
            dict(id='groom_trough', at=(TROUGH['at'][0] - 2.0, TROUGH['at'][1] - 1.4, 0.), yaw=30.),
            dict(id='groom_aisle', at=(bay_x(3)[0], BARN_CENTRE[1], FLOOR_Z), yaw=0.),
        ],
        'horse': [
            *[dict(id=f'stall_{s["id"]}', at=s['horse']['at'], yaw=s['horse']['yaw']) for s in stalls()],
            dict(id='hitch_1', at=(hx - 1.2, hy + 1.6, 0.), yaw=-90.),
            dict(id='hitch_2', at=(hx + 1.2 + 1.0, hy + 1.6, 0.), yaw=-90.),
            dict(id='trough', at=(TROUGH['at'][0], TROUGH['at'][1] - 1.9, 0.), yaw=90.),
            dict(id='paddock_1', at=(10., -12., 0.), yaw=20.),
            dict(id='paddock_2', at=(22., -20., 0.), yaw=160.),
            dict(id='paddock_3', at=(26., -6., 0.), yaw=-70.),
        ],
        'arrival': dict(at=(GATE['at'][0] - 6., GATE['at'][1], 0.), yaw=0.),    # facing the gate, east
    }


# ------------------------------------------------------------------ site
def to_world(p, pad_z):
    """A point of the stable's frame in island metres (YAW is 0)."""
    return (SITE[0] + p[0], SITE[1] + p[1], pad_z + (p[2] if len(p) > 2 else 0.))


def clearance():
    """Polygons (island metres) where the island's trees, bushes, grass and rocks are removed: the pad with a 4 m
    border, and the road's corridor. The graded slopes keep theirs: Hidamari places them on the graded ground."""
    x0, y0, x1, y1 = COMPOUND
    pad = 4.
    sx, sy = SITE
    return [
        [[sx + x0 - pad, sy + y0 - pad], [sx + x1 + pad, sy + y0 - pad], [sx + x1 + pad, sy + y1 + pad],
         [sx + x0 - pad, sy + y1 + pad]],
        road_outline(3.),
    ]


# ------------------------------------------------------------------ budgets
BUDGETS = dict(LOD0=60000, LOD1=15000, LOD2=2500, door_LOD0=600, collision_boxes=120)
LOD_SCREEN_SIZES = (1., .35, .12)    # Unreal screen sizes for LOD0/1/2 (the import uses them later)


# ------------------------------------------------------------------ collision
ROOM_CEIL = 2.7                # the rooms' ceiling (a hay loft over them)
HORSE = dict(length=2.6, width=.9, height=2.45)    # a led horse with its head up, for door and aisle checks
PLAYER = dict(radius=.35, height=1.8)


def _box(boxes, name, x0, x1, y0, y1, z0, z1, rot=(0., 0., 0.)):
    boxes.append(dict(name=name, centre=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                      size=(x1 - x0, y1 - y0, z1 - z0), rot=rot))


def _spans(a0, a1, holes):
    """[a0, a1] minus the (h0, h1) holes."""
    out, a = [], a0
    for h0, h1 in sorted(holes):
        if h1 <= a or h0 >= a1:
            continue
        if h0 - a > 1e-6:
            out.append((a, h0))
        a = max(a, h1)
    if a1 - a > 1e-6:
        out.append((a, a1))
    return out


def collision_boxes():
    """Simple convex boxes for walking (exported as UCX_ boxes): the barn's floor, walls broken at every doorway, stall
    fronts and partitions, the rooms, the two roof slopes, and the solid things of the yard, gate and paddock. Boxes
    are axis-aligned unless rot (degrees about x, y, z) says otherwise. The pad and the road collide as their own
    meshes (walkable ground)."""
    b = []
    cy = BARN_CENTRE[1]
    _box(b, 'barn_floor', BARN_X0, BARN_X1, BARN_Y0, BARN_Y1, -.4, FLOOR_Z)
    door_half = AISLE_DOOR[0] / 2
    for name, x0 in (('wall_west', BARN_X0), ('wall_east', BARN_X1 - WALL)):
        for k, (y0, y1) in enumerate(_spans(BARN_Y0, BARN_Y1, [(cy - door_half, cy + door_half)])):
            _box(b, f'{name}_{k}', x0, x0 + WALL, y0, y1, FLOOR_Z, EAVE_Z)
        _box(b, f'{name}_lintel', x0, x0 + WALL, cy - door_half, cy + door_half, FLOOR_Z + AISLE_DOOR[1], EAVE_Z)
    _box(b, 'wall_south', BARN_X0, BARN_X1, BARN_Y0, BARN_Y0 + WALL, FLOOR_Z, EAVE_Z)
    _box(b, 'wall_north', BARN_X0, BARN_X1, BARN_Y1 - WALL, BARN_Y1, FLOOR_Z, EAVE_Z)
    rx0, rx1 = bay_x(0)
    for side, label in ((1, 'n'), (-1, 's')):
        y0, y1 = sorted((cy + side * AISLE / 2, cy + side * (AISLE / 2 + PART)))
        doors = [(s['door']['pivot'][0] - STALL_DOOR[0] / 2, s['door']['pivot'][0] + STALL_DOOR[0] / 2)
                 for s in stalls() if s['side'] == side]
        for k, (x0, x1) in enumerate(_spans(rx1, BARN_X1 - WALL, doors)):
            _box(b, f'front_{label}_{k}', x0, x1, y0, y1, FLOOR_Z, STALL_FRONT_Z)
        room = rooms()['tack' if side > 0 else 'office']['door']['pivot'][0]
        for k, (x0, x1) in enumerate(_spans(rx0, rx1, [(room - ROOM_DOOR[0] / 2, room + ROOM_DOOR[0] / 2)])):
            _box(b, f'room_front_{label}_{k}', x0, x1, y0, y1, FLOOR_Z, ROOM_CEIL)
        yo0, yo1 = sorted((cy + side * (AISLE / 2 + PART), cy + side * (BARN_WIDTH / 2 - WALL)))
        _box(b, f'room_wall_{label}', rx1, rx1 + PART, yo0, yo1, FLOOR_Z, ROOM_CEIL)
        for k in range(1, STALLS_PER_SIDE):
            x = bay_x(k)[1]
            _box(b, f'partition_{label}{k}', x, x + PART, yo0, yo1, FLOOR_Z, STALL_FRONT_Z)
        _box(b, f'room_ceiling_{label}', rx0, rx1 + PART, yo0, yo1, ROOM_CEIL, ROOM_CEIL + .12)
    # the roof: one slab per slope, tilted about x
    half = BARN_WIDTH / 2 + EAVE_OVERHANG
    run = half / math.cos(math.radians(ROOF_PITCH))
    for side, label in ((1, 'n'), (-1, 's')):
        yc = cy + side * half / 2
        zc = RIDGE_Z - half / 2 * math.tan(math.radians(ROOF_PITCH)) + .15
        b.append(dict(name=f'roof_{label}', centre=(BARN_CENTRE[0], yc, zc), size=(BARN_LENGTH + 2 * EAVE_OVERHANG, run, .3),
                      rot=(-side * ROOF_PITCH, 0., 0.)))
    # yard, gate and paddock
    gx, gy = GATE['at']; o = GATE['opening'] / 2; p = GATE['post']
    for s in (-1, 1):
        y = gy + s * (o + p / 2)
        _box(b, f'gate_post_{"n" if s > 0 else "s"}', gx - p / 2, gx + p / 2, y - p / 2, y + p / 2, 0., GATE['height'])
        y0, y1 = sorted((gy + s * (o + p), gy + s * (o + p + fence_run(s))))
        _box(b, f'gate_fence_{"n" if s > 0 else "s"}', gx - .08, gx + .08, y0, y1, 0., 1.25)
    f = YARD_FENCE
    _box(b, 'yard_fence_n', gx, f['x_north'], f['y1'] - .06, f['y1'] + .06, 0., f['height'])
    _box(b, 'yard_fence_s', gx, f['x_south'], f['y0'] - .06, f['y0'] + .06, 0., f['height'])
    (sx, sy), (sw, sd) = HAY_SHED['at'], HAY_SHED['size']
    _box(b, 'hay_shed_back', sx - sw / 2, sx + sw / 2, sy + sd / 2 - .15, sy + sd / 2, 0., HAY_SHED['eave'])
    for s in (-1, 1):
        _box(b, f'hay_shed_side_{"e" if s > 0 else "w"}', sx + s * sw / 2 - .1, sx + s * sw / 2 + .1,
             sy - sd / 2, sy + sd / 2, 0., HAY_SHED['eave'])
    _box(b, 'hay_stack', sx - sw / 2 + .2, sx + sw / 2 - .2, sy + .2, sy + sd / 2 - .15, 0., 1.4)
    cx, cy = CART['at']; cw, cl = CART['size']
    b.append(dict(name='cart', centre=(cx, cy, .6), size=(cl + 1.4, cw + .3, 1.2), rot=(0., 0., CART['yaw'])))
    for k, (x, y) in enumerate(BARRELS):
        _box(b, f'barrel_{k}', x - .32, x + .32, y - .32, y + .32, 0., .9)
    for k, (x, y) in enumerate(TUBS):
        _box(b, f'tub_{k}', x - .35, x + .35, y - .35, y + .35, 0., .6)
    bx, by = BENCH['at']
    _box(b, 'bench', bx - BENCH['length'] / 2, bx + BENCH['length'] / 2, by - .3, by + .3, 0., .5)
    _box(b, 'parasol_pole', bx - .05, bx + .05, by - .6, by - .5, 0., 2.3)
    x, y = FIRE_BUCKETS
    _box(b, 'fire_buckets', x - .45, x + .45, y - .3, y + .3, 0., .9)
    tx, ty = TROUGH['at']; tw, td, th = TROUGH['size']
    _box(b, 'trough', tx - tw / 2, tx + tw / 2, ty - td / 2, ty + td / 2, 0., th)
    hx, hy = HITCH['at']
    _box(b, 'hitch_rail', hx - HITCH['length'] / 2, hx + HITCH['length'] / 2, hy - .1, hy + .1, 0., HITCH['height'] + .1)
    for k, (lx, ly) in enumerate(LANTERNS):
        _box(b, f'lantern_{k}', lx - .35, lx + .35, ly - .35, ly + .35, 0., 1.9)
    for k, (x, y, _, scale) in enumerate(TREES):
        _box(b, f'tree_{k}', x - .2 * scale, x + .2 * scale, y - .2 * scale, y + .2 * scale, 0., 2.5 * scale)
    x0, y0, x1, y1 = PADDOCK
    g0, g1 = PADDOCK_GATE['x'] - PADDOCK_GATE['width'] / 2, PADDOCK_GATE['x'] + PADDOCK_GATE['width'] / 2
    for k, (a, c) in enumerate(_spans(x0, x1, [(g0, g1)])):
        _box(b, f'paddock_n{k}', a, c, y1 - .08, y1 + .08, 0., FENCE_HEIGHT)
    _box(b, 'paddock_s', x0, x1, y0 - .08, y0 + .08, 0., FENCE_HEIGHT)
    _box(b, 'paddock_w', x0 - .08, x0 + .08, y0, y1, 0., FENCE_HEIGHT)
    _box(b, 'paddock_e', x1 - .08, x1 + .08, y0, y1, 0., FENCE_HEIGHT)
    return b


def _corners(box, lo=-.5, hi=.5):
    """The corners of a collision box between lo and hi of its local y (fractions of its size), rotated x, y then z."""
    (cx, cy, cz), (sx, sy, sz), (rx, ry, rz) = box['centre'], box['size'], box['rot']
    out = []
    for dx in (-.5, .5):
        for fy in (lo, hi):
            for dz in (-.5, .5):
                x, y, z = dx * sx, fy * sy, dz * sz
                a = math.radians(rx); y, z = y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a)
                a = math.radians(ry); x, z = x * math.cos(a) + z * math.sin(a), -x * math.sin(a) + z * math.cos(a)
                a = math.radians(rz); x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
                out.append((cx + x, cy + y, cz + z))
    return out


def aabb_boxes(steps=6):
    """collision_boxes() as axis-aligned (x0, y0, z0, x1, y1, z1) boxes, what Unreal's simple collision takes: a box
    tilted about x (a roof slab) becomes `steps` boxes along its slope, any other rotation its bounding box."""
    out = []
    for b in collision_boxes():
        rx, ry, rz = b['rot']
        cuts = [(-.5 + k / steps, -.5 + (k + 1) / steps) for k in range(steps)] if rx and not (ry or rz) else [(-.5, .5)]
        for k, (lo, hi) in enumerate(cuts):
            c = _corners(b, lo, hi)
            name = b['name'] if len(cuts) == 1 else f'{b["name"]}_{k}'
            out.append(dict(name=name, box=tuple(round(f(p[i] for p in c), 4) for f in (min, max) for i in range(3))))
    return out
