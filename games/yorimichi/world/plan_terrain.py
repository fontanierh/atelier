"""Plan one original island logical mesh; export tasks consume only bounded children."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yori  # noqa: E402,F401
from atelier.export_manifest import real_directory  # noqa: E402
from terrain_sources import ASSETS  # noqa: E402

# Exact original island FBX policy. Every child keeps the original world-space frame.
OPTIONS = dict(apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
               axis_forward='-Y', axis_up='Z', mesh_smooth_type='FACE',
               path_mode='COPY', embed_textures=False)

CELL_METRES = {'FarHills': 512.}


def plan_selected(obj, output):
    """Use wider backdrop cells without weakening the strict per-export triangle budget."""
    from region_mesh_parts import plan
    if obj.name not in ASSETS:
        raise ValueError('Unowned island logical constructor')
    return plan(obj, output, partition='spatial' if obj.name in ('Terrain', 'FarHills') else 'whole', options=OPTIONS, cell_metres=CELL_METRES.get(obj.name, 128.))


def construct(key, source, *, heightmap=None, final=None):
    import bpy
    import build_terrain
    if (key not in ASSETS or source.get('schema') != 1 or source.get('asset') != key
            or source.get('enabled') is not True):
        raise ValueError('Missing or foreign selected island constructor data')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    result = getattr(build_terrain, key.lower())(source['world'], heightmap, final,
                                               city=source.get('city', True))
    if result is None or not len(result.data.polygons):
        raise ValueError('Enabled island constructor produced no geometry')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', choices=ASSETS, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--heightmap', type=Path)
    parser.add_argument('--final', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    for path in (args.source, args.heightmap, args.final):
        if path is not None:
            real_directory(path.parent)
            if path.is_symlink() or not path.is_file():
                raise ValueError('Island planner requires unlinked regular source data')
    source = json.loads(args.source.read_text())
    import numpy as np
    from terrain_product import load
    heightmap = np.load(args.heightmap, allow_pickle=False) if args.heightmap else None
    final = load(args.final, owner='FarHills', stage='final', city=source['city']) if args.final else None
    if (args.asset in ('Terrain', 'Lane')) != (heightmap is not None):
        raise ValueError('Only the terrain lattice and lane consume the heightmap')
    if (args.asset == 'FarHills') != (final is not None):
        raise ValueError('Only FarHills consumes its canonical final query surface')
    obj = construct(args.asset, source, heightmap=heightmap, final=final)
    value = plan_selected(obj, args.output)
    print('ISLAND LOGICAL PLAN COMPLETE ' + args.asset + ' ' + str(len(value['pieces'])), flush=True)


if __name__ == '__main__':
    main()
