"""Build distant foliage from the same seeded shapes, UVs and palette as LOD0.

blender -b --python-exit-code 1 --python games/yorimichi/world/build_foliage_lods.py
Only new LOD files are exported; the detailed meshes and placements are untouched.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import build_assets as A

SPECS = {
    'Tree_Broad_A': (A.tree_broad,(1,8.5,4.6)),
    'Tree_Broad_B': (A.tree_broad,(2,7.0,3.8)),
    'Tree_Broad_C': (A.tree_broad,(3,10.0,5.4)),
    'Tree_Maple_A': (A.tree_maple,(21,6.5,6.0)),
    'Tree_Maple_B': (A.tree_maple,(22,5.2,4.6)),
    'Tree_Ginkgo': (A.tree_ginkgo,(23,9.0)),
    'Tree_Pine_A': (A.tree_pine,(4,13.0)), 'Tree_Pine_B': (A.tree_pine,(5,11.0)),
    'Tree_Cedar_A': (A.tree_cedar,(6,16.0)), 'Tree_Cedar_B': (A.tree_cedar,(7,13.0)),
    'Tree_Maple_lo': (A.tree_lo,(31,'maple',6.5,6.0)),
    'Tree_Ginkgo_lo': (A.tree_lo,(32,'ginkgo',9.0,4.2)),
    'Tree_Broad_lo': (A.tree_lo,(33,'broad',8.5,5.0)),
    'Bush_Green_A': (A.bush,(8,'LeafBroad',1.4)), 'Bush_Green_B': (A.bush,(9,'LeafBroad',1.0)),
    'Bush_Ochre_A': (A.bush,(10,'LeafOchre',1.5)), 'Bush_Ochre_B': (A.bush,(11,'LeafOchre',1.1)),
    'Bush_Flower_A': (A.bush_flower,(34,1.2)), 'Bush_Flower_B': (A.bush_flower,(35,.9)),
}


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    A.materials()
    output = yori.OUT/'foliage_lods'
    output.mkdir(parents=True,exist_ok=True)
    A.OUTDIR = str(output)
    OriginalMesh = A.Mesh
    grass_only = '--grass-only' in sys.argv
    report = json.loads((output/'manifest.json').read_text()) if grass_only and (output/'manifest.json').exists() else {}
    for name,(generate,args) in ({} if grass_only else SPECS).items():
        A.Mesh = OriginalMesh
        base = generate(name,*args)
        minimum = Vector(tuple(min(v.co[i] for v in base.data.vertices) for i in range(3)))
        maximum = Vector(tuple(max(v.co[i] for v in base.data.vertices) for i in range(3)))
        # Roadside crowns used to swap to unrelated, differently sized trees at
        # 35% screen size. Keep their seed, atlas and crown proportions at every
        # level, with an extra intermediate step before the cheapest far mesh.
        roadside = generate in (A.tree_broad,A.tree_maple,A.tree_ginkgo)
        sizes = [1.,.22,.09,.035] if roadside else ([1.,.07,.025] if name.endswith('_lo') else [1.,.08,.025])
        strides = (3,9,27) if roadside else (3,8)
        report[name] = {'triangles':[sum(len(p.vertices)-2 for p in base.data.polygons)],
                        'screen_sizes':sizes}
        for level,stride in enumerate(strides,1):
            class LodMesh(OriginalMesh):
                def __init__(self,*args):
                    super().__init__(*args)
                    self.card_number = 0

                def card(self,center,size,yaw,tilt,m,cell,normal,roll=0.,col=1.,col_bottom=None):
                    self.card_number += 1
                    # Caller-side RNG still advances for every source card. Every
                    # retained card therefore uses the original position and UV cell.
                    if (self.card_number-1)%stride: return
                    scale = min(math.sqrt(stride),3.0 if roadside else 2.2)
                    super().card(center,(size[0]*scale,size[1]*scale),yaw,tilt,m,cell,normal,roll,col,col_bottom)

                def quad(self,points,*args,**kwargs):
                    # Expanded clusters stay inside the source mesh bounds.
                    points = [Vector(tuple(max(minimum[i],min(maximum[i],p[i])) for i in range(3))) for p in points]
                    super().quad(points,*args,**kwargs)

                def tube(self,*args,**kwargs):
                    kwargs['n'] = min(kwargs.get('n',8),5 if level == 1 else 3)
                    super().tube(*args,**kwargs)

            A.Mesh = LodMesh
            lod_name = f'{name}_LOD{level}'
            obj = generate(lod_name,*args)
            triangles = sum(len(p.vertices)-2 for p in obj.data.polygons)
            assert triangles < report[name]['triangles'][-1],(name,level,triangles)
            assert all(math.isfinite(c) for v in obj.data.vertices for c in v.co)
            assert {m.name for m in obj.data.materials} == {m.name for m in base.data.materials},'LOD palette changed'
            report[name]['triangles'].append(triangles)
            A.export(obj,lod_name)
            bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.objects.remove(base,do_unlink=True)
    A.Mesh = OriginalMesh
    for name, seed in (('Grass_A', 12), ('Grass_B', 13)):
        report[name] = {'triangles':[40], 'screen_sizes':[1., .10, .035]}
        for level, expected in ((1,24), (2,8)):
            obj = A.grass_tuft(f'{name}_LOD{level}', seed, lod=level)
            triangles = sum(len(p.vertices)-2 for p in obj.data.polygons)
            assert triangles == expected, (name, level, triangles)
            report[name]['triangles'].append(triangles)
            A.export(obj, obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('FOLIAGE LODS COMPLETE',report,flush=True)


if __name__ == '__main__': main()
