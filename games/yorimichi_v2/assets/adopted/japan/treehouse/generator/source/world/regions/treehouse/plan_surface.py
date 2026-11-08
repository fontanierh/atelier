"""Select only one canonical finished Treehouse owner; no sibling geometry/export is loaded."""
import argparse
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier import mesh_ir  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
import region_plan_files  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    value=validate(args.source)
    region_plan_files.begin(args.output,value['parent'],[row['payload'] for row in value['pieces']])
    for row in value['pieces']:
        mesh_ir.write(args.output/row['payload'],(args.source/row['payload']).read_bytes())
    validate(args.output,value)
    region_plan_files.finish(args.output,value)
    print('TREEHOUSE SELECTED SOURCE COMPLETE',value['parent'],len(value['pieces']),flush=True)


if __name__=='__main__':main()
