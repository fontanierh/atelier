"""Real checkpoint files and receiving recipes; no Unreal, Blender, cook or native build."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, build_snapshot, checkpoint_actions, checkpoint_store as cp, paths
from atelier.build_cache import atomic_json


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', tmp_path / 'plugins')
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    def checkout(name, *, changed=False, project=False):
        repo = (tmp_path / name).resolve()
        repo.mkdir()
        (repo / 'uv.lock').write_text('fixture lock')
        monkeypatch.setattr(paths, 'REPO', repo)
        monkeypatch.setattr(paths, 'build_root', lambda: paths.REPO / 'build')
        out = repo / 'build/fixture'
        ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps',
                              uproject=None, unreal_root=None)
        steps = []
        for asset in ('tree', 'combat', 'house'):
            source = repo / (asset + '.txt')
            source.write_text('changed combat' if changed and asset == 'combat' else asset)
            destination = out / asset / 'asset.bin'
            steps.append(build.Step(asset, [build.Python(source, (destination,))], inputs=[source],
                                    outputs=[destination], products=[build.Product(asset, (destination.parent,))]))
        return ctx, steps
    def produce(ctx, steps):
        ctx.stamps.mkdir(parents=True)
        done = {}
        for step in steps:
            step.outputs[0].parent.mkdir(parents=True)
            step.outputs[0].write_bytes(step.name.encode())
            value = build.fingerprint(step, done)
            products = build.build_products.records(step)
            stamp = dict(fingerprint=value, products=products, seconds=3., time=1.)
            stamp['checkpoint_key'] = checkpoint_actions.certificate_key(ctx, step, value)
            declarations, files = checkpoint_actions.snapshot(ctx, step, fixture_store, save_blobs=False)
            stamp['checkpoint_inventory'] = checkpoint_actions.inventory_identity(declarations, files)
            atomic_json(ctx.stamps / (step.name + '.json'), stamp)
            done[step.name] = value
            build.build_products.feed_results(done, products)
    fixture_store = cp.Store('fixture', tmp_path / 'store')
    return SimpleNamespace(checkout=checkout, produce=produce, store=fixture_store)


def snapshot(fixture):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
    return ctx, steps, key


def publish_receiver(ctx, steps, store, key, stamps):
    build_checkpoints._publish_restoration(ctx, steps, store, key, dict(key=key, stamps=stamps))


def test_fresh_dirty_checkout_reuses_unaffected_tasks_without_head_equality(fixture):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver', changed=True)
    before = (paths.REPO / 'combat.txt').read_bytes()
    stamps = cp.restore(ctx, steps, fixture.store, key, echo=lambda _: None)
    assert set(stamps) == {'tree', 'house'}
    assert not list(ctx.stamps.glob('*.json'))  # The worker cannot publish before guard close.
    with pytest.raises(SystemExit, match='checkpoint restoration is incomplete'):
        build_snapshot.require_complete(ctx.out, game='fixture')
    publish_receiver(ctx, steps, fixture.store, key, stamps)
    assert {p.stem for p in ctx.stamps.glob('*.json')} == {'tree', 'house'}
    assert (paths.REPO / 'combat.txt').read_bytes() == before
    assert steps[1].outputs[0].read_bytes() == b'combat'  # Seed only; no current certificate.
    build_snapshot.require_complete(ctx.out, game='fixture')


def test_old_workspace_preserves_import_history_for_content_boundary_migration(fixture, monkeypatch):
    from dataclasses import replace
    donor, old_steps = fixture.checkout('old-workspace')
    old_steps[0] = replace(old_steps[0], needs=['combat'])
    fixture.produce(donor, [old_steps[1], old_steps[0], old_steps[2]])
    key = cp.capture(donor, old_steps, fixture.store, echo=lambda _: None)
    ctx, steps = fixture.checkout('new-recipe')
    steps[0] = replace(steps[0], needs=['combat.import'], checkpoint_previous_needs=('combat',))
    digest_output = ctx.out / 'digests/combat.json'
    digest = build.Step('combat.import', [build.Call('digest', lambda *_: None)], needs=['combat'],
                        outputs=[digest_output], cutoff=True)
    stamps = cp.restore(ctx, [*steps, digest], fixture.store, key, echo=lambda _: None)
    assert 'tree' not in stamps
    publish_receiver(ctx, [*steps, digest], fixture.store, key, stamps)
    # The cheap new cutoff runs first; the old importer metadata is absent from current stamps.
    digest_output.parent.mkdir(parents=True); digest_output.write_bytes(b'normalized combat')
    done = {'combat': stamps['combat']['fingerprint'], 'combat.import': 'outputs:normalized-combat'}
    current, state = build.fingerprint_state(steps[0], done)
    monkeypatch.setattr(checkpoint_actions, 'Store', lambda _: fixture.store)
    migrated = checkpoint_actions.migrate_boundary(ctx, steps[0], current, state, {}, done)
    assert migrated['fingerprint'] == current
    assert migrated['checkpoint_migration_result'] == fixture.store.load(key)['stamps']['tree']['fingerprint']
    assert steps[0].outputs[0].read_bytes() == b'tree'


@pytest.mark.parametrize('change', ['mode', 'link'])
def test_post_guard_workspace_rejects_changed_mode_or_link(fixture, change):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    link = steps[0].outputs[0].parent / 'asset-link'
    link.symlink_to('asset.bin')
    key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
    receiver, receiving = fixture.checkout('receiver')
    stamps = cp.restore(receiver, receiving, fixture.store, key, echo=lambda _: None)
    output = receiving[0].outputs[0]
    if change == 'mode':
        output.chmod(0o700)
    else:
        link = output.parent / 'asset-link'; link.unlink(); link.symlink_to('../combat/asset.bin')
    with pytest.raises(cp.CheckpointError, match='changed'):
        publish_receiver(receiver, receiving, fixture.store, key, stamps)
    assert (receiver.out / cp.JOURNAL).exists()
    assert not list(receiver.stamps.glob('*.json'))


def test_changed_producer_never_certifies_dependent_but_preserves_independent_task(fixture):
    ctx, steps = fixture.checkout('donor')
    steps[1].needs = ['tree']
    fixture.produce(ctx, steps)
    key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
    receiver, current = fixture.checkout('receiver')
    current[1].needs = ['tree']
    (paths.REPO / 'tree.txt').write_text('different tree')
    stamps = cp.restore(receiver, current, fixture.store, key)
    assert set(stamps) == {'house'}


def test_checkpoint_never_overwrites_existing_generated_work(fixture):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    ctx.out.mkdir(parents=True)
    owned = ctx.out / 'new-work.txt'
    owned.write_text('keep me')
    with pytest.raises(cp.CheckpointError, match='not empty'):
        cp.restore(ctx, steps, fixture.store, key)
    assert owned.read_text() == 'keep me' and not (ctx.out / cp.JOURNAL).exists()


def test_corrupt_blob_refuses_before_mutation(fixture):
    _, _, key = snapshot(fixture)
    saved = fixture.store.load(key)
    digest = next(iter(saved['files'].values()))['sha256']
    fixture.store.blob(digest).write_bytes(b'corrupt')
    ctx, steps = fixture.checkout('receiver')
    with pytest.raises(cp.CheckpointError, match='corrupt'):
        cp.restore(ctx, steps, fixture.store, key)
    assert not ctx.out.exists()


def test_interruption_resumes_same_checkpoint_and_retains_launch_barrier(fixture, monkeypatch):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    original, copies = cp.copy_file, []
    def interrupted(source, destination):
        copies.append(source)
        if len(copies) == 2:
            raise OSError('interrupted')
        original(source, destination)
    monkeypatch.setattr(cp, 'copy_file', interrupted)
    with pytest.raises(OSError, match='interrupted'):
        cp.restore(ctx, steps, fixture.store, key)
    assert (ctx.out / cp.JOURNAL).exists() and not list(ctx.stamps.glob('*.json'))
    monkeypatch.setattr(cp, 'copy_file', original)
    stamps = cp.restore(ctx, steps, fixture.store, key)
    publish_receiver(ctx, steps, fixture.store, key, stamps)
    assert set(stamps) == {'tree', 'combat', 'house'}


def test_receiver_changes_after_worker_refuse_publication(fixture):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    stamps = cp.restore(ctx, steps, fixture.store, key)
    (paths.REPO / 'tree.txt').write_text('steering edit')
    with pytest.raises(cp.CheckpointError, match='receiver changed'):
        publish_receiver(ctx, steps, fixture.store, key, stamps)
    assert (ctx.out / cp.JOURNAL).exists() and not list(ctx.stamps.glob('*.json'))


def test_local_outputs_are_independent_of_cache(fixture):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    stamps = cp.restore(ctx, steps, fixture.store, key)
    publish_receiver(ctx, steps, fixture.store, key, stamps)
    for blob in fixture.store.blobs.iterdir():
        blob.unlink()
    assert steps[0].outputs[0].read_bytes() == b'tree'


@pytest.mark.parametrize('member', ['generated/../source', '/absolute', 'generated/.env',
                                    'generated/part/../../source', 'generated/a\\b'])
def test_manifest_refuses_unsafe_paths(fixture, member):
    _, _, key = snapshot(fixture)
    value = fixture.store.load(key)
    entry = next(iter(value['files'].values()))
    value['files'] = {member: entry}
    with pytest.raises(cp.CheckpointError):
        cp.validate(value, 'fixture')


def test_manifest_refuses_case_aliases_and_file_ancestors(fixture):
    _, _, key = snapshot(fixture)
    value = fixture.store.load(key)
    entry = next(iter(value['files'].values()))
    for names in [('generated/A', 'generated/a'), ('generated/a', 'generated/a/b')]:
        value['files'] = dict.fromkeys(names, entry)
        with pytest.raises(cp.CheckpointError):
            cp.validate(value, 'fixture')


def test_linked_destination_ancestor_refuses_before_source_mutation(fixture):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    source = paths.REPO / 'source'
    source.mkdir()
    (paths.REPO / 'build').symlink_to(source, target_is_directory=True)
    with pytest.raises(cp.CheckpointError, match='linked ancestor'):
        cp.restore(ctx, steps, fixture.store, key)
    assert not list(source.iterdir())


def test_touched_or_stale_tasks_do_not_become_checkpoint_certificates(fixture):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    stamp = ctx.stamps / 'tree.json'
    value = cp.read_json(stamp); value['touched'] = True; atomic_json(stamp, value)
    (paths.REPO / 'combat.txt').write_text('changed')
    key = cp.capture(ctx, steps, fixture.store)
    assert set(fixture.store.load(key)['stamps']) == {'house'}


def test_artifacts_added_during_capture_refuse_publication(fixture, monkeypatch):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    original = fixture.store.put
    def changed(path, digest):
        original(path, digest)
        (ctx.out / 'appeared.bin').write_bytes(b'new')
    monkeypatch.setattr(fixture.store, 'put', changed)
    with pytest.raises(cp.CheckpointError, match='changed during'):
        cp.capture(ctx, steps, fixture.store)
    assert not list(fixture.store.manifests.glob('*.json'))


def test_large_or_unknown_cold_jobs_require_a_recorded_reason(tmp_path):
    ctx = SimpleNamespace(checkpoint_settings=dict(rebuild_budget_seconds=60), logs=tmp_path,
                          rebuild_reason=None, uproject=None)
    step = build.Step('native.import', [build.UnrealScript(Path('import.py'), 'done')], heavy=True,
                      checkpoint_outputs=(tmp_path / 'assets',))
    with pytest.raises(cp.CheckpointError, match='unknown cold'):
        build_checkpoints.protect(ctx, step)
    with pytest.raises(cp.CheckpointError, match='120s'):
        build_checkpoints.protect(ctx, step, estimate=120)
    ctx.rebuild_reason = 'first build after engine upgrade'
    build_checkpoints.protect(ctx, step, estimate=120)
    assert json.loads((tmp_path / 'rebuild-decisions.jsonl').read_text())['reason'] == ctx.rebuild_reason


def test_guard_failure_cannot_publish_receipt_or_certificates(fixture, monkeypatch):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    from atelier.harness.safety import guarded
    calls = []
    monkeypatch.setattr(guarded, 'run', lambda *a, **kw: calls.append((a, kw)) or 7)
    with pytest.raises(cp.CheckpointError, match='exit 7'):
        build_checkpoints._guard(ctx, 'restore', key)
    assert calls[0][1]['aggregate_tree'] is True
    assert calls[0][1]['timeout'] == 3600
    assert not ctx.stamps.exists()


def test_checkpoint_barrier_cannot_hide_behind_output_override(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    default = tmp_path / 'build/fixture'
    default.mkdir(parents=True)
    atomic_json(default / cp.JOURNAL, dict(schema=1, key='a' * 64, game='fixture'))
    with pytest.raises(SystemExit, match='checkpoint restoration is incomplete'):
        build_snapshot.require_complete(tmp_path / 'other/fixture', game='fixture')


def test_retired_manual_reuse_cannot_start_a_full_copy(monkeypatch):
    from atelier import cli
    with pytest.raises(SystemExit):
        cli.main(['reuse', 'fixture', '--from', 'donor'])


def test_default_checkpoint_cooking_uses_dependency_tracking(tmp_path):
    from atelier.build_cook import apply, CookMode
    game = tmp_path / 'game'; game.mkdir()
    (game / 'game.toml').write_text('[checkpoints]\nrebuild_budget_seconds=600\n')
    ctx = SimpleNamespace(game='fixture', game_dir=game, cook_mode=CookMode.DEFAULT)
    step = build.Step('cook', [build.UnrealPackage('Fixture', tmp_path / 'archive')])
    apply(ctx, [step])
    assert step.commands[0].cook_mode is CookMode.INCREMENTAL


@pytest.mark.parametrize('operation', ['restore', 'restore-action', 'stage-candidates'])
def test_checkpoint_transfer_reaches_real_guard_boundary_with_valid_invocation(tmp_path, monkeypatch, operation):
    from atelier.harness.safety import guarded
    class BeforeNativeLaunch(Exception):
        pass
    calls = []
    def boundary(*args, **kwargs):
        calls.append(args[0])
        raise BeforeNativeLaunch
    # Exercise the production guard's UUID validation, then stop before its
    # actual admission/child launcher. No native command or fake process runs.
    monkeypatch.setattr(guarded, '_run', boundary)
    ctx = SimpleNamespace(game='fixture', logs=tmp_path)
    with pytest.raises(BeforeNativeLaunch):
        build_checkpoints._guard(ctx, operation, 'a' * 64)
    assert len(calls) == 1
