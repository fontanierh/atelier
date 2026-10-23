"""A repeatable uneven-ground drive for ride quality: same start, heading and throttle every run.

    atelier live py - < games/yorimichi/scenarios/kart_uneven.py

Samples the chassis' own vertical motion (car_ride) at the 60 Hz step and writes ride numbers plus stills to
build/yorimichi/kart_film/kart_uneven.json. Use it before and after a suspension change, from the same revision
family, so the vertical acceleration and wheel-contact numbers compare like for like.
"""
import json
import importlib.util
import os
import re
import unreal

L = live.L
ROOT = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
OUT = os.path.join(ROOT, 'yorimichi/kart_film')
os.makedirs(OUT, exist_ok=True)
_spec = importlib.util.spec_from_file_location('kart_cleanup', os.path.join(live.ROOT, 'games/yorimichi/scenarios/kart_cleanup.py'))
CLEAN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CLEAN)

REPORT = os.path.join(OUT, 'kart_uneven.json')
json.dump({'ok': False, 'status': 'running', 'errors': []}, open(REPORT, 'w'), indent=1)

START = globals().get('KART_UNEVEN_START', unreal.Vector(-23600.0, 16000.0, 0.0))
YAW = globals().get('KART_UNEVEN_YAW', 0.0)
RUN = 6.0   # seconds of throttle from the standing start
NUMBER = re.compile(r'(y|vy|pitch|roll)=(-?[0-9.]+)')

st = {'t': 0.0, 'phase': 0, 'accels': [], 'speeds': [], 'lost': 0, 'samples': 0,
      'prev_vy': None, 'shot': 0, 'errors': [], 'steer_on': False, 'steer_done': False,
      'steer_t0': 0.0, 'steer_yaw': 0.0, 'steer_last_yaw': 0.0, 'yaw_rates': []}


def ride():
    text = L.car_ride()
    values = {k: float(v) for k, v in NUMBER.findall(text)}
    wheels = text.split('wheels=')[-1] if 'wheels=' in text else ''
    contact = sum(1 for w in wheels.split(',') if w.endswith('/1'))
    return values, contact


def yaw_of(state):
    match = re.search(r'yaw=(-?[0-9.]+)', state)
    return float(match.group(1)) if match else 0.0


def finish():
    CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
    accels = st['accels']
    if not accels:
        st['errors'].append('no samples')
    rms = (sum(a * a for a in accels) / len(accels)) ** .5 if accels else 0.0
    peak = max((abs(a) for a in accels), default=0.0)
    mean_speed = sum(st['speeds']) / len(st['speeds']) if st['speeds'] else 0.0
    final_speed = st['speeds'][-1] if st['speeds'] else 0.0
    lost = 100.0 * st['lost'] / max(1, st['samples'])
    steer_rms = ((sum(r * r for r in st['yaw_rates']) / len(st['yaw_rates'])) ** .5
                 if st['yaw_rates'] else 0.0)
    if accels and rms >= 4.5:
        st['errors'].append('vertical rms %.2f >= 4.5' % rms)
    if peak >= 12.0:
        st['errors'].append('vertical peak %.2f >= 12' % peak)
    if lost >= 5.0:
        st['errors'].append('contact lost %.1f%% >= 5%%' % lost)
    if mean_speed < 15.0:
        st['errors'].append('mean speed %.1f kph < 15' % mean_speed)
    if final_speed < 10.0:
        st['errors'].append('final speed %.1f kph < 10 (stall)' % final_speed)
    if not st['yaw_rates']:
        st['errors'].append('no steering response samples')
    elif steer_rms < 15.0 or steer_rms > 300.0:
        st['errors'].append('steering response rms %.1f deg/s outside 15..300' % steer_rms)
    report = {'rms_accel': round(rms, 3), 'peak_accel': round(peak, 3),
              'contact_lost_percent': round(lost, 2), 'mean_speed_kph': round(mean_speed, 1),
              'final_speed_kph': round(final_speed, 1), 'steer_rms_deg_s': round(steer_rms, 1),
              'samples': len(accels),
              'errors': st['errors']}
    report['ok'] = not st['errors']
    report['status'] = 'passed' if not st['errors'] else 'failed'
    json.dump(report, open(REPORT, 'w'), indent=1)
    unreal.log('KART UNEVEN ' + json.dumps(report))
    live.stop('kart_uneven')


def run(dt):
    try:
        st['t'] += dt
        t = st['t']
        if st['phase'] == 0 and t > 0.3:
            st['phase'] = 1
            if 'driving=1' in L.car_state():
                live.press('car')
            L.fixed_step(60)
            ground = L.ground_at(START)
            L.teleport_player(ground, YAW)
        elif st['phase'] == 1 and t > 0.8:
            st['phase'] = 2
            live.press('car')
        elif st['phase'] == 2 and t > 1.3:
            st['phase'] = 3
            if 'driving=1' not in L.car_state():
                st['errors'].append('car did not come out')
                finish()
                return
            L.input_key('W', 'press', 1.0)
        elif st['phase'] == 3:
            values, contact = ride()
            state = L.car_state()
            speed = float(re.search(r'kph=([0-9.]+)', state).group(1))
            st['speeds'].append(speed)
            if speed > 4.0 and t > 4.0 and not st['steer_on']:
                st['steer_on'] = True
                st['steer_t0'] = t
                st['steer_yaw'] = yaw_of(state)
                st['steer_last_yaw'] = st['steer_yaw']
                L.input_key('D', 'press', 1.0)
            if st['steer_on'] and not st['steer_done']:
                yaw = yaw_of(state)
                delta = ((yaw - st['steer_last_yaw'] + 180.0) % 360.0) - 180.0
                st['steer_last_yaw'] = yaw
                st['yaw_rates'].append(abs(delta) / max(dt, 1e-4))
                if t - st['steer_t0'] >= .35:
                    L.input_key('D', 'release', 0.0)
                    st['steer_done'] = True
            vy = values.get('vy', 0.0)
            if st['prev_vy'] is not None and speed > 4.0:
                st['accels'].append((vy - st['prev_vy']) / max(dt, 1e-4))
                st['samples'] += 1
                if contact < 4:
                    st['lost'] += 1
            st['prev_vy'] = vy
            if t > 2.0 + st['shot'] * 1.5 and st['shot'] < 3:
                st['shot'] += 1
                L.screenshot(os.path.join(OUT, 'kart_uneven_%d.png' % st['shot']))
            if t > RUN + 1.3:
                st['phase'] = 4
                L.input_key('W', 'release', 0.0)
                live.press('car') if 'driving=1' in L.car_state() and float(
                    re.search(r'kph=([0-9.]+)', L.car_state()).group(1)) < 1.0 else None
                L.fixed_step(0)
                finish()
    except Exception as error:
        st['errors'].append(repr(error))
        CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
        json.dump({'ok': False, 'status': 'failed', 'errors': st['errors']}, open(REPORT, 'w'), indent=1)
        unreal.log_error('KART UNEVEN: %s' % error)
        live.stop('kart_uneven')


live.behave('kart_uneven', run)
print('kart uneven armed')

