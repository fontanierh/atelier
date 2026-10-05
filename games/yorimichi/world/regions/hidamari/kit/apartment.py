"""Three-storey timber apato over a bike shop (variant 0) or a barber (variant 1): shared balconies, side stair, blue tiled gable."""
import math,random
from village import build as v
from hidamari import arcade
from hidamari.kit._lettering import raised_text

ASSETS={'HD_Shop_15':0,'HD_Shop_07':1}

# Footprint: 22 x 16 lot. Main block 19.6 wide (x -8.6..11), 15 deep (y -7.5..7.5); the
# external stair occupies the 2.4 m strip on the left (x -11..-8.6). Front faces -Y.
CX=1.2;W=19.6;D=15.0
XL=CX-W/2;XR=CX+W/2;YF=-D/2;YB=D/2
F2=4.4;F3=7.5;EAVE=10.6;RISE=3.4
BAL=1.3          # balcony projection
ROOF_D=17.8;ROOF_CY=-.7;ROOF_W=W+1.6
H0=3.2           # storefront opening height


def palette(variant):
    arcade.palette()
    v.PALETTE.update({
        'ap_plaster':(.58,.49,.34) if variant==0 else (.55,.49,.38),
        'ap_timber':(.30,.16,.06),'ap_timber_dark':(.17,.085,.03),
        'ap_wood':(.40,.21,.07),'ap_wood_light':(.46,.26,.10),
        'ap_roof':(.085,.088,.094) if variant==0 else (.07,.09,.13),   # grey metal, or a deep blue one (not a town of blue)
        'ap_roof_edge':(.05,.052,.058) if variant==0 else (.045,.056,.085),
        'ap_awning':(.09,.15,.36) if variant==0 else (.06,.17,.19),
        'ap_awning2':(.11,.17,.39) if variant==0 else (.08,.20,.22),
        'ap_sign':(.07,.13,.36) if variant==0 else (.18,.08,.05),
        'ap_display':(.62,.37,.13),'ap_ivory':(.68,.62,.46),'ap_shoji':(.76,.58,.36),'ap_glow':(.90,.60,.26),'ap_text':(.92,.82,.58),
        'ap_concrete':(.33,.31,.27),'ap_concrete2':(.29,.27,.23),'ap_iron':(.06,.065,.07),
        'ap_red':(.50,.07,.03),'ap_white':(.66,.64,.60),'ap_blue':(.08,.13,.36),
        'ap_futon':(.60,.48,.34),'ap_futon2':(.20,.26,.34),'ap_stripe':(.30,.14,.10),
        'ap_cloth_w':(.62,.58,.48),'ap_cloth_b':(.14,.20,.32),'ap_cloth_p':(.55,.30,.30),'ap_cloth_g':(.22,.32,.20),
        'ap_tyre':(.035,.035,.035),'ap_bike_o':(.62,.22,.05),'ap_bike_b':(.10,.16,.40),'ap_bike_g':(.18,.30,.16),
        'ap_metal':(.30,.31,.30),'ap_soffit':(.12,.07,.03),'ap_chalk':(.06,.08,.07),
        'ap_leather':(.20,.07,.04),'ap_mirror':(.50,.56,.60),
    })


# ---------------------------------------------------------------- small helpers
def text(m,lettering,s,pos,size,color='ap_text',layers=(0,-.02,-.04)):
    """Preserve the sign front plane using one outlined/extruded glyph mesh."""
    x,y,z=pos
    raised_text(m,s,(x,y+min(layers),z),size,color,weight=.018,depth=.02)


def post(m,x,y,z0,z1,w=.22,d=.18,key='ap_timber'):
    m.box((x,y,(z0+z1)/2),(w,d,z1-z0),key)


def roof_z(y):
    return EAVE+RISE*(1-abs(y-ROOF_CY)/(ROOF_D/2))


def ring(m,x,y,z,r,t,depth=.03,n=18,key='ap_tyre'):
    """Upright ring in the XZ plane (a wheel or a painted circle): both faces plus the rim."""
    o=[(x+r*math.cos(k*math.tau/n),z+r*math.sin(k*math.tau/n)) for k in range(n)]
    i=[(x+(r-t)*math.cos(k*math.tau/n),z+(r-t)*math.sin(k*math.tau/n)) for k in range(n)]
    for k in range(n):
        a,b=o[k],o[(k+1)%n];c,d=i[k],i[(k+1)%n]
        front=[(a[0],y-depth/2,a[1]),(c[0],y-depth/2,c[1]),(d[0],y-depth/2,d[1]),(b[0],y-depth/2,b[1])]
        m.poly(front,key);m.poly([(px,py+depth,pz) for px,py,pz in front][::-1],key)
        m.poly([(a[0],y-depth/2,a[1]),(b[0],y-depth/2,b[1]),(b[0],y+depth/2,b[1]),(a[0],y+depth/2,a[1])],key)


def bike_frame(m,key):
    """Frame, saddle and bars of a bicycle in the current frame: wheels at x=+-.53, axle height .34."""
    r=.34
    for wx in (-.53,.53):
        ring(m,wx,0,r,r,.055,.06,18,'ap_tyre')
        ring(m,wx,-.031,r,r-.055,.015,.014,18,'ap_metal')
        for k in range(3):
            a=k*math.pi/3
            m.beam((wx+math.cos(a)*(r-.05),0,r+math.sin(a)*(r-.05)),(wx-math.cos(a)*(r-.05),0,r-math.sin(a)*(r-.05)),.012,.012,'ap_metal')
        m.lathe((wx,0,r),[(-.03,.03),(.03,.03)],'ap_metal',8)
    bb=(0,0,.33);seat=(-.16,0,.92);head=(.40,0,.86);fr=(.53,0,r);rr=(-.53,0,r)
    for a,b in [(bb,seat),(bb,head),(seat,head),(bb,rr),(seat,rr),(head,fr)]:m.beam(a,b,.05,.05,key)
    m.beam((.40,-.24,.98),(.40,.24,.98),.025,.025,'ap_metal')
    m.beam(head,(.40,0,.98),.03,.03,'ap_metal')
    m.box((-.18,0,.98),(.26,.13,.06),'ap_leather',.02)
    m.beam((-.16,0,.92),(-.18,0,.96),.03,.03,'ap_metal')
    m.lathe((0,.05,.33),[(-.02,.09),(.02,.09)],'ap_metal',10)
    m.beam((0,.07,.33),(.12,.07,.19),.02,.02,'ap_metal');m.box((.13,.11,.19),(.07,.08,.02),'ap_metal')
    m.beam((0,.06,.33),(-.12,.06,.47),.02,.02,'ap_metal');m.box((-.13,.10,.47),(.07,.08,.02),'ap_metal')


def bicycle(m,x,y,z,yaw,key,seed=0):
    """Parked bicycle, length 1.75 along local X, wheels resting on z."""
    with m.at((x,y,z),yaw):
        bike_frame(m,key)
        m.beam((-.53,.03,.33),(-.53,.03,.0),.02,.02,'ap_metal')
        if seed%2:m.box((-.53,0,.60),(.55,.06,.06),'ap_metal')
        else:m.box((-.62,0,.60),(.30,.14,.03),'ap_metal')
        m.collider((0,0,.5),(1.75,.5,1.0))


def shoji(m,x,y,z,w,h,key='ap_glow'):
    """Sliding paper window on a wall face at y (facing -Y)."""
    m.box((x,y-.08,z),(w+.2,.14,h+.2),'ap_timber_dark')
    m.box((x,y-.16,z),(w,.03,h),key)
    for k in range(1,4):m.box((x-w/2+w*k/4,y-.19,z),(.045,.035,h),'ap_timber_dark')
    for k in range(1,3):m.box((x,y-.19,z-h/2+h*k/3),(w,.035,.045),'ap_timber_dark')
    m.box((x,y-.20,z-h/2-.09),(w+.36,.26,.09),'ap_timber')


def unit_door(m,x,y,z,w=.9,h=2.05):
    """Apartment door with a lit shoji upper panel, on a wall face at y."""
    m.box((x,y-.07,z+h/2),(w+.18,.12,h+.14),'ap_timber_dark')
    m.box((x,y-.14,z+h/2),(w,.03,h),'ap_wood_light')
    m.box((x,y-.16,z+h*.70),(w-.16,.03,h*.42),'ap_glow')
    m.box((x,y-.18,z+h*.70),(.035,.03,h*.42),'ap_timber_dark');m.box((x,y-.18,z+h*.70),(w-.16,.03,.035),'ap_timber_dark')
    m.box((x+w*.32,y-.18,z+1.0),(.05,.05,.20),'metal')


def small_window(m,x,y,z,s=.75):
    m.box((x,y-.07,z),(s+.16,.12,s+.16),'ap_timber_dark')
    m.box((x,y-.14,z),(s,.03,s),'ap_glow')
    m.box((x,y-.16,z),(.04,.03,s),'ap_timber_dark');m.box((x,y-.16,z),(s,.03,.04),'ap_timber_dark')
    m.box((x,y-.16,z-s/2-.07),(s+.3,.22,.08),'ap_timber')


def ac_unit(m,x,y,z,yaw=0):
    """Outdoor air-conditioner unit standing on a slab, back towards local +Y."""
    with m.at((x,y,z),yaw):
        m.box((0,-.16,.30),(.78,.30,.56),'ap_metal',.02)
        for k in range(5):m.box((0,-.32,.13+k*.09),(.60,.02,.035),'ap_iron')
        m.lathe((.0,-.325,.30),[(-.01,.20),(.01,.20)],'ap_iron',12)
        m.box((.28,-.16,.02),(.06,.30,.04),'ap_iron');m.box((-.28,-.16,.02),(.06,.30,.04),'ap_iron')


def wall_ac(m,x,y,z):
    """Wall-hung unit on a bracket, wall face at y (facing -Y)."""
    m.box((x,y-.20,z+.28),(.80,.32,.56),'ap_metal',.02)
    for k in range(5):m.box((x,y-.37,z+.10+k*.09),(.62,.02,.035),'ap_iron')
    for dx in (-.3,.3):
        m.beam((x+dx,y-.01,z-.03),(x+dx,y-.38,z-.03),.05,.05,'ap_iron');m.beam((x+dx,y-.01,z-.40),(x+dx,y-.38,z-.03),.04,.04,'ap_iron')


def square_lantern(m,x,y,z,size=.34):
    """Hanging square paper lantern; z is the hanger point on the ceiling above."""
    m.beam((x,y,z),(x,y,z-.45),.03,.03,'ap_iron')
    top=z-.45
    m.box((x,y,top-.04),(size+.08,size+.08,.06),'ap_timber_dark')
    m.box((x,y,top-.04-size*.62),(size,size,size*1.16),'paper')
    for dx in (-1,1):
        for dy in (-1,1):m.box((x+dx*size/2,y+dy*size/2,top-.04-size*.62),(.035,.035,size*1.2),'ap_timber_dark')
    m.box((x,y,top-.08-size*1.2),(size+.08,size+.08,.06),'ap_timber_dark')


def pent(m,x,y,z,w,proj,key='ap_roof'):
    """Small tiled pent roof against a wall face at y, projecting towards -Y."""
    top=[(x-w/2,y+.02,z+.05),(x+w/2,y+.02,z+.05),(x+w/2,y-proj,z-.45),(x-w/2,y-proj,z-.45)]
    m.poly(top,key);m.poly([(px,py,pz-.12) for px,py,pz in top][::-1],'ap_soffit')
    for s in (-1,1):
        side=[(x+s*w/2,y+.02,z+.05),(x+s*w/2,y-proj,z-.45),(x+s*w/2,y-proj,z-.57),(x+s*w/2,y+.02,z-.07)]
        m.poly(side if s>0 else side[::-1],'ap_roof_edge')
    m.beam((x-w/2,y-proj,z-.48),(x+w/2,y-proj,z-.48),.16,.16,'ap_roof_edge')
    n=max(3,int(w/.5))
    for k in range(n+1):
        xx=x-w/2+w*k/n
        m.beam((xx,y,z+.09),(xx,y-proj,z-.41),.055,.05,'ap_roof_edge')
    for k in range(1,3):
        t=k/3;m.beam((x-w/2,y-proj*t,z+.09-.5*t),(x+w/2,y-proj*t,z+.09-.5*t),.05,.05,'ap_roof_edge')
    for xx in (x-w/2+.3,x+w/2-.3):
        m.beam((xx,y-.01,z-1.2),(xx,y-proj+.1,z-.55),.09,.09,'ap_timber')
        m.beam((xx,y-.01,z-1.25),(xx,y-.01,z-.30),.10,.10,'ap_timber')


def gable_roof(m):
    """Shallow blue-grey tiled gable, ridge along X, closed soffit; gable walls are built by the caller."""
    cx,cy,w,d,z,rise=CX,ROOF_CY,ROOF_W,ROOF_D,EAVE,RISE
    m.box((cx,cy,z-.08),(w,d,.16),'ap_soffit')
    for s in (-1,1):
        pts=[(cx-w/2,cy,z+rise),(cx+w/2,cy,z+rise),(cx+w/2,cy+s*d/2,z),(cx-w/2,cy+s*d/2,z)]
        m.poly(pts[::-1] if s<0 else pts,'ap_roof')
        under=[(px,py,pz-.03) for px,py,pz in pts]
        m.poly(under if s<0 else under[::-1],'ap_soffit')
        m.box((cx,cy+s*(d/2-.06),z-.10),(w+.02,.14,.46),'ap_roof_edge')
        m.beam((cx-w/2,cy+s*d/2,z+.04),(cx+w/2,cy+s*d/2,z+.04),.18,.18,'ap_roof_edge')
        rows=10
        for i in range(1,rows):
            y=cy+s*d/2*i/rows;zz=z+rise*(1-i/rows)
            m.beam((cx-w/2,y,zz-.005),(cx+w/2,y,zz-.005),.06,.05,'ap_roof_edge')
        cols=int(w/.55)
        for i in range(cols+1):
            xx=cx-w/2+w*i/cols
            m.beam((xx,cy,z+rise-.002),(xx,cy+s*d/2,z-.002),.04,.035,'ap_roof_edge')
        for xx in (cx-w/2,cx+w/2):
            m.beam((xx,cy,z+rise+.03),(xx,cy+s*d/2,z+.03),.20,.28,'ap_roof_edge')
    m.box((cx,cy,z+rise+.10),(w+.1,.32,.26),'ap_roof_edge',.04)
    for xx in (cx-w/2,cx+w/2):m.box((xx,cy,z+rise+.18),(.3,.4,.4),'ap_roof_edge',.05)


# ---------------------------------------------------------------- facade dressings
def balcony(m,F,ceiling):
    """Shared balcony across the full front at floor level F; `ceiling` is the soffit above it."""
    x0=XL-.2;x1=XR+.2;w=x1-x0;xc=(x0+x1)/2;yo=YF-BAL
    m.box((xc,YF-BAL/2+.01,F-.12),(w,BAL+.02,.24),'ap_wood')
    m.collider((xc,YF-BAL/2,F-.12),(w,BAL,.24))
    m.beam((x0,yo+.08,F-.30),(x1,yo+.08,F-.30),.16,.20,'ap_timber')
    n=int(w/1.15)
    for k in range(n+1):
        xx=x0+.1+(w-.2)*k/n
        m.beam((xx,YF-.02,F-.36),(xx,yo+.05,F-.36),.14,.22,'ap_timber')
    # Railing: bottom and top rail, thick posts every sixth baluster.
    yy=yo+.08
    m.box((xc,yy,F+.09),(w,.09,.07),'ap_timber')
    m.box((xc,yy,F+1.06),(w,.13,.10),'ap_wood_light')
    m.box((xc,yy,F+.55),(w,.06,.05),'ap_timber_dark')
    nb=int(w/.40)
    for k in range(nb+1):
        xx=x0+.07+(w-.14)*k/nb;big=k%6==0
        m.box((xx,yy,F+.56),((.13 if big else .06),(.13 if big else .06),.94),'ap_timber' if big else 'ap_timber_dark')
    for xx in (x0,x1):
        m.box((xx,YF-BAL/2,F+1.06),(.10,BAL,.10),'ap_wood_light')
        m.box((xx,YF-BAL/2,F+.09),(.07,BAL-.1,.07),'ap_timber')
        for k in range(3):m.box((xx,YF-.25-k*.4,F+.56),(.06,.06,.94),'ap_timber_dark')
    # Units behind: a shoji window and a door per bay, wall posts between bays, lanterns above.
    bays=[XL+W*(k+.5)/4 for k in range(4)]
    for bx in bays:
        shoji(m,bx-1.05,YF,F+1.55,2.1,1.55)
        unit_door(m,bx+1.35,YF,F+.02)
    for bx in (bays[0]+2.45,bays[2]+2.45):square_lantern(m,bx,YF-.55,ceiling)


def storefront(m,variant,lettering):
    """Two open display recesses (1.2 m deep, lit back walls), a glazed double door, awning and signs."""
    y0=YF;y1=YF+1.2;yc=(y0+y1)/2
    piers=[(XL,XL+1.2),(1.5,1.9),(3.9,4.6),(10.4,XR)]
    displays=[(XL+1.2,1.5),(4.6,10.4)];door=(1.9,3.9)
    for xa,xb in piers:
        m.box(((xa+xb)/2,yc,(F2-.4)/2),(xb-xa,1.2,F2+.4),'ap_wood')
        k=1
        while xa+.15+k*.3<xb-.1:
            m.box((xa+.15+k*.3,YF-.005,(F2-.4)/2),(.03,.03,F2+.4),'ap_timber_dark');k+=1
    for xa,xb in [(XL+1.2,3.9),(4.6,10.4)]:m.box(((xa+xb)/2,yc,(H0+F2)/2),(xb-xa,1.2,F2-H0),'ap_wood')
    for xa,xb in displays+[door]:
        m.box(((xa+xb)/2,yc,-.02),(xb-xa,1.2,.76),'ap_concrete')
        m.box(((xa+xb)/2,yc,H0-.05),(xb-xa-.02,1.18,.05),'ap_wood_light')
    for xa,xb in displays:
        m.box(((xa+xb)/2,y1-.03,.36+(H0-.42)/2),(xb-xa-.04,.04,H0-.42),'ap_display')
    for xa,xb in displays:
        arcade.lantern(m,(xa+xb)/2,YF+.55,H0-.38,.18)
    # Split the 36 cm display plinth into two comfortable entrance risers.
    m.box((2.9,YF-.39,.065),(2.2,.82,.23),'ap_concrete')
    m.collider((2.9,YF-.39,.09),(2.2,.82,.18))
    # Recessed glazed double door.
    dx0=(door[0]+door[1])/2;dy=y1-.35
    m.box((dx0,dy,.35+1.35),(2.0,.12,2.7),'ap_timber_dark')
    for s in (-.47,.47):
        m.box((dx0+s,dy-.07,.35+1.45),(.86,.03,2.35),'ap_glow')
        m.box((dx0+s,dy-.09,.35+.9),(.86,.03,.05),'ap_timber_dark')
        m.box((dx0+s*.36,dy-.13,1.35),(.05,.05,.32),'metal')
    m.box((dx0,dy-.09,.35+1.35),(.06,.03,2.6),'ap_timber_dark')
    # Timber frame of the ground floor front and mullions across the open displays.
    for xa,xb in piers:post(m,(xa+xb)/2,YF-.10,-.4,F2-.2,.22,.20)
    m.box((CX,YF-.10,H0+.05),(W,.20,.16),'ap_timber')
    m.box((CX,YF-.12,.30),(W,.24,.14),'ap_timber')
    m.box((CX,YF-.10,F2-.30),(W,.20,.22),'ap_timber')
    for xx in (-5.2,-3.0,-.8,7.5):m.box((xx,YF-.04,(H0+.36)/2),(.10,.08,H0-.36),'ap_timber_dark')
    # Keep the display bays and side walls solid, but expose the recessed door landing.
    for xa,xb in ((XL,door[0]),(door[1],XR)):
        m.collider(((xa+xb)/2,yc,(F2-.4)/2),(xb-xa,1.25,F2+.4))
    m.collider((dx0,yc,(H0+F2)/2),(2.0,1.25,F2-H0))
    m.collider((dx0,yc,-.02),(2.0,1.2,.76))  # walkable 36 cm landing
    m.collider((dx0,dy,.35+1.35),(2.0,.12,2.7))  # closed door itself remains solid
    # Corrugated awning over the left display and the door.
    ax0=XL+1.0;ax1=4.3;z0=3.22;z1=2.86;ya=YF-.12;yb=YF-1.75
    n=int((ax1-ax0)/.42)
    for k in range(n):
        xa=ax0+(ax1-ax0)*k/n;xb=ax0+(ax1-ax0)*(k+1)/n
        key='ap_awning' if k%2 else 'ap_awning2'
        p=[(xa,ya,z0),(xb,ya,z0),(xb,yb,z1),(xa,yb,z1)]
        m.poly(p,key);m.poly([(px,py,pz-.03) for px,py,pz in p][::-1],'ap_awning')
        m.beam((xa,ya,z0+.02),(xa,yb,z1+.02),.05,.035,'ap_awning2')
        m.box(((xa+xb)/2,yb-.01,z1-.14),((ax1-ax0)/n-.03,.04,.16),key)
    m.beam((ax0,yb,z1-.02),(ax1,yb,z1-.02),.10,.12,'ap_awning')
    for xx in (ax0+.3,ax1-.3):m.beam((xx,YF-.12,z0-.9),(xx,yb+.15,z1-.05),.06,.06,'ap_iron')
    # Sign board above the awning.
    m.box((-2.5,YF-.17,3.76),(6.55,.10,.95),'ap_timber_dark')
    m.box((-2.5,YF-.17,3.76),(6.4,.18,.85),'ap_sign',.03)
    if variant==0:
        text(m,lettering,'自転車',(-1.0,YF-.28,3.46),2.5)
        ring(m,-4.55,YF-.27,3.62,.26,.035,.02,16,'ap_ivory');ring(m,-3.75,YF-.27,3.62,.26,.035,.02,16,'ap_ivory')
        for a,b in [((-4.55,3.62),(-4.15,3.98)),((-4.15,3.98),(-3.75,3.62)),((-4.55,3.62),(-4.05,3.62)),((-4.05,3.62),(-4.15,3.98)),((-4.15,3.98),(-4.3,4.02)),((-3.75,3.62),(-3.9,4.02))]:
            m.beam((a[0],YF-.27,a[1]),(b[0],YF-.27,b[1]),.03,.02,'ap_ivory')
    else:
        text(m,lettering,'床屋',(-1.5,YF-.28,3.46),2.6)
        for a,b in [((-4.5,3.45),(-3.8,4.05)),((-3.8,3.45),(-4.5,4.05))]:m.beam((a[0],YF-.27,a[1]),(b[0],YF-.27,b[1]),.05,.02,'ap_ivory')
        ring(m,-4.62,YF-.27,3.38,.12,.03,.02,12,'ap_ivory');ring(m,-3.68,YF-.27,3.38,.12,.03,.02,12,'ap_ivory')
    # Vertical hanging sign at the right corner, lettered on both faces.
    sx,sy=XR+.62,YF-BAL-.15
    m.beam((XR+.2,YF-BAL+.06,7.95),(sx,sy,7.95),.06,.06,'ap_iron')
    m.box((sx,sy,6.6),(.70,.08,2.6),'ap_timber_dark')
    m.box((sx,sy,6.6),(.62,.14,2.5),'ap_sign',.02)
    chars=['自','転','車'] if variant==0 else ['床','屋'];z0=7.25 if variant==0 else 6.95
    for j,ch in enumerate(chars):text(m,lettering,ch,(sx,sy-.08,z0-j*.66),1.5)
    with m.at((sx,sy,0),180):
        for j,ch in enumerate(chars):text(m,lettering,ch,(0,-.08,z0-j*.66),1.5)


def display_contents(m,variant):
    """Objects inside the two lit recesses, kept behind the front frame line."""
    if variant==0:
        bicycle(m,-5.4,YF+.62,.35,-6,'ap_bike_o',1)
        bicycle(m,-3.0,YF+.62,.35,4,'ap_bike_b',2)
        with m.at((-.6,YF+.55,1.55),0):
            bike_frame(m,'ap_bike_g')
            for wx in (-.53,.53):m.beam((wx,0,.36),(wx,0,1.62),.02,.02,'ap_iron')
        for x,z in ((.9,2.35),(1.0,1.4),(8.0,2.3)):ring(m,x,YF+1.09,z,.30,.05,.06,16,'ap_tyre')
        bicycle(m,6.4,YF+.60,.35,8,'ap_bike_b',3)
        for k in range(3):m.box((8.6+(k%2)*.1,YF+.85,.36+.22+k*.44),(.7,.5,.42),['clay','cream','ap_cloth_b'][k],.03)
        m.box((9.6,YF+.75,1.9),(1.2,.45,.06),'ap_wood_light');m.beam((9.6,YF+1.12,1.9),(9.6,YF+.55,1.9),.05,.05,'ap_iron')
        for k in range(3):m.lathe((9.15+k*.42,YF+.75,1.93),[(0,.10),(.06,.15),(.14,.13),(.17,.0)],['ap_red','ap_white','ap_bike_g'][k],10)
    else:
        for xx in (-5.4,-2.6,5.6,8.2):
            m.lathe((xx,YF+.7,.36),[(0,.28),(.08,.28),(.12,.08),(.45,.08),(.5,.0)],'ap_iron',10)
            m.box((xx,YF+.7,.36+.62),(.62,.62,.16),'ap_leather',.04)
            m.box((xx,YF+.95,.36+1.05),(.62,.14,.70),'ap_leather',.04)
            for dx in (-.34,.34):m.box((xx+dx,YF+.66,.36+.85),(.06,.5,.05),'ap_metal')
            m.box((xx,YF+.95,.36+.20),(.40,.30,.05),'ap_metal')
            m.box((xx,YF+1.10,1.9),(1.1,.04,1.3),'ap_timber_dark');m.box((xx,YF+1.06,1.9),(1.0,.04,1.2),'ap_mirror')
        m.box((-.4,YF+.95,.36+.5),(1.2,.45,1.0),'ap_wood',.02)
        for k in range(4):m.lathe((-.85+k*.3,YF+.9,1.36),[(0,.05),(.14,.05),(.18,.02),(.24,.02)],['ap_blue','ap_white','ap_red','ap_cloth_g'][k],8)
        m.beam((9.7,YF+.7,.36),(9.7,YF+.7,2.1),.05,.05,'ap_iron');m.lathe((9.7,YF+.7,.36),[(0,.25),(.05,.25),(.07,.05)],'ap_iron',10)
        m.box((9.7,YF+.7,1.9),(.55,.35,.35),'ap_cloth_b',.05)
        # Striped barber pole on the pier beside the door.
        px=4.25;py=YF-.42
        m.beam((px,YF-.02,2.55),(px,py,2.55),.05,.05,'ap_iron');m.beam((px,YF-.02,1.45),(px,py,1.45),.05,.05,'ap_iron')
        m.lathe((px,py,1.35),[(0,.10),(.08,.14),(.12,.12)],'ap_iron',12)
        for k in range(8):m.lathe((px,py,1.47+k*.13),[(0,.10),(.13,.10)],['ap_red','ap_white','ap_blue','ap_white'][k%4],12)
        m.lathe((px,py,2.51),[(0,.12),(.08,.14),(.14,.10),(.18,0)],'ap_iron',12)


def side_stair(m):
    """Concrete external stair in the left strip, two flights to the first-floor side door, iron railing."""
    x0=-11.0;x1=XL-.02;xc=(x0+x1)/2;wd=x1-x0
    rise=F2/24;run=.28
    steps=[];y=-7.4
    for i in range(12):
        steps.append((y+run/2,(i+1)*rise));y+=run
    l1=(y,y+1.4);y+=1.4
    for i in range(12):
        steps.append((y+run/2,(12+i+1)*rise));y+=run
    l2=(y,y+1.9)
    for k,(yy,top) in enumerate(steps):
        m.box((xc,yy,(top-.4)/2),(wd,run,top+.4),'ap_concrete' if k%2 else 'ap_concrete2')
        m.collider((xc,yy,(top-.4)/2),(wd,run,top+.4))
    for (ya,yb),top in ((l1,12*rise),(l2,F2)):
        m.box((xc,(ya+yb)/2,(top-.4)/2),(wd,yb-ya,top+.4),'ap_concrete')
        m.collider((xc,(ya+yb)/2,(top-.4)/2),(wd,yb-ya,top+.4))
    # Iron handrail along the outer edge, then across the back of the top landing.
    xr=x0+.10
    pts=[(-7.4,0),(steps[11][0]+run/2,12*rise),(l1[1],12*rise),(l2[0],F2),(l2[1],F2)]
    for a,b in zip(pts[:-1],pts[1:]):
        m.beam((xr,a[0],a[1]+.95),(xr,b[0],b[1]+.95),.05,.05,'ap_iron')
        m.beam((xr,a[0],a[1]+.50),(xr,b[0],b[1]+.50),.03,.03,'ap_iron')
    for yy,top in [(-7.3,0),(-5.7,6*rise),(steps[11][0]+.1,12*rise),(l1[1]-.1,12*rise),(l1[1]+1.7,18*rise),(l2[0]+.1,F2),(l2[1]-.1,F2)]:
        m.beam((xr,yy,top),(xr,yy,top+.98),.05,.05,'ap_iron')
    m.beam((xr,l2[1]-.05,F2+.95),(x1,l2[1]-.05,F2+.95),.05,.05,'ap_iron');m.beam((xr,l2[1]-.05,F2+.5),(x1,l2[1]-.05,F2+.5),.03,.03,'ap_iron')
    return (l2[0]+l2[1])/2


def side_walls(m,door_y):
    """Left (stair) and right (plain) walls: timber posts, rails, braces, small windows, pipes, AC."""
    for yaw,left in ((-90,True),(90,False)):
        with m.at((CX,0,0),yaw):
            yy=-W/2
            for x in (-D/2+.12,-3.75,0,3.75,D/2-.12):post(m,x,yy-.10,-.4,EAVE-.2,.20,.20)
            for z in (F2-.15,F3-.15,EAVE-.35):m.box((0,yy-.10,z),(D,.20,.22),'ap_timber')
            m.box((0,yy-.12,.30),(D,.24,.14),'ap_timber')
            m.box((0,yy-.05,(F2-.5)/2),(D-.24,.06,F2-.5),'ap_wood')
            for xa,xb,z0,z1 in ((0,3.75,F2,F3-.4),(-3.75,0,F3,EAVE-.6),(3.75,D/2-.12,F3,EAVE-.6)):
                m.beam((xa,yy-.10,z0),(xb,yy-.10,z1),.14,.12,'ap_timber')
            for x in (-4.5,4.5):
                for F in (F2,F3):small_window(m,x,yy,F+1.7,.8)
            m.beam((-D/2+.5,yy-.28,-.3),(-D/2+.5,yy-.28,EAVE-.5),.09,.09,'ap_iron')
            m.beam((-D/2+.5,yy-.28,EAVE-.5),(-D/2+.5,yy-.05,EAVE-.35),.08,.08,'ap_iron')
            if left:
                # Ground-floor side door behind the stair; landing door under a tiled pent canopy.
                unit_door(m,-4.8,yy,.02,1.0,2.1)
                unit_door(m,-door_y,yy,F2+.02,1.0,2.1)
                pent(m,-door_y,yy,F2+2.55,3.4,1.45)
                square_lantern(m,-door_y+1.3,yy-.5,F2+2.35,.28)
                wall_ac(m,2.3,yy,F3+.5)
            else:
                shoji(m,1.9,yy,1.9,1.6,1.3);shoji(m,-5.2,yy,1.9,1.4,1.2)
                wall_ac(m,-1.6,yy,F2+.5);wall_ac(m,-1.6,yy,F3+.5)


def back_wall(m):
    with m.at((CX,0,0),180):
        yy=-D/2
        for x in (-W/2+.12,-W/4,0,W/4,W/2-.12):post(m,x,yy-.10,-.4,EAVE-.2,.20,.20)
        for z in (F2-.15,F3-.15,EAVE-.35):m.box((0,yy-.10,z),(W,.20,.22),'ap_timber')
        m.box((0,yy-.12,.30),(W,.24,.14),'ap_timber')
        m.box((0,yy-.05,(F2-.5)/2),(W-.24,.06,F2-.5),'ap_wood')
        for F in (F2,F3):
            for x in (-7,-2.4,2.4,7):shoji(m,x,yy,F+1.6,1.7,1.4)
        unit_door(m,0,yy,.02,1.1,2.15)
        pent(m,0,yy,2.75,2.6,.9)
        for x in (-6.8,6.8):shoji(m,x,yy,1.8,1.6,1.3)
        wall_ac(m,4.6,yy,F2+.5);wall_ac(m,-4.6,yy,F3+.5)
        for x in (-W/2+.6,W/2-.6):m.beam((x,yy-.28,-.3),(x,yy-.28,EAVE-.5),.09,.09,'ap_iron')
        m.box((0,yy-.3,-.1),(1.8,.6,.2),'ap_concrete');m.collider((0,yy-.3,-.1),(1.8,.6,.2))
        for k in range(2):m.box((-3.0-k*.9,yy-.45,.18),(.8,.6,.36),'ap_cloth_b' if k else 'clay',.03)


def balcony_props(m,variant,seed):
    # Futons draped over the first-floor railing.
    yo=YF-BAL+.08
    futons=[(-5.6,'ap_futon'),(-4.0,'ap_futon2')] if variant==0 else [(6.2,'ap_futon2'),(7.8,'ap_futon')]
    for x,key in futons:
        m.box((x,yo-.14,F2+.62),(1.2,.10,.95),key,.03)
        m.box((x,yo+.14,F2+.78),(1.2,.09,.60),key,.03)
        m.box((x,yo,F2+1.15),(1.2,.42,.12),key,.05)
        for zz in (F2+.35,F2+.85):m.box((x,yo-.195,zz),(1.2,.012,.07),'ap_stripe')
    for x,key in (((8.6,'ap_cloth_p'),(9.3,'ap_cloth_w')) if variant==0 else ((-1.4,'ap_cloth_w'),(-.7,'ap_cloth_g'))):
        m.box((x,yo-.10,F2+.80),(.45,.07,.60),key,.02);m.box((x,yo+.09,F2+.90),(.45,.06,.40),key,.02);m.box((x,yo,F2+1.13),(.45,.30,.08),key,.03)
    # Laundry pole under the top-floor ceiling with shirts and towels.
    lx0,lx1=(4.2,10.0) if variant==0 else (-8.0,-2.2)
    zc=EAVE-.02;zp=F3+2.15
    for xx in (lx0,lx1):m.beam((xx,YF-.65,zc),(xx,YF-.65,zp),.035,.035,'ap_iron')
    m.beam((lx0-.2,YF-.65,zp),(lx1+.2,YF-.65,zp),.05,.05,'ap_metal')
    items=['ap_cloth_w','ap_cloth_b','ap_cloth_p','ap_cloth_w','ap_cloth_g'];n=5
    for k in range(n):
        xx=lx0+.4+(lx1-lx0-.8)*k/(n-1);key=items[(k+seed)%len(items)]
        if k%2==0:
            m.box((xx,YF-.65,zp-.42),(.50,.04,.70),key,.02)
            m.box((xx,YF-.65,zp-.20),(.86,.04,.22),key,.02)
        else:m.box((xx,YF-.65,zp-.45),(.40,.05,.86),key,.02)
        m.beam((xx-.1,YF-.65,zp-.06),(xx+.1,YF-.65,zp-.06),.04,.04,'ap_iron')
    for x,F in ((-1.1,F2),(6.9,F2),(-7.6,F3),(2.6,F3)):v.pot(m,x,YF-.45,F+.01,.62,'clay',plant=True)
    for x,F in ((XL+1.0,F2),(XL+1.0,F3),(4.7,F3)):ac_unit(m,x,YF-.35,F,180)


def street_props(m,variant,lettering,seed):
    """Props on the sidewalk apron (y down to -10.0), leaving the planter spot near x=-9 free."""
    lx,ly=10.3,-9.55
    m.lathe((lx,ly,-.1),[(0,.24),(.22,.24),(.45,.13),(4.0,.08),(4.15,.16)],'ap_blue',10)
    m.collider((lx,ly,2),(.3,.3,4.1))
    m.box((lx,ly,4.45),(.44,.44,.66),'paper');m.box((lx,ly,4.05),(.50,.50,.06),'ap_blue')
    for dx in (-1,1):
        for dy in (-1,1):m.beam((lx+dx*.2,ly+dy*.2,4.08),(lx+dx*.25,ly+dy*.25,4.80),.04,.04,'ap_blue')
    m.lathe((lx,ly,4.80),[(0,.36),(.08,.36),(.34,.06),(.46,.02)],'ap_blue',4)
    # Red post box left of the shop (clear of the lot planter at x=-9).
    px,py=-7.0,-9.45
    m.lathe((px,py,-.05),[(0,.30),(.15,.30),(.18,.24),(1.10,.24),(1.25,.26),(1.39,.20),(1.45,0)],'ap_red',12)
    m.box((px,py-.235,.85),(.28,.03,.05),'ap_iron');m.box((px,py-.235,.45),(.36,.03,.25),'ap_white')
    m.collider((px,py,.7),(.55,.55,1.4))
    # Planter box with flowers and pots by the display.
    bx=-4.4
    m.box((bx,-9.05,.24),(2.2,.62,.60),'ap_white',.03);m.box((bx,-9.05,.55),(2.1,.52,.03),'soil')
    m.collider((bx,-9.05,.28),(2.2,.62,.52))
    for k in range(3):arcade.flowers(m,bx-.7+k*.7,-9.05,.55,seed*3+k,root_spread=(.29,.20))
    v.pot(m,-2.2,-9.15,-.02,1.0,'clay',plant=True);m.collider((-2.2,-9.15,.4),(.7,.7,.8))
    v.pot(m,-7.9,-8.95,-.02,.8,'bluepot',plant=True,form='urn')
    # Chalkboard A-frame beside the door.
    with m.at((3.4,-9.1,0),-12):
        for x in (-.40,.40):
            m.beam((x,-.22,-.02),(x,.10,1.15),.06,.06,'ap_timber');m.beam((x,.22,-.02),(x,-.10,1.15),.06,.06,'ap_timber')
        m.box((0,-.06,.66),(.78,.06,.86),'ap_timber_dark');m.box((0,-.10,.66),(.66,.02,.70),'ap_chalk')
        m.box((0,.06,.66),(.78,.06,.86),'ap_timber_dark')
        text(m,lettering,'自転車' if variant==0 else '床屋',(0,-.12,.70),.42 if variant==0 else .62,layers=(0,-.015))
        if variant==0:ring(m,-.14,-.12,.48,.09,.02,.01,12,'ap_ivory');ring(m,.14,-.12,.48,.09,.02,.01,12,'ap_ivory')
        else:m.box((0,-.12,.48),(.3,.01,.05),'ap_ivory')
        m.collider((0,0,.55),(.8,.5,1.15))
    if variant==0:
        for k,(x,key,yaw) in enumerate(((5.35,'ap_bike_o',4),(7.25,'ap_bike_b',-3),(9.05,'ap_bike_g',6))):bicycle(m,x,-9.35,-.02,yaw,key,k)
    else:
        bicycle(m,7.9,-9.35,-.02,5,'ap_bike_b',1)
        v.bench(m,5.4,-9.25,-.02,1.9)
        m.lathe((9.6,-9.0,-.02),[(0,.17),(.02,.17),(.32,.20),(.34,0)],'ap_metal',10)
    # Paper lantern hung beside the awning under the left balcony.
    arcade.lantern(m,XL+.6,YF-1.1,2.35,.30)
    m.beam((XL+.6,YF-.05,3.45),(XL+.6,YF-1.1,3.45),.05,.05,'ap_iron')


def roof_extras(m):
    """TV antenna on the back slope and small vents on both closed gables."""
    ax,ay=9.4,-2.6;zb=roof_z(ay)
    m.beam((ax,ay,zb-.4),(ax,ay,zb+2.4),.05,.05,'ap_iron')
    for k in range(4):
        zz=zb+1.2+k*.32;ln=1.0-k*.18
        m.beam((ax-ln/2,ay,zz),(ax+ln/2,ay,zz),.03,.03,'ap_iron')
    m.beam((ax,ay-.8,zb+1.1),(ax,ay+.8,zb+1.1),.03,.03,'ap_iron')
    for x in (XL,XR):
        with m.at((x,ROOF_CY-2.2,EAVE+RISE-1.5),-90 if x<0 else 90):
            m.box((0,-.04,0),(.5,.06,.5),'ap_timber_dark')
            for k in range(3):m.box((0,-.08,-.15+k*.15),(.42,.03,.05),'ap_timber')


def build(name,variant,lettering):
    palette(variant);m=v.Mesh(name);seed=17+variant*5
    # Main body: upper plaster block and the ground-floor rear block with wood cladding.
    m.box((CX,0,(F2+EAVE)/2),(W,D,EAVE-F2),'ap_plaster')
    m.box((CX,.6,(F2-.4)/2),(W,13.8,F2+.4),'ap_wood')
    # Separate the rear mass from the upper storeys so the ground-floor door recess is open.
    m.collider((CX,.6,(F2-.4)/2),(W,13.8,F2+.4))
    m.collider((CX,0,(F2+EAVE)/2),(W,D,EAVE-F2))
    # Closed gable ends following the roof underside, with timber verge posts and a king post.
    for x in (XL,XR):
        s=-1 if x<0 else 1;xx=x+s*.01
        zf=roof_z(YF);zb=roof_z(YB)
        p=[(xx,YF,EAVE-.02),(xx,YB,EAVE-.02),(xx,YB,zb),(xx,ROOF_CY,EAVE+RISE),(xx,YF,zf)]
        m.poly(p[::-1] if x<0 else p,'ap_plaster')
        for yy,zz in ((YF+.15,zf),(YB-.15,zb)):m.box((x+s*.1,yy,(EAVE+zz)/2-.1),(.2,.2,zz-EAVE+.2),'ap_timber')
        m.box((x+s*.1,ROOF_CY,EAVE+RISE/2),(.2,.2,RISE),'ap_timber')
        m.beam((x+s*.1,YF+.15,zf-.1),(x+s*.1,ROOF_CY,EAVE+RISE-.1),.16,.16,'ap_timber')
        m.beam((x+s*.1,YB-.15,zb-.1),(x+s*.1,ROOF_CY,EAVE+RISE-.1),.16,.16,'ap_timber')
    gable_roof(m)
    # Front: storefront, balconies with columns, posts between the upper units.
    storefront(m,variant,lettering)
    display_contents(m,variant)
    balcony(m,F2,F3-.24);balcony(m,F3,EAVE-.16)
    for x,z0 in ((XL-.2,-.4),(XR+.2,-.4),(2.6,F2)):
        post(m,x,YF-BAL+.06,z0,EAVE-.10,.24,.24)
        if z0<0:m.collider((x,YF-BAL+.06,2),(.3,.3,4.8))
    for x in (XL+.1,XL+W/4,CX,XR-W/4,XR-.1):post(m,x,YF-.09,F2+.02,EAVE-.2,.18,.16)
    m.box((CX,YF-.10,EAVE-.35),(W,.18,.22),'ap_timber')
    m.box((CX,YF-.05,(F2-.2+H0)/2),(W,.06,F2-.2-H0),'ap_wood')
    balcony_props(m,variant,seed)
    door_y=side_stair(m)
    side_walls(m,door_y)
    back_wall(m)
    street_props(m,variant,lettering,seed)
    roof_extras(m)
    return m
