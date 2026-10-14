"""Export the Tuscan branch crowns and their matching authored HISM LODs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402
import json
import math

import bpy
from mathutils import Vector, Euler
import asset_mesh as A
from forest_trees import tree
from forest.specs import TUSCAN, FOREST
from asset_catalog import check_material_namespace
import forest_impostors


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    check_material_namespace([args[-1] for args in TUSCAN.values()], 'forest')
    A.materials()
    old_tex=A.TEX;A.TEX=str(yori.OUT/'forest/textures')
    for _,_,_,_,slot in TUSCAN.values():A.mat(slot,texture='T_'+slot+'.png',alpha=True)
    A.TEX=old_tex
    output=yori.OUT/'forest';output.mkdir(parents=True,exist_ok=True)
    A.OUTDIR=str(output);original=A.Mesh;report={}
    for name,args in (TUSCAN | FOREST).items():
        A.Mesh=original;base=tree(name,*args,library=A);A.export(base,name)
        minimum=Vector(tuple(min(v.co[i] for v in base.data.vertices) for i in range(3)))
        maximum=Vector(tuple(max(v.co[i] for v in base.data.vertices) for i in range(3)))
        dimensions={'height':maximum.z,'spread':max(maximum.x-minimum.x,maximum.y-minimum.y)}
        counts=[sum(len(p.vertices)-2 for p in base.data.polygons)]
        for level,stride in enumerate((4,12),1):
            class LodMesh(original):
                def __init__(self,*args):super().__init__(*args);self.cards=0;self.branch_detail=level<2
                def begin_canopy(self,count):
                    self.cards=0
                    keep=min(count,max(4,math.ceil(count/stride)))
                    self.selected={round(i*(count-1)/max(keep-1,1)) for i in range(keep)}
                    self.card_scale=math.sqrt(count/keep)
                def card(self,centre,size,yaw,tilt,*args,**kwargs):
                    index=self.cards
                    self.cards+=1
                    if index not in self.selected:return
                    scale=self.card_scale
                    rotation=Euler((math.radians(tilt),math.radians(kwargs.get('roll',0.)),yaw),'XYZ').to_matrix()
                    for sx,sz in ((-1,-1),(1,-1),(1,1),(-1,1)):
                        offset=rotation@Vector((sx*size[0]/2,0,sz*size[1]/2))
                        for axis in range(3):
                            if offset[axis]>1e-8:scale=min(scale,(maximum[axis]-centre[axis])/offset[axis])
                            elif offset[axis]<-1e-8:scale=min(scale,(minimum[axis]-centre[axis])/offset[axis])
                    scale=max(scale,.01)
                    super().card(centre,(size[0]*scale,size[1]*scale),yaw,tilt,*args,**kwargs)
                def tube(self,*args,**kwargs):
                    kwargs['n']=min(kwargs.get('n',8),5 if level==1 else 3)
                    super().tube(*args,**kwargs)
            A.Mesh=LodMesh;obj=tree(f'{name}_LOD{level}',*args,library=A)
            count=sum(len(p.vertices)-2 for p in obj.data.polygons)
            assert count<counts[-1],(name,level,count)
            counts.append(count);A.export(obj,obj.name);bpy.data.objects.remove(obj,do_unlink=True)
        proxy=forest_impostors.bake(base,output)
        bark='BarkOlive' if args[0]=='olive' else 'BarkTuscan' if name in TUSCAN else 'Bark'
        A.Mesh=original;obj=forest_impostors.mesh(name,proxy,A.MATS[bark])
        counts.append(sum(len(p.vertices)-2 for p in obj.data.polygons));A.export(obj,obj.name)
        bpy.data.objects.remove(obj,do_unlink=True)
        report[name]={**dimensions,'leaf':args[-1],'triangles':counts,'screen_sizes':[1.,.24,.075,.018],
                      'impostor':proxy,'impostor_slot':name+'_Impostor','impostor_bark':bark}
        bpy.data.objects.remove(base,do_unlink=True)
        print('FOREST CROWN COMPLETE',name,counts,flush=True)
    A.Mesh=original
    (output/'trees.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FOREST COMPLETE',len(report),flush=True)


if __name__=='__main__':main()
