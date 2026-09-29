"""Shared zeppelin stations, walkable trail and terrain clearances (Blender metres)."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math
from pathlib import Path
import numpy as np
from village.layout import spline, nearest, sample, smooth
ROOT=yori.REGIONS
# Station-local X points east, -Y is the front. Each platform shares this module.
STATIONS=[dict(key='zeppelin_forest',name='Woodland air station',origin=[-205.,230.,70.4]),
          dict(key='zeppelin_city',name='Hidamari air station',origin=[1273.,308.,34.3])]
PROPELLER_CENTERS=[[3.6,-6.0,6.1],[3.6,6.0,6.1]]
PROPELLER_RADIUS=1.65
SHIP=[6.,4.,1.65]; ENTRY=[6.,-.8,1.65]; SAFE=[6.,-8.7,.05]

def metadata():
    stations=[]
    for s in STATIONS:
        def world(p):return [a+b for a,b in zip(s['origin'],p)]
        stations.append({**s,'ship':world(SHIP),'entry':world(ENTRY),'safe':world(SAFE)})
    return dict(stations=stations,flight_height=155.,cruise_seconds=28.,propeller_centers=PROPELLER_CENTERS,propeller_radius=PROPELLER_RADIUS)

def city_pad(x,y,z):
    # Never touch the X=1240 road or Y=335 road/crossing.
    x,y=np.asarray(x),np.asarray(y)
    d=np.maximum(abs(x-1275)-14,abs(y-308)-10)
    w=smooth((5-d)/5)*smooth((x-1253)/3)*smooth((327-y)/3)
    return z*(1-w)+34.3*w

def clear(instances,city=False,path=None,h=None,before=None):
    removed={}
    for name,placements in list(instances.items()):
        if not name.startswith(('Tree','Bush','Grass','Rock','Litter')) and not (city and ('Tree' in name or 'Bush' in name)):continue
        if not placements:continue
        a=np.array(placements,float);x,y=a[:,0],a[:,1]
        ox,oy,_=STATIONS[int(city)]['origin']
        # Envelope + fins need a clean vertical rise, not merely a trunk clearance.
        mask=(abs(x-(ox+3))<(25 if ('Tree' in name) else 18))&(abs(y-oy)<(23 if ('Tree' in name) else 14))
        if path is not None:
            ii=np.flatnonzero((x>-245)&(x<-30)&(y>175)&(y<260))
            d,_=nearest(x[ii],y[ii],path)
            mask[ii]|=d<(7.5 if name.startswith('Tree') else 2.1)
        if h is not None:
            ii=np.flatnonzero((x>-245)&(x<-30)&(y>175)&(y<260)&~mask)
            for i in ii:a[i,2]+=float(sample(h,x[i],y[i])-sample(before,x[i],y[i]))
        instances[name]=a[~mask].tolist();removed[name]=int(mask.sum())
    return removed

def integrate(world,h):
    if 'zeppelin' in world:raise ValueError('Restore the pre-zeppelin baseline before integrating again')
    before=h.copy();axis=np.linspace(-world['size']/2,world['size']/2,len(h));x,y=np.meshgrid(axis,axis)
    d=np.maximum(abs(x+202)-16,abs(y-230)-12);w=smooth((7-d)/7)
    h[:]=h*(1-w)+70.4*w
    # Southern shore route avoids crossing lake water, its cabin apron and islet.
    xy,s=spline([(-47,214),(-47,205),(-61,198),(-85,196),(-113,199),(-137,211),(-158,216),(-178,210),(-190,219),(-199,221.3)])
    z=np.array([float(sample(before,*p)) for p in xy]);start=z[0];end=70.4
    # Smooth grades anchored at the real cabin approach; cap abrupt terrain humps.
    t=s/s[-1];z=start+(end-start)*smooth(t)+2.2*np.sin(np.pi*t)**2
    path=np.column_stack([xy,z]);dist,pz=nearest(x,y,path);w=smooth((5.3-dist)/3.4)
    h[:]=h*(1-w)+pz*w
    removed=clear(world['instances'],path=path,h=h,before=before)
    for name in ['ZP_Woodland','ZP_Trail']:
        world['instances'][name]=[[0,0,0,0,1]]
    world['zeppelin']={**metadata(),'trail':path.tolist(),'removed':removed}
    out=yori.OUT/'zeppelin';out.mkdir(parents=True,exist_ok=True)
    (out/'layout.json').write_text(json.dumps(world['zeppelin'],indent=2)+'\n')

if __name__=='__main__':
    import shutil
    out=yori.OUT;backup=out/'zeppelin/source';backup.mkdir(parents=True,exist_ok=True)
    for n in ['world.json','heightmap.npy','heightmap.bin']:
        if not (backup/n).exists():shutil.copy2(out/n,backup/n)
    world=json.loads((backup/'world.json').read_text());h=np.load(backup/'heightmap.npy')
    integrate(world,h)
    (out/'world.json').write_text(json.dumps(world,separators=(',',':')))
    np.save(out/'heightmap.npy',h.astype(np.float32));h.astype('<f4').tofile(out/'heightmap.bin')
