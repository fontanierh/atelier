"""Compatibility-only staging into warm receivers; no Unreal or Blender launched."""
from dataclasses import replace
import json

import pytest

from atelier import build_checkpoints, checkpoint_candidates as candidates, checkpoint_store as cp, paths
from atelier.build_cache import atomic_json
from test_checkpoints import fixture


@pytest.fixture
def donor(fixture, monkeypatch):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
    key = fixture.store.save(dict(fixture.store.load(key), source_revision='a' * 40))
    monkeypatch.setattr(candidates, 'Store', lambda _: fixture.store)
    def guard(ctx, operation, request_id):
        assert operation == 'stage-candidates'
        return candidates.stage_worker(ctx, request_id)
    monkeypatch.setattr(build_checkpoints, '_guard', guard)
    return key, fixture.store.load(key)


def test_stage_into_warm_receiver_preserves_content_and_stamps(fixture, donor):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver', changed=True)
    ctx.stamps.mkdir(parents=True)
    stamp = ctx.stamps / 'keep.json'; stamp.write_text('existing completed scope')
    existing = ctx.out / 'keep.bin'; existing.write_bytes(b'keep')
    manifest = candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    bundle = candidates.load(ctx, 'tree')
    assert bundle['source_revision'] == 'a' * 40 and bundle['provenance'] == 'compatibility-only'
    assert bundle['checkpoint'] == key and manifest.is_file()
    copied = bundle.member_path('generated/tree/asset.bin')
    assert copied.read_bytes() == b'tree'
    assert existing.read_bytes() == b'keep' and stamp.read_text() == 'existing completed scope'
    assert not (ctx.out / 'tree/asset.bin').exists()  # No live product installation.
    assert {p.name for p in ctx.stamps.iterdir()} == {'keep.json'}
    copied.write_bytes(b'edited receiver staging')
    assert fixture.store.blob(bundle['files']['generated/tree/asset.bin']['sha256']).read_bytes() == b'tree'
    assert candidates.load(ctx, 'tree') is None
    assert candidates.member_path(ctx, 'tree', 'generated/tree/asset.bin', bundle=bundle) is None


def test_stale_engine_pointer_is_a_miss(fixture, donor, monkeypatch):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    monkeypatch.setattr(candidates, 'context', lambda ctx: dict(engine='different'))
    assert candidates.load(ctx, 'tree') is None


@pytest.mark.parametrize('bad', ['missing-source', 'missing-task', 'linked-member'])
def test_missing_historical_proof_or_unsupported_member_cannot_stage(fixture, donor, bad):
    key, value = donor
    if bad == 'missing-source':
        value.pop('source_revision')
    elif bad == 'missing-task':
        value['stamps'].pop('tree')
    else:
        value['files']['generated/tree/link'] = dict(kind='link', target='member:generated/tree/asset.bin', mode=0o777, mtime_ns=1)
    key = fixture.store.save(value)
    ctx, _ = fixture.checkout('receiver')
    with pytest.raises(cp.CheckpointError):
        candidates.stage(ctx, key, 'tree', ['generated/tree/link' if bad == 'linked-member' else 'generated/tree/asset.bin'])
    assert not (candidates.root(ctx) / 'tree.json').exists()


def test_corruption_after_guard_prevents_completion_publication(fixture, donor, monkeypatch):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    def guard(ctx, operation, request_id):
        result = candidates.stage_worker(ctx, request_id)
        folder = candidates.root(ctx) / result['folder']
        (folder / result['value']['files']['generated/tree/asset.bin']['path']).write_bytes(b'corrupt')
        return result
    monkeypatch.setattr(build_checkpoints, '_guard', guard)
    with pytest.raises(cp.CheckpointError, match='changed'):
        candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    assert not (candidates.root(ctx) / 'tree.json').exists()


def test_pointer_cannot_escape_staging(fixture, donor):
    ctx, _ = fixture.checkout('receiver')
    atomic_json(candidates.root(ctx) / 'tree.json', dict(schema=1, manifest='../../foreign.json'))
    assert candidates.load(ctx, 'tree') is None


def test_staging_refuses_existing_leaf_symlink_without_touching_target(fixture, donor, monkeypatch):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    victim = ctx.out / 'keep'; victim.parent.mkdir(parents=True); victim.write_text('preserve')
    def guard(ctx, operation, request_id):
        target = candidates.root(ctx) / key / 'tree' / request_id / 'files/generated/tree/asset.bin'
        target.parent.mkdir(parents=True)
        target.symlink_to(victim)
        return candidates.stage_worker(ctx, request_id)
    monkeypatch.setattr(build_checkpoints, '_guard', guard)
    with pytest.raises(cp.CheckpointError, match='already exists'):
        candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    assert victim.read_text() == 'preserve'
    assert not (candidates.root(ctx) / 'tree.json').exists()


def test_pointer_with_linked_staging_root_is_a_miss(fixture, donor):
    ctx, _ = fixture.checkout('receiver')
    elsewhere = ctx.out / 'elsewhere'; elsewhere.mkdir(parents=True)
    root = candidates.root(ctx); root.parent.mkdir(parents=True)
    root.symlink_to(elsewhere, target_is_directory=True)
    assert candidates.load(ctx, 'tree') is None


def test_normal_preparation_discovers_declared_scope_without_manual_key(fixture, donor):
    key, _ = donor
    ctx, steps = fixture.checkout('receiver', changed=True)
    step = replace(steps[0], candidate_scope=candidates.CandidateScope(directories=(steps[0].outputs[0].parent,)))
    result = candidates.prepare(ctx, step, echo=lambda _: None)
    assert result.is_file()
    assert candidates.load(ctx, 'tree')['checkpoint'] == key
    assert candidates.prepare(ctx, step, echo=lambda _: None) is None


def test_bundle_accessor_hashes_only_requested_member(fixture, donor, monkeypatch):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin', 'generated/house/asset.bin'])
    bundle = candidates.load(ctx, 'tree')
    original = candidates.build_products.file_digest
    seen = []
    def digest(path):
        seen.append(path)
        return original(path)
    monkeypatch.setattr(candidates.build_products, 'file_digest', digest)
    assert candidates.member_path(ctx, 'tree', 'generated/tree/asset.bin', bundle=bundle).read_bytes() == b'tree'
    assert len(seen) == 1 and seen[0].name == 'asset.bin'


def test_corrupted_completion_cannot_invent_source_revision(fixture, donor):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    path = candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    value = cp.read_json(path); value['source_revision'] = 'b' * 40; atomic_json(path, value)
    assert candidates.load(ctx, 'tree') is None


def test_remote_discovery_skips_incompatible_newer_checkpoint(fixture, donor, monkeypatch):
    key, saved = donor
    incompatible = dict(saved, source_revision='')
    bad_key = cp.identity(incompatible)
    ctx, steps = fixture.checkout('receiver')
    step = replace(steps[0], candidate_scope=candidates.CandidateScope(files=(steps[0].outputs[0],)))
    monkeypatch.setattr(fixture.store, 'latest', lambda: [])
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: dict(repository='owner/private'))
    from atelier import checkpoint_github
    fetched = []
    class Remote:
        def __init__(self, *_, **kwargs): pass
        def candidates(self): return [bad_key, key]
        def descriptor(self, item, temporary):
            value = incompatible if item == bad_key else saved
            return dict(key=item, checkpoint=value, blobs={e['sha256']: [] for e in value['files'].values() if e['kind']=='file'})
        def fetch(self, item, transfer, store, *, save):
            assert not save and list(transfer['checkpoint']['files']) == ['generated/tree/asset.bin']
            fetched.append(item)
    monkeypatch.setattr(checkpoint_github, 'Remote', Remote)
    assert candidates.prepare(ctx, step, echo=lambda _: None).is_file()
    assert fetched == [key]
