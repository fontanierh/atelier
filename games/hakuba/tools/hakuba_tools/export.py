"""Exports asset folders, or checks that their committed exports are current.

    uv run --project tools export assets/characters/nox     # run its src/ script, record its inputs
    uv run --project tools export --check assets            # every asset folder under assets/

An asset folder holds an asset.toml naming its export script and outputs. Exporting runs the script, checks that every
output was written and records in asset.toml a checksum of the inputs: the folder's src/ and these tools. A check reports
a folder whose outputs are missing or whose inputs no longer match that checksum.
"""
import argparse
import hashlib
import runpy
import sys
from pathlib import Path

import tomlkit

TOOLS = Path(__file__).resolve().parent


def inputs_sha256(folder):
    digest = hashlib.sha256()
    for root in (folder / 'src', TOOLS):
        for path in sorted(root.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and not path.name.startswith('.'):
                digest.update(path.relative_to(root.parent).as_posix().encode() + b'\0')
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def problems(folder):
    config = tomlkit.parse((folder / 'asset.toml').read_text())
    found = [f'{name} is missing' for name in config['outputs'] if not (folder / name).is_file()]
    if config['export'].get('inputs_sha256') != inputs_sha256(folder):
        found.append('its inputs changed since the last export')
    return found


def export(folder):
    path = folder / 'asset.toml'
    config = tomlkit.parse(path.read_text())
    runpy.run_path(str(folder / config['export']['script']), run_name='__main__')
    missing = [name for name in config['outputs'] if not (folder / name).is_file()]
    if missing:
        raise SystemExit(f'{folder}: the export did not write {", ".join(missing)}')
    config['export']['inputs_sha256'] = inputs_sha256(folder)
    path.write_text(tomlkit.dumps(config))
    print(f'{folder}: exported {", ".join(config["outputs"])}')


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
