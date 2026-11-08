"""Shared zeppelin stations, walkable trail and terrain clearances (Blender metres)."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
from functools import lru_cache
import json, math
from pathlib import Path
import numpy as np
from village.layout import spline, nearest, sample, smooth
ROOT=yori.REGIONS
# Station-local X points east, -Y is the front. Each platform shares this module. The list is the line's order: the
# zeppelin carries on the way it came and turns back at either end, and a passenger can choose any other stop.
STATIONS=[dict(key='zeppelin_forest',name='Woodland air station',origin=[-205.,230.,70.4]),
          dict(key='zeppelin_city',name='Hidamari air station',origin=[1273.,321.,35.5]),
          dict(key='zeppelin_megapark',name='Mega Park air station',origin=[-200.,1484.,130.]),
          dict(key='zeppelin_belmonte',name='Belmonte air station',origin=[410.,4660.,217.75])]
MESHES=['ZP_Woodland','ZP_City','ZP_MegaPark','ZP_Belmonte']
# Every pair of stops is a leg. Its cruise height (metres) clears the ground and trees under a 40 m corridor with room
# for the trailing camera: the Mega Park legs cross the western foothills (116 m) and the volcano's flank (163 m).
# All legs keep the first leg's speed, 1480 m in 28 s.
LEG_HEIGHTS={(0,1):155.,(0,2):185.,(0,3):600.,(1,2):240.,(1,3):910.,(2,3):520.}
CRUISE_SPEED=1480/28
# The Mega Park stop stands on the crest west of the park's top road, on the gate's ground (megapark/gate.py): level
# under the station and the docked ship, and along its footpath east to x -170. From there a level footbridge crosses
# the dell beside the park to a sill against the road deck. The deck's west edge (DECK_EDGE) crosses the footpath's
# line at x -155.1 and 129.99 m on a slant: 0.59 m further west and 5.6 cm higher for every metre north.
PARK_PAD=(-222.,1472.,-184.,1496.)
PARK_WALK=((-189.,1477.),(-170.,1477.))
PARK_BRIDGE=((-170.5,1477.),(-156.2,1477.))
DECK_EDGE=((-155.1,1477.,129.987),-.59,.056)
# The Belmonte stop stands on the naturally level meadow outside Porta NW, joined to the northwest gate road by a stone footpath.
BELMONTE_WALK=((416.,4651.2),(414.8,4626.),(413.2,4602.),(415.8,4594.),(418.2,4591.8))
PROPELLER_CENTERS=[[3.6,-6.0,6.1],[3.6,6.0,6.1]]
PROPELLER_RADIUS=1.65
SHIP=[6.,4.,1.65]; ENTRY=[6.,-.8,1.65]; SAFE=[6.,-8.7,.05]

def metadata():
    """@cc [owner:fontanierh,label:correctness] hidamari-air-rail-clearance
    The city air station, its pedestrian approach and the docked ship's turning envelope MUST clear the town
    railway. Station origins MUST also determine ship, entry, landing and flight endpoints and leg durations.
    """
    stations=[]
    for s in STATIONS:
        def world(p):return [a+b for a,b in zip(s['origin'],p)]
        stations.append({**s,'ship':world(SHIP),'entry':world(ENTRY),'safe':world(SAFE)})
    legs=[dict(stops=[a,b],height=h,seconds=round(math.dist(stations[a]['ship'][:2],stations[b]['ship'][:2])/CRUISE_SPEED,1))
          for (a,b),h in LEG_HEIGHTS.items()]
    return dict(stations=stations,legs=legs,propeller_centers=PROPELLER_CENTERS,propeller_radius=PROPELLER_RADIUS)

def city_pad(x,y,z):
    # Never touch the X=1240 road or Y=335 road/crossing.
    ox,oy,oz=STATIONS[1]['origin']
    x,y=np.asarray(x),np.asarray(y)
    d=np.maximum(abs(x-(ox+2))-14,abs(y-oy)-10)
    w=smooth((5-d)/5)*smooth((x-1253)/3)*smooth((327-y)/3)
    return z*(1-w)+oz*w

def city_path():
    """Join the open east lane north of its railway barrier, then skirt the ticket hut to the front apron.

    It turns south at x 1260, on the apron's graded ground: turning at x 1255 took it 2.2 m down the railway
    cutting's bank and back (operator note 381), and east of x 1261 the station's sign and planter stand."""
    ox,oy,_=STATIONS[1]['origin']
    return spline([(1240.,329.),(1255.,329.),(1260.,323.),(1260.,oy+SAFE[1]),(ox+SAFE[0],oy+SAFE[1])])[0]

def megapark_pad(x,y,z):
    """The north terrain `z` levelled for the Mega Park stop and its footpath, never under the park itself."""
    from megapark.placement import contains
    oz=STATIONS[2]['origin'][2];x0,y0,x1,y1=PARK_PAD;(wx0,wy),_=PARK_WALK
    d=np.maximum(np.maximum(x0-x,x-x1),np.maximum(y0-y,y-y1))
    walk=(x>wx0-6)&(x<-159.5)
    w=np.maximum(smooth((10-d)/10),walk*smooth((17-abs(y-wy))/10))*~contains(x,y)
    return z+(oz-z)*w

@lru_cache(maxsize=1)
def belmonte_path():
    return spline(list(BELMONTE_WALK))[0]

def belmonte_clear(x,y,kind='tree'):
    """Whether (x, y) in world metres lies over the Belmonte station or within reach of its Porta NW footpath."""
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    ox,oy,_=STATIONS[3]['origin']
    tree=kind=='tree'
    mask=np.array((abs(x-(ox+3))<(25 if tree else 18))&(abs(y-oy)<(23 if tree else 14)),bool)
    inside=(x>400.)&(x<430.)&(y>4580.)&(y<4662.)
    if np.any(inside):
        xy=belmonte_path();p=np.column_stack([xy,np.zeros(len(xy))])
        d,_=nearest(x[inside],y[inside],p)
        mask[inside]|=d<(7.5 if tree else 2.1)
    return mask

def clear(instances,station=0,path=None,h=None,before=None):
    """Clear the vegetation over station `station` and within reach of its footpath `path` (x, y[, z] points).
    With h and before, heightmaps after and before levelling, re-seat what is kept on the levelled ground."""
    if station==1 and path is None:path=city_path()
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
    for name in ['ZP_Woodland','ZP_Belmonte','ZP_Trail']:
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
