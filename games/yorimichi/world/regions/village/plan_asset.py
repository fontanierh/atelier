"""Construct/capture exactly one Village logical model, without exporting geometry."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402
from region_mesh_parts import capture_colliders, plan  # noqa: E402
from village.atomic_sources import ASSETS, HEIGHTS  # noqa: E402
from village.logical import construct  # noqa: E402

OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL', axis_forward='-Y',
               axis_up='Z', mesh_smooth_type='FACE', use_custom_props=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=ASSETS, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--heightmap', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--')+1:])
    for path in (args.source, args.heightmap):
        if path is not None:
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file(): raise ValueError('Village planner requires regular source data')
    if (args.asset in HEIGHTS) != (args.heightmap is not None):
        raise ValueError('Selected Village heightmap ownership differs')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    source = json.loads(args.source.read_text())
    heights = np.load(args.heightmap, allow_pickle=False) if args.heightmap else None
    m = construct(args.asset, source, heights)
    material = bpy.data.materials.new('VillagePalette')
    obj = m.object(material)
    value = plan(obj, args.output, partition='spatial' if args.asset == 'Village_Planting' else 'whole', collisions=capture_colliders(m.colliders), options=OPTIONS)
    print('VILLAGE LOGICAL PLAN COMPLETE ' + args.asset + ' ' + str(len(value['pieces'])), flush=True)


if __name__ == '__main__': main()
