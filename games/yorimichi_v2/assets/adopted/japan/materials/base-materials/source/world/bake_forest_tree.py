"""Canonical per-species impostor image/view data before its independent mesh export."""
import argparse
from pathlib import Path
import json
import sys
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parent/'regions')]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from forest_parameters import load  # noqa: E402
import forest_source as source  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parameters',type=Path,required=True)
    parser.add_argument('--frame',type=Path,required=True)
    parser.add_argument('--views',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    name,parameters=load(args.parameters)
    root=real_directory(args.output)
    expected={name+'_'+mode+'.png' for mode in ('colour','normal')}|{'record.json'}
    expected.update(name+'-'+mode+f'-{view}.png' for mode in ('colour','normal') for view in range(4))
    if root.exists() and regular_files(root)-expected:
        raise ValueError('Foreign or incomplete per-species impostor output membership')
    root.mkdir(parents=True,exist_ok=True)
    source.initialize(name,parameters);obj=source.base(name,parameters)
    frame=json.loads(args.frame.read_text())
    if any(frame.get(key)!=value for key,value in source.bounds(obj).items()):
        raise ValueError('Impostor source differs from canonical base bounds')
    record=source.forest_impostors.bake(obj,root)
    if regular_files(root) != expected-{'record.json'} and regular_files(root) != expected:
        raise ValueError('Incomplete per-species impostor image inventory')
    atomic_json(root/'record.json',dict(name=name,record=record))
    # Geometry consumes only measured views, independently of image encoding and report-only coverage.
    atomic_json(args.views,dict(name=name,record=dict(views=record['views'])))
    print('FOREST IMPOSTOR DATA COMPLETE',name,flush=True)


if __name__=='__main__':main()
