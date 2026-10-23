"""Construct exactly one committed MegaPark model or authoritative collision section."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402
import numpy as np  # noqa: E402
from megapark import build, atomic_common  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset', required=True)
    parser.add_argument('--letters', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    source = json.loads((build.SOURCE / 'map.json').read_text())
    with np.load(args.letters, allow_pickle=False) as data:
        letters = tuple(data[key] for key in ('vertices', 'faces', 'normals', 'uv'))
    report = dict(materials={}, foliage_only=[])
    captured = []
    def collect(*values):
        obj, entry = build.mesh_object(*values)
        captured.append((obj, entry))
        return entry
    if args.asset.startswith('SM_MP_') and args.asset not in ('SM_MP_Seam', 'SM_MP_ImportSeed'):
        model = next(m for m in source['models'] if 'SM_MP_' + m['asset_id'][2:] == args.asset)
        build.model_geometry(source, model, letters, report, entry_mesh=collect)
    elif args.asset.startswith('UC_MP_') and args.asset != 'UC_MP_Seam':
        section = next(m for m in source['collision'] if 'UC_MP_' + m['id'] == args.asset)
        build.collision_geometry(section, letters, entry_mesh=collect)
    elif args.asset in ('SM_MP_Seam', 'UC_MP_Seam'):
        # Shared seam computation is source geometry, not a dependency on another mesh export.
        def selected(*values):
            if values[0] == args.asset:
                return collect(*values)
            vertices, faces = values[1:3]
            return dict(name=values[0], triangles=len(faces), native_origin=[0, 0, 0])
        build.export_seam(source, report, entry_mesh=selected,
                          selection='render' if args.asset == 'SM_MP_Seam' else None)
    elif args.asset == 'SM_MP_ImportSeed':
        collect(args.asset, np.asarray([[0,0,0],[1,0,0],[0,0,1]], 'f4'),
                np.asarray([[0,2,1]], 'u4'), ['M_Collision'], [0],
                {'UVMap': np.asarray([[0,0],[1,0],[0,1]], 'f4')})
    else:
        raise ValueError('Unknown selected MegaPark logical asset')
    if len(captured) != 1:
        raise ValueError('Selected MegaPark asset did not produce exactly one logical mesh')
    obj, entry = captured[0]
    atomic_common.capture(obj, entry, args.output, args.metadata, materials=report['materials'])
    print('MEGAPARK LOGICAL COMPLETE', args.asset, entry['triangles'], flush=True)


if __name__ == '__main__':
    main()
