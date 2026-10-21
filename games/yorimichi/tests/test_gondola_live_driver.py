"""Run the physical driver's actual wait branch at early and closing dwell phases."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


def walking_driver(points):
    path=Path(__file__).resolve().parents[1]/'scenarios/gondola_roundtrip_live.py'
    functions=[node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and
               node.name in ('record_walk','drive','route')]
    position=[0.,0.,0.];clock=[0.];commands=[]
    S=dict(stage='approach_a',stage_time=0.,route=points,index=0,still=0.,last=None,walk_sample=None,walk_stats={})
    movement=SimpleNamespace(max_walk_speed=100.,movement_mode="Walking")
    namespace={'math':math,'S':S,'HALF':0.,'WORLD':object(),'MOVEMENT':movement,
        'PAWN':SimpleNamespace(get_actor_location=lambda:SimpleNamespace(x=position[0],y=position[1],z=position[2]),
            get_velocity=lambda:SimpleNamespace(x=100.,y=0.,z=0.)),
        'time':SimpleNamespace(monotonic=lambda:clock[0]+20.),
        'PC':SimpleNamespace(set_control_rotation=lambda value:None),
        'unreal':SimpleNamespace(Rotator=lambda **kwargs:kwargs,
            GameplayStatics=SimpleNamespace(get_time_seconds=lambda world:clock[0])),
        'live':SimpleNamespace(drive=lambda *args,**kwargs:commands.append((args,kwargs))),
        'mark':lambda stage:S.update(stage=stage,stage_time=0.)}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),namespace)
    return namespace,position,clock,commands,movement


@pytest.mark.parametrize('distance',[13.,20.,60.,100.,200.])
def test_actual_walk_driver_requests_normal_gait_even_at_dense_waypoints(distance):
    driver,_,_,commands,movement=walking_driver([[distance,0.,0.]])
    assert driver['drive'](1/60) is False
    assert commands[-1]==((),dict(forward=1.,right=0.,gait='walk'))
    assert movement.max_walk_speed==100.


@pytest.mark.parametrize('still,stage_time,message',[(8.01,0.,'walking stalled'),(0.,240.01,'walking route deadline')])
def test_actual_walk_driver_retains_both_failure_limits(still,stage_time,message):
    driver,_,_,_,_=walking_driver([[100.,0.,0.]])
    driver['S'].update(still=still,stage_time=stage_time,last=(0.,0.,0.))
    with pytest.raises(RuntimeError,match=message):driver['drive'](1/60)


def test_walking_measurements_use_world_clock_and_retain_zero_speed():
    driver,position,clock,_,_=walking_driver([[100.,0.,0.]])
    driver['drive'](.5)
    position[0]=15.;clock[0]=.1
    driver['drive'](.5)
    clock[0]=.2
    driver['drive'](.5)
    row=driver['S']['walk_stats'][('approach_a',0)]
    assert row['seconds']==pytest.approx(.2)
    assert row['plan_m']==pytest.approx(.15)
    assert row['plan_m']/row['seconds']==pytest.approx(.75)
    assert row['min_speed_m_s']==0.
    assert row['max_speed_m_s']==pytest.approx(1.5)
    assert row['walk_cap_min_m_s']==row['walk_cap_max_m_s']==1.
    assert row['min_3d_speed_m_s']==0. and row['samples']==2
    sample=driver['S']['walk_sample']
    assert sample['callback_seconds']==.5 and sample['interval']['world_seconds']==pytest.approx(.1)
    assert sample['interval']['displacement_cm']==0. and sample['still_seconds']==.5
    assert sample['error_cm']==(85.,0.,0.) and sample['velocity_cm_s']==(100.,0.,0.)
    assert sample['movement_mode']=='Walking' and sample['host_monotonic_s']==20.2


def test_walking_measurements_keep_vertical_distance_separate_from_plan_speed():
    driver,position,clock,_,_=walking_driver([[100.,0.,50.]])
    driver['drive'](1/60)
    position[:]=[30.,0.,40.];clock[0]=.5
    driver['drive'](1/60)
    row=driver['S']['walk_stats'][('approach_a',0)]
    assert row['plan_m']==pytest.approx(.3) and row['distance_m']==pytest.approx(.5)
    assert row['min_speed_m_s']==pytest.approx(.6)
    assert row['min_3d_speed_m_s']==pytest.approx(1.)


def test_walking_metrics_follow_the_commanded_waypoint_and_reset_at_new_route():
    driver,position,clock,commands,_=walking_driver([[30.,0.,0.],[60.,0.,0.]])
    driver['drive'](1/60)
    position[0]=30.;clock[0]=.2
    driver['drive'](1/60)
    position[0]=60.;clock[0]=.4
    assert driver['drive'](1/60) is True
    assert commands[-1]==((0,0),{})
    rows=driver['S']['walk_stats']
    assert rows[('approach_a',0)]['plan_m']==pytest.approx(.3)
    assert rows[('approach_a',1)]['plan_m']==pytest.approx(.3)
    driver['route']([[10000.,0.,0.]],'approach_b')
    position[0]=9900.;clock[0]=2.
    driver['drive'](1/60)
    assert ('approach_b',0) not in rows


@pytest.mark.parametrize('line_index,cabins', [(0,12),(1,12),(2,4)])
@pytest.mark.parametrize('direction', [0,1])
@pytest.mark.parametrize('elapsed,boards', [(2.,True),(9.32,False)])
def test_wait_branch_requires_open_dwell_budget(line_index,cabins,direction,elapsed,boards):
    path=Path(__file__).resolve().parents[1]/'scenarios/gondola_roundtrip_live.py'
    tree=ast.parse(path.read_text())
    functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and
               node.name in ('aboard','boarding_candidate','step')]
    data={'lines':[{'id':'L'+str(i+1),'cabins':count} for i,count in enumerate((12,12,4))]}
    spec=data['lines'][line_index];station=('a','b')[direction]
    spec['clock']={'cycle_s':400.,'stops':[{'station':station,'side':1,'start':100.,'end':112.}]}
    # Use a nonzero local cabin phase and a cycle wrap. StateJson indices span
    # all lines while each service clock offsets only that line's local index.
    local=cabins-1;first=sum(row['cabins'] for row in data['lines'][:line_index])
    state={'time':100.+elapsed-400.*local/cabins+800.,'riders':[],
           'cabins':[{'index':first+local,'line':spec['id'],'station':station,'side':1,'door':1. if boards else .999175926}]}
    stage='wait_'+station
    S={'direction':direction,'stage':stage,'stage_time':0.,'elapsed':0.,
       'next_record':float('inf'),'next_photo':float('inf'),'board_tail':[[0,0,0],[0,200,0]]}
    def route(points,name):S.update(route=points,stage=name)
    namespace={'math':math,'DATA':data,'SPEC':spec,'LINE':spec['id'],'FIRST':'a','LAST':'b','S':S,
               'PAWN':SimpleNamespace(get_name=lambda:'Rider'),'state':lambda:state,'route':route,
               'live':SimpleNamespace(drive=lambda *args,**kwargs:None),
               'time':SimpleNamespace(monotonic=lambda:0.),'START':0.}
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(path),'exec'),namespace)
    namespace['step'](1/60)
    assert S['stage']==('boarding_'+station if boards else stage)
    if boards:assert S['cabin']==first+local and S['route']==S['board_tail']
