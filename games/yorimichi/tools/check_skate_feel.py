#!/usr/bin/env python3
"""Measure the skate feel (FSkateFeel / FeelTuning) on the native offline QA session.

Each case rides the same inputs with stock feel and with one value changed, and checks that the change does what the
menu says: the defaults are bit-exact with no feel at all, gravity keeps jump heights but stretches air time, a gentler
flick pops higher with a lower flick pace, rolling resistance and braking change the coast, and rail magnetism catches
a rail from farther. Requires SkateNative and the explicitly built test-only gameplay-session-cli
(Tests/build_native_session_cli.py --compile, under the render lock and memory guard). Results go to
build/yorimichi/skate-native/feel.
"""
import argparse
import json
import math
from pathlib import Path
import selectors
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
NATIVE_PACKAGE = ROOT / 'games/yorimichi/unreal/Content/Data/SkateNative'
BINARY = ROOT / 'build/skate-native-session-cli' / ('gameplay-session-cli.exe' if sys.platform == 'win32' else 'gameplay-session-cli')
OUTPUT = ROOT / 'build/yorimichi/skate-native/feel'
FLAT = [[[-200, 0, -200], [-200, 0, 200], [200, 0, 200]], [[-200, 0, -200], [200, 0, 200], [200, 0, -200]]]
FLAT_WORLD = {'triangles': FLAT, 'rails': [], 'spawn': [0, 0, 0], 'heading': 0}
PUSH, BRAKE = 0x1000, 0x2000


class Session:
    """A gameplay-session-cli process over a world: activate with a feel, then step 60 Hz frames. A session's state
    carries over from one ride to the next, so every ride after the first starts a fresh process."""

    def __init__(self, binary, package, world, name):
        self.command = [str(binary), str(package), str(OUTPUT / f'{name}.json')]
        (OUTPUT / f'{name}.json').write_text(json.dumps(world))
        self.log = (OUTPUT / f'{name}.log').open('w')
        self.start()

    def start(self):
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                     text=True, bufsize=1)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        self.ready = self.read()
        assert self.ready['type'] == 'ready'
        self.deck = self.ready['names'].index('SKATEBOARD_ROOT')
        self.generation = 0

    def stop(self):
        try:
            self.send('quit')
            self.proc.wait(timeout=10)
        finally:
            self.selector.close()
            if self.proc.poll() is None:
                self.proc.terminate()
                self.proc.wait(timeout=10)

    def read(self):
        if not self.selector.select(60):
            raise TimeoutError('No native QA response within 60 seconds')
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError('Native QA exited; see its log in ' + str(OUTPUT))
        result = json.loads(line)
        if result['type'] == 'error':
            raise RuntimeError(result['message'])
        return result

    def send(self, op, **values):
        self.proc.stdin.write(json.dumps({'op': op, **values}) + '\n')
        self.proc.stdin.flush()

    def ride(self, frames, controls, feel=None, velocity=(0, 0, 0), spawn=(0, 0, 0), difficulty='normal'):
        """Rows of every frame, from a fresh session; controls(frame) gives (buttons, left, right)."""
        if self.generation:
            self.stop()
            self.start()
        self.generation += 1
        extra = {} if feel is None else {'feel': feel}
        self.send('activate', spawn=list(spawn), heading=0, goofy=False, difficulty=difficulty, trucks=.5,
                  generation=self.generation, velocity=list(velocity), **extra)
        self.read()
        rows = []
        for frame in range(frames):
            buttons, left, right = controls(frame)
            self.send('step', dt=1 / 60, buttons=buttons, left=left, right=right, triggers=[0, 0])
            rows.append(self.read())
        return rows

    def deck_height(self, row):
        a, b = row['root'], row['bones'][self.deck]
        return sum(a[k * 4 + 1] * b[3 * 4 + k] for k in range(4))

    def close(self):
        try:
            self.stop()
        finally:
            self.log.close()


def speed(row):
    return math.hypot(row['velocity'][0], row['velocity'][2])


def flick(load, snap):
    """A straight ollie: the stick held down from frame 150 for `load` frames, then up over `snap` frames."""
    def controls(frame):
        if 150 <= frame < 150 + load:
            return 0, [0, 0], [0, -32767]
        if 150 + load <= frame < 150 + load + snap:
            t = (frame - 150 - load + 1) / snap
            return 0, [0, 0], [0, int(-32767 + 65534 * t)]
        return 0, [0, 0], [0, 0]
    return controls


def jump(session, feel, load=18, snap=2):
    rows = session.ride(330, flick(load, snap), feel, velocity=(0, 0, 5))
    air = [r for r in rows if 'Air' in r['state']]
    return {'height_m': max(session.deck_height(r) for r in rows), 'airtime_s': len(air) / 60,
            'bailed': any('Wipeout' in r['state'] for r in rows), 'states': sorted({r['state'] for r in rows})}


def coast(session, feel, buttons=0, seconds=3, start=6):
    rows = session.ride(int(seconds * 60), lambda frame: (buttons, [0, 0], [0, 0]), feel, velocity=(0, 0, start))
    return {'end_speed_mps': speed(rows[-1]), 'distance_m': rows[-1]['root'][14] - rows[0]['root'][14]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-package', type=Path, default=NATIVE_PACKAGE)
    parser.add_argument('--binary', type=Path, default=BINARY, help='Already built offline native QA executable')
    args = parser.parse_args()
    if not args.binary.is_file():
        parser.error('Native QA executable is missing; build Tests/build_native_session_cli.py --compile under the render lock and memory guard first')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report, failures = {}, []

    def check(name, ok, detail):
        report.setdefault('checks', {})[name] = {'ok': bool(ok), 'detail': detail}
        if not ok:
            failures.append(name)

    flat = Session(args.binary, args.native_package, FLAT_WORLD, 'flat')
    try:
        # Stock feel, spelled out, is the session with no feel at all, bit for bit.
        ones = {k: 1 for k in ('flick_radius', 'flick_window', 'flick_pace', 'gravity', 'boneless', 'hippy',
                               'rail_magnetism', 'grind_pop', 'grind_friction', 'braking', 'steering', 'carve', 'grip',
                               'powerslide', 'rolling_friction', 'hill_speed', 'pump', 'wobble', 'wobble_onset',
                               'manual_drift', 'landing', 'impact')}
        ones.update(auto_push=-1, assisted_air=-1)
        rides = [flat.ride(330, flick(18, 2), feel, velocity=(0, 0, 5)) for feel in (None, ones)]
        same = all(a['root'] == b['root'] and a['bones'] == b['bones'] and a['velocity'] == b['velocity'] for a, b in zip(*rides))
        check('defaults_exact', same, 'stock feel spelled out matches no feel over 330 frames, bit for bit')

        stock = jump(flat, None)
        report['stock_ollie'] = stock
        check('stock_ollie', not stock['bailed'] and stock['airtime_s'] > .3, stock)

        # Gravity: the height stays, the air time goes as 1/sqrt(gravity).
        report['gravity'] = {}
        for g in (.7, .85, 1.25):
            result = jump(flat, {'gravity': g})
            result['airtime_ratio'] = result['airtime_s'] / stock['airtime_s']
            result['expected_ratio'] = 1 / math.sqrt(g)
            report['gravity'][str(g)] = result
            check(f'gravity_{g}_height', abs(result['height_m'] - stock['height_m']) < .06 * stock['height_m'] + .02, result)
            check(f'gravity_{g}_airtime', abs(result['airtime_ratio'] - result['expected_ratio']) < .08 and not result['bailed'], result)

        # Flick pace: a slow snap (12 frames) pops higher with a lower pace, lower with a higher one.
        slow = {str(p): jump(flat, {'flick_pace': p}, snap=12) for p in (.6, 1, 1.6)}
        report['flick_pace_slow_snap'] = slow
        check('flick_pace_order', slow['0.6']['height_m'] >= slow['1']['height_m'] >= slow['1.6']['height_m']
              and slow['0.6']['height_m'] > slow['1.6']['height_m'], slow)

        # Rolling resistance: the board holds its cruising speed on the flat, and rolling resistance bleeds off the speed
        # above it, so coast from 14 m/s. Then braking.
        rolling = {str(f): coast(flat, {'rolling_friction': f}, seconds=5, start=14) for f in (0, .5, 1, 2)}
        report['rolling_friction'] = rolling
        check('rolling_friction_order', rolling['0']['end_speed_mps'] >= rolling['0.5']['end_speed_mps']
              >= rolling['1']['end_speed_mps'] >= rolling['2']['end_speed_mps']
              and rolling['0']['end_speed_mps'] > rolling['2']['end_speed_mps'] + 1, rolling)
        braking = {str(b): coast(flat, {'braking': b}, buttons=BRAKE, seconds=1.5) for b in (.5, 1, 2)}
        report['braking'] = braking
        check('braking_order', braking['0.5']['distance_m'] >= braking['1']['distance_m'] >= braking['2']['distance_m']
              and braking['0.5']['distance_m'] > braking['2']['distance_m'], braking)
    finally:
        flat.close()

    # Rail magnetism: a 40 cm rail beside the line of travel, from close (stock grinds) to beyond stock's reach. More
    # magnetism grinds from farther, less from nearer.
    report['rail'] = {}
    for offset in (1.5, 2, 2.5, 3, 3.5):
        rail = [[offset, .4, -20], [offset, .4, 60]]
        session = Session(args.binary, args.native_package,
                          {'triangles': FLAT, 'rails': [rail], 'spawn': [0, 0, 0], 'heading': 0}, f'rail_{offset}')
        try:
            row = {}
            for magnetism in (.5, 1, 2, 3):
                rows = session.ride(330, flick(18, 2), {'rail_magnetism': magnetism}, velocity=(0, 0, 5))
                row[str(magnetism)] = any('Grind' in r['state'] for r in rows)
            report['rail'][str(offset)] = row
        finally:
            session.close()
    rails = report['rail']
    widened = any(not r['1'] and (r['2'] or r['3']) for r in rails.values())
    narrowed = any(r['1'] and not r['0.5'] for r in rails.values())
    monotonic = all(not (r['1'] and not r['3']) and not (r['0.5'] and not r['1']) for r in rails.values())
    check('rail_magnetism_widens', widened and monotonic, rails)
    check('rail_magnetism_narrows', narrowed and monotonic, rails)

    report['passed'] = not failures
    report['failures'] = failures
    (OUTPUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
