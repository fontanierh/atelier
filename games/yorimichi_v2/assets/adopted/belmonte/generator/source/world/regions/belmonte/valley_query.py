"""Complete canonical valley query arrays from source data, never rendered exports."""
import argparse
import json
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from belmonte import query_arrays,source,surface_data  # noqa: E402
from belmonte.model_sources import read as definition  # noqa: E402
from belmonte.plan_model import regular  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('natural','final','colours'),required=True)
    parser.add_argument('--definition',type=Path,action='append',default=[])
    parser.add_argument('--surface',type=Path,action='append',default=[])
    parser.add_argument('--palette',type=Path)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);library=real_directory(args.library)
    faces=[];colours=[];seen=set()
    if args.mode=='colours':
        if args.palette is None or args.definition or args.surface:raise ValueError('Colour query requires only its palette projection')
        real_directory(args.palette.parent)
        if args.palette.is_symlink() or not args.palette.is_file():raise ValueError('Palette projection must be regular')
        value=json.loads(args.palette.read_text())
        if set(value)!={'schema','owner','sources'} or value['schema']!=1 or value['owner']!='BelmonteValleyColours':
            raise ValueError('Foreign terrain palette projection')
        for row in value['sources']:
            key=row['name']
            if key in seen or not key.startswith('SM_BM_BT_Terrain_') or row['path']!='meshes/'+key+'.glb':raise ValueError('Foreign terrain colour source')
            seen.add(key);data=regular(library,row['path'],row['sha256'])
            palette=[(np.asarray(p),np.asarray(t)) for p,t in row['palettes']]
            current,values=source.triangles_data(data,palette,label=key);faces.append(current);colours.append(values)
    elif args.mode=='natural':
        if args.palette or args.surface:raise ValueError('Natural query requires only its source definitions')
        for path in args.definition:
            key=path.stem;row=definition(path,asset=key)
            if key in seen or not key.startswith('SM_BM_BT_Terrain_'):raise ValueError('Foreign natural query owner')
            seen.add(key);data=regular(library,row['path'],row['sha256'])
            faces.append(source.triangles_data(data,label=key))
    else:
        if args.palette or args.definition:raise ValueError('Final query requires only final-source products')
        for path in args.surface:
            key=path.stem
            if key in seen or not key.startswith('SM_BM_BT_Terrain_'):raise ValueError('Foreign final query owner')
            seen.add(key);_,data=surface_data.read(path,owner=key)
            faces.append(source.triangles_data(data,label=key))
    if len(seen)!=56:raise ValueError('Incomplete canonical valley query roster')
    # Source order is the original terrain order and remains significant for
    # nearest-height tie behavior. Do not reorder by a new spatial partition.
    surface=source.Surface(np.concatenate(faces),np.concatenate(colours) if colours else None)
    stage='final' if args.mode=='final' else 'natural'
    owner='BelmonteValleyColours' if colours else 'BelmonteValley'
    query_arrays.write(args.output,surface.faces,surface.values,owner=owner,stage=stage)
    print('BELMONTE VALLEY QUERY COMPLETE',args.mode,len(surface.faces),flush=True)


if __name__=='__main__':main()
