"""Model the five reference buildings, village furniture and continuous lane.

blender -b --threads 6 --python-exit-code 1 --python games/yorimichi/world/regions/village/build.py
All visible parts share one opaque vertex-colour material. Exported meshes
include deliberately simple UCX volumes; furniture never blocks the lane.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import hashlib, json, math, random, sys
from pathlib import Path
from contextlib import contextmanager
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE=Path(__file__).resolve().parent
ROOT=yori.REGIONS
from village.layout import BUILDINGS, nearest, sample, upper_surface, smooth, plane, village_point, FOREST_OFFSET_Y
OUT=yori.OUT/'village'
PALETTE={
 'plaster':(.46,.31,.15), 'plaster_light':(.59,.43,.23),
 'wood':(.062,.024,.007), 'wood_light':(.19,.083,.021), 'wood_dark':(.026,.014,.008),
 'roof':(.024,.036,.052), 'roof_edge':(.013,.021,.031),
 'green':(.105,.16,.027), 'green_dark':(.065,.095,.021),
 'stone':(.18,.175,.13), 'stone_light':(.28,.255,.18),
 'paper':(.92,.58,.22), 'window':(.36,.20,.09),
 'rust':(.62,.12,.035), 'clay':(.46,.235,.085), 'bluepot':(.18,.27,.30),
 'metal':(.085,.085,.075), 'leaf':(.019,.060,.010), 'water':(.06,.14,.095),
 'lane':(.26,.14,.046), 'soil':(.09,.073,.031),
 'well_stone':(.30,.235,.15), 'well_cap':(.38,.31,.22),
}
R=random.Random(76)

class Mesh:
    def __init__(self,name):
        self.name=name;self.vertices=[];self.faces=[];self.colors=[];self.transform=Matrix.Identity(4)
        self.colliders=[];self.keys=[]   # keys: each face's palette key, None for a colour given as a tuple
    @contextmanager
    def at(self,position=(0,0,0),yaw=0):
        old=self.transform.copy()
        self.transform=old @ Matrix.Translation(Vector(position)) @ Matrix.Rotation(math.radians(yaw),4,'Z')
        try:yield
        finally:self.transform=old
    def poly(self,points,color):
        points=[Vector(p) for p in points]
        clean=[]
        for p in points:
            if not any((p-q).length_squared<1e-16 for q in clean):clean.append(p)
        if len(clean)<3:return
        if sum((clean[k]-clean[0]).cross(clean[k+1]-clean[0]).length for k in range(1,len(clean)-1))<1e-10:return
        points=clean;self.keys.append(color if isinstance(color,str) else None)
        if isinstance(color,str):color=PALETTE[color]
        i=len(self.vertices)
        self.vertices.extend(tuple(self.transform@Vector(p)) for p in points)
        self.faces.append(tuple(range(i,i+len(points))))
        # Alpha is reserved for pinned cloth wind; ordinary masonry is stationary.
        self.colors.extend([(*color,0)]*len(points))
    def box(self,c,s,color,bevel=0):
        x,y,z=c;w,d,h=s
        if bevel:
            b=min(bevel,w/3,d/3,h/3)
            outline=[(-w/2+b,-d/2),(w/2-b,-d/2),(w/2,-d/2+b),(w/2,d/2-b),
                     (w/2-b,d/2),(-w/2+b,d/2),(-w/2,d/2-b),(-w/2,-d/2+b)]
            rings=[]
            for zz,scale in [(-h/2,.94),(-h/2+b,1),(h/2-b,1),(h/2,.94)]:
                rings.append([(x+px*scale,y+py*scale,z+zz) for px,py in outline])
            self.poly(list(reversed(rings[0])),color);self.poly(rings[-1],color)
            for a,b in zip(rings[:-1],rings[1:]):
                for k in range(8):self.poly([a[k],a[(k+1)%8],b[(k+1)%8],b[k]],color)
            return
        p=[(x+dx*w/2,y+dy*d/2,z+dz*h/2) for dx,dy,dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:self.poly([p[i] for i in f],color)
    def beam(self,a,b,width,depth,color):
        a,b=Vector(a),Vector(b);v=b-a
        old=self.transform.copy()
        self.transform=old@Matrix.Translation((a+b)/2)@v.to_track_quat('Z','Y').to_matrix().to_4x4()
        self.box((0,0,0),(width,depth,v.length),color)
        self.transform=old
    def lathe(self,center,profile,color,n=12):
        x,y,z=center
        rings=[[(x+r*math.cos(i*2*math.pi/n),y+r*math.sin(i*2*math.pi/n),z+zz) for i in range(n)] for zz,r in profile]
        for a,b in zip(rings[:-1],rings[1:]):
            for k in range(n):self.poly([a[k],a[(k+1)%n],b[(k+1)%n],b[k]],color)
    def collider(self,c,s):
        self.colliders.append((tuple(self.transform@Vector(c)),s,self.transform.to_euler()))
    def object(self,material):
        data=bpy.data.meshes.new(self.name);data.from_pydata(self.vertices,[],self.faces);data.update()
        data.materials.append(material)
        # Valid dominant-plane UVs also provide non-degenerate MikkTSpace tangents.
        uv=data.uv_layers.new(name='UVMap')
        for face in data.polygons:
            drop=max(range(3),key=lambda i:abs(face.normal[i]))
            axes=[i for i in range(3) if i!=drop]
            for li in face.loop_indices:
                co=data.vertices[data.loops[li].vertex_index].co
                uv.data[li].uv=(co[axes[0]],co[axes[1]])
        col=data.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
        building=self.name in {b[0] for b in BUILDINGS}
        for i,c in enumerate(self.colors):
            # Broad ground-contact weathering, kept free of texture grain.
            shade=.62+.38*float(smooth((self.vertices[i][2]+.3)/1.0)) if building else 1.
            col.data[i].color=(*(v*shade for v in c[:3]),c[3])
        if self.name=='Village_Ground':
            # The duplicated corners carry individual palette colours, so mesh
            # auto-smoothing cannot share their normals. Supply the continuous
            # heightfield gradient instead of exposing every diagonal triangle.
            xy=np.array(self.vertices)[:,:2];x=xy[:,0];y=xy[:,1];eps=.6
            dx=(sample(HEIGHTS,x+eps,y)-sample(HEIGHTS,x-eps,y))/(2*eps)
            dy=(sample(HEIGHTS,x,y+eps)-sample(HEIGHTS,x,y-eps))/(2*eps)
            normals=np.column_stack([-dx,-dy,np.ones(len(x))]);normals/=np.linalg.norm(normals,axis=1)[:,None]
            for face in data.polygons:face.use_smooth=True
            data.normals_split_custom_set_from_vertices(normals.tolist())
        obj=bpy.data.objects.new(self.name,data);bpy.context.collection.objects.link(obj)
        return obj


def color_variant(key,amount=.05):
    f=R.uniform(1-amount,1+amount)
    return tuple(min(1,c*f) for c in PALETTE[key])


def window(m,x,y,z,w=1.45,h=1.35,glow=False):
    m.box((x,y,z),(w+.16,.10,h+.16),'wood_dark')
    m.box((x,y-.065,z),(w,.055,h),'paper' if glow else 'window')
    for xx in (x-w/2,x+w/2):m.box((xx,y-.12,z),(.095,.13,h+.13),'wood')
    for zz in (z-h/2,z+h/2):m.box((x,y-.12,zz),(w+.18,.16,.10),'wood_light')
    for i in range(1,4):m.box((x-w/2+w*i/4,y-.125,z),(.055,.075,h),'wood')
    for i in range(1,3):m.box((x,y-.13,z-h/2+h*i/3),(w,.07,.055),'wood')
    m.box((x,y-.20,z-h/2-.10),(w+.3,.36,.13),'wood_light')


def door(m,x,y,z=.35,w=1.20,h=2.15):
    m.box((x,y,z+h/2),(w+.2,.11,h+.12),'wood_dark')
    for k in range(6):m.box((x-w/2+(k+.5)*w/6,y-.08,z+h/2),(w/6-.013,.055,h),color_variant('wood_light'))
    for xx in (x-w/2,x+w/2):m.box((xx,y-.16,z+h/2),(.12,.17,h+.13),'wood')
    for zz in (z+.4,z+h-.30):m.box((x,y-.13,zz),(w,.065,.10),'wood')
    m.box((x+w*.27,y-.19,z+1.0),(.07,.06,.23),'metal')


def foundation(m,w,d):
    m.box((0,0,-.31),(w+.18,d+.18,1.16),'stone')
    for side in (-1,1):
        for row in range(2):
            count=math.ceil(w/.9)
            for k in range(count):
                m.box((-w/2+(k+.5)*w/count,side*(d/2+.065),-.1+row*.23),(w/count-.025,.25,.225),color_variant('stone_light'),.04)
        for k in range(math.ceil(d/.9)):
            nn=math.ceil(d/.9)
            m.box((side*(w/2+.065),-d/2+(k+.5)*d/nn,.02),(.26,d/nn-.025,.44),color_variant('stone'),.04)


def shell(m,w,d,eave,timber=False):
    foundation(m,w,d)
    m.box((0,0,(eave+.24)/2),(w,d,eave-.24),'wood_dark' if timber else 'plaster')
    m.collider((0,0,(eave-.5)/2),(w,d,eave+.5))
    if timber:
        for side in (-1,1):
            for k in range(math.ceil(w/.32)):
                nn=math.ceil(w/.32)
                m.box((-w/2+(k+.5)*w/nn,side*(d/2+.02),(eave+.25)/2),(w/nn-.017,.065,eave-.25),color_variant('wood'))
    for xx in (-w/2,0,w/2):
        for yy in (-d/2-.035,d/2+.035):m.box((xx,yy,(eave+.28)/2),(.19,.18,eave-.28),'wood')
    for zz in (.4,eave-.12):
        for yy in (-d/2-.04,d/2+.04):m.box((0,yy,zz),(w+.18,.2,.18),'wood')
        for xx in (-w/2-.035,w/2+.035):m.box((xx,0,zz),(.18,d,.18),'wood')
    for xx in (-w/2-.04,w/2+.04):m.box((xx,0,(eave+.3)/2),(.17,.17,eave-.3),'wood')


def roof(m,w,d,eave,rise=1.65,key='roof'):
    """Thick, shallow-curved tiled gable. Three broad facets per tile roll."""
    w+=1.3;d+=1.35
    # Fill the full roof volume: the curved tile surface rises above its eave.
    m.poly([(-w/2,d/2,eave),(w/2,d/2,eave),(w/2,-d/2,eave),(-w/2,-d/2,eave)],'wood_dark')
    for side in (-1,1):
        points=[(side*(w/2-.65),-d/2+.67,eave-.04),(side*(w/2-.65),0,eave+rise+.03),(side*(w/2-.65),d/2-.67,eave-.04)]
        m.poly(points if side<0 else list(reversed(points)),'plaster')
    # Solid sloping soffit follows the tile arc, sealing the pale sky slivers
    # between the closed walls and overhanging tiles when viewed from below.
    for side in (-1,1):
        for row in range(8):
            t0=row/8;t1=(row+1)/8
            def underside(t):return eave+rise*(1-t)**1.10+.10*t**6-.035
            pts=[(-w/2,side*d/2*t0,underside(t0)),(w/2,side*d/2*t0,underside(t0)),
                 (w/2,side*d/2*t1,underside(t1)),(-w/2,side*d/2*t1,underside(t1))]
            m.poly(pts if side<0 else pts[::-1],'wood_dark')
    count=math.ceil(w/.48);rows=math.ceil((d/2)/.55)
    def zz(t):return eave+rise*(1-t)**1.10+.10*t**6
    for side in (-1,1):
        for row in range(rows):
            t0=row/rows;t1=(row+1)/rows
            for col in range(count):
                color=color_variant(key,.045)
                xa=-w/2+col*w/count
                for seg in range(3):
                    xx=[xa+seg*w/count/3,xa+(seg+1)*w/count/3]
                    arch=[.037*math.sin(math.pi*seg/3),.037*math.sin(math.pi*(seg+1)/3)]
                    points=[(xx[0],side*d/2*t0,zz(t0)+arch[0]+.028),(xx[1],side*d/2*t0,zz(t0)+arch[1]+.028),
                            (xx[1],side*d/2*t1,zz(t1)+arch[1]+.065),(xx[0],side*d/2*t1,zz(t1)+arch[0]+.065)]
                    if side<0:points.reverse()
                    m.poly(points,color)
                # Rolled overlapping tile edge: broad enough to read without fine lines.
                m.beam((xa,side*d/2*t1,zz(t1)+.046),(xa+w/count,side*d/2*t1,zz(t1)+.046),.045,.045,color)
        m.beam((-w/2,side*d/2,zz(1)),(w/2,side*d/2,zz(1)),.14,.20,'roof_edge' if key=='roof' else 'wood')
        for xx in (-w/2,w/2):
            for row in range(rows):
                m.beam((xx,side*d/2*row/rows,zz(row/rows)),(xx,side*d/2*(row+1)/rows,zz((row+1)/rows)),.14,.18,'roof_edge' if key=='roof' else 'wood')
        for xx in np.linspace(-w/2+.25,w/2-.25,math.ceil(w/.65)):
            m.beam((float(xx),side*(d/2-.9),eave+.24),(float(xx),side*(d/2-.06),eave-.02),.085,.11,'wood_light')
    for xx in (-w/2+.65,w/2-.65):
        m.beam((xx,-d/2+.68,eave+.02),(xx,0,eave+rise-.15),.15,.14,'wood')
        m.beam((xx,0,eave+rise-.15),(xx,d/2-.68,eave+.02),.15,.14,'wood')
        m.box((xx,0,eave+rise/2),(.15,.17,rise),'wood')
    m.box((0,0,eave+rise+.10),(w+.18,.23,.22),'roof_edge' if key=='roof' else 'wood',.035)
    for xx in (-w/2,w/2):m.box((xx,0,eave+rise+.20),(.23,.27,.34),'roof_edge' if key=='roof' else 'wood',.035)


def awning(m,x,y,z,w=2.1,depth=.65,key='wood_light'):
    points=[(x-w/2,y,z+.15),(x-w/2,y-depth,z-.1),(x+w/2,y-depth,z-.1),(x+w/2,y,z+.15)]
    m.poly(points,key)
    m.poly([(px,py,pz-.035) for px,py,pz in reversed(points)],'wood')
    m.beam((x-w/2,y-depth,z-.1),(x+w/2,y-depth,z-.1),.1,.10,'wood')
    for xx in (x-w/2+.15,x+w/2-.15):m.beam((xx,y,z-.50),(xx,y-depth,z-.1),.07,.075,'wood')


def lantern(m,x,y,z,size=.43):
    m.box((x,y,z+size*.65),(.045,.045,.35),'wood_dark')
    m.lathe((x,y,z),[(-size*.55,.11),(-size*.4,size*.40),(-size*.22,size*.5),(size*.22,size*.5),(size*.4,size*.40),(size*.55,.11)],'paper',12)
    for zz in (-size*.5,size*.5):m.lathe((x,y,z+zz),[(-.025,.115),(.025,.115)],'wood_dark',12)
    # Restrained ribs, large gaps: no tiny parallel line shimmer.
    for zz in (-size*.22,0,size*.22):m.lathe((x,y,z+zz),[(-.01,size*.504),(.01,size*.504)],(.57,.43,.24),12)


def pot(m,x,y,z=0,scale=1,key='clay',plant=False,form='jar'):
    with m.at((x,y,z)):
        profile=[(0,0),(.02,.19),(.13,.26),(.32,.30),(.49,.235),(.54,.21),(.60,.22),(.62,.18),(.56,.165),(.38,.16)]
        if form=='bowl':profile=[(0,0),(.02,.15),(.1,.24),(.25,.34),(.3,.36),(.32,.32),(.22,.27),(.07,.13)]
        if form=='bottle':profile=[(0,0),(.02,.19),(.22,.22),(.4,.20),(.51,.11),(.72,.08),(.75,.10),(.77,.065),(.69,.058)]
        if form=='urn':profile=[(0,0),(.03,.18),(.12,.29),(.40,.33),(.63,.26),(.69,.25),(.71,.21),(.61,.20)]
        profile.append((profile[-1][0],0))
        m.lathe((0,0,0),[(a*scale,b*scale) for a,b in profile],key)
        if plant:
            m.poly([(math.cos(i*2*math.pi/12)*.16*scale,math.sin(i*2*math.pi/12)*.16*scale,.39*scale) for i in range(12)],'soil')
            m.beam((0,0,.40*scale),(0,0,1.32*scale),.035,.035,'wood_light')
            for k in range(7):
                a=k*2.4;zz=(.65+k*.085)*scale
                tip=Vector((math.cos(a)*.35*scale,math.sin(a)*.35*scale,zz+.20*scale))
                base=Vector((0,0,zz));side=Vector((-math.sin(a),math.cos(a),0))*.075*scale
                m.poly([base,(base+tip)/2+side,tip,(base+tip)/2-side],color_variant('leaf',.16))
                m.poly([base,(base+tip)/2-side,tip,(base+tip)/2+side],'leaf')


def bench(m,x,y,z=0,w=1.8):
    for yy in (-.13,.13):m.box((x,y+yy,z+.43),(w,.23,.11),'wood_light')
    for xx in (-w*.36,w*.36):m.box((x+xx,y,z+.22),(.13,.43,.45),'wood')
    m.collider((x,y,z+.3),(w,.53,.60))


def cottage(m,w,d,variant):
    eave=3.25;shell(m,w,d,eave)
    y=-d/2-.12
    doorx=1.50 if variant=='A' else -1.6
    windowx=-1.30 if variant=='A' else .85
    door(m,doorx,y,w=1.25)
    window(m,windowx,y,1.78,w=1.7,glow=variant=='B')
    awning(m,doorx,y,2.7,1.65,.7)
    awning(m,windowx,y,2.75,2.0,.5)
    # Two supported 15 cm risers, with a generous bottom tread.
    for offset,top,depth in [(.55,.15,1.15),(.24,.30,.55)]:
        m.box((doorx,y-offset,(top-.08)/2),(1.75,depth,top+.08),'stone_light',.035)
        m.collider((doorx,y-offset,top/2),(1.75,depth,top))
    for side in (-1,1):
        with m.at((side*w/2,0,0),90*side):window(m,0,-.08,1.85,1.3,1.2)
    with m.at((0,d/2,0),180):window(m,-.4,-.08,1.85,1.3,1.2)
    roof(m,w,d,eave,1.5 if variant=='A' else 1.75)
    lantern(m,doorx-.94,y-.17,2.25,.32)
    pot(m,-w/2+.2,y-.35,scale=1.05,plant=True)
    pot(m,w/2-.2,y-.32,scale=.82,plant=True,key='bluepot')
    bench(m,windowx,y-.55,w=1.7)


def tea_house(m,w,d):
    shell(m,w,d,5.85)
    for side in (-1,1):
        m.box((0,side*(d/2+.08),3.10),(w+.2,.22,.25),'wood')
        for xx in (-w/2,w/2):m.box((xx,0,3.1),(.22,d,.25),'wood')
    y=-d/2-.14
    door(m,-2,y,w=1.55,h=2.25)
    for xx in (.55,2.45):window(m,xx,y,1.77,1.60,1.50,True)
    # Solid split fabric panels with a restrained cup graphic on the right panel.
    for xx in (-2.46,-1.51):
        for k in range(4):
            xa=xx-.445+k*.2225;xb=xa+.2225
            pts=[(xa,y-.24,2.65),(xa,y-.27+.05*math.sin(k),.75+.04*math.sin(k)),
                 (xb,y-.27+.05*math.sin(k+1),.75+.04*math.sin(k+1)),(xb,y-.24,2.65)]
            for face in (pts,pts[::-1]):
                m.poly(face,'rust')
                for j,p in enumerate(face):m.colors[-4+j]=(*PALETTE['rust'],(2.65-p[2])/1.9)
    m.beam((-3.01,y-.25,2.73),(-.96,y-.25,2.73),.07,.08,'wood_light')
    m.poly([(-1.81,y-.268,1.83),(-1.21,y-.268,1.83),(-1.28,y-.268,1.58),(-1.71,y-.268,1.58)][::-1],'paper')
    m.box((-1.51,y-.275,1.49),(.66,.008,.045),'paper')
    m.beam((-1.51,y-.28,1.99),(-1.46,y-.28,2.13),.025,.01,'paper')
    # Wraparound lower roof, with deep eaves beneath an open timber balcony.
    outer=[(-w/2-.82,-d/2-1.26),(w/2+.82,-d/2-1.26),(w/2+.82,d/2+.76),(-w/2-.82,d/2+.76)]
    inner=[(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]
    for k in range(4):
        a,b=Vector((*outer[k],3.02)),Vector((*outer[(k+1)%4],3.02))
        c,dv=Vector((*inner[(k+1)%4],3.54)),Vector((*inner[k],3.54))
        m.poly([a,b,c,dv],'roof')
        m.beam(a,b,.14,.17,'roof_edge')
        for t in (.28,.55,.8):m.beam(a.lerp(dv,t),b.lerp(c,t),.045,.045,'roof_edge')
        count=math.ceil((b-a).length/.50)
        for j in range(count):
            m.beam(a.lerp(b,(j+.5)/count),dv.lerp(c,(j+.5)/count),.045,.045,'roof')
    m.box((0,-3.66,3.61),(w+.1,1.08,.18),'wood')
    for yy in (-3.88,-3.45):m.box((0,yy,3.715),(w+.0,.40,.055),'wood_light')
    for xx in np.linspace(-w/2+.1,w/2-.1,9):m.box((float(xx),-4.13,4.15),(.13,.15,.97),'wood_light')
    for zz in (3.96,4.48):m.box((0,-4.13,zz),(w+.16,.18,.13),'wood_light')
    for xx in (-1.40,1.40):window(m,xx,y,4.75,2.1,1.6)
    for side in (-1,1):
        with m.at((side*w/2,0,0),side*90):
            window(m,0,-.1,4.63,1.7,1.55)
            window(m,.55,-.1,1.77,1.35,1.35)
    with m.at((0,d/2,0),180):
        for xx in (-2,2):window(m,xx,-.1,4.63,1.45,1.35)
        window(m,0,-.1,1.9,1.4,1.25)
    roof(m,w,d,5.85,1.95)
    for xx in (-3.70,3.70):
        m.box((xx,-4.04,1.5275),(.18,.18,3.135),'wood')
        lantern(m,xx,-3.9,5.1,.59)
    for yy,top in [(-4.25,.15),(-3.87,.30)]:
        m.box((-2,yy,(top-.06)/2),(1.85,.42,top+.06),'stone_light',.02)
        m.collider((-2,yy,top/2),(1.85,.42,top))
    bench(m,1.55,-4.06,w=2.6)
    pot(m,-3.6,-4.35,key='bluepot',scale=1.25,plant=True)
    pot(m,3.6,-4.32,key='bluepot',scale=1.2,plant=True)


def workshop(m,w,d):
    shell(m,w,d,3.0,True)
    y=-d/2-.13
    # Shaded shopfront display remains exterior scenery; closed wall behind shelves.
    m.box((0,y-.09,1.53),(w-1,.15,2.30),'wood_dark')
    for zz in (.40,1.08,1.84):m.box((0,y-.40,zz),(4.8,.65,.12),'wood_light')
    for xx in (-2.3,0,2.3):m.box((xx,y-.40,.91),(.10,.59,1.90),'wood')
    for row,zz in enumerate((.46,1.14,1.9)):
        for k in range(6):pot(m,-1.98+k*.76,y-.42,zz,scale=.58+R.random()*.35,key='bluepot' if (k+row)%4==0 else 'clay',form=('jar','bowl','bottle','urn')[(k+row)%4])
    awning(m,0,y,2.75,w+1,1.35,'green')
    m.box((0,y-1.35,2.55),(w+1,.035,.23),'green_dark')
    for xx in (-w/2-.2,w/2+.2):
        m.box((xx,y-1.25,1.40),(.15,.16,2.8),'wood')
        m.beam((xx,y-1.25,2.1),(xx+(-.6 if xx>0 else .6),y-1.25,2.62),.1,.1,'wood_light')
    roof(m,w,d,3.0,1.3,'green')
    lantern(m,-2.64,y-1.24,2.10,.50)
    pot(m,w/2+.56,y-.52,0,1.85,'clay')
    pot(m,-w/2-.55,y-.50,0,1.2,'bluepot',True)
    pot(m,1.63,y-1.45,0,1.0,'clay')
    with m.at((w/2,0,0),90):window(m,0,-.1,1.70,1.3,1.15)
    with m.at((0,d/2,0),180):
        door(m,0,-.1,h=2.05)
        for yy,top in [(-.9,.15),(-.5,.30)]:
            m.box((0,yy,(top-.06)/2),(1.65,.45,top+.06),'stone_light',.02)
            m.collider((0,yy,top/2),(1.65,.45,top))


def storehouse(m,w,d):
    shell(m,w,d,3.65)
    y=-d/2-.10
    door(m,0,y,w=1.65,h=2.65)
    for offset,top,depth in [(.55,.15,1.15),(.24,.30,.55)]:
        m.box((0,y-offset,(top-.08)/2),(2.0,depth,top+.08),'stone_light',.035)
        m.collider((0,y-offset,top/2),(2.0,depth,top))
    # Turn the gable towards the front, like the narrow storehouse in the concept.
    with m.at(yaw=90):roof(m,d,w,3.65,1.45)
    for zz in (.80,2.45):
        for xx in (-.76,.76):m.box((xx,y-.18,zz),(.21,.075,.09),'metal')
    with m.at((w/2,0,0),90):window(m,0,-.1,2.65,.65,.65)


def garden(m):
    # Compact roofed well with no raised platform or perimeter fence.
    with m.at((0,-1.65,0),90):
        for row in range(3):
            for k in range(12):
                a=(k+.5*(row%2))*math.tau/12
                with m.at((math.cos(a)*(.79+R.uniform(-.018,.018)),math.sin(a)*.79,.16+row*.27+R.uniform(-.012,.012)),math.degrees(a)+R.uniform(-3,3)):
                    m.box((0,0,0),(.34+R.uniform(-.015,.015),.41+R.uniform(-.012,.012),.29),color_variant('well_stone',.13),.06)
        for k in range(12):
            a=k*math.tau/12
            with m.at((math.cos(a)*.80,math.sin(a)*.80,.86),math.degrees(a)):
                m.box((0,0,0),(.40,.43,.17),color_variant('well_cap',.10),.045)
        m.poly([(math.cos(i*math.tau/16)*.65,math.sin(i*math.tau/16)*.65,.3) for i in range(16)],'water')
        m.collider((0,0,.43),(1.85,1.85,.88))
        for xx in (-1.02,1.02):
            m.box((xx,0,1.27),(.16,.18,2.6),'wood_light',.02)
            m.collider((xx,0,1.3),(.17,.20,2.6))
            m.beam((xx,0,2.02),(xx*.50,0,2.53),.095,.11,'wood')
        m.beam((-1.13,0,1.70),(1.17,0,1.70),.14,.14,'wood_dark')
        m.beam((1.18,0,1.7),(1.18,0,1.4),.075,.09,'wood_light')
        m.beam((1.18,0,1.4),(1.4,0,1.4),.08,.08,'wood')
        m.beam((0,0,1.72),(0,0,.92),.025,.025,'soil')
        # Broad overlapping wooden shingles, with a closed pitched underside.
        for side in (-1,1):
            pts=[(-1.34,0,2.82),(1.34,0,2.82),(1.34,side*.97,2.28),(-1.34,side*.97,2.28)]
            if side<0:pts.reverse()
            m.poly(pts,'wood_dark');m.poly([(x,y,z-.075) for x,y,z in pts[::-1]],'wood')
            for row in range(4):
                for col in range(7):
                    x=-1.34+(col+.5)*2.68/7
                    a=row/4;b=(row+1)/4
                    pts=[(x-.187,side*a*.97,2.85-a*.54),(x+.187,side*a*.97,2.85-a*.54),
                         (x+.18,side*b*1.01,2.85-b*.54+.015),(x-.18,side*b*1.01,2.85-b*.54+.015)]
                    m.poly(pts if side>0 else pts[::-1],color_variant('wood_light',.16))
            m.beam((-1.37,side*.99,2.3),(1.37,side*.99,2.3),.10,.12,'wood')
        m.beam((-1.4,0,2.86),(1.4,0,2.86),.16,.13,'wood_light')
        # Open staved bucket with two dark hoops and a curved wooden handle.
        with m.at((.22,-.55,.95)):
            m.lathe((0,0,0),[(0,.18),(.33,.23),(.35,.23),(.35,.19),(.06,.15)],'wood_light',12)
            for zz in (.07,.28):m.lathe((0,0,0),[(zz,.20+zz*.14),(zz+.035,.205+zz*.14)],'wood_dark',12)
            for k in range(8):
                a=k*math.pi/8;b=(k+1)*math.pi/8
                m.beam((math.cos(a)*.22,0,.33+math.sin(a)*.22),(math.cos(b)*.22,0,.33+math.sin(b)*.22),.025,.025,'wood')
    # Face the well from its side; leave the maple trunk and its roots clear.
    z=float(upper_surface(HEIGHTS,102,86.5))-float(plane(99,85))-.015
    with m.at((3,1.5,z),0):bench(m,0,0,w=2.2)
    for x,y,r in [(-1.4,-3.0,.35),(-2.0,-2.1,.32),(-1.65,-.6,.30),(-.95,.5,.36),(.0,.9,.28)]:
        with m.at((x,y,-.03),R.uniform(0,180)):
            m.box((0,0,0),(r*1.8,r*1.4,.10),color_variant('stone_light',.1),.07)


def sign(m):
    m.box((0,0,1.03),(.16,.17,2.16),'wood')
    # The board itself points along local +X; both faces carry the same world
    # direction, so reading the back cannot send the player towards the road.
    profile=[(-.60,1.61),(.42,1.61),(.75,1.85),(.42,2.09),(-.60,2.09)]
    front=[(x,-.065,z) for x,z in profile];back=[(x,.065,z) for x,z in profile]
    m.poly(front,'wood_light');m.poly(back[::-1],'wood_light')
    for k in range(5):m.poly([front[k],back[k],back[(k+1)%5],front[(k+1)%5]],'wood')
    for side in (-1,1):
        y=side*.085
        m.beam((-.46,y,1.86),(-.20,y,2.02),.055,.025,'paper')
        m.beam((-.20,y,2.02),(.06,y,1.86),.055,.025,'paper')
        m.box((-.20,y,1.78),(.30,.025,.15),'paper')
        m.box((.24,y,1.83),(.25,.026,.065),'paper')
        pts=[(.33,y,1.94),(.59,y,1.83),(.33,y,1.72)]
        m.poly(pts if side>0 else pts[::-1],'paper')
    m.collider((0,0,1),(.17,.17,2))


def ground(world,h):
    m=Mesh('Village_Ground');paths=[np.array(p) for p in world['village']['paths']]
    # One continuous ground patch: unions avoid z-fighting at forks and aprons.
    step=.5;axisx=np.arange(64,179+step,step);axisy=np.arange(-32,108+FOREST_OFFSET_Y+step,step)
    x,y=np.meshgrid(axisx,axisy)
    distance=np.full(x.shape,np.inf);z=np.zeros(x.shape)
    for path in paths:
        d,zz=nearest(x,y,path);closer=d<distance
        z=np.where(closer,zz,z);distance=np.minimum(distance,d)
    # Follow the actual exported triangulated terrain surface, never a floating decal.
    terrain=upper_surface(h,x,y)
    z=terrain+.035
    # Narrow woodland trail, gently widening only inside the hamlet.
    half_width=1.3+.6*smooth((y-(FOREST_OFFSET_Y-12))/12)
    signed=distance-half_width+.16*np.sin(x*.73)*np.cos(y*.57)+.045*np.sin(x*2.7+y*1.7)
    apron_signed=np.full(x.shape,np.inf)
    for b in world['village']['buildings']:
        bx,by,bz=b['position'];a=math.radians(b['yaw'])
        lx=(x-bx)*math.cos(a)+(y-by)*math.sin(a)
        ly=-(x-bx)*math.sin(a)+(y-by)*math.cos(a)
        front=np.maximum.reduce([np.abs(lx)-(b['width']/2+1),ly+b['depth']/2-.2,-ly-b['depth']/2-4.2])
        apron_signed=np.minimum(apron_signed,front)
        # Narrow doorstep paths connect the five aprons to the lane network.
        door=np.array([bx+math.sin(a)*(b['depth']/2+2),by-math.cos(a)*(b['depth']/2+2),bz])
        allpoints=np.concatenate(paths)
        target=allpoints[np.argmin(np.linalg.norm(allpoints[:,:2]-door[:2],axis=1))]
        connection,_=nearest(x,y,np.array([door,target]))
        apron_signed=np.minimum(apron_signed,connection-1.05)
    # Small fountain forecourt and one pedestrian connection, with a planted
    # island around it. A full oval of paving made the village read as a track.
    court=np.hypot((x-99),1.1*(y-FOREST_OFFSET_Y-13.0))-3.8
    approach,_=nearest(x,y,np.array([village_point(88.,11.,20.4),village_point(99.,13.,20.5)]))
    apron_signed=np.minimum(apron_signed,np.minimum(court,approach-1.1))
    signed=np.minimum(signed,apron_signed)
    verge_colour=smooth((signed+.40)/.40)
    # Never paint across the asphalt: clip the dirt precisely at its shoulder.
    road_distance,_=nearest(x,y,np.array(world['road']))
    signed=np.maximum(signed,world['road_width']/2+.025-road_distance)
    for j in range(len(axisy)-1):
        for i in range(len(axisx)-1):
            corners=[(i,j),(i+1,j),(i+1,j+1),(i,j+1)]
            if min(signed[jj,ii] for ii,jj in corners)>0:continue
            base=np.array(PALETTE['lane'])
            variation=.017*math.sin(x[j,i]*.31)*math.sin(y[j,i]*.37)
            # Clip each triangle at the signed verge. Smooth edges, no grid stairs.
            triangles=[(0,1,2),(0,2,3)] if z[j,i]+z[j+1,i+1]>=z[j,i+1]+z[j+1,i] else [(0,1,3),(1,2,3)]
            for triangle in triangles:
                verts=[(np.array([x[jj,ii],y[jj,ii],z[jj,ii]]),signed[jj,ii]) for ii,jj in [corners[k] for k in triangle]]
                clipped=[]
                for k,(b,db) in enumerate(verts):
                    a,da=verts[k-1]
                    if (da<=0)!=(db<=0):clipped.append(a+(b-a)*(da/(da-db)))
                    if db<=0:clipped.append(b)
                if len(clipped)>=3:
                    m.poly(clipped,tuple(base+variation))
                    for k,p in enumerate(clipped):
                        base=np.array(PALETTE['lane'])
                        variation=.024*math.sin(p[0]*.31)*math.sin(p[1]*.37)+.007*math.sin(p[0]*1.1+p[1]*.82)
                        u=(p[0]-axisx[i])/step;v=(p[1]-axisy[j])/step
                        edge=(verge_colour[j,i]*(1-u)*(1-v)+verge_colour[j,i+1]*u*(1-v)+verge_colour[j+1,i]*(1-u)*v+verge_colour[j+1,i+1]*u*v)
                        base=base*(1-edge)+np.array([.20,.205,.065])*edge
                        m.colors[-len(clipped)+k]=(*tuple(base+variation),0)
    return m



def edges(world,h):
    m=Mesh('Village_Edges')
    runs=[[(70,-3),(70,18),(74,22)],[(76,36),(84,40),(93,40)],[(110,43),(119,35)],[(130,15),(130,4),(125,-10)]]
    paths=[np.array(p) for p in world['village']['paths']]
    runs=[[village_point(*p) for p in run] for run in runs]
    for run in runs:
        for a,b in zip(run[:-1],run[1:]):
            a=np.array(a,dtype=float);b=np.array(b,dtype=float);length=np.linalg.norm(b-a)
            count=math.ceil(length/.95);direction=(b-a)/length
            yaw=math.degrees(math.atan2(direction[1],direction[0]))
            for i in range(count):
                p=a+(b-a)*(i+.5)/count
                if min(float(nearest(*p,path)[0]) for path in paths)<3.8:continue
                z=float(sample(h,*p))
                with m.at((*p,z),yaw):
                    m.box((0,0,.12),(length/count-.025,.48,.60),color_variant('stone'),.05)
                    m.collider((0,0,.16),(length/count,.48,.55))
                    if i%3==0:
                        m.box((0,0,.78),(.14,.14,.96),'wood_light')
                    for zz in (.73,1.06):m.box((0,0,zz),(length/count,.095,.085),'wood_light')
    return m


def export(m,mat):
    obj=m.object(mat);objs=[obj]
    for i,(c,s,rotation) in enumerate(m.colliders):
        bpy.ops.mesh.primitive_cube_add(size=1,location=c,rotation=rotation)
        ob=bpy.context.object;ob.name=f'UCX_{m.name}_{i:02d}';ob.scale=s
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        objs.append(ob)
    bpy.ops.object.select_all(action='DESELECT')
    for ob in objs:ob.select_set(True)
    bpy.context.view_layer.objects.active=obj
    path=OUT/'assets'/f'{m.name}.fbx'
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',object_types={'MESH'},mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False)
    tri=sum(len(f)-2 for f in m.faces)
    bounds=np.array(m.vertices)
    info={'triangles':tri,'vertices':len(m.vertices),'materials':1,'collision_boxes':len(m.colliders),'min':bounds.min(axis=0).round(4).tolist(),'max':bounds.max(axis=0).round(4).tolist()}
    for ob in objs[1:]:bpy.data.objects.remove(ob,do_unlink=True)
    return obj,info


def main():
    global WORLD, HEIGHTS
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat=bpy.data.materials.new('VillagePalette');mat.use_nodes=True
    nodes=mat.node_tree.nodes;vc=nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
    bsdf=nodes.get('Principled BSDF');mat.node_tree.links.new(vc.outputs['Color'],bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value=.92;bsdf.inputs['Specular IOR Level'].default_value=.10
    world=json.loads((yori.OUT/'world.json').read_text());h=np.load(yori.OUT/'heightmap.npy')
    WORLD,HEIGHTS=world,h
    manifest={};objects={}
    for name,_,_,w,d in BUILDINGS:
        m=Mesh(name)
        if name.endswith('TeaHouse'):tea_house(m,w,d)
        elif name.endswith('CottageA'):cottage(m,w,d,'A')
        elif name.endswith('CottageB'):cottage(m,w,d,'B')
        elif name.endswith('Workshop'):workshop(m,w,d)
        else:storehouse(m,w,d)
        objects[name],manifest[name]=export(m,mat)
    for name,fn in [('Village_Garden',garden),('Village_Sign',sign)]:
        m=Mesh(name);fn(m);objects[name],manifest[name]=export(m,mat)
    m=ground(world,h);objects[m.name],manifest[m.name]=export(m,mat)
    m=edges(world,h);objects[m.name],manifest[m.name]=export(m,mat)
    from village.decorations import furnish,planting,threshold
    for fn in (furnish,planting,threshold):
        m=fn(sys.modules[__name__]);objects[m.name],manifest[m.name]=export(m,mat)
    # A usable modelling scene: actual layout, separated editable mesh assets.
    for name,obj in objects.items():
        p=world['instances'][name][0]
        obj.location=p[:3];obj.rotation_euler.z=math.radians(p[3])
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Village.blend'))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    sources=[HERE/'build.py',HERE/'layout.py',HERE/'decorations.py',HERE/'references/concept.png',HERE/'references/buildings.png',HERE/'references/polish.png',HERE/'references/forest-approach.png',HERE/'references/well-nook.png']
    sources=[p for p in sources if p.exists()]  # the concept images stay in the prototype archive
    identity={'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},
        'world_sha256':sha(yori.OUT/'world.json'),'heightmap_sha256':sha(yori.OUT/'heightmap.npy'),
        'exports':{p.name:sha(p) for p in sorted((OUT/'assets').glob('*.fbx'))}}
    (OUT/'build-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    print('VILLAGE BUILD COMPLETE',sum(v['triangles'] for v in manifest.values()),'triangles',flush=True)

if __name__=='__main__':main()
