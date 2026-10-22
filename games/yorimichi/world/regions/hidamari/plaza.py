"""Clock-square kit, modelled against the reconciled Hidamari plaza reference."""
import math
import random
from village import build as v
from hidamari import arcade, hero_approaches


def palette():
    arcade.palette()
    v.PALETTE.update({'sq_wall':(.62,.46,.29),'sq_stone':(.40,.31,.20),
        'sq_cap':(.55,.43,.28),'sq_copper':(.11,.18,.07),'sq_roof':(.032,.045,.057),
        'sq_water':(.025,.20,.31),'sq_foam':(.32,.58,.62),'sq_leaf':(.88,.40,.015)})


def roof(m,w,d,z,rise=3):
    for side in [-1,1]:
        p=[(-w/2,0,z+rise),(w/2,0,z+rise),(w/2,side*d/2,z),(-w/2,side*d/2,z)]
        m.poly(p,'sq_roof');m.poly(p[::-1],'arc_timber')
        for row in range(1,13):
            yy=side*d/2*row/12;zz=z+rise*(1-row/12)
            m.beam((-w/2,yy,zz+.025),(w/2,yy,zz+.025),.065,.07,'sq_roof')
        m.beam((-w/2,side*d/2,z),(w/2,side*d/2,z),.20,.25,'arc_timber')
    for side in [-1,1]:
        x=side*w/2
        p=[(x,-d/2,z),(x,d/2,z),(x,0,z+rise)]
        m.poly(p if side>0 else p[::-1],'sq_wall')
        for sy in [-1,1]:m.beam((x,0,z+rise),(x,sy*d/2,z),.22,.24,'arc_trim')
    for i in range(math.ceil(w/.65)):
        m.box((-w/2+.325+i*.65,0,z+rise+.1),(.62,.35,.18),'sq_roof',.04)


def glazed(m,x,y,z,w=1.65,h=2.25):
    m.box((x,y,z),(w+.24,.20,h+.28),'arc_trim',.015)
    m.box((x,y-.115,z),(w,.025,h),'arc_paper')
    for j in range(4):m.box((x-w/2+j*w/3,y-.16,z),(.045,.07,h+.08),'arc_timber')
    for j in range(5):m.box((x,y-.17,z-h/2+j*h/4),(w+.10,.07,.045),'arc_timber')
    m.box((x,y-.25,z-h/2-.12),(w+.40,.42,.16),'sq_cap',.025)
    m.box((x,y-.18,z+h/2+.18),(w+.37,.25,.18),'arc_trim')


def shop_sides(raised_rear=False):
    """Shared side/rear facade dressing for exposed plaza shop corners."""
    palette();m=v.Mesh('HD_PlazaShopSidesCorner' if raised_rear else 'HD_PlazaShopSides')
    for side in [-1,1]:
        x=side*3.51;p=[(x,-5,8.1),(x,5,8.1),(x,0,9.65)]
        m.poly(p if side>0 else p[::-1],'arc_plaster')
        for sy in [-1,1]:m.beam((x,0,9.65),(x,sy*5,8.1),.12,.14,'arc_trim')
    for yaw,width,depth in [(90,10,7),(-90,10,7),(180,7,10)]:
        with m.at(yaw=yaw):
            m.box((0,-depth/2+.03,1.8),(width,.12,3.6),'arc_plaster')
            for x in [-width/2+.25,width/2-.25]:m.box((x,-depth/2-.05,4),(.18,.17,7.9),'arc_timber')
            for z in [.45,3.6,7.9]:m.box((0,-depth/2-.055,z),(width,.18,.16),'arc_trim')
            for x in [-width*.28,0,width*.28]:
                # The southeast corner adjoins a higher shop's display apron.
                # Keep the rear glazing above that apron without removing its
                # supported approach or changing the shared street frontage.
                lower=2.85 if raised_rear and yaw==180 else 2.25
                for z in [lower,5.8]:glazed(m,x,-depth/2-.09,z,1.25,1.7)
    return m


def shop_approaches(city,height):
    """Supported shop plinths and short doorstep stairs on the sloping square."""
    palette();m=v.Mesh('HD_PlazaShopApproaches')
    for b in city['buildings']:
        if not (b['asset'].startswith('HD_ArcadeShop') and 120<b['position'][1]<215):continue
        x,y,z=b['position'];a=math.radians(b['yaw'])
        def ground(lx,ly):return float(height(x+lx*math.cos(a)-ly*math.sin(a),y+lx*math.sin(a)+ly*math.cos(a)))+.13-z
        bottom=min(ground(lx,ly) for lx in [-3.5,3.5] for ly in [-9,5])-.2
        with m.at((x,y,z),b['yaw']):
            m.box((0,0,(bottom+.16)/2),(6.98,10,.16-bottom),'arc_stone')
            # The entire display apron supports shelves, pots and the A-board.
            m.box((0,-5.92,(bottom+.02)/2),(6.98,1.85,.02-bottom),'arc_stone')
            m.collider((0,-5.92,(bottom+.02)/2),(6.98,1.85,.02-bottom))
            m.box((-2,-5.32,.09),(1.65,.55,.18),'arc_stone')
            m.collider((-2,-5.32,.09),(1.65,.55,.18))
            for i in range(8):
                top=.02-i*.15;yy=-7.01-i*.34
                footprint=[ground(lx,ly) for lx in (-2.825,-1.175) for ly in (yy-.18,yy+.18)]
                # Stop when the walking surface meets the finished plaza. Testing
                # the buried footing bottom emitted detached slivers below that.
                if top<=max(footprint)+.03:break
                low=min(footprint)-.10
                m.box((-2,yy,(low+top)/2),(1.65,.36,top-low),'arc_stone')
                m.collider((-2,yy,(low+top)/2),(1.65,.36,top-low))
    for points,color in hero_approaches.hero_approach_faces(city,height):
        m.poly(points,color)
    return m


def clock(m,y,z,lettering):
    for radius,depth,key in [(1.70,y,'arc_timber'),(1.53,y-.025,'sq_cap'),(1.42,y-.045,'arc_ivory')]:
        m.poly([(radius*math.cos(k*math.tau/64),depth,z+radius*math.sin(k*math.tau/64)) for k in range(64)],key)
    for j in range(12):
        a=j*math.tau/12
        m.beam((math.sin(a)*1.15,y-.075,z+math.cos(a)*1.15),(math.sin(a)*1.28,y-.075,z+math.cos(a)*1.28),.06,.045,'arc_timber')
    m.beam((0,y-.09,z),(-.69,y-.09,z+.48),.095,.065,'arc_timber')
    m.beam((0,y-.11,z),(.52,y-.11,z+1.00),.065,.05,'arc_timber')
    m.box((0,y-.13,z),(.14,.045,.14),'arc_timber',.02)


def clock_hall(lettering,height):
    palette();m=v.Mesh('HD_ClockHall');w=30;d=18;h=12.6
    m.box((0,0,h/2),(w,d,h),'sq_wall');m.collider((0,0,6),(w,d,13))
    m.box((0,0,-.1),(30.4,18.4,2.2),'sq_stone',.08)
    roof(m,31.8,20.0,h,3.1)
    # Two complete storeys, including the west gable seen from the square.
    for yaw,width,depth in [(0,w,d),(90,d,w),(180,w,d),(-90,d,w)]:
        with m.at(yaw=yaw):
            for x in [-width/2+.35,width/2-.35]:m.box((x,-depth/2-.16,6.1),(.40,.28,12.4),'sq_cap')
            for z in [1.1,5.5,6.2,12.15]:m.box((0,-depth/2-.14,z),(width,.25,.17),'arc_trim')
            positions=[-11.8,-7.5,-3.3,3.3,7.5,11.8] if width==w else [-6,-2,2,6]
            for x in ([-9.65,-5.4,5.4,9.65] if width==w else [-4,0,4]):
                m.box((x,-depth/2-.23,6.5),(.19,.18,10.8),'arc_timber')
            for x in positions:
                glazed(m,x,-depth/2-.2,8.65,1.72,2.55)
                if yaw==0 and abs(x)<4:continue
                glazed(m,x,-depth/2-.2,3.15,1.55,2.35)
            for row in range(3):
                for j in range(math.ceil(width/1.3)):
                    x=-width/2+(j+.5)*1.3
                    m.box((x,-depth/2-.235,.04+row*.36),(1.23,.065,.30),'sq_cap' if (j+row)%4==0 else 'sq_stone',.015)
    # Layered entrance with walkable shallow steps on the sloping plaza.
    m.box((0,-9.24,2.2),(4.2,.22,4.25),'arc_trim')
    for x in [-.95,.95]:
        m.box((x,-9.38,2.0),(1.82,.18,3.9),'arc_timber',.025)
        for z in [1.1,2.7]:m.box((x,-9.49,z),(1.42,.08,1.2),'arc_trim',.025)
        m.box((x*.22,-9.56,1.9),(.075,.08,.33),'metal')
    m.box((0,-9.38,4.95),(7.6,.3,.86),'sq_cap',.04)
    lettering(m,'HIDAMARI',(0,-9.57,4.68),.75,color='arc_timber')
    m.box((0,-9.39,4.25),(3.8,.15,.50),'arc_paper')
    for x in [-1.8,-.9,0,.9,1.8]:m.box((x,-9.50,4.25),(.065,.08,.50),'arc_timber')
    m.box((0,-9.54,4.60),(4.7,.75,.20),'arc_trim',.025)
    for i in range(7):
        y=-9.3-(7-i)*.39;top=-1.16+i*.18
        m.box((0,y,(top-1.65)/2),(5.1,.45,top+1.65),'sq_cap',.02)
        m.collider((0,y,(top-1.65)/2),(5.1,.45,top+1.65))
    # Continuous landing bridges the last tread to the doorway collider.
    m.box((0,-9.30,-.825),(5.1,.72,1.65),'sq_cap',.02)
    m.collider((0,-9.30,-.825),(5.1,.72,1.65))
    for side in [-1,1]:
        lantern_post(m,side*2.8,-9.7,2.65,wall=True)
        for y in [-10.5,-11.7]:
            z=float(height(730+side*5.6,178+y)-height(730,178))+.07
            v.pot(m,side*5.6,y,z,1.15,'clay',plant=True)
    for side in [-1,1]:
        x,y=side*10.3,-10.5
        z=float(height(730+x,178+y)-height(730,178))+.03
        planter(m,x,y,z,3.2,1.25,17+side)
    # Short clock stage and four-sided patinated copper spire.
    m.box((0,0,16.6),(5.8,5.8,4.6),'sq_wall');m.collider((0,0,16.6),(5.8,5.8,4.6))
    for yaw in [0,90,180,270]:
        with m.at(yaw=yaw):
            for x in [-2.7,2.7]:m.box((x,-2.97,16.6),(.27,.26,4.6),'arc_trim')
            m.box((0,-3.02,14.5),(6.3,.35,.3),'arc_trim')
            m.box((0,-3.02,18.8),(6.3,.35,.3),'arc_trim')
            clock(m,-3.12,16.6,lettering)
            p=[(-3.4,-3.4,19),(3.4,-3.4,19),(.25,-.25,23.5),(-.25,-.25,23.5)]
            m.poly(p,'sq_copper')
            for j in range(1,10):
                t=j/10;a=3.4*(1-t)+.25*t;z=19+4.5*t
                m.beam((-a,-a-.025,z),(a,-a-.025,z),.055,.055,'sq_copper')
    m.beam((0,0,23.4),(0,0,25),.085,.085,'arc_timber')
    m.lathe((0,0,24.1),[(-.15,.04),(0,.14),(.15,.04)],'arc_trim',12)
    return m


def lantern_post(m,x,y,z,wall=False):
    if not wall:
        m.lathe((x,y,z),[(0,.23),(.2,.23),(.45,.13),(3.25,.085),(3.45,.16)],'metal',12)
        m.collider((x,y,z+1.65),(.28,.28,3.3));z+=3.5
    else:
        m.beam((x,y+.6,z),(x,y,z),.10,.10,'metal')
    m.lathe((x,y,z),[(0,.22),(.09,.22),(.78,.31),(.83,.32)],'arc_paper',4)
    for dx in [-1,1]:
        for dy in [-1,1]:m.beam((x+dx*.15,y+dy*.15,z),(x+dx*.22,y+dy*.22,z+.81),.045,.045,'metal')
    m.lathe((x,y,z+.82),[(0,.38),(.10,.38),(.36,.06),(.53,.025)],'metal',4)


def bloom(m,x,y,z,r,color):
    # Cupped, solid blossoms read as flowers from street height, not thin cards.
    m.lathe((x,y,z),[(0,.015),(.025,r),(.06,r*.82),(.075,r*.42)],color,10)
    m.lathe((x,y,z+.064),[(0,r*.35),(.04,r*.28),(.045,0)],'arc_bloom',10)


def planter(m,x,y,z,w=3,d=1.6,seed=0):
    r=random.Random(seed)
    m.box((x,y,z+.26),(w,d,.56),'sq_stone',.10)
    m.box((x,y,z+.56),(w+.12,d+.12,.12),'sq_cap',.06)
    m.box((x,y,z+.60),(w-.18,d-.18,.035),'soil')
    m.collider((x,y,z+.28),(w,d,.56))
    for j in range(round(w*d*15)):
        xx=x+r.uniform(-w*.42,w*.42);yy=y+r.uniform(-d*.38,d*.38);zz=z+r.uniform(.72,.93)
        m.lathe((xx,yy,z+.60),[(0,.08),(.12,.18),(.22,.13),(.28,0)],'green_dark' if j%3 else 'green',7)
        if j%2==0:bloom(m,xx,yy,zz,.09+r.random()*.05,['arc_ivory','arc_rose','arc_bloom'][j%3])


def bench(m,x,y,z,yaw=0):
    with m.at((x,y,z),yaw):
        for xx in [-1.2,1.2]:
            m.box((xx,0,.36),(.12,.8,.72),'metal')
            m.beam((xx,.30,.2),(xx,.45,1.28),.09,.09,'metal')
        for j in range(4):m.box((0,-.3+j*.20,.70),(2.8,.17,.09),'arc_trim',.016)
        for j in range(3):m.box((0,.45,.90+j*.17),(2.8,.10,.13),'arc_trim',.016)
        m.collider((0,0,.38),(2.8,.9,.76))


def fountain():
    palette();m=v.Mesh('HD_PlazaFountain')
    m.lathe((0,0,0),[(-1.1,5.2),(.1,5.2),(.1,4.75),(.36,4.75),(.36,4.15),(.68,4.15),(.78,4.35),(1.02,4.35),(1.02,3.85),(.50,3.85)],'sq_stone',64)
    for j in range(40):
        a=j*math.tau/40
        with m.at((0,0,0),math.degrees(a)):
            m.box((4.09,0,.89),(.50,.59,.22),'sq_cap',.045)
    m.poly([(3.86*math.cos(j*math.tau/64),3.86*math.sin(j*math.tau/64),.45) for j in range(64)],'sq_stone')
    m.lathe((0,0,.45),[(0,.85),(.23,.85),(.38,.62),(2.35,.35),(2.45,1.4),(2.65,1.6),(2.86,1.6),(2.95,.28),(3.95,.20),(4.08,.56),(4.25,.56),(4.40,.12),(4.85,0)],'sq_cap',32)
    return m


def fountain_water():
    palette();m=v.Mesh('HD_PlazaWater')
    for z,r in [(.91,3.83),(3.23,1.38)]:
        m.poly([(r*math.cos(j*math.tau/64),r*math.sin(j*math.tau/64),z) for j in range(64)],'sq_water')
    for j in range(8):
        a=j*math.tau/8
        for k in range(16):
            def point(t):
                rr=1.42+t*1.45;return (rr*math.cos(a),rr*math.sin(a),3.20-2.28*t*t)
            m.beam(point(k/16),point((k+1)/16),.023,.028,'sq_foam')
        x,y=2.87*math.cos(a),2.87*math.sin(a)
        m.lathe((x,y,.917),[(0,.28),(.008,.35),(.013,.28)],'sq_foam',24)
    return m


def floor(height):
    palette();m=v.Mesh('HD_PlazaFloor');r=random.Random(690)
    for x in range(660,802,2):
        for y in range(122,218,2):
            m.poly([(xx,yy,float(height(xx,yy))+.13) for xx,yy in [(x,y),(x+2,y),(x+2,y+2),(x,y+2)]],(.5,.5,.5))
    from hidamari.public_spaces import PLAZA_GARDENS
    for i in range(3300):
        if i<2900:
            gx,gy,w,d,_=r.choice(PLAZA_GARDENS)
            a=r.random()*math.tau;radius=r.uniform(1.0,4.8)
            x=gx+math.cos(a)*(w/2+radius);y=gy+math.sin(a)*(d/2+radius)
        else:x=r.uniform(662,800);y=r.uniform(124,216)
        z=float(height(x,y))+.145
        size=r.uniform(.065,.15)
        with m.at((x,y,z),r.random()*360):
            m.poly([(a*size,b*size,0) for a,b in [(-1,0),(-.5,-.35),(-.6,-.8),(0,-.5),(.6,-1),(.5,-.3),(1,0),(.5,.3),(.6,1),(0,.5),(-.6,.8),(-.5,.35)]],r.choice(['sq_leaf','arc_bloom','clay']))
    return m


def furniture(height):
    palette();m=v.Mesh('HD_Square')
    for i,(x,y,w,d) in enumerate([(686,145,3,2),(705,148,3.5,1.8),(719,156,3,1.6),(747,156,3.5,1.8),(768,166,3,1.8),(781,182,3,1.8),(683,184,3,2),(752,195,3,1.7)]):
        planter(m,x,y,float(height(x,y)),w,d,i)
    for x,y,yaw in [(713,146,0),(755,160,0),(781,176,90),(686,179,-90)]:bench(m,x,y,float(height(x,y)),yaw)
    for x,y in [(707,125),(683,142),(714,152),(759,172),(789,151),(687,194)]:lantern_post(m,x,y,float(height(x,y)))
    # Small waste bin alongside a bench, away from the main travel path.
    x,y=762,160;z=float(height(x,y))
    m.box((x,y,z+.55),(.65,.65,1.1),'green_dark',.04)
    m.box((x,y,z+1.13),(.73,.73,.13),'sq_cap',.05);m.collider((x,y,z+.55),(.7,.7,1.1))
    return m


def tree(orange=False):
    m=arcade.tree(with_planter=False);m.name='HD_PlazaTreeOrange' if orange else 'HD_PlazaTreeGold'
    if orange:
        m.colors=[(c[0]*.95,c[1]*.43,c[2]*.7,c[3]) if c[0]>.4 and c[1]>.2 and c[2]<.1 else c for c in m.colors]
    return m
