"""Samples the island's ported terrain cells into Hakuba's shared ground pages, so its land is one grid of heights.

    uv run python games/yorimichi/hakuba_port/ground.py

Reads each terrain cell in `LAYERS` where its region's `placements.json` stands it, the highest surface where cells
overlap, and writes for each page `world/src/ground/<column>_<row>.bin`, 257 × 257 little-endian f32 heights 2 m apart, rows
from the south, NaN where no cell covers a point (the sea), and `world/src/ground/colours/<column>_<row>.bin`, the
cells' vertex colour at each point as sRGB bytes and an alpha of 255, or 0 where no cell gave one. The start's
terrain inside `START`, and any ground a page already has, keep their heights: a region sampled later only fills the
land the pages lack. The cells are then the ground's, so their props and placements are removed: run it once after
`port.py` brings a region's terrain."""
import json
import math
import shutil
import struct
import sys
from pathlib import Path

import numpy as np

HAKUBA = Path(__file__).resolve().parents[2] / 'hakuba' / 'assets'
WORLD = HAKUBA / 'world'
# Each region's terrain cells, by the start of their prop names.
LAYERS = [('far-hills', 'far-hills-cell-'), ('southwest', 'southwest-island-cell-'),
          ('hidamari', 'hidamari-terrain-cell-'), ('hidamari', 'hidamari-north-mountains-cell-'),
          ('brinecove', 'brinecove-ground-'),
          ('belmonte', 'belmonte-bt-terrain-'), ('belmonte', 'belmonte-north-country-'),
          ('belmonte', 'belmonte-north-apron-')]
# The start's own terrain, authored in Hakuba: west, south, east, north in metres.
START = (-300.0, -300.0, 300.0, 300.0)


def settings():
    """The ground grid's settings from the world's `asset.toml`."""
    import tomllib
    return tomllib.loads((WORLD / 'asset.toml').read_text())


def triangles(glb):
    """A source GLB's triangles as an (n, 3, 3) array of glTF positions and their corners' (n, 3, 3) linear colours."""
    data = glb.read_bytes()
    length = struct.unpack_from('<I', data, 12)[0]
    doc = json.loads(data[20:20 + length])
    binary = data[20 + length + 8:]

    def accessor(index, dtype, width):
        acc = doc['accessors'][index]
        view = doc['bufferViews'][acc['bufferView']]
        start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
        return np.frombuffer(binary, dtype, acc['count'] * width, start).reshape(-1, width)

    corners, colours = [], []
    for node in doc['nodes']:
        if node.get('name') != 'full':
            continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            positions = accessor(primitive['attributes']['POSITION'], '<f4', 3)
            colour = accessor(primitive['attributes']['COLOR_0'], '<f4', 4)[:, :3]
            kind = doc['accessors'][primitive['indices']]['componentType']
            indices = accessor(primitive['indices'], '<u2' if kind == 5123 else '<u4', 1).ravel().reshape(-1, 3)
            corners.append(positions[indices])
            colours.append(colour[indices])
    return np.concatenate(corners).astype(np.float64), np.concatenate(colours).astype(np.float64)


def rasterise(heights, colours, tris, tri_colours, origin, step):
    """Writes each triangle's height and colour at every grid point inside it where it is the highest yet, the
    surface seen and stood on where two cells overlap; both are indexed [north, east]."""
    for (a, b, c), (ca, cb, cc) in zip(tris, tri_colours):
        low = np.floor((np.minimum(np.minimum(a, b), c)[:2] - origin) / step).astype(int)
        high = np.ceil((np.maximum(np.maximum(a, b), c)[:2] - origin) / step).astype(int)
        i0, j0 = max(low[0], 0), max(low[1], 0)
        i1, j1 = min(high[0], heights.shape[1] - 1), min(high[1], heights.shape[0] - 1)
        if i0 > i1 or j0 > j1:
            continue
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(det) < 1e-12:
            continue
        ii, jj = np.meshgrid(np.arange(i0, i1 + 1), np.arange(j0, j1 + 1))
        x, y = origin[0] + ii * step, origin[1] + jj * step
        u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / det
        v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / det
        w = 1.0 - u - v
        height = u * a[2] + v * b[2] + w * c[2]
        current = heights[jj, ii]
        inside = (u >= -1e-6) & (v >= -1e-6) & (w >= -1e-6) & (np.isnan(current) | (height > current))
        heights[jj[inside], ii[inside]] = height[inside]
        colours[jj[inside], ii[inside]] = (u[..., None] * ca + v[..., None] * cb + w[..., None] * cc)[inside]


def srgb(linear):
    """Linear colours as sRGB bytes."""
    c = np.clip(linear, 0.0, 1.0)
    return np.round(255 * np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)).astype(np.uint8)


def cells():
    """Every terrain cell's triangles and corner colours on the map, x east, y north, z up, layer by layer."""
    for region, prefix in LAYERS:
        path = WORLD / 'src' / 'regions' / region / 'placements.json'
        if not path.is_file():
            continue
        groups = json.loads(path.read_text())['groups']
        for group in groups:
            if not group['model'].startswith('props/' + prefix):
                continue
            tris, colours = triangles(HAKUBA / group['model'] / 'src' / 'model.glb')
            # glTF is y up with -z north; a cell turns counter-clockwise seen from above by its yaw in degrees.
            east, north, up = tris[..., 0], -tris[..., 2], tris[..., 1]
            for x, y, z, yaw, scale in group['instances']:
                turn = math.radians(yaw)
                cos, sin = math.cos(turn), math.sin(turn)
                yield np.stack([x + scale * (cos * east - sin * north), y + scale * (sin * east + cos * north),
                                z + scale * up], axis=-1), colours


def main():
    world = settings()
    step = world['ground_step_m']
    page_steps = world['page_steps']
    page_m = step * page_steps
    south_west = np.array(world['south_west_m'])
    layers = list(cells())
    corners = np.concatenate([tris[..., :2].reshape(-1, 2) for tris, _ in layers])
    first = np.floor((corners.min(0) - south_west) / page_m).astype(int)
    last = np.floor((corners.max(0) - south_west) / page_m).astype(int)
    columns, rows = range(first[0], last[0] + 1), range(first[1], last[1] + 1)
    origin = south_west + first * page_m
    size = np.array([len(columns), len(rows)]) * page_steps + 1
    heights = np.full((size[1], size[0]), np.nan)
    colours = np.full((size[1], size[0], 3), np.nan)
    for tris, tri_colours in layers:
        rasterise(heights, colours, tris, tri_colours, origin, step)
    west, south, east, north = START
    (WORLD / world['ground'] / 'colours').mkdir(exist_ok=True)
    written = 0
    for column in columns:
        for row in rows:
            i0, j0 = (column - first[0]) * page_steps, (row - first[1]) * page_steps
            page = heights[j0:j0 + page_steps + 1, i0:i0 + page_steps + 1].copy()
            colour = colours[j0:j0 + page_steps + 1, i0:i0 + page_steps + 1].copy()
            path = WORLD / world['ground'] / f'{column}_{row}.bin'
            x = south_west[0] + (column * page_steps + np.arange(page_steps + 1)) * step
            y = south_west[1] + (row * page_steps + np.arange(page_steps + 1)) * step
            start = (y[:, None] >= south) & (y[:, None] <= north) & (x[None, :] >= west) & (x[None, :] <= east)
            known = ~np.isnan(colour[..., 0])
            rgba = np.zeros(colour.shape[:2] + (4,), np.uint8)
            rgba[known, :3] = srgb(colour[known])
            rgba[known, 3] = 255
            colour_path = WORLD / world['ground'] / 'colours' / f'{column}_{row}.bin'
            if path.is_file():
                # Ground the page already has keeps its heights and colours: a later region's terrain only fills
                # the land the pages lack. Belmonte's north country overlaps the island's hills south of its apron,
                # where the island's ground, not the north country's ramp, meets the apron.
                old = np.fromfile(path, '<f4').reshape(page_steps + 1, page_steps + 1).astype(np.float64)
                keep = start | np.isnan(page) | ~np.isnan(old)
                page[keep] = old[keep]
                old_rgba = (np.fromfile(colour_path, np.uint8).reshape(rgba.shape) if colour_path.is_file()
                            else np.zeros_like(rgba))
                rgba[keep] = old_rgba[keep]
            if np.isnan(page).all():
                continue
            page.astype('<f4').tofile(path)
            rgba.tofile(colour_path)
            written += 1
    print(f'wrote {written} pages over columns {columns.start}..{columns.stop - 1}, rows {rows.start}..{rows.stop - 1}')
    consume()


def consume():
    """Removes the terrain cells' placements and props, which the ground pages now hold."""
    removed = 0
    for region, prefix in LAYERS:
        path = WORLD / 'src' / 'regions' / region / 'placements.json'
        if not path.is_file():
            continue
        document = json.loads(path.read_text())
        kept = [g for g in document['groups'] if not g['model'].startswith('props/' + prefix)]
        for group in document['groups']:
            if group not in kept:
                shutil.rmtree(HAKUBA / group['model'])
                removed += 1
        # Written as port.py writes it: one group a line.
        text = json.dumps({'groups': kept}, separators=(',', ':'))
        path.write_text(text.replace('{"model"', '\n{"model"') + '\n')
    print(f'removed {removed} terrain props')


if __name__ == '__main__':
    sys.exit(main())
