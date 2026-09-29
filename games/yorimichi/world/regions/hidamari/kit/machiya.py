"""Kyoto machiya pair: a tea shop and a kimono tailor under one deep dark-tiled gable roof."""
import math,random
from village import build as v
from hidamari import arcade
ASSETS={'HD_Shop_00':0,'HD_Shop_08':1}

W,D=22.0,16.0;HX,HY=W/2,D/2
G=3.5       # ground-floor ceiling / upper storey base
E=6.9       # upper storey top (eave line)
RISE=5.0    # ridge rise above the eave (~33 deg pitch, ridge at z 11.9)
DY=8.95     # roof eave line |y| (0.95 m eaves, back stays inside +D/2+1)
OX=1.0      # gable verge overhang along X


def palette(variant):
    arcade.palette()
    v.PALETTE.update({
        # The engine's exposure lifts these a lot: (.50,.40,.24) rendered near-white, so the ochre sits well below it.
        'mc_plaster':(.40,.30,.14) if variant==0 else (.38,.31,.17),     # front infill panels
        'mc_plaster2':(.36,.27,.13) if variant==0 else (.35,.28,.16),    # gables, sides, back
        'mc_ochre':(.50,.38,.20),        # lamp-lit interior walls and partitions
        'mc_ochre2':(.44,.34,.18),       # ground-floor piers, deeper than the upper storey
        'mc_glow':(.62,.40,.065),        # warm amber glow (M_Arcade 'leaf' emission): bay ceilings, cabinet backs
        'mc_mushiko':(.58,.34,.06),      # amber glow behind the mushiko slats
        'mc_timber':(.21,.105,.04) if variant==0 else (.19,.09,.045),
        'mc_dark':(.075,.038,.016),'mc_fascia':(.34,.21,.09),'mc_barge':(.40,.26,.12),
        'mc_sign':(.56,.40,.18),
        'mc_tile':(.030,.036,.050),'mc_tile2':(.036,.042,.058),'mc_tile_edge':(.020,.024,.034),
        'mc_char':(.035,.026,.02),'mc_char2':(.046,.034,.025),'mc_charcoal':(.05,.05,.045),
        'mc_ivory':(.72,.66,.52),
        'mc_green':(.10,.18,.05),'mc_purple':(.22,.10,.30),
        'mc_tatami':(.34,.33,.17),'mc_tatami2':(.31,.31,.15),'mc_bamboo':(.40,.28,.12),
        'mc_plank':(.30,.17,.07),'mc_plinth':(.26,.23,.18),'mc_step':(.30,.29,.27),
    })


def frange(a,b,step):
    out=[];x=a
    while x<=b+1e-6:out.append(x);x+=step
    return out


def zr(y):
    """Main roof surface height at |y|."""
    return E-.15+(RISE+.15)*(1-abs(y)/DY)


def disc_y(m,x,y,z,r,depth,key,n=8):
    """Round eave-tile cap: a short cylinder along Y whose front face looks toward -Y."""
    f=[(x+r*math.cos(k*math.tau/n),y,z+r*math.sin(k*math.tau/n)) for k in range(n)]
    b=[(xx,y+depth,zz) for xx,_,zz in f]
    m.poly(f,key);m.poly(b[::-1],key)
    for k in range(n):
        m.poly([f[k],b[k],b[(k+1)%n],f[(k+1)%n]],key)


def eave_caps(m,xa,xb,y,z,step=.3):
    for x in frange(xa+.15,xb-.15,step):disc_y(m,x,y,z,.09,.06,'mc_tile_edge')


def eave_edge(m,xa,xb,ye,ze,fh,caps=False):
    """Eave dressing seen from the street: tile-edge cap beam, honey fascia board, rafter ends showing under it.
    ye/ze: eave line (surface edge). fh: fascia height. Everything runs along X."""
    m.beam((xa,ye,ze+.02),(xb,ye,ze+.02),.16,.18,'mc_tile_edge')
    m.beam((xa,ye+.04,ze-.02-fh/2),(xb,ye+.04,ze-.02-fh/2),.12,fh,'mc_barge')
    if caps:eave_caps(m,xa,xb,ye-.15,ze+.02)
    return ze-.02-fh   # underside of the fascia (rafter ends go just below)


def pent(m,xa,xb,yw,zw,depth,drop,rafters=True,plate=True,caps=False,top='mc_tile',fh=.26):
    """Tiled lean-to (hisashi) along X: wall line at y=yw, sloping down toward -Y."""
    p=[(xa,yw,zw),(xb,yw,zw),(xb,yw-depth,zw-drop),(xa,yw-depth,zw-drop)]
    m.poly(p[::-1],top);m.poly([(x,y,z-.06) for x,y,z in p],'mc_timber')
    for x,rev in [(xa,True),(xb,False)]:
        cap=[(x,yw,zw),(x,yw-depth,zw-drop),(x,yw-depth,zw-drop-.06),(x,yw,zw-.06)]
        m.poly(cap[::-1] if rev else cap,'mc_tile_edge')
    for i in range(1,4):
        t=i/4.2;y=yw-depth*t;z=zw-drop*t+.025
        m.beam((xa,y,z),(xb,y,z),.05,.05,'mc_tile_edge')
    under=eave_edge(m,xa,xb,yw-depth,zw-drop,fh,caps)
    if plate:m.box(((xa+xb)/2,yw-.11,zw-.15),(xb-xa,.2,.2),'mc_timber')
    if rafters:
        # Rafters parallel to the slope, their ends showing below the fascia and a hand's width past it.
        r=zw-drop-under+.01
        for x in frange(xa+.25,xb-.25,.45):
            m.beam((x,yw-.02,zw-r),(x,yw-depth-.08,zw-drop-r-.02),.08,.08,'mc_fascia')


def main_roof(m):
    xw=HX+OX;top=zr(0);low=zr(DY)
    for s in [-1,1]:
        p=[(-xw,0,top),(xw,0,top),(xw,s*DY,low),(-xw,s*DY,low)]
        m.poly(p if s>0 else p[::-1],'mc_tile')
        u=[(x,y,z-.05) for x,y,z in p]
        m.poly(u[::-1] if s>0 else u,'mc_dark')
        for row in range(1,12):
            y=s*DY*row/12;z=zr(y)+.025
            m.beam((-xw,y,z),(xw,y,z),.05,.05,'mc_tile_edge')
        for x in frange(-xw+.28,xw-.2,.55):
            m.beam((x,s*.35,zr(.35)+.03),(x,s*(DY-.05),zr(DY-.05)+.03),.06,.06,'mc_tile2')
        # Eave line: tile caps, a 0.3 m honey fascia and rafter ends under it (front and back).
        with m.at((0,0,0),0 if s<0 else 180):
            under=eave_edge(m,-xw,xw,-DY,low,.30,caps=True)
        m.box((0,s*(HY+.08),E-.06),(W+.5,.26,.2),'mc_timber')
        r=low-under+.01
        for x in frange(-xw+.3,xw-.3,.45):
            m.beam((x,s*(HY-.1),zr(HY-.1)-r),(x,s*(DY+.08),zr(DY+.08)-r-.02),.08,.08,'mc_fascia')
    # Closed gables: pentagon fills between the wall top and the roof planes, bargeboards along the verge.
    for s in [-1,1]:
        x=s*(HX+.02)
        p=[(x,-HY,E-.35),(x,HY,E-.35),(x,HY,zr(HY)),(x,0,top),(x,-HY,zr(HY))]
        m.poly(p if s>0 else p[::-1],'mc_plaster2')
        xe=s*xw
        for sy in [-1,1]:
            m.beam((xe-s*.02,sy*DY,low-.12),(xe-s*.02,0,top-.12),.24,.36,'mc_barge')
            m.beam((xe-s*.04,sy*DY,low+.04),(xe-s*.04,0,top+.04),.12,.12,'mc_tile_edge')
        # Purlin ends showing under the roof plane between the gable wall and the bargeboard.
        for y in [-5.5,-2.5,2.5,5.5]:
            m.box((s*(HX+OX/2-.05),y,zr(y)-.36),(OX-.1,.3,.3),'mc_timber')
    # Ridge: thick cap run, bold end ornaments.
    m.box((0,0,top+.1),(2*xw+.2,.5,.24),'mc_tile_edge')
    for x in frange(-xw+.3,xw-.3,.62):
        if abs(x)>1.5:m.box((x,0,top+.32),(.5,.6,.2),'mc_tile_edge',.03)
    for s in [-1,1]:m.box((s*(xw+.05),0,top+.36),(.5,.7,.5),'mc_tile_edge',.05)
    kemuridashi(m,top)


def kemuridashi(m,top):
    """Ridge smoke vent: plastered cupola with timber posts, dark slats and its own hipped tile roof, sitting on the back slope."""
    yc=.7;zb=top-.85;zt=top+1.15
    m.box((0,yc,(zb+zt)/2),(2.2,1.3,zt-zb),'mc_plaster')
    for sx in [-1,1]:
        for sy in [-1,1]:m.box((sx*1.08,yc+sy*.63,(zb+zt)/2),(.1,.1,zt-zb),'mc_timber')
    for z in [top+.2,zt-.05]:m.box((0,yc,z),(2.3,1.4,.09),'mc_timber')
    for x in frange(-.9,.9,.15):
        for sy in [-1,1]:m.box((x,yc+sy*.68,top+.67),(.06,.07,.7),'mc_dark')
    # Hip roof, 0.3 m overhang all round.
    ex,ey=1.4,.95;rx=.8;ze=zt;zr2=zt+.5
    c=[(-ex,yc-ey,ze),(ex,yc-ey,ze),(ex,yc+ey,ze),(-ex,yc+ey,ze)]
    ra,rb=(-rx,yc,zr2),(rx,yc,zr2)
    faces=[[c[0],c[1],rb,ra],[c[2],c[3],ra,rb],[c[1],c[2],rb],[c[3],c[0],ra]]
    for f in faces:
        m.poly(f,'mc_tile');m.poly([(x,y,z-.05) for x,y,z in f][::-1],'mc_dark')
    for a,b in [(c[0],c[1]),(c[2],c[3])]:m.beam((a[0],a[1],a[2]+.03),(b[0],b[1],b[2]+.03),.1,.12,'mc_tile_edge')
    for a,b in [(c[1],c[2]),(c[3],c[0])]:m.beam((a[0],a[1],a[2]+.03),(b[0],b[1],b[2]+.03),.1,.12,'mc_tile_edge')
    for a,b in [(c[0],ra),(c[1],rb),(c[2],rb),(c[3],ra)]:m.beam(a,b,.1,.1,'mc_tile_edge')
    m.box((0,yc,zr2+.04),(2*rx+.2,.3,.16),'mc_tile_edge')


def boards(m,xa,xb,y=-.08):
    n=math.ceil((xb-xa)/.33);bw=(xb-xa)/n
    for k in range(n):
        m.box((xa+(k+.5)*bw,y,.7),(bw-.02,.14,1.8),'mc_char' if k%2 else 'mc_char2')


def koshi_window(m,x,y,z,w,h):
    m.box((x,y-.08,z),(w+.2,.16,h+.2),'arc_timber')
    m.box((x,y-.19,z),(w,.04,h),'arc_shopglass')
    for xx in frange(x-w/2+.06,x+w/2-.06,.13):m.box((xx,y-.26,z),(.05,.06,h),'arc_timber')
    for zz in [z-h/2,z+h/2]:m.box((x,y-.27,zz),(w+.1,.08,.07),'mc_dark')
    m.box((x,y-.24,z-h/2-.12),(w+.34,.36,.12),'mc_fascia')


def teapot(m,x,y,z,key='clay',scale=1):
    m.lathe((x,y,z),[(0,0),(0,.13*scale),(.12*scale,.19*scale),(.24*scale,.13*scale),(.27*scale,.06*scale),(.3*scale,0)],key,10)
    m.beam((x+.12*scale,y,z+.1*scale),(x+.26*scale,y,z+.24*scale),.05*scale,.05*scale,key)
    m.beam((x-.14*scale,y,z+.14*scale),(x-.22*scale,y,z+.25*scale),.03*scale,.03*scale,'mc_dark')


def cup(m,x,y,z,key='cream'):
    m.lathe((x,y,z),[(0,0),(0,.05),(.08,.07),(.1,.06)],key,8)


def thick_text(m,text,pos,size,color,lettering,depth=.06):
    """Stacked copies of the extruded text (each 0.012 m) so the characters read as a thick plaque.
    pos y is the FRONT face of the text; the stack extends toward +Y (into the board)."""
    x,y,z=pos;n=max(1,math.ceil(depth/.012-1e-6))
    for k in range(n):lettering(m,text,(x,y+.006+k*.012,z),size,color=color)


def sign_board(m,x,text,lettering):
    """Light tan board, dark frame, big dark characters, a honey timber cap; hung from the mushiko sill in front of the hisashi."""
    y=-9.45;z=4.6;w=3.6;h=1.45
    m.box((x,y,z),(w,.14,h),'mc_sign')
    for dz in [-h/2,h/2]:m.box((x,y-.02,z+dz),(w+.08,.18,.08),'mc_dark')
    for dx in [-w/2,w/2]:m.box((x+dx,y-.02,z),(.08,.18,h+.08),'mc_dark')
    m.box((x,y+.04,z+h/2+.08),(w+.3,.6,.18),'mc_fascia')
    for dx in [-1.4,1.4]:m.box((x+dx,y-.06,z+h/2-.06),(.08,.3,.12),'mc_dark')
    for dx in [-1.3,1.3]:m.beam((x+dx,-8.2,4.7),(x+dx,y+.06,z+h/2),.06,.06,'mc_dark')
    # Blender's font size gives glyphs about half the nominal height, so 2.0 makes ~1 m characters.
    thick_text(m,text,(x,y-.08,z-.5),2.0,'mc_char',lettering,.06)


def circle(m,x,y,z,r,key,n=16):
    p=[(x+r*math.cos(k*math.tau/n),y,z+r*math.sin(k*math.tau/n)) for k in range(n)]
    m.poly(p,key);m.poly(p[::-1],key)


def leaf(m,x,y,z,size,key):
    p=[(x,y,z-size),(x+size*.55,y,z-size*.3),(x+size*.35,y,z+size*.6),(x,y,z+size),(x-size*.35,y,z+size*.6),(x-size*.55,y,z-size*.3)]
    m.poly(p,key);m.poly(p[::-1],key)


def noren(m,xc,kind,key):
    """Three cloth panels, each slightly turned about Z, the centre one hung a little forward; hem below the lintel line."""
    for dx,yaw,fwd in [(-1.55,2.5,0),(0,-1.5,.04),(1.55,-2.5,0)]:
        with m.at((xc+dx,-7.95-fwd,0),yaw):m.box((0,0,2.83),(1.45,.03,1.0),key)
    yf=-8.02
    circle(m,xc,yf,2.86,.3,'arc_ivory')
    if kind=='tea':
        m.lathe((xc,yf-.01,2.72),[(0,.0),(.0,.14),(.10,.17),(.12,0)],key,10)
        leaf(m,xc+.08,yf-.02,3.02,.11,'mc_green')
    else:
        for k in range(5):
            a=k*math.tau/5+math.pi/2
            circle(m,xc+.15*math.cos(a),yf-.01,2.86+.15*math.sin(a),.08,key,10)
        circle(m,xc,yf-.02,2.86,.06,'arc_ivory',8)


def banner(m,xb,chars,key,kind,lettering):
    """Tall cloth banner on the pier between the bays: two big ivory characters and the shop icon, rods top and bottom."""
    m.box((xb,-7.80,1.95),(.95,.03,2.3),key)
    for z in [3.13,.77]:m.beam((xb-.6,-7.8,z),(xb+.6,-7.8,z),.06,.06,'mc_dark')
    for j,ch in enumerate(chars):thick_text(m,ch,(xb,-7.82,2.36-j*.7),1.24,'mc_ivory',lettering,.03)
    if kind=='tea':
        circle(m,xb,-7.825,1.12,.24,'mc_ivory',12);leaf(m,xb+.02,-7.835,1.12,.15,key)
    else:
        m.box((xb,-7.825,1.08),(.2,.012,.48),'mc_ivory');m.box((xb,-7.825,1.22),(.5,.012,.16),'mc_ivory')


def cabinet(m,xc,kind):
    m.box((xc,-7.2,1.95),(2.0,.04,2.3),'mc_glow')            # lit back board: goods in silhouette
    m.box((xc,-7.42,.2),(2.06,.5,1.2),'arc_timber')
    m.box((xc,-7.42,3.22),(2.06,.5,.24),'mc_fascia')
    for dx in [-1,1]:m.box((xc+dx*.98,-7.42,1.95),(.1,.5,2.3),'mc_fascia')
    for z in [1.55,2.3]:m.box((xc,-7.4,z),(1.9,.44,.05),'mc_fascia')
    for dx in [-.33,.33]:m.box((xc+dx,-7.66,1.95),(.05,.03,2.3),'mc_fascia')
    m.box((xc,-7.66,1.95),(2.0,.03,.05),'mc_fascia')
    tops=[.8,1.575,2.325]
    if kind=='tea':
        for j,(dx,t) in enumerate([(-.55,0),(.4,0),(-.4,1),(.5,1),(0,2)]):
            teapot(m,xc+dx,-7.42,tops[t],['clay','cream','mc_green','clay','cream'][j],.9)
        for dx,t in [(-.1,0),(.05,1),(-.55,2),(.55,2)]:cup(m,xc+dx,-7.5,tops[t])
    else:
        cols=['mc_purple','arc_rose','blue','rust','cream','mc_green']
        for t in range(3):
            for k in range(3):
                m.box((xc-.35+t*.1,-7.42,tops[t]+.08+k*.16),(.95,.3,.15),cols[(t*3+k)%6],.02)
        m.lathe((xc+.6,-7.42,tops[1]),[(0,0),(0,.11),(.6,.11),(.6,0)],'mc_purple',10)
    m.collider((xc,-7.42,1.55),(2.06,.5,3.9))


def koshi_bay(m,xk):
    """Dashigoshi: the lattice bay projects 0.4 m past the post line on a stone sill under its own tiled pent."""
    zc=1.82;h=2.62;wb=2.06;ya=-7.5;yb=-8.33
    m.box((xk,-8.15,.16),(2.3,.55,.35),'mc_step')                        # stone sill
    for z in [.43,3.22]:m.box((xk,(ya+yb)/2,z),(wb+.16,ya-yb,.16),'mc_timber')
    for dx in [-1,1]:m.box((xk+dx*(wb/2+.03),(ya+yb)/2,zc),(.16,ya-yb,h+.32),'mc_timber')
    m.box((xk,-8.13,zc),(wb,.04,h),'arc_shopglass')
    for x in frange(xk-.95,xk+.95,.127):m.box((x,-8.25,zc),(.05,.07,h),'arc_timber')
    for z in [.62,1.9,3.1]:m.box((xk,-8.30,z),(wb,.09,.07),'mc_dark')
    m.collider((xk,-7.9,1.6),(wb+.2,.9,4.0))
    pent(m,xk-1.15,xk+1.15,-8.0,3.3,.55,.22,rafters=False,fh=.16)
    # Bamboo blind half lowered in front of the lattice.
    m.box((xk,-8.45,2.78),(2.0,.04,1.0),'mc_bamboo')
    m.beam((xk-1.0,-8.45,3.32),(xk+1.0,-8.45,3.32),.13,.13,'mc_bamboo')
    for z in [2.45,2.75,3.05]:m.box((xk,-8.475,z),(2.0,.012,.04),'arc_timber')


def shoji(m,x,w=2.6,h=2.1,y=-2.0,z=1.6):
    """Big glowing paper screen against the back wall with a timber mullion grid 0.01 m in front of it."""
    m.box((x,y,z),(w,.06,h),'arc_paper')
    n=max(3,round(w/.55))
    for k in range(n+1):m.box((x-w/2+k*w/n,y-.055,z),(.05,.03,h),'mc_timber')
    for k in range(5):m.box((x,y-.055,z-h/2+k*h/4),(w,.03,.05),'mc_timber')


def interior_lights(m,inner):
    """Glowing amber ceiling, a lit shoji on the inner partition, two hanging paper lanterns."""
    m.box((0,-4.3,3.3),(4.8,4.7,.1),'mc_glow')
    m.box((inner*2.3,-4.0,1.55),(.05,2.4,2.2),'arc_paper')
    for dy in [-1.1,-.55,0,.55,1.1]:m.box((inner*2.26,-4.0+dy,1.55),(.03,.05,2.2),'arc_timber')
    for dz in [-1.05,-.35,.35,1.05]:m.box((inner*2.26,-4.0,1.55+dz),(.03,2.4,.05),'arc_timber')
    v.lantern(m,0,-5.7,2.9,.45);v.lantern(m,0,-3.1,2.9,.45)


def interior_tea(m,variant,inner):
    """Local frame: open bay centre, floor top at .45, back wall at y=-2, ceiling 3.25."""
    for k,dx in enumerate([-1.45,0,1.45]):m.box((dx,-4.3,.47),(1.42,4.2,.06),'mc_tatami' if k%2 else 'mc_tatami2')
    for x in [-1.25,1.25]:
        for y in [-5.3,-3.4]:m.box((x,y,.56),(.55,.55,.10),'mc_green',.02)
    m.box((0,-4.3,.78),(1.5,.8,.06),'arc_timber')
    for dx in [-.65,.65]:
        for dy in [-.32,.32]:m.box((dx,-4.3+dy,.64),(.08,.08,.28),'arc_timber')
    teapot(m,-.3,-4.3,.81,'clay',.7);cup(m,.3,-4.4,.81);cup(m,.45,-4.15,.81)
    shoji(m,-1.0)
    with m.at((0,0,.45)):arcade.shelf(m,1.3,-2.36,1,71+variant)
    interior_lights(m,inner)


def interior_kimono(m,variant,inner):
    m.beam((-2.2,-2.9,2.9),(2.2,-2.9,2.9),.06,.06,'arc_timber')
    for x,key in [(-1.3,'mc_purple' if variant==0 else 'blue'),(.3,'arc_rose' if variant==0 else 'mc_purple')]:
        m.box((x,-2.9,1.95),(.8,.06,1.5),key);m.box((x,-2.9,2.45),(1.7,.05,.55),key)
        m.box((x,-2.94,2.55),(.16,.02,.3),'arc_ivory')
        for j in range(4):m.box((x-.25+(j%2)*.5,-2.94,1.5+j*.28),(.1,.02,.1),'arc_ivory')
    shoji(m,-.5)
    m.box((1.6,-4.6,.75),(1.2,1.0,.6),'arc_trim')
    cols=['rust','blue','mc_green','arc_rose','cream','clay']
    for j in range(6):
        x=1.6-.36+(j%3)*.36;y=-4.6-.26+(j//3)*.52
        m.lathe((x,y,1.0),[(0,0),(0,.13),(1.05+.1*(j%2),.13),(1.05+.1*(j%2),0)],cols[j],8)
    m.box((-1.1,-5.3,.9),(1.8,.8,.8),'arc_timber')
    for k,dx in enumerate([-.55,0,.55]):
        for j in range(4):m.box((-1.1+dx,-5.3,1.34+j*.07),(.48,.5,.065),cols[(k*2+j)%6])
    interior_lights(m,inner)


def chalkboard(m,x,y,yaw,ch,kind,lettering):
    with m.at((x,y,0),yaw):
        for xx in [-.38,.38]:m.beam((xx,-.2,0),(xx,.1,1.15),.065,.065,'arc_trim')
        m.box((0,-.05,.67),(.76,.065,.87),'arc_timber')
        m.box((0,-.1,.67),(.65,.025,.72),'mc_charcoal')
        lettering(m,ch,(0,-.125,.58),.6,color='arc_ivory')
        if kind=='tea':m.lathe((0,-.13,.36),[(0,0),(0,.09),(.07,.11),(.09,0)],'arc_ivory',8)
        else:m.box((0,-.13,.4),(.06,.012,.22),'arc_ivory');m.box((0,-.13,.44),(.2,.012,.06),'arc_ivory')
        m.collider((0,0,.6),(.8,.5,1.2))


def tub_plant(m,x,y,kind):
    m.lathe((x,y,0),[(0,0),(0,.40),(.5,.46),(.56,.46),(.56,.40),(.5,.0)],'mc_fascia',12)
    for z in [.12,.44]:m.lathe((x,y,z),[(0,.47),(.04,.47)],'arc_timber',12)
    m.lathe((x,y,.5),[(0,0),(0,.38),(.03,.38),(.03,0)],'soil',12)
    m.collider((x,y,.3),(.95,.95,.6))
    if kind=='tea':
        m.beam((x,y,.5),(x,y,1.95),.08,.08,'arc_timber')
        for k,(dx,dy,z,r,h,key) in enumerate([(.12,-.05,.9,.5,.4,'leaf'),(-.15,.1,1.15,.45,.38,'green_dark'),(.08,.12,1.42,.38,.36,'leaf'),(-.06,-.1,1.68,.28,.34,'green_dark'),(0,0,1.92,.16,.3,'leaf')]):
            m.lathe((x+dx,y+dy,z),[(0,0),(0,r),(h*.55,r*.5),(h,.03)],key,7)
    else:
        rr=random.Random(5)
        for k in range(4):
            a=k*1.7;dx=math.cos(a)*.18;dy=math.sin(a)*.18
            m.beam((x+dx,y+dy,.5),(x+dx*2,y+dy*2,2.0+.25*k),.045,.045,'green')
            for j in range(4):
                b=a+j*1.9;zz=1.1+j*.28+.1*k;bx=x+dx*1.6;by=y+dy*1.6
                p=[(bx,by,zz),(bx+math.cos(b)*.3,by+math.sin(b)*.3,zz+.08),(bx+math.cos(b)*.45,by+math.sin(b)*.45,zz+.02),(bx+math.cos(b)*.3,by+math.sin(b)*.3,zz-.05)]
                m.poly(p,'green');m.poly(p[::-1],'green_dark')


def bench_flowers(m,x,y,seed):
    v.bench(m,x,y,0,1.9)
    m.box((x,y,.58),(1.4,.4,.2),'arc_stone',.03)
    m.box((x,y,.68),(1.24,.27,.01),'soil')
    for dx in [-.4,.4]:arcade.flowers(m,x+dx,y,.68,seed+int(dx*10),root_spread=(.20,.12))


def side(m,s):
    u=-s   # local x of the street front is 8*u
    with m.at((s*HX,0,0),90*s):
        boards(m,-HY,HY)
        for x in [-7.89,-4,0,4,7.89]:m.box((x,-.13,3.35),(.22,.26,7.1),'mc_timber')
        for z in [1.66,3.55,6.82]:m.box((0,-.14,z),(D+.3,.28,.16),'mc_timber')
        koshi_window(m,u*6,-.02,2.4,1.8,1.1)
        v.door(m,u*-2,-.04,.1,1.2,2.2);pent(m,u*-2-1.3,u*-2+1.3,-.02,3.1,.9,.35,fh=.2)
        koshi_window(m,u*-6,-.02,2.4,1.2,1.0)
        for x in [u*6,u*-2,u*-6]:arcade.window(m,x,-.05,5.3,1.5,1.3)
        m.beam((u*7.6,-.36,.1),(u*7.6,-.36,6.6),.07,.07,'metal');m.beam((u*7.6,-.36,6.6),(u*7.6,-.9,6.62),.07,.07,'metal')
        # Gable frame (tie beam, king post, struts, collar) and louvred vents on the exposed end wall.
        top=zr(0);slope=(top-zr(HY))/HY
        m.box((0,-.14,7.25),(14.6,.22,.16),'mc_timber');m.box((0,-.14,(7.33+top-.4)/2),(.22,.22,top-.4-7.33),'mc_timber')
        for sx in [-1,1]:m.beam((sx*5.0,-.14,7.33),(0,-.14,top-.55),.15,.16,'mc_timber')
        m.box((0,-.14,9.3),(8.4,.22,.16),'mc_timber')
        for sx in [-1,1]:
            for xx,zz in [(sx*2.4,7.9),(sx*1.6,9.95)]:
                m.box((xx,-.09,zz),(1.2,.08,.7),'arc_timber')
                for x in frange(xx-.5,xx+.5,.125):m.box((x,-.15,zz),(.05,.06,.66),'mc_fascia')


def back(m):
    with m.at((0,HY,0),180):
        boards(m,-HX,HX)
        for x in [-10.89,-5.5,0,5.5,10.89]:m.box((x,-.13,3.35),(.22,.26,7.1),'mc_timber')
        for z in [1.66,3.55,6.82]:m.box((0,-.14,z),(W+.3,.28,.16),'mc_timber')
        v.door(m,2.8,-.04,.1,1.2,2.2);pent(m,1.4,4.2,-.02,3.1,.9,.35,fh=.2)
        for x in [-3,-8]:koshi_window(m,x,-.02,2.4,1.6,1.1)
        for x in [-8,-3,3,8]:arcade.window(m,x,-.05,5.3,1.5,1.3)
        m.beam((10.6,-.36,.1),(10.6,-.36,6.6),.07,.07,'metal');m.beam((10.6,-.36,6.6),(10.6,-.9,6.62),.07,.07,'metal')


def mushiko(m,xm,wm=8.7,zm=5.55,hm=1.6):
    """Long upper-storey lattice: amber glow behind thin slats, one mid rail, a 0.3 m timber sill and head."""
    m.box((xm,-8.08,zm),(wm+.3,.18,hm+.3),'mc_timber')
    m.box((xm,-8.23,zm),(wm,.05,hm),'mc_mushiko')
    for x in frange(xm-wm/2+.06,xm+wm/2-.06,.17):m.box((x,-8.31,zm),(.045,.075,hm),'mc_timber')
    m.box((xm,-8.33,zm),(wm,.10,.08),'mc_dark')
    for dz in [-1,1]:m.box((xm,-8.18,zm+dz*(hm/2+.15)),(wm+.5,.32,.3),'mc_timber')
    m.box((xm,-8.36,zm-hm/2-.30),(wm+.5,.06,.04),'mc_dark')


def build(name,variant,lettering):
    palette(variant);m=v.Mesh(name)
    tea=-1 if variant==0 else 1     # which side (sign of x) the tea shop takes
    # Foundation set back behind the charred boards, ground floor (open at the front, warm ochre inside), upper storey, roof.
    m.box((0,0,-.25),(W,D,.7),'mc_plinth');m.collider((0,0,-.25),(W,D,.7))
    m.box((0,3,1.55),(W,10,3.9),'mc_ochre');m.collider((0,3,1.55),(W,10,3.9))
    for s in [-1,1]:
        m.box((s*(HX-.15),-5,1.55),(.3,6,3.9),'mc_ochre2');m.collider((s*(HX-.15),-5,1.55),(.3,6,3.9))
    m.box((0,-4.85,3.4),(W,5.9,.25),'mc_dark')
    ET=zr(HY)-.02   # wall top closes up to the roof soffit so the attic never shows under the eave
    m.box((0,0,(G+ET)/2),(W,D,ET-G),'mc_plaster2');m.collider((0,0,(G+E)/2),(W,D,E-G))
    m.box((0,-HY-.03,(G+E)/2),(W-.3,.08,E-G),'mc_plaster')      # lighter ochre infill on the street face
    main_roof(m);side(m,-1);side(m,1);back(m)
    # Front line: dark posts, honey lintel and bracket arms, hisashi with eave caps and a broad fascia.
    for x in [0,-1.2,1.2,-3.6,3.6,-8.6,8.6,-HX,HX]:
        m.box((x,-7.88,1.6),(.28,.28,4.0),'mc_dark');m.collider((x,-7.88,1.6),(.28,.28,4.0))
        m.beam((x,-7.95,3.62),(x,-9.25,3.62),.14,.2,'mc_timber')
        m.beam((x,-7.95,2.95),(x,-9.1,3.55),.10,.12,'mc_timber')
    m.box((0,-7.9,3.45),(W+.34,.3,.22),'mc_timber')
    pent(m,-HX-.5,HX+.5,-HY,4.3,1.75,.6,caps=True,top='mc_tile_edge',fh=.26)
    for x in [-3.6,3.6,-8.6,8.6]:
        m.box((x,-4.85,1.55),(.16,5.8,3.9),'mc_ochre');m.collider((x,-4.85,1.55),(.16,5.8,3.9))
    # Upper storey timber frame and the long mushiko lattices.
    for x in [0,-1.15,1.15,-10.15,10.15,-HX,HX]:m.box((x,-8.12,5.55),(.22,.24,2.7),'mc_timber')
    m.box((0,-8.14,4.45),(W+.3,.22,.18),'mc_timber')
    m.box((0,-8.16,6.85),(W+.4,.28,.2),'mc_timber')
    for s in [-1,1]:mushiko(m,s*5.65)
    # The two shops, mirrored about x=0.
    for s in [-1,1]:
        kind='tea' if s==tea else 'kimono'
        cloth='mc_green' if kind=='tea' else 'mc_purple'
        text='お茶' if kind=='tea' else '呉服'
        xo=s*6.1
        sign_board(m,xo,text,lettering)
        koshi_bay(m,s*9.8)
        cabinet(m,s*2.4,kind)
        xb=s*.6
        m.box((xb,-7.5,1.55),(.9,.24,3.9),'mc_ochre2');m.box((xb,-7.58,.35),(.9,.1,1.5),'arc_timber')
        m.collider((xb,-7.5,1.55),(.9,.24,3.9))
        banner(m,xb,['お','茶'] if kind=='tea' else ['呉','服'],cloth,kind,lettering)
        # Open bay: raised honey-plank floor behind a stone step, noren under the lintel.
        m.box((xo,-4.3,.025),(4.8,4.7,.85),'mc_plank');m.box((xo,-6.62,.42),(4.8,.14,.12),'mc_fascia')
        m.collider((xo,-4.3,1.55),(4.8,4.7,3.9))
        # Three 15 cm risers connect the street to the recessed timber floor.
        m.box((xo,-8.7,-.075),(2.6,.9,.45),'mc_step');m.collider((xo,-8.7,-.075),(2.6,.9,.45))
        m.box((xo,-7.45,.10),(2.6,1.6,.40),'mc_plank');m.collider((xo,-7.45,.10),(2.6,1.6,.40))
        noren(m,xo,kind,cloth)
        with m.at((xo,0,0)):
            if kind=='tea':interior_tea(m,variant,-s)
            else:interior_kimono(m,variant,-s)
        # Corner lantern on a bracket, street props inside the apron.
        arcade.lantern(m,s*10.4,-8.75,2.45,.55)
        m.beam((s*10.85,-7.9,3.5),(s*10.4,-8.75,3.5),.07,.08,'mc_dark')
        tub_plant(m,s*10.45,-9.55,kind)
        chalkboard(m,s*4.4,-9.3,-12*s,'茶' if kind=='tea' else '呉',kind,lettering)
        bench_flowers(m,s*8.0,-9.1,3+variant*7+(s+1))
    return m
