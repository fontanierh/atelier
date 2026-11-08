"""One original fixed-terminal collision primary, from complete explicit authored hull data."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
import solid_mesh  # noqa: E402,F401
from atelier.blender import fbx  # noqa: E402,F401
from atelier.export_manifest import real_directory, publish_receipt  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from regions.ferry.terminal_constructor import kit  # noqa: E402
from region_mesh_parts import capture_collision  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--primitives', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    originals = {}
    for path in (args.input, args.primitives):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file(): raise ValueError('Terminal collision requires regular source data')
        originals[path] = path.read_bytes()
    source, primitives = (json.loads(originals[path]) for path in (args.input, args.primitives))
    key = source.get('asset')
    if source.get('schema') != 1 or key not in ('FT_HD_Collision', 'FT_BC_Collision') or not source.get('hulls'):
        raise ValueError('Incomplete selected terminal collision')
    root = real_directory(args.output, create=True)
    if regular_files(root) - {key + '.fbx', 'export.json'}: raise ValueError('Foreign terminal collision output')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    context, complete = kit(primitives, source)
    context.COL.extend(source['hulls'])
    original_collision_objects = context.collision_objects
    authored_hulls = []
    def observed_collision_objects(name, anchor, proxies):
        objects = original_collision_objects(name, anchor, proxies)
        authored_hulls.extend(capture_collision(obj) for obj in objects)
        return objects
    context._globals['collision_objects'] = observed_collision_objects
    with tempfile.TemporaryDirectory(prefix='.collision-', dir=root) as temporary:
        stage = Path(temporary); (stage / 'assets').mkdir()
        context._globals['OUT'] = stage
        count = context.export_collision(key.removesuffix('_Collision'), source['anchor']); complete()
        if count != len(source['hulls']) or any(path.read_bytes() != payload for path, payload in originals.items()):
            raise ValueError('Terminal collision source changed or lost authored hulls')
        (stage / 'assets' / (key + '.fbx')).replace(root / (key + '.fbx'))
    publish_receipt(root, key=key, primary=key + '.fbx', triangles=12,
        bounds=np.asarray([[-.05, -.05, -2.05], [.05, .05, -1.95]], dtype='<f4').tolist(),
        metadata=dict(collision_hulls=count, slots=[], polygons=6, uv_channels=[], authored_hulls=authored_hulls))
    print('FERRY TERMINAL COLLISION EXPORT COMPLETE', key, count, flush=True)


if __name__ == '__main__': main()
