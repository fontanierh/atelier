"""Mac toolchain checks and the opt-in UE 5.8.2 headless build-tool repair.

Only source edits authored here are stored in the repository. The installed engine's source and compiled DLLs stay
on the user's machine; originals and repair logs go to the machine cache. No engine download or Xcode installation
is performed by this command.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import struct
import subprocess
import tempfile

from . import paths
from .safety import guarded
from .safety.render_lock import render_lock

HEADLESS_VARIABLE = 'UE_HEADLESS_USER_DIR'
METHOD = '\t\tprivate static DirectoryReference? GetUserDirectory()\n\t\t{\n'
OVERRIDE = '''\t\t\t// Route headless build settings to an explicit, unprotected directory.
\t\t\tstring? userDirectoryOverride = Environment.GetEnvironmentVariable("UE_HEADLESS_USER_DIR");
\t\t\tif (!String.IsNullOrEmpty(userDirectoryOverride))
\t\t\t{
\t\t\t\treturn new DirectoryReference(userDirectoryOverride);
\t\t\t}

'''
INVOCATION = 'dotnet Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll "$@"'
BEGIN = '# BEGIN ATELIER HEADLESS BUILD'
END = '# END ATELIER HEADLESS BUILD'


def engine_root():
    return Path(os.environ.get('UE_ROOT') or '/Users/Shared/Epic Games/UE_5.8').resolve()


def _command(args, timeout=15):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)


def mac_checks():
    """Check full Xcode and actually compile/link a tiny Metal shader (finding the compiler alone is insufficient)."""
    if platform.system() != 'Darwin':
        return [(False, 'macOS on Apple silicon is the tested build platform')]
    ok, developer = _command(['xcode-select', '-p'])
    full = ok and developer.endswith('.app/Contents/Developer') and Path(developer).is_dir()
    checks = [(full, 'full Xcode selected; CLI tools alone cannot build Unreal '
               '(install Xcode, then sudo xcode-select -s /Applications/Xcode.app/Contents/Developer)')]
    if not full:
        return checks
    ok, version = _command(['xcodebuild', '-version'])
    checks.append((ok, version.replace('\n', ', ') if ok else 'accept the Xcode licence and run sudo xcodebuild -runFirstLaunch'))
    ok, sdk = _command(['xcrun', '--sdk', 'macosx', '--show-sdk-version'])
    checks.append((ok, 'macOS SDK ' + sdk))
    with tempfile.TemporaryDirectory(prefix='atelier-metal-') as folder:
        folder = Path(folder)
        source, air, library = folder / 'check.metal', folder / 'check.air', folder / 'check.metallib'
        source.write_text('#include <metal_stdlib>\nusing namespace metal;\nkernel void check(device float *out [[buffer(0)]], uint i [[thread_position_in_grid]]) { out[i] = 1.0; }\n')
        compiled, _ = _command(['xcrun', '--sdk', 'macosx', 'metal', '-c', str(source), '-o', str(air)], 30)
        linked = compiled and _command(['xcrun', '--sdk', 'macosx', 'metallib', str(air), '-o', str(library)], 30)[0]
        checks.append((bool(linked and library.is_file()), 'Metal compiler and linker '
                       '(if missing: xcodebuild -downloadComponent MetalToolchain)'))
    return checks


def patch_user_directory(text):
    if METHOD + OVERRIDE in text:
        return text
    if HEADLESS_VARIABLE in text or text.count(METHOD) != 1:
        raise ValueError('Unrecognised Unreal.cs; refusing to guess a source patch')
    return text.replace(METHOD, METHOD + OVERRIDE, 1)


def patch_build_script(text, cache, workers):
    """Keep the stock wrapper, adding only an explicit config directory, default XML cache and worker cap."""
    if BEGIN in text:
        start, finish = text.index(BEGIN), text.index(END) + len(END)
        text = text[:start] + INVOCATION + text[finish:]
    if text.splitlines().count(INVOCATION) != 1:
        raise ValueError('Unrecognised Build.sh; refusing to replace a custom build command')
    fragment = '\n'.join([
        BEGIN,
        'renice 10 $$ >/dev/null 2>&1',
        'export UE_HEADLESS_USER_DIR=' + shlex.quote(str(cache / 'user-config')),
        'mkdir -p "$UE_HEADLESS_USER_DIR"',
        INVOCATION + ' ' + shlex.quote('-XmlConfigCache=' + str(cache / 'remote-xmlconfig.bin')) + f' -MaxParallelActions={workers}',
        END,
    ])
    return text.replace(INVOCATION, fragment, 1)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_shader_config(text, workers, cores):
    """Use the same cap for commandlets and game launches, including CPUs using UE's percentage-based branch."""
    section = re.search(r'(?ms)^\[DevOptions.Shaders\]\n(.*?)(?=^\[|\Z)', text)
    if section is None:
        raise ValueError('Unrecognised shader configuration; engine was not modified')
    unused = max(0, cores - workers)
    values = dict(NumUnusedShaderCompilingThreads=str(unused), NumUnusedShaderCompilingThreadsDuringGame=str(unused),
                  PercentageUnusedShaderCompilingThreads=f'{100 * unused / cores:.8f}')
    body = section.group(1)
    for key, value in values.items():
        body, count = re.subn(r'(?m)^' + key + r'=[^\n]*$', key + '=' + value, body)
        if count != 1:
            raise ValueError('Unrecognised shader configuration: ' + key)
    return text[:section.start(1)] + body + text[section.end(1):]


def prepare_headless(root, workers=3):
    """Repair only the tested installed engine; run the small .NET rebuild under the render lock and memory guard."""
    if not isinstance(workers, int) or workers < 1:
        raise ValueError('workers must be a positive integer')
    root = root.resolve()
    version = json.loads((root / 'Engine/Build/Build.version').read_text())
    if tuple(version[k] for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (5, 8, 2, 56702186):
        raise ValueError('The headless repair is tested only with UE 5.8.2 CL 56702186; this engine was not modified')
    key = hashlib.sha256(str(root).encode()).hexdigest()[:16]
    cache = paths.cache_dir('toolchain', key)
    source = root / 'Engine/Source/Programs/Shared/EpicGames.Build/Unreal.cs'
    wrapper = root / 'Engine/Build/BatchFiles/Mac/Build.sh'
    shader_config = root / 'Engine/Config/BaseEngine.ini'
    binaries = root / 'Engine/Binaries/DotNET/UnrealBuildTool'
    dll = binaries / 'EpicGames.Build.dll'
    dotnet = root / 'Engine/Binaries/ThirdParty/DotNet/10.0/mac-arm64/dotnet'
    with render_lock('prepare headless Unreal build tool', kind='compile'):
        original_source, original_wrapper = source.read_text(), wrapper.read_text()
        new_source = patch_user_directory(original_source)
        new_wrapper = patch_build_script(original_wrapper, cache, workers)
        original_shaders = shader_config.read_text()
        new_shaders = patch_shader_config(original_shaders, workers, os.cpu_count() or 8)
        state_file = cache / 'headless.json'
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        current = state.get('source_sha256') == _sha(source) and state.get('dll_sha256') == _sha(dll)
        previous_binaries = {binaries / name: (binaries / name).read_bytes() if (binaries / name).exists() else None
                             for name in ('EpicGames.Build.dll', 'EpicGames.Build.pdb')}
        for file in (source, wrapper, shader_config, dll, binaries / 'EpicGames.Build.pdb'):
            backup = cache / 'originals' / file.relative_to(root)
            if file.exists() and not backup.exists():
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, backup)
        try:
            if not current or new_source != original_source:
                source.write_text(new_source)
                env = dict(os.environ, DOTNET_ROOT=str(dotnet.parent), DOTNET_CLI_TELEMETRY_OPTOUT='1',
                           DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
                output = cache / 'compiled'
                command = ['nice', '-n', '10', str(dotnet), 'build', str(source.with_name('EpicGames.Build.csproj')),
                           '-c', 'Development', '-o', str(output), '-maxcpucount:2', '-p:BuildInParallel=false']
                code = guarded.run(command, cache / 'rebuild.guard', timeout=600, lock=False, env=env, kind='compile')
                if code:
                    raise RuntimeError(f'Build-tool repair failed (exit {code}); see {cache / "rebuild.guard/stdout.log"}')
                if not (output / 'EpicGames.Build.dll').is_file():
                    raise RuntimeError('Build-tool repair produced no DLL')
                for name in ('EpicGames.Build.dll', 'EpicGames.Build.pdb'):
                    file = output / name
                    if file.exists():
                        shutil.copy2(file, binaries / name)
            (cache / 'user-config').mkdir(exist_ok=True)
            # UE 5.8 XmlConfigData serialization v2: no input files, no configured members. Remote mode uses
            # explicit command-line defaults, so protected Documents is never probed for BuildConfiguration.xml.
            (cache / 'remote-xmlconfig.bin').write_bytes(struct.pack('<iii', 2, 0, 0))
            wrapper.write_text(new_wrapper)
            shader_config.write_text(new_shaders)
            state_file.write_text(json.dumps(dict(engine=str(root), version=version, workers=workers,
                source_sha256=_sha(source), dll_sha256=_sha(dll)), indent=2) + '\n')
        except Exception:
            source.write_text(original_source)
            wrapper.write_text(original_wrapper)
            shader_config.write_text(original_shaders)
            for file, contents in previous_binaries.items():
                if contents is None:
                    file.unlink(missing_ok=True)
                else:
                    file.write_bytes(contents)
            raise
    print(f'Headless toolchain ready ({workers} workers, nice 10); originals and logs: {cache}')
    return 0


def main(headless=False, workers=3):
    checks = mac_checks()
    for ok, message in checks:
        print(('  ok    ' if ok else '  MISSING ') + message)
    if not all(ok for ok, _ in checks):
        return 1
    if headless:
        return prepare_headless(engine_root(), workers)
    print('Mac toolchain ready; for SSH-only builds use atelier setup --headless')
    return 0
