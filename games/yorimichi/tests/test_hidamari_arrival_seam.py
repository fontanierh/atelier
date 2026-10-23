"""The arrival road ribbon runs on from the island road flush, with no step, and its shoulders meet the ground drawn
under them on both terrains."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world'))
import yori  # noqa: E402,F401
from hidamari import arrival, arrival_placement  # noqa: E402

N, SIZE = 301, 600.
END = (294.51, 59.69, .05*294.51 + .25)   # the island road, its strip a little above the terrain


def is_skirt(points):
    return any(p[:2] == q[:2] and p[2] != q[2] for p in points for q in points)


class Mesh:   # village.build.Mesh, as far as the ribbon uses it: repeated points merge, a face without area is dropped
    def __init__(self):
        self.polys, self.faces = [], []

    def poly(self, points, key):
        clean = []
        for p in map(np.asarray, points):
            if not any(((p - q)**2).sum() < 1e-16 for q in clean): clean.append(p)
        if len(clean) < 3 or sum(np.linalg.norm(np.cross(clean[k] - clean[0], clean[k+1] - clean[0]))
                                 for k in range(1, len(clean) - 1)) < 1e-10:
            return
        self.polys.append(([tuple(map(float, p)) for p in clean], key)); self.faces.append(tuple(range(len(clean))))


def on_section(c, n, p):
    """The point's offset across the section through c along n, or None when it is not on it."""
    if abs((p[0] - c[0])*n[1] - (p[1] - c[1])*n[0]) > 1e-6: return None
    return (p[0] - c[0])*n[0] + (p[1] - c[1])*n[1]


def hillside(x, y):
    # Hidamari's ground: it meets the island terrain at x 300 and rolls away east of it.
    return .05*np.asarray(x) + .5*np.sin((np.asarray(x) - 300)/7.)


@pytest.fixture
def island(monkeypatch):
    # A slope rising east with alternating twisted quads (their two diagonals differ by 0.2 m), untwisted on its east
    # edge, where it meets Hidamari's ground.
    axis = np.linspace(-SIZE/2, SIZE/2, N); x, y = np.meshgrid(axis, axis)
    H = .05*x + .1*((np.arange(N)[:, None]+np.arange(N)[None, :]) % 2)*(np.arange(N)[None, :] < N-1)
    road = [[250., 60., .05*250 + .25], list(END)]
    for owner in (arrival, arrival_placement):
        monkeypatch.setattr(owner, '_world', lambda: {'road': road, 'n': N, 'size': SIZE})
    monkeypatch.setattr(arrival, '_island', lambda: (H, N, SIZE))
    xs = tuple(np.arange(300., 420.1, 4.)); ys = tuple(np.arange(0., 240.1, 4.))
    monkeypatch.setattr(arrival, '_hidamari_axes', lambda: (xs, ys))
    for cached in (arrival._road, arrival._samples):
        cached.cache_clear()
    yield H
    for cached in (arrival._road, arrival._samples):
        cached.cache_clear()


def test_drawn_follows_the_importers_a_c_diagonal():
    a, b, c, d = 0., 1., 5., 2.
    for tx, ty in [(.2, .1), (.9, .3), (.1, .8), (.4, .6), (.5, .5)]:
        if tx >= ty:   # triangle a b c
            expected = a + (b-a)*tx + (c-b)*ty
        else:          # triangle a c d
            expected = a + (c-d)*tx + (d-a)*ty
        assert arrival._drawn(a, b, c, d, tx, ty) == pytest.approx(expected)
    assert arrival._drawn(a, b, c, d, .5, .5) == pytest.approx((a+c)/2)   # on the diagonal itself


def test_island_height_is_the_drawn_island_mesh(island):
    for x, y in [(294.3, 60.1), (295.7, 61.9), (293.1, 62.6), (296.9, 57.2)]:
        fx, fy = (x+SIZE/2)/2, (y+SIZE/2)/2; i, j = int(fx), int(fy)
        a, b, c, d = island[j, i], island[j, i+1], island[j+1, i+1], island[j+1, i]
        assert arrival.island_height(x, y) == pytest.approx(arrival._drawn(a, b, c, d, fx-i, fy-j))


def test_the_ribbon_starts_as_the_island_roads_own_flat_strip(island):
    c, n, z = arrival._sections(hillside)[0]
    road = [z[s] for s in arrival.ASPHALT]
    assert road == pytest.approx([END[2] + arrival.ROAD_LIFT] * len(road))   # its height, flat across like the island strip
    assert c == pytest.approx(END[:2])


def test_asphalt_eases_onto_the_hillside_without_steps(island):
    sections = arrival._sections(hillside)
    g = arrival.ground(hillside)
    centre = [z[0.] for _, _, z in sections]
    assert max(abs(q - p) for p, q in zip(centre, centre[1:])) < .05       # every 0.25 m: no step
    for c, n, z in sections:
        for s in arrival.ASPHALT:
            assert z[s] >= g(c[0]+n[0]*s, c[1]+n[1]*s) + .02 - 1e-9          # never under the ground drawn there
    far = [(c, n, z) for c, n, z, t in zip(*zip(*sections), arrival._samples()[2]) if t > arrival.BLEND]
    assert far and all(z[0.] == pytest.approx(g(*c) + .12) for c, n, z in far)


def test_shoulders_meet_the_drawn_ground_flush(island):
    g = arrival.ground(hillside)
    at = lambda c, n, s: g(c[0]+n[0]*s, c[1]+n[1]*s)
    for c, n, z in arrival._sections(hillside):
        for side in (-1, 1):
            edge, *between, outer = arrival._shoulder(side)
            assert z[outer] == pytest.approx(at(c, n, outer) + arrival.FLUSH)
            assert all(z[s] >= at(c, n, s) + arrival.FLUSH - 1e-9 for s in between)
            assert at(c, n, edge) < z[edge] <= z[side*arrival.SHOULDER[0]]   # just under the asphalt's edge


def test_skirts_hang_only_below_the_shoulders_outer_edges_and_start(island):
    m = Mesh()
    arrival._ribbon(m, hillside)
    g = arrival.ground(hillside)
    skirts = [points for points, key in m.polys if is_skirt(points)]
    pts, _, dist = arrival._samples()
    c, n = pts[0], arrival._samples()[1][0]
    start = [s for s in skirts if all(abs((x - c[0])*n[1] - (y - c[1])*n[0]) < 1e-6 for x, y, _ in s)]
    # in the shoulder's surface over it: lawn across the start and along the edge until the gravel has grown to it
    keys = [key for points, key in m.polys if is_skirt(points)]
    assert all(k == 'ar_verge_lawn' for s, k in zip(skirts, keys) if s in start)
    grown = sum(t >= arrival.BLEND for t in dist[:-1])
    assert keys.count('ar_road_gravel') == 2 * 2 * grown
    for s in skirts:   # no raised face: along the road a skirt's top is a shoulder's outer edge, FLUSH above the ground
        if s not in start:
            assert all(z <= g(x, y) + arrival.FLUSH + 1e-9 for x, y, z in s)
    across = len(arrival.SHOULDER) - 1
    assert len(skirts) == 2 * 2 * (len(pts) - 1 + across)   # each outer edge per segment and across each start,
    #                                                       in both windings
    assert len(start) == 2 * 2 * across
    for s in start:   # under the shoulders only, never a lip across the road
        assert all(abs((x - c[0])*n[0] + (y - c[1])*n[1]) > arrival.SHOULDER[0] for x, y, _ in s)


def test_gravel_grows_from_nothing_at_the_island_road_end(island):
    # The island road runs straight onto the grass; the shoulder's gravel widens to the whole shoulder over BLEND
    # metres and the rest of it is lawn, cut on each section where the gravel ends.
    m = Mesh()
    arrival._ribbon(m, hillside)
    pts, normals, dist = arrival._samples()
    inner, outer = arrival.SHOULDER[0], arrival.SHOULDER[-1]
    for c, n, t in list(zip(pts, normals, dist))[::8]:
        width = (outer - inner)*arrival._smooth(t/arrival.BLEND)
        for key, check in (('ar_road_gravel', lambda s: abs(s) <= inner + max(width, 1e-3) + 1e-6),
                           # where the gravel's end crosses a column line between two sections, the lawn's
                           # triangle there reaches that column's corner, at most one section's growth inside it
                           ('ar_verge_lawn', lambda s: abs(s) >= inner + width - .03)):
            across = [s for points, k in m.polys if k == key and not is_skirt(points)
                      for s in (on_section(c, n, p) for p in points) if s is not None and abs(s) >= inner]
            assert all(check(s) for s in across), (key, t)
        if width < 1e-9:   # nothing of the gravel at the very start, only lawn out to the shoulder's edge
            assert not [p for points, k in m.polys if k == 'ar_road_gravel' and not is_skirt(points)
                        for p in points if (s := on_section(c, n, p)) is not None and abs(s) > inner + 2e-3]
    assert all(len(points) >= 3 for points, _ in m.polys)


def test_asphalt_carries_the_island_roads_own_uvs_in_phase(island):
    m = Mesh()
    arrival._ribbon(m, hillside)
    asphalt = [i for i, (points, key) in enumerate(m.polys) if key == 'ar_island_road']
    assert asphalt and sorted(m.uvs) == asphalt          # every asphalt face, and only those, carries the road's UVs
    assert not any(key == 'ar_road_line' for _, key in m.polys)   # the markings are the road texture's own
    step = np.hypot(END[0] - 250., END[1] - 60.)          # the fixture road: two points, the last of index 1
    pts, normals, dist = arrival._samples()
    for i in asphalt:
        for (x, y, _), (u, v) in zip(m.polys[i][0], m.uvs[i]):
            k = min(range(len(pts)), key=lambda j: np.hypot(x - pts[j][0] - normals[j][0]*(u*5.2 - 2.6),
                                                             y - pts[j][1] - normals[j][1]*(u*5.2 - 2.6)))
            assert 0. <= u <= 1. and v == pytest.approx((1 + dist[k]/step)/8)
    start = [uv for i in asphalt for (x, y, _), uv in zip(m.polys[i][0], m.uvs[i])
             if np.hypot(x - END[0], y - END[1]) < 2.7 and uv[1] == pytest.approx(1/8)]
    assert sorted(round(u, 6) for u, _ in start) == [0., .25, .25, .5, .5, .75, .75, 1.]   # right edge 0, left 1


def test_island_fade_runs_from_the_island_edge_over_its_width():
    # street_height's corridor and HD_Terrain's lawn colour (build.surface) fade from the island's on one curve
    from hidamari import layout
    x = np.array([250., 300., 300 + layout.ISLAND_FADE/2, 300 + layout.ISLAND_FADE, 400.])
    assert layout.island_fade(x).tolist() == pytest.approx([0., 0., .5, 1., 1.])
    assert np.all(np.diff(layout.island_fade(np.linspace(300, 330, 61))) >= 0)
