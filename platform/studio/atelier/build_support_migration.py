"""Preserve complete local products across a reviewed standard-library support extraction.

This changes compatibility metadata only, not the original produced action certificate.
"""
from pathlib import Path

from . import build_cache, build_products
from .atomic_files import atomic_json

PREVIOUS = {'build_cache.py': 'a4145b3ea37d55919740f024c6be71ded4955260d67311a3e8fbfc45d60c1f2d', 'build_inputs.py': '1372231a341b450130c5e1e11c715e27c05cf62b0e9e9aea858ab9b02bc9fa9e'}
CURRENT = {'build_cache.py': '4515c14043535aa1ad895ceccac4e2d2e677af4bd4bb68f6b3b252441835e5b3', 'build_inputs.py': '7f140159d1a4ce9a51eddd5625439c9ff350db3b19beec0d3dc28382ccdf72d4', 'atomic_files.py': '39163e0c3284ecd931b4f182cfded79cd275046de71003d17cdd6134f5533e9c', 'source_imports.py': '3e0e40ff742ee08354e2276ca385b99d1085e033153fc6416d057ed00e245eee'}
ADDED = {'atomic_files.py', 'source_imports.py'}
# The source tool support before the extraction; the current context no longer hashes identity code.
LEGACY_SUPPORT = ('build_source.py', 'build_inputs.py', 'build_products.py', 'build_cache.py', 'build_hashes.py',
                  'paths.py', 'build_deferred.py', 'safety/process.py', 'safety/exec_gate.py')


def legacy_support():
    from atelier.harness.safety import process
    safety, studio = Path(process.__file__).parent, Path(__file__).parent
    return {name: build_products.file_digest(safety / name.removeprefix('safety/') if name.startswith('safety/')
                                             else studio / name) for name in LEGACY_SUPPORT}


def previous_context(ctx, step, current_identity):
    """All installed tool bytes stay current; only the reviewed support extraction differs."""
    if any(build_products.file_digest(Path(__file__).with_name(name)) != digest
           for name, digest in CURRENT.items()):
        return None
    cache = ctx.__dict__.setdefault('support_migration_contexts', {})
    if current_identity not in cache:
        from .build_audit import tool_context as audited_context
        tool_context = audited_context if step.audit else build_cache.tool_context
        value = tool_context(step, build_products.file_digest, cache=ctx.__dict__.setdefault('support_migration_tools', {}))
        if build_products.identity(value) != current_identity or not isinstance(value.get('support'), dict):
            return None
        support = {**legacy_support(), **PREVIOUS}
        legacy = {k: v for k, v in value.items() if k != 'identity_schema'}
        cache[current_identity] = {**legacy, 'support': support}
    return cache[current_identity]


def migrate(ctx, step, current, input_state, previous, done, *, echo=print):
    """@cc [owner:fontanierh,label:correctness] preserve-reviewed-support-equivalence
    Migration MUST match this reviewed old/current support pair and the complete previous
    fingerprint, including installed tool bytes, current source, commands, dependencies and
    output declarations. Every named product MUST match its original complete inventory.
    A changed tool, data, worker or unsupported pair MUST miss. Only compatibility metadata
    MAY be updated; original action/tool provenance MUST NOT be rewritten or published anew.
    """
    if not previous or previous.get('fingerprint') == current or not step.products or not input_state.get('tools'):
        return previous
    from .build import Python, Blender, fingerprint, outputs_present, result
    from .checkpoint_actions import local_incremental, declared, label, snapshot, inventory_identity
    from .native_protocol import ReadStore, context
    if any(type(command) not in (Python, Blender) for command in step.commands):
        return previous
    old_context = previous_context(ctx, step, input_state['tools'])
    if old_context is None:
        return previous
    old_tools = build_products.identity(old_context)
    old_state = previous.get('input_state')
    if not isinstance(old_state, dict) or old_state.get('tools') != old_tools:
        return previous
    substitutions = [{}]
    if step.batch:
        from .build_batch_migration import previous_host, RECEIPT_HOST_SHA256
        host = Path(__file__).with_name('build_batches.py')
        raw = previous_host(ctx)
        reserved = {'ATELIER_BUILD_TASK', 'ATELIER_BUILD_GAME', 'ATELIER_BUILD_SCRIPT', 'ATELIER_MESH_REUSE_NONCE', 'ATELIER_BUILD_PRIOR_STAMP'}
        env_override = any(reserved.intersection(dict(getattr(command, 'env', ()))) for command in step.commands)
        if raw is not None and not env_override and build_products.file_digest(host) == RECEIPT_HOST_SHA256:
            substitutions.append({host: raw})
    old = previous['fingerprint']
    if not any(fingerprint(step, done, _input_bytes=inputs, _tool_identity=old_tools) == old for inputs in substitutions):
        return previous
    if (not outputs_present(step) or not build_products.valid_records(step, previous.get('products', {}))
            or fingerprint(step, done) != current):
        return previous
    if previous.get('checkpoint_key'):
        native = context(ctx)
        tool = {name: value for name, value in native.items() if name in ('system', 'machine')}
        tool['source_tools'] = {name: value for name, value in old_context.items() if name != 'audit_installation'}
        expected = build_products.identity(dict(schema=1, game=ctx.game, task=step.name,
            fingerprint=old, outputs=[label(ctx, path) for path in declared(ctx, step)], tool=tool))
        if previous['checkpoint_key'] != expected:
            return previous
        try:
            declarations, files = snapshot(ctx, step, ReadStore(ctx.game), save_blobs=False)
        except (OSError, ValueError, RuntimeError):
            return previous
        if inventory_identity(declarations, files) != previous.get('checkpoint_inventory'):
            return previous
    else:
        covered = [path for product in step.products for path in product.roots()]
        if (not local_incremental(ctx, step, old, previous) or any(
                not any(path == root or root in path.parents for root in covered)
                for path in [*declared(ctx, step), *step.outputs])):
            return previous
    migrated = dict(previous, fingerprint=current, input_state=input_state,
        checkpoint_incremental_context=getattr(ctx, 'checkpoint_observed_context', None),
        checkpoint_migrated_from=old, checkpoint_migration_result=result(step, old, previous))
    migrated.pop('checkpoint_key', None)
    migrated.pop('checkpoint_inventory', None)
    atomic_json(ctx.stamps / (step.name + '.json'), migrated)
    echo(step.name + ': preserved complete products after verified source-support extraction')
    return migrated


def cached_key(ctx, step, current, input_state, done):
    """@cc [owner:fontanierh,label:correctness] portable-support-equivalence-lookup
    Old portable lookup MUST reproduce the full current recipe with only the reviewed
    support extraction substituted, retain installed tool identities, and cover every
    declared output by verified portable products. Restoration MUST verify bytes through
    the ordinary cache journal and remain compatibility-only, without a new tool certificate.
    """
    if not step.cache or not input_state.get('tools'):
        return None
    from .checkpoint_actions import declared
    covered = [path for product in step.products for path in product.roots()]
    if any(not any(path == root or root in path.parents for root in covered)
           for path in [*declared(ctx, step), *step.outputs]):
        return None
    from .build import fingerprint
    old_context = previous_context(ctx, step, input_state['tools'])
    if old_context is None:
        return None
    key = fingerprint(step, done, _tool_identity=build_products.identity(old_context))
    return key if key != current and build_cache.Store().action(key).is_file() else None
