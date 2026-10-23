"""Construct just the selected validated CraterPark logical input, without siblings."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[3]), str(Path(__file__).resolve().parents[2])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from craterpark.v2 import dsl, export  # noqa: E402
from megapark import atomic_common  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv if argv is not None else sys.argv[sys.argv.index('--') + 1:])
    with np.load(args.input, allow_pickle=False) as data:
        spec = json.loads(str(data['spec'])); name = spec['name']
        if name != args.input.stem:
            raise ValueError('Foreign selected CraterPark source')
        if spec['kind'] == 'render':
            mesh = dsl.Mesh.from_arrays(data, 'm_')
            keys = np.unique(mesh.material)
            obj, entry = export.mesh_object(None, name, mesh.V, mesh.F,
                [dsl.MATERIALS[int(m)] for m in keys], np.searchsorted(keys, mesh.material), mesh.UV, mesh.N, mesh.AO)
            entry.update(source_id=name[6:], role=spec['role'], skipped=0, covered=0,
                         occlusion_mean=round(float(mesh.AO.mean()), 4) if len(mesh.AO) else 1.)
        elif spec['kind'] == 'collision':
            triangles = data['triangles']; vertices = triangles.reshape(-1, 3)
            obj, entry = export.mesh_object(None, name, vertices, np.arange(len(vertices)).reshape(-1, 3),
                                            ['M_Collision'], np.zeros(len(triangles), 'i4'), native_origin=data['native_origin'])
            entry.update(source_triangles=len(triangles), source_parent=spec['logical_parent'], role=spec['role'], one_sided=False)
        elif spec['kind'] == 'seed' and name == 'SM_CP_ImportSeed':
            obj, entry = export.mesh_object(None, name, np.asarray([[0,0,0],[1,0,0],[0,0,1]], 'f8'),
                np.asarray([[0,2,1]]), ['M_Collision'], [0], np.asarray([[0,0],[1,0],[0,1]], 'f8'))
        else:
            raise ValueError('Unknown selected CraterPark geometry role')
    atomic_common.capture(obj, entry, args.output, args.metadata, colours=True)
    print('CRATERPARK LOGICAL COMPLETE', name, entry['triangles'], flush=True)


if __name__ == '__main__':
    main()
