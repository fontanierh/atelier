#!/usr/bin/env python3
"""Exercise the complete local Rust session: physical support, push, ollie, landing and reset.

Requires build_skate_runtime.py and import_skate_runtime.py; results go to build/yorimichi.
"""
import json
import math
from pathlib import Path
import selectors
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / 'games/yorimichi/unreal/Content/Data/SkateRuntime'


def main():
    output = ROOT / 'build/yorimichi/skate-runtime/check'
    output.mkdir(parents=True, exist_ok=True)
    world = output / 'world.json'
    world.write_text(json.dumps({'triangles': [[[-100, 0, -100], [-100, 0, 100], [100, 0, 100]],
                                               [[-100, 0, -100], [100, 0, 100], [100, 0, -100]]],
                                 'rails': [], 'spawn': [0, 0, 0], 'heading': 0}))
    binary = RUNTIME / 'bin/atelier-skate-runtime'
    if not binary.is_file():
        binary = binary.with_suffix('.exe')
    with (output / 'worker.log').open('w') as log:
        proc = subprocess.Popen([str(binary), str(RUNTIME / 'assets'), str(world)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        def read():
            if not selector.select(60):
                raise TimeoutError('No worker response within 60 seconds')
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError('Worker exited; see worker.log')
            result = json.loads(line)
            if result['type'] == 'error':
                raise RuntimeError(result['message'])
            assert all(math.isfinite(x) for m in [result['root'], *result['bones']] for x in m)
            return result
        def send(op, **values):
            proc.stdin.write(json.dumps({'op': op, **values}) + '\n')
            proc.stdin.flush()
        try:
            started = time.monotonic()
            ready = read()
            assert ready['type'] == 'ready' and len(ready['bones']) == len(ready['reference']) == len(ready['names']) == 36
            loading = time.monotonic() - started
            cases = []
            for goofy in (False, True):
                send('activate', spawn=[0, 0, 0], heading=0, goofy=goofy, difficulty='normal', trucks=.5)
                initial = read()
                records = []
                started = time.monotonic()
                for frame in range(240):
                    # 30 Hz transport, 60 Hz native ticks. Neutral / planted push / loaded straight ollie / roll away.
                    right = [0, -32767] if 100 <= frame < 112 else [0, 32767] if frame == 112 else [0, 0]
                    send('step', dt=1/30, buttons=0x1000 if 30 <= frame < 95 else 0,
                         left=[0, 0], right=right, triggers=[0, 0])
                    records.append(read())
                states = {r['state'] for r in records}
                speed = max(math.hypot(r['velocity'][0], r['velocity'][2]) for r in records)
                assert speed > 3, speed
                assert any('Air' in s for s in states), states
                assert 'Ground' in records[-1]['state'], records[-1]['state']
                assert records[-1]['tick'] - initial['tick'] == 480
                assert abs(records[-1]['root'][13]) < 1, records[-1]['root'][13]
                assert records[80]['bones'] != records[0]['bones'], 'Animation pose never changed'
                cases.append({'goofy': goofy, 'ticks': 480, 'max_speed_mps': speed,
                              'states': sorted(states), 'elapsed_seconds': time.monotonic() - started})
            # Stock deliberate-bail chord, then push-button recovery (not a host-authored ragdoll).
            send('activate', spawn=[0, 0, 0], heading=0, goofy=False, difficulty='normal', trucks=.5)
            read()
            bail_states = set()
            for frame in range(300):
                chord = 20 <= frame < 35
                send('step', dt=1/30, buttons=0xc0 if chord else 0x1000 if 110 <= frame < 115 else 0,
                     left=[0, 0], right=[0, 0], triggers=[255, 255] if chord else [0, 0])
                recovered = read()
                bail_states.add(recovered['state'])
            assert any('Wipeout' in s for s in bail_states), bail_states
            assert recovered['state'] == 'PhysicsGround', recovered['state']
            # Sub-tick acknowledgement keeps the host's one-packet backpressure live at high render rates.
            send('step', dt=.001, buttons=0, left=[0, 0], right=[0, 0], triggers=[0, 0])
            assert read()['type'] == 'pose'
            send('suspend')
            send('quit')
            assert proc.wait(timeout=10) == 0
            report = {'ready_seconds': loading, 'cases': cases, 'bail_recovery': sorted(bail_states), 'passed': True}
            (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report, indent=2))
        finally:
            selector.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


if __name__ == '__main__':
    main()
