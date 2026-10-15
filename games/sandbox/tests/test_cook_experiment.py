"""Offline sandbox receipt gates; native modern-cook parity and speed remain untested."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, provenance
from atelier.build_cook import CookMode


def helper():
    path = Path(__file__).parents[1] / 'tools/cook_experiment.py'
    spec = importlib.util.spec_from_file_location('sandbox_cook_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cooked(tmp_path, monkeypatch):
    tool = helper()
    ctx = SimpleNamespace(out=tmp_path, logs=tmp_path / 'logs', cook_mode=CookMode.INCREMENTAL,
                          cook_source=dict(fingerprint='source', mode='modern-incremental'))
    monkeypatch.setattr(tool, 'source_snapshot', lambda _: dict(ctx.cook_source))
    app = ctx.out / 'package/archive/Mac/Fixture.app'
    for name, data in {'Contents/MacOS/Fixture': b'executable', 'Contents/UE/Fixture/Content/Paks/pak.utoc': b'index',
                       'Contents/UE/Fixture/Content/Paks/pak.ucas': b'container'}.items():
        path = app / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    report = dict(validated=True, requested='modern-incremental', modern_dependencies=True,
                  cook_completed=True, invocation_id='fresh')
    ctx.cook_observation = report
    path = ctx.logs / 'unreal.cook.guard/cook-observation.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(report))
    return tool, ctx, app, path


def test_sandbox_receipt_requires_current_observation_and_complete_inventory(cooked):
    tool, ctx, app, path = cooked
    tool.finish(ctx, io.StringIO())
    receipt = json.loads((ctx.out / 'package/cook.json').read_text())
    assert receipt['experimental'] and receipt['native_parity'] is False
    assert receipt['cook']['invocation_id'] == 'fresh' and len(receipt['files']) == 3
    assert len(list((ctx.out / 'cook-experiments').glob('*.json'))) == 1
    assert tool.present(ctx.out / 'package')
    (app / 'Contents/MacOS/Fixture').write_bytes(b'changed')
    assert not tool.present(ctx.out / 'package')


@pytest.mark.parametrize('damage', ['stale', 'mode', 'legacy', 'incomplete', 'unvalidated', 'container'])
def test_unsupported_or_incomplete_cook_cannot_publish_receipt(cooked, damage):
    tool, ctx, app, path = cooked
    report = json.loads(path.read_text())
    if damage == 'stale':
        report['invocation_id'] = 'old'
    elif damage == 'mode':
        report['requested'] = 'modern-full'
    elif damage == 'legacy':
        report['modern_dependencies'] = False
    elif damage == 'incomplete':
        report['cook_completed'] = False
    elif damage == 'unvalidated':
        report['validated'] = False
    else:
        (app / 'Contents/UE/Fixture/Content/Paks/pak.ucas').unlink()
    path.write_text(json.dumps(report))
    with pytest.raises(RuntimeError):
        tool.finish(ctx, io.StringIO())
    assert not (ctx.out / 'package/cook.json').exists()


def test_mode_survives_real_sandbox_source_snapshot_recipe_reload(tmp_path, monkeypatch):
    ctx = build.Context('sandbox', create=False, cook_mode=CookMode.FULL)
    ctx.out, ctx.stamps = tmp_path, tmp_path / 'stamps'
    ctx.stamps.mkdir()
    ctx.unreal_root = tmp_path / 'engine'
    version = ctx.unreal_root / 'Engine/Build/Build.version'
    version.parent.mkdir(parents=True)
    version.write_text('{"MajorVersion":5,"MinorVersion":8}')
    for name in ('unreal.compile', 'unreal.level'):
        (ctx.stamps / (name + '.json')).write_text('{"fingerprint":"prerequisite"}')
    monkeypatch.setattr(provenance, 'head', lambda: 'a' * 40)
    monkeypatch.setattr(provenance, 'status', lambda **kwargs: '')
    tool = helper()
    before = tool.source_snapshot(ctx)
    assert before == tool.source_snapshot(ctx) and before['mode'] == 'modern-full'
    ctx.cook_mode = CookMode.INCREMENTAL
    after = tool.source_snapshot(ctx)
    assert before['fingerprint'] != after['fingerprint'] and after['mode'] == 'modern-incremental'
    plan = build.order(build.load_recipe('sandbox').steps(ctx), [])
    assert 'unreal.cook' not in [step.name for step in plan]


def test_preparation_invalidates_prior_receipt_but_keeps_same_checkout_cooker_state(cooked, monkeypatch):
    tool, ctx, app, path = cooked
    saved = ctx.out / 'retained-Saved'
    saved.mkdir()
    (saved / 'state').write_bytes(b'warm state')
    tool.finish(ctx, io.StringIO())
    tool.prepare(ctx, io.StringIO())
    assert not (ctx.out / 'package/cook.json').exists() and not app.exists()
    assert (saved / 'state').read_bytes() == b'warm state'
