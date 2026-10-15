"""Where the tools are: one answer for the build, setup and game tools."""
import os
from pathlib import Path

import pytest

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


def blender_wrapper(tmp_path, command, app='Blender With Spaces.app'):
    binary = tmp_path / app / 'Contents/MacOS/Blender'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'not executed during discovery\n')
    binary.chmod(0o755)
    wrapper = tmp_path / 'blender'
    wrapper.write_text('#!/bin/sh\n# Forward to the real bundled runtime.\n' + command.format(binary=binary) + '\n')
    wrapper.chmod(0o755)
    return wrapper, binary


def test_path_wrapper_resolves_app_without_environment(monkeypatch, tmp_path):
    wrapper, binary = blender_wrapper(tmp_path, 'exec "{binary}" "$@"')
    monkeypatch.delenv('BLENDER', raising=False)
    monkeypatch.setattr(engine.shutil, 'which', lambda name: str(wrapper))
    assert engine.blender() == str(binary)
    assert build.Context('sandbox').blender == str(binary)


def test_explicit_wrapper_and_executable_keep_precedence(monkeypatch, tmp_path):
    wrapper, binary = blender_wrapper(tmp_path, 'exec "{binary}" "$@" # no extra flags')
    monkeypatch.setattr(engine.shutil, 'which', lambda name: '/another/blender')
    monkeypatch.setenv('BLENDER', str(wrapper))
    assert engine.blender() == str(binary)
    other = tmp_path / 'chosen-blender'
    other.write_bytes(b'\x00binary')
    monkeypatch.setenv('BLENDER', str(other))
    assert engine.blender() == str(other)


def test_unquoted_forwarding_wrapper(monkeypatch, tmp_path):
    wrapper, binary = blender_wrapper(tmp_path, 'exec {binary} "$@"', app='Blender.app')
    monkeypatch.delenv('BLENDER', raising=False)
    monkeypatch.setattr(engine.shutil, 'which', lambda name: str(wrapper))
    assert engine.blender() == str(binary)


@pytest.mark.parametrize('command', [
    'exec "{binary}" --background "$@"',
    'export EXTRA=1\nexec "{binary}" "$@"',
    'if true; then exec "{binary}" "$@"; fi',
    'exec "{binary}" $@',
    'exec "{binary}" \'$@\'',
    'exec "{binary}" "$@"; touch marker',
    'exec "$CUSTOM_BLENDER" "$@"',
    'exec "$(touch marker)" "$@"',
    'exec "{binary}" "$@"#suffix',
    'exec\u00a0"{binary}" "$@"',
    'exec "{binary}" "$@"\r',
    'exec "{binary}" "$@"\x1c',
])
def test_nontransparent_wrappers_are_preserved(monkeypatch, tmp_path, command):
    wrapper, _ = blender_wrapper(tmp_path, command)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('BLENDER', str(wrapper))
    assert engine.blender() == str(wrapper)
    assert not (tmp_path / 'marker').exists()


def test_missing_forward_target_is_preserved(monkeypatch, tmp_path):
    wrapper, binary = blender_wrapper(tmp_path, 'exec "{binary}" "$@"')
    binary.unlink()
    monkeypatch.setenv('BLENDER', str(wrapper))
    assert engine.blender() == str(wrapper)


def test_crlf_wrapper_is_preserved(monkeypatch, tmp_path):
    wrapper, _ = blender_wrapper(tmp_path, 'exec "{binary}" "$@"')
    wrapper.write_bytes(wrapper.read_bytes().replace(b'\n', b'\r\n'))
    monkeypatch.setenv('BLENDER', str(wrapper))
    assert engine.blender() == str(wrapper)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='requires POSIX FIFO')
def test_special_file_is_not_opened(monkeypatch, tmp_path):
    selected = tmp_path / 'blender-fifo'
    os.mkfifo(selected, 0o755)
    monkeypatch.setenv('BLENDER', str(selected))
    monkeypatch.setattr(engine, 'open', lambda *args, **kwargs: pytest.fail('opened a special file'), raising=False)
    assert engine.blender() == str(selected)
