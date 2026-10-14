"""Small analytic checks; native Session proof is an explicit separate command."""
from pathlib import Path
import sys
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from park_line_geometry import LineWorld, Path2D
from park_line_metrics import analyze
from validate_park_lines import validate_speeds


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
