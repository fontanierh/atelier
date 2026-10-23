"""Construct exactly one skate logical asset from source definitions and pre-export query data."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from mesh_pieces import capture  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from skatepark import atomic_source as source,board,features,geom,pieces  # noqa: E402

OPTIONS=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
             mesh_smooth_type='FACE',use_custom_props=False,colors_type='SRGB')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',choices=source.BOARD+source.PARK,required=True)
    parser.add_argument('--materials',type=Path);parser.add_argument('--terrain',type=Path);parser.add_argument('--ao',type=Path)
    parser.add_argument('--record',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    real_directory(args.record.parent)
    if args.record.is_symlink() or (args.record.exists() and not args.record.is_file()):raise ValueError('Invalid selected skate metadata output')
    bpy.ops.wm.read_factory_settings(use_empty=True);name=args.asset
    if name in source.BOARD:
        mesh=getattr(board,dict(SM_SkateDeck='deck',SM_SkateTruck='truck',SM_SkateWheel='wheel')[name])()
        material=bpy.data.materials.new('SkateParkPalette');obj=geom.to_object(mesh,material)
    else:
        if name=='SM_SkateParkFeatures' and not features.MOD.available():raise ValueError('Current skate feature source library is incomplete')
        if name in ('SM_SkatePierPilings','SM_SkatePath'):
            packet=json.loads(args.terrain.read_text());read,complete=source.lookup(packet,name)
            if name=='SM_SkatePierPilings':mesh=features.pilings(None,sample_fn=read)
            else:
                frame={key:np.asarray(value) for key,value in packet['frame'].items()}
                mesh,_,_=features.path(frame,None,surface_fn=read)
            complete()
        elif name in ('SM_SkateParkFurniture','SM_SkateParkPlanting'):
            meshes=features.gardens(name);mesh=meshes[0 if name=='SM_SkateParkFurniture' else 1]
        else:mesh=getattr(features,dict(SM_SkatePier='pier',SM_SkateParkFeatures='park_features',SM_SkateParkDecals='decals')[name])()
        ao=None
        if name in source.AO:
            value=json.loads(args.ao.read_text())
            if value.get('schema')!=1 or value.get('name')!=name or value.get('geometry_sha256')!=source.geometry_sha(mesh):
                raise ValueError('Canonical joint AO does not bind current selected geometry')
            ao=value['values']
            if len(ao)!=len(mesh.faces) or any(len(row)!=len(face) or any(type(v) not in (int,float) or not np.isfinite(v) or not 0<=v<=1 for v in row)
                for row,face in zip(ao,mesh.faces)):raise ValueError('Incomplete current selected AO corner values')
        material=source.material_objects(args.materials);obj=geom.to_object(mesh,material,geom.shade(mesh,ao))
    captured=capture(obj.data)
    faces=[captured['vertex_indices'][start:start+count].tolist() for start,count in zip(captured['starts'],captured['counts'])]
    groups=pieces.groups(name,captured['positions'],faces) if name in source.PARK else None
    value=plan(obj,args.output,options=OPTIONS,face_groups=groups)
    atomic_json(args.record,dict(name=name,triangles=mesh.triangles,vertices=len(mesh.verts),
        min=np.asarray(mesh.verts).min(0).round(3).tolist(),max=np.asarray(mesh.verts).max(0).round(3).tolist(),
        material_slots=[slot.name for slot in obj.data.materials],geometry_sha256=source.geometry_sha(mesh),
        pieces=[row['name'] for row in value['pieces']]))
    print('SKATE SELECTED LOGICAL COMPLETE',name,mesh.triangles,len(value['pieces']),flush=True)


if __name__=='__main__':main()
