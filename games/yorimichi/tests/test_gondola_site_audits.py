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
    names={name}
    if name=='access_stair':
        names.add('emit_access_floor')
        with gondola_modules('solid',pure=False):
            from gondola.support import floor_caps
        namespace.setdefault('floor_caps',floor_caps)
        namespace.setdefault('access_walk_audit',lambda *a,**k:{'pass':True})
        namespace.setdefault('W',SimpleNamespace(STEP=.3,TREAD_MIN=.25,MIN_WIDTH=.9))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),namespace)
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


def test_near_rope_uses_available_contact_budget_to_reduce_long_span_density():
    from gondola.line import centre_profile,near_rope_tolerance,simplify
    profile=centre_profile([(0.,0.,False),(400.,40.,True),(950.,210.,True),(1410.,535.,True),(1565.,631.,False)])
    points=np.c_[profile[:,0],np.zeros(len(profile)),profile[:,1]]
    tolerance=near_rope_tolerance(1.764)
    former=simplify(points,.0001)
    reduced=simplify(points,tolerance)
    assert len(reduced)<len(former)*.8
    assert 2*(12*2*(len(reduced)-1)+2*(12-2))<100000
    for a,b in zip(reduced,reduced[1:]):
        original=points[(points[:,0]>=a[0])&(points[:,0]<=b[0])]
        t=np.clip((original-a)@(b-a)/np.sum((b-a)**2),0,1)
        deviation=np.linalg.norm(original-a-t[:,None]*(b-a),axis=1).max()
        assert 1.764+.0005+deviation*1000<2.


def test_trestle_crossheads_seat_in_posts_without_coplanar_junction_overlaps():
    beams=[]
    class Mesh:
        def __init__(self,name):pass
        def beam(self,a,b,width,depth,material,**kwargs):
            if a[2]==b[2]:beams.append((np.array(a),np.array(b),width))
    def support(mesh,G,frame,xy,top,section):
        return {'xy':list(xy),'top':top,'base':top-4.}
    function=helper('station_foundation',{
        'np':np,'math':__import__('math'),'solid':SimpleNamespace(Mesh=Mesh,TIMBER=1,TIMBER_DARK=2),
        'FLOORS':{'platform'},'timber_support':support,
        'W':SimpleNamespace(inside_poly=lambda x,y,p:np.ones(len(x),bool)),
    })
    layout={'obstacles':[{'name':'platform','poly':[[-3,-3],[6,-3],[6,6],[-3,6]],'z0':[0.]}]}
    _,posts=function('fixture',layout,None,None)
    assert beams
    rectangles=[]
    for a,b,width in beams:
        axis=(b-a)[:2];axis/=np.linalg.norm(axis)
        normal=np.array([-axis[1],axis[0]])*width/2
        rect=np.array([a[:2]-normal,a[:2]+normal,b[:2]+normal,b[:2]-normal])
        rectangles.append((rect.min(0),rect.max(0)))
        for endpoint in (a,b):
            # Every crosshead still penetrates a real post, rather than leaving
            # a gap to avoid the coplanar audit.
            assert any(np.max(abs(endpoint[:2]-post['xy']))<.14 for post in posts)
    for i,(lo,hi) in enumerate(rectangles):
        for other_lo,other_hi in rectangles[i+1:]:
            overlap=np.minimum(hi,other_hi)-np.maximum(lo,other_lo)
            assert not np.all(overlap>1e-8),f'Overlapping crosshead faces: {overlap}'


def test_sloping_stringer_has_a_level_fully_supported_railing_post_seat():
    from contextlib import nullcontext
    pieces=[]
    mesh=SimpleNamespace(tagged=lambda tag:nullcontext(),prism=lambda poly,base,top,mat:pieces.append((np.asarray(poly),base,top)))
    function=helper('rail_bearing',{'np':np,'solid':SimpleNamespace(TIMBER_DARK=1)})
    for slope in (.12,.57,.85):
        roof=lambda x,y:2.-slope*x
        top=function(mesh,0.,0.,np.array([1.,0.]),np.array([0.,1.]),roof,.08)
        polygon,base,cap=pieces[-1]
        assert top==cap and top>max(roof(*point) for point in polygon)
        assert all(abs(base(*point)-(roof(*point)-.01))<1e-12 for point in polygon)
        # All five existing seat-audit rays hit this horizontal bearing surface.
        for point in ((0,0),(-.06,0),(.06,0),(0,-.06),(0,.06)):
            assert np.all(np.asarray(point)>polygon.min(0)) and np.all(np.asarray(point)<polygon.max(0))


def test_actual_access_stringer_end_caps_clear_their_support_post_faces():
    from contextlib import contextmanager,nullcontext
    roofs=[];posts=[]
    class Mesh:
        tag=None
        def __init__(self,name):pass
        @contextmanager
        def tagged(self,tag):
            previous=self.tag;self.tag=tag
            try:yield
            finally:self.tag=previous
        def prism(self,polygon,*args,**kwargs):
            if self.tag=='access_stringer':roofs.append(np.asarray(polygon))
        def at(self,*args):return nullcontext()
        def box(self,*args):pass
    def support(mesh,G,frame,point,level,section):
        posts.append((point,section));return None
    solid=SimpleNamespace(Mesh=Mesh,TIMBER_DARK=1,TIMBER=2,DECK=3)
    ground=SimpleNamespace(contact=lambda points:(np.zeros(len(points)),None))
    function=helper('access_stair',{
        'np':np,'math':__import__('math'),'solid':solid,'STATIONS':{'fixture':{}},
        'Station':lambda *a:SimpleNamespace(seats=[],proxies=[]),
        'P':SimpleNamespace(DEFAULTS={},derived=lambda p:{}),
        'world_xy':lambda points,frame:np.asarray(points),
        'ground_edge':lambda *a:(np.array([-1.1,1.1]),np.zeros(2)),
        'railing':lambda *a,**k:None,'timber_support':support,
        'floor_intrusion':lambda *a:0.,
    })
    layout={'access':[{'edge':[[0.,-1.2],[0.,1.2]],'point':[-1.,0.],'z':2.}]}
    function('fixture',layout,ground,(None,None,None,0.))
    assert len(roofs)==2 and len(posts)>0
    for polygon in roofs:
        centre=polygon[:,1].mean()
        head=polygon[:,0].min()
        initial=[(p,s) for p,s in posts if p[0]==0. and abs(p[1]-centre)<1e-8]
        assert initial
        assert all(head<p[0]-section/2-1e-8 for p,section in initial)


def test_adjoining_landing_rails_reuse_one_corner_post_and_keep_both_rails():
    from contextlib import nullcontext
    source=SOURCE.parents[3]/'assets/vehicles/gondola/stations.py'
    tree=ast.parse(source.read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='railing')
    posts=[];rails=[]
    class V:
        def __init__(self,values):self.values=np.asarray(values,float)
        @property
        def x(self):return self.values[0]
        @property
        def y(self):return self.values[1]
        def __add__(self,other):return V(self.values+other.values)
        def __sub__(self,other):return V(self.values-other.values)
        def __mul__(self,n):return V(self.values*n)
        def normalized(self):return V(self.values/np.linalg.norm(self.values))
    def point_at(points,distance):
        a,b=map(np.asarray,points);t=(b-a)/np.linalg.norm(b-a)
        return a+distance*t,V(t)
    mesh=SimpleNamespace(at=lambda *a:nullcontext(),grained=lambda *a:nullcontext(),
                         box=lambda *a,**k:None,beam=lambda a,b,*args,**k:rails.append((a,b)))
    station=SimpleNamespace(seat=lambda label,x,y,z,**k:posts.append((x,y)),proxies=[])
    namespace={'math':__import__('math'),'path_len':lambda p:np.linalg.norm(np.asarray(p[1])-p[0]),
               'point_at':point_at,'Vector':V,'TIMBER':1,'proxy_strip':lambda *a:None}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),namespace)
    function=namespace['railing']
    function(mesh,station,[(0,0),(2,0)],'timber')
    first_rails=len(rails)
    function(mesh,station,[(2,0),(2,2)],'timber',start_post=False)
    assert posts.count((2.,0.))==1 and len(posts)==len(set(posts))
    assert len(rails)==2*first_rails and first_rails>0


def test_access_stringers_and_posts_clear_the_adjoining_landing_post():
    import math
    from contextlib import nullcontext
    rails=[];supports=[]
    mesh=SimpleNamespace(tagged=lambda *a:nullcontext(),at=lambda *a:nullcontext(),
                         prism=lambda *a,**k:None,box=lambda *a,**k:None)
    def support(m,g,frame,point,*args):supports.append(np.asarray(point).copy())
    namespace={'np':np,'math':math,'solid':SimpleNamespace(Mesh=lambda *a:mesh,TIMBER=1,TIMBER_DARK=2,DECK=3),
               'STATIONS':{'fixture':{'access_turn_deg':90.}},
               'Station':lambda *a:SimpleNamespace(seats=[],proxies=[]),
               'P':SimpleNamespace(DEFAULTS={},derived=lambda p:{}),
               'world_xy':lambda p,f:np.asarray(p),
               'ground_edge':lambda *a:(np.array([-1.1,1.1]),np.zeros(2)),
               'railing':lambda m,st,points,*a,**k:rails.append(np.asarray(points)),
               'timber_support':support,'floor_intrusion':lambda *a:0.}
    function=helper('access_stair',namespace)
    layout={'access':[{'edge':[[0.,-1.2],[0.,1.2]],'point':[-1.,0.],'z':2.}]}
    function('fixture',layout,SimpleNamespace(contact=lambda xy:(np.zeros(len(xy)),None)),(None,None,None,0.))
    landing_post=rails[1][-1]
    stair_starts=[points[0] for points in rails[2:]]
    # .13m post and .18m stringer must leave at least 1cm between their faces.
    assert min(np.linalg.norm(point-landing_post) for point in stair_starts)>=.13/2+.18/2+.01
    assert len(stair_starts)==2
    for rail,post in zip(stair_starts,supports[:2]):assert np.allclose(rail,post)
