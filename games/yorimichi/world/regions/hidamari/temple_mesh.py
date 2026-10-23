"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.construction import civic
from hidamari.environment import M
from hidamari.environment import v
from mathutils import Matrix
import math


def temple():
    m=M('HD_Temple');v.shell(m,24,17,6.5,True);v.roof(m,26,20,6.5,3.5)
    for side in [-1,1]:
        for row in range(8):
            a=row/8;b=(row+1)/8
            z=lambda t:6.5+3.5*(1-t)**1.10+.10*t**6-.035
            p=[(-13.65,side*10.675*a,z(a)),(13.65,side*10.675*a,z(a)),(13.65,side*10.675*b,z(b)),(-13.65,side*10.675*b,z(b))]
            m.poly(p if side>0 else p[::-1],'roof')
    # Ground-level veranda allows strolling; ceremonial stairs are optional front detail.
    m.box((0,-11,.19),(27,5,.50),'wood_light');m.collider((0,-11,.22),(27,5,.44))
    # Two shallow treads meet the 44 cm veranda instead of a single high jump.
    for yy,top in [(-14.05,.15),(-13.70,.30)]:
        m.box((0,yy,(top-.06)/2),(4.4,.40,top+.06),'stone_light',.02)
        m.collider((0,yy,top/2),(4.4,.40,top))
    # Continuous lean-to canopy connects the outer veranda posts to the roof.
    for x in [-11,-7,7,11]:
        m.box((x,-12,2.90),(.35,.35,5.80),'wood')
        m.collider((x,-12,2.90),(.35,.35,5.80))
    m.box((0,-12,5.80),(27.3,.32,.28),'wood_dark')
    for k in range(28):
        xa=-13.7+k*27.4/28;xb=xa+27.4/28
        points=[(xa,-9.8,6.9),(xb,-9.8,6.9),(xb,-13.5,5.47),(xa,-13.5,5.47)]
        m.poly(points[::-1],'roof');m.poly([(xx,yy,zz-.12) for xx,yy,zz in points],'wood_dark')
        m.beam((xa,-9.8,6.93),(xa,-13.5,5.5),.035,.04,'roof_edge')
    m.box((0,-13.5,5.46),(27.5,.16,.20),'roof_edge')
    # Match the canopy slope in the temple's authored simple collision.
    angle=math.atan2(1.43,3.7)
    old=m.transform.copy()
    m.transform=old @ Matrix.Translation((0,-11.65,6.125)) @ Matrix.Rotation(angle,4,'X')
    m.collider((0,0,0),(27.4,math.hypot(3.7,1.43),.12*math.cos(angle)))
    m.transform=old
    for bx in [-8,8]:
        m.collider((bx,-10.2,.6925),(3.4,.65,.505))
        for xx in [bx-1.35,bx+1.35]:m.box((xx,-10.2,.66),(.18,.65,.44),'wood')
        for j in range(4):m.box((bx,-10.45+j*.17,.90),(3.4,.145,.09),'wood_light')
    v.door(m,0,-8.65,.45,4,4.5)
    for x in [-8,8]:v.window(m,x,-8.65,3,4.8,3.6,True)
    return m

def shrine():
    m=civic('HD_Shrine',7,7,3.8)
    for x in [-4,4]:m.box((x,-8,2.8),(.32,.32,5.6),'rust')
    m.box((0,-8,5.3),(10,.5,.35),'rust');m.box((0,-8,4.7),(8.8,.4,.22),'wood_dark')
    return m
