"""Worlds and scripted pad recipes for the ride oracle (ride_oracle.py).

A recipe is a list of timed events `(start_tick, end_tick, {field: value})` over a scenario of `length` ticks; a
field is `buttons` (Xbox bits, OR-ed), `lt`/`rt` (0..255), `lx`/`ly`/`rx`/`ry` (-32767..32767, up is +y). The pad
is neutral outside every event. Stance is regular unless a scenario says goofy. Native space: metres, x left, y up,
z forward; heading 0 rides toward +z.
"""
import math
import re

A, B, X, Y = 0x1000, 0x2000, 0x4000, 0x8000
LB, RB, LS, RS = 0x0100, 0x0200, 0x0040, 0x0080
TRANSFER = 0x0800
FULL = 32767

# The game's skate tuning (what the player feels); `stock` is the recovered default.
GAME = dict(difficulty='normal', goofy=False, trucks=0.5, pop=1.15, spin=1.6, speed=1.15, power=1.45, vert=1.0)
STOCK = dict(difficulty='normal', goofy=False, trucks=0.5, pop=1.0, spin=1.0, speed=1.0, power=1.0, vert=0.0)


# ---------------------------------------------------------------------------------------------------------- worlds
class Mesh:
    """Triangles are wound so that cross(b - a, c - a) is the outward normal, like the session's own fixtures."""
    def __init__(self):
        self.triangles, self.rails = [], []

    def tri(self, a, b, c, toward=None, away=None):
        n = cross(sub(b, a), sub(c, a))
        if dot(n, n) < 1e-10:
            return  # degenerate (the session rejects zero-area triangles)
        centre = [(a[i] + b[i] + c[i]) / 3 for i in range(3)]
        if toward is not None and dot(n, sub(toward, centre)) < 0:
            b, c = c, b
        if away is not None and dot(n, sub(centre, away)) < 0:
            b, c = c, b
        self.triangles.append([list(a), list(b), list(c)])

    def quad(self, a, b, c, d, toward=None, away=None):
        self.tri(a, b, c, toward, away)
        self.tri(a, c, d, toward, away)

    def ground(self, x0=-60, x1=60, z0=-60, z1=200, y=0.0, step=20):
        x = x0
        while x < x1:
            z = z0
            xa = min(x + step, x1)
            while z < z1:
                za = min(z + step, z1)
                p = (x, y, z), (x, y, za), (xa, y, za), (xa, y, z)
                self.quad(*p, toward=(x, y + 10, z))
                z = za
            x = xa

    def box(self, x0, x1, y0, y1, z0, z1):
        v = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
        centre = (0.5 * (x0 + x1), 0.5 * (y0 + y1), 0.5 * (z0 + z1))
        # v index: bit0 x, bit1 y, bit2 z
        for a, b, c, d in ((2, 6, 7, 3), (0, 1, 5, 4), (0, 4, 6, 2), (1, 3, 7, 5), (0, 2, 3, 1), (4, 5, 7, 6)):
            if a == 0 and b == 1 and y0 <= 0:
                continue  # bottom face on the ground
            self.quad(v[a], v[b], v[c], v[d], away=centre)

    def transition(self, x0, x1, z_start, radius, degrees, direction=1, extension=0.0, deck=3.0, chords=48,
                   coping=True):
        """A ramp rising from flat at z_start (toward +z when direction is 1), circular to `degrees`, then for a
        vertical wall `extension` metres of vert, a flat deck `deck` metres deep and coping on the lip."""
        profile = []
        for i in range(chords + 1):
            a = math.radians(degrees) * i / chords
            profile.append((z_start + direction * radius * math.sin(a), radius * (1 - math.cos(a))))
        if extension > 0:
            z, y = profile[-1]
            profile.append((z, y + extension))
        lip_z, lip_y = profile[-1]
        centre = (0.5 * (x0 + x1), radius, z_start)  # centre of curvature: the riding side
        for (za, ya), (zb, yb) in zip(profile, profile[1:]):
            toward = centre if yb < radius * 0.999 else (0.5 * (x0 + x1), yb, za - direction * 5)
            self.quad((x0, ya, za), (x0, yb, zb), (x1, yb, zb), (x1, ya, za), toward=toward)
        back = lip_z + direction * deck
        self.quad((x0, lip_y, lip_z), (x0, lip_y, back), (x1, lip_y, back), (x1, lip_y, lip_z),
                  toward=(0, lip_y + 10, lip_z))
        self.quad((x0, 0, back), (x0, lip_y, back), (x1, lip_y, back), (x1, 0, back),
                  toward=(0, lip_y * 0.5, back + direction * 5))
        for x in (x0, x1):  # side walls
            pts = [(x, y, z) for z, y in profile] + [(x, lip_y, back), (x, 0, back)]
            for p, q in zip(pts, pts[1:]):
                self.tri((x, 0, z_start), p, q, toward=(x + (-10 if x == min(x0, x1) else 10), lip_y * 0.5, lip_z))
        if coping:
            self.rails.append([[x0, lip_y, lip_z], [0.5 * (x0 + x1), lip_y, lip_z], [x1, lip_y, lip_z]])
        return lip_z, lip_y

    def world(self):
        return dict(triangles=self.triangles, rails=self.rails)


def sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def worlds():
    result = {}
    flat = Mesh()
    flat.ground()
    result['flat'] = flat.world()

    # Halfpipe: 8 m flat bottom from z=-4 to z=4, 3 m transitions to vertical, 0.4 m of vert, 3 m decks, coping.
    pipe = Mesh()
    pipe.ground(z0=-4, z1=4, x0=-8, x1=8, step=8)
    pipe.ground(x0=-60, x1=-8, z0=-60, z1=60)
    pipe.ground(x0=8, x1=60, z0=-60, z1=60)
    pipe.transition(-8, 8, 4, 3.0, 90, 1, extension=0.4)
    pipe.transition(-8, 8, -4, 3.0, 90, -1, extension=0.4)
    result['halfpipe'] = pipe.world()

    # Mini quarter pipe: 2.5 m radius to 60 degrees (1.25 m high), deck and coping, 16 m ahead of the spawn.
    quarter = Mesh()
    quarter.ground(z0=-60, z1=16)
    quarter.ground(z0=22, z1=200)
    quarter.ground(x0=-60, x1=-6, z0=16, z1=22, step=6)
    quarter.ground(x0=6, x1=60, z0=16, z1=22, step=6)
    quarter.transition(-6, 6, 16, 2.5, 60, 1, deck=3.0)
    result['quarter'] = quarter.world()

    # Rail: a 0.5 m high, 8 cm wide rail from z=8 to z=20 on the ride line (x=0).
    rail = Mesh()
    rail.ground()
    rail.box(-0.04, 0.04, 0, 0.5, 8, 20)
    rail.rails.append([[0, 0.5, 8], [0, 0.5, 14], [0, 0.5, 20]])
    result['rail'] = rail.world()

    # Ledge: a 0.45 m high, 0.6 m wide box from z=8 to z=22 whose right edge (x=-0.3 side faces the rider's
    # right) runs along x=0.3; both top edges are grindable.
    ledge = Mesh()
    ledge.ground()
    ledge.box(0.3, 0.9, 0, 0.45, 8, 22)
    ledge.rails.append([[0.3, 0.45, 8], [0.3, 0.45, 15], [0.3, 0.45, 22]])
    ledge.rails.append([[0.9, 0.45, 8], [0.9, 0.45, 15], [0.9, 0.45, 22]])
    result['ledge'] = ledge.world()

    # Kicker: a 0.5 m wedge over 1.6 m at z=10, flat landing beyond it.
    kicker = Mesh()
    kicker.ground()
    x0, x1, z0, z1, h = -1.5, 1.5, 10, 11.6, 0.5
    kicker.quad((x0, 0, z0), (x0, h, z1), (x1, h, z1), (x1, 0, z0))
    kicker.quad((x1, 0, z1), (x1, h, z1), (x0, h, z1), (x0, 0, z1))
    kicker.tri((x0, 0, z0), (x0, 0, z1), (x0, h, z1))
    kicker.tri((x1, 0, z0), (x1, h, z1), (x1, 0, z1))
    result['kicker'] = kicker.world()

    # Wall: 2 m high, 12 m wide, across the ride line at z=12.
    wall = Mesh()
    wall.ground()
    wall.box(-6, 6, 0, 2, 12, 12.5)
    result['wall'] = wall.world()

    # Platform: a 1 m high block to drop off (z from 0 to 6), for drops and landings.
    drop = Mesh()
    drop.ground()
    drop.box(-3, 3, 0, 1.0, -10, 6)
    result['drop'] = drop.world()
    drop3 = Mesh()
    drop3.ground()
    drop3.box(-3, 3, 0, 3.0, -14, 6)
    result['drop3'] = drop3.world()
    drop6 = Mesh()
    drop6.ground()
    drop6.box(-3, 3, 0, 6.0, -20, 6)
    result['drop6'] = drop6.world()
    return result


# --------------------------------------------------------------------------------------------------------- gestures
# Flick-It patterns from the package's gestures.skate (first pattern of each name), in conditioned pad coordinates
# with +y up (the recognizer itself works in y-down; GestureInputPublication negates y). Each pattern's tolerance is a
# radius of 0.35-0.55. The game reports the mirrored name for a regular rider (Kickflip <-> Heelflip, ...).
MAIN = {
    'Ollie': [(-0.246, -0.943), (0.371, 0.909)],
    'Kickflip': [(-0.029, -0.691), (0.909, 0.417)],
    'Heelflip': [(-0.291, -0.623), (-0.68, 0.714)],
    'PopShuvit': [(0.257, -0.943), (0.863, -0.451), (0.909, 0.36)],
    'VarialKickflip': [(-0.703, -0.703), (0.234, -0.954), (0.851, 0.509)],
    'InwardHeelflip': [(-0.714, -0.714), (0.211, -0.977), (-0.737, 0.646)],
    'FSPopShuvit': [(-0.2, -0.966), (-0.851, -0.52), (-0.943, 0.28)],
    'VarialHeelflip': [(0.726, -0.703), (-0.131, -0.977), (-0.497, 0.84)],
    'Hardflip': [(0.737, -0.669), (-0.143, -0.989), (0.6, 0.771)],
    '360PopShuvit': [(-0.874, -0.486), (0.166, -0.989), (0.954, -0.246)],
    '360Flip': [(-0.966, -0.269), (-0.497, -0.84), (0.211, -0.989), (0.909, 0.406)],
    '360InwardHeelflip': [(-0.977, -0.177), (-0.634, -0.76), (0.051, -0.977), (-0.497, 0.829)],
    'FS360PopShuvit': [(0.863, -0.486), (-0.166, -0.989), (-0.966, -0.257)],
    'Laserflip': [(1.0, -0.177), (0.657, -0.76), (0.04, -0.989), (-0.84, 0.486)],
    '360Hardflip': [(0.977, -0.177), (0.577, -0.817), (-0.12, -0.989), (0.703, 0.691)],
    'Nollie': [(-0.006, 0.989), (-0.006, -1.0)],
    'N_Kickflip': [(-0.017, 0.691), (0.714, -0.669)],
    'N_Heelflip': [(0.006, 0.691), (-0.737, -0.646)],
    'N_PopShuvit': [(0.269, 0.966), (0.931, 0.371), (0.84, -0.509)],
    'N_Hardflip': [(0.68, 0.726), (-0.223, 0.966), (0.749, -0.577)],
    'N_VarialHeelflip': [(0.691, 0.714), (-0.2, 0.966), (-0.44, -0.726)],
    'N_FSPopShuvit': [(-0.223, 1.0), (-0.92, 0.509), (-0.92, -0.44)],
    'N_VarialKickflip': [(-0.611, 0.794), (0.291, 0.943), (0.246, -0.817)],
    'N_InwardHeelflip': [(-0.623, 0.794), (0.314, 0.931), (-0.76, -0.646)],
    'N_FS360PopShuvit': [(0.954, 0.589), (-0.2, 0.886), (-1.0, 0.28)],
    'N_360Hardflip': [(0.989, 0.143), (0.634, 0.783), (-0.2, 0.977), (0.749, -0.566)],
    'N_Laserflip': [(0.954, 0.269), (0.509, 0.863), (-0.189, 0.726), (-0.737, -0.646)],
    'N_360PopShuvit': [(-0.863, 0.497), (0.177, 0.989), (0.943, 0.291)],
    'N_360Flip': [(-0.966, 0.2), (-0.554, 0.84), (0.097, 0.977), (0.851, -0.531)],
    'N_360InwardHeelflip': [(-0.954, 0.257), (-0.486, 0.863), (0.234, 0.966), (-0.84, -0.52)],
}
# Late flips in the air (no grab held): from a centred stick.
AIR = {
    'L_F_Kickflip': [(-0.006, -0.257), (-0.006, -0.977), (0.486, 0.863)],
    'L_F_Heelflip': [(-0.006, -0.257), (-0.006, -0.966), (-0.497, 0.863)],
    'L_B_Kickflip': [(0.006, 0.246), (-0.006, 1.0), (0.497, -0.851)],
    'L_B_Heelflip': [(0.006, 0.246), (-0.006, 1.0), (-0.497, -0.863)],
    'L_FS_Shuvit': [(-0.006, -0.246), (-0.017, -0.989), (-1.0, 0.017), (-0.486, 0.874)],
    'L_BS_Shuvit': [(-0.006, -0.246), (-0.017, -1.0), (1.0, 0.006), (0.497, 0.874)],
}
# While a grab trigger is held in the air.
FINGERFLIP = {
    'Fingerflip': [(-0.246, -0.977), (0.497, 0.874)],
    'FS_Varial': [(-0.006, -0.977), (0.863, -0.474), (0.897, 0.429)],
    'BS_Varial': [(-0.166, -0.989), (-0.851, -0.497), (-0.966, 0.349)],
}
# Left stick (with a grab trigger held around take-off): body flips.
LEFT = {
    'FrontFlip': [(-0.006, -0.154), (0.006, 1.0)],
    'BackFlip': [(-0.006, 0.143), (0.006, -1.0)],
}
MIRROR = {'Kickflip': 'Heelflip', 'PopShuvit': 'FSPopShuvit', 'VarialKickflip': 'VarialHeelflip',
          'Hardflip': 'InwardHeelflip', '360PopShuvit': 'FS360PopShuvit', '360Flip': 'Laserflip',
          '360Hardflip': '360InwardHeelflip'}
MIRROR.update({v: k for k, v in list(MIRROR.items())})


def regular_name(pattern):
    """The trick a regular rider gets from `pattern`."""
    prefix = 'N_' if pattern.startswith('N_') else ''
    base = pattern[len(prefix):]
    return prefix + MIRROR.get(base, base)


def slug(name):
    """'N_360Flip' -> 'nollie-360-flip', 'FSPopShuvit' -> 'fs-pop-shuvit', 'L_F_Kickflip' -> 'late-front-kickflip'."""
    name = name.replace('L_F_', 'LateFront').replace('L_B_', 'LateBack').replace('L_', 'Late').replace('N_', 'Nollie')
    name = name.replace('FS', 'Fs').replace('BS', 'Bs').replace('_', '')
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])', '-', name).lower()


def raw(point):
    """The raw stick value (-32767..32767) whose conditioned value (radial dead zone 0.25, x1.4286) is `point`."""
    x, y = point
    m = math.hypot(x, y)
    if m < 1e-6:
        return 0, 0
    length = 1.0 if m >= 0.999 else min(1.0, m / 1.4285714 + 0.25)
    return int(round(x / m * length * FULL)), int(round(y / m * length * FULL))


def gesture(at, points, stick='r', load=18, each=1, hold=2, full_load=True):
    """Hold the first point `load` ticks (pushed to full deflection when `full_load`, which is how the stick is
    loaded for a pop), then one point per `each` ticks, holding the last point `hold` extra ticks."""
    kx, ky = ('rx', 'ry') if stick == 'r' else ('lx', 'ly')
    first = points[0]
    if full_load:
        m = math.hypot(*first)
        first = (first[0] / m, first[1] / m)
    fx, fy = raw(first)
    events = [(at, at + load, {kx: fx, ky: fy})]
    t = at + load
    for i, p in enumerate(points[1:]):
        px, py = raw(p)
        extra = hold if i == len(points) - 2 else 0
        events.append((t, t + each + extra, {kx: px, ky: py}))
        t += each
    return events


def pop_tick(events):
    """The tick the last gesture point is first reached (the pop for a flick)."""
    return max(e[0] for e in events)


def flick(at, x, y, load=18, hold=3, depth=-FULL):
    """Right stick down for `load` ticks, then to raw (x, y) for `hold` ticks, from tick `at`."""
    return [(at, at + load, dict(ry=depth)), (at + load, at + load + hold, dict(rx=x, ry=y))]


def polar(degrees, magnitude=FULL):
    """Raw stick position at `degrees` clockwise from up (0 up, 90 right, 180 down, 270 left)."""
    a = math.radians(degrees)
    return int(round(magnitude * math.sin(a))), int(round(magnitude * math.cos(a)))


def arc(start, stop, steps, magnitude=FULL):
    return [polar(start + (stop - start) * i / (steps - 1), magnitude) for i in range(steps)]


def ollie(at, load=18):
    return flick(at, 0, FULL, load=load, hold=2)


def ride(speed, heading=0.0):
    return (speed * math.sin(heading), 0.0, speed * math.cos(heading))


# --------------------------------------------------------------------------------------------------------- recipes
def expand(case):
    pads = []
    for t in range(case['length']):
        pad = dict(buttons=0, lt=0, rt=0, lx=0, ly=0, rx=0, ry=0)
        for start, end, fields in case['events']:
            if start <= t < end:
                for key, value in fields.items():
                    if key == 'buttons':
                        pad['buttons'] |= value
                    else:
                        pad[key] = value
        pads.append((pad['buttons'], pad['lt'], pad['rt'], pad['lx'], pad['ly'], pad['rx'], pad['ry']))
    return pads


CASES = []


def case(name, group, events, length, world='flat', velocity=(0, 0, 0), spawn=(0, 0, 0), heading=0.0, tune=None,
         note='', **extra):
    CASES.append(dict(name=name, group=group, events=events, length=length, world=world,
                      velocity=[round(v, 4) for v in velocity], spawn=list(spawn), heading=round(heading, 6),
                      tune=dict(tune or GAME), note=note, **extra))


def all_cases():
    if not CASES:
        define()
    return CASES


# Clips dumped frame by frame (key bones in root space) to see what the clips themselves carry.
CLIPS_TO_DUMP = [
    'R_ANTIC_OLLIE_N_0_INTO', 'OLLIE_HIGH_G', 'OLLIE_HIGH_A', 'IA_IDLE_N_N_0_CYC', 'R_IDLE_HCOM_000',
    'KICKFLIP_IN_HIGH_G', 'KICKFLIP_IN_HIGH_A', 'T_KICKFLIP_HI_4FLIPS_0_OUT1',
    '360FLIP_D_HIGH_G', '360FLIP_D_HIGH_A', 'T_360FLIP_H_CYC', 'POPSHUVIT_HIGH_A', 'L_HCOM_HIMP_3',
]

# Tick at which scripted tricks start on flat ground: the launch velocity puts the rider in a short "Bumped" state
# (about ticks 2-50), so loads begin at 60 and the pop lands at 78.
AT = 60
P = AT + 24  # flat-ground ollie from AT: flick at P - 6, wheels off about P + 6
GOOFY = dict(GAME, goofy=True)


def define():
    # ---------------------------------------------------------------- standing, pushing, speed
    case('stand/idle', 'stand', [], 180, note='Standing still on flat ground: hips over deck, stance')
    case('push/hold-a', 'push', [(30, 900, dict(buttons=A))], 960, note='Hold A from rest: push cadence and top speed')
    case('push/hold-x-mongo', 'push', [(30, 900, dict(buttons=X))], 960, note='Hold X from rest: mongo push')
    case('push/tap-a', 'push', [(30 + 60 * i, 34 + 60 * i, dict(buttons=A)) for i in range(10)], 720,
         note='Tap A once a second')
    case('push/hold-a-stock', 'push', [(30, 900, dict(buttons=A))], 960, tune=STOCK, note='Stock tuning')
    case('push/hold-a-goofy', 'push', [(30, 300, dict(buttons=A))], 360, tune=GOOFY, note='Goofy stance push')
    case('push/hold-a-from-5', 'push', [(60, 600, dict(buttons=A))], 660, velocity=(0, 0, 5),
         note='Hold A while already rolling at 5 m/s')
    for speed in (2, 5, 9):
        case(f'coast/{speed}', 'coast', [], 600, velocity=(0, 0, speed), note='Coast: rolling resistance')
    # ---------------------------------------------------------------- braking, powerslides, reverts
    for speed in (4, 8):
        case(f'brake/b/{speed}', 'brake', [(AT, 400, dict(buttons=B))], 420, velocity=(0, 0, speed),
             note='Hold B: foot brake')
        for side, lx in (('left', -1), ('right', 1)):
            case(f'powerslide/{side}/{speed}', 'powerslide', [(AT, 180, dict(lx=lx * 19660, ly=-26214))], 300,
                 velocity=(0, 0, speed), note='Left stick full down-left / down-right, held: powerslide')
            case(f'powerslide/{side}/{speed}/tap', 'powerslide', [(AT, AT + 12, dict(lx=lx * 19660, ly=-26214))],
                 240, velocity=(0, 0, speed), note='Left stick down-left / down-right for 12 ticks')
    for side, sign in (('left', -1), ('right', 1)):
        half = arc(180 - sign * 90, 180 + sign * 90, 9)  # half circle through down, starting at the side
        case(f'revert/{side}', 'revert', [(AT, AT + 30, dict(lx=sign * 19660, ly=-26214))] +
             [(AT + 30 + i * 2, AT + 32 + i * 2, dict(lx=x, ly=y)) for i, (x, y) in enumerate(half)], 240,
             velocity=(0, 0, 6), note='Powerslide, then the left stick swept through a half circle: revert')
    # ---------------------------------------------------------------- steering, kick turns
    for speed in (2, 5, 9):
        for fraction in (0.25, 0.5, 0.75, 1.0):
            for side, sign in (('left', -1), ('right', 1)):
                case(f'steer/{side}/{speed}/{fraction}', 'steer',
                     [(30, 210, dict(lx=int(sign * fraction * FULL)))], 240, velocity=(0, 0, speed),
                     note='Left stick held sideways: carving yaw rate', speed=speed, stick=sign * fraction)
    for speed in (0, 1.5, 3):
        for side, sign in (('left', -1), ('right', 1)):
            case(f'kickturn/{side}/{speed}', 'kickturn', [(AT, AT + 60, dict(lx=sign * FULL))], 180,
                 velocity=(0, 0, speed), note='Left stick sideways at low speed: kick turn', speed=speed)
    # ---------------------------------------------------------------- ollies
    for speed in (0, 3, 6, 9):
        case(f'ollie/{speed}', 'ollie', ollie(AT), 240, velocity=(0, 0, speed),
             note='Right stick down 18 ticks then up: ollie', speed=speed)
    case('ollie/6/stock', 'ollie', ollie(AT), 240, velocity=(0, 0, 6), tune=STOCK, speed=6)
    case('ollie/6/goofy', 'ollie', ollie(AT), 240, velocity=(0, 0, 6), tune=GOOFY, speed=6)
    case('ollie/6/fakie', 'ollie', ollie(AT), 240, velocity=(0, 0, -6), speed=6, note='Rolling backwards: fakie ollie')
    for load in (4, 10, 40):
        case(f'ollie/6/load{load}', 'ollie', ollie(AT, load=load), 240, velocity=(0, 0, 6), speed=6,
             note=f'Load (stick down) for {load} ticks before the flick')
    case('ollie/6/slow-flick', 'ollie', [(AT, AT + 18, dict(ry=-FULL))] +
         [(AT + 18 + i, AT + 19 + i, dict(ry=int(-FULL + 2 * FULL * (i + 1) / 8))) for i in range(8)] +
         [(AT + 26, AT + 28, dict(ry=FULL))], 240, velocity=(0, 0, 6), speed=6,
         note='Stick swept from down to up over 8 ticks: slow flick (lower GestureSpeed)')
    case('nollie/6', 'ollie', gesture(AT, MAIN['Nollie']), 240, velocity=(0, 0, 6),
         note='Right stick up then down: nollie', speed=6)
    case('ollie/6/hold-crouch', 'ollie', [(AT - 30, AT + 18, dict(lt=200))] + ollie(AT), 240, velocity=(0, 0, 6),
         speed=6, note='Crouched (trigger at 200) before the pop')
    # ---------------------------------------------------------------- flip tricks: every main-set gesture
    for pattern, points in MAIN.items():
        if pattern in ('Ollie', 'Nollie'):
            continue
        name = slug(regular_name(pattern))
        case(f'flip/{name}', 'flip', gesture(AT, points), 240, velocity=(0, 0, 6), pattern=pattern,
             note=f'Flick-It pattern {pattern} (a regular rider gets {regular_name(pattern)})')
    kick = MAIN['Heelflip']  # a regular rider's kickflip
    for speed in (0, 3, 9):
        case(f'flip/kickflip/speed{speed}', 'flip', gesture(AT, kick), 240, velocity=(0, 0, speed), pattern='Heelflip')
    case('flip/kickflip/stock', 'flip', gesture(AT, kick), 240, velocity=(0, 0, 6), tune=STOCK, pattern='Heelflip')
    case('flip/kickflip/goofy', 'flip', gesture(AT, MAIN['Kickflip']), 240, velocity=(0, 0, 6), tune=GOOFY,
         pattern='Kickflip', note='Goofy rider: the unmirrored pattern names hold')
    case('flip/kickflip/fakie', 'flip', gesture(AT, kick), 240, velocity=(0, 0, -6), pattern='Heelflip',
         note='Rolling backwards')
    case('flip/kickflip/slow', 'flip', gesture(AT, [kick[0]] + [(kick[0][0] + (kick[1][0] - kick[0][0]) * i / 6,
                                                              kick[0][1] + (kick[1][1] - kick[0][1]) * i / 6)
                                                             for i in range(1, 7)]), 240,
         velocity=(0, 0, 6), pattern='Heelflip', note='The kickflip flick spread over 6 ticks: lower GestureSpeed')
    case('flip/kickflip/darkcatch-b', 'flip', gesture(AT, kick) + [(AT + 24, AT + 70, dict(buttons=B))], 240,
         velocity=(0, 0, 6), note='Kickflip, then hold B while it flips: dark catch')
    case('flip/kickflip/darkcatch-rb', 'flip', gesture(AT, kick) + [(AT + 24, AT + 70, dict(buttons=RB))], 240,
         velocity=(0, 0, 6), note='Kickflip, then hold RB while it flips')
    case('flip/kickflip/underflip', 'flip', gesture(AT, kick) + gesture(AT + 26, MAIN['Kickflip'], load=4), 240,
         velocity=(0, 0, 6), note='A second, opposite flick while the kickflip spins: underflip')
    case('flip/kickflip/double', 'flip', gesture(AT, kick) + gesture(AT + 26, kick, load=4), 240,
         velocity=(0, 0, 6), note='The same flick again while flipping')
    case('flip/kickflip/kicker', 'flip', gesture(KICK_POP - 20, kick), 300, world='kicker', spawn=KICK_SPAWN,
         velocity=(0, 0, KICK_SPEED), note='Kickflip off the kicker: longer air')
    case('flip/360-flip/kicker', 'flip', gesture(KICK_POP - 21, MAIN['Laserflip']), 300, world='kicker',
         spawn=KICK_SPAWN, velocity=(0, 0, KICK_SPEED))
    # ---------------------------------------------------------------- late flips, fingerflips, body flips
    # A flat-ground ollie from AT leaves the ground at about P + 6 and lands about P + 58.
    for pattern, points in AIR.items():
        case(f'late/{slug(pattern)}', 'late', ollie(AT) + gesture(P + 12, points, load=2, full_load=False),
             240, velocity=(0, 0, 6), pattern=pattern, note=f'Ollie, then air pattern {pattern} early in the air')
    for pattern, points in FINGERFLIP.items():
        for trigger in ('lt', 'rt'):
            # The FINGERFLIP intent is raised during the grab's Into; the graph only takes it from the grab cycle.
            for name, at in (('', P + 14), ('/in-cycle', P + 24)):
                case(f'fingerflip/{slug(pattern)}/{trigger}{name}', 'fingerflip',
                     ollie(AT) + [(P + 8, P + 50, {trigger: 255})] + gesture(at, points, load=2, full_load=False),
                     240, velocity=(0, 0, 6), pattern=pattern,
                     note='Grab trigger held in the air, then a right-stick pattern')
    for pattern, points in LEFT.items():
        for trigger in ('lt', 'rt'):
            case(f'bodyflip/{slug(pattern)}/{trigger}', 'bodyflip',
                 ollie(AT) + [(P + 6, P + 56, {trigger: 255})] +
                 gesture(P + 7, points, stick='l', load=2, full_load=False), 240, velocity=(0, 0, 6),
                 pattern=pattern, note='Grab trigger held from take-off, left stick flicked: front / back flip')
            case(f'bodyflip/{slug(pattern)}/{trigger}/halfpipe', 'bodyflip',
                 [(VERT_LIP, VERT_LIP + 60, {trigger: 255})] +
                 gesture(VERT_LIP + 2, points, stick='l', load=2, full_load=False), 600, world='halfpipe',
                 velocity=(0, 0, 10), pattern=pattern, note='The same in the first vert air of the halfpipe')
    # ---------------------------------------------------------------- body spins
    for side, sign in (('left', -1), ('right', 1)):
        for hold in (10, 20, 30, 45):
            case(f'spin/{side}/hold{hold}', 'spin', ollie(AT) + [(AT + 12, AT + 18 + hold, dict(lx=sign * FULL))],
                 240, velocity=(0, 0, 6), hold=hold,
                 note=f'Left stick {side} from 6 ticks before the pop, held {hold} ticks after it: body spin')
        case(f'spin/{side}/kickflip-hold30', 'spin', gesture(AT, kick) + [(AT + 12, AT + 48, dict(lx=sign * FULL))],
             240, velocity=(0, 0, 6), note='Kickflip with a body spin')
        case(f'spin/{side}/stock-hold30', 'spin', ollie(AT) + [(AT + 12, AT + 48, dict(lx=sign * FULL))], 240,
             velocity=(0, 0, 6), tune=STOCK)
    # ---------------------------------------------------------------- manuals
    for name, ry in (('manual', -16000), ('nose-manual', 16000), ('manual-light', -9000),
                     ('manual-deep', -24000), ('manual-full', -FULL)):
        case(f'manual/{name}', 'manual', [(AT, 240, dict(ry=ry))], 330, velocity=(0, 0, 5),
             note='Right stick partly down (manual) / up (nose manual), held')
    for name, lx in (('lean-left', -12000), ('lean-right', 12000)):
        case(f'manual/{name}', 'manual', [(AT, 240, dict(ry=-16000, lx=lx))], 330, velocity=(0, 0, 5),
             note='Manual with the left stick leaning: balance')
    case('manual/from-ollie', 'manual', ollie(AT) + [(AT + 30, 260, dict(ry=-16000))], 330, velocity=(0, 0, 5),
         note='Ollie, then hold the manual input into the landing')
    # ---------------------------------------------------------------- ground grabs, hippy jump, step off, bails
    case('ground/boneless', 'ground', [(AT, AT + 30, dict(lt=255)), (AT + 10, AT + 14, dict(buttons=X))], 240,
         velocity=(0, 0, 5), note='Left trigger fully in (ground grab), then X: boneless')
    case('ground/boneless-rt', 'ground', [(AT, AT + 30, dict(rt=255)), (AT + 10, AT + 14, dict(buttons=X))], 240,
         velocity=(0, 0, 5), note='Right trigger fully in (ground grab), then X')
    case('ground/fastplant', 'ground', [(AT, AT + 30, dict(rt=255)), (AT + 10, AT + 14, dict(buttons=A))], 240,
         velocity=(0, 0, 5), note='Right trigger fully in, then A: fastplant')
    case('ground/fastplant-lt', 'ground', [(AT, AT + 30, dict(lt=255)), (AT + 10, AT + 14, dict(buttons=A))], 240,
         velocity=(0, 0, 5), note='Left trigger fully in, then A')
    case('ground/hippy-ollie', 'ground', [(AT - 10, AT + 40, dict(buttons=A))] + ollie(AT), 240, velocity=(0, 0, 5),
         note='A held through an ollie')
    case('ground/hippy-jump', 'ground', [(AT, AT + 6, dict(buttons=A | X))], 240, velocity=(0, 0, 5),
         note='A and X together: hippy jump')
    case('ground/step-off-rolling', 'ground', [(AT, AT + 4, dict(buttons=Y)), (AT + 120, AT + 124, dict(buttons=Y))],
         300, velocity=(0, 0, 5), note='Y: step off the board while rolling, Y again: step back on')
    case('ground/step-off-still', 'ground', [(AT, AT + 4, dict(buttons=Y)), (AT + 120, AT + 124, dict(buttons=Y))],
         300, note='Y while standing still')
    case('bail/deliberate', 'bail', [(AT, AT + 40, dict(lt=255, rt=255)), (AT + 8, AT + 14, dict(buttons=LS | RS)),
                                     (AT + 150, AT + 154, dict(buttons=A))], 360, velocity=(0, 0, 5),
         note='Both triggers held, then both sticks clicked: bail on purpose; A to get back up')
    case('bail/deliberate-air', 'bail', ollie(AT) + [(P + 6, P + 40, dict(lt=255, rt=255)),
                                                    (P + 12, P + 18, dict(buttons=LS | RS))], 360,
         velocity=(0, 0, 5), note='The same in the air of an ollie')
    for speed in (3, 5, 7, 8, 9, 10):
        case(f'bail/wall/{speed}', 'bail', [], 300, world='wall', spawn=(0, 0, 12 - speed * 1.5),
             velocity=(0, 0, speed), note='Roll straight into a 2 m wall', speed=speed)
    for side, sign in (('left', -1), ('right', 1)):
        for hold in (12, 13, 14, 15, 16, 17, 18, 20):
            case(f'bail/land-sideways/{side}/{hold}', 'bail', ollie(AT) + [(AT + 12, AT + 12 + hold,
                                                                           dict(lx=sign * FULL))],
                 240, velocity=(0, 0, 6), note='Ollie with a partial body spin: land rotated')
    for speed in (3, 5):
        case(f'bail/rail-cross/{speed}', 'bail', [], 240, world='rail', spawn=(-3 * speed / 3, 0, 14),
             heading=math.pi / 2, velocity=ride(speed, math.pi / 2),
             note='Roll across the rail without popping')
        case(f'bail/rail-cross-ollie/{speed}', 'bail', ollie(AT), 240, world='rail',
             spawn=(-(speed * (AT + 18 + 20) / 60), 0, 14), heading=math.pi / 2, velocity=ride(speed, math.pi / 2),
             note='Ollie over the rail at 90 degrees')
        case(f'bail/rail-land-across/{speed}', 'bail', ollie(AT), 240, world='rail',
             spawn=(-(speed - 0.3) * (AT + 78) / 60, 0, 14), heading=math.pi / 2, velocity=ride(speed, math.pi / 2),
             note='Ollie timed so the board comes down across the rail')
    for height, world in ((1, 'drop'), (3, 'drop3'), (6, 'drop6')):
        for speed in (3, 6):
            case(f'drop/{height}m/{speed}', 'drop', [], 300, world=world, spawn=(0, height, 6 - speed * 1.2),
                 velocity=(0, 0, speed), note=f'Roll off a {height} m drop')
            case(f'drop/{height}m/{speed}/ollie', 'drop', ollie(AT), 300, world=world,
                 spawn=(0, height, 6 - speed * (AT + 18) / 60 - 0.3), velocity=(0, 0, speed),
                 note=f'Ollie off a {height} m drop at the edge')
    # ---------------------------------------------------------------- grabs (flat-ground ollie)
    tweak = P + 14
    for name, events in (
            ('bs-lt', [(P + 8, P + 46, dict(lt=255))]),
            ('fs-rt', [(P + 8, P + 46, dict(rt=255))]),
            ('christ-air', [(P + 8, P + 46, dict(lt=255)), (P + 11, P + 46,
                                                                          dict(buttons=B))]),
            ('christ-air-rt', [(P + 8, P + 46, dict(rt=255)), (P + 11, P + 46,
                                                                             dict(buttons=B))]),
            ('one-foot-a', [(P + 8, P + 46, dict(lt=255)), (P + 14, P + 42,
                                                                          dict(buttons=A))]),
            ('one-foot-x', [(P + 8, P + 46, dict(rt=255)), (P + 14, P + 42,
                                                                          dict(buttons=X))]),
            ('double', [(P + 8, P + 46, dict(lt=255, rt=255))]),
            ('superman', [(P + 8, P + 46, dict(lt=255, rt=255)),
                          (P + 11, P + 46, dict(buttons=B))]),
            ('coffin', [(P + 8, P + 46, dict(lt=255, rt=255)),
                        (P + 11, P + 46, dict(buttons=A | X))]),
            ('tuck-knee', [(P + 8, P + 46, dict(rt=255)), (tweak, P + 46, dict(rx=-FULL))]),
            ('stiffy', [(P + 8, P + 46, dict(rt=255)), (tweak, P + 46, dict(rx=FULL))]),
            ('nosebone', [(P + 8, P + 46, dict(rt=255)), (tweak, P + 46, dict(ry=FULL))]),
            ('tailbone', [(P + 8, P + 46, dict(rt=255)), (tweak, P + 46, dict(ry=-FULL))]),
            ('japan', [(P + 8, P + 46, dict(lt=255)), (tweak, P + 46, dict(ry=-FULL))]),
            ('crossbone', [(P + 8, P + 46, dict(lt=255)), (tweak, P + 46, dict(rx=-FULL))]),
            ('method', [(P + 8, P + 46, dict(lt=255)), (tweak, P + 46, dict(rx=FULL))]),
            ('melon', [(P + 8, P + 46, dict(lt=255)), (tweak, P + 46, dict(ry=FULL))]),
            ('tail-grab', [(P + 7, P + 46, dict(ry=FULL)), (P + 11, P + 46, dict(rt=255))]),
            ('seatbelt', [(P + 7, P + 46, dict(ry=FULL)), (P + 11, P + 46, dict(lt=255))]),
            ('nose-grab', [(P + 7, P + 46, dict(ry=-FULL)), (P + 11, P + 46,
                                                                          dict(lt=255))]),
            ('crail', [(P + 7, P + 46, dict(ry=-FULL)), (P + 11, P + 46, dict(rt=255))]),
            ('rocket', [(P + 7, P + 46, dict(ry=-FULL)), (P + 11, P + 46,
                                                                       dict(lt=255, rt=255))]),
            ('mute', [(P + 7, P + 46, dict(rx=-FULL)), (P + 11, P + 46, dict(lt=255))]),
            ('stale', [(P + 7, P + 46, dict(rx=-FULL)), (P + 11, P + 46, dict(rt=255))]),
            ('bs-lt-short', [(P + 8, P + 18, dict(lt=255))]),
            ('bs-lt-late-release', [(P + 8, P + 80, dict(lt=255))]),
            ('bs-lt-half', [(P + 8, P + 46, dict(lt=128))])):
        case(f'grab/{name}', 'grab', ollie(AT) + events, 240, velocity=(0, 0, 6),
             note='Ollie on flat ground at 6 m/s and grab (trigger after take-off; board-adjust grabs set the right '
                  'stick first)')
    case('air/kicker-ollie', 'air', ollie(KICK_POP - 20), 300, world='kicker', spawn=KICK_SPAWN,
         velocity=(0, 0, KICK_SPEED), note='Ollie at the lip of the kicker, no grab')
    case('air/kicker-roll', 'air', [], 300, world='kicker', spawn=KICK_SPAWN, velocity=(0, 0, KICK_SPEED),
         note='Roll off the kicker without popping')
    case('air/kicker-ollie-early', 'air', ollie(KICK_POP - 30), 300, world='kicker', spawn=KICK_SPAWN,
         velocity=(0, 0, KICK_SPEED), note='Ollie 10 ticks before the lip')
    # ---------------------------------------------------------------- grinds and slides
    for pop in (96, 102, 108, 114):
        case(f'grind/rail/pop{pop}', 'grind', ollie(pop - 18), 360, world='rail', spawn=(0, 0, -4),
             velocity=(0, 0, 5), note='Ride along the rail line and ollie onto it', pop=pop)
    for offset in (0.1, 0.2, 0.3, 0.4, 0.5, 0.7):
        for sign, side in ((1, 'left'), (-1, 'right')):
            case(f'grind/rail/offset-{side}{offset}', 'grind-snap', ollie(RAIL_POP - 18), 360, world='rail',
                 spawn=(sign * offset, 0, -4), velocity=(0, 0, 5), offset=sign * offset,
                 note='Ollie parallel to the rail, offset sideways: lateral snap tolerance')
    for degrees in (10, 20, 30, 45, 60):
        for sign, side in ((1, 'from-left'), (-1, 'from-right')):
            h = -sign * math.radians(degrees)  # heading toward the rail
            # Cross the rail line at z=10 about when a straight approach starts grinding (pop + 57 ticks).
            d = 4.6 * (RAIL_POP + 57) / 60
            spawn = (sign * d * math.sin(math.radians(degrees)), 0, 10 - d * math.cos(math.radians(degrees)))
            case(f'grind/rail/angle-{side}{degrees}', 'grind-angle', ollie(RAIL_POP - 18), 360, world='rail',
                 spawn=tuple(round(v, 3) for v in spawn), heading=h, velocity=ride(5, h), degrees=degrees,
                 note='Ollie onto the rail approaching at an angle: snap angle and grind choice')
    for name, fields in (('right-down', dict(ry=-16000)), ('right-up', dict(ry=16000)),
                         ('right-left', dict(rx=-20000)), ('right-right', dict(rx=20000)),
                         ('left-up', dict(ly=FULL)), ('left-down', dict(ly=-FULL)),
                         ('left-left', dict(lx=-FULL)), ('left-right', dict(lx=FULL)),
                         ('both-up', dict(ly=FULL, ry=FULL)), ('both-forward', dict(lx=FULL, rx=FULL))):
        case(f'grind/rail/hold-{name}', 'grind-input', ollie(RAIL_POP - 18) + [(RAIL_POP + 8, 300, fields)], 360,
             world='rail', spawn=(0, 0, -4), velocity=(0, 0, 5), note='Ollie onto the rail, then hold a stick')
    for side, sign in (('left', -1), ('right', 1)):
        for hold in (10, 16, 22):
            case(f'grind/rail/spin-{side}{hold}', 'grind-slide',
                 ollie(RAIL_POP - 18) + [(RAIL_POP - 6, RAIL_POP - 6 + hold, dict(lx=sign * FULL))], 360,
                 world='rail', spawn=(0, 0, -4), velocity=(0, 0, 5), hold=hold,
                 note='Ollie onto the rail with a body spin: board/lip slides')
    for speed in (3, 7):
        case(f'grind/rail/speed{speed}', 'grind', ollie(RAIL_POP - 18 - (5 if speed > 5 else -10)), 360,
             world='rail', spawn=(0, 0, -4 + (2 if speed < 5 else -4)), velocity=(0, 0, speed), speed=speed)
    case('grind/rail/stock', 'grind', ollie(RAIL_POP - 18), 360, world='rail', spawn=(0, 0, -4), velocity=(0, 0, 5),
         tune=STOCK)
    case('grind/rail/goofy', 'grind', ollie(RAIL_POP - 18), 360, world='rail', spawn=(0, 0, -4), velocity=(0, 0, 5),
         tune=GOOFY)
    case('grind/rail/kickflip-in', 'grind', gesture(RAIL_POP - 18, kick), 360, world='rail', spawn=(0, 0, -4),
         velocity=(0, 0, 5), note='Kickflip onto the rail')
    case('grind/rail/ollie-out', 'grind', ollie(RAIL_POP - 18) + ollie(RAIL_POP + 60), 360, world='rail',
         spawn=(0, 0, -4), velocity=(0, 0, 5), note='Ollie onto the rail, ollie off it a second later')
    for x in (0.1, 0.2, 0.3, 0.45):
        case(f'grind/ledge/x{x}', 'grind', ollie(RAIL_POP - 18), 360, world='ledge', spawn=(0.3 - x, 0, -4),
             velocity=(0, 0, 5), x=x, note='Ollie onto the ledge edge from beside it (ledge on the rider\'s left)')
    for side, sign in (('left', -1), ('right', 1)):
        case(f'grind/ledge/spin-{side}16', 'grind-slide',
             ollie(RAIL_POP - 18) + [(RAIL_POP - 6, RAIL_POP + 10, dict(lx=sign * FULL))], 360, world='ledge',
             spawn=(0.1, 0, -4), velocity=(0, 0, 5), note='Ollie onto the ledge with a body spin')
    for name, fields in (('right-down', dict(ry=-16000)), ('right-up', dict(ry=16000))):
        case(f'grind/ledge/hold-{name}', 'grind-input', ollie(RAIL_POP - 18) + [(RAIL_POP + 8, 300, fields)], 360,
             world='ledge', spawn=(0.1, 0, -4), velocity=(0, 0, 5))
    # ---------------------------------------------------------------- transitions, vert, transfers
    case('halfpipe/coast', 'transition', [], 900, world='halfpipe', velocity=(0, 0, 7),
         note='Coast across the halfpipe from the middle at 7 m/s')
    case('halfpipe/pump', 'transition', [(i, i + 20, dict(lt=200)) for i in range(15, 1200, 75)], 1200,
         world='halfpipe', velocity=(0, 0, 6), note='Pump (left trigger at 200, under a ground grab) every 75 ticks')
    case('halfpipe/pump-both', 'transition', [(i, i + 20, dict(lt=200, rt=200)) for i in range(15, 1200, 75)], 1200,
         world='halfpipe', velocity=(0, 0, 6), note='Pump with both triggers')
    case('halfpipe/pump-stick', 'transition', [(i, i + 30, dict(ry=-23000)) for i in range(15, 1200, 75)], 1200,
         world='halfpipe', velocity=(0, 0, 6), note='Load the right stick on the transitions')
    case('halfpipe/vert-air', 'vert', [], 900, world='halfpipe', velocity=(0, 0, 10),
         note='10 m/s into a vert wall: straight air out and back in')
    case('halfpipe/vert-air-12', 'vert', [], 900, world='halfpipe', velocity=(0, 0, 12), note='12 m/s')
    case('halfpipe/vert-ollie', 'vert', ollie(VERT_LIP - 18), 900, world='halfpipe', velocity=(0, 0, 10),
         note='Ollie at the lip of vert')
    for name, fields in (('bs-lt', dict(lt=255)), ('fs-rt', dict(rt=255)),
                         ('christ-air', dict(lt=255, buttons=B)), ('one-foot', dict(lt=255, buttons=A))):
        case(f'halfpipe/grab-{name}', 'vert', [(VERT_LIP + 6, VERT_LIP + 40, fields)], 900, world='halfpipe',
             velocity=(0, 0, 10), note='Grab in the first vert air')
    for side, sign in (('left', -1), ('right', 1)):
        case(f'halfpipe/spin-{side}', 'vert', [(VERT_LIP - 6, VERT_LIP + 30, dict(lx=sign * FULL))], 900,
             world='halfpipe', velocity=(0, 0, 10), note='Left stick sideways through the first vert air')
    case('halfpipe/transfer', 'vert', [(VERT_LIP - 4, VERT_LIP + 40, dict(buttons=TRANSFER, ly=FULL))], 900,
         world='halfpipe', velocity=(0, 0, 10), note='Transfer button and left stick forward in the vert air')
    case('halfpipe/kickflip', 'vert', gesture(VERT_LIP - 18, kick), 900, world='halfpipe', velocity=(0, 0, 10),
         note='Kickflip at the vert lip')
    case('quarter/air', 'transition', [], 400, world='quarter', velocity=(0, 0, 7),
         note='7 m/s into a 60 degree quarter pipe')
    case('quarter/air-grab', 'transition', [(QUARTER_LIP + 6, QUARTER_LIP + 40, dict(lt=255))], 400, world='quarter',
         velocity=(0, 0, 7))


# Calibrated from air/kicker-roll, grind/rail/pop*, halfpipe/vert-air and quarter/air (see the reference).
KICK_SPAWN = (0, 0, -6)
KICK_SPEED = 8
KICK_POP = 140   # a flick at KICK_POP - 2 pops on the kicker's lip (the board leaves it at about 146)
RAIL_POP = 108   # pop tick that lands the board on the rail from z=-4 at 5 m/s
VERT_LIP = 62    # tick the board leaves the vert lip at 10 m/s from the middle
QUARTER_LIP = 130
