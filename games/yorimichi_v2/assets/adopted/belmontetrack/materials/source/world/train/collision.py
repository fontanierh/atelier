"""The vehicles' collision, in plain Python (no Blender): the convex boxes build.py exports as UCX_ meshes and
placements.json lists, and check_collision(), which tests them against the plan the way a player capsule meets them.

collision_boxes(c) returns [(part, (x0, x1, y0, y1, z0, z1))] in the coach frame."""
import numpy as np

from train import access as A
from train import layout as L


# reservation kinds that have geometry today (fittings.py, build.lookout, the locomotive's body); the others (WC pans,
# bar, back bar, range, stoves) wait for their models and must not get collision before them
MODELLED = {'galley-counter', 'pantry-counter', 'attendant-seat', 'handbrake', 'bench', 'desk', 'luggage-shelves',
            'drinks-ledge', 'steps', 'wall', 'control-stand', 'pipework', 'seat'}


def _free(a0, a1, blocked, min_len=.12):
    out, a = [], a0
    for b0, b1 in sorted(blocked):
        if b1 <= a or b0 >= a1:
            continue
        if b0 - a >= min_len:
            out.append((a, b0))
        a = max(a, b1)
    if a1 - a >= min_len:
        out.append((a, a1))
    return out


def collision_boxes(c):
    """Simple convex boxes for walking: floor, walls broken at every doorway, partitions, ceiling and fixed fittings."""
    b = c.body
    if b.kind == 'tender':
        return tender_collision_boxes(c)
    if b.kind == 'locomotive':
        return loco_collision_boxes(c)
    boxes = []
    add = lambda n, *q: boxes.append((n, q))
    add('floor', b.in_a, b.in_b, -L.IN, L.IN, L.FLOOR_Z - .20, L.FLOOR_Z)
    for q in ceiling_boxes(b):
        add('ceiling', *q)
    for s in (-1, 1):
        if b.end(s) == 'balcony':
            x0, x1 = sorted((b.headstock(s), b.face(s)))
            add('balcony-floor', x0, x1, -L.IN, L.IN, L.FLOOR_Z - .20, L.FLOOR_Z)
    for i, (x0, x1, y0, y1) in enumerate(L.railings(b)):
        add(f'railing-{i}', x0, x1, y0, y1, L.FLOOR_Z, L.FLOOR_Z + 1.05)
    for sy in (-1, 1):
        y0, y1 = sorted((sy * L.IN, sy * L.HALF))
        doors_x = sorted((x0, x1) for _, s, x0, x1, *_ in L.exterior_openings(c) if s == sy)
        for a0, a1 in _free(b.x_a, b.x_b, doors_x, 0.):
            add(f'side-{sy}', a0, a1, y0, y1, L.FLOOR_Z, L.CANT_Z)
        for x0, x1 in doors_x:
            add(f'side-{sy}-over-door', x0, x1, y0, y1, L.FLOOR_Z + L.DOOR_H, L.CANT_Z)
    for w in c.walls:
        spans = _free(w.a0, w.a1, [(o.a0, o.a1) for o in w.openings], 0.)
        top = L.CEIL_SPRING if not w.name.startswith('end-') else L.CANT_Z
        for a0, a1 in spans:
            add(w.name, *((a0, a1, w.c0, w.c1) if w.axis == 'x' else (w.c0, w.c1, a0, a1)), L.FLOOR_Z, top)
        for o in w.openings:
            add(f'{w.name}-head', *((o.a0, o.a1, w.c0, w.c1) if w.axis == 'x' else (w.c0, w.c1, o.a0, o.a1)), o.z1, top)
            if o.z0 - L.FLOOR_Z > .05:         # below a hatch
                add(f'{w.name}-sill', *((o.a0, o.a1, w.c0, w.c1) if w.axis == 'x' else (w.c0, w.c1, o.a0, o.a1)), L.FLOOR_Z, o.z0)
    boxes += furniture_boxes(c) + gangway_boxes(c) + door_boxes(c) + lookout_boxes(c)
    for r in c.reservations:                        # the furniture modelled in code (an unmodelled box stays soft)
        if r.z0 - L.FLOOR_Z < 1.0 and r.kind in MODELLED and r.name != 'cupola-steps':
            add(r.name, r.x0, r.x1, r.y0, r.y1, L.FLOOR_Z, r.z1)
    return [(n, q) for n, q in boxes if q[1] - q[0] > 1e-4 and q[3] - q[2] > 1e-4 and q[5] - q[4] > 1e-4]


def ceiling_boxes(b):
    """The ceiling slab, left open over a roof lookout's well: (x0, x1, y0, y1, z0, z1) pieces."""
    z = (L.CEIL_SPRING, L.CEIL_SPRING + .15)
    well = L.lookout_well(b)
    if not well:
        return [(b.in_a, b.in_b, -L.IN, L.IN, *z)]
    x0, x1, hw, _ = well
    return [(b.in_a, x0, -L.IN, L.IN, *z), (x1, b.in_b, -L.IN, L.IN, *z),
            (x0, x1, -L.IN, -hw, *z), (x0, x1, hw, L.IN, *z)]


def lookout_boxes(c):
    """The brake van's lookout: its four walls from the ceiling up to its roof, the roof slab, the two step treads
    (the lower in front, the upper behind, as build.lookout makes them) and the seat up in the lookout. The ladder
    from the top tread to the seat is an interaction for later."""
    b, F = c.body, L.FLOOR_Z
    if not b.cupola:
        return []
    x0, x1 = b.cupola
    hw, w = L.CUPOLA_HW, L.CUPOLA_WALL
    under, top = L.lookout_top(b)
    z0 = L.CEIL_SPRING
    out = [('lookout-wall-a', (x0, x0 + w, -hw, hw, z0, under)), ('lookout-wall-b', (x1 - w, x1, -hw, hw, z0, under)),
           ('lookout-wall-l', (x0, x1, hw - w, hw, z0, under)), ('lookout-wall-r', (x0, x1, -hw, -hw + w, z0, under)),
           ('lookout-roof', (x0, x1, -hw, hw, under, top))]
    st = next(r for r in c.reservations if r.name == 'cupola-steps')
    lx = L.LOOKOUT_LADDER_X + .03
    out += [('cupola-steps-lower', (lx, st.x1, st.y0, st.y1, F, F + .30)),
            ('cupola-steps-upper', (st.x0, lx, st.y0, st.y1, F, F + .60))]
    sx0, sx1, sy0, sy1, seat = L.LOOKOUT_SEAT
    out.append(('lookout-seat', (sx0, sx1, sy0, sy1, F + seat - .16, F + seat)))
    return out


GANGWAY_OVERLAP = L.GANGWAY_OVERLAP   # past the buffer line: on a 250 m curve the gap between coaches opens a wedge
GANGWAY_SIDE = .10        # thickness of the invisible side walls and roof over a gangway crossing
GROUPS = {'gangway-lock-': 'gangway-lock', 'door-': 'door'}   # switchable boxes, exported apart from the fixed UCX


def group(part):
    """'fixed' for the static collision, or the switchable group a box belongs to (the game opens it for staff, or
    at stops)."""
    return next((g for prefix, g in GROUPS.items() if part.startswith(prefix)), 'fixed')


def named_boxes(c, mesh_name):
    """[(object name, part, group, box)]: the fixed boxes as UE's UCX_<mesh>_NN simple collision, the switchable ones
    as COL_<mesh>_<part> (a part named after its group), separate objects the game turns on and off."""
    out, k = [], 0
    for part, q in collision_boxes(c):
        g = group(part)
        if g == 'fixed':
            out.append((f'UCX_{mesh_name}_{k:02d}', part, g, q)); k += 1
        else:
            out.append((f'COL_{mesh_name}_{part}', part, g, q))
    return out


def gangway_boxes(c):
    """At each gangway end: the floor from the end wall's inner face out past the buffer line, invisible walls each
    side and a roof over the crossing (nobody falls between coaches, even on a curve), and on a gangway locked for
    passengers a 'gangway-lock' box filling the end wall's opening."""
    b, F, hw = c.body, L.FLOOR_Z, L.GANGWAY_W / 2
    locked = {door[-1] for v, door in A.locked_gangways() if v == c.name}
    out = []
    for s, end in ((-1, 'a'), (1, 'b')):
        if b.end(s) != 'gangway':
            continue
        x0, x1 = sorted((b.inner(s), b.buffer(s) + s * GANGWAY_OVERLAP))
        w0, w1 = hw + .04, hw + .04 + GANGWAY_SIDE
        out += [(f'gangway-{end}-floor', (x0, x1, -w0, w0, F - .20, F)),
                (f'gangway-{end}-side-l', (x0, x1, w0, w1, F, F + L.GANGWAY_H + .15)),
                (f'gangway-{end}-side-r', (x0, x1, -w1, -w0, F, F + L.GANGWAY_H + .15)),
                (f'gangway-{end}-roof', (x0, x1, -w1, w1, F + L.GANGWAY_H, F + L.GANGWAY_H + .15))]
        if end in locked:
            out.append((f'gangway-lock-{end}', (*sorted((b.inner(s), b.face(s))), -hw, hw, F, F + L.GANGWAY_H)))
    return out


HANDLE_Z = 1.0           # the Interact prompt point: at handle height,
HANDLE_OUT = .30         # this far out from each face of the door, and
HANDLE_IN = .10          # this far in from the leaf's free edge
OPENS = {'exterior': 'station', 'gate': 'station', 'staff': 'station', 'gangway': 'any', 'internal': 'any'}


def door_id(name):
    """A layout door's id: 'exterior-door-al' -> 'exterior-al', 'door-wc-a' -> 'wc-a', 'salon-doors' -> 'salon'."""
    return name.replace('-doors', '').replace('-door', '').removeprefix('door-')


def doors(c):
    """Every door and balcony gate a player opens with Interact, one at a time: id, layout door name, kind (exterior,
    gangway, internal, gate, or staff: the locomotive's cab doors, for the crew), motion, the rule for when it opens ('station': only while the train stands at a
    station; 'any'), default state, whether it is locked for passengers (a gangway behind a gangway-lock box), its
    collision part and box (a 'door' box, closed until opened), and the Interact points on each side of the leaf."""
    b, F = c.body, L.FLOOR_Z
    locked = {door for v, door in A.locked_gangways() if v == c.name}
    ext = {e[0]: e for e in L.exterior_openings(c)}
    gb = dict(gangway_boxes(c))
    out = []

    def rec(i, name, kind, motion, box, handle_a, along, sides, lock=False):
        pts = [dict(side=n, point=[round(v, 4) for v in (*((handle_a, cc) if along == 'x' else (cc, handle_a)), F + HANDLE_Z)])
               for n, cc in sides]
        part = f'gangway-lock-{i[-1]}' if lock else f'door-{i}'
        out.append(dict(id=i, door=name, kind=kind, motion=motion, opens=OPENS[kind], default='closed', locked=lock,
                        part=part, box=gb[part] if lock else box, handles=pts))

    def free_edge(a0, a1, hinge):
        return a1 - HANDLE_IN if hinge == a0 else a0 + HANDLE_IN

    for d in c.doors:
        i = door_id(d.name)
        if i in ext:                                    # exterior and cargo doors in the side walls
            _, sy, x0, x1, z0, z1 = ext[i]
            box = (x0, x1, *sorted((sy * L.IN, sy * L.HALF)), z0, z1)
            ha = (x0 + x1) / 2 if d.kind == 'cargo' else free_edge(x0, x1, x0 if x0 < 0 else x1)
            rec(i, d.name, 'exterior', 'sliding' if d.kind == 'cargo' else 'hinged', box, ha, 'x',
                (('inside', sy * (L.IN - HANDLE_OUT)), ('outside', sy * (L.HALF + HANDLE_OUT))))
            continue
        w = c.wall(d.wall); o = next(o for o in w.openings if o.name == d.opening)
        box = (*((o.a0, o.a1, w.c0, w.c1) if w.axis == 'x' else (w.c0, w.c1, o.a0, o.a1)), o.z0, o.z1)
        if d.kind == 'sliding':
            ha = o.a0 + HANDLE_IN if d.slide > 0 else o.a1 - HANDLE_IN
        elif d.kind == 'double':
            ha = (o.a0 + o.a1) / 2
        else:
            ha = free_edge(o.a0, o.a1, o.a0 if d.slide < 0 else o.a1)
        sides = []
        for cc in (w.c0 - HANDLE_OUT, w.c1 + HANDLE_OUT):
            x, y = (ha, cc) if w.axis == 'x' else (cc, ha)
            room = L._room_at(c, x, y)
            sides.append(('gangway' if room == '?' and i.startswith('gangway') else room, cc))
        kind = 'gangway' if i.startswith('gangway') else 'internal'
        rec(i, d.name, kind, d.kind, box, ha, w.axis, sides, lock=kind == 'gangway' and d.name in locked)
    if b.kind == 'locomotive':                         # the crew's doors in the cab side cut-outs
        ca, ce = L.CAB[0], L.CAB_ENTRY
        for side, sy in (('l', 1), ('r', -1)):
            box = (ca, ce, *sorted((sy * L.CAB_IN, sy * L.LOCO_HALF)), F, F + CAB_DOOR_H)
            rec(f'cab-{side}', None, 'staff', 'hinged', box, free_edge(ca, ce, ce), 'x',
                (('cab', sy * (L.CAB_IN - HANDLE_OUT)), ('outside', sy * (L.LOCO_HALF + HANDLE_OUT))))
            out[-1]['locked'] = A.LOCKED_DOORS         # crew only while the class rules are on
    for s, end in ((-1, 'a'), (1, 'b')):
        if b.end(s) != 'balcony':
            continue
        gx0, gx1 = L.balcony_gate(b, s)
        hinge = gate_hinge(b, s)
        for side, sy in (('l', 1), ('r', -1)):
            box = (gx0, gx1, *sorted((sy * (L.IN - .05), sy * L.HALF)), F, L.ROOF_TOP)
            rec(f'gate-{end}{side}', None, 'gate', 'hinged', box, free_edge(gx0, gx1, hinge), 'x',
                (('balcony', sy * (L.IN - .05 - HANDLE_OUT)), ('outside', sy * (L.HALF + HANDLE_OUT))))
    return out


BOARD_OUT = .60          # the outside start stands this far beyond the body side, on the ground (rail top, z 0)
BOARD_IN = .45           # the inside end stands this far in from the side wall, on the floor


def boarding(c):
    """How a player boards or alights at each passenger door and balcony gate (Interact, D-pad down; at a station
    only, as the door's own rule): the door, the outside start on the ground beside the steps, the two treads (upper
    first), the inside end on the floor, the yaw to face for boarding and for alighting (0 faces -Y, 90 faces +X), and
    the door's Interact points. The game opens the door, moves the player up or down the treads and shuts it again."""
    F, out = L.FLOOR_Z, []
    for d in doors(c):
        if d['kind'] not in ('exterior', 'gate') or d['id'].startswith('cargo'):
            continue
        x0, x1, y0, y1 = d['box'][:4]
        sy = 1 if y0 > 0 else -1
        xc = (x0 + x1) / 2
        r = lambda *v: [round(float(a), 4) for a in v]   # noqa: E731
        out.append(dict(
            id=d['id'], door=d['part'], kind=d['kind'], opens=d['opens'], side=sy,
            outside=r(xc, sy * (L.HALF + BOARD_OUT), 0.),
            treads=[dict(box=r(*t[:4]), top_z=t[4]) for t in L.step_treads(sy, x0, x1)],
            inside=r(xc, sy * (L.IN - BOARD_IN), F),
            board_yaw=0. if sy > 0 else 180., alight_yaw=180. if sy > 0 else 0.,
            handles=d['handles']))
    return out


def gate_hinge(body, s):
    """A balcony gate hangs on the post at its end-wall side and swings in over the balcony."""
    gx0, gx1 = L.balcony_gate(body, s)
    return gx1 if s < 0 else gx0


def door_boxes(c):
    """A 'door' box closing every door and gate that is not locked behind a gangway-lock box (the game removes one
    when a player opens that door), and, fixed, an invisible wall from each balcony railing's top up to the canopy (a
    jump clears 1.05 m)."""
    out = [(d['part'], d['box']) for d in doors(c) if not d['locked']]
    for i, (x0, x1, y0, y1) in enumerate(L.railings(c.body)):
        out.append((f'railing-{i}-above', (x0, x1, y0, y1, L.FLOOR_Z + 1.05, L.ROOF_TOP)))
    return out


SOFT = {'wall-sconce', 'table-lamp', 'canteen-mug', 'canteen-ladle', 'canteen-pot'}   # small, or standing on another
BACK = .15                                          # a seat's back slab, along the side away from where it faces


def furniture_boxes(c):
    """One box per floor-standing placement, from its footprint and the contract's height; seating is a block up to
    its seat height (where the seated marker rests) and a back slab up to its full height."""
    spec = {a['id']: a for a in L.contract()['assets']}
    out = []
    for p in c.placements:
        if p.z - L.FLOOR_Z >= .05 or p.asset in SOFT:
            continue
        x0, x1, y0, y1 = L.footprint(p)
        h = L.asset_dims(p.asset)[2]
        seat = spec[p.asset].get('seat_height_m')
        if not seat:
            out.append((p.id, (x0, x1, y0, y1, L.FLOOR_Z, L.FLOOR_Z + h)))
            continue
        out.append((p.id, (x0, x1, y0, y1, L.FLOOR_Z, L.FLOOR_Z + seat)))
        fx, fy = round(np.sin(np.radians(p.yaw))), round(-np.cos(np.radians(p.yaw)))   # the way it faces (0 = -Y)
        back = {(1, 0): (x0, x0 + BACK, y0, y1), (-1, 0): (x1 - BACK, x1, y0, y1),
                (0, 1): (x0, x1, y0, y0 + BACK), (0, -1): (x0, x1, y1 - BACK, y1)}[(fx, fy)]
        out.append((f'{p.id}-back', (*back, L.FLOOR_Z + seat, L.FLOOR_Z + h)))
    return out


FOOTPLATE_OVERLAP = .01   # the cab floor and the tender's footplate each run this far past their buffer line
CAB_DOOR_H = 1.95         # the cab side doors, under their header


def tender_collision_boxes(c):
    hw, (ta, tb), (z0, z1) = L.TENDER_HALF, L.TENDER_TANK, L.TENDER_TANK_Z
    lx0, lx1, ly, lz = L.TENDER_LOCKER
    # the footplate (with its fall plate) runs 1 cm past the buffer line onto the locomotive's cab floor
    boxes = [('floor', (tb, c.body.buffer_b + FOOTPLATE_OVERLAP, -hw + .10, hw - .10, L.FLOOR_Z - .20, L.FLOOR_Z)),
             ('tank', (ta, tb, -hw, hw, z0, L.TENDER_COPING_Z)),
             ('frames', (-L.TENDER_HEADSTOCK, L.TENDER_HEADSTOCK, -1.45, 1.45, .30, z0))]
    for side, sy in (('l', 1), ('r', -1)):
        y0, y1 = sorted((sy * ly, sy * hw))
        boxes.append((f'locker-{side}', (lx0, lx1, y0, y1, L.FLOOR_Z, lz)))
        y0, y1 = sorted((sy * (hw - .10), sy * hw))
        boxes.append((f'handrail-{side}', (lx1, L.TENDER_FALL_PLATE, y0, y1, L.FLOOR_Z, L.FLOOR_Z + 1.20)))
    return boxes


def loco_collision_boxes(c):
    F = L.FLOOR_Z
    hw, cin = L.LOCO_HALF, L.CAB_IN
    (ca, cb), ce = L.CAB, L.CAB_ENTRY
    bx = L.BACKHEAD_X
    (b0, b1, br, bz), (s0, s1, sr) = L.BOILER, L.SMOKEBOX
    boxes = [('floor', (c.body.buffer_a - FOOTPLATE_OVERLAP, cb, -cin, cin, F - .20, F)),
             ('backhead', (bx, cb, -L.FIREBOX_HW, L.FIREBOX_HW, F, L.FIREBOX_TOP)),
             ('cab-roof', (ca - .25, cb, -hw, hw, L.CAB_TOP, L.CAB_ROOF)),
             ('boiler', (b0, s1, -br - .1, br + .1, L.RUNNING_BOARD_Z - .05, bz + br + .3)),
             ('running-gear', (-5.0, L.LOCO_BEAM + .14, -hw, hw, .20, L.RUNNING_BOARD_Z))]
    for side, sy in (('l', 1), ('r', -1)):
        y0, y1 = sorted((sy * cin, sy * hw))
        boxes.append((f'cab-side-{side}', (ce, cb, y0, y1, F, L.CAB_TOP)))
        boxes.append((f'cab-front-{side}', (cb - .06, cb, *sorted((sy * L.FIREBOX_HW, sy * hw)), F, L.CAB_TOP)))
        boxes.append((f'cab-side-{side}-over-door', (L.CAB[0], ce, y0, y1, F + CAB_DOOR_H, L.CAB_TOP)))
    for r in c.reservations:
        boxes.append((r.name, (r.x0, r.x1, r.y0, r.y1, r.z0, r.z1)))
    return boxes + door_boxes(c)


# --- checks: the collision against the plan, as a player capsule meets it ----------------------------------------
F = L.FLOOR_Z
STEP_UP = .45          # UE MaxStepHeight: anything lower than this does not stop a capsule
PERCH = .08            # a capsule stays up while its centre is this close to a floor edge
SHELL = ('floor', 'ceiling', 'side-', 'end-', 'balcony-floor', 'railing', 'gangway-')
SOFT_ASSETS = SOFT
SEAT_BACK_CLEAR = .10  # and at least this far from its backrest's collision slab
SEAT_GAP = .03         # a seat marker floats at most this far above its collision top, and never sinks into it


def _cover(rect, boxes, z):
    """Share of a plan rectangle covered by boxes that span height z above the floor (5 cm raster)."""
    x0, x1, y0, y1 = rect
    xs = np.arange(x0 + .025, x1, .05); ys = np.arange(y0 + .025, y1, .05)
    if not len(xs) or not len(ys):
        return 1.
    X, Y = np.meshgrid(xs, ys, indexing='ij'); hit = np.zeros(X.shape, bool)
    for _, b in boxes:
        if b[4] <= F + z <= b[5]:
            hit |= (X >= b[0]) & (X <= b[1]) & (Y >= b[2]) & (Y <= b[3])
    return hit.mean()


def _visual_rects(c):
    """Plan rectangles of everything visible that a box may stand for: placements, reservations with a fitting."""
    out = [L.footprint(p) for p in c.placements if p.z - F < .05]
    out += [(b.x0, b.x1, b.y0, b.y1) for b in c.reservations if b.kind in MODELLED]
    return out


def _grid(c, boxes, radius, step=.025):
    b = c.body
    x0, x1 = b.buffer_a, b.buffer_b
    xs = np.arange(x0 + step / 2, x1, step); ys = np.arange(-L.HALF - .3, L.HALF + .3, step)
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    floor = np.zeros(X.shape, bool); free = np.ones(X.shape, bool)
    for s in (-1, 1):                                       # past a gangway's buffer line: the next coach's floor
        if b.end(s) == 'gangway':
            floor |= (s * (X - b.buffer(s)) > 0) & (np.abs(Y) < L.GANGWAY_W / 2 + .04)
    for _, q in boxes:
        if abs(q[5] - F) < .03 and q[4] < F:
            floor |= (X >= q[0] - PERCH) & (X <= q[1] + PERCH) & (Y >= q[2] - PERCH) & (Y <= q[3] + PERCH)
        if q[5] > F + STEP_UP and q[4] < F + A.tallest():
            dx = np.maximum(np.maximum(q[0] - X, 0.), X - q[1]); dy = np.maximum(np.maximum(q[2] - Y, 0.), Y - q[3])
            free &= dx * dx + dy * dy >= radius * radius
    return xs, ys, floor, free


def _flood(mask, seed):
    seen = np.zeros(mask.shape, bool); stack = [seed] if mask[seed] else []
    for s in stack:
        seen[s] = True
    while stack:
        i, j = stack.pop()
        for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
            if 0 <= a < mask.shape[0] and 0 <= b < mask.shape[1] and mask[a, b] and not seen[a, b]:
                seen[a, b] = True; stack.append((a, b))
    return seen


def check_collision(c, boxes):
    bad = []
    # 1. every solid thing a player can walk into has collision over >= 85 % of its plan, at knee height
    for p in c.placements:
        if p.z - F < .05 and p.asset not in SOFT_ASSETS:
            share = _cover(L.footprint(p), boxes, .30)
            if share < .85:
                bad.append(f'{p.id} ({p.asset}) has collision over {share:.0%} of its footprint')
    for b in c.reservations:
        if b.kind in MODELLED and b.z0 - F < 1.0:
            share = _cover((b.x0, b.x1, b.y0, b.y1), boxes, (b.z0 + b.z1) / 2 - F)
            if share < .85:
                bad.append(f'{b.name} ({b.kind}) has collision over {share:.0%} of its box')
    # 2. no invisible blocks: a non-shell box must stand over something visible
    rects = _visual_rects(c)
    fixed = {b.name for b in c.reservations} | {p.id for p in c.placements}
    for part, q in boxes:
        if part not in fixed:                                   # shell, walls, the engine's body: not checked here
            continue
        area = (q[1] - q[0]) * (q[3] - q[2])
        seen = sum(max(0., min(q[1], r[1]) - max(q[0], r[0])) * max(0., min(q[3], r[3]) - max(q[2], r[2])) for r in rects)
        if seen < .6 * area:
            bad.append(f'collision {part} has nothing visible under {1 - seen / area:.0%} of it')
    # 3. on the collision alone, the widest player reaches every goal and never walks off a floor edge
    #    (every door open, as a player opens them one by one; floor edges with them all shut, as while running)
    radius = max(p[2] for p in A.players())
    xs, ys, floor, free_open = _grid(c, [(p, q) for p, q in boxes if group(p) != 'door'], radius)
    _, _, _, free = _grid(c, boxes, radius)
    cell = lambda x, y: (int(np.searchsorted(xs, x)), int(np.searchsorted(ys, y)))
    seen = _flood(floor & free_open, cell(*L.start(c)))
    for g, (x, y) in L.goals(c).items():
        if not seen[cell(x, y)]:
            bad.append(f'{g} unreachable on collision')
    edge = np.zeros_like(seen); hole = free & ~floor
    edge[1:] |= seen[:-1] & hole[1:]; edge[:-1] |= seen[1:] & hole[:-1]
    edge[:, 1:] |= seen[:, :-1] & hole[:, 1:]; edge[:, :-1] |= seen[:, 1:] & hole[:, :-1]
    if edge.any():
        i, j = np.nonzero(edge)
        bad.append(f'{len(i)} floor-edge cells with no wall, e.g. at ({xs[i[0]]:.2f}, {ys[j[0]]:.2f})')
    # 3b. every place a player reaches is inside an interior (no-sprint) volume
    vols = [v['box'] for v in L.interior_volumes(c) if 'interior' in v['tags']]
    X, Y = np.meshgrid(xs, ys, indexing='ij'); inside = np.zeros_like(seen)
    for q in vols:
        inside |= (X >= q[0]) & (X <= q[1]) & (Y >= q[2]) & (Y <= q[3])
    out = seen & ~inside
    if out.any():
        i, j = np.nonzero(out)
        bad.append(f'{len(i)} reachable cells outside every interior volume, e.g. at ({xs[i[0]]:.2f}, {ys[j[0]]:.2f})')
    # 4. gangways: floor to the buffer line and closed sides and top, so two coaches' boxes meet at the buffers
    for s in (-1, 1):
        if c.body.end(s) != 'gangway':
            continue
        bf, fx = c.body.buffer(s), c.body.face(s)
        mid = (fx + bf) / 2
        hw = L.GANGWAY_W / 2 + .04
        need = {'floor': (mid, 0., F - .05), 'side+': (mid, hw + .03, F + 1.), 'side-': (mid, -hw - .03, F + 1.),
                'roof': (mid, 0., F + L.GANGWAY_H + .10)}
        for what, (x, y, z) in need.items():
            if not any(q[0] <= x <= q[1] and q[2] <= y <= q[3] and q[4] <= z <= q[5] for _, q in boxes):
                bad.append(f'gangway {"ab"[s > 0]}: no {what} collision between the end wall and the buffers')
    # 5. locked gangways are shut by collision (a box named gangway-lock-a/b over the end-wall opening)
    for v, door in A.locked_gangways():
        if v == c.name and not any(p == f'gangway-lock-{door[-1]}' for p, _ in boxes):
            bad.append(f'{door} is locked for passengers but its opening is free in collision')
    # 6. every door and balcony gate is shut by its own box ('door', or 'gangway-lock' when locked), and a balcony's
    #    railing is walled up to the canopy
    parts = {p for p, _ in boxes}
    need = [d['part'] for d in doors(c)] + [f'door-gate-{e}{sd}' for s, e in ((-1, 'a'), (1, 'b'))
                                            if c.body.end(s) == 'balcony' for sd in 'lr']
    need += [f'door-{o[0]}' for o in L.exterior_openings(c)] + [f'railing-{i}-above' for i in range(len(L.railings(c.body)))]
    bad += [f'{n} has no collision' for n in need if n not in parts]
    # 7. every seat marker sits on, or up to SEAT_GAP above, a collision top (nothing solid over it to its height),
    #    0.40-0.50 m above the floor
    for st in c.seats:
        tops = [q[5] for _, q in boxes if q[0] <= st.x <= q[1] and q[2] <= st.y <= q[3] and q[4] < st.z]
        if not tops or not -1e-6 <= st.z - max(tops) <= SEAT_GAP:
            bad.append(f'seat {st.id}: {"no collision top under it" if not tops else f"{st.z - max(tops):+.2f} m from its collision top"}')
        elif c.name not in ('locomotive',) and not .40 - 1e-6 <= st.z - F <= .50:
            bad.append(f'seat {st.id}: sitting height {st.z - F:.2f} m')
        back = next((q for p, q in boxes if p == f'{st.furniture}-back'), None)
        if back:                                                # the hips clear the backrest
            d = np.hypot(max(back[0] - st.x, 0., st.x - back[1]), max(back[2] - st.y, 0., st.y - back[3]))
            if d < SEAT_BACK_CLEAR:
                bad.append(f'seat {st.id}: {d:.2f} m from its backrest')
    # 8. a roof lookout's well is open in the ceiling collision
    if c.body.cupola:
        x0, x1 = c.body.cupola
        if any(p == 'ceiling' and q[0] < x1 - .1 and q[1] > x0 + .1 and q[2] < 0 < q[3] for p, q in boxes):
            bad.append('the ceiling collision closes the lookout well')
    return bad
