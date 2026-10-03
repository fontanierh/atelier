"""Rehearse and film Sunset Pier with player controls in the running game.

Load skate_live_skate.py first, then this file through `atelier live py -`.
Globals: TAKE (output folder name), FILM (False for telemetry rehearsal), ONLY
(shot names), SHOTS_OVERRIDE (a list of shot dictionaries for focused tuning).
Each shot settles off camera, starts at rest, and uses push, steering and Flick-It
inputs. Placement occurs only between shots. The frame clock stops each take
itself; states.json is the complete ride, including failed attempts.
"""
import json
import math
import os

import unreal

L = live.L
MV = unreal.MegaParkValidation
TAKE = globals().get('TAKE', 'pier-rehearsal')
FILM = globals().get('FILM', False)
ONLY = globals().get('ONLY')
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'),
                   'yorimichi/skatefilm', TAKE)
os.makedirs(OUT, exist_ok=True)
if os.path.exists(os.path.join(OUT, 'done.json')):
    raise RuntimeError('Use a fresh TAKE name; keep the evidence of earlier attempts')

SHOTS = globals().get('SHOTS_OVERRIDE') or [
    dict(name='arrival', start=(-60,48), heading=0, seconds=6,
         events=[(0,{'push':True})],
         camera=('sweep',(118,-143,75),(108,-128,62),(0,0,.8),55)),
    dict(name='promenade', start=(-60, 48), heading=0, seconds=10,needs={'tricks':['Kickflip','360 Flip']},
         events=[(0, {'push': True}), (3.2, {}),
                 (3.6, ('flick', 'kickflip')), (6.7, ('flick', '360_flip'))],
         camera=('chase', -9, 0)),
    dict(name='rail_line', start=(-38, 43), heading=0, seconds=9, line_y=43, needs={'grind':True},
         events=[(0, {'push': True}), (1.0, {})],
         triggers=[dict(x=-31, flick='ollie')],
         camera=('chase', -8, 0)),
    dict(name='granite', start=(1, 28), heading=0, seconds=6, needs={'grind':True},
         events=[(0, {'push': True})], triggers=[dict(x=8.5, flick='ollie')],
         camera=('dolly', (-4, -4, 1.1), 88, .45)),
    dict(name='manuals', start=(-54,54.5), heading=0, seconds=7, line_y=54.5,
         events=[(0,{'push':True}),(1.0,{})], needs={'manual':True},
         manual_ranges=[(-39.5,-26.5)],
         triggers=[dict(x=-45,flick='ollie'),dict(x=-30.5,flick='ollie')],
         camera=('dolly',(-4,-4,1.1),88,.45)),
    dict(name='bowl', start=(14.7,-10), heading=0, seconds=8, needs={'air':True},
         events=[(0,{'push':True}),(.6,{})], pump=True,
         camera=('fixed',(35,-19,1.3),82,.45)),
    dict(name='east_air', start=(53,27), heading=0, seconds=8, needs={'air':True,'grab':True},grab_air=True,
         events=[(0,{'push':True}),(4.5,{}),(5.,{'grab_left':True}),(6.1,{})],
         camera=('fixed',(59,19,1.2),82,.6)),
    dict(name='mini', start=(-23, -18), heading=180, seconds=10,needs={'air':True,'grab':True},grab_air=True,
         events=[(0, {'push': True}), (3.5, {}), (4.2, {'grab_left': True}), (5.2, {})],
         camera=('fixed', (-22, -27, 1.1), 80, .6)),
]
if ONLY:
    SHOTS = [s for s in SHOTS if s['name'] in ONLY]
for shot in SHOTS:
    shot['seconds']=globals().get('DURATIONS',{}).get(shot['name'],shot['seconds'])
assert SHOTS, 'No shots selected'
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
cm = unreal.GameplayStatics.get_player_camera_manager(L.game_world(), 0)
pawn = L.player()
deck = next(c for c in pawn.get_components_by_class(unreal.StaticMeshComponent) if c.get_name()=='SkateDeck')
SETTLE = 90
st = dict(i=-1, frame=0, sim=0, film=0, timeline=[], triggers=[], states=[],
          loops=[], cameras=[], marks=[], last_camera=None)


def expand(events):
    result = []
    for when, value in events:
        if isinstance(value, tuple) and value[0] == 'flick':
            left = value[2] if len(value) > 2 else (0, 0)
            load = value[3] if len(value) > 3 else .22
            points = live.FLICKS[value[1]]
            result.append((when, {'right': points[0], 'left': left}))
            t = when + load
            for point in points[1:]:
                result.append((t, {'right': point, 'left': left}))
                t += 1 / 30
            result.append((t, {}))
        else:
            result.append((when, dict(value)))
    return sorted(result, key=lambda item: item[0])


def where():
    p = pawn.get_actor_location()
    origin = live.park.ue(0, 0)
    return ((p.x-origin.x)/100, -(p.y-origin.y)/100, (p.z-origin.z)/100)


def view(shot):
    cam = shot['camera']
    if cam[0] == 'chase':
        if st['last_camera'] != 'chase': MV.restore_player_camera()
        L.hold_camera(.3)
        pc.set_control_rotation(unreal.Rotator(0, cam[1], -cam[2]))
        st['last_camera'] = 'chase'
    elif cam[0] == 'sweep':
        start,end,target,fov=cam[1:]
        t=max(0.,min(1.,(st['frame']-SETTLE)/60/shot['seconds']))
        t=t*t*(3-2*t)
        pos=tuple(a+(b-a)*t for a,b in zip(start,end))
        MV.review_camera(live.park.ue(*pos),live.park.ue(*target),fov)
        st['last_camera']='fixed'
    else:
        pos, fov, up = cam[1:]
        x, y, z = where()
        if cam[0] == 'dolly': pos = (x+pos[0], y+pos[1], z+pos[2])
        MV.review_camera(live.park.ue(*pos), live.park.ue(x, y, z + up), fov)
        st['last_camera'] = 'fixed'


def begin(i):
    shot = SHOTS[i]
    live.skate_input()
    live.park.place(*shot['start'], shot['heading'])
    st.update(i=i, frame=0, timeline=expand(shot['events']),
              triggers=[dict(t, fired=False) for t in shot.get('triggers', [])])
    st['marks'].append(dict(shot=shot['name'], film_frame=st['film'], sim_frame=st['sim'], needs=shot.get('needs',{})))


def finish():
    live.stop('pier_part')
    live.skate_release()
    L.fixed_step(0)
    L.film_hud(False)
    MV.restore_player_camera()
    n = L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    with open(os.path.join(OUT, 'states.json'), 'w') as f: json.dump(st['states'], f)
    with open(os.path.join(OUT, 'camera.csv'), 'w') as f:
        f.write('frame,x,y,z,yaw\n' + '\n'.join(st['cameras']) + '\n')
    with open(os.path.join(OUT, 'loops.csv'), 'w') as f: f.write('\n'.join(st['loops']) + '\n')
    with open(os.path.join(OUT, 'done.json'), 'w') as f:
        json.dump(dict(film_frames=st['film'], sim_frames=st['sim'], fps_sim=60,
                       fps_film=30, sounds=n, shots=st['marks'], filmed=FILM,
                       frame_extension='png'), f, indent=2)
    print('PIER PART DONE', OUT)


def run(dt):
    if st.get('pending'):
        st['pending']=False
        # Give the last requested viewport capture a frame to finish before
        # moving the rider or restoring the camera for the next shot.
        if st['i']+1<len(SHOTS): begin(st['i']+1)
        else: finish()
        return
    if st['i'] < 0: begin(0)
    shot = SHOTS[st['i']]
    frame = st['frame']; st['frame'] += 1
    view(shot)
    if frame < SETTLE:
        live.skate_input()
        L.audio_frame(-1000000)
        return
    t = (frame - SETTLE) / 60
    x, y, z = where()
    raw = L.skate_state()
    mode=raw.split('mode=')[1].split()[0]
    for trigger in st['triggers']:
        if 'distance' in trigger:
            a=math.radians(shot['heading']); sx,sy=shot['start']
            crossed=(x-sx)*math.cos(a)+(y-sy)*math.sin(a)>=trigger['distance']
        else:
            crossed = x >= trigger['x'] if shot['heading'] == 0 else x <= trigger['x']
        if not trigger['fired'] and crossed:
            trigger['fired'] = True
            st['timeline'] = sorted(st['timeline'] + expand([(t, ('flick', trigger['flick']) if 'flick' in trigger else trigger['inputs'])]), key=lambda e: e[0])
    inputs = {}
    for when, value in st['timeline']:
        if when <= t: inputs = dict(value)
    if shot.get('speed_cap') and inputs.get('push'):
        speed=float(raw.split('speed=')[1].split()[0])/100
        inputs['push']=speed<shot['speed_cap']
    if 'line_y' in shot and mode=='1':
        v=pawn.get_velocity()
        if v.x>100:
            direction=math.atan2(-v.y,v.x)
            desired=math.atan2(shot['line_y']-y,5.)
            error=(desired-direction+math.pi)%math.tau-math.pi
            inputs['left']=(max(-.35,min(.35,-error/.3)),0)
    if mode=='1' and any(a<=x<=b for a,b in shot.get('manual_ranges',[])) and not inputs.get('right'):
        inputs['right']=(0,-.5)
    if shot.get('pump'):
        h=(deck.get_world_location().z-live.park.ue(0,0).z)/100
        v=pawn.get_velocity()
        inputs['grab_right']=mode=='1' and h<1.25 and v.x>0
        if mode=='2' and v.z>0: inputs['grab_left']=True
    if shot.get('grab_air') and mode=='2': inputs['grab_left']=True
    if 'brake_x' in shot and x>=shot['brake_x']: inputs={'brake':True}
    live.skate_input(**inputs)
    raw = L.skate_state()
    st['states'].append(dict(shot=shot['name'], frame=st['sim'], t=round(t, 4),
                             x=round(x, 4), y=round(y, 4), z=round(z, 4), inputs=inputs, state=raw))
    L.audio_frame(st['sim'])
    st['loops'].append(L.skate_loops().strip())
    if st['sim'] % 2 == 0:
        if FILM:
            path = os.path.join(OUT, 'frame_%05d.png' % st['film'])
            # Capture the viewport render target; SHOWUI would capture the desktop's
            # Slate surface and fails on its separate offscreen scene target.
            unreal.SystemLibrary.execute_console_command(L.game_world(), 'Shot filename="' + path + '" -nosuffix')
        p = cm.get_camera_location(); r = cm.get_camera_rotation()
        st['cameras'].append('%d,%.1f,%.1f,%.1f,%.2f' % (st['film'], p.x, p.y, p.z, r.yaw))
        st['film'] += 1
    st['sim'] += 1
    if frame-SETTLE+1 >= round(shot['seconds']*60) or ('end_x' in shot and x>=shot['end_x']):
        st['pending']=True


live.stop('rec'); live.stop('skate_script')
L.skate_goofy(False)
L.film_hud(True)
L.fixed_step(60)
L.audio_log('start')
live.behave('pier_part', run)
print('PIER PART STARTED', OUT, [s['name'] for s in SHOTS], 'film=' + str(FILM))
