"""A host-only receipt migration must reproduce the full prior action, never bless new data."""
from pathlib import Path

import pytest

from atelier import build, build_products, build_batch_migration as migration, checkpoint_actions as actions, checkpoint_store as cp
from test_checkpoints import fixture


@pytest.fixture
def previous(fixture, monkeypatch):
    ctx, steps = fixture.checkout('producer')
    step = steps[0]
    step.batch = build.Batch('trees')
    fixture.produce(ctx, steps)
    # A synthetic eligible host pair tests the migration mechanism. Production
    # retains its immutable guard and refuses this new batching implementation.
    monkeypatch.setattr(migration, 'RECEIPT_HOST_SHA256',
                        build_products.file_digest(Path(build.__file__).with_name('build_batches.py')))
    raw = b'# synthetic immutable predecessor host\n'
    monkeypatch.setattr(migration, 'previous_host', lambda _: raw)
    host = Path(build.__file__).with_name('build_batches.py')
    old_key, state = build.fingerprint_state(step, {}, _input_bytes={host: raw})
    stamp = cp.read_json(ctx.stamps / 'tree.json')
    stamp.update(fingerprint=old_key, input_state=state, checkpoint_key=actions.certificate_key(ctx, step, old_key))
    return ctx, step, stamp


def test_receipt_migration_preserves_outputs_and_dependency_token(previous):
    ctx, step, old = previous
    current, state = build.fingerprint_state(step, {})
    output = step.outputs[0].read_bytes()
    migrated = migration.migrate(ctx, step, current, state, old, {}, echo=lambda _: None)
    assert current != old['fingerprint'] and migrated['fingerprint'] == current
    assert build.result(step, current, migrated) == build.result(step, old['fingerprint'], old)
    assert 'checkpoint_key' not in migrated and 'checkpoint_inventory' not in migrated
    assert step.outputs[0].read_bytes() == output


@pytest.mark.parametrize('change', ['source', 'output', 'commands', 'missing-history', 'future-host'])
def test_migration_does_not_hide_actual_changes(previous, monkeypatch, change):
    ctx, step, old = previous
    if change == 'source':
        step.inputs[0].write_text('changed geometry')
    elif change == 'output':
        step.outputs[0].write_bytes(b'corrupt')
    elif change == 'commands':
        step.commands[0].args = ('new setting',)
    elif change == 'missing-history':
        monkeypatch.setattr(migration, 'previous_host', lambda _: None)
    else:
        monkeypatch.setattr(migration, 'RECEIPT_HOST_SHA256', 'f' * 64)
    current, state = build.fingerprint_state(step, {})
    assert migration.migrate(ctx, step, current, state, old, {}, echo=lambda _: None) is old
