"""The operating town terminus: fixed platform height, open yard and right-side boarding."""
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import yori  # noqa: E402,F401
import belmonte_train_service as service  # noqa: E402
from hidamari import layout, station_yard as yard, station_yard_placement as placement  # noqa: E402
from train import route  # noqa: E402


def test_no_decorative_train_or_scatter_in_the_platform_and_approach():
    instances = {'HD_Railcar': [[1185., 301.8, 0.]],
                 'HD_P_Bin': [[1250., 301.8, 0.], [1221., 280., 0.]],
                 'Tree_Maple_A': [[1280., 302., 0.], [1100., 270., 0.]]}
    with patch.object(placement, 'floor_z', return_value=31.64):
        placement.place(lambda *a: None, instances, lambda x, y: 0., [])
    assert 'HD_Railcar' not in instances
    assert instances['HD_P_Bin'] == [[1221., 280., 0.]]
    assert instances['Tree_Maple_A'] == [[1100., 270., 0.]]


def test_extended_platform_terrain_is_level_across_the_former_east_lane():
    pad = dict(yard.PAD, z=30.25)
    with patch.object(layout, 'H', np.zeros((3, 3))), \
            patch.object(layout, 'terrain_pads', return_value=(pad,)), \
            patch.object(layout.street_height, 'start', (300., 140.), create=True):
        z = layout.height(np.array([1185., 1240., 1280.]), np.array([298., 298., 298.]))
        assert np.allclose(z, pad['z'])
        # The lane outside its closed section retains the road surface.
        assert float(layout.height(1240., 270.)) == float(layout.street_height(1240., 270.))


def test_profile_is_anchored_to_the_station_instead_of_raising_the_platform():
    with patch.object(yard, 'floor_z', return_value=31.64):
        s = np.arange(0., 1001., 10.)
        rail, _ = route.vertical(s, np.full(s.shape, 34.))
        assert rail is not None
        assert np.allclose(rail[s <= route.HIDAMARI.reserve[0]], 31.64 + yard.RAIL)


def test_historical_alternative_that_cannot_fit_is_reported_as_infeasible():
    with patch.object(route, 'alignment', return_value=None):
        with pytest.raises(route.InfeasibleRoute, match='curves do not fit'):
            route.study()


def test_profile_that_cannot_reach_the_fixed_station_is_reported_as_infeasible():
    with patch.object(route, 'vertical', return_value=(None, float('inf'))), \
            patch.object(route, 'place_loop', return_value=(None, None, float('inf'), 0.)):
        with pytest.raises(route.InfeasibleRoute, match='fixed station height'):
            route.study(sampler=lambda x, y: np.zeros_like(x))


def test_service_platform_and_arrival_join_the_existing_station_on_the_right():
    rail = 31.64 + yard.RAIL
    samples = [{'s': float(s), 'x': yard.X0 + s, 'y': yard.TRACK_Y,
                'rail_z': rail, 'ground_z': rail - .85} for s in range(0, 1010, 10)]
    data = {'samples': samples, 'stations': {
        'Hidamari': {'centre': list(yard.SERVICE_CENTRE), 'side': 'r', 'top_above_rail_m': .25 - yard.RAIL},
        'Belmonte': {'centre': [2000., 4000.]}}}
    train = {'length': 131., 'vehicles': [{'id': 'first-class', 'offset': 0., 'doors': [
        {'kind': 'exterior', 'side': 'l', 'collision': [1000., 0., 0., 1100., 0., 0.]},
        {'kind': 'exterior', 'side': 'r', 'collision': [-1100., 0., 0., -1000., 0., 0.]}]}]}
    town, belmonte = service.stations(data, train, [75.5, 900.])
    assert town['side'] == 'r' and belmonte['side'] == 'l'
    centre, size = town['platform']['centre'], town['platform']['size']
    assert abs((centre[2] + size[2] / 2) / 100 - (31.64 + .25)) < .002
    assert abs(-(centre[1] - size[1] / 2) / 100 - 299.95) < .002
    assert size[0] / 100 > train['length']
    arrival = town['arrival']['location']
    assert 295.8 < -arrival[1] / 100 < 299.95
    assert abs(arrival[0] / 100 - (yard.X0 + 75.5 - 10.5 - 7)) < .002
    assert arrival[2] / 100 == 31.89


def test_arrival_boards_hang_under_the_canopy_clear_of_the_train():
    rail = 31.64 + yard.RAIL
    samples = [{'s': float(s), 'x': yard.X0 + s, 'y': yard.TRACK_Y,
                'rail_z': rail, 'ground_z': rail - .85} for s in range(0, 1010, 10)]
    data = {'samples': samples, 'stations': {
        'Hidamari': {'centre': list(yard.SERVICE_CENTRE), 'side': 'r', 'top_above_rail_m': .25 - yard.RAIL},
        'Belmonte': {'centre': [2000., 4000.]}}}
    train = {'length': 131., 'vehicles': [{'id': 'first-class', 'offset': 0., 'doors': []}]}
    town, belmonte = service.stations(data, train, [75.5, 900.])
    boards = town['boards']
    assert [b['id'] for b in boards] == ['hidamari_canopy_1', 'hidamari_canopy_2']
    floor = 31.64
    arrival_x = town['arrival']['location'][0] / 100
    assert min(abs(b['location'][0] / 100 - arrival_x) for b in boards) < 8.
    for b in boards:
        x, y, z = b['location'][0] / 100, -b['location'][1] / 100, b['location'][2] / 100
        w, h, d = (c / 100 for c in b['size'])
        local = x - yard.STATION[0]
        # between the canopy posts (every 6 m from -21) and their knee braces (.9 m)
        assert all(abs(local - post) > w / 2 + .9 for post in range(-21, 22, 6))
        assert abs(y - (yard.STATION[1] + 9.2)) < 1e-6
        # clear of the scaled train body (1.80 m * 1.15 from the track) and above head height
        assert yard.TRACK_Y - (y + d / 2) > 1.8 * 1.15 + .3
        assert z - h / 2 - (floor + .25) > 2.4
        assert z + h / 2 < b['mount_z'] / 100 <= floor + 5.0
        assert b['mount'] == 'rods' and b['double_sided']
        assert b['yaw'] == 90.        # facing the benches (-y in the world, +y in Unreal)
    # the line's other end (not at the station site here): a board on posts on its makeshift platform
    assert [b['mount'] for b in belmonte['boards']] == ['posts']
