"""Selected logical zeppelin geometry; no regional export callback."""
from zeppelin.primitives import AirshipMesh, CREAM, DARK, GOLD, Matrix, PLANK, R, SAGE, WOOD, bench, math, np, rail, v

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
