"""Carve only one declared valley source before query/render consumers."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from belmonte.model_sources import read  # noqa: E402
from belmonte.plan_model import regular  # noqa: E402
from belmonte.surface_data import write  # noqa: E402
from belmonte import terrain  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--definition',required=True,type=Path)
    parser.add_argument('--library',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args(argv)
    entry=read(args.definition,asset=args.asset)
    if entry['name'] not in terrain.VALLEY_CARVED_TILES or entry.get('collision'):raise ValueError('Unsupported carved ground owner')
    library=real_directory(args.library);real_directory(args.output.parent)
    if args.output.absolute().is_relative_to(library):raise ValueError('Carving may not overwrite committed sources')
    # Validate the selected input before the actual production carver opens it.
    regular(library,entry['path'],entry['sha256'])
    data,count,bounds,_=terrain.carved_valley_data(library/entry['path'])
    current=dict(entry,path='glb/'+entry['name']+'.glb',sha256=hashlib.sha256(data).hexdigest(),
                 triangles=count,bounds_m=bounds)
    write(args.output,current,data)
    print('BELMONTE CARVED QUERY SOURCE COMPLETE',entry['name'],count,flush=True)


if __name__=='__main__':main()
