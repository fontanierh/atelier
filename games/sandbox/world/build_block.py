"""A small portable asset description, independently consumed from its placement."""
import json
import math
from pathlib import Path
import sys
import time


def main(source, output):
    print('ATELIER_PHASE ' + json.dumps({'event': 'begin', 'id': 'read', 'name': 'read and validate',
                                       'at': time.monotonic()}), flush=True)
    size = json.loads(Path(source).read_text())['size_cm']
    if len(size) != 3 or not all(type(n) in (int, float) and math.isfinite(n) and n > 0 for n in size):
        raise ValueError('Block dimensions must be three finite positive centimetre values')
    print('ATELIER_PHASE ' + json.dumps({'event': 'end', 'id': 'read', 'at': time.monotonic(), 'ok': True}), flush=True)
    print('ATELIER_PHASE ' + json.dumps({'event': 'begin', 'id': 'write', 'name': 'write products',
                                       'at': time.monotonic()}), flush=True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'shape.json').write_text(json.dumps({'asset': 'block', 'size_cm': size}) + '\n')
    (output / 'bounds.json').write_text(json.dumps({'half_extent_cm': [n / 2 for n in size]}) + '\n')
    print('ATELIER_PHASE ' + json.dumps({'event': 'end', 'id': 'write', 'at': time.monotonic(), 'ok': True}), flush=True)


if __name__ == '__main__':
    main(*sys.argv[1:])
