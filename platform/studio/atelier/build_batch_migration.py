"""Preserve valid warm results across one reviewed host receipt-plumbing change.

This is compatibility metadata, never a way to certify outputs under new producer tools.
The worker, commands, data, dependencies and output declarations are all checked normally.
"""
import hashlib
from pathlib import Path
import subprocess

from . import build_products, paths
from .build_cache import atomic_json

# Immutable Git blob, independent of the producer/receiver commit. No fetch is requested.
PREVIOUS_BLOB = '3da2f4a72a775615245d4c1e143289ad3c0951fb'
PREVIOUS_SHA256 = '2c6ee6bcdc07e66c2cd8271f1c01b7a8009f2ec93ceb68f194c5dea96e2ce1e9'
RECEIPT_HOST_SHA256 = '1b333bc9cf3d8ecadd6932e0b7ec8cf3d2188cc88e64a77fbc01f942772e4cda'


def previous_host(ctx):
    if 'previous_batch_host' not in ctx.__dict__:
        result = subprocess.run(['git', '--no-optional-locks', '-C', str(paths.REPO),
                                 'cat-file', 'blob', PREVIOUS_BLOB], capture_output=True, timeout=10)
        ctx.previous_batch_host = (result.stdout if result.returncode == 0 and
                                  hashlib.sha256(result.stdout).hexdigest() == PREVIOUS_SHA256 else None)
    return ctx.previous_batch_host


def migrate(ctx, step, current, input_state, previous, done, *, echo=print):
    """@cc [owner:fontanierh,label:correctness] preserve-batch-receipt-equivalence
    Migration MUST apply only to this reviewed predecessor/current host pair and reproduce the
    entire previous fingerprint using current inputs, tools, worker, commands, products and
    dependencies, substituting only the immutable predecessor host bytes. Existing outputs
    and prior certified/compatible proof MUST still match. The new stamp MUST remain
    compatibility-only and preserve its dependency result. Unknown proof MUST be a normal miss.
    """
    if not step.batch or not previous or previous.get('fingerprint') == current:
        return previous
    from .build import fingerprint, outputs_present, result
    from .checkpoint_actions import certified, local_incremental, declared
    if not step.products and not declared(ctx, step):
        return previous
    reserved = {'ATELIER_BUILD_TASK', 'ATELIER_BUILD_GAME', 'ATELIER_BUILD_SCRIPT', 'ATELIER_MESH_REUSE_NONCE', 'ATELIER_BUILD_PRIOR_STAMP'}
    if any(reserved.intersection(dict(getattr(command, 'env', ()))) for command in step.commands):
        return previous
    host = Path(__file__).with_name('build_batches.py')
    if build_products.file_digest(host) != RECEIPT_HOST_SHA256:
        return previous
    raw = previous_host(ctx)
    if raw is None:
        return previous
    old_key = fingerprint(step, done, _input_bytes={host: raw})
    if (old_key != previous.get('fingerprint') or not outputs_present(step)
            or (step.products and not build_products.valid_records(step, previous.get('products', {})))
            or not (certified(ctx, step, old_key, previous) or local_incremental(ctx, step, old_key, previous))):
        return previous
    if fingerprint(step, done) != current:
        return previous
    migrated = dict(previous, fingerprint=current, input_state=input_state,
                    checkpoint_incremental_context=getattr(ctx, 'checkpoint_observed_context', None),
                    checkpoint_migrated_from=old_key, checkpoint_migration_result=result(step, old_key, previous))
    migrated.pop('checkpoint_key', None)
    migrated.pop('checkpoint_inventory', None)
    atomic_json(ctx.stamps / (step.name + '.json'), migrated)
    echo(step.name + ': preserved existing result after verified host receipt migration')
    return migrated
