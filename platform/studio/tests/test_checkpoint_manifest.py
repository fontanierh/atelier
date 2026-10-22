"""Build-time CAS publication and metadata-only merge retention with real small artifacts."""
from pathlib import Path

import pytest

from atelier import build, build_checkpoints, build_products, checkpoint_actions as actions
from atelier import checkpoint_manifest as manifests, checkpoint_store as cp, paths
from atelier.atomic_files import atomic_json
from test_checkpoints import fixture  # noqa: F401


def published(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    ctx.checkpoint_settings = {}
    fixture.produce(ctx, steps)
    monkeypatch.setattr(manifests, 'Store', lambda game: fixture.store)
    done = {}
    with manifests.writer(ctx.out):
        for step in steps:
            stamp = cp.read_json(ctx.stamps / (step.name + '.json'))
            actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done=done, produced=True)
            atomic_json(ctx.stamps / (step.name + '.json'), stamp)
            manifests.record(ctx, step, stamp, store=fixture.store)
            done[step.name] = build.result(step, stamp['fingerprint'], stamp)
            build_products.feed_results(done, stamp['products'])
        manifests.finish(ctx, steps)
    return ctx, steps


def test_retain_uses_only_published_metadata_and_stat_checks(fixture, monkeypatch):
    ctx, steps = published(fixture, monkeypatch)
    def forbidden(*a, **kw):
        pytest.fail('retention must not hash, capture, snapshot, or launch a guard')
    from atelier.harness.safety import guarded
    monkeypatch.setattr(actions, 'snapshot', forbidden)
    monkeypatch.setattr(actions, 'certified', forbidden)
    monkeypatch.setattr(cp, 'capture', forbidden)
    monkeypatch.setattr(cp, 'members', forbidden)
    monkeypatch.setattr(build_products, 'file_digest', forbidden)
    monkeypatch.setattr(guarded, 'run', forbidden)
    key = manifests.retain(paths.REPO, ctx.out, ctx.game)
    value = fixture.store.load(key)
    assert set(value['stamps']) == {s.name for s in steps}
    assert len(value['actions']) == 3
    for step in steps:
        member = 'generated/' + step.name + '/asset.bin'
        assert fixture.store.blob(value['files'][member]['sha256']).read_bytes() == step.name.encode()


@pytest.mark.parametrize('mutation', ['bytes', 'added', 'removed', 'replaced', 'touched'])
def test_changed_producer_refuses_without_hashing(fixture, monkeypatch, mutation):
    ctx, steps = published(fixture, monkeypatch)
    target = steps[0].outputs[0]
    if mutation == 'bytes':
        target.write_bytes(b'TREE')
    elif mutation == 'added':
        (target.parent / 'surprise').write_bytes(b'extra')
    elif mutation == 'removed':
        target.unlink()
    elif mutation == 'replaced':
        data = target.read_bytes(); target.unlink(); target.write_bytes(data)
    else:
        stamp = cp.read_json(ctx.stamps / 'tree.json'); stamp['touched'] = True
        atomic_json(ctx.stamps / 'tree.json', stamp)
    monkeypatch.setattr(build_products, 'file_digest', lambda *a: pytest.fail('must only stat'))
    with pytest.raises(cp.CheckpointError, match='metadata changed|incomplete or stale'):
        manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_active_build_refuses_immediately(fixture, monkeypatch):
    ctx, _ = published(fixture, monkeypatch)
    with manifests.writer(ctx.out):
        with pytest.raises(cp.CheckpointError, match='Producer is building'):
            manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_old_producer_does_not_silently_run_capture(fixture, monkeypatch):
    ctx, steps = fixture.checkout('old')
    fixture.produce(ctx, steps)
    monkeypatch.setattr(build_checkpoints, 'capture_local', lambda *a, **kw: pytest.fail('slow fallback'))
    with pytest.raises(cp.CheckpointError, match='normal incremental build once'):
        manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_new_stamp_cannot_reuse_old_ready_manifest(fixture, monkeypatch):
    ctx, _ = published(fixture, monkeypatch)
    p = ctx.stamps / 'tree.json'; stamp = cp.read_json(p); stamp['time'] += 1; atomic_json(p, stamp)
    with pytest.raises(cp.CheckpointError, match='incomplete or stale'):
        manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_failed_task_is_not_published_but_completed_work_survives(fixture, monkeypatch):
    ctx, steps = published(fixture, monkeypatch)
    (ctx.stamps / 'combat.json').unlink()
    manifests.finish(ctx, steps)
    key = manifests.retain(paths.REPO, ctx.out, ctx.game)
    value = fixture.store.load(key)
    assert set(value['stamps']) == {'tree', 'house'}
    assert all(a['task'] != 'combat' for a in value['actions'].values())
    assert 'combat' not in value.get('incremental_stamps', {})
    # Remaining bytes are workspace seed only, never failed-task success.
    assert 'generated/combat/asset.bin' in value['files']


def test_linked_metadata_root_is_refused_before_lock_write(fixture, monkeypatch, tmp_path):
    ctx, _ = published(fixture, monkeypatch)
    import shutil
    root = manifests.folder(ctx.out); shutil.rmtree(root)
    elsewhere = tmp_path / 'foreign'; elsewhere.mkdir(); root.symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(cp.CheckpointError, match='real directory'):
        manifests.retain(paths.REPO, ctx.out, ctx.game)
    assert not list(elsewhere.iterdir())


def test_corrupt_cas_stat_refuses_without_rehash(fixture, monkeypatch):
    ctx, _ = published(fixture, monkeypatch)
    ready = cp.read_json(manifests.folder(ctx.out) / 'ready.json')
    manifest = fixture.store.load(ready['key'])
    digest = next(iter(manifest['blob_observations']))
    fixture.store.blob(digest).write_bytes(b'corrupt')
    monkeypatch.setattr(build_products, 'file_digest', lambda *a: pytest.fail('must only stat'))
    with pytest.raises(cp.CheckpointError, match='CAS blob metadata changed'):
        manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_noop_build_publication_reuses_existing_cas_hashes(fixture, monkeypatch):
    ctx, steps = published(fixture, monkeypatch)
    monkeypatch.setattr(manifests, 'digest_file', lambda *a: pytest.fail('unchanged files must not be rehashed'))
    monkeypatch.setattr(fixture.store, 'put', lambda *a: pytest.fail('unchanged files must not be recopied'))
    manifests.finish(ctx, steps)
    manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_real_legacy_build_publishes_all_workspace_files_then_retains_without_capture(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from atelier import build_cache
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    out = repo / 'build/fixture'
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps',
                          cook_mode=build.CookMode.DEFAULT)
    source = repo / 'source.py'; source.write_text('# actual legacy input')
    step = build.Step('legacy', [build.Python(source)], inputs=[source], outputs=[out / 'asset/sentinel'])
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: dict(tool='fixed'))
    def run(*args, **kwargs):
        step.outputs[0].parent.mkdir(parents=True, exist_ok=True)
        step.outputs[0].write_bytes(b'primary')
        (out / 'asset/sidecar').write_bytes(b'also required')
    monkeypatch.setattr(build, 'run_command', run)
    assert build.build('fixture') == 0
    monkeypatch.setattr(manifests, 'digest_file', lambda *a: pytest.fail('retain hashes no payload'))
    key = manifests.retain(repo, out, 'fixture')
    manifest = cp.Store('fixture').load(key)
    assert set(manifest['incremental_stamps']) == {'legacy'}
    assert manifest['stamps'] == {}
    assert 'generated/asset/sentinel' in manifest['files']
    assert 'generated/asset/sidecar' in manifest['files']
    assert manifest['actions'] == {}  # No invented complete portable action scope.


def test_build_workspace_staging_does_not_accumulate_full_checkpoint_versions(fixture, monkeypatch):
    ctx, steps = published(fixture, monkeypatch)
    before = set(fixture.store.manifests.glob('*.json'))
    for i in range(3):
        (ctx.out / f'extra-{i}').write_text(str(i))
        with fixture.store.locked():
            manifests._workspace(ctx, fixture.store)
    assert set(fixture.store.manifests.glob('*.json')) == before
    assert len(list((fixture.store.directory / 'workspaces').glob('*.json'))) == 1
    manifests.finish(ctx, steps)
    assert manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_three_hundred_step_build_retains_without_payload_work(tmp_path, monkeypatch):
    import time
    from types import SimpleNamespace
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    out = repo / 'build/fixture'
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps',
                          cook_mode=build.CookMode.DEFAULT)
    source = repo / 'recipe.txt'; source.write_text('300 actual legacy build steps')
    steps = []
    for i in range(300):
        primary = out / 'assets' / f'{i}.bin'
        def emit(ctx, log, primary=primary):
            primary.parent.mkdir(parents=True, exist_ok=True)
            primary.write_bytes(b'artifact')
            primary.with_suffix('.sidecar').write_bytes(b'complete workspace companion')
        steps.append(build.Step(f'asset{i}', [build.Call(f'emit{i}', emit)], inputs=[source], outputs=[primary]))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    assert build.build('fixture', echo=lambda _: None) == 0
    def forbidden(*a, **kw):
        pytest.fail('retention must reuse the build publication, not hash or copy payloads')
    monkeypatch.setattr(manifests, 'digest_file', forbidden)
    monkeypatch.setattr(cp.Store, 'put', forbidden)
    monkeypatch.setattr(actions, 'snapshot', forbidden)
    started = time.perf_counter()
    key = manifests.retain(repo, out, 'fixture')
    elapsed = time.perf_counter() - started
    value = cp.Store('fixture').load(key)
    assert len(value['incremental_stamps']) == 300
    assert len([v for v in value['files'].values() if v['kind'] == 'file']) == 600
    print(f'300-step/600-file actual build: retain={elapsed:.4f}s; zero payload hashing/copying')


def test_retain_never_waits_for_another_producers_cas_publication(fixture, monkeypatch):
    ctx, _ = published(fixture, monkeypatch)
    monkeypatch.setattr(fixture.store, 'locked', lambda: pytest.fail('retention reads immutable published metadata; no global writer wait'))
    assert manifests.retain(paths.REPO, ctx.out, ctx.game)


def test_interrupted_build_does_not_start_workspace_finalization(monkeypatch):
    from types import SimpleNamespace
    ctx = SimpleNamespace(cook_mode=build.CookMode.DEFAULT)
    def interrupted(ctx, *a, checkpoint, **kw):
        checkpoint['steps'] = []
        raise KeyboardInterrupt
    monkeypatch.setattr(build, '_execute_build', interrupted)
    monkeypatch.setattr(build, '_discard_changed_certificates', lambda *a, **kw: [])
    monkeypatch.setattr(manifests, 'finish', lambda *a: pytest.fail('cancel must not start publication'))
    with pytest.raises(KeyboardInterrupt):
        build._build(ctx, (), force=False, touch=False, echo=print, index=None)


def test_completed_cook_exports_zen_before_workspace_publication(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    ctx.checkpoint_settings = {}
    fixture.produce(ctx, steps)
    project = ctx.out / 'project/Game.uproject'
    project.parent.mkdir(parents=True)
    marker = project.parent / 'Saved/Cooked/Mac/ue.projectstore'
    marker.parent.mkdir(parents=True); marker.write_text('cook')
    ctx.uproject = project
    step = steps[0]
    step.commands = [build.UnrealPackage('Game', ctx.out / 'archive')]
    stamp = cp.read_json(ctx.stamps / (step.name + '.json'))
    events = []
    monkeypatch.setattr(actions, 'key', lambda *a: None)
    monkeypatch.setattr(build_checkpoints, '_guard', lambda ctx, op: events.append(op))
    monkeypatch.setattr(manifests, '_workspace', lambda *a: events.append('workspace'))
    manifests.record(ctx, step, stamp, store=fixture.store)
    assert events == ['export-zen', 'workspace']
    manifests.record(ctx, step, stamp, store=fixture.store)
    assert events == ['export-zen', 'workspace']


def test_obsolete_recipe_stamps_are_observed_without_forging_certificates(fixture, monkeypatch):
    ctx, steps = published(fixture, monkeypatch)
    atomic_json(ctx.stamps / 'obsolete.json', dict(fingerprint='old'))
    manifests.finish(ctx, steps)
    value = fixture.store.load(manifests.retain(paths.REPO, ctx.out, ctx.game))
    assert 'obsolete' not in value['stamps']
    assert 'obsolete' not in value.get('incremental_stamps', {})
