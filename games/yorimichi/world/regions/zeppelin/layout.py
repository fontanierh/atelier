"""Shared zeppelin stations, walkable trail and terrain clearances (Blender metres)."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math
from pathlib import Path
import numpy as np
from village.layout import spline, nearest, sample, smooth
ROOT=yori.REGIONS
# Station-local X points east, -Y is the front. Each platform shares this module. The list is the line's order: the
# zeppelin carries on the way it came and turns back at either end, and a passenger can choose any other stop.
STATIONS=[dict(key='zeppelin_forest',name='Woodland air station',origin=[-205.,230.,70.4]),
          dict(key='zeppelin_city',name='Hidamari air station',origin=[1273.,308.,34.3]),
          dict(key='zeppelin_megapark',name='Mega Park air station',origin=[-200.,1484.,130.])]
MESHES=['ZP_Woodland','ZP_City','ZP_MegaPark']
# Every pair of stops is a leg. Its cruise height (metres) clears the ground and trees under a 40 m corridor with room
# for the trailing camera: the Mega Park legs cross the western foothills (116 m) and the volcano's flank (163 m).
# All legs keep the first leg's speed, 1480 m in 28 s.
LEG_HEIGHTS={(0,1):155.,(0,2):185.,(1,2):225.}
CRUISE_SPEED=1480/28
# The Mega Park stop stands on the crest west of the park's top road, levelled into the north terrain's 10 m grid
# (hidamari/mountains.py): flat under the station and the docked ship, and along its footpath east to x -170, the last
# grid column clear of the park. From there a level footbridge crosses the dip the terrain makes beside the park and
# lands on the road deck, whose west edge on the footpath's line is at x -155.1 and 129.99 m.
PARK_PAD=(-222.,1472.,-184.,1496.)
PARK_WALK=((-189.,1477.),(-170.,1477.))
PARK_BRIDGE=((-170.5,1477.),(-154.,1477.))
PROPELLER_CENTERS=[[3.6,-6.0,6.1],[3.6,6.0,6.1]]
PROPELLER_RADIUS=1.65
SHIP=[6.,4.,1.65]; ENTRY=[6.,-.8,1.65]; SAFE=[6.,-8.7,.05]

def metadata():
    stations=[]
    for s in STATIONS:
        def world(p):return [a+b for a,b in zip(s['origin'],p)]
        stations.append({**s,'ship':world(SHIP),'entry':world(ENTRY),'safe':world(SAFE)})
    legs=[dict(stops=[a,b],height=h,seconds=round(math.dist(stations[a]['ship'][:2],stations[b]['ship'][:2])/CRUISE_SPEED,1))
          for (a,b),h in LEG_HEIGHTS.items()]
    return dict(stations=stations,legs=legs,propeller_centers=PROPELLER_CENTERS,propeller_radius=PROPELLER_RADIUS)

def city_pad(x,y,z):
    # Never touch the X=1240 road or Y=335 road/crossing.
    x,y=np.asarray(x),np.asarray(y)
    d=np.maximum(abs(x-1275)-14,abs(y-308)-10)
    w=smooth((5-d)/5)*smooth((x-1253)/3)*smooth((327-y)/3)
    return z*(1-w)+34.3*w

def megapark_pad(x,y,z):
    """The north terrain `z` levelled for the Mega Park stop and its footpath, never under the park itself."""
    from megapark.placement import contains
    oz=STATIONS[2]['origin'][2];x0,y0,x1,y1=PARK_PAD;(wx0,wy),_=PARK_WALK
    d=np.maximum(np.maximum(x0-x,x-x1),np.maximum(y0-y,y-y1))
    walk=(x>wx0-6)&(x<-159.5)
    w=np.maximum(smooth((10-d)/10),walk*smooth((17-abs(y-wy))/10))*~contains(x,y)
    return z+(oz-z)*w

def clear(instances,station=0,path=None,h=None,before=None):
    """Clear the vegetation over station `station` and within reach of its footpath `path` (x, y[, z] points).
    With h and before, heightmaps after and before levelling, re-seat what is kept on the levelled ground."""
    removed={}
    for name,placements in list(instances.items()):
        if not name.startswith(('Tree','Bush','Grass','Rock','Litter')) and not (station and ('Tree' in name or 'Bush' in name)):continue
        if not placements:continue
        a=np.array(placements,float);x,y=a[:,0],a[:,1]
        ox,oy,_=STATIONS[station]['origin']
        # Envelope + fins need a clean vertical rise, not merely a trunk clearance.
        mask=(abs(x-(ox+3))<(25 if ('Tree' in name) else 18))&(abs(y-oy)<(23 if ('Tree' in name) else 14))
        if path is not None:
            p=np.asarray(path,float);p=np.column_stack([p[:,:2],p[:,2] if p.shape[1]>2 else np.zeros(len(p))])
            (px0,py0),(px1,py1)=p[:,:2].min(0)-10,p[:,:2].max(0)+10
            ii=np.flatnonzero((x>px0)&(x<px1)&(y>py0)&(y<py1))
            d,_=nearest(x[ii],y[ii],p)
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
