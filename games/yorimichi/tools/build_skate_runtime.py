#!/usr/bin/env python3
"""Build and stage the optional recovered skating runtime (Rust >= 1.95).

Run import_skate_runtime.py once to install its local animation/settings data.
The ordinary Unreal build continues to work without Rust or these data files.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'platform/engine/Plugins/Activities/Skate/ThirdParty/skate-runtime/atelier-host'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', help='rustup toolchain, e.g. 1.97.1; otherwise use the configured default')
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
    print('Staged skating runtime in Content/Data/SkateRuntime/bin.')


if __name__ == '__main__':
    main()
