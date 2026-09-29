"""Hidamari railway terminus: clock-tower pavilion, arched wings, columned porch, platform canopy (ref_1)."""
import math,random
import numpy as np
from village import build as v
from hidamari import arcade
from hidamari.kit._lettering import raised_text
ASSETS={'HD_Station':0}

W,D=46,18
LET=None   # lettering callback captured by build()

def palette(variant):
    arcade.palette()
    v.PALETTE.update({
        'st_cream':(.62,.50,.27) if variant%2==0 else (.58,.46,.25),
        'st_stone':(.30,.28,.24),'st_stone_light':(.40,.37,.31),'st_stone_dark':(.20,.18,.15),
        'st_floor':(.24,.22,.19),'st_kerb':(.18,.17,.15),
        'st_brown':(.21,.105,.04),'st_brown_dark':(.11,.055,.02),'st_dark':(.065,.042,.028),'st_ink':(.012,.010,.008),
        'st_timber':(.34,.22,.11),
        'st_slate':(.026,.036,.052) if variant%2==0 else (.05,.042,.038),
        'st_seam':(.048,.062,.08) if variant%2==0 else (.085,.072,.065),
        'st_slate_edge':(.02,.028,.04),
        'st_tile':(.018,.025,.036),'st_tile_seam':(.04,.052,.07),
        'st_copper':(.15,.30,.17),'st_copper_seam':(.20,.36,.21),'st_copper_edge':(.10,.20,.11),
        'st_fascia':(.42,.39,.32),'st_white':(.66,.62,.53),'st_board':(.68,.63,.52),'st_red':(.55,.09,.03),
        'st_glass':(.66,.36,.10),'st_tyre':(.05,.05,.05),'st_tactile':(.46,.36,.12),
    })

# ---------------------------------------------------------------- lettering / signs
def text(m,s,pos,size,color='st_ink'):
    """One bold, closed glyph mesh per string; no duplicate reverse faces."""
    raised_text(m,s,pos,size,color,weight=.025,depth=.025)


def board(m,x,y,z,w,h,s,size,frame=.12,depth=.16,face='st_white',dz=None,frame_key='st_brown_dark',gap=0):
    """Framed sign board on a wall face at y (facing -Y): frame proud of a recessed pale face, an optional shadow
    gap under the top rail, bold near-black text .02+ proud of the face."""
    m.box((x,y-(depth-.06)/2,z),(w,depth-.06,h),frame_key)                         # back plate
    m.box((x,y-depth+.07,z),(w-2*frame,.04,h-2*frame),face)                        # face, front at y-depth+.05
    for sz in (-1,1):
        m.box((x,y-depth/2,z+sz*(h/2-frame/2)),(w,depth,frame),frame_key)
        m.box((x+sz*(w/2-frame/2),y-depth/2,z),(frame,depth,h-2*frame),frame_key)
    if gap:m.box((x,y-depth+.055,z+h/2-frame-gap/2),(w-2*frame,.03,gap),'st_ink')  # shadow gap, front y-depth+.04
    if s:text(m,s,(x,y-depth+.01,z-(size*.42 if dz is None else dz)),size)

# ---------------------------------------------------------------- roofs
def hip(m,cx,cy,w,d,z,rise,key,seam,fascia,edge,spacing=1.3,fh=.32):
    """Closed hip roof with a soffit, a deep eave fascia on all four sides and standing seams down every slope."""
    with m.at((cx,cy,0)):
        hw,hd=w/2,d/2;top=z+rise
        rx,ry=((hw-hd),0) if w>=d else (0,(hd-hw))
        m.box((0,0,z-.12),(w-.04,d-.04,.14),fascia)              # soffit: no sky through the eaves
        F=[(-hw,-hd,z),(hw,-hd,z),(rx,-ry,top),(-rx,-ry,top)]
        B=[(hw,hd,z),(-hw,hd,z),(-rx,ry,top),(rx,ry,top)]
        Rt=[(hw,-hd,z),(hw,hd,z),(rx,ry,top),(rx,-ry,top)]
        L=[(-hw,hd,z),(-hw,-hd,z),(-rx,-ry,top),(-rx,ry,top)]
        for p in (F,B,Rt,L):m.poly(p,key)
        # eave fascia boards (outer face flush with the eave line), hips and ridge
        for s in (-1,1):
            m.box((0,s*(hd-.08),z-.08),(w,.16,fh),edge)
            m.box((s*(hw-.08),0,z-.08),(.16,d-.34,fh),edge)
        A=(-rx,-ry,top);Bp=(rx,ry,top)
        for c,r in [((-hw,-hd,z),A),((-hw,hd,z),A),((hw,-hd,z),Bp),((hw,hd,z),Bp)]:
            m.beam(c,r,.13,.12,edge)
        if math.dist(A,Bp)>.05:m.beam(A,Bp,.16,.14,edge)
        # seams: front/back faces run in Y, end faces run in X, ending on the hip lines
        def lift(p):return (p[0],p[1],p[2]+.03)
        for s in (-1,1):
            for x in np.arange(-hw+spacing*.7,hw-spacing*.3,spacing):
                x=float(x)
                if abs(x)<=rx:end=(x,-s*ry,top)
                else:
                    t=(hw-abs(x))/(hw-rx);end=(x,-s*(hd-t*(hd-ry)),z+t*rise)
                m.beam(lift((x,-s*hd,z)),lift(end),.06,.05,seam)
            for y in np.arange(-hd+spacing*.7,hd-spacing*.3,spacing):
                y=float(y)
                if abs(y)<=ry:end=(s*rx,y,top)
                else:
                    t=(hd-abs(y))/(hd-ry);end=(s*(hw-t*(hw-rx)),y,z+t*rise)
                m.beam(lift((s*hw,y,z)),lift(end),.06,.05,seam)

def pent(m,x0,x1,y_wall,y_edge,z_wall,z_edge,key,strip=2.2,seam='st_seam',thick=.28,fascia=.45,lip=.12,soffit=True,
         edge='st_fascia',soffit_key='st_fascia'):
    """Solid standing-seam pent roof: thick sloped slabs, closed soffit, pale fascia with a brown lower lip returned at both ends."""
    n=max(1,round((x1-x0)/strip));sw=(x1-x0)/n;xm=(x0+x1)/2
    for k in range(n):
        x=x0+(k+.5)*sw
        m.beam((x,y_edge,z_edge),(x,y_wall,z_wall),sw,thick,key)
        if k:m.beam((x0+k*sw,y_edge+.05,z_edge+thick/2+.035),(x0+k*sw,y_wall,z_wall+thick/2+.035),.06,.05,seam)
    if soffit:
        dz=thick/2+.05
        m.beam((xm,y_edge+.03,z_edge-dz),(xm,y_wall,z_wall-dz),x1-x0-.02,.06,soffit_key)
    # front fascia (top flush with the slab top) and its lower lip
    ze=z_edge+thick/2;zw=z_wall+thick/2
    m.box((xm,y_edge-.02,ze-fascia/2+.02),(x1-x0+.44,.22,fascia),edge)
    m.box((xm,y_edge-.02,ze-fascia-lip/2+.02),(x1-x0+.44,.20,lip),'st_brown')
    for x in (x0-.11,x1+.11):
        m.beam((x,y_edge-.02,ze-fascia/2+.02),(x,y_wall,zw-fascia/2+.02),.22,fascia,edge)
        m.beam((x,y_edge-.02,ze-fascia-lip/2+.02),(x,y_wall,zw-fascia-lip/2+.02),.20,lip,'st_brown')

# ---------------------------------------------------------------- openings
def half_disc(m,x,y,z,r,key,n=14):
    pts=[(x+r*math.cos(a),y,z+r*math.sin(a)) for a in np.linspace(0,math.pi,n)]
    m.poly(pts,key);return pts

def arch_band(m,x,y,z,r0,r1,key,n=14,full=False):
    angles=np.linspace(0,math.tau if full else math.pi,n)
    for a0,a1 in zip(angles[:-1],angles[1:]):
        m.poly([(x+r0*math.cos(a0),y,z+r0*math.sin(a0)),(x+r1*math.cos(a0),y,z+r1*math.sin(a0)),
                (x+r1*math.cos(a1),y,z+r1*math.sin(a1)),(x+r0*math.cos(a1),y,z+r0*math.sin(a1))],key)

def arch_rim(m,x,y0,y1,z,r,key,n=14,both=False):
    angles=np.linspace(0,math.pi,n)
    for a0,a1 in zip(angles[:-1],angles[1:]):
        p0=(x+r*math.cos(a0),y0,z+r*math.sin(a0));p1=(x+r*math.cos(a1),y0,z+r*math.sin(a1))
        p2=(x+r*math.cos(a1),y1,z+r*math.sin(a1));p3=(x+r*math.cos(a0),y1,z+r*math.sin(a0))
        m.poly([p0,p1,p2,p3],key)
        if both:m.poly([p3,p2,p1,p0],key)

def arch_window(m,x,y,z0,w,h,glow='st_glass',sill=True):
    """Tall round-arched amber window: dark-brown jambs, arch band and mullions, glass recessed .12 behind the rim, stone sill and keystone."""
    r=w/2;f=.13;dp=.20;FR='st_brown_dark'
    for s in (-1,1):m.box((x+s*(r+f/2),y-dp/2,z0+h/2),(f,dp,h),FR)                # jambs
    arch_band(m,x,y-dp,z0+h,r,r+f,FR)                                            # arch head band
    arch_rim(m,x,y-dp,y-.04,z0+h,r,FR,both=True)                                 # arch reveal
    for s in (-1,1):                                                             # jamb reveals
        m.box((x+s*(r-.02),y-.12,z0+h/2),(.04,.16,h),FR)
    m.box((x,y-.06,z0+h/2),(w,.06,h),glow)                                       # glass, front at y-.09
    half_disc(m,x,y-.09,z0+h,r,glow)
    for dx in (-w/6,w/6):
        hh=h+r*.94;m.box((x+dx,y-.115,z0+hh/2),(.10,.07,hh),FR)
    for zz in (z0+h/3,z0+2*h/3,z0+h):m.box((x,y-.115,zz),(w,.07,.10),FR)
    m.box((x,y-.15,z0+h+r+.1),(.25,.30,.35),'st_stone_light')                    # keystone
    if sill:m.box((x,y-.16,z0-.07),(w+.3,.32,.14),'st_stone_light')              # projecting sill

def sq_window(m,x,y,z,w,h,glow='st_glass'):
    m.box((x,y-.07,z),(w+.22,.14,h+.22),'st_brown_dark')
    m.box((x,y-.17,z),(w,.06,h),glow)
    m.box((x,y-.225,z),(.10,.05,h),'st_brown_dark');m.box((x,y-.225,z),(w,.05,.10),'st_brown_dark')
    m.box((x,y-.16,z-h/2-.16),(w+.4,.32,.12),'st_stone_light')

def vent(m,x,y,z):
    m.box((x,y-.06,z),(.7,.12,.5),'st_brown')
    for k in range(4):m.box((x,y-.14,z-.18+k*.12),(.56,.04,.05),'st_dark')

def downpipe(m,x,y,z_top):
    m.beam((x,y,-.3),(x,y,z_top-.35),.08,.08,'metal')
    m.beam((x,y,z_top-.35),(x,y+.5,z_top-.05),.08,.08,'metal')
    for zz in (.6,z_top-1.2):m.box((x,y+.08,zz),(.16,.16,.12),'metal')

def double_door(m,x,y,w=2.6,h=2.55,fan=1.3,glass='arc_shopglass'):
    """Arched double entrance door with a lit fanlight; wall face at y."""
    m.box((x,y-.08,h/2-.1),(w+.4,.16,h+.2),'st_brown')
    half_disc(m,x,y-.16,h,fan+.2,'st_brown');arch_rim(m,x,y,y-.16,h,fan+.2,'st_brown')
    half_disc(m,x,y-.20,h,fan,'st_glass')
    for a in (math.pi*.25,math.pi*.5,math.pi*.75):
        m.beam((x,y-.23,h),(x+fan*math.cos(a),y-.23,h+fan*math.sin(a)),.05,.05,'st_brown')
    m.beam((x-fan-.1,y-.23,h),(x+fan+.1,y-.23,h),.08,.06,'st_brown')
    for s in (-1,1):
        cx=x+s*w/4
        m.box((cx,y-.14,h/2-.1),(w/2-.06,.08,h),'st_brown_dark')
        m.box((cx,y-.19,h*.66),(w/2-.34,.03,h*.5),glass)
        m.box((cx,y-.20,h*.66),(.04,.04,h*.5),'st_brown_dark');m.box((cx,y-.20,h*.66),(w/2-.34,.04,.04),'st_brown_dark')
        m.box((cx,y-.19,h*.2),(w/2-.34,.03,h*.24),'st_brown')
        m.box((cx-s*.12,y-.24,h*.45),(.05,.06,.3),'metal')
    m.box((x,y-.35,-.05),(w+.6,.9,.14),'st_stone_light')

def column(m,x,y,h):
    """Round timber column on a small pale stone base with a chamfered cap and a capital block (shaft from .50 to h)."""
    m.box((x,y,.215),(.6,.6,.45),'st_stone')                 # base -.01...44 (sunk into the porch slab)
    m.box((x,y,.47),(.66,.66,.06),'st_stone_light',.02)       # chamfered cap .44..50
    m.lathe((x,y,0),[(.50,.22),(.70,.22),(h-.15,.19),(h+.01,.19)],'st_brown',12)
    m.box((x,y,h+.09),(.55,.55,.18),'st_brown_dark')
    m.collider((x,y,h/2),(.7,.7,h+.2))

# ---------------------------------------------------------------- props
def ring(m,x0,x1,cy,cz,r0,r1,key,n=15):
    """Closed ring (tube section) between x0 and x1: outer and inner bands plus both annular faces."""
    angles=np.linspace(0,math.tau,n)
    for a0,a1 in zip(angles[:-1],angles[1:]):
        c0,s0,c1,s1=math.cos(a0),math.sin(a0),math.cos(a1),math.sin(a1)
        for x,sgn in ((x0,1),(x1,-1)):
            q=[(x,cy+r1*c0,cz+r1*s0),(x,cy+r1*c1,cz+r1*s1),(x,cy+r0*c1,cz+r0*s1),(x,cy+r0*c0,cz+r0*s0)]
            m.poly(q if sgn>0 else q[::-1],key)
        m.poly([(x0,cy+r1*c0,cz+r1*s0),(x0,cy+r1*c1,cz+r1*s1),(x1,cy+r1*c1,cz+r1*s1),(x1,cy+r1*c0,cz+r1*s0)][::-1],key)
        m.poly([(x0,cy+r0*c0,cz+r0*s0),(x0,cy+r0*c1,cz+r0*s1),(x1,cy+r0*c1,cz+r0*s1),(x1,cy+r0*c0,cz+r0*s0)],key)

def bike(m,x,y,z,yaw,col):
    """Dark-framed bicycle: fat black tyres (.08 thick tubes), metal rims and spokes, dark frame."""
    with m.at((x,y,z),yaw):
        r=.34
        for wy in (-.58,.58):
            ring(m,-.04,.04,wy,r,.27,.34,'st_tyre')                     # tyre
            ring(m,-.025,.025,wy,r,.21,.27,'metal',n=13)                 # rim
            for k in range(6):
                a=k*math.pi/6;m.beam((0,wy-.22*math.cos(a),r-.22*math.sin(a)),(0,wy+.22*math.cos(a),r+.22*math.sin(a)),.018,.018,'metal')
            m.box((0,wy,r),(.09,.09,.09),'metal')
        for a,b in [((0,.58,r),(0,.08,.86)),((0,.58,r),(0,.02,.42)),((0,.02,.42),(0,.08,.86)),((0,.08,.86),(0,-.42,.92)),((0,.02,.42),(0,-.42,.92)),((0,-.42,.92),(0,-.58,r))]:
            m.beam(a,b,.045,.045,col)
        m.beam((-.22,-.44,1.0),(.22,-.44,1.0),.03,.03,'metal')
        m.box((0,.1,.92),(.13,.26,.05),'st_dark')
        m.box((0,.6,.55),(.07,.34,.03),'metal')

def bike_rack(m,x,y,z=.02):
    """Four dark bikes in a rail rack: low hoops at the back, tall hoops joined by a top rail along the street side."""
    for dy in (-.45,.45):m.beam((x-2.1,y+dy,z+.05),(x+2.1,y+dy,z+.05),.06,.07,'metal')
    m.beam((x-1.7,y-.45,z+.85),(x+1.7,y-.45,z+.85),.05,.05,'metal')             # top rail joining the front hoops
    for k,col in enumerate(['st_dark','st_dark','st_brown_dark','st_red']):
        bx=x-1.5+k*1.0
        for dy,hh in ((-.45,.85),(.45,.55)):
            m.beam((bx-.25,y+dy,z),(bx-.25,y+dy,z+hh),.04,.04,'metal');m.beam((bx+.25,y+dy,z),(bx+.25,y+dy,z+hh),.04,.04,'metal')
            m.beam((bx-.25,y+dy,z+hh),(bx+.25,y+dy,z+hh),.04,.04,'metal')
        bike(m,bx,y,z,0,col)
    m.collider((x,y,z+.5),(4.4,1.9,1.0))

def post_box(m,x,y):
    m.lathe((x,y,-.15),[(0,.34),(.2,.34),(.26,.29),(1.2,.29),(1.25,.34),(1.4,.34),(1.48,.28),(1.58,0)],'st_red',14)
    m.box((x,y-.28,.95),(.3,.06,.05),'st_dark')
    m.collider((x,y,.65),(.7,.7,1.6))

def banner(m,x,y,texts):
    m.box((x,y,1.7),(.09,.09,3.6),'metal');m.collider((x,y,1.7),(.2,.2,3.6))
    m.beam((x-.42,y-.06,3.35),(x+.42,y-.06,3.35),.05,.05,'metal')
    m.box((x,y-.08,2.05),(.64,.06,2.5),'st_white')
    for k,ch in enumerate(texts):text(m,ch,(x,y-.14,2.92-k*.47),.40)
    m.lathe((x,y-.12,1.05),[(0,.02),(.04,.14),(.1,.16),(.14,.12),(.16,.0)],'arc_bloom',8)

def bench(m,x,y,z=0,yaw=0,w=1.8):
    """Chunky bench: thick slats on tall dark end frames."""
    with m.at((x,y,z),yaw):
        for yy in (-.14,.14):m.box((0,yy,.47),(w,.24,.12),'wood_light')
        for xx in (-w*.4,w*.4):m.box((xx,0,.25),(.14,.52,.5),'st_brown_dark')
        m.box((0,-.24,.75),(w,.06,.28),'wood_light')
        for xx in (-w*.4,w*.4):m.box((xx,-.24,.66),(.12,.08,.5),'st_brown_dark')
        m.collider((0,0,.4),(w,.6,.9))

def timetable(m,x,y):
    """Free-standing framed timetable board on two posts under a little slate hood."""
    for dx in (-.72,.72):m.box((x+dx,y,1.15),(.10,.10,2.5),'metal')
    board(m,x,y-.06,1.7,1.6,1.3,'時刻表',.28,dz=-.2)
    for k in range(4):m.box((x,y-.19,1.65-k*.10),(1.1,.02,.04),'st_ink')
    pent(m,x-.95,x+.95,y+.06,y-.40,2.62,2.48,'st_slate',strip=.95,thick=.14,fascia=.2,lip=.06,soffit=False)
    m.collider((x,y,1.2),(1.7,.4,2.4))

def planter(m,x,y,w=1.7,d=.8):
    m.box((x,y,.25),(w,d,.6),'st_brown');m.box((x,y,.56),(w-.16,d-.16,.03),'soil')
    m.collider((x,y,.28),(w,d,.56))
    for k,dx in enumerate((-.4,.4)):arcade.flowers(m,x+dx,y,.55,31+k,root_spread=(.34,.26))

def flower_box(m,x,y,z,seed):
    m.box((x,y,z+.24),(.8,.62,.46),'st_brown');m.box((x,y,z+.48),(.68,.5,.02),'soil')
    m.collider((x,y,z+.24),(.8,.62,.46))
    arcade.flowers(m,x,y,z+.47,seed,root_spread=(.26,.18))

def plinth(m,cx,cy,w,d):
    """Pale ashlar plinth 1.3 tall and .08 proud: course lines, staggered vertical joints, light sloped cap, brown string course."""
    m.box((cx,cy,.25),(w+.16,d+.16,1.3),'st_stone')
    courses=[(-.4,.18),(.18,.42),(.42,.66),(.66,.9)]
    for z in (.18,.42,.66):m.box((cx,cy,z),(w+.18,d+.18,.03),'st_stone_dark')
    for k,(z0,z1) in enumerate(courses):
        zc=(z0+z1)/2;ch=z1-z0-.04;off=.8*(k%2)
        for x in np.arange(-w/2+.5+off,w/2-.3,1.6):                       # front and back faces
            for s in (-1,1):m.box((cx+float(x),cy+s*(d+.16)/2,zc),(.03,.04,ch),'st_stone_dark')
        for y in np.arange(-d/2+.5+off,d/2-.3,1.6):                       # end faces
            for s in (-1,1):m.box((cx+s*(w+.16)/2,cy+float(y),zc),(.04,.03,ch),'st_stone_dark')
    m.box((cx,cy,.96),(w+.26,d+.26,.12),'st_stone_light')
    m.box((cx,cy,1.10),(w+.20,d+.20,.16),'st_brown')

# ---------------------------------------------------------------- building
def build(name,variant,lettering):
    global LET;LET=lettering
    palette(variant);m=v.Mesh(name)
    WING_H=4.8;TOW_H=9.8;FY=-6.5;TY=-7.5;BY=5.0;WX=22.4
    # --- masses, plinths, colliders
    m.box((0,(FY+BY)/2,2.2),(2*WX,BY-FY,5.2),'st_cream');m.collider((0,(FY+BY)/2,2.2),(2*WX,BY-FY,5.2))
    m.box((0,(TY+BY)/2,4.7),(10,BY-TY,10.2),'st_cream');m.collider((0,(TY+BY)/2,4.7),(10,BY-TY,10.2))
    plinth(m,0,(FY+BY)/2,2*WX,BY-FY)
    plinth(m,0,(TY+BY-.3)/2,10,BY-.3-TY)
    # brown string course along the wings at sill height
    m.box((0,(FY+BY)/2,1.5),(2*WX+.08,BY-FY+.08,.10),'st_brown')
    # tower bands: thin brown string course above the sign, a two-step cornice (dark band under a deep pale fascia)
    m.box((0,(TY+BY)/2,6.45),(10.36,BY-TY+.36,.18),'st_brown')
    m.box((0,(TY+BY)/2,9.31),(10.56,BY-TY+.56,.18),'st_dark')
    m.box((0,(TY+BY)/2,9.60),(11.0,BY-TY+1.0,.40),'st_fascia')
    # --- roofs (shallow slate wings, steep copper tower)
    hip(m,0,(FY+BY)/2+.15,2*WX+2.2,BY-FY+2.2,WING_H,2.6,'st_slate','st_seam','st_fascia','st_slate_edge',1.3)
    hip(m,0,(TY+BY)/2,12.4,BY-TY+2.1,TOW_H,4.4,'st_copper','st_copper_seam','st_fascia','st_copper_edge',1.1)
    cy=(TY+BY)/2
    m.beam((0,cy,TOW_H+4.2),(0,cy,TOW_H+6.0),.12,.12,'st_dark')
    m.lathe((0,cy,TOW_H+5.25),[(-.2,.03),(-.05,.2),(.1,.2),(.24,.03)],'st_copper_edge',10)
    m.lathe((0,cy,TOW_H+5.95),[(0,.08),(.35,0)],'st_dark',8)
    # --- porch: slate pent roof, warm timber rafters and purlin under a timber soffit, head beam on eight columns
    PX=23.3;PYE=-11.2;PZE=3.55;PZW=4.15;TH=.28;CY=-10.2
    pent(m,-PX,PX,FY+.1,PYE,PZW,PZE,'st_slate',thick=TH,soffit_key='st_timber')
    def slope(y):return PZE+(y-PYE)/(FY+.1-PYE)*(PZW-PZE)
    sof=TH/2+.05+.06                                       # soffit underside below the slab line
    for x in np.arange(-PX+1.1,PX,2.2):
        x=float(x);m.beam((x,FY,slope(FY)-sof-.07),(x,PYE+.12,slope(PYE+.12)-sof-.07),.12,.14,'st_timber')
    m.beam((-PX+.05,-8.5,slope(-8.5)-sof-.25),(PX-.05,-8.5,slope(-8.5)-sof-.25),.20,.22,'st_brown')
    HB=slope(CY)-sof-.20
    m.beam((-PX+.05,CY,HB),(PX-.05,CY,HB),.25,.28,'st_brown')
    COL_H=HB-.14-.18
    for x in (-21,-15,-7,-2.9,2.9,7,15,21):column(m,x,CY,COL_H)
    tx=18.0 if variant%2==0 else -18.0                    # ticket kiosk centre (between the columns at 15 and 21)
    lx_list=[-18,-11,-4.95,4.95,11,18]
    lx_list=[x for x in lx_list if abs(x-tx)>.5]+[tx-1.7,tx+1.7]   # lanterns flank the kiosk instead of hiding it
    for x in lx_list:arcade.lantern(m,x,CY,2.5,.5)
    # pale paved porch: one flat slab flush with the apron (top z=.02) with a single light nosing on its exposed edges
    FL0=FY+.05;FL1=FL0-4.4;FW=2*WX+1.6
    m.box((0,(FL0+FL1)/2,-.18),(FW,FL0-FL1,.40),'st_floor');m.collider((0,(FL0+FL1)/2,-.18),(FW,FL0-FL1,.40))
    m.box((0,FL1+.06,-.01),(FW+.02,.12,.07),'st_stone_light')                         # nosing, top .025
    for sx in (-1,1):m.box((sx*(FW/2-.06),(FL0+FL1)/2,-.01),(.12,FL0-FL1+.02,.07),'st_stone_light')
    # --- front: wings
    for sx in (-1,1):
        for x in (9.2,11.2):arch_window(m,sx*x,FY,1.62,1.4,2.0)
        if sx<0 or variant%2==1:
            for x in (15.4,17.4):arch_window(m,sx*x,FY,1.62,1.4,2.0)
        downpipe(m,sx*(WX-.35),FY-.12,WING_H)
    # ticket kiosk: lit window, deep pale stone counter with a brown front board, framed sign and its own slate hood
    m.box((tx,FY-.08,2.1),(2.6,.16,1.2),'st_brown_dark');m.box((tx,FY-.19,2.1),(2.3,.06,1.0),'st_glass')
    m.box((tx,FY-.23,2.1),(.08,.05,1.0),'st_brown_dark');m.box((tx,FY-.23,2.1),(2.3,.05,.08),'st_brown_dark')
    m.box((tx,FY-.30,1.45),(2.9,.60,.10),'st_stone');m.box((tx,FY-.28,1.32),(2.8,.52,.16),'st_brown')
    m.box((tx,FY-.55,1.28),(2.8,.03,.20),'st_brown')
    m.collider((tx,FY-.30,1.4),(2.9,.6,.2))
    for dx in (-1.2,1.2):m.beam((tx+dx,FY-.05,.95),(tx+dx,FY-.52,1.22),.07,.07,'st_brown')
    board(m,tx,FY,3.1,2.4,.6,'切符売り場',.42,frame=.08,depth=.14,dz=.11,frame_key='st_brown')
    pent(m,tx-1.5,tx+1.5,FY,FY-1.0,3.62,3.30,'st_slate',strip=.75,thick=.18,fascia=.30,lip=.08)
    for dx in (-1.35,1.35):m.beam((tx+dx,FY-.05,2.45),(tx+dx,FY-.9,3.05),.08,.09,'st_brown')
    # --- front: tower pavilion
    double_door(m,0,TY,h=2.5,fan=1.0)
    for sx in (-1,1):arch_window(m,sx*3.4,TY,1.62,1.2,1.9)
    board(m,0,TY,5.55,3.8,.95,'ひだまり駅',1.2,frame=.12,depth=.10,dz=.26,frame_key='st_brown',gap=.06)
    # clock: thick brown rim ring, white face set back, bold hour marks and hands
    cz=8.0;R=1.40
    arch_band(m,0,TY-.24,cz,1.18,R,'st_brown',n=49,full=True)
    for k in range(48):
        a0=k*math.tau/48;a1=(k+1)*math.tau/48
        m.poly([(R*math.cos(a0),TY,cz+R*math.sin(a0)),(R*math.cos(a1),TY,cz+R*math.sin(a1)),(R*math.cos(a1),TY-.24,cz+R*math.sin(a1)),(R*math.cos(a0),TY-.24,cz+R*math.sin(a0))][::-1],'st_brown')
    m.poly([(1.19*math.cos(k*math.tau/48),TY-.19,cz+1.19*math.sin(k*math.tau/48)) for k in range(48)],'st_white')
    for j in range(12):
        a=j*math.tau/12;L=.22 if j%3==0 else .14
        m.beam((math.sin(a)*(1.10-L),TY-.22,cz+math.cos(a)*(1.10-L)),(math.sin(a)*1.10,TY-.22,cz+math.cos(a)*1.10),.08,.05,'st_ink')
    m.beam((0,TY-.25,cz),(-.6,TY-.25,cz+.45),.10,.05,'st_ink')
    m.beam((0,TY-.27,cz),(.38,TY-.27,cz+.9),.08,.05,'st_ink')
    m.box((0,TY-.28,cz),(.16,.04,.16),'st_ink',.02)
    for sx in (-1,1):sq_window(m,sx*3.2,TY,cz,1.1,1.1)
    # --- back wall (platform side)
    with m.at(yaw=180):
        y=-BY
        # The rear doorway opens onto the raised platform.
        with m.at((0,0,.25)):
            double_door(m,0,y,2.4,2.4,1.2)
        for sx in (-1,1):
            for x in (9.2,11.2,15.4,17.4):arch_window(m,sx*x,y,1.62,1.4,2.0)
            sq_window(m,sx*3.2,y,cz,1.1,1.1)
            vent(m,sx*20.5,y,4.1);downpipe(m,sx*(WX-.35),y-.12,WING_H)
        board(m,0,y,5.3,4.8,.9,'ひだまり',.6,frame=.1,depth=.18,dz=.12,frame_key='st_brown',gap=.05)
    # --- side walls
    for sx in (-1,1):
        with m.at((sx*WX,0,0),90*sx):
            lx=lambda wy:-sx*wy
            for wy in (-3.6,-1.6):arch_window(m,lx(wy),0,1.62,1.4,2.0)
            v.door(m,lx(2.6),-.05,.06,1.2,2.2)
            pent(m,lx(2.6)-1.2,lx(2.6)+1.2,0,-.9,3.12,2.84,'st_slate',strip=.8,thick=.16,fascia=.26,lip=.08)
            for dx in (-1.0,1.0):m.beam((lx(2.6)+dx,-.03,2.0),(lx(2.6)+dx,-.8,2.55),.08,.09,'st_brown')
            vent(m,lx(0.4),0,4.1)
    # --- platform, tall braced canopy (rises above the wing roofs), signs and benches behind
    m.box((0,7.5,-.075),(2*WX+2.0,4.9,.65),'st_stone');m.collider((0,7.5,-.075),(2*WX+2.0,4.9,.65))
    m.box((0,9.55,.255),(2*WX+2.0,.3,.02),'st_tactile')
    CX=24.5
    CZ=3.1                                                  # canopy lift: posts to 7.7, eaves at 7.8, ridge at 8.7
    for x in range(-21,22,6):
        m.box((x,9.2,2.35+CZ/2),(.3,.3,4.25+CZ),'st_brown');m.collider((x,9.2,2.35+CZ/2),(.34,.34,4.25+CZ))
        m.beam((x,9.2,4.55+CZ),(x,7.4,5.45+CZ),.12,.15,'st_brown');m.beam((x,7.4,5.45+CZ),(x,5.3,4.55+CZ),.12,.15,'st_brown')
        m.beam((x,9.2,3.9+CZ),(x,8.2,4.55+CZ),.09,.09,'st_brown_dark');m.beam((x,9.2,3.9+CZ),(x,10.0,4.35+CZ),.09,.09,'st_brown_dark')
        for s in (-1,1):                                    # second pair of knee braces up to the tie beam
            if abs(x+s*.85)<CX-.4:m.beam((x+s*.05,9.2,4.15),(x+s*.90,9.2,5.0),.12,.12,'st_brown_dark')
    m.box((0,9.2,4.6+CZ),(2*CX,.22,.3),'st_brown')
    m.box((0,9.2,5.0),(2*CX-.6,.22,.22),'st_brown')         # horizontal tie beam between the posts at 5 m
    m.beam((-CX,7.4,5.74+CZ),(CX,7.4,5.74+CZ),.34,.18,'st_brown')
    pent(m,-CX,CX,7.4,9.85,5.6+CZ,4.7+CZ,'st_slate',thick=.2,fascia=.35,lip=.1);pent(m,-CX,CX,7.4,5.3,5.6+CZ,4.7+CZ,'st_slate',thick=.2,fascia=.35,lip=.1)
    for sx in (-1,1):
        tri=[(sx*CX,5.3,4.7+CZ),(sx*CX,9.85,4.7+CZ),(sx*CX,7.4,5.6+CZ)]
        m.poly(tri if sx>0 else tri[::-1],'st_cream');m.poly(tri[::-1] if sx>0 else tri,'st_cream')
    for k,x in enumerate((-12,12)):                         # platform number boards hang from the tie beam
        with m.at((x,9.05,4.3),180):
            board(m,0,0,0,1.0,.8,str(k+1),.5,frame=.08,depth=.12,dz=-.2,frame_key='st_brown')
        for dx in (-.3,.3):m.beam((x+dx,9.05,4.7),(x+dx,9.05,4.9),.03,.03,'metal')
    for x in (-8,8):bench(m,x,6.6,.25)
    # --- street props under and beside the porch (apron y >= -11.5, planter spot near x=-9 kept free)
    # Centre the rack in the clear bay between columns at x=-21 and -15.
    if variant%2==0:bike_rack(m,-18.0,-9.8)
    else:
        for k in range(3):m.box((-19.4+k*1.1,-9.2,.47),(1.0,.9,.9),'wood_light');m.collider((-18.3,-9.2,.47),(3.3,.9,.9))
    bench(m,-13.5,-7.2,.02)                                   # against the wall, under the porch
    bench(m,5.0,-9.55,.02)                                    # out at the porch edge beside the door, in the light
    for sx in (-1,1):
        v.pot(m,sx*2.0,-8.4,.02,1.1,'clay',plant=True)
        flower_box(m,sx*3.8,-8.9,.02,41+sx)
    banner(m,12.5,-9.9,'ようこそ' if variant%2==0 else '秋まつり')
    post_box(m,20.15,-9.6)
    planter(m,21.6,-9.2)
    timetable(m,22.1,-10.5)
    return m
