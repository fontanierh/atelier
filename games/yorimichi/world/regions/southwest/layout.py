"""Integrate the south-west detour into the seeded world: a fishing village on the slope where the coastal road
begins, a shore lane to the cove with the coconut stand, and the island offshore with its trees, torii and the
summit temple. Coordinates are Blender metres (x east, y north). Runs from gen_world after the hamlet and mega."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import math, sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from village.layout import nearest, sample, upper_surface, smooth, spline
from southwest import island as ISL

TERRACE=(-262.0,-124.0);TERRACE_Z=6.6
BUILDINGS=[  # asset, centre, yaw (front is -Y), footprint w,d
 ('SW_FisherHouseA',(-271.0,-119.0),100,5.2,4.2),
 ('SW_FisherHouseB',(-254.5,-124.0),75,4.6,3.8),
 ('SW_BoatShed',(-236.5,-146.5),10,4.6,3.4),
]
PROPS=[  # asset, position (z from terrain unless given), yaw, scale
 ('SW_DryingRack',(-262.0,-131.0),10,1.0),('SW_Boat',(-259.0,-157.0,0.15),35,1.0),('SW_Dock',(-231.0,-153.5),0,1.0),
 ('SW_CoconutStand',(-221.0,-169.5),170,1.0),('SW_StoneStairs',(-266.5,-111.0),0,1.0),
 ('SW_StoneWall',(-272.0,-132.5),0,1.0),('SW_StoneWall',(-266.0,-133.0),3,1.0),('SW_StoneWall',(-247.0,-134.5),12,1.0),   # terrace edge above the shore slope, clear of the lane (x -262..-254 here)
 ('SW_Boat',(-226.5,-158.5,0.15),80,0.9),   # second boat by the dock
]
ISLAND=dict(origin=(-150.0,-480.0,0.0),yaw=15.0)
EDIT_BOUNDS=(-300,-200,-190,-90)

def lane_points(world):
    road=np.array(world['road']);k=int(np.argmin(np.abs(road[:,0]+262)));j=road[k]
    pts=[(j[0],j[1]),(-262.5,-104),(-262.5,-112),(-262,-124),(-254,-137),(-246,-150),(-238,-158),(-229,-165),(-222,-168.5)]
    xy,s=spline(pts,.5);return xy,s,k

def integrate(world,h):
    assert 'southwest' not in world,'Apply the south-west detour to a freshly generated world'
    before=h.copy();n=len(h);axis=np.linspace(-world['size']/2,world['size']/2,n);x,y=np.meshgrid(axis,axis)
    road=np.array(world['road']);road_d,_=nearest(x,y,road);protect=smooth((road_d-2.6)/1.0)
    # 1. village terrace: a gentle plane sloping toward the sea, blended into the hillside
    plane=TERRACE_Z+.04*(y-TERRACE[1])
    radius=np.sqrt(((x-TERRACE[0])/26)**2+((y-TERRACE[1])/16)**2);terrace=smooth((1.3-radius)/.3)*protect
    h[:]=h*(1-terrace)+plane*terrace
    buildings=[]
    for name,(bx,by),yaw,w,d in BUILDINGS:
        a=math.radians(yaw);dx=x-bx;dy=y-by;lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
        edge=np.maximum(np.abs(lx)-(w/2+.8),np.abs(ly)-(d/2+.8));blend=smooth((3.0-edge)/3.0)*protect
        bz=float(sample(h,np.array([bx]),np.array([by]))[0]) if name=='SW_BoatShed' else float(TERRACE_Z+.04*(by-TERRACE[1]))
        bz=max(bz,1.4) if name=='SW_BoatShed' else bz
        h[:]=h*(1-blend)+bz*blend;buildings.append(dict(asset=name,position=[bx,by,round(bz,2)],yaw=yaw,width=w,depth=d))
    # 2. shore lane from the road, through the terrace, down to the cove
    xy,s,k=lane_points(world)
    # open the guardrail where the lane leaves the road: split any rail run around the junction
    jx,jy=road[k][0],road[k][1];runs=[]
    for run in world['rail_runs']:
        pts=[p for p in run];cur=[]
        for p in pts:
            if math.hypot(p[0]-jx,p[1]-jy)<4.5:
                if len(cur)>1:runs.append(cur)
                cur=[]
            else:cur.append(p)
        if len(cur)>1:runs.append(cur)
    world['rail_runs']=runs
    lz=sample(h,xy[:,0],xy[:,1]);lz=np.minimum.accumulate(np.maximum(lz,0.6)[::-1])[::-1] if False else lz
    # monotone descent from the road: smooth and force non-increasing after the terrace
    kk=11;lz=np.convolve(np.pad(lz,(kk//2,kk//2),mode='edge'),np.ones(kk)/kk,mode='valid');lz[0]=road[k][2]
    lz=np.minimum.accumulate(lz);lz=np.maximum(lz,0.9)
    lane=np.column_stack([xy,lz]);d,pz=nearest(x,y,lane);cut=smooth((5.0-d)/3.0)*protect
    h[:]=h*(1-cut)+(pz-.06)*cut
    # Lane carving used to undercut the houses after their pads were graded;
    # the west porch of House B was also outside its symmetric wall footprint.
    # Grade the complete occupied apron last, including side pots and timber.
    for b in buildings:
        bx,by,bz=b['position'];a=math.radians(b['yaw'])
        lx=(x-bx)*math.cos(a)+(y-by)*math.sin(a)
        ly=-(x-bx)*math.sin(a)+(y-by)*math.cos(a)
        left=b['width']/2+(2.1 if b['asset']=='SW_FisherHouseB' else 1.2)
        right=b['width']/2+1.2;front=b['depth']/2+(2.6 if b['asset']=='SW_BoatShed' else 1.6);back=b['depth']/2+1.1
        edge=np.maximum.reduce([-lx-left,lx-right,-ly-front,ly-back])
        blend=smooth((3.6-edge)/2.0)*protect
        h[:]=h*(1-blend)+bz*blend
        b['support_bounds']=[-left,right,-front,back]
    # The coconut stand includes a stool and easel off to its right. Support
    # that complete vignette, not just the four stall posts, on the shore bank.
    sx,sy=-221.,-169.5;sa=math.radians(170.)
    sz=float(sample(h,np.array([sx]),np.array([sy]))[0])
    slx=(x-sx)*math.cos(sa)+(y-sy)*math.sin(sa)
    sly=-(x-sx)*math.sin(sa)+(y-sy)*math.cos(sa)
    edge=np.maximum.reduce([-slx-1.7,slx-2.65,-sly-2.3,sly-1.2])
    blend=smooth((3.4-edge)/1.8)*protect
    h[:]=h*(1-blend)+sz*blend
    h[:]=np.where(road_d<2.6,before,h)
    lane[:,2]=upper_surface(h,xy[:,0],xy[:,1])+.06
    # 3. vegetation: clear the terrace, lane and building pads; seat the rest on the new ground
    removed={};adjusted=0;xmin,xmax,ymin,ymax=EDIT_BOUNDS
    for name,placements in world['instances'].items():
        if not placements:continue
        positions=np.array(placements,dtype=float);px,py=positions[:,0],positions[:,1]
        local=(px>xmin)&(px<xmax)&(py>ymin)&(py<ymax);indexes=np.flatnonzero(local)
        if not len(indexes):continue
        lx,ly=px[local],py[local];remove=np.zeros(len(indexes),dtype=bool);tree=name.startswith('Tree')
        vegetation=name.startswith(('Tree','Bush','Grass','Rock')) or name=='Litter'
        if vegetation:
            dist,_=nearest(lx,ly,lane);remove|=dist<(5.5 if tree else 2.0)
            remove|=((lx-TERRACE[0])/24)**2+((ly-TERRACE[1])/14)**2<1
            for b in buildings:remove|=np.hypot(lx-b['position'][0],ly-b['position'][1])<max(b['width'],b['depth'])/2+(5 if tree else 1.5)
            for asset,pos,yaw,sc in PROPS:remove|=np.hypot(lx-pos[0],ly-pos[1])<(4.5 if tree else 2.2)
        delta=sample(h,lx,ly)-sample(before,lx,ly)
        if tree:
            root=np.minimum.reduce([upper_surface(h,lx+dx,ly+dy) for dx,dy in [(-.42,0),(.42,0),(0,-.42),(0,.42),(0,0)]])-.14
            delta=root-positions[local,2]
        keep=np.ones(len(placements),dtype=bool);keep[indexes[remove]]=False
        for kk2,i in enumerate(indexes):
            if not remove[kk2] and abs(delta[kk2])>.001:
                placements[i]=list(placements[i]);placements[i][2]=round(placements[i][2]+float(delta[kk2]),2);adjusted+=1
        if (~keep).any():
            removed[name]=int((~keep).sum());world['instances'][name]=[p for p,kp in zip(placements,keep) if kp]
    inst=world['instances']
    def put(asset,x_,y_,z_,yaw,scale=1.0):inst.setdefault(asset,[]).append([round(float(x_),2),round(float(y_),2),round(float(z_),2),round(float(yaw),1),round(float(scale),3)])
    for b in buildings:put(b['asset'],*b['position'],b['yaw'])
    for asset,pos,yaw,sc in PROPS:
        z=pos[2] if len(pos)>2 else float(sample(h,np.array([pos[0]]),np.array([pos[1]]))[0])
        if asset=='SW_Dock':z=0.0
        put(asset,pos[0],pos[1],z,yaw,sc)
    # 4. the island: mesh instance, trees seated on its heightfield, torii and lanterns along the ramp, the temple
    ox,oy,oz=ISLAND['origin'];ya=math.radians(ISLAND['yaw']);ca,sa=math.cos(ya),math.sin(ya)
    def to_world(lx,ly,lz):return ox+lx*ca-ly*sa,oy+lx*sa+ly*ca,oz+lz
    put('SW_Island',ox,oy,oz,ISLAND['yaw'])
    # trees, understory and boulders come from the island's own scatter (grass band only, rock skirt gets boulders)
    px,py,pt=ISL._path_arrays();sc=ISL.scatter(1207);count=0
    for group in ('trees','understory','boulders'):
        for asset,lx,ly,lz,yaw,scale in sc[group]:
            wx,wy,wz=to_world(lx,ly,lz-(.3 if group=='trees' else 0.0));put(asset,wx,wy,wz,yaw+ISLAND['yaw'],scale);count+=group=='trees'
    # torii gates and lantern pairs along the switchback stair
    for lx,ly,lz,yaw in ISL.torii_points(5):
        # Torii posts span local Y. Face the walking direction so both feet
        # stand across the grade, not one metre apart vertically up the slope.
        wx,wy,wz=to_world(lx,ly,lz);put('Torii',wx,wy,wz,yaw+ISLAND['yaw']-90,.85)
        ang=math.radians(yaw);nx,ny=math.cos(ang),math.sin(ang)
        for sgn in (-1,1):
            lx2,ly2=lx+sgn*2.2*nx,ly+sgn*2.2*ny;z2=float(ISL.height(np.array([lx2]),np.array([ly2]))[0])
            wx2,wy2,wz2=to_world(lx2,ly2,z2);put('Lantern',wx2,wy2,wz2,yaw+ISLAND['yaw'],1.0)
    sx,sy,sz=ISL.summit_transform();wx,wy,wz=to_world(sx,sy,sz);put('SW_Temple',wx,wy,wz,180+ISLAND['yaw'])
    ramp=[]
    for i in range(0,len(px),8):
        lx_,ly_=float(px[i]),float(py[i]);z_=float(ISL.height(np.array([lx_]),np.array([ly_]))[0]);rx,ry,rz=to_world(lx_,ly_,z_);ramp.append([round(rx,2),round(ry,2),round(rz,2)])
    lx,ly=ISL.LANDING;wx,wy,wz=to_world(lx,ly,0.6)
    ex,ey,_=to_world(ISL.LANDING[0],ISL.LANDING[1]+23,0)
    world['southwest']=dict(terrace=[*TERRACE,TERRACE_Z],lane=lane.tolist(),buildings=buildings,props=[list(p[1][:2]) for p in PROPS],
        island=dict(origin=list(ISLAND['origin']),yaw=ISLAND['yaw'],landing=[round(wx,2),round(wy,2),round(wz,2)],summit=[round(v,2) for v in to_world(sx,sy,sz)],trees=count),
        beach=[-221.0,-172.0],boat_launch=[-214.0,-176.0],
        crossing=[[-104.,-258.,0.],[-242.,-284.,0.],[-179.,-327.,0.],[round(ex-45,2),round(ey+25,2),0.],[round(ex,2),round(ey,2),0.]],ramp=ramp,removed=removed,adjusted=adjusted,edit_bounds=list(EDIT_BOUNDS))
    # review shots: [x, y, z, pitch, yaw] in Blender metres like the world's own shots
    world.setdefault('shots',[]).extend([
        [-262.5,-100.5,12.6,-90.0,-10.0],      # the village from the road junction, looking down the lane
        [-236.0,-160.0,4.2,-32.0,-4.0],        # along the shore toward the stand and the island
        [-221.0,-183.0,3.0,90.0,4.0],          # from the water's edge back at the coconut stand
        [-205.0,-176.0,2.6,-80.0,-2.0],        # the island from the beach
        [-150.0,-560.0,120.0,90.0,-24.0],      # the island from the south, high
        [-160.0,-455.0,84.5,-65.0,-4.0],       # the temple terrace below the crown (ground 82.7)
    ])
    print('southwest: %d island trees, removed %s, adjusted %d'%(count,removed,adjusted))
