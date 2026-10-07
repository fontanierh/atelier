"""Fetch the pinned private obstacle meshes the skate pier is built from; extracted assets are never tracked.

modules.json pins the release archive and each member. The archive stays in the ignored Atelier cache and only the pinned
members are extracted, to build/yorimichi/skatepark/modules/<part>.glb. Without access the pier builds its procedural
stand-ins on the same lines (world/regions/skatepark/modules.py).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import hashlib
import json
import subprocess
import zipfile
from atelier.paths import cache_dir

SPEC = Path(__file__).parent / 'modules.json'
TARGET = yori.OUT / 'skatepark' / 'modules'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fetch():
    spec = json.loads(SPEC.read_text())
    cache = cache_dir('skate-extractions', spec['release'])
    archive = cache / spec['asset']
    def valid(p):
        return p.is_file() and p.stat().st_size == spec['bytes'] and sha(p.read_bytes()) == spec['sha256']
    if not valid(archive):
        try:
            subprocess.run(['gh', 'release', 'download', spec['release'], '-R', spec['repository'], '-p', spec['asset'],
                            '-D', str(cache), '--clobber'], capture_output=True, check=True)
        except (OSError, subprocess.CalledProcessError):
            # The modules are optional: the pier then builds its procedural stand-ins (docs/SKATE.md, "Skate pier").
            print(f"skate pier modules skipped: needs gh signed in with access to {spec['repository']}")
            return
        if not valid(archive):
            raise SystemExit('Skate pier module archive checksum mismatch; refusing the download.')
    TARGET.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for part, entry in spec['parts'].items():
            target = TARGET / f'{part}.glb'
            if target.is_file() and sha(target.read_bytes()) == entry['sha256']:
                continue
            data = z.read(entry['member'])
            if sha(data) != entry['sha256']:
                raise SystemExit(f'Skate pier module {part} checksum mismatch; refusing it.')
            target.write_bytes(data)
    print(f"skate pier modules verified: {len(spec['parts'])} parts from {spec['release']}")


if __name__ == '__main__':
    fetch()
