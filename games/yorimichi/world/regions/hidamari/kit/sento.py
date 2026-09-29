"""Neighbourhood sento: two-tier dark tiled hip roof with tile courses and rafter tails, projecting karahafu porch with a ゆ noren, brick chimney, glazed coin-laundry annex."""
import math,random
from mathutils import Vector
from village import build as v
from hidamari import arcade

ASSETS={'HD_Shop_13':0,'HD_Shop_05':1}

MX0,MX1=-11.5,5.5;MY0,MY1=-7.0,7.0      # main block footprint (ground storey)
UX0,UX1=-10.5,4.5;UY0,UY1=-5.5,5.5      # upper storey, set back under the skirt roof
GT=4.45;UT=7.3                           # ground / upper storey wall tops (the skirt hides the ground top)
PX=-1.5                                  # porch centre
AX0,AX1=5.45,11.5;AY0,AY1=-5.6,3.0       # coin-laundry annex box; the glazed bay stands in front (y -6.6..-5.6)
AT=3.0                                   # annex wall top
T='sento_timber';P='sento_plaster';S='sento_soffit'


def palette(variant):
    arcade.palette()
    v.PALETTE.update({
        'sento_tile':(.032,.041,.064) if variant==0 else (.034,.042,.058),   # dark slate-indigo (machiya/kura range)
        'sento_edge':(.018,.023,.038),
        'sento_plaster':(.62,.55,.42) if variant==0 else (.58,.53,.44),
        'sento_gable':(.58,.55,.48),
        'sento_timber':(.10,.05,.02) if variant==0 else (.12,.065,.028),
        'sento_trim':(.21,.115,.048),
        'sento_soffit':(.26,.17,.09),
        'sento_noren':(.07,.15,.30) if variant==0 else (.05,.11,.26),
        'sento_red':(.60,.12,.10),
        'sento_cream':(.62,.58,.50),
        'sento_white':(.78,.73,.62),
        'sento_brick':(.48,.22,.15) if variant==0 else (.42,.20,.14),
        'sento_brick_dark':(.36,.16,.11),
        'sento_bamboo':(.62,.50,.24),
        'sento_stalk':(.45,.50,.22),
        'sento_hedge':(.10,.17,.08),'sento_hedge_top':(.14,.22,.10),
        'sento_leaf':(.16,.28,.09),'sento_leaf2':(.11,.20,.07),
        'sento_stone':(.42,.42,.40),
        'sento_granite':(.12,.12,.13),
        'sento_machine':(.66,.66,.64),'sento_drum':(.08,.09,.12),'sento_panel':(.35,.55,.70),
        'sento_glow':(.70,.45,.06),      # amber 'leaf' emission behind the lattices (machiya mushiko trick)
    })


def ring(m,outer,inner,zo,zi,key,strips=10,fascia=.24,tips=.0,bare=(),pitch=.45,rafters=.6):
    """Sloped tiled band between an outer eave rectangle and an inner rectangle (a wall line, or a
    ridge given as a degenerate rectangle). Corners listed counter-clockwise seen from above.
    Every plane gets tile courses every `pitch` m, a heavy dark fascia with rafter tails under the
    skin and a round-ish cap on the hip line. Sides in `bare` (buried under another roof) get only
    the skin, courses and hip cap."""
    cx=sum(p[0] for p in outer)/4;cy=sum(p[1] for p in outer)/4
    for k in range(4):
        a=Vector((*outer[k],zo));b=Vector((*outer[(k+1)%4],zo));c=Vector((*inner[(k+1)%4],zi));d=Vector((*inner[k],zi))
        for j in range(strips):
            p=[a.lerp(b,j/strips),a.lerp(b,(j+1)/strips),d.lerp(c,(j+1)/strips),d.lerp(c,j/strips)]
            m.poly(p,v.color_variant(key,.05));m.poly(p[::-1],S)
        run=(d-a).length
        for r in range(1,int(run/pitch)+1):
            t=r*pitch/run
            if t>.96:break
            m.beam(a.lerp(d,t)+Vector((0,0,.035)),b.lerp(c,t)+Vector((0,0,.035)),.06,.05,'sento_edge')
        if run>.3:m.beam(a+Vector((0,0,.07)),d+Vector((0,0,.10)),.30,.22,'sento_edge')
        if k in bare:continue
        m.beam(a,b,.18,fascia,T)
        m.beam(a+Vector((0,0,fascia*.5)),b+Vector((0,0,fascia*.5)),.16,.12,'sento_edge')
        slope=((c+d)/2-(a+b)/2).normalized();ab=(b-a).length
        for i in range(int(ab/rafters)+1):
            s=(i+.5)*rafters/ab
            if s>=1:break
            p=a.lerp(b,s)+slope*.06-Vector((0,0,.08))
            m.beam(p,p+slope*.9,.10,.10,T)
        if tips:
            o=Vector((a.x-cx,a.y-cy,0)).normalized()
            m.beam(a-o*.25+Vector((0,0,.05)),a+o*tips+Vector((0,0,tips*.7)),.16,.16,'sento_edge')


def disc_y(m,x,y,z,r,depth,key,n=12):
    """Short cylinder along Y whose front face looks toward -Y."""
    f=[(x+r*math.cos(k*math.tau/n),y,z+r*math.sin(k*math.tau/n)) for k in range(n)]
    b=[(xx,y+depth,zz) for xx,_,zz in f]
    m.poly(f,key);m.poly(b[::-1],key)
    for k in range(n):m.poly([f[k],b[k],b[(k+1)%n],f[(k+1)%n]],key)


def karahafu(m,cx,yf,yb,ze,zf,half=2.9,rise=1.7,skin=.7,n=14):
    """Curved cusped gable projecting in front of the skirt eave: an ogee bargeboard swept through n
    segments, the 0.15 m tile skin behind it rising into the skirt/upper wall, a curved ridge cap on
    top, plaster face below the curve, returns at the flank ends. Returns the curve height function."""
    def zc(t):
        u=1-abs(t);s=u**1.35;return ze+rise*s*s*(3-2*s)
    ts=[-1+2*i/n for i in range(n+1)];xs=[cx+half*t for t in ts]
    ytop=yf+.10;yface=yf+.16
    for i in range(n):
        x0,x1=xs[i],xs[i+1];za,zb=zc(ts[i]),zc(ts[i+1])
        m.beam((x0,yf,za+.05),(x1,yf,zb+.05),.25,.30,T)
        m.beam((x0,yf+.14,za+.24),(x1,yf+.14,zb+.24),.22,.14,'sento_edge')
        top=[(x0,ytop,za),(x1,ytop,zb),(x1,yb,zb+skin),(x0,yb,za+skin)]
        bot=[(x0,ytop,za-.15),(x1,ytop,zb-.15),(x1,yb,zb+skin-.15),(x0,yb,za+skin-.15)]
        m.poly(top,v.color_variant('sento_tile',.05));m.poly(bot[::-1],S)
        for f in [.3,.6]:
            y=ytop+(yb-ytop)*f
            m.beam((x0,y,za+skin*f+.035),(x1,y,zb+skin*f+.035),.06,.05,'sento_edge')
        if max(za,zb)>zf+.08:
            m.poly([(x0,yface,zf),(x1,yface,zf),(x1,yface,max(zb-.05,zf+.02)),(x0,yface,max(za-.05,zf+.02))],'sento_gable')
    for s in [-1,1]:
        x=cx+s*half
        m.box((x,yf,ze+.05),(.32,.34,.36),T)
        p=[(x,ytop,ze-.15),(x,ytop,ze),(x,yb,ze+skin),(x,yb,ze+skin-.15)]
        m.poly(p,'sento_edge');m.poly(p[::-1],'sento_edge')
    return zc


def gegyo(m,x,y,z):
    """Carved pendant under the karahafu apex: a lathe-like disc, wedge tail and two ears."""
    disc_y(m,x,y,z,.22,.08,'wood_light',12)
    disc_y(m,x,y-.02,z,.13,.05,'sento_trim',12)
    m.box((x,y+.03,z-.33),(.12,.08,.22),'wood_light')
    m.box((x,y+.03,z-.44),(.26,.06,.06),'wood_light')
    for s in [-1,1]:m.box((x+s*.34,y+.03,z+.05),(.14,.08,.12),'wood_light')


def band(m,x,y,z,w=2.3,h=.85):
    """High four-pane lattice window, warm-lit."""
    m.box((x,y,z),(w+.24,.16,h+.24),T)
    m.box((x,y-.10,z),(w,.04,h),'paper')
    for j in range(5):m.box((x-w/2+j*w/4,y-.14,z),(.09,.10,h+.16),'sento_trim')
    for dz in [-h/2,h/2]:m.box((x,y-.14,z+dz),(w+.22,.10,.09),'sento_trim')
    m.box((x,y-.16,z-h/2-.13),(w+.44,.30,.12),'sento_trim')


def koshi(m,x,y,z,w,h,glow=True):
    """Ground-floor timber lattice window: amber-lit panel 0.06 m behind 0.05 m slats at 0.14 m pitch."""
    m.box((x,y,z),(w+.26,.18,h+.26),T)
    m.box((x,y-.125,z),(w,.05,h),'sento_glow' if glow else 'arc_glass')
    n=max(2,int(round(w/.14)))
    for j in range(n+1):m.box((x-w/2+j*w/n,y-.235,z),(.05,.05,h+.06),T)
    for dz in [-h/3,h/3]:m.box((x,y-.245,z+dz),(w+.05,.06,.05),T)
    m.box((x,y-.25,z-h/2-.24),(w+.5,.46,.18),T)


def shoji(m,x,y,z,w,h):
    """Lit paper panel with slats (porch side walls)."""
    m.box((x,y,z),(w+.26,.12,h+.26),T)
    m.box((x,y-.08,z),(w,.05,h),'paper')
    for j in range(4):m.box((x-w/2+j*w/3,y-.12,z),(.05,.04,h),T)
    for j in range(5):m.box((x,y-.12,z-h/2+j*h/4),(w,.04,.05),T)
    m.box((x,y-.12,z-h/2-.2),(w+.4,.24,.12),'sento_trim')


def framing(m,y,x0,x1,zb,zt,posts,rails=()):
    """Dark posts and rails on a plaster wall facing local -Y at y, with a purlin along the wall top."""
    for x in posts:m.box((x,y-.07,(zt+zb)/2),(.20,.16,zt-zb),T)
    for z in rails:m.box(((x0+x1)/2,y-.05,z),(x1-x0+.12,.14,.16),'sento_trim')
    m.box(((x0+x1)/2,y-.08,zt-.09),(x1-x0+.12,.22,.18),T)


def downpipe(m,x,y,top):
    m.beam((x,y,-.2),(x,y,top),.07,.07,'metal')
    m.beam((x,y,top),(x,y+.5,top+.28),.07,.07,'metal')
    m.lathe((x,y,.05),[(0,.12),(.25,.12),(.3,.08)],'metal',8)


def stone_lantern(m,x,y):
    m.lathe((x,y,-.05),[(0,.48),(.28,.48),(.34,.30),(.40,.20),(1.30,.18),(1.36,.30),(1.50,.32),(1.52,0)],'arc_stone',8)
    m.box((x,y,1.78),(.50,.50,.52),'arc_stone')
    for yaw in [0,90,180,270]:
        with m.at((x,y,0),yaw):m.box((0,-.26,1.78),(.22,.03,.26),'paper')
    m.lathe((x,y,2.02),[(0,.28),(.06,.60),(.42,.10),(.60,0)],'arc_stone',6)
    m.collider((x,y,1.2),(.7,.7,2.6))


def tubs(m,x,y):
    """Stacked wooden bath tubs and a bucket, the laundry-yard version of the props."""
    for j,(dx,dy,z) in enumerate([(0,0,0),(0,0,.36),(.62,.1,0)]):
        m.lathe((x+dx,y+dy,z),[(0,.27),(.02,.30),(.30,.33),(.34,.30),(.34,0)],'wood_light',10)
        for zz in [.08,.26]:m.lathe((x+dx,y+dy,z+zz),[(-.015,.335),(.015,.335)],'metal',10)
    m.collider((x+.25,y,.4),(1.3,.75,.8))


def washing_machine(m,x,y,z):
    """0.7 m front loader: pale box, dark drum disc, light-blue control strip."""
    m.box((x,y,z+.475),(.70,.70,.95),'sento_machine',.02)
    front=y-.352
    m.box((x,front,z+.86),(.56,.03,.07),'sento_panel')
    disc_y(m,x,front-.02,z+.44,.22,.03,'sento_drum',12)
    disc_y(m,x,front-.035,z+.44,.15,.02,'arc_glass',12)


def notice_board(m,x,y,z,lettering):
    m.box((x,y,z),(.9,.08,1.3),'wood_dark')
    m.box((x,y-.05,z),(.78,.02,1.16),'sento_cream')
    lettering(m,'松の湯',(x,y-.072,z+.28),.20,color='wood_dark')
    lettering(m,'営業中',(x,y-.072,z-.02),.16,color='wood_dark')
    lettering(m,'午後三時',(x,y-.072,z-.30),.16,color='wood_dark')


def price_board(m,x,y,lettering):
    m.box((x,y,.85),(.12,.12,2.3),'wood_dark')
    m.box((x,y-.05,1.35),(1.0,.08,1.4),'wood_dark')
    m.box((x,y-.05,2.12),(1.1,.24,.15),'sento_tile');m.box((x,y-.05,2.21),(1.16,.28,.05),'sento_edge')
    lettering(m,'入浴料',(x,y-.10,1.78),.20,color='sento_cream')
    for col,text in [(-.22,'サウナ'),(.22,'水風呂')]:
        for j,ch in enumerate(text):lettering(m,ch,(x+col,y-.10,1.46-j*.22),.18,color='sento_cream')
    lettering(m,'五百円',(x,y-.10,.72),.18,color='sento_cream')
    m.collider((x,y,1.0),(1.1,.3,2.2))


def hedge_and_fence(m,r):
    """Dense bamboo hedge inside a warm bamboo picket fence along the left half of the apron."""
    m.box((-8.35,-8.2,.45),(6.5,.6,1.3),'sento_hedge',.2)
    m.box((-8.35,-8.2,1.13),(6.3,.5,.12),'sento_hedge_top',.05)
    m.collider((-8.35,-8.2,.6),(6.6,.7,1.3))
    for i in range(22):
        x=-11.45+.3*i+r.uniform(-.05,.05);y=-8.2+r.uniform(-.14,.14);h=r.uniform(1.4,2.2)
        m.beam((x,y,.3),(x,y,h),.05,.05,'sento_stalk')
        for k in range(r.choice([3,4])):
            zz=h-.08-k*.3;yaw=r.uniform(0,360)
            with m.at((x,y,zz),yaw):m.box((.18,0,0),(.35,.12,.025),'sento_leaf' if k%2 else 'sento_leaf2')
    for j in range(57):
        x=-12.0+.13*j
        if x<-4.65:m.box((x,-8.75,.50),(.07,.05,1.20),v.color_variant('sento_bamboo',.08))
    m.box((-8.35,-8.75,1.14),(7.5,.10,.08),'wood_dark')
    for z in [.35,.80]:m.box((-8.35,-8.72,z),(7.4,.08,.06),'wood_dark')
    for x in [-12.05,-10.45,-8.85,-7.25,-5.65]:m.box((x,-8.75,.62),(.12,.12,1.30),'wood_dark')
    m.box((-4.5,-8.75,.6),(.36,.36,1.5),'arc_stone');m.box((-4.5,-8.75,1.4),(.44,.44,.12),'sento_edge')
    m.collider((-8.3,-8.75,.6),(7.7,.4,1.5))


def build(name,variant,lettering):
    palette(variant);m=v.Mesh(name);r=random.Random(31+variant)
    RX0,RX1=PX-2.1,PX+2.1;RY=-5.25                     # porch recess
    # ---- main block: ground storey with a recessed porch, set-back upper storey, stone plinth ----
    for x0,x1 in [(MX0,RX0),(RX1,MX1)]:
        m.box(((x0+x1)/2,-6.125,(GT-.4)/2),(x1-x0,1.75,GT+.4),P);m.collider(((x0+x1)/2,-6.125,(GT-.4)/2),(x1-x0,1.75,GT+.4))
    m.box(((MX0+MX1)/2,(RY-.05+MY1)/2,(GT-.4)/2),(MX1-MX0,MY1-RY+.05,GT+.4),P)
    m.collider(((MX0+MX1)/2,(RY+MY1)/2,(GT-.4)/2),(MX1-MX0,MY1-RY,GT+.4))
    m.box(((MX0+MX1)/2,(MY0+MY1)/2,-.2),(MX1-MX0+.3,MY1-MY0+.3,.8),'arc_stone')
    m.box(((UX0+UX1)/2,0,(UT+3.8)/2),(UX1-UX0,UY1-UY0,UT-3.8),P)
    # Lower skirt roof around the ground storey (1.3 m eave) and the main hip roof (1.1 m eave, ridge along X).
    ring(m,[(-12.4,-8.3),(6.7,-8.3),(6.7,8.3),(-12.4,8.3)],[(UX0,UY0),(UX1,UY0),(UX1,UY1),(UX0,UY1)],3.95,5.15,'sento_tile',strips=12,tips=.35)
    ring(m,[(-11.6,-6.6),(5.6,-6.6),(5.6,6.6),(-11.6,6.6)],[(-8.1,0),(2.1,0),(2.1,0),(-8.1,0)],7.35,9.9,'sento_tile',strips=12,tips=.5)
    m.box((-3,0,10.0),(10.6,.36,.28),'sento_edge',.06)
    for x in [-8.2,2.2]:m.box((x,0,10.08),(.5,.55,.5),'sento_edge',.06)
    # Square brick chimney behind the ridge, right of centre, with the bathhouse name down two faces.
    CX,CY=1.6,1.8;CT=14.05
    m.box((CX,CY,(CT-.3+5)/2),(1.55,1.55,CT-.3-5),'sento_brick')
    for dx,dy,w,d in [(0,-.775,1.85,.30),(0,.775,1.85,.30),(-.775,0,.30,1.25),(.775,0,.30,1.25)]:
        m.box((CX+dx,CY+dy,CT-.15),(w,d,.30),'sento_brick_dark')
    m.box((CX,CY,CT-.30),(1.28,1.28,.16),'sento_granite')
    m.box((CX,CY,CT-.22),(.55,.55,.18),(.02,.02,.02))
    m.box((CX,CY,10.0),(1.65,1.65,.40),'stone_light')
    chars=['松','の','湯'] if variant==0 else ['ゆ']
    for j,ch in enumerate(chars):
        z=12.8-j*1.15 if variant==0 else 11.9;sz=1.1 if variant==0 else 1.35
        lettering(m,ch,(CX,CY-.775-.046,z),sz,color='sento_white')
        with m.at((CX-.775-.046,CY,0),-90):lettering(m,ch,(0,0,z),sz,color='sento_white')
    # ---- front ground floor: framing, amber-lit lattice windows, notice board ----
    framing(m,MY0,MX0,RX0,-.4,GT,[MX0+.1,-6.0,RX0-.1],rails=(.45,))
    framing(m,MY0,RX1,MX1,-.4,GT,[RX1+.1,1.75,MX1-.1],rails=(.45,))
    koshi(m,-8.5,MY0-.02,2.05,4.6,1.9)
    koshi(m,4.05,MY0-.02,2.15,1.6,1.5)
    shoji(m,-4.95,MY0-.02,2.0,1.0,2.0)
    shoji(m,1.2,MY0-.02,2.0,.8,2.0)
    notice_board(m,2.55,MY0-.06,1.95,lettering)
    # ---- porch: stone steps and plinths, posts with wall lamps, lintel, ceiling, lit shoji, karahafu, name board, noren ----
    m.box((PX,-6.95,-.02),(4.4,3.5,.76),'sento_stone');m.collider((PX,-6.95,-.02),(4.4,3.5,.76))
    m.box((PX,-9.15,-.02),(4.2,.9,.76),'sento_stone');m.collider((PX,-9.15,-.02),(4.2,.9,.76))
    m.box((PX,-9.85,-.11),(4.2,.5,.58),'sento_stone');m.collider((PX,-9.85,-.11),(4.2,.5,.58))
    for s in [-1,1]:
        x=PX+s*2.4
        # These piers sit outside the stair slab: carry them to the ground.
        m.box((x,-8.7,.35),(.46,.46,.78),'stone_light')
        m.box((x,-8.7,2.45),(.30,.30,3.5),T);m.collider((x,-8.7,2.0),(.46,.46,4.4))
        m.beam((x,-8.7,3.85),(x+s*.6,-8.7,3.85),.06,.06,T)
        arcade.lantern(m,x+s*.58,-8.72,2.78,.5)
        m.box((x-s*.21,-8.7,2.3),(.12,.16,.22),'paper');m.box((x-s*.23,-8.7,2.44),(.18,.22,.04),T)
    m.box((PX,-8.7,4.05),(5.5,.34,.34),T)
    m.box((PX,-7.0,3.80),(4.6,3.6,.14),T)
    m.box((PX,RY+.02,1.75),(3.5,.12,2.7),T);m.box((PX,RY-.05,1.7),(3.2,.06,2.4),'paper')
    for j in range(9):m.box((PX-1.6+j*.4,RY-.10,1.7),(.05,.04,2.4),T)
    for j in range(6):m.box((PX,RY-.10,.5+j*.48),(3.2,.04,.05),T)
    m.box((PX,RY-.12,.41),(3.6,.22,.10),'sento_granite')
    m.box((PX-1.55,RY-.45,.62),(.8,.3,.5),T);m.collider((PX-1.55,RY-.45,.62),(.8,.3,.5))
    for x,yaw in [(RX0,90),(RX1,-90)]:
        with m.at((x,-6.15,0),yaw):shoji(m,0,-.02,1.9,1.0,2.0)
    zc=karahafu(m,PX,-8.9,-5.4,3.95,4.22)
    m.box((PX,-8.72,4.55),(2.2,.08,.58),'wood_dark')
    if variant==0:lettering(m,'松の湯',(PX,-8.775,4.33),.44,color='sento_cream')
    else:lettering(m,'湯',(PX,-8.775,4.31),.50,color='sento_cream')
    gegyo(m,PX,-8.96,5.33)
    m.beam((PX-1.85,-8.5,3.70),(PX+1.85,-8.5,3.70),.05,.05,T)
    for j,(dx,h) in enumerate([(-1.2,1.88),(0,1.94),(1.2,1.86)]):
        m.box((PX+dx,-8.5,3.68-h/2),(1.14,.03,h),'sento_noren')
    lettering(m,'ゆ',(PX,-8.535,1.98),2.0,color='sento_white')
    # ---- upper storey framing and high windows on all four sides ----
    framing(m,UY0,UX0,UX1,3.8,UT,[UX0+.1,-6.95,UX1-.1],rails=(5.4,))
    for x in [-8.5,-5.4,2.7]:band(m,x,UY0-.02,6.3)
    for x,yaw in [(UX0,-90),(UX1,90)]:
        with m.at((x,0,0),yaw):
            framing(m,0,-5.5,5.5,3.8,UT,[-5.4,0,5.4],rails=(5.4,))
            for xx in [-3,3]:band(m,xx,-.02,6.3)
    with m.at((-3,UY1,0),180):
        framing(m,0,-7.5,7.5,3.8,UT,[-7.4,-2.5,2.5,7.4],rails=(5.4,))
        for xx in [-5,5]:band(m,xx,-.02,6.3)
        m.box((0,-.08,6.3),(1.2,.12,.9),T)
        for j in range(5):m.box((0,-.15,5.95+j*.17),(1.05,.05,.07),'sento_trim')
    # ---- left side, back and the exposed right corner: door, windows, downpipes, boiler yard ----
    with m.at((MX0,0,0),-90):
        framing(m,0,-7,7,-.4,GT,[-6.9,-1.2,4.0,6.9],rails=(.45,))
        v.door(m,2.0,-.08,.06,1.2,2.15)
        koshi(m,-3.5,-.02,2.1,1.8,1.4);koshi(m,5.5,-.02,2.4,1.5,1.1)
        downpipe(m,6.55,-.32,4.3)
    with m.at((-3,MY1,0),180):
        framing(m,0,-8.5,8.5,-.4,GT,[-8.4,-4.5,0,4.5,8.4],rails=(.45,))
        v.door(m,-1.8,-.08,.06,1.25,2.15)
        koshi(m,2.6,-.02,2.2,1.8,1.4);koshi(m,-6.4,-.02,2.4,1.4,1.0)
        downpipe(m,-8.7,-.32,4.3)
        # Boiler tank and firewood for the bath water, tucked under the back eave.
        m.lathe((-6.5,-.85,-.1),[(0,.55),(1.5,.55),(1.62,.42),(1.7,0)],'metal',12);m.collider((-6.5,-.85,.7),(1.2,1.2,1.7))
        for j in range(12):
            z=.12+(j//4)*.24;yy=-.55-(j%4)*.24
            m.beam((-5.6,yy,z),(-3.4,yy,z),.22,.22,v.color_variant('wood_light',.12))
        m.collider((-4.5,-.9,.36),(2.3,1.0,.75))
    with m.at((MX1,0,0),90):
        framing(m,0,3.0,7,-.4,GT,[3.2,6.9],rails=(.45,))
        koshi(m,5.0,-.02,2.2,1.4,1.2)
        downpipe(m,6.55,-.32,4.3)
    # ---- coin-laundry annex: plaster box, low tiled hip roof tucked under the skirt, glazed lit bay, sign ----
    m.box(((AX0+AX1)/2,(AY0+AY1)/2,(AT-.4)/2),(AX1-AX0,AY1-AY0,AT+.4),P);m.collider(((AX0+AX1)/2,(AY0+AY1)/2,(AT-.4)/2),(AX1-AX0,AY1-AY0,AT+.4))
    m.box(((AX0+AX1)/2,(AY0-1.0+AY1)/2,-.2),(AX1-AX0+.3,AY1-AY0+1.3,.8),'arc_stone')
    ring(m,[(AX0,-7.4),(12.3,-7.4),(12.3,3.8),(AX0,3.8)],[(8.9,-4.0),(8.9,-4.0),(8.9,.4),(8.9,.4)],AT+.15,AT+1.15,'sento_tile',strips=8,tips=.3,bare=(3,))
    m.box((8.9,-1.8,AT+1.22),(.34,4.8,.26),'sento_edge',.06)
    for y in [-4.1,.5]:m.box((8.9,y,AT+1.3),(.46,.5,.42),'sento_edge',.06)
    # Glazed bay: raised floor, plaster returns, canvas-lit ceiling and back wall, machines, mullions, glass door.
    m.box((8.5,-6.1,-.14),(6.0,1.0,.52),'sento_stone');m.collider((8.5,-6.1,-.14),(6.0,1.0,.52))
    for x in [5.75,11.25]:m.box((x,-6.1,(AT-.4)/2),(.5,1.0,AT+.4),P);m.collider((x,-6.1,(AT-.4)/2),(.5,1.0,AT+.4))
    m.box((8.5,-6.1,AT-.16),(5.0,1.0,.12),'arc_canvas')
    m.box((8.5,AY0-.03,1.55),(5.0,.06,2.9),'arc_canvas')
    m.box((8.5,AY0-.055,.66),(5.0,.03,.10),'sento_trim')
    for x in [6.5,7.35,8.2,9.05]:washing_machine(m,x,-6.15,.12)
    m.collider((7.78,-6.15,.6),(3.6,.75,1.0))
    m.box((8.5,-6.62,.32),(5.0,.10,.42),T)
    m.box((8.5,-6.62,AT-.13),(5.0,.14,.30),T)
    for x in [6.06,7.31,8.56,9.81,10.93]:m.box((x,-6.62,(AT-.13+.32)/2),(.12,.12,AT-.13-.32),T)
    m.box((10.37,-6.60,1.72),(1.0,.05,2.2),'arc_shopglass');m.box((10.37,-6.585,1.72),(1.08,.04,2.28),T)
    m.box((10.75,-6.66,1.5),(.05,.06,.28),'metal')
    m.box((8.5,-6.95,AT-.20),(2.7,.08,.42),'wood_dark')
    lettering(m,'コインランドリー',(8.5,-7.0,AT-.34),.27,color='sento_cream')
    if variant==1:
        m.beam((9.8,-6.72,AT-.30),(10.95,-6.72,AT-.30),.04,.04,T)
        for dx in [-.24,.24]:m.box((10.37+dx,-6.72,AT-.78),(.46,.03,.92),'sento_red')
        lettering(m,'湯',(10.37,-6.745,AT-1.05),.55,color='sento_cream')
    with m.at((AX1,0,0),90):
        framing(m,0,-6,3,-.4,AT,[-5.9,-2.6,2.9],rails=(.45,))
        koshi(m,-1.2,-.02,1.9,1.4,1.2,glow=False)
        m.box((1.6,-.16,2.3),(.34,.30,.34),'metal');m.lathe((1.6,-.35,2.12),[(0,.10),(.36,.10),(.40,0)],'metal',8)
    with m.at((8.5,AY1,0),180):
        framing(m,0,-3,3,-.4,AT,[-2.9,2.9],rails=(.45,))
        v.door(m,0,-.08,.06,1.1,2.1)
    # ---- street props on the apron: bamboo fence with the hedge behind it, price board, pots, bench, lantern, tubs ----
    hedge_and_fence(m,r)
    price_board(m,-11.3,-9.2,lettering)
    for j,(x,scale,key,form) in enumerate([(1.35,.95,'clay','jar'),(2.1,.7,'bluepot','bowl'),(2.85,.85,'clay','urn'),(3.65,.7,'clay','jar'),(4.45,.9,'bluepot','urn'),(5.25,.75,'clay','bowl')]):
        v.pot(m,x,-8.55,.02,scale,key,plant=(j%2==0),form=form)
        if j%2:
            # Root flowers inside the bowl/jar, rather than hovering over its rim.
            soil_z=.02+(.22 if form=='bowl' else .39)*scale
            m.poly([(x+math.cos(k*math.tau/12)*.15*scale,-8.55+math.sin(k*math.tau/12)*.15*scale,soil_z) for k in range(12)],'soil')
            arcade.flowers(m,x,-8.55,soil_z,j+9,root_spread=(.12*scale,.12*scale))
    v.pot(m,-4.4,-9.5,.02,.9,'bluepot',plant=True)
    v.pot(m,-5.1,-9.3,.02,.7,'clay',plant=True,form='bowl')
    if variant==0:
        v.bench(m,2.2,-9.55,0,w=1.7)
        stone_lantern(m,4.45,-9.5)
    else:
        v.bench(m,2.2,-9.55,0,w=1.7);v.bench(m,-6.3,-9.7,0,w=1.5)
        tubs(m,4.5,-9.45)
    return m
