"""Narrow final world reads needed by the ropeway's owned ground queries."""
import hashlib
import json
import math
import re
import sys
from pathlib import Path


sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import export_digest

GROUND_BOUNDS = (340., 3550., 535., 4670.)
REPO = Path(__file__).resolve().parents[4]
CODE = {name: REPO / name for name in (
    'games/yorimichi/world/gondola/inputs.py',
    'games/yorimichi/world/gondola/probe.py',
    'games/yorimichi/world/regions/belmonte/source.py',
    'games/yorimichi/export_digest.py',
    'platform/studio/atelier/gltf.py',
)}


def selected_ground(build):
    """@cc [owner:fontanierh,label:correctness] logical-final-ground-selection
    Ground selection MUST read the complete published final-query inventory and select
    actual canonical surface files, independently of native render piece names. The
    logical owner is not a loadable parent UObject. Unselected metadata MUST NOT enter
    the downstream query digest, but the collector MUST declare its selector file.
    """
    product=json.loads((build/'products/belmonte/ground.json').read_text())
    if type(product) is not dict or type(product.get('schema')) is not int or product['schema']!=1:
        raise ValueError('Missing complete Belmonte final-ground product')
    origin_cm=product.get('origin_cm')
    if (not isinstance(origin_cm,list) or len(origin_cm)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in origin_cm)):
        raise ValueError('Invalid final-ground origin')
    surfaces=product.get('surfaces')
    if not isinstance(surfaces,list) or any(not isinstance(row,dict) for row in surfaces):
        raise ValueError('Invalid final-ground surface inventory')
    entries={row['name']:row for row in surfaces}
    if len(entries)!=len(surfaces) or not {'SM_BM_NorthApron','SM_BM_NorthCountry'}<=entries.keys():
        raise ValueError('Belmonte final terrain or apron is missing')
    origin=[v/f for v,f in zip(origin_cm,(100.,-100.,100.))]
    groups=[]
    for name,row in entries.items():
        if (not isinstance(name,str) or not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+',name)
                or row.get('path')!='ground/glb/'+name+'.glb'):
            raise ValueError('Invalid final-ground member path')
        if name.startswith('SM_BM_BT_Terrain_') or name=='SM_BM_NorthApron':
            if 'transforms' in row or 'transform' in row:
                raise ValueError('Gondola terrain read requires the declared identity Belmonte placement')
            bounds=row['bounds_m']
            if (len(bounds)!=2 or any(len(p)!=3 for p in bounds)
                    or any(type(v) not in (int,float) or not math.isfinite(v) for p in bounds for v in p)
                    or any(a>b for a,b in zip(*bounds))):
                raise ValueError('Invalid final-ground bounds')
            if name!='SM_BM_NorthApron':
                low=[bounds[0][i]+origin[i] for i in (0,1)]
                high=[bounds[1][i]+origin[i] for i in (0,1)]
                x0,y0,x1,y1=GROUND_BOUNDS
                if high[0]<x0 or low[0]>x1 or high[1]<y0 or low[1]>y1:
                    continue
            groups.append(dict(name=name,path=row['path']))
    return {'origin_cm':origin_cm,'groups':groups}


def geometry_paths(build, ground):
    return [build/'terrain/HD_Terrain/final.npz',build/'terrain/HD_NorthMountains/final.npz',
            build/'hidamari/assets/HD_NorthTrail.fbx',
            *(build/'belmonte'/g['path'] for g in ground['groups'])]


def paths(build):
    build=Path(build)
    return [build/'products/belmonte/ground.json',*geometry_paths(build,selected_ground(build))]


def snapshot(build):
    build=Path(build)
    ground=selected_ground(build)
    return {'code':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in CODE.items()},
            'belmonte_ground':ground,
            'files':{str(path.relative_to(build)):(export_digest.fbx(path.read_bytes()) if path.suffix=='.fbx' else hashlib.sha256(path.read_bytes()).hexdigest())
                     for path in geometry_paths(build,ground)}}
