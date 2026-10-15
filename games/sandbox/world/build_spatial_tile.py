"""Consume just the frozen spatial matches and their certified geometry products."""
import json
from pathlib import Path
import sys

from atelier.build_context import query


def main(destination):
    neighbours = [{'name': p.name, 'bounds_cm': p.bounds, 'geometry': json.loads(p.paths[0].read_text())}
                  for p in query('neighbours')]
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(neighbours, sort_keys=True) + '\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
