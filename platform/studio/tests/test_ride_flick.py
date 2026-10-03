"""The Ride backend's Flick-It reader (Skate plugin, Private/Ride/RideFlick.h) against the skate. gesture paths.

The header is plain C++; this compiles it with a small driver and plays each gesture the way the live helpers script
it: the first point held for the load, each further point for 30 ms, then the stick back at the centre, at 60 Hz.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HEADER = ROOT / 'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/Ride/RideFlick.h'

# Regular stance, x right and y away from the player (the recovered skater.pat paths with x mirrored).
PATHS = {
    'Ollie': [(0.0, -1.0), (0.0, 1.0)],
    'Nollie': [(0.005714, 0.988571), (0.005714, -1.0)],
    'Kickflip': [(0.0, -1.0), (-0.908571, 0.417143)],
    'Heelflip': [(0.1, -0.94), (0.68, 0.714286)],
    'Pop Shove-it': [(-0.257143, -0.942857), (-0.862857, -0.451429), (-0.908571, 0.36)],
    'FS Pop Shove-it': [(0.2, -0.965714), (0.851429, -0.52), (0.942857, 0.28)],
    '360 Shove-it': [(0.874286, -0.485714), (-0.165714, -0.988571), (-0.954286, -0.245714)],
    'FS 360 Shove-it': [(-0.862857, -0.485714), (0.165714, -0.988571), (0.965714, -0.257143)],
    'Varial Kickflip': [(0.702857, -0.702857), (-0.234286, -0.954286), (-0.851429, 0.508571)],
    'Varial Heelflip': [(-0.725714, -0.702857), (0.131429, -0.977143), (0.497143, 0.84)],
    'Hardflip': [(-0.737143, -0.668571), (0.142857, -0.988571), (-0.6, 0.771429)],
    'Inward Heelflip': [(0.714286, -0.714286), (-0.211429, -0.977143), (0.737143, 0.645714)],
    '360 Flip': [(0.965714, -0.268571), (0.497143, -0.84), (-0.211429, -0.988571), (-0.908571, 0.405714)],
    'Laser Flip': [(-1.0, -0.177143), (-0.657143, -0.76), (-0.04, -0.988571), (0.84, 0.485714)],
    '360 Hardflip': [(-0.977143, -0.177143), (-0.577143, -0.817143), (0.12, -0.988571), (-0.702857, 0.691429)],
    '360 Inward Heelflip': [(0.977143, -0.177143), (0.634286, -0.76), (-0.051429, -0.977143), (0.497143, 0.828571)],
}

DRIVER = r'''
#include "RideFlick.h"
#include <cstdio>
int main()
{
    atelier::ride::FlickReader Reader; float X, Y, Dt; int Manual = 0;
    while (std::scanf("%f %f %f", &X, &Y, &Dt) == 3)
    {
        const auto F = Reader.Update(X, Y, Dt);
        if (F != atelier::ride::Flick::None) std::printf("%s\n", atelier::ride::FlickName(F));
        if (Reader.ManualBand() != 0 && !Manual) { Manual = Reader.ManualBand(); std::printf("manual %d\n", Manual); }
    }
}
'''


@pytest.fixture(scope='module')
def reader(tmp_path_factory):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if not compiler:
        pytest.skip('no C++ compiler')
    folder = tmp_path_factory.mktemp('flick')
    (folder / 'driver.cpp').write_text(DRIVER)
    binary = folder / 'driver'
    subprocess.run([compiler, '-std=c++17', '-O1', f'-I{HEADER.parent}', str(folder / 'driver.cpp'), '-o', str(binary)], check=True)

    def run(samples):
        text = ''.join(f'{x} {y} {dt}\n' for x, y, dt in samples)
        return subprocess.run([str(binary)], input=text, capture_output=True, text=True, check=True).stdout.split('\n')[:-1]
    return run


def scripted(points, load=.18, step=.03, rate=60.0):
    """The live helpers' flick: ticks at `rate`, each point held for its duration, then the centre."""
    holds = [(points[0], load)] + [(p, step) for p in points[1:]] + [((0.0, 0.0), .2)]
    dt, samples = 1 / rate, []
    for (x, y), seconds in holds:
        ticks = max(1, round(seconds * rate))
        samples += [(x, y, dt)] * ticks
    return samples


@pytest.mark.parametrize('name', sorted(PATHS))
def test_scripted_gestures(reader, name):
    assert reader(scripted(PATHS[name])) == [name]


@pytest.mark.parametrize('name', ['Ollie', 'Kickflip', '360 Flip', 'Pop Shove-it'])
def test_slow_frames_still_read(reader, name):
    # A 30 fps game steps two ticks per frame, but the stick only changes once per frame.
    assert reader(scripted(PATHS[name], rate=30.0)) == [name]


def test_smooth_ollie_through_the_centre(reader):
    # A real thumb: held down, then up through the middle over a few ticks.
    samples = [(0.0, -1.0, 1 / 60)] * 12 + [(0.0, y, 1 / 60) for y in (-.6, -.2, .2, .6, 1.0)] + [(0.0, 0.0, 1 / 60)] * 10
    assert reader(samples) == ['Ollie']


def test_manual_band_is_not_a_flick(reader):
    samples = [(0.0, -.5, 1 / 60)] * 40 + [(0.0, 0.0, 1 / 60)] * 5
    assert reader(samples) == ['manual -1']


def test_load_without_flick_does_nothing(reader):
    samples = [(0.0, -1.0, 1 / 60)] * 30 + [(0.0, 0.0, 1 / 60)] * 30
    assert reader(samples) == []
