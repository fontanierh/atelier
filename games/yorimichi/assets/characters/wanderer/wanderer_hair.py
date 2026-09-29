"""Broad hair planes measured from the generated front/profile portrait crops."""
import math
import bpy
from mathutils import Vector
import mesh_tools as G
from hair import patch,crown_solid

# Front crop is 295x355: chin (141,253), eye row 187. Hair top excludes the tied tuft.
SCALE=.00172
def front(u,v,bias=0):
    x=(u-141)*SCALE;z=1.044+(253-v)*SCALE
    rx=.161 if z<1.32 else .152
    depth=.153 if z<1.31 else .135
    y=-depth*math.sqrt(max(.12,1-(x/rx)**2))+.008+bias
    return x,y,z

def plane(name,trace,centre,col='hair',bias=0):
    pts=[front(u,v,bias) for u,v in trace]
    pts.append(front(*centre,bias-.007));n=len(trace)
    # Broad quad regions avoid a shiny, inflated strand or noisy triangle fan.
    faces=[]
    for i in range(0,n,2):
        face=[i,(i+1)%n]
        if i+2<=n:face.append((i+2)%n)
        faces.append(tuple(face+[n]))
    return patch(name,pts,faces,(0,-1,0),col,.030)

def build_hair():
    start=len(G.PARTS)
    n=14;verts=[]
    for j in range(5):
        for i in range(n):
            a=2*math.pi*i/n;f=max(0,math.cos(a));side=abs(math.sin(a))
            z=[1.380,1.345,1.265,1.094+.155*f+.052*side,1.083+.172*f+.055*side][j]
            rx,front_r,back_r=[(.035,.028,.033),(.110,.100,.120),(.143,.119,.151),(.121,.105,.135),(.067,.070,.080)][j]
            x=rx*math.sin(a);c=-math.cos(a)
            verts.append((x,(front_r if c<0 else back_r)*c+.014,z))
    faces=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(4) for i in range(n)]
    faces+=[tuple(range(n-1,-1,-1)),tuple(4*n+i for i in range(n))]
    G.mesh('Closed angular hair volume',verts,faces,'hair','head')
    plane('Left swept fringe',[(121,66),(86,79),(68,112),(49,155),(43,174),(68,162),(86,148),(117,127)],(88,118),'hair')
    plane('Long centre fringe',[(121,66),(163,76),(169,110),(158,144),(124,164),(95,167),(92,149),(108,113)],(134,121),'hair_light',-.012)
    plane('Right fringe wedge',[(164,77),(195,92),(211,125),(215,159),(201,194),(185,170),(177,145)],(190,133),'hair',-.003)
    plane('Outer right blade',[(196,91),(218,111),(238,153),(244,179),(223,172),(211,155)],(218,132),'hair_dark',.010)
    plane('Outer left blade',[(89,77),(66,90),(50,115),(36,131),(48,135),(64,119)],(60,110),'hair',.014)
    # The profile is built as overlapping angular planes over the solid cranium.
    # The rear of the head stays full; no thin floating leaves at the nape.
    for s in (-1,1):
        def side(points):return [(s*x,y,z) for x,y,z in points]
        patch('Upper side crown '+str(s),side([(.018,.023,1.376),(.090,.111,1.347),(.143,.151,1.295),(.158,.131,1.242),(.147,.042,1.262),(.122,-.035,1.322)]),
              [(0,1,4,5),(1,2,3,4)],(s,0,0),'hair',.033)
        patch('Middle side blade '+str(s),side([(.132,.018,1.296),(.157,.076,1.278),(.151,.148,1.237),(.135,.171,1.197),(.119,.130,1.214),(.134,.059,1.237)]),
              [(0,1,2,5),(2,3,4,5)],(s,0,0),'hair_light',.027)
        patch('Nape plane '+str(s),side([(.123,.052,1.214),(.144,.119,1.222),(.107,.163,1.171),(.080,.157,1.093),(.057,.120,1.100),(.094,.075,1.153)]),
              [(0,1,2,5),(2,3,4,5)],(s,0,0),'hair_dark',.030)
        patch('Temple point '+str(s),side([(.122,-.028,1.302),(.145,-.037,1.250),(.120,-.050,1.179),(.105,-.050,1.163),(.108,-.018,1.240)]),
              [(0,1,2,4),(2,3,4)],(s,0,0),'hair',.027)
        patch('Rear overlap '+str(s),side([(.025,.137,1.333),(.102,.158,1.297),(.130,.158,1.240),(.098,.173,1.218),(.064,.153,1.238),(.008,.164,1.267)]),
              [(0,1,2,5),(2,3,4,5)],(0,1,0),'hair',.026)
    # A tied fan-shaped knot: two solid chopped wedges and a short red band.
    crown_solid('Angular tied topknot',[(-.023,.039,1.366),(-.056,.059,1.454),(-.030,.069,1.486),
        (.011,.087,1.509),(.042,.086,1.429),(.024,.034,1.370),(.031,.036,1.432),(-.006,.022,1.481)])
    crown_solid('Topknot side fork',[(.006,.047,1.383),(.039,.092,1.468),(.087,.101,1.447),(.050,.029,1.391),(.021,.021,1.389)])
    G.loft('Rust hair tie',[(0,.048,1.370,.038,.025),(0,.048,1.385,.041,.027)],'red','head',n=8)
    for ob in G.PARTS[start:]:
        bevel=ob.modifiers.new('Small planar edge','BEVEL');bevel.width=.0010;bevel.segments=1
        bevel.limit_method='ANGLE';bevel.angle_limit=.9;bevel.harden_normals=True
        bpy.context.view_layer.objects.active=ob;bpy.ops.object.modifier_apply(modifier=bevel.name)
