"""Checks every ported model against Hakuba's ground, independently of the exporter: none may be buried, and any
that floats is listed.

    uv run python games/yorimichi/hakuba_port/contact.py

For each instance in a region's `placements.json`, its model's lowest vertices (within `FOOT` of its lowest point,
at most `POINTS` of them) are its foot. The model stands at its height or, for a group on the ground, that far above
the ground under its origin; each foot vertex is compared with the ground pages' height under it, blended as the
exporter blends it. A model is buried if none of its vertices (at most `POINTS` of them) is above the ground under
it, and adrift if its whole foot is more than `ADRIFT` above the ground; either fails the check, as does a model on
the ground whose origin is off it. A model floats if its whole foot is more than `FLOAT` above the ground, as a roof
or a lantern may, and is sunk if its whole foot is more than `SUNK` under it, as a foundation on a slope may; both
are counted for review."""
import json
import sys
from pathlib import Path

import numpy as np

from ground import HAKUBA, WORLD, settings, triangles

FOOT = 0.25
FLOAT = 0.3
SUNK = 3.0
ADRIFT = 100.0
POINTS = 64
FLUSH = 0.005


def mosaic(world):
    """Every ground page as one array, indexed [north, east] from the world's south-west corner, NaN off the ground."""
    steps = world['page_steps']
    pages = {tuple(map(int, p.stem.split('_'))): p for p in (WORLD / world['ground']).glob('*.bin')}
    columns = max(c for c, _ in pages) + 1
    rows = max(r for _, r in pages) + 1
    heights = np.full((rows * steps + 1, columns * steps + 1), np.nan, np.float32)
    for (c, r), path in pages.items():
        page = np.fromfile(path, '<f4').reshape(steps + 1, steps + 1)
        block = heights[r * steps:r * steps + steps + 1, c * steps:c * steps + steps + 1]
        block[~np.isnan(page)] = page[~np.isnan(page)]
    return heights


def ground_at(heights, south_west, step, x, y):
    """The ground's height at map points (`x`, `y`), blended between the four nearest heights; NaN off the ground."""
    fx, fy = (x - south_west[0]) / step, (y - south_west[1]) / step
    i, j = np.floor(fx).astype(int), np.floor(fy).astype(int)
    ok = (i >= 0) & (j >= 0) & (i < heights.shape[1] - 1) & (j < heights.shape[0] - 1)
    i, j = np.where(ok, i, 0), np.where(ok, j, 0)
    u, v = fx - i, fy - j
    h = (heights[j, i] * (1 - u) * (1 - v) + heights[j, i + 1] * u * (1 - v)
         + heights[j + 1, i] * (1 - u) * v + heights[j + 1, i + 1] * u * v)
    return np.where(ok, h, np.nan)


def main():
    world = settings()
    heights = mosaic(world)
    south_west, step = np.array(world['south_west_m']), world['ground_step_m']
    feet = {}
    failed, sunk, floating, checked = [], {}, {}, 0
    for path in sorted((WORLD / 'src' / 'regions').glob('*/placements.json')):
        region = path.parent.name
        for group in json.loads(path.read_text())['groups']:
            model = group['model']
            if model not in feet:
                source = HAKUBA / model / 'src' / 'model.glb'
                if not source.is_file():
                    continue
                tris, _ = triangles(source)
                points = np.unique(tris.reshape(-1, 3), axis=0)
                east, north, up = points[:, 0], -points[:, 2], points[:, 1]
                low = up.min()
                foot = np.flatnonzero(up <= low + FOOT)
                # At most `POINTS` of the foot, evenly spread through it, keep a large group's check small.
                foot = foot[np.linspace(0, len(foot) - 1, min(len(foot), POINTS)).astype(int)]
                # And at most `POINTS` of all its vertices, from low to high, to tell whether any shows.
                body = np.argsort(up)[np.linspace(0, len(up) - 1, min(len(up), POINTS)).astype(int)]
                feet[model] = (east[foot], north[foot], up[foot], (east[body], north[body], up[body]))
            east, north, up, body = feet[model]
            rows = np.array(group['instances'], float).reshape(-1, 5)
            x, y, z, scale = rows[:, :1], rows[:, 1:2], rows[:, 2], rows[:, 4:5]
            turn = np.radians(rows[:, 3:4])
            def under(east, north):
                # The ground under each of the model's points, for each instance.
                fx = x + scale * (np.cos(turn) * east - np.sin(turn) * north)
                fy = y + scale * (np.sin(turn) * east + np.cos(turn) * north)
                return ground_at(heights, south_west, step, fx, fy)

            ground = under(east, north)
            centre = ground_at(heights, south_west, step, x[:, 0], y[:, 0])
            if group.get('on_ground'):
                # A height on the ground is an offset above the ground under the model's origin.
                z = z + centre
            over = ~np.isnan(ground)
            seen = over.any(axis=1)
            checked += int(seen.sum())
            gap = np.where(over, z[:, None] + scale * up - ground, np.nan)
            # A point over no ground shows, and so does one within `FLUSH` of the ground, as a leaf lying on it.
            showing = ~(z[:, None] + scale * body[2] <= under(body[0], body[1]) + FLUSH)
            with np.errstate(all='ignore'):
                lowest, highest = np.nanmin(gap, axis=1), np.nanmax(gap, axis=1)
            for i in np.flatnonzero(seen):
                where = f'{region} {model} at {x[i, 0]:.1f}, {y[i, 0]:.1f}'
                if np.isnan(z[i]):
                    failed.append(f'{where}: stands on the ground but its origin is off it')
                elif not showing[i].any():
                    failed.append(f'{where}: buried')
                elif lowest[i] > ADRIFT:
                    failed.append(f'{where}: adrift {lowest[i]:.0f} m above the ground')
                elif highest[i] < -SUNK:
                    sunk.setdefault(region, []).append(f'{where}: {-highest[i]:.2f} m under')
                elif lowest[i] > FLOAT:
                    floating.setdefault(region, []).append(f'{where}: {lowest[i]:.2f} m above')
    print(f'{checked} instances over the ground checked')
    for kind, found in (('float', floating), ('sunk', sunk)):
        for region, items in sorted(found.items()):
            print(f'{region}: {len(items)} {kind}, such as {"; ".join(items[:3])}')
    for item in failed:
        print('FAIL', item)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
