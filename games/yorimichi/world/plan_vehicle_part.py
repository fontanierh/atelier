"""Construct exactly one original rigid vehicle part, without export or sibling work."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory,TRIANGLE_LIMIT  # noqa: E402
from region_mesh_parts import plan,capture_colliders  # noqa: E402
from vehicle_sources import FAMILIES  # noqa: E402

OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
    object_types=['MESH'],mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False)


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness] original-vehicle-construction-finishing
    A plan MUST finish exactly its selected original rigid part before source capture.
    Kart MUST retain the actual winding selftest, geometry hash before/after paint,
    positive seat/wheel/steering signed volume and original report fields. No finishing
    pass may move geometry or collision, and no sibling part may be constructed inline.
    """
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(argv)
    real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file():raise ValueError('Vehicle selected source must be regular')
    value=json.loads(args.source.read_text());family=value.get('family');key=value.get('asset')
    fields={'schema','family','asset','builder','program','material'}|({'data'} if family=='kart' else set())
    if (set(value)!=fields or value['schema']!=1
            or family not in FAMILIES or FAMILIES[family]['builders'].get(key)!=value['builder']
            or value['material']!=FAMILIES[family]['material']):raise ValueError('Incomplete selected vehicle source')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scope={'__vehicle_data':value.get('data',{})};exec(compile(value['program'],str(args.source),'exec'),scope)
    if family=='bike':material=scope['material']()
    else:
        material=bpy.data.materials.new(value['material']);material.use_nodes=True
        vc=material.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
        material.node_tree.links.new(vc.outputs['Color'],material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    if family=='kart':scope['winding_selftest']()
    mesh=scope[value['builder']]()
    if mesh.name!=('BK_Steer' if key.startswith('BK_Steer_') else key):raise ValueError('Vehicle constructor returned a different rigid owner')
    triangles=sum(len(face)-2 for face in mesh.faces)
    if not 0<triangles<=TRIANGLE_LIMIT:raise ValueError('Vehicle part requires explicit bounded native child support')
    vertices=mesh.verts if family=='bike' else mesh.vertices
    positions=np.asarray(vertices)
    report=dict(triangles=triangles,vertices=len(vertices),materials=1,collision_boxes=len(mesh.colliders) if family!='bike' else 0,
        min=positions.min(0).round(4).tolist(),max=positions.max(0).round(4).tolist())
    if family=='kart':
        geometry=scope['geometry_hash'](mesh)
        if key=='SM_Kart_Body':scope['finish_paint'](mesh)
        if scope['geometry_hash'](mesh)!=geometry:raise ValueError('Kart paint changed render/collision geometry')
        report['geometry_sha256']=geometry
        if key!='SM_Kart_Body' and scope['signed_volume'](mesh)<=0:raise ValueError('Kart component winding is inward')
    if family=='bike':
        report.pop('materials');report.pop('collision_boxes')
    obj=mesh.object(material);obj.name=key
    options=dict(OPTIONS,mesh_smooth_type='OFF',use_mesh_edges=False,colors_type='SRGB') if family=='bike' else OPTIONS
    plan(obj,args.output,collisions=capture_colliders(mesh.colliders) if family!='bike' else [],options=options,
         face_groups=[(key,tuple(range(len(obj.data.polygons))))])
    atomic_json(args.report,report)
    print('VEHICLE LOGICAL SOURCE COMPLETE '+key,flush=True)


if __name__=='__main__':main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
