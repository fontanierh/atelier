"""Native ferry round trip. Initial setup only teleports; every audited route is driven both ways.
Run in the live bridge with OUT set to a new evidence directory. A stall fails instead of skipping ahead.
"""
import json
import math
import os
import time
import unreal

os.makedirs(OUT, exist_ok=False)
DATA = json.load(open(os.path.join(os.environ.get('ATELIER_BUILD_ROOT', os.path.join(live.ROOT, 'build')), 'yorimichi/ferry/service/service.json')))
DECK = json.load(open(os.path.join(os.environ.get('ATELIER_BUILD_ROOT', os.path.join(live.ROOT, 'build')), 'yorimichi/ferry/deck_layout.json')))
COMPANIONWAY_ONLY = globals().get('COMPANIONWAY_ONLY', False)
F = unreal.FerryLive
WORLD = live.L.game_world()
PC = unreal.GameplayStatics.get_player_controller(WORLD, 0)
PAWN = unreal.GameplayStatics.get_player_pawn(WORLD, 0)
HALF = PAWN.get_component_by_class(unreal.CapsuleComponent).get_scaled_capsule_half_height()
START = time.monotonic()
S = dict(stage='wait_hidamari', route=[], index=0, elapsed=0., stage_time=0., still=0., last=None,
         marks=[], rows=[], loops=[], photos=0, next_record=0., next_photo=0., sailed=False)


def state():
    return json.loads(F.ferry_state())


def mark(stage):
    S['marks'].append(dict(stage=stage, elapsed=S['elapsed'], state=state()))
    S['stage'], S['stage_time'], S['still'], S['last'] = stage, 0., 0., None
    print('FERRY QA', stage, round(S['elapsed'], 1), flush=True)


def walk(terminal, reverse, stage):
    route = DATA['terminals'][terminal]['walk_cm']
    S['route'] = list(reversed(route)) if reverse else route
    S['index'] = 0
    mark(stage)


def companionway_route(deck, start):
    """Ship-local metres, from the boarding walk through both companionway joins."""
    def height(surface, x):
        xs, zs = surface['x'], surface['z']
        for i in range(1, len(xs)):
            if x <= xs[i]:
                t = (x-xs[i-1])/(xs[i]-xs[i-1])
                return zs[i-1]*(1-t)+zs[i]*t
        raise ValueError('companionway waypoint outside deck')

    stair = deck['stair']
    y = sum(stair['y'])/2
    foot = stair['foot_x']-stair['tread']
    aft = foot-.8
    side = -1 if start[1] < 0 else 1
    corridor = side*4.4  # Audited aft walk: clears the canopy posts as well as the house portals.
    turn = foot-.08  # Turn before the aft lifebuoy locker, behind the stair handrail's start.
    route = [list(start), [start[0], corridor, height(deck['main_deck'], start[0])],
             [turn, corridor, height(deck['main_deck'], turn)],
             [turn, y, height(deck['main_deck'], turn)],
             [aft, y, height(deck['main_deck'], aft)], [foot, y, stair['foot_z']]]
    # Collision is the declared ramp under the visible treads. Sample it and cross the upper join.
    count = math.ceil((stair['top_x']-foot)/.5)
    route += [[foot+(stair['top_x']-foot)*i/count, y,
               stair['foot_z']+(stair['top_z']-stair['foot_z'])*i/count] for i in range(1, count+1)]
    top = stair['top_x']+.8
    route.append([top, y, height(deck['boat_deck']['z'], top)])
    return route


def begin_companionway(st):
    x, y, z = st['local']
    S['route'] = companionway_route(DECK, [x/100, -y/100, (z-HALF)/100])
    S['companionway_route'] = S['route']
    S['index'] = 0
    mark('companionway_up')


def finish(error=None):
    live.drive(0, 0)
    live.stop('ferry_roundtrip')
    live.L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    result = dict(passed=error is None, error=error, elapsed=S['elapsed'], wall_seconds=time.monotonic()-START,
                  marks=S['marks'], rows=S['rows'], loops=S['loops'], state=state(),
                  companionway_route=S.get('companionway_route'), companionway_walked=S.get('companionway_walked', False))
    json.dump(result, open(os.path.join(OUT, 'completed.json'), 'w'), indent=1)
    print('FERRY QA', 'FAILED '+str(error) if error else 'PASSED', flush=True)


def drive_route(dt, ship_local=False):
    loc = PAWN.get_actor_location()
    feet = unreal.Vector(loc.x, loc.y, loc.z-HALF)
    while S['index'] < len(S['route']):
        point = S['route'][S['index']]
        target = F.ferry_point('ship:0:%s:%s:%s' % tuple(point)) if ship_local else unreal.Vector(*point)
        dx, dy, dz = target.x-feet.x, target.y-feet.y, target.z-feet.z
        if math.hypot(dx, dy) > (12 if ship_local else 42) or abs(dz) > (35 if ship_local else 65):
            break
        S['index'] += 1
        S['still'] = 0.
    if S['index'] == len(S['route']):
        live.drive(0, 0)
        return True
    yaw = math.degrees(math.atan2(dy, dx))
    PC.set_control_rotation(unreal.Rotator(roll=0., pitch=-9., yaw=yaw))
    live.drive(forward=min(1., max(.35, math.hypot(dx, dy)/120)), right=0., gait='walk')
    position = tuple(state()['local']) if ship_local else (loc.x, loc.y, loc.z)
    prev = S['last']
    S['still'] = S['still']+dt if prev and math.dist(prev, position) < 1 else 0.
    S['last'] = position
    if S['still'] > 8 or S['stage_time'] > 120:
        raise RuntimeError('route stalled: '+S['stage']+' point '+str(S['index']))
    return False


def step(dt):
    S['elapsed'] += dt
    S['stage_time'] += dt
    if time.monotonic()-START > 2100:
        raise RuntimeError('round trip exceeded 35 minute deadline')
    st = state()
    ship = st['ships'][0]
    if S['elapsed'] >= S['next_record']:
        S['next_record'] = S['elapsed']+1
        S['rows'].append(dict(elapsed=round(S['elapsed'], 2), stage=S['stage'], index=S['index'], state=st))
        S['loops'].append([round(S['elapsed'], 2), F.ferry_loops()])
        json.dump(dict(stage=S['stage'], elapsed=S['elapsed'], index=S['index'], state=st),
                  open(os.path.join(OUT, 'progress.json'), 'w'))
    if S['elapsed'] >= S['next_photo']:
        S['next_photo'] = S['elapsed']+20
        live.L.screenshot(os.path.join(OUT, 'rider_%04d.jpg' % S['photos']))
        S['photos'] += 1
    if S['stage'] == 'wait_hidamari':
        live.drive(0, 0)
        if st['brows']['hidamari'] >= .999:
            walk(0, False, 'board_hidamari')
    elif S['stage'] == 'board_hidamari':
        if drive_route(dt):
            if not st['aboard']:
                raise RuntimeError('Hidamari walk reached deck without boarding')
            if COMPANIONWAY_ONLY:
                begin_companionway(st)
            else:
                mark('westbound')
    elif S['stage'].startswith('companionway_'):
        if not st['aboard']:
            raise RuntimeError('rider lost during companionway walk')
        if drive_route(dt, ship_local=True):
            if S['stage'] == 'companionway_up':
                S['route'] = list(reversed(S['companionway_route']))
                S['index'] = 0
                mark('companionway_down')
            else:
                S['companionway_walked'] = True
                if COMPANIONWAY_ONLY:
                    mark('complete')
                    finish()
                else:
                    mark('westbound')
    elif S['stage'].startswith('deck_'):
        if not st['aboard']:
            raise RuntimeError('rider lost during moving-deck walk')
        target = F.ferry_point('ship:0:%s:%s:%s' % tuple(S['deck_target']))
        S['route'] = [[target.x, target.y, target.z]]
        S['index'] = 0
        if drive_route(dt):
            if S['stage'] == 'deck_out':
                S['deck_target'] = S['deck_start']
                mark('deck_back')
            else:
                S['deck_walked'] = True
                begin_companionway(st)
    elif S['stage'] == 'westbound':
        live.drive(0, 0)
        S['sailed'] |= ship['speed'] > 100
        if ship['phase'] == 'cruise' and not S.get('deck_walked'):
            x, y, z = st['local']
            S['deck_start'] = [x/100, -y/100, (z-HALF)/100]
            S['deck_target'] = [x/100+2, -y/100, (z-HALF)/100]
            mark('deck_out')
            return
        if not st['aboard']:
            raise RuntimeError('rider lost on westbound voyage')
        if S['sailed'] and ship['berth'] == 1 and st['brows']['brinecove'] >= .999:
            walk(1, True, 'alight_brinecove')
    elif S['stage'] == 'alight_brinecove':
        if drive_route(dt):
            if st['aboard']:
                raise RuntimeError('still aboard on Brinecove shore')
            walk(1, False, 'board_brinecove')
    elif S['stage'] == 'board_brinecove':
        if drive_route(dt):
            if not st['aboard']:
                raise RuntimeError('Brinecove walk reached deck without boarding')
            S['sailed'] = False
            mark('eastbound')
    elif S['stage'] == 'eastbound':
        live.drive(0, 0)
        S['sailed'] |= ship['speed'] > 100
        if not st['aboard']:
            raise RuntimeError('rider lost on eastbound voyage')
        if S['sailed'] and ship['berth'] == 0 and st['brows']['hidamari'] >= .999:
            walk(0, True, 'alight_hidamari')
    elif S['stage'] == 'alight_hidamari':
        if drive_route(dt):
            if st['aboard']:
                raise RuntimeError('still aboard on Hidamari shore')
            mark('complete')
            finish()


def run(dt):
    try:
        step(dt)
    except Exception as error:
        finish(repr(error))
        raise


assert F.ferry_go('hidamari'), 'initial terminal travel failed'
live.L.audio_log('start')
mark('wait_hidamari')
live.behave('ferry_roundtrip', run)
print('FERRY QA running', OUT, flush=True)
