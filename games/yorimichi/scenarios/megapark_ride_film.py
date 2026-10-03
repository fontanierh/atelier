# megapark_ride_film.py: runs inside the game (atelier live py - < this file). This line keeps the bridge from taking
# the code for a file name: Unreal's Python reads any text whose first .py is followed by a space as a script path.
"""Mega Park Ride film: the Ride skating backend (skate.Backend Ride) through the Mega Park. A push-off and hard carves
on the park road, flat-ground flips (kickflip, heelflip, pop shove-it, 360 flip, varial kickflip, hardflip) and a
sketchy catch, a powerslide down the ramp, manuals on the plaza, a long 50-50, a boardslide and a 5-0 down the plaza
parapet, the drop-in off the upper deck into a big Indy over the pool's west wall, quarter-pipe airs (Melon 180, a
Christ air with a slow-motion replay, a 360), a grab held into a ragdoll bail and the get-up where the rider fell, and a
clean final line (kickflip, crooked grind, 360 flip). Two optional shots open with a run and a caveman onto the board
and end with a grab dismount to the feet; they run only when the game has those transitions.

    atelier play yorimichi --set 'performance=1;render_scale=100;painterly=0.35;paint_radius=2;toon=0;outline=0;
        exposure=0.9;saturation=1;wind=3.5;sun_height=48;sun_yaw=15;desktop=1;show_fps=0' -- -RenderOffscreen -ForceRes
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
    TIGHT     the framed cameras' width factor (.82)

Runs in the game's Python (the live bridge) at a fixed 60 Hz step, 90 Hz for the slow-motion shot. Every board shot is
placed, settles for a second unrecorded, is launched and then ridden by scripted skate. input: pursuit steering along
a line with push and brake holds, timed events and position triggers (Flick-It gestures, grabs, spins, grind sticks).
Each shot records into its own folder (parts/NN_name): a JPG every second 60 Hz frame (30 fps), the camera, and the
board's loops per frame; the sounds the game starts are stamped with the shot's own frame clock (AUDIO_BASE * (k + 1)
plus the frame; unrecorded frames stamp -1000000). The slow shot saves every 90 Hz frame, so the mixer can replay its
biggest air at a third of the speed. An optional shot that does not do what it should (no caveman, no dismount) is
marked keep=false and left out of the cut. megapark_ride_film_mix.py cuts the parts into the film and mixes the sound.
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
TIGHT = float(globals().get('TIGHT', .82))       # every framed camera's width x this: Cairo is short, .82 keeps him ~40% of the height
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
G_AIR = 14.                     # Ride's air gravity (m/s^2)


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


def rail_at(s):
    """Point and unit tangent (north-going) on the parapet line at s metres from its south end."""
    s = max(0., min(s, 5. * (len(RAIL0) - 1) - 1e-6)); i = int(s // 5); u = s / 5. - i
    a, b = RAIL0[i], RAIL0[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy)
    return (a[0] + dx * u, a[1] + dy * u, a[2] + (b[2] - a[2]) * u), (dx / n, dy / n)


def rail_offset(s, d):
    """A plan point d metres inside (plaza side) the parapet line at s."""
    p, t = rail_at(s)
    return p[0] + t[1] * d, p[1] - t[0] * d


def rail_lateral(x, y):
    """(s, signed distance inward, tangent) of the nearest point of the parapet line."""
    best = None
    for i in range(len(RAIL0) - 1):
        a, b = RAIL0[i], RAIL0[i + 1]; dx, dy = b[0] - a[0], b[1] - a[1]; ll = dx * dx + dy * dy
        u = max(0., min(1., ((x - a[0]) * dx + (y - a[1]) * dy) / ll))
        px, py = a[0] + dx * u, a[1] + dy * u; d = math.hypot(x - px, y - py)
        if best is None or d < best[0]:
            n = math.sqrt(ll); t = (dx / n, dy / n)
            best = (d, 5. * (i + u), ((x - px) * t[1] - (y - py) * t[0]), t)
    return best[1], best[2], best[3]


def pop_height(load):
    """Ride's ollie height (m) after the stick rested `load` seconds on the rim (PopHeightScale 1.15)."""
    return (137. - 73. * math.exp(-max(0., load - .067) / .16)) / 100.


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
    c.manual, c.slide, c.fakie = d.get('manual') == '1', d.get('slide') == '1', d.get('fakie') == '1'
    c.combo, c.last = d.get('combo', ''), d.get('last', '')
    c.landed, c.bails, c.grinds, c.score = (d.get(k, 0) for k in ('landed', 'bails', 'grinds', 'score'))
    p = L.player(); loc = p.get_actor_location(); v = p.get_velocity()
    c.x, c.y, c.za = loc.x / 100., -loc.y / 100., loc.z / 100.
    c.vx, c.vy, c.vz = v.x / 100., -v.y / 100., v.z / 100.
    c.spd = math.hypot(c.vx, c.vy)
    c.yaw = math.degrees(math.atan2(v.y, v.x)) if c.spd > .5 else p.get_actor_rotation().yaw
    c.hdi = math.atan2(c.vy, c.vx) if c.spd > .5 else -math.radians(p.get_actor_rotation().yaw)
    return c


def air_t(s, c):
    a = s['air']
    return c.t - a['t0'] if a and c.mode == 2 else -1.


def time_to_land(s, c):
    """Seconds until the board falls back to its take-off height (or `land_dz` below it)."""
    a = s['air']
    if not a: return 0.
    h = c.zb - a['z0'] + s.get('land_dz', 0.)
    return (c.vz + math.sqrt(max(0., c.vz * c.vz + 2. * G_AIR * h))) / G_AIR


# ------------------------------------------------------------------------------------------------ input effects
def flick(name, load=.2, **kw):
    """A Flick-It gesture: its first point held `load` s (the crouch), the others a 30th of a second each."""
    return dict(kind='flick', name=name, load=load, **kw)


def hold(secs=None, until=None, **inputs):
    return dict(kind='hold', secs=secs, until=until, inputs=inputs)


def spin(to=None, until=None, dir=1., mag=1.):
    """In the air: turn with the left stick until the spin (simulated from Ride's rates) will reach `to` degrees by
    the landing, or until it has turned `until` degrees."""
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
        pts = live.FLICKS[e['name']]
        if u < e['load']: inp['right'] = pts[0]
        else:
            j = 1 + int((u - e['load']) * 30. + 1e-6)
            if j > len(pts): return False
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
        inp['right'] = e['right']; return True
    # The air effects wait for an air and end with it.
    if c.mode == 2 and s['air']: e['air'] = True
    elif e['air']: return False
    else: return u < 3.
    a = s['air']
    if k == 'spin':
        if e['until'] is not None: go = abs(a['spin']) < e['until']
        else:
            tl = time_to_land(s, c)
            done, r = (a['turned'], a['trate']) if a.get('yaw') is not None else (a['spin'], a['rate'])
            r = abs(r)
            go = abs(done) + min(r, 115.) * tl + max(0., r - 115.) / 7. < e['to']
        if go: inp['left'] = (e['dir'] * e['mag'], inp['left'][1])
        return True
    if k == 'grab':
        if e['release'] is None or time_to_land(s, c) > e['release']: inp.update(GRABS[e['which']])
        return True
    return False


SPIN_SCALE = 1.6           # the game's AirSpinScale (Config/DefaultGame.ini): Ride multiplies its full spin rates by it


def board_yaw(c):
    """The board's yaw from the state line (None when it has none)."""
    try: return float(c.d['yaw'])
    except (KeyError, TypeError, ValueError): return None


def spin_model(s, c, inp, dt):
    """Ride's air spin (TickAir): the rate eases at 7/s toward the stick's full rate, or toward the current rate capped
    at 115 deg/s when the stick is centred; the total is what Ride scores as the spin."""
    a = s['air']
    if not a: return
    x = inp['left'][0]
    full = (470. if a['lip'] else 260.) * SPIN_SCALE
    target = x * full if abs(x) > .25 else max(-115., min(115., a['rate']))
    a['rate'] += (target - a['rate']) * (1. - math.exp(-7. * dt))
    a['spin'] += a['rate'] * dt


# ------------------------------------------------------------------------------------------------ cameras
CAM = {'i': -1, 'spec': None, 'p': None, 'aim': None, 'h': None, 't0': 0.}


def chase(back=3., side=0., up=.9, frame=7.5, turn=2.5, follow=6., follow_z=4., aim_up=0., agl=.5):
    """A follow camera on the travel's heading (frozen in the air and in a bail): `back` behind (negative: ahead,
    looking back), `side` to the right of the travel, `up` above the rider; the field of view keeps `frame` metres
    across at the rider (7.5 m keeps him about 40% of the frame's height)."""
    return dict(kind='chase', back=back, side=side, up=up, frame=frame, turn=turn, follow=follow, follow_z=follow_z,
                aim_up=aim_up, agl=agl)


def fixed(at, frame=8., fov=None, aim_k=6., aim_up=0., to=None, over=6.):
    """A camera standing at `at` ((x, y, z), or (x, y, probe z, height above the ground)) that turns to follow the
    rider; `frame` metres across at the rider, or a set `fov`. With `to`, it travels there over `over` seconds."""
    return dict(kind='fixed', at=at, frame=frame, fov=fov, aim_k=aim_k, aim_up=aim_up, to=to, over=over)


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
        CAM.update(shot=s['k'], i=i, spec=spec, t0=c.t, h=c.hdi, p=None, aim=None)
        if spec['kind'] == 'fixed':
            CAM['from'] = resolve(spec['at']); CAM['dest'] = resolve(spec['to']) if spec.get('to') else None
    rider = (c.x, c.y, c.za + spec.get('aim_up', 0.))
    if spec['kind'] == 'chase':
        if c.mode not in (2, 4) and c.spd > 1.:
            CAM['h'] += math.atan2(math.sin(c.hdi - CAM['h']), math.cos(c.hdi - CAM['h'])) * (1. - math.exp(-spec['turn'] * dt))
        h = CAM['h']; ch, sh = math.cos(h), math.sin(h)
        want = [c.x - spec['back'] * ch + spec['side'] * sh, c.y - spec['back'] * sh - spec['side'] * ch, c.za + spec['up']]
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
        aim_k = spec['aim_k']
    if CAM['aim'] is None: CAM['aim'] = list(rider)
    k = 1. - math.exp(-aim_k * dt)
    CAM['aim'] = [CAM['aim'][n] + (rider[n] - CAM['aim'][n]) * k for n in range(3)]
    dist = max(.5, math.dist(eye, CAM['aim']))
    fov = spec.get('fov') or max(18., min(100., 2. * math.degrees(math.atan(spec['frame'] * TIGHT / 2. / dist))))
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


def rail_ready(s, c):
    """Pop for the parapet when the board will be just inside the line at the pop's peak."""
    if c.mode != 1 or c.t < s.get('rail_after', 0.): return False
    rs, d, t = rail_lateral(c.x, c.y)
    if rs > s['lock_s'] + 14.: return False
    if d < .45: return True
    v_in = -(c.vx * t[1] - c.vy * t[0])
    load = s.get('rail_load', .32)
    horizon = load + .2 + math.sqrt(2. * pop_height(load) / G_AIR)
    return v_in > .3 and d - v_in * horizon <= s.get('apex_d', .12)


def mode_is(m):
    return lambda s, c: c.mode == m


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
PLAZA_RAIL_CAM = fixed((-65.4, 1368.6, 125., 1.0), frame=9.)
POOL_PROBE = 82.

SHOTS = [
    # A run along the road, a jump and a caveman onto the board in the air (optional: the transitions).
    dict(name='open_caveman', optional='caveman', foot=True, road=(0., 8., -134.), settle=1.5,
         acts=[(0., 'run'), (1.9, 'jump'), (2.05, 'jump_release')], secs=6.5,
         trig=[{'when': lambda s, c: s.get('jumped') is not None and c.mode == 0 and c.t > s['jumped'] + .08 and (c.vz > .3 or c.t > s['jumped'] + .35), 'act': 'toggle'},
               {'when': lambda s, c: s.get('mounted') is not None and c.mode == 1 and c.t > s['mounted'] + .5, 'do': [hold(secs=1.2, push=True)]}],
         cams=[(0., chase(back=2.2, side=2.0, up=.7, frame=6.5))],
         keep=lambda s, c: s.get('mounted') is not None and c.mode == 1 and c.backend == 'Ride' and s['max_spd_after_mount'] > 2.5 and s['d_bails'] == 0),
    # The opener: a wide view down the park road as he pushes off.
    dict(name='open_wide', unless='open_caveman', road=(0., 8.5), speed=3.,
         secs=6.5, cams=[(0., WIDE_ROAD)], expect=[]),
    # Hard carves: the heading swings 30 degrees either side every 2.2 s; a low camera behind.
    dict(name='road_carves', road=(-3., 8.5), speed=8., carve=30., period=2.2, gain=10., secs=6.2,
         cams=[(0., chase(back=3.3, side=.5, up=.5, frame=7.0, turn=3.))]),
    # Kickflip, heelflip, pop shove-it, filmed from the toe side.
    dict(name='road_flips', road=(2., -8.), speed=7., secs=6.2,
         events=[(.8, flick('kickflip')), (2.6, flick('heelflip')), (4.4, flick('shove', .16))],
         cams=[(0., chase(back=2.3, side=2.4, up=.8, frame=7.5))], expect=['Kickflip', 'Heelflip', 'Shove']),
    # 360 flip, varial kickflip, hardflip, with the camera ahead looking back.
    dict(name='road_tech', road=(-4., -8.), speed=7., secs=6.6,
         events=[(.8, flick('360_flip')), (2.7, flick('varial_kickflip')), (4.6, flick('hardflip'))],
         cams=[(0., chase(back=-3.6, side=1.3, up=.9, frame=7.5))], expect=['360 Flip', 'Varial Kickflip', 'Hardflip']),
    # A heelflip caught 20-30 degrees off the travel: a touch of left stick right after the pop.
    dict(name='road_sketchy', road=(0., -8.), speed=7., secs=3.6,
         events=[(.8, flick('heelflip')), (.8, spin(to=14., dir=1., mag=.35))], land_dz=0.,
         cams=[(0., chase(back=2.4, side=-2.5, up=.8, frame=7.0))], expect=['Heelflip']),
    # Down the ramp from the road into the plaza and a powerslide.
    dict(name='ramp_powerslide', start=(-62., 1441., 130., 90.), speed=6.5,
         way=[(-62., 1446., None), (-62., 1420., None), (-61.5, 1395., None), (-61., 1370., None)], secs=8.,
         trig=[{'when': lambda s, c: c.y < 1397.5, 'do': [hold(secs=1.1, slide=True, left=(-1., 0.))]}],
         end=lambda s, c: s['fired'][0] is not None and c.t > s['fired'][0] + 1.9,
         cams=[(0., fixed((-55.5, 1387., 125., 1.1), frame=8.5))]),
    # Manual and nose manual across the plaza, low from the side.
    dict(name='plaza_manuals', start=(-28., 1386., 125., 180.), speed=6.2, way=straight_way(-28., 1386., 180., 45., 6.), secs=5.4,
         events=[(.7, hold(secs=1.7, right=(0., -.5))), (3.0, hold(secs=1.7, right=(0., .5)))],
         cams=[(0., chase(back=1.6, side=-2.6, up=.45, frame=6.5))], expect=['Manual', 'Nose Manual']),
    # The long 50-50: along the parapet's inside, an ollie onto its edge 22 m from the end and down it to the end.
    dict(name='rail_5050', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.6, rail_load=.34, secs=11.,
         cams=[(0., chase(back=3.0, side=-1.8, up=1.0, frame=7.5)), (lambda s, c: c.mode == 3 and rail_lateral(c.x, c.y)[0] < 12., PLAZA_RAIL_CAM)],
         expect=['50-50']),
    # A boardslide: the board turned across the line in the air (onto the parapet before its lamp post, 15 m from the end).
    dict(name='rail_board', rail=True, lock_s=22., start=(-75.9, 1422., 128., 90.), speed=7.4, rail_load=.33, secs=10.,
         rail_do=[spin(until=50., dir=1.)],
         cams=[(0., chase(back=2.2, side=-2.3, up=.7, frame=7.0))], expect=['Boardslide']),
    # A 5-0, from the side.
    dict(name='rail_5_0', rail=True, lock_s=17., start=(-77.4, 1412., 126., 90.), speed=7.4, rail_load=.32, secs=9.,
         rail_do=[stick(0., -.55)],
         cams=[(0., chase(back=3.0, side=-1.6, up=1.0, frame=7.5)), (mode_is(3), fixed((-71.2, 1389.5, 125., 1.0), frame=8.))],
         expect=['5-0']),
    # The drop-in off the upper deck: down the roll-in, along the pool and up the west wall into a big Indy.
    dict(name='megadrop', start=(-44.5, 1305.1, 112., 135.), speed=3., gain=26., land_dz=0.,
         way=[(-44.5, 1305.1, None), (-54.4, 1295.2, None), (-63.6, 1286.4, -15.), (-75., 1279.5, -15.), (-90., 1274., -15.),
              (-105., 1271.5, None), (-121., 1271.2, None), (-132., 1271.2, None)],
         trig=[{'when': lambda s, c: c.x < -116.5, 'steer': False},
               {'when': lambda s, c: c.x < -114. and air_t(s, c) > .12 and c.vz > 0., 'do': [grab('indy', .45)]}],
         end=landed_after(1, 1.8, 2.5), secs=16.,
         cams=[(0., chase(back=4.2, side=.8, up=1.8, frame=8.)), (lambda s, c: c.x < -88., fixed((-104.5, 1261.5, POOL_PROBE, 1.3), frame=13.))],
         expect=['Indy']),
    # Quarter-pipe airs on the pool's north wall.
    dict(name='quarter_melon_180', start=(-108., 1258.5, POOL_PROBE, -90.), speed=11.5, way=straight_way(-108., 1258.5, -90., 40.),
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .1, 'do': [grab('melon', .4), spin(to=180., dir=1.)]}],
         end=landed_after(1, 1.2, 1.), secs=8., cams=[(0., fixed((-116.5, 1269., POOL_PROBE, 1.0), frame=8.5))],
         expect=['Melon', '180']),
    dict(name='quarter_christ', slow=True, replay={'pre': .3, 'post': .45}, start=(-108., 1258.5, POOL_PROBE, -90.), speed=11.5,
         way=straight_way(-108., 1258.5, -90., 40.),
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .1, 'do': [grab('christ', .38)]}],
         end=landed_after(1, 1.2, 1.), secs=8., cams=[(0., fixed((-101.5, 1275.5, POOL_PROBE, .9), frame=7.))],
         expect=['Christ']),
    dict(name='quarter_360', start=(-108., 1258.5, POOL_PROBE, -90.), speed=11.8, way=straight_way(-108., 1258.5, -90., 40.),
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .06, 'do': [spin(to=360., dir=-1.)]}],
         end=landed_after(1, 1.2, 1.), secs=8., cams=[(0., fixed((-104., 1288.5, 84., 1.6), frame=8.))],
         expect=['360']),
    # A Christ air held into the landing: thrown into the ragdoll, then up again where he fell.
    dict(name='bail', start=(-108., 1258.5, POOL_PROBE, -90.), speed=11.5, way=straight_way(-108., 1258.5, -90., 40.),
         trig=[{'when': lambda s, c: c.y > 1277., 'steer': False},
               {'when': lambda s, c: air_t(s, c) > .1, 'do': [grab('christ', None)]}],
         end=lambda s, c: s['up_t'] is not None and c.t > s['up_t'] + 1.6, secs=15.,
         cams=[(0., fixed((-99.5, 1271.5, POOL_PROBE, 1.2), frame=9.)),
               (lambda s, c: s['bail_t'] is not None and c.t > s['bail_t'] + 1.2, fixed((-103., 1268., POOL_PROBE, 1.0), frame=6.5, aim_k=3.))],
         expect=['bail']),
    # The final line: a kickflip down the ramp, a crooked grind down the parapet, a 360 flip on the way out, and away.
    dict(name='finale', rail=True, lock_s=16., start=(-72.5, 1437., 130., 95.), speed=7.4, want=-9.5, rail_load=.32, rail_after=2.2,
         rail_do=[stick(.52, .42)], secs=14., events=[(.7, flick('kickflip'))],
         rail_out=[(-66.3, 1369.3, None), (-61., 1367.2, None), (-52., 1366.2, 6.5), (-34., 1366., 6.5), (-20., 1366., 6.5)],
         trig=[{'when': lambda s, c: c.mode == 1 and s['d_grinds'] > 0 and c.x > -59.5, 'do': [flick('360_flip')]}],
         end=lambda s, c: s['d_grinds'] > 0 and c.x > -37.,
         cams=[(0., chase(back=3.0, side=-1.6, up=1.0, frame=7.5)),
               (lambda s, c: s['d_grinds'] > 0 and rail_lateral(c.x, c.y)[0] < 8., fixed((-45., 1377., 125., 2.2), frame=9.)),
               (lambda s, c: s['d_grinds'] > 0 and c.x > -50., fixed((-26., 1396., 125., 9.), fov=58., aim_k=2., to=(-20., 1404., 125., 16.), over=5.))],
         expect=['Kickflip', 'Crooked', '360 Flip']),
    # A grab off an ollie, let go of the board in the air and down onto the feet with it in hand (optional).
    dict(name='outro_dismount', optional='dismount', start=(-40., 1392., 125., 180.), speed=6.5, way=straight_way(-40., 1392., 180., 40.),
         events=[(.8, flick('ollie', .3))],
         trig=[{'when': lambda s, c: air_t(s, c) > .06, 'do': [grab('indy', None)]},
               {'when': lambda s, c: air_t(s, c) > .3, 'act': 'toggle'},
               {'when': lambda s, c: s.get('dismounted') is not None and c.mode == 0, 'act': 'run'},
               {'when': lambda s, c: s.get('dismounted') is not None and c.t > s['dismounted'] + 2.2, 'act': 'stop'}],
         end=lambda s, c: s.get('dismounted') is not None and c.t > s['dismounted'] + 3.2, secs=7.,
         cams=[(0., fixed((-58., 1383.5, 125., 1.0), frame=8.))],
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
    elif what == 'toggle':
        if c.mode == 0: s['mounted'] = c.t
        else: s['dismounted'] = c.t; live.skate_release()
        L.skate_toggle()


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
    k = st['k']; st['k'] += 1
    s.update(k=k, dir='%02d_%s' % (k, s['name']), ph='place', pt=0., t=0., f=0, hz=90 if s.get('slow') else 60,
             rec=False, lv=0., loop_n=0, frames=0, rep_n=0, cams_rows=[], loops=[], slowbuf=[], effects=[], fired=None,
             air=None, airs=[], prev_mode=None, steer_on=True, wk=0, log=[], combos=[], lasts=[], retail=[], first=None,
             bail_t=None, up_t=None, grind_seen=False, land_after_grind=None, stall_t=None, mounted=None, dismounted=None, jumped=None, foot_gait=None, max_spd=0., min_spd=1e9,
             max_spd_after_mount=0., bail_kind=None, d_bails=0, d_grinds=0, d_landed=0, error=None, placed=0, ground_wait=0)
    if s.get('road'):
        s['way'], s['start'] = road_way(*s['road'][:1], want=s['road'][1], **({'x0': s['road'][2]} if len(s['road']) > 2 else {}))
    if s.get('rail'):
        s['way'] = rail_way(s['start'], s['lock_s'], want=s.get('want'), out=s.get('rail_out'))
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
    live.skate_input(); L.skate_place(g, yaw + FLIP)
    pc.set_control_rotation(unreal.Rotator(0, -10, yaw))
    s['placed'] += 1
    return True


def inputs(s, c, dt):
    """This frame's skate. input: steering and speed holds on the ground, then the active effects."""
    inp = {'left': (0., 0.), 'right': (0., 0.), 'push': False, 'brake': False, 'slide': False, 'grab_left': False, 'grab_right': False}
    busy = any(e['kind'] in ('flick', 'hold') for e in s['effects'])
    if c.mode == 1 and s['steer_on']:
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


def track(s, c):
    """Airs, counters, the trick names and the states the shot went through."""
    if s['first'] is None:
        s['first'] = (c.landed, c.bails, c.grinds)
    s['d_landed'], s['d_bails'], s['d_grinds'] = c.landed - s['first'][0], c.bails - s['first'][1], c.grinds - s['first'][2]
    if c.mode == 2 and s['prev_mode'] != 2:
        s['air'] = {'t0': c.t, 'z0': c.zb, 'zmax': c.zb, 'x0': c.x, 'y0': c.y, 'lip': abs(c.vz) > 1.5 * max(c.spd, .1),
                    'rate': 0., 'spin': 0., 'yaw': board_yaw(c), 'turned': 0., 'trate': 0., 'tt': c.t}
    elif c.mode == 2 and s['air']:                  # the board's own turn, measured from the state line's yaw
        a = s['air']; y = board_yaw(c)
        if y is not None and a['yaw'] is not None and c.t > a['tt']:
            dy = (y - a['yaw'] + 180.) % 360. - 180.
            a['turned'] += dy; a['trate'] += (dy / (c.t - a['tt']) - a['trate']) * .5
        a['yaw'], a['tt'] = y, c.t
    if c.mode == 2 and s['air']:
        s['air']['zmax'] = max(s['air']['zmax'], c.zb)
    if c.mode != 2 and s['prev_mode'] == 2 and s['air']:
        a = s['air']; a.update(t1=c.t, to=c.mode, h=round(a['zmax'] - a['z0'], 2), spin=round(a['spin'], 1), turned=round(a['turned'], 1))
        s['airs'].append(a); s['air'] = None
        s['log'].append([round(c.t, 3), 'air', round(a['t1'] - a['t0'], 2), a['h'], a['spin'], c.mode, a['turned']])
    if c.mode == 3: s['grind_seen'] = True
    if s['grind_seen'] and s['stall_t'] is None and c.mode in (1, 3) and c.spd < .8: s['stall_t'] = c.t
    if s['grind_seen'] and s['land_after_grind'] is None and c.mode == 1 and s['prev_mode'] == 2: s['land_after_grind'] = c.t
    if c.mode == 4 and s['bail_t'] is None: s['bail_t'] = c.t
    if c.mode == 4 and c.d.get('bail_kind', 'none') != 'none': s['bail_kind'] = c.d['bail_kind']
    if s['bail_t'] is not None and s['up_t'] is None and c.mode in (0, 1): s['up_t'] = c.t
    for key, val in (('combos', c.combo), ('lasts', c.last), ('retail', c.retail)):
        if val and (not s[key] or s[key][-1] != val): s[key].append(val)
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
        s['log'].append([round(c.t, 3), round(c.x, 2), round(c.y, 2), round(c.zb, 2), round(c.spd, 2), c.mode, c.retail, c.combo])
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
    replay = None
    if s.get('replay') and s['airs']:
        a = max(s['airs'], key=lambda a: (a['h'], a['t1'] - a['t0']))
        replay = {'from_t': round(a['t0'] - s['replay']['pre'], 3), 'to_t': round(a['t1'] + s['replay']['post'], 3), 'stretch': 3}
    names = ' / '.join(s['combos'] + s['lasts'])
    missing = [e for e in s.get('expect', []) if e != 'bail' and e.lower() not in names.lower()] + \
              (['bail'] if 'bail' in s.get('expect', []) and not s['d_bails'] else [])
    info = {'name': s['name'], 'k': s['k'], 'dir': s['dir'], 'keep': keep, 'outcome': outcome(s), 'frames': s['frames'],
            'seconds': round(s['frames'] / 30., 2), 'slow': bool(s.get('slow')), 'replay': replay,
            'combos': s['combos'], 'tricks': s['lasts'], 'missing': missing, 'landed': s['d_landed'], 'bails': s['d_bails'],
            'grinds': s['d_grinds'], 'speed_max': round(s['max_spd'], 2), 'speed_min': round(s['min_spd'], 2) if s['min_spd'] < 1e8 else None,
            'airs': [{'t': round(a['t0'], 2), 'secs': round(a['t1'] - a['t0'], 2), 'h': a['h'], 'spin': a['spin'], 'turned': a.get('turned'), 'to': a['to']} for a in s['airs']],
            'retail': s['retail'][:40], 'launched': s.get('launched'), 'fakie_at_launch': s.get('launch_fakie'),
            'bail_kind': s['bail_kind'], 'ride_physical': physical_cvar(), 'error': s['error'], 'end_state': c.text if c else None}
    part = dict(info, cams=s['cams_rows'], loops=s['loops'], slowbuf=s['slowbuf'], log=s['log'])
    json.dump(part, open(os.path.join(OUT, 'parts', s['dir'], 'shot.json'), 'w'))
    st['done'].append(info)
    json.dump(st['done'], open(os.path.join(OUT, 'shots.json'), 'w'), indent=1)
    say('done', s['name'], info['outcome'], 'keep' if keep else 'DROP', s['combos'], 'missing', missing)
    s['effects'] = []
    live.skate_input()


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
