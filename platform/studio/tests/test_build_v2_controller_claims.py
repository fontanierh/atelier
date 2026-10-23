"""Legacy artifacts cannot acquire or replace declared controller file ownership."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, checkpoint_actions as actions, checkpoint_candidates, checkpoint_manifest
from atelier import checkpoint_store as cp
from atelier.build_v2.controller_claims import ControllerClaims
from atelier.build_v2.controller_recipe import _claim
from test_build_v2_controller_recipe import marker
from test_checkpoint_actions import saved
from test_checkpoints import fixture  # noqa: F401
from test_checkpoint_manifest import published


def test_fixed_claims_ignore_permissions_and_refuse_alias_or_parent_authority(tmp_path):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    claims = ControllerClaims.from_steps([step], tmp_path)
    assert claims.excludes(tmp_path / 'Game/copy.json')
    assert not claims.excludes(tmp_path / 'Game')
    assert not claims.excludes(tmp_path / 'Game/other.json')  # Allowed install root is not a claim.
    claims.refuse_overlap([tmp_path / 'Archives/Game/copy.json', tmp_path / 'Game/derived.pak'])
    for path in ['Game', 'game/COPY.JSON', 'Game/copy.json/child']:
        with pytest.raises(ValueError, match='controller-owned'):
            claims.refuse_overlap([tmp_path / path])
    unicode_claim = ControllerClaims((_claim(tmp_path / 'Game/Café.json'),))
    with pytest.raises(ValueError, match='controller-owned'):
        unicode_claim.refuse_overlap([tmp_path / 'game/Cafe\u0301.json'])


def test_workspace_omits_controlled_file_without_hiding_shared_parent_or_other_artifacts(fixture):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    controlled = steps[0].outputs[0]
    ctx._controller_file_claims = ControllerClaims((_claim(controlled),))
    value = checkpoint_manifest._workspace(ctx, fixture.store)
    controlled_name = actions.label(ctx, controlled)
    assert controlled_name not in value['files']
    assert any(entry.get('kind') == 'file' for entry in value['files'].values())
    assert controlled.read_bytes() == b'tree'
    assert str(controlled) not in {str(actions.destination(ctx, name)) for name in value['local_observations']}


def test_restore_and_snapshot_refuse_complete_controlled_scope_before_mutation(fixture):
    _, _, key = saved(fixture)
    ctx, steps = fixture.checkout('receiver')
    controlled = steps[0].outputs[0]
    controlled.parent.mkdir(parents=True, exist_ok=True)
    controlled.write_bytes(b'current controlled data')
    ctx._controller_file_claims = ControllerClaims((_claim(controlled),))
    with pytest.raises(cp.CheckpointError, match='controller-owned'):
        actions.restore_worker(ctx, steps[0], fixture.store, key)
    assert controlled.read_bytes() == b'current controlled data'
    assert not (ctx.out / cp.JOURNAL).exists()
    with pytest.raises(cp.CheckpointError, match='controller-owned'):
        actions.snapshot(ctx, steps[0], fixture.store, save_blobs=True)
    # An old ancestor root cannot delete the owned leaf even if its inventory omitted it.
    with pytest.raises(cp.CheckpointError, match='controller-owned'):
        actions.reject_controller_overlap(ctx, [controlled.parent])


def test_candidate_refuses_owned_receiving_member_before_staging(tmp_path, monkeypatch):
    ctx = SimpleNamespace(game='fixture', out=tmp_path / 'build')
    controlled = ctx.out / 'tree.json'
    ctx._controller_file_claims = ControllerClaims((_claim(controlled),))
    request = {'checkpoint': '0' * 64, 'donor_task': 'old', 'receiver_task': 'new',
               'members': ['generated/tree.json']}
    monkeypatch.setattr(checkpoint_candidates, 'read_json', lambda path: request)
    monkeypatch.setattr(checkpoint_candidates, 'inventory', lambda *args: {'files': {}})
    with pytest.raises(cp.CheckpointError, match='controller-owned'):
        checkpoint_candidates.stage_worker(ctx, 'a' * 24)
    assert not ctx.out.exists()


def test_controller_marker_never_enters_legacy_historical_candidates_or_keys(tmp_path):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    ctx = SimpleNamespace(stamps=tmp_path / 'missing')
    assert cp.historical_candidates(ctx, [step]) == {}
    with pytest.raises(cp.CheckpointError, match='legacy action keys'):
        actions.key(ctx, step, '0' * 64)


def test_retention_refuses_old_controlled_file_from_metadata_without_rehash(fixture, monkeypatch):
    from atelier import paths
    from atelier.build_v2 import controller_claims
    ctx, steps = published(fixture, monkeypatch)
    claims = ControllerClaims((_claim(steps[0].outputs[0]),))
    monkeypatch.setattr(controller_claims, 'for_source', lambda *args: claims)
    monkeypatch.setattr(actions, 'snapshot', lambda *args, **kwargs: pytest.fail('retention recertified outputs'))
    monkeypatch.setattr(cp, 'members', lambda *args: pytest.fail('retention walked outputs'))
    with pytest.raises(cp.CheckpointError, match='controller ownership'):
        checkpoint_manifest.retain(paths.REPO, ctx.out, ctx.game)


def test_retention_refuses_embedded_ancestor_action_even_without_owned_file_in_inventory(fixture, monkeypatch):
    from atelier import paths
    from atelier.build_v2 import controller_claims
    ctx, steps = published(fixture, monkeypatch)
    # Original tree action owns its complete directory. The new controller path was
    # not present when that action published, so workspace file-only checks miss it.
    controlled = steps[0].outputs[0].parent / 'future-controller.json'
    assert not controlled.exists()
    ready = cp.read_json(checkpoint_manifest.folder(ctx.out) / 'ready.json')
    manifest = fixture.store.load(ready['key'])
    assert actions.label(ctx, controlled) not in manifest['files']
    assert any(root['path'] == actions.label(ctx, controlled.parent)
               for action in manifest['actions'].values() for root in action['roots'])
    claims = ControllerClaims((_claim(controlled),))
    monkeypatch.setattr(controller_claims, 'for_source', lambda *args: claims)
    monkeypatch.setattr(actions, 'snapshot', lambda *args, **kwargs: pytest.fail('retention recertified outputs'))
    monkeypatch.setattr(cp, 'members', lambda *args: pytest.fail('retention walked outputs'))
    with pytest.raises(cp.CheckpointError, match='controller ownership'):
        checkpoint_manifest.retain(paths.REPO, ctx.out, ctx.game)
    assert not controlled.exists()
    assert cp.read_json(checkpoint_manifest.folder(ctx.out) / 'ready.json') == ready


def test_retention_keeps_complete_disjoint_actions_when_controller_file_is_elsewhere(fixture, monkeypatch):
    from atelier import paths
    from atelier.build_v2 import controller_claims
    ctx, _ = published(fixture, monkeypatch)
    ready = cp.read_json(checkpoint_manifest.folder(ctx.out) / 'ready.json')
    claims = ControllerClaims((_claim(ctx.out / 'controller/course.json'),))
    monkeypatch.setattr(controller_claims, 'for_source', lambda *args: claims)
    assert checkpoint_manifest.retain(paths.REPO, ctx.out, ctx.game) == ready['key']
    assert len(fixture.store.load(ready['key'])['actions']) == 3


def test_capture_drops_whole_old_overlapping_action_but_keeps_disjoint_results(fixture):
    ctx, steps, old_key = saved(fixture)
    controlled = steps[0].outputs[0]
    ctx._controller_file_claims = ControllerClaims((_claim(controlled),))
    key = cp.capture(ctx, steps[1:], fixture.store, echo=lambda _: None)
    manifest = fixture.store.load(key)
    assert old_key not in manifest['actions']
    assert actions.label(ctx, controlled) not in manifest['files']
    assert set(manifest['stamps']) == {'combat', 'house'}
    assert manifest['files']  # Non-overlapping ordinary results still publish.


def test_candidate_ancestor_scope_refuses_but_disjoint_packaged_output_remains_eligible(tmp_path):
    ctx = SimpleNamespace(game='fixture', out=tmp_path / 'build')
    controlled = ctx.out / 'data/courses.json'
    ctx._controller_file_claims = ControllerClaims((_claim(controlled),))
    with pytest.raises(cp.CheckpointError, match='controller-owned'):
        checkpoint_candidates.select(ctx, checkpoint_candidates.CandidateScope(directories=(controlled.parent,)), {})
    package = ctx.out / 'package/game.pak'
    member = actions.label(ctx, package)
    assert checkpoint_candidates.select(ctx, checkpoint_candidates.CandidateScope(files=(package,)),
                                        {member: {'kind': 'file'}}) == [member]
