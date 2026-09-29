"""Reference-built sailing dinghy. Metres; +X bow, stern tiller pivot is (-1.90,0,.64)."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
import sys,math,json
from pathlib import Path
import bpy
ROOT=yori.REGIONS
from village import build as v
OUT=yori.OUT/'sailboat';v.OUT=OUT
WOOD=(.20,.085,.026);TRIM=(.29,.15,.06);DARK=(.055,.03,.016);TEAL=(.045,.10,.12);CREAM=(.62,.57,.45);GOLD=(.65,.36,.06);METAL=(.20,.22,.21)

def hull():
 m=v.Mesh('SB_Hull')
 # Variable-width fore/aft stations make a pointed bow and a proper transom.
 xs=[-1.9,-1.55,-1.,-.4,.25,.85,1.35,1.72,1.9];ws=[.48,.65,.75,.775,.73,.60,.40,.18,.025]
 def ring(i,scale,z):return [(xs[i],s*ws[i]*scale,z) for s in [-1,1]]
 for i in range(len(xs)-1):
  for side in [-1,1]:
   for k,(za,zb,sa,sb) in enumerate([(-.28,-.14,.38,.70),(-.14,.10,.70,.90),(.10,.42,.90,1.)]):
    pts=[(xs[i],side*ws[i]*sa,za),(xs[i+1],side*ws[i+1]*sa,za),(xs[i+1],side*ws[i+1]*sb,zb),(xs[i],side*ws[i]*sb,zb)]
    m.poly(pts if side<0 else pts[::-1],tuple(c*(.77+.12*k) for c in TEAL))
   # Inner wooden skin slopes down to the cockpit floor, not a solid bathtub.
   p=[(xs[i],side*(ws[i]-.055),.40),(xs[i+1],side*(ws[i+1]-.055),.40),(xs[i+1],side*max(.01,ws[i+1]*.68-.06),.08),(xs[i],side*max(.01,ws[i]*.68-.06),.08)]
   m.poly(p if side<0 else p[::-1],WOOD)
   m.beam((xs[i],side*ws[i],.43),(xs[i+1],side*ws[i+1],.43),.08,.09,TRIM)
  m.poly([(xs[i],-ws[i]*.38,-.28),(xs[i],ws[i]*.38,-.28),(xs[i+1],ws[i+1]*.38,-.28),(xs[i+1],-ws[i+1]*.38,-.28)],TEAL)
  m.poly([(xs[i],-ws[i]*.70,.08),(xs[i+1],-ws[i+1]*.70,.08),(xs[i+1],ws[i+1]*.70,.08),(xs[i],ws[i]*.70,.08)],DARK)
  for j in range(4):
   a=-1+j*.5;b=a+.47
   m.poly([(xs[i],a*ws[i]*.66,.10),(xs[i+1],a*ws[i+1]*.66,.10),(xs[i+1],b*ws[i+1]*.66,.10),(xs[i],b*ws[i]*.66,.10)],tuple(c*(.91+.03*j) for c in WOOD))
 # Closed stern with varnished top cap.
 m.poly([(-1.9,-.48,.42),(-1.9,.48,.42),(-1.9,.48*.38,-.28),(-1.9,-.48*.38,-.28)],TEAL)
 m.poly([(-1.84,-.43,.4),(-1.84,-.17,.02),(-1.84,.17,.02),(-1.84,.43,.4)],WOOD)
 m.beam((-1.9,-.49,.44),(-1.9,.49,.44),.09,.09,TRIM)
 for x,w in [(-1.15,1.36),(.52,1.27)]:
  for xx in [-.08,.08]:m.box((x+xx,0,.43),(.15,w,.09),TRIM,bevel=.015)
  for y in [-w*.36,w*.36]:m.box((x,y,.24),(.075,.075,.4),DARK)
 for i in [1,3,5,6]:
  for s in [-1,1]:m.beam((xs[i],s*ws[i]*.65,.04),(xs[i],s*(ws[i]-.08),.38),.035,.04,TRIM)
 m.box((.30,0,.10),(.42,.14,.15),DARK,bevel=.02)
 m.lathe((.48,0,.1),[(0,.075),(4.10,.045)],WOOD,n=10)
 for z in [.40,1.4,3.96]:m.lathe((.48,0,z),[(0,.08),(.055,.08)],METAL,n=10)
 # One forestay, firmly attached to bow and mast.
 m.beam((1.72,0,.48),(.48,0,4.07),.012,.012,TRIM)
 m.box((-1.84,0,.55),(.16,.17,.14),METAL,bevel=.015)
 return m

def sail():
 m=v.Mesh('SB_Sail')
 # Local origin at mast/boom pivot. Boom extends aft; cut fabric has a modest belly.
 n=12
 def p(i,j):
  u=i/n;t=j/n
  return (-2.12*u,.15*math.sin(math.pi*u)*math.sin(math.pi*t),2.59*t)
 for i in range(n):
  for j in range(n-i):
   pts=[p(i,j),p(i+1,j),p(i,j+1)]
   color=GOLD if i>8 and j<3 else tuple(c*(.97+.025*((i+j)%3)) for c in CREAM)
   m.poly(pts,color);m.poly(pts[::-1],color)
   if j<n-i-1:
    q=[p(i+1,j),p(i+1,j+1),p(i,j+1)];m.poly(q,color);m.poly(q[::-1],color)
 # The spar stays rigid while the cloth is lowered onto it.
 for k,point in enumerate(m.vertices):
  u=-point[0]/2.12;t=point[2]/2.59
  m.colors[k]=(*m.colors[k][:3],max(0,min(1,27*u*t*(1-u-t))))
 for a,b in [((0,0,0),(0,0,2.59)),((0,0,2.59),(-2.12,0,0)),((0,0,0),(-2.12,0,0))]:m.beam(a,b,.013,.013,CREAM)
 return m

def boom():
 m=v.Mesh('SB_Boom')
 m.beam((.02,0,-.03),(-2.22,0,-.03),.045,.045,WOOD)
 return m

def wake():
 m=v.Mesh('SB_Wake')
 # Feathered ribbons have zero opacity at their edges and tail. Separate mesh
 # stays on the water surface instead of rocking with the hull.
 for side in [-1,1]:
  for start,end,y0,y1,width in [(1.6,-1.8,.20,.94,.07),(-1.7,-6.5,.72,1.65,.10),(-2.4,-5.2,.26,.58,.045)]:
   def point(t,k):
    x=start+(end-start)*t;y=side*(y0+(y1-y0)*t+.04*math.sin(t*20))
    return (x,y+side*(k-1)*width,0)
   for i in range(24):
    a=i/24;b=(i+1)/24
    for k in [0,1]:
     pts=[point(a,k),point(b,k),point(b,k+1),point(a,k+1)]
     first=len(m.vertices);m.poly(pts,(.63,.74,.72))
     for j,(t,edge) in enumerate([(a,k),(b,k),(b,k+1),(a,k+1)]):
      alpha=(.5 if edge==1 else 0)*math.sin(math.pi*t)**.6*(.18+.82*math.sin(t*22)**4)
      m.colors[first+j]=(*m.colors[first+j][:3],alpha)
 return m

def rudder():
 m=v.Mesh('SB_Rudder')
 m.box((-.07,0,-.51),(.24,.055,.62),WOOD,bevel=.015)
 m.beam((0,0,0),(1.0,-.22,.04),.03,.03,TRIM)
 m.beam((.91,-.20,.04),(1.07,-.235,.04),.032,.032,DARK)
 return m

def main():
 OUT.mkdir(exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
 bpy.ops.wm.read_factory_settings(use_empty=True)
 mat=bpy.data.materials.new('SailboatPalette');mat.use_nodes=True
 vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color';mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
 manifest={}
 for fn in [hull,sail,boom,rudder,wake]:
  m=fn();ob,report=v.export(m,mat);manifest[m.name]=report;bpy.data.objects.remove(ob,do_unlink=True)
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print('SAILBOAT BUILD COMPLETE',sum(a['triangles'] for a in manifest.values()),'triangles')
if __name__=='__main__':main()
