"""Measured plan of the Belmonte train's two coaches: the shared envelope, each coach's rooms, partitions, doors,
windows, reservations, furniture placements and seats. Plain Python (no Blender), so tests and the plan drawing
read the same numbers the Blender build uses.

Coach frame, metres: x along the coach (end A at -X, end B at +X), y across (+Y is the compartment side in first
class and the bar/galley side in the restaurant), z up, z = 0 on the top of the rail, origin at the coach's centre.
Unreal takes it through `atelier.conventions.to_unreal` only (docs: platform/conventions/units.md).

Furniture placements give the asset's origin (floor footprint centre; table lamps: base contact centre; wall
sconces: wall mount point) and a yaw in degrees about +Z. At yaw 0 an asset's front faces -Y and its width runs
along X, as in the shared contract (assets/vehicles/belmonte-train/planning/furniture-dimensions.json); yaw 90
turns its front to +X and its width to Y.
"""
from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path

import numpy as np

CONTRACT = Path(__file__).resolve().parents[2] / 'assets' / 'vehicles' / 'belmonte-train' / 'planning' / 'furniture-dimensions.json'

# --- the shared envelope ------------------------------------------------------------------------------------------
LENGTH_OVER_BUFFERS = 24.0
BUFFER_X = LENGTH_OVER_BUFFERS / 2      # buffer heads and gangway faces
BODY_X = 11.60                          # outer face of each end wall: 23.20 m body
WIDTH = 3.60                            # wider than a real coach (3.10): roomy corridors for a luxury game interior
HALF = WIDTH / 2
WALL = 0.075                            # side and end walls, lining included
IN = HALF - WALL                        # 1.725: inner face of the side walls (3.45 m clear)
IN_X = BODY_X - WALL                    # 11.525: inner face of the end walls
SKIRT_Z = 1.00                          # bottom edge of the body sides
FLOOR_Z = 1.25                          # top of the floor (assumed platform-independent; steps below the doors)
DECK = 0.15                             # floor structure under FLOOR_Z
BELT_Z = 1.85                           # midnight blue below, ivory above (under the restaurant's low bay sills)
CANT_Z = 3.45                           # top of the side walls, where the roof starts
ROOF_TOP = 4.18                         # roof skin at the centre line
VENT_TOP = 4.30                         # the ventilator caps: the 4.30 m height above rail
ROOF_SKIN = 0.05
CEIL_SPRING, CEIL_APEX = 3.30, 3.55     # ceiling meets the walls at 2.05 m above the floor, 2.30 m at the centre
CLEAR = CEIL_APEX - FLOOR_Z

SILL = FLOOR_Z + 0.80                   # windows: above restaurant tables (0.75) and cabin tables (0.62)
HEAD = FLOOR_Z + 1.72
WIN_RADIUS = 0.10
WIN_W, SMALL_W, WC_W = 1.40, 0.80, 0.50
PANO_SILL = FLOOR_Z + 0.65              # restaurant panoramic bays (r03 direction): low sill, head just under the ceiling
PANO_HEAD = FLOOR_Z + 1.97
PIER = 0.30                             # structural piers between the bays, behind each pair of banquette backs
PART = 0.05                             # interior partitions
VEST = 1.60                             # clear length of each end vestibule
SPAN_X = IN_X - VEST - PART             # 9.875: the coach's own plan between the vestibule bulkheads
DOOR_H = 1.95                           # interior doorways and the exterior doors
EXT_DOOR_W = 0.75
EXT_DOOR_X = IN_X - VEST / 2            # exterior doors are centred on the vestibules
GANGWAY_W, GANGWAY_H = 0.80, 2.00
GANGWAY_OVERLAP = .15                   # gangway floor, walls and volume run this far past the buffer line (curves)
CORRIDOR = 1.20                         # first-class side corridor; the restaurant's service corridor matches it
CABIN_W = 2.20                          # first-class cabin, partition to outer wall
CORR_Y = -IN + CORRIDOR                 # -0.575: corridor face of the longitudinal partitions
ROOM_Y = CORR_Y + PART                  # -0.525: room face of the longitudinal partitions

BOGIE_X, WHEELBASE, WHEEL_R = 8.50, 2.50, 0.46
GAUGE = 1.435                           # assumption: standard gauge, to be agreed with the map owner
BUFFER_Y, BUFFER_Z = 0.875, 1.065

CAIRO = dict(height=1.48, radius=0.22, source='Cairo: assets/characters/cairo/character.toml height_cm 148, capsule 22/74 cm (CairoCharacter.cpp)')
HUMAN = dict(height=1.75, radius=0.28, source='provisional 1.75 m adult gauge (shoulders 0.48 m + 4 cm margin)')


@dataclass
class Body:
    """One vehicle's carriage body in its own frame. x_a/x_b are the outer faces of the end walls (end A at -X), the
    buffer heads stand at buffer_a/buffer_b, and each end is a `gangway` (bellows and end door) or a `balcony` (an open
    platform from the end wall to the headstock, closed by a railing). The 24 m coaches use the defaults."""
    x_a: float = -BODY_X
    x_b: float = BODY_X
    buffer_a: float = -BUFFER_X
    buffer_b: float = BUFFER_X
    end_a: str = 'gangway'
    end_b: str = 'gangway'
    bogies: tuple = (-BOGIE_X, BOGIE_X)
    wheelbase: float = WHEELBASE
    exterior_doors: tuple = (('a', -EXT_DOOR_X), ('b', EXT_DOOR_X))   # (label, x of the door centre), both sides
    cupola: tuple = None           # (x0, x1) of a raised lookout on the roof
    crest_x: float = 0.
    livery: str = 'luxury'         # luxury, or worn: faded, rusty paint and peeling interiors (second class)
    cargo_doors: tuple = ()        # x centres of pairs of wide double sliding luggage doors, both sides (baggage van)
    kind: str = 'coach'            # coach, or tender (its own build: water tank, coal space, footplate, rigid axles)
    walk: tuple = None             # (x0, x1) standing range when it is not the space inside the end walls (the tender's footplate)
    walk_y: float = IN             # half-width of that standing range

    @property
    def length(self):
        return self.buffer_b - self.buffer_a

    @property
    def in_a(self):
        return self.x_a + WALL

    @property
    def in_b(self):
        return self.x_b - WALL

    def face(self, s):
        return self.x_b if s > 0 else self.x_a

    def inner(self, s):
        return self.in_b if s > 0 else self.in_a

    def buffer(self, s):
        return self.buffer_b if s > 0 else self.buffer_a

    def end(self, s):
        return self.end_b if s > 0 else self.end_a

    def headstock(self, s):
        """Where the underframe ends: at the end wall, or at the outer edge of a balcony."""
        return self.face(s) if self.end(s) != 'balcony' else self.buffer(s) - s * (BUFFER_X - BODY_X)

    def walk_limits(self):
        """x range a passenger can stand in: inside the end walls, out to the railing on a balcony."""
        if self.walk:
            return tuple(self.walk)
        lo = self.in_a if self.end_a != 'balcony' else self.headstock(-1) + .06
        hi = self.in_b if self.end_b != 'balcony' else self.headstock(1) - .06
        return lo, hi


def coupling(body=None):
    """The interface every vehicle of this train shares, so any two couple: buffer heads and draw hook at each end,
    and a gangway face at each gangway end. Coupled vehicles touch buffer to buffer: the next one's origin sits at
    this one's buffer plus its own half-length."""
    body = body or Body()
    ends = {}
    for end, sx in (('a', -1), ('b', 1)):
        e = dict(buffer_heads=[[body.buffer(sx), sy * BUFFER_Y, BUFFER_Z] for sy in (1, -1)],
                 draw_hook=[body.buffer(sx), 0., BUFFER_Z], floor_z=FLOOR_Z, facing=[sx, 0, 0], kind=body.end(sx))
        if body.end(sx) == 'gangway':
            e.update(gangway_face_centre=[body.buffer(sx), 0., FLOOR_Z + GANGWAY_H / 2], gangway_clear_m=[GANGWAY_W, GANGWAY_H])
        ends[end] = e
    return dict(pitch_m=body.length, length_over_buffers_m=body.length, ends=ends, buffer_head_diameter_m=.40,
                note='same buffers, hook, floor and gangway on every vehicle: a step-free walk from coach to coach')


def ceiling_z(y):
    """Underside of the ceiling at y: a flat ellipse from CEIL_SPRING at the walls to CEIL_APEX at the centre."""
    t = min(1., abs(y) / IN)
    return CEIL_SPRING + (CEIL_APEX - CEIL_SPRING) * math.sqrt(max(0., 1 - t * t))


def roof_z(y, inset=0.):
    """Outer roof skin at y (an ellipse on the cant rail), optionally `inset` inward."""
    a, b = HALF - inset, ROOF_TOP - CANT_Z - inset
    t = min(1., abs(y) / a)
    return CANT_Z + b * math.sqrt(max(0., 1 - t * t))


# --- plan records -------------------------------------------------------------------------------------------------
@dataclass
class Room:
    name: str
    kind: str              # vestibule, corridor, cabin, wc, luggage, pantry, lobby, salon, bar, galley
    x0: float
    x1: float
    y0: float
    y1: float
    floor: str             # carpet-burgundy, carpet-emerald, tile, parquet


@dataclass
class Opening:
    name: str
    a0: float              # along the wall
    a1: float
    z0: float = FLOOR_Z
    z1: float = FLOOR_Z + DOOR_H


@dataclass
class Wall:
    """An interior partition from the floor to the ceiling. axis 'x' runs along the coach (a = x, c = y);
    axis 'y' runs across it (a = y, c = x)."""
    name: str
    axis: str
    a0: float
    a1: float
    c0: float
    c1: float
    openings: list = field(default_factory=list)


@dataclass
class Window:
    name: str
    side: int              # +1 or -1: which side wall
    x: float
    width: float
    sill: float = SILL
    head: float = HEAD
    kind: str = 'clear'    # clear or frosted


@dataclass
class Door:
    """A door leaf in an opening. sliding: the leaf runs on the `face` side of the wall towards `slide`
    (+1/-1 along the wall); hinged: hinge at the `slide` end, swinging into the `face` side."""
    name: str
    wall: str
    opening: str
    kind: str              # sliding, hinged, double
    face: int
    slide: int
    glazed: bool
    width: float           # leaf width (overlaps the opening by 0.025 a side when sliding)


@dataclass
class Box:
    name: str
    kind: str
    x0: float
    x1: float
    y0: float
    y1: float
    z0: float
    z1: float
    note: str = ''


@dataclass
class Placement:
    id: str
    asset: str
    room: str
    x: float
    y: float
    z: float
    yaw: float
    through: str = ''      # a wall it passes through into the next room (the canteen counter under its hatch)


@dataclass
class Seat:
    id: str
    furniture: str
    x: float
    y: float
    z: float
    yaw: float             # the way the seated passenger faces (0 = -Y, 90 = +X)


@dataclass
class Mount:
    id: str
    kind: str              # curtain-rail, rack, sconce
    room: str
    x: float
    y: float
    z: float
    yaw: float
    length: float = 0.


@dataclass
class Coach:
    name: str
    title: str
    rooms: list = field(default_factory=list)
    walls: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    doors: list = field(default_factory=list)
    reservations: list = field(default_factory=list)
    placements: list = field(default_factory=list)
    seats: list = field(default_factory=list)
    mounts: list = field(default_factory=list)
    body: Body = field(default_factory=Body)
    goals: dict = field(default_factory=dict)     # extra walk-check points {room: (x, y)}

    def room(self, name):
        return next(r for r in self.rooms if r.name == name)

    def wall(self, name):
        return next(w for w in self.walls if w.name == name)


def contract():
    return json.loads(CONTRACT.read_text())


def seat_height(asset):
    """The contract's seat height (the cushion's top) above the floor."""
    return next(a for a in contract()['assets'] if a['id'] == asset)['seat_height_m']


def asset_dims(asset):
    spec = next(a for a in contract()['assets'] if a['id'] == asset)
    d = spec['dimensions_m']
    return d['width'], d['depth'], d['height']


def footprint(p):
    """World-space (x0, x1, y0, y1) of a floor-standing placement (yaw is a multiple of 90)."""
    w, d, _ = asset_dims(p.asset)
    if round(p.yaw / 90) % 2:
        w, d = d, w
    return p.x - w / 2, p.x + w / 2, p.y - d / 2, p.y + d / 2


# --- shared parts -------------------------------------------------------------------------------------------------
def _shared(c, vestibules=True):
    """End walls (a gangway or a balcony door in each), the exterior doors and, on the 24 m coaches, the vestibules."""
    b = c.body
    if vestibules:
        c.rooms += [Room('vestibule-a', 'vestibule', b.in_a, b.in_a + VEST, -IN, IN, 'tile'),
                    Room('vestibule-b', 'vestibule', b.in_b - VEST, b.in_b, -IN, IN, 'tile')]
    for end, sx in (('a', -1), ('b', 1)):
        c0, c1 = sorted((b.face(sx), b.inner(sx)))
        if b.end(sx) == 'gangway':
            c.walls.append(Wall(f'end-{end}', 'y', -IN, IN, c0, c1, [Opening(f'gangway-{end}', -GANGWAY_W / 2, GANGWAY_W / 2, FLOOR_Z, FLOOR_Z + GANGWAY_H)]))
            c.doors.append(Door(f'gangway-door-{end}', f'end-{end}', f'gangway-{end}', 'sliding', -sx, sx, True, GANGWAY_W + .05))
        elif b.end(sx) == 'closed':
            c.walls.append(Wall(f'end-{end}', 'y', -IN, IN, c0, c1))
        else:
            c.walls.append(Wall(f'end-{end}', 'y', -IN, IN, c0, c1, [Opening(f'balcony-door-{end}', -.45, .45)]))
            # hinged on its -Y jamb, opening out onto the balcony
            c.doors.append(Door(f'balcony-door-{end}', f'end-{end}', f'balcony-door-{end}', 'hinged', sx, -1, True, .90))
    for k, x in enumerate(b.cargo_doors):
        for side, sy in (('l', 1), ('r', -1)):
            # two leaves on the outer face, sliding apart along the side
            c.doors.append(Door(f'cargo-door-{k + 1}{side}', f'side-{side}', f'cargo-{k + 1}{side}', 'cargo', sy, 0, False, CARGO_W / 2 + .04))
    for label, x in b.exterior_doors:
        for side, sy in (('l', 1), ('r', -1)):
            # the exterior doors open inward, hinged on the jamb nearer the coach end
            c.doors.append(Door(f'exterior-door-{label}{side}', f'side-{side}', f'exterior-{label}{side}', 'hinged', -sy, 1 if x >= 0 else -1,
                                False, EXT_DOOR_W + .03))


def exterior_openings(c=None):
    """The exterior door openings in the side walls: (name, side, x0, x1, z0, z1)."""
    b = c.body if c is not None else Body()
    out = []
    for label, x in b.exterior_doors:
        for side, sy in (('l', 1), ('r', -1)):
            out.append((f'exterior-{label}{side}', sy, x - EXT_DOOR_W / 2, x + EXT_DOOR_W / 2, FLOOR_Z, FLOOR_Z + DOOR_H))
    for k, x in enumerate(b.cargo_doors):
        for side, sy in (('l', 1), ('r', -1)):
            out.append((f'cargo-{k + 1}{side}', sy, x - CARGO_W / 2, x + CARGO_W / 2, FLOOR_Z, FLOOR_Z + DOOR_H + .05))
    return out


def _bulkheads(c, opening_a, opening_b, kind='sliding', glazed=True):
    """The two vestibule bulkheads, each with one doorway (a0, a1) across the coach."""
    for end, sx, (a0, a1) in (('a', -1, opening_a), ('b', 1, opening_b)):
        x_in = sx * SPAN_X
        c0, c1 = sorted((x_in, x_in + sx * PART))
        c.walls.append(Wall(f'bulkhead-{end}', 'y', -IN, IN, c0, c1, [Opening(f'bulkhead-{end}', a0, a1)]))
        c.doors.append(Door(f'bulkhead-door-{end}', f'bulkhead-{end}', f'bulkhead-{end}', kind, sx, +1, glazed,
                            a1 - a0 + .05 if kind == 'sliding' else (a1 - a0) / 2))


def _curtains(c, rooms_for):
    for w in c.windows:
        if w.kind != 'clear':
            continue
        room = rooms_for(w)
        y = w.side * (IN - .02)
        c.mounts.append(Mount(f'curtain-{w.name}', 'curtain-rail', room, w.x, y, min(w.head + .06, CEIL_SPRING - .02), 0 if w.side > 0 else 180,
                              w.width + (PIER if w.head >= PANO_HEAD else .50)))


def _room_at(c, x, y):
    for r in c.rooms:
        if r.x0 - 1e-6 <= x <= r.x1 + 1e-6 and r.y0 - 1e-6 <= y <= r.y1 + 1e-6:
            return r.name
    return '?'


# --- first class: four private seated cabins on a side corridor --------------------------------------------------
FC_BAYS = [('wc-a', 'wc', 1.30), ('luggage', 'luggage', 2.40), ('cabin-1', 'cabin', 3.00), ('cabin-2', 'cabin', 3.00),
           ('cabin-3', 'cabin', 3.00), ('cabin-4', 'cabin', 3.00), ('pantry', 'pantry', 2.40), ('wc-b', 'wc', 1.30)]
FC_DOOR = {'cabin': .70, 'wc': .65, 'luggage': .80, 'pantry': .70}
FC_FLOOR = {'cabin': 'carpet-emerald', 'wc': 'tile', 'luggage': 'parquet', 'pantry': 'parquet'}


def first_class():
    c = Coach('first-class', 'First-class coach — private seated compartments')
    _shared(c)
    corridor_door = (-IN + CORRIDOR / 2 - .45, -IN + CORRIDOR / 2 + .45)   # 0.90 m doorway centred on the corridor
    _bulkheads(c, corridor_door, corridor_door)
    c.rooms.append(Room('corridor', 'corridor', -SPAN_X, SPAN_X, -IN, CORR_Y, 'carpet-emerald'))
    longitudinal = Wall('corridor-partition', 'x', -SPAN_X, SPAN_X, CORR_Y, ROOM_Y)
    x = -SPAN_X
    for i, (name, kind, length) in enumerate(FC_BAYS):
        x0, x1 = x, x + length
        xc = (x0 + x1) / 2
        c.rooms.append(Room(name, kind, x0, x1, ROOM_Y, IN, FC_FLOOR[kind]))
        w = FC_DOOR[kind]
        longitudinal.openings.append(Opening(f'door-{name}', xc - w / 2, xc + w / 2))
        # sliding leaves run on the corridor side, away from the cabin's centre line towards the nearer coach end
        c.doors.append(Door(f'door-{name}', 'corridor-partition', f'door-{name}', 'sliding', -1, -1 if xc < 0 else 1,
                            kind == 'cabin', w + .05))
        if i < len(FC_BAYS) - 1:
            c.walls.append(Wall(f'partition-{name}', 'y', ROOM_Y, IN, x1, x1 + PART))
        x = x1 + PART
        # windows: one wide window per cabin, smaller ones for the service rooms; the corridor side mirrors them
        if kind == 'cabin':
            c.windows += [Window(f'{name}-l', 1, xc, WIN_W), Window(f'{name}-r', -1, xc, WIN_W)]
        elif kind == 'wc':
            c.windows += [Window(f'{name}-l', 1, xc, WC_W, FLOOR_Z + 1.10, HEAD, 'frosted'), Window(f'{name}-r', -1, xc, SMALL_W)]
        else:
            c.windows += [Window(f'{name}-l', 1, xc, SMALL_W), Window(f'{name}-r', -1, xc, SMALL_W)]
        if kind == 'cabin':
            _cabin(c, name, x0, x1)
        elif kind == 'wc':
            xc = (x0 + x1) / 2
            c.reservations += [Box(f'{name}-toilet', 'wc-toilet', xc - .22, xc + .22, IN - .70, IN - .05, FLOOR_Z, FLOOR_Z + .45, 'toilet against the outer wall'),
                               Box(f'{name}-basin', 'wc-basin', x0 + .03, x0 + .43, .25, .70, FLOOR_Z + .75, FLOOR_Z + .90, 'wall-hung basin')]
        elif kind == 'luggage':
            c.reservations.append(Box(f'{name}-shelves', 'luggage-shelves', x0 + .05, x1 - .05, IN - .55, IN - .02, FLOOR_Z, FLOOR_Z + 1.90,
                                      'open luggage shelving along the outer wall'))
        elif kind == 'pantry':
            c.reservations += [Box(f'{name}-counter', 'pantry-counter', x0 + .05, x1 - .05, IN - .62, IN - .02, FLOOR_Z, FLOOR_Z + .92,
                                   'attendant pantry: coffee counter, cupboards'),
                               Box(f'{name}-seat', 'attendant-seat', x0 + .10, x0 + .55, ROOM_Y + .05, ROOM_Y + .50, FLOOR_Z, FLOOR_Z + .90,
                                   'folding attendant seat')]
    assert abs(x - PART - SPAN_X) < 1e-9, 'first-class bays must fill the span'
    c.walls.append(longitudinal)
    _curtains(c, lambda w: _room_at(c, w.x, w.side * (IN - .1)))
    return c


SEAT_FROM_BACK = .14        # a seated marker (the hip) stands this far in front of the backrest's face, 10 cm above the
                            # seat: the restaurant banquettes' 0.138 (the second-class benches have 0.114)
SOFA_BACK_FACE = {'plain': .091, 'pillow': -.029}   # that face on the fitted sofa, from its centre towards its back; on
                            # its own -x half a throw pillow leans on the back, and the pillow is the backrest there


def local_to_coach(p, u, v):
    """A point (u, v) in a placement's own frame (yaw 0 faces -v) to coach (x, y)."""
    a = math.radians(p.yaw)
    return p.x + u * math.cos(a) - v * math.sin(a), p.y + u * math.sin(a) + v * math.cos(a)


def _cabin(c, name, x0, x1):
    xc, yc = (x0 + x1) / 2, (ROOM_Y + IN) / 2
    sw, sd, _ = asset_dims('first-class-sofa')
    tw, td, _ = asset_dims('first-class-table')
    for end, sx, yaw in (('a', -1, 90), ('b', 1, -90)):
        x = (x0 + .01 + sd / 2) if sx < 0 else (x1 - .01 - sd / 2)
        sid = f'{name}-sofa-{end}'
        sofa = Placement(sid, 'first-class-sofa', name, x, yc, FLOOR_Z, yaw)
        c.placements.append(sofa)
        for k, dy in enumerate((-.46, .46)):           # on the cushion, SEAT_FROM_BACK in front of the back (or pillow)
            u = dy * round(math.sin(math.radians(yaw)))                 # the sofa's own x for this place
            sx_, sy_ = local_to_coach(sofa, u, SOFA_BACK_FACE['pillow' if u < 0 else 'plain'] - SEAT_FROM_BACK)
            c.seats.append(Seat(f'{sid}-seat-{k + 1}', sid, round(sx_, 4), round(sy_, 4), FLOOR_Z + seat_height('first-class-sofa'), yaw))
        wall_x = x0 + .02 if sx < 0 else x1 - .02
        for k, dy in enumerate((-.60, .60)):
            c.placements.append(Placement(f'{name}-sconce-{end}{k + 1}', 'wall-sconce', name, wall_x, yc + dy, FLOOR_Z + 1.62, yaw))
        c.mounts.append(Mount(f'{name}-rack-{end}', 'rack', name, wall_x, yc, FLOOR_Z + 1.85, yaw, 1.80))
    ty = IN - .02 - td / 2
    c.placements.append(Placement(f'{name}-table', 'first-class-table', name, xc, ty, FLOOR_Z, 0))
    c.placements.append(Placement(f'{name}-lamp', 'table-lamp', name, xc, ty + .06, FLOOR_Z + .62, 0))


# --- restaurant: five dining bays, bar and galley at end B -------------------------------------------------------
LOBBY = 1.45
GROUPS = 4
GROUP = .73 + .10 + .85 + .10 + .73        # banquette, knee gap, table, knee gap, banquette: 2.51 m
PITCH = GROUP + .02                         # banquettes back to back with 2 cm between them
BAR_COUNTER_X = 4.30                        # front of the bar counter
COUNTER, STAFF, BACKBAR = .55, .80, .40


GALLEY_RANGE = 1.00                         # the range's slot at the end of the galley's outer counter


def restaurant():
    c = Coach('restaurant', 'Dining car')
    _shared(c)
    lobby_x1 = -SPAN_X + LOBBY
    salon_x0 = lobby_x1 + PART
    _bulkheads(c, (-.55, .25), (-IN + CORRIDOR / 2 - .45, -IN + CORRIDOR / 2 + .45))
    counter_x1 = BAR_COUNTER_X + COUNTER
    backbar_x0 = counter_x1 + STAFF
    galley_x0 = backbar_x0 + BACKBAR + PART
    c.rooms += [Room('lobby', 'lobby', -SPAN_X, lobby_x1, -IN, .40, 'tile'),
                Room('wc', 'wc', -SPAN_X, lobby_x1, .45, IN, 'tile'),
                Room('salon', 'salon', salon_x0, BAR_COUNTER_X, -IN, IN, 'carpet-burgundy'),
                Room('bar', 'bar', BAR_COUNTER_X, galley_x0 - PART, ROOM_Y, IN, 'parquet'),
                Room('service-corridor', 'corridor', counter_x1, SPAN_X, -IN, CORR_Y, 'carpet-burgundy'),
                Room('galley', 'galley', galley_x0, SPAN_X, ROOM_Y, IN, 'tile')]
    c.walls += [Wall('wc-wall', 'x', -SPAN_X, lobby_x1, .40, .45, [Opening('door-wc', lobby_x1 - .80, lobby_x1 - .15)]),
                Wall('salon-partition', 'y', -IN, IN, lobby_x1, salon_x0, [Opening('salon-doors', -.50, .40)]),
                Wall('service-partition', 'x', counter_x1, SPAN_X, CORR_Y, ROOM_Y, [Opening('door-galley-service', 8.65, 9.35)]),
                Wall('galley-partition', 'y', ROOM_Y, IN, galley_x0 - PART, galley_x0, [Opening('door-galley-bar', .70, 1.40)])]
    c.doors += [Door('door-wc', 'wc-wall', 'door-wc', 'sliding', -1, -1, False, .70),
                Door('salon-doors', 'salon-partition', 'salon-doors', 'double', +1, 0, True, .45),
                Door('door-galley-service', 'service-partition', 'door-galley-service', 'sliding', -1, -1, False, .75),
                Door('door-galley-bar', 'galley-partition', 'door-galley-bar', 'sliding', +1, -1, False, .75)]
    bw, bd, _ = asset_dims('restaurant-banquette')
    tw, td, _ = asset_dims('restaurant-table')
    gap = .035                                # furniture off the panelling, clear of the bay frames
    tables = []
    for k in range(GROUPS):
        s = salon_x0 + .03 + k * PITCH
        tx = s + bd + .10 + td / 2
        tables.append(tx)
        for side, sy in (('l', 1), ('r', -1)):
            by = sy * (IN - gap - bw / 2)
            ty = sy * (IN - gap - tw / 2)
            t = f'table-{k + 1}{side}'
            c.placements.append(Placement(t, 'restaurant-table', 'salon', tx, ty, FLOOR_Z, 90))
            c.placements.append(Placement(f'{t}-lamp', 'table-lamp', 'salon', tx, ty + sy * .22, FLOOR_Z + .75, 0))
            for end, bx, yaw in (('a', s + bd / 2, 90), ('b', s + GROUP - bd / 2, -90)):
                b = f'banquette-{k + 1}{side}{end}'
                c.placements.append(Placement(b, 'restaurant-banquette', 'salon', bx, by, FLOOR_Z, yaw))
                c.seats.append(Seat(f'{b}-seat', b, bx + (.05 if yaw > 0 else -.05), by, FLOOR_Z + .46, yaw))
    # one panoramic bay per dining bay, centred on its tables; the piers stand where the banquette backs meet
    bays = [(x, PITCH - PIER) for x in tables]
    bar0 = tables[-1] + PITCH / 2 + PIER / 2
    bar1 = BAR_COUNTER_X - .10
    bays.append(((bar0 + bar1) / 2, min(bar1 - bar0, PITCH - PIER)))     # the bar lounge's bay, no wider than the others
    for k, (x, width) in enumerate(bays):
        c.windows += [Window(f'salon-{k + 1}-l', 1, x, width, PANO_SILL, PANO_HEAD), Window(f'salon-{k + 1}-r', -1, x, width, PANO_SILL, PANO_HEAD)]
    piers = [tables[k] + PITCH / 2 for k in range(GROUPS)]
    for k, x in enumerate(piers):                # sconces on the piers, above the banquette backs
        for side, sy in (('l', 1), ('r', -1)):
            c.placements.append(Placement(f'sconce-{k + 1}{side}', 'wall-sconce', 'salon', x, sy * (IN - .02), FLOOR_Z + 1.45, 0 if sy > 0 else 180))
    for k, x in enumerate(tables):               # brass racks on the ceiling cove above the bays
        for side, sy in (('l', 1), ('r', -1)):
            y = sy * (IN - .22)
            c.mounts.append(Mount(f'rack-{k + 1}{side}', 'rack', 'salon', x, y, ceiling_z(y) - .04, 0 if sy > 0 else 180, PITCH - PIER))
    lobby_xc = (-SPAN_X + lobby_x1) / 2
    galley_windows = (galley_x0 + 1.10, SPAN_X - 1.00)
    c.windows += [Window('wc-l', 1, lobby_xc, WC_W, FLOOR_Z + 1.10, HEAD, 'frosted'), Window('lobby-r', -1, lobby_xc, SMALL_W)]
    for k, x in enumerate(galley_windows):
        c.windows += [Window(f'galley-{k + 1}-l', 1, x, SMALL_W, FLOOR_Z + 1.00, HEAD), Window(f'service-{k + 1}-r', -1, x, SMALL_W)]
    c.reservations += [Box('wc-toilet', 'wc-toilet', -SPAN_X + .05, -SPAN_X + .70, .74, 1.18, FLOOR_Z, FLOOR_Z + .45, 'toilet against the bulkhead'),
                       Box('wc-basin', 'wc-basin', lobby_x1 - .48, lobby_x1 - .03, 1.075, IN - .02, FLOOR_Z + .75, FLOOR_Z + .90, 'basin on the outer wall')]
    last = tables[-1] + td / 2 + .10 + bd + .02
    c.reservations += [
        Box('bar-counter', 'bar-counter', BAR_COUNTER_X, counter_x1, ROOM_Y, IN - .02, FLOOR_Z, FLOOR_Z + 1.05, 'service bar facing the salon'),
        Box('back-bar', 'back-bar', backbar_x0, backbar_x0 + BACKBAR, ROOM_Y, .62, FLOOR_Z, FLOOR_Z + 2.00, 'glazed back-bar cabinet'),
        Box('drinks-ledge-l', 'drinks-ledge', last + .15, BAR_COUNTER_X - .10, IN - .22, IN - .02, FLOOR_Z + .98, FLOOR_Z + 1.05, 'standing ledge under window 6'),
        Box('galley-counter-outer', 'galley-counter', galley_x0 + .85, SPAN_X - .05 - GALLEY_RANGE, IN - .62, IN - .02, FLOOR_Z, FLOOR_Z + .92, 'galley worktops and cupboards'),
        Box('galley-range', 'galley-range', SPAN_X - .05 - GALLEY_RANGE, SPAN_X - .05, IN - .62, IN - .02, FLOOR_Z, FLOOR_Z + .92, 'coal range with its oven, against the end bulkhead (Tripo)'),
        Box('galley-counter-inner', 'galley-counter', galley_x0 + .05, 8.55, ROOM_Y + .02, ROOM_Y + .58, FLOOR_Z, FLOOR_Z + .92, 'galley worktops on the partition'),
    ]
    _curtains(c, lambda w: _room_at(c, w.x, w.side * (IN - .1)))
    return c


# --- brake van: the short tail vehicle, gangway at the front (B), open balcony at the back (A) --------------------
BRAKE_LENGTH = 12.0


CUPOLA_HW, CUPOLA_WALL = 1.25, .06                  # the lookout's half-width and wall; open below into the guard's room
LOOKOUT_RISE = .62                                  # the lookout's walls stand this far above the roof's crown
LOOKOUT_SEAT = (1.21, 1.66, -1.17, -.55, 2.45)      # x0, x1, y0, y1, top above the floor: against the lookout's rear wall
LOOKOUT_LADDER_X = 1.70                             # the ladder from the steps' top tread to the seat


def brake_van():
    """The guard's van that closes the train: guard's room with stove under a roof lookout at the front, a central
    lobby with the exterior doors, a luggage room, and an open balcony with railing, handbrake and tail lamp at the
    back. Its front end couples to the second-class coach like any other."""
    half = BRAKE_LENGTH / 2
    body = Body(x_a=-half + (BUFFER_X - BODY_X) + 1.30, x_b=half - (BUFFER_X - BODY_X), buffer_a=-half, buffer_b=half,
                end_a='balcony', end_b='gangway', bogies=(-3.30, 3.55), wheelbase=2.0,
                exterior_doors=(('m', .30),), cupola=(1.15, 3.85), crest_x=-2.45)
    c = Coach('brake-van', 'Rear brake van', body=body)
    _shared(c, vestibules=False)
    p1, p2 = (-.45, -.40), (1.00, 1.05)
    c.rooms += [Room('balcony', 'balcony', body.headstock(-1), body.x_a, -IN, IN, 'parquet'),
                Room('luggage', 'luggage', body.in_a, p1[0], -IN, IN, 'parquet'),
                Room('lobby', 'lobby', p1[1], p2[0], -IN, IN, 'tile'),
                Room('guard-room', 'guard', p2[1], body.in_b, -IN, IN, 'parquet')]
    c.walls += [Wall('luggage-partition', 'y', -IN, IN, *p1, [Opening('door-luggage', -.55, .55)]),
                Wall('guard-partition', 'y', -IN, IN, *p2, [Opening('door-guard-room', -.45, .45)])]
    c.doors += [Door('door-luggage', 'luggage-partition', 'door-luggage', 'sliding', +1, +1, False, 1.15),
                Door('door-guard-room', 'guard-partition', 'door-guard-room', 'sliding', -1, +1, True, .95)]
    for side, sy in (('l', 1), ('r', -1)):
        c.windows += [Window(f'guard-{side}', sy, 3.10, WIN_W), Window(f'guard-front-{side}', sy, 4.95, WC_W),
                      Window(f'luggage-{side}', sy, -2.45, WIN_W)]
    gi, ge = body.in_b, p2[1]
    c.reservations += [
        Box('stove', 'stove', ge + .15, ge + .70, IN - .62, IN - .10, FLOOR_Z, FLOOR_Z + 1.10, 'cast-iron stove with its flue to the roof'),
        Box('guard-bench', 'bench', 2.10, 4.30, -IN + .02, -IN + .52, FLOOR_Z, FLOOR_Z + .48, "guard's bench under the window"),
        Box('guard-desk', 'desk', 3.70, gi - .55, IN - .58, IN - .02, FLOOR_Z, FLOOR_Z + .80, 'writing desk with pigeon-holes'),
        Box('cupola-steps', 'steps', 1.45, 2.00, -1.15, -.60, FLOOR_Z, FLOOR_Z + .60, 'two steps and a ladder up to the lookout seat'),
        Box('luggage-shelves-l', 'luggage-shelves', body.in_a + .05, p1[0] - .05, IN - .52, IN - .02, FLOOR_Z, FLOOR_Z + 1.90, 'parcel shelves'),
        Box('luggage-shelves-r', 'luggage-shelves', body.in_a + .05, p1[0] - .80, -IN + .02, -IN + .52, FLOOR_Z, FLOOR_Z + 1.90, 'parcel shelves'),
        Box('handbrake', 'handbrake', body.headstock(-1) + .10, body.headstock(-1) + .32, IN - .40, IN - .18, FLOOR_Z, FLOOR_Z + 1.10, 'handbrake column on the balcony'),
    ]
    c.mounts += [Mount('tail-lamp', 'tail-lamp', 'balcony', body.headstock(-1) - .02, -IN + .30, FLOOR_Z + .95, 90),
                 Mount('guard-lamp', 'ceiling-lamp', 'guard-room', 4.65, 0., ceiling_z(0) - .02, 0)]   # past the lookout's well
    c.goals.update({'luggage': (-2.0, 0.), 'guard-room': (2.6, .20)})
    _curtains(c, lambda w: _room_at(c, w.x, w.side * (IN - .1)))
    return c


# --- second class: the run-down open saloon with its canteen at end A ----------------------------------------------
SC_PITCH = .55 + .65 + .55 + .02           # bench, legroom, bench, gap: 1.77 m
SC_BAYS = 8
# overhead fittings clear the tallest playable character (Nox, 1.78 m capsule) by 8 cm where players can stand: the
# luggage nets' mount (their lowest point is RACK_Z less the net's sag) and the centre of the menu board over the queue
OVERHEAD_CLEAR, RACK_Z, MENU_Z = 1.86, 1.92, 2.03
CANTEEN_X1 = -6.50                          # the canteen's front partition (the serving hatch)
COUNTER_DEPTH, COUNTER_H = .976, .92        # the serving counter (docs/BELMONTE_TRAIN_CANTEEN_LADY.md: 0.92 m)
# the Tripo canteen-counter measured from its centre (yaw 90: its front towards the saloon, +X): the body's plinth,
# the top's front edge and the front of its flat steel tray ledge ahead, the back of the top (open shelves on the
# cook's side) behind, the half-length; the ledge's surface above the floor, flat to 4 mm over the whole length
COUNTER_BODY_FRONT, COUNTER_TOP_FRONT, COUNTER_LEDGE_FRONT, COUNTER_BACK, COUNTER_HALF = .181, .275, .488, .488, 1.075
COUNTER_LEDGE_Z = .771
COUNTER_Y = (ROOM_Y + IN) / 2
COUNTER_X = CANTEEN_X1 + PART + .04 - COUNTER_BODY_FRONT    # the body passes through the wall, 4 cm proud on the saloon side
# the serving hatch: from the floor (the counter fills it below its top, which is the sill) to 1.80 m, over the body's
# length less 1 cm a side so the body tucks into the wall: y0, y1 and heights above the floor
HATCH = (COUNTER_Y - COUNTER_HALF + .01, COUNTER_Y + COUNTER_HALF - .01, 0., 1.80)
LADY_RADIUS = .36                           # the canteen lady standing and turning: 1.65 m tall, ~1.4x Kaede's shoulders
LADY_REACH = 1.20                           # from where she stands to the pot and to the hatch, ladle in hand
STOVE_X = -7.85                             # the stove right behind the counter (clear of its back), against the outer wall
# the Tripo canteen-shelves measured in their own frame (front -Y): the five brass hooks under the top tray (x of
# each, then y and height of the hook's tip, where a mug's handle rests) and the tray floors' heights
SHELF_HOOKS, SHELF_HOOK_TIP, SHELF_TRAYS = (-.27, -.13, .01, .15, .29), (-.17, 1.665), (.302, .808, 1.291)
# the Tripo canteen-mug (handle towards -X): where its handle's loop rests on a hook, from the mug's origin
MUG_HANDLE = (-.052, .074)
LADLE_HOOK = (-7.45, 1.70)                  # the big ladle's wall hook on the canteen side wall, behind the counter: x, height


def second_class():
    """The poor relation at the back of the train: the same body, worn livery, an open saloon of hard benches facing
    in pairs, and a tiled canteen at end A whose serving hatch opens onto the saloon. A service corridor beside the
    canteen keeps the passage to the vestibule and the brake van."""
    c = Coach('second-class', 'Second class and canteen', body=Body(livery='worn'))
    _shared(c)
    corridor_door = (-IN + CORRIDOR / 2 - .45, -IN + CORRIDOR / 2 + .45)
    _bulkheads(c, corridor_door, (-.55, .55), glazed=False)
    salon_x0 = CANTEEN_X1 + PART
    c.rooms += [Room('canteen', 'canteen', -SPAN_X, CANTEEN_X1, ROOM_Y, IN, 'tiles-grimy'),
                Room('service-corridor', 'corridor', -SPAN_X, CANTEEN_X1, -IN, CORR_Y, 'lino'),
                Room('saloon', 'saloon', salon_x0, SPAN_X, -IN, IN, 'lino')]
    c.walls += [Wall('canteen-side', 'x', -SPAN_X, CANTEEN_X1, CORR_Y, ROOM_Y, [Opening('door-canteen', -9.40, -8.52)]),
                Wall('canteen-front', 'y', ROOM_Y, IN, CANTEEN_X1, salon_x0, [Opening('canteen-hatch', HATCH[0], HATCH[1], FLOOR_Z + HATCH[2], FLOOR_Z + HATCH[3])])]
    c.doors.append(Door('door-canteen', 'canteen-side', 'door-canteen', 'sliding', -1, 1, False, .93))
    bw, bd, _ = asset_dims('second-class-bench')
    first = salon_x0 + 1.60                 # room to queue in front of the hatch
    for k in range(SC_BAYS):
        s0 = first + k * SC_PITCH
        for side, sy in (('l', 1), ('r', -1)):
            by = sy * (IN - .03 - bw / 2)
            for end, bx, yaw in (('a', s0 + bd / 2, 90), ('b', s0 + SC_PITCH - .02 - bd / 2, -90)):
                b = f'bench-{k + 1}{side}{end}'
                c.placements.append(Placement(b, 'second-class-bench', 'saloon', bx, by, FLOOR_Z, yaw))
                for n, dy in enumerate((-.30, .30)):
                    c.seats.append(Seat(f'{b}-seat-{n + 1}', b, bx + (.04 if yaw > 0 else -.04), by + dy, FLOOR_Z + .45, yaw))
            c.mounts.append(Mount(f'net-{k + 1}{side}', 'rack', 'saloon', s0 + SC_PITCH / 2, sy * (IN - .02), FLOOR_Z + RACK_Z, 0 if sy > 0 else 180, SC_PITCH - .1))
        c.mounts.append(Mount(f'bulb-{k + 1}', 'ceiling-lamp', 'saloon', s0 + SC_PITCH / 2, 0., ceiling_z(0) - .02, 0))
    # the quest bench: the one that keeps the carved M+L initials (all the others are clean)
    quest = next(p for p in c.placements if p.id == 'bench-5la')
    quest.id, quest.asset = 'quest-bench-ml', 'second-class-bench-carved'
    for st in c.seats:
        if st.furniture == 'bench-5la':
            st.furniture = 'quest-bench-ml'
    for k in range(0, SC_BAYS, 2):          # one wide window for every two bays, as on the concept
        x = first + (k + 1) * SC_PITCH - .01
        c.windows += [Window(f'saloon-{k // 2 + 1}-l', 1, x, 2 * SC_PITCH - .45), Window(f'saloon-{k // 2 + 1}-r', -1, x, 2 * SC_PITCH - .45)]
    c.windows += [Window('canteen-l', 1, -8.20, SMALL_W, FLOOR_Z + 1.00, HEAD), Window('service-r', -1, -8.20, SMALL_W)]
    # the serving line: the stove and its pot right behind the counter, the canteen lady between them facing the hatch,
    # the tray set down on the counter under the hatch, the passenger queuing in the saloon in front of it
    sw, sd, _ = asset_dims('canteen-stove')
    c.placements.append(Placement('canteen-stove', 'canteen-stove', 'canteen', STOVE_X, IN - sd / 2, FLOOR_Z, 0))
    # the pot on the stove's large left hotplate (left seen from the room, i.e. towards -X)
    # (the fitted pot's footprint centre is 1 cm off its base, which sits where the ladle-less pot always stood)
    c.placements.append(Placement('canteen-pot', 'canteen-pot', 'canteen', STOVE_X - .23, IN - sd / 2 - .04, FLOOR_Z + .83, 0))
    hy = (HATCH[0] + HATCH[1]) / 2
    # the Tripo counter through the hatch: body mostly in the kitchen, the front of its top and its tray ledge out in
    # the saloon where passengers slide their trays; its top is the hatch's sill
    c.placements.append(Placement('canteen-counter', 'canteen-counter', 'canteen', COUNTER_X, COUNTER_Y, FLOOR_Z, 90, through='canteen-front'))
    # the enamel sink against the outer wall at the canteen's end, its draining board towards the stove
    kw, kd, _ = asset_dims('canteen-sink')
    c.placements.append(Placement('canteen-sink', 'canteen-sink', 'canteen', -SPAN_X + .03 + kw / 2, IN - .02 - kd / 2, FLOOR_Z, 0))
    # the empty riveted shelves against the canteen's end wall, clear of the door, hooks facing into the kitchen; mugs
    # hang from the five hooks by their handles (handle towards the shelves) and stand on the middle tray, each its own
    # placement of the one canteen-mug asset (the plates come later)
    fw, fd, _ = asset_dims('canteen-shelves')
    shelf = Placement('canteen-shelves', 'canteen-shelves', 'canteen', -SPAN_X + .01 + fd / 2, ROOM_Y + .03 + fw / 2, FLOOR_Z, 90)
    c.placements.append(shelf)
    def on_shelf(name, lx, ly, lz, yaw):            # shelf frame (front -Y) to coach: the shelves turned 90 degrees
        c.placements.append(Placement(name, 'canteen-mug', 'canteen', shelf.x - ly, shelf.y + lx, FLOOR_Z + lz, (shelf.yaw + yaw) % 360))
    for k, hx in enumerate(SHELF_HOOKS):
        on_shelf(f'canteen-mug-hook-{k + 1}', hx, SHELF_HOOK_TIP[0] - (-MUG_HANDLE[0]), SHELF_HOOK_TIP[1] - MUG_HANDLE[1], -90)
    for k, (mx, yaw) in enumerate(((-.27, 0), (-.12, 270), (.04, 90), (.22, 180))):      # quarter turns: handles every way
        on_shelf(f'canteen-mug-shelf-{k + 1}', mx, .02, SHELF_TRAYS[1], yaw)
    # the big ladle hanging by its end hook from the wall hook (canteen-ladle mount), bowl down, flat to the wall
    c.placements.append(Placement('canteen-ladle', 'canteen-ladle', 'canteen', LADLE_HOOK[0], ROOM_Y + .075, FLOOR_Z + LADLE_HOOK[1] + .02, 180))
    c.reservations += [
    ]
    back = COUNTER_X - COUNTER_BACK
    spot = (back - LADY_RADIUS - .04, IN - sd - LADY_RADIUS - .04)     # clear of the counter's back and of the stove's front
    ledge_x = COUNTER_X + COUNTER_LEDGE_FRONT
    queue_x = ledge_x + HUMAN['radius'] + .07                                # clear of the tray ledge
    c.mounts += [
        Mount('canteen-npc-spot', 'npc-spot', 'canteen', spot[0], spot[1], FLOOR_Z, 90),            # the lady, facing the hatch
        Mount('canteen-serve-point', 'serve-point', 'saloon', (COUNTER_X + COUNTER_TOP_FRONT + ledge_x) / 2, hy, FLOOR_Z + COUNTER_LEDGE_Z, -90),  # the tray, on the ledge in front of the top
        Mount('canteen-queue', 'queue', 'saloon', queue_x, hy, FLOOR_Z, -90, .80),                    # the passenger, facing the hatch; the line runs +X
        Mount('canteen-ladle', 'ladle', 'canteen', LADLE_HOOK[0], ROOM_Y + .02, FLOOR_Z + LADLE_HOOK[1], 0),  # where the big ladle hangs
    ]
    c.goals.update({'canteen-npc-spot': spot, 'canteen-queue': (queue_x, hy)})
    c.mounts.append(Mount('menu-board', 'menu-board', 'saloon', salon_x0 + .02, .75, FLOOR_Z + MENU_Z, -90, 1.0))
    c.goals.update({'canteen': (-7.60, .30)})
    _curtains(c, lambda w: _room_at(c, w.x, w.side * (IN - .1)))
    return c


# --- baggage van: the guard's compartment behind a gangway at end A, the luggage hold, a closed end towards the tender
CARGO_W = 1.60                              # clear width of each pair of sliding luggage doors
GUARD_X1 = -7.60                            # the guard compartment's partition


def baggage_van():
    """The luxury train's baggage van, right behind the tender. End A couples to the restaurant through a gangway;
    end B, towards the tender, is closed (no passenger gangway onto the locomotive). The guard's compartment at end A
    has its own exterior doors and two projecting lookout bays; the hold has two pairs of wide double sliding doors
    on each side, a few high windows and parcel shelving along the walls."""
    body = Body(end_b='closed', exterior_doors=(('g', -10.55),), cargo_doors=(-3.40, 5.70), crest_x=1.15)
    c = Coach('baggage-van', 'Baggage van', body=body)
    _shared(c, vestibules=False)
    hold_x0 = GUARD_X1 + PART
    c.rooms += [Room('guard-room', 'guard', body.in_a, GUARD_X1, -IN, IN, 'parquet'),
                Room('hold', 'hold', hold_x0, body.in_b, -IN, IN, 'parquet')]
    c.walls.append(Wall('guard-partition', 'y', -IN, IN, GUARD_X1, hold_x0, [Opening('door-hold', -.55, .55)]))
    c.doors.append(Door('door-hold', 'guard-partition', 'door-hold', 'sliding', +1, +1, False, 1.15))
    for side, sy in (('l', 1), ('r', -1)):
        c.windows += [Window(f'guard-bay-{side}', sy, -8.85, 1.00, FLOOR_Z + .75, HEAD, 'bay'),
                      Window(f'guard-{side}', sy, -9.75, .60)]
        for k, x in enumerate((-5.60, .95, 9.70)):
            c.windows.append(Window(f'hold-{k + 1}-{side}', sy, x, SMALL_W, FLOOR_Z + 1.40, HEAD))
    # parcel shelving along both walls, leaving the luggage doorways and a wide middle clear
    spans = _free_spans(hold_x0 + .05, body.in_b - .05, [(x - CARGO_W / 2 - .15, x + CARGO_W / 2 + .15) for x in body.cargo_doors])
    for k, (a, b) in enumerate(spans):
        for side, sy in (('l', 1), ('r', -1)):
            y0, y1 = sorted((sy * (IN - .02), sy * (IN - .55)))
            c.reservations.append(Box(f'shelves-{k + 1}{side}', 'luggage-shelves', a, b, y0, y1, FLOOR_Z, FLOOR_Z + 2.00, 'parcel and trunk shelving'))
    c.reservations += [
        Box('guard-stove', 'stove', GUARD_X1 - .70, GUARD_X1 - .15, IN - .62, IN - .10, FLOOR_Z, FLOOR_Z + 1.10, 'small stove with its flue'),
        Box('guard-desk', 'desk', GUARD_X1 - 1.75, GUARD_X1 - .85, IN - .58, IN - .02, FLOOR_Z, FLOOR_Z + .80, "the guard's sorting desk"),
        Box('guard-handbrake', 'handbrake', body.in_a + .10, body.in_a + .34, -IN + .45, -IN + .69, FLOOR_Z, FLOOR_Z + 1.10, 'handbrake column'),
    ]
    c.mounts += [Mount('guard-lamp', 'ceiling-lamp', 'guard-room', -9.5, 0., ceiling_z(0) - .02, 0),
                 Mount('hold-lamp-1', 'ceiling-lamp', 'hold', -1.0, 0., ceiling_z(0) - .02, 0),
                 Mount('hold-lamp-2', 'ceiling-lamp', 'hold', 8.0, 0., ceiling_z(0) - .02, 0)]
    c.goals.update({'guard-room': (-9.0, 0.), 'hold': (1.0, 0.)})
    _curtains(c, lambda w: _room_at(c, w.x, w.side * (IN - .1)))
    return c


def _free_spans(a0, a1, blocked, min_len=.5):
    out, a = [], a0
    for b0, b1 in sorted(blocked):
        if b0 - a >= min_len:
            out.append((a, b0))
        a = max(a, b1)
    if a1 - a >= min_len:
        out.append((a, a1))
    return out


def coaches():
    return [baggage_van(), restaurant(), first_class(), second_class(), brake_van()]


# --- the tender: water tank, coal space and the fireman's footplate behind the locomotive's cab --------------------
TENDER_LENGTH = 9.0
TENDER_HALF = 1.55                          # tank half-width: narrower than the coaches, like the locomotive
TENDER_TANK = (-4.00, 2.56)                 # rear face of the tank, front face (the coal plate, facing the footplate)
TENDER_TANK_Z = (1.05, 3.30)
TENDER_COAL = (.20, 2.50)                   # the coal space on top of the front of the tank, inside raised coping plates
TENDER_COPING_Z = 3.75
TENDER_HEADSTOCK = 4.10
TENDER_AXLES = (-2.50, -.25, 2.00)          # three rigid axles, as in the concept (locomotive-tender--tender-profile-v2)
TENDER_WHEEL_R = .50
TENDER_LOCKER = (2.56, 3.30, 1.00, 2.55)    # tool lockers each side of the footplate: x0, x1, inner y, top z
TENDER_FALL_PLATE = 4.42                    # the hinged steel plate bridging to the locomotive's footplate
COAL_HOLE = (.32, 1.50, 2.05)               # half-width, bottom and top of the shovelling hole in the coal plate
TENDER_LADDER = (.95, 1.35)                 # the rear ladder's stiles (|y|), on the driver's side
TENDER_LAMP_Y = .60                         # the rear lamp irons, clear of the ladder


def tender():
    """The tender coupled behind the locomotive. Not a coach: a riveted water tank with the coal heaped on top of its
    front half, three rigid axles in outside frames, rear buffers to the baggage van's closed end, and at the front the
    fireman's footplate (floor at FLOOR_Z, like the cab's) between two tool lockers, with the shovelling hole in the
    coal plate and a fall plate towards the locomotive. Only the footplate is walkable."""
    half = TENDER_LENGTH / 2
    body = Body(x_a=TENDER_TANK[0], x_b=TENDER_TANK[1], buffer_a=-half, buffer_b=half, end_a='closed', end_b='footplate',
                bogies=(), exterior_doors=(), crest_x=-.75, kind='tender',
                walk=(TENDER_TANK[1] + .06, TENDER_FALL_PLATE - .02), walk_y=TENDER_LOCKER[2])
    c = Coach('tender', 'Tender', body=body)
    lo, hi = body.walk
    c.rooms.append(Room('footplate', 'footplate', TENDER_TANK[1], TENDER_FALL_PLATE, -TENDER_LOCKER[2], TENDER_LOCKER[2], 'parquet'))
    c.goals.update({'footplate': ((lo + hi) / 2, 0.)})
    c.mounts += [Mount('coal-hole', 'coal-hole', 'footplate', TENDER_TANK[1], 0., (COAL_HOLE[1] + COAL_HOLE[2]) / 2, 90),
                 Mount('tender-lamp-l', 'lamp-bracket', 'footplate', TENDER_TANK[0] - .03, TENDER_LAMP_Y, 3.05, -90),
                 Mount('tender-lamp-r', 'lamp-bracket', 'footplate', TENDER_TANK[0] - .03, -TENDER_LAMP_Y, 3.05, -90)]
    return c


# --- the locomotive: a 4-6-2 Pacific whose cab is walkable and laid out to be driven later --------------------------
LOCO_LENGTH = 14.0
LOCO_HALF = 1.55                            # cab and running boards, like the tender
CAB = (-6.95, -4.30)                        # cab floor from its open back (towards the tender) to the front plate
CAB_WALL = .06
CAB_IN = LOCO_HALF - CAB_WALL               # 1.49: inner face of the cab sides
CAB_ENTRY = -6.30                           # the side cut-outs from the back of the cab to here, where the crew climbs in
CAB_DOOR = (.55, 1.95)                      # half-width and height of the doorway in the cab's back plate, onto the tender
CAB_TOP, CAB_ROOF = 3.45, 4.05              # cab sides and roof apex
BACKHEAD_X = -5.00                          # the firebox backhead's face, standing into the cab
PIPEWORK = .41                              # depth of the pipework hung on it (the Tripo loco-backhead)
FIREBOX_HW, FIREBOX_TOP = .95, 3.25
BOILER = (-4.30, 3.70, .88, 2.95)           # lagged barrel: x0, x1, radius, axis height
SMOKEBOX = (3.70, 4.95, .92)
RUNNING_BOARD_Z = 2.02
DRIVERS = (2.55, .45, -1.65)                # three coupled axles, 1.90 m wheels
DRIVER_R = .95
LEADING = (6.05, 4.55)                      # leading bogie, 0.90 m wheels
LEADING_R = .45
TRAILING = (-3.85,)                         # trailing axle under the cab, 1.00 m wheels
TRAILING_R = .50
CRANK = .38
CYLINDER = (4.20, 5.30, .30, 1.05, 1.20)    # x0, x1, radius, axis height, |y|
LOCO_BEAM = 6.55                            # front buffer beam
# where the Tripo backhead's pipes stop short, measured on the fitted mesh in the coach frame (z above the floor)
BACKHEAD_STUBS = (-5.00, .8825, 1.9395, .0165)                      # x, |y|, z, radius: the outer columns' tops, bent forward
BACKHEAD_FEET = ((-5.278, .723, .060, .016), (-5.278, .815, .097, .013))   # x, |y|, bottom, radius: the injector pipes
FOUNTAIN = (-4.66, 2.08, .62, .05)          # the steam fountain on the firebox top: x, axis z above the floor, half-length, radius
WHISTLE_VALVE = (-4.86, .035)               # x and radius of the whistle valve under the driver's pull rod


def cab_ceiling_z(y):
    """The underside of the cab's elliptic roof (5 cm thick) at a lateral offset y."""
    return CAB_TOP + (CAB_ROOF - CAB_TOP) * math.sqrt(max(0., 1 - (y / (LOCO_HALF + .05)) ** 2)) - .05


def locomotive():
    """The engine at the head of the train, after the concept (locomotive-tender--locomotive-profile and the cab
    interior), in the railway's black with brass and red lining (the user's choice): brass-banded boiler, smokebox
    and chimney, brass dome, three 1.90 m coupled wheels with
    their rods, leading bogie and trailing axle. Its cab is the walkable part: open at the back onto the tender's
    footplate, the firebox backhead with the fire door at the front, the driver's controls on the left and the
    fireman's side on the right. Every control is a Mount of kind 'control' at its pivot (and a separate object in the
    GLB), so a later driving mode can find and animate it."""
    half = LOCO_LENGTH / 2
    lo, hi = CAB[0] + .03, BACKHEAD_X - PIPEWORK - .02     # up to the front of the backhead's pipework
    body = Body(x_a=CAB[0], x_b=LOCO_BEAM, buffer_a=-half, buffer_b=half, end_a='footplate', end_b='closed',
                bogies=(), exterior_doors=(), crest_x=-5.45, kind='locomotive', walk=(lo, hi), walk_y=CAB_IN - .09)
    c = Coach('locomotive', 'Locomotive 4-6-2', body=body)
    F = FLOOR_Z
    c.rooms.append(Room('cab', 'cab', CAB[0], BACKHEAD_X, -CAB_IN, CAB_IN, 'parquet'))
    for side, sy in (('l', 1), ('r', -1)):          # the cab's back plate either side of the doorway onto the tender
        c.reservations.append(Box(f'cab-back-{side}', 'wall', CAB[0], CAB[0] + CAB_WALL, *sorted((sy * CAB_DOOR[0], sy * CAB_IN)), F, CAB_TOP, 'cab back plate'))
    c.reservations += [
        Box('reverser-stand', 'control-stand', BACKHEAD_X - .52, BACKHEAD_X - .26, .98, 1.30, F, F + 1.15, 'screw reverser column with its brass quadrant'),
        Box('driver-seat', 'seat', -6.25, -5.85, 1.12, CAB_IN, F + .62, F + .80, "driver's flap seat on the cab side"),
        Box('fireman-seat', 'seat', -6.25, -5.85, -CAB_IN, -1.12, F + .62, F + .80, "fireman's flap seat on the cab side"),
        Box('pipework-l', 'pipework', BACKHEAD_X - PIPEWORK, BACKHEAD_X, .55, FIREBOX_HW, F, F + 1.93, "backhead pipe columns, the driver's side"),
        Box('pipework-r', 'pipework', BACKHEAD_X - PIPEWORK, BACKHEAD_X, -FIREBOX_HW, -.55, F, F + 1.93, "backhead pipe columns with the injector, the fireman's side"),
    ]
    c.seats += [Seat('driver', 'driver-seat', -6.05, 1.28, F + .80, 90), Seat('fireman', 'fireman-seat', -6.05, -1.28, F + .80, 90)]
    bx = BACKHEAD_X - PIPEWORK          # the controls stand at the front of the pipework, on shafts from the backhead
    # the Tripo pipework (gauges, water glasses, valves, pipes) hangs on the riveted backhead plate, above the floor
    c.placements.append(Placement('loco-backhead', 'loco-backhead', 'cab', BACKHEAD_X - asset_dims('loco-backhead')[1] / 2, 0., F + .06, -90))
    c.mounts += [
        Mount('regulator', 'control', 'cab', bx, 0., F + 1.15, 90, .50),               # lever above the central fitting, swinging across
        Mount('reverser', 'control', 'cab', BACKHEAD_X - .39, 1.14, F + 1.15, 90, .30),  # handwheel on the column
        Mount('brake', 'control', 'cab', -5.60, CAB_IN - .06, F + 1.20, 0, .25),       # driver's brake valve on the side
        Mount('whistle', 'control', 'cab', bx, .40, F + 2.02, 90, .15),
        Mount('sander', 'control', 'cab', bx, .45, F + .95, 90, .20),
        Mount('fire-door', 'control', 'cab', BACKHEAD_X - .01, 0., F + .40, 90, .70),  # on the plate, between the pipe columns
        Mount('injector-valve', 'control', 'cab', bx, -.42, F + .78, 90, .10),
        Mount('pressure-gauge', 'gauge', 'cab', bx + .12, 0., F + 1.70, 90, .36),     # gauge faces on the Tripo pipework
        Mount('water-gauge-l', 'gauge', 'cab', bx + .18, .40, F + 1.35, 90, .45),
        Mount('water-gauge-r', 'gauge', 'cab', bx + .18, -.40, F + 1.35, 90, .45),
        Mount('cab-lamp', 'ceiling-lamp', 'cab', -5.70, 0., cab_ceiling_z(0.), 0),        # under the roof's apex
        Mount('head-lamp', 'head-lamp', 'cab', LOCO_BEAM + .05, 0., 1.62, 90),
        Mount('chimney-smoke', 'emitter', 'cab', 4.40, 0., 4.12, 0, .44),             # smoke rises from the sooty floor of the bore
    ]
    c.goals.update({'cab': (-6.10, 0.), 'regulator': (hi - .30, .30), 'fire-door': (hi - .30, 0.)})
    return c


def cab_pipes():
    """The cab's own pipe runs, finishing what the Tripo backhead leaves in mid-air, as on a real Pacific: the outer
    columns feed the steam fountain (the manifold on the firebox top), the fountain and the whistle valve take steam
    from the boiler through its back end, and the injector pipes drop through the footplate. Each run is a list of
    axis-aligned points (coach frame) with a radius, a material and how each end finishes: 'union' where it joins a
    Tripo pipe or a fitting, 'cap' at the fountain's ends, 'flange' where it meets the boiler or the floor."""
    F = FLOOR_Z
    sx, sy, sz, sr = BACKHEAD_STUBS
    fx, fz, fh, fr = FOUNTAIN
    wx, wr = WHISTLE_VALVE
    boiler = CAB[1] - .005                  # the boiler barrel's back end, behind the cab front plate
    whistle = next(m for m in locomotive().mounts if m.id == 'whistle')
    runs = [dict(name='fountain', pts=[(fx, -fh, F + fz), (fx, fh, F + fz)], r=fr, mat='iron-black', ends=('cap', 'cap')),
            dict(name='steam-supply', pts=[(fx, 0., F + fz), (fx, 0., F + 2.30), (boiler, 0., F + 2.30)], r=.04,
                 mat='iron-black', ends=('union', 'flange')),
            dict(name='whistle-feed', pts=[(wx, whistle.y, F + fz), (fx, whistle.y, F + fz)], r=.02, mat='brass-dull',
                 ends=('union', 'union')),
            dict(name='whistle-pipe', pts=[(wx, whistle.y, F + 2.12), (wx, whistle.y, F + 2.38), (boiler, whistle.y, F + 2.38)],
                 r=.022, mat='brass-dull', ends=('union', 'flange'))]
    for side, s in (('l', 1), ('r', -1)):
        runs.append(dict(name=f'column-feed-{side}', pts=[(sx, s * sy, F + sz), (fx, s * sy, F + sz), (fx, s * sy, F + fz),
                                                           (fx, s * fh, F + fz)], r=sr, mat='brass-dull', ends=('union', 'union')))
        for k, (x, y, z, r) in enumerate(BACKHEAD_FEET):
            runs.append(dict(name=f'injector-{side}-{k + 1}', pts=[(x, s * y, F + z + .015), (x, s * y, F)], r=r,
                             mat='brass-dull', ends=('union', 'flange')))
    return runs


def vehicles():
    """Everything the Blender build makes: the locomotive, the tender and the coaches."""
    return [locomotive(), tender()] + coaches()


# --- checks -------------------------------------------------------------------------------------------------------
def start(c):
    """Where the walk checks begin: just inside a gangway end."""
    b = c.body
    if 'gangway' not in (b.end_a, b.end_b) and b.walk:
        return (sum(b.walk) / 2, 0.)
    s = -1 if b.end_a == 'gangway' else 1
    return (b.inner(s) - s * .30, 0.)


STEP_TREADS = ((.96, .18), (.66, .30))   # the two hanging steps under a door or gate: top above the rail, depth
STEP_BACK = .22                           # how far each tread reaches in under the body side


def step_treads(sy, x0, x1, inset=0.):
    """The two steps under an opening on side sy from x0 to x1, upper first: (x0, x1, y0, y1, top z)."""
    y = sy * (HALF - inset)
    return [(x0 + .02, x1 - .02, *sorted((y - sy * STEP_BACK, y + sy * (depth - STEP_BACK))), z) for z, depth in STEP_TREADS]


def balcony_gate(body, s):
    """x range of the gate gap in the side railings of the balcony at end s, over the steps."""
    return tuple(sorted((body.face(s) + s * .15, body.face(s) + s * .85)))


def lookout_well(body):
    """(x0, x1, half-width, top) of the opening from the guard's room up into the lookout, or None."""
    if not body.cupola:
        return None
    x0, x1 = body.cupola
    w = CUPOLA_WALL
    return x0 + w, x1 - w, CUPOLA_HW - w, roof_z(CUPOLA_HW) - .04     # up to the lookout's own walls


def lookout_top(body):
    """(underside, top) of the lookout's roof slab, above the main roof."""
    return ROOF_TOP + LOOKOUT_RISE - CUPOLA_WALL, ROOF_TOP + LOOKOUT_RISE + .16


def railings(body):
    """Balcony railings as boxes (x0, x1, y0, y1): along the outer edge and down both sides, leaving a gap at the
    steps on each side."""
    out = []
    for s in (-1, 1):
        if body.end(s) != 'balcony':
            continue
        edge = body.headstock(s)
        x0, x1 = sorted((edge, edge - s * .05))
        out.append((x0, x1, -IN, IN))
        gap0, gap1 = balcony_gate(body, s)                                    # the step opening on each side
        for sy in (-1, 1):
            y0, y1 = sorted((sy * IN, sy * (IN - .05)))
            for a0, a1 in ((min(edge, body.face(s)), gap0), (gap1, max(edge, body.face(s)))):
                if a1 - a0 > .02:
                    out.append((a0, a1, y0, y1))
    return out


INTERIOR_TAGS = ['interior', 'no_sprint', 'no_climb']
VOLUME_REACH = .05      # each room's volume reaches this far into its partitions, so doorways stay covered
VOLUME_DOORSTEP = .10   # and this far out past the body side, over the doorstep of an open exterior door


def interior_volumes(c):
    """Where a player is inside the train (and may not sprint): [dict(name, kind, box=[x0, x1, y0, y1, z0, z1],
    tags)]. One per room from just under the floor to the ceiling's springing, reaching into its partitions and out
    through the side walls (an open exterior door); one for the whole body between its end walls (the rooms leave
    passages untiled); one per gangway end from the end wall out past the buffer line;
    the brake van's lookout; the locomotive's cab out to its buffer line and the tender's footplate out to its own."""
    b, F = c.body, FLOOR_Z
    z0 = F - .10
    out = []
    add = lambda name, kind, *q: out.append(dict(name=name, kind=kind, box=[round(v, 4) for v in q], tags=list(INTERIOR_TAGS)))
    for r in c.rooms:
        x0, x1, y0, y1 = r.x0 - VOLUME_REACH, r.x1 + VOLUME_REACH, r.y0 - VOLUME_REACH, r.y1 + VOLUME_REACH
        if b.kind == 'locomotive':
            add(r.name, r.kind, b.buffer_a, x1, -LOCO_HALF - VOLUME_DOORSTEP, LOCO_HALF + VOLUME_DOORSTEP, z0, CAB_TOP)
        elif b.kind == 'tender':
            add(r.name, r.kind, TENDER_TANK[1], b.buffer_b, -TENDER_HALF, TENDER_HALF, z0, F + 2.20)
        else:
            y0 = -HALF - VOLUME_DOORSTEP if r.y0 <= -IN + .01 else y0
            y1 = HALF + VOLUME_DOORSTEP if r.y1 >= IN - .01 else y1
            add(r.name, r.kind, x0, x1, y0, y1, z0, CANT_Z if r.kind == 'balcony' else CEIL_SPRING)
    if b.kind not in ('locomotive', 'tender'):     # the whole body too: the rooms do not tile it (the restaurant's passage)
        add('body', 'body', b.in_a, b.in_b, -HALF - VOLUME_DOORSTEP, HALF + VOLUME_DOORSTEP, z0, CEIL_SPRING)
    for s, end in ((-1, 'a'), (1, 'b')):
        if b.end(s) == 'gangway':
            x0, x1 = sorted((b.inner(s), b.buffer(s) + s * GANGWAY_OVERLAP))
            hw = GANGWAY_W / 2 + .04
            add(f'gangway-{end}', 'gangway', x0, x1, -hw, hw, z0, F + GANGWAY_H)
    well = lookout_well(b)
    if well:
        x0, x1, hw, _ = well
        add('lookout', 'lookout', x0, x1, -hw, hw, CEIL_SPRING - .10, lookout_top(b)[0])
    return out


EXTERIOR_TAGS = ['no_climb']
EXTERIOR_MARGIN = .15   # beyond the body's sides and roof


def exterior_volumes(c):
    """The vehicle's outside, where nobody may climb onto it (a moving train): one 'train_exterior' box per vehicle
    over its body and roof (the lookout, the engine's chimney), from the bogies to just above the top, buffer to
    buffer. [dict(name, kind, box, tags)] like interior_volumes."""
    b, m = c.body, EXTERIOR_MARGIN
    if b.kind == 'locomotive':
        hw, top = LOCO_HALF, BOILER[3] + BOILER[2] + 1.3          # the chimney stands about 1.3 m above the barrel
    elif b.kind == 'tender':
        hw, top = TENDER_HALF, TENDER_COPING_Z
    else:
        hw, top = HALF, lookout_top(b)[1] if b.cupola else ROOF_TOP
    box = [b.buffer_a, b.buffer_b, -hw - m, hw + m, .20, top + m]
    return [dict(name='train_exterior', kind='train_exterior', box=[round(v, 4) for v in box], tags=list(EXTERIOR_TAGS))]


def walkable_grid(c, radius, step=.025):
    """Free floor cells for a disc of `radius` (2D, at standing height): walls, closed wall parts, open sliding leaves,
    floor-standing furniture and reservations are obstacles. Returns (grid, x0, y0, step)."""
    lo, hi = c.body.walk_limits()
    nx, ny = int(round((hi - lo) / step)), int(round(2 * IN / step))
    obstacles = list(railings(c.body))
    for w in c.walls:
        spans = sorted((o.a0, o.a1) for o in w.openings if o.z0 - FLOOR_Z < .3)    # a serving hatch is not a way through
        cuts, a = [], w.a0
        for o0, o1 in spans:
            cuts.append((a, o0)); a = o1
        cuts.append((a, w.a1))
        for a0, a1 in cuts:
            if a1 - a0 > 1e-6:
                obstacles.append((w.c0, w.c1, a0, a1) if w.axis == 'y' else (a0, a1, w.c0, w.c1))
    for d in c.doors:
        if d.kind != 'sliding' or d.wall.startswith('end-'):
            continue
        w = c.wall(d.wall); o = next(o for o in w.openings if o.name == d.opening)
        a0 = (o.a1 - .025) if d.slide > 0 else (o.a0 + .025 - d.width)
        a1 = a0 + d.width
        cface = (w.c1 if d.face > 0 else w.c0)
        c0, c1 = sorted((cface, cface + d.face * .045))
        obstacles.append((c0, c1, a0, a1) if w.axis == 'y' else (a0, a1, c0, c1))
    for p in c.placements:
        if p.z - FLOOR_Z < .05:
            x0, x1, y0, y1 = footprint(p)
            pad = .04 if p.asset == 'restaurant-table' else 0.
            obstacles.append((x0 - pad, x1 + pad, y0 - pad, y1 + pad))
    for b in c.reservations:
        if b.z0 - FLOOR_Z < 1.0:
            obstacles.append((b.x0, b.x1, b.y0, b.y1))
    xs = lo + (np.arange(nx) + .5) * step
    ys = -IN + (np.arange(ny) + .5) * step
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    grid = (np.abs(Y) <= c.body.walk_y - radius) & (X >= lo + radius) & (X <= hi - radius)
    for ox0, ox1, oy0, oy1 in obstacles:
        dx = np.maximum(np.maximum(ox0 - X, 0.), X - ox1); dy = np.maximum(np.maximum(oy0 - Y, 0.), Y - oy1)
        grid &= dx * dx + dy * dy >= radius * radius
    return grid, step


def reachable(c, radius, start, goals):
    """Breadth-first search over the walkable grid from `start` (x, y); returns {goal name: reached}."""
    grid, step = walkable_grid(c, radius)
    nx, ny = grid.shape
    lo = c.body.walk_limits()[0]
    cell = lambda x, y: (int((x - lo) / step), int((y + IN) / step))
    si, sj = cell(*start)
    if not grid[si, sj]:
        return {name: False for name in goals}
    seen = [[False] * ny for _ in range(nx)]
    seen[si][sj] = True
    stack = [(si, sj)]
    while stack:
        i, j = stack.pop()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < nx and 0 <= b < ny and grid[a, b] and not seen[a][b]:
                seen[a][b] = True
                stack.append((a, b))
    out = {}
    for name, (x, y) in goals.items():
        i, j = cell(x, y)
        out[name] = seen[i][j]
    return out


def goals(c):
    """Points a passenger must reach from vestibule A: gangway B, the four exterior doors and a point just inside
    every room (staff rooms included)."""
    b = c.body
    g = {}
    for end, sx in (('a', -1), ('b', 1)):
        if b.end(sx) == 'gangway':
            g[f'gangway-{end}'] = (b.inner(sx) - sx * .30, 0.)
        elif b.end(sx) == 'balcony':
            g[f'balcony-{end}'] = (b.headstock(sx) - sx * .45, 0.)
        elif b.end(sx) == 'footplate':
            g[f'footplate-{end}'] = (b.walk_limits()[sx > 0] - sx * .45, 0.)
    for label, x in b.exterior_doors:
        for side, sy in (('l', 1), ('r', -1)):
            g[f'exterior-door-{label}{side}'] = (x, sy * (IN - .35))
    for k, x in enumerate(b.cargo_doors):
        for side, sy in (('l', 1), ('r', -1)):
            g[f'cargo-door-{k + 1}{side}'] = (x, sy * (IN - .35))
    for r in c.rooms:
        if r.kind in ('vestibule', 'balcony'):
            continue
        if r.name in c.goals:
            g[r.name] = c.goals[r.name]
            continue
        door = next((o for w in c.walls for o in w.openings if o.name == f'door-{r.name}'), None)
        if r.kind == 'cabin':
            g[r.name] = ((r.x0 + r.x1) / 2, ROOM_Y + .45)
        elif c.name == 'first-class' and door is not None:
            g[r.name] = ((door.a0 + door.a1) / 2, ROOM_Y + .35)
        elif c.name == 'restaurant' and r.name in RESTAURANT_GOALS:
            g[r.name] = RESTAURANT_GOALS[r.name]
        else:
            g[r.name] = ((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2 if r.kind != 'salon' else 0.)
    for name, point in c.goals.items():      # points that are not rooms (the locomotive's controls)
        g.setdefault(name, point)
    return g


# just inside the restaurant's WC door, the galley past its bar door, the bar's staff space
RESTAURANT_GOALS = {'wc': (-SPAN_X + LOBBY - .45, .76), 'galley': (6.50, .45), 'bar': (5.25, .10)}


def check(c):
    """Numbers that must hold for the coach; returns a list of failures (empty when it is right)."""
    bad = []
    if abs(2 * IN - (WIDTH - 2 * WALL)) > 1e-9:
        bad.append('internal width does not match the envelope')
    if c.name == 'first-class':
        if abs((IN - ROOM_Y) + PART + CORRIDOR - 2 * IN) > 1e-9 or abs(IN - ROOM_Y - CABIN_W) > 1e-9:
            bad.append('cabin + partition + corridor does not fill the interior')
        for r in c.rooms:
            if r.kind == 'cabin' and (abs(r.x1 - r.x0 - 3.0) > 1e-9 or abs(r.y1 - r.y0 - CABIN_W) > 1e-9):
                bad.append(f'{r.name} is not 3.00 x {CABIN_W:.2f} m')
    if c.name == 'restaurant':
        aisle = min(-max(footprint(p)[2:]) if p.y < 0 else min(footprint(p)[2:]) for p in c.placements if p.asset == 'restaurant-banquette')
        if 2 * aisle < .95:
            bad.append(f'restaurant aisle {2 * aisle:.3f} m < 0.95 m')
    # every floor-standing placement sits inside its room, off the walls
    for p in c.placements:
        r = c.room(p.room)
        x0, x1, y0, y1 = footprint(p) if p.z - FLOOR_Z < .05 else (p.x, p.x, p.y, p.y)
        rx0, rx1, ry0, ry1 = r.x0, r.x1, r.y0, r.y1
        if p.through:                       # through a wall: the room and the one beyond it together
            w = c.wall(p.through)
            o = next(rm for rm in c.rooms if rm is not r and (rm.x0 <= w.c1 + 1e-6 <= rm.x1 or rm.x0 <= w.c0 - 1e-6 <= rm.x1)
                     and rm.y0 <= (y0 + y1) / 2 <= rm.y1)
            rx0, rx1, ry0, ry1 = min(rx0, o.x0), max(rx1, o.x1), max(ry0, min(r.y0, o.y0)), min(ry1, max(r.y1, o.y1))
            if not any(op.a0 - 1e-6 <= (y0 + y1) / 2 <= op.a1 + 1e-6 for op in w.openings):
                bad.append(f'{p.id} passes through {w.name} away from an opening')
        if x0 < rx0 - 1e-6 or x1 > rx1 + 1e-6 or y0 < ry0 - 1e-6 or y1 > ry1 + 1e-6:
            bad.append(f'{p.id} leaves {r.name}')
    floor = [p for p in c.placements if p.z - FLOOR_Z < .05]       # and no two of them in the same floor space
    for i, a in enumerate(floor):
        ax0, ax1, ay0, ay1 = footprint(a)
        for b in floor[i + 1:]:
            bx0, bx1, by0, by1 = footprint(b)
            if min(ax1, bx1) - max(ax0, bx0) > 1e-6 and min(ay1, by1) - max(ay0, by0) > 1e-6:
                bad.append(f'{a.id} overlaps {b.id}')
    for name, radius in (('Cairo', CAIRO['radius']), ('adult', HUMAN['radius'])):
        res = reachable(c, radius, start(c), goals(c))
        bad += [f'{name} cannot reach {g}' for g, ok in res.items() if not ok]
    # windows clear of partitions and doors, inside the ivory band
    for w in c.windows:
        if w.sill < BELT_Z or w.head > CEIL_SPRING - .05:
            bad.append(f'window {w.name} leaves the ivory band')
        for wall in c.walls:
            touches = wall.axis == 'y' and (wall.a1 >= IN - 1e-6 if w.side > 0 else wall.a0 <= -IN + 1e-6)
            if touches and wall.c1 > w.x - w.width / 2 - .05 and wall.c0 < w.x + w.width / 2 + .05:
                bad.append(f'window {w.name} meets {wall.name}')
        for name, side, x0, x1, *_ in exterior_openings(c):
            if side == w.side and x1 > w.x - w.width / 2 - .1 and x0 < w.x + w.width / 2 + .1:
                bad.append(f'window {w.name} meets {name}')
    return bad


def as_dict(c):
    d = asdict(c)
    d['frame'] = 'metres; x along the coach (end A -X, end B +X), y across (+Y compartment/galley side), z up from the top of the rail'
    return d


def envelope():
    names = ['LENGTH_OVER_BUFFERS', 'BODY_X', 'WIDTH', 'WALL', 'IN', 'IN_X', 'SKIRT_Z', 'FLOOR_Z', 'DECK', 'BELT_Z', 'CANT_Z',
             'ROOF_TOP', 'VENT_TOP', 'CEIL_SPRING', 'CEIL_APEX', 'CLEAR', 'SILL', 'HEAD', 'WIN_W', 'SMALL_W', 'WC_W', 'PART',
             'VEST', 'SPAN_X', 'DOOR_H', 'EXT_DOOR_W', 'EXT_DOOR_X', 'GANGWAY_W', 'GANGWAY_H', 'CORRIDOR', 'CABIN_W', 'BOGIE_X',
             'WHEELBASE', 'WHEEL_R', 'GAUGE', 'BUFFER_Y', 'BUFFER_Z']
    return {n: round(globals()[n], 4) for n in names}
