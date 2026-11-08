"""Explicit consumed seam knots stop interior edits before a sibling constructor."""
from copy import deepcopy
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from atelier.atomic_files import atomic_json
from atelier.export_manifest import name,real_directory

TOLERANCE=1e-4


def capture(meshes,origin,lines):
    """Project the exact existing stitch sequence into per-owner boundary data."""
    from train import earthworks
    working={name(owner):deepcopy(mesh) for owner,mesh in meshes.items()}
    result={owner:dict(schema=1,owner=owner,origin=[float(v) for v in origin],seams=[]) for owner in working}
    for axis,value in lines:
        snapshots={}
        for owner,mesh in working.items():
            points=np.asarray(mesh.p,float)+origin
            on=abs(points[:,axis]-value)<TOLERANCE
            snapshots[owner]={round(float(p[1-axis]),4):float(p[2]) for p in points[on]}
        for owner in working:
            others={}
            for other,knots in snapshots.items():
                if other!=owner:others.update(knots)
            points=np.asarray(working[owner].p,float)+origin
            on=abs(points[:,axis]-value)<TOLERANCE
            consumed=set()
            for a,b,c in np.asarray(working[owner].i).reshape(-1,3):
                for first,last,_ in ((a,b,c),(b,c,a),(c,a,b)):
                    if not (on[first] and on[last]):continue
                    lo,hi=sorted((points[first,1-axis],points[last,1-axis]))
                    consumed.update(key for key in others if lo+TOLERANCE<key<hi-TOLERANCE)
                    # Preserve the original stitch's first on-seam edge rule,
                    # including its break when that edge needs no new knot.
                    break
            result[owner]['seams'].append(dict(axis=axis,value=float(value),
                knots=[[key,others[key]] for key in sorted(consumed)]))
        earthworks.stitch(list(working.values()),origin,[(axis,value)],tol=TOLERANCE,whole_seam=True)
    for owner,value in result.items():validate(value,owner=owner)
    return result


def validate(value,*,owner):
    if (not isinstance(value,dict) or set(value)!={'schema','owner','origin','seams'}
            or type(value['schema']) is not int or value['schema']!=1 or value['owner']!=name(owner)
            or not isinstance(value['origin'],list) or len(value['origin'])!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in value['origin'])
            or not isinstance(value['seams'],list) or not value['seams']):raise ValueError('Invalid terrain seam owner')
    for row in value['seams']:
        if (set(row)!={'axis','value','knots'} or type(row['axis']) is not int or row['axis'] not in (0,1)
                or type(row['value']) not in (int,float) or not math.isfinite(row['value'])
                or not isinstance(row['knots'],list) or any(not isinstance(p,list) or len(p)!=2
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) for p in row['knots'])
                or any(a[0]>=b[0] for a,b in zip(row['knots'],row['knots'][1:]))):raise ValueError('Invalid terrain seam knots')
    return value


def apply(mesh,value,*,owner):
    """@cc [owner:fontanierh,label:correctness;performance] independent-terrain-seam-input
    Each terrain constructor MUST consume only its own construction data and the
    exact ordered seam projection from its neighbours. Apply the original stitch
    policy without changing height, normal, UV or triangle semantics. Unconsumed
    neighbour interiors MUST stop at unchanged boundary data; render exports
    MUST NOT be used as seam inputs.
    """
    validate(value,owner=owner)
    from train import earthworks
    result=deepcopy(mesh);origin=np.asarray(value['origin'],float)
    for row in value['seams']:
        points=[]
        for knot,height in row['knots']:
            point=np.zeros(3);point[row['axis']]=row['value'];point[1-row['axis']]=knot;point[2]=height
            points.append(point-origin)
        if not points:continue
        neighbour=SimpleNamespace(p=points,n=np.zeros((len(points),3)),t=np.zeros((len(points),2)),i=[])
        earthworks.stitch([result,neighbour],origin,[(row['axis'],row['value'])],tol=TOLERANCE,whole_seam=True)
    return result


def write(path,value,*,owner):
    path=Path(path);real_directory(path.parent);validate(value,owner=owner)
    if path.name!=name(owner)+'.json' or path.is_symlink() or path.exists() and not path.is_file():
        raise ValueError('Foreign terrain seam destination')
    if not path.exists() or json.loads(path.read_text())!=value:atomic_json(path,value)


def read(path,*,owner):
    path=Path(path);real_directory(path.parent)
    if path.name!=name(owner)+'.json' or path.is_symlink() or not path.is_file():raise ValueError('Invalid terrain seam input')
    return validate(json.loads(path.read_text()),owner=owner)
