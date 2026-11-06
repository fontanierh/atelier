"""The ground draws the colour Yorimichi's terrain materials paint, not the flat colour its cells were ported in.

The far hills, Belmonte's valley, apron and north country, and Brinecove's natural ground were ported as single flat
colours (and Brinecove's twice too bright), where Yorimichi paints sand, rock, meadow and forest floor from height,
slope and position. `ground.py` now records which layer owns each point and hands it to that layer's painter.
"""
import sys
from pathlib import Path

import numpy as np

PORT = Path(__file__).resolve().parents[1] / 'hakuba_port'
sys.path.insert(0, str(PORT))
# Yorimichi's `world/regions/` package and the port's `regions.py` share a name in one test process: the port's
# modules import with the port's `regions`, and whatever was cached before is put back for the tests that use it.
_before = sys.modules.pop('regions', None)
import ground  # noqa: E402
import ground_paint  # noqa: E402
if _before is not None:
    sys.modules['regions'] = _before
else:
    sys.modules.pop('regions', None)


def test_every_painter_names_a_layer():
    assert set(ground_paint.PAINTERS) <= {prefix for _, prefix in ground.LAYERS}


def test_paint_changes_only_the_painted_layers_points():
    heights = np.full((3, 3), 20.0)
    flat = np.array(ground_paint.FAR_FOREST)
    colours = np.tile(flat, (3, 3, 1))
    owners = np.full((3, 3), -1)
    far_hills = [prefix for _, prefix in ground.LAYERS].index('far-hills-cell-')
    owners[1, :] = far_hills
    # Inland, south of Belmonte's join and away from every coast, the far hills keep their forest floor.
    origin = np.array([0.0, 1500.0])
    ground.paint(heights, colours, owners, origin, 2.0)
    assert np.allclose(colours[0], flat) and np.allclose(colours[2], flat)
    assert np.allclose(colours[1], ground_paint.far_hills(np.zeros(3), np.full(3, 1500.0), np.full(3, 20.0),
                                                           np.ones(3), np.tile(flat, (3, 1))))


def test_far_hills_brighten_north_of_the_join():
    flat = np.tile(ground_paint.FAR_FOREST, (2, 1))
    south, north = ground_paint.far_hills(np.zeros(2), np.array([1500.0, 4500.0]), np.full(2, 20.0), np.ones(2), flat)
    assert np.allclose(south, ground_paint.FAR_FOREST)
    assert np.allclose(north, (0.105, 0.145, 0.055))


def test_brinecove_paints_only_its_natural_ground():
    meadow = ground_paint.texture_mean(next(ground_paint.BRINECOVE_TEXTURES.glob('terrain_meadow.*')))
    path = np.array([0.3, 0.2, 0.1])
    x, y = np.array([-1500.0, -1500.0, -1500.0]), np.zeros(3)
    z, normal_z = np.array([0.3, 40.0, 40.0]), np.array([0.99, 0.5, 0.5])
    colour = ground_paint.brinecove(x, y, z, normal_z, np.stack([meadow, meadow, path]))
    sand = ground_paint.texture_mean(next(ground_paint.BRINECOVE_TEXTURES.glob('terrain_sand.*')))
    rock = ground_paint.texture_mean(next(ground_paint.BRINECOVE_TEXTURES.glob('terrain_rock.*')))
    # The waterline is sand, a steep high face rock, and a path keeps its own colour.
    assert np.allclose(colour[0], sand)
    assert np.allclose(colour[1], rock * ground_paint.BRINECOVE_ROCK_BREAKUP)
    assert np.allclose(colour[2], path)
