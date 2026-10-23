"""Independently cached real FBX roundtrip for exactly one bounded skate piece."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier import mesh_ir,export_manifest  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--export',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    meta,piece=mesh_ir.decode(args.input.read_bytes());name=meta['asset']
    receipt=export_manifest.validate(args.export,key=name)
    if meta['collisions'] or receipt['metadata']['geometry_sha256']!=export_manifest.sha(args.input):
        raise ValueError('Unexpected skate collision or stale atomic export input')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(args.export/receipt['primary']))
    objects=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']
    if len(objects)!=1:raise ValueError('A skate atomic primary must contain exactly one rendered mesh')
    obj=objects[0];mesh=obj.data;mesh.calc_loop_triangles()
    world=np.asarray([obj.matrix_world@vertex.co for vertex in mesh.vertices])
    matrix=np.asarray(meta['matrix']);original=piece['positions']@matrix[:3,:3].T+matrix[:3,3]
    error=float(max(np.abs(world.min(0)-original.min(0)).max(),np.abs(world.max(0)-original.max(0)).max()))
    if error>=.001 or len(mesh.loop_triangles)!=piece['triangles']:
        raise ValueError('Actual skate FBX roundtrip changed bounds or triangle count')
    if [layer.name for layer in mesh.uv_layers]!=[label for label,_ in piece['uvs']]:raise ValueError('Skate FBX roundtrip lost original UV channels')
    if len(mesh.color_attributes)!=len(piece['colours']):raise ValueError('Skate FBX roundtrip lost colour channels')
    used={meta['slots'][int(i)] for i in piece['materials']};actual={slot.name for slot in mesh.materials}
    if not used<=actual<=set(meta['slots']):raise ValueError('Skate FBX roundtrip changed source material membership')
    atomic_json(args.output,dict(schema=1,name=name,complete=True,fbx_sha256=receipt['sha256'],
        input_sha256=export_manifest.sha(args.input),triangles=piece['triangles'],bounds_error_mm=error*1000))
    print('SKATE ATOMIC FBX ROUNDTRIP COMPLETE',name,error*1000,flush=True)


if __name__=='__main__':main()
