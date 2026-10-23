"""Unreal imports with owned Content outputs publish and restore like source actions; no Unreal launches."""
import json
import time
from types import SimpleNamespace

import pytest

from atelier import build, build_cache, build_checkpoints, checkpoint_actions as actions, checkpoint_store as cp, paths
from atelier.unreal_saves import outside, saved


def save_line(content, relative):
    destination = f'../../../../{content.parent.parent.name}/{content.parent.name}/Content/{relative}'
    return f"[0]LogSavePackage: Moving '../../Saved/tmp1.tmp' to '{destination}'\n"


def test_saved_packages_are_read_from_the_log(tmp_path):
    content = tmp_path / 'game/unreal/Content'
    log = tmp_path / 'step.log'
    log.write_text(save_line(content, 'FX/M_Glow.uasset') + save_line(content, 'Japan/Assets/SM_Car.uasset')
                   + "[0]LogSavePackage: Moving 'a.tmp' to '/elsewhere/Other/Content/X.uasset'\n")
    assert saved(log, content) == ['FX/M_Glow.uasset', 'Japan/Assets/SM_Car.uasset']
    assert outside(log, content, [content / 'FX']) == ['Japan/Assets/SM_Car.uasset']
    assert outside(log, content, [content / 'FX', content / 'Japan']) == []


@pytest.fixture
def unreal_build(tmp_path, monkeypatch):
    repo = tmp_path.resolve(); (repo / 'uv.lock').write_text('lock')
    monkeypatch.setattr(paths, 'REPO', repo)
    monkeypatch.setattr(paths, 'ENGINE_PLUGINS', repo / 'plugins')
    monkeypatch.setattr(paths, 'build_root', lambda: repo / 'build')
    monkeypatch.setenv('ATELIER_CACHE', str(repo / 'cache'))
    project = repo / 'game/unreal'; project.mkdir(parents=True)
    content = project / 'Content'
    ctx = SimpleNamespace(game='fixture', out=repo / 'build/fixture', logs=repo / 'build/fixture/logs',
                          stamps=repo / 'build/fixture/stamps', cook_mode=build.CookMode.DEFAULT,
                          uproject=project / 'Game.uproject', unreal_root=None,
                          checkpoint_observed_context='fixture context')  # Set by prepare() in real builds.
    ctx.uproject.write_text('{}')
    script = repo / 'import_fx.py'; script.write_text('# import')
    step = build.Step('unreal.fx', [build.UnrealScript(script, 'FX IMPORT COMPLETE')], inputs=[script],
                      checkpoint_outputs=(content / 'FX',))
    monkeypatch.setattr(build, 'Context', lambda *a, **kw: ctx)
    monkeypatch.setattr(build, 'load_recipe', lambda _: SimpleNamespace(steps=lambda ctx: [step]))
    monkeypatch.setattr(build_checkpoints, 'configured', lambda ctx: {})
    monkeypatch.setattr(build_checkpoints, 'prepare', lambda *a, **kw: None)
    monkeypatch.setattr(build_cache, 'tool_context', lambda *a, **kw: dict(tool='fixed'))
    launches, extra = [], []

    def run(ctx, step, command, log, *args, **kw):  # Stands in for the Unreal editor.
        launches.append(step.name)
        for relative in ('FX/M_Glow.uasset', 'FX/Textures/T_Glow.uasset', *extra):
            (content / relative).parent.mkdir(parents=True, exist_ok=True)
            (content / relative).write_bytes(b'package ' + relative.encode())
            log.write(save_line(content, relative))
    monkeypatch.setattr(build, 'run_command', run)
    messages = []
    return SimpleNamespace(ctx=ctx, step=step, content=content, launches=launches, extra=extra, messages=messages,
                           run=lambda: build.build('fixture', echo=messages.append))


def test_an_unreal_import_publishes_and_restores_without_a_launch(unreal_build):
    p = unreal_build
    assert p.run() == 0 and p.launches == ['unreal.fx']
    stamp = json.loads((p.ctx.stamps / 'unreal.fx.json').read_text())
    assert actions.entry_path(cp.Store('fixture'), stamp['checkpoint_key']).is_file()
    import shutil
    shutil.rmtree(p.content / 'FX')
    started = time.monotonic()
    assert p.run() == 0
    assert p.launches == ['unreal.fx']  # Restored, not relaunched.
    assert time.monotonic() - started < 5
    assert (p.content / 'FX/Textures/T_Glow.uasset').read_bytes() == b'package FX/Textures/T_Glow.uasset'
    assert any('restored in' in m and 'checkpoint action' in m for m in p.messages)


def test_an_import_that_saves_outside_its_outputs_stays_local(unreal_build):
    p = unreal_build
    p.extra.append('Japan/Assets/SM_Shared.uasset')
    assert p.run() == 0
    stamp = json.loads((p.ctx.stamps / 'unreal.fx.json').read_text())
    assert 'checkpoint_key' not in stamp
    assert not list((cp.Store('fixture').directory / 'actions').glob('*.json'))
    assert any('kept local, not published' in m and 'Japan/Assets/SM_Shared.uasset' in m for m in p.messages)
    p.messages.clear()
    assert p.run() == 0 and p.launches == ['unreal.fx']  # Still current locally.
