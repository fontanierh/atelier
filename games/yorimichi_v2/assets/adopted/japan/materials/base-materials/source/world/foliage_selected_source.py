"""Build only one authored foliage LOD/seed or crown from explicit pre-export inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori
import bpy
import numpy as np
from mathutils import Vector
from atelier import mesh_ir,mesh_collision,export_manifest
from atelier.atomic_files import atomic_json
from mesh_pieces import capture,subset,create_mesh
import asset_mesh as A
import foliage_geometry as F
import far_crown
from build_foliage_lods import lod_mesh_type,triangles

OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
             mesh_smooth_type='FACE',path_mode='STRIP',embed_textures=False,use_tspace=False,colors_type='SRGB')


def piece(obj):
    source=capture(obj.data)
    return subset(source,tuple(range(len(source['counts']))),preserve_unused=True)


def collision(obj):
    """The exact original A.export authored cube and transform application, without exporting."""
    if 'trunk_collision' not in obj:return []
    values=obj['trunk_collision'];radius=values[0];a=Vector(values[1:4]);b=Vector(values[4:7])
    bpy.ops.mesh.primitive_cube_add(size=1,location=(a+b)*.5)
    hull=bpy.context.object;hull.name='UCX_'+obj.name+'_00';hull.scale=(radius*2,radius*2,(b-a).length+.2)
    hull.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler()
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    pose=dict(rotation_mode=hull.rotation_mode,location=list(hull.location),scale=list(hull.scale),
              rotation_euler=list(hull.rotation_euler),rotation_quaternion=list(hull.rotation_quaternion),rotation_axis_angle=list(hull.rotation_axis_angle))
    value=mesh_collision.encode(piece(hull),slots=[m.name for m in hull.data.materials],matrix=np.asarray(hull.matrix_world,dtype='<f8').tolist(),transform=pose)
    bpy.data.objects.remove(hull,do_unlink=True)
    return [value]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--definition',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--bounds',type=Path);parser.add_argument('--palette',type=Path);parser.add_argument('--last',type=Path)
    parser.add_argument('--last-materials',type=Path)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    row=json.loads(args.definition.read_text());key=export_manifest.name(row['key']);mode=row['mode'];kind=export_manifest.name(row['kind'])
    if (row.get('schema')!=1 or len(row['material_order'])!=len(set(row['material_order']))
            or set(row['material_order'])!=set(row['materials'])):raise ValueError('Incomplete selected foliage palette')
    bpy.ops.wm.read_factory_settings(use_empty=True);A.MATS.clear();A.LEAF_CROPS.clear()
    # Read only the material definitions projected into this selected source input.
    for label in row['material_order']:A.mat(label,**row['materials'][label])
    original=A.Mesh;crown=None
    try:
        if mode=='mesh':
            generate=getattr(F,row['generator'])
            if row['level'] and row['generator']!='grass_tuft':
                bounds=json.loads(args.bounds.read_text());lo,hi=map(Vector,bounds)
                A.Mesh=lod_mesh_type(original,generate,lo,hi,row['level'],[row['stride']]*row['level'])
            obj=generate(key,*row['arguments'],**({'lod':row['level']} if row['generator']=='grass_tuft' else {}))
        elif mode=='seed':
            palette=json.loads(args.palette.read_text());seed=A.Mesh(key);seed.box((0,0,.5),(1,1,1),A.MATS[palette[0]]);obj=seed.build()
        elif mode=='crown':
            meta,data=mesh_ir.decode(args.last.read_bytes());data['slots']=[A.MATS[label] for label in meta['slots']]
            mesh=create_mesh(key,data);obj=bpy.data.objects.new(key,mesh);bpy.context.scene.collection.objects.link(obj)
            # Original replace() changes the last authored mesh, retaining its object properties.
            last_materials=json.loads(args.last_materials.read_text())
            if last_materials['trunk_collision'] is not None:obj['trunk_collision']=last_materials['trunk_collision']
            palette=json.loads(args.palette.read_text());leaves=[m for m in palette if row['materials'][m].get('alpha')]
            if len(leaves)!=1:raise ValueError('Original crown needs exactly one leaf material')
            material=A.mat(far_crown.slot(kind),color=(1.,1.,1.));bounds=json.loads(args.bounds.read_text());lo,hi=map(Vector,bounds)
            crown=far_crown.replace(obj,A.MATS[leaves[0]],material,(hi-lo).length,far_crown.LEAF_TINTS.get(leaves[0],(1.,1.,1.)))
        else:raise ValueError('Unknown selected foliage source')
    finally:A.Mesh=original
    if not all(np.isfinite(tuple(vertex.co)).all() for vertex in obj.data.vertices):raise ValueError('Nonfinite original foliage')
    palette=[m.name for m in obj.data.materials];hulls=collision(obj)
    if mode=='mesh':
        expected=json.loads(args.palette.read_text()) if args.palette else list(row['materials'])
        if set(palette)!=set(expected):raise ValueError('Original authored palette changed')
    payload=mesh_ir.encode(piece(obj),key=key,slots=palette,matrix=np.asarray(obj.matrix_world,dtype='<f8').tolist(),options=OPTIONS,collisions=hulls)
    args.output.mkdir(parents=True,exist_ok=True);mesh_ir.write(args.output/(key+'.npz'),payload)
    material_rows=dict(row['materials'])
    for label in palette:
        if label not in material_rows:
            if mode!='crown' or label!=far_crown.slot(kind):raise ValueError('Unprojected foliage material')
            material_rows[label]=dict(color=[1.,1.,1.])
    atomic_json(args.output/(key+'.materials.json'),dict(materials=material_rows,material_order=list(row['material_order'])+[m for m in palette if m not in row['materials']],
        normals_domain=obj.data.normals_domain,trunk_collision=list(obj['trunk_collision']) if 'trunk_collision' in obj else None))
    report=dict(key=key,triangles=triangles(obj),materials=palette,collision_hulls=len(hulls),
                geometry_sha256=hashlib.sha256(payload).hexdigest(),
                materials_sha256=hashlib.sha256((args.output/(key+'.materials.json')).read_bytes()).hexdigest())
    if crown is not None:report['crown']=crown
    if key==kind:
        bounds=[[min(vertex.co[i] for vertex in obj.data.vertices) for i in range(3)],
                [max(vertex.co[i] for vertex in obj.data.vertices) for i in range(3)]]
        atomic_json(args.output/(key+'.bounds.json'),bounds);atomic_json(args.output/(key+'.palette.json'),palette)
        atomic_json(args.output/(key+'.base.json'),dict(bounds=bounds,materials=palette,trunk_collision=list(obj['trunk_collision']) if 'trunk_collision' in obj else None))
        report['base_sha256']=hashlib.sha256((args.output/(key+'.base.json')).read_bytes()).hexdigest()
    atomic_json(args.output/(key+'.report.json'),report)
    print('FOLIAGE SELECTED SOURCE COMPLETE',key,report['triangles'],flush=True)


if __name__=='__main__':main()
