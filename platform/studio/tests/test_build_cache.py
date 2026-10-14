"""Real engine/cache scenarios with tiny deterministic outputs; no native tools or shared cache."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_plan, build_products, paths
from atelier.build import Product, Python, Step


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / 'checkout'; repo.mkdir()
    source = repo / 'source'; source.write_text('one')
    tool = tmp_path / 'tool'; tool.write_text('tool-v1')
    script = repo / 'generate.py'; script.write_text('# fixture generator')
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture', logs=repo / 'build/fixture/logs',
                          stamps=repo / 'build/fixture/stamps')
    step = Step('mesh', [Python(script)], inputs=[source], cache=True,
                products=[Product('mesh', (ctx.out / 'mesh',)), Product('bounds', (ctx.out / 'bounds.json',))])
    store = build_cache.Store(tmp_path / 'store')
    calls = []
    def run(ctx, step, command, log, *args):
        calls.append(step.name)
        folder = step.products[0].paths[0]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'vertices').write_text((command.script.parent / 'source').read_text())
        (folder / 'empty').mkdir(exist_ok=True)
        step.products[1].paths[0].write_text('bounds')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'build_root', lambda: ctx.out.parent)
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: [step]))
    monkeypatch.setattr(build, 'run_command', run)
    monkeypatch.setattr(build_cache, 'Store', lambda: store)
    monkeypatch.setattr(build_cache, 'tool_context', lambda step, hasher, **kwargs: {'tool': hasher(tool)})
    messages = []
    return SimpleNamespace(ctx=ctx, step=step, store=store, source=source, tool=tool, calls=calls,
                           messages=messages, run=lambda **kwargs: build.build('fixture', echo=messages.append, **kwargs))


def test_build_restores_missing_and_modified_outputs_as_independent_copies(project):
    p = project
    assert p.run() == 0 and p.calls == ['mesh']
    expected = build_products.records(p.step)
    (p.ctx.out / 'mesh/vertices').unlink()
    p.calls.clear()
    assert p.run() == 0 and p.calls == []
    assert build_products.records(p.step) == expected
    (p.ctx.out / 'mesh/vertices').write_text('corruption')
    assert p.run() == 0 and p.calls == []
    assert build_products.records(p.step) == expected
    assert any('restored in' in message for message in p.messages)
    assert not (p.ctx.stamps / 'mesh.restore.json').exists()


def test_source_and_tool_changes_miss_but_reverting_reuses_previous_products(project):
    p = project
    assert p.run() == 0
    original = build_products.records(p.step)
    p.source.write_text('two')
    assert p.run() == 0 and p.calls == ['mesh', 'mesh']
    p.source.write_text('one')
    assert p.run() == 0 and p.calls == ['mesh', 'mesh']
    assert build_products.records(p.step) == original
    p.tool.write_text('tool-v2')
    assert p.run() == 0 and len(p.calls) == 3


def test_clean_and_cache_restored_builds_agree_without_the_donor_checkout(project, tmp_path, monkeypatch):
    p = project
    assert p.run() == 0
    expected = build_products.records(p.step)
    old = p.ctx.out
    old_key = build.fingerprint(p.step, {})
    receiving = tmp_path / 'receiving'; receiving.mkdir()
    (receiving / 'source').write_text('one')
    (receiving / 'generate.py').write_text('# fixture generator')
    new = receiving / 'build/fixture'
    p.ctx.out, p.ctx.logs, p.ctx.stamps = new, new / 'logs', new / 'stamps'
    p.step.products = [Product(item.name, tuple(new / path.relative_to(old) for path in item.paths))
                       for item in p.step.products]
    p.step.commands = [Python(receiving / 'generate.py')]
    p.step.inputs = [receiving / 'source']
    monkeypatch.setattr(paths, 'REPO', receiving)
    old.parent.parent.rename(tmp_path / 'donor-unavailable')
    assert build.fingerprint(p.step, {}) == old_key
    p.calls.clear()
    assert p.run() == 0 and not p.calls
    assert build_products.records(p.step) == expected
    assert p.run(force=True) == 0 and p.calls == ['mesh']
    assert build_products.records(p.step) == expected


def test_corrupt_blob_falls_back_to_build_without_accepting_partial_bytes(project):
    p = project
    assert p.run() == 0
    (p.ctx.out / 'mesh/vertices').unlink()
    for blob in (p.store.root / 'blobs').glob('*/*'):
        blob.chmod(0o644); blob.write_bytes(b'wrong')
    assert p.run() == 0 and p.calls == ['mesh', 'mesh']
    assert (p.ctx.out / 'mesh/vertices').read_text() == 'one'
    assert any('cache unavailable' in message for message in p.messages)


def test_interrupted_install_has_no_stamp_and_next_build_recovers(project, monkeypatch):
    p = project
    assert p.run() == 0
    key = build.fingerprint(p.step, {})
    real = Path.replace
    def interrupt(source, target):
        if '.restore-' in str(source) and str(target).endswith('bounds.json'):
            raise OSError('simulated interrupted replacement')
        return real(source, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', interrupt)
        with pytest.raises(OSError):
            p.store.restore(p.ctx, p.step, key)
    assert not (p.ctx.stamps / 'mesh.json').exists()
    assert (p.ctx.stamps / 'mesh.restore.json').exists()
    assert any('interrupted' in reason for reason in build_plan.inspect(p.ctx, [p.step])['steps'][0]['reasons'])
    p.calls.clear()
    assert p.run() == 0 and not p.calls
    assert not (p.ctx.stamps / 'mesh.restore.json').exists()


def test_same_key_with_different_bytes_is_not_overwritten(project):
    p = project
    assert p.run() == 0
    key = build.fingerprint(p.step, {})
    original = p.store.action(key).read_bytes()
    (p.ctx.out / 'mesh/vertices').write_text('different')
    with pytest.raises(ValueError, match='different bytes'):
        p.store.publish(p.ctx, p.step, key, build_products.records(p.step))
    assert p.store.action(key).read_bytes() == original
    assert p.store.restore(p.ctx, p.step, key) is None


def test_cache_lookup_runtime_error_falls_back_and_does_not_certify_changed_inputs(project, monkeypatch):
    p = project
    assert p.run() == 0
    (p.ctx.out / 'mesh/vertices').unlink()
    def changed(*args):
        p.source.write_text('changed during restore')
        raise RuntimeError('inputs changed')
    monkeypatch.setattr(p.store, 'restore', changed)
    assert p.run() == 1
    assert not (p.ctx.stamps / 'mesh.json').exists()
    assert any('cache unavailable' in m for m in p.messages)
    assert any('inputs changed during build' in m for m in p.messages)


def test_undeclared_import_refuses_build_and_cache_hit(project):
    p = project
    assert p.run() == 0
    script = p.step.commands[0].script
    (script.parent / 'helper.py').write_text('VALUE = 1')
    script.write_text('import helper\n')
    p.calls.clear()
    assert p.run() == 1 and not p.calls
    assert any('undeclared local imports' in m for m in p.messages)


def test_interrupted_staging_is_swept_for_only_this_action(project):
    p = project
    staging = build_cache.staging_root(p.ctx, p.step)
    staging.mkdir(parents=True)
    (staging / '.restore-abandoned').mkdir()
    other = staging.parent / 'other'; other.mkdir()
    (other / 'live').write_text('leave alone')
    assert p.run() == 0
    assert not staging.exists()
    assert (other / 'live').read_text() == 'leave alone'


def test_gc_keeps_pins_shared_blobs_and_respects_active_transfers(project):
    from atelier import cache_admin
    p = project
    assert p.run() == 0
    first = build.fingerprint(p.step, {})
    cache_admin.pin(p.store, first, True)
    p.source.write_text('two')
    assert p.run() == 0
    second = build.fingerprint(p.step, {})
    state = cache_admin.snapshot(p.store)
    assert state['unique_bytes'] == len('one') + len('two') + len('bounds')
    with p.store.lock():
        with pytest.raises(BlockingIOError):
            cache_admin.prune(p.store, max_bytes=0, max_age_days=0)
    preview = cache_admin.prune(p.store, max_bytes=0, max_age_days=0, dry=True)
    assert preview['removed_actions'] == [second]
    assert p.store.action(second).exists()
    result = cache_admin.prune(p.store, max_bytes=0, max_age_days=0)
    assert result['remaining_bytes'] == len('one') + len('bounds')
    assert p.store.action(first).exists() and not p.store.action(second).exists()
    assert p.store.restore(p.ctx, p.step, first) is not None
    cache_admin.pin(p.store, first, False)
    assert cache_admin.prune(p.store, max_bytes=0, max_age_days=0)['remaining_bytes'] == 0


def test_conflicts_can_be_discarded_but_never_pinned(project):
    from atelier import cache_admin
    p = project
    assert p.run() == 0
    key = build.fingerprint(p.step, {})
    (p.ctx.out / 'mesh/vertices').write_text('nondeterministic')
    with pytest.raises(ValueError):
        p.store.publish(p.ctx, p.step, key, build_products.records(p.step))
    assert cache_admin.snapshot(p.store)['conflicts'] == [key]
    with pytest.raises(ValueError):
        cache_admin.pin(p.store, key, True)
    cache_admin.forget(p.store, key)
    assert not p.store.action(key).exists()
    assert cache_admin.snapshot(p.store)['conflicts'] == []


@pytest.mark.parametrize('malformed', [None, [], 'invalid', {'schema': 1, 'products': []}])
def test_malformed_cache_action_falls_back_to_a_real_build(project, malformed):
    p = project
    assert p.run() == 0
    key = build.fingerprint(p.step, {})
    p.store.action(key).write_text(json.dumps(malformed))
    (p.ctx.out / 'mesh/vertices').unlink()
    assert p.run() == 0 and p.calls == ['mesh', 'mesh']


def test_cache_cannot_follow_a_linked_blob_directory(project, tmp_path):
    p = project
    outside = tmp_path / 'outside'; outside.mkdir()
    p.store.root.mkdir(parents=True)
    (p.store.root / 'blobs').symlink_to(outside, target_is_directory=True)
    assert p.run() == 0
    assert not list(outside.iterdir())
    assert any('publication skipped' in m for m in p.messages)


def test_restore_refuses_linked_destinations_and_native_outputs(project):
    p = project
    p.ctx.out.mkdir(parents=True)
    external = p.ctx.out.parent / 'external'; external.mkdir()
    (p.ctx.out / 'mesh').symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='Linked'):
        build_cache.roots(p.ctx, p.step)
    p.step.products = [Product('native', (p.ctx.out / 'Content/tree.uasset',))]
    with pytest.raises(ValueError, match='Native'):
        build_cache.roots(p.ctx, p.step)


@pytest.mark.parametrize('member', ['0/../outside', '0//absolute', '0/a/../../outside', '1/.', '0/link\\name'])
def test_manifest_paths_cannot_escape_declared_roots(member):
    with pytest.raises(ValueError):
        list(build_cache.members({'schema': 1, 'files': {member: {'kind': 'directory'}}}, 1))
