#!/usr/bin/env python3
"""Prepare local Skate animation banks, graphs and physics data for the recovered runtime.

--game is an extracted disc containing default.xex and data/.
--engine is a checkout of SK8-ENGINE/skate-3-rust-engine containing tools/.
Converted files stay in ignored Content/Data and build folders.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--engine', type=Path, required=True)
    args = parser.parse_args()
    if not (args.game / 'default.xex').is_file() or not (args.engine / 'tools/asset_pipeline').is_dir():
        parser.error('Expected an extracted disc and the upstream tools checkout.')
    sys.path.insert(0, str(args.engine.resolve()))
    from tools.asset_pipeline.install import extract
    from tools.asset_pipeline.vlt import convert
    from tools.asset_pipeline.physics_skeleton import convert as skeleton
    from tools.owned_game.refpack import decompress

    staging = ROOT / 'build/yorimichi/skate-runtime'
    staging.mkdir(parents=True, exist_ok=True)
    destination = ROOT / 'games/yorimichi/unreal/Content/Data/SkateRuntime/assets'
    with tempfile.TemporaryDirectory(prefix='import-', dir=staging) as temporary:
        work = Path(temporary)
        private = work / 'assets/private'
        stock = private / 'stock'
        extract(args.game / 'data/big/miscload.big', stock,
                lambda e: e.path.lower().startswith(('data/anim/', 'data/state/', 'data/joystick/', 'data/script/camera/', 'data/camera/')))
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
        hashes = {str(p.relative_to(private)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(private.rglob('*')) if p.is_file()}
        (private / 'provenance.json').write_text(json.dumps({'version': 1, 'sha256': hashes}, indent=2))
        if destination.exists():
            raise SystemExit('Runtime assets already exist; move that generated assets folder aside before reimporting.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(work / 'assets', destination)
    print(f'Imported {len(hashes)} runtime files. Run build_skate_runtime.py to install the worker.')


if __name__ == '__main__':
    main()
