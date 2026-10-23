"""Build the approved open-deck zeppelin and detailed, grounded station modules."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import sys,math,json,random
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix
ROOT=yori.REGIONS
from village import mesh as v
from village.layout import upper_surface
from zeppelin.layout import STATIONS,MESHES,PARK_WALK,PARK_BRIDGE,DECK_EDGE,PROPELLER_CENTERS,PROPELLER_RADIUS,belmonte_path,city_path
M=v.Mesh;OUT=yori.OUT/'zeppelin'
from zeppelin.parts.ship import ship
from zeppelin.parts.motors import motors
from zeppelin.parts.propeller import propeller
from zeppelin.parts.gate import gate
from zeppelin.parts.gangway import gangway
from zeppelin.parts.station import station, city_ground
from zeppelin.primitives import STONE


def main():
 OUT.mkdir(exist_ok=True);(OUT/'assets').mkdir(exist_ok=True);v.OUT=OUT
 bpy.ops.wm.read_factory_settings(use_empty=True)
 mat=bpy.data.materials.new('ZeppelinPalette');mat.use_nodes=True;vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color';mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
 h=np.load(yori.OUT/'heightmap.npy');report={}
 for m in [ship(),motors(),propeller(),gate(),gangway(),*[station(i,h) for i in range(len(STATIONS))]]:
  if m.name=='ZP_City':
   from hidamari import station_yard
   assert min(p[1] for p in m.vertices)>station_yard.Y1+2., 'Air-station geometry enters the railway clearance'
  ob,report[m.name]=v.export(m,mat)
  report[m.name]['materials']=len(ob.data.materials)
 m=M('ZP_Trail');world=json.loads((yori.OUT/'world.json').read_text());path=np.array(world['zeppelin']['trail']);d=np.gradient(path[:,:2],axis=0);d/=np.linalg.norm(d,axis=1)[:,None];n=np.column_stack([-d[:,1],d[:,0]])
 for i in range(len(path)-1):
  p=[]
  for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
   q=path[k,:2]+n[k]*1.25*side;p.append((*q,float(upper_surface(h,*q))+.04))
  m.poly(p,(.25,.16,.079))
 # The city link starts beyond the closed railway lane and reaches the moved apron without crossing the tracks.
 # It follows HD_Terrain as built (railway earthworks carved, then the apron pad), never the uncarved layout
 # height, which left it floating over the cutting's bank; side skirts close any gap at its edges.
 path=city_path();tangent=np.gradient(path,axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
 normal=np.column_stack([-tangent[:,1],tangent[:,0]])
 for i in range(len(path)-1):
  p=[]
  for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
   xx,yy=path[k]+normal[k]*.8*side;p.append((float(xx),float(yy),city_ground(xx,yy)+.04))
  m.poly(p,STONE)
  for a,b in [(p[0],p[1]),(p[2],p[3])]:
   m.poly([(a[0],a[1],a[2]-.35),(b[0],b[1],b[2]-.35),b,a],STONE)
 _,report[m.name]=v.export(m,mat)
 from zeppelin.check_rotors import check
 check()
 bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Zeppelin.blend'))
 (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
 print('ZEPPELIN BUILD COMPLETE',sum(x['triangles'] for x in report.values()),flush=True)
if __name__=='__main__':main()
