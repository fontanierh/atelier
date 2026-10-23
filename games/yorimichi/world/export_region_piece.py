"""Export exactly one complete, bounded planned mesh in an ordinary cached Blender task."""
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yori  # noqa: E402,F401

from atelier import export_tasks, mesh_ir  # noqa: E402
from atelier.blender.fbx import export_atomic_fbx  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from mesh_pieces import create_mesh  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--format', choices=['.fbx', '.glb'], default='.fbx')
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    export_tasks.real_directory(args.input.parent)
    if args.input.is_symlink() or not args.input.is_file():
        raise ValueError('Atomic exporter requires a regular planned input')
    original = args.input.read_bytes()
    meta, piece = mesh_ir.decode(original)
    key = meta['asset']
    root = export_tasks.real_directory(args.output, create=True)
    if regular_files(root) - {key + args.format, 'export.json'}:
        raise ValueError('Atomic export output has foreign members')
    import bpy
    from mathutils import Matrix
    bpy.ops.wm.read_factory_settings(use_empty=True)
    piece['slots'] = [bpy.data.materials.new(label) for label in piece['slots']]
    mesh = create_mesh(key, piece)
    obj = bpy.data.objects.new(key, mesh)
    bpy.context.collection.objects.link(obj)
    obj.matrix_world = Matrix(meta['matrix'])
    selected = [obj]
    for index, collision in enumerate(meta['collisions']):
        label = f'UCX_{key}_{index:02d}'
        data = bpy.data.meshes.new(label)
        data.from_pydata(collision['vertices'], [], collision['faces']); data.update()
        hull = bpy.data.objects.new(label, data)
        bpy.context.collection.objects.link(hull)
        hull.matrix_world = Matrix(collision['matrix'])
        selected.append(hull)
    bpy.ops.object.select_all(action='DESELECT')
    for item in selected:
        item.select_set(True)
    bpy.context.view_layer.objects.active = obj
    with tempfile.TemporaryDirectory(prefix='.export-', dir=root) as staging:
        primary = Path(staging) / (key + args.format)
        if args.format == '.fbx':
            options = dict(meta['options'])
            options.update(filepath=str(primary), use_selection=True, object_types={'MESH'}, bake_anim=False)
            export_atomic_fbx(**options)
        else:
            from atelier.blender.gltf import export_atomic_glb
            export_atomic_glb(primary)
        if args.input.read_bytes() != original:
            raise ValueError('Planned input changed during atomic export')
        primary.replace(root / primary.name)
    import numpy as np
    positions = piece['positions'] @ np.asarray(meta['matrix'])[:3, :3].T + np.asarray(meta['matrix'])[:3, 3]
    export_tasks.publish_receipt(root, key=key, primary=key + args.format,
                                triangles=piece['triangles'],
                                bounds=[positions.min(0).tolist(), positions.max(0).tolist()],
                                metadata=dict(slots=meta['slots'], polygons=len(piece['faces']), collision_hulls=len(meta['collisions']),
                                              uv_channels=[n for n, _ in piece['uvs']]))
    print('ATOMIC REGION EXPORT COMPLETE ' + key, flush=True)


if __name__ == '__main__':
    main()
