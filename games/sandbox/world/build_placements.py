"""Placement references a stable asset ID; it never reads the asset's shape or bounds."""
import json
import math
from pathlib import Path
import sys


def main(source, output):
    records = json.loads(Path(source).read_text())
    for record in records:
        point = record['position_cm']
        if record['asset'] != 'block' or len(point) != 3 or not all(
                type(n) in (int, float) and math.isfinite(n) for n in point):
            raise ValueError('Placement needs the block asset and three finite centimetre coordinates')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, sort_keys=True) + '\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
