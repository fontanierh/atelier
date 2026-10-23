"""Generate only the original Gondola procedural timber textures."""
import argparse
from pathlib import Path
import sys

KIT = Path(__file__).resolve().parents[3] / 'assets/vehicles/gondola'
sys.path.insert(0,str(KIT))
import textures  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    textures.generate(args.output)


if __name__ == '__main__': main()
