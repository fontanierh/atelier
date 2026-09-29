"""Ground-conforming plaza furniture based on the September 8 image-gen target."""
import math
import random
import numpy as np
from village import build as v
from hidamari import plaza, arcade
from hidamari.public_spaces import PLAZA_GARDENS, PLAZA_STALLS, PLAZA_CAFE


def palette():
    plaza.palette()
    v.PALETTE.update({'garden_stone':(.34,.30,.245),'garden_cap':(.46,.40,.31),
        'canvas_cream':(.73,.62,.44),'canvas_rust':(.50,.22,.105),
        'garden_leaf':(.18,.245,.085),'fruit_red':(.64,.105,.042),
        'fruit_gold':(.87,.45,.035),'paver_dark':(.085,.067,.046)})


def ground_post(m,x,y,top,w,d,key,height,base_offset=.13):
    bottom=float(height(x,y))+base_offset-.025
    m.box((x,y,(bottom+top)/2),(w,d,top-bottom),key)


def patch(m,x,y,w,d,height,key,offset=.15,cell=1.):
    # Small cells follow slope and plateau boundaries without hovering corners.
    nx=max(1,math.ceil(w/cell));ny=max(1,math.ceil(d/cell))
    xs=x-w/2+np.arange(nx+1)*w/nx;ys=y-d/2+np.arange(ny+1)*d/ny
    gx,gy=np.meshgrid(xs,ys)
    # Height queries evaluate every building plateau. Batch the grid rather
    # than evaluating that complete field separately for every polygon corner.
    gz=np.asarray(height(gx,gy))+offset
    if gz.ndim==0:gz=np.full(gx.shape,float(gz))
    for ix in range(nx):
        for iy in range(ny):
            m.poly([(float(gx[j,i]),float(gy[j,i]),float(gz[j,i])) for i,j in [(ix,iy),(ix+1,iy),(ix+1,iy+1),(ix,iy+1)]],key)


def border(m,x,y,w,d,height):
    for s in (-1,1):
        patch(m,x+s*w/2,y,.42,d,height,'paver_dark',.157)
        patch(m,x,y+s*d/2,w+.42,.42,height,'paver_dark',.157)


def raised_bed(m,x,y,w,d,height,seed=0):
    r=random.Random(seed);top=max(float(height(x+a*w/2,y+b*d/2)) for a in (-1,1) for b in (-1,1))+.67
    low=min(float(height(x+a*w/2,y+b*d/2)) for a in (-1,1) for b in (-1,1))+.10
    m.box((x,y,(top+low)/2),(w,d,top-low),'garden_stone',.045)
    m.collider((x,y,(top+low)/2),(w,d,top-low))
    m.box((x,y,top),(w+.13,d+.13,.16),'garden_cap',.04)
    m.box((x,y,top+.09),(w-.30,d-.30,.07),'soil')
    for side in (-1,1):
        for j in range(math.ceil(w/.85)):
            xx=x-w/2+(j+.5)*w/math.ceil(w/.85)
            m.box((xx,y+side*(d/2+.005),top-.24),(w/math.ceil(w/.85)-.035,.02,.32),'garden_cap' if j%3 else 'garden_stone')
    # Flower roots meet soil; avoid the central tree trunk and built-in bench.
    for i in range(round(w*d*5)):
        xx=x+r.uniform(-w*.44,w*.44);yy=y+r.uniform(-d*.40,d*.40)
        if abs(xx-x)<.65 and abs(yy-y)<.65:continue
        z=top+.12;h=r.uniform(.22,.45)
        m.lathe((xx,yy,z),[(0,.025),(.13,.20),(h,.08),(h+.02,0)],'garden_leaf',6)
        m.beam((xx,yy,z),(xx,yy,z+h+.07),.025,.025,'green_dark')
        plaza.bloom(m,xx,yy,z+h,.105,r.choice(['arc_ivory','arc_bloom','arc_rose']))
    # Seat uses the planter wall for its back; independent feet reach local paving.
    yy=y-d/2-.48;seat=float(height(x,yy))+.13+.48
    for xx in (x-w*.34,x+w*.34):ground_post(m,xx,yy,seat,.20,.62,'arc_timber',height)
    for j in range(4):m.box((x,yy-.25+j*.17,seat),(w-.45,.145,.09),'arc_trim',.012)
    m.collider((x,yy,seat-.23),(w-.45,.75,.5))
    return top+.12


def parasol(m,x,y,z,r=2.45):
    m.lathe((x,y,z),[(0,.32),(.10,.32),(.14,.20),(.14,0)],'garden_stone',8)
    m.beam((x,y,z+.08),(x,y,z+3.65),.09,.09,'arc_timber')
    for i in range(10):
        a=i*math.tau/10;b=(i+1)*math.tau/10
        pts=[(x,y,z+3.65),(x+r*math.cos(a),y+r*math.sin(a),z+2.95),(x+r*math.cos(b),y+r*math.sin(b),z+2.95)]
        m.poly(pts,'canvas_cream');m.poly(pts[::-1],'canvas_cream')
        m.beam(pts[0],pts[1],.035,.035,'arc_trim')
        m.poly([pts[1],pts[2],(pts[2][0],pts[2][1],z+2.76),(pts[1][0],pts[1][1],z+2.76)],'canvas_cream')
    m.collider((x,y,z+1.6),(.15,.15,3.2))


def cafe_table(m,x,y,height):
    z=float(height(x,y))+.14
    parasol(m,x,y,z)
    m.lathe((x,y,z),[(0,.30),(.06,.30),(.09,.09),(.78,.09),(.80,.85),(.89,.85),(.89,0)],'arc_trim',16)
    m.collider((x,y,z+.45),(1.7,1.7,.90))
    for angle in (0,120,240):
        a=math.radians(angle);xx=x+1.32*math.cos(a);yy=y+1.32*math.sin(a);seat=float(height(xx,yy))+.61
        # Seat, legs and back share one local frame facing the table. Ground
        # height is still sampled at each transformed foot on sloped paving.
        heading=math.radians(angle-90)
        def chair_ground(lx,ly):
            return height(xx+lx*math.cos(heading)-ly*math.sin(heading),yy+lx*math.sin(heading)+ly*math.cos(heading))
        with m.at((xx,yy,0),angle-90):
            for dx in (-.22,.22):
                for dy in (-.22,.22):ground_post(m,dx,dy,seat,.07,.07,'arc_timber',chair_ground)
            m.box((0,0,seat),(.64,.64,.09),'arc_trim',.02)
            for bx in (-.23,.23):m.beam((bx,.28,seat),(bx,.28,seat+.52),.06,.06,'arc_timber')
            m.box((0,.28,seat+.38),(.62,.10,.28),'arc_trim',.02)
            m.collider((0,0,seat-.22),(.65,.65,.6))
    for dx in (-.45,.4):
        m.lathe((x+dx,y,z+.89),[(0,.12),(.13,.13),(.16,.14)],'arc_ivory',12)
        m.poly([(x+dx+.10*math.cos(i*math.tau/12),y+.10*math.sin(i*math.tau/12),z+1.045) for i in range(12)],'soil')


def market_stall(m,x,y,height,variant,lettering):
    z=max(float(height(x+dx,y+dy)) for dx in (-2.3,2.3) for dy in (-1.6,1.6))+.14
    key='canvas_cream' if variant==1 else 'canvas_rust'
    for dx in (-2.15,2.15):
        for dy in (-1.35,1.35):
            ground_post(m,x+dx,y+dy,z+2.70,.15,.15,'arc_timber',height)
            bottom=float(height(x+dx,y+dy))+.13
            m.collider((x+dx,y+dy,(bottom+z+2.70)/2),(.19,.19,z+2.70-bottom))
    for side in (-1,1):
        pts=[(x-2.6,y,z+3.35),(x+2.6,y,z+3.35),(x+2.6,y+side*1.9,z+2.55),(x-2.6,y+side*1.9,z+2.55)]
        m.poly(pts,key);m.poly(pts[::-1],key)
        m.beam(pts[2],pts[3],.10,.10,'arc_trim')
        m.poly([pts[2],pts[3],(x-2.6,y+side*1.9,z+2.37),(x+2.6,y+side*1.9,z+2.37)],key)
    m.beam((x-2.6,y,z+3.35),(x+2.6,y,z+3.35),.12,.12,'arc_trim')
    # Front faces toward the open southern forecourt; each counter foot is grounded.
    yy=y-1.05;counter=float(height(x,yy))+.98
    for xx in (x-1.75,x+1.75):ground_post(m,xx,yy,counter,.16,.62,'arc_timber',height)
    m.box((x,yy,counter),(4.2,.92,.16),'arc_trim',.025)
    m.collider((x,yy,(counter+float(height(x,yy))+.13)/2),(4.2,.92,counter-float(height(x,yy))-.13))
    for i in range(15):
        m.box((x-1.96+i*.28,yy-.47,counter-.35),(.25,.07,.65),'arc_trim')
    for i in range(3):
        xx=x-1.4+i*1.4
        m.box((xx,yy,counter+.18),(1.25,.78,.20),'arc_timber')
        for k in range(8):
            px=xx-.45+(k%4)*.29;py=yy-.19+(k//4)*.36
            m.lathe((px,py,counter+.29),[(0,.10),(.09,.15),(.20,.11),(.24,.025),(.245,0)],['fruit_red','fruit_gold','garden_leaf'][(variant+i)%3],8)
    m.box((x,y+1.25,z+1.7),(3.8,.24,.11),'arc_trim')
    for i in range(6):v.pot(m,x-1.5+i*.60,y+1.25,z+1.755,.33,'clay')
    m.box((x,y-1.93,z+2.40),(2.25,.10,.44),'arc_timber',.025)
    lettering(m,['やさい','お茶','くだもの'][variant],(x,y-2,z+2.24),.40,color='arc_ivory')


def furniture(height,lettering):
    palette();m=v.Mesh('HD_Square')
    for i,(x,y,w,d,orange) in enumerate(PLAZA_GARDENS):
        raised_bed(m,x,y,w,d,height,i+81);border(m,x,y,w+2.4,d+2.5,height)
    for x,y in PLAZA_CAFE:cafe_table(m,x,y,height)
    for x,y,var in PLAZA_STALLS:market_stall(m,x,y,height,var,lettering)
    for x,y in [(709,134),(750,131),(780,156),(692,185),(773,199)]:
        z=float(height(x,y))+.13;plaza.lantern_post(m,x,y,z)
        # Supported autumn pennant on the side of the pole.
        m.beam((x,y,z+3.1),(x+.95,y,z+3.1),.06,.06,'metal')
        m.poly([(x+.18,y,z+3.08),(x+.88,y,z+3.08),(x+.88,y,z+1.65),(x+.53,y,z+1.8),(x+.18,y,z+1.65)],'canvas_rust')
    # Deliberate paving frames shape the open space without adding trip edges.
    for x,y,w,d in [(760,158,25,7),(695,134,17,20)]:border(m,x,y,w,d,height)
    return m
