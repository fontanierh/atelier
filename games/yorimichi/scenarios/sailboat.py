"""Run native sailboat regression checks and capture real rear/side gameplay stills.

Run only after building/importing sailboat assets and rebuilding YorimichiEditor.
atelier qa yorimichi sailboat SESSION
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = yori.GAME
PROJECT = ROOT / 'unreal'
sys.path.insert(0, str(ROOT / 'tools'))
from benchmark import other_render_processes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    args = parser.parse_args()
    busy = other_render_processes()
    if busy:
        raise RuntimeError(f'Wait for active render jobs before native QA: {busy}')
    folder = yori.OUT / 'sailboat' / args.session
    folder.mkdir(parents=True, exist_ok=False)
    engine = Path(os.environ.get('UE_ROOT', '/Users/Shared/Epic Games/UE_5.8'))
    command = [str(engine / 'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'),
               str(PROJECT / 'Yorimichi.uproject'), '-game', '-windowed',
               '-resx=1920', '-resy=1080',  '-sailboatqa',
               '-fixedview', '-UseFixedTimeStep', '-FPS=60', '-unattended', '-nosplash',
               '-stdout', '-reviewdir=' + str(folder), '-abslog=' + str(folder / 'game.log'),
               '-ExecCmds=r.DynamicRes.OperationMode 0,r.ScreenPercentage 100']
    settings = PROJECT / 'Saved/settings.txt'
    before = settings.read_bytes() if settings.exists() else None
    manifest = dict(command=command,
                    commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                    dirty=subprocess.check_output(['git', 'status', '--porcelain'], text=True),
                    native_sha256=hashlib.sha256((PROJECT / 'Binaries/Mac/libUnrealEditor-Yorimichi.dylib').read_bytes()).hexdigest(),
                    fixed_step=True, performance_evidence=False)
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with (folder / 'stdout.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
    after = settings.read_bytes() if settings.exists() else None
    assert before == after, 'Native QA changed saved preferences'
    assert 'SAILBOAT QA COMPLETE' in (folder / 'game.log').read_text(), 'Native QA did not finish'
    results = json.loads((folder / 'results.json').read_text())
    expected = ['01_rear', '02_rear', '03_side', '04_helm', '05_helm', '06_side', '13_rear']
    for name in expected:
        path = folder / f'sailboat_{name}.png'
        assert path.is_file(), f'Missing actual gameplay screenshot: {name}'
        assert struct.unpack('>II', path.read_bytes()[16:24]) == (1920, 1080)
    with (folder / 'telemetry.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 1500, 'Incomplete native telemetry'
    assert {int(row['step']) for row in rows} == set(range(23)), 'Missing QA stages'
    results.update(settings_unchanged=True, screenshots=expected, telemetry_frames=len(rows),
                   scope='Native boat behavior; phone transport tested separately')
    (folder / 'checks.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2), flush=True)
    assert results['checks'] >= 45, 'Missing native assertions'
    assert results['passed'], results['errors']


if __name__ == '__main__':
    main()
