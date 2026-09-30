#!/usr/bin/env python3
"""Prepare local Skate animation banks, graphs and physics data for the recovered runtime.

--game is an extracted disc containing default.xex and data/.
--engine is a checkout of SK8-ENGINE/skate-3-rust-engine containing tools/.
Candidate files and a checksum manifest go to build/ for review; tracked runtime data is never overwritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / 'games/yorimichi/assets/skate/runtime.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/yorimichi/skate-runtime/reconverted')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Candidate output already exists; choose a new --output directory.')
    if not (args.game / 'default.xex').is_file() or not (args.engine / 'tools/asset_pipeline').is_dir():
        parser.error('Expected an extracted disc and the upstream tools checkout.')
    sys.path.insert(0, str(args.engine.resolve()))
    from tools.asset_pipeline.install import extract
    from tools.asset_pipeline.vlt import convert
    from tools.asset_pipeline.physics_skeleton import convert as skeleton
    from tools.owned_game.refpack import decompress

    staging = ROOT / 'build/yorimichi/skate-runtime'
    staging.mkdir(parents=True, exist_ok=True)
    provenance = json.loads(MANIFEST.read_text())
    provenance['converter_commit'] = subprocess.check_output(
        ['git', '-C', str(args.engine), 'rev-parse', 'HEAD'], text=True).strip()
    required_stock = {name.removeprefix('private/stock/').lower() for name in provenance['sha256']
                      if name.startswith('private/stock/data/')}
    with tempfile.TemporaryDirectory(prefix='import-', dir=staging) as temporary:
        work = Path(temporary)
        private = work / 'assets/private'
        stock = private / 'stock'
        extract(args.game / 'data/big/miscload.big', stock,
                lambda e: e.path.lower() in required_stock)
        extract(args.game / 'data/big/miscboot.big', stock,
                lambda e: e.path.lower() == 'data/config/input.cfg')
        for name in ('OnBoard.abin', 'OffBoard.abin'):
            source = args.game / 'data/anim' / name
            if source.is_file():
                (stock / 'data/anim').mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, stock / 'data/anim' / name)
        database = work / 'database'
        stems = ('skaterschema', 'skatercollections')
        extract(args.game / 'data/big/db.big', database,
                lambda e: Path(e.path).name.lower() in {s + ext for s in stems for ext in ('.vlt', '.bin')})
        database /= 'data/db'
        for path in database.iterdir():
            raw = path.read_bytes()
            if raw[:2] in (b'\x10\xfb', b'\x90\xfb'):
                path.write_bytes(decompress(raw))
        names = (args.engine / 'tools/asset_pipeline/names.txt').read_text().splitlines()
        (stock / 'skater-collections.json').write_text(json.dumps(convert(database / stems[0], database / stems[1], names)))
        (stock / 'physics-skeletons.json').write_text(json.dumps(skeleton(stock / 'data/anim/OnBoard.abin')))
        # GameAssets validates a scene path. Headless Session never renders it: Unreal supplies the avatar.
        scene = json.dumps({'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{}]}, separators=(',', ':')).encode()
        scene += b' ' * (-len(scene) % 4)
        (private / 'headless.glb').write_bytes(struct.pack('<III', 0x46546c67, 2, 20 + len(scene)) +
                                             struct.pack('<II', len(scene), 0x4e4f534a) + scene)
        manifest = {'version': 1, 'character_scene': 'private/headless.glb', 'initial_animation': 'R_IDLE_HCOM_000',
                    'action_graph': 'private/stock/data/state/ActionGraph_OnBoard.stategraph',
                    'motion_graph': 'private/stock/data/state/MotionGraph_OnBoard.stategraph'}
        (private / 'game.json').write_text(json.dumps(manifest))
        provenance['sha256'] = {name: hashlib.sha256((work / 'assets' / name).read_bytes()).hexdigest()
                                for name in provenance['sha256']}
        args.output.mkdir(parents=True)
        shutil.move(work / 'assets', args.output / 'assets')
        (args.output / 'runtime.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(f'Converted {len(provenance["sha256"])} candidate files in {args.output}. Review before replacing tracked data.')


if __name__ == '__main__':
    main()
