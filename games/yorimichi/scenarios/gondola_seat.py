"""Verify gondola bench seating, first-person view with +-100 deg yaw / +-60 deg pitch look clamp,
plumb cabin with no wall clipping, and standing up back to third-person on arrival.
"""
import json
import math
import os
import time
import unreal

os.makedirs(OUT, exist_ok=False)
DATA = json.load(open(os.path.join(os.environ.get('ATELIER_BUILD_ROOT', os.path.join(live.ROOT, 'build')), 'yorimichi/gondola/runtime.json')))
LINE = globals().get('LINE', 'L1')
SPEC = next(row for row in DATA['lines'] if row['id'] == LINE)
STATIONS = {row['id']: row for row in DATA['stations']}
FIRST, LAST = SPEC['stations']
G = unreal.GondolaLive
WORLD = live.L.game_world()
PC = unreal.GameplayStatics.get_player_controller(WORLD, 0)
PAWN = unreal.GameplayStatics.get_player_pawn(WORLD, 0)
HALF = PAWN.get_component_by_class(unreal.CapsuleComponent).get_scaled_capsule_half_height()
MOVEMENT = PAWN.get_component_by_class(unreal.CharacterMovementComponent)
START = time.monotonic()
S = dict(
    stage='',
    elapsed=0.0,
    stage_time=0.0,
    route=[],
    index=0,
    still=0.0,
    last=None,
    cabin=-1,
    sailed=False,
    clamp_step=0,
    checks=dict(
        seated_on_board=False,
        first_person_active=False,
        head_hidden=False,
        look_clamped_pos=False,
        look_clamped_neg=False,
        cabin_plumb=True,
        no_wall_clip=True,
        stood_on_arrival=False,
        third_person_restored=False,
    ),
    marks=[],
)


def state():
    return json.loads(G.gondola_state())


def rider_row(st):
    return next((row for row in st['riders'] if row['name'] == PAWN.get_name()), None)


def wrap_deg(angle):
    return (angle + 180.0) % 360.0 - 180.0


def mark(stage):
    S.update(stage=stage, stage_time=0.0, still=0.0, last=None)
    S['marks'].append(dict(stage=stage, elapsed=round(S['elapsed'], 2), state=state()))
    print('GONDOLA SEAT QA', LINE, stage, round(S['elapsed'], 1), flush=True)


def route(points, stage):
    S.update(route=points, index=0)
    mark(stage)


def finish(error=None):
    live.drive(0, 0)
    live.stop('gondola_seat')
    passed = error is None and all(S['checks'].values())
    if error is None and not passed:
        error = f"incomplete checks: {S['checks']}"
    json.dump(
        dict(
            passed=passed,
            error=error,
            line=LINE,
            elapsed=round(S['elapsed'], 2),
            wall_seconds=round(time.monotonic() - START, 2),
            checks=S['checks'],
            marks=S['marks'],
            state=state(),
        ),
        open(os.path.join(OUT, 'completed.json'), 'w'),
        indent=1,
    )
    print('GONDOLA SEAT QA', 'PASSED' if passed else f'FAILED {error}', LINE, flush=True)


def drive(dt):
    loc = PAWN.get_actor_location()
    feet = (loc.x, loc.y, loc.z - HALF)
    while S['index'] < len(S['route']):
        target = S['route'][S['index']]
        dx, dy, dz = [a - b for a, b in zip(target, feet)]
        if math.hypot(dx, dy) > 12.0 or abs(dz) > 60.0:
            break
        S['index'] += 1
        S['still'] = 0.0
    if S['index'] == len(S['route']):
        live.drive(0, 0)
        return True
    PC.set_control_rotation(unreal.Rotator(roll=0.0, pitch=-8.0, yaw=math.degrees(math.atan2(dy, dx))))
    live.drive(forward=1.0, right=0.0, gait='walk')
    displacement = math.dist(S['last'], feet) if S['last'] else None
    S['still'] = S['still'] + dt if displacement is not None and displacement < 0.5 else 0.0
    S['last'] = feet
    if S['still'] > 8.0:
        raise RuntimeError(f"walking stalled {S['stage']} waypoint {S['index']}")
    if S['stage_time'] > 240.0:
        raise RuntimeError(f"walking deadline {S['stage']} waypoint {S['index']}")
    return False


def boarding_candidate(st, station):
    clock = SPEC['clock']
    cycle = clock['cycle_s']
    first = sum(row['cabins'] for row in DATA['lines'][: next(i for i, r in enumerate(DATA['lines']) if r['id'] == LINE)])
    for cabin in st['cabins']:
        if cabin['line'] != LINE or cabin['station'] != station or cabin['side'] != 1 or cabin['door'] <= 0.999:
            continue
        index = cabin['index'] - first
        phase = (st['time'] + cycle * index / SPEC['cabins']) % cycle
        if any(
            stop['station'] == station and stop['side'] == 1 and stop['start'] <= phase < stop['end'] and stop['end'] - phase >= 9.0
            for stop in clock['stops']
        ):
            return cabin
    return None


def step(dt):
    S['elapsed'] += dt
    S['stage_time'] += dt
    if time.monotonic() - START > 1200.0:
        raise RuntimeError('gondola seat scenario exceeded 20 minutes')
    st = state()
    rider = rider_row(st)
    if S['stage'] == 'approach':
        if drive(dt):
            mark('wait_cabin')
    elif S['stage'] == 'wait_cabin':
        live.drive(0, 0)
        ready = boarding_candidate(st, FIRST)
        if ready:
            S['cabin'] = ready['index']
            route(S['board_tail'], 'boarding')
        elif S['stage_time'] > 240.0:
            raise RuntimeError('no outbound cabin reached ' + FIRST)
    elif S['stage'] == 'boarding':
        if drive(dt):
            if not rider or rider['cabin'] != S['cabin']:
                raise RuntimeError('boarding route did not enter expected cabin')
            mark('seated_ride')
    elif S['stage'] == 'seated_ride':
        live.drive(0, 0)
        if not rider or rider['cabin'] != S['cabin']:
            raise RuntimeError('rider lost from cabin')
        cabin = next(c for c in st['cabins'] if c['index'] == S['cabin'])
        if cabin['floor_tilt_deg'] > 0.01:
            S['checks']['cabin_plumb'] = False
            raise RuntimeError(f"cabin floor tilted: {cabin['floor_tilt_deg']}")
        if not rider.get('no_clip', False) or rider.get('wall_clearance_cm', -1.0) <= 0.0:
            S['checks']['no_wall_clip'] = False
            raise RuntimeError(f"rider body capsule clipped cabin wall: {rider}")
        if rider.get('seated') and rider.get('seat_id') in ('back_left', 'back_right', 'west', 'east'):
            S['checks']['seated_on_board'] = True
        if S['stage_time'] > 0.6 and rider.get('first_person') and rider.get('head_hidden') and rider.get('camera_blend', 0.0) >= 0.99:
            S['checks']['first_person_active'] = True
            S['checks']['head_hidden'] = True
            base_yaw = float(PAWN.get_actor_rotation().yaw)
            if S['clamp_step'] == 0:
                PC.set_control_rotation(unreal.Rotator(roll=0.0, pitch=85.0, yaw=base_yaw + 150.0))
                S['clamp_step'] = 1
            elif S['clamp_step'] == 1:
                rot = PC.get_control_rotation()
                if abs(wrap_deg(rot.yaw - base_yaw)) <= 100.1 and abs(wrap_deg(rot.pitch)) <= 60.1:
                    S['checks']['look_clamped_pos'] = True
                PC.set_control_rotation(unreal.Rotator(roll=0.0, pitch=-85.0, yaw=base_yaw - 150.0))
                S['clamp_step'] = 2
            elif S['clamp_step'] == 2:
                rot = PC.get_control_rotation()
                if abs(wrap_deg(rot.yaw - base_yaw)) <= 100.1 and abs(wrap_deg(rot.pitch)) <= 60.1:
                    S['checks']['look_clamped_neg'] = True
                PC.set_control_rotation(unreal.Rotator(roll=0.0, pitch=0.0, yaw=base_yaw))
                S['clamp_step'] = 3
        S['sailed'] |= cabin['speed_m_s'] > 1.0
        if S['sailed'] and cabin['station'] == LAST and cabin['side'] == -1 and cabin['door'] > 0.999:
            if rider.get('seated'):
                raise RuntimeError('rider did not stand up on arrival')
            S['checks']['stood_on_arrival'] = True
            mark('stand_blend')
    elif S['stage'] == 'stand_blend':
        live.drive(0, 0)
        if S['stage_time'] >= 0.45:
            if rider and (rider.get('first_person') or rider.get('head_hidden') or rider.get('camera_blend', 1.0) > 0.01):
                raise RuntimeError(f'third-person camera did not restore after 0.4 s: {rider}')
            S['checks']['third_person_restored'] = True
            route(list(reversed(STATIONS[LAST]['boarding_cm']['-1'])), 'alight')
    elif S['stage'] == 'alight':
        if drive(dt):
            if rider is not None:
                raise RuntimeError('still aboard after walking out onto arrival platform')
            mark('complete')
            finish()


def run(dt):
    try:
        step(dt)
    except Exception as error:
        finish(repr(error))
        raise


assert G.gondola_go(FIRST), 'initial station setup failed'
points = STATIONS[FIRST]['boarding_cm']['1']
end = points[-1]
split = max(i for i, p in enumerate(points) if math.dist(p[:2], end[:2]) > 150.0)
S['board_tail'] = points[split + 1 :]
route(points[: split + 1], 'approach')
live.behave('gondola_seat', run)
print('GONDOLA SEAT QA running', LINE, OUT, flush=True)
