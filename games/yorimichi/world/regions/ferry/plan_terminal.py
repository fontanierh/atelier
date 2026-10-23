"""Construct and bound one terminal mesh from its selected program and exact query values."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import solid_mesh  # noqa: E402,F401 (actual shared primitive input)
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from region_mesh_parts import capture_collision, plan  # noqa: E402
from regions.ferry.terminal_constructor import construct  # noqa: E402

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
               axis_up='Z', mesh_smooth_type='EDGE', use_custom_props=False)


def read(path):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Terminal source data must be regular')
    return json.loads(path.read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    source = read(args.source)
    if source.get('asset') != args.asset: raise ValueError('Foreign selected terminal source')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    context, mesh, metadata = construct(source, source['primitives'])
    raw = {key: list(getattr(mesh, key)) for key in ('verts', 'faces', 'mats', 'parts', 'origins', 'seats')}
    report = context.F.check(mesh)
    if report['open_edges']: raise ValueError('Original terminal closure gate failed: ' + args.asset)
    anchor = source['anchor']
    mesh.verts[:] = [(x - anchor[0], y - anchor[1], z - anchor[2]) for x, y, z in mesh.verts]
    materials = context.F.make_materials()
    obj, slots = context.F.to_object(mesh, materials)
    hulls = context.collision_objects(args.asset, anchor, context.BROW_COL) if args.asset.endswith('_Brow') else []
    collisions = [capture_collision(hull) for hull in hulls]
    value = plan(obj, args.output, options=OPTIONS, collisions=collisions)
    atomic_json(args.queries, dict(schema=1, asset=args.asset, owner=source['owner'], raw=raw,
        metadata=metadata, fixed_hulls=context.COL, moving_hulls=context.BROW_COL,
        report=report, triangles=value['source_triangles'], materials=slots, anchor=anchor, authored_hulls=collisions))
    print('FERRY TERMINAL LOGICAL PLAN COMPLETE', args.asset, len(value['pieces']), flush=True)


if __name__ == '__main__': main()
