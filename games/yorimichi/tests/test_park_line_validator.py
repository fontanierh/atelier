"""Small analytic checks; native Session proof is an explicit separate command."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from park_line_geometry import LineWorld, Path2D
from park_line_metrics import analyze
from validate_park_lines import validate_speeds
from park_line_controller import LineFollower
from park_line_gaps import validate_gap_specs


def test_profile_lane_keeps_endpoints_and_gap(tmp_path):
    world = LineWorld(dict(path=[[0,0],[0,100]], sections=[
        dict(id='takeoff',role='takeoff',start_m=0,profile=dict(y=0,parts=[['line',5],['arc',10,30]])),
        dict(id='land',role='landing',start_m=40,knots=[[0,2,-20],[20,0,0]])]), tmp_path)
    assert np.all(world.normal[:,1]>0)
    assert world.support([0,.2,2])['surface']=='takeoff'
    assert world.support([0,10,25],drop=20) is None
    assert world.support([0,2.2,40])['surface']=='land'
    assert np.isclose(world.triangles[:,:,2].max(),60)
    assert np.allclose(world.spawn()[0],[0,.05,1])


def test_path_projection_and_heading():
    path = Path2D([[0,0],[10,0],[10,10]])
    s, lateral = path.project(np.array([[3,0,2],[12,0,7]]))
    assert np.allclose(s,[3,17]) and np.allclose(lateral,[2,2])
    p,d = path.at(12)
    assert np.allclose(p,[10,2]) and np.allclose(d,[0,1])


def test_triangle_surface_tags(tmp_path):
    world=LineWorld(dict(path=[[0,0],[0,2]],triangles=[[[0,0,0],[0,0,2],[2,0,0]]],
                        surface_regions=[dict(id='floor',role='runout',faces=[0])],spawn=[.2,.05,.2]),tmp_path)
    assert world.support([.2,.1,.2])['role']=='runout'


class FixtureWorld:
    def __init__(self, role='landing', width=80):
        self.spec={'finish_s_m':35,'acceptance':{'landing_recovery_s':.3}}
        self.path=Path2D([[0,0],[0,100]])
        self.width=80;self.design_width=width;self.sections={}
        self.finish_m=35
        self.role=role
    def support(self,p):
        if p[2]<5:
            return dict(surface='takeoff',role='takeoff',normal=[0,1,0])
        angle=np.radians(20 if self.role=='landing' else 0)
        return dict(surface='landing',role=self.role,normal=[0,float(np.cos(angle)),float(np.sin(angle))])


def flight_rows():
    rows=[]
    for i in range(80):
        ground=i<10 or i>=50
        # 0.67s artificial air, 32m horizontal; incoming slope matches a -20 degree landing.
        z=float(i*.8)
        velocity=[0,-20*np.tan(np.radians(20)) if i>=40 else 3,20]
        rows.append(dict(time_s=(i+1)/60,position=[0,1,z],velocity=velocity,
                         state='PhysicsGround' if ground else 'PhysicsAir',buttons=0))
    return rows


def test_verified_landing_passes_and_flat_landing_fails():
    result=analyze(flight_rows(),FixtureWorld())
    assert result['passed'],result['failures']
    assert result['airs'][0]['huge_air_pass']
    result=analyze(flight_rows(),FixtureWorld('runout'))
    assert not result['passed']
    assert 'landing is not an intended sloped transition' in result['airs'][0]['failures']


def test_unfinished_air_and_missing_recovery_fail():
    assert not analyze(flight_rows()[:45],FixtureWorld())['passed']
    result=analyze(flight_rows()[:52],FixtureWorld())
    assert not result['passed']
    assert 'insufficient observations after landing' in result['airs'][0]['failures']


def test_bail_and_diagnostic_width_do_not_pass():
    rows=flight_rows();rows[55]['state']='Wipeout'
    assert not analyze(rows,FixtureWorld())['passed']
    rows=flight_rows()
    for r in rows:r['position'][0]=8
    result=analyze(rows,FixtureWorld(width=10))
    assert 'rider left the designed rideable corridor' in result['failures']


def test_gravity_corrected_bump_and_brake_exclusion():
    rows=[dict(time_s=(i+1)/60,position=[0,0,i*.15],velocity=[0,0,10 if i<40 else 6],
               state='PhysicsGround',buttons=0) for i in range(80)]
    result=analyze(rows,FixtureWorld())
    assert result['bump_candidates'] and result['bump_candidates'][0]['gravity_corrected_loss_mps']>=4
    for r in rows:r['buttons']=0x2000
    assert not analyze(rows,FixtureWorld())['bump_candidates']


def test_brief_lip_support_gap_uses_recent_ground_but_unknown_landing_fails():
    world=FixtureWorld();base=world.support
    world.support=lambda p:None if 6.4<=p[2]<8 else base(p)
    result=analyze(flight_rows(),world)
    assert result['passed']
    assert result['unknown_ground_support_frames']==2
    assert result['airs'][0]['takeoff_support_frame']==7
    world.support=lambda p:None if p[2]>=39 else base(p)
    result=analyze(flight_rows(),world)
    assert not result['passed']
    assert 'landing support unknown' in result['airs'][0]['failures']


def test_triangle_mesh_finish_defaults_to_path_end(tmp_path):
    world=LineWorld(dict(path=[[0,0],[0,20]],triangles=[[[0,0,0],[0,0,20],[20,0,0]]],
                        surface_regions=[dict(id='floor',role='runout',faces=[0])],spawn=[.2,.05,.2]),tmp_path)
    assert world.finish_m==18


def test_empty_or_invalid_sweep_cannot_pass_without_trials():
    for speeds in ([],[-1],[float('nan')],[float('inf')]):
        with pytest.raises(ValueError):
            validate_speeds(speeds)
    assert validate_speeds([0,10])==[0,10]


def test_follower_corrects_cross_track_and_rotates_with_path():
    first=LineFollower(Path2D([[0,0],[0,100]]),{})
    rotated=LineFollower(Path2D([[0,0],[100,0]]),{})
    a=dict(state='PhysicsGround',position=[2,0,10],velocity=[0,0,12])
    b=dict(state='PhysicsGround',position=[10,0,-2],velocity=[12,0,0])
    assert first.steering(a)>0
    assert first.previous==pytest.approx(rotated.steering(b)/32767,abs=1/32767)


def test_follower_never_steers_in_air_or_offboard():
    follower=LineFollower(Path2D([[0,0],[0,100]]),{})
    row=dict(state='PhysicsGround',position=[2,0,10],velocity=[0,0,12])
    assert follower.steering(row)>0
    for state in ('PhysicsAir','WipeoutAir','BipedGround','Teleporting'):
        assert follower.steering({**row,'state':state})==0
        assert follower.previous==0
    assert follower.steering({**row,'velocity':[0,0,0]})==0


def test_follower_input_is_bounded_and_invalid_settings_rejected():
    path=Path2D([[0,0],[0,100]])
    follower=LineFollower(path,dict(max_stick=.4,smoothing_seconds=.001))
    value=follower.steering(dict(state='PhysicsGround',position=[30,0,10],velocity=[12,0,0]))
    assert abs(value)<=round(.4*32767)
    assert follower.report()['saturated_frames']==1
    for config in ({'gain':0},{'max_stick':2},{'lookahead_m':float('nan')},{'mode':'teleport'},{'unknown':1}):
        with pytest.raises(ValueError):
            LineFollower(path,config)


def paired_flights():
    world=FixtureWorld()
    world.path=Path2D([[0,0],[0,200]])
    world.finish_m=95
    world.sections={name:dict(role=role) for name,role in
                    [('launch1','takeoff'),('land1','landing'),('launch2','takeoff'),('land2','landing')]}
    world.spec['required_airs']=[
        dict(id='hero',takeoff='launch1',landing='land1',knuckle_s_m=36,knuckle_y_m=-2,
             landing_end_s_m=60,min_knuckle_margin_m=3,min_air_m=25),
        dict(id='secondary',takeoff='launch2',landing='land2',knuckle_s_m=86,
             landing_end_s_m=100,min_knuckle_margin_m=3)]
    def support(p):
        name='launch1' if p[2]<10 else 'land1' if p[2]<65 else 'launch2' if p[2]<77 else 'land2'
        return dict(surface=name,role=world.sections[name]['role'],
                    normal=[0,float(np.cos(np.radians(20))),float(np.sin(np.radians(20)))])
    world.support=support
    rows=flight_rows()
    for row in flight_rows():
        rows.append({**row,'time_s':row['time_s']+80/60,
                     'position':[0,1,70+row['position'][2]/2]})
    return rows,world


def test_secondary_gap_can_be_shorter_while_hero_remains_required():
    rows,world=paired_flights()
    report=analyze(rows,world)
    assert report['passed'],report['failures']
    assert [a['huge_air_pass'] for a in report['airs']]==[True,False]
    assert all(g['passed'] for g in report['gap_checks'])
    assert report['gap_checks'][0]['vertical_clearance_at_knuckle_m']==pytest.approx(3)
    assert report['gap_checks'][1]['touchdown_margin_m']==pytest.approx(4)
    world.spec.pop('required_airs')
    assert not analyze(rows,world)['passed']  # legacy required_takeoffs still demand huge airs
    rows,world=paired_flights()
    world.spec['required_airs']=world.spec['required_airs'][1:]
    world.spec['required_takeoffs']=['launch2']
    for row in rows[:80]:row['state']='PhysicsGround'
    assert 'no completed qualifying huge air' in analyze(rows,world)['failures']


@pytest.mark.parametrize('change,expected',[
    ('wrong_receiver','named receiver'),('close_knuckle','too close'),
    ('overshoot','beyond the intended'),('speed','takeoff speed'),
    ('missing','no observed flight'),('order','declaration order'),
    ('bail','safety checks')])
def test_gap_gate_does_not_hide_bad_secondary_with_successful_hero(change,expected):
    rows,world=paired_flights()
    spec=world.spec['required_airs'][1]
    if change=='wrong_receiver':spec['landing']='land1'
    elif change=='close_knuckle':spec['knuckle_s_m']=88
    elif change=='overshoot':spec['landing_end_s_m']=89
    elif change=='speed':spec['min_takeoff_speed_mps']=100
    elif change=='missing':
        for row in rows[80:]:row['state']='PhysicsGround'
    elif change=='order':world.spec['required_airs'].reverse()
    elif change=='bail':rows[135]['state']='WipeoutGround'
    report=analyze(rows,world)
    assert not report['passed']
    assert report['airs'][0]['huge_air_pass']
    assert any(expected in f for g in report['gap_checks'] for f in g['failures'])


@pytest.mark.parametrize('key,value',[
    ('knuckle_s_m',float('nan')),('landing_end_s_m',201),('min_air_m',-1),
    ('knuckle_y_m',float('inf')),('takeoff','missing'),('landing','launch1'),('typo',3)])
def test_invalid_gap_requirement_fails_closed(key,value):
    _,world=paired_flights();world.spec['required_airs'][0][key]=value
    with pytest.raises(ValueError):validate_gap_specs(world)
