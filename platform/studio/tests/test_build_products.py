"""Small, serial build scenarios: no external tools, render locks or shared cache."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_plan
from atelier.build import Call, Product, Step
from atelier.build_products import Graph, inventory


def test_package_sidecars_track_presence_bytes_and_exclusive_ownership(tmp_path):
    package, sidecar = tmp_path / 'Mesh.uasset', tmp_path / 'Mesh.ubulk'
    package.write_bytes(b'package')
    product = Product('mesh', (package,), optional_paths=(sidecar,))
    absent = inventory(product)
    assert absent['files']['1/.'] == {'kind': 'absent'}
    sidecar.write_bytes(b'bulk')
    present = inventory(product)
    assert present != absent
    sidecar.write_bytes(b'edit')
    assert inventory(product) != present
    owner = Step('mesh', [], products=[product])
    other = Step('bulk', [], products=[Product('other', (sidecar,))])
    with pytest.raises(ValueError, match='Overlapping product ownership'):
        Graph([owner, other])
    package.unlink()
    with pytest.raises(OSError):
        inventory(product)


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    ctx = SimpleNamespace(game='fixture', out=root / 'out', logs=root / 'out/logs', stamps=root / 'out/stamps')
    steps, calls = [], []
    monkeypatch.setattr(build, 'Context', lambda game, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))

    def add(name, outputs, *, inputs=(), reads=(), references=()):
        def generate(ctx, log):
            calls.append(name)
            for path, contents in outputs:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents() if callable(contents) else contents)
        step = Step(name, [Call(name, generate)], inputs=list(inputs), reads=list(reads),
                    references=list(references),
                    products=[Product(f'{name}.{path.stem}', (path,)) for path, _ in outputs])
        steps.append(step)
        return step

    return SimpleNamespace(ctx=ctx, steps=steps, calls=calls, add=add, root=root,
                           run=lambda: build.build('fixture', echo=lambda message: None))


def test_only_consumers_of_changed_product_rebuild(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('first')
    p.add('generate', [(p.ctx.out / 'a.txt', source.read_text), (p.ctx.out / 'b.txt', 'stable')], inputs=[source])
    p.add('read_a', [(p.ctx.out / 'used_a.txt', 'a')], reads=['generate.a'])
    p.add('read_b', [(p.ctx.out / 'used_b.txt', 'b')], reads=['generate.b'])
    assert p.run() == 0
    p.calls.clear()
    assert p.run() == 0 and p.calls == []
    source.write_text('second')
    assert p.run() == 0 and p.calls == ['generate', 'read_a']


def test_identical_output_stops_rebuild_cascade(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('one')
    p.add('generate', [(p.ctx.out / 'stable.txt', 'stable')], inputs=[source])
    p.add('consumer', [(p.ctx.out / 'used.txt', 'used')], reads=['generate.stable'])
    assert p.run() == 0
    p.calls.clear(); source.write_text('two')
    assert p.run() == 0 and p.calls == ['generate']


def test_missing_or_corrupt_leaf_is_repaired_before_consuming(project):
    p = project
    step = p.add('generate', [(p.ctx.out / 'bundle/a.txt', 'a'), (p.ctx.out / 'bundle/b.txt', 'b')])
    step.products = [Product('bundle', (p.ctx.out / 'bundle',))]
    p.add('consumer', [(p.ctx.out / 'used.txt', 'used')], reads=['bundle'])
    assert p.run() == 0
    p.calls.clear(); (p.ctx.out / 'bundle/b.txt').unlink()
    assert p.run() == 0 and p.calls == ['generate']
    p.calls.clear(); (p.ctx.out / 'bundle/a.txt').write_text('wrong')
    assert p.run() == 0 and p.calls == ['generate']


def test_reference_cycle_is_included_without_content_dependency(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('one')
    a = p.add('a', [(p.ctx.out / 'a.txt', source.read_text)], inputs=[source], references=['b.b'])
    b = p.add('b', [(p.ctx.out / 'b.txt', 'b')], references=['a.a'])
    assert set(s.name for s in Graph([a, b]).select(['a'])) == {'a', 'b'}
    assert p.run() == 0
    p.calls.clear(); source.write_text('two')
    assert p.run() == 0 and p.calls == ['a']


def test_plan_leaves_fresh_checkout_untouched(project):
    p = project
    p.add('generate', [(p.ctx.out / 'mesh.txt', 'mesh')])
    report = build_plan.inspect(p.ctx, p.steps)
    assert report['steps'][0]['status'] == 'run'
    assert not p.ctx.out.exists() and p.calls == []


def test_plan_marks_unobserved_products_conditional(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('one')
    p.add('generate', [(p.ctx.out / 'mesh.txt', 'same')], inputs=[source])
    p.add('consumer', [(p.ctx.out / 'used.txt', 'used')], reads=['generate.mesh'])
    assert p.run() == 0
    source.write_text('two')
    report = build_plan.inspect(p.ctx, p.steps)
    assert [s['status'] for s in report['steps']] == ['run', 'check-after-build']
    assert any('source.txt' in reason for reason in report['steps'][0]['reasons'])


def test_plan_keeps_changed_legacy_cutoff_results_conditional(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('one')
    generator = p.add('generate', [(p.ctx.out / 'mesh.txt', 'same')], inputs=[source])
    generator.products = []; generator.outputs = [p.ctx.out / 'mesh.txt']; generator.cutoff = True
    consumer = p.add('consumer', [(p.ctx.out / 'used.txt', 'used')])
    consumer.products = []; consumer.needs = ['generate']
    assert p.run() == 0
    source.write_text('two')
    assert [s['status'] for s in build_plan.inspect(p.ctx, p.steps)['steps']] == ['run', 'check-after-build']


def test_unrelated_corrupt_stamp_cannot_block_a_selected_build(project):
    p = project
    p.add('wanted', [(p.ctx.out / 'wanted.txt', 'wanted')])
    p.add('other', [(p.ctx.out / 'other.txt', 'other')])
    p.ctx.stamps.mkdir(parents=True)
    (p.ctx.stamps / 'other.json').write_text('interrupted JSON')
    assert build.build('fixture', ['wanted'], echo=lambda message: None) == 0
    assert p.calls == ['wanted']


def test_plan_handles_a_malformed_product_record(project):
    p = project
    p.add('generate', [(p.ctx.out / 'mesh.txt', 'same')])
    assert p.run() == 0
    path = p.ctx.stamps / 'generate.json'
    stamp = json.loads(path.read_text()); stamp['products'] = {'generate.mesh': {}}
    path.write_text(json.dumps(stamp))
    assert build_plan.inspect(p.ctx, p.steps)['steps'][0]['status'] == 'run'


def test_changed_inputs_during_run_are_not_certified(project):
    p = project
    source = p.root / 'source.txt'; source.write_text('one')
    step = p.add('generate', [(p.ctx.out / 'mesh.txt', 'mesh')], inputs=[source])
    step.commands.append(Call('mutate', lambda ctx, log: source.write_text('two')))
    assert p.run() == 1
    assert not (p.ctx.stamps / 'generate.json').exists()


def test_missing_product_input_cannot_be_built_or_accepted_as_current(project):
    p = project
    source = p.root / 'source.txt'
    p.add('generate', [(p.ctx.out / 'mesh.txt', 'constant output')], inputs=[source])
    assert p.run() == 1 and p.calls == []
    source.write_text('present')
    assert p.run() == 0
    p.calls.clear(); source.unlink()
    report = build_plan.inspect(p.ctx, p.steps)
    assert any('required input missing' in reason for reason in report['steps'][0]['reasons'])
    assert p.run() == 1 and p.calls == []


@pytest.mark.parametrize('kind', ['duplicate', 'overlap', 'unknown', 'cycle'])
def test_invalid_graphs_fail_before_execution(tmp_path, kind):
    a = Step('a', [], products=[Product('a.mesh', (tmp_path / 'a',))])
    b = Step('b', [], products=[Product('b.mesh', (tmp_path / 'b',))])
    if kind == 'duplicate': b.name = 'a'
    if kind == 'overlap': b.products = [Product('b.mesh', (tmp_path / 'a/child',))]
    if kind == 'unknown': b.reads = ['missing']
    if kind == 'cycle': a.reads, b.reads = ['b.mesh'], ['a.mesh']
    with pytest.raises(ValueError): Graph([a, b])


def test_symlink_and_unexpected_members_are_not_accepted(tmp_path):
    root = tmp_path.resolve() / 'bundle'; root.mkdir()
    item = root / 'file'; item.write_text('first')
    product = Product('bundle', (root,))
    before = inventory(product)
    (root / 'new').write_text('extra')
    assert inventory(product) != before
    (root / 'link').symlink_to(item)
    with pytest.raises(ValueError, match='linked'): inventory(product)


def test_system_style_symlinked_parent_is_allowed_but_product_links_are_not(tmp_path):
    real = tmp_path / 'real'; real.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(real, target_is_directory=True)
    output = real / 'mesh.txt'; output.write_text('mesh')
    assert inventory(Product('mesh', (alias / 'mesh.txt',))) == inventory(Product('mesh', (output,)))
    (alias / 'linked.txt').symlink_to(output)
    with pytest.raises(ValueError, match='linked'): inventory(Product('mesh', (alias / 'linked.txt',)))


@pytest.mark.parametrize('source', ['output', 'output/leaf', '.'])
def test_product_cannot_overlap_its_own_inputs(tmp_path, source):
    step = Step('bad', [], inputs=[tmp_path / source], products=[Product('mesh', (tmp_path / 'output',))])
    with pytest.raises(ValueError, match='input overlaps'): Graph([step])


def test_directory_addition_during_hashing_is_not_certified(tmp_path, monkeypatch):
    from atelier import build_products
    root = tmp_path / 'bundle'; root.mkdir()
    (root / 'first').write_text('first')
    digest = build_products.file_digest
    def mutate(path):
        (root / 'added').write_text('late')
        return digest(path)
    monkeypatch.setattr(build_products, 'file_digest', mutate)
    with pytest.raises(ValueError, match='changed during inventory'):
        inventory(Product('bundle', (root,)))


def test_old_stamp_is_readable_and_new_stamp_records_durations(project):
    p = project
    p.add('generate', [(p.ctx.out / 'mesh.txt', 'mesh')])
    assert p.run() == 0
    stamp = json.loads((p.ctx.stamps / 'generate.json').read_text())
    assert stamp['commands'][0]['kind'] == 'Call'
    assert stamp['commands'][0]['seconds'] >= 0
    assert stamp['products']['generate.mesh']['inventory']['schema'] == 1
