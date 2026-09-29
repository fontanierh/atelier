"""Half-timbered two-storey bookshop (本と文具) / wagashi shop (和菓子): glowing vitrine under a timber colonnade, slate-blue gable roof with exposed purlins."""
import math,random
from village import build as v
from hidamari import arcade

ASSETS={'HD_Shop_06':0,'HD_Shop_14':1}
W,D=21.4,15.6            # wall footprint (lot 22 x 16)
EAVE,RISE=7.3,3.0        # eave height, ridge rise (ridge along X at z 10.3)
RW,RD=W+2.4,D+2.4        # roof extents (1.2 m verge overhang, 1.2 m eaves)
SLAB=3.4                 # upper floor slab
TOP=.3                   # deck top (raised timber platform)
YG=-D/2+1.5              # recessed ground-floor face (vitrine grid line)
BOOKS=['rust','blue','green','clay','bk_yellow','arc_rose','bk_cream','green_dark']
SWEETS=['bk_pink','bk_mint','bk_cream','bk_matcha','clay']


def palette(variant):
    arcade.palette()
    v.PALETTE.update({
        'bk_plaster':(.56,.48,.34) if variant==0 else (.58,.48,.31),
        'bk_fascia':(.43,.27,.12),'bk_cream':(.68,.58,.40),'bk_timber':(.32,.18,.07),
        'bk_roof':(.05,.08,.13),'bk_roof_light':(.09,.12,.19),
        'bk_awning':(.05,.12,.26) if variant==0 else (.30,.09,.04),
        'bk_rib':(.24,.38,.52) if variant==0 else (.64,.36,.18),
        'bk_deck':(.24,.12,.045),'bk_stone':(.30,.28,.22),'bk_ginkgo':(.60,.38,.05),
        'bk_glow':(.74,.61,.43),                                   # lit vitrine back wall (soft canvas glow)
        'bk_yellow':(.62,.40,.08),'bk_pink':(.55,.24,.24),'bk_mint':(.30,.42,.28),
        'bk_matcha':(.28,.38,.11),'bk_lid':(.62,.56,.42),'bk_board':(.06,.07,.06),
        'bk_cat':(.24,.20,.16),'bk_glass':(.16,.20,.20),
    })


# ---------------------------------------------------------------- small parts

def disc(m,x,y,z,r,key,n=28,both=False):
    p=[(x+r*math.cos(k*math.tau/n),y,z+r*math.sin(k*math.tau/n)) for k in range(n)]
    m.poly(p,key)
    if both:m.poly(p[::-1],key)


def slab(m,pts,y,depth,key):
    """Planar polygon (x,z) counter-clockwise, front face at y facing -Y, extruded back by depth."""
    front=[(x,y,z) for x,z in pts];back=[(x,y+depth,z) for x,z in pts]
    m.poly(front,key);m.poly(back[::-1],key)
    n=len(pts)
    for i in range(n):
        j=(i+1)%n
        m.poly([front[i],back[i],back[j],front[j]],key)


def circle(x,z,r,n=32):
    return [(x+r*math.cos(k*math.tau/n),z+r*math.sin(k*math.tau/n)) for k in range(n)]


def emblem(m,x,y,z,w,variant,key='arc_trim',depth=.02):
    """Open book (variant 0) or a dango skewer (variant 1), facing -Y, standing `depth` proud of y."""
    if variant==0:
        for s in (-1,1):
            pts=[(x,z-w*.42),(x+s*w*.48,z-w*.32),(x+s*w*.48,z+w*.42),(x,z+w*.30)]
            slab(m,pts if s>0 else pts[::-1],y,depth,key)
        m.box((x,y+depth/2-.008,z),(.03,depth+.016,w*.74),key)
    else:
        m.beam((x-w*.44,y+depth/2,z-w*.40),(x+w*.44,y+depth/2,z+w*.40),.05,depth,'arc_timber')
        for i,c in enumerate(['bk_pink','bk_cream','bk_mint']):
            t=(i-1)*w*.27
            slab(m,circle(x+t,z+t,w*.19,16),y-.005,depth,c)


def signboard(m,y,variant,lettering):
    """Single flush-mounted plaque, with clearance to the roof and upper window."""
    x,z=-.85,5.25;w,h=6.35,1.55
    m.box((x,y-.07,z),(w,.14,h),'bk_timber',.025)
    m.box((x,y-.15,z),(w-.20,.025,h-.20),'arc_timber')
    for xx in [x-w/2+.07,x+w/2-.07]:m.box((xx,y-.17,z),(.14,.06,h),'bk_timber')
    for zz in [z-h/2+.07,z+h/2-.07]:m.box((x,y-.17,zz),(w,.06,.14),'bk_timber')
    icon_x=x-2.28
    if variant==1:
        m.beam((icon_x-.30,y-.205,z-.55),(icon_x+.27,y-.205,z+.47),.035,.04,'bk_cream')
        for i,key in enumerate(['bk_mint','bk_cream','bk_pink']):
            slab(m,circle(icon_x+(i-1)*.16,z+(i-1)*.29,.215,20),y-.245-i*.008,.035,key)
    else:emblem(m,icon_x,y-.23,z,.90,0,'bk_cream',.025)
    lettering(m,'本と文具' if variant==0 else '和菓子',(x+.52,y-.215,z-.35),2.5 if variant else 2.15,color='arc_ivory')


def awning(m,y0,z0,w,depth,drop):
    hw=w/2
    top=[(-hw,y0,z0),(hw,y0,z0),(hw,y0-depth,z0-drop),(-hw,y0-depth,z0-drop)]
    m.poly(top[::-1],'bk_awning')
    m.poly([(px,py,pz-.035) for px,py,pz in top],'bk_awning')
    n=int(w/1.4)
    for i in range(n+1):
        x=-hw+.3+i*(w-.6)/n
        m.beam((x,y0-.03,z0+.04),(x,y0-depth+.02,z0-drop+.04),.075,.06,'bk_rib')
    yv=y0-depth
    m.beam((-hw,yv-.01,z0-drop-.01),(hw,yv-.01,z0-drop-.01),.06,.06,'bk_rib')   # light front edge rail
    seg=int(w/.9);yv=yv-.02
    for i in range(seg):
        xa=-hw+i*w/seg;xb=xa+w/seg;xm=(xa+xb)/2
        p=[(xa,yv,z0-drop-.03),(xa,yv,z0-drop-.18),(xm,yv,z0-drop-.30),(xb,yv,z0-drop-.18),(xb,yv,z0-drop-.03)]
        m.poly(p,'bk_awning');m.poly(p[::-1],'bk_awning')
    m.beam((-hw,yv-.012,z0-drop-.20),(hw,yv-.012,z0-drop-.20),.03,.04,'bk_rib')


def books(m,x,y,z,w,r,depth=.22,tall=(.26,.42)):
    n=int(w/.17)
    for i in range(n):
        h=r.uniform(*tall);bw=r.uniform(.11,.16)
        m.box((x-w/2+.1+i*.17,y,z+h/2),(bw,depth,h),r.choice(BOOKS),.008)


def sweets(m,x,y,z,w,r):
    n=int(w/.38)
    for i in range(n):
        xx=x-w/2+.22+i*.38
        m.box((xx,y,z+.09),(.30,.26,.18),r.choice(SWEETS),.012)
        m.box((xx,y,z+.20),(.33,.28,.04),'bk_lid',.01)


def flat_stack(m,x,y,z,r,count):
    for k in range(count):
        m.box((x+r.uniform(-.03,.03),y+r.uniform(-.03,.03),z+.03+k*.06),(.40,.29,.055),r.choice(BOOKS),.008)


def stone_bench(m,x,y,z,w=1.6):
    m.box((x,y,z+.42),(w,.52,.13),'bk_stone',.03)
    for dx in (-w*.36,w*.36):m.box((x+dx,y,z+.18),(.22,.42,.36),'stone',.02)
    m.collider((x,y,z+.25),(w,.55,.5))


def cat(m,x,y,z):
    m.box((x,y,z+.15),(.46,.20,.20),'bk_cat',.04)
    m.box((x+.26,y,z+.30),(.18,.18,.16),'bk_cat',.03)
    for dy in (-.05,.05):
        p=[(x+.31,y+dy-.03,z+.37),(x+.31,y+dy+.03,z+.37),(x+.31,y+dy,z+.45)]
        m.poly(p,'bk_cat');m.poly(p[::-1],'bk_cat')
    m.beam((x-.22,y,z+.18),(x-.42,y+.10,z+.36),.05,.05,'bk_cat')


def shrub_planter(m,x,y,z,w,seed):
    r=random.Random(seed)
    m.box((x,y,z+.28),(w,.62,.56),'bk_timber',.03)
    for zz in (.12,.42):m.box((x,y-.32,z+zz),(w+.06,.06,.11),'arc_timber')
    m.collider((x,y,z+.3),(w,.65,.6))
    for i in range(int(w/.45)):
        xx=x-w/2+.25+i*.45;s=r.uniform(.28,.36)
        m.lathe((xx,y+r.uniform(-.1,.1),z+.55),[(0,0),(.02,.06),(.12,s*.8),(.32,s),(.52,s*.75),(.66,.05),(.68,0)],'bk_ginkgo',8)


def downpipe(m,x,y,z0,z1):
    m.beam((x,y,z0),(x,y,z1-.35),.06,.06,'metal')
    m.beam((x,y,z1-.35),(x,y+.4,z1),.06,.06,'metal')
    for zz in (z0+.6,z0+3.5,z1-.8):m.box((x,y+.03,zz),(.12,.14,.08),'metal')


def pavement_pot(m,x,y,scale):
    # Give the tapered jar a real flat foot at pavement height. A point
    # bottom lifted 2 cm made these small pots read as hovering in-game.
    v.pot(m,x,y,0,scale,'clay',plant=True)
    radius=.19*scale
    m.lathe((x,y,0),[(0,0),(0,radius),(.025*scale,radius)],'clay',12)


def win(m,x,y,z,w,h,cols=2,rows=2):
    """Warm-timber window with a cols x rows mullion grid, facing -Y (frame back at y)."""
    m.box((x,y,z),(w+.18,.18,h+.18),'bk_timber')
    m.box((x,y-.115,z),(w,.04,h),'arc_glass')
    for i in range(cols+1):m.box((x-w/2+i*w/cols,y-.17,z),(.09,.14,h+.17),'bk_timber')
    for j in range(rows+1):m.box((x,y-.18,z-h/2+j*h/rows),(w+.2,.13,.09),'bk_timber')
    m.box((x,y-.27,z-h/2-.08),(w+.4,.50,.14),'bk_timber')


def shutter(m,x,y,z):
    """One folded shutter leaf: 0.42 x 2.6 timber panel, three dark battens, proud cream inset."""
    m.box((x,y-.10,z),(.42,.10,2.6),'bk_timber')             # face y-.15
    m.box((x,y-.155,z),(.28,.03,2.36),'bk_cream')            # inset, face y-.17
    for zz in (z-.95,z,z+.95):m.box((x,y-.18,zz),(.44,.06,.06),'arc_timber')


def bookshelf(m,x,y,r,kind):
    """Freestanding 1.6 x .45 x 2.4 shelf on the deck, front facing -Y, four packed rows."""
    for dx in (-.76,.76):m.box((x+dx,y,TOP+1.2),(.08,.45,2.4),'bk_timber')
    m.box((x,y+.20,TOP+1.2),(1.6,.05,2.4),'bk_timber')
    m.box((x,y,TOP+2.43),(1.7,.5,.06),'bk_timber')
    for z in (TOP+.12,TOP+.72,TOP+1.32,TOP+1.92):
        m.box((x,y,z),(1.55,.44,.06),'arc_timber')
        if kind==0:books(m,x,y-.02,z+.03,1.4,r,.30,(.26,.40))
        else:
            for j in range(4):m.lathe((x-.55+j*.37,y-.02,z+.03),[(0,.12),(.12,.15),(.24,.06),(.26,0)],'clay',8)
    m.collider((x,y,TOP+1.2),(1.7,.5,2.45))


# ---------------------------------------------------------------- roof

def roof(m):
    hw,hd,gw=RW/2,RD/2,W/2
    m.box((0,0,EAVE-.08),(W-.02,RD,.16),'arc_timber')       # closed soffit slab between the gable walls
    def zz(y):return EAVE+RISE*(1-abs(y)/hd)
    cols=8
    for s in (-1,1):
        for c in range(cols):
            xa=-hw+c*RW/cols;xb=xa+RW/cols
            p=[(xa,0,EAVE+RISE),(xb,0,EAVE+RISE),(xb,s*hd,EAVE),(xa,s*hd,EAVE)]
            m.poly(p[::-1] if s<0 else p,v.color_variant('bk_roof',.07))
        for xa,xb in ((-hw,-gw),(gw,hw)):                    # verge overhang underside
            q=[(xa,0,EAVE+RISE-.16),(xb,0,EAVE+RISE-.16),(xb,s*hd,EAVE-.16),(xa,s*hd,EAVE-.16)]
            m.poly(q[::-1] if s>0 else q,'arc_timber')
        for k in range(1,int(hd)):                            # thick battens every metre = tile courses
            y=s*k
            if s<0:
                m.beam((-hw,y,zz(y)+.05),(3.9,y,zz(y)+.05),.10,.12,'bk_roof_light')
                m.beam((7.1,y,zz(y)+.05),(hw,y,zz(y)+.05),.10,.12,'bk_roof_light')
            else:m.beam((-hw,y,zz(y)+.05),(hw,y,zz(y)+.05),.10,.12,'bk_roof_light')
        m.beam((-hw,s*hd,EAVE-.05),(hw,s*hd,EAVE-.05),.24,.38,'bk_fascia')      # warm continuous eave fascia
        for i in range(int(RW/.5)):
            m.box((-hw+.25+i*.5,s*(hd-.14),EAVE+.10),(.44,.30,.20),'bk_roof_light',.02)
        n=int(RW/.95)
        for i in range(n+1):
            x=-hw+.35+i*(RW-.7)/n
            m.beam((x,s*(D/2-.2),EAVE-.22),(x,s*(hd-.14),EAVE-.22),.12,.16,'bk_fascia')   # rafter tails
        for z in (EAVE+.3,EAVE+RISE*.55):                     # purlins poking 1.2 m past the gable walls
            y=s*hd*(1-(z-EAVE)/RISE)
            m.box((0,y,z-.32),(RW+.4,.22,.24),'bk_timber')
    m.box((0,0,EAVE+RISE-.32),(RW+.4,.22,.24),'bk_timber')   # ridge purlin
    for s in (-1,1):                                          # plaster gable walls at the building line
        x=s*gw
        p=[(x,-hd,EAVE-.16),(x,hd,EAVE-.16),(x,0,EAVE+RISE)]
        m.poly(p if s>0 else p[::-1],'bk_plaster')
        m.box((x+s*.06,0,EAVE+RISE/2-.15),(.12,.22,RISE-.4),'bk_timber')
        m.box((x+s*.06,0,EAVE+RISE*.40),(.12,hd*1.15,.18),'bk_timber')
        for sy in (-1,1):m.beam((x+s*.06,sy*hd*.95,EAVE+.05),(x+s*.06,sy*hd*.55,EAVE+RISE*.40),.12,.18,'bk_timber')
        m.box((x+s*.03,0,EAVE+RISE*.62),(.06,.8,.42),'arc_timber')
        x=s*hw                                                # verge beams along the roof edge
        for sy in (-1,1):m.beam((x,sy*hd,EAVE-.08),(x,0,EAVE+RISE-.08),.24,.30,'bk_fascia')
    m.box((0,0,EAVE+RISE+.08),(RW+.1,.35,.25),'bk_roof')      # ridge cap
    for i in range(int(RW/.65)):
        m.box((-hw+.3+i*.65,0,EAVE+RISE+.24),(.6,.40,.10),'bk_roof_light',.02)


def dormer(m,x):
    yf,yb=-D/2-.4,-.5                                         # face just above the eave fascia; body buried back into the roof
    zb,zt=7.3,9.4
    m.box((x,(yf+yb)/2,(zb+zt)/2),(2.6,yb-yf,zt-zb),'bk_plaster')
    for dx in (-1.25,1.25):m.box((x+dx,yf-.06,8.5),(.14,.14,1.8),'bk_timber')
    win(m,x,yf-.06,8.55,1.4,.9,2,1)
    ridge,ze,ov=10.1,9.35,.35
    for side in (-1,1):
        p=[(x+side*1.5,yf-ov,ze),(x+side*1.5,yb,ze),(x,yb,ridge),(x,yf-ov,ridge)]
        m.poly(p[::-1] if side<0 else p,'bk_roof')
        q=[(px,py,pz-.08) for px,py,pz in p]
        m.poly(q if side<0 else q[::-1],'arc_timber')
        m.beam((x+side*1.5,yf-ov,ze-.02),(x,yf-ov,ridge-.02),.14,.14,'bk_timber')
    m.beam((x,yf-ov-.02,ridge+.02),(x,yb,ridge+.02),.18,.12,'bk_roof')
    for y,s in ((yf-.01,1),(yb+.01,-1)):
        p=[(x-1.5,y,ze-.05),(x+1.5,y,ze-.05),(x,y,ridge-.03)]
        m.poly(p if s>0 else p[::-1],'bk_plaster')


# ---------------------------------------------------------------- facades

def side(m,variant,right):
    with m.at((W/2 if right else -W/2,0,0),90 if right else -90):
        # local -Y is outward; local x runs along world y (front is local -x on the right, +x on the left)
        for z in (3.6,6.95):m.box((0,-.12,z),(D+.3,.22,.34),'bk_timber')
        for x in (-6.4,0,6.4):m.box((x,-.11,5.4),(.2,.2,3.5),'bk_timber')
        for x in (-3.2,3.2):
            win(m,x,-.06,5.55,2.1,2.3)
            m.box((x,-.19,4.15),(2.6,.25,.12),'bk_timber')
        fx=-1 if right else 1
        if right:
            v.door(m,2.6,-.05,TOP,1.15,2.1)
            # Match the front/rear 12 cm tread beneath the 30 cm deck.
            m.box((2.6,-.40,-.14),(1.8,.8,.52),'bk_deck')
            m.collider((2.6,-.40,-.14),(1.8,.8,.52))
            m.box((2.6,-.56,3.05),(2.0,1.1,.08),'bk_roof')
            m.box((2.6,-.55,2.99),(1.9,1.0,.08),'arc_timber')
            for dx in (-.8,.8):m.beam((2.6+dx,-.1,2.35),(2.6+dx,-.95,2.9),.08,.08,'bk_timber')
            lows=(-1.6,)
        else:
            lows=(-2.0,3.5)
        for x in lows:
            win(m,x,-.06,1.9,1.6,1.7)
            m.box((x,-.19,.80),(2.1,.25,.12),'bk_timber')
        arcade.lantern(m,fx*6.0,-.55,2.5,.42)
        m.beam((fx*6.0,-.04,3.55),(fx*6.0,-.6,3.55),.06,.06,'arc_timber')
        downpipe(m,-fx*(D/2-.45),-.16,TOP+.05,EAVE-.25)
        for k in range(3):m.box((fx*5.4,-.07,2.35+k*.22),(.9,.12,.08),'arc_timber')


def back(m,variant):
    with m.at((0,D/2,0),180):
        for z in (3.6,6.95):m.box((0,-.12,z),(W+.3,.22,.34),'bk_timber')
        for x in (-5.2,5.2):
            for dx in (-1.35,1.35):m.box((x+dx,-.11,5.4),(.2,.2,3.5),'bk_timber')
            win(m,x,-.06,5.55,2.1,2.3)
        m.box((0,-.11,5.4),(.2,.2,3.5),'bk_timber')
        v.door(m,-3.0,-.05,TOP,1.2,2.15)
        m.box((-3.0,-.36,-.14),(2.0,.7,.52),'bk_deck');m.collider((-3.0,-.36,-.14),(2.0,.7,.52))
        p=[(-4.4,-.02,3.05),(-1.6,-.02,3.05),(-1.6,-1.2,2.6),(-4.4,-1.2,2.6)]
        m.poly(p[::-1],'bk_roof');m.poly([(px,py,pz-.07) for px,py,pz in p],'arc_timber')
        m.beam((-4.4,-1.2,2.58),(-1.6,-1.2,2.58),.1,.12,'bk_timber')
        for x in (-4.1,-1.9):m.beam((x,-.1,2.05),(x,-1.1,2.55),.09,.09,'bk_timber')
        win(m,4.0,-.06,1.9,1.6,1.7)
        for k in range(3):m.box((7.5,-.07,2.35+k*.22),(.9,.12,.08),'arc_timber')
        downpipe(m,9.6,-.16,TOP+.05,EAVE-.25)


def storefront(m,variant,lettering):
    r=random.Random(31+variant)
    yg=YG
    # two lit vitrines: warm glowing back wall, packed book rows, timber grid on the glass line
    for x in (-5.55,5.55):
        m.box((x,yg+1.0,2.05),(8.3,.06,2.7),'bk_glow')                # lit back panel
        m.box((x,yg+.45,.50),(8.3,1.5,.44),'bk_timber')                # vitrine floor (top at .72)
        m.box((x,yg-.30,.46),(8.5,.14,.5),'bk_timber')                 # skirting below the sill
        m.box((x,yg-.30,.78),(8.5,.14,.14),'bk_timber')                # sill rail
        m.box((x,yg-.30,3.35),(8.5,.14,.14),'bk_timber')               # head rail
        for dx in (-4.15,4.15):m.box((x+dx,yg-.30,2.06),(.12,.14,2.72),'bk_timber')
        for dx in (-2.85,-.95,.95,2.85):m.box((x+dx,yg-.30,2.05),(.10,.12,2.7),'bk_timber')   # mullions
        m.box((x,yg-.30,2.6),(8.3,.12,.10),'bk_timber')                # transom
        for z in (1.80,2.75):m.box((x,yg+.55,z),(8.2,.9,.08),'bk_timber')   # shelf boards
        if variant==0:
            books(m,x,yg+.35,.73,7.2,r);books(m,x,yg+.35,1.85,7.2,r);books(m,x,yg+.35,2.80,7.2,r,.22,(.24,.40))
            for dx in (-2.4,1.9):flat_stack(m,x+dx,yg-.02,.73,r,4)
        else:
            sweets(m,x,yg+.35,.73,7.2,r);sweets(m,x,yg+.35,2.80,7.2,r)
            for j in range(4):
                xx=x-2.7+j*1.8
                m.lathe((xx,yg+.35,1.85),[(0,0),(0,.22),(.03,.22),(.05,.05),(.22,.05),(.25,.18),(.27,.18),(.27,0)],'bk_cream',10)
                for k in range(5):
                    a=k*math.tau/5
                    m.lathe((xx+math.cos(a)*.11,yg+.35+math.sin(a)*.11,2.12),[(0,0),(0,.03),(.03,.045),(.06,.03),(.07,0)],SWEETS[(j+k)%5],6)
    for s in (-1,1):                                                    # plaster piers closing the vitrine ends
        m.box((s*10.2,yg+.4,1.5),(1.0,1.5,3.9),'bk_plaster');m.collider((s*10.2,yg+.4,1.5),(1.0,1.5,3.9))
    # open doorway with a lit interior: cream walls, canvas floor and ceiling, shelf, hanging lantern
    for x in (-1.45,1.45):
        m.box((x,yg+.4,1.85),(.22,1.6,3.1),'bk_timber');m.collider((x,yg+.4,1.85),(.22,1.6,3.1))
    m.box((0,yg+.25,3.15),(3.2,.55,.6),'bk_timber')
    m.box((0,yg+1.5,.32),(2.5,2.9,.05),'arc_canvas')
    m.box((0,yg+1.5,3.36),(2.5,2.9,.04),'arc_canvas')
    for x in (-1.27,1.27):m.box((x,yg+1.5,1.85),(.04,2.9,2.9),'bk_cream')
    with m.at((0,0,TOP)):arcade.shelf(m,0,yg+2.65,0 if variant==0 else 1,7+variant)
    arcade.lantern(m,0,yg-.6,2.3,.5)
    emblem(m,0,yg-.6-.5*.49,2.3,.34,variant,'arc_trim')
    # colonnade posts on the deck under the overhanging upper storey
    for x in (-2.3,2.3):
        m.box((x,-D/2+.25,1.85),(.3,.3,3.1),'bk_timber');m.collider((x,-D/2+.25,1.85),(.3,.3,3.1))
    m.box((0,-D/2+.1,3.45),(W+.3,.28,.36),'arc_timber')   # deck fascia / floor beam
    # street props under the colonnade
    stone_bench(m,-9.95,-D/2+.5,TOP,1.2)
    ty=-D/2+.3;cy=-D/2+.2
    if variant==0:
        m.box((-5.5,ty,TOP+.78),(2.6,.95,.08),'bk_timber',.02)
        for dx,dy in ((-1.2,-.38),(1.2,-.38),(-1.2,.38),(1.2,.38)):m.box((-5.5+dx,ty+dy,TOP+.37),(.1,.1,.74),'bk_timber')
        m.collider((-5.5,ty,TOP+.4),(2.6,.95,.85))
        for j,(dx,dy) in enumerate(((-.95,-.2),(-.35,.15),(.3,-.22),(.9,.12),(.05,.25))):flat_stack(m,-5.5+dx,ty+dy,TOP+.82,r,3+j%3)
        books(m,-5.5,ty+.28,TOP+.82,1.6,r,.2,(.22,.32))
    else:
        m.box((-5.5,ty,TOP+.45),(2.6,.95,.9),'bk_timber',.02);m.collider((-5.5,ty,TOP+.45),(2.6,.95,.9))
        m.box((-5.5,ty,TOP+1.15),(2.5,.85,.5),'bk_glass')
        m.box((-5.5,ty,TOP+1.42),(2.6,.95,.05),'arc_timber')
        sweets(m,-5.5,ty,TOP+.93,2.2,r)
    # book cart (1 m tall body on four wheels, two rows on top)
    m.box((5.3,cy,TOP+.80),(1.7,.8,1.0),'bk_timber',.02);m.collider((5.3,cy,TOP+.7),(1.9,1.0,1.4))
    for x in (4.5,6.1):m.box((x,cy,TOP+.85),(.06,.86,1.1),'arc_timber')
    for x in (4.55,6.05):
        for y in (cy-.45,cy+.45):
            with m.at((x,y,TOP+.22),90):slab(m,circle(0,0,.22,14),-.03,.06,'arc_timber')
    m.beam((4.5,cy,TOP+1.42),(6.1,cy,TOP+1.42),.05,.05,'arc_timber')
    if variant==0:
        for dy in (-.2,.2):books(m,5.3,cy+dy,TOP+1.31,1.5,r,.30,(.24,.36))
    else:
        for j in range(3):
            for k in range(2):
                m.box((4.75+j*.55,cy-.2+k*.4,TOP+1.46+(j%2)*.1),(.42,.32,.3),SWEETS[(j+k)%5],.02)
                m.box((4.75+j*.55,cy-.2+k*.4,TOP+1.63+(j%2)*.1),(.45,.35,.04),'bk_lid',.01)
    bookshelf(m,W/2-.9,-D/2+.3,r,variant)
    cat(m,1.6,-D/2-1.0,.12)


def front(m,variant,lettering):
    y=-D/2
    for x in (-4.75,4.75):m.box((x,y-.1,5.4),(.22,.22,3.5),'bk_timber')
    for z in (3.6,6.95):m.box((0,y-.1,z),(W+.3,.22,.34),'bk_timber')
    for x in (-7.3,7.3):
        win(m,x,y-.06,5.55,2.6,2.5,3,2)
        for s in (-1,1):shutter(m,x+s*1.68,y,5.55)
    win(m,3.6,y-.06,6.0,1.6,2.0)
    signboard(m,y,variant,lettering)
    awning(m,y-.22,3.72,W-.4,1.55,.75)
    # hanging round sign on a bracket at the right front corner
    px=W/2+.02;yb=y+.08
    m.beam((px+.15,yb,3.35),(px+1.35,yb,3.35),.09,.09,'bk_timber')
    m.beam((px+.15,yb,2.85),(px+.5,yb,3.3),.06,.06,'bk_timber')
    sx=px+.9
    for dx in (-.25,.25):m.beam((sx+dx,yb,3.31),(sx+dx,yb,3.0),.03,.03,'metal')
    with m.at((sx,yb,2.66),0):
        slab(m,circle(0,0,.46,28),-.03,.06,'bk_timber')
        for s in (-1,1):
            with m.at((0,0,0),0 if s<0 else 180):
                disc(m,0,-.04,0,.38,'bk_cream')
                emblem(m,0,-.08,0,.48,variant,'arc_trim',.03)


def props(m,variant,lettering):
    yf=-D/2
    # A-frame board on the pavement (chalk drawing + one authored character)
    with m.at((3.6,yf-1.3,.02),-14):
        for x in (-.45,.45):m.beam((x,-.25,0),(x,.12,1.45),.07,.07,'bk_timber')
        m.box((0,-.05,.85),(.9,.07,1.3),'bk_timber');m.box((0,-.10,.85),(.76,.025,1.12),'bk_board')
        emblem(m,0,-.13,1.08,.42,variant,'bk_cream',.015)
        lettering(m,'本' if variant==0 else '菓',(0,-.135,.36),1.1,color='arc_ivory')
        m.collider((0,0,.75),(1.0,.55,1.5))
    pavement_pot(m,-6.9,yf-1.55,1.05);m.collider((-6.9,yf-1.55,.35),(.7,.7,.7))
    shrub_planter(m,10.1,yf-1.75,.02,1.5,3+variant)
    pavement_pot(m,W/2+.5,-1.9,.8)


# ---------------------------------------------------------------- building

def build(name,variant,lettering):
    palette(variant)
    m=v.Mesh(name)
    yg=YG
    # stone plinth, raised timber deck + step (walkable), then the ground-floor wall pieces around the vitrines and doorway
    m.box((0,0,-.225),(W+.3,D+.3,.35),'bk_stone')
    m.box((0,-.5,-.05),(W+.2,16.4,.7),'bk_deck');m.collider((0,-.5,-.05),(W+.2,16.4,.7))
    m.box((0,-8.9,-.14),(W+.2,.42,.52),'bk_deck');m.collider((0,-8.9,-.14),(W+.2,.42,.52))
    for s in (-1,1):
        cx=s*(W/2+1.35)/2;cw=W/2-1.35;y0=yg+1.05
        m.box((cx,(y0+D/2)/2,1.5),(cw,D/2-y0,3.9),'bk_plaster');m.collider((cx,(y0+D/2)/2,1.5),(cw,D/2-y0,3.9))
    m.box((0,(yg+3+D/2)/2,1.5),(2.7,D/2-yg-3,3.9),'bk_plaster');m.collider((0,(yg+3+D/2)/2,1.5),(2.7,D/2-yg-3,3.9))
    m.box((0,0,SLAB+.12),(W,D,.25),'arc_timber')
    m.box((0,0,(SLAB+.2+EAVE-.1)/2),(W,D,EAVE-.1-SLAB-.2),'bk_plaster');m.collider((0,0,5.4),(W,D,3.6))
    for x in (-1,1):
        for y in (-1,1):
            m.box((x*(W/2+.02),y*(D/2+.02),3.45),(.4,.4,7.6),'bk_timber')
            if y<0:m.collider((x*(W/2+.02),y*(D/2+.02),1.5),(.4,.4,3.8))
    storefront(m,variant,lettering)
    front(m,variant,lettering)
    side(m,variant,True);side(m,variant,False)
    back(m,variant)
    roof(m)
    dormer(m,5.5)
    props(m,variant,lettering)
    return m
