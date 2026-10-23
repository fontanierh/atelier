"""Construct one explicitly declared SwordCamp asset; no region-wide construction or export."""
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
    parser.add_argument('--parameters', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    name(args.asset); name(args.builder); name(args.function)
    parameters = json.loads(args.parameters)
    if not isinstance(parameters, dict): raise ValueError('Explicit constructor parameters required')
    real_directory(args.output)
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from swordcamp.mesh import ProcMesh
    from region_mesh_parts import plan, capture_colliders
    module = importlib.import_module('swordcamp.parts.' + args.builder)
    constructor = getattr(module, args.function)
    source = ProcMesh(args.asset)
    constructor(source, **parameters)
    material = bpy.data.materials.new('M_SwordCamp')
    obj = source.to_blender(material)
    hulls = capture_colliders([(centre, size, (0., 0., 0.)) for centre, size in source.colliders])
    plan(obj, args.output, collisions=hulls, options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', use_custom_props=False, path_mode='STRIP'))
    print('LOGICAL SWORDCAMP GEOMETRY COMPLETE ' + args.asset, flush=True)


if __name__ == '__main__': main()
