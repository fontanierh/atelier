"""Pure dimension assembly and original two recoloured source textures before Treehouse exports."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402


def dimensions(inputs,output):
    result={}
    for path in inputs:
        value=json.loads(path.read_text());name=value['name']
        if name in result or path.stem!=name or not name.startswith('Tree_Canopy_'):
            raise ValueError('Foreign/duplicate current canopy dimensions')
        result[name]=value['dimensions']
    if len(result)!=4:raise ValueError('Incomplete canopy dimension owner')
    atomic_json(output,result)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recolour',type=Path)
    parser.add_argument('--record',action='append',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    if args.recolour:
        root=real_directory(args.recolour)
        if root.exists() and regular_files(root)-{'T_leaf_crimson.png','T_leaf_amber.png'}:
            raise ValueError('Foreign canopy recolour destination')
        root.mkdir(parents=True,exist_ok=True)
        import bpy
        from treehouse import trees
        bpy.ops.wm.read_factory_settings(use_empty=True);trees.OUT=root;trees.recolour()
    else:dimensions(args.record,args.output)
    print('TREEHOUSE CANOPY DATA COMPLETE',flush=True)


if __name__=='__main__':main()
