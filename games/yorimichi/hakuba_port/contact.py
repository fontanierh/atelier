"""Checks every ported model against Hakuba's ground, independently of the exporter: none may be buried, and any
that floats is listed.

    uv run python games/yorimichi/hakuba_port/contact.py

For each instance in a region's `placements.json`, its model's lowest vertices (within `FOOT` of its lowest point)
are its foot, compared with the ground pages' height under each, blended as the exporter blends it. A model is buried
if its highest point is below the ground under its centre, and adrift if its whole foot is more than `ADRIFT` above
the ground; either fails the check. A model floats if its whole foot is more than `FLOAT` above the ground, as a roof
or a lantern may, and is sunk if its whole foot is more than `SUNK` under it, as a foundation on a slope may; both
are counted for review."""
import json
import math
import sys
from pathlib import Path

import numpy as np

from ground import HAKUBA, WORLD, settings, triangles

FOOT = 0.25
FLOAT = 0.3
SUNK = 3.0
ADRIFT = 100.0


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
                foot = up <= low + FOOT
                feet[model] = (east[foot], north[foot], up[foot], up.max())
            east, north, up, top = feet[model]
            for x, y, z, yaw, scale in group['instances']:
                turn = math.radians(yaw)
                cos, sin = math.cos(turn), math.sin(turn)
                fx, fy = x + scale * (cos * east - sin * north), y + scale * (sin * east + cos * north)
                ground = ground_at(heights, south_west, step, fx, fy)
                over = ~np.isnan(ground)
                if not over.any():
                    continue
                checked += 1
                gap = z + scale * up[over] - ground[over]
                centre = ground_at(heights, south_west, step, np.array([x]), np.array([y]))[0]
                where = f'{region} {model} at {x:.1f}, {y:.1f}'
                if not np.isnan(centre) and z + scale * top < centre:
                    failed.append(f'{where}: buried')
                elif gap.min() > ADRIFT:
                    failed.append(f'{where}: adrift {gap.min():.0f} m above the ground')
                elif gap.max() < -SUNK:
                    sunk.setdefault(region, []).append(f'{where}: {-gap.max():.2f} m under')
                elif gap.min() > FLOAT:
                    floating.setdefault(region, []).append(f'{where}: {gap.min():.2f} m above')
    print(f'{checked} instances over the ground checked')
    for kind, found in (('float', floating), ('sunk', sunk)):
        for region, items in sorted(found.items()):
            print(f'{region}: {len(items)} {kind}, such as {"; ".join(items[:3])}')
    for item in failed:
        print('FAIL', item)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
