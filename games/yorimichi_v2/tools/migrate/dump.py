"""Dump the running ORIGINAL game's static scene inside some bounds, for the one-time V2 migration.

    uv run python games/yorimichi_v2/tools/migrate/dump.py --bounds-cm -25600 0 0 25600 \
        --out build/yorimichi_v2/migrate/slice.json [--session ID]

Start the donor game first (from the donor workspace) and wait until its world has finished spawning. The dump
goes through that game's live bridge: `--session ID` selects it (`atelier live sessions` lists them); without it,
the live CLI refuses to guess between several running games.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--bounds-cm', type=float, nargs=4, required=True, metavar=('XMIN', 'YMIN', 'XMAX', 'YMAX'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--source-revision', help='the donor revision, recorded in the dump')
    parser.add_argument('--session', help='live session ID (atelier live sessions)')
    args = parser.parse_args(argv)
    out = args.out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    params = {'bounds_cm': args.bounds_cm, 'out': str(out), 'source_revision': args.source_revision}
    code = f'PARAMS = {json.dumps(params)!r}\nimport json as _j\nPARAMS = _j.loads(PARAMS)\n' + \
        (HERE / 'dump_scene.py').read_text()
    command = ['uv', 'run', 'atelier', 'live'] + (['--session', args.session] if args.session else []) + ['py', '-']
    result = subprocess.run(command, cwd=REPO, input=code, text=True)
    if result.returncode or not out.is_file():
        print('dump failed: is exactly one donor game running with its world loaded?', file=sys.stderr)
        return 1
    data = json.loads(out.read_text())
    print(f'{out}: {len(data["meshes"])} mesh components')
    return 0


if __name__ == '__main__':
    sys.exit(main())
