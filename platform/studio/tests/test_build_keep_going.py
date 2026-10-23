"""Failed and interrupted builds: independent steps finish, and every exit prints the reuse summary."""
import json
from types import SimpleNamespace

import pytest

from atelier import build, paths


@pytest.fixture
def project(tmp_path, monkeypatch):
    out = tmp_path / 'build' / 'fixture'
    ctx = SimpleNamespace(game='fixture', out=out, stamps=out / 'stamps', logs=out / 'logs')
    behaviour, ran = {}, []

    def call(name):
        def run(ctx, log):
            ran.append(name)
            action = behaviour.get(name)
            if action is not None:
                raise action
            (out / name).write_text(name + ' output')
        return run

    steps = [build.Step('broken', [build.Call('broken', call('broken'))], outputs=[out / 'broken']),
             build.Step('dependent', [build.Call('dependent', call('dependent'))], needs=['broken'],
                        outputs=[out / 'dependent']),
             build.Step('later', [build.Call('later', call('later'))], needs=['dependent'], outputs=[out / 'later']),
             build.Step('independent', [build.Call('independent', call('independent'))], outputs=[out / 'independent'])]
    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(paths, 'build_root', lambda: out.parent)
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))
    messages = []
    return SimpleNamespace(ctx=ctx, out=out, behaviour=behaviour, ran=ran, messages=messages,
                           run=lambda **kwargs: build.build('fixture', echo=messages.append, **kwargs))


def stamped(p, name):
    return (p.ctx.stamps / (name + '.json')).exists()


def test_success_ends_with_the_reuse_summary(project):
    p = project
    assert p.run() == 0
    assert p.messages[-1].startswith('4 steps, 4 ran, 0 restored, 0 up to date, ')


def test_failure_keeps_building_independent_steps_and_lists_blocked_ones(project):
    p = project
    p.behaviour['broken'] = RuntimeError('fixture failure')
    assert p.run() == 1
    assert p.ran == ['broken', 'independent']
    assert stamped(p, 'independent') and not stamped(p, 'broken') and not stamped(p, 'dependent')
    assert 'FAILED steps: broken' in p.messages
    assert 'BLOCKED by a failed step: dependent (needs broken), later (needs dependent)' in p.messages
    assert p.messages[-1].startswith('4 steps, 1 ran, 0 restored, 0 up to date, 1 failed, 2 blocked, ')
    # After the fix, only the failed subtree runs.
    p.behaviour.clear(); p.ran.clear(); p.messages.clear()
    assert p.run() == 0
    assert p.ran == ['broken', 'dependent', 'later']
    assert p.messages[-1].startswith('4 steps, 3 ran, 0 restored, 1 up to date, ')


def test_fail_fast_stops_at_the_first_failure_with_a_summary(project):
    p = project
    p.behaviour['broken'] = RuntimeError('fixture failure')
    assert p.run(fail_fast=True) == 1
    assert p.ran == ['broken'] and not stamped(p, 'independent')
    assert p.messages[-1].startswith('4 steps, 0 ran, 0 restored, 0 up to date, 1 failed, 3 not reached, ')


@pytest.mark.parametrize('signal', [KeyboardInterrupt(), SystemExit(143)], ids=['SIGINT', 'SIGTERM'])
def test_interrupt_keeps_finished_steps_and_prints_the_summary(project, signal):
    p = project
    p.behaviour['independent'] = signal
    with pytest.raises(type(signal)):
        p.run()
    assert stamped(p, 'broken') and stamped(p, 'later') and not stamped(p, 'independent')
    assert json.loads((p.ctx.stamps / 'later.json').read_text())['fingerprint']
    assert 'BUILD INTERRUPTED during independent; completed steps stay published' in p.messages
    assert p.messages[-1].startswith('4 steps, 3 ran, 0 restored, 0 up to date, 1 not reached, ')


@pytest.mark.parametrize('stop', ['failure', 'SIGINT', 'SIGTERM'])
def test_checkpoint_builds_publish_finished_steps_whatever_stops_them(tmp_path, monkeypatch, stop):
    from atelier import build_cache, build_checkpoints, checkpoint_actions as actions, checkpoint_store as cp
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture', logs=repo / 'build/fixture/logs',
                          stamps=repo / 'build/fixture/stamps', cook_mode=build.CookMode.DEFAULT)
    steps = []
    for name in ('mesh', 'stopper'):
        source = repo / (name + '.txt'); source.write_text(name)
        script = repo / (name + '.py'); script.write_text('# ' + name)
        steps.append(build.Step(name, [build.Python(script)], inputs=[source],
                                products=[build.Product(name, (ctx.out / name,))]))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: dict(tool='fixed'))
    signal = {'failure': RuntimeError('fixture failure'), 'SIGINT': KeyboardInterrupt(), 'SIGTERM': SystemExit(143)}[stop]

    def run(ctx, step, command, log, *args, **kw):
        if step.name == 'stopper':
            raise signal
        (ctx.out / step.name).mkdir(parents=True)
        (ctx.out / step.name / 'data').write_text(step.name)
    monkeypatch.setattr(build, 'run_command', run)
    messages = []
    if stop == 'failure':
        assert build.build('fixture', echo=messages.append) == 1
    else:
        with pytest.raises(type(signal)):
            build.build('fixture', echo=messages.append)
    stamp = json.loads((ctx.stamps / 'mesh.json').read_text())
    assert actions.entry_path(cp.Store('fixture'), stamp['checkpoint_key']).is_file()
    from atelier.checkpoint_manifest import folder
    assert (folder(ctx.out) / 'tasks/mesh.json').is_file()  # Retention record for the finished step.
    assert messages[-1].startswith('2 steps, 1 ran, 0 restored, 0 up to date, ')


def test_a_current_certificate_without_its_stamp_file_is_written_back(project, monkeypatch):
    """A migrated or otherwise recovered current certificate must land on disk: the cook reads stamp files."""
    from atelier import build_plan
    p = project
    assert p.run() == 0
    stamp = p.ctx.stamps / 'independent.json'
    saved = json.loads(stamp.read_text())
    stamp.unlink()
    real = build_plan.read_stamp
    served = []

    def recovered(path):
        if path == stamp and not served:  # The certificate arrives from elsewhere, as a migration would supply it.
            served.append(path)
            return dict(saved)
        return real(path)

    monkeypatch.setattr(build_plan, 'read_stamp', recovered)
    p.ran.clear(); p.messages.clear()
    assert p.run() == 0
    assert 'independent' not in p.ran
    assert json.loads(stamp.read_text()) == saved
