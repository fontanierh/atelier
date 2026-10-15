"""Bounded scheduling boundaries with mocked commands; no native tools or admission."""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

from atelier import build, cli, paths


@pytest.fixture
def project(tmp_path, monkeypatch):
    out = tmp_path / 'build' / 'fixture'
    ctx = SimpleNamespace(game='fixture', out=out, stamps=out / 'stamps', logs=out / 'logs',
                          env=lambda extra: dict(extra))
    script = tmp_path / 'import.py'
    script.write_text('# fixture import')
    steps, prepared, launched = [], [], []
    for name in ('first', 'second', 'third'):
        steps.append(build.Step(name, [build.UnrealScript(script, 'completed')], heavy=True,
                                products=[build.Product(name, (out / name,))]))

    @contextmanager
    def prepare(command, ctx):
        prepared.append(command)
        yield ['mock-command'], ()

    def guarded(argv, folder, **kwargs):
        name = folder.name.removesuffix('.guard')
        launched.append(name)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'stdout.log').write_text('completed')
        (out / name).write_text('new output')
        kwargs['on_slot']('big', '')
        return 0

    monkeypatch.setattr(paths, 'REPO', tmp_path)
    monkeypatch.setattr(paths, 'build_root', lambda: out.parent)
    monkeypatch.setattr(build, 'Context', lambda *args, **kwargs: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda game: SimpleNamespace(steps=lambda ctx: steps))
    monkeypatch.setattr(build.UnrealScript, 'prepared', prepare)
    monkeypatch.setattr(build.guarded, 'run', guarded)
    messages = []
    return SimpleNamespace(ctx=ctx, steps=steps, prepared=prepared, launched=launched, messages=messages,
                           run=lambda **kwargs: build.build('fixture', echo=messages.append, **kwargs))


def test_budget_yields_before_preparation_and_preserves_unstarted_outputs(project):
    p = project
    p.ctx.stamps.mkdir(parents=True)
    stamp = p.ctx.stamps / 'second.json'
    stamp.write_text(json.dumps({'fingerprint': 'old'}))
    (p.ctx.out / 'second').write_text('old owned output')
    before = stamp.read_bytes()
    assert p.run(max_heavy_commands=1) == 75
    assert p.launched == ['first'] and p.prepared == [p.steps[0].commands[0]]
    assert (p.ctx.stamps / 'first.json').exists()
    assert stamp.read_bytes() == before
    assert (p.ctx.out / 'second').read_text() == 'old owned output'
    assert any('BUILD YIELDED' in message and 'second' in message for message in p.messages)


def test_resume_skips_completed_stamps_and_final_command_succeeds(project):
    p = project
    assert p.run(max_heavy_commands=1) == 75
    first = (p.ctx.stamps / 'first.json').read_bytes()
    assert p.run(max_heavy_commands=1) == 75
    assert (p.ctx.stamps / 'first.json').read_bytes() == first
    assert p.run(max_heavy_commands=1) == 0
    assert p.launched == ['first', 'second', 'third']
    assert p.run(max_heavy_commands=1) == 0
    assert p.launched == ['first', 'second', 'third']


def test_plain_prerequisites_and_calls_continue_after_budget(project):
    p = project
    called = []
    plain = build.Step('plain', [build.Call('plain', lambda ctx, log: called.append('plain'))])
    inline = build.Step('inline', [build.Call('inline', lambda ctx, log: called.append('inline'))], heavy=True)
    p.steps[1:1] = [plain, inline]
    assert p.run(max_heavy_commands=1) == 75
    assert called == ['plain', 'inline']
    assert p.launched == ['first']


def test_multiple_commands_yield_without_certifying_partial_step(project):
    p = project
    p.steps[0].commands *= 2
    assert p.run(max_heavy_commands=1) == 75
    assert len(p.prepared) == 1 and p.launched == ['first']
    assert not (p.ctx.stamps / 'first.json').exists()


def test_unbounded_build_keeps_running(project):
    assert project.run() == 0
    assert project.launched == ['first', 'second', 'third']


@pytest.mark.parametrize('value', [0, -1, 1.5, True])
def test_api_rejects_invalid_budget_before_loading_recipe(project, value):
    with pytest.raises(ValueError, match='positive integer'):
        project.run(max_heavy_commands=value)
    assert not project.ctx.out.exists()


@pytest.mark.parametrize('value', ['0', '-2', '1.5', 'many'])
def test_cli_rejects_invalid_budget(value):
    with pytest.raises(SystemExit):
        cli.main(['build', 'fixture', '--max-heavy-commands', value])


@pytest.mark.parametrize('option', ['--plan', '--list', '--touch', '--timings', '--changes', '--ddc', '--json'])
def test_budget_requires_execution(option):
    with pytest.raises(SystemExit, match='requires build execution'):
        cli.main(['build', 'fixture', '--max-heavy-commands', '1', option])


def test_cli_forwards_budget(monkeypatch):
    observed = []
    monkeypatch.setattr(cli, 'build', lambda *args, **kwargs: observed.append((args, kwargs)) or 75)
    assert cli.main(['build', 'fixture', 'first', '--max-heavy-commands', '2']) == 75
    assert observed[0][0] == ('fixture', ['first'])
    assert observed[0][1]['max_heavy_commands'] == 2
