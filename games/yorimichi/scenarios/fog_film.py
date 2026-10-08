"""Volumetric fog review (docs/VOLUMETRIC_FOG.md): stills of fixed views with the "fog" setting on and off, and a short
film of the mist and the light shafts.

    atelier play yorimichi -- -nofox -nosound -ForceDPCVars=r.Streaming.PoolSize=200 -RenderOffscreen -ForceRes
    atelier live py "TAKE='fog1'" && atelier live py - < games/yorimichi/scenarios/fog_film.py
    ... wait for build/yorimichi/fog_film/<take>/done.json, then:
    python games/yorimichi/scenarios/fog_film_cut.py build/yorimichi/fog_film/fog.mp4 <take>

Stills: each view at the game's own sun (the "Sun elevation" and "Sun direction" settings as saved), fog on then off,
as <view>_on.png and <view>_off.png; the GPU frame time of each (stat unit, averaged over a second) goes to done.json.
Film: a morning sun low ahead of the camera (the sun settings moved for the shot), each shot labelled; the last one
switches the setting off and on again in the same view. Runs at a fixed 60 fps step and saves every second step as a
JPG (30 fps, real time); frames.json gives each frame its shot's caption and whether the fog was on.
Sliders: the settings menu (menu.png), then each fog slider stepped through three values in one view.
Optional globals: TAKE; ONLY, 'stills', 'film' or 'sliders'; VIEWS_ONLY, the still views to take (names). The sun and fog settings
are put back as found.
"""
import json, math, os, traceback
import unreal

L = live.L
TAKE = globals().get('TAKE', 'fog1')
ONLY = globals().get('ONLY')
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/fog_film', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.jpg') or f.endswith('.png') or f.endswith('.json'):
        os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
MV = unreal.MegaParkValidation

# Still views: eye -> look-at in island metres (x east, y north); a height given as ('ground', h) is the terrain's plus h.
VIEWS = {
    'village_road': ((-248.3, -100.0, 10.8), (-200.0, -102.3, 8.5), 60.),
    'coast': ((-236.0, -160.0, 4.2), (-196.0, -185.0, 1.5), 60.),
    'valley': ((-115.1, -70.7, 12.2), (-65.7, -78.1, 8.7), 60.),
    'overlook': ((-102.4, -98.5, 101.6), (-68.0, -134.0, 80.0), 60.),
    'forest_lake': ((-116.0, 195.0, 87.0), (-80.0, 228.6, 75.0), 60.),
    'forest_shore': ((-128.5, 214.5, ('ground', 2.)), (-147.3, 249.8, ('ground', 3.)), 60.),
    'hidamari_hill': ((170., 60., ('ground', 30.)), (780., 110., 25.), 60.),
    'hidamari_road': ((300., 60., ('ground', 2.)), (700., 140., 25.), 60.),
    'hidamari_lighthouse': ((440., -225., ('ground', 22.)), (780., 160., 25.), 70.),
    'hidamari_lane': ((1100., -46., ('ground', 1.7)), (1200., -46., ('ground', 1.7)), 60.),
    'hidamari_sea': ((800., -700., 25.), (800., 100., 35.), 55.),
}

st = {'frames': [], 'errors': [], 'sim': 0, 'film': 0, 'rec': False, 'label': '', 'gpu': {}, 'cam': None}


def ue(x, y, z=0.):
    """Island metres (x east, y north) to Unreal cm."""
    return unreal.Vector(x * 100., -y * 100., z * 100.)


def ground(x, y):
    """The terrain's height (m) under island x, y: ground_at looks from 20 m above its point to 60 m below."""
    for z in (300., 240., 180., 120., 60., 0.):
        g = L.ground_at(unreal.Vector(x * 100., -y * 100., z * 100.))
        if abs(g.z - z * 100.) > 1.:
            return g.z / 100.
    return 0.


def height(p):
    z = p[2]
    return ground(p[0], p[1]) + z[1] if isinstance(z, tuple) else z


def ue_yaw(a, b):
    """The Unreal yaw from island point a toward b."""
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))


def state():
    return json.loads(L.move_state())


def wait(seconds):
    t = 0.
    while t < seconds:
        t += (yield)


def until(test, timeout):
    t = 0.
    while t < timeout:
        s = state()
        if test(s):
            return s
        t += (yield)
    return None


def saved_settings():
    path = os.path.join(unreal.Paths.project_saved_dir(), 'settings.txt')
    values = {'fog': 1., 'sun_height': 48., 'sun_yaw': 15.}
    try:
        for line in open(path):
            k, _, v = line.partition('=')
            if k.strip() in values:
                values[k.strip()] = float(v)
    except (OSError, ValueError):
        pass
    return values


def fog(on):
    L.set_preference('fog', 1. if on else 0.)
    st['fog'] = on


def sun(elevation, ue_direction):
    """Put the sun `elevation` degrees up, shining along Unreal yaw `ue_direction` (it stands at the opposite yaw)."""
    L.set_preference('sun_height', elevation)
    L.set_preference('sun_yaw', (ue_direction + 180.) % 360. - 180.)


def aim(eye, at, fov):
    """A fixed camera from island point eye to at; the player waits 6 m behind the eye, out of the picture."""
    e = ue(eye[0], eye[1], height(eye)); a = ue(at[0], at[1], height(at))
    yaw = math.atan2(a.y - e.y, a.x - e.x)
    behind = unreal.Vector(e.x - math.cos(yaw) * 600., e.y - math.sin(yaw) * 600., e.z)
    L.teleport_player(ue(behind.x / 100., -behind.y / 100., ground(behind.x / 100., -behind.y / 100.) + 1.), math.degrees(yaw))
    MV.review_camera(e, a, fov)
    st['cam'] = None


# ------------------------------------------------------------------------------------------------- stills

def gpu_ms(seconds):
    """The GPU frame time (ms) averaged over `seconds` (the engine's stat unit figure, RHI GPU cycles)."""
    total, n = 0., 0
    t = 0.
    while t < seconds:
        total += unreal.LiveLibrary.gpu_frame_ms()
        n += 1
        t += (yield)
    return round(total / max(n, 1), 2)


def stills():
    names = globals().get('VIEWS_ONLY') or list(VIEWS)
    for name in names:
        eye, at, fov = VIEWS[name]
        aim(eye, at, fov)
        fog(True)
        yield from wait(2.5)                      # streaming, the fog's history
        st['gpu'][name] = {'on': (yield from gpu_ms(1.))}
        L.screenshot(os.path.join(OUT, name + '_on.png'))
        yield from wait(.3)
        fog(False)
        yield from wait(1.)
        st['gpu'][name]['off'] = yield from gpu_ms(1.)
        L.screenshot(os.path.join(OUT, name + '_off.png'))
        yield from wait(.3)
        save()


# ------------------------------------------------------------------------------------------------- film

def label(text):
    st['label'] = text; st['rec'] = True
    unreal.log(f'FOG FILM | {text}')


def cut():
    st['rec'] = False


def dolly(eye, at, fov, move, seconds, turn=0.):
    """A camera from eye toward at, sliding `move` metres (island x, y, z) over `seconds` and panning `turn` degrees."""
    e = ue(eye[0], eye[1], height(eye)); a = ue(at[0], at[1], height(at))
    st['cam'] = dict(e=e, a=a, fov=fov, move=ue(*move), turn=turn, t=0., T=seconds)


def update_camera(dt):
    c = st['cam']
    if not c:
        return
    k = min(1., c['t'] / c['T']); k = k * k * (3. - 2. * k)
    e = c['e'] + c['move'] * k
    d = c['a'] - c['e']; r = math.radians(c['turn'] * k)
    d = unreal.Vector(d.x * math.cos(r) - d.y * math.sin(r), d.x * math.sin(r) + d.y * math.cos(r), d.z)
    MV.review_camera(e, e + d, c['fov'])
    c['t'] += dt


def shot(eye, at, fov, move, seconds, text, turn=0.):
    aim(eye, at, fov)
    yield from wait(2.)                            # streaming and the fog's history before recording
    dolly(eye, at, fov, move, seconds, turn)
    label(text)
    yield from wait(seconds)
    cut()


def film():
    # The road out of the village at dawn: the sun low ahead, the mist lit from behind.
    eye, at = (-246.5, -104.1, 10.8), (-190.0, -112.0, 9.0)
    sun(12., ue_yaw(eye, at) + 180. + 25.)
    fog(True)
    yield from shot(eye, at, 60., (14., -2., 0.), 7., 'Dawn: mist on the road out of the village')
    # Light shafts through the forest by the lake: the sun behind the trees.
    eye, at = (-116.0, 195.0, 81.0), (-80.0, 228.6, 79.0)
    sun(16., ue_yaw(eye, at) + 180. - 15.)
    yield from shot(eye, at, 60., (6., 5., 0.), 7., 'Light shafts through the forest', turn=-10.)
    # Running through it, the game's own camera.
    yield from run_through()
    # Gliding down into it.
    yield from glide_into()
    # Hidamari's arrival road.
    eye, at = (300., 60., ('ground', 2.)), (700., 140., 25.)
    sun(14., ue_yaw(eye, at) + 180. + 30.)
    yield from shot(eye, at, 60., (12., 2., 0.), 6., 'Arriving at Hidamari')
    # The setting itself, in one view: on, off, on.
    eye, at = (-116.0, 195.0, 81.0), (-80.0, 228.6, 79.0)
    sun(16., ue_yaw(eye, at) + 180. - 15.)
    aim(eye, at, 60.); fog(True)
    yield from wait(2.)
    label('Settings: Volumetric fog on')
    yield from wait(3.)
    fog(False); label('Settings: Volumetric fog off')
    yield from wait(3.)
    fog(True); label('Settings: Volumetric fog on')
    yield from wait(3.)
    cut()


def run_through():
    """Sprinting down the village road toward a low sun, the game's own camera behind."""
    start, toward = (-248.3, -100.0), (-200.0, -102.3)
    yaw = ue_yaw(start, toward)
    sun(12., yaw + 180. + 30.)
    L.teleport_player(ue(start[0], start[1], ground(*start) + 1.), yaw)
    pc.set_control_rotation(unreal.Rotator(0, -6, yaw))
    MV.restore_player_camera(); st['cam'] = None
    yield from wait(2.)
    label('Running through the mist (the game camera)')
    live.drive(1., 0., 'sprint')
    t = 0.
    while t < 4.5:
        pc.set_control_rotation(unreal.Rotator(0, -6, yaw))
        t += (yield)
    live.drive(0)
    yield from wait(.8)
    cut()


def glide_into():
    """Launched high over the village road and gliding down it, toward a low sun, the game's own camera behind."""
    start, toward = (-246.5, -104.1), (-190.0, -112.0)
    yaw = ue_yaw(start, toward)
    sun(14., yaw + 180. + 35.)
    L.teleport_player(ue(start[0], start[1], ground(*start) + 1.), yaw)
    pc.set_control_rotation(unreal.Rotator(0, -15, yaw))
    MV.restore_player_camera(); st['cam'] = None
    yield from wait(1.5)
    L.launch(unreal.Vector(0, 0, 3200))
    yield from until(lambda s: s['vz'] > 500., 1.)
    yield from until(lambda s: s['vz'] < 80., 4.)
    live.press('jump'); live.press('jump_release')
    if (yield from until(lambda s: s['mode'] == 'glide', .3)) is None:
        yield from until(lambda s: s['vz'] < 80., 1.5)
        live.press('jump'); live.press('jump_release')
        yield from until(lambda s: s['mode'] == 'glide', .6)
    label('Gliding down into the mist')
    live.drive(1., 0., 'run')
    t = 0.
    while t < 8. and state().get('mode') == 'glide':
        pc.set_control_rotation(unreal.Rotator(0, -15, yaw))
        t += (yield)
    live.drive(0)
    cut()
    yield from until(lambda s: s.get('mode') in ('ground', 'swim'), 20.)


SLIDERS = [('fog_density', 'Fog density', (.03, .07, .14)), ('fog_reach', 'Fog reach (m)', (15., 30., 90.)),
           ('fog_falloff', 'Fog height falloff', (.04, .12, .4)), ('fog_glow', 'Fog glow toward the sun', (0., .5, .85)),
           ('fog_shafts', 'Light shafts', (0., 1., 3.))]


def sliders():
    """The settings menu with its fog sliders (menu.png), then each slider stepped through three values in one view by
    the forest lake, a low sun ahead; each back to its default (the middle value) after."""
    eye, at = (-116.0, 195.0, 81.0), (-80.0, 228.6, 79.0)
    sun(16., ue_yaw(eye, at) + 180. - 15.)
    aim(eye, at, 60.); fog(True)
    yield from wait(2.)
    live.press('menu'); yield from wait(.5)
    L.screenshot(os.path.join(OUT, 'menu.png')); yield from wait(.5)
    live.press('menu'); yield from wait(.5)
    for key, name, values in SLIDERS:
        for v in values:
            L.set_preference(key, v)
            yield from wait(.6)                  # the fog's history settles before the shot
            label(f'Settings: {name} {v:g}' + (' (default)' if v == values[1] else ''))
            yield from wait(1.6)
            cut()
        L.set_preference(key, values[1])


# ------------------------------------------------------------------------------------------------- run

def steps():
    st['found'] = saved_settings()
    L.film_hud(True)
    sections = [('stills', stills), ('film', film), ('sliders', sliders)]
    for name, fn in sections:
        if ONLY and name != ONLY:
            continue
        try:
            if name in ('film', 'sliders'):
                L.fixed_step(60)
            yield from fn()
        except Exception:
            st['errors'].append({'section': name, 'label': st['label'], 'error': traceback.format_exc()})
            unreal.log_warning(f'FOG FILM {name} failed: {traceback.format_exc()}')
        cut(); live.drive(0); L.fixed_step(0)
        save()


def run(dt):
    dt = unreal.GameplayStatics.get_world_delta_seconds(L.game_world())
    if st.get('gen') is None:
        st['gen'] = steps(); next(st['gen'])
        return
    try:
        st['gen'].send(dt)
    except StopIteration:
        return finish()
    update_camera(dt)
    if st['rec']:
        if st['sim'] % 2 == 0:
            L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % st['film']))
            st['frames'].append([st['film'], st['label'], bool(st.get('fog'))])
            st['film'] += 1
        st['sim'] += 1


def save():
    json.dump({'frames': st['frames'], 'gpu': st['gpu'], 'errors': st['errors']}, open(os.path.join(OUT, 'frames.json'), 'w'))


def finish():
    live.stop('fog_film'); live.drive(0); L.fixed_step(0)
    found = st.get('found') or {}
    for key in ('fog', 'sun_height', 'sun_yaw'):
        if key in found:
            L.set_preference(key, found[key])
    MV.restore_player_camera(); L.film_hud(False)
    save()
    json.dump({'frames': st['film'], 'gpu': st['gpu'], 'errors': st['errors']}, open(os.path.join(OUT, 'done.json'), 'w'))
    unreal.log('FOG FILM DONE')


live.behave('fog_film', run)
print('FOG FILM started', OUT)
