"""Production curve contact, exact loop joins and bounded rope mesh reduction."""
import importlib.util
import math
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'world'))
from gondola.line import centre_profile, closed_circuit, simplify, span_height, station_frame, tower_saddles


def test_span_is_one_parabola_with_the_authored_sag():
    length,za,zb=100.,0.,70.
    z=lambda x: float(span_height(x,length,za,zb))
    assert z(0)==za and z(length)==zb
    assert z(length/2)==pytest.approx((za+zb)/2-.035*length)
    slopes=[(z((k+1)*length/20)-z(k*length/20))/(length/20) for k in range(20)]
    assert all(b>a for a,b in zip(slopes,slopes[1:]))          # no mid-air inflection
    second=[z((k+1)*length/20)-2*z(k*length/20)+z((k-1)*length/20) for k in range(1,20)]
    assert all(v>0 for v in second)                             # concave up everywhere


def test_tower_saddle_meets_both_spans_with_continuous_tangents():
    p=centre_profile([(0,0,False),(100,30,True),(200,60,False)])
    x=p[:,0]
    assert np.all(np.diff(x)>1e-9)
    eps=1e-4
    z=lambda q: float(np.interp(q,x,p[:,1]))
    for q in (98.4,101.6):
        left=(z(q)-z(q-eps))/eps; right=(z(q+eps)-z(q))/eps
        assert left==pytest.approx(right,abs=5e-3)               # tangent at both contact points
    assert z(101.6)>z(98.4)                                      # the train climbs with the line
    slopes=[(z(98.4+k*.4+eps)-z(98.4+k*.4-eps))/(2*eps) for k in range(9)]
    assert max(slopes)-min(slopes)>1e-3                          # a saddle, not a level shelf


def test_station_mouth_curve_is_short_and_tangent_to_the_span():
    p=centre_profile([(0,13.77,False),(200,73.77,False)],station_curve=7.)
    x,z=p[:,0],p[:,1]
    assert x[-1]==pytest.approx(200)
    assert z[0]==pytest.approx(13.77)
    eps=1e-4
    zq=lambda q: float(np.interp(q,x,z))
    assert (zq(eps)-zq(0))/eps==pytest.approx(0,abs=1e-2)
    assert x[x<=7.01].max()==pytest.approx(7,abs=.1)
    L=200.;m=(73.77-13.77)/L
    for q in (20.,50.,100.):
        assert zq(q)==pytest.approx(13.77+m*q-4*.035*L*(q/L)*(1-q/L),abs=1e-3)


def test_final_station_curve_can_use_twenty_metres_without_exceeding_the_span_slope():
    supports=[(0,500.,False),(460,611.,True),(615.5,707.4,False)]
    p=centre_profile(supports,end_station_curve=20.)
    x,z=p[:,0],p[:,1]
    zq=lambda q: float(np.interp(q,x,z))
    assert z[-1]==pytest.approx(707.4)
    assert zq(615.5-20.)==pytest.approx(float(span_height(615.5-460.-20.,155.5,611.,707.4)),abs=.2)
    end_slope=math.atan((707.4-611.)/(615.5-460.)+4*.035)
    peak=max(math.atan((zq(q+1e-3)-zq(q-1e-3))/2e-3) for q in np.linspace(595.5,615.5,401))
    assert peak<=end_slope+math.radians(1)


def test_high_deflection_tower_saddle_keeps_a_twelve_metre_bend():
    gentle=tower_saddles([(0,0,False),(100,20,True),(200,54,False)])[1]
    assert gentle['half']==pytest.approx(1.6)                   # <= 10 deg keeps the 3.2 m train
    steep=tower_saddles([(0,0,False),(100,40,True),(200,60,False)])[1]
    assert steep['half']>1.6
    flat=min(abs(steep['m_in']),abs(steep['m_out']))
    radius=(1+flat*flat)**1.5*2*steep['half']/abs(steep['m_out']-steep['m_in'])
    assert radius>=12.                                          # tightest curvature at the flatter end


@pytest.mark.parametrize('supports', [[(0,0,0),(0,1,1)],[(1,0,0),(0,0,0)],[(0,0,0),(1,float('nan'),0)]])
def test_invalid_supports_fail(supports):
    with pytest.raises(ValueError):
        centre_profile(supports)


def test_both_tracks_join_the_actual_kit_loops_with_identical_endpoints():
    spec=importlib.util.spec_from_file_location('kit_rope',ROOT/'assets/vehicles/gondola/rope.py')
    rope=importlib.util.module_from_spec(spec);spec.loader.exec_module(rope)
    a,b=np.array([20.,40.]),np.array([130.,170.])
    length=float(np.linalg.norm(b-a))
    profile=centre_profile([(.6,13.77,False),(length-.6,73.77,False)])
    loop=rope.station_loop(3,3.77,3.77,7.6,.045).pts
    points=closed_circuit(profile,station_frame(a,b,10,7.6),station_frame(b,a,70,7.6),loop,6)
    assert np.allclose(points[0],points[-1])
    assert np.max(np.linalg.norm(np.diff(points,axis=0),axis=1))<.15


def test_rope_reduction_bounds_every_original_interval_and_keeps_corners():
    x=np.linspace(0,100,2001)
    points=np.c_[x,np.zeros(len(x)),.005*x*x]
    reduced=simplify(points,.0005)
    assert len(reduced)<len(points)/3
    for a,b in zip(reduced,reduced[1:]):
        subset=points[(points[:,0]>=a[0])&(points[:,0]<=b[0])]
        t=np.clip((subset-a)@(b-a)/np.sum((b-a)**2),0,1)
        assert np.linalg.norm(subset-(a+t[:,None]*(b-a)),axis=1).max()<=.0005+1e-10


@pytest.mark.parametrize('points', [
    [[0,0,0],[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,0]],
    [[0,0,0],[1,1,0],[2,0,0],[3,-1,0],[4,0,0],[5,1,0],[6,0,0]],
])
def test_reduction_proves_intervals_even_when_prefix_error_is_not_monotone(points):
    points=np.array(points,float);tolerance=.2
    reduced=simplify(points,tolerance)
    first=0
    for endpoint in reduced[1:]:
        last=next(i for i in range(first+1,len(points)) if np.array_equal(points[i],endpoint))
        q=points[first:last+1];a,b=points[first],points[last];ab=b-a
        t=np.clip((q-a)@ab/(ab@ab),0,1) if ab@ab else np.zeros(len(q))
        assert np.linalg.norm(q-a-t[:,None]*ab,axis=1).max()<=tolerance
        first=last
    assert first==len(points)-1


@pytest.mark.parametrize('tolerance',[float('nan'),float('inf'),0.,-1.])
def test_reduction_refuses_invalid_error_bound(tolerance):
    with pytest.raises(ValueError):simplify([[0,0,0],[1,1,1]],tolerance)


def test_world_rope_reduction_bounds_stored_float32_segments_in_both_tracks():
    from gondola.line import near_rope_tolerance
    profile=centre_profile([(0.,0.,False),(400.,40.,True),(950.,210.,True),(1410.,535.,True),(1565.,631.,False)])
    axis=np.array([60.,1585.]);axis/=np.linalg.norm(axis)
    normal=np.array([-axis[1],axis[0]]);tolerance=near_rope_tolerance(1.764)
    for side in(-1,1):
        points=np.c_[np.array([1120.,455.])+profile[:,0,None]*axis+side*3*normal,profile[:,1]+51.]
        reduced=simplify(points,tolerance);stored=reduced.astype('f4').astype(float)
        assert 2*(12*2*(len(reduced)-1)+2*(12-2))<100000
        longitudinal=(points[:,:2]-np.array([1120.,455.]))@axis
        for a,b,sa,sb in zip(reduced,reduced[1:],stored,stored[1:]):
            lo,hi=(np.array([a[:2],b[:2]])-np.array([1120.,455.]))@axis
            original=points[(longitudinal>=lo-1e-9)&(longitudinal<=hi+1e-9)]
            t=np.clip((original-sa)@(sb-sa)/np.sum((sb-sa)**2),0,1)
            assert np.linalg.norm(original-sa-t[:,None]*(sb-sa),axis=1).max()<=tolerance+1e-12


def test_rope_refuses_when_storage_precision_exhausts_axis_allowance():
    with pytest.raises(ValueError,match='float32 coordinate precision'):
        simplify([[10000.1234,10000.4567,0.],[10001.1234,10001.4567,1.]],.0001)
    with pytest.raises(ValueError,match='Unrepresentable'):
        simplify([[0.,0.,0.],[1e40,0.,0.]],.001)


def test_stored_rope_axis_uses_centimetre_float32_vertices():
    from gondola.line import float32_cm_axes
    vertices=np.array([[1000.123456+ring,2000.456789,500.123456] for ring in range(4) for _ in range(12)])
    axes=float32_cm_axes(vertices,[2,2])
    expected=(vertices*100).astype('f4').astype(float)/100
    assert np.array_equal(np.vstack(axes),expected.reshape(4,12,3).mean(1))
    with pytest.raises(ValueError):float32_cm_axes(vertices[:-1],[2,2])


def test_rope_correspondence_preserves_the_actual_nonidentity_world_transform():
    from gondola.line import recover_rope_vertices
    expected=np.array([[1176.240478515625,2021.1805419921875,697.8170776367188],
                       [1177.,2022.,698.]],dtype='f4').astype(float)
    local=expected[::-1].copy()
    matrix=np.array([[1.,1.5099580252808664e-7,0.],[-1.5099580252808664e-7,1.,0.],[0.,0.,1.]],dtype='f4')
    world=(matrix@local.astype('f4').T).T.astype(float)
    recovered,proof=recover_rope_vertices(expected,local,world,lambda p:int(np.linalg.norm(local-p,axis=1).argmin()))
    assert np.array_equal(recovered,world[::-1])
    assert proof['control_point_error_m']==0
    assert proof['world_displacement_m']>proof['control_point_allowance_m']
    assert proof['world_transform_applied'] is True


@pytest.mark.parametrize('fault',['count','local-drift','ambiguous','local-nan','world-nan'])
def test_rope_correspondence_still_refuses_invalid_control_points(fault):
    from gondola.line import recover_rope_vertices
    expected=np.array([[1000.,2000.,500.],[1001.,2000.,500.]])
    local=expected.copy();world=local.copy()
    if fault=='count':local=local[:1];world=world[:1]
    elif fault=='local-drift':local[0,0]+=.002
    elif fault=='local-nan':local[0,0]=float('nan')
    elif fault=='world-nan':world[0,0]=float('nan')
    nearest=lambda p:0 if fault=='ambiguous' else int(np.linalg.norm(local-p,axis=1).argmin())
    with pytest.raises(ValueError):recover_rope_vertices(expected,local,world,nearest)


def test_preserved_world_displacement_still_fails_actual_groove_limit():
    from gondola.line import recover_rope_vertices,float32_cm_axes,stored_groove_audit
    spec=importlib.util.spec_from_file_location('transformed_rope',ROOT/'assets/vehicles/gondola/rope.py')
    rope=importlib.util.module_from_spec(spec);spec.loader.exec_module(rope)
    vertices=np.array([[x,.045*math.cos(a),100.+.045*math.sin(a)]
                       for x in (0.,4.,0.,4.) for a in np.arange(12)*2*math.pi/12],dtype='f4').astype(float)
    local=np.unique(vertices,axis=0);world=local+[0,.003,0]
    recovered,_=recover_rope_vertices(vertices,local,world,lambda p:int(np.linalg.norm(local-p,axis=1).argmin()))
    axes=float32_cm_axes(recovered,[2,2])
    angles=np.radians([*range(0,86,5),86])
    groove=[[x,side*.045*math.cos(t),.045*math.sin(t)] for side in(-1,1) for x in(-.195,0.,.195) for t in angles]
    proof=stored_groove_audit(np.array([[0.,100.],[4.,100.]]),axes,groove,rope.RopePath,.045)
    assert proof['max_error_mm']>2.9 and proof['pass'] is False


@pytest.mark.parametrize('offset,passed',[(.0005,True),(.003,False)])
def test_stored_grooves_check_unquantized_runtime_frames_and_both_directions(offset,passed):
    from gondola.line import stored_groove_audit
    spec=importlib.util.spec_from_file_location('stored_rope',ROOT/'assets/vehicles/gondola/rope.py')
    rope=importlib.util.module_from_spec(spec);spec.loader.exec_module(rope)
    angles=np.radians([*range(0,86,5),86])
    groove=[[x,side*.045*math.cos(t),.045*math.sin(t)] for side in(-1,1) for x in(-.195,0.,.195) for t in angles]
    profile=np.array([[0.,10000.123456],[4.,10000.123456]])
    axes=[np.c_[[0.,4.],[offset,offset],profile[:,1]] for _ in(-1,1)]
    proof=stored_groove_audit(profile,axes,groove,rope.RopePath,.045)
    assert proof['directions']==[-1,1] and proof['poses']>=40
    assert proof['points_per_pose']==114
    assert proof['pass'] is passed
    assert proof['max_error_mm']==pytest.approx(offset*1000,abs=1e-5)
    assert proof['bound_mm']==pytest.approx(offset*1000+.005,abs=1e-5)
