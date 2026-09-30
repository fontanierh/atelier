#!/usr/bin/env python3
"""Verify the tracked skating data and build its recovered runtime executable."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / 'games/yorimichi/assets/skate'
ASSETS = ROOT / 'games/yorimichi/unreal/Content/Data/SkateRuntime/assets'
SOURCE = ROOT / 'platform/engine/Plugins/Activities/Skate/ThirdParty/skate-runtime/atelier-host'


def verify_assets(assets=ASSETS):
    manifest = json.loads((BUNDLE / 'runtime.json').read_text())
    assets = Path(assets)
    for name, digest in manifest['sha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('Invalid runtime asset path')
        source = assets / relative
        if not source.is_file():
            raise ValueError(f'Missing tracked Skate runtime asset: {name}')
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Skate runtime asset checksum mismatch: {name}')
    print(f'Verified {len(manifest["sha256"])} tracked skating assets.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', default='1.97.1', help='rustup toolchain (default: 1.97.1)')
    args = parser.parse_args()
    verify_assets()
    target = Path(os.environ.get('ATELIER_BUILD_ROOT', ROOT / 'build')) / 'yorimichi/skate-runtime/target'
    cargo = ['cargo', *(['+' + args.toolchain] if args.toolchain else [])]
    subprocess.run([*cargo, 'build', '--release', '--locked', '--jobs', '2', '--manifest-path',
                    str(SOURCE / 'Cargo.toml'), '--target-dir', str(target)], check=True)
    name = 'atelier-skate-runtime' + ('.exe' if os.name == 'nt' else '')
    destination = ROOT / 'games/yorimichi/unreal/Content/Data/SkateRuntime/bin' / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Replace the inode: overwriting a previously executed Mach-O in place can retain a stale code-sign cache.
    # Atomic replacement also leaves an already running worker's executable intact until it exits.
    with tempfile.TemporaryDirectory(prefix='stage-', dir=destination.parent) as folder:
        staged = Path(folder) / name
        shutil.copy2(target / 'release' / name, staged)
        os.replace(staged, destination)
    print('Staged skating runtime in Content/Data/SkateRuntime/bin.')


if __name__ == '__main__':
    main()
