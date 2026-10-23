"""Walk from the rim landing into the Kiyomizu hoist portal, ride up to p183, and ride back down.

    atelier live py - < games/yorimichi/scenarios/crater_tower_hoist.py

Proves:
1. Outside the 2.5 m portal proximity radius (on the 6x6 m landing at x=133150 cm, 4.6 m away),
   Interact does not trigger Ride up.
2. Walking west into the 3.2x3.2x4.5 m hoist portal (within 250 cm of (132690, -249400, 75964) cm)
   and pressing Interact rides up to the p183 deck (feet z ~ 85800 cm).
3. Pressing Interact on the p183 deck rides back down to the 6x6 m rim landing (feet z ~ 75960 cm).
"""
import json
import math
import os
import unreal

L = live.L
ROOT = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
OUT = os.path.join(ROOT, 'yorimichi/crater_tower_hoist')
os.makedirs(OUT, exist_ok=True)
REPORT = os.path.join(OUT, 'completed.json')
json.dump({'ok': False, 'status': 'running', 'errors': []}, open(REPORT, 'w'), indent=1)

WORLD = L.game_world()
PAWN = unreal.GameplayStatics.get_player_pawn(WORLD, 0)
HALF = PAWN.get_component_by_class(unreal.CapsuleComponent).get_scaled_capsule_half_height()

LANDING_CM = unreal.Vector(133150.0, -249400.0, 75960.0)
PORTAL_XY_CM = (132690.0, -249400.0)
PORTAL_Z_CM = 75964.0
DECK_Z_CM = 85800.0
PROXIMITY_CM = 250.0

st = {
    't': 0.0,
    'phase': 0,
    'landing_z_cm': None,
    'portal_dist_cm': None,
    'deck_z_cm': None,
    'return_z_cm': None,
    'errors': [],
}


def feet():
    loc = PAWN.get_actor_location()
    return float(loc.x), float(loc.y), float(loc.z) - float(HALF)


def finish():
    live.drive(0.0, 0.0)
    report = {
        'ok': not st['errors'],
        'status': 'passed' if not st['errors'] else 'failed',
        'landing_z_cm': st['landing_z_cm'],
        'portal_dist_cm': st['portal_dist_cm'],
        'deck_z_cm': st['deck_z_cm'],
        'return_z_cm': st['return_z_cm'],
        'errors': st['errors'],
    }
    json.dump(report, open(REPORT, 'w'), indent=1)
    unreal.log('CRATER TOWER HOIST ' + json.dumps(report))
    live.stop('crater_tower_hoist')


def step(dt):
    try:
        st['t'] += dt
        t = st['t']
        fx, fy, fz = feet()
        if st['phase'] == 0 and t > 0.3:
            st['phase'] = 1
            L.teleport_player(LANDING_CM, 180.0)
        elif st['phase'] == 1 and t > 1.0:
            st['landing_z_cm'] = round(fz, 1)
            # At 4.6 m from the portal (> 2.5 m proximity), Interact must not ride up.
            live.press('interact')
            st['phase'] = 2
        elif st['phase'] == 2 and t > 1.5:
            if abs(fz - PORTAL_Z_CM) > 150.0:
                st['errors'].append(f'interact outside 2.5m radius unexpectedly teleported to z={fz:.1f}')
                finish()
                return
            # Walk west from the rim landing into the hoist portal.
            live.drive(1.0, 0.0)
            st['phase'] = 3
        elif st['phase'] == 3:
            dist = math.hypot(fx - PORTAL_XY_CM[0], fy - PORTAL_XY_CM[1])
            if dist <= PROXIMITY_CM - 30.0:
                live.drive(0.0, 0.0)
                st['portal_dist_cm'] = round(dist, 1)
                live.press('interact')
                st['phase'] = 4
                st['t_interact'] = t
            elif t > 8.0:
                st['errors'].append(f'failed to walk into portal proximity (dist={dist:.1f} cm)')
                finish()
        elif st['phase'] == 4 and t > st.get('t_interact', 0.0) + 0.8:
            st['deck_z_cm'] = round(fz, 1)
            if abs(fz - DECK_Z_CM) > 120.0:
                st['errors'].append(f'Ride up did not reach p183 deck z~85800 (got {fz:.1f})')
                finish()
                return
            # Ride back down from the p183 deck to the rim landing.
            live.press('interact')
            st['phase'] = 5
            st['t_down'] = t
        elif st['phase'] == 5 and t > st.get('t_down', 0.0) + 0.8:
            st['return_z_cm'] = round(fz, 1)
            if abs(fz - PORTAL_Z_CM) > 120.0:
                st['errors'].append(f'Ride down did not return to rim landing z~75960 (got {fz:.1f})')
            finish()
    except Exception as exc:
        st['errors'].append(str(exc))
        finish()


live.behave('crater_tower_hoist', step)
