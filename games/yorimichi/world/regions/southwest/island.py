"""The island: a wooded crown (about 123 m) with a lower west top and an east hump, headlands and points pushing
out on every side and four sea stacks off them, so the silhouette is uneven from any bearing. The coast is a band
of dark rock cliffs, mostly 4-30 m high and lowest at the cove, whose height changes with the bearing and which
break into a ledge where they are tall; the ground above them is capped at a steep but wooded slope, so the rock
stays at the rim and on a few knobs. A pale sand cove on the north side (toward the beach) is the landing; a valley climbs from it and the
stairway ramp zig-zags up the north face to the temple terrace on the crown's north spur (104 m).
`height(x,y)` is the authored heightfield in island-local metres (numpy-vectorised) so the layout can seat props
and trees on it; `build()` makes the vertex-coloured mesh with one flat colour per triangle (crisp facets);
`boulder_*()` are the faceted rock props and `pine_lean_*()` the pines that lean out over the cliff edges;
`scatter()` gives the layout the tree / understory / boulder placements (woods in masses: pines on the cliff tops,
a cedar grove on the crown, maple and ginkgo drifts) and `torii_points()` the gates along the stair."""
import math, sys
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
# local copy: the layout runs without Blender. Linear values, dark on purpose: the game's exposure lifts them.
PALETTE={'sand':(.42,.35,.21),'rock':(.048,.044,.040),'rock_light':(.076,.069,.058),'rock_dark':(.029,.027,.026),
         'grass':(.070,.105,.026),'grass_dark':(.048,.078,.022),'moss':(.040,.068,.024),'step':(.080,.082,.086),
         'pine':(.028,.058,.034),'pine_dark':(.015,.034,.021),'bark':(.050,.034,.022)}

SIZE=(340.0,316.0)        # grid extent (x,y): the coast with its headlands and stacks, and a margin of sea floor
PEAK=124.0                # the wooded crown behind the temple
CROWN=(10.0,-20.0)        # its top
SUMMIT=(0.0,8.0)          # the temple terrace, on the crown's north spur
SUMMIT_R=15.0             # flat radius: a 30 m circle, enough for the 26 x 20 m temple set
SUMMIT_Z=104.0
LANDING=(-20.0,112.0)     # cove on the north side (toward the beach); island local y is north like the world
COVE_R=16.0               # sand only here
CENTRE=(0.0,-6.0)         # the coastline is a radius around this point, by bearing
STEP=2.0
NOISE_AMP=(3.0,0.6)       # large / small relief noise amplitude in metres
ROCK_SLOPE=64.0           # degrees: steeper than this is bare rock (the sea cliffs, their ledges' risers, the outcrops); the steep wooded flanks stay green
SHORE_ROCK_Z=4.0          # below this the shore is rock (wet, dark) except in the cove

def _noise(x,y,seed=3):
    return (np.sin(x*.071+seed)+np.sin(y*.083+seed*1.7)+.6*np.sin((x+y)*.037+seed*2.3)+.4*np.sin((x-y)*.19+seed))/3.0

def _lobe(th,at,width,amount):
    """A bump of `amount` metres on the coastline around bearing `at` (degrees), `width` degrees wide."""
    d=np.degrees(np.angle(np.exp(1j*(th-np.radians(at)))))
    return amount*np.exp(-(d/width)**2)

# the outline: two rocky headlands flank the cove (north-east and north-west), a long low point runs out to the west,
# the east side is a broad cliffed shoulder, the south a scalloped line of coves and spurs
HEADLANDS=[(-95.0,34.0,10.0),(70.0,9.0,36.0),(126.0,8.0,30.0),(186.0,11.0,20.0),(-14.0,16.0,12.0),(-58.0,9.0,-14.0),(-104.0,7.0,-10.0),(-128.0,12.0,10.0),(28.0,8.0,-8.0)]
COVE_BEARING=math.degrees(math.atan2(LANDING[1]-CENTRE[1],LANDING[0]-CENTRE[0]))
STACKS=[((80.0,140.0),9.0,15.0),((-104.0,124.0),8.0,12.0),((-146.0,-96.0),7.5,10.0),((152.0,-86.0),10.0,14.0)]   # sea stacks: (centre, radius, height)
# the hills behind the cliffs, heights above the sea: (centre, radii west/east/south/north, height, profile exponents
# (top, flank), footprint exponent: 2 an ellipse, higher a rounded rectangle). Rounded domes joined by a soft maximum,
# so they meet in saddles: the crown; the stair face under the temple terrace, broad and even so the switchbacks climb
# it steadily; a lower west shoulder; an east hump across a saddle; low tops on the headlands and the west point.
HILLS=[(CROWN,(100.0,118.0,116.0,120.0),PEAK,(1.6,1.6),2),
       ((0.0,16.0),(120.0,100.0,60.0,104.0),SUMMIT_Z-1.0,(1.25,1.0),4),
       ((-94.0,6.0),(64.0,56.0,74.0,66.0),98.0,(1.7,1.5),2),((104.0,-8.0),(52.0,50.0,62.0,60.0),72.0,(1.8,1.5),2),
       ((-142.0,8.0),(36.0,40.0,34.0,36.0),24.0,(1.6,1.5),2),((-118.0,80.0),(34.0,36.0,30.0,30.0),30.0,(1.6,1.5),2),
       ((64.0,116.0),(30.0,30.0,26.0,24.0),30.0,(1.6,1.5),2)]
VALLEY=((-20.0,114.0),(-27.0,88.0),7.0,.8,.85)   # a wooded ravine behind the cove: mouth, head, half floor width, floor and side grades
OUTCROPS=[((-58.0,-44.0),9.0,12.0),((84.0,-58.0),8.0,10.0),((-30.0,-84.0),7.0,9.0),((122.0,30.0),7.0,9.0)]   # rock knobs in the forest

def coast_radius(th):
    r=136.0+7.0*np.sin(2*th+.7)+5.0*np.sin(3*th+2.1)+3.5*np.sin(5*th+.3)+2.2*np.sin(7*th+1.9)+1.2*np.sin(11*th+.4)
    for at,w,a in HEADLANDS:r=r+_lobe(th,at,w,a)
    return r-_lobe(th,COVE_BEARING,9.0,16.0)

def cliff_height(th):
    """Height of the sea cliff by bearing: low at the cove, highest on the exposed south and east."""
    h=17.0+9.0*np.sin(3*th+1.0)+5.0*np.sin(5*th+2.0)+3.0*np.sin(9*th+.5)+_lobe(th,70.0,10.0,8.0)+_lobe(th,126.0,9.0,6.0)
    return np.maximum(h,4.0)*(1-.8*np.exp(-(np.degrees(np.angle(np.exp(1j*(th-np.radians(COVE_BEARING)))))/20.0)**2))

def _dome(x,y,c,r,h,e,n):
    dx=np.abs(x-c[0])/np.where(x<c[0],r[0],r[1]);dy=np.abs(y-c[1])/np.where(y<c[1],r[2],r[3])
    q=np.clip((dx**n+dy**n)**(1/n),0,1)
    return h*(1-q**e[0])**e[1]

def _hills(x,y,p=6.0):
    """Soft maximum (a p-norm) of the domes: rounded saddles where two hills meet, never their sum."""
    zs=np.stack([_dome(x,y,*hill) for hill in HILLS]);top=np.maximum(zs.max(0),1e-6)
    return top*((zs/top)**p).sum(0)**(1/p)

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

def _smooth(t):
    t=np.clip(t,0,1);return t*t*(3-2*t)

def _base(x,y):
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float)
    th=np.arctan2(y-CENTRE[1],x-CENTRE[0]);r=np.hypot(x-CENTRE[0],y-CENTRE[1])
    wob=4.0*_noise(x*.9,y*.9,5)                                                    # the coastline wanders
    d=coast_radius(th)+wob-r                                                       # metres inland from the waterline
    hc=cliff_height(th)*(1+.18*_noise(x*1.7,y*1.7,9))
    # the sea cliff: where it is high, a first riser, a sloping ledge part way up (moss and pines on it), a second
    # riser; where it is low, one riser with the forest right above it. The hills start from the cliff top.
    width=10.0+3.0*np.sin(4*th+1.3)
    t=d/width;split=1-_smooth((hc-12.0)/6.0)*(.50-.12*np.sin(6*th+.8))
    cliff=hc*(split*_smooth(t/.34)+(1-split)*_smooth((t-.62)/.38))
    z=np.where(d<0,np.maximum(d*.30,-12.8),cliff)-1.2                             # below the waterline the cliff keeps dropping
    hills=_hills(x,y)
    for (kx,ky),kr,kh in OUTCROPS:hills=hills+kh*_smooth((kr-np.hypot(x-kx,y-ky))/(kr*.45))
    # above the cliff top the ground may rise no faster than a forested slope (53-58 degrees with the bearing):
    # a hill that reaches the coast is cut back into a wooded flank, never a second bare wall behind the cliff
    excess=np.maximum(hills+NOISE_AMP[0]*_noise(x,y)-hc,0)
    cap=np.maximum(d-width*.6,0)*(1.45+.12*np.sin(3*th+.4))
    k=8.0;hk=np.clip((k-np.abs(excess-cap))/k,0,1)
    z=z+np.maximum(np.minimum(excess,cap)-hk*hk*k/4,0)+NOISE_AMP[1]*_noise(x*2.3,y*2.3,7)
    (ax,ay),(bx,by),hw,grade,side=VALLEY                                           # the ravine the stair climbs out of the cove
    L=math.hypot(bx-ax,by-ay);ux,uy=(bx-ax)/L,(by-ay)/L
    u=(x-ax)*ux+(y-ay)*uy;lat=np.abs((x-ax)*uy-(y-ay)*ux)
    wall=0.6+grade*np.clip(u,0,L)+np.maximum(lat-hw,0)*side
    z=z-np.maximum(z-wall,0)*(1-_smooth((u-L)/24.0))*_smooth((u+12.0)/12.0)
    for (sx,sy),sr,sh in STACKS:                                                   # sea stacks off the headlands
        q=np.hypot(x-sx,y-sy)/sr;z=np.maximum(z,np.where(q<1,sh*_smooth((1-q)/.35)*(1+.12*_noise(x*3,y*3,2))-1.5,-14.0))
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
    # where the stair runs above the hillside (the ends of the switchbacks) the ground rises to carry it, falling
    # away at 45 degrees from its edges: a wooded spur under each turn, never a bare embankment wall
    lift=rz-_base(px,py);raised=lift>.5
    if raised.any():
        dd=np.maximum(np.sqrt(d2[...,raised])-4.0,0)
        spur=np.where(dd<lift[raised],rz[raised]-dd,-1e9).max(axis=-1)
        z=np.where(spur>z,z+(spur-z)*(1-w),z)
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
    pd=path_distance(cx,cy)
    c=np.where(((pd<10.0)&is_rock&(cz>SHORE_ROCK_Z+2))[...,None],moss,c)                 # the stair banks are mossy, not bare scars
    c=np.where((pd<2.2)[...,None],step,c)
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

# ---- leaning pines: the black pines of the Japanese coast, grown out over the cliff edge toward the sea
def _pine_lean(name,seed,height,lean):
    """A trunk in five beams that leans out along +x by `lean` metres and turns up at the top, with flat layered
    needle pads on short branches (the clipped-cloud look of a coastal kuromatsu). The layout yaws +x to the sea."""
    from mesh import Mesh
    rng=np.random.default_rng(seed);m=Mesh(name)
    pts=[(0.0,0.0,-.6)]
    for k in range(1,6):
        t=k/5;out=lean*math.sin(t*math.pi*.62)/math.sin(math.pi*.62)          # leans out fast, then climbs
        pts.append((out+rng.uniform(-.25,.25),rng.uniform(-.4,.4),height*(.08+.92*t**.9)))
    for k,(a,b) in enumerate(zip(pts[:-1],pts[1:])):
        w=.62-.09*k;m.beam(a,b,w,w,PALETTE['bark'])
    def pad(c,r,h):
        ring=[(c[0]+math.cos(a)*r*(1+.25*math.sin(3*a+c[0])),c[1]+math.sin(a)*r*(1+.2*math.cos(2*a+c[1])),c[2]) for a in np.linspace(0,2*math.pi,10,endpoint=False)]
        top=[(c[0]*.35+q[0]*.65,c[1]*.35+q[1]*.65,c[2]+h) for q in ring]
        m.poly(ring[::-1],PALETTE['pine_dark'])
        for i in range(10):m.poly([ring[i],ring[(i+1)%10],top[(i+1)%10],top[i]],PALETTE['pine'] if i%2 else PALETTE['pine_dark'])
        m.poly(top,PALETTE['pine'])
    for k,p in enumerate(pts[2:]):
        for j in range(2 if k<3 else 1):
            ang=rng.uniform(0,2*math.pi) if k<3 else 0.0;dist=rng.uniform(1.2,2.4)*(1-.18*k)
            c=(p[0]+math.cos(ang)*dist,p[1]+math.sin(ang)*dist,p[2]+rng.uniform(-.3,.4))
            m.beam(p,c,.22,.22,PALETTE['bark'])
            pad(c,rng.uniform(1.8,2.6)*(1-.12*k),rng.uniform(.55,.8))
    pad((pts[-1][0]+.3,pts[-1][1],pts[-1][2]+.2),2.2,.8)
    return m
def pine_lean_a():return _pine_lean('SW_PineLean_A',41,9.0,5.5)    # far out over the edge
def pine_lean_b():return _pine_lean('SW_PineLean_B',43,11.0,3.2)   # taller, leaning less

# ---- placements for the layout (island-local metres; the layout applies the island origin and yaw)
PINES=(['Tree_Pine_B','Tree_Pine_A'],[.65,.35])
CEDARS=(['Tree_Cedar_B','Tree_Cedar_A'],[.6,.4])
MAPLES=(['Tree_Maple_lo','Tree_Maple_A'],[.75,.25])
GINKGOS=(['Tree_Ginkgo_lo','Tree_Ginkgo'],[.8,.2])
BROADS=(['Tree_Broad_lo'],[1.0])
CANOPY=(['Tree_Canopy_Crimson','Tree_Canopy_Maple'],['Tree_Canopy_Ginkgo','Tree_Canopy_Amber'])   # the tree house's big autumn crowns
GROVE_R=38.0              # the dark cedar grove on the crown, behind the temple

def inland(x,y):
    """Metres from the coastline, positive inland."""
    th=np.arctan2(y-CENTRE[1],x-CENTRE[0]);return coast_radius(th)-np.hypot(x-CENTRE[0],y-CENTRE[1])

def forest(x,y,z):
    """Which forest grows here, as probabilities (pine, cedar, maple, ginkgo, broad) that change over tens of metres:
    black pines along the cliff tops and headlands, a cedar grove on the crown, maples filling the hollows and in
    drifts, ginkgo drifts on the lower slopes, a mixed wood of pine, cedar and broadleaf between them."""
    x=np.asarray(x,dtype=float);y=np.asarray(y,dtype=float);z=np.asarray(z,dtype=float)
    d=inland(x,y);th=np.arctan2(y-CENTRE[1],x-CENTRE[0])
    e=10.0;b=_base(x,y)
    hollow=np.clip(((_base(x+e,y)+_base(x-e,y)+_base(x,y+e)+_base(x,y-e)-4*b)/(e*e)-.01)/.04,0,1)   # concave ground
    coast=(1-_smooth((d-8.0)/14.0))*np.clip((cliff_height(th)-5.0)/8.0,0,1)
    grove=1-_smooth((np.hypot(x-CROWN[0],y-CROWN[1])-GROVE_R)/14.0)
    maple=np.maximum(_smooth((_noise(x*1.5,y*1.5,21)-.10)/.35),hollow)
    ginkgo=_smooth((_noise(x*1.3+40.0,y*1.3,33)-.20)/.3)*(1-_smooth((z-80.0)/20.0))*(1-maple)
    free=(1-coast)*(1-grove)
    p=np.stack([.08+coast*.85+free*.18,.03+grove*.85+free*.10,.02+free*maple*.90,.02+free*ginkgo*.80,.02+free*.08])
    p=p*p;return p/p.sum(0)                                                       # squared: each wood keeps to its own ground

def glade(x,y,sl):
    """Open grass where the slope allows it: a few clearings so the wood is not one carpet."""
    return (_noise(np.asarray(x)*1.2,np.asarray(y)*1.2,47)<-.58)&(np.asarray(sl)<42)

def scatter(seed=1207,tree_attempts=36000,shrub_attempts=7000,boulders=140):
    """Returns dict(trees=[(asset,x,y,z,yaw,scale)],understory=[...],boulders=[...]). Trees only on the grass band
    (slope below the rock threshold, or below 80 degrees on the stair's mossy cut banks; above the wet shore, outside
    the cove, the stair strip, the summit clearing and a few glades), 3 m apart so the canopy is continuous. The forest is in masses (see forest()): pines on the
    cliff tops, cedars on the crown (1.3-1.6x), maple and ginkgo drifts. Leaning pines (SW_PineLean_*) grow out over
    the cliff edges on the headlands and top the sea stacks, yawed toward the sea. Boulders sit at the foot of the
    cliffs, on the steep lower faces and on the rock knobs."""
    rng=np.random.default_rng(seed);trees=[];under=[];rocks=[]
    def ok_band(lx,ly,z,sl,bank=False):
        if z<SHORE_ROCK_Z+1.0 or z>SUMMIT_Z-4 and math.hypot(lx-CROWN[0],ly-CROWN[1])>GROVE_R:return False
        if sl>(80.0 if bank and z>SHORE_ROCK_Z+6 else ROCK_SLOPE):return False    # the stair's mossy cut banks are wooded too
        if math.hypot(lx-SUMMIT[0],ly-SUMMIT[1])<SUMMIT_R+8:return False
        if math.hypot(lx-LANDING[0],ly-LANDING[1])<COVE_R+3:return False
        return True
    cell=3.0;occupied={}
    def free(lx,ly,r):
        cx,cy=int(lx//cell),int(ly//cell)
        for i in range(cx-2,cx+3):
            for j in range(cy-2,cy+3):
                for (qx,qy) in occupied.get((i,j),()):
                    if (qx-lx)**2+(qy-ly)**2<r*r:return False
        return True
    def take(lx,ly):occupied.setdefault((int(lx//cell),int(ly//cell)),[]).append((lx,ly))
    def add(group,asset,lx,ly,z,yaw,scale):
        group.append((str(asset),round(float(lx),2),round(float(ly),2),round(float(z),2),round(float(yaw),1),round(float(scale),3)))
    # leaning pines first: on the cliff tops where the cliff is high, most on the headlands, yawed out to sea
    xs=rng.uniform(-SIZE[0]/2,SIZE[0]/2,9000);ys=rng.uniform(-SIZE[1]/2,SIZE[1]/2,9000)
    th=np.arctan2(ys-CENTRE[1],xs-CENTRE[0]);d=inland(xs,ys);hc=cliff_height(th)
    near=(d>7.0)&(d<16.0)&(hc>9.0);xs,ys,th=xs[near],ys[near],th[near]
    zs=height(xs,ys);sls=slope_deg(xs,ys);pds=path_distance(xs,ys);leaning=0
    for lx,ly,a,z,sl,pd in zip(xs,ys,th,zs,sls,pds):
        if leaning>=34 or sl>50 or pd<8 or not ok_band(lx,ly,z,sl) or not free(lx,ly,11.0):continue
        head=max(float(_lobe(a,at,w*1.6,1.0)) for at,w,amt in HEADLANDS if amt>0)
        if rng.random()>.25+.75*head:continue
        take(lx,ly);leaning+=1
        add(trees,'SW_PineLean_A' if rng.random()<.55 else 'SW_PineLean_B',lx,ly,z-.3,math.degrees(a)+rng.uniform(-30,30),rng.uniform(.85,1.2))
    for (sx,sy),sr,sh in STACKS:                                                   # every stack wears a pine
        a=math.atan2(sy-CENTRE[1],sx-CENTRE[0]);z=float(height(sx,sy))
        add(trees,'SW_PineLean_A',sx-math.cos(a)*sr*.25,sy-math.sin(a)*sr*.25,z-.3,math.degrees(a)+rng.uniform(-20,20),rng.uniform(.8,1.0));take(sx,sy)
        add(trees,'Tree_Pine_B',sx+math.sin(a)*sr*.3,sy-math.cos(a)*sr*.3,z-.3,rng.uniform(0,360),rng.uniform(.7,.9))
    # the wood
    xs=rng.uniform(-SIZE[0]/2,SIZE[0]/2,tree_attempts);ys=rng.uniform(-SIZE[1]/2,SIZE[1]/2,tree_attempts)
    zs=height(xs,ys);sls=slope_deg(xs,ys);pds=path_distance(xs,ys);P=forest(xs,ys,zs);open_=glade(xs,ys,sls)
    groups=(PINES,CEDARS,MAPLES,GINKGOS,BROADS)
    for k,(lx,ly,z,sl,pd) in enumerate(zip(xs,ys,zs,sls,pds)):
        if open_[k] or not ok_band(lx,ly,z,sl,pd<10.0) or pd<3.2 or not free(lx,ly,3.0):continue
        g=int(rng.choice(5,p=P[:,k]));group=groups[g]
        asset=rng.choice(group[0],p=group[1]);scale=rng.uniform(.9,1.25)
        if g in (2,3) and P[g,k]>.5 and rng.random()<.22:                     # the heart of a drift: a big autumn crown
            asset=rng.choice(CANOPY[g-2]);scale=rng.uniform(.75,.95)
        if g<2 and z>PEAK*.62:scale=rng.uniform(1.3,1.6)                       # the crown stands tall
        take(lx,ly);add(trees,asset,lx,ly,z-.3-.03*max(sl-30.0,0),rng.uniform(0,360),scale)   # sunk deeper on steep ground: no root in the air
    xs=rng.uniform(-SIZE[0]/2,SIZE[0]/2,shrub_attempts);ys=rng.uniform(-SIZE[1]/2,SIZE[1]/2,shrub_attempts)
    zs=height(xs,ys);sls=slope_deg(xs,ys);pds=path_distance(xs,ys)
    for lx,ly,z,sl,pd in zip(xs,ys,zs,sls,pds):
        if not ok_band(lx,ly,z,sl+6,pd<10.0) or pd<2.5:continue          # shrubs may sit a little closer to the rock edge
        asset=rng.choice(['Bush_Green_A','Bush_Green_B','Bush_Ochre_A','Bush_Ochre_B','Grass_A','Grass_B'],p=[.2,.2,.12,.08,.2,.2])
        add(under,asset,lx,ly,z-.05,rng.uniform(0,360),rng.uniform(.8,1.3))
    # boulders: at the foot of the cliffs (awash or just above the water), on the steep lower faces, on the knobs
    n_ring=int(boulders*.6);n_slope=int(boulders*.28);n_peak=boulders-n_ring-n_slope
    for kind,count in (('ring',n_ring),('slope',n_slope),('peak',n_peak)):
        made=0;tries=0
        while made<count and tries<count*80:
            tries+=1
            if kind=='ring':
                a=rng.uniform(-math.pi,math.pi);r=float(coast_radius(a))+rng.uniform(-2.0,7.0);lx=CENTRE[0]+r*math.cos(a);ly=CENTRE[1]+r*math.sin(a)
            elif kind=='slope':
                lx=rng.uniform(-SIZE[0]/2,SIZE[0]/2);ly=rng.uniform(-SIZE[1]/2,SIZE[1]/2)
            else:
                (kx,ky),ks,kh=OUTCROPS[int(rng.integers(len(OUTCROPS)))] if rng.random()<.7 else (CROWN,SUMMIT_R+10,0)
                lx=kx+rng.normal(0,ks*.8);ly=ky+rng.normal(0,ks*.8)
            z=float(height(lx,ly));sl=float(slope_deg(lx,ly))
            if math.hypot(lx-LANDING[0],ly-LANDING[1])<COVE_R+10 or float(path_distance(lx,ly))<6:continue
            if kind=='ring' and not (-3.0<z<6.0):continue
            if kind=='slope' and not (6.0<z<PEAK*.55 and sl>ROCK_SLOPE-4):continue
            if kind=='peak' and not (z>PEAK*.4 and sl>ROCK_SLOPE-12 and math.hypot(lx-SUMMIT[0],ly-SUMMIT[1])>SUMMIT_R+6):continue
            asset=rng.choice(['SW_Boulder_A','SW_Boulder_B','SW_Boulder_C'],p=[.45,.35,.2])
            scale=rng.uniform(2.5,7.5) if kind=='ring' else rng.uniform(2.0,5.0)     # unit rocks are ~2 m: 5-15 m at the water
            add(rocks,asset,lx,ly,z-.12*scale,rng.uniform(0,360),scale)
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
