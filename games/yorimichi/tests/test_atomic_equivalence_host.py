"""Host Git authority and subprocess-free frozen native-parser fault injection."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

GAME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GAME/'tools'))
import atomic_equivalence as eq
import atomic_equivalence_host as host
import atomic_equivalence_parser as parser

spec=importlib.util.spec_from_file_location('host_equivalence_fixture',GAME/'tests/test_atomic_equivalence.py')
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


def git(repo,*args):
    return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,text=True).stdout.strip()


def setup(tmp_path):
    repo=tmp_path/'repo';repo.mkdir();git(repo,'init','-q')
    source=repo/'build.py';source.write_text('immutable_original=1\n');git(repo,'add','build.py')
    git(repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','original')
    original=git(repo,'rev-parse','HEAD');code=dict(revision=original,path='build.py',sha256=host.binding(source)['sha256'])
    # A true unrelated history: original is available, but is NOT an ancestor.
    git(repo,'checkout','--orphan','replacement');source.write_text('new_split=2\n');git(repo,'add','build.py')
    git(repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','replacement')
    assert subprocess.run(['git','-C',str(repo),'merge-base','--is-ancestor',original,'HEAD']).returncode==1
    model=fixture.packet(tmp_path,'Original',fixture.selected(fixture.piece(),0))
    exported=fixture.artifact(tmp_path,'Original.fbx',b'actual serialized fixture bytes')
    state=fixture.write_json(tmp_path,'policy.json',dict(logical='Logical',placements=[],cull=dict(start_cm=0,end_cm=0),shadow=True,fade=dict(mode=0),collision='complex',materials=['Rock']))
    guard=fixture.guarded_fixture(tmp_path)
    census=dict(complete=True,groups={'fixture':['world.original']},owners={'world.original':dict(models=['Logical'],
        captures={'Logical':dict(source_triangles=1,exported=True)})})
    asset=dict(baseline=fixture.geometry([model]),actual=fixture.geometry([model]),baseline_exports=[exported],actual_exports=[exported],baseline_policy=state,actual_policy=state)
    owner=dict(baseline_sources=[code],actual_sources=[code],baseline_inputs=[],actual_inputs=[],baseline_guard=guard,actual_guard=guard,assets={'Logical':asset})
    value=dict(schema=1,scope=dict(recipe=code,census=fixture.write_json(tmp_path,'census.json',census),guard=guard),regions={'world.original':owner})
    path=tmp_path/'aggregate.json';path.write_text(json.dumps(value))
    return repo,path,value


def parse_frozen(monkeypatch,record,tmp_path):
    tree=fixture.fbx_tree()
    monkeypatch.setitem(sys.modules,'io_scene_fbx',SimpleNamespace(parse_fbx=SimpleNamespace(parse=lambda path:(tree,7400))))
    def forbidden(*args,**kwargs):raise AssertionError('Native parser attempted subprocess/Git')
    with monkeypatch.context() as patch:
        patch.setattr(subprocess,'run',forbidden);patch.setattr(subprocess,'Popen',forbidden)
        patch.setattr(eq,'source_binding',forbidden)
        output=tmp_path/'observations.json';parser.parse(record['job'],output)
    observed=host.binding(output)
    guard=fixture.guarded_fixture(tmp_path/'parser-guard')
    marker='ATOMIC FBX OBSERVATIONS '+record['job']['sha256']+' '+observed['sha256']
    guard['marker']=marker
    guard['stdout']=fixture.artifact(tmp_path,'parser.log',marker.encode())
    return observed,guard


def test_frozen_real_nonancestor_git_and_processless_actual_parser_roundtrip(tmp_path,monkeypatch):
    repo,path,_=setup(tmp_path);record=host.prepare(path,tmp_path/'frozen',repo=repo)
    observed,guard=parse_frozen(monkeypatch,record,tmp_path)
    result=host.finalize(record,observed,guard,repo=repo,native=False,required_groups=('fixture',))
    assert result['exporter_complete'] and not result['native_complete'] and not result['complete'],result['errors']
    result=host.finalize(record,observed,guard,repo=repo,required_groups=('fixture',))
    assert result['exporter_complete'] and not result['complete'] and result['native_errors']


@pytest.mark.parametrize('change',['original','frozen','job','spec','observations','guard_marker','missing_row','extra_row','bad_counter'])
def test_host_refuses_changed_bytes_or_parser_census(tmp_path,monkeypatch,change):
    repo,path,_=setup(tmp_path);record=host.prepare(path,tmp_path/'frozen',repo=repo)
    observed,guard=parse_frozen(monkeypatch,record,tmp_path)
    if change in ('original','frozen','job','spec','observations'):
        row=(record['originals'][0] if change=='original' else record['frozen'][0] if change=='frozen'
            else observed if change=='observations' else record[change])
        Path(row['path']).write_bytes(b'changed')
    elif change=='guard_marker':guard['marker']='PASS'
    else:
        value=eq.json_artifact(observed)
        if change=='missing_row':value['rows']=[]
        elif change=='extra_row':value['rows'].append(copy.deepcopy(value['rows'][0]))
        else:value['rows'][0]['render']={'unsupported':1}
        Path(observed['path']).write_text(json.dumps(value));observed=host.binding(observed['path'])
        guard['marker']='ATOMIC FBX OBSERVATIONS '+record['job']['sha256']+' '+observed['sha256']
        guard['stdout']=fixture.artifact(tmp_path,'parser.log',guard['marker'].encode())
    with pytest.raises(eq.EvidenceError):host.finalize(record,observed,guard,repo=repo,native=False,required_groups=('fixture',))


def test_git_authority_rechecked_after_parser_and_after_comparison(tmp_path,monkeypatch):
    repo,path,_=setup(tmp_path);record=host.prepare(path,tmp_path/'frozen',repo=repo)
    observed,guard=parse_frozen(monkeypatch,record,tmp_path)
    original=host.recheck;calls=[]
    def checked(record,repo):
        calls.append(len(calls));return original(record,repo)
    monkeypatch.setattr(host,'recheck',checked)
    host.finalize(record,observed,guard,repo=repo,native=False,required_groups=('fixture',))
    assert len(calls)==2
    source=eq.json_artifact(record['original_spec'])['scope']['recipe']
    # Remove only this fixture repo's original immutable object authority.
    object_path=repo/'.git/objects'/source['revision'][:2]/source['revision'][2:]
    object_path.unlink()
    with pytest.raises(eq.EvidenceError,match='unavailable'):host.finalize(record,observed,guard,repo=repo,native=False,required_groups=('fixture',))


def test_parser_rechecks_frozen_bytes_after_native_parse(tmp_path):
    row=fixture.artifact(tmp_path,'input.fbx',b'fbx')
    job=fixture.write_json(tmp_path,'job.json',dict(schema=1,exports=[row]))
    def mutate(path):
        path.write_bytes(b'changed');return dict(render=eq.Counter({b'a'*32:1}),collision=eq.Counter()),1
    with pytest.raises(eq.EvidenceError,match='bytes differ'):parser.parse(job,tmp_path/'result.json',reader=mutate)
    assert not (tmp_path/'result.json').exists()


def test_aggregate_native_migration_refuses_git_before_starting_a_child(monkeypatch):
    monkeypatch.setitem(sys.modules,'bpy',SimpleNamespace())
    def forbidden(*args,**kwargs):raise AssertionError('Git child escaped native stage')
    monkeypatch.setattr(subprocess,'run',forbidden)
    with pytest.raises(eq.EvidenceError,match='host-only'):eq.source_binding({})


def test_source_only_result_cannot_claim_export_or_native_acceptance(tmp_path):
    repo,path,value=setup(tmp_path)
    result=eq.verify(value,repo=repo,native=False,serialized=False,required_groups=('fixture',))
    assert result['source_complete'] and result['mode']=='source_only'
    assert not result['exporter_complete'] and not result['native_complete'] and not result['complete']
