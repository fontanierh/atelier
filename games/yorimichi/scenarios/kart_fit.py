"""All four riders in the kart, from the angles the fit review needs.

    atelier live py - < games/yorimichi/scenarios/kart_fit.py

Switches the playable character in place, summons the kart on the flat village road and captures front, rear, both sides,
an elevated seat view and a grip close-up per rider. The review camera is restored and the kart parked afterward.
Writes build/yorimichi/kart_film/kart_fit.json with each rider's mesh, car state, ride telemetry and glider state.
"""
import json
import importlib.util
import math
import os
import re
import unreal

L = live.L
MV = unreal.MegaParkValidation
ROOT = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
OUT = os.path.join(ROOT, 'yorimichi/kart_film/fit')
os.makedirs(OUT, exist_ok=True)
_spec = importlib.util.spec_from_file_location('kart_cleanup', os.path.join(live.ROOT, 'games/yorimichi/scenarios/kart_cleanup.py'))
CLEAN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CLEAN)
try:
    PREPARED = {'models': {name: json.load(open(os.path.join(live.ROOT,
                'games/yorimichi/assets/characters', name, 'kart-grip-model.json')))
                for name in ('cairo', 'modori', 'nox', 'paul')}}
except Exception:
    PREPARED = {'models': {}}

flags = {}


def scale_of(state):
    match = re.search(r'scale=([0-9.]+)', state)
    return float(match.group(1)) if match else None

# This scenario intentionally captures the four operator-approved riders as a fixed QA set.
RIDERS = ['Cairo', 'Modori', 'Nox', 'Paul']
# (name, forward, right, up, aim forward, aim up, fov)
VIEWS = [
    ('front', 480.0, 0.0, 160.0, 0.0, 60.0, 50.0),
    ('rear', -480.0, 0.0, 160.0, 0.0, 60.0, 50.0),
    ('left', 0.0, -520.0, 130.0, 0.0, 60.0, 50.0),
    ('right', 0.0, 520.0, 130.0, 0.0, 60.0, 50.0),
    ('seat', 250.0, 0.0, 300.0, 0.0, 30.0, 55.0),
]
BEACH = unreal.Vector(-25542.0, 10140.0, 0.0)   # the flat village road: the sand dunes refuse the larger karts
REQUIRED_VIEWS = [view[0] for view in VIEWS] + ['grip_left_steer', 'grip_right_steer', 'grip_left_steer_other',
                                                'grip_right_steer_other', 'grip_left_neutral', 'grip_right_neutral']


def frame(loc, yaw, forward, right, up, aim_forward, aim_up):
    r = math.radians(yaw)
    f = unreal.Vector(math.cos(r), math.sin(r), 0.0)
    rt = unreal.Vector(-math.sin(r), math.cos(r), 0.0)
    eye = loc + f * forward + rt * right + unreal.Vector(0, 0, up)
    at = loc + f * aim_forward + unreal.Vector(0, 0, aim_up)
    return eye, at


def glider_visible():
    world = unreal.LiveLibrary.game_world()
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    for component in pawn.get_components_by_class(unreal.SkeletalMeshComponent):
        if component.get_name() == 'Paraglider':
            return bool(component.is_visible())
    return None


def hand_shot(side, rider, state):
    """A close-up of one hand on the rim, aimed from the hand bone itself rather than the pawn origin."""
    if not flags.get(rider):
        return
    world = unreal.LiveLibrary.game_world()
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    mesh = None
    for component in pawn.get_components_by_class(unreal.SkeletalMeshComponent):
        if component.get_name() in ('CharacterMesh0', 'Mesh'):
            mesh = component
            break
    if not mesh:
        return
    bone = 'hand_L' if side == 'left' else 'hand_R'
    hand = mesh.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_WORLD).translation
    _, yaw = live.player()
    r = math.radians(yaw)
    forward = unreal.Vector(math.cos(r), math.sin(r), 0.0)
    right = unreal.Vector(-math.sin(r), math.cos(r), 0.0)
    lateral = -45.0 if side == 'left' else 45.0
    eye = hand + forward * 55.0 + right * lateral + unreal.Vector(0, 0, 18)
    MV.review_camera(eye, hand, 30.0)
    L.screenshot(os.path.join(OUT, '%s_grip_%s_%s.png' % (rider.lower(), side, state)))


queue = []


def later(delay, fn):
    queue.append([delay, fn])


def build():
    for index, rider in enumerate(RIDERS):
        def select(rider=rider):
            print('rider %s -> %s' % (rider, L.switch_character(rider)))
            for name in os.listdir(OUT):
                if name.startswith(rider.lower() + '_'):
                    os.remove(os.path.join(OUT, name))

        def park():
            if 'driving=1' in L.car_state():
                live.press('car')
                L.fixed_step(60)

        def place(index=index):
            ground = L.ground_at(BEACH)
            L.teleport_player(ground, 0.0)

        def summon(index=index, rider=rider):
            live.press('car')
            if 'driving=1' not in L.car_state():
                # A crest or a slope can refuse the car; try a second flat patch before recording a failure.
                ground = L.ground_at(BEACH + unreal.Vector(450.0, 400.0, 0.0))
                L.teleport_player(ground, 0.0)
                live.press('car')
            flags[rider] = 'driving=1' in L.car_state()

        def record(rider=rider):
            world = unreal.LiveLibrary.game_world()
            pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
            mesh = None
            for component in pawn.get_components_by_class(unreal.SkeletalMeshComponent):
                if component.get_name() in ('CharacterMesh0', 'Mesh'):
                    mesh = component.get_skeletal_mesh_asset()
                    break
            result = {'rider': rider,
                      'pawn': pawn.get_class().get_name(),
                      'mesh': mesh.get_path_name() if mesh else None,
                      'summon_ok': bool(flags.get(rider)),
                      'live_scale': scale_of(L.car_state()),
                      'prepared_scale': PREPARED.get('models', {}).get(rider.lower(), {}).get('scale'),
                      'car': L.car_state(),
                      'ride': L.car_ride(),
                      'glider_visible': glider_visible(),
                      'views': OUT}
            results.append(result)

        def restore():
            MV.restore_player_camera()

        def settings():
            L.fixed_step(60)

        later(0.2, settings)
        later(0.1, select)
        later(1.2, park)
        later(0.6, place)
        later(0.7, summon)
        later(0.7, lambda: L.input_key('D', 'press', 1.0))
        for view, forward, right, up, aim_forward, aim_up, fov in VIEWS:
            def shot(view=view, forward=forward, right=right, up=up, aim_forward=aim_forward,
                     aim_up=aim_up, fov=fov, rider=rider):
                if not flags.get(rider):
                    return
                loc, yaw = live.player()
                eye, at = frame(loc, yaw, forward, right, up, aim_forward, aim_up)
                MV.review_camera(eye, at, fov)
                L.screenshot(os.path.join(OUT, '%s_%s.png' % (rider.lower(), view)))
            later(0.3, shot)
        later(0.3, lambda rider=rider: hand_shot('left', rider, 'steer'))
        later(0.3, lambda rider=rider: hand_shot('right', rider, 'steer'))
        later(0.2, lambda: L.input_key('D', 'release', 0.0))
        later(0.2, lambda: L.input_key('A', 'press', 1.0))
        later(0.4, lambda rider=rider: hand_shot('left', rider, 'steer_other'))
        later(0.3, lambda rider=rider: hand_shot('right', rider, 'steer_other'))
        later(0.2, lambda: L.input_key('A', 'release', 0.0))
        later(0.5, lambda rider=rider: hand_shot('left', rider, 'neutral'))
        later(0.3, lambda rider=rider: hand_shot('right', rider, 'neutral'))
        later(0.2, restore)
        later(0.2, record)
        later(0.2, park)


results = []
build()
json_path = os.path.join(OUT, 'kart_fit.json')
json.dump({'ok': False, 'status': 'running', 'riders': []}, open(json_path, 'w'), indent=1)
clock = {'t': 0.0}
finished = {'value': False}


def tick(dt):
    try:
        if finished['value']:
            return
        if not queue:
            finished['value'] = True
            CLEAN.cleanup(live, MV.restore_player_camera)
            errors = []
            for rider in RIDERS:
                if not flags.get(rider):
                    errors.append('%s did not mount' % rider)
                missing = [name for name in REQUIRED_VIEWS
                           if not os.path.exists(os.path.join(OUT, '%s_%s.png' % (rider.lower(), name)))]
                if missing:
                    errors.append('%s missing %s' % (rider, ', '.join(missing)))
            for item in results:
                actual, expected = item['live_scale'], item['prepared_scale']
                if (not isinstance(actual, (int, float)) or not math.isfinite(actual) or actual <= 0
                        or not isinstance(expected, (int, float)) or not math.isfinite(expected) or expected <= 0
                        or abs(actual / expected - 1) > .01):
                    errors.append('%s live/prepared scale mismatch: %s / %s (1%% limit)' %
                                  (item['rider'], actual, expected))
            ok = not errors
            json.dump({'ok': ok, 'status': 'passed' if ok else 'failed', 'riders': results, 'errors': errors},
                      open(json_path, 'w'), indent=1)
            print('kart fit done: %d riders, %d errors' % (len(results), len(errors)))
            unreal.log('KART FIT COMPLETE %d errors %d' % (len(results), len(errors)))
            live.stop('kart_fit')
            return
        queue[0][0] -= dt
        if queue[0][0] <= 0.0:
            fn = queue.pop(0)[1]
            fn()
    except Exception as error:
        finished['value'] = True
        CLEAN.cleanup(live, MV.restore_player_camera)
        json.dump({'ok': False, 'status': 'failed', 'riders': results, 'errors': [repr(error)]},
                  open(json_path, 'w'), indent=1)
        unreal.log_error('KART FIT: %s' % error)
        queue.clear()
        live.stop('kart_fit')


live.behave('kart_fit', tick)
print('kart fit armed: %d riders' % len(RIDERS))

