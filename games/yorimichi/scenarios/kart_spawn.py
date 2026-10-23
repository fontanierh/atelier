"""Prove the kart finds ground on a slope, a crest, a narrow path and beside a wall.

    atelier live py - < games/yorimichi/scenarios/kart_spawn.py

The scenario searches a bounded patch of the existing world for each shape, then taps L1 (the live bridge injects the
gamepad shoulder) and records whether the kart placed. It does not create or alter geometry.

A "narrow" spot is a flat piece of ground whose two sides are closed within 2.5 m: each side's ground is at least
45 cm above or below the centre (a bank, kerb or drop), or a near-vertical trace hits within reach (a wall, rail or
prop). At least one of those sides must be a real step of 90 cm or a wall, so a uniform slope is not narrow: it has
no closed side. The search walks 1 m rings out to 30 m from BASE, so a shape just outside the old 18 m grid is still
found.
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
NARROW_STEP = 45.0      # cm: each side must differ by this much to count as closed
NARROW_STRONG = 90.0    # cm: one side must be a real bank, kerb or drop (or a wall)
NARROW_REACH = 250.0    # cm: lateral room a narrow spot closes on both sides
NARROW_CLEAR = 120.0    # cm: the kart itself must fit at the candidate
NARROW_FLAT = .9        # minimum ground normal z at the candidate
NARROW_RADIUS = 3000.0  # cm: search rings around BASE
NARROW_GRID = 100.0     # cm: ring spacing, and spacing of points around a ring


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


def wall(x, y, z, dx, dy, reach):
    """A near-vertical hit within reach of a horizontal trace at kart height."""
    hit = unreal.SystemLibrary.line_trace_single(
        L.game_world(), unreal.Vector(x, y, z + 80.0), unreal.Vector(x + dx * reach, y + dy * reach, z + 80.0),
        unreal.TraceTypeQuery.ECC_VISIBILITY, False, [unreal.LiveLibrary.player()], unreal.DrawDebugTrace.NONE, True)
    return hit is not None and abs(hit.to_tuple()[7].z) < .2


def side(x, y, z, dx, dy):
    """Whether a side is closed, whether it is a real step or wall, and its height difference in cm."""
    h = height(x + dx * NARROW_REACH, y + dy * NARROW_REACH)
    if h is None:
        return True, True, None
    delta = h - z
    strong = abs(delta) > NARROW_STRONG
    if not strong:
        strong = wall(x, y, z, dx, dy, NARROW_REACH)
    return abs(delta) > NARROW_STEP or strong, strong, delta


def narrow_at(x, y):
    """A flat point with closed sides on one axis: (z, detail), or None."""
    hit = trace(x, y)
    if hit is None or hit[7].z < NARROW_FLAT:
        return None
    z = hit[5].z
    for axis, dx, dy in (('x', 1.0, 0.0), ('y', 0.0, 1.0)):
        left = side(x, y, z, -dx, -dy)
        right = side(x, y, z, dx, dy)
        if not (left[0] and right[0] and (left[1] or right[1])):
            continue
        # Keep the kart's own footprint out of a wall; a bank touches the ground and is not a wall here.
        if any(wall(x, y, z, ux, uy, NARROW_CLEAR) for ux, uy in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0))):
            continue
        detail = {'axis': axis, 'deltas_cm': [None if left[2] is None else round(left[2], 1),
                                             None if right[2] is None else round(right[2], 1)]}
        return z, detail
    return None


def find_narrow():
    """Nearest narrow spot in 1 m rings around BASE: (Vector, detail), or (None, None)."""
    for radius in range(0, int(NARROW_RADIUS) + 1, int(NARROW_GRID)):
        count = 1 if radius == 0 else max(8, int(round(2 * math.pi * radius / NARROW_GRID)))
        for i in range(count):
            angle = 2 * math.pi * i / count
            x, y = BASE.x + radius * math.cos(angle), BASE.y + radius * math.sin(angle)
            found = narrow_at(x, y)
            if found is not None:
                return unreal.Vector(x, y, found[0]), found[1]
    return None, None


def find(kind):
    """First point within 18 m of BASE that matches a named ground shape."""
    if kind == 'narrow':
        return find_narrow()[0]
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

st = {'t': 0.0, 'phase': 0, 'index': 0, 'cases': [], 'errors': [], 'tap': 0.0, 'shapes': {}}


def finish():
    CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
    report = {'ok': not st['errors'], 'status': 'passed' if not st['errors'] else 'failed',
              'cases': st['cases'], 'shapes': st['shapes'], 'errors': st['errors']}
    json.dump(report, open(REPORT, 'w'), indent=1)
    unreal.log('KART SPAWN ' + json.dumps(report))
    live.stop('kart_spawn')


def start_case():
    kind, at = st['cases'][st['index']] if st['index'] < len(st['cases']) else (None, None)
    if kind is None:
        finish()
        return
    if at is None:
        if kind == 'narrow':
            at, detail = find_narrow()
            if detail is not None:
                st['shapes']['narrow'] = detail
        else:
            at = find(kind)
        if at is None:
            limit = NARROW_RADIUS if kind == 'narrow' else 1800.0
            st['errors'].append('no %s found within %d m of the base' % (kind, limit / 100.0))
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
