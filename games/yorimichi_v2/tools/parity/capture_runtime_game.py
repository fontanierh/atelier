"""Game side of capture_runtime.py: runs inside a running game (the donor or V2) through its live bridge, with PARAMS.

For each pose it travels the player below the pose (so streaming and any player-centred runtime scenery load there),
hides the player and the HUD, views from a hidden prop at the pose (the pose FOV on the camera manager), waits PARAMS['settle_s'] for streaming and
temporal effects, then screenshots the viewport to PARAMS['out']/<pose>.png. A post-tick callback paces the steps
on game frames. It writes PARAMS['out']/done.json (the render settings, or the error) and removes itself.
"""
import json
import time
from pathlib import Path

import unreal as U

L = U.LiveLibrary
OUT = Path(PARAMS['out'])
POSES = PARAMS['poses']
SETTLE = float(PARAMS.get('settle_s', 8))
COMPILE_WAIT_S = 300.   # after the settle, the longest wait for assets still compiling before a pose is refused
# V2 counts the assets still compiling (the "Preparing Static Meshes" message); the donor has no such verb.
PENDING = getattr(getattr(U, 'YorimichiLive', None), 'pending_asset_compiles', None)
QUALITY = ('r.ForwardShading', 'r.ScreenPercentage', 'sg.ResolutionQuality', 'sg.ViewDistanceQuality', 'sg.AntiAliasingQuality',
           'sg.ShadowQuality', 'sg.GlobalIlluminationQuality', 'sg.ReflectionQuality', 'sg.PostProcessQuality',
           'sg.TextureQuality', 'sg.EffectsQuality', 'sg.FoliageQuality', 'sg.ShadingQuality')

world = L.game_world()
controller = U.GameplayStatics.get_player_controller(world, 0)
hidden = []   # every pawn hidden: the game may replace the controlled pawn when it teleports
# The view target: a hidden one-triangle prop (Python cannot spawn a CameraActor in a game world). An actor without a
# camera is viewed from its own location and rotation, with the camera manager's default FOV.
camera = L.spawn_model('parity_camera', PARAMS['camera_glb'], U.Vector(0, 0, 0), 0.0, 1.0, 'none', '')
camera.set_actor_hidden_in_game(True)
manager = controller.player_camera_manager
default_fov = manager.get_editor_property('default_fov')
state = {'pose': 0, 'phase': 'place', 'until': 0.0, 'shot': None, 'compiled_by': 0.0}
waits = {}   # pose -> seconds it waited past the settle for compiling assets (V2)


def hide_pawn():
    pawn = controller.get_controlled_pawn()
    if pawn:
        pawn.set_actor_hidden_in_game(True)
        if pawn not in hidden:
            hidden.append(pawn)


def place(pose):
    x, y, z = pose['location']
    r = pose['rotation']
    travel = getattr(getattr(U, 'YorimichiLive', None), 'travel', None)
    if not (travel and travel(U.Vector(x, y, z), r['yaw'])):   # the donor has no Travel: the platform teleport
        L.teleport_player(U.Vector(x, y, z), r['yaw'])
    hide_pawn()
    hud = controller.get_hud()
    if hud:
        hud.set_editor_property('show_hud', False)
    camera.set_actor_location_and_rotation(U.Vector(x, y, z), U.Rotator(roll=r['roll'], pitch=r['pitch'], yaw=r['yaw']),
                                           False, True)
    manager.set_editor_property('default_fov', float(pose['fov']))
    controller.set_view_target_with_blend(camera, 0.0)


def finish(result):
    U.unregister_slate_post_tick_callback(HANDLE)
    try:
        camera.destroy_actor()
        manager.set_editor_property('default_fov', default_fov)
        for pawn in hidden:
            pawn.set_actor_hidden_in_game(False)
        controller.set_view_target_with_blend(controller.get_controlled_pawn(), 0.0)
    finally:
        (OUT / 'done.json').write_text(json.dumps(result))


def tick(_dt):
    now = time.monotonic()
    try:
        if state['pose'] >= len(POSES):
            finish({'render': {'renderer': 'runtime viewport screenshot (LiveLibrary.Screenshot)',
                               'quality': {c: U.SystemLibrary.get_console_variable_float_value(c) for c in QUALITY}},
                    'map': world.get_path_name().split('.')[0], 'engine_version': U.SystemLibrary.get_engine_version(),
                    'compile_waits_s': waits if PENDING else None})
            return
        pose = POSES[state['pose']]
        if state['phase'] == 'place':
            place(pose)
            state.update(phase='settle', until=now + SETTLE)
        elif state['phase'] == 'settle' and now >= state['until']:
            # A view is finished only when nothing is still compiling: a mesh being prepared renders as a proxy or not at all.
            if PENDING and PENDING() > 0:
                if not state['compiled_by']:
                    state['compiled_by'] = now + COMPILE_WAIT_S
                elif now >= state['compiled_by']:
                    raise RuntimeError(f'{pose["name"]}: {PENDING()} asset(s) still compiling {COMPILE_WAIT_S:.0f} s after the settle')
                return
            if state['compiled_by']:
                waits[pose['name']] = round(now - (state['compiled_by'] - COMPILE_WAIT_S), 1)
            state['compiled_by'] = 0.0
            hide_pawn()
            controller.set_view_target_with_blend(camera, 0.0)
            state['shot'] = OUT / f'{pose["name"]}.png'
            L.screenshot(str(state['shot']))
            state.update(phase='shoot', until=now + 120)
        elif state['phase'] == 'shoot':
            if state['shot'].is_file() and state['shot'].stat().st_size > 0:
                state.update(pose=state['pose'] + 1, phase='place')
            elif now >= state['until']:
                raise RuntimeError(f'{pose["name"]}: no screenshot after 120 s')
    except Exception as error:   # never leave a broken callback ticking
        finish({'error': repr(error)})


OUT.mkdir(parents=True, exist_ok=True)
HANDLE = U.register_slate_post_tick_callback(tick)
print('capture started', OUT, len(POSES), 'poses')
