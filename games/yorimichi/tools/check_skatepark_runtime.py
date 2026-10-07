#!/usr/bin/env python3
"""Exercise Sunset Pier's exported collision with the native offline QA session.

Build world.skatepark and verify skate.runtime first, then explicitly build the
test-only gameplay-session-cli under the render guard. This does not select a
shipping backend. Results: build/yorimichi/skatepark/physics/.
"""
import argparse
import json
import math
from pathlib import Path
import selectors
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
NATIVE_PACKAGE = ROOT / 'games/yorimichi/unreal/Content/Data/SkateNative'
BINARY = ROOT / 'build/skate-native-session-cli' / ('gameplay-session-cli.exe' if sys.platform == 'win32' else 'gameplay-session-cli')
OUT = ROOT / 'build/yorimichi/skatepark'


def product(a, b):
    return [sum(a[k*4+r]*b[c*4+k] for k in range(4)) for c in range(4) for r in range(4)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-package', type=Path, default=NATIVE_PACKAGE)
    parser.add_argument('--binary', type=Path, default=BINARY, help='Already built offline native QA executable')
    args = parser.parse_args()
    if not args.binary.is_file():
        parser.error('Native QA executable is missing; build Tests/build_native_session_cli.py --compile under the render lock and memory guard first')
    if not (args.native_package / 'package-manifest.json').is_file():
        parser.error('Native bundle manifest is missing: ' + str(args.native_package))
    output = OUT / 'physics'; output.mkdir(parents=True, exist_ok=True)
    with (output / 'native-session.log').open('w') as log:
        proc = subprocess.Popen([str(args.binary), str(args.native_package), str(OUT/'collision.json')],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True, bufsize=1)
        selector = selectors.DefaultSelector(); selector.register(proc.stdout, selectors.EVENT_READ)
        def read():
            if not selector.select(60): raise TimeoutError('Native QA session timed out')
            row = json.loads(proc.stdout.readline())
            if row['type'] == 'error': raise RuntimeError(row['message'])
            return row
        def send(op, **values):
            proc.stdin.write(json.dumps(dict(op=op, **values))+'\n'); proc.stdin.flush()
        def tick(trigger=0):
            send('step', dt=1/60, buttons=0, left=[0,0], right=[0,0], triggers=[trigger,0])
            return read()
        try:
            ready = read(); deck = ready['names'].index('SKATEBOARD_ROOT')
            def board(row): return product(row['root'], row['bones'][deck])
            def exercise(name, x, y, speed, duration, pump=None, z=0, heading=0, pop=False, gesture=None):
                angle=math.radians(heading)
                send('activate', spawn=[y,z,x], heading=angle, goofy=False, difficulty='normal', trucks=.5, pop=1.15, spin=2.15)
                read()
                for _ in range(60): row=tick()
                send('launch', velocity=[speed*math.sin(angle),0,speed*math.cos(angle)])
                rows=[]; pop_frames=0
                for frame in range(round(duration*60)):
                    trigger=pump(row,board(row)) if pump else 0
                    if gesture:
                        start,load=gesture; t=frame/60
                        right=[0,-32767] if start<=t<start+load else [0,32767] if start+load<=t<start+load+.034 else [0,0]
                        send('step',dt=1/60,buttons=0,left=[0,0],right=right,triggers=[trigger,0]);row=read()
                    elif pop:
                        before=board(row)
                        if before[13]>2.2 and pop_frames==0:pop_frames=1
                        right=[0,32767] if 0<pop_frames<3 else [0,-32767] if pop_frames==0 and before[13]>.3 else [0,0]
                        if pop_frames:pop_frames+=1
                        send('step',dt=1/60,buttons=0,left=[0,0],right=right,triggers=[trigger,0]);row=read()
                    else:row=tick(trigger)
                    b=board(row)
                    rows.append(dict(t=frame/60,state=row['state'],pos=[b[14],b[12],b[13]],
                                     velocity=[row['velocity'][2],row['velocity'][0],row['velocity'][1]],trigger=trigger,trick=row['trick']))
                (output/(name+'.json')).write_text(json.dumps(rows)+'\n')
                assert not any('Wipeout' in r['state'] for r in rows), name+' bailed'
                assert rows[-1]['state']=='PhysicsGround', (name,rows[-1])
                return rows
            def air_return(rows, lip, rim):
                air=next(i for i,r in enumerate(rows) if 'Air' in r['state'])
                # An air must leave upwards and recontact a sloped face below its lip.
                leave=rows[air]; land=next(r for r in rows[air+1:] if r['state']=='PhysicsGround' and r['pos'][2]<rim-.2)
                assert leave['velocity'][2]>0
                assert abs(leave['velocity'][0])<max(2.,leave['velocity'][2])
                assert abs(land['pos'][0]-lip)<2.5 and land['pos'][2]>.3,(leave,land)
                assert max(r['pos'][2] for r in rows)>rim+.1
                return dict(apex_m=max(r['pos'][2] for r in rows),launch_velocity=leave['velocity'],landing=land['pos'])
            base=exercise('bowl_coast',29,-10,8.5,5)
            # Compress on approach, extend partway up the transition; release in air to avoid grabbing.
            pumping=lambda row,b:255 if b[13]<1.25 and row['velocity'][2]>0 and 'Air' not in row['state'] else 0
            pumped=exercise('bowl_pump',29,-10,8.5,5,pumping)
            def return_speed(rows):
                row=next(b for a,b in zip(rows,rows[1:]) if a['pos'][0]>30>=b['pos'][0] and b['t']>2)
                return math.hypot(*row['velocity'][:2])
            report={'bowl':air_return(pumped,42,3.2),'pumping':dict(coast_apex_m=max(r['pos'][2] for r in base),
                pumped_apex_m=max(r['pos'][2] for r in pumped),coast_return_mps=return_speed(base),pumped_return_mps=return_speed(pumped))}
            gain=report['pumping']
            assert gain['pumped_apex_m']>gain['coast_apex_m']+.5,gain
            assert gain['pumped_return_mps']>gain['coast_return_mps']+.4,gain
            crouch=lambda row,b:255 if 'Air' not in row['state'] else 0
            mini=exercise('mini_back_and_forth',-23,-22,9,9,crouch)
            report['mini']=air_return(mini,-10,2.65)
            assert any('Air' in r['state'] and r['pos'][0]<-35 for r in mini), 'No return air on opposite wall'
            quarter=exercise('east_return',57,25,8.5,4)
            report['quarter']=air_return(quarter,70,2.15)
            rollin=exercise('bowl_rollin',15,-10,2,4,crouch,z=3.2,heading=180)
            report['rollin_max_speed_mps']=max(math.hypot(*r['velocity'][:2]) for r in rollin)
            assert report['rollin_max_speed_mps']>5
            popped=exercise('bowl_ollie',29,-10,9,5,pop=True)
            report['bowl_ollie']=air_return(popped,42,3.2)
            rail=exercise('seven_stair_handrail',-64,25.5,5.2,5,z=1.5,gesture=(2.5,.2))
            assert any('Grind' in r['state'] for r in rail),'Handrail was not acquired'
            report['stair_handrail']=sorted({r['state'] for r in rail if 'Grind' in r['state']})
            report['passed']=True
            (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2),flush=True)
        finally:
            selector.close()
            if proc.poll() is None:
                send('quit')
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired: proc.kill();proc.wait()


if __name__=='__main__': main()
