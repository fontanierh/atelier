#!/usr/bin/env python3
"""Measure the skate feel (FSkateFeel / FeelTuning) on the native offline QA session.

Each case rides the same inputs with stock feel and with one value changed, and checks that the change does what the
menu says: the defaults are bit-exact with no feel at all, gravity keeps jump heights but stretches air time, a gentler
flick pops higher with a lower flick pace, the 120 Hz flick reading reads the same flicks with the same window and pace
and keeps a fast hardflip's bottom point that 60 Hz misses, rolling resistance and braking change the coast, and rail magnetism catches
a rail from farther. Requires the assembled native package (skate.runtime) and the explicitly built test-only gameplay-session-cli
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
NATIVE_PACKAGE = ROOT / 'build/yorimichi/skate-native/package'  # atelier build yorimichi skate.runtime
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
        """Rows of every frame, from a fresh session; controls(frame) gives (buttons, left, right), or with the frame's
        120 Hz stick readings after them (with_readings)."""
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
            buttons, left, right, *readings = controls(frame)
            extra = {'readings': readings[0]} if readings else {}
            self.send('step', dt=1 / 60, buttons=buttons, left=left, right=right, triggers=[0, 0], **extra)
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


def arc(angles):
    """A flip flick from frame 150 through stick angles in degrees (0 right, 90 up): out to the first, round to each
    middle one, then a straight snap to the last."""
    point = lambda degrees, r=1.: (r * math.cos(math.radians(degrees)), r * math.sin(math.radians(degrees)))
    path = [point(angles[0], k / 3) for k in (1, 2, 3)] + [point(angles[0])] * 4
    for a, b in zip(angles[:-2], angles[1:-1]):
        path += [point(a + (b - a) * k / 5) for k in range(1, 6)]
    (ax, ay), (bx, by) = point(angles[-2]), point(angles[-1])
    path += [(ax + (bx - ax) * k / 3, ay + (by - ay) * k / 3) for k in (1, 2, 3)] + [point(angles[-1])] * 2
    def controls(frame):
        if 150 <= frame < 150 + len(path):
            x, y = path[frame - 150]
            return 0, [0, 0], [round(x * 32767), round(y * 32767)]
        return 0, [0, 0], [0, 0]
    return controls


def with_readings(controls, half=None):
    """controls with the host's 120 Hz stick readings: each frame's sticks half a frame before its end (half(frame),
    by default midway from the last frame's) and at its end. Ages sit a hair past each tick's end, as a reading taken
    just before it would be."""
    def stick(frame):
        buttons, left, right = controls(frame)[:3]
        return left + right
    def fine(frame):
        buttons, left, right = controls(frame)[:3]
        middle = half(frame) if half else [round((a + b) / 2) for a, b in zip(stick(frame - 1), left + right)]
        return buttons, left, right, [[1 / 120 + 1e-4, *middle], [1e-4, *left, *right]]
    return fine


def traced(path, start=150):
    """A right-stick flick traced at 120 Hz from frame `start`: the frame's sticks are every second point, the
    readings half a frame before them the points between."""
    stick = lambda p: [round(p[0] * 32767), round(p[1] * 32767)]
    point = lambda k: path[k] if 0 <= k < len(path) else (0, 0)
    controls = lambda frame: (0, [0, 0], stick(point(2 * (frame - start) + 1)))
    return with_readings(controls, lambda frame: [0, 0, *stick(point(2 * (frame - start)))])


def sampled(stick, phase):
    """A continuous right stick, stick(t) in frames, read at frame ends `phase` of a frame late: each frame's packet
    and the 120 Hz reading half a frame before it."""
    to = lambda p: [round(p[0] * 32767), round(p[1] * 32767)]
    return with_readings(lambda frame: (0, [0, 0], to(stick(frame - phase))),
                         lambda frame: [0, 0, *to(stick(frame - .5 - phase))])


def stretched(controls, by, start=150):
    """controls slowed `by` times from frame `start`, each stick moving linearly between the original frames."""
    def slow(frame):
        if frame < start:
            return controls(frame)
        at = start + (frame - start) / by
        (b, l0, r0), (_, l1, r1) = controls(math.floor(at))[:3], controls(math.floor(at) + 1)[:3]
        t = at - math.floor(at)
        mix = lambda p, q: [round(a + (c - a) * t) for a, c in zip(p, q)]
        return b, mix(l0, l1), mix(r0, r1)
    return slow


def first_trick(session, controls, feel):
    """The trick named on the frame the board leaves the ground (the label sticks afterwards)."""
    rows = session.ride(240, controls, feel, velocity=(0, 0, 5))
    for before, row in zip(rows, rows[1:]):
        if 'Air' in row['state'] and 'Air' not in before['state']:
            return row['trick'].replace('ID_TRICK_FLIP_', '') or 'blank'
    return 'none'


def takeoff_trick(session, angles, feel):
    return first_trick(session, arc(angles), feel)


def jump(session, feel, load=18, snap=2, fine=False):
    controls = flick(load, snap)
    rows = session.ride(330, with_readings(controls) if fine else controls, feel, velocity=(0, 0, 5))
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
        ones.update(auto_push=-1, assisted_air=-1, tight_flicks=0, flick_120hz=0)
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

        # Tight flicks: a hardflip or inward heelflip flicked close to straight down then up (regular stance) reads as the
        # flip with the switch on; the authored wide arcs and a straight ollie read the same either way.
        flips = {'tight_hardflip': ([-110, -88, 112], 'HARDFLIP'), 'tight_inward_heelflip': ([-70, -92, 68], 'INWARD_HEELFLIP'),
                 'hardflip': ([-138, -82, 128], 'HARDFLIP'), 'inward_heelflip': ([-42, -98, 41], 'INWARD_HEELFLIP'),
                 'ollie': ([-90, 90], 'OLLIE')}
        tight = {name: {str(on): takeoff_trick(flat, angles, {'tight_flicks': on}) for on in (0, 1)}
                 for name, (angles, _) in flips.items()}
        report['tight_flicks'] = tight
        check('tight_flicks_read', all(tight[name]['1'] == trick for name, (_, trick) in flips.items()), tight)
        check('tight_flicks_keep_authored', all(tight[name]['0'] == trick for name, (_, trick) in flips.items()
                                                if not name.startswith('tight')), tight)

        # 120 Hz flicks: every flick above reads as at 60 Hz, from the host's readings between frames or (no readings:
        # another platform, injected input) from each frame's packet (read once a tick), with tight flicks off and on.
        fine = {}
        for name, (angles, _) in flips.items():
            for on in (0, 1):
                feel = {'tight_flicks': on, 'flick_120hz': 1}
                fine[f'{name}_{on}'] = {'readings': first_trick(flat, with_readings(arc(angles)), feel),
                                        'packet': first_trick(flat, arc(angles), feel), '60hz': tight[name][str(on)]}
        report['flick_120hz_tricks'] = fine
        check('flick_120hz_same_tricks', all(r['readings'] == r['60hz'] and r['packet'] == r['60hz'] for r in fine.values()), fine)

        # The window is a time at either rate: a hardflip slowed down reads at the same windows at 60 and 120 Hz,
        # and more window reads slower flicks.
        slowed = {}
        for by in (2, 3, 4):
            for window in (.5, 1, 2, 3):
                feel = {'flick_window': window}
                controls = stretched(arc(flips['hardflip'][0]), by)
                slowed[f'x{by}_{window}'] = {'60hz': first_trick(flat, controls, feel),
                                             '120hz': first_trick(flat, with_readings(controls), {**feel, 'flick_120hz': 1})}
        report['flick_120hz_window'] = slowed
        reads = lambda rate, by: [slowed[f'x{by}_{w}'][rate] == 'HARDFLIP' for w in (.5, 1, 2, 3)]
        check('flick_120hz_window_matches', all(reads('120hz', by) == reads('60hz', by) for by in (2, 3, 4)), slowed)
        check('flick_120hz_window_order', all(reads('120hz', by) == sorted(reads('120hz', by)) for by in (2, 3, 4))
              and any(not all(reads('120hz', by)) and any(reads('120hz', by)) for by in (2, 3, 4)), slowed)

        # The pace is a time too: read from the packet, a flick pops exactly as high at either rate; from the readings
        # its ends are found up to half a tick apart from 60 Hz's, so close to it; and a lower pace pops a slow snap
        # higher.
        paced = {f'{p}_{snap}': {'60hz': jump(flat, {'flick_pace': p}, snap=snap)['height_m'],
                                 '120hz_packet': jump(flat, {'flick_pace': p, 'flick_120hz': 1}, snap=snap)['height_m'],
                                 '120hz': jump(flat, {'flick_pace': p, 'flick_120hz': 1}, snap=snap, fine=True)['height_m']}
                 for p in (.6, 1, 1.6) for snap in (2, 12)}
        report['flick_120hz_pace'] = paced
        check('flick_120hz_pace_matches', all(r['120hz_packet'] == r['60hz'] and abs(r['120hz'] - r['60hz']) <= .12 * r['60hz']
                                              for r in paced.values()), paced)
        # On average over where a flick falls between frames, it pops as high at either rate (the tick count is unbiased).
        def snap_over(frames):
            return lambda t: (0, -1) if 150 <= t < 168 else (0, min(1, -1 + 2 * (t - 168) / frames)) if 168 <= t < 168 + frames + 1 else (0, 0)
        phases = [k / 8 for k in range(8)]
        unbiased = {}
        for frames in (6, 9):
            rides = {rate: [max(flat.deck_height(r) for r in flat.ride(330, sampled(snap_over(frames), phase), feel, velocity=(0, 0, 5)))
                            for phase in phases] for rate, feel in (('60hz', None), ('120hz', {'flick_120hz': 1}))}
            unbiased[str(frames)] = {rate: sum(h) / len(h) for rate, h in rides.items()}
        report['flick_120hz_pace_unbiased'] = unbiased
        check('flick_120hz_pace_unbiased', all(abs(r['120hz'] - r['60hz']) <= .04 * r['60hz'] for r in unbiased.values()), unbiased)
        check('flick_120hz_pace_order', paced['0.6_12']['120hz'] >= paced['1_12']['120hz'] >= paced['1.6_12']['120hz']
              and paced['0.6_12']['120hz'] > paced['1.6_12']['120hz'], paced)

        # A hardflip flicked in a sixtieth of a second through its bottom: the stick passes straight down between two
        # frames, so 60 Hz never sees it, and the 120 Hz readings do.
        point = lambda degrees, r=1.: (r * math.cos(math.radians(degrees)), r * math.sin(math.radians(degrees)))
        quick = [point(-138, r) for r in (.25, .5, .75)] + [point(-138)] * 5 + [point(-82)]
        (ax, ay), (bx, by) = point(-82), point(128)
        quick += [(ax + (bx - ax) * k / 2, ay + (by - ay) * k / 2) for k in (1, 2)] + [point(128)] * 5
        fast = {'60hz': first_trick(flat, traced(quick), {'tight_flicks': 1}),
                '120hz': first_trick(flat, traced(quick), {'tight_flicks': 1, 'flick_120hz': 1}),
                '120hz_packet': first_trick(flat, lambda frame: traced(quick)(frame)[:3], {'tight_flicks': 1, 'flick_120hz': 1})}
        report['flick_120hz_fast_hardflip'] = fast
        check('flick_120hz_fast_hardflip', fast['120hz'] == 'HARDFLIP' and fast['60hz'] != 'HARDFLIP'
              and fast['120hz_packet'] == fast['60hz'], fast)

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
