"""A compact fish market between the existing piers, based on the approved concept."""
import math
import random
from village import build as v
from hidamari import harbor

from hidamari.public_spaces import HARBOR_STALLS


def fish(m,x,y,z,scale=1):
    rings=[]
    for xx,ry,rz in [(-.28,.008,.008),(-.17,.075,.055),(.04,.10,.068),(.19,.06,.045),(.24,.018,.02)]:
        rings.append([(x+xx*scale,y+ry*math.cos(i*math.tau/8)*scale,z+rz*math.sin(i*math.tau/8)*scale) for i in range(8)])
    m.poly(rings[0][::-1],'fish_silver');m.poly(rings[-1],'fish_silver')
    for j in range(4):
        for i in range(8):m.poly([rings[j][i],rings[j+1][i],rings[j+1][(i+1)%8],rings[j][(i+1)%8]],'fish_back' if i in (0,1,2,3) else 'fish_silver')
    m.poly([(x-.24*scale,y,z),(x-.38*scale,y-.08*scale,z+.005),(x-.34*scale,y,z+.025),(x-.38*scale,y+.08*scale,z+.005)],'fish_tail')
    m.lathe((x+.18*scale,y-.045*scale,z+.043*scale),[(0,.012*scale),(.015*scale,0)],'h_dark',6)


def stall(m,x,y,variant,height,lettering):
    z=float(height(x,y))+.045;r=random.Random(990+variant)
    with m.at((x,y,z),180):
        def ground(lx,ly):return float(height(x-lx,y-ly))+.035-z
        for xx in [-2.2,2.2]:
            for yy in [-1.45,1.45]:
                bottom=ground(xx,yy)
                m.box((xx,yy,(bottom+2.65)/2),(.14,.14,2.65-bottom),'h_wood')
                m.beam((xx,yy,2.06),(xx-math.copysign(.52,xx),yy,2.61),.085,.085,'h_deck')
        for xx in [-2.2,2.2]:
            m.beam((xx,-1.45,2.60),(xx,1.45,2.60),.14,.14,'h_wood')
            m.beam((xx,0,2.65),(xx,0,3.15),.14,.14,'h_wood')
        for yy in [-1.45,1.45]:m.beam((-2.2,yy,2.57),(2.2,yy,2.57),.14,.14,'h_wood')
        for side in [-1,1]:
            for k in range(8):
                xa=-2.65+k*.6625;xb=xa+.6625;key='h_blue' if variant==0 or k%2 else 'h_white'
                pts=[(xa,0,3.15),(xb,0,3.15),(xb,side*1.95,2.51),(xa,side*1.95,2.51)]
                m.poly(pts,key);m.poly(pts[::-1],key)
            m.beam((-2.7,side*1.94,2.5),(2.7,side*1.94,2.5),.11,.11,'h_deck')
        m.beam((-2.7,0,3.16),(2.7,0,3.16),.12,.12,'h_wood')
        # Cloth shop fronts have actual suspension loops and frame attachment.
        for i in range(3):
            xx=(i-1)*1.55;key='h_blue' if variant==0 else 'h_white'
            m.box((xx,-1.97,2.21),(1.44,.022,.55),key)
            for dx in [-.45,.45]:harbor.ring(m,(xx+dx,-1.97,2.52),.07,.015,'h_rope','X',12)
            lettering(m,['鮮魚','地魚','ひもの'][i],(xx,-2.0,2.02),.49,color='h_white' if variant==0 else 'h_blue')
        for xx in [-1.8,1.8]:
            for yy in [-1.6,-.7]:
                bottom=ground(xx,yy);m.box((xx,yy,(bottom+.90)/2),(.16,.16,.90-bottom),'h_wood')
        m.box((0,-1.15,.90),(4.35,1.12,.14),'h_deck',.02)
        for k in range(15):m.box((-2.0+k*.285,-1.72,.5),(.26,.07,.80),'h_deck')
        for tray in [-1,1]:
            tx=tray*1.05;m.box((tx,-1.15,1.0),(1.91,.99,.10),'h_crate')
            m.box((tx,-1.15,1.065),(1.74,.86,.045),'fish_ice')
            for k in range(40):
                xx=tx+r.uniform(-.79,.79);yy=-1.15+r.uniform(-.35,.35)
                m.box((xx,yy,1.1),(.07,.06,.05),'fish_ice',.015)
            for row in range(3):
                for col in range(3):
                    with m.at((tx-.58+col*.56,-1.43+row*.26,1.16),-8+row*5):fish(m,0,0,0,.8 if variant else 1.)
        # Pared-back back counter; working boxes are supported by its shelf.
        m.box((0,1.1,1.05),(3.7,.65,.10),'h_deck')
        for xx in [-1.6,1.6]:
            bottom=ground(xx,1.1);m.box((xx,1.1,(bottom+1.05)/2),(.13,.50,1.05-bottom),'h_wood')
        for xx in [-1.2,0,1.2]:harbor.crate(m,xx,1.1,1.10,True,.65)
    # Crates beside, never in front of the skating lane or a pier entrance.
    for dx,dy in [(-3.05,.0),(3.05,-.2)]:
        zz=float(height(x+dx,y+dy))+.05;harbor.crate(m,x+dx,y+dy,zz,True,.8)


def add(m,height,lettering):
    harbor.COLORS.update({'fish_silver':(.48,.53,.49),'fish_back':(.10,.20,.23),'fish_tail':(.18,.28,.30),'fish_ice':(.62,.68,.61)})
    for x,y,variant in HARBOR_STALLS:stall(m,x,y,variant,height,lettering)
    x,y=652,-122.;z=float(height(x,y))+.05
    # Grounded net-drying rack with a sagging visible woven mesh.
    for dx in [-1.5,1.5]:
        bottom=float(height(x+dx,y))+.04
        m.box((x+dx,y,(bottom+z+1.9)/2),(.13,.13,z+1.9-bottom),'h_wood')
    m.beam((x-1.6,y,z+1.9),(x+1.6,y,z+1.9),.12,.12,'h_deck')
    for k in range(13):
        xx=x-1.4+k*.23
        pts=[(xx,y+.06+.16*math.sin(t*math.pi/6),z+1.82-t*.235-.12*math.sin(k*math.pi/12)) for t in range(7)]
        harbor.tube(m,pts,.014,'h_rope',5)
    for row in range(7):
        harbor.tube(m,[(x-1.4+k*.23,y+.06+.16*math.sin(row*math.pi/6),z+1.82-row*.235-.12*math.sin(k*math.pi/12)) for k in range(13)],.014,'h_rope',5)
    harbor.rope_coil(m,x-.8,y+.25,z,.65)
    harbor.ring(m,(x+1.0,y+.12,z+.60),.49,.10,'h_orange','Y')
    # A readable fish flag and chalk board mark the compact market from the quay.
    x,y=655.,-122.;z=float(height(x,y))+.04
    m.box((x,y,z+1.65),(.12,.12,3.3),'h_wood')
    m.beam((x,y,z+3.23),(x+.85,y,z+3.23),.07,.07,'h_deck')
    m.box((x+.47,y,z+2.33),(.70,.03,1.75),'h_blue')
    with m.at((x+.47,y+.035,z+2.45),180):lettering(m,'漁',(0,-.02,0),.63,color='h_white')
    for side in [-1,1]:
        yy=y+side*.03
        pts=[(x+.2,yy,z+1.92),(x+.34,yy,z+2.07),(x+.61,yy,z+2.07),(x+.74,yy,z+1.92),(x+.61,yy,z+1.80),(x+.34,yy,z+1.80)]
        m.poly(pts if side<0 else pts[::-1],'h_white')
        m.poly([(x+.22,yy,z+1.92),(x+.08,yy,z+2.05),(x+.08,yy,z+1.80)],'h_white')
    x,y=634.,-119.8;z=float(height(x,y))+.05
    with m.at((x,y,z),180):
        for xx in [-.49,.49]:
            for yy in [-.28,.28]:
                bottom=float(height(x-xx,y-yy))+.04-z
                m.beam((xx,yy,bottom),(xx,0,1.46),.07,.07,'h_wood')
        # Two battens bridge the sloping A-frame to its vertical display.
        for xx in [-.49,.49]:
            for zz in [.35,1.40]:
                frame_y=-.28*(1-zz/1.46)
                m.beam((xx,frame_y,zz),(xx,-.22,zz),.07,.07,'h_wood')
        m.box((0,-.22,.88),(1.08,.08,1.20),'h_deck')
        m.box((0,-.27,.88),(.92,.03,1.04),'h_dark')
        lettering(m,'地魚',(0,-.30,1.01),.31,color='h_white')
        lettering(m,'直売',(0,-.30,.56),.31,color='h_white')
    # A quiet view seat east of the next pier, with independently grounded feet.
    x,y=670.,-122.5;seat=float(height(x,y))+.52
    for xx in [x-1.3,x+1.3]:
        bottom=float(height(xx,y))+.035;m.box((xx,y,(bottom+seat)/2),(.17,.65,seat-bottom),'h_wood')
    for j in range(4):m.box((x,y-.26+j*.17,seat),(3.5,.145,.085),'h_deck')
    m.colliders=[]
    return m
