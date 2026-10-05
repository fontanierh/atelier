"""Deterministic city layout in the approved world coordinates (metres, Z up)."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json, math, random
from functools import lru_cache
from pathlib import Path
from hidamari import arrival as arrival_road, house_gardens, mountains, park_grounds, station_yard, temple_precinct
from megapark import trail as park_trail
import numpy as np
ROOT=yori.REGIONS
OUT=yori.OUT/'hidamari'
ROAD_Y=[-90,15,140,230,335,75]
ROAD_X=[410,560,730,920,1120,1240]
# (paving, asphalt) half-widths in metres. The east-west shop streets and the civic axis x = 730 (the arcade's floor and
# the plaza steps meet its paving) keep the broad section; the other north-south streets are lanes, 11 m wall line to
# wall line of paving with a 6 m carriageway, so the fences, hedges and poles along them close the view.
WIDE,LANE=(8.,3.8),(5.5,3.)
def road_width(x=None,y=None):
    """The (paving, asphalt) half-widths of the street along x = x or y = y."""
    return LANE if x is not None and x!=730 else WIDE
H=None

def _base_height(x,y):
    global H
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    z=np.interp(y,[-300,-125,-90,15,140,230,335,450],[-8,2.4,3.2,10,20,28,36,47])
    if H is None:H=np.load(yori.OUT/'heightmap.npy')
    t=np.clip((x-300)/70,0,1);t=t*t*(3-2*t)
    edge=np.interp(np.clip(y,-300,300),np.linspace(-300,300,H.shape[0]),H[:,-1])
    z=edge*(1-t)+z*t
    radius=np.sqrt(((x-1030)/46)**2+((y-284)/32)**2)
    blend=np.clip((1.65-radius)/.5,0,1);blend=blend*blend*(3-2*blend)
    z=z*(1-blend)+30.8*blend
    return z

def street_height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    cuts=[];values=[]
    for cy in sorted(ROAD_Y):cuts.extend([cy-8,cy+8]);values.extend([cy,cy])
    # Horizontal intersections are level; the same profile drives crossing
    # streets and terrain, so separate road ribbons cannot create raised steps.
    def profile(px,py):
        my=np.interp(py,cuts,values);my=np.where(py<cuts[0],py+8,np.where(py>cuts[-1],py-8,my))
        bx=np.clip((px-300)/90,0,1);bx=bx*bx*(3-2*bx)
        z=_base_height(px,py)*(1-bx)+_base_height(px,my)*bx
        radius=np.sqrt(((px-1030)/46)**2+((py-284)/32)**2)
        pond_blend=np.clip((1.65-radius)/.5,0,1);pond_blend=pond_blend*pond_blend*(3-2*pond_blend)
        return z*(1-pond_blend)+30.8*pond_blend
    z=profile(x,y)
    if not hasattr(street_height,'start'):
        street_height.start=max(json.loads((yori.OUT/'world.json').read_text())['road'],key=lambda q:q[0])[:2]
    anchors=[street_height.start,[335,85],[390,140],[650,140]]
    distance=np.full(x.shape,1e6);tx=x;ty=y
    for a,b in zip(anchors,anchors[1:]):
        vx=b[0]-a[0];vy=b[1]-a[1];t=np.clip(((x-a[0])*vx+(y-a[1])*vy)/(vx*vx+vy*vy),0,1)
        px=a[0]+t*vx;py=a[1]+t*vy;dd=np.hypot(x-px,y-py)
        near=dd<distance;tx=np.where(near,px,tx);ty=np.where(near,py,ty);distance=np.minimum(distance,dd)
    weight=np.clip((12-distance)/4,0,1);weight=weight*weight*(3-2*weight)
    if not np.any(weight):return z
    return z*(1-weight)+profile(tx,ty)*weight

@lru_cache(maxsize=1)
def shop_sites():
    """One source of lot coordinates for buildings and their supporting terrain."""
    sites=[]
    for row,cy in enumerate(ROAD_Y):
        for side in [-1,1]:
            if cy==-90 and side<0:continue
            y=min(cy+side*19,351)
            for col,x in enumerate(range(455,1220,27)):
                if min(abs(x-t) for t in ROAD_X)<17:continue
                if y<-120 or y>360:continue
                if 870<x<1130 and y>230:continue
                if 650<x<810 and 120<y<215:continue
                if 575<x<810 and y>245:continue
                if 1115<x and y>230:continue
                if 830<x<870 and y<20:continue
                if cy==75 and 588<x<723:continue
                # The old last lot at x=1103 overlapped the x=1120 sidewalk.
                # Share the four-metre setback across this block, keeping every
                # shop/variant and at least 1.33 m between their 25 m aprons.
                if 920<x<1120:x=941+(x-941)*158/162
                sites.append((f'HD_Shop_{(row*7+col)%16:02d}',x,y,0 if side>0 else 180,cy,col,side))
    # The station square's flanks (station_yard.SHOPS), facing the y=230 street.
    sites+=[(name,x,y,0,230,1,1) for name,x,y in station_yard.SHOPS]
    return tuple(sites)

def arcade_sites():
    """The roofed lane shops share level support with the central street."""
    for side in (-1,1):
        for i in range(-1,14):
            if i in (3,10):continue
            asset=f'HD_ArcadeShop_{((3 if i==-1 else 0 if i==0 else i-1)+(0 if side>0 else 1))%6:02d}'
            yield asset,614.5+i*7,75+side*13.4,0 if side>0 else 180


HOUSE=(10.,9.)       # the back-lane house plot (kit/house.py), width x depth
HOUSE_ALLEY=7.       # metres between facing house plots across a block's inner lane

def _clear_of_hero(x,y):
    """Open ground for an ordinary lot: shop_sites' own exclusions (squares, park, temple hill, station, canal)."""
    if 870<x<1130 and y>230:return False
    if 650<x<810 and 120<y<215:return False
    if 575<x<810 and y>245:return False
    if 1115<x and y>230:return False
    if 830<x<870 and y<20:return False
    if 808<x<828 and 238<y<278:return False      # the east temple's approach (temple_precinct)
    return 430<x<1230

@lru_cache(maxsize=1)
def house_sites():
    """Back-lane family houses filling the block interiors behind the shop rows: two rows per block facing each
    other across a narrow inner lane, a plot every 11.5 m with the odd gap left as a garden, clear of the
    north-south lanes and the public spaces. Front faces -Y before yaw, so the south row turns 180."""
    r=random.Random(1907);sites=[];w,d=HOUSE
    ys=sorted(ROAD_Y)
    for a,b in zip(ys,ys[1:]):
        lo=a+31.;hi=b-31.          # behind the shop rows (cy +- 19, 21.2 deep) with a metre to spare
        if hi-lo<2*d+HOUSE_ALLEY:continue
        rows=[(lo+d/2,180),(lo+d+HOUSE_ALLEY+d/2,0)]
        for y,yaw in rows:
            x=440.+r.uniform(0,4)
            while x<1230:
                lane=min(ROAD_X,key=lambda c:abs(x-c))
                if abs(x-lane)<road_width(x=lane)[0]+w/2+5.5:x+=2.;continue
                if all(_clear_of_hero(x+sx*w/2,y+sy*d/2) for sx in (-1,1) for sy in (-1,1)) and r.random()>.16:
                    sites.append((f'HD_House_{r.randrange(4):02d}',round(x,2),y,yaw))
                x+=w+1.5+(r.uniform(4,9) if r.random()<.12 else 0)
    return tuple(sites)

@lru_cache(maxsize=1)
def terrain_pads():
    """Flat module/apron datums, with blended earth outside the occupied footprint.

    Shops meet the height of their adjacent street instead of floating at the
    uphill lot centre. Dimensions include attached stairs, tubs and benches.
    Hero forecourts meet their existing approach terrain. Metres, local -Y front.
    """
    pads=[]
    for asset,x,y,yaw,cy,_,_ in shop_sites():
        pads.append(dict(asset=asset,x=x,y=y,yaw=yaw,z=float(street_height(x,cy)),
                         half_width=12.5,front=-10.6,back=9.0,fade_x=4.,fade_y=5.))
    for p in temple_precinct.PADS:pads.append(dict(p,z=float(street_height(p['x'],p['y']))))
    for asset,x,y,yaw in house_sites():
        pads.append(dict(asset=asset,x=x,y=y,yaw=yaw,z=float(street_height(x,y)),
                         half_width=HOUSE[0]/2+.5,front=-HOUSE[1]/2-.5,back=HOUSE[1]/2+.5,fade_x=3.,fade_y=3.,group='houses'))
    for asset,x,y,w,front,back in [('HD_Station',1185,290,25.5,-11.5,10.5),
                                 ('HD_Shrine',600,280,5.6,-9.5,4.5)]:
        pads.append(dict(asset=asset,x=x,y=y,yaw=0,z=float(street_height(x,y+front)),
                         half_width=w,front=front,back=back,fade_x=7.,fade_y=8.))
    # The railway cutting behind the station, after the station's own pad so its floor wins where they meet.
    pads.append(dict(station_yard.PAD,z=float(street_height(1185,278.5))+station_yard.BED))
    # Full-wall support is required behind the arcade too: the old central-
    # street datum left south backs floating 1.1 m and buried north backs 1 m.
    for asset,x,y,yaw in arcade_sites():
        pads.append(dict(asset=asset,x=x,y=y,yaw=yaw,z=float(street_height(x,75)),
                         half_width=3.5,front=-5.4,back=5.3,fade_x=1.,fade_y=2.,group='arcade'))
    # Axis-aligned earthwork includes the rotated temple's whole veranda. No
    # road is moved: shoulders still fade out before the protected road skin.
    for asset,x,y,w,front,back in [('HD_Temple',690,300,13.8,-14.5,9.2),
                                  ('HD_Temple',790,305,18.4,-18.4,14.3),
                                  ('HD_Pavilion',1040,350,5.3,-4.3,4.3),
                                  ('HD_Pavilion',985,265,5.3,-4.3,4.3),
                                  ('HD_Market',600,-113,19.3,-3.8,3.8),
                                  ('HD_Market',730,-113,19.3,-3.8,3.8)]:
        pads.append(dict(asset=asset,x=x,y=y,yaw=0,z=float(street_height(x,y)),
                         half_width=w,front=front,back=back,fade_x=3.,fade_y=4.,group='public'))
    # Park seating and adjacent planters need a small level rest area; their
    # old centre-only placement crossed up to 65 cm of bank relief.
    for x,y in [(998,250),(1064,250),(995,319),(1080,320),(605,275),(765,285)]:
        z=float(street_height(600,270.5) if x==605 else street_height(x,y))
        pads.append(dict(asset='HD_Bench',x=x,y=y,yaw=0,z=z,half_width=4.1,
                         front=-1.1,back=1.1,fade_x=1.5,fade_y=1.5,group='props'))
    return tuple(pads)

def height(x,y):
    """Terrain and props share flat lot support while all road corridors stay fixed."""
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    from zeppelin.layout import city_pad
    base=city_pad(x,y,street_height(x,y))
    if not x.size or np.max(x)<435 or np.min(x)>1240 or np.max(y)<-110 or np.min(y)>372:return base
    shape=x.shape;xx=x.ravel();yy=y.ravel();weights=np.zeros(xx.size);targets=np.zeros(xx.size)
    coverage=np.zeros(xx.size)
    core=np.zeros(xx.size,dtype=bool);core_z=np.zeros(xx.size)
    xmin,xmax=float(xx.min()),float(xx.max());ymin,ymax=float(yy.min()),float(yy.max())
    for p in terrain_pads():
        sign=1 if p['yaw']==0 else -1
        y0,y1=sorted((p['y']+sign*p['front'],p['y']+sign*p['back']))
        extent=p['half_width']+p['fade_x']
        if xmax<p['x']-extent or xmin>p['x']+extent or ymax<y0-p['fade_y'] or ymin>y1+p['fade_y']:continue
        mask=(abs(xx-p['x'])<extent)&(yy>y0-p['fade_y'])&(yy<y1+p['fade_y'])
        idx=np.flatnonzero(mask)
        dx=np.maximum(0,abs(xx[idx]-p['x'])-p['half_width'])
        dy=np.maximum(0,np.maximum(y0-yy[idx],yy[idx]-y1))
        w=(1-mountains.smooth(dx/p['fade_x']))*(1-mountains.smooth(dy/p['fade_y']))
        # Let the nearest plateau dominate continuously at its edge. Ordinary
        # weighted averaging followed by a flat-core override creates a ledge
        # wherever the neighbouring lot's shoulder overlaps the core boundary.
        priority=w/np.maximum(1e-7,1-w)
        coverage[idx]+=w;weights[idx]+=priority;targets[idx]+=priority*p['z']
        inside=idx[(dx==0)&(dy==0)];core[inside]=True;core_z[inside]=p['z']
    # Overlapping shoulder blends meet without humps in the narrow side alleys.
    target=np.divide(targets,weights,out=base.ravel().copy(),where=weights>0)
    target[core]=core_z[core];strength=np.minimum(1,coverage);strength[core]=1
    vertical=np.min(abs(xx[:,None]-np.asarray(ROAD_X)),axis=1)
    vertical=np.where((yy>=-90)&(yy<=350),vertical,np.inf)
    road_distance=np.minimum(vertical,np.min(abs(yy[:,None]-np.asarray(ROAD_Y)),axis=1))
    # Roads occupy +/-8 m. The closest pad starts at 8.4 m; retain a smooth join.
    strength*=mountains.smooth((road_distance-8)/.4)
    return (base.ravel()+(target-base.ravel())*strength).reshape(shape)

def terrain_axes():
    """Keep the coarse distant grid; resolve plateau edges and shoulder curves."""
    xs=set(np.arange(300.,1421.,4.));ys=set(np.arange(-300.,501.,4.))
    for p in terrain_pads():
        sign=1 if p['yaw']==0 else -1
        # A house row shares its y lines; its plots' x edges stay on the 4 m grid (the flat core still holds).
        for side in ([] if p.get('group')=='houses' else [-1,1]):
            for distance in np.linspace(0,p['fade_x'],5):xs.add(p['x']+side*(p['half_width']+distance))
        for edge in [p['front'],p['back']]:
            side=-1 if edge<0 else 1
            for distance in np.linspace(0,p['fade_y'],6):ys.add(p['y']+sign*(edge+side*distance))
    for cx in ROAD_X:
        for side in [-1,1]:
            for d in sorted({8.,8.2,8.4,road_width(x=cx)[0],road_width(x=cx)[0]+.2}):xs.add(cx+side*d)
    for cy in ROAD_Y:
        for side in [-1,1]:
            for d in [8.,8.2,8.4]:ys.add(cy+side*d)
    for _,_,y,yaw in house_sites():
        if yaw==180:
            for d in (-5.85,-3.5,-3.1,3.1,3.5,5.85):ys.add(y+HOUSE[1]/2+HOUSE_ALLEY/2+d)   # the lane between the rows: walls, ditches, house fronts
    return np.unique(np.round(sorted(xs),6)),np.unique(np.round(sorted(ys),6))

def pond(x,y):return ((x-1030)/46)**2+((y-284)/32)**2<1

def canal(x,y):return (abs(x-848)<8)&(y<-5)&(y>-130)

def generate():
    world=json.loads((yori.OUT/'world.json').read_text());r=random.Random(921)
    inst={};buildings=[];residents=[]
    def put(name,x,y,z=None,yaw=0,scale=1):
        z=float(height(x,y)) if z is None else z
        inst.setdefault(name,[]).append([round(x,3),round(y,3),round(z,3),yaw,scale])
    # Reference modules and attached props rest on the same plateau as the terrain.
    for name,x,y,yaw,cy,col,side in shop_sites():
        z=float(height(x,y))
        put(name,x,y,z,yaw)
        buildings.append({'asset':name,'position':[x,y,z],'yaw':yaw,'width':25,'depth':21.2,'terrain_pad':True})
        if col%2==0:put('HD_Planter',x-9,y-side*10,yaw=0)
    for name,x,y,yaw in house_sites():
        z=float(street_height(x,y))
        put(name,x,y,z,yaw)
        buildings.append({'asset':name,'position':[x,y,z],'yaw':yaw,'width':HOUSE[0],'depth':HOUSE[1],'terrain_pad':True})
    # A close, varied shop perimeter encloses the clock square.
    for side,x,yaw in [(0,663,90),(1,796,-90)]:
        for i,y in enumerate(range(150,207,7)):
            if side==1 and y in [171,178]:continue
            name=f'HD_ArcadeShop_{(i+side+1)%6:02d}';z=float(height(x,y-3.5))-.035
            put(name,x,y,z,yaw)
            buildings.append({'asset':name,'position':[x,y,z],'yaw':yaw,'width':7,'depth':10})
    for i,x in enumerate(range(677,791,7)):
        if 708<x<751 or x>785:continue
        name=f'HD_ArcadeShop_{i%6:02d}';y=208;z=float(height(x,y-6.6))-.035
        put(name,x,y,z)
        buildings.append({'asset':name,'position':[x,y,z],'yaw':0,'width':7,'depth':10})
    for i,x,y in [(1,683.5,149),(2,690.5,163),(0,712,130),(0,775,176),(3,782,176),(4,789,176)]:
        yaw=-90 if x==712 else 0
        name=f'HD_ArcadeShop_{i:02d}';z=float(height(x-6.6,y) if yaw else height(x,y-6.6))-.035
        put(name,x,y,z,yaw)
        buildings.append({'asset':name,'position':[x,y,z],'yaw':yaw,'width':7,'depth':10})
    # Seat each plaza facade on its actual rotated frontage, not a downhill
    # Y sample. Keep the high end of the ground-floor glazing above the paving.
    for b in buildings:
        if not b['asset'].startswith('HD_ArcadeShop'):continue
        x,y,old_z=b['position'];a=math.radians(b['yaw'])
        def at(lx,ly):return float(height(x+lx*math.cos(a)-ly*math.sin(a),y+lx*math.sin(a)+ly*math.cos(a)))
        z=max(at(lx,-5.15) for lx in [-3.5,0,3.5])+.04
        # Side/rear sills start 1.1 m above the datum.
        z=max(z,max(at(lx,ly) for lx in [-3.5,3.5] for ly in [-5,5])-.85)
        b['position'][2]=z
        for item in inst[b['asset']]:
            if item[0]==x and item[1]==y:item[2]=round(z,3)
    put('HD_PlazaShopApproaches',0,0,0)
    # Shared three-sided dressing prevents blank shop gables around the open square.
    for b in buildings:
        x,y,z=b['position']
        if b['asset'].startswith('HD_ArcadeShop') and 120<y<215:
            dressing='HD_PlazaShopSidesCorner' if (x,y)==(789,176) else 'HD_PlazaShopSides'
            put(dressing,x,y,z,b['yaw'])
    # Hero buildings and public-space anchors.
    for name,x,y,yaw in [('HD_ClockHall',730,178,0),('HD_Temple',690,300,0),('HD_Temple',790,305,25),('HD_Shrine',600,280,0),('HD_Station',1185,290,0),('HD_Market',600,-113,180),('HD_Market',730,-113,180),('HD_Pavilion',1040,350,0),('HD_Pavilion',985,265,0),('HD_Arcade',660,75,0),('HD_Playground',1100,260,0)]:
        put(name,x,y,yaw=yaw)
        if name in ('HD_Station','HD_Shrine'):
            width,depth=(51,23) if name=='HD_Station' else (11.2,19)
            buildings.append({'asset':name,'position':[x,y,float(height(x,y))],
                              'yaw':yaw,'width':width,'depth':depth,'terrain_pad':True})
        elif name in ('HD_Temple','HD_Pavilion','HD_Market'):
            width,depth={'HD_Temple':(28,28),'HD_Pavilion':(11,9),'HD_Market':(39,8)}[name]
            buildings.append({'asset':name,'position':[x,y,float(height(x,y))],
                              'yaw':yaw,'width':width,'depth':depth,'terrain_pad':True})
    # Reference arcade: connected narrow shop bays, with furniture behind pillars.
    for name,x,y,yaw in arcade_sites():
        z=float(height(x,y));put(name,x,y,z,yaw)
        buildings.append({'asset':name,'position':[x,y,z],'yaw':yaw,'width':7,'depth':10,'terrain_pad':True})
        # The display shell has no lower rear wall. Dress the forest-facing
        # backs as well as the plaza shops; these sides are reachable on foot.
        put('HD_PlazaShopSides',x,y,z,yaw)
    put('HD_ArcadeFloor',0,0,0)
    put('HD_ArcadeRoof',660,75)
    put('HD_ArcadeLanterns',660,75)
    put('HD_ArcadeGate',744,75)
    for x in [609,716]:
        for y in [66.2,83.8]:put('HD_ArcadeTree',x,y,scale=1.12)
    for x in [635.5,684.5]:
        for y in [64.5,85.5]:put('HD_ArcadeTree',x,y,scale=.95)
    # Shopkeepers browse at the edge; walkers stay outside the central skate line.
    arcade_people=[(607.5,81.1,90,.99,[.14,.20,.34],'Interact'),
                   (608,68.9,-90,1.08,[.34,.12,.19],'Idle'),
                   (642,81,90,.94,[.16,.27,.18],'Interact'),
                   (665,69,-90,1.04,[.36,.24,.12],'Idle'),
                   (694,81,90,.97,[.19,.16,.31],'Idle')]
    for x,y,yaw,scale,colour,action in arcade_people:
        position=[x,y,float(height(x,y))+.10]
        residents.append({'residents':[{'position':position,'yaw':yaw,'scale':scale,
            'colour':colour,'action':action,'destination':position}]})
    for x,y,colour in [(631,80,[.18,.27,.31]),(674,70,[.33,.17,.12])]:
        residents.append({'residents':[{'position':[x,y,float(height(x,y))+.10],
            'destination':[x+5,y,float(height(x+5,y))+.10],'yaw':0,'scale':1.0,
            'colour':colour,'action':'Walk'}]})
    # Harbor workboats are below quay level, not resting on land.
    for i in range(12):put('HD_Boat',460+i*32,-150-(i%2)*19,.45,yaw=0 if i%2 else 180,scale=.95+.08*(i%4))
    put('HD_Lighthouse',440,-225,2.3)
    for x in range(452,865,12):
        put('HD_Bollard',x,-125,2.4)
    # Street lamps, trees and benches; no bushes in travel lanes.
    for cy in ROAD_Y:
        for x in range(420,1240,42):
            if cy>230 and 900<x<1140:continue
            if cy==75 and 588<x<723:continue
            put('HD_Lamp',x,cy+7.8)
            if min(abs(x-t) for t in ROAD_X)>12 and not (cy==75 and 610<x<710):
                put('Tree_Ginkgo' if x%3 else 'Tree_Maple_A',x,cy-10,scale=1.2)
    for x,y in [(680,145),(780,145),(680,180),(780,180),(700,206),(760,206)]:put('Tree_Ginkgo',x,y,scale=1.4)
    # The park's trees stand in groves with lawns between them, not scattered evenly.
    groves=[(955,258,9),(1000,300,8),(958,322,10),(1075,262,8),(1100,318,9),(1040,250,6),(1010,340,7),(1085,342,7)]
    for i in range(95):
        gx,gy,spread=groves[i%len(groves)]
        x=gx+r.gauss(0,spread);y=gy+r.gauss(0,spread*.8)
        if not (940<x<1120 and 245<y<350) or pond(x,y) or abs(y-335)<10 or abs(x-1120)<12:continue
        put('Tree_Ginkgo' if i%3 else 'Tree_Maple_A',x,y,scale=r.uniform(.95,1.3))
    for x,y in [(705,150),(755,150),(705,178),(755,178),(998,250),(1064,250),(995,319),(1080,320),(795,-95),(890,20),(605,275),(765,285)]:
        put('HD_Bench',x,y);put('HD_Planter',x+3,y)
    for x in range(640,805,12):
        put('HD_Lamp',x,255)
    # Green interior courtyards and the northern transition soften the street grid.
    for x in range(385,1380,24):
        for y in range(-95,470,24):
            if min(abs(y-c) for c in ROAD_Y)<30 or min(abs(x-c) for c in ROAD_X)<20:continue
            if 660<x<805 and 135<y<215:continue
            if 565<x<835 and 255<y<340:continue
            if pond(x,y) or canal(x,y):continue
            if any(abs(x-b['position'][0])<15 and abs(y-b['position'][1])<12 for b in buildings):continue
            if r.random()<.55:put('Tree_Ginkgo' if r.random()<.6 else 'Tree_Maple_A',x,y,scale=r.uniform(.9,1.5))
    # Organic forest groups grow gradually out of the city into the foothills.
    # Batch heightfield evaluation keeps the denser forest cheap to regenerate.
    forest_rng=np.random.default_rng(743)
    forest_xy=forest_rng.uniform([-680,370],[2380,2940],size=(155000,2))
    forest_z=north_height(forest_xy[:,0],forest_xy[:,1])
    forest_distance=trail_distance(forest_xy[:,0],forest_xy[:,1])
    for (x,y),sample_z,distance in zip(forest_xy,forest_z,forest_distance):
        if y<500 and not (315<x<2180):continue
        if x<1420 and y<500:
            if min(abs(x-c) for c in ROAD_X)<10:continue
            if any(abs(x-b['position'][0])<b['width']/2+10 and abs(y-b['position'][1])<b['depth']/2+10 for b in buildings):continue
        z=float(sample_z)
        if z<2 or z>210+30*math.sin(x*.008) or distance<7:continue
        density=.82+.16*math.sin(x*.009+math.sin(y*.007)*2)*math.sin(y*.012)
        density*=float(mountains.smooth((y-380)/220)) if y<590 else 1
        # Drifts and clearings: a slow second pattern thins whole glades instead of every tree.
        clump=math.sin(x*.021+math.sin(y*.017)*2.1)*math.cos(y*.019-x*.006)
        density*=.25+.85*float(mountains.smooth((clump+.55)/.5))
        if r.random()>density:continue
        patch=math.sin(x*.009+math.sin(y*.006)*1.8)+.7*math.cos(y*.014-x*.003)
        kind=('Pine' if patch<-.5 else 'Rust' if patch<.45 else 'Gold')
        if r.random()<.35:kind=r.choice(['Pine','Rust','Gold'])
        name='HD_NorthTree'+kind
        if (y<620 and r.random()<.4) or distance<22:
            name=r.choice(['Tree_Ginkgo','Tree_Maple_A','Tree_Maple_A'])
        put(name,x,y,z-.3,yaw=r.uniform(0,360),scale=r.uniform(.70,1.15))
    # Distant overlapping crowns add geometry without a readable silhouette.
    # Thin them gradually, retaining the detailed city/trail belt and its layout.
    thin_rng=np.random.default_rng(744)
    for name in ('HD_NorthTreeGold','HD_NorthTreeRust','HD_NorthTreePine'):
        points=np.asarray(inst.get(name,[]),float)
        if not len(points):continue
        distance=trail_distance(points[:,0],points[:,1])
        far=mountains.smooth((distance-80)/120)*mountains.smooth((points[:,1]-650)/250)
        keep=thin_rng.random(len(points))>=.40*far
        points[:,4]*=1+.08*far
        inst[name]=points[keep].tolist()
    # Small rooted plants and stones dress the trail, leaving its riding corridor open.
    for index,(x,y,z) in enumerate(mountains.trail_points(north_height)):
        if y<460 or index%2:continue
        for side in (-1,1):
            px=x+side*r.uniform(3.2,9.5);py=y+r.uniform(-2.5,2.5)
            if float(mountains.trail_distance(px,py))<2.8:continue
            pz=float(north_height(px,py))
            name=r.choices(['Grass_A','Grass_B','Bush_Ochre_A','Rock_B'],[.42,.40,.13,.05])[0]
            put(name,px,py,pz-.08,yaw=r.uniform(0,360),scale=r.uniform(.6,1.0))
    put('HD_NorthMountains',0,0,0)
    put('HD_NorthGate',0,0,0)
    put('HD_NorthTrail',0,0,0)
    # The Mega Park trail: its own ground north of the square, a forest closing over it, undergrowth along it.
    park_trail.forest(inst,north_height)
    put('HD_NorthApproach',0,0,0)
    put('HD_NorthParkTrail',0,0,0)
    # Small groups let the existing proximity gate sleep each distant district independently.
    for group,(x,y) in enumerate([(680,140),(760,140),(580,-98),(710,-99),(870,-65),(1020,242),(1190,230),(690,276),(490,15),(1040,15)]):
        if 650<x<805 and 120<y<215:continue
        specs=[]
        for i in range(3):
            px=x+i*2.3;py=y+5
            specs.append({'position':[px,py,float(height(px,py))+.06],'yaw':30+i*60,'scale':.94+i*.04,'colour':[.10+.08*(group%3),.16,.11+.1*(i%2)],'action':'Idle' if i<2 else 'Walk','destination':[px+9,py,float(height(px+9,py))+.06]})
        residents.append({'residents':specs})
    for x,y,yaw,colour,action in [(681,140,30,[.12,.20,.28],'Idle'),(686,141,15,[.20,.23,.12],'Idle'),(772,164,-70,[.34,.13,.18],'Interact'),(757,182,0,[.17,.25,.29],'Walk')]:
        residents.append({'residents':[{'position':[x,y,float(height(x,y))+.10],'yaw':yaw,'scale':1.0,
            'colour':colour,'action':action,'destination':[x+5,y,float(height(x+5,y))+.10]}]})
    # Remove obsolete street furniture and trees inside the pedestrian square.
    for name,items in inst.items():
        if name.startswith('Tree') or name in ['HD_Lamp','HD_Planter','HD_Bench']:
            inst[name]=[p for p in items if not (660<p[0]<802 and 122<p[1]<218)]
    put('HD_PlazaFloor',0,0,0)
    put('HD_PlazaFountain',698,154)
    put('HD_PlazaWater',698,154)
    from hidamari.public_spaces import PLAZA_GARDENS, PLAZA_STALLS
    for x,y,w,d,orange in PLAZA_GARDENS:
        soil=max(float(height(x+sx*w/2,y+sy*d/2)) for sx in (-1,1) for sy in (-1,1))+.79
        put('HD_PlazaTreeOrange' if orange else 'HD_PlazaTreeGold',x,y,soil-.24,scale=1.65)
    for x,y,var in PLAZA_STALLS:
        for px,py,action,yaw in [(x,y+.3,'Idle',0),(x-1,y-3.1,'Idle',180)]:
            residents.append({'residents':[{'position':[px,py,float(height(px,py))+.15], 'yaw':yaw,'scale':1.,'colour':[.16+.05*var,.23,.12], 'action':action,'destination':[px,py,float(height(px,py))+.15]}]})
    for key,items in inst.items():
        if key.startswith('Tree'):inst[key]=[p for p in items if not (1077<p[0]<1092 and 281<p[1]<300)]
    put('Tree_Maple_A',1050.6,299.7,30.0,scale=1.05)
    from hidamari.public_spaces import HARBOR_STALLS, TEMPLES, STATION_GARDENS
    for x,y,var in HARBOR_STALLS:
        for px,py,yaw,action in [(x,y-.3,180,'Idle'),(x-1,y+2.8,0,'Idle')]:
            pz=float(height(px,py))+.05
            residents.append({'residents':[{'position':[px,py,pz],'yaw':yaw,'scale':1.,'colour':[.10,.20,.28+.03*var],'action':action,'destination':[px,py,pz]}]})
    for x,y,yaw in TEMPLES:
        a=math.radians(yaw)
        for side in [-1,1]:
            setback=28 if side<0 else 25
            tx=x+side*11*math.cos(a)+setback*math.sin(a);ty=y+side*11*math.sin(a)-setback*math.cos(a)
            put('Tree_Maple_A',tx,ty,float(height(tx,ty))-.05,scale=1.15)
    for x,y,w,d,orange in STATION_GARDENS:
        soil=max(float(height(x+sx*w/2,y+sy*d/2)) for sx in (-1,1) for sy in (-1,1))+.79
        put('HD_PlazaTreeOrange' if orange else 'HD_PlazaTreeGold',x,y,soil-.12,scale=.85)

    for name in ['HD_Terrain','HD_Streets','HD_Wires','HD_LaneEdges','HD_Precinct','HD_StationYard','HD_ParkGrounds','HD_Arrival','HD_Harbor','HD_Park','HD_Square','HD_Sea','HD_InlandWater','HD_CivicGardens']:
        put(name,0,0,0)
    end=max(world['road'],key=lambda p:p[0]);arrival=[end,[335,85,float(height(335,85))],[390,140,float(height(390,140))],[650,140,20]]
    roads=[[[float(x),float(y),float(height(x,y))] for x in np.arange(400,1251,2)] for y in ROAD_Y]
    roads += [[[float(x),float(y),float(height(x,y))] for y in np.arange(-90,351,2) if not (x==730 and y>162)] for x in ROAD_X]
    road_widths=[list(road_width(y=y)) for y in ROAD_Y]+[list(road_width(x=x)) for x in ROAD_X]
    # Resample approach straight segments for exact terrain-conforming strip construction.
    path=[]
    for a,b in zip(arrival,arrival[1:]):
        for t in np.linspace(0,1,max(2,math.ceil(math.dist(a[:2],b[:2])/1.5)),endpoint=False):
            x=a[0]*(1-t)+b[0]*t;y=a[1]*(1-t)+b[1]*t
            z=float(height(x,y)) if x>=300 else a[2]
            path.append([x,y,z])
    roads.append(path)
    # Reviewed storefront conflicts: put these freestanding props in the
    # neighbouring 27 m lot seams, clear of modeled displays and upper awnings.
    # Keep their street-side Y position so they do not encroach on riding lanes.
    street_prop_moves={
        'HD_Planter':{(1202,131):1197.5,(824,326):820.5,
                      (446,131):441.5,(878,131):873.5,(500,326):495.5,
                      (984.667,131):980.167},
        'HD_Lamp':{(840,342.8):846.5,(504,342.8):495.5,(546,342.8):549.5,
                   (462,342.8):468.5},
    }
    for name,moves in street_prop_moves.items():
        for item in inst.get(name,[]):
            new_x=moves.get((item[0],item[1]))
            if new_x is not None:
                item[0]=new_x
                item[2]=round(float(height(new_x,item[1])),3)
    # Replace adjacent legacy furniture in the newly planted street pockets.
    from hidamari.public_spaces import STREET_GARDENS
    for name in ['HD_Lamp','HD_Bench','HD_Planter']:
        inst[name]=[p for p in inst.get(name,[]) if not any(abs(p[0]-x)<5.5 and abs(p[1]-y)<1.8 for x,y,_ in STREET_GARDENS)]
    temple_precinct.place(put,inst,height,buildings)
    # The Tripo street props (street_props.py), before the trees make way for everything placed.
    from hidamari import street_props
    print('HIDAMARI STREET PROPS',street_props.place(put,inst,buildings,shop_sites()),flush=True)
    # Utility poles along every street, after everything else on the sidewalks; build.py strings their wires.
    from hidamari import city_poles
    poles=city_poles.place(put,inst,ROAD_X,ROAD_Y,road_width,height)
    print('HIDAMARI POLES',sum(len(row) for _,row in poles),flush=True)
    # Check the complete generated scatter, including street trees. Reserve
    # crown/awning clearance against each rotated shop, not only trunk centres.
    for name,placements in inst.items():
        if not (name.startswith(('Tree','HD_NorthTree')) or name in ('HD_ArcadeTree','HD_PlazaTreeGold','HD_PlazaTreeOrange')):continue
        kept=[]
        for item in placements:
            x,y,_,_,scale=item
            margin=(5.5 if name.startswith(('Tree','HD_NorthTree')) else 1.4)*scale+.7
            blocked=False
            for b in buildings:
                a=math.radians(b['yaw']);dx=x-b['position'][0];dy=y-b['position'][1]
                lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
                if abs(lx)<b['width']/2+margin and abs(ly)<b['depth']/2+margin:
                    blocked=True;break
            if not blocked:kept.append(item)
        inst[name]=kept
    # The houses' front gardens, after the clearance: their maples stand inside the plots on purpose.
    house_gardens.place(put,house_sites())
    from hidamari.forest_backdrop import append as append_forest_backdrop,ground as backdrop_ground
    forest_backdrop=append_forest_backdrop(inst,buildings,height,backdrop_grid,terrain_axes,north_height,ROAD_X,ROAD_Y)
    # Round the Mega Park the forest is the detailed autumn kind, as the skater gets close to it there, closed beyond.
    from megapark import forest as megapark_forest
    megapark_forest.grow(inst,lambda x,y:backdrop_ground(np.asarray(x,float),np.asarray(y,float),height,backdrop_grid,terrain_axes,north_height),trail_distance)
    from zeppelin.layout import clear as clear_air_station,PARK_WALK,PARK_BRIDGE
    clear_air_station(inst,1)
    clear_air_station(inst,2,path=[*PARK_WALK,PARK_BRIDGE[1]])
    # The Mega Park's own ground, rock and ramps replace the forest on its footprint; only the undergrowth by the seam
    # comes closer than 4 m (megapark/forest.py).
    from megapark import placement as megapark
    for name,placements in list(inst.items()):
        if not placements:continue
        a=np.asarray(placements,float)
        inst[name]=a[~megapark.contains(a[:,0],a[:,1],margin=4.)|megapark_forest.seam_undergrowth(name,a[:,0],a[:,1])].tolist()
    # By the air station the gate's ground has its own grass, verges, bushes and rocks (megapark/gate.py).
    from megapark import gate
    gate.dress(inst,north_base_height)
    park_grounds.place(put,inst,height)
    arrival_road.place(put,inst,height)
    station_yard.place(put,inst,height,buildings)
    inst['ZP_City']=[[0,0,0,0,1]];inst['ZP_MegaPark']=[[0,0,0,0,1]]
    return {'forest_backdrop':forest_backdrop,'near_trees':[megapark_forest.near_box(),*park_trail.near_boxes()],'name':'Hidamari','terrain_pads':list(terrain_pads()),'north_bounds':list(mountains.BOUNDS),'north_trail':mountains.trail_points(north_height),'park_trail':park_trail.bed().tolist(),'bounds':[300,-260,1320,430],'instances':inst,'buildings':buildings,'resident_groups':residents,'roads':roads,'road_widths':road_widths,'poles':poles,'arrival':path,'plaza_lights':[[x,y,float(height(x,y))+2.6] for x,y in [(669,150),(669,171),(790,157),(790,185),(730,167)]],'plaza_steps':[[730.,float(y),float(height(730,y))] for y in np.arange(163.5,169,.25)],'plaza_route':[[float(x),150.,float(height(x,150))] for x in range(712,786)],'arcade_lights':[[x,y,float(height(x,y))+2.5] for x in [607.5,614.5,628.5,656.5,684.5] for y in [67.2,82.8]],'arcade_route':[[float(x),75.,float(height(x,75))] for x in range(599,726)],'park_route':[[float(x),284.,30.925+1.5*math.sin(math.pi*(x-984)/92) if x<=1076 else float(height(x,284))] for x in range(984,1093)],'harbor_route':[[float(x),-116.,float(height(x,-116))] for x in range(570,701)],'harbor_pier_route':[[600.,float(y),2.55] for y in range(-126,-170,-1)],'review_route':path+[point for point in roads[2] if point[0]>=650],'districts':json.loads((ROOT/'hidamari/location.json').read_text())['districts'],'water_probes':[[1030,294,28.8],[848,-40,float(height(848,-40))-1.8],[500,-190,0]],'shots':[]}

# Broad scenery transition around the new city. Both far terrain and its trees
# use this same grid, so lowering a hill cannot leave its tree line floating.
BACKDROP=None

def backdrop_grid():
    global BACKDROP
    if BACKDROP is None:
        original=np.load(yori.OUT/'farhills.npy');axis=np.linspace(-3200,3200,original.shape[0]);x,y=np.meshgrid(axis,axis)
        smooth=lambda q:(lambda t:t*t*(3-2*t))(np.clip(q,0,1))
        weight=smooth((x-270)/90)*smooth((2200-x)/800)*smooth((y+450)/130)*smooth((1600-y)/1000)
        target=_base_height(x,np.minimum(y,450))+np.maximum(y-450,0)*.035-6
        BACKDROP=original*(1-weight)+target*weight
    return BACKDROP

def backdrop_height(x,y):
    h=backdrop_grid();n=h.shape[0]
    fx=np.clip((np.asarray(x)+3200)/6400*(n-1),0,n-1.001);fy=np.clip((np.asarray(y)+3200)/6400*(n-1),0,n-1.001)
    i=fx.astype(int);j=fy.astype(int);u=fx-i;v=fy-j
    return (h[j,i]*(1-u)+h[j,i+1]*u)*(1-v)+(h[j+1,i]*(1-u)+h[j+1,i+1]*u)*v

def north_base_height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    base=backdrop_height(x,y)
    city_edge=mountains.smooth((x-280)/60)*mountains.smooth((1440-x)/60)
    return base+(height(x,500)-backdrop_height(x,500))*city_edge*mountains.smooth((800-y)/300)

def north_height(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    base=backdrop_height(x,y)
    z=mountains.height(x,y,north_base_height)
    # Existing city terrain extends through y=500.
    city=(x>=300)&(x<=1420)&(y<=500)&(y>=-300)
    z=np.where(city,height(x,y),np.where(mountains.contains(x,y),z,base))
    approach=park_trail.in_approach(x,y)
    if approach.any():z[approach]=park_trail.approach_height(x[approach],y[approach])
    # Where the Mega Park meets its air station the ground is the gate's own finer patch (megapark/gate.py).
    from megapark import gate
    on=gate.inside(x,y)
    if on.any():z[on]=gate.height(x[on],y[on],north_base_height)
    return z

def trail_distance(x,y):
    """Metres to the nearer of the north trail and the Mega Park trail."""
    return np.minimum(mountains.trail_distance(x,y),park_trail.distance(x,y))

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True);w=generate();(OUT/'city.json').write_text(json.dumps(w,indent=2)+'\n');print(len(w['buildings']),'city buildings')
