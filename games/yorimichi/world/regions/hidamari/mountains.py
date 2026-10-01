"""Northern foothills and a distant volcanic summit, in Blender world metres.

One sampled surface drives mesh, trees, trail and map. The accessible trail rises
gradually out of the park; the large summit is a scenic landmark beyond it.
"""
import math
from functools import lru_cache
import numpy as np
from megapark import placement as megapark

BOUNDS = (-700., 500., 2400., 3000.)
STEP = 10.
TRAIL = [(1120,335),(1120,440),(1120,500),(1100,555),(1040,620),
         (1030,680),(1090,735),(1170,780),(1200,850),(1160,915),
         (1080,960),(1000,1020),(1010,1090),(1060,1130)]

def smooth(t):
    t=np.clip(t,0,1)
    return t*t*(3-2*t)

def contains(x,y):
    return (x>=BOUNDS[0])&(x<=BOUNDS[2])&(y>=BOUNDS[1])&(y<=BOUNDS[3])

def trail_distance(x,y):
    x,y=np.broadcast_arrays(x,y);d=np.full(x.shape,1e9)
    for a,b in zip(TRAIL,TRAIL[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        t=np.clip(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1)
        d=np.minimum(d,np.hypot(x-a[0]-t*dx,y-a[1]-t*dy))
    return d

def noise(x,y,scale,seed=0):
    """Continuous deterministic value noise; shared by geometry and its snow cover."""
    x=np.asarray(x)/scale;y=np.asarray(y)/scale
    ix=np.floor(x);iy=np.floor(y);u=smooth(x-ix);v=smooth(y-iy)
    def h(a,b):
        q=np.sin(a*127.1+b*311.7+seed*73.9)*43758.5453
        return (q-np.floor(q))*2-1
    return (h(ix,iy)*(1-u)+h(ix+1,iy)*u)*(1-v)+(h(ix,iy+1)*(1-u)+h(ix+1,iy+1)*u)*v

@lru_cache(maxsize=1)
def drainage():
    """Authored-seed branching snow gullies, expressed as planar tapered segments."""
    rng=np.random.default_rng(412)
    segments=[]
    for i in range(40):
        angle=i*math.tau/40+rng.uniform(-.05,.05)
        reach=rng.uniform(580,890);bend=rng.uniform(-.15,.15)
        radii=[70,160,280,reach*.58,reach*.80,reach]
        widths=[26,22,12,9,6,0]
        points=[]
        for k,r in enumerate(radii):
            a=angle+bend*r/reach+(rng.uniform(-.045,.045) if k>1 else 0)
            points.append((550+r*math.cos(a),1930+r*math.sin(a),widths[k]))
        segments.extend(zip(points,points[1:]))
        # Two narrow tributaries leave different levels, joining the main snow field.
        for k,side in [(2,-1),(3,1)]:
            start=points[k];rr=radii[k]
            end=rr+rng.uniform(130,240);a=angle+bend+side*rng.uniform(.10,.20)
            middle=(550+(rr+end)/2*math.cos(a),1930+(rr+end)/2*math.sin(a),8)
            tip=(550+end*math.cos(a+side*.035),1930+end*math.sin(a+side*.035),0)
            segments.extend([((start[0],start[1],11),middle),(middle,tip)])
    return segments

def drainage_field(x,y):
    x,y=np.broadcast_arrays(x,y)
    # Positive inside snow ribbons; the cap connects all gullies near the summit.
    snow=190+noise(x,y,95,28)*24-np.hypot(x-550,y-1930)
    cut=np.zeros_like(x,dtype=float)
    for a,b in drainage():
        dx=b[0]-a[0];dy=b[1]-a[1]
        t=np.clip(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1)
        distance=np.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
        width=a[2]*(1-t)+b[2]*t
        snow=np.maximum(snow,width-distance)
        cut=np.maximum(cut,np.exp(-(distance/(width+16))**2)*smooth(width/12))
    return snow,cut

def natural_height(x,y):
    """The foothills and volcano before the edge blend, without the Mega Park."""
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    north=np.maximum(y-500,0)
    apron=47+north*.020
    foothills=(70*np.exp(-((x-80)/400)**2-((y-930)/230)**2)
              +22*np.exp(-((x-1000)/350)**2-((y-1330)/220)**2)
              +58*np.exp(-((x-1030)/260)**2-((y-970)/160)**2)
              +65*np.exp(-((x-1450)/300)**2-((y-1800)/150)**2)
              +150*np.exp(-((x-1920)/520)**2-((y-2230)/270)**2)
              +106*np.exp(-((x-1930)/420)**2-((y-1140)/280)**2)
              -70*np.exp(-((x-520)/270)**2-((y-1050)/340)**2))
    dx,dy=x-550,y-1930;r=np.hypot(dx,dy)
    # A tangent quadratic dome rounds only the last 110 m of the summit.
    # It joins the existing flank with matching height and slope.
    summit_radius=np.where(r<110,35+r*r/220,np.maximum(r-20,0))
    cone=510*np.maximum(0,1-summit_radius/1170)**1.55
    _,cuts=drainage_field(x,y)
    relief=(-cuts*8+noise(x,y,70,2)*12+noise(x,y,180,17)*9)
    relief*=smooth((r-35)/170)*smooth((1220-r)/230)
    # Small irregular facets subdivide the broad faces without changing the skyline.
    relief+=noise(x,y,24,3)*9*smooth((r-35)/110)*smooth((1100-r)/250)
    trail_quiet=smooth((trail_distance(x,y)-15)/100)
    relief*=trail_quiet
    foothills+=noise(x,y,130,4)*15*smooth(north/240)*trail_quiet
    target=apron+foothills+np.maximum(cone+relief,0)
    return 47+(target-47)*smooth(north/180)

def raw_height(x,y,base):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    north=np.maximum(y-500,0)
    # The Mega Park sits in the western foothills; the relief around it is eased to meet its edges.
    target=megapark.terrain(x,y,natural_height(x,y),natural_height)
    edge=smooth((x-BOUNDS[0])/200)*smooth((BOUNDS[2]-x)/200)*smooth((BOUNDS[3]-y)/210)*smooth(north/180)
    return np.asarray(base)*(1-edge)+target*edge

@lru_cache(maxsize=4)
def surface_grid(base_sampler):
    xs=np.arange(BOUNDS[0],BOUNDS[2]+1,STEP);ys=np.arange(BOUNDS[1],BOUNDS[3]+1,STEP)
    x,y=np.meshgrid(xs,ys)
    return x,y,raw_height(x,y,base_sampler(x,y))

def height(x,y,base_sampler):
    """Barycentric sampling of the single cached grid exported as actual collision."""
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    ix=np.clip(np.floor((x-BOUNDS[0])/STEP).astype(int),0,int((BOUNDS[2]-BOUNDS[0])/STEP)-1)
    iy=np.clip(np.floor((y-BOUNDS[1])/STEP).astype(int),0,int((BOUNDS[3]-BOUNDS[1])/STEP)-1)
    u=np.clip((x-BOUNDS[0])/STEP-ix,0,1);v=np.clip((y-BOUNDS[1])/STEP-iy,0,1)
    z=surface_grid(base_sampler)[2]
    z00=z[iy,ix];z10=z[iy,ix+1];z01=z[iy+1,ix];z11=z[iy+1,ix+1]
    return np.where(u>=v,z00*(1-u)+z10*(u-v)+z11*v,z00*(1-v)+z11*u+z01*(v-u))

def mesh(base_sampler):
    from village.build import Mesh
    m=Mesh('HD_NorthMountains')
    xs=np.arange(BOUNDS[0],BOUNDS[2]+1,STEP);ys=np.arange(BOUNDS[1],BOUNDS[3]+1,STEP)
    x,y,z=surface_grid(base_sampler)
    rock_noise=noise(x,y,26,9)*.65+noise(x,y,85,20)*.35
    forest=smooth((z-140+noise(x,y,125,27)*28)/75)
    # Muted warm/slate rock planes sit behind the warm tree canopy.
    rock=np.stack([.145+.043*rock_noise,.137+.025*rock_noise,.185+.015*rock_noise],axis=-1)
    green=np.stack([.055+.015*noise(x,y,85,12),.11+.018*noise(x,y,90,14),np.full_like(x,.035)],axis=-1)
    colors=green*(1-forest[...,None])+rock*forest[...,None]
    apron=smooth((y-500)/190)
    colors=np.array((.24,.30,.12))*(1-apron[...,None])+colors*apron[...,None]
    # Round the Mega Park the ground under the closed canopy is forest floor, leaf litter and moss (megapark/forest.py).
    from megapark import forest as megapark_forest
    under=megapark_forest.floor(x,y)*(1-smooth((z-205)/30))
    litter=noise(x,y,40,41)
    floor=np.stack([.066+.018*litter,.062+.014*litter,np.full_like(x,.026)],axis=-1)
    colors=colors*(1-under[...,None])+floor*under[...,None]
    radius=np.hypot(x-550,y-1930)
    # Snow collects in broken, tapering gullies instead of long uniform ribbons.
    # Preserve a continuous crown, then expose irregular rock islands downslope.
    breakup=noise(x,y,38,31)*6+noise(x,y,83,32)*4
    exposure=smooth((radius-170)/180)
    signed=drainage_field(x,y)[0]+noise(x,y,25,19)*3
    signed-=smooth((radius-150)/130)*2+smooth((radius-420)/300)*3
    signed+=breakup*exposure
    signed=np.maximum(signed,170+noise(x,y,65,33)*14-radius)
    signed=np.minimum(signed,z-235)
    for j in range(len(ys)-1):
        for i in range(len(xs)-1):
            for offsets in [((0,0),(1,0),(1,1)),((0,0),(1,1),(0,1))]:
                p=[(x[j+b,i+a],y[j+b,i+a],z[j+b,i+a]) for a,b in offsets]
                color=np.mean([colors[j+b,i+a] for a,b in offsets],axis=0)
                values=[signed[j+b,i+a] for a,b in offsets]
                variation=1+.10*float(rock_noise[j,i])
                for snow in (False,True):
                    clipped=[]
                    for k in range(3):
                        a=np.array(p[k]);b=np.array(p[(k+1)%3]);da=values[k];db=values[(k+1)%3]
                        inside=da>=0 if snow else da<0
                        if inside:clipped.append(tuple(a))
                        if (da>=0)!=(db>=0):clipped.append(tuple(a+(b-a)*(da/(da-db))))
                    if len(clipped)>=3:m.poly(clipped,tuple(c*variation for c in ((.72,.76,.81) if snow else color)))
    return m

def trail_mesh(surface):
    from village.build import Mesh
    m=Mesh('HD_NorthTrail')
    for a,b in zip(TRAIL,TRAIL[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        nx,ny=-dy/length,dx/length
        for k in range(math.ceil(length/2)):
            t=k/math.ceil(length/2);nt=(k+1)/math.ceil(length/2)
            points=[]
            for q,s in [(t,-1),(nt,-1),(nt,1),(t,1)]:
                xx=a[0]+q*dx+nx*s*2.1;yy=a[1]+q*dy+ny*s*2.1
                points.append((xx,yy,float(surface(xx,yy))+.045))
            m.poly(points,(.24,.17,.095))
    # Rounded joins cover the outside wedge at each change in direction.
    for x,y in TRAIL[1:-1]:
        points=[]
        for i in range(16):
            a=i*math.tau/16;xx=x+2.1*math.cos(a);yy=y+2.1*math.sin(a)
            points.append((xx,yy,float(surface(xx,yy))+.05))
        for i in range(16):
            m.poly([(x,y,float(surface(x,y))+.05),points[i],points[(i+1)%16]],(.24,.17,.095))
    return m

def trail_points(surface):
    points=[]
    for a,b in zip(TRAIL,TRAIL[1:]):
        n=math.ceil(math.dist(a,b)/2)
        for k in range(n):
            t=k/n;x=a[0]+(b[0]-a[0])*t;y=a[1]+(b[1]-a[1])*t
            points.append([x,y,float(surface(x,y))])
    x,y=TRAIL[-1];points.append([x,y,float(surface(x,y))])
    return points


def forest_tree(kind,backdrop=False):
    """Low, interlocking opaque crowns replace distant lollipop leaf cards."""
    import bpy,random
    from village.build import Mesh
    r=random.Random({'Gold':81,'Rust':123,'Pine':206,'Green':279}[kind])
    m=Mesh('HD_NorthTree'+('Backdrop' if backdrop else '')+kind)
    bark=(.055,.027,.012)
    m.lathe((0,0,0),[(0,.26),(3.6,.17),(6,.06)],bark,n=7)
    m.collider((0,0,2.5),(.48,.48,5.))
    if kind=='Pine':
        for z,radius in [(2.8,2.8),(4.1,2.5),(5.8,1.9),(7.3,1.3)]:
            m.lathe((r.uniform(-.35,.35),r.uniform(-.35,.35),z),[(0,radius*.48),(.28,radius),(2.5,.05)],(.018,.049,.029),n=7)
        return m
    palette={'Gold':(.49,.27,.035),'Rust':(.45,.12,.023),'Green':(.028,.085,.044)}[kind]
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2,radius=1)
    ob=bpy.context.object
    for vertex in ob.data.vertices:
        vertex.co*=r.uniform(.78,1.15)
    ob.data.update()
    for k in range(7):
        a=k*math.tau/6+r.uniform(-.5,.5);radius=r.uniform(1.3,3.0);cx=radius*math.cos(a) if k<6 else 0;cy=radius*math.sin(a) if k<6 else 0
        cz=r.uniform(4.0,7.0) if k<6 else 8.0
        sx=r.uniform(1.5,2.9);sy=r.uniform(1.5,2.9);sz=r.uniform(1.4,2.7)
        tint=r.uniform(.80,1.15)
        for f in ob.data.polygons:
            pts=[(cx+ob.data.vertices[i].co.x*sx,cy+ob.data.vertices[i].co.y*sy,cz+ob.data.vertices[i].co.z*sz) for i in f.vertices]
            face=tint*(.52+.48*max(0,f.normal.z))
            m.poly(pts,tuple(v*face for v in palette))
    bpy.data.objects.remove(ob,do_unlink=True)
    return m
