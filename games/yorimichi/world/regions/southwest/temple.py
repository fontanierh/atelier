"""The summit temple: a modest single-room hall (about 6 m wide) on a stepped stone plinth with a wide sweeping
indigo hip roof, cream plaster between vermilion columns, an open veranda with a two-rail balustrade, a long formal
stair with cheek walls down the hill (two runs and a landing), a bell pavilion, stone lanterns, pennants on a sagging
rope, layered-pad pines, a red maple, shrubs, grass and faceted boulders at the cliff edge.
Front faces -Y. Origin = ground at the summit; the plinth top is z=1.0, the stair ends at z=-1.6 around y=-12."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import math, random, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mesh import Mesh, PALETTE
R=random.Random(41)
def cv(key,amount=.05):
    f=R.uniform(1-amount,1+amount);return tuple(min(1,c*f) for c in PALETTE[key])
def lerp(a,b,t):return a+(b-a)*t

def site_ground(x,y):
    """Temple is placed 180 degrees around the authored island summit."""
    import island
    z=float(island.height(-x,island.SUMMIT[1]-y))-island.SUMMIT_Z
    if abs(x)<=6.5 and -4.5<=y<=6.5:z=max(z,.48)
    if abs(x)<=4.5 and -3<=y<=5:z=max(z,1.0)
    return z

# ---------------------------------------------------------------- roof
def temple_roof(m,w,d,eave,rise=2.2,over=1.5,lift=.45,thick=.22,ridge=.5,crest=True):
    """Hipped roof on a u/t grid: concave slope (steep at the ridge, flaring flat toward the eave), corners lifted,
    one flat indigo colour, thick fascia, warm rafter underside, lighter ridge cap with small forked ends."""
    W,D=w+2*over,d+2*over;rl=w*ridge
    def prof(t):return eave+rise*(1-t)**1.7
    NT,NU=3,6
    def P(side,u,t):
        # side 0/2: front(-y)/back(+y) slopes; 1/3: right(+x)/left(-x) hips
        kick=lift*t**3*(2*abs(u-.5))**2.2
        if side in (0,2):
            sy=-1 if side==0 else 1
            x=lerp(-rl/2+u*rl,-W/2+u*W,t);y=sy*t*D/2
        else:
            sx=1 if side==1 else -1
            x=sx*lerp(rl/2,W/2,t);y=lerp(0,-D/2+u*D,t)
        return (x,y,prof(t)+kick)
    for side in range(4):
        for i in range(NT):
            for j in range(NU):
                t0,t1=i/NT,(i+1)/NT;u0,u1=j/NU,(j+1)/NU
                q=[P(side,u0,t0),P(side,u1,t0),P(side,u1,t1),P(side,u0,t1)]
                if side in (0,3):q=q[::-1]
                if side==2 or side==1:pass
                # outward-facing winding: check with the face normal against the outward direction
                c=[sum(p[k] for p in q)/4 for k in range(3)]
                ax=(q[1][0]-q[0][0],q[1][1]-q[0][1],q[1][2]-q[0][2]);bx=(q[2][0]-q[0][0],q[2][1]-q[0][1],q[2][2]-q[0][2])
                n=(ax[1]*bx[2]-ax[2]*bx[1],ax[2]*bx[0]-ax[0]*bx[2],ax[0]*bx[1]-ax[1]*bx[0])
                if n[2]<0:q=q[::-1]
                m.poly(q,'roof_indigo')
                under=[(p[0],p[1],p[2]-thick) for p in q][::-1]
                m.poly(under,'wood_light')
    # fascia: thick eave board around the rim following the corner lift
    for side in range(4):
        for j in range(NU):
            a,b=P(side,j/NU,1),P(side,(j+1)/NU,1)
            m.beam((a[0],a[1],a[2]-thick/2),(b[0],b[1],b[2]-thick/2),thick+.02,.16,'eave_board')
    # rafters under the eave, warm brown, from the wall line to the eave
    for side in range(4):
        n=int((W if side in (0,2) else D)/.75)
        for j in range(1,n):
            u=j/n;a=P(side,u,.55);b=P(side,u,1.0)
            m.beam((a[0],a[1],a[2]-thick-.04),(b[0],b[1],b[2]-thick-.02),.10,.12,'wood_light')
    # ridge cap and small forked ends
    top=prof(0)
    m.box((0,0,top+.10),(rl+.4,.34,.26),'roof_cap',bevel=.04)
    if crest:
        for sx in (-1,1):
            m.beam((sx*(rl/2+.05),0,top+.2),(sx*(rl/2+.30),0,top+.55),.10,.12,'roof_cap')
            m.beam((sx*(rl/2+.30),-.12,top+.55),(sx*(rl/2+.42),-.16,top+.78),.06,.06,'roof_cap');m.beam((sx*(rl/2+.30),.12,top+.55),(sx*(rl/2+.42),.16,top+.78),.06,.06,'roof_cap')
        for x in (-rl/5,rl/5):m.beam((x,-.32,top+.22),(x,.32,top+.22),.10,.10,'wood_dark')

# ---------------------------------------------------------------- hall
def column(m,x,y,z0,h,r=.15):
    m.box((x,y,z0+.08),(.5,.5,.16),'granite_light',bevel=.03)
    m.lathe((x,y,z0+.16),[(0,r),(h-.16,r)],'vermilion',n=8)

def balustrade(m,a,b,z,h=.85):
    """two rails and square posts between a and b at floor height z"""
    ax,ay=a;bx,by=b;L=math.hypot(bx-ax,by-ay);n=max(1,int(L/.9))
    for k in range(n+1):
        t=k/n;m.beam((lerp(ax,bx,t),lerp(ay,by,t),z),(lerp(ax,bx,t),lerp(ay,by,t),z+h),.09,.09,'vermilion')
    m.beam((ax,ay,z+h),(bx,by,z+h),.11,.11,'vermilion');m.beam((ax,ay,z+h*.5),(bx,by,z+h*.5),.07,.07,'vermilion')

def lattice(m,cx,y,cz,w,h,depth_sign):
    """dark wooden lattice window with a cream panel behind (no glow)"""
    m.box((cx,y,cz),(w,.06,h),'wood_dark');m.box((cx,y+depth_sign*.02,cz),(w-.14,.04,h-.14),'plaster_cream')
    for k in range(int(w/.22)):m.box((cx-w/2+.11+k*.22,y+depth_sign*.05,cz),(.04,.03,h-.14),'wood')
    for k in range(int(h/.30)):m.box((cx,y+depth_sign*.05,cz-h/2+.15+k*.30),(w-.14,.03,.04),'wood')

def hall(m,w=6.0,d=4.8,z=1.0):
    """hall on the plinth top z: raised floor, veranda, cream walls, vermilion columns, roof"""
    fl=z+.55;ch=2.85;eave=fl+ch                                    # floor, column height, eave
    vw=1.05                                                       # veranda width
    # raised floor on short posts, veranda planks
    m.box((0,0,fl-.07),(w+2*vw,d+2*vw,.14),'wood_pale');m.collider((0,0,(z+fl)/2),(w+2*vw,d+2*vw,fl-z))
    for xx in [-w/2-vw+.3+i*(w+2*vw-.6)/6 for i in range(7)]:
        for yy in (-d/2-vw+.3,d/2+vw-.3):m.beam((xx,yy,z),(xx,yy,fl-.1),.14,.14,'wood_dark')
    for yy in [-d/2-vw+.3+i*(d+2*vw-.6)/4 for i in range(5)]:
        for xx in (-w/2-vw+.3,w/2+vw-.3):m.beam((xx,yy,z),(xx,yy,fl-.1),.14,.14,'wood_dark')
    # walls: cream plaster box, columns at the corners and thirds
    m.box((0,0,fl+ch/2),(w-.2,d-.2,ch),'plaster_cream');m.collider((0,0,fl+ch/2),(w,d,ch))
    for xx in (-w/2,-w/6,w/6,w/2):
        for yy in (-d/2,d/2):column(m,xx,yy,fl,ch)
    for yy in (0,):
        for xx in (-w/2,w/2):column(m,xx,yy,fl,ch)
    # outer veranda columns carrying the eave
    for xx in (-w/2-vw+.1,w/2+vw-.1):
        for yy in (-d/2-vw+.1,d/2+vw-.1):column(m,xx,yy,fl,ch,.13)
    for xx in (0,):
        for yy in (-d/2-vw+.1,d/2+vw-.1):column(m,xx,yy,fl,ch,.13)
    # tie beams at the head and the sill
    for zz in (fl+.35,fl+ch-.12):
        for yy in (-d/2,d/2):m.beam((-w/2,yy,zz),(w/2,yy,zz),.16,.16,'vermilion')
        for xx in (-w/2,w/2):m.beam((xx,-d/2,zz),(xx,d/2,zz),.16,.16,'vermilion')
    for yy in (-d/2-vw+.1,d/2+vw-.1):m.beam((-w/2-vw+.1,yy,fl+ch-.12),(w/2+vw-.1,yy,fl+ch-.12),.16,.16,'vermilion')
    for xx in (-w/2-vw+.1,w/2+vw-.1):m.beam((xx,-d/2-vw+.1,fl+ch-.12),(xx,d/2+vw-.1,fl+ch-.12),.16,.16,'vermilion')
    # front: dark plank sliding doors, lattice windows either side and at the back, a small noren-free doorway
    m.box((0,-d/2-.05,fl+1.1),(1.7,.08,2.1),'wood_dark')
    for k in range(6):m.box((-.75+k*.3,-d/2-.10,fl+1.1),(.06,.03,2.0),'wood')
    m.box((0,-d/2-.10,fl+1.1),(.05,.03,2.0),'wood_pale')
    for sx in (-1,1):lattice(m,sx*w*.33,-d/2-.06,fl+1.6,1.3,1.3,-1)
    for sx in (-1,1):lattice(m,sx*w*.33,d/2+.06,fl+1.6,1.3,1.3,1)
    lattice(m,0,d/2+.06,fl+1.6,1.3,1.3,1)
    for sx in (-1,1):
        with m.at((sx*(w/2),0,0),yaw=90):lattice(m,0,-sx*.06,fl+1.6,1.3,1.3,-sx)   # side windows in the wall plane
    # balustrade around the veranda with an opening for the steps at the front
    yf=-d/2-vw+.1;yb=d/2+vw-.1;xl=-w/2-vw+.1;xr=w/2+vw-.1
    balustrade(m,(xl,yf),(-1.0,yf),fl);balustrade(m,(1.0,yf),(xr,yf),fl)
    balustrade(m,(xl,yf),(xl,yb),fl);balustrade(m,(xr,yf),(xr,yb),fl);balustrade(m,(xl,yb),(xr,yb),fl)
    # small stair from the plinth to the veranda
    for i in range(3):m.box((0,yf-.2-i*.36,fl-.12-i*.17),(1.9,.38,.14),cv('granite_light',.05),bevel=.02)
    m.beam((-.95,yf-.1,fl+.05),(-.95,yf-1.1,z+.1),.10,.10,'vermilion');m.beam((.95,yf-.1,fl+.05),(.95,yf-1.1,z+.1),.10,.10,'vermilion')
    # paper lanterns under the front eave
    for xx in (-w/3,w/3):
        m.beam((xx,yf-.2,eave+.9),(xx,yf-.2,eave+.55),.02,.02,'rope');m.lathe((xx,yf-.2,eave+.2),[(0,.09),(.08,.17),(.28,.17),(.36,.09)],'paper',n=8)
    temple_roof(m,w+2*vw-.2,d+2*vw-.2,eave+.05,rise=2.1,over=1.35,lift=.5)
    return eave

# ---------------------------------------------------------------- props
def stone_lantern(m,x,y,z=0,h=1.5,yaw=0):
    with m.at((x,y,z),yaw):
        m.box((0,0,-.005),(.62,.62,.29),'granite',bevel=.02);m.box((0,0,.22),(.40,.40,.16),'granite_light',bevel=.02)
        m.lathe((0,0,.30),[(0,.12),(h*.42,.10)],'granite',n=8)
        m.box((0,0,h*.42+.36),(.34,.34,.12),'granite_light',bevel=.02)                 # middle platform
        m.box((0,0,h*.42+.62),(.36,.36,.40),'granite')                                 # fire box
        m.box((0,-.185,h*.42+.62),(.20,.02,.24),'paper');m.box((0,.185,h*.42+.62),(.20,.02,.24),'paper')
        m.box((-.185,0,h*.42+.62),(.02,.20,.24),'paper');m.box((.185,0,h*.42+.62),(.02,.20,.24),'paper')
        # square roof cap with an upturned edge
        m.poly([(-.36,-.36,h*.42+.84),(.36,-.36,h*.42+.84),(.36,.36,h*.42+.84),(-.36,.36,h*.42+.84)][::-1],'granite')
        for k in range(4):
            a=k*math.pi/2;b=a+math.pi/2
            m.poly([(.36*math.cos(a)*1.414*math.cos(math.pi/4)*1.0,.36*math.sin(a)*1.414,h*.42+.84),(.36*1.414*math.cos(b),.36*1.414*math.sin(b),h*.42+.84),(0,0,h*.42+1.06)] ,'granite_light')
        m.sphere((0,0,h*.42+1.12),.07,'granite',n=6,rings=3)

def bell_house(m,x,y,z,yaw=0):
    with m.at((x,y,z),yaw):
        m.box((0,0,.16),(2.6,2.6,.32),'granite',bevel=.02);m.box((0,0,.40),(2.1,2.1,.16),'granite_light',bevel=.02)
        for sx in (-1,1):
            for sy in (-1,1):column(m,sx*.8,sy*.8,.48,2.3,.11)
        for sx in (-1,1):m.beam((sx*.8,-.8,2.7),(sx*.8,.8,2.7),.13,.13,'vermilion');m.beam((-.8,sx*.8,2.7),(.8,sx*.8,2.7),.13,.13,'vermilion')
        m.beam((-.8,0,2.55),(.8,0,2.55),.14,.14,'wood_dark')
        m.beam((0,0,2.5),(0,0,2.2),.04,.04,'rope');m.lathe((0,0,.95),[(0,.30),(.12,.40),(.85,.42),(1.10,.32),(1.22,.14),(1.26,0)],'bronze',n=12)
        m.beam((-.95,.95,.48),(-.95,.95,1.5),.07,.07,'wood');m.beam((-.95,.95,1.5),(-.25,.35,1.25),.09,.09,'wood_pale')
        temple_roof(m,1.7,1.7,2.78,rise=1.0,over=.75,lift=.25,thick=.16,ridge=.45,crest=False)
        m.collider((0,0,1.6),(2.6,2.6,3.2))

def pennants(m,a,b,n=13,sag=.7):
    ax,ay,az=a;bx,by,bz=b
    for x,y,z in (a,b):m.beam((x,y,site_ground(x,y)-.08),(x,y,z+.15),.09,.09,'wood_dark');m.sphere((x,y,z+.18),.07,'wood_pale',n=6,rings=3)
    cols=['mustard','white','faded_blue','pennant_orange','white','mustard','faded_blue','white','pennant_orange','mustard','white','faded_blue','mustard']
    pts=[(lerp(ax,bx,k/n),lerp(ay,by,k/n),lerp(az,bz,k/n)-sag*math.sin(math.pi*k/n)) for k in range(n+1)]
    for p,q in zip(pts[:-1],pts[1:]):m.beam(p,q,.02,.02,'rope')
    dx,dy=bx-ax,by-ay;L=math.hypot(dx,dy);nx,ny=-dy/L,dx/L
    for k in range(n):
        p,q=pts[k],pts[k+1];cx,cy,cz=(p[0]+q[0])/2,(p[1]+q[1])/2,(p[2]+q[2])/2;hw=.11;h=.55
        ux,uy=(q[0]-p[0])/2*.75,(q[1]-p[1])/2*.75
        quad=[(cx-ux,cy-uy,cz),(cx+ux,cy+uy,cz),(cx+ux*.9+nx*.03,cy+uy*.9+ny*.03,cz-h),(cx-ux*.9+nx*.03,cy-uy*.9+ny*.03,cz-h)]
        m.poly(quad,cols[k%len(cols)]);m.poly(quad[::-1],cols[k%len(cols)])

def pine(m,x,y,z,h=5.0,yaw=0,seed=0):
    """layered-pad pine: a twisting trunk in four beams, short branches, each ending in a clump of two stacked pads"""
    r=random.Random(seed)
    with m.at((x,y,z),yaw):
        p=(0,0,-.3);pts=[p];lean=r.uniform(-.35,.35)
        for k in range(4):
            q=(p[0]+lean*(1+k*.4)+r.uniform(-.25,.25),p[1]+r.uniform(-.3,.3),p[2]+h/4*r.uniform(.85,1.1));m.beam(p,q,.30-k*.055,.30-k*.055,'wood_dark');p=q;pts.append(p)
        def pad(cx,cy,cz,rad):
            ring=[(cx+math.cos(a)*rad*(1+.22*math.sin(3*a+cx)),cy+math.sin(a)*rad*(1+.18*math.cos(2*a+cy)),cz+.05*math.sin(4*a)) for a in [i*2*math.pi/8 for i in range(8)]]
            top=[(q[0]*.6+cx*.4,q[1]*.6+cy*.4,q[2]+.26) for q in ring]
            m.poly(ring[::-1],'green_dark')                                   # underside
            for i in range(8):m.poly([ring[i],ring[(i+1)%8],top[(i+1)%8],top[i]],'green' if i%2 else 'green_dark')
            m.poly(top,'green')
        for k,base in enumerate(pts[1:]):
            for j in range(3 if k<3 else 2):
                ang=r.uniform(0,2*math.pi);dist=r.uniform(.5,1.3)*(1-.15*k)
                cx,cy,cz=base[0]+math.cos(ang)*dist,base[1]+math.sin(ang)*dist,base[2]+r.uniform(-.15,.25)
                m.beam(base,(cx,cy,cz),.11,.11,'wood_dark')
                pad(cx,cy,cz,r.uniform(.75,1.2)*(1-.1*k))
        pad(pts[-1][0],pts[-1][1],pts[-1][2]+.15,.8)

def maple(m,x,y,z,h=3.6,seed=3):
    r=random.Random(seed)
    with m.at((x,y,z)):
        m.beam((0,0,-.2),(.2,.1,h*.45),.22,.22,'wood_dark')
        for k in range(3):
            q=(r.uniform(-1,1),r.uniform(-1,1),h*.45+r.uniform(.6,1.4));m.beam((.2,.1,h*.45),q,.10,.10,'wood_dark')
            m.sphere(q,r.uniform(.8,1.2),'maple',n=7,rings=4,squash=.7)
        m.sphere((.2,.1,h*.45+1.2),1.5,'maple',n=8,rings=4,squash=.7)

def shrub(m,x,y,z,r=.6,key='shrub_yellow',seed=0):
    rr=random.Random(seed)
    for k in range(3):m.sphere((x+rr.uniform(-r*.6,r*.6),y+rr.uniform(-r*.6,r*.6),z+r*.5),r*rr.uniform(.6,.9),key,n=6,rings=3,squash=.8)

def boulder(m,x,y,z,s,seed=0,key='granite'):
    rr=random.Random(seed);n=6;rings=4
    with m.at((x,y,z),rr.uniform(0,360)):
        prof=[]
        for i in range(rings+1):
            t=i/rings;rad=s*math.sin(t*math.pi)*rr.uniform(.75,1.15)+ (0 if i in (0,rings) else .05)
            prof.append((-s*.8*math.cos(t*math.pi)*rr.uniform(.8,1.1),rad if 0<i<rings else 0))
        # jitter by building rings manually
        ringsxyz=[[(prof[i][1]*math.cos(a)*rr.uniform(.85,1.15),prof[i][1]*math.sin(a)*rr.uniform(.85,1.15),prof[i][0]) for a in [k*2*math.pi/n for k in range(n)]] for i in range(rings+1)]
        for a,b in zip(ringsxyz[:-1],ringsxyz[1:]):
            for k in range(n):m.poly([a[k],a[(k+1)%n],b[(k+1)%n],b[k]],cv(key if k%2 else 'granite_light',.07))
    m.collider((x,y,z),(s*1.6,s*1.6,s*1.4))

def paved_contact(x,y,margin=.12):
    """Exclude authored grass from the shelf, bellhouse and stair footprints."""
    if abs(x)<6.5+margin and -4.5-margin<y<6.5+margin:return True
    if abs(x)<2.0+margin and -12.5-margin<y<-4.5+margin:return True
    a=math.radians(-8);dx=x-5.6;dy=y+1.4
    return abs(dx*math.cos(a)+dy*math.sin(a))<1.32+margin and abs(-dx*math.sin(a)+dy*math.cos(a))<1.32+margin

def grass_patch(m,x,y,z,r,seed=0):
    rr=random.Random(seed)
    ring=[(x+math.cos(a)*r*rr.uniform(.6,1.2),y+math.sin(a)*r*rr.uniform(.6,1.2),z+.02) for a in [i*2*math.pi/7 for i in range(7)]]
    ring=[(px,py,site_ground(px,py)+.018) for px,py,_ in ring]
    colour=cv('grass_ochre',.08)
    # Triangulate the patch around its centre, omitting any triangle touching
    # paving instead of drawing ochre ground on top of the stone shelf.
    centre=(x,y,site_ground(x,y)+.018)
    for p,q in zip(ring,ring[1:]+ring[:1]):
        if not any(paved_contact(px,py) for px,py,_ in (centre,p,q)):
            m.poly([centre,p,q],colour)
    for k in range(int(r*3)):
        gx,gy=x+rr.uniform(-r,r),y+rr.uniform(-r,r);gh=rr.uniform(.25,.5);z=site_ground(gx,gy)
        tipx=rr.uniform(-.1,.1);tipy=rr.uniform(-.1,.1)
        if paved_contact(gx,gy):continue
        m.poly([(gx-.06,gy,z),(gx+.06,gy,z),(gx+tipx,gy,z+gh)],'green');m.poly([(gx,gy-.06,z),(gx,gy+.06,z),(gx,gy+tipy,z+gh*.8)],'green_dark')

def stair(m,y0,z0,steps,rise,run,width,cheek=True):
    """descending stair toward -Y from (y0,z0); returns (y,z) at the bottom"""
    import island
    for i in range(steps):
        y=y0-(i+.5)*run; top=z0-i*rise
        ground=min(float(island.height(-x,island.SUMMIT[1]-yy))-island.SUMMIT_Z
                   for x in (-width/2,0,width/2) for yy in (y-run/2,y+run/2))
        bottom=min(top-rise,ground-.18)
        m.box((0,y,(top+bottom)/2),(width,run+.02,top-bottom),cv('granite_light' if i%2 else 'granite',.05))
        m.collider((0,y,(top+bottom)/2),(width,run+.02,top-bottom))
    yb,zb=y0-steps*run,z0-steps*rise
    if cheek:
        for sx in (-1,1):
            x=sx*(width/2+.18)
            q=[(x,y0,z0+.35),(x,yb,zb+.35),(x,yb,zb-.6),(x,y0,z0-.6)]
            m.poly(q if sx>0 else q[::-1],'granite');m.poly(q[::-1] if sx>0 else q,'granite')
            m.beam((x,y0,z0+.35),(x,yb,zb+.35),.36,.22,'granite_light')
    return yb,zb

# ---------------------------------------------------------------- the set
def temple():
    m=Mesh('SW_Temple')
    PT=1.0                                                         # plinth top
    # stepped stone plinth: a broad lower shelf and the hall's tier, darker grey, dry-stone edge blocks
    m.box((0,1.0,.24),(13.0,11.0,.48),'granite');m.box((0,1.0,.48+.26),(9.0,8.0,.52),'granite_light')
    for tier,(w,d,z,h) in enumerate([(13.0,11.0,.24,.46),(9.0,8.0,.74,.50)]):
        n=int(w/1.1)
        for k in range(n):
            for sy in (-1,1):m.box((-w/2+(k+.5)*w/n,1.0+sy*(d/2-.02),z),(w/n-.05,.26,h-.04),cv('granite' if (k+tier)%2 else 'granite_light',.07),bevel=.02)
        nn=int(d/1.1)
        for k in range(nn):
            for sx in (-1,1):m.box((sx*(w/2-.02),1.0-d/2+(k+.5)*d/nn,z),(.26,d/nn-.05,h-.04),cv('granite_light' if (k+tier)%2 else 'granite',.07),bevel=.02)
    m.collider((0,1.0,.24),(13,11,.48));m.collider((0,1.0,.74),(9,8,.52))
    # paving lines on the shelf
    for k in range(-5,6):m.beam((k*1.2,-4.4,.49),(k*1.2,6.4,.49),.04,.02,'granite')
    with m.at((0,1.6,0)):hall(m,z=PT)
    # steps from the shelf (z .48) to the hall tier (z 1.0) in front of the veranda stair
    for i in range(3):
        top=.98-i*.17;bottom=.46
        m.box((0,-3.1-i*.36,(top+bottom)/2),(2.6,.38,top-bottom),cv('granite_light',.05))
        m.collider((0,-3.1-i*.36,(top+bottom)/2),(2.6,.38,top-bottom))
    # the long formal stair: run one from the shelf edge down to ground, landing, run two down the slope
    yb,zb=stair(m,-4.5,.48,4,.12,.36,3.0)
    m.box((0,yb-.8,zb-.5),(3.8,1.6,1.0),'granite_light');m.collider((0,yb-.8,zb-.08),(3.8,1.6,.16))
    for sx in (-1,1):m.beam((sx*1.68,yb,zb+.3),(sx*1.68,yb-1.6,zb+.3),.36,.22,'granite_light')
    yb2,zb2=stair(m,yb-1.6,zb,12,.17,.38,3.0)
    stone_lantern(m,-2.3,-6.0,zb+.0);stone_lantern(m,2.3,-6.0,zb+.0)
    stone_lantern(m,-2.2,-1.6,.48,1.4);stone_lantern(m,2.2,-1.6,.48,1.4)
    stone_lantern(m,2.6,yb2+1.2,site_ground(2.6,yb2+1.2),1.3)
    with m.at((5.6,-1.4,0),yaw=-8):
        m.box((0,0,.21),(2.64,2.64,.54),'granite')
        m.collider((0,0,.24),(2.64,2.64,.48))
    bell_house(m,5.6,-1.4,.48,yaw=-8)
    pennants(m,(6.4,-4.2,2.7),(9.4,-7.6,2.4))
    # vegetation: pines at the corners, a maple by the hall, shrubs along the plinth and the stair
    pine(m,-7.0,3.5,site_ground(-7,3.5)-.08,h=5.2,seed=1);pine(m,7.4,4.6,site_ground(7.4,4.6)-.08,h=4.6,yaw=60,seed=2);pine(m,-6.6,-6.4,site_ground(-6.6,-6.4)-.08,h=4.2,yaw=130,seed=3);pine(m,8.6,-9.0,site_ground(8.6,-9)-.08,h=3.8,yaw=200,seed=4)
    maple(m,-4.6,-3.4,.48)
    for k,(x,y,z,r,key) in enumerate([(-6.2,-3.2,0,.7,'shrub_yellow'),(-5.6,-7.6,-.5,.6,'green'),(-3.6,-9.8,-.9,.6,'shrub_yellow'),(3.9,-8.8,-.8,.65,'shrub_yellow'),(5.0,-10.8,-1.3,.6,'maple'),(6.8,2.2,0,.6,'green'),(-7.4,.8,0,.6,'shrub_yellow'),(7.2,-6.2,-.4,.55,'green'),(-2.3,-12.2,-1.7,.5,'shrub_yellow'),(2.4,-13.0,-1.9,.5,'green'),(-8.0,6.0,0,.7,'shrub_yellow'),(8.4,7.2,0,.6,'shrub_yellow')]):
        shrub(m,x,y,site_ground(x,y)-.06,r,key,seed=k)
    # faceted boulders at the cliff edge and beside the stair
    for k,(x,y,z,s) in enumerate([(-8.6,-2.0,-.6,1.6),(-7.6,-5.2,-.9,1.3),(8.8,-3.6,-.7,1.5),(9.8,0.8,-.5,1.7),(-9.4,3.8,-.4,1.4),(9.6,4.8,-.5,1.2),(-3.2,-13.4,-2.0,1.2),(3.4,-13.8,-2.2,1.3),(-5.4,-10.6,-1.4,1.0),(6.4,-11.6,-1.6,1.1),(-8.8,7.8,-.3,1.1),(0,8.4,-.2,1.3)]):
        boulder(m,x,y,z,s,seed=k)
    # ochre grass patches and tufts around the plinth and along the slope
    for k,(x,y,z,r) in enumerate([(-6.6,-1.0,0,1.6),(6.6,-2.6,0,1.4),(-5.0,-8.6,-.7,1.6),(5.2,-8.0,-.6,1.5),(-8.4,4.6,0,1.8),(8.0,3.2,0,1.5),(-2.4,-11.4,-1.5,1.3),(2.6,-11.0,-1.4,1.2),(0,8.0,0,2.0),(-7.6,-8.4,-.9,1.2),(7.8,-9.6,-1.2,1.2)]):
        grass_patch(m,x,y,z,r,seed=k)
    return m
