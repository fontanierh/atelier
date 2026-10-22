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
    owner=functions(Path('regions/brinecove/build.py'),['split','bounded_parts'])
    from brinecove.geom import distinct_corners
    owner.update(R=S(OUTER=(-10,-10,10,10)),Builder=Builder,TILE=256.,soft=lambda key:False,
                 distinct_corners=distinct_corners,MIXED_TRIANGLE_LIMIT=32768)
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



def test_florist_buckets_classify_all_petals_and_leaves_but_keep_stems_rigid():
    owner=functions(Path('regions/hidamari/kit/bakery_western.py'),['bucket','bunch'])
    mesh=Faces();owner['bucket'](mesh,0,0,0,17)
    pairs=list(zip(mesh.keys,[R.key_role(key) for key in R.face_keys(mesh)]))
    assert pairs[0]==('bw_bucket',0)
    assert len(pairs)==71
    assert all(role==0 for key,role in pairs if key=='green_dark')
    assert all(role==2 for key,role in pairs if key in ('green','arc_ivory','arc_rose','arc_bloom'))
    assert {key for key,role in pairs if role==2}=={'green','arc_ivory','arc_rose','arc_bloom'}


def test_persimmon_fallen_leaves_are_litter_and_fruit_and_trunk_stay_rigid():
    owner=functions(Path('regions/hidamari/kit/kura.py'),['persimmon'])
    mesh=Faces();owner['persimmon'](mesh,0,0,17)
    pairs=list(zip(mesh.keys,[R.key_role(key) for key in R.face_keys(mesh)]))
    assert any(key=='kura_fallen' for key,role in pairs)
    assert all(role==2 for key,role in pairs if key=='kura_fallen')
    assert all(role==0 for key,role in pairs if key in ('kura_bark','kura_twig','kura_fruit'))
    assert all(role==1 for key,role in pairs if key in ('kura_leaf_a','kura_leaf_b'))



def test_lake_islet_grass_is_thin_while_rocks_stay_rigid():
    owner=functions(Path('regions/forest_lake/details.py'),['islet'])
    rocks,plants=Faces(),Faces();owner['islet'](rocks,plants)
    assert len(plants.faces)==30
    assert {R.key_role(key) for key in R.face_keys(plants)}=={2}
    assert {R.key_role(key) for key in R.face_keys(rocks)}=={0}


def test_belmonte_current_authored_sources_keep_all_original_data(tmp_path,monkeypatch):
    from atelier.gltf import glb_parts
    monkeypatch.syspath_prepend(str(WORLD))
    monkeypatch.syspath_prepend(str(WORLD/'regions'))
    from belmonte import foliage,source
    entries={entry['name']:entry for entry in source.manifest()['meshes']}
    assert len(foliage.AUTHORED)==9
    for name in foliage.AUTHORED:
        entry=entries[name]
        assert entry['triangles']<=R.AUTHORED_BUDGET
        data=(source.LIBRARY/entry['path']).read_bytes()
        doc,original=glb_parts(data)
        path=tmp_path/(name+'.glb');path.write_bytes(data);metadata=foliage.prepare(path)
        assert metadata['source_sha256']==entry['sha256']
        assert metadata['sha256']==source.sha(path)
        assert metadata['sha256']!=metadata['source_sha256']
        prepared,binary=glb_parts(path.read_bytes())
        assert binary[:len(original)]==original
        assert prepared['materials']==doc['materials']
        assert prepared['nodes']==doc['nodes']
        for old,new in zip(doc['meshes'],prepared['meshes']):
            for p,q in zip(old['primitives'],new['primitives']):
                assert all(q[k]==v for k,v in p.items() if k!='attributes')
                assert all(q['attributes'][k]==v for k,v in p['attributes'].items())
                assert all('TEXCOORD_'+str(i) in q['attributes'] for i in range(6))
                a=prepared['accessors'][q['attributes']['TEXCOORD_5']]
                view=prepared['bufferViews'][a['bufferView']]
                uv=np.frombuffer(binary,dtype='<f4',count=a['count']*2,offset=view['byteOffset']).reshape(-1,2)
                assert np.all(uv==[3.,R.MARKER])


def test_arcade_floor_litter_roles_do_not_depend_on_the_visible_paint():
    mesh=Faces()
    owner=functions(Path('regions/hidamari/arcade.py'),['floor','palette'])
    owner['v'].Mesh=lambda name:mesh
    owner['floor'](lambda x,y:0.)
    paving=123*28
    assert len(mesh.faces)==paving+1700
    roles=[R.key_role(key) for key in R.face_keys(mesh)]
    assert roles[:paving]==[0]*paving
    assert roles[paving:]==[2]*1700
    assert set(mesh.keys[paving:])=={'arc_leaf','clay','arc_bloom'}
    assert set(mesh.foliage_roles)==set(range(paving,len(mesh.faces)))


@pytest.mark.parametrize('path,count,paint,minimum',[
    ('plaza.py',3300,{'sq_leaf','arc_bloom','clay'},3300),
    ('harbor.py',1000,{'h_leaf'},10000),
    ('civic_gardens.py',280,{'arc_leaf'},200),
    ('kit/shrine.py',16,{'arc_leaf'},16),
])
def test_ground_scatter_emitters_preserve_paint_and_emit_only_thin_litter(path,count,paint,minimum):
    # Execute the actual scatter loop, avoiding unrelated architecture/Blender
    # helpers. Select its authored iteration count and real paint expression.
    source=WORLD/'regions/hidamari'/path
    tree=ast.parse(source.read_text())
    loops=[node for node in ast.walk(tree) if isinstance(node,ast.For)
           and isinstance(node.iter,ast.Call) and isinstance(node.iter.func,ast.Name)
           and node.iter.func.id=='range' and len(node.iter.args)==1
           and isinstance(node.iter.args[0],ast.Constant) and node.iter.args[0].value==count
           and any(isinstance(n,ast.Constant) and n.value in paint for n in ast.walk(node)
                   if isinstance(n,ast.Constant) and isinstance(n.value,str))]
    assert len(loops)==1
    public=ast.parse((WORLD/'regions/hidamari/public_spaces.py').read_text())
    gardens=next(ast.literal_eval(n.value) for n in public.body if isinstance(n,ast.Assign)
                 and any(isinstance(t,ast.Name) and t.id=='PLAZA_GARDENS' for t in n.targets))
    mesh=Faces()
    scope={'m':mesh,'r':random.Random(690),'rng':random.Random(41),'math':math,
           'height':lambda x,y:0.,'local_height':lambda x,y:0.,'PLAZA_GARDENS':gardens}
    exec(compile(ast.Module(body=loops,type_ignores=[]),str(source),'exec'),scope)
    assert minimum<=len(mesh.faces)
    assert set(mesh.keys)==paint
    assert [R.key_role(key) for key in R.face_keys(mesh)]==[2]*len(mesh.faces)
    assert set(mesh.foliage_roles)==set(range(len(mesh.faces)))
