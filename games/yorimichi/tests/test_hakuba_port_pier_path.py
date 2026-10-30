"""Sunset Pier's path in from the coast is an authored ground surface in Hakuba's `skatepark` region
(`regions/skatepark/path-source.json`). Its whole edge must meet what it abuts, from the exported data on both sides,
as `seamless-surface-boundaries` asks: its own edge bands and the deck in the pier's props, and the coast road's
edge in `momiji-coast`. The ground under it must stay a declared clearance below it.

The edge is sampled every `STEP` along its whole length. Each sample must lie on a surface facing up on the other
side within `PLAN` in plan and `HEIGHT` in height: the props stand at placements stored to 0.1 mm and the path's
corners are stored to 0.1 mm, so both are a few tenths of a millimetre, nothing a slit or step could hide in.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

PORT = Path(__file__).resolve().parents[1] / 'hakuba_port'
sys.path.insert(0, str(PORT))
import contact  # noqa: E402
import ground  # noqa: E402

REGIONS = ground.WORLD / 'src' / 'regions'
PATH = REGIONS / 'skatepark' / 'path-source.json'
PIER = REGIONS / 'skatepark' / 'placements.json'
ROAD = REGIONS / 'momiji-coast' / 'road-source.json'
STEP = 0.25
PLAN = 0.0005
HEIGHT = 0.0005
# The ground's least depth under the path, in metres.
CLEARANCE = 0.05
# The seam's two ends: the path's end on the coast road and its end on the deck, (west, south, east, north).
ROAD_END = (-158.0, -86.0, -151.0, -82.0)
DECK_END = (-107.0, -168.5, -101.0, -167.5)


def lfs(path):
    return path.read_bytes()[:8] == b'version '


def path_triangles():
    return np.array([t['xyz'] for s in json.loads(PATH.read_text())['surfaces'] for t in s['triangles']], float)


def facing_up(triangles):
    n = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    return triangles[n[:, 2] > 0.5 * np.linalg.norm(n, axis=1)]


def pier_props():
    """The pier props' triangles, as placed, in map metres; the floor paint (decals) is not a surface."""
    found = []
    for group in json.loads(PIER.read_text())['groups']:
        if 'decals' in group['model']:
            continue
        shape = contact.full_triangles(group['model'])
        for x, y, z, yaw, scale in np.array(group['instances'], float).reshape(-1, 5):
            assert yaw == 0 and scale == 1, 'the pier stands unturned'
            found.append(np.stack([x + shape[..., 0], y - shape[..., 2], z + shape[..., 1]], -1))
    return np.concatenate(found)


def road_triangles():
    return np.array([t['xyz'] for t in json.loads(ROAD.read_text())['triangles']], float)


def edge(triangles):
    """The open edges of a triangle set, its corners matched to 1 mm, as (n, 2, 3) segments at the stored corners."""
    count, at = {}, {}
    for t in triangles:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ka, kb = tuple(np.round(t[a], 3)), tuple(np.round(t[b], 3))
            at[ka], at[kb] = t[a], t[b]
            pair = tuple(sorted((ka, kb)))
            count[pair] = count.get(pair, 0) + 1
    return [(at[a], at[b]) for (a, b), n in count.items() if n == 1]


def samples(segments):
    out = []
    for a, b in segments:
        n = max(1, int(np.ceil(np.linalg.norm(b[:2] - a[:2]) / STEP)))
        out += [a + (b - a) * k / n for k in range(n + 1)]
    return np.array(out)


def heights(triangles, points, reach):
    """For each point, the heights of `triangles` within `reach` of it in plan, at their nearest point to it."""
    cell = 1.0
    lo = np.floor((triangles[..., :2].min(1) - reach) / cell).astype(int)
    hi = np.floor((triangles[..., :2].max(1) + reach) / cell).astype(int)
    bins = {}
    for k, ((x0, y0), (x1, y1)) in enumerate(zip(lo, hi)):
        for i in range(x0, x1 + 1):
            for j in range(y0, y1 + 1):
                bins.setdefault((i, j), []).append(k)
    out = []
    for p in points:
        rows = bins.get(tuple(np.floor(p[:2] / cell).astype(int)), [])
        if not rows:
            out.append(np.array([]))
            continue
        a, b, c = (triangles[rows, k] for k in range(3))
        v0, v1, v2 = b[:, :2] - a[:, :2], c[:, :2] - a[:, :2], p[:2] - a[:, :2]
        den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
        u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
        v = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
        inside = (u >= 0) & (v >= 0) & (u + v <= 1)
        h = np.where(inside, a[:, 2] + u * (b[:, 2] - a[:, 2]) + v * (c[:, 2] - a[:, 2]), np.nan)
        apart = np.where(inside, 0.0, np.inf)
        for s, e in ((a, b), (b, c), (c, a)):
            d = e - s
            t = np.clip(((p[:2] - s[:, :2]) * d[:, :2]).sum(1) / np.maximum((d[:, :2] ** 2).sum(1), 1e-18), 0, 1)
            q = s + t[:, None] * d
            off = np.linalg.norm(q[:, :2] - p[:2], axis=1)
            nearer = off < apart
            apart, h = np.where(nearer, off, apart), np.where(nearer, q[:, 2], h)
        out.append(h[apart <= reach])
    return out


@pytest.fixture(scope='module')
def path():
    return path_triangles()


@pytest.fixture(scope='module')
def neighbours():
    if any(lfs(p) for p in (REGIONS.parent.parent.parent / 'props').glob('skatepark-path-*/src/model.glb')):
        pytest.skip('the pier props are Git LFS pointers here')
    return facing_up(pier_props()), facing_up(road_triangles())


def test_path_edge_is_one_closed_loop(path):
    segments = edge(path)
    ends = {}
    for a, b in segments:
        for p in (a, b):
            key = tuple(np.round(p, 3))
            ends[key] = ends.get(key, 0) + 1
    # The paving and its joints share every inner edge, so only the outline is open, each corner on two of its edges.
    assert set(ends.values()) == {2}
    assert len(segments) == len(ends)


def test_path_edge_meets_the_deck_its_bands_and_the_road(path, neighbours):
    props, road = neighbours
    points = samples(edge(path))
    off = np.full(len(points), np.inf)
    by = np.full(len(points), '', object)
    for name, triangles in (('pier', props), ('road', road)):
        for k, found in enumerate(heights(triangles, points, PLAN)):
            if len(found) and np.abs(found - points[k, 2]).min() < off[k]:
                off[k], by[k] = np.abs(found - points[k, 2]).min(), name
    missing = points[off > HEIGHT]
    assert not len(missing), f'{len(missing)} of {len(points)} edge samples meet nothing, first {missing[:3].round(4)}'

    # Both ends are covered: the road owns the north end, the deck the south end.
    def within(box):
        west, south, east, north = box
        return (points[:, 0] >= west) & (points[:, 0] <= east) & (points[:, 1] >= south) & (points[:, 1] <= north)
    assert (by[within(ROAD_END)] == 'road').sum() >= 10
    assert (by[within(DECK_END)] == 'pier').sum() >= 10


def test_ground_stays_under_the_path(path):
    world = ground.settings()
    pages = sorted((ground.WORLD / world['ground']).glob('*.bin'))
    if not pages or lfs(pages[0]):
        pytest.skip('the ground pages are Git LFS pointers here')
    heights_ = contact.mosaic(world)
    rng = np.random.default_rng(0)
    weights = rng.random((24, 2))
    weights[weights.sum(1) > 1] = 1 - weights[weights.sum(1) > 1]
    inner = (path[:, None, 0] + weights[None, :, :1] * (path[:, None, 1] - path[:, None, 0])
             + weights[None, :, 1:] * (path[:, None, 2] - path[:, None, 0]))
    points = np.concatenate([path.reshape(-1, 3), inner.reshape(-1, 3)])
    under = contact.ground_at(heights_, world['south_west_m'], world['ground_step_m'], points[:, 0], points[:, 1])
    assert not np.isnan(under).any()
    depth = points[:, 2] - under
    assert depth.min() >= CLEARANCE, f'the ground reaches {depth.min():.3f} m under the path'


def test_path_stays_off_the_road(path):
    road = facing_up(road_triangles())
    centres = path.mean(1)
    over = [k for k, found in enumerate(heights(road, centres, 0.0)) if len(found)]
    assert not over, f'{len(over)} path triangles lie over the road'
