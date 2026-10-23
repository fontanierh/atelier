"""Export the original one-primary ferry collision owner from explicit authored proxies."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.blender import fbx  # noqa: E402,F401 (declared transitive original exporter code)
from atelier.export_manifest import real_directory, publish_receipt  # noqa: E402
from atelier.model_files import regular_files  # noqa: E402
from regions.ferry.ship_sources import BUILD  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    originals = {}
    for path in (args.source, args.input):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file():
            raise ValueError('Ferry collision requires regular original source/proxy inputs')
        originals[path] = path.read_bytes()
    source, data = (json.loads(originals[path]) for path in (args.source, args.input))
    if any(row.get('schema') != 1 or row.get('asset') != 'FY_Collision' for row in (source, data)):
        raise ValueError('Foreign ferry collision input')
    root = real_directory(args.output, create=True)
    if regular_files(root) - {'FY_Collision.fbx', 'export.json'}:
        raise ValueError('Foreign ferry collision export members')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    namespace = dict(__file__=str(BUILD), __name__='ferry_original_collision')
    exec(compile(source['program'], str(BUILD), 'exec'), namespace)
    with tempfile.TemporaryDirectory(prefix='.collision-', dir=root) as temporary:
        stage = Path(temporary); (stage / 'assets').mkdir()
        namespace['OUT'] = stage
        count = namespace['export_collision'](data['proxies'])
        if count != len(data['proxies']) or count <= 0:
            raise ValueError('Incomplete original ferry collision hulls')
        if any(path.read_bytes() != original for path, original in originals.items()):
            raise ValueError('Ferry collision inputs changed during export')
        (stage / 'assets/FY_Collision.fbx').replace(root / 'FY_Collision.fbx')
    publish_receipt(root, key='FY_Collision', primary='FY_Collision.fbx', triangles=12,
        bounds=np.asarray([[-.05, -.05, -2.05], [.05, .05, -1.95]], dtype='<f4').tolist(),
        metadata=dict(collision_hulls=count, slots=[], polygons=6, uv_channels=[]))
    print('FERRY COLLISION ORIGINAL EXPORT COMPLETE', count, flush=True)


if __name__ == '__main__': main()
