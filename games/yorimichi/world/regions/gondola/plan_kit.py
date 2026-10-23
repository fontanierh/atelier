"""Construct exactly one selected Gondola command stream; publish bounded geometry."""
import argparse
import json
from pathlib import Path
import sys

WORLD = Path(__file__).resolve().parents[2]
KIT = WORLD.parent / 'assets/vehicles/gondola'
sys.path[:0] = [str(KIT), str(WORLD)]
import yori  # noqa: E402,F401
import bpy  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, name  # noqa: E402
from region_mesh_parts import plan  # noqa: E402
from commands import replay  # noqa: E402
import solid  # noqa: E402

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
               axis_up='Z', mesh_smooth_type='EDGE', use_custom_props=False)
FIELDS = ('verts', 'faces', 'mats', 'parts', 'origins', 'fgrain')


def source(path, asset):
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file(): raise ValueError('Gondola source must be a regular file')
    value = json.loads(path.read_text())
    if value.get('schema') != 1 or value.get('asset') != asset:
        raise ValueError('Foreign selected Gondola source')
    return value


def construct(value):
    if not name(value['asset']).startswith('GD_'): raise ValueError('Unknown Gondola selected mesh')
    mesh = replay(value, solid.Mesh)
    report = solid.closed(mesh)
    if any(report[key] for key in ('open_edges', 'misoriented_edges', 'degenerate_faces')):
        raise ValueError('Gondola original closure gate failed: ' + repr(report))
    obj, slots = solid.to_object(mesh, solid.make_materials({}))
    query = dict(schema=1, asset=mesh.name, mesh={field: getattr(mesh, field) for field in FIELDS},
                 report=report, materials=slots)
    return obj, query


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--queries', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    selected = source(args.source, args.asset)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj, query = construct(selected)
    value = plan(obj, args.output, options=OPTIONS)
    query['triangles'] = value['source_triangles']
    atomic_json(args.queries, query)
    print('GONDOLA LOGICAL PLAN COMPLETE', args.asset, len(value['pieces']), flush=True)


if __name__ == '__main__': main()
