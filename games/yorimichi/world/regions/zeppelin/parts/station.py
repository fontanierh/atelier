"""Selected logical zeppelin geometry; no regional export callback."""
from zeppelin.primitives import CREAM, DARK, GOLD, M, PLANK, R, SAGE, STONE, WOOD, badge, bench, cylinder, math, np, rail, v
from zeppelin.layout import DECK_EDGE, MESHES, PARK_BRIDGE, PARK_WALK, STATIONS, belmonte_path
from village.layout import upper_surface

def station(index,h):
 s=STATIONS[index];ox,oy,oz=s['origin'];m=M(MESHES[index])
 def ground(x,y):
  if index==1:
   from hidamari.layout import height
   return float(height(x+ox,y+oy))-oz
  if index==2:
   from hidamari.layout import north_height
   return float(north_height(x+ox,y+oy))-oz
  if index==3:
   from belmonte import layout as bm_layout,source as bm_source
   return float(bm_source.terrain().height(x+ox-bm_layout.ORIGIN[0],y+oy-bm_layout.ORIGIN[1])+bm_layout.ORIGIN[2])-oz
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
    m.box((float(xx)+.5,float(yy)+.5,(top+min(z-.2,-.2))/2),(1.,1.,top-min(z-.2,-.2)),tuple(c*R.uniform(.97,1.03) for c in (STONE if index in (1,3) else (.23,.15,.075))))
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
 if index==3:belmonte_walk(m)
 return m

def park_walk(m,z):
 # The footpath to the footbridge is painted on the gate's ground (megapark/gate.py). The footbridge crosses the dell
 # beside the park from a timber sleeper on the level path to a concrete sill against the road deck's edge, which runs
 # across the bridge on a slant (DECK_EDGE). It is skateable end to end: the planks stand 5 mm proud of the path, and
 # the sill ramps from the planks' height to the deck's at its edge, then tucks under the deck, so the bridge never
 # lies on the road and no edge on the way is a step. A dark subfloor 1 mm under the planks' tops fills the gaps
 # between them, so a wheel or a pushing foot rides over a millimetre, never into a gap.
 from hidamari.layout import north_height
 (_,y),_=PARK_WALK
 (b0,_),(b1,_)=PARK_BRIDGE;top=z+.005
 for x in np.arange(b0,b1+.1,.24):m.box((float(x)+.11,y,top-.03),(.22,2.2,.06),tuple(c*R.uniform(.95,1.05) for c in PLANK),.008)
 m.poly([(b0,y-1.1,top-.001),(b1,y-1.1,top-.001),(b1,y+1.1,top-.001),(b0,y+1.1,top-.001)],WOOD)
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

def city_ground(x,y):
 """HD_Terrain's surface at (x, y): the layout height carved by the railway earthworks and levelled by the air
 station's pad, read off its grid like the mesh, and never below the exact surface."""
 from hidamari.layout import height,terrain_axes
 from train import earthworks
 from zeppelin.layout import city_pad
 def final(gx,gy):return city_pad(gx,gy,earthworks.carve(gx,gy,height(gx,gy)))
 xs,ys=map(np.asarray,terrain_axes())
 i=int(np.clip(np.searchsorted(xs,x)-1,0,len(xs)-2));j=int(np.clip(np.searchsorted(ys,y)-1,0,len(ys)-2))
 gx,gy=np.meshgrid(xs[i:i+2],ys[j:j+2]);z=np.asarray(final(gx,gy),float)
 u=(x-xs[i])/(xs[i+1]-xs[i]);w=(y-ys[j])/(ys[j+1]-ys[j])
 grid=z[0,0]*(1-u)*(1-w)+z[0,1]*u*(1-w)+z[1,0]*(1-u)*w+z[1,1]*u*w
 return float(max(grid,float(np.asarray(final(np.array([x]),np.array([y])),float).ravel()[0])))

def belmonte_walk(m):
 from belmonte import layout as bm_layout,source as bm_source
 surf=bm_source.terrain();path=belmonte_path()
 d=np.gradient(path,axis=0);d/=np.linalg.norm(d,axis=1)[:,None];n=np.column_stack([-d[:,1],d[:,0]])
 for i in range(len(path)-1):
  p=[]
  for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
   q=path[k]+n[k]*1.3*side
   z=float(surf.height(q[0]-bm_layout.ORIGIN[0],q[1]-bm_layout.ORIGIN[1])+bm_layout.ORIGIN[2])+.035
   p.append((float(q[0]),float(q[1]),z))
  m.poly(p,STONE)
  for a,b in [(p[0],p[1]),(p[2],p[3])]:
   m.poly([(a[0],a[1],a[2]-.18),(b[0],b[1],b[2]-.18),b,a],STONE)
