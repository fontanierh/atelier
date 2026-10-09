#!/usr/bin/env python3
"""Verify the game asset library from a fresh checkout, without generated output."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import runpy
import tempfile

GAME = Path(__file__).resolve().parents[1]
ASSETS = GAME / 'assets'
FORMATS = {'.glb', '.npz', '.blend', '.png', '.jpg', '.jpeg'}


def verify(assets=ASSETS):
    assets = Path(assets)
    contract = json.loads((assets / 'source-library.json').read_text())
    files = contract['files']
    actual = {p.relative_to(assets).as_posix() for p in assets.rglob('*')
              if p.is_file() and (p.suffix in FORMATS or p.parent == assets / 'characters/adventure/source')}
    if actual != set(files):
        raise ValueError(f'Library file set differs: missing={sorted(set(files) - actual)}, extra={sorted(actual - set(files))}')
    for name, entry in files.items():
        raw = (assets / name).read_bytes()
        if len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Library source size or checksum mismatch: ' + name)
    native = contract['native_skating']
    runtime = assets.parent / native['directory']
    if hashlib.sha256((runtime / native['manifest']).read_bytes()).hexdigest() != native['sha256']:
        raise ValueError('Library native skating manifest checksum mismatch')
    verifier = runpy.run_path(str(GAME / 'tools/verify_skate_native.py'))
    with tempfile.TemporaryDirectory() as folder:
        package = verifier['assemble'](Path(folder) / 'package', runtime, assets / native['motion'])
        skating = verifier['verify_bundle'](package, assets / 'skate/runtime.json')
    return {'files': files, 'formats': dict(Counter(Path(name).suffix for name in files)),
            'source_bytes': sum(entry['bytes'] for entry in files.values()), 'native_skating': skating}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = verify()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('files', 'native_skating')}, indent=2), flush=True)
    print(f"Verified {len(report['files'])} library sources and {report['native_skating']['payloads']} native skating payloads.", flush=True)
