"""Only effective terrain palettes consumed by the original northern join painter."""
import argparse
import json
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from belmonte.terrain_palette import TERRAIN_LAYERS  # noqa: E402
from belmonte.model_sources import entry  # noqa: E402
from belmonte.ground_pieces import placements  # noqa: E402


def project(value):
    placements(value)
    placed={row['asset']:row['materials'] for row in value['placements']}
    result=[];seen=set()
    for row in value['meshes']:
        if not row['name'].startswith('SM_BM_BT_Terrain_'):continue
        current=entry(row)
        if current['name'] in seen:raise ValueError('Duplicate terrain palette owner')
        seen.add(current['name']);palettes=[]
        for key in placed[current['source_asset']]:
            material=value['materials'][key];vectors=material['vectors']
            tint=np.asarray(vectors.get('Tint',[1.,1.,1.])[:3])*vectors.get('StableColor',[1.,1.,1.])[:3]
            if tint.shape!=(3,) or not np.isfinite(tint).all():raise ValueError('Invalid effective terrain tint')
            palettes.append([list(map(list,TERRAIN_LAYERS.values())),
                             (tint*material['scalars'].get('Brightness',1.)).tolist()])
        result.append(dict(name=current['name'],path=current['path'],sha256=current['sha256'],palettes=palettes))
    if len(result)!=56:raise ValueError('Incomplete terrain palette source roster')
    return dict(schema=1,owner='BelmonteValleyColours',sources=result)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);real_directory(args.source.parent);real_directory(args.output.parent)
    if args.source.is_symlink() or not args.source.is_file():raise ValueError('Palette catalogue must be regular')
    value=project(json.loads(args.source.read_text()))
    if args.output.is_symlink() or args.output.exists() and not args.output.is_file():raise ValueError('Palette output must be regular')
    if not args.output.exists() or json.loads(args.output.read_text())!=value:atomic_json(args.output,value)
    print('BELMONTE VALLEY PALETTES COMPLETE',len(value['sources']),flush=True)


if __name__=='__main__':main()
