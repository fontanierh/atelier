#!/usr/bin/env python3
"""Measure real frame pacing through park skating, including bails (normal game, no fixed-step capture)."""
import argparse
import json
import time
import skate as qa


def summarize(rows):
    if len(rows)<2: raise RuntimeError('Frame sampler did not record a running game')
    intervals=[(b[0]-a[0])*1000 for a,b in zip(rows,rows[1:])]
    ordered=sorted(intervals)
    def percentile(p): return ordered[min(len(ordered)-1,round((len(ordered)-1)*p))]
    repeated=longest=0
    for a,b in zip(rows,rows[1:]):
        repeated=repeated+1 if a[1]==b[1] else 0
        longest=max(longest,repeated)
    return dict(frames=len(intervals),fps=1000/(sum(intervals)/len(intervals)),
                p95_ms=percentile(.95),p99_ms=percentile(.99),worst_ms=max(intervals),
                over_33ms=sum(t>33.34 for t in intervals),over_50ms=sum(t>50 for t in intervals),
                repeated_native_frames=sum(a[1]==b[1] for a,b in zip(rows,rows[1:])),
                longest_repeated_native_run=longest,
                modes=sorted({r[2] for r in rows}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8830);args=parser.parse_args()
    qa.bridge.URL=f'http://127.0.0.1:{args.port}'
    qa.py((qa.GAME/'scenarios/skate_live_skate.py').read_text())
    qa.py('live.L.fixed_step(0); live.skate_park(); live.skate_input()')
    for _ in range(60):
        if 'retail=PhysicsGround' in qa.py('print(live.skate_state())'): break
        time.sleep(1)
    else: raise RuntimeError('Runtime did not become ready')
    qa.settle(minimum=58,seconds=3,limit=60)
    qa.py('''
import time
p=unreal.GameplayStatics.get_player_character(live.L.game_world(),0)
deck=next(c for c in p.get_components_by_class(unreal.StaticMeshComponent) if c.get_name()=='SkateDeck')
def sample_performance(dt):
    s=live.skate_state()
    live.PERF.append([time.perf_counter(),int(s.split('tick=')[-1].split()[0]),s.split('mode=')[1].split()[0]])
def performance_pump(dt):
    live.skate_input(grab_right='mode=1 ' in live.skate_state() and deck.get_world_location().z<305 and p.get_velocity().x>0)
''')
    report={}
    for name,x,y,speed,seconds in [
        ('push_and_flip',-28,38,0,5.5),
        ('bowl_pump_air',29,-10,850,5.5),
        ('mini_air',-23,-22,900,7),
        ('quarter_air',33,25,850,4.5),
        ('street_to_mini',-23,38,700,11),
        ('bail',-20,38,500,4.5)]:
        heading=-90 if name=='street_to_mini' else 0
        qa.py(f'live.park.place({x},{y},{heading});live.skate_input();live.park.look(-12,{heading})')
        time.sleep(1.5)
        # Start before the action, including the first bail's skinned vertex cache preparation.
        qa.py("live.PERF=[];live.behave('perf_sample',sample_performance)")
        time.sleep(.1)
        qa.py(f'live.park.launch({speed},{heading})')
        if name=='bail':
            qa.py("live.skate_release();live.L.input_key('Gamepad_LeftThumbstick','press',1);live.L.input_key('Gamepad_RightThumbstick','press',1);live.L.input_key('Gamepad_LeftTriggerAxis','axis',1);live.L.input_key('Gamepad_RightTriggerAxis','axis',1)")
        else:
            if name=='push_and_flip':
                qa.py("live.skate_script([(2.4,{'push':True}),(.4,{}),(.3,{'right':(0,-1)}),(.03,{'right':(-1,1)}),(2.37,{})])")
            if name=='bowl_pump_air':qa.py("live.behave('perf_pump',performance_pump)")
            if name=='mini_air':qa.py('live.skate_input(grab_right=True)')
        time.sleep(seconds)
        raw=json.loads(qa.py("live.stop('perf_sample');live.stop('perf_pump');print(json.dumps(live.PERF))").strip().splitlines()[-1])
        report[name]=summarize(raw)
        modes=set(report[name]['modes'])
        required={'4'} if name=='bail' else {'1'} if name=='street_to_mini' else {'1','2'}
        report[name]['activity_observed']=required<=modes and (name=='bail' or '4' not in modes)
        print(name+': '+json.dumps(report[name]),flush=True)
        qa.py("live.skate_input();live.L.input_key('Gamepad_LeftThumbstick','release',0);live.L.input_key('Gamepad_RightThumbstick','release',0);live.L.input_key('Gamepad_LeftTriggerAxis','axis',0);live.L.input_key('Gamepad_RightTriggerAxis','axis',0)")
    output=qa.yori.OUT/'skateqa/performance.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if all(r['activity_observed'] and r['fps']>=58.5 and r['p95_ms']<20 and r['p99_ms']<33.34
                    and not r['over_50ms'] and r['longest_repeated_native_run']<3 for r in report.values()) else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    finally:
        qa.py("live.stop('perf_sample');live.stop('perf_pump');live.stop('skate_script');live.skate_park();live.skate_release();live.L.input_key('Gamepad_LeftThumbstick','release',0);live.L.input_key('Gamepad_RightThumbstick','release',0);live.L.input_key('Gamepad_LeftTriggerAxis','axis',0);live.L.input_key('Gamepad_RightTriggerAxis','axis',0)")
