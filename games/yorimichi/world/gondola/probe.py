"""Read final exported North Trail and narrowly selected Belmonte ground.

This generates ropeway query products only; it never changes either region.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hashlib
import json

import bpy
import numpy as np
from gondola.inputs import GROUND_BOUNDS, snapshot
from regions.belmonte import source
import yori


def clipped(triangles,bounds):
    triangles=np.asarray(triangles,float).reshape(-1,3,3)
    lo,hi=triangles[:,:,:2].min(1),triangles[:,:,:2].max(1)
    x0,y0,x1,y1=bounds
    return triangles[(hi[:,0]>=x0)&(lo[:,0]<=x1)&(hi[:,1]>=y0)&(lo[:,1]<=y1)]


def main():
    build=yori.OUT; before=snapshot(build)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    print('GONDOLA GROUND: final exported North Trail',flush=True)
    bpy.ops.import_scene.fbx(filepath=str(build/'hidamari/assets/HD_NorthTrail.fbx'))
    trail=[]
    for obj in list(bpy.data.objects):
        if obj.type!='MESH':
            continue
        mesh=obj.data;mesh.calc_loop_triangles()
        matrix=np.asarray(obj.matrix_world,float)
        vertices=np.asarray([tuple(v.co) for v in mesh.vertices],float).reshape(-1,3)
        vertices=vertices@matrix[:3,:3].T+matrix[:3,3]
        indices=np.asarray([tuple(f.vertices) for f in mesh.loop_triangles],int).reshape(-1,3)
        trail.append(vertices[indices])
    if not trail or not sum(map(len,trail)):
        raise ValueError('Exported North Trail does not cover the valley station')
    surfaces={'trail':np.concatenate(trail)}
    origin=np.asarray(before['belmonte_ground']['origin_cm'])/np.array([100.,-100.,100.])
    valley=[]
    for group in before['belmonte_ground']['groups']:
        name=group['asset'].rsplit('/',1)[-1].split('.')[0]
        print('GONDOLA GROUND:',name,flush=True)
        triangles=clipped(source.triangles(build/'belmonte/glb'/f'{name}.glb')+origin,GROUND_BOUNDS)
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
