"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.environment import M
from hidamari.environment import v
import math
import numpy as np


def simple_roof(m,w,d,z,rise=2):
    w+=1.1;d+=1.3
    # Closed soffit prevents sky showing through the projecting gable ends.
    m.box((0,0,z-.06),(w,d,.15),'wood_dark')
    for s in [-1,1]:
        pts=[(-w/2,0,z+rise),(w/2,0,z+rise),(w/2,s*d/2,z),( -w/2,s*d/2,z)]
        m.poly(pts[::-1] if s<0 else pts,'roof')
        m.beam((-w/2,s*d/2,z),(w/2,s*d/2,z),.24,.24,'roof_edge')
        for i in range(1,7):
            y=s*d/2*i/7;zz=z+rise*(1-i/7)
            m.beam((-w/2,y,zz),(w/2,y,zz),.055,.055,'roof_edge')
    for x in [-w/2,w/2]:
        m.poly([(x,-d/2,z),(x,d/2,z),(x,0,z+rise)][::-1 if x<0 else 1],'plaster_light')
        m.beam((x,-d/2,z),(x,0,z+rise),.2,.2,'roof_edge');m.beam((x,d/2,z),(x,0,z+rise),.2,.2,'roof_edge')
    m.beam((-w/2,0,z+rise),(w/2,0,z+rise),.3,.25,'roof_edge')


def civic(name,w,d,h):
    m=M(name);v.shell(m,w,d,h);simple_roof(m,w,d,h,3)
    for x in np.linspace(-w/2+3,w/2-3,int(w/5)):
        v.window(m,float(x),-d/2-.1,h*.65,2.5,2.8,True)
    v.door(m,0,-d/2-.15,.06,3,3.5)
    for side in [-1,1]:
        with m.at((side*w/2,0,0),90*side):
            for x in [-d*.28,0,d*.28]:
                v.window(m,x,-.12,h*.63,2.5,2.8,True)
            m.box((0,-.1,3.7),(d,.18,.2),'wood_light')
    return m

def flowerbed(m,x,y,z,w=1.6,d=1.2):
    m.box((x,y,z+.3),(w,d,.6),'stone',.07)
    m.box((x,y,z+.61),(w-.18,d-.18,.05),'soil')
    for i in range(max(3,int(w/.4))):
        for j in range(max(2,int(d/.45))):
            xx=x-w/2+.25+i*(w-.5)/max(1,int(w/.4)-1)
            yy=y-d/2+.25+j*(d-.5)/max(1,int(d/.45)-1)
            zz=z+.66+.06*math.sin(i*3+j)
            m.lathe((xx,yy,zz),[(0,.13),(.18,.28),(.38,.12),(.43,0)],'green',6)
            m.lathe((xx+.04,yy,zz+.32),[(0,.04),(.09,.16),(.14,.13),(.17,0)],'paper' if (i+j)%3 else 'rust',6)
