"""Publish separate CraterPark assets and unchanged logical course metadata."""
import argparse
import json
from pathlib import Path
import sys
sys.path[:0] = [str(Path(__file__).resolve().parents[3]), str(Path(__file__).resolve().parents[2])]
import yori  # noqa: E402,F401
import numpy as np  # noqa: E402
from craterpark import placement  # noqa: E402
from craterpark.v2 import export  # noqa: E402
from megapark import atomic_common  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    projected = args.out / 'craterpark-inputs'
    inventory = json.loads((projected / 'inputs.json').read_text())
    if inventory.get('schema') != 1 or inventory.get('complete') is not True:
        raise ValueError('Incomplete canonical CraterPark source inventory')
    groups, _ = atomic_common.assemble_files(args.out, 'craterpark', [a['name'] for a in inventory['assets']])
    with np.load(projected / 'metadata.npz', allow_pickle=False) as geometry:
        index = json.loads(str(geometry['index']))
        provenance = export.validate_geometry(index)
        build = dict(scene_sha256=export.sha(placement.SOURCE / 'scene.json'), render=[], collision=[])
        if provenance:
            build['v4'] = provenance
        for row in inventory['assets']:
            if row['kind'] != 'seed':
                build[row['kind']].extend(groups[row['name']])
        export.write_metadata(args.out / 'craterpark', placement.SOURCE, geometry, placement, build, index, provenance)
    print('CRATERPARK ASSEMBLY COMPLETE', len(build['render']), len(build['collision']), flush=True)


if __name__ == '__main__':
    main()
