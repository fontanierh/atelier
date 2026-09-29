"""Deterministic final vegetation exclusion around every legacy minka placement.

Runs after all scatter/integrations, so rejection cannot shift random streams or
miss bank grass, hand-planted trees, flower bushes or later district scattering.
Coordinates match the actual House mesh, including the engawa and front steps.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import math
import numpy as np

# Ground-level occupied rectangles: foundation, porch, then narrow stairs.
HOUSE_FOOTPRINTS=((-4.8,4.8,-3.5,3.5),(-4.75,4.75,-4.35,-3.15),(-1.05,1.05,-5.18,-4.1))
ROOF_FOOTPRINT=(-5.65,5.65,-4.35,4.35)
BUSH_RADII={'Bush_Flower_A':1.75,'Bush_Flower_B':1.45,'Bush_Green_A':1.88,
            'Bush_Green_B':1.48,'Bush_Ochre_A':1.98,'Bush_Ochre_B':1.58}
ROCK_RADII={'Rock_A':1.8,'Rock_B':1.1,'Rock_C':2.6}


def occupied_mask(name,placements,houses):
    """Account for plant crown/blade width; a clear root alone is insufficient."""
    if not placements or not houses:return np.zeros(len(placements),dtype=bool)
    if name.startswith('Tree'):radius=5.5;footprints=(ROOF_FOOTPRINT,)
    elif name.startswith('Bush'):radius=BUSH_RADII.get(name,2.0);footprints=HOUSE_FOOTPRINTS
    elif name.startswith('Grass'):radius=.52;footprints=HOUSE_FOOTPRINTS
    elif name.startswith('Rock'):radius=ROCK_RADII.get(name,2.6);footprints=HOUSE_FOOTPRINTS
    elif name=='Litter':radius=.25;footprints=HOUSE_FOOTPRINTS
    else:return np.zeros(len(placements),dtype=bool)
    points=np.asarray(placements,dtype=float);blocked=np.zeros(len(points),dtype=bool)
    reach=radius*points[:,4]+.18
    for hx,hy,_,yaw,scale in houses:
        angle=math.radians(yaw);dx=points[:,0]-hx;dy=points[:,1]-hy
        lx=dx*math.cos(angle)+dy*math.sin(angle);ly=-dx*math.sin(angle)+dy*math.cos(angle)
        for left,right,front,back in footprints:
            # Euclidean distance to a rotated rectangle avoids a conspicuous
            # square clearing while allowing plants to frame its outside edge.
            ex=np.maximum.reduce([left*scale-lx,lx-right*scale,np.zeros(len(lx))])
            ey=np.maximum.reduce([front*scale-ly,ly-back*scale,np.zeros(len(ly))])
            blocked|=np.hypot(ex,ey)<reach
    return blocked


def clear_house_vegetation(world):
    houses=world['instances'].get('House',[]);removed={}
    for name,items in world['instances'].items():
        blocked=occupied_mask(name,items,houses)
        if np.any(blocked):
            removed[name]=int(blocked.sum())
            world['instances'][name]=[p for p,reject in zip(items,blocked) if not reject]
    world['house_vegetation_clearance']={'houses':len(houses),'removed':removed,
        'footprints':[list(p) for p in HOUSE_FOOTPRINTS],'tree_roof_footprint':list(ROOF_FOOTPRINT)}
    return removed


def check_house_vegetation(world):
    houses=world['instances'].get('House',[])
    errors={name:int(mask.sum()) for name,items in world['instances'].items()
            if np.any(mask:=occupied_mask(name,items,houses))}
    assert not errors,('vegetation overlaps legacy houses',errors)
    return {'house_vegetation_placements_checked':len(houses),'house_vegetation_clear':True}


if __name__=='__main__':
    import json,sys
    from pathlib import Path
    world=json.loads((yori.OUT/'world.json').read_text())
    if '--dry-run' in sys.argv:print(json.dumps({'would_remove':clear_house_vegetation(world)}))
    print(json.dumps(check_house_vegetation(world)))
