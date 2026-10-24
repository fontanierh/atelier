"""Real incremental builds discover atomic exports without rerunning siblings."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build, build_checkpoints, paths
from atelier.build import Call, Product, Step


@pytest.fixture(autouse=True)
def independent_virtual_checkout(tmp_path, monkeypatch):
    # These tests inject a synthetic recipe/Context. The real source checkout now
    # has managed install metadata; it is not the virtual producer under test.
    from atelier.build_v2 import legacy_entry
    monkeypatch.setattr(legacy_entry, '_checkout', lambda: tmp_path)


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


@pytest.fixture
def protected_project(project, monkeypatch):
    """Real expansion, execution, protection and local stores; only native launch is replaced."""
    from atelier import build_cache
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {'rebuild_budget_seconds': 1})
    # No engine/workspace restore preparation is relevant to these portable fixture files.
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    base = build.load_recipe('fixture').steps
    script = project.repo / 'export.py'
    script.write_text('# selected export fixture; native execution is replaced below\n')
    def recipe(ctx):
        steps = base(ctx)
        for step in steps:
            if step.name not in ('region.plan', 'region'):
                step.commands = [build.Python(script)]
                step.inputs.append(script)
                step.cache = step.heavy = True
        return steps
    def run(ctx, step, command, log, *args, **kwargs):
        if isinstance(command, Call):return command.fn(ctx, log)
        project.trace.append(step.name)
        step.products[0].paths[0].write_bytes(step.inputs[0].read_bytes())
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=recipe))
    monkeypatch.setattr(build, 'run_command', run)
    protect = build_checkpoints.protect
    project.protected = []
    def observed(ctx, step, **kwargs):
        project.protected.append(step.name)
        return protect(ctx, step, **kwargs)
    monkeypatch.setattr(build_checkpoints, 'protect', observed)
    execute = build._build
    project.indices = []
    def executing(*args, **kwargs):
        project.indices.append(kwargs['index'])
        return execute(*args, **kwargs)
    monkeypatch.setattr(build, '_build', executing)
    project.store = build_cache.Store()
    project.recipe = recipe
    return project


def test_discovered_store_misses_inherit_only_original_bare_reason(protected_project):
    p = protected_project;messages=[]
    assert build.build('fixture', ['region'], rebuild_reason='approved original cold build', echo=messages.append) == 0
    assert p.trace == ['plan', 'region.One', 'region.Two', 'assemble']
    assert p.ctx.rebuild_reasons == {} and p.ctx.rebuild_reason == 'approved original cold build'
    assert set(p.ctx.rebuild_covered) == {'region.One', 'region.Two'}
    assert p.ctx.rebuild_upstream['region'] == {'region.plan', 'region.One', 'region.Two'}
    assert p.ctx.rebuild_upstream['region.One'] == set()  # Only after=planner, not a read/need reason.
    assert len(p.indices) == 2 and p.indices[0] is p.indices[1]
    for step in p.recipe(p.ctx):
        if step.cache:
            stamp=json.loads((p.ctx.stamps/(step.name+'.json')).read_text())
            assert p.store.action(stamp['fingerprint']).is_file()
    assert all('approved original cold build' in row for row in messages if 'rebuild reason applied' in row)


@pytest.mark.parametrize('reason', [None, 'region.plan=planner-only change'])
def test_discovered_store_misses_without_bare_reason_still_refuse(protected_project, reason):
    p = protected_project;messages=[]
    assert build.build('fixture', ['region'], rebuild_reason=reason, echo=messages.append) == 1
    assert p.trace == ['plan']
    assert {'region.One', 'region.Two'} <= set(p.protected)
    assert sum('unknown cold cost' in row for row in messages) == 2
    assert not (p.out/'One.fbx').exists() and not (p.out/'Two.fbx').exists()
    assert not p.ctx.rebuild_covered


def test_newly_discovered_existing_stamp_stays_protected(protected_project):
    p = protected_project;messages=[]
    p.ctx.stamps.mkdir(parents=True)
    # Retained expensive history exists even though the planner has not rediscovered it.
    (p.ctx.stamps/'region.One.json').write_text(json.dumps(dict(fingerprint='old',seconds=900)))
    assert build.build('fixture', ['region'], rebuild_reason='approved original cold build', echo=messages.append) == 1
    assert 'region.One' not in p.ctx.cold_at_launch
    assert p.trace == ['plan', 'region.Two']
    assert p.ctx.rebuild_covered == ['region.Two']
    assert any('900s retained rebuild estimate' in row for row in messages)
    assert not (p.out/'One.fbx').exists()


@pytest.mark.parametrize('reason', [None, 'approved original cold build'])
def test_discovered_cache_hits_restore_without_execution_or_protection(protected_project, reason):
    p = protected_project
    assert build.build('fixture', ['region'], rebuild_reason='approved original cold build') == 0
    # Simulate discovery in an empty receiving workspace; preserve the actual local stores.
    for name in ('region.plan', 'region.One', 'region.Two', 'region'):
        (p.ctx.stamps/(name+'.json')).unlink()
    for name in ('plan.json', 'One.fbx', 'Two.fbx', 'all.fbx'):(p.out/name).unlink()
    p.trace.clear();p.protected.clear();messages=[]
    assert build.build('fixture', ['region'], rebuild_reason=reason, echo=messages.append) == 0
    assert p.trace == []  # Planner, exports and assembly all restore from their real task entries.
    assert any('Discovering independently cached exports after region.plan' in row for row in messages)
    assert not {'region.One', 'region.Two'} & set(p.protected)
    assert not p.ctx.rebuild_covered
    for name in ('region.One', 'region.Two'):
        stamp=json.loads((p.ctx.stamps/(name+'.json')).read_text())
        assert stamp['restore_source'] in ('checkpoint', 'local')
    assert (p.out/'all.fbx').read_bytes() == b'OneTwo'
