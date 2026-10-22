"""White plaster kura storehouse with a namako base and a timber shop annex: pottery gallery (0) or sake shop (1)."""
import math,random
from mathutils import Matrix,Vector
from village import build as v
from hidamari import arcade

ASSETS={'HD_Shop_09':0,'HD_Shop_01':1}

# Kura mass and annex footprints (front faces -Y; lot 22 x 16).
KX0,KX1,KY0,KY1=-11.0,5.0,-4.5,7.5
AX0,AX1,AY0,AY1=-11.0,-0.5,-8.0,-4.5
WALL_TOP,RIDGE=7.86,11.2
ROOF_W,ROOF_D=17.8,14.2
EAVE_EDGE=RIDGE-(RIDGE-7.9)/6*(ROOF_D/2)
# Annex pent roof: x extent, eave line y, top height at the eave / at the kura wall, vertical thickness.
RX0,RX1,RYE=AX0-.5,AX1+1.0,-8.9
RZE,RZW,RT=3.8,4.9,.36
NAM0,NAM1=.5,2.9   # namako band


def az(y):
    """Top surface height of the annex pent roof at y."""
    return RZE+(RZW-RZE)*(y-RYE)/(AY1-RYE)


def palette(variant):
    arcade.palette()
    v.PALETTE.update({
        'kura_white':(.58,.53,.43) if variant==0 else (.58,.525,.42),
        'kura_frame':(.64,.60,.51),
        'kura_lattice':(.62,.60,.55),
        'kura_inner':(.18,.20,.26),
        'kura_black':(.028,.030,.036),
        'kura_plinth':(.055,.058,.064),
        'kura_tile':(.040,.058,.084) if variant==0 else (.048,.058,.074),
        'kura_ridge':(.026,.036,.052),
        'kura_soffit':(.030,.020,.012),
        'kura_board':(.16,.10,.06),
        'kura_glow':(.55,.35,.14),
        'kura_iron':(.05,.05,.055),
        'kura_cedar':(.21,.125,.045),
        'kura_fruit':(.78,.14,.02),
        'kura_bark':(.15,.085,.04),
        'kura_twig':(.20,.12,.06),
        'kura_leaf_a':(.62,.26,.02),'kura_leaf_b':(.76,.37,.03),'kura_fallen':(.70,.30,.03),
        'kura_cloth':(.04,.05,.13),
        'kura_glaze_a':(.11,.23,.24),'kura_glaze_b':(.38,.15,.06),'kura_glaze_c':(.09,.10,.15),
        'kura_bottle':(.06,.11,.06),
        'kura_chalk':(.06,.07,.06),
    })


def face(m,pts,key,toward):
    """Polygon oriented so its front faces the `toward` direction."""
    a,b,c=[Vector(p) for p in pts[:3]]
    n=(b-a).cross(c-a)
    m.poly(pts if n.dot(Vector(toward))>=0 else list(pts)[::-1],key)


def pieces(xa,xb,holes):
    """Split [xa,xb] into intervals outside the holes."""
    out=[(xa,xb)]
    for ha,hb in holes:
        nxt=[]
        for a,b in out:
            if hb<=a or ha>=b:nxt.append((a,b));continue
            if a<ha:nxt.append((a,ha))
            if hb<b:nxt.append((hb,b))
        out=nxt
    return [(a,b) for a,b in out if b-a>.08]


def thick_text(m,lettering,text,pos,size,color='arc_ivory',depth=.06):
    """Lettering stacked into a visibly extruded sign character; pos is the front face (text faces -Y)."""
    x,y,z=pos;n=max(1,int(round(depth/.0115)))
    for k in range(n):lettering(m,text,(x,y+.006+k*.0115,z),size,color=color)


def namako(m,L,holes=()):
    """Dark stone plinth, near-black tile band z .5-2.9 with bottom rail, raised white diagonal lattice and a projecting cap rail (wall face y=0)."""
    z0,z1=NAM0,NAM1
    for a,b in pieces(-L/2-.11,L/2+.11,holes):
        m.box(((a+b)/2,-.05,(z0-.4)/2),(b-a,.14,z0+.4),'kura_plinth')
    for a,b in pieces(-L/2-.04,L/2+.04,holes):
        m.box(((a+b)/2,-.02,(z0+z1)/2),(b-a,.08,z1-z0),'kura_black')
    for a,b in pieces(-L/2-.14,L/2+.14,holes):
        m.box(((a+b)/2,-.08,z0+.075),(b-a,.20,.15),'kura_lattice',.03)
        m.box(((a+b)/2,-.08,z1+.09),(b-a,.20,.18),'kura_lattice',.04)
    za,zb=z0+.11,z1+.04;sp=.9
    for s in (1,-1):
        c=math.floor((za-L/2)/sp)*sp
        while c<=zb+L/2:
            if s>0:xa,xb=max(-L/2,za-c),min(L/2,zb-c)
            else:xa,xb=max(-L/2,c-zb),min(L/2,c-za)
            for a,b in pieces(xa,xb,holes):
                m.beam((a,-.085,s*a+c),(b,-.085,s*b+c),.05,.12,'kura_lattice')
            c+=sp


def barred_window(m,x,z,w=.9,h=1.0):
    """Deep-set barred opening, projecting plaster frame with thick head and sill, heavy shutters swung out ~115 deg (wall face y=0)."""
    m.box((x,0,z),(w+.1,.10,h+.1),'kura_black')
    for dx in (-1,1):m.box((x+dx*(w/2+.13),-.15,z),(.26,.34,h+.44),'kura_frame',.03)
    m.box((x,-.17,z+h/2+.20),(w+.8,.38,.30),'kura_frame',.05)
    m.box((x,-.19,z-h/2-.19),(w+.8,.42,.26),'kura_frame',.05)
    for k in range(4):m.box((x-w/2+(k+.5)*w/4,-.10,z),(.05,.05,h),'wood_dark')
    m.box((x,-.11,z),(w,.05,.05),'wood_dark')
    sw=w*.58;lh=h+.26
    for sx in (-1,1):
        with m.at((x+sx*(w/2+.26),-.32,z),sx*115):
            m.box((sx*(sw/2+.02),-.09,0),(sw,.18,lh),'kura_frame',.03)
            m.box((sx*(sw/2+.02),-.19,0),(sw-.16,.04,lh-.16),'kura_frame',.01)
            m.box((sx*(sw/2+.02),.005,0),(sw-.12,.03,lh-.12),'kura_inner')


def crest(m,x,z,r=.5):
    """Plaster medallion at the gable peak: three stepped discs."""
    n=20
    ring=lambda rr,y:[(x+rr*math.cos(t*math.tau/n),y,z+rr*math.sin(t*math.tau/n)) for t in range(n)]
    for rr,y0,y1,key in ((r,.02,-.16,'kura_frame'),(r*.72,-.16,-.23,'kura_lattice'),(r*.34,-.23,-.30,'kura_frame')):
        outer=ring(rr,y1);base=ring(rr,y0)
        m.poly(outer,key)
        for k in range(n):m.poly([base[k],base[(k+1)%n],outer[(k+1)%n],outer[k]],key)


def hood(m,x,y,z,w,depth,key='kura_tile'):
    """Small sloped tiled hood on a wall (face at y), projecting toward -Y."""
    top=[(x-w/2,y,z+.22),(x+w/2,y,z+.22),(x+w/2,y-depth,z),(x-w/2,y-depth,z)]
    face(m,top,key,(0,-1,1))
    face(m,[(px,py,pz-.09) for px,py,pz in top],'kura_soffit',(0,0,-1))
    m.beam((x-w/2,y-depth,z-.04),(x+w/2,y-depth,z-.04),.12,.14,'arc_timber')
    for sx in (-1,1):m.beam((x+sx*w/2,y,z+.18),(x+sx*w/2,y-depth,z-.04),.11,.12,'arc_timber')
    for j in range(max(1,int(w/.45))):
        m.box((x-w/2+.225+j*.45,y-depth,z+.06),(.40,.24,.13),key,.03)


def vent(m,x,z):
    """Dark iron vent grille under the eaves (wall face y=0)."""
    m.box((x,-.03,z),(.66,.10,.66),'kura_iron')
    for k in range(5):m.box((x,-.10,z-.22+k*.11),(.56,.05,.05),'metal')


def downpipe(m,x):
    """Downpipe held 0.2 m off the wall on two brackets, shoe at the paving, bend into the cornice."""
    m.beam((x,-.25,.1),(x,-.25,7.0),.09,.09,'metal')
    m.beam((x,-.25,7.0),(x,-.04,7.35),.08,.08,'metal')
    m.lathe((x,-.25,.05),[(0,.14),(.25,.11)],'metal',8)
    for z in (1.7,5.7):m.box((x,-.12,z),(.14,.28,.06),'metal')


def sign_board(m,lettering,x,z,w,text,size):
    """Dark wood wall sign with a plaster frame and big extruded cream characters, held 0.1 m proud of the wall (wall face y=0)."""
    h=1.45
    for dx in (-1,1):m.box((x+dx*(w/2-.3),-.05,z),(.12,.14,.4),'kura_board')
    m.box((x,-.16,z),(w,.12,h),'kura_board')
    for dz in (-1,1):m.box((x,-.17,z+dz*(h/2+.04)),(w+.16,.14,.08),'kura_frame')
    for dx in (-1,1):m.box((x+dx*(w/2+.04),-.17,z),(.08,.14,h+.16),'kura_frame')
    thick_text(m,lettering,text,(x,-.285,z-size*.28),size,depth=.06)


def gable_roof(m,cx,cy,w,d,ze,zr,soff=.08):
    """Straight-slope tiled gable, ridge along X, closed soffit, thick rounded ridge cap with end blocks."""
    x0,x1=cx-w/2,cx+w/2;k=(zr-ze)/(d/2)
    for s in (-1,1):
        ye=cy+s*d/2
        top=[(x0,cy,zr),(x1,cy,zr),(x1,ye,ze),(x0,ye,ze)]
        face(m,top,'kura_tile',(0,s,1))
        face(m,[(px,py,pz-soff) for px,py,pz in top],'kura_soffit',(0,0,-1))
        n=int(d/2/.72)
        for i in range(1,n+1):
            t=i/n;y=cy+s*d/2*t;z=zr-(zr-ze)*t
            m.beam((x0,y,z+.03),(x1,y,z+.03),.07,.07,'kura_ridge')
        j=1
        while x0+j*.55<x1-.2:
            x=x0+j*.55
            m.beam((x,cy+s*.42,zr-.42*k+.03),(x,ye,ze+.03),.05,.05,'kura_ridge');j+=1
        j=0
        while x0+.25+j*.5<x1:
            m.box((x0+.25+j*.5,ye,ze+.03),(.44,.30,.20),'kura_tile',.04);j+=1
        m.beam((x0-.12,ye-s*.05,ze-.06),(x1+.12,ye-s*.05,ze-.06),.26,.30,'arc_timber')
        for x in (x0,x1):m.beam((x,cy,zr-.03),(x,ye,ze-.03),.26,.26,'kura_ridge')
    m.box((cx,cy,zr+.10),(w+.24,.80,.28),'kura_ridge',.06)
    m.box((cx,cy,zr+.32),(w+.14,.52,.32),'kura_ridge',.13)
    for x in (x0-.06,x1+.06):m.box((x,cy,zr+.42),(.72,.88,.66),'kura_ridge',.14)


def crate(m,x,y,z,yaw=0,w=1.0,d=.8,h=.5):
    with m.at((x,y,z),yaw):
        m.box((0,0,h/2),(w,d,h),'wood_light')
        for zz in (.05,h-.05):m.box((0,0,zz),(w+.05,d+.05,.08),'wood')
        for sx in (-1,1):m.box((sx*(w/2-.05),0,h/2),(.08,d+.03,h-.02),'wood')
        m.collider((0,0,h/2),(w,d,h))


def cart(m,x,y,yaw):
    with m.at((x,y,0),yaw):
        m.box((0,0,.72),(2.0,1.1,.10),'wood_light')
        for sy in (-1,1):m.box((0,sy*.52,.98),(2.0,.06,.42),'wood')
        for sx in (-1,1):m.box((sx*.97,0,.98),(.06,1.1,.42),'wood')
        for sy in (-1,1):m.beam((-.6,sy*.36,.66),(-2.0,sy*.30,.95),.07,.07,'wood')
        m.beam((0,-.8,.55),(0,.8,.55),.08,.08,'wood_dark')
        for sx in (-1,1):m.box((.8,sx*.40,.34),(.09,.09,.72),'wood')
        for sy in (-1,1):
            with m.at((0,sy*.72,.55),0):
                m.transform=m.transform@Matrix.Rotation(math.pi/2,4,'X')
                m.lathe((0,0,0),[(-.05,.55),(.05,.55),(.05,.45),(-.05,.45),(-.05,.55)],'wood_dark',14)
                m.lathe((0,0,0),[(-.07,.10),(.07,.10),(.07,0)],'wood',10)
                m.lathe((0,0,0),[(-.07,0),(-.07,.10)],'wood',10)
                for k in range(6):
                    a=k*math.pi/6
                    m.beam((-.48*math.cos(a),-.48*math.sin(a),0),(.48*math.cos(a),.48*math.sin(a),0),.05,.045,'wood_light')
        m.collider((-.3,0,.6),(3.0,1.7,1.2))


def persimmon(m,x,y,seed):
    """Feature persimmon: thick trunk, four main limbs, a full ~5 m wide canopy of muted orange leaf clusters 3-6.5 m up, ~60 fruit, fallen leaves below."""
    r=random.Random(seed)
    m.lathe((x,y,-.3),[(0,.32),(.5,.25),(1.4,.21),(2.4,.17)],'kura_bark',9)
    m.collider((x,y,1.4),(.7,.7,3.6))
    tips=[]
    for j in range(4):
        a=j*math.tau/4+.55+r.uniform(-.25,.25)
        e=(x+math.cos(a)*1.5,y+math.sin(a)*1.5,4.1+r.uniform(-.2,.3))
        m.beam((x,y,2.0),e,.20,.20,'kura_bark');tips.append((e[0],e[1],e[2]+.3))
        for k in (-1,1):
            aa=a+k*r.uniform(.35,.8)
            f=(e[0]+math.cos(aa)*1.0,e[1]+math.sin(aa)*1.0,e[2]+r.uniform(.6,1.1))
            m.beam(e,f,.11,.11,'kura_twig');tips.append(f)
            ab=aa+r.uniform(-.7,.7)
            g=(f[0]+math.cos(ab)*.6,f[1]+math.sin(ab)*.6,f[2]+r.uniform(.3,.7))
            m.beam(f,g,.06,.06,'kura_twig');tips.append(g)
    # Filler clusters round the canopy centre so the crown reads as one solid mass.
    for k in range(6):
        a=k*math.tau/6+r.uniform(-.3,.3);rr=r.uniform(.9,1.6)
        tips.append((x+math.cos(a)*rr,y+math.sin(a)*rr,4.6+r.uniform(-.4,.6)))
    tips.append((x,y,5.3))
    for i,t in enumerate(tips):
        s=r.uniform(1.6,2.1)
        cx=min(max(t[0],x-2.3),12.3-.5*s);cy=max(t[1],-8.3+.5*s);cz=max(t[2],3.2)
        m.lathe((cx,cy,cz),[(-.48*s,0),(-.30*s,.36*s),(0,.48*s),(.30*s,.36*s),(.48*s,0)],'kura_leaf_a' if i%2 else 'kura_leaf_b',7)
        for k in range(3):
            a=r.random()*math.tau;el=r.uniform(-.6,.4)
            fx=cx+math.cos(a)*math.cos(el)*.49*s;fy=cy+math.sin(a)*math.cos(el)*.49*s;fz=cz+math.sin(el)*.49*s
            m.lathe((fx,fy,fz),[(-.09,0),(-.055,.07),(0,.09),(.055,.07),(.09,0)],'kura_fruit',6)
    for k in range(26):
        a=r.random()*math.tau;rr=.6+r.random()*2.2
        lx=x+math.cos(a)*rr;ly=y+math.sin(a)*rr
        if lx>12.3 or ly<-8.3:continue
        with m.at((lx,ly,.012),r.random()*360):
            p=[(0,-.15,0),(.10,0,0),(0,.15,0),(-.10,0,0)]
            m.poly(p,'kura_fallen');m.poly(p[::-1],'kura_fallen')


def shelf_items(m,x,y,z,w,variant,seed):
    r=random.Random(seed)
    n=7 if variant==1 else 5
    for k in range(n):
        xx=x-w/2+.3+k*(w-.6)/(n-1)
        if variant==1:
            v.pot(m,xx,y,z+.01,.5,['kura_bottle','blue','clay','kura_bottle','green_dark'][k%5],form='bottle')
        else:
            v.pot(m,xx,y,z+.01,r.uniform(.42,.55),['kura_glaze_a','kura_glaze_b','cream','kura_glaze_c','clay'][k%5],form=['bowl','jar','urn','jar','bowl'][k%5])


def a_board(m,x,y,yaw,text,lettering):
    with m.at((x,y,.05),yaw):
        for xx in (-.36,.36):m.beam((xx,-.2,0),(xx,.1,1.15),.065,.065,'arc_trim')
        m.box((0,-.05,.67),(.74,.065,.86),'arc_timber')
        m.box((0,-.10,.67),(.62,.025,.70),'kura_chalk')
        lettering(m,text,(0,-.125,.50),.8,color='arc_ivory')
        for z in (.36,.44):m.box((0,-.12,z),(.36,.018,.017),'cream')
        m.collider((0,0,.6),(.8,.45,1.2))


def annex(m,variant,lettering,sign):
    cx=(AX0+AX1)/2;L=AX1-AX0;rcx=(RX0+RX1)/2
    m.box((cx,-6.4,-.125),(L+.3,3.8,.55),'kura_plinth')
    m.box((cx,-6.25,.20),(L-.2,3.4,.10),'arc_trim')
    m.collider((cx,-6.3,1.7),(L+.2,3.6,4.2))
    m.box((cx,-5.35,1.9),(L-.3,1.9,3.2),'arc_timber')
    # End walls carried up to the pent soffit.
    for sx,x in ((-1,AX0+.1),(1,AX1-.1)):
        m.box((x,-6.25,1.75),(.2,3.5,3.5),'kura_white')
        xo=x+sx*.1
        face(m,[(xo,-8.0,3.5),(xo,-4.5,3.5),(xo,-4.5,az(-4.5)-RT-.01),(xo,-8.0,az(-8.0)-RT-.01)],'kura_white',(sx,0,0))
        m.box((x+sx*.06,-5.0,1.75),(.14,.24,3.5),'arc_timber')
        m.box((x+sx*.06,-6.25,3.30),(.14,3.4,.22),'arc_timber')
        m.box((x+sx*.06,-6.25,.55),(.14,3.4,.16),'arc_timber')
    with m.at((AX0,-6.1,0),-90):
        arcade.window(m,0,-.12,2.0,1.2,1.2)
        hood(m,0,.02,2.85,1.8,.6)
    m.box((cx,-6.0,3.5),(L-.3,3.5,.12),'kura_soffit')
    # Heavy posts on stone footings and the eave beam across them.
    for x,s in ((AX0,.30),(-7.5,.26),(-4.0,.26),(AX1,.30)):
        m.box((x,-7.85,1.575),(s,s,3.75),'arc_timber')
        m.box((x,-7.85,.02),(s+.14,s+.14,.34),'arc_stone',.02)
        m.collider((x,-7.85,1.6),(s,s,3.8))
    m.box((cx,-7.85,3.55),(L+.3,.22,.22),'arc_timber')
    # Thick tiled pent roof: a closed wedge with tile rows, eave tile ends, fascia and barge beams.
    YW=-4.3
    top=[(RX0,YW,az(YW)),(RX1,YW,az(YW)),(RX1,RYE,RZE),(RX0,RYE,RZE)]
    face(m,top,'kura_tile',(0,-1,1))
    face(m,[(px,py,pz-RT) for px,py,pz in top],'kura_soffit',(0,0,-1))
    face(m,[(RX0,RYE,RZE-RT),(RX1,RYE,RZE-RT),(RX1,RYE,RZE),(RX0,RYE,RZE)],'kura_ridge',(0,-1,0))
    for x,sx in ((RX0,-1),(RX1,1)):
        face(m,[(x,RYE,RZE-RT),(x,RYE,RZE),(x,YW,az(YW)),(x,YW,az(YW)-RT)],'kura_tile',(sx,0,0))
    for i in range(1,8):
        y=RYE+i*.6;m.beam((RX0,y,az(y)+.03),(RX1,y,az(y)+.03),.06,.06,'kura_ridge')
    j=1
    while RX0+j*.55<RX1-.2:
        x=RX0+j*.55;m.beam((x,RYE+.2,az(RYE+.2)+.03),(x,-4.6,az(-4.6)+.03),.045,.045,'kura_ridge');j+=1
    j=0
    while RX0+.15+j*.3<RX1:
        m.box((RX0+.15+j*.3,RYE-.04,RZE+.01),(.24,.22,.16),'kura_tile',.04);j+=1
    m.box((rcx,RYE+.05,RZE-RT-.08),(RX1-RX0+.06,.12,.20),'arc_timber')
    for x in (RX0,RX1):m.beam((x,RYE,RZE-.03),(x,-4.5,az(-4.5)-.03),.24,.24,'kura_ridge')
    m.box((rcx,-4.6,az(-4.5)+.06),(RX1-RX0,.24,.18),'kura_ridge')
    # Storefront bays: two lit display recesses and a sliding glass door under the noren.
    for x,w,kind in ((-9.25,3.30,'display'),(-5.75,3.30,'door'),(-2.25,3.30,'display')):
        if kind=='display':
            m.box((x,-7.87,.45),(w,.14,.62),'arc_trim')
            m.box((x,-7.92,.80),(w,.12,.10),'arc_timber')
            for j in range(1,6):m.box((x-w/2+j*w/6,-7.9,2.05),(.07,.09,2.5),'arc_timber')
            for z in (1.55,2.35):m.box((x,-7.91,z),(w,.09,.07),'arc_timber')
            m.box((x,-7.9,3.36),(w,.09,.14),'arc_timber')
            m.box((x,-7.90,2.87),(w-.1,.02,.95),'arc_shopglass')
            m.box((x,-6.65,1.75),(w-.2,.04,3.2),'kura_glow')
            m.box((x,-7.2,3.40),(w-.2,.6,.05),'arc_canvas')
            for zt in (1.05,1.85,2.65):
                m.box((x,-7.05,zt),(w-.3,.5,.07),'arc_trim')
                shelf_items(m,x,-7.15,zt+.035,w-.3,variant,int(x*10+zt*100))
            for sx in (-1,1):m.box((x+sx*(w/2-.2),-7.05,1.475),(.08,.5,2.45),'arc_trim')  # feet on the .25 m annex deck
        else:
            for dx,py in ((-.75,-7.90),(.75,-7.79)):
                m.box((x+dx,py,1.25),(1.55,.10,2.2),'arc_timber')
                m.box((x+dx,py-.06,1.25),(1.35,.04,2.0),'arc_shopglass')
                for k in (-.45,0,.45):m.box((x+dx+k,py-.09,1.25),(.045,.03,2.0),'arc_timber')
                for z in (.5,1.05,1.6,2.1):m.box((x+dx,py-.09,z),(1.35,.03,.045),'arc_timber')
            m.box((x,-7.87,2.47),(w,.14,.24),'arc_trim')
            m.box((x,-7.88,2.95),(w-.1,.03,.70),'arc_shopglass')
            for k in (-1,0,1):m.box((x+k*1.05,-7.90,2.95),(.07,.09,.72),'arc_timber')
            m.box((x,-7.9,3.36),(w,.09,.14),'arc_timber')
            m.box((x,-8.3,-.05),(3.4,.7,.30),'arc_stone');m.collider((x,-8.3,-.05),(3.4,.7,.30))
            # Noren: pole on two brackets, three indigo strips leaning slightly out, the sign on the middle one.
            m.beam((x-1.55,-8.07,3.0),(x+1.55,-8.07,3.0),.06,.06,'wood_light')
            for sx in (-1,1):m.beam((x+sx*1.4,-7.94,3.28),(x+sx*1.4,-8.07,3.03),.04,.04,'arc_timber')
            for k in (-1,0,1):
                with m.at((x+k*1.01,-8.07,2.96),0):
                    m.transform=m.transform@Matrix.Rotation(math.radians(-5),4,'X')
                    m.box((0,0,-.55),(.95,.03,1.1),'kura_cloth')
                    if k==0:
                        if len(sign)==1:thick_text(m,lettering,sign,(0,-.03,-.94),1.4,depth=.012)
                        else:
                            for j,ch in enumerate(sign):thick_text(m,lettering,ch,(0,-.03,-.34-j*.31),.65,depth=.012)
    for x in (-7.5,AX1):
        m.beam((x,-7.85,3.50),(x,-8.5,3.50),.05,.05,'arc_timber')
        arcade.lantern(m,x,-8.5,2.15,.42)


def front(m,variant,lettering,sign):
    """Upper white wall above the annex, sign between the windows, and the exposed right third at street level."""
    with m.at((-3,KY0,0),0):
        namako(m,KX1-KX0,holes=[(-8.2,2.4)])
        for x in (-5.5,1.0,5.5):barred_window(m,x,6.15)
        m.box((5.45,-.05,4.3),(5.5,.14,.20),'kura_frame',.03)
        if variant==1:
            # Cedar ball under its tiled hood, hung from a rope, next to the 酒 board.
            hood(m,-3.4,0,6.7,1.0,.55)
            m.beam((-3.4,-.32,6.62),(-3.4,-.32,6.25),.03,.03,'wood_dark')
            m.lathe((-3.4,-.32,5.75),[(-.52,0),(-.45,.28),(-.3,.44),(-.1,.52),(.1,.52),(.3,.44),(.45,.28),(.52,0)],'kura_cedar',14)
            sign_board(m,lettering,-1.2,5.7,1.8,sign,2.6)
        else:
            sign_board(m,lettering,-2.25,5.7,3.3,sign,2.4)
    # Right third at street level: planter box, big pots.
    m.box((2.6,-5.25,.3),(2.8,1.0,.6),'arc_stone',.06)
    m.box((2.6,-5.25,.62),(2.6,.84,.05),'soil')
    m.collider((2.6,-5.25,.3),(2.8,1.0,.6))
    for j,x in enumerate((1.8,2.6,3.4)):arcade.flowers(m,x,-5.25,.62,30+j)
    v.pot(m,4.4,-5.4,.02,1.1,'clay',plant=True)
    if variant==0:
        for j,x in enumerate((.5,1.2)):v.pot(m,x,-5.3,.02,.9,['kura_glaze_a','kura_glaze_b'][j],form=['urn','jar'][j])


def sides(m,variant):
    # Local frames: -Y is outward on every side.
    for cx,cy,yaw,L,door_x,gable,wins,vents,pipes in (
            (KX1,1.5,90,12,3.2,True,(-2.6,1.4),(5.0,),(-5.7,)),
            (KX0,1.5,-90,12,None,True,(-2.2,2.2),(-5.0,),(-5.7,)),
            (-3,KY1,180,16,0,False,(),(-6.8,6.8),(-7.6,7.6))):
        with m.at((cx,cy,0),yaw):
            holes=[(door_x-.9,door_x+.9)] if door_x is not None else []
            namako(m,L,holes)
            m.box((0,-.05,4.3),(L+.3,.14,.20),'kura_frame',.03)
            if door_x is not None:
                v.door(m,door_x,-.02,z=.10,w=1.1,h=2.45)
                m.box((door_x,-.45,-.15),(1.7,.9,.5),'stone_light',.03);m.collider((door_x,-.45,-.15),(1.7,.9,.5))
                hood(m,door_x,0,3.2,2.0,.85)
            if gable:
                barred_window(m,0,8.45,.85,.95)
                crest(m,0,10.1,.5)
                for x in wins:barred_window(m,x,5.3,.9,1.1)
            else:
                for x in (-5,4.5):barred_window(m,x,6.15)
                barred_window(m,0,5.3,.8,.8)
            for x in vents:vent(m,x,6.55)
            for x in pipes:downpipe(m,x)


def yard(m,variant):
    persimmon(m,10.5,-5.0,41+variant)
    cart(m,7.7,-3.6,-22)
    v.pot(m,6.0,-6.8,.02,1.45,'clay',form='urn');m.collider((6.0,-6.8,.5),(1.0,1.0,1.0))
    v.pot(m,7.2,-7.3,.02,1.15,'kura_glaze_c' if variant==0 else 'clay',form='jar');m.collider((7.2,-7.3,.4),(.8,.8,.8))
    crate(m,9.4,-6.6,0,14);crate(m,9.4,-6.6,.5,-6,.9,.7,.45)
    crate(m,10.3,-1.0,0,80,1.0,.8,.5)
    if variant==0:
        for j,x in enumerate((9.2,9.6)):v.pot(m,x,-6.6,.95,.5,['kura_glaze_a','cream'][j],form=['bowl','jar'][j])


def street_props(m,variant,lettering):
    # Crates and goods at the annex feet, away from the planter spot near x=-9, y=-9.5.
    crate(m,-8.0,-8.8,0,6);crate(m,-8.0,-8.8,.5,-4,.9,.7,.42)
    crate(m,-1.2,-9.35,0,-8,1.1,.8,.5)
    if variant==0:
        for j,(x,y) in enumerate(((-1.5,-9.4),(-.9,-9.3),(-8.0,-8.8))):
            v.pot(m,x,y,(.5 if j<2 else .92)+.01,.5,['kura_glaze_a','kura_glaze_b','cream'][j],form=['jar','bowl','urn'][j])
        v.pot(m,.3,-8.9,.02,.9,'kura_glaze_c',form='urn')
    else:
        for j in range(4):v.pot(m,-1.55+j*.25,-9.35,.51,.42,['kura_bottle','blue','clay','kura_bottle'][j],form='bottle')
        v.pot(m,-.2,-9.0,.02,1.0,'clay',form='jar')
    a_board(m,-3.4,-8.95,-12,'器' if variant==0 else '酒',lettering)
    v.pot(m,-10.6,-8.6,.02,.8,'clay',plant=True)


def build(name,variant,lettering):
    palette(variant)
    m=v.Mesh(name)
    sign='うつわ' if variant==0 else '酒'
    # Main kura mass with warm plaster, bevelled cornice band and closed gables.
    m.box((-3,1.5,(WALL_TOP-.4)/2),(KX1-KX0,KY1-KY0,WALL_TOP+.4),'kura_white')
    m.collider((-3,1.5,3.7),(KX1-KX0,KY1-KY0,8.2))
    m.box((-3,1.5,7.3),(KX1-KX0+.6,KY1-KY0+.6,.5),'kura_frame',.14)
    for x,sx in ((KX1,1),(KX0,-1)):
        face(m,[(x,KY0,WALL_TOP),(x,KY1,WALL_TOP),(x,1.5,RIDGE-.08)],'kura_white',(sx,0,0))
    gable_roof(m,-3,1.5,ROOF_W,ROOF_D,EAVE_EDGE,RIDGE)
    front(m,variant,lettering,sign)
    sides(m,variant)
    annex(m,variant,lettering,sign)
    street_props(m,variant,lettering)
    yard(m,variant)
    return m
