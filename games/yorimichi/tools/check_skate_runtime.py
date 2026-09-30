#!/usr/bin/env python3
"""Exercise the complete local Rust session: physical support, push, ollie, landing and reset.

Requires the normal Yorimichi build; results go to build/yorimichi.
"""
import argparse
import json
import math
from pathlib import Path
import selectors
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / 'games/yorimichi/unreal/Content/Data/SkateRuntime'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, default=RUNTIME / 'assets')
    args = parser.parse_args()
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
        proc = subprocess.Popen([str(binary), str(args.assets), str(world)], stdin=subprocess.PIPE,
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
            def matrix_product(a, b):
                return [sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]
            deck = ready['names'].index('SKATEBOARD_ROOT')
            def yaw(row):
                m = matrix_product(row['root'], row['bones'][deck])
                return math.degrees(math.atan2(m[8], m[10]))
            def exercise(goofy, direction, pop, spin, slide=False):
                send('activate', spawn=[0,0,0], heading=0, goofy=goofy, difficulty='normal', trucks=.5,
                     pop=pop, spin=spin, generation=9, velocity=[0,0,5])
                first=read()
                assert first['generation']==9 and abs(first['root'][12])<.02 and abs(first['root'][14])<.02
                assert first['velocity']==[0.,0.,5.], first['velocity']
                rows=[]; angle=0.; previous=yaw(first)
                for frame in range(330):
                    if slide:
                        left=[int(direction*.6*32767),int(-.8*32767)] if 150<=frame<210 else [0,0]
                        right=[0,0]
                    else:
                        left=[direction*32767 if 160<=frame<270 and abs(angle)<350 else 0,0]
                        right=[0,-32767] if 150<=frame<168 else [0,32767] if 168<=frame<170 else [0,0]
                    send('step',dt=1/60,buttons=0,left=left,right=right,triggers=[0,0])
                    row=read(); current=yaw(row)
                    if 'Air' in row['state']: angle+=(current-previous+180)%360-180
                    previous=current; rows.append(row)
                assert not any('Wipeout' in r['state'] for r in rows), {r['state'] for r in rows}
                assert rows[-1]['state']=='PhysicsGround', rows[-1]['state']
                height=max(matrix_product(r['root'],r['bones'][deck])[13] for r in rows)
                return rows,dict(goofy=goofy,direction=direction,height_m=height,air_rotation_degrees=angle,
                                 airtime_s=sum('Air' in r['state'] for r in rows)/60)
            _, stock=exercise(False,0,1.,1.)
            _, tuned=exercise(False,0,1.15,2.15)
            assert .15<tuned['height_m']-stock['height_m']<.4,(stock,tuned)
            assert tuned['airtime_s']>stock['airtime_s']+.08,(stock,tuned)
            feedback={'stock_pop':stock,'tuned_pop':tuned,'spins':[],'slides':[]}
            def pushes(power, target):
                send('activate',spawn=[0,0,0],heading=0,goofy=False,difficulty='normal',trucks=.5,
                     push_power=power,push_speed=target)
                read();speeds=[]
                for frame in range(300):
                    send('step',dt=1/60,buttons=0x1000 if frame>=60 else 0,left=[0,0],right=[0,0],triggers=[0,0])
                    r=read()
                    if frame>=60:speeds.append(math.hypot(r['velocity'][0],r['velocity'][2]))
                return dict(at_two_seconds_mps=speeds[119],at_four_seconds_mps=speeds[-1])
            stock_push=pushes(1.,1.); tuned_push=pushes(1.45,1.15)
            assert tuned_push['at_two_seconds_mps']>stock_push['at_two_seconds_mps']*1.1,(stock_push,tuned_push)
            assert tuned_push['at_four_seconds_mps']>stock_push['at_four_seconds_mps'],(stock_push,tuned_push)
            feedback['pushes']=dict(stock=stock_push,tuned=tuned_push)

            for goofy in (False,True):
                for direction in (-1,1):
                    rows, result=exercise(goofy,direction,1.15,2.15)
                    assert 300<abs(result['air_rotation_degrees'])<370,result
                    feedback['spins'].append(result)
                    rows, result=exercise(goofy,direction,1.15,2.15,slide=True)
                    assert any(r['state']=='SlideGround' for r in rows)
                    assert math.hypot(rows[-1]['velocity'][0],rows[-1]['velocity'][2])<3.5
                    feedback['slides'].append(result)
            # A retained session mounts at the new feet position, never the previous ride, with a running start.
            for generation,spawn in [(10,[15,0,10]),(11,[-12,0,-8])]:
                send('activate',spawn=spawn,heading=0,goofy=False,difficulty='normal',trucks=.5,
                     generation=generation,velocity=[0,0,4.2],pop=1.15,spin=2.15)
                mounted=read()
                assert mounted['generation']==generation
                assert math.hypot(mounted['root'][12]-spawn[0],mounted['root'][14]-spawn[2])<.02
                assert abs(mounted['velocity'][2]-4.2)<1e-6,mounted['velocity']
                send('step',dt=1/30,buttons=0,left=[0,0],right=[0,0],triggers=[0,0])
                moved=read()
                assert moved['generation']==generation and moved['velocity'][2]>3.5
                assert 0<moved['root'][14]-spawn[2]<.25
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
            report = {'ready_seconds': loading, 'cases': cases, 'bail_recovery': sorted(bail_states), 'feedback': feedback, 'passed': True}
            (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report, indent=2))
        finally:
            selector.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=10)


if __name__ == '__main__':
    main()
