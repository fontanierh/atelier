"""Normal selected-target dispatch has no v1 certificate or fallback path."""
from types import SimpleNamespace

import pytest

from atelier import build, build_plan, paths
from atelier.build_v2 import controller_entry as entry
from atelier.build_v2.controller_recipe import ControllerTarget


def marker():
    return ControllerTarget('data.copy', 'fixture', {
        'schema_version': 2, 'cache_version': 'v2-1', 'units': [{
            'id': 'data.copy', 'op': {'kind': 'py_data', 'version': '1'},
            'script': 'ops/copy.py', 'code': ['ops/copy.py'], 'inputs': [],
            'outputs': [{'id': 'copy', 'logical_path': '/Game/Data/copy.json', 'class': 'JsonData',
                         'destination': 'checkout', 'files': [{'path': 'copy.json', 'install_path': 'Game/copy.json'}]}],
        }]}, {'data.copy': {}}, {}, ('Game',))


def test_controller_discovery_leaves_injected_legacy_recipe_selection_unchanged(monkeypatch):
    def absent(game):
        raise FileNotFoundError('a legacy test/caller owns this recipe provider')
    monkeypatch.setattr(paths, 'game_dir', absent)
    assert entry.exact_selection('injected', ['legacy.step']) is None


def test_controller_exact_selection_validates_unselected_owners_before_invocation(tmp_path, monkeypatch):
    from atelier import mesh_export_contract
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    other = build.Step('unselected.legacy', [], outputs=[tmp_path / 'Elsewhere/output.json'])
    contexts = []
    def steps(ctx):
        contexts.append(ctx)
        return [step, other]
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(paths, 'game_dir', lambda game: tmp_path)
    monkeypatch.setattr(paths, 'build_root', lambda: tmp_path / 'build')
    monkeypatch.setattr(paths, 'uproject', lambda game: tmp_path / 'source.uproject')
    monkeypatch.setattr(entry, 'discover', lambda game: {owned.unit: owned})
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=steps))
    def forbidden(*args, **kwargs):
        raise AssertionError('early controller dispatch created a legacy runtime Context')
    monkeypatch.setattr(build, 'Context', forbidden)
    checked = []
    def source_preflight(selected, blender_type):
        checked.append([item.name for item in selected])
    monkeypatch.setattr(mesh_export_contract, 'check_steps', source_preflight)
    assert entry.exact_selection('fixture', [owned.unit]) is step
    assert checked == [[owned.unit]]  # No unrelated Blender/source closure inspection.
    assert contexts[0].out == tmp_path / 'build/fixture'
    assert not hasattr(contexts[0], 'unreal_root')
    assert not (tmp_path / 'build').exists()
    other.outputs = [tmp_path / 'Game']
    with pytest.raises(ValueError, match='ownership overlaps'):
        entry.exact_selection('fixture', [owned.unit])
    assert not (tmp_path / 'build').exists()


def test_normal_exact_target_bypasses_legacy_context_stamps_and_fallback(tmp_path, monkeypatch):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    calls = []
    monkeypatch.setattr(entry, 'exact_selection', lambda *args: step)
    monkeypatch.setattr(entry, 'execute', lambda selected, **kwargs: calls.append(selected.name) or 1)
    def forbidden(*args, **kwargs):
        raise AssertionError('controller refusal fell back to the v1 engine')
    monkeypatch.setattr(build, 'Context', forbidden)
    assert build.build('fixture', [owned.unit], echo=lambda _: None) == 1
    assert calls == [owned.unit]
    with pytest.raises(ValueError, match='legacy force'):
        build.build('fixture', [owned.unit], touch=True, echo=lambda _: None)
    with pytest.raises(ValueError, match='legacy force'):
        build.build('fixture', [owned.unit], fail_fast=True, echo=lambda _: None)
    assert calls == [owned.unit]
    assert not list(tmp_path.iterdir())


def test_readonly_exact_controller_plan_never_bootstraps_or_opens_context(tmp_path, monkeypatch):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    monkeypatch.setattr(entry, 'exact_selection', lambda *args: step)
    def forbidden(*args, **kwargs):
        raise AssertionError('readonly plan performed runtime/bootstrap preparation')
    monkeypatch.setattr(build, 'Context', forbidden)
    monkeypatch.setattr(entry, 'ensure_controller', forbidden)
    monkeypatch.setattr(entry, 'invoke_controller', forbidden)
    output = []
    assert build_plan.show('fixture', [owned.unit], explain=True, echo=output.append) == 0
    assert 'unknown' in output[0]
    assert 'no helper bootstrap' in output[1]
    assert not list(tmp_path.iterdir())


def test_controller_list_is_explicit_without_runtime_context_or_bootstrap(tmp_path, monkeypatch):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(entry, 'discover', lambda game: {owned.unit: owned})
    monkeypatch.setattr(entry, 'declaration_context', lambda game: SimpleNamespace(game=game))
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: [step]))
    def forbidden(*args, **kwargs):
        raise AssertionError('controller list created runtime/bootstrap state')
    monkeypatch.setattr(build, 'Context', forbidden)
    monkeypatch.setattr(entry, 'ensure_controller', forbidden)
    monkeypatch.setattr(entry, 'invoke_controller', forbidden)
    output = []
    build.list_steps('fixture', echo=output.append)
    assert 'controller; reuse unknown; no bootstrap' in output[0]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('journal', ['.checkpoint-in-progress.json', '.reuse-in-progress.json',
                                     '.package-install-in-progress.json', '.portable-snapshot-in-progress.json'])
def test_controller_exact_build_and_plan_preserve_default_snapshot_barriers(tmp_path, monkeypatch, journal):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(paths, 'build_root', lambda: tmp_path / 'override')
    monkeypatch.setattr(entry, 'exact_selection', lambda *args: step)
    default = tmp_path / 'build/fixture'
    default.mkdir(parents=True)
    barrier = default / journal
    barrier.write_text('{}')
    def forbidden(*args, **kwargs):
        raise AssertionError('partial legacy snapshot reached runtime/bootstrap')
    monkeypatch.setattr(build, 'Context', forbidden)
    monkeypatch.setattr(entry, 'execute', forbidden)
    for invoke in [lambda: build.build('fixture', [owned.unit]),
                   lambda: build_plan.show('fixture', [owned.unit])]:
        with pytest.raises(SystemExit, match='incomplete|interrupted'):
            invoke()
    assert barrier.read_text() == '{}'
    assert not (tmp_path / 'override').exists()
    assert not (tmp_path / 'Game').exists()


def test_mixed_checkpoint_custody_refuses_before_old_workspace_restore(tmp_path, monkeypatch):
    from atelier import build_checkpoints
    owned = marker()
    leaf = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    legacy = build.Step('data.stage', [], after=[owned.unit], outputs=[tmp_path / 'Elsewhere/file'])
    ctx = SimpleNamespace(game='fixture', out=tmp_path / 'build')
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: [leaf, legacy]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: {'enabled': True})
    def forbidden(*args, **kwargs):
        raise AssertionError('mixed selection restored a v1 workspace before custody approval')
    monkeypatch.setattr(build_checkpoints, 'prepare', forbidden)
    with pytest.raises(ValueError, match='mixed v1/controller checkpoint'):
        build._prepared_build(ctx, ['data.stage'], force=False, touch=False, echo=lambda _: None,
                              verify=False, rebuild_reason=None, rebuild_touched=False,
                              record_cook_recovery=False, max_heavy_commands=None)
    assert not (tmp_path / 'build').exists()


def test_controller_parent_alias_refuses_before_queries_checkpoints_dispatch_or_writes(tmp_path, monkeypatch):
    from atelier import build_spatial
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    (tmp_path / 'Game').mkdir()
    alias = tmp_path / 'Alias'
    alias.symlink_to(tmp_path / 'Game', target_is_directory=True)
    other = build.Step('unselected.legacy', [], outputs=[alias / 'copy.json'])
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(paths, 'game_dir', lambda game: tmp_path)
    monkeypatch.setattr(paths, 'build_root', lambda: tmp_path / 'build')
    monkeypatch.setattr(paths, 'uproject', lambda game: tmp_path / 'source.uproject')
    monkeypatch.setattr(entry, 'discover', lambda game: {owned.unit: owned})
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: [step, other]))
    reached = []
    def forbidden(*args, **kwargs):
        reached.append(True)
        raise AssertionError('ownership preflight reached runtime/query/checkpoint/dispatch')
    monkeypatch.setattr(build, 'Context', forbidden)
    monkeypatch.setattr(build, '_prepared_build', forbidden)
    monkeypatch.setattr(build_spatial, 'bind', forbidden)
    monkeypatch.setattr(entry, 'execute', forbidden)
    with pytest.raises(ValueError, match='controller output ownership overlaps'):
        build.build('fixture', [owned.unit], echo=lambda _: None)
    assert reached == []
    assert not (tmp_path / 'Game/copy.json').exists()
    assert not (tmp_path / 'build').exists()
    assert set(tmp_path.iterdir()) == {tmp_path / 'Game', alias}


def test_failed_normal_target_prints_private_diagnostic_locator_without_changing_result(tmp_path, monkeypatch):
    owned = marker()
    step = build.Step(owned.unit, [], outputs=list(owned.outputs(tmp_path)), controller=owned)
    log = tmp_path / 'private-run/controller.log'
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(paths, 'build_root', lambda: tmp_path / 'build')
    monkeypatch.setattr(paths, 'cache_dir', lambda *args, **kwargs: tmp_path / 'cache')
    monkeypatch.setattr(entry, 'ensure_controller', lambda *args, **kwargs: object())
    monkeypatch.setattr(entry, 'provenance', lambda _: {})
    monkeypatch.setattr(entry, 'invoke_controller', lambda *args, **kwargs: {
        'state': 'observed', 'cancelled': False, 'returncode': 0,
        'diagnostic_log': str(log), 'report': {'observation': {
            'summary': None, 'cancellation_requested': False,
            'final_requirements_satisfied': False,
        }},
    })
    output = []
    assert entry.execute(step, echo=output.append) == 1  # Helper exit0 is not target success.
    assert output[-1] == f'Private failure diagnostic locator: {log}'
    assert not list(tmp_path.iterdir())
