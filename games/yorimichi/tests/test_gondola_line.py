"""Production curve contact, exact loop joins and bounded rope mesh reduction."""
import importlib.util
import math
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'world'))
from gondola.line import centre_profile, closed_circuit, simplify, span_height, station_frame


def test_shoulders_meet_the_level_sheave_trains_with_continuous_tangents():
    length,za,zb=100.,0.,70.
    epsilon=1e-5
    z=lambda x: float(span_height(x,length,za,zb))
    assert z(0)==za and z(length)==zb
    assert abs((z(epsilon)-z(0))/epsilon)<1e-5
    assert abs((z(length)-z(length-epsilon))/epsilon)<1e-5
    for x in (40.,60.):
        assert abs((z(x)-z(x-epsilon))/epsilon-(z(x+epsilon)-z(x))/epsilon)<1e-5
    p=centre_profile([(0,0,False),(100,30,True),(200,60,False)])
    assert np.all(p[(p[:,0]>=98.4)&(p[:,0]<=101.6),1]==30)


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
