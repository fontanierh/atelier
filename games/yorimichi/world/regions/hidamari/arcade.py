"""Reference-led arcade kit: metre-scale opaque meshes and reusable shop bays."""
import math
import random
from mathutils import Matrix
from village import build as v


def palette():
    v.PALETTE.update({
        'arc_plaster':(.52,.43,.31), 'arc_timber':(.13,.065,.025),
        'arc_trim':(.23,.125,.052), 'arc_roof':(.035,.055,.078),
        'arc_cloth':(.055,.12,.19), 'arc_canvas':(.74,.61,.43),
        'arc_glass':(.075,.084,.065), 'arc_paper':(.90,.60,.24),
        'arc_stone':(.34,.30,.23), 'arc_leaf':(.78,.37,.012),
        'arc_shopglass':(.20,.095,.03), 'arc_rose':(.67,.19,.20),
        'arc_bloom':(.95,.53,.11), 'arc_ivory':(.88,.77,.51),
    })


def lantern(m,x,y,z,size=.7):
    # Start inside the scaled top cap, including the small shop lanterns.
    # A fixed +.35 left a visible gap above lanterns smaller than .525.
    m.beam((x,y,z+size*.6),(x,y,z+1.05),.045,.045,'arc_timber')
    m.lathe((x,y,z),[(size*.6*t,size*(.04+.44*math.sqrt(1-t*t))) for t in [-.98,-.9,-.75,-.5,-.25,0,.25,.5,.75,.9,.98]],'arc_paper',32)
    for dz in [-.52,-.42,-.3,-.18,-.06,.06,.18,.3,.42,.52]:
        radius=size*.48*math.sqrt(max(.15,1-(dz/.65)**2))
        m.lathe((x,y,z+dz*size),[(-.008,radius),(.008,radius)],'arc_canvas',32)
    for j in range(5):
        a=j*math.tau/5;rr=size*.15;yy=y+math.cos(a)*rr;zz=z+math.sin(a)*rr
        m.poly([(x-size*.486,yy+math.cos(t)*size*.075,zz+math.sin(t)*size*.075) for t in [k*math.tau/12 for k in range(12)]][::-1],'arc_trim')
    for dz in [-.6,.6]:m.lathe((x,y,z+size*dz),[(-.035,.12),(.035,.12)],'arc_timber',12)


def canopy(lettering):
    m=v.Mesh('HD_Arcade');palette()
    for x in range(-42,43,7):
        for y in [-6.7,6.7]:
            m.box((x,y,.28),(.59,.59,.50),'arc_stone',.014)
            m.box((x,y,3.3),(.40,.40,6.1),'arc_trim',.008)
            m.collider((x,y,3.2),(.52,.52,6.4))
            m.beam((x,y,4.9),(x,y-math.copysign(1.5,y),6.638),.20,.22,'arc_timber')
        for side in [-1,1]:
            m.beam((x,0,7.7),(x,side*7.1,6.25),.27,.30,'arc_trim')
        if x in [-42,42]:m.beam((x,-6.9,6.05),(x,6.9,6.05),.24,.28,'arc_timber')

    for y in [-6.7,6.7]:
        m.beam((-42.4,y,6.15),(42.4,y,6.15),.34,.34,'arc_timber')
    # Substantial entrance gables, tiled lip, and bracket-mounted paper lanterns.
    for x in [-42,42]:
        m.box((x,0,6.3),(.48,14.9,.5),'arc_trim')
        for side in [-1,1]:
            p=[(x,0,8.15),(x,side*7.6,6.65),(x,side*7.6,6.38),(x,0,7.88)]
            m.poly(p,'arc_timber');m.poly(p[::-1],'arc_timber')
            m.beam((x,0,8.15),(x,side*7.6,6.65),.38,.40,'arc_trim')
            # A horizontal tiled eave layers below the triangular timber gable.
            for j in range(36):
                yy=side*(j+.5)*7.6/36
                m.box((x-.22,yy,6.73),(.95,.19,.095),'arc_roof',.025)
            m.beam((x-.63,0,6.58),(x-.63,side*7.7,6.58),.18,.22,'arc_timber')
            m.beam((x-.47,0,6.42),(x-.47,side*7.7,6.42),.12,.12,'arc_trim')
            if x==-42:
                with m.at((x-.5,side*5.7,0),-90):
                    m.box((0,0,4.05),(.72,.04,2.65),'cream')
                    m.beam((-.43,0,5.42),(.43,0,5.42),.055,.055,'arc_trim')
                    for j,text in enumerate(['秋','の','市']):lettering(m,text,(0,-.05,4.9-j*.40),.57,color='arc_timber')
                    for j in range(3):
                        z=3.05+j*.18
                        m.poly([(-.22,-.04,z),(-.14,-.04,z+.16),(.04,-.04,z+.25),(.17,-.04,z+.10),(.10,-.04,z-.04)][::-1],'arc_leaf')
    return m


def canopy_lanterns():
    palette();m=v.Mesh('HD_ArcadeLanterns')
    for x in range(-42,43,7):
        lantern(m,x,0,5.65,.68)
        m.beam((x,0,6.65),(x,0,7.70),.035,.035,'arc_timber')
    for x in [-42,42]:
        for side in [-1,1]:lantern(m,x-.6,side*6.25,5.4,.82)
    return m


def roof_panels():
    palette();m=v.Mesh('HD_ArcadeRoof')
    for x in range(-42,42,7):
        for side in [-1,1]:
            p=[(x+.16,0,7.78),(x+6.84,0,7.78),(x+6.84,side*7.25,6.30),(x+.16,side*7.25,6.30)]
            m.poly(p,'arc_canvas');m.poly(p[::-1],'arc_canvas')
    for x in range(-42,42,7):
        for side in [-1,1]:
            for yy in [2.4,4.8]:
                z=7.7-yy/7.1*1.45
                m.beam((x,side*yy,z),(x+7,side*yy,z),.11,.12,'arc_timber')
    return m


def book_icon(m,x,y,z,w):
    for side in [-1,1]:
        p=[(x,y,z+w*.30),(x+side*w*.48,y,z+w*.42),(x+side*w*.48,y,z-w*.32),(x,y,z-w*.42)]
        m.poly(p,'cream');m.poly(p[::-1],'cream')
    m.box((x,y-.012,z),(.024,.022,w*.72),'arc_timber')


def window(m,x,y,z,w,h,shopfront=False):
    m.box((x,y,z),(w+.18,.18,h+.18),'arc_timber')
    if not shopfront:m.box((x,y-.11,z),(w,.04,h),'arc_glass')
    for dx in [-w/2,0,w/2]:m.box((x+dx,y-.17,z),(.09,.14,h+.17),'arc_trim')
    for dz in [-h/2,0,h/2]:m.box((x,y-.18,z+dz),(w+.2,.13,.09),'arc_trim')
    m.box((x,y-.27,z-h/2-.08),(w+.4,.50,.14),'arc_trim')


def flowers(m,x,y,z,seed=1,root_spread=(.40,.40)):
    """Flower heads may overhang; root spread must fit the container's soil."""
    r=random.Random(seed)
    for i in range(30):
        a=r.random()*math.tau;rr=r.random();xx=x+math.cos(a)*rr*root_spread[0];yy=y+math.sin(a)*rr*root_spread[1];zz=z+r.uniform(.18,.55)
        m.beam((xx,yy,z),(xx,yy,zz),.025,.025,'green_dark')
        for j in range(3):
            b=a+j*2.1
            m.poly([(xx,yy,zz-.12),(xx+math.cos(b)*.19,yy+math.sin(b)*.19,zz-.06),(xx+.06,yy+.04,zz)],'green')
        for j in range(5):
            b=j*math.tau/5
            m.poly([(xx,yy,zz+.018),(xx+math.cos(b-.4)*.11,yy+math.sin(b-.4)*.11,zz),
                    (xx+math.cos(b+.4)*.11,yy+math.sin(b+.4)*.11,zz)],['arc_ivory','arc_rose','arc_bloom'][i%3])


def shelf(m,x,y,kind,seed):
    r=random.Random(seed)
    m.box((x,y,.965),(2.15,.60,2.01),'arc_timber')
    for z in [.16,.71,1.26,1.81]:
        m.box((x,y-.10,z),(2.2,.82,.085),'arc_trim')
        for j in range(12 if kind==0 else 6):
            if kind==0:
                h=r.uniform(.24,.44);xx=x-1+j*.17
                m.box((xx,y-.24,z+h/2+.05),(.12,.36,h),['blue','cream','rust','green','clay'][r.randrange(5)],.008)
                for band in [.1,h-.06]:m.box((xx,y-.427,z+band+.05),(.095,.018,.018),'arc_ivory')
            elif kind==1:
                xx=x-.86+j*.34
                m.lathe((xx,y-.28,z+.045),[(0,.12),(.12,.15),(.22,.06),(.24,0)],'clay',8)
            else:
                v.pot(m,x-.8+j*.32,y-.2,z+.05,.45,'clay')
    m.collider((x,y,1.0),(2.2,.8,2.0))


def shop(index,lettering):
    palette();m=v.Mesh(f'HD_ArcadeShop_{index:02d}');r=random.Random(120+index)
    # Local frontage faces -Y. Contiguous 7m bays, with recessed display windows.
    # Open display recess beneath the solid upper storey.
    m.box((0,0,5.87),(6.98,10,4.46),'arc_plaster')
    for x in [-3.42,3.42]:m.box((x,0,1.8),(.14,10,3.6),'arc_plaster')
    m.box((0,-3.35,1.8),(6.84,.16,3.6),'arc_shopglass')
    m.box((0,-4.2,.15),(6.84,1.8,.15),'arc_timber')
    shelf(m,.8,-3.85,0 if index in [1,3,5] else 1,index+80)
    m.collider((0,0,3.8),(6.98,10,8.6))
    m.box((0,0,.18),(7,10,.36),'arc_stone')
    for x in [-3.43,-1.15,1.15,3.43]:m.box((x,-5.09,4.0),(.18,.24,8.0),'arc_timber')
    for z in [.38,3.6,7.9]:m.box((0,-5.12,z),(7,.27,.18),'arc_trim')
    upper_x=[-2.15,1.6] if index%2==0 else [-2.2,0,2.2]
    for x in upper_x:
        window(m,x,-5.10,5.8+(index%3)*.12,1.35 if index%2 else 1.8,1.55)
        if index in [0,3,5]:
            for dx in [-1,1]:
                xx=x+dx*(1.12 if index%2==0 else .86)
                m.box((xx,-5.23,5.8+(index%3)*.12),(.33,.12,1.62),'arc_trim')
                for k in range(8):m.box((xx,-5.31,5.12+(index%3)*.12+k*.19),(.34,.05,.07),'arc_timber')
    # Slender downpipe and a tiled ledge break the repeated window grid.
    for a,b in [((-3.18,-5.36,.5),(-3.18,-5.36,6.9)),((-3.18,-5.36,6.9),(-2.95,-5.36,7.1))]:
        m.beam(a,b,.055,.06,'metal')
    for j in range(30):m.box((-3.45+j*.235,-5.6,4.52),(.22,.78,.09),'arc_roof',.016)
    # Door and glazing with readable interior silhouettes, no fake emissive flat wall.
    window(m,-2,-5.13,1.6,1.3,2.55,shopfront=True)
    m.box((-1.65,-5.37,1.2),(.045,.09,.28),'metal')
    window(m,1.15,-5.13,1.65,3.4,2.3,shopfront=True)
    # Sloping awning + separate hanging noren panels.
    cloth=['green_dark','arc_cloth','rust','blue','arc_cloth','green'][index]
    for k in range(7):
        xa=-3.4+k*.97;xb=xa+.94
        p=[(xa,-5.2,3.45),(xb,-5.2,3.45),(xb,-6.5,3.0),(xa,-6.5,3.0)]
        m.poly(p,cloth);m.poly(p[::-1],cloth)
        m.box(((xa+xb)/2,-6.50,2.85),(.93,.045,.31),cloth)
    m.beam((-3.45,-6.48,3.0),(3.45,-6.48,3.0),.09,.09,'arc_timber')
    # Sign above the awning, painted icon plus legible authored name.
    m.box((0,-5.28,3.98),(5.65,.23,.75),'arc_timber',.04)
    lettering(m,['フラワー','本と文具','焼きたてパン','お茶','うつわ','喫茶'][index],(-.25,-5.43,3.68),.90 if index!=2 else .73)
    for x in ([-2.9] if index%2 else [2.9]):
        lantern(m,x,-5.8,3.6,.44)
        m.beam((x,-5.8,4.65),(x,-5.05,4.65),.055,.055,'arc_timber')
    if index==1:
        book_icon(m,1.1,-6.54,2.88,.42)
        book_icon(m,2.3,-5.43,4.04,.52)
    # Long shelves and individual display groups occupy only the storefront edge.
    if index in [1,2,4]:
        shelf(m,.85,-5.75,0 if index==1 else 1,index)
    else:
        for j,x in enumerate([-.25,.8,1.85]):
            v.pot(m,x,-5.85,.08,1.25,'clay')
            flowers(m,x,-5.85,.75,index*10+j,root_spread=(.18,.18))
        m.box((.8,-5.8,.365),(3.25,.95,.77),'arc_trim',.035)
        for k in range(4):m.box((.8,-6.3,.15+k*.18),(3.35,.08,.13),'arc_timber')
    if index==0:
        for tier in range(3):
            yy=-6.4+tier*.40;zz=.25+tier*.43
            m.box((.4,yy,zz),(3.5,.6,.10),'arc_trim')
            for xx in (-1.15,1.95):
                m.box((xx,yy,(zz-.09)/2),(.11,.45,zz-.01),'arc_timber')
            for j in range(6):
                xx=-1.1+j*.6
                v.pot(m,xx,yy,zz+.05,.62,'clay')
                flowers(m,xx,yy,zz+.40,tier*37+j,root_spread=(.085,.085))
    if index==1:
        m.box((.8,-6.25,.65),(2.35,.75,.12),'arc_trim')
        for xx in (-.22,1.82):
            for yy in (-6.50,-6.00):m.box((xx,yy,.275),(.12,.12,.63),'arc_timber')
        for j in range(5):
            xx=-.05+j*.43
            m.box((xx,-6.35,.87),(.33,.12,.37),['cream','blue','rust','green','clay'][j],.015)
            m.box((xx,-6.425,.9),(.19,.016,.11),'cream')
            for k in range(3):m.box((xx,-6.435,.81+k*.025),(.18,.01,.007),'arc_timber')
    # A-board: stowed inside the 8.4m facade line, outside the 10m clear route.
    with m.at((-2.6,-6.05,.05),-8):
        for x in [-.38,.38]:m.beam((x,-.2,0),(x,.1,1.15),.065,.065,'arc_trim')
        m.box((0,-.05,.67),(.76,.065,.87),'arc_timber')
        m.box((0,-.10,.67),(.65,.025,.72),'arc_glass')
        if index==1:book_icon(m,0,-.125,.82,.34)
        lettering(m,['花','本','パン','茶','器','珈琲'][index],(0,-.14,.58),.40,color='arc_ivory')
        for z in [.38,.46]:m.box((0,-.12,z),(.40,.018,.017),'cream')
    # Roof silhouette and a small eave rather than a flat box lid.
    for s in [-1,1]:
        p=[(-3.65,0,9.65),(3.65,0,9.65),(3.65,s*5.6,8.1),(-3.65,s*5.6,8.1)]
        m.poly(p,'arc_roof');m.poly(p[::-1],'arc_timber')
        for yy in range(1,7):
            y=s*yy*.8;z=9.65-abs(y)*1.55/5.6
            m.beam((-3.65,y,z),(3.65,y,z),.045,.055,'roof_edge')
        m.beam((-3.65,s*5.6,8.1),(3.65,s*5.6,8.1),.17,.20,'arc_roof')
    for x in [-3.5,3.5]:
        m.poly([(x,-5,8.1),(x,5,8.1),(x,0,9.65)],'arc_plaster')
    return m


def floor(height):
    palette();m=v.Mesh('HD_ArcadeFloor');r=random.Random(726)
    # A continuous world-space surface follows the existing street profile.
    # Paving joints live in the texture, never in individually raised colliders.
    for x in range(599,722):
        for y in range(61,89):
            h=lambda xx,yy:float(height(xx,yy))+.07
            m.poly([(x,y,h(x,y)),(x+1,y,h(x+1,y)),(x+1,y+1,h(x+1,y+1)),(x,y+1,h(x,y+1))],(.5,.5,.5))
    # Sparse flat leaf silhouettes: no collision, no fine grass or bushes in travel lanes.
    for k in range(1700):
        x=r.uniform(600,720);y=r.uniform(61,89);z=float(height(x,y))+.084;a=r.random()*math.tau
        with m.at((x,y,z),math.degrees(a)):
            m.poly([(-.105,0,0),(-.07,-.035,0),(-.075,-.07,0),(-.015,-.06,0),(.035,-.1,0),(.055,-.04,0),(.12,0,0),(.055,.04,0),(.035,.1,0),(-.015,.06,0),(-.075,.07,0),(-.07,.035,0)],r.choice(['arc_leaf','clay','arc_bloom']))
    return m


def tree(with_planter=True):
    palette();m=v.Mesh('HD_ArcadeTree');r=random.Random(187)
    m.lathe((0,0,-.3),[(0,.25),(2,.20),(5,.12),(8,.035)],'arc_timber',14)
    m.collider((0,0,2.5),(.65,.65,5.5))
    if with_planter:
        m.box((0,0,.22),(2.1,2.1,.44),'arc_timber',.03)
        m.box((0,0,.46),(1.94,1.94,.05),'soil')
        for z in [.12,.30]:
            for side in [-1,1]:
                m.box((side*1.05,0,z),(.08,2.16,.13),'arc_trim')
                m.box((0,side*1.05,z),(2.16,.08,.13),'arc_trim')
        m.collider((0,0,.22),(2.15,2.15,.44))
        for j in range(9):
            a=j*2.4;rr=.25+.6*(j%3)/2
            flowers(m,math.cos(a)*rr,math.sin(a)*rr,.49,j+250,root_spread=(.10,.10))
    for branch in range(15):
        a=branch*2.4;z=3.4+branch*.30;rr=2.6 if branch<10 else 1.6
        cx=math.cos(a)*rr;cy=math.sin(a)*rr;cz=z+1.4
        m.beam((0,0,z),(cx,cy,cz),.075,.09,'arc_timber')
        # Broad opaque folded leaf fans, clustered into a full ginkgo crown.
        for j in range(310 if with_planter else 210):
            t=r.random()*math.tau;rad=math.sqrt(r.random())*1.8
            x=cx+math.cos(t)*rad;y=cy+math.sin(t)*rad;zz=cz+r.uniform(-.75,.9)
            size=r.uniform(.055,.11)*(1 if with_planter else 1.18);col=r.choice([(.90,.46,.014),(.74,.34,.008),(.98,.61,.045),(.80,.41,.018)])
            with m.at((x,y,zz),r.random()*360):
                m.transform=m.transform@Matrix.Rotation(r.uniform(-1.1,1.1),4,'X')@Matrix.Rotation(r.uniform(-.7,.7),4,'Y')
                p=[(0,-size,0)]+[(math.cos(a)*size,math.sin(a)*size,.018) for a in [math.pi,2.75,2.4,2.05,1.7,1.45,1.1,.75,.4,0]]
                m.poly(p,col);m.poly(p[::-1],tuple(c*.95 for c in col))
    return m


def end_gate(lettering):
    """A small pass-through landmark closes the arcade vista beyond the crossing."""
    palette();m=v.Mesh('HD_ArcadeGate')
    for side in [-1,1]:
        m.box((0,side*6.2,3.3),(.62,.62,6.6),'arc_trim')
        m.collider((0,side*6.2,3.1),(.65,.65,6.8))
        m.beam((0,side*6.2,4.8),(0,side*4.8,6.6),.25,.30,'arc_timber')
        for xx in [-1.4,1.4]:m.box((xx,side*6.2,3.4),(.24,.24,6.8),'arc_timber')
        m.beam((0,0,8.8),(0,side*9,6.8),3.4,.23,'arc_roof')
        m.beam((-1.72,0,8.75),(-1.72,side*9,6.75),.22,.24,'arc_trim')
        lantern(m,-1.6,side*5.5,4.7,.8)
    m.box((0,0,6.8),(2.8,14.4,.65),'arc_timber')
    with m.at((0,0,0),-90):lettering(m,'HIDAMARI',(0,-1.46,6.56),.53)
    return m
