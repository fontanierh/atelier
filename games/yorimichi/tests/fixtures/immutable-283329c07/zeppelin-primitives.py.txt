"""Shared zeppelin geometry primitives; no asset construction or exports."""
import math
import random
import bpy
import numpy as np
from mathutils import Matrix
from village import mesh as v
M = v.Mesh
R = random.Random(980)
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
