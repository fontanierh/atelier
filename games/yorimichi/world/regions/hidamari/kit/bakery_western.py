"""Meiji pseudo-western (giyofu) bakery: sage clapboard, dark copper mansard, corner turret; variant 1 is a florist."""
import math,random
from village import build as v
from hidamari import arcade,plaza

ASSETS={'HD_Shop_03':0,'HD_Shop_11':1}
W,D=22,16
GF=4.0          # ground floor ceiling / upper storey base
CORNICE=8.0     # top of the main wall
BREAK=11.0      # top of the steep mansard slope (curb line)
RIDGE=12.4      # ridge of the shallow cap
TX,TY=9.9,-6.9  # turret centre (stretched octagon, ~1 m proud of both walls)
OCT=[(1.1,-2.15),(2.15,-1.1),(2.15,1.1),(1.1,2.15),(-1.1,2.15),(-2.15,1.1),(-2.15,-1.1),(-1.1,-2.15)]


def palette(variant):
    arcade.palette();plaza.palette()
    v.PALETTE.update({
        # the game grade lifts and cools everything hard: keep every green far down, whites at ivory
        'bw_sage':(.30,.33,.18),'bw_sage2':(.25,.28,.15),'bw_sage_dark':(.14,.17,.09),
        'bw_white':(.52,.49,.39),'bw_white2':(.42,.40,.32),
        'bw_copper':(.020,.048,.034),'bw_copper_dark':(.011,.028,.019),'bw_copper_lit':(.028,.062,.044),
        'bw_shutter':(.020,.042,.018),'bw_shutter_dark':(.012,.026,.012),
        'bw_belt':(.045,.09,.04),
        'bw_door':(.022,.048,.020) if variant==0 else (.12,.05,.07),
        'bw_stripe':(.06,.13,.06) if variant==0 else (.30,.08,.10),
        # loaves sit in the M_Arcade 'leaf' glow window (r>=.4, g>=.24, b<=.07) so they self-light in the recess
        'bw_bread':(.50,.27,.05),'bw_crust':(.42,.25,.03),'bw_bun':(.58,.36,.06),
        'bw_brass':(.50,.36,.10),'bw_glass':(.09,.10,.085),'bw_bucket':(.16,.17,.16),
        'bw_base':(.14,.135,.11),'bw_step':(.30,.28,.22),'bw_chalk':(.06,.065,.055),
        # back panel of the display in the 'canvas' glow window (r .70-.79, g>=.55, b>=.35)
        'bw_glow':(.74,.58,.38),
    })


# ---------------------------------------------------------------- facade pieces (local frame: wall plane y=0, outside -Y)

def boards(m,x0,x1,z0,z1):
    """Horizontal lap siding: alternating sage boards over the darker core wall."""
    n=max(1,round((z1-z0)/.34));pitch=(z1-z0)/n
    for k in range(n):
        m.box(((x0+x1)/2,-.06,z0+(k+.5)*pitch),(x1-x0,.06,pitch-.045),'bw_sage' if k%2 else 'bw_sage2')


def sash(m,x,y,z,w,h,lit=True,shutters=False):
    """Tall white-framed sash window with a warm pane, meeting rail and sill."""
    m.box((x,y-.07,z),(w+.32,.14,h+.32),'bw_white')
    m.box((x,y-.16,z),(w,.06,h),'paper' if lit else 'bw_glass')
    m.box((x,y-.20,z),(.07,.06,h),'bw_white')
    m.box((x,y-.20,z),(w,.06,.11),'bw_white')
    for dz in (-h/4,h/4):m.box((x,y-.20,z+dz),(w,.05,.05),'bw_white')
    m.box((x,y-.20,z-h/2-.09),(w+.5,.34,.13),'bw_white')
    m.box((x,y-.12,z+h/2+.12),(w+.5,.24,.18),'bw_white')
    if shutters:
        for s in (-1,1):
            sx=x+s*(w/2+.16+.30)
            m.box((sx,y-.08,z),(.58,.10,h+.20),'bw_shutter')
            for k in range(7):m.box((sx,y-.145,z-h/2+.1+k*(h-.2)/6),(.46,.04,.06),'bw_shutter_dark')


def pent_hood(m,x,z,w=2.6,depth=1.0):
    """Small copper pent roof over a side/back door, closed underneath."""
    p=[(x-w/2,0,z),(x+w/2,0,z),(x+w/2,-depth,z-.45),(x-w/2,-depth,z-.45)]
    m.poly(p[::-1],'bw_copper');m.poly([(a,b,c-.05) for a,b,c in p],'bw_white2')
    m.beam((x-w/2,-depth,z-.47),(x+w/2,-depth,z-.47),.10,.12,'bw_copper_dark')
    for xx in (x-w/2+.2,x+w/2-.2):m.beam((xx,-.05,z-1.0),(xx,-depth+.08,z-.52),.08,.08,'bw_white')


def downpipe(m,x,ztop):
    m.beam((x,-.20,-.3),(x,-.20,ztop),.07,.07,'metal')
    m.beam((x,-.20,ztop),(x,-.62,ztop+.28),.07,.07,'metal')
    m.lathe((x,-.20,.02),[(0,.16),(.05,.16),(.05,0)],'metal',8)


def vent(m,x,z):
    m.box((x,-.06,z),(.7,.12,.5),'bw_white2')
    for k in range(4):m.box((x,-.14,z-.18+k*.12),(.56,.05,.05),'bw_shutter_dark')


def dentils(m,x0,x1):
    """Dentil blocks hung under the edge of the 1 m cornice soffit."""
    k=0
    while True:
        x=x0+k*1.1
        if x>x1:break
        m.box((x,-.85,7.70),(.26,.32,.22),'bw_white');k+=1


def wall_side(m,length,upper_x,ground_x,door_x=None,vent_x=None,pipes=()):
    """Dress one exposed side: siding, belt, frieze, sash windows, door, downpipes."""
    L=length/2
    boards(m,-L+.15,L-.15,-.2,4.72)
    boards(m,-L+.15,L-.15,4.88,CORNICE-.55)
    m.box((0,-.09,4.80),(length+.1,.12,.14),'bw_belt')
    m.box((0,-.10,7.70),(length+.3,.32,.45),'bw_white')
    for x in upper_x:sash(m,x,-.02,6.05,1.25,2.2,True,shutters=True)
    for x in ground_x:sash(m,x,-.02,2.15,1.25,2.0,True,shutters=True)
    if door_x is not None:
        v.door(m,door_x,-.06,.10,1.15,2.25)
        pent_hood(m,door_x,3.05)
        m.box((door_x,-.45,-.15),(1.9,.9,.5),'bw_step',.03)
        m.collider((door_x,-.45,-.15),(1.9,.9,.5))
    if vent_x is not None:vent(m,vent_x,3.3)
    for x in pipes:downpipe(m,x,CORNICE-.15)
    dentils(m,-L+.3,L-.25)


# ---------------------------------------------------------------- roof

def hip_ring(m,bw,bd,z0,tw,td,z1,keys):
    """Four sloped facets between a lower and an upper rectangle (degenerate top = ridge). keys: one key or [front,right,back,left]."""
    if isinstance(keys,str):keys=[keys]*4
    b=[(-bw,-bd,z0),(bw,-bd,z0),(bw,bd,z0),(-bw,bd,z0)]
    t=[(-tw,-td,z1),(tw,-td,z1),(tw,td,z1),(-tw,td,z1)]
    for i in range(4):
        m.poly([b[i],b[(i+1)%4],t[(i+1)%4],t[i]],keys[i])
    return b,t


def ring_beams(m,pts,w,key):
    for i in range(4):m.beam(pts[i],pts[(i+1)%4],w,w,key)


def mansard(m):
    """Two-pitch mansard: ~66 deg lower slope over the 1 m cornice, curb, then a ~10 deg cap to the ridge."""
    bw,bd=W/2+1.0,D/2+1.0;tw,td=W/2-.2,D/2-.2;z0=CORNICE+.3
    b,t=hip_ring(m,bw,bd,z0,tw,td,BREAK,['bw_copper_lit','bw_copper','bw_copper','bw_copper'])
    # standing-seam / tile courses on the steep slope
    for row in range(1,8):
        f=row/8;zz=z0+(BREAK-z0)*f
        xw=bw+(tw-bw)*f;yd=bd+(td-bd)*f
        for s in (-1,1):
            m.beam((-xw,s*yd,zz),(xw,s*yd,zz),.07,.07,'bw_copper_dark')
            m.beam((s*xw,-yd,zz),(s*xw,yd,zz),.07,.07,'bw_copper_dark')
    for i in range(4):m.beam(b[i],t[i],.16,.16,'bw_copper_dark')
    ring_beams(m,b,.22,'bw_copper_dark')          # eave lip over the cornice edge
    ring_beams(m,t,.22,'bw_copper_dark')          # curb at the break line
    # shallow hipped cap and ridge
    rw=5.0
    hip_ring(m,tw,td,BREAK,rw,0,RIDGE,'bw_copper')
    for i in range(4):m.beam(t[i],(rw if i in (1,2) else -rw,0,RIDGE),.14,.14,'bw_copper_dark')
    m.box((0,0,RIDGE+.03),(rw*2+.3,.30,.22),'bw_copper_dark',.04)


def dormer(m,x):
    """Dormer punched into the steep slope: vertical white front, copper cheeks, small gable roof under the curb."""
    y0=-D/2-.90
    m.box((x,y0+.70,9.475),(1.5,1.4,2.05),'bw_copper')
    m.box((x,y0-.05,9.475),(1.56,.12,2.05),'bw_white')
    for s in (-1,1):m.box((x+s*.70,y0-.10,9.475),(.16,.10,2.05),'bw_white2')
    sash(m,x,y0-.11,9.35,.8,1.05,True)
    for s in (-1,1):
        p=[(x,y0-.25,10.85),(x,y0+1.45,10.85),(x+s*.98,y0+1.45,10.45),(x+s*.98,y0-.25,10.45)]
        m.poly(p if s<0 else p[::-1],'bw_copper')
        q=[(a,b,c-.05) for a,b,c in p]
        m.poly(q[::-1] if s<0 else q,'bw_white2')
        m.beam((x,y0-.25,10.83),(x+s*.98,y0-.25,10.43),.09,.10,'bw_white')
    m.poly([(x-.98,y0-.22,10.43),(x+.98,y0-.22,10.43),(x,y0-.22,10.83)],'bw_white')
    m.poly([(x-.98,y0+1.45,10.43),(x,y0+1.45,10.83),(x+.98,y0+1.45,10.43)],'bw_copper')
    m.beam((x,y0-.25,10.87),(x,y0+1.45,10.87),.08,.08,'bw_copper_dark')


def chimney(m):
    x,y=-6.0,3.5
    m.box((x,y,11.775),(1.0,.8,3.15),'stone')
    m.box((x,y,13.45),(1.2,1.0,.2),'bw_white2')
    m.box((x,y,13.62),(.8,.6,.15),'bw_copper_dark')


# ---------------------------------------------------------------- turret (stretched octagon, local frame centred on TX,TY)

def octo(off):
    """Octagon ring offset outward by `off` metres (approximate for the stretched shape)."""
    s=1+off/2.15
    return [(x*s,y*s) for x,y in OCT]


def oct_band(m,z0,z1,off0,off1,key,caps=False):
    a=octo(off0);b=octo(off1)
    for k in range(8):
        j=(k+1)%8
        m.poly([(a[k][0],a[k][1],z0),(a[j][0],a[j][1],z0),(b[j][0],b[j][1],z1),(b[k][0],b[k][1],z1)],key)
    if caps:
        m.poly([(x,y,z1) for x,y in b],key)
        m.poly([(x,y,z0) for x,y in a][::-1],key)


def turret(m,variant):
    with m.at((TX,TY,0),0):
        # base and base board
        oct_band(m,-.4,.10,.22,.22,'bw_base',True)
        oct_band(m,.08,.35,.16,.16,'bw_sage_dark',True)
        # lap siding bands with a dark groove between them
        z=.35;k=0
        while z<10.26:
            top=min(z+.30,10.28)
            oct_band(m,z,top,0,0,'bw_sage' if k%2 else 'bw_sage2')
            if top<10.28:oct_band(m,top,top+.04,-.05,-.05,'bw_sage_dark')
            z+=.34;k+=1
        oct_band(m,4.73,4.87,.08,.08,'bw_belt',True)
        oct_band(m,7.55,8.0,.16,.16,'bw_white',True)
        oct_band(m,8.0,8.28,.30,.30,'bw_white2',True)
        # dentilled white band under the flared cap
        oct_band(m,10.28,10.63,.26,.26,'bw_white',True)
        a=octo(.32)
        for i in range(8):
            j=(i+1)%8;n=3 if i%2 else 2
            for q in range(n):
                f=(q+.5)/n;px=a[i][0]+(a[j][0]-a[i][0])*f;py=a[i][1]+(a[j][1]-a[i][1])*f
                m.box((px,py,10.17),(.22,.22,.18),'bw_white2')
        # drip beam, flared dark copper cone with ribs, brass finial
        d=octo(.45)
        for i in range(8):
            j=(i+1)%8;m.beam((d[i][0],d[i][1],10.55),(d[j][0],d[j][1],10.55),.16,.16,'bw_copper_dark')
        m.poly([(x,y,10.6) for x,y in d][::-1],'bw_copper_dark')
        prof=[(10.6,.45),(10.85,.15),(11.7,-.5),(12.7,-1.2),(13.6,-1.75),(14.6,-2.12)]
        for (za,oa),(zb,ob) in zip(prof[:-1],prof[1:]):oct_band(m,za,zb,oa,ob,'bw_copper')
        for i in range(8):m.beam((d[i][0],d[i][1],10.6),(0,0,14.6),.09,.09,'bw_copper_dark')
        m.beam((0,0,14.45),(0,0,15.35),.08,.08,'metal')
        m.lathe((0,0,15.1),[(-.14,.03),(-.05,.15),(.05,.15),(.14,.03)],'bw_brass',8)
        m.lathe((0,0,15.35),[(0,.05),(.12,.09),(.28,.02)],'bw_brass',8)
        # strong white corner boards on the four exposed corners
        for x,y in ((1.1,-2.15),(2.15,-1.1),(-1.1,-2.15),(2.15,1.1)):
            m.box((x*1.014,y*1.014,4.99),(.22,.22,10.6),'bw_white')
        # lit sash windows on the three exposed flats at all three levels
        for (fx,fy,yaw,w) in ((0,-2.15,0,1.3),(1.626,-1.626,45,1.1),(2.15,0,90,1.3)):
            with m.at((fx,fy,0),yaw):
                sash(m,0,-.02,2.15,w,2.0,True)
                sash(m,0,-.02,6.05,w,2.2,True)
                sash(m,0,-.02,9.25,w-.15,1.55,True)
        # bracketed hanging sign off the diagonal flat
        with m.at((1.66,-1.66,4.6),-45):
            m.beam((0,0,0),(.9,0,0),.06,.06,'metal')
            m.beam((.12,0,-.03),(.85,0,-.62),.04,.04,'metal')
            m.box((.52,0,-.62),(.70,.06,1.0),'wood')
            m.box((.52,0,-.62),(.58,.08,.86),'arc_canvas')
            for s in (-1,1):
                if variant==0:m.box((.52,s*.045,-.62),(.40,.03,.22),'arc_ivory',.07)
                else:
                    m.box((.52,s*.045,-.55),(.24,.03,.24),'arc_rose',.09)
                    m.beam((.52,s*.045,-.92),(.52,s*.045,-.66),.02,.02,'green')
    m.collider((TX,TY,5.0),(4.4,4.4,11.0))


# ---------------------------------------------------------------- storefront

def loaf(m,x,y,z,kind,r):
    if kind==0:
        with m.at((x,y,z),r.uniform(-20,20)):m.box((0,0,.07),(.60,.14,.13),'bw_crust',.05)
    elif kind==1:
        m.lathe((x,y,z),[(0,.16),(.06,.19),(.15,.16),(.20,.07),(.21,0)],'bw_bread',8)
    else:
        for dx in (-.11,.11):m.lathe((x+dx,y,z),[(0,.09),(.05,.10),(.10,.06),(.12,0)],'bw_bun',7)


def bunch(m,x,y,z,seed,n=10):
    r=random.Random(seed)
    for i in range(n):
        a=r.random()*math.tau;rr=r.random()*.11;xx=x+math.cos(a)*rr;yy=y+math.sin(a)*rr;zz=z+r.uniform(.28,.48)
        m.beam((xx,yy,z),(xx,yy,zz),.02,.02,'green_dark')
        c=['arc_ivory','arc_rose','arc_bloom'][(seed+i)%3]
        for j in range(5):
            b=j*math.tau/5
            m.poly([(xx,yy,zz+.02),(xx+math.cos(b-.5)*.11,yy+math.sin(b-.5)*.11,zz),(xx+math.cos(b+.5)*.11,yy+math.sin(b+.5)*.11,zz)],c)
        b=a+1.3
        m.poly([(xx,yy,zz-.14),(xx+math.cos(b)*.13,yy+math.sin(b)*.13,zz-.08),(xx+.04,yy+.03,zz-.02)],'green')


def bucket(m,x,y,z,seed):
    m.lathe((x,y,z),[(0,0),(0,.13),(.30,.16),(.30,0)],'bw_bucket',8)
    bunch(m,x,y,z+.28,seed)


def storefront(m,variant):
    y=-D/2;x0,x1=-9.6,-1.4;cx=(x0+x1)/2;w=x1-x0
    # recess plinth, header and the glowing back panel 0.6 m behind the frame
    m.box((cx,y+.5,.275),(w,1.0,1.35),'wood_light')
    for k in range(15):m.box((x0+.3+k*.51,y-.04,.35),(.08,.06,1.0),'wood')
    m.box((cx,y+.5,3.70),(w,1.0,.6),'wood_light')
    m.box((cx,y+.6,2.175),(w-.02,.06,2.45),'bw_glow')
    for xx in (x0+.12,x1-.12):m.box((xx,y-.06,2.2),(.24,.14,2.7),'wood')
    m.box((cx,y-.06,3.70),(w,.14,.66),'wood');m.box((cx,y-.06,.98),(w,.14,.16),'wood')
    for xx in (-6.9,-4.1):m.box((xx,y-.02,2.2),(.12,.12,2.4),'wood')
    for xx in (-8.2,-5.5,-2.8):m.box((xx,y+.35,3.36),(.9,.25,.06),'paper')   # ceiling lamps
    r=random.Random(11+variant)
    for tier,zt in enumerate((1.12,1.92,2.72)):
        m.box((cx,y+.33,zt-.035),(w-.4,.55,.07),'wood_light')
        for k in range(9):
            xx=x0+.55+k*.81+r.uniform(-.05,.05);yy=y+.35+r.uniform(-.10,.10)
            if variant==0:loaf(m,xx,yy,zt,(tier+k)%3 if tier else 2,r)
            else:bucket(m,xx,yy,zt,tier*10+k)
    # plump striped canvas awning, 1.4 m deep, scalloped valance, shaded underside, tie rods
    ax0,ax1=x0-.44,x1+.44;n=17;sw=(ax1-ax0)/n;za,zb=3.65,3.05;depth=1.4
    for k in range(n):
        xa=ax0+k*sw;xb=xa+sw;key='bw_stripe' if k%2==0 else 'arc_canvas'
        p=[(xa,y-.02,za),(xb,y-.02,za),(xb,y-depth,zb),(xa,y-depth,zb)]
        m.poly(p[::-1],key);m.poly([(a,b,c-.12) for a,b,c in p],'bw_white2')
        m.box(((xa+xb)/2,y-depth,zb-.16+(.04 if k%2 else 0)),(sw,.05,.32-(.08 if k%2 else 0)),key)
    for xa in (ax0,ax1):
        e=[(xa,y-.02,za),(xa,y-depth,zb),(xa,y-depth,zb-.12),(xa,y-.02,za-.12)]
        m.poly(e,'bw_stripe');m.poly(e[::-1],'bw_stripe')
    m.beam((ax0,y-depth,zb-.02),(ax1,y-depth,zb-.02),.06,.06,'metal')
    for xx in (ax0+.15,ax0+.55,ax1-.55,ax1-.15):m.beam((xx,y-.05,zb-.75),(xx,y-depth+.06,zb-.06),.05,.05,'metal')
    # cream sign board: one arc_canvas slab proud of the wall, framed by four wood rails
    m.box((-5.5,y-.19,4.19),(5.9,.24,1.10),'bw_white2')
    m.box((-5.5,y-.36,4.19),(5.7,.12,.95),'arc_canvas')
    for dz in (-.535,.535):m.box((-5.5,y-.35,4.19+dz),(6.0,.20,.14),'wood')
    for dx in (-2.92,2.92):m.box((-5.5+dx,y-.35,4.19),(.16,.20,1.24),'wood')
    text=['焼きたてパン','フラワー'][variant]
    return text


def entrance(m,variant,lettering):
    y=-D/2;x=4.5
    # recessed double door with transom
    for s in (-1,1):
        lx=x+s*.53
        m.box((lx,y+.55,1.32),(1.02,.10,2.4),'bw_door')
        for zz in (.75,1.85):m.box((lx,y+.49,zz),(.72,.03,.75),'bw_door',.03)
        m.beam((lx-s*.30,y+.42,1.15),(lx-s*.30,y+.42,1.45),.05,.05,'bw_brass')
    m.box((x,y+.55,2.72),(2.3,.10,.36),'paper')
    m.box((x,y+.55,2.92),(2.4,.12,.10),'bw_white')
    for xx in (x-1.2,x+1.2):m.box((xx,y+.30,1.55),(.12,.60,3.1),'bw_white')
    m.box((x,y+.30,3.05),(2.5,.60,.14),'bw_white')
    # pilasters, entablature and pediment
    for xx in (x-1.45,x+1.45):
        m.box((xx,y-.12,1.95),(.50,.28,3.9),'bw_white')
        m.box((xx,y-.15,3.85),(.62,.34,.16),'bw_white')
        m.box((xx,y-.15,.05),(.62,.34,.16),'bw_white')
    m.box((x,y-.18,4.05),(3.9,.36,.30),'bw_white')
    m.poly([(x-1.9,y-.34,4.22),(x+1.9,y-.34,4.22),(x,y-.34,4.72)],'bw_white2')
    for s in (-1,1):m.beam((x+s*1.95,y-.20,4.20),(x,y-.20,4.75),.17,.36,'bw_white')
    # warm stone step reaching into the recess
    m.box((x,y-.25,-.13),(3.0,1.7,.55),'bw_step',.03)
    m.collider((x,y-.25,-.13),(3.0,1.7,.55))
    m.collider((x,y+.55,1.32),(2.08,.10,2.4))  # closed double door at the back of the recess
    # chalk A-board beside the door: framed face, stacked characters, loaf below
    with m.at((2.05,y-.95,.02),-10):
        for xx in (-.40,.40):m.beam((xx,-.2,0),(xx,.1,1.28),.06,.06,'wood_light')
        m.box((0,-.05,.70),(.80,.06,1.10),'wood_light')
        m.box((0,-.10,.70),(.64,.025,.94),'bw_chalk')
        for xx in (-.36,.36):m.box((xx,-.10,.70),(.08,.04,1.10),'wood_light')
        for zz in (.19,1.21):m.box((0,-.10,zz),(.80,.04,.08),'wood_light')
        ch=['パン','花'][variant]
        if variant==0:
            lettering(m,ch[0],(0,-.13,.84),.9,color='arc_ivory');lettering(m,ch[1],(0,-.13,.50),.9,color='arc_ivory')
            m.box((0,-.13,.32),(.34,.02,.14),'arc_ivory',.05)
        else:
            lettering(m,ch,(0,-.13,.62),1.0,color='arc_ivory')
            m.lathe((0,-.13,.40),[(0,0),(0,.10)],'arc_ivory',6);m.beam((0,-.13,.24),(0,-.13,.36),.015,.015,'arc_ivory')
        m.collider((0,0,.64),(.9,.5,1.28))


# ---------------------------------------------------------------- props

def planter(m,x,y,z,w,d,seed):
    r=random.Random(seed)
    m.box((x,y,z+.24),(w,d,.48),'bw_base',.04)
    m.box((x,y,z+.50),(w+.1,d+.1,.08),'bw_step',.02)
    m.box((x,y,z+.55),(w-.16,d-.16,.03),'soil')
    for j in range(int(w*d*10)):
        xx=x+r.uniform(-w*.4,w*.4);yy=y+r.uniform(-d*.35,d*.35)
        m.lathe((xx,yy,z+.55),[(0,.10),(.14,.20),(.26,.12),(.31,0)],'green_dark' if j%3 else 'green',7)
        if j%2==0:m.lathe((xx,yy,z+.84),[(0,.02),(.03,.10),(.06,.07),(.065,0)],'arc_ivory',7)
    m.collider((x,y,z+.27),(w,d,.55))


def flower_stand(m,x,y):
    for tier,(yy,zt) in enumerate(((y,.62),(y-.62,.30))):
        m.box((x,yy,zt-.04),(5.6,.55,.08),'wood_light')
        for xx in (x-2.6,x+2.6):m.box((xx,yy,zt/2-.2),(.10,.45,zt+.4),'wood')
        for k in range(6):bucket(m,x-2.3+k*.92,yy+.02,zt,40+tier*10+k)
    m.collider((x,y-.31,.45),(5.7,1.2,.95))


# ---------------------------------------------------------------- build

def build(name,variant,lettering):
    palette(variant)
    m=v.Mesh(name)
    # main mass: upper storey full depth; ground floor wall set back 1 m with solid fills between the recesses
    m.box((0,0,(GF+CORNICE)/2),(W,D,CORNICE-GF),'bw_sage_dark')
    m.box((0,.5,(GF-.4)/2),(W,D-1,GF+.4),'bw_sage_dark')
    for xa,xb,ya,yb in ((-11,-9.6,-8,-7),(-1.4,3.3,-8,-7),(3.3,5.7,-7.4,-7),(5.7,11,-8,-7)):
        m.box(((xa+xb)/2,(ya+yb)/2,(GF-.4)/2),(xb-xa,yb-ya,GF+.4),'bw_sage_dark')
    # dark stone base and sage base board instead of a pale plinth
    m.box((0,0,-.15),(W+.44,D+.44,.5),'bw_base')
    # The high baseboard stops at the doorway instead of crossing the low entrance tread.
    for xa,xb,ya,yb in ((-W/2-.16,3.3,-D/2-.16,D/2+.16),
                         (5.7,W/2+.16,-D/2-.16,D/2+.16),
                         (3.3,5.7,-7.4,D/2+.16)):
        m.box(((xa+xb)/2,(ya+yb)/2,.215),(xb-xa,yb-ya,.27),'bw_sage_dark')
    # Preserve the solid building/display bays while opening only the door recess.
    # The old single bounding box filled the rear half of the visible front tread.
    for xa,xb,ya,yb,z0,z1 in ((-W/2,3.3,-D/2,D/2,-.4,CORNICE+.4),
                              (5.7,W/2,-D/2,D/2,-.4,CORNICE+.4),
                              (3.3,5.7,-7.4,D/2,-.4,CORNICE+.4),
                              (3.3,5.7,-D/2,-7.4,2.54,CORNICE+.4)):
        m.collider(((xa+xb)/2,(ya+yb)/2,(z0+z1)/2),(xb-xa,yb-ya,z1-z0))
    # front (street side, -Y)
    with m.at((0,-D/2,0),0):
        boards(m,-10.85,-9.7,-.2,3.95);boards(m,-1.3,2.85,-.2,3.95);boards(m,6.2,7.9,-.2,3.95)
        boards(m,-10.85,7.9,4.05,4.72);boards(m,-10.85,7.9,4.88,CORNICE-.55)
        m.box((-1.5,-.09,4.80),(19.0,.12,.14),'bw_belt')
        m.box((0,-.10,7.70),(W+.3,.32,.45),'bw_white')
        for x in (-8.35,-5.25,1.05,4.15):sash(m,x,-.02,6.05,1.25,2.2,True,shutters=True)
        dentils(m,-10.7,7.6)
    with m.at((W/2,0,0),90):wall_side(m,D,(-1.5,2.0,5.5),(-1.5,2.0,5.5),vent_x=None,pipes=(7.7,))
    with m.at((0,D/2,0),180):wall_side(m,W,(-7.5,-3.0,3.0,7.5),(-7.5,7.5),door_x=0,vent_x=3.6,pipes=(-10.7,10.7))
    with m.at((-W/2,0,0),-90):wall_side(m,D,(-5.5,-2.0,1.5,5.0),(-2.0,1.5,5.0),door_x=-5.5,pipes=(-7.7,))
    # corner boards (the front-right corner is inside the turret)
    for x,y in ((-W/2,-D/2),(-W/2,D/2),(W/2,D/2)):m.box((x,y,3.55),(.42,.42,7.9),'bw_white')
    # deep cornice (1 m projection) with ivory soffit, sealed under the roof drip
    m.box((0,0,CORNICE+.06),(W+2.0,D+2.0,.30),'bw_white')
    m.box((0,0,CORNICE-.10),(W+1.9,D+1.9,.16),'bw_white2')
    m.box((0,0,CORNICE+.26),(W+1.98,D+1.98,.14),'bw_copper_dark')
    mansard(m)
    for x in (-6.8,2.6):dormer(m,x)
    chimney(m)
    turret(m,variant)
    # ground floor shop
    text=storefront(m,variant)
    lettering(m,text,(-5.5,-D/2-.435,3.86),1.7 if variant==0 else 1.8,color='wood_dark')
    entrance(m,variant,lettering)
    # street props inside the sidewalk apron (the city's own planter stands near x=-9, y=-9.5)
    y=-D/2
    if variant==0:
        v.pot(m,-10.6,y-.85,.02,.85,'clay',plant=True)
        v.pot(m,-.55,y-.9,.02,1.15,'clay',plant=True)
        v.pot(m,6.9,y-.85,.02,.8,'clay',plant=True)
        v.bench(m,-7.0,y-1.3,0,1.8)
    else:
        flower_stand(m,-5.5,y-.95)
        v.pot(m,6.9,y-.85,.02,.8,'clay',plant=True)
        v.pot(m,-10.6,y-.85,.02,.7,'bluepot',plant=True)
    planter(m,TX,y-1.75,0,2.0,.6,5+variant)
    plaza.lantern_post(m,10.7,y-2.1,0)
    return m
