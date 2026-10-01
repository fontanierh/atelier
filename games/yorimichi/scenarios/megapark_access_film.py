"""Mega Park access film: Cairo boards the zeppelin at Hidamari, flies to the Mega Park stop, runs down the station
stairs and over the footbridge, then skates the park road (Kickflip, 360 Flip, Powerslide), drops off the upper deck
into a BS Grab high over the pool's north-west quarter, and takes the same quarter again with a Kickflip.

    atelier play yorimichi --set 'performance=1;render_scale=100;painterly=0.35;paint_radius=2;toon=0;outline=0;
        exposure=0.9;saturation=1;wind=3.5;sun_height=48;sun_yaw=15;desktop=1;show_fps=0' \\
        -- -zeppelindock=1 -RenderOffscreen -ForceRes          (1920x1080; the ship waits at Hidamari)
    atelier live py "TAKE='take1'" && atelier live py - < games/yorimichi/scenarios/megapark_access_film.py
    ... wait for build/yorimichi/megapark/access-film/<take>/done.json, then:
    python games/yorimichi/scenarios/megapark_access_film_mix.py build/yorimichi/megapark/access-film/<take>

Optional globals: ONLY, the shots to run (zeppelin, walk, road, drop, pool; rehearsals run a few), and LOG, the game
log the zeppelin's phase lines are read from (the -abslog file, else the project log).

Runs in the game's Python (the live bridge) at a fixed 60 fps step. The walking is driven input and the skating is
scripted skate. input (pursuit steering plus Flick-It gestures), so capture stalls do not change the ride. On recorded
frames every second sim frame is saved as a JPG (30 fps); the sounds the game starts are logged with the recorded sim
frame (unrecorded frames log at -1000000, which the mixer drops) and the board's loops per recorded frame. Every
skate shot is placed on its line, settles for a second and is launched at speed, so it coasts whatever stance the
launch gives; the park shots end a set time after the pool landing.
"""
import json, math, os, re
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1')
ONLY = globals().get('ONLY') or ['zeppelin', 'walk', 'road', 'drop', 'pool']
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/megapark/access-film', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.jpg') or f in ('done.json', 'audio.json', 'camera.csv', 'loops.csv', 'log.json', 'progress.txt'):
        os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
cm = unreal.GameplayStatics.get_player_camera_manager(L.game_world(), 0)
MV = unreal.MegaParkValidation
UNRECORDED = -1000000
NEUTRAL_LOOPS = '0 1 0 1 0 1 0 1 0 1'

HIDAMARI_ENTRY = (1279.0, 307.2)
PARK_STATION = (-194.0, 1488.0)


def game_log():
    m = re.search(r'-abslog=("[^"]+"|\S+)', unreal.SystemLibrary.get_command_line())
    if m: return m.group(1).strip('"')
    return os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_log_dir()), 'Yorimichi.log')


LOG = globals().get('LOG') or game_log()


def ue(x, y, z):
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


def expand(events):
    out = []
    for when, what in events:
        if isinstance(what, tuple) and what[0] == 'flick':
            pts = live.FLICKS[what[1]]; left = what[2]; load = what[3]
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
    """Scripted skate. input along a line: pursuit steering with speed holds (a negative want is a cap: brake above
    it, never push), timed events and position triggers ({'when': fn(x, y, z, vz, spd, t), 'inputs', 'secs'})."""

    def __init__(self, way, events=(), trig=(), gain=25., look=8.):
        self.way, self.gain, self.look, self.k = way, gain, look, 0
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
                if isinstance(tr['inputs'], tuple):
                    self.tl = sorted(self.tl + expand([(t, tr['inputs'])]), key=lambda e: e[0])
            if tr['fired'] is not None and not isinstance(tr['inputs'], tuple) and t - tr['fired'] <= tr.get('secs', .5):
                inputs.update(tr['inputs'])
        live.skate_input(**inputs)
        return x, y, z, spd


# The park line: the chevron roll-in off the upper deck, the snake run-out and the pool's north-west quarter. The
# flick fires on the transition (z above the 75.8 m floor), the grab once he is well up; the stick stays centred
# through both, since a steer held through a flip turns it into a Darkcatch.
PARK_WAY = [(-44.5, 1305.1, None), (-54.4, 1295.2, None), (-63.6, 1286.4, None), (-75, 1279, None), (-90, 1272.5, None),
            (-102, 1269, None), (-110, 1272.5, None), (-118, 1279, None), (-128, 1287.5, None), (-134, 1297, -19.),
            (-137, 1310, -19.)]
PARK_START = (-44.5, 1305.1, 112., 135.)                 # x, y, probe z, UE yaw of travel
STRAIGHT = {'when': lambda x, y, z, vz, spd, t: x < -116. and y > 1276, 'inputs': {'left': (0., 0.)}, 'secs': 3.6}
DROP_TRIG = [STRAIGHT,
             {'when': lambda x, y, z, vz, spd, t: x < -118. and z > 78.6 and y < 1290,
              'inputs': {'grab_left': True, 'left': (0., 0.)}, 'secs': .9}]
POOL_TRIG = [STRAIGHT,
             {'when': lambda x, y, z, vz, spd, t: x < -116.5 and z > 76.2 and y < 1290, 'inputs': ('flick', 'kickflip', (0., 0.), .22)},
             {'when': lambda x, y, z, vz, spd, t: z > 83.0 and vz > 0, 'inputs': {'grab_left': True, 'left': (0., 0.)}, 'secs': 1.25}]
# The park road east of the footbridge: it coasts from an 8.5 m/s launch.
ROAD_START = (-152., 1476.5, 133., 0.)
ROAD_WAY = [(-156, 1477, None), (-140, 1476.5, None), (-120, 1476, None), (-95, 1475.5, None), (-80, 1475.5, None),
            (-60, 1475.5, None)]
ROAD_EVENTS = [(1.9, ('flick', 'kickflip', (0., 0.), .22)), (2.6, {'left': 'steer'}),
               (4.6, ('flick', '360_flip', (0., 0.), .22)), (5.5, {'left': 'steer'}),
               (7.3, {'slide': True, 'left': (-1., -1.)}), (8.6, {'left': 'steer'})]
# Down the station stairs (the east railing holds him in until their foot), along the footpath and over the footbridge.
WALK_WAY = [(-194, 1483.2, None), (-194, 1474.3, None), (-191.5, 1475.0, None), (-189, 1476.7, None), (-170, 1477, None),
            (-154, 1477, None), (-140, 1476.5, None)]

# Cameras (island metres, field of view, aim height): fixed review cameras that turn to follow the player.
CAM_TAKEOFF = ((1318, 272, 52), 55., 6.)         # south-east of Hidamari's station, the volcano behind the ship
CAM_LANDING = ((-150, 1471, 131.8), 58., 6.)      # the park road at the footbridge
CAM_PATH = ((-180, 1474.2, 132.4), 70., 1.)       # the station's footpath, looking back at the stairs
CAM_BRIDGE = ((-146, 1473.5, 132.2), 40., 1.)     # the road end of the footbridge
CAM_POOL = ((-111, 1275.5, 77.2), 45., 1.)        # the pool floor beside the line into the north-west quarter

st = {'shot': None, 'i': -1, 'f': 0, 't': 0., 'sim': 0, 'film': 0, 'view': None, 'aim': None, 'camera': [], 'loops': [],
      'marks': [], 'log': [], 'rec': False}
logf = open(LOG, 'r', errors='ignore'); logf.seek(0, 2)
Z = {'phase': 0, 'dock': 1}


def read_phase():
    for m in re.finditer(r'ZEPPELIN phase=(\d+) dock=(\d+)', logf.read()):
        Z['phase'], Z['dock'] = int(m.group(1)), int(m.group(2))


def view_follow(pitch=None, yaw=None):
    if st['view'] != 'follow':
        MV.restore_player_camera(); st['view'] = 'follow'
    if pitch is not None:
        pc.set_control_rotation(unreal.Rotator(0, pitch, yaw))


def view_fixed(cam, smooth=.12):
    (cx, cy, cz), fov, up = cam
    x, y, z = where(); aim = (x, y, z + up)
    if st['view'] != cam or st['aim'] is None:
        st['aim'] = aim
    else:
        a = st['aim']; st['aim'] = tuple(a[k] + (aim[k] - a[k]) * smooth for k in range(3))
    MV.review_camera(ue(cx, cy, cz), ue(*st['aim']), fov); st['view'] = cam


def mark(name):
    st['marks'].append({'shot': name, 'film_frame': st['film'], 'sim_frame': st['sim']})


def stand_up():
    if ' mode=1 ' in ' ' + L.skate_state() + ' ':
        live.skate_input(); live.skate_release(); L.skate_toggle()
    live.drive(0)


# ---------------------------------------------------------------------------------------------- the zeppelin
# Phases from the game log: 2 boarding walk, 3 climb, 4 cruise, 5 descent, 6 disembark, 0 docked. Interact is pressed
# once to board and never again (it skips the flight); Stop next twice in the cruise takes it to 2x.
def zeppelin_setup():
    stand_up()
    ex, ey = HIDAMARI_ENTRY
    g = L.ground_at(ue(ex, ey - 11.5, 40.))
    L.teleport_player(g, -90.)
    pc.set_control_rotation(unreal.Rotator(0, -6, -90))
    st['z'] = {'s': 'settle', 't0': 0., 'pressed': 0}


def zeppelin(t):
    z = st['z']; read_phase(); x, y, h = where()
    if z['s'] == 'settle':
        st['rec'] = False
        if t >= 6.0: z['s'] = 'approach'; mark('hidamari'); z['t0'] = t
        return
    if z['s'] == 'approach':
        st['rec'] = True
        ex, ey = HIDAMARI_ENTRY; d = math.hypot(ex - x, ey - y)
        yaw = yaw_to(x, y, ex, ey)
        view_follow(-6., yaw); live.drive(1., 0., 'run')
        if d < 1.5:
            live.drive(0); live.press('interact'); z['s'] = 'boarding'; z['t0'] = t
        return
    if z['s'] == 'boarding':
        st['rec'] = t - z['t0'] < .8; view_follow(-8., -90.)
        if Z['phase'] >= 3:
            z['s'] = 'climb'; z['t0'] = t; mark('takeoff')
        return
    if z['s'] == 'climb':
        st['rec'] = t - z['t0'] < 4.5
        view_fixed(CAM_TAKEOFF, .2)
        if Z['phase'] >= 4:
            z['s'] = 'cruise'; z['t0'] = t; z['yaw'] = None
        return
    if z['s'] == 'cruise':           # the passenger camera follows the control rotation: aim it round the ship
        tc = t - z['t0']
        if z['pressed'] < 2 and tc >= .1 * (z['pressed'] + 1):
            live.press('stop_next'); z['pressed'] += 1
        vx, vy, _ = velocity()
        if math.hypot(vx, vy) > 5.:
            yaw = math.degrees(math.atan2(-vy, vx))
            z['yaw'] = yaw if z['yaw'] is None else z['yaw'] + wrap(yaw - z['yaw']) * .05
        sy = z['yaw'] if z['yaw'] is not None else -141.
        dpark = math.hypot(PARK_STATION[0] - x, PARK_STATION[1] - y)
        if .6 <= tc < 5.0:
            st['rec'] = True; view_follow(-8., sy + 180. + 32. - (tc - .6) * 4.)
            if st.get('cruise_mark') != 1: st['cruise_mark'] = 1; mark('cruise_front')
        elif 8.0 <= tc < 12.5:
            st['rec'] = True; view_follow(-24., sy + 100. - (tc - 8.) * 6.)
            if st.get('cruise_mark') != 2: st['cruise_mark'] = 2; mark('cruise_side')
        elif dpark < 440.:
            st['rec'] = True; view_follow(-22., sy)
            if st.get('cruise_mark') != 3: st['cruise_mark'] = 3; mark('approach_park')
        else:
            st['rec'] = False; view_follow(-10., sy + 180.)
        if Z['phase'] >= 5:
            z['s'] = 'descent'; z['t0'] = t; mark('landing')
        return
    if z['s'] == 'descent':
        st['rec'] = h < 168.; view_fixed(CAM_LANDING, .15)
        if Z['phase'] == 6 or (Z['phase'] == 0 and Z['dock'] == 2):
            z['s'] = 'disembark'; z['t0'] = t
        return
    if z['s'] == 'disembark':
        st['rec'] = False; view_follow(-8., 90.)
        if Z['phase'] == 0 and Z['dock'] == 2: return 'done'


# ---------------------------------------------------------------------------------------------- the walk
def walk_setup():
    stand_up()                                     # the disembark isn't filmed: start from the stairs' top
    g = L.ground_at(ue(-194., 1483.2, 134.)); L.teleport_player(g, 90.)
    st['w'] = {'s': 'settle', 'k': 0}
    pc.set_control_rotation(unreal.Rotator(0, -8, 90))


def walk(t):
    w = st['w']; x, y, z = where()
    if w['s'] == 'settle':
        st['rec'] = False
        if t >= 2.0: w['s'] = 'walk'; mark('walk')
        return
    st['rec'] = True
    wx, wy, _, w['k'] = pursue(WALK_WAY, w['k'], x, y, 1.2 if x < -190. else 2.5)
    yaw = yaw_to(x, y, wx, wy)
    if x < -189.5:
        view_follow(-8., yaw)
    else:
        pc.set_control_rotation(unreal.Rotator(0, -8, yaw)); view_fixed(CAM_PATH if x < -179. else CAM_BRIDGE, .25)
    live.drive(1., 0., 'run')
    if int(t * 60) % 6 == 0: st['log'].append(['walk', round(t, 2), round(x, 2), round(y, 2), round(z, 2)])
    if x > -156.:
        live.drive(0); return 'done'


# ---------------------------------------------------------------------------------------------- the skate shots
def skate_setup(name):
    live.drive(0)
    sx, sy, sz, syaw = ROAD_START if name == 'road' else PARK_START
    g = L.ground_at(ue(sx, sy, sz))
    live.skate_input(); L.skate_place(g, syaw + 180.)          # turned against travel, as rehearsed
    pc.set_control_rotation(unreal.Rotator(0, -12, syaw))
    ride = Ride(ROAD_WAY, ROAD_EVENTS, gain=25., look=8.) if name == 'road' else \
        Ride(PARK_WAY, trig=DROP_TRIG if name == 'drop' else POOL_TRIG, gain=28., look=8.)
    st['p'] = {'s': 'settle', 'name': name, 'start': (sx, sy, sz, syaw), 'ride': ride}


def skate(t):
    p = st['p']; name = p['name']
    if p['s'] == 'settle':                                     # a second of neutral input before the launch
        st['rec'] = False; live.skate_input()
        if t >= 1.0:
            h = math.radians(p['start'][3]); v = 850. if name == 'road' else 250.
            L.skate_launch(unreal.Vector(v * math.cos(h), v * math.sin(h), 0)); p['s'] = 'launch'; p['t0'] = t
        return
    if p['s'] == 'launch':                                     # the stance shows once the launch speed is on
        st['rec'] = False; live.skate_input()
        if t - p['t0'] < .15: return
        print('ACCESS FILM', name, 'launched', L.skate_state().split(' manual')[0])
        p['s'] = 'ride'
    tr = t - p['t0']
    x, y, z, spd = p['ride'].tick(tr)
    st['log'].append([name, round(tr, 3), round(x, 2), round(y, 2), round(z, 2), round(spd, 2), L.skate_state().split(' | ')[1]])
    if name == 'road':
        st['rec'] = tr >= .8; view_follow()                    # once the camera has swung round behind him
        if st['rec'] and st.get('road_mark') is None: st['road_mark'] = 1; mark('road')
        if tr >= 8.7: return 'done'
        return
    # The pool air: on the floor, up past 80 m, back down; each park shot ends a set time after that landing.
    if z < 76.5 and not p.get('air'): p['floor'] = True
    if p.get('floor') and z > 80.: p['air'] = True
    if p.get('air') and p.get('landed') is None and z < 76.: p['landed'] = tr
    if tr >= 22.: return 'done'
    if name == 'drop':
        st['rec'] = tr >= 4.8; view_follow()
        if st['rec'] and st.get('drop_mark') is None: st['drop_mark'] = 1; mark('drop')
        if p.get('landed') is not None and tr >= p['landed'] + .9: return 'done'
    else:
        if st.get('pool_mark') is None and x < -88.5: st['pool_mark'] = 1; mark('pool')
        st['rec'] = st.get('pool_mark') is not None
        view_fixed(CAM_POOL, .35)
        if p.get('landed') is not None and tr >= p['landed'] + 1.2: return 'done'


SHOTS = [s for s in (('zeppelin', zeppelin_setup, zeppelin), ('walk', walk_setup, walk),
                     ('road', lambda: skate_setup('road'), skate), ('drop', lambda: skate_setup('drop'), skate),
                     ('pool', lambda: skate_setup('pool'), skate)) if s[0] in ONLY]


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
            L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % st['film']))
            loc = cm.get_camera_location(); rot = cm.get_camera_rotation(); pl = L.player().get_actor_location()
            st['camera'].append('%d,%.1f,%.1f,%.1f,%.2f,%.1f' % (st['film'], loc.x, loc.y, loc.z, rot.yaw, (pl - loc).length()))
            if st['film'] % 30 == 0:
                open(os.path.join(OUT, 'progress.txt'), 'w').write('%s film=%d sim=%d t=%.1f z=%s\n' % (name, st['film'], st['sim'], t, Z))
            st['film'] += 1
        st['sim'] += 1
    else:
        L.audio_frame(UNRECORDED)
    if r == 'done':
        st['rec'] = False
        if not next_shot(): finish()


def finish():
    live.stop('access_film')
    live.skate_input(); live.skate_release(); live.drive(0)
    MV.restore_player_camera(); L.film_hud(False); L.fixed_step(0)
    n = L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    open(os.path.join(OUT, 'camera.csv'), 'w').write('frame,x,y,z,yaw,dist\n' + '\n'.join(st['camera']) + '\n')
    open(os.path.join(OUT, 'loops.csv'), 'w').write('\n'.join(st['loops']) + '\n')
    json.dump(st['log'], open(os.path.join(OUT, 'log.json'), 'w'))
    json.dump({'film_frames': st['film'], 'sim_frames': st['sim'], 'fps_sim': 60, 'fps_film': 30, 'sounds': n, 'shots': st['marks'],
               'state': L.skate_state()}, open(os.path.join(OUT, 'done.json'), 'w'), indent=1)


L.film_hud(True); L.fixed_step(60); L.audio_log('start')
live.behave('access_film', run)
print('ACCESS FILM started', OUT, [s[0] for s in SHOTS])
