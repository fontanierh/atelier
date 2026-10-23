"""Canonical shoreline sample/event data, before rendered object construction or export."""
from contextlib import contextmanager
import math
import random
import numpy as np
from forest_lake.layout import CENTER,RADII,WATER,CABIN,radius
from village.layout import upper_surface
from forest_lake.details import islet
STONE=(.24,.25,.21)


class Events:
    def __init__(self,name):self.name=name;self.events=[]
    def poly(self,*args):self.events.append(['poly',args])
    def beam(self,*args):self.events.append(['beam',args])
    @contextmanager
    def at(self,position=(0,0,0),yaw=0):
        self.events.append(['push',[position,yaw]])
        try:yield
        finally:self.events.append(['pop',[]])


def rng_after_cabin():
    # Exact ambient719 draws in the source cabin. village.mesh uses its separate
    # Random(76), so its windows/roof do not advance this shoreline stream.
    rng=random.Random(719)
    for _ in np.arange(-3.4,3.5,.25):
        for _ in [-2.55,2.55]:
            for _ in range(3):rng.uniform(.9,1.1)
    for _ in np.arange(-13,-4.3,.22):
        for _ in range(3):rng.uniform(.91,1.09)
    return rng


def shoreline(h):
    m=Events('Lake_Shore');plants=Events('Lake_Plants');rng=rng_after_cabin()
    for i in range(100):
        a=rng.uniform(0,math.tau);r=rng.uniform(.99,1.065)*(1+.045*math.sin(3*a)+.035*math.cos(5*a));x=CENTER[0]+RADII[0]*r*math.cos(a);y=CENTER[1]+RADII[1]*r*math.sin(a)
        if x>-67 and y<229:continue
        z=float(upper_surface(h,x,y))
        if i%2==0:
            # Ground-intersecting faceted stones, no free-floating instances.
            with m.at((x,y,z-.15),rng.uniform(0,360)):
                sx=rng.uniform(.45,1.5);sy=rng.uniform(.4,1.1);sz=rng.uniform(.5,1.1)
                points=[(sx*math.cos(a),sy*math.sin(a),0) for a in np.linspace(0,math.tau,7)[:-1]]
                top=[(px*.7,py*.7,sz*rng.uniform(.8,1.05)) for px,py,_ in points]
                m.poly(top,STONE)
                for j in range(6):k=(j+1)%6;m.poly([points[j],points[k],top[k],top[j]],tuple(c*rng.uniform(.85,1.13) for c in STONE))
        for j in range(rng.randint(5,11)):
            px=x+rng.uniform(-.65,.65);py=y+rng.uniform(-.65,.65);pz=float(upper_surface(h,px,py))-.06;height=rng.uniform(.35,.95)
            if pz<WATER-.35:continue
            dx=rng.uniform(-.2,.2);dy=rng.uniform(-.2,.2)
            col=rng.choice([(.19,.26,.07),(.32,.33,.12),(.28,.37,.13)])
            for width in [(.04,0),(0,.04)]:
                pts=[(px-width[0],py-width[1],pz),(px+width[0],py+width[1],pz),(px+dx,py+dy,pz+height)]
                plants.poly(pts,col);plants.poly(pts[::-1],col)
            if j%4==0:plants.beam((px+dx,py+dy,pz+height-.15),(px+dx,py+dy,pz+height+.08),.045,.045,(.52,.43,.22))
    # Sparse autumn leaves seated on bank and approach, never suspended in water.
    for i in range(450):
        x=rng.uniform(-131,-41);y=rng.uniform(202,267);r=radius(x,y)
        if not 1.03<r<1.27 or (abs(x-CABIN[0])<7 and abs(y-CABIN[1])<7):continue
        z=float(upper_surface(h,x,y))+.025;sz=rng.uniform(.08,.18)
        plants.poly([(x-sz,y,z),(x,y-sz*.6,z),(x+sz,y,z+.008),(x,y+sz*.6,z)],rng.choice([(.48,.20,.036),(.61,.39,.06),(.36,.11,.022)]))
    # Small grouped lily leaves break up the near-water edge without blocking walking.
    for i in range(55):
        a=rng.choice([.4,1.7,3.4,4.6])+rng.uniform(-.16,.16)
        rr=rng.uniform(.80,.93);x=CENTER[0]+RADII[0]*rr*math.cos(a);y=CENTER[1]+RADII[1]*rr*math.sin(a)
        if float(upper_surface(h,x,y))>WATER-.15:continue
        rad=rng.uniform(.13,.32)
        pts=[(x+rad*math.cos(t),y+rad*math.sin(t),WATER+.015) for t in np.linspace(.2,math.tau-.2,10)]
        plants.poly([(x,y,WATER+.016),*pts],(.17,.27,.095))
    islet(m,plants)
    return {m.name:m.events,plants.name:plants.events}
