"""Cross on the ferry in the running slice game through its live bridge and check it (plan P4: transport plays).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/ferry_ride.py --session ID --out OUT [--start hidamari]

With a screenshot and a state line at each step: 1. ferry_go --start (the ship comes alongside, its brow down);
2. along the terminal's walk, over the brow, onto the deck; 3. stand there through departure and the crossing,
every second checking the player stays aboard that ship and moves with it (drift in the ship's frame under --drift
cm while nobody steers); 4. berthed at the other terminal, its brow down; 5. back along that terminal's walk, ashore.
OUT/ride.jsonl holds the steps; OUT/report.json the session, the checkout's revision and the outcome. Exit 0 only
when every step holds. It saves nothing.
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

SERVICE = GAME / 'unreal' / 'Content' / 'Data' / 'ferry' / 'service' / 'service.json'

HELPERS = r'''
import math, unreal
_F = globals().setdefault('_FERRY_WALK', {})
def _ferry_walk(dt):
    p = unreal.LiveLibrary.player_transform().translation
    q = unreal.FerryLive.ferry_point(_F['target'])
    dx, dy = q.x - p.x, q.y - p.y
    if math.hypot(dx, dy) < _F['radius'] or _F.get('frames', 0) > _F.get('limit', 900):
        live.drive(0); live.stop('ferrywalk'); _F['done'] = True; return
    _F['frames'] = _F.get('frames', 0) + 1
    pc = unreal.GameplayStatics.get_player_controller(unreal.LiveLibrary.game_world(), 0)
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-12, yaw=math.degrees(math.atan2(dy, dx))))
    live.drive(1, 0, 'walk')
def ferry_walk(target, radius=30.0, limit=900):
    _F.update(target=target, radius=radius, done=False, frames=0, limit=limit)
    live.behave('ferrywalk', _ferry_walk)
'''


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
    return json.loads(value('unreal.FerryLive.ferry_state()'))


def terminals():
    return json.loads(SERVICE.read_text())['terminals']


def walk_points(index):
    walk = terminals()[index]['walk_cm']
    return len(json.loads(walk) if isinstance(walk, str) else walk)


class Review:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.lines, self.step = [], 0

    def log(self, what, shot=None, extra=None):
        s = state()
        line = {'what': what, 'wall': round(time.time(), 1), **{k: s[k] for k in ('time', 'aboard', 'ship', 'local', 'brows', 'base')},
                'ships': [{k: x[k] for k in ('phase', 'berth', 'speed')} for x in s['ships']], **(extra or {})}
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
        print('FERRY', what, '| aboard', s['aboard'], 'ship', s['ship'], 'phase', line['ships'][0]['phase'], 'base', s['base'], flush=True)
        (self.out / 'ride.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in self.lines))
        return line

    def walk(self, target, radius=30.0, timeout=25.0):
        py(f'ferry_walk({target!r}, {radius})')
        end = time.time() + timeout
        while time.time() < end:
            if value("_FERRY_WALK.get('done')") == 'True':
                return True
            time.sleep(.2)
        py("live.drive(0); live.stop('ferrywalk')")
        return False

    def wait(self, test, timeout, every=.5):
        end = time.time() + timeout
        while time.time() < end:
            s = state()
            if test(s):
                return s
            time.sleep(every)
        raise TimeoutError('condition not met in time: ' + json.dumps(state())[:2000])


def cross(args):
    r = Review(args.out)
    py(HELPERS)
    rows = terminals()
    start = next(i for i, t in enumerate(rows) if t['key'] == args.start)
    # 1. To the terminal: the next ship comes alongside, brow down.
    assert value(f'unreal.FerryLive.ferry_go({args.start!r})') == 'True', f'ferry_go {args.start} refused'
    time.sleep(3)
    r.wait(lambda s: s['brows'].get(args.start, 0) > .95 and any(x['phase'] == 'berthed' for x in s['ships']), 90)
    r.log(f'1 at {args.start}, brow down', 'terminal')
    # 2. Along the walk, over the brow, onto the deck.
    for i in range(walk_points(start)):
        r.walk(f'walk:{start}:{i}')
    time.sleep(1.5)
    line = r.log('2 aboard', 'aboard')
    assert line['aboard'], 'not aboard after the walk: ' + json.dumps(line)
    ship = line['ship']
    # 3. Stand on deck through departure and the crossing.
    worst = {'drift_cm': 0., 'off': 0, 'samples': 0}
    first, left, dest = None, False, None
    end = time.time() + args.crossing_timeout
    while time.time() < end:
        s = state()
        x = s['ships'][ship]
        worst['samples'] += 1
        worst['off'] += not (s['aboard'] and s['ship'] == ship)
        if s['aboard'] and s['ship'] == ship:
            first = first or s['local']
            worst['drift_cm'] = max(worst['drift_cm'], math.dist(first[:2], s['local'][:2]))
        if x['phase'] != 'berthed' and not left:
            left = True
            r.log('3a departing', 'departing')
        elif left and x['phase'] == 'cruise' and worst['samples'] % 120 == 0:
            r.log('3b at sea', 'sea')
        if left and x['phase'] == 'berthed':
            dest = x['berth']
            break
        time.sleep(1)
    assert dest is not None, 'never berthed again: ' + json.dumps(state()['ships'][ship])
    key = rows[dest]['key']
    r.wait(lambda s: s['brows'].get(key, 0) > .95, 60)
    r.log(f'4 berthed at {key}', 'berthed', {'worst': worst})
    assert worst['off'] == 0, f'left the ship during the crossing: {worst}'
    assert worst['drift_cm'] < args.drift, f'not carried by the ship: drift {worst["drift_cm"]:.0f} cm'
    # 5. Back along that terminal's walk, ashore.
    for i in range(walk_points(dest) - 1, -1, -1):
        r.walk(f'walk:{dest}:{i}')
    time.sleep(1.5)
    line = r.log(f'5 ashore at {key}', 'ashore')
    assert not line['aboard'], 'still aboard after walking off'
    return {'from': args.start, 'to': key, **worst}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'ferry-ride')
    parser.add_argument('--start', default='hidamari', help='terminal to board at (service.json terminals key)')
    parser.add_argument('--drift', type=float, default=60.0, help='cm the player may move in the ship frame standing')
    parser.add_argument('--crossing-timeout', type=float, default=1200, help='seconds from boarding to the next berth')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the crossing to its game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'session': args.session, 'revision': source, 'passed': False}
    try:
        report['crossing'] = cross(args)
        report['passed'] = True
    except (AssertionError, TimeoutError) as error:
        report['failure'] = str(error)[:2000]
        print('FERRY CROSSING FAILED', error, file=sys.stderr)
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('FERRY CROSSING', 'PASSED' if report['passed'] else 'FAILED', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
