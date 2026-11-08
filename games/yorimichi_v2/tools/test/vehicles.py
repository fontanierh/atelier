"""Ride the bike, the horse and the sailboat in the running slice game through its live bridge and check them (F08-F10).

    uv run atelier play yorimichi_v2 --profile slice -- -RenderOffscreen      # first, and wait for the world
    uv run python games/yorimichi_v2/tools/test/vehicles.py --session ID --out OUT [--only bike horse sail]

Each vehicle starts with a map travel to its site (map.json zones) and then uses only the player's buttons and stick,
with a screenshot and a state line at each step:
  bike   on the coastal road: get on, ride, sprint, steer, stop, park, get back on the parked bike, park again; it
         must ride on its wheels (airborne under --air of the samples) and turn with the stick
  horse  at Belmonte's training grounds: mount, take each of the roster's breeds in turn (each must resolve), walk,
         jog, gallop and sprint (each faster than the last), stop and dismount onto the ground
  sail   at the coconut-stand beach: launch from the sand, sail out on the water, come about, sail back and step off
         onto the beach
OUT/vehicles.jsonl holds the steps; OUT/report.json the session, the checkout's revision and each vehicle's outcome.
Exit 0 only when every chosen vehicle passes. It saves nothing.
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

DATA = GAME / 'unreal' / 'Content' / 'Data'
BIKE_OFF, BIKE_RIDING = 0, 2
HORSE_STOWED, HORSE_RIDING = 0, 2

HELPERS = r'''
import math, unreal
_V = globals().setdefault('_VEHICLE_GO', {})
def _vehicle_go(dt):
    p = unreal.LiveLibrary.player_transform().translation
    x, y = _V['target']
    dx, dy = x - p.x, y - p.y
    if math.hypot(dx, dy) < _V['radius'] or _V.get('frames', 0) > _V['limit']:
        live.drive(0); live.stop('vehiclego'); _V['done'] = True; return
    _V['frames'] = _V.get('frames', 0) + 1
    pc = unreal.GameplayStatics.get_player_controller(unreal.LiveLibrary.game_world(), 0)
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-12, yaw=math.degrees(math.atan2(dy, dx))))
    live.drive(1, 0, _V['gait'])
def vehicle_go(x, y, radius, gait='run', limit=2400):
    _V.update(target=(x, y), radius=radius, gait=gait, done=False, frames=0, limit=limit)
    live.behave('vehiclego', _vehicle_go)
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


def fields(text):
    """BikeState / HorseState / SailState text: key=value words, numbers and (x,y,z) tuples parsed."""
    out = {}
    for word in text.split(' '):
        if '=' not in word:
            continue
        key, raw = word.split('=', 1)
        try:
            out[key] = [float(v) for v in raw.strip('()').split(',')] if raw.startswith('(') else float(raw)
        except ValueError:
            out[key] = raw
    return out


def bike():
    return fields(value('unreal.YorimichiLive.bike_state()'))


def horse():
    return fields(value('unreal.YorimichiLive.horse_state()'))


def sail():
    return fields(value('unreal.YorimichiLive.sail_state()'))


def player():
    return [float(v) for v in value('(lambda p: f"{p.x} {p.y} {p.z}")(unreal.LiveLibrary.player_transform().translation)').split()]


def press(button):
    assert value(f'live.press({button!r})') == 'True', f'{button} was not pressed'


def drive(forward=0., right=0., gait='run'):
    py(f'live.drive({forward}, {right}, {gait!r})')


class Review:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.lines, self.step = [], 0

    def log(self, what, shot=None, extra=None):
        line = {'what': what, 'wall': round(time.time(), 1), 'player': player(), **(extra or {})}
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
        print('VEHICLE', what, json.dumps({k: v for k, v in line.items() if k not in ('what', 'wall', 'shot')})[:300], flush=True)
        (self.out / 'vehicles.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in self.lines))
        return line

    def wait(self, read, test, timeout, every=.25):
        end = time.time() + timeout
        while time.time() < end:
            s = read()
            if test(s):
                return s
            time.sleep(every)
        raise TimeoutError('condition not met in time: ' + json.dumps(read())[:1500])

    def go(self, x, y, radius, gait='run', timeout=60.):
        py(f'vehicle_go({x}, {y}, {radius}, {gait!r})')
        end = time.time() + timeout
        while time.time() < end:
            if value("_VEHICLE_GO.get('done')") == 'True':
                return True
            time.sleep(.25)
        py("live.drive(0); live.stop('vehiclego')")
        return False


def travel(r, key, settle):
    zone = next(z for z in json.loads((DATA / 'map' / 'map.json').read_text())['zones'] if z['key'] == key)
    # Map metres to Unreal cm (AJapanWorld::ToUE flips y, so a map yaw turns the other way).
    x, y, z = zone['x'] * 100, -zone['y'] * 100, zone['z'] * 100
    assert value(f'unreal.YorimichiLive.travel(unreal.Vector({x}, {y}, {z}), {-zone["yaw"]})') == 'True', f'travel to {key} refused'
    time.sleep(settle)
    r.log(f'at {zone["name"]}', key)
    return zone


def sample(read, seconds, every=.2):
    rows, end = [], time.time() + seconds
    while time.time() < end:
        rows.append(read())
        time.sleep(every)
    return rows


def check_bike(r, args):
    travel(r, 'spawn', args.settle)
    press('bike')
    r.wait(bike, lambda s: s.get('state') == BIKE_RIDING, 10)
    r.log('bike: on', 'bike-on', {'bike': bike()})
    drive(1, 0, 'run')
    rows = sample(bike, 6)
    press('sprint')
    rows += sample(bike, 4)
    sprinted = any(s['sprint'] == 1 for s in rows[-20:])
    r.log('bike: riding', 'bike-riding', {'bike': rows[-1]})
    yaw = rows[-1]['yaw']
    drive(1, .7, 'run')
    turn = sample(bike, 3)
    turned = abs((turn[-1]['yaw'] - yaw + 180) % 360 - 180)
    rows += turn
    drive(0)
    r.wait(bike, lambda s: s['speed'] < 30, 15)
    top, air = max(s['speed'] for s in rows), sum(s['air'] for s in rows) / len(rows)
    press('bike')
    parked = r.wait(bike, lambda s: s['state'] == BIKE_OFF and s['parked'] == 1, 10)
    r.log('bike: parked', 'bike-parked', {'bike': parked})
    press('bike')
    r.wait(bike, lambda s: s.get('state') == BIKE_RIDING, 10)
    drive(1, 0, 'run')
    time.sleep(2)
    drive(0)
    r.wait(bike, lambda s: s['speed'] < 30, 15)
    press('bike')
    again = r.wait(bike, lambda s: s['state'] == BIKE_OFF and s['parked'] == 1, 10)
    r.log('bike: parked again', 'bike-parked-again', {'bike': again})
    result = {'top_speed': top, 'sprinted': sprinted, 'turned_deg': round(turned, 1), 'airborne': round(air, 3)}
    assert top > 400, f'bike too slow: {result}'
    assert sprinted, f'sprint did not take: {result}'
    assert turned > 20, f'bike did not steer: {result}'
    assert air < args.air, f'bike off its wheels: {result}'
    return result


def check_horse(r, args):
    travel(r, 'belmonte_training', args.settle)
    press('horse')
    r.wait(horse, lambda s: s.get('state') == HORSE_RIDING, 15)
    r.log('horse: mounted', 'horse-mounted', {'horse': horse()})
    breeds = json.loads((DATA / 'horses' / 'roster.json').read_text())['breed_order']
    resolved = []
    for breed in breeds:
        s = fields(value(f'unreal.YorimichiLive.horse_configure({breed!r})'))
        assert s.get('breed') == breed, f'{breed} did not resolve: {s}'
        time.sleep(1.5)
        resolved.append(breed)
        r.log(f'horse: {breed}', f'horse-{breed}', {'horse': horse()})
    speeds = {}
    for gait, stick in (('walk', 'walk'), ('jog', 'run'), ('gallop', 'sprint')):
        drive(1, 0, stick)
        time.sleep(5)
        speeds[gait] = horse()['speed']
    press('sprint')
    time.sleep(4)
    speeds['sprint'] = horse()['speed']
    r.log('horse: sprinting', 'horse-sprint', {'horse': horse(), 'speeds': speeds})
    drive(0)
    r.wait(horse, lambda s: s['speed'] < 20, 20)
    press('horse')
    r.wait(horse, lambda s: s.get('state') == HORSE_STOWED, 15)
    time.sleep(1)
    line = r.log('horse: dismounted', 'horse-off', {'horse': horse()})
    order = list(speeds.values())
    result = {'breeds': resolved, 'speeds': speeds}
    assert all(b > a + 50 for a, b in zip(order, order[1:])), f'gaits not each faster: {result}'
    assert line['horse'].get('ground') == 1, f'not on the ground after dismounting: {line["horse"]}'
    return result


def check_sail(r, args):
    travel(r, 'cove', args.settle)
    beach = player()
    press('sailboat')
    s = r.wait(sail, lambda s: s.get('equipped') == 1, 10)
    r.log('sail: launched', 'sail-launch', {'sail': s})
    drive(1, 0, 'run')
    rows = sample(sail, 12)
    out = sail()
    sailed = math.dist(beach[:2], out['pos'][:2]) / 100
    r.log('sail: out at sea', 'sail-out', {'sail': out, 'sailed_m': round(sailed, 1)})
    # Come about and sail home; step off once the beach is close.
    reached = r.go(beach[0], beach[1], 600, timeout=60)
    rows += sample(sail, 1)
    for _ in range(10):
        press('sailboat')
        time.sleep(1)
        if sail().get('equipped') == 0:
            break
        drive(1, 0, 'walk')
        time.sleep(1)
        drive(0)
    time.sleep(1.5)
    line = r.log('sail: ashore', 'sail-ashore', {'sail': sail()})
    result = {'sailed_m': round(sailed, 1), 'top_speed': max(s['speed'] for s in rows), 'reached_beach': reached,
              'on_water': all(s['equipped'] == 1 and s['depth'] > 0 for s in rows)}
    assert sailed > 15, f'did not sail out: {result}'
    assert result['on_water'], f'off the water while sailing: {result}'
    assert line['sail']['equipped'] == 0 and line['sail']['ground'] == 1, f'not ashore: {line["sail"]}'
    return result


CHECKS = {'bike': check_bike, 'horse': check_horse, 'sail': check_sail}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--session', required=True, help='live session ID of the running slice game')
    parser.add_argument('--out', type=Path, default=REPO / 'build' / 'yorimichi_v2' / 'vehicles')
    parser.add_argument('--only', nargs='+', choices=sorted(CHECKS), default=list(CHECKS))
    parser.add_argument('--air', type=float, default=.1, help='share of bike samples allowed off the ground')
    parser.add_argument('--settle', type=float, default=15.0, help='seconds for a site to load after travel')
    args = parser.parse_args(argv)
    try:
        launched = launch_revision(args.session, REPO)
        source = revision(REPO, launched, 'session')  # refuse a moved checkout before driving the game
    except (OSError, ValueError, RuntimeError) as error:
        print(f'cannot bind the rides to their game: {error}', file=sys.stderr)
        return 2
    os.environ['ATELIER_LIVE_SESSION'] = args.session
    r = Review(args.out)
    py(HELPERS)
    report = {'session': args.session, 'revision': source, 'vehicles': {}}
    for name in args.only:
        try:
            report['vehicles'][name] = {'passed': True, **CHECKS[name](r, args)}
        except (AssertionError, TimeoutError) as error:
            report['vehicles'][name] = {'passed': False, 'failure': str(error)[:2000]}
            print('VEHICLE', name, 'FAILED', error, file=sys.stderr)
            py("live.drive(0); live.stop('vehiclego')")
            for button, read in (('bike', bike), ('horse', horse), ('sailboat', sail)):  # back on foot for the next
                state = read()
                if state.get('state') == 2 or state.get('equipped') == 1:
                    press(button)
                    time.sleep(3)
    report['passed'] = all(v['passed'] for v in report['vehicles'].values())
    (args.out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print('VEHICLES', 'PASSED' if report['passed'] else 'FAILED', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
