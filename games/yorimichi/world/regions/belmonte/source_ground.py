"""Publish one committed final terrain source without exporting a rendered mesh."""
import argparse
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from belmonte.model_sources import read  # noqa: E402
from belmonte.plan_model import regular  # noqa: E402
from belmonte.ground_pieces import is_ground  # noqa: E402
from belmonte.ground_names import VALLEY_CARVED_TILES  # noqa: E402
from belmonte.surface_data import write  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--definition',required=True,type=Path)
    parser.add_argument('--library',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    entry=read(args.definition,asset=args.asset)
    if (not is_ground(entry['name']) or entry.get('collision') or entry['name'] in VALLEY_CARVED_TILES):
        raise ValueError('Unsupported committed final ground: carved terrain requires its final constructor')
    library=real_directory(args.library);real_directory(args.output.parent)
    if args.output.absolute().is_relative_to(library):raise ValueError('Final query may not overwrite committed sources')
    data=regular(library,entry['path'],entry['sha256'])
    write(args.output,dict(entry,path='glb/'+entry['name']+'.glb'),data)
    print('BELMONTE FINAL QUERY SOURCE COMPLETE',entry['name'],entry['triangles'],flush=True)


if __name__=='__main__':main()
