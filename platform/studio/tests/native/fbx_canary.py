"""Explicit guarded receiving canary; hosted CI runs the source-level exporter checks."""
import hashlib
import json
import os
from pathlib import Path


from atelier import engine
from atelier.harness.safety import guarded



def run(tmp_path):
    fixture = Path(__file__).resolve().parents[1] / 'fixtures' / 'fbx_export.py'
    before = hashlib.sha256(fixture.read_bytes()).hexdigest()
    for name, seed in (('first', '0'), ('second', '91')):
        command = [engine.blender(), '-b', '--factory-startup', '--threads', '3',
                   '--python-exit-code', '1', '--python', str(fixture), '--', '--output', str(tmp_path/name)]
        if name == 'second':
            command.append('--reverse')
        code = guarded.run(command, tmp_path/(name+'.guard'), timeout=900,
            purpose='native FBX determinism and receiving canary', kind='job',
            env=dict(os.environ, PYTHONHASHSEED=seed))
        assert code == 0
        assert 'FBX EXPORT CANARY COMPLETE' in (tmp_path/(name+'.guard')/'stdout.log').read_text()
    for name in ('static.fbx', 'skeletal.fbx', 'clip.fbx'):
        assert (tmp_path/'first'/name).read_bytes() == (tmp_path/'second'/name).read_bytes(), name
    receiver = fixture.with_name('fbx_receive.py')
    for kind in ('static', 'skeletal', 'clip'):
        report = tmp_path / (kind+'.receive.guard')
        command = [engine.blender(), '-b', '--factory-startup', '--threads', '3',
                   '--python-exit-code', '1', '--python', str(receiver), '--', str(tmp_path/'first'), kind]
        assert guarded.run(command, report, timeout=900, kind='job',
            purpose='native FBX '+kind+' receiving canary') == 0
        assert 'FBX RECEIVE CANARY COMPLETE' in (report/'stdout.log').read_text()
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == before


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run(args.output.resolve())
    print('NATIVE FBX CANARY PASS', flush=True)
