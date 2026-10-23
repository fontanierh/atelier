"""Real checkpoint files and receiving recipes; no Unreal, Blender, cook or native build."""
from copy import deepcopy
import hashlib
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, build_snapshot, checkpoint_actions, checkpoint_store as cp, paths
from atelier.build_cache import atomic_json


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', tmp_path / 'plugins')
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    def checkout(name, *, changed=False, project=False):
        repo = (tmp_path / name).resolve()
        repo.mkdir()
        (repo / 'uv.lock').write_text('fixture lock')
        monkeypatch.setattr(paths, 'REPO', repo)
        monkeypatch.setattr(paths, 'build_root', lambda: paths.REPO / 'build')
        out = repo / 'build/fixture'
        ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps',
                              uproject=None, unreal_root=None)
        steps = []
        for asset in ('tree', 'combat', 'house'):
            source = repo / (asset + '.txt')
            source.write_text('changed combat' if changed and asset == 'combat' else asset)
            destination = out / asset / 'asset.bin'
            steps.append(build.Step(asset, [build.Python(source, (destination,))], inputs=[source],
                                    outputs=[destination], products=[build.Product(asset, (destination.parent,))]))
        return ctx, steps
    def produce(ctx, steps):
        ctx.stamps.mkdir(parents=True)
        done = {}
        for step in steps:
            step.outputs[0].parent.mkdir(parents=True)
            step.outputs[0].write_bytes(step.name.encode())
            value = build.fingerprint(step, done)
            products = build.build_products.records(step)
            stamp = dict(fingerprint=value, products=products, seconds=3., time=1.)
            stamp['checkpoint_key'] = checkpoint_actions.certificate_key(ctx, step, value)
            declarations, files = checkpoint_actions.snapshot(ctx, step, fixture_store, save_blobs=False)
            stamp['checkpoint_inventory'] = checkpoint_actions.inventory_identity(declarations, files)
            atomic_json(ctx.stamps / (step.name + '.json'), stamp)
            done[step.name] = value
            build.build_products.feed_results(done, products)
    fixture_store = cp.Store('fixture', tmp_path / 'store')
    return SimpleNamespace(checkout=checkout, produce=produce, store=fixture_store)


def snapshot(fixture):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    key = cp.capture(ctx, steps, fixture.store, echo=lambda _: None)
    return ctx, steps, key


@pytest.mark.parametrize('member', ['generated/../source', '/absolute', 'generated/.env',
                                    'generated/part/../../source', 'generated/a\\b'])
def test_manifest_refuses_unsafe_paths(fixture, member):
    _, _, key = snapshot(fixture)
    value = fixture.store.load(key)
    entry = next(iter(value['files'].values()))
    value['files'] = {member: entry}
    with pytest.raises(cp.CheckpointError):
        cp.validate(value, 'fixture')


def test_manifest_refuses_case_aliases_and_file_ancestors(fixture):
    _, _, key = snapshot(fixture)
    value = fixture.store.load(key)
    entry = next(iter(value['files'].values()))
    for names in [('generated/A', 'generated/a'), ('generated/a', 'generated/a/b')]:
        value['files'] = dict.fromkeys(names, entry)
        with pytest.raises(cp.CheckpointError):
            cp.validate(value, 'fixture')


def test_touched_or_stale_tasks_do_not_become_checkpoint_certificates(fixture):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    stamp = ctx.stamps / 'tree.json'
    value = cp.read_json(stamp); value['touched'] = True; atomic_json(stamp, value)
    (paths.REPO / 'combat.txt').write_text('changed')
    key = cp.capture(ctx, steps, fixture.store)
    assert set(fixture.store.load(key)['stamps']) == {'house'}


def test_artifacts_added_during_capture_refuse_publication(fixture, monkeypatch):
    ctx, steps = fixture.checkout('donor')
    fixture.produce(ctx, steps)
    original = fixture.store.put
    def changed(path, digest):
        original(path, digest)
        (ctx.out / 'appeared.bin').write_bytes(b'new')
    monkeypatch.setattr(fixture.store, 'put', changed)
    with pytest.raises(cp.CheckpointError, match='changed during'):
        cp.capture(ctx, steps, fixture.store)
    assert not list(fixture.store.manifests.glob('*.json'))


def test_large_or_unknown_cold_jobs_require_a_recorded_reason(tmp_path):
    ctx = SimpleNamespace(checkpoint_settings=dict(rebuild_budget_seconds=60), logs=tmp_path,
                          rebuild_reason=None, uproject=None)
    step = build.Step('native.import', [build.UnrealScript(Path('import.py'), 'done')], heavy=True,
                      checkpoint_outputs=(tmp_path / 'assets',))
    with pytest.raises(cp.CheckpointError, match='unknown cold'):
        build_checkpoints.protect(ctx, step)
    with pytest.raises(cp.CheckpointError, match='120s'):
        build_checkpoints.protect(ctx, step, estimate=120)
    ctx.rebuild_reason = 'first build after engine upgrade'
    build_checkpoints.protect(ctx, step, estimate=120)
    assert json.loads((tmp_path / 'rebuild-decisions.jsonl').read_text())['reason'] == ctx.rebuild_reason


def test_rebuild_reason_covers_only_the_tasks_it_names_or_that_were_cold(tmp_path):
    ctx = SimpleNamespace(checkpoint_settings=dict(rebuild_budget_seconds=60), logs=tmp_path, uproject=None,
                          rebuild_reasons={'native.terrain': 'terrain recipe rewrite'}, rebuild_reason='new region',
                          cold_at_launch={'native.region'})
    def native(name):
        return build.Step(name, [build.UnrealScript(Path('import.py'), 'done')], heavy=True,
                          checkpoint_outputs=(tmp_path / name,))
    messages = []
    build_checkpoints.protect(ctx, native('native.terrain'), estimate=900, echo=messages.append)
    build_checkpoints.protect(ctx, native('native.region'), echo=messages.append)
    # An already-built task invalidated by the same run still stops at the budget.
    with pytest.raises(cp.CheckpointError, match='--rebuild-reason native.world='):
        build_checkpoints.protect(ctx, native('native.world'), estimate=900, echo=messages.append)
    assert messages == ['native.terrain: rebuild reason applied (named): terrain recipe rewrite',
                        'native.region: rebuild reason applied (requested or cold at launch): new region']
    decisions = [json.loads(line) for line in (tmp_path / 'rebuild-decisions.jsonl').read_text().splitlines()]
    assert [(d['step'], d['scope']) for d in decisions] == [('native.terrain', 'named'), ('native.region', 'requested or cold at launch')]
    # The bare reason follows the cascade from a covered rerun, never an unrelated invalidation.
    ctx.rebuild_upstream = {'native.belmonte': {'native.region'}, 'native.world': {'native.ferry'}}
    build_checkpoints.note_rerun(ctx, native('native.region'))
    build_checkpoints.note_rerun(ctx, native('native.ferry'))  # Not covered: it extends nothing.
    build_checkpoints.protect(ctx, native('native.belmonte'), estimate=900, echo=messages.append)
    assert messages[-1] == 'native.belmonte: rebuild reason applied (downstream of native.region): new region'
    with pytest.raises(cp.CheckpointError, match='stopped before a costly rebuild'):
        build_checkpoints.protect(ctx, native('native.world'), estimate=900, echo=messages.append)
    assert ctx.rebuild_covered == ['native.terrain', 'native.region', 'native.belmonte']


def test_rebuild_reasons_parse_scoped_and_one_bare_value():
    assert build_checkpoints.reasons(['a.b=why', 'plain reason', 'c=x=y']) == ({'a.b': 'why', 'c': 'x=y'}, 'plain reason')
    assert build_checkpoints.reasons('legacy single value') == ({}, 'legacy single value')
    with pytest.raises(cp.CheckpointError, match='at most one bare'):
        build_checkpoints.reasons(['one', 'two'])


def test_guard_failure_cannot_publish_receipt_or_certificates(fixture, monkeypatch):
    _, _, key = snapshot(fixture)
    ctx, steps = fixture.checkout('receiver')
    from atelier.harness.safety import guarded
    calls = []
    monkeypatch.setattr(guarded, 'run', lambda *a, **kw: calls.append((a, kw)) or 7)
    with pytest.raises(cp.CheckpointError, match='exit 7'):
        build_checkpoints._guard(ctx, 'restore', key)
    assert calls[0][1]['aggregate_tree'] is True
    assert calls[0][1]['timeout'] == 3600
    assert not ctx.stamps.exists()


def test_checkpoint_barrier_cannot_hide_behind_output_override(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    default = tmp_path / 'build/fixture'
    default.mkdir(parents=True)
    atomic_json(default / cp.JOURNAL, dict(schema=1, key='a' * 64, game='fixture'))
    with pytest.raises(SystemExit, match='checkpoint restoration is incomplete'):
        build_snapshot.require_complete(tmp_path / 'other/fixture', game='fixture')


def test_retired_manual_reuse_cannot_start_a_full_copy(monkeypatch):
    from atelier import cli
    with pytest.raises(SystemExit):
        cli.main(['reuse', 'fixture', '--from', 'donor'])


def test_default_checkpoint_cooking_uses_dependency_tracking(tmp_path):
    from atelier.build_cook import apply, CookMode
    game = tmp_path / 'game'; game.mkdir()
    (game / 'game.toml').write_text('[checkpoints]\nrebuild_budget_seconds=600\n')
    ctx = SimpleNamespace(game='fixture', game_dir=game, cook_mode=CookMode.DEFAULT)
    step = build.Step('cook', [build.UnrealPackage('Fixture', tmp_path / 'archive')])
    apply(ctx, [step])
    assert step.commands[0].cook_mode is CookMode.INCREMENTAL


@pytest.mark.parametrize('operation', ['restore-action'])
def test_checkpoint_transfer_reaches_real_guard_boundary_with_valid_invocation(tmp_path, monkeypatch, operation):
    from atelier.harness.safety import guarded
    class BeforeNativeLaunch(Exception):
        pass
    calls = []
    def boundary(*args, **kwargs):
        calls.append(args[0])
        raise BeforeNativeLaunch
    # Exercise the production guard's UUID validation, then stop before its
    # actual admission/child launcher. No native command or fake process runs.
    monkeypatch.setattr(guarded, '_run', boundary)
    ctx = SimpleNamespace(game='fixture', logs=tmp_path)
    with pytest.raises(BeforeNativeLaunch):
        build_checkpoints._guard(ctx, operation, 'a' * 64)
    assert len(calls) == 1


def representative(ctx):
    """A step known only by a sample output, like a non-factory Blender world export."""
    source = paths.REPO / 'world.txt'
    source.write_text('world')
    report = ctx.out / 'world/build-report.json'
    return build.Step('world', [build.Python(source, (report,))], inputs=[source], outputs=[report])


def inventoried(ctx, files):
    """A representative-output step (like unreal.treehouse) whose stamp lists every file it wrote."""
    step = representative(ctx)
    (ctx.out / 'world').mkdir(parents=True, exist_ok=True)
    inventory = {}
    for name in ('build-report.json', *files):
        path = ctx.out / 'world' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
        info = path.stat()
        inventory['generated/world/' + name] = [info.st_size, info.st_mtime_ns, hashlib.sha256(name.encode()).hexdigest()]
    stamp = dict(fingerprint=build.fingerprint(step, {}), seconds=30., time=1., output_inventory=inventory)
    atomic_json(ctx.stamps / 'world.json', stamp)
    return step


