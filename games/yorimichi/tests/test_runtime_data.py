"""The staged runtime files retain their source bytes and optional-content cleanup."""
from dataclasses import replace
import io
import os
from types import SimpleNamespace

import pytest

from atelier import build


@pytest.mark.parametrize('optional_park', [False, True])
def test_staging_copies_required_sources_and_preserves_unrelated_data(tmp_path, monkeypatch, optional_park):
    recipe = build.load_recipe('yorimichi')
    data = recipe.runtime_data
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path / 'build')
    destination = tmp_path / 'Content' / 'Data'
    monkeypatch.setattr(data, 'REGIONS', tmp_path / 'regions')
    monkeypatch.setattr(data, 'ASSETS', tmp_path / 'assets')
    monkeypatch.setattr(data.paths, 'content_data', lambda game: destination)
    if optional_park:
        source = data.ASSETS / 'communitypark/megapark-textured.glb'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'library source')
    expected = {}
    for rel in data.staged(ctx.out):
        source = data.staged_source(ctx.out, rel)
        source.parent.mkdir(parents=True, exist_ok=True)
        expected[rel] = rel.encode()
        source.write_bytes(expected[rel])
        os.utime(source, ns=(1_000_000_000, 2_000_000_000))
    # The committed skatepark source wins over any similarly named generated file.
    (ctx.out / 'skatepark').mkdir(exist_ok=True)
    (ctx.out / 'skatepark/park.json').write_bytes(b'wrong generated park')
    retained = destination / 'SkateRide/clips.json'
    retained.parent.mkdir(parents=True)
    retained.write_bytes(b'keep source data')
    stale = destination / 'communitypark/park.json'
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_bytes(b'previous park')

    log = io.StringIO()
    recipe.stage_data(ctx, log)

    for rel, content in expected.items():
        target = destination / rel
        assert target.read_bytes() == content
        assert target.stat().st_mtime_ns == 2_000_000_000
    assert retained.read_bytes() == b'keep source data'
    assert stale.exists() == optional_park
    assert log.getvalue().splitlines() == [f'staged {rel}' for rel in data.staged(ctx.out)]


def test_staging_implementation_is_a_narrow_fingerprint_input(tmp_path):
    recipe = build.load_recipe('yorimichi')
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)
    steps = recipe.steps(ctx)
    stage = next(step for step in steps if step.name == 'data.stage')
    implementation = recipe.GAME / 'runtime_data.py'
    assert implementation in stage.inputs
    assert stage.commands[0].fn is recipe.runtime_data.stage_data
    assert all(implementation not in step.inputs for step in steps if step.name != 'data.stage')

    source = tmp_path / 'runtime_data.py'
    source.write_bytes(implementation.read_bytes())
    contract = replace(stage, inputs=[source])
    done = {name: name for name in stage.needs}
    previous = build.fingerprint(contract, done)
    source.write_text(source.read_text() + '\n# a staging implementation change\n')
    assert build.fingerprint(contract, done) != previous
