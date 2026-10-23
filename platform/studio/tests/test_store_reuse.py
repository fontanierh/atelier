"""Shared local store reuse: checkouts share only immutable store entries, by exact fingerprint."""
import json
import os
from pathlib import Path
import time

import pytest

from atelier import build, build_checkpoints, checkpoint_actions as actions, checkpoint_store as cp, store_retention
from atelier.build_cache import atomic_json
from test_checkpoints import fixture, hydrate_in_process, snapshot  # noqa: F401


def publish_all(ctx, steps, store):
    done, keys = {}, {}
    for step in steps:
        stamp = cp.read_json(ctx.stamps / (step.name + '.json'))
        keys[step.name] = actions.publish(ctx, step, stamp['fingerprint'], stamp, store=store, done=done, produced=True)
        done[step.name] = build.result(step, stamp['fingerprint'], stamp)
    return keys


def recipe_free_guard(monkeypatch, store):
    """Per-task action restores run in the build process; other transfers keep the guard."""
    real = build_checkpoints._guard
    def guard(ctx, operation, key=None):
        assert operation != 'restore-action', 'action restores never spawn a guarded child'
        return real(ctx, operation, key)
    monkeypatch.setattr(build_checkpoints, '_guard', guard)


def test_dirty_checkout_at_another_revision_shares_only_through_the_store(fixture, monkeypatch):
    donor, steps = fixture.checkout('donor', changed=True)  # Another revision with an uncommitted edit.
    fixture.produce(donor, steps)
    keys = publish_all(donor, steps, fixture.store)
    ctx, receiving = fixture.checkout('receiver')
    monkeypatch.setattr(actions, 'Store', lambda _: fixture.store)
    cache = actions.Actions(ctx, {}, echo=lambda _: None)
    recipe_free_guard(monkeypatch, fixture.store)
    tree, combat = receiving[0], receiving[1]
    hit = cache.get(tree, build.fingerprint(tree, {}))
    assert hit is not None and hit['key'] == keys['tree']
    assert cache.restore(tree, build.fingerprint(tree, {}), hit, {})
    assert (ctx.out / 'tree/asset.bin').read_bytes() == b'tree'
    assert cache.get(combat, build.fingerprint(combat, {})) is None  # Different inputs never match.
    assert (fixture.store.directory / 'used' / keys['tree']).exists()


def test_corrupt_blob_disables_the_entry_and_restores_nothing(fixture, monkeypatch):
    donor, steps = fixture.checkout('donor')
    fixture.produce(donor, steps)
    keys = publish_all(donor, steps, fixture.store)
    value = actions.load(fixture.store, keys['tree'])
    fixture.store.blob(next(iter(value['files'].values()))['sha256']).write_bytes(b'x')
    ctx, receiving = fixture.checkout('receiver')
    request = ctx.out / '.state/action-requests' / (keys['tree'] + '.json')
    atomic_json(request, dict(task='tree', labels=['generated/tree']))
    with pytest.raises(cp.CheckpointError, match='disabled'):
        actions.restore_worker(ctx, None, fixture.store, keys['tree'], labels=['generated/tree'])
    assert actions.entry_path(fixture.store, keys['tree']).with_suffix('.conflict').exists()
    assert not (ctx.out / 'tree/asset.bin').exists() and not (ctx.out / cp.JOURNAL).exists()


def test_partial_or_changed_outputs_are_never_published(fixture):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    step = steps[0]
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    step.outputs[0].write_bytes(b'partial')
    with pytest.raises(cp.CheckpointError, match='products changed'):
        actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    step.outputs[0].unlink()
    with pytest.raises((cp.CheckpointError, OSError, ValueError)):
        actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    assert not list((fixture.store.directory / 'actions').glob('*.json'))


def test_interrupted_hydration_resumes(fixture, monkeypatch):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    (ctx.out / 'tree').mkdir(parents=True)
    (ctx.out / 'tree/asset.bin').write_bytes(b'stale')
    plan, _, _ = build_checkpoints.hydration_plan(ctx, steps, fixture.store)
    atomic_json(ctx.out / cp.HYDRATION_REQUEST, dict(key=key, units=plan['units'], stamps=plan['stamps'], outputs=plan['outputs']))
    original, copies = cp.copy_file, []
    def interrupted(source, destination):
        copies.append(source)
        if len(copies) == 2:
            raise OSError('interrupted')
        original(source, destination)
    monkeypatch.setattr(cp, 'copy_file', interrupted)
    with pytest.raises(OSError):
        cp.hydrate_files(ctx, fixture.store, key, echo=lambda _: None)
    pending = cp.read_json(ctx.out / cp.JOURNAL)
    monkeypatch.setattr(cp, 'copy_file', original)
    hydrate_in_process(monkeypatch, fixture)
    assert build_checkpoints.hydrate(ctx, steps, fixture.store, echo=lambda _: None, resume=pending)['key'] == key
    assert (ctx.out / 'combat/asset.bin').read_bytes() == b'combat' and (ctx.out / 'house/asset.bin').read_bytes() == b'house'
    assert (ctx.out / 'tree/asset.bin').read_bytes() == b'stale' and not (ctx.out / cp.JOURNAL).exists()


def test_scan_of_a_large_checkpoint_is_fast(fixture, monkeypatch):
    ctx, steps = fixture.checkout('donor')
    original = Path.mkdir
    monkeypatch.setattr(Path, 'mkdir', lambda self, *a, **k: original(self, *a, **{**k, 'exist_ok': True}))
    many = ctx.out / 'tree/many'
    many.mkdir(parents=True)
    for i in range(5000):
        (many / f'{i}.bin').write_bytes(b'%d' % (i % 7))
    fixture.produce(ctx, steps)
    monkeypatch.setattr(Path, 'mkdir', original)
    key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
    receiver, receiving = fixture.checkout('receiver')
    build_checkpoints.hydration_plan(receiver, receiving, fixture.store)  # Builds the summary once.
    started = time.monotonic()
    plan, _, _ = build_checkpoints.hydration_plan(receiver, receiving, fixture.store)
    assert plan['key'] == key and plan['missing'] == 5003
    assert time.monotonic() - started < 1.0


def test_retention_evicts_least_recently_used_unpinned_entries(fixture, monkeypatch):
    donor, steps = fixture.checkout('donor')
    fixture.produce(donor, steps)
    keys = publish_all(donor, steps, fixture.store)
    old = time.time() - 7200
    for path in (fixture.store.directory / 'actions').glob('*.json'):
        os.utime(path, (old, old))
    for path in fixture.store.blobs.iterdir():
        os.utime(path, (old, old))
    store_retention.touch(fixture.store, keys['house'])
    result = store_retention.collect(fixture.store, budget=1, echo=lambda _: None)
    assert result['removed_entries'] == 2 and result['removed_blobs'] == 2  # The recently used entry stays.
    assert [p.stem for p in (fixture.store.directory / 'actions').glob('*.json')] == [keys['house']]
    assert actions.load(fixture.store, keys['house']) is not None
    assert store_retention.collect(fixture.store, budget=10**12, echo=lambda _: None)['removed_entries'] == 0


def test_retention_dry_run_changes_nothing_and_keeps_workspace_staging_blobs(fixture, monkeypatch):
    donor, steps = fixture.checkout('donor')
    fixture.produce(donor, steps)
    keys = publish_all(donor, steps, fixture.store)
    old = time.time() - 7200
    for path in [*(fixture.store.directory / 'actions').glob('*.json'), *fixture.store.blobs.iterdir()]:
        os.utime(path, (old, old))
    before = sorted(p.name for p in fixture.store.directory.rglob('*') if p.is_file())
    plan = store_retention.collect(fixture.store, budget=1, dry_run=True, echo=lambda _: None)
    assert plan['dry_run'] and plan['removed_entries'] == 3 and len(plan['entries']) == 3
    assert sorted(p.name for p in fixture.store.directory.rglob('*') if p.is_file()) == before
    # A build's workspace staging pointer is a CAS root: its blobs survive eviction of entries.
    house = actions.load(fixture.store, keys['house'])
    pointer = fixture.store.directory / 'workspaces/producer.json'
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps(dict(key='0' * 64, workspace=dict(files=house['files']))))
    result = store_retention.collect(fixture.store, budget=1, echo=lambda _: None)
    assert result['removed_entries'] == 3
    for entry in house['files'].values():
        if entry['kind'] == 'file':
            assert fixture.store.blob(entry['sha256']).is_file()


def test_budget_is_the_smaller_of_cap_and_free_disk_share(fixture, monkeypatch):
    import shutil
    from collections import namedtuple
    usage = namedtuple('usage', 'total used free')
    monkeypatch.setattr(shutil, 'disk_usage', lambda _: usage(0, 0, 100 * 2**30))
    assert store_retention.budget_bytes(fixture.store, total=20 * 2**30) == 60 * 2**30  # Half of 100 + 20 GiB.
    settings = fixture.store.directory.parent.parent / 'settings.json'
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(dict(local_budget_gib=30, local_keep_manifests=2)))
    assert store_retention.budget_bytes(fixture.store, total=20 * 2**30) == 30 * 2**30
    assert store_retention.settings(fixture.store)['keep'] == 2
