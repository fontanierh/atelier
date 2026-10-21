"""Walk both terminal routes and ride both directions on one fitted ropeway.

Run through the live bridge with LINE and a new OUT directory. Only initial
station setup teleports. Every boarding/alighting route is driven on imported
collision, with stalls and lost riders refusing the evidence.
"""
import json
import math
import os
import time
import unreal

os.makedirs(OUT,exist_ok=False)
DATA=json.load(open(os.path.join(os.environ.get('ATELIER_BUILD_ROOT',os.path.join(live.ROOT,'build')),'yorimichi/gondola/runtime.json')))
LINE=globals().get('LINE','L1')
SPEC=next(row for row in DATA['lines'] if row['id']==LINE)
STATIONS={row['id']:row for row in DATA['stations']}
FIRST,LAST=SPEC['stations']
G=unreal.GondolaLive
WORLD=live.L.game_world()
PC=unreal.GameplayStatics.get_player_controller(WORLD,0)
PAWN=unreal.GameplayStatics.get_player_pawn(WORLD,0)
HALF=PAWN.get_component_by_class(unreal.CapsuleComponent).get_scaled_capsule_half_height()
MOVEMENT=PAWN.get_component_by_class(unreal.CharacterMovementComponent)
START=time.monotonic()
S=dict(stage='',elapsed=0.,stage_time=0.,route=[],index=0,rows=[],marks=[],photos=0,next_photo=0.,next_record=0.,still=0.,last=None,cabin=-1,direction=0,sailed=False,walk_sample=None,walk_stats={})


def state():return json.loads(G.gondola_state())


def aboard(st):
    return next((row['cabin'] for row in st['riders'] if row['name']==PAWN.get_name()),-1)


def mark(stage):
    S.update(stage=stage,stage_time=0.,still=0.,last=None)
    S['marks'].append(dict(stage=stage,elapsed=S['elapsed'],state=state()))
    print('GONDOLA QA',LINE,stage,round(S['elapsed'],1),flush=True)


def route(points,stage):
    S.update(route=points,index=0,walk_sample=None,walk_interval=None)
    mark(stage)


def finish(error=None):
    live.drive(0,0);live.stop('gondola_roundtrip')
    json.dump(dict(passed=error is None,error=error,line=LINE,elapsed=S['elapsed'],wall_seconds=time.monotonic()-START,
                   marks=S['marks'],rows=S['rows'],state=state(),walking_clock='native world seconds',
                   walking=[dict(row,average_speed_m_s=row['plan_m']/row['seconds'],
                                 average_3d_speed_m_s=row['distance_m']/row['seconds']) for row in S['walk_stats'].values()]),open(os.path.join(OUT,'completed.json'),'w'),indent=1)
    print('GONDOLA QA','FAILED '+str(error) if error else 'PASSED',LINE,flush=True)


def record_walk(feet):
    now=unreal.GameplayStatics.get_time_seconds(WORLD)
    previous=S['walk_sample']
    if previous is None or previous['stage']!=S['stage']:return
    seconds=now-previous['world_s']
    if seconds<=0:return
    before=previous['feet_cm'];plan=math.hypot(feet[0]-before[0],feet[1]-before[1])/100
    distance=math.dist(before,feet)/100;speed=plan/seconds;speed_3d=distance/seconds
    key=(previous['stage'],previous['index'])
    S['walk_interval']=dict(world_seconds=seconds,displacement_cm=100*distance,
        speed_m_s=speed,speed_3d_m_s=speed_3d)
    row=S['walk_stats'].setdefault(key,dict(stage=key[0],index=key[1],seconds=0.,plan_m=0.,distance_m=0.,
        min_speed_m_s=speed,max_speed_m_s=speed,min_3d_speed_m_s=speed_3d,max_3d_speed_m_s=speed_3d,
        samples=0,forward=previous['forward'],
        walk_cap_min_m_s=previous['walk_cap_m_s'],walk_cap_max_m_s=previous['walk_cap_m_s'],first_cm=before,last_cm=feet))
    row['seconds']+=seconds;row['plan_m']+=plan;row['distance_m']+=distance;row['samples']+=1
    row['min_speed_m_s']=min(row['min_speed_m_s'],speed);row['max_speed_m_s']=max(row['max_speed_m_s'],speed)
    row['min_3d_speed_m_s']=min(row['min_3d_speed_m_s'],speed_3d)
    row['max_3d_speed_m_s']=max(row['max_3d_speed_m_s'],speed_3d)
    row['walk_cap_min_m_s']=min(row['walk_cap_min_m_s'],previous['walk_cap_m_s'])
    row['walk_cap_max_m_s']=max(row['walk_cap_max_m_s'],previous['walk_cap_m_s']);row['last_cm']=feet


def drive(dt):
    """@cc [owner:fontanierh,label:correctness] gondola-qa-normal-walk
    Traversal MUST request full normal walk input without scaling it down for dense waypoints,
    changing movement settings or moving the pawn directly. Per-waypoint speeds MUST use native
    world time and actual feet displacement, preserving zero/minimum samples. The eight-second
    no-motion and 240-second route refusals MUST remain independent and explicit.
    """
    loc=PAWN.get_actor_location();feet=(loc.x,loc.y,loc.z-HALF)
    record_walk(feet)
    while S['index']<len(S['route']):
        target=S['route'][S['index']];dx,dy,dz=[a-b for a,b in zip(target,feet)]
        if math.hypot(dx,dy)>.12*100 or abs(dz)>60:break
        S['index']+=1;S['still']=0.
    if S['index']==len(S['route']):S['walk_sample']=None;live.drive(0,0);return True
    PC.set_control_rotation(unreal.Rotator(roll=0.,pitch=-8.,yaw=math.degrees(math.atan2(dy,dx))))
    live.drive(forward=1.,right=0.,gait='walk')
    displacement=math.dist(S['last'],feet) if S['last'] else None
    S['still']=S['still']+dt if displacement is not None and displacement<.5 else 0.
    velocity=PAWN.get_velocity()
    S['walk_sample']=dict(stage=S['stage'],index=S['index'],feet_cm=feet,target_cm=target,
        error_cm=(dx,dy,dz),velocity_cm_s=(velocity.x,velocity.y,velocity.z),
        movement_mode=str(MOVEMENT.movement_mode),world_s=unreal.GameplayStatics.get_time_seconds(WORLD),
        host_monotonic_s=time.monotonic(),callback_seconds=dt,displacement_cm=displacement,
        still_seconds=S['still'],interval=S.get('walk_interval'),forward=1.,right=0.,gait='walk',
        walk_cap_m_s=float(MOVEMENT.max_walk_speed)/100)
    S['last']=feet
    if S['still']>8:raise RuntimeError('walking stalled '+S['stage']+' waypoint '+str(S['index']))
    if S['stage_time']>240:raise RuntimeError('walking route deadline '+S['stage']+' waypoint '+str(S['index']))
    return False


def approach(station):
    points=STATIONS[station]['boarding_cm']['1']
    end=points[-1]
    split=max(i for i,p in enumerate(points) if math.dist(p[:2],end[:2])>150)
    S['board_tail']=points[split+1:]
    route(points[:split+1],'approach_'+station)


def boarding_candidate(st,station):
    """@cc [owner:fontanierh,label:correctness] gondola-qa-open-dwell
    Boarding MUST use the normal service clock and a fully open outbound cabin
    with at least nine seconds of stationary dwell remaining. A late opening
    sample MUST NOT start an ordinary walking route through a closing door.
    """
    clock=SPEC['clock'];cycle=clock['cycle_s']
    first=0
    for line in DATA['lines']:
        if line['id']==LINE:break
        first+=line['cabins']
    for cabin in st['cabins']:
        if cabin['line']!=LINE or cabin['station']!=station or cabin['side']!=1 or cabin['door']<=.999:continue
        index=cabin['index']-first
        if not 0<=index<SPEC['cabins']:raise RuntimeError('invalid cabin clock index')
        phase=(st['time']+cycle*index/SPEC['cabins'])%cycle
        if any(stop['station']==station and stop['side']==1 and stop['start']<=phase<stop['end']
               and stop['end']-phase>=9. for stop in clock['stops']):
            return cabin
    return None


def step(dt):
    S['elapsed']+=dt;S['stage_time']+=dt
    if time.monotonic()-START>2100:raise RuntimeError('ropeway round trip exceeded 35 minutes')
    st=state();current=aboard(st)
    if S['elapsed']>=S['next_record']:
        S['next_record']=S['elapsed']+1
        S['rows'].append(dict(elapsed=round(S['elapsed'],2),stage=S['stage'],index=S['index'],state=st,motion=S.get('walk_sample')))
        json.dump(dict(stage=S['stage'],elapsed=S['elapsed'],index=S['index'],state=st),open(os.path.join(OUT,'progress.json'),'w'))
    if S['elapsed']>=S['next_photo']:
        S['next_photo']=S['elapsed']+20
        live.L.screenshot(os.path.join(OUT,'rider_%04d.jpg'%S['photos']));S['photos']+=1
    station=FIRST if S['direction']==0 else LAST
    destination=LAST if S['direction']==0 else FIRST
    if S['stage'].startswith('approach_'):
        if drive(dt):mark('wait_'+station)
    elif S['stage'].startswith('wait_'):
        live.drive(0,0)
        ready=boarding_candidate(st,station)
        if ready:
            S['cabin']=ready['index'];route(S['board_tail'],'boarding_'+station)
        elif S['stage_time']>240:raise RuntimeError('no outbound cabin reached '+station)
    elif S['stage'].startswith('boarding_'):
        if drive(dt):
            if current!=S['cabin']:raise RuntimeError('boarding route did not enter expected cabin')
            S['sailed']=False;mark('ride_'+destination)
    elif S['stage'].startswith('ride_'):
        live.drive(0,0)
        if current!=S['cabin']:raise RuntimeError('rider lost from moving cabin')
        cabin=next(c for c in st['cabins'] if c['index']==current)
        if cabin['floor_tilt_deg']>.01:raise RuntimeError('cabin floor tilted')
        S['sailed']|=cabin['speed_m_s']>1.
        if S['sailed'] and cabin['station']==destination and cabin['side']==-1 and cabin['door']>.999:
            route(list(reversed(STATIONS[destination]['boarding_cm']['-1'])),'alight_'+destination)
    elif S['stage'].startswith('alight_'):
        if drive(dt):
            if current!=-1:raise RuntimeError('still aboard at ground end of access')
            if S['direction']==0:
                S['direction']=1;approach(LAST)
            else:mark('complete');finish()


def run(dt):
    try:step(dt)
    except Exception as error:finish(repr(error));raise


assert G.gondola_go(FIRST),'initial station setup failed'
approach(FIRST)
live.behave('gondola_roundtrip',run)
print('GONDOLA QA running',LINE,OUT,flush=True)
