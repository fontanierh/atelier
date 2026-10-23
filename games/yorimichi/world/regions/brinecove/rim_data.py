"""Publish only the final FarHills hole boundary consumed by coastal geometry."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from brinecove import region  # noqa: E402
from brinecove.geometry_finish import rim  # noqa: E402

SIDES = {'south', 'north', 'west', 'east'}


def project(path):
    path = Path(path)
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Final coast boundary requires a regular terrain product')
    current, world = rim(path)
    return dict(schema=1, owner='FarHills', stage='final', city=True,
                sides=current.sides, world=world)


def read(value):
    if (set(value) != {'schema', 'owner', 'stage', 'city', 'sides', 'world'}
            or value['schema'] != 1 or value['owner'] != 'FarHills'
            or value['stage'] != 'final' or value['city'] is not True
            or set(value['sides']) != SIDES or set(value['world']) != SIDES):
        raise ValueError('Invalid final coast boundary identity')
    for table, size in ((value['sides'], 2), (value['world'], 3)):
        for rows in table.values():
            if (not isinstance(rows, list) or len(rows) < 2
                    or any(len(row) != size or not all(math.isfinite(v) for v in row) for row in rows)):
                raise ValueError('Incomplete or nonfinite final coast boundary')
    sides = {name: [tuple(row) for row in rows] for name, rows in value['sides'].items()}
    if any(rows != sorted(rows) for rows in sides.values()):
        raise ValueError('Unordered final coast boundary')
    return region.Rim(sides), {name: [tuple(row) for row in rows] for name, rows in value['world'].items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    # Do not include unconsumed interior geometry or the whole source digest in
    # this projection. Normal task identity still verifies the complete input.
    value = project(args.source)
    # JSON is the published representation and must pass its strict receiver.
    read(json.loads(json.dumps(value, allow_nan=False)))
    real_directory(args.output.parent)
    atomic_json(args.output, value)


if __name__ == '__main__':
    main()
