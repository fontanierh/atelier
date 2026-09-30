#!/usr/bin/env python3
"""Build the recovered skating runtime and install the committed animation/settings bundle."""
import argparse
import hashlib
import json
import zipfile
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
BUNDLE = ROOT / 'games/yorimichi/assets/skate'
SOURCE = ROOT / 'platform/engine/Plugins/Activities/Skate/ThirdParty/skate-runtime/atelier-host'


def stage_assets(destination):
    manifest = json.loads((BUNDLE / 'runtime.json').read_text())
    archive = BUNDLE / 'runtime.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['archive_sha256']:
        raise ValueError('Skate runtime bundle checksum mismatch')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle, tempfile.TemporaryDirectory(prefix='stage-', dir=destination.parent) as temp:
        if set(bundle.namelist()) != set(manifest['sha256']):
            raise ValueError('Skate runtime bundle manifest mismatch')
        for name, digest in manifest['sha256'].items():
            data = bundle.read(name)
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f'Skate runtime asset checksum mismatch: {name}')
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Invalid runtime asset path')
            target = destination / relative
            if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            staged = Path(temp) / 'asset'
            staged.write_bytes(data)
            os.replace(staged, target)
    print(f'Staged {len(manifest["sha256"])} committed skating assets.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', default='1.97.1', help='rustup toolchain (default: 1.97.1)')
    args = parser.parse_args()
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
    stage_assets(destination.parent.parent / 'assets')
    print('Staged skating runtime in Content/Data/SkateRuntime/bin.')


if __name__ == '__main__':
    main()
