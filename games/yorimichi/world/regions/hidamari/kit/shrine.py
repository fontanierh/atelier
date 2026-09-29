"""Neighbourhood Inari shrine hall: raised floor on vermilion posts, broad low stepped-row bark hip roof with chigi, wide gabled porch canopy with a gold frieze, curly-maned komainu, lantern, basin pavilion, banners."""
import math,random
import numpy as np
from village import build as v
from hidamari import arcade
from hidamari.kit._lettering import raised_text

ASSETS={'HD_Shrine':0}

VARIANTS=[
    dict(name='稲荷神社',fox=True,plaster=(.62,.55,.41),bark=(.11,.074,.044),cloth=(.70,.66,.54),plinth='奉納'),
    dict(name='八幡神社',fox=False,plaster=(.60,.54,.41),bark=(.10,.080,.052),cloth=(.69,.66,.55),plinth='奉納'),
]


def palette(var):
    arcade.palette()
    bark=var['bark']
    v.PALETTE.update({
        'shr_verm':(.62,.115,.025),'shr_verm_dark':(.42,.08,.02),
        'shr_plaster':var['plaster'],'shr_bark':bark,'shr_bark_d':tuple(c*.7 for c in bark),'shr_ridge':(.075,.055,.040),
        'shr_fascia':(.36,.28,.17),'shr_pale':(.34,.26,.13),
        'shr_stone':(.47,.41,.29),'shr_stone_l':(.57,.51,.38),'shr_stone_d':(.33,.28,.19),'shr_mane':(.50,.45,.33),
        'shr_gravel':(.38,.34,.26),'shr_pebble':(.55,.50,.40),'shr_straw':(.42,.30,.11),
        'shr_cloth':var['cloth'],'shr_ink':(.04,.04,.05),'shr_bamboo':(.16,.20,.08),'shr_node':(.07,.08,.03),
        'shr_green':(.14,.26,.11),'shr_gold':(.40,.29,.08),'shr_gold_l':(.72,.55,.18),'shr_fox':(.86,.60,.12),
        'shr_wood':(.15,.075,.028),'shr_under':(.10,.06,.03),'shr_dark':(.05,.04,.03),
        'shr_glow':(.74,.57,.36),'shr_gable':(.42,.36,.24),'shr_timber':(.13,.062,.024),'shr_plinth_ink':(.03,.03,.035),
        'shr_cream':(.55,.49,.36),'shr_rope':(.66,.62,.52),'shr_shide':(.70,.66,.56),
    })


def _normal(a,b,c):
    u=np.array(b,dtype=float)-np.array(a,dtype=float);w=np.array(c,dtype=float)-np.array(a,dtype=float);n=np.cross(u,w);l=np.linalg.norm(n)
    return n/l if l>1e-9 else np.array([0,0,1.])


def face(m,pts,key,out):
    """Polygon whose front side faces the `out` direction (winding fixed automatically)."""
    n=_normal(pts[0],pts[1],pts[2])
    m.poly(pts if float(np.dot(n,out))>=0 else pts[::-1],key)


def both(m,pts,key):
    m.poly(pts,key);m.poly(pts[::-1],key)


def cone_y(m,base,length,r0,r1,key,n=8):
    """Cone/frustum whose axis points along -Y from `base` (rings in the XZ plane, faces outward)."""
    x,y,z=base
    ra=[(x+r0*math.cos(i*math.tau/n),y,z+r0*math.sin(i*math.tau/n)) for i in range(n)]
    rb=[(x+r1*math.cos(i*math.tau/n),y-length,z+r1*math.sin(i*math.tau/n)) for i in range(n)]
    for k in range(n):
        q=[ra[k],ra[(k+1)%n],rb[(k+1)%n],rb[k]]
        c=np.mean(np.array(q),axis=0);out=c-np.array([x,y-length/2,z])
        face(m,q,key,out)
    face(m,rb,key,(0,-1,0))


def bold(m,text,pos,size,color,lettering,dx=.012,dz=.012):
    """Readable ink and gold lettering with one expanded, extruded outline."""
    raised_text(m,text,pos,size,color,weight=max(dx,dz),depth=.016)


def stepped_rows(m,rings,key,ledge,step=.04,jitter=.10):
    """Rows of bark between successive rings. Each row's lower edge is pushed out along the slope normal so the
    rows step like shingle courses, and a dark ledge beam runs along every lower edge so the courses self-shade."""
    n=len(rings[0])
    for i,(a,b) in enumerate(zip(rings[:-1],rings[1:])):
        for k in range(n):
            p0,p1,p2,p3=a[k],a[(k+1)%n],b[(k+1)%n],b[k]
            if np.linalg.norm(np.array(p1)-np.array(p0))<1e-6:continue
            nm=_normal(p0,p1,p3 if np.linalg.norm(np.array(p3)-np.array(p0))>1e-6 else p2)
            if i>0:
                q0=tuple(np.array(p0)+nm*step);q1=tuple(np.array(p1)+nm*step)
                m.poly([q0,q1,p2,p3],v.color_variant(key,jitter))
                l0=tuple(np.array(p0)+nm*.015);l1=tuple(np.array(p1)+nm*.015)
                m.beam(l0,l1,.10,.06,ledge)
            else:
                m.poly([p0,p1,p2,p3],v.color_variant(key,jitter))


def hip_roof(m,x0,x1,y0,y1,ze,zr,rx0,rx1,key='shr_bark',under='shr_wood'):
    """Broad low hipped bark roof: gently flared eave, a second shallow flare ring, then five stepped courses
    up to a long ridge with short hips. Closed underneath by a soffit."""
    yr=(y0+y1)/2
    r0=[(x0,y0,ze),(x1,y0,ze),(x1,y1,ze),(x0,y1,ze)]
    r1=[(x0+.5,y0+.5,ze+.15),(x1-.5,y0+.5,ze+.15),(x1-.5,y1-.5,ze+.15),(x0+.5,y1-.5,ze+.15)]
    r2=[(x0+.9,y0+1.0,ze+.40),(x1-.9,y0+1.0,ze+.40),(x1-.9,y1-1.0,ze+.40),(x0+.9,y1-1.0,ze+.40)]
    rt=[(rx0,yr,zr),(rx1,yr,zr),(rx1,yr,zr),(rx0,yr,zr)]
    lerp=lambda a,b,t:tuple(a[i]+(b[i]-a[i])*t for i in range(3))
    rows=5
    rings=[r0,r1,r2]+[[lerp(r2[k],rt[k],(i+1)/rows) for k in range(4)] for i in range(rows)]
    stepped_rows(m,rings,key,'shr_bark_d')
    m.poly([(x,y,ze-.04) for x,y,_ in r0][::-1],under)
    for k in range(4):
        for a,b in zip(rings[:-1],rings[1:]):
            if np.linalg.norm(np.array(a[k])-np.array(b[k]))>1e-6:m.beam(a[k],b[k],.13,.13,'shr_ridge')
    m.box((0,yr,zr+.04),(rx1-rx0+.4,.36,.24),'shr_ridge',.05)
    m.box((0,yr,zr+.21),(rx1-rx0+.3,.24,.10),'shr_pale',.02)


def gable_rows(m,xs,y0,y1,ze,zr,rows=4,key='shr_bark',under='shr_verm'):
    """Straight gable slopes (ridge along Y at x=0) with the same stepped courses as the main roof."""
    for s in [-1,1]:
        rings=[]
        for i in range(rows+1):
            t=i/rows;xa=s*xs*(1-t);za=ze+(zr-ze)*t
            ring=[(xa,y0,za),(xa,y1,za)]
            rings.append(ring if s<0 else ring[::-1])
        stepped_rows(m,[[r[0],r[1]] for r in rings],key,'shr_bark_d')
        p=[(s*xs,y0,ze-.035),(s*xs,y1,ze-.035),(0,y1,zr-.035),(0,y0,zr-.035)]
        face(m,p,under,(0,0,-1))


def komainu(m,x,y,z,text,lettering,mouth):
    """Carved plinth with a bold dedication tablet and a seated lion-dog facing the street: chest wedge, low body,
    haunches, round lathe head with a cone snout, tiny ears, a collar of mane curls, chest curls, bushy tail."""
    m.box((x,y,z+.03),(.97,.97,.06),'shr_stone_d')
    m.box((x,y,z+.475),(.85,.85,.95),'shr_stone')
    m.box((x,y,z+1.0),(.93,.93,.08),'shr_stone_l',.02)
    m.box((x,y-.44,z+.50),(.70,.03,.80),'shr_stone_l')
    bold(m,text,(x,y-.47,z+.20),.60,'shr_plinth_ink',lettering,.01,.01)
    si=-1 if x>0 else 1                                             # inner side faces the stair
    m.box((x+si*.44,y,z+.50),(.03,.70,.80),'shr_stone_l')
    with m.at((0,0,0),si*90):
        bold(m,text,(si*y,-si*(x+si*.47),z+.20),.60,'shr_plinth_ink',lettering,.01,.01)
    z0=z+1.04;s='shr_stone'
    m.box((x,y+.08,z0+.25),(.50,.70,.50),s,.08)                     # body
    m.box((x,y+.22,z0+.28),(.58,.34,.40),s,.06)                     # haunches
    # chest wedge from the forelegs up to the shoulders
    face(m,[(x-.22,y-.34,z0+.01),(x+.22,y-.34,z0+.01),(x+.18,y-.18,z0+.62),(x-.18,y-.18,z0+.62)],s,(0,-1,0))
    for sx in [-1,1]:
        face(m,[(x+sx*.22,y-.34,z0+.01),(x+sx*.22,y-.10,z0+.01),(x+sx*.18,y-.18,z0+.62)],s,(sx,0,0))
    for dx in [-.15,.15]:
        m.box((x+dx,y-.32,z0+.22),(.13,.15,.44),s,.03)              # forelegs
        m.box((x+dx,y-.38,z0+.05),(.16,.22,.10),s,.02)              # paws
    hy=y-.24
    m.lathe((x,hy,z0+.66),[(0,0),(.08,.16),(.18,.21),(.28,.19),(.36,.10),(.40,0)],s,10)   # round head
    cone_y(m,(x,hy-.16,z0+.82),.16,.10,.06,s,8)                       # snout
    for dx in [-.08,.08]:m.box((x+dx,hy-.185,z0+.92),(.05,.04,.04),'shr_dark')   # eyes
    for dx in [-.13,.13]:m.box((x+dx,hy+.12,z0+.99),(.06,.08,.05),s,.01)         # ear nubs swept back
    if mouth:m.box((x,hy-.325,z0+.785),(.12,.04,.06),'shr_dark')       # open mouth
    for j in range(10):                                              # collar of mane curls around the head rim
        a=j*math.tau/10;m.lathe((x+math.cos(a)*.24,hy+math.sin(a)*.24,z0+.62),[(0,0),(.05,.07),(.10,.05),(.14,0)],'shr_mane',6)
    for j in range(6):                                               # second row of smaller curls on the chest
        a=math.pi+j*math.pi/5;m.lathe((x+math.cos(a)*.17,y-.20+math.sin(a)*.05,z0+.52),[(0,0),(.035,.05),(.07,.035),(.10,0)],'shr_mane',6)
    m.lathe((x,y+.40,z0+.25),[(0,.06),(.15,.12),(.30,.14),(.42,.08),(.50,0)],'shr_mane',8)   # tail
    m.collider((x,y,z+.6),(.97,.97,1.2));m.collider((x,y-.05,z+1.78),(.6,.95,1.1))


def stone_lantern(m,x,y,z):
    m.lathe((x,y,z),[(0,.40),(.12,.40),(.16,.30),(.24,.28),(.30,.15),(1.30,.13),(1.34,.26),(1.42,.32),(1.52,.30)],'shr_stone',6)
    m.box((x,y,z+1.77),(.44,.44,.50),'shr_stone_l',.03)
    m.box((x,y-.225,z+1.77),(.20,.02,.24),'arc_shopglass')
    m.lathe((x,y,z),[(2.00,.48),(2.12,.40),(2.34,.16),(2.40,.10),(2.52,.06),(2.60,0)],'shr_stone',6)
    m.collider((x,y,z+1.3),(.8,.8,2.6))


def water_basin(m,x,y,z):
    """Small waist-high chamfered stone trough on a kerb slab with standing water, bamboo spout and a dipper rack,
    under a delicate dark-timber pavilion with a green pyramid roof."""
    m.box((x,y,z+.04),(1.0,.70,.08),'shr_stone_l')
    zb=z+.08
    for dy in [-.235,.235]:m.box((x,y+dy,zb+.275),(.80,.08,.55),'shr_stone',.04)
    for dx in [-.36,.36]:m.box((x+dx,y,zb+.275),(.08,.55,.55),'shr_stone',.04)
    m.box((x,y,zb+.22),(.66,.42,.44),'shr_stone_d')
    m.box((x,y,z+.60),(.66,.41,.03),'blue')
    m.beam((x+.30,y+.26,zb),(x+.30,y+.26,zb+.95),.06,.06,'shr_bamboo')
    m.beam((x+.30,y+.26,zb+.90),(x-.02,y+.08,zb+.84),.06,.06,'shr_bamboo')
    for dx in [-.06,.06]:m.beam((x+dx,y-.33,z+.66),(x+dx,y+.33,z+.66),.03,.03,'shr_pale')   # dipper rack rods
    m.beam((x-.30,y-.30,z+.70),(x+.20,y+.10,z+.72),.03,.03,'shr_pale')                     # ladle handle
    m.lathe((x+.20,y+.10,z+.68),[(0,.02),(.03,.06),(.08,.07)],'shr_pale',8)                 # ladle cup
    for dx in [-.45,.45]:
        for dy in [-.45,.45]:
            m.box((x+dx,y+dy,z+.80),(.09,.09,1.60),'shr_timber')
            m.collider((x+dx,y+dy,z+.80),(.12,.12,1.6))
    for dy in [-.45,.45]:m.box((x,y+dy,z+1.55),(1.0,.10,.10),'shr_timber')
    for dx in [-.45,.45]:m.box((x+dx,y,z+1.55),(.10,1.0,.10),'shr_timber')
    a=(x,y,z+2.10);c=[(x-.72,y-.72,z+1.60),(x+.72,y-.72,z+1.60),(x+.72,y+.72,z+1.60),(x-.72,y+.72,z+1.60)]
    for k in range(4):
        m.poly([c[k],c[(k+1)%4],a],'shr_green')
        m.beam(c[k],c[(k+1)%4],.12,.10,'shr_timber')
        m.beam(c[k],a,.08,.08,'shr_timber')
    m.poly([(px,py,pz-.03) for px,py,pz in c][::-1],'shr_timber')
    m.lathe(a,[(0,.08),(.07,.05),(.12,.08),(.17,.04),(.24,0)],'shr_timber',6)
    m.collider((x,y,z+.32),(1.0,.70,.64))
    arcade.flowers(m,x+.55,y-.60,z+.02,5)


def fox(m,cx,cy,zz,d,out):
    """Sitting fox silhouette on one banner face: upright body ellipse, head, ears, big curled tail."""
    P=lambda ex,ez:(cx+ex*d,cy,zz+ez)
    body=[P(math.cos(k*math.tau/8)*.13,math.sin(k*math.tau/8)*.24) for k in range(8)]
    face(m,body,'shr_fox',out)
    face(m,[P(-.02,.16),P(.14,.24),P(.18,.36),P(.02,.40),P(-.14,.30)],'shr_fox',out)       # head
    face(m,[P(-.10,.34),P(-.16,.50),P(-.02,.40)],'shr_fox',out)                            # ear
    face(m,[P(.04,.40),P(.11,.54),P(.15,.36)],'shr_fox',out)                               # ear
    face(m,[P(-.08,-.20),P(-.30,-.28),P(-.32,-.02),P(-.16,.06)],'shr_fox',out)             # curled tail
    face(m,[P(.08,-.22),P(.22,-.24),P(.20,-.10),P(.10,-.06)],'shr_fox',out)                # forepaw


def banner(m,x,y,z,inward,text,has_fox,lettering):
    """Bamboo pole with crossbar and finial holding a 0.8 x 2.6 m cream banner: four bold ink characters over the upper
    part and a yellow sitting fox near the hem, on both faces."""
    m.beam((x,y,z),(x,y,z+4.3),.09,.09,'shr_bamboo')
    for zz in [z+1.45,z+2.95]:m.lathe((x,y,zz),[(0,.055),(.06,.055)],'shr_node',8)
    m.lathe((x,y,z+4.3),[(0,.06),(.05,.085),(.12,.05),(.20,0)],'shr_bamboo',6)
    m.beam((x-inward*.07,y,z+4.12),(x+inward*.85,y,z+4.12),.05,.05,'shr_bamboo')
    m.collider((x,y,z+2.15),(.12,.12,4.3))
    cy=y-.06;xa=x+inward*.05;xb=x+inward*.85;cx=(xa+xb)/2
    top=z+4.06;bot=top-2.6
    p=[(xa,cy,bot),(xb,cy,bot),(xb,cy,top),(xa,cy,top)]
    face(m,p,'shr_cloth',(0,-1,0));face(m,p,'shr_cloth',(0,1,0))
    for i,ch in enumerate(text):
        zc=top-.38-i*.39
        bold(m,ch,(cx,cy-.03,zc),.44,'shr_ink',lettering)
        with m.at((0,0,0),180):bold(m,ch,(-cx,-cy-.03,zc),.44,'shr_ink',lettering)
    if has_fox:
        zz=bot+.34
        fox(m,cx,cy-.03,zz,inward,(0,-1,0));fox(m,cx,cy+.03,zz,inward,(0,1,0))


def torii(m):
    """Broad vermilion entrance gate, with an open walkable 7 m span."""
    y=-8.0
    for side in (-1,1):
        x=side*4.0
        m.box((x,y,-.04),(.96,.90,.36),'shr_stone',.035)
        m.lathe((x,y,.14),[(0,.35),(.12,.35),(.15,.28)],'shr_stone_d',12)
        # Very subtle inward taper, stone feet embedded below pavement level.
        m.beam((x,y,.22),(x-side*.10,y,4.95),.43,.43,'shr_verm')
        m.collider((x-side*.05,y,2.45),(.55,.55,4.9))
        m.box((x-side*.10,y,4.64),(.62,.66,.20),'shr_verm_dark')
    m.box((0,y,3.83),(8.75,.33,.30),'shr_verm')
    m.box((0,y,4.68),(9.30,.55,.35),'shr_verm')
    # Five joined segments give the dark capping beam a restrained upward sweep.
    points=[(-5.0,5.15),(-3.8,4.99),(-1.9,4.94),(1.9,4.94),(3.8,4.99),(5.0,5.15)]
    for (xa,za),(xb,zb) in zip(points,points[1:]):
        m.beam((xa,y,za),(xb,y,zb),.72,.25,'shr_bark_d')
    m.box((0,y-.19,4.27),(.55,.15,.66),'shr_verm_dark')


def build(name,variant,lettering):
    var=VARIANTS[variant%len(VARIANTS)];palette(var);r=random.Random(31+variant)
    m=v.Mesh(name)
    torii(m)
    # ---- stone terrace over the whole 7x7 lot with a coping bead, two broad pale steps down to the pavement,
    # curbed gravel court of raised pale cobbles.
    m.box((0,0,-.11),(7.0,7.0,.58),'shr_stone')
    m.box((0,0,.245),(7.04,7.04,.12),'shr_stone_l')
    m.collider((0,0,.15),(7.0,7.0,.3))
    for y in [-3.47,3.47]:m.box((0,y,.355),(7.04,.10,.10),'shr_stone_l',.02)
    for x in [-3.47,3.47]:m.box((x,0,.355),(.10,7.04,.10),'shr_stone_l',.02)
    for yc,top in [(-3.71,.22),(-4.09,.12)]:
        m.box((0,yc,(top-.04-.4)/2),(7.04,.38,top-.04+.4),'shr_stone')
        m.box((0,yc,top-.02),(7.04,.40,.04),'shr_stone_l')
        m.collider((0,yc,top/2),(7.04,.38,top))
    m.box((0,-2.2,.305),(5.6,2.2,.03),'shr_gravel')
    for dy in [-1.16,1.16]:m.box((0,-2.2+dy,.33),(5.84,.12,.08),'shr_stone_d')
    for dx in [-2.86,2.86]:m.box((dx,-2.2,.33),(.12,2.44,.08),'shr_stone_d')
    for i in range(150):
        xx=r.uniform(-2.7,2.7);yy=r.uniform(-3.2,-1.2);rr=r.uniform(.06,.10);a=r.random()*math.tau;n=r.choice([4,5,5,6])
        m.poly([(xx+math.cos(a+k*math.tau/n)*rr*r.uniform(.8,1.2),yy+math.sin(a+k*math.tau/n)*rr*r.uniform(.8,1.2),.335) for k in range(n)],v.color_variant('shr_pebble',.12))
    for i in range(16):
        xx=r.uniform(-3.3,3.3);yy=r.uniform(-5.8,-1.2);zz=.34 if yy>-3.5 else (.23 if yy>-3.9 else (.13 if yy>-4.28 else .012))
        a=r.random()*math.tau
        m.poly([(xx+math.cos(a+k*2.1)*.09,yy+math.sin(a+k*2.1)*.09,zz) for k in range(3)],'arc_leaf')
    # ---- raised timber floor on vermilion posts over a dark slatted underfloor skirt.
    m.box((0,1.05,.65),(5.5,3.7,.66),'shr_under')
    for k in range(5):
        zz=.40+.12*k
        m.box((0,-.82,zz),(5.3,.04,.07),'shr_wood')
        for sx in [-1,1]:m.box((sx*2.77,1.05,zz),(.04,3.5,.07),'shr_wood')
    for x in [-2.95,-1.2,1.2,2.95]:
        for y in [-.95,1.0,3.05]:m.box((x,y,.64),(.18,.18,.74),'shr_verm')
    m.box((0,1.05,1.10),(6.34,4.24,.22),'shr_verm')
    m.box((0,1.05,1.215),(6.2,4.1,.03),'shr_wood')
    m.collider((0,1.05,.615),(6.34,4.24,1.23))
    # ---- hall walls: warm plaster panels framed by vermilion posts, deep doorway with a warm-lit sanctuary.
    m.box((0,1.6,2.475),(6.0,2.8,2.49),'shr_plaster')
    for x in [-1.925,1.925]:m.box((x,-.05,2.475),(2.15,.5,2.49),'shr_plaster')
    m.box((0,.17,2.475),(1.9,.06,2.49),'wood_dark')
    m.box((0,.12,2.30),(1.5,.04,1.8),'arc_paper')
    for x in [-.5,0,.5]:m.box((x,.09,2.30),(.05,.03,1.8),'wood_dark')
    for zz in [1.42,1.87,2.32,2.77,3.18]:m.box((0,.09,zz),(1.5,.03,.05),'wood_dark')
    for x in [-.77,.77]:m.box((x,-.05,2.4),(.16,.54,2.32),'wood_dark')
    m.box((0,-.06,1.29),(1.9,.52,.12),'shr_verm')
    m.box((0,-.05,3.56),(2.02,.5,.34),'wood_dark')
    # altar: dark shelf, two cream sake bottles, a gold mirror on a stand, two small lanterns inside the doorway.
    m.box((0,-.08,1.75),(1.2,.40,.08),'shr_timber')
    for dx in [-.25,.25]:m.lathe((dx,-.10,1.79),[(0,.05),(.14,.06),(.19,.03),(.27,.02),(.29,0)],'shr_cream',8)
    m.beam((0,.02,1.79),(0,.02,1.96),.05,.05,'shr_timber');m.box((0,.02,1.81),(.20,.12,.04),'shr_timber')
    disc=[(math.cos(k*math.tau/12)*.14,.02,2.05+math.sin(k*math.tau/12)*.14) for k in range(12)]
    both(m,disc,'shr_gold')
    for dx in [-.6,.6]:arcade.lantern(m,dx,-.14,2.72,.22)
    m.collider((0,1.35,2.5),(6.3,3.5,2.6))
    # Offering box on the porch with slatted lid.
    m.box((0,-.62,1.46),(1.3,.55,.48),'wood_dark',.02)
    for x in np.linspace(-.5,.5,6):m.box((float(x),-.62,1.72),(.07,.5,.05),'shr_wood')
    m.box((0,-.62,1.71),(1.34,.59,.04),'shr_wood')
    zc=2.475;hh=2.5
    # Front frame with gold bracket blocks under the eave beam.
    for x in [-3.0,-1.0,1.0,3.0]:
        m.box((x,-.36,zc),(.2,.2,hh),'shr_verm')
        m.box((x,-.52,3.62),(.16,.16,.16),'shr_gold_l',.02)
    m.box((0,-.36,3.83),(6.4,.22,.22),'shr_verm');m.box((0,-.36,1.33),(6.4,.22,.2),'shr_verm')
    # Side frames, lattice windows with a faint warm glow, mid rails.
    for s in [-1,1]:
        x=s*3.06
        for y in [-.3,1.35,3.0]:m.box((x,y,zc),(.2,.2,hh),'shr_verm')
        m.box((x,1.35,3.83),(.22,3.5,.22),'shr_verm');m.box((x,1.35,1.33),(.22,3.5,.2),'shr_verm')
        m.box((x,1.35,2.55),(.16,3.3,.12),'shr_verm')
        for y in [.5,2.2]:
            m.box((s*3.12,y,2.35),(.06,1.1,.9),'arc_shopglass')
            for k in range(5):m.box((s*3.16,y-.44+k*.22,2.35),(.05,.06,.9),'shr_verm')
            m.box((s*3.16,y,1.86),(.06,1.2,.08),'shr_verm')
    # Back frame with a vent panel and a small service door.
    for x in [-3.0,-1.0,1.0,3.0]:m.box((x,3.06,zc),(.2,.2,hh),'shr_verm')
    m.box((0,3.06,3.83),(6.4,.22,.22),'shr_verm');m.box((0,3.06,1.33),(6.4,.22,.2),'shr_verm')
    m.box((0,3.06,2.55),(6.2,.16,.12),'shr_verm')
    m.box((2.0,3.12,3.2),(1.4,.06,.5),'window')
    for k in range(7):m.box((1.4+k*.2,3.16,3.2),(.05,.06,.5),'shr_verm')
    m.box((-2.0,3.12,2.2),(.9,.06,1.9),'wood_dark')
    for k in range(4):m.box((-2.38+k*.25,3.16,2.2),(.15,.03,1.85),'shr_wood')
    # Rear service entrance: six supported 18 cm treads to the raised floor.
    # Keep the outermost tread inside the existing y=4.5 m support pad.
    for i in range(6):
        top=1.08-i*.18;yc=3.28+i*.22
        m.box((-2.0,yc,(top-.08)/2),(1.2,.22,top+.08),'shr_stone_l')
        m.collider((-2.0,yc,top/2),(1.2,.22,top))
    # ---- broad low hipped cypress-bark roof (~30 deg) with a long ridge, wide eaves, fascia, vermilion rafters, chigi.
    ze=3.99;zr=5.45;yr=1.1;X=4.3;Y0=-1.9;Y1=4.1
    hip_roof(m,-X,X,Y0,Y1,ze,zr,-3.2,3.2)
    m.box((0,Y0,3.85),(2*X,.14,.30),'shr_fascia');m.box((0,Y1,3.85),(2*X,.14,.30),'shr_fascia')
    for x in [-X,X]:m.box((x,yr,3.85),(.14,Y1-Y0,.30),'shr_fascia')
    for x in np.linspace(-3.6,3.6,13):
        m.box((float(x),(-.36+Y0)/2,3.88),(.09,Y0*-1-.36,.10),'shr_verm')
        m.box((float(x),(3.06+Y1)/2,3.88),(.09,Y1-3.06,.10),'shr_verm')
    for y in np.linspace(-1.5,3.7,11):
        for s in [-1,1]:m.box((s*(3.06+X)/2,float(y),3.88),(X-3.06,.09,.10),'shr_verm')
    for x in [-2.9,2.9]:
        m.beam((x,yr-.70,zr-.75),(x,yr+.70,zr+1.10),.14,.22,'shr_pale')
        m.beam((x,yr+.70,zr-.75),(x,yr-.70,zr+1.10),.14,.22,'shr_pale')
        zx=zr+.175
        for s in [-1,1]:
            xx=x+s*.115
            pts=[(xx,yr+math.cos(k*math.tau/12)*.26,zx+math.sin(k*math.tau/12)*.26) for k in range(12)]
            m.poly(pts if s>0 else pts[::-1],'shr_pale')
        m.box((x,yr,zx),(.22,.28,.28),'shr_pale',.05)
    # ---- wide gabled vermilion porch canopy over the stair on two stout posts, gold bracket frieze under both headers.
    xs=2.6;ce=3.42;cr=4.25;y0=-3.9;y1=-.85
    for s in [-1,1]:
        m.box((s*1.75,-2.6,1.90),(.24,.24,3.2),'shr_verm');m.collider((s*1.75,-2.6,1.90),(.24,.24,3.2))
        m.box((s*1.75,-1.45,3.2),(.16,2.3,.2),'shr_verm')
        m.box((s*1.75,-2.6,.385),(.5,.5,.16),'shr_stone_l',.02)
        m.box((s*1.75,-2.6,3.42),(.24,.24,.22),'shr_gold',.03)
        m.box((s*1.75,-.30,3.2),(.10,.10,.10),'shr_gold')
    m.box((0,-2.6,3.2),(3.7,.16,.2),'shr_verm')
    for s in [-1,1]:m.box((s*1.90,-2.6,3.2),(.10,.10,.10),'shr_gold')
    gable_rows(m,xs,y0,y1,ce,cr)
    m.box((0,(y0+y1)/2,cr+.03),(.18,y1-y0+.04,.16),'shr_ridge')
    for s in [-1,1]:
        m.box((s*xs,(y0+y1)/2,ce-.02),(.14,y1-y0+.04,.16),'shr_fascia')
        m.beam((s*xs,y0,ce),(0,y0,cr),.12,.14,'shr_verm')
        m.beam((s*xs,y1,ce),(0,y1,cr),.12,.14,'shr_verm')
    both(m,[(-xs,y0+.01,ce),(xs,y0+.01,ce),(0,y0+.01,cr)],'shr_gable')
    face(m,[(-xs,y1-.01,ce),(xs,y1-.01,ce),(0,y1-.01,cr)],'shr_gable',(0,1,0))
    m.box((0,y0-.02,(ce+cr)/2),(.12,.04,cr-ce),'shr_verm')                       # king post
    for yh in [-3.45,-1.0]:
        m.box((0,yh,ce),(5.2,.12,.16),'shr_verm')                                  # headers under the eaves
        for x in np.linspace(-1.8,1.8,5):m.box((float(x),yh,ce-.16),(.16,.16,.16),'shr_gold',.02)   # gold frieze
    for x in np.linspace(-2.3,2.3,11):m.box((float(x),-3.45,ce+.10),(.09,.55,.10),'shr_verm')     # rafter tails
    # Big vertical name plaque hung over the gable face and king post.
    m.box((0,-3.95,3.65),(.70,.06,1.60),'shr_gold',.02)
    m.box((0,-3.985,3.65),(.60,.05,1.48),'shr_dark')
    for i,ch in enumerate(var['name']):bold(m,ch,(0,-4.02,3.98-i*.35),.34,'shr_gold_l',lettering,.015,.015)
    # Shimenawa: thick sagging straw rope with paper shide and hanging straw tassels; big bell and a fat
    # red/white braided bell rope ending in a tassel.
    m.beam((-1.75,-2.72,2.95),(-.6,-2.72,2.88),.18,.18,'shr_straw')
    m.beam((-.6,-2.72,2.88),(.6,-2.72,2.88),.34,.34,'shr_straw')
    m.beam((.6,-2.72,2.88),(1.75,-2.72,2.95),.18,.18,'shr_straw')
    for x in [-.35,.35]:m.box((x,-2.72,2.56),(.18,.03,.45),'shr_shide')
    for x in [-1.05,1.05]:m.box((x,-2.72,2.62),(.18,.03,.45),'shr_shide')
    for x in [-.7,.7]:m.beam((x,-2.72,2.72),(x,-2.72,2.22),.08,.08,'shr_straw')
    m.box((0,-2.0,3.90),(.06,.06,.72),'shr_wood')
    m.lathe((0,-2.0,3.30),[(0,.08),(.06,.26),(.22,.26),(.32,.16),(.38,0)],'shr_gold',12)
    zt=1.23+.40;ztop=zt+.48;seg=(3.30-ztop)/8
    for i in range(8):m.beam((0,-2.0,3.30-i*seg),(0,-2.0,3.30-(i+1)*seg),.20,.20,['shr_verm','shr_rope'][i%2])
    m.lathe((0,-2.0,zt),[(0,0),(.06,.12),(.18,.18),(.38,.16),(.48,.06)],'shr_verm',10)
    for s in [-1,1]:
        arcade.lantern(m,s*2.17,-2.55,2.35,.42)
        m.beam((s*1.75,-2.55,3.40),(s*2.17,-2.55,3.40),.06,.06,'shr_verm')
    # ---- stair (five risers) with vermilion railings, veranda rails either side.
    for k in range(5):
        top=1.23-.155*(k+1);y=-1.05-.3*(k+.5)
        m.box((0,y,(top+.28)/2),(2.2,.3,top-.28),'shr_wood')
        m.collider((0,y,(top+.28)/2),(2.2,.3,top-.28))
        m.box((0,y-.15,top-.02),(2.22,.04,.05),'wood_light')
    for s in [-1,1]:
        x=s*1.2
        m.box((x,-1.1,1.68),(.11,.11,.9),'shr_verm');m.box((x,-2.62,.9),(.11,.11,.9),'shr_verm')
        m.beam((x,-1.1,2.08),(x,-2.62,1.30),.08,.10,'shr_verm')
        m.beam((x,-1.1,1.68),(x,-2.62,.90),.06,.06,'shr_verm')
        m.box((s*3.05,-1.1,1.63),(.11,.11,.8),'shr_verm')
        m.box((s*2.12,-1.1,2.0),(1.95,.08,.10),'shr_verm');m.box((s*2.12,-1.1,1.55),(1.95,.06,.06),'shr_verm')
    # ---- props on the terrace and apron.
    komainu(m,-2.35,-2.85,.32,var['plinth'][0],lettering,False)
    komainu(m,2.35,-2.85,.32,var['plinth'][1],lettering,True)
    stone_lantern(m,3.0,-5.0,-.02)
    water_basin(m,-4.5,-5.0,-.02)
    for s in [-1,1]:banner(m,s*3.3,-3.75,.20,-s,var['name'],var['fox'],lettering)
    m.box((1.75,-5.05,.13),(1.4,.8,.30),'shr_stone',.03);m.box((1.75,-5.05,.29),(1.3,.7,.04),'soil')
    for j,x in enumerate([1.35,1.75,2.15]):arcade.flowers(m,x,-5.05,.3,variant*7+j,root_spread=(.19,.27))
    m.collider((1.75,-5.05,.14),(1.4,.8,.3))
    for s in [-1,1]:v.pot(m,s*3.2,-1.4,.3,.75,'clay',plant=True)
    return m
