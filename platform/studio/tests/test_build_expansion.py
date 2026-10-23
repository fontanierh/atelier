"""Real incremental builds discover atomic exports without rerunning siblings."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, paths
from atelier.build import Call, Product, Step


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path.resolve()
    (repo / 'uv.lock').write_text('fixture lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: None)
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    out = repo / 'build/fixture'
    ctx = SimpleNamespace(game='fixture', out=out, logs=out / 'logs', stamps=out / 'stamps',
                          cook_mode=build.CookMode.DEFAULT)
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    spec = repo / 'parts.json'; spec.write_text(json.dumps({'One': 'one', 'Two': 'two'}))
    trace = []
    def recipe(ctx):
        plan = out / 'plan.json'
        def discover(ctx, log):
            trace.append('plan')
            plan.write_text(spec.read_text())
        result = [Step('region.plan', [Call('discover', discover)], inputs=[spec],
                       products=[Product('region.plan', (plan,))], replan=True)]
        products, destinations = [], []
        rows = json.loads(plan.read_text()) if plan.is_file() else {}
        for name, contents in rows.items():
            source = repo / (name + '.txt')
            # Separate committed logical inputs, present before recipe evaluation.
            target = out / (name + '.fbx')
            def export(ctx, log, name=name, source=source, target=target):
                trace.append(name)
                target.write_bytes(source.read_bytes())
            product = 'region.' + name
            result.append(Step('region.' + name, [Call('export ' + name, export)], inputs=[source],
                               products=[Product(product, (target,))], after=['region.plan']))
            products.append(product); destinations.append(target)
        def assemble(ctx, log):
            if not destinations:
                raise ValueError('missing completed export plan')
            trace.append('assemble')
            (out / 'all.fbx').write_bytes(b''.join(p.read_bytes() for p in destinations))
        result.append(Step('region', [Call('assemble', assemble)], needs=['region.plan'],
                           reads=products, outputs=[out / 'all.fbx']))
        return result
    for name in ('One', 'Two'): (repo / (name + '.txt')).write_text(name)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=recipe))
    return SimpleNamespace(repo=repo, out=out, spec=spec, trace=trace, ctx=ctx)


def test_cold_build_discovers_real_children_before_assembly(project):
    assert build.build('fixture', ['region']) == 0
    assert project.trace == ['plan', 'One', 'Two', 'assemble']
    assert (project.out / 'all.fbx').read_bytes() == b'OneTwo'
    assert build.build('fixture', ['region']) == 0
    assert project.trace == ['plan', 'One', 'Two', 'assemble']


def test_one_logical_edit_does_not_regenerate_another_part(project):
    assert build.build('fixture') == 0
    project.trace.clear()
    (project.repo / 'One.txt').write_text('edited One')
    assert build.build('fixture') == 0
    assert project.trace == ['One', 'assemble']
    assert (project.out / 'all.fbx').read_bytes() == b'edited OneTwo'


def test_replanned_roster_keeps_unchanged_atomic_products_current(project):
    assert build.build('fixture') == 0
    project.trace.clear()
    (project.repo / 'Three.txt').write_text('Three')
    project.spec.write_text(json.dumps({'One': 'one', 'Two': 'two', 'Three': 'three'}))
    assert build.build('fixture') == 0
    assert project.trace == ['plan', 'Three', 'assemble']
    assert (project.out / 'all.fbx').read_bytes() == b'OneTwoThree'


def test_forced_planner_is_not_forced_again_on_its_internal_expansion_pass(project):
    assert build.build('fixture', force=True) == 0
    assert project.trace == ['plan', 'One', 'Two', 'assemble']


def test_force_suppression_is_scoped_to_one_expansion_invocation(project):
    for _ in range(2):
        assert build.build('fixture', force=True) == 0
        assert not hasattr(project.ctx, 'expansion_completed')
        assert not hasattr(project.ctx, 'expansion_heavy_commands')
    assert project.trace == ['plan', 'One', 'Two', 'assemble'] * 2


def test_heavy_budget_spans_planner_expansion(project, monkeypatch):
    base = build.load_recipe('fixture').steps
    script = project.repo / 'planner.py'; script.write_text('# selected source planner')
    def recipe(ctx):
        steps = base(ctx)
        for step in steps:
            if step.name == 'region.plan' or step.name.startswith('region.'):
                step.commands = [build.Blender(script, (step.name,), factory_startup=True, threads=3)]
                step.inputs.append(script)
                step.heavy = True
        return steps
    def run(ctx, step, command, log, *a, **kw):
        if isinstance(command, build.Blender):
            project.trace.append(step.name)
            if step.name == 'region.plan':
                (project.out / 'plan.json').write_text(project.spec.read_text())
            else:
                (project.out / (step.name.split('.')[-1] + '.fbx')).write_bytes(b'mesh')
        else:
            return command.fn(ctx, log)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=recipe))
    monkeypatch.setattr(build, 'run_command', run)
    assert build.build('fixture', max_heavy_commands=1) == 75
    assert project.trace == ['region.plan']
    assert (project.out / 'stamps/region.plan.json').exists()
    assert not (project.out / 'One.fbx').exists()
