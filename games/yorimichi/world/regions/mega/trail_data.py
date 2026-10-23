"""Project only the final terrain samples consumed by the mini-mega trail.

This product contains geometry data, not an exported mesh. Unrelated world
placements or terrain samples do not enter the downstream mesh constructor.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from village.layout import upper_surface  # noqa: E402


def project(world, heights):
    """Preserve the original trail's ordered final-surface polygons exactly."""
    path = np.asarray(world['mega']['trail'], dtype=float)
    heights = np.asarray(heights)
    if (path.ndim != 2 or path.shape[1] != 3 or len(path) < 2
            or not np.isfinite(path).all() or heights.ndim != 2
            or min(heights.shape) < 2 or heights.shape[0] != heights.shape[1]
            or not np.isfinite(heights).all()):
        raise ValueError('Mega trail requires a finite route and complete final heightfield')
    tangent = np.gradient(path[:, :2], axis=0)
    lengths = np.linalg.norm(tangent, axis=1)
    if np.any(lengths <= 0):
        raise ValueError('Mega trail has an undefined route tangent')
    tangent /= lengths[:, None]
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    polygons = []
    for i in range(len(path) - 1):
        for side in [-1, 1]:
            points = []
            for k, offset in [(i, 0), (i + 1, 0), (i + 1, side * 1.35), (i, side * 1.35)]:
                p = path[k, :2] + normal[k] * offset
                points.append([float(p[0]), float(p[1]), float(upper_surface(heights, *p)) + .045])
            if side < 0:
                points.reverse()
            polygons.append(points)
    return dict(schema=1, asset='Mega_Trail', polygons=polygons)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--world', type=Path, required=True)
    parser.add_argument('--heightmap', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    value = project(json.loads(args.world.read_text()), np.load(args.heightmap, allow_pickle=False))
    atomic_json(args.output, value)


if __name__ == '__main__':
    main()
