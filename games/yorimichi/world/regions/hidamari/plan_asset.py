"""Construct only one logical Hidamari asset and publish bounded mesh inputs, not FBX."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yori  # noqa: E402,F401

from atelier.export_tasks import name, real_directory  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--city', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name(args.asset)
    real_directory(args.output, create=True)
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from hidamari import build, surfaces
    from region_mesh_parts import plan
    surfaces._materials.clear()
    city = json.loads(args.city.read_text())
    builders = build.asset_builders(city)
    if args.asset not in builders:
        raise ValueError('Unknown logical Hidamari asset: ' + args.asset)
    source = builders[args.asset]()
    if source.name != args.asset:
        raise ValueError('Logical builder returned another asset')
    if surfaces.textured(source.name):
        obj, _ = surfaces.mesh_object(source)
    else:
        material = bpy.data.materials.new('HidamariPalette')
        material.use_nodes = True
        colour = material.node_tree.nodes.new('ShaderNodeVertexColor'); colour.layer_name = 'Color'
        material.node_tree.links.new(colour.outputs['Color'], material.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
        obj = source.object(material)
    from region_mesh_parts import capture_colliders
    collisions = capture_colliders(source.colliders)
    plan(obj, args.output, collisions=collisions, options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', use_custom_props=False))
    print('LOGICAL CITY GEOMETRY COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__':
    main()
