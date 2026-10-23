"""Publish one lot's placements and exact final-terrain query values, without exporting meshes."""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from houses.layout import HALF_W, BACK, front_y, to_world  # noqa: E402

FIELDS = ('name', 'house', 'variant', 'level', 'front', 'gate', 'garden', 'gate_verge', 'centre', 'yaw')


def queries(lot):
    """The original wall-foot queries; a new constructor query must refuse until declared."""
    def yf(x):
        return float(front_y(lot, x))
    points = []
    for (xa, ya), (xb, yb) in (((-HALF_W, yf(-HALF_W)), (-HALF_W, BACK)),
                              ((-HALF_W, BACK), (HALF_W, BACK)),
                              ((HALF_W, BACK), (HALF_W, yf(HALF_W)))):
        length = math.hypot(xb - xa, yb - ya)
        dx, dy = (xb - xa) / length, (yb - ya) / length
        nx, ny = -dy, dx
        if nx * (xa + xb) + ny * (ya + yb) < 0:
            nx, ny = -nx, -ny
        cols = max(2, int(round(length / .85)))
        for c in range(cols):
            p0 = np.array([xa + (xb - xa) * c / cols, ya + (yb - ya) * c / cols])
            p1 = np.array([xa + (xb - xa) * (c + 1) / cols, ya + (yb - ya) * (c + 1) / cols])
            points.extend((p0 + (nx * .5, ny * .5), p1 + (nx * .5, ny * .5)))
    for x in (-HALF_W, HALF_W):
        points.append((x + (-.5 if x < 0 else .5), yf(x) + .5))
    return [tuple(map(float, to_world(lot, *p))) for p in points]


def cell(x, y, n, size):
    step = size / (n - 1)
    fx, fy = (x + size / 2) / step, (y + size / 2) / step
    return int(np.clip(math.floor(fx), 0, n - 2)), int(np.clip(math.floor(fy), 0, n - 2))


def project(world, heights, key):
    """Consume only this lot and its declared final-surface samples."""
    lots = [lot for lot in world['houses']['lots'] if lot['name'] == key]
    if len(lots) != 1:
        raise ValueError('House lot must have exactly one current logical placement')
    lot = {field: lots[0][field] for field in FIELDS}
    n, size = world['n'], world['size']
    if (type(n) is not int or n < 2 or not math.isfinite(size) or size <= 0
            or heights.shape != (n, n) or not np.isfinite(heights).all()):
        raise ValueError('House lot requires the complete finite final heightfield')
    cells = {}
    for x, y in queries(lot):
        i, j = cell(x, y, n, size)
        cells[f'{i},{j}'] = float(heights[j:j + 2, i:i + 2].min())
    return dict(schema=1, asset=key, n=n, size=size, lot=lot, cells=cells)


class Ground:
    """Read only declared final wall-foot cells; never fall back to another surface."""
    def __init__(self, value):
        if (value.get('schema') != 1 or value.get('asset') != value.get('lot', {}).get('name')
                or not value.get('cells')):
            raise ValueError('Missing complete house lot query product')
        self.value = value

    def low(self, x, y):
        i, j = cell(x, y, self.value['n'], self.value['size'])
        try:
            result = self.value['cells'][f'{i},{j}']
        except KeyError as error:
            raise ValueError('House geometry queried an undeclared final-terrain cell') from error
        if type(result) not in (int, float) or not math.isfinite(result):
            raise ValueError('House final-terrain query value is not finite')
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--heightmap', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    value = project(json.loads(args.world.read_text()), np.load(args.heightmap, allow_pickle=False), args.asset)
    atomic_json(args.output, value)


if __name__ == '__main__':
    main()
