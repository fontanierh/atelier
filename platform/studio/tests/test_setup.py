"""The headless repair must be idempotent, preserve the installed engine on failure, and refuse unknown versions."""
from contextlib import nullcontext
import json
from pathlib import Path
import shlex

import pytest

from atelier import setup


def test_user_directory_patch_is_explicit_and_idempotent():
    original = 'class Unreal {\n' + setup.METHOD + '\t\t\treturn null;\n\t\t}\n}\n'
    patched = setup.patch_user_directory(original)
    assert patched.index(setup.HEADLESS_VARIABLE) < patched.index('return null')
    assert setup.patch_user_directory(patched) == patched
    with pytest.raises(ValueError):
        setup.patch_user_directory('a different engine source layout')


def test_explicit_xml_cache_also_supplies_incremental_makefile_inputs():
    original = 'if (overrideCacheFile != null) {\n' + setup.XML_CACHE_LOAD + '} else { ScanDefaultInputs(); }\n'
    patched = setup.patch_xml_cache_inputs(original)
    assert setup.XML_CACHE_LOAD + setup.XML_CACHE_INPUTS in patched
    assert patched.endswith('} else { ScanDefaultInputs(); }\n')
    assert setup.patch_xml_cache_inputs(patched) == patched
    with pytest.raises(ValueError):
        setup.patch_xml_cache_inputs('a different engine source layout')


def test_wrapper_quotes_cache_paths_and_replaces_only_its_own_block(tmp_path):
    cache = tmp_path / "cache with spaces and a ' quote"
    original = '#!/bin/sh\necho Running ' + setup.INVOCATION + '\n' + setup.INVOCATION + '\nExitCode=$?\n'
    patched = setup.patch_build_script(original, cache, 3)
    command = next(line for line in patched.splitlines() if line.startswith('dotnet '))
    assert shlex.split(command)[-2:] == ['-XmlConfigCache=' + str(cache / 'remote-xmlconfig.bin'), '-MaxParallelActions=3']
    assert setup.patch_build_script(patched, cache, 3) == patched
    assert ('echo Running ' + setup.INVOCATION + '\n') in patched
    assert len([line for line in patched.splitlines() if line.startswith('dotnet ')]) == 1
    assert '-MaxParallelActions=2' in setup.patch_build_script(patched, cache, 2)
    assert 'ExitCode=$?' in patched
    with pytest.raises(ValueError):
        setup.patch_build_script(original.replace('"$@"', 'custom arguments'), cache, 3)


@pytest.mark.parametrize('cores', [8, 10, 16, 24])
def test_shader_worker_cap_covers_both_engine_selection_branches(cores):
    import math
    original = '[DevOptions.Shaders]\nNumUnusedShaderCompilingThreads=3\nNumUnusedShaderCompilingThreadsDuringGame=4\nPercentageUnusedShaderCompilingThreads=50\n[Other]\nKeep=1\n'
    patched = setup.patch_shader_config(original, 3, cores)
    values = dict(line.split('=', 1) for line in patched.splitlines() if '=' in line)
    assert cores - int(values['NumUnusedShaderCompilingThreads']) == 3
    assert cores - int(values['NumUnusedShaderCompilingThreadsDuringGame']) == 3
    assert cores - math.ceil(cores * float(values['PercentageUnusedShaderCompilingThreads']) / 100) <= 3
    assert setup.patch_shader_config(patched, 3, cores) == patched
    assert '[Other]\nKeep=1\n' in patched


@pytest.fixture
def engine(tmp_path, monkeypatch):
    root = tmp_path / 'installed engine'
    files = {
        'Engine/Build/Build.version': json.dumps(dict(MajorVersion=5, MinorVersion=8, PatchVersion=2, Changelist=56702186)),
        'Engine/Source/Programs/Shared/EpicGames.Build/Unreal.cs': setup.METHOD + '\t\t\treturn null;\n\t\t}\n',
        'Engine/Source/Programs/UnrealBuildTool/Configuration/Xml/XmlConfig.cs': setup.XML_CACHE_LOAD,
        'Engine/Build/BatchFiles/Mac/Build.sh': '#!/bin/sh\necho Running ' + setup.INVOCATION + '\n' + setup.INVOCATION + '\nExitCode=$?\n',
        'Engine/Config/BaseEngine.ini': '[DevOptions.Shaders]\nNumUnusedShaderCompilingThreads=3\nNumUnusedShaderCompilingThreadsDuringGame=4\nPercentageUnusedShaderCompilingThreads=50\n',
        'Engine/Binaries/DotNET/UnrealBuildTool/EpicGames.Build.dll': 'original binary',
        'Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll': 'original UBT binary',
    }
    for relative, contents in files.items():
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(contents)
    monkeypatch.setattr(setup.paths, 'cache_dir', lambda *args: tmp_path / 'cache')
    (tmp_path / 'cache').mkdir()
    monkeypatch.setattr(setup, 'render_lock', lambda *args, **kwargs: nullcontext())
    return root, files


def test_failed_managed_build_restores_source_wrapper_and_binary(engine, monkeypatch):
    root, files = engine
    monkeypatch.setattr(setup.guarded, 'run', lambda *args, **kwargs: 1)
    with pytest.raises(RuntimeError, match='exit 1'):
        setup.prepare_headless(root)
    for relative, contents in files.items():
        assert (root / relative).read_text() == contents


def test_read_only_installer_files_are_repaired_and_keep_their_modes(engine, monkeypatch):
    root, files = engine
    for relative in files:
        (root / relative).chmod(0o444)

    def rebuild(command, folder, **kwargs):
        output = Path(command[command.index('-o') + 1])
        output.mkdir(parents=True, exist_ok=True)
        for name in ('EpicGames.Build.dll', 'UnrealBuildTool.dll'):
            (output / name).write_text('patched binary')
        return 0

    monkeypatch.setattr(setup.guarded, 'run', rebuild)
    setup.prepare_headless(root)
    for relative in files:
        expected = 0o555 if relative.endswith('/Build.sh') else 0o444
        assert (root / relative).stat().st_mode & 0o777 == expected


def test_unknown_engine_is_refused_before_any_mutation(engine):
    root, files = engine
    file = root / 'Engine/Build/Build.version'
    file.write_text(file.read_text().replace('56702186', '1'))
    with pytest.raises(ValueError, match='not modified'):
        setup.prepare_headless(root)
    for relative, contents in files.items():
        if relative != 'Engine/Build/Build.version':
            assert (root / relative).read_text() == contents


def test_repeat_setup_skips_rebuild_but_detects_replaced_binary(engine, monkeypatch, tmp_path):
    root, _ = engine
    calls = []

    def rebuild(command, folder, **kwargs):
        assert kwargs['lock'] is False  # the enclosing repair holds both slots as a compile
        calls.append(command)
        output = Path(command[command.index('-o') + 1])
        output.mkdir(parents=True, exist_ok=True)
        (output / 'EpicGames.Build.dll').write_text('patched binary')
        (output / 'UnrealBuildTool.dll').write_text('patched UBT binary')
        assert command[command.index('build') + 1].endswith('/UnrealBuildTool/UnrealBuildTool.csproj')
        return 0

    monkeypatch.setattr(setup.guarded, 'run', rebuild)
    setup.prepare_headless(root)
    wrapper = root / 'Engine/Build/BatchFiles/Mac/Build.sh'
    first = wrapper.read_bytes()
    assert wrapper.stat().st_mode & 0o111 == 0o111
    setup.prepare_headless(root)
    assert len(calls) == 1 and wrapper.read_bytes() == first
    (root / 'Engine/Binaries/DotNET/UnrealBuildTool/EpicGames.Build.dll').write_text('vendor update')
    setup.prepare_headless(root)
    assert len(calls) == 2
    (root / 'Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll').write_text('vendor UBT update')
    setup.prepare_headless(root)
    assert len(calls) == 3
    assert (tmp_path / 'cache/remote-xmlconfig.bin').read_bytes() == b'\x02' + b'\0' * 11


def test_cli_tools_only_reports_full_xcode_before_trying_metal(monkeypatch):
    monkeypatch.setattr(setup.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(setup, '_command', lambda *args: (True, '/Library/Developer/CommandLineTools'))
    checks = setup.mac_checks()
    assert len(checks) == 1 and checks[0][0] is False
    assert 'CLI tools alone' in checks[0][1]
