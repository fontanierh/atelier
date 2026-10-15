"""Local unsigned portable snapshots: selected graph closure and explicit cache retention roots.

This is local selection/accounting, never a publisher attestation or a remote bundle importer.
No command in this module executes an action or installs native packages.
"""
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path

from . import artifact_bundle as bundle, build_cache, build_products

MAX_ACTIONS = 256
MAX_SNAPSHOTS = 512


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read(path):
    with ExitStack() as stack:
        return bundle._read_json(stack, path, bundle.MAX_MANIFEST)


def _path(store, key, suffix='.json'):
    if type(key) is not str or not build_cache.DIGEST.fullmatch(key):
        raise ValueError('Invalid snapshot identity')
    # Readers use O_NOFOLLOW. Explicit removal may unlink an invalid link without following it.
    return store.path('snapshots') / (key + suffix)


def _names(value):
    if (type(value) is not list or len(value) > MAX_ACTIONS
            or any(type(name) is not str or not bundle.IDENTIFIER.fullmatch(name) for name in value)
            or len(set(value)) != len(value)):
        raise ValueError('Invalid snapshot graph names')
    return value


def _validate(value):
    bundle._fields(value, ('schema', 'authority', 'game', 'roots', 'audience', 'actions'))
    if (type(value['schema']) is not int or value['schema'] != 1 or value['authority'] != 'local-unsigned'
            or type(value['game']) is not str or not bundle.IDENTIFIER.fullmatch(value['game'])
            or value['audience'] not in ('private', 'public') or not _names(value['roots'])
            or type(value['actions']) is not list or not 1 <= len(value['actions']) <= MAX_ACTIONS):
        raise ValueError('Invalid local snapshot manifest')
    actions, owners, blobs, logical = {}, {}, {}, 0
    for action in value['actions']:
        bundle._fields(action, ('step', 'key', 'products', 'needs', 'after', 'reads', 'references', 'redistribution'))
        name = action['step']
        if type(name) is not str or not bundle.IDENTIFIER.fullmatch(name) or name in actions:
            raise ValueError('Duplicate or invalid snapshot owner')
        actions[name] = action
        if type(action['key']) is not str or not build_cache.DIGEST.fullmatch(action['key']):
            raise ValueError('Invalid snapshot action key')
        for field in ('needs', 'after', 'reads', 'references'):
            _names(action[field])
        _, found, size, _ = bundle._records(_entry(action))
        logical += size
        if logical > bundle.MAX_BYTES:
            raise ValueError('Snapshot logical bytes exceed limit')
        for digest, size in found.items():
            if digest in blobs and blobs[digest] != size:
                raise ValueError('Contradictory snapshot blob sizes')
            blobs[digest] = size
        grants = action['redistribution']
        if type(grants) is not dict or set(grants) != set(action['products']):
            raise ValueError('Snapshot requires a grant for every product')
        for product, grant in grants.items():
            if product in owners:
                raise ValueError('Duplicate snapshot product owner')
            owners[product] = name
            bundle._fields(grant, ('permission', 'grant'))
            if (grant['permission'] not in ('private', 'public') or type(grant['grant']) is not str
                    or not bundle.IDENTIFIER.fullmatch(grant['grant'])
                    or value['audience'] == 'public' and grant['permission'] != 'public'):
                raise ValueError('Snapshot redistribution policy refuses selection')
    chosen, completed = set(), set()
    def visit(name):
        if name not in actions:
            raise ValueError('Snapshot dependency is missing')
        if name in chosen:
            return
        chosen.add(name)
        action = actions[name]
        for dependency in [*action['needs'], *action['after']]:
            visit(dependency)
        for product in [*action['reads'], *action['references']]:
            if product not in owners:
                raise ValueError('Snapshot referenced product is missing')
            visit(owners[product])
    for root in value['roots']:
        visit(root)
    if chosen != set(actions):
        raise ValueError('Snapshot contains actions outside the selected closure')
    for action in value['actions']:
        prerequisites = {*action['needs'], *action['after'], *(owners[p] for p in action['reads'])}
        if not prerequisites <= completed:
            raise ValueError('Snapshot has invalid dependency order')
        completed.add(action['step'])
    return blobs


def _entry(action):
    return dict(schema=1, key=action['key'], products=action['products'])


def _verify(store, value):
    blobs = _validate(value)
    for action in value['actions']:
        path = store.action(action['key'])
        conflict = path.with_suffix('.conflict.json')
        if (conflict.exists() or conflict.is_symlink()
                or bundle._canonical(_read(path)) != bundle._canonical(_entry(action))):
            raise ValueError('Snapshot action is missing, conflicting or changed')
    for digest, size in blobs.items():
        path = store.blob(digest)
        with ExitStack() as stack:
            fd, info = bundle._open_file(stack, path)
            if info.st_size != size:
                raise ValueError('Snapshot blob size differs')
            hasher = hashlib.sha256()
            remaining = size
            while remaining:
                data = os.read(fd, min(65536, remaining))
                if not data:
                    raise ValueError('Snapshot blob is incomplete')
                hasher.update(data)
                remaining -= len(data)
            if (hasher.hexdigest() != digest or os.read(fd, 1)
                    or bundle._signature(info) != bundle._signature(os.fstat(fd))):
                raise ValueError('Snapshot blob bytes differ')
    return blobs


def load(store, key, *, verify=True):
    value = _read(_path(store, key))
    _validate(value)
    if build_products.identity(value) != key:
        raise ValueError('Snapshot content identity differs')
    if verify:
        _verify(store, value)
    return value


def retention(store):
    """@cc [owner:fontanierh,label:correctness] snapshot-retention-fails-closed
    GC MUST validate every local snapshot and every pinned member action and blob before deleting
    anything. Invalid manifests, dangling pins and missing/conflicting/corrupt retained members MUST
    refuse GC. Unpinned valid manifests MAY outlive evicted members; removal MUST remain explicit.

    Caller holds the exclusive store lock for mutations, including the whole GC decision.
    """
    result, invalid, roots = [], [], set()
    directory = store.path('snapshots')
    keys = set()
    if directory.exists():
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries, 1):
                if count > MAX_SNAPSHOTS * 3:
                    raise ValueError('Snapshot directory exceeds enumeration limit')
                path = Path(entry.name)
                if path.suffix in ('.json', '.pin'):
                    keys.add(path.stem)
                    if len(keys) > MAX_SNAPSHOTS:
                        raise ValueError('Snapshot count exceeds limit')
    for key in sorted(keys):
        try:
            marker = _path(store, key, '.pin')
            pinned = marker.exists() or marker.is_symlink()
            if pinned and bundle._canonical(_read(marker)) != bundle._canonical(dict(schema=1, snapshot=key)):
                raise ValueError('Invalid snapshot pin')
            value = load(store, key, verify=pinned)
            members = [action['key'] for action in value['actions']]
            if pinned:
                roots.update(members)
            result.append(dict(key=key, game=value['game'], roots=value['roots'], audience=value['audience'],
                               pinned=pinned, actions=members))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            invalid.append(key)
    return dict(snapshots=result, invalid_snapshots=invalid, snapshot_actions=sorted(roots))


def _selection(ctx, wanted):
    from . import build
    graph = build_products.Graph(build.load_recipe(ctx.game).steps(ctx))
    plan = graph.select(wanted)
    roots = [step.name for step in graph.steps if any(step.name == name or
             step.name.startswith(name + '.') and not step.explicit for name in wanted)]
    if not roots or len(plan) > MAX_ACTIONS:
        raise ValueError('Snapshot requires explicit portable targets within the action limit')
    for step in plan:
        if not step.cache or step.batch or step.verify is not None or not step.products:
            raise ValueError(f'{step.name}: snapshot closure requires portable cache-enabled owners')
        build_cache.roots(ctx, step)
    return plan, roots


def _declaration(step):
    return dict(step=step.name, needs=list(step.needs), after=list(step.after), reads=list(step.reads),
                references=list(step.references))


def create(game, wanted, grants, *, store=None, public=False):
    """Select only an already current verified closure, without executing or fetching any action."""
    from . import build, build_snapshot
    from .artifact_publisher import _grants, _stamp
    store = store or build_cache.Store()
    ctx = build.Context(game, create=False)
    build_snapshot.require_complete(ctx.out, game=game)
    def observe():
        plan, roots = _selection(ctx, wanted)
        done, actions, tools = {}, [], {}
        for step in plan:
            stamp = _stamp(ctx.stamps / (step.name + '.json'))
            key, state = build.fingerprint_state(step, done, tool_cache=tools)
            products = build_products.records(step)
            if (stamp.get('touched') or stamp.get('fingerprint') != key
                    or build_products.identity(stamp.get('input_state')) != build_products.identity(state)
                    or stamp.get('products') != products or not build.outputs_present(step)
                    or build.missing_product_inputs(step)
                    or (ctx.stamps / (step.name + '.restore.json')).exists()):
                raise ValueError(f'{step.name}: current complete successful products required')
            actions.append(dict(**_declaration(step), key=key, products=products,
                                redistribution=_grants(Path(grants), game, step)))
            done[step.name] = key
            build_products.feed_results(done, products)
        return dict(schema=1, authority='local-unsigned', game=game, roots=roots,
                    audience='public' if public else 'private', actions=actions)
    with store.lock(exclusive=True):
        value = observe()
        _verify(store, value)
        data = bundle._canonical(value)
        if len(data) > bundle.MAX_MANIFEST:
            raise ValueError('Snapshot manifest exceeds limit')
        if observe() != value:
            raise ValueError('Snapshot inputs or products changed during verification')
        key = build_products.identity(value)
        target = _path(store, key)
        retained = retention(store)
        if retained['invalid_snapshots'] or (not target.exists() and len(retained['snapshots']) >= MAX_SNAPSHOTS):
            raise ValueError('Repair/remove invalid snapshots or free snapshot capacity before creation')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if load(store, key) != value:
                raise ValueError('Snapshot identity conflict')
        else:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                target.unlink(missing_ok=True)
                raise
        build_cache.atomic_json(_path(store, key, '.pin'), dict(schema=1, snapshot=key))
        _sync(target.parent)
    return dict(snapshot=key, pinned=True, authority='local-unsigned', actions=len(value['actions']))


def pin(store, key, enabled):
    with store.lock(exclusive=True):
        marker = _path(store, key, '.pin')
        if enabled:
            load(store, key)
            build_cache.atomic_json(marker, dict(schema=1, snapshot=key))
        else:
            marker.unlink(missing_ok=True)
        if marker.parent.exists():
            _sync(marker.parent)


def remove(store, key):
    with store.lock(exclusive=True):
        marker = _path(store, key, '.pin')
        if marker.exists() or marker.is_symlink():
            raise ValueError('Unpin the snapshot explicitly before removing it')
        _path(store, key).unlink(missing_ok=True)
        if marker.parent.exists():
            _sync(marker.parent)


def restore(game, key, *, store=None):
    """@cc [owner:fontanierh,label:correctness] portable-snapshot-restore
    Restore MUST validate the full selected recipe/key closure and all CAS bytes before mutation.
    Only declared portable outputs MAY be installed, as independent copies. Every selected stamp
    MUST be removed and journalled before replacement; success MUST require fresh inputs and all
    installed inventories. No action execution or native package installation MAY occur here.
    """
    from . import build, build_snapshot
    import time
    store = store or build_cache.Store()
    ctx = build.Context(game, create=False)
    build_snapshot.require_complete(ctx.out, game=game)
    with store.lock(exclusive=True):
        value = load(store, key)
        if value['game'] != game:
            raise ValueError('Snapshot belongs to another game')
        plan, roots = _selection(ctx, value['roots'])
        if roots != value['roots'] or [s.name for s in plan] != [a['step'] for a in value['actions']]:
            raise ValueError('Receiving snapshot closure differs')
        def check(installed=False):
            fresh, fresh_roots = _selection(ctx, value['roots'])
            if fresh_roots != roots or [s.name for s in fresh] != [s.name for s in plan]:
                raise ValueError('Receiving snapshot closure changed during restoration')
            done, states, tools = {}, {}, {}
            for step, action in zip(fresh, value['actions'], strict=True):
                fingerprint, state = build.fingerprint_state(step, done, tool_cache=tools)
                if fingerprint != action['key'] or any(action[k] != v for k, v in _declaration(step).items()):
                    raise ValueError('Receiving action inputs or graph differ from snapshot')
                if installed and (build_products.records(step) != action['products']
                                  or not build.outputs_present(step) or build.missing_product_inputs(step)):
                    raise ValueError('Restored snapshot products or inputs differ')
                states[step.name] = state
                done[step.name] = fingerprint
                build_products.feed_results(done, action['products'])
            return states
        check()
        ctx.stamps.mkdir(parents=True, exist_ok=True)
        try:
            for step, action in zip(plan, value['actions'], strict=True):
                (ctx.stamps / (step.name + '.json')).unlink(missing_ok=True)
                build_cache.atomic_json(ctx.stamps / (step.name + '.restore.json'), dict(schema=1, key=action['key']))
            for step, action in zip(plan, value['actions'], strict=True):
                if store._restore(ctx, step, action['key']) != action['products']:
                    raise ValueError('Snapshot member could not be restored')
            states = check(installed=True)
            for step, action in zip(plan, value['actions'], strict=True):
                build_cache.atomic_json(ctx.stamps / (step.name + '.json'),
                    dict(fingerprint=action['key'], input_state=states[step.name], products=action['products'],
                         restored_from=action['key'], snapshot=key, time=time.time(), commands=[]))
            check(installed=True)
            for step in plan:
                (ctx.stamps / (step.name + '.restore.json')).unlink()
        except BaseException:
            for step in plan:
                (ctx.stamps / (step.name + '.json')).unlink(missing_ok=True)
            raise
    return dict(snapshot=key, restored=True, actions=len(plan), executed=0)
