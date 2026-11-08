"""Prepare one committed logical model as independently exported lossless data."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.export_manifest import real_directory  # noqa: E402
from belmonte.model_sources import read  # noqa: E402
from belmonte.model_pieces import planned  # noqa: E402
from belmonte.atomic_metadata import metadata  # noqa: E402
from encoded_region_plan import publish  # noqa: E402


def regular(library,relative,wanted):
    path=library/relative;real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Committed model must be regular')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=wanted:raise ValueError('Committed model differs from its own definition')
    return data


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--definition',type=Path,required=True)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    value=read(args.definition,asset=args.asset)
    if value['name'].startswith(('SM_BM_BT_Terrain_','SM_BM_North')):
        raise ValueError('Query terrain requires its own final-source constructor')
    library=real_directory(args.library);output=real_directory(args.output)
    if output.is_relative_to(library) or library.is_relative_to(output):raise ValueError('Model inputs/outputs overlap')
    data=regular(library,value['path'],value['sha256'])
    value=dict(value,path='glb/'+value['name']+'.glb')
    rows=planned(value,data)
    parts=[dict(name=row['name'],data=payload,**metadata(row,slots,collides))
           for row,slots,collides,payload in rows]
    if 'collision' in value:
        hull=value['collision'];payload=regular(library,hull['path'],hull['sha256'])
        parts.append(dict(name=value['name']+'_Collision',data=payload,role='collision',metadata=dict(parent=value['name'])))
    result=publish(output,parent=value['name'],parts=parts)
    print('BELMONTE MODEL DATA COMPLETE',value['name'],len(rows),result['source_render_triangles'],flush=True)
    return result


if __name__=='__main__':main()
