"""Exercise the shipped template with real Python processes and the real portable store."""
import json
import shutil

import pytest

from atelier import build, build_products, paths


@pytest.mark.parametrize('override', [False, True], ids=['optional-absent', 'optional-present'])
def test_small_edits_and_another_checkout_reuse_independent_products(tmp_path, monkeypatch, override):
    source = paths.GAMES / 'sandbox'
    repo = tmp_path / 'first'; repo.mkdir()
    game = repo / 'games/sandbox'; game.mkdir(parents=True)
    shutil.copytree(source / 'world', game / 'world', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(source / 'build.py', game / 'build.py')
    shutil.copyfile(paths.REPO / 'uv.lock', repo / 'uv.lock')
    if override:
        (game / 'world/block.override.json').write_text('{"size_cm":[100,200,400]}')
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

    assert build.build('sandbox', ['world'], echo=messages.append) == 0
    assert calls == ['world.block', 'world.placements']
    calls.clear()
    (game / 'world/placements.json').write_text('[{"asset":"block","position_cm":[900,600,100]}]')
    assert build.build('sandbox', ['world'], echo=messages.append) == 0
    assert calls == ['world.placements']
    calls.clear()
    (game / 'world/block.json').write_text('{"size_cm":[800,400,200]}')
    assert build.build('sandbox', ['world'], echo=messages.append) == 0
    assert calls == ['world.block']
    expected = [build_products.records(step) for step in build.load_recipe('sandbox').steps(build.Context('sandbox'))[:2]]

    receiver = tmp_path / 'receiving'; receiver.mkdir()
    shutil.copytree(repo / 'games', receiver / 'games', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(repo / 'uv.lock', receiver / 'uv.lock')
    repo.rename(tmp_path / 'donor-unavailable')
    monkeypatch.setattr(paths, 'REPO', receiver)
    monkeypatch.setattr(paths, 'GAMES', receiver / 'games')
    calls.clear()
    assert build.build('sandbox', ['world'], echo=messages.append) == 0
    assert calls == []
    steps = build.load_recipe('sandbox').steps(build.Context('sandbox'))[:2]
    assert [build_products.records(step) for step in steps] == expected
    assert all('restored_from' in json.loads((receiver / 'build/sandbox/stamps' / (step.name + '.json')).read_text())
               for step in steps)
    assert build.build('sandbox', ['world'], force=True, echo=messages.append, verify=True) == 0
    assert [build_products.records(step) for step in steps] == expected
