"""Actual access-floor audit refuses complete triangle-backed peaks and holes."""
import math
from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest
from gondola_kit_fixture import gondola_modules
from test_gondola_site_audits import helper
from terrain_product import Mesh
from terrain_query import Surface
from gondola.terrain import Ground


def terrain(case):
    peaks={'centre':(.16,0.,3.),'off-centre':(.14,.25,3.),
           'join-first':(3.14,0.,1.5),'join-last':(3.14,.6,1.5)}
    peak=peaks.get(case)
    xs=sorted(set([-1.,0.,.12,.13,.14,.16,.17,.18,.32,2.24,2.94,3.74,20.]))
    ys=sorted(set([-3.,-1.1,-.02,0.,.02,.23,.25,.27,1.1,3.]))
    if peak:
        xs=sorted(set(xs+[peak[0]-.01,peak[0],peak[0]+.01]))
        ys=sorted(set(ys+[peak[1]-.01,peak[1],peak[1]+.01]))
    triangles=[]
    for a,b in zip(xs,xs[1:]):
        for c,d in zip(ys,ys[1:]):
            if case=='hole' and a>=.13 and b<=.17 and c>=.23 and d<=.27:continue
            def vertex(x,y):return [x,y,peak[2] if peak and x==peak[0] and y==peak[1] else 0.]
            q=[vertex(a,c),vertex(b,c),vertex(b,d),vertex(a,d)]
            triangles.extend([[q[0],q[1],q[2]],[q[0],q[2],q[3]]])
    def surface(owner,triangles):
        tri=np.asarray(triangles,float).reshape(-1,3,3)
        return Surface(Mesh.from_polygons(tri.reshape(-1,3),np.arange(len(tri)*3).reshape(-1,3)),owner=owner,stage='final')
    city=surface('city',triangles)
    distant=surface('other',[[[40,40,0],[41,40,0],[40,41,0]]])
    return Ground(city=city,mountain=distant,valley=distant,apron=distant,trail=distant,
                  city_bounds=(-1,-3,20,4),mountain_bounds=(-1,4,20,5),
                  valley_bounds=(30,5,50,50),apron_bounds=(-1,5,60,60))


class GeometrySink:
    def __init__(self,name):pass
    def tagged(self,*a):return nullcontext()
    def at(self,*a):return nullcontext()
    def prism(self,*a,**k):pass
    def box(self,*a,**k):pass


@pytest.mark.parametrize('case',['centre','off-centre','hole','join-first','join-last'])
def test_actual_access_refuses_hidden_ground_defects_in_every_floor_strip(case):
    with gondola_modules('solid',pure=False):
        from gondola.support import floor_intrusion
    G=terrain(case)
    edge=np.array([-1.1,.25,1.1]) if case.startswith('join') else np.array([-1.1,1.1])
    namespace={'np':np,'math':math,'solid':SimpleNamespace(Mesh=GeometrySink,TIMBER=1,TIMBER_DARK=2,DECK=3),
               'STATIONS':{'fixture':{}},'Station':lambda *a:SimpleNamespace(seats=[],proxies=[]),
               'P':SimpleNamespace(DEFAULTS={},derived=lambda p:{}),
               'world_xy':lambda p,f:np.asarray(p),'ground_edge':lambda *a:(edge,np.zeros(len(edge))),
               'railing':lambda *a,**k:None,'timber_support':lambda *a:None,'floor_intrusion':floor_intrusion}
    function=helper('access_stair',namespace)
    layout={'access':[{'edge':[[0.,-1.2],[0.,1.2]],'point':[-1.,0.],'z':2.}]}
    with pytest.raises(ValueError,match='intersects an access floor|Missing owned terrain'):
        function('fixture',layout,G,(None,None,None,0.))
