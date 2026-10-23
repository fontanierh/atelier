"""Read final source-query North Trail and narrowly selected Belmonte ground.

This generates ropeway query products only; it never changes either region.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib
import json

import numpy as np
import yori  # Bootstrap shared studio and region imports inside Blender.
import region_query
from gondola.inputs import GROUND_BOUNDS, snapshot
from gondola.query_frames import imported_identity_triangles
from regions.belmonte import source


def clipped(triangles,bounds):
    triangles=np.asarray(triangles,float).reshape(-1,3,3)
    lo,hi=triangles[:,:,:2].min(1),triangles[:,:,:2].max(1)
    x0,y0,x1,y1=bounds
    return triangles[(hi[:,0]>=x0)&(lo[:,0]<=x1)&(hi[:,1]>=y0)&(lo[:,1]<=y1)]


def main():
    build=yori.OUT; before=snapshot(build)
    print('GONDOLA GROUND: final North Trail source query',flush=True)
    trail=imported_identity_triangles(region_query.load(build/'hidamari/query-data/HD_NorthTrail.npz',
        owner='HD_NorthTrail',stage='final'))
    if not len(trail):
        raise ValueError('Final North Trail does not cover the valley station')
    surfaces={'trail':trail}
    origin=np.asarray(before['belmonte_ground']['origin_cm'])/np.array([100.,-100.,100.])
    valley=[]
    for group in before['belmonte_ground']['groups']:
        name=group['name']
        print('GONDOLA GROUND:',name,flush=True)
        triangles=clipped(source.triangles(build/'belmonte'/group['path'])+origin,GROUND_BOUNDS)
        if name=='SM_BM_NorthApron':
            surfaces['apron']=triangles
        else:
            valley.append(triangles)
    surfaces['valley']=np.concatenate(valley)
    if snapshot(build)!=before:
        raise ValueError('Gondola ground inputs changed during extraction')
    folder=build/'gondola/world';folder.mkdir(parents=True,exist_ok=True)
    np.savez(folder/'ground.npz',**surfaces)
    (folder/'ground.json').write_text(json.dumps({'inputs':before,'output_sha256':hashlib.sha256((folder/'ground.npz').read_bytes()).hexdigest()},indent=2)+'\n')
    print('GONDOLA GROUND COMPLETE', {key:len(value) for key,value in surfaces.items()},flush=True)


if __name__=='__main__':
    main()
