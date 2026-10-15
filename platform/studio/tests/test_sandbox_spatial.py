"""Real offline actions prove query membership, narrow rebuilds and portable restoration."""
import json
import shutil
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_plan, build_products, paths


@pytest.fixture
def demo(tmp_path, monkeypatch):
    source = paths.GAMES / 'sandbox'
    repo = tmp_path / 'first'
    game = repo / 'games/sandbox'
    game.mkdir(parents=True)
    shutil.copytree(source / 'world', game / 'world', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(source / 'build.py', game / 'build.py')
    shutil.copyfile(paths.REPO / 'uv.lock', repo / 'uv.lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'GAMES', repo / 'games')
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    for name in ('ATELIER_BUILD_ROOT', 'ATELIER_PYTHON', 'PYTHONHOME', 'PYTHONPATH'):
        monkeypatch.delenv(name, raising=False)
    calls, messages = [], []
    real_run = build.run_command

    def run(ctx, step, *args, **kwargs):
        assert not step.heavy
        calls.append(step.name)
        return real_run(ctx, step, *args, **kwargs)
    monkeypatch.setattr(build, 'run_command', run)

    def edit(name, **updates):
        path = game / f'world/spatial/{name}.json'
        value = json.loads(path.read_text())
        path.write_text(json.dumps(value | updates))

    def execute(*wanted, **kwargs):
        calls.clear()
        return build.build('sandbox', list(wanted or ('spatial.demo',)), echo=messages.append, **kwargs)

    return SimpleNamespace(repo=repo, game=game, calls=calls, messages=messages, edit=edit, run=execute,
                           output=repo / 'build/sandbox', real_run=real_run)


def test_local_edits_ignore_far_products_and_unread_siblings(demo):
    d = demo
    assert d.run() == 0, d.messages
    assert d.calls == ['spatial.source.east', 'spatial.source.far', 'spatial.source.west',
                       'spatial.tile.west', 'spatial.tile.east']
    assert d.run() == 0 and d.calls == []
    d.edit('west', shape='wedge')
    assert d.run() == 0, d.messages
    assert d.calls == ['spatial.source.west', 'spatial.tile.west']
    d.edit('west', preview_colour='purple')
    assert d.run() == 0 and d.calls == ['spatial.source.west']
    d.edit('far', shape='cone', bounds_cm=[2000, -10, -10, 2010, 10, 10])
    assert d.run() == 0 and d.calls == ['spatial.source.far']


def test_moving_product_invalidates_old_and_new_tiles_and_plan_is_read_only(demo):
    d = demo
    assert d.run() == 0, d.messages
    d.edit('west', bounds_cm=[120, -10, -10, 130, 10, 10])
    stamps = {p: p.read_bytes() for p in (d.output / 'stamps').iterdir()}
    ctx = build.Context('sandbox', create=False)
    report = build_plan.inspect(ctx, build.load_recipe('sandbox').steps(ctx), ['spatial.demo'])
    tiles = {s['step']: s for s in report['steps'] if s['step'].startswith('spatial.tile.')}
    assert all(s['status'] == 'run' for s in tiles.values())
    assert tiles['spatial.tile.west']['queries']['neighbours']['matches'] == []
    assert any('spatial query changed' in reason for reason in tiles['spatial.tile.east']['reasons'])
    assert {p: p.read_bytes() for p in stamps} == stamps
    assert d.run() == 0, d.messages
    assert d.calls == ['spatial.source.west', 'spatial.tile.west', 'spatial.tile.east']
    assert json.loads((d.output / 'spatial/tiles/west.json').read_text()) == []
    assert [p['name'] for p in json.loads((d.output / 'spatial/tiles/east.json').read_text())] == [
        'spatial.east', 'spatial.west']


def test_add_remove_and_boundary_membership(demo):
    d = demo
    assert d.run('spatial.tile.west') == 0, d.messages
    assert d.calls == ['spatial.source.west', 'spatial.tile.west']
    added = d.game / 'world/spatial/new.json'
    # A zero-width box on the boundary belongs to both neighbouring tiles.
    added.write_text('{"bounds_cm":[100,0,0,100,0,0],"shape":"point","preview_colour":"white"}')
    assert d.run('spatial.tile.west') == 0, d.messages
    assert d.calls == ['spatial.source.new', 'spatial.tile.west']
    added.unlink()
    assert d.run('spatial.tile.west') == 0 and d.calls == []
    restored = json.loads((d.output / 'stamps/spatial.tile.west.json').read_text())
    assert restored['restored_from'] == restored['fingerprint']
    (d.game / 'world/spatial/west.json').unlink()
    assert d.run('spatial.tile.west') == 0 and d.calls == ['spatial.tile.west']
    assert json.loads((d.output / 'spatial/tiles/west.json').read_text()) == []


def test_restore_without_donor_and_fresh_build_agree(demo, tmp_path, monkeypatch):
    d = demo
    assert d.run() == 0, d.messages
    expected = {p.name: p.read_bytes() for p in (d.output / 'spatial/tiles').iterdir()}
    receiver = tmp_path / 'receiver'
    shutil.copytree(d.repo / 'games', receiver / 'games', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(d.repo / 'uv.lock', receiver / 'uv.lock')
    d.repo.rename(tmp_path / 'donor-unavailable')
    monkeypatch.setattr(paths, 'REPO', receiver)
    monkeypatch.setattr(paths, 'GAMES', receiver / 'games')
    assert d.run() == 0, d.messages
    assert d.calls == []
    tiles = receiver / 'build/sandbox/spatial/tiles'
    assert {p.name: p.read_bytes() for p in tiles.iterdir()} == expected
    assert d.run(force=True, verify=True) == 0, d.messages
    assert {p.name: p.read_bytes() for p in tiles.iterdir()} == expected


@pytest.mark.parametrize('target', ['catalogue', 'nonmatching-product', 'sibling'])
def test_query_does_not_grant_catalogue_or_other_product_reads(demo, target):
    d = demo
    hidden = {'catalogue': d.game / 'world/spatial/far.json',
              'nonmatching-product': d.output / 'spatial/sources/far/geometry.json',
              'sibling': d.output / 'spatial/sources/west/preview.json'}[target]
    script = d.game / 'world/build_spatial_tile.py'
    script.write_text(script.read_text() + f'\nPath({str(hidden)!r}).read_text()\n')
    assert d.run() == 1
    assert not (d.output / 'stamps/spatial.tile.west.json').exists()
    report = json.loads((d.output / 'logs/spatial.tile.west.audit.json').read_text())
    assert report['violations'] and not report['passed']


@pytest.mark.parametrize('change', ['membership', 'selected-bytes', 'owner-path', 'action', 'order'])
def test_drift_during_action_refuses_certification(demo, monkeypatch, change):
    d = demo
    def run(ctx, step, *args, **kwargs):
        result = d.real_run(ctx, step, *args, **kwargs)
        if step.name == 'spatial.tile.west':
            if change == 'membership':
                d.edit('far', bounds_cm=[30, 0, 0, 40, 1, 1])
            elif change == 'selected-bytes':
                (d.output / 'spatial/sources/west/geometry.json').write_text('{"shape":"changed"}')
            else:
                real_recipe = build.load_recipe
                def load(game):
                    recipe = real_recipe(game)
                    original = recipe.steps
                    def steps(ctx):
                        result = original(ctx)
                        for s in result:
                            if change == 'action' and s.name == step.name:
                                s.commands[0].args = (*s.commands[0].args, 'new-argument')
                            if change == 'order' and s.name == step.name:
                                s.after = ['spatial.source.far']
                            if change == 'owner-path' and s.name == 'spatial.source.west':
                                p = s.products[0]
                                s.products[0] = build.Product(p.name, (ctx.out / 'moved.json',),
                                                              collection=p.collection, bounds=p.bounds)
                        return result
                    recipe.steps = steps
                    return recipe
                monkeypatch.setattr(build, 'load_recipe', load)
        return result
    monkeypatch.setattr(build, 'run_command', run)
    assert d.run() == 1, d.messages
    assert not (d.output / 'stamps/spatial.tile.west.json').exists()
    assert any('spatial' in m and ('changed' in m or 'replan' in m) for m in d.messages)


@pytest.mark.parametrize('boundary', ['up-to-date', 'restore'])
def test_drift_cannot_accept_an_old_stamp_or_restored_hit(demo, monkeypatch, boundary):
    d = demo
    assert d.run() == 0, d.messages
    published = []
    real_publish = build_cache.Store.publish
    def publish(store, ctx, step, *args):
        published.append(step.name)
        return real_publish(store, ctx, step, *args)
    monkeypatch.setattr(build_cache.Store, 'publish', publish)
    if boundary == 'up-to-date':
        real_valid = build_products.valid_records
        def valid(step, *args, **kwargs):
            result = real_valid(step, *args, **kwargs)
            if step.name == 'spatial.tile.west':
                d.edit('far', bounds_cm=[30, 0, 0, 40, 1, 1])
            return result
        monkeypatch.setattr(build_products, 'valid_records', valid)
    else:
        (d.output / 'spatial/tiles/west.json').unlink()
        real_restore = build_cache.Store.restore
        def restore(store, ctx, step, *args):
            result = real_restore(store, ctx, step, *args)
            if step.name == 'spatial.tile.west':
                assert result is not None
                d.edit('far', bounds_cm=[30, 0, 0, 40, 1, 1])
            return result
        monkeypatch.setattr(build_cache.Store, 'restore', restore)
    assert d.run() == 1, d.messages
    assert d.calls == [] and published == []
    assert not (d.output / 'stamps/spatial.tile.west.json').exists()
    assert any('spatial inputs changed' in m for m in d.messages)


def test_unmatched_catalogue_edit_during_action_does_not_invalidate(demo, monkeypatch):
    d = demo
    def run(ctx, step, *args, **kwargs):
        result = d.real_run(ctx, step, *args, **kwargs)
        if step.name == 'spatial.tile.west':
            d.edit('far', bounds_cm=[2000, 0, 0, 2010, 1, 1])
        return result
    monkeypatch.setattr(build, 'run_command', run)
    assert d.run('spatial.tile.west') == 0, d.messages
    assert (d.output / 'stamps/spatial.tile.west.json').is_file()
