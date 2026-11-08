"""Shared vertex-colour mesh construction; no village building generation on import.

Regional producers depend on this narrow kernel instead of loading the village's
building, ground and decoration constructors as incidental source dependencies.
"""
import sys as _sys
from pathlib import Path
_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori
import math
import random
from contextlib import contextmanager
import bpy
import numpy as np
from mathutils import Matrix, Vector
from village.layout import BUILDINGS, sample, smooth

OUT = yori.OUT / 'village'
HEIGHTS = None
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
    from atelier.blender.fbx import export_fbx as export_scene_fbx
    export_scene_fbx(filepath=str(path),use_selection=True,apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',object_types={'MESH'},mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False)
    tri=sum(len(f)-2 for f in m.faces)
    bounds=np.array(m.vertices)
    info={'triangles':tri,'vertices':len(m.vertices),'materials':1,'collision_boxes':len(m.colliders),'min':bounds.min(axis=0).round(4).tolist(),'max':bounds.max(axis=0).round(4).tolist()}
    for ob in objs[1:]:bpy.data.objects.remove(ob,do_unlink=True)
    return obj,info
