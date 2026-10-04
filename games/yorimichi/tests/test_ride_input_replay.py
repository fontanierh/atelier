"""Ride's Flick-It (Native's own controls through Ride's adapter), offline: the owner's car park take and the scripted
gestures the game's scenarios and films play.

The Skate plugin's ride_input_replay_probe packs each recorded row of carpark-1 with the host's packer
(Private/SkatePad.h) and checks it against the packet the Native backend sent, then steps Ride's adapter
(Private/Ride/RideFlick.cpp) and Native's ControllerInputRuntime and PlayerControls, scheduled as GameplaySession
schedules them, one packet per tick over the whole take. Every tick is compared bit for bit: the 26 controller words, the
intentions before and after the gestures, every recognizer's match, GestureSpeed, the held pattern and the trick mapped
under each pinned stance. Over the same take Ride's manual (Private/Ride/RideManual.cpp, Native's controller) runs on
the adapter's intentions and Native's own ground, and starts and ends where Native's did. The recording lives in the
ignored build folder; without it those tests skip.

In its script mode the probe plays skate.input as the scenarios drive it (yorimichi_live's FLICKS at the live helper's,
the QA scenarios' and the Mega Park film's timings, the film's rail, grind and manual inputs, skate_ride's pad nollies)
through the same adapter beside Native's owners, and Ride's manual on them. Without a C++ compiler everything skips.
"""
import ast
import json
import math
import re
import shutil
import struct
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
TAKE = REPO / 'build/yorimichi/ride-record/carpark-1'
LIVE = GAME / 'live/python/yorimichi_live.py'
SKATE_RIDE = GAME / 'scenarios/skate_ride.py'
BUNDLE = GAME / 'unreal/Content/Data/SkateNative'
PLUGIN = REPO / 'platform/engine/Plugins/Activities/Skate'
PRIVATE = PLUGIN / 'Source/AtelierSkate/Private'
PROBE = PLUGIN / 'Tests/Native/ride_input_replay_probe.cpp'
# The probe, Ride's adapter and manual, and the Native sources they reach.
SOURCES = [PROBE, PRIVATE / 'Ride/RideFlick.cpp', PRIVATE / 'Ride/RideManual.cpp'] + [
    PRIVATE / 'Native' / (name + '.cpp') for name in (
        'AggregateMass', 'AnimationName', 'BoardPhysicsSettings', 'BodyMass', 'ConstraintFrames', 'ControllerInputRuntime',
        'DeckGeometry', 'DriveBuild', 'DriveFrames', 'GestureInputPublication', 'Gestures', 'GraphGestureOperations',
        'GroundControlSettings', 'Input', 'InputIntentions', 'Intents', 'Manual', 'NameId', 'NativeMath', 'PlayerControls',
        'RigidBody', 'Settings')]
# Unreal's own float settings: no contraction, no fast math (UnrealBuildTool's Mac and Clang toolchains).
FLAGS = ['-std=c++20', '-O1', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti', f'-I{PRIVATE}']

# The guide's first event: the reconstructed canonical right stick, frames 144-159 (port-map.md section 8).
FIRST_STICK = {144: (-15583, 15099), 145: (-19934, 18681), 146: (-24428, 24170), 147: (-22951, 26841),
               148: (-18045, 30767), 149: (-11002, 32767), 150: (0, 32767), 151: (11265, 32767), 152: (17552, 31594),
               153: (21510, 30114), 154: (25167, 27254), 155: (15587, 9962), 156: (0, 0), 157: (-21670, -28158),
               158: (-23360, -20552), 159: (0, 0)}
# The main recognizer's matches over the take (pattern index, name) and the tricks the goofy rider's mapping gives.
MAIN = {157: (23, 'N_InwardHeelflip'), 346: (1, 'Kickflip'), 446: (17, 'N_Heelflip'), 741: (30, 'Ollie'),
        992: (30, 'Ollie'), 1242: (1, 'Kickflip')}
# Ride's manuals over the take: (row, side) where one started (-1 tail, 1 nose) or ended (0).
MANUALS = [(211, -1), (246, 0), (408, 1), (445, 0)]


def bits(value):
    out = struct.unpack('<I', struct.pack('<f', value))[0]
    assert struct.unpack('<f', struct.pack('<I', out))[0] == value, value     # recorded values are binary32
    return out


def real(word):
    return struct.unpack('<f', struct.pack('<I', int(word, 16)))[0]


def call(*command):
    done = subprocess.run([str(c) for c in command], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-4000:]
    return done.stdout


def field(row, key):
    found = re.search(r'\b' + key + r'=(\S+)', row['s'])
    return found.group(1) if found else None


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('no clang++')
    folder = tmp_path_factory.mktemp('ride-input-replay')

    def build(source):
        out = folder / (source.stem + '.o')
        call(compiler, *FLAGS, '-c', source, '-o', out)
        return out

    with ThreadPoolExecutor(8) as pool:
        objects = list(pool.map(build, SOURCES))
    binary = folder / 'ride_input_replay_probe'
    call(compiler, *objects, '-o', binary)
    return binary, folder


def rows_file(folder, rows, prefix, name):
    """The probe's rows: k, the six axes' bits, the button mask, dt's bits, whether the ride was rolling before the
    frame (mode 1, the powerslide's condition), the packet Native sent when there is one, then Native's own state after
    the frame for Ride's manual: rolling, pushing and the speed's bits (cm/s)."""
    lines = [f'prefix {prefix}']
    for i, row in enumerate(rows):
        before = rows[i - 1] if i else row
        pad = re.search(r'\bpad=([0-9a-f]+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+),(-?\d+)', row['s'])
        packet = [pad.group(1), *pad.groups()[1:]] if pad else ['0'] * 7
        lines.append(' '.join([str(row['k']), *(f'{bits(a):08x}' for a in row['ax']), str(row['b']),
                               f'{bits(row["dt"]):08x}', '1' if field(before, 'mode') == '1' else '0',
                               '1' if pad else '0', *packet, '1' if field(row, 'mode') == '1' else '0',
                               '1' if field(row, 'push') not in (None, '0') else '0',
                               f'{bits(float(field(row, "speed") or 0)):08x}']))
    path = folder / name
    path.write_text('\n'.join(lines) + '\n')
    return path


def run(probe, rows, prefix, name):
    binary, folder = probe
    path = rows_file(folder, rows, prefix, name)
    out = call(binary, BUNDLE / 'settings.skate', BUNDLE / 'gestures.skate', path)
    result = {'pad': {}, 'rec': [], 'trick': {}, 'manual': [], 'flag': [], 'brake': [], 'deck': {}, 'diff': [], 'summary': {}}
    for line in out.splitlines():
        kind, *words = line.split(' ')
        if kind in ('manual', 'flag', 'brake'):
            result[kind].append((int(words[0]), int(words[1])))
        elif kind == 'deck':
            result['deck'][int(words[0])] = (float(words[1]), float(words[2]))
        elif kind == 'pad':
            result['pad'][int(words[0])] = (int(words[1], 16), *map(int, words[2:]))
        elif kind == 'rec':
            k, group, pattern, name, strength, distance, elapsed, permitted = words
            result['rec'].append(dict(k=int(k), set=int(group), pattern=int(pattern), name=name, strength=real(strength),
                                      distance=real(distance), elapsed=real(elapsed), permitted=permitted == '1',
                                      bits=(strength, distance, elapsed)))
        elif kind == 'trick':
            k, speed, unmirrored, mirrored, goofy, regular, _, _ = words
            result['trick'][int(k)] = dict(speed=real(speed), unmirrored=unmirrored, mirrored=mirrored, goofy=goofy,
                                           regular=regular)
        elif kind == 'diff':
            result['diff'].append(line)
        elif kind == 'summary':
            result['summary'] = {key: value for key, value in (word.split('=') for word in words)}
    return result


@pytest.fixture(scope='module')
def take():
    if not TAKE.joinpath('frames.jsonl').exists():
        pytest.skip('no carpark-1 recording in build/')
    rows = [json.loads(line) for line in TAKE.joinpath('frames.jsonl').read_text().splitlines() if line.strip()]
    return rows


@pytest.fixture(scope='module')
def replay(probe, take):
    # Row 0 is the capture boundary, the session's tick `tick`: the mount activated a fresh session with five neutral
    # ticks (GameplaySession::Activate), then the settle held the pad neutral until row 0.
    prefix = int(field(take[0], 'tick')) - 1 - 5
    assert prefix >= 0
    return run(probe, take, prefix, 'rows.txt')


def test_the_whole_take_is_replayed(take, replay):
    assert [row['k'] for row in take] == list(range(len(take))) and len(take) == 1573
    s = replay['summary']
    assert int(s['rows']) == 1573 and int(s['ticks']) == 1573 + int(s['prefix'])
    assert s['step'] == '3c888889'                # Native's 1/60 s board step


def test_host_packets_match_what_native_sent(replay):
    s = replay['summary']
    # Rows 1461 on are on foot (the Native backend sent nothing).
    assert int(s['pad_rows']) == 1461 and s['pad_same'] == s['pad_rows'] and s['first_pad_diff'] == '-1'
    for k, (rx, ry) in FIRST_STICK.items():
        assert replay['pad'][k][5:7] == (rx, ry), k


def test_adapter_matches_native_bit_for_bit(replay):
    s = replay['summary']
    assert not replay['diff'], replay['diff']
    for key in ('words', 'conditioned', 'pre_intents', 'trace', 'intents', 'speed', 'held', 'mapping', 'stance'):
        assert s[key] == '0', key


def test_main_recognitions_over_the_take(replay):
    main = {r['k']: r for r in replay['rec'] if r['set'] == 0 and r['permitted']}
    assert {k: (r['pattern'], r['name']) for k, r in main.items()} == MAIN
    # Nothing on the first gesture's releases, and a trick only where the main recognizer matched (frame 152's
    # rotated-90 heelflip publishes a GestureSpeed that no ground trick maps).
    assert 156 not in replay['trick'] and 159 not in replay['trick']
    assert sorted(k for k, t in replay['trick'].items() if t['unmirrored'] != '-') == sorted(MAIN)
    assert all(t['goofy'] == t['regular'] == '-' for k, t in replay['trick'].items() if k not in MAIN)
    first = main[157]
    assert first['elapsed'] == 9 and first['distance'] == pytest.approx(.197971, abs=2e-6)
    assert first['strength'] == pytest.approx(.5283019, abs=1e-7)


def test_mapping_under_pinned_stances(replay):
    tricks = replay['trick']
    # The goofy rider of the take maps unmirrored; a regular one would map the same gesture mirrored.
    assert [tricks[k]['goofy'] for k in sorted(MAIN)] == ['N_InwardHeelflip', 'Kickflip', 'N_Heelflip', 'Ollie',
                                                          'Ollie', 'Kickflip']
    assert (tricks[157]['unmirrored'], tricks[157]['mirrored']) == ('N_InwardHeelflip', 'N_Hardflip')
    assert (tricks[157]['goofy'], tricks[157]['regular']) == ('N_InwardHeelflip', 'N_Hardflip')


def test_frame_446_needs_the_history_from_372(probe, take, replay):
    # The third trick's gesture starts before its manual: replayed from frame 372 on, a fresh mount's controls give
    # frame 446 the same match, to the bit, as the whole take does.
    later = run(probe, take[372:], 0, 'rows-372.txt')
    assert not later['diff'], later['diff']
    full = [r for r in replay['rec'] if r['k'] == 446 and r['set'] == 0]
    part = [r for r in later['rec'] if r['k'] == 446 and r['set'] == 0]
    assert part and [r['bits'] for r in part] == [r['bits'] for r in full]


def test_manuals_over_the_take(take, replay):
    # Ride's manual, on the adapter's intentions over Native's ground, starts on Native's rows: 211 on the landing tick
    # (the Manual intention counted its 0.2 s in the air) and 408. Each ends on the row the intention goes, a row before
    # Native's published balance clears: the Native backend's worker hands back the step it took a frame earlier
    # (SkateRuntime polls before it sends the frame's pad), so its state rows are a frame behind its pad rows. From 909 to 1004 the stick passed 0.9 first, so Idle went into its
    # anticipation and no manual starts (U80), as in Native.
    assert replay['manual'] == MANUALS
    assert [row['k'] for row in take if field(row, 'manual') == '1'] == list(range(211, 247)) + list(range(408, 446))
    # Both carry their balance at once: the nose manual was landed from the air, straight into its cycle.
    assert replay['flag'] == [(211, 1), (246, 0), (408, 1), (445, 0)]
    # Native's controller tips the deck toward the side held (nose up on the tail), never past its brake angle, and
    # nothing in it throws the rider off.
    tail = [replay['deck'][k] for k in range(211, 246)]
    nose = [replay['deck'][k] for k in range(408, 445)]
    assert all(0 <= a < 30 and 0 < target <= 30 for a, target in tail) and tail[-1][0] > 5
    assert all(-30 < a <= 0 and -30 <= target < 0 for a, target in nose) and nose[-1][0] < -10


# ------------------------------------------------------------------------------------------------ scripted gestures
SQUARE, NOSE, TAIL = 0, 1, 2      # GraphGestureOperations' GestureGroup: a ground or manual flick, a nose or tail grind's
GROUND = 64                       # the probe's flag: the board rolling (push 1, brake 2, grab left 16, grab right 32)
# yorimichi_live's FLICKS names and the trick Native maps each to.
NATIVE = {'ollie': 'Ollie', 'nollie': 'Nollie', 'kickflip': 'Kickflip', 'heelflip': 'Heelflip', 'shove': 'PopShuvit',
          'fs_shove': 'FSPopShuvit', '360_shove': '360PopShuvit', 'fs_360_shove': 'FS360PopShuvit',
          'varial_kickflip': 'VarialKickflip', 'varial_heelflip': 'VarialHeelflip', 'hardflip': 'Hardflip',
          'inward_heelflip': 'InwardHeelflip', '360_flip': '360Flip', 'laser_flip': 'Laserflip',
          '360_hardflip': '360Hardflip', '360_inward_heelflip': '360InwardHeelflip'}


def literal(path, name):
    """A module-level literal assignment of a scenario file, without importing it (it runs in the game)."""
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == name:
            return ast.literal_eval(node.value)
    raise KeyError(name)


# The live helpers' paths in regular stance (yorimichi_live mirrors the recovered ones' x).
FLICKS = {name: [(-x, y) for x, y in points] for name, points in literal(LIVE, 'FLICKS').items()}


class Script:
    """skate.input, one 60 Hz tick per line, after a mount."""
    def __init__(self):
        self.lines = ['script', 'mount']
        self.ticks = 0

    def tick(self, right=(0., 0.), left=(0., 0.), flags=GROUND, group=SQUARE, goofy=False):
        self.lines.append(f'tick {float(left[0])!r} {float(left[1])!r} {float(right[0])!r} {float(right[1])!r} '
                          f'{flags} {group} {int(goofy)}')
        self.ticks += 1
        return self

    def hold(self, count, right=(0., 0.), **kw):
        for _ in range(count):
            self.tick(right, **kw)
        return self

    def play(self, sticks, **kw):
        for right in sticks:
            self.tick(right, **kw)
        return self


def play(probe, script):
    binary, folder = probe
    path = folder / 'script.txt'
    path.write_text('\n'.join(script.lines) + '\n')
    out = call(binary, BUNDLE / 'settings.skate', BUNDLE / 'gestures.skate', path)
    result = {'flicks': [], 'manual': [], 'flag': [], 'brake': [], 'deck': {}, 'diff': [], 'summary': {}}
    for line in out.splitlines():
        kind, *words = line.split(' ')
        if kind == 'flick':
            result['flicks'].append((int(words[0]), words[1]))
        elif kind in ('manual', 'flag', 'brake'):
            result[kind].append((int(words[0]), int(words[1])))
        elif kind == 'deck':
            result['deck'][int(words[0])] = (float(words[1]), float(words[2]))
        elif kind == 'diff':
            result['diff'].append(line)
        elif kind == 'summary':
            result['summary'] = {key: value for key, value in (word.split('=') for word in words)}
    # The adapter is Native's owners, to the bit, on scripted input too.
    assert not result['diff'] and all(v == '0' for k, v in result['summary'].items() if k not in ('ticks', 'tricks')), result
    return result


def film_flick(points, load, hz=60.):
    """megapark_ride_film's flick effect: the first point held `load` s, the others a 30th of a second each, at the
    frame rate (frames of 1/hz s; a tick runs on the input of the frame it falls in)."""
    frames, n = [], 0
    while True:
        u = n / hz
        if u < load:
            frames.append(points[0])
        else:
            j = 1 + int((u - load) * 30. + 1e-6)
            if j > len(points):
                break
            frames.append(points[j] if j < len(points) else (0., 0.))
        n += 1
    ticks, clock = [], 1. / 60. - 1e-8
    for frame in frames:
        clock += 1. / hz
        while clock >= 1. / 60.:
            ticks.append(frame); clock -= 1. / 60.
    return ticks


def skate_script(points, load, step, hz=60.):
    """skate_script's flick (live.flick, the QA scenarios): one step at most per frame, then the centre."""
    queue = [(load, points[0])] + [(step, p) for p in points[1:]] + [(.12, (0., 0.))]
    t, i, frames = 0., 0, []
    while True:
        if i < len(queue) and t >= queue[i][0]:
            t = max(0., t - queue[i][0]); i += 1
        if i >= len(queue):
            return [frame for frame in frames for _ in range(round(60. / hz))]
        frames.append(queue[i][1]); t += 1. / hz


def flicked(probe, sticks, goofy=False, **kw):
    """The tricks recognised over a gesture played from rest, as (ticks after its start, Native's trick)."""
    script = Script().hold(40, goofy=goofy, **kw)
    script.play(sticks, goofy=goofy, **kw).hold(40, goofy=goofy, **kw)
    return [(k - 40, name) for k, name in play(probe, script)['flicks']]


TIMINGS = {'film': lambda p: film_flick(p, .2), 'film 90 Hz': lambda p: film_flick(p, .2, 90.),
           'scenario': lambda p: skate_script(p, .16, .03), 'live.flick': lambda p: skate_script(p, .18, .03),
           'live.flick 30 fps': lambda p: skate_script(p, .18, .03, 30.)}


@pytest.mark.parametrize('timing', sorted(TIMINGS))
@pytest.mark.parametrize('goofy', [False, True])
def test_scripted_flicks_give_their_tricks(probe, timing, goofy):
    # Every live helper's gesture, as the stance in effect plays it (a goofy rider's stick mirrored), is its trick, once,
    # on the tick the stick reaches the path's last point.
    for name, points in FLICKS.items():
        path = [(-x, y) for x, y in points] if goofy else points
        sticks = TIMINGS[timing](path)
        got = flicked(probe, sticks, goofy)
        last = next(i for i, s in enumerate(sticks) if s == path[-1])
        assert got == [(last, NATIVE[name])], (name, got)


def test_film_flick_loads(probe):
    # megapark_ride_film's flicks with their own loads: road_flips' shove, the rail and grind ollies, the dismount.
    for name, load in (('shove', .16), ('ollie', .34), ('ollie', .33), ('ollie', .32), ('ollie', .3), ('ollie', .12),
                       ('ollie', .1)):
        assert [n for _, n in flicked(probe, film_flick(FLICKS[name], load))] == [NATIVE[name]], (name, load)


@pytest.mark.parametrize('held, group', [((0., -.55), TAIL), ((.52, .42), NOSE)])
def test_film_rail_stick_is_no_trick(probe, held, group):
    # The film's 5-0 and crooked: the rail ollie, then the right stick held from the air into the grind and let go a
    # moment after the lock-on. Only the ollie is a trick (in the air it would flip the board, in the grind pop out).
    script = Script().hold(40).play(film_flick(FLICKS['ollie'], .33)).hold(13)
    script.hold(30, held, flags=0).hold(12, held, flags=0, group=group).hold(90, flags=0, group=group).hold(40)
    assert [name for _, name in play(probe, script)['flicks']] == ['Ollie']


def test_film_grind_ollie(probe):
    # bowl_coping's and bail_grind's ollie out of a 50-50.
    for load in (.1, .12):
        assert [n for _, n in flicked(probe, film_flick(FLICKS['ollie'], load), flags=0)] == ['Ollie']


def test_film_holds_are_no_tricks(probe):
    # plaza_manuals' tail and nose manual holds, an air's spin and grabs, a powerslide on the left stick, and steering
    # with pushes and brakes: no trick, and the manual holds are Ride's tail and nose manuals.
    manuals = play(probe, Script().hold(42).hold(102, (0., -.5)).hold(36).hold(102, (0., .5)).hold(60))
    assert not manuals['flicks'] and [side for _, side in manuals['manual'] if side] == [-1, 1]
    script = Script().hold(20, flags=0)
    for mag in (.35, 1.):
        script.hold(40, left=(mag, 0.), flags=32).hold(20, left=(-mag, 0.), flags=16 | 2).hold(20, flags=0)
    script.hold(66, left=(-1., 0.), flags=GROUND | 8).hold(20)
    for k in range(600):
        script.tick(left=(max(-1., min(1., 1.3 * math.sin(k / 23.))), 0.),
                    flags=GROUND | (1 if (k // 40) % 3 == 0 else 0) | (2 if k % 97 < 10 else 0))
    assert not play(probe, script)['flicks']


def test_manual_graph(probe):
    # Native's manual graph on scripted sticks, a stick held from tick 30. Half way down it starts a tail manual once
    # the Manual intention has been held over 0.2 s (the 13th tick), and ends the tick the stick centres.
    def manuals(script):
        return play(probe, script)['manual']
    assert manuals(Script().hold(30).hold(40, (0., -.5)).hold(20)) == [(42, -1), (70, 0)]
    # Slammed past 0.9 first, Idle goes into its anticipation (the Antic state), which has no way into a manual.
    assert manuals(Script().hold(30).hold(5, (0., -1.)).hold(60, (0., -.5)).hold(20)) == []
    # The intention counts in the air: the manual starts on the landing tick. Pushing, Idle waits for the push's end.
    assert manuals(Script().hold(30).hold(20, (0., -.5), flags=0).hold(30, (0., -.5)).hold(20)) == [(50, -1), (80, 0)]
    assert manuals(Script().hold(30).hold(30, (0., -.5), flags=GROUND | 1).hold(30, (0., -.5)).hold(20)) == [(60, -1), (90, 0)]
    # Across the centre the manual changes side without ending.
    assert manuals(Script().hold(30).hold(30, (0., -.5)).hold(30, (0., .5)).hold(20)) == [(42, -1), (60, 1), (90, 0)]
    # Out past 0.9 in a manual is its brake: the controller's target goes to BrakeTiltAngle.
    brake = play(probe, Script().hold(30).hold(30, (0., -.5)).hold(30, (0., -1.)).hold(20))
    assert brake['manual'] == [(42, -1), (90, 0)]
    assert all(brake['deck'][k][1] < 24 for k in range(42, 60)) and all(brake['deck'][k][1] == 30 for k in range(61, 90))


def test_nose_manual_into_and_the_brake(probe):
    # A nose manual started on the ground plays NoseManual.Holding.Into first, which carries no balance: the published
    # balance comes 25 ticks after the start, as Native's does (carpark-1's manual_trick-02 window: stick at 41, the
    # combo label's Into at 54 and the balance at 79 on Native's rows, a frame behind its pad, so 53 and 78 here). Across from the tail it plays Into again; landed from the air it goes straight to Cycle.
    def run(script):
        out = play(probe, script)
        return out['manual'], out['flag'], out['brake']
    assert run(Script().hold(30).hold(60, (0., .5)).hold(20))[:2] == ([(42, 1), (90, 0)], [(67, 1), (90, 0)])
    assert run(Script().hold(30).hold(30, (0., -.5)).hold(40, (0., .5)).hold(20))[:2] == (
        [(42, -1), (60, 1), (100, 0)], [(42, 1), (60, 0), (85, 1), (100, 0)])
    assert run(Script().hold(30).hold(20, (0., .5), flags=0).hold(30, (0., .5)).hold(20))[:2] == (
        [(50, 1), (80, 0)], [(50, 1), (80, 0)])
    # Let go during Into, it ends without a balance.
    assert run(Script().hold(30).hold(30, (0., .5)).hold(20))[:2] == ([(42, 1), (60, 0)], [])
    # The brake button starts Riding.Brake, which Idle waits for: Into plays out (14 ticks: its expiry waits for the
    # 0.2 s blend, which the tree drops on the advance after it has passed), Cyc lasts while the brake is held, Out hands
    # back to Turning 0.4 s in, and Idle's manual starts on the tick after.
    manual, flag, brake = run(Script().hold(30).hold(4, flags=GROUND | 2).hold(70, (0., .5)).hold(20))
    assert brake == [(30, 1), (69, 0)] and manual == [(70, 1), (104, 0)] and flag == [(95, 1), (104, 0)]
    manual, flag, brake = run(Script().hold(30).hold(30, flags=GROUND | 2).hold(60, (0., -.5)).hold(20))
    assert brake == [(30, 1), (84, 0)] and manual == [(85, -1), (120, 0)]


def test_plaza_manuals_timing(probe):
    # The film's plaza_manuals pad from its rolling start (ref-film-plaza_manuals): a tail manual held from 53 to 155,
    # a push 158-184, a brake tap 188-191, then a nose manual held from 192 to 294. Native's rows publish balance on
    # 66-156 and 255-295, a frame behind its pad (test_manuals_over_the_take), so on 65-155 and 254-294 in pad ticks.
    # Ride's first is Native's to the tick. Its second waits for the brake to play out, enters the nose manual's Into at
    # 228 and balances from 253, a tick before Native's (whose Into starts at 229: its combo label, 12 ticks late, reads
    # Nose Manual from row 242). U98: before, Ride's second manual balanced from row 198
    # for 97 frames, against Native's 255 for 41.
    script = Script().hold(53).hold(103, (0., -.5)).hold(2).hold(27, flags=GROUND | 1).hold(3)
    script.hold(4, flags=GROUND | 2).hold(103, (0., .5)).hold(20)
    out = play(probe, script)
    assert out['brake'] == [(188, 1), (227, 0)]
    assert out['manual'] == [(65, -1), (156, 0), (228, 1), (295, 0)]
    assert out['flag'] == [(65, 1), (156, 0), (253, 1), (295, 0)]


def test_thumb_through_the_centre_and_a_load_alone(probe):
    # A thumb held down and swept up through the middle over a few ticks is an ollie; held down and let go, nothing.
    assert [n for _, n in flicked(probe, [(0., -1.)] * 12 + [(0., y) for y in (-.6, -.2, .2, .6, 1.)])] == ['Ollie']
    assert flicked(probe, [(0., -1.)] * 30) == []


def test_pad_nollies(probe):
    # skate_ride's pad rows: every nollie in Native's table and its diagonals (regular), then the goofy rider's (x
    # mirrored), through the pad's 0.25 per-axis dead zone, each held .16 s and stepped every .034 s.
    nollies = literal(SKATE_RIDE, 'NOLLIES')
    runs = [(n, p, False) for n, p in nollies.items()] + [('Nollie', p, False) for p in literal(SKATE_RIDE, 'NOLLIE_DIAGONALS')]
    runs += [(n, [(-x, y) for x, y in nollies[n]], True) for n in literal(SKATE_RIDE, 'GOOFY_NOLLIES')]
    for name, points, goofy in runs:
        timeline = [(0., (0., 0.)), (.4, points[0])] + [(.56 + .034 * i, p) for i, p in enumerate(points[1:])]
        timeline.append((.56 + .034 * (len(points) - 1), (0., 0.)))
        sticks, t, i = [], 0., 0
        while t < 1.2:
            if i + 1 < len(timeline) and timeline[i + 1][0] <= t:
                i += 1
            sticks.append(tuple(0. if abs(v) <= .25 else v for v in timeline[i][1])); t += 1. / 60.
        got = [n for _, n in flicked(probe, sticks, goofy)]
        native = 'Nollie' if name == 'Nollie' else 'N_' + NATIVE[next(k for k, v in NOLLIE_NAMES.items() if v == name[7:])]
        assert got == [native], (name, goofy, got)


# skate_ride's NOLLIES names after "Nollie ": the live helpers' names.
NOLLIE_NAMES = {'kickflip': 'Kickflip', 'heelflip': 'Heelflip', 'shove': 'Pop Shove-it', 'fs_shove': 'FS Pop Shove-it',
                '360_shove': '360 Shove-it', 'fs_360_shove': 'FS 360 Shove-it', 'varial_kickflip': 'Varial Kickflip',
                'varial_heelflip': 'Varial Heelflip', 'hardflip': 'Hardflip', 'inward_heelflip': 'Inward Heelflip',
                '360_flip': '360 Flip', 'laser_flip': 'Laser Flip', '360_hardflip': '360 Hardflip',
                '360_inward_heelflip': '360 Inward Heelflip'}
