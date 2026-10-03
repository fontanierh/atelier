#!/usr/bin/env python3
"""In-game checks for getting on and off the board with the Ride backend (Skate plugin, RIDE.md "Transitions").

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_transitions [--only name,name]
On the skate pier's long flat, with skate.Backend Ride and the player's own buttons (the top face button): mounts from
standing, walking, running and sprinting, dismounts at low and high speed, a bail left on foot (the rider gets up
where the body lies), a bail back onto the board, a board left lying that dissolves, and Link as the rider.

Every frame is checked for continuity: the character moves no farther than its speed allows, the hips do not jump,
the velocity changes no faster than a push or a brake could, and the board shows whenever it is somewhere. Writes
build/yorimichi/skateqa/transitions.json.
"""
import argparse
import json
import math
import time
import skate as qa

FLAT = (-28, 38)        # the pier's long flat run, heading east
TOP = 'Gamepad_FaceButton_Top'
SLACK_MOVE = 6.0        # cm a frame the character may move beyond its speed's travel
SLACK_HIP = 12.0        # cm a frame the hips may move beyond that travel (the pose's own motion)
SLACK_HIP_BAIL = 40.0   # ... while the body tumbles
ACCEL = 4000.0          # cm/s^2: the most a push, a brake or a landing changes the speed
SLACK_SPEED = 60.0      # cm/s a frame on top
BAIL_KEYS = ('Gamepad_LeftThumbstick', 'Gamepad_RightThumbstick')
BAIL_AXES = ('Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis')


def vec(text):
    return tuple(float(x) for x in text.strip('()').split(','))


def length(v):
    return math.sqrt(sum(x * x for x in v))


def record(code, seconds):
    """Run `code` in the game and record every frame's skate state (with the frame time) for `seconds`."""
    qa.py("import json\nlive.TR=[]\nlive.behave('tr', lambda dt: live.TR.append((dt, live.L.skate_state())))\n" + code)
    time.sleep(seconds)
    rows = json.loads(qa.py("import json; live.stop('tr'); print(json.dumps(live.TR))").strip().splitlines()[-1])
    out = []
    for dt, state in rows:
        row = qa.parse(state)
        row['dt'] = dt
        out.append(row)
    return [r for r in out if 'hip' in r and 'pos' in r]


def tap(key, delay):
    """Code that presses `key` after `delay` seconds and lets go two frames later, as a player's tap."""
    return f'''
live.TAP=[0.0,0]
def _tap(dt):
    live.TAP[0]+=dt
    if live.TAP[1]==0 and live.TAP[0]>={delay}: live.L.input_key('{key}','press',1); live.TAP[1]=1
    elif 1<=live.TAP[1]<3: live.TAP[1]+=1
    elif live.TAP[1]==3: live.L.input_key('{key}','release',0); live.TAP[1]=4; live.stop('tap')
live.behave('tap', _tap)
'''


def continuity(rows, tumbling=lambda row: False):
    """The worst frame-to-frame jumps beyond what the speed explains: the character, its hips and its velocity."""
    worst = {'move_cm': 0.0, 'hip_cm': 0.0, 'speed_cm_s': 0.0}
    for a, b in zip(rows, rows[1:]):
        dt = b['dt']
        va, vb = vec(a['vel']), vec(b['vel'])
        travel = max(length(va), length(vb)) * dt
        bail = tumbling(a) or tumbling(b)
        if not bail:
            worst['move_cm'] = max(worst['move_cm'], math.dist(vec(a['pos']), vec(b['pos'])) - travel)
            worst['speed_cm_s'] = max(worst['speed_cm_s'], math.dist(va, vb) - ACCEL * dt)
        hip = math.dist(vec(a['hip']), vec(b['hip'])) - travel
        worst['hip_cm'] = max(worst['hip_cm'], hip - (SLACK_HIP_BAIL - SLACK_HIP if bail else 0))
    return worst


def smooth(worst):
    return worst['move_cm'] <= SLACK_MOVE and worst['hip_cm'] <= SLACK_HIP and worst['speed_cm_s'] <= SLACK_SPEED


def board_shown(rows):
    """The board shows whenever it is somewhere, and fades rather than pops (no frame jumps more than half way)."""
    hidden = sum(1 for r in rows if r['board'] in ('ride', 'hand', 'world') and float(r['shown']) > 0 and r['vis'] != '1')
    pops = sum(1 for a, b in zip(rows, rows[1:]) if abs(float(b['shown']) - float(a['shown'])) > .5)
    return hidden == 0 and pops == 0, f'hidden {hidden}, pops {pops}'


def describe(worst):
    return 'jumps ' + ', '.join(f'{k} {v:.1f}' for k, v in worst.items())


def on_foot(heading=0):
    """Stand on the flat, off the board, the camera looking along the run."""
    if qa.parse(qa.py('print(live.skate_state())'))['mode'] != '0':
        qa.py('live.skate_release(); live.skate()')
        time.sleep(1.5)
    qa.py(f'live.drive(0); live.teleport(live.L.ground_at(live.park.ue({FLAT[0]},{FLAT[1]},3.0)), {-heading}); live.park.look(-12,{heading})')
    time.sleep(1.5)


def riding(speed, heading=0):
    qa.py(f'live.skate_release(); live.park.place({FLAT[0]},{FLAT[1]},{heading}); live.park.look(-12,{heading}); live.park.launch({speed},{heading})')
    time.sleep(.6)


def first(rows, mode):
    return next((i for i, r in enumerate(rows) if r['mode'] == mode), None)


def flat_speed(row):
    v = vec(row['vel'])
    return math.hypot(v[0], v[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--only', default='', help='comma-separated check names (prefixes) to run')
    args = parser.parse_args()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    only = [o for o in args.only.split(',') if o]
    wanted = lambda name: not only or any(name.startswith(o) for o in only)
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.Backend Ride')")
    qa.py('live.L.skate_goofy(False)')
    results, frames = {}, []

    def report(name, rows, passed, note):
        frames.extend(r['dt'] for r in rows)
        results[name] = {'ok': bool(passed), 'note': note, 'frames': len(rows)}
        print(('PASS' if passed else 'FAIL') + ' ' + name + ': ' + note, flush=True)

    qa.settle(minimum=50, seconds=2, limit=60)

    def mount(name, gait):
        on_foot()
        if gait:
            qa.py(f"live.drive(1,0,'{gait}')")
            time.sleep(1.8)
        rows = record(tap(TOP, .25), 1.6)
        qa.py('live.drive(0)')
        at = first(rows, '1')
        if at is None:
            report(name, rows, False, 'never got on')
            return
        before, after = flat_speed(rows[at - 1]), flat_speed(rows[at])
        worst = continuity(rows)
        shown, note = board_shown(rows)
        carried = after >= .85 * before - 20
        report(name, rows, smooth(worst) and shown and carried and rows[-1]['board'] == 'ride' and float(rows[-1]['shown']) == 1.0,
               f'{before:.0f} -> {after:.0f} cm/s; {describe(worst)}; board {note}')

    def dismount(name, speed):
        riding(speed)
        rows = record(tap(TOP, .2) + "live.drive(1,0,'run')\n", 2.2)
        qa.py('live.drive(0)')
        at = first(rows, '0')
        if at is None:
            report(name, rows, False, 'never got off')
            return
        before, after = flat_speed(rows[at - 1]), flat_speed(rows[at])
        worst = continuity(rows)
        shown, note = board_shown(rows)
        walking = rows[-1]['mm'].startswith('1/')
        report(name, rows, smooth(worst) and shown and after >= .9 * before - 20 and walking,
               f'{before:.0f} -> {after:.0f} cm/s, {flat_speed(rows[-1]):.0f} after 2 s, momentum {rows[at]["momentum"]}; {describe(worst)}; board {note}')

    def bail(name, leave_on_foot):
        riding(600)
        start = vec(qa.parse(qa.py('print(live.skate_state())'))['pos'])
        press = '\n'.join([f"live.L.input_key('{k}','press',1)" for k in BAIL_KEYS] + [f"live.L.input_key('{k}','axis',1)" for k in BAIL_AXES])
        release = '\n'.join([f"live.L.input_key('{k}','release',0)" for k in BAIL_KEYS] + [f"live.L.input_key('{k}','axis',0)" for k in BAIL_AXES])
        code = f'''
live.skate_input(); live.L.skate_release()
{press}
live.BAIL=[0.0]
def _bail(dt):
    live.BAIL[0]+=dt
    if live.BAIL[0]>.5:
{chr(10).join('        ' + line for line in release.splitlines())}
        live.stop('bail')
live.behave('bail', _bail)
''' + (tap(TOP, 1.0) if leave_on_foot else '')
        rows = record(code, 9)
        if '4' not in qa.modes(rows):
            report(name, rows, False, 'no bail')
            return
        last_bail = max(i for i, r in enumerate(rows) if r['mode'] == '4')
        end = vec(rows[-1]['pos'])
        body = vec(rows[last_bail]['hip'])
        worst = continuity(rows, tumbling=lambda r: r['mode'] == '4')
        shown, note = board_shown(rows)
        away = math.dist(end[:2], start[:2])
        near = math.dist(end[:2], body[:2])
        if leave_on_foot:
            passed = rows[-1]['mode'] == '0' and away > 150 and near < 150 and rows[-1]['board'] == 'world' and rows[-1]['vis'] == '1'
        else:
            passed = rows[-1]['mode'] == '1' and away > 150
        report(name, rows, passed and smooth(worst) and shown,
               f'ended mode {rows[-1]["mode"]} {away:.0f} cm from the bail start, {near:.0f} cm from where the body lay; '
               f'board {rows[-1]["board"]}; {describe(worst)}; board {note}')

    if wanted('mount'):
        for gait in ('', 'walk', 'run', 'sprint'):
            mount('mount_' + (gait or 'stand'), gait)
    if wanted('dismount'):
        dismount('dismount_low', 350)
        dismount('dismount_high', 900)
    if wanted('bail_on_foot'):
        bail('bail_on_foot', True)
    if wanted('lying_board'):
        # Out of reach for a short lying time, the board left by the bail dissolves.
        if results.get('bail_on_foot', {}).get('ok'):
            qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune BoardLyingTime=1.5')")
            rows = record("live.drive(1,0,'run')", 1.0)
            rows += record('live.drive(0)', 2.5)
            qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune')")
            fading = sum(1 for r in rows if 0 < float(r['shown']) < 1)
            shown, note = board_shown(rows)
            report('lying_board', rows, rows[-1]['board'] == 'away' and rows[-1]['vis'] == '0' and fading >= 4 and shown,
                   f'board {rows[-1]["board"]}, {fading} fading frames; board {note}')
        else:
            report('lying_board', [], False, 'needs bail_on_foot')
    if wanted('bail_back'):
        bail('bail_back_on_board', False)
    if wanted('link'):
        switched = qa.py("print(live.L.switch_character('Link'))").strip()
        time.sleep(2.5)
        mount('link_mount_run', 'run')
        dismount('link_dismount_high', 900)
        qa.py("live.L.switch_character('Cairo')")
        time.sleep(2.5)
        results['link_mount_run']['note'] += f' ({switched})'

    if frames:
        ms = sorted(dt * 1000 for dt in frames)
        p99 = ms[min(len(ms) - 1, round((len(ms) - 1) * .99))]
        report('pacing', [], p99 < 17, f'{len(ms)} frames, p50 {ms[len(ms) // 2]:.1f} ms, p99 {p99:.1f} ms, worst {ms[-1]:.1f} ms')
    qa.py('live.drive(0); live.skate_release()')
    out = qa.yori.OUT / 'skateqa' / 'transitions.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + '\n')
    print(f'{sum(r["ok"] for r in results.values())}/{len(results)} passed -> {out}')
    return 0 if all(r['ok'] for r in results.values()) else 1


def release_controls():
    qa.py("live.stop('tr'); live.stop('tap'); live.stop('bail'); live.drive(0); live.skate_release()\n"
          "for k in ['Gamepad_LeftThumbstick','Gamepad_RightThumbstick','Gamepad_FaceButton_Top']: live.L.input_key(k,'release',0)\n"
          "for k in ['Gamepad_LeftTriggerAxis','Gamepad_RightTriggerAxis']: live.L.input_key(k,'axis',0)\n"
          "unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune')")


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        release_controls()
