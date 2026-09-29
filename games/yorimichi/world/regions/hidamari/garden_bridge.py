"""Cedar pond bridge, built from the September 8 image-generation reference.

The original continuous riding profile and bank connections are retained.
A roofed bay is offset from the through lane; all supports extend below water.
"""
import math
import random
import numpy as np
from village import build as v


def level(x):
    return 30.925+1.5*math.sin(math.pi*min(1.,max(0.,(x-984)/92)))


def palette():
    v.PALETTE.update({'gb_cedar':(.23,.105,.041),'gb_rail':(.17,.068,.024),
        'gb_endgrain':(.105,.045,.018),'gb_deck':(.31,.165,.077),
        'gb_stone':(.27,.30,.29),'gb_mortar':(.11,.135,.14),
        'gb_iron':(.026,.030,.032),'gb_paper':(.94,.71,.39)})


def lantern(m,x,y,z):
    m.box((x,y,z+.035),(.47,.47,.07),'gb_iron')
    m.box((x,y,z+.245),(.33,.33,.38),'gb_paper')
    for dx in [-.19,.19]:
        for dy in [-.19,.19]:m.box((x+dx,y+dy,z+.25),(.045,.045,.43),'gb_endgrain')
    for side in [-1,1]:
        m.box((x+side*.19,y,z+.25),(.035,.035,.39),'gb_endgrain')
        m.box((x,y+side*.19,z+.25),(.035,.035,.39),'gb_endgrain')
    m.box((x,y,z+.465),(.49,.49,.07),'gb_iron')
    m.lathe((x,y,z+.49),[(0,.38),(.13,.17),(.17,0)],'roof',4)


def post(m,x,y,z,major=False,lit=False):
    w=.30 if major else .18;h=1.47 if lit else 1.18
    m.box((x,y,z+h/2),(w,w,h),'gb_cedar',.02)
    m.box((x,y,z+h-.01),(w+.10,w+.10,.10),'gb_endgrain',.018)
    for dz in [.16,1.02]:
        m.box((x,y,z+dz),(w+.012,w+.012,.075),'gb_iron')
    if lit:lantern(m,x,y,z+h+.04)


def rail(m,a,b,za,zb):
    ax,ay=a;bx,by=b
    for h,w,d in [(.35,.11,.12),(.72,.13,.14),(1.08,.15,.22)]:
        m.beam((ax,ay,za+h),(bx,by,zb+h),w,d,'gb_cedar' if h>1 else 'gb_rail')
    # Pegged joinery, restrained enough to read clearly from gameplay distance.
    for t in [.08,.92]:
        x=ax+(bx-ax)*t;y=ay+(by-ay)*t;z=za+(zb-za)*t
        m.box((x,y,z+.73),(.075,.18,.075),'gb_iron')


def stone_face(m,x,z,w,color):
    # Only the exposed chamfered face is modeled; the continuous pier core
    # closes its back. Hidden full beveled cubes waste most of their triangles.
    h=.40;c=.045
    outline=[(-w/2+c,-h/2),(w/2-c,-h/2),(w/2,-h/2+c),(w/2,h/2-c),
             (w/2-c,h/2),(-w/2+c,h/2),(-w/2,h/2-c),(-w/2,-h/2+c)]
    outer=[(x+px,-.535,z+pz) for px,pz in outline]
    front=[(x+px*.94,-.61,z+pz*.88) for px,pz in outline]
    m.poly(front,color)
    for i in range(8):m.poly([outer[i],outer[(i+1)%8],front[(i+1)%8],front[i]],color)


def footing(m,x,y,top):
    bottom=27.0;cap=30.0
    m.box((x,y,(bottom+cap)/2),(1.05,1.05,cap-bottom),'gb_mortar')
    for row in range(4):
        z=28.50+row*.42
        widths=[.29,.58,.29] if row%2 else [.58,.58]
        for angle in [0,90,180,270]:
            with m.at((x,y,0),angle):
                start=-.58
                for j,w in enumerate(widths):
                    color=tuple(c*(.94+.035*((row+j)%4)) for c in v.PALETTE['gb_stone'])
                    stone_face(m,start+w/2,z,w-.025,color);start+=w
    m.box((x,y,cap-.055),(1.23,1.23,.16),'gb_stone',.05)
    m.box((x,y,(cap+top)/2),(.42,.42,top-cap),'gb_rail')


def seat(m,x,y,z,width=3.0,yaw=0):
    with m.at((x,y,z),yaw):
        for xx in [-width/2+.23,width/2-.23]:
            m.box((xx,0,.235),(.17,.48,.47),'gb_rail')
            m.box((xx,.27,.67),(.13,.13,.84),'gb_rail')
        for j in range(3):m.box((0,-.22+j*.20,.51),(width,.185,.08),'gb_cedar',.012)
        for h in [.79,1.00]:m.box((0,.27,h),(width,.09,.15),'gb_cedar',.015)


def add(m):
    palette();rng=random.Random(902)
    # Same support surface and small plank joints as the tested original bridge.
    for x in np.arange(982.83,1077.17,.5):
        xx=min(float(x)+.5,1077.17)
        m.poly([(x,282,level(x)-.022),(xx,282,level(xx)-.022),(xx,286,level(xx)-.022),(x,286,level(x)-.022)],'gb_rail')
    for x in np.arange(982.83,1077.17,.32):
        xx=min(float(x)+.305,1077.17)
        top=[(x,282,level(x)),(xx,282,level(xx)),(xx,286,level(xx)),(x,286,level(x))]
        bottom=[(px,py,pz-.18) for px,py,pz in top]
        color=tuple(c*rng.uniform(.94,1.05) for c in v.PALETTE['gb_deck'])
        m.poly(top,color);m.poly(bottom[::-1],'gb_rail')
        for k in range(4):m.poly([top[k],bottom[k],bottom[(k+1)%4],top[(k+1)%4]],color)
    # Deeper continuous edge girders follow the gentle arch.
    for side in [-1,1]:
        for i in range(80):
            x=984+i*1.15;xx=x+1.15;y=284+side*1.89
            m.beam((x,y,level(x)-.34),(xx,y,level(xx)-.34),.34,.30,'gb_rail')
        for i in range(41):
            x=984+i*2.3
            if 18<i<22:continue
            post(m,x,284+side*1.9,level(x),i%4==0,i%8==0 or i in (18,22))
            if i<40 and i not in (18,19,20,21):rail(m,(x,284+side*1.9),(x+2.3,284+side*1.9),level(x),level(x+2.3))
    # Paired masonry piers and curved timber knee braces support each long span.
    for i in range(0,41,4):
        x=984+i*2.3;z=level(x)
        for side in [-1,1]:
            y=284+side*1.6;footing(m,x,y,z-.18)
            for direction in [-1,1]:
                if not 984<=x+direction*2.2<=1076:continue
                for k in range(8):
                    a=k/8;b=(k+1)/8
                    def p(t):return (x+direction*2.2*t,y,z-1.35+1.00*math.sin(t*math.pi/2))
                    m.beam(p(a),p(b),.24,.24,'gb_cedar')
        m.beam((x,282.0,z-.32),(x,286.0,z-.32),.30,.33,'gb_rail')
    # Flat side bays share the crest level; the central four-metre lane stays open.
    z=level(1030)
    for side,outer in [(-1,278.7),(1,292.3)]:
        inner=282 if side<0 else 286;cy=(outer+inner)/2;depth=abs(outer-inner)
        m.box((1030,cy,z-.16),(9.2,depth,.28),'gb_rail')
        for j in range(33):m.box((1025.52+j*.28,cy,z-.035),(.265,depth,.07),'gb_deck')
        for xx in [1025.4,1030,1034.6]:
            footing(m,xx,outer,z-.18);post(m,xx,outer,z,True,xx!=1030)
            if xx<1034.6:rail(m,(xx,outer),(xx+4.6,outer),z,z)
            for direction in [-1,1]:
                if not 1025.4<=xx+direction*1.4<=1034.6:continue
                for k in range(6):
                    def p(t):return (xx+direction*1.4*t,outer,z-1.25+.95*math.sin(t*math.pi/2))
                    m.beam(p(k/6),p((k+1)/6),.22,.22,'gb_cedar')
        m.box((1030,outer,z-.30),(9.5,.30,.30),'gb_rail')
        for xx in [1025.4,1034.6]:
            rail(m,(xx,inner),(xx,outer),z,z)
            m.beam((xx,inner,z-.32),(xx,outer,z-.32),.30,.30,'gb_rail')
        seat(m,1030,outer-side*.60,z,3.1,0 if side>0 else 180)
    # Offset open shelter: all posts and furniture are beyond y=286.75.
    with m.at((1030,289.45,z),0):
        for x in [-3.5,3.5]:
            for y in [-1.85,1.85]:
                m.box((x,y,1.59),(.27,.27,3.18),'gb_cedar',.018)
                m.box((x,y,.12),(.31,.31,.24),'gb_iron')
                for dx in [-1,1]:m.beam((x,y,2.56),(x+dx*.60,y,3.05),.14,.14,'gb_cedar')
        for y in [-1.85,1.85]:m.box((0,y,3.08),(7.7,.24,.28),'gb_rail')
        for x in [-3.5,3.5]:m.box((x,0,3.08),(.24,4.3,.28),'gb_rail')
        original=v.PALETTE['plaster'];v.PALETTE['plaster']=v.PALETTE['gb_rail']
        try:v.roof(m,7.7,4.1,3.2,1.12)
        finally:v.PALETTE['plaster']=original
    return m
