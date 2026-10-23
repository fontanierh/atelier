"""Immutable original serialized controls for independent Hippodrome data ownership."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GAME));sys.path.insert(0,str(GAME/'world'))
import yori
BASELINE='283329c07ea04bee34587022a3d43827468c66d7'
SOURCE='games/yorimichi/world/regions/hippodrome/build.py'


def original():
    payload=subprocess.check_output(['git','show',BASELINE+':'+SOURCE],cwd=GAME)
    value=types.ModuleType('immutable_original_hippodrome');value.__file__=str(GAME/'world/regions/hippodrome/build.py')
    exec(compile(payload,str(value.__file__),'exec'),value.__dict__)
    return value,hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize('suffix,method,index,material',[
    ('Ground','platform',0,'HD_Grass'),('Skirt','platform',1,'HD_Stone'),
    ('Track','track',None,'HD_Dirt'),('Rails','rails',None,'HD_Rail'),
    ('Lane','lane',0,'HD_Dirt'),('LaneSkirt','lane',1,'HD_Stone')])
def test_selected_source_is_original_serialized_control(tmp_path,monkeypatch,suffix,method,index,material):
    old,source_sha=original();old.OUT=tmp_path
    assert len(source_sha)==64
    # This source control binds both implementations to an explicit deterministic terrain fixture.
    import numpy as np
    monkeypatch.setattr(old.H,"north_height",lambda x,y: np.asarray(x)*.001+np.asarray(y)*.003+35.)
    from hippodrome.project_queries import project
    from hippodrome.query_context import load
    project(tmp_path/"queries.json");load(tmp_path/"queries.json")
    z=old.L.platform_height(old.H.north_height)
    mesh=getattr(old,method)(z) if method in ('platform','lane') else getattr(old,method)()
    if index is not None:mesh=mesh[index]
    path=tmp_path/('SM_HD_'+suffix+'.glb');info=mesh.save(path,material)
    module=importlib.import_module('hippodrome.plan_'+suffix.lower())
    data,current=module.construct()
    assert data==path.read_bytes()
    assert current==info
    from hippodrome.planner import plan
    from encoded_region_plan import validate
    from atelier import encoded_glb
    root=tmp_path/'plan';plan(path.stem,root,module.construct)
    value=validate(root)
    assert sum(row['triangles'] for row in value['pieces'])==info['triangles']
    for row in value['pieces']:assert row['triangles']<=32768
    if info['triangles']<=32768:assert encoded_glb.read(root/value['pieces'][0]['payload'])[1]==data


@pytest.mark.parametrize('slug',['grandstand','judges_tower','finish_post','tote_board'])
def test_committed_structure_matches_immutable_original(tmp_path,slug):
    old,_=original()
    old.OUT=tmp_path;name,info=old.structure(slug,old.L.STRUCTURES[slug])
    module=importlib.import_module('hippodrome.plan_'+slug)
    data,current=module.construct()
    assert data==(tmp_path/'glb'/(name+'.glb')).read_bytes()
    assert current==info


def test_selected_constructor_input_closures_exclude_siblings():
    from atelier.build_inputs import local_imports
    from hippodrome.atomic import assets
    rows=list(assets())
    for row in rows:
        closure=set(local_imports(row.script,(GAME/'world',GAME/'world/regions')))
        assert GAME/'world/regions/hippodrome/build.py' not in closure
        assert not any(other.script in closure for other in rows if other.key!=row.key)


def test_complete_file_assembly_and_actual_serialized_corner_conservation(tmp_path,monkeypatch):
    import numpy as np
    from atelier import encoded_glb,export_assembly
    from atelier.atomic_files import atomic_json
    from hippodrome.project_queries import project
    from hippodrome.query_context import load
    from hippodrome.planner import plan
    from hippodrome.atomic import assets,assemble
    sys.path.insert(0,str(GAME/'tools'))
    from atomic_equivalence import glb_counter
    old,_=original()
    monkeypatch.setattr(old.H,'north_height',lambda x,y:np.asarray(x)*.001+np.asarray(y)*.003+35.)
    old.OUT=tmp_path/'original';old.main()
    out=tmp_path/'actual';out.mkdir();project(out/'hippodrome_queries.json');load(out/'hippodrome_queries.json')
    items=[];parents={}
    for asset in assets():
        module=importlib.import_module('hippodrome.'+asset.script.stem)
        root=out/'plans'/asset.key;value=plan(asset.key,root,module.construct);parents[asset.key]=[]
        actual_counter=None
        for row in value['pieces']:
            key=row['name'];destination=out/'exports'/key
            encoded_glb.export(root/row['payload'],destination)
            parents[asset.key].append(key);items.append(export_assembly.Item(key,destination))
            count,triangles=glb_counter((destination/(key+'.glb')).read_bytes())
            if actual_counter is None:actual_counter=(count,triangles)
            else:
                actual_counter[0]['render'].update(count['render']);actual_counter[0]['collision'].update(count['collision'])
                actual_counter=(actual_counter[0],actual_counter[1]+triangles)
        baseline=glb_counter((old.OUT/'glb'/(asset.key+'.glb')).read_bytes())
        assert actual_counter==baseline
    region=out/'atomic_regions'/'hippodrome';region.mkdir(parents=True)
    export_assembly.assemble(items,region/'assets');atomic_json(region/'logical-pieces.json',dict(parents=parents))
    assemble(out)
    before=json.loads((old.OUT/'hippodrome.json').read_text());after=json.loads((out/'hippodrome/region/hippodrome.json').read_text())
    for row in after['meshes']:row.pop('logical_parent')
    assert before==after
    assert json.loads((old.OUT/'build-report.json').read_text())==json.loads((out/'hippodrome/region/build-report.json').read_text())
