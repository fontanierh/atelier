"""Whole final queries and bounded native members are independent products."""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest
from atelier import build
from atelier import build_cache, build_inputs
from atelier.gltf import glb_pack, glb_parts
from atelier.model_files import retain_files

GAME = Path(__file__).resolve().parents[1]
SCRIPT = GAME/'world/regions/belmonte/ground_pieces.py'
SPEC = importlib.util.spec_from_file_location('bounded_final_ground', SCRIPT)
GROUND = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(GROUND)


def model():
    points=[]
    for x,y in ((2.,2.),(18.,2.),(2.,18.),(18.,18.)):
        points.extend(((x,0.,-y),(x+1.,0.,-y),(x,0.,-y-1.)))
    raw=b''.join(struct.pack('<3f',*p) for p in points)+struct.pack('<12H',*range(12))
    doc=dict(asset={'version':'2.0'}, buffers=[{'byteLength':len(raw)}],
             bufferViews=[dict(buffer=0,byteOffset=0,byteLength=144),dict(buffer=0,byteOffset=144,byteLength=24)],
             accessors=[dict(bufferView=0,componentType=5126,type='VEC3',count=12),
                        dict(bufferView=1,componentType=5123,type='SCALAR',count=12)],
             materials=[{'name':'BM_000_Ground'}],nodes=[{'mesh':0}],scenes=[{'nodes':[0]}],scene=0,
             meshes=[{'primitives':[dict(attributes={'POSITION':0},indices=1,material=0)]}])
    return glb_pack(doc,raw)


def triangles(raw):
    doc,binary=glb_parts(raw);result=[]
    for primitive in doc['meshes'][0]['primitives']:
        pos=doc['accessors'][primitive['attributes']['POSITION']]
        view=doc['bufferViews'][pos['bufferView']];offset=view.get('byteOffset',0)
        points=[binary[offset+i*12:offset+(i+1)*12] for i in range(pos['count'])]
        index=doc['accessors'][primitive['indices']];view=doc['bufferViews'][index['bufferView']]
        offset=view.get('byteOffset',0);indices=struct.unpack('<'+'H'*index['count'],binary[offset:offset+index['count']*2])
        result.extend(tuple(points[i] for i in indices[k:k+3]) for k in range(0,len(indices),3))
    return Counter(result)


@pytest.fixture
def prepared(tmp_path):
    raw=model();folder=tmp_path/'belmonte';(folder/'glb').mkdir(parents=True)
    surfaces=[];pieces=[]
    for name in sorted(GROUND.NORTH):
        path=folder/'glb'/(name+'.glb');path.write_bytes(raw)
        entry=dict(name=name,path='glb/'+path.name,sha256=hashlib.sha256(raw).hexdigest(),
                   bounds_m=[[0.,0.,0.],[20.,20.,0.]],triangles=4,slots=['Ground'])
        surface,current=GROUND.prepare(entry,path,folder,triangle_limit=1)
        surfaces.append(surface);pieces.extend(row[0] for row in current)
    return folder,raw,surfaces,pieces


def test_whole_queries_survive_native_parent_retirement(prepared,tmp_path):
    folder,raw,surfaces,pieces=prepared
    assert max(p['triangles'] for p in pieces)==1
    for surface in surfaces:
        assert (folder/surface['path']).read_bytes()==raw
        children=[p for p in pieces if p['name'].startswith(surface['name']+'_Piece')]
        assert sum((triangles((folder/p['path']).read_bytes()) for p in children),Counter())==triangles(raw)
    GROUND.publish(folder,surfaces,[100.,-200.,300.])
    retired=retain_files(folder/'glb',[Path(p['path']).name for p in pieces])
    assert set(retired)=={name+'.glb' for name in GROUND.NORTH}
    output=tmp_path/'products/belmonte/ground.json'
    GROUND.project(folder,output)
    assert json.loads(output.read_text())==GROUND.load(folder)
    for surface in surfaces: assert (folder/surface['path']).read_bytes()==raw
    result=subprocess.run([sys.executable,'-I','-S',str(SCRIPT),str(folder),str(output)],
                          cwd=tmp_path,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr


def test_small_ground_keeps_its_exact_native_report_entry_and_bytes(tmp_path):
    raw=model();path=tmp_path/'glb/SM_BM_NorthApron.glb';path.parent.mkdir();path.write_bytes(raw)
    entry=dict(name=path.stem,path='glb/'+path.name,sha256=hashlib.sha256(raw).hexdigest(),
               bounds_m=[[0.,0.,0.],[20.,20.,0.]],triangles=4,slots=['Ground'])
    _,current=GROUND.prepare(entry,path,tmp_path)
    assert current==[(entry,[0],True)] and current[0][0] is entry
    assert path.read_bytes()==raw


def test_linked_membership_refuses_before_retiring_any_query(prepared,tmp_path):
    folder,raw,surfaces,_=prepared
    stale=folder/'ground/glb/stale.glb';stale.write_bytes(raw)
    other=tmp_path/'unrelated.json';other.write_text('preserve')
    (folder/'ground/membership.json').symlink_to(other)
    with pytest.raises(ValueError,match='unlinked'):
        GROUND.publish(folder,surfaces,[0.,0.,0.])
    assert stale.read_bytes()==raw
    assert other.read_text()=='preserve'


def test_projection_succeeds_through_the_actual_audited_build(prepared,tmp_path,monkeypatch):
    folder,_,surfaces,_=prepared
    GROUND.publish(folder,surfaces,[0.,0.,0.])
    output=folder.parent/'products/belmonte/ground.json'
    ctx=SimpleNamespace(game='fixture',out=folder.parent,logs=folder.parent/'logs',
                        stamps=folder.parent/'stamps',env=lambda extra=():dict(os.environ)|dict(extra))
    step=build.Step('ground',[build.Python(SCRIPT,(str(folder),str(output)))],
        inputs=[*build_inputs.local_imports(SCRIPT),folder/'ground'],
        products=[build.Product('ground',(output,))],audit=True,cache=True)
    store=build_cache.Store(tmp_path/'store')
    monkeypatch.setattr(build,'Context',lambda *a,**k:ctx)
    monkeypatch.setattr(build,'load_recipe',lambda game:SimpleNamespace(steps=lambda ctx:[step]))
    monkeypatch.setattr(build_cache,'Store',lambda:store)
    monkeypatch.setattr(build_cache,'tool_context',lambda *a,**k:{'test':'fixed interpreter'})
    messages=[]
    assert build.build('fixture',echo=messages.append)==0,messages
    report=json.loads((ctx.logs/'ground.audit.json').read_text())
    assert report['passed'] and not report['violations']
    assert json.loads(output.read_text())==GROUND.load(folder)


@pytest.mark.parametrize('change',['move','remove','duplicate'])
def test_actual_producer_refuses_nonidentity_or_missing_ground_placements(tmp_path,monkeypatch,change):
    import ast
    identity=dict(translation_cm=[0.,0.,0.],rotation_xyzw=[0.,0.,0.,1.],scale=[1.,1.,1.])
    row=dict(asset='ground',transform=identity)
    data=dict(meshes=[dict(name='SM_BM_BT_Terrain_0_0',source_asset='ground')],placements=[row])
    if change=='move':row['transform']=dict(identity,translation_cm=[100.,0.,0.])
    elif change=='remove':data['placements']=[]
    else:data['placements'].append(deepcopy(row))
    script=SCRIPT.with_name('build.py')
    main=next(n for n in ast.parse(script.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='main')
    namespace=dict(OUT=tmp_path/'out',source=SimpleNamespace(manifest=lambda:data),ground_pieces=GROUND)
    namespace['finish_surfaces']=lambda data:pytest.fail('Invalid ground must refuse before geometry/material assembly')
    with pytest.raises(ValueError,match='exactly one identity'):
        exec(compile(ast.Module(body=main.body,type_ignores=[]),str(script),'exec'),namespace)


@pytest.mark.parametrize('fault',['changed','missing','linked','extra','duplicate','missing-country','schema','origin'])
def test_incomplete_or_changed_query_product_refuses(prepared,fault):
    folder,raw,surfaces,pieces=prepared
    GROUND.publish(folder,surfaces,[0.,0.,0.]);path=folder/'ground/membership.json'
    data=json.loads(path.read_text());query=folder/surfaces[0]['path']
    if fault=='changed':query.write_bytes(raw+b'changed')
    elif fault=='missing':query.unlink()
    elif fault=='linked':
        query.unlink();query.symlink_to(folder/'glb'/Path(surfaces[0]['path']).name)
    elif fault=='extra':(query.parent/'stale.glb').write_bytes(raw)
    elif fault=='duplicate':data['surfaces'].append(deepcopy(data['surfaces'][0]))
    elif fault=='missing-country':data['surfaces']=[e for e in data['surfaces'] if e['name']!='SM_BM_NorthCountry']
    elif fault=='schema':data['schema']=True
    else:data['origin_cm']=[False,0,0]
    path.write_text(json.dumps(data))
    with pytest.raises((ValueError,OSError)):GROUND.load(folder)


def test_ground_and_native_consumers_use_distinct_real_products():
    ctx=build.Context('yorimichi',create=False);recipe=build.load_recipe('yorimichi')
    steps={step.name:step for step in recipe.steps(ctx)}
    assert steps['world.gondola_ground_inputs'].needs==['world.gondola_ground_sources']
    assert 'world.belmonte.ground' not in steps['world.gondola_ground_inputs'].needs
    assert 'world.belmonte' not in steps['world.gondola_ground_inputs'].needs
    assert 'belmonte.ground' in steps['world.map'].reads
    assert 'belmonte.ground' not in steps['unreal.belmonte'].reads
    assert steps['world.belmonte.ground'].products[0].name=='belmonte.ground'
    assert not any(p.name=='SM_BM_NorthApron.uasset' for p in steps['unreal.belmonte'].outputs)
