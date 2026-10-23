"""Canonical complete ground data precedes independently bounded render products."""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from atelier import encoded_glb
from atelier.build import check_modules
from atelier.gltf import glb_parts,glb_pack

GAME=Path(__file__).resolve().parents[1]
LIBRARY=GAME/'assets/belmonte'


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world'))
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    return tuple(importlib.import_module('belmonte.'+key) for key in
                 ('surface_data','source_ground','plan_ground','model_sources'))


def test_real_committed_final_ground_data_has_exact_bytes_before_atomic_exports(tmp_path,modules):
    surfaces,source,planner,definitions=modules
    manifest=json.loads((LIBRARY/'source.json').read_text())
    entry=next(row for row in manifest['meshes'] if row['name']=='SM_BM_BT_Terrain_0_0')
    definition=tmp_path/'definition.json';definition.write_text(json.dumps(definitions.project(dict(meshes=[entry]))[entry['name']]))
    path=tmp_path/(entry['name']+'.surface')
    source.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(LIBRARY),'--output',str(path)])
    value,data=surfaces.read(path,owner=entry['name'])
    assert data==(LIBRARY/entry['path']).read_bytes() and value['triangles']==entry['triangles']
    before=path.stat().st_mtime_ns
    source.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(LIBRARY),'--output',str(path)])
    assert path.stat().st_mtime_ns==before
    plan=planner.main(['--asset',entry['name'],'--surface',str(path),'--output',str(tmp_path/'plan')])
    assert sum(row['triangles'] for row in plan['pieces'])==entry['triangles']
    for row in plan['pieces']:
        assert row['triangles']<=32768
        encoded_glb.export(tmp_path/'plan'/row['payload'],tmp_path/'exports'/row['name'])
    assert path.read_bytes().startswith(surfaces.MAGIC)
    assert not list(tmp_path.glob('*.glb'))


def test_whole_surface_survives_independent_forced_small_pieces_with_exact_winding(tmp_path,modules):
    surfaces,_,_,_=modules
    from test_belmonte_ground_pieces import GROUND,model,triangles
    data=model();entry=dict(name='SM_BM_NorthApron',sha256=hashlib.sha256(data).hexdigest(),
        bounds_m=[[0.,0.,0.],[20.,20.,0.]],triangles=4,slots=['Ground'],path='glb/SM_BM_NorthApron.glb')
    path=tmp_path/(entry['name']+'.surface');surfaces.write(path,entry,data)
    saved,actual=surfaces.read(path,owner=entry['name'])
    _,rows=GROUND.planned(saved,actual,triangle_limit=1)
    assert len(rows)==4
    assert sum((triangles(payload) for _,_,_,payload in rows),Counter())==triangles(data)
    assert surfaces.read(path,owner=entry['name'])[1]==data


@pytest.mark.parametrize('fault',['hash','count','owner','link','unsupported'])
def test_invalid_query_source_refuses_without_altering_external_or_prior_bytes(tmp_path,modules,fault):
    surfaces,_,_,_=modules
    from test_belmonte_ground_pieces import model
    data=model();entry=dict(name='SM_BM_NorthApron',sha256=hashlib.sha256(data).hexdigest(),triangles=4)
    path=tmp_path/'SM_BM_NorthApron.surface';surfaces.write(path,entry,data);before=path.read_bytes()
    outside=tmp_path/'outside';outside.write_bytes(b'keep')
    if fault=='hash':entry['sha256']='0'*64
    if fault=='count':entry['triangles']+=1
    if fault=='owner':entry['name']='Foreign'
    if fault=='link':path.unlink();path.symlink_to(outside)
    if fault=='unsupported':
        doc,binary=glb_parts(data);doc['nodes'][0]['scale']=[1,1,1];data=glb_pack(doc,binary)
        entry['sha256']=hashlib.sha256(data).hexdigest()
    with pytest.raises(ValueError):surfaces.write(path,entry,data)
    assert outside.read_bytes()==b'keep'
    if fault!='link':assert path.read_bytes()==before


def test_pure_ground_writer_matches_immutable_original_byte_encoder(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(GAME/'world/regions'))
    monkeypatch.syspath_prepend(str(GAME/'world'))
    terrain=importlib.import_module('belmonte.terrain')
    witness=json.loads((GAME/'tests/fixtures/belmonte-ground-writer.json').read_text())
    assert witness['revision']=='5e73f22c'
    assert hashlib.sha256(witness['function'].encode()).hexdigest()==witness['sha256']
    namespace=dict(np=np,source=SimpleNamespace(glb_pack=glb_pack),_encode_colour=terrain._encode_colour)
    exec(compile(witness['function'],'immutable-original-ground-writer','exec'),namespace)
    entry=next(row for row in json.loads((LIBRARY/'source.json').read_text())['meshes'] if row['name']=='SM_BM_BT_Terrain_4_3')
    doc,arrays=terrain._read_glb(LIBRARY/entry['path'])
    args=(arrays['position'],arrays['normal'],arrays['uv'],arrays['colour'],arrays['faces'])
    path=tmp_path/'original.glb';namespace['_write_glb'](path,deepcopy(doc),*args)
    assert terrain.encoded_tile(deepcopy(doc),*args)==path.read_bytes()


def test_plain_ground_constructor_refuses_each_authored_carved_tile_before_any_output(tmp_path,modules):
    _,source,_,definitions=modules
    from belmonte.ground_names import VALLEY_CARVED_TILES
    assert VALLEY_CARVED_TILES=={'SM_BM_BT_Terrain_4_3','SM_BM_BT_Terrain_5_2',
                                 'SM_BM_BT_Terrain_5_3','SM_BM_BT_Terrain_6_2'}
    projected=definitions.project(json.loads((LIBRARY/'source.json').read_text()))
    for key in VALLEY_CARVED_TILES:
        definition=tmp_path/'selected.json';definition.write_text(json.dumps(projected[key]))
        output=tmp_path/(key+'.surface')
        with pytest.raises(ValueError,match='carved terrain'):
            source.main(['--asset',key,'--definition',str(definition),'--library',str(LIBRARY),'--output',str(output)])
        assert not output.exists()


def test_ground_graph_selects_final_carving_and_has_no_export_or_assembly_input(tmp_path,modules):
    spec=importlib.util.spec_from_file_location('belmonte_ground_graph_test',GAME/'belmonte_atomic_build.py')
    recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
    steps=recipe.ground_steps(SimpleNamespace(out=tmp_path.resolve()))
    check_modules(steps)
    sources=[step for step in steps if '.final_source.' in step.name]
    planners=[step for step in steps if '.geometry.' in step.name]
    assert len(sources)==len(planners)==56
    line=GAME/'assets/vehicles/belmonte-train/line.json'
    carved=[step for step in sources if step.commands[0].script.name=='carve_ground.py']
    assert len(carved)==4
    for step in sources:
        assert (line in step.inputs)==(step in carved)
        if step not in carved:assert all(path.name!='terrain.py' for path in step.inputs)
    for step in planners:
        key=step.name.rsplit('.',1)[1]
        assert step.reads==['belmonte.final_surface.'+key]
        assert not any(path.suffix=='.glb' or path.name=='build-report.json' for path in step.inputs)
        assert all(path.name not in ('source_ground.py','carve_ground.py','terrain.py') for path in step.inputs)
