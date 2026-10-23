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
    monkeypatch.setattr(build_checkpoints, '_guard', lambda *a: pytest.fail('action restore spawned a child'))
    worker = actions.restore_worker
    def barrier(ctx, step, store, key, **kwargs):
        value = worker(ctx, step, store, key, **kwargs)
        assert (ctx.out / cp.JOURNAL).exists()  # The launch barrier stands until verification.
        assert not (ctx.stamps / 'tree.json').exists()
        return value
    monkeypatch.setattr(actions, 'restore_worker', barrier)
    cache.restore(steps[0], fingerprint, hit, {})
    assert steps[0].outputs[0].read_bytes() == b'tree'
    assert own.read_bytes() == b'new combat'
    assert not (ctx.out / cp.JOURNAL).exists()


def test_source_change_during_publication_cannot_save_action(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    ctx.build_tool_cache = {}
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


def test_publication_reuses_invocation_tool_resources_but_refuses_changed_binary(fixture, tmp_path, monkeypatch):
    from dataclasses import replace
    from atelier import build_cache, engine
    ctx, steps = fixture.checkout('producer')
    bundle = tmp_path / 'Blender.app/Contents'
    binary, resource = bundle / 'MacOS/Blender', bundle / 'Resources/exporter.py'
    binary.parent.mkdir(parents=True); resource.parent.mkdir(parents=True)
    binary.write_bytes(b'executable one'); resource.write_bytes(b'complete bundled exporter')
    monkeypatch.setattr(engine, 'blender', lambda: str(binary))
    step = replace(steps[0], commands=[build.Blender(steps[0].inputs[0], factory_startup=True)], cache=True)
    fixture.produce(ctx, [step])
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    ctx.build_tool_cache = {}
    assert build.fingerprint(step, {}, tool_cache=ctx.build_tool_cache) == stamp['fingerprint']
    original = build_cache.tool_context
    calls, reads = [], []
    def context(step, hasher, *, cache=None):
        calls.append(cache)
        def observed(path):
            reads.append(path)
            return hasher(path)
        return original(step, observed, cache=cache)
    monkeypatch.setattr(build_cache, 'tool_context', context)
    assert actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    assert sum(value is ctx.build_tool_cache for value in calls) == 2
    assert len(calls) == 4 and all(value is ctx.build_tool_cache or value is ctx.checkpoint_source_tool_cache
                                 for value in calls)
    assert resource not in reads  # No repeated complete app hashing for each publication.
    assert binary not in reads  # The executable's stat signature is unchanged since planning hashed it.
    binary.write_bytes(b'changed executable')
    with pytest.raises(cp.CheckpointError, match='inputs changed before publication'):
        actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    assert binary in reads  # A changed executable is rehashed and invalidates the bundle memo;
    assert resource not in reads  # an unchanged resource keeps its stat-bound digest.


def test_publishing_many_actions_hashes_the_tool_once_and_nothing_under_the_store_lock(fixture, tmp_path, monkeypatch):
    import builtins
    import contextlib
    import io
    from dataclasses import replace
    from atelier import build_cache, build_hashes, engine
    ctx, steps = fixture.checkout('producer')
    bundle = tmp_path / 'Blender.app/Contents'
    binary = bundle / 'MacOS/Blender'
    binary.parent.mkdir(parents=True); (bundle / 'Resources').mkdir()
    binary.write_bytes(b'large executable'); (bundle / 'Resources/exporter.py').write_bytes(b'exporter')
    monkeypatch.setattr(engine, 'blender', lambda: str(binary))
    monkeypatch.setattr(build_cache, '_TOOL_DIGESTS', {})
    steps = [replace(s, commands=[build.Blender(s.inputs[0], factory_startup=True)], cache=True) for s in steps]
    opened, locked = [], []
    real_open, real_io_open, real_locked = builtins.open, io.open, fixture.store.locked
    def watch(opener):
        def spy(file, *args, **kwargs):
            path = Path(file) if isinstance(file, (str, Path)) else None
            if path is not None:
                opened.append(path)

                if locked and not path.is_relative_to(fixture.store.directory):
                    pytest.fail(f'read {path} while holding the store lock')
            return opener(file, *args, **kwargs)
        return spy
    @contextlib.contextmanager
    def holding():
        with real_locked():
            locked.append(True)
            try:
                yield
            finally:
                locked.pop()
    monkeypatch.setattr(builtins, 'open', watch(real_open))
    monkeypatch.setattr(io, 'open', watch(real_io_open))
    monkeypatch.setattr(fixture.store, 'locked', holding)
    fixture.produce(ctx, steps)
    ctx.build_tool_cache = {}
    ctx.build_hash_index = build_hashes.HashIndex(ctx.out / '.state/file-hashes.sqlite3')
    for step in steps:
        stamp = cp.read_json(ctx.stamps / (step.name + '.json'))
        assert actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    assert opened.count(binary) <= 1
    assert all(actions.entry_path(fixture.store, actions.key(ctx, s, cp.read_json(ctx.stamps / (s.name + '.json'))['fingerprint'])).exists()
               for s in steps)


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


def test_declared_roots_keep_outermost_order_and_sibling_names(tmp_path):
    parent = tmp_path / 'owned'
    sibling = tmp_path / 'owned-other'
    step = build.Step('geometry', [], checkpoint_outputs=(parent / 'child', sibling,
                       parent, parent / 'child' / 'file', sibling, tmp_path / 'other'))
    assert actions.declared(SimpleNamespace(), step) == [sibling, parent, tmp_path / 'other']


@pytest.mark.parametrize('root', ['.', '/', 'generated', 'generated/tree', 'generated/trees',
                                '/generated', '/generated/tree', '/generated/trees', '../source'])
def test_source_scope_lookup_preserves_lexical_source_protection(root):
    sources = {Path('generated/tree/model.glb'), Path('/generated/tree/code.py'), Path('../source')}
    candidate = Path(root)
    expected = any(candidate == source or candidate in source.parents for source in sources)
    assert (candidate in actions.source_scopes(sources)) == expected


def test_snapshot_rechecks_newly_tracked_files(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    sources = set()
    monkeypatch.setattr(actions, 'tracked_paths', lambda: sources.copy())
    actions.snapshot(ctx, steps[0], fixture.store, save_blobs=False)
    sources.add(steps[0].outputs[0])
    with pytest.raises(cp.CheckpointError, match='tracked source'):
        actions.snapshot(ctx, steps[0], fixture.store, save_blobs=False)


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
    from test_checkpoints import publish_receiver
    assert publish_receiver(receiver, current, fixture.store, key, restored) == {'tree', 'house'}
    assert all('checkpoint_key' not in cp.read_json(p) for p in receiver.stamps.glob('*.json'))


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


def offline(monkeypatch):
    """Any subprocess or socket use during lookup fails the test."""
    import socket, subprocess
    from atelier import checkpoint_github
    def refuse(*_, **__):
        pytest.fail('ordinary checkpoint lookup made a subprocess or network call')
    for name in ('run', 'Popen', 'check_output', 'check_call', 'call'):
        monkeypatch.setattr(subprocess, name, refuse)
    monkeypatch.setattr(socket, 'create_connection', refuse)
    monkeypatch.setattr(socket.socket, 'connect', refuse)
    monkeypatch.setattr(checkpoint_github, 'Remote', refuse)


def test_ordinary_miss_makes_no_subprocess_or_network_call(fixture, monkeypatch):
    monkeypatch.delenv(build_checkpoints.REMOTE_LOOKUP, raising=False)
    ctx, steps = fixture.checkout('receiver')
    cache = actions.Actions(ctx, dict(repository='owner/private'))
    cache.store = fixture.store
    offline(monkeypatch)
    assert cache.get(steps[0], build.fingerprint(steps[0], {})) is None
    assert cache.remote is None


def test_cold_prepare_without_local_checkpoint_stays_offline(fixture, monkeypatch):
    monkeypatch.delenv(build_checkpoints.REMOTE_LOOKUP, raising=False)
    ctx, steps = fixture.checkout('receiver')
    monkeypatch.setattr(build_checkpoints, 'Store', lambda game: fixture.store)
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: dict(repository='owner/private'))
    monkeypatch.setattr(build_checkpoints, 'cold', lambda ctx: True)
    messages = []
    offline(monkeypatch)
    build_checkpoints.prepare(ctx, steps, echo=messages.append)
    assert any('remote checkpoint lookup is off' in m for m in messages)


def test_remote_action_lookup_runs_only_when_opted_in(fixture, monkeypatch):
    from contextlib import contextmanager
    from atelier import checkpoint_github
    ctx, steps = fixture.checkout('receiver')
    opened = []
    class Remote:
        def __init__(self, repository, game, echo=None): opened.append(repository)
        @contextmanager
        def transaction(self): yield
        def candidates(self): return []
    monkeypatch.setattr(checkpoint_github, 'Remote', Remote)
    monkeypatch.setenv(build_checkpoints.REMOTE_LOOKUP, '1')
    cache = actions.Actions(ctx, dict(repository='owner/private'))
    cache.store = fixture.store
    assert cache.get(steps[0], build.fingerprint(steps[0], {})) is None
    assert opened == ['owner/private']


def test_action_restore_is_in_process_and_takes_milliseconds(fixture, monkeypatch):
    import time
    from atelier.build_hashes import HashIndex
    ctx, steps = fixture.checkout('producer')
    fixture.produce(ctx, steps)
    for i in range(200):  # A foliage-sized action: many outputs under one declared root.
        (ctx.out / 'tree' / f'lod{i}.bin').write_bytes(b'lod %d' % i)
    step = steps[0]
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    stamp['products'] = build.build_products.records(step)
    stamp['checkpoint_inventory'] = actions.inventory_identity(*actions.snapshot(ctx, step, fixture.store, save_blobs=False))
    actions.publish(ctx, step, stamp['fingerprint'], stamp, store=fixture.store, done={}, produced=True)
    receiver, received = fixture.checkout('receiver')
    monkeypatch.setattr(build_checkpoints, '_guard', lambda *a: pytest.fail('action restore spawned a child'))
    cache = actions.Actions(receiver, {})
    cache.store = fixture.store
    with HashIndex(receiver.out / '.state/file-hashes.sqlite3') as index:
        tools = {}
        current = build.fingerprint(received[0], {}, index=index, tool_cache=tools)
        hit = cache.get(received[0], current)
        started = time.perf_counter()
        cache.restore(received[0], current, hit, {}, index=index, tool_cache=tools)
        elapsed = time.perf_counter() - started
        # Restored digests are already in the build's index: product records read no bytes.
        monkeypatch.setattr(build.build_products, 'file_digest', lambda *a: pytest.fail('restored output was reread'))
        assert build.build_products.records(received[0], hasher=index.digest)
    assert len(list((receiver.out / 'tree').glob('lod*.bin'))) == 200
    print(f'201-file action restore in process: {elapsed * 1000:.0f} ms')
    # The regression this guards against took seconds to minutes per hit (a guarded child and
    # broker admission); shared CI runners vary by tens of milliseconds, so the bound is 1 s.
    assert elapsed < 1.0, f'{elapsed:.3f} s for one 201-file action restore'


def test_source_scope_inventory_remains_exact_without_rebuilding_shared_ancestor_chains(monkeypatch):
    sources = {Path('/repo/game/source/deep') / ('file' + str(i) + '.py') for i in range(200)}
    sources.update((Path('/other/file.py'), Path('/repo/game/source/deep/../literal.py')))
    expected = {ancestor for path in sources for ancestor in (path, *path.parents)}
    original = Path.parent.fget
    calls = []
    def parent(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'parent', property(parent))
    assert actions.source_scopes(iter(sources)) == expected
    assert len(calls) == len(expected)
