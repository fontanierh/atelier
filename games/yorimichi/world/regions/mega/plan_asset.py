"""Construct one mini-mega logical mesh without exporting its siblings."""
import argparse
import importlib
import json
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier.export_manifest import real_directory  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True, choices=['Mega_Ramp', 'Mega_Trim', 'Mega_Trail'])
    parser.add_argument('--data', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    real_directory(args.output)
    import bpy
    from village.mesh import Mesh
    from region_mesh_parts import plan, capture_colliders
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if args.asset == 'Mega_Trail':
        if args.data is None:
            raise ValueError('Mega trail requires its current final-surface data product')
        value = json.loads(args.data.read_text())
        if value.get('schema') != 1 or value.get('asset') != args.asset or not value.get('polygons'):
            raise ValueError('Missing complete final-surface trail product')
        source = Mesh(args.asset)
        for points in value['polygons']:
            source.poly(points, (.26, .14, .046))
    else:
        if args.data is not None:
            raise ValueError('The local ramp and trim must not consume world or trail data')
        # These two layers are authored together against the same riding profiles.
        # Only the selected layer becomes a planner product and an atomic export.
        source = next(mesh for mesh in importlib.import_module('mega.ride').build()
                      if mesh.name == args.asset)
    material = bpy.data.materials.new('MegaPalette')
    obj = source.object(material)
    plan(obj, args.output, collisions=capture_colliders(source.colliders), partition='whole', options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', use_custom_props=False))
    print('LOGICAL MEGA GEOMETRY COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__':
    main()
