"""Check several named markers and safe returns in a guarded CairoBotw game using an isolated -markersave file.

    atelier qa yorimichi session_marker --port 8830 --save-file build/yorimichi/marker-test.json

The first run requires an empty review save. Restart the guarded game with the same -markersave=FILE and run with
--reload to check disk persistence. Never uses the player's normal save. The caller owns the lock and memory guard.
"""
import argparse
import json
import math
import stat
from pathlib import Path
import sys
import time

from atelier import live, paths


def py(code):
    result = live.request('/python', "p=unreal.LiveLibrary.player(); m=p.get_editor_property('map')\n"+code, timeout=10)
    if not result.get('ok'):
        raise RuntimeError(result)
    return result.get('output', '')


def value(expression):
    return json.loads(py('import json; print(json.dumps(' + expression + '))').strip().splitlines()[-1])


def snapshot():
    return json.loads(py('''
import json
t = m.get_marker_transform()
g = t.translation
l = p.get_actor_location()
v = p.get_velocity()
half = p.get_editor_property('capsule_component').get_scaled_capsule_half_height()
print(json.dumps(dict(has=m.has_marker(), marker=[g.x,g.y,g.z,t.rotation.rotator().yaw],
    key=m.get_selected_marker_key(),name=m.get_marker_name(),keys=list(m.get_marker_keys()),
    feet=[l.x,l.y,l.z-half], yaw=p.get_actor_rotation().yaw, speed=v.length(), pawn=p.get_name())))
''').strip().splitlines()[-1])


def key(name):
    py(f"unreal.LiveLibrary.input_key({name!r}, 'press', 1)")
    time.sleep(.15)
    py(f"unreal.LiveLibrary.input_key({name!r}, 'release', 0)")
    time.sleep(.4)


def travel(point, yaw=0):
    assert value(f'unreal.LiveLibrary.teleport_player(unreal.Vector({point[0]},{point[1]},{point[2]}),{yaw})')
    time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--reload', action='store_true')
    parser.add_argument('--save-file', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=paths.build_root()/'yorimichi/session-marker/review')
    args = parser.parse_args()
    live.URL = f'http://127.0.0.1:{args.port}'
    args.out.mkdir(parents=True, exist_ok=True)
    save = args.save_file.resolve()
    launch = value('unreal.SystemLibrary.get_command_line()')
    if '-markersave='+str(save) not in launch and '-markersave="'+str(save)+'"' not in launch:
        raise RuntimeError('QA requires the same explicit isolated -markersave path on the game')
    checks = {}

    def record(name, ok, evidence):
        checks[name] = dict(ok=bool(ok), evidence=evidence)
        print(('PASS ' if ok else 'FAIL ') + name + ': ' + json.dumps(evidence), flush=True)

    def returned(name, marker):
        current = snapshot()
        distance = math.dist(current['feet'][:2], marker[:2])
        yaw = abs((current['yaw']-marker[3]+180) % 360-180)
        record(name, distance < 2 and abs(current['feet'][2]-marker[2]) < 6 and yaw < 1 and current['speed'] < 5, current)

    before = snapshot()
    try:
        if args.reload:
            persisted = json.loads(save.read_text())
            record('restart_loads_all_places_and_selection', set(before['keys']) == {r['id'] for r in persisted['markers']}
                   and before['key'] == persisted['selected'] and len(before['keys']) >= 2, before)
            for row in persisted['markers']:
                assert value(f'm.select_marker({row["id"]!r})')
                current = snapshot()
                expected = [row[k] for k in ('x','y','z','yaw')]
                record('reload_'+row['name'], current['name'] == row['name'] and math.dist(current['marker'][:3], expected[:3]) < .01, current)
                # The deliberately removed QA platform still must refuse; real ground places can return.
                if row['name'] != 'Removed platform':
                    assert value('m.return_to_marker()')
                    time.sleep(.6)
                    returned('reload_return_'+row['name'], expected)
            first = persisted['markers'][0]['id']
            assert value(f'm.select_marker({first!r})')
            assert value('m.delete_marker()')
            record('delete_commits_without_erasing_other_places', first not in snapshot()['keys'] and
                   {r['id'] for r in json.loads(save.read_text())['markers']} == set(snapshot()['keys']), snapshot())
        else:
            record('isolated_save_initially_empty', not before['has'] and not before['keys'], before)
            if before['keys']:
                raise RuntimeError('First QA run requires a new empty isolated save')
            prior = snapshot()
            refused = not value('m.return_to_marker()')
            record('unset_return_refused', refused and math.dist(snapshot()['feet'], prior['feet']) < .1, snapshot())
            key('F5')
            first = snapshot()
            record('keyboard_saves_ground_and_heading', first['has'] and math.dist(first['feet'], first['marker'][:3]) < 6, first)
            anchor = first['marker']
            travel([anchor[0]+1000, anchor[1], anchor[2]], 87)
            assert value('unreal.YorimichiLive.launch(unreal.Vector(350,0,200))')
            key('F9')
            returned('keyboard_return_stops_and_faces_marker', anchor)

            travel([anchor[0]+1000, anchor[1], anchor[2]], 87)
            assert value('m.save_marker("Street line")')
            second = snapshot()
            record('multiple_named_places', len(second['keys']) == 2 and first['key'] in second['keys'] and second['name'] == 'Street line', second)
            replacement = second['marker']
            assert value('m.rename_marker("Street return")')
            duplicate = not value('m.save_marker("street return")')
            record('rename_and_duplicate_name_refusal', duplicate and snapshot()['name'] == 'Street return' and len(snapshot()['keys']) == 2, snapshot())
            travel(anchor[:3])
            assert value(f'm.teleport_to_zone({second["key"]!r})')
            time.sleep(.6)
            returned('map_and_phone_zone_returns_to_named_place', replacement)

            assert value(f'unreal.YorimichiLive.skate_place(unreal.Vector({anchor[0]},{anchor[1]},{anchor[2]}),0)')
            time.sleep(.8)
            mounted = value('unreal.YorimichiLive.skate_state()')
            key('F9')
            stowed = value('unreal.YorimichiLive.skate_state()')
            record('return_stows_ridden_board', 'mode=1' in mounted and 'mode=0' in stowed, dict(before=mounted, after=stowed))
            returned('board_return_lands_on_marker', replacement)

            py('p.set_actor_location(p.get_actor_location()+unreal.Vector(0,0,600),False,False)')
            time.sleep(.1)
            refused = not value('m.set_marker()')
            record('airborne_save_preserves_places', refused and snapshot()['marker'] == replacement and len(snapshot()['keys']) == 2, snapshot())
            travel(anchor[:3])

            assert value(f'unreal.YorimichiLive.test_wall(unreal.Vector({replacement[0]},{replacement[1]},{replacement[2]+300}),0,unreal.Vector(800,800,20))')
            assert value('m.return_to_marker()')
            time.sleep(.6)
            returned('return_stays_below_roof', replacement)
            travel(anchor[:3])
            py('unreal.YorimichiLive.clear_tests()')

            assert value(f'unreal.YorimichiLive.test_wall(unreal.Vector({replacement[0]},{replacement[1]},{replacement[2]}),0,unreal.Vector(100,100,220))')
            prior = snapshot()
            refused = not value('m.return_to_marker()')
            after = snapshot()
            record('blocked_return_preserves_player_and_marker', refused and math.dist(after['feet'], prior['feet']) < .1 and after['marker'] == replacement, after)
            py('unreal.YorimichiLive.clear_tests()')

            platform = [anchor[0]+2000, anchor[1], anchor[2]+400]
            assert value(f'unreal.YorimichiLive.test_wall(unreal.Vector({platform[0]},{platform[1]},{platform[2]}),0,unreal.Vector(400,400,30))')
            travel([platform[0], platform[1], platform[2]+30])
            assert value('m.save_marker("Removed platform")')
            high = snapshot()
            record('marker_on_raised_platform', high['has'] and abs(high['marker'][2]-platform[2]-30) < 2, high)
            travel(anchor[:3])
            py('unreal.YorimichiLive.clear_tests()')
            prior = snapshot()
            refused = not value('m.return_to_marker()')
            after = snapshot()
            record('missing_floor_refuses_instead_of_falling', refused and math.dist(after['feet'], prior['feet']) < .1 and after['marker'] == high['marker'], after)

            assert value(f'm.select_marker({first["key"]!r})')
            saved = snapshot()
            py('print(unreal.YorimichiLive.switch_character("Link"))')
            time.sleep(2)
            switched = snapshot()
            record('character_switch_keeps_saved_places', switched['pawn'] != saved['pawn'] and switched['marker'] == saved['marker'] and switched['keys'] == saved['keys'], switched)
            travel([anchor[0]+1000, anchor[1], anchor[2]], 133)
            key('F9')
            returned('new_character_keyboard_return', saved['marker'])
            py('print(unreal.YorimichiLive.switch_character("CairoBotw"))')
            time.sleep(2)
            key('M')
            prior = snapshot()
            board = value('unreal.YorimichiLive.skate_state()')
            typed = value('m.review_marker_name_input("mbvhk wasd")')
            time.sleep(1)
            after = snapshot()
            record('name_typing_keeps_map_open_and_player_still', typed == 'mbvhk wasd' and value('m.is_map_open()')
                   and math.dist(after['feet'], prior['feet']) < 2 and after['keys'] == prior['keys']
                   and value('unreal.YorimichiLive.skate_state()') == board and not value('m.is_marker_review_on_vehicle()'), dict(typed=typed,player=after))
            assert value('m.review_commit_marker_name()')
            time.sleep(.3)
            record('enter_saves_typed_name', snapshot()['name'] == 'mbvhk wasd' and len(snapshot()['keys']) == len(prior['keys'])+1, snapshot())
            py(f'unreal.LiveLibrary.screenshot({str(args.out / "marker-map.png")!r})')
            time.sleep(1)
            key('M')
            persisted = json.loads(save.read_text())
            record('disk_has_all_places_and_selection', {r['id'] for r in persisted['markers']} == set(snapshot()['keys'])
                   and persisted['selected'] == snapshot()['key'], persisted)
            # A failed disk write must not report a saved place or mutate the existing state/file.
            original = save.read_bytes()
            prior = snapshot()
            mode = stat.S_IMODE(save.parent.stat().st_mode)
            try:
                save.parent.chmod(0o500)
                refused = not value('m.save_marker("Unwritable review")')
                record('failed_write_preserves_save_and_memory', refused and save.read_bytes() == original
                       and snapshot()['keys'] == prior['keys'] and snapshot()['key'] == prior['key'], snapshot())
            finally:
                save.parent.chmod(mode)

    except Exception as exc:
        record('scenario_completed', False, repr(exc))
    finally:
        try:
            py('unreal.YorimichiLive.clear_tests()')
        except Exception as exc:
            record('qa_cleanup', False, repr(exc))
        result = dict(passed=all(c['ok'] for c in checks.values()), checks=checks)
        (args.out/'checks.json').write_text(json.dumps(result, indent=2)+'\n')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
