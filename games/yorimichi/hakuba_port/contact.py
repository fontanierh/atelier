"""Checks every exported copy of a ported placement against the surface the game draws under it, independently of
the exporter: none may be buried, and any that floats is listed.

    uv run python games/yorimichi/hakuba_port/contact.py [--leave-out]

It reads the exported full-detail tiles: each tile's ground mesh, as drawn, and each of its data nodes' copies, at the
positions the game spawns them, matched with the regions' placements by where they stand. A plant may also stand on a
ported prop, such as Belmonte's and Brinecove's ground pieces past the terrain, so plants are checked against the ground
and every ported prop copy around them, transformed as the tiles place it; a prop is checked against the ground alone,
so that none holds itself up. Under each point, the surface is the one nearest the copy's origin. Each copy's lowest
vertices (within `FOOT` of its lowest point, at most `POINTS` of them) are its foot, compared with the surface under
each one. A copy is buried if none of its vertices (at most `POINTS` of them) is above the surface under it, and adrift
if its whole foot is more than `ADRIFT` above it; either fails the check. A copy floats if its whole foot is more than
`FLOAT` above the surface, as a roof or a lantern may, and is sunk if its whole foot is more than `SUNK` under it, as a
foundation on a slope may; both are counted for review. With `--leave-out`, the forest's buried plants are removed from
its placements instead of failing, as ground cover a little inside the ground prop it stands on, for export again.
`mosaic` and `ground_at` read the ground pages, for the port's scripts that place models before export."""
import argparse
import functools
import json
import struct
import sys
import warnings
from pathlib import Path

import numpy as np

from ground import HAKUBA, WORLD, settings

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


class Drawn:
    """The surfaces the game draws: each full tile's ground mesh and, with `props`, the copies of the ported props
    standing in it and its neighbours, as the tiles place them; their triangles binned by the ground's squares."""

    def __init__(self, world, props=None):
        self.south_west, self.step = np.array(world['south_west_m']), world['ground_step_m']
        self.tile_m = world['tile_steps'] * self.step
        self.tiles = WORLD / 'tiles'
        self.props = props

    @functools.lru_cache(maxsize=64)
    def tile(self, i, j):
        """A tile's triangles as map (east, north) corners and heights, and each square's triangles; None where it
        draws none."""
        path = self.tiles / f'{i}_{j}.glb'
        if not path.is_file():
            return None
        doc, binary = glb(path)
        corners = []
        for node in doc.get('nodes', []):
            if node.get('name') != 'ground' or 'mesh' not in node:
                continue
            for primitive in doc['meshes'][node['mesh']]['primitives']:
                positions = accessor(doc, binary, primitive['attributes']['POSITION'])
                corners.append(positions[accessor(doc, binary, primitive['indices']).reshape(-1, 3)])
        if self.props is not None:
            corners.extend(self.supports(i, j))
        if not corners:
            return None
        tris = np.concatenate(corners).astype(np.float64)
        east, north, up = tris[..., 0], -tris[..., 2], tris[..., 1]
        x0 = self.south_west[0] + i * self.tile_m
        y0 = self.south_west[1] + j * self.tile_m
        side = int(round(self.tile_m / self.step))
        cx0 = np.floor((east.min(1) - x0) / self.step).astype(int)
        cx1 = np.floor((east.max(1) - x0) / self.step - 1e-9).astype(int)
        cy0 = np.floor((north.min(1) - y0) / self.step).astype(int)
        cy1 = np.floor((north.max(1) - y0) / self.step - 1e-9).astype(int)
        # A neighbour's prop may reach into this tile; only the part over its squares is kept.
        keep = (cx1 >= 0) & (cy1 >= 0) & (cx0 < side) & (cy0 < side)
        cx0, cx1 = np.clip(cx0, 0, side - 1), np.clip(cx1, 0, side - 1)
        cy0, cy1 = np.clip(cy0, 0, side - 1), np.clip(cy1, 0, side - 1)
        kept = np.flatnonzero(keep)
        if not len(kept):
            return None
        # Each triangle in every square its bounds cover.
        wide, high = cx1[kept] - cx0[kept] + 1, cy1[kept] - cy0[kept] + 1
        owners = np.repeat(kept, wide * high)
        within = np.arange(len(owners)) - np.repeat(np.cumsum(wide * high) - wide * high, wide * high)
        span = np.repeat(wide, wide * high)
        cells = (cy0[owners] + within // span) * side + cx0[owners] + within % span
        order = np.argsort(cells, kind='stable')
        cells, owners = cells[order], owners[order]
        starts = np.searchsorted(cells, np.arange(side * side))
        ends = np.searchsorted(cells, np.arange(side * side), side='right')
        return np.stack([east, north], -1), up, owners, starts, ends, x0, y0, side

    def supports(self, i, j):
        """The triangles, in the game's frame, of the ported prop copies the tile and its neighbours place."""
        return [shape for di in (-1, 0, 1) for dj in (-1, 0, 1) for shape in self.placed_props(i + di, j + dj)]

    @functools.lru_cache(maxsize=256)
    def placed_props(self, i, j):
        """The triangles, in the game's frame, of the ported prop copies one tile places."""
        path = self.tiles / f'{i}_{j}.glb'
        if not path.is_file():
            return []
        doc, _ = glb(path)
        found = []
        for node in doc.get('nodes', []):
            extras = node.get('extras') or {}
            model = node.get('name', '')
            if extras.get('detail') != 'full' or model not in self.props:
                continue
            shape = full_triangles(model)
            if shape is None:
                continue
            rows = np.array(extras['instances'], float).reshape(-1, 5)
            rows = rows[[tuple(at) in self.props[model] for at in stored(rows[:, [0, 2]] * (1, -1))]]
            px, py, pz = shape[None, ..., 0], shape[None, ..., 1], shape[None, ..., 2]
            x, y, z, yaw, scale = (rows[:, k, None, None] for k in range(5))
            found.extend(np.stack([x + scale * (np.cos(yaw) * px + np.sin(yaw) * pz), y + scale * py,
                                   z + scale * (-np.sin(yaw) * px + np.cos(yaw) * pz)], -1))
        return found

    def heights(self, x, y, near):
        """The height of the drawn surface under map points (`x`, `y`) nearest to heights `near`; NaN where none is
        drawn."""
        x, y, near = (np.asarray(v, float).ravel() for v in (x, y, near))
        out = np.full(len(x), np.nan)
        ti = np.floor((x - self.south_west[0]) / self.tile_m).astype(int)
        tj = np.floor((y - self.south_west[1]) / self.tile_m).astype(int)
        for i, j in set(zip(ti.tolist(), tj.tolist())):
            tile = self.tile(i, j)
            if tile is None:
                continue
            flat, up, owners, starts, ends, x0, y0, side = tile
            pick = np.flatnonzero((ti == i) & (tj == j))
            px, py, seat = x[pick], y[pick], near[pick]
            cell = (np.clip(np.floor((py - y0) / self.step), 0, side - 1).astype(int) * side
                    + np.clip(np.floor((px - x0) / self.step), 0, side - 1).astype(int))
            first, count = starts[cell], ends[cell] - starts[cell]
            found, apart = np.full(len(pick), np.nan), np.full(len(pick), np.inf)
            for k in range(int(count.max(initial=0))):
                rows = np.flatnonzero(k < count)
                t = owners[first[rows] + k]
                a, b, c = flat[t, 0], flat[t, 1], flat[t, 2]
                q = np.stack([px[rows], py[rows]], -1)
                v0, v1, v2 = b - a, c - a, q - a
                den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
                # A wall, upright, has no area seen from above and holds nothing up.
                with np.errstate(divide='ignore', invalid='ignore'):
                    u = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
                    v = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
                    inside = (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
                    h = up[t, 0] + u * (up[t, 1] - up[t, 0]) + v * (up[t, 2] - up[t, 0])
                rows, h = rows[inside], h[inside]
                nearer = np.abs(h - seat[rows]) < apart[rows]
                rows, h = rows[nearer], h[nearer]
                found[rows], apart[rows] = h, np.abs(h - seat[rows])
            out[pick] = found
        return out


@functools.lru_cache(maxsize=None)
def full_triangles(model):
    """A Hakuba model's `full` triangles, in its glTF frame, or None for a model with no source."""
    source = HAKUBA / model / 'src' / 'model.glb'
    if not source.is_file():
        return None
    doc, binary = glb(source)
    return np.concatenate([accessor(doc, binary, primitive['attributes']['POSITION'])[
        accessor(doc, binary, primitive['indices']).reshape(-1, 3)]
        for node in doc['nodes'] if node.get('name') == 'full'
        for primitive in doc['meshes'][node['mesh']]['primitives']]).astype(np.float64)


def full_positions(path):
    """The positions of a model's `full` node, in its glTF frame."""
    doc, binary = glb(path)
    return np.concatenate([accessor(doc, binary, primitive['attributes']['POSITION'])
                           for node in doc['nodes'] if node.get('name') == 'full'
                           for primitive in doc['meshes'][node['mesh']]['primitives']]).astype(np.float64)


@functools.lru_cache(maxsize=None)
def points_of(model):
    """A Hakuba model's foot (its vertices within `FOOT` of its lowest point) and body (its vertices from low to high),
    at most `POINTS` of each, or None for a model with no source."""
    source = HAKUBA / model / 'src' / 'model.glb'
    if not source.is_file():
        return None
    points = np.unique(full_positions(source), axis=0)
    up = points[:, 1]
    foot = np.flatnonzero(up <= up.min() + FOOT)
    # Evenly spread through the foot and the body, keeping a large group's check small.
    foot = foot[np.linspace(0, len(foot) - 1, min(len(foot), POINTS)).astype(int)]
    body = np.argsort(up)[np.linspace(0, len(up) - 1, min(len(up), POINTS)).astype(int)]
    return points[foot], points[body]


def placed(drawn, rows, points):
    """The heights of a model's `points` in each copy (`rows` of game-frame x, y, z, yaw in radians, scale), turned
    about up and scaled as the game spawns it, and of the drawn surface under each, NaN where none is drawn."""
    yaw, scale = rows[:, 3:4], rows[:, 4:5]
    px, py, pz = points[:, 0], points[:, 1], points[:, 2]
    gx = rows[:, :1] + scale * (np.cos(yaw) * px + np.sin(yaw) * pz)
    gz = rows[:, 2:3] + scale * (-np.sin(yaw) * px + np.cos(yaw) * pz)
    gy = rows[:, 1:2] + scale * py
    # Every point of a copy is seated on the surface nearest the copy's origin: a plant beside a rock stands on the
    # ground, and one sunk into the rock on the rock.
    return gy, drawn.heights(gx, -gz, np.broadcast_to(rows[:, 1:2], gx.shape)).reshape(gx.shape)


def showing(height, ground):
    """Whether any point of each copy shows: one over no ground does, and so does one within `FLUSH` of the ground, as
    a leaf lying on it. A copy none of whose points shows is buried."""
    return (~(height < ground - FLUSH)).any(axis=1)


def stored(at):
    """Map points (east, north) at the single precision the exporter stores them in, to match a placement with its
    exported copy exactly."""
    return np.asarray(at, float).astype(np.float32)


def glb(path):
    data = path.read_bytes()
    length = struct.unpack_from('<I', data, 12)[0]
    return json.loads(data[20:20 + length]), data[20 + length + 8:]


def accessor(doc, binary, index):
    acc = doc['accessors'][index]
    view = doc['bufferViews'][acc['bufferView']]
    kind = {5126: '<f4', 5125: '<u4', 5123: '<u2', 5121: 'u1'}[acc['componentType']]
    width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[acc['type']]
    start = view.get('byteOffset', 0) + acc.get('byteOffset', 0)
    return np.frombuffer(binary, kind, acc['count'] * width, start).reshape(-1, width).squeeze(-1) \
        if width == 1 else np.frombuffer(binary, kind, acc['count'] * width, start).reshape(-1, width)


def ported_copies():
    """The ported copies: each model's placements, by where they stand, so that Hakuba's own copies of the same model
    are left to Hakuba's checks."""
    ported = {}
    for path in (WORLD / 'src' / 'regions').glob('*/placements.json'):
        for group in json.loads(path.read_text())['groups']:
            ported.setdefault(group['model'], set()).update(map(tuple, stored(
                np.array(group['instances'], float).reshape(-1, 5)[:, :2])))
    return ported


def supports(world, ported=None):
    """The surfaces a plant may stand on: a ported prop, a deck or a ground piece, as well as the ground; a prop stands
    on the ground alone, so that none holds itself up."""
    ported = ported_copies() if ported is None else ported
    return Drawn(world, {model: at for model, at in ported.items() if model.startswith('props/')})


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--leave-out', action='store_true',
                        help="remove the forest's buried plants from its placements")
    args = parser.parse_args()
    world = settings()
    drawn = Drawn(world)
    failed, sunk, floating, checked, found, buried = [], {}, {}, 0, 0, {}
    ported = ported_copies()
    supported = supports(world, ported)
    tiles = sorted(p for p in drawn.tiles.glob('*_*.glb') if not p.name.endswith('.middle.glb'))
    # Row by row, so that a tile's neighbours stay cached.
    tiles.sort(key=lambda p: tuple(int(n) for n in p.stem.split('_'))[::-1])
    for path in tiles:
        doc, _ = glb(path)
        for node in doc.get('nodes', []):
            extras = node.get('extras') or {}
            if 'instances' not in extras or extras.get('detail') != 'full':
                continue
            model = node['name']
            if model not in ported:
                continue
            seated = points_of(model)
            if seated is None:
                continue
            foot, body = seated
            rows = np.array(extras['instances'], float).reshape(-1, 5)
            rows = rows[[tuple(at) in ported[model] for at in stored(rows[:, [0, 2]] * (1, -1))]]
            found += len(rows)
            surface = supported if model.startswith('plants/') else drawn
            height, ground = placed(surface, rows, foot)
            over = ~np.isnan(ground)
            seen = over.any(axis=1)
            checked += int(seen.sum())
            gap = np.where(over, height - ground, np.nan)
            body_height, body_ground = placed(surface, rows, body)
            shows = showing(body_height, body_ground)
            with np.errstate(all='ignore'), warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                lowest, highest = np.nanmin(gap, axis=1), np.nanmax(gap, axis=1)
                top = np.nanmax(body_height - body_ground, axis=1)
            region = model.split('/')[1].split('-')[0]
            for i in np.flatnonzero(seen):
                where = f'{model} at {rows[i, 0]:.1f}, {-rows[i, 2]:.1f} ({path.stem})'
                if not shows[i]:
                    failed.append(f'{where}: buried, its top {-top[i]:.2f} m under')
                    buried[model, tuple(stored([rows[i, 0], -rows[i, 2]]))] = failed[-1]
                elif lowest[i] > ADRIFT:
                    failed.append(f'{where}: adrift {lowest[i]:.0f} m above the ground')
                elif highest[i] < -SUNK:
                    sunk.setdefault(region, []).append(f'{where}: {-highest[i]:.2f} m under')
                elif lowest[i] > FLOAT:
                    floating.setdefault(region, []).append(f'{where}: {lowest[i]:.2f} m above')
    total = sum(map(len, ported.values()))
    print(f'{found} of {total} ported copies found in the full tiles, {checked} of them over a drawn surface checked')
    for kind, found in (('float', floating), ('sunk', sunk)):
        for group, items in sorted(found.items()):
            print(f'{group}: {len(items)} {kind}, such as {"; ".join(items[:3])}')
    if args.leave_out:
        return leave_out(buried, failed)
    for item in failed:
        print('FAIL', item)
    return 1 if failed else 0


def leave_out(buried, failed):
    """Removes the forest's buried plants from its placements; every other failure still fails."""
    path = WORLD / 'src' / 'regions' / 'forest' / 'placements.json'
    groups, removed = json.loads(path.read_text())['groups'], set()
    for group in groups:
        rows = group['instances']
        keys = [(group['model'], tuple(at)) for at in stored(np.array(rows, float).reshape(-1, 5)[:, :2])]
        removed.update(key for key in keys if key in buried)
        group['instances'] = [row for row, key in zip(rows, keys) if key not in buried]
    groups = [group for group in groups if group['instances']]
    # Written as `plants.py` writes it, one group a line.
    text = json.dumps({'groups': groups}, separators=(',', ':'))
    path.write_text(text.replace('{"model"', '\n{"model"') + '\n')
    print(f'{len(removed)} buried forest plants left out of {path.name}')
    others = [item for item in failed if item not in {buried[key] for key in removed}]
    for item in others:
        print('FAIL', item)
    return 1 if others else 0

if __name__ == '__main__':
    sys.exit(main())
