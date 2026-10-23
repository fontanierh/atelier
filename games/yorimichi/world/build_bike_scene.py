"""Explicit diagnostic scene of independent source meshes; never an export prerequisite."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import yori  # noqa: E402
import bpy  # noqa: E402
from mathutils import Matrix  # noqa: E402
from atelier import mesh_ir  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from mesh_pieces import create_mesh  # noqa: E402
from region_mesh_parts import validate  # noqa: E402
from bike_sources import BUILDERS  # noqa: E402


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--plans',type=Path,required=True);parser.add_argument('--layout',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);real_directory(args.output.parent,create=True)
    if args.output.is_symlink():raise ValueError('Linked Bike review scene refused')
    info=json.loads(args.layout.read_text());info['steering_parts']=[key for key in BUILDERS if key.startswith('BK_Steer_')]
    model_path=yori.ASSETS/'vehicles/bike/build.py'
    spec=importlib.util.spec_from_file_location('bike_diagnostic_placement',model_path);model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    bpy.ops.wm.read_factory_settings(use_empty=True);material=model.material();objects={}
    for key in BUILDERS:
        directory=args.plans/key;value=validate(directory)
        if [row['name'] for row in value['pieces']]!=[key]:raise ValueError('Incomplete Bike diagnostic source member')
        meta,piece=mesh_ir.decode((directory/value['pieces'][0]['payload']).read_bytes())
        if meta['slots']!=['BikePalette'] or meta['collisions']:raise ValueError('Unexpected Bike diagnostic attributes')
        piece['slots']=[material];obj=bpy.data.objects.new(key,create_mesh(key,piece));bpy.context.collection.objects.link(obj)
        obj.matrix_world=Matrix(meta['matrix']);objects[key]=obj
    model.assemble(objects,info)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output));print('BIKE INDEPENDENT DIAGNOSTIC SCENE COMPLETE',flush=True)


if __name__=='__main__':main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
