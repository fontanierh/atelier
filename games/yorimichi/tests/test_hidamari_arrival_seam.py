"""The arrival road ribbon meets the island road on the island terrain, not on Hidamari's ground model."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from hidamari import arrival  # noqa: E402

N, SIZE = 301, 600.


def is_skirt(points):
    return any(p[:2] == q[:2] and p[2] != q[2] for p in points for q in points)


class Mesh:
    def __init__(self):
        self.polys = []

    def poly(self, points, key):
        self.polys.append((points, key))


@pytest.fixture
def island(monkeypatch):
    # A steep hillside with alternating twisted quads: their two diagonals differ by 0.4 m.
    axis = np.linspace(-SIZE/2, SIZE/2, N); x, y = np.meshgrid(axis, axis)
    H = .2*y + .2*((np.arange(N)[:, None]+np.arange(N)[None, :]) % 2)
    road = [[250., 30., 0.], [294.51, 59.69, 0.]]
    monkeypatch.setattr(arrival, '_world', lambda: {'road': road, 'n': N, 'size': SIZE})
    monkeypatch.setattr(arrival, '_island', lambda: (H, N, SIZE))
    for cached in (arrival._road, arrival._samples):
        cached.cache_clear()
    yield H
    for cached in (arrival._road, arrival._samples):
        cached.cache_clear()


def test_ribbon_west_of_the_island_edge_lies_on_the_island_terrain(island):
    m = Mesh()
    arrival._ribbon(m, lambda x, y: -50.)        # Hidamari's ground model, deliberately far off
    surface = [p for points, key in m.polys if not is_skirt(points) for p in points]
    west = [p for p in surface if p[0] < SIZE/2]
    assert west
    for x, y, z in west:
        ground = arrival.island_height(x, y)
        assert ground + .09 < z < ground + .14   # on the terrain, never under either diagonal
    east = [p for points, key in m.polys if key == 'ar_road_asphalt' for p in points if p[0] > SIZE/2 + 1]
    assert east and all(abs(z + 50 - .12) < 1e-9 for _, _, z in east)


def test_island_height_never_sinks_under_either_triangulation(island):
    for x, y in [(294.3, 60.1), (295.7, 61.9), (293.1, 62.6), (296.9, 57.2)]:
        fx, fy = (x+SIZE/2)/2, (y+SIZE/2)/2; i, j = int(fx), int(fy); tx, ty = fx-i, fy-j
        a, b, c, d = island[j, i], island[j, i+1], island[j+1, i+1], island[j+1, i]
        ac = a+(b-a)*tx+(c-b)*ty if tx >= ty else a+(c-d)*tx+(d-a)*ty
        bd = a+(b-a)*tx+(d-a)*ty if tx+ty <= 1 else c+(c-d)*(tx-1)+(c-b)*(ty-1)
        assert arrival.island_height(x, y) == pytest.approx(max(ac, bd))


def test_shoulders_and_start_carry_a_skirt_below_the_edge(island):
    m = Mesh()
    arrival._ribbon(m, lambda x, y: 0.)
    skirts = [points for points, key in m.polys if is_skirt(points)]
    assert all(key == 'ar_road_gravel' for points, key in m.polys if is_skirt(points))
    for s in skirts:                                    # each corner pairs with one exactly SKIRT above or below
        assert all(any(q[:2] == p[:2] and abs(p[2] - q[2]) == pytest.approx(arrival.SKIRT) for q in s) for p in s)
    pts, _ = arrival._samples()
    assert len(skirts) == 2 * (2 * (len(pts) - 1) + 1)  # both edges per segment, plus the start, in both windings
    start = [s for s in skirts if all(abs(p[0] - pts[0][0]) < 3.5 and abs(p[1] - pts[0][1]) < 3.5 for p in s)]
    assert start
