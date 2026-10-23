"""Canonical replacement lettering query/source arrays, before any mesh export."""
import argparse
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from megapark import build  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    real_directory(args.output.parent, create=True)
    if args.output.is_symlink():
        raise ValueError('Linked lettering output')
    vertices, faces, normals, uv = build.letters()
    np.savez(args.output, vertices=vertices, faces=faces, normals=normals, uv=uv, triangles=vertices[faces])
    print('MEGAPARK LETTER SOURCE COMPLETE', len(faces), flush=True)


if __name__ == '__main__':
    main()
