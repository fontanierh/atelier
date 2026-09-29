"""Secluded lake west of the mini-mega; all coordinates in Blender metres."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math
from pathlib import Path
import numpy as np
from village.layout import spline, nearest, sample, upper_surface, smooth
CENTER=(-90.,235.); RADII=(34.,23.); WATER=75.; CABIN=(-56.,215.,75.65)

def radius(x,y):
    angle=np.arctan2((y-CENTER[1])/RADII[1],(x-CENTER[0])/RADII[0])
    return np.hypot((x-CENTER[0])/RADII[0],(y-CENTER[1])/RADII[1])/(1+.045*np.sin(angle*3)+.035*np.cos(angle*5))

def integrate(world,h):
    # Applying twice is an error: preserve the source heights before local updates.
    if 'forest_lake' in world: raise ValueError('Lake already integrated; restore the pre-lake snapshot before rebuilding layout')
    before=h.copy(); axis=np.linspace(-world['size']/2,world['size']/2,len(h));x,y=np.meshgrid(axis,axis)
    r=radius(x,y)
    target=np.where(r<.80,WATER-2.8+1.4*(r/.8)**2,WATER-1.4+(r-.8)*8)
    target=np.minimum(target,WATER+.75)
    influence=smooth((1.48-r)/.30)
    h[:]=h*(1-influence)+target*influence
    # Level cabin/porch approach, well outside the lake bed, with soft outer banks.
    d=np.maximum(abs(x-CABIN[0])-5,abs(y-CABIN[1])-5)
    pad=smooth((5-d)/4)
    h[:]=h*(1-pad)+CABIN[2]*pad
    xy,s=spline([(55,234),(33,225),(13,229),(-5,239),(-24,232),(-38,214),(-47,214),(-47,221),(-53,223),(-57.8,220)])
    z=66.8+(CABIN[2]-66.8)*smooth(s/s[-1]);path=np.column_stack([xy,z])
    dist,pz=nearest(x,y,path);trail=smooth((6-dist)/3.8)
    h[:]=h*(1-trail)+pz*trail
    removed={}
    for name,placements in list(world['instances'].items()):
        if not name.startswith(('Tree','Bush','Grass','Rock')) and name!='Litter':continue
        a=np.array(placements,float)
        if not len(a):continue
        px,py=a[:,0],a[:,1];local=(px>-150)&(px<60)&(py>190)&(py<284);ii=np.flatnonzero(local)
        if not len(ii):continue
        lx,ly=px[ii],py[ii];pd,_=nearest(lx,ly,path);rr=radius(lx,ly);tree=name.startswith('Tree')
        house=np.hypot(lx-CABIN[0],ly-CABIN[1])<(13 if tree else 8)
        remove=(rr<(1.24 if tree else 1.08))|(pd<(7.5 if tree else 2.0))|house
        keep=np.ones(len(a),bool);keep[ii[remove]]=False
        for k,i in enumerate(ii):
            if remove[k]:continue
            a[i,2]+=float(sample(h,px[i],py[i])-sample(before,px[i],py[i]))
            if tree:a[i,2]=min(float(upper_surface(h,px[i]+dx,py[i]+dy)) for dx,dy in [(0,0),(.5,0),(-.5,0),(0,.5),(0,-.5)])-.15
        world['instances'][name]=a[keep].tolist();removed[name]=int(remove.sum())
    for name in ['Lake_Cabin','Lake_Shore','Lake_Trail','Lake_Water','Lake_Plants']:
        world['instances'][name]=[[0,0,0,0,1]]
    world['instances'].setdefault('Tree_Maple_lo',[]).append([-109.,246.,76.35,25.,.23])
    world['forest_lake']={'center':CENTER,'radii':RADII,'water_height':WATER,'cabin':CABIN,'trail':path.tolist(),'safe_shore':[-54,223,75.65],'removed':removed}
    world['shots'] += [[-116,195,87,43,-16],[-75,202,79,43,-4],[-87,235,130,0,-80]]

if __name__=='__main__':
    out=yori.OUT;backup=out/'forest_lake/source';backup.mkdir(parents=True,exist_ok=True)
    import shutil
    for name in ['world.json','heightmap.npy','heightmap.bin']:
        if not (backup/name).exists():shutil.copy2(out/name,backup/name)
    world=json.loads((backup/'world.json').read_text());h=np.load(backup/'heightmap.npy')
    integrate(world,h)
    (out/'world.json').write_text(json.dumps(world,separators=(',',':')))
    np.save(out/'heightmap.npy',h.astype(np.float32));h.astype('<f4').tofile(out/'heightmap.bin')
    (out/'forest_lake/layout.json').write_text(json.dumps(world['forest_lake'],indent=2))
