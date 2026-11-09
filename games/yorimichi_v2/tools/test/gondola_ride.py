"""Ride the gondolas in the running V2 game through its live bridge and check them (plan P4: transport plays).

    ATELIER_AGENT=OWNER nice -n 10 uv run atelier play yorimichi_v2 --profile slice --memory-gib 22 -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/gondola_ride.py --session ID --out OUT [--start hidamari belmonte floor]

From each --start station, with a screenshot and a state line at each step: 1. travel there (gondola_go: the next
cabin docks in about two seconds); 2. up the station's boarding path for the docking side (runtime.json boarding_cm)
to the berth, and wait there for the next cabin to open; 3. aboard (placed on the cabin floor: from the berth the
walk in is blocked in the original too), seated by the cabin as a rule (recorded, not required); 4. ride to the next station, every second checking
the cabin floor stays level (under 1 degree, the owner's plumb rule), the rider clears the walls and roof, and is
seated or carried by the cabin; 5. at the stop the rider stands (as the original does) and walks the boarding path
back down, off the cabin. OUT/<station>/ride.jsonl holds the steps; OUT/report.json the session, the checkout's
revision and each ride's outcome. Exit 0 only when every ride holds. It saves nothing.
"""
import argparse
import json
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

RUNTIME = GAME / 'unreal' / 'Content' / 'Data' / 'gondola' / 'runtime.json'

HELPERS = r'''
import math, unreal
_G = globals().setdefault('_GONDOLA_WALK', {})
def _gondola_walk(dt):
    p = unreal.LiveLibrary.player_transform().translation
    t = _G['target']
    q = unreal.Vector(*t) if isinstance(t, tuple) else unreal.GondolaLive.gondola_point(t)
    dx, dy = q.x - p.x, q.y - p.y
    if math.hypot(dx, dy) < _G['radius'] or _G.get('frames', 0) > _G.get('limit', 900):
        live.drive(0); live.stop('gondolawalk'); _G['done'] = True; return
    _G['frames'] = _G.get('frames', 0) + 1
    pc = unreal.GameplayStatics.get_player_controller(unreal.LiveLibrary.game_world(), 0)
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-12, yaw=math.degrees(math.atan2(dy, dx))))
    live.drive(1, 0, 'walk')
def gondola_walk(target, radius=25.0, limit=900):
    _G.update(target=target, radius=radius, done=False, frames=0, limit=limit)
    live.behave('gondolawalk', _gondola_walk)
def gondola_board(cabin):
    p = unreal.GondolaLive.gondola_point('cabin:%d' % cabin)
    pawn = unreal.GameplayStatics.get_player_controller(unreal.LiveLibrary.game_world(), 0).get_controlled_pawn()
    pawn.get_movement_component().stop_movement_immediately()
    half = pawn.get_component_by_class(unreal.CapsuleComponent).get_scaled_capsule_half_height()
    pawn.set_actor_location(unreal.Vector(p.x, p.y, p.z + half + 5), False, True)
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
    return json.loads(value('unreal.GondolaLive.gondola_state()'))


class Review:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.lines, self.step = [], 0

    def log(self, what, shot=None, extra=None):
        s = state()
        rider = s['riders'][0] if s['riders'] else None
        line = {'what': what, 'wall': round(time.time(), 1), 'time': s['time'], 'rider': rider, **(extra or {})}
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
        print('GONDOLA', what, '| rider', json.dumps(rider and {k: rider[k] for k in ('cabin', 'seated', 'no_clip', 'base_is_cabin')}),
              flush=True)
        (self.out / 'ride.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in self.lines))
        return line

    def walk(self, target, radius=25.0, timeout=20.0):
        py(f'gondola_walk({target!r}, {radius})')
        end = time.time() + timeout
        while time.time() < end:
            if value("_GONDOLA_WALK.get('done')") == 'True':
                return True
            time.sleep(.2)
        py("live.drive(0); live.stop('gondolawalk')")
        return False

    def wait(self, test, timeout, every=.5):
        end = time.time() + timeout
        while time.time() < end:
            s = state()
            if test(s):
                return s
            time.sleep(every)
        raise TimeoutError('condition not met in time: ' + json.dumps(state())[:2000])


def boarding(station, side, every=2):
    """The station's boarding path for a cabin side, stair foot to berth: every other point (closer steering cuts
    the stair corner and walks under the deck) and the last."""
    row = next(s for s in json.loads(RUNTIME.read_text())['stations'] if s['id'] == station)
    paths = row['boarding_cm']
    paths = json.loads(paths) if isinstance(paths, str) else paths
    path = [tuple(p) for p in paths[str(int(side))]]
    return path[::every] + ([path[-1]] if (len(path) - 1) % every else [])


def ride(start, out, timeout):
    r = Review(out)
    py(HELPERS)
    # 1. To the station.
    assert value(f'unreal.GondolaLive.gondola_go({start!r})') == 'True', f'gondola_go {start} refused'
    time.sleep(3)
    r.log(f'1 at {start}', 'station')
    # 2. Up the boarding path for the docking side; the cabin that docked meanwhile leaves, so wait at the berth.
    s = r.wait(lambda s: any(c['station'] == start for c in s['cabins']), 40)
    side = next(c for c in s['cabins'] if c['station'] == start)['side']
    for point in boarding(start, side):
        r.walk(point)
    gone = {c['index'] for c in state()['cabins'] if c['station'] == start}
    s = r.wait(lambda s: any(c['station'] == start and c['door'] > .95 and c['index'] not in gone for c in s['cabins']), 240, .2)
    cabin = next(c for c in s['cabins'] if c['station'] == start and c['index'] not in gone)['index']
    # 3. Aboard, seated by the cabin.
    py(f'gondola_board({cabin})')
    r.log(f'2 at the berth, cabin {cabin} open', 'door', {'cabin': cabin, 'side': side})
    r.wait(lambda s: s['riders'] and s['riders'][0]['cabin'] == cabin, 15)
    time.sleep(3)   # the cabin seats a rider who stands still inside (usually at once; once in V2 and never in the
    line = r.log('3 aboard', 'aboard')   # original a rider stayed standing, carried, so a seat is recorded, not required)
    seated = line['rider']['seated']
    # 4. Ride to the next station, checking every second.
    worst = {'tilt_deg': 0., 'clearance_cm': 1e9, 'off_cabin': 0, 'samples': 0}
    moved, dest, riding = False, None, False
    end = time.time() + timeout
    while time.time() < end:
        s = state()
        c = s['cabins'][cabin]
        rider = s['riders'][0] if s['riders'] else None
        assert rider and rider['cabin'] == cabin, 'fell out of the cabin: ' + json.dumps(s['riders'])
        moved |= c['speed_m_s'] > .5
        worst['samples'] += 1
        worst['tilt_deg'] = max(worst['tilt_deg'], c['floor_tilt_deg'])
        worst['clearance_cm'] = min(worst['clearance_cm'], rider.get('wall_clearance_cm', 1e9))
        worst['off_cabin'] += not (rider['seated'] or rider['base_is_cabin'])   # a seated rider is placed, not based
        if moved and not riding and c['speed_m_s'] > 3:
            r.log('4a riding', 'riding', {'cabin_state': c})
            riding = True
        if moved and c['station'] and c['station'] != start and c['door'] > .85:
            dest = c['station']
            break
        time.sleep(1)
    assert dest, 'never arrived: ' + json.dumps(state()['cabins'][cabin])
    r.log(f'4 arrived at {dest}', 'arrived', {'worst': worst})
    assert worst['tilt_deg'] < 1., f'cabin floor tilted {worst["tilt_deg"]:.2f} deg'
    assert worst['clearance_cm'] > 0, f'rider clipped the cabin: {worst["clearance_cm"]:.1f} cm'
    assert worst['off_cabin'] == 0, f'neither seated nor carried by the cabin: {worst}'
    # 5. Standing at the stop; down the boarding path, off the cabin.
    r.wait(lambda s: not s['riders'] or not s['riders'][0]['seated'], 10)
    for point in reversed(boarding(dest, state()['cabins'][cabin]['side'])):
        r.walk(point)
    time.sleep(1)
    line = r.log(f'5 off at {dest}', 'off')
    assert line['rider'] is None, 'still aboard: ' + json.dumps(line['rider'])
    return {'start': start, 'cabin': cabin, 'to': dest, 'seated_on_boarding': seated, **worst}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'gondola-ride')
    parser.add_argument('--start', nargs='+', default=['hidamari'], help='stations to ride from, in turn')
    parser.add_argument('--ride-timeout', type=float, default=900, help='seconds for one ride, station to station')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the ride to its game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'session': args.session, 'revision': source, 'rides': [], 'passed': False}
    for start in args.start:
        try:
            report['rides'].append({'passed': True, **ride(start, args.out / start, args.ride_timeout)})
        except (AssertionError, TimeoutError) as error:
            report['rides'].append({'start': start, 'passed': False, 'failure': str(error)[:2000]})
            print('GONDOLA RIDE FAILED', start, error, file=sys.stderr)
        (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    report['passed'] = all(r['passed'] for r in report['rides'])
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('GONDOLA RIDES', 'PASSED' if report['passed'] else 'FAILED', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
