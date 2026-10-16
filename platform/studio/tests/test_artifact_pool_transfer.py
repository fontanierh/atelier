"""Pool copies must use normal admission and cannot certify a failed or interrupted worker."""
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest

from atelier import artifact_pool as pool, artifact_pool_state as state, artifact_pool_transfer as tx
from atelier import build_snapshot, paths
from atelier.build import Python, Step
from atelier.harness.safety import guarded

IDENTITY = 'a' * 64


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    out = repo / 'build' / 'sandbox'
    ctx = SimpleNamespace(out=out, stamps=out/'stamps', game='sandbox')
    ctx.stamps.mkdir(parents=True)
    folder = out/'textures';folder.mkdir()
    (folder/'output').write_text('original')
    step = Step('world.textures', [Python(repo/'source.py')], outputs=[folder/'output'], pool_roots=[folder])
    cache = tmp_path/'cache'
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'build_root', lambda:repo/'build')
    monkeypatch.setattr(paths, 'cache_dir', lambda *args, **kwargs:cache)
    monkeypatch.setattr(pool, 'select', lambda *args:(ctx,step,'source'))
    monkeypatch.setattr(pool, 'key', lambda *args:IDENTITY)
    monkeypatch.delenv('ATELIER_BUILD_ROOT', raising=False)
    monkeypatch.delenv('ATELIER_PYTHON', raising=False)
    stamp = ctx.stamps/'world.textures.json'
    state.write(stamp, dict(fingerprint='source', pool_key=IDENTITY, seconds=2))
    return SimpleNamespace(ctx=ctx, step=step, cache=cache, stamp=stamp, folder=folder,
                           journal=out/state.JOURNAL, repo=repo)


def seed(f):
    stage = state.stage(f.cache, uuid.uuid4().hex)
    pool.transfer('publish', f.ctx, f.step, 'source', f.cache, staging=stage)
    stage.rename(f.cache/IDENTITY)


def fake_guard(monkeypatch, *, after=None, code=0):
    calls = []
    def run(command, folder, **options):
        calls.append((command,folder,options))
        assert command[1:3] == ['-m','atelier.artifact_pool_worker']
        def option(name):return command[command.index(name)+1]
        tx.execute(*command[3:6], invocation=option('--invocation'), expected_key=option('--expected-key'),
                   expected_journal=option('--expected-journal'))
        if after:after(command,folder,options)
        return code
    monkeypatch.setattr(guarded, 'run', run)
    return calls


def test_publish_and_restore_only_finalize_after_normal_guard_success(fixture, monkeypatch):
    f=fixture
    def published(*_):
        assert f.journal.exists()
        assert not (f.cache/IDENTITY).exists()
        with pytest.raises(SystemExit, match='pool transfer'):
            build_snapshot.require_complete(f.ctx.out,game='sandbox')
    calls=fake_guard(monkeypatch, after=published)
    assert pool.main('publish','sandbox','world.textures') == 0
    assert not f.journal.exists() and (f.cache/IDENTITY).is_dir()
    (f.folder/'output').write_text('changed')
    (f.folder/'extra').write_text('stale')
    def restored(*_):
        assert not f.stamp.exists() and f.journal.exists()
        assert (f.folder/'output').read_text() == 'original'
    fake_guard(monkeypatch,after=restored)
    assert pool.main('restore','sandbox','world.textures') == 0
    assert not f.journal.exists() and not (f.folder/'extra').exists()
    assert state.read(f.stamp)['pooled_from'] == IDENTITY
    assert (f.folder/'output').stat().st_ino != (f.cache/IDENTITY/'outputs/textures/output').stat().st_ino
    options=calls[0][2]
    assert options['kind']=='job' and options['aggregate_tree'] is True
    assert options['timeout']==1800 and options['progress']==30
    assert options['invocation_id'] in str(calls[0][1])
    assert 'no_lock' not in options and 'capacity_session' not in options


@pytest.mark.parametrize('failure',['exit','close'])
def test_failed_outer_guard_cannot_publish_restore_stamp_and_same_command_resumes(fixture,monkeypatch,failure):
    f=fixture;seed(f)
    (f.folder/'output').write_text('changed')
    def fail(*_):
        assert not f.stamp.exists()
        if failure=='close':raise RuntimeError('capacity close refused')
    fake_guard(monkeypatch,after=fail,code=1)
    if failure=='close':
        with pytest.raises(RuntimeError,match='close refused'):pool.main('restore','sandbox','world.textures')
    else:
        assert pool.main('restore','sandbox','world.textures') == 1
    assert f.journal.exists() and not f.stamp.exists()
    first=state.read(f.journal)['invocation']
    with pytest.raises(SystemExit,match='pool transfer'):
        build_snapshot.require_complete(f.ctx.out,game='sandbox')
    calls=fake_guard(monkeypatch)
    assert pool.main('restore','sandbox','world.textures') == 0
    assert state.read(f.stamp)['pooled_from'] == IDENTITY and not f.journal.exists()
    assert calls[0][2]['invocation_id'] != first


def test_failed_publish_keeps_original_stamp_and_is_resumable_without_publishing(fixture,monkeypatch):
    f=fixture;original=f.stamp.read_bytes()
    fake_guard(monkeypatch,code=1)
    assert pool.main('publish','sandbox','world.textures') == 1
    previous=state.read(f.journal)['invocation']
    assert state.stage(f.cache,previous).exists() and not (f.cache/IDENTITY).exists()
    assert f.stamp.read_bytes()==original
    fake_guard(monkeypatch)
    assert pool.main('publish','sandbox','world.textures') == 0
    assert not state.stage(f.cache,previous).exists() and (f.cache/IDENTITY).exists()
    assert f.stamp.read_bytes()==original and not f.journal.exists()


@pytest.mark.parametrize('action',['publish','restore'])
def test_abandon_is_guarded_and_preserves_unrelated_data(fixture,monkeypatch,action):
    f=fixture
    if action=='restore':seed(f)
    keep=f.ctx.out/'unrelated';keep.mkdir();(keep/'keep').write_text('keep')
    fake_guard(monkeypatch,code=1)
    assert pool.main(action,'sandbox','world.textures') == 1
    old=state.read(f.journal)['invocation']
    monkeypatch.setattr(pool,'select',lambda *a:pytest.fail('abandon must not depend on changed recipe'))
    fake_guard(monkeypatch)
    assert pool.main('abandon','sandbox','world.textures') == 0
    assert not f.journal.exists() and not state.stage(f.cache,old).exists()
    assert (keep/'keep').read_text()=='keep'
    if action=='publish':assert f.stamp.exists() and (f.folder/'output').read_text()=='original'
    else:assert not f.stamp.exists() and not f.folder.exists() and (f.cache/IDENTITY).exists()


def test_changed_key_while_queued_refuses_before_mutation(fixture,monkeypatch):
    f=fixture;before=f.stamp.read_bytes()
    def run(command,folder,**options):
        monkeypatch.setattr(pool,'key',lambda *a:'b'*64)
        return tx.execute('publish','sandbox','world.textures',invocation=options['invocation_id'],
                          expected_key=IDENTITY,expected_journal='none')
    monkeypatch.setattr(guarded,'run',run)
    with pytest.raises(ValueError,match='while awaiting admission'):pool.main('publish','sandbox','world.textures')
    assert f.stamp.read_bytes()==before and not f.journal.exists() and not f.cache.exists()


def test_original_parent_cannot_finalize_a_newer_attempt(fixture,monkeypatch):
    f=fixture;seed(f)
    def superseded(*_):
        record=state.read(f.journal);record['invocation']=uuid.uuid4().hex;state.write(f.journal,record)
    fake_guard(monkeypatch,after=superseded)
    with pytest.raises(ValueError,match='no longer this guarded transfer'):
        pool.main('restore','sandbox','world.textures')
    assert f.journal.exists() and not f.stamp.exists()


def test_pool_miss_and_invalid_producer_refuse_without_creating_a_barrier(fixture,monkeypatch):
    f=fixture;fake_guard(monkeypatch)
    with pytest.raises(ValueError,match='Pool miss'):pool.main('restore','sandbox','world.textures')
    assert not f.journal.exists() and f.stamp.exists()
    state.write(f.stamp,dict(fingerprint='source',pool_key=IDENTITY,touched=True))
    with pytest.raises(ValueError,match='fresh successful'):pool.main('publish','sandbox','world.textures')
    assert not f.journal.exists() and not f.cache.exists()


def test_matching_pool_resume_never_bypasses_other_installation_barriers(fixture,monkeypatch):
    f=fixture;fake_guard(monkeypatch,code=1)
    pool.main('publish','sandbox','world.textures')
    record=state.read(f.journal)
    for name in [build_snapshot.PACKAGE_JOURNAL,build_snapshot.JOURNAL,build_snapshot.PORTABLE_JOURNAL]:
        marker=f.ctx.out/name;marker.write_text('{}')
        with pytest.raises(SystemExit):build_snapshot.require_complete(f.ctx.out,game='sandbox',pool_resume=record)
        marker.unlink()


def test_partial_pool_transfer_blocks_default_root_even_with_an_output_override(fixture,monkeypatch,tmp_path):
    f=fixture;fake_guard(monkeypatch,code=1);pool.main('publish','sandbox','world.textures')
    alternate=tmp_path/'elsewhere'/'sandbox'
    with pytest.raises(SystemExit,match='pool transfer'):
        build_snapshot.require_complete(alternate,game='sandbox')
    with pytest.raises(SystemExit,match='pool transfer'):
        build_snapshot.require_launch(['editor','-project='+str(f.repo/'games/sandbox/unreal/Sandbox.uproject')],
                                      env={'ATELIER_BUILD_ROOT':str(alternate.parent)})


@pytest.mark.parametrize('roots',[['../outside'],['logs'],['stamps'],['a/../b'],['a','a/b'],['Content'],['a//b'],['LoGs'],['StAmPs'],['bINARIES'],['a','A/b'],
    ['caf\u00e9','cafe\u0301/b'],['caf\u00e9','cafe\u0301'],[state.JOURNAL],
    ['.REUSE-in-progress.json'],['.portable-snapshot-in-progress.json'],['.package-install-in-progress.json']])
def test_unsafe_or_ambiguous_journal_scope_refuses(roots):
    with pytest.raises(ValueError):state.owned_roots(roots)


def test_symlink_output_ancestor_refuses_before_any_copy(fixture,monkeypatch,tmp_path):
    f=fixture;elsewhere=tmp_path/'external';elsewhere.mkdir()
    f.step.pool_roots=[f.ctx.out/'linked'/'textures']
    f.step.outputs=[f.ctx.out/'linked'/'textures/output']
    (f.ctx.out/'linked').symlink_to(elsewhere,target_is_directory=True)
    fake_guard(monkeypatch)
    with pytest.raises(ValueError,match='symlink'):pool.main('publish','sandbox','world.textures')
    assert not f.journal.exists() and not list(elsewhere.iterdir())


def test_input_change_during_restore_retains_barrier_and_never_certifies(fixture,monkeypatch):
    f=fixture;seed(f)
    copy=pool.copy_tree
    def changing(*args,**kwargs):
        copy(*args,**kwargs)
        monkeypatch.setattr(pool,'key',lambda *a:'b'*64)
    monkeypatch.setattr(pool,'copy_tree',changing)
    fake_guard(monkeypatch)
    with pytest.raises(ValueError,match='scope changed'):pool.main('restore','sandbox','world.textures')
    assert f.journal.exists() and not f.stamp.exists()
    # Explicit abandonment remains available after source changes and preserves the immutable entry.
    fake_guard(monkeypatch)
    assert pool.main('abandon','sandbox','world.textures') == 0
    assert not f.folder.exists() and (f.cache/IDENTITY).is_dir()


@pytest.mark.parametrize('change',['identity','stamp','symlink'])
def test_bad_completion_cannot_install_a_stamp(fixture,monkeypatch,tmp_path,change):
    f=fixture;seed(f)
    def corrupt(command,folder,options):
        path=folder/'completed.json'
        value=state.read(path)
        if change=='identity':value['key']='b'*64
        if change=='stamp':value['stamp']['touched']=True
        if change=='symlink':
            other=tmp_path/'foreign.json';state.write(other,value)
            path.unlink();path.symlink_to(other)
        else:state.write(path,value)
    fake_guard(monkeypatch,after=corrupt)
    with pytest.raises((OSError,ValueError)):pool.main('restore','sandbox','world.textures')
    assert f.journal.exists() and not f.stamp.exists()


def test_new_journal_while_queued_is_not_silently_adopted(fixture,monkeypatch):
    f=fixture
    def run(command,folder,**options):
        # Another attempt made a valid durable claim after this caller's preflight.
        other=uuid.uuid4().hex
        tx.execute('publish','sandbox','world.textures',invocation=other,expected_key=IDENTITY,expected_journal='none')
        preserved=f.journal.read_bytes()
        with pytest.raises(ValueError,match='journal changed while awaiting'):
            tx.execute('publish','sandbox','world.textures',invocation=options['invocation_id'],
                       expected_key=IDENTITY,expected_journal='none')
        assert f.journal.read_bytes()==preserved
        return 1
    monkeypatch.setattr(guarded,'run',run)
    assert pool.main('publish','sandbox','world.textures') == 1
    assert not (f.cache/IDENTITY).exists() and f.journal.exists()


def test_foreign_project_launch_does_not_consult_controller_pool_journal(fixture,monkeypatch,tmp_path):
    f=fixture;fake_guard(monkeypatch,code=1);pool.main('publish','sandbox','world.textures')
    project=tmp_path/'other'/'games/sandbox/unreal/Sandbox.uproject'
    project.parent.mkdir(parents=True);project.write_text('{}')
    build_snapshot.require_launch(['editor',str(project)],env={})
    assert f.journal.exists()


def test_case_alias_of_logs_is_never_a_removable_pool_root(fixture,monkeypatch):
    f=fixture
    f.step.pool_roots=[f.ctx.out/'LoGs']
    f.step.outputs=[f.ctx.out/'LoGs/output']
    fake_guard(monkeypatch)
    with pytest.raises(ValueError,match='unsafe'):
        pool.main('publish','sandbox','world.textures')
    assert not f.journal.exists() and f.stamp.exists()
