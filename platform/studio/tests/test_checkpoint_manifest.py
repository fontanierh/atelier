"""Build-time CAS publication and metadata-only merge retention with real small artifacts."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_checkpoints, build_products, checkpoint_actions as actions
from atelier import checkpoint_manifest as manifests, checkpoint_store as cp, native_protocol, paths
from atelier.atomic_files import atomic_json
from test_checkpoints import fixture  # noqa: F401


def prepared(fixture, monkeypatch, name='producer'):
    """Publish every certificate and record, and stop just before one manifest publication."""
    ctx, steps = fixture.checkout(name)
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
    return ctx, steps


def published(fixture, monkeypatch, name='producer'):
    ctx, steps = prepared(fixture, monkeypatch, name)
    with manifests.writer(ctx.out):
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


def test_representative_step_publishes_its_written_files_and_restores_when_they_drift(tmp_path, monkeypatch):
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
    # The run credits the step with every file it wrote, not just its representative output.
    stamp = json.loads((out / 'stamps/legacy.json').read_bytes())
    assert set(stamp['output_inventory']) == {'generated/asset/sentinel', 'generated/asset/sidecar'}
    monkeypatch.setattr(manifests, 'digest_file', lambda *a: pytest.fail('retain hashes no payload'))
    key = manifests.retain(repo, out, 'fixture')
    manifest = cp.Store('fixture').load(key)
    # It owns the files it wrote, so it publishes an action entry like any other step.
    assert set(manifest['stamps']) == {'legacy'} and not manifest['incremental_stamps']
    assert {'generated/asset/sentinel', 'generated/asset/sidecar'} <= set(manifest['files'])
    # A written file that no longer matches its stamp makes the step stale: its own entry puts it back.
    (out / 'asset/sidecar').write_bytes(b'replaced by another producer')
    runs = []
    monkeypatch.setattr(build, 'run_command', lambda *a, **kw: runs.append(1) or run())
    messages = []
    assert build.build('fixture', echo=messages.append) == 0
    assert not runs and any(m.startswith('legacy') and 'restored in' in m for m in messages)
    assert (out / 'asset/sidecar').read_bytes() == b'also required'


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
        steps.append(build.Step(f'asset{i}', [build.Call(f'emit{i}', emit)], inputs=[source], outputs=[primary],
                                products=[build.Product(f'asset{i}', (primary, primary.with_suffix('.sidecar')))]))
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
    assert len(value['stamps']) == 300
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


def test_unconfigured_build_does_not_acquire_checkpoint_metadata_lock(tmp_path, monkeypatch):
    from types import SimpleNamespace
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture',
                          cook_mode=build.CookMode.DEFAULT)
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: None)
    monkeypatch.setattr(build, '_build', lambda *a, **kw: 0)
    monkeypatch.setattr(manifests, 'writer', lambda *a: pytest.fail('unconfigured build acquired checkpoint writer'))
    assert build.build('fixture') == 0
    assert not (ctx.out / '.state/retention').exists()


def publication_limit(store, ctx, manifest_size):
    """A limit below the assembled manifest, above every file the publication re-reads."""
    directories = (ctx.stamps, manifests.folder(ctx.out) / 'tasks', store.directory / 'actions',
                   store.directory / 'workspaces')
    reread = max(path.stat().st_size for directory in directories for path in directory.glob('*.json'))
    limit = (reread + manifest_size) // 2
    assert reread < limit < manifest_size, (reread, limit, manifest_size)
    return limit


class CapBelow(cp.Store):
    """Set the limit one byte below the manifest the run actually assembles.

    A run that drops a step assembles a smaller candidate than the store's previous manifest, so a
    cap derived from that older, bigger manifest can sit above the candidate and let it publish.
    """

    def __init__(self, game, directory, monkeypatch):
        super().__init__(game, directory)
        self.monkeypatch, self.sizes = monkeypatch, []

    def save(self, manifest):
        self.sizes.append(len(native_protocol.canonical(manifest)))
        self.monkeypatch.setattr(native_protocol, 'MAX_MANIFEST', self.sizes[-1] - 1)
        return super().save(manifest)


def test_a_manifest_that_fits_is_published(fixture, monkeypatch):
    ctx, _ = published(fixture, monkeypatch)
    ready = json.loads((manifests.folder(ctx.out) / 'ready.json').read_text())
    assert fixture.store.load(ready['key'])['game'] == 'fixture'


def test_an_oversized_first_manifest_publishes_nothing(fixture, monkeypatch, capsys):
    donor, _ = published(fixture, monkeypatch, 'donor')
    size = len(native_protocol.canonical(fixture.store.load(
        json.loads((manifests.folder(donor.out) / 'ready.json').read_text())['key'])))
    ctx, steps = prepared(fixture, monkeypatch, 'producer-oversized')
    manifests_before = sorted(fixture.store.manifests.glob('*.json'))
    blobs_before = sorted(path for path in fixture.store.blobs.rglob('*') if path.is_file())
    monkeypatch.setattr(native_protocol, 'MAX_MANIFEST', publication_limit(fixture.store, ctx, size))
    capsys.readouterr()
    manifests.finish(ctx, steps)
    assert 'checkpoint not published; receivers keep the previous checkpoint' in capsys.readouterr().out
    assert not (manifests.folder(ctx.out) / 'ready.json').exists()
    assert sorted(fixture.store.manifests.glob('*.json')) == manifests_before
    assert sorted(path for path in fixture.store.blobs.rglob('*') if path.is_file()) == blobs_before
    assert all((ctx.stamps / (step.name + '.json')).is_file() for step in steps)


def test_an_oversized_manifest_keeps_the_previous_checkpoint_bytes(fixture, monkeypatch, capsys):
    ctx, steps = prepared(fixture, monkeypatch)
    manifests.finish(ctx, steps)
    ready = manifests.folder(ctx.out) / 'ready.json'
    before = ready.read_bytes()
    size = len(native_protocol.canonical(fixture.store.load(json.loads(before)['key'])))
    manifests_before = {path.name: path.read_bytes() for path in fixture.store.manifests.glob('*.json')}
    blobs_before = sorted(path.name for path in fixture.store.blobs.rglob('*') if path.is_file())
    monkeypatch.setattr(native_protocol, 'MAX_MANIFEST', publication_limit(fixture.store, ctx, size))
    capsys.readouterr()
    manifests.finish(ctx, steps)
    assert 'checkpoint not published; receivers keep the previous checkpoint' in capsys.readouterr().out
    assert ready.read_bytes() == before
    assert {path.name: path.read_bytes() for path in fixture.store.manifests.glob('*.json')} == manifests_before
    assert sorted(path.name for path in fixture.store.blobs.rglob('*') if path.is_file()) == blobs_before


def test_the_member_byte_total_is_not_a_skip(fixture, monkeypatch):
    ctx, steps = prepared(fixture, monkeypatch)
    sizes = [path.stat().st_size for path in ctx.out.rglob('asset.bin')]
    limit = sum(sizes) - 1     # Above every single member, below their total.
    assert max(sizes) <= limit
    monkeypatch.setattr(native_protocol, 'MAX_BYTES', limit)
    with pytest.raises(cp.CheckpointError) as caught:
        manifests.finish(ctx, steps)
    assert not isinstance(caught.value, cp.ManifestTooLarge)
    assert 'exceeds its size limit' in str(caught.value)
    assert not (manifests.folder(ctx.out) / 'ready.json').exists()


def test_a_publication_io_error_is_not_a_skip(fixture, monkeypatch):
    ctx, steps = prepared(fixture, monkeypatch)
    fixture.store.manifests.write_text('not a directory')
    with pytest.raises(OSError):
        manifests.finish(ctx, steps)
    assert not (manifests.folder(ctx.out) / 'ready.json').exists()


def test_a_corrupt_certificate_is_not_a_skip(fixture, monkeypatch):
    ctx, steps = prepared(fixture, monkeypatch)
    stamp = cp.read_json(ctx.stamps / 'tree.json'); stamp['fingerprint'] = 'not-hex'
    atomic_json(ctx.stamps / 'tree.json', stamp)
    record = cp.read_json(manifests.folder(ctx.out) / 'tasks/tree.json'); record['stamp'] = stamp
    atomic_json(manifests.folder(ctx.out) / 'tasks/tree.json', record)
    with pytest.raises(cp.CheckpointError, match='certificate'):
        manifests.finish(ctx, steps)
    assert not (manifests.folder(ctx.out) / 'ready.json').exists()
    assert not list(fixture.store.manifests.glob('*.json'))


def test_an_oversized_manifest_that_is_also_corrupt_is_refused_not_skipped(fixture, monkeypatch, capsys):
    ctx, steps = prepared(fixture, monkeypatch)
    manifests.finish(ctx, steps)
    ready = manifests.folder(ctx.out) / 'ready.json'
    before = ready.read_bytes()
    size = len(native_protocol.canonical(fixture.store.load(json.loads(before)['key'])))
    # A keyless record carries its stamp straight into the manifest, so the corrupt certificate is
    # the one `validate` sees last, after the size gate would have fired in the old ordering.
    stamp = cp.read_json(ctx.stamps / 'tree.json'); stamp['fingerprint'] = 'not-hex'
    atomic_json(ctx.stamps / 'tree.json', stamp)
    record_path = manifests.folder(ctx.out) / 'tasks/tree.json'
    record = cp.read_json(record_path); record['stamp'] = stamp; record['action'] = None
    atomic_json(record_path, record)
    monkeypatch.setattr(native_protocol, 'MAX_MANIFEST', publication_limit(fixture.store, ctx, size))
    manifests_before = sorted(fixture.store.manifests.glob('*.json'))
    capsys.readouterr()
    with pytest.raises(cp.CheckpointError) as caught:
        manifests.finish(ctx, steps)
    assert not isinstance(caught.value, cp.ManifestTooLarge)
    assert 'certificate' in str(caught.value)
    assert 'checkpoint not published' not in capsys.readouterr().out
    assert sorted(fixture.store.manifests.glob('*.json')) == manifests_before
    assert ready.read_bytes() == before


class LateCorruption(cp.Store):
    """A stored manifest carrying corruption that the producer's own finish cannot construct.

    finish puts a finished step in exactly one of ``stamps`` and ``incremental_stamps``, and never
    writes ``historical_stamps``, so these two manifests exist only when they come back from a store.
    """

    def __init__(self, game, directory, corruption):
        super().__init__(game, directory)
        self.corruption = corruption

    def save(self, manifest):
        doctored = dict(manifest)
        name = sorted(doctored['stamps'])[0]
        stamp = doctored['stamps'][name]
        if self.corruption == 'incremental':
            doctored['incremental_stamps'] = {name: stamp}
        elif self.corruption == 'historical':
            doctored['historical_stamps'] = {name: stamp}
        elif self.corruption == 'certificate':
            doctored['stamps'] = {**doctored['stamps'], name: dict(stamp, fingerprint='not-hex')}
        else:
            raise AssertionError(self.corruption)
        return super().save(doctored)


@pytest.mark.parametrize('corruption, message', [
    ('certificate', 'invalid or touched certificate'),
    ('incremental', 'Invalid incremental checkpoint state'),
    ('historical', 'Invalid historical candidate evidence'),
])
def test_an_oversized_manifest_with_late_corruption_is_refused_not_skipped(
        fixture, monkeypatch, capsys, corruption, message):
    ctx, steps = prepared(fixture, monkeypatch)
    with manifests.writer(ctx.out):
        manifests.finish(ctx, steps)
    ready = manifests.folder(ctx.out) / 'ready.json'
    before = ready.read_bytes()
    size = len(native_protocol.canonical(fixture.store.load(json.loads(before)['key'])))
    manifests_before = sorted(fixture.store.manifests.glob('*.json'))
    monkeypatch.setattr(manifests, 'Store',
                        lambda game: LateCorruption(game, fixture.store.directory, corruption))
    monkeypatch.setattr(native_protocol, 'MAX_MANIFEST', publication_limit(fixture.store, ctx, size))
    capsys.readouterr()
    with pytest.raises(cp.CheckpointError, match=message) as caught:
        manifests.finish(ctx, steps)
    assert not isinstance(caught.value, cp.ManifestTooLarge)
    assert 'checkpoint not published' not in capsys.readouterr().out
    assert sorted(fixture.store.manifests.glob('*.json')) == manifests_before
    assert ready.read_bytes() == before


def build_project(tmp_path, monkeypatch):
    """A real build with checkpoints enabled and its commands replaced: nothing native runs."""
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture', logs=repo / 'build/fixture/logs',
                          stamps=repo / 'build/fixture/stamps', cook_mode=build.CookMode.DEFAULT)
    steps = []
    for name in ('mesh', 'extra'):
        source = repo / (name + '.txt'); source.write_text(name)
        script = repo / (name + '.py'); script.write_text('# ' + name)
        steps.append(build.Step(name, [build.Python(script)], inputs=[source],
                                products=[build.Product(name, (ctx.out / name,))]))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: dict(tool='fixed'))
    behaviour, ran = {}, []

    def run(ctx, step, command, log, *args, **kw):
        failure = behaviour.get(step.name)
        if failure is not None:
            raise failure
        ran.append(step.name)
        (ctx.out / step.name).mkdir(parents=True, exist_ok=True)
        (ctx.out / step.name / 'data').write_text(step.name)

    monkeypatch.setattr(build, 'run_command', run)
    messages = []
    return SimpleNamespace(ctx=ctx, repo=repo, behaviour=behaviour, ran=ran, messages=messages,
                           run=lambda **kw: build.build('fixture', echo=messages.append, **kw))


def test_a_skipped_publication_leaves_a_successful_build_successful(tmp_path, monkeypatch, capsys):
    p = build_project(tmp_path, monkeypatch)
    assert p.run() == 0
    ready = manifests.folder(p.ctx.out) / 'ready.json'
    assert ready.is_file(), 'the first build must publish its checkpoint'
    before = ready.read_bytes()
    store = cp.Store('fixture')
    size = len(native_protocol.canonical(store.load(json.loads(before)['key'])))
    monkeypatch.setattr(native_protocol, 'MAX_MANIFEST', publication_limit(store, p.ctx, size))
    (p.repo / 'mesh.txt').write_text('changed mesh')
    capsys.readouterr()
    assert p.run() == 0, p.messages
    out = capsys.readouterr().out
    assert 'checkpoint not published; receivers keep the previous checkpoint' in out, p.messages
    assert ready.read_bytes() == before


def test_a_skipped_publication_never_turns_a_failure_into_success(tmp_path, monkeypatch, capsys):
    p = build_project(tmp_path, monkeypatch)
    assert p.run() == 0
    ready = manifests.folder(p.ctx.out) / 'ready.json'
    before = ready.read_bytes()
    store = cp.Store('fixture')
    manifests_before = sorted(store.manifests.glob('*.json'))
    capped = CapBelow('fixture', store.directory, monkeypatch)
    monkeypatch.setattr(manifests, 'Store', lambda game: capped)
    p.behaviour['extra'] = RuntimeError('fixture failure')
    (p.repo / 'mesh.txt').write_text('changed mesh')
    (p.repo / 'extra.txt').write_text('changed extra')
    capsys.readouterr()
    assert p.run() == 1, p.messages
    out = capsys.readouterr().out
    assert 'checkpoint not published; receivers keep the previous checkpoint' in out, p.messages
    assert capped.sizes, 'the failing run must still assemble a candidate manifest'
    assert sorted(store.manifests.glob('*.json')) == manifests_before
    assert ready.read_bytes() == before
