"""Synthetic strict diagnostic/query faults; never read retained data or launch native."""
import ast
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from atelier.gltf import glb_pack

HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parents[1]/'tools')]
import track_query_surface as surface
from test_track_query_surface import arch
import track_observation_data as observation
import track_query_supplement as query










def diagnostic_fixture():
    names=[*query.VIADUCTS,*('SM_TK_Test_'+str(i)for i in range(130))];runtime=dict(meshes={},pieces=[],instances=[])
    records={};controls={}
    for index,name in enumerate(names):
        levels=3 if index<88 else 2
        runtime['meshes'][name]=dict(lods=[f'meshes/{name}_LOD{k}.glb'for k in range(levels)],screen_sizes=[1.,.3,.05][:levels],materials=['MI_B_stone'])
        runtime['pieces'].append(dict(name=name,collision=levels-1 if index<133 else -1))
        rows=[]
        for kind in (('positive','negative')if index<133 else ('negative',)):
            for shape in ('ray','capsule'):
                q=dict(start=[0,0,1],end=[0,0,-1],channel='Pawn',trace_complex=True)
                if shape=='capsule':q.update(radius_cm=.1,half_height_cm=.1,orientation=[0,0,0,1])
                rows.append(dict(id=name+'.'+shape+'.'+kind,kind=shape+'_'+kind,input=q))
        controls[name]=rows
        mesh='/Game/AtelierValidation/Track_0123456789ab/Library/'+name+'.'+name
        observed=[dict(copy.deepcopy(r),target=mesh,hit=None if r['kind'].endswith('negative')or name in query.VIADUCTS else dict(blocking=True,logical=name,position=[0.,0.,0.],normal=[0.,0.,1.],distance=1.))for r in rows]
        records[name]=dict(policy_scope='fixture',meshes=[mesh],source_lods={k:['real saved MD']for k in range(levels)},
            render_lods={k:['real GPU basis']for k in range(levels)},source_presence={k:{True}for k in range(levels)},
            cooked=['real cooked'],probes=dict(logical=name,seams=[],controls=observed))
    return runtime,records,controls


@pytest.mark.parametrize('fault',[None,'source','gpu','cook','schema','negative','other_positive','missing_known_failure'])
def test_diagnostic_keeps_full_geometry_and_only_exact_fourteen_query_noncoverage(monkeypatch,fault):
    runtime,records,controls=diagnostic_fixture();name=next(n for n in records if n not in query.VIADUCTS)
    monkeypatch.setattr(observation.proof,'whole_bounds',lambda _:b'actual bounds')
    monkeypatch.setattr(observation.proof,'native_raw_set',lambda r,_:r)
    row=records[name]
    if fault=='source':row['source_lods'].pop(0)
    elif fault=='gpu':row['render_lods'].pop(0)
    elif fault=='cook':row['cooked']=[]
    elif fault=='schema':row['probes']['controls'][0]['input']['channel']='Visibility'
    elif fault=='negative':row['probes']['controls'][-1]['hit']=dict(blocking=True)
    elif fault=='other_positive':row['probes']['controls'][0]['hit']=None
    elif fault=='missing_known_failure':records[query.VIADUCTS[0]]['probes']['controls'][0]['hit']=dict(blocking=True)
    if fault is None:
        report=observation.validate(records,runtime,controls)
        assert report['geometry_owners']==137 and len(report['failed_query_rows'])==14
        assert report['query_complete_owner_count']==130 and report['query_row_count']==540 and report['successful_query_row_count']==526 and not report['query_all_pass'] and not report['native_complete']
    else:
        with pytest.raises(ValueError):observation.validate(records,runtime,controls)


@pytest.mark.parametrize('fault',[None,'missing_owner','missing_query','positive_miss','negative_hit','wrong_component'])
def test_seven_owner_query_results_are_strict_and_never_waived(fault):
    doc,binary,_=arch();source=surface.triangles(glb_pack(doc,binary));controls={};rows={}
    for name in query.VIADUCTS:
        controls[name],_=surface.controls(name,source,suffix='.supplement')
        rows[name]=dict(queries=[dict(r,blocking=r['kind'].endswith('positive'),selected_component=True)for r in controls[name]])
    name=query.VIADUCTS[0]
    if fault=='missing_owner':rows.pop(name)
    elif fault=='missing_query':rows[name]['queries'].pop()
    elif fault=='positive_miss':rows[name]['queries'][0]['blocking']=False
    elif fault=='negative_hit':rows[name]['queries'][-1]['blocking']=True
    elif fault=='wrong_component':rows[name]['queries'][0]['selected_component']=False
    if fault is None:assert query.check_rows(rows,controls)==28
    else:
        with pytest.raises(ValueError):query.check_rows(rows,controls)


def test_query_child_is_readonly_and_no_numpy_host_authority_imports(tmp_path):
    code="""import importlib.abc,pathlib,sys
root=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(root))
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name=='atomic_equivalence'or name.split('.')[0]in('numpy','mesh_ir')or name=='atelier.mesh_ir':raise ModuleNotFoundError(name)
sys.meta_path.insert(0,Block())
import track_query_supplement
print('STDLIB QUERY CHILD IMPORTED')
"""
    result=subprocess.run([sys.executable,'-I','-S','-c',code,str(HERE)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    tree=ast.parse(Path(query.__file__).read_text())
    forbidden={'save_loaded_asset','save_loaded_assets','delete_asset','delete_directory','delete_loaded_assets','import_mesh','import_asset_tasks','snapshot','subprocess','host_state'}
    assert not any(isinstance(n,ast.Attribute)and n.attr in forbidden or isinstance(n,ast.Name)and n.id in forbidden for n in ast.walk(tree))


@pytest.mark.parametrize('fault',[None,'nonfinite','missing_hit','wrong_mesh'])
def test_actual_query_readback_requires_full_finite_selected_hit(fault):
    row=dict(blocking=True,query_channel='Pawn',component='own-component',mesh='own-mesh',selected_component=True,
             position=[0.,0.,0.],normal=[0.,0.,1.],distance=2.)
    if fault=='nonfinite':row['position'][0]=float('nan')
    elif fault=='missing_hit':row.pop('normal')
    elif fault=='wrong_mesh':row['mesh']='foreign'
    if fault is None:assert query.observed_result(row,'own-component','own-mesh')is row
    else:
        with pytest.raises(ValueError):query.observed_result(row,'own-component','own-mesh')


def test_receiver_build_binds_before_separate_source_yori(tmp_path):
    # A distinct installed receiver package delegates all helpers to real source,
    # but its build module has an observable provider identity.
    from atelier import paths
    package=tmp_path/'receiver-site/atelier';package.mkdir(parents=True)
    (package/'__init__.py').write_text('__path__.append('+repr(str(Path(paths.__file__).parent))+')\n')
    (package/'build.py').write_text("PROVIDER='receiver-installed'\n")
    code=r'''
import importlib.abc,importlib.util,pathlib,sys
site,native=map(pathlib.Path,sys.argv[1:]);sys.path[:0]=[str(site),str(native)]
class Yori(importlib.abc.MetaPathFinder,importlib.abc.Loader):
 def find_spec(self,name,path=None,target=None):
  if name=='yori':return importlib.util.spec_from_loader(name,self)
 def create_module(self,spec):return None
 def exec_module(self,module):
  assert sys.modules['atelier.build'].PROVIDER=='receiver-installed'
  source=native.parents[1]/'world/yori.py';module.__file__=str(source)
  exec(compile(source.read_bytes(),str(source),'exec'),module.__dict__)
sys.meta_path.insert(0,Yori())
import run_track_query_supplement as host
assert host.build.PROVIDER=='receiver-installed'
print('SEPARATE RECEIVER BUILD BOUND BEFORE SOURCE YORI')
'''
    result=subprocess.run([sys.executable,'-I','-c',code,str(package.parent),str(HERE)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


@pytest.mark.parametrize('fault',[None,'append','mutate','truncate','replace','live','failed_whole'])
def test_terminal_stdout_snapshot_binds_prefix_and_never_waits_for_shared_trace(tmp_path,monkeypatch,fault):
    from atelier.atomic_files import atomic_json
    from atomic_equivalence_io import artifact
    from atomic_equivalence import guard_binding
    from track_guard_stdout import snapshot
    from recover_track_native_observations import binding
    receipt=tmp_path/'receipt.json';whole=tmp_path/'whole.json';source=tmp_path/'stdout.log';dest=tmp_path/'new-report/snapshot.log'
    atomic_json(receipt,dict(state='child_exited',cleanup_complete=True,processes=[123]if fault=='live'else[],footprint_bytes=0))
    atomic_json(whole,dict(exit_code=255 if fault=='failed_whole'else 0));source.write_bytes(b'ACTUAL OWNED MARKER\n')
    original_open=Path.open
    def opening(path,*args,**kwargs):
        if path==dest and args and args[0]=='xb':
            if fault=='append':
                with original_open(source,'ab')as stream:stream.write(b'shared TraceServer shutdown after owned cleanup\n')
            elif fault=='mutate':
                with original_open(source,'wb')as stream:stream.write(b'CHANGED PREFIX BYTES\n')
            elif fault=='truncate':
                with original_open(source,'wb')as stream:stream.write(b'x')
            elif fault=='replace':
                source.rename(tmp_path/'previous.log')
                with original_open(source,'wb')as stream:stream.write(b'ACTUAL OWNED MARKER\n')
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opening)
    if fault in (None,'append'):
        row,observation=snapshot(binding(receipt),binding(whole),source,dest,expected_exit=0)
        assert artifact(row)==b'ACTUAL OWNED MARKER\n' and observation['shared_services_waited_or_signalled']is False
        with original_open(source,'ab')as stream:stream.write(b'later shared shutdown\n')
        guard_binding(dict(receipt=binding(receipt),whole_result=binding(whole),stdout=row,marker='ACTUAL OWNED MARKER'))
        assert artifact(row)==b'ACTUAL OWNED MARKER\n'
    else:
        with pytest.raises(ValueError):snapshot(binding(receipt),binding(whole),source,dest,expected_exit=0)




def test_code_closure_uses_actual_receiver_platform_and_rejects_shadow_provider(tmp_path,monkeypatch):
    import run_track_query_supplement as host
    from atelier import source_imports
    receiver=tmp_path/'receiver';own_studio=host.GAME.parents[1]/'platform/studio';studio=receiver/'platform/studio'
    monkeypatch.setattr(host.build,'__file__',str(studio/'atelier/build.py'))
    seen=[]
    def imports(entry,roots):
        seen.append(roots);return {entry}
    monkeypatch.setattr(source_imports,'local_imports',imports)
    files=host.runtime_code_inputs(receiver)
    assert studio/'atelier/unreal_script_guard.py' in files and seen
    assert all(studio in roots and own_studio not in roots for roots in seen)
    monkeypatch.setattr(host.build,'__file__',str(own_studio/'atelier/build.py'))
    with pytest.raises(ValueError):host.runtime_code_inputs(receiver)
