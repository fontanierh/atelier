"""Guarded immutable Stable source census; production ENABLED stays false."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.atomic_files import atomic_json
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--donor', type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Fresh Stable original-source evidence required')
donor = real_directory(args.donor.absolute())
checkout = Path(__file__).resolve().parents[4]
def bindings():
    entries = {}
    for name in ('world.json', 'heightmap.npy', 'farhills.npy'):
        path = donor / name
        if path.is_symlink() or not path.is_file(): raise ValueError('Missing original Stable donor data')
        info = path.stat()
        entries[name] = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
    # Immutable Git/source authority is resolved by the outer host only, never by Blender.
    return dict(source_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip(),
        donor_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=donor, text=True).strip(), inputs=entries)
before = bindings()
root.mkdir()
atomic_json(root / 'source-binding-before.json', before)
fixture = Path(__file__).resolve().parents[1] / 'fixtures/stable_atomic_context.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--output', str(root / 'products'), '--donor', str(args.donor.absolute())]
code = guarded.run(command, root / 'guard', timeout=600, kind='job', purpose='immutable disabled-owner Stable constructor census',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
after = bindings()
atomic_json(root / 'source-binding-after.json', after)
atomic_json(root / 'whole-result.json', dict(exit_code=code, source_head=before['source_head']))
if after != before: raise ValueError('Stable source or donor identity changed during guarded census')
if code: raise SystemExit(code)
assert 'STABLE ORIGINAL CONTEXT COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
receipt = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and result['source_policy_enabled'] is False
assert receipt['state'] == 'child_exited' and receipt['cleanup_complete'] and not receipt['processes']
assert not receipt.get('late_reporters', {}).get('unresolved', [])
print('GUARDED ORIGINAL STABLE CONTEXT PASS', flush=True)
