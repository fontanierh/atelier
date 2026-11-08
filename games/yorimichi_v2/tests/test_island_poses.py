"""Whole-island parity poses (plan P5): generated from committed data, one or more per world row, with citations that exist."""
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PARITY = ROOT / 'tools/parity'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(PARITY))
gen = load('v2_make_island_poses', PARITY / 'make_island_poses.py')
poseset = load('v2_poseset', PARITY / 'poseset.py')
ISLAND = json.loads((PARITY / 'island_poses.json').read_text())
POSES = ISLAND['poses']
NAME = re.compile(r'^w(\d{2})_[a-z0-9_]+$')
# CI checks out Git LFS pointers, not the committed heightmap and world data the generator reads: those tests skip there.
POINTERS = gen.pointer_inputs()
needs_data = pytest.mark.skipif(bool(POINTERS), reason='generator inputs are Git LFS pointers in this checkout')


@needs_data
def test_the_committed_file_is_the_generator_output():
    assert gen.main(['--check']) == 0, 'island_poses.json is stale: rerun make_island_poses.py'


def test_every_world_row_has_at_least_two_poses():
    counts = {}
    for pose in POSES:
        match = NAME.match(pose['name'])
        assert match, f'{pose["name"]}: not <wrow>_<what>'
        counts[int(match.group(1))] = counts.get(int(match.group(1)), 0) + 1
    assert sorted(counts) == list(range(21)), 'rows W00-W20 must each have poses'
    assert {row: n for row, n in counts.items() if n < 2} == {}


def test_names_are_unique_and_the_file_matches_the_slice_schema():
    names = [pose['name'] for pose in POSES]
    assert len(names) == len(set(names))
    assert ISLAND['schema'] == 1 and ISLAND['maps'] == {'donor': '/Game/Japan/Maps/Slice', 'v2': '/Game/V2/Maps/Slice'}
    for pose in POSES:
        assert set(pose) == {'name', 'location', 'rotation', 'fov', 'source'}
        assert len(pose['location']) == 3 and set(pose['rotation']) == {'pitch', 'yaw', 'roll'}
        assert 0 < pose['fov'] < 180 and pose['source']


def test_every_cited_file_exists_in_the_checkout():
    pattern = re.compile(r'(unreal/Content/Data/[\w/.\-]+|world/regions/[\w/.\-]+|docs/inventory/world\.md)')
    cited = {m for pose in POSES for m in pattern.findall(pose['source'])}
    assert cited
    for path in cited:
        assert (ROOT / path).exists(), f'cited file is missing: {path}'


def test_the_look_at_math_reproduces_the_slice_pier_arrival():
    """pier_arrival in poses.json: eye (-200, 36200, 6380) cm, aimed at the park-local (0, 0, 0.8) of the skate park."""
    slice_poses = {p['name']: p for p in json.loads((PARITY / 'poses.json').read_text())['poses']}
    arrival = slice_poses['pier_arrival']
    eye = (-2.0, -362.0, 63.8)
    target = gen.Target(-110.0, -234.0, 2.6, 'test')
    location, rotation = gen.look_at(eye, target, aim_up=0.0)
    assert location == pytest.approx(arrival['location'], abs=0.01)
    assert rotation['yaw'] == pytest.approx(arrival['rotation']['yaw'], abs=0.05)
    assert rotation['pitch'] == pytest.approx(arrival['rotation']['pitch'], abs=0.05)


@needs_data
def test_the_heightfield_is_the_committed_grid_in_north_up_rows():
    # world.json park_trail[0] is (-184.0, 214.5, 70.728): row J = +Y north, 2 m spacing.
    assert gen.heightfield(-184.0, 214.5) == pytest.approx(70.728, abs=0.5)
    assert gen.heightfield(400.0, 0.0) is None


@needs_data
def test_each_camera_is_outside_its_target_above_the_ground_and_looks_down():
    for name, target, bearing, distance, height, _ in gen.build_poses():
        placed = gen.pose_from(target, bearing, distance, height)
        cx, cy, cz = placed['camera']
        assert math.hypot(cx - target.x, cy - target.y) == pytest.approx(distance, abs=1e-6), name
        assert cz >= target.z + height - 1e-9, f'{name}: camera below the target and its clearance'
        assert height >= 8 and distance >= 30, name
        assert placed['rotation']['pitch'] < 0, f'{name}: camera does not look down at its landmark'


def test_pose_selection_by_glob_and_list():
    assert [p['name'] for p in poseset.select(POSES, 'w07_*')] == [p['name'] for p in POSES if p['name'].startswith('w07_')]
    picked = [p['name'] for p in poseset.select(POSES, ['w12_crater_*, w19_zeppelin_woodland'])]
    assert picked == ['w12_crater_overview', 'w12_crater_rim_station', 'w19_zeppelin_woodland']
    assert poseset.select(POSES, None) == POSES
    with pytest.raises(ValueError, match='matches no pose: w99_\\*'):
        poseset.select(POSES, 'w99_*')
