"""Actual triangulated access caps, connections and final-ground walkability."""
import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest
from gondola_kit_fixture import gondola_modules
from test_gondola_site_audits import helper
from test_gondola_ground import ground,plane


def functions():
    with gondola_modules('solid',pure=False):
        from gondola.support import floor_caps,cap_slope,access_walk_audit
    return floor_caps,cap_slope,access_walk_audit


def fixture():
    G=ground(city=plane('city',0.),mountain=plane('mountain',0.),trail=plane('trail',0.,(8,8,9,9)))
    tread={'poly':[[0,-1.1],[.4,-1.1],[.4,1.1],[0,1.1]],'top':0.}
    join={'poly':[[.4,-1.1],[1.2,-1.1],[1.2,1.1],[.4,1.1]],'z1':[0.,0.,0.,0.]}
    frame=(np.array([0.,-2.]),np.array([1.,0.]),np.array([0.,1.]),0.)
    return G,frame,tread,join


def audit(top=.2,*,tread=None,join=None,head=None,ground_override=None):
    G,frame,default_tread,default_join=fixture()
    G=ground_override or G
    return functions()[2](G,frame,head if head is not None else [[0,-1.2],[0,1.2]],top,[],
        [tread or default_tread],[join or default_join],np.array([1.2,0.]),np.array([1.,0.]),np.array([0.,1.]),
        step_limit=.3,tread_min=.25,walk_width=.9,last_tread=.4)


@pytest.mark.parametrize('relief,old_degrees',[(1.0745901558115066,53.3334),(2.2209,70.1902)])
def test_actual_old_twisted_caps_refused_despite_smaller_bilinear_centre_grade(relief,old_degrees):
    caps,slope,_=functions()
    surface={'poly':[[0,-1.1],[.8,-1.1],[.8,1.1],[0,1.1]],'z1':[0.,-relief,0.,0.]}
    assert slope(caps(surface))==pytest.approx(old_degrees,abs=.002)
    assert math.degrees(math.atan(relief/2/.8))<old_degrees
    with pytest.raises(ValueError,match='cap slope'):audit(join=surface)


def test_emission_and_audit_use_identical_planar_caps():
    caps,slope,_=functions();pieces=[]
    mesh=SimpleNamespace(prism=lambda poly,base,roof,*a,**k:pieces.append(np.array([[*p,roof(*p)] for p in poly])))
    surface={'poly':[[0,-1.1],[1.3,-1.1],[1.3,1.1],[0,1.1]],'z1':[0.,-1.0745901558115066,0.,0.]}
    fn=helper('emit_access_floor',{'np':np,'floor_caps':caps,'solid':SimpleNamespace(TIMBER_DARK=1,DECK=2)})
    fn(mesh,surface)
    assert np.array_equal(np.array(pieces),caps(surface))
    assert slope(np.array(pieces))==pytest.approx(39.5774014748)


def test_step_gate_measures_height_jump_not_route_waypoint_height_delta():
    proof=audit();assert proof['pass'] and proof['maximum_step_m']==.2
    assert proof['shared_edge_gap_m']==proof['ground_edge_gap_m']==0.
    with pytest.raises(ValueError,match='excessive height step'):audit(top=.301)


def test_access_head_must_connect_to_real_kit_edge():
    with pytest.raises(ValueError,match='open edge'):audit(head=[[1,-1.2],[1,1.2]])


def test_audit_refuses_open_join_even_when_both_caps_are_flat():
    _,_,_,join=fixture();join=copy.deepcopy(join)
    join['poly'][0][0]+=.01;join['poly'][3][0]+=.01
    with pytest.raises(ValueError,match='open edge'):audit(join=join)


def test_preflight_requires_complete_unrelaxed_walk_receipt():
    from gondola.validation import validate_access_walk
    _,_,tread,join=fixture()
    data=dict(walk_proof=audit(),surfaces=[tread,join],risers=1,riser=.2,run_m=1.2,join_m=.8,tread=.32,flights=[1],landing_m=1.2)
    validate_access_walk(data)
    for key in list(data['walk_proof']):
        changed=copy.deepcopy(data);del changed['walk_proof'][key]
        with pytest.raises(ValueError):validate_access_walk(changed)
    for key,value in [('maximum_slope_deg',40.01),('maximum_step_m',.31),('shared_edge_gap_m',.001),('slope_limit_deg',45.)]:
        changed=copy.deepcopy(data);changed['walk_proof'][key]=value
        with pytest.raises(ValueError):validate_access_walk(changed)


def test_return_flight_has_three_level_rests_and_uses_exact_head_edge():
    from contextlib import nullcontext
    class Sink:
        def __init__(self,*a):pass
        def tagged(self,*a):return nullcontext()
        def at(self,*a):return nullcontext()
        def prism(self,*a,**k):pass
        def box(self,*a,**k):pass
    ns={'np':np,'math':math,'solid':SimpleNamespace(Mesh=Sink,TIMBER=1,TIMBER_DARK=2,DECK=3),
        'STATIONS':{'fixture':{'access_turn_deg':180.,'access_fit':{
            'risers':52,'tread_m':.28,'run_m':21.38,'join_m':3.2,'flights':[13]*4,'landing_m':1.2}}},
        'Station':lambda *a:SimpleNamespace(seats=[],proxies=[]),'P':SimpleNamespace(DEFAULTS={},derived=lambda p:{}),
        'world_xy':lambda p,f:np.asarray(p),'ground_edge':lambda *a:(np.array([-1.1,1.1]),np.zeros(2)),
        'railing':lambda *a,**k:None,'timber_support':lambda *a:None,'floor_intrusion':lambda *a:0.}
    # Deliberately rounded/inconsistent hint: the exact head edge owns direction.
    layout={'access':[{'edge':[[0,-1.2],[0,1.2]],'point':[-.5,.001],'z':13.832}]}
    _,access=helper('access_stair',ns)('fixture',layout,SimpleNamespace(contact=lambda p:(np.zeros(len(p)),None)),(None,None,None,0))
    rests=[(i,p) for i,p in enumerate(access['surfaces']) if p.get('rest_landing')]
    assert len(rests)==3 and access['risers']==52 and access['flights']==[13]*4
    for index,landing in rests:
        assert landing['top']==access['surfaces'][index-1]['top']
        assert landing['top']-access['surfaces'][index+1]['top']==pytest.approx(.266)
        assert np.ptp(np.asarray(landing['poly'])[:,0])==pytest.approx(1.2)
    assert np.asarray(access['surfaces'][0]['entry'])[:,0].tolist()==[0.,0.]
    assert access['route'][-1][:2]==pytest.approx([-21.38,2.6])
    assert access['walk_proof']['pass']


def headroom_fixture(obstacle):
    from gondola.interactions import access_headroom
    floor={'poly':[[-1,-1],[2,-1],[2,2],[-1,2]],'top':0.}
    # Real tagged part filtering: the walking slab is exempt; an untagged pole is not.
    floor_tri=np.array([[-1,-1,0],[2,-1,0],[2,2,0]])
    vertices=np.concatenate([floor_tri,np.asarray(obstacle)])
    mesh=SimpleNamespace(verts=vertices,faces=[[0,1,2],[3,4,5]],parts=[(0,1,'access_floor'),(1,2,'post')])
    distant={'name':'distant','poly':[[8,8],[9,8],[9,9],[8,9]],'z0':[0.]*4,'z1':[1.]*4}
    with gondola_modules('solid',pure=False):
        return access_headroom({'route':[[0,0,0],[1,0,0],[1,1,0]],'surfaces':[floor]},[mesh],{'obstacles':[distant]},fixture()[0],fixture()[1])


def test_cross_mesh_headroom_catches_turn_corner_and_retains_rails_posts():
    assert headroom_fixture([[1.8,1.8,.5],[1.9,1.8,.5],[1.8,1.9,1.5]])['pass']
    # Outside both uncapped rectangles, inside the capsule's corner footprint.
    with pytest.raises(ValueError,match='headroom'):
        headroom_fixture([[1.3,-.3,.5],[1.35,-.3,.5],[1.3,-.3,1.5]])


def test_pure_preflight_refuses_missing_headroom_and_rest_plan():
    from gondola.validation import validate_access_headroom,validate_access_walk
    proof=headroom_fixture([[1.8,1.8,.5],[1.9,1.8,.5],[1.8,1.9,1.5]])
    validate_access_headroom({'headroom_proof':proof})
    for key in proof:
        changed=copy.deepcopy(proof);del changed[key]
        with pytest.raises(ValueError):validate_access_headroom({'headroom_proof':changed})
    _,_,tread,join=fixture()
    row=dict(walk_proof=audit(),surfaces=[tread,join],risers=1,riser=.2,run_m=1.2,join_m=.8,tread=.32,flights=[1],landing_m=1.2)
    for key in ('flights','landing_m','tread'):
        changed=copy.deepcopy(row);del changed[key]
        with pytest.raises(ValueError):validate_access_walk(changed)


@pytest.mark.parametrize('case',['hole','steep'])
def test_final_ground_continuation_requires_complete_walkable_triangles(case):
    from terrain_product import Mesh
    from terrain_query import Surface
    triangles=[]
    xs=[-5.,1.2,1.3,1.5,1.6,5.];ys=[-5.,-2.1,-1.9,0.]
    for a,b in zip(xs,xs[1:]):
        for c,d in zip(ys,ys[1:]):
            if case=='hole' and a==1.3 and c==-2.1:continue
            def point(x,y):return [x,y,0. if case=='hole' else max(0.,min(x-1.2,.4))*2.]
            q=[point(a,c),point(b,c),point(b,d),point(a,d)]
            triangles.extend((q[:3],[q[0],q[2],q[3]]))
    tri=np.asarray(triangles)
    city=Surface(Mesh.from_polygons(tri.reshape(-1,3),np.arange(len(tri)*3).reshape(-1,3)),owner='city',stage='final')
    G=ground(city=city,mountain=plane('mountain',0.),trail=plane('trail',0.,(8,8,9,9)))
    with pytest.raises(ValueError,match='Missing owned terrain|nonwalkable'):
        audit(ground_override=G)


@pytest.mark.parametrize('route',[[[0,0,0],[1,0,0],[3,0,0]],[[0,0,0],[3,0,0]]])
def test_headroom_keeps_original_cap_for_every_route_segment(route):
    from gondola.interactions import access_headroom
    floor={'poly':[[-1,-1],[4,-1],[4,2],[-1,2]],'top':0.}
    mesh=SimpleNamespace(verts=[[2,-.1,.5],[2.1,.1,.5],[2,.1,1.5]],faces=[[0,1,2]],parts=[(0,1,'post')])
    distant={'name':'distant','poly':[[8,8],[9,8],[9,9],[8,9]],'z0':[0.]*4,'z1':[1.]*4}
    with gondola_modules('solid',pure=False),pytest.raises(ValueError,match='headroom'):
        access_headroom({'route':route,'surfaces':[floor]},[mesh],{'obstacles':[distant]},fixture()[0],fixture()[1])


@pytest.mark.parametrize('x',[-.2,1.2])
def test_headroom_covers_capsule_overhang_at_real_kit_and_ground_endpoints(x):
    from gondola.interactions import access_headroom
    floor={'poly':[[0,-1],[1,-1],[1,1],[0,1]],'top':0.}
    mesh=SimpleNamespace(verts=[[x,-.1,.5],[x+.1,.1,.5],[x,.1,1.5]],faces=[[0,1,2]],parts=[(0,1,'post')])
    head={'name':'boardwalk','poly':[[-1,-1],[0,-1],[0,1],[-1,1]],'z0':[-.2]*4,'z1':[0.]*4}
    with gondola_modules('solid',pure=False),pytest.raises(ValueError,match='headroom'):
        access_headroom({'route':[[0,0,0],[1,0,0]],'surfaces':[floor]},[mesh],{'obstacles':[head]},fixture()[0],fixture()[1])


def test_stringer_post_feet_stay_behind_the_stair_exit():
    """The floor_rim exit was blocked by the last post's raised .8m stone foot."""
    from contextlib import nullcontext
    class Sink:
        def __init__(self,*a):pass
        def tagged(self,*a):return nullcontext()
        def at(self,*a):return nullcontext()
        def prism(self,*a,**k):pass
        def box(self,*a,**k):pass
    feet=[]
    def support(mesh,G,frame,xy,top,section):
        feet.append(np.asarray(xy,float));return {'xy':list(map(float,xy))}
    ns={'np':np,'math':math,'solid':SimpleNamespace(Mesh=Sink,TIMBER=1,TIMBER_DARK=2,DECK=3),
        'STATIONS':{'fixture':{'access_turn_deg':180.,'access_fit':{
            'risers':52,'tread_m':.28,'run_m':21.38,'join_m':3.2,'flights':[13]*4,'landing_m':1.2}}},
        'Station':lambda *a:SimpleNamespace(seats=[],proxies=[]),'P':SimpleNamespace(DEFAULTS={},derived=lambda p:{}),
        'world_xy':lambda p,f:np.asarray(p),'ground_edge':lambda *a:(np.array([-1.1,1.1]),np.zeros(2)),
        'railing':lambda *a,**k:None,'timber_support':support,'floor_intrusion':lambda *a:0.}
    layout={'access':[{'edge':[[0,-1.2],[0,1.2]],'point':[-.5,.001],'z':13.832}]}
    _,access=helper('access_stair',ns)('fixture',layout,SimpleNamespace(contact=lambda p:(np.zeros(len(p)),None)),(None,None,None,0))
    route=np.asarray(access['route'])[:,:2];end=route[-1]
    direction=(end-route[-2])/np.linalg.norm(end-route[-2])
    corners=np.array([[-.4,-.4],[.4,-.4],[.4,.4],[-.4,.4]])
    assert len(feet)>2
    assert max(float(((foot+corners-end)@direction).max()) for foot in feet)<0
