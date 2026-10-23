"""Export one immutable foliage payload through the actual original portable A.export body."""
import argparse
import hashlib
import json
import stat
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori
import bpy
import numpy as np
from mathutils import Matrix
from atelier import mesh_ir,export_manifest
from atelier.model_files import regular_files
from mesh_pieces import create_mesh
import asset_mesh as A


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness] actual-portable-foliage-export
    Export ONLY the selected MeshIR source, preserving original material construction,
    portable texture detachment, FBX options and authored trunk-cube construction.
    Never read a sibling rendered export or invoke a foliage constructor. The material
    sidecar and every palette texture MUST be explicit action inputs.
    """
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--format',choices=['.fbx'],default='.fbx')
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    export_manifest.real_directory(args.input.parent)
    sidecar=args.input.with_suffix('.materials.json')
    if any(not stat.S_ISREG(path.lstat().st_mode) for path in (args.input,sidecar)):
        raise ValueError('Selected foliage inputs must be regular files')
    original=args.input.read_bytes();settings=sidecar.read_bytes()
    meta,data=mesh_ir.decode(original);key=meta['asset'];values=json.loads(settings)
    if (args.input.name!=key+'.npz' or len(values['material_order'])!=len(set(values['material_order']))
            or set(values['material_order'])!=set(values['materials']) or not set(meta['slots'])<=set(values['materials'])):
        raise ValueError('Foreign selected foliage identity or palette')
    if meta['schema']!=2 or bool(meta['collisions'])!=(values['trunk_collision'] is not None) or len(meta['collisions'])>1:
        raise ValueError('Original foliage collision ownership changed')
    root=export_manifest.real_directory(args.output,create=True)
    if regular_files(root)-{key+'.fbx','export.json'}:raise ValueError('Foreign atomic foliage output')
    bpy.ops.wm.read_factory_settings(use_empty=True);A.MATS.clear();A.LEAF_CROPS.clear()
    for label in values['material_order']:A.mat(label,**values['materials'][label])
    data['slots']=[A.MATS[label] for label in meta['slots']]
    mesh=create_mesh(key,data);obj=bpy.data.objects.new(key,mesh);bpy.context.scene.collection.objects.link(obj)
    obj.matrix_world=Matrix(meta['matrix'])
    if values['trunk_collision'] is not None:obj['trunk_collision']=values['trunk_collision']
    with tempfile.TemporaryDirectory(prefix='.export-',dir=root) as staging:
        A.OUTDIR=staging;A.export(obj,key,portable=True)
        if args.input.read_bytes()!=original or sidecar.read_bytes()!=settings:raise ValueError('Immutable foliage source changed')
        (Path(staging)/(key+'.fbx')).replace(root/(key+'.fbx'))
    positions=data['positions']@np.asarray(meta['matrix'])[:3,:3].T+np.asarray(meta['matrix'])[:3,3]
    export_manifest.publish_receipt(root,key=key,primary=key+'.fbx',triangles=data['triangles'],
        bounds=[positions.min(0).tolist(),positions.max(0).tolist()],metadata=dict(geometry_sha256=hashlib.sha256(original).hexdigest(),
        materials_sha256=hashlib.sha256(settings).hexdigest(),slots=meta['slots'],polygons=len(data['faces']),
        collision_hulls=len(meta['collisions']),uv_channels=[label for label,_ in data['uvs']]))
    print('ATOMIC FOLIAGE EXPORT COMPLETE',key,flush=True)


if __name__=='__main__':main()
