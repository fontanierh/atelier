"""Evaluate only original Bike pivot/contact data in its explicit factory environment."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file():raise ValueError('Regular Bike layout source required')
    value=json.loads(args.source.read_text())
    if set(value)!={'schema','program'} or value['schema']!=1:raise ValueError('Incomplete Bike layout source')
    scope={};exec(compile(value['program'],str(args.source),'exec'),scope)
    atomic_json(args.output,scope['layout']());print('BIKE LAYOUT DATA COMPLETE',flush=True)


if __name__=='__main__':main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
