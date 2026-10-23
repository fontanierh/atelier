"""The ground round an in-ground bowl meets its deck: no trench under the rim, no terrain through the deck."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from craterpark.v2 import editor_generate as eg  # noqa: E402

GAME = Path(__file__).resolve().parents[1]


def grid(n=100, cell=1.):
    return {'x0': 0., 'z0': 0., 'G': cell, 'nx': n, 'nz': n}


def square(lo, hi, y):
    """A closed plan square at height y (counter-clockwise in x,z)."""
    return np.array([(lo, y, lo), (hi, y, lo), (hi, y, hi), (lo, y, hi)], 'f8')


def test_an_in_ground_bowl_lifts_the_ground_to_its_rim_and_keeps_the_pit_under_the_rides():
    g = grid()
    rim = [(square(60., 80., 10.), True)]          # the deck's outer edge
    rides = np.array([(70., -10., 70.), (71., -10., 71.)], 'f8')
    pit = np.zeros((100, 100), bool)
    pit[62:78, 62:78] = True                        # the carve, inside the coping
    H = np.zeros((100, 100))
    out = eg.clear_bowls(H, g, [(rim, rides, True, 2.)], pit)
    # the collar just outside the deck edge is at the rim
    assert abs(out[55, 70] - (10. - eg.BOWL_CLEAR)) < .01      # 4.5 m outside the square
    # beyond the collar the ground climbs at BOWL_SLOPE
    assert abs(out[45, 70] - (10. - eg.BOWL_SLOPE * 6.5 - eg.BOWL_CLEAR)) < .02   # 14.5 m outside
    # the carved pit stays below the rides
    assert out[70, 70] < -9.9
    # far outside the ease the ground is untouched
    assert out[5, 5] == 0.


def test_an_elevated_bowl_does_not_raise_the_ground_to_its_deck():
    g = grid()
    rim = [(square(60., 80., 10.), True)]
    rides = np.array([(70., -10., 70.)], 'f8')
    H = np.zeros((100, 100))
    out = eg.clear_bowls(H, g, [(rim, rides, False, 2.)], None)
    assert np.all(out[10:95, 10:95] == 0.)


def test_the_deck_edge_caps_ground_that_would_rise_through_it():
    g = grid()
    rim = [(square(60., 80., 10.), True)]
    rides = np.array([(70., -10., 70.)], 'f8')
    H = np.full((100, 100), 20.)
    out = eg.clear_bowls(H, g, [(rim, rides, True, 2.)], None)
    assert out[55, 70] <= 10. - eg.BOWL_CLEAR + 1e-6
    assert out[5, 5] == 20.                         # beyond the ease it is still the surrounding ground


def test_the_rim_height_is_interpolated_along_a_sloped_deck_edge():
    """The deep pocket and the ext blend change the deck's height along its edge: the ground follows the edge between
    its vertices, not the nearest vertex, or it leaves a trench under the lower stretch."""
    g = grid()
    rim = [(np.array([(20., 0., 20.), (20., 12., 60.)], 'f8'), False)]
    rides = np.array([(20., -10., 20.)], 'f8')
    H = np.zeros((100, 100))
    out = eg.clear_bowls(H, g, [(rim, rides, True, 0.)], np.zeros((100, 100), bool))
    # a cell beside the middle of the sloped edge sits at the edge's interpolated height (about 6.45 m there)
    assert 6.0 < out[41, 25] < 6.9


def test_the_volcano_and_island_consumers_follow_the_editor_ground_grid(tmp_path, monkeypatch):
    """A bowl seal changes the cut grid; the volcano must rebuild with it, not stay at the old floor."""
    import importlib.util
    from types import SimpleNamespace

    monkeypatch.delenv('ATELIER_CRATERPARK_V4_DESIGN', raising=False)
    monkeypatch.delenv('ATELIER_CRATERPARK_EDITOR_PARK', raising=False)
    spec = importlib.util.spec_from_file_location('yorimichi_editor_recipe_test', GAME / 'build.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    steps = {step.name: step for step in module.world_steps(SimpleNamespace(out=tmp_path))}
    for name in ('world.hidamari.geometry.HD_NorthMountains', 'world.layout', 'world.map'):
        assert 'world.craterpark_geometry' in steps[name].needs, name
