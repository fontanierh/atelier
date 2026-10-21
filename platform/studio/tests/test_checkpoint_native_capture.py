"""Ordinary successful owners retain immutable hints; no native process is launched."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, checkpoint_candidates, checkpoint_native_capture as capture
from atelier import checkpoint_store, mesh_reuse, native_protocol, paths


@pytest.fixture
def owner(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'; repo.mkdir()
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', tmp_path / 'plugins')
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture',
                          uproject=repo / 'game/Game.uproject', unreal_root=None,
                          cook_mode=build.CookMode.DEFAULT)
    ctx.logs, ctx.stamps = ctx.out / 'logs', ctx.out / 'stamps'
    ctx.out.mkdir(parents=True)
    content = ctx.uproject.parent / 'Content'
    source = ctx.out / 'source.glb'; source.write_bytes(b'source')
    report = ctx.out / 'report.json'; report.write_text('report')
    for package in ('Mesh', 'Hull'):
        path = content / ('Region/' + package + '.uasset')
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(package.encode())
    (content / 'Region/Mesh.ubulk').write_bytes(b'bulk')
    current = native_protocol.context(ctx)
    store = checkpoint_store.Store(ctx.game, tmp_path / 'store')
    monkeypatch.setattr(checkpoint_store, 'Store', lambda *_: store)
    monkeypatch.setattr(checkpoint_candidates, 'Store', lambda *_: store)
    monkeypatch.setattr(capture, '_revision', lambda: 'a' * 40)
    scope = checkpoint_candidates.CandidateScope(files=(report,), directories=(content / 'Region',))
    step = build.Step('unreal.region', [build.Call('owner', lambda *_: None)],
                      inputs=[source], outputs=[report], candidate_scope=scope)
    def finalize(nonce='b' * 24, *, assets=False):
        task = step.name + ('.assets' if assets else '')
        entry = dict(key='c' * 64, packages=['/Game/Region/Mesh', '/Game/Region/Hull'],
                     sources=[dict(package='/Game/Region/' + name, member='generated/source.glb',
                                   sha256=mesh_reuse.digest(source)) for name in ('Mesh', 'Hull')],
                     provenance={'kind': 'current-native-import'})
        entry['native_assets_validated' if assets else 'native_source_validated'] = True
        if assets:
            entry['kind'] = 'asset-group'
        mesh_reuse.queue_pending(ctx, task, nonce, 'd' * 64, current, 'Mesh', entry,
                                 dict(imported=1, reused_local=0, reused_candidate=0))
        mesh_reuse.finalize_pending(ctx, step.name, nonce)
    stamp = dict(fingerprint='e' * 64, input_state={'inputs': {'original.py': 'original-identity'}})
    return SimpleNamespace(ctx=ctx, step=step, source=source, report=report, content=content,
                           store=store, finalize=finalize, stamp=stamp)


def retain(owner, **kwargs):
    return capture.publish(owner.ctx, owner.step, owner.stamp,
                           fresh=lambda: owner.stamp['fingerprint'], echo=lambda _: None, **kwargs)


def test_finalized_hints_are_automatically_discoverable_and_independent(owner):
    owner.finalize()
    key = retain(owner)
    assert key in checkpoint_candidates.local_keys(owner.store)
    value = native_protocol.read_json(owner.store.directory / 'candidate-sources' / (key + '.json'))
    assert value['stamps'] == {} and value['actions'] == {}
    assert value['historical_stamps'] == {owner.step.name: owner.stamp}
    assert set(value['files']) == {'generated/report.json', 'content/Region/Mesh.uasset',
                                   'content/Region/Mesh.ubulk', 'content/Region/Hull.uasset'}
    entry = value['files']['content/Region/Mesh.uasset']
    (owner.content / 'Region/Mesh.uasset').write_bytes(b'later owner edit')
    assert owner.store.blob(entry['sha256']).read_bytes() == b'Mesh'


@pytest.mark.parametrize('change', ['package', 'sidecar-added', 'source', 'linked', 'partial-scope', 'dirty', 'inputs'])
def test_changed_or_partial_evidence_cannot_publish(owner, monkeypatch, change):
    owner.finalize()
    if change == 'package':
        (owner.content / 'Region/Hull.uasset').write_bytes(b'changed')
    elif change == 'sidecar-added':
        (owner.content / 'Region/Hull.uexp').write_bytes(b'new')
    elif change == 'source':
        owner.source.write_bytes(b'changed')
    elif change == 'linked':
        target = owner.content / 'Region/Hull.uasset'; target.unlink(); target.symlink_to(owner.source)
    elif change == 'partial-scope':
        owner.step = replace(owner.step, candidate_scope=checkpoint_candidates.CandidateScope(
            files=(owner.report, owner.content / 'Region/Mesh.uasset', owner.content / 'Region/Mesh.ubulk')))
    elif change == 'dirty':
        monkeypatch.setattr(capture, '_revision', lambda: None)
    else:
        return_value = capture.publish(owner.ctx, owner.step, owner.stamp, fresh=lambda: 'f' * 64, echo=lambda _: None)
        assert return_value is None
        return
    assert retain(owner) is None
    assert not list((owner.store.directory / 'candidate-sources').glob('*.json'))


def test_multiple_commands_and_asset_groups_survive_receipt_book_replacement(owner):
    owner.finalize()
    owner.finalize('f' * 24, assets=True)
    owner.finalize('0' * 24)
    assert len(owner.ctx.native_candidate_observations[owner.step.name]) == 3
    assert retain(owner)


def test_metadata_and_package_change_during_copy_cannot_publish(owner, monkeypatch):
    owner.finalize()
    put = owner.store.put
    def changed(path, digest):
        put(path, digest)
        owner.report.write_text('changed during retention')
    monkeypatch.setattr(owner.store, 'put', changed)
    assert retain(owner) is None
    assert not list((owner.store.directory / 'candidate-sources').glob('*.json'))


def test_capture_does_not_walk_unrelated_content_or_plugin_trees(owner, monkeypatch):
    owner.finalize()
    def refuse(*args, **kwargs):
        raise AssertionError('Broad filesystem walk is forbidden')
    monkeypatch.setattr(Path, 'rglob', refuse)
    assert retain(owner)


def test_ordinary_build_retains_passed_owner_before_later_failure(owner, monkeypatch):
    from atelier import build_checkpoints
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: owner.ctx)
    later = build.Step('later', [build.Call('fail', lambda *_: None)], needs=[owner.step.name])
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [owner.step, later]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    monkeypatch.setattr(checkpoint_candidates, 'prepare', lambda *a, **kw: None)
    def run(ctx, step, command, log, *args, **kwargs):
        if step.name == 'later':
            raise RuntimeError('later task failed')
        owner.finalize()
    monkeypatch.setattr(build, 'run_command', run)
    assert build.build('fixture', echo=lambda _: None) == 1
    keys = checkpoint_candidates.local_keys(owner.store)
    assert len(keys) == 1
    value = native_protocol.read_json(owner.store.directory / 'candidate-sources' / (keys[0] + '.json'))
    saved = native_protocol.read_json(owner.ctx.stamps / (owner.step.name + '.json'))
    assert value['historical_stamps'][owner.step.name] == saved
    assert not (owner.ctx.stamps / 'later.json').exists()


def test_pending_child_evidence_never_retains_candidates(owner):
    assert retain(owner) is None
    assert not checkpoint_candidates.local_keys(owner.store)


@pytest.mark.parametrize('mutation', ['source', 'new-sidecar'])
def test_proof_rechecked_after_copy(owner, monkeypatch, mutation):
    owner.finalize()
    put = owner.store.put
    def changed(path, digest):
        put(path, digest)
        if mutation == 'source':
            owner.source.write_bytes(b'changed after copy')
        else:
            (owner.content / 'Region/Hull.uexp').write_bytes(b'new sidecar after copy')
    monkeypatch.setattr(owner.store, 'put', changed)
    assert retain(owner) is None
    assert not list((owner.store.directory / 'candidate-sources').glob('*.json'))


def test_new_partial_catalogue_cannot_hide_older_complete_donor(owner, monkeypatch):
    from atelier import build_checkpoints, native_candidates
    owner.finalize()
    complete = retain(owner)
    hull = owner.content / 'Region/Hull.uasset'
    # A+B -> A: a later owner roster removes B and publishes a newer partial catalogue.
    hull.unlink()
    nonce = '1' * 24
    entry = dict(key='2' * 64, packages=['/Game/Region/Mesh'], native_source_validated=True,
                 provenance={'kind': 'current-native-import'},
                 sources=[dict(package='/Game/Region/Mesh', member='generated/source.glb',
                               sha256=mesh_reuse.digest(owner.source))])
    mesh_reuse.queue_pending(owner.ctx, owner.step.name, nonce, 'd' * 64, native_protocol.context(owner.ctx),
                            'Mesh', entry, dict(imported=1, reused_local=0, reused_candidate=0))
    mesh_reuse.finalize_pending(owner.ctx, owner.step.name, nonce)
    partial = retain(owner)
    assert partial != complete
    assert checkpoint_candidates.local_keys(owner.store)[0] == partial
    monkeypatch.setattr(native_candidates, 'Store', lambda *_: owner.store)
    def guard(ctx, operation, request_id):
        assert operation == 'stage-candidates'
        return checkpoint_candidates.stage_worker(ctx, request_id)
    monkeypatch.setattr(build_checkpoints, '_guard', guard)
    # A -> A+B: ordinary discovery stages the coherent older donor including B.
    assert checkpoint_candidates.prepare(owner.ctx, owner.step, echo=lambda _: None)
    bundle = checkpoint_candidates.load(owner.ctx, owner.step.name)
    assert bundle['checkpoint'] == complete
    assert bundle.member_path('content/Region/Hull.uasset').read_bytes() == b'Hull'
    assert not hull.exists()  # Staging remains independent, without receiving success.


def test_linked_catalogue_parent_refuses_without_external_write(owner, tmp_path):
    owner.finalize()
    outside = tmp_path / 'outside'; outside.mkdir()
    (owner.store.directory / 'candidate-sources').symlink_to(outside, target_is_directory=True)
    assert retain(owner) is None
    assert not list(outside.iterdir())


def test_whole_owned_root_scope_selects_only_observed_groups(owner):
    owner.finalize()
    unrelated = owner.content / 'Other/Unrelated.uasset'
    unrelated.parent.mkdir(); unrelated.write_bytes(b'unobserved')
    owner.step = replace(owner.step, candidate_scope=checkpoint_candidates.CandidateScope(
        files=(owner.report,), directories=(owner.content, owner.ctx.out)))
    key = retain(owner)
    assert key
    value = native_protocol.read_json(owner.store.directory / 'candidate-sources' / (key + '.json'))
    assert 'content/Region/Hull.uasset' in value['files']
    assert 'content/Other/Unrelated.uasset' not in value['files']


@pytest.mark.parametrize('preference', ['fingerprint', 'metadata'])
def test_matching_newer_donor_outranks_larger_stale_workspace(owner, monkeypatch, preference):
    from atelier import build_checkpoints, native_candidates
    owner.finalize()
    older = retain(owner)
    if preference == 'metadata':
        owner.report.write_text('current roster A only')
    owner.stamp['fingerprint'] = 'f' * 64
    (owner.content / 'Region/Hull.uasset').unlink()
    entry = dict(key='2' * 64, packages=['/Game/Region/Mesh'], native_source_validated=True,
                 provenance={'kind': 'current-native-import'},
                 sources=[dict(package='/Game/Region/Mesh', member='generated/source.glb',
                               sha256=mesh_reuse.digest(owner.source))])
    mesh_reuse.queue_pending(owner.ctx, owner.step.name, '1' * 24, 'd' * 64, native_protocol.context(owner.ctx),
                            'Mesh', entry, dict(imported=1, reused_local=0, reused_candidate=0))
    mesh_reuse.finalize_pending(owner.ctx, owner.step.name, '1' * 24)
    newer = retain(owner)
    monkeypatch.setattr(native_candidates, 'Store', lambda *_: owner.store)
    monkeypatch.setattr(build_checkpoints, '_guard', lambda ctx, op, request: checkpoint_candidates.stage_worker(ctx, request))
    fingerprint = 'f' * 64 if preference == 'fingerprint' else None
    assert checkpoint_candidates.prepare(owner.ctx, owner.step, fingerprint=fingerprint, echo=lambda _: None)
    bundle = checkpoint_candidates.load(owner.ctx, owner.step.name)
    assert bundle['checkpoint'] == newer and newer != older
    # A cached ranking hint cannot bypass a later descriptor corruption at actual staging.
    target = owner.store.directory / 'candidate-sources' / (newer + '.json')
    target.write_text('{}')
    owner.ctx.prepared_candidate_tasks.clear()
    assert checkpoint_candidates.prepare(owner.ctx, owner.step, fingerprint=fingerprint, echo=lambda _: None)
    assert checkpoint_candidates.load(owner.ctx, owner.step.name)['checkpoint'] == older
