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
