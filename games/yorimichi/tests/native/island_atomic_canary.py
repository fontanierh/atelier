"""Normally guarded actual-source island split equivalence; no donor mutation or native compile."""
import argparse
import json
import os
from pathlib import Path
import uuid

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded


def preflight(root, *, resume_queued=False):
    """Resume only a no-child queue attempt, never a previous native run or partial data."""
    if not os.path.lexists(root): return
    real_directory(root)
    guard = root / 'guard'
    real_directory(guard)
    if (not resume_queued or {p.name for p in root.iterdir()} != {'guard'}
            or {p.name for p in guard.iterdir()} != {'execution-timings.json'}):
        raise ValueError('Fresh canary root or exact metadata-only queued attempt required')
    timing = guard / 'execution-timings.json'
    if timing.is_symlink() or not timing.is_file(): raise ValueError('Linked queue timing evidence')
    original = timing.read_bytes(); value = json.loads(original)
    if (set(value) != {'schema', 'invocation_id', 'admission_seconds', 'child_lifetime_seconds', 'execution_seconds'}
            or value['schema'] != 1 or not isinstance(value['invocation_id'], str)
            or uuid.UUID(value['invocation_id']).hex != value['invocation_id']
            or any(value[key] is not None for key in ('admission_seconds', 'child_lifetime_seconds', 'execution_seconds'))):
        raise ValueError('Previous attempt may have admitted or executed native work')
    archive = root.with_name(root.name + '-queued-' + value['invocation_id'] + '.json')
    if os.path.lexists(archive):
        if archive.is_symlink() or not archive.is_file() or archive.read_bytes() != original:
            raise ValueError('Foreign queue evidence archive')
    else:
        with archive.open('xb') as stream: stream.write(original)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--donor', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--assets', nargs='+')
parser.add_argument('--resume-queued', action='store_true', help='same guarded command after a no-child queue deadline')
args = parser.parse_args()
root = real_directory(args.output.absolute())
preflight(root, resume_queued=args.resume_queued)
fixture = Path(__file__).resolve().parents[1] / 'fixtures/island_atomic_equivalence.py'
command = [engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
           '--python', str(fixture), '--', '--donor', str(args.donor.absolute()), '--output', str(root / 'products'),
           *(['--assets', *args.assets] if args.assets else [])]
code = guarded.run(command, root / 'guard', timeout=1200, kind='job',
                   purpose='actual island predecessor and bounded atomic export conservation',
                   env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'ISLAND ATOMIC EQUIVALENCE COMPLETE' in (root / 'guard/stdout.log').read_text()
result = json.loads((root / 'products/result.json').read_text())
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert result['complete'] and result['exact_source_channels'] and result['exact_piece_channel_union']
assert result['numeric_exported_polygon_union']
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved', [])
print('GUARDED ACTUAL ISLAND ATOMIC EXPORT PASS', flush=True)
