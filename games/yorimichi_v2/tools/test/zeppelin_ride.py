"""Fly the zeppelin round its line in the running slice game through its live bridge and check it (plan P5-E, F11).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/zeppelin_ride.py --session ID --out OUT [--start 0] [--legs 6]

The player travels once, to the --start station's entry; from then on only the interact button is pressed, as a
player would. Each leg, with a screenshot and a state line at each step: 1. interact at the platform (it calls the
ship in when it is docked elsewhere, then boards); 2. the ship's own boarding walk onto the deck; 3. climb, cruise
and landing, every half second checking the player is still its passenger and rides on the ship; 4. by the time
the gate opens, World Partition has activated every cell within --loaded metres of the arrival platform (the player
was the moving streaming source); 5. the ship's own walk off: ashore, on walkable ground at the arrival platform,
standing still. The ship carries on along its line, turning back at either end, so six legs from Woodland fly out
to Belmonte and home again. OUT/ride.jsonl holds the steps; OUT/report.json the session, the checkout's revision and
each leg's stations, flight seconds and worst samples. Exit 0 only when every step holds. It saves nothing.
"""
import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[1]
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'platform' / 'studio'))
from launch import launch_revision, revision  # noqa: E402
from atelier import live  # noqa: E402
from atelier.live_sessions import Unreachable  # noqa: E402

DOCKED, CALLED, BOARDING, CLIMB, CRUISE, LANDING, LEAVING = range(7)


def py(code):
    # A busy game can miss the session check, which runs before anything is sent: only that is retried.
    for attempt in range(8):
        try:
            out = live.request('/python', code)
            break
        except Unreachable:
            if attempt == 7:
                raise
            time.sleep(3)
    if not out.get('ok'):
        raise RuntimeError(out.get('result') or out)
    return out.get('output', '').strip()


def value(expression):
    return py(f'print({expression})')


def state():
    return json.loads(value('unreal.ZeppelinLive.zeppelin_state()'))


def loaded(point, radius_cm):
    x, y, z = point
    return value(f'unreal.V2Streaming.is_loaded_around(unreal.LiveLibrary.game_world(), unreal.Vector({x}, {y}, {z}), {radius_cm})') == 'True'


class Review:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.lines, self.step = [], 0

    def log(self, what, shot=None, extra=None):
        s = state()
        line = {'what': what, 'wall': round(time.time(), 1), **{k: s[k] for k in ('phase', 'dock', 'destination', 'phase_time', 'ship',
                'passenger', 'player', 'mode', 'on_ground', 'gate')}, **(extra or {})}
        if shot:
            self.step += 1
            path = self.out / f'{self.step:02d}-{shot}.png'
            if path.exists():
                path.unlink()
            py(f'unreal.LiveLibrary.screenshot({str(path)!r})')
            for _ in range(80):
                if path.exists() and path.stat().st_size:
                    break
                time.sleep(.1)
            line['shot'] = path.name
        self.lines.append(line)
        print('ZEPPELIN', what, '| phase', s['phase'], 'dock', s['dock'], 'passenger', s['passenger'], flush=True)
        (self.out / 'ride.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in self.lines))
        return line

    def wait(self, test, timeout, every=.5):
        end = time.time() + timeout
        while time.time() < end:
            s = state()
            if test(s):
                return s
            time.sleep(every)
        raise TimeoutError('condition not met in time: ' + json.dumps(state())[:2000])


def leg(r, args, number):
    s = state()
    at, names = s['dock'], [x['name'] for x in s['stations']]
    # 1. Interact at the platform: a ship docked elsewhere is called in first, then a second press boards.
    for _ in range(3):
        py("live.press('interact')")
        time.sleep(1)
        s = r.wait(lambda s: s['phase'] in (DOCKED, BOARDING) or s['passenger'], 30)
        if s['passenger']:
            break
    assert s['passenger'] and s['phase'] == BOARDING, 'interact did not board: ' + json.dumps(s)[:1500]
    if s['dock'] != at:
        raise AssertionError(f'boarded at {names[s["dock"]]}, not {names[at]}')
    to = s['destination']
    r.log(f'{number}.1 boarding at {names[at]} for {names[to]}', f'{number}-boarding')
    # 2. The ship's boarding walk, then 3. the flight, sampled.
    r.wait(lambda s: s['phase'] >= CLIMB, 30)
    r.log(f'{number}.2 aboard, climbing', f'{number}-climb')
    worst = {'off_ship_cm': 0., 'not_passenger': 0, 'samples': 0, 'top_m': 0.}
    start, cruise_shot, arrived_loaded, loaded_before = time.time(), False, None, loaded(s['stations'][to]['entry'], args.loaded * 100)
    end = start + args.flight_timeout
    while time.time() < end:
        s = state()
        if s['phase'] in (DOCKED, LEAVING):
            break
        worst['samples'] += 1
        worst['not_passenger'] += not s['passenger']
        worst['off_ship_cm'] = max(worst['off_ship_cm'], math.dist(s['player'][:2], s['ship'][:2]))
        worst['top_m'] = max(worst['top_m'], s['ship'][2] / 100)
        if s['phase'] == CRUISE and s['phase_time'] > 8 and not cruise_shot:
            cruise_shot = True
            r.log(f'{number}.3 cruising', f'{number}-cruise')
        if s['phase'] == LANDING and arrived_loaded is None and loaded(s['stations'][to]['entry'], args.loaded * 100):
            arrived_loaded = round(s['phase_time'], 1)
        time.sleep(.5)
    flight = round(time.time() - start, 1)
    assert s['phase'] in (DOCKED, LEAVING), f'still flying after {args.flight_timeout:.0f} s: ' + json.dumps(s)[:1500]
    # 4. The arrival platform's cells are active by the time the gate opens.
    if arrived_loaded is None and loaded(s['stations'][to]['entry'], args.loaded * 100):
        arrived_loaded = 'at gate'
    r.log(f'{number}.4 landed at {names[to]}', f'{number}-landed', {'worst': worst, 'loaded': arrived_loaded})
    assert worst['not_passenger'] == 0, f'not a passenger during the flight: {worst}'
    assert worst['off_ship_cm'] < args.off_ship, f'not riding on the ship: {worst["off_ship_cm"]:.0f} cm from it'
    assert arrived_loaded is not None, f'{names[to]} not loaded within {args.loaded:.0f} m when the gate opened'
    # 5. The ship's walk off: ashore, standing on the arrival platform.
    s = r.wait(lambda s: s['phase'] == DOCKED and not s['passenger'], 40)
    time.sleep(3)
    before = state()['player']
    time.sleep(2)
    line = r.log(f'{number}.5 ashore at {names[to]}', f'{number}-ashore')
    off = math.dist(line['player'][:2], s['stations'][to]['entry'][:2])
    assert line['on_ground'], 'not on the ground after walking off: ' + json.dumps(line)
    assert off < args.ashore, f'{off:.0f} cm from the arrival platform entry'
    assert abs(line['player'][2] - before[2]) < 10, f'not standing still ashore: fell {before[2] - line["player"][2]:.0f} cm'
    return {'from': names[at], 'to': names[to], 'flight_s': flight, 'loaded_before_departure': loaded_before,
            'loaded_landing_s': arrived_loaded, **worst}


def ride(args):
    r = Review(args.out)
    s = state()
    assert s.get('ready'), 'no ready zeppelin: ' + json.dumps(s)[:500]
    x, y, z = s['stations'][args.start]['entry']
    sx, sy = s['stations'][args.start]['ship'][:2]
    assert value(f'unreal.YorimichiLive.travel(unreal.Vector({x}, {y}, {z}), {math.degrees(math.atan2(sy - y, sx - x))})') == 'True', 'travel refused'
    time.sleep(args.settle)
    r.wait(lambda s: s['on_ground'], 30)
    r.log(f'0 at {s["stations"][args.start]["name"]}', '0-platform')
    legs = []
    for number in range(1, args.legs + 1):
        legs.append(leg(r, args, number))
    return legs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'zeppelin-ride')
    parser.add_argument('--start', type=int, default=0, help='station index to travel to first (world.json zeppelin stations)')
    parser.add_argument('--legs', type=int, default=6, help='flights; six from Woodland fly to Belmonte and back')
    parser.add_argument('--loaded', type=float, default=300.0, help='metres round the arrival platform that must be loaded')
    parser.add_argument('--off-ship', type=float, default=300.0, help='cm the passenger may be from the ship, level')
    parser.add_argument('--ashore', type=float, default=200.0, help='cm the player may stand from the arrival platform entry')
    parser.add_argument('--settle', type=float, default=20.0, help='seconds for the start platform to load after travel')
    parser.add_argument('--flight-timeout', type=float, default=240.0, help='seconds from boarding to the arrival gate')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the ride to its game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'session': args.session, 'revision': source, 'passed': False}
    try:
        report['legs'] = ride(args)
        report['passed'] = True
    except (AssertionError, TimeoutError) as error:
        report['failure'] = str(error)[:2000]
        print('ZEPPELIN RIDE FAILED', error, file=sys.stderr)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('ZEPPELIN RIDE', 'PASSED' if report['passed'] else 'FAILED', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
