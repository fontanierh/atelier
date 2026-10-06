"""The in-game half of tools/review_bike.py: ride Cairo's bike through every move on a fixed 60 fps step.

    atelier live py "OUT='/abs/folder'; SITE=(x, y, yaw); CRASH=(x, y, yaw); FILM=True" && atelier live py - < this file

Runs in the game's Python (the live bridge). SITE is open, level ground (Unreal cm and yaw): the bike comes out
there and Cairo mounts, rides, steers both ways, rings the bell, waves, hops, pedals hard into a skid stop, puts a
foot down and parks it. He then gets back on the parked bike, rides a lap and parks again. CRASH is level ground with room
ahead: first he pedals hard from a standstill (one tap of Sprint) and skids to a stop; then a test wall goes up 11 m in
front and he pedals hard into it. Then, on the same run with the wall gone, a test ramp
(12.5 degrees, 1 m high, then a drop) checks that both wheels stay on a slope. Every frame's live.bike_state() goes to rows.json; named stills go to OUT; with
FILM every other frame goes to OUT/film as a PNG (30 fps), and for the film's soundtrack the sounds the game starts go to
audio.json, the bike's loops every frame to loops.csv and the camera every film frame to camera.csv (their clock runs
only while the film does; tools/review_bike.py mixes them). done.json marks the end (with any error).
"""
import json, math, os
import unreal

L = live.L
OUT = globals()['OUT']; SITE = globals()['SITE']; CRASH = globals().get('CRASH'); FILM = bool(globals().get('FILM', True))
os.makedirs(os.path.join(OUT, 'film'), exist_ok=True)
for name in ('done.json', 'rows.json', 'progress.json', 'audio.json', 'loops.csv', 'camera.csv'):
    if os.path.exists(os.path.join(OUT, name)): os.remove(os.path.join(OUT, name))
review = unreal.MegaParkValidation


def fields(row):
    f = {}
    for kv in row.split(' '):
        if '=' in kv: k, v = kv.split('=', 1); f[k] = v
    return f


def vec(text):
    return [float(x) for x in text.strip('()').split(',')]


def drive(forward=0., right=0., gait='run'):
    L.drive(unreal.Vector2D(float(right), float(forward)), {'walk': 0, 'run': 1, 'sprint': 2}[gait])


def place(site):
    x, y, yaw = site
    L.teleport_player(L.ground_at(unreal.Vector(x, y, 5000.)), float(yaw))


# The cameras: 'game' is the player's own chase camera; 'track' rides along at (forward, right, up) cm in the rider's
# frame, looking at a point (forward, right, up) on him, eased so a turn swings it round smoothly; 'fixed' holds a
# camera placed once in the rider's frame when the shot starts.
CAM = {'mode': 'game', 'eye': None}


def camera(mode, eye=(0, 0, 0), at=(0, 0, 90), fov=55.):
    CAM.update(mode=mode, off=eye, at=at, fov=fov, eye=None, look=None)
    if mode == 'game':
        review.restore_player_camera()


def frame_point(offset):
    p, yaw = live.player()
    r = math.radians(yaw); f, s, u = offset
    return unreal.Vector(p.x + math.cos(r) * f - math.sin(r) * s, p.y + math.sin(r) * f + math.cos(r) * s, p.z - 74.6 + u)


def update_camera():
    if CAM['mode'] == 'game': return
    eye, look = frame_point(CAM['off']), frame_point(CAM['at'])
    if CAM['mode'] == 'fixed' and CAM['eye'] is not None: eye = CAM['eye']
    elif CAM['eye'] is not None and CAM['mode'] == 'track':
        k = .12
        eye = unreal.Vector(*(a + (b - a) * k for a, b in zip((CAM['eye'].x, CAM['eye'].y, CAM['eye'].z), (eye.x, eye.y, eye.z))))
        look = unreal.Vector(*(a + (b - a) * .3 for a, b in zip((CAM['look'].x, CAM['look'].y, CAM['look'].z), (look.x, look.y, look.z))))
    CAM['eye'], CAM['look'] = eye, look
    review.review_camera(eye, look, CAM['fov'])


def still(name):
    # One screenshot can be pending at a time: a film frame taken on the same frame would replace it, so the film
    # takes the still's picture and copies it in afterwards.
    S['stills'].append(name)


SIDE = dict(eye=(30, -430, 110), at=(30, 0, 85))          # his left, where he gets on
FRONT3 = dict(eye=(300, -260, 140), at=(20, 0, 105))      # three-quarter front, from his left
REAR3 = dict(eye=(-330, 170, 170), at=(40, 0, 90))

# (seconds, what happens). Seconds are simulation time on the fixed step.
STEPS = [
    (0.0, lambda: place(SITE)),
    (1.0, lambda: camera('fixed', **SIDE, fov=50.)),
    (1.5, lambda: still('00_summon_before')),
    (1.6, lambda: live.press('bike')),
    (2.4, lambda: still('01_mount')),
    (3.4, lambda: still('02_seated')),
    (3.6, lambda: camera('game')),
    (3.7, lambda: drive(.8)),
    (5.4, lambda: still('03_ride_rear')),
    (5.5, lambda: camera('track', **SIDE, fov=50.)),
    (6.4, lambda: still('04_ride_side')),
    (6.5, lambda: drive(.7, .45)),
    (7.6, lambda: still('05_turn_right')),
    (8.5, lambda: drive(.7, -.45)),
    (9.6, lambda: still('06_turn_left')),
    (10.5, lambda: drive(.7, .2)),
    (10.6, lambda: camera('track', **FRONT3, fov=48.)),
    (11.0, lambda: live.press('attack')),
    (11.35, lambda: still('07_bell')),
    (12.2, lambda: live.press('wave')),
    (12.75, lambda: still('08_wave')),
    (13.9, lambda: camera('track', **SIDE, fov=50.)),
    (14.2, lambda: live.press('jump')),
    (14.25, lambda: live.press('jump_release')),
    (14.5, lambda: still('09_hop')),
    (15.6, lambda: camera('game')),
    (15.7, lambda: drive(.7, -.2)),   # bearing away from the station's walls (the sprint has its own run)
    (16.9, lambda: still('10_cruise')),
    (17.6, lambda: camera('track', **REAR3, fov=50.)),
    (18.0, lambda: (drive(0.), live.press('crouch'))),
    (18.45, lambda: still('11_skid')),
    (19.8, lambda: still('12_foot_down')),
    (20.6, lambda: camera('fixed', **SIDE, fov=50.)),
    (20.7, lambda: live.press('bike')),
    (21.6, lambda: still('13_dismount')),
    (23.0, lambda: still('14_kickstand')),
    (23.8, lambda: still('15_parked')),
    (24.0, lambda: camera('game')),
    (24.3, lambda: live.press('bike')),        # back onto the parked bike
    (26.2, lambda: drive(.6, -.3)),
    (30.0, lambda: drive(-1.)),                # brake to a stop
    (31.5, lambda: drive(0.)),
    (32.3, lambda: live.press('bike')),
    (35.2, lambda: still('16_parked_again')),
]
WALL_CM = 1100.   # tools/review_bike.py checks his reach against it


def wall_ahead(site, distance=WALL_CM):
    # A test wall across his path, so the crash happens wherever CRASH is (a real wall further on is never reached).
    x, y, yaw = site; r = math.radians(yaw)
    ground = L.ground_at(unreal.Vector(x + math.cos(r) * distance, y + math.sin(r) * distance, 5000.))
    L.test_wall(ground, float(yaw), unreal.Vector(40., 500., 220.))


CRASH_STEPS = [
    (0.0, lambda: (place(CRASH), wall_ahead(CRASH))),
    (1.0, lambda: camera('game')),
    (1.2, lambda: live.press('bike')),
    (3.0, lambda: (drive(1., 0.), live.press('sprint'))),
    (3.1, lambda: camera('track', eye=(-120, -520, 170), at=(150, 0, 80), fov=55.)),
]
CRASH_AFTER = [(0.35, lambda: still('17_crash_over')), (.9, lambda: still('18_crash_down')), (1.6, lambda: still('19_crash_squat')),
               (2.6, lambda: still('20_crash_up'))]

RAMP = dict(start=300., length=450., rise=100.)   # tools/review_bike.py


def ramp_ahead(site):
    x, y, yaw = site; r = math.radians(yaw)
    L.clear_tests()
    ground = L.ground_at(unreal.Vector(x + math.cos(r) * RAMP['start'], y + math.sin(r) * RAMP['start'], 5000.))
    L.test_ramp(ground, float(yaw), RAMP['length'], RAMP['rise'])


# Pedalling hard needs a long straight: on the crash run (before its wall goes up) he taps Sprint once, pulls away
# from a standstill past 1000 cm/s, skids to a stop and parks.
SPRINT_STEPS = [
    (0.0, lambda: place(CRASH)),
    (1.0, lambda: camera('game')),
    (1.2, lambda: live.press('bike')),
    (3.0, lambda: (drive(1.), live.press('sprint'))),   # one tap: pedalling hard stays on
    (4.4, lambda: camera('track', **REAR3, fov=50.)),
    (5.0, lambda: still('10_sprint')),
    (5.5, lambda: (drive(0.), live.press('crouch'))),
    (6.0, lambda: still('10b_sprint_skid')),
    (8.0, lambda: live.press('bike')),
]

SLOPE_STEPS = [
    (0.0, lambda: (place(CRASH), ramp_ahead(CRASH))),
    (1.0, lambda: camera('fixed', eye=(320, -700, 170), at=(320, 0, 70), fov=55.)),
    (1.2, lambda: live.press('bike')),
    (3.0, lambda: drive(.6)),
    (4.9, lambda: still('21_ramp_up')),
    (5.5, lambda: still('22_ramp_top')),
    (6.3, lambda: still('23_ramp_off')),
    (6.8, lambda: drive(-1.)),
    (8.0, lambda: drive(0.)),
]

S = {'frame': 0, 't': 0., 'segment': 'ride', 'queue': list(STEPS), 'rows': [], 'crash_at': None, 'error': None, 'end': None,
     'stills': [], 'copies': [], 'film': 0, 'loops': [], 'camera': []}
CM = unreal.GameplayStatics.get_player_camera_manager(L.game_world(), 0)


def finish(error=None):
    live.stop('bike_qa')
    drive(0.)
    review.restore_player_camera()
    L.fixed_step(0.)
    json.dump(S['rows'], open(os.path.join(OUT, 'rows.json'), 'w'))
    L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    open(os.path.join(OUT, 'loops.csv'), 'w').write('\n'.join(S['loops']) + '\n')
    open(os.path.join(OUT, 'camera.csv'), 'w').write('frame,x,y,z,yaw\n' + '\n'.join(S['camera']) + '\n')
    json.dump({'error': error, 'frames': S['frame'], 'film_copies': S['copies']}, open(os.path.join(OUT, 'done.json'), 'w'))


def tick(_dt):
    try:
        step = 1. / 60.
        while S['queue'] and S['queue'][0][0] <= S['t'] + 1e-6:
            S['queue'].pop(0)[1]()
        row = L.bike_state()
        f = fields(row); f['clip_t'] = f.pop('t', '')
        S['rows'].append(dict(seg=S['segment'], t=round(S['t'], 4), **f))
        if S['segment'] == 'crash':
            if S['crash_at'] is None and f.get('state') == '5':
                S['crash_at'] = S['t']
                S['queue'] = sorted(S['queue'] + [(S['t'] + d, a) for d, a in CRASH_AFTER] +
                                    [(S['t'] + .05, lambda: (drive(0.), camera('fixed', eye=(-260, -620, 190), at=(120, 0, 50), fov=55.)))],
                                    key=lambda s: s[0])
                S['end'] = S['t'] + 3.5
            if S['t'] > 9. and S['crash_at'] is None:
                return finish('no crash within 6 s of pedalling at the wall')
        update_camera()
        filmed = FILM and (bool(S['stills']) or S['frame'] % 2 == 0) and S['t'] > 1.
        if FILM and S['t'] > 1.:
            # The soundtrack's clock is the film's at 60 Hz: film frame k is tick 2k (a still taken on an odd frame
            # adds a film frame, so the clock follows the film, not the simulation).
            tick_ = 2 * S['film'] if filmed else 2 * S['film'] - 1
            L.audio_frame(tick_); row = L.bike_loops().strip()
            while len(S['loops']) <= tick_: S['loops'].append(row)
            if filmed:
                loc, rot = CM.get_camera_location(), CM.get_camera_rotation()
                S['camera'].append('%d,%.1f,%.1f,%.1f,%.2f' % (S['film'], loc.x, loc.y, loc.z, rot.yaw)); S['film'] += 1
        if S['stills']:
            name = os.path.join(OUT, f'bike_{S["stills"].pop(0)}.png'); L.screenshot(name)
            if FILM: S['copies'].append((name, os.path.join(OUT, 'film', f'{S["segment"]}_{S["frame"]:05d}.png')))
        elif FILM and S['frame'] % 2 == 0 and S['t'] > 1.:
            L.screenshot(os.path.join(OUT, 'film', f'{S["segment"]}_{S["frame"]:05d}.png'))
        S['frame'] += 1; S['t'] += step
        if S['frame'] % 120 == 0:
            json.dump({'segment': S['segment'], 't': round(S['t'], 2), 'frame': S['frame'], 'clip': f.get('clip'), 'state': f.get('state')},
                      open(os.path.join(OUT, 'progress.json'), 'w'))
        if S['segment'] in ('ride', 'sprint', 'slope') and not S['queue'] and S['end'] is None: S['end'] = S['t'] + (3. if S['segment'] == 'sprint' else 1.)
        if S['end'] is not None and S['t'] >= S['end']:
            if S['segment'] == 'ride' and CRASH:
                S.update(segment='sprint', t=0., queue=list(SPRINT_STEPS), end=None)
                return
            if S['segment'] == 'sprint':
                S.update(segment='crash', t=0., queue=list(CRASH_STEPS), end=None)
                return
            if S['segment'] == 'crash':
                S.update(segment='slope', t=0., queue=list(SLOPE_STEPS), end=None)
                return
            L.clear_tests()
            finish()
    except Exception as error:
        import traceback
        finish(traceback.format_exc())


L.fixed_step(60.)
L.audio_log('start')
live.behave('bike_qa', tick)
print('bike qa started')
