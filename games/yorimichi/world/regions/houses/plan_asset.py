"""Construct one explicitly declared house or lot from its own parameters and final query data."""
import argparse
import importlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.export_manifest import name, real_directory  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--builder', required=True)
    parser.add_argument('--function', required=True)
    parser.add_argument('--mode', required=True, choices=['model', 'lot'])
    parser.add_argument('--seed', required=True, type=int)
    parser.add_argument('--prefix-draws', required=True, type=int)
    parser.add_argument('--data', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    for value in (args.asset, args.builder, args.function):
        name(value)
    if not 0 <= args.prefix_draws <= 1_000_000 or not -(2 ** 31) <= args.seed < 2 ** 31:
        raise ValueError('House random stream must have explicit bounded parameters')
    if (args.mode == 'lot') != (args.data is not None):
        raise ValueError('Only a house lot consumes final-terrain data')
    real_directory(args.output)
    import bpy
    from houses import geometry_mesh as kernel
    from region_mesh_parts import plan, capture_colliders
    bpy.ops.wm.read_factory_settings(use_empty=True)
    kernel.R.seed(args.seed)
    for _ in range(args.prefix_draws):
        kernel.R.random()
    module = importlib.import_module('houses.' + args.builder)
    constructor = getattr(module, args.function)
    if args.mode == 'lot':
        real_directory(args.data.parent)
        if args.data.is_symlink() or not args.data.is_file():
            raise ValueError('House lot requires its own regular query product')
        value = json.loads(args.data.read_text())
        if value.get('asset') != args.asset:
            raise ValueError('House lot query product belongs to another placement')
        ground = importlib.import_module('houses.lot_data').Ground(value)
        source = constructor(value['lot'], ground)
    else:
        source = kernel.Mesh(args.asset)
        constructor(source)
    if source.name != args.asset:
        raise ValueError('House constructor returned a different logical asset')
    materials = [bpy.data.materials.new(label) for label in ('Village', 'Ground')]
    obj = source.object(materials, kernel.house_shade if args.mode == 'model' else None)
    plan(obj, args.output, collisions=capture_colliders(source.colliders), options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', use_custom_props=False))
    print('LOGICAL HOUSE GEOMETRY COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__':
    main()
