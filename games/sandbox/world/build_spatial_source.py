"""Two independent products: tile consumers read geometry, never the preview settings."""
import json
from pathlib import Path
import sys


def main(source, destination):
    data = json.loads(Path(source).read_text())
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'geometry.json').write_text(json.dumps({'shape': data['shape']}, sort_keys=True) + '\n')
    (output / 'preview.json').write_text(json.dumps({'colour': data['preview_colour']}) + '\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
