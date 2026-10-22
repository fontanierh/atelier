"""Temple gardens and station forecourt from the September 8 reference sheet."""
import math
import random
from functools import partial
from village import build as v
from hidamari import living_plaza, pond_garden
from hidamari.kit import station
surface_patch=partial(living_plaza.patch,cell=.25)

from hidamari.public_spaces import TEMPLES, STATION_GARDENS


def garden_patch(m,x,y,w,d,height,seed):
    rng=random.Random(seed)
    reserved=lambda xx,yy: (-11.4<xx<-6.6 and -24<yy<-20) or (-7.6<xx<-1.6 and -23.2<yy<-20.8) or any((xx-tx)**2+(yy-ty)**2<1.2**2 for tx,ty in [(-11,-28),(11,-25)])
    surface_patch(m,x,y,w,d,height,'civic_gravel',.045)
    # Sparse, broad pebbles stay subordinate to the rocks and plants.
    for i in range(round(w*d*2)):
        xx=x+rng.uniform(-w/2,w/2);yy=y+rng.uniform(-d/2,d/2)
        if reserved(xx,yy):continue
        z=float(height(xx,yy))+.055
        m.lathe((xx,yy,z),[(0,.07),(.035,.085),(.075,.035),(.08,0)],'pond_rock_light',5)
    # Group planting around larger stones; leave visible open gravel between pockets.
    from hidamari import plaza
    for px,py in [(-2.8,-4.8),(-1.,1.6),(2.6,4.6),(2.7,-2.8),(-2.5,4.8)]:
        cx,cy=x+px,y+py
        size=rng.uniform(.8,1.35)
        if not reserved(cx,cy):
            z=min(float(height(cx+dx,cy+dy)) for dx in [-size,size] for dy in [-size,size])-.09
            pond_garden.rock(m,cx,cy,z,size,rng)
        for i in range(18):
            angle=rng.random()*math.tau;radius=rng.uniform(.75,1.75)
            xx=cx+math.cos(angle)*radius;yy=cy+math.sin(angle)*radius
            if abs(xx-x)>w*.47 or abs(yy-y)>d*.47 or reserved(xx,yy):continue
            z=float(height(xx,yy))+.025;h=rng.uniform(.25,.60);r=rng.uniform(.18,.36)
            m.lathe((xx,yy,z-.04),[(0,r*.55),(h*.4,r),(h*.85,r*.65),(h,0)],'garden_leaf',7)
            if i%2:plaza.bloom(m,xx,yy,z+h-.025,.12,'arc_leaf' if i%3==0 else 'arc_ivory')


def basin(m,x,y,height):
    levels=[float(height(x+dx,y+dy)) for dx in [-1.4,1.4] for dy in [-1.,1.]]
    z=max(levels)+.05;bottom=min(levels)-.05
    m.box((x,y,(bottom+z)/2),(2.8,2.,z-bottom),'pond_rock')
    # A solid basin rests on a stone plinth; the water is recessed below its rim.
    m.box((x,y,z+.12),(2.7,1.9,.24),'pond_rock',.08)
    m.box((x,y,z+.56),(2.4,1.6,.70),'pond_rock_light',.12)
    m.box((x,y,z+.94),(2.12,1.31,.08),'soil')
    m.box((x,y,z+.99),(1.86,1.05,.015),'civic_water')
    for dx in [-1.12,1.12]:m.box((x+dx,y,z+1.01),(.20,1.6,.20),'pond_rock_light')
    for dy in [-.7,.7]:m.box((x,y+dy,z+1.01),(2.4,.20,.20),'pond_rock_light')
    for dx in [-1.8,1.8]:living_plaza.ground_post(m,x+dx,y, z+3.9,.17,.17,'arc_timber',height,base_offset=.04)
    for side in [-1,1]:
        pts=[(x-2.2,y,z+3.9),(x+2.2,y,z+3.9),(x+2.2,y+side*1.55,z+3.35),(x-2.2,y+side*1.55,z+3.35)]
        m.poly(pts,'roof');m.poly(pts[::-1],'roof')
        m.beam(pts[2],pts[3],.13,.16,'arc_trim')
    m.beam((x-2.2,y,z+3.9),(x+2.2,y,z+3.9),.17,.17,'arc_timber')
    for dx in [-.65,.65]:
        m.beam((x+dx,y-.65,z+1.18),(x+dx,y+.65,z+1.18),.045,.045,'arc_trim')
        m.lathe((x+dx,y+.38,z+1.18),[(0,.13),(.12,.15),(.15,.13)],'arc_trim',8)


def temple_ground(m,cx,cy,yaw,height,seed):
    a=math.radians(yaw)
    def local_height(x,y):return height(cx+x*math.cos(a)-y*math.sin(a),cy+x*math.sin(a)+y*math.cos(a))
    with m.at((cx,cy,0),yaw):
        for x in [-8,8]:garden_patch(m,x,-24,10,15,local_height,seed+int(x))
        # Four metre central route meets the original shallow veranda steps.
        surface_patch(m,0,-24,4,20,local_height,'civic_gravel',.054)
        for y in range(-34,-14):
            for x in [-1.5,-.5,.5,1.5]:
                surface_patch(m,x,y+.5,.96,.96,local_height,'civic_paving',.06)
        for x in [-3.2,3.2]:
            for y in [-31,-18]:
                levels=[local_height(x+dx,y+dy) for dx in [-.53,.53] for dy in [-.53,.53]]
                z=max(levels)+.045;bottom=min(levels)-.04
                m.box((x,y,(z+bottom)/2),(1.06,1.06,z-bottom),'pond_rock')
                pond_garden.lantern(m,x,y,z)
        surface_patch(m,-4.7,-22,5.4,1.8,local_height,'civic_paving',.065)
        basin(m,-9,-22,local_height)
        # Low rope edging protects planting while leaving the centre and sides open.
        for x in [-13.4,13.4]:
            for y in [-32,-28,-24,-20,-16]:
                z=local_height(x,y);m.lathe((x,y,z),[(0,.09),(.85,.09),(.91,.11),(.91,0)],'arc_timber',8)
                if y<-16:m.beam((x,y,z+.71),(x,y+4,local_height(x,y+4)+.71),.025,.025,'arc_trim')
        # Fallen leaves lie on the gravel rather than floating at one global height.
        rng=random.Random(seed)
        for i in range(280):
            xx=rng.uniform(-13,13);yy=rng.uniform(-33,-15)
            if abs(xx)<2.3:continue
            z=local_height(xx,yy)+.063
            m.poly([(xx-.1,yy,z),(xx,yy-.08,z),(xx+.12,yy,z),(xx,yy+.13,z)],'arc_leaf')


def map_board(m,height,city,lettering):
    x,y=1169.,270.;z=float(height(x,y))+.13
    for dx in [-1.85,1.85]:living_plaza.ground_post(m,x+dx,y,z+3.28,.17,.17,'arc_timber',height,base_offset=.13)
    m.box((x,y,z+1.65),(3.9,.18,2.3),'arc_timber')
    m.box((x-.55,y-.11,z+1.62),(2.6,.06,1.85),'civic_map')
    m.box((x+1.2,y-.11,z+1.62),(.75,.06,1.85),'arc_ivory')
    # Actual city road layout in miniature, not fabricated readable map content.
    def to_panel(px,py):return (x-1.78+(px-300)/1020*2.42,y-.16,z+.81+(py+260)/690*1.55)
    for path in city['roads']:
        for aa,bb in zip(path[::10],path[10::10]):
            if not (300<=aa[0]<=1320 and -260<=aa[1]<=430):continue
            m.beam(to_panel(aa[0],aa[1]),to_panel(bb[0],bb[1]),.010,.012,'arc_ivory')
    for px,py in [(730,175),(1030,284),(1185,290)]:
        xx,yy,zz=to_panel(px,py);m.box((xx,yy-.015,zz),(.065,.015,.065),'canvas_rust')
    for row in range(9):
        for col in range(3):m.box((x+.94+col*.23,y-.16,z+.93+row*.14),(.16,.015,.025),'arc_timber')
    lettering(m,'ひだまり',(x,y-.13,z+2.68),.32,color='arc_ivory')
    m.beam((x-2.2,y,z+3.28),(x+2.2,y,z+3.28),.14,.14,'arc_timber')
    for side in [-1,1]:
        pts=[(x-2.2,y,z+3.28),(x+2.2,y,z+3.28),(x+2.2,y+side*.78,z+2.91),(x-2.2,y+side*.78,z+2.91)]
        m.poly(pts,'roof');m.poly(pts[::-1],'roof')
        m.beam(pts[2],pts[3],.10,.10,'arc_trim')


def build(height,city,lettering):
    living_plaza.palette();station.palette(0)
    v.PALETTE.update({'pond_rock':(.105,.13,.115),'pond_rock_light':(.18,.20,.16),'pond_moss':(.095,.17,.035),
      'civic_gravel':(.30,.255,.18),'civic_paving':(.39,.35,.27),'civic_water':(.025,.12,.11),'civic_map':(.18,.28,.13)})
    m=v.Mesh('HD_CivicGardens')
    for i,(x,y,yaw) in enumerate(TEMPLES):temple_ground(m,x,y,yaw,height,710+i)
    surface_patch(m,1185,263,54,26,height,'civic_gravel',.124)
    for x in range(1158,1212,2):
        for y in range(250,276,2):surface_patch(m,x+1,y+1,1.96,1.96,height,'civic_paving',.13)
    surface_patch(m,1185,263,.62,26,height,'st_tactile',.145)
    for i,(x,y,w,d,_) in enumerate(STATION_GARDENS):living_plaza.raised_bed(m,x,y,w,d,height,850+i)
    map_board(m,height,city,lettering)
    # Wheels lie east/west along level ground, rather than across the slope.
    for y in [270.,271.,272.]:station.bike(m,1201,y,float(height(1201,y))+.13,90,'st_dark')
    for y in [269.5,272.5]:living_plaza.ground_post(m,1201,y,float(height(1201,y))+.85,.07,.07,'metal',height,base_offset=.13)
    m.beam((1201,269.5,float(height(1201,269.5))+.85),(1201,272.5,float(height(1201,272.5))+.85),.07,.07,'metal')
    m.colliders=[]
    return m
