#!/usr/bin/env python3
"""In-game checks for getting on and off the board with the Ride backend (Skate plugin, RIDE.md "Transitions").

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_transitions [--only name,name]
On the skate pier's long flat, with skate.Backend Ride and the player's own buttons (the top face button gets on and
off, D-pad Right brings the board to the hand or puts it away): mounts from standing, walking, running and sprinting
(each its own BR_*_INTO_MOUNT clip), a mount from the board carry, dismounts to a stand, a run and a fast run (the
BR_DISMOUNT_* clips, into the carry), the carry put away after its hold time, the board button with no board and
with a board lying, a bail left on foot (the rider gets up where the body lies), a bail back onto the board, a board
left lying that dissolves, jumps with the board in hand (JBR_* then BR_LAND_*), the board thrown under the feet mid-jump
(a caveman, with and without the board in hand), a step off the board in the air from a grab (BR_DISMOUNT_*_INTO_BR_AIR,
then a landing), and Link as the rider.

Every frame is checked for continuity: the character moves no farther than its speed allows, the hips do not jump,
the velocity changes no faster than a push or a brake could (at a landing, the horizontal velocity), and the board shows
whenever it is somewhere. Writes
build/yorimichi/skateqa/transitions.json.
"""
import argparse
import json
import math
import time
import skate as qa

FLAT = (-28, 38)        # the pier's long flat run, heading east
TOP = 'Gamepad_FaceButton_Top'
HAND = 'Gamepad_DPad_Right'   # the board button (G on the keyboard)
SLACK_MOVE = 6.0        # cm a frame the character may move beyond its speed's travel
SLACK_HIP = 12.0        # cm a frame the hips may move beyond that travel (the pose's own motion)
SLACK_HIP_BAIL = 40.0   # ... while the body tumbles
ACCEL = 4000.0          # cm/s^2: the most a push, a brake or a landing changes the speed
SLACK_SPEED = 60.0      # cm/s a frame on top
BAIL_KEYS = ('Gamepad_LeftThumbstick', 'Gamepad_RightThumbstick')
BAIL_AXES = ('Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis')


def vec(text):
    return tuple(float(x) for x in text.strip().strip('()').split(','))


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
            # A landing stops the fall in a frame: only the horizontal velocity carries on.
            if a.get('mm', '').startswith('3/') and not b.get('mm', '').startswith('3/'):
                va, vb = (va[0], va[1], 0.0), (vb[0], vb[1], 0.0)
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


def state():
    return qa.parse(qa.py('print(live.skate_state())'))


def press_key(key):
    qa.py(f"live.L.input_key('{key}','press',1); live.L.input_key('{key}','release',0)")


def on_foot(heading=0, board=False):
    """Stand on the flat, off the board (with the board in hand or not), the camera looking along the run."""
    if state()['mode'] != '0':
        qa.py('live.skate_release(); live.skate()')
        time.sleep(1.5)
    if (state().get('board') == 'hand') != board:
        press_key(HAND)
        time.sleep(.8)
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


def clip_of(rows, foot):
    """The clip played while `foot` (mount, dismount) and the index of its first frame."""
    at = next((i for i, r in enumerate(rows) if r.get('foot') == foot), None)
    return (rows[at].get('clip', '-'), at) if at is not None else ('-', None)


def fading(rows):
    return sum(1 for r in rows if 0 < float(r['shown']) < 1)


def clips(rows):
    """The clips played, in order, each with the foot it played as (air, land, airmount...)."""
    seen = []
    for r in rows:
        clip = (r.get('foot', '-'), r.get('clip', '-'))
        if clip[1] != '-' and (not seen or seen[-1] != clip):
            seen.append(clip)
    return seen


def line(seen):
    return ' > '.join(f'{foot}:{clip}' for foot, clip in seen) or '(no clips)'


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

    def mount(name, gait, carrying=False):
        on_foot(board=carrying)
        if gait:
            qa.py(f"live.drive(1,0,'{gait}')")
            time.sleep(1.8)
        rows = record(tap(TOP, .25), 2.6)
        qa.py('live.drive(0)')
        clip, start = clip_of(rows, 'mount')
        at = first(rows, '1')
        if at is None or start is None:
            report(name, rows, False, f'never got on (clip {clip})')
            return
        want = {'': 'BR_STAND_0_INTO_MOUNT', 'walk': 'BR_WALK_FWD_', 'run': 'BR_RUN_FWD_', 'sprint': 'BR_SPRINT_FWD_'}[gait]
        entry, before, after = flat_speed(rows[max(0, start - 1)]), flat_speed(rows[at - 1]), flat_speed(rows[at])
        worst = continuity(rows)
        shown, note = board_shown(rows)
        # The speed carries on into the clip and out of it onto the board; a held board never fades.
        carried = flat_speed(rows[start]) >= .85 * entry - 20 and after >= .85 * before - 20
        held = not carrying or all(float(r['shown']) == 1.0 for r in rows[start:at])
        in_hand = all(r['board'] == 'hand' for r in rows[start:at])
        report(name, rows, smooth(worst) and shown and carried and held and in_hand and clip.startswith(want) and
               rows[-1]['board'] == 'ride' and float(rows[-1]['shown']) == 1.0,
               f'{clip} ({(at - start)} frames) at {entry:.0f} cm/s, onto the board {before:.0f} -> {after:.0f} cm/s; '
               f'{describe(worst)}; board {note}{", held throughout" if carrying and held else ""}')

    def dismount(name, speed, want, run=True):
        riding(speed)
        rows = record(tap(TOP, .2) + ("live.drive(1,0,'run')\n" if run else ''), 2.6)
        qa.py('live.drive(0)')
        at = first(rows, '0')
        clip, start = clip_of(rows, 'dismount')
        if at is None or start is None:
            report(name, rows, False, f'never got off (clip {clip})')
            return
        before, after = flat_speed(rows[at - 1]), flat_speed(rows[at])
        worst = continuity(rows)
        shown, note = board_shown(rows)
        walking = rows[-1]['mm'].startswith('1/')
        carry = next((i for i, r in enumerate(rows) if r.get('foot') == 'carry'), None)
        held = carry is not None and all(r['board'] == 'hand' and r['vis'] == '1' for r in rows[start:])
        report(name, rows, smooth(worst) and shown and after >= .9 * before - 20 and walking and held and clip == want,
               f'{clip} ({(carry or len(rows)) - start} frames), {before:.0f} -> {after:.0f} cm/s, {flat_speed(rows[-1]):.0f} after 2.6 s, '
               f'momentum {rows[at]["momentum"]}, then {"carrying" if carry is not None else "no carry"}; {describe(worst)}; board {note}')

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
        mount('mount_carry_run', 'run', carrying=True)
    if wanted('dismount'):
        dismount('dismount_stand', 90, 'BR_DISMOUNT_HI_INTO_STAND_0', run=False)
        dismount('dismount_low', 350, 'BR_DISMOUNT_HI_INTO_RUN_FWD')
        dismount('dismount_high', 900, 'BR_DISMOUNT_FAST_HI_INTO_RUN_FWD')
    if wanted('carry'):
        # Held past its hold time, the board dissolves in the hand and the character's own pose blends back.
        qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune BoardHoldTime=1.5')")
        riding(350)
        rows = record(tap(TOP, .2) + "live.drive(1,0,'run')\n", 1.6)
        rows += record('live.drive(0)', 2.0)
        qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune')")
        worst = continuity(rows)
        shown, note = board_shown(rows)
        carried = sum(1 for r in rows if r.get('foot') == 'carry')
        report('carry_put_away', rows, carried > 10 and rows[-1]['board'] == 'away' and rows[-1]['vis'] == '0' and
               rows[-1].get('foot') == 'off' and fading(rows) >= 4 and smooth(worst) and shown,
               f'{carried} carry frames, board {rows[-1]["board"]}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
    if wanted('board_button'):
        # No board: one dissolves into the hand; pressed again, it is put away.
        on_foot()
        rows = record(tap(HAND, .2), 1.4)
        worst = continuity(rows)
        shown, note = board_shown(rows)
        got = rows[-1]['board'] == 'hand' and rows[-1].get('foot') == 'carry' and rows[-1]['vis'] == '1'
        report('board_button_take', rows, got and fading(rows) >= 4 and smooth(worst) and shown,
               f'board {rows[-1]["board"]}, foot {rows[-1].get("foot")}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
        rows = record(tap(HAND, .2), 1.2)
        worst = continuity(rows)
        shown, note = board_shown(rows)
        report('board_button_put_away', rows, rows[-1]['board'] == 'away' and rows[-1].get('foot') == 'off' and fading(rows) >= 4 and smooth(worst) and shown,
               f'board {rows[-1]["board"]}, foot {rows[-1].get("foot")}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
    if wanted('bail_on_foot'):
        bail('bail_on_foot', True)
    if wanted('lying_board'):
        # Out of reach for a short lying time, the board left by the bail dissolves.
        if results.get('bail_on_foot', {}).get('ok'):
            qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune BoardLyingTime=1.5')")
            rows = record("live.drive(1,0,'run')", 1.0)
            rows += record('live.drive(0)', 2.5)
            qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune')")
            faded = fading(rows)
            shown, note = board_shown(rows)
            report('lying_board', rows, rows[-1]['board'] == 'away' and rows[-1]['vis'] == '0' and faded >= 4 and shown,
                   f'board {rows[-1]["board"]}, {faded} fading frames; board {note}')
        else:
            report('lying_board', [], False, 'needs bail_on_foot')
    if wanted('bail_back'):
        bail('bail_back_on_board', False)
    if wanted('recall_lying'):
        # A board lying in the world: the board button dissolves it and a fresh one comes to the hand.
        bail('bail_on_foot_again', True)
        if state().get('board') == 'world':
            rows = record(tap(HAND, .2), 1.6)
            shown, note = board_shown(rows)
            worst = continuity(rows)
            went = any(r['board'] == 'away' or float(r['shown']) < .5 for r in rows)
            report('recall_lying', rows, went and rows[-1]['board'] == 'hand' and rows[-1].get('foot') == 'carry' and shown and smooth(worst),
                   f'board {rows[-1]["board"]}, foot {rows[-1].get("foot")}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
        else:
            report('recall_lying', [], False, 'no board lying after the bail')
    def jump(name, gait, want_air, want_land, seconds=2.6):
        # A jump with the board in hand: the jump clip from the stride, then a landing clip, the board held throughout.
        on_foot(board=True)
        if gait:
            qa.py(f"live.drive(1,0,'{gait}')")
            time.sleep(1.5)
        before = flat_speed(state())
        rows = record("live.press('jump')\n", seconds)
        qa.py("live.press('jump_release'); live.drive(0)")
        seen = clips(rows)
        air = next((c for f, c in seen if f == 'air'), '-')
        land = next((c for f, c in seen if f == 'land'), '-')
        landed = next((i for i, r in enumerate(rows) if r.get('foot') == 'land'), None)
        worst = continuity(rows)
        shown, note = board_shown(rows)
        held = all(r['board'] == 'hand' and r['vis'] == '1' for r in rows)
        after = flat_speed(rows[landed]) if landed is not None else 0.0
        kept = not gait or after >= .8 * before - 20
        report(name, rows, air.startswith(want_air) and land.startswith(want_land) and held and kept and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} cm/s, {after:.0f} at the landing, {flat_speed(rows[-1]):.0f} after {seconds} s; '
               f'{describe(worst)}; board {note}{", in hand throughout" if held else ""}')

    def caveman(name, carrying):
        # Running, a jump, then the skate button in the air: the board goes under the feet and the ride goes on.
        on_foot(board=carrying)
        qa.py("live.drive(1,0,'run')")
        time.sleep(1.5)
        before = flat_speed(state())
        rows = record("live.press('jump')\n" + tap(TOP, .22), 2.6)
        qa.py("live.press('jump_release'); live.drive(0)")
        seen = clips(rows)
        mount = next((c for f, c in seen if f == 'airmount'), '-')
        at = first(rows, '1')
        at = at if at is not None else first(rows, '2')
        worst = continuity(rows)
        shown, note = board_shown(rows)
        on = at is not None and rows[-1]['board'] == 'ride' and rows[-1]['mode'] in ('1', '2')
        after = flat_speed(rows[at]) if at is not None else 0.0
        jumped = not carrying or any(f == 'air' and c.startswith('JBR_RUN_FWD_') for f, c in seen)
        report(name, rows, 'AIR_INTO_MOUNT_BSGRAB' in mount and on and jumped and after >= .8 * before - 20 and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} cm/s running, {after:.0f} onto the board, mode {rows[-1]["mode"]} at the end; '
               f'{describe(worst)}; board {note}')

    def air_dismount(name, grab, want, height=4.5):
        # In the air with a grab held, the skate button: off the board from the grab, the board into the hand, a landing.
        riding(0)
        code = (f"g=live.L.ground_at(live.park.ue({FLAT[0]},{FLAT[1]},3.0)); live.skate_place(g+unreal.Vector(0,0,{height * 100}),0)\n"
                f"live.park.launch(500,0); live.park.look(-12,0); live.skate_input(grab_right={grab})\n" + tap(TOP, .3))
        rows = record(code, 3.0)
        qa.py('live.skate_release()')
        seen = clips(rows)
        off = next((c for f, c in seen if f == 'air'), '-')
        land = next((c for f, c in seen if f == 'land'), '-')
        start = next((i for i, r in enumerate(rows) if r.get('foot') == 'air'), None)
        if start is None:
            report(name, rows, False, f'never got off ({line(seen)}; modes {"".join(sorted(qa.modes(rows)))})')
            return
        worst = continuity(rows[start - 1:])
        shown, note = board_shown(rows)
        held = all(r['board'] == 'hand' and r['vis'] == '1' for r in rows[start:])
        before, after = flat_speed(rows[start - 1]), flat_speed(rows[start])
        report(name, rows, off == want and land.startswith('BR_LAND_') and held and after >= .9 * before - 20 and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} -> {after:.0f} cm/s off the board, {flat_speed(rows[-1]):.0f} after 3 s; '
               f'{describe(worst)}; board {note}{", in hand throughout" if held else ""}')

    if wanted('jump'):
        jump('jump_run', 'run', 'JBR_RUN_FWD_', 'BR_LAND_SML_FWD_')
        jump('jump_stand', '', 'JBR_STAND_0_TO_SML_FWD_0', 'BR_LAND_SML_FWD_0_INTO_STAND', seconds=3.4)
    if wanted('caveman'):
        caveman('caveman_run', False)
        caveman('caveman_carry', True)
    if wanted('air_dismount'):
        air_dismount('air_dismount_grab', True, 'BR_DISMOUNT_FS_INTO_BR_AIR')
        air_dismount('air_dismount_nograb', False, 'BR_DISMOUNT_MUTE_INTO_BR_AIR')
    if wanted('link'):
        switched = qa.py("print(live.L.switch_character('Link'))").strip()
        time.sleep(2.5)
        mount('link_mount_run', 'run')
        dismount('link_dismount_high', 900, 'BR_DISMOUNT_FAST_HI_INTO_RUN_FWD')
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
    qa.py("live.stop('tr'); live.stop('tap'); live.stop('bail'); live.drive(0); live.skate_release(); live.press('jump_release')\n"
          "for k in ['Gamepad_LeftThumbstick','Gamepad_RightThumbstick','Gamepad_FaceButton_Top','Gamepad_DPad_Right']: live.L.input_key(k,'release',0)\n"
          "for k in ['Gamepad_LeftTriggerAxis','Gamepad_RightTriggerAxis']: live.L.input_key(k,'axis',0)\n"
          "unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune')")


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        release_controls()
