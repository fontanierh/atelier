"""The coconut stand on the cove, rebuilt against docs/reconcile/stand.png: an open plank hut under a thick gabled
thatch with ragged eaves, a tall coconut signboard standing on the ridge, a hip-height counter stacked with big
yellow-green coconuts, a string of coconuts on the post, a chalkboard easel, a stool, a crate of shoots, a tall
leaning nobori beside it and two grey boulders. Front (the counter) faces -Y; place it so -Y faces the lane.
Footprint about 3.6 m (x) by 4.2 m (y) including the banner and boulders; the hut itself is 2.6 x 1.8 m."""
import math, random
from mesh import Mesh
R=random.Random(11)

# warmer, darker wood than the shared palette (linear values; the game's exposure lifts mid tones)
WOOD=(.15,.075,.030);WOOD_LIGHT=(.21,.115,.048);WOOD_DARK=(.055,.026,.011);WOOD_WARM=(.18,.085,.034)
INTERIOR=(.030,.016,.008);POST=(.085,.040,.016)
STRAW=(.40,.26,.085);STRAW_LIGHT=(.52,.36,.13);STRAW_DARK=(.20,.12,.040);STRAW_EDGE=(.14,.08,.028)
COCO=(.27,.34,.070);COCO_LIGHT=(.36,.42,.11);COCO_CAP=(.80,.70,.42);COCO_HUSK=(.13,.07,.025)
BOULDER=(.062,.060,.078);BOULDER_LIGHT=(.115,.11,.135);SLAB=(.16,.15,.14)
RUST=(.60,.13,.035);RUST_DARK=(.34,.07,.02);CHALK=(.040,.045,.040);CREAM=(.78,.66,.42);WHITE=(.85,.82,.72)
SHOOT=(.10,.18,.03);SHOOT_LIGHT=(.17,.26,.05);ROPE=(.40,.28,.12)
PLANKS=[WOOD,WOOD_LIGHT,WOOD_WARM,WOOD]

def coconut(m,c,r=.15,color=COCO,cap=True):
    m.sphere(c,r,color,n=7,squash=1.12,rings=5)
    if cap:m.lathe((c[0],c[1],c[2]+r*1.02),[(0,r*.30),(.03,r*.26),(.045,0)],COCO_CAP,n=7)

def boulder(m,c,r,seed):
    rr=random.Random(seed);n=7;rings=4
    x,y,z=c
    prof=[(-r*.75*math.cos(i*math.pi/rings),r*math.sin(i*math.pi/rings)) for i in range(rings+1)]
    prof[0]=(-r*.75,0);prof[-1]=(r*.75,0)
    ringpts=[[(x+rad*rr.uniform(.8,1.15)*math.cos(i*2*math.pi/n+rr.uniform(-.15,.15)),y+rad*rr.uniform(.8,1.15)*math.sin(i*2*math.pi/n),z+zz+rr.uniform(-r*.05,r*.05)) for i in range(n)] for zz,rad in prof]
    for k,(a,b) in enumerate(zip(ringpts[:-1],ringpts[1:])):
        for i in range(n):m.poly([a[i],a[(i+1)%n],b[(i+1)%n],b[i]],BOULDER_LIGHT if k>=rings-2 else BOULDER)
    m.poly(ringpts[-1],BOULDER_LIGHT)

def thatch(m,W,D,ridge_z,front_eave,back_eave,T=.24):
    """Gabled thatch, ridge along X. Thick slabs on both slopes made of straw bands, ragged fringes on every eave,
    closed gable ends, dark underside."""
    y_f,y_b=-D/2-.80,D/2+.55;z_f,z_b=front_eave,back_eave;X0,X1=-W/2-.42,W/2+.42
    def slope(y0,z0,y1,z1,bands,flip):
        L=math.hypot(y1-y0,z1-z0);dy,dz=(y1-y0)/L,(z1-z0)/L;ny,nz=-dz,dy
        if nz<0:ny,nz=-ny,-nz
        def P(x,u,lift=0):return (x,y0+u*dy+lift*ny,z0+u*dz+lift*nz)
        cols=int((X1-X0)/.36)+1
        for b in range(bands):
            u0,u1=b*L/bands,(b+1)*L/bands;um=(u0+u1)/2
            c0=[STRAW_LIGHT,STRAW,STRAW_LIGHT,STRAW][b%4];step=.035
            for k in range(cols):
                x0=X0+k*(X1-X0)/cols;x1=X0+(k+1)*(X1-X0)/cols;h0=R.uniform(0,.012);h1=R.uniform(0,.012)
                q=[P(x0,u0,h0+step),P(x1,u0,h1+step),P(x1,u1,h1),P(x0,u1,h0)];m.poly(q if not flip else q[::-1],c0)
                q=[P(x0,u1,h0),P(x1,u1,h1),P(x1,u1+.03,h1-step),P(x0,u1+.03,h0-step)];m.poly(q if not flip else q[::-1],STRAW_DARK)   # the layer's lower edge
        # thick underside and the eave face
        q=[P(X0,0,-T),P(X0,L,-T),P(X1,L,-T),P(X1,0,-T)];m.poly(q if flip else q[::-1],STRAW_DARK)
        n=int((X1-X0)/.20)
        for k in range(n):
            x0=X0+k*(X1-X0)/n;x1=X0+(k+1)*(X1-X0)/n;xm=(x0+x1)/2;sag=.04+R.uniform(0,.04)
            a,b_,c=P(x0,L,0),P(x1,L,0),P(x1,L,-T);d=(xm,y1,z1-T-sag);e=P(x0,L,-T)
            q=[a,b_,c,d,e];m.poly(q if not flip else q[::-1],STRAW_EDGE)
        for k in range(int((X1-X0)/.09)):
            x=X0+k*.09+R.uniform(-.02,.02);ln=.07+R.uniform(0,.10);w=.04+R.uniform(0,.03)
            col=R.choice([STRAW_DARK,STRAW,STRAW_EDGE])
            a=P(x-w/2,L-.02,-T*.5);b_=P(x+w/2,L-.02,-T*.5);c=(x+w*.2,y1+(.03 if y1>0 else -.03),z1-T-ln);d=(x-w*.2,y1+(.03 if y1>0 else -.03),z1-T-ln)
            m.poly([a,b_,c,d],col);m.poly([b_,a,d,c],STRAW_DARK)
        # side fringes along the gable edges
        for xs,x in ((-1,X0),(1,X1)):
            for k in range(int(L/.11)):
                u=k*.11+R.uniform(0,.03);ln=.06+R.uniform(0,.09);w=.05
                a=P(x,u,-T*.5);b_=P(x,u+w,-T*.5);c=(x+xs*.03,a[1],a[2]-ln);d=(x+xs*.03,b_[1],b_[2]-ln)
                m.poly([a,b_,d,c],STRAW_DARK);m.poly([b_,a,c,d],STRAW_EDGE)
        return P,L
    slope(0,ridge_z,y_f,z_f,5,False)      # front slope: from the ridge down to the front eave
    slope(0,ridge_z,y_b,z_b,4,True)       # back slope
    # gable ends: closed straw triangles between the slopes (thick) and a ridge cap
    for x,order in ((X0,1),(X1,-1)):
        pts=[(x,y_f,z_f-T),(x,0,ridge_z-T),(x,y_b,z_b-T)]
        m.poly(pts if order>0 else pts[::-1],STRAW_DARK)
        pts=[(x,y_f,z_f),(x,0,ridge_z+.02),(x,y_b,z_b),(x,y_b,z_b-T),(x,0,ridge_z-T),(x,y_f,z_f-T)]
        m.poly(pts if order>0 else pts[::-1],STRAW_EDGE)
    m.beam((X0,0,ridge_z+.05),(X1,0,ridge_z+.05),.30,.11,STRAW_DARK);m.beam((X0+.02,0,ridge_z+.11),(X1-.02,0,ridge_z+.11),.20,.06,STRAW)
    for k in range(5):
        x=X0+.25+k*(X1-X0-.5)/4;m.beam((x,-.30,ridge_z-.02),(x,.30,ridge_z-.02),.035,.035,POST);m.beam((x,-.28,ridge_z+.18),(x,.28,ridge_z+.18),.035,.035,POST)

def signboard(m,z):
    """Two stacked planks on short posts standing on the ridge, with a faceted coconut and a cut half painted on."""
    with m.at((0,.02,z)):
        for x in (-.52,.52):m.beam((x,0,-.22),(x,0,.50),.08,.08,POST)
        m.box((0,0,.22),(1.36,.06,.40),WOOD_WARM);m.box((0,0,.55),(1.22,.06,.26),WOOD_LIGHT)
        m.box((0,0,.42),(1.36,.064,.03),WOOD_DARK)
        m.sphere((-.16,-.05,.26),.17,COCO_LIGHT,n=7,squash=1.15,rings=4)
        m.lathe((.20,-.045,.20),[(0,0),(0,.13)],CREAM,n=8);m.lathe((.20,-.05,.20),[(0,0),(0,.095)],WHITE,n=8)
        m.lathe((.20,-.052,.20),[(0,0),(0,.035)],WOOD_DARK,n=6)

def build():
    m=Mesh('SW_CoconutStand')
    W,D=2.6,1.8;H=1.95                       # bay width/depth, eave post height at the front
    RIDGE=2.60;FRONT_EAVE=1.84;BACK_EAVE=2.00
    # posts: four corners, thicker, dark; the back ones taller
    for x in (-W/2,W/2):
        m.box((x,-D/2,H/2),(.13,.13,H),POST);m.box((x,D/2,(H+.25)/2),(.13,.13,H+.25),POST)
    # back wall: planks up to the shelf, then open under the roof so light comes through
    for k in range(4):
        z=.17+k*.30;m.box((0,D/2-.02,z),(W-.1,.05,.28),PLANKS[k%4])
    m.box((0,D/2-.045,.68),(W-.12,.02,1.36),INTERIOR)                                  # dark interior face
    for sx in (-1,1):
        for k in range(4):m.box((sx*(W/2-.02),0,.17+k*.30),(.05,D-.3,.28),PLANKS[(k+1)%4])
    m.beam((-W/2,D/2,H+.2),(W/2,D/2,H+.2),.09,.09,WOOD_DARK);m.beam((-W/2,-D/2,H-.05),(W/2,-D/2,H-.05),.09,.09,WOOD_DARK)   # wall plates
    for sx in (-1,1):m.beam((sx*W/2,-D/2,H-.05),(sx*W/2,D/2,H+.2),.08,.08,WOOD_DARK)     # side plates
    m.beam((0,-D/2,H-.05),(0,D/2,H+.2),.08,.08,WOOD_DARK)                                # centre tie
    for sx in (-1,1):m.beam((sx*(W/2-.05),-D/2+.02,.95),(sx*(W/2-.35),-D/2+.02,H-.15),.06,.06,WOOD)   # knee braces
    # shelf at the back with cups and a jug, a lantern under the ridge
    m.box((0,D/2-.24,1.28),(W-.3,.30,.045),WOOD_LIGHT)
    for k in range(5):m.lathe((-.75+k*.30,D/2-.26,1.30),[(0,0),(0,.05),(.09,.055),(.09,0)],[CREAM,(.06,.12,.30),WHITE][k%3],n=8)
    m.lathe((.85,D/2-.26,1.30),[(0,0),(0,.07),(.12,.10),(.22,.08),(.26,.045)],(.46,.235,.085),n=9)
    m.beam((.55,.1,H+.1),(.55,.1,H-.12),.012,.012,ROPE);m.lathe((.55,.1,H-.40),[(0,.06),(.05,.13),(.20,.13),(.26,.06)],(.92,.58,.22),n=8)
    # counter: hip height, plank top, horizontal plank apron, side returns
    m.box((0,-D/2+.02,.95),(W+.16,.62,.075),WOOD_LIGHT,bevel=.012)
    for k in range(4):m.box((0,-D/2-.22,.14+k*.20),(W-.1,.05,.18),PLANKS[(k+2)%4])
    for sx in (-1,1):
        for k in range(4):m.box((sx*(W/2-.02),-D/2+.06,.14+k*.20),(.05,.55,.18),PLANKS[(k+1)%4])
    m.beam((-W/2-.08,-D/2-.28,.90),(W/2+.08,-D/2-.28,.90),.06,.09,WOOD_DARK)               # counter lip
    # roof, signboard on the ridge
    thatch(m,W,D,RIDGE,FRONT_EAVE,BACK_EAVE)
    signboard(m,RIDGE+.20)
    # coconuts: a pyramid on the counter (left), a row on the right, a string of four hanging from the left post
    py=-D/2-.02
    base=[(-.70,py-.14),(-.40,py-.14),(-.55,py+.12),(-.85,py+.12),(-.25,py+.12),(-.55,py-.40)]
    for (x,y) in base:coconut(m,(x,y,.99+.15))
    for (x,y) in [(-.55,py-.15),(-.70,py+.10),(-.40,py+.10)]:coconut(m,(x,y,.99+.15+.26))
    coconut(m,(-.55,py-.02,.99+.15+.52))
    for k,(x,y) in enumerate([(.35,py-.10),(.65,py+.05),(.95,py-.12)]):coconut(m,(x,y,.99+.15),.15,COCO_LIGHT if k%2 else COCO)
    coconut(m,(.15,py+.20,.99+.13),.13,COCO_HUSK,cap=False);coconut(m,(1.05,py+.22,.99+.13),.13,COCO_HUSK,cap=False)
    m.lathe((.05,py-.30,.99),[(0,0),(0,.075),(.16,.095),(.17,.085)],COCO_LIGHT,n=8);m.lathe((.05,py-.30,1.15),[(0,0),(0,.07)],WHITE,n=8)   # opened coconut with a straw
    m.beam((.05,py-.30,1.16),(.12,py-.36,1.42),.012,.012,RUST)
    with m.at((-W/2-.02,-D/2-.16,0)):
        # The lowest fruit is centred at .61: the old .95 rope endpoint
        # stopped above it. Carry the cord through the whole string and tie
        # each offset cap back to it so every fruit has a visible attachment.
        m.beam((0,0,H-.10),(0,0,H-.35-3*.33-.17),.035,.035,ROPE)
        for k in range(4):
            cx=R.uniform(-.04,.04);cz=H-.35-k*.33
            coconut(m,(cx,-.02,cz),.14,COCO if k%2 else COCO_LIGHT)
            m.beam((0,0,cz+.19),(cx,-.025,cz+.14),.045,.035,ROPE)
    # chalkboard easel at the front right, leaning: A-frame legs, dark board, chalk coconut and price marks
    with m.at((W/2+.05,-D/2-.60,0),yaw=-22):
        for sx in (-1,1):
            m.beam((sx*.30,-.10,0),(sx*.24,-.02,1.02),.04,.04,WOOD);m.beam((sx*.26,.14,0),(sx*.24,.0,1.02),.035,.035,WOOD)
        m.beam((-.25,-.01,1.02),(.25,-.01,1.02),.05,.05,WOOD)
        with m.at((0,-.05,.50),pitch=-6):
            m.box((0,0,0),(.66,.035,.86),WOOD_LIGHT);m.box((0,-.02,0),(.58,.01,.78),CHALK)
            m.lathe((-.05,-.03,.12),[(0,0),(0,.13)],WHITE,n=9);m.lathe((-.05,-.035,.12),[(0,0),(0,.10)],CHALK,n=9)
            for k in range(3):m.box((-.14+k*.14,-.03,-.20),(.10,.004,.025),WHITE)
            m.beam((-.20,-.03,.31),(.20,-.03,.31),.016,.004,RUST)
    # stool and the crate of shoots on a stone slab, front right
    with m.at((W/2+1.0,-D/2-.72,0)):
        m.lathe((0,0,.46),[(0,0),(0,.17),(.045,.18),(.055,.16)],WOOD_LIGHT,n=8)
        for k in range(3):
            a=k*2*math.pi/3+.5;m.beam((math.cos(a)*.13,math.sin(a)*.13,0),(math.cos(a)*.10,math.sin(a)*.10,.46),.04,.04,WOOD)
    with m.at((W/2+.62,-D/2-.95,0)):
        m.box((0,0,.03),(.70,.60,.06),SLAB)
        m.box((0,0,.24),(.40,.34,.36),WOOD_LIGHT,bevel=.01)
        for k in range(3):m.box((0,0,.10+k*.13),(.42,.36,.03),WOOD_DARK)
        for k in range(7):
            a=k*2*math.pi/7;x,y=math.cos(a)*.11,math.sin(a)*.09;h=.28+R.uniform(0,.16)
            m.poly([(x-.03,y,.42),(x+.03,y,.42),(x+.01,y+.02,.42+h)],SHOOT_LIGHT if k%2 else SHOOT)
            m.poly([(x+.03,y,.42),(x-.03,y,.42),(x-.01,y+.02,.42+h)],SHOOT)
    # crate of coconuts at the front left
    with m.at((-W/2-.55,-D/2-.30,0),yaw=12):
        m.box((0,0,.19),(.46,.40,.38),WOOD_LIGHT,bevel=.012)
        for k in range(3):m.box((0,0,.07+k*.13),(.48,.42,.03),WOOD_DARK)
        for (x,y,z) in [(-.09,-.04,.46),(.10,.05,.46),(0,.0,.70)]:coconut(m,(x,y,z),.14)
    # tall nobori on a dark pole with a cross-bar, leaning a few degrees, right of the stand
    with m.at((W/2+1.05,-D/2-.05,0),roll=-4,yaw=-8):
        m.lathe((0,0,0),[(0,.035),(3.05,.025)],POST,n=6);m.lathe((0,0,3.05),[(0,.05),(.06,.05),(.09,0)],WOOD_DARK,n=6)
        m.beam((-.02,0,2.95),(.36,0,2.95),.03,.03,POST)
        for k in range(10):m.box((.19,0,2.85-k*.20),(.32,.014,.20),RUST if k%4 else RUST_DARK)
        m.box((.19,-.009,2.35),(.16,.006,.16),CREAM)
    # two grey boulders: a big one behind left, a small one front right
    boulder(m,(-W/2-.95,D/2+.45,-.15),.62,3);boulder(m,(W/2+1.45,-D/2-1.0,-.08),.34,5)
    m.collider((0,0,H/2),(W+.4,D+1.2,H+.3))
    return m
