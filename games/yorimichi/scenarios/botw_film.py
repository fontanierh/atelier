"""BOTW demo film: the imported BOTW characters on the island, then a Bokoblin on the skateboard in the Mega Park.

    atelier play yorimichi -- -rider=Bokoblin -nofox -RenderOffscreen -ForceRes       (1920x1080)
    atelier live py "TAKE='take1'" && atelier live py - < games/yorimichi/scenarios/botw_film.py
    Link's tricks: -rider=Link, and "TAKE='...'; FLIP_TRICK='varial_kickflip'; POOL_TRICK='flair'"
    ... wait for build/yorimichi/botw/film/<take>/done.json, then:
    python games/yorimichi/scenarios/skate_mix_showreel.py build/yorimichi/botw/film/<take>

Shots: a line-up of characters along the road above the start, each playing its clips in turn (ABotwCreature's
showcase), with a Hinox at the end; a Bokoblin camp that notices the player walking up and comes for it; the Bokoblin
player's 360 flip on the Mega Park road; and the drop off the upper deck into the pool's north-west quarter for a
Christ air with a 360 spin. Optional globals: ONLY, the shots to run; REHEARSE, no frames saved (the rides still log to
log.json); POOL_TRICK, 'christ' (CHRIST) or 'flair' (FLAIR) on the pool quarter; TUNE, overrides for that trick;
FLIP_TRICK, the flick for the flat trick ('~360_flip' mirrors it for goofy).

Runs in the game's Python (the live bridge) at a fixed 60 fps step, like megapark_access_film.py: the walking is
driven input, the skating scripted skate. input (pursuit steering, Flick-It gestures, grabs and the dismount), and
every second recorded sim frame is saved as a JPG (30 fps) with its sounds and board loops for the mixer.
"""
import json, math, os, re
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1')
ONLY = globals().get('ONLY') or ['lineup', 'camp', 'flip', 'christ']
REHEARSE = globals().get('REHEARSE', False)
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/botw/film', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.jpg') or f in ('done.json', 'audio.json', 'camera.csv', 'loops.csv', 'log.json'):
        os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
cm = unreal.GameplayStatics.get_player_camera_manager(L.game_world(), 0)
MV = unreal.MegaParkValidation
UNRECORDED = -1000000
NEUTRAL_LOOPS = '0 1 0 1 0 1 0 1 0 1'
AIR = 2                                                      # ESkateMode::Air in skate_state's mode=

# The Christ air (the skate README: hold the left-trigger grab, B makes it a Christ air), timed like the skate GIF's:
# the grab `grab` s into the air, B at `dismount` s, B let go when the board is `brake_off` s from falling back to its
# take-off height and the grab at `grab_off` s. The 360 is the left stick at `spin` from take-off, or wound up on the
# quarter's face when `wind` (from x < `wind_x` with the board above `wind_z`; the carve that winds it can lose the
# board, so it is off). The twist is the body's turn about its own up axis (the
# quarter's own half turn is a pitch over, not a twist). The spin carries on once started and the feet must be back on
# a board that has stopped turning, so until B is let go the stick steers the twist it will have then (now + rate x
# time left) to `target` (held while short of it by more than `tol`, the other way while past it), and after it the
# stick brakes the spin to under `still` degrees a second.
CHRIST = dict(side='grab_left', grab=.2, dismount=.5, brake_off=.7, grab_off=.4, spin=-1., wind=False, wind_x=-117.,
              wind_z=76.3, target=360., tol=15., still=25.)
# The flair, a backflip 180 (the skate README's body flip): the grab held from take-off and the left stick pulled
# straight back twice, quickly, just after it (`pulls`, (start, end) s into the air: the gesture set's BackFlip, which
# counts only with a grab held, fires on each pull from the centre), then the twist steered to `target` like the
# Christ air's 360, done `brake_off` s before it is back at its take-off height; no B.
FLAIR = dict(CHRIST, grab=0., dismount=None, target=180., pulls=[(.05, .084), (.117, .15)])
POOL_TRICK = globals().get('POOL_TRICK', 'christ')
POOL = dict(FLAIR if POOL_TRICK == 'flair' else CHRIST)
POOL.update(globals().get('TUNE') or {})


def ue(x, y, z):
    """Island metres (x east, y north) to Unreal cm."""
    return unreal.Vector(x * 100., -y * 100., z * 100.)


def wrap(a):
    return (a + 180.) % 360. - 180.


def where():
    l = L.player().get_actor_location(); return l.x / 100., -l.y / 100., l.z / 100.


def velocity():
    v = L.player().get_velocity(); return v.x / 100., -v.y / 100., v.z / 100.


def yaw_to(x, y, tx, ty):
    """UE yaw from (x, y) towards (tx, ty), island metres."""
    return math.degrees(math.atan2(-(ty - y), tx - x))


def skate_mode():
    m = re.search(r'\bmode=(\d)', L.skate_state()); return int(m.group(1)) if m else 0


def last_trick():
    m = re.search(r'\blast=(\S+)', L.skate_state()); return m.group(1) if m else None


def expand(events):
    out = []
    for when, what in events:
        if isinstance(what, tuple) and what[0] == 'flick':
            pts = live.FLICKS[what[1].lstrip('~')]; left = what[2]; load = what[3]
            if what[1].startswith('~'): pts = [(-px, py) for px, py in pts]      # '~': the goofy gesture
            out.append((when, {'right': pts[0], 'left': left}))
            t = when + load
            for q in pts[1:]:
                out.append((t, {'right': q, 'left': left})); t += 1 / 30
            out.append((t, {'right': (0, 0), 'left': left}))
        else:
            out.append((when, dict(what)))
    return sorted(out, key=lambda e: e[0])


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


class Ride:
    """Scripted skate. input along a line: pursuit steering with speed holds (a negative want is a cap), timed events,
    position triggers ({'when': fn(x, y, z, vz, spd, t), 'inputs', 'secs'}) and an optional hook that has the last
    word on the inputs (hook(x, y, z, vz, spd, t, inputs))."""

    def __init__(self, way, events=(), trig=(), gain=25., look=8., hook=None):
        self.way, self.gain, self.look, self.k, self.hook = way, gain, look, 0, hook
        self.tl = expand(list(events)); self.trig = [dict(t, fired=None) for t in trig]

    def tick(self, t):
        x, y, z = where(); vx, vy, vz = velocity(); spd = math.hypot(vx, vy)
        wx, wy, want, self.k = pursue(self.way, self.k, x, y, self.look)
        target = yaw_to(x, y, wx, wy)
        v = L.player().get_velocity()
        heading = math.degrees(math.atan2(v.y, v.x)) if spd > .5 else L.player().get_actor_rotation().yaw
        steer = max(-1., min(1., wrap(target - heading) / self.gain))
        inputs = {'left': (steer, 0.)}
        if want is not None and want < 0:
            if spd > -want + .3: inputs['brake'] = True
        elif want is not None:
            if spd < want - .5: inputs['push'] = True
            elif spd > want + 1.5: inputs['brake'] = True
        ev = None
        for when, what in self.tl:
            if when <= t: ev = what
        if ev:
            inputs.update(ev)
            if ev.get('left') == 'steer': inputs['left'] = (steer, 0.)
        for tr in self.trig:
            if tr['fired'] is None and tr['when'](x, y, z, vz, spd, t):
                tr['fired'] = t
            if tr['fired'] is not None and t - tr['fired'] <= tr.get('secs', .5):
                inputs.update(tr['inputs'])
        if self.hook: self.hook(x, y, z, vz, spd, t, inputs)
        live.skate_input(**inputs); self.inputs = inputs
        return x, y, z, spd


class ChristAir:
    """The air controller for the pool quarter (CHRIST, FLAIR): wind the spin, grab, B or the back flip, steer the
    twist to `target`, let go."""

    def __init__(self, tune):
        self.c = tune; self.t0 = None; self.z0 = 0.; self.fw = None; self.turned = 0.; self.rate = 0.; self.landed = None

    def twist(self):
        """Add the body's turn about its own up axis since the last frame to `turned` (signed degrees)."""
        a = L.player(); f = a.get_actor_forward_vector(); u = a.get_actor_up_vector(); u = (u.x, u.y, u.z)
        flat = lambda v: [v[i] - sum(v[k] * u[k] for k in range(3)) * u[i] for i in range(3)]
        f = flat((f.x, f.y, f.z))
        if self.fw is not None:
            p = self.fw; c = (p[1] * f[2] - p[2] * f[1], p[2] * f[0] - p[0] * f[2], p[0] * f[1] - p[1] * f[0])
            step = math.degrees(math.atan2(sum(c[i] * u[i] for i in range(3)), sum(p[i] * f[i] for i in range(3))))
            self.turned += step; self.rate += (step * 60. - self.rate) * .3
        self.fw = f

    def __call__(self, x, y, z, vz, spd, t, inputs):
        c = self.c; mode = skate_mode()
        winding = self.t0 is None and c['wind'] and x < c['wind_x'] and z > c['wind_z']
        if self.t0 is None and mode == AIR and x < -114. and z > 77.:
            self.t0, self.z0 = t, z
        if winding or self.t0 is not None:                       # the twist counts from the wind-up
            self.twist()
        if self.t0 is None:
            if winding: inputs['left'] = (c['spin'], 0.)
            return
        if self.landed is not None:
            if t - self.landed < .5: self.twist()                  # the twist it lands with
            return
        if mode != AIR and t - self.t0 > .3:
            self.landed = t; return
        tair = t - self.t0; up = max(0., z - self.z0)
        tl = (vz + math.sqrt(vz * vz + 2 * 9.8 * up)) / 9.8      # seconds until it is back at the take-off height
        falling = vz < 0
        inputs[c['side']] = tair >= c['grab'] and not (falling and tl < c['grab_off'])
        if c['dismount'] is not None:
            inputs['brake'] = tair >= c['dismount'] and not (falling and tl < c['brake_off'])
        if c.get('pulls') and tair < c['pulls'][-1][1]:              # the flair's quick pulls back
            inputs['left'] = (0., -1. if any(a <= tair < b for a, b in c['pulls']) else 0.)
            return
        way = math.copysign(1., c['spin']); lead = tl - c['brake_off']     # seconds until B is let go
        if lead > 0:
            ahead = (self.turned + self.rate * lead) * way                  # the twist it will have then
            push = 1. if ahead < c['target'] - c['tol'] else -1. if ahead > c['target'] + c['tol'] else 0.
        else:
            push = -1. if self.rate * way > c['still'] else 1. if self.rate * way < -c['still'] else 0.
        inputs['left'] = (c['spin'] * push, 0.)


# ---------------------------------------------------------------------------------------------- the island road
ROAD = (-255.26, -99.51, 10.2, 4.7)       # the player start: island x, y, probe z (m) and the UE yaw up the road
PAIRS = [('Korok', 'Zelda'), ('Paya', 'Sidon'), ('BokoblinBlue', 'BokoblinBlack'), ('Lizalfos', 'Stalkoblin'),
         ('Moblin', 'Lynel')]


def road(along, side, up=0.):
    """The ground `along` m up the road from the start and `side` m to its right (a Vector), plus `up` m."""
    x0, y0, z0, yaw = ROAD; h = math.radians(yaw)
    x = x0 + math.cos(h) * along - math.sin(h) * side; y = y0 - (math.sin(h) * along + math.cos(h) * side)
    g = L.ground_at(ue(x, y, z0 + 15.))
    return unreal.Vector(g.x, g.y, g.z + up * 100.)


st = {'shot': None, 'i': -1, 'f': 0, 't': 0., 'sim': 0, 'film': 0, 'view': None, 'aim': None, 'camera': [], 'loops': [],
      'marks': [], 'log': [], 'rec': False}


def mark(name):
    st['marks'].append({'shot': name, 'film_frame': st['film'], 'sim_frame': st['sim']})


def view_follow(pitch=None, yaw=None):
    if st['view'] != 'follow':
        MV.restore_player_camera(); st['view'] = 'follow'
    if pitch is not None:
        pc.set_control_rotation(unreal.Rotator(0, pitch, yaw))


def view_fixed(cam, smooth=.12, frame=None):
    """A review camera at island metres `cam` = ((x, y, z), fov, aim height) that turns to follow the player; with
    `frame` it also zooms (never wider than fov) to keep about `frame` metres across the picture at the player."""
    (cx, cy, cz), fov, up = cam
    x, y, z = where(); aim = (x, y, z + up)
    if frame:
        fov = min(fov, math.degrees(2 * math.atan(frame * .5 / max(1., math.dist((cx, cy, cz), aim)))))
    if st['view'] != cam or st['aim'] is None:
        st['aim'] = aim; st['fov'] = fov
    else:
        a = st['aim']; st['aim'] = tuple(a[k] + (aim[k] - a[k]) * smooth for k in range(3))
        st['fov'] += (fov - st['fov']) * smooth
    MV.review_camera(ue(cx, cy, cz), ue(*st['aim']), st['fov']); st['view'] = cam


def stand_up():
    if skate_mode():
        live.skate_input(); live.skate_release(); L.skate_toggle()
    live.drive(0)


def lineup_setup():
    stand_up(); L.botw_clear()
    _, _, _, yaw = ROAD
    for k, pair in enumerate(PAIRS):
        for name, side in zip(pair, (-3.3, 3.3)):
            # They face back down the road, turned a little towards its middle.
            L.botw_spawn(name, road(9. + k * 4.2 + (1.5 if k == 4 else 0.), side), yaw + 180. + (20. if side > 0 else -20.), 'showcase')
    L.botw_spawn('Hinox', road(34., 0.), yaw + 180., 'showcase')
    L.teleport_player(road(0., 0., 1.), yaw)
    st['l'] = {'cam': None}


def lineup(t):
    """Eight seconds after the spawn (their clips and textures load), dolly up the road between them for nine."""
    if t < 8.:
        st['rec'] = False; return
    if not st['rec']: mark('lineup')
    st['rec'] = True
    s = min(1., (t - 8.) / 9.); along = 2. + 11. * (s * s * (3 - 2 * s))
    eye = road(along, -.4, 1.7); look = road(along + 14., 0., 2.2 + 3.5 * s)
    l = st['l']
    l['cam'] = eye if l['cam'] is None else unreal.Vector(eye.x, eye.y, l['cam'].z + (eye.z - l['cam'].z) * .08)
    MV.review_camera(l['cam'], look, 62.); st['view'] = 'lineup'
    if t >= 17.: return 'done'


def camp_setup():
    stand_up(); L.botw_clear()
    _, _, _, yaw = ROAD
    for name, along, side, turn in (('Bokoblin', 19., .5, 150.), ('BokoblinBlue', 17.5, -2.2, 200.), ('BokoblinSilver', 21., 2.8, 120.)):
        L.botw_spawn(name, road(along, side), yaw + turn, 'camp')
    L.teleport_player(road(0., 0., 1.), yaw)
    view_follow(-14., yaw)
    st['c'] = {}


def camp(t):
    """The player walks up the road until they come for it, then waits for them."""
    _, _, _, yaw = ROAD
    if t < 2.:
        st['rec'] = False; view_follow(-14., yaw); return
    if not st['rec']: mark('camp')
    st['rec'] = True
    view_follow(-14. + min(1., (t - 2.) / 4.) * 4., yaw)
    live.drive(1. if t < 6. else 0., 0., 'walk')
    if t >= 13.: live.drive(0); return 'done'


# ---------------------------------------------------------------------------------------------- the Mega Park
# The park road east of the footbridge (megapark_access_film.py): placed turned against travel and launched at 8.5 m/s.
FLIP_START = (-152., 1476.5, 133., 0.)
FLIP_WAY = [(-156, 1477, None), (-140, 1476.5, None), (-120, 1476, None), (-95, 1475.5, None)]
FLIP_EVENTS = [(1.9, ('flick', globals().get('FLIP_TRICK', '360_flip'), (0., 0.), .22)), (2.7, {'left': 'steer'})]
CAM_FLIP = ((-137.5, 1471.2, 132.3), 48., .7)        # the road side where the rider flips
# The chevron roll-in off the upper deck, the snake run-out and the pool's north-west quarter.
PARK_WAY = [(-44.5, 1305.1, None), (-54.4, 1295.2, None), (-63.6, 1286.4, None), (-75, 1279, None), (-90, 1272.5, None),
            (-102, 1269, None), (-110, 1272.5, None), (-118, 1279, None), (-128, 1287.5, None), (-134, 1297, -19.),
            (-137, 1310, -19.)]
PARK_START = (-44.5, 1305.1, 112., 135.)
STRAIGHT = {'when': lambda x, y, z, vz, spd, t: x < -116. and y > 1276, 'inputs': {'left': (0., 0.)}, 'secs': 3.6}
CAM_POOL = ((-111, 1275.5, 77.2), 55., 1.)           # the pool floor beside the line into the quarter
POOL_FRAME = 11.                                    # metres across the picture at the rider in the air


def skate_setup(name):
    live.drive(0)
    sx, sy, sz, syaw = FLIP_START if name == 'flip' else PARK_START
    g = L.ground_at(ue(sx, sy, sz))
    live.skate_input(); L.skate_place(g, syaw + 180.)
    pc.set_control_rotation(unreal.Rotator(0, -12, syaw))
    ride = Ride(FLIP_WAY, FLIP_EVENTS, gain=25., look=8.) if name == 'flip' else \
        Ride(PARK_WAY, trig=[STRAIGHT], gain=28., look=8., hook=ChristAir(dict(POOL)))
    st['p'] = {'s': 'settle', 'name': name, 'start': (sx, sy, sz, syaw), 'ride': ride}


def skate(t):
    p = st['p']; name = p['name']
    if p['s'] == 'settle':
        st['rec'] = False; live.skate_input()
        if name == 'flip': view_fixed(CAM_FLIP, 1.)
        else: view_follow()
        if t >= 1.0:
            h = math.radians(p['start'][3]); v = 850. if name == 'flip' else 250.
            L.skate_launch(unreal.Vector(v * math.cos(h), v * math.sin(h), 0)); p['s'] = 'launch'; p['t0'] = t
        return
    if p['s'] == 'launch':
        st['rec'] = False; live.skate_input()
        if t - p['t0'] < .15: return
        p['s'] = 'ride'
    tr = t - p['t0']
    ride = p['ride']
    x, y, z, spd = ride.tick(tr)
    st['log'].append([name, round(tr, 3), round(x, 2), round(y, 2), round(z, 2), round(velocity()[2], 2), round(spd, 2),
                      skate_mode(), round(ride.hook.turned, 1) if ride.hook else None, ' | '.join(L.skate_state().split(' | ')[1:3]),
                      ''.join(k[0] if k != 'grab_left' else 'L' for k, v in ride.inputs.items() if v is True) + ' %.2f,%.2f' % tuple(ride.inputs['left'])])
    if name == 'flip':
        if not st['rec'] and tr >= .7: mark('flip')
        st['rec'] = tr >= .7; view_fixed(CAM_FLIP, .3)
        if tr >= 4.: return 'done'
        return
    air = ride.hook
    if not st['rec'] and tr >= 4.8: mark('drop')
    st['rec'] = tr >= 4.8
    if x < -88.5:
        if st['view'] != CAM_POOL: mark('christ')
        view_fixed(CAM_POOL, .5, frame=POOL_FRAME)
    else:
        view_follow()
    if air.landed is not None and tr >= air.landed + 1.4: return 'done'
    if tr >= 22.: return 'done'


SHOTS = [s for s in (('lineup', lineup_setup, lineup), ('camp', camp_setup, camp),
                     ('flip', lambda: skate_setup('flip'), skate), ('christ', lambda: skate_setup('christ'), skate))
         if s[0] in ONLY]


def next_shot():
    st['i'] += 1
    if st['i'] >= len(SHOTS): return False
    name, setup, _ = SHOTS[st['i']]
    st['shot'] = name; st['f'] = 0; st['t'] = 0.; setup()
    return True


def run(dt):
    if st['shot'] is None and not next_shot():
        return finish()
    name, _, fn = SHOTS[st['i']]
    t = st['f'] / 60.; st['t'] = t; st['f'] += 1
    r = fn(t)
    if st['rec']:
        L.audio_frame(st['sim'])
        st['loops'].append(L.skate_loops().strip() or NEUTRAL_LOOPS)
        if st['sim'] % 2 == 0:
            if not REHEARSE: L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % st['film']))
            loc = cm.get_camera_location(); rot = cm.get_camera_rotation()
            st['camera'].append('%d,%.1f,%.1f,%.1f,%.2f' % (st['film'], loc.x, loc.y, loc.z, rot.yaw))
            st['film'] += 1
        st['sim'] += 1
    else:
        L.audio_frame(UNRECORDED)
    if r == 'done':
        st['rec'] = False
        if not next_shot(): finish()


def finish():
    live.stop('botw_film')
    live.skate_input(); live.skate_release(); live.drive(0)
    MV.restore_player_camera(); L.film_hud(False); L.fixed_step(0)
    n = L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    open(os.path.join(OUT, 'camera.csv'), 'w').write('frame,x,y,z,yaw\n' + '\n'.join(st['camera']) + '\n')
    open(os.path.join(OUT, 'loops.csv'), 'w').write('\n'.join(st['loops']) + '\n')
    json.dump(st['log'], open(os.path.join(OUT, 'log.json'), 'w'))
    json.dump({'film_frames': st['film'], 'sim_frames': st['sim'], 'fps_sim': 60, 'fps_film': 30, 'sounds': n, 'shots': st['marks'],
               'rehearsal': bool(REHEARSE), 'pool': dict(POOL, trick=POOL_TRICK), 'state': L.skate_state()}, open(os.path.join(OUT, 'done.json'), 'w'), indent=1)


L.film_hud(True); L.fixed_step(60); L.audio_log('start')
live.behave('botw_film', run)
print('BOTW FILM started', OUT, [s[0] for s in SHOTS])
