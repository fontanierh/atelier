"""Showa-era corner cafe block: chamfered corner entrance, arched shopfront under a striped awning, copper-green hip roof."""
import math,random
from village import build as v
from hidamari import arcade

ASSETS={'HD_Shop_04':0,'HD_Shop_12':1}
W,D=21.6,15.6;XL=XR=W/2;YF=YB=D/2;CUT=3.6           # wall footprint and the 45-degree corner cut
Z1,Z2,EAVE=4.3,7.5,10.2                              # storey lines and the roof eave
PITCH=.55                                            # hip roof rise per metre of run (ridge ~ EAVE+4.8)
K=1+1/math.sqrt(2);Q=math.sqrt(2)-1
CH=(-XL+CUT/2,-YF+CUT/2);HL=CUT/math.sqrt(2)         # chamfer midpoint and half length
ZF2,ZF3=6.0,8.85                                     # sash centres, floors 2 and 3


def outline(o):
    """Pentagon footprint offset outward by o (wall line at o=0), counter-clockwise from above."""
    xl,xr,yf,yb=-XL-o,XR+o,-YF-o,YB+o;c=CUT+o*(2-math.sqrt(2))
    return [(xl+c,yf),(xr,yf),(xr,yb),(xl,yb),(xl,yf+c)]


def band(m,o,z0,z1,key,chamfer=True):
    pts=outline(o);n=5 if chamfer else 4
    for i in range(n):
        a=pts[i];b=pts[(i+1)%5]
        m.poly([(a[0],a[1],z0),(b[0],b[1],z0),(b[0],b[1],z1),(a[0],a[1],z1)],key)
    if chamfer:
        m.poly([(x,y,z1) for x,y in pts],key);m.poly([(x,y,z0) for x,y in reversed(pts)],key)
    else:
        inner=outline(0)
        for i in range(4):
            a,b,c,d=pts[i],pts[i+1],inner[i+1],inner[i]
            m.poly([(a[0],a[1],z1),(b[0],b[1],z1),(c[0],c[1],z1),(d[0],d[1],z1)],key)


def arch_pts(x,z0,w,zs,n=10):
    """Round-arched opening outline in the (x,z) plane, counter-clockwise seen from -Y."""
    r=w/2;pts=[(x-r,z0),(x+r,z0),(x+r,zs)]
    for i in range(1,n):
        a=math.pi*i/n;pts.append((x+r*math.cos(a),zs+r*math.sin(a)))
    pts.append((x-r,zs));return pts


def arc(x,zs,r,n=10):
    """Semicircle points from the left springing to the right one, over the top."""
    return [(x+r*math.cos(math.pi-math.pi*i/n),zs+r*math.sin(math.pi-math.pi*i/n)) for i in range(n+1)]


def ring(m,x,z0,zs,r0,r1,y,key,n=10):
    """Arch-shaped frame band (two jambs and a semicircular head) between radii r0 and r1, in the plane y."""
    for s in (-1,1):
        q=[(x+s*r0,y,z0),(x+s*r1,y,z0),(x+s*r1,y,zs),(x+s*r0,y,zs)]
        m.poly(q if s>0 else q[::-1],key)
    a0=arc(x,zs,r0,n);a1=arc(x,zs,r1,n)
    for i in range(n):
        m.poly([(a0[i][0],y,a0[i][1]),(a0[i+1][0],y,a0[i+1][1]),(a1[i+1][0],y,a1[i+1][1]),(a1[i][0],y,a1[i][1])],key)


def wall_face(m,x0,x1,zt,openings,split=Z1):
    """Stucco face at y=0 from x0 to x1: solid above the split, built around round-arched openings (x,r,z0,zs) below."""
    m.poly([(x0,0,split),(x1,0,split),(x1,0,zt),(x0,0,zt)],'cc_plaster')
    edges=[x0]+[e for (x,r,z0,zs) in openings for e in (x-r,x+r)]+[x1]
    for i in range(0,len(edges),2):
        a,b=edges[i],edges[i+1]
        m.poly([(a,0,-.4),(b,0,-.4),(b,0,split),(a,0,split)],'cc_plaster')
    for x,r,z0,zs in openings:
        m.poly([(x-r,0,-.4),(x+r,0,-.4),(x+r,0,z0),(x-r,0,z0)],'cc_plaster')
        ac=arc(x,zs,r)
        for (xa,za),(xb,zb) in zip(ac[:-1],ac[1:]):
            m.poly([(xa,0,za),(xb,0,zb),(xb,0,split),(xa,0,split)],'cc_plaster')


def hip_roof(m,z0,e=.95,p=PITCH,key='cc_roof',lift=.07):
    xl,xr,yf,yb=-XL-e,XR+e,-YF-e,YB+e;cc=CUT+e*(2-math.sqrt(2));dh=(yb-yf)/2
    out=outline(e)
    # Cream soffit and one thin cream fascia box all round: no sky through the eaves.
    m.poly([(x,y,z0-.18) for x,y in reversed(out)],'cc_surround')
    for i in range(5):
        a=out[i];b=out[(i+1)%5]
        m.poly([(a[0],a[1],z0-.18),(b[0],b[1],z0-.18),(b[0],b[1],z0),(a[0],a[1],z0)],'arc_trim')
    def ends(face,o):
        if face=='front':
            xa=xl+cc+Q*o if o<K*cc else xl+o
            return (xa,yf+o),(xr-o,yf+o)
        if face=='right':return (xr-o,yf+o),(xr-o,yb-o)
        if face=='back':return (xr-o,yb-o),(xl+o,yb-o)
        if face=='left':
            ya=yf+cc+Q*o if o<K*cc else yf+o
            return (xl+o,yb-o),(xl+o,ya)
        if o>K*cc+1e-3:return None
        return (xl+o,yf+cc+Q*o),(xl+cc+Q*o,yf+o)
    offs=sorted(set([round(i*.4,4) for i in range(int(dh/.4)+1)]+[round(K*cc,4),round(dh,4)]))
    offs=[o for o in offs if o<=dh+1e-6]
    # Tile rows as stepped wedges: each row is thick at its lower edge (a riser) and tapers into the next.
    for face in ('front','right','back','left','cham'):
        for o0,o1 in zip(offs[:-1],offs[1:]):
            e0=ends(face,o0);e1=ends(face,o1)
            if e0 is None or e1 is None:continue
            (L0,R0),(L1,R1)=e0,e1;zl=z0+p*o0;zh=z0+p*o1
            m.poly([(*L0,zl),(*R0,zl),(*R0,zl+lift),(*L0,zl+lift)],'cc_roof_shade')
            m.poly([(*L0,zl+lift),(*R0,zl+lift),(*R1,zh),(*L1,zh)],v.color_variant(key,.06))
    S1=(xl+cc,yf,z0);S2=(xl,yf+cc,z0);A=(xl+K*cc,yf+K*cc,z0+p*K*cc);L=(xl+dh,0,z0+p*dh);R=(xr-dh,0,z0+p*dh)
    for a,b in [(S1,A),(S2,A),(A,L),((xr,yf,z0),R),((xr,yb,z0),R),((xl,yb,z0),L),(L,R)]:
        m.beam((a[0],a[1],a[2]+.05),(b[0],b[1],b[2]+.05),.25,.14,'cc_roof_dark')
    m.box((0,0,z0+p*dh+.10),(xr-xl-2*dh+.3,.25,.18),'cc_roof_dark',.03)
    return p


def wall_lantern(m,x,z):
    m.beam((x,-.02,z+.22),(x,-.36,z+.22),.05,.05,'cc_iron')
    m.box((x,-.36,z+.24),(.30,.30,.05),'cc_iron');m.box((x,-.36,z-.19),(.30,.30,.05),'cc_iron')
    m.box((x,-.36,z),(.24,.24,.36),'arc_paper')
    m.box((x,-.36,z+.30),(.06,.06,.08),'cc_iron')


def cup(m,x,y,z,s,key='cream'):
    m.poly([(x-.34*s,y,z-.28*s),(x+.34*s,y,z-.28*s),(x+.44*s,y,z+.26*s),(x-.44*s,y,z+.26*s)],key)
    m.box((x,y+.01,z-.34*s),(1.15*s,.02,.08*s),key)
    m.beam((x+.42*s,y,z+.12*s),(x+.68*s,y,z+.04*s),.07*s,.02,key)
    m.beam((x+.68*s,y,z+.04*s),(x+.66*s,y,z-.14*s),.07*s,.02,key)
    m.beam((x+.66*s,y,z-.14*s),(x+.36*s,y,z-.22*s),.07*s,.02,key)
    for dx in (-.14,.10):
        m.poly([(x+dx*s,y,z+.34*s),(x+(dx+.09)*s,y,z+.34*s),(x+(dx+.14)*s,y,z+.62*s),(x+(dx+.05)*s,y,z+.62*s)],key)


def disc(m,x,y,z,r):
    n=20
    m.poly([(x+r*math.cos(i*math.tau/n),y,z+r*math.sin(i*math.tau/n)) for i in range(n)],'cc_iron')
    m.poly([(x+r*.36*math.cos(i*math.tau/n),y-.012,z+r*.36*math.sin(i*math.tau/n)) for i in range(n)],'rust')
    m.poly([(x+r*.08*math.cos(i*math.tau/n),y-.02,z+r*.08*math.sin(i*math.tau/n)) for i in range(n)],'cream')


def arch(m,x,z0,w,zs,kind,seed,depth=1.05):
    if kind==3:depth=1.35
    """Tall round-arched shopfront: cream surround ring with keystone, brown frame ring, an open lit alcove
    with a display shelf behind the plane of the glass, a centre mullion and a fan over the transom."""
    r=w/2
    ring(m,x,z0-.22,zs,r+.15,r+.35,-.03,'cc_surround')
    ring(m,x,z0-.08,zs,r,r+.15,-.06,'arc_timber')
    m.box((x,-.10,zs+r+.05),(.30,.16,.42),'cc_surround')
    pts=arch_pts(x,z0,w,zs)
    for (xa,za),(xb,zb) in zip(pts,pts[1:]+pts[:1]):
        q=[(xa,0,za),(xb,0,zb),(xb,depth,zb),(xa,depth,za)];m.poly(q,'cc_surround');m.poly(q[::-1],'cc_surround')
    m.poly([(px,depth,pz) for px,pz in pts],'cc_glow')
    if kind==3:
        cafe_table(m,x,.60)
        for sx,yaw in ((-.60,-90),(.60,90)):chair(m,x+sx,.58,yaw)
        m.box((x,depth-.10,1.15),(w-.2,.18,.06),'arc_trim')
        for k in range(3):m.lathe((x-.6+k*.6,depth-.10,1.18),[(0,.09),(.09,.11),(.16,.05),(.17,0)],'arc_ivory',8)
    else:arcade.shelf(m,x,.62,kind,seed)
    m.box((x,-.06,(z0+zs)/2),(.08,.08,zs-z0),'arc_trim')
    m.box((x,-.06,zs),(w,.08,.10),'arc_trim')
    for a in (45,90,135):m.beam((x,-.06,zs),(x+r*math.cos(math.radians(a)),-.06,zs+r*math.sin(math.radians(a))),.06,.06,'arc_trim')
    m.box((x,-.17,z0-.10),(w+.5,.36,.16),'cc_surround')


def sash(m,x,z,w=.80,h=1.75):
    m.box((x,-.03,z),(w+.36,.07,h+.36),'cc_surround')
    m.box((x,-.10,z),(w+.14,.09,h+.14),'arc_timber')
    m.box((x,-.15,z),(w,.04,h),'cc_glass')
    m.box((x,-.18,z),(.06,.05,h),'arc_trim')
    m.box((x,-.18,z+.04),(w+.02,.05,.08),'arc_trim')
    for dz in (h*.27,-h*.25):m.box((x,-.18,z+dz),(w+.02,.05,.05),'arc_trim')


def pair(m,x,z,rail=True):
    """Paired sash windows on a projecting sill, with a thin iron balcony rail."""
    for dx in (-.52,.52):sash(m,x+dx,z)
    zb=z-.875
    m.box((x,-.24,zb-.10),(2.2,.52,.16),'cc_surround')
    if not rail:return
    for xx in (-1.0,0,1.0):m.box((x+xx,-.44,zb+.42),(.06,.06,.85),'cc_iron')
    for zz in (zb+.82,zb+.40):m.box((x,-.44,zz),(2.0,.05,.05),'cc_iron')
    for k in range(1,8):
        xx=-1.0+k*.25
        if abs(xx)>.05:m.box((x+xx,-.44,zb+.42),(.035,.035,.78),'cc_iron')


def flat_door(m,x,w=1.0,h=2.6,shop=False,sign=None,lettering=None,size=.9):
    m.box((x,-.03,h/2+.1),(w+.4,.06,h+.3),'cc_surround')
    m.box((x,-.08,h/2+.05),(w+.16,.10,h+.16),'arc_timber')
    m.box((x,-.13,h/2+.05),(w,.05,h),'arc_shopglass' if shop else 'arc_trim')
    m.box((x,-.16,h/2+.05),(.06,.05,h),'arc_trim');m.box((x,-.16,h*.45),(w,.05,.08),'arc_trim')
    m.box((x+w*.3,-.19,1.05),(.05,.06,.25),'metal')
    m.box((x,-.28,-.17),(w+.5,.6,.46),'cc_stone');m.collider((x,-.28,-.17),(w+.5,.6,.46))
    if sign:
        m.box((x,-.12,h+.55),(w+.7,.14,.55),'cc_sign')
        lettering(m,sign,(x,-.21,h+.55-.17*size),size,color='cream')


def awning(m,x0,x1,z,key_a,key_b,depth=1.3,drop=.45):
    """Striped canvas awning from x0 to x1 (x0<x1), with a valance on an iron rod and iron arms."""
    n=max(2,round((x1-x0)/.5));sw=(x1-x0)/n
    for i in range(n):
        xa=x0+i*sw;xb=xa+sw;key=key_a if i%2==0 else key_b
        p=[(xa,-.02,z),(xb,-.02,z),(xb,-depth,z-drop),(xa,-depth,z-drop)]
        m.poly(p,key);m.poly(p[::-1],key)
        m.box(((xa+xb)/2,-depth-.02,z-drop-.13),(sw+.005,.04,.26),key)
    m.beam((x0-.03,-depth-.02,z-drop-.28),(x1+.03,-depth-.02,z-drop-.28),.06,.06,'cc_iron')
    na=max(1,round((x1-x0)/3.2))
    for xx in [x0+.3+i*(x1-x0-.6)/na for i in range(na+1)]:
        m.beam((xx,-.06,z-1.05),(xx,-depth+.08,z-drop-.03),.06,.06,'cc_iron')
        m.beam((xx,-.06,z-.05),(xx,-depth+.08,z-drop-.03),.05,.05,'cc_iron')


def vent(m,x,z):
    m.box((x,-.07,z),(.6,.14,.5),'metal')
    for k in range(3):m.box((x,-.15,z-.14+k*.14),(.54,.04,.05),'cc_iron')


def pipe(m,x,z1,z2):
    m.beam((x,-.16,z1),(x,-.16,z2),.09,.09,'arc_trim')
    m.beam((x,-.16,z2),(x,-.02,z2+.3),.09,.09,'arc_trim')
    for zz in (z1+1.5,z2-1.5):m.box((x,-.09,zz),(.15,.15,.10),'arc_trim')


def planter(m,x,y,seed):
    m.box((x,y,.21),(1.8,.55,.42),'arc_trim',.03)
    m.box((x,y,.43),(1.86,.6,.06),'arc_timber')
    m.box((x,y,.45),(1.7,.45,.03),'soil')
    for j,dx in enumerate((-.42,.42)):arcade.flowers(m,x+dx,y,.46,seed*7+j,root_spread=(.37,.17))
    m.collider((x,y,.22),(1.8,.55,.46))


def bicycle(m,x,y,yaw):
    with m.at((x,y,0),yaw):
        for cx in (-.56,.56):
            n=14;pts=[(cx+.34*math.cos(i*math.tau/n),0,.34+.34*math.sin(i*math.tau/n)) for i in range(n)]
            for i in range(n):m.beam(pts[i],pts[(i+1)%n],.045,.045,'cc_iron')
            for i in range(3):
                a=i*math.pi/3;m.beam((cx+.3*math.cos(a),0,.34+.3*math.sin(a)),(cx-.3*math.cos(a),0,.34-.3*math.sin(a)),.02,.02,'metal')
            m.box((cx,0,.34),(.07,.09,.07),'metal')
        f='cc_bike'
        m.beam((.45,0,.78),(0,0,.38),.04,.04,f);m.beam((0,0,.38),(-.16,0,.90),.04,.04,f)
        m.beam((-.16,0,.90),(.45,0,.80),.04,.04,f);m.beam((-.16,0,.90),(-.56,0,.34),.035,.035,f)
        m.beam((0,0,.38),(-.56,0,.34),.035,.035,f);m.beam((.45,0,.80),(.56,0,.34),.035,.035,f)
        m.beam((.45,0,.78),(.50,0,.98),.035,.035,'metal');m.beam((.50,-.24,.98),(.50,.24,.98),.03,.03,'metal')
        m.box((-.18,0,.93),(.28,.16,.05),'arc_timber');m.box((0,0,.38),(.12,.16,.04),'metal')
        m.box((.74,0,.86),(.32,.36,.26),'clay');m.beam((.74,0,.86),(.55,0,.80),.03,.03,'metal')
        m.beam((-.1,.05,.36),(-.1,.10,.02),.03,.03,'metal')
        m.collider((0,0,.5),(1.9,.5,1.0))


def cafe_table(m,x,y):
    m.lathe((x,y,0),[(0,0),(.01,.30),(.04,.30),(.07,.04),(.66,.04),(.66,.0)],'cc_iron',12)
    m.lathe((x,y,0),[(.66,0),(.66,.38),(.72,.38),(.72,0)],'arc_timber',14)
    m.collider((x,y,.36),(.8,.8,.72))


def chair(m,x,y,yaw):
    with m.at((x,y,0),yaw):
        m.lathe((0,0,0),[(.43,0),(.43,.22),(.47,.22),(.47,0)],'arc_timber',10)
        for sx in (-1,1):
            for sy in (-1,1):m.beam((sx*.15,sy*.15,.0),(sx*.19,sy*.19,.43),.03,.03,'arc_trim')
        for sx in (-1,1):
            m.beam((sx*.17,.18,.43),(sx*.17,.23,.85),.03,.03,'arc_trim')
            m.beam((sx*.17,.23,.85),(sx*.08,.25,.96),.03,.03,'arc_trim')
        m.beam((-.08,.25,.96),(.08,.25,.96),.03,.03,'arc_trim')
        m.beam((0,.21,.47),(0,.24,.93),.025,.025,'arc_trim')
        m.collider((0,0,.48),(.5,.5,.96))


def aboard(m,x,y,yaw,lettering,variant):
    with m.at((x,y,.05),yaw):
        for sx in (-.38,.38):
            m.beam((sx,-.22,0),(sx,.02,1.15),.06,.06,'arc_trim');m.beam((sx,.24,0),(sx,.02,1.15),.06,.06,'arc_trim')
        m.box((0,-.05,.67),(.76,.06,.9),'arc_timber');m.box((0,-.10,.67),(.66,.025,.76),'arc_glass')
        if variant==0:
            lettering(m,'珈琲',(0,-.14,.78),.9,color='arc_ivory');cup(m,0,-.13,.45,.42,'arc_ivory')
        else:
            lettering(m,'♪',(0,-.14,.62),1.2,color='arc_ivory');lettering(m,'レコード',(0,-.14,.34),.5,color='arc_ivory')
        m.collider((0,0,.58),(.8,.5,1.15))


def crates(m,x,y):
    for dx in (-.5,.5):
        m.box((x+dx,y,.28),(.92,.55,.5),'arc_trim',.02)
        for k in range(3):m.box((x+dx,y-.29,.12+k*.16),(.9,.03,.10),'arc_timber')
        for k in range(8):
            m.box((x+dx-.36+k*.1,y,.46),(.035,.36,.36),['cc_iron','rust','blue','cream'][k%4])
    m.collider((x,y,.28),(1.9,.55,.6))


def build(name,variant,lettering):
    arcade.palette()
    for k,c in (('cream',(.66,.57,.41)),('blue',(.08,.19,.25)),('brick',(.31,.12,.055))):v.PALETTE.setdefault(k,c)
    v.PALETTE.update({
        'cc_plaster':(.54,.47,.33) if variant==0 else (.52,.47,.36),
        'cc_surround':(.62,.56,.43),'cc_base':(.40,.33,.22),'cc_stone':(.30,.27,.21),
        'cc_roof':(.19,.33,.22) if variant==0 else (.17,.29,.26),'cc_roof_dark':(.11,.19,.13),
        'cc_roof_shade':(.14,.25,.17) if variant==0 else (.13,.22,.20),
        'cc_red':(.40,.09,.04),'cc_green':(.08,.20,.11),'cc_white':(.62,.57,.46),
        'cc_iron':(.045,.045,.05),'cc_sign':(.09,.045,.02),'cc_bike':(.12,.30,.15),
        'cc_glass':(.06,.05,.04),'cc_glow':(.28,.15,.06)})
    stripe='cc_red' if variant==0 else 'cc_green'
    corner_text,side_text='喫茶','レコード'
    if variant==1:corner_text,side_text=side_text,corner_text
    side_kind=0 if variant==0 else 1
    m=v.Mesh(name)

    # Shell: chamfered stucco block (front and left faces are built around their arched openings below),
    # plinth, a dark wood shop fascia at Z1, a cream storey band at Z2, thin cream quoins.
    pts=outline(0)
    for i in (1,2):
        a,b=pts[i],pts[i+1]
        m.poly([(a[0],a[1],-.4),(b[0],b[1],-.4),(b[0],b[1],EAVE+.2),(a[0],a[1],EAVE+.2)],'cc_plaster')
    m.poly([(x,y,EAVE+.2) for x,y in pts],'cc_plaster')
    m.collider((1.8,0,5.2),(18,15.6,11.4));m.collider((-9,1.8,5.2),(3.6,12,11.4))
    band(m,.18,-.58,-.05,'cc_stone',chamfer=False)
    band(m,.10,-.4,.6,'cc_base',chamfer=False)
    band(m,.16,Z1-.05,Z1+.45,'arc_timber')
    band(m,.10,Z2-.05,Z2+.15,'cc_surround')
    for x,y in [(XR,-YF),(XR,YB),(-XL,YB),(pts[0][0],-YF),(-XL,pts[4][1])]:
        m.box((x,y,(EAVE-.4)/2),(.28,.28,EAVE+.4),'cc_surround')
    p=hip_roof(m,EAVE)

    # Rooftop iron signboard above the ridge (posts, braces, a white board with a dark border, lettered both
    # sides), plus a water tank and a flue for the silhouette.
    zt=EAVE+p*8.75;zc=zt+1.35
    for sx in (-3.2,3.2):
        for sy in (-.28,.28):m.beam((sx,sy,zt-.6),(sx,sy,zt+2.45),.13,.13,'cc_iron')
        m.beam((sx,-.28,zt+2.45),(sx,.28,zt+2.45),.09,.09,'cc_iron')
        for sy in (-1,1):m.beam((sx,sy*.28,zt+.9),(sx*1.35,sy*1.6,zt-1.4),.08,.08,'cc_iron')
    for sy in (-.28,.28):
        m.beam((-3.2,sy,zt+2.45),(3.2,sy,zt+2.45),.09,.09,'cc_iron');m.beam((-3.2,sy,zt+.4),(3.2,sy,zt+.4),.09,.09,'cc_iron')
    m.box((0,0,zc),(6.6,.20,1.8),'cc_sign');m.box((0,0,zc),(6.35,.30,1.56),'cc_white')
    for yaw in (0,180):
        with m.at((0,0,0),yaw):
            lettering(m,'喫茶',(-1.95,-.16,zc-.34),1.9,color='cc_sign');cup(m,-.15,-.165,zc+.02,.72,'cc_sign')
            lettering(m,'レコード',(1.65,-.16,zc-.30),1.7,color='cc_sign')
    tx,ty=-5.2,4.4
    for sx in (-.55,.55):
        for sy in (-.55,.55):m.beam((tx+sx,ty+sy,EAVE+1.5),(tx+sx*.8,ty+sy*.8,EAVE+3.2),.08,.08,'cc_iron')
    m.lathe((tx,ty,0),[(EAVE+3.1,0),(EAVE+3.1,.8),(EAVE+4.3,.8),(EAVE+4.4,.55),(EAVE+4.45,0)],'metal',14)
    m.lathe((6.6,4.4,0),[(EAVE+1.8,.16),(EAVE+3.6,.16),(EAVE+3.6,.24),(EAVE+3.75,.24),(EAVE+3.75,0)],'metal',10)

    # Front (long street face): five arched shopfronts with lit displays, striped awning, a stair door at the end.
    with m.at((0,-YF,0),0):
        xs=[-4.7,-1.6,1.5,4.6,7.7]
        wall_face(m,pts[0][0],XR,EAVE+.2,[(x,1.05,.75,2.6) for x in xs])
        for i,x in enumerate(xs):arch(m,x,.75,2.1,2.6,3 if variant==0 else 0,11+i)
        flat_door(m,9.8,.95,2.6)
        awning(m,-6.75,10.35,4.05,stripe,'cc_white')
        for z in (ZF2,ZF3):
            for x in (-5.6,-1.4,2.8,7.0):pair(m,x,z)
            sash(m,9.8,z)
        pipe(m,10.55,.1,EAVE-.55)
        for x in (1.5,4.6):planter(m,x,-.62,int(x*3))
        if variant==1:crates(m,-1.6,-.72)

    # Chamfered corner: recessed glazed double door with a fanlight, lanterns, fascia sign, balconies above.
    with m.at((CH[0],CH[1],0),-45):
        zs,zt2,r,dp=2.6,EAVE+.2,1.1,.62
        for sx in (-1,1):
            xa,xb=(-HL,-r) if sx<0 else (r,HL)
            m.poly([(xa,0,-.4),(xb,0,-.4),(xb,0,zt2),(xa,0,zt2)],'cc_plaster')
            m.box((sx*1.85,-.10,.03),(1.5,.2,1.15),'cc_base')
        a=arc(0,zs,r)
        for (xa,za),(xb,zb) in zip(a[:-1],a[1:]):
            m.poly([(xa,0,za),(xb,0,zb),(xb,0,zs+r),(xa,0,zs+r)],'cc_plaster')
            q=[(xa,0,za),(xb,0,zb),(xb,dp,zb),(xa,dp,za)];m.poly(q,'cc_surround');m.poly(q[::-1],'cc_surround')
        m.poly([(-r,0,zs+r),(r,0,zs+r),(r,0,zt2),(-r,0,zt2)],'cc_plaster')
        for sx in (-r,r):
            q=[(sx,0,-.1),(sx,dp,-.1),(sx,dp,zs),(sx,0,zs)];m.poly(q,'cc_surround');m.poly(q[::-1],'cc_surround')
        ring(m,0,-.1,zs,r+.12,r+.45,-.04,'cc_surround')
        ring(m,0,-.1,zs,r,r+.12,-.07,'arc_timber')
        m.box((0,-.10,zs+r+.06),(.34,.18,.5),'cc_surround')
        # Two glazed leaves on a stone step, transom and a fanlight with three radial mullions.
        # Fill the full 2*r opening: narrower leaves exposed daylight through
        # both jambs, especially in the shaded corner entrance.
        for sx in (-r/2,r/2):
            m.box((sx,dp-.06,1.375),(r,.08,2.45),'arc_timber')
            m.box((sx,dp-.12,1.7),(.6,.05,1.6),'arc_shopglass')
            m.box((sx,dp-.12,.5),(.6,.05,.45),'arc_trim')
            m.box((sx*.3,dp-.17,1.1),(.05,.07,.35),'metal')
        m.box((0,dp-.06,zs),(2*r,.08,.10),'arc_trim')
        m.poly([(px,dp-.08,pz) for px,pz in reversed(arc(0,zs,r-.02,12))],'arc_shopglass')
        for ang in (45,90,135):m.beam((0,dp-.11,zs),(r*math.cos(math.radians(ang)),dp-.11,zs+r*math.sin(math.radians(ang))),.05,.05,'arc_trim')
        m.box((0,.31,-.12),(2*r,.62,.54),'cc_stone');m.collider((0,.31,-.12),(2*r,.62,.54))
        m.box((0,-.5,-.125),(3.0,1.0,.55),'cc_stone');m.collider((0,-.5,-.125),(3.0,1.0,.55))
        m.collider((-1.83,1.28,5.2),(1.45,2.55,11.4));m.collider((1.83,1.28,5.2),(1.45,2.55,11.4));m.collider((0,1.55,5.2),(2.3,2.0,11.4))
        for sx in (-1.8,1.8):wall_lantern(m,sx,2.55)
        m.box((0,-.19,Z1+.2),(3.8,.14,1.05),'cc_surround')
        m.box((0,-.22,Z1+.2),(3.6,.16,.9),'cc_sign')
        if variant==0:lettering(m,corner_text,(-.55,-.33,Z1+.2-.28),1.7,color='cream');cup(m,1.0,-.335,Z1+.2,.7)
        else:lettering(m,corner_text,(-.5,-.33,Z1+.2-.22),1.4,color='cream');disc(m,1.3,-.335,Z1+.2,.32)
        for z in (ZF2,ZF3):pair(m,0,z)

    # Left side (exposed corner street): two arches, the second shop's door, blade banner, awning.
    with m.at((-XL,0,0),-90):
        wall_face(m,-YB,YF-CUT,EAVE+.2,[(-.4,1.05,.75,2.6),(2.6,1.05,.75,2.6)])
        for i,x in enumerate((2.6,-.4)):arch(m,x,.75,2.1,2.6,side_kind,21+i)
        flat_door(m,-3.4,1.2,2.6,shop=True,sign=side_text,lettering=lettering,size=.9 if variant==0 else 1.1)
        arcade.window(m,-6.3,-.02,2.0,1.2,1.5)
        awning(m,-4.4,3.75,4.05,stripe,'cc_white')
        for z in (ZF2,ZF3):
            for x in (1.9,-2.3):pair(m,x,z)
            sash(m,-6.3,z)
        pipe(m,-7.55,.1,EAVE-.55)
        # Both boxes follow the straight side wall, below the two shop arches.
        # A box on the chamfer inherited its -45 degree yaw and stuck diagonally
        # into the corner entrance instead of belonging to the shopfront.
        for x,seed in ((-.4,5),(2.6,9)):planter(m,x,-.62,seed)
        # Vertical blade banner hung off the corner pier on two iron bracket arms, lettered on both faces.
        bx=3.55
        for zz in (5.05,8.75):
            m.beam((bx,-.02,zz),(bx,-1.3,zz),.07,.07,'cc_iron');m.beam((bx,-.02,zz-.55),(bx,-.95,zz),.05,.05,'cc_iron')
        m.box((bx,-.9,6.9),(.06,.9,4.2),'cc_sign');m.box((bx,-.9,6.9),(.08,.78,4.08),'cc_white')
        items=['喫','茶','cup','レ','コ','bar','ド'] if variant==0 else ['レ','コ','bar','ド','disc','喫','茶']
        for sgn,yaw in ((1,90),(-1,-90)):
            with m.at((bx+sgn*.045,-.9,0),yaw):
                for j,it in enumerate(items):
                    z=8.55-j*.56
                    if it=='cup':cup(m,0,-.01,z-.05,.5,'cc_sign')
                    elif it=='disc':disc(m,0,-.01,z,.22)
                    elif it=='bar':m.box((0,-.01,z),(.07,.02,.38),'cc_sign')
                    else:lettering(m,it,(0,-.01,z-.25),1.5,color='cc_sign')

    # Right side: plain sash windows, a service door, vent and downpipe.
    with m.at((XR,0,0),90):
        for x in (-4.6,4.6):arcade.window(m,x,-.02,2.05,1.6,1.7)
        flat_door(m,0,1.0,2.4)
        vent(m,-6.9,3.4)
        for z in (ZF2,ZF3):
            for x in (-6.0,-2.0,2.0,6.0):pair(m,x,z,rail=(abs(x)<3))
        pipe(m,7.55,.1,EAVE-.55)

    # Back: kitchen door under a small pent roof, windows without balconies, vents.
    with m.at((0,YB,0),180):
        flat_door(m,0,1.1,2.4)
        pnt=[(-1.6,-.02,3.5),(1.6,-.02,3.5),(1.6,-1.0,3.05),(-1.6,-1.0,3.05)]
        m.poly(pnt,'cc_roof');m.poly(pnt[::-1],'arc_trim')
        m.beam((-1.6,-1.0,3.05),(1.6,-1.0,3.05),.12,.12,'arc_trim')
        for sx in (-1.4,1.4):m.beam((sx,-.05,2.6),(sx,-.9,3.0),.08,.08,'arc_trim')
        for x in (-5.5,5.5):arcade.window(m,x,-.02,2.05,1.5,1.6)
        for x in (-8.6,8.6):vent(m,x,2.4)
        for z in (ZF2,ZF3):
            for x in (-7.5,-3.0,3.0,7.5):pair(m,x,z,rail=False)
        pipe(m,-10.55,.1,EAVE-.55)

    # Street props inside the sidewalk apron; the lab's planter spot near x=-9 stays clear.
    if variant==0:
        cafe_table(m,-3.4,-9.3);chair(m,-4.35,-9.3,-90);chair(m,-2.45,-9.3,90)
        aboard(m,-6.3,-9.75,-12,lettering,0)
        bicycle(m,-7.0,-8.5,20)
    else:
        bicycle(m,-7.0,-8.5,20)
        aboard(m,-6.3,-9.75,-12,lettering,1)
        crates(m,6.4,-8.55)
    return m
