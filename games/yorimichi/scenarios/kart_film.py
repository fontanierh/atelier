"""A short kart gameplay take: summon on the beach flat, pull away, steer both ways, brake.

    atelier live py - < games/yorimichi/scenarios/kart_film.py
    ffmpeg -framerate 30 -i build/yorimichi/kart_film/kart1/frame_%05d.jpg -c:v libx264 -crf 20 -pix_fmt yuv420p kart.mp4

The game steps at a fixed 60 Hz and every second step is captured, so the take is 30 fps in real time. Input goes through
the real key bindings (W / A / D / S), not the scripted intent, so the same path as a player's. Writes the frames and
done.json with the car state.
"""
import importlib.util, json, os
import unreal

L = live.L
TAKE = globals().get('TAKE', 'kart1')
ROOT = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
OUT = os.path.join(ROOT, 'yorimichi/kart_film', TAKE)
os.makedirs(OUT, exist_ok=True)
_spec = importlib.util.spec_from_file_location('kart_cleanup', os.path.join(live.ROOT, 'games/yorimichi/scenarios/kart_cleanup.py'))
CLEAN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CLEAN)
for name in os.listdir(OUT):
    if name.endswith('.jpg') or name.endswith('.json'):
        os.remove(os.path.join(OUT, name))

START, END = 0.8, 7.0
# t, keys (the set of held keys from this time on)
TIMELINE = [
    (0.0, set()),
    (1.4, {'W'}),
    (3.4, {'W', 'D'}),
    (4.3, {'W', 'A'}),
    (5.1, {'S'}),
    (6.3, set()),
]
st = {'t': 0.0, 'sim': 0, 'film': 0, 'phase': -1, 'held': set(), 'frames': [], 'errors': [], 'started': False,
      'press_at': None}


def phase_at(t):
    i = 0
    for k, row in enumerate(TIMELINE):
        if row[0] <= t:
            i = k
    return i


def run(dt):
    try:
        if not st['started']:
            st['started'] = True
            live.stop('kart_drive')
            if 'driving=1' in L.car_state():
                live.press('car')
            g = L.ground_at(unreal.Vector(-23600, 16000, 3000))
            L.teleport_player(g, 0.0)
            L.fixed_step(60)
            # The press needs the teleport to have settled: a same-frame summon is refused on the ground check.
            st['press_at'] = 0.7
        st['t'] += 1.0 / 60.0
        t = st['t']
        if st['press_at'] is not None and t >= st['press_at']:
            st['press_at'] = None
            live.press('car')
            st['car'] = L.car_state()
        phase = phase_at(t)
        if phase != st['phase']:
            st['phase'] = phase
            want = TIMELINE[phase][1]
            for k in st['held'] - want:
                L.input_key(k, 'release', 0)
            for k in want - st['held']:
                L.input_key(k, 'press', 1)
            st['held'] = set(want)
        if START <= t <= END and st['sim'] % 2 == 0:
            L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % st['film']))
            st['frames'].append([st['film'], round(t, 3), phase, L.car_state()])
            st['film'] += 1
        st['sim'] += 1
        if t > END + .4:
            CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
            json.dump({'take': TAKE, 'fps': 30, 'frames': st['frames'], 'car': L.car_state(),
                       'loops': L.car_loops(), 'errors': st['errors'], 'ok': not st['errors'],
                       'status': 'passed' if not st['errors'] else 'failed'},
                      open(os.path.join(OUT, 'done.json'), 'w'), indent=1)
            unreal.log('KART FILM COMPLETE %d frames' % st['film'])
            live.stop('kart_film')
    except Exception as error:
        st['errors'].append(repr(error))
        CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
        json.dump({'take': TAKE, 'ok': False, 'status': 'failed', 'errors': st['errors']},
                  open(os.path.join(OUT, 'done.json'), 'w'), indent=1)
        unreal.log_error('KART FILM: %s' % error)
        live.stop('kart_film')


live.behave('kart_film', run)
print('kart film', TAKE, '->', OUT)
