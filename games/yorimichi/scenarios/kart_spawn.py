"""Prove the kart finds ground on a slope, a crest, a narrow path and beside a wall.

    atelier live py - < games/yorimichi/scenarios/kart_spawn.py

The scenario searches a bounded patch of the existing world for each shape, then taps L1 (the live bridge injects the
gamepad shoulder) and records whether the kart placed. It does not create or alter geometry.
"""
import importlib.util
import json
import math
import os

import unreal

L = live.L
ROOT = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
OUT = os.path.join(ROOT, 'yorimichi/kart_film')
os.makedirs(OUT, exist_ok=True)
_spec = importlib.util.spec_from_file_location('kart_cleanup', os.path.join(live.ROOT, 'games/yorimichi/scenarios/kart_cleanup.py'))
CLEAN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CLEAN)

REPORT = os.path.join(OUT, 'kart_spawn.json')
BASE = globals().get('KART_SPAWN_BASE', unreal.Vector(-25542.0, 10140.0, 0.0))


def trace(x, y, z=5000.0):
    world = L.game_world()
    pawn = unreal.LiveLibrary.player()
    hit = unreal.SystemLibrary.line_trace_single(
        world, unreal.Vector(x, y, z), unreal.Vector(x, y, -5000.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY, False, [pawn], unreal.DrawDebugTrace.NONE, True)
    return None if hit is None else hit.to_tuple()


def height(x, y):
    hit = trace(x, y)
    return None if hit is None else hit[5].z


def normal_z(x, y):
    hit = trace(x, y)
    return None if hit is None else hit[7].z


def find(kind):
    """First point within 18 m of BASE that matches a named ground shape."""
    for dx in range(-1800, 1801, 300):
        for dy in range(-1800, 1801, 300):
            x, y = BASE.x + dx, BASE.y + dy
            z = height(x, y)
            if z is None:
                continue
            if kind == 'slope' and normal_z(x, y) is not None and .55 <= normal_z(x, y) <= .9:
                return unreal.Vector(x, y, z)
            if kind == 'crest':
                sides = [height(x - 200, y), height(x + 200, y), height(x, y - 200), height(x, y + 200)]
                if all(v is not None and z > v + 15.0 for v in sides):
                    return unreal.Vector(x, y, z)
            if kind == 'narrow':
                sides = [height(x - 250, y), height(x + 250, y), height(x, y - 250), height(x, y + 250)]
                if sum(v is None for v in sides) >= 2:
                    return unreal.Vector(x, y, z)
            if kind == 'wall':
                world = L.game_world()
                pawn = unreal.LiveLibrary.player()
                hit = unreal.SystemLibrary.line_trace_single(
                    world, unreal.Vector(x, y, z + 100.0), unreal.Vector(x + 300.0, y, z + 100.0),
                    unreal.TraceTypeQuery.ECC_VISIBILITY, False, [pawn], unreal.DrawDebugTrace.NONE, True)
                if hit is not None and abs(hit.to_tuple()[7].z) < .2:
                    return unreal.Vector(x, y, z)
    return None


CASES = globals().get('KART_SPAWN_CASES', None) or [
    ('slope', None), ('crest', None), ('narrow', None), ('wall', None)]

st = {'t': 0.0, 'phase': 0, 'index': 0, 'cases': [], 'errors': [], 'tap': 0.0}


def finish():
    CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
    report = {'ok': not st['errors'], 'status': 'passed' if not st['errors'] else 'failed',
              'cases': st['cases'], 'errors': st['errors']}
    json.dump(report, open(REPORT, 'w'), indent=1)
    unreal.log('KART SPAWN ' + json.dumps(report))
    live.stop('kart_spawn')


def start_case():
    kind, at = st['cases'][st['index']] if st['index'] < len(st['cases']) else (None, None)
    if kind is None:
        finish()
        return
    if at is None:
        at = find(kind)
        if at is None:
            st['errors'].append('no %s found near the base' % kind)
            st['index'] += 1
            return
        st['cases'][st['index']] = (kind, at)
    if 'driving=1' in L.car_state():
        live.press('car')
        L.fixed_step(60)
    L.teleport_player(L.ground_at(at), 0.0)
    st['tap'] = st['t']
    st['phase'] = 2


def run(dt):
    try:
        st['t'] += dt
        t = st['t']
        if st['phase'] == 0:
            st['cases'] = list(CASES)
            st['phase'] = 1
        elif st['phase'] == 1:
            start_case()
        elif st['phase'] == 2:
            # A real 0.2 s L1 press, not the scripted ToggleCar call.
            L.pad_input('Gamepad_LeftShoulder', 1.0)
            st['phase'] = 3
        elif st['phase'] == 3 and t > st['tap'] + .25:
            L.pad_input('Gamepad_LeftShoulder', 0.0)
            st['phase'] = 4
        elif st['phase'] == 4 and t > st['tap'] + .9:
            kind, at = st['cases'][st['index']]
            state = L.car_state()
            ok = 'driving=1' in state
            st['cases'][st['index']] = (kind, [round(at.x), round(at.y), round(at.z)], ok, state)
            if not ok:
                st['errors'].append('%s did not spawn: %s' % (kind, state))
            st['index'] += 1
            st['phase'] = 1
    except Exception as error:
        CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
        st['errors'].append(repr(error))
        finish()


live.behave('kart_spawn', run)
print('kart spawn armed')
