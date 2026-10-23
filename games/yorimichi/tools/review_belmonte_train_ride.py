"""Scripted ride on the Belmonte train through the live bridge, with screenshots and log lines at each step.

    uv run atelier play yorimichi --profile play          # in one terminal (or any profile with the live bridge)
    uv run python games/yorimichi/tools/review_belmonte_train_ride.py [--out DIR] [--scale 10]

1. travel to Belmonte Station as a train starts its dwell; 2. wait for the dwell; 3. Board at a door (it opens, the
steps, it closes); 4. into the saloon; 5. stand still through the departure (drift against the coach), walk the saloon
at speed, sit; 6. ride (at --scale times the timetable) past the loop, stand a while in the spiral, sit again; 7. arrive
at Hidamari; 8. stand and Step off onto the platform.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME.parents[1] / 'platform' / 'studio'))
from atelier import live  # noqa: E402

HELPERS = r'''
import math, unreal
_T = globals().setdefault('_TRAIN_WALK', {})
def _train_target():
    t = _T['target']
    return unreal.BelmonteTrainLive.train_point(*t) if isinstance(t, tuple) else t
def _train_walk(dt):
    p = unreal.LiveLibrary.player_transform().translation
    q = _train_target()
    dx, dy = q.x - p.x, q.y - p.y
    if math.hypot(dx, dy) < _T['radius'] or _T.get('frames', 0) > _T.get('limit', 900):
        live.drive(0); live.stop('trainwalk'); _T['done'] = True; return
    _T['frames'] = _T.get('frames', 0) + 1
    pc = unreal.GameplayStatics.get_player_controller(unreal.LiveLibrary.game_world(), 0)
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-12, yaw=math.degrees(math.atan2(dy, dx))))
    live.drive(1, 0, 'walk')
def train_walk(target, radius=40.0, limit=900):
    _T.update(target=target, radius=radius, done=False, frames=0, limit=limit)
    live.behave('trainwalk', _train_walk)
def train_face(target):
    p = unreal.LiveLibrary.player_transform().translation
    q = unreal.BelmonteTrainLive.train_point(*target) if isinstance(target, tuple) else target
    pc = unreal.GameplayStatics.get_player_controller(unreal.LiveLibrary.game_world(), 0)
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-15, yaw=math.degrees(math.atan2(q.y - p.y, q.x - p.x))))
'''


def py(code):
    out = live.request('/python', code)
    if not out.get('ok'):
        raise RuntimeError(out.get('result') or out)
    return out.get('output', '').strip()


def value(expression):
    return py(f'print({expression})')


def state():
    return json.loads(value('unreal.BelmonteTrainLive.train_state()'))


def console(command):
    py(f'unreal.SystemLibrary.execute_console_command(unreal.LiveLibrary.game_world(), {command!r})')


class Review:
    def __init__(self, out):
        self.out = out
        self.out.mkdir(parents=True, exist_ok=True)
        self.lines = []
        self.step = 0

    def log(self, what, shot=None, extra=None):
        s = state()
        line = {'what': what, 'wall': round(time.time(), 1), 'prompt': value('unreal.BelmonteTrainLive.train_prompt()'), **s, **(extra or {})}
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
        print('TRAIN REVIEW', json.dumps(line), flush=True)
        (self.out / 'ride.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in self.lines))
        return line

    def walk(self, target, radius=40.0, timeout=30.0):
        py(f'train_walk({target!r}, {radius})')
        end = time.time() + timeout
        while time.time() < end:
            if value("_TRAIN_WALK.get('done')") == 'True':
                return True
            time.sleep(.2)
        py("live.drive(0); live.stop('trainwalk')")
        return False

    def wait(self, test, timeout, every=.5):
        end = time.time() + timeout
        while time.time() < end:
            s = state()
            if test(s):
                return s
            time.sleep(every)
        raise TimeoutError('condition not met in time: ' + json.dumps(state()))


def nearest_seat(train, vehicle, count):
    p = state()['player']
    best, index = 1e18, 0
    for i in range(count):
        q = [float(x) for x in value(f'tuple(unreal.BelmonteTrainLive.train_point({train}, {vehicle!r}, "seat:{i}").to_tuple())').strip('()').split(',')]
        d = math.dist(p[:2], q[:2])
        if d < best:
            best, index = d, i
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=GAME.parents[1] / 'build/yorimichi/belmonte-train/ingame')
    parser.add_argument('--scale', type=float, default=10.0, help='service clock speed between the walking tests')
    parser.add_argument('--vehicle', default='second-class')
    parser.add_argument('--door', default='exterior-bl')
    parser.add_argument('--inner', default='bulkhead-b', help='the vestibule door into the saloon')
    parser.add_argument('--seats', type=int, default=64)
    args = parser.parse_args(argv)
    r = Review(args.out)
    py(HELPERS)
    console('train.TimeScale 1')
    # 1. Teleport (the map's "Belmonte Station" does the same).
    console('train.Go belmonte')
    time.sleep(3)
    s = r.log('1 teleported to Belmonte Station', 'teleport')
    # 2. Wait for the dwell.
    s = r.wait(lambda s: any(t['station'] and t['s'] > 7000 for t in s['trains']), 60)
    train = next(i for i, t in enumerate(s['trains']) if t['station'] and t['s'] > 7000)
    r.log(f'2 train {s["trains"][train]["name"]} standing at Belmonte', 'dwell')
    vehicle = lambda what: (train, args.vehicle, what)  # noqa: E731

    def drift(seconds, every=.2):
        """How far the standing player moves in their coach's frame while the train runs (cm), from one state read
        each time (the player and the coach in the same frame)."""
        first = state()['local']
        worst, end = 0., time.time() + seconds
        while time.time() < end:
            s = state()
            assert s['aboard'], 'fell out of the train: ' + json.dumps(s)
            worst = max(worst, math.dist(s['local'][:2], first[:2]))
            time.sleep(every)
        return round(worst, 1)

    def ride_door(up):
        py("live.press('interact')")
        time.sleep(.6)
        r.log(f'{"Board" if up else "Step off"}: on the steps', 'steps-up' if up else 'steps-down')
        return r.wait(lambda s: not s['boarding'], 15, .2)

    # 3. Monter: from the platform at the door, the door opens, he walks up the steps, it closes behind him.
    r.walk(vehicle(f'board:{args.door}:0'), 45)
    py(f'train_face({vehicle(f"board:{args.door}:-1")!r})')
    time.sleep(.3)
    s = r.log('3 at the door on the platform', 'door')
    assert 'board' in s['prompt'], s['prompt']
    s = ride_door(True)
    s = r.log('4 aboard (door closed behind)', 'aboard')
    assert s['aboard'], 'not aboard after boarding'
    # 4. Through the bulkhead door into the saloon, then stand still in the aisle for the departure.
    r.walk(vehicle(f'door:{args.inner}:1'), 35)
    py(f'train_face({vehicle(f"door:{args.inner}:0")!r})')
    py("live.press('interact')")
    time.sleep(1.2)
    r.walk(vehicle('local:6:0'), 30)
    py(f'train_face({vehicle("local:0:0")!r})')
    r.log('5 standing in the saloon', 'standing')
    s = r.wait(lambda s: abs(s['trains'][train]['kmh']) > .5, 140, .2)
    standing = drift(12)
    s = r.log('6a departure standing still', 'departing-standing', {'drift_cm': standing})
    assert standing < 40, f'not carried at departure: {standing} cm'
    # 5. Walk the corridor at speed: the walk is relative to the coach.
    s = r.wait(lambda s: abs(s['trains'][train]['kmh']) > 25, 120)
    for target in ('local:2:0', 'local:-4:0', 'local:4:0'):
        r.walk(vehicle(target), 40, 15)
    s = r.log('6b walked the saloon at speed', 'walking-at-speed', {'kmh': s['trains'][train]['kmh']})
    assert s['aboard'], 'fell out of the train while walking'
    # 6. Sit, ride past the loop and into the spiral faster than the timetable; stand a while in the spiral.
    seat = nearest_seat(train, args.vehicle, args.seats)
    r.walk(vehicle(f'seat:{seat}'), 70)
    py("live.press('interact')")
    time.sleep(2.5)
    s = r.log('6c seated', 'seated')
    assert s['seat'], 'not seated'
    console(f'train.TimeScale {args.scale}')
    s = r.wait(lambda s: s['trains'][train]['s'] < 4800, 600, 1)
    r.log('6d at the passing loop', 'loop')
    s = r.wait(lambda s: s['trains'][train]['s'] < 3300, 900, 1)
    console('train.TimeScale 2')
    py("live.press('interact')")
    time.sleep(1.5)
    standing = drift(10)
    s = r.log('6e standing in the spiral', 'spiral-standing', {'drift_cm': standing, 'kmh': s['trains'][train]['kmh']})
    assert standing < 40, f'not carried in the spiral: {standing} cm'
    seat = nearest_seat(train, args.vehicle, args.seats)
    r.walk(vehicle(f'seat:{seat}'), 70)
    py("live.press('interact')")
    time.sleep(2)
    console(f'train.TimeScale {args.scale}')
    s = r.wait(lambda s: s['trains'][train]['s'] < 2200, 600, 1)
    r.log('6f past the spiral', 'past-spiral')
    s = r.wait(lambda s: s['trains'][train]['s'] < 600, 600, 1)
    console('train.TimeScale 1')
    # 7. Arrive at Hidamari, seated, through the braking.
    s = r.wait(lambda s: s['trains'][train]['station'], 240)
    r.log('7 arrived at Hidamari', 'arrived')
    assert s['seat'] and s['vehicle'] == args.vehicle, 'lost the seat on the way'
    # 8. Stand, back through the vestibule, Descendre.
    py("live.press('interact')")
    time.sleep(1)
    r.walk(vehicle('local:8.6:0'), 35)
    r.walk(vehicle('local:10.7:0'), 30)   # through the bulkhead doorway, then across the vestibule
    r.walk(vehicle(f'board:{args.door}:-1'), 30)
    py(f'train_face({vehicle(f"board:{args.door}:0")!r})')
    time.sleep(.3)
    s = r.log('8a inside at the door at Hidamari', 'door-hidamari')
    assert 'step off' in s['prompt'], s['prompt']
    s = ride_door(False)
    py(f'train_face({vehicle("centre")!r})')
    time.sleep(.5)
    s = r.log('8 stepped off at Hidamari', 'off')
    assert not s['aboard'], 'still aboard'
    print('TRAIN REVIEW COMPLETE', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
