"""Detached upload lifecycle and durable resume, without native work or real network."""
import json
from pathlib import Path

import pytest

from atelier import build_checkpoints, checkpoint_backup as backup, checkpoint_github as gh, release
from test_checkpoint_github import checkpoint, fixture
from test_release import package, REVISION, SPEC, TAG


def queued(fixture, tmp_path):
    _, store, _ = fixture
    key = checkpoint(store, tmp_path, [b'immutable retained bytes'])
    return backup.queue(store, 'owner/private', key, 'playtest-1', 'c' * 40, public_repository='owner/game')


def test_request_is_durable_before_upload_and_conflicting_identity_is_preserved(fixture, tmp_path):
    path = queued(fixture, tmp_path)
    original = path.read_bytes(); record = json.loads(original)
    assert record['state'] == 'waiting-public' and 'source' not in record
    with pytest.raises(backup.CheckpointError, match='differs'):
        backup.queue(fixture[1], 'other/private', record['key'], record['tag'], record['revision'], public_repository='owner/game')
    assert path.read_bytes() == original


def test_upload_worker_uses_only_immutable_store_and_survives_missing_producer(fixture, tmp_path, monkeypatch):
    path = queued(fixture, tmp_path)
    record = json.loads(path.read_text()); record['state'] = 'pending'; backup.save(path, record)
    monkeypatch.setattr(gh, 'Remote', lambda *a, **kw: fixture[2])
    monkeypatch.setattr(backup.paths, 'REPO', tmp_path / 'producer-no-longer-exists')
    assert backup.run(path) == 0
    assert json.loads(path.read_text())['state'] == 'complete'
    assert len(fixture[2].candidates()) == 1
    assert len(fixture[0].releases) == 2  # Completion index plus immutable pack storage.


def test_failed_upload_retains_request_and_reuses_completed_remote_assets(fixture, tmp_path, monkeypatch):
    path = queued(fixture, tmp_path)
    record = json.loads(path.read_text()); record['state'] = 'pending'; backup.save(path, record)
    remote = fixture[2]; monkeypatch.setattr(gh, 'Remote', lambda *a, **kw: remote)
    publish = remote.publish
    def interrupted(*a, **kw):
        def fail():
            raise release.PublishError('interrupted before completion')
        return publish(*a, **{**kw, 'revalidate': fail})
    monkeypatch.setattr(remote, 'publish', interrupted)
    assert backup.run(path) == 1
    assert json.loads(path.read_text())['state'] == 'failed'
    count = len([e for e in fixture[0].events if e[0] == 'upload'])
    monkeypatch.setattr(remote, 'publish', publish)
    assert backup.run(path) == 0
    assert json.loads(path.read_text())['attempts'] == 2
    assert len([e for e in fixture[0].events if e[0] == 'upload']) == count + 1  # index only


def test_waiting_public_request_cannot_start_upload(fixture, tmp_path):
    path = queued(fixture, tmp_path)
    with pytest.raises(backup.CheckpointError, match='not completed'):
        backup.run(path)
    assert not fixture[0].events


def test_detached_launch_failure_keeps_pending_record(fixture, tmp_path, monkeypatch):
    path = queued(fixture, tmp_path); commands = []
    def spawn(argv, **kw):
        commands.append((argv, kw))
        raise OSError('launcher unavailable')
    monkeypatch.setattr(backup.subprocess, 'Popen', spawn)
    messages = []; backup.start(path, echo=messages.append)
    assert commands[0][1]['start_new_session'] and commands[0][1]['close_fds']
    assert str(path) in commands[0][0]
    assert json.loads(path.read_text())['state'] == 'pending'
    assert 'public release is ready' in messages[-1].lower()


def test_active_worker_does_not_block_public_replay_or_start_duplicate(fixture, tmp_path, monkeypatch):
    path = queued(fixture, tmp_path)
    record = json.loads(path.read_text())
    monkeypatch.setattr(backup.subprocess, 'Popen', lambda *a, **kw: pytest.fail('duplicate worker'))
    with backup.locked(path):
        assert backup.queue(fixture[1], record['repository'], record['key'], record['tag'], record['revision'],
                            public_repository=record['public_repository']) == path
        backup.start(path, echo=lambda _: None)
        assert backup.run(path) == 0


@pytest.mark.parametrize('failure', ['none', 'prepare', 'spawn'])
def test_public_release_precedes_detached_private_upload_and_private_failure_cannot_fail_it(package, tmp_path, monkeypatch, failure):
    root, proof, _, _ = package
    events = []
    monkeypatch.setattr(release, 'source_identity', lambda *a: (REVISION, 'owner/repo', SPEC))
    monkeypatch.setattr(release.paths, 'build_dir', lambda game: tmp_path / 'controller')
    def prepare(*a, **kw):
        events.append('retain-local')
        if failure == 'prepare':
            raise backup.CheckpointError('capture failed')
        return Path('immutable-backup-request')
    monkeypatch.setattr(build_checkpoints, 'prepare_publication', prepare)
    def publish(*a, **kw):
        events.append('public'); kw['revalidate']()
        return {'html_url': 'public-release'}
    monkeypatch.setattr(release, 'publish_assets', publish)
    def start(*a, **kw):
        events.append('detach')
        # The real launcher absorbs Popen failures, exercised above.
        if failure == 'spawn':
            kw['echo']('private backup remains pending')
    monkeypatch.setattr(backup, 'start', start)
    messages = []; monkeypatch.setattr(release, 'say', messages.append)
    assert release.main('game', root, tag=TAG, verification=proof, source=tmp_path) == 0
    assert events == ['retain-local', 'public'] + ([] if failure == 'prepare' else ['detach'])
    assert any('published verified release: public-release' in m for m in messages)


@pytest.mark.parametrize('origin', ['new', 'pending'])
def test_prepare_reuses_durable_capture_without_upload_or_recapture(fixture, tmp_path, monkeypatch, origin):
    remote = fixture[2]
    game = tmp_path / 'producer/games/fixture'; game.mkdir(parents=True)
    (game / 'game.toml').write_text('[checkpoints]\nrebuild_budget_seconds=600\n')
    config = tmp_path / 'config'; config.mkdir(); (config / 'settings.json').write_text('{"repository":"owner/private"}')
    monkeypatch.setattr(build_checkpoints.paths, 'cache_dir', lambda *a, **kw: config)
    monkeypatch.setattr(build_checkpoints, 'Store', lambda _: fixture[1])
    monkeypatch.setattr(gh, 'Remote', lambda *a, **kw: remote)
    key = checkpoint(fixture[1], tmp_path, [b'captured'])
    calls = []
    monkeypatch.setattr(build_checkpoints, 'capture_local', lambda *a: calls.append('capture') or key)
    monkeypatch.setattr(remote, 'require_private', lambda: pytest.fail('private network before public release'))
    monkeypatch.setattr(release, 'find_release', lambda *a: pytest.fail('private network before public release'))
    if origin == 'pending':
        backup.queue(fixture[1], 'owner/private', key, 'playtest-1', 'c' * 40, public_repository='owner/game')
    path = build_checkpoints.prepare_publication(game.parents[1], 'fixture', 'playtest-1', 'c' * 40,
        revalidate=lambda: calls.append('revalidate'), public_repository='owner/game')
    assert json.loads(path.read_text())['key'] == key
    assert calls == (['capture'] if origin == 'new' else []) + ['revalidate']
    assert not fixture[0].events



def test_frozen_worker_runtime_imports_without_checkout_or_site_packages(tmp_path):
    import subprocess
    import sys
    runtime = backup.snapshot_runtime(tmp_path)
    code = ('import sys; sys.path.insert(0,sys.argv[1]); '
            'import atelier.checkpoint_backup,atelier.checkpoint_github,atelier.checkpoint_actions; '
            'assert all(str(m.__file__).startswith(sys.argv[1]) for n,m in sys.modules.items() '
            'if n.startswith("atelier") and hasattr(m,"__file__")); print("isolated upload runtime ready")')
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(runtime)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'isolated upload runtime ready' in result.stdout
    assert backup.snapshot_runtime(tmp_path) == runtime


def test_explicit_old_backup_resume_refuses_wrong_source_without_recapture(fixture, tmp_path, monkeypatch):
    remote = fixture[2]
    key = checkpoint(fixture[1], tmp_path, [b'captured'])
    config = tmp_path / 'config'; config.mkdir(); (config / 'settings.json').write_text('{"repository":"owner/private"}')
    monkeypatch.setattr(backup.paths, 'cache_dir', lambda *a, **kw: config)
    monkeypatch.setattr(gh, 'Remote', lambda *a, **kw: remote)
    monkeypatch.setattr(release, 'find_release', lambda *a: dict(id=1, draft=True,
        tag_name=remote.prefix + 'playtest-1', name=remote.prefix + 'playtest-1',
        body='Build checkpoint ' + key + '\nSource wrong', prerelease=False, target_commitish='main'))
    monkeypatch.setattr(backup, 'start', lambda *a, **kw: pytest.fail('unsafe resume'))
    with pytest.raises(release.PublishError, match='conflicts'):
        backup.resume('fixture', key, 'playtest-1', 'c' * 40, 'owner/game')


def test_frozen_worker_executes_real_publish_from_cas_with_fake_transport(fixture, tmp_path):
    import inspect
    import subprocess
    import sys
    from test_checkpoint_github import GitHub, Remote
    path = queued(fixture, tmp_path)
    record = json.loads(path.read_text()); record['state'] = 'pending'; backup.save(path, record)
    runtime = backup.snapshot_runtime(path.parent)
    code = ('import sys,hashlib,threading; from pathlib import Path; from copy import deepcopy; '
            'sys.path.insert(0,sys.argv[1]); '
            'from atelier import checkpoint_github as gh,checkpoint_store as cp,release,checkpoint_backup as backup\n'
            'def sha(value): return hashlib.sha256(value).hexdigest()\n' + inspect.getsource(GitHub) + '\n' +
            inspect.getsource(Remote) + '\n' +
            'github=GitHub(); remote=Remote("owner/private","fixture",github=github); '
            'gh.Remote=lambda *a,**kw:remote; assert backup.run(Path(sys.argv[2]))==0; '
            'assert github.releases[1]["draft"] is False\n')
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(runtime), str(path)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(path.read_text())['state'] == 'complete'


@pytest.mark.parametrize('damage', [None, 'key', 'repository', 'revision', 'public_repository', 'missing'])
def test_resume_before_private_draft_uses_exact_durable_request(fixture, tmp_path, monkeypatch, damage):
    path = queued(fixture, tmp_path)
    value = json.loads(path.read_text()); key = value['key']
    value['state'] = 'failed'
    if damage == 'missing':
        path.unlink()
    else:
        if damage is not None:
            value[damage] = 'e' * 64 if damage == 'key' else 'wrong'
        backup.save(path, value)
    config = tmp_path / 'config'; config.mkdir()
    (config / 'settings.json').write_text('{"repository":"owner/private"}')
    monkeypatch.setattr(backup.paths, 'cache_dir', lambda *a, **kw: config)
    monkeypatch.setattr(backup, 'Store', lambda game: fixture[1])
    monkeypatch.setattr(gh, 'Remote', lambda *a, **kw: fixture[2])
    public = object()
    monkeypatch.setattr(release, 'GitHub', lambda *a: public)
    monkeypatch.setattr(release, 'find_release', lambda client, tag: dict(draft=False) if client is public else None)
    observed = []
    monkeypatch.setattr(release, 'check_tag', lambda *a, **kw: observed.append('public verified'))
    monkeypatch.setattr(release, 'asset_map', lambda *a: dict.fromkeys(['SHA256SUMS', 'manifest.json', 'verification.json']))
    monkeypatch.setattr(backup, 'start', lambda target, **kw: observed.append(target))
    if damage is not None:
        with pytest.raises(backup.CheckpointError, match='matching retained'):
            backup.resume('fixture', key, 'playtest-1', 'c' * 40, 'owner/game')
        assert not observed
    else:
        result = backup.resume('fixture', key, 'playtest-1', 'c' * 40, 'owner/game')
        assert result['checkpoint'] == key
        assert observed == ['public verified', path]
        assert not fixture[0].events


def test_capture_source_binding_cannot_be_relabelled(fixture, tmp_path):
    _, store, remote = fixture
    key = checkpoint(store, tmp_path, [b'captured'])
    captured = store.save(dict(store.load(key), source_revision='c' * 40))
    with pytest.raises(backup.CheckpointError, match='Captured checkpoint source'):
        backup.queue(store, 'owner/private', captured, 'playtest-1', 'd' * 40, public_repository='owner/game')
    with pytest.raises(backup.CheckpointError, match='Captured checkpoint source'):
        remote.publish(store, captured, 'playtest-1', revision='d' * 40)
    assert not fixture[0].events
