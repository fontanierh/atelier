#!/usr/bin/env python3
"""In-game checks for the complete recovered skating session (requires its local data and worker).

atelier qa yorimichi skate_runtime --port 8830
"""
import argparse
import json
import time
import skate as qa


def position(row):
    return tuple(float(x) for x in row['pos'].strip('()').split(','))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    args = parser.parse_args()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    qa.py('live.L.skate_goofy(False); live.skate_park(); live.skate_input()')
    for _ in range(60):
        state = qa.py('print(live.skate_state())')
        if 'retail=' not in state:
            raise RuntimeError('Complete runtime is not installed/enabled')
        if 'retail=PhysicsGround' in state:
            break
        time.sleep(1)
    else:
        raise RuntimeError('Runtime failed to become ready')
    qa.settle(minimum=35, seconds=2, limit=60)
    results = {}
    def record(name, rows, passed, note):
        results[name] = {'ok': bool(passed), 'note': note, 'frames': len(rows)}
        print(('PASS' if passed else 'FAIL') + ' ' + name + ': ' + note, flush=True)

    rows = qa.run_scenario("-28,6,0,0,[(0,{'push':True}),(2.4,{}),(2.8,('flick','kickflip',(0,0),.3))],duration=5", 5)
    record('push_flip_land', rows, max(float(r['speed']) for r in rows)>400 and 'Kickflip' in qa.combos(rows)
           and '2' in qa.modes(rows) and rows[-1]['mode']=='1' and int(rows[-1]['score'])>0, qa.combos(rows))
    rows = qa.run_scenario("-20,8,0,500,[(.2,{'left':(.6,0)}),(1.2,{})],duration=1.5", 1.5)
    dy=position(rows[-1])[1]-position(rows[0])[1]
    record('steer_right', rows, dy>40 and rows[-1]['mode']=='1', f'rightward displacement {dy:.0f} cm')
    rows = qa.run_scenario("-10,8,0,480,[(.3,{'right':(0,-.5)}),(1.5,{})],duration=2", 2)
    record('manual', rows, qa.ever(rows,'manual','1') and rows[-1]['manual']=='0' and not qa.count(rows,'bails'), qa.combos(rows))
    rows = qa.run_scenario("2,-4.5,0,520,[(.98,('flick','ollie'))],duration=3.5", 3.5)
    record('rail', rows, '3' in qa.modes(rows) and 'Ollie' in qa.combos(rows), 'states '+','.join(sorted(qa.modes(rows)))+'; '+qa.combos(rows))
    rows = qa.run_scenario("22,0,0,950,[],duration=5", 5)
    record('vert', rows, '2' in qa.modes(rows) and not qa.count(rows,'bails'), 'states '+','.join(sorted(qa.modes(rows))))
    # The original engine can recover a sideways drop. Exercise its deliberate bail chord instead.
    qa.py("live.park.place(-10,8,0); live.park.launch(500); live.skate_release(); live.REC=[]; live.behave('rec',lambda dt: live.REC.append(live.skate_state()))")
    qa.py("live.L.input_key('Gamepad_LeftThumbstick','press',1); live.L.input_key('Gamepad_RightThumbstick','press',1); live.L.input_key('Gamepad_LeftTriggerAxis','axis',1); live.L.input_key('Gamepad_RightTriggerAxis','axis',1)")
    time.sleep(.6)
    qa.py("live.L.input_key('Gamepad_LeftThumbstick','release',0); live.L.input_key('Gamepad_RightThumbstick','release',0); live.L.input_key('Gamepad_LeftTriggerAxis','axis',0); live.L.input_key('Gamepad_RightTriggerAxis','axis',0)")
    time.sleep(2)
    qa.py("live.L.input_key('W','press',1)")
    time.sleep(.15)
    qa.py("live.L.input_key('W','release',0)")
    time.sleep(4)
    rows = [qa.parse(r) for r in json.loads(qa.py("live.stop('rec'); print(json.dumps(live.REC))").strip().splitlines()[-1])]
    record('bail_recovery', rows, '4' in qa.modes(rows) and rows[-1]['mode']=='1', 'states '+','.join(sorted(qa.modes(rows))))
    qa.py("live.skate_input(); live.park.place(-10,8,0)")
    time.sleep(.5)
    # The imported Cairo mesh faces -X before its authored mesh-rotation correction.
    text = qa.py('''
import json
p=unreal.GameplayStatics.get_player_character(live.L.game_world(),0)
m=p.mesh
mod=unreal.SkeletonModifier(); mod.set_skeletal_mesh(m.get_skinned_asset())
bind=mod.get_bone_transform('head',True).rotation
head=m.get_socket_transform('head',unreal.RelativeTransformSpace.RTS_WORLD).rotation
look=head.rotate_vector(bind.unrotate_vector(unreal.Vector(-1,0,0)))
forward=p.get_actor_forward_vector()
pc=unreal.GameplayStatics.get_player_controller(live.L.game_world(),0)
length_errors=[]
for a,b in [('chest','neck'),('neck','head'),('thigh_L','shin_L'),('shin_L','foot_L'),('foot_L','toe_L'),('foot_R','toe_R')]:
    rest=(mod.get_bone_transform(a,True).translation-mod.get_bone_transform(b,True).translation).length()
    posed=(m.get_socket_location(a)-m.get_socket_location(b)).length()
    length_errors.append(abs(posed/rest-1))
print(json.dumps({'head_forward':look.x*forward.x+look.y*forward.y+look.z*forward.z,'fov':pc.player_camera_manager.get_fov_angle(),'bone_length_error':max(length_errors)}))
''')
    pose=json.loads(text.strip().splitlines()[-1])
    record('retarget_and_camera', [], pose['head_forward']>.4 and 85<pose['fov']<130 and pose['bone_length_error']<.01, str(pose))
    qa.py("live.skate_release(); live.ANKLES=[]; live.behave('ankles',lambda dt: live.ANKLES.append([m.get_socket_transform(n,unreal.RelativeTransformSpace.RTS_COMPONENT).translation.z for n in ['foot_L','foot_R']])); live.L.input_key('W','press',1)")
    time.sleep(1.6)
    text=qa.py("live.L.input_key('W','release',0); live.stop('ankles'); print(json.dumps({'excursion':max(max(a[i] for a in live.ANKLES)-min(a[i] for a in live.ANKLES) for i in [0,1]),'state':live.skate_state()}))")
    movement=json.loads(text.strip().splitlines()[-1])
    record('keyboard_push_animation',[],movement['excursion']>8 and float(qa.parse(movement['state'])['speed'])>300,str(movement))
    qa.py("live.park.place(-10,8,0)")
    time.sleep(.3)
    qa.py('live.skate(); live.skate_release()')
    time.sleep(.3)
    walking=qa.parse(qa.py('print(live.skate_state())').strip())
    record('stow', [], walking.get('mode')=='0' and 'retail' not in walking, 'mode '+walking.get('mode','?'))
    qa.py('live.skate_park(); live.skate_release()')
    time.sleep(.5)
    remount=qa.py('print(live.skate_state())')
    record('remount', [], 'retail=PhysicsGround' in remount, remount.strip())
    qa.py('live.L.skate_goofy(True)')
    rows = qa.run_scenario("-28,6,0,0,[(0,{'push':True}),(1.5,{}),(1.8,('flick','ollie'))],duration=4",4)
    record('goofy_push_ollie',rows,max(float(r['speed']) for r in rows)>300 and 'Ollie' in qa.combos(rows) and '2' in qa.modes(rows) and rows[-1]['mode']=='1' and not qa.count(rows,'bails'),qa.combos(rows))
    qa.py('live.L.skate_goofy(False); live.skate_park(); live.skate_release()')
    out=qa.yori.OUT / 'skateqa' / 'runtime.json'; out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(results,indent=2)+'\n')
    print(f'{sum(r["ok"] for r in results.values())}/{len(results)} passed -> {out}')
    return 0 if all(r['ok'] for r in results.values()) else 1


if __name__=='__main__':
    try:
        raise SystemExit(main())
    finally:
        # Always return control to the player, including when a check raises.
        qa.py("live.stop('skate_script'); live.stop('rec'); live.stop('ankles'); live.skate_release(); live.L.input_key('W','release',0); live.L.input_key('Gamepad_LeftThumbstick','release',0); live.L.input_key('Gamepad_RightThumbstick','release',0); live.L.input_key('Gamepad_LeftTriggerAxis','axis',0); live.L.input_key('Gamepad_RightTriggerAxis','axis',0)")
