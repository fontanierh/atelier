"""The coach fittings hung on the layout's mounts, modelled in code (plain Python; build.py turns them into meshes).

Every coach and van in its own style (STYLES): polished brass and burgundy or emerald velvet in the restaurant and
first class, dull brass and worn cloth in second class and the vans:
- rack: a luggage net over the seats, brass rods on two cast wall brackets (or hung from the ceiling where the rack
  sits above the top of the wall) and a sagging cord net;
- ceiling-lamp: a bare bulb under a small enamel shade (grimy outside, sooted inside, chipped rim), on a twisted
  cord from a ceiling rose (cord and rose LOD0 only);
- curtain-rail: a thin rod over the window and two softly pleated curtains drawn to its sides, mapped in metres;
- menu-board: the canteen's framed menu board, its face a texture slot (T_BT_MenuBoard);
- luggage shelving: open walnut shelves on every 'luggage-shelves' reservation (vans and first class), low under a
  window so the curtains hang clear;
- counters: fitted cupboards with a top on the galley's and the pantry's counters (the galley range left to Tripo),
  the pantry attendant's folding seat, the vans' handbrake columns, the guard's locker bench and
  the guards' desks with pigeon-holes;
- drinks ledge: the restaurant's standing ledge under a window, walnut on brass brackets, with a foot rail;
- ladle: the iron wall hook the canteen lady's big ladle hangs from (the ladle itself is a separate asset).
The other mount kinds are anchors for gameplay (ANCHORS) or modelled with the shell in build.py (BUILT).

Each fitting kind gives one Part (one object for every mount of that kind, few draw calls): its faces as
(points, material, uv or None) in the coach frame, whether the mesh is closed, its LODs and its light sockets.
"""
import math
from dataclasses import dataclass, field

from train import layout as L

# per coach: rack and rail metal, net cord, curtain cloth (all cloth is mapped in metres: CURTAIN_TILE)
STYLES = {
    'restaurant': dict(metal='brass', net='cord-burgundy', cloth='velvet-burgundy'),
    'first-class': dict(metal='brass', net='cord-emerald', cloth='velvet-emerald'),
    'second-class': dict(metal='brass-dull', net='cord', cloth='curtain-fabric'),
    'baggage-van': dict(metal='brass-dull', net='cord', cloth='curtain-canvas'),
    'brake-van': dict(metal='brass-dull', net='cord', cloth='curtain-canvas'),
    'locomotive': dict(metal='brass-dull', net='cord', cloth='curtain-canvas'),     # only its cab lamp
}
COACHES = set(STYLES)
ANCHORS = {'npc-spot', 'serve-point', 'queue'}      # where the canteen lady stands, the tray lands, passengers queue
BUILT = {'tail-lamp', 'control', 'gauge', 'head-lamp', 'emitter'}   # in build.py: the brake van's tail lamp on its
# balcony; the locomotive's controls, head lamp and chimney socket with its body (its gauges are on the Tripo backhead)

RACK_DEPTH, RACK_SAG, ROD_R = .30, .04, .008
NET_CORD = .008                                       # width of a cord ribbon
SHADE_R, SHADE_H, CORD_LEN = .13, .10, .20          # the bulb clears a 1.75 m adult by 15 cm in the aisle
CURTAIN_W, CURTAIN_PITCH, CURTAIN_AMP, CURTAIN_GAP = .26, .065, .02, .065   # gathered width, pleat, depth, off the wall
CURTAIN_TILE = .50                                    # metres of cloth per repeat of the fabric swatch (T_BT_CurtainFabric)
BOARD_H, BOARD_FRAME = .32, .04


@dataclass
class Part:
    name: str
    faces: list = field(default_factory=list)
    closed: bool = True
    lods: tuple = (0, 1)
    sockets: list = field(default_factory=list)       # (name, (x, y, z)): where a runtime light goes
    smooth: float = 35.                               # edges sharper than this stay hard (degrees)

    def quad(self, a, b, c_, d, mat, uv=None):
        self.faces.append(([a, b, c_, d], mat, uv))


def _sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def _add(a, b, s=1.): return (a[0] + b[0] * s, a[1] + b[1] * s, a[2] + b[2] * s)
def _cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    n = math.sqrt(sum(v * v for v in a)) or 1.
    return (a[0] / n, a[1] / n, a[2] / n)


def tube(p, pts, r, mat, sides=6, caps=True):
    """A round bar of radius r along a polyline."""
    rings = []
    for i, c in enumerate(pts):
        d = _unit(_sub(pts[min(i + 1, len(pts) - 1)], pts[max(i - 1, 0)]))
        ref = (0, 0, 1) if abs(d[2]) < .9 else (1, 0, 0)
        u = _unit(_cross(d, ref)); v = _cross(d, u)
        rings.append([_add(_add(c, u, r * math.cos(2 * math.pi * k / sides)), v, r * math.sin(2 * math.pi * k / sides)) for k in range(sides)])
    for a, b in zip(rings, rings[1:]):
        for k in range(sides):
            p.quad(a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k], mat)
    if caps:
        p.faces.append((rings[0][::-1], mat, None)); p.faces.append((rings[-1], mat, None))


def ribbon(p, pts, w, mat, across=(0, 0, 1)):
    """A flat strip of width w along a polyline, lying across `across` (a cord seen from above and below)."""
    for a, b in zip(pts, pts[1:]):
        d = _unit(_sub(b, a)); s = _unit(_cross(d, across))
        p.quad(_add(a, s, -w / 2), _add(b, s, -w / 2), _add(b, s, w / 2), _add(a, s, w / 2), mat)


def _noise(*v):
    """A repeatable pseudo-random number in [0, 1) from a few numbers (no global random state)."""
    return math.modf(math.sin(sum(a * b for a, b in zip(v, (12.9898, 78.233, 37.719, 4.581)))) * 43758.5453)[0] % 1.


def lathe(p, cx, cy, profile, mat, seg=14):
    """A surface of revolution about the vertical through (cx, cy) from (radius, z) points, top to bottom. mat is a
    material name, or a function (band, segment) -> material name for bands and patches of their own."""
    ring = lambda r, z: [(cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z) for k in range(seg)]
    loops = [ring(r, z) for r, z in profile]
    for i, (a, b) in enumerate(zip(loops, loops[1:])):
        for k in range(seg):
            m = mat(i, k) if callable(mat) else mat
            if profile[i][0] < 1e-6:
                p.faces.append(([a[k], b[(k + 1) % seg], b[k]], m, None))
            elif profile[i + 1][0] < 1e-6:
                p.faces.append(([a[k], a[(k + 1) % seg], b[k]], m, None))
            else:
                p.quad(a[k], a[(k + 1) % seg], b[(k + 1) % seg], b[k], m)


def box(p, x0, x1, y0, y1, z0, z1, mat):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1)); z0, z1 = sorted((z0, z1))
    P = lambda i, j, k: ((x0, x1)[i], (y0, y1)[j], (z0, z1)[k])
    for q in ([P(0, 1, 0), P(0, 0, 0), P(0, 0, 1), P(0, 1, 1)], [P(1, 0, 0), P(1, 1, 0), P(1, 1, 1), P(1, 0, 1)],
              [P(0, 0, 0), P(1, 0, 0), P(1, 0, 1), P(0, 0, 1)], [P(1, 1, 0), P(0, 1, 0), P(0, 1, 1), P(1, 1, 1)],
              [P(0, 1, 0), P(1, 1, 0), P(1, 0, 0), P(0, 0, 0)], [P(0, 0, 1), P(1, 0, 1), P(1, 1, 1), P(0, 1, 1)]):
        p.faces.append((q, mat, None))


def into_room(c, mt):
    """The unit vector from the wall a mount hangs on into its room (the nearest edge of the room's rectangle)."""
    r = c.room(mt.room)
    edges = [(mt.x - r.x0, (1, 0)), (r.x1 - mt.x, (-1, 0)), (mt.y - r.y0, (0, 1)), (r.y1 - mt.y, (0, -1))]
    return min(edges)[1]


def _frame(c, mt):
    """Wall-mount frame: (u along the wall, v out from the wall face into the room, height z) -> coach coordinates."""
    nx, ny = into_room(c, mt)
    tx, ty = -ny, nx
    r = c.room(mt.room)
    wx = mt.x if not nx else (r.x0 if nx > 0 else r.x1)
    wy = mt.y if not ny else (r.y0 if ny > 0 else r.y1)
    return lambda u, v, z: (wx + tx * u + nx * v, wy + ty * u + ny * v, z)


def racks(c, part, net, metal='brass-dull', cord='cord'):
    for mt in c.mounts:
        if mt.kind != 'rack':
            continue
        P, h, z = _frame(c, mt), mt.length / 2, mt.z
        on_wall = z + .09 < L.ceiling_z(P(0, 0, z)[1])                    # the bracket's plate fits on the wall
        if not on_wall:                                                   # under the ceiling's curve: level, clear of it
            z = min(z, L.ceiling_z(P(0, .05, z)[1]) - .035)
        for v in (.05, RACK_DEPTH):                                       # back and front rods
            tube(part, [P(-h, v, z), P(h, v, z)], ROD_R, metal, 8)
        for u in (-h + .06, h - .06):
            tube(part, [P(u, .01, z), P(u, RACK_DEPTH + .015, z)], .007, metal, 6)                   # arm
            if on_wall:                                                   # cast bracket: wall plate and strut above
                a, b = P(u - .025, 0, z - .03), P(u + .025, .012, z + .08)
                box(part, a[0], b[0], a[1], b[1], a[2], b[2], metal)
                tube(part, [P(u, .01, z + .06), P(u, .22, z)], .006, metal, 6)
            else:                                                         # above the wall: hangers from the ceiling
                for v in (.05, RACK_DEPTH):
                    q = P(u, v, z)
                    tube(part, [q, (q[0], q[1], L.ceiling_z(q[1]))], .006, metal, 6)
        sag = lambda u, v: z - RACK_SAG * math.sin(math.pi * (v - .05) / (RACK_DEPTH - .05)) * (.7 + .3 * math.cos(math.pi * u / h))
        n_u = 16
        for k in range(1, 5):                                             # cords along the rack
            v = .05 + k * (RACK_DEPTH - .05) / 5
            ribbon(net, [P(-h + .01 + i * (2 * h - .02) / n_u, v, sag(-h + .01 + i * (2 * h - .02) / n_u, v)) for i in range(n_u + 1)], NET_CORD, cord)
        n = int((2 * h - .02) / .10)
        for i in range(n + 1):                                            # cords across, every 10 cm
            u = -h + .01 + i * (2 * h - .02) / n
            ribbon(net, [P(u, v, sag(u, v)) for v in [.05 + j * (RACK_DEPTH - .05) / 5 for j in range(6)]], NET_CORD, cord,
                   across=(0, 0, 1))


def lamps(c, part, cords):
    for n, mt in enumerate(m for m in c.mounts if m.kind == 'ceiling-lamp'):
        x, y, z = mt.x, mt.y, mt.z
        lathe(cords, x, y, [(0, z + .02), (.045, z + .02), (.045, z), (.03, z - .02), (0, z - .02)], 'enamel-grimy', 8)   # ceiling rose
        z0, z1 = z - .02, z - .02 - CORD_LEN
        for s in (0, math.pi):                                            # two twisted strands
            tube(cords, [(x + .003 * math.cos(s + 9 * t), y + .003 * math.sin(s + 9 * t), z0 + (z1 - z0) * t / 6) for t in range(7)],
                 .0025, 'end-dark', 3)
        lathe(part, x, y, [(0, z1), (.018, z1), (.018, z1 - .055), (0, z1 - .055)], 'end-dark', 8)                   # bakelite holder
        # the shade: an enamel cone, grimy outside, sooted inside above the bulb, its rim chipped to the dark iron
        def shade(band, k, n=n):
            if band in (2, 3):
                return 'iron-black' if _noise(n, k, band) < .55 else 'enamel-grimy'
            if band >= 4:
                return 'enamel-soot' if band == 5 or _noise(n, k, 9) < .6 else 'enamel-grimy'
            return 'enamel-grimy' if band == 0 or _noise(n, k, 3) < .7 else 'enamel-white'
        zs = z1 - .03
        lathe(part, x, y, [(.02, zs), (.06, zs - .03), (SHADE_R, zs - SHADE_H), (SHADE_R + .004, zs - SHADE_H - .004),
                           (SHADE_R - .004, zs - SHADE_H), (.057, zs - .033), (.017, zs - .003)], shade, 12)
        zb = z1 - .055
        lathe(part, x, y, [(.008, zb), (.014, zb - .02), (.03, zb - .05), (.031, zb - .07), (.02, zb - .095), (0, zb - .10)], 'lamp-white', 10)
        part.sockets.append((f'SOCKET_Light_{"".join(w.title() for w in mt.id.split("-"))}', (x, y, zb - .06)))


def _pivot(pl):
    return next(a['pivot'] for a in L.contract()['assets'] if a['id'] == pl.asset)


def _top(pl):
    """The highest point of a placement: its pivot is at its base, or at its top for things hung from a hook."""
    return pl.z if _pivot(pl) == 'hook_top' else pl.z + L.asset_dims(pl.asset)[2]


def curtains(c, rails, cloth, metal='brass-dull', fabric='curtain-fabric'):
    windows = {f'curtain-{w.name}': w for w in c.windows}
    for mt in c.mounts:
        if mt.kind != 'curtain-rail':
            continue
        w = windows[mt.id]
        P, h, z = _frame(c, mt), mt.length / 2, mt.z
        tube(rails, [P(-h, CURTAIN_GAP, z), P(h, CURTAIN_GAP, z)], ROD_R, metal, 8)
        for u in (-h, h):
            tube(rails, [P(u, 0, z), P(u, CURTAIN_GAP, z)], .006, metal, 6)                  # wall brackets
            tube(rails, [P(u, CURTAIN_GAP, z), P(u + (-.03 if u < 0 else .03), CURTAIN_GAP, z)], .013, metal, 8)     # finials
        top = z - .015
        steps = int(CURTAIN_W / CURTAIN_PITCH) * 10
        for side in (-1, 1):                                              # drawn to both ends
            seed = _noise(mt.x, mt.y, side)
            def under(pl, u0):                                            # a placement (or box) in the curtain's floor space
                a, b = P(u0, 0, 0), P(u0 - side * CURTAIN_W, CURTAIN_GAP + 2 * CURTAIN_AMP, 0)
                x0, x1, y0, y1 = (pl.x0, pl.x1, pl.y0, pl.y1) if isinstance(pl, L.Box) else L.footprint(pl)
                return x0 < max(a[0], b[0]) and min(a[0], b[0]) < x1 and y0 < max(a[1], b[1]) and min(a[1], b[1]) < y1
            u0 = side * (h - .02)
            sconces = [pl for pl in c.placements if _pivot(pl) == 'wall_mount_center']
            while any(under(pl, u0) for pl in sconces) and abs(u0) > w.width / 2 - .10:   # a wall lamp on the pier:
                u0 -= side * .01                                          # draw the curtain in beside it
            bottom = w.sill - .06                                         # just below the sill, or clear of a bench back
            for pl in c.placements:
                if pl not in sconces and under(pl, u0):
                    bottom = max(bottom, _top(pl) + .03)
            for bx in c.reservations:                                     # a ledge built under the window
                if bx.kind in LEDGES and under(bx, u0):
                    bottom = max(bottom, bx.z1 + .03)
            # soft folds: the phase runs at a pitch wandering +-15 %, each fold its own depth, gathered tight at the rail
            # and fuller at the hem, which dips at the leading edge and curls up towards the wall end
            cols, phase, run = [], 0., 0.
            for i in range(steps + 1):
                t = i / steps
                u = u0 - side * CURTAIN_W * t
                if i:
                    phase += 2 * math.pi * (CURTAIN_W / steps) / (CURTAIN_PITCH * (1 + .3 * (_noise(seed, int(phase / math.pi)) - .5)))
                depth = CURTAIN_AMP * (.75 + .5 * _noise(seed, int(phase / (2 * math.pi)), 7))
                f = math.sin(phase)
                hem = bottom - .025 * math.sin(math.pi * t) ** 2 + .015 * t
                cols.append((P(u, CURTAIN_GAP + depth * .6 * f, top), P(u, CURTAIN_GAP + depth * f, hem)))
            for (a0, a1), (b0, b1) in zip(cols, cols[1:]):                 # UVs in metres of cloth, for the swatch
                da, db = _sub(b0, a0), _sub(b1, a1)
                s0, s1 = run, run + math.sqrt(sum(v * v for v in da))
                cloth.quad(a1, b1, b0, a0, fabric, [(s0 / CURTAIN_TILE, a1[2] / CURTAIN_TILE), (s1 / CURTAIN_TILE, b1[2] / CURTAIN_TILE),
                                                              (s1 / CURTAIN_TILE, b0[2] / CURTAIN_TILE), (s0 / CURTAIN_TILE, a0[2] / CURTAIN_TILE)])
                run = s1


def menu_board(c, part):
    for mt in c.mounts:
        if mt.kind != 'menu-board':
            continue
        P, h, z = _frame(c, mt), mt.length / 2, mt.z
        hb, f = BOARD_H / 2, BOARD_FRAME
        a, b = P(-h, 0, z - hb), P(h, .015, z + hb)
        box(part, a[0], b[0], a[1], b[1], a[2], b[2], 'end-dark')                                        # the board's body
        part.faces.append(([P(-h + f, .016, z - hb + f), P(h - f, .016, z - hb + f), P(h - f, .016, z + hb - f), P(-h + f, .016, z + hb - f)],
                           'menu-board', [(0, 0), (1, 0), (1, 1), (0, 1)]))                              # its face, mapped whole
        for u0, u1, z0, z1 in ((-h, h, z - hb, z - hb + f), (-h, h, z + hb - f, z + hb), (-h, -h + f, z - hb, z + hb), (h - f, h, z - hb, z + hb)):
            a, b = P(u0, 0, z0), P(u1, .03, z1)
            box(part, a[0], b[0], a[1], b[1], a[2], b[2], 'enamel-cream')


def ladle_hooks(c, part):
    for mt in c.mounts:
        if mt.kind != 'ladle':
            continue
        P, z = _frame(c, mt), mt.z
        a, b = P(-.03, 0, z - .07), P(.03, .012, z + .03)
        box(part, a[0], b[0], a[1], b[1], a[2], b[2], 'iron-black')                                     # screwed plate
        tube(part, [P(0, .01, z), P(0, .07, z - .005), P(0, .085, z + .02), P(0, .08, z + .045)], .006, 'iron-black', 6)   # J hook


SHELF_BOARDS = (.10, .70, 1.25, 1.80)                 # board tops above the floor; trunks go on the lowest
SHELF_LOW = (.10, .55)                                 # under a window: low shelves clear of the curtains' hems
SHELF_T, SHELF_POST, SHELF_BAY = .025, .04, 1.00       # board thickness, upright, widest bay between uprights


def _window_zones(c, sy, x0, x1):
    """Spans of a wall (side sy) between x0 and x1 that a window and its drawn curtains take, with the curtains' hem."""
    zones = []
    rails = {mt.id: mt for mt in c.mounts if mt.kind == 'curtain-rail'}
    for w in c.windows:
        if w.side != sy:
            continue
        rail = rails.get(f'curtain-{w.name}')
        h = (rail.length / 2 + .06) if rail else (w.width / 2 + .05)
        a, b = (rail.x if rail else w.x) - h, (rail.x if rail else w.x) + h
        if a < x1 and b > x0:
            zones.append((max(a, x0), min(b, x1), w.sill - .06))
    return sorted(zones)


def shelving(c, part, metal):
    """Open walnut shelving on every 'luggage-shelves' box, against its outer wall: end panels, front uprights at most
    a metre apart, boards with a metal lip along the front; under a window only low shelves, below the curtains."""
    for b in (r for r in c.reservations if r.kind == 'luggage-shelves'):
        sy = 1 if b.y0 + b.y1 > 0 else -1
        wall, front = (b.y1, b.y0) if sy > 0 else (b.y0, b.y1)
        zones = _window_zones(c, sy, b.x0, b.x1)
        cuts = sorted({b.x0, b.x1} | {x for z in zones for x in z[:2]})
        for xa, xb in zip(cuts, cuts[1:]):
            low = next((z for z in zones if z[0] <= xa + 1e-6 and xb <= z[1] + 1e-6), None)
            boards = SHELF_LOW if low else tuple(t for t in SHELF_BOARDS if L.FLOOR_Z + t < b.z1 - .05)
            top = L.FLOOR_Z + boards[-1]
            if low:
                assert top < low[2] - .10, (c.name, b.name)
            for x, s in ((xa, 1), (xb, -1)):                       # end panels, full depth
                box(part, x, x + s * SHELF_T, wall, front, L.FLOOR_Z, min(top + (.12 if not low else .04), b.z1), 'walnut')
            n = max(1, math.ceil((xb - xa - 2 * SHELF_T) / SHELF_BAY))
            for k in range(1, n):                                   # front uprights and their wall cleats
                x = xa + (xb - xa) * k / n
                box(part, x - SHELF_POST / 2, x + SHELF_POST / 2, front, front + sy * SHELF_POST, L.FLOOR_Z, top, 'walnut')
                box(part, x - SHELF_POST / 2, x + SHELF_POST / 2, wall, wall - sy * .03, L.FLOOR_Z, top, 'walnut')
            for t in boards:
                z = L.FLOOR_Z + t
                box(part, xa + SHELF_T, xb - SHELF_T, wall, front, z - SHELF_T, z, 'walnut')
                box(part, xa + SHELF_T, xb - SHELF_T, front, front + sy * .012, z, z + .04, metal)   # lip


LEDGES = {'drinks-ledge', 'galley-counter', 'pantry-counter'}   # reservation kinds curtains hang clear of
# counters modelled in code: cupboard fronts, top, knobs
COUNTERS = {'galley-counter': ('enamel-cream', 'zinc', 'brass-dull'), 'pantry-counter': ('walnut', 'zinc', 'brass')}
COUNTER_TOP, PLINTH, DOOR_W = .04, .08, .50


def counters(c, part):
    """Fitted counters on their reservations: a dark plinth, a run of cupboard doors (each with a knob, the seams
    between them shadowed), and a top with a rounded nosing, its front towards the middle of the room."""
    for b in (r for r in c.reservations if r.kind in COUNTERS):
        front_mat, top_mat, knob = COUNTERS[b.kind]
        sy = _facing(c, b)                                               # the front faces the room's middle
        front, back = (b.y0, b.y1) if sy < 0 else (b.y1, b.y0)
        f = lambda d: front + sy * d                                     # d metres out from the front face
        z0, z1 = L.FLOOR_Z, b.z1
        box(part, b.x0 + .02, b.x1 - .02, back, f(-.075), z0, z0 + PLINTH, 'end-dark')       # recessed plinth
        box(part, b.x0, b.x1, back, f(-.035), z0 + PLINTH, z1 - COUNTER_TOP, front_mat)    # carcass
        n = max(1, round((b.x1 - b.x0) / DOOR_W))
        for k in range(n):
            xa, xb = b.x0 + (b.x1 - b.x0) * k / n + .006, b.x0 + (b.x1 - b.x0) * (k + 1) / n - .006
            box(part, xa, xb, f(-.035), f(-.015), z0 + PLINTH + .01, z1 - COUNTER_TOP - .06, front_mat)   # door
            box(part, xa, xb, f(-.035), f(-.015), z1 - COUNTER_TOP - .05, z1 - COUNTER_TOP - .01, front_mat)  # drawer
            kx = xb - .05 if k % 2 == 0 else xa + .05
            tube(part, [(kx, f(-.015), z1 - COUNTER_TOP - .20), (kx, f(0.), z1 - COUNTER_TOP - .20)], .012, knob, 8)
            tube(part, [((xa + xb) / 2, f(-.015), z1 - COUNTER_TOP - .03), ((xa + xb) / 2, f(0.), z1 - COUNTER_TOP - .03)], .008, knob, 6)
        box(part, b.x0, b.x1, back, f(-.005), z1 - COUNTER_TOP, z1 - .012, top_mat)             # top, lipped front
        box(part, b.x0, b.x1, back, f(0.), z1 - .012, z1, top_mat)


def _facing(c, b):
    """+1 or -1: the y direction a reservation's front faces, towards the middle of its room."""
    r = next(r for r in c.rooms if r.x0 - 1e-6 <= (b.x0 + b.x1) / 2 <= r.x1 + 1e-6 and r.y0 - 1e-6 <= (b.y0 + b.y1) / 2 <= r.y1 + 1e-6)
    return -1 if (b.y0 + b.y1) / 2 > (r.y0 + r.y1) / 2 else 1


def attendant_seats(c, part, cloth, metal):
    """The attendant's folding seat on the wall: a walnut back board with a cushion, a hinged seat (shown down) with
    its cushion, held by two folding brass stays, on a brass hinge rod."""
    for b in (r for r in c.reservations if r.kind == 'attendant-seat'):
        sy = _facing(c, b)
        wall = b.y0 if sy > 0 else b.y1
        f = lambda d: wall + sy * d
        z = L.FLOOR_Z
        box(part, b.x0, b.x1, f(0.), f(.02), z + .50, b.z1, 'walnut')                       # back board
        box(part, b.x0 + .04, b.x1 - .04, f(.02), f(.05), z + .58, b.z1 - .06, cloth)       # back cushion
        box(part, b.x0, b.x1, f(.03), f(b.y1 - b.y0), z + .42, z + .45, 'walnut')            # seat, folded down
        box(part, b.x0 + .02, b.x1 - .02, f(.05), f(b.y1 - b.y0 - .02), z + .45, z + .48, cloth)
        tube(part, [(b.x0, f(.03), z + .435), (b.x1, f(.03), z + .435)], .009, metal, 8)        # hinge rod
        for x in (b.x0 + .03, b.x1 - .03):
            box(part, x - .015, x + .015, f(0.), f(.01), z + .14, z + .26, metal)              # stay plate
            tube(part, [(x, f(.01), z + .20), (x, f(b.y1 - b.y0 - .06), z + .42)], .007, metal, 6)


def handbrakes(c, part, metal):
    """A handbrake on each 'handbrake' box: a cast-iron column on a bolted floor flange, its screw housing and a
    four-spoked wheel on top, turned flat for the guard to wind."""
    for b in (r for r in c.reservations if r.kind == 'handbrake'):
        cx, cy, z = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, L.FLOOR_Z
        rr = min(b.x1 - b.x0, b.y1 - b.y0) / 2 - .012          # the wheel fills the box
        top = b.z1 - .08                                       # the spinner knob reaches the box top
        lathe(part, cx, cy, [(0, z + .035), (.09, z + .035), (.09, z), (.06, z), (.05, z + .06), (.045, z + .55), (.055, z + .58),
                             (.055, z + .64), (.04, z + .67), (.034, top - .08), (.026, top - .06), (0, top - .06)], 'iron-black', 12)
        for k in range(4):                                      # flange bolts
            a = math.pi / 4 + k * math.pi / 2
            lathe(part, cx + .07 * math.cos(a), cy + .07 * math.sin(a), [(0, z + .05), (.012, z + .05), (.012, z + .035)], metal, 6)
        lathe(part, cx, cy, [(0, top + .02), (.03, top + .02), (.03, top - .02), (.016, top - .06), (0, top - .06)], metal, 10)  # hub
        ring = [(cx + rr * math.cos(2 * math.pi * k / 16), cy + rr * math.sin(2 * math.pi * k / 16), top) for k in range(17)]
        tube(part, ring, .011, metal, 6, caps=False)
        for k in range(4):
            a = k * math.pi / 2
            tube(part, [(cx + .03 * math.cos(a), cy + .03 * math.sin(a), top), (cx + rr * math.cos(a), cy + rr * math.sin(a), top)], .007, metal, 6)
        a = math.pi / 4                                         # the spinner knob
        kx, ky = cx + rr * math.cos(a), cy + rr * math.sin(a)
        tube(part, [(kx, ky, top), (kx, ky, top + .07)], .012, 'end-dark', 8)


def benches(c, part, cloth, metal):
    """The guard's locker bench on each 'bench' box: a panelled walnut chest along the wall, its lid the seat, with a
    cushion, a brass hasp and a kick recess at the foot."""
    for b in (r for r in c.reservations if r.kind == 'bench'):
        sy = _facing(c, b)
        front, back = (b.y0, b.y1) if sy < 0 else (b.y1, b.y0)
        f = lambda d: front + sy * d
        z, top = L.FLOOR_Z, b.z1 - .06                          # the cushion takes the last 6 cm
        box(part, b.x0, b.x1, back, f(-.06), z, z + .07, 'end-dark')                     # kick recess
        box(part, b.x0, b.x1, back, f(-.02), z + .07, top - .03, 'walnut')                # chest
        n = max(1, round((b.x1 - b.x0) / .55))
        for k in range(n):                                      # raised panels on the front
            xa, xb = b.x0 + (b.x1 - b.x0) * k / n + .04, b.x0 + (b.x1 - b.x0) * (k + 1) / n - .04
            box(part, xa, xb, f(-.02), f(-.005), z + .12, top - .08, 'walnut')
            box(part, (xa + xb) / 2 - .015, (xa + xb) / 2 + .015, f(-.005), f(0.), top - .07, top - .035, metal)   # hasp
        box(part, b.x0, b.x1, back, f(0.), top - .03, top, 'walnut')                       # the lid
        box(part, b.x0 + .02, b.x1 - .02, back, f(-.03), top, b.z1, cloth)       # cushion


def desks(c, part, metal):
    """The guard's writing desk on each 'desk' box, against the outer wall: nothing rises above its top, so the windows
    over it stay clear. A walnut top, a pedestal of open pigeon-holes (four rows of three) facing the guard at its
    low-x end, a kneehole with a shallow drawer and a modesty board, and a side panel at the other end."""
    for b in (r for r in c.reservations if r.kind == 'desk'):
        sy = _facing(c, b)
        front, back = (b.y0, b.y1) if sy < 0 else (b.y1, b.y0)
        f = lambda d: front + sy * d
        z, top = L.FLOOR_Z, b.z1
        ped = min(.45, (b.x1 - b.x0) * .5)
        px0, px1 = b.x0, b.x0 + ped                              # the pigeon-hole pedestal
        box(part, b.x0, b.x1, back, f(0.), top - .03, top, 'walnut')                          # top
        box(part, px0, px1, back, back + sy * .02, z, top - .03, 'walnut')                    # pedestal back
        for x in (px0, px1 - .02):
            box(part, x, x + .02, back, f(0.), z, top - .03, 'walnut')                        # pedestal sides
        box(part, px0, px1, back, f(0.), z, z + .06, 'end-dark')                              # plinth
        rows, cols = 4, 3
        h = (top - .03 - (z + .06)) / rows
        for k in range(rows + 1):                                                               # shelves
            zz = z + .06 + k * h
            box(part, px0 + .02, px1 - .02, back + sy * .02, f(0.), zz - .008, zz + .008, 'walnut')
        for k in range(1, cols):                                                                # dividers
            x = px0 + .02 + (ped - .04) * k / cols
            box(part, x - .006, x + .006, back + sy * .02, f(-.01), z + .06, top - .03, 'walnut')
        box(part, b.x1 - .03, b.x1, back, f(0.), z, top - .03, 'walnut')                       # far side panel
        box(part, px1, b.x1 - .03, back, back + sy * .02, top - .30, top - .03, 'walnut')      # modesty board
        box(part, px1, b.x1 - .03, f(-.02), f(0.), top - .13, top - .03, 'walnut')             # kneehole drawer
        mx = (px1 + b.x1 - .03) / 2
        box(part, mx - .05, mx + .05, f(-.005), f(0.), top - .09, top - .07, metal)           # drawer pull


def drinks_ledges(c, part, metal):
    """The restaurant's standing ledge under a window: a walnut top with a rounded nosing and a brass gallery rail
    (glasses don't slide off on a curve), on cast brackets, and a brass foot rail low along the wall."""
    for b in (r for r in c.reservations if r.kind == 'drinks-ledge'):
        sy = 1 if b.y0 + b.y1 > 0 else -1
        wall, front = (b.y1, b.y0) if sy > 0 else (b.y0, b.y1)
        sill = next((w.sill for w in c.windows if w.side == sy and abs(w.x - (b.x0 + b.x1) / 2) < w.width / 2
                     and w.sill < b.z1), None)
        box(part, b.x0, b.x1, wall, front, b.z1 - .04, b.z1, 'walnut')
        tube(part, [(b.x0, front + sy * .02, b.z1 - .02), (b.x1, front + sy * .02, b.z1 - .02)], .02, 'walnut', 8)   # nosing
        tube(part, [(b.x0 + .03, front + sy * .03, b.z1 + .035), (b.x1 - .03, front + sy * .03, b.z1 + .035)], .006, metal, 6)
        n = max(2, math.ceil((b.x1 - b.x0) / .75) + 1)
        for k in range(n):
            x = b.x0 + .06 + (b.x1 - b.x0 - .12) * k / (n - 1)
            tube(part, [(x, front + sy * .03, b.z1), (x, front + sy * .03, b.z1 + .035)], .005, metal, 6)   # gallery posts
            if sill is not None:                                   # over glass: brackets stand on the window's sill
                box(part, x - .02, x + .02, wall - sy * .01, wall - sy * .09, sill, sill + .012, metal)    # foot plate
                tube(part, [(x, wall - sy * .05, sill + .012), (x, wall - sy * .05, b.z1 - .04)], .009, metal, 6)
                tube(part, [(x, wall - sy * .06, sill + .06), (x, front + sy * .04, b.z1 - .045)], .008, metal, 6)
            else:
                box(part, x - .012, x + .012, wall, wall - sy * .03, b.z1 - .30, b.z1 - .04, metal)       # bracket plate
                tube(part, [(x, wall - sy * .02, b.z1 - .28), (x, front + sy * .04, b.z1 - .045)], .01, metal, 6)
            tube(part, [(x, wall, L.FLOOR_Z + .18), (x, front + sy * .05, L.FLOOR_Z + .18)], .008, metal, 6)    # foot-rail arm
        tube(part, [(b.x0 + .02, front + sy * .05, L.FLOOR_Z + .18), (b.x1 - .02, front + sy * .05, L.FLOOR_Z + .18)], .016, metal, 10)


def fittings(c):
    """Every fitting Part of a coach (empty for coaches not yet fitted)."""
    if c.name not in COACHES:
        return []
    parts = {k: Part(n, closed=cl, lods=lo) for k, n, cl, lo in (
        ('rack', 'Fittings_Racks', False, (0, 1)), ('net', 'Fittings_RackNets', False, (0,)),
        ('ceiling-lamp', 'Fittings_Lamps', False, (0, 1)), ('cord', 'Fittings_LampCords', False, (0,)),
        ('curtain-rail', 'Fittings_CurtainRails', False, (0, 1)), ('curtain', 'Fittings_Curtains', False, (0, 1)),
        ('menu-board', 'Fittings_MenuBoard', True, (0, 1)), ('ladle', 'Fittings_LadleHook', False, (0, 1)),
        ('shelves', 'Fittings_Shelves', True, (0,)), ('counters', 'Fittings_Counters', True, (0,)), ('ledge', 'Fittings_DrinksLedge', False, (0,)))}          # shelves: LOD0 only (first class sits at its LOD1 budget)
    if c.name == 'locomotive':                        # the cab lamp alone: small, LOD0 only
        parts['ceiling-lamp'].lods = (0,)
    st = STYLES[c.name]
    racks(c, parts['rack'], parts['net'], st['metal'], st['net'])
    lamps(c, parts['ceiling-lamp'], parts['cord'])
    parts['curtain'].smooth = 180.                    # soft folds, no hard creases
    curtains(c, parts['curtain-rail'], parts['curtain'], st['metal'], st['cloth'])
    menu_board(c, parts['menu-board'])
    ladle_hooks(c, parts['ladle'])
    shelving(c, parts['shelves'], st['metal'])
    drinks_ledges(c, parts['ledge'], st['metal'])
    counters(c, parts['counters'])
    attendant_seats(c, parts['counters'], st['cloth'], st['metal'])
    handbrakes(c, parts['counters'], st['metal'])
    benches(c, parts['counters'], st['cloth'], st['metal'])
    desks(c, parts['counters'], st['metal'])
    return [p for p in parts.values() if p.faces]


KINDS = {'rack': ('Fittings_Racks', 'Fittings_RackNets'), 'ceiling-lamp': ('Fittings_Lamps', 'Fittings_LampCords'),
         'curtain-rail': ('Fittings_CurtainRails', 'Fittings_Curtains'), 'menu-board': ('Fittings_MenuBoard',),
         'ladle': ('Fittings_LadleHook',)}
