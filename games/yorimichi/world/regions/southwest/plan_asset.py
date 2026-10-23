"""Publish one completed Southwest logical source as bounded mesh inputs and final query data."""
import argparse
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--query-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    from atelier.export_manifest import real_directory
    real_directory(args.output); real_directory(args.query_output.parent)
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    from southwest import models
    from southwest.mesh import material
    import region_query
    from region_mesh_parts import plan
    source = models.construct(args.model, args.context)
    obj = source.object(material())
    # Old Southwest FBX exported only this render object. Its diagnostic boxes
    # never participated in native collision; preserve actual complex queries.
    region_query.save(args.query_output, [region_query.capture(obj)], owner=source.name, stage='final')
    value = plan(obj, args.output, partition='spatial' if obj.name == 'SW_Island' else 'whole', collisions=(), options=dict(
        apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
        mesh_smooth_type='FACE', colors_type='SRGB'))
    print('SOUTHWEST LOGICAL GEOMETRY COMPLETE', source.name, value['source_triangles'], len(value['pieces']), flush=True)


if __name__ == '__main__':
    main()
