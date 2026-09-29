"""Pond garden additions from the reconciled September 8 reference.

The original crossing and five-metre perimeter walk remain unobstructed.
All stone planting is below the inner bank; the island avoids recovery probes.
"""
import math
import random
from village import build as v
from hidamari import plaza, living_plaza


def rock(m,x,y,z,s,rng):
    rings=[];n=7
    angles=[i*math.tau/n+rng.uniform(-.10,.10) for i in range(n)]
    stretch=rng.uniform(.65,1.05);turn=rng.random()*math.tau
    radial=[rng.uniform(.78,1.14) for _ in angles]
    for h,r in [(0,.88),(.32,1),(.72,.78),(.85,.36)]:
        rings.append([(x+s*r*radial[i]*math.cos(a+turn),y+s*r*stretch*radial[i]*math.sin(a+turn),z+s*h+rng.uniform(-.055,.055)*s) for i,a in enumerate(angles)])
    for j in range(3):
        for i in range(n):
            m.poly([rings[j][i],rings[j][(i+1)%n],rings[j+1][(i+1)%n],rings[j+1][i]],'pond_moss' if j==2 and i%3 else ['pond_rock','pond_rock_light'][i%2])
    m.poly(rings[-1],'pond_moss')


def reeds(m,x,y,z,rng):
    for i in range(12):
        a=rng.random()*math.tau;h=rng.uniform(.6,1.45);dx=math.cos(a);dy=math.sin(a)
        xx=x+rng.uniform(-.4,.4);yy=y+rng.uniform(-.4,.4)
        pts=[(xx-.055*dy,yy+.055*dx,z),(xx+.055*dy,yy-.055*dx,z),(xx+dx*.25,yy+dy*.25,z+h*.75),(xx+dx*.60,yy+dy*.60,z+h)]
        key='pond_reed' if i%3 else 'pond_reed_light'
        m.poly(pts,key);m.poly(pts[::-1],key)
        if i%5==0:
            m.beam((xx,yy,z),(xx,yy,z+h),.025,.025,'pond_reed')
            plaza.bloom(m,xx,yy,z+h,.14,'pond_iris')


def lantern(m,x,y,z):
    m.lathe((x,y,z),[(0,.48),(.15,.48),(.20,.29),(.70,.24),(.76,.44),(.83,.44),(.83,0)],'pond_rock_light',8)
    m.box((x,y,z+1.04),(.47,.47,.45),'paper')
    for dx in [-.26,.26]:
        for dy in [-.26,.26]:m.box((x+dx,y+dy,z+1.04),(.085,.085,.49),'wood_dark')
    m.lathe((x,y,z+1.28),[(0,.58),(.13,.54),(.45,.13),(.56,0)],'pond_rock',4)


def add(m,height):
    plaza.palette()
    v.PALETTE.update({'pond_rock':(.105,.13,.115),'pond_rock_light':(.18,.20,.16),
      'pond_moss':(.095,.17,.035),'pond_reed':(.12,.245,.075),'pond_reed_light':(.36,.40,.095),'pond_iris':(.34,.20,.39)})
    rng=random.Random(683)
    # Overlapping coves hide the vertical inner bank, leaving the walk above clear.
    for i in range(64):
        a=i*math.tau/64+rng.uniform(-.018,.018)
        if abs(math.sin(a))<.17:continue  # Bridge landings.
        for ring in range(1 if i%9 in (0,1,2) else 2):
            rr=ring*1.8+rng.uniform(-.15,.25)
            x=1030+(44.3-rr)*math.cos(a);y=284+(30.4-rr)*math.sin(a)
            rock(m,x,y,28.0 if ring else 28.65,rng.uniform(1.45,2.6) if not ring else rng.uniform(.65,1.8),rng)
        if i%11 not in (0,1,2):
            for k in range(3):
                t=a+(k-1)*.022;xx=1030+45.4*math.cos(t);yy=284+31.4*math.sin(t)
                m.lathe((xx,yy,30.2),[(0,.62),(.38,.65),(.45,.6),(.45,0)],'pond_moss',8)
                reeds(m,xx,yy,30.64,rng)
        if i%2==0:
            x=1030+42.4*math.cos(a);y=284+28.4*math.sin(a)
            # Rooted shallow soil mound, not reeds sprouting in thin air.
            m.lathe((x,y,28.3),[(0,.6),(.55,.8),(.68,.65),(.68,0)],'pond_moss',8)
            reeds(m,x,y,28.96,rng)
            for k in range(5):
                xx=x+rng.uniform(-1.5,1.5);yy=y+rng.uniform(-1.3,1.3)
                m.poly([(xx+.25*math.cos(t*math.tau/7),yy+.25*math.sin(t*math.tau/7),28.825) for t in range(7)],'pond_moss')
    # Continuous scalloped coves taper back into the bank at both ends.
    # This avoids the straight-sided green cards of the first shelf iteration.
    for start in [3,14,25,36,47,58]:
        a=(start-.75)*math.tau/64;b=(min(start+7,63)+.75)*math.tau/64
        def section(t):
            ang=a+(b-a)*t;strength=math.sin(math.pi*t)**.65
            width=(4.2+.55*math.sin(t*math.tau*2))*strength
            outer=(1030+45.9*math.cos(ang),284+31.9*math.sin(ang),30.77)
            inner=(1030+(45.9-width)*math.cos(ang),284+(31.9-width)*math.sin(ang),30.77-2.10*strength)
            return outer,inner
        for j in range(32):
            oa,ia=section(j/32);ob,ib=section((j+1)/32)
            m.poly([oa,ia,ib,ob][::-1],'pond_moss')
    # Small planted islet: clear of the crossing and the designated water recovery point.
    m.lathe((1050,299,27.8),[(0,5.4),(1.0,5.5),(2.,4.3),(2.2,3.7)],'pond_rock',14)
    m.poly([(1050+3.7*math.cos(i*math.tau/14),299+3.7*math.sin(i*math.tau/14),30.) for i in range(14)],'pond_moss')
    for i in range(15):
        a=i*math.tau/15;rock(m,1050+4.9*math.cos(a),299+4.9*math.sin(a),28.3,rng.uniform(1.0,1.65),rng)
    lantern(m,1047.7,299,30.0)
    for x,y in [(1048,301),(1052,301),(1052,297)]:reeds(m,x,y,30.,rng)
    for gx,gy in [(1051.8,300.8),(1049.,297.4),(1052.4,297.8)]:
        for i in range(5):
            xx=gx+rng.uniform(-.6,.6);yy=gy+rng.uniform(-.5,.5);rr=rng.uniform(.35,.62)
            m.lathe((xx,yy,30.),[(0,rr*.6),(.25,rr),(.48,rr*.55),(.55,0)],'pond_moss',7)
            if i%2:plaza.bloom(m,xx,yy,30.55,.12,'arc_bloom')
    # A tea terrace outside the perimeter walk, accessible from the surrounding lawn.
    living_plaza.palette()
    # This level bank avoids placing tables on the rising northeastern slope.
    m.box((1084,290,30.90),(7,10,.24),'arc_timber')
    for i in range(25):m.box((1080.64+i*.28,290,31.01),(.26,10,.06),'arc_trim')
    terrace_height=lambda x,y:30.91
    living_plaza.cafe_table(m,1084,287.5,terrace_height)
    living_plaza.cafe_table(m,1084,292.5,terrace_height)
    # Retain complex collision for the original bank and crossing. New decorative
    # shapes sit off the travel lanes; no partial UCX set may replace this surface.
    m.colliders=[]
    return m
