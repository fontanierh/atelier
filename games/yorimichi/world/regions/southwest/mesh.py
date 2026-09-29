"""Shared faceted-mesh builder for the south-west detour props (metres, Z up, vertex colours, one palette material).
Same conventions as the village and skateboard builders: linear colours, flat facets, no textures."""
import math, random
from contextlib import contextmanager
import bpy
from mathutils import Matrix, Vector

PALETTE={
 'plaster':(.46,.31,.15),'plaster_light':(.59,.43,.23),
 'wood':(.075,.040,.018),'wood_light':(.17,.10,.045),'wood_dark':(.034,.020,.011),'wood_grey':(.13,.11,.085),'wood_pale':(.22,.15,.08),'driftwood':(.19,.16,.12),
 'roof':(.024,.036,.052),'roof_edge':(.013,.021,.031),
 'straw':(.36,.23,.075),'straw_light':(.48,.33,.12),'straw_dark':(.20,.12,.04),'chalk':(.05,.055,.05),
 'green':(.105,.16,.027),'green_dark':(.065,.095,.021),'coconut':(.12,.26,.05),'coconut_light':(.24,.40,.08),
 'stone':(.11,.105,.08),'stone_light':(.17,.155,.11),'stone_dark':(.06,.06,.05),
 'paper':(.92,.58,.22),'cream':(.78,.66,.42),'white':(.85,.82,.72),
 'rust':(.62,.12,.035),'rust_dark':(.36,.07,.02),'clay':(.46,.235,.085),'sand':(.60,.50,.30),
 'metal':(.085,.085,.075),'leaf':(.019,.060,.010),'water':(.06,.14,.095),'rope':(.40,.28,.12),
 'roof_grey':(.030,.034,.040),'roof_grey_light':(.045,.050,.056),'stone_blue':(.070,.080,.092),'stone_blue_light':(.115,.13,.145),'glass':(.16,.34,.32),
 'window':(.36,.20,.09),'bluepot':(.18,.27,.30),'soil':(.09,.073,.031),'lane':(.26,.14,.046),'well_stone':(.30,.235,.15),'well_cap':(.38,.31,.22),
 'plaster_cream':(.40,.33,.20),'vermilion':(.40,.070,.028),'roof_indigo':(.017,.020,.042),'roof_cap':(.055,.062,.095),'eave_board':(.30,.25,.17),
 'bronze':(.055,.085,.055),'mustard':(.40,.27,.06),'faded_blue':(.10,.16,.24),'pennant_orange':(.50,.17,.05),'maple':(.30,.055,.025),'shrub_yellow':(.20,.22,.045),'grass_ochre':(.15,.16,.04),'granite':(.09,.088,.082),'granite_light':(.14,.135,.125),
 'metal_dark':(.040,.040,.038),'skin':(.65,.42,.26),'hair':(.03,.02,.02),'blue':(.06,.12,.30),'red':(.55,.08,.03),
 'plank_cream':(.30,.235,.15),'plank_cream_light':(.37,.30,.20),'plank_tan':(.22,.16,.09),'cloth_blue':(.22,.34,.42),'cloth_pink':(.62,.30,.24),'fish_blue':(.13,.17,.21),'granite':(.13,.13,.12),'granite_light':(.20,.20,.18),'straw_bundle':(.42,.30,.10),
}

class Mesh:
    def __init__(self,name):
        self.name=name;self.vertices=[];self.faces=[];self.colors=[];self.transform=Matrix.Identity(4);self.colliders=[]
    @contextmanager
    def at(self,position=(0,0,0),yaw=0,pitch=0,roll=0):
        old=self.transform.copy()
        self.transform=old@Matrix.Translation(Vector(position))@Matrix.Rotation(math.radians(yaw),4,'Z')@Matrix.Rotation(math.radians(pitch),4,'Y')@Matrix.Rotation(math.radians(roll),4,'X')
        try:yield
        finally:self.transform=old
    def poly(self,points,color):
        points=[Vector(p) for p in points];clean=[]
        for p in points:
            if not any((p-q).length_squared<1e-16 for q in clean):clean.append(p)
        if len(clean)<3:return
        if sum((clean[k]-clean[0]).cross(clean[k+1]-clean[0]).length for k in range(1,len(clean)-1))<1e-10:return
        if isinstance(color,str):color=PALETTE[color]
        i=len(self.vertices)
        self.vertices.extend(tuple(self.transform@p) for p in clean)
        self.faces.append(tuple(range(i,i+len(clean))));self.colors.extend([(*color[:3],1)]*len(clean))
    def box(self,c,s,color,bevel=0):
        x,y,z=c;w,d,h=s
        if bevel:
            b=min(bevel,w/3,d/3,h/3)
            outline=[(-w/2+b,-d/2),(w/2-b,-d/2),(w/2,-d/2+b),(w/2,d/2-b),(w/2-b,d/2),(-w/2+b,d/2),(-w/2,d/2-b),(-w/2,-d/2+b)]
            rings=[[(x+px*sc,y+py*sc,z+zz) for px,py in outline] for zz,sc in [(-h/2,.94),(-h/2+b,1),(h/2-b,1),(h/2,.94)]]
            self.poly(list(reversed(rings[0])),color);self.poly(rings[-1],color)
            for a,bb in zip(rings[:-1],rings[1:]):
                for k in range(8):self.poly([a[k],a[(k+1)%8],bb[(k+1)%8],bb[k]],color)
            return
        p=[(x+dx*w/2,y+dy*d/2,z+dz*h/2) for dx,dy,dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]:self.poly([p[i] for i in f],color)
    def beam(self,a,b,width,depth,color):
        a,b=Vector(a),Vector(b);v=b-a;old=self.transform.copy()
        self.transform=old@Matrix.Translation((a+b)/2)@v.to_track_quat('Z','Y').to_matrix().to_4x4()
        self.box((0,0,0),(width,depth,v.length),color);self.transform=old
    def lathe(self,center,profile,color,n=12,cap=True):
        x,y,z=center
        rings=[[(x+r*math.cos(i*2*math.pi/n),y+r*math.sin(i*2*math.pi/n),z+zz) for i in range(n)] for zz,r in profile]
        for a,b in zip(rings[:-1],rings[1:]):
            for k in range(n):self.poly([a[k],a[(k+1)%n],b[(k+1)%n],b[k]],color)
        if cap:
            if profile[0][1]>1e-4:self.poly(list(reversed(rings[0])),color)
            if profile[-1][1]>1e-4:self.poly(rings[-1],color)
    def sphere(self,center,r,color,n=8,squash=1.0,rings=None):
        rings=rings or n
        prof=[(-r*squash*math.cos(i*math.pi/rings),r*math.sin(i*math.pi/rings)) for i in range(rings+1)]
        prof[0]=(-r*squash,0);prof[-1]=(r*squash,0)
        self.lathe(center,prof,color,n,cap=False)
    def collider(self,c,s):
        self.colliders.append((tuple(self.transform@Vector(c)),s))
    def plank(self,a,b,width,thickness,color):
        self.beam(a,b,width,thickness,color)
    def object(self,material,collision=True):
        data=bpy.data.meshes.new(self.name);data.from_pydata(self.vertices,[],self.faces);data.update()
        data.materials.append(material)
        uv=data.uv_layers.new(name='UVMap')
        for face in data.polygons:
            drop=max(range(3),key=lambda i:abs(face.normal[i]));axes=[i for i in range(3) if i!=drop]
            for li in face.loop_indices:
                co=data.vertices[data.loops[li].vertex_index].co;uv.data[li].uv=(co[axes[0]],co[axes[1]])
        col=data.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
        for i,c in enumerate(self.colors):col.data[i].color=c
        obj=bpy.data.objects.new(self.name,data);bpy.context.collection.objects.link(obj)
        return obj

def material():
    m=bpy.data.materials.get('Southwest_Palette')
    if m:return m
    m=bpy.data.materials.new('Southwest_Palette');m.use_nodes=True
    n=m.node_tree.nodes;b=n.get('Principled BSDF');vc=n.new('ShaderNodeVertexColor');vc.layer_name='Color'
    m.node_tree.links.new(vc.outputs['Color'],b.inputs['Base Color']);b.inputs['Roughness'].default_value=.9;b.inputs['Specular IOR Level'].default_value=.1
    return m
