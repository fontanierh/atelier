"""Inspect the downloaded rig before authoring deformation tests."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
from pathlib import Path
import bpy, json
from mathutils import Vector

ROOT=ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12/tripo-rig-r01'
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT/'raw/output_model_url.glb'))
report={'objects':[],'armatures':[],'materials':[]}
for o in bpy.context.scene.objects:
    if o.type=='MESH' and not o.vertex_groups:
        continue  # Blender-generated bone custom-shape helper, absent from source GLB.
    item={'name':o.name,'type':o.type,'matrix_world':[list(row) for row in o.matrix_world]}
    if o.type=='ARMATURE':
        item['bones']=[{'name':b.name,'parent':b.parent.name if b.parent else None,'head':list(o.matrix_world@b.head_local),'tail':list(o.matrix_world@b.tail_local),'matrix':[list(row) for row in b.matrix_local]} for b in o.data.bones]
        report['armatures'].append(item)
    elif o.type=='MESH':
        points=[o.matrix_world@v.co for v in o.data.vertices]
        totals=[sum(g.weight for g in v.groups) for v in o.data.vertices]
        item.update(vertices=len(points),triangles=sum(len(f.vertices)-2 for f in o.data.polygons),bounds_min=[min(p[i] for p in points) for i in range(3)],bounds_max=[max(p[i] for p in points) for i in range(3)],groups=[g.name for g in o.vertex_groups],unweighted=sum(w<.0001 for w in totals),weight_min=min(totals),weight_max=max(totals),max_influences=max(len(v.groups) for v in o.data.vertices))
    report['objects'].append(item)
for m in bpy.data.materials:
    p=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    report['materials'].append({'name':m.name,'roughness':p.inputs['Roughness'].default_value if p else None,'metallic':p.inputs['Metallic'].default_value if p else None})
(ROOT/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({**report,'armatures':[{**a,'bones':[{k:v for k,v in b.items() if k!='matrix'} for b in a['bones']]} for a in report['armatures']],'objects':[{k:v for k,v in o.items() if k not in ('bones','groups','matrix_world')} for o in report['objects']]},indent=2))
