"""One railway mesh using the immutable original finite material/export functions."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402,F401
import bpy
import numpy as np
from mathutils import Matrix
from atelier import export_manifest, mesh_ir
from atelier.blender.fbx import validate_atomic_selection
from atelier.model_files import regular_files
from mesh_pieces import create_mesh


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--materials', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--format', choices=['.glb'], required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    originals = {}
    for path in (args.input, args.materials):
        export_manifest.real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Linked railway export input')
        originals[path] = path.read_bytes()
    meta, piece = mesh_ir.decode(originals[args.input]); key = meta['asset']
    materials = json.loads(originals[args.materials])
    if (materials.get('schema') != 1 or materials.get('asset') != key or set(materials['palette']) != set(meta['slots'])
            or meta['collisions']): raise ValueError('Foreign railway material/collision ownership')
    root = export_manifest.real_directory(args.output, create=True)
    if regular_files(root) - {key + '.glb', 'export.json'}: raise ValueError('Foreign railway export member')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    namespace = dict(bpy=bpy, T=SimpleNamespace(MATERIALS=materials['palette']))
    exec(compile(materials['material_factory'] + '\n' + materials['export_glb'], '<original-railway-export>', 'exec'), namespace)
    palette = namespace['materials']()
    piece['slots'] = [palette[slot] for slot in meta['slots']]
    mesh = create_mesh(key, piece)
    obj = bpy.data.objects.new(key, mesh); bpy.context.collection.objects.link(obj)
    obj.matrix_world = Matrix(meta['matrix'])
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True); bpy.context.view_layer.objects.active = obj
    validate_atomic_selection()
    with tempfile.TemporaryDirectory(prefix='.railway-', dir=root) as staging:
        primary = Path(staging) / (key + '.glb')
        namespace['export_glb'](primary, obj)
        if any(path.read_bytes() != data for path, data in originals.items()): raise ValueError('Railway inputs changed during export')
        primary.replace(root / primary.name)
    positions = piece['positions'] @ np.asarray(meta['matrix'])[:3, :3].T + np.asarray(meta['matrix'])[:3, 3]
    export_manifest.publish_receipt(root, key=key, primary=key + '.glb', triangles=piece['triangles'],
        bounds=[positions.min(0).tolist(), positions.max(0).tolist()],
        metadata=dict(slots=meta['slots'], polygons=len(piece['faces']), collision_hulls=0,
            geometry_sha256=hashlib.sha256(originals[args.input]).hexdigest(),
            material_sha256=hashlib.sha256(originals[args.materials]).hexdigest()))
    print('ATOMIC RAILWAY EXPORT COMPLETE', key, flush=True)


if __name__ == '__main__': main()
