"""Final, deterministic plant clearance for gate posts, passage and stone lanterns.

The six Torii instances use local Y for the crossbar (posts at Y +/-1.6).
Lanterns are separate placed meshes and must be tested in their own transforms.
Run after district scatter, without changing terrain or random streams.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import math
import numpy as np
from house_clearance import BUSH_RADII

GATE_FOOTPRINTS=((-0.55,0.55,-1.8,1.8),)
LANTERN_FOOTPRINTS=((-0.35,0.35,-0.35,0.35),)


def occupied_mask(name, placements, instances):
    if name.startswith('Tree'):radius=5.5
    elif name.startswith('Bush'):radius=BUSH_RADII.get(name,2.)
    elif name.startswith('Grass'):radius=.52
    else:return np.zeros(len(placements),dtype=bool)
    if not placements:return np.zeros(0,dtype=bool)
    points=np.asarray(placements,dtype=float);blocked=np.zeros(len(points),dtype=bool)
    reach=radius*points[:,4]+.18
    for asset,footprints in [('Torii',GATE_FOOTPRINTS),('Lantern',LANTERN_FOOTPRINTS)]:
        for x,y,z,yaw,scale in instances.get(asset,[]):
            a=math.radians(yaw);dx=points[:,0]-x;dy=points[:,1]-y
            lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
            for left,right,front,back in footprints:
                ex=np.maximum.reduce([left*scale-lx,lx-right*scale,np.zeros(len(lx))])
                ey=np.maximum.reduce([front*scale-ly,ly-back*scale,np.zeros(len(ly))])
                blocked|=np.hypot(ex,ey)<reach
    return blocked


def clear_torii_vegetation(world):
    instances=world['instances'];removed={}
    for name,items in instances.items():
        mask=occupied_mask(name,items,instances)
        if np.any(mask):
            removed[name]=int(mask.sum())
            instances[name]=[p for p,reject in zip(items,mask) if not reject]
    world['torii_vegetation_clearance']={'gates':len(instances.get('Torii',[])),
        'lanterns':len(instances.get('Lantern',[])), 'removed':removed,
        'gate_footprints':GATE_FOOTPRINTS,'lantern_footprints':LANTERN_FOOTPRINTS}
    return removed


def check_torii_vegetation(world):
    instances=world['instances']
    errors={name:int(mask.sum()) for name,items in instances.items()
            if np.any(mask:=occupied_mask(name,items,instances))}
    assert not errors,('vegetation overlaps torii or lanterns',errors)
    return {'gates_checked':len(instances.get('Torii',[])),
            'lanterns_checked':len(instances.get('Lantern',[])), 'clear':True}


if __name__=='__main__':
    import json,sys
    from pathlib import Path
    world=json.loads((yori.OUT/'world.json').read_text())
    if '--dry-run' in sys.argv:print(json.dumps({'would_remove':clear_torii_vegetation(world)}))
    print(json.dumps(check_torii_vegetation(world)))
