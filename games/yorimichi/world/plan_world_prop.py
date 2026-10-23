"""Construct exactly one small original prop and capture its complete export input."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import asset_mesh  # noqa: E402
from atelier.export_manifest import TRIANGLE_LIMIT,real_directory  # noqa: E402
from region_mesh_parts import plan  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file():raise ValueError('World prop source must be regular')
    value=json.loads(args.source.read_text())
    if set(value)!={'schema','asset','builder','args','program','materials'} or value['schema']!=1:
        raise ValueError('Incomplete selected prop source')
    bpy.ops.wm.read_factory_settings(use_empty=True);asset_mesh.MATS.clear()
    for key,spec in value['materials'].items():asset_mesh.mat(key,**spec)
    scope={};exec(compile(value['program'],str(args.source),'exec'),scope)
    obj=scope[value['builder']](value['asset'],*value['args'])
    if obj.name!=value['asset']:raise ValueError('Prop constructor returned a different logical owner')
    triangles=sum(len(face.vertices)-2 for face in obj.data.polygons)
    if not 0<triangles<=TRIANGLE_LIMIT:
        raise ValueError('A growing rigid prop needs explicit native child/pivot support before export')
    plan(obj,args.output,options=dict(apply_unit_scale=True,apply_scale_options='FBX_SCALE_ALL',axis_forward='-Y',axis_up='Z',
        object_types=['MESH'],mesh_smooth_type='FACE',bake_anim=False,path_mode='STRIP',embed_textures=False,
        use_tspace=False,colors_type='SRGB'))
    print('WORLD PROP GEOMETRY COMPLETE '+obj.name,flush=True)


if __name__=='__main__':main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
