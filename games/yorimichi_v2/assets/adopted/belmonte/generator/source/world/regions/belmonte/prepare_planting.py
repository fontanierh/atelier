"""Authored and connecting woodland placements from explicit final query data."""
import argparse
import json
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from belmonte import planting,query_arrays,runtime_layout  # noqa: E402
from belmonte.query_surface import Surface  # noqa: E402
from belmonte.scene_inputs import read  # noqa: E402


def prepare(inputs,valley,apron,output):
    """@cc [owner:fontanierh,label:correctness;performance] planting-consumes-final-query-data
    Planting MUST consume the complete current final valley and apron query
    products and its authored scene view, never rendered mesh exports or an
    inline terrain reconstruction. Preserve seeds, thinning, species, source
    transform frames and railway settlement from the existing owner.
    """
    output=Path(output);real_directory(output.parent)
    if output.name!='planting.json' or output.is_symlink() or output.exists() and not output.is_file():
        raise ValueError('Invalid generated planting output')
    data=read(inputs,view='planting')
    value=query_arrays.read(valley,owner='BelmonteValley',stage='final')
    ground=Surface(value['faces'])
    value=query_arrays.read(apron,owner='SM_BM_NorthApron',stage='final')
    collar=Surface(value['faces'])
    print('BELMONTE PLANTING authored source selection starting',flush=True)
    plants,report=planting.replacements(data,ground.height)
    print('BELMONTE PLANTING authored selection complete',sum(len(v) for v in plants.values()),flush=True)
    woods=planting.woodland(collar)
    for name,transforms in woods.items():plants.setdefault(name,[]).extend(transforms)
    report['connecting_woodland']=sum(len(v) for v in woods.values())
    report['tree_detail']='Original detailed leaf geometry; no backdrop or _lo assets'
    print('BELMONTE PLANTING woodland complete',report['connecting_woodland'],flush=True)
    report['railway_corridor_removed']=runtime_layout.clear_railway(plants)
    value=dict(schema=1,owner='BelmontePlants',plants=plants,report=report)
    json.dumps(value,allow_nan=False)
    if not output.exists() or json.loads(output.read_text())!=value:atomic_json(output,value)
    print('BELMONTE PLANTING COMPLETE',sum(len(v) for v in plants.values()),flush=True)
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('input','valley','apron','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();prepare(args.input,args.valley,args.apron,args.output)
