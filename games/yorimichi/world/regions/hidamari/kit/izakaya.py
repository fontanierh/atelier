"""Two adjoining eateries on one lot: a tall ramen shop (red tin front, ラーメン) and a lower yakitori izakaya (honey timber, 焼鳥, orange lantern row); variant 1 is a soba shop + oden bar."""
import math,random
from mathutils import Vector
from village import build as v
from hidamari import arcade
from hidamari.kit._lettering import raised_text
ASSETS={'HD_Shop_02':0,'HD_Shop_10':1}

FY=-7.5          # front wall plane (street side, -Y)
RX0,RX1=-11.0,-0.6   # ramen shop x extent
IX0,IX1=-0.58,11.0   # izakaya x extent
R_EAVE,I_EAVE=7.0,5.9


def palette():
    arcade.palette()
    v.PALETTE.update({
        'iz_roof':(.09,.092,.098),'iz_ridge':(.055,.057,.062),'iz_tile':(.075,.077,.083),   # silver ibushi kawara
        'iz_cream':(.48,.41,.27),
        'iz_shoji':(.66,.52,.28),'iz_glow':(.62,.48,.24),'iz_downlight':(.70,.50,.22),
        'iz_orange':(.62,.20,.03),'iz_lamp_band':(.35,.10,.02),'iz_vend':(.78,.66,.40),
        'iz_tin':(.48,.12,.07),'iz_tin_dark':(.34,.08,.05),'iz_teal':(.13,.23,.24),'iz_teal_dark':(.09,.17,.18),
        'iz_red':(.46,.07,.04),'iz_red_lamp':(.58,.13,.04),'iz_navy':(.04,.06,.14),'iz_indigo':(.07,.12,.28),'iz_cloth_cream':(.60,.52,.36),
        'iz_galv':(.30,.32,.33),'iz_galv_dark':(.19,.21,.22),'iz_black':(.04,.04,.045),
        'iz_yellow':(.58,.36,.04),'iz_yellow_dark':(.30,.17,.03),'iz_board':(.42,.25,.10),'iz_ivory':(.86,.76,.52),'iz_blue':(.10,.24,.44),'iz_blue_dark':(.07,.17,.32),
        'iz_cream_lamp':(.85,.66,.28),'iz_steam':(.60,.60,.58),'iz_bowl':(.55,.50,.42),'iz_broth':(.50,.30,.10),
        'iz_plank':(.30,.17,.07),'iz_plank_dark':(.22,.12,.05),'iz_concrete':(.30,.29,.26),
    })


# ---------------------------------------------------------------- primitives

def cyl(m,a,b,r,key,n=10,caps=True):
    """Solid cylinder between two points (any direction)."""
    a=Vector(a);b=Vector(b);d=b-a
    if d.length<1e-6:return
    d.normalize();u=d.cross(Vector((0,0,1)))
    if u.length<1e-6:u=Vector((1,0,0))
    u.normalize();w=d.cross(u)
    ra=[a+(u*math.cos(t)+w*math.sin(t))*r for t in [k*math.tau/n for k in range(n)]]
    rb=[p+(b-a) for p in ra]
    for k in range(n):m.poly([ra[k],ra[(k+1)%n],rb[(k+1)%n],rb[k]],key)
    if caps:m.poly(ra[::-1],key);m.poly(rb,key)


def gable_roof(m,cx,cy,w,d,z,rise):
    """Tiled gable roof, ridge along X: thick soffit slab, fascia boxes on both eaves, heavy ridge with round end tiles, closed gable ends."""
    with m.at((cx,cy,0)):
        m.box((0,0,z-.15),(w,d,.30),'arc_timber')
        for s in [-1,1]:
            pts=[(-w/2,0,z+rise),(w/2,0,z+rise),(w/2,s*d/2,z),(-w/2,s*d/2,z)]
            m.poly(pts[::-1] if s<0 else pts,'iz_roof')
            m.box((0,s*d/2,z-.10),(w+.04,.28,.30),'iz_ridge',.02)
            rows=max(3,round(d/2/.75))
            for i in range(1,rows):
                t=i/rows;y=s*d/2*t;zz=z+rise*(1-t)
                m.beam((-w/2,y,zz+.03),(w/2,y,zz+.03),.07,.07,'iz_tile')
            cols=max(4,round(w/.62))
            for i in range(cols+1):
                x=-w/2+i*w/cols
                m.beam((x,0,z+rise+.03),(x,s*d/2,z+.03),.05,.05,'iz_tile')
        for x in [-w/2,w/2]:
            pts=[(x,-d/2,z),(x,d/2,z),(x,0,z+rise)]
            m.poly(pts[::-1] if x<0 else pts,'iz_cream')
            m.beam((x,-d/2,z-.02),(x,0,z+rise),.22,.22,'arc_trim');m.beam((x,d/2,z-.02),(x,0,z+rise),.22,.22,'arc_trim')
        zr=z+rise+.10
        m.box((0,0,zr),(w+.12,.36,.36),'iz_ridge',.03)
        for x in [-w/2-.06,w/2+.06]:cyl(m,(x-.08,0,zr),(x+.08,0,zr),.21,'iz_ridge',12)


def pent(m,x0,x1,yw,zt,depth,drop,brackets=True,positions=None):
    """Tiled pent roof hanging off a wall at y=yw, from (yw,zt) down to (yw-depth,zt-drop): slab, fascia box, tile rows, tie beam and brackets."""
    zb=zt-drop;yf=yw-depth;th=.16
    top=[(x0,yf,zb),(x1,yf,zb),(x1,yw,zt),(x0,yw,zt)]
    m.poly(top,'iz_roof')
    bot=[(x,y,z-th) for x,y,z in top];m.poly(bot[::-1],'arc_timber')
    for x,rev in [(x0,False),(x1,True)]:
        p=[(x,yw,zt),(x,yw,zt-th),(x,yf,zb-th),(x,yf,zb)]
        m.poly(p[::-1] if rev else p,'arc_trim')
    m.box(((x0+x1)/2,yf+.02,zb-.05),(x1-x0+.04,.24,.22),'iz_ridge',.02)
    cols=max(3,round((x1-x0)/.55))
    for i in range(cols+1):
        x=x0+i*(x1-x0)/cols
        m.beam((x,yw,zt+.03),(x,yf,zb+.03),.05,.05,'iz_tile')
    for i in range(1,5):
        t=i/5;m.beam((x0,yw-depth*t,zt-drop*t+.03),(x1,yw-depth*t,zt-drop*t+.03),.06,.06,'iz_tile')
    m.beam((x0-.04,yw+.04,zt+.05),(x1+.04,yw+.04,zt+.05),.16,.14,'iz_ridge')
    if brackets:
        m.beam((x0,yw-.08,zt-th-.07),(x1,yw-.08,zt-th-.07),.14,.14,'wood_light')
        n=max(2,round((x1-x0)/2.4))
        for x in (positions or [x0+.25+i*(x1-x0-.5)/n for i in range(n+1)]):
            m.beam((x,yw-.08,zt-th-.90),(x,yf+.30,zb-th-.03),.14,.14,'wood_light')
            m.box((x,yw-.08,zt-th-.47),(.14,.16,1.0),'wood_light')


def cladding(m,x0,x1,y,z0,z1,keys,pitch,width,depth=.06,skip=()):
    n=max(1,round((x1-x0)/pitch))
    for i in range(n):
        x=x0+(i+.5)*(x1-x0)/n
        if any(a<x<b for a,b in skip):continue
        m.box((x,y-depth/2,(z0+z1)/2),(width,depth,z1-z0),keys[i%len(keys)])


def tin(m,x0,x1,y,z0,z1,key,dark,skip=()):
    """Corrugated tin: sheet segments (cut around the skip ranges) with vertical ribs."""
    cuts=[x0]+[c for a,b in skip for c in (a,b)]+[x1]
    for xa,xb in zip(cuts[::2],cuts[1::2]):
        m.box(((xa+xb)/2,y-.02,(z0+z1)/2),(xb-xa,.04,z1-z0),key)
    cladding(m,x0,x1,y-.04,z0,z1,[dark],.30,.11,.04,skip)


def base(m,cx,w,y=0):
    m.box((cx,y-.06,.15),(w,.08,.5),'arc_timber')


def frame(m,xs,cx,w,z0,z1,y=0):
    """Upper-floor timber frame: 0.30 m posts and rails one step darker than the plaster."""
    for x in xs:m.box((x,y-.10,(z0+z1)/2),(.30,.22,z1-z0),'iz_plank')
    for z in [z0+.22,z1-.10]:m.box((cx,y-.10,z),(w,.20,.24),'iz_plank')


def shoji(m,x,y,z,w,h,cell=.45,glow='iz_shoji'):
    """Timber-framed paper window band, lit from inside."""
    m.box((x,y+.02,z),(w+.32,.16,h+.32),'arc_timber')
    m.box((x,y-.07,z),(w,.04,h),glow)
    nx=max(1,round(w/cell));nz=max(1,round(h/cell))
    for i in range(nx+1):m.box((x-w/2+i*w/nx,y-.105,z),(.05,.05,h),'arc_timber')
    for j in range(nz+1):m.box((x,y-.105,z-h/2+j*h/nz),(w+.02,.05,.05),'arc_timber')
    m.box((x,y-.17,z-h/2-.10),(w+.44,.38,.12),'arc_trim')


def sliding_doors(m,x,y,z0,w,h):
    """Two timber sliding doors with lit upper panes (glow backing behind each pane)."""
    m.box((x,y-.05,z0+h/2),(w+.32,.14,h+.22),'arc_timber')
    for k,dx in enumerate([-w/4,w/4]):
        px=x+dx;pw=w/2-.06;yy=y-.15-k*.06
        m.box((px,yy,z0+h/2),(pw,.05,h),'arc_trim')
        m.box((px,yy+.10,z0+h*.70),(pw-.14,.04,h*.50),'iz_glow')
        m.box((px,yy-.05,z0+h*.70),(pw-.14,.08,h*.50),'iz_glow')
        m.box((px,yy-.03,z0+h*.24),(pw-.14,.03,h*.36),'wood')
        m.box((px,yy-.105,z0+h*.70),(.05,.03,h*.50),'arc_trim')
        m.box((px,yy-.105,z0+h*.70),(pw-.14,.03,.05),'arc_trim')
        m.box((px+(.12 if k else -.12),yy-.11,z0+h*.42),(.05,.03,.24),'metal')
    m.box((x,y-.14,z0-.02),(w+.32,.24,.06),'arc_timber')


def noren(m,lettering,x,y,z,w,h,key,text,panels=3,size=.5,tkey='iz_ivory',gap=.05,motif=False):
    m.beam((x-w/2-.15,y+.02,z+h),(x+w/2+.15,y+.02,z+h),.06,.06,'arc_timber')
    pw=(w-gap*(panels-1))/panels
    for k in range(panels):
        xa=x-w/2+k*(pw+gap);xb=xa+pw
        ya=y-.03*math.sin(k*1.7);yb=y-.03*math.sin(k*1.7+1.3)
        p=[(xa,y,z+h),(xa,ya,z),(xb,yb,z),(xb,y,z+h)]
        m.poly(p,key);m.poly(p[::-1],key)
        if motif and k in (0,panels-1):
            # ivory swirl roundel on the outer panels
            mx=(xa+xb)/2;mz=z+h*.42
            cyl(m,(mx,y-.04,mz),(mx,y-.06,mz),.15,'iz_ivory',12)
            cyl(m,(mx,y-.06,mz),(mx,y-.075,mz),.085,key,12)
            cyl(m,(mx,y-.075,mz),(mx,y-.09,mz),.035,'iz_ivory',8)
    if text:bold(m,lettering,text,(x,y-.05,z+h/2),size,tkey)


def lantern(m,x,y,z,size,key,text=None,lettering=None,tkey='iz_black',hang=.0,tsize=None):
    """Paper lantern with dark bands at the top and bottom rings; characters stacked down the belly."""
    prof=[(-1.1,.22),(-.92,.72),(-.55,.95),(0,1.0),(.55,.95),(.92,.72),(1.1,.22)]
    m.lathe((x,y,z),[(a*size,b*size) for a,b in prof],key,12)
    for zz in [-1.1,1.1]:m.lathe((x,y,z+zz*size),[(-.03,.24*size),(.03,.24*size)],'arc_timber',10)
    for zz in [-.92,.92]:m.lathe((x,y,z+zz*size),[(-.03,.80*size),(.03,.80*size)],'iz_lamp_band',12)
    for zz in [-.5,0,.5]:
        r=size*(.96 if zz else 1.0)+.006
        m.lathe((x,y,z+zz*size),[(-.012,r),(.012,r)],'arc_trim',12)
    if hang>0:m.beam((x,y,z+1.1*size),(x,y,z+1.1*size+hang),.03,.03,'arc_timber')
    if text and lettering:
        ts=tsize or size*.4;lines=len(text);body='\n'.join(text)
        bold(m,lettering,body,(x,y-size-.025,z+ts*.5*(lines-1)),ts,tkey)


GLYPH=.43   # measured: Noto Sans JP at lettering size 1 renders ~0.43 m tall glyphs

def bold(m,lettering,text,pos,size,color,d=None):
    """Thicken the outline once; pos z remains the visual glyph centre."""
    x,y,z=pos
    raised_text(m,text,(x,y,z-size*GLYPH/2),size,color,weight=d or size*.014,depth=.018)


def sign_board(m,lettering,x,y,z,w,h,text,size,tkey='iz_ivory'):
    """Warm brown name board in a thick light-timber frame, propped on struts."""
    m.box((x,y-.12,z),(w,.24,h),'iz_board',.03)
    m.box((x,y-.27,z+h/2-.07),(w+.20,.16,.14),'wood_light')
    m.box((x,y-.27,z-h/2+.07),(w+.20,.16,.14),'wood_light')
    for dx in [-w/2+.07,w/2-.07]:m.box((x+dx,y-.27,z),(.14,.16,h),'wood_light')
    for dx in [-w/2+.5,w/2-.5]:m.beam((x+dx,y+.0,z-h/2-.5),(x+dx,y-.36,z-h/2+.05),.12,.12,'wood_light')
    bold(m,lettering,text,(x,y-.27,z),size,tkey)


def vent_pipe(m,x,y,z0,z1,r=.19,fwd=(0,-1)):
    """Galvanised pipe up a wall with an elbow at the base and a cap."""
    cyl(m,(x,y,z0),(x,y,z1),r,'iz_galv',10)
    m.lathe((x,y,z0),[(-r,.0),(-r*.6,r*.9),(0,r*1.08),(r*.6,r*.9),(r,.0)],'iz_galv_dark',10)
    fx,fy=fwd
    cyl(m,(x,y,z0),(x+fx*.9,y+fy*.9,z0),r*.95,'iz_galv',10)
    m.lathe((x+fx*.9,y+fy*.9,z0),[(-r,.0),(-r*.6,r*.9),(0,r*1.08),(r*.6,r*.9),(r,.0)],'iz_galv_dark',10)
    cyl(m,(x+fx*.9,y+fy*.9,z0),(x+fx*.9,y+fy*.9,z0-.5),r*.95,'iz_galv',10)
    m.lathe((x,y,z1),[(-.02,r*1.2),(.12,r*1.2),(.12,r*.3),(.30,r*.3),(.30,r*1.35),(.42,r*1.35),(.50,r*.2)],'iz_galv_dark',10)
    for zz in [z0+1.6,z0+4.0]:
        if zz<z1-.4:m.lathe((x,y,zz),[(-.05,r+.03),(.05,r+.03)],'iz_galv_dark',10)


def satellite_dish(m,x,y,z,out):
    """Dish on a wall bracket, facing `out` (unit x direction)."""
    m.beam((x,y,z-.3),(x+out*.55,y,z-.3),.06,.06,'iz_galv_dark')
    m.beam((x+out*.55,y,z-.3),(x+out*.55,y,z+.1),.07,.07,'iz_galv_dark')
    cyl(m,(x+out*.55,y,z+.1),(x+out*.62,y,z+.1),.48,'iz_galv',14)
    m.beam((x+out*.62,y,z-.2),(x+out*1.05,y,z+.05),.04,.04,'iz_galv_dark')
    m.lathe((x+out*1.05,y,z+.0),[(-.05,.05),(.05,.05)],'iz_galv_dark',6)


def ac_unit(m,x,y,z):
    m.box((x,y-.17,z),(.85,.34,.62),'iz_galv',.02)
    cyl(m,(x-.16,y-.35,z),(x-.16,y-.37,z),.20,'iz_galv_dark',12)
    for k in range(4):m.box((x+.24,y-.355,z-.2+k*.13),(.22,.02,.04),'iz_galv_dark')
    m.beam((x-.3,y,z-.34),(x-.3,y-.34,z-.34),.05,.05,'iz_galv_dark');m.beam((x+.3,y,z-.34),(x+.3,y-.34,z-.34),.05,.05,'iz_galv_dark')


def extractor(m,x,y,z):
    m.lathe((x,y,z),[(0,.48),(.75,.48),(.75,.56),(.88,.56),(.98,.40),(.98,0)],'iz_galv',12)
    m.beam((x,y,z+.35),(x,y+1.4,z+.35),.32,.32,'iz_galv_dark')


def crate_stack(m,lettering,x,y,n,key,dark,text,yaw=0):
    """Stacked plastic beer/sake crates (0.95 x 0.62 x 0.42), lettered on the street face."""
    with m.at((x,y,0),yaw):
        for i in range(n):
            z=.03+i*.44
            m.box((0,0,z+.21),(.95,.62,.42),key,.01)
            for k in range(3):
                m.box((-.30+k*.30,-.31,z+.33),(.20,.03,.07),dark)
                m.box((-.30+k*.30,.31,z+.33),(.20,.03,.07),dark)
            for s in [-1,1]:m.box((s*.475,0,z+.33),(.03,.38,.07),dark)
            bold(m,lettering,text,(0,-.325,z+.15),.30,dark)
        m.collider((0,0,.03+n*.22),(.97,.64,n*.44))


def barrel(m,x,y,plant=True):
    m.lathe((x,y,0),[(0,.36),(.15,.40),(.5,.42),(.85,.40),(1.0,.36),(1.0,0)],'arc_trim',12)
    for zz in [.14,.5,.86]:m.lathe((x,y,zz),[(-.03,.45 if zz==.5 else .43),(.03,.45 if zz==.5 else .43)],'iz_galv_dark',12)
    if plant:v.pot(m,x,y,1.0,.8,'clay',plant=True)
    m.collider((x,y,.5),(.85,.85,1.0))


def vending(m,lettering,x,y,z=0,yaw=0):
    with m.at((x,y,z),yaw):
        m.box((0,0,.95),(1.0,.75,1.9),'iz_black',.02)
        m.box((0,-.39,1.28),(.86,.04,1.0),'iz_vend')
        cols=['iz_red','iz_blue','iz_yellow','green','iz_galv','clay']
        for row in range(3):
            for k in range(6):
                m.box((-.34+k*.136,-.425,.98+row*.30),(.09,.03,.20),cols[(k+row)%6],.01)
        m.box((0,-.39,.42),(.86,.04,.46),'iz_galv_dark')
        m.box((.20,-.415,.60),(.36,.02,.16),'iz_galv')
        m.box((0,-.395,1.86),(.92,.03,.08),'iz_red')
        lettering(m,'ほっと',(-.22,-.43,.55),.22,color='iz_cream')
        m.collider((0,0,.95),(1.0,.75,1.9))


def bin_(m,x,y):
    m.lathe((x,y,0),[(0,.28),(.05,.31),(.85,.34),(.85,0)],'iz_blue',10)
    m.lathe((x,y,.85),[(0,.34),(.06,.36),(.10,.30),(.10,0)],'iz_blue_dark',10)
    m.box((x,y-.33,.55),(.22,.02,.16),'iz_cream')
    m.collider((x,y,.45),(.7,.7,.95))


def bicycle(m,x,y,yaw=0):
    with m.at((x,y,0),yaw):
        for wx in [-.56,.56]:
            cyl(m,(wx,-.02,.33),(wx,.02,.33),.33,'iz_black',14)
            cyl(m,(wx,-.05,.33),(wx,.05,.33),.06,'iz_galv',6)
        f='iz_galv'
        m.beam((-.56,0,.33),(-.08,0,.88),.035,.035,f);m.beam((-.08,0,.88),(.42,0,.86),.035,.035,f)
        m.beam((.42,0,.86),(.56,0,.33),.035,.035,f);m.beam((-.08,0,.88),(.02,0,.33),.035,.035,f)
        m.beam((.02,0,.33),(-.56,0,.33),.035,.035,f);m.beam((.02,0,.33),(.42,0,.86),.035,.035,f)
        m.beam((-.08,0,.88),(-.10,0,1.0),.03,.03,f);m.box((-.12,0,1.03),(.28,.14,.06),'iz_black',.01)
        m.beam((.42,0,.86),(.44,0,1.0),.03,.03,f);m.beam((.44,-.26,1.0),(.44,.26,1.0),.03,.03,f)
        m.box((.68,0,.86),(.30,.36,.24),'arc_trim',.01)
        for k in range(4):m.box((.68,-.19+k*.126,.86),(.31,.02,.23),'iz_plank_dark')
        m.lathe((.02,.06,.33),[(-.02,.07),(.02,.07)],'iz_black',8)
        m.beam((-.05,-.04,.44),(-.05,-.14,.44),.04,.04,'iz_black')
        m.collider((0,0,.5),(1.85,.5,1.0))


def a_board(m,lettering,x,y,yaw,title,lines):
    with m.at((x,y,.03),yaw):
        for xx in [-.40,.40]:m.beam((xx,-.22,0),(xx,.12,1.20),.06,.06,'arc_trim')
        m.box((0,-.05,.70),(.80,.06,.90),'arc_timber')
        m.box((0,-.095,.70),(.68,.02,.76),'iz_black')
        lettering(m,title,(0,-.11,.93),.30,color='iz_cream')
        for k,ln in enumerate(lines):lettering(m,ln,(0,-.11,.76-k*.11),.15,color='iz_cream')
        m.beam((-.40,.12,1.20),(.40,.12,1.20),.06,.06,'arc_trim')
        m.collider((0,0,.6),(.85,.45,1.2))


def stool(m,x,y):
    m.lathe((x,y,0),[(0,.15),(.04,.15),(.04,.045),(.55,.045),(.55,.19),(.62,.19),(.62,0)],'arc_trim',8)
    m.collider((x,y,.31),(.4,.4,.62))


def small_window(m,x,y,z,w,h,glow=False):
    m.box((x,y+.02,z),(w+.24,.14,h+.24),'arc_timber')
    m.box((x,y-.06,z),(w,.04,h),'iz_shoji' if glow else 'arc_glass')
    m.box((x,y-.09,z),(.05,.05,h),'arc_timber');m.box((x,y-.09,z),(w,.05,.05),'arc_timber')
    m.box((x,y-.14,z-h/2-.08),(w+.34,.32,.10),'arc_trim')


def downpipe(m,x,y,z0,z1,fwd=-1):
    m.beam((x,y,z0),(x,y,z1),.09,.09,'iz_galv_dark')
    m.beam((x,y,z1),(x,y+fwd*.35,z1+.25),.09,.09,'iz_galv_dark')
    m.beam((x,y,z0),(x,y+fwd*.35,z0-.15),.09,.09,'iz_galv_dark')


def side_door(m,x,y,z=.05):
    v.door(m,x,y-.02,z,1.05,2.05)
    pent(m,x-.9,x+.9,y,z+2.55,.7,.28,brackets=False)


# ---------------------------------------------------------------- building

def build(name,variant,lettering):
    palette();m=v.Mesh(name)
    V=variant
    tin_key,tin_dark=('iz_tin','iz_tin_dark') if V==0 else ('iz_teal','iz_teal_dark')
    left_sign='ラーメン' if V==0 else 'そば'
    right_sign='焼鳥' if V==0 else 'おでん'
    left_noren=('iz_red','iz_ivory') if V==0 else ('iz_indigo','iz_ivory')
    right_noren=('iz_navy','iz_ivory') if V==0 else ('iz_cloth_cream','arc_timber')
    lamp_key='iz_orange' if V==0 else 'iz_cream_lamp'
    left_lamp='iz_red_lamp' if V==0 else 'iz_cream_lamp'
    planks=['iz_plank','iz_plank_dark','arc_trim','iz_plank']

    rw=RX1-RX0;rcx=(RX0+RX1)/2;iw=IX1-IX0;icx=(IX0+IX1)/2
    # Low concrete steps (ramen top 0.05, izakaya top 0.02) and main volumes (walls sunk to z=-0.4).
    m.box((rcx,0,-.175),(rw+.24,15.24,.45),'iz_concrete',.02)
    m.box((icx,-.5,-.19),(iw+.24,14.24,.42),'iz_concrete',.02)
    m.box((rcx,0,(R_EAVE-.4)/2),(rw,15.0,R_EAVE+.4),'iz_cream')
    m.collider((rcx,0,(R_EAVE-.4)/2),(rw,15.0,R_EAVE+.4))
    # Izakaya as four blocks so the entrance recess (x 4.3..7.3, 1.2 m deep) is a real void.
    ex0,ex1,ed=4.3,7.3,1.2;ecx=(ex0+ex1)/2
    for cx,w,cy,d,cz,h in [((IX0+ex0)/2,ex0-IX0,-.5,14.0,(I_EAVE-.4)/2,I_EAVE+.4),
                           ((ex1+IX1)/2,IX1-ex1,-.5,14.0,(I_EAVE-.4)/2,I_EAVE+.4),
                           (ecx,ex1-ex0-.02,(FY+ed+6.5)/2,6.5-FY-ed,(I_EAVE-.4)/2,I_EAVE+.4),
                           (ecx,ex1-ex0-.02,FY+ed/2,ed+.02,(I_EAVE+2.6)/2,I_EAVE-2.6)]:
        m.box((cx,cy,cz),(w,d,h),'iz_cream');m.collider((cx,cy,cz),(w,d,h))

    # ---------------- Ramen shop front (x -11..-0.6)
    doors_x=-4.5;doors_w=4.0
    tin(m,RX0,RX1,FY,-.35,3.45,tin_key,tin_dark,skip=[(doors_x-doors_w/2-.20,doors_x+doors_w/2+.20)])
    base(m,rcx,rw,FY)
    m.box((rcx,FY-.09,3.52),(rw+.1,.16,.22),'arc_timber')
    sliding_doors(m,doors_x,FY,.06,doors_w,2.5)
    # Kitchen window (lit) with a wooden hood and a steaming bowl on the sill.
    kx,kz=-9.1,1.55
    m.box((kx,FY-.05,kz),(1.7,.14,1.25),'arc_timber')
    m.box((kx,FY-.14,kz),(1.5,.06,1.05),'iz_glow')
    m.box((kx,FY-.19,kz),(.05,.04,1.05),'arc_trim');m.box((kx,FY-.19,kz+.25),(1.5,.04,.05),'arc_trim')
    m.box((kx,FY-.22,kz-.60),(1.9,.44,.12),'arc_trim')
    m.lathe((kx-.25,FY-.30,kz-.54),[(0,0),(.02,.12),(.14,.21),(.21,.22),(.21,.18),(.06,.10)],'iz_bowl',10)
    m.lathe((kx-.25,FY-.30,kz-.36),[(-.005,.17),(.005,.17),(.005,0)],'iz_broth',10)
    m.lathe((kx+.30,FY-.30,kz-.54),[(0,0),(.02,.07),(.22,.08),(.24,0)],'iz_cream',8)
    for dx,dz,rr in [(-.30,.1,.09),(-.16,.28,.11),(-.30,.46,.08)]:
        m.lathe((kx+dx,FY-.30,kz-.30+dz),[(-rr,0),(-rr*.5,rr*.9),(rr*.5,rr*.9),(rr,0)],'iz_steam',8)
    v.awning(m,kx,FY-.02,kz+.75,1.9,.62,'arc_trim')
    # Deep entrance hood; long split noren in its shadow with the lit doors behind; lantern on a bracket arm beside it.
    pent(m,doors_x-2.55,doors_x+2.55,FY,3.05,1.5,.38,brackets=False)
    noren(m,lettering,doors_x,FY-.55,1.62,4.2,.95,left_noren[0],left_sign,panels=4,size=1.15 if len(left_sign)>2 else 1.3,tkey=left_noren[1],gap=.08,motif=True)
    m.beam((-7.35,FY,2.9),(-7.35,FY-.85,2.9),.06,.06,'arc_timber')
    lantern(m,-7.35,FY-.85,2.05,.32,left_lamp,text=left_sign,lettering=lettering,tkey='iz_ivory',hang=.5,tsize=.13 if len(left_sign)>2 else .22)
    # Wide ground-floor pent roof and the big wooden name board above it.
    pent(m,RX0-.25,RX1-.15,FY,3.85,2.0,.5,brackets=True,positions=[-10.75,-7.7,-4.5,-1.1])
    sign_board(m,lettering,rcx-.3,FY-.18,4.48,5.8,1.3,left_sign,2.4)
    extractor(m,-9.3,FY-.85,3.55)
    m.beam((-9.3,FY-.85,3.9),(-9.3,FY+.1,3.9),.30,.30,'iz_galv_dark')
    # Upper floor: timber frame with a wide lit shoji band.
    frame(m,[RX0+.15,-7.5,-4.0,RX1-.15],rcx,rw+.1,3.5,R_EAVE,FY)
    shoji(m,-5.75,FY,6.05,8.2,1.5,.46)
    v.pot(m,-1.55,FY-.75,.03,.95,'clay',plant=True)
    downpipe(m,RX1-.22,FY-.28,-.2,R_EAVE-.35)

    # ---------------- Izakaya front (x -0.58..11)
    cladding(m,IX0,IX1,FY,-.35,3.5,planks,.34,.31,.06,skip=[(ex0-.1,ex1+.1)])
    cladding(m,ex0-.1,ex1+.1,FY,2.68,3.5,planks,.34,.31,.06)
    base(m,icx,iw,FY)
    m.box((icx,FY-.09,3.55),(iw+.1,.16,.20),'arc_timber')
    # Recessed entrance: timber-lined reveal, glowing sliding door at the back, downlight in the ceiling, noren across the opening.
    with m.at((ex0,0,0),90):cladding(m,FY,FY+ed,0,-.35,2.6,planks,.34,.31,.05)
    with m.at((ex1,0,0),-90):cladding(m,-(FY+ed),-FY,0,-.35,2.6,planks,.34,.31,.05)
    m.box((ecx,FY+ed/2,2.58),(ex1-ex0+.1,ed+.1,.10),'arc_timber')
    m.box((ecx,FY+ed/2,2.45),(.9,.5,.06),'iz_downlight')
    by=FY+ed
    m.box((ecx,by-.05,1.32),(2.6,.12,2.55),'arc_timber')
    for k,dx in enumerate([-.62,.62]):
        m.box((ecx+dx,by-.12-.05*k,1.32),(1.2,.05,2.4),'arc_trim')
        m.box((ecx+dx,by-.19-.05*k,1.32),(1.05,.08,2.25),'iz_glow')
        for j in range(1,4):m.box((ecx+dx,by-.245-.05*k,.2+j*.56),(1.05,.03,.04),'arc_trim')
        m.box((ecx+dx,by-.245-.05*k,1.32),(.04,.03,2.25),'arc_trim')
    for z in [.6,1.6]:m.box((ecx-1.25,FY+.5,z),(.36,.5,.06),'arc_trim')
    for k,key in enumerate(['iz_cream','iz_blue','clay']):m.box((ecx-1.36+k*.11,FY+.5,.71),(.07,.07,.16),key)
    m.lathe((ecx-1.25,FY+.55,1.63),[(0,0),(.02,.08),(.20,.09),(.28,.04),(.36,.035),(.38,0)],'iz_bowl',8)
    for x in [ex0-.13,ex1+.13]:m.box((x,FY-.10,1.5),(.22,.22,3.8),'arc_timber')
    lantern(m,ecx+1.05,FY+.55,2.15,.17,'arc_paper',hang=.28)
    noren(m,lettering,ecx,FY-.16,1.85,2.8,.85,right_noren[0],right_sign,panels=2,size=1.4 if len(right_sign)<=2 else 1.2,tkey=right_noren[1])
    # Lit lattice window left of the door; counter, stools and the lit serving hatch on the right.
    shoji(m,2.55,FY,1.55,2.4,1.75,.30,'iz_glow')
    m.box((8.5,FY-.32,.45),(1.9,.6,.86),'arc_trim',.02)
    m.box((8.5,FY-.36,.90),(2.1,.72,.07),'wood_light')
    m.collider((8.5,FY-.32,.47),(2.1,.72,.94))
    for xx in [7.95,9.05]:stool(m,xx,FY-1.05)
    m.box((8.5,FY-.06,2.2),(1.4,.10,.9),'arc_timber');m.box((8.5,FY-.14,2.2),(1.25,.06,.78),'iz_glow')
    # Pent roof with the row of orange lanterns strung under it, name board above.
    pent(m,1.0,IX1-.2,FY,3.55,1.6,.4,brackets=True,positions=[1.25,4.9,7.3,10.5])
    for k in range(7):
        xx=1.9+k*1.2
        lantern(m,xx,FY-.85,2.72,.36,lamp_key,text=right_sign,lettering=lettering,hang=.1,tsize=.34 if len(right_sign)<=2 else .23)
    m.beam((1.5,FY-.85,3.12),(9.5,FY-.85,3.12),.03,.03,'arc_timber')
    sign_board(m,lettering,5.8,FY-.18,4.13,4.6,1.1,right_sign,2.0)
    frame(m,[IX0+.17,3.0,8.4,IX1-.15],icx,iw+.1,3.5,I_EAVE,FY)
    shoji(m,5.7,FY,5.25,5.0,.9,.42)
    ac_unit(m,.35,FY-.04,2.5)
    a_board(m,lettering,2.9,FY-1.35,-12,right_sign,['もも','ねぎま','つくね','かわ','レバー'] if V==0 else ['大根','たまご','ちくわ','こんにゃく','はんぺん'])
    vending(m,lettering,10.35,FY-.72)
    bin_(m,8.35,FY-1.85)
    if V==0:bicycle(m,9.9,FY-2.0,-4)
    else:
        barrel(m,10.1,FY-1.95,plant=False);m.box((10.1,FY-1.95,1.05),(.5,.5,.10),'arc_trim')

    # ---------------- Street props on the left corner (the city planter lives near x=-9, y=-9.5; kept clear)
    if V==0:
        crate_stack(m,lettering,-7.6,FY-1.05,3,'iz_yellow','iz_yellow_dark','ビール',6)
        crate_stack(m,lettering,-6.3,FY-1.0,2,'iz_yellow','iz_yellow_dark','ビール',-5)
    else:
        crate_stack(m,lettering,-7.6,FY-1.05,3,'iz_blue','iz_blue_dark','酒',4)
        crate_stack(m,lettering,-6.3,FY-1.0,2,'iz_blue','iz_blue_dark','酒',-7)
    barrel(m,-10.45,FY-.85)

    # ---------------- Ramen left side wall (x=-11): steam vent pipe, windows, side door, downpipe
    with m.at((RX0,0,0),-90):
        # local x runs toward the street (world -Y); local -Y is world -X
        cladding(m,-7.5,7.5,0,-.35,3.45,planks,.34,.31,.06,skip=[(-4.4,-2.6),(1.0,2.4)])
        base(m,0,15);m.box((0,-.09,3.52),(15.1,.16,.22),'arc_timber')
        frame(m,[-7.35,-3.5,0,3.5,7.35],0,15.1,3.5,R_EAVE)
        small_window(m,1.7,0,5.4,1.6,1.3,True);small_window(m,-3.5,0,5.4,1.6,1.3,False)
        small_window(m,1.7,0,1.9,1.3,1.1,True)
        side_door(m,-3.5,0)
        downpipe(m,-7.2,-.30,-.2,R_EAVE-.35)
    vent_pipe(m,RX0-.28,-5.6,1.15,R_EAVE+2.3,.20,fwd=(0,-1))
    for zz in [2.6,5.2]:m.box((RX0-.12,-5.6,zz),(.24,.16,.10),'iz_galv_dark')
    # Ramen right wall above the izakaya roof, and its exposed back-corner strip (y 6.5..7.5).
    with m.at((RX1,0,0),90):
        for x in [-7.35,0]:m.box((x,-.10,(I_EAVE-.3+R_EAVE)/2),(.30,.22,R_EAVE-I_EAVE+.3),'iz_plank')
        m.box((7.0,-.10,(R_EAVE-.4)/2),(.30,.22,R_EAVE+.4),'iz_plank')
        m.box((0,-.10,R_EAVE-.10),(15.1,.20,.24),'iz_plank')
        m.lathe((-6.0,-.12,6.5),[(-.02,.22),(.02,.22)],'iz_galv_dark',10)
        cyl(m,(-6.0,-.0,6.5),(-6.0,-.20,6.5),.20,'iz_galv',10)
        downpipe(m,7.3,-.30,-.2,R_EAVE-.35)

    # ---------------- Izakaya right side wall (x=11): vent pipe, satellite dish, windows, side door
    with m.at((IX1,0,0),90):
        cladding(m,-7.5,6.5,0,-.35,3.5,planks,.34,.31,.06,skip=[(-3.2,-1.4),(2.0,3.4)])
        base(m,-.5,14);m.box((-.5,-.09,3.55),(14.1,.16,.20),'arc_timber')
        frame(m,[-7.35,-2.3,2.3,6.35],-.5,14.1,3.5,I_EAVE)
        small_window(m,-4.7,0,4.7,1.5,1.1,True);small_window(m,0,0,4.7,1.5,1.1,False);small_window(m,4.3,0,4.7,1.5,1.1,True)
        small_window(m,-2.3,0,1.8,1.2,1.0,True)
        side_door(m,2.7,0)
        downpipe(m,6.2,-.30,-.2,I_EAVE-.35)
    vent_pipe(m,IX1+.28,-6.4,1.0,I_EAVE+2.6,.18,fwd=(0,-1))
    for zz in [2.4,4.8]:m.box((IX1+.12,-6.4,zz),(.24,.16,.10),'iz_galv_dark')
    satellite_dish(m,IX1,-2.6,5.0,1)
    # ---------------- Backs (ramen y=7.5, izakaya y=6.5)
    with m.at((0,7.5,0),180):
        # local x = world -x; the ramen spans local x 0.6..11
        cladding(m,.6,11,0,-.35,3.45,planks,.34,.31,.06,skip=[(4.2,5.6)])
        base(m,5.8,10.4);m.box((5.8,-.09,3.52),(10.5,.16,.22),'arc_timber')
        frame(m,[.75,4.0,7.5,10.85],5.8,10.5,3.5,R_EAVE)
        small_window(m,2.4,0,5.4,1.6,1.3,True);small_window(m,8.2,0,5.4,1.6,1.3,False)
        small_window(m,8.2,0,1.9,1.4,1.1,True)
        side_door(m,4.9,0)
        cyl(m,(2.2,-.35,3.6),(2.2,-.35,R_EAVE+1.6),.16,'iz_galv',8)
        m.lathe((2.2,-.35,R_EAVE+1.6),[(-.02,.22),(.10,.22),(.10,.08),(.28,.08),(.28,.24),(.40,.24),(.46,.05)],'iz_galv_dark',8)
        downpipe(m,10.7,-.30,-.2,R_EAVE-.35)
    with m.at((0,6.5,0),180):
        # the izakaya spans local x -11..0.58
        cladding(m,-11,.58,0,-.35,3.5,planks,.34,.31,.06,skip=[(-7.3,-5.9)])
        base(m,-5.21,11.58);m.box((-5.21,-.09,3.55),(11.68,.16,.20),'arc_timber')
        frame(m,[-10.85,-7.5,-3.5,.43],-5.21,11.68,3.5,I_EAVE)
        small_window(m,-9.2,0,4.7,1.5,1.1,True);small_window(m,-5.5,0,4.7,1.5,1.1,False);small_window(m,-1.8,0,4.7,1.5,1.1,True)
        small_window(m,-2.6,0,1.8,1.3,1.0,False)
        v.door(m,-6.6,-.02,.05,1.05,2.05)
        pent(m,-10.2,-3.2,0,3.5,1.1,.35,brackets=True,positions=[-9.9,-6.7,-3.5])
        ac_unit(m,-9.5,-.04,2.4)
        downpipe(m,-10.7,-.30,-.2,I_EAVE-.35)

    # ---------------- Roofs: tall shallow gable over the ramen, flatter gable over the izakaya.
    gable_roof(m,(RX0-.8+RX1+.9)/2,0,(RX1+.9)-(RX0-.8),16.6,R_EAVE,1.7)
    gable_roof(m,(RX1-.1+IX1+.8)/2,-.5,(IX1+.8)-(RX1-.1),15.6,I_EAVE,.8)
    return m
