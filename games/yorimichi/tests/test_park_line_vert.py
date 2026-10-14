"""Acceptance checks for declared same-wall vert returns, including vertical collision."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from park_line_geometry import LineWorld
from park_line_metrics import analyze
from park_line_vert import VertReturns


def vert_trial(tmp_path):
    # A vertical plane facing -z: a vertical support ray cannot identify it.
    wall = [[[-100,0,5],[-100,10,5],[100,10,5]],
            [[-100,0,5],[100,10,5],[100,0,5]]]
    spec = dict(path=[[0,0],[100,0]], triangles=wall, finish_s_m=35,
                surface_regions=[dict(id='wall',role='vert',faces=[0,1])],
                validation_mode='vert_return', required_vert_returns=[dict(
                    id='elbow',surface='wall',coping_y_m=2,max_normal_speed_mps=5)])
    world=LineWorld(spec,tmp_path)
    rows=[]
    for i in range(90):
        air=10<=i<50
        y=2.1+3*np.sin((i-10)/40*np.pi) if air else 2.1
        rows.append(dict(time_s=(i+1)/60,position=[i*.8,float(y),4.9],
                         velocity=[20,-8,.8],state='PhysicsAir' if air else 'PhysicsGround',buttons=0))
    return world,rows


def test_vertical_return_uses_nearest_collision_and_cannot_supply_route_hero(tmp_path):
    world,rows=vert_trial(tmp_path)
    assert world.support(rows[50]['position']) is None
    result=analyze(rows,world)
    assert result['passed'],result['failures']
    air=result['airs'][0]
    assert air['safe_landing_pass'] and not air['huge_air_pass']
    assert air['vert_return']['inferred_normal_speed_mps']==pytest.approx(.8)
    assert air['vert_return']['return_support']['distance_m']==pytest.approx(.1)
    world.spec['validation_mode']='route'
    assert 'no completed qualifying huge air' in analyze(rows,world)['failures']


@pytest.mark.parametrize('case,reason',[
    ('hard','normal-speed limit'),('far','nearby collision'),('bail','bail'),
    ('recovery','recovery'),('coping','coping'),('absent','absent or failed')])
def test_vert_return_does_not_conceal_failures(tmp_path,case,reason):
    world,rows=vert_trial(tmp_path)
    if case=='hard':rows[47]['velocity']=[20,-8,9]  # last frame alone looks gentle
    elif case=='far':
        for row in rows[50:]:row['position'][2]=4
    elif case=='bail':rows[60]['state']='WipeoutGround'
    elif case=='recovery':rows[60]['state']='PhysicsAir'
    elif case=='coping':world.spec['required_vert_returns'][0]['coping_y_m']=20
    elif case=='absent':
        for row in rows:row['state']='PhysicsGround'
    result=analyze(rows,world)
    assert not result['passed']
    failures=result['failures']+[f for a in result['airs'] for f in a['failures']]
    assert any(reason in f for f in failures)


def test_nearer_other_surface_cannot_be_ignored_to_claim_same_wall(tmp_path):
    world,rows=vert_trial(tmp_path)
    spec=world.spec
    # Another region lies directly on the returning root, closer than the required wall.
    spec['triangles'] += [[[35,0,4.9],[35,10,4.9],[100,10,4.9]],
                          [[35,0,4.9],[100,10,4.9],[100,0,4.9]]]
    spec['surface_regions'].append(dict(id='other',role='transition',faces=[2,3]))
    result=analyze(rows,LineWorld(spec,tmp_path))
    assert not result['passed']
    assert 'vert return lacks nearby collision on its named wall' in result['airs'][0]['failures']


def test_vert_configuration_is_explicit_and_bounded(tmp_path):
    world,_=vert_trial(tmp_path)
    world.spec['required_vert_returns'][0]['max_contact_distance_m']=3
    with pytest.raises(ValueError):VertReturns(world)
    world.spec['required_vert_returns']=[]
    with pytest.raises(ValueError):VertReturns(world)
    world.spec['validation_mode']='anything'
    with pytest.raises(ValueError):VertReturns(world)
