"""Prove the kart righting itself after a flip, and that L1 rights it at once.

    atelier live py - < games/yorimichi/scenarios/kart_flip.py

The live bridge rolls the equipped kart onto its back at the flat village road. The scenario waits for the one-second
inverted timer and the half-second righting arc, then checks that the chassis is upright again and kept its yaw.
"""
import importlib.util
import json
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

REPORT = os.path.join(OUT, 'kart_flip.json')
START = globals().get('KART_FLIP_START', unreal.Vector(-25542.0, 10140.0, 0.0))
YAW = globals().get('KART_FLIP_YAW', 0.0)

st = {'t': 0.0, 'phase': 0, 'flip_t': 0.0, 'yaw_before': None, 'errors': [], 'recovered': False}


def car_yaw(state):
    match = re.search(r'yaw=(-?[0-9.]+)', state)
    return float(match.group(1)) if match else 0.0


def ride_angles():
    values = dict(re.findall(r'(pitch|roll)=(-?[0-9.]+)', L.car_ride()))
    return float(values.get('pitch', 0.0)), float(values.get('roll', 0.0))


def finish():
    CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
    report = {'ok': not st['errors'], 'status': 'passed' if not st['errors'] else 'failed',
              'errors': st['errors'], 'recovered': st['recovered']}
    json.dump(report, open(REPORT, 'w'), indent=1)
    unreal.log('KART FLIP ' + json.dumps(report))
    live.stop('kart_flip')


def run(dt):
    try:
        st['t'] += dt
        t = st['t']
        if st['phase'] == 0 and t > .3:
            st['phase'] = 1
            if 'driving=1' in L.car_state():
                live.press('car')
            L.fixed_step(60)
            L.teleport_player(L.ground_at(START), YAW)
        elif st['phase'] == 1 and t > .8:
            st['phase'] = 2
            live.press('car')
        elif st['phase'] == 2 and t > 1.4:
            if 'driving=1' not in L.car_state():
                st['errors'].append('car did not come out')
                finish()
                return
            st['yaw_before'] = car_yaw(L.car_state())
            if not L.car_flip():
                st['errors'].append('car flip hook failed')
                finish()
                return
            st['flip_t'] = t
            st['phase'] = 3
        elif st['phase'] == 3 and t > st['flip_t'] + 2.2:
            pitch, roll = ride_angles()
            state = L.car_state()
            st['recovered'] = abs(pitch) < 20.0 and abs(roll) < 20.0
            if not st['recovered']:
                st['errors'].append('still inverted: pitch %.1f roll %.1f' % (pitch, roll))
            if 'Recovered' not in state:
                st['errors'].append('righting hint missing: %s' % state)
            if abs(((car_yaw(state) - st['yaw_before'] + 180.0) % 360.0) - 180.0) > 10.0:
                st['errors'].append('yaw changed by more than 10 degrees')
            st['phase'] = 4
            finish()
    except Exception as error:
        CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
        st['errors'].append(repr(error))
        finish()


live.behave('kart_flip', run)
print('kart flip armed')
