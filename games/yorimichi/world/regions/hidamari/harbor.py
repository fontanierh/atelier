"""Reference-led fishing harbor kit. Metres, Z up; existing quay/boat positions.

Alpha tags select local surface treatments in M_Harbor: 0 paint, .25 cedar,
.5 limestone, .75 stonework, 1 glass. No changes to the shared village palette.
"""
import math
import random
from mathutils import Vector, Matrix
from village import build as v

COLORS = {
    'h_white': (.55,.53,.43), 'h_blue': (.010,.10,.22),
    'h_trim': (.025,.17,.30), 'h_dark': (.035,.065,.068),
    'h_glass': (.003,.018,.035), 'h_wood': (.12,.052,.015),
    'h_deck': (.22,.12,.035), 'h_rope': (.20,.105,.025),
    'h_orange': (.60,.095,.010), 'h_stone': (.36,.32,.245),
    'h_paving': (.40,.35,.27), 'h_leaf': (.38,.16,.012),
    'h_crate': (.008,.035,.12), 'h_metal': (.12,.14,.14),
}


class Mesh(v.Mesh):
    def __init__(self,name):
        super().__init__(name)
        self.smooth_normals={}

    def poly(self, points, color):
        start=len(self.colors)
        key=color if isinstance(color,str) else ''
        super().poly(points,COLORS.get(key,color))
        tag=1 if key=='h_glass' else .5 if key=='h_paving' else .75 if key in ('h_stone','stone','stone_light') else .25 if key in ('h_wood','h_deck','wood','wood_dark','wood_light') else 0
        for i in range(start,len(self.colors)):
            self.colors[i]=(*self.colors[i][:3],tag)

    def object(self,material):
        ob=super().object(material)
        if self.smooth_normals:
            for face in ob.data.polygons:
                face.use_smooth=all(i in self.smooth_normals for i in face.vertices)
            ob.data.normals_split_custom_set_from_vertices([self.smooth_normals.get(i,(0,0,0)) for i in range(len(self.vertices))])
        return ob


def tube(m,points,radius,color,sides=6,reference=(0,0,1)):
    """Continuous low-poly rope/rail, without a box cap at every bend."""
    points=[Vector(p) for p in points]
    rings=[]
    closed=(points[0]-points[-1]).length<.00001
    for i,p in enumerate(points):
        t=(points[1]-points[-2]).normalized() if closed and i in (0,len(points)-1) else (points[min(i+1,len(points)-1)]-points[max(0,i-1)]).normalized()
        u=t.cross(Vector(reference))
        if u.length<.01:u=t.cross(Vector((0,1,0)))
        u.normalize();w=t.cross(u).normalized()
        rings.append([p+radius*(u*math.cos(a*math.tau/sides)+w*math.sin(a*math.tau/sides)) for a in range(sides)])
    for j,(a,b) in enumerate(zip(rings,rings[1:])):
        for i in range(sides):
            ps=[a[i],a[(i+1)%sides],b[(i+1)%sides],b[i]]
            centers=[points[j],points[j],points[j+1],points[j+1]]
            start=len(m.vertices);m.poly(ps,color)
            for k,(p,c) in enumerate(zip(ps,centers)):
                m.smooth_normals[start+k]=tuple((m.transform.to_3x3()@(p-c)).normalized())


def ring(m,center,radius,thickness,color,axis='Z',segments=24):
    x,y,z=center
    points=[]
    for i in range(segments+1):
        a=i*math.tau/segments
        q=(radius*math.cos(a),radius*math.sin(a),0)
        if axis=='X':q=(0,q[0],q[1])
        if axis=='Y':q=(q[0],0,q[1])
        points.append((x+q[0],y+q[1],z+q[2]))
    tube(m,points,thickness,color,10,{'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1)}[axis])


def rope_coil(m,x,y,z,radius=.65):
    for layer in range(3):
        points=[]
        for i in range(145):
            a=i*math.tau/48;r=radius-.22+i/144*.22
            points.append((x+r*math.cos(a),y+r*math.sin(a),z+.06+layer*.085))
        tube(m,points,.043,'h_rope',6)
    tube(m,[(x+radius,y,z+.1),(x+radius+.35,y+.16,z+.06),(x+radius+.8,y+.10,z+.05)],.043,'h_rope')


def crate(m,x,y,z,plastic=False,scale=1):
    with m.at((x,y,z)):
        w,d,h=1.15*scale,.84*scale,.72*scale
        color='h_crate' if plastic else 'h_deck'
        m.box((0,0,.07*scale),(w,d,.14*scale),color,.025)
        for side in [-1,1]:
            for i in range(3):
                zz=(.2+i*.21)*scale
                m.box((0,side*d/2,zz),(w,.055*scale,.16*scale),color,.018)
                m.box((side*w/2,0,zz),(.055*scale,d,.16*scale),color,.018)
            for xx in [-w/2,w/2]:m.box((xx,side*d/2,h/2),(.085*scale,.085*scale,h),color,.015)
            m.box((0,side*d/2,h),(w+.08*scale,.09*scale,.085*scale),color,.015)
            if plastic:
                for xx in [-.33,0,.33]:m.box((xx*scale,side*(d/2+.04),h/2),(.05*scale,.035*scale,h*.8),color)
        m.box((0,0,h*.72),(w*.85,d*.85,.06*scale),'h_dark')
        if plastic:
            for xx in [-.3,0,.3]:
                m.box((xx*scale,0,h*.78),(.20*scale,.51*scale,.12*scale),(.44,.49,.46),.05)


def boat():
    m=Mesh('HD_Boat')
    outline=[(0,-6.5),(1.0,-5.85),(1.65,-4.5),(1.9,-2),(1.9,3.5),(1.25,5),(-1.25,5),(-1.9,3.5),(-1.9,-2),(-1.65,-4.5),(-1,-5.85)]
    # Rounded chine, painted waterline band and an open inset working deck.
    rings=[[(x*s,y*(.94 if z<0 else 1),z) for x,y in outline] for s,z in [(.60,-.55),(.82,-.20),(1,.38),(1.015,.62),(1.015,1.15)]]
    for k,(a,b) in enumerate(zip(rings,rings[1:])):
        for i in range(len(a)):
            j=(i+1)%len(a);m.poly([a[i],a[j],b[j],b[i]],['h_blue','h_white','h_blue','h_white'][k])
    m.poly(list(reversed(rings[0])),'h_blue')
    deck=[(x*.92,y*.94,.78) for x,y in outline];m.poly(deck,'h_deck')
    for i,(x,y) in enumerate(outline):
        nx,ny=outline[(i+1)%len(outline)]
        m.poly([(x*.92,y*.94,.78),(nx*.92,ny*.94,.78),(nx*1.015,ny,1.15),(x*1.015,y,1.15)],'h_white')
    tube(m,[(x*1.02,y,1.19) for x,y in outline+[outline[0]]],.065,'h_trim',8)
    # Cabin faces carry marine glazing, not the houses' timber lattice window.
    m.box((0,1.45,1.95),(2.62,3.1,2.32),'h_white',.09)
    m.box((0,1.45,3.16),(2.97,3.45,.20),'h_trim',.05)
    for xx in [-.66,.66]:
        m.box((xx,-.125,2.35),(1.02,.065,1.18),'h_dark',.025)
        m.box((xx,-.17,2.35),(.84,.02,1.0),'h_glass')
        m.beam((xx-.3,-.20,1.98),(xx+.17,-.20,2.37),.022,.025,'h_metal')
    for side in [-1,1]:
        for yy in [.58,1.86]:
            m.box((side*1.328,yy,2.35),(.05,.88,1.16),'h_dark',.025)
            m.box((side*1.36,yy,2.35),(.015,.72,.99),'h_glass')
        m.box((side*1.344,2.65,1.73),(.055,.47,1.57),'h_white',.025)
        m.box((side*1.38,2.82,1.70),(.04,.12,.04),'h_metal')
    # Mast, rigging, chimney, navigation lamps and deck rails.
    m.lathe((0,1.55,3.24),[(0,.11),(2.9,.065),(3.02,0)],'h_wood',12)
    m.beam((-1.65,1.55,5.32),(1.65,1.55,5.32),.07,.07,'h_wood')
    for side in [-1,1]:
        tube(m,[(side*1.65,1.55,5.32),(side*1.22,1.55,3.28)],.012,'h_rope',4)
        m.lathe((side*1.05,.6,3.3),[(0,.13),(.2,.13),(.25,.09)],'h_orange' if side<0 else 'h_trim',10)
        for yy in [-4.0,-2.0,3.5]:m.beam((side*1.72,yy,1.2),(side*1.72,yy,1.85),.035,.035,'h_metal')
        tube(m,[(side*1.65,-4,1.85),(side*1.78,-2,1.85),(side*1.78,-.5,1.85)],.025,'h_metal')
    m.lathe((.93,3.42,.8),[(0,.13),(3.4,.13),(3.5,.18),(3.62,.18)],'h_metal',10)
    for side in [-1,1]:
        for yy in [-3.7,-1.8,1.1,3.5]:
            ring(m,(side*1.96,yy,.72),.30,.115,'h_orange','X')
            tube(m,[(side*1.83,yy,1.22),(side*2,yy,.98)],.025,'h_rope')
    crate(m,-.6,-2.7,.81);crate(m,.62,-2.55,.81,True,.85)
    rope_coil(m,0,-4.45,.8,.40)
    m.box((0,4,.99),(1.7,1.0,.22),'h_deck',.04)
    return m


def dress_harbor(m,height):
    """Dress the existing collision shell; keep pier mouths and quay walk clear."""
    r=random.Random(681)
    # Ground-following paving replaces the bare grass strip at the seafront.
    for x in range(420,900,4):
        for y in range(-124,-98,2):
            if 839<x<857:continue  # canal mouth stays open
            m.poly([(xx,yy,float(height(xx,yy))+.04) for xx,yy in [(x,y),(x+4,y),(x+4,y+2),(x,y+2)]],'h_paving')
    # Fill the former open soil seam with a solid sloped stone strip, landing
    # on the existing coping instead of hovering over its edge.
    for x in range(420,900,2):
        if x<856 and x+2>840:continue  # Preserve the open canal mouth.
        pts=[(x,-124,float(height(x,-124))+.04),(x+2,-124,float(height(x+2,-124))+.04),(x+2,-124.4,2.475),(x,-124.4,2.475)]
        m.poly(pts[::-1],'h_paving')
    # Proper timber planks and piles make the piers appear supported.
    for x in range(480,840,60):
        for i in range(110):
            yy=-169.8+i*.4
            m.box((x,yy,2.525),(2.98,.385,.04),'h_deck')
        for yy in range(-168,-125,6):
            for side in [-1,1]:
                m.lathe((x+side*1.12,yy,-1.25),[(0,.18),(3.68,.18)],'h_wood',10)
            m.beam((x-1.4,yy,1.88),(x+1.4,yy,1.88),.28,.25,'h_wood')
    # Masonry courses along the sea-facing breakwater; tide line below the cap.
    for x in range(422,760,2):
        for row in range(3):
            m.box((x+(row%2),-223.31,.25+row*.64),(1.96,.07,.61),'h_stone',.035)
        m.box((x,-225,2.51),(1.97,3.32,.12),'h_paving',.025)
    # Low irregular wave-break rocks beyond the wall, preserving open horizon.
    for i in range(32):
        x=425+i*10.4;y=-229-r.uniform(0,2)
        with m.at((x,y,0),r.uniform(0,180)):
            m.box((0,0,1.8),(r.uniform(1.4,2.6),r.uniform(1.5,2.5),r.uniform(1.8,3.3)),'h_stone',.5)
    # Mooring lines terminate outside the pier walking surface.
    for i in range(12):
        bx=460+i*32;by=-150-(i%2)*19
        px=min(range(480,840,60),key=lambda x:abs(x-bx));side=1 if px>bx else -1
        for yy in [-2,2]:
            tube(m,[(bx+side*2.15,by+yy,1.55),((bx+px)/2,by+yy,.95),(px-side*1.35,by+yy,2.70)],.025,'h_rope')
    # Reusable work clusters beside the rail, leaving an inland movement lane.
    for x in [466,526,628.5,706,778,886]:
        y=-120.5 if x==628.5 else -124.0;z=float(height(x,y))+.05
        with m.at((x,y,z),-12):
            if x==628.5:m.transform=m.transform@Matrix.Diagonal((.8,.8,.8,1.0))
            crate(m,0,0,0,True,1.15);crate(m,-1.05,.25,0,False,.90)
            crate(m,-.05,.05,.85,True,.63);crate(m,1.13,-.1,0,False,.92)
            rope_coil(m,-.63,1.25,.02,.58)
            ring(m,(-1.48,.70,.63),.48,.065,'h_rope','Y')
            ring(m,(-1.48,.73,.63),.38,.065,'h_rope','Y')
    # Flat, individually shaped fallen leaves: no raised ground collision.
    for i in range(1000):
        x=r.uniform(610,650) if i>=720 else r.uniform(422,899)
        y=r.uniform(-124,-112) if i>=720 else r.uniform(-124,-103)
        if 839<x<857:continue
        z=float(height(x,y))+.055
        with m.at((x,y,z),r.uniform(0,360)):
            s=r.uniform(.07,.16)
            outline=[(-.3,-1),(-.55,-.38),(-1,-.32),(-.65,.15),(-.85,.72),(-.25,.56),(0,1.12),(.27,.53),(.83,.71),(.62,.14),(1,-.3),(.45,-.35),(.3,-1)]
            for a,b in zip(outline,outline[1:]+outline[:1]):m.poly([(0,0,.015),(b[0]*s,b[1]*s,0),(a[0]*s,a[1]*s,0)],'h_leaf')
    return m
