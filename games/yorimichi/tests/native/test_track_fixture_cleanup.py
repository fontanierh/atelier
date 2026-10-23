"""Pure fault injection for the exact failed namespace cleanup. Never starts Unreal."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
import cleanup_track_fixture as cleanup
from run_track_native_equivalence import strict_cleanup


def fixture(tmp_path):
    content=tmp_path/'Content';root=content/cleanup.FAILED_PACKAGE.removeprefix('/Game/')
    files={};directories=['Library','Prerequisites','Prerequisites/Materials']
    for relative in('Library/PartA.uasset','Prerequisites/Materials/MaterialA.uasset'):
        path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(('uncertified '+relative).encode())
        files[relative]=dict(identity=cleanup.pin(path.lstat()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return dict(package=cleanup.FAILED_PACKAGE,root=str(root),files=files,directories=directories),content


@pytest.mark.parametrize('fault',['changed','same_bytes_replaced','missing','new_file','new_directory','link','parent_link','fifo','hardlink'])
def test_frozen_census_refuses_every_changed_entry_before_archive_writes(tmp_path,fault):
    manifest,_=fixture(tmp_path);root=Path(manifest['root']);first=root/'Library/PartA.uasset'
    if fault=='changed':first.write_bytes(b'changed bytes')
    elif fault=='same_bytes_replaced':
        data=first.read_bytes();first.unlink();first.write_bytes(data)
    elif fault=='missing':first.unlink()
    elif fault=='new_file':(root/'Library/new.ubulk').write_bytes(b'not frozen')
    elif fault=='new_directory':(root/'Library/unknown-empty').mkdir()
    elif fault=='link':
        foreign=tmp_path/'foreign';foreign.write_bytes(first.read_bytes());first.unlink();first.symlink_to(foreign)
    elif fault=='parent_link':
        saved=root.with_name('retained');root.rename(saved);root.symlink_to(saved,target_is_directory=True)
    elif fault=='fifo':first.unlink();os.mkfifo(first)
    else:os.link(first,tmp_path/'another-reference')
    archive=tmp_path/'archive'
    with pytest.raises((ValueError,FileNotFoundError)):cleanup.archive_payloads(root,manifest,archive)
    assert not archive.exists()and not archive.is_symlink()


def test_independent_archive_preserves_every_payload_and_identity_before_retirement(tmp_path):
    manifest,_=fixture(tmp_path);root=Path(manifest['root']);archive_root=tmp_path/'archive'
    archived=cleanup.archive_payloads(root,manifest,archive_root)
    assert cleanup.scan(root,manifest)==cleanup.scan(archive_root,archived)
    for relative in manifest['files']:
        assert (root/relative).read_bytes()==(archive_root/relative).read_bytes()
        assert (root/relative).stat().st_ino!=(archive_root/relative).stat().st_ino
    (archive_root/'Library/PartA.uasset').write_bytes(b'changed archive')
    with pytest.raises(ValueError):cleanup.scan(archive_root,archived)
    assert cleanup.scan(root,manifest)


def unreal(manifest,*,external=False,registry_fault=None,load_fault=None,delete_ok=True,on_load=None):
    allowed=cleanup.packages(manifest);objects={p:p+'.'+p.rsplit('/',1)[-1]for p in allowed}
    state=dict(registry=set(objects.values()),deletes=0,loads=0,refs={p:set()for p in allowed})
    if external:state['refs'][sorted(allowed)[-1]]={'/Game/Foreign/SavedUser'}
    if registry_fault=='extra':state['registry'].add('/Game/Foreign.Extra')
    elif registry_fault=='missing':state['registry'].pop()
    def refs(path,*args,**kwargs):return list(state['refs'][path])
    def load(path):
        state['loads']+=1
        if on_load:on_load(state,path)
        if load_fault=='missing':return None
        actual='/Game/Foreign.Other'if load_fault=='redirect'else objects[path]
        return SimpleNamespace(get_path_name=lambda:actual)
    def delete(values):
        state['deletes']+=1
        if delete_ok:state['registry'].difference_update(v.get_path_name()for v in values)
        return delete_ok
    E=SimpleNamespace(list_assets=lambda *a,**k:sorted(state['registry']),find_package_referencers_for_asset=refs,
        load_asset=load,does_asset_exist=lambda p:objects[p]in state['registry'])
    registry=SimpleNamespace(wait_for_completion=lambda:None,is_loading_assets=lambda:False)
    kind=object();U=SimpleNamespace(EditorAssetLibrary=E,EditorAssetSubsystem=kind,
        AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda:registry),SystemLibrary=SimpleNamespace(collect_garbage=lambda:None),
        get_editor_subsystem=lambda cls:SimpleNamespace(delete_loaded_assets=delete))
    return U,state


@pytest.mark.parametrize('fault',['external','extra_registry','missing_registry','redirect','missing_object','late_file','late_archive','late_external'])
def test_complete_native_preflight_refuses_before_any_batch_deletion(tmp_path,fault):
    manifest,_=fixture(tmp_path);root=Path(manifest['root']);archive_root=tmp_path/'archive'
    archived=cleanup.archive_payloads(root,manifest,archive_root)
    def loaded(state,path):
        if fault=='late_file':(root/'Library/PartA.uasset').write_bytes(b'changed while loading')
        elif fault=='late_archive':(archive_root/'Library/PartA.uasset').write_bytes(b'changed archive while loading')
        elif fault=='late_external':state['refs'][path]={'/Game/Foreign/LateUser'}
    U,state=unreal(manifest,external=fault=='external',
        registry_fault={'extra_registry':'extra','missing_registry':'missing'}.get(fault),
        load_fault={'redirect':'redirect','missing_object':'missing'}.get(fault),on_load=loaded)
    with pytest.raises(ValueError):cleanup.retire_checked(U,manifest,archived,archive_root)
    assert state['deletes']==0 and len(list(root.rglob('*.uasset')))==2


def test_supported_retirement_only_allows_exact_archived_host_remnants(tmp_path):
    manifest,content=fixture(tmp_path);root=Path(manifest['root']);archive_root=tmp_path/'archive'
    archived=cleanup.archive_payloads(root,manifest,archive_root);U,state=unreal(manifest)
    result=cleanup.retire_checked(U,manifest,archived,archive_root)
    assert state['deletes']==1 and not state['registry']
    assert result['allowed_packages']==sorted(cleanup.packages(manifest))
    assert result['remaining']=={k:v['sha256']for k,v in manifest['files'].items()}
    strict_cleanup(dict(content=str(content),package=manifest['package']),result)
    assert not root.exists()and cleanup.scan(archive_root,archived)


def test_native_delete_failure_preserves_files_and_archive_without_host_unlink(tmp_path):
    manifest,_=fixture(tmp_path);root=Path(manifest['root']);archive_root=tmp_path/'archive'
    archived=cleanup.archive_payloads(root,manifest,archive_root);U,state=unreal(manifest,delete_ok=False)
    with pytest.raises(ValueError):cleanup.retire_checked(U,manifest,archived,archive_root)
    assert state['deletes']==1 and cleanup.scan(root,manifest)and cleanup.scan(archive_root,archived)


def custody():
    files={};directories=[f'Group_{k}'for k in range(105)]
    for k in range(317):
        size=49362412 if k==0 else 1
        files[f'Group_{k%105}/Part_{k}.uasset']=dict(identity=[1,k+1,size,1,1],sha256='a'*64)
    launch=dict(args=['unused']*3+['-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path=/private/proof))'],
        ddc_dir='/private/proof',engine_dir='/installed/Engine',engine_pak='/installed/Engine/DerivedDataCache/Compressed.ddp')
    log="\n".join(["LogDerivedDataCache: Verbose: Parsing cache graph '"+launch['args'][3][5:]+"'...",
        'LogDerivedDataCache: V2Local: Using data cache path /private/proof: Writable',
        'LogDerivedDataCache: Display: /installed/Engine/DerivedDataCache/Compressed.ddp: Opened pak cache for reading. (1 MiB)'])
    terminal=dict(state='child_exited',cleanup_complete=True,processes=[],footprint_bytes=0)
    spec=dict(source_head=cleanup.FAILED_SOURCE,package=cleanup.FAILED_PACKAGE,phase='original',content='/owned/Content',
        receiving_head='b'*40,launch=launch)
    manifest=dict(source_head=cleanup.FAILED_SOURCE,spec_sha256=cleanup.FAILED_SPEC,package=cleanup.FAILED_PACKAGE,
        root='/owned/Content/'+cleanup.FAILED_PACKAGE.removeprefix('/Game/'),receiving_head='b'*40,
        whole_exit=143,output_certified=False,files=files,directories=directories,terminal=copy.deepcopy(terminal))
    startup=dict(cleanup.startup_ddc(launch,log),launch=launch)
    return spec,manifest,terminal,startup,log


@pytest.mark.parametrize('fault',['spec','scope','certified','terminal','count','guard','receiver','startup','extra_dir'])
def test_old_failed_custody_never_becomes_new_blanket_deletion_authority(fault):
    spec,manifest,terminal,startup,log=custody();cleanup.validate_custody(spec,manifest,terminal,startup,log)
    if fault=='spec':manifest['spec_sha256']='0'*64
    elif fault=='scope':spec['package']='/Game/Foreign'
    elif fault=='certified':manifest['output_certified']=True
    elif fault=='terminal':terminal['processes']=[dict(pid=1)]
    elif fault=='count':manifest['files'].pop(next(iter(manifest['files'])))
    elif fault=='guard':manifest['terminal']['observed']='not the actual terminal'
    elif fault=='receiver':spec['receiving_head']='c'*40
    elif fault=='startup':startup['graph']='shared'
    else:manifest['directories'][-1]='unknown'
    with pytest.raises(ValueError):cleanup.validate_custody(spec,manifest,terminal,startup,log)


def test_native_cleanup_import_is_stdlib_only_without_host_geometry_or_unreal(tmp_path):
    import subprocess
    code='''import importlib.abc,sys\nclass Block(importlib.abc.MetaPathFinder):\n def find_spec(self,fullname,path=None,target=None):\n  if fullname=='atomic_equivalence' or fullname.split('.')[0] in ('numpy','mesh_ir','unreal') or fullname=='atelier.mesh_ir':raise ModuleNotFoundError(fullname)\nsys.meta_path.insert(0,Block());sys.path.insert(0,sys.argv[1])\nimport cleanup_track_fixture\nassert 'unreal' not in sys.modules and 'numpy' not in sys.modules\nprint('CLEANUP STDLIB IMPORT VERIFIED')'''
    result=subprocess.run([sys.executable,'-I','-S','-c',code,str(HERE)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CLEANUP STDLIB IMPORT VERIFIED'in result.stdout


def test_changed_last_native_remnant_stops_host_before_first_unlink(tmp_path):
    manifest,content=fixture(tmp_path);root=Path(manifest['root']);archive_root=tmp_path/'archive'
    archived=cleanup.archive_payloads(root,manifest,archive_root);U,_=unreal(manifest)
    record=cleanup.retire_checked(U,manifest,archived,archive_root)
    first=root/'Library/PartA.uasset';before=first.read_bytes()
    (root/'Prerequisites/Materials/MaterialA.uasset').write_bytes(b'changed after native exit')
    with pytest.raises(ValueError):
        cleanup.scan(root,manifest,remaining=True)
        strict_cleanup(dict(content=str(content),package=manifest['package']),record)
    assert first.read_bytes()==before and cleanup.scan(archive_root,archived)
