"""Construct one airborne Zeppelin asset from its own declared source closure."""
import argparse
import importlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.export_manifest import name, real_directory  # noqa: E402

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--builder', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name(args.asset); name(args.builder)
    real_directory(args.output)
    import bpy
    from zeppelin import primitives
    from village import mesh as village_mesh
    from region_mesh_parts import plan, capture_colliders
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # The airborne assets precede stations in the original authoring order; only
    # ship consumes randomness. Explicitly reset both streams in a warm process.
    primitives.R.seed(980)
    village_mesh.R.seed(76)
    builder = args.builder
    source = getattr(importlib.import_module('zeppelin.parts.' + builder), builder)()
    if source.name != args.asset:
        raise ValueError('Zeppelin constructor returned a different logical asset')
    material = bpy.data.materials.new('ZeppelinPalette')
    obj = source.object(material)
    plan(obj, args.output, collisions=capture_colliders(source.colliders), options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', use_custom_props=False))
    print('LOGICAL ZEPPELIN GEOMETRY COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__':
    main()
