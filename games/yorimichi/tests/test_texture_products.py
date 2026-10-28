"""Real small texture audit/cache checks; no native tools, generated references or shared cache."""
from dataclasses import replace
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_products


RECIPE = build.load_recipe('yorimichi')


def context(directory):
    ctx = SimpleNamespace(game='yorimichi', out=directory / 'yorimichi', uproject=None)
    ctx.logs, ctx.stamps = ctx.out / 'logs', ctx.out / 'stamps'
    ctx.env = lambda extra=(): {**os.environ, 'ATELIER_BUILD_ROOT': str(directory), **dict(extra)}
    return ctx


def test_every_legacy_texture_has_one_exact_owner_and_the_aggregate_reads_them(tmp_path):
    ctx = context(tmp_path)
    steps = RECIPE.texture_steps(ctx)
    graph = build_products.Graph(steps)
    aggregate = graph.by_name['world.textures']
    textures = [step for step in steps if step.name.startswith('world.textures.')]
    assert len(textures) == 22 and len(set(aggregate.reads)) == 22
    assert aggregate.commands == [] and aggregate.products == [] and aggregate.outputs == []
    roots = []
    for step in textures:
        assert step.cache is True and step.audit is True and step.heavy is False
        product, = step.products
        output, = product.paths
        assert output.parent == ctx.out / 'textures'
        assert step.outputs == [output] and product.name in aggregate.reads
        assert graph.owners[product.name] == step.name
        roots.append(output)
    assert len(set(roots)) == 22
    assert {s.name for s in graph.select(['world.textures'])} == {'world.textures', *(s.name for s in textures)}
    assert [s.name for s in graph.select(['world.textures.white'])] == ['world.textures.white']


def test_only_asset_backed_textures_declare_those_images(tmp_path):
    steps = RECIPE.texture_steps(context(tmp_path))
    image_dir = RECIPE.ASSETS / 'environment/textures'
    declarations = {step.name: {p.name for p in step.inputs if p.parent == image_dir}
                    for step in steps if step.products}
    assert {name: files for name, files in declarations.items() if files} == {
        'world.textures.bark': {'tree-bark.jpg'},
        'world.textures.bark_olive': {'tree-bark.jpg'},
        'world.textures.ground_detail': {'tuscan-ground.jpg', 'tuscan-ground.provenance.json'},
    }


@pytest.fixture
def actual_build(tmp_path, monkeypatch, unmanaged_builder_checkout):
    for name in ('ATELIER_ARTIFACT_URL', 'ATELIER_ARTIFACT_TRUST', 'ATELIER_ARTIFACT_TIMEOUT',
                 'ATELIER_PYTHON', 'PYTHONPATH', 'PYTHONHOME'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('ATELIER_CACHE', str(tmp_path / 'cache'))
    monkeypatch.setenv('OPENBLAS_NUM_THREADS', '1')
    monkeypatch.setenv('OMP_NUM_THREADS', '1')
    state = SimpleNamespace(ctx=context(tmp_path / 'first'), calls=[], consumers=[], selected=('white', 'concrete'))
    spec = tmp_path / 'white.json'
    spec.write_bytes((RECIPE.WORLD / 'textures/white.json').read_bytes())
    state.spec = spec
    def steps(ctx):
        result = []
        for step in RECIPE.texture_steps(ctx):
            if step.name not in {f'world.textures.{name}' for name in state.selected}:
                continue
            if step.name == 'world.textures.white':
                original = RECIPE.WORLD / 'textures/white.json'
                command, = step.commands
                step = replace(step, inputs=[spec if p == original else p for p in step.inputs],
                               commands=[build.Python(command.script, tuple(spec if p == original else p for p in command.args))])
            result.append(step)
        return result
    state.steps = steps
    monkeypatch.setattr(build, 'Context', lambda game: state.ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=steps))
    run = build.run_command
    def observed(ctx, step, command, *args, **kwargs):
        state.calls.append(step.name)
        return run(ctx, step, command, *args, **kwargs)
    monkeypatch.setattr(build, 'run_command', observed)
    def execute(**kwargs):
        monkeypatch.setenv('ATELIER_BUILD_ROOT', str(state.ctx.out.parent))
        state.log = []
        return build.build('yorimichi', echo=state.log.append, **kwargs)
    state.run = execute
    def why():
        logs = ''.join(f'\n--- {path.name} ---\n{path.read_text()[-4000:]}'
                       for path in sorted(state.ctx.logs.glob('*.log')))
        return '\n'.join(state.log) + logs
    state.why = why
    return state


def test_actual_audited_textures_restore_in_a_different_directory_without_execution(actual_build, tmp_path, monkeypatch):
    p = actual_build
    assert p.run() == 0, p.why()
    assert set(p.calls) == {'world.textures.white', 'world.textures.concrete'}
    expected = {product.paths[0].name: product.paths[0].read_bytes()
                for step in p.steps(p.ctx) for product in step.products}
    for step in p.steps(p.ctx):
        stamp = json.loads((p.ctx.stamps / f'{step.name}.json').read_text())
        assert stamp['audit_receipt']['execution'] == 'audited-python-v1'
    p.calls.clear()
    assert p.run() == 0 and p.calls == [], p.why()  # Warm stamps.
    original = p.ctx.out
    p.ctx = context(tmp_path / 'receiver')
    monkeypatch.setattr(build, 'run_command', lambda *args, **kwargs: pytest.fail('cache restoration executed a command'))
    assert p.run() == 0, p.why()
    assert {path.name: path.read_bytes() for path in (p.ctx.out / 'textures').iterdir()} == expected
    for step in p.steps(p.ctx):
        stamp = json.loads((p.ctx.stamps / f'{step.name}.json').read_text())
        assert 'restored_from' in stamp and 'audit_receipt' not in stamp
    # Restored bytes are independent from the donor's mutable outputs.
    (p.ctx.out / 'textures/T_white.png').write_bytes(b'changed receiver')
    assert (original / 'textures/T_white.png').read_bytes() == expected['T_white.png']


def test_one_spec_edit_rebuilds_one_texture_and_its_real_consumers(actual_build, monkeypatch):
    p = actual_build
    source_steps = p.steps
    def steps(ctx):
        return [*source_steps(ctx), build.Step('world.textures', [], reads=['texture.white', 'texture.concrete']),
                build.Step('consume.white', [build.Call('white', lambda ctx, log: p.consumers.append('white'))], reads=['texture.white']),
                build.Step('consume.concrete', [build.Call('concrete', lambda ctx, log: p.consumers.append('concrete'))], reads=['texture.concrete']),
                build.Step('consume.legacy', [build.Call('legacy', lambda ctx, log: p.consumers.append('legacy'))], needs=['world.textures'])]
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=steps))
    assert p.run() == 0, p.why()
    concrete = (p.ctx.out / 'textures/T_concrete.jpg').read_bytes()
    p.calls.clear(); p.consumers.clear()
    value = json.loads(p.spec.read_text())
    value['options']['colour'] = [250, 251, 252]
    p.spec.write_text(json.dumps(value))
    assert p.run() == 0, p.why()
    assert set(p.calls) == {'world.textures.white', 'consume.white', 'consume.legacy'}
    assert set(p.consumers) == {'white', 'legacy'}
    assert (p.ctx.out / 'textures/T_concrete.jpg').read_bytes() == concrete
