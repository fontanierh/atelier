"""Where the tools are: one answer for the build, setup and game tools."""
import os
from pathlib import Path

from atelier import build, engine, setup


def test_overrides_and_standard_paths(monkeypatch, tmp_path):
    monkeypatch.delenv('UE_ROOT', raising=False)
    assert engine.unreal_root() == Path(engine.DEFAULT_UE_ROOT)
    monkeypatch.setenv('UE_ROOT', str(tmp_path / 'UE'))
    assert engine.unreal_root() == tmp_path / 'UE'
    assert engine.unreal_cmd() == tmp_path / 'UE/Engine/Binaries/Mac/UnrealEditor-Cmd'
    assert engine.unreal_app().name == 'UnrealEditor' and 'UnrealEditor.app' in engine.unreal_app().parts
    assert setup.engine_root() == (tmp_path / 'UE').resolve()
    blender = tmp_path / 'Blender'
    blender.touch()
    link = tmp_path / 'blender-link'
    link.symlink_to(blender)
    monkeypatch.setenv('BLENDER', str(link))
    assert engine.blender() == os.path.realpath(blender), 'the real executable, not the symlink'


def test_build_context_reports_the_same_tools(monkeypatch, tmp_path):
    monkeypatch.setenv('UE_ROOT', str(tmp_path / 'UE'))
    ctx = build.Context('sandbox')
    assert (ctx.unreal_root, ctx.unreal_cmd, ctx.unreal_app, ctx.blender) == (
        engine.unreal_root(), engine.unreal_cmd(), engine.unreal_app(), engine.blender())
