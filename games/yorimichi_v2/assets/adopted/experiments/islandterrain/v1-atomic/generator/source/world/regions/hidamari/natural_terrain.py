"""Natural northern terrain math, independent of railway deformation, scenery and export.

The sampling lattice and numerical operations are shared with the final mountain surface. Crater Park
consumes this kernel directly, so unrelated station/export implementations are not its source inputs.
"""
import math
from functools import lru_cache
import numpy as np
from craterpark.v2 import v4_config

GRID_ORIGIN = (-700., 500.)

STEP = 5.
VOLCANO = (850., 2400.)     # centre, Blender metres (x east, y north)
BASE_RADIUS = 1480.         # where the cone meets the foothills
RIM_RADIUS = 470.           # mean radius of the crest; it wanders by about 35 m
FLOOR_RADIUS = 330.
CRAG_STEP = 16.                 # metres between the inner wall's ledges
LOW_STRETCH = 245.              # degrees (from east, counter-clockwise): the crest's lowest stretch, level with the park's deck
CREST = 600.                # the cone's height over its apron at the crest
DEPTH = 45.                 # the floor lies this far below the crest: Crater Park stands high in it, its tallest
FORMER = (550., 1930.)
MEGAPARK_SHOULDER = (-150., 1300., 1150., 450.)    # x, y, radius where the former cone is kept in full, fade
LIFT = 1.35
TRAIL = [(1120,335),(1120,440),(1120,500),(1100,555),(1040,620),
         (1030,680),(1090,735),(1170,780),(1200,850),(1160,915),
         (1080,960),(1000,1020),(1010,1090),(1060,1130)]

def smooth(t):
    t=np.clip(t,0,1)
    return t*t*(3-2*t)

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
    # The crest breaks into crags and notches (the targets' jagged rim): ridged noise round the ring, about zero mean,
    # gathered by a slow envelope so a few sharp peaks stand among broad shoulders. Narrow even teeth read as a comb.
    around=lambda s,seed:noise(np.cos(angle)*RIM_RADIUS,np.sin(angle)*RIM_RADIUS,s,seed)
    gather=smooth((around(160.,65)+.2)/.6)
    teeth=((1-np.abs(around(55.,63)))**2*30+(1-np.abs(around(19.,64)))**2*8-15)*(.25+.75*gather)
    # The rim's lowest stretch, which the park's deck looks out over (LOW_STRETCH), keeps notches but no crags.
    away=np.abs(np.angle(np.exp(1j*(angle-math.radians(LOW_STRETCH)))))
    teeth=np.where(teeth>0,teeth*smooth((away-.25)/.3),teeth)
    lip=lip+teeth*np.exp(-((r-crest)/np.where(r<crest,35.,70.))**2)*breach
    peaks=sum(h*np.exp(-((dx-rr*math.cos(a))**2+(dy-rr*math.sin(a))**2)/s**2)
              for a,rr,h,s in ((2.6,RIM_RADIUS+5,42,50),(-.35,RIM_RADIUS+10,20,36),(4.2,RIM_RADIUS+12,14,30)))
    shoulders=(100*np.exp(-((dx-400*k)/(130*k))**2-((dy-90*k)/(160*k))**2)
               +60*np.exp(-((dx+300*k)/(120*k))**2-((dy+190*k)/(150*k))**2))
    relief=((ridge*np.minimum(52.,cone*.12)-cuts*np.minimum(30.,cone*.1))*ridge_band+lip+peaks+shoulders
            +noise(x,y,70,2)*9+noise(x,y,180,17)*13)
    relief*=smooth((BASE_RADIUS+50-r)/300)
    # Granite ribs down the upper flank (g_zep, f_city2): ridged noise long downslope and about 20 m across, so snow
    # gathers in the gullies between them. Faded in below the crest, which keeps its height.
    rib=(1-np.abs(downslope_noise(r,angle,22.,68,.15)))**2+.5*(1-np.abs(downslope_noise(r,angle,9.,69,.2)))**2-.62
    relief+=rib*16*smooth((r-crest-12)/25)*smooth((crest+260-r)/120)
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
    depth = DEPTH
    if v4_config.selected():
        depth = v4_config.caldera_depth(DEPTH)
    return float(apron_height(VOLCANO[1]))+CREST-depth

def natural_height(x,y):
    """@cc [owner:fontanierh,label:correctness] natural-mountain-kernel
    Preserve the existing natural-height evaluation order, seeded drainage and selected caldera depth.
    This kernel MUST NOT depend on railway carving, source meshes, scenery or final export code.
    """
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
    # Crags: the inner wall steps down in cliff bands and ledges (the targets' broken granite), the bands warped and
    # tilted by noise so none reads as a ring. Each band is a ledge for 60 per cent of its height, then a steep riser.
    wall=smooth((r-foot-8)/15)*smooth((crest-6-r)/12)*(r<crest)
    # Strongly warped (half to one band over 45 m), and blended at 70 per cent, so the bands break into crags rather
    # than reading as a quarry's even benches.
    warped=target+noise(x,y,45,66)*16+noise(x,y,17,67)*6
    band=CRAG_STEP;k=np.floor(warped/band);f=warped/band-k
    target=target+((k+smooth((f-.6)/.4))*band-warped)*wall*.7
    # Round the Mega Park the former summit's flank stands wherever it is the higher.
    sx,sy,reach,fade=MEGAPARK_SHOULDER
    keep=smooth((reach-np.hypot(x-sx,y-sy))/fade)
    on=keep>0
    if on.any():
        former=ground[on]+_former_cone(x[on],y[on],trail_quiet[on])
        target=target.copy();target[on]+=keep[on]*np.maximum(former-target[on],0)
    north=np.maximum(y-500,0)
    return 47+(target-47)*smooth(north/180)

def _barycentric(z00,z10,z01,z11,u,v):
    return np.where(u>=v,z00*(1-u)+z10*(u-v)+z11*v,z00*(1-v)+z11*u+z01*(v-u))


def downslope_noise(radius,angle,scale,seed,stretch=.3,arc=470.):
    """noise() in the cone's polar frame, stretched along the radius (downslope); two wraps blended so neither seam shows."""
    other=np.where(angle<0,angle+math.tau,angle)
    w=smooth((np.abs(angle)-1.2)/.8)
    return noise(radius*stretch,angle*arc,scale,seed)*(1-w)+noise(radius*stretch,other*arc,scale,seed)*w

