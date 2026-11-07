"""The slice route check (tools/test/route.py): a recorded walk and skate run passes only when Cairo walked the road,
rode the pier at speed on a flat deck and the frame rate held."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v2_route', ROOT / 'tools/test/route.py')
route = importlib.util.module_from_spec(spec)
sys.modules['v2_route'] = route
spec.loader.exec_module(route)


def walk(n=11, step=175, mode='MOVE_WALKING', speed=352.):
    return [{'phase': 'walk', 'x': -24830 + i * step, 'y': 10000, 'z': 990 - i, 'speed': 0. if i == 0 else speed,
             'movement_mode': mode, 'board': 'away', 'fps': 60.} for i in range(n)]


def skate(n=10, top=850., board='ride', dz=0.):
    return [{'phase': 'skate' if i < 8 else 'skate_coast', 'x': -10400 - i * 400, 'y': 17400, 'z': 256 + dz * (i % 2),
             'speed': min(top, 100. + i * 150), 'movement_mode': 'MOVE_CUSTOM', 'board': board, 'fps': 60.}
            for i in range(n)]


def test_a_good_route_passes():
    failures, measured = route.evaluate(walk() + skate())
    assert failures == []
    assert measured['walk_m'] == 17.5 and measured['skate_top_speed'] == 850. and measured['min_sampled_fps'] == 60.


def test_swimming_or_a_short_walk_fails():
    assert any('not walking' in f for f in route.evaluate(walk(mode='MOVE_CUSTOM') + skate())[0])
    assert any(f.startswith('walk: 5.2 m') for f in route.evaluate(walk(n=4) + skate())[0])


def test_a_slow_skate_off_the_board_or_off_the_deck_fails():
    assert any('top speed' in f for f in route.evaluate(walk() + skate(top=400.))[0])
    assert any('not riding' in f for f in route.evaluate(walk() + skate(board='hand'))[0])
    assert any('height varies' in f for f in route.evaluate(walk() + skate(dz=80.))[0])


def test_missing_phases_and_low_frame_rates_fail():
    assert route.evaluate(skate())[0] == ['walk: 0 samples']
    rows = walk() + skate()
    rows[3]['fps'] = 12.
    assert route.evaluate(rows)[0] == ['frame: a sampled frame at 12.0 fps < 20']
    teleport = {**rows[0], 'phase': 'skate_place', 'fps': 2.5}   # a teleport's streaming frame is no play
    assert route.evaluate(walk() + [teleport] + skate())[0] == []


def test_the_report_names_the_launch_commit_and_refuses_a_moved_checkout():
    head = subprocess.run(['git', '-C', str(route.REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                          check=True).stdout.strip()
    assert route.revision(head)['commit'] == head
    with pytest.raises(ValueError, match='launched at'):
        route.revision('0' * 40)
