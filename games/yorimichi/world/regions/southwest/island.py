"""The island: a steep single mountain rising from the sea, rock knobs on its shoulders, faceted cliffs meeting
the water (no sand except the landing cove on the north side toward the beach), a stairway ramp spiralling to a
flat summit platform for the temple. `height(x,y)` is the authored heightfield in island-local metres
(numpy-vectorised) so the layout can seat props and trees on it; `build()` makes the vertex-coloured mesh with
one flat colour per triangle (crisp facets); `boulder_*()` are the faceted rock props; `scatter()` gives the
layout the tree / understory / boulder placements and `torii_points()` the gates along the stair."""
import math, sys
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
# local copy: the layout runs without Blender. Linear values, dark on purpose: the game's exposure lifts them.
PALETTE={'sand':(.42,.35,.21),'rock':(.040,.042,.047),'rock_light':(.062,.064,.070),'rock_dark':(.026,.028,.032),
         'grass':(.070,.105,.026),'grass_dark':(.048,.078,.022),'moss':(.040,.068,.024),'step':(.080,.082,.086)}

SIZE=(310.0,270.0)        # footprint extent (x,y)
PEAK=122.0                # up from 104 m; a dome profile keeps the upper slopes forestable and the rim as cliffs (rock skirt = lower third)
SUMMIT=(0.0,8.0)          # summit plateau centre
SUMMIT_R=15.0             # flat radius: a 30 m circle, enough for the 26 x 20 m temple set
SUMMIT_Z=PEAK-1.0         # the platform is the top: the dome around it stays below
LANDING=(-20.0,112.0)     # cove on the north side (toward the beach); island local y is north like the world
COVE_R=16.0               # sand only here
KNOBS=[((62.0,-22.0),22.0,15.0),((-56.0,30.0),17.0,12.0),((18.0,74.0),12.0,10.0)]   # (centre, height, sigma): rock knobs on the shoulders
STEP=2.0
DOME_EXP=.85              # dome profile exponent: lower = flatter top and steeper rim
NOISE_AMP=(3.0,0.6)       # large / small relief noise amplitude in metres
ROCK_SLOPE=60.0           # degrees: steeper than this is bare rock (the cliff rim and the knobs)
SHORE_ROCK_Z=5.0          # below this the shore is rock (wet, dark) except in the cove

def _noise(x,y,seed=3):
    return (np.sin(x*.071+seed)+np.sin(y*.083+seed*1.7)+.6*np.sin((x+y)*.037+seed*2.3)+.4*np.sin((x-y)*.19+seed))/3.0

WAYPOINTS=[(-20.0,112.0),(-26.0,92.0),(-66.0,74.0),(56.0,56.0),(-50.0,34.0),(0.0,20.0)]   # switchbacks up the north face, toward the beach: readable from the sea; ends at the foot of the temple's own stair
FRONT_Y=SUMMIT[1]+6.0     # the platform is flat south of this line and descends toward the front (north) at about 18 degrees
FRONT_DROP=0.34           # metres per metre beyond FRONT_Y
PATH_END_Z=None           # set below: the ramp ends where the temple stair starts (local (0,20))
def path_points(n=480):
    """Stairway from the landing to the summit: switchbacks up the north face (the side facing the beach), corners
    rounded, so the whole climb with its torii is visible from the sea; about 340 m for a 120 m rise."""
    pts=np.array(WAYPOINTS,dtype=float);seg=np.hypot(*np.diff(pts,axis=0).T);s=np.concatenate([[0],np.cumsum(seg)])
    out=[]
    for i in range(n):
        t=i/(n-1);d=t*s[-1];k=min(int(np.searchsorted(s,d,side='right'))-1,len(seg)-1);u=(d-s[k])/seg[k]
        x,y=pts[k]*(1-u)+pts[k+1]*u
        out.append((float(x),float(y),t))
    # round the corners: box-smooth the polyline (12 m window), keeping the ends
    a=np.array(out);w=int(n*12/s[-1])|1
    for c in (0,1):
        sm=np.convolve(np.pad(a[:,c],(w//2,w//2),mode='edge'),np.ones(w)/w,mode='valid');a[:,c]=sm
    a[0,:2]=pts[0];a[-1,:2]=pts[-1]
    return [tuple(map(float,r)) for r in a]

_PATH=None
def _path_arrays():
    global _PATH
    if _PATH is None:
        p=np.array(path_points());_PATH=(p[:,0],p[:,1],p[:,2])
    return _PATH

def _base(x,y):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    dx=(x-SUMMIT[0])/(SIZE[0]*.44);dy=(y-SUMMIT[1])/(SIZE[1]*.46)
    r=np.sqrt(dx*dx+dy*dy)
    cone=np.clip(1-r*r,0,1)**DOME_EXP                                            # dome: gentle top, steep rim
    shoulder=np.exp(-(((x-66)/44)**2+((y+8)/40)**2))*.34
    z=PEAK*(cone+shoulder*(1-cone*.6))
    for (kx,ky),kh,ks in KNOBS:z=z+kh*np.exp(-((x-kx)**2+(y-ky)**2)/(2*ks*ks))
    z+=NOISE_AMP[0]*_noise(x,y)*np.clip(1-r,0,1)+NOISE_AMP[1]*_noise(x*2.3,y*2.3,7)
    z=np.where(z<22,z*.40+np.clip(z-6,0,None)*1.0,z)                          # steep rocky shore: cliffs into the water
    z-=3.0
    ds=np.sqrt((x-SUMMIT[0])**2+(y-SUMMIT[1])**2);plateau=np.clip((SUMMIT_R+6-ds)/6,0,1)
    plat_z=SUMMIT_Z-np.clip(y-FRONT_Y,0,None)*FRONT_DROP                          # flat, then sloping down toward the temple front
    z=z*(1-plateau)+plat_z*plateau
    dl=np.sqrt((x-LANDING[0])**2+(y-LANDING[1])**2);cove=np.clip((COVE_R-dl)/14,0,1)   # a bay: the cliff rises gradually out of the cove
    return z*(1-cove)+0.6*cove

_RAMP=None
def _ramp():
    """Path height: the base terrain sampled along the path and smoothed, then made monotonic with the local grade
    capped at 36 degrees so the stair climbs steadily; the end is pinned to the summit platform."""
    global _RAMP
    if _RAMP is None:
        px,py,pt=_path_arrays();z=_base(px,py)
        k=21;z=np.convolve(np.pad(z,(k//2,k//2),mode='edge'),np.ones(k)/k,mode='valid')
        seg=np.hypot(np.diff(px),np.diff(py));cap=math.tan(math.radians(36))       # steep enough to climb the shore cliff without a canyon; still walkable
        out=np.empty_like(z);out[0]=0.6
        for i in range(1,len(z)):out[i]=min(max(z[i],out[i-1]),out[i-1]+cap*seg[i-1])
        end_z=float(_base(np.array([WAYPOINTS[-1][0]]),np.array([WAYPOINTS[-1][1]]))[0])
        out=0.6+(out-0.6)*(end_z-0.6)/max(out[-1]-0.6,1e-6);out[-6:]=end_z
        _RAMP=out
    return _RAMP

def height(x,y):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);z=_base(x,y)
    px,py,pt=_path_arrays();rz=_ramp()
    d2=(x[...,None]-px)**2+(y[...,None]-py)**2
    k=np.argmin(d2,axis=-1);dmin=np.sqrt(np.take_along_axis(d2,k[...,None],axis=-1)[...,0]);ramp_z=rz[k]
    blend=3.0+13.0*np.clip((.20-pt[k])/.20,0,1)                                   # a wide gully out of the cove, a tight 3 m corridor higher up
    w=np.clip((4.0-dmin)/blend+1,0,1)*np.clip((4.0+blend-dmin)/blend,0,1)          # 4 m strip, cut-and-fill blend
    w=w*np.clip((np.sqrt((x-SUMMIT[0])**2+(y-SUMMIT[1])**2)-7.0)/4.0,0,1)         # the strip never reaches into the flat summit
    z=z*(1-w)+ramp_z*w
    # Open the landing cove to the sea. The radial cove alone leaves an 8 m
    # ridge across its mouth, trapping a rider against the island shoreline.
    cut=np.clip((15.0-np.abs(x-LANDING[0]))/8.0,0,1)
    cut=cut*cut*(3-2*cut)*np.clip((y-(LANDING[1]-4.0))/4.0,0,1)
    beach=np.maximum(-3.0,0.6-np.maximum(y-LANDING[1],0)*.12)
    return z*(1-cut)+np.minimum(z,beach)*cut

def slope_deg(x,y,eps=1.5):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    gx=(height(x+eps,y)-height(x-eps,y))/(2*eps);gy=(height(x,y+eps)-height(x,y-eps))/(2*eps)
    return np.degrees(np.arctan(np.hypot(gx,gy)))

def path_distance(x,y):
    px,py,pt=_path_arrays();x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    return np.sqrt(((x[...,None]-px)**2+(y[...,None]-py)**2).min(axis=-1))

def grid():
    xs=np.arange(-SIZE[0]/2,SIZE[0]/2+STEP,STEP);ys=np.arange(-SIZE[1]/2,SIZE[1]/2+STEP,STEP)
    X,Y=np.meshgrid(xs,ys);return X,Y,height(X,Y)

def face_colour(cx,cy,cz,slope,nz):
    """One colour per triangle from its centre, height, slope and normal: sand only in the cove, rock on every
    steep face and along the wet shore, grass in between with a darker band right under the rock and moss high up."""
    cx=np.asarray(cx);cy=np.asarray(cy);cz=np.asarray(cz);slope=np.asarray(slope);nz=np.asarray(nz)
    n=_noise(cx*3,cy*3,11)
    sand=np.array(PALETTE['sand']);rock=np.array(PALETTE['rock']);rock_l=np.array(PALETTE['rock_light']);rock_d=np.array(PALETTE['rock_dark'])
    grass=np.array(PALETTE['grass']);grass_d=np.array(PALETTE['grass_dark']);moss=np.array(PALETTE['moss']);step=np.array(PALETTE['step'])
    dl=np.hypot(cx-LANDING[0],cy-LANDING[1]);cove=(dl<COVE_R+4)&(cz<4.0)
    is_rock=(slope>ROCK_SLOPE)|((cz<SHORE_ROCK_Z)&~cove)
    jit=(np.sin(cx*12.9898+cy*78.233)*43758.5453)%1.0                                      # per-face hash: subtle facet variation, no blotches
    rockc=np.where((nz>.78)[...,None],rock_l,np.where((nz<.45)[...,None],rock_d,rock))*(0.9+0.2*jit)[...,None]
    c=np.where((cz>90)[...,None],moss,grass)
    c=np.where(((slope>ROCK_SLOPE-6)&~is_rock)[...,None],grass_d,c)                        # 2-4 m dark band right under the rock
    c=np.where(is_rock[...,None],rockc,c)
    c=np.where(cove[...,None],sand,c)
    c=np.where((path_distance(cx,cy)<2.2)[...,None],step,c)
    return np.clip(c,0,1)

def build():
    from mesh import Mesh
    X,Y,Z=grid();m=Mesh('SW_Island');ny,nx=Z.shape
    tris=[]
    for j in range(ny-1):
        for i in range(nx-1):
            a=(j,i);b=(j,i+1);c=(j+1,i+1);d=(j+1,i)
            if (i+j)%2:tris+=[(a,b,c),(a,c,d)]
            else:tris+=[(a,b,d),(b,c,d)]
    P=np.array([[(X[j,i],Y[j,i],Z[j,i]) for (j,i) in t] for t in tris])          # (n,3,3)
    ctr=P.mean(axis=1);nrm=np.cross(P[:,1]-P[:,0],P[:,2]-P[:,0]);nrm/=np.linalg.norm(nrm,axis=1)[:,None]+1e-9
    slope=np.degrees(np.arccos(np.clip(nrm[:,2],-1,1)))
    C=face_colour(ctr[:,0],ctr[:,1],ctr[:,2],slope,nrm[:,2])
    for t,col in zip(P,C):
        i=len(m.vertices);m.vertices.extend(tuple(map(float,p)) for p in t);m.faces.append((i,i+1,i+2));m.colors.extend([(*map(float,col),1)]*3)
    # skirt down to -12 m so the waterline never shows a gap
    ring=[(0,i) for i in range(nx)]+[(j,nx-1) for j in range(1,ny)]+[(ny-1,i) for i in range(nx-2,-1,-1)]+[(j,0) for j in range(ny-2,0,-1)]
    for (j0,i0),(j1,i1) in zip(ring,ring[1:]+ring[:1]):
        i=len(m.vertices)
        m.vertices+=[(float(X[j1,i1]),float(Y[j1,i1]),float(Z[j1,i1])),(float(X[j0,i0]),float(Y[j0,i0]),float(Z[j0,i0])),(float(X[j0,i0]),float(Y[j0,i0]),-12.0),(float(X[j1,i1]),float(Y[j1,i1]),-12.0)]
        m.faces.append((i,i+1,i+2,i+3));m.colors.extend([(*PALETTE['rock_dark'],1)]*4)
    return m

# ---- boulders: faceted rocks for the waterline ring, the lower slope and the peak (scaled 5-15 m by the layout)
def _boulder(name,seed,rx,ry,rz,rings=4,segs=7,jitter=.22,flat_top=.75):
    from mesh import Mesh
    rng=np.random.default_rng(seed);m=Mesh(name)
    def pt(i,k):
        th=math.pi*(i/rings);ph=2*math.pi*(k%segs)/segs+(.5*(i%2))*2*math.pi/segs
        r=1+jitter*rng.uniform(-1,1)
        x=rx*r*math.sin(th)*math.cos(ph);y=ry*r*math.sin(th)*math.sin(ph);z=rz*r*math.cos(th)
        return (x,y,max(z,-rz*.55) if z<0 else min(z,rz*flat_top))
    P=[[pt(i,k) for k in range(segs)] for i in range(rings+1)]
    P[0]=[(0,0,rz*flat_top*(1+jitter*.3))]*segs;P[-1]=[(0,0,-rz*.55)]*segs
    for i in range(rings):
        for k in range(segs):
            quad=[P[i][k],P[i][(k+1)%segs],P[i+1][(k+1)%segs],P[i+1][k]]
            q=[np.array(v) for v in quad];n=np.cross(q[1]-q[0],q[2]-q[0]);nz=n[2]/(np.linalg.norm(n)+1e-9)
            col=PALETTE['rock_light'] if nz>.55 else (PALETTE['rock_dark'] if nz<-.1 or (k*7+i)%5==0 else PALETTE['rock'])
            m.poly(quad,col)
    m.collider((0,0,0),(rx*1.6,ry*1.6,rz*1.3))
    return m
def boulder_a():return _boulder('SW_Boulder_A',11,1.0,.85,.75,rings=4,segs=7,jitter=.18)          # round, ~2 m unit
def boulder_b():return _boulder('SW_Boulder_B',23,1.4,.7,.6,rings=3,segs=6,jitter=.26,flat_top=.6)  # blocky slab
def boulder_c():return _boulder('SW_Boulder_C',37,.7,.6,1.25,rings=5,segs=6,jitter=.2,flat_top=.9)   # tall prism
BOULDERS={'boulder_a':boulder_a,'boulder_b':boulder_b,'boulder_c':boulder_c}

# ---- placements for the layout (island-local metres; the layout applies the island origin and yaw)
CONIFERS=(['Tree_Pine_B','Tree_Cedar_B','Tree_Pine_A'],[.55,.35,.10])
YELLOWS=(['Tree_Ginkgo_lo','Tree_Broad_lo','Tree_Ginkgo'],[.6,.3,.1])
MAPLES=(['Tree_Maple_lo','Tree_Maple_A'],[.75,.25])
def scatter(seed=1207,tree_attempts=14000,shrub_attempts=6000,boulders=140):
    """Returns dict(trees=[(asset,x,y,z,yaw,scale)],understory=[...],boulders=[...]). Trees only on the grass band
    (slope below the rock threshold, above the wet shore, outside the cove, the stair strip and the summit
    clearing), a 3.2 m minimum spacing so the canopy is continuous without stacking, 60 / 25 / 15 conifer / yellow
    / maple, conifers 1.3-1.6x on the ridge. Boulders sit on the rock: a ring at the waterline, some on the lower
    slope and a few on the peak knobs."""
    rng=np.random.default_rng(seed);trees=[];under=[];rocks=[]
    def ok_band(lx,ly,z,sl):
        if z<SHORE_ROCK_Z+1.0 or z>SUMMIT_Z-4:return False
        if sl>ROCK_SLOPE:return False
        if math.hypot(lx-SUMMIT[0],ly-SUMMIT[1])<SUMMIT_R+8:return False
        if math.hypot(lx-LANDING[0],ly-LANDING[1])<COVE_R+3:return False
        return True
    cell=2.8;occupied={}
    def free(lx,ly,r):
        cx,cy=int(lx//cell),int(ly//cell)
        for i in range(cx-1,cx+2):
            for j in range(cy-1,cy+2):
                for (qx,qy) in occupied.get((i,j),()):
                    if (qx-lx)**2+(qy-ly)**2<r*r:return False
        return True
    xs=rng.uniform(-SIZE[0]/2,SIZE[0]/2,tree_attempts);ys=rng.uniform(-SIZE[1]/2,SIZE[1]/2,tree_attempts)
    zs=height(xs,ys);sls=slope_deg(xs,ys);pds=path_distance(xs,ys)
    for lx,ly,z,sl,pd in zip(xs,ys,zs,sls,pds):
        if not ok_band(lx,ly,z,sl) or pd<4.5 or not free(lx,ly,2.8):continue
        u=rng.random();group=CONIFERS if u<.60 else (YELLOWS if u<.85 else MAPLES)
        asset=rng.choice(group[0],p=group[1]);scale=rng.uniform(.9,1.25)
        if group is CONIFERS and z>PEAK*.62:scale=rng.uniform(1.3,1.6)
        occupied.setdefault((int(lx//cell),int(ly//cell)),[]).append((lx,ly))
        trees.append((str(asset),round(float(lx),2),round(float(ly),2),round(float(z)-.3,2),round(float(rng.uniform(0,360)),1),round(float(scale),3)))
    xs=rng.uniform(-SIZE[0]/2,SIZE[0]/2,shrub_attempts);ys=rng.uniform(-SIZE[1]/2,SIZE[1]/2,shrub_attempts)
    zs=height(xs,ys);sls=slope_deg(xs,ys);pds=path_distance(xs,ys)
    for lx,ly,z,sl,pd in zip(xs,ys,zs,sls,pds):
        if not ok_band(lx,ly,z,sl+6) or pd<2.5:continue          # shrubs may sit a little closer to the rock edge
        asset=rng.choice(['Bush_Green_A','Bush_Green_B','Bush_Ochre_A','Bush_Ochre_B','Grass_A','Grass_B'],p=[.2,.2,.12,.08,.2,.2])
        under.append((str(asset),round(float(lx),2),round(float(ly),2),round(float(z)-.05,2),round(float(rng.uniform(0,360)),1),round(float(rng.uniform(.8,1.3)),3)))
    # boulders: waterline ring (z 0.5-6 on rock), lower slope rock faces, peak knobs
    n_ring=int(boulders*.6);n_slope=int(boulders*.28);n_peak=boulders-n_ring-n_slope
    for kind,count in (('ring',n_ring),('slope',n_slope),('peak',n_peak)):
        made=0;tries=0
        while made<count and tries<count*80:
            tries+=1
            if kind=='ring':
                a=rng.uniform(0,2*math.pi);r=rng.uniform(.80,1.0);lx=SUMMIT[0]+r*SIZE[0]*.46*math.cos(a);ly=SUMMIT[1]+r*SIZE[1]*.48*math.sin(a)
            elif kind=='slope':
                lx=rng.uniform(-SIZE[0]/2,SIZE[0]/2);ly=rng.uniform(-SIZE[1]/2,SIZE[1]/2)
            else:
                (kx,ky),kh,ks=KNOBS[int(rng.integers(len(KNOBS)))] if rng.random()<.7 else ((SUMMIT[0],SUMMIT[1]),0,SUMMIT_R+10)
                lx=kx+rng.normal(0,ks*.8);ly=ky+rng.normal(0,ks*.8)
            z=float(height(lx,ly));sl=float(slope_deg(lx,ly))
            if math.hypot(lx-LANDING[0],ly-LANDING[1])<COVE_R+6 or float(path_distance(lx,ly))<6:continue
            if kind=='ring' and not (-1.0<z<6.0):continue
            if kind=='slope' and not (6.0<z<PEAK*.55 and sl>ROCK_SLOPE-4):continue
            if kind=='peak' and not (z>PEAK*.6 and sl>ROCK_SLOPE-8 and math.hypot(lx-SUMMIT[0],ly-SUMMIT[1])>SUMMIT_R+6):continue
            asset=rng.choice(['SW_Boulder_A','SW_Boulder_B','SW_Boulder_C'],p=[.45,.35,.2])
            scale=rng.uniform(2.5,7.5) if kind=='ring' else rng.uniform(2.0,5.0)     # unit rocks are ~2 m: 5-15 m at the water
            rocks.append((str(asset),round(float(lx),2),round(float(ly),2),round(z-.12*scale,2),round(float(rng.uniform(0,360)),1),round(float(scale),2)))
            made+=1
    return dict(trees=trees,understory=under,boulders=rocks)

def torii_points(n=5):
    """Evenly spaced gates along the stair between 8% and 92% of the climb: (x,y,z,yaw) in island-local metres,
    yaw such that the gate faces along the path (the layout's previous convention: atan2 + 90)."""
    px,py,pt=_path_arrays();out=[]
    seg=np.hypot(np.diff(px),np.diff(py));s=np.concatenate([[0],np.cumsum(seg)]);L=s[-1]
    for k in range(n):
        target=L*(.06+.82*k/(n-1));i=int(np.searchsorted(s,target));i=min(max(i,2),len(px)-1)
        lx,ly=float(px[i]),float(py[i]);x0,y0=float(px[i-2]),float(py[i-2])
        out.append((lx,ly,float(height(lx,ly)),math.degrees(math.atan2(ly-y0,lx-x0))+90))
    return out

def summit_transform():return (SUMMIT[0],SUMMIT[1],SUMMIT_Z)
def stair_props(spacing=6.0):
    """Positions/yaws along the ramp for stone stair props."""
    p=path_points();out=[];acc=0
    for i in range(1,len(p)):
        x,y,t=p[i];x0,y0,_=p[i-1];acc+=math.hypot(x-x0,y-y0)
        if acc>=spacing:
            acc=0;yaw=math.degrees(math.atan2(y-y0,x-x0))-90;out.append((x,y,float(height(x,y)),yaw,t))
    return out
