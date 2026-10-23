"""Plan one selected complete Zeppelin mesh; never export a sibling."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import argparse
import importlib
import bpy
from region_mesh_parts import plan,capture_colliders
from zeppelin.random_context import restore
from zeppelin.query_data import Queries
from zeppelin import primitives
from village import mesh as v


def main(kind=None,key=None):
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--query');parser.add_argument('--asset');parser.add_argument('--builder')
    args=parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else None)
    kind=kind or args.builder;key=key or args.asset
    allowed=dict(ship="ZP_Airship",motors="ZP_Motors",propeller="ZP_Propeller",gate="ZP_Gate",gangway="ZP_Gangway",trail="ZP_Trail")
    if kind=="station_data":
        if key not in ("ZP_Woodland","ZP_City","ZP_MegaPark","ZP_Belmonte"):raise ValueError("Unknown Zeppelin station")
    elif allowed.get(kind)!=key:raise ValueError("Explicit Zeppelin selection required")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    restore(key,primitives.R,v.R)
    print('Construct selected Zeppelin source '+key,flush=True)
    module=importlib.import_module('zeppelin.parts.'+kind)
    if kind=='station_data':
        from zeppelin.layout import MESHES
        queries=Queries(args.query)
        mesh=module.station(MESHES.index(key),queries=queries)
        if key=='ZP_City':
            assert min(p[1] for p in mesh.vertices)>queries.value['rail_clearance_min_y'],'Air-station geometry enters the railway clearance'
    elif kind=='trail':mesh=module.construct(Queries(args.query))
    else:mesh=getattr(module,kind)()
    if mesh.name!=key:raise ValueError('Selected Zeppelin constructor returned foreign owner')
    mat=bpy.data.materials.new('ZeppelinPalette');mat.use_nodes=True
    vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
    mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    print('Capture complete Zeppelin geometry '+key,flush=True)
    obj=mesh.object(mat)
    plan(obj,args.output,collisions=capture_colliders(mesh.colliders),options=dict(
        apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
        mesh_smooth_type='FACE',bake_anim=False,use_custom_props=False))
    print('LOGICAL ZEPPELIN GEOMETRY COMPLETE '+key,flush=True)

if __name__=="__main__":main()
