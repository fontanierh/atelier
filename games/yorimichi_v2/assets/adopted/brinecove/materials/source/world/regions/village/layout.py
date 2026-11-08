"""Local, deterministic addition to the seeded world. Coordinates are Blender metres.

Run from gen_world after all original scattering: unrelated RNG streams and
placements remain byte-for-byte identical outside the earthwork footprint.
"""
import math
import numpy as np

FOREST_OFFSET_Y = 70.0
ELEVATION_OFFSET = 9.0
EDIT_BOUNDS = (40, 185, -40, 190)

def village_point(x, y, z=None):
    """Convert authored hamlet coordinates to its secluded forest location."""
    return [x, y+FOREST_OFFSET_Y] if z is None else [x, y+FOREST_OFFSET_Y, z+ELEVATION_OFFSET]

BUILDINGS = [
    # name, centre, yaw (local front is -Y), width, depth
    ('Village_TeaHouse', (77.5, 7.5), 90, 8.0, 6.4),
    ('Village_CottageA', (80.0, 29.0), 45, 6.5, 5.0),
    ('Village_CottageB', (104.5, 35.0), -20, 6.0, 5.3),
    ('Village_Workshop', (118.0, -2.0), -120, 6.2, 4.8),
    ('Village_Storehouse', (122.0, 19.5), -90, 3.8, 4.5),
]

BUILDINGS = [(name, tuple(village_point(*xy)), yaw, w, d) for name,xy,yaw,w,d in BUILDINGS]

PLANTING_BEDS=[(94,4,2.0,3.0),(97,3,2.4,2.1),(104,6,2.3,2.2),
    (106.7,17.8,2.0,3.1),(98,18.6,2.6,2.0),(98,37,3.0,2.2),
    (75,-1,1.4,2.5),(72,15,1.5,3),(78,36,2,1.1),
    (110,38.8,1.6,2.0),(126,17,1.7,3.0),(124,-5,1.2,2.6),
    (96,8,2,1.5),(104,12,1.0,2.2),(95,20,1.9,1.6),
    (81,2,1.0,1.1),(84,14,1,1.2),(119,12,1.4,2.5)]

PLANTING_BEDS=[(*village_point(x,y),rx,ry) for x,y,rx,ry in PLANTING_BEDS]


def smooth(x):
    x = np.clip(x, 0, 1)
    return x*x*(3-2*x)


def plane(x, y):
    return 19.8 + ELEVATION_OFFSET + .055*(np.asarray(y)-FOREST_OFFSET_Y)


def spline(points, spacing=.5):
    p = np.array([points[0], *points, points[-1]], dtype=float)
    dense = []
    for k in range(1, len(p)-2):
        a,b,c,d=p[k-1:k+3]
        for t in np.linspace(0, 1, 60, endpoint=False):
            dense.append(.5*(2*b+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
    dense=np.array([*dense,p[-1]])
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(dense,axis=0),axis=1))]
    s=np.linspace(0,lengths[-1],math.ceil(lengths[-1]/spacing)+1)
    return np.column_stack([np.interp(s,lengths,dense[:,i]) for i in range(2)]),s


def nearest(x, y, points):
    """Distances to continuous segments, avoiding sample-shaped scalloped verges."""
    x,y=np.broadcast_arrays(np.asarray(x,dtype=float),np.asarray(y,dtype=float))
    dist=np.full(x.shape,np.inf); height=np.zeros(x.shape)
    for a,b in zip(points[:-1],points[1:]):
        delta=b[:2]-a[:2]
        t=np.clip(((x-a[0])*delta[0]+(y-a[1])*delta[1])/np.dot(delta,delta),0,1)
        d=np.hypot(x-a[0]-t*delta[0],y-a[1]-t*delta[1])
        closer=d<dist
        height=np.where(closer,a[2]+t*(b[2]-a[2]),height)
        dist=np.minimum(dist,d)
    return dist,height


def sample(h,x,y,size=600):
    """Vectorised bilinear heightfield lookup, including exact boundary points."""
    n=len(h); step=size/(n-1)
    xx=np.clip((np.asarray(x)+size/2)/step,0,n-1)
    yy=np.clip((np.asarray(y)+size/2)/step,0,n-1)
    i=np.minimum(xx.astype(int),n-2);j=np.minimum(yy.astype(int),n-2)
    u=xx-i;v=yy-j
    return h[j,i]*(1-u)*(1-v)+h[j,i+1]*u*(1-v)+h[j+1,i]*(1-u)*v+h[j+1,i+1]*u*v



def upper_surface(h,x,y,size=600):
    """Upper envelope of both possible triangulations of an exported terrain quad.

    Bilinear heights can sit below a diagonal triangle on a non-planar grid
    cell. The road overlay must cover either FBX triangulation, including banks.
    """
    n=len(h);step=size/(n-1)
    xx=np.clip((np.asarray(x)+size/2)/step,0,n-1);yy=np.clip((np.asarray(y)+size/2)/step,0,n-1)
    i=np.minimum(xx.astype(int),n-2);j=np.minimum(yy.astype(int),n-2);u=xx-i;v=yy-j
    a=h[j,i];b=h[j,i+1];c=h[j+1,i+1];d=h[j+1,i]
    ac=np.where(u>=v,a*(1-u)+b*(u-v)+c*v,a*(1-v)+c*u+d*(v-u))
    bd=np.where(u+v<=1,a*(1-u-v)+b*u+d*v,b*(1-v)+c*(u+v-1)+d*(1-u))
    return np.maximum(ac,bd)


def authored_paths(world):
    road=np.array(world['road']); start=road[395]
    # Two woodland bends hide the houses and make the approach a journey.
    approach=[tuple(start[:2]),(94,-20),(98,-10),(85,4),(79,16),
              (87,30),(105,37),(111,49),(108,59)]
    inner=[(98,-8),(88,0),(87,13),(90,23),(102,28),(112,25),
           (126,38),(143,46),(159,55),(161,69),(149,82),(144,97)]
    xy,s=spline(approach+[village_point(*p) for p in inner])
    ramp_end=int(np.argmin(np.linalg.norm(xy-np.array(village_point(98,-8)),axis=1)))
    exit_index=int(np.argmin(np.linalg.norm(xy-np.array(village_point(112,25)),axis=1)))
    z=plane(xy[:,0],xy[:,1])
    # A steady gentle grade avoids an unnecessarily steep smoothstep midpoint.
    z[:ramp_end+1]=start[2]+(z[ramp_end]-start[2])*s[:ramp_end+1]/s[ramp_end]
    z[exit_index:]=z[exit_index]+.075*(s[exit_index:]-s[exit_index])
    lane=np.column_stack([xy,z])
    loop,_=spline([village_point(*p) for p in [(112,25),(114,16),(113,8),(108,2),(98,-8)]])
    loop=np.column_stack([loop,plane(loop[:,0],loop[:,1])])
    return lane,loop


def integrate(world,h):
    assert 'village' not in world, 'Apply village to a freshly generated base world'
    before=h.copy(); n=len(h); axis=np.linspace(-world['size']/2,world['size']/2,n)
    x,y=np.meshgrid(axis,axis)
    lane,loop=authored_paths(world)
    paths=[lane,loop]
    main_distance,_=nearest(x,y,np.array(world['road']))
    protect=smooth((main_distance-2.6)/1.0)
    # A softly blended terrace, with five small level foundation pads.
    radius=np.sqrt(((x-99)/34)**2+((y-FOREST_OFFSET_Y-15)/35)**2)
    terrace=smooth((1.30-radius)/.30)*protect
    h[:]=h*(1-terrace)+plane(x,y)*terrace
    buildings=[]
    for name,(bx,by),yaw,width,depth in BUILDINGS:
        a=math.radians(yaw);dx=x-bx;dy=y-by
        lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
        edge=np.maximum(np.abs(lx)-(width/2+.8),np.abs(ly)-(depth/2+.8))
        blend=smooth((3.0-edge)/3.0)*protect
        bz=float(plane(bx,by))
        h[:]=h*(1-blend)+bz*blend
        buildings.append(dict(asset=name,position=[bx,by,bz],yaw=yaw,width=width,depth=depth))
    d=np.full(x.shape,np.inf);z=np.zeros(x.shape)
    for path in paths:
        nd,nz=nearest(x,y,path)
        z=np.where(nd<d,nz,z);d=np.minimum(d,nd)
    cut=smooth((12-d)/8)*protect
    h[:]=h*(1-cut)+(z-.08)*cut
    # Grade household aprons last: lane carving must not undercut furniture
    # authored at the house datum. Blend the outer edge into the dirt trail.
    for b in buildings:
        bx,by,bz=b['position'];a=math.radians(b['yaw'])
        dx=x-bx;dy=y-by
        lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
        edge=np.maximum(np.abs(lx)-(b['width']/2+1.6),
                        np.maximum(ly-(b['depth']/2+1.1),-ly-(b['depth']/2+3.3)))
        blend=smooth((3.0-edge)/3.0)*protect
        h[:]=h*(1-blend)+bz*blend
    # At the junction use the original carriageway's elevation exactly.
    h[:]=np.where(main_distance<2.6,before,h)

    removed={}; adjusted=0
    for name,placements in world['instances'].items():
        if not placements:continue
        positions=np.array(placements,dtype=float)
        px,py=positions[:,0],positions[:,1]
        xmin,xmax,ymin,ymax=EDIT_BOUNDS
        local=(px>xmin)&(px<xmax)&(py>ymin)&(py<ymax)
        indexes=np.flatnonzero(local)
        if not len(indexes):continue
        lx,ly=px[local],py[local]
        remove=np.zeros(len(indexes),dtype=bool)
        tree=name.startswith('Tree')
        vegetation=name.startswith(('Tree','Bush','Grass','Rock')) or name=='Litter'
        if vegetation:
            distance=np.minimum.reduce([nearest(lx,ly,p)[0] for p in paths])
            remove|=distance<(6.8 if tree else 1.9)
            remove|=((lx-99)/31)**2+((ly-FOREST_OFFSET_Y-15)/33)**2<1
            for b in buildings:
                remove|=np.hypot(lx-b['position'][0],ly-b['position'][1])<max(b['width'],b['depth'])/2+(6 if tree else 1.5)
        delta=sample(h,lx,ly)-sample(before,lx,ly)
        if tree:
            # Seat the complete trunk footprint into the slope, not just its
            # centre's bilinear height. This also corrects pre-existing gaps.
            root=np.minimum.reduce([upper_surface(h,lx+dx,ly+dy) for dx,dy in [(-.42,0),(.42,0),(0,-.42),(0,.42),(0,0)]])-.14
            delta=root-positions[local,2]
        keep=np.ones(len(placements),dtype=bool)
        keep[indexes[remove]]=False
        for k,i in enumerate(indexes):
            if not remove[k] and abs(delta[k])>.001:
                original_z=placements[i][2]
                placements[i]=list(placements[i]);placements[i][2]=round(original_z+float(delta[k]),2);adjusted+=1
                if name.startswith('Pole'):
                    for anchors in world['anchors']:
                        centre=np.mean(np.array(anchors[:3])[:,:2],axis=0)
                        if np.linalg.norm(centre-np.array(placements[i][:2]))<.02:
                            for anchor in anchors:anchor[2]=round(anchor[2]+placements[i][2]-original_z,3)
        world['instances'][name]=[p for i,p in enumerate(placements) if keep[i]]
        if remove.any():removed[name]=int(remove.sum())
    def put(name,px,py,yaw=0,scale=1,z=None):
        # Woodland-bank scatter must never spill onto the existing main road.
        # Reserve canopy/blade width as well as the instance centre.
        if name.startswith(('Bush','Grass')):
            clearance=2.0 if name.startswith('Bush') else .8
            if float(nearest(px,py,np.array(world['road']))[0])<world['road_width']/2+clearance:return
        if name.startswith(('Tree','Bush','Grass')):
            margin=4.5*scale+.8 if name.startswith('Tree') else (1.5*scale+.35 if name.startswith('Bush') else .5)
            for b in buildings:
                a=math.radians(b['yaw']);dx=px-b['position'][0];dy=py-b['position'][1]
                lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
                if abs(lx)<b['width']/2+margin and -b['depth']/2-2.7-margin<ly<b['depth']/2+margin:return
        if z is None:
            z=float(upper_surface(h,px,py))
            if name.startswith('Tree'):
                z=min(float(upper_surface(h,px+dx,py+dy)) for dx,dy in [(-.42,0),(.42,0),(0,-.42),(0,.42)])-.14
        world['instances'].setdefault(name,[]).append([px,py,z,yaw,scale])
    for b in buildings:put(b['asset'],*b['position'][:2],b['yaw'],z=b['position'][2])
    put('Village_Ground',0,0,z=0)
    put('Village_Edges',0,0,z=0)
    put('Village_Details',0,0,z=0)
    put('Village_Planting',0,0,z=0)
    gate_index=int(np.argmin(np.linalg.norm(lane[:,:2]-village_point(126,38),axis=1)));gate=lane[gate_index];direction=lane[gate_index+1,:2]-lane[gate_index-1,:2]
    put('Village_Threshold',*gate[:2],math.degrees(math.atan2(direction[1],direction[0]))-90,z=float(gate[2]))
    put('Village_Garden',*village_point(99,15),z=float(plane(*village_point(99,15))))
    sign_direction=lane[32,:2]-lane[16,:2]
    put('Village_Sign',90.1,-22.4,math.degrees(math.atan2(sign_direction[1],sign_direction[0])),scale=.78)
    put('Village_Sign',*village_point(118,36),-125,scale=.78)
    def local_put(name,px,py,*args,**kwargs):
        put(name,*village_point(px,py),*args,**kwargs)
    # Hand-placed planting on the cleared village edge, using the existing foliage palette.
    r=np.random.default_rng(913)
    for bx,by in [(68,5),(70,25),(77,45),(93,49),(115,46),(133,28),(127,3),(118,-11)]:
        local_put('Tree_Maple_A' if by<30 else 'Tree_Pine_A',bx,by,float(r.uniform(0,360)),float(r.uniform(.85,1.05)))
    local_put('Tree_Maple_A',100,16,25,.67)
    # Existing leaf foliage wraps the side trellis, matching the forest material.
    for k in range(4):
        local_put('Bush_Green_B',79.3-k*.35,3.19,k*75,.25,z=float(plane(*village_point(77.5,7.5)))+.30+k*.55)
    for bx,by,sc in [(96,38,.55),(72,21,.6),(125,29,.58),(94,3,.43)]:
        local_put('Tree_Maple_B',bx,by,float(r.uniform(0,360)),sc)
    for bx,by in [(94,5),(97,3),(106,19),(98,36),(123,30),(124,-5),(73,20)]:
        for k in range(4):
            px=bx+float(r.uniform(-1.5,1.5));py=by+float(r.uniform(-1.5,1.5))
            if min(float(nearest(*village_point(px,py),p)[0]) for p in paths)>3.5:
                local_put('Bush_Green_A' if k%2 else 'Bush_Flower_A',px,py,float(r.uniform(0,360)),float(r.uniform(.35,.6)))
    for bx,by in [(73,-1),(71,14),(75,28),(90,37),(112,36),(120,21),(118,13),(110,-9),(99,21)]:
        for k in range(3):
            px=bx+float(r.uniform(-1.2,1.2));py=by+float(r.uniform(-1.2,1.2))
            if min(float(nearest(*village_point(px,py),p)[0]) for p in paths)<3.3:continue
            local_put('Bush_Flower_A' if k==0 else 'Bush_Green_A',px,py,float(r.uniform(0,360)),.60)
    for bx,by in [(69,1),(69,15),(72,23),(76,35),(83,38),(92,40),(113,42),(121,36),(130,17),(130,7),(125,-11),(97,16)]:
        for k in range(3):
            px=bx+float(r.uniform(-.7,.7));py=by+float(r.uniform(-.7,.7))
            if min(float(nearest(*village_point(px,py),p)[0]) for p in paths)<3.5:continue
            local_put('Bush_Flower_A' if k==0 else 'Bush_Green_B',px,py,float(r.uniform(0,360)),.43)
    def household_clear(px,py):
        for b in buildings:
            a=math.radians(b['yaw']);dx=px-b['position'][0];dy=py-b['position'][1]
            lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
            if abs(lx)<b['width']/2+.8 and -b['depth']/2-3.7<ly<b['depth']/2+.8:return False
        return not (95.5<px<102.2 and 10+FOREST_OFFSET_Y<py<18+FOREST_OFFSET_Y)
    for bx,by,rx,ry in PLANTING_BEDS:
        for k in range(6):
            px=bx+float(r.uniform(-.65,.65))*rx;py=by+float(r.uniform(-.65,.65))*ry
            if household_clear(px,py) and min(float(nearest(px,py,p)[0]) for p in paths)>3.25:
                put('Bush_Flower_A' if k%3==0 else 'Bush_Green_B',px,py,float(r.uniform(0,360)),float(r.uniform(.25,.43)))
    # Short grasses connect the authored flower groups without a mown-lawn edge.
    gx,gy=np.meshgrid(np.arange(69,133,1.65),np.arange(-12+FOREST_OFFSET_Y,44+FOREST_OFFSET_Y,1.65))
    gx=gx.ravel()+r.uniform(-.65,.65,gx.size);gy=gy.ravel()+r.uniform(-.65,.65,gy.size)
    gd=np.minimum.reduce([nearest(gx,gy,p)[0] for p in paths])
    for px,py,d in zip(gx,gy,gd):
        if 3.0<d<14 and household_clear(px,py) and r.random()<.7:
            put('Grass_A' if r.random()<.5 else 'Grass_B',float(px),float(py),float(r.uniform(0,360)),float(r.uniform(.55,.85)))
    # The graded forest banks previously had little understory on their new slopes.
    forest=lane
    for i in range(0,len(forest)-2,3):
        p=forest[i]
        # Keep native understory out of household aprons and the inner square.
        if p[1]>=FOREST_OFFSET_Y-12 and i<gate_index:continue
        t=forest[i+1,:2]-forest[i,:2];t/=np.linalg.norm(t);side=np.array([-t[1],t[0]])
        for sign in (-1,1):
            for k in range(3):
                px,py=p[:2]+side*sign*r.uniform(2.0 if p[1]<62 else 3.0,5.0)+t*r.uniform(-.5,.5)
                put('Grass_A' if k else 'Bush_Green_B',float(px),float(py),float(r.uniform(0,360)),float(r.uniform(.35,.6)))
    def shot(pos,target):
        pos=village_point(*pos);target=village_point(*target)
        dx,dy,dz=np.array(target)-pos
        world['shots'].append([*map(float,pos),math.degrees(math.atan2(dy,dx)),math.degrees(math.atan2(dz,math.hypot(dx,dy)))])
        return len(world['shots'])-1
    shots={
        'overview':shot([137,-35,43],[99,12,23]),
        'arrival':shot([97,-21,20],[87,13,24]),
        'square':shot([117,13,23],[77.5,10,23]),
        'forest':shot([143,43,27],[160,63,29]),
        'workshop':shot([110,13,23],[118,-2,22.1]),
        'threshold':shot([115,24,26],[126,38,24.3]),
    }
    shots['entrance']=shot([84,-101,10],[95,-85,11])
    shots['trail']=shot([82.21,7.73-FOREST_OFFSET_Y,20.98+1.7-ELEVATION_OFFSET],[80.65,21.65-FOREST_OFFSET_Y,22.36+1.0-ELEVATION_OFFSET])
    shots['roadside']=shot([77,-99,9.8],[93,-90,10.2])
    shots['birds_eye']=shot([145,-34,140],[105,8,21])
    def at_building(suffix,lx,ly):
        b=next(b for b in buildings if b['asset'].endswith(suffix));a=math.radians(b['yaw'])
        px=b['position'][0]+lx*math.cos(a)-ly*math.sin(a)
        py=b['position'][1]+lx*math.sin(a)+ly*math.cos(a)
        return [px,py,float(upper_surface(h,px,py))+.15]
    residents=[
        dict(position=at_building('Workshop',.1,-4.0),yaw=-120,scale=.97,action='Interact',colour=[.055,.10,.18]),
        dict(position=at_building('TeaHouse',-2.8,-6.0),yaw=-90,scale=.91,action='Idle',colour=[.34,.16,.045]),
        dict(position=at_building('CottageA',-1,-4.9),destination=at_building('CottageA',1.6,-4.9),
             yaw=135,scale=.93,action='Walk',colour=[.16,.075,.11]),
    ]
    world['village']={'name':'Momiji Hamlet','entrance_road_index':395,'lane_width':2.6,'edit_bounds':EDIT_BOUNDS,'offset':[0,FOREST_OFFSET_Y,ELEVATION_OFFSET],
        'paths':[p.round(4).tolist() for p in paths],
        'surface_paths':[np.column_stack([p[:,:2], upper_surface(h,p[:,0],p[:,1])+.035]).round(4).tolist() for p in paths], 'buildings':buildings,'shots':shots,
        'residents':residents,
        'arrival_index':int(np.argmin(np.linalg.norm(lane[:,:2]-village_point(87,10),axis=1))),
        'gate_index':gate_index,
        'planting_beds':PLANTING_BEDS,
        'removed_instances':removed,'adjusted_heights':adjusted}
    return world['village']
