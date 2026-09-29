#!/usr/bin/env python3
"""Skateboarding regression check against the running game (docs/SKATE.md).

    atelier play yorimichi       # in another terminal (or already running)
    atelier qa yorimichi skate [name] [--only case,case]

Every case drives the board through the live bridge with the same inputs a player makes: scripted skate. controls
(Flick-It gestures on the right stick, the left stick, buttons) or simulated key and mouse events through the player
controller. The game's state is recorded every frame and checked. Writes build/yorimichi/skateqa/<name>.json and exits 1 on a
failure.
"""
import argparse, json, sys, time
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world')); import yori  # noqa: E402
from atelier import live as bridge  # noqa: E402

GESTURES = {'ollie': 'Ollie', 'nollie': 'Nollie', 'kickflip': 'Kickflip', 'heelflip': 'Heelflip', 'shove': 'Pop Shove-it',
            'fs_shove': 'Frontside Pop Shove-it', '360_shove': '360 Shove-it', 'fs_360_shove': 'Frontside 360 Shove-it',
            'varial_kickflip': 'Varial Kickflip', 'varial_heelflip': 'Varial Heelflip', 'hardflip': 'Hardflip',
            'inward_heelflip': 'Inward Heelflip', '360_flip': '360 Flip', 'laser_flip': 'Laser Flip'}


def py(code):
    out = bridge.request('/python', code)
    if not out.get('ok'): raise RuntimeError(out.get('result', '') + out.get('output', ''))
    return out.get('output', '')


def parse(state):
    head, _, rest = state.partition(' | ')
    f = {}
    for kv in head.split(' '):
        if '=' in kv and not kv.startswith('flick'): k, v = kv.split('=', 1); f[k] = v
    parts = state.split(' | ')
    f['combo'] = parts[1][6:] if len(parts) > 1 else ''
    tail = ' '.join(parts[2:])
    for kv in tail.split(' '):
        if '=' in kv: k, v = kv.split('=', 1); f.setdefault(k, v)
    return f


def run_scenario(args, seconds):
    py(f'live.scenario({args})')
    time.sleep(seconds + .6)
    rows = json.loads(py('import json; live.stop("rec"); print(json.dumps(live.REC))').strip().splitlines()[-1])
    return [parse(r) for r in rows]


def modes(rows): return {r.get('mode') for r in rows}
def ever(rows, key, value): return any(r.get(key) == value for r in rows)
def combos(rows): return ' / '.join(dict.fromkeys(r['combo'] for r in rows if r.get('combo')))
def count(rows, key): return int(rows[-1].get(key, 0)) - int(rows[0].get(key, 0))


CASES = {}
def case(fn): CASES[fn.__name__] = fn; return fn


@case
def gestures():
    """Every Flick-It gesture pops its trick and lands (stopped on flat ground)."""
    bad = []
    for gesture, name in GESTURES.items():
        rows = run_scenario(f"-10, 8, 0, 0, [(0.2, ('flick', '{gesture}'))], duration=1.6", 1.6)
        seen = combos(rows)
        if name not in seen.split(' / ') and not any(c.startswith(name) for c in seen.split(' / ')): bad.append(f'{gesture} -> {seen or "nothing"}')
        elif count(rows, 'bails'): bad.append(f'{gesture} bailed')
    return not bad, '; '.join(bad) or f'{len(GESTURES)} gestures'


@case
def push_and_kickflip():
    rows = run_scenario("-28, 6, 0, 0, [(0.0, {'push': True}), (2.4, {}), (2.8, ('flick', 'kickflip', (0, 0), .22))], duration=4.2", 4.2)
    fast = max(float(r['speed']) for r in rows)
    ok = ever(rows, 'push', '1') and fast > 300 and 'Kickflip' in combos(rows) and count(rows, 'landed') >= 1 and not count(rows, 'bails')
    return ok, f'top speed {fast:.0f} cm/s, {combos(rows)}'


@case
def flat_bar_5050():
    rows = run_scenario("2, -4.5, 0, 520, [(0.98, ('flick', 'ollie'))], duration=3.5", 3.5)
    return ever(rows, 'mode', '3') and '50-50' in combos(rows) and not count(rows, 'bails'), combos(rows)


@case
def five_o():
    rows = run_scenario("2, -4.5, 0, 520, [(0.98, ('flick', 'ollie')), (1.3, {'right': (0, -0.6)}), (3.0, {})], duration=3.8", 3.8)
    return '5-0' in combos(rows), combos(rows)


@case
def boardslide():
    rows = run_scenario("2.5, 4.5, 0, 500, [(0.98, ('flick', 'ollie')), (1.22, {'left': (1, 0)}), (1.42, {})], duration=3.5", 3.5)
    return 'Boardslide' in combos(rows) and not count(rows, 'bails'), combos(rows)


@case
def handrail():
    rows = run_scenario("-28.5, -22.5, 0, 520, [(1.02, ('flick', 'ollie', (0, 0), .36))], duration=3.5", 3.5)
    return ever(rows, 'mode', '3') and not count(rows, 'bails'), combos(rows)


@case
def kicker():
    rows = run_scenario("-20, .9, 0, 750, [], duration=3.0", 3.0)
    return ever(rows, 'mode', '2') and not count(rows, 'bails'), f'air frames {sum(r.get("mode") == "2" for r in rows)}'


@case
def vert():
    rows = run_scenario("22, 0, 0, 950, [], duration=4.5", 4.5)
    up_vertical = any(abs(float(r['up'].strip('()').split(',')[2])) < .15 for r in rows if 'up' in r)
    ok = ever(rows, 'mode', '2') and up_vertical and rows[-1].get('fakie') == '1' and rows[-1].get('mode') == '1' and not count(rows, 'bails')
    return ok, f'reached vertical {up_vertical}, ends fakie {rows[-1].get("fakie")}'


@case
def revert():
    """The powerslide input right after a landing swings the board 180 on its wheels."""
    rows = run_scenario("-10, 8, 0, 500, [(0.3, ('flick', 'ollie')), (1.55, {'slide': True}), (1.65, {})], duration=2.5", 2.5)
    return 'Revert' in combos(rows) and rows[-1].get('fakie') == '1' and not count(rows, 'bails'), combos(rows)


@case
def double_flip():
    """A second flick in the air adds a flip."""
    rows = run_scenario("-10, 8, 0, 350, [(0.2, ('flick', 'kickflip', (0, 0), .3)), (0.86, ('flick', 'kickflip', (0, 0), .02))], duration=1.8", 1.8)
    return 'Double Kickflip' in combos(rows) and not count(rows, 'bails'), combos(rows)


@case
def continuous_push():
    """Holding push keeps pushing: the foot swings back to the ground, never back onto the tail, until let go."""
    rows = run_scenario("-38, 12, 0, 0, [(0.0, {'push': True}), (2.4, {})], duration=3.4", 3.4)
    held = [float(r['t']) for r in rows[:int(len(rows) * 2.0 / 3.4)] if r.get('clip') == 'SkatePush' and 't' in r]   # well before letting go
    back_on_tail = sum(1 for t in held if t > .8)
    top = max(float(r['speed']) for r in rows)
    return ever(rows, 'push', '1') and back_on_tail == 0 and top > 400 and rows[-1].get('push') == '0', f'top {top:.0f} cm/s, frames with the foot back on the tail while held: {back_on_tail}'


@case
def fakie_push():
    """Pushing while rolling fakie drives the board the way it is rolling (a switch push)."""
    rows = run_scenario("-10, 12, 0, -250, [(0.3, {'push': True}), (2.0, {})], duration=2.2", 2.2)
    return all(r.get('fakie') == '1' for r in rows[5:]) and float(rows[-1]['speed']) > 500, f'end speed {rows[-1]["speed"]}, fakie all along {all(r.get("fakie") == "1" for r in rows[5:])}'


@case
def turn_while_loaded():
    """The left stick still turns the board while the pop is loaded."""
    import math, re
    rows = run_scenario("-20, 8, 0, 500, [(0.2, {'right': (0, -1), 'left': (1, 0)}), (1.2, {'right': (0, -1)}), (1.25, {})], duration=1.6", 1.6)
    loaded = [r for r in rows if float(r.get('load', 0)) > .9]
    P = [tuple(map(float, r['pos'].strip('()').split(',')[:2])) for r in rows if 'pos' in r]
    turn = abs(math.degrees(math.atan2(P[-1][1] - P[-4][1], P[-1][0] - P[-4][0])))
    return len(loaded) > 10 and turn > 30, f'turned {turn:.0f} deg while loaded ({len(loaded)} frames)'


@case
def sideways_landing():
    """A landing up to about 60 degrees off the line rolls away (it costs speed); past that it bails."""
    import re
    ok_rows = run_scenario("-10, 8, 0, 500, [(0.2, ('flick', 'ollie', (0, 0), .3)), (0.55, {'left': (1, 0)}), (0.70, {})], duration=2.0", 2.0)
    spin = [float(r.get('spin', 0)) for r in ok_rows if r.get('mode') == '2']
    bad_rows = run_scenario("-10, 8, 0, 500, [(0.2, ('flick', 'ollie', (0, 0), .3)), (0.55, {'left': (1, 0)}), (0.78, {})], duration=2.0", 2.0)
    ok = not count(ok_rows, 'bails') and spin and abs(spin[-1]) > 40 and count(bad_rows, 'bails') == 1
    return ok, f'{abs(spin[-1]) if spin else 0:.0f} deg off landed, a bigger miss bailed {count(bad_rows, "bails") == 1}'


@case
def manual():
    rows = run_scenario("-10, 8, 0, 480, [(0.3, {'right': (0, -0.5)}), (1.3, {})], duration=1.8", 1.8)
    return ever(rows, 'manual', '1') and 'Manual' in combos(rows), combos(rows)


@case
def trick_to_manual():
    """Holding the manual on the way down lands the trick straight into it: no flat landing first."""
    rows = run_scenario("-10, 8, 0, 450, [(0.2, ('flick', 'kickflip', (0, 0), .3)), (0.85, {'right': (0, -0.5)}), (2.2, {})], duration=2.6", 2.6)
    touch = [i for i in range(1, len(rows)) if rows[i].get('mode') == '1' and rows[i - 1].get('mode') == '2']
    first = rows[touch[0]] if touch else {}
    ok = bool(touch) and first.get('manual') == '1' and first.get('clip') != 'SkateLand' and 'Kickflip + Manual' in combos(rows) and not count(rows, 'bails')
    return ok, f'touchdown manual={first.get("manual")} clip={first.get("clip")}; {combos(rows)}'


@case
def powerslide():
    rows = run_scenario("-12, -10, 0, 760, [(0.6, {'slide': True}), (1.8, {})], duration=2.2", 2.2)
    return ever(rows, 'slide', '1') and float(rows[-1]['speed']) < 300, f'end speed {rows[-1]["speed"]}'


@case
def grab():
    rows = run_scenario("0, 8, 0, 550, [(0.4, ('flick', 'ollie', (0, 0), .3)), (0.75, {'grab_right': True}), (1.05, {})], duration=2.2", 2.2)
    return 'Indy' in combos(rows) and not count(rows, 'bails'), combos(rows)


@case
def bail():
    rows = run_scenario("-11.5, 14, 90, 650, [], duration=3.6", 3.6)
    return count(rows, 'bails') == 1 and rows[-1].get('mode') == '1', f'{combos(rows)}, back on the board {rows[-1].get("mode") == "1"}'


@case
def sand_slows():
    """On the beach sand (the coconut stand beach) the board stops much sooner than on the pier's concrete."""
    sand = run_scenario("-106, 26, 0, 500, [], duration=1.3", 1.3)      # park-local metres of the beach at (-216, -169)
    concrete = run_scenario("-10, 8, 0, 500, [], duration=1.3", 1.3)
    a, b = float(sand[-1]['speed']), float(concrete[-1]['speed'])
    lost_a, lost_b = 500 - a, 500 - b
    return lost_a > 2.5 * lost_b and 'Sand' in sand[-1].get('surf', ''), f'speed lost in 1.3 s: sand {lost_a:.0f}, concrete {lost_b:.0f} cm/s'


@case
def keyboard_and_mouse():
    """The player's own path: keys and mouse through the player controller (not scripted skate input)."""
    py("live.skate_release(); live.skate() if 'mode=0' not in live.L.skate_state() else None")
    py("import unreal; live.teleport(live.park.ue(-25, 5), 0)")
    time.sleep(2.5)
    code = '''
L = live.L
ev = []
def key(t, k, down): ev.append((t, lambda: L.input_key(k, 'press' if down else 'release', 1.0)))
def axis(t, k, v, n=3):
    for i in range(n): ev.append((t + i * .017, lambda k=k, v=v: L.input_key(k, 'axis', v)))
key(0.0, 'B', True); key(0.05, 'B', False)
key(0.6, 'W', True); key(2.4, 'W', False)
key(2.6, 'LeftMouseButton', True); axis(2.63, 'MouseY', -300); axis(2.85, 'MouseX', -330); axis(2.85, 'MouseY', 330); key(3.05, 'LeftMouseButton', False)
key(4.2, 'SpaceBar', True); key(4.5, 'SpaceBar', False)
key(5.6, 'B', True); key(5.65, 'B', False)
ev.sort(key=lambda e: e[0]); st = {'t': 0.0, 'i': 0}; live.REC = []
def run(dt):
    st['t'] += dt
    while st['i'] < len(ev) and ev[st['i']][0] <= st['t']: ev[st['i']][1](); st['i'] += 1
    live.REC.append(L.skate_state())
    if st['t'] > 6.2: live.stop('keys')
live.behave('keys', run)
'''
    py(code)
    time.sleep(7)
    rows = [parse(r) for r in json.loads(py('import json; print(json.dumps(live.REC))').strip().splitlines()[-1])]
    ok = ever(rows, 'push', '1') and 'Kickflip' in combos(rows) and 'Ollie' in combos(rows) and rows[-1].get('mode') == '0'
    return ok, f'{combos(rows)}; stepped off {rows[-1].get("mode") == "0"}'


@case
def mouse_flip_to_manual():
    """With the mouse: a kickflip swipe, then a slow pull back lands into a manual (the mouse stick springs back to the
    centre after the flick, so the pull starts from the middle)."""
    py("live.skate_release(); live.park.place(-10, 8, 0); live.park.launch(450, 0)")
    code = '''
L = live.L
ev = []
def key(t, k, down): ev.append((t, lambda: L.input_key(k, 'press' if down else 'release', 1.0)))
def axis(t, k, v, n=3):
    for i in range(n): ev.append((t + i * .017, lambda k=k, v=v: L.input_key(k, 'axis', v)))
key(0.2, 'LeftMouseButton', True); axis(0.23, 'MouseY', -300); axis(0.45, 'MouseX', -330); axis(0.45, 'MouseY', 330)
axis(0.85, 'MouseY', -30, 12)
key(2.4, 'LeftMouseButton', False)
ev.sort(key=lambda e: e[0]); st = {'t': 0.0, 'i': 0}; live.REC = []
def run(dt):
    st['t'] += dt
    while st['i'] < len(ev) and ev[st['i']][0] <= st['t']: ev[st['i']][1](); st['i'] += 1
    live.REC.append(L.skate_state())
    if st['t'] > 2.6: live.stop('mouse')
live.behave('mouse', run)
'''
    py(code)
    time.sleep(3.2)
    rows = [parse(r) for r in json.loads(py('import json; print(json.dumps(live.REC))').strip().splitlines()[-1])]
    touch = [i for i in range(1, len(rows)) if rows[i].get('mode') == '1' and rows[i - 1].get('mode') == '2']
    first = rows[touch[0]] if touch else {}
    return 'Kickflip + Manual' in combos(rows) and first.get('manual') == '1', f'touchdown manual={first.get("manual")}; {combos(rows)}'


def settle(minimum=50., seconds=3., limit=300.):
    """Wait for a steady frame rate: a fresh project compiles shaders for minutes, and the mouse cases read gestures
    frame by frame."""
    start = time.monotonic(); steady = None
    while time.monotonic() - start < limit:
        fps = bridge.request('/state').get('fps', 0)
        steady = steady or (time.monotonic() if fps >= minimum else None)
        if fps < minimum: steady = None
        if steady and time.monotonic() - steady >= seconds: return
        time.sleep(.25)
    print(f'warning: frame rate still under {minimum:.0f} fps after {limit:.0f} s', flush=True)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('name', nargs='?', default=time.strftime('%Y%m%d_%H%M%S')); ap.add_argument('--only')
    a = ap.parse_args()
    settle()
    py(open(GAME / 'scenarios/skate_live_skate.py').read())
    py('live.L.skate_goofy(False); live.skate_park()')
    time.sleep(1.5)
    results = {}
    for name, fn in CASES.items():
        if a.only and name not in a.only.split(','): continue
        try: ok, note = fn()
        except Exception as error: ok, note = False, f'error: {error}'
        results[name] = {'ok': bool(ok), 'note': note}
        print(f'{"PASS" if ok else "FAIL"}  {name:20s} {note}', flush=True)
        py('live.skate_release()')
    out = yori.OUT / 'skateqa'; out.mkdir(parents=True, exist_ok=True)
    (out / f'{a.name}.json').write_text(json.dumps(results, indent=1) + '\n')
    passed = sum(r['ok'] for r in results.values())
    print(f'SKATE QA {passed}/{len(results)} passed -> {out / (a.name + ".json")}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(main())
