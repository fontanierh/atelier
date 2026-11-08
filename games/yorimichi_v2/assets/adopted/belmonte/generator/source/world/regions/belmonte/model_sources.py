"""Project only each committed model's consumed geometry definition."""
import argparse
import json
import math
from pathlib import Path
import re
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import name,real_directory,sha  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402

FIELDS=('name','path','sha256','triangles','bounds_m','slots','source_asset')
INDEX='inventory.json'


def entry(value):
    result={key:value[key] for key in FIELDS}
    key=name(result['name'])
    if (not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+',key) or result['path']!='meshes/'+key+'.glb'
            or not isinstance(result['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',result['sha256'])
            or type(result['triangles']) is not int or result['triangles']<1
            or not isinstance(result['source_asset'],str) or not result['source_asset']
            or not isinstance(result['slots'],list) or not result['slots']
            or any(not isinstance(slot,str) or not slot for slot in result['slots'])):
        raise ValueError('Invalid committed model source identity')
    bounds=result['bounds_m']
    if (not isinstance(bounds,list) or len(bounds)!=2 or any(not isinstance(row,list) or len(row)!=3 for row in bounds)
            or any(type(v) not in (int,float) or not math.isfinite(v) for row in bounds for v in row)
            or any(a>b for a,b in zip(*bounds))):raise ValueError('Invalid committed model bounds')
    if 'collision' in value:
        collision=value['collision']
        if (not isinstance(collision,dict) or set(collision)!={'path','sha256'}
                or collision['path']!='meshes/'+key+'_Collision.glb'
                or not isinstance(collision['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',collision['sha256'])):
            raise ValueError('Invalid committed whole collision identity')
        result['collision']=collision
    return result


def project(manifest):
    """@cc [owner:fontanierh,label:correctness;performance] independent-committed-model-definitions
    Geometry definitions MUST contain only the selected model's consumed source
    identity, slots, bounds and optional authored hull. Global placements, signs,
    material colours and sibling model identities MUST stop at unchanged per-model
    products. Validate the whole roster before any output mutation.
    """
    result={}
    rows=manifest['meshes']
    if not isinstance(rows,list) or not rows:raise ValueError('Missing committed model roster')
    for value in rows:
        selected=entry(value);key=selected['name']
        if key.casefold() in {name.casefold() for name in result}:raise ValueError('Aliased committed model owner')
        result[key]=dict(schema=1,asset=key,source=selected)
    return result


def read(path,*,asset):
    path=Path(path);real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Model definition must be regular')
    value=json.loads(path.read_text())
    if (set(value)!={'schema','asset','source'} or type(value['schema']) is not int or value['schema']!=1 or value['asset']!=name(asset)
            or entry(value['source'])!=value['source'] or value['source']['name']!=asset):
        raise ValueError('Model definition belongs to another source')
    return value['source']


def publish(source,root):
    source=Path(source).absolute();real_directory(source.parent);root=real_directory(root)
    if source.is_symlink() or not source.is_file() or source.is_relative_to(root):raise ValueError('Invalid model catalogue input')
    selected=project(json.loads(source.read_text()))
    expected={key+'.json' for key in selected}
    actual=regular_files(root) if root.exists() else set()
    previous={}
    if INDEX in actual:
        prior=json.loads((root/INDEX).read_text())
        if set(prior)!={'schema','complete','files'} or type(prior['schema']) is not int or prior['schema']!=1 or prior['complete'] is not True:
            raise ValueError('Invalid prior model definition ownership')
        previous=prior['files']
        if (not isinstance(previous,dict) or any(Path(k).name!=k or k!=name(Path(k).stem)+'.json'
                or not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for k,v in previous.items())):
            raise ValueError('Foreign prior definition membership')
    if actual-expected-set(previous)-{INDEX} or (root.exists() and any(p.is_dir() for p in root.iterdir())):
        raise ValueError('Foreign model definition files')
    for relative in (set(previous)-expected)&actual:
        if sha(root/relative)!=previous[relative]:raise ValueError('Retiring model definition changed outside its owner')
    root.mkdir(parents=True,exist_ok=True)
    for key,value in selected.items():
        path=root/(key+'.json')
        if not path.exists() or json.loads(path.read_text())!=value:atomic_json(path,value)
    inventory={key+'.json':sha(root/(key+'.json')) for key in selected}
    atomic_json(root/INDEX,dict(schema=1,complete=True,files=inventory))
    for relative in (set(previous)-expected)&actual:(root/relative).unlink()
    return selected


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=publish(args.source,args.output)
    print('BELMONTE MODEL DEFINITIONS COMPLETE',len(result),flush=True)
