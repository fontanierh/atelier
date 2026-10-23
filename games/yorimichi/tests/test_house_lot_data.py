"""Final terrain query products isolate each lot from unrelated world edits."""
import importlib
import math
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def data(monkeypatch):
    world = Path(__file__).resolve().parents[1] / 'world'
    monkeypatch.syspath_prepend(str(world))
    monkeypatch.syspath_prepend(str(world / 'regions'))
    return importlib.import_module('houses.lot_data')


def fixture_world():
    lot = dict(name='HouseLot_1', house='House_A', variant='A', level=4.,
               front=[[-9.5, -8., 0.], [9.5, -8., 0.]], gate=[1., 3.],
               garden=dict(centre=[-4., -5.], radii=[1., 2.]), gate_verge=-.1,
               centre=[0., 0.], yaw=30.)
    return dict(n=301, size=600., houses=dict(lots=[lot]))


def test_declared_queries_match_original_whole_final_heightmap_lookup(data):
    world = fixture_world()
    heights = np.arange(301 * 301, dtype=np.float32).reshape(301, 301) / 100
    result = data.project(world, heights, 'HouseLot_1')
    ground = data.Ground(result)
    assert 0 < len(result['cells']) < 100
    for x, y in data.queries(world['houses']['lots'][0]):
        step = world['size'] / (world['n'] - 1)
        i = int(np.clip(math.floor((x + world['size'] / 2) / step), 0, world['n'] - 2))
        j = int(np.clip(math.floor((y + world['size'] / 2) / step), 0, world['n'] - 2))
        assert ground.low(x, y) == float(heights[j:j + 2, i:i + 2].min())
    with pytest.raises(ValueError, match='undeclared'):
        ground.low(-250., -250.)


def test_other_placements_and_unread_terrain_do_not_change_lot_product(data):
    world = fixture_world()
    heights = np.zeros((301, 301))
    before = data.project(world, heights, 'HouseLot_1')
    world['instances'] = {'Tree': [[250., 250., 0.]]}
    world['houses']['lots'][0]['unused_annotation'] = 'not geometry'
    world['houses']['lots'].append(dict(name='OtherLot'))
    heights[0, 0] = 50
    assert data.project(world, heights, 'HouseLot_1') == before
    i, j = map(int, next(iter(before['cells'])).split(','))
    heights[j:j + 2, i:i + 2] = 10
    assert data.project(world, heights, 'HouseLot_1') != before


def test_incomplete_or_duplicate_placement_refuses(data):
    world = fixture_world()
    world['houses']['lots'] *= 2
    with pytest.raises(ValueError, match='exactly one'):
        data.project(world, np.zeros((301, 301)), 'HouseLot_1')
