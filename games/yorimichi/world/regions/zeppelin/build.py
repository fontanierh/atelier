"""Build the approved open-deck zeppelin and detailed, grounded station modules."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import sys,math,json,random
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix
ROOT=yori.REGIONS
from village import build as v
from village.layout import upper_surface
from zeppelin.layout import STATIONS,MESHES,PARK_WALK,PARK_BRIDGE,DECK_EDGE,PROPELLER_CENTERS,PROPELLER_RADIUS
M=v.Mesh;OUT=yori.OUT/'zeppelin';R=random.Random(980)
CREAM=(.68,.61,.46);SAGE=(.19,.245,.14);GOLD=(.50,.32,.09);WOOD=(.18,.075,.026);PLANK=(.32,.17,.067);DARK=(.055,.027,.012);STONE=(.25,.25,.22)

class AirshipMesh(M):
 def object(self,material):
  obj=super().object(material);data=obj.data;normals=[(0,0,0)]*len(data.loops)
  fabric=bpy.data.materials.get('ZeppelinFabric')
  if fabric is None:fabric=material.copy();fabric.name='ZeppelinFabric'
  data.materials.append(fabric)
  # Continuous fabric normals avoid a dark, disc-shaped terminator at the nose.
  # Keep deck, fittings and fins flat shaded; panel colours retain the fabric seams.
  for face in data.polygons:
   if any(i>=self.envelope_vertices for i in face.vertices):continue
   face.use_smooth=True;face.material_index=1
   for li in face.loop_indices:
    x,y,z=data.vertices[data.loops[li].vertex_index].co;z-=6.5
    d=169-x*x
    if d<1e-5:n=np.array([1 if x>0 else -1,0,0])
    else:
     a=4*(d/169)**.375;b=4*math.sqrt(d/169)
     n=np.array([x/d*(.75*y*y/(a*a)+z*z/(b*b)),y/(a*a),z/(b*b)]);n/=np.linalg.norm(n)
    normals[li]=tuple(n)
  data.normals_split_custom_set(normals)
  return obj

def cylinder(m,c,r,h,color,n=16):m.lathe(c,[(0,0),(0,r),(h,r),(h,0)],color,n)
def xlathe(m,c,profile,color,n=24):
 old=m.transform.copy();m.transform=old@Matrix.Translation(c)@Matrix.Rotation(math.pi/2,4,'Y');m.lathe((0,0,0),profile,color,n);m.transform=old

def ring(m,coords,z,width=.075,col=WOOD):
 for a,b in zip(coords,coords[1:]+coords[:1]):m.beam((*a,z),(*b,z),width,width,col)

def rail(m,a,b,z,post=True):
 for h in [.42,.98]:m.beam((a[0],a[1],z+h),(b[0],b[1],z+h),.095,.11,PLANK)
 if post:
  for p in [a,b]:m.box((*p,z+.52),(.13,.13,1.04),WOOD,.016)

def bench(m,x,y,z,w=1.8):
 for xx in [-w*.35,w*.35]:m.box((x+xx,y,z+.23),(.12,.34,.46),WOOD)
 for yy in [-.13,.13]:m.box((x,y+yy,z+.49),(w,.24,.09),PLANK,.012)
 for xx in [-w*.4,w*.4]:m.box((x+xx,y+.21,z+.64),(.095,.095,.72),WOOD)
 for zz in [.75,.93]:m.box((x,y+.22,z+zz),(w,.09,.15),PLANK,.014)

def badge(m,x,y,z,s=1):
 # Flush sign pictogram, facing local -Y.
 pts=[(x,y,z)]+[(x+math.cos(a)*s*.48,y,z+math.sin(a)*s*.48) for a in np.linspace(0,math.pi,17)]
 m.poly(pts,GOLD);m.poly(pts[::-1],GOLD)
 for a in np.linspace(.15,math.pi-.15,9):
  m.beam((x+math.cos(a)*s*.61,y,z+math.sin(a)*s*.61),(x+math.cos(a)*s*.85,y,z+math.sin(a)*s*.85),s*.065,.018,GOLD)
 m.box((x,y,z-.13*s),(1.55*s,.025,.075*s),GOLD)

def ship():
 m=AirshipMesh('ZP_Airship');K=64
 # Put both gold bands directly into the envelope topology, avoiding overlapping shells.
 cuts=sorted(list(np.linspace(-math.pi/2,math.pi/2,41))+[math.asin(x/13) for x in [-10.67,-10.53,10.73,10.87]])
 for t0,t1 in zip(cuts[:-1],cuts[1:]):
  for k in range(K):
   a=math.tau*k/K;b=math.tau*(k+1)/K
   def point(t,q):return (13*math.sin(t),4*max(0,math.cos(t))**.75*math.cos(q),6.5+4*math.cos(t)*math.sin(q))
   pts=[point(t0,a),point(t1,a),point(t1,b),point(t0,b)]
   mx=13*math.sin((t0+t1)/2)
   c=GOLD if abs(mx+10.6)<.071 or abs(mx-10.8)<.071 else SAGE if math.sin((a+b)/2)<-.40 else CREAM
   factor=1+(.018 if k%8==0 else -.008 if k%8==7 else 0)
   m.poly(pts[::-1],tuple(x*factor for x in c))
 m.envelope_vertices=len(m.vertices)
 # Four solid tail fins at the rear (-X), with gold inlay and no broken front geometry.
 for angle in [0,math.pi/2,math.pi,math.pi*1.5]:
  old=m.transform.copy();m.transform=old@Matrix.Translation((0,0,6.5))@Matrix.Rotation(angle,4,'X')
  outline=[(-12.1,0,1.0),(-12.7,0,3.8),(-8.8,0,3.35),(-7.7,0,1.8)]
  for side in [-1,1]:m.poly([(x,side*.075,z) for x,y,z in (outline if side>0 else outline[::-1])],SAGE)
  for i in range(4):a=outline[i];b=outline[(i+1)%4];m.poly([(a[0],-.075,a[2]),(b[0],-.075,b[2]),(b[0],.075,b[2]),(a[0],.075,a[2])],GOLD if i==1 else SAGE)
  m.transform=old
 # Flat usable floor on a shallow closed boat hull; rail gap is centred on -Y.
 outline=[(6.5*math.cos(a),1.75*math.sin(a)) for a in np.linspace(0,math.tau,49)[:-1]]
 low=[(x*.93,y*.78,-.52) for x,y in outline]
 m.poly(list(reversed(low)),DARK);m.poly([(x,y,-.03) for x,y in outline],PLANK)
 for i in range(len(outline)):
  j=(i+1)%len(outline);x,y=outline[i];xx,yy=outline[j]
  m.poly([low[i],low[j],(xx,yy,-.05),(x,y,-.05)],WOOD)
 for y in np.arange(-1.62,1.65,.20):
  w=13*math.sqrt(max(0,1-(y/1.75)**2));m.box((0,float(y),-.015),(w,.187,.05),tuple(c*R.uniform(.95,1.05) for c in PLANK))
 for i in range(24):
  a=math.tau*i/24;b=math.tau*(i+1)/24
  p=(6.45*math.cos(a),1.70*math.sin(a));q=(6.45*math.cos(b),1.70*math.sin(b))
  if p[1]<-1.6 and min(p[0],q[0])<.9 and max(p[0],q[0])>-.9:continue
  rail(m,p,q,0,post=i%2==0)
 rail(m,(-1.67,-1.64),(-.85,-1.70),0)
 rail(m,(.85,-1.70),(1.67,-1.64),0)
 for x in [-.85,.85]:m.box((x,-1.70,.52),(.14,.14,1.04),WOOD)
 for x in [-3.7,3.7]:
  bench(m,x,.96,0,2.0)
 # The deck is supported independently of both motors.
 for x in [-4.7,4.7]:
  for y in [-1.35,1.35]:
   m.box((x,y,1.65),(.20,.20,3.30),SAGE,.018)
   for z in [.18,3.10]:m.box((x,y,z),(.29,.29,.22),GOLD,.02)
 # Tessellated sunrise conforms to the convex fabric (large flat decals cut into it).
 for side in [-1,1]:
  def decal(points):
   out=[]
   for x,z in points:
    z+=6.6;t=math.asin(x/13)
    yy=4*math.cos(t)**.75*math.sqrt(max(0,1-((z-6.5)/(4*math.cos(t)))**2))+.032
    out.append((x,side*yy,z))
   m.poly(out if side<0 else out[::-1],GOLD)
  for i in range(16):
   r0=.96*i/16;r1=.96*(i+1)/16
   for j in range(32):
    a=math.pi*j/32;b=math.pi*(j+1)/32
    decal([(r0*math.cos(a),r0*math.sin(a)),(r1*math.cos(a),r1*math.sin(a)),(r1*math.cos(b),r1*math.sin(b)),(r0*math.cos(b),r0*math.sin(b))])
  for a in np.linspace(.15,math.pi-.15,9):
   for i in range(12):
    r0=1.22+.48*i/12;r1=1.22+.48*(i+1)/12
    decal([(r*math.cos(a)+w*math.sin(a),r*math.sin(a)-w*math.cos(a)) for r,w in [(r0,.05),(r1,.05),(r1,-.05),(r0,-.05)]])
  for x in np.linspace(-1.55,1.5,62):decal([(x,-.34),(x+.05,-.34),(x+.05,-.19),(x,-.19)])
 m.box((4.5,0,.57),(.32,.32,1.14),WOOD,.03)
 # Upright helm wheel centred above the podium, with spokes.
 coords=[(4.5+.32*math.cos(a),.02,1.22+.32*math.sin(a)) for a in np.linspace(0,math.tau,17)[:-1]]
 for i in range(16):m.beam(coords[i],coords[(i+1)%16],.055,.055,GOLD)
 for a in np.linspace(0,math.tau,7)[:-1]:m.beam((4.5,.02,1.22),(4.5+.38*math.cos(a),.02,1.22+.38*math.sin(a)),.035,.035,WOOD)
 # Two liferings mounted against the rails and a compact helm lantern.
 for side in [-1,1]:
  for i in range(32):
   a=math.tau*i/32;b=math.tau*(i+1)/32
   for j in range(8):
    def q(t,k):
     u=math.tau*k/8;r=.38+.10*math.cos(u)
     return (-3.5+r*math.cos(t),side*(1.60+.10*math.sin(u)),.62+r*math.sin(t))
    m.poly([q(a,j),q(b,j),q(b,j+1),q(a,j+1)],CREAM if i//4%2 else (.43,.14,.052))
 m.box((4.45,.60,1.16),(.075,.075,2.32),WOOD)
 m.beam((4.45,.60,2.31),(4.45,.02,2.31),.075,.075,WOOD)
 v.lantern(m,4.45,.02,1.9,.36)
 return m

def motors():
 m=M('ZP_Motors')
 # Direct envelope mounts; motors rotate only their separate blade mesh.
 for _,y,z in PROPELLER_CENTERS:
  side=1 if y>0 else -1
  m.beam((3.,side*3.65,z),(3.,y,z),.30,.30,SAGE)
  m.box((3.,side*3.85,z),(.55,.20,.52),GOLD,.025)
  xlathe(m,(2.25,y,z),[(0,0),(.18,.41),(.8,.5),(1.2,.32),(1.32,0)],SAGE)
  xlathe(m,(3.45,y,z),[(0,.19),(.24,.19),(.31,0)],GOLD)
 return m

def propeller():
 scale=PROPELLER_RADIUS/math.hypot(.09,1.16)
 m=M('ZP_Propeller');xlathe(m,(0,0,0),[(-.11,0),(-.1,.19),(.13,.19),(.20,0)],GOLD)
 for side in [-1,1]:
  pts=[(-.055,-.09,side*.12),(-.055,-.23,side*.75),(-.055,-.10,side*1.12),(-.055,.09,side*1.16),(-.055,.15,side*.62),(-.055,.09,side*.12)]
  pts=[(x,y*scale,z*scale) for x,y,z in pts]
  for x in [-.055,.055]:m.poly([(x,y,z) for _,y,z in (pts if x<0 else pts[::-1])],PLANK)
  for i in range(len(pts)):
   a=pts[i];b=pts[(i+1)%len(pts)];m.poly([(-.055,a[1],a[2]),(.055,a[1],a[2]),(.055,b[1],b[2]),(-.055,b[1],b[2])],WOOD)
 return m

def gate():
 m=M('ZP_Gate')
 for x in np.linspace(0,1.7,8):m.box((float(x),0,.50),(.18,.075,.86),PLANK,.01)
 for z in [.16,.85]:m.box((.85,-.06,z),(1.82,.075,.09),WOOD)
 for z in [.2,.78]:m.box((.02,-.07,z),(.18,.05,.07),GOLD)
 return m

def station(index,h):
 s=STATIONS[index];ox,oy,oz=s['origin'];m=M(MESHES[index])
 def ground(x,y):
  if index==1:
   from hidamari.layout import height
   return float(height(x+ox,y+oy))-oz
  if index==2:
   from hidamari.layout import north_height
   return float(north_height(x+ox,y+oy))-oz
  return float(upper_surface(h,x+ox,y+oy))-oz
 with m.at(s['origin']):
  # Detailed ticket hut; its front sill and every furnishing share the slab datum.
  with m.at((-6,-1.5,.12)):
   m.box((0,0,-.3),(6.8,4.9,.65),STONE,.04)
   m.box((0,-3,-.19),(7.4,1.9,.36),STONE,.02)
   m.box((0,0,1.5),(6.4,4.5,3),CREAM)
   for x in [-3.2,0,3.2]:
    for y in [-2.28,2.28]:m.box((x,y,1.55),(.19,.17,3.15),WOOD)
   for z in [.25,1,2.97]:
    for y in [-2.30,2.30]:m.box((0,y,z),(6.6,.16,.15),WOOD)
   for y in [-2.32,2.32]:
    for x in np.arange(-3.1,3.11,.27):m.box((float(x),y,.52),(.25,.08,.75),PLANK)
   v.roof(m,6.4,4.5,3.15,1.4)
   # Closed upward-facing roof underlay beneath separate rolled tiles.
   for side in [-1,1]:
    for k in range(20):
     a=k/20;b=(k+1)/20;zz=lambda t:3.15+1.4*(1-t)**1.10+.1*t**6+.005
     p=[(-3.85,side*2.925*a,zz(a)),(3.85,side*2.925*a,zz(a)),(3.85,side*2.925*b,zz(b)),(-3.85,side*2.925*b,zz(b))];m.poly(p if side>0 else p[::-1],v.PALETTE['roof'])
   v.window(m,-.9,-2.36,1.82,2.5,1.45,True);v.door(m,2,-2.36,.01,1.04,2.4)
   m.box((-.9,-2.75,1.12),(2.9,.8,.12),PLANK,.018)
   # Sheltered ticket opening, board, framed sign, lamp and back/side windows.
   m.box((-.9,-2.48,2.8),(2.7,.20,.55),WOOD,.04);badge(m,-.9,-2.595,2.63,.42)
   with m.at((0,0,0),180):v.window(m,0,-2.35,1.9,2,1.2)
   for side in [-1,1]:
    with m.at((side*3.25,0,0),side*90):v.window(m,0,-.04,1.9,1.3,1.3)
   for x in [-2.6,1.05]:
    m.beam((x,-2.3,2.98),(x,-2.75,2.98),.075,.075,WOOD)
    m.box((x,-2.75,2.91),(.045,.045,.22),WOOD)
    v.lantern(m,x,-2.75,2.4,.38)
   bench(m,-2.25,-3.3,0,1.6)
   v.pot(m,.7,-3.15,0,.63,'clay',plant=True)
   for z in [.15,.48]:m.box((3,-3.1,z),(.62,.5,.3),PLANK,.05)
   for y in [-2.7,2.7]:
    for x in [-3.45,3.45]:
     m.box((x,y,-.06),(.40,.40,.36),STONE,.03)
     m.box((x,y,1.62),(.14,.14,3.24),WOOD)
     m.beam((x,y,2.20),(x*.78,y,2.95),.11,.11,WOOD)
  # Level apron approaches, all slab edges penetrate the ground.
  for xx in np.arange(-10,11,1.):
   for yy in np.arange(-8.8,-5.1,1.):
    z=ground(float(xx),float(yy));top=.03
    m.box((float(xx)+.5,float(yy)+.5,(top+min(z-.2,-.2))/2),(1.,1.,top-min(z-.2,-.2)),tuple(c*R.uniform(.97,1.03) for c in (STONE if index==1 else (.23,.15,.075))))
  # A continuous small staircase, with ten 16.5cm rises, leads to the boarding pier.
  for k in range(10):
   top=(k+1)*.165;y=-7.9+k*.49
   bottom=min(ground(6,y)-.2,0)
   m.box((6,y,(bottom+top)/2),(2.6,.51,top-bottom),PLANK,.007)
  m.box((6,-3.19,1.59),(2.6,.42,.12),PLANK,.006)
  for x in [4.55,7.45]:
   m.beam((x,-8.12,1.06),(x,-3.35,2.67),.10,.10,WOOD)
   for k in [0,4,9]:
    y=-7.9+k*.49;z=(k+1)*.165
    m.box((x,y,(ground(x,y)+z+1)/2),(.14,.14,z+1-ground(x,y)),WOOD)
  # Pier planks: top exactly 1.65, fixed gangway to the vessel side gate.
  for y in np.arange(-3.0,1.05,.22):m.box((6,float(y),1.59),(8,.22,.12),tuple(c*R.uniform(.97,1.03) for c in PLANK))
  for x in [2.25,6,9.75]:
   for y in [-2.8,.8]:
    bottom=ground(x,y)-.22
    m.box((x,y,(bottom+1.48)/2),(.24,.24,1.48-bottom),WOOD)
    m.box((x,y,bottom+.20),(.62,.62,.5),STONE,.05)
   m.beam((x,-2.8,.15),(x,.8,1.46),.16,.16,WOOD)
  for y in [-3.02,1.04]:
   spans=[(2,5.08),(6.92,10)] if y>0 else [(2,4.6),(7.4,10)]
   for a,b in spans:rail(m,(a,y),(b,y),1.65)
  for x in [2,10]:rail(m,(x,-3),(x,1.04),1.65)
  # Separate visible ramp mesh is static while docked; runtime hides its final section in flight.
  # Runtime owns the retractable final gangway and dock safety gate.
  # Sign and tidy planted borders outside the path.
  m.box((-10,-5.6,1.15),(.18,.18,2.6),WOOD);m.beam((-10.3,-5.6,2.36),(-8.3,-5.6,2.36),.16,.14,WOOD)
  m.box((-9.25,-5.62,1.82),(1.55,.12,.8),WOOD,.04);badge(m,-9.25,-5.69,1.60,.53)
  for x,y in [(-10,-3.2),(-1.7,-5.4),(10,-6.5)]:
   bottom=min(ground(x,y)-.08,0);m.box((x,y,(bottom+.45)/2),(1.5,.9,.45-bottom),STONE,.06)
   m.box((x,y,.43),(1.32,.72,.06),DARK)
   for j in range(7):
    px=x+R.uniform(-.55,.55);py=y+R.uniform(-.25,.25)
    cylinder(m,(px,py,.43),.022,.33,SAGE,6)
    for a in np.linspace(0,math.tau,5)[:-1]:
     pts=[(px-.055*math.sin(a),py+.055*math.cos(a),.52),(px+.055*math.sin(a),py-.055*math.cos(a),.52),(px+.23*math.cos(a),py+.23*math.sin(a),.68)]
     m.poly(pts,SAGE);m.poly(pts[::-1],SAGE)
    cylinder(m,(px,py,.73),.13,.05,R.choice([GOLD,(.44,.15,.05),CREAM]),6)
  for x in [2,10]:
   m.box((x,-2.86,2.52),(.12,.12,1.74),WOOD)
   m.beam((x,-2.86,3.37),(x,-3.03,3.37),.08,.08,WOOD)
   v.lantern(m,x,-3.03,2.95,.42)
 if index==2:park_walk(m,oz)
 return m

def park_walk(m,z):
 # The footpath to the footbridge is painted on the gate's ground (megapark/gate.py). The footbridge crosses the dell
 # beside the park from a timber sleeper on the level path to a concrete sill against the road deck's edge, which runs
 # across the bridge on a slant (DECK_EDGE). It is skateable end to end: the planks stand 5 mm proud of the path, and
 # the sill ramps from the planks' height to the deck's at its edge, then tucks under the deck, so the bridge never
 # lies on the road and no edge on the way is a step.
 from hidamari.layout import north_height
 (_,y),_=PARK_WALK
 (b0,_),(b1,_)=PARK_BRIDGE;top=z+.005
 for x in np.arange(b0,b1+.1,.24):m.box((float(x)+.11,y,top-.03),(.22,2.2,.06),tuple(c*R.uniform(.95,1.05) for c in PLANK),.008)
 m.box((b0+.15,y,z-.1),(.3,2.5,.2),WOOD,.02)
 (ex,ey,ez),slope,rise=DECK_EDGE
 edge=lambda yy:(ex+slope*(yy-ey),ez+rise*(yy-ey))
 south,north=edge(y-1.25),edge(y+1.25)
 rim=[(b1,y-1.25),(south[0],y-1.25),(north[0],y+1.25),(b1,y+1.25)]
 lift=[top,south[1],north[1],top]
 foot=z-.7
 m.poly([(a,b,h) for (a,b),h in zip(rim,lift)],STONE)
 m.poly([(south[0],y-1.25,south[1]),(south[0]+.05,y-1.25,south[1]-.01),(north[0]+.05,y+1.25,north[1]-.01),(north[0],y+1.25,north[1])],STONE)
 for k in (0,2,3):
  (a0,c0),(a1,c1)=rim[k],rim[(k+1)%4];h0,h1=lift[k],lift[(k+1)%4]
  m.poly([(a0,c0,foot),(a1,c1,foot),(a1,c1,h1),(a0,c0,h0)],STONE)
 for side in [-1,1]:
  m.beam((b0,y+side*.85,top-.16),(b1+.05,y+side*.85,top-.16),.14,.2,WOOD)
  for x in [b0+2.6,b0+7.1,b0+11.6]:
   ground=float(north_height(x,y+side*.98))
   if ground>z-.45:continue
   bottom=ground-z-.35
   m.box((x,y+side*.98,z+(bottom-.06)/2),(.2,.2,-.06-bottom),WOOD)
   m.box((x,y+side*.98,z+bottom+.25),(.5,.5,.5),STONE,.04)
  rail(m,(b0+.2,y+side*1.08),(b1-.3,y+side*1.08),top)

def gangway():
 m=M('ZP_Gangway')
 for y in np.arange(.10,1.3,.20):m.box((0,float(y),-.06),(1.7,.20,.12),PLANK)
 for x in [-.88,.88]:rail(m,(x,0),(x,1.30),0)
 return m

def main():
 OUT.mkdir(exist_ok=True);(OUT/'assets').mkdir(exist_ok=True);v.OUT=OUT
 bpy.ops.wm.read_factory_settings(use_empty=True)
 mat=bpy.data.materials.new('ZeppelinPalette');mat.use_nodes=True;vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color';mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
 h=np.load(yori.OUT/'heightmap.npy');report={}
 for m in [ship(),motors(),propeller(),gate(),gangway(),*[station(i,h) for i in range(len(STATIONS))]]:
  ob,report[m.name]=v.export(m,mat)
  report[m.name]['materials']=len(ob.data.materials)
 m=M('ZP_Trail');world=json.loads((yori.OUT/'world.json').read_text());path=np.array(world['zeppelin']['trail']);d=np.gradient(path[:,:2],axis=0);d/=np.linalg.norm(d,axis=1)[:,None];n=np.column_stack([-d[:,1],d[:,0]])
 for i in range(len(path)-1):
  p=[]
  for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
   q=path[k,:2]+n[k]*1.25*side;p.append((*q,float(upper_surface(h,*q))+.04))
  m.poly(p,(.25,.16,.079))
 # City pedestrian link skirts existing road and ends at the new southern apron.
 from hidamari.layout import height
 for x in np.arange(1248,1279,.5):
  p=[(xx,yy,float(height(xx,yy))+.035) for xx,yy in [(x,297.6),(x+.5,297.6),(x+.5,299.2),(x,299.2)]];m.poly(p,STONE)
 _,report[m.name]=v.export(m,mat)
 from zeppelin.check_rotors import check
 check()
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Zeppelin.blend'))
 (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 print('ZEPPELIN BUILD COMPLETE',sum(x['triangles'] for x in report.values()),flush=True)
if __name__=='__main__':main()
