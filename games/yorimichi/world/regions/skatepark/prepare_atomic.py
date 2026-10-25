"""Publish original skate AO, validated riding/terrain data or consumed UV material scales."""
import argparse
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from skatepark import atomic_source as source  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=('ao','queries','materials'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--textures',type=Path)
    args=parser.parse_args(argv if argv is not None else (sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None))
    if args.kind=='materials':
        real_directory(args.output.parent,create=True)
        if args.output.is_symlink() or (args.output.exists() and not args.output.is_file()):raise ValueError('Invalid skate UV data destination')
        atomic_json(args.output,source.material_projection(args.textures))
    elif args.kind=='ao':source.publish_ao(args.output)
    else:source.publish_queries(args.output)


if __name__=='__main__':main()
