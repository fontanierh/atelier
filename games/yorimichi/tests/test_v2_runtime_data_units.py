"""Actual data.stage row, ordinary recipe binding and isolated staged runtime bytes."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2 import recipe_dependencies,recipe_inputs,recipe_compiler,recipe_job

ROOT=Path(__file__).resolve().parents[3];GAME=ROOT/'games/yorimichi'


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


units=load('games/yorimichi/v2_runtime_data_units.py','runtime_stage_units_test')


@pytest.fixture(scope='module')
def declaration():
    recipe=load('games/yorimichi/build.py','runtime_stage_actual_recipe_test')
    rows=recipe_dependencies.extract(recipe.steps(NS(out=ROOT/'build/yorimichi',game='yorimichi',uproject=GAME/'unreal/Yorimichi.uproject')),checkout=ROOT,build_root=ROOT/'build')
    original=next(row for row in rows if row['id']=='data.stage');result=units.lower(rows,checkout=ROOT);row=result['rows'][0]
    roots=[];products={}
    for owner in rows:
        for index,product in enumerate(owner['products']):
            paths=[*product['paths'],*product['optional_paths']];products[product['id']]=(owner['id'],'product'+str(index),paths)
            roots.extend((path,owner['id'],'product'+str(index)) for path in paths)
        for index,path in enumerate(owner['outputs']):
            if not any((path==p or path.startswith(p+'/')) and unit==owner['id'] for p,unit,_ in roots):roots.append((path,owner['id'],'output'+str(index)))
    lowered=recipe_inputs.lower_inputs(row,rows=rows,roots=roots,products=products,checkout=ROOT)
    return rows,original,result,lowered


def test_actual_row_keeps_complete_original_roster_and_declared_dependencies(declaration):
    rows,original,result,lowered=declaration;row=result['rows'][0]
    assert result['aliases']=={'data.stage':('data.stage',)} and original['commands'][0]['fn']['qualname']=='stage_data'
    for key in original:
        if key not in ('commands','code','inputs'):assert row[key]==original[key]
    assert all(entry in row['inputs'] for entry in original['inputs']) and set(original['code'])<=set(row['code'])
    assert row['commands'][0]['fn']['source']==units.BODY and row['commands'][0]['fn']['qualname']=='stage'
    assert not row['commands'][0]['fn']['closure'] and len(row['commands'][0]['fn']['defaults'])==4
    table=row['commands'][0]['fn']['defaults'][0]
    assert [destination['path'] for _,destination in table]==row['outputs']
    assert all(any(source['path']==path or source['path'].startswith(path+'/') for path in lowered['paths']) for source,_ in table)
    assert not any(p.endswith('/kart/cockpit.json') or p.endswith('/racing/belmonte_courses.json') for p in row['outputs'])
    assert 'games/yorimichi/world/racing/courses.py' in row['code'] and 'games/yorimichi/world/regions/belmonte/source.py' in row['code']
    assert len(row['outputs'])>40 and original['commands'][0]['fn']['source']==units.ORIGINAL


def staged_view(tmp_path,declaration):
    rows,_,result,lowered=declaration;row=result['rows'][0];view=tmp_path/'view';view.mkdir()
    for relative in row['code']:
        source=ROOT/relative;target=view/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    # Materialize each real declared source needed by the course reader. Other runtime
    # generated files use unique test bytes at their exact declared bound paths.
    for entry in row['inputs']:
        relative=entry['path'];source=ROOT/relative;target=view/relative
        if not relative.startswith('build/') and source.is_file() and not target.exists():target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    table=row['commands'][0]['fn']['defaults'][0];expected={}
    for index,(source,destination) in enumerate(table):
        path=view/source['path'];path.parent.mkdir(parents=True,exist_ok=True)
        if source['path'].startswith('build/'):path.write_bytes(('required runtime '+str(index)+'\n').encode())
        expected[destination['path']]=path.read_bytes();os.utime(path,ns=(1234567890000000000+index,1234567890000000000+index))
    callback=recipe_job.bind(recipe_compiler._binding(row['commands'][0]['fn']),view)
    return view,callback,expected,table


def test_real_bound_zero_argument_callback_copies_exact_bytes_and_preserves_warm_neighbors(tmp_path,declaration):
    view,callback,expected,table=staged_view(tmp_path,declaration)
    sentinel=view/'games/yorimichi/unreal/Content/Data/keep-owner.json';sentinel.parent.mkdir(parents=True);sentinel.write_bytes(b'other owner')
    callback()
    for source,destination in table:
        src=view/source['path'];dst=view/destination['path'];assert dst.read_bytes()==expected[destination['path']]
        assert dst.stat().st_mtime_ns==src.stat().st_mtime_ns
    callback()
    assert sentinel.read_bytes()==b'other owner'
    assert not (sentinel.parent/'racing/belmonte_courses.json').exists() and not (sentinel.parent/'kart/cockpit.json').exists()


@pytest.mark.parametrize('damage',['missing','corrupt','surface'])
def test_invalid_original_courses_fail_before_any_runtime_write(tmp_path,declaration,damage):
    view,callback,_,_=staged_view(tmp_path,declaration)
    course=view/'games/yorimichi/world/racing/belmonte_courses.json'
    if damage=='missing':course.unlink()
    elif damage=='corrupt':course.write_text('{invalid')
    else:
        scene=json.loads((view/'games/yorimichi/assets/belmonte/source.json').read_text());model=next(m for m in scene['meshes'] if m['name']=='SM_BM_BHip_Course')
        (view/'games/yorimichi/assets/belmonte'/model['path']).write_bytes(b'corrupt committed course surface')
    with pytest.raises((ValueError,OSError)):callback()
    assert not (view/'games/yorimichi/unreal/Content/Data').exists()


def test_missing_late_runtime_source_fails_before_writes(tmp_path,declaration):
    view,callback,_,table=staged_view(tmp_path,declaration);(view/table[-1][0]['path']).unlink()
    with pytest.raises(ValueError):callback()
    assert not (view/'games/yorimichi/unreal/Content/Data').exists()


@pytest.mark.parametrize('damage',['output','original','validation','owner'])
def test_lowering_refuses_incomplete_or_unowned_original_row(declaration,damage):
    rows=deepcopy(declaration[0]);row=next(r for r in rows if r['id']=='data.stage')
    if damage=='output':row['outputs'].pop()
    elif damage=='original':row['commands'][0]['fn']['qualname']='other'
    elif damage=='validation':row['inputs']=[r for r in row['inputs'] if not r['path'].endswith('belmonte_courses.json')]
    else:
        for owner in rows:
            owner['outputs']=[p for p in owner['outputs'] if not p.endswith('/world.json')]
            for product in owner['products']:product['paths']=[p for p in product['paths'] if not p.endswith('/world.json')]
    with pytest.raises(ValueError):units.lower(rows,checkout=ROOT)


def test_normal_recipe_view_preparation_and_zero_argument_execution(tmp_path,monkeypatch,declaration):
    _,_,result,lowered=declaration;row=result['rows'][0]
    job_dir=tmp_path/'job';job_dir.mkdir();(job_dir/recipe_job.RUNTIME).mkdir()
    code=sorted(lowered['code'])
    for relative in code:
        target=job_dir/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    table=row['commands'][0]['fn']['defaults'][0];wanted={s['path']:('frozen runtime '+str(i)).encode() for i,(s,_) in enumerate(table)}
    incoming=[]
    for index,(logical,staged) in enumerate(lowered['paths'].items()):
        path=job_dir/staged;path.parent.mkdir(parents=True,exist_ok=True)
        if staged.endswith('.tree.tar'):
            children=[p for p in wanted if p.startswith(logical+'/')]
            source=tmp_path/'frozen'/str(index)
            source.parent.mkdir(parents=True,exist_ok=True)
            if children:
                source.mkdir()
                for child in children:
                    member=source/Path(child).relative_to(logical);member.parent.mkdir(parents=True,exist_ok=True);member.write_bytes(wanted[child])
            else:source.write_bytes(wanted.get(logical,b'unread declared producer output'))
            recipe_job.pack_root(source,path)
        else:shutil.copyfile(ROOT/logical,path)
        incoming.append({'path':staged})
    emitted=[{'path':path,'file':'outputs/'+str(i)+'.tree.tar','required':True} for i,path in enumerate(row['outputs'])]
    recipe={'version':1,'commands':[recipe_compiler._command(row['commands'][0])],'paths':lowered['paths'],'outputs':emitted,'verify':None}
    view,_,_=recipe_job.prepare_view({'code':code,'inputs':incoming,'params':{'recipe':recipe}},job_dir)
    expected={d['path']:(view/s['path']).read_bytes() for s,d in table}
    # The original module remains declared code, but must never initialize or run.
    (view/units.ORIGINAL).chmod(0o644);(view/units.ORIGINAL).write_text("raise AssertionError('old runtime module executed')\n")
    output=tmp_path/'packed';output.mkdir();monkeypatch.chdir(view);monkeypatch.setattr(sys,'path',list(sys.path))
    recipe_job.run(NS(params={'recipe':recipe},output_dir=output))
    for i,path in enumerate(row['outputs']):
        decoded=tmp_path/'decoded'/str(i);recipe_job.unpack_root(output/'outputs'/f'{i}.tree.tar',decoded)
        assert decoded.read_bytes()==expected[path]
