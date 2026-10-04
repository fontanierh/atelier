# megapark_ride_film.py: runs inside the game (atelier live py - < this file). This line keeps the bridge from taking
# the code for a file name: Unreal's Python reads any text whose first .py is followed by a space as a script path.
"""Mega Park Ride film: the Ride skating backend (skate.Backend Ride) through the Mega Park. A push-off and hard carves
on the park road, flat-ground flips (kickflip, heelflip, pop shove-it, 360 flip, varial kickflip, hardflip) and a
sketchy catch, a powerslide down the ramp, manuals on the plaza, a long 50-50, a boardslide and a 5-0 down the plaza
parapet, the drop-in off the upper deck into a big Indy over the pool's west wall, quarter-pipe airs that come back down
into the pool's north wall (Melon 180, a Christ air with a slow-motion replay, a 360), a transition line in the capsule
bowl (a roll-in over the coping, then airs back and forth between its outer wall and the spine, from the floor should
the roll-in run out of speed: a Melon 180 coming down forward, an Indy coming down fakie, a 360, a Christ air, with a
slow-motion replay of the one that turned the most) and a 50-50 on its coping from the deck back into the bowl, three
ragdoll bails (an Indy held into the landing on the pool's west wall, a kickflip on the road at speed come down on one
foot, a 50-50 down the parapet and an Indy held down the plaza's step into a slam), each with the get-up where the body
came to rest and a slow-motion replay the mixer can play (from the road bail he gets up on foot, recalls the board to
his hand with the board button and runs with it), and a clean final line (kickflip, crooked grind, 360 flip). Two
optional shots open with a run and a caveman onto the board and end with a grab dismount to the feet; they run only when
the game has those transitions. The trick cameras keep the rider about 40% of the frame's height (CLOSE metres across at
his pelvis), aimed at the physical body with a lead on its motion.

    atelier play --set 'performance=1;render_scale=100;desktop=1;show_fps=0' yorimichi -- -RenderOffscreen -ForceRes
    atelier live py "TAKE='take1'" && atelier live py - < games/yorimichi/scenarios/megapark_ride_film.py
    ... wait for build/yorimichi/megapark/ride-film/<take>/done.json, then:
    python games/yorimichi/scenarios/megapark_ride_film_mix.py build/yorimichi/megapark/ride-film/<take>

Optional globals, set with `atelier live py` before the script:
    TAKE      the take's folder name (take1)
    OUTDIR    the take folder itself, to write into another checkout's build/
    ONLY      the shots to run, by name (rehearsals)
    REHEARSE  True: no screenshots; done.json still reports every shot
    TUNE      {'shot': {'field': value}}: overrides of the shot table
    EXTRAS    True or False, or {'caveman': bool, 'dismount': bool}: force the optional shots on or off; by default
              each runs when the skate state's moves= word lists it (caveman, airdismount). The game prints that word
              once the rider has been on the board, so without it the run starts with a moment on the board, unrecorded
    FLIP      degrees added to every board placement, should the board face against the launch
    PHYSICAL  skate.RidePhysical for the take: True (the default) films the active ragdoll rider, False the animated one;
              done.json logs the cvar as the game reads it
    CLOSE     metres across the frame at the rider for every camera without its own width (4.3: about 40% of the height)
    TIGHT     the width factor of the cameras that set their own width (.82)
    RECALL    False: the road bail gets up back onto the board instead of on foot with the board recalled to the hand

Runs in the game's Python (the live bridge) at a fixed 60 Hz step, 90 Hz for the slow-motion shots. Every board shot is
placed, settles for a second unrecorded, is launched and then ridden by scripted skate. input: pursuit steering along a
line with push and brake holds, timed events and position triggers (Flick-It gestures, grabs, spins, grind sticks). Each
shot records into its own folder (parts/NN_name): a JPG every second 60 Hz frame (30 fps), the camera, and the board's
loops per frame; the sounds the game starts are stamped with the shot's own frame clock (AUDIO_BASE * (k + 1) plus the
frame; unrecorded frames stamp -1000000). A slow shot saves every 90 Hz frame, so the mixer can replay its biggest air
(a line's most turned), or its bail, at a third of the speed. A transition air's camera widens to hold the lip, the top
of the air and the wall below the lip with the rider; a lip air's spin is measured from the board's SkateDeck mesh about
the take-off's up. A shot with `retry` that is not kept (a roll-in or a quarter-pipe air that does not come back into
the transition, a floor line without three airs back in) runs again from its start; the floor line runs only when the
roll-in ran out of speed before its fourth air. done.json logs each air: its take-off and landing face, point, slope and
stance, the speed there and on the flat before and after, the trick, a bail, and whether it came back into the
transition. An optional shot that does not do what it should (no caveman, no dismount) is marked keep=false and left out
of the cut. done.json logs each bail's entry speed, how far the body went, how low it lay (the state's lie=), how long
it was down and, around the get-up, the largest move in one tick of the pelvis and of the board's deck while it shows (a
pop), and each fade of the board (shown=); the part's shot.json keeps the bail's body log, every tick from the bail to
BODY_AFTER s after the get-up. megapark_ride_film_mix.py cuts the parts into the film and mixes the sound.
"""
import json, math, os, re, shutil, traceback
import unreal

L = live.L
MV = unreal.MegaParkValidation
TAKE = globals().get('TAKE', 'take1')
ONLY = globals().get('ONLY')
REHEARSE = bool(globals().get('REHEARSE', False))
TUNE = globals().get('TUNE') or {}
EXTRAS = globals().get('EXTRAS')
FLIP = float(globals().get('FLIP', 0.))
TIGHT = float(globals().get('TIGHT', .82))       # the width factor of a camera with its own `frame`
CLOSE = float(globals().get('CLOSE', 4.3))       # m across at the rider: Cairo is 1.2 m on the board, .85 m tucked
MIN_FOV = 8.
RECALL = bool(globals().get('RECALL', True))     # the road bail ends on foot with the board recalled to the hand
PHYSICAL = bool(globals().get('PHYSICAL', True))
OUT = globals().get('OUTDIR') or os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'),
                                              'yorimichi/megapark/ride-film', TAKE)
os.makedirs(OUT, exist_ok=True)
shutil.rmtree(os.path.join(OUT, 'parts'), ignore_errors=True)
for f in os.listdir(OUT):
    if f in ('done.json', 'audio.json', 'progress.txt', 'error.txt', 'shots.json'):
        os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
cm = unreal.GameplayStatics.get_player_camera_manager(L.game_world(), 0)
UNRECORDED = -1000000
AUDIO_BASE = 1000000
NEUTRAL_LOOPS = '0 1 0 1 0 1 0 1 0 1'
G_AIR = 14.                     # Ride's air gravity (m/s^2); each air measures its own (a lip air may fall slower)
VERT_DZ = float(globals().get('VERT_DZ', 1.2))   # m below its lip that a lip air comes back down onto the wall


# ------------------------------------------------------------------------------------------------ geometry
def ue(x, y, z):
    return unreal.Vector(x * 100., -y * 100., z * 100.)


def wrap(a):
    return (a + 180.) % 360. - 180.


def yaw_to(x, y, tx, ty):
    """UE yaw from (x, y) towards (tx, ty), island metres."""
    return math.degrees(math.atan2(-(ty - y), tx - x))


def ground_z(x, y, probe):
    """The first surface under (x, y) below probe + 20 m (island metres)."""
    return L.ground_at(ue(x, y, probe)).z / 100.


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def flat(v, n):
    """v projected onto the plane normal to the unit n, normalised (None when v is along n)."""
    k = dot(v, n); w = (v[0] - k * n[0], v[1] - k * n[1], v[2] - k * n[2]); m = math.sqrt(dot(w, w))
    return (w[0] / m, w[1] / m, w[2] / m) if m > 1e-6 else None


def slope_of(up):
    return round(math.degrees(math.acos(max(-1., min(1., up[2])))), 1) if up else None


class Pipe:
    """A straight channel between two transitions facing each other: u along it, k across it from the first coping
    (k grows towards the far wall); `faces` names the side of the middle an air leaves from."""

    def __init__(self, origin, heading, width, faces=('near wall', 'far wall')):
        self.o = origin; h = math.radians(heading)
        self.u = (math.cos(h), math.sin(h)); self.n = (math.sin(h), -math.cos(h)); self.w = width; self.faces = faces

    def at(self, u, k):
        return (self.o[0] + self.u[0] * u + self.n[0] * k, self.o[1] + self.u[1] * u + self.n[1] * k)

    def uk(self, x, y):
        dx, dy = x - self.o[0], y - self.o[1]
        return dx * self.u[0] + dy * self.u[1], dx * self.n[0] + dy * self.n[1]

    def face(self, x, y, z=None):
        return self.faces[0] if self.uk(x, y)[1] < self.w / 2. else self.faces[1]


def pursue(way, k, x, y, look):
    """Pure pursuit on a polyline of (x, y, want): the nearest point from segment k on, then `look` metres further."""
    best = (1e9, k, 0.)
    for j in range(k, min(k + 4, len(way) - 1)):
        ax, ay = way[j][:2]; bx, by = way[j + 1][:2]; dx, dy = bx - ax, by - ay; ll = dx * dx + dy * dy
        u = max(0., min(1., ((x - ax) * dx + (y - ay) * dy) / ll)); d = math.hypot(ax + dx * u - x, ay + dy * u - y)
        if d < best[0] - .01: best = (d, j, u)
    _, j, u = best
    rest = look; jj, uu = j, u
    while True:
        ax, ay = way[jj][:2]; bx, by = way[jj + 1][:2]; seg = math.hypot(bx - ax, by - ay); left_ = seg * (1 - uu)
        if rest <= left_ or jj + 2 >= len(way):
            uu = min(1., uu + rest / seg); break
        rest -= left_; jj += 1; uu = 0.
    ax, ay = way[jj][:2]; bx, by = way[jj + 1][:2]
    return ax + (bx - ax) * uu, ay + (by - ay) * uu, way[j + 1][2], j


# The plaza parapet's inner edge (grind line 0), every 5 m from its south end; the plaza is on its right (inward)
# side going north. It runs on north and west along the road; the film grinds its last 25 m southward to the end.
RAIL0 = [(-68.80, 1372.26, 118.91), (-71.13, 1376.69, 118.91), (-73.20, 1381.23, 118.90), (-74.98, 1385.91, 118.92),
         (-76.45, 1390.68, 118.97), (-77.59, 1395.55, 119.08), (-78.36, 1400.49, 119.26), (-78.74, 1405.47, 119.53),
         (-78.73, 1410.47, 119.93), (-78.47, 1415.46, 120.49), (-78.18, 1420.46, 121.25)]


def rail_at(s, line=RAIL0):
    """Point and unit tangent (north-going) on the parapet line (or another line of points 5 m apart) at s metres
    from its start."""
    s = max(0., min(s, 5. * (len(line) - 1) - 1e-6)); i = int(s // 5); u = s / 5. - i
    a, b = line[i], line[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy)
    return (a[0] + dx * u, a[1] + dy * u, a[2] + (b[2] - a[2]) * u), (dx / n, dy / n)


def rail_offset(s, d):
    """A plan point d metres inside (plaza side) the parapet line at s."""
    p, t = rail_at(s)
    return p[0] + t[1] * d, p[1] - t[0] * d


def rail_lateral(x, y, line=RAIL0):
    """(s, signed distance inward (right of the line's way), tangent) of the nearest point of the parapet line."""
    best = None
    for i in range(len(line) - 1):
        a, b = line[i], line[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; ll = dx * dx + dy * dy
        u = max(0., min(1., ((x - a[0]) * dx + (y - a[1]) * dy) / ll))
        px, py = a[0] + dx * u, a[1] + dy * u; d = math.hypot(x - px, y - py)
        if best is None or d < best[0]:
            n = math.sqrt(ll); t = (dx / n, dy / n)
            best = (d, 5. * (i + u), ((x - px) * t[1] - (y - py) * t[0]), t)
    return best[1], best[2], best[3]


def pop_height(load):
    """Ride's ollie height (m) after the stick rested `load` seconds on the rim (PopHeightScale 1.15)."""
    return (150.8 - 80.4 * math.exp(-max(0., load - .067) / .16)) / 100.


# ------------------------------------------------------------------------------------------------ the state
def parse(text):
    """The live skate state: the component's debug words, the line, the counters and the actor position."""
    head = text.split(' | ')[0]
    d = dict(re.findall(r'(\w+)=(\S+)', head))
    m = re.search(r' \| combo=(.*?) \| last=(.*?) landed=(-?\d+) bails=(-?\d+) grinds=(-?\d+) score=(-?\d+)', text)
    if m:
        d['combo'], d['last'] = m.group(1).strip(), m.group(2).strip()
        d['landed'], d['bails'], d['grinds'], d['score'] = (int(m.group(k)) for k in range(3, 7))
    return d


class Ctx:
    """What a shot sees each frame (island metres, m/s, UE yaw degrees)."""


def observe(s):
    text = L.skate_state(); d = parse(text); c = Ctx()
    c.text, c.d = text, d
    c.t = s['t']
    c.mode = int(d.get('mode', 0)); c.retail = d.get('retail', ''); c.backend = d.get('backend', '')
    c.zb = float(d.get('z', 0.)) / 100.
    c.manual, c.slide, c.fakie, c.switch = d.get('manual') == '1', d.get('slide') == '1', d.get('fakie') == '1', d.get('switch') == '1'
    c.combo, c.last = d.get('combo', ''), d.get('last', '')
    c.landed, c.bails, c.grinds, c.score = (d.get(k, 0) for k in ('landed', 'bails', 'grinds', 'score'))
    p = L.player(); loc = p.get_actor_location(); v = p.get_velocity()
    c.x, c.y, c.za = loc.x / 100., -loc.y / 100., loc.z / 100.
    c.vx, c.vy, c.vz = v.x / 100., -v.y / 100., v.z / 100.
    c.spd = math.hypot(c.vx, c.vy)
    c.yaw = math.degrees(math.atan2(v.y, v.x)) if c.spd > .5 else p.get_actor_rotation().yaw
    c.hx, c.hy, c.hz, c.hsrc = c.x, c.y, c.za, 'actor'    # the physical pelvis (the ragdoll's body in a bail), else the actor
    for key in ('hips', 'hip'):
        try:
            hx, hy, hz = (float(n) for n in d[key].split(','))
            c.hx, c.hy, c.hz, c.hsrc = hx / 100., -hy / 100., hz / 100., key; break
        except (KeyError, ValueError): pass
    c.hdi = math.atan2(c.vy, c.vx) if c.spd > .5 else -math.radians(p.get_actor_rotation().yaw)
    c.v3 = math.sqrt(c.spd * c.spd + c.vz * c.vz)
    c.axes = deck_axes()
    c.slope = slope_of(c.axes[1]) if c.axes else None
    return c


def deck_axes():
    """The board's forward and up (island axes) from its SkateDeck mesh, or None. A vert air turns the board about a
    level axis, where the state line's yaw (a rotator's) says nothing: the spin is measured from these."""
    d = st.get('deck')
    if d is False: return None
    for again in (False, True):
        if d is None or again:
            d = next((m for m in L.player().get_components_by_class(unreal.StaticMeshComponent) if m.get_name() == 'SkateDeck'), None)
            st['deck'] = d if d is not None else False
            if d is None: return None
        try:
            f, u = d.get_forward_vector(), d.get_up_vector()
            return (f.x, -f.y, f.z), (u.x, -u.y, u.z)
        except Exception:
            d = None
    st['deck'] = False
    return None


def air_t(s, c):
    a = s['air']
    return c.t - a['t0'] if a and c.mode == 2 else -1.


def air_g(a):
    return a.get('g') or G_AIR


def time_to_land(s, c):
    """Seconds until the board falls back to its take-off height (`land_dz` below it; a lip air VERT_DZ below it)."""
    a = s['air']
    if not a: return 0.
    g = air_g(a)
    h = c.zb - a['z0'] + s.get('land_dz', VERT_DZ if a['lip'] else 0.)
    return (c.vz + math.sqrt(max(0., c.vz * c.vz + 2. * g * h))) / g


# ------------------------------------------------------------------------------------------------ input effects
def flick(name, load=.2, **kw):
    """A Flick-It gesture: its first point held `load` s (the crouch), the others a 30th of a second each (live.FLICKS,
    or NOLLIES for a name there)."""
    return dict(kind='flick', name=name, load=load, **kw)


# Native's nollie gestures (gestures.skate, "main": N_*) in live.FLICKS' frame (x right, y up, regular stance): the
# stick up first, onto the nose. Some wind up only part-way out (N_Kickflip at 0.69).
NOLLIES = {
    'nollie_kickflip': [(0.02, 0.69), (-0.71, -0.67)],
    'nollie_heelflip': [(-0.01, 0.69), (0.74, -0.65)],
    'nollie_shove': [(-0.27, 0.97), (-0.93, 0.37), (-0.84, -0.51)],
    'nollie_varial_kickflip': [(0.61, 0.79), (-0.29, 0.94), (-0.25, -0.82)],
    'nollie_360_flip': [(0.97, 0.2), (0.55, 0.84), (-0.1, 0.98), (-0.85, -0.53)],
}


def hold(secs=None, until=None, **inputs):
    return dict(kind='hold', secs=secs, until=until, inputs=inputs)


def spin(to=None, until=None, dir=1., mag=1.):
    """In the air: turn with the left stick until the spin (the board's measured turn: about the take-off's up in a
    lip air, else the state line's yaw) will reach `to` degrees by the landing, or until it has turned `until`."""
    return dict(kind='spin', to=to, until=until, dir=dir, mag=mag)


def grab(which, release=.35):
    """In the air: hold a grab ('indy', 'melon', 'christ', 'one_foot', 'tuck') until `release` s before the landing
    (None: into the landing)."""
    return dict(kind='grab', which=which, release=release)


def stick(x, y):
    """From the air: hold the right stick (a grind's kind at lock-on) until a moment after the lock-on."""
    return dict(kind='stick', right=(x, y))


GRABS = {'indy': {'grab_right': True}, 'melon': {'grab_left': True}, 'christ': {'grab_left': True, 'brake': True},
         'one_foot': {'grab_right': True, 'push': True}, 'tuck': {'grab_right': True, 'left': (0., -.85)}}


def activate(s, c, spec):
    e = dict(spec); e['start'] = c.t; e['air'] = False
    s['effects'].append(e)


def apply_effect(s, c, e, inp):
    """Shape this frame's inputs; returns False when the effect is over."""
    k = e['kind']; u = c.t - e['start']
    if k == 'flick':
        pts = NOLLIES.get(e['name']) or live.FLICKS[e['name']]
        if e.get('mirror'): pts = [(-x, y) for x, y in pts]          # the other foot forward (switch)
        if u < e['load']: inp['right'] = pts[0]
        else:
            j = 1 + int((u - e['load']) * 30. + 1e-6)
            if j > len(pts):
                # Then the left stick stays neutral until the air it pops is over: native reads it through the pop's
                # wind-up (GroundAnimation) into the air's spin, so steering there turns the board in the air.
                if c.mode == 2: e['popped'] = True
                elif e.get('popped') or u > e['load'] + len(pts) / 30. + .8: return False
                if not any(x['kind'] == 'spin' for x in s['effects']): inp['left'] = e.get('left', (0., 0.))
                return True
            inp['right'] = pts[j] if j < len(pts) else (0., 0.)
        inp['left'] = e.get('left', (0., 0.)); inp['push'] = inp['brake'] = False
        return True
    if k == 'hold':
        if e['secs'] is not None and u >= e['secs']: return False
        if e['until'] is not None and e['until'](s, c): return False
        inp.update(e['inputs']); return True
    if k == 'stick':                                 # from the air until just after the lock-on (a pop can land on the
        if c.mode == 2: e['air'] = True              # ledge's top first and lock a moment later)
        if not e['air']: return u < 3.
        if c.mode == 3: e.setdefault('lock', c.t)
        if (e.get('lock') is not None and c.t > e['lock'] + .2) or u > 2.5: return False
        if c.mode != 1: inp['right'] = e['right']          # not on the ground: there it would be a manual
        return True
    # The air effects wait for an air and end with it.
    if c.mode == 2 and s['air']: e['air'] = True
    elif e['air']: return False
    else: return u < 3.
    a = s['air']
    if k == 'spin':
        if e['until'] is not None: go = abs(a['spin']) < e['until']
        else:
            # The turn so far, and what Ride's controller still turns by the landing should the stick go now. Once let
            # go, a lip air comes down on the nearer of forward and fakie by itself (Ride's landing alignment, native's
            # known air), so the stick goes back only for a turn more than SPIN_SLACK short.
            if a['lip'] and a.get('dprev') is not None: done = a['dturn']     # the deck's own turn
            else: done = a['turned'] if a.get('yaw') is not None else a['spin']
            short = e['to'] - abs(done) - e['dir'] * spin_left(s['spin_ctl'], time_to_land(s, c))
            go = short > (SPIN_SLACK if a['lip'] and e.get('let_go') else 0.)
            if go: e['pushed'] = True; e['let_go'] = False
            elif e.get('pushed'): e['let_go'] = True
        if go: inp['left'] = (e['dir'] * e['mag'], inp['left'][1])
        return True
    if k == 'grab':
        if e['release'] is None or time_to_land(s, c) > e['release']: inp.update(GRABS[e['which']])
        return True
    return False


SPIN_SCALE = 1.6           # the game's AirSpinScale (Config/DefaultGame.ini): the spin preference
TICK = 1. / 60.            # Ride's step
# Ride's spin controller (RideSession.cpp: ReadSpinStick and TickSpin, native's PhysicalBodySpin in its normal mode), by
# the time in the air (s): the rate at full stick (rad/s, before the preference) and the most it changes in a tick
# (rad/s); and the snap's weight by the age of the stick's push (s, negative before the take-off), over the last
# SPIN_TICKS ticks.
SPIN_PROP = ((0., 3.15), (.052, 6.364), (.127, 7.779), (.244, 7.939), (.368, 7.714), (.564, 6.975), (.906, 5.689),
             (2., 3.664))
SPIN_DELTA = ((0., .993), (.116, .761), (.256, .507), (.394, .35), (.533, .225), (.678, .171), (.878, .157), (1., .154))
SPIN_SNAP = ((-.497, 0.), (-.375, .05), (-.254, 1.), (0., 1.), (.135, 1.), (.228, .629), (.337, .386), (.5, .286))
SPIN_TICKS = 30
SPIN_SLACK = 45.           # degrees short of its spin a lip air's stick goes back for, once let go


def board_yaw(c):
    """The board's yaw from the state line (None when it has none)."""
    try: return float(c.d['yaw'])
    except (KeyError, TypeError, ValueError): return None


def curve(pts, x):
    """Ride's Curve: piecewise linear through `pts`, flat beyond its ends."""
    if x <= pts[0][0]: return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1: return y0 + (y1 - y0) * (x - x0) / max(1e-4, x1 - x0)
    return pts[-1][1]


def spin_stick(left):
    """The stick's x as the spin reads it (native's ConditionStick): its length less a quarter over three quarters (at
    most 1) along its direction, so a stick within a quarter of the centre spins nothing, a half-pushed one a third."""
    n = math.hypot(left[0], left[1])
    return 0. if n < .001 else left[0] * max(0., min(1., (n - .25) / .75)) / n


def spin_ctl():
    """The spin controller's state as a ride starts (Ride clears it on every mount)."""
    return {'in': 0., 'smooth': 0., 'filt': 0., 'clock': 0., 'peak': 0., 'hist': [0.] * SPIN_TICKS, 'at': 0,
            'rate': 0., 'acc': 0., 'tick': None}


def spin_tick(k, x, air):
    """One Ride tick of the controller `k` with the conditioned stick `x`; returns the rate (deg/s, the stick's way).
    Every tick keeps the stick's push (its change x1.5 while it moves outward); on the ground the air's clock waits and
    the stick is smoothed. In the air the rate follows the stick x SPIN_PROP x the preference, weighed by the snap (the
    sharpest push from SPIN_TICKS before the take-off on, by its age: .4 to 1), and changes by at most SPIN_DELTA x the
    preference a tick (.2 x it back against the turn); a released stick fades out, 4% a tick. Two parts need what
    the film cannot see and are left out (Ride's own spin=, spin_sync, has them): the take-off carries a little of the
    ground's turn, and a lip air turns to the nearer of forward and fakie by its landing once the stick is let go."""
    ch = 1.5 * (x - k['in']); k['in'] = x
    k['filt'] = max(-1., min(1., ch if ch * x > .1 else 0.))
    k['hist'][k['at']] = k['filt']; k['at'] = (k['at'] + 1) % SPIN_TICKS
    if not air:
        k['clock'] = 0.; k['smooth'] = .8 * k['smooth'] + .2 * x; k['rate'] = 0.
        return 0.
    if k['clock'] == 0.:                     # the take-off: the snap so far
        k['peak'] = 0.
        for i in range(1, SPIN_TICKS):
            w = curve(SPIN_SNAP, -i * TICK) * k['hist'][(k['at'] - i) % SPIN_TICKS]
            if abs(w) > abs(k['peak']): k['peak'] = w
    accel = curve(SPIN_DELTA, k['clock']) * SPIN_SCALE
    snap = curve(SPIN_SNAP, k['clock']) * k['filt']
    if abs(snap) > abs(k['peak']): k['peak'] = snap
    k['clock'] += TICK
    if abs(k['in']) < 1.5e-5: k['smooth'] *= .96; k['in'] = k['smooth']
    else: k['smooth'] = .8 * k['smooth'] + .2 * k['in']
    prop = curve(SPIN_PROP, k['clock']) * SPIN_SCALE * k['in']
    if prop * k['peak'] < 0.: k['peak'] = 0.
    target = (abs(k['peak']) * .6 + .4) * prop          # rad/s, the stick's way (native turns against it)
    old = math.radians(k['rate'])
    lim = min(.2 * SPIN_SCALE, accel)
    lo, hi = (-accel, lim) if old < 0. else (-lim, accel)
    k['rate'] = math.degrees(old + max(lo, min(hi, target - old)))
    return k['rate']


def spin_left(k, tl):
    """The turn (degrees, the stick's way) Ride's controller `k` still makes in `tl` s should the stick go now."""
    k = dict(k, hist=list(k['hist'])); left = 0.
    for _ in range(int(round(max(0., tl) / TICK))):
        left += spin_tick(k, 0., True) * TICK
    return left


def spin_sync(s, c):
    """Before the frame's input, in the air, when the state has them (Ride's spin=, the turn since the take-off, and
    tick=): the air's spin, and a tick on the controller's rate."""
    k = s.setdefault('spin_ctl', spin_ctl()); a = s['air'] if c.mode == 2 else None
    try: total, tick = float(c.d['spin']), int(c.d['tick'])
    except (KeyError, TypeError, ValueError):
        k['tick'] = None
        return
    # The last frame's stick, stepped once for every tick Ride took with it (Ride's own phase, not an accumulator's).
    pending = k.pop('pending', None)
    if k['tick'] is not None and pending is not None:
        x, was_air = pending
        for _ in range(max(0, tick - k['tick'])): spin_tick(k, x, was_air)
    if a is not None:
        if k['tick'] is not None and tick == k['tick'] + 1 and a.get('ride_spin') is not None:
            k['rate'] = (total - a['ride_spin']) / TICK
        a['rate'] = k['rate']
        a['spin'] = a['ride_spin'] = total
    k['tick'] = tick


def spin_model(s, c, inp, dt):
    """Ride's spin controller stepped through the frame with its stick (spin_tick, a tick each 60th of a second), on
    the ground too, where the stick's push before a take-off weighs the air's rate; in the air its rate turns the
    air's `spin` (Ride's own once spin_sync reads it)."""
    k = s.setdefault('spin_ctl', spin_ctl()); a = s['air'] if c.mode == 2 else None
    x = spin_stick(inp['left'])
    if k['tick'] is not None:
        # On Ride, spin_sync steps this stick once the state says how many ticks took it.
        k['pending'] = (x, a is not None)
        return
    k['acc'] += dt / TICK; n = int(k['acc'] + 1e-6); k['acc'] -= n
    for _ in range(n):
        r = spin_tick(k, x, a is not None)
        if a is not None: a['rate'] = r; a['spin'] += r * TICK


def plan_air(s, c, a):
    """A transition line's trick for this lip air: the first of the shot's `plan` not done yet whose stance (None:
    either) is the one he climbed in and whose least air time the climb gives (2 vz / g, g the vert guess `vert_g`);
    else a straight Indy, which turns the stance round for the next wall. A straight air comes back down fakie, a 180
    forward, a 360 fakie again."""
    left = s.setdefault('plan_left', list(s['plan']))
    T = 2. * max(0., c.vz) / s.get('vert_g', 10.)
    trick = next((p for p in left if p.get('stance') in (None, a['off']['stance']) and T >= p.get('T', 0.)), None)
    if trick is None: trick = {'name': 'indy (between)', 'grab': 'indy'}
    else: left.remove(trick)
    a['plan'] = {'name': trick['name'], 'T': round(T, 2), 'stance': a['off']['stance']}
    fx = [grab(trick['grab'], trick.get('release', .3))] if trick.get('grab') else []
    if trick.get('spin'): fx.append(spin(to=trick['spin'], dir=trick.get('dir', 1.)))
    return fx


def back_in(a):
    """An air that came back into the transition: rolling away from a landing on a slope below its lip, no bail."""
    on = a.get('on') or {}
    return a['to'] == 1 and not a.get('bail') and (on.get('slope') or 0.) > 12. and (on.get('at') or [0, 0, 1e9])[2] < a['z0'] - .1


def line_done(s, c):
    """A transition line ends 1.4 s after the landing of its last planned air, 2.5 s after a bail, or 1.2 s after a
    climb that turns back down its wall short of the lip (the line has run out of speed)."""
    if s['bail_t'] is not None: return c.t > s['bail_t'] + 2.5
    if c.mode == 1 and (c.slope or 0.) > 25.:
        if c.vz > .5: s['climb'] = True
        elif c.vz < -.5 and s.get('climb'): s['climb'] = False; s.setdefault('stall_wall_t', c.t)
    elif c.mode != 1: s['climb'] = False
    if s.get('stall_wall_t') is not None and c.t > s['stall_wall_t'] + 1.2: return True
    planned = [a for a in s['airs'] if a.get('plan') and not a['plan']['name'].endswith('(between)')]
    return len(planned) == len(s['plan']) and c.t > planned[-1]['t1'] + 1.4


def came_back(s, c):
    """A quarter-pipe air is kept when it came back into the transition and rode away."""
    return not s['d_bails'] and any(back_in(a) for a in s['airs'])


def line_kept(s, c):
    """A transition line is kept with at least three airs back into the transition and no bail."""
    return not s['d_bails'] and sum(1 for a in s['airs'] if back_in(a)) >= 3


# ------------------------------------------------------------------------------------------------ cameras
CAM = {'i': -1, 'spec': None, 'p': None, 'aim': None, 'h': None, 't0': 0.}


def chase(back=3., side=0., up=.9, frame=None, turn=2.5, follow=6., follow_z=4., aim_up=0., agl=.5):
    """A follow camera on the travel's heading (frozen in the air and in a bail): `back` behind (negative: ahead,
    looking back), `side` to the right of the travel, `up` above the rider; the field of view keeps `frame` metres
    (x TIGHT) across at the rider, by default CLOSE."""
    return dict(kind='chase', back=back, side=side, up=up, frame=frame, turn=turn, follow=follow, follow_z=follow_z,
                aim_up=aim_up, agl=agl)


def fixed(at, frame=None, fov=None, aim_k=6., aim_up=0., to=None, over=6., keep=False, slide=None, rise=0.):
    """A camera standing at `at` ((x, y, z), or (x, y, probe z, height above the ground)) that turns to follow the
    rider; `frame` metres (x TIGHT) across at the rider (by default CLOSE), or a set `fov`. With `to`, it travels there
    over `over` seconds. keep=True widens the frame through a transition air so it holds the lip, the top of the air
    and the wall below the lip where it comes back in, with the rider, from the climb to after the landing. slide=
    ((x, y) unit axis, share): the eye moves along the axis by that share of the rider's move along it; rise: by that
    share of the rider's height above the eye's ground."""
    return dict(kind='fixed', at=at, frame=frame, fov=fov, aim_k=aim_k, aim_up=aim_up, to=to, over=over, keep=keep,
                slide=slide, rise=rise)


ASPECT = 16. / 9.


def keep_points(s, c):
    """The points a keep camera holds besides the rider: a lip air's lip, its top (with the body above the board)
    and the wall VERT_DZ + .7 m below the lip, from the climb towards it until .8 s after its landing."""
    a = s['air'] if c.mode == 2 else None
    if a is None and s['airs'] and s['airs'][-1].get('lip') and c.t < s['airs'][-1]['t1'] + .8: a = s['airs'][-1]
    if a is not None and a.get('lip'):
        g = air_g(a); top = a['z0'] + max(0., a.get('vz_ref', a['vz0'])) ** 2 / (2. * g)
        return [(a['x0'], a['y0'], a['z0']), (a['x0'], a['y0'], max(top, a['zmax']) + 1.3),
                (a['x0'], a['y0'], a['z0'] - VERT_DZ - .7)]
    if c.mode == 1 and c.vz > 2.5 and (c.slope or 0.) > 25.:      # climbing a wall fast: the air to come
        return [(c.hx, c.hy, c.zb + c.vz * c.vz / (2. * 10.) + 1.3), (c.hx, c.hy, c.zb - 1.)]
    return []


def keep_frame(eye, pts, base_fov):
    """The aim point and horizontal field of view that hold `pts` (the first is the rider) from `eye`, at least
    base_fov wide."""
    dirs = []
    for p in pts:
        d = (p[0] - eye[0], p[1] - eye[1], p[2] - eye[2])
        dirs.append((math.atan2(d[1], d[0]), math.atan2(d[2], math.hypot(d[0], d[1])), math.sqrt(dot(d, d))))
    y0 = dirs[0][0]
    yaws = [y0 + math.atan2(math.sin(d[0] - y0), math.cos(d[0] - y0)) for d in dirs]; pits = [d[1] for d in dirs]
    yc, pc_ = (max(yaws) + min(yaws)) / 2., (max(pits) + min(pits)) / 2.
    span = max(max(yaws) - min(yaws), (max(pits) - min(pits)) * ASPECT)
    fov = max(base_fov, math.degrees(span) * 1.18 + 5.)
    r = dirs[0][2]
    aim = (eye[0] + r * math.cos(pc_) * math.cos(yc), eye[1] + r * math.cos(pc_) * math.sin(yc), eye[2] + r * math.sin(pc_))
    return aim, min(fov, 90.)


def resolve(at):
    if len(at) == 4: return (at[0], at[1], ground_z(at[0], at[1], at[2]) + at[3])
    return tuple(at)


def camera(s, c, dt):
    cams = s['cams']; i = max(CAM['i'] if CAM.get('shot') == s['k'] else 0, 0)
    for j in range(i + 1, len(cams)):
        cond = cams[j][0]
        if (cond(s, c) if callable(cond) else c.t >= cond): i = j
    spec = cams[i][1]; fresh = CAM.get('shot') != s['k'] or CAM['i'] != i
    if fresh:
        new_shot = CAM.get('shot') != s['k']
        CAM.update(shot=s['k'], i=i, spec=spec, t0=c.t, h=c.hdi, p=None, aim=None)
        if new_shot: CAM.update(body=None, bv=[0., 0., 0.])
        if spec['kind'] == 'fixed':
            CAM['from'] = resolve(spec['at']); CAM['dest'] = resolve(spec['to']) if spec.get('to') else None
            CAM['ground'] = CAM['from'][2] - (spec['at'][3] if len(spec['at']) == 4 else 0.)
            CAM['fov'] = None
            if spec.get('slide') or spec.get('rise'):
                CAM['slid'] = [0., 0.]
    # The body's velocity, smoothed, leads the aim by the aim's own lag, so a long lens keeps a fast rider centred.
    body = (c.hx, c.hy, c.hz)
    if CAM.get('body') is not None:
        raw = [(body[n] - CAM['body'][n]) / dt for n in range(3)]
        if math.dist(body, CAM['body']) > 3. or c.hsrc != CAM.get('hsrc'): raw = [0., 0., 0.]   # a placement or another body
        CAM['bv'] = [CAM['bv'][n] + (raw[n] - CAM['bv'][n]) * (1. - math.exp(-8. * dt)) for n in range(3)]
    CAM['body'], CAM['hsrc'] = body, c.hsrc
    rider = (c.hx, c.hy, c.hz + spec.get('aim_up', 0.))
    if spec['kind'] == 'chase':
        if c.mode not in (2, 4) and c.spd > 1.:
            CAM['h'] += math.atan2(math.sin(c.hdi - CAM['h']), math.cos(c.hdi - CAM['h'])) * (1. - math.exp(-spec['turn'] * dt))
        h = CAM['h']; ch, sh = math.cos(h), math.sin(h)
        want = [c.hx - spec['back'] * ch + spec['side'] * sh, c.hy - spec['back'] * sh - spec['side'] * ch, c.hz + spec['up']]
        if CAM['p'] is None: CAM['p'] = list(want)
        k, kz = 1. - math.exp(-spec['follow'] * dt), 1. - math.exp(-spec['follow_z'] * dt)
        p = CAM['p']; p[0] += (want[0] - p[0]) * k; p[1] += (want[1] - p[1]) * k; p[2] += (want[2] - p[2]) * kz
        floor = ground_z(p[0], p[1], p[2] - 19.5) + spec['agl']
        if p[2] < floor: p[2] = floor
        eye = tuple(p); aim_k = 12.
    else:
        a = CAM['from']
        if CAM['dest']:
            u = min(1., (c.t - CAM['t0']) / spec['over']); u = u * u * (3 - 2 * u); b = CAM['dest']
            eye = tuple(a[n] + (b[n] - a[n]) * u for n in range(3))
        else: eye = a
        if spec.get('slide') or spec.get('rise'):      # the eye follows a share of the rider's move, smoothed
            want = [0., 0.]
            if spec.get('slide'):
                (ax, ay), share = spec['slide']; m = ((c.hx - a[0]) * ax + (c.hy - a[1]) * ay) * share; want[0] = m
            want[1] = max(0., c.hz - CAM['ground'] - 1.) * spec.get('rise', 0.)
            ks = 1. - math.exp(-2.5 * dt); sl = CAM['slid']
            sl[0] += (want[0] - sl[0]) * ks; sl[1] += (want[1] - sl[1]) * ks
            if spec.get('slide'): eye = (eye[0] + ax * sl[0], eye[1] + ay * sl[0], eye[2] + sl[1])
            else: eye = (eye[0], eye[1], eye[2] + sl[1])
        aim_k = spec['aim_k']
    lead = [CAM['bv'][n] / aim_k for n in range(3)]; ll = math.sqrt(sum(x * x for x in lead))
    if ll > 2.: lead = [x * 2. / ll for x in lead]
    target = [rider[n] + lead[n] for n in range(3)]
    width = spec['frame'] * TIGHT if spec.get('frame') else CLOSE
    if spec.get('keep'):
        # The rider (led) with the air's lip, top and re-entry: aim at the middle of them and widen to hold them all.
        base = max(MIN_FOV, 2. * math.degrees(math.atan(width / 2. / max(.5, math.dist(eye, target)))))
        aim, want_fov = keep_frame(eye, [tuple(target)] + keep_points(s, c), base)
        target = list(aim)
        f = CAM['fov'] if CAM.get('fov') else want_fov
        CAM['fov'] = f + (want_fov - f) * (1. - math.exp(-(6. if want_fov > f else 1.8) * dt))
    if CAM['aim'] is None: CAM['aim'] = list(rider)
    k = 1. - math.exp(-aim_k * dt)
    CAM['aim'] = [CAM['aim'][n] + (target[n] - CAM['aim'][n]) * k for n in range(3)]
    dist = max(.5, math.dist(eye, CAM['aim']))
    fov = spec.get('fov') or (CAM['fov'] if spec.get('keep') else max(MIN_FOV, min(100., 2. * math.degrees(math.atan(width / 2. / dist)))))
    MV.review_camera(ue(*eye), ue(*CAM['aim']), fov)


# ------------------------------------------------------------------------------------------------ the shots
# Every shot: start (x, y, probe z, UE yaw of travel), the launch speed (m/s), how it is steered (way: a polyline of
# (x, y, want speed; a negative want is a cap), carve: (UE yaw, amplitude, period) or a straight heading), timed events
# (t, effect), position triggers ({'when': fn(s, c), 'do': [effects], 'steer': False to stop steering, 'act': an
# on-foot action}), cameras [(t or fn(s, c), camera)] that latch in order, rec_from, an end predicate and `secs` at
# most. Times are seconds from the launch. Headings: UE yaw 0 east, 90 south, -90 north, 180 west.
def landed_after(n=1, secs=1.2, min_h=0.):
    """End `secs` after the n-th landing from an air at least min_h high."""
    def end(s, c):
        lands = [a['t1'] for a in s['airs'] if a['to'] == 1 and a['h'] >= min_h]
        return len(lands) >= n and c.t >= lands[n - 1] + secs
    return end


def straight_way(x0, y0, yaw, length, want=None):
    h = math.radians(yaw)
    return [(x0 - 5 * math.cos(h), y0 + 5 * math.sin(h), want), (x0 + length * math.cos(h), y0 - length * math.sin(h), want)]


def rail_way(start, lock_s, a_ds=14., a_d=1.9, b_ds=5., b_d=-.6, want=None, out=None):
    """The parapet line: from the start to a point a_d inside the line a_ds before the lock, straight across it a_ds
    later (b_d outside), on along it to its south end, then east along the plaza's south edge."""
    a = rail_offset(lock_s + a_ds, a_d); b = rail_offset(lock_s - b_ds, b_d); e = rail_offset(0., 0.)
    way = [(start[0], start[1], want), (a[0], a[1], want), (b[0], b[1], want), (e[0], e[1], None)]
    return way + (out or [(-66.3, 1369.3, None), (-61., 1367.2, None), (-52., 1366.2, None), (-40., 1366., None), (-30., 1366., None)])


def grind_held(s, c):
    """A rail shot worth keeping: it grinded and stayed up."""
    return s['d_grinds'] > 0 and not s['d_bails']


def rail_ready(s, c):
    """Pop for the parapet when the board will be just inside the line at the pop's peak."""
    if c.mode != 1 or c.t < s.get('rail_after', 0.): return False
    rs, d, t = rail_lateral(c.x, c.y, s.get('rail_line', RAIL0))
    if rs > s['lock_s'] + 14.: return False
    if d < .45: return True
    v_in = -(c.vx * t[1] - c.vy * t[0])
    load = s.get('rail_load', .32)
    horizon = load + .2 + math.sqrt(2. * pop_height(load) / G_AIR)
    return v_in > .3 and d - v_in * horizon <= s.get('apex_d', .12)


def mode_is(m):
    return lambda s, c: c.mode == m


def up_after(secs):
    """End `secs` after the rider is up again from a bail."""
    return lambda s, c: s['up_t'] is not None and c.t > s['up_t'] + secs


BAIL_REPLAY = {'on': 'bail', 'pre': .5, 'post': 1.8}     # the replay's window: from just before the bail into the slide


def free_on_foot(s, c):
    """On foot with no clip playing (the get-up done): the hands can take the board."""
    return s['up_t'] is not None and c.mode == 0 and c.d.get('foot', 'off') == 'off' and c.d.get('clip', '-') == '-'


# Up on foot where the body lies (the skate button during the bail), the board recalled to the hand, and a run with it.
RECALL_TRIG = [{'when': lambda s, c: s['bail_t'] is not None and c.mode == 4 and c.t > s['bail_t'] + .5, 'act': 'toggle'},
               {'when': lambda s, c: free_on_foot(s, c) and c.t > s['up_t'] + .4, 'act': 'recall'},
               {'when': lambda s, c: s.get('recalled') is not None and c.t > s['recalled'] + 1.1, 'act': 'run'},
               {'when': lambda s, c: s.get('recalled') is not None and c.t > s['recalled'] + 3.0, 'act': 'stop'}]


# The park road's middle, from the footbridge round its bend to the top of the ramp into the plaza (it is 32 m wide
# between the parapet inside the bend and the outer railing, and falls about 4 degrees east).
ROAD_MID = [(-133., 1471.1), (-127.9, 1471.1), (-120.3, 1471.0), (-110.6, 1469.6), (-100.6, 1466.9), (-91.0, 1462.8),
            (-82.7, 1457.9), (-76.7, 1453.3), (-72.0, 1448.5), (-68.6, 1444.2), (-65.5, 1437.), (-63.5, 1428.), (-62.5, 1418.)]


def road_way(d, want=None, x0=-127.9):
    """The road `d` metres out from its middle (towards the outer railing), from x0 on; returns (way, start)."""
    way = []
    for i, (x, y) in enumerate(ROAD_MID):
        a, b = ROAD_MID[max(0, i - 1)], ROAD_MID[min(len(ROAD_MID) - 1, i + 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]; n = math.hypot(tx, ty)
        way.append((x - ty / n * d, y + tx / n * d, want))
    j = next(i for i, w in enumerate(way) if w[0] >= x0)
    start = (way[j][0], way[j][1], 134., yaw_to(way[j][0], way[j][1], way[j + 1][0], way[j + 1][1]))
    return way[max(0, j - 1):], start


WIDE_ROAD = fixed((-101., 1479., 140., 5.5), fov=50., aim_k=3.)
PLAZA_RAIL_CAM = fixed((-65.4, 1368.6, 125., 1.0))
POOL_PROBE = 82.


def pool_face(x, y, z=None):
    return 'pool north wall' if y > 1279.5 else 'pool floor'


# The capsule bowl's north-west channel: the outer wall under the north-west coping (5.6 m, vertical at the top) and the
# spine 13.5 m across it (4.7 m, about 80 degrees at its top), straight from u = 10 to 22 m along the coping. Both
# copings are grind lines.
CAPSULE = Pipe((-202.61, 1359.95), 30., 13.5, faces=('outer wall', 'spine'))
CAPSULE_Z, CAPSULE_SPINE_Z, CAPSULE_FLOOR = 54.88, 54.04, 49.3
LINE_U = 16.
COPING_U = 17.
BOWL_PLAN = [{'name': 'melon 180', 'grab': 'melon', 'spin': 180., 'dir': 1., 'stance': 'forward', 'T': .7},
             {'name': 'indy', 'grab': 'indy'},
             {'name': '360', 'spin': 360., 'dir': -1., 'T': .75},
             {'name': 'christ', 'grab': 'christ', 'T': .6}]
COPING = [CAPSULE.at(u, 0.) + (CAPSULE_Z,) for u in (40., 35., 30., 25., 20., 15., 10., 5., 0.)]   # going back along u: the deck on its right

SHOTS = [
    # A run along the road, a jump and a caveman onto the board in the air (optional: the transitions).
    dict(name='open_caveman', optional='caveman', foot=True, road=(0., 8., -134.), settle=1.5,
         acts=[(0., 'run'), (1.9, 'jump'), (2.05, 'jump_release')], secs=6.5,
         trig=[{'when': lambda s, c: s.get('jumped') is not None and c.mode == 0 and c.t > s['jumped'] + .08 and (c.vz > .3 or c.t > s['jumped'] + .35), 'act': 'toggle'},
               {'when': lambda s, c: s.get('mounted') is not None and c.mode == 1 and c.t > s['mounted'] + .5, 'do': [hold(secs=1.2, push=True)]}],
         cams=[(0., chase(back=2.2, side=2.0, up=.7))],
         keep=lambda s, c: s.get('mounted') is not None and c.mode == 1 and c.backend == 'Ride' and s['max_spd_after_mount'] > 2.5 and s['d_bails'] == 0),
    # The opener: a wide view down the park road as he pushes off.
    dict(name='open_wide', unless='open_caveman', road=(0., 8.5), speed=3.,
         secs=6.5, cams=[(0., WIDE_ROAD)], expect=[]),
    # Hard carves: the heading swings 30 degrees either side every 2.2 s; a low camera behind.
    dict(name='road_carves', road=(-3., 8.5), speed=8., carve=30., period=2.2, gain=10., secs=6.2,
         cams=[(0., chase(back=3.3, side=.5, up=.5, turn=3.))]),
    # Kickflip, heelflip, pop shove-it, filmed from the toe side.
    dict(name='road_flips', road=(2., -8.), speed=7., secs=6.2,
         events=[(.8, flick('kickflip')), (2.6, flick('heelflip')), (4.4, flick('shove', .16))],
         cams=[(0., chase(back=2.3, side=2.4, up=.8))], expect=['Kickflip', 'Heelflip', 'Shove']),
    # 360 flip, varial kickflip, hardflip, with the camera ahead looking back.
    dict(name='road_tech', road=(-4., -8.), speed=7., secs=6.6,
         events=[(.8, flick('360_flip')), (2.7, flick('varial_kickflip')), (4.6, flick('hardflip'))],
         cams=[(0., chase(back=-3.6, side=1.3, up=.9))], expect=['360 Flip', 'Varial Kickflip', 'Hardflip']),
    # A heelflip caught 20-30 degrees off the travel: a touch of left stick right after the pop.
    dict(name='road_sketchy', road=(0., -8.), speed=7., secs=3.6,
         events=[(.8, flick('heelflip')), (.8, spin(to=14., dir=1., mag=.35))], land_dz=0.,
         cams=[(0., chase(back=2.4, side=-2.5, up=.8))], expect=['Heelflip']),
    # Down the ramp from the road into the plaza and a powerslide.
    dict(name='ramp_powerslide', start=(-62., 1441., 130., 90.), speed=6.5,
         way=[(-62., 1446., None), (-62., 1420., None), (-61.5, 1395., None), (-61., 1370., None)], secs=8.,
         trig=[{'when': lambda s, c: c.y < 1397.5, 'do': [hold(secs=1.1, slide=True, left=(-1., 0.))]}],
         end=lambda s, c: s['fired'][0] is not None and c.t > s['fired'][0] + 1.9,
         cams=[(0., chase(back=3.0, side=1.4, up=.9)), (lambda s, c: c.y < 1406., fixed((-55.5, 1387., 125., 1.1)))]),
    # Manual and nose manual across the plaza, low from the side.
    dict(name='plaza_manuals', start=(-28., 1386., 125., 180.), speed=6.2, way=straight_way(-28., 1386., 180., 45., 6.), secs=5.4,
         events=[(.7, hold(secs=1.7, right=(0., -.5))), (3.0, hold(secs=1.7, right=(0., .5)))],
         cams=[(0., chase(back=1.6, side=-2.6, up=.45))], expect=['Manual', 'Nose Manual']),
    # Nollies across the plaza: a nollie kickflip, a nollie heelflip and a nollie 360 flip.
    dict(name='plaza_nollies', start=(-28., 1389., 125., 180.), speed=6.5, way=straight_way(-28., 1389., 180., 45., 6.5), secs=6.2,
         events=[(.8, flick('nollie_kickflip')), (2.6, flick('nollie_heelflip')), (4.4, flick('nollie_360_flip'))],
         cams=[(0., chase(back=2.3, side=2.4, up=.8))], expect=['Nollie Kickflip', 'Nollie Heelflip', 'Nollie 360 Flip']),
    # A FS 180 to fakie, then a fakie kickflip and a fakie 360 flip, unsteered on the flat (the steering reads the
    # board's heading, backwards rolling fakie). Launched backwards instead, native takes him for switch, not fakie.
    dict(name='plaza_fakie', steer=False, start=(-28., 1389., 125., 180.), speed=7., secs=6.4,
         events=[(.6, flick('ollie', .16)), (.6, spin(to=180., dir=1.)), (2.6, flick('kickflip')), (4.4, flick('360_flip'))],
         cams=[(0., chase(back=2.3, side=2.4, up=.8))], expect=['180', 'Fakie Kickflip', 'Fakie 360 Flip']),
    # Switch: launched backwards from a standstill native puts him in his other stance, rolling forward; the gestures
    # mirrored (his other foot forward): a switch kickflip, a switch heelflip and a switch 360 flip.
    dict(name='plaza_switch', back=True, steer=False, start=(-28., 1389., 125., 180.), speed=7., secs=6.2,
         events=[(.8, flick('kickflip', mirror=True)), (2.6, flick('heelflip', mirror=True)), (4.4, flick('360_flip', mirror=True))],
         cams=[(0., chase(back=2.3, side=-2.4, up=.8))], expect=['Switch Kickflip', 'Switch Heelflip', 'Switch 360 Flip']),
    # The long 50-50: along the parapet's inside, an ollie onto its edge 22 m from the end and down it to the end. The
    # line closes on the parapet steeply enough (b_d) for the air to come down through the grind edge's height near it,
    # which is where native's grind assist looks; it misses about one take in six, hence the retries.
    dict(name='rail_5050', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.6, rail_load=.34, secs=11.,
         gain=12., b_d=-1.9, keep=grind_held, retry=2,
         cams=[(0., chase(back=3.0, side=-1.8, up=1.0)), (lambda s, c: c.mode == 3 and rail_lateral(c.x, c.y)[0] < 12., PLAZA_RAIL_CAM)],
         expect=['50-50']),
    # A boardslide: the board turned across the line in the air (onto the parapet 22 m from its end, before the lamp post).
    dict(name='rail_board', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.4, rail_load=.33, secs=10.,
         gain=12., b_d=-1.6, keep=grind_held, retry=1,
         rail_do=[spin(to=88., dir=1.)], land_dz=-.5,           # the deck square to the line when it meets the ledge's top
         cams=[(0., chase(back=2.2, side=-2.3, up=.7))], expect=['Boardslide']),
    # A 5-0, from the side (onto the parapet before its lamp post too): a shallower line than the 50-50's lands on one truck.
    dict(name='rail_5_0', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.6, rail_load=.33, secs=10.,
         gain=12., b_d=-1.6, keep=grind_held, retry=2,
         rail_do=[stick(0., -.55)],
         cams=[(0., chase(back=3.0, side=-1.6, up=1.0)), (mode_is(3), fixed((-71.2, 1389.5, 125., 1.0)))],
         expect=['5 0']),          # native names it FS 5 0
    # The drop-in off the upper deck: down the roll-in, along the pool and up the west wall into a big Indy.
    dict(name='megadrop', start=(-47.7, 1301.9, 112., 135.), speed=3., gain=26., land_dz=0.,
         way=[(-47.7, 1301.9, None), (-54.4, 1295.2, None), (-63.6, 1286.4, -15.), (-75., 1279.5, -15.), (-90., 1274., -15.),
              (-105., 1271.5, None), (-121., 1271.2, None), (-132., 1271.2, None)],
         trig=[{'when': lambda s, c: c.x < -116.5, 'steer': False},
               {'when': lambda s, c: c.x < -114. and air_t(s, c) > .12 and c.vz > 0., 'do': [grab('indy', .45)]}],
         end=landed_after(1, 1.8, 2.5), secs=16., keep=lambda s, c: not s['d_bails'], retry=4,
         # Behind him on the deck, then from the pool floor below the roll-in as he drops (a chase would sink into the face
         # and the deck hides the face from its side), then from across the pool as soon as he is down (he passes the
         # floor camera at 21 m/s).
         cams=[(0., chase(back=4.2, side=.8, up=1.8, frame=6.5)), (lambda s, c: c.zb < 108., fixed((-67., 1282.5, 80., 1.4), aim_k=8.)),
               (lambda s, c: c.x < -65. and c.zb < 77., fixed((-104.5, 1261.5, POOL_PROBE, 1.3), aim_k=8.))],
         expect=['FS Grab']),        # native names the toe-side grab (Ride's Indy) FS Grab, the heel-side (Melon) BS Grab
    # Quarter-pipe airs on the pool's north wall, straight at it where its lip faces due south (x -105: further west
    # the lip turns, and a climb there carves along it): each comes back down onto the wall and rides out across the
    # pool, the camera holding the lip, the top of the air and the wall below the lip.
    dict(name='quarter_melon_180', start=(-105., 1258.5, POOL_PROBE, -90.), speed=11.5, way=straight_way(-105., 1258.5, -90., 40.),
         faces=pool_face,
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .05, 'do': [grab('melon', .3), spin(to=180., dir=1.)]}],
         end=landed_after(1, 1.5, .5), secs=9., keep=came_back, retry=1, cams=[(0., fixed((-113.5, 1269., POOL_PROBE, 1.0), aim_k=8., keep=True))],
         expect=['BS Grab', '180']),
    # The Christ Air close: from the west, the side he faces in the air (the board held up in one hand, the other arm
    # out), the eye rising with him.
    dict(name='quarter_christ', slow=True, replay={'pre': .3, 'post': .6}, start=(-105., 1258.5, POOL_PROBE, -90.), speed=11.5,
         way=straight_way(-105., 1258.5, -90., 40.), faces=pool_face,
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .05, 'do': [grab('christ', .5)]}],     # let go in time to land
         end=landed_after(1, 1.5, .5), secs=9., keep=came_back, retry=1,
         cams=[(0., fixed((-110., 1273.5, POOL_PROBE, 1.0), frame=3.6, aim_k=10., rise=.7))],
         expect=['Christ']),
    dict(name='quarter_360', start=(-105., 1258.5, POOL_PROBE, -90.), speed=11.8, way=straight_way(-105., 1258.5, -90., 40.),
         faces=pool_face,
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .04, 'do': [spin(to=360., dir=-1.)]}],
         end=landed_after(1, 1.5, .5), secs=9., keep=came_back, retry=1, cams=[(0., fixed((-94., 1266., POOL_PROBE, 1.1), aim_k=8., keep=True))],
         expect=['360']),
    # The transition line in the capsule bowl's north-west channel: a roll-in off the deck over the outer wall's coping,
    # then back and forth between the outer wall and the spine, each air chosen at its lip by the stance and the air
    # time (a Melon 180 coming down forward, an Indy coming down fakie, a 360, a Christ air), squared up across the
    # floor between the walls. The camera stands down the channel at the floor and slides across with him; the replay
    # is the air that turned the most. The roll-in brings only the coping's height: the spine is .84 m lower, so its
    # first air comes easily, but the outer wall gives back what the airs and the rolling cost, so unless pumping pays
    # for that the line runs out of speed there; it then ends after that climb turns back (kept as the drop-in when an
    # air came back in) and the floor line below carries the airs.
    dict(name='bowl_line', slow=True, replay={'pre': .3, 'post': .7, 'pick': 'spin'}, retry=1,
         start=CAPSULE.at(LINE_U, -1.2) + (57., 60.), speed=1.5, pipe={'pipe': CAPSULE, 'u': LINE_U}, faces=CAPSULE.face,
         plan=BOWL_PLAN, end=line_done, keep=came_back, full=line_kept, secs=34.,
         cams=[(0., chase(back=3.4, side=-.9, up=1.6, frame=4.5)),
               (lambda s, c: c.zb < CAPSULE_Z - .4,
                fixed(CAPSULE.at(LINE_U - 9., CAPSULE.w / 2.) + (CAPSULE_FLOOR + 3., 2.), frame=5.5, aim_k=8., keep=True,
                      slide=(CAPSULE.n, .45), rise=.3))],
         expect=['BS Grab', '180', '360']),
    # The same line launched across the channel's floor at 11.5 m/s, faster than the roll-in arrives, unless the
    # roll-in made the whole line.
    dict(name='bowl_line_floor', unless='bowl_line:full', slow=True, replay={'pre': .3, 'post': .7, 'pick': 'spin'}, retry=1,
         start=CAPSULE.at(LINE_U, CAPSULE.w / 2.) + (CAPSULE_FLOOR + 2., 60.), speed=11.5, pipe={'pipe': CAPSULE, 'u': LINE_U},
         faces=CAPSULE.face, plan=BOWL_PLAN, end=line_done, keep=line_kept, secs=32.,
         cams=[(0., fixed(CAPSULE.at(LINE_U - 9., CAPSULE.w / 2.) + (CAPSULE_FLOOR + 3., 2.), frame=5.5, aim_k=8., keep=True,
                          slide=(CAPSULE.n, .45), rise=.3))],
         expect=['BS Grab', '180', '360']),
    # A 50-50 on the same coping from the deck, and back into the bowl off it: rolling along the deck at 18 degrees to
    # the coping, an ollie that comes down on it a little past its line (the bowl on his toe side, so the grind is
    # backside and leaving it drops him into the bowl), an ollie out after .9 s. Dropped unless it grinds and rides
    # away.
    dict(name='bowl_coping', rail=True, rail_line=COPING, lock_s=40. - COPING_U, apex_d=.35, rail_load=.12,
         start=CAPSULE.at(COPING_U - 11., -3.6) + (57., yaw_to(*CAPSULE.at(COPING_U - 11., -3.6), *CAPSULE.at(COPING_U + 2.5, .8))),
         speed=6.5, way=[CAPSULE.at(COPING_U - 11., -3.6) + (None,), CAPSULE.at(COPING_U + 2.5, .8) + (None,)],
         faces=CAPSULE.face, retry=3,
         trig=[{'when': lambda s, c: c.mode == 3, 'steer': False},
               {'when': lambda s, c: s.get('grind_t') is not None and c.t > s['grind_t'] + .9, 'do': [flick('ollie', .1)]}],
         end=lambda s, c: (s['land_after_grind'] is not None and c.t > s['land_after_grind'] + 1.6)
                          or (s['bail_t'] is not None and c.t > s['bail_t'] + 2.) or (s['stall_t'] is not None and c.t > s['stall_t'] + .8),
         keep=lambda s, c: s['d_grinds'] > 0 and not s['d_bails'], secs=10.,
         cams=[(0., fixed(CAPSULE.at(COPING_U + 1., CAPSULE.w) + (CAPSULE_SPINE_Z + 1.6,), frame=5., aim_k=8., keep=True))],
         expect=['50-50']),
    # The ragdoll section: three bails, each down where the body comes to rest and up again from there. Each is shot at
    # 90 Hz so the mixer can replay it at a third of the speed (--replays picks the one to show).
    # Across the pool floor at the megadrop's speed and up its west wall into an Indy held into the landing: a slam on the
    # wall's face and a slide back down into the pool (the north wall is a hump: an air off it lands out of sight).
    dict(name='bail_pool', start=(-100., 1271.2, POOL_PROBE, 180.), speed=13.3, way=straight_way(-100., 1271.2, 180., 40.),
         slow=True, replay=BAIL_REPLAY, rec_from=.3,
         trig=[{'when': lambda s, c: c.x < -116.5, 'steer': False},
               {'when': lambda s, c: c.x < -114. and air_t(s, c) > .12 and c.vz > 0., 'do': [grab('indy', None)]}],
         end=up_after(1.2), secs=15., keep=lambda s, c: s['d_bails'] > 0, retry=2,
         cams=[(0., fixed((-104.5, 1261.5, POOL_PROBE, 1.3), aim_k=8.))],
         expect=['bail']),
    # Fast down the road, a kickflip, and down on one foot (a one-foot grab held into the landing): a slam at speed.
    # With RECALL he gets up on foot, recalls the board (it has rolled on down the road) to his hand and runs with it.
    dict(name='bail_road', road=(1., 10.), speed=9.5, slow=True, replay=BAIL_REPLAY, rec_from=.5, secs=18. if RECALL else 14.,
         events=[(1.3, flick('kickflip'))],
         trig=[{'when': lambda s, c: air_t(s, c) > .38, 'do': [grab('one_foot', None)]}] + (RECALL_TRIG if RECALL else []),
         end=(lambda s, c: s.get('recalled') is not None and c.t > s['recalled'] + 3.6) if RECALL else up_after(1.2),
         cams=[(0., chase(back=2.0, side=2.6, up=.7))], expect=['bail']),
    # A 50-50 down the parapet, popped out at its end, and an Indy grabbed going down the plaza's step held into the
    # landing (the pop off the low end is only a hop: the grab waits for the step's longer air).
    dict(name='bail_grind', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.6, rail_load=.34, secs=15.,
         slow=True, replay=BAIL_REPLAY, rec_from=1.5, gain=12., b_d=-1.9,
         keep=lambda s, c: s['d_grinds'] > 0 and s['d_bails'] > 0, retry=2,
         trig=[{'when': lambda s, c: c.mode == 3 and rail_lateral(c.x, c.y)[0] < 3., 'do': [flick('ollie', .12)]},
               {'when': lambda s, c: s['land_after_grind'] is not None and c.mode == 2 and air_t(s, c) > .06, 'do': [grab('indy', None)]}],
         end=up_after(1.2),
         cams=[(0., chase(back=3.0, side=-1.8, up=1.0)), (lambda s, c: c.mode == 3 and rail_lateral(c.x, c.y)[0] < 9., fixed((-58., 1374., 125., 1.1)))],   # east of the end, off his way out
         expect=['bail']),
    # The final line: a 50-50 down the parapet and a 360 flip out of it before its corner (the grind slows to a stop
    # against the corner and drops off the outside), down onto the slope beyond and away.
    dict(name='finale', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.6, rail_load=.32, gain=12., b_d=-1.9,
         secs=14., keep=grind_held, retry=2,
         rail_out=[(-66.3, 1369.3, None), (-61., 1367.2, None), (-52., 1366.2, 6.5), (-34., 1366., 6.5), (-20., 1366., 6.5)],
         trig=[{'when': lambda s, c: c.mode == 3 and rail_lateral(c.x, c.y)[0] < 9., 'do': [flick('360_flip', .12)]}],
         end=lambda s, c: s['land_after_grind'] is not None and c.t > s['land_after_grind'] + 1.2,
         cams=[(0., chase(back=3.0, side=-1.6, up=1.0)),
               (lambda s, c: s['d_grinds'] > 0 and rail_lateral(c.x, c.y)[0] < 8., fixed((-45., 1377., 125., 2.2))),
               (lambda s, c: s['d_grinds'] > 0 and c.x > -50., fixed((-26., 1396., 125., 9.), fov=58., aim_k=2., to=(-20., 1404., 125., 16.), over=5.))],
         expect=['50-50', '360 Flip']),
    # A grab off an ollie, let go of the board in the air and down onto the feet with it in hand (optional).
    dict(name='outro_dismount', optional='dismount', start=(-40., 1392., 125., 180.), speed=6.5, way=straight_way(-40., 1392., 180., 40.),
         events=[(.8, flick('ollie', .3))],
         trig=[{'when': lambda s, c: air_t(s, c) > .06, 'do': [grab('indy', None)]},
               {'when': lambda s, c: air_t(s, c) > .3, 'act': 'toggle'},
               {'when': lambda s, c: s.get('dismounted') is not None and c.mode == 0, 'act': 'run'},
               {'when': lambda s, c: s.get('dismounted') is not None and c.t > s['dismounted'] + 2.2, 'act': 'stop'}],
         end=lambda s, c: s.get('dismounted') is not None and c.t > s['dismounted'] + 3.2, secs=7.,
         cams=[(0., fixed((-58., 1383.5, 125., 1.0)))],
         keep=lambda s, c: s.get('dismounted') is not None and c.mode == 0 and s['d_bails'] == 0),
]
for _shot in SHOTS:
    _shot.update(TUNE.get(_shot['name'], {}))

FEATURES = {'caveman': 'caveman', 'dismount': 'airdismount'}


def ready(feature):
    """Whether the game can do an optional shot's transition: EXTRAS, else the skate state's moves= word names it."""
    if isinstance(EXTRAS, dict) and feature in EXTRAS: return bool(EXTRAS[feature])
    if isinstance(EXTRAS, bool): return EXTRAS
    m = re.search(r'\bmoves=(\S*)', L.skate_state())
    return bool(m) and FEATURES[feature] in m.group(1).split(',')


# ------------------------------------------------------------------------------------------------ the run
st = {'i': -1, 'shot': None, 'k': 0, 'kept': {}, 'done': [], 'errors': 0, 'finishing': 0, 'film': 0, 'backend': None,
      'hz': 60}


def say(*a):
    print('RIDE FILM', *a)


def stand_up():
    if ' mode=0 ' not in ' ' + L.skate_state() + ' ':
        live.skate_input(); live.skate_release(); L.skate_toggle()
    live.drive(0)


def act(s, c, what):
    s['log'].append([round(c.t, 3), 'act', what])
    if what in ('run', 'sprint', 'walk'):
        s['foot_gait'] = what
    elif what == 'stop':
        s['foot_gait'] = None; live.drive(0)
    elif what == 'jump':
        s['jumped'] = c.t; live.press('jump')
    elif what == 'jump_release':
        live.press('jump_release')
    elif what == 'toggle':                         # in a bail: get up on foot where the body lies
        if c.mode == 0: s['mounted'] = c.t
        else: s['dismounted'] = c.t; live.skate_release()
        L.skate_toggle()
    elif what == 'recall':                         # the board button (D-pad Right) on foot: the lying board dissolves
        s['recalled'] = c.t                        # and a fresh one comes to the hand
        comp = L.player().get_component_by_class(unreal.SkateComponent)
        if comp: comp.recall_board()


def next_shot():
    while True:
        st['i'] += 1
        if st['i'] >= len(SHOTS): st['shot'] = None; return False
        spec = SHOTS[st['i']]
        if ONLY and spec['name'] not in ONLY: continue
        if spec.get('optional') and not ready(spec['optional']):
            st['done'].append({'name': spec['name'], 'skipped': 'no ' + spec['optional']}); continue
        if spec.get('unless') and st['kept'].get(spec['unless']): continue
        break
    s = dict(spec)
    again = st.pop('again', None)
    if again and again[0] == s['name']: s['try'] = again[1]
    st['deck'] = None
    k = st['k']; st['k'] += 1
    s.update(k=k, dir='%02d_%s' % (k, s['name']), ph='place', pt=0., t=0., f=0, hz=90 if s.get('slow') else 60,
             rec=False, lv=0., loop_n=0, frames=0, rep_n=0, cams_rows=[], loops=[], slowbuf=[], effects=[], fired=None,
             air=None, airs=[], prev_mode=None, steer_on=True, wk=0, log=[], body=[], combos=[], lasts=[], retail=[], first=None,
             bail_t=None, up_t=None, grind_seen=False, land_after_grind=None, stall_t=None, mounted=None, dismounted=None, jumped=None, foot_gait=None, max_spd=0., min_spd=1e9,
             max_spd_after_mount=0., bail_kind=None, d_bails=0, d_grinds=0, d_landed=0, error=None, placed=0, ground_wait=0)
    if s.get('steer') is False: s['steer_on'] = False
    if s.get('road'):
        s['way'], s['start'] = road_way(*s['road'][:1], want=s['road'][1], **({'x0': s['road'][2]} if len(s['road']) > 2 else {}))
    if s.get('rail'):
        if not s.get('way'): s['way'] = rail_way(s['start'], s['lock_s'], want=s.get('want'), out=s.get('rail_out'),
                                             **{k: s[k] for k in ('a_ds', 'a_d', 'b_ds', 'b_d') if k in s})
        # Off the end and rolling on, or (Ride stops a slow grind dead at the parapet's corner) half a second after it stalls.
        s.setdefault('end', lambda s, c: (s['land_after_grind'] is not None and c.t > s['land_after_grind'] + 1.4)
                     or (s['stall_t'] is not None and c.t > s['stall_t'] + .5))
        s['trig'] = [{'when': rail_ready, 'do': [flick('ollie', s.get('rail_load', .32))] + list(s.get('rail_do', []))}] + list(s.get('trig', []))
    s['trig'] = [dict(t) for t in s.get('trig', [])]; s['fired'] = [None] * len(s['trig'])
    s['pending'] = sorted(s.get('events', []), key=lambda e: e[0])
    s['acts_left'] = sorted(s.get('acts', []), key=lambda e: e[0])
    os.makedirs(os.path.join(OUT, 'parts', s['dir']), exist_ok=True)
    st['shot'] = s
    say('shot', s['name'], 'k', k)
    return True


def place(s):
    """Put the rider at the shot's start; False while the ground there does not answer yet (up to 10 s)."""
    x, y, probe, yaw = s['start']
    L.fixed_step(s['hz'])
    g = L.ground_at(ue(x, y, probe))
    if abs(g.z - probe * 100.) < .01 and s['ground_wait'] < 600:     # no hit: the trace returns its probe
        s['ground_wait'] += 1; return False
    if s.get('foot'):
        stand_up()
        L.teleport_player(g, yaw)
        pc.set_control_rotation(unreal.Rotator(0, -8, yaw))
        return True
    L.skate_goofy(False)
    live.skate_input(); L.skate_place(g, yaw + FLIP + (180. if s.get('back') else 0.))     # back: launched backwards
    pc.set_control_rotation(unreal.Rotator(0, -10, yaw))
    s['placed'] += 1
    return True


def inputs(s, c, dt):
    """This frame's skate. input: steering and speed holds on the ground, then the active effects."""
    inp = {'left': (0., 0.), 'right': (0., 0.), 'push': False, 'brake': False, 'slide': False, 'grab_left': False, 'grab_right': False}
    spin_sync(s, c)
    busy = any(e['kind'] in ('flick', 'hold') for e in s['effects'])
    pipe = s.get('pipe')
    if c.mode == 1 and s['steer_on'] and pipe:
        # Back and forth across a channel: steer only on its flat floor, square across it towards the wall ahead and
        # back towards the line's u (the walls turn the board up their fall line themselves). No pumping: Ride pumps
        # only while push is held off the flat, and gives it back when push is let go on the curve (push in the air
        # is a one-foot grab), so the line keeps the speed of its drop-in.
        p, u_keep = pipe['pipe'], pipe['u']
        if c.slope is not None and c.slope < 8. and c.spd > 2.:
            u, _ = p.uk(c.hx, c.hy); side = 1. if c.vx * p.n[0] + c.vy * p.n[1] > 0. else -1.
            dx = side * p.n[0] + max(-.35, min(.35, (u_keep - u) * pipe.get('gain_u', .12))) * p.u[0]
            dy = side * p.n[1] + max(-.35, min(.35, (u_keep - u) * pipe.get('gain_u', .12))) * p.u[1]
            target = yaw_to(c.x, c.y, c.x + dx, c.y + dy)
            inp['left'] = (max(-1., min(1., wrap(target - c.yaw) / s.get('gain', 25.))), 0.)
    elif c.mode == 1 and s['steer_on']:
        heading = c.yaw
        if s.get('way'):
            wx, wy, want, s['wk'] = pursue(s['way'], s['wk'], c.x, c.y, s.get('way_look', 8.)); target = yaw_to(c.x, c.y, wx, wy)
            if s.get('carve'): target += s['carve'] * math.sin(2. * math.pi * c.t / s.get('period', 2.2))
        else:
            target, want = s['start'][3], s.get('want')
        inp['left'] = (max(-1., min(1., wrap(target - heading) / s.get('gain', 25.))), 0.)
        if want is not None and not busy and not c.manual and not c.slide:
            if want < 0:
                inp['brake'] = c.spd > -want + .3
            elif c.spd < want - .5: inp['push'] = True
            elif c.spd > want + 1.5: inp['brake'] = True
    keep = []
    for e in s['effects']:
        if apply_effect(s, c, e, inp): keep.append(e)
    s['effects'] = keep
    if c.mode == 2 and not any(e['kind'] == 'grab' for e in keep):
        inp['push'] = inp['brake'] = False
    spin_model(s, c, inp, dt)
    return inp


BODY_AFTER = 3.     # s after the get-up that a bail's body log goes on (it takes in the board recall)


def body_row(c):
    """A tick of a bail's body log: [t, pelvis x, y, z (m), its source, lie (cm), deck x, y, z (m), board, mode, retail,
    shown (the board's dissolve, 1 solid), vis (the board's component visible)]."""
    try: deck = [round(float(n) / 100. * sg, 3) for n, sg in zip(c.d['deck'].split(','), (1., -1., 1.))]
    except (KeyError, ValueError): deck = [None] * 3
    try: shown = float(c.d['shown'])
    except (KeyError, ValueError): shown = None
    return [round(c.t, 4), round(c.hx, 3), round(c.hy, 3), round(c.hz, 3), c.hsrc, c.d.get('lie')] + deck + \
           [c.d.get('board'), c.mode, c.retail, shown, c.d.get('vis')]


def board_seen(r):
    """The board shows in this body-log row (unknown counts as shown)."""
    shown, vis = (r[12], r[13]) if len(r) > 13 else (None, None)
    return (shown is None or shown > 0.) and vis != '0'


def getup_steps(rows, up_t, before=1.2, after=1.5):
    """The largest move in one tick of the pelvis and of the board's deck around a get-up (a pop shows here):
    {'hips': [cm, m/s, t], 'deck': [cm, m/s, t] while the board shows at both ticks, 'deck_any': the same at any
    shown, 'fades': [[t0, t1, shown at t0, shown at t1], ...] for each run of ticks where the board's dissolve
    went one way (out or in), from the bail to the end of the log}."""
    w = [r for r in rows if up_t - before <= r[0] <= up_t + after]
    out = {}
    for key, i, seen in (('hips', 1, False), ('deck', 6, True), ('deck_any', 6, False)):
        best = None
        for a, b in zip(w, w[1:]):
            if None in a[i:i + 3] + b[i:i + 3] or b[0] <= a[0] or (key == 'hips' and a[4] != b[4]): continue
            if seen and not (board_seen(a) and board_seen(b)): continue
            d = math.dist(a[i:i + 3], b[i:i + 3])
            if best is None or d > best[0]: best = (d, d / (b[0] - a[0]), b[0])
        out[key] = [round(best[0] * 100., 1), round(best[1], 2), best[2]] if best else None
    fades, run = [], None
    for a, b in zip(rows, rows[1:]):
        sa, sb = (a[12], b[12]) if len(b) > 12 else (None, None)
        if sa is None or sb is None or abs(sb - sa) < 1e-3 or (run and (sb > sa) != (run[3] > run[2])):
            if run: fades.append(run); run = None
            if sa is None or sb is None or abs(sb - sa) < 1e-3: continue
        run = [run[0], b[0], run[2], sb] if run else [a[0], b[0], sa, sb]
    if run: fades.append(run)
    out['fades'] = [[round(f[0], 3), round(f[1], 3), round(f[2], 2), round(f[3], 2)] for f in fades]
    return out


def track(s, c):
    """Airs, counters, the trick names and the states the shot went through."""
    if s['first'] is None:
        s['first'] = (c.landed, c.bails, c.grinds)
        s['stale'] = {'combos': c.combo, 'lasts': c.last}   # the previous shot's names, still shown at the start
    s['d_landed'], s['d_bails'], s['d_grinds'] = c.landed - s['first'][0], c.bails - s['first'][1], c.grinds - s['first'][2]
    face = s.get('faces')
    if c.mode == 2 and s['prev_mode'] != 2:
        g = s.get('ground') or {}
        s['air'] = {'t0': c.t, 'z0': c.zb, 'zmax': c.zb, 'x0': c.x, 'y0': c.y, 'lip': abs(c.vz) > 1.5 * max(c.spd, .1),
                    'rate': 0., 'spin': 0., 'yaw': board_yaw(c), 'turned': 0., 'trate': 0., 'tt': c.t, 'vz0': c.vz, 'g': None,
                    'off': {'face': face(c.x, c.y, c.zb) if face else None, 'at': [round(c.x, 2), round(c.y, 2), round(c.zb, 2)],
                            'slope': g.get('slope'), 'stance': g.get('stance'), 'speed': g.get('speed'),
                            'floor_speed': g.get('floor_speed'), 'up': [round(v, 3) for v in c.axes[1]] if c.axes else None},
                    'dturn': 0., 'drate': 0., 'dprev': None, 'up0': c.axes[1] if c.axes else None, 'last0': s.get('last_pre')}
        if c.axes: s['air']['dprev'] = flat(c.axes[0], c.axes[1])
    elif c.mode == 2 and s['air']:                  # the board's own turn, measured from the state line's yaw
        a = s['air']; y = board_yaw(c)
        if y is not None and a['yaw'] is not None and c.t > a['tt']:
            dy = (y - a['yaw'] + 180.) % 360. - 180.
            a['turned'] += dy; a['trate'] += (dy / (c.t - a['tt']) - a['trate']) * .5
        # and from the deck: its turn about the take-off's up (a vert air turns the board in the wall's plane)
        if a['dprev'] is not None and c.axes and c.t > a['tt']:
            f = flat(c.axes[0], a['up0'])
            if f:
                d = math.degrees(math.atan2(dot(cross(a['dprev'], f), a['up0']), dot(a['dprev'], f)))
                a['dturn'] += d; a['drate'] += (d / (c.t - a['tt']) - a['drate']) * .5; a['dprev'] = f
        a['yaw'], a['tt'] = y, c.t
        if 'vz_ref' not in a: a['vz_ref'], a['t_ref'] = c.vz, c.t          # the first tick after the lip-off
        elif c.t - a['t_ref'] >= .1: a['g'] = max(6., min(18., (a['vz_ref'] - c.vz) / (c.t - a['t_ref'])))
    if c.mode == 2 and s['air']:
        s['air']['zmax'] = max(s['air']['zmax'], c.zb)
    if c.mode != 2 and s['prev_mode'] == 2 and s['air']:
        a = s['air']; a.update(t1=c.t, to=c.mode, h=round(a['zmax'] - a['z0'], 2), spin=round(a['spin'], 1), turned=round(a['turned'], 1))
        a['dturn'] = round(a['dturn'], 1)
        a['on'] = {'face': face(c.x, c.y, c.zb) if face else None, 'at': [round(c.x, 2), round(c.y, 2), round(c.zb, 2)],
                   'slope': c.slope, 'stance': None, 'speed': round(c.v3, 2), 'floor_speed': None}
        a['bail'] = c.mode == 4
        s['airs'].append(a); s['air'] = None
        s['log'].append([round(c.t, 3), 'air', round(a['t1'] - a['t0'], 2), a['h'], a['spin'], c.mode, a['turned'], a['dturn']])
    # After a landing: the stance it rode away in, the trick's name, the speed back on the flat, a bail soon after.
    la = s['airs'][-1] if s['airs'] else None
    if la and c.mode != 2:
        if c.mode == 1 and la['on']['stance'] is None and c.t >= la['t1'] + .1:
            la['on']['stance'] = 'fakie' if c.fakie else 'forward'
            la['trick'] = c.last if c.last != la.get('last0') else None     # an air with no trick of its own
        if c.mode == 4 and c.t <= la['t1'] + 1.5: la['bail'] = True
        if c.mode == 1 and la['on']['floor_speed'] is None and c.slope is not None and c.slope < 8. and c.t > la['t1'] + .1:
            la['on']['floor_speed'] = round(c.spd, 2)
    if c.mode == 1:                                  # the ground the next air leaves from
        g = s.setdefault('ground', {})
        g.update(slope=c.slope, stance='fakie' if c.fakie else 'forward', speed=round(c.v3, 2))
        if c.slope is not None and c.slope < 8.: g['floor_speed'] = round(c.spd, 2)
    if c.mode == 3:
        s['grind_seen'] = True; s.setdefault('grind_t', c.t)
    if s['grind_seen'] and s['stall_t'] is None and c.mode in (1, 3) and c.spd < .8: s['stall_t'] = c.t
    if s['grind_seen'] and s['land_after_grind'] is None and c.mode == 1 and s['prev_mode'] == 2: s['land_after_grind'] = c.t
    if c.mode == 4 and s['bail_t'] is None:
        s['bail_t'] = c.t; s['bail_at'] = (c.hx, c.hy); s['bail'] = {'speed': round(s.get('ride_spd', c.spd), 2), 'travel': 0., 'lie_min': None}
    if c.mode == 4 and c.d.get('bail_kind', 'none') != 'none': s['bail_kind'] = c.d['bail_kind']
    if s['bail_t'] is not None and s['up_t'] is None:     # how far the body went, and how low it lay (lie=, cm)
        b = s['bail']; b['travel'] = round(max(b['travel'], math.hypot(c.hx - s['bail_at'][0], c.hy - s['bail_at'][1])), 2)
        try: lie = float(c.d['lie'])                   # -1 out of the bail (the get-up has the body)
        except (KeyError, ValueError): lie = -1.
        if lie >= 0.: b['lie_min'] = min(lie, b['lie_min'] if b['lie_min'] is not None else 1e9)
        if c.t <= s['bail_t'] + 1.: b['travel_1s'], b['lie_1s'] = b['travel'], b['lie_min']
        if c.mode in (0, 1): s['up_t'] = c.t; b['down_secs'] = round(c.t - s['bail_t'], 2)
    if c.mode != 4: s['ride_spd'] = c.spd
    for key, val in (('combos', c.combo), ('lasts', c.last), ('retail', c.retail)):
        if key in s['stale']:
            if val == s['stale'][key]: continue
            del s['stale'][key]
        if val and (not s[key] or s[key][-1] != val): s[key].append(val)
    if c.mode != 2 and c.retail != 'GroundAnimation': s['last_pre'] = c.last    # the name before a pop's wind-up
    if c.mode == 1:
        s['max_spd'] = max(s['max_spd'], c.spd); s['min_spd'] = min(s['min_spd'], c.spd)
        if s['mounted'] is not None: s['max_spd_after_mount'] = max(s['max_spd_after_mount'], c.spd)
    s['prev_mode'] = c.mode


def ride(s, c, dt):
    """The ridden part of a shot; returns 'done' at its end."""
    while s['pending'] and s['pending'][0][0] <= c.t:
        activate(s, c, s['pending'].pop(0)[1])
    while s['acts_left'] and s['acts_left'][0][0] <= c.t:
        act(s, c, s['acts_left'].pop(0)[1])
    for n, tr in enumerate(s['trig']):
        if s['fired'][n] is None and tr['when'](s, c):
            s['fired'][n] = c.t; s['log'].append([round(c.t, 3), 'trigger', n])
            for spec in tr.get('do', []): activate(s, c, spec)
            if tr.get('steer') is False: s['steer_on'] = False
            if tr.get('act'): act(s, c, tr['act'])
    a = s['air']
    if s.get('plan') and a is not None and c.mode == 2 and 'plan' not in a:     # a line's next trick, chosen at the lip
        a['plan'] = None
        if a['lip']:
            fx = plan_air(s, c, a)
            for spec in fx: activate(s, c, spec)
            s['log'].append([round(c.t, 3), 'plan', a.get('plan')])
    if c.mode == 0 or s['dismounted'] is not None:     # on foot, or on the way down from an air dismount
        if s['foot_gait']:
            pc.set_control_rotation(unreal.Rotator(0, -8, s['start'][3] if c.spd < .5 else c.yaw))
            live.drive(1., 0., s['foot_gait'])
    else:
        if s.get('foot') and s['mounted'] is not None and s['foot_gait']:
            s['foot_gait'] = None; live.drive(0)
        live.skate_input(**inputs(s, c, dt))
    end = s.get('end')
    if end and end(s, c): return 'done'
    if c.t >= s.get('secs', 10.): return 'done'


def step_shot(s, dt):
    c = observe(s)
    if s['ph'] == 'place':                       # the camera starts on the next frame, from the placed rider
        s['rec'] = False
        if not place(s): return
        s['ph'] = 'settle'; s['pt'] = 0.; CAM['shot'] = None
        return
    if s['ph'] == 'settle':
        s['pt'] += dt; s['rec'] = False
        if not s.get('foot'): live.skate_input()
        camera(s, c, dt)
        if s['pt'] >= s.get('settle', 1.0):
            if not s.get('foot') and c.backend != 'Ride':
                if s['placed'] < 3:
                    say('not Ride yet:', c.text.split(' | ')[0]); s['ph'] = 'place'; return
                s['error'] = 'Ride did not mount: ' + c.text.split(' | ')[0]; return 'done'
            st['backend'] = c.backend or st['backend']
            if s.get('foot'):
                s['ph'] = 'ride'; s['t'] = 0.
            else:
                v = s.get('speed', 0.) * 100.; h = math.radians(s['start'][3])
                L.skate_launch(unreal.Vector(v * math.cos(h), v * math.sin(h), 0)); s['ph'] = 'launch'; s['pt'] = 0.
        return
    if s['ph'] == 'launch':
        s['pt'] += dt; live.skate_input(); camera(s, c, dt)
        if s['pt'] >= .15:
            s['launched'] = c.text.split(' | ')[0]; s['launch_fakie'] = c.fakie
            say(s['name'], 'launched', s['launched'])
            s['ph'] = 'ride'; s['t'] = 0.
        return
    track(s, c)
    s['rec'] = c.t >= s.get('rec_from', 0.)
    r = ride(s, c, dt)
    camera(s, c, dt)
    if s['f'] % 6 == 0:
        s['log'].append([round(c.t, 3), round(c.x, 2), round(c.y, 2), round(c.zb, 2), round(c.spd, 2), c.mode, c.retail, c.combo,
                         ('fakie' if c.fakie else '') + ('switch' if c.switch else '')])
    if s['bail_t'] is not None and (s['up_t'] is None or c.t <= s['up_t'] + BODY_AFTER):
        s['body'].append(body_row(c))
    s['f'] += 1
    s['t'] += 1. / s['hz']
    s['last_c'] = c
    return r


def record(s):
    """Stamp the sounds, keep the loops and save the frame(s) of a recorded sim frame."""
    if not s['rec']:
        L.audio_frame(UNRECORDED); return
    lv = s['lv']
    L.audio_frame(AUDIO_BASE * (s['k'] + 1) + int(round(lv)))
    loops = L.skate_loops().strip() or NEUTRAL_LOOPS
    while s['loop_n'] <= lv + 1e-6:
        s['loops'].append(loops); s['loop_n'] += 1
    loc = cm.get_camera_location(); rot = cm.get_camera_rotation(); pl = L.player().get_actor_location()
    cam = [round(loc.x, 1), round(loc.y, 1), round(loc.z, 1), round(rot.yaw, 2), round((pl - loc).length(), 1)]
    name = None
    if lv + 1e-6 >= 2 * s['frames']:
        name = 'f%05d.jpg' % s['frames']; s['cams_rows'].append([s['frames']] + cam); s['frames'] += 1; st['film'] += 1
        if st['film'] % 30 == 0:
            c = s.get('last_c')
            open(os.path.join(OUT, 'progress.txt'), 'w').write('%s film=%d t=%.2f mode=%s combo=%s\n' % (
                s['name'], st['film'], s['t'], c.mode if c else '?', c.combo if c else ''))
    elif s.get('slow'):
        name = 'r%05d.jpg' % s['rep_n']; s['rep_n'] += 1
    if s.get('slow'):
        s['slowbuf'].append([round(s['t'] - 1. / s['hz'], 4), round(lv, 3), name, cam, loops])
    if name and not REHEARSE:
        L.screenshot(os.path.join(OUT, 'parts', s['dir'], name))
    s['lv'] += 60. / s['hz']


def outcome(s):
    c = s.get('last_c')
    if s['error']: return 'error'
    if s['d_bails']: return 'bailed'
    if s['airs']: return 'landed' if c is None or c.mode != 4 else 'bailed'
    return 'rode'


def end_shot():
    s = st['shot']; c = s.get('last_c')
    keep = s['error'] is None
    if keep and s.get('keep') and c is not None:
        try: keep = bool(s['keep'](s, c))
        except Exception: keep = False
    st['kept'][s['name']] = keep
    if s.get('full') and c is not None:          # a kept shot that also did all it could (a whole transition line)
        try: st['kept'][s['name'] + ':full'] = keep and bool(s['full'](s, c))
        except Exception: st['kept'][s['name'] + ':full'] = False
    if s.get('bail') and s['up_t'] is not None: s['bail']['getup'] = getup_steps(s['body'], s['up_t'])
    replay = None
    if s.get('replay') and s['replay'].get('on') == 'bail':
        if s['bail_t'] is not None:
            replay = {'from_t': round(s['bail_t'] - s['replay']['pre'], 3), 'to_t': round(s['bail_t'] + s['replay']['post'], 3), 'stretch': 3}
    elif s.get('replay') and s['airs']:
        if s['replay'].get('pick') == 'spin':     # the landed air that turned the most (the deck's turn), then the highest
            ok = [a for a in s['airs'] if not a.get('bail')] or s['airs']
            a = max(ok, key=lambda a: (round(abs(a['dturn'] if a['lip'] and a.get('up0') else a['turned']) / 90.), a['h']))
        else: a = max(s['airs'], key=lambda a: (a['h'], a['t1'] - a['t0']))
        replay = {'from_t': round(a['t0'] - s['replay']['pre'], 3), 'to_t': round(a['t1'] + s['replay']['post'], 3), 'stretch': 3}
    names = ' / '.join(s['combos'] + s['lasts'])
    missing = [e for e in s.get('expect', []) if e != 'bail' and e.lower() not in names.lower()] + \
              (['bail'] if 'bail' in s.get('expect', []) and not s['d_bails'] else [])
    info = {'name': s['name'], 'k': s['k'], 'dir': s['dir'], 'keep': keep, 'outcome': outcome(s), 'frames': s['frames'],
            'seconds': round(s['frames'] / 30., 2), 'slow': bool(s.get('slow')), 'replay': replay,
            'combos': s['combos'], 'tricks': s['lasts'], 'missing': missing, 'landed': s['d_landed'], 'bails': s['d_bails'],
            'grinds': s['d_grinds'], 'speed_max': round(s['max_spd'], 2), 'speed_min': round(s['min_spd'], 2) if s['min_spd'] < 1e8 else None,
            'airs': [air_info(a) for a in s['airs']], 'try': s.get('try', 1), 'full': st['kept'].get(s['name'] + ':full'),
            'stall_wall_t': s.get('stall_wall_t'),
            'retail': s['retail'][:40], 'launched': s.get('launched'), 'fakie_at_launch': s.get('launch_fakie'),
            'bail_kind': s['bail_kind'], 'bail': s.get('bail'), 'ride_physical': physical_cvar(), 'error': s['error'], 'end_state': c.text if c else None}
    part = dict(info, cams=s['cams_rows'], loops=s['loops'], slowbuf=s['slowbuf'], log=s['log'], body=s['body'])
    json.dump(part, open(os.path.join(OUT, 'parts', s['dir'], 'shot.json'), 'w'))
    st['done'].append(info)
    json.dump(st['done'], open(os.path.join(OUT, 'shots.json'), 'w'), indent=1)
    say('done', s['name'], info['outcome'], 'keep' if keep else 'DROP', s['combos'], 'missing', missing)
    s['effects'] = []
    live.skate_input()
    if not keep and s.get('retry') and s.get('try', 1) <= s['retry']:      # once more, from the start
        st['again'] = (s['name'], s.get('try', 1) + 1); st['i'] -= 1


def air_info(a):
    """An air for done.json: when, how long and high, the spin (Ride's own, else simulated; the state's yaw; the deck's
    turn), where it left and came down (face, point, slope of the board there, stance, speed along the travel and the
    speed on the flat before and after), what it landed in (1 rolling, 3 a grind, 4 a bail), a bail within 1.5 s of the
    landing, and whether it came back into the transition (landed rolling on a slope below its lip)."""
    on = a.get('on') or {}
    return {'t': round(a['t0'], 2), 'secs': round(a['t1'] - a['t0'], 2), 'h': a['h'], 'lip': a['lip'], 'trick': a.get('trick'),
            'plan': a.get('plan'), 'spin': a['spin'], 'turned': a.get('turned'), 'deck_turn': a.get('dturn') if a.get('up0') else None,
            'g': round(a['g'], 2) if a.get('g') else None, 'to': a['to'], 'bail': bool(a.get('bail')), 'back_in': back_in(a),
            'takeoff': a.get('off'), 'landing': on}


def physical_cvar():
    try: return unreal.SystemLibrary.get_console_variable_int_value('skate.RidePhysical')
    except Exception as e: return repr(e)


def start_finish():
    st['finishing'] = 1; st['shot'] = None
    live.skate_input(); live.drive(0)


def finish():
    live.stop('ride_film')
    live.skate_input(); live.skate_release(); live.drive(0)
    MV.restore_player_camera(); L.film_hud(False); L.fixed_step(0)
    n = L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    json.dump({'take': TAKE, 'backend': st['backend'], 'physical': PHYSICAL, 'ride_physical': physical_cvar(), 'extras': EXTRAS, 'moves': st.get('moves'), 'fps_film': 30, 'sim_clock': 60, 'audio_base': AUDIO_BASE,
               'unrecorded': UNRECORDED, 'sounds': n, 'rehearse': REHEARSE, 'film_frames': st['film'], 'errors': st['errors'],
               'shots': st['done'], 'state': L.skate_state()}, open(os.path.join(OUT, 'done.json'), 'w'), indent=1)
    say('finished', OUT, st['film'], 'frames')


def probe_moves():
    """Whether an optional shot waits on the moves= word, which the game prints only once the rider has been on the
    board: then the run starts with a moment on the board, unrecorded."""
    if EXTRAS is not None and not isinstance(EXTRAS, dict): return False
    wanted = [x['optional'] for x in SHOTS if x.get('optional') and (not ONLY or x['name'] in ONLY)
              and not (isinstance(EXTRAS, dict) and x['optional'] in EXTRAS)]
    return bool(wanted) and not re.search(r'\bmoves=', L.skate_state())


def probe(p):
    L.audio_frame(UNRECORDED); p['f'] += 1
    if p['f'] == 1:
        loc = L.player().get_actor_location()
        live.skate_input(); L.skate_place(L.ground_at(unreal.Vector(loc.x, loc.y, loc.z + 200.)), L.player().get_actor_rotation().yaw)
    elif 'off' not in p:
        if p['f'] >= 40 or (p['f'] > 5 and re.search(r'\bmoves=', L.skate_state())):
            m = re.search(r'\bmoves=(\S*)', L.skate_state()); st['moves'] = m.group(1) if m else None
            say('moves probe', st['moves'])
            stand_up(); p['off'] = p['f']
    elif ' mode=0 ' in ' ' + L.skate_state() + ' ' or p['f'] > p['off'] + 180:
        st['probe'] = None


def run(dt):
    try:
        if st.get('probe'):
            probe(st['probe']); return
        if st['finishing']:
            L.audio_frame(UNRECORDED); st['finishing'] += 1
            if st['finishing'] > 6: finish()
            return
        if st['shot'] is None and not next_shot():
            start_finish(); return
        s = st['shot']
        try:
            r = step_shot(s, 1. / s['hz'])          # sim time: the wall-clock dt stretches while frames are saved
            record(s)
        except Exception:
            st['errors'] += 1; s['error'] = traceback.format_exc().strip().splitlines()[-1]
            open(os.path.join(OUT, 'error.txt'), 'a').write('%s\n%s\n' % (s['name'], traceback.format_exc()))
            r = 'done'
        if r == 'done':
            end_shot()
            if st['errors'] > 3 or not next_shot(): start_finish()
    except Exception:
        open(os.path.join(OUT, 'error.txt'), 'a').write('fatal\n%s\n' % traceback.format_exc())
        try: finish()
        except Exception: live.stop('ride_film')


unreal.SystemLibrary.execute_console_command(L.game_world(), 'skate.Backend Ride'); st['backend'] = 'asked'   # at each mount
unreal.SystemLibrary.execute_console_command(L.game_world(), 'skate.RidePhysical %d' % PHYSICAL)
L.film_hud(True); L.fixed_step(60); L.audio_log('start')
st['probe'] = {'f': 0} if probe_moves() else None
live.behave('ride_film', run)
say('started', OUT, [s['name'] for s in SHOTS if not ONLY or s['name'] in ONLY])
