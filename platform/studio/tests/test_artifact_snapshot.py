"""Real portable sandbox snapshots and isolated CAS retention; no native tools or network."""
import json
import shutil

import pytest

from atelier import artifact_snapshot as snapshots, build, build_cache, build_products, cache_admin, cli, paths
from test_sandbox_spatial import demo  # noqa: F401 - real sandbox, real audited Python actions, isolated cache


@pytest.fixture
def package(demo, tmp_path, monkeypatch):
    d = demo
    for name in ('ATELIER_ARTIFACT_URL', 'ATELIER_ARTIFACT_TRUST'):
        monkeypatch.delenv(name, raising=False)
    assert d.run('world.placements', 'spatial.tile.west') == 0, d.messages
    ctx = build.Context('sandbox', create=False)
    graph = build_products.Graph(build.load_recipe('sandbox').steps(ctx))
    policy = {'schema': 1, 'actions': {f'sandbox/{step.name}': {
        product.name: {'permission': 'public', 'grant': 'fixture-redistribution-v1'} for product in step.products}
        for step in graph.steps if step.products}}
    grants = tmp_path / 'grants.json'
    grants.write_text(json.dumps(policy))
    d.store, d.grants, d.policy = build_cache.Store(), grants, policy
    d.create = lambda **kw: snapshots.create('sandbox', ['world.placements', 'spatial.tile.west'], grants,
                                            store=d.store, **kw)
    return d


def test_cli_selects_complete_real_closure_and_restores_without_execution(package, monkeypatch, capsys):
    d = package
    assert cli.main(['cache', 'snapshot-create', 'sandbox', 'world.placements', 'spatial.tile.west',
                     '--grants', str(d.grants), '--public']) == 0
    receipt = json.loads(capsys.readouterr().out)
    key = receipt['snapshot']
    assert receipt['pinned'] and receipt['authority'] == 'local-unsigned'
    value = snapshots.load(d.store, key)
    assert [a['step'] for a in value['actions']] == [
        'world.block', 'world.placements', 'spatial.source.west', 'spatial.tile.west']
    assert value['actions'][1]['references'] == ['block.shape']
    assert value['actions'][-1]['reads'] == ['spatial.west']
    assert str(d.repo) not in json.dumps(value)
    assert d.create(public=True)['snapshot'] == key  # Immutable deterministic selection, no timestamps.
    assert d.store.path('snapshots', key + '.json').stat().st_mode & 0o222 == 0
    expected = {a['step']: a['products'] for a in value['actions']}
    shutil.rmtree(d.output)
    monkeypatch.setattr(build, 'run_command', lambda *a, **k: pytest.fail('snapshot ran an action'))
    assert cli.main(['cache', 'snapshot-restore', key, 'sandbox']) == 0
    assert json.loads(capsys.readouterr().out)['executed'] == 0
    ctx = build.Context('sandbox', create=False)
    graph = build_products.Graph(build.load_recipe('sandbox').steps(ctx))
    for step in graph.select(value['roots']):
        assert build_products.records(step) == expected[step.name]
        assert not (ctx.stamps / (step.name + '.restore.json')).exists()
    assert d.run('world.placements', 'spatial.tile.west') == 0 and not d.calls
    assert cli.main(['cache', 'snapshot-show', key]) == 0
    assert json.loads(capsys.readouterr().out)['authority'] == 'local-unsigned'


def test_pinned_snapshot_roots_all_actions_and_blobs_until_explicit_unpin(package, capsys):
    d = package
    key = d.create()['snapshot']
    value = snapshots.load(d.store, key)
    member_keys = {a['key'] for a in value['actions']}
    assert cli.main(['cache', 'status']) == 0
    state = json.loads(capsys.readouterr().out)
    assert set(state['snapshot_actions']) == member_keys
    assert all(a['snapshot_retained'] for a in state['actions'])
    assert cache_admin.prune(d.store, max_bytes=0, max_age_days=0)['removed_actions'] == []
    with pytest.raises(ValueError, match='Unpin'):
        cache_admin.forget(d.store, next(iter(member_keys)))
    assert cli.main(['cache', 'snapshot-remove', key]) == 1
    capsys.readouterr()
    assert cli.main(['cache', 'snapshot-unpin', key]) == 0
    result = cache_admin.prune(d.store, max_bytes=0, max_age_days=0)
    assert set(result['removed_actions']) == member_keys and result['remaining_bytes'] == 0
    assert cli.main(['cache', 'snapshot-show', key, '--metadata-only']) == 0
    capsys.readouterr()
    assert cli.main(['cache', 'snapshot-pin', key]) == 1
    capsys.readouterr()
    assert cli.main(['cache', 'snapshot-remove', key]) == 0
    assert cache_admin.snapshot(d.store)['snapshots'] == []


@pytest.mark.parametrize('damage', ['missing-action', 'malformed-action', 'conflict', 'missing-blob', 'corrupt-blob',
                                    'bad-manifest', 'missing-manifest', 'bad-pin'])
def test_retained_damage_refuses_gc_before_any_deletion(package, damage):
    d = package
    key = d.create()['snapshot']
    value = snapshots.load(d.store, key)
    action = d.store.action(value['actions'][0]['key'])
    blob = next(path for path in d.store.path('blobs').glob('*/*') if path.is_file())
    if damage == 'missing-action':
        action.unlink()
    elif damage == 'malformed-action':
        entry = json.loads(action.read_text())
        entry['schema'] = True  # Python dict equality must not accept True as schema 1.
        action.write_text(json.dumps(entry))
    elif damage == 'conflict':
        action.with_suffix('.conflict.json').write_text('{}')
    elif damage == 'missing-blob':
        blob.unlink()
    elif damage == 'corrupt-blob':
        blob.chmod(0o644)
        original = blob.read_bytes()
        blob.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    elif damage == 'bad-manifest':
        manifest = d.store.path('snapshots', key + '.json')
        manifest.chmod(0o644)
        manifest.write_text('{}')
    elif damage == 'bad-pin':
        d.store.path('snapshots', key + '.pin').write_text(json.dumps(dict(schema=True, snapshot=key)))
    else:
        d.store.path('snapshots', key + '.json').unlink()
    before = {str(p.relative_to(d.store.root)): p.read_bytes() for p in d.store.root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Invalid snapshot'):
        cache_admin.prune(d.store, max_bytes=0, max_age_days=0)
    after = {str(p.relative_to(d.store.root)): p.read_bytes() for p in d.store.root.rglob('*') if p.is_file()}
    assert after == before
    if damage != 'bad-pin':
        with pytest.raises((OSError, ValueError)):
            snapshots.restore('sandbox', key, store=d.store)


def test_private_grants_are_retained_locally_but_refused_for_public_selection(package):
    d = package
    d.policy['actions']['sandbox/world.block']['block.bounds']['permission'] = 'private'
    d.grants.write_text(json.dumps(d.policy))
    key = d.create()['snapshot']
    assert snapshots.load(d.store, key)['audience'] == 'private'
    with pytest.raises(ValueError, match='redistribution'):
        d.create(public=True)
    del d.policy['actions']['sandbox/world.block']['block.bounds']
    d.grants.write_text(json.dumps(d.policy))
    with pytest.raises(ValueError, match='grants'):
        d.create()


@pytest.mark.parametrize('damage', ['source', 'output', 'journal', 'touched', 'missing-cas'])
def test_creation_refuses_uncurrent_uncertain_or_uncached_closure(package, damage):
    d = package
    if damage == 'source':
        (d.game / 'world/block.json').write_text('{}')
    elif damage == 'output':
        (d.output / 'block/shape.json').write_text('{}')
    elif damage in ('journal', 'touched'):
        stamp = d.output / 'stamps/world.block.json'
        if damage == 'journal':
            stamp.with_name('world.block.restore.json').write_text('{}')
        else:
            value = json.loads(stamp.read_text()) | {'touched': True}
            stamp.write_text(json.dumps(value))
    else:
        next(d.store.path('actions').glob('*.json')).unlink()
    with pytest.raises((OSError, ValueError)):
        d.create()
    assert not list(d.store.path('snapshots').glob('*.json'))


def test_restore_rechecks_added_dependencies_and_never_executes_callbacks(package, monkeypatch):
    d = package
    key = d.create()['snapshot']
    real = build.load_recipe
    def changed(game):
        recipe = real(game)
        steps = recipe.steps
        def declarations(ctx):
            found = steps(ctx)
            found[1].after = ['spatial.source.east']
            return found
        recipe.steps = declarations
        return recipe
    monkeypatch.setattr(build, 'load_recipe', changed)
    with pytest.raises(ValueError, match='closure'):
        snapshots.restore('sandbox', key, store=d.store)


def test_interrupted_snapshot_restore_leaves_all_selected_actions_uncertified(package, monkeypatch):
    d = package
    key = d.create()['snapshot']
    value = snapshots.load(d.store, key)
    real = d.store._restore
    count = [0]
    def interrupt(*args):
        count[0] += 1
        if count[0] == 2:
            raise OSError('injected replacement failure')
        return real(*args)
    monkeypatch.setattr(d.store, '_restore', interrupt)
    with pytest.raises(OSError, match='replacement failure'):
        snapshots.restore('sandbox', key, store=d.store)
    for action in value['actions']:
        assert not (d.output / 'stamps' / (action['step'] + '.json')).exists()
        assert (d.output / 'stamps' / (action['step'] + '.restore.json')).exists()
    monkeypatch.setattr(d.store, '_restore', real)
    assert snapshots.restore('sandbox', key, store=d.store)['restored']


def test_complete_needs_order_and_reference_cycle_closure(package, monkeypatch):
    d = package
    real = build.load_recipe
    def load(game):
        recipe = real(game)
        steps = recipe.steps
        def declarations(ctx):
            found = steps(ctx)
            found[0].references = ['world.placements']  # Legal reference-only cycle.
            found[1].needs = ['spatial.source.far']
            found[1].after = ['spatial.source.east']
            return found
        recipe.steps = declarations
        return recipe
    monkeypatch.setattr(build, 'load_recipe', load)
    assert d.run('world.placements', 'spatial.tile.west') == 0, d.messages
    key = d.create()['snapshot']
    value = snapshots.load(d.store, key)
    assert {a['step'] for a in value['actions']} == {'world.block', 'world.placements', 'spatial.source.far',
        'spatial.source.east', 'spatial.source.west', 'spatial.tile.west'}
    shutil.rmtree(d.output)
    monkeypatch.setattr(build, 'run_command', lambda *a, **k: pytest.fail('restore executed an action'))
    assert snapshots.restore('sandbox', key, store=d.store)['executed'] == 0


def test_empty_queries_and_unselected_metadata_are_bound_correctly(package):
    d = package
    original = d.create()['snapshot']
    d.edit('far', preview_colour='metadata-unread-by-any-selected-action')
    assert d.create()['snapshot'] == original
    d.edit('west', bounds_cm=[1000, -10, -10, 1010, 10, 10])
    assert d.run('world.placements', 'spatial.tile.west') == 0, d.messages
    key = d.create()['snapshot']
    value = snapshots.load(d.store, key)
    assert value['actions'][-1]['reads'] == []
    assert 'spatial.source.west' not in {a['step'] for a in value['actions']}
    shutil.rmtree(d.output)
    assert snapshots.restore('sandbox', key, store=d.store)['restored']
    d.edit('far', bounds_cm=[10, -10, -10, 20, 10, 10])
    with pytest.raises(ValueError, match='closure'):
        snapshots.restore('sandbox', key, store=d.store)


@pytest.mark.parametrize('kind', ['symlink', 'fifo', 'oversized'])
def test_invalid_unpinned_manifests_refuse_gc_and_can_be_removed_explicitly(tmp_path, kind):
    store = build_cache.Store(tmp_path / 'cache')
    directory = store.path('snapshots')
    directory.mkdir(parents=True)
    key = '1' * 64
    path = directory / (key + '.json')
    if kind == 'symlink':
        outside = tmp_path / 'outside'
        outside.write_text('preserved')
        path.symlink_to(outside)
    elif kind == 'fifo':
        import os
        os.mkfifo(path)
    else:
        path.write_bytes(b' ' * (snapshots.bundle.MAX_MANIFEST + 1))
    with pytest.raises(ValueError, match='Invalid snapshot'):
        cache_admin.prune(store, max_bytes=0, max_age_days=0)
    snapshots.remove(store, key)
    assert not path.exists()
    if kind == 'symlink':
        assert outside.read_text() == 'preserved'


def test_snapshot_enumeration_has_an_explicit_bound(tmp_path, monkeypatch):
    store = build_cache.Store(tmp_path / 'cache')
    directory = store.path('snapshots')
    directory.mkdir(parents=True)
    for name in ('a.json', 'b.json'):
        (directory / name).write_text('{}')
    monkeypatch.setattr(snapshots, 'MAX_SNAPSHOTS', 1)
    with pytest.raises(ValueError, match='count exceeds'):
        cache_admin.prune(store, max_bytes=0, max_age_days=0)


def test_receiving_checkout_restores_with_donor_unavailable_and_independent_bytes(package, tmp_path, monkeypatch):
    d = package
    key = d.create()['snapshot']
    receiver = tmp_path / 'receiver'
    shutil.copytree(d.repo / 'games', receiver / 'games', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(d.repo / 'uv.lock', receiver / 'uv.lock')
    d.repo.rename(tmp_path / 'donor-unavailable')
    monkeypatch.setattr(paths, 'REPO', receiver)
    monkeypatch.setattr(paths, 'GAMES', receiver / 'games')
    monkeypatch.setattr(build, 'run_command', lambda *a, **k: pytest.fail('receiver executed an action'))
    assert snapshots.restore('sandbox', key, store=d.store)['restored']
    manifest = snapshots.load(d.store, key)
    shape = manifest['actions'][0]['products']['block.shape']['inventory']['files']['0/.']['sha256']
    blob = d.store.blob(shape)
    before = blob.read_bytes()
    output = receiver / 'build/sandbox/block/shape.json'
    assert output.stat().st_ino != blob.stat().st_ino
    output.write_text('changed independently')
    assert blob.read_bytes() == before
