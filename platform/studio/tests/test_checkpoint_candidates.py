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


@pytest.mark.parametrize('failure', ['incompatible', 'descriptor', 'download'])
def test_remote_discovery_skips_unusable_newer_checkpoint(fixture, donor, monkeypatch, failure):
    key, saved = donor
    incompatible = dict(saved, source_revision='' if failure == 'incompatible' else 'b' * 40)
    bad_key = cp.identity(incompatible)
    ctx, steps = fixture.checkout('receiver')
    step = replace(steps[0], candidate_scope=candidates.CandidateScope(files=(steps[0].outputs[0],)))
    monkeypatch.setattr(candidates, 'local_keys', lambda _: [])
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: dict(repository='owner/private'))
    from atelier import checkpoint_github
    fetched = []
    class Remote:
        def __init__(self, *_, **kwargs): pass
        def candidates(self): return [bad_key, key]
        def descriptor(self, item, temporary):
            if item == bad_key and failure == 'descriptor':
                raise cp.CheckpointError('Corrupt remote descriptor')
            value = incompatible if item == bad_key else saved
            return dict(key=item, checkpoint=value, blobs={e['sha256']: [] for e in value['files'].values() if e['kind']=='file'})
        def fetch(self, item, transfer, store, *, save):
            if item == bad_key and failure == 'download':
                raise cp.CheckpointError('Missing or corrupt pack')
            assert not save and list(transfer['checkpoint']['files']) == ['generated/tree/asset.bin']
            fetched.append(item)
    monkeypatch.setattr(checkpoint_github, 'Remote', Remote)
    assert candidates.prepare(ctx, step, echo=lambda _: None).is_file()
    assert fetched == [key]


def test_linked_request_directory_cannot_write_receiver_products(fixture, donor):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    protected = ctx.out / 'Content'; protected.mkdir(parents=True)
    directory = ctx.out / '.state/candidate-requests'; directory.parent.mkdir()
    directory.symlink_to(protected, target_is_directory=True)
    with pytest.raises(cp.CheckpointError, match='linked ancestor'):
        candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    assert list(protected.iterdir()) == []


def test_corrupt_local_donor_does_not_hide_valid_older_checkpoint(fixture, donor):
    key, _ = donor
    (fixture.store.manifests / ('f' * 64 + '.json')).write_text('{broken')
    ctx, steps = fixture.checkout('receiver')
    step = replace(steps[0], candidate_scope=candidates.CandidateScope(files=(steps[0].outputs[0],)))
    assert candidates.prepare(ctx, step, echo=lambda _: None).is_file()
    assert candidates.load(ctx, 'tree')['checkpoint'] == key


def test_normal_build_stages_candidates_before_changed_task_executes(fixture, donor, monkeypatch):
    from types import SimpleNamespace
    from atelier import build
    key, _ = donor
    ctx, steps = fixture.checkout('receiver', changed=True)
    ctx.cook_mode = build.CookMode.DEFAULT
    step = replace(steps[1], candidate_scope=candidates.CandidateScope(directories=(steps[1].outputs[0].parent,)))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    executions = []
    def run(ctx, step, command, log, *args, **kwargs):
        bundle = candidates.load(ctx, step.name)
        assert bundle['checkpoint'] == key
        assert bundle.member_path('generated/combat/asset.bin').read_bytes() == b'combat'
        assert not step.outputs[0].exists()  # Staging did not install the donor's live product.
        step.outputs[0].parent.mkdir(parents=True)
        step.outputs[0].write_text('new validated receiver result')
        executions.append(step.name)
    monkeypatch.setattr(build, 'run_command', run)
    assert build.build('fixture') == 0
    assert executions == ['combat']
    assert cp.read_json(ctx.stamps / 'combat.json')['fingerprint'] != fixture.store.load(key)['stamps']['combat']['fingerprint']


@pytest.mark.parametrize('bad', [None, [], 'invalid', 42])
def test_malformed_json_pointer_or_completion_is_a_normal_miss(fixture, donor, bad):
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    manifest = candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    pointer = candidates.root(ctx) / 'tree.json'
    original_pointer = cp.read_json(pointer)
    atomic_json(pointer, bad)
    assert candidates.load(ctx, 'tree') is None
    atomic_json(pointer, original_pointer)
    atomic_json(manifest, bad)
    assert candidates.load(ctx, 'tree') is None


def test_null_file_entry_and_foreign_cached_bundle_are_misses(fixture, donor):
    from types import SimpleNamespace
    key, _ = donor
    ctx, _ = fixture.checkout('receiver')
    manifest = candidates.stage(ctx, key, 'tree', ['generated/tree/asset.bin'])
    bundle = candidates.load(ctx, 'tree')
    assert candidates.member_path(ctx, 'combat', 'generated/tree/asset.bin', bundle=bundle) is None
    foreign = SimpleNamespace(game='another', out=ctx.out)
    assert candidates.member_path(foreign, 'tree', 'generated/tree/asset.bin', bundle=bundle) is None
    other, _ = fixture.checkout('another-receiver')
    assert candidates.member_path(other, 'tree', 'generated/tree/asset.bin', bundle=bundle) is None
    value = cp.read_json(manifest); value['files']['generated/tree/asset.bin'] = None
    atomic_json(manifest, value)
    assert candidates.load(ctx, 'tree') is None


def test_metadata_only_remote_subset_is_rediscovered_offline(fixture, donor, monkeypatch):
    key, saved = donor
    atomic_json(fixture.store.directory / 'candidate-sources' / (key + '.json'), saved)
    (fixture.store.manifests / (key + '.json')).unlink()
    ctx, steps = fixture.checkout('receiver')
    step = replace(steps[0], candidate_scope=candidates.CandidateScope(files=(steps[0].outputs[0],)))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: pytest.fail('already-local subset attempted network discovery'))
    assert candidates.prepare(ctx, step, echo=lambda _: None).is_file()
    assert candidates.load(ctx, 'tree')['checkpoint'] == key
    assert not (fixture.store.manifests / (key + '.json')).exists()


def test_candidate_capture_does_not_write_producer_or_publish_task_proof(fixture, tmp_path):
    import hashlib
    ctx, steps = fixture.checkout('read-only-producer')
    fixture.produce(ctx, steps)
    def observed():
        return {p: (p.stat().st_mtime_ns, p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in paths.REPO.rglob('*') if p.is_file()}
    before = observed()
    key = cp.capture(ctx, steps, fixture.store, candidate_only=True,
                     scratch=tmp_path / 'controller/hashes.sqlite3', echo=lambda _: None)
    assert observed() == before
    assert not (ctx.out / '.state').exists()
    assert not list(fixture.store.manifests.glob('*.json'))
    assert not list((fixture.store.directory / 'actions').glob('*.json'))
    saved = candidates.original(fixture.store, key)
    assert saved['candidate_only'] and saved['stamps'] == {} and saved['actions'] == {}
    assert set(saved['incremental_stamps']) == {'tree', 'house', 'combat'}


def test_candidate_capture_requires_external_scratch(fixture):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    with pytest.raises(cp.CheckpointError, match='outside the producer'):
        cp.capture(ctx, steps, fixture.store, candidate_only=True, scratch=ctx.out / '.state/hashes.sqlite3')
