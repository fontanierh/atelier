"""Construct only one logical Hidamari asset and publish bounded mesh inputs, not FBX."""
import argparse
import json
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yori  # noqa: E402,F401

from atelier.export_manifest import name, real_directory  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--city', type=Path)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--query-output', type=Path)
    parser.add_argument('--source-output', type=Path)
    parser.add_argument('--source-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name(args.asset)
    real_directory(args.output)
    if (args.source_output is not None or args.source_only) and args.asset != 'HD_Harbor':
        raise ValueError('Only the Harbor cut consumes a pre-export city source')
    if args.source_only and args.source_output is not None:
        raise ValueError('Source-only output already owns the complete raw source')
    from hidamari import source_context
    context = source_context.read(args.context, args.asset)
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from hidamari import surfaces
    from village import mesh as kernel
    from region_mesh_parts import plan
    surfaces._materials.clear()
    if args.city is not None:
        real_directory(args.city.parent)
        if args.city.is_symlink() or not args.city.is_file():
            raise ValueError('City constructor requires its explicit layout projection')
    if args.city is not None:
        from hidamari.city_data import read as read_city
        city = read_city(json.loads(args.city.read_text()), args.asset)
    else:
        city = {}
    constructor = importlib.import_module('hidamari.logical.' + args.asset).construct
    source_context.apply(context, kernel)
    source = constructor(city)
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
    if args.query_output is not None:
        import region_query
        region_query.save(args.query_output, [region_query.capture(obj),
            *region_query.capture_colliders(args.asset, collisions)], owner=args.asset,
            stage='raw' if args.asset == 'HD_Harbor' else 'final')
    if args.source_output is not None or args.source_only:
        from mesh_pieces import capture
        import source_geometry
        source_geometry.write(args.output if args.source_only else args.source_output, capture(obj.data), owner=args.asset,
            slots=[material.name for material in obj.data.materials],
            matrix=[list(row) for row in obj.matrix_world], collisions=collisions)
    if args.source_only:
        print('RAW CITY SOURCE COMPLETE ' + args.asset, flush=True)
        return
    plan(obj, args.output, collisions=collisions, options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', use_custom_props=False))
    print('LOGICAL CITY GEOMETRY COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__':
    main()
