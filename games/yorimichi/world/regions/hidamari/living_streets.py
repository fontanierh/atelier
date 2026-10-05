"""Human-scale street details matching the reference, with a clear carriageway."""
import math
import random
from village import build as v
from hidamari import layout, living_plaza, arcade
from hidamari.kit import station

# Two targeted ordinary-street stretches, outside the finished pedestrian arcade/plaza.
from hidamari.public_spaces import STREET_GARDENS


def tree(m,x,y,z,seed):
    r=random.Random(seed)
    m.lathe((x,y,z),[(0,.13),(2.2,.10),(4.1,.025),(4.12,0)],'arc_timber',9)
    m.collider((x,y,z+1.5),(.28,.28,3))
    for k in range(7):
        a=k*2.4;cx=x+math.cos(a)*1.05;cy=y+math.sin(a)*.52;cz=z+2.8+(k%3)*.5
        m.beam((x,y,z+1.9+k*.17),(cx,cy,cz),.055,.055,'arc_timber')
        for j in range(80):
            a=r.random()*math.tau;rad=math.sqrt(r.random());xx=cx+math.cos(a)*rad*.72;yy=cy+math.sin(a)*rad*.40;zz=cz+r.uniform(-.28,.38)
            size=r.uniform(.09,.15);col=r.choice([(.82,.44,.015),(.70,.33,.008),(.92,.54,.03)])
            with m.at((xx,yy,zz),r.random()*360):
                pts=[(0,-size,0),(-size,0,0),(-size*.7,size,.035),(0,size*1.2,.05),(size*.7,size,.035),(size,0,0)]
                tilt_x=r.uniform(-1.0,1.0);tilt_y=r.uniform(-.8,.8)
                from mathutils import Euler, Vector
                rotation=Euler((tilt_x,tilt_y,0)).to_matrix()
                pts=[rotation@Vector(p) for p in pts]
                m.poly(pts,col);m.poly(pts[::-1],col)


def garden(m,x,y,side,height,seed):
    top=max(float(height(x+dx,y+dy)) for dx in [-1.9,1.9] for dy in [-.7,.7])+.55
    low=min(float(height(x+dx,y+dy)) for dx in [-1.9,1.9] for dy in [-.7,.7])+.035
    m.box((x,y,(low+top)/2),(3.8,1.4,top-low),'garden_stone',.04)
    m.box((x,y,top),(3.95,1.55,.12),'garden_cap',.035)
    m.box((x,y,top+.06),(3.58,1.18,.04),'soil');m.collider((x,y,(low+top)/2),(3.95,1.55,top-low+.12))
    tree(m,x,y,top+.09,seed)
    r=random.Random(seed)
    for i in range(24):
        xx=x+r.uniform(-1.65,1.65);yy=y+r.uniform(-.47,.47)
        if abs(xx-x)<.3:continue
        m.lathe((xx,yy,top+.08),[(0,.07),(.17,.18),(.30,.09),(.30,0)],'garden_leaf',6)
        from hidamari import plaza
        plaza.bloom(m,xx,yy,top+.38,.13,'arc_ivory' if i%3 else 'arc_bloom')
    # A separate narrow bench beside the planting, facing the passing street.
    bx=x+(-3.7 if x==546 else 3.7);seat=float(height(bx,y))+.08+.46
    for xx in [bx-1.1,bx+1.1]:living_plaza.ground_post(m,xx,y,seat,.14,.52,'arc_timber',height,base_offset=.07)
    for j in range(3):m.box((bx,y-.19+j*.19,seat),(2.8,.165,.08),'arc_trim',.01)
    m.collider((bx,y,seat-.23),(2.8,.56,.54))
    # Supported, double-sided ginkgo banner: no floating cloth.
    lx=x-2.65;lz=float(height(lx,y))+.08
    m.box((lx,y,lz+1.9),(.13,.13,3.8),'arc_timber');m.collider((lx,y,lz+1.9),(.17,.17,3.8))
    m.beam((lx,y,lz+3.5),(lx+.8,y,lz+3.5),.06,.06,'arc_trim')
    m.box((lx,y,lz+3.8),(.44,.44,.08),'arc_timber')
    m.box((lx,y,lz+4.04),(.30,.30,.40),'arc_paper')
    for dx in [-.19,.19]:
        for dy in [-.19,.19]:m.box((lx+dx,y+dy,lz+4.04),(.045,.045,.42),'arc_timber')
    m.lathe((lx,y,lz+4.27),[(0,.35),(.23,0)],'arc_roof',4)
    for ss in [-1,1]:
        p=[(lx+.15,y+ss*.014,lz+3.46),(lx+.75,y+ss*.014,lz+3.46),(lx+.75,y+ss*.014,lz+2.02),(lx+.15,y+ss*.014,lz+2.02)]
        m.poly(p if ss<0 else p[::-1],'street_banner')
        m.poly([(lx+.45,y+ss*.025,lz+2.48),(lx+.19,y+ss*.025,lz+2.79),(lx+.3,y+ss*.025,lz+2.98),(lx+.6,y+ss*.025,lz+2.98),(lx+.70,y+ss*.025,lz+2.79)],'arc_leaf')


def add(m,city,height,road_x,road_y):
    living_plaza.palette();station.palette(0)
    v.PALETTE.update({'street_paver':(.35,.30,.23),'street_gutter':(.025,.032,.028),'street_line':(.30,.265,.19),'street_banner':(.17,.17,.30)})
    def excluded(x,y):return (660<x<805 and 122<y<218) or (589<x<727 and 65<y<85)
    r=random.Random(499)
    # Broad readable tile joints, flush kerbs and gutters; no extra trip geometry.
    for cy in road_y:
        for x in range(398,1248,2):
            if excluded(x+1,cy) or min(abs(x+1-c)-layout.road_width(x=c)[0] for c in road_x)<1:continue
            for side in [-1,1]:
                living_plaza.patch(m,x+1,cy+side*5.85,2.04,4.05,height,'street_gutter',.074)
                for band in range(3):
                    yy=cy+side*(4.50+band*1.35)
                    living_plaza.patch(m,x+1,yy,1.96,1.29,height,(.25+r.uniform(-.025,.025),.205,.135),.080)
                living_plaza.patch(m,x+1,cy+side*3.95,2,.22,height,'street_gutter',.084)
                if x%6==0:
                    for j in range(5):living_plaza.patch(m,x+.2+j*.17,cy+side*3.95,.055,.20,height,'metal',.087)
                living_plaza.patch(m,x+1,cy+side*3.57,2,.09,height,'street_line',.083)
        for cx in road_x:
            if excluded(cx,cy):continue
            for side in [-1,1]:
                for y in [-2.7,-1.8,-.9,0,.9,1.8,2.7]:
                    living_plaza.patch(m,cx+side*(layout.road_width(x=cx)[0]+2.2),cy+y,2.15,.40,height,'street_line',.086)
    for i,(x,y,side) in enumerate(STREET_GARDENS):garden(m,x,y,side,height,400+i)
    # Two bicycle pockets use the existing detailed bicycle kit at actual pavement.
    for x,y in [(510,133.4),(983,236.6)]:
        z=float(height(x,y))+.08
        for k in range(2):
            xx=x+k*.8
            station.bike(m,xx,y,float(height(xx,y))+.08,0,'st_dark')
            for dy in [-.35,.35]:living_plaza.ground_post(m,xx,y+dy,z+.6,.055,.055,'metal',height,base_offset=.08)
            m.beam((xx,y-.35,z+.6),(xx,y+.35,z+.6),.055,.055,'metal')
        m.collider((x+.4,y,z+.5),(1.4,1.95,1.))
    m.colliders=[]  # Keep the existing street surface as complex-as-simple collision.
    return m
