#!/usr/bin/env python3
"""Sunset Pier's bank exits, handrail and bowl air in the running Unreal game."""
import argparse
import json
import math
import time
import skate as qa


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8830);args=parser.parse_args()
    qa.bridge.URL=f'http://127.0.0.1:{args.port}'
    qa.py((qa.GAME/'scenarios/skate_live_skate.py').read_text())
    # The native runtime's park checks: the game rides on Ride by default.
    qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.Backend Native')")
    qa.py('live.skate_park(); live.skate_input()')
    for _ in range(60):
        if 'retail=PhysicsGround' in qa.py('print(live.skate_state())'):break
        time.sleep(1)
    else:raise RuntimeError('Skater failed to become ready')
    report={}
    def record(name,ok,**values):
        report[name]=dict(ok=bool(ok),**values)
        print(('PASS ' if ok else 'FAIL ')+name+': '+str(values),flush=True)
    # A low entry speed; gravity supplies the speed. All exits lead into open park lanes.
    for name,x,y,heading,drop in [('bowl',15,-10,180,3.2),('mini',-37.5,-14,90,2.65),('return',71.5,19,-90,2.15),('mellow',69.5,-35,90,1.6),('seven',-49,34,0,1.26),('four',-62,7,-90,.72),('market',-62,-27,-90,.60)]:
        rows=qa.run_scenario(f'{x},{y},{heading},200,[],duration=4',4)
        speed=max(float(r['speed']) for r in rows)
        # Compare with gravity's available energy, allowing ordinary rolling loss.
        # A 60 cm bank at 2 m/s has an ideal exit of 3.97 m/s, below the old
        # common 4 m/s floor even without friction.
        minimum=.9*math.sqrt(200**2+2*981*drop*100)
        record(name+'_rollin',speed>minimum and not qa.count(rows,'bails') and rows[-1]['mode']=='1',max_speed_cm_s=speed,minimum_speed_cm_s=round(minimum,1),states=sorted(qa.modes(rows)))
    rows=qa.run_scenario("-64,25.5,0,520,[(1.8,('flick','ollie',(0,0),.2))],duration=3.3",3.3)
    record('stair_handrail','3' in qa.modes(rows) and not qa.count(rows,'bails'),tricks=qa.combos(rows))
    qa.py("live.park.place(29,-10,0); live.skate_input(); p=unreal.GameplayStatics.get_player_character(live.L.game_world(),0); deck=next(c for c in p.get_components_by_class(unreal.StaticMeshComponent) if c.get_name()=='SkateDeck')")
    time.sleep(1.2)
    qa.py('''
live.BOWL=[]
def bowl_check(dt):
    q=deck.get_world_location();v=p.get_velocity();state=live.skate_state()
    grounded='mode=1 ' in state
    live.skate_input(grab_right=grounded and q.z<305 and v.x>0)
    live.BOWL.append({'z':(q.z-180)/100,'x':q.x/100+110,'velocity':[v.x/100,-v.y/100,v.z/100],'state':state})
live.behave('bowl_check',bowl_check);live.park.launch(850)
''')
    time.sleep(5)
    rows=json.loads(qa.py("live.stop('bowl_check');live.skate_input();print(json.dumps(live.BOWL))").strip().splitlines()[-1])
    air=next((i for i,r in enumerate(rows) if qa.parse(r['state'])['mode']=='2'),None)
    lands=[] if air is None else [r for r in rows[air+1:] if qa.parse(r['state'])['mode']=='1' and .3<r['z']<3]
    apex=max(r['z'] for r in rows)
    record('bowl_up_and_back',air is not None and apex>3.5 and bool(lands) and abs(lands[0]['x']-42)<2.5 and not any(qa.parse(r['state'])['mode']=='4' for r in rows),apex_m=apex,landing=lands[0]['x'] if lands else None)
    qa.py('live.skate_park();live.skate_release()')
    output=qa.yori.OUT/'skateqa/park.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    return 0 if all(v['ok'] for v in report.values()) else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    finally:qa.py("live.stop('bowl_check');live.stop('rec');live.stop('skate_script');live.skate_release()")
