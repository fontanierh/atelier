"""Publish one coach's complete layout and capsule/adjacent-door query data before geometry."""
import argparse
from dataclasses import fields, is_dataclass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json
from train import access as A, layout as L

BUILDERS = dict(locomotive=L.locomotive, tender=L.tender, **{'baggage-van': L.baggage_van,
    'restaurant': L.restaurant, 'first-class': L.first_class, 'second-class': L.second_class, 'brake-van': L.brake_van})


def encode(value):
    if is_dataclass(value):
        return dict(kind='record', type=type(value).__name__, fields={field.name: encode(getattr(value, field.name)) for field in fields(value)})
    if isinstance(value, (tuple, list)):
        return dict(kind='tuple' if isinstance(value, tuple) else 'list', items=[encode(item) for item in value])
    if isinstance(value, dict): return dict(kind='map', items={key: encode(item) for key, item in value.items()})
    if value is None or type(value) in (str, bool, int, float): return value
    raise ValueError('Unsupported coach constructor field: ' + type(value).__name__)


def request(coach):
    if coach not in BUILDERS: raise ValueError('Unknown selected coach')
    selected = BUILDERS[coach]()
    return dict(schema=1, coach=coach, layout=encode(selected), access=dict(players=encode(A.players()),
        locked_gangways=encode([pair for pair in A.locked_gangways() if pair[0] == coach]), locked_doors=A.LOCKED_DOORS))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coach', choices=tuple(BUILDERS), required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    value = request(args.coach); json.dumps(value, allow_nan=False)
    atomic_json(args.output, value)
    print('CARRIAGE LAYOUT AND SOURCE QUERIES COMPLETE', args.coach, flush=True)


if __name__ == '__main__': main()
