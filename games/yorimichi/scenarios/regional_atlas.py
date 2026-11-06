"""Review the actual native regional atlas in an already guarded game.

The game must use explicit, isolated -markersave and -atlasnamesfile paths.
This checks real travel resolvers and Slate controller input, saves unretouched
UI screenshots, and leaves normal player saves alone. The caller owns the game.
"""
import argparse
import json
import math
from pathlib import Path
import time

from atelier import live, paths


REGIONS = {'momiji_coast', 'momiji_woods', 'hidamari', 'temple_island',
           'northern_foothills', 'volcanic_highlands', 'haras_valley', 'brinecove'}
DESTINATIONS = {'spawn', 'hamlet', 'mega', 'fishing', 'cove', 'landing', 'temple', 'arrival', 'arcade',
                'plaza', 'harbor', 'hillside', 'park', 'station', 'foothills', 'forest_lake', 'megapark',
                'craterpark', 'skatepier', 'hippodrome', 'ronin_camp', 'zeppelin_forest', 'zeppelin_city',
                'zeppelin_megapark', 'zeppelin_belmonte', 'belmonte', 'belmonte_course', 'belmonte_training',
                'hidamari_station', 'belmonte_station', 'belmonte_salon', 'brinecove_quay'}
REGION_STOPS = dict(momiji_coast='spawn', momiji_woods='hamlet', hidamari='plaza', temple_island='temple',
                    northern_foothills='megapark', volcanic_highlands='craterpark', haras_valley='belmonte',
                    brinecove='brinecove_quay')


def same_leg_times(actual, expected):
    """Compare endpoint identity exactly and durations with a float32-sized tolerance."""
    return len(actual) == len(expected) and all(
        a[0] == e[0] and a[1] == e[1] and math.isclose(float(a[2]), float(e[2]), rel_tol=0., abs_tol=1e-4)
        for a, e in zip(actual, expected))


def py(code):
    result = live.request('/python', 'import json\np=unreal.LiveLibrary.player(); m=p.get_map()\n'+code, timeout=10)
    if not result.get('ok'):
        raise RuntimeError(result)
    return result.get('output', '')


def value(expression):
    return json.loads(py('print(json.dumps('+expression+'))').strip().splitlines()[-1])


def position():
    return value('[p.get_actor_location().x,p.get_actor_location().y,p.get_actor_location().z]')


def slate(key):
    py(f'm.review_slate_key({key!r},True); m.review_slate_key({key!r},False)')


def open_map():
    if not value('m.is_map_open()'):
        slate('M')


def close_map():
    if value('m.is_map_open()'):
        slate('Escape')


def controller_state():
    return json.loads(value('m.review_atlas_controller()'))


def controller_tap(key):
    py(f'm.review_slate_key({key!r},True)')
    time.sleep(.12)
    py(f'm.review_slate_key({key!r},False)')
    time.sleep(.18)


def focus_target(key):
    state = controller_state()
    if key not in state['targets']:
        raise AssertionError('Controller target is absent: '+key)
    for _ in range(len(state['targets'])+1):
        if controller_state()['focus'] == key:
            return
        slate('Gamepad_RightTrigger')
        time.sleep(.06)
    raise AssertionError('Controller cannot focus: '+key)


def analog(key, amount):
    if not value(f'm.review_slate_analog({key!r},{amount})'):
        raise AssertionError('Slate axis refused: '+key)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, help='a game without a live session on loopback port N (default: the session atelier qa selects)')
    parser.add_argument('--save-file', type=Path, required=True)
    parser.add_argument('--names-file', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=paths.build_dir('yorimichi')/'atlas-review')
    args = parser.parse_args()
    live.use_port(args.port)
    args.out.mkdir(parents=True, exist_ok=True)
    launch = value('unreal.SystemLibrary.get_command_line()')
    for key, file in [('markersave', args.save_file), ('atlasnamesfile', args.names_file)]:
        path = str(file.resolve())
        if f'-{key}={path}' not in launch and f'-{key}="{path}"' not in launch:
            raise RuntimeError(f'Launch with the explicit isolated -{key} review file')
    checks = {}

    def record(name, ok, evidence):
        checks[name] = dict(ok=bool(ok), evidence=evidence)
        (args.out/'checks.json').write_text(json.dumps(checks, indent=2)+'\n')
        print(('PASS ' if ok else 'FAIL ')+name+': '+json.dumps(evidence), flush=True)
        if not ok:
            raise AssertionError(name)

    def shot(name):
        file = (args.out/(name+'.png')).resolve()
        py(f'unreal.LiveLibrary.screenshot({str(file)!r})')
        deadline = time.monotonic()+5
        while not file.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        record('screenshot_'+name, file.exists() and file.stat().st_size > 10000, file.name)

    try:
        regions = value('list(m.get_atlas_region_keys())')
        record('all_seven_regions', set(regions) == REGIONS, regions)
        air = json.loads(value('m.review_atlas_air_route()'))
        record('zeppelin_four_stops', air['line'] == ['zeppelin_forest', 'zeppelin_city', 'zeppelin_megapark', 'zeppelin_belmonte'], air['line'])
        actual_times = [(leg['from'], leg['to'], leg['seconds']) for leg in air['legs']]
        expected_times = [('zeppelin_forest', 'zeppelin_city', 28.), ('zeppelin_city', 'zeppelin_megapark', 35.5),
                          ('zeppelin_megapark', 'zeppelin_belmonte', 61.2)]
        record('zeppelin_sequential_times', same_leg_times(actual_times, expected_times), actual_times)
        record('zeppelin_stop_positions', len(air['stops']) == 4 and all(math.isfinite(p['x']) and math.isfinite(p['y']) for p in air['stops']), air['stops'])
        keys = value('list(m.get_atlas_zone_keys("world"))')
        record('complete_destination_registry', DESTINATIONS <= set(keys), keys)
        record('salon_classified_haras_valley', value('"belmonte_salon" in list(m.get_atlas_zone_keys("haras_valley"))'),
               value('list(m.get_atlas_zone_keys("haras_valley"))'))
        # Exercise each existing resolver, including special camp, train and
        # Crater Park paths. Region selection never supplies travel coordinates.
        for key in keys:
            if key.startswith('marker_'):
                continue
            record('travel_'+key, value(f'm.teleport_to_zone({key!r})'), dict(key=key, position=position()))
            time.sleep(.25)
            p = position()
            record('finite_location_'+key, all(math.isfinite(v) for v in p), p)
        record('return_spawn', value('m.teleport_to_zone("spawn")'), position())
        time.sleep(1.)
        open_map()
        time.sleep(.3)
        record('opens_on_current_region', value('m.get_atlas_region()') == 'momiji_coast', value('m.get_atlas_region()'))
        for key in regions:
            close_map()
            py(f'm.teleport_to_zone({REGION_STOPS[key]!r})')
            time.sleep(.5)
            open_map()
            time.sleep(.2)
            record('current_region_'+key, value('m.get_atlas_region()') == key, value('m.get_atlas_region()'))
            record('select_'+key, value(f'm.select_atlas_region({key!r})'), key)
            time.sleep(.3)
            shot(key)
        py('m.select_atlas_region("haras_valley"); m.select_stable("alder_stables")')
        record('editable_stable_label', value('m.rename_stable("alder_stables","Cedar Run")'), value('m.get_stable_name("alder_stables")'))
        time.sleep(.3)
        shot('haras_valley_custom_name')
        saved = json.loads(args.names_file.read_text(encoding='utf-8-sig'))
        record('name_is_saved_as_data', saved['names'].get('alder_stables') == 'Cedar Run', saved)
        close_map()
        py('print(unreal.YorimichiLive.switch_character("Modori"))')
        time.sleep(.6)
        record('character_switch_keeps_names', value('m.get_stable_name("alder_stables")') == 'Cedar Run', value('p.get_name()'))
        py('print(unreal.YorimichiLive.switch_character("Cairo"))')
        time.sleep(.6)
        record('save_marker', value('m.save_marker("Atlas return")'), value('m.get_marker_name()'))
        marker_keys = [k for k in value('list(m.get_atlas_zone_keys("world"))') if k.startswith('marker_')]
        record('saved_marker_reachable', bool(marker_keys) and value(f'm.teleport_to_zone({marker_keys[-1]!r})'), marker_keys)
        open_map()
        time.sleep(.3)
        before = position()
        typed = value('m.review_marker_name_input("mbvhk wasd")')
        time.sleep(.3)
        record('text_entry_isolates_gameplay', typed == 'mbvhk wasd' and value('m.is_map_open()') and math.dist(before, position()) < 1., typed)
        record('enter_saves_typed_marker', value('m.review_commit_marker_name()'), value('m.get_marker_name()'))
        py('m.select_atlas_region("haras_valley"); m.review_marker_name_input("Unsaved text")')
        slate('Gamepad_FaceButton_Right')
        record('controller_text_back_to_world', value('m.is_map_open()') and value('m.get_atlas_region()') == 'world', value('m.get_atlas_region()'))
        slate('Gamepad_FaceButton_Right')
        record('controller_text_back_closes_world', not value('m.is_map_open()'), value('m.is_map_open()'))
        # Use the real gamepad route throughout: View, triggers, sticks and face
        # buttons. Cycling must retain distinct keys even when pins coincide.
        close_map()
        py('m.teleport_to_zone("spawn")')
        time.sleep(.5)
        py('unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(),"japan.ControllerHUD 1")')
        controller_tap('Gamepad_Special_Left')
        record('controller_opens_current_region', value('m.is_map_open()') and value('m.get_atlas_region()') == 'momiji_coast', controller_state())
        slate('Gamepad_FaceButton_Right')
        record('controller_back_to_world', value('m.get_atlas_region()') == 'world' and value('m.is_map_open()'), value('m.get_atlas_region()'))
        shot('world')
        for region in regions:
            focus_target(region)
            slate('Gamepad_FaceButton_Bottom')
            time.sleep(.12)
            record('controller_opens_'+region, value('m.get_atlas_region()') == region and value('m.is_map_open()'), controller_state())
            expected = set(controller_state()['targets'])
            seen = set()
            for _ in range(len(expected)):
                slate('Gamepad_RightTrigger')
                time.sleep(.08)
                seen.add(controller_state()['focus'])
            record('controller_reaches_every_pin_'+region, expected == seen, dict(expected=sorted(expected), reached=sorted(seen)))
            required = set(value(f'list(m.get_atlas_zone_keys({region!r}))'))
            record('controller_preserves_destinations_'+region, required <= seen, sorted(required))
            previous = controller_state()['focus']
            slate('Gamepad_RightTrigger')
            slate('Gamepad_LeftTrigger')
            record('controller_reverse_cycle_'+region, controller_state()['focus'] == previous, previous)
            slate('Gamepad_FaceButton_Right')
            time.sleep(.08)
        focus_target('haras_valley')
        slate('Gamepad_FaceButton_Bottom')
        time.sleep(.15)
        focus_target('belmonte')
        slate('Gamepad_DPad_Up')
        time.sleep(.12)
        record('controller_directional_selection', controller_state()['focus'] not in ('', 'belmonte') and value('m.is_map_open()'), controller_state())
        focus_target('belmonte')
        before = controller_state()
        slate('Gamepad_RightShoulder')
        slate('Gamepad_RightShoulder')
        time.sleep(.15)
        record('controller_shoulder_zoom', controller_state()['zoom'] > before['zoom'], controller_state())
        zoomed = controller_state()['zoom']
        slate('Gamepad_LeftShoulder')
        record('controller_shoulder_zoom_out', controller_state()['zoom'] < zoomed, controller_state())
        slate('Gamepad_RightShoulder')
        time.sleep(.12)
        before = controller_state()
        analog('Gamepad_RightX', .65)
        analog('Gamepad_RightY', .4)
        time.sleep(.35)
        during = controller_state()
        analog('Gamepad_RightX', 0.)
        analog('Gamepad_RightY', 0.)
        record('controller_pan_keeps_reticle', abs(during['pan_x']-before['pan_x']) > 5 and abs(during['pan_y']-before['pan_y']) > 5 and math.dist([during['screen_x'],during['screen_y']],[before['screen_x'],before['screen_y']]) < 4, dict(before=before, during=during))
        slate('Gamepad_RightThumbstick')
        time.sleep(.12)
        record('controller_one_button_fit', controller_state()['zoom'] == 1., controller_state())
        focus_target('belmonte')
        before = controller_state()
        player_before = position()
        analog('Gamepad_LeftX', .65)
        time.sleep(.25)
        during = controller_state()
        analog('Gamepad_LeftX', 0.)
        record('controller_left_stick_moves_cursor_only', abs(during['cursor_x']-before['cursor_x']) > .01 and math.dist(player_before, position()) < 1., dict(before=before, during=during))
        for style, select, zoom, cycle, return_key in [(1,'A','LB / RB','LT / RT','X'),(2,'Cross','L1 / R1','L2 / R2','Square'),(3,'B','L / R','ZL / ZR','Y'),(4,'Bottom button','Shoulders','Triggers','Left button')]:
            py(f'unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(),"japan.ControllerHUD {style}")')
            hints = controller_state()
            record('controller_button_labels_'+str(style), all(word in hints['hint'] for word in [select+': select', zoom+': zoom', cycle+': cycle places']) and hints['return_hint'] == 'Return · '+return_key, hints['hint'])
        py('unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(),"japan.ControllerHUD 1")')
        shot('controller_haras_valley')
        slate('Gamepad_LeftThumbstick')
        time.sleep(.15)
        record('controller_locates_current_region', value('m.get_atlas_region()') == 'momiji_coast' and controller_state()['zoom'] == 1., controller_state())
        focus_target('ronin_camp')
        player_before = position()
        slate('Gamepad_FaceButton_Bottom')
        time.sleep(.5)
        record('controller_face_button_travels', not value('m.is_map_open()') and math.dist(player_before,position()) > 1000., position())
        # Test saved-place controls on the clear spawn road. The combat-camp
        # arrival can be obstructed, which correctly refuses marker return.
        record('controller_marker_clear_start', value('m.teleport_to_zone("spawn")'), position())
        time.sleep(.5)
        controller_tap('Gamepad_Special_Left')
        marker_count = len(value('list(m.get_marker_keys())'))
        slate('Gamepad_FaceButton_Top')
        record('controller_saves_place', len(value('list(m.get_marker_keys())')) == marker_count+1, value('m.get_marker_name()'))
        saved_position = position()
        record('controller_marker_travel_away', value('m.teleport_to_zone("belmonte")'), position())
        time.sleep(.25)
        record('controller_marker_moved_away', math.dist(saved_position, position()) > 1000., position())
        slate('Gamepad_FaceButton_Left')
        record('controller_returns_to_place', not value('m.is_map_open()') and math.dist(saved_position, position()) < 25., position())
        controller_tap('Gamepad_Special_Left')
        slate('Gamepad_FaceButton_Right')
        slate('Gamepad_FaceButton_Right')
        record('controller_back_closes_world', not value('m.is_map_open()'), value('m.is_map_open()'))
        record('all_checks_passed', True, len(checks))
    finally:
        close_map()
        py('unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(),"japan.ControllerHUD -1")')


if __name__ == '__main__':
    main()
