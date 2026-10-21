"""Exercise actual site helpers without importing a Blender generator."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest
from gondola_kit_fixture import gondola_modules
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
SOURCE=Path(__file__).resolve().parents[1]/'world/regions/gondola/site.py'


def helper(name,namespace):
    tree=ast.parse(SOURCE.read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),namespace)
    return namespace[name]


def test_body_and_signed_jaws_keep_both_directions_when_subsampling():
    seen={'groove':set(),'body':set(),'jaw':set()}
    def record(key,frames):
        seen[key].update(row[1].C for row in frames)
        return {'ok':True,'max_error_mm':1.,'min_distance_from_rope_axis_m':.1}
    path=SimpleNamespace(s=[0.,.1,3.,4.],grip_frame=lambda s,axis:axis[1])
    K=SimpleNamespace(groove_check=lambda c,p,f:record('groove',f),
                      rope_check=lambda c,p,f:record('body',f),jaw_contact=lambda c,p,f:record('jaw',f))
    function=helper('audit_span',{'np':np,'R':SimpleNamespace(RopePath=lambda *a:path),
                                'pose':lambda q:SimpleNamespace(C=q),'K':K,
                                'checks':SimpleNamespace(hanging_ok=lambda c:True)})
    function('fixture',np.array([[0.,0.],[3.,0.]]),{}, {'rope_radius':.045})
    assert all(directions=={-1,1} for directions in seen.values())


def test_complete_ground_clearance_refuses_a_narrow_crest_between_old_rays():
    with gondola_modules('solid',pure=False):
        from gondola.support import owned_triangles
    from terrain_product import Mesh
    from terrain_query import Surface
    from gondola.terrain import Ground
    def surface(owner,tri):
        tri=np.asarray(tri,float).reshape(-1,3,3)
        return Surface(Mesh.from_polygons(tri.reshape(-1,3),np.arange(len(tri)*3).reshape(-1,3)),owner=owner,stage='final')
    triangles=[];ys=[-10.,-.29,-.24,-.19,10.];zs=[0.,0.,20.,0.,0.]
    for a,b,za,zb in zip(ys,ys[1:],zs,zs[1:]):
        triangles += [[[-10,a,za],[120,a,za],[120,b,zb]],[[-10,a,za],[120,b,zb],[-10,b,zb]]]
    ground=Ground(city=surface('city',triangles),mountain=surface('mountain',[]),
                  valley=surface('valley',[]),apron=surface('apron',[]),trail=surface('trail',[]),
                  city_bounds=(-10,-10,120,10),mountain_bounds=(-10,10,120,20),
                  valley_bounds=(-10,30,120,40),apron_bounds=(-10,20,120,40))
    function=helper('ground_gap',{'np':np,'owned_triangles':owned_triangles})
    assert ground.contact([[50,y] for y in np.linspace(-4.3,4.3,19)])[0].max()==0.
    with pytest.raises(ValueError,match='intersects approach terrain'):
        function(np.array([[0.,10.],[100.,10.]]),np.array([0.,0.]),np.array([1.,0.]),ground,0.)


def test_actual_timber_support_refuses_missing_interior_ground():
    with gondola_modules('solid',pure=False):
        from gondola.support import owned_range
    from test_gondola_ground import ground,plane
    # The point query's corners and centre all exist; the .1m interior patch is absent.
    from terrain_product import Mesh
    from terrain_query import Surface
    tri=[];knots=[-.6,.15,.25,.6]
    for i,(a,b) in enumerate(zip(knots,knots[1:])):
        for j,(c,d) in enumerate(zip(knots,knots[1:])):
            if i==j==1:continue
            tri += [[[a,c,0],[b,c,0],[b,d,0]],[[a,c,0],[b,d,0],[a,d,0]]]
    tri=np.asarray(tri);tri[:,:,1]-=2
    surface=Surface(Mesh.from_polygons(tri.reshape(-1,3),np.arange(len(tri)*3).reshape(-1,3)),owner='city',stage='final')
    G=ground(city=surface,trail=plane('trail',0,(3,3,4,4)))
    frame=(np.array([0.,-2.]),np.array([1.,0.]),np.array([0.,1.]),2.)
    def world_xy(points,frame):return np.asarray(points)+frame[0]
    function=helper('timber_support',{'np':np,'owned_range':owned_range,'world_xy':world_xy})
    assert G.contact(world_xy([[-.4,-.4],[.4,-.4],[.4,.4],[-.4,.4],[0,0]],frame))[0].tolist()==[0.]*5
    with pytest.raises(ValueError,match='Missing owned terrain'):
        function(None,G,frame,np.array([0.,0.]),1.)


def test_near_rope_simplification_uses_remaining_jaw_allowance():
    from gondola.line import near_rope_tolerance
    for error in (1.695,1.798,1.999):
        assert error+.0005+1000*near_rope_tolerance(error)<2.
    assert 1.695+1000*.0005>2. # former fixed reduction can overspend the budget
    with pytest.raises(ValueError):near_rope_tolerance(2.)
