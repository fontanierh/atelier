"""Equipment around the kart: the paraglider is stowed while driving and comes back on foot.

    atelier live py - < games/yorimichi/scenarios/kart_equipment.py

Runs on the beach flat: opens the glider in the air, lands, summons the car, checks the canopy is not on the kart,
steps out, then opens the glider again to prove driving left the equipment working. Writes
build/yorimichi/kart_film/kart_equipment.json with every check and two stills.
"""
import json
import importlib.util
import os
import unreal

L = live.L
ROOT = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
OUT = os.path.join(ROOT, 'yorimichi/kart_film')
os.makedirs(OUT, exist_ok=True)
_spec = importlib.util.spec_from_file_location('kart_cleanup', os.path.join(live.ROOT, 'games/yorimichi/scenarios/kart_cleanup.py'))
CLEAN = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CLEAN)

REPORT = os.path.join(OUT, 'kart_equipment.json')
# A previous success must not survive a failed run: the receipt is invalid while this one is armed.
json.dump({'ok': False, 'status': 'running', 'checks': [], 'errors': []}, open(REPORT, 'w'), indent=1)


def glider_visible():
    world = unreal.LiveLibrary.game_world()
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    if not pawn:
        return None
    for component in pawn.get_components_by_class(unreal.SkeletalMeshComponent):
        if component.get_name() == 'Paraglider':
            return bool(component.is_visible())
    return None


def press(key):
    L.input_key(key, 'press', 1.0)
    L.input_key(key, 'release', 0.0)


def lift(metres):
    """Put the player in the air: the ground-only teleport verb would snap them back down."""
    world = unreal.LiveLibrary.game_world()
    pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
    ground = L.ground_at(BEACH)
    pawn.set_actor_location(unreal.Vector(ground.x, ground.y, ground.z + metres * 100.0), False, True)


st = {'t': 0.0, 'phase': 0, 'checks': [], 'errors': [], 'shots': []}


def check(name, ok, detail=''):
    st['checks'].append({'check': name, 'ok': bool(ok), 'detail': detail})
    if not ok:
        st['errors'].append(name + (': ' + detail if detail else ''))


def shot(name):
    path = os.path.join(OUT, name)
    L.screenshot(path)
    st['shots'].append(path)


BEACH = unreal.Vector(-23600.0, 16000.0, 0.0)


def run(dt):
    try:
        st['t'] += dt
        t = st['t']
        if st['phase'] == 0 and t > 0.3:
            st['phase'] = 1
            live.stop('kart_film')
            if 'driving=1' in L.car_state():
                live.press('car')
            ground = L.ground_at(BEACH)
            L.teleport_player(ground, 0.0)
            L.fixed_step(60)
        elif st['phase'] == 1 and t > 0.8:
            st['phase'] = 2
            lift(18.0)
        elif st['phase'] == 2 and t > 1.5:
            st['phase'] = 3
            press('SpaceBar')   # Cairo's double jump; any other rider jumps its aerial move
        elif st['phase'] == 3 and t > 1.9:
            st['phase'] = 4
            press('SpaceBar')   # the glider opens on the next press in the air
        elif st['phase'] == 4 and t > 2.4:
            st['phase'] = 5
            check('glider opens in the air', glider_visible() is True, 'visible=%r' % glider_visible())
            ground = L.ground_at(BEACH)
            L.teleport_player(ground, 0.0)
        elif st['phase'] == 5 and t > 3.2:
            st['phase'] = 6
            check('glider stowed after landing', glider_visible() is False, 'visible=%r' % glider_visible())
            live.press('car')
        elif st['phase'] == 6 and t > 3.9:
            st['phase'] = 7
            state = L.car_state()
            check('car is out', 'driving=1' in state, state)
            check('no glider while driving', glider_visible() is False, 'visible=%r' % glider_visible())
            shot('kart_equipment_drive.png')
        elif st['phase'] == 7 and t > 4.4:
            st['phase'] = 8
            live.press('car')
        elif st['phase'] == 8 and t > 5.2:
            st['phase'] = 9
            state = L.car_state()
            check('car parked', 'driving=0' in state, state)
            check('no glider back on foot', glider_visible() is False, 'visible=%r' % glider_visible())
            shot('kart_equipment_foot.png')
        elif st['phase'] == 9 and t > 5.6:
            st['phase'] = 10
            lift(18.0)
        elif st['phase'] == 10 and t > 6.3:
            st['phase'] = 11
            press('SpaceBar')
        elif st['phase'] == 11 and t > 6.7:
            st['phase'] = 12
            press('SpaceBar')
        elif st['phase'] == 12 and t > 7.2:
            st['phase'] = 13
            check('glider still opens after driving', glider_visible() is True, 'visible=%r' % glider_visible())
            CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
            json.dump({'ok': not st['errors'], 'status': 'passed' if not st['errors'] else 'failed',
                       'checks': st['checks'], 'shots': st['shots'], 'errors': st['errors']},
                      open(REPORT, 'w'), indent=1)
            unreal.log('KART EQUIPMENT %s' % ('PASS' if not st['errors'] else 'FAIL: ' + '; '.join(st['errors'])))
            live.stop('kart_equipment')
    except Exception as error:
        st['errors'].append(repr(error))
        CLEAN.cleanup(live, unreal.MegaParkValidation.restore_player_camera)
        json.dump({'ok': False, 'status': 'failed', 'checks': st['checks'], 'errors': st['errors']},
                  open(REPORT, 'w'), indent=1)
        unreal.log_error('KART EQUIPMENT: %s' % error)
        live.stop('kart_equipment')


live.behave('kart_equipment', run)
print('kart equipment armed')

