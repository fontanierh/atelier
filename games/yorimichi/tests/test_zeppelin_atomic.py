"""Selected Zeppelin ownership and immutable-original entropy controls (no native claim)."""
import ast
from contextlib import nullcontext
import hashlib
import math
from pathlib import Path
import random
import sys
from types import SimpleNamespace

import numpy as np
import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GAME));sys.path.insert(0,str(GAME/'world'))
import yori
from zeppelin.random_context import restore
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'
SOURCE_SHA={'zeppelin/primitives.py': 'aa2b88d02ba5c68150ce3f612e8c21cb2aa14d4e14ddfd2e12b5290173e84f3d', 'zeppelin/parts/ship.py': '62ea795df53edd9f83ffce1f85ef41403806811eb10415be0e850d52353d3a7d', 'zeppelin/parts/motors.py': '64c41605a6832cb56d541c8dec699fef5ec76b614baf0347d5a7dc48ceea5f30', 'zeppelin/parts/propeller.py': 'c4723f98ff802ce7d7b7754a1b43ae64f6bcafeeb95018381d584fe975ea4f28', 'zeppelin/parts/gate.py': 'ffc96dbe23fb32935b763abb26ea06d2d15b7b583cf04429f5ddc66a67a184e5', 'zeppelin/parts/gangway.py': '67e92c3271c304ea0f05a1aac370494de8bd580be6081c8310c92ce8f3d9fb9a', 'zeppelin/parts/station.py': '8402ab741c00e030da4c56318111dd680f11ace3d77479258bef7af3491d9b4e', 'zeppelin/build.py': '7fe1ace16de68e04ab6e6564c4c8aa758912d610e77d88a03c75e1d053c40753', 'village/mesh.py': '386ec356206fe1d96c77a516cb0ce794184bcd574448042f948795882839d4c7'}


class Matrix:
    @staticmethod
    def Translation(*args):return Matrix()
    @staticmethod
    def Rotation(*args):return Matrix()
    def copy(self):return Matrix()
    def __matmul__(self,other):return self


class Mesh:
    def __init__(self,*args):self.transform=Matrix();self.vertices=[];self.events=[]
    def at(self,*args):self.events.append(("at",args));return nullcontext()
    def __getattr__(self,name):
        def record(*args,**kwargs):self.events.append((name,args,kwargs))
        return record


def source(path):
    payload=(GAME/'tests/fixtures/immutable-283329c07'/(path.replace('/','-')+'.txt')).read_bytes()
    assert hashlib.sha256(payload).hexdigest()==SOURCE_SHA[path]
    return payload


def declarations(path,names,namespace):
    tree=ast.parse(source(path))
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),path,'exec'),namespace)


def original_context():
    # Geometry sinks preserve all argument evaluations and entropy calls. This proves
    # stream contexts, not serialized geometry or native acceptance.
    primitive=random.Random(980);village=random.Random(76)
    from zeppelin.layout import STATIONS,MESHES,PARK_WALK,PARK_BRIDGE,DECK_EDGE,belmonte_path,PROPELLER_CENTERS,PROPELLER_RADIUS
    vns=dict(R=village,math=math,np=np,Vector=lambda x:np.array(x),PALETTE={'roof':(.1,.2,.3),'wood_light':(.2,.3,.4),'leaf':(.3,.4,.5)})
    declarations('village/mesh.py',{'color_variant','roof','door','pot','window','lantern'},vns)
    v=SimpleNamespace(**{key:value for key,value in vns.items() if callable(value)},PALETTE=vns['PALETTE'])
    ns=dict(R=primitive,M=Mesh,AirshipMesh=Mesh,Matrix=Matrix,np=np,math=math,v=v,
            STATIONS=STATIONS,MESHES=MESHES,PARK_WALK=PARK_WALK,PARK_BRIDGE=PARK_BRIDGE,
            DECK_EDGE=DECK_EDGE,belmonte_path=belmonte_path,PROPELLER_CENTERS=PROPELLER_CENTERS,
            PROPELLER_RADIUS=PROPELLER_RADIUS,upper_surface=lambda *args:0.)
    ns.update({name:(.2,.3,.4) for name in ('CREAM','DARK','GOLD','PLANK','SAGE','STONE','WOOD')})
    declarations('zeppelin/primitives.py',{'cylinder','xlathe','ring','rail','bench','badge'},ns)
    declarations('zeppelin/parts/ship.py',{'ship'},ns)
    for kind in ('motors','propeller','gate','gangway'):declarations('zeppelin/parts/'+kind+'.py',{kind},ns)
    # Keep all original geometry and query arithmetic; substitute deterministic readers
    # through explicit fixture functions, retaining their exact scalar coordinate calls.
    tree=ast.parse(source('zeppelin/parts/station.py'))
    class QueryFixture(ast.NodeTransformer):
        def visit_ImportFrom(self,node):return None
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
    tree=ast.fix_missing_locations(QueryFixture().visit(ast.Module(body=nodes,type_ignores=[])))
    reader=lambda x,y:np.asarray(x)*.001+np.asarray(y)*.003+17.
    ns.update(height=reader,north_height=reader,upper_surface=lambda h,x,y:reader(x,y),
              bm_layout=SimpleNamespace(ORIGIN=[0.,0.,0.]),bm_source=SimpleNamespace(terrain=lambda:SimpleNamespace(height=reader)))
    exec(compile(tree,'immutable-station','exec'),ns)
    return ns,primitive,village


def test_rng_matches_actual_immutable_original_constructor_evaluation():
    ns,primitive,village=original_context()
    from zeppelin.layout import MESHES
    constructors=[('ZP_Airship',lambda:ns['ship']()),('ZP_Motors',lambda:ns['motors']()),
        ('ZP_Propeller',lambda:ns['propeller']()),('ZP_Gate',lambda:ns['gate']()),('ZP_Gangway',lambda:ns['gangway']())]
    constructors += [(name,lambda i=i:ns['station'](i,None)) for i,name in enumerate(MESHES)]
    for name,construct in constructors:
        selected,selected_v=random.Random(),random.Random();restore(name,selected,selected_v)
        assert selected.getstate()==primitive.getstate(),name
        assert selected_v.getstate()==village.getstate(),name
        construct()


def test_all_ten_logical_owners_have_single_selected_scripts(tmp_path):
    from zeppelin.atomic import steps,LOGICAL
    from atelier.build_inputs import local_imports
    graph=steps(SimpleNamespace(out=tmp_path))
    planners=[row for row in graph if row.name.startswith('world.zeppelin.geometry.')]
    assert len(planners)==len(LOGICAL)==10
    for planner in planners:
        assert planner.cache
        script=planner.commands[0].script
        closure=set(local_imports(script,(GAME/'world',GAME/'world/regions')))
        assert GAME/'world/regions/zeppelin/build.py' not in closure
        for other in planners:
            if other is not planner:assert other.commands[0].script not in closure


@pytest.mark.parametrize('index',range(4))
def test_selected_station_all_constructor_events_match_original_queries(tmp_path,monkeypatch,index):
    from zeppelin.layout import MESHES
    from zeppelin.project_queries import project
    from zeppelin.query_data import Queries
    from hidamari import layout as city
    from village import layout as village_layout
    from belmonte import source as bm_source,layout as bm_layout
    reader=lambda x,y:np.asarray(x)*.001+np.asarray(y)*.003+17.
    monkeypatch.setattr(city,'height',reader);monkeypatch.setattr(city,'north_height',reader)
    monkeypatch.setattr(village_layout,'upper_surface',lambda h,x,y:reader(x,y))
    monkeypatch.setattr(bm_source,'terrain',lambda:SimpleNamespace(height=lambda x,y:reader(x+bm_layout.ORIGIN[0],y+bm_layout.ORIGIN[1])-bm_layout.ORIGIN[2]))
    np.save(tmp_path/'heightmap.npy',np.zeros((2,2)))
    monkeypatch.setattr(yori,'OUT',tmp_path)
    query=tmp_path/'queries.json';project(MESHES[index],query)
    ns,primitive,village=original_context();ns.update(bm_layout=bm_layout,bm_source=bm_source)
    restore(MESHES[index],primitive,village)
    baseline=ns['station'](index,None)
    tree=ast.parse((GAME/'world/regions/zeppelin/parts/station_data.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef)]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'selected-station', 'exec'),ns)
    restore(MESHES[index],primitive,village)
    actual=ns['station'](index,queries=Queries(query))
    def normalize(value):
        if isinstance(value,dict):return {key:normalize(item) for key,item in value.items()}
        if isinstance(value,(list,tuple,np.ndarray)):return [normalize(item) for item in value]
        if isinstance(value,np.generic):return value.item()
        return value
    assert normalize(actual.events)==normalize(baseline.events)


def test_trail_exact_original_constructor_events_follow_projected_final_data(tmp_path,monkeypatch):
    import json
    from village import layout as village_layout
    from zeppelin import ground_query as station
    from zeppelin.project_queries import project
    from zeppelin.query_data import Queries
    from zeppelin.layout import city_path
    reader=lambda x,y:np.asarray(x)*.001+np.asarray(y)*.003+17.
    monkeypatch.setattr(village_layout,'upper_surface',lambda h,x,y:reader(x,y))
    monkeypatch.setattr(station,'city_ground',reader)
    monkeypatch.setattr(yori,'OUT',tmp_path)
    np.save(tmp_path/'heightmap.npy',np.zeros((2,2)))
    (tmp_path/'world.json').write_text(json.dumps(dict(zeppelin=dict(trail=[[-205.,230.,70.4],[-200.,235.,71.],[-193.,237.,72.]]))))
    project('ZP_Trail',tmp_path/'queries.json')
    ns,_,_=original_context();ns.update(yori=yori,json=json,city_path=city_path,city_ground=reader,h=np.zeros((2,2)))
    tree=ast.parse(source('zeppelin/build.py'));main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    start=next(i for i,node in enumerate(main.body) if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call)
               and isinstance(node.value.func,ast.Name) and node.value.func.id=='M'
               and node.value.args and isinstance(node.value.args[0],ast.Constant) and node.value.args[0].value=='ZP_Trail')
    end=next(i for i,node in enumerate(main.body[start:],start) if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call)
             and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='export')
    exec(compile(ast.Module(body=main.body[start:end],type_ignores=[]),'immutable-trail','exec'),ns)
    baseline=ns['m']
    tree=ast.parse((GAME/'world/regions/zeppelin/parts/trail.py').read_text())
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef)],type_ignores=[]),'selected-trail','exec'),ns)
    actual=ns['construct'](Queries(tmp_path/'queries.json'))
    def normalize(value):
        if isinstance(value,dict):return {key:normalize(item) for key,item in value.items()}
        if isinstance(value,(list,tuple,np.ndarray)):return [normalize(item) for item in value]
        if isinstance(value,np.generic):return value.item()
        return value
    assert normalize(actual.events)==normalize(baseline.events)
