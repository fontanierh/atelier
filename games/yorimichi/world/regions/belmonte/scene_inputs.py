"""Separate scene metadata products, with no model construction or export reads."""
import argparse
import json
from pathlib import Path
import sys

sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory,sha  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402

FIELDS={'materials':{'materials','textures'},'planting':{'planting','meshes','placements'},
        'runtime':{'meshes','placements','signs'}}
INDEX='inventory.json'
JOURNAL='.scene-transaction.json'


def project(data):
    """@cc [owner:fontanierh,label:correctness;performance] separate-belmonte-scene-views
    Material preparation, planting and runtime assembly MUST consume separate
    explicit scene views. A sign or material colour edit MUST NOT enter model
    export identities. Planting MUST retain authored and embedded plant hints,
    placements and their transforms, without unrelated mesh hashes or colours.
    """
    selected={
        'materials':{key:data[key] for key in ('materials','textures')},
        'planting':dict(planting=data['planting'],
            meshes=[{key:row[key] for key in ('source_asset','embedded_plants')} for row in data['meshes']],
            placements=[{key:row[key] for key in ('asset','transform')} for row in data['placements']]),
        'runtime':{key:data[key] for key in ('meshes','placements','signs')}}
    return {key:dict(schema=1,view=key,data=value) for key,value in selected.items()}


def read(path,*,view):
    path=Path(path);real_directory(path.parent)
    if view not in FIELDS or path.name!=view+'.json' or path.is_symlink() or not path.is_file():raise ValueError('Invalid scene view input')
    value=json.loads(path.read_text())
    if (set(value)!={'schema','view','data'} or type(value['schema']) is not int or value['schema']!=1
            or value['view']!=view or not isinstance(value['data'],dict) or set(value['data'])!=FIELDS[view]):
        raise ValueError('Foreign or incomplete scene metadata view')
    return value['data']


def publish(source,root):
    source=Path(source);real_directory(source.parent);root=real_directory(root)
    if source.is_symlink() or not source.is_file() or source.absolute().is_relative_to(root):raise ValueError('Invalid scene metadata source')
    values=project(json.loads(source.read_text()));expected={key+'.json' for key in values}
    json.dumps(values,allow_nan=False)
    current=regular_files(root) if root.exists() else set()
    if root.exists() and any(path.is_dir() for path in root.iterdir()):raise ValueError('Scene views must be flat')
    if current-expected-{INDEX,JOURNAL}:raise ValueError('Foreign scene metadata outputs')
    if current:
        if INDEX in current:
            prior=json.loads((root/INDEX).read_text())
            if set(prior)!={'schema','owner','files'} or prior['schema']!=1 or prior['owner']!='BelmonteScene' or set(prior['files'])!=expected:
                raise ValueError('Foreign previous scene metadata ownership')
        elif JOURNAL not in current:raise ValueError('Unrecorded scene metadata outputs')
        if JOURNAL in current:
            prior=json.loads((root/JOURNAL).read_text())
            if prior!=dict(schema=1,owner='BelmonteScene',files=sorted(expected)):raise ValueError('Foreign scene transaction')
    root.mkdir(parents=True,exist_ok=True)
    atomic_json(root/JOURNAL,dict(schema=1,owner='BelmonteScene',files=sorted(expected)))
    for key,value in values.items():
        path=root/(key+'.json')
        if not path.exists() or json.loads(path.read_text())!=value:atomic_json(path,value)
    atomic_json(root/INDEX,dict(schema=1,owner='BelmonteScene',files={key:sha(root/key) for key in sorted(expected)}))
    (root/JOURNAL).unlink()
    return values


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();publish(args.source,args.output)
    print('BELMONTE SCENE VIEWS COMPLETE',flush=True)
