#!/usr/bin/env python3
"""In-game checks for the Ride skating backend (Skate plugin, Private/Ride, RIDE.md) on the skate pier park.

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_ride [--only name,name]
Mounts with skate.Backend Ride, then checks pushing, steering, braking, the ollie's height, every Flick-It trick, a grab,
a 360, a grind, a manual, a bail and its recovery, a vert air that comes back in, and frame pacing (including mounting
and switching character). Writes build/yorimichi/skateqa/ride.json.
"""
import argparse
import json
import time
import skate as qa

# live.FLICKS name -> the trick name Ride shows.
FLIPS = {
    'ollie': 'Ollie', 'nollie': 'Nollie', 'kickflip': 'Kickflip', 'heelflip': 'Heelflip', 'shove': 'Pop Shove-it',
    'fs_shove': 'FS Pop Shove-it', '360_shove': '360 Shove-it', 'fs_360_shove': 'FS 360 Shove-it',
    'varial_kickflip': 'Varial Kickflip', 'varial_heelflip': 'Varial Heelflip', 'hardflip': 'Hardflip',
    'inward_heelflip': 'Inward Heelflip', '360_flip': '360 Flip', 'laser_flip': 'Laser Flip',
    '360_hardflip': '360 Hardflip', '360_inward_heelflip': '360 Inward Heelflip',
}
FLAT = (-28, 38)       # the pier's long flat run, heading east
RAIL = (-23, 20)       # an ollie at .98 s onto the rail
QUARTER = (33, 25)     # a quarter pipe, launched at 950 cm/s


def position(row):
    return tuple(float(x) for x in row['pos'].strip('()').split(','))


def speed(row):
    return float(row['speed'])


def recorded():
    return [qa.parse(r) for r in json.loads(qa.py("live.stop('rec'); print(json.dumps(live.REC))").strip().splitlines()[-1])]


def record_while(code, seconds):
    """Record every frame's state while `code` runs in the game for `seconds`."""
    qa.py("live.REC=[]; live.behave('rec', lambda dt: live.REC.append(live.skate_state()))\n" + code)
    time.sleep(seconds)
    return recorded()


def mount_ride():
    qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.Backend Ride')")
    qa.py('live.L.skate_goofy(False); live.skate_park(); live.skate_input()')
    for _ in range(40):
        state = qa.py('print(live.skate_state())')
        if 'backend=Ride' in state and 'retail=PhysicsGround' in state:
            return state
        time.sleep(.5)
    raise RuntimeError('Ride did not mount: ' + state.strip())


def frame_sampler():
    qa.py('''
import time
live.FRAMES=[]
live.behave('frames', lambda dt: live.FRAMES.append(time.perf_counter()))
''')


def frame_report():
    stamps = json.loads(qa.py("live.stop('frames'); print(json.dumps(live.FRAMES))").strip().splitlines()[-1])
    intervals = sorted((b - a) * 1000 for a, b in zip(stamps, stamps[1:]))
    if not intervals:
        return {'frames': 0}
    pick = lambda p: intervals[min(len(intervals) - 1, round((len(intervals) - 1) * p))]
    return {'frames': len(intervals), 'fps': 1000 * len(intervals) / sum(intervals), 'p50_ms': pick(.5),
            'p95_ms': pick(.95), 'p99_ms': pick(.99), 'worst_ms': intervals[-1],
            'over_33ms': sum(t > 33.4 for t in intervals), 'over_50ms': sum(t > 50 for t in intervals)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--only', default='', help='comma-separated check names (prefixes) to run')
    args = parser.parse_args()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    only = [o for o in args.only.split(',') if o]
    wanted = lambda name: not only or any(name.startswith(o) for o in only)
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    results = {}

    def record(name, rows, passed, note):
        results[name] = {'ok': bool(passed), 'note': note, 'frames': len(rows)}
        print(('PASS' if passed else 'FAIL') + ' ' + name + ': ' + note, flush=True)

    mounted = mount_ride()
    record('mount', [], True, mounted.strip().split(' | ')[0])
    qa.settle(minimum=50, seconds=2, limit=60)

    if wanted('push'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(0,{{'push':True}}),(3.5,{{}})],duration=4", 4)
        first = next((float(r['speed']) for r in rows if float(r['speed']) > 150), 0)
        top = max(map(speed, rows))
        record('push_cruise', rows, top > 750 and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               f'top speed {top:.0f} cm/s after 3.5 s of pushing')
    if wanted('steer'):
        for direction in (1, -1):
            rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,500,[(.2,{{'left':({direction * .8},0)}}),(1.4,{{}})],duration=1.6", 1.6)
            dy = position(rows[-1])[1] - position(rows[0])[1]
            turned = (float(rows[-1]['yaw']) - float(rows[0]['yaw']) + 180) % 360 - 180
            record(f'steer_{"right" if direction > 0 else "left"}', rows, dy * direction > 40 and turned * direction > 30 and rows[-1]['mode'] == '1',
                   f'sideways {dy:.0f} cm, turned {turned:.0f} degrees')
    if wanted('brake'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,600,[(.3,{{'brake':True}}),(2.6,{{}})],duration=2.8", 2.8)
        record('brake', rows, speed(rows[-1]) < 60 and not qa.count(rows, 'bails'), f'{speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s')
    if wanted('powerslide'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,700,[(.3,{{'slide':True,'left':(.6,0)}}),(1.3,{{}})],duration=2", 2)
        record('powerslide', rows, qa.ever(rows, 'slide', '1') and speed(rows[-1]) < 600 and not qa.count(rows, 'bails'),
               f'{speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s')
    if wanted('ollie'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,400,[(.4,('flick','ollie'))],duration=2.2", 2.2)
        base = position(rows[0])[2]
        height = max(position(r)[2] for r in rows) - base
        air = sum(1 for r in rows if r['mode'] == '2')
        # The reference rises 0.98 m after a 10-tick load (the flick's .16 s), 1.31 m after a long one.
        record('ollie_height', rows, 75 < height < 125 and 'Ollie' in qa.combos(rows) and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               f'{height:.0f} cm high, {air} air frames; {qa.combos(rows)}')
    for key, name in FLIPS.items():
        if not wanted('flip') and not wanted('flip_' + key):
            continue
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,450,[(.4,('flick','{key}'))],duration=2.3", 2.3)
        combos = qa.combos(rows)
        landed = rows[-1]['mode'] == '1' and not qa.count(rows, 'bails')
        # The line reads "Kickflip" (or "Fakie Kickflip" and so on); "360 Flip" must not pass for "Laser Flip".
        tricks = [t.strip() for c in combos.split(' / ') for t in c.split('+')]
        record(f'flip_{key}', rows, landed and any(t == name or t.endswith(' ' + name) for t in tricks), f'{combos or "(none)"}; landed={landed}')
    if wanted('grab'):
        # Hold the right trigger for the first half second of the air (a grab held into the landing bails).
        rows = record_while(f'''
live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)
live.AIR=[0.0]
def grab(dt):
    s=live.skate_state(); air='mode=2 ' in s
    live.AIR[0]=live.AIR[0]+dt if air else 0.0
    live.skate_input(grab_right=air and .08<live.AIR[0]<.6)
live.behave('grab', grab)
''', 5)
        qa.py("live.stop('grab'); live.skate_input()")
        combos = qa.combos(rows)
        record('grab_indy', rows, 'Indy' in combos and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'), combos or '(none)')
    if wanted('spin'):
        for direction in (-1, 1):
            events = [(.4, {'right': (0, -1), 'left': (direction, 0)}), (.62, {'right': (0, 1), 'left': (direction, 0)}),
                      (.66, {'left': (direction, 0)}), (1.6, {})]
            rows = qa.run_scenario(f'{FLAT[0]},{FLAT[1]},0,500,{events!r},duration=2.6', 2.6)
            angle = 0
            for prev, row in zip(rows, rows[1:]):
                if row['mode'] == '2':
                    angle += (float(row['yaw']) - float(prev['yaw']) + 180) % 360 - 180
            record(f'flat_spin_{direction}', rows, abs(angle) > 200 and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
                   f'air rotation {angle:.0f} degrees; {qa.combos(rows)}')
        # A 360 needs a bigger air: off the quarter, spinning until about 320 degrees (the release carries the rest).
        rows = record_while(f'''
live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)
live.SPIN=[0.0, None]
def spin(dt):
    s=live.skate_state(); yaw=float(s.split('yaw=')[1].split()[0])
    if 'mode=2 ' in s and live.SPIN[1] is not None: live.SPIN[0]+=(yaw-live.SPIN[1]+180)%360-180
    live.SPIN[1]=yaw
    live.skate_input(left=(1,0) if 'mode=2 ' in s and abs(live.SPIN[0])<320 else (0,0))
live.behave('spin', spin)
''', 5)
        qa.py("live.stop('spin'); live.skate_input()")
        record('quarter_360', rows, '360' in qa.combos(rows) or '540' in qa.combos(rows), qa.combos(rows) or '(none)')
    if wanted('grind'):
        rows = qa.run_scenario(f"{RAIL[0]},{RAIL[1]},0,520,[(.98,('flick','ollie'))],duration=3.5", 3.5)
        record('grind', rows, '3' in qa.modes(rows) and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               'states ' + ','.join(sorted(qa.modes(rows))) + '; ' + qa.combos(rows))
    if wanted('manual'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,-.5)}}),(1.8,{{}})],duration=2.3", 2.3)
        record('manual', rows, qa.ever(rows, 'manual', '1') and rows[-1]['manual'] == '0' and 'Manual' in qa.combos(rows)
               and not qa.count(rows, 'bails'), qa.combos(rows))
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,.5)}}),(1.8,{{}})],duration=2.3", 2.3)
        record('nose_manual', rows, 'Nose Manual' in qa.combos(rows) and not qa.count(rows, 'bails'), qa.combos(rows))
    if wanted('vert'):
        rows = qa.run_scenario(f"{QUARTER[0]},{QUARTER[1]},0,950,[],duration=5", 5)
        record('vert_air_back_in', rows, '2' in qa.modes(rows) and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               'states ' + ','.join(sorted(qa.modes(rows))))
        rows = qa.run_scenario("29,-10,0,850,[],duration=5", 5)
        record('bowl_carve', rows, rows[-1]['mode'] == '1' and not qa.count(rows, 'bails') and max(map(speed, rows)) > 300,
               'states ' + ','.join(sorted(qa.modes(rows))) + f'; speed {speed(rows[-1]):.0f}')
    if wanted('bail'):
        qa.py(f"live.park.place({FLAT[0] + 18},{FLAT[1]},0); live.park.launch(600); live.skate_release()")
        frame_sampler()
        rows = record_while("live.skate_input(); live.L.skate_release()\n"
                            "live.L.input_key('Gamepad_LeftThumbstick','press',1); live.L.input_key('Gamepad_RightThumbstick','press',1)\n"
                            "live.L.input_key('Gamepad_LeftTriggerAxis','axis',1); live.L.input_key('Gamepad_RightTriggerAxis','axis',1)", .5)
        qa.py("live.REC2=list(live.REC); live.behave('rec', lambda dt: live.REC2.append(live.skate_state()))\n"
              "live.L.input_key('Gamepad_LeftThumbstick','release',0); live.L.input_key('Gamepad_RightThumbstick','release',0)\n"
              "live.L.input_key('Gamepad_LeftTriggerAxis','axis',0); live.L.input_key('Gamepad_RightTriggerAxis','axis',0)")
        time.sleep(8)
        rows = [qa.parse(r) for r in json.loads(qa.py("live.stop('rec'); print(json.dumps(live.REC2))").strip().splitlines()[-1])]
        down = sum(1 for r in rows if r['mode'] == '4') / 60
        frames = frame_report()
        # The fall (ragdoll, loose board, the surfaces around made physical) must not hitch.
        record('bail_recovery', rows, '4' in qa.modes(rows) and '0' not in qa.modes(rows) and rows[-1]['mode'] == '1'
               and 1.5 < down < 6 and frames.get('worst_ms', 999) < 50,
               f'states {",".join(sorted(qa.modes(rows)))}; down about {down:.1f} s; worst frame {frames.get("worst_ms", 0):.1f} ms')
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,500,[(.1,{{'push':True}}),(.3,{{}})],duration=1", 1)
        record('ride_after_bail', rows, rows[-1]['mode'] == '1' and speed(rows[-1]) > 300, f'speed {speed(rows[-1]):.0f}')
    if wanted('pacing'):
        # Ride through the park with tricks, then mount and switch character, sampling every frame.
        frame_sampler()
        qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(0,{{'push':True}}),(2,{{}}),(2.3,('flick','kickflip')),(3.6,('flick','360_flip'))],duration=5", 5)
        qa.run_scenario(f"{QUARTER[0]},{QUARTER[1]},0,950,[],duration=4", 4)
        riding = frame_report()
        cost = qa.py('print(live.skate_state())').split('cost=')[-1].split()[0]
        frame_sampler()
        qa.py("live.skate_release(); live.skate()")
        time.sleep(1)
        qa.py("live.skate_park(); live.skate_input()")
        time.sleep(1.5)
        mounting = frame_report()
        frame_sampler()
        switched = qa.py("print(live.L.switch_character('Link'))").strip()
        time.sleep(2.5)
        qa.py("live.skate_park(); live.skate_input()")
        time.sleep(1.5)
        qa.py("live.L.switch_character('Cairo')")
        time.sleep(2.5)
        switching = frame_report()
        mount_ride()
        record('pacing_riding', [], riding['fps'] >= 58 and riding['p99_ms'] < 33.4 and not riding['over_50ms'], json.dumps(riding) + f' sim cost {cost} ms')
        record('pacing_mount', [], mounting['worst_ms'] < 100, json.dumps(mounting))
        record('pacing_switch', [], switching['worst_ms'] < 250, f'{switched}: ' + json.dumps(switching))
    qa.py('live.skate_input(); live.skate_park(); live.skate_release()')
    out = qa.yori.OUT / 'skateqa' / 'ride.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + '\n')
    print(f'{sum(r["ok"] for r in results.values())}/{len(results)} passed -> {out}')
    return 0 if all(r['ok'] for r in results.values()) else 1


def release_controls():
    qa.py("live.stop('skate_script'); live.stop('rec'); live.stop('grab'); live.stop('spin'); live.stop('frames'); live.skate_release()\n"
          "for k in ['Gamepad_LeftThumbstick','Gamepad_RightThumbstick']: live.L.input_key(k,'release',0)\n"
          "for k in ['Gamepad_LeftTriggerAxis','Gamepad_RightTriggerAxis']: live.L.input_key(k,'axis',0)")


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        release_controls()
