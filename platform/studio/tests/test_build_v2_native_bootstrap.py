"""Native bootstrap distribution tests use a fake compiler; no native job is admitted."""
import hashlib
import json
from pathlib import Path

import pytest

from atelier.build_v2 import native_bootstrap as bootstrap
from atelier.harness.safety import guarded


def put(root, name, raw=b'source'):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    return path


@pytest.fixture
def world(tmp_path, monkeypatch):
    checkout = tmp_path / 'checkout'; checkout.mkdir()
    plugin = checkout / bootstrap.SOURCE
    put(plugin, 'AtelierBuildWorker.uplugin', b'{"Modules":[{"Name":"AtelierBuildWorker","Type":"Editor"}]}')
    for name in ['Source/AtelierBuildWorker/AtelierBuildWorker.Build.cs',
                 'Source/AtelierBuildWorker/Private/AtelierBuildWorkerLibrary.cpp',
                 'Source/AtelierBuildWorker/Private/AtelierBuildWorkerModule.cpp',
                 'Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h']:
        put(plugin,name,name.encode())
    engine = tmp_path / 'engine'; engine.mkdir()
    put(engine,'Engine/Binaries/Mac/UnrealEditor.modules',json.dumps({'BuildId':'fixture-engine','Modules':{}}).encode())
    put(engine,'Engine/Build/BatchFiles/Mac/Build.sh',b'#!/bin/sh\n')
    cache = tmp_path / 'cache'
    calls = []
    def compile(command, report, **kwargs):
        calls.append((command,report,kwargs,Path.cwd()))
        host = Path(next(arg.removeprefix('-Project=') for arg in command if arg.startswith('-Project='))).parent
        built = host / 'Plugins/AtelierBuildWorker'
        assert not (built / 'Binaries').exists()
        source, frozen = bootstrap._capture(built)
        assert frozen == bootstrap._capture(plugin)[1]
        for name in frozen:
            assert (built / name).stat().st_ino != (plugin / name).stat().st_ino
        put(built,'Binaries/Mac/libUnrealEditor-AtelierBuildWorker.dylib', b'compiled frozen source '+source.encode())
        put(built,'Binaries/Mac/UnrealEditor.modules',json.dumps({'BuildId':bootstrap._engine_id(engine),
            'Modules':{'AtelierBuildWorker':'libUnrealEditor-AtelierBuildWorker.dylib'}}).encode())
        return 0
    monkeypatch.setattr(guarded,'run',compile)
    return checkout,cache,engine,calls,compile


def test_frozen_source_compiles_under_existing_guard_and_verified_hit_reuses(world):
    checkout,cache,engine,calls,_ = world
    cwd = Path.cwd()
    built = bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert built.is_absolute() and Path.cwd()==cwd and len(calls)==1
    command,report,kwargs,entered = calls[0]
    assert command[:4] == ['/usr/bin/nice','-n','10',str(engine/'Engine/Build/BatchFiles/Mac/Build.sh')]
    assert command[4:7] == ['AtelierWorkerHostEditor','Mac','Development']
    assert '-MaxParallelActions=3' in command and '-NoUBA' in command and '-NoUBTMakefiles' in command
    assert entered==built.parents[1] and report.name=='compile.guard'
    assert kwargs['kind']=='compile' and kwargs['timeout']==kwargs['queue_seconds']==1800
    assert kwargs['aggregate_tree'] is True
    host=entered
    assert (host/'Source/RuntimeDummy/RuntimeDummy.cpp').is_file()
    assert b'Core' in (host/'Source/RuntimeDummy/RuntimeDummy.Build.cs').read_bytes()
    receipt=json.loads(next(cache.glob('*/ready.json')).read_text())
    assert receipt['source_digest']==bootstrap._capture(checkout/bootstrap.SOURCE)[0]
    for relative,digest in receipt['binaries'].items():
        assert hashlib.sha256((built/relative).read_bytes()).hexdigest()==digest
    assert bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)==built and len(calls)==1


def test_source_and_engine_build_id_changes_get_new_private_distributions(world):
    checkout,cache,engine,calls,_ = world
    first=bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    put(checkout/bootstrap.SOURCE,'Source/AtelierBuildWorker/Public/NewCollision.h',b'new project-owned implementation')
    second=bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert first!=second and first.exists() and second.exists()
    put(engine,'Engine/Binaries/Mac/UnrealEditor.modules',json.dumps({'BuildId':'fixture-engine-2'}).encode())
    third=bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert third not in (first,second) and len(calls)==3


@pytest.mark.parametrize('change',['binary','extra','source','module_id'])
def test_changed_cached_artifact_never_becomes_a_stale_hit(world,change):
    checkout,cache,engine,calls,_ = world
    built=bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    if change=='binary':
        path=built/'Binaries/Mac/libUnrealEditor-AtelierBuildWorker.dylib';path.chmod(0o600);path.write_bytes(b'changed')
    elif change=='extra': put(built,'Binaries/Mac/foreign.dylib',b'foreign')
    elif change=='source':
        path=built/'Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h';path.chmod(0o600);path.write_bytes(b'changed')
    elif change=='module_id':
        path=built/'Binaries/Mac/UnrealEditor.modules';path.chmod(0o600);path.write_text(json.dumps({'BuildId':'foreign','Modules':{}}))
    with pytest.raises(ValueError): bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert len(calls)==1 and built.exists()


@pytest.mark.parametrize('failure',['return','cancel','source_change','module_mismatch'])
def test_failure_or_cancellation_preserves_attempt_without_publication(world,monkeypatch,failure):
    checkout,cache,engine,calls,compile=world
    original=Path.cwd()
    def fail(command,report,**kwargs):
        if failure=='cancel': raise KeyboardInterrupt
        result=compile(command,report,**kwargs)
        if failure=='return': return 1
        if failure=='source_change': put(checkout/bootstrap.SOURCE,'Source/AtelierBuildWorker/Public/Changed.h',b'changed')
        if failure=='module_mismatch':
            host=Path.cwd();put(host/'Plugins/AtelierBuildWorker','Binaries/Mac/UnrealEditor.modules',b'{"BuildId":"wrong","Modules":{}}')
        return result
    monkeypatch.setattr(guarded,'run',fail)
    with pytest.raises((RuntimeError,ValueError,KeyboardInterrupt)):
        bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert Path.cwd()==original and not list(cache.glob('*/ready.json'))
    assert list(cache.glob('*/attempt-*'))


def test_source_capture_rejects_links_before_compile(world):
    checkout,cache,engine,calls,_=world
    root=checkout/bootstrap.SOURCE
    (root/'Source/linked.h').symlink_to(root/'Source/AtelierBuildWorker/Public/AtelierBuildWorkerLibrary.h')
    with pytest.raises(ValueError,match='link'): bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert not calls and not cache.exists()


def test_source_manifest_is_exact_buildcs_utf16_ordinal_format(world):
    checkout,_,_,_,_=world
    root=checkout/bootstrap.SOURCE
    for name in ['\ue000.h','\U00010000.h']: put(root,'Source/'+name,name.encode())
    digest,files=bootstrap._capture(root)
    names=sorted(files,key=lambda name:name.encode('utf-16-be'))
    expected=''.join(name+'\0'+hashlib.sha256(files[name]).hexdigest()+'\n' for name in names).encode('utf-8')
    assert digest==hashlib.sha256(expected).hexdigest()


def test_busy_private_bootstrap_refuses_before_any_second_guard(world):
    import fcntl
    import os
    checkout,cache,engine,calls,_=world
    bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    lock=os.open(next(cache.glob('*/.bootstrap.lock')),os.O_RDWR)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(RuntimeError,match='already active'):
            bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
        assert len(calls)==1
    finally:
        os.close(lock)


def test_bootstrap_implementation_bytes_are_a_private_cache_ingredient(world,monkeypatch):
    checkout,cache,engine,calls,_=world
    first=bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    original=bootstrap.control._read_at
    def changed(root,name,*args,**kwargs):
        raw=original(root,name,*args,**kwargs)
        return raw+b'\n# changed bootstrap implementation\n' if Path(root)==Path(bootstrap.__file__).parent and name==Path(bootstrap.__file__).name else raw
    monkeypatch.setattr(bootstrap.control,'_read_at',changed)
    second=bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert first!=second and first.exists() and len(calls)==2


def test_public_or_linked_cache_root_cannot_admit_compilation(world):
    checkout,cache,engine,calls,_=world
    cache.mkdir(mode=0o755);cache.chmod(0o755)
    with pytest.raises(ValueError,match='private and owned'):
        bootstrap.ensure_native_worker(checkout,cache,engine,echo=lambda _:None)
    assert not calls
