"""Keep the actual town railway clear while moving every air-service datum together."""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from hidamari import station_yard as yard  # noqa: E402
from zeppelin import layout as air  # noqa: E402


def test_apron_ship_turn_and_pedestrian_link_clear_the_railway():
    city = air.metadata()['stations'][1]
    # The apron projects 8.8 m south; a 14 m radius contains the ship, fins and motors at any heading.
    assert city['origin'][1] - 8.8 > yard.Y1 + 2.
    assert city['ship'][1] - 14. > yard.Y1 + 2.
    path = air.city_path()
    assert path[:, 1].min() - .8 > yard.Y1 + 2.
    assert path[0, 0] == yard.LANE_BREAK[0]
    assert path[0, 1] > yard.LANE_BREAK[2] + 3.
    assert np.allclose(path[-1], city['safe'][:2])


def test_air_station_grading_does_not_change_the_rail_cutting_or_roads():
    x, y = np.meshgrid(np.linspace(yard.X0, yard.X1, 25), [yard.Y0, yard.TRACK_Y, yard.Y1])
    ground = np.full(x.shape, 30.25)
    assert np.array_equal(air.city_pad(x, y, ground), ground)
    for x, y in [(1240., 329.), (1273., 335.), (1290., 335.)]:
        assert air.city_pad(x, y, 36.) == 36.
    ox, oy, oz = air.STATIONS[1]['origin']
    assert air.city_pad(ox + air.SAFE[0], oy + air.SAFE[1], 20.) == oz


def test_city_station_clears_its_walking_link_by_default():
    instances = {'Tree_Maple_A': [[1242., 329., 36.], [1242., 350., 36.]]}
    removed = air.clear(instances, station=1)
    assert removed['Tree_Maple_A'] == 1
    assert instances['Tree_Maple_A'] == [[1242., 350., 36.]]


def test_air_service_and_flight_durations_follow_the_moved_station(monkeypatch):
    before = air.metadata()
    stations = [{**s, 'origin': list(s['origin'])} for s in air.STATIONS]
    delta = np.array([8., 13., 1.2])
    stations[1]['origin'] = (np.array(stations[1]['origin']) + delta).tolist()
    monkeypatch.setattr(air, 'STATIONS', stations)
    after = air.metadata()
    for i, station in enumerate(after['stations']):
        for key in ('origin', 'ship', 'entry', 'safe'):
            assert np.allclose(np.subtract(station[key], before['stations'][i][key]), delta if i == 1 else 0.)
    for leg in after['legs']:
        a, b = leg['stops']
        expected = math.dist(after['stations'][a]['ship'][:2], after['stations'][b]['ship'][:2]) / air.CRUISE_SPEED
        assert leg['seconds'] == pytest.approx(round(expected, 1))
    # A leg without Hidamari keeps its complete authored flight specification.
    assert [leg for leg in after['legs'] if 1 not in leg['stops']] == [
        leg for leg in before['legs'] if 1 not in leg['stops']]
