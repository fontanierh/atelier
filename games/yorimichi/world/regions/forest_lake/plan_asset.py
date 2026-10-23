"""Construct exactly one lake logical asset from parameters or its explicit sampled event data."""
import argparse
import json
from pathlib import Path
import random
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from forest_lake import geometry  # noqa: E402
from village import mesh as lib  # noqa: E402
from region_mesh_parts import plan,capture_colliders  # noqa: E402

OWNERS=('Lake_Cabin','Lake_Water','Lake_Trail','Lake_Shore','Lake_Plants')
OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
             mesh_smooth_type='FACE',use_custom_props=False)


def replay(mesh,events):
    stack=[]
    try:
        for operation,args in events:
            if operation=='push':
                context=mesh.at(*args);context.__enter__();stack.append(context)
            elif operation=='pop':
                if not stack:raise ValueError('Unbalanced canonical lake frame')
                stack.pop().__exit__(None,None,None)
            elif operation in ('poly','beam'):
                getattr(mesh,operation)(*args)
            else:raise ValueError('Unsupported canonical lake source operation')
        if stack:raise ValueError('Incomplete canonical lake frame')
    finally:
        while stack:stack.pop().__exit__(None,None,None)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',choices=OWNERS,required=True)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--record',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    material=bpy.data.materials.new('LakePalette');material.use_nodes=True
    vc=material.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
    material.node_tree.links.new(vc.outputs['Color'],material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    mesh=lib.Mesh(args.asset)
    if args.asset=='Lake_Cabin':
        previous=lib.R
        try:
            lib.R=random.Random(76)
            geometry.cabin(mesh,random.Random(719))
        finally:lib.R=previous
    elif args.asset=='Lake_Water':
        geometry.water(mesh)
    else:
        source=json.loads(args.input.read_text())
        if source.get('schema')!=1 or source.get('name')!=args.asset:
            raise ValueError('Foreign selected lake query data')
        replay(mesh,source['events'])
    obj=mesh.object(material)
    value=plan(obj,args.output,collisions=capture_colliders(mesh.colliders),options=OPTIONS)
    atomic_json(args.record,dict(name=args.asset,triangles=value['source_triangles'],
        collision_boxes=len(mesh.colliders),pieces=[row['name'] for row in value['pieces']]))
    print('LAKE LOGICAL COMPLETE',args.asset,value['source_triangles'],len(value['pieces']),flush=True)


if __name__=='__main__':main()
