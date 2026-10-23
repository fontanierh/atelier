"""Bounded ordinary guard for actual Harbor source-data cut/export parity."""
import argparse
import json
import os
from pathlib import Path

from atelier import engine
from atelier.export_manifest import real_directory
from atelier.harness.safety import guarded

parser = argparse.ArgumentParser(description=__doc__)
for flag in ('source', 'site', 'output'): parser.add_argument('--' + flag, type=Path, required=True)
args = parser.parse_args()
root = real_directory(args.output.absolute())
if os.path.lexists(root): raise ValueError('Cut canary requires fresh evidence')
fixture = Path(__file__).resolve().parents[1] / 'fixtures/hidamari_cut_data.py'
code = guarded.run([engine.blender(), '-b', '--factory-startup', '--threads', '3', '--python-exit-code', '1',
    '--python', str(fixture), '--', '--source', str(args.source.absolute()), '--site', str(args.site.absolute()),
    '--output', str(root / 'products')], root / 'guard', timeout=300, kind='job',
    purpose='actual Harbor source-data cut and atomic export conservation', env=dict(os.environ, PYTHONHASHSEED='0'))
if code: raise SystemExit(code)
assert 'HARBOR SOURCE DATA CUT CANARY COMPLETE' in (root / 'guard/stdout.log').read_text()
value = json.loads((root / 'products/result.json').read_text())
assert value['complete'] and value['exact_exported_corners'] and value['exact_cut_controls']
guard = json.loads((root / 'guard/memory-health-tree.json').read_text())
assert guard['state'] == 'child_exited' and guard['cleanup_complete'] and not guard['processes']
assert not guard.get('late_reporters', {}).get('unresolved')
print('GUARDED HARBOR SOURCE DATA CUT PASS', flush=True)
