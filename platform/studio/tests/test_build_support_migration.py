"""Support relocation cannot force exports or conceal actual source/tool changes."""
from dataclasses import replace
from pathlib import Path
import json

import pytest

from atelier import build, build_cache, build_products, build_support_migration as migration, checkpoint_actions as actions
from test_checkpoints import fixture


@pytest.fixture
def previous(fixture, monkeypatch):
    # Exercise a synthetic reviewed pair in this unit fixture. Production keeps
    # its exact pinned pair and refuses later support changes, including the
    # runtime-copy extraction; tests must not widen that historical allowance.
    support = Path(migration.__file__).parent
    monkeypatch.setattr(migration, 'CURRENT', {name: build_products.file_digest(support / name)
        for name in (*migration.CURRENT, 'file_copy.py')})
    ctx, steps = fixture.checkout('support-producer')
    steps[0] = replace(steps[0], cache=True)
    fixture.produce(ctx, steps)
    step = steps[0]
    current, state = build.fingerprint_state(step, {})
    old_context = migration.previous_context(ctx, step, state['tools'])
    old_tools = build_products.identity(old_context)
    old, old_state = build.fingerprint_state(step, {}, _tool_identity=old_tools)
    stamp = json.loads((ctx.stamps / 'tree.json').read_text())
    with monkeypatch.context() as patch:
        patch.setattr(build_cache, 'tool_context', lambda *a, **k: old_context)
        old_action = actions.certificate_key(ctx, step, old)
    stamp.update(fingerprint=old, input_state=old_state, checkpoint_key=old_action)
    return ctx, step, stamp


def test_unchanged_complete_products_preserve_dependency_result(previous):
    ctx, step, old = previous
    current, state = build.fingerprint_state(step, {})
    before = step.outputs[0].read_bytes()
    saved = migration.migrate(ctx, step, current, state, old, {}, echo=lambda _: None)
    assert current != old['fingerprint'] and saved['fingerprint'] == current
    assert build.result(step, current, saved) == build.result(step, old['fingerprint'], old)
    assert 'checkpoint_key' not in saved and 'checkpoint_inventory' not in saved
    assert step.outputs[0].read_bytes() == before


@pytest.mark.parametrize('change', ['source', 'output', 'command', 'tool', 'future-support', 'copy-support', 'missing-output', 'missing-products'])
def test_source_tool_or_output_changes_do_not_migrate(previous, monkeypatch, change):
    ctx, step, old = previous
    if change == 'source': step.inputs[0].write_text('changed_geometry')
    elif change == 'output': step.outputs[0].write_bytes(b'changed geometry')
    elif change == 'missing-output': step.outputs[0].unlink()
    elif change == 'command': step.commands[0].args = ('changed setting',)
    elif change == 'tool': old['input_state']['tools'] = 'e' * 64
    elif change == 'future-support': monkeypatch.setitem(migration.CURRENT, 'source_imports.py', 'e' * 64)
    elif change == 'copy-support': monkeypatch.setitem(migration.CURRENT, 'file_copy.py', 'e' * 64)
    else: old.pop('products')
    current, state = build.fingerprint_state(step, {})
    assert migration.migrate(ctx, step, current, state, old, {}, echo=lambda _: None) is old


@pytest.mark.parametrize('change', ['tamper', 'missing'])
def test_extra_declared_output_requires_its_original_byte_inventory(previous, monkeypatch, change):
    ctx, step, old = previous
    extra = ctx.out / 'extra.bin'; extra.write_bytes(b'original auxiliary output')
    step.checkpoint_outputs = (extra,)
    _, state = build.fingerprint_state(step, {})
    old_context = migration.previous_context(ctx, step, state['tools'])
    with monkeypatch.context() as patch:
        patch.setattr(build_cache, 'tool_context', lambda *a, **k: old_context)
        old['checkpoint_key'] = actions.certificate_key(ctx, step, old['fingerprint'])
    declarations, files = actions.snapshot(ctx, step, __import__('atelier.native_protocol', fromlist=['ReadStore']).ReadStore(ctx.game), save_blobs=False)
    old['checkpoint_inventory'] = actions.inventory_identity(declarations, files)
    if change == 'tamper': extra.write_bytes(b'corrupted auxiliary output')
    else: extra.unlink()
    current, state = build.fingerprint_state(step, {})
    assert migration.migrate(ctx, step, current, state, old, {}, echo=lambda _: None) is old


@pytest.mark.parametrize('reserved', [False, True])
def test_composed_host_migration_refuses_changed_reserved_environment(previous, monkeypatch, reserved):
    from pathlib import Path
    from atelier import build_batch_migration as host
    ctx, step, old = previous
    step.batch = build.Batch('fixture')
    if reserved:
        step.commands[0].env = (('ATELIER_BUILD_GAME', 'other-owner'),)
    raw = b'# prior host fixture\n'
    monkeypatch.setattr(host, 'previous_host', lambda _: raw)
    # Select the synthetic current/predecessor pair only in this unit fixture.
    monkeypatch.setattr(host, 'RECEIPT_HOST_SHA256', build_products.file_digest(Path(host.__file__).with_name('build_batches.py')))
    current, state = build.fingerprint_state(step, {})
    old_context = migration.previous_context(ctx, step, state['tools'])
    old_tools = build_products.identity(old_context)
    old_key, old_state = build.fingerprint_state(step, {}, _tool_identity=old_tools,
        _input_bytes={Path(build.__file__).with_name('build_batches.py'): raw})
    with monkeypatch.context() as patch:
        patch.setattr(build_cache, 'tool_context', lambda *a, **k: old_context)
        old['checkpoint_key'] = actions.certificate_key(ctx, step, old_key)
    old.update(fingerprint=old_key, input_state=old_state)
    result = migration.migrate(ctx, step, current, state, old, {}, echo=lambda _: None)
    assert (result is old) == reserved


def test_normal_build_restores_verified_old_portable_result_without_new_tool_certificate(previous, monkeypatch):
    from types import SimpleNamespace
    from atelier import build_checkpoints
    ctx, step, old = previous
    store = build_cache.Store()
    store.publish(ctx, step, old['fingerprint'], build_products.records(step))
    step.outputs[0].unlink(); (ctx.stamps / (step.name + '.json')).unlink()
    monkeypatch.setattr(build, 'Context', lambda *a, **k: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda _: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda _: None)
    monkeypatch.setattr(build, 'run_command', lambda *a, **k: pytest.fail('unchanged cached export was executed'))
    assert build.build(ctx.game, [step.name], echo=lambda _: None) == 0
    restored = json.loads((ctx.stamps / (step.name + '.json')).read_text())
    assert step.outputs[0].read_bytes() == b'tree'
    assert restored['restore_source'] == 'compatible-local'
    assert restored['restored_from'] == old['fingerprint'] and 'checkpoint_key' not in restored
    assert not store.action(restored['fingerprint']).exists()


def test_portable_fallback_cannot_certify_extra_checkpoint_output(previous):
    ctx, step, old = previous
    build_cache.Store().publish(ctx, step, old['fingerprint'], build_products.records(step))
    extra = ctx.out / 'unproved.bin'; extra.write_bytes(b'not in the portable product')
    step.checkpoint_outputs = (extra,)
    current, state = build.fingerprint_state(step, {})
    assert migration.cached_key(ctx, step, current, state, {}) is None
