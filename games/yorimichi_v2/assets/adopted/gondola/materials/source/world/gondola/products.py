"""Verified owned ground query construction for ropeway site preparation."""
import hashlib
import json

import numpy as np
from gondola.inputs import snapshot
from gondola.terrain import Ground
from regions.belmonte import layout as B
from terrain_product import Mesh, load
from terrain_query import Surface


def triangle_surface(triangles, owner):
    triangles=np.asarray(triangles,float).reshape(-1,3,3)
    mesh=Mesh.from_polygons(triangles.reshape(-1,3),np.arange(triangles.size//3).reshape(-1,3))
    return Surface(mesh,owner=owner,stage='final')


def ground(build):
    folder=build/'gondola/world'
    receipt=json.loads((folder/'ground.json').read_text())
    if receipt['inputs']!=snapshot(build):
        raise ValueError('Gondola ground exports changed; rebuild ground queries')
    path=folder/'ground.npz'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=receipt['output_sha256']:
        raise ValueError('Gondola ground query product changed')
    surfaces={key:Surface(load(build/f'terrain/{owner}/final.npz',owner=owner,stage='final',city=True),owner=owner,stage='final')
              for key,owner in [('city','HD_Terrain'),('mountain','HD_NorthMountains')]}
    with np.load(path,allow_pickle=False) as arrays:
        for key,owner in [('trail','HD_NorthTrail'),('valley','BelmonteTerrain'),('apron','SM_BM_NorthApron')]:
            surfaces[key]=triangle_surface(arrays[key],owner)
    return Ground(**surfaces,city_bounds=(300,-1000,1420,500),
                  mountain_bounds=(-700,500,2400,B.SOUTH_JOIN),valley_bounds=B.BOUNDS,
                  apron_bounds=(B.BOUNDS[0]-B.APRON,B.SOUTH_JOIN,B.BOUNDS[2]+B.APRON,B.BOUNDS[3]+B.APRON))
