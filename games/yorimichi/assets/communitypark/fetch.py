"""Fetch the pinned private community-park handoff; extracted assets are never tracked."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'world'))
import yori
import base64
import hashlib
import json
import shutil
import subprocess
from atelier.paths import cache_dir


def fetch():
    spec = json.loads((Path(__file__).parent / 'source.json').read_text())
    name = Path(spec['file']).name
    cache = cache_dir('skate-extractions', spec['revision']) / name
    target = yori.OUT / 'communitypark' / 'source' / name
    def valid(p):
        return p.is_file() and p.stat().st_size == spec['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest() == spec['sha256']
    if not valid(cache):
        if valid(target):
            data = target.read_bytes()
        else:
            try:
                result = subprocess.run(['gh', 'api', f"repos/{spec['repository']}/git/blobs/{spec['blob']}"],
                                        capture_output=True, check=True)
            except (OSError, subprocess.CalledProcessError):
                # The park is optional: the island builds without it (docs/COMMUNITY_PARK.md).
                print(f"community park skipped: needs gh signed in with access to {spec['repository']}")
                return
            data = base64.b64decode(json.loads(result.stdout)['content'])
        if len(data) != spec['bytes'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise SystemExit('Community park source checksum mismatch; refusing the download.')
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix('.download')
        temporary.write_bytes(data)
        temporary.replace(cache)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not valid(target):
        shutil.copy2(cache, target)
    print(f"community park source verified: {spec['revision']}, {spec['bytes']} bytes")


if __name__ == '__main__':
    fetch()
