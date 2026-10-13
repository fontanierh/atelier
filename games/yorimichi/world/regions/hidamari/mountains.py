"""Northern foothills and a distant volcanic summit, in Blender world metres.

One sampled surface drives mesh, trees, trail and map. The accessible trail rises
gradually out of the park; the large summit is a scenic landmark beyond it.
"""
import math
from functools import lru_cache
import numpy as np
from megapark import placement as megapark
from craterpark import placement as craterpark

from belmonte import layout as belmonte
from belmonte.layout import SOUTH_JOIN

# The foothills reach north to Belmonte's southern join (belmonte/layout.py).
BOUNDS = (-700., 500., 2400., SOUTH_JOIN)
STEP = 5.
# The volcano (docs/VOLCANO.md): a broad cone whose summit caldera has a level floor wide and deep enough for a park,
# FLOOR_RADIUS across its foot and DEPTH below the crest.
VOLCANO = (850., 2400.)     # centre, Blender metres (x east, y north)
BASE_RADIUS = 1480.         # where the cone meets the foothills
RIM_RADIUS = 470.           # mean radius of the crest; it wanders by about 35 m
# The level floor reaches this far; the wall's foot moves in and out by up to 12 m. Crater Park (a 338 x 385 m block,
# corner radius 256 m) then keeps at least 62 m to the wall's foot at any heading, room for the slopes round its edges.
FLOOR_RADIUS = 330.
CREST = 600.                # the cone's height over its apron at the crest
DEPTH = 45.                 # the floor lies this far below the crest: Crater Park stands high in it, its tallest
                            # ramps just over the rim (craterpark/placement.py LIFT)
# The former, smaller summit stands on as the western shoulder, so the ground round the Mega Park keeps its shape.
FORMER = (550., 1930.)
MEGAPARK_SHOULDER = (-150., 1300., 1150., 450.)    # x, y, radius where the former cone is kept in full, fade
SNOW_STEP = 2.5
SNOW_BOUNDS = (VOLCANO[0]-1280., VOLCANO[1]-1280., VOLCANO[0]-1280.+1023*SNOW_STEP, VOLCANO[1]-1280.+1023*SNOW_STEP)
# Heights on the larger cone scale its predecessor's by LIFT above the apron, so the tree line, rock and snow sit at
# the same share of the slope (forest/ecotone.py and hidamari/layout.py read it too).
LIFT = 1.35
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

def polar(x,y,centre=VOLCANO):
    dx,dy=np.asarray(x,float)-centre[0],np.asarray(y,float)-centre[1]
    return dx,dy,np.hypot(dx,dy),np.arctan2(dy,dx)

def rim_radius(angle):
    """The crest's radius: two slow harmonics and noise, so the caldera is not a drawn circle."""
    return (RIM_RADIUS+18*np.cos(angle-2.3)+10*np.cos(3*angle+1.1)
            +14*noise(np.cos(angle)*400,np.sin(angle)*400,90.,93))

def wall_foot(angle):
    """Where the caldera wall leaves the floor: collapse scallops push it in and out."""
    return FLOOR_RADIUS+(18*noise(np.cos(angle)*500,np.sin(angle)*500,60.,94)+10*np.cos(7*angle+.8)).clip(-12,None)

def apron_height(y):
    return 47+np.maximum(np.asarray(y,float)-500,0)*.020

def stretch(r):
    """A radius on the former cone (summit rim 95 m, base 1170 m) to the same place on this one."""
    return RIM_RADIUS+(np.asarray(r,float)-95)*(BASE_RADIUS-RIM_RADIUS)/(1170-95)

def lifted(z):
    """A height on the former cone, over its apron at the summit (76 m), to the same share of this one's slope."""
    return apron_height(VOLCANO[1])+(np.asarray(z,float)-76)*LIFT

@lru_cache(maxsize=1)
def drainage():
    """Authored-seed branching snow gullies from the rim down the flanks, expressed as planar tapered segments."""
    rng=np.random.default_rng(412)
    segments=[]
    cx,cy=VOLCANO
    for i in range(40):
        angle=i*math.tau/40+rng.uniform(-.05,.05)
        reach=stretch(rng.uniform(580,890));bend=rng.uniform(-.15,.15)
        radii=[RIM_RADIUS-25,stretch(160),stretch(280),RIM_RADIUS+(reach-RIM_RADIUS)*.58,RIM_RADIUS+(reach-RIM_RADIUS)*.80,reach]
        widths=[30,26,15,11,7,0]
        points=[]
        for k,r in enumerate(radii):
            a=angle+bend*r/reach+(rng.uniform(-.045,.045) if k>1 else 0)
            points.append((cx+r*math.cos(a),cy+r*math.sin(a),widths[k]))
        segments.extend(zip(points,points[1:]))
        # Two narrow tributaries leave different levels, joining the main snow field.
        for k,side in [(2,-1),(3,1)]:
            start=points[k];rr=radii[k]
            end=rr+rng.uniform(130,240);a=angle+bend+side*rng.uniform(.10,.20)
            middle=(cx+(rr+end)/2*math.cos(a),cy+(rr+end)/2*math.sin(a),10)
            tip=(cx+end*math.cos(a+side*.035),cy+end*math.sin(a+side*.035),0)
            segments.extend([((start[0],start[1],13),middle),(middle,tip)])
    return segments

@lru_cache(maxsize=1)
def former_drainage():
    """The former summit's gullies, which still cut its shoulder."""
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
            points.append((FORMER[0]+r*math.cos(a),FORMER[1]+r*math.sin(a),widths[k]))
        segments.extend(zip(points,points[1:]))
        for k,side in [(2,-1),(3,1)]:
            start=points[k];rr=radii[k]
            end=rr+rng.uniform(130,240);a=angle+bend+side*rng.uniform(.10,.20)
            middle=(FORMER[0]+(rr+end)/2*math.cos(a),FORMER[1]+(rr+end)/2*math.sin(a),8)
            tip=(FORMER[0]+end*math.cos(a+side*.035),FORMER[1]+end*math.sin(a+side*.035),0)
            segments.extend([((start[0],start[1],11),middle),(middle,tip)])
    return segments

def drainage_field(x,y,segments=None,spread=16,depth=12):
    x,y=np.broadcast_arrays(x,y)
    snow=np.full(x.shape,-1e9)
    cut=np.zeros_like(x,dtype=float)
    for a,b in drainage() if segments is None else segments:
        dx=b[0]-a[0];dy=b[1]-a[1]
        t=np.clip(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1)
        distance=np.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
        width=a[2]*(1-t)+b[2]*t
        snow=np.maximum(snow,width-distance)
        cut=np.maximum(cut,np.exp(-(distance/(width+spread))**2)*smooth(width/depth))
    return snow,cut

def _foothills(x,y,trail_quiet):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    north=np.maximum(y-500,0)
    hills=(70*np.exp(-((x-80)/400)**2-((y-930)/230)**2)
           +22*np.exp(-((x-1000)/350)**2-((y-1330)/220)**2)
           +58*np.exp(-((x-1030)/260)**2-((y-970)/160)**2)
           +65*np.exp(-((x-1450)/300)**2-((y-1800)/150)**2)
           +150*np.exp(-((x-1920)/520)**2-((y-2230)/270)**2)
           +106*np.exp(-((x-1930)/420)**2-((y-1140)/280)**2)
           -70*np.exp(-((x-520)/270)**2-((y-1050)/340)**2))
    return apron_height(y)+hills+noise(x,y,130,4)*15*smooth(north/240)*trail_quiet

def _cone(x,y,trail_quiet):
    """The volcano over its foothills, before the caldera: a concave cone from the crest to its base, arêtes and
    gullies on the flanks, and the crest's broken lip with three spires."""
    dx,dy,r,angle=polar(x,y)
    crest=rim_radius(angle)
    cone=CREST*(1-np.clip((r-crest)/(BASE_RADIUS-crest),0,1))**1.45
    k=(BASE_RADIUS-RIM_RADIUS)/(1170-95)
    ridge=(.5+.5*np.cos(angle*8+.45*np.sin(angle*3)+r*.0006))**2
    ridge_band=smooth((r-RIM_RADIUS-30)/150)*smooth((BASE_RADIUS-r)/380)
    # Long arêtes read from the flight above the summit as well as from town.
    _,cuts=drainage_field(x,y,spread=20,depth=14)
    lift=1+.40*np.cos(angle-2.6)+.12*np.cos(2*angle+.7)+.25*noise(np.cos(angle)*300,np.sin(angle)*300,40.,91)
    breach=1.-.6*smooth((np.cos(angle-.5)-.82)/.15)
    lip=26*np.exp(-((r-crest)/np.where(r<crest,30.,80.))**2)*lift*breach
    peaks=sum(h*np.exp(-((dx-rr*math.cos(a))**2+(dy-rr*math.sin(a))**2)/s**2)
              for a,rr,h,s in ((2.6,RIM_RADIUS+5,42,50),(-.35,RIM_RADIUS+10,20,36),(4.2,RIM_RADIUS+12,14,30)))
    shoulders=(100*np.exp(-((dx-400*k)/(130*k))**2-((dy-90*k)/(160*k))**2)
               +60*np.exp(-((dx+300*k)/(120*k))**2-((dy+190*k)/(150*k))**2))
    relief=((ridge*np.minimum(52.,cone*.12)-cuts*np.minimum(30.,cone*.1))*ridge_band+lip+peaks+shoulders
            +noise(x,y,70,2)*9+noise(x,y,180,17)*13)
    relief*=smooth((BASE_RADIUS+50-r)/300)
    # Small weathering rides the macro ridges; material grain supplies close detail.
    relief+=noise(x,y,32,3)*4*smooth((BASE_RADIUS-70-r)/330)
    return np.maximum(cone+relief*trail_quiet,0)

def _former_cone(x,y,trail_quiet):
    """The former summit (550, 1930), unchanged: it stands on as the western shoulder above the Mega Park."""
    dx,dy,r,angle=polar(x,y,FORMER)
    # A tangent quadratic dome rounds only the last 110 m of the summit.
    summit_radius=np.where(r<110,35+r*r/220,np.maximum(r-20,0))
    cone=510*np.maximum(0,1-summit_radius/1170)**1.55
    ridge=(.5+.5*np.cos(angle*8+.45*np.sin(angle*3)+r*.0008))**2
    ridge_band=smooth((r-140)/140)*smooth((1170-r)/280)
    rim_r=95+10*np.cos(angle-2.3)
    lift=1+.40*np.cos(angle-2.6)+.12*np.cos(2*angle+.7)+.25*noise(np.cos(angle)*300,np.sin(angle)*300,40.,91)
    breach=1.-.9*smooth((np.cos(angle-.5)-.82)/.15)
    rim=12*np.exp(-((r-rim_r)/np.where(r<rim_r,17.,48.))**2)*lift*breach
    crater=-50*smooth((rim_r-r)/60)**.85
    peaks=sum(h*np.exp(-((dx-rr*math.cos(a))**2+(dy-rr*math.sin(a))**2)/s**2)
              for a,rr,h,s in ((2.6,96,20,28),(-.35,104,9,20),(4.2,110,6,16)))
    shoulders=(72*np.exp(-((dx-290)/130)**2-((dy-90)/160)**2)
               +48*np.exp(-((dx+220)/120)**2-((dy+140)/150)**2))
    _,cuts=drainage_field(x,y,former_drainage())
    relief=((ridge*np.minimum(38.,cone*.12)-cuts*np.minimum(22.,cone*.1))*ridge_band+rim+crater+peaks+shoulders
            +noise(x,y,70,2)*9+noise(x,y,180,17)*13)
    relief*=smooth((1220-r)/230)
    relief+=noise(x,y,32,3)*4*smooth((r-35)/110)*smooth((1100-r)/250)
    return np.maximum(cone+relief*trail_quiet,0)

def caldera_floor():
    """The caldera floor's level, metres above sea level."""
    return float(apron_height(VOLCANO[1]))+CREST-DEPTH

def natural_height(x,y):
    """The foothills and volcano before the edge blend, without the Mega Park."""
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    trail_quiet=smooth((trail_distance(x,y)-15)/100)
    ground=_foothills(x,y,trail_quiet)
    target=ground+_cone(x,y,trail_quiet)
    # The caldera: a level floor DEPTH below the crest, and a wall that steepens toward the crest.
    _,_,r,angle=polar(x,y)
    crest=rim_radius(angle);foot=wall_foot(angle)
    t=np.clip((r-foot)/np.maximum(crest-12-foot,1),0,1)
    floor=caldera_floor()+.8*noise(x,y,60,95)+.5*noise(x,y,23,96)
    target=np.where(r<crest,floor+(target-floor)*t*t*(2.2-1.2*t),target)
    # Round the Mega Park the former summit's flank stands wherever it is the higher.
    sx,sy,reach,fade=MEGAPARK_SHOULDER
    keep=smooth((reach-np.hypot(x-sx,y-sy))/fade)
    on=keep>0
    if on.any():
        former=ground[on]+_former_cone(x[on],y[on],trail_quiet[on])
        target=target.copy();target[on]+=keep[on]*np.maximum(former-target[on],0)
    north=np.maximum(y-500,0)
    return 47+(target-47)*smooth(north/180)

def raw_height(x,y,base,shoulder=None):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    north=np.maximum(y-500,0)
    # The Mega Park sits in the western foothills and Crater Park on the caldera floor; the relief around each is eased
    # to meet its edges.
    target=megapark.terrain(x,y,natural_height(x,y),natural_height)
    target=craterpark.terrain(x,y,target,natural_height)
    leave=smooth(north/180)
    if shoulder is not None:
        # West of the city the far hills' shoulder (`shoulder`, the base at y=500) stood 40-60 m over the apron, a trough
        # across the Mega Park trail; the ground now leaves the shoulder within 60 m, before the far hills rise again,
        # and falls gently from it north to the foothills.
        west=smooth((420-x)/220)
        d=np.asarray(shoulder)-.11*north-target
        target=target+west*(1-smooth((y-760)/160))*(d+np.sqrt(d*d+36))/2
        leave=leave*(1-west)+smooth(north/60)*west
    # Along Belmonte's apron (belmonte/terrain.py collar) the north edge is joined as it stands, so the volcano's
    # northern foot runs on into the valley; east of the apron it eases back to the country as on the other sides.
    north_edge=1-(1-smooth((BOUNDS[3]-y)/210))*(1-smooth((belmonte.BOUNDS[2]+belmonte.APRON-x)/250))
    edge=smooth((x-BOUNDS[0])/200)*smooth((BOUNDS[2]-x)/200)*north_edge*leave
    return np.asarray(base)*(1-edge)+target*edge

@lru_cache(maxsize=4)
def surface_grid(base_sampler):
    xs=np.arange(BOUNDS[0],BOUNDS[2]+1,STEP);ys=np.arange(BOUNDS[1],BOUNDS[3]+1,STEP)
    x,y=np.meshgrid(xs,ys)
    z=raw_height(x,y,base_sampler(x,y),base_sampler(x,np.full_like(y,BOUNDS[1])))
    # The Mega Park trail's bed (megapark/trail.py) runs through the western foothills, and the Mega Park air station
    # stands on a levelled pad by the park's top road (zeppelin/layout.py).
    from megapark import trail as park_trail
    from zeppelin.layout import megapark_pad
    # Neither raises the ground under the park (megapark.terrain keeps it below the park's surfaces).
    carved=park_trail.carve(x,y,z,reach=park_trail.CARVE_COARSE[0],fade=park_trail.CARVE_COARSE[1])
    z=np.where(megapark.contains(x,y),np.minimum(z,carved),carved)
    return x,y,megapark_pad(x,y,z)

def _cell(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    ix=np.clip(np.floor((x-BOUNDS[0])/STEP).astype(int),0,int((BOUNDS[2]-BOUNDS[0])/STEP)-1)
    iy=np.clip(np.floor((y-BOUNDS[1])/STEP).astype(int),0,int((BOUNDS[3]-BOUNDS[1])/STEP)-1)
    return ix,iy,np.clip((x-BOUNDS[0])/STEP-ix,0,1),np.clip((y-BOUNDS[1])/STEP-iy,0,1)

def _barycentric(z00,z10,z01,z11,u,v):
    return np.where(u>=v,z00*(1-u)+z10*(u-v)+z11*v,z00*(1-v)+z11*u+z01*(v-u))

def height(x,y,base_sampler):
    """Barycentric sampling of the single cached grid exported as actual collision."""
    ix,iy,u,v=_cell(x,y)
    z=surface_grid(base_sampler)[2]
    return _barycentric(z[iy,ix],z[iy,ix+1],z[iy+1,ix],z[iy+1,ix+1],u,v)

def on_grid(x,y,field):
    """field(x, y) at the grid's nodes round each (x, y), sampled as height() samples the grid: what the ground would be
    if field were the grid."""
    ix,iy,u,v=_cell(x,y)
    def node(i,j):
        return field(BOUNDS[0]+i*STEP,BOUNDS[1]+j*STEP)
    return _barycentric(node(ix,iy),node(ix+1,iy),node(ix,iy+1),node(ix+1,iy+1),u,v)

def colours(x,y,z):
    """The ground's vertex colours: grass on the apron, forest green, and rock high up."""
    rock_noise=noise(x,y,26,9)*.65+noise(x,y,85,20)*.35
    radius=polar(x,y)[2]
    floor=apron_height(y)
    # Rising backdrop ground is still woodland. Exposed rock belongs to the
    # actual volcanic relief above its local apron, not an absolute elevation.
    forest=smooth((z-floor-135*LIFT+noise(x,y,125,27)*28)/(160*LIFT))*smooth((stretch(1120)-radius)/180)
    rock=np.stack([.125+.022*rock_noise,.108+.024*rock_noise,.090+.026*rock_noise],axis=-1)
    lichen=smooth((noise(x,y,12,99)-.45)/.20)
    rock*=np.stack([1+.05*lichen,1+.08*lichen,1-.15*lichen],axis=-1)
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
    t=smooth((y-(SOUTH_JOIN-420))/420)
    join=smooth(np.clip(t+t*(1-t)*noise(x,y,140,82)*.7,0,1))
    palette=np.array([.055,.11,.035])
    return colors*(1-join[...,None])+palette*join[...,None]

def shade_height(z,step):
    shade_z=z.copy()
    for _ in range(max(1,round(16/(step*step)))):
        padded=np.pad(shade_z,1,mode='edge')
        shade_z=(padded[1:-1,1:-1]+padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])/5
    return shade_z

def relief_curvature(z,step=STEP):
    dy,dx=np.gradient(shade_height(z,step),step,step)
    lap=np.gradient(dx,step,axis=1)+np.gradient(dy,step,axis=0)
    for _ in range(round(3*(10/step)**2)):
        padded=np.pad(lap,1,mode='edge')
        lap=(padded[1:-1,1:-1]+padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])/5
    return smooth((-lap-.002)/.006),smooth((lap-.001)/.005)


def snow_cover(x,y,z,step=STEP):
    """Snow in drainage hollows and the crater bowl, with bare convex crests."""
    _,_,radius,angle=polar(x,y)
    signed=np.full(x.shape,-1e9)
    pinch=.65+.35*smooth((noise(x,y,55,52)+.4)/.8)
    for a,b in drainage():
        dx,dy=b[0]-a[0],b[1]-a[1]
        t=np.clip(((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy),0,1)
        distance=np.hypot(x-a[0]-t*dx,y-a[1]-t*dy)
        # The ribbons widen with the cone, so the cap keeps its share of snow.
        width=(a[2]*(1-t)+b[2]*t)*pinch*LIFT
        signed=np.maximum(signed,np.where(width>0,np.maximum(width,3),0)-distance)
    breakup=noise(x,y,38,31)*6+noise(x,y,83,32)*4
    signed+=noise(x,y,25,19)*3+breakup*smooth((radius-stretch(170))/180)
    # Each seeded ribbon already has a different reach; this broad weather
    # field breaks the snowline without a concentric cut across every gully.
    ribbons=smooth((signed+4)/9)*smooth((stretch(520)+noise(x,y,220,51)*180-radius)/120)
    dy,dx=np.gradient(shade_height(z,step),step,step)
    nz=1/np.sqrt(1+dx*dx+dy*dy)
    crest,gully=relief_curvature(z,step)
    faces=smooth((z-lifted(400))/(90*LIFT))*smooth((nz-.80)/.10)*smooth((noise(x,y,90,41)+noise(x,y,140,42)*.6+.15)/.5)*(1-crest)
    ring=lambda r,s,seed:noise(np.cos(angle)*r,np.sin(angle)*r,s,seed)
    # The caldera floor is patchy snow over cinders; drifts gather at the wall's foot and chutes run down the wall.
    foot=wall_foot(angle);rim_r=rim_radius(angle)
    floor_r=foot-10+25*ring(240.,60.,95)
    bowl=smooth((floor_r-radius)/12)*(1-.85*smooth((noise(x,y,34,96)-.2)/.2))
    drifts=smooth((radius-foot+30)/20)*smooth((foot+25-radius)/15)
    chutes=(smooth((np.sin(angle*21+1.5*ring(400.,60.,97))-.25)/.3)
            *smooth((rim_r-14-radius)/18)*smooth((radius-foot+5)/12))
    bowl=np.maximum.reduce([bowl,drifts,chutes])
    rim=np.exp(-((radius-rim_r)/28)**2)
    inside=smooth((rim_r-20-radius)/14)
    snow=np.maximum.reduce([(ribbons*(1-.75*crest)+.35*gully*smooth((z-lifted(300))/(120*LIFT)))*(1-inside),
                            faces*(1-inside),bowl])
    snow=np.clip(snow,0,1)*(1-.92*rim*(1-bowl))
    line=lifted(230)+noise(x,y,180,83)*40*LIFT
    return np.clip(snow,0,1)*smooth((z-line)/(90*LIFT))*smooth((nz-.42)/.30)

@lru_cache(maxsize=4)
def snow_grid(base_sampler):
    xs=np.arange(SNOW_BOUNDS[0],SNOW_BOUNDS[2]+1,SNOW_STEP)
    ys=np.arange(SNOW_BOUNDS[1],SNOW_BOUNDS[3]+1,SNOW_STEP)
    x,y=np.meshgrid(xs,ys)
    cover=snow_cover(x,y,height(x,y,base_sampler),SNOW_STEP)
    # The same bytes drive the material and planting; filtering is bilinear.
    return np.rint(np.clip(cover,0,1)*255).astype(np.uint8)

def snow(x,y,base_sampler):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    field=snow_grid(base_sampler)
    px=np.clip((x-SNOW_BOUNDS[0])/SNOW_STEP,0,field.shape[1]-1.001)
    py=np.clip((y-SNOW_BOUNDS[1])/SNOW_STEP,0,field.shape[0]-1.001)
    ix=px.astype(int);iy=py.astype(int);u=px-ix;v=py-iy
    value=((field[iy,ix].astype(float)*(1-u)+field[iy,ix+1]*u)*(1-v)
           +(field[iy+1,ix]*(1-u)+field[iy+1,ix+1]*u)*v)/255.
    inside=(x>=SNOW_BOUNDS[0])&(x<=SNOW_BOUNDS[2])&(y>=SNOW_BOUNDS[1])&(y<=SNOW_BOUNDS[3])
    return np.where(inside,value,0.)

def export_snow_mask(output,base_sampler):
    """Linear R8 PNG, row zero at minimum world y, sampled at texel centres."""
    import json,struct,zlib
    field=snow_grid(base_sampler)
    assert not any(np.any(edge) for edge in (field[0],field[-1],field[:,0],field[:,-1])),'Snow mask clips its footprint'
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+row.tobytes() for row in field)
    png=(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',field.shape[1],field.shape[0],8,0,0,0,0))
         +chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))
    (output/'north_snow.png').write_bytes(png)
    meta={'bounds':SNOW_BOUNDS,'step_m':SNOW_STEP,'size':[field.shape[1],field.shape[0]],
          'linear':True,'row_zero_world_y':SNOW_BOUNDS[1],'filter':'bilinear, clamp, texel-centred',
          # The ground material's exposed-rock band (mountain_material.py) and its join to Belmonte's palette.
          'volcano_m':list(VOLCANO),'rock_radius_m':[float(stretch(940)),float(stretch(1120))],
          'rock_prominence_m':[130*LIFT,250*LIFT],'south_join_m':SOUTH_JOIN}
    (output/'north_snow.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('NORTH SNOW MASK',field.shape,len(png),'bytes',flush=True)

def mesh(base_sampler):
    xs=np.arange(BOUNDS[0],BOUNDS[2]+1,STEP);ys=np.arange(BOUNDS[1],BOUNDS[3]+1,STEP)
    x,y,z=surface_grid(base_sampler)
    colors=colours(x,y,z)
    crest,gully=relief_curvature(z)
    _,_,radius,angle=polar(x,y)
    prominence=z-apron_height(y)
    exposed=smooth((prominence-135*LIFT)/(120*LIFT))*smooth((stretch(1120)-radius)/180)
    cavity=(1-.45*gully)*(1+.15*crest)
    rim=np.exp(-((radius-rim_radius(angle))/40)**2)
    colors*=((1-exposed)+exposed*cavity*(1-.35*rim))[...,None]
    dy,dx=np.gradient(z,STEP,STEP)
    normals=np.stack([-dx,-dy,np.ones_like(z)],-1)
    normals/=np.linalg.norm(normals,axis=-1,keepdims=True)
    # Soft continuous snow masks replace hard clipped lavender polygons.
    mask=snow(x,y,base_sampler)
    # The gate's finer patch replaces these cells by the Mega Park's air station (megapark/gate.py, HD_NorthGate).
    from megapark import gate
    faces=[]
    width=len(xs)
    for j in range(len(ys)-1):
        for i in range(len(xs)-1):
            if gate.cell_inside(x[j,i],y[j,i],STEP):continue
            a=j*width+i;b=a+1;c=a+width+1;d=a+width
            faces.extend([(a,b,c),(a,c,d)])
    faces=np.asarray(faces,dtype=np.int32)
    used=np.unique(faces);remap=np.full(x.size,-1,dtype=np.int32);remap[used]=np.arange(len(used))
    return dict(vertices=np.stack([x,y,z],-1).reshape(-1,3)[used],faces=remap[faces],
                colours=np.dstack([colors,mask]).reshape(-1,4)[used],normals=normals.reshape(-1,3)[used])


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
