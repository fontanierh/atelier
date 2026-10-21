"""Run actual authored plant functions without Blender; preserve their face semantics."""
import ast
from contextlib import nullcontext
import importlib.util
import math
from pathlib import Path
import random
from types import SimpleNamespace as S

import numpy as np
import pytest

WORLD=Path(__file__).resolve().parents[1]/'world'
spec=importlib.util.spec_from_file_location('role_codec',WORLD/'foliage_roles.py')
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)


class Faces:
    def __init__(self):self.keys=[];self.faces=[];self.foliage_roles={}
    def at(self,*args):return nullcontext()
    def use(self,*args):return nullcontext()
    def poly(self,points,colour,**kwargs):
        self.keys.append(colour if isinstance(colour,str) else None)
        role=getattr(colour,'foliage_key',None)
        if role is not None:self.foliage_roles[len(self.faces)]=role
        self.faces.append(points)
    def lathe(self,centre,profile,colour,*args,**kwargs):self.poly([],colour)
    def beam(self,a,b,w,d,colour):self.poly([],colour)
    def sphere(self,centre,r,colour,**kwargs):self.poly([],colour)
    def box(self,centre,size,colour,*args):self.poly([],colour)
    def collider(self,*args):pass


def functions(path,names,**values):
    tree=ast.parse((WORLD/path).read_text())
    body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    assert len(body)==len(names)
    owner=dict(math=math,random=random,np=np,foliage_roles=R,v=S(foliage_roles=R,PALETTE={'green':(.1,.2,.3)}),R=random.Random(41),
               LEAVES=[],LEAF=[(.78,.2,.06)],site_ground=lambda x,y:0,paved_contact=lambda x,y:False,**values)
    exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),owner)
    return owner


def test_treehouse_litter_and_potted_leaves_are_explicit_despite_literal_colours():
    owner=functions(Path('regions/treehouse/build.py'),['maple_leaf','potted_plant','two_sided','vary'])
    fallen=Faces();owner['maple_leaf'](fallen,0,0,0)
    assert len(fallen.keys)==1 and R.key_role(R.face_keys(fallen)[0])==2
    plant=Faces();owner['potted_plant'](plant,0,0,0)
    assert [R.key_role(key) for key in R.face_keys(plant)]==[0,0]+[1]*18


def test_rigid_terrain_adapter_needs_no_palette_role_or_reserved_uv():
    # Hidamari's SheetMesh carries baked per-vertex colour, without palette keys.
    terrain=S(name='Terrain',faces=[(0,1,2)])
    assert R.face_keys(terrain)==[None]
    R.export_roles(S(),terrain) # No UV access for an entirely rigid surface.


@pytest.mark.parametrize('path,name,arguments',[
    ('regions/hidamari/build.py','flowerbed',(0,0,0)),
    ('regions/hidamari/plaza.py','planter',(0,0,0)),
    ('regions/hidamari/kit/bakery_western.py','planter',(0,0,0,2,1,5)),
    ('regions/hidamari/kit/machiya.py','tub_plant',(0,0,'tea')),
    ('regions/hidamari/kit/machiya.py','tub_plant',(0,0,'bamboo')),
])
def test_current_planters_keep_architecture_rigid_and_classify_every_plant(path,name,arguments):
    names=[name,'bloom'] if 'plaza.py' in path else [name]
    owner=functions(Path(path),names)
    mesh=Faces();owner[name](mesh,*arguments)
    roles=[R.key_role(key) for key in R.face_keys(mesh)]
    rigid=2 if name=='flowerbed' else 3
    assert roles[:rigid]==[0]*rigid # planter, rim and soil
    assert sum(role>0 for role in roles)>=2
    # Every opaque green or literal white/rose flower face has been given an explicit role.
    assert not any(key in ('green','green_dark','arc_ivory','arc_rose') for key in R.face_keys(mesh))


@pytest.mark.parametrize('name,args', [('pine',(0,0,0)),('maple',(0,0,0)),('shrub',(0,0,0)),('shrub',(0,0,0,.6,'green')),('grass_patch',(0,0,0,2))])
def test_southwest_embedded_plants_have_roles_and_keep_trunks_and_ground_rigid(name,args):
    source=ast.parse((WORLD/'regions/southwest/mesh.py').read_text())
    palette=next(ast.literal_eval(node.value) for node in source.body if isinstance(node,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='PALETTE' for t in node.targets))
    owner=functions(Path('regions/southwest/temple.py'),[name,'cv'],PALETTE=palette)
    mesh=Faces();owner[name](mesh,*args)
    roles=[R.key_role(key) for key in R.face_keys(mesh)]
    assert any(role>0 for role in roles)
    if name in ('pine','maple'):assert roles[0]==0 # trunk
    if name=='grass_patch':assert roles[0]==0 and 2 in roles # flat paint versus upright blades


def test_explicit_role_annotations_never_rewrite_surface_selection_keys():
    owner=functions(Path('regions/hidamari/plaza.py'),['planter','bloom'])
    mesh=Faces();owner['planter'](mesh,0,0,0)
    assert 'green' in mesh.keys and 'arc_ivory' in mesh.keys
    assert 'groundcover_leaf' not in mesh.keys and 'flower' not in mesh.keys
    assert 'groundcover_leaf' in R.face_keys(mesh) and 'flower' in R.face_keys(mesh)


def test_current_textured_plant_props_explicitly_declare_bounded_authored_policy():
    import struct,json
    for region,slug in [('hidamari','planter_box'),('hidamari','bonsai_shelf'),('hidamari','potted_plants'),('treehouse','planter')]:
        path=WORLD.parent/f'assets/{region}/props/{slug}/{slug}.glb'
        data=path.read_bytes();size=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+size])
        triangles=sum(doc['accessors'][p['indices']]['count']//3 for mesh in doc['meshes'] for p in mesh['primitives'])
        assert triangles<=R.AUTHORED_BUDGET,(slug,triangles)
    # Execute the real treehouse source-owner entrypoint, rather than matching comments.
    owner=functions(Path('regions/treehouse/props.py'),['one'],SRC=Path('sources'),OUT=Path('exports'),
                    SIZE={},PROPS={'planter':[0,0,0,1]},TURN={},TARGET={'planter':.1},SOLID=set(),
                    fit=lambda *args,**kwargs:kwargs)
    assert owner['one']('planter')['foliage'] is True
    tree=ast.parse((WORLD/'regions/hidamari/props.py').read_text())
    call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
              and n.func.attr=='fit' and any(k.arg=='foliage' for k in n.keywords))
    condition=next(k.value for k in call.keywords if k.arg=='foliage')
    for slug in ('planter_box','bonsai_shelf','potted_plants'):
        assert eval(compile(ast.Expression(condition),'policy','eval'),{'slug':slug})
    assert not eval(compile(ast.Expression(condition),'policy','eval'),{'slug':'street_bench'})


def test_stand_live_shoot_colours_keep_their_explicit_thin_role():
    tree=ast.parse((WORLD/'regions/southwest/stand.py').read_text())
    body=[node for node in tree.body if isinstance(node,ast.Assign)
          and any(isinstance(t,ast.Name) and t.id in ('SHOOT','SHOOT_LIGHT') for t in node.targets)]
    owner={'foliage_roles':R}
    exec(compile(ast.Module(body=body,type_ignores=[]),'stand shoots','exec'),owner)
    assert tuple(owner['SHOOT'])==(.10,.18,.03) and tuple(owner['SHOOT_LIGHT'])==(.17,.26,.05)
    assert all(R.key_role(owner[key].foliage_key)==2 for key in ('SHOOT','SHOOT_LIGHT'))


@pytest.fixture
def brine(monkeypatch):
    monkeypatch.syspath_prepend(str(WORLD))
    monkeypatch.syspath_prepend(str(WORLD/'regions'))
    from brinecove import kit
    from brinecove.geom import Builder
    return kit,Builder


@pytest.mark.parametrize('name,args',[('flower_box',(0,0,0,0,0,0)),('banana',(0,0,0)),('vine',(0,0,0))])
def test_brinecove_generic_painted_plants_have_explicit_roles_and_keep_rigid_parts(brine,name,args):
    kit,Builder=brine;b=Builder('Mixed')
    getattr(kit,name)(b,*args)
    roles=[R.key_role(key) for key in R.face_keys(b)]
    assert any(roles) and 0 in roles
    assert all(isinstance(key,str) for key in b.mats)
    if name=='banana':assert roles[-12:]==[2]*12
    if name=='flower_box':
        assert roles[:6]==[0]*6 # the container keeps wood, collision and source geometry
        assert set(b.mats)=={'wood_dark','jungle','jungle_light','blossom','coral','gold','blossom_pale','cream'}
        assert all(role>0 for role in roles[6:])


def test_brinecove_leaf_painted_fruit_remains_rigid(brine):
    kit,Builder=brine;found=0
    for seed in range(40):
        b=Builder('Market');kit.goods(b,0,0,0,rng=random.Random(seed))
        for material,key in zip(b.mats,R.face_keys(b)):
            if material=='leaf_sun':
                found+=1;assert R.key_role(key)==0
    assert found>0


def test_brinecove_tile_split_preserves_roles_through_dropped_faces(brine):
    _,Builder=brine;b=Builder('Mixed')
    b.tri((0,0,0),(1,0,0),(0,1,0),R.SurfaceKey('leaf_sun','rigid'))
    b.tri((0,0,0),(0,0,0),(0,0,0),'stone') # dropped, so role indices must be remapped
    b.tri((2,0,0),(3,0,0),(2,1,0),R.SurfaceKey('jungle','groundcover_leaf'))
    owner=functions(Path('regions/brinecove/build.py'),['split'])
    from brinecove.geom import distinct_corners
    owner.update(R=S(OUTER=(-10,-10,10,10)),Builder=Builder,TILE=256.,soft=lambda key:False,
                 distinct_corners=distinct_corners)
    parts,_,_,degenerate=owner['split'](b,'Mixed',None)
    assert degenerate==1 and len(parts)==1
    part=next(iter(parts.values()))
    assert [R.key_role(key) for key in R.face_keys(part)]==[0,2]
    assert part.mats==['leaf_sun','jungle']


def test_pier_ornamental_grass_keeps_thin_roles_and_rigid_planters(monkeypatch):
    monkeypatch.syspath_prepend(str(WORLD))
    spec=importlib.util.spec_from_file_location('pier_geom',WORLD/'regions/skatepark/geom.py')
    geom=importlib.util.module_from_spec(spec);spec.loader.exec_module(geom)
    owner=functions(Path('regions/skatepark/features.py'),['gardens'],MeshData=geom.MeshData)
    furniture,grass=owner['gardens']()
    assert len(grass.faces)==4320
    assert {R.key_role(key) for key in R.face_keys(grass)}=={2}
    assert {R.key_role(key) for key in R.face_keys(furniture)}=={0}
    # Role tags do not alter the visible concrete texture selected for the blades.
    assert {geom.surface_key(tag,cols) for tag,cols in zip(grass.tags,grass.colors)}=={'concrete'}
    fspec=importlib.util.spec_from_file_location('pier_foliage',WORLD.parent/'foliage_system.py')
    foliage=importlib.util.module_from_spec(fspec);fspec.loader.exec_module(foliage)
    source=dict(path='/Game/SkatePark/SM_SkateParkPlanting',kind='tree',classification='roles',
                materials=[dict(path='M_Pier_concrete',foliage=False)],vertices=[],faces=[])
    for face in grass.faces:
        indices=[]
        for index in face:
            indices.append(len(source['vertices']))
            source['vertices'].append(dict(p=[x*100 for x in grass.verts[index]],n=[0,0,1],uv=[0,0],
                                          c=[.1,.2,.1,0],uvs=[[0,0]]*5+[[2.,R.MARKER]]))
        source['faces'].append(dict(v=indices,s=0))
    product=foliage.build(source)
    assert not product['coverage'] # thin grass never authorizes solid crown patches
    original={tuple(vertex['p']) for vertex in source['vertices']}
    assert all(tuple(v['p']) in original for level in product['levels'] for v in level['vertices'])
    for level in product['levels']:
        windings={tuple(tuple(level['vertices'][i]['p']) for i in face['v']) for face in level['faces']}
        for winding in windings:
            reverse=winding[::-1]
            assert any(reverse[i:]+reverse[:i] in windings for i in range(3))
    assert len(product['levels'][-1]['faces'])<len(grass.faces)//10
