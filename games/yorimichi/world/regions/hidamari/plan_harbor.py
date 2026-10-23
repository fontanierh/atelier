"""Cut the authoritative raw Harbor data before independently exporting final pieces."""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory, sha  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cut-data', type=Path, required=True)
    parser.add_argument('--query-output', type=Path, required=True)
    parser.add_argument('--proof-output', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    from ferry import site_inputs
    import source_geometry
    import region_query
    from region_mesh_parts import plan
    from mesh_pieces import create_mesh
    from region_plan_files import files
    from hidamari.ferry_cut import cut_object
    from hidamari.cut_ingress import prepare
    import bpy
    from mathutils import Matrix
    output, raw = real_directory(args.output), real_directory(args.source)
    if output.is_relative_to(raw) or raw.is_relative_to(output):
        raise ValueError('Final Harbor output must be independent of its raw source')
    if len({args.query_output.absolute(), args.proof_output.absolute(), args.cut_data.absolute()}) != 3:
        raise ValueError('Harbor query, proof and cut data must have distinct ownership')
    for destination in (args.query_output, args.proof_output):
        real_directory(destination.parent)
        if (destination.absolute().is_relative_to(raw) or destination.absolute().is_relative_to(output)
                or (os.path.lexists(destination) and (destination.is_symlink() or not destination.is_file()))):
            raise ValueError('Harbor auxiliary outputs require independent regular destinations')
    real_directory(args.cut_data.parent)
    if args.cut_data.is_symlink() or not args.cut_data.is_file():
        raise ValueError('Final Harbor requires regular verified cut parameters')
    before = sha(args.cut_data)
    cuts = site_inputs.read_projection(json.loads(args.cut_data.read_text()))
    inputs = {relative: sha(args.source / relative) for relative in files(args.source)}
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = source_geometry.read(args.source, owner='HD_Harbor')
    if source['collisions']:
        raise ValueError('The authored Harbor cut expects no whole UCX override')
    source['slots'] = [bpy.data.materials.new(label) for label in source['slots']]
    obj = bpy.data.objects.new('HD_Harbor', create_mesh('HD_Harbor', source))
    bpy.context.collection.objects.link(obj)
    obj.matrix_world = Matrix(source['matrix'])
    prepare(obj)
    result = cut_object(obj, cuts)
    if result['failures'] or not all(row['cap_normals_pass'] for row in result['cuts']):
        raise ValueError('Final Harbor source cut failed: ' + json.dumps(result))
    region_query.save(args.query_output, [region_query.capture(obj)], owner='HD_Harbor', stage='final')
    value = plan(obj, args.output, options=dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
        axis_forward='-Y', axis_up='Z', mesh_smooth_type='FACE', use_custom_props=False))
    if value['source_triangles'] != result['triangles']['after']:
        raise ValueError('Final Harbor plan differs from the audited cut')
    if (sha(args.cut_data) != before
            or {relative: sha(args.source / relative) for relative in files(args.source)} != inputs):
        raise ValueError('Harbor raw source or ferry proof changed during construction')
    atomic_json(args.proof_output, dict(schema=1, complete=True, **result,
        raw_source=inputs, query_sha256=sha(args.query_output), plan_sha256=sha(args.output / 'plan.json'),
        cut_data_sha256=before))
    print('FINAL HARBOR GEOMETRY COMPLETE', value['source_triangles'], flush=True)


if __name__ == '__main__': main()
