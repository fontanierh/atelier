"""Exports asset folders, or checks that their committed exports are current.

    uv run --project tools export assets/characters/nox     # export it, record its inputs
    uv run --project tools export --check assets            # every asset folder under assets/

An asset folder holds an asset.toml whose `kind` picks the exporter (KINDS); that exporter reads its other settings.
Exporting writes the folder's outputs and records in asset.toml a checksum of the inputs: its settings, its src/ folder
and the hakuba_tools package. A check reports a folder whose outputs are missing or whose inputs no longer match that
checksum.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import tomlkit

from hakuba_tools import character

TOOLS = Path(__file__).resolve().parent
KINDS = {'character': character}


def outputs(folder):
    return [folder / f'{folder.name}.glb']


def inputs_sha256(folder, config):
    digest = hashlib.sha256()
    settings = {key: value for key, value in config.unwrap().items() if key != 'inputs_sha256'}
    digest.update(json.dumps(settings, sort_keys=True).encode() + b'\0')
    for root in (folder / 'src', TOOLS):
        for path in sorted(root.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and not path.name.startswith('.'):
                digest.update(path.relative_to(root.parent).as_posix().encode() + b'\0')
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def problems(folder):
    config = tomlkit.parse((folder / 'asset.toml').read_text())
    found = [f'{path.name} is missing' for path in outputs(folder) if not path.is_file()]
    if config.get('inputs_sha256') != inputs_sha256(folder, config):
        found.append('its inputs changed since the last export')
    return found


def export(folder):
    path = folder / 'asset.toml'
    config = tomlkit.parse(path.read_text())
    written = KINDS[config['kind']].export(folder, config.unwrap())
    missing = [p.name for p in outputs(folder) if p not in written or not p.is_file()]
    if missing:
        raise SystemExit(f'{folder}: the export did not write {", ".join(missing)}')
    config['inputs_sha256'] = inputs_sha256(folder, config)
    path.write_text(tomlkit.dumps(config))
    print(f'{folder}: exported {", ".join(p.name for p in written)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('folders', nargs='+', type=Path)
    parser.add_argument('--check', action='store_true', help='report stale exports instead of exporting')
    args = parser.parse_args()
    if not args.check:
        for folder in args.folders:
            export(folder.resolve())
        return
    stale = 0
    for root in args.folders:
        for config in sorted(root.resolve().rglob('asset.toml')):
            for problem in problems(config.parent):
                print(f'{config.parent}: {problem}')
                stale += 1
    sys.exit(1 if stale else 0)


if __name__ == '__main__':
    main()
