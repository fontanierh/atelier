"""Later terrain only fills the land Hakuba's ground pages lack, so overlapping regions cannot cut cliffs.

Belmonte's north country overlaps the island's hills south of its apron. When later terrain overwrote the pages,
its ramp stood up to 113 m above the island's ground there; the island's ground, not the ramp, meets the apron.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

PORT = Path(__file__).resolve().parents[1] / 'hakuba_port'
sys.path.insert(0, str(PORT))
import ground  # noqa: E402
import contact  # noqa: E402

# The north country's join with the island and its apron, [west, south, east, north] in map metres.
JOIN = (-700.0, 3100.0, 1800.0, 3700.0)
# The largest rise between neighbouring ground samples there, in metres.
STEEPEST = 20.0


def test_later_terrain_keeps_existing_ground():
    old = np.array([[100.0, 100.0], [np.nan, np.nan]])
    new = np.array([[213.0, 213.0], [111.0, np.nan]])
    start = np.zeros_like(old, bool)
    keep = ground.kept(new, old, start)
    merged = np.where(keep, old, new)
    # The island's ground stays where the north country's ramp overlaps it, and the ramp fills only bare land.
    assert np.array_equal(merged[0], [100.0, 100.0])
    assert merged[1, 0] == 111.0
    assert np.isnan(merged[1, 1])


def test_start_regions_keep_their_ground():
    old = np.full((2, 2), np.nan)
    new = np.full((2, 2), 50.0)
    start = np.array([[True, False], [False, False]])
    assert ground.kept(new, old, start).tolist() == [[True, False], [False, False]]


def test_north_country_join_has_no_cliff():
    world = ground.settings()
    pages = sorted((ground.WORLD / world['ground']).glob('*.bin'))
    if not pages or pages[0].read_bytes()[:8] == b'version ':
        pytest.skip('the ground pages are Git LFS pointers here')
    heights = contact.mosaic(world)
    south_west, step = np.array(world['south_west_m']), world['ground_step_m']
    west, south, east, north = JOIN
    i0, i1 = int((west - south_west[0]) / step), int((east - south_west[0]) / step)
    j0, j1 = int((south - south_west[1]) / step), int((north - south_west[1]) / step)
    band = heights[j0:j1 + 1, i0:i1 + 1].astype(np.float64)
    with np.errstate(invalid='ignore'):
        rise = max(np.nanmax(np.abs(np.diff(band, axis=0))), np.nanmax(np.abs(np.diff(band, axis=1))))
    assert rise <= STEEPEST, f'a {rise:.0f} m cliff in the north country join'
