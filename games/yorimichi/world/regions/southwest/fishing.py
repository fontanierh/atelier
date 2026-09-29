"""Fishing village kit for the south-west detour, built with the same helpers as Momiji Hamlet (shell, roof, window,
door, lantern) so the two villages share construction, plus what a working harbour needs: a boat shed, a plank dock
on piles, stone stairs, drying racks with fish, nets, buoys, crates and a small boat."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import math, random, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from village.build import window, door, shell, roof, awning, lantern, pot, bench
from mesh import Mesh, PALETTE
R=random.Random(23)
def color_variant(key,amount=.05):
    f=R.uniform(1-amount,1+amount);return tuple(min(1,c*f) for c in PALETTE[key])

def net(m,x,y,z,w=1.6,h=1.2,color='rope'):
    """A hanging net: a coarse grid of thin beams with a sagging bottom edge."""
    n=int(w/.2);k=int(h/.2)
    for i in range(n+1):
        xx=x-w/2+i*w/n;m.beam((xx,y,z+h/2),(xx+.03*math.sin(i),y,z-h/2-.08*math.sin(math.pi*i/n)),.012,.012,color)
    for j in range(k+1):
        zz=z+h/2-j*h/k;m.beam((x-w/2,y,zz),(x+w/2,y,zz-.04*(j/k)),.012,.012,color)
    for i in range(0,n+1,2):m.sphere((x-w/2+i*w/n,y-.02,z-h/2-.08*math.sin(math.pi*i/n)),.035,'cream',n=5,rings=3)

def floats(m,x,y,z,count=4):
    """Glass fishing floats in rope slings, hung under an eave."""
    for i in range(count):
        xx=x+i*.30;m.beam((xx,y,z+.35),(xx,y-.02,z),.012,.012,'rope');m.sphere((xx,y-.03,z-.13),.12,'glass',n=7,rings=4)
        for a in (0,1.05,2.1):m.beam((xx+math.cos(a)*.12,y-.03+math.sin(a)*.12,z-.13),(xx,y-.03,z-.01),.01,.01,'rope')
def buoys(m,x,y,z,count=3):
    """Two-tone fishing buoys, orange over cream, hung from a rope."""
    for i in range(count):
        xx=x+i*.30;m.beam((xx,y,z+.35),(xx,y-.02,z+.05),.012,.012,'rope')
        m.lathe((xx,y-.03,z-.22),[(0,.0),(0,.11),(.14,.13)],'cream',n=8);m.lathe((xx,y-.03,z-.08),[(0,.13),(.14,.11),(.14,0)],'rust',n=8)

def lobster_pot(m,x,y,z=0,r=.28,h=.42):
    with m.at((x,y,z)):
        for zz in (0,h/2,h):m.lathe((0,0,zz),[(-.015,r),(.015,r)],'wood_pale',n=8)
        for k in range(8):
            a=k*2*math.pi/8;m.beam((math.cos(a)*r,math.sin(a)*r,0),(math.cos(a)*r,math.sin(a)*r,h),.02,.02,'wood_light')
        m.lathe((0,0,h/2),[(-h/2+.03,.02),(h/2-.03,.02)],'rope',n=5)

T30=math.tan(math.radians(30))
def plank_wall(m,x0,x1,y,z0,z1,depth=.06,key='plank_cream',board=.22):
    """Horizontal cream/taupe boards between z0 and z1 along a wall at y; every other board steps out 12 mm."""
    k=0;z=z0
    while z<z1-.01:
        h=min(board,z1-z);m.box(((x0+x1)/2,y+(.012 if k%2 else 0),z+h/2),(x1-x0,depth,h-.012),color_variant(key if k%3 else 'plank_cream_light',.07));z+=h;k+=1

def gable_wall(m,half,y,z0,rise,key='plank_cream',vent=True):
    """Planked gable triangle over a wall of half-width `half` at y: boards shrink toward the ridge; a small vent near the top."""
    k=0;z=z0
    while z<z0+rise-.02:
        h=min(.22,z0+rise-z);hw=half*(1-(z+h/2-z0)/rise)
        if hw>.08:m.box((0,y+(.012 if k%2 else 0),z+h/2),(2*hw,.06,h-.012),color_variant(key if k%3 else 'plank_cream_light',.07))
        z+=h;k+=1
    if vent:m.box((0,y,z0+rise*.55),(.26,.09,.26),'wood_dark');m.box((0,y,z0+rise*.55),(.16,.13,.16),(.01,.008,.006))

def gable_roof(m,w,d,eave,overhang=.7,gable_overhang=.45,thick=.13,key='roof_grey'):
    """Solid dark slate roof at 30 degrees: one thick slab per slope, ridge cap, bargeboards and rafter tails UNDER the eave."""
    W=w+2*gable_overhang;ridge=eave+(d/2)*T30;ez=eave-overhang*T30;D=d/2+overhang
    for s in (-1,1):
        lo=[(-W/2,s*D,ez),(W/2,s*D,ez)];hi=[(W/2,0,ridge),(-W/2,0,ridge)]
        top=[(x,y,z+thick) for x,y,z in lo+hi];bot=lo+hi
        col=color_variant(key,.06 if s<0 else .10)
        m.poly(top if s<0 else top[::-1],col);m.poly(bot[::-1] if s<0 else bot,'roof_edge')
        m.poly([bot[0],bot[1],top[1],top[0]] if s<0 else [bot[1],bot[0],top[0],top[1]],'roof_edge')            # eave fascia
        for x in (-W/2,W/2):m.poly([bot[0 if x<0 else 1],hi[1 if x<0 else 0],top[3 if x<0 else 2],top[0 if x<0 else 1]],'roof_edge')
        for k in (1,2):                                                                              # two plank lines per slope
            t=k/3;y=s*D*(1-t);z=ez+(ridge-ez)*t+thick;m.box((0,y,z+.012),(W-.2,.05,.03),'roof_grey_light')
        n=int(W/.55)
        for i in range(n+1):
            x=-W/2+.15+i*(W-.3)/n;m.beam((x,s*(d/2-.25),eave+.25*T30-.08),(x,s*D-.05,ez+.05*T30-.08),.08,.10,'wood')   # rafter tails
        m.beam((-W/2,s*D,ez+thick/2),(-W/2,0,ridge+thick/2),.07,thick+.02,'wood_dark');m.beam((W/2,s*D,ez+thick/2),(W/2,0,ridge+thick/2),.07,thick+.02,'wood_dark')
    m.box((0,0,ridge+thick+.04),(W+.06,.34,.11),'roof_grey_light')
    for yy in (-d/2,d/2):m.beam((-w/2-.05,yy,eave-.10),(w/2+.05,yy,eave-.10),.14,.14,'wood')          # wall plates
    return ridge

def plinth(m,w,d,h=.42):
    """Low grey stone plinth: a chamfered granite slab with a few darker stones in its face."""
    m.box((0,0,(h-.4)/2),(w+.34,d+.34,h+.4),'granite',bevel=.05)
    for side in (-1,1):
        for k in range(int(w/.8)):m.box((-w/2+(k+.5)*w/int(w/.8),side*(d/2+.19),.12),(w/int(w/.8)-.08,.05,.18),color_variant('granite_light',.10))
        for k in range(int(d/.8)):m.box((side*(w/2+.19),-d/2+(k+.5)*d/int(d/.8),.12),(.05,d/int(d/.8)-.08,.18),color_variant('granite_light',.10))

def sliding_door(m,x,y,z0,w=1.15,h=1.82):
    """Dark plank sliding door with a vertical centre rail and a lintel."""
    m.box((x,y,z0+h/2),(w+.22,.10,h+.12),'wood_dark')
    for k in range(5):m.box((x-w/2+(k+.5)*w/5,y-.07,z0+h/2),(w/5-.012,.05,h),color_variant('wood',.10))
    m.box((x,y-.11,z0+h/2),(.09,.06,h),'wood_dark');m.box((x,y-.11,z0+h-.10),(w,.06,.08),'wood_dark');m.box((x,y-.11,z0+.32),(w,.06,.08),'wood_dark')
    for xx in (x-w/2-.06,x+w/2+.06):m.box((xx,y-.13,z0+h/2),(.12,.15,h+.14),'wood')
    m.box((x,y-.10,z0+h+.09),(w+.36,.12,.11),'wood');m.box((x+.16,y-.15,z0+1.0),(.05,.05,.20),'metal')

def lattice_window(m,x,y,z,w=1.3,h=.95):
    """Dark frame, warm off-white panes behind a wooden lattice, a small sill and a pale shutter rail above."""
    m.box((x,y,z),(w+.18,.10,h+.18),'wood_dark');m.box((x,y-.06,z),(w,.05,h),'cream')
    for i in range(1,5):m.box((x-w/2+w*i/5,y-.10,z),(.045,.05,h),'wood_dark')
    for j in range(1,3):m.box((x,y-.10,z-h/2+h*j/3),(w,.05,.045),'wood_dark')
    m.box((x,y-.14,z-h/2-.04),(w+.30,.20,.07),'wood');m.box((x,y-.10,z+h/2+.10),(w+.34,.12,.08),'wood_light')

def teardrop_net(m,x,y,z,h=1.5,w=.75):
    """A hanging teardrop net: a lathe-like cage of rope beams around a bulging profile, with a cork float at the neck."""
    prof=[(0,.02),(-.12,.08),(-.35,.20),(-.65,.34),(-.95,.36),(-1.2,.30),(-1.4,.18),(-h,.05)]
    n=8
    rings=[[(x+r*w/.36*math.cos(i*2*math.pi/n)*.5,y-.02-r*.55*w/.36*.5+ .0,z+zz) for i in range(n)] for zz,r in prof]
    for i in range(n):
        for a,b in zip(rings[:-1],rings[1:]):m.beam(a[i],b[i],.014,.014,'rope')
    for ring in rings[1:-1]:
        for i in range(n):m.beam(ring[i],ring[(i+1)%n],.012,.012,'rope')
    m.beam((x,y-.02,z+.30),(x,y-.02,z),.014,.014,'rope');m.lathe((x,y-.05,z-.28),[(-.10,.03),(-.06,.075),(.06,.075),(.10,.03)],'straw_light',n=7)

def laundry_rail(m,x,y,z,w=1.5):
    """A rail on two brackets with three cloths (blue, white, pink) and a bundle of straw."""
    m.beam((x-w/2,y,z),(x+w/2,y,z),.045,.045,'wood_light')
    for xx in (x-w/2+.08,x+w/2-.08):m.beam((xx,y+.10,z-.12),(xx,y-.02,z),.04,.04,'wood')
    for i,col in enumerate(('cloth_blue','white','cloth_pink')):
        cx=x-w/2+.28+i*.36;top=z-.02;bot=z-.95-.06*i
        for side,dy in ((1,-.03),(-1,-.032)):
            pts=[(cx-.14,y+dy,top),(cx+.14,y+dy,top),(cx+.15,y+dy-.04,bot),(cx-.15,y+dy-.04,bot)];m.poly(pts if side>0 else pts[::-1],col)
    sx=x+w/2-.16
    for k in range(7):
        a=k*2*math.pi/7;m.beam((sx+math.cos(a)*.05,y-.06+math.sin(a)*.05,z-.02),(sx+math.cos(a)*.11,y-.06+math.sin(a)*.11,z-.85),.03,.03,color_variant('straw_bundle',.12))
    m.lathe((sx,y-.06,z-.12),[(-.03,.06),(.03,.06)],'rope',n=6)

def bamboo_panel(m,x,y,z,w=1.2,h=.7):
    for k in range(int(w/.09)):m.beam((x-w/2+(k+.5)*w/int(w/.09),y,z),(x-w/2+(k+.5)*w/int(w/.09),y,z+h),.05,.05,color_variant('plank_tan',.10))
    for zz in (z+.15,z+h-.15):m.beam((x-w/2,y-.03,zz),(x+w/2,y-.03,zz),.04,.04,'wood')

def bucket(m,x,y,z=0):
    m.lathe((x,y,z),[(0,.14),(.34,.17)],'stone_blue',n=9);m.lathe((x,y,z+.34),[(-.02,.175),(.02,.175)],'stone_blue_light',n=9)
    m.beam((x-.17,y,z+.34),(x,y,z+.62),.02,.02,'metal');m.beam((x,y,z+.62),(x+.17,y,z+.34),.02,.02,'metal')

def porch(m,w,d,eave,depth=1.6):
    """Lean-to porch on the -X gable end: two posts, a shed roof in the house's slate, a plank floor, harbour clutter under it."""
    x0=-w/2;x1=-w/2-depth;zt=eave-.55;zo=zt-depth*.28
    for yy in (-d/2+.25,d/2-.25):m.beam((x1+.10,yy,0),(x1+.10,yy,zo-.05),.15,.15,'wood')
    m.beam((x1+.10,-d/2+.25,zo-.06),(x1+.10,d/2-.25,zo-.06),.12,.12,'wood');m.beam((x0,-d/2-.1,zt-.06),(x0,d/2+.1,zt-.06),.10,.14,'wood')
    for yy in [-d/2-.1+i*(d+.2)/4 for i in range(5)]:m.beam((x0+.2,yy,zt-.1),(x1-.3,yy,zo-.1),.07,.09,'wood')
    top=[(x0+.15,-d/2-.30,zt),(x0+.15,d/2+.30,zt),(x1-.35,d/2+.30,zo),(x1-.35,-d/2-.30,zo)]
    m.poly(top[::-1],color_variant('roof_grey',.08));m.poly([(x,y,z-.10) for x,y,z in top],'roof_edge')
    for a,b in zip(top,top[1:]+top[:1]):m.poly([a,b,(b[0],b[1],b[2]-.10),(a[0],a[1],a[2]-.10)],'roof_edge')
    m.box((x1-.10,0,zo-.02),(.06,d+.6,.12),'roof_grey_light')
    for k in range(int(depth/.3)):m.box((x0-.15-k*.3,0,.08),(.28,d,.05),color_variant('driftwood',.10))
    m.box((x0-depth/2,0,.0),(depth,d,.16),'wood_dark')
    barrel(m,x1+.55,-d/2+.6,.1);pot(m,x1+.55,d/2-.75,.1,1.15,'clay',form='urn');pot(m,x0-.45,d/2-.55,.1,.9,'clay',form='jar')
    teardrop_net(m,x0-.30,-d/2+.05,eave-.75,h=1.35);bucket(m,x1+.35,.15,.1)
    m.collider((x0-depth/2,0,zo/2),(depth,d,zo))

def plank_house(m,w=5.2,d=4.2,variant='A',stilts=0.0):
    """A fisher's house in the reconciled look: low granite plinth, cream plank walls with a dark skirting board, dark
    corner posts and frame, planked gables with a vent, a solid dark slate gable roof at 30 degrees with rafter tails
    under the eave; A wears a teardrop net, bench, bowl and barrels, B a lean-to porch, laundry rail and an oar."""
    eave=2.55;z0=.42
    if stilts:
        for xx in [-w/2+.3+i*(w-.6)/3 for i in range(4)]:
            for yy in (-d/2+.3,d/2-.3):m.beam((xx,yy,-stilts),(xx,yy,.1),.20,.20,'wood_dark')
    plinth(m,w,d,z0)
    m.box((0,0,(eave+z0)/2),(w-.06,d-.06,eave-z0),'wood_dark')                                    # inner core so gaps never show
    for yy in (-d/2,d/2):plank_wall(m,-w/2,w/2,yy,z0+.42,eave-.10)
    for sx in (-1,1):
        with m.at((0,0,0),yaw=90):plank_wall(m,-d/2,d/2,-sx*w/2,z0+.42,eave-.10);gable_wall(m,d/2,-sx*w/2,eave-.10,(d/2)*T30+.10,vent=(variant=='B') or sx>0)
    for yy in (-d/2,d/2):m.box((0,yy+(.02 if yy<0 else -.02),z0+.22),(w+.02,.09,.44),'wood_dark')   # skirting boards
    for sx in (-1,1):m.box((sx*(w/2+.01),0,z0+.22),(.09,d+.02,.44),'wood_dark')
    for xx in (-w/2,w/2):
        for yy in (-d/2,d/2):m.beam((xx,yy,z0),(xx,yy,eave),.17,.17,'wood')
    ridge=gable_roof(m,w,d,eave)
    m.collider((0,0,ridge/2),(w+.4,d+.4,ridge+.3))
    y=-d/2-.05
    if variant=='A':
        sliding_door(m,w/2-1.25,y-.02,z0);lattice_window(m,-w/2+1.55,y-.02,z0+1.35,w=1.3,h=.95)
        teardrop_net(m,-w/2+.85,y-.14,eave-.55,h=1.45);bench(m,w/2-2.55,y-.55,z=0,w=1.3)
        barrel(m,-w/2-.55,-d/2+.45);barrel(m,w/2+.45,-d/2+.40);pot(m,w/2-2.4,y-1.05,0,.7,'stone_blue_light',form='bowl')
        bamboo_panel(m,w/2-2.3,y-.10,z0+.05,w=1.0,h=.55);m.beam((w/2+.10,d/2-1.3,.1),(w/2+.16,d/2-1.6,2.25),.06,.03,'wood_pale')
    else:
        sliding_door(m,w/2-1.35,y-.02,z0);laundry_rail(m,-w/2+1.35,y-.12,eave-.85,w=1.5)
        bench(m,w/2-2.7,y-.55,z=0,w=1.1);barrel(m,w/2+.55,-d/2+.3);pot(m,w/2+.55,-d/2+.3,.9,.55,'stone_blue',form='jar')
        m.beam((w/2+.12,d/2-.9,.1),(w/2+.22,d/2-1.25,2.35),.06,.03,'wood_pale')                      # a leaning oar
        porch(m,w,d,eave)
    doorx=w/2-(1.25 if variant=='A' else 1.35)
    for yy,top in [(-d/2-.82,.14),(-d/2-.40,.28)]:
        m.box((doorx,yy,(top-.06)/2),(1.25,.46,top+.06),'granite_light',bevel=.02)
        m.collider((doorx,yy,top/2),(1.25,.46,top))
    return m
fisher_house=plank_house

def fish(m,x,y,z,length=.30,color='fish_blue'):
    """A small elongated fish hung by the tail: dark blue-grey back, pale belly, forked tail."""
    L=length;h=L*.16
    back=[(x,y,z+L*.5),(x-h*.55,y,z+L*.25),(x-h*.7,y,z-L*.05),(x-h*.45,y,z-L*.32),(x-h*.9,y,z-L*.5),(x,y,z-L*.40),(x+h*.9,y,z-L*.5),(x+h*.45,y,z-L*.32),(x+h*.7,y,z-L*.05),(x+h*.55,y,z+L*.25)]
    m.poly(back,color);m.poly([(px,py+.012,pz) for px,py,pz in back[::-1]],color)
    belly=[(x-h*.30,y-.004,z-L*.05),(x+h*.30,y-.004,z-L*.05),(x+h*.25,y-.004,z-L*.36),(x-h*.25,y-.004,z-L*.36)]
    m.poly(belly,'stone_blue_light');m.poly([(px,py+.02,pz) for px,py,pz in belly[::-1]],'stone_blue_light')

def drying_rack(m,x=0,y=0,w=2.4,h=1.9):
    with m.at((x,y,0)):
        for xx in (-w/2,w/2):m.beam((xx,0,0),(xx,0,h),.08,.08,'wood');m.beam((xx-.35,0,0),(xx,0,h*.55),.05,.05,'wood_light')
        m.beam((-w/2,0,h),(w/2,0,h),.06,.06,'wood_light');m.beam((-w/2,0,h*.62),(w/2,0,h*.62),.05,.05,'wood_light')
        for i in range(6):
            xx=-w/2+.25+i*(w-.5)/5;m.beam((xx,0,h),(xx,0,h-.16),.012,.012,'rope')
            for dy in (-.03,.03):fish(m,xx+dy*1.5,dy,h-.16-R.uniform(.12,.16),R.uniform(.26,.34))
        for i in range(4):
            xx=-w/2+.45+i*(w-.9)/3;m.beam((xx,0,h*.62),(xx,0,h*.62-.14),.012,.012,'rope')
            for dy in (-.03,.03):fish(m,xx+dy*1.5,dy,h*.62-.14-R.uniform(.10,.14),R.uniform(.22,.28))
        m.collider((0,0,h/2),(w+.7,.4,h))

def crate(m,x,y,z=0,s=.55):
    m.box((x,y,z+s/2),(s,s,s),'wood_light',bevel=.012)
    for k in range(2):m.box((x,y,z+s*.25+k*s*.5),(s+.02,s+.02,.035),'wood_dark')
    m.collider((x,y,z+s/2),(s,s,s))

def fish_crate(m,x,y,z=0,s=.55):
    crate(m,x,y,z,s)
    for i in range(6):
        fish(m,x-s*.3+(i%3)*s*.3,y-s*.15+(i//3)*s*.3,z+s+.02,s*.5,'stone_blue_light' if i%2 else 'cream')

def laundry(m,a,b,drop=.25):
    a,b=tuple(a),tuple(b);m.beam(a,b,.012,.012,'rope')
    for t,col in ((.3,'cream'),(.5,'blue'),(.7,'white')):
        x=a[0]+(b[0]-a[0])*t;y=a[1]+(b[1]-a[1])*t;z=a[2]+(b[2]-a[2])*t-.01
        m.poly([(x-.22,y,z),(x+.22,y,z),(x+.2,y+.03,z-.55-drop*(t-.5)**2*4),(x-.2,y+.03,z-.55-drop*(t-.5)**2*4)],col)
        m.poly([(x+.22,y+.001,z),(x-.22,y+.001,z),(x-.2,y+.031,z-.55-drop*(t-.5)**2*4),(x+.2,y+.031,z-.55-drop*(t-.5)**2*4)],col)

def seaweed(m,x,y,z=0,h=.9):
    for k in range(3):
        a=k*2.1;m.poly([(x+math.cos(a)*.08,y+math.sin(a)*.08,z+h),(x+math.cos(a)*.12,y+math.sin(a)*.12,z+h*.5),(x+math.cos(a)*.06+.05,y+math.sin(a)*.06,z),(x+math.cos(a)*.14,y+math.sin(a)*.14,z+h*.2)],'green_dark')

def barrel(m,x,y,z=0):
    m.lathe((x,y,z),[(0,.22),(.15,.27),(.45,.29),(.75,.27),(.9,.22)],'wood_light',n=10)
    for zz in (.2,.7):m.lathe((x,y,z+zz),[(-.02,.29),(.02,.29)],'metal',n=10)
    m.collider((x,y,z+.45),(.6,.6,.9))

def rope_coil(m,x,y,z=0):
    m.lathe((x,y,z),[(0,.10),(0,.30),(.12,.32),(.14,.28),(.14,.12),(.12,.10)],'rope',n=10)

def boat_shed(m,w=4.6,d=3.4):
    """Open-fronted boat shed in the house vocabulary: granite plinth, tan plank walls on three sides with the dark
    timber frame exposed outside them, a solid slate gable roof (ridge toward the open -Y front) with deep eaves, and
    a small plank awning over the opening; nets, crates, a barrel and a rope coil inside, the drying rack out front."""
    eave=2.45;z0=.30
    plinth(m,w,d,z0)
    m.box((0,.06,(eave+z0)/2),(w-.06,d-.18,eave-z0),'wood_dark')                                   # inner core
    with m.at((0,0,0),yaw=90):
        for sx in (-1,1):plank_wall(m,-d/2,d/2,-sx*w/2,z0+.05,eave-.10,key='plank_tan')
    gable_wall(m,w/2,d/2,eave-.10,(w/2)*T30+.10,key='plank_tan',vent=True)                        # back gable (+Y)
    plank_wall(m,-w/2,w/2,d/2,z0+.05,eave-.10,key='plank_tan')
    for xx in (-w/2,w/2):
        for yy in (-d/2,d/2):m.beam((xx,yy,z0),(xx,yy,eave+(0)),.18,.18,'wood')
    for yy in (-d/2,d/2):m.beam((-w/2,yy,z0+.9),(w/2,yy,z0+.9),.10,.12,'wood') if yy>0 else None
    for sx in (-1,1):
        m.beam((sx*w/2,-d/2,z0+1.0),(sx*w/2,d/2,z0+1.0),.12,.10,'wood');m.beam((sx*w/2,-d/2,z0+1.8),(sx*w/2,d/2,z0+1.8),.10,.10,'wood')  # exposed rails
        m.beam((sx*w/2,0,z0),(sx*w/2,0,eave),.15,.15,'wood')
    m.box((0,d/2,z0+1.3),(w,.10,.10),'wood')
    # front gable above the opening: planked, with the roof ridge running along Y
    gable_wall(m,w/2,-d/2,eave-.10,(w/2)*T30+.10,key='plank_tan',vent=False)
    m.beam((-w/2,-d/2,eave-.10),(w/2,-d/2,eave-.10),.16,.16,'wood')                                 # header over the opening
    with m.at((0,0,0),yaw=90):ridge=gable_roof(m,d,w,eave,overhang=.8,gable_overhang=.55)
    # small plank awning over the opening
    aw=[(-w/2-.25,-d/2-.02,eave-.50),(w/2+.25,-d/2-.02,eave-.50),(w/2+.25,-d/2-1.05,eave-.82),(-w/2-.25,-d/2-1.05,eave-.82)]
    m.poly(aw,color_variant('roof_grey',.08));m.poly([(x,y,z-.09) for x,y,z in aw[::-1]],'roof_edge')
    for a,b in zip(aw,aw[1:]+aw[:1]):m.poly([a,b,(b[0],b[1],b[2]-.09),(a[0],a[1],a[2]-.09)],'roof_edge')
    m.beam((-w/2-.25,-d/2-1.0,eave-.90),(w/2+.25,-d/2-1.0,eave-.90),.10,.10,'wood')
    for xx in (-w/2+.2,w/2-.2):m.beam((xx,-d/2-.05,eave-1.15),(xx,-d/2-1.0,eave-.92),.08,.08,'wood');m.beam((xx,-d/2-.05,eave-.62),(xx,-d/2-1.0,eave-.92),.08,.08,'wood')
    for yy in [-d/2-.15-k*.3 for k in range(3)]:m.beam((-w/2-.25,yy,eave-.50-(yy+d/2+.02)/-1.03*-.32-.09+.04),(w/2+.25,yy,eave-.50-(yy+d/2+.02)/-1.03*-.32-.09+.04),.04,.04,'roof_grey_light')
    net(m,-w/4,d/2-.12,1.35,w=1.5,h=1.5);crate(m,w/4,d/2-.65,z0,.6);barrel(m,w/4+.75,d/2-.55,z0);rope_coil(m,-w/4,d/2-.95,z0)
    m.box((0,0,z0-.03),(w-.1,d-.1,.06),'wood_dark')
    m.box((0,-d/2-.40,.045),(1.65,.52,.21),'granite_light',bevel=.02)
    m.collider((0,-d/2-.40,.075),(1.65,.52,.15))                                                # floor
    lobster_pot(m,-w/2-.65,-d/2+.2,0);crate(m,w/2+.6,-d/2+.6,0,.5)
    drying_rack(m,0,-d/2-2.0,w=2.6,h=1.8)
    m.collider((0,.2,eave/2),(w,d-.4,eave))
    return m

def stone_wall(m,length=6.0,height=1.2,depth=.7):
    """A dry-stone terrace retaining wall segment running along X, face toward -Y: two or three courses of chunky
    granite blocks with lighter tops, capped by a row of flatter stones; offered for the village terraces."""
    z=0;row=0
    while z<height-.05:
        h=min(R.uniform(.32,.42),height-z);x=-length/2+(.2 if row%2 else 0)
        while x<length/2-.05:
            ln=min(R.uniform(.5,.9),length/2-x);m.box((x+ln/2,-depth/2+R.uniform(-.03,.03),z+h/2),(ln-.03,depth*R.uniform(.9,1.05),h-.02),color_variant(R.choice(['granite','granite','granite_light','stone']),.10),bevel=.04);x+=ln
        z+=h;row+=1
    m.box((0,-depth/2,z+.05),(length,depth+.1,.10),color_variant('granite_light',.06),bevel=.02)
    m.collider((0,-depth/2,height/2),(length,depth,height+.1))
    return m

def stairs(m,steps=9,w=2.2,rise=.18,run=.32):
    """Stone stairway climbing toward +Y: blue-grey treads with dry-stone retaining walls of stacked, varied blocks."""
    for i in range(steps):
        m.box((0,i*run+run/2,i*rise+rise/2),(w,run+.02,rise),color_variant('stone_blue_light',.07),bevel=.02)
        m.box((0,i*run+run/2,i*rise-rise/2),(w,run+.02,rise),'stone_blue') if i else None
    for sx in (-1,1):
        z=0;row=0
        while z<steps*rise+.6:
            yy=0
            while yy<steps*run:
                ln=R.uniform(.35,.6);h=.22+R.uniform(0,.06)
                if z<yy/run*rise+.62:m.box((sx*(w/2+.22),yy+ln/2,z+h/2),(.42,ln-.02,h-.015),color_variant(R.choice(['stone_blue','stone_blue_light','stone']),.08),bevel=.03)
                yy+=ln
            z+=.25;row+=1
    m.collider((0,steps*run/2,steps*rise/2),(w+.9,steps*run,steps*rise+.6))
    return m

def dock(m,length=7.0,w=2.6):
    """Plank deck 1.2 m over the water on braced piles, running toward -Y; gapped planks, two mooring posts, a ladder,
    a lantern post, crates and a rope coil."""
    H=1.2
    for i in range(int(length/.42)):
        y=-i*.42;m.box((0,y-.19,H),(w,.34,.06),color_variant('driftwood',.12))
    for sx in (-1,1):m.beam((sx*(w/2-.1),.1,H-.06),(sx*(w/2-.1),-length,H-.06),.16,.14,'wood_dark')
    for i in range(int(length/1.5)+1):
        y=-i*1.5-.2
        for sx in (-1,1):m.beam((sx*(w/2-.15),y,-1.0),(sx*(w/2-.15),y,H+.05),.16,.16,'wood')
        m.beam((-(w/2-.15),y,H-.9),((w/2-.15),y,H-.2),.07,.07,'wood_light');m.beam(((w/2-.15),y,H-.9),(-(w/2-.15),y,H-.2),.07,.07,'wood_light')
    for y in (-1.2,-length+1.0):m.beam((w/2+.05,y,H-.6),(w/2+.05,y,H+1.0),.14,.14,'wood_dark')                  # mooring posts
    m.beam((w/2-.2,-length+.3,H),(w/2-.2,-length+.3,H+1.9),.09,.09,'wood');lantern(m,w/2-.2,-length+.3,H+1.55,.34)
    for k in range(4):m.beam((-w/2-.05,-length+2.0,H-.1-k*.32),(-w/2-.35,-length+2.0,H-.1-k*.32),.05,.05,'wood_light')  # ladder
    for xx in (-w/2-.05,-w/2-.35):m.beam((xx,-length+2.0,H+.1),(xx,-length+2.0,H-1.3),.05,.05,'wood')
    crate(m,-w/2+.45,-1.3,H+.03,.5);crate(m,-w/2+.45,-1.85,H+.03,.45);crate(m,-w/2+.95,-1.5,H+.03,.42);rope_coil(m,.3,-length+1.0,H+.03);barrel(m,-w/2+.5,-length+1.6,H+.03)
    lobster_pot(m,w/2-.5,-3.0,H+.03);lobster_pot(m,w/2-.5,-3.0,H+.45,.24,.36)
    m.collider((0,-length/2,H-.3),(w,length,.6))
    return m

def boat(m,length=4.4):
    """A small wooden fishing boat: faceted hull with real freeboard, three ribs, two thwarts, two oars and a rope."""
    ribs=[];n=9;F=.50
    for i in range(n+1):
        u=-1+2*i/n;x=u*length/2;hw=.66*(1-u**4)+.05;depth=.62*(1-.45*u**4);top=F+.22*abs(u)**2
        ribs.append([(x,-hw,top),(x,-hw*.72,top-depth*.62),(x,0,top-depth),(x,hw*.72,top-depth*.62),(x,hw,top)])
    for a,b in zip(ribs[:-1],ribs[1:]):
        for k in range(4):m.poly([a[k],b[k],b[k+1],a[k+1]],color_variant('driftwood',.12));m.poly([a[k+1],b[k+1],b[k],a[k]],'wood_light')
    for i in (0,4):
        for a,b in zip(ribs[:-1],ribs[1:]):m.beam(a[i],b[i],.09,.09,'wood_dark')
    for x in (-1.1,0,1.1):                                                                       # ribs inside
        for k in range(4):
            r=ribs[int((x/length+.5)*n)];m.beam(r[k],r[k+1],.05,.05,'wood')
    for x in (-1.0,.7):m.box((x,0,F-.05),(.26,1.2,.05),'wood_light')
    for s_,x in ((-1,-.4),(1,.4)):m.beam((x,s_*.6,F+.05),(x+1.2,s_*1.5,-.15),.06,.06,'wood_pale');m.box((x+1.25,s_*1.55,-.16),(.35,.12,.02),'wood_pale')
    rope_coil(m,1.5,-.2,F-.2)
    m.collider((0,0,F/2),(length,1.5,F+.6))
    return m

def vignette():
    """A review composition of the whole kit, like a corner of the village seen from the water side."""
    m=Mesh('SW_FishingVignette')
    with m.at((-4.0,4.0,0),yaw=8):fisher_house(m,5.2,4.2,'A')
    with m.at((4.0,5.0,.5),yaw=-20):fisher_house(m,4.6,3.8,'B')
    with m.at((6.0,-1.5,0),yaw=20):boat_shed(m)
    with m.at((-0.5,-.5,0),yaw=0):stairs(m,6)
    with m.at((-2.0,-3.0,0),yaw=0):dock(m,5.5)
    with m.at((-6.0,-5.5,-.35),yaw=60):boat(m)
    drying_rack(m,1.2,1.8,2.6,1.9);fish_crate(m,2.6,1.4,0,.55);barrel(m,-1.6,1.0);fish_crate(m,-6.2,-.5,0,.5);rope_coil(m,-7.0,0)
    laundry(m,(-1.5,2.2,2.3),(1.2,3.6,2.4));m.beam((-1.5,2.2,0),(-1.5,2.2,2.35),.07,.07,'wood')
    for (x,y) in [(-3.15,-3.2),(-.85,-3.2),(-3.15,-6.2),(-.85,-4.7)]:seaweed(m,x,y,-.4)
    for x,y in [(-3,-5),(1,-6),(4,-4.5)]:m.lathe((x,y,-.6),[(0,0),(0,.5),(.45,.6),(.7,.4)],'stone',n=7)     # a few rocks at the waterline
    return m

MODELS={'fisher_house_a':lambda:fisher_house(Mesh('SW_FisherHouseA'),5.2,4.2,'A'),'fisher_house_b':lambda:fisher_house(Mesh('SW_FisherHouseB'),4.6,3.8,'B'),
        'boat_shed':lambda:boat_shed(Mesh('SW_BoatShed')),'stone_wall':lambda:stone_wall(Mesh('SW_StoneWall')),'stairs':lambda:stairs(Mesh('SW_StoneStairs')),'dock':lambda:dock(Mesh('SW_Dock')),'boat':lambda:boat(Mesh('SW_Boat')),
        'drying_rack':lambda:(lambda mm:(drying_rack(mm),mm)[1])(Mesh('SW_DryingRack')),'fishing_vignette':vignette}
