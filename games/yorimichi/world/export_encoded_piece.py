"""Export one bounded encoded GLB without a Blender attribute round trip."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
from atelier.encoded_glb import export  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--format',choices=['.glb'],required=True)
    args=parser.parse_args(argv)
    value=export(args.input,args.output)
    print('ENCODED ATOMIC GLB COMPLETE',value['asset'],value['triangles'],flush=True)


if __name__=='__main__':main()
