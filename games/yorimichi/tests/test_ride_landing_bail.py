"""Ride's landing bail against Native's bad landing (WipeoutBadLanding) and DangerZone (CheckWipeoutAir), offline.

Native's touch-down wipes out when the heading is off the travel by more than max_landing_angle at the speed along the
face, or when the speed into the face passes max_landing_speed (max_grind_speed onto a line), each limit times the
mode's bad_landing_scale. Ride copies the curve into RideSession.cpp (LandingAngleCurve) and the speeds into
RideTuning.h (BailImpact, BailGrindImpact, BailScale). The Skate plugin's ride_landing_bail_probe reads them with
Native's own loader from the tracked settings.skate; these tests check that Ride's copy is Native's, bit for bit, and
that Ride's curve lookup gives Native's limit at every speed. Without a C++ compiler they skip.

Before those, a board contact in the air past ignore_danger_frames while the playing clip carries the DangerZone
attribute wipes out once it closes faster than xz_trick across the rider's up or y_trick along it. Ride checks the
grab clip it plays (FRideAnimator::GrabDanger) against RideTuning.h's BailDanger* limits; the tests check the limits
against the probe and, with the stdlib decoder, which of the animator's grab clips carry DANGERZONE in the tracked
bundle: the Christ air's and the one-foot grab's (the one-foot out only early on), never the Indy's, Melon's or tuck
knee's, so those still ride away.
"""
import importlib.util
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
REPO = GAME.parents[1]
BUNDLE = GAME / 'unreal/Content/Data/SkateNative'
PLUGIN = REPO / 'platform/engine/Plugins/Activities/Skate'
PRIVATE = PLUGIN / 'Source/AtelierSkate/Private'
RIDE = PRIVATE / 'Ride'
PROBE = PLUGIN / 'Tests/Native/ride_landing_bail_probe.cpp'
SCRIPTS = GAME / 'unreal/Scripts/skate_ride'
SOURCES = [PROBE] + [PRIVATE / 'Native' / (name + '.cpp') for name in (
    'NameId', 'NativeMath', 'Settings', 'StockSettingsReader', 'WipeoutSettings')]
FLAGS = ['-std=c++20', '-O1', '-ffp-contract=off', '-fno-fast-math', '-fno-exceptions', '-fno-rtti', f'-I{PRIVATE / "Native"}']
NORMAL = 1      # WipeoutMode's order: easy, normal, hardcore, motorized, test
# Speeds along the face (m/s): below, on and between the curve's points, and past its end.
SPEEDS = [0, 5, 9.25, 9.25666714, 10, 11.7412596, 13, 15.5, 17.0540695, 19, 22, 25, 27, 27.7700005, 30, 60]

spec = importlib.util.spec_from_file_location('skate_ride_native_bail', SCRIPTS / 'native.py')
N = importlib.util.module_from_spec(spec)
sys.modules['skate_ride_native_bail'] = N
spec.loader.exec_module(N)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def real(word):
    return struct.unpack('<f', struct.pack('<I', int(word, 16)))[0]


def ride_curve():
    """RideSession.cpp's LandingAngleCurve as binary32 (m/s, radians)."""
    body = re.search(r'LandingAngleCurve\[\]\[2\] = \{(.*?)\};', (RIDE / 'RideSession.cpp').read_text(), re.S).group(1)
    return [(f32(float(x)), f32(float(y))) for x, y in re.findall(r'\{(-?[\d.]+)f?, (-?[\d.]+)f?\}', body)]


def ride_tune():
    """RideTuning.h's float defaults."""
    return {k: float(v) for k, v in re.findall(r'float (\w+) = (-?[\d.]+)f;', (RIDE / 'RideTuning.h').read_text())}


def ride_lookup(points, x):
    """RideSession.cpp's Curve(): clamped at both ends, linear between points."""
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / max(1e-4, x1 - x0)
    return points[-1][1]


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    compiler = shutil.which('clang++')
    if not compiler:
        pytest.skip('no clang++')
    binary = tmp_path_factory.mktemp('ride-landing-bail') / 'ride_landing_bail_probe'
    built = subprocess.run([compiler, *FLAGS, *map(str, SOURCES), '-o', str(binary)], capture_output=True, text=True)
    assert built.returncode == 0, built.stderr[-4000:]
    done = subprocess.run([str(binary), str(BUNDLE / 'settings.skate'), *map(str, SPEEDS)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-4000:]
    out = {'curve': [], 'mode': {}, 'eval': []}
    for line in done.stdout.splitlines():
        kind, *words = line.split()
        if kind == 'curve':
            out['curve'].append(tuple(map(real, words)))
        elif kind == 'mode':
            out['mode'][int(words[0])] = (words[1] == '1', real(words[2]))
        elif kind == 'limits':
            out['landing'], out['stairs'], out['grind'] = map(real, words)
        elif kind == 'eval':
            out['eval'].append(tuple(map(real, words)))
        elif kind == 'danger':
            out['danger'] = (real(words[0]), real(words[1]), int(words[2]))
    return out


def test_curve_is_natives(native):
    assert len(native['curve']) == 8
    assert ride_curve() == native['curve']


def test_lookup_gives_natives_limit(native):
    points = ride_curve()
    assert len(native['eval']) == len(SPEEDS)
    for speed, angle in native['eval']:
        assert ride_lookup(points, speed) == pytest.approx(angle, abs=1e-6), speed
    # Below 9.26 m/s the limit is 1.6 rad (92 degrees): Ride's folded heading (at most 90) never bails there.
    assert ride_lookup(points, 9) > 3.14159265 / 2


def test_limits_are_natives(native):
    tune = ride_tune()
    checks, scale = native['mode'][NORMAL]
    assert checks
    assert tune['BailScale'] == scale
    # Ride keeps a softer impact limit until its airs land where native's do (RideTuning.h), never a stricter one.
    assert tune['BailImpact'] >= native['landing'] * 100
    assert tune['BailGrindImpact'] == pytest.approx(native['grind'] * 100, abs=1e-3)
    assert 'SidewaysSafeSpeed' not in tune and 'BailYawFast' not in tune


def test_danger_limits_are_natives(native):
    tune = ride_tune()
    across, along, frames = native['danger']
    assert tune['BailDangerAcross'] == pytest.approx(across * 100, abs=1e-3)
    assert tune['BailDangerAlong'] == pytest.approx(along * 100, abs=1e-3)
    assert tune['BailDangerFrames'] == frames


def grab_clips():
    """RideAnimator.cpp's GrabNames by ERideGrab after None: (into, cycle, out)."""
    body = re.search(r'GrabNames\[\]\[3\] = \{(.*?)\};', (RIDE / 'RideAnimator.cpp').read_text(), re.S).group(1)
    rows = re.findall(r'\{TEXT\("(\w+)"\), TEXT\("(\w+)"\), TEXT\("(\w+)"\)\}', body)
    names = re.search(r'enum class ERideGrab : uint8 \{ None, ([\w, ]+) \}', (RIDE / 'RideTypes.h').read_text()).group(1).split(', ')
    assert len(rows) == len(names)
    return dict(zip(names, rows))


def danger_windows(clip):
    """A clip's DANGERZONE windows from the tracked bundle's metadata: (begin, end) in seconds, None for whole-clip."""
    for meta in N.Bundle(BUNDLE).metadata():
        found = meta.clip(clip)
        if found:
            return [None if a.begin == N.ALWAYS else (a.begin * found.length, a.end * found.length)
                    for a in found.attributes if a.name == 'DANGERZONE']
    raise AssertionError(f'{clip} not in the bundle')


def test_grab_danger_clips():
    grabs = grab_clips()
    for grab in ('ChristAir', 'OneFoot'):
        into, cycle, out = grabs[grab]
        assert danger_windows(into) == [None] and danger_windows(cycle) == [None], grab
    assert danger_windows(grabs['ChristAir'][2]) == [None]
    (window,) = danger_windows(grabs['OneFoot'][2])
    assert window[0] == 0 and window[1] == pytest.approx(.288, abs=1e-3)
    for grab in ('Indy', 'Melon', 'TuckKnee'):
        assert all(danger_windows(clip) == [] for clip in grabs[grab]), grab
