"""Publish only the final FarHills hole boundary consumed by coastal geometry."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from brinecove.boundary import rim  # noqa: E402

from brinecove.rim_schema import read  # noqa: E402


def project(path):
    path = Path(path)
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Final coast boundary requires a regular terrain product')
    current, world = rim(path)
    return dict(schema=1, owner='FarHills', stage='final', city=True,
                sides=current.sides, world=world)


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
