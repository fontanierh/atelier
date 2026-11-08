"""CPU diagnostic compiler: python -m craterpark.v2.v4_editor --help."""
import argparse
import json
from pathlib import Path

from .editor import diagnostic, frontend


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--park', type=Path, required=True)
    parser.add_argument('--terrain', type=Path, help='Editor data directory (defaults to park sibling data/)')
    parser.add_argument('--out', type=Path, required=True, help='A new diagnostic output directory')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    print('Snapshotting editor document and terrain', flush=True)
    frozen = frontend.snapshot(args.park, args.out / 'snapshot', terrain_dir=args.terrain)
    print('Compiling pinned Node geometry (CPU only, 120-second deadline)', flush=True)
    scene = frontend.compile_snapshot(frozen, args.out / 'node')
    print(f'Exporting {len(scene.pieces)} pieces to GLB and checking every indexed vertex', flush=True)
    glb = args.out / 'editor.glb'
    diagnostic.write_glb(scene, glb)
    report = diagnostic.compare(scene, glb)
    (args.out / 'parity.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['by_type'], indent=2), flush=True)
    print('UNACCEPTED EDITOR DIAGNOSTIC complete; no game or ride certification', flush=True)


if __name__ == '__main__':
    main()
