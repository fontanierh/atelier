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


def test_source_editor_app_is_a_command_line_fallback(monkeypatch, tmp_path):
    root = tmp_path / 'Source Engine'
    monkeypatch.setenv('UE_ROOT', str(root))
    app = engine.unreal_app(root)
    app.parent.mkdir(parents=True)
    app.write_bytes(b'never executed during discovery')
    assert engine.unreal_cmd() == app
    assert build.Context('sandbox').unreal_cmd == app
    command = root / 'Engine/Binaries/Mac/UnrealEditor-Cmd'
    command.touch()
    assert engine.unreal_cmd() == command


def test_editor_fallback_respects_explicit_engine_root(monkeypatch, tmp_path):
    monkeypatch.setenv('UE_ROOT', str(tmp_path / 'Other Engine'))
    root = tmp_path / 'Selected Engine'
    app = engine.unreal_app(root)
    app.parent.mkdir(parents=True)
    app.touch()
    assert engine.unreal_cmd(root) == app
    app.unlink()
    assert engine.unreal_cmd(root) == root / 'Engine/Binaries/Mac/UnrealEditor-Cmd'


def test_compile_caps_native_and_browser_targets(monkeypatch, tmp_path):
    monkeypatch.setenv('UE_ROOT', str(tmp_path / 'Source Engine'))
    ctx = build.Context('sandbox')
    for target, platform in [('SandboxEditor', 'Mac'), ('Sandbox', 'HTML5')]:
        command = build.UnrealCompile(target, platform=platform, args=('-NoDebugInfo',))
        argv = command.argv(ctx)
        assert argv[1:4] == [target, platform, 'Development']
        assert '-MaxParallelActions=3' in argv and '-NoDebugInfo' in argv
        assert dict(command.env) == dict(DOTNET_PROCESSOR_COUNT='3', EMCC_CORES='3', BINARYEN_CORES='3')
        assert command.timeout > 1800 and command.progress <= 30
        assert Path(argv[0]).name == ('Build.sh' if platform == 'Mac' else 'RunUBT.sh')


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


def test_compile_postlink_children_use_aggregate_guard(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace

    ctx = SimpleNamespace(game='fixture', logs=tmp_path, env=lambda extra: dict(extra))
    command = build.UnrealCompile('Fixture', platform='HTML5')
    step = build.Step('browser.compile', [command], heavy=True)
    observed = {}

    def guarded(argv, folder, **kwargs):
        observed.update(kwargs)
        folder.mkdir()
        (folder / 'stdout.log').write_text('Post-link preparation completed\n')
        return 0

    monkeypatch.setattr(build.guarded, 'run', guarded)
    build.run_argv(ctx, step, command, ['fixture-build'], command.env, io.StringIO(), None, None)
    assert observed['kind'] == 'compile'
    assert observed['aggregate_tree'] and observed['track_tree']
    assert observed['env']['BINARYEN_CORES'] == '3'


def test_homebrew_bash_forwarder_resolves_the_complete_app(monkeypatch, tmp_path):
    wrapper, binary = blender_wrapper(tmp_path, 'exec "{binary}"  "$@"')
    wrapper.write_text(wrapper.read_text().replace('#!/bin/sh', '#!/bin/bash', 1))
    monkeypatch.delenv('BASH_ENV', raising=False)
    monkeypatch.delenv('SHELLOPTS', raising=False)
    for name in list(os.environ):
        if name.startswith('BASH_FUNC_'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('BLENDER', str(wrapper))
    assert engine.blender() == str(binary)


@pytest.mark.parametrize('name', ['BASH_ENV', 'SHELLOPTS', 'BASH_FUNC_exec%%'])
def test_bash_custom_startup_retains_wrapper_identity(monkeypatch, tmp_path, name):
    wrapper, binary = blender_wrapper(tmp_path, 'exec "{binary}" "$@"')
    wrapper.write_text(wrapper.read_text().replace('#!/bin/sh', '#!/bin/bash', 1))
    monkeypatch.setenv('BLENDER', str(wrapper))
    monkeypatch.setenv(name, 'custom-startup')
    assert engine.blender() == str(wrapper)
