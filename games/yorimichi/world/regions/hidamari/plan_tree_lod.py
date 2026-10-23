"""Construct one tree LOD while retaining the base's complete per-piece face membership."""
import argparse
import importlib
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from atelier import mesh_ir  # noqa: E402
from atelier.export_manifest import name, real_directory, sha  # noqa: E402

from hidamari.tree_policy import TREES  # noqa: E402


def groups(base, parent, level, polygons):
    """Carry original polygon membership through outline simplification without spatial re-binning."""
    if (base.get('parent') != parent or base.get('source_polygons') != polygons
            or base.get('source_collision_hulls', 0) < 1 or level not in (1, 2)):
        raise ValueError('Tree LOD differs from its current base source')
    result = []
    for row in base['pieces']:
        key = name(row['name'])
        if key != parent and not key.startswith(parent + '_cell_'):
            raise ValueError('Invalid base tree piece owner')
        if len(row.get('source_faces', ())) != row['polygons']:
            raise ValueError('Tree LOD requires exact original polygon membership')
        result.append((parent + '_LOD' + str(level) + key[len(parent):], row['source_faces']))
    return result


def verify_base(obj, collisions, base, root, options):
    """Compare every completed base payload to its actual current constructor, including corner bytes."""
    from mesh_pieces import capture, subset
    source = capture(obj.data)
    if len(collisions) != base['source_collision_hulls']:
        raise ValueError('Tree base collision differs from its current constructor')
    for index, row in enumerate(base['pieces']):
        if 'source_faces' not in row:
            raise ValueError('Tree base lacks exact source face membership')
        payload = mesh_ir.encode(subset(source, row['source_faces']), key=row['name'],
            slots=[material.name for material in source['slots']], matrix=[list(row) for row in obj.matrix_world],
            options=options, collisions=collisions if index == 0 else ())
        if (Path(root) / row['payload']).read_bytes() != payload:
            raise ValueError('Tree LOD base differs from actual constructor geometry')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=TREES, required=True)
    parser.add_argument('--level', type=int, choices=(1, 2), required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    from hidamari import source_context
    from region_mesh_parts import plan, validate, capture_colliders
    from region_plan_files import files
    from hidamari.tree_outline import simplified
    from village import mesh as kernel
    import bpy
    root = real_directory(args.base)
    before = {key: sha(root / key) for key in files(root)}
    base = validate(root)
    constructor = importlib.import_module('hidamari.logical.' + args.asset).construct
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source_context.apply(source_context.read(args.context, args.asset), kernel)
    source = constructor({})
    if (source.name != args.asset or len(source.faces) != base['source_polygons']
            or sum(len(face)-2 for face in source.faces) != base['source_triangles']):
        raise ValueError('Tree LOD constructor differs from its completed base geometry')
    material = bpy.data.materials.new('HidamariPalette')
    options = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y', axis_up='Z',
                   mesh_smooth_type='FACE', use_custom_props=False)
    base_obj = source.object(material)
    verify_base(base_obj, capture_colliders(source.colliders), base, root, options)
    bpy.data.objects.remove(base_obj, do_unlink=True)
    reduced, leaves = simplified(source, args.level)
    obj = reduced.object(material)
    value = plan(obj, args.output, face_groups=groups(base, args.asset, args.level, len(reduced.faces)),
                 options=options)
    if {key: sha(root / key) for key in files(root)} != before:
        raise ValueError('Tree base input changed during LOD construction')
    print('ATOMIC TREE LOD GEOMETRY COMPLETE', args.asset, args.level, leaves,
          len(value['pieces']), value['source_triangles'], flush=True)


if __name__ == '__main__': main()
