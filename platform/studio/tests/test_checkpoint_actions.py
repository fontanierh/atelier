"""Action reuse and failure boundaries with real files; no Unreal or Blender launches."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, build_snapshot, checkpoint_actions as actions, checkpoint_store as cp, paths
from atelier.build_cache import atomic_json
from test_checkpoints import fixture  # noqa: F401


def saved(fixture):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    step = steps[0]
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    key = actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    return ctx, steps, key


def test_task_reuses_in_warm_changed_checkout_without_overwriting_other_work(fixture, monkeypatch):
    _, _, key = saved(fixture)
    ctx, steps = fixture.checkout('receiver', changed=True)
    own = ctx.out / 'combat/new.bin'; own.parent.mkdir(parents=True); own.write_bytes(b'new combat')
    cache = actions.Actions(ctx, {})
    cache.store = fixture.store
    fingerprint = build.fingerprint(steps[0], {})
    hit = cache.get(steps[0], fingerprint)
    assert hit['key'] == key
    def guarded(ctx, operation, key):
        assert operation == 'restore-action'
        actions.restore_worker(ctx, steps[0], fixture.store, key)
        assert (ctx.out / cp.JOURNAL).exists()
        assert not (ctx.stamps / 'tree.json').exists()
        return dict(key=key)
    monkeypatch.setattr(build_checkpoints, '_guard', guarded)
    cache.restore(steps[0], fingerprint, hit, {})
    assert steps[0].outputs[0].read_bytes() == b'tree'
    assert own.read_bytes() == b'new combat'
    assert not (ctx.out / cp.JOURNAL).exists()


def test_source_change_during_publication_cannot_save_action(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    step = steps[0]; stamp = cp.read_json(ctx.stamps / 'tree.json')
    key = actions.key(ctx, step, stamp['fingerprint'])
    put = fixture.store.put
    def racing(source, digest):
        put(source, digest)
        step.inputs[0].write_text('new source while bytes were copied')
    monkeypatch.setattr(fixture.store, 'put', racing)
    with pytest.raises(cp.CheckpointError, match='changed during publication'):
        actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    assert not actions.entry_path(fixture.store, key).exists()


def test_same_inputs_different_outputs_disable_key(fixture):
    ctx, steps, key = saved(fixture)
    step = steps[0]
    step.outputs[0].write_bytes(b'different bytes')
    stamp = dict(cp.read_json(ctx.stamps / 'tree.json'), products=build.build_products.records(step))
    with pytest.raises(cp.CheckpointError, match='different outputs'):
        actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    assert actions.entry_path(fixture.store, key).with_suffix('.conflict').exists()


def test_restore_cannot_bypass_another_installation_barrier(fixture):
    _, _, key = saved(fixture)
    ctx, steps = fixture.checkout('receiver')
    ctx.out.mkdir(parents=True)
    (ctx.out / build_snapshot.PACKAGE_JOURNAL).write_text('{}')
    with pytest.raises(SystemExit, match='Package installation'):
        actions.restore_worker(ctx, steps[0], fixture.store, key)
    assert not steps[0].outputs[0].exists()


def test_extra_roots_cannot_overwrite_another_owner(fixture):
    ctx, steps = fixture.checkout('producer')
    steps[1].checkpoint_outputs = (steps[0].products[0].paths[0].parent,)
    with pytest.raises(cp.CheckpointError, match='overlap'):
        actions.validate_ownership(ctx, steps)


def test_compile_receipt_requires_every_declared_plugin_binary(tmp_path, monkeypatch):
    repo = tmp_path.resolve()
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    project = repo / 'game/Fixture.uproject'; project.parent.mkdir()
    project.write_text(json.dumps(dict(Modules=[dict(Name='Fixture', Type='Runtime')])))
    plugin = paths.ENGINE_PLUGINS / 'Sample/Sample.uplugin'; plugin.parent.mkdir(parents=True)
    plugin.write_text(json.dumps(dict(Modules=[dict(Name='Sample', Type='Runtime')])))
    ctx = SimpleNamespace(uproject=project)
    step = build.Step('compile', [build.UnrealCompile('FixtureEditor')])
    output = project.parent / 'Binaries/Mac'; output.mkdir(parents=True)
    for name in ('libUnrealEditor-Fixture.dylib', 'libUnrealEditor-Sample.dylib', 'UnrealEditor.modules'):
        (output / name).write_text(name)
    receipt = output / 'FixtureEditor.target'
    receipt.write_text(json.dumps(dict(TargetName='FixtureEditor', Platform='Mac', BuildProducts=[
        dict(Path='$(ProjectDir)/Binaries/Mac/libUnrealEditor-Sample.dylib', Type='DynamicLibrary')])))
    assert actions.compile_present(ctx, step)
    (output / 'libUnrealEditor-Sample.dylib').unlink()
    assert not actions.compile_present(ctx, step)
    receipt.unlink()
    assert not actions.compile_present(ctx, step)


def test_normal_build_uses_action_hit_before_a_native_batch(tmp_path, monkeypatch):
    # A tiny recipe goes through the actual execution loop with an in-process copy worker.
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture', logs=repo / 'build/fixture/logs',
                          stamps=repo / 'build/fixture/stamps', cook_mode=build.CookMode.DEFAULT)
    source = repo / 'source'; source.write_text('source')
    script = repo / 'script.py'; script.write_text('# source')
    output = ctx.out / 'mesh'
    step = build.Step('mesh', [build.Python(script)], inputs=[source],
                      products=[build.Product('mesh', (output,))])
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    from atelier import build_cache, build_batches
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: dict(tool='fixed'))
    runs = []
    def run(ctx, step, command, log, *args, **kw):
        runs.append(step.name)
        output.mkdir(parents=True)
        (output / 'data').write_text('mesh')
        (output / 'empty').mkdir()
    monkeypatch.setattr(build, 'run_command', run)
    assert build.build('fixture') == 0
    original = build.build_products.records(step)
    (output / 'data').write_text('corrupt')
    def guard(ctx, operation, key):
        actions.restore_worker(ctx, step, cp.Store(ctx.game), key)
        return dict(key=key)
    monkeypatch.setattr(build_checkpoints, '_guard', guard)
    monkeypatch.setattr(build_batches, 'select', lambda *a, **kw: pytest.fail('cache hit entered batch selection'))
    assert build.build('fixture') == 0 and runs == ['mesh']
    assert build.build_products.records(step) == original
    # Exact task force never forces a prerequisite.
    ctx.checkpoint_force_task = 'other'
    from atelier.build_cook import forced
    assert not forced(ctx, step, True)


def test_restore_cost_cannot_make_a_later_full_rebuild_look_cheap():
    assert build_checkpoints.estimate(dict(seconds=.1, restored_from='key')) is None
    assert build_checkpoints.estimate(dict(seconds=.1, restored_from='key', checkpoint_build_seconds=900)) == 900


def test_tracked_source_cannot_become_an_action_output(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    monkeypatch.setattr(actions, 'tracked_paths', lambda: {steps[0].outputs[0]})
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    with pytest.raises(cp.CheckpointError, match='tracked source'):
        actions.publish(ctx, steps[0], stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)


def test_private_repository_is_configured_outside_source(fixture, monkeypatch):
    from atelier.checkpoint_github import Remote
    monkeypatch.setattr(Remote, 'require_private', lambda self: dict(private=True))
    result = build_checkpoints.configure_repository('owner/artifacts')
    settings = paths.cache_dir('checkpoints') / 'settings.json'
    assert result == dict(configured=True, scope='machine-local')
    assert settings.stat().st_mode & 0o777 == 0o600
    assert json.loads(settings.read_text()) == dict(repository='owner/artifacts')


def test_unchanged_source_cannot_adopt_old_outputs_under_new_native_tools(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    steps[0].commands = [build.UnrealScript(steps[0].inputs[0], 'done')]
    monkeypatch.setattr(actions, 'context', lambda ctx: dict(system='Darwin', machine='arm64', engine={'version': 'old'}))
    fixture.produce(ctx, steps)
    step = steps[0]; stamp = cp.read_json(ctx.stamps / 'tree.json')
    fingerprint = build.fingerprint(step, {})
    assert actions.certified(ctx, step, fingerprint, stamp)
    monkeypatch.setattr(actions, 'context', lambda ctx: dict(system='Darwin', machine='arm64', engine={'version': 'new'}))
    del ctx.checkpoint_tool_context  # A new invocation reads the selected tools again.
    assert build.fingerprint(step, {}) == fingerprint
    assert not actions.certified(ctx, step, fingerprint, stamp)
    with pytest.raises(cp.CheckpointError, match='producer tool/inventory proof'):
        actions.publish(ctx, step, fingerprint, stamp, store=fixture.store, done={})


def test_lost_action_manifest_does_not_allow_changed_secondary_outputs(fixture):
    ctx, steps, key = saved(fixture)
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    actions.entry_path(fixture.store, key).unlink()
    assert actions.certified(ctx, steps[0], stamp['fingerprint'], stamp)
    (steps[0].outputs[0].parent / 'unrecorded-secondary').write_text('extra bytes')
    assert not actions.certified(ctx, steps[0], stamp['fingerprint'], stamp)


def test_pre_key_release_retains_only_uncertified_workspace_seed(fixture):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    for path in ctx.stamps.glob('*.json'):
        value = cp.read_json(path)
        value.pop('checkpoint_key'); value.pop('checkpoint_inventory')
        atomic_json(path, value)
    key = cp.capture(ctx, steps, fixture.store, allow_seed=True)
    assert fixture.store.load(key)['stamps'] == {}
    assert fixture.store.load(key)['actions'] == {}
    assert fixture.store.load(key)['files']


def test_observed_environment_keeps_pre_key_warm_state_without_adopting_it(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    stamp.pop('checkpoint_key'); stamp.pop('checkpoint_inventory')
    monkeypatch.setattr(build_checkpoints, 'context', lambda ctx: dict(engine='first environment'))
    build_checkpoints.incremental_environment(ctx)
    assert actions.local_incremental(ctx, steps[0], stamp['fingerprint'], stamp)
    assert not actions.certified(ctx, steps[0], stamp['fingerprint'], stamp)
    monkeypatch.setattr(build_checkpoints, 'context', lambda ctx: dict(engine='changed environment'))
    build_checkpoints.incremental_environment(ctx)
    assert not actions.local_incremental(ctx, steps[0], stamp['fingerprint'], stamp)


def test_non_factory_blender_does_not_claim_a_portable_action_key(fixture):
    ctx, steps = fixture.checkout('producer')
    step = steps[0]
    step.commands = [build.Blender(step.inputs[0], factory_startup=False)]
    assert actions.key(ctx, step, build.fingerprint(step, {})) is None


def test_compatible_workspace_keeps_pre_key_stamps_without_action_certificates(fixture):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    for path in ctx.stamps.glob('*.json'):
        value = cp.read_json(path); value.pop('checkpoint_key'); value.pop('checkpoint_inventory')
        atomic_json(path, value)
    build_checkpoints.incremental_environment(ctx)
    key = cp.capture(ctx, steps, fixture.store)
    value = fixture.store.load(key)
    assert not value['stamps'] and not value['actions']
    assert set(value['incremental_stamps']) == {'tree', 'combat', 'house'}
    receiver, current = fixture.checkout('receiver', changed=True)
    restored = cp.restore(receiver, current, fixture.store, key)
    build_checkpoints._publish_restoration(receiver, current, fixture.store, key, dict(key=key, stamps=restored))
    assert set(restored) == {'tree', 'house'}
    assert all('checkpoint_key' not in record for record in restored.values())


def test_fresh_unsupported_execution_is_current_after_observed_environment_change(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    monkeypatch.setattr(build_checkpoints, 'context', lambda ctx: dict(engine='first'))
    build_checkpoints.incremental_environment(ctx)
    monkeypatch.setattr(build_checkpoints, 'context', lambda ctx: dict(engine='second'))
    build_checkpoints.incremental_environment(ctx)
    assert not ctx.checkpoint_incremental_compatible
    stamp = dict(fingerprint='a' * 64, checkpoint_key=None,
                 checkpoint_incremental_context=ctx.checkpoint_observed_context)
    assert actions.local_incremental(ctx, steps[0], 'a' * 64, stamp)


def test_browser_compile_owns_its_platform_and_requires_receipt_products(tmp_path, monkeypatch):
    repo = tmp_path.resolve()
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    project = repo / 'games/fixture/unreal/Fixture.uproject'
    project.parent.mkdir(parents=True)
    project.write_text(json.dumps(dict(Modules=[dict(Name='Fixture', Type='Runtime')])))
    ctx = SimpleNamespace(uproject=project, out=repo / 'build/fixture', game_dir=project.parent.parent)
    editor = build.Step('editor', [build.UnrealCompile('FixtureEditor')])
    browser = build.Step('browser', [build.UnrealCompile('Fixture', platform='HTML5')])
    actions.validate_ownership(ctx, [editor, browser])
    output = project.parent / 'Binaries/HTML5'
    output.mkdir(parents=True)
    wasm = output / 'Fixture.wasm'
    wasm.write_bytes(b'\0asm\x01\0\0\0')
    receipt = output / 'Fixture.target'
    receipt.write_text(json.dumps(dict(TargetName='Fixture', Platform='HTML5', BuildProducts=[
        dict(Path='$(ProjectDir)/Binaries/HTML5/Fixture.wasm', Type='RequiredResource'),
        dict(Path='$(ProjectDir)/Binaries/HTML5/Fixture.wasm.debug.wasm', Type='SymbolFile')])))
    assert actions.compile_present(ctx, browser)
    # No portable result is claimed under a Mac-only SDK/tool context.
    assert actions.key(ctx, browser, 'a' * 64) is None
    wasm.unlink()
    assert not actions.compile_present(ctx, browser)
